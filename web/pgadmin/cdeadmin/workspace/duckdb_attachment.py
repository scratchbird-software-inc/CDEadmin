"""Session-bound DuckDB ATTACH/DETACH SQL preview; never executes it."""

import hashlib
import os
import stat

from ..providers.embedded_route import contained_database
from ..sdk.relational import RelationalClientError
from .duckdb_test_data import _quote


def plan(route, request):
    if not isinstance(request, dict) or request.get('action') not in {'attach', 'detach'}:
        raise ValueError('Select native ATTACH or DETACH')
    action = request['action']
    required = {'action', 'alias', 'path', 'read_only'} if action == 'attach' else {'action', 'alias'}
    if set(request) != required:
        raise ValueError('Native attachment options are incomplete or unsupported')
    alias = request['alias']
    if (not isinstance(alias, str) or not alias or '\x00' in alias or
            len(alias.encode()) > 128 or alias.lower() in {'memory', 'system', 'temp'}):
        raise ValueError('Native attachment alias is invalid or reserved')
    try:
        primary = contained_database(route)
    except RelationalClientError as error:
        raise ValueError(str(error)) from None
    if primary == ':memory:':
        raise ValueError('Independent in-memory DuckDB attachment scope is unavailable')
    primary_alias = os.path.splitext(os.path.basename(primary))[0]
    if alias.lower() == primary_alias.lower():
        raise ValueError('Native attachment alias conflicts with the primary catalog')
    if action == 'detach':
        source = 'DETACH ' + _quote(alias) + ';'
        target = alias
    else:
        value, read_only = request['path'], request['read_only']
        if type(read_only) is not bool:
            raise ValueError('Read-only choice must be Boolean')
        if route.get('read_only') is True and not read_only:
            raise ValueError('Read-only primary route cannot attach a writable database')
        if not isinstance(value, str) or not os.path.isabs(value) or '\x00' in value:
            raise ValueError('ATTACH requires an absolute native file path')
        try:
            path = contained_database({**route, 'database': value})
        except RelationalClientError as error:
            raise ValueError(str(error)) from None
        if path == primary or os.path.islink(value):
            raise ValueError('ATTACH requires another registered-root file, not the primary or a symlink')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
        try:
            descriptor = os.open(path, flags)
        except OSError:
            raise ValueError('ATTACH requires an existing readable DuckDB file') from None
        try:
            info = os.fstat(descriptor)
            header = os.read(descriptor, 12)
            if not stat.S_ISREG(info.st_mode) or info.st_size < 12 or header[8:12] != b'DUCK':
                raise ValueError('ATTACH target is not an existing DuckDB database file')
        finally:
            os.close(descriptor)
        escaped = path.replace("'", "''")
        source = f"ATTACH '{escaped}' AS {_quote(alias)}" + (' (READ_ONLY)' if read_only else '') + ';'
        target = path
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected attachment SQL') from None
    expected = duckdb.StatementType.ATTACH if action == 'attach' else duckdb.StatementType.DETACH
    if len(statements) != 1 or statements[0].type != expected:
        raise ValueError('Exactly one native attachment statement is required')
    return {'format': 'scratchrobin.duckdb.attachment-plan@1', 'action': action,
        'alias': alias, 'target': target, 'source': source,
        'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'executed': False,
        'session_scope': 'selected-retained-connection',
        'warnings': ['Preview only; run this script on the selected retained DuckDB connection.',
            'An independent connection cannot observe or modify another session’s attachments.']}
