"""Observe native editor identity and language settings without ending user work."""
import hashlib
import json
import uuid
from contextlib import contextmanager

from psycopg import Cursor, sql
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row


@contextmanager
def read_scope(state):
    connection = state.connection.conn
    original = connection.info.transaction_status
    if original not in {TransactionStatus.IDLE, TransactionStatus.INTRANS}:
        raise ValueError('Editor observation requires an idle or healthy pending transaction')
    owned = original == TransactionStatus.IDLE
    savepoint = sql.Identifier('sr_editor_' + uuid.uuid4().hex)
    attempted = False
    try:
        with Cursor(connection, row_factory=tuple_row) as cursor:
            attempted = True
            cursor.execute('BEGIN READ ONLY' if owned else sql.SQL('SAVEPOINT {}').format(savepoint))
        yield connection
    finally:
        if attempted:
            try:
                if owned:
                    connection.rollback()
                else:
                    with Cursor(connection, row_factory=tuple_row) as cursor:
                        cursor.execute(sql.SQL('ROLLBACK TO SAVEPOINT {}').format(savepoint))
                        cursor.execute(sql.SQL('RELEASE SAVEPOINT {}').format(savepoint))
                if (connection.closed or connection.broken or
                        connection.info.transaction_status != original):
                    raise RuntimeError('Native editor transaction state was not restored')
            except BaseException:
                state.uncertain = True
                raise RuntimeError('Editor observation cleanup is unconfirmed; close this session without replay') from None


def observe(state):
    connection = state.connection.conn
    original = connection.info.transaction_status
    context = {
        'engine': 'postgresql', 'version': connection.info.server_version,
        'authenticated_principal': connection.info.user,
        'session_principal': None, 'effective_principal': None,
        'active_role': None, 'selected_role': None,
        'search_path': None, 'resolved_search_path': None,
        'standard_conforming_strings': None, 'backslash_quote': None,
        'client_encoding': connection.info.parameter_status('client_encoding'),
        'server_encoding': connection.info.parameter_status('server_encoding'),
        'observation': {'available': False},
    }
    if original not in {TransactionStatus.IDLE, TransactionStatus.INTRANS}:
        context['observation']['reason'] = 'native-transaction-unavailable'
        if original == TransactionStatus.UNKNOWN:
            state.uncertain = True
    else:
        try:
            with read_scope(state), Cursor(connection, row_factory=tuple_row) as cursor:
                cursor.execute("SELECT CURRENT_USER, SESSION_USER, CURRENT_ROLE, "
                               "pg_catalog.current_setting('role'), "
                               "pg_catalog.current_setting('search_path'), "
                               "pg_catalog.current_schemas(true), "
                               "pg_catalog.current_setting('standard_conforming_strings'), "
                               "pg_catalog.current_setting('backslash_quote')")
                row = cursor.fetchone()
                if row is None or len(row) != 8:
                    raise ValueError('Native editor context is unavailable')
                context.update(zip(('effective_principal', 'session_principal',
                    'active_role', 'selected_role', 'search_path',
                    'resolved_search_path', 'standard_conforming_strings',
                    'backslash_quote'), row))
                context['observation'] = {'available': True}
        except Exception as error:
            if state.uncertain:
                raise
            context['observation'] = {'available': False,
                'reason': 'native-observation-failed',
                'sqlstate': getattr(error, 'sqlstate', None)}
    context['context_revision'] = hashlib.sha256(
        json.dumps(context, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return context
