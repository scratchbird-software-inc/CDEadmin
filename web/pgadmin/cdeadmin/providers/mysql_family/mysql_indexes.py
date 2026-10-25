"""Native MySQL index definitions with typed key parts and owned execution."""
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import re

from ...sdk import RelationalClientError
from ...data_studio.language_tools import analyze
from .mysql_catalog import identifier as quote_identifier
from .mysql_instance import environment

KINDS = ('NORMAL', 'FULLTEXT', 'SPATIAL')
METHODS = ('DEFAULT', 'BTREE', 'HASH')
ALGORITHMS = ('DEFAULT', 'INPLACE', 'COPY')
LOCKS = ('DEFAULT', 'NONE', 'SHARED', 'EXCLUSIVE')
KEYS = {'name', 'parent', 'table', 'columns', 'unique', 'index_kind', 'method',
        'key_block_size', 'comment', 'visible', 'parser',
        'secondary_engine_attribute', 'algorithm', 'lock'}


def identifier(value):
    try:
        if isinstance(value, str): value.encode('utf8')
        return quote_identifier(value)
    except ValueError:
        raise RelationalClientError('Native identifier must be nonempty text without NUL') from None


def utf8_length(value):
    try:
        return len(value.encode('utf8'))
    except UnicodeError:
        raise RelationalClientError('Native index text must be valid UTF-8') from None


def path(value):
    value = value.split('.') if isinstance(value, str) else value
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 2:
        raise RelationalClientError('Select a table identifier path')
    for part in value:
        identifier(part)
    return list(value)


def expression(value, mode=None):
    if not isinstance(value, str) or not value.strip() or '\0' in value or utf8_length(value) > 65536:
        raise RelationalClientError('Index expression requires bounded SQL text')
    modes = (mode,) if mode is not None else ('', 'ANSI_QUOTES', 'NO_BACKSLASH_ESCAPES', 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES')
    for selected in modes:
        result = analyze('SELECT '+value+'\n', 'mysql-sql', script=True, settings={
            'ansi_quotes': 'ANSI_QUOTES' in selected.split(','),
            'no_backslash_escapes': 'NO_BACKSLASH_ESCAPES' in selected.split(','),
            'mysql_dollar_quotes': True})
        if not result['diagnostics'] and len(result['statements']) == 1 and not executable_comment(value, selected):
            return value
    raise RelationalClientError('Index expression has an unsafe native boundary')


def executable_comment(source, mode):
    """Recognize executable comments without mistaking literal text for SQL."""
    from ...data_studio.mysql_quoting import marker_at, end_of_quote
    modes = set(mode.split(',')); position = 0
    while position < len(source):
        char = source[position]
        if char in "'\"`":
            quote = char; position += 1
            while position < len(source):
                char = source[position]; position += 1
                if char == '\\' and quote != '`' and not (quote == '"' and 'ANSI_QUOTES' in modes) and 'NO_BACKSLASH_ESCAPES' not in modes:
                    position += 1
                elif char == quote:
                    if source[position:position+1] == quote: position += 1
                    else: break
        elif char == '$' and (marker := marker_at(source, position)):
            position = end_of_quote(source, position, marker) or len(source)
        elif char == '#' or source.startswith('--', position) and (position+2 == len(source) or source[position+2].isspace()):
            end = source.find('\n', position); position = len(source) if end < 0 else end+1
        elif source.startswith('/*!', position):
            return True
        elif source.startswith('/*', position):
            end = source.find('*/', position+2); position = len(source) if end < 0 else end+2
        else:
            position += 1
    return False


def structural_definition(source, mode):
    """Exclude only SHOW CREATE's unquoted table AUTO_INCREMENT counter."""
    modes = set(mode.split(',')); position = depth = 0; parts = []; start = 0
    while position < len(source):
        char = source[position]
        if char in "'\"`":
            quote = char; position += 1
            while position < len(source):
                char = source[position]; position += 1
                if char == '\\' and quote != '`' and not (quote == '"' and 'ANSI_QUOTES' in modes) and 'NO_BACKSLASH_ESCAPES' not in modes:
                    position += 1
                elif char == quote:
                    if source[position:position+1] == quote: position += 1
                    else: break
        elif source.startswith('/*!', position) and (version := re.match(r'/\*!([0-9]{5,6})\s', source[position:])) and int(version[1]) <= 90700:
            # SHOW CREATE emits versioned options whose SQL strings may
            # themselves contain */. Active comments contain ordinary SQL.
            position += version.end()
        elif source.startswith('/*', position):
            end = source.find('*/', position+2); position = len(source) if end < 0 else end+2
        elif char == '(':
            depth += 1; position += 1
        elif char == ')':
            depth -= 1; position += 1
        elif depth == 0 and (position == 0 or source[position-1].isspace()) and (match := re.match(r'AUTO_INCREMENT=[0-9]+\b', source[position:])):
            parts.extend((source[start:position], 'AUTO_INCREMENT=<runtime-counter>'))
            position += match.end(); start = position
        else:
            position += 1
    parts.append(source[start:])
    return hashlib.sha256(''.join(parts).encode('utf8')).hexdigest()


def compile_create(draft, mode=None):
    if not isinstance(draft, Mapping):
        raise RelationalClientError('Select structured index properties')
    draft = deepcopy(dict(draft)); options = draft.pop('options', {})
    if not isinstance(options, Mapping) or set(options)-KEYS:
        raise RelationalClientError('Unknown index option')
    for key, value in options.items():
        if key in draft and draft[key] != value:
            raise RelationalClientError('Conflicting index option: '+key)
        draft[key] = value
    if set(draft)-KEYS:
        raise RelationalClientError('Unknown index property')
    table = path(draft.get('table'))
    if draft.get('parent'):
        parent = path(draft['parent'])
        if len(parent) != 1 or len(table) == 2 and table[0] != parent[0]:
            raise RelationalClientError('Index database and owning table differ')
        if len(table) == 1:
            table = parent+table
    kind = draft.get('index_kind', 'NORMAL'); unique = draft.get('unique', False)
    method = draft.get('method', 'DEFAULT')
    if kind not in KINDS or type(unique) is not bool or method not in METHODS:
        raise RelationalClientError('Select index kind, uniqueness and method')
    if kind != 'NORMAL' and (unique or method != 'DEFAULT'):
        raise RelationalClientError('FULLTEXT and SPATIAL indexes do not accept UNIQUE or USING')
    rows = draft.get('columns')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 4096:
        raise RelationalClientError('Select ordered index key parts')
    parts = []
    for row in rows:
        row = {'name': row} if isinstance(row, str) else row
        if not isinstance(row, Mapping) or set(row)-{'name', 'expression', 'prefix_length', 'direction'}:
            raise RelationalClientError('Unknown index key-part property')
        name, body = row.get('name'), row.get('expression')
        if any(value is not None and not isinstance(value, str) for value in (name, body)):
            raise RelationalClientError('Key-part columns and expressions require text')
        if bool(name) == bool(body):
            raise RelationalClientError('Each key part requires a column or an expression')
        part = identifier(name) if name else '('+expression(body, mode)+'\n)'
        prefix = row.get('prefix_length')
        if prefix not in (None, ''):
            if not name or type(prefix) is not int or not 1 <= prefix <= 2147483647:
                raise RelationalClientError('Column prefix length requires a positive native integer')
            part += '('+str(prefix)+')'
        direction = row.get('direction', 'DEFAULT')
        if direction not in ('DEFAULT', 'ASC', 'DESC'):
            raise RelationalClientError('Select key-part ordering')
        if direction != 'DEFAULT':
            part += ' '+direction
        parts.append(part)
    source = 'CREATE '+('UNIQUE ' if unique else kind+' ' if kind != 'NORMAL' else '')+'INDEX '+identifier(draft.get('name'))
    if method != 'DEFAULT':
        source += ' USING '+method
    source += ' ON '+'.'.join(identifier(part) for part in table)+' ('+', '.join(parts)+')'
    parameters = []
    block = draft.get('key_block_size')
    if block not in (None, ''):
        if not isinstance(block, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,19})', block) or int(block) > 2**64-1:
            raise RelationalClientError('Key block size requires unsigned decimal text')
        source += ' KEY_BLOCK_SIZE='+block
    if 'comment' in draft:
        value = draft['comment']
        if not isinstance(value, str) or '\0' in value or utf8_length(value) > 65536:
            raise RelationalClientError('Index comment requires bounded text')
        source += ' COMMENT %s'; parameters.append(value)
    if 'visible' in draft:
        if type(draft['visible']) is not bool:
            raise RelationalClientError('Index visibility must be boolean')
        source += ' VISIBLE' if draft['visible'] else ' INVISIBLE'
    for key in ('secondary_engine_attribute',):
        if key not in draft:
            continue
        try:
            value = json.dumps(draft[key], ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        except (TypeError, ValueError):
            raise RelationalClientError('Engine attributes require a JSON value') from None
        if utf8_length(value) > 65536:
            raise RelationalClientError('Engine attributes exceed 64 KiB')
        source += ' '+key.upper()+'=%s'; parameters.append(value)
    if draft.get('parser'):
        if kind != 'FULLTEXT':
            raise RelationalClientError('Parser selection belongs to FULLTEXT indexes')
        source += ' WITH PARSER '+identifier(draft['parser'])
    for key, values in (('algorithm', ALGORITHMS), ('lock', LOCKS)):
        if key in draft:
            if draft[key] not in values:
                raise RelationalClientError('Select native index '+key)
            source += ' '+key.upper()+'='+draft[key]
    return {'statements': [{'source': source, 'parameters': tuple(parameters)}],
        'mysql_index_create': {'draft': draft, 'table': table},
        'warnings': ['Native DDL owns implicit commits. This operation uses its own connection and is never automatically replayed.',
            'Review binds observed identity and table definition; concurrent external DDL is not fenced. Native storage engines decide which index options they retain.']}


def observe(cursor, intent, mode):
    table = intent['table']
    if len(table) != 2:
        raise RelationalClientError('Select the database and owning table explicitly')
    cursor.execute('SHOW CREATE TABLE '+'.'.join(identifier(part) for part in table))
    row = cursor.fetchone()
    if not row or len(row) < 2 or not isinstance(row[1], str):
        raise RelationalClientError('Native table definition is unavailable')
    cursor.execute('SELECT SEQ_IN_INDEX,COLUMN_NAME,EXPRESSION,SUB_PART,COLLATION,INDEX_TYPE,IS_VISIBLE,INDEX_COMMENT '
        'FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s ORDER BY SEQ_IN_INDEX',
        (*table, intent['draft']['name']))
    return {'table_definition': row[1], 'table_structure_sha256': structural_definition(row[1], mode),
        'key_parts': [list(value) for value in cursor.fetchall()]}


def context(cursor):
    value = environment(cursor)
    cursor.execute('SELECT @@SESSION.sql_mode,DATABASE()')
    mode, database = cursor.fetchone()
    return {**value, 'sql_mode': mode, 'database': database}


def bind_review(client, planned):
    payload = planned['provider_payload']; intent = payload['compiled']['mysql_index_create']
    handle = client._connect({'route': payload['route']}); cursor = None
    try:
        handle.autocommit = True; cursor = handle.cursor(); identity = context(cursor)
        if len(intent['table']) == 1:
            if not identity['database']:
                raise RelationalClientError('Select a default database or a qualified owning table')
            intent['table'] = [identity['database'], *intent['table']]
        checked = compile_create(intent['draft'], identity['sql_mode'])
        before = observe(cursor, intent, identity['sql_mode'])
        intent['review'] = {'execution_identity': identity, 'before': before}
        planned['command_preview'].update(native_execution_identity=identity, native_index_observation=public(before))
        # Qualification of the actual mode precedes any native DDL. The SQL
        # remains the reviewed source; default database identity is also bound.
        if checked['statements'] != payload['compiled']['statements']:
            raise RelationalClientError('Index definition changed during native mode admission')
        return planned
    finally:
        if cursor is not None: client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('Index creation requires an independently owned connection')
    payload = request['provider_payload']; compiled = payload['compiled']; intent = compiled['mysql_index_create']
    review = intent.get('review')
    if not isinstance(review, Mapping):
        raise RelationalClientError('Review the native index before dispatch')
    checked = compile_create(intent['draft'], review['execution_identity']['sql_mode'])
    expected = checked['mysql_index_create']
    if len(expected['table']) == 1:
        expected['table'] = [review['execution_identity']['database'], *expected['table']]
    candidate = deepcopy(compiled); candidate['mysql_index_create'].pop('review', None)
    if checked != candidate:
        raise RelationalClientError('Reviewed index statement changed')
    handle = client._connect({'route': payload['route']}); cursor = None
    dispatched = acknowledged = False
    try:
        handle.autocommit = True; handle.get_warnings = True; handle.raise_on_warnings = False
        cursor = handle.cursor(); identity = context(cursor); before = observe(cursor, intent, identity['sql_mode'])
        expected_before = review['before']
        if (identity != review['execution_identity'] or before['table_structure_sha256'] != expected_before['table_structure_sha256'] or
                before['key_parts'] != expected_before['key_parts']):
            raise RelationalClientError('Native index identity or owning table changed since review')
        statement = compiled['statements'][0]; dispatched = True
        cursor.execute(statement['source'], statement['parameters'] or None); acknowledged = True
        warnings = [{'level': level, 'code': code, 'message': message} for level, code, message in (cursor.warnings or ())]
        after = observe(cursor, intent, identity['sql_mode'])
        return {'accepted': True, 'native_implicit_commit': True, 'commit_requested': False,
            'rollback_requested': False, 'staged_in_provider_session': False, 'automatic_retry': False,
            'native_warnings': warnings, 'driver_observation_only': True,
            'transaction_finality_interpreted_by_common_code': False,
            'index_observation': {'native_acknowledged': True, 'execution_identity': identity,
                'before': public(before), 'after': public(after), 'concurrent_external_ddl_fenced': False}}
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError('Native index creation failed ('+type(error).__name__+')')
        failure.native_dispatched = dispatched; failure.native_acknowledged = acknowledged; failure.automatic_retry = False
        failure.errno = getattr(error, 'errno', None); failure.sqlstate = getattr(error, 'sqlstate', None)
        raise failure from None
    finally:
        if cursor is not None: client._safe_close(cursor)
        client._forget_and_close(handle)


def public(observed):
    # The table may contain unrelated default literals or a sensitive remote
    # connection. Public index receipts contain scoped index facts and hashes.
    return {key: value for key, value in observed.items() if key != 'table_definition'}
