"""Lease-scoped MySQL rules and transitions, driven only by collector samples."""
import copy
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import re
import threading
import time
import uuid


# Sources describe measurements, not a claim of complete instance visibility.
METRICS = {
    'threads_running': ('Running threads', 'threads', 'performance_schema.global_status', 'Inspect current activity and workload waits.'),
    'connection_usage_percent': ('Connection utilization', '%', 'global_status / @@max_connections', 'Inspect connections and native max_connections before changing capacity.'),
    'oldest_transaction_seconds': ('Oldest InnoDB transaction', 'seconds', 'information_schema.innodb_trx', 'Inspect active transactions and lock owners before ending a session.'),
    'lock_waits': ('InnoDB lock waits', 'waits', 'performance_schema.data_lock_waits', 'Inspect native lock wait dependencies and blocking transactions.'),
    'aborted_connects_per_second': ('Aborted connections', '/second', 'global_status.Aborted_connects interval', 'Inspect connection authentication, TLS and server diagnostics.'),
    'slow_queries_per_second': ('Slow queries', '/second', 'global_status.Slow_queries interval', 'Open workload analysis and inspect slow-log coverage and long_query_time.'),
    'temp_disk_percent': ('Disk temporary tables', '% of created temporary tables', 'global_status.Created_tmp_disk_tables / Created_tmp_tables interval', 'Inspect digest temporary work and execution plans; this counter does not cover all TempTable overflow.'),
    'buffer_pool_miss_percent': ('Buffer pool reads', '% of read requests', 'global_status.Innodb_buffer_pool_reads / Innodb_buffer_pool_read_requests interval', 'Inspect I/O waits and buffer pool configuration alongside workload.'),
        'replication_errors': ('Replication errors', 'receivers / coordinators / workers with last error', 'replication_connection_status + replication_applier_status_by_coordinator / by_worker', 'Inspect native replication channel and applier error numbers before repair.'),
    'replication_stopped': ('Stopped replication services', 'receivers / appliers', 'replication_connection_status + replication_applier_status', 'Inspect the configured channels; intentional stopped channels can be silenced.'),
    'collector_unavailable': ('Collector unavailable', '0 or 1', 'owned collector probe outcome', 'Inspect collector authentication, native errors and endpoint reachability.'),
}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        return None
    try:
        if len(str(value)) > 100:
            return None
        result = Decimal(value)
        return result if result.is_finite() and result >= 0 and result <= Decimal('1e30') else None
    except InvalidOperation:
        return None


@dataclass(frozen=True)
class AlertRule:
    id: str
    metric: str
    threshold: str = '0'
    duration_seconds: int = 0
    missing: str = 'unknown'
    severity: str = 'warning'
    route_id: str = ''

    def __post_init__(self):
        if (not isinstance(self.id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', self.id) or
                self.metric not in METRICS or self.missing not in {'unknown', 'alert'} or
                self.severity not in {'warning', 'critical'} or type(self.duration_seconds) is not int or
                not 0 <= self.duration_seconds <= 86400 or not isinstance(self.route_id, str) or
                len(self.route_id) > 128 or number(self.threshold) is None):
            raise ValueError('Invalid MySQL alert rule')
        object.__setattr__(self, 'threshold', format(number(self.threshold), 'f'))


def rules(value):
    if not isinstance(value, (tuple, list)) or len(value) > 32:
        raise ValueError('MySQL alerts require at most 32 rules')
    result = tuple(item if isinstance(item, AlertRule) else AlertRule(**item) for item in value)
    if len({item.id for item in result}) != len(result):
        raise ValueError('Duplicate MySQL alert rule identity')
    return result


def measurement(metric, sample):
    """Return a bounded evidence record. Absent/denied/reset never means zero."""
    evidence = {'metric': metric, 'scope': 'server', 'source': METRICS[metric][2],
        'sample_id': sample.get('sample_id'), 'observed_at': sample.get('ended_at'),
        'source_epoch': sample.get('source_epoch'),
        'server_uuid': sample.get('identity', {}).get('server_uuid'),
        'visibility': 'native-permission-and-instrumentation-scope',
        'value': None, 'status': 'unavailable', 'reason': 'native-observation-unavailable'}
    def present(value, **extra):
        value = number(value)
        return {**evidence, **extra, 'value': format(value, 'f'), 'status': 'available', 'reason': None} if value is not None else evidence
    if metric == 'collector_unavailable':
        return present('1' if sample.get('status') == 'unavailable' else '0')
    if (sample.get('status') not in {'available', 'partial'} or not sample.get('transaction_completed') or
            not evidence['source_epoch'] or not evidence['server_uuid']):
        return evidence
    groups = sample.get('groups', {})
    def rows(name):
        group = groups.get(name, {})
        if group.get('status') != 'available' or group.get('truncated') or group.get('observation_age_seconds', 0) != 0:
            return None
        return group.get('rows', [])
    status = rows('status')
    status = {row.get('variable_name'): row.get('variable_value') for row in status} if status is not None else {}
    if metric == 'threads_running':
        return present(status.get('Threads_running'))
    if metric == 'connection_usage_percent':
        limits = rows('alert_capacity')
        connected, maximum = number(status.get('Threads_connected')), number((limits or [{}])[0].get('max_connections'))
        if connected is not None and maximum:
            with localcontext() as context:
                context.prec = 64
                return present(connected * 100 / maximum, native={'Threads_connected': str(connected), 'max_connections': str(maximum)})
    elif metric in {'oldest_transaction_seconds', 'lock_waits'}:
        native = rows('alert_transactions' if metric == 'oldest_transaction_seconds' else 'alert_locks')
        if native:
            return present(native[0].get('value'))
    elif metric.startswith('replication_'):
        receiver = rows('replication')
        worker = rows('alert_replication_workers')
        coordinator = rows('alert_replication_coordinators')
        applier = rows('alert_replication_appliers')
        if receiver is None or worker is None or applier is None or coordinator is None:
            return evidence
        if not receiver or not applier:
            return {**evidence, 'reason': 'no-observed-replication-channel'}
        selected = receiver + (worker + coordinator if metric == 'replication_errors' else applier)
        field = 'last_error_number' if metric == 'replication_errors' else 'service_state'
        if any((number(row.get(field)) is None if metric == 'replication_errors' else row.get(field) not in {'ON', 'OFF', 'CONNECTING'}) for row in selected):
            return evidence
        affected = [row for row in selected if (number(row[field]) > 0 if metric == 'replication_errors' else row[field] == 'OFF')]
        return present(len(affected), native={'channels': [{key: row[key] for key in ('channel_name', 'worker_id', field) if key in row} for row in selected]})
    else:
        rates = sample.get('rates', {})
        if rates.get('status') != 'available':
            return {**evidence, 'reason': rates.get('reason', 'counter-baseline-unavailable')}
        values = rates.get('per_second', {})
        rate = {'aborted_connects_per_second': 'Aborted_connects', 'slow_queries_per_second': 'Slow_queries'}.get(metric)
        if rate:
            return present(values.get(rate), interval_seconds=rates.get('elapsed_seconds'))
        numerator, denominator = {'temp_disk_percent': ('Created_tmp_disk_tables', 'Created_tmp_tables'),
            'buffer_pool_miss_percent': ('Innodb_buffer_pool_reads', 'Innodb_buffer_pool_read_requests')}[metric]
        top, bottom = number(values.get(numerator)), number(values.get(denominator))
        if top is not None and bottom:
            with localcontext() as context:
                context.prec = 64
                return present(top * 100 / bottom, interval_seconds=rates.get('elapsed_seconds'), native={numerator: str(top), denominator: str(bottom)})
        return {**evidence, 'reason': 'counter-gap-or-no-denominator-activity'}
    return evidence


class MySQLAlerts:
    """One policy revision. Silence suppresses delivery, never changes evidence.

    Volatile state is bounded and follows the collector grant/lease. Transport
    attempts use the application's durable delivery service, not history storage.
    """
    def __init__(self, policy, submit, *, clock=time.monotonic):
        self.policy, self.submit, self.clock = policy, submit, clock
        self.lock = threading.RLock()
        self.states = {rule.id: {'rule': asdict(rule), 'state': 'unknown', 'condition': 'unknown',
            'active': False, 'since': None, 'silenced_until': None, 'evidence': None} for rule in policy.mysql_alert_rules}
        self.events = deque(maxlen=100)
        self.epoch = None
        self.last_clock = None
        self.closed = False

    def snapshot(self):
        with self.lock:
            return copy.deepcopy({'storage': 'volatile-policy-lease', 'rules': list(self.states.values()),
                'events': list(self.events), 'automatic_retry': False, 'event_limit': 100})

    def _event(self, item, transition):
        event = {'event_id': str(uuid.uuid4()), 'rule_id': item['rule']['id'],
            'transition': transition, 'severity': item['rule']['severity'],
            'threshold': item['rule']['threshold'], 'duration_seconds': item['rule']['duration_seconds'],
            'evidence': copy.deepcopy(item['evidence']), 'created_at': datetime.now(timezone.utc).isoformat(),
            'action': METRICS[item['rule']['metric']][3], 'delivery': {'state': 'not-configured'}}
        self.events.append(event)
        route = item['rule']['route_id']
        if item['silenced_until'] is not None:
            event['delivery'] = {'state': 'silenced'}
        elif route:
            event['delivery'] = {'state': 'queued'}
            self.submit(self, event, route)

    def observe(self, sample, *, maximum_gap_seconds=None):
        with self.lock:
            now = self.clock()
            epoch = (sample.get('source_epoch'), sample.get('identity', {}).get('server_uuid'))
            gap = self.policy.interval_seconds * 3 if maximum_gap_seconds is None else maximum_gap_seconds
            contiguous = self.last_clock is not None and 0 <= now - self.last_clock <= gap and epoch == self.epoch
            self.epoch, self.last_clock = epoch, now
            for rule in self.policy.mysql_alert_rules:
                item = self.states[rule.id]
                was_silenced = item['silenced_until'] is not None
                if was_silenced and now >= item['silenced_until']:
                    item['silenced_until'] = None
                evidence = measurement(rule.metric, sample)
                item['evidence'] = evidence
                missing = evidence['status'] != 'available'
                condition = 'missing' if missing else 'threshold'
                # Missing data can have its own firing condition if admitted.
                breached = rule.missing == 'alert' if missing else number(evidence['value']) > number(rule.threshold)
                if not contiguous or item['condition'] != condition:
                    item['since'] = None
                item['condition'] = condition
                if missing and rule.missing == 'unknown':
                    item.update(state='unknown', since=None)
                elif not breached:
                    if item['active']:
                        item['active'] = False
                        self._event(item, 'resolved')
                    item.update(state='resolved', since=None)
                else:
                    if item['since'] is None:
                        item['since'] = now
                    firing = now - item['since'] >= rule.duration_seconds
                    item['state'] = 'firing' if firing else 'pending'
                    if firing and not item['active']:
                        item['active'] = True
                        self._event(item, 'firing')
                    elif firing and was_silenced and item['silenced_until'] is None:
                        self._event(item, 'firing-after-silence')
                if item['silenced_until'] is not None:
                    item['state'] = 'silenced'
                item['breach_seconds'] = max(0, now - item['since']) if item['since'] is not None else 0
                item['silence_remaining_seconds'] = max(0, item['silenced_until'] - now) if item['silenced_until'] is not None else 0
            return [{**copy.deepcopy(item), 'code': 'mysql-' + item['rule']['metric'], 'action': METRICS[item['rule']['metric']][3]}
                for item in self.states.values() if item['state'] in {'firing', 'silenced', 'unknown'}]

    def silence(self, rule_id, seconds):
        if type(seconds) is not int or not 0 <= seconds <= 86400 or rule_id not in self.states:
            raise ValueError('Invalid MySQL alert silence')
        with self.lock:
            item = self.states[rule_id]
            # Unsilencing is evaluated at the next collector observation.
            item['silenced_until'] = self.clock() + seconds
            item['state'] = 'silenced'
            return self.snapshot()

    def delivery_admitted(self, event):
        with self.lock:
            return not self.closed and self.states[event['rule_id']]['silenced_until'] is None

    def receipt(self, event, value):
        with self.lock:
            event['delivery'] = copy.deepcopy(value)

    def close(self):
        with self.lock:
            self.closed = True
