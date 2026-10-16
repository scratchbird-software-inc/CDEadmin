"""Owner-scoped DuckDB file monitoring without a network credential grant."""

import copy
import time
from threading import RLock

from .monitoring import MonitoringPolicy
from .monitoring_delegation import route_fingerprint
from .monitoring_host import MonitoringHost, MonitoringHostUnavailable
from .mysql_monitoring_host import MySQLMonitoringHost, init_app as init_native_host
from ..providers.embedded_route import contained_database


class DuckDBFileGrant:
    def __init__(self, policy, route, generation, authorize, *, clock=time.monotonic):
        if policy.target_id is None or route.get('database') == ':memory:':
            raise ValueError('DuckDB monitoring requires a registered file target')
        if any(key in route for key in ('password', 'passwd', 'secret', 'token', 'credential_references')):
            raise ValueError('DuckDB monitoring route has unsupported credentials')
        contained_database(route)
        self.policy, self.generation = policy, generation
        self.route_digest = route_fingerprint(route)
        self.authentication = {'mode': 'local-file', 'username': '', 'role': ''}
        self._route = copy.deepcopy(route)
        self._authorize, self._clock = authorize, clock
        self._deadline = clock() + policy.lease_seconds
        self._revoked = False
        self._lock = RLock()
        self.require(policy, 'configure')

    def require(self, policy, purpose):
        with self._lock:
            if (self._revoked or policy != self.policy or
                    self._clock() >= self._deadline or
                    purpose not in {'configure', 'collect', 'view'}):
                raise PermissionError('DuckDB monitoring grant ended')
            if self._authorize(policy, purpose, self.generation, self.route_digest) is not True:
                raise PermissionError('DuckDB monitoring scope changed')
            return True

    def open_source(self, policy):
        self.require(policy, 'collect')
        from ..providers.duckdb.monitoring import DuckDBMonitor
        return DuckDBMonitor(copy.deepcopy(self._route), target_id=policy.target_id,
                             metadata_interval_seconds=policy.metadata_interval_seconds)

    def revoke(self):
        with self._lock:
            self._revoked = True


class DuckDBMonitoringHost(MySQLMonitoringHost):
    engine = 'duckdb'
    profile_id = 'duckdb-native'
    provider_id = 'org.cdeadmin.duckdb'
    identity_key = 'target_id'
    policy_fields = frozenset({'interval_seconds', 'retain_samples', 'lease_seconds',
        'heartbeat_enabled', 'heartbeat_timeout_seconds', 'metadata_interval_seconds', 'history_enabled'})

    @property
    def available(self):
        return self.admitted and self.ownership is not None

    def enable(self, owner, sid, target, body):
        if not isinstance(body, dict) or set(body) - self.policy_fields:
            raise ValueError('Unsupported DuckDB monitoring policy fields')
        if not isinstance(target, str) or not target:
            raise ValueError('Select a registered DuckDB file')
        if not self.available:
            raise MonitoringHostUnavailable('Monitoring requires single-process admission and a lock path')
        key = owner, sid, target
        with self._lock:
            if key not in self._grants:
                with self.app.app_context():
                    server = self._owned_server(owner, sid)
                    context, endpoint, _ = self.endpoints.workspace(server, database_target_id=target)
                    if context.profile_id != self.profile_id:
                        raise PermissionError('Select a native DuckDB endpoint')
                    self._admissions[key] = {
                        'endpoint_id': server.endpoint_profile.id,
                        'generation': server.endpoint_profile.profile_generation or server.endpoint_profile.cache_namespace,
                        'configuration': self._configuration(server),
                        'route': copy.deepcopy(endpoint['route'])}
            try:
                scope = self._scope(owner, sid, target)
                policy = MonitoringPolicy(owner, scope['endpoint_id'], target,
                    **{'interval_seconds': 5, **body})
                previous = self._grants.get(key)
                if previous is not None:
                    previous.require(policy, 'configure')
                    self.runtime.enable(policy, previous.open_source, previous.require,
                                        history_writer=self._history_writer(previous))
                else:
                    self.ownership.acquire()
                    grant = DuckDBFileGrant(policy, scope['route'], scope['generation'],
                        self._authorizer(owner, sid, target))
                    try:
                        self.runtime.enable(policy, grant.open_source, grant.require,
                                            history_writer=self._history_writer(grant))
                    except BaseException:
                        grant.revoke()
                        raise
                    self._grants[key] = grant
                grant = self._grants[key]
                return {**self.runtime.snapshot(policy, grant.require),
                    'authentication': dict(grant.authentication),
                    'policy': {field: getattr(policy, field) for field in self.policy_fields}}
            finally:
                if key not in self._grants:
                    self._admissions.pop(key, None)

    def snapshot(self, owner, sid, target):
        result = super().snapshot(owner, sid, target)
        if target is not None:
            return result
        registered = result.get('navigation', {}).get('databases', [])
        if len(registered) > 256:
            raise ValueError('DuckDB server dashboard exceeds 256 registered files')
        files = []
        for item in registered:
            current = super().snapshot(owner, sid, item['target_id'])
            files.append({'target_id': item['target_id'], 'name': item['name'],
                          'snapshot': {'state': current['state'],
                                       'heartbeat': current.get('heartbeat')}})
        return {**result, 'state': 'aggregate', 'databases': files,
                'aggregation': 'registered files only; no remote server process is inferred'}

    def inspect_statement(self, owner, sid, target, reference):
        self.snapshot(owner, sid, target)
        return {'status': 'unavailable', 'reason': 'DuckDB has no global statement inventory'}

    def inspect_details(self, owner, sid, target, reference):
        self.snapshot(owner, sid, target)
        return {'status': 'unavailable', 'reason': 'DuckDB has no remote server details'}


def init_app(app, shared_host):
    return init_native_host(app, shared_host, DuckDBMonitoringHost)
