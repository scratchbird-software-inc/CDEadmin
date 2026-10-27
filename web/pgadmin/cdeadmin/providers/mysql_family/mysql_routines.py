"""Typed Community stored routines; no application replacement semantics."""
from collections.abc import Mapping
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from ...sdk import RelationalClientError
from ...data_studio.language_tools import analyze
from ..mysql_views import _account_part
from .mysql_indexes import context, identifier, executable_comment, utf8_length

KINDS = {'procedure', 'function'}
ACCESS = ('CONTAINS SQL', 'NO SQL', 'READS SQL DATA', 'MODIFIES SQL DATA')
SECURITY = ('DEFINER', 'INVOKER')
KEYS = {'name', 'parent', 'database', 'body', 'definition', 'parameters',
        'return_parameters', 'returns', 'deterministic', 'data_access',
        'sql_security', 'definer_user', 'definer_host', 'comment', 'if_not_exists',
        'language'}


def text(value, label, maximum=65535):
    if not isinstance(value, str) or '\0' in value or utf8_length(value) > maximum:
        raise RelationalClientError(label+' requires bounded UTF-8 text')
    return value


@lru_cache(maxsize=1)
def type_names():
    data = json.loads((Path(__file__).parent/'mysql_dialect_9_7_0.json').read_text())
    return sorted({row['native_name'] for row in data['inventories']['data_types']}, key=len, reverse=True)


def type_text(value, mode):
    """Bound a native type slot; MySQL still owns type grammar and semantics."""
    value = text(value, 'Routine type', 65535).strip()
    base = next((name for name in type_names()
                 if re.match(r'^'+r'\s+'.join(map(re.escape, name.split()))+r'(?=\s|\(|$)', value, re.I)), None)
    if base is None:
        raise RelationalClientError('Select a native MySQL type')
    matched = re.match(r'^'+r'\s+'.join(map(re.escape, base.split())), value, re.I)
    rest = value[matched.end():].strip()
    # At most one argument list. Literals are consumed before looking for
    # separators, so ENUM/SET punctuation cannot become routine syntax.
    if rest.startswith('('):
        pos = 1
        while pos < len(rest):
            char = rest[pos]
            if char in "'\"":
                quote = char; pos += 1
                while pos < len(rest):
                    char = rest[pos]; pos += 1
                    if char == '\\' and 'NO_BACKSLASH_ESCAPES' not in mode.split(','):
                        pos += 1
                    elif char == quote:
                        if rest[pos:pos+1] == quote: pos += 1
                        else: break
                else: raise RelationalClientError('Unterminated native type literal')
            elif char == ')':
                rest = rest[pos+1:].strip(); break
            elif char.isdigit() or char.isspace() or char in ',+-.':
                pos += 1
            else:
                raise RelationalClientError('Routine type arguments have an unsafe boundary')
        else: raise RelationalClientError('Unterminated native type arguments')
    # Native spelling/argument validity belongs to MySQL. Only native type
    # modifiers and named charset/collation slots can follow the base type.
    suffix = r'(?:(?:UNSIGNED|SIGNED|ZEROFILL|ASCII|UNICODE|BINARY)|(?:CHARACTER\s+SET|CHARSET|COLLATE)\s+[A-Za-z0-9_]+)'
    if rest and not re.fullmatch(suffix+r'(?:\s+'+suffix+r')*', rest, re.I):
        raise RelationalClientError('Routine type modifiers have an unsafe boundary')
    return value


def compile_create(kind, draft, mode=None):
    if mode is None:
        failure = None
        for candidate in ('', 'ANSI_QUOTES', 'NO_BACKSLASH_ESCAPES', 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'):
            try:
                return compile_create(kind, draft, candidate)
            except RelationalClientError as error:
                failure = error
        raise failure
    if kind not in KINDS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a native stored routine')
    draft = deepcopy(dict(draft)); options = draft.pop('options', {})
    if not isinstance(options, Mapping) or set(options) & set(draft):
        raise RelationalClientError('Ambiguous native routine options')
    draft.update(options)
    for alias, canonical in (('definition', 'body'), ('parent', 'database')):
        if alias in draft:
            if canonical in draft: raise RelationalClientError('Ambiguous native routine field')
            draft[canonical] = draft.pop(alias)
    if set(draft)-KEYS:
        raise RelationalClientError('Unknown native routine option')
    database = draft.get('database')
    if isinstance(database, list) and len(database) == 1: database = database[0]
    qualified = identifier(database)+'.'+identifier(draft.get('name'))
    selected_mode = mode if mode is not None else ''
    params = draft.get('parameters', [])
    if not isinstance(params, list) or len(params)>4096:
        raise RelationalClientError('Routine parameters require ordered records')
    if draft.get('return_parameters'):
        raise RelationalClientError('Procedure outputs belong in parameters with OUT or INOUT mode')
    declarations = []
    for item in params:
        if not isinstance(item, Mapping) or set(item)-{'name', 'type', 'mode', 'character_set', 'collation'}:
            raise RelationalClientError('Unknown native routine parameter option')
        direction = item.get('mode', 'IN')
        if direction not in {'IN', 'OUT', 'INOUT'} or kind=='function' and direction!='IN':
            raise RelationalClientError('Functions accept input parameters; procedures accept IN, OUT and INOUT')
        declaration = (direction+' ' if kind=='procedure' else '')+identifier(item.get('name'))+' '+type_text(item.get('type'), selected_mode)
        for key, prefix in (('character_set', ' CHARACTER SET '), ('collation', ' COLLATE ')):
            if key in item:
                value = item[key]
                if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_]+', value):
                    raise RelationalClientError('Parameter character set/collation requires a native name')
                declaration += prefix+value
        declarations.append(declaration)
    body = text(draft.get('body'), 'Routine body', 1024*1024).strip()
    if not body: raise RelationalClientError('Routine body is required')
    source = 'CREATE '
    if 'definer_user' in draft or 'definer_host' in draft:
        source += 'DEFINER='+_account_part(draft.get('definer_user'),32)+'@'+_account_part(draft.get('definer_host'),255)+' '
    exists = draft.get('if_not_exists', False)
    if type(exists) is not bool: raise RelationalClientError('IF NOT EXISTS must be boolean')
    source += kind.upper()+' '+('IF NOT EXISTS ' if exists else '')+qualified+' ('+', '.join(declarations)+')'
    if kind=='function': source += ' RETURNS '+type_text(draft.get('returns'), selected_mode)
    elif draft.get('returns'): raise RelationalClientError('Procedures do not declare a scalar return type')
    if 'language' in draft:
        if draft['language']!='SQL': raise RelationalClientError('Non-SQL runtime integration is outside this Community profile')
        source += ' LANGUAGE SQL'
    deterministic = draft.get('deterministic')
    if 'deterministic' in draft:
        if type(deterministic) is not bool: raise RelationalClientError('Deterministic must be boolean')
        source += ' DETERMINISTIC' if deterministic else ' NOT DETERMINISTIC'
    for key, values, prefix in (('data_access', ACCESS, ' '), ('sql_security', SECURITY, ' SQL SECURITY ')):
        if key in draft:
            if draft[key] not in values: raise RelationalClientError('Select a native routine characteristic')
            source += prefix+draft[key]
    parameters = (); parser_source = source
    if 'comment' in draft:
        parameters = (text(draft['comment'], 'Routine comment'),)
        source += ' COMMENT %s'
        parser_source += " COMMENT ''"
    source += '\n'+body
    parser_source += '\n'+body
    modes = (mode,) if mode is not None else ('', 'ANSI_QUOTES', 'NO_BACKSLASH_ESCAPES', 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES')
    for candidate in modes:
        parsed = analyze(source+'\n', 'mysql-sql', script=False, settings={
            'ansi_quotes': 'ANSI_QUOTES' in candidate.split(','),
            'no_backslash_escapes': 'NO_BACKSLASH_ESCAPES' in candidate.split(','),
            'mysql_dollar_quotes': True})
        if not parsed['diagnostics'] and not executable_comment(source,candidate):
            break
    else: raise RelationalClientError('Routine body must contain one lexically complete native definition')
    return {'statements': [{'source': source, 'parameters': parameters, 'parser_source': parser_source}],
        'mysql_routine_create': {'kind': kind, 'draft': draft, 'path': [database, draft['name']]},
        'warnings': ['Native routine creation uses an independent connection and is never automatically replayed. Review does not fence concurrent external DDL.']}


def observe(cursor, intent):
    cursor.execute('SELECT ROUTINE_TYPE,ROUTINE_DEFINITION,IS_DETERMINISTIC,SQL_DATA_ACCESS,SECURITY_TYPE,DEFINER,ROUTINE_COMMENT,CAST(SQL_MODE AS CHAR),CHARACTER_SET_CLIENT,COLLATION_CONNECTION,DATABASE_COLLATION '
        'FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_NAME=%s AND ROUTINE_TYPE=%s',
        (*intent['path'], intent['kind'].upper()))
    rows = [list(row) for row in cursor.fetchall()]
    # Do not expose an existing same-name body/default literals in a preview.
    digest = hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode('utf8')).hexdigest()
    return {'present': bool(rows), 'definition_sha256': digest,
            'definition_visibility': 'unavailable' if any(row[1] is None for row in rows) else 'visible' if rows else 'absent'}


def check_grammar(client, compiled, mode):
    from .mysql_parser import library, native
    try:
        path = library(client)
    except OSError:
        path = None
    if path is None:
        raise RelationalClientError('Routine review requires the registered MySQL9.7 Shell native grammar library; no DDL was executed')
    result = native(path, [{'source': compiled['statements'][0]['parser_source'], 'sql_mode': mode}])
    if not result['statements'][0]['sql_syntax_valid']:
        raise RelationalClientError('Native MySQL grammar rejected the routine definition; no DDL was executed')
    return {'library_sha256': result['library_sha256'], 'worker_sha256': result['worker_sha256'],
            'parser_version': result['parser_version'], 'sql_executed': False}


def bind_review(client, planned):
    compiled = planned['provider_payload']['compiled']; intent = compiled['mysql_routine_create']
    handle = client._connect({'route': planned['provider_payload']['route']}); cursor = None
    try:
        handle.autocommit = True; cursor = handle.cursor(); identity = context(cursor)
        checked = compile_create(intent['kind'], intent['draft'], identity['sql_mode'])
        if checked != compiled: raise RelationalClientError('Routine definition changed during SQL mode admission')
        grammar = check_grammar(client, checked, identity['sql_mode'])
        before = observe(cursor, intent)
        intent['review'] = {'identity': identity, 'before': before, 'grammar': grammar}
        planned['command_preview'].update(native_execution_identity=identity,native_routine_observation=before,native_grammar=grammar)
        return planned
    finally:
        if cursor is not None: client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client, request, connection=None):
    if connection is not None: raise RelationalClientError('Routine creation requires an independently owned connection')
    payload = request['provider_payload']; compiled = payload['compiled']; intent = compiled['mysql_routine_create']; review = intent.get('review')
    if not isinstance(review, Mapping): raise RelationalClientError('Review the native routine before dispatch')
    candidate = deepcopy(compiled); candidate['mysql_routine_create'].pop('review',None)
    if compile_create(intent['kind'],intent['draft'],review['identity']['sql_mode']) != candidate:
        raise RelationalClientError('Reviewed routine statement changed')
    if check_grammar(client, candidate, review['identity']['sql_mode']) != review['grammar']:
        raise RelationalClientError('Native routine grammar dependency changed since review')
    handle = client._connect({'route': payload['route']}); cursor = None; dispatched = acknowledged = False
    try:
        handle.autocommit = True; handle.get_warnings = True; handle.raise_on_warnings = False
        cursor = handle.cursor(); identity = context(cursor)
        if identity!=review['identity'] or observe(cursor,intent)!=review['before']:
            raise RelationalClientError('Native routine identity or definition changed since review')
        statement = compiled['statements'][0]; dispatched = True
        cursor.execute(statement['source'],statement['parameters'] or None); acknowledged = True
        warnings = [{'level':level,'code':code,'message':message} for level,code,message in (cursor.warnings or ())]
        after = observe(cursor,intent)
        return {'accepted': True, 'native_implicit_commit': True, 'commit_requested': False,
            'rollback_requested': False, 'staged_in_provider_session': False, 'automatic_retry': False,
            'driver_observation_only': True, 'transaction_finality_interpreted_by_common_code': False,
            'native_warnings': warnings, 'routine_observation': {'native_acknowledged': True,
                'before':review['before'], 'after':after, 'concurrent_external_ddl_fenced': False}}
    except Exception as error:
        failure = error if isinstance(error,RelationalClientError) else RelationalClientError('Native routine creation failed ('+type(error).__name__+')')
        failure.native_dispatched = dispatched; failure.native_acknowledged = acknowledged; failure.automatic_retry = False
        failure.errno = getattr(error,'errno',None); failure.sqlstate = getattr(error,'sqlstate',None)
        raise failure from None
    finally:
        if cursor is not None: client._safe_close(cursor)
        client._forget_and_close(handle)
