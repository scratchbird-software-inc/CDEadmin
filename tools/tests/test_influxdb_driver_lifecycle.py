"""InfluxDB exact values, explicit writes and native JSONL delivery."""
import json

import pytest
import test_cdeadmin_clickhouse_provider  # noqa: F401
from test_clickhouse_driver_lifecycle import Response
from pgadmin.cdeadmin.providers.influxdb.driver import (
    InfluxDBDriverBackend, exact, parameters_native)


def test_exact_native_integer_roundtrip():
    value = {'signed': -(2**63), 'unsigned': 2**64 - 1, 'tag': 'é'}
    assert parameters_native(exact(value)) == value
    with pytest.raises(Exception):
        parameters_native({'$integer': '1.2'})


def test_jsonl_stream_not_truncated_and_response_closed(monkeypatch):
    response = Response(b'{"v":9223372036854775807}\n' * 10017)
    monkeypatch.setattr(
        'pgadmin.cdeadmin.providers.influxdb.driver.open_stream',
        lambda *a, **k: response)
    backend = InfluxDBDriverBackend()
    owner = backend.open_session({'route': {'host': 'localhost'}})
    pages = list(backend.iterate(owner, 'SELECT * FROM values', {}))
    assert sum(len(p.records) for p in pages) == 10017
    assert pages[0].records[0]['v'] == {'$integer': '9223372036854775807'}
    assert response.closed and response.released
    backend.close()


def test_explicit_write_flags_and_readonly(monkeypatch):
    backend = InfluxDBDriverBackend()
    owner = backend.open_session({'route': {'host': 'localhost'}})
    calls = []
    monkeypatch.setattr(backend, '_request', lambda *a, **k: calls.append(k))
    command = {'operation': 'write', 'line_protocol': 'm v=1i 1'}
    list(backend.iterate(owner, command, {}))
    assert calls[0]['query']['accept_partial'] == 'false'
    assert calls[0]['query']['no_sync'] == 'false'
    owner.route['read_only'] = True
    with pytest.raises(Exception, match='Read-only'):
        list(backend.iterate(owner, command, {}))
    assert len(calls) == 1
    backend.close()
