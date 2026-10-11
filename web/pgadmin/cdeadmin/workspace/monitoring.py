"""Bounded policy-driven monitoring runtime, independent of dashboard viewers.

Hosts supply authorization and source factories, including any delegated secret
resolution. This module neither impersonates a browser user nor stores secrets.
It is process-local, not a durable scheduler or the ScratchBird history writer.
"""

import copy
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class MonitoringPolicy:
    owner_id: int
    endpoint_id: str
    target_id: str | None
    interval_seconds: int = 5
    retain_samples: int = 120
    lease_seconds: int = 3600
    heartbeat_enabled: bool = False
    heartbeat_timeout_seconds: int | None = None
    metadata_interval_seconds: int = 60
    max_transaction_age_seconds: int = 0
    max_backup_state_seconds: int = 0
    require_wire_encryption: bool = False
    expected_encryption_state: int | None = None

    def __post_init__(self):
        if type(self.owner_id) is not int or self.owner_id <= 0:
            raise ValueError('Monitoring policy requires an owner')
        if not isinstance(self.endpoint_id, str) or not self.endpoint_id:
            raise ValueError('Monitoring policy requires an endpoint')
        if self.target_id is not None and (
                not isinstance(self.target_id, str) or not self.target_id):
            raise ValueError('Monitoring target is invalid')
        minimum = 15 if self.target_id is None else 5
        for name, lower, upper in (
                ('interval_seconds', minimum, 300),
                ('metadata_interval_seconds', 60, 3600),
                ('max_transaction_age_seconds', 0, 86400),
                ('max_backup_state_seconds', 0, 86400),
                ('retain_samples', 1, 720), ('lease_seconds', 5, 86400)):
            value = getattr(self, name)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError('Invalid monitoring policy ' + name)
        if not isinstance(self.heartbeat_enabled, bool):
            raise ValueError('Heartbeat admission must be a boolean')
        if type(self.require_wire_encryption) is not bool:
            raise ValueError('Wire encryption policy must be boolean')
        if self.expected_encryption_state is not None and (
                type(self.expected_encryption_state) is not int or
                self.expected_encryption_state not in range(4)):
            raise ValueError('Invalid expected native encryption state')
        if self.heartbeat_timeout_seconds is not None and (
                type(self.heartbeat_timeout_seconds) is not int or not
                self.interval_seconds + 5 <= self.heartbeat_timeout_seconds <= 3600):
            raise ValueError('Heartbeat overdue threshold is invalid')

    @property
    def heartbeat_timeout(self):
        return (self.heartbeat_timeout_seconds if
                self.heartbeat_timeout_seconds is not None else
                max(15, self.interval_seconds * 3))

    @property
    def key(self):
        return self.owner_id, self.endpoint_id, self.target_id


class MonitoringRuntime:
    """At most one job per owner/endpoint/target; reads never schedule work.

    A host must serialize ownership across application processes before exposing
    this runtime in a multi-worker deployment. authorize(policy, purpose) must
    recheck current rights for both collection and viewing; exceptions fail
    closed. Factories must arrange admitted worker credentials, not capture an
    interactive Flask session. monitoring_host admits the current single-process
    web boundary; shared multi-worker operation requires a different owner.
    """

    def __init__(self, *, capacity=16, clock=time.monotonic):
        if type(capacity) is not int or not 1 <= capacity <= 64:
            raise ValueError('Monitoring capacity is invalid')
        self._capacity = capacity
        self._clock = clock
        self._jobs = {}
        self._lock = threading.RLock()
        self._closed = False

    def enable(self, policy, source_factory, authorize):
        # Invocation is itself an explicit policy change, never a viewer GET.
        if authorize(policy, 'configure') is not True:
            raise PermissionError('Monitoring policy is not authorized')
        with self._lock:
            if self._closed:
                raise RuntimeError('Monitoring runtime is closed')
            previous = self._jobs.get(policy.key)
            if previous is not None:
                if previous.policy != policy or previous.stop.is_set():
                    raise ValueError('Disable and release the previous policy first')
                return previous.revision
            if len(self._jobs) >= self._capacity:
                raise ValueError('Monitoring policy capacity reached')
            job = _Job(policy, source_factory, authorize, self._clock)
            self._jobs[policy.key] = job
            job.thread.start()
            return job.revision

    def snapshot(self, policy, authorize):
        if authorize(policy, 'view') is not True:
            raise PermissionError('Monitoring view is not authorized')
        with self._lock:
            job = self._jobs.get(policy.key)
            if job is None:
                return {'state': 'disabled', 'samples': [], 'history': 'volatile'}
            return job.snapshot()

    def inspect_statement(self, policy, authorize, reference):
        if authorize(policy, 'view') is not True:
            raise PermissionError('Statement inspection is not authorized')
        with self._lock:
            job = self._jobs.get(policy.key)
            if job is None:
                return {'status': 'unavailable', 'reason': 'collector-disabled'}
        with job.lock:
            def admitted():
                if job.stop.is_set() or job.clock() >= job.deadline or job.source is None:
                    raise PermissionError('Statement inspection grant ended')
                if authorize(policy, 'view') is not True or job.authorize(policy, 'collect') is not True:
                    raise PermissionError('Statement inspection is not authorized')
            admitted()
            if isinstance(reference, dict) and reference.get('kind') == 'compiled':
                fields = {'compiled_statement_id', 'object_name', 'object_type', 'package_name', 'stat_id'}
                if set(reference) != fields | {'sample_id', 'kind'}:
                    raise ValueError('Compiled inspection requires an exact sampled identity')
                if any(value is not None and (not isinstance(value, str) or len(value) > 256)
                       for value in reference.values()):
                    raise ValueError('Invalid compiled statement identity')
                if not isinstance(reference['compiled_statement_id'], str) or not reference['compiled_statement_id'].isdigit():
                    raise ValueError('Invalid compiled statement identity')
                sample = job.samples[-1] if job.samples else {}
                group = sample.get('groups', {}).get('compiled_details', {})
                if (reference['sample_id'] != sample.get('sample_id') or group.get('status') != 'available' or
                        not any(all(row.get(key) == reference[key] for key in fields)
                                for row in group.get('values', {}).get('rows', []))):
                    return {'status': 'changed', 'reason': 'latest-sample-does-not-match'}
                result = job.source.inspect_statement({**reference, 'source_epoch': sample.get('source_epoch')})
                admitted()
                return result
            fields = {'statement_id', 'attachment_id', 'compiled_statement_id', 'timestamp'}
            if not isinstance(reference, dict) or set(reference) != fields | {'sample_id'}:
                raise ValueError('Statement inspection requires an exact sampled identity')
            if (not isinstance(reference['sample_id'], str) or len(reference['sample_id']) > 64 or
                    any(not isinstance(reference[key], str) or not reference[key].isdigit() or
                        len(reference[key]) > 19 for key in ('statement_id', 'attachment_id')) or
                    (reference['compiled_statement_id'] is not None and (
                        not isinstance(reference['compiled_statement_id'], str) or
                        not reference['compiled_statement_id'].isdigit() or len(reference['compiled_statement_id']) > 19)) or
                    (reference['timestamp'] is not None and (
                        not isinstance(reference['timestamp'], str) or len(reference['timestamp']) > 80))):
                raise ValueError('Invalid bounded statement identity')
            sample = job.samples[-1] if job.samples else {}
            group = sample.get('groups', {}).get('statement_details', {})
            if (reference['sample_id'] != sample.get('sample_id') or group.get('status') != 'available' or
                    not any(all(row.get(key) == reference[key] for key in fields)
                            for row in group.get('values', {}).get('rows', []))):
                return {'status': 'changed', 'reason': 'latest-sample-does-not-match'}
            result = job.source.inspect_statement({**reference, 'source_epoch': sample.get('source_epoch')})
            admitted()
            return result

    def inspect_details(self, policy, authorize, reference):
        if (not isinstance(reference, dict) or set(reference) != {'sample_id', 'operation'} or
                reference.get('operation') not in ('accounts', 'server-log', 'server-paths') or
                not isinstance(reference.get('sample_id'), str) or len(reference['sample_id']) > 64):
            raise ValueError('Invalid monitoring detail reference')
        if (reference['operation'] == 'accounts') != (policy.target_id is not None):
            raise ValueError('Invalid monitoring detail scope')
        if authorize(policy, 'view') is not True:
            raise PermissionError('Monitoring inspection is not authorized')
        with self._lock:
            job = self._jobs.get(policy.key)
        if job is None:
            return {'status': 'unavailable', 'reason': 'collector-disabled'}
        with job.lock:
            def admitted():
                if (job.stop.is_set() or job.clock() >= job.deadline or job.source is None or
                        authorize(policy, 'view') is not True or job.authorize(policy, 'collect') is not True):
                    raise PermissionError('Monitoring inspection grant ended')
            admitted()
            latest = job.samples[-1] if job.samples else {}
            sample = next((item for item in list(job.samples)[-3:]
                           if item.get('sample_id') == reference['sample_id']), {})
            if (not sample or sample.get('source_epoch') != latest.get('source_epoch') or
                    sample.get('status') not in ('available', 'partial') or not sample.get('source_epoch')):
                return {'status': 'changed', 'reason': 'recent-collector-epoch-does-not-match'}
            result = job.source.inspect_details(reference['operation'], sample['source_epoch'])
            admitted()
            return result

    def disable(self, policy, authorize, *, timeout=5):
        if authorize(policy, 'configure') is not True:
            raise PermissionError('Monitoring policy is not authorized')
        with self._lock:
            job = self._jobs.get(policy.key)
            if job is None:
                return True
            job.stop.set()
        job.thread.join(timeout=max(0, min(timeout, 30)))
        with self._lock:
            # Unconfirmed release remains owned and blocks replacement.
            if job.thread.is_alive():
                return False
            if not job.release():
                return False
            if self._jobs.get(policy.key) is job:
                del self._jobs[policy.key]
            return True

    def close(self, *, timeout=5):
        with self._lock:
            self._closed = True
            jobs = tuple(self._jobs.values())
            for job in jobs:
                job.stop.set()
        deadline = self._clock() + max(0, min(timeout, 30))
        released = True
        for job in jobs:
            job.thread.join(timeout=max(0, deadline - self._clock()))
            if job.thread.is_alive() or not job.release():
                released = False
        return released


class _Job:
    def __init__(self, policy, factory, authorize, clock):
        self.policy = policy
        self.revision = str(uuid.uuid4())
        self.factory = factory
        self.authorize = authorize
        self.clock = clock
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.source = None
        self.samples = deque(maxlen=policy.retain_samples)
        self.evicted = 0
        self.state = 'starting'
        self.error_type = None
        self.started_clock = clock()
        self.deadline = self.started_clock + policy.lease_seconds
        self.last_heartbeat = None
        self.last_heartbeat_at = None
        self.last_probe = 'unknown'
        self.last_sample_clock = None
        self.thread = threading.Thread(
            target=self.run, name='cde-monitor-' + self.revision[:8], daemon=True)

    def snapshot(self):
        with self.lock:
            return copy.deepcopy({
                'revision': self.revision, 'state': self.state,
                'error_type': self.error_type, 'history': 'volatile',
                'retention_evictions': self.evicted,
                'interval_seconds': self.policy.interval_seconds,
                'samples': list(self.samples),
                'sample_age_seconds': (None if self.last_sample_clock is None else
                    max(0, self.clock() - self.last_sample_clock)),
                'stale_after_seconds': max(15, self.policy.interval_seconds * 3),
                'heartbeat': self.heartbeat(),
            })

    def heartbeat(self):
        age = (None if self.last_heartbeat is None else
               max(0, self.clock() - self.last_heartbeat))
        if not self.policy.heartbeat_enabled:
            status = 'disabled'
        elif self.stop.is_set():
            status = 'stopped'
        elif age is None:
            status = 'unknown'
        elif age > self.policy.heartbeat_timeout:
            status = 'overdue'
        else:
            status = 'observed'
        return {
            'enabled': self.policy.heartbeat_enabled, 'status': status,
            'last_success_at': self.last_heartbeat_at,
            'age_seconds': age, 'overdue_after_seconds': self.policy.heartbeat_timeout,
            'latest_probe': self.last_probe,
            'source': ('database-transaction-refresh' if self.policy.target_id
                       is not None else 'service-query'),
        }

    def release(self):
        with self.lock:
            if self.source is None:
                return True
            try:
                self.source.close()
            except Exception as error:
                self.state = 'release-unconfirmed'
                self.error_type = type(error).__name__
                return False
            self.source = None
            return True

    def run(self):
        failures = 0
        try:
            while not self.stop.is_set():
                if self.clock() >= self.deadline:
                    with self.lock:
                        self.state = 'expired'
                    break
                try:
                    if self.authorize(self.policy, 'collect') is not True:
                        raise PermissionError('Monitoring collection is not authorized')
                except Exception as error:
                    with self.lock:
                        self.state = 'authorization-denied'
                        self.error_type = type(error).__name__
                    break
                try:
                    if self.source is None:
                        self.source = self.factory(self.policy)
                    sample = self.source.sample()
                    if not isinstance(sample, dict) or sample.get('status') not in (
                            'available', 'partial', 'unavailable'):
                        raise ValueError('Invalid monitoring source result')
                except Exception as error:
                    sample = {'status': 'unavailable',
                              'sample_id': str(uuid.uuid4()),
                              'ended_at': datetime.now(timezone.utc).isoformat(),
                              'error_type': type(error).__name__}
                # An in-flight native read may outlive its grant. Never publish
                # its values after disable, expiry or a scope/rights change.
                if self.stop.is_set():
                    break
                if self.clock() >= self.deadline:
                    with self.lock:
                        self.state = 'expired'
                    break
                try:
                    if self.authorize(self.policy, 'collect') is not True:
                        raise PermissionError('Monitoring collection is not authorized')
                except Exception as error:
                    with self.lock:
                        self.state = 'authorization-denied'
                        self.error_type = type(error).__name__
                    break
                with self.lock:
                    if len(self.samples) == self.samples.maxlen:
                        self.evicted += 1
                    sample = copy.deepcopy(sample)
                    sample['runtime_elapsed_seconds'] = max(0, self.clock() - self.started_clock)
                    from .monitoring_findings import findings
                    sample['findings'] = findings(self.policy, sample, list(self.samples))
                    self.samples.append(sample)
                    self.last_sample_clock = self.clock()
                    self.state = 'collecting'
                    self.last_probe = sample['status']
                    evidence_key = ('transaction_refresh' if
                                    self.policy.target_id is not None else
                                    'service_probe')
                    expected_scope = ('database' if self.policy.target_id
                                      is not None else 'server')
                    if self.policy.heartbeat_enabled and (
                            sample['status'] in ('available', 'partial') and
                            sample.get('scope') == expected_scope and
                            sample.get(evidence_key, {}).get('status') == 'completed'):
                        self.last_heartbeat = self.clock()
                        self.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
                failures = failures + 1 if sample['status'] == 'unavailable' else 0
                # Delay from completion: no overlap or catch-up storm, bounded
                # exponential failure backoff, and expiration wakes promptly.
                delay = min(300, self.policy.interval_seconds * 2**min(failures, 6))
                self.stop.wait(max(0, min(delay, self.deadline - self.clock())))
        finally:
            self.stop.set()
            with self.lock:
                if self.state not in ('expired', 'authorization-denied'):
                    self.state = 'stopped'
            self.release()
