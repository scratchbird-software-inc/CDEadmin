import config
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError


def service(profile='firebird-native', **changes):
    owner = object.__new__(ProviderWorkspaceService)
    route = {'host': '::1', 'port': 3051, 'database': '/server/file name.fdb',
             'user': 'Account', 'charset': 'UTF8', 'role': 'Role',
             'password': 'must-not-leave-server', 'credential_reference_id': 'sealed', **changes}
    owner.endpoint_service = SimpleNamespace(workspace=Mock(return_value=(None, {'route': route}, None)))
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id=profile))
    return owner, server


def test_exact_owner_scoped_connection_description_has_no_secrets():
    owner, server = service()
    result = owner.firebird_isql_context(server, {'database_target_id': 'owned'})
    assert result == {'schema': 'scratchrobin.firebird.isql-context@1', 'database_target_id': 'owned',
        'dsn': 'inet://[::1]:3051//server/file name.fdb', 'user': 'Account', 'role': 'Role', 'charset': 'UTF8', 'sql_dialect': 3}
    owner.endpoint_service.workspace.assert_called_once_with(server, database_target_id='owned')


@pytest.mark.parametrize('payload', [{}, {'database_target_id': ''}, {'database_target_id': 'owned', 'password': 'bad'}, None])
def test_invalid_scope_is_refused_before_route_access(payload):
    owner, server = service()
    with pytest.raises(ProviderWorkspaceError): owner.firebird_isql_context(server, payload)
    owner.endpoint_service.workspace.assert_not_called()


@pytest.mark.parametrize('changes', [{'profile': 'postgresql-native'}, {'profile': 'firebird-embedded'}, {'host': ''}, {'protocol': 'XNET'}, {'sql_dialect': 2}])
def test_local_or_unsupported_targets_are_not_reinterpreted(changes):
    owner, server = service(**changes)
    with pytest.raises(ProviderWorkspaceError): owner.firebird_isql_context(server, {'database_target_id': 'owned'})
