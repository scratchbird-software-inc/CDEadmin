"""YCQL asynchronous ownership, exact bindings and no-replay regressions."""
from decimal import Decimal
from threading import Event
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_cdeadmin_yugabytedb_ycql_provider import fake_module, route
from pgadmin.cdeadmin.providers.yugabytedb_ycql.driver import (
    NativeYCQLClient, bindings, exact, prepared_bindings,
)


@pytest.fixture
def owner():
    module, _ = fake_module()
    client = NativeYCQLClient(module=module)
    handle = client.open_session({'route': route()})
    handle.session = Mock(row_factory=lambda *_: None)
    future = Mock(trace_id=None, warnings=[])
    result = SimpleNamespace(column_names=['same', 'same'],
                             column_types=['bigint', 'text'],
                             current_rows=[(2**63 - 1, 'native')],
                             has_more_pages=False)
    future.result.return_value = result
    handle.session.execute_async.return_value = future
    yield client, handle, future
    client.close()


def finish(client, token):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = client.describe_result(token)
        if value['complete']:
            return value
    raise AssertionError('YCQL operation did not finish')


def test_execute_returns_before_response_and_owns_session(owner):
    client, handle, future = owner
    release = Event()
    result = future.result.return_value
    future.result.side_effect = lambda: result if release.wait(2) else None
    token = client.execute(handle, {'source': 'SELECT value FROM owned'})
    try:
        assert not token.finished.is_set()
        with pytest.raises(RuntimeError, match='execution is active'):
            client.execute(handle, {'source': 'SELECT 2'})
        assert client.cancel(token)
        assert not token.finished.is_set()
    finally:
        release.set()
    page = finish(client, token)
    assert page['payload']['local_delivery_stopped']
    assert not page['payload']['server_cancellation_confirmed']
    future.cancel.assert_not_called()


def test_duplicate_columns_and_browser_unsafe_integer(owner):
    client, handle, _ = owner
    page = finish(client, client.execute(handle, {'source': 'SELECT i,i'}))
    assert [c['key'] for c in page['schema']['columns']] == ['0', '1']
    assert page['payload']['rows'] == [
        {'0': {'$integer': '9223372036854775807'}, '1': 'native'}]


def test_unknown_native_error_blocks_reuse_without_retry(owner):
    client, handle, future = owner
    future.result.side_effect = OSError('private SQL and credential material')
    token = client.execute(handle, {'source': 'INSERT INTO owned VALUES(1)'})
    page = finish(client, token)
    assert page['payload']['session_reuse_blocked']
    assert 'private' not in str(page)
    with pytest.raises(RuntimeError, match='unknown'):
        client.execute(handle, {'source': 'INSERT INTO owned VALUES(1)'})
    handle.session.execute_async.assert_called_once()


def test_close_failure_retains_owner_and_attempts_both_releases(owner):
    client, handle, _ = owner
    cluster = Mock()
    handle.cluster = cluster
    handle.session.shutdown.side_effect = OSError
    with pytest.raises(RuntimeError, match='cleanup incomplete'):
        client.close_session(handle)
    assert handle in client._sessions and not handle.closed
    cluster.shutdown.assert_called_once()
    handle.session.shutdown.side_effect = None
    client.close_session(handle)
    assert not client._sessions and handle.closed


def test_closed_owner_refuses_new_sessions(owner):
    client, _, _ = owner
    client.close()
    with pytest.raises(RuntimeError, match='closed'):
        client.open_session({'route': route()})


def test_native_exact_values_preserve_map_keys_and_collections():
    assert exact({1: 'integer', '1': 'text'}) == {
        '$map': [[1, 'integer'], ['1', 'text']]}
    assert exact(Decimal('1.00000000000000001')) == {
        '$decimal': '1.00000000000000001'}
    from cassandra.util import SortedSet
    assert exact(SortedSet(['b', 'a'])) == {'$set': ['a', 'b']}
    assert bindings([{'type': 'decimal', 'value': '1.00000000000000001'}]) == [
        Decimal('1.00000000000000001')]
    with pytest.raises(RuntimeError):
        bindings([2**63 - 1])


def test_prepared_placeholder_translation_skips_quotes_and_comments():
    source = "INSERT INTO t(\"%s\",b) VALUES(%s,'%s') -- %s\n /* %(x)s */"
    query, values = prepared_bindings(source, [7])
    assert query == source.replace('VALUES(%s,', 'VALUES(?,')
    assert values == [7]
    assert prepared_bindings('SELECT * FROM t WHERE a=%(v)s OR b=%(v)s',
                             {'v': 17}) == (
                                 'SELECT * FROM t WHERE a=? OR b=?', [17, 17])
    assert prepared_bindings(
        'INSERT INTO t(a,b) VALUES(?,?)', [
            1, 2])[1] == [
        1, 2]
    with pytest.raises(RuntimeError):
        prepared_bindings('SELECT * FROM t WHERE a=?', [1, 2])


def test_pending_future_warning_property_is_not_read(owner):
    client, handle, future = owner
    release = Event()
    result = future.result.return_value
    future.result.side_effect = lambda: result if release.wait(2) else None
    token = client.execute(handle, {'source': 'SELECT 1'})
    try:
        page = client.describe_result(token)
        assert not page['complete']
        assert page['schema']['native_observation']['warnings'] == []
    finally:
        release.set()
    finish(client, token)


def test_export_uses_ordinal_keys_with_duplicate_labels():
    from pgadmin.cdeadmin.results.renderers import export_tabular
    metadata = {'schema': {'columns': [
        {'name': 'same', 'key': '0'}, {'name': 'same', 'key': '1'}]}}
    assert export_tabular(metadata, [{'0': 'exact', '1': 'other'}], 'csv') == (
        b'same,same\r\nexact,other\r\n')
