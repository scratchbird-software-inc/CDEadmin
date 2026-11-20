"""Workspace service for MariaDB host & system-table upgrade workflows (11.8 -> 12.2.2)."""
import atexit
from copy import deepcopy
import os
from pathlib import Path
import time
import uuid

from ..operations.fileio import exclusive_file_lock, private_directory, private_file
from ..operations.store import JsonOperationStore
from ..providers.mysql_family import mariadb_host_upgrade as native
from ..providers.mysql_family.mariadb_host_services import control_managed_service
from ..providers.mysql_family.mariadb_host_upgrade import MariaDBUpgradeError
from ..providers.mysql_family.mariadb_physical import canonical_digest
from .mariadb_physical_service import _acquire_password, _admitted_endpoint, _client_and_route
from .mysql_binlog_jobs import identity


class MariaDBUpgradeJobStore:
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

    def save_record(self, rec):
        jid = rec['job_id']
        def _w(store):
            store.change(lambda doc: doc.setdefault('jobs', {}).update({jid: deepcopy(rec)}))
            return deepcopy(store.read()['jobs'][jid])
        out = self._with_store(_w)
        out.pop('owner', None)
        return out

    def load(self, job_id, owner, endpoint_id):
        jid = identity(job_id)
        ep = identity(endpoint_id)
        def _r(store):
            rec = store.read().get('jobs', {}).get(jid)
            if rec is None or rec['owner'] != owner or rec['endpoint_id'] != ep:
                raise MariaDBUpgradeError('Select an owned MariaDB upgrade job')
            return deepcopy(rec)
        return self._with_store(_r)

    def list(self, owner, endpoint_id, offset=0, limit=25):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise MariaDBUpgradeError('Invalid MariaDB upgrade job page bounds')
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
    owner, endpoint, _ctx = _admitted_endpoint(service, server, required_perms=('upgrade_admin', 'administer'))
    store = getattr(service.operation_bus, 'store', None)
    if not isinstance(store, JsonOperationStore):
        raise MariaDBUpgradeError('MariaDB upgrade workflow requires durable application storage')
    with service._semantic_lock:
        jobs = getattr(service, 'mariadb_upgrade_jobs', None)
        if jobs is None:
            root = (
                current_app.config.get('CDEADMIN_MARIADB_UPGRADE_ROOT')
                or str(store.path.parent / 'mariadb-host-upgrades')
            )
            jobs = service.mariadb_upgrade_jobs = MariaDBUpgradeJobStore(
                str(store.path) + '.mariadb-upgrade', root
            )
            atexit.register(jobs.close)
    return jobs, owner, endpoint


def _resolve_backup_record(service, server, owner, endpoint_id, backup_job_id):
    if not backup_job_id:
        return None
    from .mariadb_physical_service import manager as phys_mgr
    phys_jobs, _o, _ep = phys_mgr(service, server)
    return phys_jobs.load(backup_job_id, owner, endpoint_id)


def action(service, server, operation, request):
    if not isinstance(request, dict):
        raise MariaDBUpgradeError('Select a MariaDB upgrade request')
    jobs, owner, endpoint = manager(service, server)

    if operation == 'inspect_source':
        client, route = _client_and_route(service, server)
        conn = client._connect({'route': {**route, 'autocommit': True}})
        try:
            return native.inspect_source_for_upgrade(conn)
        finally:
            client._discard_failed_session(conn)

    if operation == 'list':
        if set(request) - {'offset', 'limit'}:
            raise MariaDBUpgradeError('Invalid MariaDB upgrade job list request')
        return jobs.list(owner, endpoint.id, **request)

    if operation == 'status':
        if set(request) != {'job_id'}:
            raise MariaDBUpgradeError('Select one MariaDB upgrade job')
        rec = jobs.load(request['job_id'], owner, endpoint.id)
        rec.pop('owner', None)
        return rec

    if operation == 'reconcile':
        if set(request) != {'job_id', 'confirmed'} or request['confirmed'] is not True:
            raise MariaDBUpgradeError('Confirm reconciliation of one MariaDB upgrade job')
        rec = jobs.load(request['job_id'], owner, endpoint.id)
        jdir = jobs.job_dir(owner, endpoint.id, rec['job_id'])
        recon = native.reconcile_interrupted_upgrade(job_dir=jdir, datadir=rec['options']['datadir'])
        rec.update(state='reconciled', reconciliation=recon, reconciled_at=time.time())
        return jobs.save_record(rec)

    if operation == 'rollback':
        if set(request) != {'job_id', 'confirmed'} or request['confirmed'] is not True:
            raise MariaDBUpgradeError('Confirm rolling back one interrupted/failed MariaDB upgrade')
        rec = jobs.load(request['job_id'], owner, endpoint.id)
        jdir = jobs.job_dir(owner, endpoint.id, rec['job_id'])
        client, route = _client_and_route(service, server)
        pw = _acquire_password(client, route)
        rb = native.rollback_interrupted_upgrade(
            job_dir=jdir,
            datadir=rec['options']['datadir'],
            db_user=rec['options'].get('db_user') or route.get('user') or 'root',
            db_password=rec['options'].get('db_password', pw),
        )
        rec.update(state='rolled_back', rollback_result=rb, rolled_back_at=time.time())
        return jobs.save_record(rec)

    if operation == 'stop_target':
        if set(request) != {'job_id', 'confirmed'} or request['confirmed'] is not True:
            raise MariaDBUpgradeError('Confirm stopping the upgraded target MariaDB daemon')
        rec = jobs.load(request['job_id'], owner, endpoint.id)
        jdir = jobs.job_dir(owner, endpoint.id, rec['job_id'])
        client, route = _client_and_route(service, server)
        pw = _acquire_password(client, route)
        stopped = control_managed_service(
            action='stop',
            service_mode='managed_daemon',
            state_dir=jdir / 'target-daemon',
            db_user=rec['options'].get('db_user') or route.get('user') or 'root',
            db_password=rec['options'].get('db_password', pw),
        )
        rec.update(target_daemon_stopped=stopped)
        return jobs.save_record(rec)

    if operation in {'preflight', 'review'}:
        opts = deepcopy(request.get('options') if operation == 'review' else request)
        if not isinstance(opts, dict) or 'datadir' not in opts:
            raise MariaDBUpgradeError('Supply upgrade options including datadir')
        opts.setdefault('target_mariadbd_binary', os.environ.get('CDEADMIN_MARIADBD_BINARY', 'mariadbd'))
        opts.setdefault('target_upgrade_binary', os.environ.get('CDEADMIN_MARIADB_UPGRADE_BINARY', 'mariadb-upgrade'))
        opts.setdefault('target_version_prefix', '12.2.2')
        backup_rec = _resolve_backup_record(service, server, owner, endpoint.id, opts.get('backup_job_id'))
        pre = native.preflight_upgrade(
            datadir=opts['datadir'],
            target_mariadbd_binary=opts['target_mariadbd_binary'],
            target_upgrade_binary=opts['target_upgrade_binary'],
            source_version=opts.get('source_version'),
            configuration_file=opts.get('configuration_file'),
            target_basedir=opts.get('target_basedir'),
            target_lc_messages_dir=opts.get('target_lc_messages_dir'),
            backup_record=backup_rec,
            verified_backup_dir=opts.get('verified_backup_dir'),
            verified_logical_dump_path=opts.get('verified_logical_dump_path'),
            target_version_prefix=opts['target_version_prefix'],
        )
        if operation == 'preflight':
            return pre

        if type(opts.get('target_port')) is not int or not 1024 <= opts['target_port'] <= 65535:
            raise MariaDBUpgradeError('Select target_port between 1024 and 65535')

        jid = str(uuid.uuid4())
        rec = {
            'job_id': jid,
            'owner': owner,
            'endpoint_id': endpoint.id,
            'operation': 'mariadb_host_upgrade',
            'state': 'reviewed',
            'options': {k: v for k, v in opts.items() if k != 'db_password'},
            'preflight': pre,
            'warnings': [
                'Stops any active source daemon cleanly with innodb_fast_shutdown=0 before switching to target 12.2.2 mariadbd.',
                'Runs mariadb-upgrade against system tables and verifies mariadb_upgrade_info and post-upgrade readiness.',
                'Retains a pre-upgrade datadir snapshot for explicit rollback if interrupted; no automatic replay occurs.',
            ],
            'created_at': time.time(),
            'expires_at': time.time() + 600,
            'automatic_retry': False,
        }
        rec['review_digest'] = canonical_digest({
            'job_id': jid,
            'datadir': pre['datadir'],
            'target_mariadbd_sha256': pre['target_mariadbd']['executable_sha256'],
            'target_upgrade_sha256': pre['target_mariadb_upgrade']['executable_sha256'],
            'backup_prerequisite': pre['backup_prerequisite'],
        })
        saved = jobs.save_record(rec)
        # Store password only if explicitly overridden in private non-public state? No, pass at start or acquire from endpoint!
        return saved

    if operation == 'start':
        allowed = {'job_id', 'review_digest', 'confirmed', 'db_password', 'source_running_connection'}
        if not {'job_id', 'review_digest', 'confirmed'} <= set(request) or set(request) - allowed or request['confirmed'] is not True:
            raise MariaDBUpgradeError('Confirm the exact MariaDB upgrade review before execution')
        rec = jobs.load(request['job_id'], owner, endpoint.id)
        if rec['review_digest'] != request['review_digest']:
            raise MariaDBUpgradeError('MariaDB upgrade review_digest mismatch')
        if rec['state'] != 'reviewed':
            rec.pop('owner', None)
            return rec
        if time.time() > rec['expires_at']:
            raise MariaDBUpgradeError('MariaDB upgrade review expired')

        opts = rec['options']
        jdir = jobs.job_dir(owner, endpoint.id, rec['job_id'])
        client, route = _client_and_route(service, server)
        pw = request.get('db_password') if 'db_password' in request else _acquire_password(client, route)
        backup_rec = _resolve_backup_record(service, server, owner, endpoint.id, opts.get('backup_job_id'))

        rec['state'] = 'executing'
        jobs.save_record(rec)
        try:
            res = native.run_managed_upgrade(
                job_id=rec['job_id'],
                job_dir=jdir,
                datadir=opts['datadir'],
                target_mariadbd_binary=opts['target_mariadbd_binary'],
                target_upgrade_binary=opts['target_upgrade_binary'],
                target_port=int(opts['target_port']),
                db_user=opts.get('db_user') or route.get('user') or 'root',
                db_password=pw,
                source_running_connection=request.get('source_running_connection') or opts.get('source_running_connection'),
                configuration_file=opts.get('configuration_file'),
                target_basedir=opts.get('target_basedir'),
                target_plugin_dir=opts.get('target_plugin_dir'),
                target_lc_messages_dir=opts.get('target_lc_messages_dir'),
                daemon_user=opts.get('daemon_user'),
                backup_record=backup_rec,
                verified_backup_dir=opts.get('verified_backup_dir'),
                verified_logical_dump_path=opts.get('verified_logical_dump_path'),
                source_version=opts.get('source_version'),
                target_version_prefix=opts['target_version_prefix'],
                create_rollback_snapshot=bool(opts.get('create_rollback_snapshot', True)),
                simulate_interrupt_before_upgrade_tool=bool(opts.get('_simulate_interrupt_before_upgrade_tool', False)),
                timeout_seconds=int(opts.get('timeout_seconds', 300)),
            )
            rec.update(state='completed', result=res, finished_at=time.time())
            return jobs.save_record(rec)
        except BaseException as exc:
            rec.update(
                state='interrupted' if isinstance(exc, InterruptedError) else 'failed',
                error_type=type(exc).__name__,
                error_message=str(exc),
                finished_at=time.time(),
            )
            jobs.save_record(rec)
            raise

    raise MariaDBUpgradeError(f'Unknown MariaDB upgrade action: {operation!r}')
