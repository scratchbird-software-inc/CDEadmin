"""Distributed MySQL-wire ownership and native decision regressions."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from test_cdeadmin_distributed_providers import TIDB
from pgadmin.cdeadmin.sdk.relational import RelationalClientConfig
from pgadmin.cdeadmin.providers.mysql_wire_driver import (
    CatalogCursor, RetainedMySQLWireClient, WireExecution,
)
from pgadmin.cdeadmin.providers.tidb.driver import TiDBNativeClient


@pytest.fixture
def owner():
    config = RelationalClientConfig(
        profile=TIDB, module_name='mysql.connector', version_query='SELECT 1',
        version_parser=lambda row: '8.5.6', connect_arguments=lambda r: r,
        metadata_reader=lambda *_: [], security_reader=lambda *_: {})
    client = TiDBNativeClient(config, module=Mock())
    handle = Mock(in_transaction=False)
    client._connections.append(handle)
    client._states[id(handle)] = {}
    client._requests[id(handle)] = {'route': {'host': 'owned'}}
    yield client, handle
    client.close()


def test_lost_commit_is_not_replayed_and_quarantines(owner):
    client, handle = owner
    handle.commit.side_effect = OSError('private data')
    with pytest.raises(RuntimeError, match='command failed'):
        client.control_transaction(handle, 'commit')
    assert client.describe_transaction(handle)['session_reuse_blocked']
    with pytest.raises(RuntimeError, match='unknown'):
        client.control_transaction(handle, 'commit')
    handle.commit.assert_called_once()


def test_decoded_tidb_conflict_allows_explicit_rollback(owner):
    client, handle = owner
    failure = Exception('private statement')
    failure.errno, failure.sqlstate = 9007, 'HY000'
    handle.commit.side_effect = failure
    with pytest.raises(RuntimeError):
        client.control_transaction(handle, 'commit')
    state = client.describe_transaction(handle)
    assert state['transaction_retry_required']
    assert not state['session_reuse_blocked']
    client.control_transaction(handle, 'rollback')
    assert 'errno' not in client.describe_transaction(handle)
    handle.rollback.assert_called_once()


def test_failed_native_close_retains_owner(owner):
    client, handle = owner
    handle.close.side_effect = OSError
    with pytest.raises(RuntimeError, match='release failed'):
        client.close_session(handle)
    assert handle in client._connections
    handle.close.side_effect = None
    client.close_session(handle)
    assert not client._connections


def test_failed_thread_start_does_not_strand_session(owner):
    client, handle = owner
    with patch.object(WireExecution, 'start', side_effect=RuntimeError):
        with pytest.raises(RuntimeError, match='could not start'):
            client.execute(handle, {'source': 'SELECT 1'})
    assert not client._operations


def test_unobserved_result_blocks_decisions_and_metadata(owner):
    client, handle = owner
    token = WireExecution(client, handle, 'SELECT 1', (), {})
    token.finished.set()
    client._operations.append(token)
    for action in [lambda: client.control_transaction(handle, 'commit'),
                   lambda: client.list_resources(
                       {'_provider_session_handle': handle})]:
        with pytest.raises(RuntimeError, match='execution is active'):
            action()
    assert client.describe_result(token)['complete']
    client.control_transaction(handle, 'commit')


def test_optional_catalog_error_never_rolls_back_transaction():
    cursor = Mock()
    error = Exception()
    error.errno = 1146
    cursor.execute.side_effect = error
    assert CatalogCursor(cursor).cde_optional_rows('SELECT missing') == []
    cursor.connection.rollback.assert_not_called()
    error.errno = 9007
    with pytest.raises(Exception):
        CatalogCursor(cursor).cde_optional_rows('SELECT conflict')


@pytest.mark.parametrize('origin,accepted',
                         [('original', True), ('new', False)])
def test_tidb_cancellation_pins_process_identity(owner, origin, accepted):
    client, handle = owner
    cursor = Mock()
    cursor.fetchone.return_value = (origin, 123)
    control = Mock()
    control.cursor.return_value = cursor
    client._invoke_connector = Mock(return_value=control)
    token = SimpleNamespace(
        identity=(
            'original',
            123),
        request={},
        handle=handle)
    if accepted:
        client.cancel_native(token)
        assert cursor.execute.call_args.args == ('KILL TIDB QUERY 123',)
    else:
        with pytest.raises(RuntimeError, match='origin changed'):
            client.cancel_native(token)
        assert cursor.execute.call_count == 1
    control.close.assert_called_once()


def test_explicit_connector_implementation_is_not_dropped(owner):
    client, _ = owner
    assert client.config.connect_arguments({})['use_pure'] is True
    assert client.config.connect_arguments({'use_pure': False})[
        'use_pure'] is False
    with pytest.raises(RuntimeError, match='Boolean'):
        client.config.connect_arguments({'use_pure': 'false'})
