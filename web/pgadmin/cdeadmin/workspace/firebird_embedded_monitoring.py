"""File-authorized Firebird collectors; Engine13 does not validate passwords."""
import copy
import threading
import time
from types import SimpleNamespace

from .monitoring_delegation import route_fingerprint, _GrantedSource
from ..providers.firebird.embedded import embedded_route


class EmbeddedMonitoringGrant:
    def __init__(self, policy, route, generation, permissions, authorize, *, clock=time.monotonic):
        if policy.target_id is None or route.get('attachment_mode') != 'embedded':
            raise ValueError('Embedded monitoring requires a registered database file')
        embedded_route(route, permissions)
        if policy.require_wire_encryption:
            raise ValueError('Embedded monitoring has no wire encryption')
        self.policy, self.generation = policy, generation
        self.route_digest = route_fingerprint(route)
        self._authorize, self._clock = authorize, clock
        self._deadline = clock() + policy.lease_seconds
        self._lock, self._revoked = threading.RLock(), False
        self._route = copy.deepcopy(route)
        for key in ('credential_references', 'credential_reference_id', 'credential_kind', 'principal_reference'):
            self._route.pop(key, None)
        self.authentication = {'mode':'local-file', 'username':route.get('user', ''), 'role':route.get('role', '')}
        self.require(policy, 'configure')

    def require(self, policy, purpose):
        with self._lock:
            if (self._revoked or policy != self.policy or self._clock() >= self._deadline or
                    purpose not in {'configure', 'collect', 'view'} or
                    self._authorize(policy, purpose, self.generation, self.route_digest) is not True):
                raise PermissionError('Embedded monitoring grant ended or scope changed')
            return True

    def revoke(self):
        with self._lock:
            self._revoked = True

    def open_source(self, policy):
        self.require(policy, 'collect')
        from ..providers.firebird.monitoring import FirebirdMonitor
        def require(permission, *_):
            if permission not in {'embedded_runtime', 'filesystem'}:
                raise PermissionError('Embedded collector permission is unavailable')
            return self.require(policy, 'collect')
        permissions = SimpleNamespace(require=require, acquire_secret=lambda *_:
            (_ for _ in ()).throw(PermissionError('Embedded collection does not use password authentication')))
        return _GrantedSource(self, FirebirdMonitor(permissions, copy.deepcopy(self._route),
            metadata_interval_seconds=policy.metadata_interval_seconds))
