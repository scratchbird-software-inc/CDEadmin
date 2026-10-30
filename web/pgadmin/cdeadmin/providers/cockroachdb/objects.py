"""CockroachDB triggers, users and roles: only what 26.1 accepts.

Every clause here was checked live on 26.1.3 (docs/en_US/
postgresql_wire_parity.rst). Triggers are row-level, BEFORE or AFTER, on
INSERT, UPDATE or DELETE, and cannot be altered, replaced or commented on.
Users and roles are one kind of principal; a user is a role with LOGIN.
"""
from ...sdk.relational import RelationalClientError

OPERATIONS = {
    'trigger': frozenset({'create'}),
    'user': frozenset({'create', 'alter', 'drop'}),
    'role': frozenset({'create', 'alter', 'drop'}),
}

TIMINGS = ('BEFORE', 'AFTER')
EVENTS = ('INSERT', 'UPDATE', 'DELETE')
# Role options CockroachDB 26.1 accepts, each with a NO form. SUPERUSER,
# INHERIT and CONNECTION LIMIT are refused; LOGIN, SQLLOGIN, PASSWORD and
# VALID UNTIL have their own fields.
PRIVILEGES = (
    'CREATEDB', 'CREATEROLE', 'CREATELOGIN', 'CONTROLJOB',
    'CONTROLCHANGEFEED', 'CANCELQUERY', 'VIEWACTIVITY',
    'VIEWACTIVITYREDACTED', 'VIEWCLUSTERSETTING', 'MODIFYCLUSTERSETTING',
    'REPLICATION', 'BYPASSRLS',
)
_PRINCIPAL_KEYS = {'name', 'login', 'sql_login', 'password',
                   'clear_password', 'valid_until', 'privileges',
                   'member_of'}
_TRIGGER_KEYS = {'name', 'parent', 'table', 'timing', 'events',
                 'function', 'arguments', 'when'}


def form(kind, operation, field):
    if kind == 'trigger':
        return {'form_id': 'cockroachdb.trigger.create',
                'title': 'Create CockroachDB trigger', 'fields': [
                    field('name', 'Name', 'text', True),
                    field('table', 'Table', 'text', True,
                          'schema.table'),
                    field('timing', 'Timing', 'select', True,
                          default='BEFORE', options=TIMINGS),
                    field('events', 'Events', 'multiselect', True,
                          default=['INSERT'], options=EVENTS),
                    field('function', 'Trigger function', 'text', True,
                          'schema.function; it returns TRIGGER.'),
                    field('arguments', 'Function arguments', 'json', False,
                          'String constants passed to the function.', []),
                    field('when', 'WHEN condition', 'code', False,
                          'Write row fields as (NEW).column or '
                          '(OLD).column; NEW.column is refused.'),
                ]}
    if operation == 'drop':
        return {'form_id': f'cockroachdb.{kind}.drop',
                'title': f'Drop CockroachDB {kind}',
                'fields': [field('confirmation', 'Confirmation', 'text',
                                 True)]}
    creating = operation == 'create'
    fields = []
    if creating:
        fields.append(field('name', 'Name', 'text', True))
    fields += [
        field('login', 'Can log in', 'boolean', False,
              default=(kind == 'user') if creating else None),
        field('sql_login', 'SQL login', 'boolean', False,
              'Off (NOSQLLOGIN) still allows the DB Console.',
              default=True if creating else None),
        field('password', 'Password', 'password', False,
              'Optional; a cluster in insecure mode refuses passwords. '
              'The value is redacted from validation and plans.',
              sensitive=True),
    ]
    if not creating:
        fields.append(field('clear_password', 'Remove password', 'boolean',
                            False, default=False))
    fields += [
        field('valid_until', 'Valid until', 'text', False,
              'A timestamp; empty means no expiry.'),
        field('privileges', 'Role options', 'multiselect', False,
              options=PRIVILEGES, default=[] if creating else None),
        field('member_of', 'Member of', 'json', False,
              'Role names this principal is granted.',
              [] if creating else None),
    ]
    if not creating:
        # The record carries these (principal_native); never the password.
        for item in fields:
            if item['field_id'] in {'login', 'sql_login', 'valid_until',
                                    'privileges', 'member_of'}:
                item['initial_value_path'] = [item['field_id']]
    return {'form_id': f'cockroachdb.{kind}.{operation}',
            'title': f'{operation.title()} CockroachDB {kind}',
            'fields': fields}


def compile_operation(admin, kind, operation, draft, target):
    if operation not in OPERATIONS.get(kind, ()) or not isinstance(
            draft, dict):
        raise RelationalClientError('CockroachDB operation is unavailable')
    if kind == 'trigger':
        return [_trigger(admin, draft)]
    if operation == 'drop':
        name = (target or {}).get('display_name')
        return [{'source': f'DROP ROLE {admin._quote(name)}',
                 'parameters': ()}]
    unknown = set(draft) - _PRINCIPAL_KEYS - {'confirmation'}
    if unknown:
        raise RelationalClientError(
            'unknown option: ' + ', '.join(sorted(unknown)))
    if operation == 'create':
        return _create_principal(admin, kind, draft)
    return _alter_principal(admin, draft, target or {})


def _trigger(admin, draft):
    unknown = set(draft) - _TRIGGER_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown trigger option: ' + ', '.join(sorted(unknown)))
    name = admin._quote(draft.get('name'))
    table = admin._option_path(draft, 'table')
    if len(table) == 1 and draft.get('parent'):
        # The navigator passes the schema it was opened from.
        table = admin._path_value(draft['parent']) + table
    table = admin._qualified(table)
    timing = draft.get('timing')
    if timing not in TIMINGS:
        raise RelationalClientError(
            'CockroachDB triggers are BEFORE or AFTER (no INSTEAD OF)')
    events = draft.get('events')
    if not isinstance(events, list) or not events or any(
            item not in EVENTS for item in events) or len(
                set(events)) != len(events):
        raise RelationalClientError(
            'select one or more of INSERT, UPDATE, DELETE')
    function = list(admin._option_path(draft, 'function'))
    # Routine resources are named name(arguments); a trigger function's
    # argument list is empty.
    if function[-1].endswith('()'):
        function[-1] = function[-1][:-2]
    function = admin._qualified(function)
    arguments = draft.get('arguments') or []
    if not isinstance(arguments, list) or any(
            not isinstance(item, str) for item in arguments):
        raise RelationalClientError('trigger arguments must be strings')
    if any("'" in item for item in arguments):
        # Live, 26.1.3: CockroachDB re-renders the statement with the quote
        # unescaped and fails to parse it, however the literal is written.
        raise RelationalClientError(
            "CockroachDB cannot store a trigger argument containing '")
    source = (f'CREATE TRIGGER {name} {timing} {" OR ".join(events)} ON '
              f'{table} FOR EACH ROW')
    when = draft.get('when')
    if when not in (None, ''):
        source += ' WHEN (' + admin._safe_fragment(
            when, 'WHEN condition') + ')'
    source += (f' EXECUTE FUNCTION {function}(' +
               ', '.join(admin._literal(item) for item in arguments) + ')')
    return {'source': source, 'parameters': ()}


def _privileges(value):
    if value is None:
        return []
    if not isinstance(value, list) or any(
            item not in PRIVILEGES for item in value):
        raise RelationalClientError(
            'role options must come from: ' + ', '.join(PRIVILEGES))
    return list(dict.fromkeys(value))


def _roles(admin, value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise RelationalClientError('member of must be a list of roles')
    return [admin._identifier(item) for item in dict.fromkeys(value)]


def _boolean(draft, key):
    value = draft.get(key)
    if value is not None and not isinstance(value, bool):
        raise RelationalClientError(f'{key} must be true or false')
    return value


def _valid_until(admin, value):
    if value in (None, ''):
        return 'VALID UNTIL NULL'
    return 'VALID UNTIL ' + admin._literal(str(value))


def _password(admin, draft, clauses, previews):
    password = draft.get('password')
    if password in (None, ''):
        return
    if not isinstance(password, str):
        raise RelationalClientError('password must be text')
    clauses.append('PASSWORD ' + admin._literal(password))
    previews.append('PASSWORD <redacted>')


def _statement(prefix, clauses, previews):
    if not clauses:
        return None
    return {'source': f'{prefix} WITH ' + ' '.join(clauses),
            'preview_source': f'{prefix} WITH ' + ' '.join(previews),
            'parameters': ()}


def _create_principal(admin, kind, draft):
    name = admin._quote(draft.get('name'))
    clauses = []
    login = _boolean(draft, 'login')
    if login is None:
        login = kind == 'user'
    clauses.append('LOGIN' if login else 'NOLOGIN')
    if _boolean(draft, 'sql_login') is False:
        clauses.append('NOSQLLOGIN')
    previews = list(clauses)
    _password(admin, draft, clauses, previews)
    if draft.get('valid_until') not in (None, ''):
        clauses.append(_valid_until(admin, draft['valid_until']))
        previews.append(clauses[-1])
    for item in _privileges(draft.get('privileges')):
        clauses.append(item)
        previews.append(item)
    keyword = 'USER' if kind == 'user' else 'ROLE'
    statements = [_statement(f'CREATE {keyword} {name}', clauses, previews)]
    for role in _roles(admin, draft.get('member_of')):
        statements.append({'source': f'GRANT {admin._quote(role)} TO {name}',
                           'parameters': ()})
    return statements


def _alter_principal(admin, draft, target):
    native = target.get('native') or {}
    name = admin._quote(target.get('display_name'))
    clauses, previews = [], []
    for key, on, off in (('login', 'LOGIN', 'NOLOGIN'),
                         ('sql_login', 'SQLLOGIN', 'NOSQLLOGIN')):
        value = _boolean(draft, key)
        if value is not None and value != native.get(key):
            clauses.append(on if value else off)
            previews.append(clauses[-1])
    if _boolean(draft, 'clear_password'):
        if draft.get('password') not in (None, ''):
            raise RelationalClientError(
                'set a password or remove it, not both')
        clauses.append('PASSWORD NULL')
        previews.append('PASSWORD NULL')
    else:
        _password(admin, draft, clauses, previews)
    if 'valid_until' in draft and (draft['valid_until'] or None) != (
            native.get('valid_until') or None):
        clauses.append(_valid_until(admin, draft['valid_until']))
        previews.append(clauses[-1])
    if 'privileges' in draft:
        wanted = set(_privileges(draft['privileges']))
        held = set(native.get('privileges') or ())
        for item in PRIVILEGES:
            if item in wanted - held:
                clauses.append(item)
            elif item in held - wanted:
                clauses.append('NO' + item)
            else:
                continue
            previews.append(clauses[-1])
    statements = []
    altered = _statement(f'ALTER ROLE {name}', clauses, previews)
    if altered:
        statements.append(altered)
    if 'member_of' in draft:
        wanted = _roles(admin, draft['member_of'])
        held = list(native.get('member_of') or ())
        for role in wanted:
            if role not in held:
                statements.append({
                    'source': f'GRANT {admin._quote(role)} TO {name}',
                    'parameters': ()})
        for role in held:
            if role not in wanted:
                statements.append({
                    'source': f'REVOKE {admin._quote(role)} FROM {name}',
                    'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def principal_native(options, member_of, can_login, valid_until):
    """The record a user or role editor reopens, from SHOW ROLES."""
    options = [str(item) for item in options or ()]
    return {
        'login': bool(can_login),
        'sql_login': 'NOSQLLOGIN' not in options,
        'privileges': [item for item in PRIVILEGES if item in options],
        'valid_until': None if valid_until is None else str(valid_until),
        'member_of': sorted(str(item) for item in member_of or ()),
        'options': options,
    }


_TIMING_BITS = {2: 'BEFORE', 64: 'INSTEAD OF'}
_EVENT_BITS = ((4, 'INSERT'), (16, 'UPDATE'), (8, 'DELETE'),
               (32, 'TRUNCATE'))


def trigger_native(table_path, tgtype, enabled, function_path, arguments,
                   when):
    """Decode pg_trigger into the fields the trigger form takes."""
    tgtype = int(tgtype)
    raw = bytes(arguments or b'')
    values = raw.split(b'\x00')[:-1] if raw else []
    return {
        'table': list(table_path),
        'timing': next((label for bit, label in _TIMING_BITS.items()
                        if tgtype & bit), 'AFTER'),
        'events': [label for bit, label in _EVENT_BITS if tgtype & bit],
        'row_level': bool(tgtype & 1),
        # As the function's resource is named: name(), no arguments.
        'function': [*function_path[:-1], f'{function_path[-1]}()'],
        'arguments': [item.decode('utf-8') for item in values],
        'when': None if when is None else _unwrap(str(when)),
        'enabled': str(enabled) != 'D',
    }


def _unwrap(text):
    """pg_trigger keeps the WHEN clause in its own outer parentheses."""
    if text.startswith('(') and text.endswith(')'):
        depth = 0
        for index, char in enumerate(text):
            depth += char == '('
            depth -= char == ')'
            if depth == 0 and index < len(text) - 1:
                return text
        return text[1:-1]
    return text
