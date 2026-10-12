"""Redis retained ownership, exact RESP types and no-replay regressions."""
from unittest.mock import Mock

import pytest
import test_cdeadmin_distributed_providers  # noqa: F401
from pgadmin.cdeadmin.providers.redis.driver import (
    RedisDriverBackend, RedisOwner, exact, argument,
)


def owner():
    value = RedisOwner(
        Mock(), None, {
            'topology_mode': 'standalone', 'database': 0})
    value.connection = Mock()
    return value


def test_resp_map_keys_and_unsafe_numbers_are_not_stringified_or_rounded():
    value = exact({b'\0\xff': 9007199254740993, b'plain': {b'a', b'b'}})
    assert value['$map'][0] == [
        {'$binary': 'AP8='}, {'$integer': '9007199254740993'}]
    assert set(value['$map'][1][1]['$set']) == {'a', 'b'}
    assert exact(float('inf')) == {'$float': 'inf'}
    assert argument({'$integer': '9007199254740993'}) == b'9007199254740993'
    with pytest.raises(RuntimeError):
        argument(9007199254740993)


def test_multi_exec_commands_use_the_same_reserved_connection():
    backend = RedisDriverBackend()
    handle = owner()
    handle.connection.read_response.side_effect = [b'OK', b'QUEUED', [b'OK']]
    backend._command(handle, (b'MULTI',))
    assert handle.state == 'multi'
    assert backend._command(handle, (b'SET', b'key', b'v')) == b'QUEUED'
    assert backend._command(handle, (b'EXEC',)) == [b'OK']
    assert handle.last_decision == [b'OK']
    assert handle.connection.send_command.call_count == 3
    handle.client.execute_command.assert_not_called()


def test_failed_exec_is_never_repeated_or_reinterpreted_as_discard():
    backend = RedisDriverBackend()
    handle = owner()
    connection = handle.connection
    connection.read_response.side_effect = OSError
    with pytest.raises(OSError):
        backend._command(handle, (b'EXEC',))
    assert handle.state == 'exec-unknown'
    backend.close_session(handle, True)
    assert handle.client is None and handle.connection is None
    connection.send_command.assert_called_once_with(b'EXEC')
    # Close disconnected the socket, without a second command.


def test_failed_connection_cleanup_retains_owner_for_retry():
    backend = RedisDriverBackend()
    handle = owner()
    backend._sessions.append(handle)
    connection, client = handle.connection, handle.client
    connection.disconnect.side_effect = OSError
    with pytest.raises(RuntimeError, match='cleanup incomplete'):
        backend.close_session(handle)
    assert handle in backend._sessions and handle.client is client
    assert handle.connection is connection
    client.close.assert_not_called()
    connection.disconnect.side_effect = None
    backend.close_session(handle)
    assert handle not in backend._sessions
    client.close.assert_called_once()


def test_temporary_cleanup_attempts_both_and_retains_failed_pair():
    backend = RedisDriverBackend()
    client, topology = Mock(), Mock()
    client.close.side_effect = OSError
    with pytest.raises(RuntimeError):
        backend._close_native(client, topology)
    topology.close.assert_called_once()
    assert backend._pending_native_cleanup == [(client, topology)]
    client.close.side_effect = None
    backend.close()
    assert not backend._pending_native_cleanup


def test_reply_pages_remain_lazy_and_ordinal():
    backend = RedisDriverBackend()
    handle = owner()
    seen = []

    def values():
        for i in range(10017):
            seen.append(i)
            yield i

    pages = backend._pages(values(), 'SCAN', handle)
    first = next(pages)
    assert len(first.records) == 256 and len(seen) == 257
    second = next(pages)
    assert second.native['row_offset'] == 256
    assert second.records[0]['ordinal'] == 256
    pages.close()


def test_cluster_command_catalog_names_preserve_binary_operands():
    args = (b'ACL', b'GETUSER', b'\0\xff')
    assert RedisDriverBackend._cluster_arguments(
        args) == ('ACL GETUSER', b'\0\xff')
    with pytest.raises(RuntimeError, match='retries must be zero'):
        route = dict(host='localhost', cluster_error_retry_attempts=1)
        RedisDriverBackend._route({'route': route})
