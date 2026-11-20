"""Workspace service for native MariaDB wsrep / Galera cluster administration."""
import atexit
from copy import deepcopy
from pathlib import Path
import time
import uuid

from ..operations.fileio import exclusive_file_lock, private_directory, private_file
from ..operations.store import JsonOperationStore
from ..providers.mysql_family import mariadb_galera as native
from ..providers.mysql_family.mariadb_galera import MariaDBGaleraError
from ..providers.mysql_family.mariadb_host_services import control_managed_service
from ..providers.mysql_family.mariadb_physical import canonical_digest
from .mariadb_binlog_replay_service import source_server
from .mariadb_physical_service import _acquire_password, _admitted_endpoint, _client_and_route
from .mysql_binlog_jobs import identity


GALERA_OPERATIONS = frozenset({
    'bootstrap_cluster',
    'join_node',
    'set_desync',
    'stop_node',
    'rejoin_node',
    'recover_quorum',
})


class MariaDBGaleraJobStore:
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
                raise MariaDBGaleraError('Select an owned MariaDB Galera operation')
            return deepcopy(rec)
        return self._with_store(_r)

    def list(self, owner, endpoint_id, offset=0, limit=25):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise MariaDBGaleraError('Invalid MariaDB Galera job page bounds')
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
    owner, endpoint, _ctx = _admitted_endpoint(service, server, required_perms=('replication_admin', 'administer'))
    store = getattr(service.operation_bus, 'store', None)
    if not isinstance(store, JsonOperationStore):
        raise MariaDBGaleraError('MariaDB Galera management requires durable application storage')
    with service._semantic_lock:
        jobs = getattr(service, 'mariadb_galera_jobs', None)
        if jobs is None:
            root = (
                current_app.config.get('CDEADMIN_MARIADB_GALERA_ROOT')
                or str(store.path.parent / 'mariadb-galera')
            )
            jobs = service.mariadb_galera_jobs = MariaDBGaleraJobStore(
                str(store.path) + '.mariadb-galera', root
            )
            atexit.register(jobs.close)
    return jobs, owner, endpoint


def _inspect_registered_server(service, srv, *, host_datadir=None, host_provider_path=None):
    client, route = _client_and_route(service, srv)
    conn = client._connect({'route': {**route, 'autocommit': True}})
    try:
        return native.inspect_galera_node(
            conn, host_datadir=host_datadir, host_provider_path=host_provider_path
        )
    finally:
        client._discard_failed_session(conn)


def action(service, server, operation, request):
    if not isinstance(request, dict):
        raise MariaDBGaleraError('Select a MariaDB Galera request')
    jobs, owner, endpoint = manager(service, server)

    if operation == 'inspect':
        allowed = {'host_datadir', 'host_provider_path'}
        if set(request) - allowed:
            raise MariaDBGaleraError('Invalid MariaDB Galera inspect parameters')
        return _inspect_registered_server(
            service, server,
            host_datadir=request.get('host_datadir'),
            host_provider_path=request.get('host_provider_path'),
        )

    if operation == 'inspect_grastate':
        if set(request) != {'datadir'}:
            raise MariaDBGaleraError('Supply datadir to inspect grastate.dat')
        return native.inspect_grastate(request['datadir'])

    if operation == 'inspect_cluster':
        peer_ids = request.get('peer_server_ids', [])
        if not isinstance(peer_ids, list) or len(peer_ids) > 32:
            raise MariaDBGaleraError('Select up to 32 registered MariaDB peer_server_ids')
        members = []
        seed_obs = _inspect_registered_server(service, server)
        members.append({'server_id': server.id, 'name': server.name, 'reachable': True, 'observation': seed_obs})
        for pid in peer_ids:
            peer_srv = source_server(owner, pid)
            try:
                obs = _inspect_registered_server(service, peer_srv)
                members.append({'server_id': peer_srv.id, 'name': peer_srv.name, 'reachable': True, 'observation': obs})
            except Exception as exc:
                members.append({'server_id': peer_srv.id, 'name': peer_srv.name, 'reachable': False, 'error': str(exc)})
        uuids = {
            m['observation']['cluster']['wsrep_cluster_state_uuid']
            for m in members
            if m['reachable'] and m['observation'].get('galera_available')
        }
        return {
            'members': members,
            'uniform_cluster_uuid': len(uuids) == 1,
            'cluster_state_uuids': sorted(u for u in uuids if u),
            'async_replication_substituted': False,
        }

    if operation == 'list':
        if set(request) - {'offset', 'limit'}:
            raise MariaDBGaleraError('Invalid MariaDB Galera job list request')
        return jobs.list(owner, endpoint.id, **request)

    if operation == 'status':
        if set(request) != {'job_id'}:
            raise MariaDBGaleraError('Select one MariaDB Galera job')
        rec = jobs.load(request['job_id'], owner, endpoint.id)
        rec.pop('owner', None)
        return rec

    if operation == 'review':
        if set(request) != {'options'} or not isinstance(request['options'], dict):
            raise MariaDBGaleraError('Supply options to review a MariaDB Galera operation')
        opts = deepcopy(request['options'])
        op_kind = opts.get('operation')
        if op_kind not in GALERA_OPERATIONS:
            raise MariaDBGaleraError(f'Select a supported MariaDB Galera operation: {sorted(GALERA_OPERATIONS)}')

        preflight = {}
        warnings = [
            'Executes native MariaDB wsrep/Galera administration; asynchronous channels and Group Replication are never substituted.',
            'No Galera bootstrap, desync, or quorum promotion is ever automatically retried.',
        ]

        if op_kind == 'bootstrap_cluster':
            mode = opts.get('bootstrap_mode', 'grastate_and_verify')
            if mode not in {'grastate_and_verify', 'managed_daemon', 'promote_live_quorum'}:
                raise MariaDBGaleraError("Select bootstrap_mode 'grastate_and_verify', 'managed_daemon', or 'promote_live_quorum'")
            opts['bootstrap_mode'] = mode
            if opts.get('host_provider_path'):
                lib = native.inspect_provider_library(opts['host_provider_path'])
                if not lib['available_on_host']:
                    raise MariaDBGaleraError(f"Galera provider library unavailable: {lib['reason']}")
                preflight['provider_library'] = lib
            if opts.get('datadir'):
                gra = native.inspect_grastate(opts['datadir'])
                peer_seqnos = []
                for pdir in opts.get('peer_datadirs', []):
                    pg = native.inspect_grastate(pdir)
                    if pg.get('seqno') is not None:
                        peer_seqnos.append(pg['seqno'])
                if gra['exists'] and not gra['safe_to_bootstrap'] and not opts.get('force_safe_to_bootstrap'):
                    raise MariaDBGaleraError(
                        f"grastate.dat reports safe_to_bootstrap=0 (seqno={gra['seqno']}); bootstrap refused without explicit force_safe_to_bootstrap=True"
                    )
                if gra['exists'] and peer_seqnos and max(peer_seqnos) > (gra['seqno'] if gra['seqno'] is not None else -1):
                    raise MariaDBGaleraError(
                        f"Refusing bootstrap on stale node (seqno={gra['seqno']} < peer seqno={max(peer_seqnos)})"
                    )
                preflight['grastate'] = gra
                preflight['peer_seqnos'] = peer_seqnos
            elif mode == 'promote_live_quorum':
                obs = _inspect_registered_server(service, server)
                if not obs['galera_available']:
                    raise MariaDBGaleraError(f"Galera unavailable ({obs['availability_reason']})")
                preflight['live_observation'] = obs

        elif op_kind in {'set_desync', 'stop_node', 'recover_quorum'}:
            obs = _inspect_registered_server(service, server, host_datadir=opts.get('datadir'))
            if not obs['galera_available']:
                raise MariaDBGaleraError(
                    f"Galera wsrep_provider is unavailable on this MariaDB server ({obs['availability_reason']})"
                )
            opts['expected_server_uid'] = obs['identity']['server_uid']
            preflight['node_observation'] = obs

        elif op_kind in {'join_node', 'rejoin_node'}:
            seed_id = opts.get('seed_server_id')
            seed_srv = source_server(owner, seed_id) if seed_id else server
            seed_obs = _inspect_registered_server(service, seed_srv)
            if not seed_obs['galera_available'] or seed_obs['cluster']['wsrep_cluster_status'] != 'Primary':
                raise MariaDBGaleraError('Seed Galera cluster must have wsrep_provider loaded and Primary status')
            preflight['seed_observation'] = seed_obs

        jid = str(uuid.uuid4())
        rec = {
            'job_id': jid,
            'owner': owner,
            'endpoint_id': endpoint.id,
            'galera_operation': op_kind,
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
            'galera_operation': op_kind,
            'options': opts,
            'preflight': preflight,
        })
        return jobs.save_record(rec)

    if operation == 'start':
        if set(request) != {'job_id', 'review_digest', 'confirmed'} or request['confirmed'] is not True:
            raise MariaDBGaleraError('Confirm the exact MariaDB Galera review before execution')
        rec = jobs.load(request['job_id'], owner, endpoint.id)
        if rec['review_digest'] != request['review_digest']:
            raise MariaDBGaleraError('MariaDB Galera review_digest mismatch')
        if rec['state'] != 'reviewed':
            rec.pop('owner', None)
            return rec
        if time.time() > rec['expires_at']:
            raise MariaDBGaleraError('MariaDB Galera review expired')

        opts = rec['options']
        op_kind = rec['galera_operation']
        jdir = jobs.job_dir(owner, endpoint.id, rec['job_id'])
        client, route = _client_and_route(service, server)
        pw = _acquire_password(client, route)
        rec['state'] = 'executing'
        jobs.save_record(rec)

        try:
            if op_kind == 'bootstrap_cluster':
                mode = opts['bootstrap_mode']
                gra_prep = None
                if opts.get('datadir'):
                    peer_seqnos = []
                    for pdir in opts.get('peer_datadirs', []):
                        pg = native.inspect_grastate(pdir)
                        if pg.get('seqno') is not None:
                            peer_seqnos.append(pg['seqno'])
                    gra_prep = native.validate_and_prepare_grastate_bootstrap(
                        opts['datadir'],
                        allow_initial=bool(opts.get('allow_initial', True)),
                        force_safe_to_bootstrap=bool(opts.get('force_safe_to_bootstrap', False)),
                        peer_seqnos=peer_seqnos,
                        backup_dir=jdir,
                    )
                if mode == 'promote_live_quorum':
                    peer_seqs = []
                    for pid in opts.get('peer_server_ids', []):
                        psrv = source_server(owner, pid)
                        pobs = _inspect_registered_server(service, psrv)
                        if pobs.get('galera_available'):
                            peer_seqs.append(pobs['local_member']['wsrep_last_committed'])
                    conn = client._connect({'route': {**route, 'autocommit': True}})
                    try:
                        promoted = native.promote_non_primary_quorum(
                            conn, peer_committed_seqnos=peer_seqs
                        )
                    finally:
                        client._discard_failed_session(conn)
                    res = {'mode': mode, 'grastate_preparation': gra_prep, 'quorum_promotion': promoted}
                elif mode == 'managed_daemon':
                    started = control_managed_service(
                        action='start',
                        service_mode='managed_daemon',
                        state_dir=opts.get('state_dir') or str(jdir / 'galera-daemon'),
                        mariadbd_binary=opts['mariadbd_binary'],
                        defaults_file=opts.get('configuration_file'),
                        datadir=opts['datadir'],
                        port=int(opts.get('port') or route.get('port', 3306)),
                        bind_address=opts.get('bind_address', '127.0.0.1'),
                        daemon_user=opts.get('daemon_user'),
                        basedir=opts.get('basedir'),
                        plugin_dir=opts.get('plugin_dir'),
                        lc_messages_dir=opts.get('lc_messages_dir'),
                        extra_args=('--wsrep-new-cluster', *opts.get('extra_args', ())),
                        db_user=route.get('user') or 'root',
                        db_password=pw,
                    )
                    synced = native.wait_for_galera_synced(
                        host=route.get('host') or '127.0.0.1',
                        port=int(opts.get('port') or route.get('port', 3306)),
                        db_user=route.get('user') or 'root',
                        db_password=pw,
                        minimum_cluster_size=1,
                        timeout_seconds=int(opts.get('timeout_seconds', 90)),
                    )
                    res = {'mode': mode, 'grastate_preparation': gra_prep, 'daemon': started, 'synced_observation': synced}
                else:
                    if opts.get('verify_live', True):
                        synced = native.wait_for_galera_synced(
                            host=route.get('host') or '127.0.0.1',
                            port=int(route.get('port', 3306)),
                            db_user=route.get('user') or 'root',
                            db_password=pw,
                            minimum_cluster_size=1,
                            timeout_seconds=int(opts.get('timeout_seconds', 90)),
                        )
                    else:
                        synced = None
                    res = {'mode': mode, 'grastate_preparation': gra_prep, 'synced_observation': synced}

            elif op_kind == 'set_desync':
                conn = client._connect({'route': {**route, 'autocommit': True}})
                try:
                    res = native.set_node_desync(
                        conn,
                        enabled=bool(opts['enabled']),
                        expected_server_uid=opts.get('expected_server_uid'),
                    )
                finally:
                    client._discard_failed_session(conn)

            elif op_kind == 'stop_node':
                conn = client._connect({'route': {**route, 'autocommit': True}})
                try:
                    res = native.stop_galera_member(
                        conn,
                        expected_server_uid=opts.get('expected_server_uid'),
                        host_datadir=opts.get('datadir'),
                    )
                finally:
                    client._discard_failed_session(conn)

            elif op_kind in {'join_node', 'rejoin_node'}:
                seed_obs = rec['preflight']['seed_observation']
                expected_uuid = seed_obs['cluster']['wsrep_cluster_state_uuid']
                min_size = int(opts.get('expected_cluster_size', 2))
                min_committed = (
                    seed_obs['local_member']['wsrep_last_committed']
                    if op_kind == 'rejoin_node' else None
                )
                if opts.get('start_managed_daemon'):
                    control_managed_service(
                        action='start',
                        service_mode='managed_daemon',
                        state_dir=opts.get('state_dir') or str(jdir / 'galera-joiner'),
                        mariadbd_binary=opts['mariadbd_binary'],
                        defaults_file=opts.get('configuration_file'),
                        datadir=opts['datadir'],
                        port=int(opts.get('port') or route.get('port', 3306)),
                        bind_address=opts.get('bind_address', '127.0.0.1'),
                        daemon_user=opts.get('daemon_user'),
                        basedir=opts.get('basedir'),
                        plugin_dir=opts.get('plugin_dir'),
                        lc_messages_dir=opts.get('lc_messages_dir'),
                        db_user=route.get('user') or 'root',
                        db_password=pw,
                    )
                synced = native.wait_for_galera_synced(
                    host=route.get('host') or '127.0.0.1',
                    port=int(route.get('port', 3306)),
                    db_user=route.get('user') or 'root',
                    db_password=pw,
                    expected_cluster_uuid=expected_uuid,
                    minimum_cluster_size=min_size,
                    minimum_last_committed=min_committed,
                    timeout_seconds=int(opts.get('timeout_seconds', 90)),
                )
                res = {
                    'operation': op_kind,
                    'seed_cluster_uuid': expected_uuid,
                    'minimum_last_committed_required': min_committed,
                    'member_observation': synced,
                }

            elif op_kind == 'recover_quorum':
                peer_seqs = []
                for pid in opts.get('peer_server_ids', []):
                    psrv = source_server(owner, pid)
                    try:
                        pobs = _inspect_registered_server(service, psrv)
                        if pobs.get('galera_available'):
                            peer_seqs.append(pobs['local_member']['wsrep_last_committed'])
                    except Exception:
                        pass
                conn = client._connect({'route': {**route, 'autocommit': True}})
                try:
                    res = native.promote_non_primary_quorum(
                        conn,
                        expected_server_uid=opts.get('expected_server_uid'),
                        peer_committed_seqnos=peer_seqs,
                    )
                finally:
                    client._discard_failed_session(conn)

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

    raise MariaDBGaleraError(f'Unknown MariaDB Galera action: {operation!r}')
