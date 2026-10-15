"""MySQL owner-scoped collector admission without worker browser sessions."""
import atexit
import copy

from .monitoring_host import MonitoringHost
from .monitoring_delegation import route_fingerprint


class MySQLMonitoringHost(MonitoringHost):
    engine = 'mysql'
    profile_id = 'mysql-native'
    provider_id = 'org.cdeadmin.mysql'
    identity_key = 'server_uuid'
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
                server.endpoint_profile is None or server.endpoint_profile.profile_id != self.profile_id or
                server.endpoint_profile.provider_id != self.provider_id):
            raise PermissionError(f'{self.engine} monitoring endpoint is unavailable')
        return server

    @staticmethod
    def _configuration(server):
        endpoint = server.endpoint_profile
        runtime = endpoint.runtime_identity
        return route_fingerprint({
            'owner': server.user_id, 'username': server.username, 'password_revision': str(server.password),
            'provider': [endpoint.provider_id, endpoint.provider_version, endpoint.profile_id, endpoint.profile_version],
            'generation': endpoint.profile_generation or endpoint.cache_namespace,
            # Reverification timestamps are observations, not registration changes.
            'verification': [runtime.verification_state, runtime.verified_runtime_family,
                runtime.verified_runtime_version,
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
            raise ValueError(f'Unsupported {self.engine} monitoring fields')
        key = owner, sid, target
        with self._lock:
            if key not in self._grants:
                server = self._owned_server(owner, sid)
                context, endpoint, _ = self.endpoints.workspace(server, database_target_id=target)
                binding = self.endpoints.provider_registry.resolve(context)
                if context.profile_id != self.profile_id:
                    raise PermissionError(f'Select a native {self.engine} endpoint')
                self._admissions[key] = {'endpoint_id': server.endpoint_profile.id,
                    'generation': server.endpoint_profile.profile_generation or server.endpoint_profile.cache_namespace,
                    'configuration': self._configuration(server), 'route': copy.deepcopy(endpoint['route'])}
                self._issuing_permissions[key] = binding.permissions
            try:
                result = super().enable(owner, sid, target, body)
                policy = self._grants[key].policy
                return {**result, 'policy': {field: getattr(policy, field) for field in self.policy_fields}}
            finally:
                self._issuing_permissions.pop(key, None)
                if key not in self._grants:
                    self._admissions.pop(key, None)

    def close(self):
        with self._lock:
            for grant in self._grants.values():
                grant.revoke()
            return self.runtime.close()  # The common host owns the process lock.

    def snapshot(self, owner, sid, target):
        with self.app.app_context():
            server = self._owned_server(owner, sid)
            targets = sorted([{'target_id': row.id, 'name': row.display_name}
                for row in server.endpoint_profile.database_targets],
                key=lambda row: (row['name'].casefold(), row['target_id']))
            if target is not None and not any(row['target_id'] == target for row in targets):
                raise PermissionError('Monitoring target is unavailable')
            navigation = {'server_id': sid, 'name': server.name, 'databases': targets}
        with self._lock:
            grant = self._grants.get((owner, sid, target))
            if grant is None:
                return {'state': 'disabled', 'samples': [], 'history': 'volatile',
                    'runtime_scope': 'this-process', 'collection_available': self.available,
                    'navigation': navigation}
            current = self._authorizer(owner, sid, target)
            result = self.runtime.snapshot(grant.policy, lambda policy, purpose:
                current(policy, purpose, grant.generation, grant.route_digest))
            return {**result, 'navigation': navigation, 'authentication': dict(grant.authentication),
                'policy': {key: getattr(grant.policy, key) for key in self.policy_fields}}

    def _registrations(self, owner):
        from pgadmin.model import Server, User
        with self.app.app_context():
            if User.query.filter_by(id=owner, active=True).first() is None:
                raise PermissionError('Monitoring owner is unavailable')
            registrations = []
            for server in Server.query.filter_by(user_id=owner).all():
                endpoint = server.endpoint_profile
                if endpoint is None or endpoint.profile_id != self.profile_id or endpoint.provider_id != self.provider_id:
                    continue
                registrations.append({'server_id': server.id, 'name': server.name,
                    'databases': sorted([{'target_id': row.id, 'name': row.display_name}
                        for row in endpoint.database_targets], key=lambda row: (row['name'].casefold(), row['target_id']))})
            if len(registrations) > 512 or sum(len(row['databases']) for row in registrations) > 4096:
                raise ValueError('Monitoring inventory exceeds its registered-scope bound')
            return sorted(registrations, key=lambda row: (row['name'].casefold(), row['server_id']))

    def fleet(self, owner):
        def read(sid, target):
            try:
                current = self.snapshot(owner, sid, target)
                samples = []
                for sample in current.get('samples', [])[-1:]:
                    identity = {key: value for key, value in sample.get('identity', {}).items()
                        if key in {'database_name', 'version', self.identity_key}}
                    samples.append({key: value for key, value in {**sample, 'identity': identity}.items()
                        if key not in {'groups', 'rates'}})
                return {key: value for key, value in {**current, 'samples': samples}.items()
                    if key not in {'authentication', 'navigation'}}
            except PermissionError:
                return {'state': 'authorization-denied', 'samples': []}
            except Exception:
                return {'state': 'scope-unavailable', 'samples': []}
        servers = []
        for registered in self._registrations(owner):
            sid = registered['server_id']
            servers.append({**registered, 'snapshot': read(sid, None),
                'databases': [{**target, 'snapshot': read(sid, target['target_id'])} for target in registered['databases']]})
        return {'scope': 'engine', 'engine_id': self.engine, 'registered_endpoints': len(servers),
            'servers': servers, 'history': 'volatile', 'inventory': 'owner-registrations-not-physical-instances'}

    def definition_scope(self, owner, sid, target):
        with self.app.app_context():
            if sid is None:
                if target is not None:
                    raise ValueError('Engine scope cannot include a database')
                self._registrations(owner)
                return {'engine': self.engine, 'kind': 'engine', 'owner': owner}
            server = self._owned_server(owner, sid)
            scope = {'engine': self.engine, 'kind': 'database' if target is not None else 'server',
                'owner': owner, 'server_id': sid, 'endpoint_id': server.endpoint_profile.id}
            if target is not None:
                registered = next((row for row in server.endpoint_profile.database_targets if row.id == target), None)
                if registered is None:
                    raise PermissionError('Dashboard target is unavailable')
                scope.update(target_id=target, database=registered.database)
            return scope

    def disable(self, owner, sid, target):
        result = super().disable(owner, sid, target)
        if result.get('released'):
            with self._lock:
                self._admissions.pop((owner, sid, target), None)
        return result


def init_app(app, shared_host, host_class=MySQLMonitoringHost):
    engine = host_class.engine
    key = f'cdeadmin_{engine}_monitoring_host'
    if key in app.extensions:
        return app.extensions[key]
    host = host_class(app, shared_host)
    app.extensions[key] = host
    atexit.register(host.close)
    from flask import Blueprint, jsonify, request
    from flask_security import current_user
    from pgadmin.user_login_check import pga_login_required
    api = Blueprint(f'cdeadmin_{engine}_monitoring', __name__)

    @api.route(f'/cdeadmin/api/monitoring/{engine}', methods=['GET'])
    @pga_login_required
    def fleet():
        try:
            response = jsonify(success=1, data=host.fleet(current_user.id))
            response.headers['Cache-Control'] = 'no-store'
            return response
        except PermissionError:
            return jsonify(success=0, errormsg='Monitoring scope is not authorized'), 403
        except Exception:
            return jsonify(success=0, errormsg='Monitoring inventory is unavailable'), 503

    @api.route(f'/cdeadmin/api/monitoring/{engine}/definition', methods=['GET', 'PUT', 'POST'])
    @pga_login_required
    def definition():
        from .assets import service_for_app, ProjectAssetError, ProjectAssetConflict, ProjectAssetForbidden
        from .dashboard_definitions import DashboardDefinitions
        from .dashboard_validation import validate_dashboard
        try:
            text = request.args.get('sid')
            sid = int(text) if text is not None else None
            target = request.args.get('target_id')
            if target == '' or (target is not None and len(target) > 255):
                raise ValueError('Invalid target')
            definitions = DashboardDefinitions(service_for_app(app), host.definition_scope,
                lambda snapshot, scope: validate_dashboard(snapshot, scope,
                    app.config.get('CDEADMIN_DDN_NODE', 'node'), engine=engine))
            if request.method == 'GET':
                data = (definitions.published(current_user.id, sid, target) if request.args.get('published') == '1'
                    else definitions.read(current_user.id, sid, target))
            elif request.method == 'POST':
                data = definitions.publish(current_user.id, sid, target, request.get_json(silent=True))
            else:
                data = definitions.save(current_user.id, sid, target, request.get_json(silent=True))
            response = jsonify(success=1, data=data)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except (PermissionError, ProjectAssetForbidden):
            return jsonify(success=0, errormsg='Dashboard scope is not authorized'), 403
        except ProjectAssetConflict:
            return jsonify(success=0, code='asset_conflict', errormsg='Dashboard version changed; reopen before saving.'), 409
        except (ProjectAssetError, ValueError, TypeError):
            return jsonify(success=0, errormsg='Invalid dashboard draft'), 400
        except Exception:
            return jsonify(success=0, errormsg='Dashboard draft request failed'), 503

    @api.route(f'/cdeadmin/api/monitoring/{engine}/<int:sid>', methods=['GET', 'POST', 'DELETE'])
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
            response = jsonify(success=1, data=data)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except PermissionError:
            return jsonify(success=0, errormsg='Monitoring scope is not authorized'), 403
        except (ValueError, TypeError):
            return jsonify(success=0, errormsg='Invalid monitoring policy'), 400
        except Exception:
            return jsonify(success=0, errormsg='Monitoring request failed'), 503
    app.register_blueprint(api)
    return host
