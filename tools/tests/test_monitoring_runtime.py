"""Background sampling without viewers, coalescing and authorization fencing."""

import threading
from unittest.mock import Mock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.workspace.monitoring import (
    MonitoringPolicy, MonitoringRuntime,
)


def policy(**overrides):
    return MonitoringPolicy(**{'owner_id': 1, 'endpoint_id': 'endpoint',
                               'target_id': 'database', **overrides})


def test_collection_runs_without_viewers_and_duplicate_enable_coalesces():
    sampled = threading.Event()
    count = 0

    def sample():
        nonlocal count
        count += 1
        if count == 2:
            sampled.set()
        return {'status': 'available', 'sample_id': str(count)}

    source = Mock(sample=sample)
    factory = Mock(return_value=source)
    authorization = Mock(return_value=True)
    runtime = MonitoringRuntime()
    config = policy(retain_samples=1)
    try:
        revision = runtime.enable(config, factory, authorization)
        assert runtime.enable(config, factory, authorization) == revision
        assert sampled.wait(8), 'Policy did not collect without a viewer'
        snapshot = runtime.snapshot(config, authorization)
        assert len(snapshot['samples']) == 1
        assert snapshot['retention_evictions'] == 1
        snapshot['samples'].clear()
        assert runtime.snapshot(config, authorization)['samples']
        factory.assert_called_once_with(config)
        assert count == 2
    finally:
        assert runtime.close()
    source.close.assert_called_once()


def test_view_cannot_create_job_or_authorize_collection():
    runtime = MonitoringRuntime()
    denied = Mock(return_value=False)
    with pytest.raises(PermissionError):
        runtime.snapshot(policy(), denied)
    assert runtime.snapshot(policy(), lambda *_: True)['state'] == 'disabled'
    assert runtime._jobs == {}
    with pytest.raises(PermissionError):
        runtime.enable(policy(), Mock(), denied)
    runtime.close()


def test_revoked_collection_does_not_open_source_and_cannot_implicitly_restart():
    factory = Mock()
    runtime = MonitoringRuntime()
    config = policy()
    authorize = lambda _, purpose: purpose != 'collect'
    runtime.enable(config, factory, authorize)
    job = runtime._jobs[config.key]
    job.thread.join(timeout=1)
    assert not job.thread.is_alive()
    assert runtime.snapshot(config, authorize)['state'] == 'authorization-denied'
    factory.assert_not_called()
    with pytest.raises(ValueError, match='previous policy'):
        runtime.enable(config, factory, authorize)
    assert runtime.disable(config, authorize)
    assert runtime.close()


def test_expiring_policy_closes_source_and_discards_late_observation():
    now = [0]
    source = Mock()

    def sample():
        now[0] = 6
        return {'status': 'available', 'sample_id': 'one'}

    source.sample = sample
    runtime = MonitoringRuntime(clock=lambda: now[0])
    config = policy(lease_seconds=5)
    runtime.enable(config, lambda _: source, lambda *_: True)
    runtime._jobs[config.key].thread.join(timeout=1)
    snapshot = runtime.snapshot(config, lambda *_: True)
    assert snapshot['state'] == 'expired'
    assert snapshot['history'] == 'volatile'
    assert snapshot['samples'] == []
    source.close.assert_called_once()
    assert runtime.close()


def test_revocation_during_native_read_discards_inflight_values():
    entered, finish = threading.Event(), threading.Event()
    allowed = [True]
    source = Mock()

    def sample():
        entered.set()
        assert finish.wait(2)
        return {'status': 'available', 'private': 'inflight-value'}

    source.sample = sample
    runtime = MonitoringRuntime()
    config = policy()
    authorize = lambda _, purpose: purpose != 'collect' or allowed[0]
    runtime.enable(config, lambda _: source, authorize)
    assert entered.wait(1)
    allowed[0] = False
    finish.set()
    runtime._jobs[config.key].thread.join(timeout=2)
    snapshot = runtime.snapshot(config, authorize)
    assert snapshot['state'] == 'authorization-denied'
    assert snapshot['samples'] == []
    source.close.assert_called_once()
    assert runtime.close()


def test_unconfirmed_cleanup_retains_source_and_blocks_replacement():
    sampled = threading.Event()
    source = Mock()
    source.sample.side_effect = lambda: (sampled.set() or {'status': 'available'})
    source.close.side_effect = RuntimeError('sensitive native error')
    runtime = MonitoringRuntime()
    config = policy()
    runtime.enable(config, lambda _: source, lambda *_: True)
    assert sampled.wait(1)
    assert runtime.disable(config, lambda *_: True) is False
    status = runtime.snapshot(config, lambda *_: True)
    assert status['state'] == 'release-unconfirmed'
    assert 'sensitive' not in str(status)
    with pytest.raises(ValueError):
        runtime.enable(config, lambda _: source, lambda *_: True)
    source.close.side_effect = None
    assert runtime.disable(config, lambda *_: True)
    assert runtime.close()


@pytest.mark.parametrize('options', [
    {'owner_id': True}, {'interval_seconds': 0}, {'retain_samples': 0},
    {'target_id': None, 'interval_seconds': 5}, {'lease_seconds': 9999999},
])
def test_policy_rejects_unbounded_or_too_frequent_work(options):
    with pytest.raises(ValueError):
        policy(**options)


@pytest.mark.parametrize('refresh,status', [
    ({'status': 'completed'}, 'partial'),
    ({'status': 'completed'}, 'available'),
    ({'status': 'completed'}, 'unavailable'),
    ({'status': 'failed'}, 'available'),
    ({}, 'available'),
])
def test_heartbeat_requires_completed_refresh_and_exposes_overdue(refresh, status):
    now = [0]
    sampled = threading.Event()
    source = Mock()
    source.sample.side_effect = lambda: (sampled.set() or {
        'status': status, 'scope': 'database', 'transaction_refresh': refresh})
    runtime = MonitoringRuntime(clock=lambda: now[0])
    config = policy(heartbeat_enabled=True, heartbeat_timeout_seconds=10)
    runtime.enable(config, lambda _: source, lambda *_: True)
    assert sampled.wait(1)
    job = runtime._jobs[config.key]
    # Wait for publication under the job lock, not just the source callback.
    for _ in range(100):
        if runtime.snapshot(config, lambda *_: True)['samples']:
            break
        threading.Event().wait(0.01)
    heartbeat = runtime.snapshot(config, lambda *_: True)['heartbeat']
    observed = refresh.get('status') == 'completed' and status != 'unavailable'
    assert heartbeat['status'] == ('observed' if observed else 'unknown')
    now[0] = 11
    heartbeat = runtime.snapshot(config, lambda *_: True)['heartbeat']
    assert heartbeat['status'] == ('overdue' if observed else 'unknown')
    assert runtime.close()
    assert job.snapshot()['heartbeat']['status'] == 'stopped'


def test_heartbeat_is_disabled_unless_explicitly_admitted():
    runtime = MonitoringRuntime(clock=lambda: 0)
    config = policy()
    source = Mock(sample=Mock(return_value={
        'status': 'available', 'scope': 'database',
        'transaction_refresh': {'status': 'completed'}}))
    runtime.enable(config, lambda _: source, lambda *_: True)
    assert runtime.snapshot(config, lambda *_: True)['heartbeat']['status'] == 'disabled'
    assert runtime.close()


def test_sample_age_uses_monotonic_time_without_enabling_heartbeat():
    now = [100]
    sampled = threading.Event()
    source = Mock(sample=lambda: {'status': 'available'})
    runtime = MonitoringRuntime(clock=lambda: now[0])
    config = policy()
    try:
        runtime.enable(config, lambda _: source, lambda *_: True)
        job = runtime._jobs[config.key]
        # Synchronize on publication, not merely entry to the native call.
        import time
        deadline = time.monotonic() + 1
        while not runtime.snapshot(config, lambda *_: True)['samples']:
            assert time.monotonic() < deadline
            sampled.wait(0.001)
        now[0] = 120
        result = runtime.snapshot(config, lambda *_: True)
        assert result['samples'][0]['runtime_elapsed_seconds'] == 0
        assert result['sample_age_seconds'] == 20
        assert result['stale_after_seconds'] == 15
        assert result['heartbeat']['status'] == 'disabled'
        assert job.last_sample_clock == 100
    finally:
        assert runtime.close()


def test_statement_inspection_requires_latest_identity_and_rechecks_after_read():
    from pgadmin.cdeadmin.workspace.monitoring import _Job
    config = policy(); authorization = Mock(return_value=True)
    runtime = MonitoringRuntime(clock=lambda: 10)
    job = _Job(config, Mock(), authorization, lambda: 10)
    reference = {'statement_id': '1', 'attachment_id': '2', 'compiled_statement_id': '3', 'timestamp': 't'}
    job.samples.append({'sample_id': 's', 'source_epoch': 'epoch', 'groups': {'statement_details': {
        'status': 'available', 'values': {'rows': [reference]}}}})
    job.source = Mock(inspect_statement=Mock(return_value={'status': 'available', 'sql_text': {'value': 'SELECT secret'}}))
    runtime._jobs[config.key] = job
    assert runtime.inspect_statement(config, authorization, {**reference, 'sample_id': 'old'})['status'] == 'changed'
    job.source.inspect_statement.assert_not_called()
    assert runtime.inspect_statement(config, authorization, {**reference, 'sample_id': 's'})['status'] == 'available'
    def revoke(_):
        job.stop.set()
        return {'status': 'available', 'sql_text': {'value': 'must not publish'}}
    job.source.inspect_statement.side_effect = revoke
    with pytest.raises(PermissionError):
        runtime.inspect_statement(config, authorization, {**reference, 'sample_id': 's'})
    runtime._jobs.clear()
    runtime.close()


def test_detail_inspection_reauthorizes_after_io_and_refuses_wrong_scope():
    from pgadmin.cdeadmin.workspace.monitoring import _Job
    config = policy(); authorization = Mock(return_value=True)
    runtime = MonitoringRuntime(clock=lambda: 10)
    job = _Job(config, Mock(), authorization, lambda: 10)
    job.samples.append({'sample_id': 's', 'source_epoch': 'epoch', 'status': 'available'})
    job.source = Mock(inspect_details=Mock(return_value={'status': 'available'}))
    runtime._jobs[config.key] = job
    assert runtime.inspect_details(config, authorization, {'sample_id': 'old', 'operation': 'accounts'})['status'] == 'changed'
    job.source.inspect_details.assert_not_called()
    assert runtime.inspect_details(config, authorization, {'sample_id': 's', 'operation': 'accounts'})['status'] == 'available'
    with pytest.raises(ValueError):
        runtime.inspect_details(config, authorization, {'sample_id': 's', 'operation': 'server-log'})
    def revoke(*_):
        job.stop.set()
        return {'status': 'available', 'rows': ['must not publish']}
    job.source.inspect_details.side_effect = revoke
    with pytest.raises(PermissionError):
        runtime.inspect_details(config, authorization, {'sample_id': 's', 'operation': 'accounts'})
    runtime._jobs.clear()


def test_independent_detail_read_tolerates_view_refresh_race_but_not_reconnect():
    from pgadmin.cdeadmin.workspace.monitoring import _Job
    config = policy(); authorization = Mock(return_value=True)
    runtime = MonitoringRuntime(clock=lambda: 10)
    job = _Job(config, Mock(), authorization, lambda: 10)
    job.source = Mock(inspect_details=Mock(return_value={'status': 'available'}))
    runtime._jobs[config.key] = job
    for identifier in ('old', 'new'):
        job.samples.append({'sample_id': identifier, 'source_epoch': 'epoch', 'status': 'available'})
    assert runtime.inspect_details(config, authorization, {'sample_id': 'old', 'operation': 'accounts'})['status'] == 'available'
    job.samples.append({'sample_id': 'reconnected', 'source_epoch': 'another', 'status': 'available'})
    assert runtime.inspect_details(config, authorization, {'sample_id': 'old', 'operation': 'accounts'})['status'] == 'changed'
    runtime._jobs.clear()
