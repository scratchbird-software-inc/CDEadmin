"""Retained XTDB ownership and exact values without synthetic transactions."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_xtdb_provider  # noqa: F401
from pgadmin.cdeadmin.providers.xtdb.client import _Session
from pgadmin.cdeadmin.providers.xtdb.driver import XTDBNativeClient
from pgadmin.cdeadmin.providers.temporal_wire import TemporalExecution


@pytest.fixture
def owner():
    module = SimpleNamespace(__version__='3.3.4', connect=Mock())
    client = XTDBNativeClient(module=module)
    connection = Mock(closed=False, autocommit=True)
    handle = _Session(connection, dict(transaction_mode='read-write',
                                       transaction_async=True,
                                       transaction_timezone='UTC'))
    client._connections.append(handle)
    yield client, handle
    client.close()


def test_exact_integer_parameters_and_nested_result_values(owner):
    client, _ = owner
    value = client._adapt_value({'$xtdb_type': 'integer',
                                 'value': '9007199254740993'})
    assert value == 9007199254740993
    with pytest.raises(RuntimeError, match='envelope'):
        client._adapt_value(9007199254740993)
    assert client.json_value({'nested': [9007199254740993]}) == {
        'nested': [{'$xtdb_type': 'integer', 'value': '9007199254740993'}]}


def test_control_begin_preserves_native_async_timezone_policy(owner):
    client, handle = owner
    cursor = handle.connection.cursor.return_value
    cursor.statusmessage = 'BEGIN'
    client.control_transaction(handle, 'begin')
    cursor.execute.assert_called_once_with(
        "BEGIN READ WRITE WITH (ASYNC, TIMEZONE = 'UTC')")
    assert client.describe_transaction(handle)['native_observation'] == 'BEGIN'


def test_native_rollback_tag_is_not_relabelled_commit(owner):
    client, handle = owner
    handle.connection.cursor.return_value.statusmessage = 'ROLLBACK'
    client.control_transaction(handle, 'commit')
    assert client.describe_transaction(
        handle)['native_observation'] == 'ROLLBACK'


def test_lost_commit_quarantines_without_retry(owner):
    client, handle = owner
    cursor = handle.connection.cursor.return_value
    cursor.execute.side_effect = OSError
    with pytest.raises(RuntimeError):
        client.control_transaction(handle, 'commit')
    with pytest.raises(RuntimeError, match='unknown'):
        client.control_transaction(handle, 'commit')
    cursor.execute.assert_called_once()


def test_unobserved_result_prevents_transaction_control(owner):
    client, handle = owner
    token = TemporalExecution(client, handle, 'SELECT 1', ())
    token.finished.set()
    client._operations.append(token)
    with pytest.raises(RuntimeError, match='active'):
        client.control_transaction(handle, 'commit')
    handle.connection.cursor.assert_not_called()


def test_failed_close_preserves_retained_handle(owner):
    client, handle = owner
    handle.connection.close.side_effect = OSError
    with pytest.raises(RuntimeError, match='cleanup'):
        client.close_session(handle)
    assert handle in client._connections
    handle.connection.close.side_effect = None
    client.close_session(handle)
    assert not client._connections
