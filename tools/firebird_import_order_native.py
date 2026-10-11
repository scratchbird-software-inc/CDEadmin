"""Qualify explicit row ordering without disabling native foreign keys."""
import json
from pgadmin.cdeadmin.providers.firebird.provider import ADMINISTRATION, _resources
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_data_import import preview


def qualify(connection, provider, route, root):
    def sql(source):
        with connection.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []
    sql('CREATE TABLE IMPORT_PARENT (ID INTEGER PRIMARY KEY, CHILD_ID INTEGER)')
    sql('CREATE TABLE IMPORT_CHILD (ID INTEGER PRIMARY KEY, PARENT_ID INTEGER REFERENCES IMPORT_PARENT(ID))')
    sql('ALTER TABLE IMPORT_PARENT ADD FOREIGN KEY (CHILD_ID) REFERENCES IMPORT_CHILD(ID)')
    connection.commit()
    model = build_export(_resources(connection, {}), endpoint_id='owned', target_id='owned', generation='order', native_model=True)
    connection.rollback()
    tables = []
    for name, rows in [('IMPORT_PARENT', [{'ID': 2, 'CHILD_ID': 10}, {'ID': 1, 'CHILD_ID': None}]),
                       ('IMPORT_CHILD', [{'ID': 10, 'PARENT_ID': 1}])]:
        tables.append({'name': name, 'native_columns': model['rows']['table:' + name]['native']['columns'], 'rows': rows})
    source = json.dumps({'format': 'scratchrobin.firebird.data@1', 'contents': 'data', 'row_count': 3, 'tables': tables})
    order = [{'table': 'IMPORT_PARENT', 'row': 1}, {'table': 'IMPORT_CHILD', 'row': 0}, {'table': 'IMPORT_PARENT', 'row': 0}]
    planned = preview(source, model, row_order=order)
    scoped = {**route, 'transaction_access': 'WRITE', 'transaction_isolation': 'SNAPSHOT', 'transaction_auto_commit': False}
    client = provider.client
    for decision in ('rollback', 'commit'):
        handle = client.open_session({'route': scoped})
        try:
            for operation in planned['operations']:
                request = {'resource_kind': 'table', 'operation_id': 'insert', '_provider_route': scoped,
                    'target_resource': planned['catalogs'][operation['table']]['resource'],
                    'draft': {'values': operation['values'], 'override_identity': operation['override_identity']}}
                result = ADMINISTRATION.apply(client, ADMINISTRATION.plan(request), connection=handle)
                assert result['staged_in_provider_session']
            assert sql('SELECT COUNT(*) FROM IMPORT_PARENT') == [(0,)]
            connection.rollback()
            client.control_transaction(handle, decision)
        finally:
            client.close_session(handle)
        assert sql('SELECT COUNT(*) FROM IMPORT_PARENT') == [(0 if decision == 'rollback' else 2,)]
        connection.rollback()
    try:
        sql('INSERT INTO IMPORT_CHILD VALUES (20, 999)')
    except Exception as error:
        assert 335544466 in getattr(error, 'gds_codes', ()), type(error)
        connection.rollback()
    else:
        raise AssertionError('Native foreign key not enforced')
    return {'explicit_interleaved_row_order': True, 'rollback_and_commit': True,
            'independent_visibility': True, 'native_constraints_remain_enforced': True}
