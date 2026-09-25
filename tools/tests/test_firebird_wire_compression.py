"""Native compression options, early rejection and configuration isolation."""

from unittest.mock import Mock

import firebird.driver as native
import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird import provider
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('value', ['', 'true', 'false', 0, 1, [], {}])
@pytest.mark.parametrize('scope', ['database', 'service', 'create'])
def test_invalid_compression_rejected_before_driver(value, scope):
    module = Mock()
    route = {'host': 'localhost', 'database': '/owned/test.fdb',
             'wire_compression': value}
    with pytest.raises(RelationalClientError, match='compression policy'):
        if scope == 'database':
            provider._route_arguments(route, module)
        elif scope == 'service':
            provider._server_arguments(route, module)
        else:
            provider._database_create_arguments(
                route, 'localhost:/owned/new.fdb', {}, module)
    assert not module.mock_calls


@pytest.mark.parametrize('value', [False, True])
@pytest.mark.parametrize('raw', ['WireCompression=true',
                                 '  wirecompression = false'])
def test_duplicate_raw_compression_rejected(value, raw):
    with pytest.raises(RelationalClientError, match='duplicates'):
        provider._wire_configuration({'wire_compression': value,
                                      'wire_config': raw})
    assert provider._wire_configuration({'wire_config': raw}) == raw


def test_compression_uses_isolated_database_and_service_configs(monkeypatch):
    monkeypatch.setattr(provider, '_configure_client_library', Mock())
    configs = []
    for value in (None, False, True):
        route = {'host': 'localhost', 'database': '/owned/compression.fdb',
                 'wire_crypt': 'Required', 'wire_compression': value}
        db = provider._route_arguments(route, native)['database']
        svc = provider._server_arguments(route, native)['server']
        for config in (native.driver_config.get_database(db),
                       native.driver_config.get_server(svc)):
            text = config.config.value
            if value is None:
                assert 'WireCompression' not in text
            else:
                assert 'WireCompression=' + str(value).lower() in text
        configs.append((db, svc))
    assert len({db for db, _ in configs}) == 3
    assert len({svc for _, svc in configs}) == 3
