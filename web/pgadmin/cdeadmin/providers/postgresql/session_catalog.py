"""Retained PostgreSQL catalog observation with caller-owned transaction guards."""
import uuid

from psycopg import Cursor, sql
from psycopg.rows import tuple_row
from psycopg.pq import TransactionStatus

from .catalog_capture import capture


def observe(state, *, include_system=False):
    connection = state.connection.conn
    original = connection.info.transaction_status
    if original not in {TransactionStatus.IDLE, TransactionStatus.INTRANS}:
        raise ValueError('Session catalog requires an idle or healthy pending transaction; resolve the existing transaction first')
    owned = original == TransactionStatus.IDLE
    savepoint = sql.Identifier('sr_catalog_' + uuid.uuid4().hex)
    guard_attempted = False
    try:
        with Cursor(connection, row_factory=tuple_row) as cursor:
            guard_attempted = True
            cursor.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY' if owned else
                           sql.SQL('SAVEPOINT {}').format(savepoint))
            cursor.execute('SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database()')
            oid = cursor.fetchone()[0]
            if state.database_id is not None and oid != state.database_id:
                raise ValueError('Selected database identity changed')
        result = capture(connection, oid, include_system=include_system,
                         _in_transaction=True, session_scope=True)
    finally:
        if guard_attempted:
            try:
                if owned:
                    connection.rollback()
                else:
                    with Cursor(connection, row_factory=tuple_row) as cursor:
                        # Roll back even after success: SET LOCAL must not leak
                        # into the user's enclosing transaction.
                        cursor.execute(sql.SQL('ROLLBACK TO SAVEPOINT {}').format(savepoint))
                        cursor.execute(sql.SQL('RELEASE SAVEPOINT {}').format(savepoint))
                if connection.closed or connection.broken or connection.info.transaction_status != original:
                    raise RuntimeError('Session catalog guard did not restore the native transaction state')
            except BaseException:
                state.uncertain = True
                raise RuntimeError('Session catalog cleanup is unconfirmed; close this session without replay') from None
    result.update(observation_scope='retained-session',
                  transaction_preserved=True, original_transaction_status=int(original))
    return result
