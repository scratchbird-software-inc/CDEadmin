"""Local native attachments cannot inherit network access or configuration."""

from unittest.mock import Mock
from dataclasses import replace
from pathlib import Path

import firebird.driver as native
from firebird.driver.config import DriverConfig
import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.embedded import embedded_route
from pgadmin.cdeadmin.providers.firebird.provider import (
    _create_client, _database_create_arguments, _route_arguments,
    _server_arguments, create_provider, FirebirdProvider, PROFILE,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.sdk.actual_engine import PilotProviderError
from tools.tests.test_cdeadmin_actual_engine_pilots import context


def test_embedded_interface_has_no_network_or_service_authority():
    from pgadmin.cdeadmin.providers.firebird.embedded_provider import (
        PROFILE as embedded_profile, ADMINISTRATION as embedded_admin,
    )
    from pgadmin.cdeadmin.providers.relational_admin import (
        _FIREBIRD_SERVICE_OPERATIONS,
    )

    assert embedded_profile.required_permissions == (
        'embedded_runtime', 'filesystem')
    assert embedded_profile.admin_tools == ()
    assert 'service-operation' not in embedded_profile.resource_kinds
    assert 'server' not in embedded_admin.dialect.supported
    assert 'servers' in embedded_admin.dialect.not_applicable_concepts
    assert not (_FIREBIRD_SERVICE_OPERATIONS &
                embedded_admin.dialect.supported['database'])
    assert 'create' in embedded_admin.dialect.supported['table']


@pytest.mark.parametrize('field', [
    'resource_kinds', 'required_permissions', 'result_export_formats',
])
def test_optional_admin_tools_does_not_relax_other_profile_lists(field):
    assert replace(PROFILE, admin_tools=()).admin_tools == ()
    with pytest.raises(PilotProviderError):
        replace(PROFILE, **{field: ()})
    with pytest.raises(PilotProviderError):
        replace(PROFILE, admin_tools=('duplicate', 'duplicate'))


@pytest.mark.parametrize('denied', [
    None, 'administer', 'embedded_runtime', 'filesystem',
])
def test_bootstrap_requires_local_and_administration_authority(route, denied):
    from pgadmin.cdeadmin.providers.firebird.embedded_provider import (
        PROFILE as local_profile, create_provider as local_provider,
    )
    permissions = Mock()

    def require(permission):
        if permission == denied:
            raise PermissionError(permission)

    permissions.require.side_effect = require
    provider = local_provider(replace(
        context(local_profile), target_adapter_id='firebird-embedded-client',
        effective_permissions=frozenset({
            'embedded_runtime', 'filesystem', 'administer'})), permissions)
    provider.client.create_database = Mock(return_value={'created': True})
    try:
        if denied:
            with pytest.raises(PermissionError, match=denied):
                provider.create_initial_database({'route': route})
            provider.client.create_database.assert_not_called()
        else:
            assert provider.create_initial_database({'route': route}) == {
                'created': True}
            provider.client.create_database.assert_called_once_with(
                {'route': route}, route['database'],
                'firebird-create-database')
            # Existing files are rejected even when the native call is mocked.
            Path(route['database']).touch()
            with pytest.raises(RelationalClientError, match='overwrite'):
                provider.create_initial_database({'route': route})
            assert provider.client.create_database.call_count == 1
    finally:
        provider.client.close()


def test_missing_local_library_does_not_break_provider_factory(
        route, monkeypatch, tmp_path):
    monkeypatch.setenv('CDEADMIN_FIREBIRD_CLIENT_LIBRARY',
                       str(tmp_path / 'not-installed.so'))
    client = _create_client(Mock(), attachment_mode='embedded')
    try:
        with pytest.raises(RelationalClientError,
                           match='client library was not found'):
            client.config.connect_arguments(route)
    finally:
        client.close()


@pytest.mark.parametrize('embedded', [True, False])
def test_native_failure_keeps_codes_and_scopes_runtime_hint(
        route, monkeypatch, embedded):
    from pgadmin.cdeadmin.sdk.relational import RelationalDBAPIClient
    failure = RelationalClientError(
        'Firebird connection failed (DatabaseError)')
    failure.gds_codes = (335544375,)

    def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(RelationalDBAPIClient, '_invoke_connector', fail)
    client = _create_client(Mock(), attachment_mode='embedded')
    try:
        with pytest.raises(RelationalClientError) as caught:
            client._invoke_connector({'route': route if embedded else {
                'host': 'localhost', 'database': 'alias'}}, Mock())
        assert caught.value.gds_codes == failure.gds_codes
        assert ('Engine13' in str(caught.value)) == embedded
    finally:
        client.close()


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


@pytest.mark.parametrize('embedded', [False, True])
@pytest.mark.parametrize('operation', ['discover_endpoint', 'open_session'])
def test_provider_mode_cannot_be_changed_by_request(embedded, operation):
    admitted = frozenset({'embedded_runtime', 'filesystem'} if embedded else
                         {'network'})
    selected = replace(
        context(PROFILE), effective_permissions=admitted,
        target_adapter_id=('firebird-embedded-client' if embedded else
                           'firebird_wire-client'))
    client = Mock()
    permissions = Mock()
    provider = FirebirdProvider(selected, permissions, client)
    with pytest.raises(RelationalClientError, match='admitted endpoint'):
        getattr(provider, operation)({'route': {
            'attachment_mode': 'network' if embedded else 'embedded'}})
    assert not client.mock_calls
    assert not permissions.mock_calls
    assert set(provider.profile.required_permissions) == admitted


def test_ambiguous_transport_grants_refused():
    selected = replace(
        context(PROFILE), target_adapter_id='firebird-embedded-client',
        effective_permissions=frozenset({
            'embedded_runtime', 'filesystem', 'network'}))
    with pytest.raises(RelationalClientError, match='together'):
        FirebirdProvider(selected, Mock(), Mock())


def test_network_adapter_is_not_reinterpreted_from_broad_permissions():
    selected = replace(context(PROFILE), effective_permissions=frozenset({
        'embedded_runtime', 'filesystem', 'network'}))
    provider = FirebirdProvider(selected, Mock(), Mock())
    assert provider.attachment_mode == 'network'
    assert provider.profile is PROFILE


@pytest.mark.parametrize('embedded', [False, True])
@pytest.mark.parametrize('operation', ['attach', 'create', 'service'])
def test_factory_client_is_bound_for_every_native_entry(
        route, embedded, operation):
    selected = replace(
        context(PROFILE), target_adapter_id=(
            'firebird-embedded-client' if embedded else
            'firebird_wire-client'),
        effective_permissions=frozenset(
            {'embedded_runtime', 'filesystem'} if embedded else {'network'}))
    provider = create_provider(selected, Mock())
    foreign_route = {'attachment_mode': (
        'network' if embedded else 'embedded')}
    try:
        with pytest.raises(RelationalClientError, match='admitted endpoint'):
            if operation == 'attach':
                provider.client.config.connect_arguments(foreign_route)
            elif operation == 'create':
                provider.client.config.database_create_arguments(
                    foreign_route, route['database'], {})
            else:
                provider.client.config.server_connect_arguments(foreign_route)
    finally:
        provider.client.close()
