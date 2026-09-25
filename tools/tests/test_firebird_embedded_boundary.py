"""Local native attachments cannot inherit network access or configuration."""

from unittest.mock import Mock

import firebird.driver as native
from firebird.driver.config import DriverConfig
import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.embedded import embedded_route
from pgadmin.cdeadmin.providers.firebird.provider import (
    _create_client, _database_create_arguments, _route_arguments,
    _server_arguments,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.fixture
def route(tmp_path):
    return {'attachment_mode': 'embedded', 'filesystem_root': str(tmp_path),
            'database': str(tmp_path / 'owned.fdb'), 'user': 'SYSDBA'}


@pytest.mark.parametrize('key,value', [
    ('host', 'localhost'), ('port', 3050), ('protocol', 'INET'),
    ('wire_config', 'Providers=Remote'), ('wire_crypt', 'Required'),
    ('wire_compression', False), ('auth_plugin_list', 'Srp'),
    ('trusted_auth', False), ('service_expected_database', 'other'),
    ('password', 'not-used'), ('timeout', 1), ('dummy_packet_interval', 0),
])
def test_network_options_rejected_before_driver(route, key, value):
    with pytest.raises(RelationalClientError, match='cannot use network'):
        _route_arguments({**route, key: value}, Mock())


@pytest.mark.parametrize('target', [':memory:', 'alias', 'inet://host/db'])
def test_no_alias_memory_or_remote_targets(route, target):
    with pytest.raises(RelationalClientError):
        embedded_route({**route, 'database': target})


def test_escape_and_symlink_rejected(route, tmp_path):
    outside = tmp_path.parent / 'outside.fdb'
    (tmp_path / 'link.fdb').symlink_to(outside)
    for path in (outside, tmp_path / 'link.fdb', tmp_path):
        with pytest.raises(RelationalClientError):
            embedded_route({**route, 'database': str(path)})


@pytest.mark.parametrize('denied', ['embedded_runtime', 'filesystem'])
def test_permissions_before_native_access(route, denied):
    permissions = Mock()

    def require(permission):
        if permission == denied:
            raise PermissionError(permission)

    permissions.require.side_effect = require
    client = _create_client(permissions)
    connector = Mock()
    try:
        with pytest.raises(PermissionError):
            client._invoke_connector({'route': route}, connector)
        connector.assert_not_called()
        permissions.acquire_secret.assert_not_called()
    finally:
        client.close()


@pytest.mark.parametrize('creation', [False, True])
def test_engine13_forced_and_defaults_unchanged(route, monkeypatch, creation):
    registry = DriverConfig('owned-embedded-test')
    registry.db_defaults.config.value = 'Providers=Remote'
    registry.server_defaults.host.value = 'unrelated.example'
    monkeypatch.setattr(native, 'driver_config', registry)
    before = registry.db_defaults.get_config()
    arguments = (_database_create_arguments(
        route, route['database'], {}, native) if creation else
        _route_arguments(route, native))
    config = registry.get_database(arguments['database'])
    server = registry.get_server(config.server.value)
    assert config.config.value == 'Providers=Engine13'
    assert server.host.value is None and server.port.value is None
    assert registry.db_defaults.get_config() == before


def test_services_refused_before_driver_configuration(route):
    module = Mock()
    with pytest.raises(RelationalClientError, match='Services API'):
        _server_arguments(route, module)
    assert not module.mock_calls


def test_implicit_embedded_attachment_refused(route):
    permissions = Mock()
    client = _create_client(permissions)
    connector = Mock()
    try:
        with pytest.raises(RelationalClientError, match='explicit embedded'):
            client._invoke_connector({'route': {
                'database': route['database']}}, connector)
        connector.assert_not_called()
        permissions.acquire_secret.assert_not_called()
    finally:
        client.close()


@pytest.mark.parametrize('key,value', [
    ('credential_reference_id', 'saved'),
    ('credential_references', {'database_password': 'saved'}),
])
def test_saved_credentials_not_acquired(route, key, value):
    permissions = Mock()
    client = _create_client(permissions)
    connector = Mock()
    try:
        with pytest.raises(RelationalClientError, match='filesystem'):
            client._invoke_connector(
                {'route': {**route, key: value}}, connector)
        connector.assert_not_called()
        permissions.acquire_secret.assert_not_called()
    finally:
        client.close()
