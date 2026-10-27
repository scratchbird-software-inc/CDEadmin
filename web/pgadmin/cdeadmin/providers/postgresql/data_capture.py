"""Explicit, bounded relation data acquisition for portable static DDN views."""
import json
import re
import uuid
from datetime import datetime, timezone

from psycopg import Cursor, sql
from psycopg.rows import tuple_row

from .execution import value, control
from ...results.ddn_export import export_workspace
from ..native_data_layout import inspect_relation

MAX_ROWS = 6000
MAX_BYTES = 4 * 1024 * 1024
RELATION = re.compile(r'postgresql:pg_class:([1-9][0-9]{0,9})\Z')


def capture(provider, route, endpoint_id, resource_id, *, mode='sample', row_limit=100):
    match = RELATION.fullmatch(resource_id) if isinstance(resource_id, str) else None
    if (not match or int(match[1]) > 4294967295 or mode not in ('sample', 'full') or
            type(row_limit) is not int or not 1 <= row_limit <= MAX_ROWS or
            type(route.get('database_id')) is not int or not 1 <= route['database_id'] <= 4294967295):
        raise ValueError('Select an exact database/relation, sample or full mode, and a 1–6,000 row budget')
    provider.permissions.require('data_read', 'resource')
    provider.permissions.require('execute')
    oid = int(match[1])
    opened = connection = None
    try:
        opened = provider.open_session({'route': route})
        state = provider._sessions[opened['session_id']]
        with state.lock:
            provider._ensure_native_connection(state)
            connection = state.connection.conn
            if int(connection.info.transaction_status) != 0:
                raise ValueError('Data capture requires an independently owned idle attachment')
            connection.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            connection.execute("SET LOCAL statement_timeout = '15s'")
            connection.execute("SET LOCAL lock_timeout = '2s'")
            connection.execute('SET LOCAL standard_conforming_strings = on')
            connection.execute('SET LOCAL search_path = pg_catalog')
            connection.execute("SET LOCAL DateStyle = 'ISO, YMD'")
            connection.execute("SET LOCAL IntervalStyle = 'postgres'")
            connection.execute("SET LOCAL TimeZone = 'UTC'")
            connection.execute("SET LOCAL bytea_output = 'hex'")
            connection.execute('SET LOCAL extra_float_digits = 3')
            with Cursor(connection, row_factory=tuple_row) as cursor:
                cursor.execute('SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database()')
                if int(cursor.fetchone()[0]) != route['database_id']:
                    raise ValueError('Selected database identity changed')
                cursor.execute('''SELECT n.nspname,c.relname,c.relkind
                    FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                    WHERE c.oid=%s AND c.relkind IN ('r','p','v','m')''', (oid,))
                relation = cursor.fetchone()
                if relation is None:
                    raise ValueError('Selected relation is unavailable or has no admitted data capture')
                schema, name, kind = relation
                layout = inspect_relation(connection, 'postgresql', resource_id, route)
                qualified = sql.Identifier(schema, name)
                # DECLARE acquires the query's relation locks, including on a
                # materialized view (which LOCK TABLE does not support).
                cursor_name = sql.Identifier('scratchrobin_data_' + uuid.uuid4().hex)
                cursor.execute(sql.SQL('DECLARE {} NO SCROLL CURSOR FOR SELECT * FROM {}').format(cursor_name, qualified))
                cursor.execute('SELECT pg_catalog.to_regclass(%s)::oid', (qualified.as_string(connection),))
                if int(cursor.fetchone()[0]) != oid:
                    raise ValueError('Selected relation was replaced')
                rows, size, columns, exhausted = [], 0, None, False
                # One lookahead row proves whether the visible selection ended.
                while len(rows) <= row_limit:
                    count = min(128, row_limit + 1 - len(rows))
                    cursor.execute(sql.SQL('FETCH FORWARD {} FROM {}').format(sql.Literal(count), cursor_name), binary=False)
                    result = cursor.pgresult
                    if result.nfields > 256:
                        raise ValueError('DDN data capture supports at most 256 columns')
                    if columns is None:
                        columns = [{'name': result.fname(i).decode(connection.info.encoding),
                            'native_name': result.fname(i).decode(connection.info.encoding), 'native_type': layout['native_columns'][i]['native_type'],
                            'key': str(i), 'pos': i, 'type_code': result.ftype(i),
                            'format': 'postgresql-text', 'table_oid': result.ftable(i),
                            'table_column': result.ftablecol(i)} for i in range(result.nfields)]
                    for number in range(result.ntuples):
                        row = [value(result.get_value(number, i), connection.info.encoding) for i in range(result.nfields)]
                        size += len(json.dumps(row, ensure_ascii=False).encode('utf8'))
                        if size > MAX_BYTES:
                            raise ValueError('DDN data capture exceeds 4 MiB of encoded values; use a smaller selection')
                        rows.append(row)
                    if result.ntuples < count:
                        exhausted = True
                        break
                    if len(rows) > row_limit:
                        break
                cursor.execute(sql.SQL('CLOSE {}').format(cursor_name))
            truncated = len(rows) > row_limit
            rows = rows[:row_limit]
            acquisition = {'endpoint_id': endpoint_id, 'database_oid': route['database_id'],
                'resource_id': resource_id, 'schema': schema, 'name': name, 'relkind': kind,
                'mode': mode, 'row_limit': row_limit, 'rows': len(rows), 'truncated': truncated,
                'selection_complete': exhausted and not truncated, 'order': 'unspecified native scan order',
                'observed_at': datetime.now(timezone.utc).isoformat(),
                'consistency': 'repeatable-read/read-only',
                'text_settings': {'DateStyle': 'ISO, YMD', 'IntervalStyle': 'postgres',
                                  'TimeZone': 'UTC', 'bytea_output': 'hex', 'extra_float_digits': 3},
                'visibility': 'native SELECT privileges and row-security rules; attachment-visible rows only',
                'value_encoding': 'PostgreSQL text protocol with native type OIDs; NULL retained'}
            acquisition.update(engine_id='postgresql', native_version=layout['native_version'], native_columns=layout['native_columns'], native_layout=layout)
            metadata = {'schema': {'columns': columns or []}, 'complete': acquisition['selection_complete'],
                'acquisition': acquisition, 'export_coverage': acquisition,
                'value_encoding': acquisition['value_encoding'],
                'consistency': acquisition['consistency'], 'title': 'Selected PostgreSQL relation data'}
            status, command = control(connection, 'COMMIT')
            if not status or command != 'COMMIT':
                raise ValueError('Data capture transaction did not complete successfully')
            acquisition['transaction_completed'] = True
            snapshot = json.loads(export_workspace(metadata, rows))
            return {'snapshot': snapshot, 'coverage': acquisition,
                'views': [{'id': 'result_' + str(i), 'entry': filename, 'label': 'Data page ' + str(i)}
                          for i, filename in enumerate(snapshot['files'], 1)]}
    except Exception:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if opened is not None:
            provider.close_session(opened)
