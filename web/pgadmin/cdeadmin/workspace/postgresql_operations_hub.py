"""PostgreSQL GUI Parity Operations Hub: Activity/Locks, pg_stat_statements, LISTEN/NOTIFY, COPY, Search, Bulk Grants & Logical pg_dump/pg_restore."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid

import psycopg
from psycopg import Cursor, sql
from psycopg.rows import dict_row

from ..operations.fileio import exclusive_file_lock, private_directory
from ..operations.store import JsonOperationStore
from ..providers.postgresql.continuity import ContinuityError
from .postgresql_continuity_service import artifact_context, paths_for_app
from .postgresql_monitoring_host import PostgreSQLMonitoringHost

_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]{0,62}$')
_SHARED_RESET_TARGETS = frozenset({'archiver', 'bgwriter', 'checkpointer', 'io', 'recovery_prefetch', 'wal'})
_PUBSUB_LOCK = threading.Lock()
_PUBSUB_SESSIONS: dict[tuple[int, str, str], dict] = {}


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf8')
    ).hexdigest()


def _require_ident(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENT_RE.match(value.strip()):
        raise ContinuityError(f'Invalid {label} identifier')
    return value.strip()


def _ops_store_call(service, owner: int, endpoint: str, fn):
    store_obj = getattr(service.operation_bus, 'store', None)
    if not isinstance(store_obj, JsonOperationStore):
        raise ContinuityError('PostgreSQL operations hub requires durable application storage')
    base = Path(str(store_obj.path) + '.postgresql-ops') / str(owner) / endpoint
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(base)
    path = base / 'jobs.json'
    fd = os.open(str(path) + '.lock', os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with exclusive_file_lock(fd):
            return fn(JsonOperationStore(path))
    finally:
        os.close(fd)


def _sql_conn_params(service, server, database_target_id: str | None = None, dbname_override: str | None = None) -> dict:
    from pgadmin.cdeadmin.providers.postgresql.connection_target import database_oid
    from pgadmin.utils.driver.registry import DriverRegistry

    oid = database_oid(database_target_id) if database_target_id else None
    manager = DriverRegistry.get('psycopg3').connection_manager(server.id)
    connection = manager.connection(did=oid) if oid is not None else manager.connection()
    if not connection.connected():
        raise ContinuityError('Connect the selected PostgreSQL server or database first')
    info = connection.conn.info
    params: dict[str, object] = {
        'host': info.host or server.host,
        'port': int(info.port or server.port or 5432),
        'user': info.user or server.username,
        'dbname': dbname_override or info.dbname or server.maintenance_db or 'postgres',
    }
    if getattr(info, 'hostaddr', None):
        params['hostaddr'] = info.hostaddr
    pw = getattr(connection.conn.pgconn, 'password', None)
    if pw:
        params['password'] = pw.decode('utf8', errors='surrogateescape') if isinstance(pw, bytes) else str(pw)
    opts = info.get_parameters() if hasattr(info, 'get_parameters') else {}
    for k in ('sslmode', 'sslrootcert', 'sslcert', 'sslkey'):
        if opts.get(k):
            params[k] = opts[k]
    return params


def _save_review(service, owner: int, endpoint: str, kind: str, payload: dict) -> dict:
    job_id = str(uuid.uuid4())
    digest = _sha256_json({'kind': kind, 'payload': payload})
    rec = {
        'job_id': job_id,
        'kind': kind,
        'state': 'reviewed',
        'review_digest': digest,
        'payload': payload,
        'created_at': time.time(),
    }

    def _put(store):
        store.change(lambda doc: doc.setdefault('ops_jobs', {}).update({job_id: rec}))
        return rec

    return _ops_store_call(service, owner, endpoint, _put)


def _consume_review(service, owner: int, endpoint: str, kind: str, request: dict) -> tuple[str, dict]:
    job_id = str(request.get('job_id') or '').strip()
    digest = str(request.get('review_digest') or '').strip()
    if request.get('confirmed') is not True:
        raise ContinuityError('Explicit confirmation is required before executing a reviewed PostgreSQL operation')

    def _claim(store):
        doc = store.read()
        rec = (doc.get('ops_jobs') or {}).get(job_id)
        if not rec or rec.get('kind') != kind:
            raise ContinuityError('Reviewed PostgreSQL operation was not found')
        if rec.get('state') != 'reviewed':
            raise ContinuityError(f'Reviewed operation {job_id} was already consumed ({rec.get("state")}); no automatic replay')
        if rec.get('review_digest') != digest:
            raise ContinuityError('Review digest mismatch; prepare a fresh review')
        payload_out = dict(rec['payload'])

        def _mark(d):
            d['ops_jobs'][job_id]['state'] = 'executing'

        store.change(_mark)
        return payload_out

    return job_id, _ops_store_call(service, owner, endpoint, _claim)


def _complete_review(service, owner: int, endpoint: str, job_id: str, state: str, outcome: dict) -> dict:
    def _finish(store):
        now = time.time()

        def _upd(d):
            r = d['ops_jobs'][job_id]
            r['state'] = state
            r['completed_at'] = now
            r['outcome'] = outcome

        store.change(_upd)
        return dict(store.read()['ops_jobs'][job_id])

    return _ops_store_call(service, owner, endpoint, _finish)


def _logical_backup_dir(service, app, owner: int, endpoint: str, host_authorized: bool) -> Path:
    configured = app.config.get('POSTGRESQL_LOGICAL_BACKUP_DIR')
    if configured:
        if not host_authorized:
            raise ContinuityError('Host authorization is required to access custom PostgreSQL logical backup directories')
        p = Path(configured).resolve()
        p.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_directory(p)
        return p
    store_obj = getattr(service.operation_bus, 'store', None)
    if not isinstance(store_obj, JsonOperationStore):
        raise ContinuityError('PostgreSQL logical backup requires durable application storage')
    root = Path(str(store_obj.path) + '.postgresql-logical-backups') / str(owner) / str(endpoint)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(root)
    return root


def _find_pg_tool(app, tool_name: str) -> str:
    for cfg_key in ('CDEADMIN_POSTGRESQL_HOST_BINARY_PATH', 'CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH'):
        cfg_dir = app.config.get(cfg_key)
        if cfg_dir:
            cand = Path(cfg_dir) / tool_name
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
    try:
        paths = paths_for_app(app)
        if isinstance(paths, dict) and paths.get(tool_name):
            return str(paths[tool_name])
    except Exception:
        pass
    for ver in ('18', '17', '16', '15'):
        cand = Path(f'/usr/lib/postgresql/{ver}/bin/{tool_name}')
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    found = shutil.which(tool_name)
    if found:
        return found
    raise ContinuityError(f'Required PostgreSQL utility {tool_name!r} was not found on application host')


def action(service, server, operation: str, request: dict, *, host_authorized: bool = False) -> dict:
    from flask import current_app
    if not isinstance(request, dict):
        raise ContinuityError('A PostgreSQL operations request object is required')
    if not PostgreSQLMonitoringHost._native_registration(server):
        raise ContinuityError('Select a native PostgreSQL registration')

    owner = service._principal_id(server)
    endpoint = server.endpoint_profile.id
    permissions = service.endpoint_service.provider_registry.admitted_permissions(artifact_context(server))
    db_target = request.get('database_target_id') if isinstance(request.get('database_target_id'), str) else None

    # 1. Active Sessions & Locks + fenced cancel/terminate
    if operation == 'activity_locks':
        params = _sql_conn_params(service, server, database_target_id=db_target)
        with psycopg.connect(**params, autocommit=True) as conn:
            with Cursor(conn, row_factory=dict_row) as cur:
                ver = int(cur.execute('SHOW server_version_num').fetchone()['server_version_num'])
                sessions = list(cur.execute(
                    """
                    SELECT
                        a.pid::integer AS pid,
                        a.usename,
                        a.datname,
                        a.application_name,
                        a.client_addr::text AS client_addr,
                        a.backend_type,
                        a.state,
                        a.wait_event_type,
                        a.wait_event,
                        to_char(a.backend_start AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS backend_start_utc,
                        EXTRACT(EPOCH FROM (clock_timestamp() - a.xact_start))::numeric(12,2)::text AS xact_age_seconds,
                        EXTRACT(EPOCH FROM (clock_timestamp() - a.query_start))::numeric(12,2)::text AS query_age_seconds,
                        pg_catalog.pg_blocking_pids(a.pid)::integer[] AS blocking_pids,
                        LEFT(COALESCE(a.query, ''), 500) AS query_preview
                    FROM pg_catalog.pg_stat_activity a
                    WHERE a.pid <> pg_catalog.pg_backend_pid()
                    ORDER BY a.backend_start DESC NULLS LAST, a.pid ASC
                    LIMIT 200
                    """
                ).fetchall())
                locks = list(cur.execute(
                    """
                    SELECT
                        l.pid::integer AS pid,
                        l.locktype,
                        d.datname AS database,
                        n.nspname AS schema,
                        c.relname AS relation,
                        l.mode,
                        l.granted,
                        l.waitstart::text AS waitstart
                    FROM pg_catalog.pg_locks l
                    LEFT JOIN pg_catalog.pg_database d ON d.oid = l.database
                    LEFT JOIN pg_catalog.pg_class c ON c.oid = l.relation
                    LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                    WHERE l.pid <> pg_catalog.pg_backend_pid()
                    ORDER BY l.granted ASC, l.pid ASC
                    LIMIT 200
                    """
                ).fetchall())
        return {'server_version_num': ver, 'sessions': sessions, 'locks': locks}

    if operation == 'session_signal_review':
        if 'administer' not in permissions:
            raise ContinuityError('PostgreSQL session administration permission is unavailable')
        pid = request.get('pid')
        if type(pid) is not int or pid <= 0:
            raise ContinuityError('Target backend PID must be a positive integer')
        sig_kind = str(request.get('signal') or 'cancel').strip().lower()
        if sig_kind not in {'cancel', 'terminate'}:
            raise ContinuityError('Signal must be cancel or terminate')
        params = _sql_conn_params(service, server, database_target_id=db_target)
        with psycopg.connect(**params, autocommit=True) as conn:
            with Cursor(conn, row_factory=dict_row) as cur:
                row = cur.execute(
                    """
                    SELECT
                        pid::integer AS pid,
                        usename,
                        datname,
                        state,
                        to_char(backend_start AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS backend_start_utc
                    FROM pg_catalog.pg_stat_activity
                    WHERE pid = %s AND pid <> pg_catalog.pg_backend_pid()
                    """,
                    (pid,),
                ).fetchone()
        if not row:
            raise ContinuityError(f'Backend PID {pid} is no longer active')
        return _save_review(service, owner, endpoint, 'session_signal', {
            'pid': pid,
            'signal': sig_kind,
            'expected_backend_start_utc': row['backend_start_utc'],
            'expected_usename': row['usename'],
            'datname': row['datname'],
            'database_target_id': db_target,
        })

    if operation == 'session_signal_start':
        if 'administer' not in permissions:
            raise ContinuityError('PostgreSQL session administration permission is unavailable')
        job_id, payload = _consume_review(service, owner, endpoint, 'session_signal', request)
        params = _sql_conn_params(service, server, database_target_id=payload.get('database_target_id'))
        fn_sql = 'pg_catalog.pg_terminate_backend' if payload['signal'] == 'terminate' else 'pg_catalog.pg_cancel_backend'
        with psycopg.connect(**params, autocommit=True) as conn:
            with Cursor(conn, row_factory=dict_row) as cur:
                check = cur.execute(
                    f"""
                    SELECT
                        pid::integer AS pid,
                        {fn_sql}(pid) AS signalled
                    FROM pg_catalog.pg_stat_activity
                    WHERE pid = %s
                      AND to_char(backend_start AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') = %s
                      AND pid <> pg_catalog.pg_backend_pid()
                    """,
                    (payload['pid'], payload['expected_backend_start_utc']),
                ).fetchone()
        if not check:
            rec = _complete_review(service, owner, endpoint, job_id, 'stale_target_refused', {
                'signalled': False,
                'reason': 'Target backend exited or PID was recycled before signal dispatch',
            })
            raise ContinuityError(rec['outcome']['reason'])
        return _complete_review(service, owner, endpoint, job_id, 'completed', {
            'pid': payload['pid'],
            'signal': payload['signal'],
            'signalled': bool(check['signalled']),
        })

    # 2. pg_stat_statements explorer & statistics reset
    if operation == 'stat_statements':
        sort_by = str(request.get('sort_by') or 'total_exec_time').strip()
        if sort_by not in {'total_exec_time', 'mean_exec_time', 'calls', 'rows', 'shared_blks_read', 'wal_bytes'}:
            sort_by = 'total_exec_time'
        limit = min(max(int(request.get('limit') or 50), 1), 200)
        params = _sql_conn_params(service, server, database_target_id=db_target)
        with psycopg.connect(**params, autocommit=True) as conn:
            with Cursor(conn, row_factory=dict_row) as cur:
                ext = cur.execute(
                    "SELECT n.nspname AS ext_schema, e.extversion FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'pg_stat_statements'"
                ).fetchone()
                if not ext:
                    return {'installed': False, 'rows': []}
                q = sql.SQL(
                    """
                    SELECT
                        queryid::text AS queryid,
                        calls::bigint AS calls,
                        round(total_exec_time::numeric, 3)::text AS total_exec_time_ms,
                        round(mean_exec_time::numeric, 3)::text AS mean_exec_time_ms,
                        rows::bigint AS rows,
                        shared_blks_hit::bigint AS shared_blks_hit,
                        shared_blks_read::bigint AS shared_blks_read,
                        wal_bytes::text AS wal_bytes,
                        LEFT(query, 1000) AS query
                    FROM {}.pg_stat_statements
                    ORDER BY {} DESC NULLS LAST
                    LIMIT %s
                    """
                ).format(sql.Identifier(ext['ext_schema']), sql.Identifier(sort_by))
                try:
                    rows = list(cur.execute(q, (limit,)).fetchall())
                    for r in rows:
                        r['calls'] = int(r['calls'])
                        r['rows'] = int(r['rows'])
                        r['shared_blks_hit'] = int(r['shared_blks_hit'])
                        r['shared_blks_read'] = int(r['shared_blks_read'])
                    return {'installed': True, 'extversion': ext['extversion'], 'rows': rows}
                except psycopg.Error as exc:
                    return {'installed': True, 'extversion': ext['extversion'], 'preload_missing_or_denied': str(exc), 'rows': []}

    if operation == 'stats_reset_review':
        if 'administer' not in permissions:
            raise ContinuityError('PostgreSQL statistics reset requires administer permission')
        target = str(request.get('target') or 'pg_stat_statements').strip()
        if target != 'pg_stat_statements' and target not in _SHARED_RESET_TARGETS:
            raise ContinuityError('Select pg_stat_statements or a valid pg_stat_reset_shared target')
        return _save_review(service, owner, endpoint, 'stats_reset', {
            'target': target,
            'database_target_id': db_target,
        })

    if operation == 'stats_reset_start':
        if 'administer' not in permissions:
            raise ContinuityError('PostgreSQL statistics reset requires administer permission')
        job_id, payload = _consume_review(service, owner, endpoint, 'stats_reset', request)
        params = _sql_conn_params(service, server, database_target_id=payload.get('database_target_id'))
        with psycopg.connect(**params, autocommit=True) as conn:
            with Cursor(conn, row_factory=dict_row) as cur:
                if payload['target'] == 'pg_stat_statements':
                    ext = cur.execute(
                        "SELECT n.nspname AS ext_schema FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'pg_stat_statements'"
                    ).fetchone()
                    if not ext:
                        raise ContinuityError('pg_stat_statements is not installed in this database')
                    cur.execute(sql.SQL('SELECT {}.pg_stat_statements_reset()').format(sql.Identifier(ext['ext_schema'])))
                else:
                    cur.execute('SELECT pg_catalog.pg_stat_reset_shared(%s)', (payload['target'],))
        return _complete_review(service, owner, endpoint, job_id, 'completed', {'reset_target': payload['target']})

    # 3. Live LISTEN / NOTIFY Channel Subscriber & Publisher
    if operation in {'pubsub_subscribe', 'pubsub_poll', 'pubsub_unsubscribe', 'pubsub_notify'}:
        if 'execute' not in permissions:
            raise ContinuityError('Execute permission is required for LISTEN / NOTIFY')
        params = _sql_conn_params(service, server, database_target_id=db_target)
        key = (owner, endpoint, str(params['dbname']))

        if operation == 'pubsub_notify':
            channel = _require_ident(request.get('channel'), 'channel')
            payload_text = str(request.get('payload') or '')
            if len(payload_text.encode('utf8')) > 7999:
                raise ContinuityError('PostgreSQL NOTIFY payload cannot exceed 7999 UTF-8 bytes')
            with psycopg.connect(**params, autocommit=True) as conn:
                sender_pid = int(conn.info.backend_pid)
                conn.execute('SELECT pg_catalog.pg_notify(%s, %s)', (channel, payload_text))
            return {'sent': True, 'channel': channel, 'sender_pid': sender_pid}

        with _PUBSUB_LOCK:
            entry = _PUBSUB_SESSIONS.get(key)
            if entry is not None and entry['conn'].closed:
                _PUBSUB_SESSIONS.pop(key, None)
                entry = None

            if operation == 'pubsub_unsubscribe':
                ch = request.get('channel')
                if entry is None:
                    return {'subscribed_channels': [], 'notifications': []}
                if ch:
                    channel = _require_ident(ch, 'channel')
                    entry['conn'].execute(sql.SQL('UNLISTEN {}').format(sql.Identifier(channel)))
                    entry['channels'].discard(channel)
                    if not entry['channels']:
                        entry['conn'].close()
                        _PUBSUB_SESSIONS.pop(key, None)
                        return {'subscribed_channels': [], 'notifications': []}
                else:
                    entry['conn'].close()
                    _PUBSUB_SESSIONS.pop(key, None)
                    return {'subscribed_channels': [], 'notifications': []}

            if operation == 'pubsub_subscribe':
                channel = _require_ident(request.get('channel'), 'channel')
                if entry is None:
                    conn = psycopg.connect(**params, autocommit=True)
                    entry = {
                        'conn': conn,
                        'channels': set(),
                        'buffer': [],
                        'backend_pid': int(conn.info.backend_pid),
                    }
                    _PUBSUB_SESSIONS[key] = entry
                if len(entry['channels']) >= 8 and channel not in entry['channels']:
                    raise ContinuityError('At most 8 concurrent LISTEN channels per workspace')
                entry['conn'].execute(sql.SQL('LISTEN {}').format(sql.Identifier(channel)))
                entry['channels'].add(channel)

            if entry is None:
                return {'subscribed_channels': [], 'backend_pid': None, 'notifications': []}

            for n in entry['conn'].notifies(timeout=0.05):
                entry['buffer'].append({
                    'pid': int(n.pid),
                    'channel': n.channel,
                    'payload': n.payload,
                    'received_at': time.time(),
                })
            entry['buffer'] = entry['buffer'][-100:]
            return {
                'backend_pid': entry['backend_pid'],
                'subscribed_channels': sorted(entry['channels']),
                'notifications': list(reversed(entry['buffer'])),
            }

    # 4. Fast Native Catalog Object Search
    if operation == 'catalog_search':
        pattern = str(request.get('query') or '').strip()
        schema_filter = str(request.get('schema') or '').strip()
        kind_filter = str(request.get('kind') or '').strip()
        like_pat = f'%{pattern}%' if pattern else '%'
        params = _sql_conn_params(service, server, database_target_id=db_target)
        with psycopg.connect(**params, autocommit=True) as conn:
            with Cursor(conn, row_factory=dict_row) as cur:
                rows = list(cur.execute(
                    """
                    WITH items AS (
                        SELECT
                            n.nspname AS schema,
                            c.relname AS name,
                            CASE c.relkind
                                WHEN 'r' THEN 'table'
                                WHEN 'p' THEN 'partitioned-table'
                                WHEN 'v' THEN 'view'
                                WHEN 'm' THEN 'materialized-view'
                                WHEN 'i' THEN 'index'
                                WHEN 'I' THEN 'partitioned-index'
                                WHEN 'S' THEN 'sequence'
                                WHEN 'f' THEN 'foreign-table'
                                ELSE c.relkind::text
                            END AS kind,
                            pg_catalog.pg_get_userbyid(c.relowner) AS owner,
                            COALESCE(pg_catalog.obj_description(c.oid, 'pg_class'), '') AS comment
                        FROM pg_catalog.pg_class c
                        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                          AND n.nspname NOT LIKE 'pg_toast%%'
                        UNION ALL
                        SELECT
                            n.nspname AS schema,
                            p.proname || '(' || pg_catalog.pg_get_function_identity_arguments(p.oid) || ')' AS name,
                            CASE p.prokind WHEN 'p' THEN 'procedure' WHEN 'a' THEN 'aggregate' ELSE 'function' END AS kind,
                            pg_catalog.pg_get_userbyid(p.proowner) AS owner,
                            COALESCE(pg_catalog.obj_description(p.oid, 'pg_proc'), '') AS comment
                        FROM pg_catalog.pg_proc p
                        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                    )
                    SELECT schema, name, kind, owner, comment
                    FROM items
                    WHERE (name ILIKE %s OR schema ILIKE %s OR comment ILIKE %s)
                      AND (%s = '' OR schema = %s)
                      AND (%s = '' OR kind = %s)
                    ORDER BY schema ASC, kind ASC, name ASC
                    LIMIT 200
                    """,
                    (like_pat, like_pat, like_pat, schema_filter, schema_filter, kind_filter, kind_filter),
                ).fetchall())
        return {'results': rows, 'count': len(rows)}

    # 5. Client-Streamed COPY Export & Reviewed COPY Import
    if operation == 'copy_export':
        if 'data_read' not in permissions:
            raise ContinuityError('Data read permission is required for COPY export')
        schema_name = _require_ident(request.get('schema') or 'public', 'schema')
        table_name = _require_ident(request.get('table'), 'table')
        fmt = str(request.get('format') or 'csv').strip().lower()
        if fmt not in {'csv', 'text'}:
            raise ContinuityError('COPY export format must be csv or text')
        header = bool(request.get('header', True))
        params = _sql_conn_params(service, server, database_target_id=db_target)
        buf = bytearray()
        with psycopg.connect(**params, autocommit=True) as conn:
            opts = "FORMAT csv, HEADER true" if (fmt == 'csv' and header) else ("FORMAT csv" if fmt == 'csv' else "FORMAT text")
            stmt = sql.SQL(f'COPY {{}}.{{}} TO STDOUT WITH ({opts})').format(
                sql.Identifier(schema_name), sql.Identifier(table_name)
            )
            with conn.cursor() as cur:
                with cur.copy(stmt) as cp:
                    for chunk in cp:
                        buf.extend(bytes(chunk))
                        if len(buf) > 4 * 1024 * 1024:
                            raise ContinuityError('Interactive COPY preview exceeds 4 MiB; use pg_dump for bulk archives')
        text_out = bytes(buf).decode('utf8', errors='replace')
        line_count = max(0, len(text_out.splitlines()) - (1 if fmt == 'csv' and header and text_out else 0))
        return {
            'schema': schema_name,
            'table': table_name,
            'format': fmt,
            'header': header,
            'rows_exported': line_count,
            'sha256': hashlib.sha256(buf).hexdigest(),
            'data': text_out,
        }

    if operation == 'copy_import_review':
        if 'data_write' not in permissions:
            raise ContinuityError('Data write permission is required for COPY import')
        schema_name = _require_ident(request.get('schema') or 'public', 'schema')
        table_name = _require_ident(request.get('table'), 'table')
        csv_data = str(request.get('data') or '')
        if not csv_data.strip() or len(csv_data.encode('utf8')) > 4 * 1024 * 1024:
            raise ContinuityError('Provide non-empty CSV data up to 4 MiB')
        header = bool(request.get('header', True))
        raw_cols = request.get('columns') or []
        cols = [_require_ident(c, 'column') for c in raw_cols] if isinstance(raw_cols, list) and raw_cols else []
        reader = list(csv.reader(io.StringIO(csv_data)))
        row_estimate = max(0, len(reader) - (1 if header else 0))
        return _save_review(service, owner, endpoint, 'copy_import', {
            'schema': schema_name,
            'table': table_name,
            'columns': cols,
            'header': header,
            'row_estimate': row_estimate,
            'data_sha256': hashlib.sha256(csv_data.encode('utf8')).hexdigest(),
            'data': csv_data,
            'database_target_id': db_target,
        })

    if operation == 'copy_import_start':
        if 'data_write' not in permissions:
            raise ContinuityError('Data write permission is required for COPY import')
        job_id, payload = _consume_review(service, owner, endpoint, 'copy_import', request)
        params = _sql_conn_params(service, server, database_target_id=payload.get('database_target_id'))
        opts = 'FORMAT csv, HEADER true' if payload['header'] else 'FORMAT csv'
        col_sql = (
            sql.SQL(' (') + sql.SQL(', ').join(sql.Identifier(c) for c in payload['columns']) + sql.SQL(')')
            if payload['columns']
            else sql.SQL('')
        )
        stmt = sql.SQL(f'COPY {{}}.{{}}{{}} FROM STDIN WITH ({opts})').format(
            sql.Identifier(payload['schema']),
            sql.Identifier(payload['table']),
            col_sql,
        )
        with psycopg.connect(**params, autocommit=False) as conn:
            with conn.cursor() as cur:
                with cur.copy(stmt) as cp:
                    cp.write(payload['data'].encode('utf8'))
                inserted = int(cur.rowcount) if cur.rowcount is not None and cur.rowcount >= 0 else payload['row_estimate']
            conn.commit()
        return _complete_review(service, owner, endpoint, job_id, 'completed', {
            'schema': payload['schema'],
            'table': payload['table'],
            'rows_imported': inserted,
            'data_sha256': payload['data_sha256'],
        })

    # 6. Bulk Privilege Grant / Revoke Wizard
    if operation == 'bulk_grant_review':
        if 'administer' not in permissions:
            raise ContinuityError('Administer permission is required for bulk privilege changes')
        mode = str(request.get('mode') or 'GRANT').strip().upper()
        if mode not in {'GRANT', 'REVOKE'}:
            raise ContinuityError('Mode must be GRANT or REVOKE')
        grantee = _require_ident(request.get('grantee'), 'grantee')
        obj_kind = str(request.get('object_kind') or 'TABLE').strip().upper()
        if obj_kind not in {'TABLE', 'SEQUENCE', 'SCHEMA'}:
            raise ContinuityError('Object kind must be TABLE, SEQUENCE or SCHEMA')
        allowed_privs = {
            'TABLE': {'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER', 'MAINTAIN', 'ALL'},
            'SEQUENCE': {'USAGE', 'SELECT', 'UPDATE', 'ALL'},
            'SCHEMA': {'USAGE', 'CREATE', 'ALL'},
        }[obj_kind]
        privs = [str(p).strip().upper() for p in (request.get('privileges') or []) if str(p).strip()]
        if not privs or any(p not in allowed_privs for p in privs):
            raise ContinuityError(f'Select valid {obj_kind} privileges')
        targets = request.get('targets') or []
        if not isinstance(targets, list) or not 1 <= len(targets) <= 100:
            raise ContinuityError('Select 1 to 100 target objects')
        stmts: list[str] = []
        for tgt in targets:
            if obj_kind == 'SCHEMA':
                ident = sql.Identifier(_require_ident(tgt, 'schema'))
                target_sql = sql.SQL('SCHEMA {}').format(ident)
            else:
                parts = str(tgt).split('.', 1)
                sc = _require_ident(parts[0] if len(parts) == 2 else 'public', 'schema')
                nm = _require_ident(parts[1] if len(parts) == 2 else parts[0], 'object')
                target_sql = sql.SQL('{} {}.{}').format(sql.SQL(obj_kind), sql.Identifier(sc), sql.Identifier(nm))
            priv_sql = sql.SQL('ALL PRIVILEGES') if 'ALL' in privs else sql.SQL(', ').join(sql.SQL(p) for p in privs)
            if mode == 'GRANT':
                tail = sql.SQL(' WITH GRANT OPTION') if request.get('with_grant_option') else sql.SQL('')
                q = sql.SQL('GRANT {} ON {} TO {}{}').format(priv_sql, target_sql, sql.Identifier(grantee), tail)
            else:
                tail = sql.SQL(' CASCADE') if request.get('cascade') else sql.SQL(' RESTRICT')
                q = sql.SQL('REVOKE {} ON {} FROM {}{}').format(priv_sql, target_sql, sql.Identifier(grantee), tail)
            with psycopg.connect(**_sql_conn_params(service, server, database_target_id=db_target), autocommit=True) as c:
                stmts.append(q.as_string(c))
        return _save_review(service, owner, endpoint, 'bulk_grant', {
            'mode': mode,
            'grantee': grantee,
            'object_kind': obj_kind,
            'statements': stmts,
            'database_target_id': db_target,
        })

    if operation == 'bulk_grant_start':
        if 'administer' not in permissions:
            raise ContinuityError('Administer permission is required for bulk privilege changes')
        job_id, payload = _consume_review(service, owner, endpoint, 'bulk_grant', request)
        params = _sql_conn_params(service, server, database_target_id=payload.get('database_target_id'))
        with psycopg.connect(**params, autocommit=False) as conn:
            with conn.cursor() as cur:
                for st in payload['statements']:
                    cur.execute(st)
            conn.commit()
        return _complete_review(service, owner, endpoint, job_id, 'completed', {
            'statements_executed': len(payload['statements']),
            'grantee': payload['grantee'],
            'mode': payload['mode'],
        })

    # 7. Native Logical Backup (pg_dump) & Restore (pg_restore / psql)
    if operation == 'logical_backup_catalog':
        bdir = _logical_backup_dir(service, current_app, owner, endpoint, host_authorized)
        archives = sorted(
            [
                {'filename': p.name, 'size_bytes': p.stat().st_size, 'modified_at': p.stat().st_mtime}
                for p in bdir.iterdir()
                if p.is_file() and not p.name.startswith('.')
            ],
            key=lambda x: x['modified_at'],
            reverse=True,
        )
        return {
            'backup_dir': str(bdir),
            'pg_dump': _find_pg_tool(current_app, 'pg_dump'),
            'pg_restore': _find_pg_tool(current_app, 'pg_restore'),
            'archives': archives[:50],
        }

    if operation == 'logical_backup_review':
        if 'backup_admin' not in permissions and 'administer' not in permissions:
            raise ContinuityError('Backup administration permission is required')
        task = str(request.get('task') or 'backup').strip().lower()
        if task not in {'backup', 'restore', 'toc'}:
            raise ContinuityError('Logical backup task must be backup, restore or toc')
        filename = str(request.get('filename') or '').strip()
        if not re.match(r'^[A-Za-z0-9._-]{1,120}$', filename) or '..' in filename:
            raise ContinuityError('Archive filename must contain only safe [A-Za-z0-9._-] characters')
        fmt = str(request.get('format') or 'custom').strip().lower()
        if fmt not in {'custom', 'plain', 'tar'}:
            raise ContinuityError('Format must be custom, plain or tar')
        schema_only = bool(request.get('schema_only', False))
        data_only = bool(request.get('data_only', False))
        if schema_only and data_only:
            raise ContinuityError('schema_only and data_only cannot both be enabled')
        clean_objs = bool(request.get('clean', False))
        schema_filter = _require_ident(request['schema'], 'schema') if request.get('schema') else None
        return _save_review(service, owner, endpoint, 'logical_backup', {
            'task': task,
            'filename': filename,
            'format': fmt,
            'schema_only': schema_only,
            'data_only': data_only,
            'clean': clean_objs,
            'schema': schema_filter,
            'database_target_id': db_target,
        })

    if operation == 'logical_backup_start':
        if 'backup_admin' not in permissions and 'administer' not in permissions:
            raise ContinuityError('Backup administration permission is required')
        job_id, payload = _consume_review(service, owner, endpoint, 'logical_backup', request)
        bdir = _logical_backup_dir(service, current_app, owner, endpoint, host_authorized)
        archive_path = (bdir / payload['filename']).resolve()
        if archive_path.parent != bdir:
            raise ContinuityError('Archive path escapes logical backup directory')
        params = _sql_conn_params(service, server, database_target_id=payload.get('database_target_id'))
        pw_file = bdir / f'.pgpass-{uuid.uuid4().hex}'
        env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LC_ALL': 'C'}
        try:
            if params.get('password'):
                fd = os.open(str(pw_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w', encoding='utf8') as fh:
                    fh.write(f"*:*:*:{params['user']}:{params['password']}\n")
                env['PGPASSFILE'] = str(pw_file)
            conn_args = ['-h', str(params['host']), '-p', str(params['port']), '-U', str(params['user']), '-w']
            if payload['task'] == 'backup':
                fmt_flag = {'custom': 'c', 'plain': 'p', 'tar': 't'}[payload['format']]
                cmd = [_find_pg_tool(current_app, 'pg_dump'), *conn_args, '-F', fmt_flag, '-f', str(archive_path)]
                if payload['schema_only']:
                    cmd.append('--schema-only')
                if payload['data_only']:
                    cmd.append('--data-only')
                if payload['clean']:
                    cmd.extend(['--clean', '--if-exists'])
                if payload['schema']:
                    cmd.extend(['-n', payload['schema']])
                cmd.append(str(params['dbname']))
            elif payload['task'] == 'toc':
                if not archive_path.is_file():
                    raise ContinuityError(f'Archive {payload["filename"]} does not exist')
                cmd = [_find_pg_tool(current_app, 'pg_restore'), '--list', str(archive_path)]
            else:
                if not archive_path.is_file():
                    raise ContinuityError(f'Archive {payload["filename"]} does not exist')
                if payload['format'] == 'plain':
                    cmd = [_find_pg_tool(current_app, 'psql'), *conn_args, '-v', 'ON_ERROR_STOP=1', '-d', str(params['dbname']), '-f', str(archive_path)]
                else:
                    cmd = [_find_pg_tool(current_app, 'pg_restore'), *conn_args, '-d', str(params['dbname'])]
                    if payload['clean']:
                        cmd.extend(['--clean', '--if-exists'])
                    if payload['schema_only']:
                        cmd.append('--schema-only')
                    if payload['data_only']:
                        cmd.append('--data-only')
                    if payload['schema']:
                        cmd.extend(['-n', payload['schema']])
                    cmd.append(str(archive_path))
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                _complete_review(service, owner, endpoint, job_id, 'failed', {
                    'returncode': proc.returncode,
                    'stderr': proc.stderr[-2000:],
                })
                raise ContinuityError(f'Logical {payload["task"]} failed: {proc.stderr.strip()[:400]}')
            return _complete_review(service, owner, endpoint, job_id, 'completed', {
                'task': payload['task'],
                'filename': payload['filename'],
                'size_bytes': archive_path.stat().st_size if archive_path.is_file() else 0,
                'stdout': proc.stdout[-4000:],
            })
        finally:
            if pw_file.exists():
                pw_file.unlink(missing_ok=True)

    raise ContinuityError(f'Unsupported PostgreSQL operations hub action: {operation!r}')
