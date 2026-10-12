"""Qualify all trigger families through durable reviews on an owned database."""
from copy import deepcopy


def qualify(connection, provider, route, root):
    from pgadmin.cdeadmin.providers.firebird.schema_application import capture, apply_review
    from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan, digest
    from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications
    target = {'endpoint_id': 'owned', 'database_target_id': 'owned', 'generation': 'trigger-native'}
    store = SchemaApplications(root / 'trigger-receipts.json')
    def snapshot():
        if connection.main_transaction.is_active():
            connection.rollback()
        result = capture(connection, target)
        connection.rollback()
        return result
    def application(base, desired):
        desired['sha256'] = digest(desired['rows'])
        plan = build_plan(base, desired, base)
        assert plan['status'] == 'review-ready', plan['blockers']
        review = store.review(plan, base, desired, 'owned', 'owned', route['database'])
        return SchemaApplications(store.path).apply({'review_id': review['review_id'],
            'review_digest': review['review_digest'], 'confirmed': True}, 'owned', 'owned',
            lambda record: apply_review(provider, route, record))['outcome']
    def expect_commit(outcome):
        assert outcome['native_commit_returned'] and outcome['attachment_released'], outcome
        if not outcome['rediscovery']['available']:
            from pgadmin.cdeadmin.workspace.firebird_schema_plan import _model
            for row in snapshot()['rows'].values():
                if row['kind'] == 'trigger' and row['name'] in {item[0] for item in definitions}:
                    try:
                        _model(row)
                    except Exception as error:
                        raise AssertionError((row['name'], row['path'], row['native'], str(error))) from error
        assert outcome['rediscovery']['available'], outcome
        assert all(item['matches_reviewed_properties'] for item in outcome['rediscovery']['objects']), outcome
    def fresh_work(expected):
        owned = provider.client._connect({'route': route})
        try:
            with owned.cursor() as cursor:
                for event in ('CONNECT', 'START'):
                    cursor.execute("SELECT RDB$GET_CONTEXT('USER_SESSION', ?) FROM RDB$DATABASE", [event])
                    assert cursor.fetchone()[0] == 'seen', event
                cursor.execute('INSERT INTO TRIGGER_DATA (ID, V) VALUES (1, 0) RETURNING V')
                assert cursor.fetchone()[0] == expected
            owned.commit()
            with owned.cursor() as cursor:
                cursor.execute("SELECT RDB$GET_CONTEXT('USER_SESSION', 'COMMIT') FROM RDB$DATABASE")
                assert cursor.fetchone()[0] == 'seen'
            owned.rollback()
            with owned.cursor() as cursor:
                cursor.execute("SELECT RDB$GET_CONTEXT('USER_SESSION', 'ROLLBACK') FROM RDB$DATABASE")
                assert cursor.fetchone()[0] == 'seen'
                cursor.execute('DELETE FROM TRIGGER_DATA')
            owned.commit()
        finally:
            if owned.main_transaction.is_active():
                owned.rollback()
            provider.client._release_attachment(owned)
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE TRIGGER_DATA (ID INTEGER, V INTEGER)')
        cursor.execute('CREATE ROLE TRIGGER_READER')
    connection.commit()
    base = snapshot(); desired = deepcopy(base)
    definitions = [('A_DML', 1, 'TRIGGER_DATA', 'BEGIN NEW.V = 7; END')]
    for number, name in enumerate(['CONNECT', 'DISCONNECT', 'START', 'COMMIT', 'ROLLBACK']):
        definitions.append(('DB_' + name, 8192 + number, None,
            "BEGIN RDB$SET_CONTEXT('USER_SESSION', '" + name + "', 'seen'); END"))
    definitions.append(('DDL_EVENT', 16384 | (1 << 1) | (1 << 2), None,
        "BEGIN RDB$SET_CONTEXT('USER_SESSION', 'DDL', 'seen'); END"))
    for name, event, relation, body in definitions:
        identity = 'trigger:' + name
        desired['rows'][identity] = {'resource_id': identity, 'kind': 'trigger', 'path': [relation, name] if relation else [name],
            'name': name, 'system': 'false', 'native': {'relation': relation, 'trigger_type': event,
            'inactive': 0, 'position': 0, 'metadata_source': body, 'sql_security': True,
            'engine_name': None, 'entrypoint': None, 'description': 'owned native trigger'}}
    expect_commit(application(base, desired))
    fresh_work(7)
    with connection.cursor() as cursor:
        cursor.execute('GRANT SELECT ON TRIGGER_DATA TO TRIGGER A_DML')
    connection.commit()
    ddl_connection = provider.client._connect({'route': route})
    try:
        with ddl_connection.cursor() as cursor:
            cursor.execute('CREATE TABLE DDL_PROBE (ID INTEGER)')
            cursor.execute("SELECT RDB$GET_CONTEXT('USER_SESSION', 'DDL') FROM RDB$DATABASE")
            assert cursor.fetchone()[0] == 'seen'
        ddl_connection.commit()
    finally:
        if ddl_connection.main_transaction.is_active():
            ddl_connection.rollback()
        provider.client._release_attachment(ddl_connection)
    base = snapshot(); desired = deepcopy(base)
    for name, _, _, _ in definitions:
        desired['rows']['trigger:' + name]['native'].update(position=5, sql_security=None,
            description='changed trigger')
    desired['rows']['trigger:A_DML']['native']['metadata_source'] = 'BEGIN NEW.V = 9; END'
    expect_commit(application(base, desired))
    fresh_work(9)
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM RDB$USER_PRIVILEGES WHERE RDB$USER='A_DML' AND RDB$RELATION_NAME='TRIGGER_DATA' AND RDB$PRIVILEGE='S'")
        assert cursor.fetchone()[0] == 1
    connection.rollback()
    base = snapshot(); desired = deepcopy(base)
    desired['rows']['trigger:A_DML']['native']['metadata_source'] = 'BEGIN NEW.V = 11; END'
    desired['rows']['trigger:DDL_EVENT']['native']['metadata_source'] = 'BEGIN UNKNOWN_NATIVE_CALL(); END'
    failed = application(base, desired)
    assert failed['native_rollback_returned'] and not failed['native_commit_returned'], failed
    fresh_work(9)
    base = snapshot(); desired = deepcopy(base)
    desired['rows']['trigger:A_DML']['native']['inactive'] = 1
    expect_commit(application(base, desired))
    fresh_work(0)
    base = snapshot(); desired = deepcopy(base)
    native = {'relation': 'TRIGGER_CREATED', 'trigger_type': 1, 'inactive': 0, 'position': 0,
        'metadata_source': 'BEGIN NEW.V = 31; END', 'sql_security': None,
        'engine_name': None, 'entrypoint': None, 'description': 'created with table'}
    desired['rows']['table:TRIGGER_CREATED'] = {'resource_id': 'table:TRIGGER_CREATED', 'kind': 'table',
        'name': 'TRIGGER_CREATED', 'path': ['TRIGGER_CREATED'], 'system': 'false',
        'native': {'relation_type': 0, 'sql_security': None, 'publication_enabled': False,
            'columns': [{'name': 'V', 'position': 0, 'field_type': 8, 'field_sub_type': 0,
                         'field_scale': 0, 'dimensions': 0}],
            'triggers': [{'name': 'TRIGGER_CREATED_BI', **native}]}}
    desired['rows']['trigger:TRIGGER_CREATED_BI'] = {'resource_id': 'trigger:TRIGGER_CREATED_BI',
        'kind': 'trigger', 'name': 'TRIGGER_CREATED_BI', 'path': ['TRIGGER_CREATED', 'TRIGGER_CREATED_BI'],
        'system': 'false', 'native': native}
    expect_commit(application(base, desired))
    with connection.cursor() as cursor:
        cursor.execute('INSERT INTO TRIGGER_CREATED DEFAULT VALUES RETURNING V')
        assert cursor.fetchone()[0] == 31
    connection.rollback()
    return {'durable_reviews': True, 'dml_native_effect': True, 'five_database_events_created': True,
            'connection_and_transaction_events_observed': True, 'ddl_event_observed': True,
            'all_family_alterations': True, 'security_override_removed': True, 'grants_preserved': True,
            'later_failure_rolls_back_earlier_trigger': True, 'inactive_effect_observed': True,
            'native_rediscovery': True, 'new_table_and_nested_trigger_created_once': True}
