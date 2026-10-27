"""Explicit MySQL relation reads on an independently owned read-only snapshot."""
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone

from .mysql_catalog import identifier, SYSTEM, _value
from .mysql_values import value, columns
from ...results.ddn_export import export_workspace

MAX_ROWS = 6000
MAX_BYTES = 4 * 1024 * 1024
LAYOUT_FIELDS = ('column_name', 'column_type', 'is_nullable', 'extra', 'generation_expression',
                 'character_set_name', 'collation_name', 'srs_id')


def native_layout(cursor, database, name):
    cursor.execute('SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,EXTRA,GENERATION_EXPRESSION,CHARACTER_SET_NAME,COLLATION_NAME,SRS_ID '
                   'FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION LIMIT 257', (database, name))
    return [{field: _value(value) for field, value in zip(LAYOUT_FIELDS, row)} for row in cursor.fetchall()]


def relation_address(database, resource_id):
    if not isinstance(resource_id, str) or not resource_id.startswith('mysql:'):
        raise ValueError('Select an exact native MySQL relation')
    try:
        parts = json.loads(resource_id[6:])
    except (ValueError, TypeError):
        raise ValueError('Invalid native MySQL relation identity') from None
    root = 'mysql:' + json.dumps([database, 'database', None, database], ensure_ascii=False, separators=(',', ':'))
    if (not isinstance(parts, list) or len(parts) != 4 or parts[0] != database or
            parts[1] not in {'table', 'view', 'materialized-view'} or parts[2] != root or
            not isinstance(parts[3], str) or not parts[3] or '\0' in parts[3] or
            resource_id != 'mysql:' + json.dumps(parts, ensure_ascii=False, separators=(',', ':')) or database in SYSTEM):
        raise ValueError('Relation does not belong to the selected user database')
    return parts[1], parts[3]


def capture(connection, database, resource_id, *, endpoint_id, target_id, mode='sample', row_limit=100):
    if type(row_limit) is not int or not 1 <= row_limit <= MAX_ROWS or mode not in {'sample', 'full'}:
        raise ValueError('Select sample/full mode and a 1–6,000 row budget')
    kind, name = relation_address(database, resource_id)
    if connection.in_transaction:
        raise ValueError('Data capture requires its own idle connection')
    connection.autocommit = True
    control = connection.cursor()
    stream = None
    begun = False
    started = time.monotonic()
    try:
        control.execute('SELECT DATABASE(), VERSION(), @@server_uuid')
        identity = control.fetchone()
        if (not identity or identity[0] != database or str(identity[1]).split('-')[0] != '9.7.0' or
                not isinstance(identity[2], str) or not identity[2]):
            raise ValueError('Native MySQL database/server/version identity changed')
        control.execute('SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        control.execute('SET SESSION max_execution_time=15000')
        control.execute('SET SESSION lock_wait_timeout=2')
        control.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
        begun = True
        control.execute('SELECT TABLE_TYPE, ENGINE FROM information_schema.TABLES '
                        'WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s', (database, name))
        relation = control.fetchone()
        if relation is None or control.fetchone() is not None or (
                kind == 'table' and relation[0] != 'BASE TABLE' or
                kind in {'view', 'materialized-view'} and relation[0] != 'VIEW'):
            raise ValueError('Native relation is unavailable or its kind changed')
        layout = native_layout(control, database, name)
        if not 1 <= len(layout) <= 256:
            raise ValueError('DDN data capture needs 1–256 visible native columns')
        control.execute('SELECT @@sql_mode')
        sql_mode = control.fetchone()[0]
        control.execute('SET SESSION time_zone=%s', ('+00:00',))
        stream = connection.cursor(raw=True, buffered=False)
        stream.execute('SELECT ' + ','.join(identifier(column['column_name']) for column in layout) +
            ' FROM ' + identifier(database) + '.' + identifier(name) + ' LIMIT %s', (row_limit + 1,))
        schema = {'columns': columns(stream)}
        if not schema['columns'] or len(schema['columns']) > 256:
            raise ValueError('DDN data capture needs 1–256 visible columns')
        description = stream.description
        records = []
        size = len(json.dumps({'schema': schema, 'native_columns': layout}, ensure_ascii=False).encode('utf8'))
        if size > MAX_BYTES:
            raise ValueError('Data capture column metadata exceeds 4 MiB')
        exceeded = False
        while True:
            page = stream.fetchmany(128)
            if not page:
                break
            for native in page:
                if time.monotonic() - started > 30:
                    raise ValueError('Data capture exceeded 30 seconds; no partial download is available')
                if len(records) >= row_limit:
                    exceeded = True
                    continue
                if len(native) != len(description):
                    raise ValueError('Native row shape changed during capture')
                row = [value(item, column, connection.python_charset) for item, column in zip(native, description)]
                size += len(json.dumps(row, ensure_ascii=False, allow_nan=False).encode('utf8'))
                if size > MAX_BYTES:
                    raise ValueError('Data capture exceeds 4 MiB; no partial download is available')
                records.append(row)
        if exceeded and mode == 'full':
            raise ValueError('Full data capture exceeds the row budget; no partial download is available')
        stream.close(); stream = None
        if native_layout(control, database, name) != layout:
            raise ValueError('Native column layout changed during data capture')
        connection.rollback(); begun = False
        consistent = kind == 'table' and relation[1] == 'InnoDB'
        acquisition = {'engine_id': 'mysql', 'endpoint_id': endpoint_id, 'database_target_id': target_id,
            'resource_id': resource_id, 'database': database, 'relation': name, 'kind': kind,
            'server_uuid': identity[2], 'native_version': identity[1], 'storage_engine': relation[1],
            'observed_at': datetime.now(timezone.utc).isoformat(), 'mode': mode, 'row_limit': row_limit,
            'rows': len(records), 'more_rows_observed': exceeded, 'ordering': 'unspecified native order',
            'transaction_completed': True, 'consistent_innodb_table_snapshot': consistent}
        acquisition.update(native_columns=layout, sql_mode=sql_mode, time_zone='+00:00', timestamp_transport='UTC session projection')
        metadata = {'result_id': str(uuid.uuid4()), 'execution_id': None, 'title': database + '.' + name,
            'schema': schema, 'complete': not exceeded, 'export_coverage': 'full relation' if not exceeded else 'bounded sample',
            'acquisition': acquisition, 'value_encoding': 'exact MySQL text-protocol positional JSON; binary uses base64',
            'consistency': 'InnoDB read-only repeatable-read consistent snapshot' if consistent else
                'read-only transaction; nontransactional storage or view dependencies have observational consistency'}
        encoded = export_workspace(metadata, records)
        snapshot = json.loads(encoded)
        return {'snapshot': snapshot, 'acquisition': acquisition, 'columns': schema['columns'],
            'views': [{'id': 'result_' + str(index), 'label': 'Data page ' + str(index), 'entry': filename}
                      for index, filename in enumerate(snapshot['files'], 1)],
            'sha256': hashlib.sha256(encoded).hexdigest(), 'filename': 'mysql-relation-data.ddn-workspace.json',
            'warnings': ([] if consistent else ['Nontransactional storage or view dependencies do not gain InnoDB snapshot guarantees.']) +
                        (['This is a bounded sample; more rows were observed.'] if exceeded else [])}
    finally:
        # The provider retires the attachment even if an unread-result error
        # prevents cursor/transaction cleanup. Never return a partial success.
        try:
            if stream is not None: stream.close()
        finally:
            try:
                if begun: connection.rollback()
            finally:
                control.close()
