"""Qualify structured DDN privilege changes against native Firebird catalogs."""
from copy import deepcopy
import json
from pgadmin.cdeadmin.providers.firebird.identity import catalog_resource_id
from pgadmin.cdeadmin.providers.firebird.schema_application import capture, apply_review
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan, digest
from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications
from pgadmin.cdeadmin.workspace.firebird_privilege_plan import FIELDS


def qualify(connection, provider, route, root):
    statements = ['CREATE TABLE DDN_GRANTS (ID INTEGER)', 'CREATE SEQUENCE DDN_SEQUENCE',
        'CREATE ROLE DDN_ROLE', 'CREATE PROCEDURE DDN_PROC AS BEGIN END',
        'GRANT SELECT ON DDN_GRANTS TO USER DDN_SOURCE WITH GRANT OPTION',
        'GRANT UPDATE (ID) ON DDN_GRANTS TO USER DDN_SOURCE',
        'GRANT EXECUTE ON PROCEDURE DDN_PROC TO USER DDN_SOURCE',
        'GRANT USAGE ON SEQUENCE DDN_SEQUENCE TO USER DDN_SOURCE',
        'GRANT CREATE TABLE TO USER DDN_SOURCE',
        'GRANT ALTER DATABASE TO USER DDN_SOURCE',
        'GRANT DEFAULT DDN_ROLE TO USER DDN_SOURCE WITH ADMIN OPTION']
    for statement in statements:
        connection.execute_immediate(statement)
    connection.commit()
    target = {'endpoint_id': 'owned', 'database_target_id': 'owned', 'generation': 'grant-plan'}
    def snapshot():
        if connection.main_transaction.is_active(): connection.rollback()
        value = capture(connection, target); connection.rollback(); return value
    store = SchemaApplications(root / 'grant-plan-receipts.json')
    def apply(base, desired):
        desired['sha256'] = digest(desired['rows'])
        plan = build_plan(base, desired, base)
        (root / 'grant-last-plan.json').write_text(json.dumps(plan, indent=2))
        assert plan['status'] == 'review-ready', plan['blockers']
        review = store.review(plan, base, desired, 'owner', 'binding', route['database'])
        result = store.apply({'review_id': review['review_id'], 'review_digest': review['review_digest'],
            'confirmed': True}, 'owner', 'binding', lambda record: apply_review(provider, route, record))['outcome']
        assert result['native_commit_returned'] and result['attachment_released'], result
        assert result['rediscovery']['available'] and all(item['matches_reviewed_properties']
            for item in result['rediscovery']['objects']), result
        return result
    base = snapshot(); desired = deepcopy(base); identities = []
    for original in base['rows'].values():
        if original['kind'] != 'privilege' or original['native'].get('grantee') != 'DDN_SOURCE': continue
        row = deepcopy(original); row['native']['grantee'] = 'DDN_TARGET'
        row['name'] = row['name'].replace('DDN_SOURCE', 'DDN_TARGET'); row['path'] = [row['name']]
        values = [row['native'][key] if key != 'field' else row['native'][key] or '' for key in FIELDS]
        row['resource_id'] = catalog_resource_id('privilege', [], json.dumps(values, ensure_ascii=False, separators=(',', ':')))
        row['native']['grant_change'] = {'operation': 'grant', 'confirmation': 'DDN_TARGET', 'allow_cascade': False}
        desired['rows'][row['resource_id']] = row; identities.append(row['resource_id'])
    assert len(identities) == 7
    apply(base, desired)
    granted = snapshot()
    assert all(identity in granted['rows'] for identity in identities)
    revoke = deepcopy(granted)
    for identity in identities:
        revoke['rows'][identity]['native']['grant_change'] = {
            'operation': 'revoke', 'confirmation': 'DDN_TARGET', 'allow_cascade': True}
    apply(granted, revoke)
    final = snapshot()
    assert all(identity not in final['rows'] for identity in identities)
    assert sum(row['kind'] == 'privilege' and row['native'].get('grantee') == 'DDN_SOURCE'
               for row in final['rows'].values()) == 7
    return {'grant_identities_roundtripped': len(identities), 'exact_native_revocation': True,
            'column_membership_default_admin_class_and_database_grants': True,
            'unrelated_grants_preserved': True, 'native_rediscovery_matches': True}
