"""Structured native ordinary-view definitions; no replacement fallback."""
import re
from ..data_studio.language_tools import analyze
from ..sdk.relational import RelationalClientError
from .mysql_tablespaces import identifier

OPERATIONS = frozenset({'create', 'alter'})
ALGORITHMS = ('UNDEFINED', 'MERGE', 'TEMPTABLE')
SECURITY = ('DEFINER', 'INVOKER')
CHECK = ('NONE', 'LOCAL', 'CASCADED')


def _account_part(value, maximum):
    if not isinstance(value, str) or not value or len(value) > maximum or '\x00' in value:
        raise RelationalClientError('Definer requires exact bounded user and host')
    return '`' + value.replace('`', '``') + '`'


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, dict):
        raise RelationalClientError('Native view operation is unavailable')
    draft = dict(draft)
    # Keep the existing visual-administration request names compatible.
    for alias, canonical in (('query', 'definition'), ('parent', 'database')):
        if alias in draft:
            if canonical in draft:
                raise RelationalClientError('Ambiguous native view option')
            draft[canonical] = draft.pop(alias)
    allowed = {'confirmation', 'definition', 'columns', 'algorithm', 'sql_security',
               'check_option', 'definer_user', 'definer_host'}
    if operation == 'create':
        allowed |= {'name', 'database'}
        path = [draft.get('database'), draft.get('name')]
    else:
        path = (target or {}).get('display_path', [])
    if set(draft) - allowed or not isinstance(path, list) or len(path) != 2:
        raise RelationalClientError('Exact view identity and admitted options are required')
    qualified = '.'.join(identifier(part) for part in path)
    query = draft.get('definition')
    if not isinstance(query, str) or not re.match(r'^\s*(SELECT|WITH)\b', query, re.I) or '\x00' in query:
        raise RelationalClientError('View query must begin with SELECT or WITH')
    for mode in (False, True):
        result = analyze(query, 'mysql-sql', script=True, settings={'no_backslash_escapes': mode})
        if result['diagnostics'] or len(result['statements']) != 1:
            raise RelationalClientError('View definition requires one lexically complete query')
    # Drop a final delimiter so appended CHECK OPTION belongs to the query.
    query = result['statements'][0]['source']
    algorithm = draft.get('algorithm', 'UNDEFINED')
    security = draft.get('sql_security', 'DEFINER')
    check = draft.get('check_option', 'NONE')
    if algorithm not in ALGORITHMS or security not in SECURITY or check not in CHECK:
        raise RelationalClientError('Select native algorithm, security and check options')
    columns = draft.get('columns', [])
    if not isinstance(columns, list) or len(columns) > 4096 or len(set(c for c in columns if isinstance(c, str))) != len(columns):
        raise RelationalClientError('View columns require distinct ordered names')
    names = ', '.join(identifier(column) for column in columns)
    source = operation.upper() + ' ALGORITHM=' + algorithm
    if 'definer_user' in draft or 'definer_host' in draft:
        source += ' DEFINER=' + _account_part(draft.get('definer_user'), 32) + '@' + _account_part(draft.get('definer_host'), 255)
    source += ' SQL SECURITY ' + security + ' VIEW ' + qualified
    if names:
        source += ' (' + names + ')'
    source += ' AS ' + query + '\n'
    if check != 'NONE':
        source += 'WITH ' + check + ' CHECK OPTION'
    return {'source': source, 'parameters': ()}
