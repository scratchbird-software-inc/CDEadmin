"""Native view-plan application and grant preservation evidence."""
from copy import deepcopy


def qualify(connection, provider, route):
    from pgadmin.cdeadmin.providers.firebird.schema_application import capture, apply_review
    from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan, digest
    from pgadmin.cdeadmin.providers.firebird.identity import catalog_resource_id
    target = {'endpoint_id': 'owned', 'database_target_id': 'owned', 'generation': 'view-native'}
    identity = catalog_resource_id('view', [], 'VIEW_PLAN_NATIVE')
    def snapshot():
        if connection.main_transaction.is_active():
            connection.rollback()
        value = capture(connection, target)
        connection.rollback()
        return value
    def apply(base, desired):
        desired['sha256'] = digest(desired['rows'])
        plan = build_plan(base, desired, base)
        assert plan['status'] == 'review-ready', plan['blockers']
        return apply_review(provider, route, {'plan': plan, 'baseline': base, 'desired': desired})
    base = snapshot()
    desired = deepcopy(base)
    desired['rows'][identity] = {'resource_id': identity, 'kind': 'view', 'name': 'VIEW_PLAN_NATIVE',
        'path': ['VIEW_PLAN_NATIVE'], 'system': 'false', 'native': {'relation_type': 1,
        'definition': 'SELECT 1 FROM RDB$DATABASE', 'columns': [{'name': 'Exact"Name', 'position': 0}],
        'description': 'Created from DDN'}}
    created = apply(base, desired)
    assert created['native_commit_returned'], created
    assert all(item['matches_reviewed_properties'] for item in created['rediscovery']['objects']), created
    with connection.cursor() as cursor:
        cursor.execute('GRANT SELECT ON VIEW_PLAN_NATIVE TO PUBLIC')
    connection.commit()
    base = snapshot(); desired = deepcopy(base)
    desired['rows'][identity]['native']['definition'] = 'SELECT 42 FROM RDB$DATABASE'
    desired['rows'][identity]['native']['description'] = 'Changed from DDN'
    changed = apply(base, desired)
    assert changed['native_commit_returned'], changed
    assert all(item['matches_reviewed_properties'] for item in changed['rediscovery']['objects']), changed
    with connection.cursor() as cursor:
        cursor.execute('SELECT "Exact""Name" FROM VIEW_PLAN_NATIVE')
        assert cursor.fetchone() == (42,)
        cursor.execute("SELECT COUNT(*) FROM RDB$USER_PRIVILEGES WHERE RDB$RELATION_NAME = 'VIEW_PLAN_NATIVE' AND RDB$USER = 'PUBLIC' AND RDB$PRIVILEGE = 'S'")
        assert cursor.fetchone()[0] == 1
    connection.rollback()
    base = snapshot(); desired = deepcopy(base)
    desired['rows'][identity]['native']['definition'] = 'SELECT MISSING_FIELD FROM RDB$DATABASE'
    refused = apply(base, desired)
    assert refused['native_rollback_returned'] and not refused['native_commit_returned'], refused
    with connection.cursor() as cursor:
        cursor.execute('SELECT "Exact""Name" FROM VIEW_PLAN_NATIVE')
        assert cursor.fetchone() == (42,)
    connection.rollback()
    return {'passed': True, 'create': created, 'alter': changed, 'native_failure': refused,
            'grant_preserved': True, 'original_query_preserved_on_failure': True}
