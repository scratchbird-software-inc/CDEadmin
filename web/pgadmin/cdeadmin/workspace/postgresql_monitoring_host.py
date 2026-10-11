"""PostgreSQL collection with persisted-owner checks and sealed worker grants."""
import atexit
import copy
from types import SimpleNamespace

from .monitoring_host import MonitoringHost, MonitoringHostUnavailable
from .monitoring_delegation import route_fingerprint
from pgadmin.cdeadmin.providers.postgresql.connection_target import database_oid
from pgadmin.cdeadmin.security.secrets import SecretLease


class PostgreSQLMonitoringHost(MonitoringHost):
    engine = 'postgresql'
    policy_fields = frozenset({'interval_seconds', 'retain_samples', 'lease_seconds',
                              'heartbeat_enabled', 'heartbeat_timeout_seconds',
                              'metadata_interval_seconds'})

    def __init__(self, app, shared_host):
        super().__init__(app, shared_host.endpoints)
        self.ownership = shared_host.ownership
        self.keys = shared_host.keys
        self._admissions = {}
        self._issuing_permissions = {}

    def _owned_server(self, owner, sid):
        from pgadmin.model import Server, User
        server = Server.query.filter_by(id=sid, user_id=owner).first()
        if (server is None or User.query.filter_by(id=owner, active=True).first() is None or
                server.endpoint_profile is None or
                not self.endpoints._is_preserved_postgresql(server)):
            raise PermissionError('PostgreSQL monitoring endpoint is unavailable')
        return server

    @staticmethod
    def _configuration(server):
        # Persisted encrypted credential changes revoke the old grant too.
        values = {name: getattr(server, name, None) for name in (
            'host', 'port', 'username', 'role', 'maintenance_db', 'service',
            'use_ssh_tunnel', 'kerberos_conn', 'connection_params', 'passexec_cmd')}
        values['credential_revision'] = str(server.password)
        return route_fingerprint(values)

    def _scope(self, owner, sid, target):
        with self.app.app_context():
            server = self._owned_server(owner, sid)
            admitted = self._admissions.get((owner, sid, target))
            if (admitted is None or admitted['configuration'] != self._configuration(server) or
                    admitted['endpoint_id'] != server.endpoint_profile.id or
                    admitted['generation'] != (server.endpoint_profile.profile_generation or
                                               server.endpoint_profile.cache_namespace)):
                raise PermissionError('Monitoring registration changed; stop and reconfigure')
            return {**admitted, 'route': copy.deepcopy(admitted['route']),
                    'permissions': self._issuing_permissions.get((owner, sid, target))}

    def _admit(self, owner, sid, target, dedicated):
        from pgadmin.utils.driver.registry import DriverRegistry
        from pgadmin.utils.master_password import get_crypt_key
        from pgadmin.utils.crypto import decrypt
        server = self._owned_server(owner, sid)
        if server.use_ssh_tunnel or server.service or server.kerberos_conn:
            raise ValueError('This collector requires a direct password-authenticated registration')
        oid = database_oid(target)
        manager = DriverRegistry.get('psycopg3').connection_manager(sid)
        connection = manager.connection(did=oid) if oid is not None else manager.connection()
        if not connection.connected() or manager.version != 180003:
            raise ValueError('Connect the selected PostgreSQL 18.3 database first')
        if not connection.db:
            raise ValueError('Monitoring requires an explicit database')
        route = {'host': server.host, 'port': server.port,
                 'database': connection.db, 'user': manager.user, 'role': server.role or '',
                 'connection_params': dict(server.connection_params or {}),
                 'principal_reference': f'user:{owner}', 'credential_reference_id': 'current-connection'}
        if oid is not None:
            route['database_oid'] = oid
        permission = None
        if not dedicated:
            encrypted = connection.password or manager.password
            present, crypt_key = get_crypt_key()
            if not present or not encrypted:
                raise ValueError('Current connection password is unavailable; use a dedicated account')
            # Closure exists only during synchronous grant issue, never in a worker.
            permission = SimpleNamespace(acquire_secret=lambda *_:
                SecretLease(decrypt(encrypted, crypt_key)))
        return {'endpoint_id': server.endpoint_profile.id,
                'generation': server.endpoint_profile.profile_generation or server.endpoint_profile.cache_namespace,
                'configuration': self._configuration(server), 'route': route}, permission

    def enable(self, owner, sid, target, body):
        database_oid(target)
        if not isinstance(body, dict) or set(body) - (self.policy_fields | {'credentials'}):
            raise ValueError('Unsupported PostgreSQL monitoring fields')
        key = owner, sid, target
        with self._lock:
            if key not in self._grants:
                admitted, permissions = self._admit(owner, sid, target, 'credentials' in body)
                self._admissions[key] = admitted
                self._issuing_permissions[key] = permissions
            try:
                return super().enable(owner, sid, target, body)
            finally:
                self._issuing_permissions.pop(key, None)
                if key not in self._grants:
                    self._admissions.pop(key, None)

    def snapshot(self, owner, sid, target):
        database_oid(target)
        with self.app.app_context():
            server = self._owned_server(owner, sid)
            navigation = {'server_id': sid, 'name': server.name}
        with self._lock:
            grant = self._grants.get((owner, sid, target))
            if grant is None:
                return {'state': 'disabled', 'samples': [], 'history': 'volatile',
                        'collection_available': self.available, 'navigation': navigation}
            current = self._authorizer(owner, sid, target)
            result = self.runtime.snapshot(grant.policy, lambda policy, purpose:
                current(policy, purpose, grant.generation, grant.route_digest))
            return {**result, 'authentication': dict(grant.authentication), 'navigation': navigation}

    def disable(self, owner, sid, target):
        database_oid(target)
        with self._lock:
            result = super().disable(owner, sid, target)
            if result['released']:
                self._admissions.pop((owner, sid, target), None)
            return result

    def close(self):
        with self._lock:
            for grant in self._grants.values():
                grant.revoke()
            # The common host owns the shared process lock.
            return self.runtime.close()


def init_app(app, shared_host):
    key = 'cdeadmin_postgresql_monitoring_host'
    if key in app.extensions:
        return app.extensions[key]
    host = PostgreSQLMonitoringHost(app, shared_host)
    app.extensions[key] = host
    atexit.register(host.close)
    from flask import Blueprint, jsonify, request
    from flask_security import current_user
    from pgadmin.user_login_check import pga_login_required
    api = Blueprint('cdeadmin_postgresql_monitoring', __name__)

    @api.route('/cdeadmin/api/monitoring/postgresql/<int:sid>', methods=['GET', 'POST', 'DELETE'])
    @pga_login_required
    def monitoring(sid):
        target = request.args.get('target_id')
        try:
            database_oid(target)
            if request.method == 'GET':
                data = host.snapshot(current_user.id, sid, target)
            elif request.method == 'DELETE':
                data = host.disable(current_user.id, sid, target)
            else:
                data = host.enable(current_user.id, sid, target, request.get_json(silent=True))
            response = jsonify(success=1, data=data)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except PermissionError:
            return jsonify(success=0, errormsg='Monitoring scope is not authorized'), 403
        except (ValueError, TypeError):
            return jsonify(success=0, errormsg='Invalid monitoring policy or unavailable direct PostgreSQL connection'), 400
        except MonitoringHostUnavailable:
            return jsonify(success=0, errormsg='Monitoring host is unavailable'), 503
        except Exception:
            return jsonify(success=0, errormsg='Monitoring request failed'), 503

    app.register_blueprint(api)
    return host
