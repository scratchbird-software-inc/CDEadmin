"""Audited configuration grammar, precedence and driver-default isolation."""

from unittest.mock import Mock

import firebird.driver as native
from firebird.driver.config import DriverConfig
import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird import provider
from pgadmin.cdeadmin.providers.firebird.config_text import (
    validate_config_text,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.endpoints import (
    EndpointService, EndpointRegistrationError, registration_profile,
)


@pytest.mark.parametrize('text', [
    'include /etc/passwd', 'include = /etc/passwd', 'Providers=Engine13',
    'RemoteServicePort=9999', 'SecurityDatabase=/other', 'AuthServer=Srp',
    'TcpRemoteBufferSize=8192', 'StatementTimeout=10', 'MadeUp=1',
    'WireCrypt=', 'WireCrypt=not-a-policy', 'WireCompression=maybe',
    'ConnectionTimeout=-1', 'ConnectionTimeout=2147483648',
    'ConnectionTimeout=2G', 'ClientBatchBuffer=128KB',
    'WireCryptPlugin=$(root)', 'WireCryptPlugin= {other}',
    'WireCrypt=Required\x00', 'WireCrypt=Required\v',
    'WireCompression=true\nWIRECOMPRESSION=false',
    'WireCrypt="Required" garbage', 'AuthClient= ,;', 'x' * 16385,
    'AuthClient=\ud800',
])
@pytest.mark.parametrize('scope', ['database', 'service', 'create'])
def test_bad_config_fails_before_native_access(text, scope):
    module = Mock()
    route = {'host': 'localhost', 'database': '/owned/config.fdb',
             'wire_config': text}
    with pytest.raises(RelationalClientError):
        if scope == 'database':
            provider._route_arguments(route, module)
        elif scope == 'service':
            provider._server_arguments(route, module)
        else:
            provider._database_create_arguments(
                route, 'localhost:/owned/new.fdb', {}, module)
    assert not module.mock_calls


@pytest.mark.parametrize('text', [
    '', '# comment only\n', ' # WireCrypt=Disabled\nWireCrypt=Required',
    'wIrEcRyPt = "required" # comment\r\n',
    'AuthClient=Srp256; Srp', 'WireCryptPlugin=VendorPlugin,ChaCha64',
    'TcpNoNagle=yes', 'WireCompression=n', 'ClientBatchBuffer=128K',
    'ConnectionTimeout=0', 'DummyPacketInterval=2147483647',
])
def test_valid_native_text_is_preserved(text):
    validate_config_text(text)
    assert provider._wire_configuration({'wire_config': text}) == (
        text or None)


def test_raw_auth_cannot_override_explicit_plugin_selection():
    with pytest.raises(RelationalClientError, match='duplicates'):
        provider._wire_configuration({'auth_plugin_list': 'Srp256',
                                      'wire_config': 'AuthClient=Legacy_Auth'})


@pytest.mark.parametrize('text', [
    'include /etc/passwd', 'Unknown=1', 'WireCrypt=Disabled',
])
def test_invalid_or_conflicting_raw_text_cannot_be_saved(text):
    with pytest.raises(EndpointRegistrationError):
        EndpointService._validated_route(
            registration_profile('firebird-native'),
            {'cde_route_wire_config': text}, {
                'host': 'localhost', 'wire_crypt': 'Required'})


@pytest.mark.parametrize('text', [
    '# comment\r\nTcpNoNagle=false\nClientBatchBuffer=128K',
    '#' + 'x' * 16383,
])
def test_server_form_preserves_valid_multiline_and_maximum_text(text):
    values = EndpointService._server_form_values(
        registration_profile('firebird-native'), 'edit',
        {'name': 'owned', 'host': 'localhost', 'port': 3050,
         'wire_config': text})
    assert values['wire_config'] == text


@pytest.mark.parametrize('text', ['#' + 'x' * 16384, 'TcpNoNagle=no\x00',
                                  'include /etc/passwd'])
def test_server_form_still_rejects_invalid_native_text(text):
    with pytest.raises(EndpointRegistrationError):
        EndpointService._server_form_values(
            registration_profile('firebird-native'), 'edit',
            {'name': 'owned', 'host': 'localhost', 'port': 3050,
             'wire_config': text})


def test_server_form_does_not_relax_other_fields():
    with pytest.raises(EndpointRegistrationError):
        EndpointService._server_form_values(
            registration_profile('firebird-native'), 'edit',
            {'name': 'owned', 'host': 'local\nhost', 'port': 3050})


def test_wire_config_isolated_from_driver_defaults_and_names(monkeypatch):
    registry = DriverConfig('owned-config-isolation')
    monkeypatch.setattr(native, 'driver_config', registry)
    monkeypatch.setattr(native.core, 'driver_config', registry)
    monkeypatch.setattr(provider, '_configure_client_library', Mock())
    for defaults in (registry.db_defaults, registry.server_defaults):
        defaults.config.value = 'Providers=Engine13\nWireCrypt=Disabled'
        defaults.password.value = 'unrelated-secret'
    registry.db_defaults.timeout.value = 999
    registry.register_database('inventory').config.value = 'WireCrypt=Disabled'
    original = (registry.db_defaults.get_config(),
                registry.server_defaults.get_config())
    for raw in (None, 'WireCrypt=Required'):
        route = {'host': 'localhost', 'database': 'inventory',
                 'wire_config': raw, 'timeout': 1}
        db = provider._route_arguments(route, native)['database']
        service = provider._server_arguments(route, native)['server']
        assert registry.get_database(db).config.value == raw
        assert registry.get_database(db).timeout.value == 1
        assert registry.get_server(service).config.value == raw
        assert registry.get_server(service).password.value is None
    assert original == (registry.db_defaults.get_config(),
                        registry.server_defaults.get_config())
