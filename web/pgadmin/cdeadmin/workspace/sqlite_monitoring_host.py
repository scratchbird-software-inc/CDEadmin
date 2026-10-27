"""Owner-scoped SQLite file monitoring without an invented server credential."""

import copy

from .duckdb_monitoring_host import DuckDBFileGrant, DuckDBMonitoringHost
from .monitoring import MonitoringPolicy
from .monitoring_host import MonitoringHostUnavailable
from .mysql_monitoring_host import init_app as init_native_host


class SQLiteFileGrant(DuckDBFileGrant):
    def open_source(self, policy):
        self.require(policy, 'collect')
        from ..providers.sqlite.monitoring import SQLiteMonitor
        return SQLiteMonitor(copy.deepcopy(self._route), target_id=policy.target_id,
                             metadata_interval_seconds=policy.metadata_interval_seconds)


class SQLiteMonitoringHost(DuckDBMonitoringHost):
    engine = 'sqlite'
    profile_id = 'sqlite-native'
    provider_id = 'org.cdeadmin.sqlite'

    def enable(self, owner, sid, target, body):
        if not isinstance(body, dict) or set(body) - self.policy_fields:
            raise ValueError('Unsupported SQLite monitoring policy fields')
        if not isinstance(target, str) or not target:
            raise ValueError('Select a registered SQLite file')
        if not self.available:
            raise MonitoringHostUnavailable(
                'Monitoring requires single-process admission and a lock path')
        key = owner, sid, target
        with self._lock:
            if key not in self._grants:
                with self.app.app_context():
                    server = self._owned_server(owner, sid)
                    context, endpoint, _ = self.endpoints.workspace(
                        server, database_target_id=target)
                    if context.profile_id != self.profile_id:
                        raise PermissionError('Select a native SQLite endpoint')
                    self._admissions[key] = {
                        'endpoint_id': server.endpoint_profile.id,
                        'generation': server.endpoint_profile.profile_generation or
                                      server.endpoint_profile.cache_namespace,
                        'configuration': self._configuration(server),
                        'route': copy.deepcopy(endpoint['route'])}
            try:
                scope = self._scope(owner, sid, target)
                policy = MonitoringPolicy(owner, scope['endpoint_id'], target,
                    **{'interval_seconds': 5, **body})
                previous = self._grants.get(key)
                if previous is not None:
                    previous.require(policy, 'configure')
                    self.runtime.enable(policy, previous.open_source,
                                        previous.require, history_writer=self._history_writer(previous))
                else:
                    self.ownership.acquire()
                    grant = SQLiteFileGrant(policy, scope['route'],
                        scope['generation'],
                        self._authorizer(owner, sid, target))
                    try:
                        self.runtime.enable(policy, grant.open_source,
                                            grant.require, history_writer=self._history_writer(grant))
                    except BaseException:
                        grant.revoke()
                        raise
                    self._grants[key] = grant
                grant = self._grants[key]
                return {**self.runtime.snapshot(policy, grant.require),
                    'authentication': dict(grant.authentication),
                    'policy': {field: getattr(policy, field)
                               for field in self.policy_fields}}
            finally:
                if key not in self._grants:
                    self._admissions.pop(key, None)


def init_app(app, shared_host):
    return init_native_host(app, shared_host, SQLiteMonitoringHost)
