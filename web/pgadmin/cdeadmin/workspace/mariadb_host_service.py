"""Workspace service for MariaDB host configuration, validation, datadir initialization & service control."""
import atexit
from copy import deepcopy
import os
from pathlib import Path
import time
import uuid

from ..operations.fileio import exclusive_file_lock, private_directory, private_file
from ..operations.store import JsonOperationStore
from ..providers.mysql_family import mariadb_host_services as native
from ..providers.mysql_family.mariadb_host_services import MariaDBHostError
from ..providers.mysql_family.mariadb_physical import canonical_digest
from .mariadb_physical_service import _acquire_password, _admitted_endpoint, _client_and_route
from .mysql_binlog_jobs import identity


OPERATIONS = frozenset({
    'deploy_config',
    'initialize_data',
    'service_start',
    'service_stop',
    'service_restart',
    'service_boot_policy',
})


class MariaDBHostJobStore:
    def __init__(self, store_path, root_dir):
        self.store_path = Path(store_path).resolve()
        self.root = Path(root_dir).resolve()
        self.store_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_directory(self.root)

    def close(self):
        pass

    def _with_store(self, fn):
        lock_file = self.store_path.parent / (self.store_path.name + '.lock')
        with lock_file.open('a+b') as lf:
            private_file(lock_file)
            with exclusive_file_lock(lf.fileno()):
                return fn(JsonOperationStore(self.store_path))

    def job_dir(self, owner, endpoint_id, job_id):
        d = self.root / str(owner) / identity(endpoint_id) / identity(job_id)
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_directory(d)
        return d

    def service_state_dir(self, owner, endpoint_id):
        d = self.root / str(owner) / identity(endpoint_id) / 'managed-daemon-state'
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_directory(d)
        return d

    def save_record(self, rec):
        jid = rec['job_id']
        def _w(store):
            store.change(lambda doc: doc.setdefault('jobs', {}).update({jid: deepcopy(rec)}))
            return deepcopy(store.read()['jobs'][jid])
        out = self._with_store(_w)
        out.pop('owner', None)
        if isinstance(out.get('options'), dict) and 'replacement_text' in out['options']:
            out['options']['replacement_sha256'] = canonical_digest(out['options']['replacement_text'])
        return out

    def load(self, job_id, owner, endpoint_id):
        jid = identity(job_id)
        ep = identity(endpoint_id)
        def _r(store):
            rec = store.read().get('jobs', {}).get(jid)
            if rec is None or rec['owner'] != owner or rec['endpoint_id'] != ep:
                raise MariaDBHostError('Select an owned MariaDB host management job')
            return deepcopy(rec)
        return self._with_store(_r)

    def list(self, owner, endpoint_id, offset=0, limit=25):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise MariaDBHostError('Invalid MariaDB host job page bounds')
        ep = identity(endpoint_id)
        def _r(store):
            return [
                deepcopy(r) for r in store.read().get('jobs', {}).values()
                if r['owner'] == owner and r['endpoint_id'] == ep
            ]
        items = sorted(self._with_store(_r), key=lambda r: (r['created_at'], r['job_id']), reverse=True)
        for it in items:
            it.pop('owner', None)
        return {'jobs': items[offset:offset + limit], 'total': len(items), 'offset': offset, 'limit': limit}


def manager(service, server):
    from flask import current_app
    owner, endpoint, _ctx = _admitted_endpoint(service, server, required_perms=('administer',))
    store = getattr(service.operation_bus, 'store', None)
    if not isinstance(store, JsonOperationStore):
        raise MariaDBHostError('MariaDB host management requires durable application storage')
    with service._semantic_lock:
        jobs = getattr(service, 'mariadb_host_jobs', None)
        if jobs is None:
            root = (
                current_app.config.get('CDEADMIN_MARIADB_HOST_ROOT')
                or str(store.path.parent / 'mariadb-host-services')
            )
            jobs = service.mariadb_host_jobs = MariaDBHostJobStore(
                str(store.path) + '.mariadb-host', root
            )
            atexit.register(jobs.close)
    return jobs, owner, endpoint


def action(service, server, operation, request):
    if not isinstance(request, dict):
        raise MariaDBHostError('Select a MariaDB host operation request')
    jobs, owner, endpoint = manager(service, server)

    if operation == 'inspect_config':
        if set(request) != {'configuration_file'}:
            raise MariaDBHostError('Supply configuration_file to inspect')
        return native.inspect_option_file_graph(request['configuration_file'])

    if operation == 'validate_config':
        allowed = {'mariadbd_binary', 'configuration_file', 'basedir', 'lc_messages_dir', 'version_prefix'}
        if not {'configuration_file'} <= set(request) or set(request) - allowed:
            raise MariaDBHostError('Supply configuration_file and optional mariadbd_binary/basedir')
        return native.validate_option_file_natively(
            request.get('mariadbd_binary') or os.environ.get('CDEADMIN_MARIADBD_BINARY', 'mariadbd'),
            request['configuration_file'],
            basedir=request.get('basedir'),
            lc_messages_dir=request.get('lc_messages_dir'),
            version_prefix=request.get('version_prefix'),
        )

    if operation == 'service_status':
        state_dir = request.get('state_dir') or str(jobs.service_state_dir(owner, endpoint.id))
        return native.control_managed_service(
            action='status',
            service_mode=request.get('service_mode', 'managed_daemon'),
            state_dir=state_dir,
            systemd_unit=request.get('systemd_unit', 'mariadb.service'),
        )

    if operation == 'verify_readiness':
        client, route = _client_and_route(service, server)
        pw = _acquire_password(client, route)
        return native.verify_sql_readiness(
            host=request.get('host') or route.get('host') or '127.0.0.1',
            port=int(request.get('port') or route.get('port', 3306)),
            socket_path=request.get('socket_path') or route.get('unix_socket'),
            db_user=request.get('db_user') or route.get('user') or 'root',
            db_password=request.get('db_password', pw),
            expected_datadir=request.get('expected_datadir'),
            expected_server_uid=request.get('expected_server_uid'),
            timeout_seconds=int(request.get('timeout_seconds', 30)),
        )

    if operation == 'list':
        if set(request) - {'offset', 'limit'}:
            raise MariaDBHostError('Invalid MariaDB host job list request')
        return jobs.list(owner, endpoint.id, **request)

    if operation == 'status':
        if set(request) != {'job_id'}:
            raise MariaDBHostError('Select one MariaDB host job')
        rec = jobs.load(request['job_id'], owner, endpoint.id)
        rec.pop('owner', None)
        return rec

    if operation == 'rollback_config':
        if set(request) != {'job_id', 'confirmed'} or request['confirmed'] is not True:
            raise MariaDBHostError('Confirm rolling back one deployed MariaDB option file')
        rec = jobs.load(request['job_id'], owner, endpoint.id)
        if rec['host_operation'] != 'deploy_config' or rec['state'] != 'completed':
            raise MariaDBHostError('Select a completed MariaDB deploy_config job for rollback')
        jdir = jobs.job_dir(owner, endpoint.id, rec['job_id'])
        rb = native.rollback_deployed_option_file(jdir)
        rec.update(state='rolled_back', rollback_result=rb, rolled_back_at=time.time())
        return jobs.save_record(rec)

    if operation == 'review':
        if set(request) != {'options'} or not isinstance(request['options'], dict):
            raise MariaDBHostError('Supply options to review a MariaDB host operation')
        opts = deepcopy(request['options'])
        op_kind = opts.get('operation')
        if op_kind not in OPERATIONS:
            raise MariaDBHostError(f'Select a supported MariaDB host operation: {sorted(OPERATIONS)}')

        mariadbd_bin = opts.get('mariadbd_binary') or os.environ.get('CDEADMIN_MARIADBD_BINARY', 'mariadbd')
        opts['mariadbd_binary'] = mariadbd_bin
        preflight = {}
        warnings = [
            'Host configuration and service actions execute explicitly on the authorized MariaDB host.',
            'Service process completion and SQL wire readiness are verified independently.',
        ]

        if op_kind == 'deploy_config':
            graph_before = native.inspect_option_file_graph(opts['configuration_file'])
            target_meta = graph_before['files'][0]
            with Path(jobs.root).joinpath(f'.rev-val-{uuid.uuid4().hex}.cnf').open('wb') as tmp_f:
                tmp_path = Path(tmp_f.name)
                private_file(tmp_path)
                content = opts.get('replacement_text', '')
                if not isinstance(content, str) or '\x00' in content:
                    tmp_path.unlink(missing_ok=True)
                    raise MariaDBHostError('Supply valid UTF-8 replacement_text')
                tmp_f.write((content if content.endswith('\n') else content + '\n').encode('utf-8'))
            try:
                val = native.validate_option_file_natively(
                    mariadbd_bin, tmp_path,
                    basedir=opts.get('basedir'),
                    lc_messages_dir=opts.get('lc_messages_dir'),
                    version_prefix=opts.get('version_prefix'),
                )
            finally:
                tmp_path.unlink(missing_ok=True)
            if not val['valid']:
                raise MariaDBHostError(
                    'Candidate option file failed native mariadbd --help --verbose validation: '
                    + '; '.join(val['diagnostics'])
                )
            opts['expected_original_sha256'] = target_meta['sha256']
            preflight = {'before_graph': graph_before, 'candidate_validation': val}
            warnings.append('Deploying an option file creates a 0600 backup and replaces atomically without restarting mariadbd.')

        elif op_kind == 'initialize_data':
            install_bin = opts.get('install_db_binary') or os.environ.get('CDEADMIN_MARIADB_INSTALL_DB_BINARY', 'mariadb-install-db')
            opts['install_db_binary'] = install_bin
            ddir = native.safe_absolute_path(opts.get('datadir'), 'datadir')
            if ddir.exists() and any(ddir.iterdir()):
                raise MariaDBHostError('Target datadir is non-empty; mariadb-install-db requires an empty datadir')
            admitted = native.admit_install_db_script(install_bin, mariadbd_bin, version_prefix=opts.get('version_prefix'))
            preflight = {'datadir': str(ddir), 'tool': admitted}
            warnings.append('Datadir initialization creates MariaDB system tables without starting a network listener.')

        elif op_kind in {'service_start', 'service_stop', 'service_restart', 'service_boot_policy'}:
            if op_kind in {'service_stop', 'service_restart'} and opts.get('disconnect_all_clients') is not True:
                raise MariaDBHostError('Confirm disconnect_all_clients=True before stopping or restarting MariaDB')
            state_dir = opts.get('state_dir') or str(jobs.service_state_dir(owner, endpoint.id))
            opts['state_dir'] = state_dir
            preflight = native.control_managed_service(
                action='status',
                service_mode=opts.get('service_mode', 'managed_daemon'),
                state_dir=state_dir,
                systemd_unit=opts.get('systemd_unit', 'mariadb.service'),
            )

        jid = str(uuid.uuid4())
        rec = {
            'job_id': jid,
            'owner': owner,
            'endpoint_id': endpoint.id,
            'host_operation': op_kind,
            'state': 'reviewed',
            'options': opts,
            'preflight': preflight,
            'warnings': warnings,
            'created_at': time.time(),
            'expires_at': time.time() + 600,
            'automatic_retry': False,
        }
        rec['review_digest'] = canonical_digest({
            'job_id': jid,
            'host_operation': op_kind,
            'options': opts,
            'preflight': preflight,
        })
        return jobs.save_record(rec)

    if operation == 'start':
        if set(request) != {'job_id', 'review_digest', 'confirmed'} or request['confirmed'] is not True:
            raise MariaDBHostError('Confirm the exact MariaDB host review before execution')
        rec = jobs.load(request['job_id'], owner, endpoint.id)
        if rec['review_digest'] != request['review_digest']:
            raise MariaDBHostError('MariaDB host review_digest mismatch')
        if rec['state'] != 'reviewed':
            rec.pop('owner', None)
            return rec
        if time.time() > rec['expires_at']:
            raise MariaDBHostError('MariaDB host review expired')

        opts = rec['options']
        op_kind = rec['host_operation']
        jdir = jobs.job_dir(owner, endpoint.id, rec['job_id'])
        rec['state'] = 'executing'
        jobs.save_record(rec)

        try:
            if op_kind == 'deploy_config':
                res = native.deploy_option_file_atomically(
                    mariadbd_binary=opts['mariadbd_binary'],
                    target_config_path=opts['configuration_file'],
                    replacement_text=opts['replacement_text'],
                    job_dir=jdir,
                    expected_original_sha256=opts.get('expected_original_sha256'),
                    basedir=opts.get('basedir'),
                    lc_messages_dir=opts.get('lc_messages_dir'),
                    version_prefix=opts.get('version_prefix'),
                )
            elif op_kind == 'initialize_data':
                res = native.initialize_datadir(
                    install_db_binary=opts['install_db_binary'],
                    mariadbd_binary=opts['mariadbd_binary'],
                    datadir=opts['datadir'],
                    job_dir=jdir,
                    auth_root_method=opts.get('auth_root_method', 'normal'),
                    daemon_user=opts.get('daemon_user'),
                    basedir=opts.get('basedir'),
                    skip_test_db=bool(opts.get('skip_test_db', True)),
                    version_prefix=opts.get('version_prefix'),
                )
            else:
                client, route = _client_and_route(service, server)
                pw = _acquire_password(client, route)
                verb = {
                    'service_start': 'start',
                    'service_stop': 'stop',
                    'service_restart': 'restart',
                    'service_boot_policy': 'set_boot_policy',
                }[op_kind]
                res = native.control_managed_service(
                    action=verb,
                    service_mode=opts.get('service_mode', 'managed_daemon'),
                    state_dir=opts['state_dir'],
                    mariadbd_binary=opts['mariadbd_binary'],
                    defaults_file=opts.get('configuration_file'),
                    datadir=opts.get('datadir'),
                    port=opts.get('port'),
                    bind_address=opts.get('bind_address', '127.0.0.1'),
                    daemon_user=opts.get('daemon_user'),
                    basedir=opts.get('basedir'),
                    plugin_dir=opts.get('plugin_dir'),
                    lc_messages_dir=opts.get('lc_messages_dir'),
                    extra_args=opts.get('extra_args', ()),
                    db_user=opts.get('db_user') or route.get('user') or 'root',
                    db_password=opts.get('db_password', pw),
                    systemd_unit=opts.get('systemd_unit', 'mariadb.service'),
                    boot_enabled=opts.get('boot_enabled'),
                    version_prefix=opts.get('version_prefix'),
                )
                if verb in {'start', 'restart'} and opts.get('verify_sql_readiness', True):
                    daemon_info = res.get('daemon') or {}
                    readiness = native.verify_sql_readiness(
                        host=daemon_info.get('bind_address', '127.0.0.1'),
                        port=int(daemon_info.get('port') or opts.get('port') or route.get('port', 3306)),
                        db_user=opts.get('db_user') or route.get('user') or 'root',
                        db_password=opts.get('db_password', pw),
                        expected_datadir=daemon_info.get('datadir') or opts.get('datadir'),
                    )
                    res['independent_sql_readiness'] = readiness
                    res['sql_readiness_verified'] = readiness['sql_readiness_verified']

            rec.update(state='completed', result=res, finished_at=time.time())
            return jobs.save_record(rec)
        except BaseException as exc:
            rec.update(
                state='failed',
                error_type=type(exc).__name__,
                error_message=str(exc),
                finished_at=time.time(),
            )
            jobs.save_record(rec)
            raise

    raise MariaDBHostError(f'Unknown MariaDB host action: {operation!r}')
