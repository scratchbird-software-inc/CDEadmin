"""Reviewed typed DDN imports on independent PostgreSQL/DuckDB/SQLite sessions."""
import base64
from contextlib import contextmanager
import hashlib
import json
import math
import os
import re
import uuid

from .mysql_data_import import read, MySQLDataApplications, plan_digest
from .firebird_schema_plan import digest
from ..providers.native_data_layout import inspect_relation, quote

ENGINES = {'postgresql', 'duckdb', 'sqlite'}


@contextmanager
def connection(provider, route, engine, *, writing=False):
    opened = native = None
    try:
        if engine == 'postgresql':
            opened = provider.open_session({'route': route})
            state = provider._sessions[opened['session_id']]
            provider._ensure_native_connection(state)
            native = state.connection.conn
            if int(native.info.transaction_status) != 0:
                raise ValueError('Data import requires its own idle PostgreSQL attachment')
            native.execute('BEGIN ISOLATION LEVEL REPEATABLE READ' + ('' if writing else ' READ ONLY'))
            for setting in ("statement_timeout='30s'", "lock_timeout='2s'", "search_path=pg_catalog",
                            "standard_conforming_strings=on", "DateStyle='ISO, YMD'", "IntervalStyle=postgres", "TimeZone=UTC", "bytea_output=hex", 'extra_float_digits=3'):
                native.execute('SET LOCAL ' + setting)
        else:
            from ..providers.embedded_route import contained_database
            filename = contained_database(route)
            if filename == ':memory:' or not os.path.isfile(filename):
                raise ValueError('Select an existing registered native database file')
            native = provider.client._connect({'route': route})
            native.execute('BEGIN IMMEDIATE' if engine == 'sqlite' and writing else 'BEGIN')
        yield native
    finally:
        if native is not None:
            if engine == 'postgresql': provider.close_session(opened)
            else: provider.client._discard_failed_session(native)


def sqlite_binding(value):
    if value is None or isinstance(value, str) or type(value) is int and abs(value) < 2**53 or type(value) is bool:
        return '?', value
    if isinstance(value, dict):
        encoding = value.get('encoding')
        if encoding == 'integer' and set(value) == {'encoding', 'data'}:
            data = value['data']
            if isinstance(data, str) and re.fullmatch(r'-?(0|[1-9][0-9]*)', data) and -(2**63) <= int(data) < 2**63:
                return '?', int(data)
        if encoding == 'float64' and set(value) == {'encoding', 'data'}:
            data = value['data']
            if isinstance(data, str) and re.fullmatch(r'-?(?:inf|(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:e[+-]?[0-9]+)?)', data):
                result = float(data)
                if not math.isnan(result): return '?', result
        if encoding == 'base64' and not set(value) - {'encoding', 'data', 'byte_length', 'native_storage_class'}:
            data = base64.b64decode(value.get('data', ''), validate=True)
            if type(value.get('byte_length')) is not int or len(data) != value['byte_length']:
                raise ValueError('Native binary byte length differs')
            if value.get('native_storage_class') not in {None, 'text'}:
                raise ValueError('Unknown SQLite storage class')
            return 'CAST(? AS TEXT)' if value.get('native_storage_class') == 'text' else '?', data
    raise ValueError('SQLite value is not an exact native storage value')


def postgres_binding(value, column):
    from ..providers.postgresql.execution import value as encode
    if value is None or isinstance(value, str): return '%s::' + column['native_type'], value
    if isinstance(value, dict) and set(value) == {'encoding', 'data', 'byte_length', 'native_encoding'} and value['native_encoding'] == 'SQL_ASCII':
        raw = base64.b64decode(value['data'], validate=True)
        if encode(raw, 'ascii') == value:
            return "convert_from(%s,'SQL_ASCII')::" + column['native_type'], raw
    raise ValueError('A PostgreSQL text-protocol value or NULL is required')


def duckdb_table(native, layout, chunks, descriptor, expected):
    import pyarrow as pa
    from ..providers.duckdb.values import scalar
    if (not isinstance(descriptor, dict) or descriptor.get('format') != 'arrow-ipc@1' or
            not isinstance(chunks, list) or not 1 <= len(chunks) <= 4 or descriptor.get('chunks') != len(chunks)):
        raise ValueError('An exact DuckDB Arrow type payload is required')
    raw = b''.join(base64.b64decode(part['data'], validate=True) for part in chunks)
    if not 1 <= len(raw) <= 4 * 1024 * 1024 or descriptor.get('byte_length') != len(raw) or descriptor.get('sha256') != hashlib.sha256(raw).hexdigest():
        raise ValueError('Native DuckDB payload fingerprint differs')
    with pa.ipc.open_stream(pa.BufferReader(raw)) as reader:
        table = reader.read_all()
    names = [column['native_name'] for column in layout['native_columns']]
    if table.num_rows != len(expected) or table.num_columns != len(names) or table.column_names != names:
        raise ValueError('Native DuckDB payload layout differs')
    alias = '__scratchrobin_import_' + uuid.uuid4().hex
    native.register(alias, table)
    try:
        # The installed native engine interprets its Arrow extension metadata.
        # Re-export after exact native casts to prove the hidden representation
        # agrees with every displayed positional value before reviewing it.
        query = 'SELECT ' + ','.join('CAST(' + quote(column['native_name']) + ' AS ' + column['native_type'] + ') AS ' + quote(column['native_name'])
            for column in layout['native_columns']) + ' FROM ' + quote(alias)
        native.execute(query)
        rows = []
        with native.to_arrow_reader(128) as reader:
            for batch in reader:
                rows.extend([scalar(column[index]) for column in batch.columns] for index in range(batch.num_rows))
        if rows != expected: raise ValueError('Displayed DuckDB values differ from the native type payload')
    finally: native.unregister(alias)
    return table


def preview(provider, route, engine, source, resource_id, *, endpoint_id, target_id, node='node'):
    if engine not in ENGINES: raise ValueError('Invalid native data engine')
    provider.permissions.require('data_read', 'resource')
    provider.permissions.require('data_write', 'resource')
    metadata, rows = read(source, node, engine=engine)
    with connection(provider, route, engine) as native:
        layout = inspect_relation(native, engine, resource_id, route)
        if layout['kind'] not in {'table', 'r', 'p'}:
            raise ValueError('Select a writable native table destination')
        captured = metadata['acquisition']['native_columns']
        names = [column['native_name'] for column in layout['native_columns']]
        if (len(captured) != len(names) or names != [column.get('native_name') for column in captured] or
                names != [column.get('native_name') for column in metadata['schema']['columns']] or
                any(before.get('native_type') != after['native_type'] for before, after in zip(captured, layout['native_columns']))):
            raise ValueError('Native source and destination column names or exact types differ')
        writable = [index for index, column in enumerate(layout['native_columns']) if not column['generated']]
        if not writable: raise ValueError('The destination has no explicit writable columns')
        if engine == 'sqlite':
            for row in rows:
                for index in writable: sqlite_binding(row[index])
        elif engine == 'postgresql':
            for row in rows:
                for index in writable: postgres_binding(row[index], layout['native_columns'][index])
        else:
            duckdb_table(native, layout, metadata.get('native_payload'), metadata['acquisition'].get('native_payload'), rows)
        native.execute('ROLLBACK')
    values = {'values': rows, 'payload': metadata['native_payload']} if engine == 'duckdb' else rows
    plan = {'format': 'scratchrobin.' + engine + '.data-import-plan@1', 'engine_id': engine,
        'endpoint_id': endpoint_id, 'database_target_id': target_id, 'resource_id': resource_id,
        'layout': layout, 'columns': [names[index] for index in writable], 'writable_positions': writable,
        'rows': values, 'row_count': len(rows), 'ready_for_review': bool(rows),
        'source_sha256': hashlib.sha256(source.encode('utf8')).hexdigest(),
        'native_payload': metadata['acquisition'].get('native_payload'),
        'source_coverage': {'mode': metadata['acquisition'].get('mode'),
            'partial': bool(metadata['acquisition'].get('more_rows_observed') or metadata['acquisition'].get('truncated'))},
        'warnings': ['Import inserts and explicitly commits the reviewed rows on a separate native connection.',
            'Native constraints and triggers remain active. Identity allocation and external trigger effects can survive rollback.',
            'Generated columns are recomputed by the destination. No table is cleared or replaced.']}
    if engine == 'postgresql' and any(column['identity'] or str(column.get('default') or '').startswith('nextval(') for column in layout['native_columns']):
        plan['warnings'].append('Explicit PostgreSQL identity/serial values leave target sequences unchanged. Review their next value in the native sequence editor before generating new identities.')
    plan['execution_sha256'] = plan_digest(plan)
    return plan


class NativeDataApplications(MySQLDataApplications):
    def __init__(self, path, engine):
        if engine not in ENGINES: raise ValueError('Invalid native data receipt engine')
        super().__init__(path)
        self.format = 'scratchrobin.' + engine + '.data-import-plan@1'


def apply(provider, route, engine, record):
    plan = record['plan']
    if plan['engine_id'] != engine or plan['execution_sha256'] != plan_digest(plan):
        raise ValueError('Reviewed native data changed')
    provider.permissions.require('data_write', 'resource')
    provider.permissions.require('execute')
    dispatched = committed = False
    rows_completed = 0
    with connection(provider, route, engine, writing=True) as native:
        try:
            layout = inspect_relation(native, engine, plan['resource_id'], route)
            if digest(layout) != digest(plan['layout']):
                native.execute('ROLLBACK')
                return {'state': 'not_dispatched', 'reason': 'Native destination metadata changed', 'rows_completed': 0}
            target = '.'.join(map(quote, layout['path']))
            names = ','.join(map(quote, plan['columns']))
            columns = [layout['native_columns'][index] for index in plan['writable_positions']]
            if engine == 'duckdb':
                table = duckdb_table(native, layout, plan['rows']['payload'], plan['native_payload'], plan['rows']['values'])
                alias = '__scratchrobin_rows_' + uuid.uuid4().hex
                native.register(alias, table)
                try:
                    projected = ','.join('CAST(' + quote(column['native_name']) + ' AS ' + column['native_type'] + ')' for column in columns)
                    dispatched = True
                    inserted = native.execute('INSERT INTO ' + target + '(' + names + ') SELECT ' + projected + ' FROM ' + quote(alias)).fetchone()[0]
                    if inserted != plan['row_count']: raise ValueError('Native inserted row count differs')
                    rows_completed = inserted
                finally: native.unregister(alias)
            else:
                cursor = native.cursor()
                try:
                    for row in plan['rows']:
                        if engine == 'sqlite':
                            bound = [sqlite_binding(row[index]) for index in plan['writable_positions']]
                            placeholders, parameters = ','.join(item[0] for item in bound), [item[1] for item in bound]
                            overriding = ''
                        else:
                            bound = [postgres_binding(row[index], column) for index, column in zip(plan['writable_positions'], columns)]
                            placeholders, parameters = ','.join(item[0] for item in bound), [item[1] for item in bound]
                            overriding = ' OVERRIDING SYSTEM VALUE' if any(column['identity'] for column in columns) else ''
                        dispatched = True
                        cursor.execute('INSERT INTO ' + target + '(' + names + ')' + overriding + ' VALUES (' + placeholders + ')', parameters)
                        if cursor.rowcount != 1: raise ValueError('Native insert acknowledgement differs')
                        rows_completed += 1
                finally: cursor.close()
            # Mark before dispatch: a lost COMMIT reply cannot be reclassified
            # as a confirmed rollback, and this durable review is never replayed.
            committed = True
            native.execute('COMMIT')
            return {'state': 'native_commit_returned', 'rows_completed': rows_completed,
                'transaction_completed': True, 'native_version': layout['native_version'],
                'verification': 'Native insert counts and commit acknowledged; independent row identity verification remains separate'}
        except Exception as error:
            state = 'unknown_outcome'
            rollback = False
            if not committed:
                try:
                    native.execute('ROLLBACK'); rollback = True
                    state = 'native_rollback_returned' if dispatched else 'not_dispatched'
                except Exception: pass
            return {'state': state, 'rows_completed': rows_completed, 'rollback_returned': rollback,
                    'error_type': type(error).__name__, 'native_code': getattr(error, 'sqlstate', getattr(error, 'sqlite_errorcode', None))}
