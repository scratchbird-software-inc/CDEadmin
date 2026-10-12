"""VTGate native ownership, cancellation and uncertain decision contracts."""
import socket
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_cdeadmin_distributed_providers import VITESS
from pgadmin.cdeadmin.sdk.relational import RelationalClientConfig
from pgadmin.cdeadmin.providers.mysql_family.mysql_connections import Lease
from pgadmin.cdeadmin.providers.vitess.driver import VitessNativeClient


@pytest.fixture
def owner():
    config = RelationalClientConfig(
        profile=VITESS, module_name='mysql.connector',
        version_query='SELECT 1',
        version_parser=lambda row: '23.0.3', connect_arguments=lambda r: r,
        metadata_reader=lambda *_: [], security_reader=lambda *_: {})
    client = VitessNativeClient(config, module=Mock())
    handle = Mock(in_transaction=False)
    client._connections.append(handle)
    client._states[id(handle)] = {}
    client._requests[id(handle)] = {'route': {'host': 'owned'}}
    yield client, handle
    client.close()


def test_gateway_rpc_error_packet_is_not_a_known_mutation_outcome(owner):
    client, _ = owner
    error = Exception('private query')
    error.errno, error.sqlstate = 1105, 'HY000'
    assert not client.error_outcome_known(error)
    error.errno = 1062
    assert client.error_outcome_known(error)


def test_failed_decision_packet_quarantines_without_replay(owner):
    client, handle = owner
    error = Exception('private tablet response')
    error.errno, error.sqlstate = 1105, 'HY000'
    handle.commit.side_effect = error
    with pytest.raises(RuntimeError):
        client.control_transaction(handle, 'commit')
    assert client.describe_transaction(handle)['outcome_unknown']
    with pytest.raises(RuntimeError, match='unknown'):
        client.control_transaction(handle, 'commit')
    handle.commit.assert_called_once()


def test_cancel_targets_owned_socket_and_never_opens_control_connection(owner):
    client, handle = owner
    native_socket = handle._socket.sock
    token = SimpleNamespace(handle=handle, identity=native_socket,
                            uncertain=False)
    client.cancel_native(token)
    native_socket.shutdown.assert_called_once_with(socket.SHUT_RDWR)
    client.module.connect.assert_not_called()
    assert token.uncertain
    assert client.describe_transaction(handle)['session_reuse_blocked']


def test_changed_socket_refuses_cancel(owner):
    client, handle = owner
    with pytest.raises(RuntimeError, match='unavailable'):
        client.cancel_native(SimpleNamespace(handle=handle, identity=object()))
    handle._socket.sock.shutdown.assert_not_called()


def test_vtgate_lease_is_discarded_even_after_known_success(owner):
    client, handle = owner
    pool = Mock()
    lease = Lease(pool, handle)
    client._connections.remove(handle)
    client._connections.append(lease)
    client._states[id(lease)] = {}
    client._requests[id(lease)] = {}
    client._forget_and_close(lease)
    handle.close.assert_called_once()
    pool.release.assert_not_called()
    pool.discard.assert_called_once_with(handle)
    assert not client._connections


def test_failed_discard_close_preserves_lease_for_retry(owner):
    client, handle = owner
    pool = Mock()
    lease = Lease(pool, handle)
    client._connections.remove(handle)
    client._connections.append(lease)
    client._states[id(lease)] = {}
    client._requests[id(lease)] = {}
    handle.close.side_effect = OSError
    with pytest.raises(RuntimeError, match='release failed'):
        client._forget_and_close(lease)
    assert lease in client._connections and lease._native is handle
    pool.discard.assert_not_called()
    handle.close.side_effect = None
    client._forget_and_close(lease)
