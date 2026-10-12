"""FM-FB03-006 validation and native configuration paths."""

from unittest.mock import Mock

import firebird.driver as native
import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird import provider
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('field', ['timeout', 'dummy_packet_interval'])
@pytest.mark.parametrize('value', [
    -1, 2147483648, True, False, 1.5, '1', '', [], {},
])
@pytest.mark.parametrize('scope', ['database', 'service', 'create'])
def test_invalid_timing_rejected_before_driver(field, value, scope):
    route = {'host': 'localhost', 'database': '/owned/timing.fdb',
             field: value}
    module = Mock()
    with pytest.raises(RelationalClientError, match='integer from 0'):
        if scope == 'database':
            provider._route_arguments(route, module)
        elif scope == 'service':
            provider._server_arguments(route, module)
        else:
            provider._database_create_arguments(
                route, 'localhost:/owned/new.fdb', {}, module)
    assert not module.mock_calls


@pytest.mark.parametrize('value', [None, 0, 1, 2147483647])
def test_timing_native_boundaries_and_services_config(value, monkeypatch):
    monkeypatch.setattr(provider, '_configure_client_library', Mock())
    route = {'host': 'localhost', 'database': '/owned/timing.fdb',
             'timeout': value, 'dummy_packet_interval': value}
    args = provider._route_arguments(route, native)
    config = native.driver_config.get_database(args['database'])
    assert config.timeout.value == value
    assert config.dummy_packet_interval.value == value
    svc = provider._server_arguments(route, native)
    text = native.driver_config.get_server(svc['server']).config.value
    expected = None if value is None else f'DummyPacketInterval={value}'
    assert text == config.config.value == expected


def test_dummy_intervals_have_independent_service_configurations(monkeypatch):
    monkeypatch.setattr(provider, '_configure_client_library', Mock())
    servers = [provider._server_arguments({
        'host': 'localhost', 'dummy_packet_interval': value}, native)['server']
        for value in (None, 0, 1)]
    assert len(set(servers)) == 3


@pytest.mark.parametrize('value', [0, 1])
def test_duplicate_dummy_config_is_not_silently_overridden(value):
    with pytest.raises(RelationalClientError, match='duplicates'):
        provider._wire_configuration({
            'dummy_packet_interval': value,
            'wire_config': 'dummyPacketInterval = 4'})
    assert provider._wire_configuration({
        'wire_config': 'DummyPacketInterval=4'}) == 'DummyPacketInterval=4'
