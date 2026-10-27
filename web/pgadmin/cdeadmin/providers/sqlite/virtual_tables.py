"""Structured constructors for SQLite's native creatable virtual modules.

Values are data, never SQL fragments. Module availability and constructor
constraints remain decisions of the selected native connection.
"""
from collections.abc import Mapping
import re

from pgadmin.cdeadmin.sdk import RelationalClientError


MODULES = ('fts3', 'fts4', 'fts5', 'rtree', 'rtree_i32', 'geopoly',
           'fts4aux', 'fts5vocab', 'fts3tokenize', 'dbstat')
KINDS = frozenset({'virtual-table', 'fts-table'})


def _error(message):
    raise RelationalClientError('SQLite virtual table: ' + message)


def _text(value):
    if not isinstance(value, str) or '\0' in value:
        _error('option values must be text without NUL characters')
    return value


def _literal(value):
    return "'" + _text(value).replace("'", "''") + "'"


def _identifier(value):
    if not _text(value) or len(value) > 1024:
        _error('column names must contain 1 to 1024 characters')
    return '"' + value.replace('"', '""') + '"'


def _strings(value, label):
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        _error(label + ' must be a list of strings')
    for item in value:
        _text(item)
    return value


def _tokenizer(value, *, fts5=False):
    if not isinstance(value, Mapping) or set(value) - {'name', 'arguments'}:
        _error('tokenizer requires name and optional arguments')
    name = value.get('name')
    if not isinstance(name, str) or not name or '\0' in name:
        _error('tokenizer name is required')
    args = _strings(value.get('arguments', []), 'tokenizer arguments')
    tokens = [name, *args]
    # Tokenizer grammars have their own quoting layer, inside the SQL module
    # argument. FTS5 parses a single string; FTS3/4 parse successive tokens.
    if fts5:
        return 'tokenize=' + _literal(' '.join(_literal(v) for v in tokens))
    return 'tokenize=' + ' '.join(_literal(v) for v in tokens)


def arguments(module, columns, options, *, schema='main'):
    if not isinstance(module, str) or module not in MODULES:
        _error('module has no structured native constructor')
    if not isinstance(options, Mapping):
        _error('module_options must be an object')
    if columns is None:
        columns = []
    if not isinstance(columns, list):
        _error('columns must be a list')
    allowed = {
        'fts3': {'tokenizer'},
        'fts4': {'tokenizer', 'prefix', 'matchinfo', 'compress', 'uncompress',
                 'order', 'content', 'languageid', 'notindexed'},
        'fts5': {'tokenizer', 'prefix', 'content', 'content_rowid', 'columnsize',
                 'detail', 'contentless_delete', 'contentless_unindexed',
                 'tokendata', 'locale'},
        'rtree': {'auxiliary_columns'}, 'rtree_i32': {'auxiliary_columns'},
        'geopoly': set(), 'fts4aux': {'table', 'database'},
        'fts5vocab': {'table', 'database', 'mode'},
        'fts3tokenize': {'tokenizer'}, 'dbstat': {'database'},
    }[module]
    if set(options) - allowed:
        _error('unknown options for ' + module + ': ' + ', '.join(sorted(set(options) - allowed)))
    if module in {'fts3', 'fts4', 'fts5', 'rtree', 'rtree_i32', 'geopoly'}:
        values = []
        for column in columns:
            if isinstance(column, Mapping) and module == 'fts5':
                if set(column) - {'name', 'unindexed'} or not isinstance(column.get('unindexed', False), bool):
                    _error('FTS5 columns accept name and boolean unindexed')
                values.append(_identifier(column.get('name')) + (' UNINDEXED' if column.get('unindexed') else ''))
            else:
                values.append(_identifier(column))
    else:
        if columns:
            _error(module + ' defines its own columns; leave columns empty')
        values = []
    if module in {'fts3', 'fts4', 'fts5'}:
        if 'tokenizer' in options:
            values.append(_tokenizer(options['tokenizer'], fts5=module == 'fts5'))
        if 'prefix' in options:
            prefix = options['prefix']
            if (not isinstance(prefix, list) or not prefix or any(
                    isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in prefix)):
                _error('prefix must be a nonempty list of positive integers')
            values.append('prefix=' + _literal((' ' if module == 'fts5' else ',').join(map(str, prefix))))
        for key in ('matchinfo', 'compress', 'uncompress', 'order', 'content', 'languageid', 'content_rowid', 'detail'):
            if key in options:
                values.append(key + '=' + _literal(options[key]))
        for key in ('columnsize', 'contentless_delete', 'contentless_unindexed', 'tokendata', 'locale'):
            if key in options:
                value = options[key]
                if isinstance(value, bool):
                    value = int(value)
                if not isinstance(value, int) or value not in (0, 1):
                    _error(key + ' must be 0 or 1')
                values.append(key + '=' + str(value))
        for column in _strings(options.get('notindexed', []), 'notindexed'):
            values.append('notindexed=' + _literal(column))
    elif module in {'rtree', 'rtree_i32'}:
        values.extend('+' + _identifier(v) for v in _strings(options.get('auxiliary_columns', []), 'auxiliary_columns'))
    elif module in {'fts4aux', 'fts5vocab'}:
        table = options.get('table')
        if not isinstance(table, str) or not table:
            _error(module + ' requires the source table name')
        if 'database' in options:
            database = options['database']
            _text(database)
            same_database = database.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')) == schema.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))
            if same_database:
                pass  # Both modules use the two-argument form in their own schema.
            elif module == 'fts4aux':
                # Native FTS4 copies this argument without dequoting. Its
                # cross-database constructor is only available in TEMP.
                if schema.casefold() != 'temp' or not isinstance(database, str) or re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', database) is None:
                    _error('cross-database fts4aux requires TEMP and an unquoted database identifier')
                values.append(database)
            else:
                if schema.lower() != 'temp':
                    _error('cross-database fts5vocab requires TEMP')
                values.append(_literal(database))
        values.append(_literal(table))
        if module == 'fts5vocab':
            mode = options.get('mode', 'row')
            if not isinstance(mode, str) or mode not in {'row', 'col', 'instance'}:
                _error('fts5vocab mode must be row, col or instance')
            values.append(_literal(mode))
    elif module == 'fts3tokenize':
        tokenizer = options.get('tokenizer', {'name': 'simple'})
        if not isinstance(tokenizer, Mapping) or set(tokenizer) - {'name', 'arguments'}:
            _error('tokenizer requires name and optional arguments')
        name = tokenizer.get('name')
        if not isinstance(name, str) or not name:
            _error('tokenizer name is required')
        values = [_literal(name), *(_literal(v) for v in _strings(tokenizer.get('arguments', []), 'tokenizer arguments'))]
    elif module == 'dbstat' and 'database' in options:
        values.append(_identifier(options['database']))
    return ', '.join(values)


def form(field, kind):
    return {
        'form_id': kind + '.create', 'title': 'Create SQLite virtual table',
        'fields': [
            field('name', 'Name', 'text', True),
            field('parent', 'Database', 'text', False, 'main, or a retained session database such as temp.', default='main'),
            field('module', 'Native module', 'select', True, options=MODULES, default='fts5'),
            field('columns', 'Module columns', 'json', False,
                  'FTS/spatial column names; FTS5 also accepts {"name":"body","unindexed":true}. '
                  'Geopoly lists auxiliary columns. Vocabulary, tokenizer and dbstat modules define their own columns.', default=['body']),
            field('module_options', 'Native constructor options', 'json', False,
                  'FTS: {"tokenizer":{"name":"unicode61","arguments":["remove_diacritics","2"]},"prefix":[2,3]}. '
                  'FTS4 tokenizer arguments use ["remove_diacritics=2"]. '
                  'FTS4 also accepts content, languageid, matchinfo, compress/uncompress, order and notindexed. '
                  'FTS5 accepts content, content_rowid, columnsize, detail, contentless_delete, contentless_unindexed, tokendata and locale. '
                  'RTree: {"auxiliary_columns":["label"]}. '
                  'FTS4aux/FTS5vocab: {"table":"search","database":"main","mode":"row"} (mode only for FTS5vocab; cross-database sources require TEMP). '
                  'Tokenizer: {"tokenizer":{"name":"unicode61","arguments":["remove_diacritics=2"]}}. '
                  'Dbstat: {"database":"main"}. Installed modules and all constructor constraints are checked by SQLite.', default={}),
        ],
    }


def apply_creation(client, request, connection=None):
    """Own a real SQLite DDL transaction, or stage in the caller's transaction."""
    payload = request['provider_payload']
    compiled = payload['compiled']
    target = compiled['sqlite_virtual_constructor']
    owned = connection is None
    if owned and target['schema'].casefold() != 'main':
        _error('TEMP and attached database creation require a retained session')
    connection = connection or client._connect({'route': payload['route']})
    started = False
    savepoint = None
    commit_started = False
    try:
        if not owned:
            client._require_idle(connection)
        if owned:
            connection.execute('BEGIN IMMEDIATE')
            started = True
        else:
            if not connection.in_transaction:
                connection.execute('BEGIN')
                started = True
            # Never release the outer transaction or an existing savepoint.
            import uuid
            savepoint = 'cde_virtual_' + uuid.uuid4().hex
            connection.execute('SAVEPOINT ' + savepoint)
        source = compiled['statements'][0]['source']
        connection.execute(source)
        schema = _identifier(target['schema'])
        row = connection.execute('SELECT sql FROM ' + schema + '.sqlite_schema WHERE name=? COLLATE NOCASE',
                                 (target['name'],)).fetchone()
        if row is None:
            _error('native constructor returned without a discoverable definition')
        ddl = row[0]
        columns = connection.execute('PRAGMA ' + schema + '.table_xinfo(' + _literal(target['name']) + ')').fetchall()
        if not columns:
            _error('native constructor returned without a column declaration')
        if savepoint:
            connection.execute('RELEASE ' + savepoint)
            savepoint = None
        if owned:
            commit_started = True
            connection.commit()
        return {
            'accepted': True, 'commit_requested': owned, 'rollback_requested': False,
            'driver_observation_only': True, 'transaction_finality_interpreted_by_common_code': False,
            'staged_in_provider_session': not owned,
            'native_virtual_table': {**target, 'ddl': ddl, 'columns': [
                {'name': row[1], 'native_type': row[2], 'hidden': row[6]} for row in columns]},
            'native_outcome': 'committed' if owned else 'staged',
        }
    except Exception as error:
        rollback_verified = False
        try:
            if savepoint:
                connection.execute('ROLLBACK TO ' + savepoint)
                connection.execute('RELEASE ' + savepoint)
            if started:
                connection.rollback()
            rollback_verified = not commit_started
        except Exception:
            pass
        failure = RelationalClientError('SQLite virtual-table creation failed: ' + str(error))
        failure.native_status_codes = [getattr(error, 'sqlite_errorcode')] if hasattr(error, 'sqlite_errorcode') else []
        failure.native_outcome = 'rolled_back' if rollback_verified else 'unknown_outcome'
        if not owned and not rollback_verified:
            client._uncertain.add(id(connection))
        raise failure from None
    finally:
        if owned:
            client._forget_and_close(connection)


def observe_creation(client, request):
    """Compare fresh native declarations with the original execution receipt."""
    target = request['provider_payload']['compiled']['sqlite_virtual_constructor']
    original = (request.get('provider_result') or {}).get('native_virtual_table')
    if not original:
        return {'confirmed': False, 'reason': 'native_creation_receipt_unavailable', 'automatic_retry': False}
    connection = request.get('_provider_session_handle')
    owned = connection is None
    connection = connection or client._connect({'route': request['provider_payload']['route']})
    try:
        if not owned:
            client._require_idle(connection)
        schema = _identifier(target['schema'])
        row = connection.execute('SELECT sql FROM ' + schema + '.sqlite_schema WHERE name=? COLLATE NOCASE', (target['name'],)).fetchone()
        columns = connection.execute('PRAGMA ' + schema + '.table_xinfo(' + _literal(target['name']) + ')').fetchall() if row else []
        observed = [{'name': item[1], 'native_type': item[2], 'hidden': item[6]} for item in columns]
        return {'confirmed': row is not None and row[0] == original['ddl'] and observed == original['columns'],
                'authority': 'sqlite-native-definition-and-columns', 'scope': 'retained-session' if not owned else 'independent-connection',
                'transaction_committed': None if not owned else True, 'automatic_retry': False}
    finally:
        if owned:
            client._forget_and_close(connection)
