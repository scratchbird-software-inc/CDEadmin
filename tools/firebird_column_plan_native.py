"""Qualify durable reviewed column edits against an owned native database."""
from copy import deepcopy


def qualify(connection, provider, route, root):
    from pgadmin.cdeadmin.providers.firebird.schema_application import capture, apply_review
    from pgadmin.cdeadmin.providers.firebird.identity import catalog_resource_id
    from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan, digest
    from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications
    target = {'endpoint_id': 'owned', 'database_target_id': 'owned', 'generation': 'column-native'}
    store = SchemaApplications(root / 'column-receipts.json')
    def sql(source):
        with connection.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []
    def snapshot():
        if connection.main_transaction.is_active():
            connection.rollback()
        result = capture(connection, target)
        connection.rollback()
        return result
    def edit(document, column, changes, nested=False):
        identity = catalog_resource_id('column', ['COLUMN_PLAN'], column)
        document['rows'][identity]['native'].update(changes)
        if nested:
            for item in document['rows']['table:COLUMN_PLAN']['native']['columns']:
                if item['name'] == column:
                    item.update(changes)
        document['sha256'] = digest(document['rows'])
    def application(base, desired, before_dispatch=None):
        plan = build_plan(base, desired, base)
        assert plan['status'] == 'review-ready', plan['blockers']
        reviewed = store.review(plan, base, desired, 'owned', 'owned', route['database'])
        if before_dispatch:
            before_dispatch()
        return store.apply({'review_id': reviewed['review_id'], 'review_digest': reviewed['review_digest'],
                            'confirmed': True}, 'owned', 'owned',
                           lambda record: apply_review(provider, route, record))
    sql('CREATE TABLE COLUMN_PLAN (ID BIGINT GENERATED ALWAYS AS IDENTITY (START WITH 42 INCREMENT BY 3) PRIMARY KEY, V INTEGER, N INTEGER, C COMPUTED BY (V + 1), A INTEGER[-1:1], TXT VARCHAR(5) CHARACTER SET UTF8)')
    connection.commit()
    sql('INSERT INTO COLUMN_PLAN (V, N) VALUES (1, NULL)')
    connection.commit()
    base = snapshot(); wanted = deepcopy(base)
    edit(wanted, 'V', {'default_source': 'DEFAULT 7', 'not_null': 1, 'description': 'from design'}, True)
    edit(wanted, 'ID', {'identity_type': 1})
    edit(wanted, 'C', {'computed_source': '(V + 2)', 'field_type': 16, 'field_precision': 18, 'field_length': 8}, True)
    edit(wanted, 'N', {'field_type': 16, 'field_length': 8}, True)
    edit(wanted, 'TXT', {'character_length': 20, 'field_length': 80}, True)
    success = application(base, wanted)
    assert success['outcome']['native_commit_returned'], success
    assert success['outcome']['rediscovery']['available'], success
    assert all(item['matches_reviewed_properties'] for item in success['outcome']['rediscovery']['objects']), success
    assert sql('INSERT INTO COLUMN_PLAN DEFAULT VALUES RETURNING ID, V, C') == [(45, 7, 9)]
    connection.rollback()
    # Native data validation must roll back earlier DDL in this same plan.
    base = snapshot(); wanted = deepcopy(base)
    edit(wanted, 'ID', {'description': 'must roll back'})
    edit(wanted, 'N', {'not_null': 1})
    refused = application(base, wanted)
    assert refused['outcome']['native_rollback_returned'] and not refused['outcome']['native_commit_returned'], refused
    assert snapshot()['rows'][catalog_resource_id('column', ['COLUMN_PLAN'], 'ID')]['native']['description'] is None
    # Independently changed metadata must stop dispatch rather than overwrite.
    base = snapshot(); wanted = deepcopy(base)
    edit(wanted, 'V', {'default_source': 'DEFAULT 9'})
    def drift():
        sql("COMMENT ON COLUMN COLUMN_PLAN.V IS 'concurrent change'")
        connection.commit()
    stale = application(base, wanted, drift)
    assert stale['outcome']['statements_completed'] == 0 and stale['state'] == 'not_executed', stale
    # Dropping a local default/nullability is separate from domain state.
    base = snapshot(); wanted = deepcopy(base)
    edit(wanted, 'V', {'default_source': None, 'not_null': None, 'description': None}, True)
    removed = application(base, wanted)
    assert removed['outcome']['native_commit_returned'], removed
    assert all(item['matches_reviewed_properties'] for item in removed['outcome']['rediscovery']['objects']), removed
    base = snapshot(); wanted = deepcopy(base)
    identity = catalog_resource_id('column', ['COLUMN_PLAN'], 'NEW_COL')
    prototype = deepcopy(base['rows'][catalog_resource_id('column', ['COLUMN_PLAN'], 'V')])
    prototype.update(resource_id=identity, name='NEW_COL', path=['COLUMN_PLAN', 'NEW_COL'])
    prototype['native'].update(position=2, default_source='DEFAULT 11', description='added through native design')
    wanted['rows'][identity] = prototype
    sibling = deepcopy(prototype)
    sibling_id = catalog_resource_id('column', ['COLUMN_PLAN'], 'Z_ADDED')
    sibling.update(resource_id=sibling_id, name='Z_ADDED', path=['COLUMN_PLAN', 'Z_ADDED'])
    sibling['native'].update(position=1, default_source='DEFAULT 13')
    wanted['rows'][sibling_id] = sibling
    wanted['sha256'] = digest(wanted['rows'])
    created = application(base, wanted)
    assert created['outcome']['native_commit_returned'], created
    assert created['outcome']['rediscovery']['available'], created
    assert all(item['matches_reviewed_properties'] for item in created['outcome']['rediscovery']['objects']), created
    assert sql('SELECT V FROM COLUMN_PLAN') == [(1,)]
    assert sql('INSERT INTO COLUMN_PLAN DEFAULT VALUES RETURNING NEW_COL, Z_ADDED') == [(11, 13)]
    connection.rollback()
    base = snapshot(); wanted = deepcopy(base)
    name = 'COLUMN_CHILD_PLAN'
    child = deepcopy(base['rows'][identity])
    child_id = catalog_resource_id('column', [name], 'NEW_COL')
    child.update(resource_id=child_id, path=[name, 'NEW_COL'])
    child['native']['position'] = 0
    wanted['rows'][child_id] = child
    table_id = catalog_resource_id('table', [], name)
    wanted['rows'][table_id] = {'resource_id': table_id, 'kind': 'table', 'path': [name],
        'name': name, 'system': 'false', 'native': {'relation_type': 0, 'sql_security': None,
        'publication_enabled': False, 'description': None,
        'columns': [{'name': 'NEW_COL', **deepcopy(child['native'])}]}}
    wanted['sha256'] = digest(wanted['rows'])
    embedded = application(base, wanted)
    assert embedded['outcome']['native_commit_returned'], embedded
    assert embedded['outcome']['rediscovery']['available'], embedded
    assert all(item['matches_reviewed_properties'] for item in embedded['outcome']['rediscovery']['objects']), embedded
    base = snapshot(); wanted = deepcopy(base)
    for view, source, dependency in [('Z_COLUMN_VIEW', 'COLUMN_CHILD_PLAN', table_id),
                                     ('A_COLUMN_VIEW', 'Z_COLUMN_VIEW', 'view:Z_COLUMN_VIEW')]:
        view_id = catalog_resource_id('view', [], view)
        wanted['rows'][view_id] = {'resource_id': view_id, 'kind': 'view', 'path': [view],
            'name': view, 'system': 'false', 'native': {'relation_type': 1,
            'definition': 'SELECT NEW_COL FROM ' + source,
            'columns': [{'name': 'NEW_COL', 'position': 0}], 'creation_dependencies': [dependency]}}
    wanted['sha256'] = digest(wanted['rows'])
    ordered = application(base, wanted)
    assert ordered['outcome']['native_commit_returned'], ordered
    assert ordered['outcome']['rediscovery']['available'], ordered
    assert all(item['matches_reviewed_properties'] for item in ordered['outcome']['rediscovery']['objects']), ordered
    return {'durable_receipts': True, 'native_commit_and_rediscovery': True,
            'native_failure_rolls_back_all_ddl': True, 'drift_stops_dispatch': True,
            'identity_allocation_preserved': True, 'default_nullability_comment_removal': True,
            'native_column_add_and_position': True, 'computed_expression_changed': True,
            'new_table_standalone_column_once': True, 'scalar_type_alteration': True,
            'computed_type_alteration': True, 'character_length_alteration': True,
            'durable_creation_dependency_order': True}
