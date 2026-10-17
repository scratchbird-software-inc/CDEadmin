"""PostgreSQL collection with persisted-owner checks and sealed worker grants."""
import atexit
import base64
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
                              'metadata_interval_seconds','native_metric_sources'})

    def __init__(self, app, shared_host):
        super().__init__(app, shared_host.endpoints)
        self.ownership = shared_host.ownership
        self.keys = shared_host.keys
        self._admissions = {}
        self._issuing_permissions = {}

    @staticmethod
    def _native_registration(server):
        from pgadmin.cdeadmin.providers.postgresql.provider import (
            PROVIDER_ID, PROVIDER_VERSION, PROFILE_ID, PROFILE_VERSION)
        endpoint = getattr(server, 'endpoint_profile', None)
        if endpoint is None or endpoint.provider_id != PROVIDER_ID:
            return False
        # Preserved registrations predate provider revisions. Managed native
        # registrations must match the installed, qualified adapter exactly.
        return endpoint.provider_version is None or (
            endpoint.provider_version == PROVIDER_VERSION and
            endpoint.profile_id == PROFILE_ID and
            endpoint.profile_version == PROFILE_VERSION)

    def _owned_server(self, owner, sid):
        from pgadmin.model import Server, User
        server = Server.query.filter_by(id=sid, user_id=owner).first()
        if (server is None or User.query.filter_by(id=owner, active=True).first() is None or
                server.endpoint_profile is None or
                not self._native_registration(server)):
            raise PermissionError('PostgreSQL monitoring endpoint is unavailable')
        return server

    @staticmethod
    def _configuration(server):
        # Persisted encrypted credential changes revoke the old grant too.
        values = {name: getattr(server, name, None) for name in (
            'host', 'port', 'username', 'role', 'maintenance_db', 'service',
            'use_ssh_tunnel', 'kerberos_conn', 'connection_params', 'passexec_cmd')}
        values['credential_revision'] = str(server.password)
        values['ssh_configuration'] = {name: getattr(server, name, None) for name in (
            'tunnel_host', 'tunnel_port', 'tunnel_username', 'tunnel_authentication',
            'tunnel_identity_file', 'tunnel_keep_alive', 'tunnel_password')}
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
        if server.kerberos_conn and not dedicated:
            raise ValueError('Independent Kerberos monitoring is not yet admitted')
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
        transport_secrets = {}
        if server.service:
            route.update(self._resolved_service(connection, secrets=transport_secrets))
        else:
            route['connection_params'] = self._direct_options(route['connection_params'])
        if server.kerberos_conn:
            route['connection_params'].update(gssencmode='disable',
                require_auth='password,md5,scram-sha-256')
        tls_password = route['connection_params'].pop('sslpassword', None)
        if tls_password:
            transport_secrets['tls_private_key_password'] = tls_password
        if oid is not None:
            route['database_oid'] = oid
        permission = None
        if not dedicated:
            encrypted = connection.password or manager.password
            present, crypt_key = get_crypt_key()
            if present and encrypted:
                # Closure exists only during synchronous grant issue, never in a worker.
                permission = SimpleNamespace(acquire_secret=lambda *_:
                    SecretLease(decrypt(encrypted, crypt_key)))
            elif server.service:
                current_password = connection.conn.info.password
                if not isinstance(current_password, str) or not current_password:
                    raise ValueError('Current connection password is unavailable; use a dedicated account')
                permission = SimpleNamespace(acquire_secret=lambda *_: SecretLease(current_password))
            else:
                raise ValueError('Current connection password is unavailable; use a dedicated account')
        if server.use_ssh_tunnel:
            ssh, secrets = self._ssh_admission(server, manager)
            route.update(ssh=ssh, port=ssh['remote_port'], transport_source='dedicated-ssh')
            transport_secrets.update(secrets)
        if transport_secrets:
            secrets = transport_secrets
            references = {kind: 'registration-' + kind for kind in secrets}
            route['credential_references'] = references
            database_permission = permission
            def acquire(reference, principal, purpose, kind):
                if principal != route['principal_reference'] or purpose != 'connect':
                    raise PermissionError('Monitoring credential scope changed')
                if kind in secrets and reference == references[kind]:
                    return SecretLease(secrets[kind])
                if kind == 'database_password' and database_permission is not None:
                    return database_permission.acquire_secret(reference, principal, purpose, kind)
                raise PermissionError('Monitoring credential is unavailable')
            permission = SimpleNamespace(acquire_secret=acquire)
        return {'endpoint_id': server.endpoint_profile.id,
                'generation': server.endpoint_profile.profile_generation or server.endpoint_profile.cache_namespace,
                'configuration': self._configuration(server), 'route': route}, permission

    @staticmethod
    def _ssh_admission(server, manager):
        from pgadmin.cdeadmin.providers.postgresql.monitoring_ssh import validate_ssh_route
        from pgadmin.utils import get_complete_file_path
        from pgadmin.utils.crypto import decrypt
        from pgadmin.utils.master_password import get_crypt_key
        tunnel = manager.tunnel_object
        if (tunnel is None or not tunnel.is_active or not tunnel._transport.is_authenticated() or
                len(tunnel._remote_binds) != 1 or
                server.tunnel_host != manager.tunnel_host or
                (server.tunnel_port or 22) != manager.tunnel_port or
                server.tunnel_username != manager.tunnel_username or
                (server.tunnel_authentication or 0) != manager.tunnel_authentication or
                (manager.tunnel_authentication == 1 and
                 server.tunnel_identity_file != manager.tunnel_identity_file) or
                (server.host, server.port) != tunnel._remote_binds[0]):
            raise ValueError('Reconnect the selected SSH registration before configuring monitoring')
        key = tunnel._transport.get_remote_server_key()
        ssh = {'host': manager.tunnel_host, 'port': int(manager.tunnel_port),
               'username': manager.tunnel_username, 'remote_host': tunnel._remote_binds[0][0],
               'remote_port': tunnel._remote_binds[0][1], 'host_key_type': key.get_name(),
               'host_key': base64.b64encode(key.asbytes()).decode('ascii'),
               'authentication': 'private_key' if manager.tunnel_authentication == 1 else 'password',
               'keep_alive': int(manager.tunnel_keep_alive)}
        validate_ssh_route(ssh)
        encrypted = manager.tunnel_password or getattr(server, 'tunnel_password', None)
        password = None
        if encrypted:
            present, crypt_key = get_crypt_key()
            if not present:
                raise ValueError('SSH credential authority is unavailable')
            password = decrypt(encrypted, crypt_key)
        if ssh['authentication'] == 'password':
            if not password:
                raise ValueError('The connected SSH password is unavailable')
            return ssh, {'ssh_password': password}
        path = get_complete_file_path(manager.tunnel_identity_file)
        with open(path, 'rb') as source:
            private_key = source.read(1024 * 1024 + 1)
        if not private_key or len(private_key) > 1024 * 1024:
            raise ValueError('The monitoring SSH key exceeds its admission limit')
        secrets = {'ssh_private_key': private_key}
        if password:
            secrets['ssh_private_key_password'] = password
        return ssh, secrets

    @staticmethod
    def _direct_options(parameters):
        """Resolve user storage paths while the admitting request owns access."""
        from pgadmin.utils import get_complete_file_path
        options = dict(parameters)
        for key in ('sslcert', 'sslkey', 'sslcrl', 'sslcrldir', 'sslrootcert'):
            if key in options and not (key == 'sslrootcert' and options[key] == 'system'):
                options[key] = get_complete_file_path(options[key])
        return options

    @staticmethod
    def _resolved_service(connection, *, secrets=None):
        """Freeze the selected native peer; collectors never re-resolve an alias."""
        from ..providers.postgresql.monitoring import CONNECTION_OPTIONS
        info = connection.conn.info
        parameters = dict(info.get_parameters())
        if 'sslpassword' in parameters and secrets is not None:
            password = parameters.pop('sslpassword')
            if password:
                secrets['tls_private_key_password'] = password
        replaced = {'service', 'host', 'port', 'dbname', 'user', 'application_name',
                    'fallback_application_name', 'client_encoding', 'passfile'}
        if set(parameters) - CONNECTION_OPTIONS - replaced - {'connect_timeout'}:
            raise ValueError('The service uses connection options not yet admitted for monitoring')
        host, database, user, port = info.host, info.dbname, info.user, info.port
        if (any(not isinstance(value, str) or not value or '\x00' in value for value in (host, database, user))
                or type(port) is not int or not 1 <= port <= 65535 or database != connection.db):
            raise ValueError('The service did not resolve a valid selected database endpoint')
        options = {key: value for key, value in parameters.items()
                   if key in CONNECTION_OPTIONS | {'connect_timeout'}}
        if info.hostaddr:
            options['hostaddr'] = info.hostaddr
        return {'host': host, 'port': port, 'database': database, 'user': user,
                'connection_params': options, 'transport_source': 'resolved-libpq-service'}

    def enable(self, owner, sid, target, body):
        database_oid(target)
        if not isinstance(body, dict) or set(body) - (self.policy_fields | {'credentials'}):
            raise ValueError('Unsupported PostgreSQL monitoring fields')
        if 'native_metric_sources' in body:
            from ..providers.postgresql.metrics import select_sources
            select_sources(body['native_metric_sources'])
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
                        'collection_available': self.available, 'navigation': navigation,
                        'history_available': self.history is not None}
            current = self._authorizer(owner, sid, target)
            result = self.runtime.snapshot(grant.policy, lambda policy, purpose:
                current(policy, purpose, grant.generation, grant.route_digest))
            return {**result, 'authentication': dict(grant.authentication), 'navigation': navigation,
                    'history_available': self.history is not None,
                    'policy': {field: getattr(grant.policy, field) for field in self.policy_fields}}

    def _historical_scope(self, owner, sid, target):
        # Historical owner/OID scope survives collector shutdown and does not
        # borrow or reconnect an interactive attachment. Configuration changes
        # during destination I/O invalidate the response.
        database_oid(target)
        with self.app.app_context():
            server = self._owned_server(owner, sid)
            return server.endpoint_profile.id, self._configuration(server)

    def historical(self, owner, sid, target, arguments):
        from .mysql_monitoring_host import MySQLMonitoringHost
        return MySQLMonitoringHost.historical(self, owner, sid, target, arguments)

    def disable(self, owner, sid, target):
        database_oid(target)
        with self._lock:
            result = super().disable(owner, sid, target)
            if result['released']:
                self._admissions.pop((owner, sid, target), None)
            return result

    def _registrations(self, owner):
        from pgadmin.model import Server, User
        with self.app.app_context():
            if User.query.filter_by(id=owner, active=True).first() is None:
                raise PermissionError('Monitoring owner is unavailable')
            return sorted([{'server_id': server.id, 'name': server.name}
                for server in Server.query.filter_by(user_id=owner).all()
                if server.endpoint_profile is not None and
                self._native_registration(server)],
                key=lambda row: (row['name'].casefold(), row['server_id']))

    def fleet(self, owner):
        def observation(sid, target):
            try:
                snapshot = self.snapshot(owner, sid, target)
                # Engine inventory needs only the current observation, not a
                # second copy of every collector's retained history.
                return {key: value for key, value in {
                    **snapshot, 'samples': snapshot.get('samples', [])[-1:],
                }.items() if key not in ('authentication', 'navigation')}
            except PermissionError:
                return {'state': 'authorization-denied', 'samples': []}
            except Exception:
                return {'state': 'scope-unavailable', 'samples': []}

        servers = []
        for registered in self._registrations(owner):
            sid = registered['server_id']
            with self._lock:
                targets = sorted([(key[2], item['route']['database'])
                    for key, item in self._admissions.items()
                    if key[:2] == (owner, sid) and key[2] is not None],
                    key=lambda row: (row[1].casefold(), row[0]))
            databases = []
            for target, name in targets:
                current = observation(sid, target)
                databases.append({'target_id': target,
                    'name': name if current['state'] not in ('authorization-denied', 'scope-unavailable') else 'Unavailable target',
                    'snapshot': current})
            servers.append({**registered, 'snapshot': observation(sid, None), 'databases': databases})
        return {'registered_endpoints': len(servers), 'servers': servers,
                'history': 'volatile', 'inventory': 'owner-registrations-and-configured-collectors'}

    def definition_scope(self, owner, sid, target):
        oid = database_oid(target)
        if sid is None:
            if target is not None:
                raise ValueError('Engine scope cannot include a database')
            self._registrations(owner)
            return {'engine': 'postgresql', 'kind': 'engine', 'owner': owner}
        server = self._owned_server(owner, sid)
        scope = {'engine': 'postgresql', 'kind': 'database' if oid else 'server',
                 'owner': owner, 'server_id': sid,
                 'endpoint_id': server.endpoint_profile.id,
                 'generation': server.endpoint_profile.profile_generation or server.endpoint_profile.cache_namespace}
        if oid is not None:
            from pgadmin.utils.driver.registry import DriverRegistry
            connection = DriverRegistry.get('psycopg3').connection_manager(sid).connection(did=oid)
            if not connection.connected() or not connection.db:
                raise PermissionError('Connect the selected database before editing its dashboard')
            scope.update(target_id=target, database=connection.db)
        return scope

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

    @api.route('/cdeadmin/api/monitoring/postgresql/sources',methods=['GET'])
    @pga_login_required
    def sources():
        if not current_user.is_authenticated:
            return jsonify(success=0,errormsg='Native metric sources require authentication'),403
        from ..providers.postgresql.metrics import source_catalog
        response=jsonify(success=1,data=source_catalog())
        response.headers['Cache-Control']='no-store'
        return response

    @api.route('/cdeadmin/api/monitoring/postgresql/<int:sid>/history', methods=['GET'])
    @pga_login_required
    def history(sid):
        try:
            data = host.historical(current_user.id, sid, request.args.get('target_id'), request.args)
            response = jsonify(success=1, data=data)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except PermissionError:
            return jsonify(success=0, errormsg='History scope is not authorized'), 403
        except (ValueError, TypeError):
            return jsonify(success=0, errormsg='Invalid history query'), 400
        except Exception:
            return jsonify(success=0, errormsg='Monitoring history is unavailable'), 503

    @api.route('/cdeadmin/api/monitoring/postgresql/definition', methods=['GET', 'PUT', 'POST'])
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
                    app.config.get('CDEADMIN_DDN_NODE', 'node'), engine='postgresql'))
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
            response = jsonify(success=1, data=data)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except (PermissionError, ProjectAssetForbidden):
            return jsonify(success=0, errormsg='Dashboard scope is not authorized'), 403
        except ProjectAssetConflict:
            return jsonify(success=0, code='asset_conflict',
                           errormsg='Dashboard draft changed; reopen before saving.'), 409
        except (ProjectAssetError, ValueError, TypeError):
            return jsonify(success=0, errormsg='Invalid dashboard draft'), 400
        except Exception:
            return jsonify(success=0, errormsg='Dashboard draft request failed'), 503

    @api.route('/cdeadmin/api/monitoring/postgresql', methods=['GET'])
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
