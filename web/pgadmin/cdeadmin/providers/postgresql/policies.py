"""PostgreSQL row-level security policies on the provider tree (M4,
2026-11-11).

CREATE POLICY name ON table [AS PERMISSIVE | RESTRICTIVE] [FOR command]
[TO roles] [USING (expr)] [WITH CHECK (expr)]; ALTER POLICY ... TO / USING
/ WITH CHECK / RENAME TO; COMMENT ON POLICY; DROP POLICY ... ON table. AS
and FOR are fixed once created, and a clause cannot be removed in place
(ALTER POLICY ... USING (NULL) stores NULL, which refuses every row).
Field ids follow the inherited dialog (``row_security_policy.ui.js``:
name, event, using, withcheck, policyowner, type, description).

Expressions are the user's SQL; they are admitted only when PostgreSQL's
own parser (pglast) reads them as exactly one expression with no statement
separator or comment, then placed verbatim inside parentheses.
"""
from .native_admin import (
    PostgreSQLNativeAdminError, _identifier, _literal, _name, _qualified,
)

KINDS = ('PERMISSIVE', 'RESTRICTIVE')
COMMANDS = ('ALL', 'SELECT', 'INSERT', 'UPDATE', 'DELETE')
_COMMAND_CODES = {'*': 'ALL', 'r': 'SELECT', 'a': 'INSERT', 'w': 'UPDATE',
                  'd': 'DELETE'}


def _blank(value):
    return value is None or value == ''


def expression(value, label):
    """One SQL expression, admitted by PostgreSQL's own parser."""
    if not isinstance(value, str) or not value.strip():
        raise PostgreSQLNativeAdminError(f'{label} must not be empty')
    value = value.strip()
    if ';' in value or '--' in value or '/*' in value or '\x00' in value:
        raise PostgreSQLNativeAdminError(f'{label} contains unsafe syntax')
    # Parentheses must balance inside the fragment, or "a) OR (b" would
    # read as two clauses once wrapped.
    depth = 0
    for char in value:
        depth += {'(': 1, ')': -1}.get(char, 0)
        if depth < 0:
            raise PostgreSQLNativeAdminError(
                f'{label} contains unsafe syntax')
    if depth:
        raise PostgreSQLNativeAdminError(f'{label} contains unsafe syntax')
    from pglast import parse_sql
    from pglast.parser import ParseError
    try:
        statements = parse_sql(f'SELECT ({value})')
    except ParseError as exc:
        raise PostgreSQLNativeAdminError(
            f'{label} is not a valid expression: {exc}') from None
    if len(statements) != 1:
        raise PostgreSQLNativeAdminError(f'{label} contains unsafe syntax')
    return value


def _roles(value):
    if _blank(value):
        return []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(',') if part.strip()]
    if not isinstance(value, list):
        raise PostgreSQLNativeAdminError('roles must be a list of names')
    roles = []
    for item in value:
        if isinstance(item, dict):
            item = item.get('role')
        name = _name(item, 'role')
        roles.append('PUBLIC' if name.upper() == 'PUBLIC'
                     else _identifier(name, 'role'))
    return roles


def facts(native, relations=None):
    """The target's current values: table, kind, command, roles,
    expressions, comment. ``relations`` maps relation OID -> (schema,
    name) from the same capture."""
    row = native.get('catalog_row') or {}
    try:
        relation = int(row.get('polrelid'))
    except (TypeError, ValueError):
        relation = None
    schema, table = (relations or {}).get(relation, (native.get('schema'),
                                                     None))
    return {
        'name': native.get('name') or row.get('polname'),
        'schema': schema, 'table': table,
        'type': 'PERMISSIVE' if row.get('polpermissive', True)
        else 'RESTRICTIVE',
        'event': _COMMAND_CODES.get(row.get('polcmd'), 'ALL'),
        'roles': list(row.get('roles_sql') or []),
        'using': row.get('using_sql'),
        'withcheck': row.get('check_sql'),
        'description': native.get('comment'),
    }


def _table(draft, current=None):
    source = current if current is not None else draft
    schema = _name(source.get('schema'), 'schema')
    table = _name(source.get('table'), 'table')
    return _qualified(schema, table)


def _comment(name, table, value):
    text = 'NULL' if _blank(value) else _literal(str(value), 'comment')
    return f'COMMENT ON POLICY {name} ON {table} IS {text}'


def _create(draft):
    name = _identifier(draft.get('name'), 'name')
    table = _table(draft)
    kind = str(draft.get('type') or 'PERMISSIVE').upper()
    command = str(draft.get('event') or 'ALL').upper()
    if kind not in KINDS:
        raise PostgreSQLNativeAdminError(
            'policy type is PERMISSIVE or RESTRICTIVE')
    if command not in COMMANDS:
        raise PostgreSQLNativeAdminError(
            'event is one of: ' + ', '.join(COMMANDS))
    statement = f'CREATE POLICY {name} ON {table} AS {kind} FOR {command}'
    roles = _roles(draft.get('policyowner'))
    if roles:
        statement += ' TO ' + ', '.join(roles)
    if not _blank(draft.get('using')):
        if command == 'INSERT':
            raise PostgreSQLNativeAdminError('an INSERT policy has no USING')
        statement += ' USING (' + expression(draft['using'], 'USING') + ')'
    if not _blank(draft.get('withcheck')):
        if command in {'SELECT', 'DELETE'}:
            raise PostgreSQLNativeAdminError(
                f'a {command} policy has no WITH CHECK')
        statement += ' WITH CHECK (' + expression(
            draft['withcheck'], 'WITH CHECK') + ')'
    statements = [statement]
    if not _blank(draft.get('description')):
        statements.append(_comment(name, table, draft['description']))
    return statements


def _current(native):
    # The listing resolved the table from the same capture; a bare native
    # (no listing) falls back to what the row alone can say.
    return native.get('policy_facts') or facts(native)


def _alter(native, draft):
    current = _current(native)
    for key in ('type', 'event'):
        if not _blank(draft.get(key)) and str(draft[key]).upper() != \
                current[key]:
            raise PostgreSQLNativeAdminError(
                'the policy type and event are fixed when the policy is '
                'created; drop and create the policy to change them')
    table = _table(draft, current)
    name = _identifier(current['name'], 'name')
    head = f'ALTER POLICY {name} ON {table}'
    clauses = []
    if 'policyowner' in draft and not _blank(draft['policyowner']):
        roles = _roles(draft['policyowner'])
        if sorted(roles) != sorted(
                'PUBLIC' if role.upper() == 'PUBLIC' else
                _identifier(role, 'role') for role in current['roles']):
            clauses.append('TO ' + ', '.join(roles))
    for key, keyword in (('using', 'USING'), ('withcheck', 'WITH CHECK')):
        if key not in draft or (draft[key] or None) == (
                current[key] or None):
            continue
        if _blank(draft[key]):
            raise PostgreSQLNativeAdminError(
                f'a policy\'s {keyword} cannot be removed in place; drop '
                'the policy and create it without one')
        clauses.append(f'{keyword} (' + expression(draft[key], keyword) + ')')
    statements = []
    if clauses:
        statements.append(head + ' ' + ' '.join(clauses))
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        statements.append(_comment(name, table, draft['description']))
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != current['name']:
        statements.append(f'{head} RENAME TO '
                          + _identifier(new_name, 'name'))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _drop(native, draft):
    current = _current(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    return [f'DROP POLICY {_identifier(name, "name")} ON '
            f'{_table(draft, current)}']


def compile_operation(operation, native, draft):
    """One exact native text for the policy lifecycle."""
    if operation == 'create':
        statements = _create(draft)
    elif operation == 'alter':
        statements = _alter(native, draft)
    elif operation == 'drop':
        statements = _drop(native, draft)
    else:
        raise PostgreSQLNativeAdminError(
            'policy inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


def form(operation, field):
    """Dialog fields; ids follow the inherited policy dialog."""
    options = [{'value': item, 'label': item} for item in COMMANDS]
    kinds = [{'value': item, 'label': item.title()} for item in KINDS]
    if operation == 'drop':
        return {'form_id': 'postgresql-row-policy-drop',
                'form_key': 'native:postgresql:schema:row-policy',
                'title': 'Drop row security policy',
                'fields': [field('confirmation',
                                 'Type the policy name to confirm',
                                 required=True)]}
    alter = operation == 'alter'
    initial = (lambda key: {'initial_value_path': ['policy_facts', key]}) \
        if alter else (lambda key: {})
    fields = [field('name', 'Name', required=not alter, **initial('name'))]
    if not alter:
        fields += [field('schema', 'Schema', required=True),
                   field('table', 'Table', required=True),
                   field('type', 'Type', 'select', options=kinds,
                         default='PERMISSIVE'),
                   field('event', 'Event', 'select', options=options,
                         default='ALL')]
    fields += [
        field('policyowner', 'Roles (TO)', help=(
            'Comma-separated role names; PUBLIC for everyone.' +
            (' Empty keeps the current roles.' if alter else ''))),
        field('using', 'USING expression', 'code', help=(
            'Rows the policy lets a statement see or change.'),
            **initial('using')),
        field('withcheck', 'WITH CHECK expression', 'code', help=(
            'Rows an INSERT or UPDATE may write.'), **initial('withcheck')),
        field('description', 'Comment', 'multiline',
              **initial('description'))]
    return {'form_id': f'postgresql-row-policy-{operation}',
            'form_key': 'native:postgresql:schema:row-policy',
            'title': f'{operation.title()} row security policy',
            'fields': fields}
