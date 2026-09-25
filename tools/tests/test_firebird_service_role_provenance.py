"""All service previews expose requested roles, never assumed authorization."""

import copy
from concurrent.futures import ThreadPoolExecutor

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.providers.relational_admin import (
    _FIREBIRD_SERVICE_OPERATIONS,
)
from pgadmin.cdeadmin.providers.firebird.service_connection import (
    service_authentication,
)


@pytest.mark.parametrize('operation', sorted(_FIREBIRD_SERVICE_OPERATIONS))
@pytest.mark.parametrize('task,expected,source', [
    (None, 'DEFAULT', 'connection'), ('', 'DEFAULT', 'connection'),
    ('OVERRIDE', 'OVERRIDE', 'task'),
])
def test_all_service_previews_disclose_effective_role(
        operation, task, expected, source):
    draft = {'role': task}
    if operation == 'activate_shadow':
        draft.update(shadow_filename='/owned/shadow.fdb',
                     confirmation='/owned/shadow.fdb', original_isolated=True)
    if operation == 'repair_database':
        draft['repair_action'] = 'VALIDATE_DB'
    route = {'database': '/owned/main.fdb', 'role': 'DEFAULT',
             'service_expected_database': 'SECURITY_CONTEXT',
             'password': 'never-in-preview',
             'credential_reference_id': 'never-export-reference'}
    request = {'resource_kind': 'database', 'operation_id': operation,
               '_provider_route': route, 'draft': draft}
    before = copy.deepcopy(request)
    plan = ADMINISTRATION.plan(request)
    auth = plan['command_preview']['service_authentication_requested']
    assert auth['requested_role'] == expected
    assert auth['role_source'] == source
    assert auth['authentication_database'] == 'SECURITY_CONTEXT'
    assert auth['authorization_verified'] is False
    assert 'never-' not in repr(plan['command_preview'])
    assert request == before


def test_parallel_service_scopes_never_mutate_connection_defaults():
    route = {'role': 'DEFAULT', 'service_expected_database': 'original'}
    before = copy.deepcopy(route)
    with ThreadPoolExecutor(max_workers=8) as pool:
        observed = list(pool.map(lambda index: service_authentication(
            route, {'role': 'ROLE_' + str(index)}), range(32)))
    assert [v['requested_role'] for v in observed] == [
        'ROLE_' + str(index) for index in range(32)]
    assert route == before
