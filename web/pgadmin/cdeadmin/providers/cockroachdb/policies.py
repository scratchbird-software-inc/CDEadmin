"""CockroachDB row-level security policies.

Checked live on 26.1.3: CREATE POLICY name ON table [AS PERMISSIVE |
RESTRICTIVE] [FOR ALL | SELECT | INSERT | UPDATE | DELETE] [TO roles]
[USING (expr)] [WITH CHECK (expr)]; ALTER POLICY ... TO / USING / WITH
CHECK / RENAME TO; DROP POLICY ... ON table. AS and FOR cannot change
(syntax errors), and COMMENT ON POLICY is refused. A table's ENABLE /
FORCE ROW LEVEL SECURITY are table settings (tables.py).
"""
from ...sdk.relational import RelationalClientError

KINDS = ('PERMISSIVE', 'RESTRICTIVE')
COMMANDS = ('ALL', 'SELECT', 'INSERT', 'UPDATE', 'DELETE')
CREATE_KEYS = {'name', 'table', 'parent', 'policy_type', 'command', 'roles',
               'using', 'with_check'}
ALTER_KEYS = {'name', 'roles', 'using', 'with_check', 'confirmation'}


def _blank(value):
    return value is None or value == ''


def _roles(admin, value):
    if _blank(value):
        return []
    if not isinstance(value, list):
        raise RelationalClientError('roles must be a list')
    # PUBLIC is a keyword here, not a role name to quote.
    return ['PUBLIC' if str(item).lower() == 'public' else admin._quote(item)
            for item in value]


def _table(admin, draft):
    table = admin._option_path(draft, 'table')
    if len(table) == 1 and draft.get('parent'):
        table = admin._path_value(draft['parent']) + table
    return admin._qualified(table)


def create(admin, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown policy option: ' + ', '.join(sorted(unknown)))
    name = admin._quote(admin._identifier(draft.get('name')))
    source = f'CREATE POLICY {name} ON {_table(admin, draft)}'
    kind = str(draft.get('policy_type') or 'PERMISSIVE').upper()
    command = str(draft.get('command') or 'ALL').upper()
    if kind not in KINDS:
        raise RelationalClientError('policy type is PERMISSIVE or RESTRICTIVE')
    if command not in COMMANDS:
        raise RelationalClientError(
            'command is one of: ' + ', '.join(COMMANDS))
    source += f' AS {kind} FOR {command}'
    roles = _roles(admin, draft.get('roles'))
    if roles:
        source += ' TO ' + ', '.join(roles)
    if not _blank(draft.get('using')):
        if command == 'INSERT':
            raise RelationalClientError('an INSERT policy has no USING')
        source += ' USING (' + admin._safe_fragment(draft['using'],
                                                    'USING') + ')'
    if not _blank(draft.get('with_check')):
        if command in {'SELECT', 'DELETE'}:
            raise RelationalClientError(
                f'a {command} policy has no WITH CHECK')
        source += ' WITH CHECK (' + admin._safe_fragment(
            draft['with_check'], 'WITH CHECK') + ')'
    return [{'source': source, 'parameters': ()}]


def alter(admin, draft, target, engine='CockroachDB'):
    # engine: the name in refusals; YugabyteDB YSQL shares these rules.
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            ', '.join(sorted(unknown)) + ' cannot change in place; '
            f'{engine} fixes AS and FOR when the policy is created')
    native = (target or {}).get('native') or {}
    path = admin._target_path(target)
    head = f'ALTER POLICY {admin._quote(path[-1])} ON ' + admin._qualified(
        path[:-1])
    clauses = []
    if 'roles' in draft and sorted(draft['roles'] or []) != sorted(
            native.get('roles') or []):
        roles = _roles(admin, draft['roles']) or ['PUBLIC']
        clauses.append('TO ' + ', '.join(roles))
    for key, keyword in (('using', 'USING'), ('with_check', 'WITH CHECK')):
        if key in draft and (draft[key] or None) != (native.get(key) or None):
            if _blank(draft[key]):
                # Live: ALTER POLICY ... (NULL) stores NULL, which refuses
                # every row, and nothing removes the clause. Drop and create
                # would leave the table unguarded in between.
                raise RelationalClientError(
                    f'{engine} cannot remove a policy\'s {keyword}; '
                    'drop the policy and create it without one')
            clauses.append(f'{keyword} (' + admin._safe_fragment(
                draft[key], keyword) + ')')
    statements = []
    if clauses:
        statements.append({'source': head + ' ' + ' '.join(clauses),
                           'parameters': ()})
    if draft.get('name') not in (None, '', path[-1]):
        statements.append({'source': (
            f'{head} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def drop(admin, target):
    path = admin._target_path(target)
    return [{'source': (f'DROP POLICY {admin._quote(path[-1])} ON '
                        f'{admin._qualified(path[:-1])}'), 'parameters': ()}]


def form(field, operation):
    fields = [field('name', 'Name', 'text', True)]
    if operation == 'create':
        fields += [field('table', 'Table', 'text', True, 'schema.table'),
                   field('policy_type', 'Type', 'select', False,
                         default='PERMISSIVE', options=KINDS),
                   field('command', 'Command', 'select', False,
                         default='ALL', options=COMMANDS)]
    fields += [field('using', 'USING expression', 'code', False,
                     'Rows the policy lets a statement see or change.'),
               field('with_check', 'WITH CHECK expression', 'code', False,
                     'Rows an INSERT or UPDATE may write.')]
    if operation == 'alter':
        for item in fields:
            item['initial_value_path'] = [item['field_id']]
    return {'form_id': f'cockroachdb.row-policy.{operation}',
            'title': f'{operation.title()} row security policy',
            'fields': fields,
            'notes': 'Roles are a descriptor grid (row-policy.form.json).'}
