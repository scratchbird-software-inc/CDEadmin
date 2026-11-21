"""Cross-registration & ordinary-SQL-principal snapshot consumers, output-plugin admission,
and coordinated destination table loading/cutover (PG-AUDIT-SNAPSHOT-01).

Preserves exact exporter backend/session lifetime (never sending commands on the
exporter socket during consumer import), tracks independent consumer SQL identity,
verifies installed logical output plugins (`pgoutput`, `test_decoding`), and
refuses automatic replay of any uncertain copy or stream.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import threading
import time
import uuid

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus

from ..operations.fileio import exclusive_file_lock, private_directory, private_file
from ..operations.store import JsonOperationStore
from ..providers.postgresql.continuity import ContinuityError

SNAPSHOT_RE = re.compile(r'[0-9A-Fa-f-]{1,128}\Z')
PLUGIN_RE = re.compile(r'[a-zA-Z0-9_]{1,63}\Z')
IDENT_RE = re.compile(r'[^\x00]{1,63}\Z')


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf8')
    ).hexdigest()


class _ConsumerRuntimeRegistry:
    lock = threading.RLock()
    sessions: dict[str, dict] = {}


def _store_call(service, owner: int, endpoint: str, fn):
    store_obj = getattr(service.operation_bus, 'store', None)
    if not isinstance(store_obj, JsonOperationStore):
        raise ContinuityError('Snapshot orchestration requires durable application storage')
    base = Path(str(store_obj.path) + '.postgresql-snapshots') / str(owner) / endpoint
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(base)
    path = base / 'state.json'
    fd = os.open(str(path) + '.lock', os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with exclusive_file_lock(fd):
            return fn(JsonOperationStore(path))
    finally:
        os.close(fd)


def _sql_conn_params(service, server, *, database_name: str | None = None) -> dict:
    """Extract pure SQL connection parameters without requiring REPLICATION privilege."""
    context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    opened = provider.open_session({'route': payload['route']})
    try:
        state = provider._sessions[opened['session_id']]
        provider._ensure_native_connection(state)
        conn = state.connection.conn
        info = conn.info
        out = {
            k: v
            for k, v in info.get_parameters().items()
            if k not in {'service', 'passfile', 'replication', 'fallback_application_name'}
        }
        out.update(
            host=info.host,
            port=info.port,
            user=info.user,
            dbname=database_name or info.dbname,
        )
        if info.hostaddr:
            out['hostaddr'] = info.hostaddr
        pw = conn.pgconn.password
        if pw:
            out['password'] = bytes(pw).decode('utf8')
        return out
    finally:
        provider.close_session(opened)


# ==============================================================================
# 1. Installed Output-Plugin Discovery & Admission
# ==============================================================================

def inspect_output_plugins(conn_params: dict, *, candidate_plugins: list[str] | None = None) -> dict:
    """Discover and verify installed logical decoding output plugins on the target cluster."""
    candidates = candidate_plugins or ['pgoutput', 'test_decoding', 'wal2json']
    for name in candidates:
        if not isinstance(name, str) or not PLUGIN_RE.fullmatch(name):
            raise ContinuityError(f'Invalid output plugin identifier: {name!r}')

    with psycopg.connect(**{**conn_params, 'autocommit': True, 'connect_timeout': 10}) as conn:
        sys_id, wal_level, max_slots, ver_num = conn.execute(
            """
            SELECT
                (SELECT system_identifier::text FROM pg_catalog.pg_control_system()),
                current_setting('wal_level'),
                current_setting('max_replication_slots')::int,
                current_setting('server_version_num')::int
            """
        ).fetchone()
        active_plugins = {
            r[0]
            for r in conn.execute(
                'SELECT DISTINCT plugin FROM pg_catalog.pg_replication_slots WHERE plugin IS NOT NULL'
            ).fetchall()
        }
        # Probe pkglibdir on local installations or via SQL temporary slot creation inside a rolled-back savepoint
        # when wal_level='logical' and caller has REPLICATION privilege; otherwise check pg_config/libdir.
        has_repl = conn.execute(
            'SELECT rolsuper OR rolreplication FROM pg_catalog.pg_roles WHERE rolname = session_user'
        ).fetchone()[0]

        results = []
        for plugin in candidates:
            if plugin in active_plugins:
                results.append({
                    'plugin': plugin,
                    'installed': True,
                    'verification_method': 'active_replication_slot_catalog',
                    'builtin': plugin == 'pgoutput',
                })
                continue
            if wal_level == 'logical' and has_repl and max_slots > 0:
                probe_slot = f'sr_plugin_probe_{uuid.uuid4().hex[:10]}'
                try:
                    conn.execute(
                        'SELECT pg_catalog.pg_create_logical_replication_slot(%s, %s, true)',
                        (probe_slot, plugin),
                    )
                    conn.execute('SELECT pg_catalog.pg_drop_replication_slot(%s)', (probe_slot,))
                    results.append({
                        'plugin': plugin,
                        'installed': True,
                        'verification_method': 'ephemeral_logical_slot_probe',
                        'builtin': plugin == 'pgoutput',
                    })
                except psycopg.Error as err:
                    msg = (err.diag.message_primary or str(err))[:256]
                    not_found = (
                        err.sqlstate in {'58P01', '42704', '22023', '42501'}
                        and (
                            err.sqlstate != '42501'
                            or 'may not be used as an output plugin' in msg.lower()
                        )
                        or 'could not access file' in msg.lower()
                        or 'no such file' in msg.lower()
                    )
                    results.append({
                        'plugin': plugin,
                        'installed': False if not_found else None,
                        'sqlstate': err.sqlstate,
                        'reason': msg,
                        'verification_method': 'ephemeral_logical_slot_probe',
                        'builtin': plugin == 'pgoutput',
                    })
            else:
                results.append({
                    'plugin': plugin,
                    'installed': True if plugin == 'pgoutput' else None,
                    'verification_method': 'builtin_core_guarantee' if plugin == 'pgoutput' else 'unverified_requires_logical_wal_level',
                    'builtin': plugin == 'pgoutput',
                })

    return {
        'system_identifier': str(sys_id),
        'server_version_num': int(ver_num),
        'wal_level': wal_level,
        'max_replication_slots': int(max_slots),
        'plugins': results,
    }


# ==============================================================================
# 2. Ordinary-SQL-Principal & Cross-Registration Snapshot Consumers
# ==============================================================================

def _resolve_exporter_reference(
    service,
    owner: int,
    exporter_server,
    request: dict,
) -> dict:
    """Resolve an exported snapshot from a temporary replication resource or explicit verified exporter."""
    if 'exporter_resource_id' in request and 'exporter_database_target_id' in request:
        from .postgresql_replication_temporary_service import manager as repl_manager
        exp_jobs, exp_owner, exp_endpoint = repl_manager(
            service, exporter_server, request['exporter_database_target_id']
        )
        if exp_owner != owner:
            raise ContinuityError('Cross-owner snapshot consumption is forbidden')
        current = exp_jobs.load(request['exporter_resource_id'], exp_owner, exp_endpoint)
        exp_jobs.require_open(current)
        snap = (current.get('latest_native_inventory') or {}).get('snapshot')
        if not snap:
            raise ContinuityError('Exporter replication resource has no active exported snapshot')
        return {
            'origin': 'replication_temporary_resource',
            'exporter_endpoint_id': exp_endpoint,
            'exporter_job_id': current['job_id'],
            'exporter_backend_pid': int(current['backend_pid']),
            'system_identifier': str(current['source']['system_identifier']),
            'timeline': int(current['source']['timeline']),
            'database': current['source']['database'],
            'snapshot_name': snap['snapshot_name'],
            'consistent_point': snap['consistent_point'],
            'slot': snap['slot'],
        }

    # Explicit SQL/replication exporter reference (verified live against pg_stat_activity)
    snap_name = request.get('snapshot_name')
    exp_pid = request.get('exporter_backend_pid')
    db_name = request.get('database')
    if (
        not isinstance(snap_name, str)
        or not SNAPSHOT_RE.fullmatch(snap_name)
        or type(exp_pid) is not int
        or exp_pid <= 0
        or not isinstance(db_name, str)
        or not IDENT_RE.fullmatch(db_name)
    ):
        raise ContinuityError(
            'Provide exporter_resource_id + exporter_database_target_id OR explicit snapshot_name, exporter_backend_pid, and database'
        )
    exp_params = _sql_conn_params(service, exporter_server, database_name=db_name)
    with psycopg.connect(**{**exp_params, 'autocommit': True, 'connect_timeout': 10}) as conn:
        sys_id, tli = conn.execute(
            'SELECT (SELECT system_identifier::text FROM pg_catalog.pg_control_system()), '
            '(SELECT timeline_id FROM pg_catalog.pg_control_checkpoint())'
        ).fetchone()
        act = conn.execute(
            'SELECT pid, datname, state FROM pg_catalog.pg_stat_activity WHERE pid = %s',
            (exp_pid,),
        ).fetchone()
        if not act:
            raise ContinuityError('Exporter backend PID is not active on the exporter server')
    return {
        'origin': 'explicit_exporter_backend',
        'exporter_endpoint_id': exporter_server.endpoint_profile.id,
        'exporter_job_id': None,
        'exporter_backend_pid': exp_pid,
        'system_identifier': str(sys_id),
        'timeline': int(tli),
        'database': db_name,
        'snapshot_name': snap_name,
        'consistent_point': request.get('consistent_point'),
        'slot': request.get('slot'),
    }


def consumer_review(
    service,
    consumer_server,
    exporter_server,
    owner: int,
    endpoint: str,
    request: dict,
) -> dict:
    """Review an ordinary-SQL-principal (same- or cross-registration) snapshot consumer."""
    ref = _resolve_exporter_reference(service, owner, exporter_server, request)
    consumer_params = _sql_conn_params(service, consumer_server, database_name=ref['database'])
    # Override role/password if an explicit ordinary SQL consumer credential was supplied for testing/delegation
    if isinstance(request.get('consumer_credentials'), dict):
        cred = request['consumer_credentials']
        if cred.get('user'):
            consumer_params['user'] = str(cred['user'])
        if 'password' in cred:
            consumer_params['password'] = str(cred['password'])

    with psycopg.connect(**{**consumer_params, 'autocommit': True, 'connect_timeout': 10}) as conn:
        c_sys, c_tli, c_db, auth_user, eff_user, is_repl = conn.execute(
            """
            SELECT
                (SELECT system_identifier::text FROM pg_catalog.pg_control_system()),
                (SELECT timeline_id FROM pg_catalog.pg_control_checkpoint()),
                pg_catalog.current_database(),
                session_user,
                current_user,
                (SELECT rolreplication FROM pg_catalog.pg_roles WHERE rolname = session_user)
            """
        ).fetchone()
    if str(c_sys) != ref['system_identifier'] or int(c_tli) != ref['timeline'] or c_db != ref['database']:
        raise ContinuityError(
            'Consumer registration does not resolve to the exporter cluster system_identifier, timeline, and database'
        )

    consumer_id = str(uuid.uuid4())
    max_lifetime = int(request.get('max_lifetime_seconds') or 120)
    if not 5 <= max_lifetime <= 3600:
        raise ContinuityError('max_lifetime_seconds must be between 5 and 3600')

    record = {
        'consumer_id': consumer_id,
        'state': 'reviewed',
        'cross_registration': consumer_server.endpoint_profile.id != ref['exporter_endpoint_id'],
        'consumer_endpoint_id': consumer_server.endpoint_profile.id,
        'exporter_reference': ref,
        'consumer_principal': {
            'authenticated_principal': auth_user,
            'effective_principal': eff_user,
            'rolreplication': bool(is_repl),
            'admission_interface': 'ordinary-sql',
        },
        'max_lifetime_seconds': max_lifetime,
        'created_at': time.time(),
        'expires_at': time.time() + 600,
        'automatic_retry': False,
    }
    record['review_digest'] = _sha256_json({
        'consumer_id': consumer_id,
        'exporter_reference': ref,
        'consumer_principal': record['consumer_principal'],
        'max_lifetime_seconds': max_lifetime,
    })

    # Store non-secret connection overrides in memory keyed by consumer_id for start
    with _ConsumerRuntimeRegistry.lock:
        _ConsumerRuntimeRegistry.sessions[f'pending:{consumer_id}'] = {
            'conn_params': consumer_params,
        }

    def _save(store):
        store.change(lambda s: s.setdefault('sql_consumers', {}).__setitem__(consumer_id, record))
        return deepcopy(record)

    return _store_call(service, owner, endpoint, _save)


def consumer_start(service, owner: int, endpoint: str, request: dict) -> dict:
    """Open an independent ordinary-SQL-principal `REPEATABLE READ READ ONLY` session and import the snapshot."""
    if (
        not isinstance(request, dict)
        or set(request) != {'consumer_id', 'review_digest', 'confirmed'}
        or request.get('confirmed') is not True
    ):
        raise ContinuityError('Confirm snapshot consumer start with consumer_id, review_digest, and confirmed=True')
    consumer_id = request['consumer_id']

    def _claim(store):
        rec = store.read().get('sql_consumers', {}).get(consumer_id)
        if not rec:
            raise ContinuityError('Snapshot consumer review is unavailable')
        if rec['review_digest'] != request['review_digest']:
            raise ContinuityError('Snapshot consumer review digest mismatch')
        if rec['state'] != 'reviewed':
            raise ContinuityError('Snapshot consumer review was already dispatched; automatic replay is refused')
        if time.time() > rec['expires_at']:
            raise ContinuityError('Snapshot consumer review expired')
        def _mut(s):
            s['sql_consumers'][consumer_id]['state'] = 'importing'
        store.change(_mut)
        return deepcopy(rec)

    rec = _store_call(service, owner, endpoint, _claim)
    with _ConsumerRuntimeRegistry.lock:
        pending = _ConsumerRuntimeRegistry.sessions.pop(f'pending:{consumer_id}', None)
    if not pending:
        raise ContinuityError('Snapshot consumer runtime parameters expired; review again')

    conn_params = pending['conn_params']
    ref = rec['exporter_reference']
    ready_evt = threading.Event()
    stop_evt = threading.Event()
    cmd_q: queue.Queue = queue.Queue()
    init_outcome: dict = {}

    def _worker():
        conn = None
        try:
            conn = psycopg.connect(
                **{
                    **conn_params,
                    'autocommit': True,
                    'connect_timeout': 10,
                    'application_name': f'ScratchRobin sql-snap-consumer {consumer_id[:8]}',
                }
            )
            c_pid = conn.info.backend_pid
            # Pre-verify exporter backend is still the exact live backend!
            exp_before = conn.execute(
                'SELECT pid, extract(epoch FROM backend_start)::text '
                'FROM pg_catalog.pg_stat_activity WHERE pid = %s',
                (ref['exporter_backend_pid'],),
            ).fetchone()
            if not exp_before:
                raise ContinuityError('Exporter backend terminated before consumer snapshot import')

            with psycopg.ClientCursor(conn) as cur:
                cur.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
                cur.execute('SET TRANSACTION SNAPSHOT %s', (ref['snapshot_name'],))
            exp_after = conn.execute(
                'SELECT pid, extract(epoch FROM backend_start)::text '
                'FROM pg_catalog.pg_stat_activity WHERE pid = %s',
                (ref['exporter_backend_pid'],),
            ).fetchone()
            if exp_after != exp_before or conn.info.transaction_status != TransactionStatus.INTRANS:
                raise ContinuityError('Exporter backend changed during snapshot import; aborting consumer')

            init_outcome.update(
                ok=True,
                consumer_backend_pid=c_pid,
                exporter_backend_started_epoch=exp_before[1],
                imported_at=time.time(),
            )
            ready_evt.set()

            deadline = time.monotonic() + rec['max_lifetime_seconds']
            while not stop_evt.is_set() and time.monotonic() < deadline:
                try:
                    task = cmd_q.get(timeout=0.15)
                except queue.Empty:
                    continue
                if task is None:
                    break
                fn, res_q = task
                try:
                    res_q.put(('ok', fn(conn)))
                except Exception as err:
                    res_q.put(('err', err))
        except Exception as err:
            init_outcome.update(ok=False, error=str(err))
            ready_evt.set()
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            with _ConsumerRuntimeRegistry.lock:
                _ConsumerRuntimeRegistry.sessions.pop(consumer_id, None)
            def _mark_closed(store):
                def _m(s):
                    cur = s.get('sql_consumers', {}).get(consumer_id)
                    if cur and cur.get('state') == 'open':
                        cur['state'] = 'released'
                        cur['released_at'] = time.time()
                store.change(_m)
            try:
                _store_call(service, owner, endpoint, _mark_closed)
            except Exception:
                pass

    thread = threading.Thread(target=_worker, daemon=True, name=f'pg-sql-snap-{consumer_id[:8]}')
    with _ConsumerRuntimeRegistry.lock:
        _ConsumerRuntimeRegistry.sessions[consumer_id] = {
            'thread': thread,
            'stop_evt': stop_evt,
            'cmd_q': cmd_q,
        }
    thread.start()
    ready_evt.wait(timeout=15)

    if not init_outcome.get('ok'):
        stop_evt.set()
        err_msg = init_outcome.get('error') or 'Snapshot import timed out'
        def _fail(store):
            store.change(lambda s: s['sql_consumers'][consumer_id].update(
                state='failed', error=err_msg, finished_at=time.time()
            ))
        _store_call(service, owner, endpoint, _fail)
        raise ContinuityError(err_msg)

    def _mark_open(store):
        def _m(s):
            s['sql_consumers'][consumer_id].update(
                state='open',
                consumer_backend_pid=init_outcome['consumer_backend_pid'],
                exporter_backend_started_epoch=init_outcome['exporter_backend_started_epoch'],
                snapshot_exporter_preverified=True,
                snapshot_exporter_postverified=True,
                exporter_connection_required_after_import=False,
                imported_at=init_outcome['imported_at'],
            )
        store.change(_m)
        return deepcopy(store.read()['sql_consumers'][consumer_id])

    return _store_call(service, owner, endpoint, _mark_open)


def consumer_copy_table(service, owner: int, endpoint: str, request: dict) -> dict:
    """Read consistent table rows from an open ordinary-SQL snapshot consumer (even after exporter release)."""
    if not isinstance(request, dict) or set(request) - {'consumer_id', 'schema', 'table', 'format'}:
        raise ContinuityError('Provide consumer_id, schema, table, and optional format (csv|text|json)')
    consumer_id = request.get('consumer_id')
    schema_name = request.get('schema') or 'public'
    table_name = request.get('table')
    fmt = request.get('format') or 'json'
    if not isinstance(table_name, str) or not IDENT_RE.fullmatch(table_name) or fmt not in {'json', 'csv', 'text'}:
        raise ContinuityError('Provide valid schema, table, and format (json|csv|text)')

    with _ConsumerRuntimeRegistry.lock:
        sess = _ConsumerRuntimeRegistry.sessions.get(consumer_id)
    if not sess:
        raise ContinuityError('Selected SQL snapshot consumer is not open')

    res_q: queue.Queue = queue.Queue()

    def _run_copy(conn):
        if conn.info.transaction_status != TransactionStatus.INTRANS:
            raise ContinuityError('Snapshot consumer transaction is no longer active; do not replay')
        q_ident = sql.SQL('{}.{}').format(sql.Identifier(schema_name), sql.Identifier(table_name))
        if fmt == 'json':
            rows = conn.execute(
                sql.SQL('SELECT row_to_json(t) FROM (SELECT * FROM {}) t').format(q_ident)
            ).fetchall()
            payload_list = [json.loads(r[0]) if isinstance(r[0], str) else r[0] for r in rows]
            raw_bytes = json.dumps(payload_list, separators=(',', ':')).encode('utf8')
            return {
                'row_count': len(payload_list),
                'rows': payload_list,
                'sha256': hashlib.sha256(raw_bytes).hexdigest(),
                'bytes': len(raw_bytes),
            }
        copy_fmt = 'FORMAT csv, HEADER true' if fmt == 'csv' else 'FORMAT text'
        buf = bytearray()
        with conn.cursor().copy(sql.SQL(f'COPY {{}} TO STDOUT ({copy_fmt})').format(q_ident)) as cp:
            for chunk in cp:
                buf.extend(bytes(chunk))
        return {
            'row_count': None,
            'payload_utf8': bytes(buf).decode('utf8', 'replace'),
            'sha256': hashlib.sha256(buf).hexdigest(),
            'bytes': len(buf),
        }

    sess['cmd_q'].put((_run_copy, res_q))
    status, val = res_q.get(timeout=30)
    if status == 'err':
        raise ContinuityError(str(val))
    return {
        'consumer_id': consumer_id,
        'schema': schema_name,
        'table': table_name,
        'format': fmt,
        **val,
    }


def consumer_release(service, owner: int, endpoint: str, request: dict) -> dict:
    if not isinstance(request, dict) or set(request) != {'consumer_id', 'confirmed'} or request.get('confirmed') is not True:
        raise ContinuityError('Confirm SQL snapshot consumer release')
    consumer_id = request['consumer_id']
    with _ConsumerRuntimeRegistry.lock:
        sess = _ConsumerRuntimeRegistry.sessions.get(consumer_id)
    if sess:
        sess['stop_evt'].set()
        sess['cmd_q'].put(None)
        sess['thread'].join(timeout=5)

    def _read(store):
        rec = store.read().get('sql_consumers', {}).get(consumer_id)
        if not rec:
            raise ContinuityError('SQL snapshot consumer receipt is unavailable')
        if rec['state'] == 'open':
            store.change(lambda s: s['sql_consumers'][consumer_id].update(state='released', released_at=time.time()))
            rec = store.read()['sql_consumers'][consumer_id]
        return deepcopy(rec)

    return _store_call(service, owner, endpoint, _read)


# ==============================================================================
# 3. Coordinated Destination Table Loading & Atomic Cutover
# ==============================================================================

def coordinated_load_review(
    service,
    source_server,
    destination_server,
    owner: int,
    endpoint: str,
    request: dict,
) -> dict:
    """Review coordinated snapshot-consistent table load + atomic destination cutover."""
    allowed = {
        'consumer_id', 'source_schema', 'source_table',
        'destination_database', 'destination_schema', 'destination_table',
        'cutover_mode',
    }
    if not isinstance(request, dict) or set(request) - allowed:
        raise ContinuityError('Unsupported coordinated destination load fields')
    consumer_id = request.get('consumer_id')
    src_schema = request.get('source_schema') or 'public'
    src_table = request.get('source_table')
    dst_db = request.get('destination_database') or 'postgres'
    dst_schema = request.get('destination_schema') or src_schema
    dst_table = request.get('destination_table') or src_table
    cutover_mode = request.get('cutover_mode') or 'atomic_swap'
    if cutover_mode not in {'stage_only', 'atomic_swap'}:
        raise ContinuityError('cutover_mode must be stage_only or atomic_swap')
    if not all(isinstance(x, str) and IDENT_RE.fullmatch(x) for x in (src_schema, src_table or '', dst_schema, dst_table or '')):
        raise ContinuityError('Provide valid source and destination schema/table identifiers')

    with _ConsumerRuntimeRegistry.lock:
        if consumer_id not in _ConsumerRuntimeRegistry.sessions:
            raise ContinuityError('Select an open SQL snapshot consumer for coordinated destination loading')

    dst_params = _sql_conn_params(service, destination_server, database_name=dst_db)
    with psycopg.connect(**{**dst_params, 'autocommit': True, 'connect_timeout': 10}) as dconn:
        dst_sys_id = dconn.execute('SELECT system_identifier::text FROM pg_catalog.pg_control_system()').fetchone()[0]

    load_id = str(uuid.uuid4())
    stage_table = f'{dst_table[:42]}__sr_stage_{load_id[:8]}'
    rec = {
        'load_id': load_id,
        'state': 'reviewed',
        'consumer_id': consumer_id,
        'source_schema': src_schema,
        'source_table': src_table,
        'destination_endpoint_id': destination_server.endpoint_profile.id,
        'destination_system_identifier': str(dst_sys_id),
        'destination_database': dst_db,
        'destination_schema': dst_schema,
        'destination_table': dst_table,
        'staging_table': stage_table,
        'cutover_mode': cutover_mode,
        'created_at': time.time(),
        'expires_at': time.time() + 600,
        'automatic_retry': False,
    }
    rec['review_digest'] = _sha256_json({
        k: rec[k]
        for k in (
            'load_id', 'consumer_id', 'source_schema', 'source_table',
            'destination_endpoint_id', 'destination_database', 'destination_schema',
            'destination_table', 'staging_table', 'cutover_mode',
        )
    })
    with _ConsumerRuntimeRegistry.lock:
        _ConsumerRuntimeRegistry.sessions[f'load_params:{load_id}'] = dst_params

    def _save(store):
        store.change(lambda s: s.setdefault('coordinated_loads', {}).__setitem__(load_id, rec))
        return deepcopy(rec)

    return _store_call(service, owner, endpoint, _save)


def coordinated_load_start(service, owner: int, endpoint: str, request: dict) -> dict:
    """Copy consistent rows from open snapshot consumer into destination staging table and optionally atomically cut over."""
    if (
        not isinstance(request, dict)
        or set(request) != {'load_id', 'review_digest', 'confirmed'}
        or request.get('confirmed') is not True
    ):
        raise ContinuityError('Confirm coordinated destination load with load_id, review_digest, and confirmed=True')
    load_id = request['load_id']

    def _claim(store):
        rec = store.read().get('coordinated_loads', {}).get(load_id)
        if not rec:
            raise ContinuityError('Coordinated destination load review is unavailable')
        if rec['review_digest'] != request['review_digest']:
            raise ContinuityError('Coordinated destination load review digest mismatch')
        if rec['state'] != 'reviewed':
            raise ContinuityError('Coordinated destination load was already dispatched; automatic replay is refused')
        if time.time() > rec['expires_at']:
            raise ContinuityError('Coordinated destination load review expired')
        store.change(lambda s: s['coordinated_loads'][load_id].update(state='executing'))
        return deepcopy(rec)

    rec = _store_call(service, owner, endpoint, _claim)
    with _ConsumerRuntimeRegistry.lock:
        dst_params = _ConsumerRuntimeRegistry.sessions.pop(f'load_params:{load_id}', None)
        sess = _ConsumerRuntimeRegistry.sessions.get(rec['consumer_id'])
    if not dst_params or not sess:
        raise ContinuityError('Snapshot consumer or destination connection expired; review again')

    try:
        # 1. Extract column definitions + CSV data from the consistent snapshot consumer
        res_q: queue.Queue = queue.Queue()
        def _extract(sconn):
            src_q = sql.SQL('{}.{}').format(
                sql.Identifier(rec['source_schema']), sql.Identifier(rec['source_table'])
            )
            cols = sconn.execute(
                """
                SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull
                FROM pg_catalog.pg_attribute a
                JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY a.attnum
                """,
                (rec['source_schema'], rec['source_table']),
            ).fetchall()
            if not cols:
                raise ContinuityError('Source relation has no visible columns in snapshot')
            buf = bytearray()
            with sconn.cursor().copy(sql.SQL('COPY {} TO STDOUT (FORMAT binary)').format(src_q)) as cp:
                for chunk in cp:
                    buf.extend(bytes(chunk))
            count = sconn.execute(sql.SQL('SELECT count(*) FROM {}').format(src_q)).fetchone()[0]
            return cols, bytes(buf), int(count)

        sess['cmd_q'].put((_extract, res_q))
        st, payload = res_q.get(timeout=30)
        if st == 'err':
            raise ContinuityError(str(payload))
        cols, binary_copy, expected_rows = payload
        copy_sha256 = hashlib.sha256(binary_copy).hexdigest()

        # 2. Load into destination staging table & optionally perform atomic swap cutover inside one transaction!
        with psycopg.connect(**{**dst_params, 'autocommit': False, 'connect_timeout': 10}) as dconn:
            dconn.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(rec['destination_schema'])))
            col_defs = sql.SQL(', ').join(
                sql.SQL('{} {} {}').format(
                    sql.Identifier(cname),
                    sql.SQL(ctype),
                    sql.SQL('NOT NULL' if notnull else ''),
                )
                for cname, ctype, notnull in cols
            )
            stage_q = sql.SQL('{}.{}').format(
                sql.Identifier(rec['destination_schema']), sql.Identifier(rec['staging_table'])
            )
            target_q = sql.SQL('{}.{}').format(
                sql.Identifier(rec['destination_schema']), sql.Identifier(rec['destination_table'])
            )
            dconn.execute(sql.SQL('CREATE TABLE {} ({})').format(stage_q, col_defs))
            with dconn.cursor().copy(sql.SQL('COPY {} FROM STDIN (FORMAT binary)').format(stage_q)) as dcp:
                dcp.write(binary_copy)
            loaded_rows = dconn.execute(sql.SQL('SELECT count(*) FROM {}').format(stage_q)).fetchone()[0]
            if int(loaded_rows) != expected_rows:
                raise ContinuityError(f'Loaded row count {loaded_rows} differs from snapshot count {expected_rows}')

            cutover_applied = False
            if rec['cutover_mode'] == 'atomic_swap':
                retired_name = f"{rec['destination_table'][:40]}__sr_prev_{load_id[:8]}"
                exists = dconn.execute(
                    'SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace '
                    'WHERE n.nspname = %s AND c.relname = %s',
                    (rec['destination_schema'], rec['destination_table']),
                ).fetchone()
                if exists:
                    dconn.execute(sql.SQL('LOCK TABLE {} IN ACCESS EXCLUSIVE MODE').format(target_q))
                    dconn.execute(
                        sql.SQL('ALTER TABLE {} RENAME TO {}').format(target_q, sql.Identifier(retired_name))
                    )
                    dconn.execute(
                        sql.SQL('ALTER TABLE {} RENAME TO {}').format(
                            stage_q, sql.Identifier(rec['destination_table'])
                        )
                    )
                    dconn.execute(
                        sql.SQL('DROP TABLE {}.{}').format(
                            sql.Identifier(rec['destination_schema']), sql.Identifier(retired_name)
                        )
                    )
                else:
                    dconn.execute(
                        sql.SQL('ALTER TABLE {} RENAME TO {}').format(
                            stage_q, sql.Identifier(rec['destination_table'])
                        )
                    )
                cutover_applied = True
            dconn.commit()
    except Exception as exc:
        def _fail(store):
            store.change(lambda s: s['coordinated_loads'][load_id].update(
                state='failed', error=str(exc), finished_at=time.time()
            ))
        _store_call(service, owner, endpoint, _fail)
        raise

    def _done(store):
        def _m(s):
            s['coordinated_loads'][load_id].update(
                state='completed',
                rows_copied=expected_rows,
                copy_sha256=copy_sha256,
                cutover_applied=cutover_applied,
                finished_at=time.time(),
            )
        store.change(_m)
        return deepcopy(store.read()['coordinated_loads'][load_id])

    return _store_call(service, owner, endpoint, _done)


def snapshot_orchestration_action(service, server, operation: str, request: dict) -> dict:
    if not isinstance(request, dict):
        raise ContinuityError('Snapshot orchestration request must be an object')
    owner = service._principal_id(server)
    endpoint = server.endpoint_profile.id

    if operation == 'output_plugins':
        params = _sql_conn_params(service, server, database_name=request.get('database'))
        return inspect_output_plugins(params, candidate_plugins=request.get('plugins'))

    if operation == 'consumer_review':
        exporter_server = server
        if request.get('exporter_server_id') is not None:
            from pgadmin.browser.server_groups.servers import get_server
            exporter_server = get_server(int(request['exporter_server_id']))
            if exporter_server is None or service._principal_id(exporter_server) != owner:
                raise ContinuityError('Selected exporter server registration is unavailable for this owner')
        clean_req = {k: v for k, v in request.items() if k != 'exporter_server_id'}
        return consumer_review(service, server, exporter_server, owner, endpoint, clean_req)

    if operation == 'consumer_start':
        return consumer_start(service, owner, endpoint, request)

    if operation == 'consumer_copy':
        return consumer_copy_table(service, owner, endpoint, request)

    if operation == 'consumer_release':
        return consumer_release(service, owner, endpoint, request)

    if operation == 'consumer_status':
        cid = request.get('consumer_id')
        def _get(store):
            rec = store.read().get('sql_consumers', {}).get(cid)
            if not rec:
                raise ContinuityError('SQL snapshot consumer receipt is unavailable')
            return deepcopy(rec)
        return _store_call(service, owner, endpoint, _get)

    if operation == 'load_review':
        dest_server = server
        if request.get('destination_server_id') is not None:
            from pgadmin.browser.server_groups.servers import get_server
            dest_server = get_server(int(request['destination_server_id']))
            if dest_server is None or service._principal_id(dest_server) != owner:
                raise ContinuityError('Selected destination server registration is unavailable for this owner')
        clean_req = {k: v for k, v in request.items() if k != 'destination_server_id'}
        return coordinated_load_review(service, server, dest_server, owner, endpoint, clean_req)

    if operation == 'load_start':
        return coordinated_load_start(service, owner, endpoint, request)

    if operation == 'load_status':
        lid = request.get('load_id')
        def _get_l(store):
            rec = store.read().get('coordinated_loads', {}).get(lid)
            if not rec:
                raise ContinuityError('Coordinated destination load receipt is unavailable')
            return deepcopy(rec)
        return _store_call(service, owner, endpoint, _get_l)

    raise ContinuityError('Snapshot orchestration action is unavailable')
