"""YugabyteDB YSQL triggers, users and roles: the PostgreSQL 15 surface.

Checked live on 2025.2.2.2 (docs/en_US/postgresql_wire_parity.rst):
triggers BEFORE / AFTER / INSTEAD OF, FOR EACH ROW or STATEMENT, INSERT /
UPDATE [OF columns] / DELETE / TRUNCATE, WHEN, CREATE OR REPLACE, ALTER
TRIGGER ... RENAME, ENABLE / DISABLE, COMMENT ON TRIGGER. Refused:
transition tables (REFERENCING). Roles take PostgreSQL's options,
CONNECTION LIMIT, RENAME and COMMENT ON ROLE.

Field ids match the CockroachDB forms where the concept is the same
(providers/cockroachdb/objects.py); options either engine lacks are not
offered for it.
"""
from ...sdk.relational import RelationalClientError

OPERATIONS = {
    'trigger': frozenset({'create', 'alter'}),
    'user': frozenset({'create', 'alter', 'drop'}),
    'role': frozenset({'create', 'alter', 'drop'}),
}
TIMINGS = ('BEFORE', 'AFTER', 'INSTEAD OF')
EVENTS = ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
LEVELS = ('ROW', 'STATEMENT')
ENABLED = ('ORIGIN', 'DISABLED', 'REPLICA', 'ALWAYS')
# PostgreSQL role options (each with a NO form). LOGIN and PASSWORD,
# VALID UNTIL and CONNECTION LIMIT have their own fields.
PRIVILEGES = ('SUPERUSER', 'CREATEDB', 'CREATEROLE', 'INHERIT',
              'REPLICATION', 'BYPASSRLS')
_TRIGGER_KEYS = {'name', 'parent', 'table', 'timing', 'events',
                 'update_columns', 'level', 'function', 'arguments', 'when',
                 'enabled', 'comment', 'confirmation'}
_PRINCIPAL_KEYS = {'name', 'login', 'password', 'clear_password',
                   'valid_until', 'privileges', 'member_of',
                   'connection_limit', 'comment', 'confirmation'}


def _blank(value):
    return value is None or value == ''


# --- triggers -------------------------------------------------------------

def _function(admin, value):
    path = list(admin._path_value(value))
    # Routine resources are named name(arguments); a trigger function's
    # argument list is empty.
    if path[-1].endswith('()'):
        path[-1] = path[-1][:-2]
    return admin._qualified(path)


def _trigger_definition(admin, name, table, values, replace=False):
    timing = values.get('timing')
    if timing not in TIMINGS:
        raise RelationalClientError(
            'timing is one of: ' + ', '.join(TIMINGS))
    events = values.get('events')
    if not isinstance(events, list) or not events or any(
            item not in EVENTS for item in events) or len(
                set(events)) != len(events):
        raise RelationalClientError(
            'select one or more of ' + ', '.join(EVENTS))
    level = values.get('level') or 'ROW'
    if level not in LEVELS:
        raise RelationalClientError('level is ROW or STATEMENT')
    if timing == 'INSTEAD OF' and level != 'ROW':
        raise RelationalClientError('an INSTEAD OF trigger is row-level')
    if 'TRUNCATE' in events and level != 'STATEMENT':
        raise RelationalClientError('a TRUNCATE trigger is statement-level')
    columns = values.get('update_columns') or []
    rendered = []
    for event in events:
        if event == 'UPDATE' and columns:
            rendered.append('UPDATE OF ' + admin._identifier_list(columns))
        else:
            rendered.append(event)
    if columns and 'UPDATE' not in events:
        raise RelationalClientError('columns apply to an UPDATE event')
    arguments = values.get('arguments') or []
    if not isinstance(arguments, list) or any(
            not isinstance(item, str) for item in arguments):
        raise RelationalClientError('trigger arguments must be strings')
    source = (f'CREATE {"OR REPLACE " if replace else ""}TRIGGER {name} '
              f'{timing} {" OR ".join(rendered)} ON {table} '
              f'FOR EACH {level}')
    if not _blank(values.get('when')):
        when = admin._safe_fragment(values['when'], 'WHEN condition')
        source += f' WHEN ({when})'
    function = _function(admin, values.get('function'))
    literals = ', '.join(admin._literal(item) for item in arguments)
    return source + f' EXECUTE FUNCTION {function}({literals})'


def _enable(admin, table, name, value):
    if value not in ENABLED:
        raise RelationalClientError(
            'enabled is one of: ' + ', '.join(ENABLED))
    clause = {'ORIGIN': 'ENABLE', 'DISABLED': 'DISABLE',
              'REPLICA': 'ENABLE REPLICA', 'ALWAYS': 'ENABLE ALWAYS'}[value]
    return {'source': f'ALTER TABLE {table} {clause} TRIGGER {name}',
            'parameters': ()}


def _trigger_comment(admin, table, name, value):
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON TRIGGER {name} ON {table} IS {text}',
            'parameters': ()}


def _trigger_create(admin, draft):
    table = admin._option_path(draft, 'table')
    if len(table) == 1 and draft.get('parent'):
        table = admin._path_value(draft['parent']) + table
    table = admin._qualified(table)
    name = admin._quote(admin._identifier(draft.get('name')))
    statements = [{'source': _trigger_definition(admin, name, table, draft),
                   'parameters': ()}]
    if draft.get('enabled') not in (None, '', 'ORIGIN'):
        statements.append(_enable(admin, table, name, draft['enabled']))
    if not _blank(draft.get('comment')):
        statements.append(_trigger_comment(admin, table, name,
                                           draft['comment']))
    return statements


_DEFINITION_KEYS = ('timing', 'events', 'update_columns', 'level',
                    'function', 'arguments', 'when')


def _trigger_alter(admin, draft, target):
    native = (target or {}).get('native') or {}
    path = admin._target_path(target)
    table = admin._qualified(path[:-1])
    name = admin._quote(path[-1])
    statements = []
    if any(key in draft and draft[key] != native.get(key)
           for key in _DEFINITION_KEYS):
        values = {key: draft.get(key, native.get(key))
                  for key in _DEFINITION_KEYS}
        statements.append({'source': _trigger_definition(
            admin, name, table, values, replace=True), 'parameters': ()})
    if 'enabled' in draft and draft['enabled'] != native.get('enabled'):
        statements.append(_enable(admin, table, name, draft['enabled']))
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_trigger_comment(admin, table, name,
                                           draft['comment']))
    if draft.get('name') not in (None, '', path[-1]):
        statements.append({'source': (
            f'ALTER TRIGGER {name} ON {table} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


# --- users and roles ------------------------------------------------------

def _privileges(value):
    if value is None:
        return []
    if not isinstance(value, list) or any(
            item not in PRIVILEGES for item in value):
        raise RelationalClientError(
            'role options must come from: ' + ', '.join(PRIVILEGES))
    return list(dict.fromkeys(value))


def _connection_limit(value):
    if _blank(value):
        return -1
    if isinstance(value, bool) or not isinstance(value, int) or value < -1:
        raise RelationalClientError(
            'connection limit is a whole number, -1 for none')
    return value


def _principal_comment(admin, name, value):
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON ROLE {name} IS {text}', 'parameters': ()}


def _with(prefix, clauses, previews):
    return {'source': f'{prefix} WITH ' + ' '.join(clauses),
            'preview_source': f'{prefix} WITH ' + ' '.join(previews),
            'parameters': ()}


def _principal_create(admin, kind, draft):
    name = admin._quote(admin._identifier(draft.get('name')))
    login = draft.get('login')
    if login is None:
        login = kind == 'user'
    clauses = ['LOGIN' if login else 'NOLOGIN']
    clauses += _privileges(draft.get('privileges'))
    held = set(clauses)
    # PostgreSQL defaults INHERIT on; an unticked INHERIT means NOINHERIT.
    if 'INHERIT' not in held:
        clauses.append('NOINHERIT')
    limit = _connection_limit(draft.get('connection_limit'))
    if limit != -1:
        clauses.append(f'CONNECTION LIMIT {limit}')
    if not _blank(draft.get('valid_until')):
        clauses.append('VALID UNTIL ' + admin._literal(
            str(draft['valid_until'])))
    previews = list(clauses)
    if not _blank(draft.get('password')):
        clauses.append('PASSWORD ' + admin._literal(str(draft['password'])))
        previews.append('PASSWORD <redacted>')
    keyword = 'USER' if kind == 'user' else 'ROLE'
    statements = [_with(f'CREATE {keyword} {name}', clauses, previews)]
    for role in draft.get('member_of') or []:
        statements.append({'source': f'GRANT {admin._quote(role)} TO {name}',
                           'parameters': ()})
    if not _blank(draft.get('comment')):
        statements.append(_principal_comment(admin, name, draft['comment']))
    return statements


def _principal_alter(admin, draft, target):
    native = (target or {}).get('native') or {}
    current = (target or {}).get('display_name')
    name = admin._quote(current)
    clauses, previews = [], []
    if draft.get('login') is not None and draft['login'] != native.get(
            'login'):
        clauses.append('LOGIN' if draft['login'] else 'NOLOGIN')
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
    if 'connection_limit' in draft:
        limit = _connection_limit(draft['connection_limit'])
        if limit != native.get('connection_limit', -1):
            clauses.append(f'CONNECTION LIMIT {limit}')
            previews.append(clauses[-1])
    if 'valid_until' in draft and (draft['valid_until'] or None) != (
            native.get('valid_until') or None):
        clauses.append('VALID UNTIL ' + (
            "'infinity'" if _blank(draft['valid_until'])
            else admin._literal(str(draft['valid_until']))))
        previews.append(clauses[-1])
    if draft.get('clear_password'):
        if not _blank(draft.get('password')):
            raise RelationalClientError(
                'set a password or remove it, not both')
        clauses.append('PASSWORD NULL')
        previews.append('PASSWORD NULL')
    elif not _blank(draft.get('password')):
        clauses.append('PASSWORD ' + admin._literal(str(draft['password'])))
        previews.append('PASSWORD <redacted>')
    statements = [_with(f'ALTER ROLE {name}', clauses, previews)] if (
        clauses) else []
    if 'member_of' in draft:
        wanted = list(dict.fromkeys(draft['member_of'] or []))
        held = list(native.get('member_of') or [])
        statements += [{'source': f'GRANT {admin._quote(role)} TO {name}',
                        'parameters': ()} for role in wanted
                       if role not in held]
        statements += [{'source': f'REVOKE {admin._quote(role)} FROM {name}',
                        'parameters': ()} for role in held
                       if role not in wanted]
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_principal_comment(admin, name, draft['comment']))
    if draft.get('name') not in (None, '', current):
        statements.append({'source': (
            f'ALTER ROLE {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def compile_operation(admin, kind, operation, draft, target):
    if operation not in OPERATIONS.get(kind, ()) or not isinstance(
            draft, dict):
        raise RelationalClientError('YugabyteDB operation is unavailable')
    keys = _TRIGGER_KEYS if kind == 'trigger' else _PRINCIPAL_KEYS
    unknown = set(draft) - keys
    if unknown:
        raise RelationalClientError(
            'unknown option: ' + ', '.join(sorted(unknown)))
    if kind == 'trigger':
        return (_trigger_create(admin, draft) if operation == 'create'
                else _trigger_alter(admin, draft, target))
    if operation == 'drop':
        return [{'source': 'DROP ROLE ' + admin._quote(
            (target or {}).get('display_name')), 'parameters': ()}]
    if operation == 'create':
        return _principal_create(admin, kind, draft)
    return _principal_alter(admin, draft, target)


# --- catalog records ------------------------------------------------------

_EVENT_BITS = ((4, 'INSERT'), (16, 'UPDATE'), (8, 'DELETE'),
               (32, 'TRUNCATE'))
_ENABLED = {'O': 'ORIGIN', 'D': 'DISABLED', 'R': 'REPLICA', 'A': 'ALWAYS'}


def trigger_native(table_path, tgtype, enabled, function_path, arguments,
                   when, update_columns, comment):
    """Decode pg_trigger into the trigger form's fields."""
    tgtype = int(tgtype)
    raw = bytes(arguments or b'')
    return {
        'table': '.'.join(table_path),
        'timing': ('INSTEAD OF' if tgtype & 64 else
                   'BEFORE' if tgtype & 2 else 'AFTER'),
        'level': 'ROW' if tgtype & 1 else 'STATEMENT',
        'events': [label for bit, label in _EVENT_BITS if tgtype & bit],
        'update_columns': list(update_columns or []),
        'function': '.'.join([*function_path[:-1],
                              f'{function_path[-1]}()']),
        'arguments': [item.decode('utf-8')
                      for item in raw.split(b'\x00')[:-1]] if raw else [],
        'when': when,
        'enabled': _ENABLED.get(str(enabled), 'ORIGIN'),
        'comment': comment,
    }


def principal_native(row, member_of, comment):
    """pg_roles facts as the user and role forms' fields."""
    (can_login, superuser, createdb, createrole, inherit, replication,
     bypassrls, limit, valid_until) = row
    flags = dict(zip(PRIVILEGES, (superuser, createdb, createrole, inherit,
                                  replication, bypassrls)))
    return {
        'login': bool(can_login),
        'privileges': [item for item in PRIVILEGES if flags[item]],
        'connection_limit': int(limit) if limit is not None else -1,
        'valid_until': None if valid_until in (None, 'infinity') else str(
            valid_until),
        'member_of': sorted(str(item) for item in member_of or ()),
        'comment': comment,
    }


def form(kind, operation, field):
    """Provider forms; list values (arguments, columns, memberships) are
    descriptor grids (ui_descriptors/yugabytedb)."""
    if operation == 'drop':
        return {'form_id': f'yugabytedb.{kind}.drop',
                'title': f'Drop YSQL {kind}',
                'fields': [field('confirmation', 'Confirmation', 'text',
                                 True)]}
    creating = operation == 'create'
    if kind == 'trigger':
        fields = [field('name', 'Name', 'text', True)]
        if creating:
            fields.append(field('table', 'Table', 'text', True,
                                'schema.table'))
        fields += [
            field('timing', 'Timing', 'select', True, default='BEFORE',
                  options=TIMINGS),
            field('events', 'Events', 'multiselect', True,
                  default=['INSERT'], options=EVENTS),
            field('level', 'Level', 'select', True, default='ROW',
                  options=LEVELS),
            field('function', 'Trigger function', 'text', True,
                  'schema.function; it returns TRIGGER.'),
            field('when', 'WHEN condition', 'code'),
            field('enabled', 'Fires', 'select', False, default='ORIGIN',
                  options=ENABLED),
            field('comment', 'Comment', 'text'),
        ]
    else:
        fields = [field('name', 'Name', 'text', True),
                  field('login', 'Can log in', 'boolean', False,
                        default=(kind == 'user') if creating else None),
                  field('password', 'Password', 'password', False,
                        'Redacted from validation and plans.',
                        sensitive=True)]
        if not creating:
            fields.append(field('clear_password', 'Remove password',
                                'boolean', False, default=False))
        fields += [field('valid_until', 'Valid until', 'text'),
                   field('connection_limit', 'Connection limit', 'number',
                         False, '-1: no limit.'),
                   field('privileges', 'Role options', 'multiselect', False,
                         options=PRIVILEGES),
                   field('comment', 'Comment', 'text')]
    if not creating:
        for item in fields:
            if item['field_id'] not in {'password', 'clear_password'}:
                item['initial_value_path'] = [item['field_id']]
    return {'form_id': f'yugabytedb.{kind}.{operation}',
            'title': f'{operation.title()} YSQL {kind}', 'fields': fields}
