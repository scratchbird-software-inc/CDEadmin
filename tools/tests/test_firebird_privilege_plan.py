"""Explicit security changes retain full native identities and confirmations."""
from copy import deepcopy
import json
import pytest
from tools.tests.test_firebird_schema_plan import document, obj
from pgadmin.cdeadmin.providers.firebird.identity import catalog_resource_id
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan
from pgadmin.cdeadmin.workspace.firebird_privilege_plan import FIELDS


def grant(**changes):
    native = {'grantee': 'R', 'object_name': 'T', 'field': None, 'privilege': 'S',
        'grantor': 'SYSDBA', 'grant_option': 0, 'user_type': 13, 'object_type': 0, 'default_role': False, **changes}
    identity = [native[key] if key != 'field' else native[key] or '' for key in FIELDS]
    row = obj('privilege', 'R grant', **native)
    row['resource_id'] = catalog_resource_id('privilege', [], json.dumps(identity, ensure_ascii=False, separators=(',', ':')))
    return row


def catalog(*rows):
    value = document([obj('table', 'T'), obj('role', 'R', system_privileges=[]), *rows])
    value['rows']['database:database']['native']['catalog_observations'] = [
        {'section': 'object privileges', 'available': True}]
    return value


def desired_grant(base, row, operation='grant', cascade=False):
    desired = deepcopy(base)
    converted = catalog(row)['rows'][row['resource_id']]
    converted['native']['grant_change'] = {'operation': operation, 'confirmation': row['extensions']['firebird']['native']['grantee'], 'allow_cascade': cascade}
    desired['rows'][row['resource_id']] = converted
    return desired


def test_create_and_revoke_native_grant_with_exact_postconditions():
    base, row = catalog(), grant()
    plan = build_plan(base, desired_grant(base, row), base)
    assert plan['status'] == 'review-ready', plan['blockers']
    operation = plan['operations'][0]
    assert operation['statements'] == ['GRANT SELECT ON TABLE "T" TO ROLE "R" GRANTED BY USER "SYSDBA"']
    assert operation['after']['grantor'] == 'SYSDBA'
    base = catalog(row)
    revoked = build_plan(base, desired_grant(base, row, 'revoke'), base)
    assert revoked['status'] == 'review-ready', revoked['blockers']
    assert revoked['operations'][0]['after'] is None
    assert revoked['operations'][0]['statements'] == ['REVOKE SELECT ON TABLE "T" FROM ROLE "R" GRANTED BY USER "SYSDBA"']


def test_omission_and_option_changes_never_silently_revoke():
    row = grant(); base = catalog(row)
    assert build_plan(base, catalog(), base)['status'] == 'blocked'
    changed = desired_grant(base, row)
    changed['rows'][row['resource_id']]['native']['grant_option'] = 1
    assert build_plan(base, changed, base)['status'] == 'blocked'
    option = grant(grant_option=1)
    assert build_plan(base, desired_grant(base, option), base)['status'] == 'blocked'


def test_cascade_acknowledgement_and_native_drift_are_required():
    row = grant(grant_option=1); base = catalog(row)
    assert build_plan(base, desired_grant(base, row, 'revoke'), base)['status'] == 'blocked'
    desired = desired_grant(base, row, 'revoke', True)
    assert build_plan(base, desired, base)['status'] == 'review-ready'
    live = deepcopy(base); del live['rows'][row['resource_id']]
    assert build_plan(base, desired, live)['status'] == 'blocked'


@pytest.mark.parametrize('changes', [
    {'grant_option': True}, {'user_type': True}, {'object_name': 'UNKNOWN'},
    {'object_type': 22, 'object_name': 'spoofed', 'privilege': 'C'},
    {'default_role': True}, {'unrecognized': 'ignored?'}])
def test_invalid_or_unobserved_native_facts_block(changes):
    base = catalog(); row = grant(**changes)
    assert build_plan(base, desired_grant(base, row), base)['status'] == 'blocked'


def test_default_membership_and_database_class_syntax():
    for row, expected in [
        (grant(privilege='M', object_type=13, object_name='R', grantee='BOB', user_type=8, default_role=True, grant_option=2), 'GRANT DEFAULT "R" TO USER "BOB" WITH ADMIN OPTION'),
        (grant(privilege='C', object_type=22, object_name='SQL$TABLES'), 'GRANT CREATE TABLE TO ROLE "R"'),
        (grant(privilege='L', object_type=21, object_name='SQL$DATABASE'), 'GRANT ALTER DATABASE TO ROLE "R"')]:
        base = catalog(); plan = build_plan(base, desired_grant(base, row), base)
        assert plan['status'] == 'review-ready', plan['blockers']
        assert plan['operations'][0]['statements'][0].startswith(expected)


def test_privilege_catalog_and_separate_structural_review_required():
    base = catalog(); row = grant(); desired = desired_grant(base, row)
    hidden = deepcopy(base); hidden['rows']['database:database']['native']['catalog_observations'] = []
    assert build_plan(base, desired, hidden)['status'] == 'blocked'
    extra = document([obj('exception', 'E', message='message')])['rows']['exception:E']
    desired['rows']['exception:E'] = extra
    assert build_plan(base, desired, base)['status'] == 'blocked'


def test_review_retains_explicit_intent_and_does_not_guard_volatile_database_counters(tmp_path):
    from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications
    base = catalog(); desired = desired_grant(base, grant())
    for value in (base, desired):
        value['rows']['database:database']['native'].update(guid='guid', file_id='file')
    plan = build_plan(base, desired, base)
    store = SchemaApplications(tmp_path / 'grants.json')
    review = store.review(plan, base, desired, 1, 'binding', 'db.fdb')
    observed = []
    def execute(record):
        current = deepcopy(base)
        current['rows']['database:database']['native'].update(next_transaction=999, fetches=1000)
        rebuilt = build_plan(record['baseline'], record['desired'], current)
        observed.append(rebuilt['execution_sha256'] == plan['execution_sha256'])
        return {'state': 'not_executed'}
    store.apply({'review_id': review['review_id'], 'review_digest': review['review_digest'], 'confirmed': True},
                1, 'binding', execute)
    assert observed == [True]
