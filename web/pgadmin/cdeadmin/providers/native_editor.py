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


class NativeTypeShapeLimit(ValueError):
    """A visible type exceeds this observation's bounded traversal."""


class NativeTypeBindingUnavailable(ValueError):
    """The companion cannot confirm the retained catalog's exact type."""


def duckdb_type_shape(native_type, budget, depth=0):
    if depth>32 or budget[0]<=0:
        raise NativeTypeShapeLimit('Native type observation limit')
    budget[0]-=1
    shape={'kind':native_type.id,'sql':str(native_type)}
    if native_type.id in {'struct','union'}:
        children=native_type.children
        if native_type.id=='struct' and children and all(not name for name,_child in children):
            shape['positions']=[duckdb_type_shape(child,budget,depth+1) for _name,child in children]
        else:
            shape['fields']=[{'name':name,'type':duckdb_type_shape(child,budget,depth+1)}
                for name,child in children if name]
    elif native_type.id in {'list','array','map'}:
        for name,child in native_type.children:
            if name=='size':shape['size']=child
            else:shape[name]=duckdb_type_shape(child,budget,depth+1)
    return shape


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
    type_parser = None
    context = {'engine': engine}
    cursor = handle if engine == 'duckdb' else (
        transaction.cursor() if engine == 'firebird' else handle.cursor())

    def query(name, sql, *, unavailable_view=False, unavailable_relation=False):
        try:
            cursor.execute(sql)
            if engine == 'sqlite' and cursor.description is None:
                observations.append({'section': name, 'available': False,
                                     'reason': 'native-result-unobserved'})
                return []
            rows = cursor.fetchmany(MAX_SYMBOLS + 1)
            observations.append({'section': name, 'available': True,
                                 'truncated': len(rows) > MAX_SYMBOLS})
            return rows[:MAX_SYMBOLS]
        except Exception as error:
            code = getattr(error, 'errno', None)
            if engine=='sqlite':
                import sqlite3
                native_code=getattr(error,'sqlite_errorcode',None)
                if (isinstance(error,sqlite3.Error) and type(native_code) is int and
                        (native_code & 255 == sqlite3.SQLITE_AUTH or
                         native_code & 255 == sqlite3.SQLITE_ERROR and (unavailable_view or unavailable_relation))):
                    observations.append({'section':name,'available':False,'error_code':native_code,
                        'error_name':getattr(error,'sqlite_errorname',None),'reason':
                        'native-authorization' if native_code & 255 == sqlite3.SQLITE_AUTH else
                        'native-view-binding' if unavailable_view else 'native-relation-binding'})
                    return []
            # Only native permission failures are incomplete metadata. A broken
            # transport/transaction or invalid query is never an empty section.
            if (code not in {1044, 1045, 1142, 1143, 1227} and
                    getattr(error, 'sqlcode', None) != -551 and getattr(error, 'sqlstate', None) != '28000'):
                raise RelationalClientError('Native editor metadata is unavailable (' + type(error).__name__ + ')') from None
            observations.append({'section': name, 'available': False, 'error_code': code})
            return []

    def add(kind, path, detail='', *, hidden_from_star=False, native_identifier_token=False, native_type=None, table_valued=False):
        nonlocal total, size
        path = [str(value).rstrip(' ') if engine == 'firebird' else str(value) for value in path]
        row = {'resource_kind': kind, 'display_path': path, 'display_name': path[-1], 'detail': str(detail)}
        if hidden_from_star:
            row['hidden_from_star'] = True
        if native_identifier_token:
            row['native_identifier_token'] = True
        if native_type is not None:
            row['native_type']=native_type
        if table_valued:
            row['table_valued'] = True
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
            import sqlite3
            context.update(version=sqlite3.sqlite_version, default_schema='main')
            context['database_config'] = {}
            for option in ('DEFENSIVE', 'DQS_DDL', 'DQS_DML', 'ENABLE_FKEY',
                           'ENABLE_QPSG', 'ENABLE_TRIGGER', 'LEGACY_ALTER_TABLE',
                           'TRUSTED_SCHEMA', 'WRITABLE_SCHEMA'):
                code = getattr(sqlite3, 'SQLITE_DBCONFIG_' + option, None)
                if code is None or not callable(getattr(handle, 'getconfig', None)):
                    observations.append({'section': 'database-config:' + option,
                        'available': False, 'reason': 'native-client-binding-unavailable'})
                else:
                    context['database_config'][option] = handle.getconfig(code)
                    observations.append({'section': 'database-config:' + option, 'available': True})
            databases = query('databases', 'PRAGMA database_list')
            context['search_path'] = ([row[1] for row in databases if row[1]=='temp'] +
                [row[1] for row in databases if row[1]!='temp'])
            native_relations = set(); masking_complete = {}
            for _ordinal, schema, _path in databases:
                add('schema', [schema])
                quoted = '"' + schema.replace('"', '""') + '"'
                raw_flags = query('table-flags:' + schema, f'PRAGMA {quoted}.table_list')
                if observations[-1]['available'] and not raw_flags:
                    observations[-1].update(available=False, reason='native-table-list-unobserved')
                flags_complete = observations[-1]['available'] and not observations[-1].get('truncated', False)
                table_flags = {row[1]: row for row in raw_flags if row[0] == schema}
                native_relations.update((schema, row[1]) for row in table_flags.values())
                relations = query('relations:' + schema, f'SELECT name,type FROM {quoted}.sqlite_schema WHERE type IN (\'table\',\'view\') ORDER BY name LIMIT 25001')
                if any(not isinstance(row[0], str) or not row[0] or row[1] not in {'table', 'view'} for row in relations):
                    observations[-1].update(available=False, reason='native-relation-identities-unobserved')
                    relations = [row for row in relations if isinstance(row[0], str) and row[0] and row[1] in {'table', 'view'}]
                relations_complete = observations[-1]['available'] and not observations[-1].get('truncated', False)
                masking_complete[schema] = flags_complete or relations_complete
                if not relations_complete and flags_complete:
                    relations = [(row[1], 'view' if row[2] == 'view' else 'table') for row in table_flags.values()]
                for name, kind in relations:
                    native_relations.add((schema, name))
                    add(kind, [schema, name])
                    table = '"' + name.replace('"', '""') + '"'
                    columns = query('columns:' + schema + ':' + name, f'PRAGMA {quoted}.table_xinfo({table})',
                                    unavailable_view=kind=='view',unavailable_relation=True)
                    column_observation = observations[-1]
                    if column_observation['available'] and not columns:
                        column_observation.update(available=False, reason='native-columns-unobserved')
                    for column in columns:
                        # Virtual-table hidden fields are excluded from star;
                        # generated columns (flags 2/3) remain in the projection.
                        add('column', [schema, name, column[1]], column[2], hidden_from_star=column[6] == 1)
                    flags = table_flags.get(name)
                    if (kind == 'table' and (not flags or not flags[4]) and column_observation['available'] and
                            not column_observation.get('truncated', False)):
                        from .sqlite.table_functions import rowid_observations
                        aliases = rowid_observations(cursor, schema, name, [
                            {'name': column[1], 'hidden': column[6]} for column in columns], table_valued=False)
                        observations.append({'section': 'row-identifiers:' + schema + ':' + name,
                            'available': all(row['available'] for row in aliases), 'native_aliases': aliases})
                        for alias in aliases:
                            if alias['available']:
                                add('column', [schema, name, alias['name']], 'INTEGER; native row identifier, not a durable application key', hidden_from_star=True)
            for name, builtin, kind, encoding, arity, flags in query('functions', 'PRAGMA function_list'):
                add('function', [name], f'{kind}({arity}); {encoding}; flags={flags}; builtin={builtin}')
            from .sqlite.table_functions import discover
            table_functions = discover(cursor, [row[1] for row in databases], native_relations, masking_complete=masking_complete)
            for function in table_functions:
                observations.append({'section': 'table-function:' + function['name'],
                    'available': function['observation_complete'], 'native_scopes': function['scopes']})
                for scope in function['scopes']:
                    if not scope['available']:
                        continue
                    paths = [[scope['schema'], function['name']]]
                    if function['unqualified_available'] and scope is function['scopes'][0]:
                        paths.append([function['name']])
                    for path in paths:
                        add('function', path, 'Native table-valued function', table_valued=True)
                        for column in scope['columns']:
                            add('column', [*path, column['name']], column['data_type'], hidden_from_star=column['hidden']==1)
                        for alias in scope.get('rowid_observations', []):
                            if alias['available']:
                                add('column', [*path, alias['name']], 'INTEGER; native virtual-table row identifier',
                                    hidden_from_star=True)
            for _ordinal, name in query('collations', 'PRAGMA collation_list'):
                add('collation', [name])
            context['compile_options'] = [row[0] for row in query('compile-options', 'PRAGMA compile_options')]
        elif engine == 'duckdb':
            version, database, schema = query('session', 'SELECT version(), current_database(), current_schema()')[0]
            context.update(version=version, default_schema=f'{database}.{schema}', catalog=database, schema=schema)
            context['search_path'] = query('search-path', "SELECT current_setting('search_path')")[0][0]
            context['extensions'] = [dict(zip(('name', 'loaded', 'installed', 'version', 'install_mode'), row))
                for row in query('extensions', 'SELECT extension_name,loaded,installed,extension_version,install_mode FROM duckdb_extensions() ORDER BY extension_name LIMIT 25001')]
            for database, schema in query('schemas', 'SELECT database_name,schema_name FROM duckdb_schemas() ORDER BY database_name,schema_name LIMIT 25001'):
                add('schema', [database, schema])
            storage = {name: kind for name, kind in query('databases', 'SELECT database_name,type FROM duckdb_databases()')}
            relations = query('relations', "SELECT database_name,schema_name,table_name,'table' FROM duckdb_tables() UNION ALL SELECT database_name,schema_name,view_name,'view' FROM duckdb_views() LIMIT 25001")
            for database, schema, name, kind in relations:
                add(kind, [database, schema, name])
            rowid_owners = {(database, schema, name) for database, schema, name, kind in relations
                            if kind == 'table' and storage.get(database) == 'duckdb'}
            nested_fields = 0
            type_budget=[MAX_SYMBOLS]
            native_columns=query('columns', 'SELECT database_name,schema_name,table_name,column_name,data_type FROM duckdb_columns() ORDER BY database_name,schema_name,table_name,column_index LIMIT 25001')
            columns_truncated=observations[-1]['truncated']
            for database, schema, table, name, data_type in native_columns:
                shape=None
                if str(data_type).lstrip().upper().startswith(('STRUCT(', 'UNION(', 'MAP(')) or str(data_type).rstrip().endswith(']'):
                    import duckdb
                    try:
                        # A failed DuckDB type-parser API call can abort its
                        # connection's transaction. Catalog facts remain on
                        # the retained session; parsing owns this companion.
                        if type_parser is None:type_parser=handle.cursor()
                        try:native_type=duckdb.sqltype(data_type,connection=type_parser)
                        except (duckdb.InvalidInputException,duckdb.ParserException,duckdb.CatalogException,duckdb.BinderException):
                            type_parser.close();type_parser=handle.cursor()
                            # Unnamed tuple types cannot roundtrip through the
                            # type-string parser. Bind observed identities on
                            # the companion and inspect types without fetching
                            # rows. Its committed catalog may be older/newer
                            # than the retained session; require exact shape.
                            quoted=lambda value:'"'+str(value).replace('"','""')+'"'
                            source='SELECT '+quoted(name)+' FROM '+'.'.join(map(quoted,(database,schema,table)))+' LIMIT 0'
                            bound=type_parser.sql(source).types
                            if len(bound)!=1 or str(bound[0])!=str(data_type):raise NativeTypeBindingUnavailable()
                            native_type=bound[0]
                        shape=duckdb_type_shape(native_type,type_budget)
                    except NativeTypeShapeLimit:
                        observations.append({'section':'nested-types:'+database+':'+schema+':'+table+':'+name,
                            'available':False,'truncated':True,'reason':'native-type-observation-limit'})
                    except (duckdb.InvalidInputException,duckdb.ParserException,duckdb.CatalogException,duckdb.BinderException,NativeTypeBindingUnavailable):
                        if type_parser is not None:type_parser.close();type_parser=None
                        observations.append({'section':'nested-fields:'+database+':'+schema+':'+table+':'+name,
                            'available':False,'reason':'native-type-binding'})
                add('column', [database, schema, table, name], data_type,native_type=shape)
                if shape is not None:
                    pending=[([database,schema,table,name],shape)]
                    while pending:
                        parent,native_type=pending.pop()
                        for field_entry in native_type.get('fields',[]):
                            field,field_type=field_entry['name'],field_entry['type']
                            if nested_fields>=MAX_SYMBOLS:
                                observations.append({'section':'nested-fields','available':True,'truncated':True})
                                pending.clear();break
                            field_path=[*parent,field]
                            add('field',field_path,field_type['sql'],native_type=field_type);nested_fields+=1
                            if field_type.get('fields'):pending.append((field_path,field_type))
                if str(name).translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')) == 'rowid':
                    rowid_owners.discard((database, schema, table))
            # Do not invent rowids on foreign extension storage or views.
            if not columns_truncated:
                for owner in sorted(rowid_owners):
                    add('column', [*owner, 'rowid'], 'BIGINT; native row identifier, not a durable application key',
                        hidden_from_star=True)
            functions = query('functions', 'SELECT database_name,schema_name,function_name,function_type,parameters,parameter_types,return_type,internal FROM duckdb_functions() ORDER BY database_name,schema_name,function_name LIMIT 25001')
            from .duckdb.editor_type_rules import aggregate_type_rules
            context['aggregate_type_rules'] = aggregate_type_rules(version, functions, observations[-1]['truncated'])
            for database, schema, name, kind, parameters, types, returns, _internal in functions:
                add('function', [database, schema, name], f'{kind} {parameters} {types} -> {returns}')
            for database, schema, name in query('types', 'SELECT database_name,schema_name,type_name FROM duckdb_types() ORDER BY database_name,schema_name,type_name LIMIT 25001'):
                add('type', [database, schema, name])
        else:
            context.update(version=str(handle.info.version), sql_dialect=dialect or handle.sql_dialect)
            identity=query('authentication','SELECT CURRENT_USER,CURRENT_ROLE FROM RDB$DATABASE')
            if len(identity)!=1:raise RelationalClientError('Native editor authentication context is unavailable')
            context.update(authenticated_principal=identity[0][0],active_role=identity[0][1])
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
                                     if row.get('reserved') or row.get('non_reserved') is False or row.get('category')=='reserved']
        if engine=='duckdb':
            # Native ColId admits unreserved and column-name keyword classes.
            # Preserve keyword display separately from identifier resolution.
            context['identifier_keywords']=[row['native_name'] for row in inv['lexical_rules']
                if row.get('category') in {'unreserved','column_name'}]
        elif engine=='sqlite':
            from .sqlite.identifier_keywords import observe
            native_keywords,native_observations=observe(handle,words)
            context.update(native_keywords);observations.extend(native_observations)
        context['context_revision'] = hashlib.sha256(json.dumps({'context':context,'resources':symbols,
            'observations':observations,'visible_resource_count':total}, sort_keys=True, default=str).encode()).hexdigest()
        truncated = total > len(symbols) or any(row.get('truncated') for row in observations)
        return {'context': context, 'resources': symbols, 'visible_resource_count': total,
                'observations': observations, 'truncated': truncated,
                'complete': not truncated and all(row.get('available', True) and not row.get('unavailable', False) for row in observations),
                'coverage': 'Native visible metadata on the retained session; denied, unavailable or truncated sections are incomplete.'}
    finally:
        if type_parser is not None:type_parser.close()
        if cursor is not handle:
            cursor.close()


def mysql_bind_markers(source, modes, *, dollar_quotes=False):
    """Replace driver placeholders outside quoted/comment spans without values."""
    from ..data_studio.mysql_quoting import parameter_spans
    output = list(source)
    for start, end, _name in parameter_spans(source, modes, dollar_quotes=dollar_quotes):
        output[start:end] = '?' + ' ' * (end - start - 1)
    return ''.join(output)


def validate_mysql(client, handle, source, engine, script=False):
    cursor = handle.cursor()
    previous_lock_timeout = None
    try:
        cursor.execute('SELECT VERSION(), @@sql_mode, @@SESSION.lock_wait_timeout')
        version, mode, previous_lock_timeout = cursor.fetchone()
        cursor.execute('SET SESSION lock_wait_timeout=2')
        modes = set(str(mode).upper().split(','))
        from ..data_studio.mysql_quoting import available
        dollar_quotes = engine == 'mysql' and available(version)
        result = analyze(source, engine + '-sql', script=script,
                         settings={'no_backslash_escapes': 'NO_BACKSLASH_ESCAPES' in modes,
                                   'ansi_quotes': 'ANSI_QUOTES' in modes,
                                   'mysql_dollar_quotes': dollar_quotes})
        if not script:
            # One native statement may contain compound/procedural semicolons
            # and mode-specific quoting that the client script framer rejects.
            result['diagnostics'] = []
            if '\x00' in source:
                result['diagnostics'] = [{'code': 'INVALID_SOURCE', 'message': 'SQL source contains NUL.',
                                          'severity': 'error', 'offset': source.index('\x00'), 'line': 1, 'column': 1}]
        result.update(authority=engine + '-native-prepare', parser_version=str(version),
                      sql_mode=str(mode), scope='Native SQL PREPARE only; no submitted SQL is executed. Quoted external-language bodies are not parsed by this SQL check. Context and permission failures leave grammar unconfirmed.')
        if result['diagnostics']: return result
        statements = result['statements'] if script else [{'source': source, 'start': 0, 'end': len(source), 'ordinal': 1}]
        valid = True if statements else None
        observations=[]
        for item in statements:
            name = 'sr_check_' + uuid.uuid4().hex
            acquired = False
            preparing=False
            marker = '%s' if engine == 'mysql' else '?'
            try:
                encoded = mysql_bind_markers(item['source'], modes, dollar_quotes=dollar_quotes).encode('utf8')
                cursor.execute(f'SET @{name} = CONVERT({marker} USING utf8mb4)', (encoded,))
                preparing=True
                cursor.execute(f'PREPARE {name} FROM @{name}')
                acquired = True
                observations.append({'ordinal':item['ordinal'],'native_preparation':'prepared','grammar_valid':True})
            except Exception as error:
                code = getattr(error, 'errno', None)
                if code is None or code in {2006, 2013, 2055}:
                    client._uncertain_sessions.add(id(handle))
                    raise RelationalClientError('Native editor connection state is unknown; close this session') from None
                from .mysql_family.prepare_classification import post_parse_family
                family=post_parse_family(item['source'],modes,version) if preparing and engine=='mysql' and code==1295 else None
                parsed=family is not None
                syntax=preparing and code in {1064,1149}
                observations.append({'ordinal':item['ordinal'],'native_preparation':'not_started' if not preparing else 'unsupported' if code==1295 else 'rejected',
                    'native_stage':'preparation' if preparing else 'source_binding',
                    'native_code':code,'grammar_valid':True if parsed else False if syntax else None,
                    **({'qualified_post_parse_family':family,'catalog_binding_validated':False} if parsed else {})})
                if not parsed:
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
        result['syntax_valid'] = valid
        result['native_statements']=observations
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
            if engine == 'mysql':
                from .mysql_family.mysql_completion import complete
                return {'editor_context': complete(self.client, handle)}
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
            if engine == 'mysql':
                from .mysql_family.mysql_native_validation import validate
                return validate(self.client, handle, source, request.get('script', False))
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
