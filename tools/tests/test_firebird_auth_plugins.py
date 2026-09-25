"""Preserve exact plugin policy across private attachment configurations."""

from unittest.mock import patch

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.provider import (
    _route_arguments, _server_arguments, _database_create_arguments,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('value', [
    '', ' ,;\t ', False, 1, [], {}, 'Srp256\x00Legacy_Auth', 'Srp\nSrp256',
    'Srp\r', 'Srp\x7f'])
@pytest.mark.parametrize('kind', ['attach', 'create', 'services'])
def test_invalid_policy_fails_before_native_configuration(value, kind):
    route = {'host': 'localhost', 'database': '/owned.fdb',
             'auth_plugin_list': value}
    with pytest.raises(RelationalClientError, match='plugin list'):
        if kind == 'services':
            _server_arguments(route, None)
        elif kind == 'create':
            _database_create_arguments(route, '/new.fdb', {}, None)
        else:
            _route_arguments(route)


@pytest.mark.parametrize('value', [
    None, 'Srp512,Srp256', 'Srp256,Srp512', 'Srp384;\tSrp256 Srp', 'Srp,Srp',
    'ThirdPartyAuthentication,Srp256'])
def test_preserve_exact_policy_for_all_attachment_paths(value):
    import firebird.driver as driver
    route = {'host': 'localhost', 'database': '/owned.fdb',
             'auth_plugin_list': value}
    attach = _route_arguments(route, driver)
    create = _database_create_arguments(route, '/new.fdb', {}, driver)
    with patch('pgadmin.cdeadmin.providers.firebird.provider.'
               '_configure_client_library'):
        service = _server_arguments(route, driver)
    for arguments in (attach, create):
        config = driver.driver_config.get_database(arguments['database'])
        server = driver.driver_config.get_server(config.server.value)
        assert server.auth_plugin_list.value == value
        assert arguments['auth_plugin_list'] == value
    assert driver.driver_config.get_server(
        service['server']).auth_plugin_list.value == value
    assert attach['database'] != create['database']


def test_reordered_lists_cannot_reuse_private_configuration():
    import firebird.driver as driver
    route = {'host': 'localhost', 'database': '/owned.fdb'}
    first = _route_arguments(
        {**route, 'auth_plugin_list': 'Srp,Srp256'}, driver)
    second = _route_arguments(
        {**route, 'auth_plugin_list': 'Srp256,Srp'}, driver)
    assert first['database'] != second['database']


@pytest.mark.parametrize('value', ['', ' ;,\t ', 'Srp\x00', False])
def test_profile_validation_cannot_remove_invalid_list(value):
    from pgadmin.cdeadmin.endpoints.service import EndpointService
    from pgadmin.cdeadmin.endpoints import EndpointRegistrationError
    profile = {'profile_id': 'firebird-native'}
    with pytest.raises(EndpointRegistrationError, match='plugin list'):
        EndpointService._validated_route(
            profile, {'cde_route_auth_plugin_list': value})
    with pytest.raises(EndpointRegistrationError, match='plugin list'):
        EndpointService._server_form_values(
            profile, 'edit', {'auth_plugin_list': value})


def test_gate_collects_failures_without_leaking_exception_text(
        monkeypatch, tmp_path):
    from tools import cdeadmin_firebird_auth_plugins_gate as gate
    seen = []

    def check(_route, _password, plugins, expected, wire, creation=False):
        seen.append(plugins)
        if plugins == 'Srp512,Srp256':
            raise RuntimeError('private-secret-never-report')
        return {'observed': expected}

    def fixture(evidence, browser, **_kwargs):
        evidence.mkdir()
        with pytest.raises(AssertionError, match='failures recorded'):
            browser({'user': 'owned'}, 'Srp256', [('owned', 'secret')],
                    evidence / 'Srp256')

    monkeypatch.setattr(gate, 'attach', check)
    monkeypatch.setattr(gate, 'password_run', fixture)
    gate.run(tmp_path / 'evidence')
    assert set(seen) == {row[1] for row in gate.CASES}
    evidence = (tmp_path / 'evidence/Srp256/negotiation.json').read_text()
    assert 'private-secret-never-report' not in evidence
    assert 'concurrent-isolation' in evidence


@pytest.mark.parametrize('offered', [
    [], ['Srp'], ['Srp256', 'BadPlugin'], ['Srp256', 'Srp256']])
def test_owned_gate_rejects_invalid_server_setup_before_docker(
        monkeypatch, tmp_path, offered):
    from unittest.mock import Mock
    from tools import cdeadmin_firebird_password_gate as gate
    docker = Mock()
    monkeypatch.setattr(gate, 'docker', docker)
    with pytest.raises(ValueError, match='server plugins'):
        gate.run(tmp_path / 'invalid', selected_plugins=['Srp256'],
                 server_plugins=offered)
    docker.assert_not_called()
    assert not (tmp_path / 'invalid').exists()
