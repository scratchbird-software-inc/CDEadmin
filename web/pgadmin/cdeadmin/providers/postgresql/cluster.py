"""PostgreSQL roles and tablespaces on the provider tree (M4, 2026-11-11).

Both run from the server scope, attached to the maintenance database.
Roles: CREATE ROLE with LOGIN, SUPERUSER, CREATEDB, CREATEROLE, INHERIT,
REPLICATION, BYPASSRLS, CONNECTION LIMIT and VALID UNTIL, membership
(GRANT role TO role [WITH ADMIN OPTION]), per-role settings (ALTER ROLE
... [IN DATABASE ...] SET) and a comment; ALTER ROLE for the attributes a
user chooses to change, membership granted and revoked, settings set and
reset, rename and comment; DROP ROLE. The password is never carried in a
plan, so password changes stay with the inherited dialog. Tablespaces:
CREATE TABLESPACE name [OWNER] LOCATION path runs alone outside a
transaction, as PostgreSQL requires, and so does DROP TABLESPACE; ALTER
TABLESPACE RENAME TO / OWNER TO / SET | RESET options, privileges and
comment run in one transaction. PostgreSQL tablespaces are directories,
unlike YugabyteDB's placement tablespaces. Field ids follow the inherited
dialogs (``role.ui.js``, ``tablespace.ui.js``).

The server-scope listing carries only a role's login, superuser flag and
comment, so the alter dialog's attribute fields are three-state (keep,
yes, no) and emit only what the user chooses.
"""
import re

from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
)

ATTRIBUTES = (('rolcanlogin', 'LOGIN'), ('rolsuper', 'SUPERUSER'),
              ('rolcreatedb', 'CREATEDB'), ('rolcreaterole', 'CREATEROLE'),
              ('rolinherit', 'INHERIT'), ('rolreplication', 'REPLICATION'),
              ('rolbypassrls', 'BYPASSRLS'))
_SETTING = re.compile(r'[A-Za-z_][A-Za-z0-9_.]{0,127}')
_VALID_UNTIL = re.compile(r'[0-9A-Za-z :+./-]{1,64}')
_OPTION = re.compile(r'[a-z_]{1,64}')
_OPTION_VALUE = re.compile(r'[0-9]+(?:\.[0-9]+)?')
TABLESPACE_PRIVILEGES = {'C': 'CREATE'}


def _blank(value):
    return value is None or value == ''


def _rows(draft, key, label):
    value = draft.get(key)
    if value in (None, ''):
        return []
    if not isinstance(value, list) or any(
            not isinstance(item, dict) for item in value):
        raise PostgreSQLNativeAdminError(f'{label} must be a list of rows')
    return value


def _comment(keyword, name, value):
    text = 'NULL' if _blank(value) else _literal(str(value), 'comment')
    return f'COMMENT ON {keyword} {name} IS {text}'


# -- roles --------------------------------------------------------------------

def role_facts(native):
    meta = native.get('catalog_metadata') or {}
    return {'rolname': native.get('name') or meta.get('rolname'),
            'rolcanlogin': bool(meta.get('rolcanlogin', False)),
            'rolsuper': bool(meta.get('rolsuper', False)),
            'description': meta.get('description')}


def _limit(value):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < -1:
        raise PostgreSQLNativeAdminError(
            'connection limit is a whole number, -1 for no limit')
    return value


def _valid_until(value):
    if not isinstance(value, str) or not _VALID_UNTIL.fullmatch(value):
        raise PostgreSQLNativeAdminError(
            "valid until is a timestamp or 'infinity'")
    return _literal(value, 'valid until')


def _tri_state(draft, key):
    """'' keeps the attribute; a boolean or yes/no chooses it."""
    value = draft.get(key)
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return value
    text = str(value).lower()
    if text in ('yes', 'true'):
        return True
    if text in ('no', 'false'):
        return False
    raise PostgreSQLNativeAdminError(f'{key} is yes, no or empty')


def _memberships(name, draft, key, direction, label):
    statements = []
    for row in _rows(draft, key, label):
        other = _identifier(row.get('role'), 'role')
        grant, to = (other, name) if direction == 'member_of' else (name,
                                                                   other)
        option = ' WITH ADMIN OPTION' if _flag(row, 'admin') else ''
        statements.append(f'GRANT {grant} TO {to}{option}')
    return statements


def _revocations(name, draft, key, direction, label):
    statements = []
    for row in _rows(draft, key, label):
        other = _identifier(row.get('role'), 'role')
        grant, frm = (other, name) if direction == 'member_of' else (name,
                                                                    other)
        prefix = 'REVOKE ADMIN OPTION FOR ' if _flag(row, 'admin_only') \
            else 'REVOKE '
        statements.append(f'{prefix}{grant} FROM {frm}')
    return statements


def _settings(name, rows):
    statements = []
    for row in rows:
        variable = row.get('name')
        if not isinstance(variable, str) or not _SETTING.fullmatch(variable):
            raise PostgreSQLNativeAdminError('a setting needs a variable name')
        value = row.get('value')
        if not isinstance(value, str) or not value.strip():
            raise PostgreSQLNativeAdminError(f'{variable} needs a value')
        scope = ''
        if not _blank(row.get('database')):
            scope = ' IN DATABASE ' + _identifier(row['database'], 'database')
        statements.append(f'ALTER ROLE {name}{scope} SET {variable} = '
                          + _literal(value, variable))
    return statements


def _create_role(draft):
    name = _identifier(draft.get('rolname'), 'name')
    words = []
    for key, keyword in ATTRIBUTES:
        value = draft.get(key)
        if value is None:
            value = key == 'rolinherit'
        words.append(keyword if _flag({key: value}, key) else 'NO' + keyword)
    if not _blank(draft.get('rolconnlimit')):
        words.append(f'CONNECTION LIMIT {_limit(draft["rolconnlimit"])}')
    if not _blank(draft.get('rolvaliduntil')):
        words.append('VALID UNTIL ' + _valid_until(draft['rolvaliduntil']))
    statements = [f'CREATE ROLE {name} WITH ' + ' '.join(words)]
    statements += _memberships(name, draft, 'rolmembership', 'member_of',
                               'member of')
    statements += _memberships(name, draft, 'rolmembers', 'members',
                               'members')
    statements += _settings(name, _rows(draft, 'variables', 'settings'))
    if not _blank(draft.get('description')):
        statements.append(_comment('ROLE', name, draft['description']))
    return statements


def _alter_role(native, draft):
    current = native.get('role_facts') or role_facts(native)
    name = _name(current['rolname'], 'name')
    quoted = _identifier(name, 'name')
    statements = []
    new_name = draft.get('rolname')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER ROLE {quoted} RENAME TO '
                          + _identifier(new_name, 'name'))
        quoted = _identifier(new_name, 'name')
    words = []
    for key, keyword in ATTRIBUTES:
        chosen = _tri_state(draft, key)
        if chosen is None:
            continue
        if key in current and chosen == current[key]:
            continue
        words.append(keyword if chosen else 'NO' + keyword)
    if not _blank(draft.get('rolconnlimit')):
        words.append(f'CONNECTION LIMIT {_limit(draft["rolconnlimit"])}')
    if not _blank(draft.get('rolvaliduntil')):
        words.append('VALID UNTIL ' + _valid_until(draft['rolvaliduntil']))
    if words:
        statements.append(f'ALTER ROLE {quoted} WITH ' + ' '.join(words))
    statements += _revocations(quoted, draft, 'revoke_membership',
                               'member_of', 'revoked memberships')
    statements += _memberships(quoted, draft, 'rolmembership', 'member_of',
                               'member of')
    statements += _revocations(quoted, draft, 'revoke_members', 'members',
                               'revoked members')
    statements += _memberships(quoted, draft, 'rolmembers', 'members',
                               'members')
    for row in _rows(draft, 'reset_variables', 'reset settings'):
        variable = row.get('name')
        if not isinstance(variable, str) or not _SETTING.fullmatch(variable):
            raise PostgreSQLNativeAdminError('a setting needs a variable name')
        scope = ''
        if not _blank(row.get('database')):
            scope = ' IN DATABASE ' + _identifier(row['database'], 'database')
        statements.append(f'ALTER ROLE {quoted}{scope} RESET {variable}')
    statements += _settings(quoted, _rows(draft, 'variables', 'settings'))
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        statements.append(_comment('ROLE', quoted, draft['description']))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _drop_role(native, draft):
    current = native.get('role_facts') or role_facts(native)
    name = _name(current['rolname'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    return [f'DROP ROLE {_identifier(name, "name")}']


# -- tablespaces --------------------------------------------------------------

def tablespace_facts(native):
    meta = native.get('catalog_metadata') or {}
    return {'name': native.get('name') or meta.get('name'),
            'description': meta.get('description')}


def _options(rows):
    parts = []
    for row in rows:
        option = row.get('name')
        if not isinstance(option, str) or not _OPTION.fullmatch(option):
            raise PostgreSQLNativeAdminError(
                'a tablespace option needs a name')
        value = row.get('value')
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = str(value)
        if not isinstance(value, str) or not _OPTION_VALUE.fullmatch(value):
            raise PostgreSQLNativeAdminError(f'{option} takes a number')
        parts.append(f'{option} = {value}')
    return parts


def _grantee(value):
    value = _name(value, 'grantee')
    return 'PUBLIC' if value.upper() == 'PUBLIC' else _identifier(
        value, 'grantee')


def _create_tablespace(draft):
    name = _identifier(draft.get('name'), 'name')
    location = draft.get('spclocation')
    if not isinstance(location, str) or not location.startswith('/') or \
            '\x00' in location:
        raise PostgreSQLNativeAdminError(
            'location is an absolute directory path on the server host')
    text = f'CREATE TABLESPACE {name}'
    if not _blank(draft.get('spcuser')):
        text += ' OWNER ' + _identifier(draft['spcuser'], 'owner')
    text += ' LOCATION ' + _literal(location, 'location')
    options = _options(_rows(draft, 'spcoptions', 'options'))
    if options:
        text += ' WITH (' + ', '.join(options) + ')'
    # One statement outside a transaction block, by PostgreSQL's rule; the
    # comment follows in an alter.
    if not _blank(draft.get('description')):
        raise PostgreSQLNativeAdminError(
            'CREATE TABLESPACE runs alone outside a transaction; set the '
            'comment with Alter afterwards')
    return {'statement': text, 'read_only': False, 'autocommit': True}


def _alter_tablespace(native, draft):
    current = native.get('tablespace_facts') or tablespace_facts(native)
    name = _name(current['name'], 'name')
    quoted = _identifier(name, 'name')
    statements = []
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER TABLESPACE {quoted} RENAME TO '
                          + _identifier(new_name, 'name'))
        quoted = _identifier(new_name, 'name')
    if not _blank(draft.get('spcuser')):
        statements.append(f'ALTER TABLESPACE {quoted} OWNER TO '
                          + _identifier(draft['spcuser'], 'owner'))
    options = _options(_rows(draft, 'spcoptions', 'options'))
    if options:
        statements.append(f'ALTER TABLESPACE {quoted} SET ('
                          + ', '.join(options) + ')')
    resets = [row.get('name') for row in _rows(draft, 'reset_options',
                                                'reset options')]
    if resets:
        if any(not isinstance(item, str) or not _OPTION.fullmatch(item)
               for item in resets):
            raise PostgreSQLNativeAdminError(
                'a tablespace option needs a name')
        statements.append(f'ALTER TABLESPACE {quoted} RESET ('
                          + ', '.join(resets) + ')')
    for row in _rows(draft, 'revoke', 'revoked grantees'):
        statements.append(f'REVOKE ALL ON TABLESPACE {quoted} FROM '
                          + _grantee(row.get('grantee')))
    for row in _rows(draft, 'spcacl', 'privileges'):
        option = ' WITH GRANT OPTION' if _flag(row, 'with_grant') else ''
        statements.append(f'GRANT CREATE ON TABLESPACE {quoted} TO '
                          f'{_grantee(row.get("grantee"))}{option}')
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        statements.append(_comment('TABLESPACE', quoted,
                                   draft['description']))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return {'statement': ';\n'.join(statements), 'read_only': False}


def _drop_tablespace(native, draft):
    current = native.get('tablespace_facts') or tablespace_facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    return {'statement': f'DROP TABLESPACE {_identifier(name, "name")}',
            'read_only': False, 'autocommit': True}


def compile_operation(kind, operation, native, draft):
    """One exact native text for a role or tablespace lifecycle."""
    if kind == 'role':
        if operation == 'create':
            statements = _create_role(draft)
        elif operation == 'alter':
            statements = _alter_role(native, draft)
        elif operation == 'drop':
            statements = _drop_role(native, draft)
        else:
            raise PostgreSQLNativeAdminError(
                'role inspection stays with the provider tree')
        return {'statement': ';\n'.join(statements), 'read_only': False}
    if operation == 'create':
        return _create_tablespace(draft)
    if operation == 'alter':
        return _alter_tablespace(native, draft)
    if operation == 'drop':
        return _drop_tablespace(native, draft)
    raise PostgreSQLNativeAdminError(
        'tablespace inspection stays with the provider tree')


# -- forms --------------------------------------------------------------------

def _column(field_id, label, control='text', required=False, **extra):
    return {'field_id': field_id, 'label': label, 'control': control,
            'required': required, **extra}


def role_form(operation, field):
    """Dialog fields; ids follow the inherited role dialog. No password."""
    membership = [_column('role', 'Role', required=True),
                  _column('admin', 'With admin option', 'boolean')]
    revocation = [_column('role', 'Role', required=True),
                  _column('admin_only', 'Admin option only', 'boolean')]
    settings = [_column('name', 'Name', required=True),
                _column('value', 'Value', required=True),
                _column('database', 'Database (optional)')]
    tri = [{'value': '', 'label': 'Keep'}, {'value': 'yes', 'label': 'Yes'},
           {'value': 'no', 'label': 'No'}]
    labels = {'rolcanlogin': 'Can login', 'rolsuper': 'Superuser',
              'rolcreatedb': 'Create databases',
              'rolcreaterole': 'Create roles', 'rolinherit': 'Inherit rights',
              'rolreplication': 'Replication', 'rolbypassrls': 'Bypass RLS'}
    if operation == 'drop':
        fields = [field('confirmation', 'Type the role name to confirm',
                        required=True)]
    elif operation == 'create':
        fields = [field('rolname', 'Name', required=True)]
        fields += [field(key, labels[key], 'boolean',
                         **({'default': True} if key == 'rolinherit' else {}))
                   for key, _ in ATTRIBUTES]
        fields += [
            field('rolconnlimit', 'Connection limit', 'number',
                  help='-1 for no limit.'),
            field('rolvaliduntil', 'Account expires',
                  help="A timestamp, or 'infinity'."),
            field('rolmembership', 'Member of', 'grid', columns=membership),
            field('rolmembers', 'Members', 'grid', columns=membership),
            field('variables', 'Parameters', 'grid', columns=settings),
            field('description', 'Comments', 'multiline')]
    else:
        fields = [field('rolname', 'Name',
                        initial_value_path=['role_facts', 'rolname'])]
        fields += [field(key, labels[key], 'select', options=tri)
                   for key, _ in ATTRIBUTES]
        fields += [
            field('rolconnlimit', 'Connection limit', 'number',
                  help='Empty keeps it; -1 for no limit.'),
            field('rolvaliduntil', 'Account expires',
                  help="Empty keeps it; 'infinity' clears it."),
            field('rolmembership', 'Grant membership of', 'grid',
                  columns=membership),
            field('revoke_membership', 'Revoke membership of', 'grid',
                  columns=revocation),
            field('rolmembers', 'Add members', 'grid', columns=membership),
            field('revoke_members', 'Remove members', 'grid',
                  columns=revocation),
            field('variables', 'Set parameters', 'grid', columns=settings),
            field('reset_variables', 'Reset parameters', 'grid', columns=[
                _column('name', 'Name', required=True),
                _column('database', 'Database (optional)')]),
            field('description', 'Comments', 'multiline',
                  initial_value_path=['role_facts', 'description'])]
    return {'form_id': f'postgresql-role-{operation}',
            'form_key': 'native:postgresql:server:role',
            'title': f'{operation.title()} role', 'fields': fields,
            'notes': 'Passwords and security labels stay with the inherited '
                     'dialog; a plan never carries a password.'}


def tablespace_form(operation, field):
    """Dialog fields; ids follow the inherited tablespace dialog."""
    options = [_column('name', 'Option', required=True),
               _column('value', 'Value', required=True)]
    if operation == 'drop':
        fields = [field('confirmation',
                        'Type the tablespace name to confirm',
                        required=True)]
        notes = 'DROP TABLESPACE runs alone outside a transaction.'
    elif operation == 'create':
        fields = [field('name', 'Name', required=True),
                  field('spcuser', 'Owner'),
                  field('spclocation', 'Location', required=True, help=(
                      'An existing, empty directory on the database '
                      'server host, owned by the server user.')),
                  field('spcoptions', 'Options', 'grid', columns=options,
                        help='seq_page_cost, random_page_cost, '
                             'effective_io_concurrency, '
                             'maintenance_io_concurrency')]
        notes = ('CREATE TABLESPACE runs alone outside a transaction; set '
                 'the comment and privileges with Alter afterwards.')
    else:
        fields = [
            field('name', 'Name',
                  initial_value_path=['tablespace_facts', 'name']),
            field('spcuser', 'Owner', help='Empty keeps the owner.'),
            field('spcoptions', 'Set options', 'grid', columns=options),
            field('reset_options', 'Reset options', 'grid', columns=[
                _column('name', 'Option', required=True)]),
            field('spcacl', 'Grant CREATE', 'grid', columns=[
                _column('grantee', 'Grantee', required=True),
                _column('with_grant', 'With grant option', 'boolean')]),
            field('revoke', 'Revoke all privileges from', 'grid', columns=[
                _column('grantee', 'Grantee', required=True)]),
            field('description', 'Comment', 'multiline',
                  initial_value_path=['tablespace_facts', 'description'])]
        notes = 'Security labels stay with the inherited dialog.'
    return {'form_id': f'postgresql-tablespace-{operation}',
            'form_key': 'native:postgresql:server:tablespace',
            'title': f'{operation.title()} tablespace', 'fields': fields,
            'notes': notes}
