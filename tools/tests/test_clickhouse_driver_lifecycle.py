"""Native HTTP streaming bounds, late errors and exact positional rows."""
import json
from types import SimpleNamespace

import pytest
import test_cdeadmin_clickhouse_provider  # noqa: F401
from pgadmin.cdeadmin.providers.clickhouse.driver import (
    ClickHouseDriverBackend)
from pgadmin.cdeadmin.providers.analytic_stream import lines, open_stream


class Response:
    status = 200

    def __init__(self, data):
        self.data = data
        self.closed = self.released = False

    def stream(self, *args, **kwargs):
        for offset in range(0, len(self.data), 7):
            yield self.data[offset:offset + 7]

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


def test_line_bound_and_split_utf8():
    text = ('["é"]\n' * 3).encode()
    assert len(list(lines(Response(text)))) == 3
    with pytest.raises(Exception, match='bound'):
        list(lines(Response(b'X' * 33), maximum=32))


def test_ordinal_columns_and_late_server_failure(monkeypatch):
    prefix = b'["same","same"]\n["Int64","String"]\n'
    rows = b'["9007199254740993","ok"]\n' * 257
    response = Response(prefix + rows + b'Code: 241. Memory limit\n')
    monkeypatch.setattr(
        'pgadmin.cdeadmin.providers.clickhouse.driver.open_stream',
        lambda *a, **k: response)
    backend = ClickHouseDriverBackend()
    owner = backend.open_session({'route': {'host': 'localhost'}})
    iterator = backend.iterate(owner, 'SELECT 1', {})
    first = next(iterator)
    assert first.records[0][0] == '9007199254740993'
    assert first.schema['columns'][1]['ordinal'] == 1
    with pytest.raises(json.JSONDecodeError):
        list(iterator)
    assert response.closed and response.released
    backend.close()


def test_no_redirect_retry_or_preload():
    calls = []
    response = Response(b'')
    response.status = 307

    def request(*args, **kwargs):
        calls.append(kwargs)
        return response

    transport = SimpleNamespace(
        _with_secrets=lambda route, callback: callback({}),
        _authorize=lambda *args: None,
        _pool=lambda *args: SimpleNamespace(request=request))
    with pytest.raises(Exception, match='HTTP request'):
        open_stream(transport, dict(tls_mode='disable', host='localhost',
                                    port=1, connect_timeout=1,
                                    statement_timeout=1), '/', b'query')
    assert len(calls) == 1
    assert calls[0]['retries'] is False
    assert calls[0]['redirect'] is False
    assert calls[0]['preload_content'] is False
    assert response.closed and response.released
