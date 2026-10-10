"""FoundationDB ownership and no-replay lifecycle regressions."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import test_cdeadmin_distributed_providers  # noqa: F401

from pgadmin.cdeadmin.providers.foundationdb.driver import (
    DatabaseOwner, FoundationDBDriverBackend, FoundationDBDriver,
)
from pgadmin.cdeadmin.providers.foundationdb.provider import PROFILE


def backend():
    value = object.__new__(FoundationDBDriverBackend)
    value._database_routes = {}
    value._databases = []
    return value


def test_missing_value_differs_from_empty_binary():
    value = backend()
    tx = Mock()
    value._transaction = Mock(return_value=tx)
    owner = DatabaseOwner(Mock())
    tx.get.return_value.value = None
    result = list(value.iterate(owner, {'operation': 'get', 'key': ''}, None))
    assert result[0].records == [{'key': '', 'value': None}]
    tx.get.return_value.value = b''
    result = list(value.iterate(owner, {'operation': 'get', 'key': ''}, None))
    assert result[0].records == [{'key': '', 'value': ''}]
    tx.commit.assert_not_called()
    assert tx.cancel.call_count == 2


def test_uncertain_commit_detaches_before_decision_and_never_retries():
    value = backend()
    owner = DatabaseOwner(Mock())
    tx = owner.transaction = Mock()
    tx.commit.return_value.wait.side_effect = OSError
    with pytest.raises(OSError):
        value.control_transaction(owner, 'commit')
    assert owner.transaction is None and owner.state == 'commit-unknown'
    value.close_session(owner, True)
    tx.commit.assert_called_once()
    tx.cancel.assert_not_called()
    tx.on_error.assert_not_called()


def test_explicit_native_transaction_stages_until_decision():
    value = backend()
    owner = DatabaseOwner(Mock())
    owner.transaction = Mock()
    result = list(
        value.iterate(
            owner,
            dict(
                operation='set',
                key='AA==',
                key_encoding='base64',
                value='/w==',
                value_encoding='base64'),
            None))
    owner.transaction.set.assert_called_once_with(b'\0', b'\xff')
    owner.transaction.commit.assert_not_called()
    owner.transaction.cancel.assert_not_called()
    assert result[0].records[0]['staged'] is True


def test_range_pages_retain_native_transaction_and_never_materialize_all():
    value = backend()
    owner = DatabaseOwner(Mock())
    tx = Mock()
    value._transaction = Mock(return_value=tx)
    tx.get_read_version.return_value.wait.return_value = 9007199254740993
    seen = []

    def native_range(*args, **kwargs):
        for i in range(10017):
            seen.append(i)
            yield SimpleNamespace(key=str(i).encode(), value=b'\xff')

    tx.get_range.side_effect = native_range
    iterator = value.iterate(owner, dict(
        operation='range', begin='a', end='z'), None)
    first = next(iterator)
    assert len(first.records) == 256 and len(seen) == 257
    assert first.native['read_version'] == '9007199254740993'
    iterator.close()
    tx.cancel.assert_called_once()
    tx.commit.assert_not_called()


def test_independent_owner_objects_share_only_native_database():
    native = Mock()
    a, b = DatabaseOwner(native), DatabaseOwner(native)
    a.transaction = Mock()
    assert b.transaction is None
    value = backend()
    value._databases = [a, b]
    value.close_session(a)
    assert b.database is native and value._databases == [b]
    native.close.assert_not_called()


def test_failure_quarantines_worker_without_replay():
    value = backend()
    owner = DatabaseOwner(Mock())
    value.open_session = Mock(return_value=owner)
    tx = Mock()
    value._transaction = Mock(return_value=tx)
    tx.commit.return_value.wait.side_effect = TimeoutError
    client = FoundationDBDriver(PROFILE, value, {})
    session = client.open_session({})
    operation = client.execute(
        session, {'source': '{"operation":"set","key":"k","value":"v"}'})
    for _ in range(100):
        result = client.describe_result(operation)
        if result['complete']:
            break
    assert result['payload']['session_reuse_blocked']
    with pytest.raises(RuntimeError, match='unknown'):
        client.execute(session, {'source': '{"operation":"get","key":"k"}'})
    client.close_session(session)
    tx.commit.assert_called_once()
    tx.on_error.assert_not_called()
