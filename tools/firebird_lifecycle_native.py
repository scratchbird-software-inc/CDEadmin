"""Qualify native identity preservation through durable DDN schema reviews."""
from copy import deepcopy


def qualify(connection, provider, route, root):
    from pgadmin.cdeadmin.providers.firebird.schema_application import capture, apply_review
    from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan, digest
    from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications
    target = {'endpoint_id': 'owned', 'database_target_id': 'owned', 'generation': 'lifecycle'}
    store = SchemaApplications(root / 'lifecycle-receipts.json')
    def sql(source):
        with connection.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []
    def snapshot():
        if connection.main_transaction.is_active(): connection.rollback()
        result = capture(connection, target)
        connection.rollback()
        return result
    def lifecycle(base, requests, operation='rename'):
        desired = deepcopy(base)
        for identity, name in requests:
            row = desired['rows'][identity]
            row['native']['lifecycle'] = {'operation': operation, 'confirmation': row['name']}
            if operation == 'rename': row['native']['lifecycle']['new_name'] = name
            elif operation in {'type', 'bind_domain'}: row['native'].update(name)
        desired['sha256'] = digest(desired['rows'])
        plan = build_plan(base, desired, base)
        assert plan['status'] == 'review-ready', plan['blockers']
        review = store.review(plan, base, desired, 'owner', 'binding', route['database'])
        return store.apply({'review_id': review['review_id'], 'review_digest': review['review_digest'],
            'confirmed': True}, 'owner', 'binding', lambda record: apply_review(provider, route, record))['outcome']
    sql('CREATE DOMAIN D_OLD AS INTEGER CHECK (VALUE >= 0)')
    sql('CREATE TABLE T (C_OLD D_OLD, BLOCKED INT)')
    sql('CREATE ROLE R_RENAME')
    sql('GRANT UPDATE (C_OLD) ON T TO R_RENAME')
    sql('GRANT UPDATE (C_OLD) ON T TO USER RENAME_PARENT WITH GRANT OPTION')
    sql('GRANT UPDATE (C_OLD) ON T TO USER RENAME_CHILD GRANTED BY USER RENAME_PARENT')
    sql("COMMENT ON COLUMN T.C_OLD IS 'retained column'")
    sql("COMMENT ON DOMAIN D_OLD IS 'retained domain'")
    connection.commit()
    sql('INSERT INTO T VALUES (7, 8)')
    sql('CREATE VIEW V_BLOCK AS SELECT BLOCKED FROM T')
    connection.commit()
    result = lifecycle(snapshot(), [('column:T:C_OLD', 'C_NEW'), ('domain:D_OLD', 'D_NEW')])
    assert result['native_commit_returned'] and result['attachment_released'], result
    assert len(result['identity_transitions']) == 2, result
    assert all(row['native_identity_verified'] for row in result['identity_transitions']), result
    assert result['rediscovery']['available'] and all(
        row['matches_reviewed_properties'] for row in result['rediscovery']['objects']), result
    assert sql('SELECT C_NEW FROM T') == [(7,)]
    assert sql("SELECT TRIM(RDB$FIELD_SOURCE) FROM RDB$RELATION_FIELDS WHERE RDB$RELATION_NAME='T' AND RDB$FIELD_NAME='C_NEW'") == [('D_NEW',)]
    grants = sql("SELECT TRIM(RDB$FIELD_NAME) FROM RDB$USER_PRIVILEGES WHERE RDB$USER='R_RENAME' AND RDB$RELATION_NAME='T'")
    assert grants == [('C_NEW',)], grants
    grants = sql("SELECT TRIM(RDB$USER), TRIM(RDB$GRANTOR), RDB$GRANT_OPTION, TRIM(RDB$FIELD_NAME) FROM RDB$USER_PRIVILEGES WHERE RDB$USER IN ('RENAME_PARENT','RENAME_CHILD') AND RDB$RELATION_NAME='T' ORDER BY 1")
    assert grants == [('RENAME_CHILD', 'RENAME_PARENT', 0, 'C_NEW'), ('RENAME_PARENT', 'SYSDBA', 1, 'C_NEW')], grants
    connection.rollback()
    # A dependency refusal in the second rename rolls back the first rename.
    sql('CREATE DOMAIN A_FIRST AS INTEGER'); connection.commit()
    result = lifecycle(snapshot(), [('domain:A_FIRST', 'A_CHANGED'), ('column:T:BLOCKED', 'NO_CHANGE')])
    assert result['native_rollback_returned'] and not result['native_commit_returned'], result
    live = snapshot()['rows']
    assert 'domain:A_FIRST' in live and 'domain:A_CHANGED' not in live
    assert 'column:T:BLOCKED' in live and 'column:T:NO_CHANGE' not in live
    assert sql('SELECT BLOCKED FROM V_BLOCK') == [(8,)]
    connection.rollback()
    sql('CREATE DOMAIN DROP_D AS INTEGER')
    sql('CREATE TABLE DROP_T (C DROP_D)')
    connection.commit()
    sql('CREATE VIEW DROP_V AS SELECT C FROM DROP_T')
    sql('CREATE SEQUENCE DROP_S')
    sql("CREATE EXCEPTION DROP_E 'explicit removal'")
    sql('CREATE PACKAGE DROP_P AS BEGIN FUNCTION F RETURNS INTEGER; END')
    sql('CREATE PACKAGE BODY DROP_P AS BEGIN FUNCTION F RETURNS INTEGER AS BEGIN RETURN 1; END END')
    connection.commit()
    identities = ['domain:DROP_D', 'table:DROP_T', 'view:DROP_V', 'sequence:DROP_S', 'exception:DROP_E', 'package:DROP_P']
    result = lifecycle(snapshot(), [(item, None) for item in identities], 'drop')
    assert result['native_commit_returned'] and result['attachment_released'], result
    assert result['rediscovery']['available'] and all(row['matches_reviewed_properties'] for row in result['rediscovery']['objects']), result
    assert not set(identities) & snapshot()['rows'].keys()
    result = lifecycle(snapshot(), [('domain:A_FIRST', None), ('table:T', None)], 'drop')
    assert result['native_rollback_returned'] and not result['native_commit_returned'], result
    assert 'domain:A_FIRST' in snapshot()['rows']
    assert sql('SELECT C_NEW FROM T') == [(7,)]
    connection.rollback()
    sql('CREATE TABLE REMOVE_CHILDREN (I INTEGER, J INTEGER, CONSTRAINT REMOVE_CHECK CHECK (I > 0))')
    sql('CREATE INDEX REMOVE_INDEX ON REMOVE_CHILDREN (I)')
    sql('CREATE TRIGGER REMOVE_TRIGGER FOR REMOVE_CHILDREN BEFORE INSERT AS BEGIN NEW.I = 1; END')
    sql('CREATE TABLE REMOVE_A (ID INTEGER PRIMARY KEY, B INTEGER)')
    sql('CREATE TABLE REMOVE_B (ID INTEGER PRIMARY KEY, A INTEGER)')
    connection.commit()
    sql('ALTER TABLE REMOVE_A ADD CONSTRAINT REMOVE_A_FK FOREIGN KEY (B) REFERENCES REMOVE_B(ID)')
    sql('ALTER TABLE REMOVE_B ADD CONSTRAINT REMOVE_B_FK FOREIGN KEY (A) REFERENCES REMOVE_A(ID)')
    connection.commit()
    identities = ['column:REMOVE_CHILDREN:J', 'index:REMOVE_CHILDREN:REMOVE_INDEX',
        'constraint:REMOVE_CHILDREN:REMOVE_CHECK', 'trigger:REMOVE_TRIGGER',
        'constraint:REMOVE_A:REMOVE_A_FK', 'constraint:REMOVE_B:REMOVE_B_FK',
        'table:REMOVE_A', 'table:REMOVE_B']
    result = lifecycle(snapshot(), [(item, None) for item in identities], 'drop')
    assert result['native_commit_returned'] and result['attachment_released'], result
    assert result['rediscovery']['available'] and all(row['matches_reviewed_properties'] for row in result['rediscovery']['objects']), result
    live = snapshot()['rows']
    assert not set(identities) & live.keys()
    assert 'table:REMOVE_CHILDREN' in live and 'column:REMOVE_CHILDREN:I' in live
    result = lifecycle(snapshot(), [('domain:D_NEW', {'field_type': 16, 'field_length': 8})], 'type')
    assert result['native_commit_returned'] and result['attachment_released'], result
    assert result['rediscovery']['available'] and all(row['matches_reviewed_properties'] for row in result['rediscovery']['objects']), result
    assert sql('SELECT C_NEW FROM T') == [(7,)]
    connection.rollback()
    sql('CREATE DOMAIN Z_LONG AS VARCHAR(20) CHARACTER SET UTF8 COLLATE UNICODE_CI')
    sql('CREATE TABLE TYPE_TEXT (V Z_LONG)')
    connection.commit()
    sql("INSERT INTO TYPE_TEXT VALUES ('long native value')"); connection.commit()
    base = snapshot()
    utf8 = base['rows']['character-set:UTF8']['native']['default_collation']
    result = lifecycle(base, [('domain:Z_LONG', {'character_length': 30, 'field_length': 120, 'collation': utf8})], 'type')
    assert result['native_commit_returned'] and result['attachment_released'], result
    assert result['rediscovery']['available'] and all(row['matches_reviewed_properties'] for row in result['rediscovery']['objects']), result
    assert sql('SELECT V FROM TYPE_TEXT') == [('long native value',)]
    connection.rollback()
    result = lifecycle(snapshot(), [('domain:A_FIRST', {'field_type': 16, 'field_length': 8}),
        ('domain:Z_LONG', {'character_length': 2, 'field_length': 8})], 'type')
    assert result['native_rollback_returned'] and not result['native_commit_returned'], result
    live = snapshot()['rows']
    assert str(live['domain:A_FIRST']['native']['field_type']) == '8'
    assert str(live['domain:Z_LONG']['native']['character_length']) == '30'
    sql('CREATE DOMAIN BIND_NEW AS BIGINT CHECK (VALUE > 0)')
    sql('CREATE DOMAIN BIND_INT AS INTEGER')
    sql('CREATE TABLE ZZ_BIND_FAILURE (V VARCHAR(20))'); connection.commit()
    sql("INSERT INTO ZZ_BIND_FAILURE VALUES ('not a number')"); connection.commit()
    from pgadmin.cdeadmin.workspace.firebird_domain_plan import TYPE_FIELDS
    def binding(base, domain):
        facts = base['rows']['domain:' + domain]['native']
        return {**{key: facts.get(key) for key in TYPE_FIELDS}, 'domain': domain,
                'domain_not_null': facts.get('not_null')}
    identity_before = sql("SELECT RDB$FIELD_ID FROM RDB$RELATION_FIELDS WHERE RDB$RELATION_NAME='T' AND RDB$FIELD_NAME='C_NEW'")
    base = snapshot()
    result = lifecycle(base, [('column:T:C_NEW', binding(base, 'BIND_NEW'))], 'bind_domain')
    assert result['native_commit_returned'] and result['attachment_released'], result
    assert result['rediscovery']['available'] and all(row['matches_reviewed_properties'] for row in result['rediscovery']['objects']), result
    assert sql("SELECT RDB$FIELD_ID FROM RDB$RELATION_FIELDS WHERE RDB$RELATION_NAME='T' AND RDB$FIELD_NAME='C_NEW'") == identity_before
    assert sql('SELECT C_NEW FROM T') == [(7,)]
    connection.rollback()
    base = snapshot()
    result = lifecycle(base, [('column:T:C_NEW', binding(base, 'D_NEW')),
        ('column:ZZ_BIND_FAILURE:V', binding(base, 'BIND_INT'))], 'bind_domain')
    assert result['native_rollback_returned'] and not result['native_commit_returned'], result
    live = snapshot()['rows']
    assert result['statements_completed'] >= 1, result
    assert live['column:T:C_NEW']['native']['domain'] == 'BIND_NEW'
    base = snapshot(); desired = deepcopy(base)
    desired['rows']['collation:REMOVE_COLL'] = {'resource_id': 'collation:REMOVE_COLL',
        'kind': 'collation', 'name': 'REMOVE_COLL', 'path': ['REMOVE_COLL'], 'system': 'false',
        'native': {'character_set': 'UTF8', 'base_collation': 'UNICODE', 'attributes': 3,
                   'specific_attributes': 'NUMERIC-SORT=1', 'description': 'native collation'}}
    def collation_application(base, desired):
        desired['sha256'] = digest(desired['rows'])
        plan = build_plan(base, desired, base)
        if plan['status'] != 'review-ready':
            import json
            (root / 'collation-plan-blockers.json').write_text(json.dumps(plan['blockers'], indent=2))
        assert plan['status'] == 'review-ready', plan['blockers']
        review = store.review(plan, base, desired, 'owner', 'binding', route['database'])
        outcome = store.apply({'review_id': review['review_id'], 'review_digest': review['review_digest'],
            'confirmed': True}, 'owner', 'binding', lambda record: apply_review(provider, route, record))['outcome']
        assert outcome['native_commit_returned'] and outcome['attachment_released'], outcome
        assert outcome['rediscovery']['available'] and all(row['matches_reviewed_properties'] for row in outcome['rediscovery']['objects']), outcome
    collation_application(base, desired)
    base = snapshot(); desired = deepcopy(base)
    desired['rows']['collation:REMOVE_COLL']['native']['description'] = 'changed collation comment'
    collation_application(base, desired)

    # One review creates a new collation, its domain, and a dependent table.
    base = snapshot(); desired = deepcopy(base)
    desired['rows']['collation:CHAIN_COLL'] = {
        **deepcopy(base['rows']['collation:REMOVE_COLL']),
        'resource_id': 'collation:CHAIN_COLL', 'name': 'CHAIN_COLL', 'path': ['CHAIN_COLL']}
    desired['rows']['collation:CHAIN_COLL']['native'].update(
        specific_attributes='NUMERIC-SORT=1', description=None)
    for field in ('owner', 'privileges'):
        desired['rows']['collation:CHAIN_COLL']['native'].pop(field, None)
    facts = {'field_type': 37, 'field_sub_type': 0, 'field_scale': 0,
        'character_length': 12, 'field_length': 48, 'dimensions': 0,
        'character_set': 'UTF8', 'collation': 'CHAIN_COLL'}
    desired['rows']['domain:CHAIN_DOMAIN'] = {
        'resource_id': 'domain:CHAIN_DOMAIN', 'kind': 'domain', 'name': 'CHAIN_DOMAIN',
        'path': ['CHAIN_DOMAIN'], 'system': 'false', 'native': {**facts,
        'not_null': 0, 'default_source': None, 'validation_source': None}}
    desired['rows']['table:CHAIN_TABLE'] = {
        'resource_id': 'table:CHAIN_TABLE', 'kind': 'table', 'name': 'CHAIN_TABLE',
        'path': ['CHAIN_TABLE'], 'system': 'false', 'native': {
        'relation_type': 0, 'sql_security': None, 'publication_enabled': False,
        'columns': [{**facts, 'name': 'V', 'position': 0, 'domain': 'CHAIN_DOMAIN',
                     'domain_not_null': 0}]}}
    collation_application(base, desired)
    sql("INSERT INTO CHAIN_TABLE VALUES ('item10')")
    sql("INSERT INTO CHAIN_TABLE VALUES ('item2')")
    assert sql('SELECT V FROM CHAIN_TABLE ORDER BY V') == [('item2',), ('item10',)]
    connection.rollback()
    result = lifecycle(snapshot(), [(identity, None) for identity in (
        'collation:CHAIN_COLL', 'domain:CHAIN_DOMAIN', 'table:CHAIN_TABLE')], 'drop')
    assert result['native_commit_returned'], result

    sql("DECLARE EXTERNAL FUNCTION REMOVE_UDF INTEGER RETURNS INTEGER BY VALUE ENTRY_POINT 'abs' MODULE_NAME 'ib_udf'")
    connection.commit()
    result = lifecycle(snapshot(), [('collation:REMOVE_COLL', None), ('external-function:REMOVE_UDF', None)], 'drop')
    assert result['native_commit_returned'] and result['attachment_released'], result
    assert result['rediscovery']['available'] and all(row['matches_reviewed_properties'] for row in result['rediscovery']['objects']), result
    return {'collation_domain_table_creation_order_and_native_sort': True,
            'collation_creation_and_comment_rediscovered': True, 'column_and_domain_native_identity_preserved': True, 'saved_review_replayed': True,
            'data_comments_and_column_grants_preserved': True, 'domain_references_follow_native_identity': True,
            'column_grant_chain_and_grant_options_preserved': True,
            'compound_drop_dependency_order_and_absence': True, 'failed_drop_restores_prior_removals': True,
            'explicit_child_removals_and_foreign_key_cycle_break': True,
            'domain_type_widening_and_explicit_collation_effect': True,
            'domain_conversion_failure_rolls_back_prior_conversion': True,
            'column_domain_rebinding_identity_data_and_rollback': True,
            'native_collation_and_legacy_declaration_removal': True,
            'native_dependency_refusal_rolls_back_all': True}
