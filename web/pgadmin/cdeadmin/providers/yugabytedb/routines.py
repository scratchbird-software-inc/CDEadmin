"""YugabyteDB YSQL functions and procedures: PostgreSQL 15's routines.

Checked live on 2025.2.2.2 (probe): SQL and PL/pgSQL bodies; IN / OUT /
INOUT / VARIADIC parameters with defaults; RETURNS [SETOF] type or RETURNS
TABLE; volatility, STRICT, LEAKPROOF, SECURITY DEFINER, PARALLEL, COST,
ROWS and SET options; CREATE OR REPLACE; ALTER ... RENAME TO; COMMENT ON
FUNCTION / PROCEDURE.

A routine is identified by name and argument types (overloads share a
name), so its signature is fixed once created. Field ids match the
CockroachDB routine form (providers/cockroachdb/routines.py); YSQL adds
VARIADIC and TABLE parameters, parallel, cost, rows, settings and comment.
"""
import re

from ...sdk.relational import RelationalClientError

MODES = ('IN', 'OUT', 'INOUT', 'VARIADIC', 'TABLE')
LANGUAGES = ('SQL', 'PLPGSQL')
VOLATILITY = ('IMMUTABLE', 'STABLE', 'VOLATILE')
SECURITY = ('INVOKER', 'DEFINER')
PARALLEL = ('UNSAFE', 'RESTRICTED', 'SAFE')
_FUNCTION_ONLY = ('returns', 'returns_set', 'volatility', 'strict',
                  'leakproof', 'parallel', 'cost', 'rows')
_BODY_KEYS = ('language', 'body', 'security', 'settings', 'volatility',
              'strict', 'leakproof', 'parallel', 'cost', 'rows')
_SIGNATURE_KEYS = ('parameters', 'returns', 'returns_set')
CREATE_KEYS = {'name', 'parent', 'parameters', 'comment', *_FUNCTION_ONLY,
               *_BODY_KEYS}
ALTER_KEYS = {'name', 'comment', 'confirmation', *_BODY_KEYS}
_SETTING = re.compile(r'[a-z_][a-z0-9_.]{0,127}')


def _blank(value):
    return value is None or value == ''


def _choice(value, allowed, label, default):
    if _blank(value):
        return default
    value = str(value).upper()
    if value not in allowed:
        raise RelationalClientError(
            f'{label} must be one of: ' + ', '.join(allowed))
    return value


def _parameters(admin, items):
    if not isinstance(items, list):
        raise RelationalClientError('parameters must be a list')
    listed, table = [], []
    for item in items:
        if not isinstance(item, dict):
            raise RelationalClientError('a parameter must be an object')
        mode = _choice(item.get('mode'), MODES, 'parameter mode', 'IN')
        kind = admin._safe_type(item.get('type'), 'parameter type')
        name = '' if _blank(item.get('name')) else admin._quote(item['name'])
        if mode == 'TABLE':
            if not name:
                raise RelationalClientError('a TABLE column needs a name')
            table.append(f'{name} {kind}')
            continue
        text = ('' if mode == 'IN' else mode + ' ') + (
            f'{name} ' if name else '') + kind
        if not _blank(item.get('default')):
            if mode == 'OUT':
                raise RelationalClientError(
                    'an OUT parameter takes no default')
            text += ' DEFAULT ' + admin._safe_fragment(item['default'],
                                                       'default')
        listed.append(text)
    return ', '.join(listed), table


def _dollar_quote(body):
    tag, index = 'cde', 0
    while f'${tag}$' in body:
        index += 1
        tag = f'cde{index}'
    return f'${tag}$\n{body}\n${tag}$'


def _settings(admin, value):
    if not value:
        return []
    if not isinstance(value, list):
        raise RelationalClientError('settings must be a list')
    out = []
    for item in value:
        if not isinstance(item, dict) or not _SETTING.fullmatch(
                str(item.get('name') or '')):
            raise RelationalClientError('a setting needs a variable name')
        if not isinstance(item.get('value'), str):
            raise RelationalClientError(f'{item["name"]} needs a value')
        out.append(f'SET {item["name"]} = {admin._literal(item["value"])}')
    return out


def definition(admin, kind, name, values, replace=False):
    keyword = 'FUNCTION' if kind == 'function' else 'PROCEDURE'
    if kind == 'procedure':
        given = [key for key in _FUNCTION_ONLY
                 if values.get(key) not in (None, '', False)]
        if given:
            raise RelationalClientError(
                'a procedure takes no ' + ', '.join(given))
    body = values.get('body')
    if not isinstance(body, str) or not body.strip() or '\x00' in body:
        raise RelationalClientError('a routine needs a body')
    listed, table = _parameters(admin, values.get('parameters') or [])
    if table and kind != 'function':
        raise RelationalClientError('only a function returns a TABLE')
    source = (f'CREATE {"OR REPLACE " if replace else ""}{keyword} {name}'
              f'({listed})')
    if kind == 'function':
        if table:
            if not _blank(values.get('returns')):
                raise RelationalClientError(
                    'RETURNS TABLE takes its columns, not a return type')
            source += ' RETURNS TABLE (' + ', '.join(table) + ')'
        else:
            returns = values.get('returns')
            if _blank(returns):
                if not any(str(item.get('mode', '')).upper() in {
                        'OUT', 'INOUT'}
                        for item in values.get('parameters') or []):
                    raise RelationalClientError(
                        'a function needs a return type or OUT parameters')
                returns = 'record'
            source += (' RETURNS ' + ('SETOF ' if values.get('returns_set')
                                      else '') +
                       admin._safe_type(returns, 'return type'))
        volatility = _choice(values.get('volatility'), VOLATILITY,
                             'volatility', 'VOLATILE')
        source += f' {volatility}'
        source += ' LEAKPROOF' if values.get('leakproof') else ''
        source += (' STRICT' if values.get('strict')
                   else ' CALLED ON NULL INPUT')
        source += ' PARALLEL ' + _choice(values.get('parallel'), PARALLEL,
                                         'parallel', 'UNSAFE')
        for key in ('cost', 'rows'):
            if not _blank(values.get(key)):
                value = values[key]
                if isinstance(value, bool) or not isinstance(
                        value, (int, float)) or value <= 0:
                    raise RelationalClientError(f'{key} is a positive number')
                source += f' {key.upper()} {value:g}'
    source += ' LANGUAGE ' + _choice(values.get('language'), LANGUAGES,
                                     'language', 'SQL')
    source += ' SECURITY ' + _choice(values.get('security'), SECURITY,
                                     'security', 'INVOKER')
    for setting in _settings(admin, values.get('settings')):
        source += f' {setting}'
    return source + ' AS ' + _dollar_quote(body.strip())


def _comment(admin, kind, signature, value):
    keyword = 'FUNCTION' if kind == 'function' else 'PROCEDURE'
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON {keyword} {signature} IS {text}',
            'parameters': ()}


def _signature(admin, schema, name, types):
    return f'{admin._qualified((schema, name))}({types or ""})'


def create(admin, kind, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown routine option: ' + ', '.join(sorted(unknown)))
    name = admin._new_object_name(admin._identifier(draft.get('name')),
                                  draft)
    statements = [{'source': definition(admin, kind, name, draft),
                   'parameters': ()}]
    if not _blank(draft.get('comment')):
        # The new routine's argument types, as COMMENT ON names it.
        types = ', '.join(
            admin._safe_type(item.get('type'), 'parameter type')
            for item in draft.get('parameters') or []
            if str(item.get('mode') or 'IN').upper() in {
                'IN', 'INOUT', 'VARIADIC'})
        statements.append({'source': (
            f'COMMENT ON {"FUNCTION" if kind == "function" else "PROCEDURE"}'
            f' {name}({types}) IS {admin._literal(str(draft["comment"]))}'),
            'parameters': ()})
    return statements


def alter(admin, kind, draft, target):
    locked = [key for key in _SIGNATURE_KEYS if key in draft]
    if locked:
        raise RelationalClientError(
            "the parameters and return type are part of the routine's "
            'identity; create a new routine to change them')
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown routine change: ' + ', '.join(sorted(unknown)))
    native = (target or {}).get('native') or {}
    path = admin._target_path(target)
    schema, name = path[0], native.get('name')
    signature = _signature(admin, schema, name, native.get('signature'))
    statements = []
    if any(key in draft and draft[key] != native.get(key)
           for key in _BODY_KEYS):
        values = {**{key: native.get(key) for key in (
            *_SIGNATURE_KEYS, *_BODY_KEYS)},
            **{key: draft[key] for key in _BODY_KEYS if key in draft}}
        statements.append({'source': definition(
            admin, kind, admin._qualified((schema, name)), values,
            replace=True), 'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, kind, signature, draft['comment']))
    if draft.get('name') not in (None, '', name):
        keyword = 'FUNCTION' if kind == 'function' else 'PROCEDURE'
        statements.append({'source': (
            f'ALTER {keyword} {signature} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def drop(admin, kind, target):
    native = (target or {}).get('native') or {}
    path = admin._target_path(target)
    keyword = 'FUNCTION' if kind == 'function' else 'PROCEDURE'
    signature = _signature(admin, path[0], native.get('name'),
                           native.get('signature'))
    return [{'source': f'DROP {keyword} {signature}', 'parameters': ()}]


# --- reading pg_proc --------------------------------------------------------

def _split_top(text):
    items, depth, start, quote = [], 0, 0, None
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif char == ',' and depth == 0:
            items.append(text[start:index].strip())
            start = index + 1
    if text[start:].strip():
        items.append(text[start:].strip())
    return items


def parameters_from(arguments, result, names, modes):
    """Parameters from pg_get_function_arguments / _result.

    ``names`` and ``modes`` are proargnames / proargmodes, which say where a
    parameter's name ends; TABLE columns come from the result text.
    """
    names = list(names or [])
    modes = list(modes or [])
    out = []
    for position, text in enumerate(_split_top(arguments or '')):
        mode = 'IN'
        for keyword in ('INOUT ', 'OUT ', 'VARIADIC ', 'IN '):
            if text.startswith(keyword):
                mode, text = keyword.strip(), text[len(keyword):]
                break
        given = names[position] if position < len(names) else ''
        if given:
            quoted = f'"{given}"'
            for spelling in (quoted + ' ', given + ' '):
                if text.startswith(spelling):
                    text = text[len(spelling):]
                    break
        kind, _, default = text.partition(' DEFAULT ')
        out.append({'mode': mode, 'name': given or '', 'type': kind.strip(),
                    'default': default.strip() or None})
    table = re.fullmatch(r'TABLE\((.*)\)', result or '')
    if table:
        for text in _split_top(table.group(1)):
            name, _, kind = text.partition(' ')
            out.append({'mode': 'TABLE', 'name': name.strip('"'),
                        'type': kind.strip(), 'default': None})
    return out


def returns_from(result):
    if not result or result.startswith('TABLE('):
        return None, False
    if result.startswith('SETOF '):
        return result[len('SETOF '):], True
    return result, False


def form(field, kind, operation):
    fields = [field('name', 'Name', 'text', True)]
    if operation == 'create':
        fields.append(field('parent', 'Schema', 'text'))
        if kind == 'function':
            fields += [field('returns', 'Return type', 'text'),
                       field('returns_set', 'Returns a set (SETOF)',
                             'boolean', False, default=False)]
    fields += [field('language', 'Language', 'select', True, default='SQL',
                     options=LANGUAGES),
               field('security', 'Security', 'select', False,
                     default='INVOKER', options=SECURITY)]
    if kind == 'function':
        fields += [field('volatility', 'Volatility', 'select', False,
                         default='VOLATILE', options=VOLATILITY),
                   field('strict', 'Strict', 'boolean', False,
                         default=False),
                   field('leakproof', 'Leakproof', 'boolean', False,
                         default=False),
                   field('parallel', 'Parallel', 'select', False,
                         default='UNSAFE', options=PARALLEL),
                   field('cost', 'Cost', 'number'),
                   field('rows', 'Rows (set-returning)', 'number')]
    fields += [field('body', 'Body', 'code', True),
               field('comment', 'Comment', 'text')]
    if operation == 'alter':
        for item in fields:
            item['initial_value_path'] = [item['field_id']]
    return {'form_id': f'yugabytedb.{kind}.{operation}',
            'title': f'{operation.title()} YSQL {kind}', 'fields': fields,
            'notes': 'Parameters and settings are descriptor grids.'}
