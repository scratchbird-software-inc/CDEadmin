"""MySQL owner-scoped collector admission without worker browser sessions."""
import atexit
import copy

from .monitoring_host import MonitoringHost
from .monitoring_delegation import route_fingerprint


class MySQLMonitoringHost(MonitoringHost):
    engine = 'mysql'
    policy_fields = frozenset({'interval_seconds', 'retain_samples', 'lease_seconds',
        'heartbeat_enabled', 'heartbeat_timeout_seconds', 'metadata_interval_seconds'})

    def __init__(self, app, shared_host):
        super().__init__(app, shared_host.endpoints)
        self.ownership, self.keys = shared_host.ownership, shared_host.keys
        self._admissions, self._issuing_permissions = {}, {}

    def _owned_server(self, owner, sid):
        from pgadmin.model import Server, User
        server = Server.query.filter_by(id=sid, user_id=owner).first()
        if (server is None or User.query.filter_by(id=owner, active=True).first() is None or
                server.endpoint_profile is None or server.endpoint_profile.profile_id != 'mysql-native' or
                server.endpoint_profile.provider_id != 'org.cdeadmin.mysql'):
            raise PermissionError('MySQL monitoring endpoint is unavailable')
        return server

    @staticmethod
    def _configuration(server):
        endpoint = server.endpoint_profile
        runtime = endpoint.runtime_identity
        return route_fingerprint({
            'owner': server.user_id, 'username': server.username, 'password_revision': str(server.password),
            'provider': [endpoint.provider_id, endpoint.provider_version, endpoint.profile_id, endpoint.profile_version],
            'generation': endpoint.profile_generation or endpoint.cache_namespace,
            'verification': [runtime.verification_state, runtime.verified_runtime_family,
                runtime.verified_runtime_version, str(runtime.verified_at),
                runtime.verification_evidence_reference] if runtime is not None else None,
            'tls': [endpoint.tls_profile.tls_mode, endpoint.tls_profile.configuration_reference]
                if endpoint.tls_profile is not None else None,
            'routes': sorted((row.id, row.route_reference, row.route_kind, row.priority, row.configuration) for row in endpoint.routes),
            'targets': sorted((row.id, row.database, row.configuration, row.registration_user,
                str(row.registration_password), row.registration_credentials) for row in endpoint.database_targets),
            'references': sorted((row.id, row.secret_kind, row.storage_kind, row.secret_reference) for row in endpoint.secret_references),
        })

    def _scope(self, owner, sid, target):
        with self.app.app_context():
            server = self._owned_server(owner, sid)
            admitted = self._admissions.get((owner, sid, target))
            if admitted is None or admitted['configuration'] != self._configuration(server):
                raise PermissionError('Monitoring registration changed; stop and reconfigure')
            return {**admitted, 'route': copy.deepcopy(admitted['route']),
                    'permissions': self._issuing_permissions.get((owner, sid, target))}

    def enable(self, owner, sid, target, body):
        if not isinstance(body, dict) or set(body) - (self.policy_fields | {'credentials'}):
            raise ValueError('Unsupported MySQL monitoring fields')
        key = owner, sid, target
        with self._lock:
            if key not in self._grants:
                server = self._owned_server(owner, sid)
                context, endpoint, _ = self.endpoints.workspace(server, database_target_id=target)
                binding = self.endpoints.provider_registry.resolve(context)
                if context.profile_id != 'mysql-native':
                    raise PermissionError('Select a native MySQL endpoint')
                self._admissions[key] = {'endpoint_id': server.endpoint_profile.id,
                    'generation': server.endpoint_profile.profile_generation or server.endpoint_profile.cache_namespace,
                    'configuration': self._configuration(server), 'route': copy.deepcopy(endpoint['route'])}
                self._issuing_permissions[key] = binding.permissions
            try:
                return super().enable(owner, sid, target, body)
            finally:
                self._issuing_permissions.pop(key, None)
                if key not in self._grants:
                    self._admissions.pop(key, None)

    def close(self):
        with self._lock:
            for grant in self._grants.values():
                grant.revoke()
            return self.runtime.close()  # The common host owns the process lock.

    def disable(self, owner, sid, target):
        result = super().disable(owner, sid, target)
        if result.get('released'):
            with self._lock:
                self._admissions.pop((owner, sid, target), None)
        return result


def init_app(app, shared_host):
    key = 'cdeadmin_mysql_monitoring_host'
    if key in app.extensions:
        return app.extensions[key]
    host = MySQLMonitoringHost(app, shared_host)
    app.extensions[key] = host
    atexit.register(host.close)
    from flask import Blueprint, jsonify, request
    from flask_security import current_user
    from pgadmin.user_login_check import pga_login_required
    api = Blueprint('cdeadmin_mysql_monitoring', __name__)

    @api.route('/cdeadmin/api/monitoring/mysql/<int:sid>', methods=['GET', 'POST', 'DELETE'])
    @pga_login_required
    def monitoring(sid):
        target = request.args.get('target_id')
        if target == '' or (target is not None and len(target) > 255):
            return jsonify(success=0, errormsg='Invalid monitoring target'), 400
        try:
            owner = current_user.id
            if request.method == 'POST':
                data = host.enable(owner, sid, target, request.get_json(silent=True))
            elif request.method == 'DELETE':
                data = host.disable(owner, sid, target)
            else:
                data = host.snapshot(owner, sid, target)
            return jsonify(success=1, data=data)
        except PermissionError:
            return jsonify(success=0, errormsg='Monitoring scope is not authorized'), 403
        except (ValueError, TypeError):
            return jsonify(success=0, errormsg='Invalid monitoring policy'), 400
        except Exception:
            return jsonify(success=0, errormsg='Monitoring request failed'), 503
    app.register_blueprint(api)
    return host
