"""Exact-file DuckDB COPY script planning; no file or database writes."""

import hashlib
import os
import stat

from .duckdb_test_data import _quote


def plan(model, request, root):
    if (not isinstance(request, dict) or set(request) != {'resource_id', 'direction', 'format', 'path'} or
            request['direction'] not in {'from', 'to'} or request['format'] not in {'CSV', 'PARQUET'}):
        raise ValueError('Select one exact DuckDB table, direction and native file format')
    identity = request['resource_id']
    row = model['rows'].get(identity) if isinstance(identity, str) else None
    databases = [item for item in model['rows'].values() if item['kind'] == 'database' and item['system'] == 'false']
    if (len(databases) != 1 or row is None or row['kind'] != 'table' or row['system'] != 'false' or
            len(row['path']) != 3 or row['path'][0] != databases[0]['name'] or
            row['native'].get('catalog_metadata', {}).get('temporary') is not False):
        raise ValueError('Select a persistent table in the exact registered DuckDB file')
    value = request['path']
    if not isinstance(value, str) or not os.path.isabs(value) or '\x00' in value:
        raise ValueError('COPY requires an absolute native file path')
    if not isinstance(root, str) or not os.path.isabs(root):
        raise ValueError('DuckDB endpoint has no absolute filesystem root')
    root_path, path = os.path.realpath(root), os.path.realpath(value)
    if os.path.commonpath((root_path, path)) != root_path:
        raise ValueError('COPY file escapes the registered filesystem root')
    if request['direction'] == 'from':
        if os.path.islink(value) or not os.path.isfile(path) or not stat.S_ISREG(os.stat(path).st_mode):
            raise ValueError('COPY import requires an existing regular file, not a symlink')
    else:
        if not os.path.isdir(os.path.dirname(path)) or os.path.lexists(value):
            raise ValueError('COPY export requires an existing parent and absent destination')
    target = '.'.join(_quote(part) for part in row['path'])
    escaped = path.replace("'", "''")
    direction = 'FROM' if request['direction'] == 'from' else 'TO'
    options = 'FORMAT CSV, HEADER TRUE' if request['format'] == 'CSV' else 'FORMAT PARQUET'
    source = f"COPY {target} {direction} '{escaped}' ({options});"
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected COPY') from None
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.COPY:
        raise ValueError('Exactly one native COPY statement is required')
    return {'format': 'scratchrobin.duckdb.copy-plan@1', 'engine_id': 'duckdb',
        'resource_id': identity, 'target': target, 'direction': request['direction'],
        'native_format': request['format'], 'path': path, 'source': source,
        'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'executed': False,
        'warnings': ['Preview only; open this script on the exact registered file in the shared Query Tool.',
            'Native file and transaction effects apply; SQL rollback does not remove exported files.']}
