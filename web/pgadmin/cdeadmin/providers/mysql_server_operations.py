"""Native MySQL global/persistent variable changes and exact process control."""
import re
from decimal import Decimal
from ..sdk.relational import RelationalClientError

OPERATIONS = {'system-variable': frozenset({'set_global', 'set_persist', 'set_persist_only', 'reset_persist'}),
              'session': frozenset({'terminate_query', 'terminate_connection'})}


def compile_operation(kind, operation, draft, target):
    if operation not in OPERATIONS.get(kind, ()) or not isinstance(draft, dict):
        raise RelationalClientError('Native MySQL server operation is unavailable')
    if kind == 'session':
        if set(draft) - {'confirmation'}: raise RelationalClientError('Unknown native session option')
        native = (target or {}).get('native') or (target or {}).get('extensions', {}).get('mysql', {}).get('native', {})
        identity = native.get('processlist_id')
        if not isinstance(identity, str) or not re.fullmatch(r'[1-9][0-9]{0,19}', identity) or int(identity) > 2**64-1:
            raise RelationalClientError('Exact native process/connection ID is required')
        return {'source': 'KILL ' + ('QUERY ' if operation == 'terminate_query' else 'CONNECTION ') + identity, 'parameters': ()}
    allowed = {'confirmation'} | (set() if operation == 'reset_persist' else {'value', 'value_mode', 'value_type'})
    if set(draft) - allowed: raise RelationalClientError('Unknown native variable option')
    name = (target or {}).get('display_name')
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?', name) or len(name) > 128:
        raise RelationalClientError('Exact native variable name is required')
    quoted = '`' + name + '`'
    if operation == 'reset_persist': return {'source': 'RESET PERSIST ' + quoted, 'parameters': ()}
    native = (target or {}).get('native') or (target or {}).get('extensions', {}).get('mysql', {}).get('native', {})
    facts = native.get('catalog_row', native)
    if facts.get('variable_scope') == 'SESSION_ONLY':
        raise RelationalClientError('This native variable has session-only scope; use its retained SQL session')
    mode = draft.get('value_mode', 'VALUE')
    if mode not in {'VALUE', 'DEFAULT', 'NULL'}: raise RelationalClientError('Select a bound value, native DEFAULT or NULL')
    source = 'SET ' + {'set_global': 'GLOBAL ', 'set_persist': 'PERSIST ', 'set_persist_only': 'PERSIST_ONLY '}[operation] + quoted + ' = '
    if mode in {'DEFAULT', 'NULL'}: return {'source': source + mode, 'parameters': ()}
    value = draft.get('value')
    if not (isinstance(value, str) and '\x00' not in value and len(value.encode('utf8')) <= 65536 or
            type(value) is bool or type(value) is int and -(2**53-1) <= value <= 2**53-1):
        raise RelationalClientError('Native variable requires bounded text, boolean or safe integer; use text for large numeric values')
    expression = '%s'
    value_type = draft.get('value_type', 'AUTO')
    if not isinstance(value_type, str):
        raise RelationalClientError('Select a native value representation')
    if value_type in {'TEXT', 'BOOLEAN', 'SAFE_INTEGER'}:
        expected = {'TEXT': str, 'BOOLEAN': bool, 'SAFE_INTEGER': int}[value_type]
        if type(value) is not expected:
            raise RelationalClientError('The supplied value must match its selected input type')
    elif value_type == 'INTEGER':
        if not isinstance(value, str) or not re.fullmatch(r'-?(?:0|[1-9][0-9]{0,19})', value) or not -(2**63) <= int(value) <= 2**64-1:
            raise RelationalClientError('Explicit integer values require exact signed/unsigned 64-bit decimal text')
        expression = 'CAST(%s AS ' + ('SIGNED' if value.startswith('-') else 'UNSIGNED') + ')'
    elif value_type == 'DECIMAL':
        if not isinstance(value, str) or len(value) > 128 or not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,3})?', value):
            raise RelationalClientError('Explicit decimal values require bounded exact decimal text')
        numeric = Decimal(value)
        sign, digits, exponent = numeric.as_tuple()
        if max(len(digits) + exponent, 0) > 35 or exponent < -30:
            raise RelationalClientError('Explicit decimal must fit native DECIMAL(65,30)')
        expression = 'CAST(%s AS DECIMAL(65,30))'
    elif value_type == 'DOUBLE':
        if not isinstance(value, str) or len(value) > 128 or not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,4})?', value):
            raise RelationalClientError('Explicit DOUBLE requires bounded decimal/scientific text; the native server owns floating conversion and overflow')
        expression = 'CAST(%s AS DOUBLE)'
    elif value_type != 'AUTO':
        raise RelationalClientError('Select automatic scalar, explicit integer, decimal or DOUBLE input')
    return {'source': source + expression, 'preview_source': source + '<redacted>', 'parameters': (value,)}
