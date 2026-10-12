"""Owner-authorized Firebird monitoring for an admitted single web process."""

import atexit
import os
from pathlib import Path
import threading

from pgadmin.cdeadmin.report_scheduler.crypto import WorkerKeyRing
from .monitoring import MonitoringPolicy, MonitoringRuntime
from .monitoring_delegation import MonitoringGrant, route_fingerprint

APP_EXTENSION_KEY = 'cdeadmin_monitoring_host'
POLICY_FIELDS = frozenset({
    'interval_seconds', 'retain_samples', 'lease_seconds',
    'heartbeat_enabled', 'heartbeat_timeout_seconds',
    'metadata_interval_seconds',
    'max_transaction_age_seconds', 'max_backup_state_seconds',
    'require_wire_encryption', 'expected_encryption_state',
})


class MonitoringHostUnavailable(RuntimeError):
    pass


class ProcessOwnership:
    """Nonblocking OS lock: fail closed if another process owns this runtime.

    The lock file is never unlinked while another process could have it open.
    Windows locks one byte; POSIX locks the descriptor. This is not a distributed
    scheduler lease and is intended only for an explicitly single-process host.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.fd = None

    def acquire(self):
        if self.fd is not None:
            return
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b'0')
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(fd)
            raise MonitoringHostUnavailable(
                'Another process owns monitoring, or its lock is unavailable') from None
        self.fd = fd

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class MonitoringHost:
    engine = 'firebird'
    policy_fields = POLICY_FIELDS
    def __init__(self, app, endpoint_service):
        self.app = app
        self.endpoints = endpoint_service
        self.runtime = MonitoringRuntime()
        self.keys = WorkerKeyRing(
            app.config.get('CDEADMIN_MONITORING_WORKER_KEYS', {}),
            app.config.get('CDEADMIN_MONITORING_WORKER_ACTIVE_KEY_ID'))
        self.admitted = app.config.get('CDEADMIN_MONITORING_PROCESS_MODE') == 'single'
        path = app.config.get('CDEADMIN_MONITORING_LOCK_PATH')
        self.ownership = ProcessOwnership(path) if path else None
        self._grants = {}
        self._lock = threading.RLock()

    @property
    def available(self):
        return self.admitted and self.keys.available and self.ownership is not None

    def _owned_server(self, owner, sid):
        from pgadmin.model import Server, User
        server = Server.query.filter_by(id=sid, user_id=owner).first()
        user = User.query.filter_by(id=owner, active=True).first()
        if server is None or user is None or server.endpoint_profile is None:
            raise PermissionError('Monitoring endpoint is unavailable')
        if server.endpoint_profile.profile_id != 'firebird-native':
            raise PermissionError('This monitoring source requires native Firebird')
        return server

    def _scope(self, owner, sid, target):
        with self.app.app_context():
            server = self._owned_server(owner, sid)
            context, endpoint, _ = self.endpoints.workspace(
                server, database_target_id=target)
            binding = self.endpoints.provider_registry.resolve(context)
            return {
                'endpoint_id': server.endpoint_profile.id,
                'generation': (server.endpoint_profile.profile_generation or
                               server.endpoint_profile.cache_namespace),
                'route': endpoint['route'], 'permissions': binding.permissions,
            }

    def _authorizer(self, owner, sid, target):
        def authorize(policy, purpose, generation, digest):
            if policy.owner_id != owner or policy.target_id != target:
                return False
            scope = self._scope(owner, sid, target)
            return (scope['endpoint_id'] == policy.endpoint_id and
                    scope['generation'] == generation and
                    route_fingerprint(scope['route']) == digest)
        return authorize

    def enable(self, owner, sid, target, body):
        if not isinstance(body, dict) or set(body) - (self.policy_fields | {'credentials'}):
            raise ValueError('Unsupported monitoring policy fields')
        if 'credentials' in body and not isinstance(body['credentials'], dict):
            raise ValueError('Invalid monitoring credentials')
        if not self.available:
            raise MonitoringHostUnavailable(
                'Monitoring requires single-process admission, a worker key '
                'authority and a lock path')
        with self._lock:
            scope = self._scope(owner, sid, target)
            policy = MonitoringPolicy(
                owner, scope['endpoint_id'], target,
                **{'interval_seconds': 15 if target is None else 5,
                   **{key: value for key, value in body.items() if key != 'credentials'}})
            key = owner, sid, target
            previous = self._grants.get(key)
            if previous is not None:
                if 'credentials' in body:
                    raise ValueError('Stop collection before replacing credentials')
                previous.require(policy, 'configure')
                self.runtime.enable(policy, previous.open_source, previous.require)
                return {**self.runtime.snapshot(policy, previous.require),
                        'authentication': dict(previous.authentication)}
            self.ownership.acquire()
            grant = MonitoringGrant.issue(
                policy, scope['route'], scope['generation'], scope['permissions'],
                self.keys, self._authorizer(owner, sid, target),
                credentials=body.get('credentials'), engine=self.engine)
            try:
                self.runtime.enable(policy, grant.open_source, grant.require)
            except BaseException:
                grant.revoke()
                raise
            self._grants[key] = grant
            return {**self.runtime.snapshot(policy, grant.require),
                    'authentication': dict(grant.authentication)}

    def snapshot(self, owner, sid, target):
        with self.app.app_context():
            server = self._owned_server(owner, sid)
            targets = sorted([
                {'target_id': row.id, 'name': row.display_name}
                for row in server.endpoint_profile.database_targets
            ], key=lambda item: (item['name'].casefold(), item['target_id']))
            if target is not None and not any(row['target_id'] == target for row in targets):
                raise PermissionError('Monitoring target is unavailable')
            navigation = {'server_id': sid, 'name': server.name, 'databases': targets}
        with self._lock:
            grant = self._grants.get((owner, sid, target))
            if grant is None:
                result = {'state': 'disabled', 'samples': [], 'history': 'volatile',
                        'runtime_scope': 'this-process',
                        'collection_available': self.available, 'navigation': navigation}
            else:
                current = self._authorizer(owner, sid, target)
                result = self.runtime.snapshot(grant.policy, lambda policy, purpose:
                    current(policy, purpose, grant.generation, grant.route_digest))
                result = {**result, 'navigation': navigation,
                          'authentication': dict(grant.authentication)}
        if target is None:
            from .monitoring_fleet import aggregate, observation
            databases = []
            for registered in targets:
                try:
                    current = self.snapshot(owner, sid, registered['target_id'])
                except PermissionError:
                    current = {'state': 'authorization-denied'}
                except Exception:
                    current = {'state': 'scope-unavailable'}
                databases.append({**registered, **observation(current, 'database')})
            result['databases'] = databases
            result['aggregate'] = aggregate(databases)
        return result

    def inspect_statement(self, owner, sid, target, reference):
        if target is None:
            raise ValueError('Statement inspection requires a database')
        # Resolving the ordinary snapshot checks ownership and registration;
        # the runtime rechecks current authorization before and after I/O.
        self.snapshot(owner, sid, target)
        with self._lock:
            grant = self._grants.get((owner, sid, target))
            if grant is None:
                return {'status': 'unavailable', 'reason': 'collector-disabled'}
            current = self._authorizer(owner, sid, target)
            return self.runtime.inspect_statement(grant.policy,
                lambda policy, purpose: current(policy, purpose, grant.generation, grant.route_digest), reference)

    def inspect_details(self, owner, sid, target, reference):
        if isinstance(reference, dict) and reference.get('operation') == 'receipts':
            if set(reference) != {'sample_id', 'operation'}:
                raise ValueError('Invalid receipt inspection reference')
            from datetime import datetime, timezone
            from .monitoring_receipts import project_receipts
            from pgadmin.cdeadmin.operations import service_for_app
            with self.app.app_context():
                server = self._owned_server(owner, sid)
                database = None
                if target is not None:
                    registered = next((row for row in server.endpoint_profile.database_targets
                                       if row.id == target), None)
                    if registered is None:
                        raise PermissionError('Monitoring target is unavailable')
                    database = registered.database
                records = service_for_app(self.app).list_provider_audit(
                    server.endpoint_profile.id, 'user:' + str(owner))
                result = project_receipts(records, database)
                self._owned_server(owner, sid)
                return {**result, 'observed_at': datetime.now(timezone.utc).isoformat()}
        self.snapshot(owner, sid, target)
        with self._lock:
            grant = self._grants.get((owner, sid, target))
            if grant is None:
                return {'status': 'unavailable', 'reason': 'collector-disabled'}
            current = self._authorizer(owner, sid, target)
            return self.runtime.inspect_details(grant.policy,
                lambda policy, purpose: current(policy, purpose, grant.generation, grant.route_digest), reference)

    def fleet(self, owner):
        from pgadmin.model import Server, User
        from .monitoring_fleet import fleet_snapshot
        with self.app.app_context():
            if User.query.filter_by(id=owner, active=True).first() is None:
                raise PermissionError('Monitoring owner is unavailable')
            registrations = []
            for server in Server.query.filter_by(user_id=owner).all():
                profile = server.endpoint_profile
                if profile is None or profile.profile_id != 'firebird-native':
                    continue
                registrations.append({
                    'server_id': server.id, 'name': server.name,
                    'databases': sorted([
                        {'target_id': target.id, 'name': target.display_name}
                        for target in profile.database_targets
                    ], key=lambda item: (item['name'].casefold(), item['target_id'])),
                })
            registrations.sort(key=lambda item: (item['name'].casefold(), item['server_id']))
            return fleet_snapshot(registrations, lambda sid, target:
                                  self.snapshot(owner, sid, target))

    def definition_scope(self, owner, sid, target):
        from pgadmin.model import User
        if User.query.filter_by(id=owner, active=True).first() is None:
            raise PermissionError('Dashboard owner is unavailable')
        if sid is None:
            if target is not None:
                raise ValueError('Engine scope has no database target')
            return {'engine': 'firebird', 'kind': 'engine', 'owner': owner}
        server = self._owned_server(owner, sid)
        if target is not None and not any(
                row.id == target for row in server.endpoint_profile.database_targets):
            raise PermissionError('Dashboard target is unavailable')
        return {'engine': 'firebird', 'kind': 'database' if target else 'server',
                'owner': owner, 'endpoint_id': server.endpoint_profile.id,
                'target_id': target}

    def disable(self, owner, sid, target):
        # Ownership permits cleanup even after verification/route changes.
        with self.app.app_context():
            self._owned_server(owner, sid)
        with self._lock:
            key = owner, sid, target
            grant = self._grants.get(key)
            if grant is None:
                return {'state': 'disabled', 'released': True}
            grant.revoke()
            released = self.runtime.disable(
                grant.policy, lambda policy, purpose: policy.owner_id == owner)
            if released:
                del self._grants[key]
            return {'state': 'disabled' if released else 'release-unconfirmed',
                    'released': released}

    def close(self):
        with self._lock:
            postgres = self.app.extensions.get('cdeadmin_postgresql_monitoring_host')
            postgres_released = postgres.close() if postgres is not None else True
            mysql = self.app.extensions.get('cdeadmin_mysql_monitoring_host')
            mysql_released = mysql.close() if mysql is not None else True
            for grant in self._grants.values():
                grant.revoke()
            released = self.runtime.close()
            released = released and postgres_released and mysql_released
            if released and self.ownership is not None:
                self.ownership.close()
            return released


def init_app(app, endpoint_service):
    if APP_EXTENSION_KEY in app.extensions:
        return app.extensions[APP_EXTENSION_KEY]
    host = MonitoringHost(app, endpoint_service)
    app.extensions[APP_EXTENSION_KEY] = host
    atexit.register(host.close)
    from flask import Blueprint, jsonify, request
    from flask_security import current_user
    from pgadmin.user_login_check import pga_login_required

    api = Blueprint('cdeadmin_monitoring', __name__)

    @api.route('/cdeadmin/api/monitoring/firebird/definition', methods=['GET', 'PUT', 'POST'])
    @pga_login_required
    def definition():
        from .assets import (service_for_app, ProjectAssetError,
                             ProjectAssetConflict, ProjectAssetForbidden)
        from .dashboard_definitions import DashboardDefinitions
        try:
            sid_text = request.args.get('sid')
            sid = int(sid_text) if sid_text is not None else None
            target = request.args.get('target_id')
            if target == '' or (target is not None and len(target) > 255):
                raise ValueError('Invalid target')
            from .dashboard_validation import validate_dashboard
            definitions = DashboardDefinitions(service_for_app(app), host.definition_scope,
                lambda snapshot, scope: validate_dashboard(snapshot, scope,
                    app.config.get('CDEADMIN_DDN_NODE', 'node')))
            if request.method == 'GET':
                data = (definitions.published(current_user.id, sid, target)
                        if request.args.get('published') == '1' else
                        definitions.read(current_user.id, sid, target))
            elif request.method == 'POST':
                data = definitions.publish(current_user.id, sid, target,
                                           request.get_json(silent=True))
            else:
                data = definitions.save(current_user.id, sid, target,
                                        request.get_json(silent=True))
            return jsonify(success=1, data=data)
        except (PermissionError, ProjectAssetForbidden):
            return jsonify(success=0, errormsg='Dashboard scope is not authorized'), 403
        except ProjectAssetConflict:
            return jsonify(success=0, code='asset_conflict',
                           errormsg='Dashboard draft changed; reopen before saving.'), 409
        except (ProjectAssetError, ValueError, TypeError):
            return jsonify(success=0, errormsg='Invalid dashboard draft'), 400
        except Exception:
            return jsonify(success=0, errormsg='Dashboard draft request failed'), 503

    @api.route('/cdeadmin/api/monitoring/firebird', methods=['GET'])
    @pga_login_required
    def fleet():
        try:
            return jsonify(success=1, data=host.fleet(current_user.id))
        except PermissionError:
            return jsonify(success=0, errormsg='Monitoring scope is not authorized'), 403
        except Exception:
            return jsonify(success=0, errormsg='Monitoring inventory is unavailable'), 503

    @api.route('/cdeadmin/api/monitoring/firebird/<int:sid>',
               methods=['GET', 'POST', 'DELETE'])
    @pga_login_required
    def monitoring(sid):
        target = request.args.get('target_id')
        if target == '' or (target is not None and len(target) > 255):
            return jsonify(success=0, errormsg='Invalid monitoring target'), 400
        try:
            if request.method == 'GET':
                data = host.snapshot(current_user.id, sid, target)
            elif request.method == 'DELETE':
                data = host.disable(current_user.id, sid, target)
            else:
                data = host.enable(current_user.id, sid, target,
                                   request.get_json(silent=True))
            return jsonify(success=1, data=data)
        except PermissionError:
            return jsonify(success=0, errormsg='Monitoring scope is not authorized'), 403
        except MonitoringHostUnavailable as error:
            return jsonify(success=0, errormsg=str(error)), 503
        except (ValueError, TypeError):
            return jsonify(success=0, errormsg='Invalid monitoring policy'), 400
        except Exception:
            # Native/credential diagnostics must not be exposed through HTTP.
            return jsonify(success=0, errormsg='Monitoring request failed'), 503

    @api.route('/cdeadmin/api/monitoring/firebird/<int:sid>/statement', methods=['POST'])
    @pga_login_required
    def statement(sid):
        target = request.args.get('target_id')
        if not target or len(target) > 255:
            return jsonify(success=0, errormsg='Invalid monitoring target'), 400
        try:
            result = host.inspect_statement(current_user.id, sid, target, request.get_json(silent=True))
            response = jsonify(success=1, data=result)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except PermissionError:
            return jsonify(success=0, errormsg='Monitoring scope is not authorized'), 403
        except (ValueError, TypeError):
            return jsonify(success=0, errormsg='Invalid statement inspection identity'), 400
        except Exception:
            return jsonify(success=0, errormsg='Statement inspection is unavailable'), 503

    @api.route('/cdeadmin/api/monitoring/firebird/<int:sid>/details', methods=['POST'])
    @pga_login_required
    def details(sid):
        target = request.args.get('target_id')
        if target == '' or (target is not None and len(target) > 255):
            return jsonify(success=0, errormsg='Invalid monitoring target'), 400
        try:
            result = host.inspect_details(current_user.id, sid, target, request.get_json(silent=True))
            response = jsonify(success=1, data=result)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except PermissionError:
            return jsonify(success=0, errormsg='Monitoring scope is not authorized'), 403
        except (ValueError, TypeError):
            return jsonify(success=0, errormsg='Invalid monitoring detail reference'), 400
        except Exception:
            return jsonify(success=0, errormsg='Monitoring details are unavailable'), 503

    app.register_blueprint(api)
    from .postgresql_monitoring_host import init_app as init_postgresql
    init_postgresql(app, host)
    from .mysql_monitoring_host import init_app as init_mysql
    init_mysql(app, host)
    return host
