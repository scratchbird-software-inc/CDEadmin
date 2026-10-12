"""Wire policy/plugin validation and private configuration isolation."""

from unittest.mock import Mock
import json
from pathlib import Path

import firebird.driver as native
import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird import provider
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.endpoints.profiles import (
    _connection_fields, provider_route_options,
)


@pytest.mark.parametrize('policy', ['', False, 0, [], {}, 'required', 'Other'])
def test_invalid_policy_cannot_become_native_default(policy):
    with pytest.raises(RelationalClientError, match='policy'):
        provider._wire_configuration({'wire_crypt': policy})


@pytest.mark.parametrize('plugins', [
    '', ' ,;\t', False, 1, [], {}, 'ChaCha64\nWireCrypt=Disabled',
    'ChaCha64\r', 'ChaCha64\x00', 'ChaCha64#', 'ChaCha64{', 'Name=Value',
])
@pytest.mark.parametrize('scope', ['database', 'service', 'create'])
def test_invalid_plugins_fail_before_native_access(plugins, scope):
    module = Mock()
    route = {'host': 'localhost', 'database': '/owned/test.fdb',
             'wire_crypt_plugins': plugins}
    with pytest.raises(RelationalClientError, match='plugin list'):
        if scope == 'database':
            provider._route_arguments(route, module)
        elif scope == 'service':
            provider._server_arguments(route, module)
        else:
            provider._database_create_arguments(
                route, 'localhost:/owned/new.fdb', {}, module)
    assert not module.mock_calls


@pytest.mark.parametrize('plugins', [
    'ChaCha64', 'ChaCha,ChaCha64', 'VendorPlugin;\tChaCha64',
])
def test_native_order_and_vendor_plugin_names_are_preserved(plugins):
    assert provider._wire_configuration({
        'wire_crypt': 'Required', 'wire_crypt_plugins': plugins}) == (
            'WireCrypt=Required\nWireCryptPlugin=' + plugins)


@pytest.mark.parametrize('key,field,value', [
    ('WireCrypt', 'wire_crypt', 'Required'),
    ('WireCryptPlugin', 'wire_crypt_plugins', 'ChaCha64'),
])
def test_raw_configuration_cannot_override_visual_policy(key, field, value):
    with pytest.raises(RelationalClientError, match='duplicates'):
        provider._wire_configuration({field: value,
                                      'wire_config': key + '=' + value})
    text = key + '=' + value
    assert provider._wire_configuration({'wire_config': text}) == text


def test_wire_plugin_preferences_have_distinct_database_and_service_configs(
        monkeypatch):
    monkeypatch.setattr(provider, '_configure_client_library', Mock())
    route = {'host': 'localhost', 'database': '/owned/test.fdb',
             'wire_crypt': 'Required'}
    configurations = []
    for plugins in ('ChaCha64', 'ChaCha'):
        selected = {**route, 'wire_crypt_plugins': plugins}
        db = provider._route_arguments(selected, native)['database']
        service = provider._server_arguments(selected, native)['server']
        assert 'WireCryptPlugin=' + plugins in (
            native.driver_config.get_database(db).config.value)
        assert 'WireCryptPlugin=' + plugins in (
            native.driver_config.get_server(service).config.value)
        configurations.append((db, service))
    assert configurations[0][0] != configurations[1][0]
    assert configurations[0][1] != configurations[1][1]


def test_visual_plugin_field_can_be_cleared_to_native_default():
    manifest = json.loads((Path(provider.__file__).parent /
                           'provider_manifest.json').read_text())
    fields = [field for field in manifest['registration']['connection_fields']
              if field['field_id'] == 'wire_crypt_plugins']
    assert len(fields) == 1
    profile = {'connection_fields': _connection_fields({
        'connection_fields': fields})}
    selected = provider_route_options(profile, {
        'cde_route_wire_crypt_plugins': 'ChaCha'})
    assert selected == {'wire_crypt_plugins': 'ChaCha'}
    assert provider_route_options(profile, {
        'cde_route_wire_crypt_plugins': ''}, selected) == {}
