"""PostgreSQL functions and procedures on the provider tree (M4,
2026-11-11).

CREATE [OR REPLACE] FUNCTION | PROCEDURE with IN / OUT / INOUT / VARIADIC
arguments and defaults, RETURNS type | SETOF type | TABLE(...), LANGUAGE,
volatility, STRICT, LEAKPROOF, SECURITY DEFINER, PARALLEL, COST, ROWS, SET
parameters and a dollar-quoted body; owner, comment; ALTER ... RENAME TO /
OWNER TO / SET SCHEMA; DROP. A routine's signature (arguments and return
type) is fixed once created: a changed body or option runs CREATE OR
REPLACE with the same signature; a changed signature is refused (drop and
create). C-language routines, support functions, window functions,
privileges and security labels stay with the inherited dialog. Field ids
follow the inherited dialog (``function.ui.js``).

The alter dialog's initial values come from ``pg_get_functiondef`` read
back through PostgreSQL's own parser (pglast), so arguments, options and
body are exact. Argument types are admitted the same way.
"""
import re

from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified, _type_reference,
)
from .policies import expression

MODES = {'IN': 'i', 'OUT': 'o', 'INOUT': 'b', 'VARIADIC': 'v',
         'TABLE': 't'}
_MODE_NAMES = {value: key for key, value in MODES.items()}
VOLATILITY = {'i': 'IMMUTABLE', 's': 'STABLE', 'v': 'VOLATILE'}
PARALLEL = {'u': 'UNSAFE', 'r': 'RESTRICTED', 's': 'SAFE'}
_LANGUAGE = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,62}')
_SETTING = re.compile(r'[A-Za-z_][A-Za-z0-9_.]{0,127}')
_SEARCH_PATH = re.compile(r'[\w$"]+(?:\s*,\s*[\w$"]+)*')


def _blank(value):
    return value is None or value == ''


# -- facts: the routine's definition read back through the parser ------------

def _render(node):
    from pglast.stream import RawStream
    return RawStream()(node)


def facts(native):
    """Current values from pg_get_functiondef; never raises."""
    row = native.get('catalog_row') or {}
    result = {
        'name': native.get('name') or row.get('proname'),
        'pronamespace': native.get('schema'),
        'sql_identity': native.get('sql_identity'),
        'kind': 'procedure' if row.get('prokind') == 'p' else 'function',
        'description': native.get('comment'),
        'arguments': [], 'prorettypename': None, 'lanname': None,
        'prosrc': None, 'provolatile': VOLATILITY.get(
            row.get('provolatile'), 'VOLATILE'),
        'proisstrict': bool(row.get('proisstrict', False)),
        'prosecdef': bool(row.get('prosecdef', False)),
        'proleakproof': bool(row.get('proleakproof', False)),
        'proparallel': PARALLEL.get(row.get('proparallel'), 'UNSAFE'),
        'procost': row.get('procost'), 'prorows': row.get('prorows'),
        'variables': [], 'definition_parsed': False,
    }
    definition = native.get('definition')
    if not isinstance(definition, str) or not definition.strip():
        return result
    try:
        from pglast import parse_sql
        statement = parse_sql(definition)[0].stmt
        table = []
        for item in statement.parameters or []:
            mode = getattr(item.mode, 'value', item.mode) or 'i'
            entry = {'argmode': _MODE_NAMES.get(mode, 'IN'),
                     'argname': item.name,
                     'argtype': _render(item.argType),
                     'argdefval': _render(item.defexpr)
                     if item.defexpr is not None else None}
            (table if mode == 't' else result['arguments']).append(entry)
        if table:
            result['prorettypename'] = 'TABLE(' + ', '.join(
                f'{_identifier(item["argname"], "column")} '
                f'{item["argtype"]}' for item in table) + ')'
        elif statement.returnType is not None:
            result['prorettypename'] = _render(statement.returnType)
        for option in statement.options or []:
            arg = option.arg
            if option.defname == 'language':
                result['lanname'] = arg.sval
            elif option.defname == 'as':
                items = list(arg) if not hasattr(arg, 'sval') else [arg]
                result['prosrc'] = items[0].sval if items else None
            elif option.defname == 'set':
                values = [_render(value) for value in arg.args or []]
                text = ', '.join(values)
                if arg.name != 'search_path':
                    text = text[1:-1].replace("''", "'") if len(
                        values) == 1 and text.startswith("'") else text
                else:
                    text = ', '.join(value.strip("'") for value in values)
                result['variables'].append({'name': arg.name,
                                            'value': text})
        result['definition_parsed'] = True
    except Exception:
        return result
    return result


# -- compile ------------------------------------------------------------------

def _arguments(rows, kind):
    """(declaration list, signature type list) from the arguments grid."""
    declarations, signature = [], []
    for row in rows:
        if not isinstance(row, dict):
            raise PostgreSQLNativeAdminError('arguments must be rows')
        mode = str(row.get('argmode') or 'IN').upper()
        if mode not in MODES:
            raise PostgreSQLNativeAdminError(
                'argument mode is ' + ', '.join(MODES))
        if mode == 'TABLE':
            raise PostgreSQLNativeAdminError(
                'TABLE columns belong to the return type (RETURNS TABLE)')
        argtype = _type_reference(row.get('argtype'), 'argument type')
        parts = [] if mode == 'IN' else [mode]
        if not _blank(row.get('argname')):
            parts.append(_identifier(row['argname'], 'argument name'))
        parts.append(argtype)
        if not _blank(row.get('argdefval')):
            parts.append('DEFAULT ' + expression(row['argdefval'],
                                                 'argument default'))
        declarations.append(' '.join(parts))
        if mode != 'OUT' or kind == 'procedure':
            signature.append(('VARIADIC ' if mode == 'VARIADIC' else '')
                             + argtype)
    return declarations, signature


def _returns(value):
    value = (value or '').strip()
    if not value:
        raise PostgreSQLNativeAdminError('return type must not be empty')
    upper = value.upper()
    if upper.startswith('TABLE'):
        inner = value[5:].strip()
        if not inner.startswith('(') or not inner.endswith(')'):
            raise PostgreSQLNativeAdminError(
                'RETURNS TABLE needs (column type, ...)')
        columns = []
        depth, start = 0, 0
        body = inner[1:-1]
        for index, char in enumerate(body + ','):
            depth += {'(': 1, ')': -1}.get(char, 0)
            if char == ',' and depth == 0:
                part = body[start:index].strip()
                start = index + 1
                if not part:
                    continue
                if part.startswith('"'):
                    # A quoted column name may hold spaces.
                    end = part.find('"', 1)
                    while 0 < end < len(part) - 1 and part[end + 1] == '"':
                        end = part.find('"', end + 2)
                    if end < 1:
                        raise PostgreSQLNativeAdminError(
                            'RETURNS TABLE column name is unterminated')
                    name = part[1:end].replace('""', '"')
                    type_text = part[end + 1:].strip()
                else:
                    name, _, type_text = part.partition(' ')
                columns.append(f'{_identifier(name, "column")} '
                               f'{_type_reference(type_text, "column type")}')
        if not columns:
            raise PostgreSQLNativeAdminError(
                'RETURNS TABLE needs at least one column')
        return 'TABLE(' + ', '.join(columns) + ')'
    if upper.startswith('SETOF '):
        return 'SETOF ' + _type_reference(value[6:].strip(), 'return type')
    return _type_reference(value, 'return type')


def _dollar_quote(body):
    tag = 'BODY'
    while f'${tag}$' in body:
        tag += '_'
    return f'${tag}${body}${tag}$'


def _settings(rows):
    clauses = []
    for row in rows:
        if not isinstance(row, dict):
            raise PostgreSQLNativeAdminError('settings must be rows')
        name = row.get('name')
        if not isinstance(name, str) or not _SETTING.fullmatch(name):
            raise PostgreSQLNativeAdminError('a setting needs a variable name')
        value = row.get('value')
        if not isinstance(value, str) or not value.strip():
            raise PostgreSQLNativeAdminError(f'{name} needs a value')
        if name == 'search_path':
            if not _SEARCH_PATH.fullmatch(value.strip()):
                raise PostgreSQLNativeAdminError(
                    'search_path is a comma-separated list of schemas')
            clauses.append(f'SET search_path = {value.strip()}')
        else:
            clauses.append(f'SET {name} = {_literal(value, name)}')
    return clauses


def _choice(value, allowed, label, current):
    if _blank(value):
        return current
    text = str(value).upper()
    if text not in allowed.values():
        raise PostgreSQLNativeAdminError(
            f'{label} is ' + ', '.join(allowed.values()))
    return text


def _number(value, label, current, *, minimum=0):
    if _blank(value):
        return current
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or \
            value < minimum:
        raise PostgreSQLNativeAdminError(f'{label} is a whole number')
    return value


def _bool(draft, key, current):
    return current if draft.get(key) is None else _flag(draft, key)


def _definition(kind, qualified, draft, current, replace):
    rows = draft.get('arguments')
    if rows in (None, ''):
        rows = current['arguments'] if current else []
    declarations, signature = _arguments(rows, kind)
    head = ('CREATE OR REPLACE ' if replace else 'CREATE ') + (
        'PROCEDURE' if kind == 'procedure' else 'FUNCTION')
    text = f'{head} {qualified}(' + ', '.join(declarations) + ')'
    if kind == 'function':
        returns = draft.get('prorettypename')
        if _blank(returns) and current:
            returns = current['prorettypename']
        text += ' RETURNS ' + _returns(returns)
    language = draft.get('lanname')
    if _blank(language) and current:
        language = current['lanname']
    if not isinstance(language, str) or not _LANGUAGE.fullmatch(language):
        raise PostgreSQLNativeAdminError('language is a language name')
    if language.lower() == 'c':
        raise PostgreSQLNativeAdminError(
            'C-language routines stay with the inherited dialog')
    text += f' LANGUAGE {language.lower()}'
    if kind == 'function':
        base = current or {}
        text += ' ' + _choice(draft.get('provolatile'), VOLATILITY,
                              'volatility', base.get('provolatile',
                                                     'VOLATILE'))
        if _bool(draft, 'proleakproof', base.get('proleakproof', False)):
            text += ' LEAKPROOF'
        if _bool(draft, 'proisstrict', base.get('proisstrict', False)):
            text += ' STRICT'
    if _bool(draft, 'prosecdef', (current or {}).get('prosecdef', False)):
        text += ' SECURITY DEFINER'
    if kind == 'function':
        base = current or {}
        text += ' PARALLEL ' + _choice(draft.get('proparallel'), PARALLEL,
                                       'parallel', base.get('proparallel',
                                                            'UNSAFE'))
        cost = _number(draft.get('procost'), 'cost', base.get('procost'))
        if cost:
            text += f' COST {cost}'
        rows_estimate = _number(draft.get('prorows'), 'rows',
                                base.get('prorows'))
        if rows_estimate:
            text += f' ROWS {rows_estimate}'
    settings = draft.get('variables')
    if settings in (None, '') and current:
        settings = current['variables']
    for clause in _settings(settings or []):
        text += ' ' + clause
    body = draft.get('prosrc')
    if _blank(body) and current:
        body = current['prosrc']
    if not isinstance(body, str) or not body.strip():
        raise PostgreSQLNativeAdminError('the code must not be empty')
    if '\x00' in body:
        raise PostgreSQLNativeAdminError('the code contains a NUL byte')
    text += ' AS ' + _dollar_quote(body)
    return text, '(' + ', '.join(signature) + ')'


def _keyword(kind):
    return 'PROCEDURE' if kind == 'procedure' else 'FUNCTION'


def _create(kind, draft):
    schema = _name(draft.get('pronamespace'), 'schema')
    qualified = _qualified(schema, draft.get('name'))
    text, signature = _definition(kind, qualified, draft, None, False)
    statements = [text]
    keyword = _keyword(kind)
    if not _blank(draft.get('funcowner')):
        statements.append(f'ALTER {keyword} {qualified}{signature} OWNER TO '
                          + _identifier(draft['funcowner'], 'owner'))
    if not _blank(draft.get('description')):
        statements.append(f'COMMENT ON {keyword} {qualified}{signature} IS '
                          + _literal(str(draft['description']), 'comment'))
    return statements


def _identity(current):
    identity = current.get('sql_identity')
    if not isinstance(identity, str) or '(' not in identity:
        raise PostgreSQLNativeAdminError(
            'the routine identity is unavailable; refresh the tree')
    return identity


def _alter(kind, native, draft):
    current = native.get('routine_facts') or facts(native)
    keyword = _keyword(kind)
    identity = _identity(current)
    schema = _name(current['pronamespace'], 'schema')
    name = _name(current['name'], 'name')
    statements = []
    body_keys = ('lanname', 'prosrc', 'provolatile', 'proisstrict',
                 'prosecdef', 'proleakproof', 'proparallel', 'procost',
                 'prorows', 'variables')
    rows = draft.get('arguments')
    if rows not in (None, '') and rows != current['arguments']:
        raise PostgreSQLNativeAdminError(
            'the arguments are fixed once created; drop and create the '
            'routine to change them')
    returns = draft.get('prorettypename')
    if not _blank(returns) and returns != current['prorettypename']:
        raise PostgreSQLNativeAdminError(
            'the return type is fixed once created; drop and create the '
            'routine to change it')
    changed = any(key in draft and draft[key] is not None and
                  draft[key] != current.get(key) for key in body_keys)
    if changed:
        if not current['definition_parsed']:
            raise PostgreSQLNativeAdminError(
                'the current definition could not be read back; edit it '
                'from the inherited dialog')
        text, _ = _definition(kind, _qualified(schema, name), draft,
                              current, True)
        statements.append(text)
    arguments = identity[identity.index('('):]
    qualified = _qualified(schema, name)
    if not _blank(draft.get('funcowner')):
        statements.append(f'ALTER {keyword} {qualified}{arguments} OWNER TO '
                          + _identifier(draft['funcowner'], 'owner'))
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        text = 'NULL' if _blank(draft['description']) else _literal(
            str(draft['description']), 'comment')
        statements.append(f'COMMENT ON {keyword} {qualified}{arguments} IS '
                          f'{text}')
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER {keyword} {qualified}{arguments} RENAME TO '
                          + _identifier(new_name, 'name'))
        qualified = _qualified(schema, new_name)
    new_schema = draft.get('pronamespace')
    if not _blank(new_schema) and new_schema != schema:
        statements.append(f'ALTER {keyword} {qualified}{arguments} SET SCHEMA '
                          + _identifier(new_schema, 'schema'))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _drop(kind, native, draft):
    current = native.get('routine_facts') or facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    identity = _identity(current)
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    qualified = _qualified(current['pronamespace'], name)
    return [f'DROP {_keyword(kind)} {qualified}'
            f'{identity[identity.index("("):]}{cascade}']


def compile_operation(kind, operation, native, draft):
    """One exact native text for a function or procedure lifecycle."""
    if operation == 'create':
        statements = _create(kind, draft)
    elif operation == 'alter':
        statements = _alter(kind, native, draft)
    elif operation == 'drop':
        statements = _drop(kind, native, draft)
    else:
        raise PostgreSQLNativeAdminError(
            'routine inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


# -- forms --------------------------------------------------------------------

def form(kind, operation, field):
    """Dialog fields; ids follow the inherited function dialog."""
    label = 'procedure' if kind == 'procedure' else 'function'
    if operation == 'drop':
        fields = [field('cascade', 'Drop dependent objects', 'boolean'),
                  field('confirmation', f'Type the {label} name to confirm',
                        required=True)]
    else:
        alter = operation == 'alter'

        def initial(key):
            return {'initial_value_path': ['routine_facts', key]} if alter \
                else {}
        argument_columns = [
            {'field_id': 'argmode', 'label': 'Mode', 'control': 'select',
             'required': False, 'options': [
                 {'value': mode, 'label': mode} for mode in MODES
                 if mode != 'TABLE']},
            {'field_id': 'argname', 'label': 'Argument name',
             'control': 'text', 'required': False},
            {'field_id': 'argtype', 'label': 'Data type', 'control': 'text',
             'required': True},
            {'field_id': 'argdefval', 'label': 'Default', 'control': 'text',
             'required': False}]
        fields = [
            field('name', 'Name', required=not alter, **initial('name')),
            field('pronamespace', 'Schema', required=not alter, **(
                {'help': 'A different schema runs SET SCHEMA.'} if alter
                else {}), **initial('pronamespace')),
            field('funcowner', 'Owner', help=(
                'Empty keeps the owner.' if alter else 'OWNER TO')),
            field('description', 'Comment', 'multiline',
                  **initial('description')),
            field('arguments', 'Arguments', 'grid', columns=argument_columns,
                  help=('Fixed once created.' if alter else
                        'Mode, name, type and default per argument.'),
                  **initial('arguments'))]
        if kind == 'function':
            fields.append(field(
                'prorettypename', 'Return type', required=not alter,
                help='type, SETOF type, or TABLE(column type, ...).',
                **initial('prorettypename')))
        fields += [
            field('lanname', 'Language', required=not alter,
                  **({} if alter else {'default': 'plpgsql'}),
                  **initial('lanname')),
            field('prosrc', 'Code', 'code', required=not alter,
                  **initial('prosrc'))]
        if kind == 'function':
            fields += [
                field('provolatile', 'Volatility', 'select', options=[
                    {'value': value, 'label': value.title()}
                    for value in VOLATILITY.values()],
                    **({} if alter else {'default': 'VOLATILE'}),
                    **initial('provolatile')),
                field('proisstrict', 'Strict', 'boolean',
                      **initial('proisstrict')),
                field('proleakproof', 'Leak proof', 'boolean',
                      **initial('proleakproof')),
                field('proparallel', 'Parallel', 'select', options=[
                    {'value': value, 'label': value.title()}
                    for value in PARALLEL.values()],
                    **({} if alter else {'default': 'UNSAFE'}),
                    **initial('proparallel')),
                field('procost', 'Estimated cost', 'number',
                      **initial('procost')),
                field('prorows', 'Estimated rows', 'number',
                      help='Set-returning functions only.',
                      **initial('prorows'))]
        fields += [
            field('prosecdef', 'Security of definer', 'boolean',
                  **initial('prosecdef')),
            field('variables', 'Parameters (SET)', 'grid', columns=[
                {'field_id': 'name', 'label': 'Name', 'control': 'text',
                 'required': True},
                {'field_id': 'value', 'label': 'Value', 'control': 'text',
                 'required': True}], **initial('variables'))]
    return {'form_id': f'postgresql-{kind}-{operation}',
            'form_key': f'native:postgresql:schema:{kind}',
            'title': f'{operation.title()} {label}', 'fields': fields,
            'notes': 'C-language routines, support and window functions, '
                     'privileges and security labels stay with the '
                     'inherited dialog.'}
