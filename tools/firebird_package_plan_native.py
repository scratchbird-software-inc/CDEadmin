"""Package creation/replacement through persisted reviews and fresh attachments."""
from copy import deepcopy


def qualify(connection, provider, route, root):
    from pgadmin.cdeadmin.providers.firebird.schema_application import capture, apply_review
    from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan, digest
    from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications
    target = {'endpoint_id': 'owned', 'database_target_id': 'owned', 'generation': 'package-native'}
    store = SchemaApplications(root / 'package-receipts.json')
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
        result = SchemaApplications(store.path).apply({'review_id': reviewed['review_id'],
            'review_digest': reviewed['review_digest'], 'confirmed': True}, 'owned', 'owned',
            lambda record: apply_review(provider, route, record))
        return result['outcome']
    def expect_commit(outcome):
        assert outcome['native_commit_returned'] and outcome['attachment_released'], outcome
        assert outcome['rediscovery']['available'], outcome
        assert all(item['matches_reviewed_properties'] for item in outcome['rediscovery']['objects']), outcome
    def fresh_value():
        owned = provider.client._connect({'route': route})
        try:
            with owned.cursor() as cursor:
                cursor.execute('SELECT A_PKG.F() FROM RDB$DATABASE')
                return cursor.fetchone()[0]
        finally:
            if owned.main_transaction.is_active():
                owned.rollback()
            provider.client._release_attachment(owned)
    base = snapshot(); desired = deepcopy(base)
    header = 'BEGIN FUNCTION F RETURNS INTEGER; END'
    for name, body in [('A_PKG', 'BEGIN FUNCTION F RETURNS INTEGER AS BEGIN RETURN Z_PKG.F(); END END'),
                       ('Z_PKG', 'BEGIN FUNCTION F RETURNS INTEGER AS BEGIN RETURN 7; END END')]:
        identity = 'package:' + name
        desired['rows'][identity] = {'resource_id': identity, 'kind': 'package', 'path': [name],
            'name': name, 'system': 'false', 'native': {'header_source': header, 'body_source': body,
            'sql_security': None, 'description': 'owned native package'}}
    expect_commit(application(base, desired))
    assert fresh_value() == 7
    with connection.cursor() as cursor:
        cursor.execute('CREATE ROLE PACKAGE_READER')
        cursor.execute('GRANT EXECUTE ON PACKAGE A_PKG TO ROLE PACKAGE_READER')
    connection.commit()
    base = snapshot(); desired = deepcopy(base)
    desired['rows']['package:A_PKG']['native'].update(sql_security=False,
        body_source='BEGIN FUNCTION F RETURNS INTEGER AS BEGIN RETURN Z_PKG.F() + 2; END END')
    expect_commit(application(base, desired))
    assert fresh_value() == 9
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM RDB$USER_PRIVILEGES WHERE RDB$RELATION_NAME='A_PKG' AND RDB$USER='PACKAGE_READER' AND RDB$PRIVILEGE='X'")
        assert cursor.fetchone()[0] == 1
    connection.rollback()
    base = snapshot(); desired = deepcopy(base)
    desired['rows']['package:A_PKG']['native'].update(sql_security=True,
        body_source='BEGIN FUNCTION F RETURNS INTEGER AS BEGIN RETURN UNKNOWN_FUNCTION(); END END')
    refused = application(base, desired)
    assert refused['native_rollback_returned'] and not refused['native_commit_returned'], refused
    assert snapshot()['rows']['package:A_PKG']['native']['sql_security'] == base['rows']['package:A_PKG']['native']['sql_security']
    assert fresh_value() == 9
    base = snapshot(); desired = deepcopy(base)
    body = desired['rows']['package:A_PKG']['native']['body_source']
    desired['rows']['package:A_PKG']['native']['body_source'] = None
    expect_commit(application(base, desired))
    assert snapshot()['rows']['package:A_PKG']['native']['body_source'] is None
    base = snapshot(); desired = deepcopy(base)
    desired['rows']['package:A_PKG']['native']['body_source'] = body
    expect_commit(application(base, desired))
    assert fresh_value() == 9
    return {'durable_reviews': True, 'headers_precede_bodies': True,
            'native_rediscovery': True, 'grants_preserved': True,
            'body_failure_rolls_back_header': True, 'explicit_body_drop_and_restore': True,
            'fresh_attachment_execution': True}
