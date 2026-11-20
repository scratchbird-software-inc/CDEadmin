"""Workspace service for MariaDB physical backup, incremental prepare, isolated recovery & cutover."""
import atexit
from copy import deepcopy
import os
from pathlib import Path
import threading
import time
import uuid

from ..core import EndpointContext
from ..operations.fileio import exclusive_file_lock, private_directory, private_file
from ..operations.store import JsonOperationStore
from ..providers.mysql_family import mariadb_physical as native
from ..providers.mysql_family.mariadb_connections import POOL_ARGUMENTS
from ..providers.mysql_family.mariadb_physical import MariaDBPhysicalError, canonical_digest
from ..providers.mysql_family.mysql_clone import rows
from ..providers.mysql_family.provider import MariaDBPilotProvider
from .mariadb_archive_retention import protection_manager
from .mysql_binlog_jobs import identity


PHASES = frozenset({'backup', 'incremental', 'prepare', 'copy_back', 'move_back', 'recover'})


class MariaDBPhysicalJobManager:
    """Durable, owner-scoped store & background/synchronous worker runner for MariaDB physical jobs."""

    def __init__(self, store_path, root_dir):
        self.store_path = Path(store_path).resolve()
        self.root = Path(root_dir).resolve()
        self.store_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_directory(self.root)
        self._lock = threading.RLock()
        self._signals = {}
        self._threads = {}

    def close(self):
        with self._lock:
            for sig in self._signals.values():
                sig.set()
            threads = list(self._threads.values())
        for t in threads:
            t.join(timeout=5)

    def _with_store(self, fn):
        lock_file = self.store_path.parent / (self.store_path.name + '.lock')
        with self._lock, lock_file.open('a+b') as lf:
            private_file(lock_file)
            with exclusive_file_lock(lf.fileno()):
                store = JsonOperationStore(self.store_path)
                return fn(store)

    def job_dir(self, owner, endpoint_id, job_id):
        d = self.root / str(owner) / identity(endpoint_id) / identity(job_id)
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_directory(d)
        return d

    def get(self, job_id, owner, endpoint_id):
        job_id = identity(job_id)
        endpoint_id = identity(endpoint_id)
        def _read(store):
            rec = store.read().get('jobs', {}).get(job_id)
            if rec is None or rec['owner'] != owner or rec['endpoint_id'] != endpoint_id:
                raise MariaDBPhysicalError('Select an owned MariaDB physical continuity job')
            return deepcopy(rec)
        rec = self._with_store(_read)
        return self.public(rec)

    def load(self, job_id, owner, endpoint_id):
        job_id = identity(job_id)
        endpoint_id = identity(endpoint_id)
        def _read(store):
            rec = store.read().get('jobs', {}).get(job_id)
            if rec is None or rec['owner'] != owner or rec['endpoint_id'] != endpoint_id:
                raise MariaDBPhysicalError('Select an owned MariaDB physical continuity job')
            return deepcopy(rec)
        return self._with_store(_read)

    def update(self, job_id, **fields):
        job_id = identity(job_id)
        def _write(store):
            def _mut(doc):
                rec = doc.setdefault('jobs', {})[job_id]
                rec.update(deepcopy(fields))
                rec['updated_at'] = time.time()
            store.change(_mut)
            return deepcopy(store.read()['jobs'][job_id])
        return self._with_store(_write)

    def list(self, owner, endpoint_id, offset=0, limit=25):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise MariaDBPhysicalError('Invalid MariaDB physical job page bounds')
        endpoint_id = identity(endpoint_id)
        def _read(store):
            all_jobs = [
                deepcopy(r) for r in store.read().get('jobs', {}).values()
                if r['owner'] == owner and r['endpoint_id'] == endpoint_id
            ]
            return all_jobs
        rows_list = sorted(self._with_store(_read), key=lambda r: (r['created_at'], r['job_id']), reverse=True)
        return {
            'jobs': [self.public(r) for r in rows_list[offset:offset + limit]],
            'total': len(rows_list),
            'offset': offset,
            'limit': limit,
        }

    @staticmethod
    def public(rec):
        out = deepcopy(rec)
        out.pop('owner', None)
        if isinstance((out.get('result') or {}).get('artifact'), dict):
            art = out['result']['artifact']
            if 'files' in art:
                art['file_count'] = len(art['files'])
                art.pop('files', None)
        return out

    def create_review(self, owner, endpoint_id, options, source_capture, program_info, extra_warnings=()):
        job_id = str(uuid.uuid4())
        now = time.time()
        warnings = [
            'Executes native MariaDB physical continuity utilities with a private 0600 credential file and bounded process supervision.',
            'Dispatch, native acknowledgement, artifact adoption, and restored SQL verification are tracked as separate states.',
            'Original base and incremental artifacts remain immutable; prepare operates on an isolated staged working copy.',
            'No failed or unknown physical operation is ever automatically replayed.',
            *extra_warnings,
        ]
        record = {
            'job_id': job_id,
            'owner': owner,
            'endpoint_id': identity(endpoint_id),
            'operation': 'mariadb_native_physical_continuity',
            'phase': options['phase'],
            'state': 'reviewed',
            'dispatch_state': 'not_dispatched',
            'acknowledgement_state': 'unacknowledged',
            'artifact_adoption_state': 'unverified',
            'database_recovery_verified': False,
            'production_cutover_verified': False,
            'options': deepcopy(options),
            'source': deepcopy(source_capture['identity']),
            'source_state': deepcopy(source_capture['state']),
            'program': deepcopy(program_info),
            'warnings': warnings,
            'created_at': now,
            'updated_at': now,
            'expires_at': now + 600,
            'automatic_retry': False,
        }
        record['review_digest'] = canonical_digest({
            'job_id': job_id,
            'phase': options['phase'],
            'options': options,
            'source': source_capture['identity'],
            'program': program_info,
        })
        def _save(store):
            store.change(lambda doc: doc.setdefault('jobs', {}).update({job_id: record}))
        self._with_store(_save)
        return self.public(record)

    def cancel(self, job_id, owner, endpoint_id):
        rec = self.load(job_id, owner, endpoint_id)
        with self._lock:
            sig = self._signals.get(rec['job_id'])
            if sig is not None:
                sig.set()
        if rec['state'] == 'reviewed':
            return self.public(self.update(rec['job_id'], state='cancelled', cancel_requested=True, finished_at=time.time()))
        if rec['state'] in {'dispatching', 'active'}:
            self.update(rec['job_id'], cancel_requested=True)
        return self.get(rec['job_id'], owner, endpoint_id)

    def cutover_store(self):
        return self._with_store


def _admitted_endpoint(service, server, required_perms=('backup_admin',)):
    endpoint = getattr(server, 'endpoint_profile', None)
    if endpoint is None or endpoint.profile_id != 'mariadb-native' or endpoint.provider_id != 'org.cdeadmin.mariadb':
        raise MariaDBPhysicalError('Select an owned native MariaDB registration')
    ctx = EndpointContext(
        endpoint_id=endpoint.id,
        mode='legacy_native',
        experience_family='mariadb',
        provider_id=endpoint.provider_id,
        provider_version=endpoint.provider_version or '0.1.0',
        profile_id=endpoint.profile_id,
        profile_version=endpoint.profile_version or '12.2.2',
        target_adapter_id=endpoint.target_adapter_id,
        target_adapter_version=endpoint.target_adapter_version or '0.1.0',
        **{name: getattr(endpoint, name) for name in ('pool_namespace', 'session_namespace', 'cache_namespace', 'diagnostic_namespace')},
    )
    perms = service.endpoint_service.provider_registry.admitted_permissions(ctx)
    if not set(required_perms).issubset(perms):
        raise MariaDBPhysicalError('Required MariaDB continuity permissions are unavailable')
    return service._principal_id(server), endpoint, ctx


def manager(service, server, required_perms=('backup_admin',)):
    from flask import current_app
    owner, endpoint, _ctx = _admitted_endpoint(service, server, required_perms=required_perms)
    store = getattr(service.operation_bus, 'store', None)
    if not isinstance(store, JsonOperationStore):
        raise MariaDBPhysicalError('MariaDB physical continuity requires durable application storage')
    with service._semantic_lock:
        jobs = getattr(service, 'mariadb_physical_jobs', None)
        if jobs is None:
            root = (
                current_app.config.get('CDEADMIN_MARIADB_PHYSICAL_ROOT')
                or str(store.path.parent / 'mariadb-physical-continuity')
            )
            jobs = service.mariadb_physical_jobs = MariaDBPhysicalJobManager(
                str(store.path) + '.mariadb-physical', root
            )
            atexit.register(jobs.close)
    return jobs, owner, endpoint


def _client_and_route(service, server):
    ctx, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
    provider = service.endpoint_service.provider_registry.resolve(ctx).instance
    if not isinstance(provider, MariaDBPilotProvider):
        raise MariaDBPhysicalError('Native MariaDB provider client is unavailable')
    route = {k: v for k, v in payload['route'].items() if k not in POOL_ARGUMENTS}
    return provider.client, route


def _acquire_password(client, route):
    found = []
    client._tool_secret(route, lambda pw: found.append(pw))
    return found[0] if found else ''


def validate_options(raw):
    if not isinstance(raw, dict) or raw.get('phase') not in PHASES:
        raise MariaDBPhysicalError('Select a MariaDB physical phase: backup, incremental, prepare, copy_back, move_back, or recover')
    opts = deepcopy(raw)
    phase = opts['phase']
    opts.setdefault('backup_binary', os.environ.get('CDEADMIN_MARIADB_BACKUP_BINARY', 'mariadb-backup'))
    opts.setdefault('timeout_seconds', 3600)
    opts.setdefault('parallel', 1)
    opts.setdefault('version_prefix', '12.2.2')
    if type(opts['timeout_seconds']) is not int or not 1 <= opts['timeout_seconds'] <= 604800:
        raise MariaDBPhysicalError('Select bounded timeout_seconds between 1 and 604800')
    if type(opts['parallel']) is not int or not 1 <= opts['parallel'] <= 64:
        raise MariaDBPhysicalError('Select parallel threads between 1 and 64')

    if phase in {'backup', 'incremental'}:
        if 'source_datadir' in opts and opts['source_datadir'] is not None:
            opts['source_datadir'] = str(native.safe_absolute_path(opts['source_datadir'], 'source_datadir'))
        if phase == 'incremental':
            opts['parent_job_id'] = identity(opts.get('parent_job_id'))
            mode = opts.get('incremental_mode', 'basedir')
            if mode not in {'basedir', 'lsn'}:
                raise MariaDBPhysicalError("Select incremental_mode 'basedir' or 'lsn'")
            opts['incremental_mode'] = mode
    elif phase == 'prepare':
        opts['base_job_id'] = identity(opts.get('base_job_id'))
        inc_ids = opts.get('incremental_job_ids', [])
        if not isinstance(inc_ids, list) or len(inc_ids) > 64:
            raise MariaDBPhysicalError('Select 0 to 64 ordered incremental_job_ids')
        opts['incremental_job_ids'] = [identity(x) for x in inc_ids]
        if len(set(opts['incremental_job_ids'])) != len(opts['incremental_job_ids']):
            raise MariaDBPhysicalError('incremental_job_ids must be distinct')
        opts.setdefault('memory_bytes', 268435456)
        if type(opts['memory_bytes']) is not int or not 67108864 <= opts['memory_bytes'] <= 17179869184:
            raise MariaDBPhysicalError('Select prepare memory_bytes between 64 MiB and 16 GiB')
    elif phase in {'copy_back', 'move_back'}:
        opts['prepared_job_id'] = identity(opts.get('prepared_job_id'))
        opts['target_datadir'] = str(native.safe_absolute_path(opts.get('target_datadir'), 'target_datadir'))
    elif phase == 'recover':
        opts['restore_job_id'] = identity(opts.get('restore_job_id'))
        opts['mariadbd_binary'] = opts.get('mariadbd_binary') or os.environ.get('CDEADMIN_MARIADBD_BINARY', 'mariadbd')
        opts['mariadb_client_binary'] = opts.get('mariadb_client_binary') or os.environ.get('CDEADMIN_MARIADB_CLIENT_BINARY', 'mariadb')
        opts['mariadb_binlog_binary'] = opts.get('mariadb_binlog_binary') or os.environ.get('CDEADMIN_MARIADB_BINLOG_BINARY', 'mariadb-binlog')
        if type(opts.get('recovery_port')) is not int or not 1024 <= opts['recovery_port'] <= 65535:
            raise MariaDBPhysicalError('Select an isolated recovery_port between 1024 and 65535')
        opts.setdefault('recovery_server_id', 99173)
    return opts


def _resolve_pitr_spec(service, server, owner, endpoint_id, pitr_req):
    if not pitr_req:
        return None
    if not isinstance(pitr_req, dict):
        raise MariaDBPhysicalError('PITR specification must be an object')
    spec = deepcopy(pitr_req)
    if 'archive_job_ids' in spec and spec['archive_job_ids']:
        from .mysql_binlog_service import manager as binlog_mgr
        archives, _o, _ep, _ctx = binlog_mgr(service, server, 'mariadb')
        files = []
        for aid in spec['archive_job_ids']:
            rec = archives.load(identity(aid), owner, endpoint_id)
            art = (rec.get('result') or {}).get('artifact')
            if rec.get('artifact_removed') or not art:
                raise MariaDBPhysicalError(f'PITR archive {aid} is unavailable or removed')
            arch_dir = archives.directory(rec) / 'archive'
            verified = archives.native_verify(arch_dir, rec['source'])
            for f in verified['files']:
                if f['path'] != 'archive.json':
                    files.append(str(arch_dir / f['path']))
        spec['binlog_files'] = files
    elif 'binlog_files' not in spec or not spec['binlog_files']:
        raise MariaDBPhysicalError('Specify archive_job_ids or binlog_files for PITR catch-up')
    return spec


def _execute_job(service, server, jobs, rec, client, route, password, sig, synchronous=True):
    owner, endpoint_id = rec['owner'], rec['endpoint_id']
    job_id = rec['job_id']
    opts = rec['options']
    phase = opts['phase']
    jdir = jobs.job_dir(owner, endpoint_id, job_id)
    prot = protection_manager(service)

    def _worker():
        try:
            jobs.update(job_id, state='active')
            source_datadir = opts.get('source_datadir') or rec['source']['datadir']

            if phase in {'backup', 'incremental'}:
                parent_rec = None
                inc_basedir = inc_lsn = None
                chain_root = job_id
                if phase == 'incremental':
                    parent_rec = jobs.load(opts['parent_job_id'], owner, endpoint_id)
                    parent_art = (parent_rec.get('result') or {}).get('artifact')
                    if not parent_art or parent_rec.get('artifact_adoption_state') != 'artifact_adopted':
                        raise MariaDBPhysicalError('Parent backup is not verified/adopted')
                    if parent_rec['source']['server_uid'] != rec['source']['server_uid']:
                        raise MariaDBPhysicalError('Parent backup belongs to another MariaDB server_uid')
                    chain_root = parent_rec.get('chain_root_job_id') or parent_rec['job_id']
                    if opts['incremental_mode'] == 'basedir':
                        inc_basedir = parent_rec['artifact_dir']
                    else:
                        inc_lsn = parent_art['to_lsn']

                prot.register_physical_backup_hold(
                    owner, endpoint_id,
                    backup_job_id=job_id,
                    source_uid=rec['source']['server_uid'],
                    backup_type=phase,
                    chain_root_job_id=chain_root,
                    parent_job_id=opts.get('parent_job_id'),
                    state='pending_native_reply',
                )

                def _on_dispatch(info):
                    jobs.update(job_id, dispatch_state='dispatched', dispatched_at=info['dispatched_at'])

                def _on_ack(info):
                    jobs.update(
                        job_id,
                        acknowledgement_state='native_acknowledged' if info['native_acknowledged'] else 'native_failed',
                        native_acknowledged=info['native_acknowledged'],
                    )

                res = native.run_physical_backup(
                    backup_binary=opts['backup_binary'],
                    source_datadir=source_datadir,
                    job_dir=jdir,
                    db_user=route.get('user') or route.get('username') or 'root',
                    db_password=password,
                    host=opts.get('sql_host') or route.get('host') or '127.0.0.1',
                    port=opts.get('sql_port') or int(route.get('port', 3306)),
                    socket_path=opts.get('socket_path') or route.get('unix_socket'),
                    ssl=bool(route.get('ssl')),
                    parallel=opts['parallel'],
                    timeout_seconds=opts['timeout_seconds'],
                    cancel=sig,
                    incremental_basedir=inc_basedir,
                    incremental_lsn=inc_lsn,
                    version_prefix=opts['version_prefix'],
                    on_dispatch=_on_dispatch,
                    on_acknowledge=_on_ack,
                )
                art = res['artifact']
                if phase == 'incremental':
                    p_to = int(parent_rec['result']['artifact']['to_lsn'])
                    if int(art['from_lsn']) != p_to:
                        raise MariaDBPhysicalError(
                            f"Incremental from_lsn={art['from_lsn']} does not match parent.to_lsn={p_to}"
                        )
                hold = prot.register_physical_backup_hold(
                    owner, endpoint_id,
                    backup_job_id=job_id,
                    source_uid=rec['source']['server_uid'],
                    backup_type=art['checkpoints']['backup_type'],
                    chain_root_job_id=chain_root,
                    parent_job_id=opts.get('parent_job_id'),
                    binlog_file=art['binlog_info'].get('binlog_file'),
                    binlog_position=art['binlog_info'].get('binlog_position'),
                    gtid_pos=art['binlog_info'].get('gtid_pos'),
                    from_lsn=art['from_lsn'],
                    to_lsn=art['to_lsn'],
                    last_lsn=art['last_lsn'],
                    state='active',
                    native_acknowledged=True,
                )
                jobs.update(
                    job_id,
                    state='completed',
                    dispatch_state='dispatched',
                    acknowledgement_state='native_acknowledged',
                    artifact_adoption_state='artifact_adopted',
                    artifact_dir=res['artifact_dir'],
                    chain_root_job_id=chain_root,
                    protection_hold_id=hold['hold_id'],
                    result=res,
                    finished_at=time.time(),
                )

            elif phase == 'prepare':
                base_rec = jobs.load(opts['base_job_id'], owner, endpoint_id)
                inc_recs = [jobs.load(iid, owner, endpoint_id) for iid in opts['incremental_job_ids']]
                jobs.update(job_id, dispatch_state='dispatched', dispatched_at=time.time())
                res = native.run_staged_prepare(
                    backup_binary=opts['backup_binary'],
                    base_record=base_rec,
                    incremental_records=inc_recs,
                    job_dir=jdir,
                    memory_bytes=opts['memory_bytes'],
                    timeout_seconds=opts['timeout_seconds'],
                    cancel=sig,
                    version_prefix=opts['version_prefix'],
                    simulate_interrupt_after_step=opts.get('_simulate_interrupt_after_step'),
                )
                jobs.update(
                    job_id,
                    state='completed',
                    acknowledgement_state='native_acknowledged',
                    artifact_adoption_state='artifact_adopted',
                    artifact_dir=res['artifact_dir'],
                    result=res,
                    finished_at=time.time(),
                )

            elif phase in {'copy_back', 'move_back'}:
                prep_rec = jobs.load(opts['prepared_job_id'], owner, endpoint_id)
                jobs.update(job_id, dispatch_state='dispatched', dispatched_at=time.time())
                res = native.run_isolated_copy_or_move_back(
                    backup_binary=opts['backup_binary'],
                    prepared_record=prep_rec,
                    target_datadir=opts['target_datadir'],
                    source_datadir=source_datadir,
                    job_dir=jdir,
                    mode=phase,
                    daemon_user=opts.get('daemon_user'),
                    timeout_seconds=opts['timeout_seconds'],
                    cancel=sig,
                    version_prefix=opts['version_prefix'],
                )
                jobs.update(
                    job_id,
                    state='completed',
                    acknowledgement_state='native_acknowledged',
                    artifact_adoption_state='artifact_adopted',
                    target_datadir=res['target_datadir'],
                    result=res,
                    finished_at=time.time(),
                )

            elif phase == 'recover':
                rest_rec = jobs.load(opts['restore_job_id'], owner, endpoint_id)
                if rest_rec['state'] != 'completed' or not rest_rec.get('target_datadir'):
                    raise MariaDBPhysicalError('Select a completed isolated copy_back or move_back job')
                prep_rec = jobs.load(rest_rec['options']['prepared_job_id'], owner, endpoint_id)
                prep_binlog = (((prep_rec.get('result') or {}).get('artifact') or {}).get('binlog_info') or {})
                pitr_spec = _resolve_pitr_spec(service, server, owner, endpoint_id, opts.get('pitr'))
                if pitr_spec is not None:
                    if prep_binlog.get('gtid_pos'):
                        pitr_spec.setdefault('baseline_gtid_pos', prep_binlog['gtid_pos'])
                        if not pitr_spec.get('start_gtid') and pitr_spec.get('start_position') is None:
                            pitr_spec['start_gtid'] = prep_binlog['gtid_pos']
                archive_ids = (opts.get('pitr') or {}).get('archive_job_ids') or []
                prot.register_active_recovery_hold(
                    owner, endpoint_id,
                    recovery_job_id=job_id,
                    source_uid=rec['source']['server_uid'],
                    base_backup_job_id=rest_rec['options']['prepared_job_id'],
                    archive_job_ids=archive_ids,
                )
                jobs.update(job_id, dispatch_state='dispatched', dispatched_at=time.time())
                res = native.start_isolated_recovery_instance(
                    mariadbd_binary=opts['mariadbd_binary'],
                    mariadb_client_binary=opts['mariadb_client_binary'],
                    mariadb_binlog_binary=opts['mariadb_binlog_binary'],
                    target_datadir=rest_rec['target_datadir'],
                    source_datadir=source_datadir,
                    source_port=opts.get('source_port') or int(route.get('port', 3306)),
                    recovery_port=opts['recovery_port'],
                    job_dir=jdir,
                    db_user=opts.get('recovery_db_user') or route.get('user') or 'root',
                    db_password=opts.get('recovery_db_password', password),
                    recovery_server_id=opts['recovery_server_id'],
                    basedir=opts.get('basedir'),
                    plugin_dir=opts.get('plugin_dir'),
                    lc_messages_dir=opts.get('lc_messages_dir'),
                    daemon_user=opts.get('daemon_user'),
                    pitr=pitr_spec,
                    expected_checks=opts.get('expected_checks'),
                    version_prefix=opts['version_prefix'],
                    timeout_seconds=min(opts['timeout_seconds'], 300),
                )
                jobs.update(
                    job_id,
                    state='completed',
                    acknowledgement_state='native_acknowledged',
                    artifact_adoption_state='artifact_adopted',
                    database_recovery_verified=res['database_recovery_verified'],
                    recovery_running=True,
                    result=res,
                    finished_at=time.time(),
                )

        except BaseException as exc:
            obs = getattr(exc, 'observation', None) or {}
            term_confirmed = obs.get('process_termination_confirmed', True)
            cancelled = sig.is_set() or isinstance(exc, InterruptedError) or obs.get('cancel_requested')
            final_state = 'unknown' if term_confirmed is False else ('cancelled' if cancelled else 'failed')
            if final_state == 'unknown' or (phase in {'backup', 'incremental'} and rec.get('dispatch_state') == 'dispatched'):
                prot.record_uncertain_hold(
                    owner, endpoint_id,
                    origin_operation=f'mariadb_physical_{phase}',
                    origin_job_id=job_id,
                    source_uid=rec['source']['server_uid'],
                    uncertainty_reason=str(exc),
                    native_acknowledged=False,
                    process_termination_confirmed=bool(term_confirmed),
                )
            jobs.update(
                job_id,
                state=final_state,
                acknowledgement_state='cancelled' if cancelled else ('unknown' if final_state == 'unknown' else 'native_failed'),
                error_type=type(exc).__name__,
                error_message=str(exc),
                process_observation={k: v for k, v in obs.items() if k not in {'stdout', 'stderr'}} if obs else None,
                finished_at=time.time(),
            )
        finally:
            with jobs._lock:
                jobs._signals.pop(job_id, None)
                jobs._threads.pop(job_id, None)

    if synchronous:
        _worker()
        return jobs.get(job_id, owner, endpoint_id)
    t = threading.Thread(target=_worker, daemon=True)
    with jobs._lock:
        jobs._threads[job_id] = t
    t.start()
    return jobs.get(job_id, owner, endpoint_id)


def _cutover_action(service, server, jobs, owner, endpoint, sub_op, request):
    """Separately reviewed one-use production cutover with primary fencing, registration update & rollback."""
    import mariadb
    from pgadmin.model import db

    if sub_op == 'list':
        def _read_list(store):
            return [
                deepcopy(v) for v in store.read().get('cutovers', {}).values()
                if v['owner'] == owner and v['endpoint_id'] == endpoint.id
            ]
        items = sorted(jobs.cutover_store()(_read_list), key=lambda x: x['created_at'], reverse=True)
        for it in items:
            it.pop('owner', None)
        return {'cutovers': items, 'total': len(items)}

    if sub_op == 'status':
        cid = identity(request.get('cutover_id'))
        def _read_one(store):
            c = store.read().get('cutovers', {}).get(cid)
            if not c or c['owner'] != owner or c['endpoint_id'] != endpoint.id:
                raise MariaDBPhysicalError('Select an owned MariaDB cutover record')
            return deepcopy(c)
        res = jobs.cutover_store()(_read_one)
        res.pop('owner', None)
        return res

    client, route = _client_and_route(service, server)
    password = _acquire_password(client, route)

    if sub_op == 'review':
        required = {'recovery_job_id', 'target_confirmation', 'fence_old_primary', 'update_target_registration'}
        if not isinstance(request, dict) or not required <= set(request):
            raise MariaDBPhysicalError('Supply recovery_job_id, target_confirmation, fence_old_primary, and update_target_registration')
        if request['fence_old_primary'] is not True:
            raise MariaDBPhysicalError('Production cutover requires fence_old_primary=True')
        rec_job = jobs.load(request['recovery_job_id'], owner, endpoint.id)
        if not rec_job.get('database_recovery_verified') or not rec_job.get('recovery_running'):
            raise MariaDBPhysicalError('Select a running isolated recovery instance with independent verification')
        rec_port = rec_job['result']['recovery_port']
        rec_user = rec_job['options'].get('recovery_db_user') or route.get('user') or 'root'
        rec_pw = rec_job['options'].get('recovery_db_password', password)

        old_conn = client._connect({'route': {**route, 'autocommit': True}})
        rec_conn = mariadb.connect(host='127.0.0.1', port=int(rec_port), user=rec_user, password=rec_pw or '', autocommit=True)
        try:
            old_obs = rows(
                old_conn,
                'SELECT VERSION() AS version, @@server_uid AS server_uid, @@datadir AS datadir, '
                '@@port AS port, @@read_only AS read_only, @@gtid_binlog_pos AS gtid_binlog_pos',
            )[0]
            rec_obs = rows(
                rec_conn,
                'SELECT VERSION() AS version, @@server_uid AS server_uid, @@datadir AS datadir, '
                '@@port AS port, @@read_only AS read_only, @@gtid_current_pos AS gtid_current_pos',
            )[0]
        finally:
            client._discard_failed_session(old_conn)
            rec_conn.close()

        if not native.mariadb_bool(rec_obs['read_only']):
            raise MariaDBPhysicalError('Isolated recovery instance must be read_only=1 prior to cutover')
        if request['target_confirmation'] not in {rec_obs['datadir'], str(rec_port), rec_obs['server_uid']}:
            raise MariaDBPhysicalError('Confirm the exact isolated recovery datadir, port, or server_uid')

        cutover_id = str(uuid.uuid4())
        prev_route = {
            'host': server.host,
            'port': int(server.port),
            'route_configuration': deepcopy(getattr(endpoint, 'route_configuration', None) or route),
        }
        rollback_metadata = {
            'previous_server_registration': prev_route,
            'old_primary': old_obs,
            'promoted_recovery': rec_obs,
            'rollback_steps': [
                'Set read_only=ON on the promoted recovery instance',
                'Restore Server registration route to previous_server_registration',
                'Set read_only=OFF on old_primary only after verifying zero post-cutover writes or reconciling diverged transactions',
            ],
        }
        record = {
            'cutover_id': cutover_id,
            'owner': owner,
            'endpoint_id': endpoint.id,
            'server_id': server.id,
            'recovery_job_id': rec_job['job_id'],
            'state': 'reviewed',
            'one_use_consumed': False,
            'options': {
                'fence_old_primary': True,
                'update_target_registration': bool(request['update_target_registration']),
                'promote_writable': bool(request.get('promote_writable', True)),
            },
            'old_primary_before': old_obs,
            'recovery_before': rec_obs,
            'rollback_metadata': rollback_metadata,
            'created_at': time.time(),
            'expires_at': time.time() + 300,
        }
        record['review_digest'] = canonical_digest({
            'cutover_id': cutover_id,
            'recovery_job_id': rec_job['job_id'],
            'old_primary_before': old_obs,
            'recovery_before': rec_obs,
        })
        def _save_cutover(store):
            store.change(lambda doc: doc.setdefault('cutovers', {}).update({cutover_id: record}))
        jobs.cutover_store()(_save_cutover)
        out = deepcopy(record)
        out.pop('owner', None)
        return out

    if sub_op == 'start':
        if not isinstance(request, dict) or set(request) != {'cutover_id', 'review_digest', 'confirmed'} or request['confirmed'] is not True:
            raise MariaDBPhysicalError('Confirm the exact one-use cutover review')
        cid = identity(request['cutover_id'])

        def _claim(store):
            doc = store.read()
            rec = doc.get('cutovers', {}).get(cid)
            if rec is None or rec['owner'] != owner or rec['endpoint_id'] != endpoint.id:
                raise MariaDBPhysicalError('Select an owned MariaDB cutover review')
            if rec['review_digest'] != request['review_digest']:
                raise MariaDBPhysicalError('Cutover review_digest mismatch')
            if rec.get('one_use_consumed') or rec['state'] != 'reviewed':
                raise MariaDBPhysicalError('This one-use MariaDB cutover review has already been consumed; replay is forbidden')
            if time.time() > rec['expires_at']:
                raise MariaDBPhysicalError('Cutover review expired; create a fresh review')
            def _mark(d):
                d['cutovers'][cid]['one_use_consumed'] = True
                d['cutovers'][cid]['state'] = 'executing'
                d['cutovers'][cid]['dispatched_at'] = time.time()
            store.change(_mark)
            return deepcopy(store.read()['cutovers'][cid])

        cutover = jobs.cutover_store()(_claim)
        rec_job = jobs.load(cutover['recovery_job_id'], owner, endpoint.id)
        rec_port = rec_job['result']['recovery_port']
        rec_user = rec_job['options'].get('recovery_db_user') or route.get('user') or 'root'
        rec_pw = rec_job['options'].get('recovery_db_password', password)

        old_conn = None
        rec_conn = None
        try:
            # 1. Fence old primary read-only
            old_conn = client._connect({'route': {**route, 'autocommit': True}})
            cur_old = old_conn.cursor()
            cur_old.execute('SET GLOBAL read_only=ON')
            cur_old.close()
            fenced_obs = rows(
                old_conn,
                'SELECT @@global.read_only AS read_only, @@global.gtid_binlog_pos AS gtid_binlog_pos',
            )[0]
            if not native.mariadb_bool(fenced_obs['read_only']):
                raise MariaDBPhysicalError('Failed to confirm read_only=1 fence on old MariaDB primary')

            # 2. Promote isolated recovery instance
            rec_conn = mariadb.connect(
                host='127.0.0.1', port=int(rec_port), user=rec_user, password=rec_pw or '', autocommit=True
            )
            if cutover['options']['promote_writable']:
                cur_rec = rec_conn.cursor()
                cur_rec.execute('SET GLOBAL read_only=OFF')
                cur_rec.close()
            promoted_obs = rows(
                rec_conn,
                'SELECT @@global.read_only AS read_only, @@port AS port, @@datadir AS datadir, @@server_uid AS server_uid',
            )[0]
            if cutover['options']['promote_writable'] and native.mariadb_bool(promoted_obs['read_only']):
                raise MariaDBPhysicalError('Failed to confirm writable promotion on new MariaDB primary')

            # 3. Update target registration if requested
            reg_updated = False
            if cutover['options']['update_target_registration']:
                server.host = '127.0.0.1'
                server.port = int(rec_port)
                if endpoint is not None and hasattr(endpoint, 'route_configuration'):
                    rcfg = deepcopy(endpoint.route_configuration or {})
                    rcfg['host'] = '127.0.0.1'
                    rcfg['port'] = int(rec_port)
                    endpoint.route_configuration = rcfg
                db.session.commit()
                reg_updated = True

            rollback_meta = deepcopy(cutover['rollback_metadata'])
            rollback_meta.update(
                old_primary_fenced=True,
                old_primary_fenced_gtid=fenced_obs['gtid_binlog_pos'],
                promoted_new_primary=promoted_obs,
                registration_updated=reg_updated,
                cutover_completed_at=time.time(),
            )

            def _complete(store):
                def _upd(d):
                    d['cutovers'][cid].update(
                        state='completed',
                        old_primary_fenced=True,
                        old_primary_after=fenced_obs,
                        promoted_after=promoted_obs,
                        registration_updated=reg_updated,
                        rollback_metadata=rollback_meta,
                        production_cutover_verified=True,
                        finished_at=time.time(),
                    )
                store.change(_upd)
                return deepcopy(store.read()['cutovers'][cid])

            done = jobs.cutover_store()(_complete)
            jobs.update(rec_job['job_id'], production_cutover_verified=True, cutover_id=cid)
            done.pop('owner', None)
            return done
        except BaseException as exc:
            def _fail(store):
                store.change(lambda d: d['cutovers'][cid].update(
                    state='unknown_or_partial',
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    finished_at=time.time(),
                ))
            jobs.cutover_store()(_fail)
            raise
        finally:
            if old_conn is not None:
                client._discard_failed_session(old_conn)
            if rec_conn is not None:
                rec_conn.close()

    if sub_op == 'rollback':
        if not isinstance(request, dict) or set(request) != {'cutover_id', 'confirmed'} or request['confirmed'] is not True:
            raise MariaDBPhysicalError('Confirm the exact cutover_id to execute registration/read-only rollback')
        cid = identity(request['cutover_id'])
        def _load_c(store):
            rec = store.read().get('cutovers', {}).get(cid)
            if not rec or rec['owner'] != owner or rec['endpoint_id'] != endpoint.id:
                raise MariaDBPhysicalError('Select an owned MariaDB cutover record')
            return deepcopy(rec)
        cutover = jobs.cutover_store()(_load_c)
        if cutover['state'] != 'completed':
            raise MariaDBPhysicalError('Only a completed cutover can execute automated rollback')
        rb = cutover['rollback_metadata']
        rec_job = jobs.load(cutover['recovery_job_id'], owner, endpoint.id)
        rec_port = rec_job['result']['recovery_port']
        rec_user = rec_job['options'].get('recovery_db_user') or route.get('user') or 'root'
        rec_pw = rec_job['options'].get('recovery_db_password', password)

        # Fence promoted recovery back to read_only=ON
        rec_conn = mariadb.connect(host='127.0.0.1', port=int(rec_port), user=rec_user, password=rec_pw or '', autocommit=True)
        try:
            c = rec_conn.cursor()
            c.execute('SET GLOBAL read_only=ON')
            c.close()
        finally:
            rec_conn.close()

        # Restore Server registration to old primary
        prev = rb['previous_server_registration']
        server.host = prev['host']
        server.port = int(prev['port'])
        if endpoint is not None and hasattr(endpoint, 'route_configuration'):
            endpoint.route_configuration = deepcopy(prev['route_configuration'])
        db.session.commit()

        # Unfence old primary
        old_conn = mariadb.connect(
            host=prev['host'], port=int(prev['port']),
            user=prev['route_configuration'].get('user') or 'root',
            password=password or '', autocommit=True,
        )
        try:
            c2 = old_conn.cursor()
            c2.execute('SET GLOBAL read_only=OFF')
            c2.close()
        finally:
            old_conn.close()

        def _mark_rb(store):
            store.change(lambda d: d['cutovers'][cid].update(state='rolled_back', rolled_back_at=time.time()))
            return deepcopy(store.read()['cutovers'][cid])
        done = jobs.cutover_store()(_mark_rb)
        done.pop('owner', None)
        return done

    raise MariaDBPhysicalError('Unknown MariaDB cutover action')


def action(service, server, operation, request):
    if not isinstance(request, dict):
        raise MariaDBPhysicalError('Select a MariaDB physical continuity request')
    req_perms = ('restore_admin', 'backup_admin') if (
        operation.startswith('cutover_') or (request.get('options') or {}).get('phase') in {'copy_back', 'move_back', 'recover'}
    ) else ('backup_admin',)
    jobs, owner, endpoint = manager(service, server, required_perms=req_perms)

    if operation.startswith('cutover_'):
        return _cutover_action(service, server, jobs, owner, endpoint, operation.removeprefix('cutover_'), request)

    if operation == 'list':
        if set(request) - {'offset', 'limit'}:
            raise MariaDBPhysicalError('Invalid MariaDB physical job list request')
        return jobs.list(owner, endpoint.id, **request)

    if operation in {'status', 'cancel'}:
        if set(request) != {'job_id'}:
            raise MariaDBPhysicalError('Select one MariaDB physical job')
        return (jobs.get if operation == 'status' else jobs.cancel)(request['job_id'], owner, endpoint.id)

    if operation == 'stop_recovery':
        if set(request) != {'job_id', 'confirmed'} or request['confirmed'] is not True:
            raise MariaDBPhysicalError('Confirm stopping the isolated MariaDB recovery instance')
        rec = jobs.load(request['job_id'], owner, endpoint.id)
        if rec['phase'] != 'recover':
            raise MariaDBPhysicalError('Select a MariaDB recover job to stop')
        client, route = _client_and_route(service, server)
        pw = _acquire_password(client, route)
        res = rec.get('result') or {}
        stopped = native.stop_isolated_recovery_instance(
            pid_birth=res.get('process_birth'),
            socket_path=res.get('socket_path'),
            port=res.get('recovery_port'),
            db_user=rec['options'].get('recovery_db_user') or route.get('user') or 'root',
            db_password=rec['options'].get('recovery_db_password', pw),
            run_dir=res.get('short_run_dir'),
        )
        updated = jobs.update(rec['job_id'], recovery_running=not stopped['stopped'], recovery_stopped=stopped)
        return jobs.public(updated)

    if operation == 'reconcile':
        if set(request) != {'job_id', 'confirmed'} or request['confirmed'] is not True:
            raise MariaDBPhysicalError('Confirm reconciliation of one MariaDB physical job')
        rec = jobs.load(request['job_id'], owner, endpoint.id)
        jdir = jobs.job_dir(owner, endpoint.id, rec['job_id'])
        if rec['phase'] == 'prepare':
            base_rec = jobs.load(rec['options']['base_job_id'], owner, endpoint.id)
            inc_recs = [jobs.load(iid, owner, endpoint.id) for iid in rec['options']['incremental_job_ids']]
            recon = native.reconcile_interrupted_prepare(
                job_dir=jdir, base_record=base_rec, incremental_records=inc_recs
            )
            return jobs.public(jobs.update(rec['job_id'], state='reconciled', reconciliation=recon))
        obs = rec.get('process_observation') or {}
        alive = native.process_alive(obs.get('process_birth'))
        if alive:
            raise MariaDBPhysicalError('Native utility process is still running; cancel or wait before reconciling')
        recon = {
            'reconciled_at': time.time(),
            'process_termination_confirmed': True,
            'original_state': rec['state'],
            'artifact_adopted': rec.get('artifact_adoption_state') == 'artifact_adopted',
            'automatic_retry': False,
        }
        return jobs.public(jobs.update(rec['job_id'], state='reconciled', reconciliation=recon))

    client, route = _client_and_route(service, server)
    password = _acquire_password(client, route)

    if operation == 'inspect':
        if request:
            raise MariaDBPhysicalError('Physical source inspection takes no parameters')
        conn = client._connect({'route': {**route, 'autocommit': True}})
        try:
            return native.capture_source_state(conn)
        finally:
            client._discard_failed_session(conn)

    if operation == 'review':
        if set(request) != {'options'}:
            raise MariaDBPhysicalError('Review exact MariaDB physical options')
        opts = validate_options(request['options'])
        conn = client._connect({'route': {**route, 'autocommit': True}})
        try:
            captured = native.capture_source_state(conn)
        finally:
            client._discard_failed_session(conn)
        if any(captured['state']['encryption'].values()) and not opts.get('encryption_acknowledged'):
            raise MariaDBPhysicalError('Acknowledge encryption keyring prerequisites before physical backup')
        tool_info = native.admit_executable(
            opts['backup_binary'] if opts['phase'] != 'recover' else opts['mariadbd_binary'],
            'mariadb-backup' if opts['phase'] != 'recover' else 'mariadbd',
            version_prefix=opts['version_prefix'],
        )
        if opts['phase'] == 'prepare':
            base_rec = jobs.load(opts['base_job_id'], owner, endpoint.id)
            inc_recs = [jobs.load(iid, owner, endpoint.id) for iid in opts['incremental_job_ids']]
            native.validate_backup_chain(base_rec, inc_recs)
        extra_warn = []
        if captured['state']['volatile_memory_tables']:
            extra_warn.append('MEMORY table definitions are preserved, while volatile rows reset on restart.')
        return jobs.create_review(owner, endpoint.id, opts, captured, tool_info, extra_warnings=extra_warn)

    if operation == 'start':
        allowed_keys = {'job_id', 'review_digest', 'confirmed', 'async'}
        if not {'job_id', 'review_digest', 'confirmed'} <= set(request) or set(request) - allowed_keys or request['confirmed'] is not True:
            raise MariaDBPhysicalError('Confirm the exact MariaDB physical review before dispatch')
        rec = jobs.load(request['job_id'], owner, endpoint.id)
        if rec['review_digest'] != request['review_digest']:
            raise MariaDBPhysicalError('MariaDB physical review_digest does not match')
        if rec['state'] != 'reviewed':
            return jobs.public(rec)
        if time.time() > rec['expires_at']:
            raise MariaDBPhysicalError('MariaDB physical review expired; create a fresh review')
        sig = threading.Event()
        with jobs._lock:
            jobs._signals[rec['job_id']] = sig
        jobs.update(rec['job_id'], state='dispatching')
        rec = jobs.load(rec['job_id'], owner, endpoint.id)
        return _execute_job(
            service, server, jobs, rec, client, route, password, sig,
            synchronous=not bool(request.get('async', False)),
        )

    raise MariaDBPhysicalError(f'Unknown MariaDB physical continuity action: {operation!r}')
