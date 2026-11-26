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
    # M7 (2026-11-11): the inherited table node's row count, statistics
    # reset and trigger toggles join the maintenance set.
    'table': frozenset({'vacuum', 'analyze', 'reindex', 'cluster', 'truncate', 'count-rows',
                        'reset-statistics', 'enable-triggers', 'disable-triggers',
                        'create-partition', 'attach-partition', 'detach-partition'}),
    # A partitioned table takes the partition operations and the row count (M7).
    'partitioned-table': frozenset({'create-partition', 'attach-partition', 'count-rows'}),
    'index': frozenset({'reindex', 'attach-partition'}),
    'partitioned-index': frozenset({'reindex', 'attach-partition'}),
    # Schema and database scope VACUUM/ANALYZE (M6, 2026-11-11): a schema
    # has no VACUUM form, so its statement names the tables captured with it.
    'schema': frozenset({'vacuum', 'analyze', 'reindex'}),
    'database': frozenset({'vacuum', 'analyze', 'reindex', 'reindex-system'}),
    'materialized-view': frozenset({'refresh'}),
    # Server operations from the provider tree's server scope (M6, 2026-11-11):
    # the inherited server menu's reload, restore point and WAL replay control.
    'server': frozenset({'reload', 'restore-point', 'wal-replay-pause',
                         'wal-replay-resume', 'checkpoint',
                         'inspect-configuration', 'alter-system-set',
                         'alter-system-reset', 'alter-system-reset-all',
                         'inspect-prepared-transactions', 'resolve-prepared-transaction'}),
    # Role and tablespace operations that act inside one database (M6,
    # 2026-11-11): the dialog picks the database; the plan's route runs there.
    'role': frozenset({'reassign-owned', 'drop-owned'}),
    'tablespace': frozenset({'move-objects'}),
    # The inherited pgAgent "Run now" (M6, 2026-11-11).
    'pgagent-job': frozenset({'run-now'}),
}
#: Operations whose database comes from the dialog's `database` reference.
DATABASE_PICKED = frozenset({('role', 'reassign-owned'), ('role', 'drop-owned'),
                             ('tablespace', 'move-objects')})
# A database reference: the public resource id a picker sends
# (postgresql:postgresql/endpoint/<endpoint>/database/OID), the catalog's own spelling
# (postgresql:pg_database:OID) or the older path form (postgresql:pg_database/OID).
_DATABASE_REFERENCE = __import__('re').compile(
    r'postgresql:(?:pg_database[:/]|postgresql/endpoint/[0-9a-f-]{36}/database/)([1-9][0-9]{0,9})')
MOVE_OBJECT_TYPES = {'all': ('TABLE', 'INDEX', 'MATERIALIZED VIEW'), 'tables': ('TABLE',),
                     'indexes': ('INDEX',), 'materialized-views': ('MATERIALIZED VIEW',)}
#: Maintenance actions whose plan needs an explicit confirmation (typed name for TRUNCATE).
CONFIRMED = frozenset({
    ('table', 'truncate'), ('table', 'cluster'), ('schema', 'reindex'), ('database', 'reindex'),
    ('database', 'reindex-system'), ('index', 'attach-partition'), ('partitioned-index', 'attach-partition'),
    ('server', 'checkpoint'), ('server', 'reload'), ('server', 'wal-replay-pause'), ('server', 'wal-replay-resume'),
    ('server', 'alter-system-reset'), ('server', 'alter-system-reset-all'),
    ('server', 'resolve-prepared-transaction'),
    ('role', 'reassign-owned'), ('role', 'drop-owned'), ('tablespace', 'move-objects'),
    ('pgagent-job', 'run-now'), ('table', 'disable-triggers'), ('table', 'detach-partition'),
})
MUTATION_CLASSES = {
    'vacuum': 'admin', 'analyze': 'admin', 'reindex': 'admin', 'reindex-system': 'admin', 'cluster': 'admin',
    'truncate': 'destructive', 'refresh': 'admin',
    'checkpoint': 'admin', 'reload': 'admin', 'restore-point': 'admin', 'wal-replay-pause': 'admin',
    'wal-replay-resume': 'admin',
    'inspect-configuration': 'read', 'alter-system-set': 'admin',
    'alter-system-reset': 'admin', 'alter-system-reset-all': 'destructive',
    'inspect-prepared-transactions': 'read', 'resolve-prepared-transaction': 'destructive',
    'reassign-owned': 'admin', 'drop-owned': 'destructive', 'move-objects': 'admin',
    'run-now': 'admin',
    'count-rows': 'read', 'reset-statistics': 'admin', 'enable-triggers': 'admin',
    'disable-triggers': 'admin', 'create-partition': 'write', 'attach-partition': 'admin',
    'detach-partition': 'admin',
}

_VACUUM_COMMON = {
    'full', 'freeze', 'analyze', 'verbose', 'parallel',
    'disable_page_skipping', 'skip_locked', 'index_cleanup',
    'process_main', 'process_toast', 'truncate',
    'skip_database_stats', 'only_database_stats', 'buffer_usage_limit',
}

_OPTIONS = {
    ('table', 'vacuum'): _VACUUM_COMMON - {'only_database_stats'},
    ('table', 'analyze'): {'verbose', 'skip_locked', 'buffer_usage_limit', 'columns'},
    ('table', 'reindex'): {'concurrently', 'verbose', 'tablespace'},
    ('index', 'reindex'): {'concurrently', 'verbose', 'tablespace'},
    ('partitioned-index', 'reindex'): {'concurrently', 'verbose', 'tablespace'},
    ('index', 'attach-partition'): {'child_schema', 'child_index'},
    ('partitioned-index', 'attach-partition'): {'child_schema', 'child_index'},
    ('schema', 'vacuum'): _VACUUM_COMMON - {'only_database_stats'},
    ('schema', 'analyze'): {'verbose', 'skip_locked', 'buffer_usage_limit'},
    ('schema', 'reindex'): {'concurrently', 'verbose', 'tablespace'},
    ('database', 'vacuum'): _VACUUM_COMMON,
    ('database', 'analyze'): {'verbose', 'skip_locked', 'buffer_usage_limit'},
    ('database', 'reindex'): {'concurrently', 'verbose', 'tablespace'},
    ('database', 'reindex-system'): {'concurrently', 'verbose', 'tablespace'},
    ('table', 'cluster'): {'index', 'verbose'},
    ('table', 'truncate'): {'restart_identity', 'cascade', 'confirmation'},
    ('materialized-view', 'refresh'): {'concurrently', 'with_data'},
    ('server', 'checkpoint'): {'wait_timeout_ms'},
    ('server', 'reload'): set(),
    ('server', 'restore-point'): {'name'},
    ('server', 'wal-replay-pause'): set(),
    ('server', 'wal-replay-resume'): set(),
    ('server', 'inspect-configuration'): {'scope', 'parameter'},
    ('server', 'alter-system-set'): {'parameter', 'value_mode', 'value', 'reload_after'},
    ('server', 'alter-system-reset'): {'parameter', 'reload_after', 'confirmation'},
    ('server', 'alter-system-reset-all'): {'reload_after', 'confirmation'},
    ('server', 'inspect-prepared-transactions'): set(),
    ('server', 'resolve-prepared-transaction'): {'gid', 'expected_database', 'expected_owner', 'expected_xid', 'decision', 'coordinator_reference', 'confirmation'},
    ('role', 'reassign-owned'): {'database', 'new_owner'},
    ('role', 'drop-owned'): {'database', 'cascade', 'confirmation'},
    ('tablespace', 'move-objects'): {'database', 'object_type', 'new_tablespace', 'owner'},
    ('pgagent-job', 'run-now'): set(),
    ('table', 'count-rows'): set(),
    ('table', 'reset-statistics'): set(),
    ('table', 'enable-triggers'): set(),
    ('table', 'disable-triggers'): set(),
    ('table', 'create-partition'): {'name', 'schema', 'is_default', 'partition_value', 'relpersistence',
                                    'is_partitioned', 'partition_type', 'partition_keys', 'amname',
                                    'fillfactor', 'spcname', 'relowner', 'description'},
    ('partitioned-table', 'create-partition'): {'name', 'schema', 'is_default', 'partition_value',
                                                'relpersistence', 'is_partitioned', 'partition_type',
                                                'partition_keys', 'amname', 'fillfactor', 'spcname',
                                                'relowner', 'description'},
    ('table', 'attach-partition'): {'partition', 'is_default', 'partition_value'},
    ('partitioned-table', 'attach-partition'): {'partition', 'is_default', 'partition_value'},
    ('table', 'detach-partition'): {'mode'},
    ('partitioned-table', 'count-rows'): set(),
}
_RESTORE_POINT = __import__('re').compile(r'[^\x00]{1,63}')
_BUFFER_LIMIT = __import__('re').compile(r'(?:0|[1-9][0-9]{0,9})(?:\s*(?:B|kB|MB|GB|TB))?', __import__('re').IGNORECASE)
_MAX_PARALLEL = 1024


def _buffer_usage_limit(value):
    if value in (None, ''):
        return None
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return str(value)
    if not isinstance(value, str) or not _BUFFER_LIMIT.fullmatch(value.strip()):
        _refuse('BUFFER_USAGE_LIMIT must be 0 or an integer size with optional B, kB, MB, GB or TB unit')
    return value.strip()


def _tri_bool(draft, name):
    if name not in draft or draft[name] in (None, ''):
        return None
    val = draft[name]
    if type(val) is bool:
        return val
    if isinstance(val, str) and val.upper() in ('TRUE', 'FALSE'):
        return val.upper() == 'TRUE'
    _refuse(f'{name} must be boolean')


def _analyze_columns(value):
    from .native_admin import _identifier, _name
    if value in (None, '', []):
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(',') if part.strip()]
    elif isinstance(value, list):
        items = []
        for entry in value:
            if isinstance(entry, dict):
                col = entry.get('name') or entry.get('column') or entry.get('value')
                items.append(_name(col, 'column'))
            else:
                items.append(_name(entry, 'column'))
    else:
        _refuse('ANALYZE columns must be a list of column names')
    if not items or len(set(items)) != len(items):
        _refuse('ANALYZE columns must be non-empty and distinct')
    return [_identifier(col, 'column') for col in items]


def _refuse(message, code=None, field_id=None):
    from .native_admin import PostgreSQLNativeAdminError
    raise PostgreSQLNativeAdminError(message, code, field_id)


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
    if key in DATABASE_PICKED:
        return _database_picked_operation(kind, operation, native, draft)
    if kind in {'table', 'partitioned-table'} and operation in {
            'count-rows', 'reset-statistics', 'enable-triggers', 'disable-triggers'}:
        return _table_operation(operation, native)
    if operation in {'create-partition', 'attach-partition', 'detach-partition'} and kind in {'table', 'partitioned-table'}:
        from .partitions import compile_operation as compile_partition
        compiled = compile_partition(operation, native, draft)
        compiled.setdefault('autocommit', False)
        compiled['maintenance'] = {'action': operation, 'object_kind': kind, 'object': native.get('name'),
                                   'options': [], 'transaction_mode': 'autocommit' if compiled['autocommit']
                                   else 'transaction'}
        return compiled
    if operation == 'attach-partition' and kind in {'index', 'partitioned-index'}:
        from .indexes import compile_attach_partition
        compiled = compile_attach_partition(native, draft)
        compiled.setdefault('autocommit', False)
        compiled['maintenance'] = {'action': operation, 'object_kind': kind, 'object': native.get('name'),
                                   'options': [], 'transaction_mode': 'transaction'}
        return compiled
    if key == ('pgagent-job', 'run-now'):
        from .pgagent import run_now
        compiled = run_now(native)
        compiled['maintenance'] = {'action': operation, 'object_kind': kind, 'object': native.get('name'),
                                   'options': [], 'transaction_mode': 'transaction'}
        return compiled
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
    min_ver = None
    if operation == 'vacuum':
        from .native_admin import _literal
        flags = {name: _flag(draft, name) for name in (
            'full', 'freeze', 'analyze', 'verbose',
            'disable_page_skipping', 'skip_locked', 'skip_database_stats',
        )}
        only_db_stats = _flag(draft, 'only_database_stats') if 'only_database_stats' in draft else False
        if only_db_stats:
            if kind != 'database':
                _refuse('VACUUM (ONLY_DATABASE_STATS) applies only to database scope')
            if flags['full'] or flags['freeze'] or flags['analyze'] or flags['skip_database_stats']:
                _refuse('ONLY_DATABASE_STATS cannot be combined with FULL, FREEZE, ANALYZE or SKIP_DATABASE_STATS')
        if flags['full'] and flags['skip_locked']:
            _refuse('VACUUM FULL cannot be combined with SKIP_LOCKED')
        parallel = _parallel(draft.get('parallel'))
        if flags['full'] and parallel is not None:
            _refuse('VACUUM FULL cannot use PARALLEL')
        idx_cleanup = draft.get('index_cleanup')
        if idx_cleanup not in (None, ''):
            if isinstance(idx_cleanup, bool) or not isinstance(idx_cleanup, str):
                _refuse('INDEX_CLEANUP must be AUTO, ON or OFF')
            idx_cleanup = idx_cleanup.strip().upper()
            if idx_cleanup not in {'AUTO', 'ON', 'OFF'}:
                _refuse('INDEX_CLEANUP must be AUTO, ON or OFF')
            if flags['full']:
                _refuse('VACUUM FULL cannot use INDEX_CLEANUP')
        else:
            idx_cleanup = None
        proc_main = _tri_bool(draft, 'process_main')
        proc_toast = _tri_bool(draft, 'process_toast')
        trunc_opt = _tri_bool(draft, 'truncate')
        if flags['full'] and (proc_main is False or trunc_opt is False):
            _refuse('VACUUM FULL cannot disable PROCESS_MAIN or specify TRUNCATE')
        buf_limit = _buffer_usage_limit(draft.get('buffer_usage_limit'))
        options = [name.upper() for name in ('full', 'freeze', 'analyze', 'verbose', 'disable_page_skipping', 'skip_locked') if flags[name]]
        if idx_cleanup:
            options.append(f'INDEX_CLEANUP {idx_cleanup}')
        if proc_main is False:
            options.append('PROCESS_MAIN FALSE')
            min_ver = max(min_ver or 0, 160000)
        if proc_toast is False:
            options.append('PROCESS_TOAST FALSE')
        if trunc_opt is False:
            options.append('TRUNCATE FALSE')
        if parallel is not None:
            options.append(f'PARALLEL {parallel}')
        if flags['skip_database_stats']:
            options.append('SKIP_DATABASE_STATS')
            min_ver = max(min_ver or 0, 160000)
        if only_db_stats:
            options.append('ONLY_DATABASE_STATS')
            min_ver = max(min_ver or 0, 160000)
        if buf_limit is not None:
            options.append('BUFFER_USAGE_LIMIT ' + _literal(buf_limit, 'buffer_usage_limit'))
            min_ver = max(min_ver or 0, 160000)
        statement = ('VACUUM' + (' (' + ', '.join(options) + ')' if options else '') + ' ' + target).rstrip()
        autocommit = True
    elif operation == 'analyze':
        from .native_admin import _literal
        options = [name.upper() for name in ('verbose', 'skip_locked') if _flag(draft, name)]
        buf_limit = _buffer_usage_limit(draft.get('buffer_usage_limit'))
        if buf_limit is not None:
            options.append('BUFFER_USAGE_LIMIT ' + _literal(buf_limit, 'buffer_usage_limit'))
            min_ver = max(min_ver or 0, 160000)
        col_list = _analyze_columns(draft.get('columns')) if kind == 'table' else []
        col_clause = (' (' + ', '.join(col_list) + ')') if col_list else ''
        statement = ('ANALYZE' + (' (' + ', '.join(options) + ')' if options else '') +
                     ((' ' + target + col_clause) if target else '')).rstrip()
    elif operation in {'reindex', 'reindex-system'}:
        concurrently = _flag(draft, 'concurrently')
        options = (['CONCURRENTLY'] if concurrently else []) + (['VERBOSE'] if _flag(draft, 'verbose') else [])
        spcname = draft.get('tablespace')
        if spcname not in (None, ''):
            options.append('TABLESPACE ' + _identifier(_name(spcname, 'tablespace'), 'tablespace'))
        if operation == 'reindex-system':
            if concurrently:
                _refuse('REINDEX SYSTEM cannot run CONCURRENTLY')
            word = 'SYSTEM'
        else:
            word = {'table': 'TABLE', 'index': 'INDEX', 'partitioned-index': 'INDEX', 'schema': 'SCHEMA', 'database': 'DATABASE'}[kind]
        statement = 'REINDEX' + (' (' + ', '.join(options) + ')' if options else '') + f' {word} {target}'
        autocommit = concurrently or kind in {'schema', 'database', 'partitioned-index'} or operation == 'reindex-system'
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
    out = {
        'statement': statement, 'read_only': False, 'autocommit': autocommit,
        'maintenance': {'action': operation, 'object_kind': kind, 'object': object_name,
                        'options': options, 'transaction_mode': 'autocommit' if autocommit else 'transaction'},
    }
    if min_ver is not None:
        out['minimum_server_version'] = min_ver
    return out


def database_reference_oid(value):
    """The pg_database OID a dialog's database reference names."""
    match = _DATABASE_REFERENCE.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        _refuse('choose the database the operation runs in')
    return int(match.group(1))


def _database_picked_operation(kind, operation, native, draft):
    """REASSIGN OWNED, DROP OWNED and ALTER ... ALL IN TABLESPACE: one
    transaction in the database the dialog picked (plan route), on the
    objects of that database only."""
    from .native_admin import _identifier, _name
    database_reference_oid(draft.get('database'))
    name = _name(native.get('name'), 'name')
    target = _identifier(name, 'name')
    options = []
    if operation == 'reassign-owned':
        new_owner = _identifier(_name(draft.get('new_owner'), 'new_owner'), 'new_owner')
        statement = f'REASSIGN OWNED BY {target} TO {new_owner}'
    elif operation == 'drop-owned':
        if _name(draft.get('confirmation'), 'confirmation') != name:
            _refuse('drop confirmation does not match object name')
        cascade = _flag(draft, 'cascade')
        options = ['CASCADE'] if cascade else []
        statement = f'DROP OWNED BY {target}' + (' CASCADE' if cascade else ' RESTRICT')
    else:
        object_type = draft.get('object_type', 'all')
        if object_type not in MOVE_OBJECT_TYPES:
            _refuse('object_type must be one of ' + ', '.join(sorted(MOVE_OBJECT_TYPES)))
        new_tablespace = _identifier(_name(draft.get('new_tablespace'), 'new_tablespace'), 'new_tablespace')
        if draft.get('new_tablespace') == name:
            _refuse('choose a different tablespace to move the objects to')
        owner = draft.get('owner')
        owned = '' if owner in (None, '') else ' OWNED BY ' + _identifier(_name(owner, 'owner'), 'owner')
        options = [object_type]
        statement = ';\n'.join(f'ALTER {word} ALL IN TABLESPACE {target}{owned} SET TABLESPACE {new_tablespace}'
                                for word in MOVE_OBJECT_TYPES[object_type])
    return {
        'statement': statement, 'read_only': False, 'autocommit': False,
        'maintenance': {'action': operation, 'object_kind': kind, 'object': name,
                        'options': options, 'transaction_mode': 'transaction'},
    }


def _table_operation(operation, native):
    """The inherited table node's own operations (M7): one statement each,
    in a transaction; the row count is a read whose result row is shown."""
    from .native_admin import _name
    target = _qualified(native)
    read_only = operation == 'count-rows'
    if operation == 'count-rows':
        statement = f'SELECT count(*) AS row_count FROM {target}'
    elif operation == 'reset-statistics':
        oid = native.get('oid')
        if type(oid) is str and oid.isdigit():
            oid = int(oid)
        if type(oid) is not int or oid <= 0:
            _refuse('the table listing carries no OID to reset statistics for')
        statement = f'SELECT pg_catalog.pg_stat_reset_single_table_counters({oid}) AS reset'
    else:
        word = 'ENABLE' if operation == 'enable-triggers' else 'DISABLE'
        statement = f'ALTER TABLE {target} {word} TRIGGER ALL'
    return {
        'statement': statement, 'read_only': read_only, 'autocommit': False,
        'returns_rows': operation in {'count-rows', 'reset-statistics'},
        'maintenance': {'action': operation, 'object_kind': 'table', 'object': _name(native.get('name'), 'name'),
                        'options': [], 'transaction_mode': 'transaction'},
    }


def _server_operation(operation, draft):
    """One server-wide function call; the result row is the receipt."""
    from .native_admin import _literal
    if operation in {'inspect-configuration', 'alter-system-set', 'alter-system-reset', 'alter-system-reset-all'}:
        from .configuration import compile_operation as compile_cfg
        return compile_cfg(operation, {}, draft)
    if operation in {'inspect-prepared-transactions', 'resolve-prepared-transaction'}:
        from .prepared_transactions import compile_operation as compile_2pc
        return compile_2pc(operation, {}, draft)
    if operation == 'checkpoint':
        timeout=draft.get('wait_timeout_ms',30000)
        if type(timeout)is not int or not 1<=timeout<=600000:
            _refuse('Checkpoint wait timeout is 1–600000 milliseconds')
        return {'statement':'CHECKPOINT','read_only':False,'autocommit':True,'returns_rows':False,
                'maintenance':{'action':'checkpoint','object_kind':'server','object':None,'options':[],
                               'transaction_mode':'autocommit','wait_timeout_ms':timeout}}
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
    if kind == 'server' and operation in {'inspect-configuration', 'alter-system-set', 'alter-system-reset', 'alter-system-reset-all'}:
        from .configuration import form as cfg_form
        return cfg_form(operation, field)
    if kind == 'server' and operation in {'inspect-prepared-transactions', 'resolve-prepared-transaction'}:
        from .prepared_transactions import form as xact_form
        return xact_form(operation, field)
    if operation == 'attach-partition' and kind in {'index', 'partitioned-index'}:
        return {
            'form_id': f'postgresql-{kind}-attach-partition',
            'form_key': 'native:postgresql:schema:index',
            'title': 'Attach index partition',
            'fields': [
                field('child_schema', 'Partition index schema', help='Defaults to the parent index schema.'),
                field('child_index', 'Partition index name', required=True),
            ],
        }
    if operation in {'create-partition', 'attach-partition', 'detach-partition'}:
        from .partitions import form as partition_form
        return partition_form(operation, field)
    def boolean(name, label, **kw):
        return field(name, label, 'boolean', **kw)
    fields = []
    if operation == 'vacuum':
        fields = [boolean('full', 'Full (rewrite the table; exclusive lock)'),
                  boolean('freeze', 'Freeze row versions'),
                  boolean('analyze', 'Also analyze'),
                  boolean('verbose', 'Verbose'),
                  boolean('disable_page_skipping', 'Disable visibility-map page skipping'),
                  boolean('skip_locked', 'Skip relations that cannot be immediately locked'),
                  field('index_cleanup', 'Index cleanup mode', 'select', options=[
                      {'value': 'AUTO', 'label': 'Auto'},
                      {'value': 'ON', 'label': 'On'},
                      {'value': 'OFF', 'label': 'Off'},
                  ]),
                  boolean('process_main', 'Process main relation (PostgreSQL 16+)', default=True),
                  boolean('process_toast', 'Process TOAST table', default=True),
                  boolean('truncate', 'Truncate empty trailing pages'),
                  boolean('skip_database_stats', 'Skip updating pg_database frozen XID stats (PostgreSQL 16+)'),
                  *([boolean('only_database_stats', 'Update only pg_database frozen XID stats (PostgreSQL 16+)')]
                    if kind == 'database' else []),
                  field('buffer_usage_limit', 'Buffer usage limit (PostgreSQL 16+, e.g. 16MB or 0)'),
                  field('parallel', 'Parallel workers (not with Full)', 'number',
                        help='Leave empty to let the server decide; 0 disables parallel index vacuuming.')]
    elif operation == 'analyze':
        fields = [boolean('verbose', 'Verbose'),
                  boolean('skip_locked', 'Skip tables that cannot be locked'),
                  field('buffer_usage_limit', 'Buffer usage limit (PostgreSQL 16+, e.g. 8MB or 0)'),
                  *([field('columns', 'Selected columns (optional, comma-separated)')] if kind == 'table' else [])]
    elif operation in {'reindex', 'reindex-system'}:
        fields = [*([boolean('concurrently', 'Concurrently (cannot run in a transaction block)')]
                    if operation != 'reindex-system' else []),
                  boolean('verbose', 'Verbose'),
                  field('tablespace', 'Destination tablespace (optional)')]
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
    database = field('database', 'Database', 'reference', required=True, reference_kind='database',
                     reference_value='resource_id', help='Only the objects of this database are affected.')
    if operation == 'reassign-owned':
        fields = [database, field('new_owner', 'New owner', 'reference', required=True, reference_kind='role')]
    elif operation == 'drop-owned':
        fields = [database, boolean('cascade', 'Cascade to dependent objects'),
                  field('confirmation', 'Type the role name to confirm', required=True)]
    elif operation == 'move-objects':
        fields = [database,
                  field('object_type', 'Objects to move', 'select', default='all', options=[
                      {'value': 'all', 'label': 'Tables, indexes and materialized views'},
                      {'value': 'tables', 'label': 'Tables'}, {'value': 'indexes', 'label': 'Indexes'},
                      {'value': 'materialized-views', 'label': 'Materialized views'}]),
                  field('new_tablespace', 'New tablespace', 'reference', required=True, reference_kind='tablespace'),
                  field('owner', 'Only objects owned by', 'reference', reference_kind='role',
                        help='Leave empty to move every object in the tablespace.')]
    if operation=='checkpoint':fields=[field('wait_timeout_ms','Wait timeout (milliseconds)','number',default=30000,help='1–600000. Timeout/cancellation stops waiting; native checkpoint work may continue.') ]
    titles = {'checkpoint':'Checkpoint', 'vacuum': 'Vacuum', 'analyze': 'Analyze', 'reindex': 'Reindex',
              'reindex-system': 'Reindex system catalogs', 'cluster': 'Cluster',
              'truncate': 'Truncate', 'refresh': 'Refresh', 'reload': 'Reload configuration',
              'restore-point': 'Create restore point', 'wal-replay-pause': 'Pause WAL replay',
              'wal-replay-resume': 'Resume WAL replay', 'reassign-owned': 'Reassign owned objects',
              'drop-owned': 'Drop owned objects', 'move-objects': 'Move objects to another tablespace',
              'run-now': 'Run now', 'count-rows': 'Count rows', 'reset-statistics': 'Reset statistics',
              'enable-triggers': 'Enable all triggers', 'disable-triggers': 'Disable all triggers'}
    if kind in {'role', 'tablespace', 'pgagent-job'}:
        return {'form_id': f'postgresql-{kind}-{operation}', 'form_key': f'native:postgresql:server:{kind}',
                'title': titles[operation], 'fields': fields}
    if kind == 'server':
        return {'form_id': f'postgresql-server-{operation}', 'form_key': 'native:postgresql:server:server',
                'title': titles[operation], 'fields': fields}
    return {'form_id': f'postgresql-{kind}-{operation}', 'form_key': f'native:postgresql:schema:{kind}',
            'title': f'{titles[operation]} {kind.replace("-", " ")}', 'fields': fields}
