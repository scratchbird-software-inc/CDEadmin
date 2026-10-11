"""Scope-bound, volatile credentials for dedicated native collectors.

The host authenticates the owner at issue time and supplies a current scope
authorizer. Workers use sealed leases, never a captured Flask login/session.
"""

import copy
from dataclasses import asdict
import hashlib
import json
import threading
import time
from types import SimpleNamespace
import uuid

from pgadmin.cdeadmin.security.secrets import SecretLease


class MonitoringGrantError(PermissionError):
    """A monitoring grant is absent, expired, revoked or outside its scope."""


def route_fingerprint(route):
    return hashlib.sha256(json.dumps(
        route, sort_keys=True, separators=(',', ':'), allow_nan=False,
    ).encode('utf-8')).hexdigest()


class MonitoringGrant:
    """Host-owned grant; the authorizer must resolve current persisted scope.

    authorize(policy, purpose, generation, route_digest) must independently
    validate current owner/rights, endpoint verification, route, database target
    and generation. This callable is not serialized or supplied by the browser.
    """

    @classmethod
    def issue(cls, policy, route, generation, permissions, key_ring,
              authorize, *, clock=time.monotonic, credentials=None,
              engine='firebird'):
        if engine not in ('firebird', 'postgresql'):
            raise MonitoringGrantError('Unsupported monitoring engine')
        if not key_ring.available:
            raise MonitoringGrantError('Monitoring worker key authority is unavailable')
        if not isinstance(generation, str) or not generation:
            raise MonitoringGrantError('Monitoring generation is unavailable')
        if route.get('attachment_mode', 'network') != 'network':
            raise MonitoringGrantError('This grant requires a network attachment')
        if any(key in route for key in ('password', 'passwd', 'secret', 'token')):
            raise MonitoringGrantError('Monitoring route must use secret references')
        if engine == 'postgresql':
            if not route.get('database'):
                raise MonitoringGrantError('PostgreSQL requires a connection database')
            if policy.target_id is not None:
                from pgadmin.cdeadmin.providers.postgresql.connection_target import database_oid
                oid = database_oid(policy.target_id)
                if type(route.get('database_oid')) is not int or route['database_oid'] != oid:
                    raise MonitoringGrantError('Monitoring database identity does not match')
        elif (policy.target_id is not None) != bool(route.get('database')):
            raise MonitoringGrantError('Monitoring database scope does not match')
        original = copy.deepcopy(route)
        digest = route_fingerprint(original)
        if authorize(policy, 'configure', generation, digest) is not True:
            raise MonitoringGrantError('Monitoring delegation is not authorized')
        if credentials is not None:
            if (not isinstance(credentials, dict) or
                    set(credentials) - {'username', 'password', 'role'} or
                    any(not isinstance(credentials.get(key), str) or
                        not credentials[key] or '\x00' in credentials[key] or
                        len(credentials[key]) > limit
                        for key, limit in (('username', 255), ('password', 4096))) or
                    not isinstance(credentials.get('role', ''), str) or
                    len(credentials.get('role', '')) > 255 or
                    '\x00' in credentials.get('role', '')):
                raise ValueError('Invalid monitoring credentials')
        references = dict(original.get('credential_references') or {})
        primary = original.get('credential_reference_id')
        if primary is not None:
            kind = original.get('credential_kind', 'database_password')
            if kind in references and references[kind] != primary:
                raise MonitoringGrantError('Monitoring credential references conflict')
            references[kind] = primary
        if credentials is not None:
            references = {'database_password': 'dedicated'}
        if set(references) != {'database_password'}:
            raise MonitoringGrantError('A database password reference is required')
        principal = original.get('principal_reference')
        if not isinstance(principal, str) or not principal:
            raise MonitoringGrantError('Monitoring credential principal is unavailable')
        grant = cls()
        grant.engine = engine
        grant.policy = policy
        grant.generation = generation
        grant.route_digest = digest
        grant.id = str(uuid.uuid4())
        grant._clock = clock
        grant._deadline = clock() + policy.lease_seconds
        grant._authorize = authorize
        grant._keys = key_ring
        grant._lock = threading.RLock()
        grant._revoked = False
        grant._credentials = {}
        grant._route = original
        if credentials is not None:
            grant._route.update(user=credentials['username'],
                                role=credentials.get('role', ''), trusted_auth=False)
        grant.authentication = {
            'mode': 'dedicated' if credentials is not None else 'registration',
            'username': grant._route.get('user', ''),
            'role': grant._route.get('role', ''),
        }
        rebound = {}
        try:
            for kind, reference in references.items():
                if not isinstance(reference, str) or not reference:
                    raise MonitoringGrantError('Monitoring credential is unavailable')
                identifier = str(uuid.uuid4())
                lease = (SecretLease(credentials['password']) if credentials is not None
                         else permissions.acquire_secret(reference, principal, 'connect', kind))
                with lease:
                    envelope = lease.use(lambda value: key_ring.encrypt(
                        value, grant._aad(identifier, kind)))
                grant._credentials[identifier] = (kind, envelope)
                rebound[kind] = identifier
            grant._route.update(
                credential_references=rebound,
                credential_reference_id=rebound['database_password'],
                credential_kind='database_password',
                principal_reference='monitor:' + grant.id)
            # Admission can expire or be revoked while credentials are acquired.
            grant.require(policy, 'collect')
        except BaseException:
            grant.revoke()
            raise
        return grant

    def _aad(self, identifier, kind):
        return {
            'schema': 'cdeadmin.monitoring-grant.v1', 'grant_id': self.id,
            'engine': self.engine,
            'policy': asdict(self.policy), 'generation': self.generation,
            'route_digest': self.route_digest, 'credential_id': identifier,
            'secret_kind': kind, 'authentication': dict(self.authentication),
        }

    def require(self, policy, purpose):
        with self._lock:
            if (self._revoked or policy != self.policy or
                    self._clock() >= self._deadline or
                    purpose not in ('configure', 'collect', 'view')):
                raise MonitoringGrantError('Monitoring grant is unavailable')
            try:
                admitted = self._authorize(
                    policy, purpose, self.generation, self.route_digest)
            except Exception:
                raise MonitoringGrantError('Monitoring scope could not be authorized') from None
            if admitted is not True:
                raise MonitoringGrantError('Monitoring scope is no longer authorized')
            return True

    def revoke(self):
        with self._lock:
            self._revoked = True
            self._credentials.clear()

    def _acquire(self, reference, principal, purpose, kind):
        with self._lock:
            self.require(self.policy, 'collect')
            if principal != 'monitor:' + self.id or purpose != 'connect':
                raise MonitoringGrantError('Monitoring credential use is not authorized')
            entry = self._credentials.get(reference)
            if entry is None or entry[0] != kind:
                raise MonitoringGrantError('Monitoring credential scope does not match')
            try:
                value = bytearray(self._keys.decrypt(
                    entry[1], self._aad(reference, kind)))
                try:
                    return SecretLease(value)
                finally:
                    for index in range(len(value)):
                        value[index] = 0
            except Exception:
                raise MonitoringGrantError('Monitoring credential is unavailable') from None

    def open_source(self, policy, *, source_factory=None):
        with self._lock:
            self.require(policy, 'collect')
            if source_factory is None:
                if self.engine == 'postgresql':
                    from pgadmin.cdeadmin.providers.postgresql.monitoring import PostgreSQLMonitor
                    source_factory = PostgreSQLMonitor
                elif self.engine == 'firebird':
                    from pgadmin.cdeadmin.providers.firebird.monitoring import FirebirdMonitor
                    source_factory = FirebirdMonitor
                else:
                    raise MonitoringGrantError('Unsupported monitoring engine')
            source = source_factory(
                SimpleNamespace(acquire_secret=self._acquire),
                copy.deepcopy(self._route),
                scope='database' if policy.target_id is not None else 'server',
                metadata_interval_seconds=policy.metadata_interval_seconds)
            return _GrantedSource(self, source)


class _GrantedSource:
    def __init__(self, grant, source):
        self._grant = grant
        self._source = source

    def sample(self):
        self._grant.require(self._grant.policy, 'collect')
        value = self._source.sample()
        self._grant.require(self._grant.policy, 'collect')
        return value

    def inspect_statement(self, reference):
        self._grant.require(self._grant.policy, 'collect')
        value = self._source.inspect_statement(reference)
        self._grant.require(self._grant.policy, 'collect')
        return value

    def inspect_details(self, operation, source_epoch):
        self._grant.require(self._grant.policy, 'collect')
        value = self._source.inspect_details(operation, source_epoch)
        self._grant.require(self._grant.policy, 'collect')
        return value

    def close(self):
        # Revocation cannot prevent releasing the already owned attachment.
        self._source.close()
