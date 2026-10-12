"""CockroachDB ownership, ambiguous decisions and pool isolation."""
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from test_cdeadmin_distributed_providers import COCKROACHDB  # bootstrap
from pgadmin.cdeadmin.sdk.relational import RelationalClientConfig
from pgadmin.cdeadmin.providers.pgwire_driver import (
    RetainedPGWireClient as CockroachDBClient,
    PGWireExecution as CockroachExecution, PoolConnector, PoolLease,
    exact_parameters,
)

DRIVER = 'pgadmin.cdeadmin.providers.pgwire_driver'


@pytest.fixture
def owner():
    config = RelationalClientConfig(
        profile=COCKROACHDB, module_name='psycopg', version_query='SELECT 1',
        version_parser=lambda row: '26.1.3', connect_arguments=lambda r: r,
        metadata_reader=lambda *_: [], security_reader=lambda *_: {})
    client = CockroachDBClient(config, 'owned', module=Mock())
    handle = Mock(closed=False)
    handle.info.transaction_status.name = 'IDLE'
    client._connections.append(handle)
    client._states[id(handle)] = {}
    # Mock must not invent the pool lease attribute used by native().
    del handle._connection
    yield client, handle
    client.close()


def finish(client, token):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        page = client.describe_result(token)
        if page['complete']:
            return page['payload']
    raise AssertionError('worker did not finish')


@pytest.mark.parametrize('code,blocked,retry', [
    ('40001', False, True), ('40003', True, False),
    ('08006', True, False), (None, True, False), ('42601', False, False)])
def test_native_error_is_not_replayed_or_disclosed(
        owner, code, blocked, retry):
    client, handle = owner
    error = Exception('private query and credentials')
    error.sqlstate = code
    with patch(DRIVER + '.result_pages', side_effect=error) as run:
        token = client.execute(handle, {'source': 'SELECT 1'})
        payload = finish(client, token)
    assert run.call_count == 1
    assert payload['session_reuse_blocked'] is blocked
    assert payload['error']['transaction_retry_required'] is retry
    assert 'private' not in str(payload)
    if blocked:
        with pytest.raises(RuntimeError, match='unknown'):
            client.execute(handle, {'source': 'SELECT 2'})


def test_execution_remains_exclusive_until_observed(owner):
    client, handle = owner
    with patch(DRIVER + '.result_pages', return_value=iter([])):
        token = client.execute(handle, {'source': 'SELECT 1'})
        token.worker.join(2)
        for action in [lambda: client.execute(handle, {'source': 'SELECT 2'}),
                       lambda: client.control_transaction(handle, 'commit'),
                       lambda: client.list_resources(
                           {'_provider_session_handle': handle})]:
            with pytest.raises(RuntimeError, match='execution is active'):
                action()
        finish(client, token)
    with patch(DRIVER + '.control', return_value=(True, 'ROLLBACK')):
        client.control_transaction(handle, 'commit')
    assert client.describe_transaction(handle)['command_status'] == 'ROLLBACK'


def test_failed_start_does_not_strand_owner(owner):
    client, handle = owner
    with patch.object(CockroachExecution, 'start', side_effect=RuntimeError):
        with pytest.raises(RuntimeError, match='could not start'):
            client.execute(handle, {'source': 'SELECT 1'})
    assert not client._executions


def test_unknown_decision_is_quarantined(owner):
    client, handle = owner
    with patch(DRIVER + '.control', side_effect=OSError) as run:
        with pytest.raises(RuntimeError, match='command failed'):
            client.control_transaction(handle, 'commit')
        with pytest.raises(RuntimeError, match='unknown'):
            client.control_transaction(handle, 'commit')
    assert run.call_count == 1
    assert client.describe_transaction(handle)['outcome_unknown']


def test_rollback_clears_prior_retry_observation(owner):
    client, handle = owner
    error = Exception()
    error.sqlstate = '40001'
    with patch(DRIVER + '.control', side_effect=error):
        with pytest.raises(RuntimeError):
            client.control_transaction(handle, 'commit')
    with patch(DRIVER + '.control', return_value=(True, 'ROLLBACK')):
        client.control_transaction(handle, 'rollback')
    assert 'sqlstate' not in client.describe_transaction(handle)


def test_pool_return_failure_retains_ownership(owner):
    client, raw = owner
    pool = Mock()
    pool.putconn.side_effect = OSError
    lease = PoolLease(pool, raw)
    client._connections[:] = [lease]
    client._states = {id(lease): {}}
    with pytest.raises(RuntimeError, match='release failed'):
        client.close_session(lease)
    assert lease in client._connections and not lease._closed
    pool.putconn.side_effect = None
    client.close_session(lease)
    assert not client._connections and lease._closed


def test_pool_reset_discards_server_state_and_returns_once():
    raw, pool = Mock(closed=False), Mock()
    lease = PoolLease(pool, raw)
    lease.close()
    lease.close()
    raw.execute.assert_called_once_with('DISCARD ALL')
    pool.putconn.assert_called_once_with(raw)
    assert raw.autocommit is False and raw.isolation_level is None


def test_failed_pool_reset_drops_connection():
    raw, pool = Mock(closed=False), Mock()
    raw.execute.side_effect = OSError
    PoolLease(pool, raw).close()
    raw.close.assert_called_once()
    pool.putconn.assert_called_once_with(raw)


def test_pool_key_includes_credentials_tls_policy_and_route():
    module = Mock()
    factory = Mock()
    connector = PoolConnector(module, 'owned',
                              SimpleNamespace(ConnectionPool=factory))
    route = dict(pool_enabled=True, cde_route_id='same', host='localhost',
                 user='owned', password='secret-a', sslmode='verify-full')
    connector(**route)
    connector(**route)
    for changed in [dict(password='secret-b'), dict(sslmode='require'),
                    dict(pool_max_size=3), dict(dbname='other')]:
        connector(**dict(route, **changed))
    assert factory.call_count == 5
    assert all('secret-' not in key for key in connector._pools)
    connector.close()


@pytest.mark.parametrize('value', [2**53, float('inf'), float('nan')])
def test_unsafe_json_scalars_require_exact_envelopes(value):
    with pytest.raises(RuntimeError):
        exact_parameters([value])


def test_cancel_transport_error_awaits_original_query(owner):
    client, handle = owner
    error = Exception('private native text')
    error.sqlstate = '57014'
    handle.cancel_safe.side_effect = OSError('SSL EOF')
    from threading import Event
    release = Event()

    def cancelled(*_):
        assert release.wait(2)
        raise error

    with patch(DRIVER + '.result_pages', side_effect=cancelled):
        token = client.execute(handle, {'source': 'SELECT pg_sleep(20)'})
        assert client.cancel(token) is False
        with pytest.raises(RuntimeError, match='execution is active'):
            client.control_transaction(handle, 'commit')
        release.set()
        payload = finish(client, token)
    assert payload['cancel_transport_error_type'] == 'OSError'
    assert payload['error']['sqlstate'] == '57014'
    assert not payload['session_reuse_blocked']
    assert 'SSL EOF' not in str(payload)
