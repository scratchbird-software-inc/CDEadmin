"""Native routine signature/body qualification through stored application reviews."""
from copy import deepcopy


def qualify(connection, provider, route, root):
    from pgadmin.cdeadmin.providers.firebird.schema_application import capture, apply_review
    from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan, digest
    from pgadmin.cdeadmin.workspace.firebird_routine_plan import FIELDS
    from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications
    target = {'endpoint_id': 'owned', 'database_target_id': 'owned', 'generation': 'routine-native'}
    store = SchemaApplications(root / 'routine-receipts.json')
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
    def application(base, desired):
        desired['sha256'] = digest(desired['rows'])
        plan = build_plan(base, desired, base)
        assert plan['status'] == 'review-ready', plan['blockers']
        reviewed = store.review(plan, base, desired, 'owned', 'owned', route['database'])
        result = store.apply({'review_id': reviewed['review_id'], 'review_digest': reviewed['review_digest'],
            'confirmed': True}, 'owned', 'owned', lambda record: apply_review(provider, route, record))
        return result['outcome']
    def expect_commit(outcome):
        assert outcome['native_commit_returned'] and outcome['attachment_released'], outcome
        assert outcome['rediscovery']['available'], outcome
        assert all(item['matches_reviewed_properties'] for item in outcome['rediscovery']['objects']), outcome
    def fresh(source):
        owned = provider.client._connect({'route': route})
        try:
            with owned.cursor() as cursor:
                cursor.execute(source)
                return cursor.fetchall()
        finally:
            if owned.main_transaction.is_active():
                owned.rollback()
            provider.client._release_attachment(owned)
    sql('CREATE DOMAIN ROUTINE_DOMAIN AS NUMERIC(12,2) CHECK(VALUE >= 0)')
    sql('CREATE TABLE ROUTINE_TYPES (ID INTEGER, TXT VARCHAR(20) CHARACTER SET UTF8)')
    connection.commit()
    sql('CREATE PROCEDURE SOURCE_P (A TYPE OF ROUTINE_DOMAIN DEFAULT 2) RETURNS (R NUMERIC(12,2)) AS BEGIN R = A + 1; SUSPEND; END')
    sql('CREATE FUNCTION SOURCE_F (A TYPE OF COLUMN ROUTINE_TYPES.ID) RETURNS BIGINT DETERMINISTIC SQL SECURITY INVOKER AS BEGIN RETURN A + 1; END')
    sql('CREATE FUNCTION SOURCE_TEXT (A VARCHAR(20) CHARACTER SET UTF8) RETURNS VARCHAR(20) CHARACTER SET UTF8 AS BEGIN RETURN A; END')
    sql("COMMENT ON PROCEDURE PARAMETER SOURCE_P.A IS 'native input comment'")
    connection.commit()
    base = snapshot(); desired = deepcopy(base)
    for kind, old_name, name in [('procedure', 'SOURCE_P', 'P_DDN'),
                                ('function', 'SOURCE_F', 'F_DDN'),
                                ('function', 'SOURCE_TEXT', 'TEXT_DDN')]:
        row = deepcopy(base['rows'][kind + ':' + old_name]); identity = kind + ':' + name
        row.update(resource_id=identity, name=name, path=[name])
        row['native'] = {key: value for key, value in row['native'].items() if key in FIELDS | {'deterministic'}}
        desired['rows'][identity] = row
    expect_commit(application(base, desired))
    assert fresh('SELECT R FROM P_DDN') == [(3,)]
    assert fresh('SELECT F_DDN(4) FROM RDB$DATABASE') == [(5,)]
    assert fresh("SELECT TEXT_DDN('utf8 ü') FROM RDB$DATABASE") == [('utf8 ü',)]
    sql('CREATE ROLE ROUTINE_READER')
    sql('GRANT EXECUTE ON PROCEDURE P_DDN TO ROLE ROUTINE_READER')
    connection.commit()
    base = snapshot(); desired = deepcopy(base)
    procedure = desired['rows']['procedure:P_DDN']['native']
    procedure['metadata_source'] = 'BEGIN R = A + 3; SUSPEND; END'
    procedure['parameters'][0]['default_source'] = 'DEFAULT 5'
    procedure['parameters'][0]['description'] = 'changed default'
    function = desired['rows']['function:F_DDN']['native']
    function.update(metadata_source='BEGIN RETURN A + 2; END', deterministic=0, sql_security=True)
    for parameter in function['parameters']:
        if parameter['return_value']:
            parameter.update(field_type=26, field_length=16, field_precision=0)
    expect_commit(application(base, desired))
    assert fresh('SELECT R FROM P_DDN') == [(8,)]
    assert fresh('SELECT F_DDN(4) FROM RDB$DATABASE') == [(6,)]
    assert sql("SELECT COUNT(*) FROM RDB$USER_PRIVILEGES WHERE RDB$RELATION_NAME='P_DDN' AND RDB$USER='ROUTINE_READER' AND RDB$PRIVILEGE='X'") == [(1,)]
    connection.rollback()
    base = snapshot(); desired = deepcopy(base)
    desired['rows']['function:F_DDN']['native']['metadata_source'] = 'BEGIN RETURN A + 99; END'
    desired['rows']['procedure:P_DDN']['native']['metadata_source'] = 'BEGIN R = UNKNOWN_COLUMN; SUSPEND; END'
    refused = application(base, desired)
    assert refused['native_rollback_returned'] and not refused['native_commit_returned'], refused
    assert fresh('SELECT F_DDN(4) FROM RDB$DATABASE') == [(6,)]
    type_matrix = [
        'SMALLINT', 'INTEGER', 'BIGINT', 'INT128',
        'NUMERIC(4,2)', 'NUMERIC(9,3)', 'NUMERIC(18,4)', 'NUMERIC(38,8)',
        'DECIMAL(4,2)', 'DECIMAL(18,4)', 'DECIMAL(38,8)',
        'CHAR(5) CHARACTER SET UTF8 COLLATE UNICODE_CI',
        'VARCHAR(15) CHARACTER SET UTF8', 'BINARY(5)', 'VARBINARY(12)',
        'BLOB SUB_TYPE 0 SEGMENT SIZE 256',
        'BLOB SUB_TYPE TEXT SEGMENT SIZE 120 CHARACTER SET UTF8',
        'BLOB SUB_TYPE -2 SEGMENT SIZE 80', 'DATE', 'TIME', 'TIMESTAMP',
        'TIME WITH TIME ZONE', 'TIMESTAMP WITH TIME ZONE', 'BOOLEAN',
        'FLOAT', 'DOUBLE PRECISION', 'DECFLOAT(16)', 'DECFLOAT(34)']
    for ordinal, definition in enumerate(type_matrix):
        sql(f'CREATE FUNCTION SOURCE_TYPE_{ordinal} (A {definition}) RETURNS {definition} AS BEGIN RETURN A; END')
    connection.commit()
    for start in range(0, len(type_matrix), 4):
        base = snapshot(); desired = deepcopy(base)
        for ordinal in range(start, min(start + 4, len(type_matrix))):
            name = f'TYPE_DDN_{ordinal}'; identity = 'function:' + name
            row = deepcopy(base['rows'][f'function:SOURCE_TYPE_{ordinal}'])
            row.update(resource_id=identity, name=name, path=[name])
            row['native'] = {key: value for key, value in row['native'].items() if key in FIELDS | {'deterministic'}}
            desired['rows'][identity] = row
        expect_commit(application(base, desired))
        for ordinal in range(start, min(start + 4, len(type_matrix))):
            assert fresh(f'SELECT TYPE_DDN_{ordinal}(NULL) FROM RDB$DATABASE') == [(None,)]
    base = snapshot(); desired = deepcopy(base)
    for name, other in [('CYCLE_A', 'CYCLE_B'), ('CYCLE_B', 'CYCLE_A')]:
        row = deepcopy(base['rows']['function:SOURCE_TYPE_1']); identity = 'function:' + name
        row.update(resource_id=identity, name=name, path=[name])
        row['native'] = {key: value for key, value in row['native'].items() if key in FIELDS | {'deterministic'}}
        row['native'].update(metadata_source='BEGIN IF (A > 0) THEN RETURN ' + other + '(A - 1) + 1; RETURN 0; END',
                             creation_dependencies=['function:' + other])
        desired['rows'][identity] = row
    expect_commit(application(base, desired))
    assert fresh('SELECT CYCLE_A(3), CYCLE_B(4) FROM RDB$DATABASE') == [(3, 4)]
    # A later body failure must remove all newly staged signatures.
    base = snapshot(); desired = deepcopy(base)
    for name, other in [('BAD_A', 'BAD_B'), ('BAD_B', 'BAD_A')]:
        row = deepcopy(base['rows']['function:SOURCE_TYPE_1']); identity = 'function:' + name
        row.update(resource_id=identity, name=name, path=[name])
        row['native'] = {key: value for key, value in row['native'].items() if key in FIELDS | {'deterministic'}}
        row['native'].update(metadata_source='BEGIN RETURN ' + (other + '(A)' if name == 'BAD_A' else 'UNKNOWN_FUNCTION(A)') + '; END',
                             creation_dependencies=['function:' + other])
        desired['rows'][identity] = row
    refused = application(base, desired)
    assert refused['native_rollback_returned'] and not refused['native_commit_returned'], refused
    assert not {'function:BAD_A', 'function:BAD_B'} & snapshot()['rows'].keys()
    # Test the actual intermediate signature without making it durable.
    from pgadmin.cdeadmin.workspace.firebird_routine_plan import model
    from pgadmin.cdeadmin.workspace.firebird_routine_stages import parts
    temporary = {**model(base['rows']['function:SOURCE_TYPE_1']), 'name': 'INCOMPLETE_TEST'}
    primary, _ = parts('function', temporary)
    sql(primary[0])
    try:
        sql('SELECT INCOMPLETE_TEST(1) FROM RDB$DATABASE')
    except Exception as error:
        assert 335544844 in getattr(error, 'gds_codes', ()), (type(error), getattr(error, 'gds_codes', ()))
    else:
        raise AssertionError('An incomplete signature returned fabricated output')
    connection.rollback()
    # A signature may depend on a domain created in this same saved review.
    # Exercise receipt reduction, ordering and post-commit native rediscovery.
    from pgadmin.cdeadmin.workspace.firebird_domain_plan import FIELDS as DOMAIN_FIELDS, TYPE_FIELDS
    base = snapshot(); desired = deepcopy(base)
    domain = deepcopy(base['rows']['domain:ROUTINE_DOMAIN'])
    domain.update(resource_id='domain:NEW_SIGNATURE_DOMAIN', name='NEW_SIGNATURE_DOMAIN',
                  path=['NEW_SIGNATURE_DOMAIN'])
    domain['native'] = {key: value for key, value in domain['native'].items()
                        if key in DOMAIN_FIELDS | TYPE_FIELDS}
    desired['rows'][domain['resource_id']] = domain
    routine = deepcopy(base['rows']['procedure:SOURCE_P'])
    routine.update(resource_id='procedure:PROJECTED_P', name='PROJECTED_P', path=['PROJECTED_P'])
    routine['native'] = {key: value for key, value in routine['native'].items() if key in FIELDS}
    routine['native']['parameters'][0]['domain'] = 'NEW_SIGNATURE_DOMAIN'
    desired['rows'][routine['resource_id']] = routine
    expect_commit(application(base, desired))
    assert fresh('SELECT R FROM PROJECTED_P(9)') == [(10,)]
    return {'durable_review_native_commit': True, 'signature_and_body_rediscovery': True,
            'new_domain_and_dependent_routine_one_review': True,
            'type_of_domain_and_column': True, 'numeric_character_and_int128': True,
            'default_and_parameter_comment_changed': True, 'grants_preserved': True,
            'multi_routine_failure_rolls_back_all': True, 'fresh_attachment_execution': True,
            'native_scalar_signature_matrix': len(type_matrix), 'mutual_routine_cycle': True,
            'failed_cycle_body_rolls_back_all_signatures': True, 'intermediate_signature_refuses_calls': True}
