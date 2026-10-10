"""Milvus exact values, native iterator ownership and no-replay transport."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
import test_cdeadmin_mongodb_provider  # noqa: F401
from pgadmin.cdeadmin.providers.milvus.driver import (
    MilvusDriverBackend, MilvusNativeFailure, exact, native, no_replay_channel)


def test_exact_vectors_and_ids():
    value = {'id': 2**63 - 1, 'binary': b'\x00\xff',
             'sparse': {1: 0.5, 3000: 1.25}, 'dense': [0.25, 1.5]}
    assert native(exact(value)) == value
    with pytest.raises(Exception):
        native({'$integer': str(2**63)})
    with pytest.raises(Exception, match='dimension'):
        native({'$sparse': [[1, 0.5], [1, 1.5]]})


def test_native_iterator_is_untruncated_and_closed():
    class Iterator:
        closed = False
        offset = 0

        def next(self):
            if self.offset == 10017:
                return []
            end = min(10017, self.offset + 256)
            rows = [{'id': i} for i in range(self.offset, end)]
            self.offset = end
            return rows

        def close(self):
            self.closed = True

    iterator = Iterator()
    backend = MilvusDriverBackend()
    owner = SimpleNamespace(
        client=SimpleNamespace(
            query_iterator=lambda **_: iterator),
        route=dict(
            read_only=False,
            operation_timeout=2,
            consistency_level='Strong'))
    pages = list(backend.iterate(owner, {'operation': 'query',
                                         'collection_name': 'values'}, {}))
    assert sum(len(p.records) for p in pages) == 10017
    assert iterator.closed and not backend._iterators


def test_grpc_failure_cannot_trigger_pymilvus_timeout_retry_loop():
    import grpc
    from pymilvus.decorators import retry_on_rpc_failure
    calls = []

    def fail(request, context):
        calls.append(request)
        context.abort(grpc.StatusCode.UNAVAILABLE, 'lost reply')

    server = grpc.server(ThreadPoolExecutor(max_workers=1))
    server.add_generic_rpc_handlers([grpc.method_handlers_generic_handler(
        'fixture', {'write': grpc.unary_unary_rpc_method_handler(fail)})])
    port = server.add_insecure_port('127.0.0.1:0')
    server.start()
    route = MilvusDriverBackend._route({'route': {'host': '127.0.0.1',
                                                  'port': port}})
    channel = no_replay_channel(route)
    call = channel.unary_unary('/fixture/write')

    @retry_on_rpc_failure()
    def write(_self, timeout=None):
        return call(b'write-once', timeout=timeout)

    try:
        with pytest.raises(Exception, match='outcome unknown'):
            write(SimpleNamespace(), timeout=2)
        assert calls == [b'write-once']
    finally:
        channel.close()
        server.stop(0).wait()


def test_failed_iterator_cleanup_preserves_session_for_retry():
    backend, closed = MilvusDriverBackend(), []
    fail = [True]

    def cleanup():
        if fail[0]:
            raise OSError('cleanup unavailable')
        closed.append('iterator')

    owner = SimpleNamespace(client=SimpleNamespace(
        close=lambda: closed.append('client')), closed=False)
    backend._sessions.append(owner)
    backend._iterators.append({'owner': owner, 'iterator': SimpleNamespace(
        close=cleanup)})
    with pytest.raises(OSError):
        backend.close_session(owner)
    assert not owner.closed and not closed
    fail[0] = False
    backend.close_session(owner)
    assert closed == ['iterator', 'client']
    assert not backend._iterators and not backend._sessions
    backend.close()
