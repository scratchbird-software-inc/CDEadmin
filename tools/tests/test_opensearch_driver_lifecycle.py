"""Scroll/cursor cleanup, exact values, partial results and PPL limits."""
from types import SimpleNamespace

import pytest
import test_cdeadmin_mongodb_provider  # noqa: F401
from pgadmin.cdeadmin.providers.opensearch.driver import (
    OpenSearchDriverBackend, exact, native)
from pgadmin.cdeadmin.providers.opensearch_sql_ppl.driver import (
    OpenSearchSQLPPLDriverBackend)


def owner():
    return SimpleNamespace(
        route={
            'read_only': False,
            'query_language': 'sql',
            'fetch_size': 256,
            'explicit_fetch_size': False},
        close=lambda: None)


def response(document):
    return SimpleNamespace(json=lambda: document)


def test_scroll_uses_latest_id_and_retains_failed_cleanup():
    backend, session, calls = OpenSearchDriverBackend(), owner(), []
    responses = iter([
        {'_scroll_id': 'first', 'hits': {'hits': [{'_id': '1'}]}},
        {'_scroll_id': 'second', 'hits': {'hits': [{'_id': '2'}]}}])

    def request(route, path, **kw):
        calls.append(kw)
        if kw['method'] == 'DELETE':
            raise OSError('cleanup unavailable')
        return response(next(responses))

    backend._request = request
    iterator = backend.iterate(session, {'operation': 'scan'}, {})
    next(iterator)
    next(iterator)
    with pytest.raises(OSError):
        iterator.close()
    assert calls[-1]['json_body']['scroll_id'] == ['second']
    assert len(backend._scrolls) == 1
    backend._request = lambda *_, **__: response({'succeeded': True})
    backend.close_session(session)
    assert not backend._scrolls
    backend.close()


def test_partial_scroll_cannot_report_exhaustion():
    backend = OpenSearchDriverBackend()
    backend._request = lambda *_, **__: response({
        'timed_out': True, 'hits': {'hits': [{'_id': '1'}]}})
    iterator = backend.iterate(owner(), {'operation': 'scan'}, {})
    assert next(iterator).native['partial']
    with pytest.raises(Exception, match='Partial scroll'):
        next(iterator)
    backend.close()


def test_sql_cursor_preserves_duplicate_column_ordinals_and_large_rows():
    backend, session, calls = OpenSearchSQLPPLDriverBackend(), owner(), []
    documents = iter([
        {'schema': [{'name': 'same', 'type': 'long'}] * 2,
         'datarows': [[2**63 - 1, i] for i in range(10017)], 'cursor': 'next'},
        {'datarows': [[1, 2]]}])

    def request(route, path, **kw):
        calls.append(kw['json_body'])
        return response(next(documents))

    backend._request = request
    result = list(backend.iterate(session, 'SELECT x, x FROM t', {}))
    assert sum(len(p.records) for p in result) == 10018
    assert result[0].records[0] == [{'$integer': str(2**63 - 1)}, 0]
    assert len(result[-1].schema['columns']) == 2
    assert calls[-1] == {'cursor': 'next'}
    assert not backend._cursors
    backend.close()


def test_sql_cleanup_failure_retains_owner_and_latest_cursor():
    backend, session = OpenSearchSQLPPLDriverBackend(), owner()
    calls = []

    def request(route, path, **kw):
        calls.append((path, kw['json_body']))
        if path.endswith('/close'):
            return response({'succeeded': False})
        return response({'schema': [], 'datarows': [[1]], 'cursor': 'owned'})

    backend._request = request
    iterator = backend.iterate(session, 'SELECT x FROM t', {})
    next(iterator)
    with pytest.raises(Exception, match='cleanup'):
        iterator.close()
    assert backend._cursors[0]['owner'] is session
    backend._request = lambda *_, **__: response({'succeeded': True})
    backend.close_session(session)
    assert not backend._cursors
    backend.close()


def test_ppl_never_injects_sql_fetch_default():
    backend, session, calls = OpenSearchSQLPPLDriverBackend(), owner(), []

    def request(route, path, **kw):
        calls.append(kw['json_body'])
        return response({'schema': [], 'datarows': [[i] for i in range(1100)]})

    backend._request = request
    result = list(
        backend.iterate(
            session, {
                'source': 'source=t', 'language': 'ppl'}, {}))
    assert 'fetch_size' not in calls[0]
    assert sum(len(p.records) for p in result) == 1100
    assert result[-1].native['server_limit_applies']
    assert not result[-1].native['cursor_supported']
    list(
        backend.iterate(
            session, {
                'source': 'source=t', 'language': 'ppl', 'fetch_size': 5}, {}))
    assert calls[-1]['fetch_size'] == 5
    backend.close()


def test_exact_values_and_readonly_mutations():
    assert native(exact({'value': 2**63 - 1})) == {'value': 2**63 - 1}
    backend, session = OpenSearchDriverBackend(), owner()
    session.route['read_only'] = True
    for command in [{'operation': 'bulk', 'actions': [{}]}, {
            'operation': 'request', 'method': 'PUT', 'path': '/index'}]:
        with pytest.raises(Exception, match='Read-only'):
            list(backend.iterate(session, command, {}))
    backend.close()


@pytest.mark.parametrize('failure', ['overflow', 'read-error'])
def test_incomplete_http_response_is_discarded_without_replay(failure):
    from pgadmin.cdeadmin.providers.opensearch.transport import (
        OpenSearchHTTPTransport)
    calls = []

    def read(_amount):
        if failure == 'read-error':
            raise OSError('connection lost')
        return b'12345'

    reply = SimpleNamespace(read=read, close=lambda: calls.append('closed'),
                            release_conn=lambda: calls.append('released'))

    def request(*args, **kwargs):
        calls.append('request')
        assert kwargs['retries'] is False
        return reply

    transport = OpenSearchHTTPTransport()
    transport.max_response_bytes = 4
    transport._pool = lambda *_: SimpleNamespace(request=request)
    with pytest.raises(Exception):
        transport._pooled_request(
            {'connect_timeout': 1, 'statement_timeout': 1},
            'POST', 'http://fixture', b'write', {}, {})
    assert calls == ['request', 'closed', 'released']
    transport.close()
