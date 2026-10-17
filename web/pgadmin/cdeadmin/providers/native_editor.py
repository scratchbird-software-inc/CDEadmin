"""Retained native-session editor metadata and nonexecuting preparation.

All statements submitted by this module are fixed metadata queries or PREPARE.
User SQL is never executed. No interactive transaction is committed or rolled
back. Native context/permission failures are distinct from grammar rejection.
"""
from contextlib import contextmanager
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import uuid

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.data_studio.language_tools import analyze, LanguageToolError

MAX_SYMBOLS = 25000
MAX_BYTES = 4 * 1024 * 1024


def diagnostic_position(error, statement, start, source):
    """Use only numeric native positions; never return source-bearing messages."""
    matches = list(re.finditer(r'\b(?:at\s+)?line\s+(\d+)(?:,?\s+column\s+(\d+))?', str(error), re.I))
    lines = statement.splitlines(keepends=True)
    native_line, native_column = (int(matches[-1][1]), int(matches[-1][2] or 1)) if matches else (1, 1)
    native_line = max(1, min(native_line, len(lines) or 1))
    line_start = sum(len(line) for line in lines[:native_line - 1])
    text = lines[native_line - 1] if lines else ''
    exact = bool(matches and matches[-1][2]) and text.isascii()
    relative = line_start + min(max(native_column - 1, 0), len(text)) if exact else line_start
    offset = start + relative
    return {'offset': offset, 'offset_end': offset if exact else start + line_start + len(text.rstrip('\r\n')),
            'line': source.count('\n', 0, offset) + 1, 'column': offset - source.rfind('\n', 0, offset),
            'native_line': native_line, 'native_column': native_column, 'position_exact': exact}


@contextmanager
def session_access(client, handle, engine):
    if engine == 'firebird':
        with client._exclusive(handle):
            transaction = handle.main_transaction
            owned = not transaction.is_active()
            if owned:
                from firebird.driver import tpb, TraAccessMode, Isolation
                transaction = handle.transaction_manager(tpb(Isolation.READ_COMMITTED_RECORD_VERSION,
                    lock_timeout=2, access_mode=TraAccessMode.READ))
                transaction.begin()
            try:
                yield transaction
            finally:
                if owned:
                    try:
                        transaction.rollback()
                        transaction.close()
                    except Exception:
                        client._state(handle).result_cleanup_failed = True
                        raise RelationalClientError('Firebird editor transaction release is unconfirmed; close this session') from None
    elif engine in {'mysql', 'mariadb'}:
        with client._executions.lock:
            if client._executions.closing or not any(item is handle for item in client._connections):
                raise RelationalClientError('Native editor session is unavailable')
            client._executions.require_idle(handle)
            client._require_usable_session(handle)
            yield None
    else:
        with client._lock:
            client._require_idle(handle)
            yield None


@lru_cache(maxsize=5)
def inventory(engine):
    folder, version = {
        'mysql': ('mysql_family', '9_7_0'), 'mariadb': ('mysql_family', '12_2_2'),
        'sqlite': ('sqlite', '3_53_0'), 'duckdb': ('duckdb', '1_5_2'),
        'firebird': ('firebird', '5_0_4'),
    }[engine]
    data = json.loads((Path(__file__).parent / folder / f'{engine}_dialect_{version}.json').read_text())
    return data['inventories']


def metadata(handle, engine, transaction=None, dialect=None):
    symbols, observations, total, size = [], [], 0, 0
    context = {'engine': engine}
    cursor = handle if engine == 'duckdb' else (
        transaction.cursor() if engine == 'firebird' else handle.cursor())

    def query(name, sql, *, unavailable_view=False):
        try:
            cursor.execute(sql)
            rows = cursor.fetchmany(MAX_SYMBOLS + 1)
            observations.append({'section': name, 'available': True,
                                 'truncated': len(rows) > MAX_SYMBOLS})
            return rows[:MAX_SYMBOLS]
        except Exception as error:
            code = getattr(error, 'errno', None)
            if engine=='sqlite' and unavailable_view:
                import sqlite3
                native_code=getattr(error,'sqlite_errorcode',None)
                if isinstance(error,sqlite3.Error) and type(native_code) is int and native_code & 255 in {sqlite3.SQLITE_ERROR,sqlite3.SQLITE_AUTH}:
                    observations.append({'section':name,'available':False,'error_code':native_code,
                        'error_name':getattr(error,'sqlite_errorname',None),'reason':'native-view-binding'})
                    return []
            # Only native permission failures are incomplete metadata. A broken
            # transport/transaction or invalid query is never an empty section.
            if (code not in {1044, 1045, 1142, 1143, 1227} and
                    getattr(error, 'sqlcode', None) != -551 and getattr(error, 'sqlstate', None) != '28000'):
                raise RelationalClientError('Native editor metadata is unavailable (' + type(error).__name__ + ')') from None
            observations.append({'section': name, 'available': False, 'error_code': code})
            return []

    def add(kind, path, detail='', *, hidden_from_star=False, native_identifier_token=False):
        nonlocal total, size
        path = [str(value).rstrip(' ') if engine == 'firebird' else str(value) for value in path]
        row = {'resource_kind': kind, 'display_path': path, 'display_name': path[-1], 'detail': str(detail)}
        if hidden_from_star:
            row['hidden_from_star'] = True
        if native_identifier_token:
            row['native_identifier_token'] = True
        total += 1
        count = len(json.dumps(row, ensure_ascii=False).encode())
        if len(symbols) < MAX_SYMBOLS and size + count <= MAX_BYTES:
            size += count
            symbols.append(row)

    try:
        if engine in {'mysql', 'mariadb'}:
            state = query('session', 'SELECT VERSION(), DATABASE(), @@sql_mode, @@character_set_client, @@lower_case_table_names')[0]
            context.update(version=str(state[0]), default_schema=state[1], sql_mode=str(state[2]),
                           character_set_client=state[3], lower_case_table_names=int(state[4]))
            identity=query('authentication','SELECT CURRENT_USER(),CURRENT_ROLE()')
            if len(identity)!=1:raise RelationalClientError('Native editor authentication context is unavailable')
            context.update(authenticated_principal=identity[0][0],active_role=identity[0][1])
            for (database,) in query('databases', 'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA ORDER BY SCHEMA_NAME LIMIT 25001'):
                add('schema', [database])
            for database, table, kind in query('relations', 'SELECT TABLE_SCHEMA,TABLE_NAME,TABLE_TYPE FROM information_schema.TABLES ORDER BY (TABLE_SCHEMA=DATABASE()) DESC,TABLE_SCHEMA,TABLE_NAME LIMIT 25001'):
                add('view' if kind == 'VIEW' else 'table', [database, table])
            for database, table, column, native_type, extra in query('columns', 'SELECT TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,EXTRA FROM information_schema.COLUMNS ORDER BY (TABLE_SCHEMA=DATABASE()) DESC,TABLE_SCHEMA,TABLE_NAME,ORDINAL_POSITION LIMIT 25001'):
                add('column', [database, table, column], native_type,
                    hidden_from_star='INVISIBLE' in str(extra).upper().split())
            for database, routine, kind, native_type in query('routines', 'SELECT ROUTINE_SCHEMA,ROUTINE_NAME,ROUTINE_TYPE,DTD_IDENTIFIER FROM information_schema.ROUTINES ORDER BY (ROUTINE_SCHEMA=DATABASE()) DESC,ROUTINE_SCHEMA,ROUTINE_NAME,ROUTINE_TYPE LIMIT 25001'):
                add(kind.lower(), [database, routine], native_type or kind)
        elif engine == 'sqlite':
            context.update(version=query('version', 'SELECT sqlite_version()')[0][0], default_schema='main')
            databases = query('databases', 'PRAGMA database_list')
            for _ordinal, schema, _path in databases:
                add('schema', [schema])
                quoted = '"' + schema.replace('"', '""') + '"'
                table_flags = {row[1]: row for row in query('table-flags:' + schema, f'PRAGMA {quoted}.table_list')}
                for name, kind in query('relations:' + schema, f'SELECT name,type FROM {quoted}.sqlite_schema WHERE type IN (\'table\',\'view\') ORDER BY name LIMIT 25001'):
                    add(kind, [schema, name])
                    table = '"' + name.replace('"', '""') + '"'
                    columns = query('columns:' + schema + ':' + name, f'PRAGMA {quoted}.table_xinfo({table})',unavailable_view=kind=='view')
                    for column in columns:
                        # Virtual-table hidden fields are excluded from star;
                        # generated columns (flags 2/3) remain in the projection.
                        add('column', [schema, name, column[1]], column[2], hidden_from_star=column[6] == 1)
                    flags = table_flags.get(name)
                    names = {str(column[1]).translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))
                             for column in columns}
                    if kind == 'table' and flags and not flags[4] and not observations[-1]['truncated']:
                        for alias in ('rowid', '_rowid_', 'oid'):
                            if alias not in names:
                                add('column', [schema, name, alias], 'INTEGER; native row identifier, not a durable application key',
                                    hidden_from_star=True)
            for name, builtin, kind, encoding, arity, flags in query('functions', 'PRAGMA function_list'):
                add('function', [name], f'{kind}({arity}); {encoding}; flags={flags}; builtin={builtin}')
            for _ordinal, name in query('collations', 'PRAGMA collation_list'):
                add('collation', [name])
            context['compile_options'] = [row[0] for row in query('compile-options', 'PRAGMA compile_options')]
        elif engine == 'duckdb':
            version, database, schema = query('session', 'SELECT version(), current_database(), current_schema()')[0]
            context.update(version=version, default_schema=f'{database}.{schema}', catalog=database, schema=schema)
            for database, schema in query('schemas', 'SELECT database_name,schema_name FROM duckdb_schemas() ORDER BY database_name,schema_name LIMIT 25001'):
                add('schema', [database, schema])
            storage = {name: kind for name, kind in query('databases', 'SELECT database_name,type FROM duckdb_databases()')}
            relations = query('relations', "SELECT database_name,schema_name,table_name,'table' FROM duckdb_tables() UNION ALL SELECT database_name,schema_name,view_name,'view' FROM duckdb_views() LIMIT 25001")
            for database, schema, name, kind in relations:
                add(kind, [database, schema, name])
            rowid_owners = {(database, schema, name) for database, schema, name, kind in relations
                            if kind == 'table' and storage.get(database) == 'duckdb'}
            for database, schema, table, name, data_type in query('columns', 'SELECT database_name,schema_name,table_name,column_name,data_type FROM duckdb_columns() ORDER BY database_name,schema_name,table_name,column_index LIMIT 25001'):
                add('column', [database, schema, table, name], data_type)
                if str(name).translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')) == 'rowid':
                    rowid_owners.discard((database, schema, table))
            # Do not invent rowids on foreign extension storage or views.
            if not observations[-1]['truncated']:
                for owner in sorted(rowid_owners):
                    add('column', [*owner, 'rowid'], 'BIGINT; native row identifier, not a durable application key',
                        hidden_from_star=True)
            for database, schema, name, kind, parameters, types, returns in query('functions', 'SELECT database_name,schema_name,function_name,function_type,parameters,parameter_types,return_type FROM duckdb_functions() ORDER BY database_name,schema_name,function_name LIMIT 25001'):
                add('function', [database, schema, name], f'{kind} {parameters} {types} -> {returns}')
            for database, schema, name in query('types', 'SELECT database_name,schema_name,type_name FROM duckdb_types() ORDER BY database_name,schema_name,type_name LIMIT 25001'):
                add('type', [database, schema, name])
        else:
            context.update(version=str(handle.info.version), sql_dialect=dialect or handle.sql_dialect)
            relations = query('relations', 'SELECT RDB$RELATION_NAME,CASE WHEN RDB$VIEW_BLR IS NULL THEN 0 ELSE 1 END FROM RDB$RELATIONS')
            for name, view in relations:
                add('view' if view else 'table', [name])
            column_names = set()
            for relation, name in query('columns', 'SELECT RDB$RELATION_NAME,RDB$FIELD_NAME FROM RDB$RELATION_FIELDS ORDER BY RDB$RELATION_NAME,RDB$FIELD_POSITION'):
                add('column', [relation, name])
                column_names.add((relation.rstrip(' '), name.rstrip(' ')))
            if not observations[-1]['truncated']:
                for name, view in relations:
                    if not view and (name.rstrip(' '), 'RDB$DB_KEY') not in column_names:
                        add('column', [name, 'RDB$DB_KEY'], 'Native binary record identifier, not a durable application key',
                            hidden_from_star=True, native_identifier_token=True)
            for catalog, field, kind in (
                    ('RDB$PROCEDURES', 'RDB$PROCEDURE_NAME', 'procedure'),
                    ('RDB$FUNCTIONS', 'RDB$FUNCTION_NAME', 'function')):
                for package, name in query(kind, f'SELECT RDB$PACKAGE_NAME,{field} FROM {catalog} WHERE RDB$PACKAGE_NAME IS NULL OR COALESCE(RDB$PRIVATE_FLAG,1)=0'):
                    add(kind, [package, name] if package else [name])
            for catalog, field, kind in (
                    ('RDB$PACKAGES', 'RDB$PACKAGE_NAME', 'package'),
                    ('RDB$GENERATORS', 'RDB$GENERATOR_NAME', 'sequence'),
                    ('RDB$FIELDS', 'RDB$FIELD_NAME', 'domain'),
                    ('RDB$EXCEPTIONS', 'RDB$EXCEPTION_NAME', 'exception'),
                    ('RDB$COLLATIONS', 'RDB$COLLATION_NAME', 'collation')):
                for (name,) in query(kind, f'SELECT {field} FROM {catalog}'):
                    add(kind, [name])
        inv = inventory(engine)
        words = [row['native_name'] for row in inv['lexical_rules'] if re.fullmatch(r'[A-Za-z][A-Za-z0-9_$]*', row['native_name'])]
        if engine in {'mysql', 'mariadb'}:
            for group, kind in (('functions', 'function'), ('data_types', 'type')):
                for row in inv[group]:
                    if re.fullmatch(r'[A-Za-z][A-Za-z0-9_$]*', row['native_name']):
                        add(kind, [row['native_name']], 'native ' + kind)
        context['keywords'] = ' '.join(words)
        context['reserved_words'] = [row['native_name'] for row in inv['lexical_rules']
                                     if row.get('reserved') or row.get('non_reserved') is False]
        context['context_revision'] = hashlib.sha256(json.dumps({'context':context,'resources':symbols,
            'observations':observations,'visible_resource_count':total}, sort_keys=True, default=str).encode()).hexdigest()
        return {'context': context, 'resources': symbols, 'visible_resource_count': total,
                'observations': observations, 'truncated': total > len(symbols) or any(row.get('truncated') for row in observations),
                'coverage': 'Native visible metadata on the retained session; denied, unavailable or truncated sections are incomplete.'}
    finally:
        if cursor is not handle:
            cursor.close()


def mysql_bind_markers(source, modes):
    """Replace driver placeholders outside quoted/comment spans without values."""
    output, i, quote, comment = list(source), 0, None, None
    while i < len(source):
        c, pair = source[i], source[i:i + 2]
        if comment:
            if comment == 'line' and c == '\n': comment = None
            elif comment == 'block' and pair == '*/': comment = None; i += 1
        elif quote:
            if c == '\\' and 'NO_BACKSLASH_ESCAPES' not in modes: i += 1
            elif c == quote:
                if source[i + 1:i + 2] == quote: i += 1
                else: quote = None
        elif c in "'\"`": quote = c
        elif c == '#' or pair == '--' and (i + 2 == len(source) or source[i + 2].isspace()): comment = 'line'
        elif pair == '/*': comment = 'block'; i += 1
        elif c == '%':
            match = re.match(r'%(?:s|\([A-Za-z_][A-Za-z0-9_]*\)s)', source[i:])
            if match:
                output[i:i + len(match[0])] = '?' + ' ' * (len(match[0]) - 1)
                i += len(match[0]) - 1
        i += 1
    return ''.join(output)


def validate_mysql(client, handle, source, engine, script=False):
    cursor = handle.cursor()
    previous_lock_timeout = None
    try:
        cursor.execute('SELECT VERSION(), @@sql_mode, @@SESSION.lock_wait_timeout')
        version, mode, previous_lock_timeout = cursor.fetchone()
        cursor.execute('SET SESSION lock_wait_timeout=2')
        modes = set(str(mode).upper().split(','))
        result = analyze(source, engine + '-sql', script=script,
                         settings={'no_backslash_escapes': 'NO_BACKSLASH_ESCAPES' in modes})
        if not script:
            # One native statement may contain compound/procedural semicolons
            # and mode-specific quoting that the client script framer rejects.
            result['diagnostics'] = []
            if '\x00' in source:
                result['diagnostics'] = [{'code': 'INVALID_SOURCE', 'message': 'SQL source contains NUL.',
                                          'severity': 'error', 'offset': source.index('\x00'), 'line': 1, 'column': 1}]
        result.update(authority=engine + '-native-prepare', parser_version=str(version),
                      sql_mode=str(mode), scope='Native PREPARE only; no submitted SQL is executed. Context and permission failures leave grammar unconfirmed.')
        if result['diagnostics']: return result
        statements = result['statements'] if script else [{'source': source, 'start': 0, 'end': len(source), 'ordinal': 1}]
        valid = True
        for item in statements:
            name = 'sr_check_' + uuid.uuid4().hex
            acquired = False
            marker = '%s' if engine == 'mysql' else '?'
            try:
                encoded = mysql_bind_markers(item['source'], modes).encode('utf8')
                cursor.execute(f'SET @{name} = CONVERT({marker} USING utf8mb4)', (encoded,))
                cursor.execute(f'PREPARE {name} FROM @{name}')
                acquired = True
            except Exception as error:
                code = getattr(error, 'errno', None)
                if code is None or code in {2006, 2013, 2055}:
                    client._uncertain_sessions.add(id(handle))
                    raise RelationalClientError('Native editor connection state is unknown; close this session') from None
                # These exact MySQL routine/view/database paths have independently
                # qualified post-parse 1295 refusals in the schema adapter.
                parsed = engine == 'mysql' and code == 1295 and re.match(
                    r'^\s*(?:CREATE|ALTER|DROP)\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION|TRIGGER|VIEW|DATABASE)\b', item['source'], re.I)
                if not parsed:
                    syntax = code in {1064, 1149}
                    valid = False if syntax else (None if valid is not False else False)
                    result['diagnostics'].append({'code': 'NATIVE_SYNTAX' if syntax else 'NATIVE_CONTEXT',
                        'native_code': code, 'message': 'Native parser rejected the SQL syntax.' if syntax else 'Native preparation requires valid catalog context and privileges.',
                        'severity': 'error' if syntax else 'warning',
                        **diagnostic_position(error, item['source'], item['start'], source)})
            finally:
                try:
                    if acquired: cursor.execute(f'DEALLOCATE PREPARE {name}')
                    cursor.execute(f'SET @{name} = NULL')
                except Exception:
                    client._uncertain_sessions.add(id(handle))
                    raise RelationalClientError('Native prepared-statement release is unconfirmed; close this session') from None
        result['grammar_valid'] = valid
        result['syntax_valid'] = valid is not False
        result['statements'] = statements
        result['script_ready'] = script and valid is not False and bool(statements)
        return result
    finally:
        try:
            if previous_lock_timeout is not None:
                cursor.execute('SET SESSION lock_wait_timeout=' + str(int(previous_lock_timeout)))
        except Exception:
            client._uncertain_sessions.add(id(handle))
            raise RelationalClientError('Native editor settings restoration is unconfirmed; close this session') from None
        finally:
            cursor.close()


class NativeEditorProvider:
    """Mixin for native relational providers with shared editor contributions."""

    def source_tooling(self, language_profile):
        if language_profile != self.profile.language_profile:
            raise RelationalClientError('Native editor language changed')
        engine = self.profile.engine_id
        return {'validation_authority': engine + ('-native-prepare' if engine in {'mysql', 'mariadb', 'firebird'} else '-native-parser' if engine == 'duckdb' else '-native-compilation'),
                'native_validation_available': True, 'nonexecuting': True}

    @staticmethod
    def _native_editor_completion(binding, request):
        return binding.instance.complete(request)

    def data_studio_contributions(self):
        from pgadmin.cdeadmin.data_studio import CompletionContribution
        result = super().data_studio_contributions()
        result['completions'] = (CompletionContribution(
            self.profile.engine_id + '.native-editor.completion', frozenset({self.profile.language_profile}),
            NativeEditorProvider._native_editor_completion),)
        return result

    def _editor_session(self, request):
        self._require('data_read', 'resource')
        session = self._sessions.get(request.get('session_id'))
        if session is None:
            raise RelationalClientError('Native editor session is unavailable')
        return session.handle

    def complete(self, request):
        handle = self._editor_session(request)
        engine = self.profile.engine_id
        with session_access(self.client, handle, engine) as transaction:
            return {'editor_context': metadata(handle, engine, transaction, request.get('client_sql_dialect'))}

    def capture_session_catalog(self, request):
        engine=self.profile.engine_id
        if engine not in {'sqlite','duckdb'} or request.get('language_profile')!=self.profile.language_profile:
            raise RelationalClientError('Retained catalog is unavailable for this native language')
        include_system=request.get('include_system',False)
        if type(include_system) is not bool:raise RelationalClientError('Invalid native system-object selection')
        handle=self._editor_session(request)
        from .embedded_session_catalog import sqlite_catalog,duckdb_catalog
        with session_access(self.client,handle,engine):
            return (sqlite_catalog if engine=='sqlite' else duckdb_catalog)(self.client,handle,
                request['session_id'],include_system=include_system)

    def validate_source_without_execution(self, request):
        if request.get('language_profile') != self.profile.language_profile:
            raise RelationalClientError('Native editor language changed')
        source = request.get('source')
        if not isinstance(source, str) or len(source.encode()) > 2 * 1024 * 1024:
            raise LanguageToolError('Source must be text no larger than 2 MiB')
        handle = self._editor_session(request)
        engine = self.profile.engine_id
        with session_access(self.client, handle, engine) as transaction:
            if engine in {'mysql', 'mariadb'}:
                return validate_mysql(self.client, handle, source, engine, request.get('script', False))
            if engine != 'firebird':
                raise RelationalClientError('This provider owns its native validator')
            from .firebird.query_dialect import DialectCursor
            dialect = request.get('client_sql_dialect', handle.sql_dialect)
            if type(dialect) is not int or dialect not in {1, 2, 3}:
                raise LanguageToolError('Firebird statement dialect must be 1, 2 or 3')
            result = {'language_profile': 'firebird-sql', 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                'authority': 'firebird-native-prepare', 'parser_version': str(handle.info.version),
                'client_sql_dialect': dialect, 'grammar_valid': None, 'syntax_valid': False,
                'script_ready': False, 'diagnostics': [], 'statements': [],
                'scope': 'Firebird native DSQL/PSQL preparation only; no submitted statement is executed.'}
            script = request.get('script', False)
            if script:
                from .firebird.scripts import parse, ScriptPreflightError
                try:
                    entries = parse(source)
                except ScriptPreflightError as error:
                    result['diagnostics'] = [{'code': 'SCRIPT_FRAMING', 'severity': 'error', 'message': str(error),
                                              'offset': 0, 'line': 1, 'column': 1, 'position_exact': False}]
                    return result
                statements = []
                for entry in entries:
                    if entry.kind == 'dialect': dialect = entry.value
                    if entry.kind == 'sql':
                        statements.append({'ordinal': len(statements) + 1, 'source': entry.source,
                                           'start': entry.offset, 'end': entry.offset + len(entry.source), 'client_sql_dialect': dialect})
            else:
                statements = [{'ordinal': 1, 'source': source, 'start': 0, 'end': len(source), 'client_sql_dialect': dialect}]
            valid = True
            for item in statements:
                cursor = DialectCursor(handle, item['client_sql_dialect'])
                try:
                    cursor.prepare(item['source'], transaction)
                except Exception as error:
                    if str(getattr(error, 'sqlstate', '')).startswith('08'):
                        self.client._state(handle).attachment_liveness_failed = True
                        raise RelationalClientError('Firebird editor connection was lost; close this session') from None
                    syntax = getattr(error, 'sqlcode', None) == -104
                    valid = False if syntax else None if valid is not False else False
                    result['diagnostics'].append({'code': 'FIREBIRD_SYNTAX' if syntax else 'FIREBIRD_CONTEXT',
                        'message': 'Firebird parser rejected the SQL syntax.' if syntax else 'Native preparation requires valid catalog context and privileges.',
                        'severity': 'error' if syntax else 'warning', **diagnostic_position(error, item['source'], item['start'], source)})
                finally:
                    try: cursor.close()
                    except Exception:
                        state = self.client._state(handle)
                        state.result_cleanup_failed = True
                        state.failed_cursors.append(cursor)
                        raise RelationalClientError('Firebird preparation release is unconfirmed; close this session') from None
            result.update(grammar_valid=valid if statements else None, syntax_valid=valid is True and bool(statements),
                          statements=statements, script_ready=script and valid is not False and bool(statements))
            return result
