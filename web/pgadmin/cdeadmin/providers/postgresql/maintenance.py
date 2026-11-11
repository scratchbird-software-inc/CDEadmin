##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Native PostgreSQL maintenance: VACUUM, ANALYZE, REINDEX, CLUSTER, TRUNCATE, REFRESH.

Every identifier is double-quoted from catalog identity; every option comes from
a closed allow-list with strict types. Statements that PostgreSQL refuses inside
a transaction block (VACUUM, REINDEX SCHEMA/DATABASE, any REINDEX ... CONCURRENTLY)
are marked ``autocommit`` so the apply route runs them without BEGIN/COMMIT.
"""

from __future__ import annotations

MAINTENANCE_OPERATIONS = {
    'table': frozenset({'vacuum', 'analyze', 'reindex', 'cluster', 'truncate'}),
    'index': frozenset({'reindex'}),
    # Schema and database scope VACUUM/ANALYZE (M6, 2026-11-11): a schema
    # has no VACUUM form, so its statement names the tables captured with it.
    'schema': frozenset({'vacuum', 'analyze', 'reindex'}),
    'database': frozenset({'vacuum', 'analyze', 'reindex'}),
    'materialized-view': frozenset({'refresh'}),
    # Server operations from the provider tree's server scope (M6, 2026-11-11):
    # the inherited server menu's reload, restore point and WAL replay control.
    'server': frozenset({'reload', 'restore-point', 'wal-replay-pause',
                         'wal-replay-resume'}),
}
#: Maintenance actions whose plan needs an explicit confirmation (typed name for TRUNCATE).
CONFIRMED = frozenset({
    ('table', 'truncate'), ('table', 'cluster'), ('schema', 'reindex'), ('database', 'reindex'),
    ('server', 'reload'), ('server', 'wal-replay-pause'), ('server', 'wal-replay-resume'),
})
MUTATION_CLASSES = {
    'vacuum': 'admin', 'analyze': 'admin', 'reindex': 'admin', 'cluster': 'admin',
    'truncate': 'destructive', 'refresh': 'admin',
    'reload': 'admin', 'restore-point': 'admin', 'wal-replay-pause': 'admin',
    'wal-replay-resume': 'admin',
}

_OPTIONS = {
    ('table', 'vacuum'): {'full', 'freeze', 'analyze', 'verbose', 'parallel'},
    ('table', 'analyze'): {'verbose', 'skip_locked'},
    ('table', 'reindex'): {'concurrently', 'verbose'},
    ('index', 'reindex'): {'concurrently', 'verbose'},
    ('schema', 'vacuum'): {'full', 'freeze', 'analyze', 'verbose', 'parallel'},
    ('schema', 'analyze'): {'verbose', 'skip_locked'},
    ('schema', 'reindex'): {'concurrently', 'verbose'},
    ('database', 'vacuum'): {'full', 'freeze', 'analyze', 'verbose', 'parallel'},
    ('database', 'analyze'): {'verbose', 'skip_locked'},
    ('database', 'reindex'): {'concurrently', 'verbose'},
    ('table', 'cluster'): {'index', 'verbose'},
    ('table', 'truncate'): {'restart_identity', 'cascade', 'confirmation'},
    ('materialized-view', 'refresh'): {'concurrently', 'with_data'},
    ('server', 'reload'): set(),
    ('server', 'restore-point'): {'name'},
    ('server', 'wal-replay-pause'): set(),
    ('server', 'wal-replay-resume'): set(),
}
_RESTORE_POINT = __import__('re').compile(r'[^\x00]{1,63}')
_MAX_PARALLEL = 1024


def _refuse(message):
    from .native_admin import PostgreSQLNativeAdminError
    raise PostgreSQLNativeAdminError(message)


def _flag(draft, name, default=False):
    value = draft.get(name, default)
    if type(value) is not bool:
        _refuse(f'{name} must be boolean')
    return value


def _qualified(native):
    from .native_admin import _identifier, _name
    return (_identifier(_name(native.get('schema'), 'schema'), 'schema') + '.' +
            _identifier(_name(native.get('name'), 'name'), 'name'))


def _schema_relations(native):
    """The schema's tables and materialized views as one quoted list, from the
    listing that produced the node; a table created afterwards is not in it."""
    from .native_admin import _identifier, _name
    schema = _name(native.get('name'), 'name')
    relations = native.get('relations')
    if not isinstance(relations, list) or any(type(item) is not str for item in relations):
        _refuse('the schema listing carries no table list to vacuum or analyze')
    if not relations:
        _refuse('the schema has no tables or materialized views to vacuum or analyze')
    return ', '.join(_identifier(schema, 'schema') + '.' + _identifier(name, 'name')
                     for name in sorted(set(relations)))


def _parallel(value):
    if value in (None, ''):
        return None
    if type(value) is str and value.isascii() and value.isdigit():
        value = int(value)
    if type(value) is not int or not 0 <= value <= _MAX_PARALLEL:
        _refuse(f'PARALLEL requires an integer from 0 to {_MAX_PARALLEL}')
    return value


def compile_operation(kind, operation, native, draft):
    """Return the exact statement, transaction mode and receipt description."""
    from .native_admin import _identifier, _name
    key = (kind, operation)
    if key not in _OPTIONS:
        _refuse('PostgreSQL maintenance operation is unavailable for this object')
    if set(draft) - _OPTIONS[key]:
        _refuse('Unknown PostgreSQL maintenance option')
    options = []
    autocommit = False
    if kind == 'server':
        return _server_operation(operation, draft)
    if kind in {'schema', 'database'}:
        target = _identifier(_name(native.get('name'), 'name'), 'name')
    else:
        target = _qualified(native)
    object_name = native.get('name')
    if operation in {'vacuum', 'analyze'} and kind == 'database':
        # Without a table list VACUUM/ANALYZE cover the connected database;
        # the apply route checks that database is the one named here.
        target = ''
    elif operation in {'vacuum', 'analyze'} and kind == 'schema':
        target = _schema_relations(native)
    if operation == 'vacuum':
        flags = {name: _flag(draft, name) for name in ('full', 'freeze', 'analyze', 'verbose')}
        parallel = _parallel(draft.get('parallel'))
        if flags['full'] and parallel is not None:
            _refuse('VACUUM FULL cannot use PARALLEL')
        options = [name.upper() for name, on in flags.items() if on]
        if parallel is not None:
            options.append(f'PARALLEL {parallel}')
        statement = ('VACUUM' + (' (' + ', '.join(options) + ')' if options else '') + ' ' + target).rstrip()
        autocommit = True
    elif operation == 'analyze':
        options = [name.upper() for name in ('verbose', 'skip_locked') if _flag(draft, name)]
        statement = ('ANALYZE' + (' (' + ', '.join(options) + ')' if options else '') + ' ' + target).rstrip()
    elif operation == 'reindex':
        concurrently = _flag(draft, 'concurrently')
        options = (['CONCURRENTLY'] if concurrently else []) + (['VERBOSE'] if _flag(draft, 'verbose') else [])
        word = {'table': 'TABLE', 'index': 'INDEX', 'schema': 'SCHEMA', 'database': 'DATABASE'}[kind]
        statement = 'REINDEX' + (' (' + ', '.join(options) + ')' if options else '') + f' {word} {target}'
        autocommit = concurrently or kind in {'schema', 'database'}
    elif operation == 'cluster':
        verbose = _flag(draft, 'verbose')
        index = draft.get('index')
        options = ['VERBOSE'] if verbose else []
        statement = ('CLUSTER' + (' (VERBOSE)' if verbose else '') + ' ' + target +
                     ('' if index in (None, '') else ' USING ' + _identifier(index, 'index')))
    elif operation == 'truncate':
        if draft.get('confirmation') != object_name or not isinstance(object_name, str):
            _refuse('truncate confirmation does not match table name')
        restart, cascade = _flag(draft, 'restart_identity'), _flag(draft, 'cascade')
        options = (['RESTART IDENTITY'] if restart else []) + (['CASCADE'] if cascade else [])
        statement = ('TRUNCATE TABLE ' + target + (' RESTART IDENTITY' if restart else ' CONTINUE IDENTITY') +
                     (' CASCADE' if cascade else ' RESTRICT'))
    else:
        concurrently = _flag(draft, 'concurrently')
        with_data = _flag(draft, 'with_data', True)
        if concurrently and not with_data:
            _refuse('REFRESH CONCURRENTLY cannot be combined with WITH NO DATA')
        options = (['CONCURRENTLY'] if concurrently else []) + ([] if with_data else ['WITH NO DATA'])
        statement = ('REFRESH MATERIALIZED VIEW ' + ('CONCURRENTLY ' if concurrently else '') + target +
                     (' WITH DATA' if with_data else ' WITH NO DATA'))
    return {
        'statement': statement, 'read_only': False, 'autocommit': autocommit,
        'maintenance': {'action': operation, 'object_kind': kind, 'object': object_name,
                        'options': options, 'transaction_mode': 'autocommit' if autocommit else 'transaction'},
    }


def _server_operation(operation, draft):
    """One server-wide function call; the result row is the receipt."""
    from .native_admin import _literal
    if operation == 'reload':
        statement = 'SELECT pg_catalog.pg_reload_conf() AS reloaded'
    elif operation == 'restore-point':
        name = draft.get('name')
        if not isinstance(name, str) or not _RESTORE_POINT.fullmatch(name):
            _refuse('a restore point needs a name of at most 63 characters')
        statement = ('SELECT pg_catalog.pg_create_restore_point('
                     + _literal(name, 'name') + ') AS restore_point_lsn')
    elif operation == 'wal-replay-pause':
        statement = 'SELECT pg_catalog.pg_wal_replay_pause() AS paused'
    else:
        statement = 'SELECT pg_catalog.pg_wal_replay_resume() AS resumed'
    return {
        'statement': statement, 'read_only': False, 'autocommit': False, 'returns_rows': True,
        'maintenance': {'action': operation, 'object_kind': 'server', 'object': None,
                        'options': [], 'transaction_mode': 'transaction'},
    }


def form(kind, operation, field):
    """Dialog fields for the catalog form; mirrors the allow-list above."""
    def boolean(name, label, **kw):
        return field(name, label, 'boolean', **kw)
    fields = []
    if operation == 'vacuum':
        fields = [boolean('full', 'Full (rewrite the table; exclusive lock)'),
                  boolean('freeze', 'Freeze row versions'),
                  boolean('analyze', 'Also analyze'),
                  boolean('verbose', 'Verbose'),
                  field('parallel', 'Parallel workers (not with Full)', 'number',
                        help='Leave empty to let the server decide; 0 disables parallel index vacuuming.')]
    elif operation == 'analyze':
        fields = [boolean('verbose', 'Verbose'), boolean('skip_locked', 'Skip tables that cannot be locked')]
    elif operation == 'reindex':
        fields = [boolean('concurrently', 'Concurrently (cannot run in a transaction block)'),
                  boolean('verbose', 'Verbose')]
    elif operation == 'cluster':
        fields = [field('index', 'Index to cluster on', help='Leave empty to reuse the index the table was last clustered on.'),
                  boolean('verbose', 'Verbose')]
    elif operation == 'truncate':
        fields = [boolean('restart_identity', 'Restart identity (reset owned sequences)'),
                  boolean('cascade', 'Cascade to tables with foreign keys to this table'),
                  field('confirmation', 'Type the table name to confirm', required=True)]
    elif operation == 'refresh':
        fields = [boolean('with_data', 'Populate with data', default=True),
                  boolean('concurrently', 'Concurrently (requires a unique index)')]
    elif operation == 'restore-point':
        fields = [field('name', 'Restore point name', required=True,
                        help='Recorded in the WAL; a recovery_target_name for point-in-time recovery.')]
    titles = {'vacuum': 'Vacuum', 'analyze': 'Analyze', 'reindex': 'Reindex', 'cluster': 'Cluster',
              'truncate': 'Truncate', 'refresh': 'Refresh', 'reload': 'Reload configuration',
              'restore-point': 'Create restore point', 'wal-replay-pause': 'Pause WAL replay',
              'wal-replay-resume': 'Resume WAL replay'}
    if kind == 'server':
        return {'form_id': f'postgresql-server-{operation}', 'form_key': 'native:postgresql:server:server',
                'title': titles[operation], 'fields': fields}
    return {'form_id': f'postgresql-{kind}-{operation}', 'form_key': f'native:postgresql:schema:{kind}',
            'title': f'{titles[operation]} {kind.replace("-", " ")}', 'fields': fields}
