"""Native evidence, continuity, missing observations and delivery fencing."""
from dataclasses import asdict
import threading
from types import SimpleNamespace as NS
from unittest.mock import Mock
import uuid

from flask import Flask
import pytest

from pgadmin.cdeadmin.workspace.monitoring import MonitoringPolicy, MonitoringRuntime
from pgadmin.cdeadmin.workspace.mysql_alerts import AlertRule, METRICS, MySQLAlerts, measurement
from pgadmin.cdeadmin.workspace.mysql_alert_delivery import MySQLAlertDelivery


def sample(value='2', epoch='one', available=True):
    return {'status': 'partial' if available else 'unavailable', 'transaction_completed': available,
        'source_epoch': epoch, 'identity': {'server_uuid': 'native'}, 'sample_id': str(uuid.uuid4()),
        'ended_at': '2026-10-22T12:00:00Z', 'groups': {'status': {'status': 'available', 'rows': [
            {'variable_name': 'Threads_running', 'variable_value': value}]}}}


def evaluator(**rule):
    now, sent = [0], []
    policy = MonitoringPolicy(1, 'endpoint', 'db', mysql_alert_rules=[{'id': 'r', 'metric': 'threads_running', **rule}])
    alerts = MySQLAlerts(policy, lambda _a, event, route: sent.append((event, route)), clock=lambda: now[0])
    return alerts, now, sent


def state(alerts):
    return alerts.snapshot()['rules'][0]


def test_duration_firing_resolution_and_exact_native_value_are_not_repeated():
    alerts, now, sent = evaluator(threshold='9007199254740993', duration_seconds=10, route_id='ops')
    alerts.observe(sample('9007199254740994')); assert state(alerts)['state'] == 'pending'
    now[0] = 5; alerts.observe(sample('9007199254740994')); assert not sent
    now[0] = 10; alerts.observe(sample('9007199254740994')); assert state(alerts)['state'] == 'firing'
    assert len(sent) == 1 and sent[0][0]['evidence']['value'] == '9007199254740994'
    now[0] = 15; alerts.observe(sample('9007199254740994')); assert len(sent) == 1
    now[0] = 20; alerts.observe(sample('9007199254740993'))
    assert state(alerts)['state'] == 'resolved' and len(sent) == 2 and sent[-1][0]['transition'] == 'resolved'


@pytest.mark.parametrize('break_kind', ['unavailable', 'epoch', 'identity', 'gap', 'denied', 'stale', 'truncated'])
def test_duration_does_not_bridge_missing_reset_stale_or_long_collection_gap(break_kind):
    alerts, now, sent = evaluator(duration_seconds=10, route_id='ops')
    alerts.observe(sample()); now[0] = 5
    interrupted = sample(available=break_kind != 'unavailable', epoch='two' if break_kind == 'epoch' else 'one')
    if break_kind == 'identity': interrupted['identity']['server_uuid'] = 'changed'
    if break_kind == 'gap': now[0] = 30
    if break_kind == 'denied': interrupted['groups']['status']['status'] = 'unavailable'
    if break_kind == 'stale': interrupted['groups']['status']['observation_age_seconds'] = 10
    if break_kind == 'truncated': interrupted['groups']['status']['truncated'] = True
    alerts.observe(interrupted); now[0] += 5
    alerts.observe(sample()); assert not sent and state(alerts)['state'] == 'pending'


def test_missing_unknown_does_not_resolve_firing_incident_and_missing_alert_has_own_duration():
    alerts, now, sent = evaluator(route_id='ops')
    alerts.observe(sample()); now[0] = 5; alerts.observe(sample(available=False))
    assert state(alerts)['state'] == 'unknown' and state(alerts)['active'] and len(sent) == 1
    now[0] = 10; alerts.observe(sample('0')); assert sent[-1][0]['transition'] == 'resolved'
    alerts, now, sent = evaluator(missing='alert', duration_seconds=5, route_id='ops')
    alerts.observe(sample(available=False)); now[0] = 5; alerts.observe(sample(available=False))
    assert state(alerts)['state'] == 'firing' and sent[-1][0]['evidence']['value'] is None
    assert state(alerts)['condition'] == 'missing'


def test_silence_preserves_evidence_suppresses_transitions_and_emits_once_after_expiry():
    alerts, now, sent = evaluator(route_id='ops')
    alerts.silence('r', 10); alerts.observe(sample()); assert not sent
    assert state(alerts)['state'] == 'silenced' and state(alerts)['active']
    assert alerts.snapshot()['events'][0]['delivery']['state'] == 'silenced'
    now[0] = 10; alerts.observe(sample()); assert len(sent) == 1 and sent[0][0]['transition'] == 'firing-after-silence'
    now[0] = 15; alerts.observe(sample()); assert len(sent) == 1
    alerts.silence('r', 20); assert not alerts.delivery_admitted(sent[0][0])
    alerts.close(); assert not alerts.delivery_admitted(sent[0][0])


def test_metric_gaps_and_no_configured_replication_are_not_healthy_zeroes():
    observed = sample()
    for name in METRICS:
        if name not in {'threads_running', 'collector_unavailable'}:
            assert measurement(name, observed)['status'] == 'unavailable', name
    for name in ('replication', 'alert_replication_workers', 'alert_replication_appliers', 'alert_replication_coordinators'):
        observed['groups'][name] = {'status': 'available', 'rows': []}
    assert measurement('replication_errors', observed)['reason'] == 'no-observed-replication-channel'
    observed['rates'] = {'status': 'unavailable', 'reason': 'server-or-status-reset'}
    assert measurement('slow_queries_per_second', observed)['reason'] == 'server-or-status-reset'
    observed['rates'] = {'status': 'available', 'per_second': {'Created_tmp_tables': '0', 'Created_tmp_disk_tables': '0'}}
    assert measurement('temp_disk_percent', observed)['value'] is None


def test_replication_coordinator_errors_and_partial_coverage():
    observed = sample()
    for name, rows in {'replication': [{'channel_name': 'c', 'service_state': 'ON', 'last_error_number': '0'}],
            'alert_replication_workers': [], 'alert_replication_appliers': [{'channel_name': 'c', 'service_state': 'OFF'}],
            'alert_replication_coordinators': [{'channel_name': 'c', 'last_error_number': '1236'}]}.items():
        observed['groups'][name] = {'status': 'available', 'rows': rows}
    assert measurement('replication_errors', observed)['value'] == '1'
    assert measurement('replication_stopped', observed)['value'] == '1'
    observed['groups']['alert_replication_coordinators']['truncated'] = True
    assert measurement('replication_errors', observed)['value'] is None


@pytest.mark.parametrize('change', [{'threshold': 'NaN'}, {'threshold': True}, {'duration_seconds': True},
    {'duration_seconds': 86401}, {'metric': 'enterprise_masking'}, {'missing': 'healthy'}, {'route_id': None}])
def test_rule_admission_rejects_invalid_or_unsupported_semantics(change):
    with pytest.raises((ValueError, TypeError)):
        evaluator(**change)


def test_policy_copies_rules_and_bounds_duplicate_identities():
    source = [{'id': 'r', 'metric': 'threads_running'}]
    policy = MonitoringPolicy(1, 'endpoint', 'db', mysql_alert_rules=source)
    source[0]['metric'] = 'other'
    assert asdict(policy)['mysql_alert_rules'][0]['metric'] == 'threads_running'
    with pytest.raises(ValueError): MonitoringPolicy(1, 'endpoint', 'db', mysql_alert_rules=source * 33)
    with pytest.raises(ValueError): MonitoringPolicy(1, 'endpoint', 'db', mysql_alert_rules=[{'id': 'r', 'metric': 'threads_running'}] * 2)


def test_runtime_uses_observer_without_any_viewer_and_revocation_discards_late_samples():
    published = threading.Event()
    policy = MonitoringPolicy(1, 'endpoint', 'db', mysql_alert_rules=[{'id': 'r', 'metric': 'threads_running'}])
    observer = MySQLAlerts(policy, lambda *_: None)
    original = observer.observe
    def observe(value, **kwargs):
        result = original(value, **kwargs); published.set(); return result
    observer.observe = observe
    source = Mock(sample=lambda: sample())
    runtime = MonitoringRuntime()
    try:
        runtime.enable(policy, lambda _: source, lambda *_: True, observation_factory=lambda: observer)
        assert published.wait(2)
        current = runtime.snapshot(policy, lambda *_: True)
        assert current['alerts']['rules'][0]['state'] == 'firing'
        assert current['samples'][0]['findings'][0]['code'] == 'mysql-threads_running'
        with pytest.raises(PermissionError): runtime.silence(policy, lambda *_: False, 'r', 60)
        assert runtime.silence(policy, lambda *_: True, 'r', 60)['rules'][0]['state'] == 'silenced'
    finally: assert runtime.close()
    assert observer.closed


def test_sustained_outage_duration_survives_scheduled_failure_backoff():
    from pgadmin.cdeadmin.workspace.monitoring import _Job
    now, delivered = [0], []
    policy = MonitoringPolicy(1, 'endpoint', 'db', mysql_alert_rules=[{
        'id': 'outage', 'metric': 'collector_unavailable', 'duration_seconds': 30, 'route_id': 'ops'}])
    alerts = MySQLAlerts(policy, lambda *args: delivered.append(args), clock=lambda: now[0])
    source = Mock(sample=Mock(side_effect=ConnectionError('private server detail')))
    job = _Job(policy, lambda _: source, lambda *_: True, lambda: now[0], observation_factory=lambda: alerts)
    class Scheduler:
        count = 0
        stopped = False
        def is_set(self): return self.stopped
        def set(self): self.stopped = True
        def wait(self, seconds):
            now[0] += seconds; self.count += 1
            if self.count == 4: self.set()
    job.stop = Scheduler(); job.run()
    assert len(delivered) == 1
    event = delivered[0][1]
    assert event['transition'] == 'firing' and event['evidence']['value'] == '1'
    assert event['duration_seconds'] == 30 and now[0] == 150
    assert 'private server detail' not in str(alerts.snapshot())


@pytest.mark.parametrize('mode', ['success', 'denied', 'changed', 'silenced', 'unknown'])
def test_delivery_rechecks_live_grant_route_and_silence_without_retry(mode, monkeypatch):
    app = Flask(__name__)
    delivery = MySQLAlertDelivery(app)
    policy = MonitoringPolicy(1, str(uuid.uuid4()), 'db', mysql_alert_rules=[{'id': 'r', 'metric': 'threads_running', 'route_id': 'ops'}])
    alerts = MySQLAlerts(policy, lambda *_: None)
    alerts.observe(sample()); event = alerts.events[-1]
    grant = NS(policy=policy, require=Mock(return_value=True))
    service = Mock()
    service.deliver.return_value = {'state': 'delivered', 'occurrence_id': 'receipt', 'error_type': None, 'completed_at': 'now'}
    monkeypatch.setattr(delivery, '_route', lambda *_: (service, {'profile_id': 'smtp'}, {'recipients': ['ops@localhost']}, 'changed' if mode == 'changed' else 'digest'))
    if mode == 'denied': grant.require.side_effect = PermissionError('private')
    if mode == 'silenced': alerts.silence('r', 60)
    if mode == 'unknown': service.deliver.side_effect = OSError('private transport secret')
    try:
        delivery.submit(alerts, event, 'ops', grant, 'digest')
        delivery.queue.join()
        status = alerts.snapshot()['events'][-1]['delivery']
        assert status['state'] == {'success': 'delivered', 'denied': 'failed', 'changed': 'failed', 'silenced': 'suppressed', 'unknown': 'outcome_unknown'}[mode]
        assert service.deliver.call_count == (1 if mode in {'success', 'unknown'} else 0)
        assert 'private' not in str(status) and 'recipients' not in str(status)
    finally: assert delivery.close()


def test_routes_are_owner_scoped_allowlisted_and_secret_free(monkeypatch):
    from pgadmin.cdeadmin.report_delivery import DeliveryProfileRegistry
    app = Flask(__name__)
    app.config['CDEADMIN_MYSQL_ALERT_ROUTES'] = {'ops': {'owner_ids': [1], 'profile_id': 'smtp', 'target': {'recipients': ['ops@localhost']}}}
    registry = DeliveryProfileRegistry({'smtp': {'kind': 'smtp', 'host': 'private-host', 'username': 'private-user',
        'password': 'private-password', 'sender': 'sender@localhost', 'allowed_recipients': ['ops@localhost']}})
    monkeypatch.setattr('pgadmin.cdeadmin.report_delivery.init_app', lambda _: NS(profiles=registry))
    delivery = MySQLAlertDelivery(app)
    assert delivery.catalog(1) == [{'id': 'ops', 'label': 'ops'}]
    assert not delivery.catalog(2)
    app.config['CDEADMIN_MYSQL_ALERT_ROUTES']['ops']['target'] = {'recipients': ['not-allowed@localhost']}
    assert not delivery.catalog(1)
