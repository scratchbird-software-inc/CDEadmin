"""CockroachDB functions and procedures.

Checked live on 26.1.3: SQL and PL/pgSQL bodies; IN / OUT / INOUT
parameters with defaults; RETURNS [SETOF] type (RETURNS TABLE renders as
OUT parameters and SETOF RECORD); IMMUTABLE / STABLE / VOLATILE, STRICT /
CALLED ON NULL INPUT, LEAKPROOF (immutable only), SECURITY DEFINER /
INVOKER; CREATE OR REPLACE; ALTER ... RENAME TO. Refused: VARIADIC,
PARALLEL, COST, SET options, COMMENT ON FUNCTION / PROCEDURE.

A routine is identified by name and argument types (overloads share a
name), so its signature is fixed once created: a change would create an
overload, not edit this one.
"""
import re

from ...sdk.relational import RelationalClientError

MODES = ('IN', 'OUT', 'INOUT')
LANGUAGES = ('SQL', 'PLPGSQL')
VOLATILITY = ('IMMUTABLE', 'STABLE', 'VOLATILE')
SECURITY = ('INVOKER', 'DEFINER')
_FUNCTION_ONLY = ('returns', 'returns_set', 'volatility', 'strict',
                  'leakproof')
_BODY_KEYS = ('language', 'body', 'security', *_FUNCTION_ONLY[2:])
CREATE_KEYS = {'name', 'parent', 'parameters', *_FUNCTION_ONLY,
               *_BODY_KEYS}
ALTER_KEYS = {'name', 'confirmation', *_BODY_KEYS}
_SIGNATURE_KEYS = ('parameters', 'returns', 'returns_set')


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
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise RelationalClientError('a parameter must be an object')
        mode = _choice(item.get('mode'), MODES, 'parameter mode', 'IN')
        text = ('' if mode == 'IN' else mode + ' ')
        if not _blank(item.get('name')):
            text += admin._quote(item['name']) + ' '
        text += admin._safe_fragment(item.get('type'), 'parameter type')
        if not _blank(item.get('default')):
            if mode == 'OUT':
                raise RelationalClientError(
                    'an OUT parameter takes no default')
            text += ' DEFAULT ' + admin._safe_fragment(item['default'],
                                                       'default')
        out.append(text)
    return ', '.join(out)


def _dollar_quote(body):
    tag, index = 'cde', 0
    while f'${tag}$' in body:
        index += 1
        tag = f'cde{index}'
    return f'${tag}$\n{body}\n${tag}$'


def definition(admin, kind, name, values, replace=False):
    """CREATE [OR REPLACE] FUNCTION / PROCEDURE from the editor's values."""
    keyword = 'FUNCTION' if kind == 'function' else 'PROCEDURE'
    if kind == 'procedure':
        given = [key for key in _FUNCTION_ONLY
                 if values.get(key) not in (None, '', False)]
        if given:
            raise RelationalClientError(
                'a procedure takes no ' + ', '.join(given))
    body = values.get('body')
    if not isinstance(body, str) or not body.strip():
        raise RelationalClientError('a routine needs a body')
    if '\x00' in body:
        raise RelationalClientError('the body must be text')
    language = _choice(values.get('language'), LANGUAGES, 'language', 'SQL')
    source = (f'CREATE {"OR REPLACE " if replace else ""}{keyword} {name}('
              f'{_parameters(admin, values.get("parameters") or [])})')
    if kind == 'function':
        returns = values.get('returns')
        if _blank(returns):
            if not any(str(item.get('mode', '')).upper() in {'OUT', 'INOUT'}
                       for item in values.get('parameters') or []):
                raise RelationalClientError(
                    'a function needs a return type or OUT parameters')
            returns = 'RECORD'
        source += (' RETURNS ' + ('SETOF ' if values.get('returns_set')
                                  else '') +
                   admin._safe_fragment(returns, 'return type'))
        volatility = _choice(values.get('volatility'), VOLATILITY,
                             'volatility', 'VOLATILE')
        if values.get('leakproof') and volatility != 'IMMUTABLE':
            # Live: "leak proof function must be immutable".
            raise RelationalClientError(
                'a LEAKPROOF function must be IMMUTABLE')
        source += f' {volatility}'
        source += ' LEAKPROOF' if values.get('leakproof') else ''
        source += (' STRICT' if values.get('strict')
                   else ' CALLED ON NULL INPUT')
    source += f' LANGUAGE {language}'
    security = _choice(values.get('security'), SECURITY, 'security',
                       'INVOKER')
    source += f' SECURITY {security} AS ' + _dollar_quote(body.strip())
    return source


def create(admin, kind, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown routine option: ' + ', '.join(sorted(unknown)))
    name = admin._new_object_name(admin._identifier(draft.get('name')),
                                  draft)
    return [{'source': definition(admin, kind, name, draft),
             'parameters': ()}]


def _signature(admin, native, path):
    name = admin._qualified([*path[:-1], native.get('name') or path[-1]])
    return f'{name}({native.get("signature") or ""})'


def alter(admin, kind, draft, target):
    locked = [key for key in _SIGNATURE_KEYS if key in draft]
    if locked:
        raise RelationalClientError(
            'the parameters and return type are part of the routine\'s '
            'identity; create a new routine to change them')
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown routine change: ' + ', '.join(sorted(unknown)))
    native = (target or {}).get('native') or {}
    path = admin._target_path(target)
    statements = []
    if any(key in draft and draft[key] != native.get(key)
           for key in _BODY_KEYS):
        values = {**{key: native.get(key) for key in (
            *_SIGNATURE_KEYS, *_BODY_KEYS)},
            **{key: draft[key] for key in _BODY_KEYS if key in draft}}
        name = admin._qualified([*path[:-1], native.get('name')])
        statements.append({'source': definition(
            admin, kind, name, values, replace=True), 'parameters': ()})
    if draft.get('name') not in (None, '', native.get('name')):
        keyword = 'FUNCTION' if kind == 'function' else 'PROCEDURE'
        statements.append({'source': (
            f'ALTER {keyword} {_signature(admin, native, path)} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def drop(admin, kind, target):
    native = (target or {}).get('native') or {}
    keyword = 'FUNCTION' if kind == 'function' else 'PROCEDURE'
    signature = _signature(admin, native, admin._target_path(target))
    return [{'source': f'DROP {keyword} {signature}', 'parameters': ()}]


# --- reading SHOW CREATE ALL ROUTINES -----------------------------------

def _split_top(text):
    """Split on commas outside parentheses and quotes."""
    items, depth, start, index, quote = [], 0, 0, 0, None
    while index < len(text):
        char = text[index]
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
        index += 1
    tail = text[start:].strip()
    if tail:
        items.append(tail)
    return items


def parse_create(statement, names, modes):
    """((schema, name), facts) from CockroachDB's rendering, or None.

    ``names``/``modes`` are pg_proc.proargnames / proargmodes, which say
    where each parameter's name ends and its type begins.
    """
    from .tables import _identifier, _strip_casts
    match = re.match(r'CREATE (FUNCTION|PROCEDURE) ', statement)
    if not match:
        return None
    try:
        schema, index = _identifier(statement, match.end())
        name, index = _identifier(statement, index + 1)
    except ValueError:
        return None
    if not statement.startswith('(', index):
        return None
    depth, end = 0, index
    for end in range(index, len(statement)):
        depth += statement[end] == '('
        depth -= statement[end] == ')'
        if depth == 0:
            break
    texts = _split_top(statement[index + 1:end])
    names = list(names or [])
    modes = list(modes or [])
    parameters = []
    for position, text in enumerate(texts):
        mode = {'o': 'OUT', 'b': 'INOUT'}.get(
            modes[position] if position < len(modes) else 'i', 'IN')
        for keyword in ('INOUT ', 'OUT ', 'IN '):
            if text.startswith(keyword):
                text = text[len(keyword):]
                break
        given = names[position] if position < len(names) else ''
        if given:
            try:
                _, at = _identifier(text, 0)
                text = text[at:].lstrip()
            except ValueError:
                pass
        kind, _, default = text.partition(' DEFAULT ')
        parameters.append({'mode': mode, 'name': given or '',
                           'type': kind.strip(),
                           'default': _strip_casts(default) or None})
    returns = re.search(r'\n\tRETURNS (SETOF )?([^\n]+)', statement)
    lines = set(re.findall(r'\n\t([A-Z][A-Z ]+)(?=\n)', statement))
    facts = {
        'parameters': parameters,
        'returns': returns.group(2).strip() if returns else None,
        'returns_set': bool(returns and returns.group(1)),
        # pg_proc.prosecdef does not follow ALTER ... SECURITY (live).
        'security': 'DEFINER' if 'SECURITY DEFINER' in lines else 'INVOKER',
    }
    language = re.search(r'\n\tLANGUAGE (\w+)', statement)
    if language:
        facts['language'] = ('PLPGSQL' if language.group(1).lower() ==
                             'plpgsql' else 'SQL')
    volatility = [item for item in VOLATILITY if item in lines]
    if volatility:
        facts.update(volatility=volatility[0], leakproof='LEAKPROOF' in lines,
                     strict='STRICT' in lines)
    return (schema, name), facts


def form(field, kind, operation):
    fields = [field('name', 'Name', 'text', True)]
    if operation == 'create':
        fields.append(field('parent', 'Schema', 'text'))
    if kind == 'function' and operation == 'create':
        fields += [field('returns', 'Return type', 'text'),
                   field('returns_set', 'Returns a set (SETOF)', 'boolean',
                         False, default=False)]
    fields += [field('language', 'Language', 'select', True, default='SQL',
                     options=LANGUAGES),
               field('security', 'Security', 'select', False,
                     default='INVOKER', options=SECURITY)]
    if kind == 'function':
        fields += [field('volatility', 'Volatility', 'select', False,
                         default='VOLATILE', options=VOLATILITY),
                   field('strict', 'Strict (returns null on null input)',
                         'boolean', False, default=False),
                   field('leakproof', 'Leakproof', 'boolean', False,
                         'Immutable functions only.', False)]
    fields.append(field('body', 'Body', 'code', True,
                        'The routine body only, without CREATE.'))
    if operation == 'alter':
        for item in fields:
            item['initial_value_path'] = [item['field_id']]
    return {'form_id': f'cockroachdb.{kind}.{operation}',
            'title': f'{operation.title()} CockroachDB {kind}',
            'fields': fields,
            'notes': 'Parameters are a descriptor grid (routine.form.json); '
                     'they are fixed once the routine exists.'}
