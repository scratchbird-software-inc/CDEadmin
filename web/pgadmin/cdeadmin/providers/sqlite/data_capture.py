"""Bounded independent SQLite relation reads for public DDN data views."""

from datetime import datetime, timezone
import hashlib
import json
import os
import re
import time
import uuid

from ..embedded_route import contained_database
from .provider import _resource_id
from .values import value
from ...results.ddn_export import export_workspace
from pgadmin.cdeadmin.sdk import RelationalClientError

MAX_ROWS = 6000
MAX_BYTES = 4 * 1024 * 1024
MAX_SECONDS = 30
RELATIONS = {'table', 'view', 'virtual-table', 'fts-table'}


def relation_address(resource_id):
    if not isinstance(resource_id, str) or not resource_id.startswith('sqlite:'):
        raise ValueError('Select an exact native SQLite relation')
    try:
        parts = json.loads(resource_id[7:])
    except (ValueError, TypeError):
        raise ValueError('Invalid native SQLite relation identity') from None
    if (not isinstance(parts, list) or len(parts) != 3 or
            parts[0] not in RELATIONS or
            any(not isinstance(part, str) or not part or '\0' in part
                for part in parts[1:]) or
            resource_id != _resource_id(parts[0], [parts[1]], parts[2])):
        raise ValueError('Relation identity is not an exact SQLite table or view')
    return parts


def _identifier(value):
    return '"' + value.replace('"', '""') + '"'


def capture(provider, route, resource_id, *, endpoint_id, target_id,
            mode='sample', row_limit=100):
    if (type(row_limit) is not int or not 1 <= row_limit <= MAX_ROWS or
            mode not in {'sample', 'full'}):
        raise ValueError('Select sample/full mode and a 1–6,000 row budget')
    kind, schema, name = relation_address(resource_id)
    provider.permissions.require('data_read', 'resource')
    provider.permissions.require('execute')
    path = contained_database(route)
    if path == ':memory:':
        raise RelationalClientError(
            'Independent :memory: relation capture observes a different database')
    if not os.path.isfile(path):
        raise RelationalClientError('Registered SQLite database file does not exist')
    connection = provider.client._connect({'route': route})
    begun = False
    started = time.monotonic()
    try:
        connection.execute('BEGIN')
        begun = True
        connection.set_progress_handler(
            lambda: 1 if time.monotonic() - started > MAX_SECONDS else 0,
            1000)
        names = {row[1] for row in connection.execute('PRAGMA database_list')}
        if schema not in names:
            raise ValueError('SQLite attachment is unavailable on this connection')
        observed = connection.execute(
            'SELECT type, sql FROM ' + _identifier(schema) +
            '.sqlite_schema WHERE name=?', (name,)).fetchone()
        if observed is None or observed[0] not in {'table', 'view'} or (
                kind == 'view') != (observed[0] == 'view'):
            raise ValueError('Native relation is unavailable or its kind changed')
        source = str(observed[1] or '')
        is_virtual = bool(re.match(
            r'^\s*CREATE\s+VIRTUAL\s+TABLE\b', source, re.I))
        is_fts = is_virtual and bool(re.search(
            r'\bUSING\s+fts\d?\b', source, re.I))
        if (kind in {'fts-table', 'virtual-table'}) != is_virtual or (
                kind == 'fts-table') != is_fts:
            raise ValueError('Native relation kind changed')
        qualified = _identifier(schema) + '.' + _identifier(name)
        cursor = connection.execute('SELECT * FROM ' + qualified +
                                    ' LIMIT ?', (row_limit + 1,))
        description = cursor.description or ()
        if not 1 <= len(description) <= 256:
            raise ValueError('DDN data capture needs 1–256 visible columns')
        columns = [{'name': str(item[0]), 'key': str(index),
                    'ordinal': index, 'native_type': None}
                   for index, item in enumerate(description)]
        rows, size, exceeded = [], 0, False
        for native_row in cursor:
            if time.monotonic() - started > MAX_SECONDS:
                raise ValueError('SQLite data capture exceeded 30 seconds')
            if len(rows) >= row_limit:
                exceeded = True
                break
            row = [value(item) for item in native_row]
            size += len(json.dumps(row, ensure_ascii=False,
                                   allow_nan=False).encode('utf8'))
            if size > MAX_BYTES:
                raise ValueError('SQLite data capture exceeds 4 MiB')
            rows.append(row)
        if exceeded and mode == 'full':
            raise ValueError('Full data capture exceeds the row budget')
        acquisition = {
            'engine_id': 'sqlite', 'endpoint_id': endpoint_id,
            'database_target_id': target_id, 'resource_id': resource_id,
            'schema': schema, 'relation': name, 'kind': kind,
            'mode': mode, 'row_limit': row_limit, 'rows': len(rows),
            'more_rows_observed': exceeded,
            'ordering': 'unspecified native order',
            'observed_at': datetime.now(timezone.utc).isoformat(),
            'consistency': 'independently owned native read transaction',
            'value_encoding': 'exact SQLite storage values in positional JSON'}
        metadata = {
            'result_id': str(uuid.uuid4()), 'execution_id': None,
            'title': qualified, 'schema': {'columns': columns},
            'complete': not exceeded,
            'export_coverage': 'full relation' if not exceeded else 'bounded sample',
            'acquisition': acquisition, 'consistency': acquisition['consistency'],
            'value_encoding': acquisition['value_encoding']}
        encoded = export_workspace(metadata, rows)
        connection.execute('ROLLBACK')
        begun = False
        snapshot = json.loads(encoded)
        return {
            'snapshot': snapshot, 'acquisition': acquisition,
            'columns': columns,
            'views': [{'id': 'result_' + str(number),
                       'label': 'Data page ' + str(number), 'entry': filename}
                      for number, filename in enumerate(snapshot['files'], 1)],
            'sha256': hashlib.sha256(encoded).hexdigest(),
            'filename': 'sqlite-relation-data.ddn-workspace.json',
            'warnings': ['This is a bounded sample; more rows were observed.']
            if exceeded else []}
    finally:
        connection.set_progress_handler(None, 0)
        try:
            if begun:
                connection.execute('ROLLBACK')
        finally:
            provider.client._discard_failed_session(connection)
