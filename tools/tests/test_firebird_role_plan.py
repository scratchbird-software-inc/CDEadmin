"""Native role privilege sets, governance boundaries and three-way planning."""
from copy import deepcopy

import pytest

from tools.tests.test_firebird_schema_plan import document, obj
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan


def role(name='R', **native):
    return obj('role', name, **{'system_privileges': [], 'description': None, **native})


def catalog(*rows):
    result = document(list(rows))
    result['rows']['database:database']['native']['catalog_observations'] = [
        {'section': 'role objects', 'available': True}]
    return result


def test_role_create_and_explicit_privilege_review():
    base = catalog()
    desired = catalog(role('R"ü', system_privileges=['MONITOR_ANY_ATTACHMENT', 'USER_MANAGEMENT'],
                           description="It's reviewed"))
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    operation = plan['operations'][0]
    assert operation['statements'] == [
        'CREATE ROLE "R""ü" SET SYSTEM PRIVILEGES TO USER_MANAGEMENT, MONITOR_ANY_ATTACHMENT',
        'COMMENT ON ROLE "R""ü" IS \'It\'\'s reviewed\'']
    assert operation['security_changes']['added_system_privileges'] == [
        'USER_MANAGEMENT', 'MONITOR_ANY_ATTACHMENT']
    assert operation['security_changes']['ownership'] == 'creating native user'
    assert plan['apply_available'] is False


def test_set_drop_and_independent_live_comment_membership_owner_preservation():
    base = catalog(role(system_privileges=['MONITOR_ANY_ATTACHMENT'], owner='OLD', memberships=[]))
    desired = deepcopy(base)
    desired['rows']['role:R']['native']['system_privileges'] = []
    live = deepcopy(base)
    live['rows']['role:R']['native'].update(description='live', owner='CURRENT',
                                         memberships=[{'grantee': 'SOMEONE'}])
    plan = build_plan(base, desired, live)
    assert plan['status'] == 'review-ready', plan['blockers']
    op = plan['operations'][0]
    assert op['statements'] == ['ALTER ROLE "R" DROP SYSTEM PRIVILEGES']
    assert op['after']['description'] == 'live'
    assert op['security_changes']['removed_system_privileges'] == ['MONITOR_ANY_ATTACHMENT']
    assert build_plan(base, desired, desired)['status'] == 'no-op'


def test_role_set_order_is_not_a_change_and_competing_sets_conflict():
    base = catalog(role(system_privileges=['USER_MANAGEMENT', 'MONITOR_ANY_ATTACHMENT']))
    reordered = catalog(role(system_privileges=['MONITOR_ANY_ATTACHMENT', 'USER_MANAGEMENT']))
    assert build_plan(base, reordered, base)['status'] == 'no-op'
    desired = catalog(role(system_privileges=['READ_RAW_PAGES']))
    live = catalog(role(system_privileges=['USE_GBAK_UTILITY']))
    plan = build_plan(base, desired, live)
    assert plan['status'] == 'blocked' and plan['script'] is None
    assert plan['blockers'][0]['fields'] == ['system_privileges']


@pytest.mark.parametrize('native', [
    {'system_privileges': None}, {'system_privileges': ['UNKNOWN']},
    {'system_privileges': ['READ_RAW_PAGES', 'READ_RAW_PAGES']},
    {'system_privileges': [True]}, {'unknown_system_privilege_bits': [63]},
    {'owner': 'SYSDBA'}, {'memberships': [{'grantee': 'SOMEONE'}]},
    {'privileges': [{'privilege': 'M'}]}, {'auto_admin_mapping': True},
])
def test_role_incomplete_unknown_or_other_lifecycle_metadata_blocks(native):
    base = catalog()
    result = build_plan(base, catalog(role(**native)), base)
    assert result['status'] == 'blocked'
    assert result['script'] is None


def test_role_creation_requires_observed_catalog_and_rejects_builtin():
    base = catalog()
    for name in ('RDB$ADMIN',):
        assert build_plan(base, catalog(role(name)), base)['status'] == 'blocked'
    unavailable = deepcopy(base)
    unavailable['rows']['database:database']['native']['catalog_observations'] = []
    assert build_plan(base, catalog(role()), unavailable)['status'] == 'blocked'


def test_comment_only_change_preserves_native_privileges_and_unknown_bits_block():
    base = catalog(role(system_privileges=['READ_RAW_PAGES']))
    desired = catalog(role(system_privileges=['READ_RAW_PAGES'], description='comment'))
    plan = build_plan(base, desired, base)
    assert plan['operations'][0]['statements'] == ['COMMENT ON ROLE "R" IS \'comment\'']
    live = deepcopy(base)
    live['rows']['role:R']['native']['unknown_system_privilege_bits'] = [63]
    assert build_plan(base, desired, live)['status'] == 'blocked'
