"""Original-session native administration for PostgreSQL temporary and uncommitted objects (PG-AUDIT-RETAINEDADMIN-01).

Preserves independent committed-object administration as the default while adding
explicit `session_id`-bound administration on the caller's original backend:
- Never opens a new connection or silently reconnects a broken session
- Never commits or rolls back an enclosing caller transaction (`INTRANS` uses a `SAVEPOINT`)
- Refuses `autocommit`-only commands (`VACUUM`, `CHECKPOINT`, `ALTER SYSTEM`, `COMMIT PREPARED`)
  inside an active caller transaction
- Verifies original `pg_backend_pid()`, `current_user`, and database OID at both plan and apply
"""
from __future__ import annotations

import copy
import uuid

from psycopg import Cursor, sql
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from .execution import control as native_control


def observe_retained_session(provider, session_id: str, route: dict, compiled: dict) -> dict:
    from .provider import PostgreSQLProviderError, PostgreSQLStatementRejected

    state = provider._sessions.get(session_id)
    if state is None or state.uncertain or not state.attached:
        raise PostgreSQLProviderError('Retained PostgreSQL session is unavailable or uncertain; do not reconnect')
    if state.server_id != route.get('server_id') or (
        route.get('database_id') is not None and state.database_id not in (None, route.get('database_id'))
    ):
        raise PostgreSQLProviderError('Retained PostgreSQL session belongs to a different server or database')
    conn = state.connection.conn
    if conn is None or conn.closed or conn.broken:
        state.uncertain = True
        raise PostgreSQLProviderError('Retained PostgreSQL backend connection is closed; will not reconnect')
    tx_status = conn.info.transaction_status
    if tx_status not in {TransactionStatus.IDLE, TransactionStatus.INTRANS}:
        raise PostgreSQLStatementRejected(
            'Retained PostgreSQL session has an aborted or failed transaction; resolve it before planning'
        )
    if compiled.get('autocommit') and tx_status == TransactionStatus.INTRANS:
        raise PostgreSQLStatementRejected(
            'Nontransactional PostgreSQL command cannot run inside an active retained-session transaction without committing caller work'
        )
    provider._check_admin_version(conn, compiled)

    sp = sql.Identifier('sr_ret_plan_' + uuid.uuid4().hex[:12])
    owned = tx_status == TransactionStatus.IDLE
    try:
        with Cursor(conn, row_factory=tuple_row) as cur:
            cur.execute('BEGIN READ ONLY' if owned else sql.SQL('SAVEPOINT {}').format(sp))
            cur.execute(
                'SELECT pg_catalog.pg_backend_pid(), current_user, '
                '(SELECT oid FROM pg_catalog.pg_database WHERE datname = current_database()), '
                'pg_catalog.pg_my_temp_schema()::oid'
            )
            pid, user, dboid, temp_oid = cur.fetchone()
    finally:
        if owned:
            conn.rollback()
        else:
            with Cursor(conn, row_factory=tuple_row) as cur:
                cur.execute(sql.SQL('ROLLBACK TO SAVEPOINT {}').format(sp))
                cur.execute(sql.SQL('RELEASE SAVEPOINT {}').format(sp))

    if route.get('database_id') is not None and dboid != route['database_id']:
        raise PostgreSQLProviderError('Retained session database OID disagrees with requested route')

    return {
        'session_id': session_id,
        'backend_pid': int(pid),
        'effective_user': str(user),
        'database_oid': int(dboid),
        'temp_schema_oid': int(temp_oid),
        'planned_transaction_status': int(tx_status),
    }


def apply_on_retained_session(provider, payload: dict, compiled: dict) -> dict:
    from .provider import PostgreSQLProviderError, PostgreSQLStatementRejected, _rejection

    binding = payload['retained_session_binding']
    session_id = binding['session_id']
    state = provider._sessions.get(session_id)
    if state is None or state.uncertain or not state.attached:
        raise PostgreSQLProviderError('Retained PostgreSQL session is unavailable or uncertain; do not replay')
    with state.lock:
        conn = state.connection.conn
        if conn is None or conn.closed or conn.broken:
            state.uncertain = True
            raise PostgreSQLProviderError('Retained PostgreSQL backend connection was lost; do not reconnect or replay')
        provider._check_admin_version(conn, compiled)
        orig_tx = conn.info.transaction_status
        if orig_tx not in {TransactionStatus.IDLE, TransactionStatus.INTRANS}:
            raise PostgreSQLStatementRejected(
                'Retained PostgreSQL session has an aborted transaction; roll back first'
            )
        autocommit_stmt = compiled.get('autocommit') is True
        if autocommit_stmt and orig_tx == TransactionStatus.INTRANS:
            raise PostgreSQLStatementRejected(
                'Nontransactional PostgreSQL command cannot run inside an active retained-session transaction'
            )

        owned_tx = (orig_tx == TransactionStatus.IDLE) and not autocommit_stmt
        use_savepoint = orig_tx == TransactionStatus.INTRANS
        sp_name = 'sr_ret_apply_' + uuid.uuid4().hex[:12]
        sp_ident = sql.Identifier(sp_name)
        committing = False
        guard_started = False

        try:
            if autocommit_stmt:
                if getattr(conn, 'autocommit', None) is not True:
                    raise PostgreSQLProviderError('Retained session must have autocommit enabled for this command')
            elif owned_tx:
                ok, _ = native_control(conn, 'BEGIN READ ONLY' if compiled['read_only'] else 'BEGIN')
                if not ok:
                    raise PostgreSQLProviderError('Retained-session transaction could not start')
                guard_started = True
                native_control(conn, 'SET LOCAL standard_conforming_strings = on')
            elif use_savepoint:
                with Cursor(conn, row_factory=tuple_row) as cur:
                    cur.execute(sql.SQL('SAVEPOINT {}').format(sp_ident))
                guard_started = True

            with Cursor(conn, row_factory=tuple_row) as cur:
                cur.execute(
                    'SELECT pg_catalog.pg_backend_pid(), current_user, '
                    '(SELECT oid FROM pg_catalog.pg_database WHERE datname = current_database())'
                )
                live_pid, live_user, live_dboid = cur.fetchone()
            if int(live_pid) != binding['backend_pid'] or int(live_dboid) != binding['database_oid']:
                raise PostgreSQLStatementRejected(
                    'Retained PostgreSQL session backend PID or database changed; review again on the current session'
                )

            returns_rows = compiled['read_only'] or compiled.get('returns_rows')
            statement = payload['statement']
            try:
                status, result = (
                    state.connection.execute_dict(statement, formatted_exception_msg=True)
                    if returns_rows
                    else state.connection.execute_void(statement, formatted_exception_msg=True)
                )
            except Exception as exc:
                if getattr(exc, 'diag', None) is None and not getattr(exc, 'sqlstate', None):
                    raise
                raise _rejection(exc) from None
            if not status:
                raise _rejection(result if isinstance(result, str) else '')

            observation = None
            if compiled.get('observation_statement'):
                obs_ok, observation = state.connection.execute_dict(compiled['observation_statement'])
                if not obs_ok:
                    raise PostgreSQLProviderError('Retained-session administrative readback failed')

            if autocommit_stmt:
                tx_outcome = 'committed'
            elif owned_tx:
                if compiled['read_only']:
                    conn.rollback()
                    tx_outcome = 'read_only_rolled_back'
                else:
                    committing = True
                    ok, cmd = native_control(conn, 'COMMIT')
                    if not ok or cmd != 'COMMIT':
                        raise PostgreSQLProviderError('Retained-session commit was not confirmed')
                    tx_outcome = 'committed'
                guard_started = False
            else:
                with Cursor(conn, row_factory=tuple_row) as cur:
                    if compiled['read_only']:
                        cur.execute(sql.SQL('ROLLBACK TO SAVEPOINT {}').format(sp_ident))
                    cur.execute(sql.SQL('RELEASE SAVEPOINT {}').format(sp_ident))
                guard_started = False
                if conn.info.transaction_status != TransactionStatus.INTRANS:
                    state.uncertain = True
                    raise PostgreSQLProviderError('Caller transaction state unexpectedly changed')
                tx_outcome = 'read_only_rolled_back' if compiled['read_only'] else 'savepoint_released_pending_caller_commit'

            resp = {
                'provider_owned': True,
                'native_outcome': 'observed',
                'transaction_outcome': tx_outcome,
                'independent_attachment': False,
                'retained_session_id': session_id,
                'backend_pid': int(live_pid),
                'caller_transaction_committed': False,
                'result': copy.deepcopy(result),
                'automatic_retry_performed': False,
                'common_finality_inference': False,
            }
            if observation is not None:
                resp['native_observation'] = copy.deepcopy(observation)
            return resp

        except Exception:
            if committing:
                state.uncertain = True
                raise PostgreSQLProviderError('Retained-session commit outcome is unknown; do not replay') from None
            if guard_started:
                try:
                    if owned_tx:
                        conn.rollback()
                    elif use_savepoint:
                        with Cursor(conn, row_factory=tuple_row) as cur:
                            cur.execute(sql.SQL('ROLLBACK TO SAVEPOINT {}').format(sp_ident))
                            cur.execute(sql.SQL('RELEASE SAVEPOINT {}').format(sp_ident))
                except Exception:
                    state.uncertain = True
                    raise PostgreSQLProviderError(
                        'Retained-session savepoint cleanup failed; close this session without replay'
                    ) from None
            raise
