"""PostgreSQL database create and alter on the provider tree (M4,
2026-11-11).

CREATE DATABASE runs alone and outside a transaction block (PostgreSQL
refuses it inside one and inside a multi-command string), so create is
exactly one statement in autocommit; the comment, privileges, labels,
settings and default privileges follow in an alter (the create dialog
refuses them with that message). ALTER DATABASE RENAME TO / OWNER TO /
CONNECTION LIMIT / ALLOW_CONNECTIONS / IS_TEMPLATE / SET / RESET, COMMENT
ON DATABASE, SECURITY LABEL, GRANT / REVOKE and ALTER DEFAULT PRIVILEGES
run in one transaction; SET TABLESPACE also runs alone in autocommit, so
it is refused together with other changes. Default privileges act inside
the database, so a plan that carries them attaches to that database
(owner direction 2026-11-11: the family form's fields are all compiled).
Field ids follow the inherited database dialog (``database.ui.js``).
"""
import re

from .native_admin import (
    PostgreSQLNativeAdminError, privilege_words,
    _flag, _identifier, _literal, _name,
)

PRIVILEGE_CODES = {'C': 'CREATE', 'T': 'TEMPORARY', 'c': 'CONNECT'}
DEFAULT_PRIVILEGES = {
    'deftblacl': ('TABLES', {
        'a': 'INSERT', 'r': 'SELECT', 'w': 'UPDATE', 'd': 'DELETE',
        'D': 'TRUNCATE', 'x': 'REFERENCES', 't': 'TRIGGER',
        'm': 'MAINTAIN'}),
    'defseqacl': ('SEQUENCES', {'r': 'SELECT', 'w': 'UPDATE',
                                'U': 'USAGE'}),
    'deffuncacl': ('FUNCTIONS', {'X': 'EXECUTE'}),
    'deftypeacl': ('TYPES', {'U': 'USAGE'}),
}
STRATEGIES = ('wal_log', 'file_copy')
_SETTING = re.compile(r'[A-Za-z_][A-Za-z0-9_.]{0,127}')
FOLLOW_UP = ('comments', 'datacl', 'seclabels', 'variables',
             'deftblacl', 'defseqacl', 'deffuncacl', 'deftypeacl')
LOCALE_PROVIDERS = ('libc', 'icu', 'builtin')
_LOCALE = re.compile(r'[A-Za-z0-9_.@-]{1,64}')
_ENCODING = re.compile(r'[A-Za-z0-9_-]{1,32}')


def _blank(value):
    return value is None or value == ''


def facts(native):
    """Current values from either listing: the server-scope row (inherited
    nodes template) or the captured pg_database row."""
    meta = native.get('catalog_metadata') or {}
    row = native.get('catalog_row') or {}
    limit = row.get('datconnlimit')
    return {
        'name': native.get('name') or meta.get('name') or row.get('datname'),
        'spcname': meta.get('spcname'),
        'datconnlimit': limit if isinstance(limit, int) else None,
        'is_template': bool(meta.get('is_template',
                                     row.get('datistemplate', False))),
        'datallowconn': bool(meta.get('datallowconn',
                                      row.get('datallowconn', True))),
        'comments': meta.get('description', native.get('comment')),
        'datacl': list(row.get('datacl') or []),
        # Per-database settings (ALTER DATABASE ... SET) when the listing
        # carries them: rows of name, value and an optional role.
        'variables': [dict(item) for item in native.get('settings') or []
                      if isinstance(item, dict)],
    }


def _setting_name(value):
    if not isinstance(value, str) or not _SETTING.fullmatch(value):
        raise PostgreSQLNativeAdminError('a setting is a parameter name')
    return value


def _settings(name, draft, current):
    """ALTER DATABASE ... SET / RESET from the Parameters grid. A row with
    a value sets it (for a role: ALTER ROLE r IN DATABASE d SET); a row
    with an empty value resets it; a current setting left out of the grid
    is reset when the listing knows the current settings."""
    statements = []
    seen = set()
    for row in _rows(draft, 'variables', 'settings'):
        setting = _setting_name(row.get('name'))
        role = row.get('role')
        subject = (f'ALTER ROLE {_identifier(role, "role")} IN DATABASE '
                   f'{name}' if not _blank(role) else f'ALTER DATABASE {name}')
        seen.add((setting, role or None))
        if _blank(row.get('value')):
            statements.append(f'{subject} RESET {setting}')
        else:
            statements.append(f'{subject} SET {setting} TO '
                              + _literal(str(row['value']), 'value'))
    for row in current:
        key = (row.get('name'), row.get('role') or None)
        if key in seen or not isinstance(row.get('name'), str):
            continue
        setting = _setting_name(row['name'])
        subject = (f'ALTER ROLE {_identifier(row["role"], "role")} IN '
                   f'DATABASE {name}' if row.get('role')
                   else f'ALTER DATABASE {name}')
        statements.append(f'{subject} RESET {setting}')
    return statements


def _label(name, row):
    provider = _name(row.get('provider'), 'provider')
    label = row.get('label')
    if not isinstance(label, str) or not label:
        raise PostgreSQLNativeAdminError('a security label needs text')
    return (f'SECURITY LABEL FOR {_identifier(provider, "provider")} ON '
            f'DATABASE {name} IS {_literal(label, "label")}')


def _default_privileges(draft):
    """ALTER DEFAULT PRIVILEGES ... GRANT ... ON TABLES | SEQUENCES |
    FUNCTIONS | TYPES TO grantee, for the four Default Privileges grids;
    they act for the applying role inside the database."""
    statements = []
    for key, (objects, codes) in DEFAULT_PRIVILEGES.items():
        for row in _rows(draft, key, 'default privileges'):
            words = privilege_words(row.get('privileges'), codes,
                                    objects.lower())
            privileges = 'ALL' if len(words) == len(codes) else ', '.join(
                words)
            option = ' WITH GRANT OPTION' if _flag(row, 'with_grant') else ''
            statements.append(f'ALTER DEFAULT PRIVILEGES GRANT {privileges} '
                              f'ON {objects} TO {_grantee(row.get("grantee"))}'
                              f'{option}')
    return statements


def has_default_privileges(draft):
    """True when a draft carries default-privilege rows: the plan then
    attaches to the database itself (the provider route reads this)."""
    return any(draft.get(key) not in (None, '', [])
               for key in DEFAULT_PRIVILEGES)


def _limit(value):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < -1:
        raise PostgreSQLNativeAdminError(
            'connection limit is a whole number, -1 for no limit')
    return value


def _locale(value, label):
    if not isinstance(value, str) or not _LOCALE.fullmatch(value):
        raise PostgreSQLNativeAdminError(f'{label} is a locale name')
    return _literal(value, label)


def _grantee(value):
    value = _name(value, 'grantee')
    return 'PUBLIC' if value.upper() == 'PUBLIC' else _identifier(
        value, 'grantee')


def _rows(draft, key, label):
    value = draft.get(key)
    if value in (None, ''):
        return []
    if not isinstance(value, list) or any(
            not isinstance(item, dict) for item in value):
        raise PostgreSQLNativeAdminError(f'{label} must be a list of rows')
    return value


def _grant(name, row):
    words_chosen = privilege_words(row.get('privileges'), PRIVILEGE_CODES,
                                   'database')
    words = words_chosen
    privileges = 'ALL' if len(words) == len(PRIVILEGE_CODES) else ', '.join(
        words)
    option = ' WITH GRANT OPTION' if _flag(row, 'with_grant') else ''
    return (f'GRANT {privileges} ON DATABASE {name} TO '
            f'{_grantee(row.get("grantee"))}{option}')


def _create(draft):
    name = _identifier(draft.get('name'), 'name')
    for key in FOLLOW_UP:
        if draft.get(key) not in (None, '', []):
            raise PostgreSQLNativeAdminError(
                'CREATE DATABASE runs alone, outside a transaction: set the '
                'comment, privileges, security labels, parameters and '
                'default privileges with Edit after creating it')
    if draft.get('schema_res') not in (None, '', []):
        raise PostgreSQLNativeAdminError(
            'the schema restriction is a browsing preference of the '
            'inherited tree; the provider tree does not store it')
    clauses = []
    if not _blank(draft.get('datowner')):
        clauses.append('OWNER = ' + _identifier(draft['datowner'], 'owner'))
    if not _blank(draft.get('template')):
        clauses.append('TEMPLATE = ' + _identifier(draft['template'],
                                                   'template'))
    if not _blank(draft.get('encoding')):
        encoding = draft['encoding']
        if not isinstance(encoding, str) or not _ENCODING.fullmatch(encoding):
            raise PostgreSQLNativeAdminError('encoding is an encoding name')
        clauses.append('ENCODING = ' + _literal(encoding, 'encoding'))
    provider = str(draft.get('datlocaleprovider') or '').lower()
    if provider and provider not in LOCALE_PROVIDERS:
        raise PostgreSQLNativeAdminError(
            'locale provider is ' + ', '.join(LOCALE_PROVIDERS))
    if provider:
        clauses.append(f'LOCALE_PROVIDER = {provider}')
    for key, keyword, needs in (('datcollate', 'LC_COLLATE', None),
                                ('datctype', 'LC_CTYPE', None),
                                ('daticulocale', 'ICU_LOCALE', 'icu'),
                                ('daticurules', 'ICU_RULES', 'icu'),
                                ('datbuiltinlocale', 'BUILTIN_LOCALE',
                                 'builtin')):
        if _blank(draft.get(key)):
            continue
        if needs and provider and provider != needs:
            # The dialog hides a provider's fields when another provider is
            # chosen but keeps their values; a hidden value is ignored.
            continue
        if needs and not provider:
            raise PostgreSQLNativeAdminError(
                f'{keyword} needs the {needs} locale provider')
        clauses.append(f'{keyword} = ' + _locale(draft[key], keyword))
    if provider == 'icu' and _blank(draft.get('daticulocale')):
        raise PostgreSQLNativeAdminError(
            'the icu locale provider needs an ICU locale')
    if provider == 'builtin' and _blank(draft.get('datbuiltinlocale')):
        raise PostgreSQLNativeAdminError(
            'the builtin locale provider needs a builtin locale')
    if not _blank(draft.get('spcname')):
        clauses.append('TABLESPACE = ' + _identifier(draft['spcname'],
                                                     'tablespace'))
    if not _blank(draft.get('datconnlimit')):
        clauses.append(f'CONNECTION LIMIT = {_limit(draft["datconnlimit"])}')
    for key, keyword in (('datallowconn', 'ALLOW_CONNECTIONS'),
                         ('is_template', 'IS_TEMPLATE')):
        if draft.get(key) is not None:
            value = 'true' if _flag(draft, key) else 'false'
            clauses.append(f'{keyword} = {value}')
    strategy = draft.get('datstrategy')
    if not _blank(strategy):
        if strategy not in STRATEGIES:
            raise PostgreSQLNativeAdminError(
                'strategy is ' + ' or '.join(STRATEGIES))
        clauses.append(f'STRATEGY = {strategy}')
    statement = f'CREATE DATABASE {name}'
    if clauses:
        statement += ' WITH ' + ' '.join(clauses)
    # One statement, outside a transaction block, by PostgreSQL's rule.
    return {'statement': statement, 'read_only': False, 'autocommit': True}


def _alter(native, draft):
    # The listing's facts first (they carry the tablespace name); a bare
    # native falls back to what its rows say.
    current = native.get('database_facts') or facts(native)
    name = _identifier(current['name'], 'name')
    if draft.get('schema_res') not in (None, '', []):
        raise PostgreSQLNativeAdminError(
            'the schema restriction is a browsing preference of the '
            'inherited tree; the provider tree does not store it')
    statements = []
    tablespace = draft.get('spcname')
    moving = not _blank(tablespace) and tablespace != current['spcname']
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != current['name']:
        statements.append(f'ALTER DATABASE {name} RENAME TO '
                          + _identifier(new_name, 'name'))
        name = _identifier(new_name, 'name')
    if not _blank(draft.get('datowner')):
        statements.append(f'ALTER DATABASE {name} OWNER TO '
                          + _identifier(draft['datowner'], 'owner'))
    if not _blank(draft.get('datconnlimit')) and \
            draft['datconnlimit'] != current['datconnlimit']:
        statements.append(f'ALTER DATABASE {name} CONNECTION LIMIT '
                          f'{_limit(draft["datconnlimit"])}')
    for key, keyword in (('datallowconn', 'ALLOW_CONNECTIONS'),
                         ('is_template', 'IS_TEMPLATE')):
        if draft.get(key) is not None and _flag(draft, key) != current[key]:
            statements.append(f'ALTER DATABASE {name} WITH {keyword} '
                              f'{"true" if draft[key] else "false"}')
    if 'comments' in draft and (draft['comments'] or None) != (
            current['comments'] or None):
        text = 'NULL' if _blank(draft['comments']) else _literal(
            str(draft['comments']), 'comment')
        statements.append(f'COMMENT ON DATABASE {name} IS {text}')
    for row in _rows(draft, 'revoke', 'revoked grantees'):
        statements.append(f'REVOKE ALL ON DATABASE {name} FROM '
                          + _grantee(row.get('grantee')))
    for row in _rows(draft, 'datacl', 'privileges'):
        statements.append(_grant(name, row))
    for row in _rows(draft, 'seclabels', 'security labels'):
        statements.append(_label(name, row))
    if 'variables' in draft:
        statements.extend(_settings(name, draft, current.get('variables')
                                    or []))
    if has_default_privileges(draft):
        if not _blank(new_name) and new_name != current['name']:
            raise PostgreSQLNativeAdminError(
                'default privileges run inside the database, which cannot '
                'be renamed meanwhile; rename it separately')
        statements.extend(_default_privileges(draft))
    if moving:
        if statements:
            raise PostgreSQLNativeAdminError(
                'a tablespace change runs alone, outside a transaction; '
                'apply the other changes first')
        return {'statement': (f'ALTER DATABASE {name} SET TABLESPACE '
                              + _identifier(tablespace, 'tablespace')),
                'read_only': False, 'autocommit': True}
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return {'statement': ';\n'.join(statements), 'read_only': False}


def _drop(native, draft):
    """DROP DATABASE, optionally WITH (FORCE), from the server scope (M6).

    FORCE terminates the other sessions of that database first, including
    any this application holds to it; the server refuses to drop the
    connected database and a template database regardless.
    """
    name = _name(facts(native)['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    force = ' WITH (FORCE)' if _flag(draft, 'force') else ''
    return {'statement': f'DROP DATABASE {_identifier(name, "name")}{force}',
            'read_only': False, 'autocommit': True}


def compile_operation(operation, native, draft):
    """One exact native text for database create, alter or drop."""
    if operation == 'create':
        return _create(draft)
    if operation == 'alter':
        return _alter(native, draft)
    if operation == 'drop':
        return _drop(native, draft)
    raise PostgreSQLNativeAdminError(
        'database inspection stays with the provider tree')


# The family form's field ids (database.form.json), by operation; the
# validator admits exactly these, so the dialog's draft is never refused as
# unknown. Read-only properties are admitted and ignored.
_FAMILY_FIELDS = {
    'create': ('name', 'datoid', 'datowner', 'comments', 'template',
               'encoding', 'spcname', 'datcollate', 'datctype',
               'datconnlimit', 'is_template', 'datallowconn', 'datstrategy',
               'datlocaleprovider', 'daticulocale', 'daticurules',
               'datbuiltinlocale', 'schema_res', 'datacl', 'seclabels',
               'variables'),
    'alter': ('name', 'did', 'datowner', 'is_sys_obj', 'comments',
              'encoding', 'spcname', 'datcollate', 'datctype',
              'datconnlimit', 'is_template', 'datallowconn',
              'datlocaleprovider', 'daticulocale', 'daticurules',
              'datbuiltinlocale', 'datcollversion', 'schema_res', 'acl',
              'tblacl', 'seqacl', 'funcacl', 'typeacl', 'datacl',
              'seclabels', 'deftblacl', 'defseqacl', 'deffuncacl',
              'deftypeacl', 'variables', 'revoke'),
}
_GRIDS = ('datacl', 'seclabels', 'variables', 'deftblacl', 'defseqacl',
          'deffuncacl', 'deftypeacl', 'revoke')
_BOOLEANS = ('is_template', 'datallowconn', 'is_sys_obj')
_LOCALE_FIELDS = {'datcollate': 'libc', 'datctype': 'libc',
                  'daticulocale': 'icu', 'daticurules': 'icu',
                  'datbuiltinlocale': 'builtin'}


def _when(controller, value):
    # The client reads ``field``; the server validator reads ``field_id``.
    return {'field': controller, 'field_id': controller, 'equals': value}


def form(operation, field):
    """The validator's view of the database family form: every field id
    the dialog sends, typed loosely; the family form file carries the
    labels, tabs and grid columns."""
    if operation == 'drop':
        return {'form_id': 'postgresql-database-drop',
                'form_key': 'native:postgresql:server:database',
                'title': 'Drop database', 'fields': [
                    field('force', 'Force (terminate other sessions first)',
                          'boolean', help='DROP DATABASE ... WITH (FORCE); '
                          'sessions in a prepared transaction or that cannot '
                          'be terminated still block it.'),
                    field('confirmation', 'Type the database name to confirm',
                          required=True)],
                'notes': ('Runs from the server scope outside a transaction. '
                          'The server refuses the connected database and '
                          'templates.')}
    alter = operation == 'alter'

    def initial(key):
        return {'initial_value_path': ['database_facts', key]} if alter \
            else {}
    fields = []
    for field_id in _FAMILY_FIELDS[operation]:
        label = field_id.replace('_', ' ').capitalize()
        extra = {}
        if field_id in _LOCALE_FIELDS:
            extra['visible_when'] = _when('datlocaleprovider',
                                          _LOCALE_FIELDS[field_id])
        if field_id in _GRIDS:
            fields.append(field(field_id, label, 'grid', columns=[], **extra))
        elif field_id in _BOOLEANS:
            fields.append(field(field_id, label, 'boolean',
                                **initial(field_id)))
        elif field_id in ('datconnlimit', 'datoid', 'did'):
            fields.append(field(field_id, label, 'number',
                                **initial(field_id)))
        elif field_id == 'datlocaleprovider':
            fields.append(field(field_id, 'Locale provider', 'select',
                                options=[{'value': item, 'label': item}
                                         for item in LOCALE_PROVIDERS]))
        elif field_id == 'datstrategy':
            fields.append(field(field_id, 'Strategy', 'select', options=[
                {'value': item, 'label': item} for item in STRATEGIES]))
        else:
            fields.append(field(field_id, label,
                                required=field_id == 'name' and not alter,
                                **(initial(field_id) if field_id in
                                   ('name', 'spcname', 'comments') else {}),
                                **extra))
    notes = ('Renaming the database you are connected to is refused by the '
             'server; alter it from another database. A different '
             'tablespace runs SET TABLESPACE alone, outside a transaction. '
             'Default privileges run inside the database.') if alter else (
        'CREATE DATABASE runs alone outside a transaction; set the comment, '
        'privileges, labels, parameters and default privileges with Edit '
        'afterwards.')
    return {'form_id': f'postgresql-database-{operation}',
            'form_key': 'native:postgresql:server:database',
            'title': f'{operation.title()} database', 'fields': fields,
            'notes': notes}
