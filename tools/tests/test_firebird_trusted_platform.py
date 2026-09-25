"""FM-FB02-003 Linux exclusion; simulated Windows is not login evidence."""

from unittest.mock import Mock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.authentication import (
    validate_authentication_plugins,
)
from pgadmin.cdeadmin.providers.firebird.provider import (
    _route_arguments, _server_arguments, _database_create_arguments,
)
from pgadmin.cdeadmin.endpoints.service import EndpointService
from pgadmin.cdeadmin.endpoints import EndpointRegistrationError
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('platform', ['linux', 'darwin'])
@pytest.mark.parametrize('plugins', [None, 'Win_Sspi', 'Win_Sspi,Srp256'])
def test_non_windows_rejects_before_driver_configuration(
        monkeypatch, platform, plugins):
    monkeypatch.setattr(
        'pgadmin.cdeadmin.providers.firebird.authentication.sys.platform',
        platform)
    route = {'host': 'windows-server.example', 'database': 'owned.fdb',
             'trusted_auth': True, 'auth_plugin_list': plugins,
             'user': 'must-not-be-used'}
    driver = Mock()
    for call in (
        lambda: _route_arguments(route, driver),
        lambda: _server_arguments(route, driver),
        lambda: _database_create_arguments(route, 'owned:new.fdb', {}, driver),
    ):
        with pytest.raises(RelationalClientError, match='host to run Windows'):
            call()
    assert not driver.mock_calls


@pytest.mark.parametrize('value', ['false', 'true', 0, 1, [], {}])
def test_trusted_selection_has_no_truthiness_conversion(value):
    with pytest.raises(RelationalClientError, match='boolean'):
        validate_authentication_plugins({'trusted_auth': value})


def test_linux_preserves_mixed_native_plugin_lists():
    # An explicit mixed AuthClient list is different from requesting trusted
    # authentication. Native negotiation may select its installed SRP entry.
    validate_authentication_plugins({
        'trusted_auth': False, 'auth_plugin_list': 'Win_Sspi,Srp256'})


def test_windows_policy_admission_is_not_native_login_evidence(monkeypatch):
    monkeypatch.setattr(
        'pgadmin.cdeadmin.providers.firebird.authentication.'
        'windows_authentication_host', lambda: True)
    validate_authentication_plugins({
        'trusted_auth': True, 'auth_plugin_list': 'Win_Sspi'})


def test_linux_profile_and_route_cannot_persist_trusted_selection(monkeypatch):
    monkeypatch.setattr(
        'pgadmin.cdeadmin.providers.firebird.authentication.'
        'windows_authentication_host', lambda: False)
    profile = {'profile_id': 'firebird-native'}
    with pytest.raises(EndpointRegistrationError, match='host to run Windows'):
        EndpointService._server_form_values(
            profile, 'edit', {'trusted_auth': True})
    with pytest.raises(EndpointRegistrationError, match='host to run Windows'):
        EndpointService._validated_route(
            profile, {'cde_route_trusted_auth': True})


def test_existing_imported_trusted_route_is_rejected(monkeypatch):
    monkeypatch.setattr(
        'pgadmin.cdeadmin.providers.firebird.authentication.'
        'windows_authentication_host', lambda: False)
    with pytest.raises(EndpointRegistrationError, match='host to run Windows'):
        EndpointService._validated_route(
            {'profile_id': 'firebird-native'}, {}, {'trusted_auth': True})
