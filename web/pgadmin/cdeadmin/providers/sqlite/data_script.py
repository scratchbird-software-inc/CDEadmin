"""Exact, bounded SQLite table-data INSERT script from an owned read handle."""

import hashlib
import math
import os
import sqlite3
import stat

from pgadmin.cdeadmin.sdk import RelationalClientError
from ..embedded_route import contained_database
from .provider import _resource_id, _resources
from .values import NativeTextBytes

MAX_ROWS = 5000
MAX_BYTES = 1024 * 1024


def _quote(name):
    if not isinstance(name, str) or not name or '\x00' in name or len(name.encode('utf8')) > 256:
        raise ValueError('Invalid SQLite identifier')
    return '"' + name.replace('"', '""') + '"'


def _literal(value):
    if value is None:
        return 'NULL'
    if type(value) is int:
        return str(value)
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('Nonfinite SQLite REAL cannot be exported as native SQL')
        return repr(value)
    if isinstance(value, NativeTextBytes):
        raise ValueError('Invalid UTF-8 TEXT cannot be exported as a lossless SQL literal')
    if type(value) is bytes:
        return "X'" + value.hex() + "'"
    if type(value) is str:
        if '\x00' in value:
            # SQLite text may contain NUL; CHAR(0) preserves it without
            # relying on a SQL literal that native tokenizers truncate.
            pieces = value.split('\x00')
            return ' || char(0) || '.join("'" + part.replace("'", "''") + "'"
                                           for part in pieces)
        return "'" + value.replace("'", "''") + "'"
    raise ValueError('Unsupported SQLite storage class in native SQL export')


def export(provider, route, resource_id, *, endpoint_id, target_id):
    provider._require('data_read', 'resource')
    path = contained_database(route)
    if path == ':memory:' or not os.path.isfile(path):
        raise RelationalClientError('Native SQL export requires an existing registered SQLite file')
    before_info = os.stat(path)
    if not stat.S_ISREG(before_info.st_mode):
        raise RelationalClientError('Native SQL export requires a regular SQLite file')
    connection = provider.client._connect({'route': route})
    try:
        connection.execute('BEGIN')
        resources = _resources(connection, {})
        by_id = {item['resource_id']: item for item in resources}
        relation = by_id.get(resource_id)
        if (relation is None or relation['resource_kind'] != 'table' or
                relation['native'].get('system_object') is True or
                relation['display_path'][0] != 'main' or
                relation['resource_id'] != _resource_id('table', ['main'], relation['display_name'])):
            raise ValueError('Select an ordinary user table in the main SQLite file')
        name = relation['display_name']
        columns = [item['name'] for item in relation['native']['columns']
                   if item.get('hidden') == 0]
        if not columns or len(columns) > 512 or len(set(columns)) != len(columns):
            raise ValueError('SQLite table has no unambiguous writable columns')
        target = _quote('main') + '.' + _quote(name)
        names = ', '.join(_quote(column) for column in columns)
        source = ('SELECT ' + names + ' FROM ' + target +
                  f' LIMIT {MAX_ROWS + 1}')
        lines = ['-- SQLite native data export; review before executing.',
                 '-- No data was modified during export.']
        length = sum(len(line.encode('utf8')) + 1 for line in lines)
        count = 0
        cursor = connection.execute(source)
        try:
            for row in cursor:
                if count == MAX_ROWS:
                    raise ValueError('Table exceeds the 5,000-row SQL export limit')
                statement = ('INSERT INTO ' + target + ' (' + names + ') VALUES (' +
                             ', '.join(_literal(value) for value in row) + ');')
                length += len(statement.encode('utf8')) + 1
                if length > MAX_BYTES:
                    raise ValueError('Native SQLite SQL export exceeds 1 MiB')
                lines.append(statement)
                count += 1
        finally:
            cursor.close()
        connection.execute('ROLLBACK')
        after_info = os.stat(path)
        if (before_info.st_dev, before_info.st_ino) != (after_info.st_dev, after_info.st_ino):
            raise RelationalClientError('SQLite registered file changed during SQL export')
        script = '\n'.join(lines) + '\n'
        return {'format': 'scratchrobin.sqlite.table-data-sql@1',
            'endpoint_id': endpoint_id, 'database_target_id': target_id,
            'resource_id': resource_id, 'table': name,
            'rows': count, 'executed': False,
            'source': script, 'source_sha256': hashlib.sha256(script.encode('utf8')).hexdigest(),
            'warnings': ['No INSERT was executed; use the shared Query Tool to import the reviewed script.']}
    except BaseException:
        if connection.in_transaction:
            try:
                connection.execute('ROLLBACK')
            except sqlite3.Error:
                pass
        raise
    finally:
        provider.client._discard_failed_session(connection)
