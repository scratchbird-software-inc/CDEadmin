"""PostgreSQL database create and alter on the provider tree (M4,
2026-11-11).

CREATE DATABASE runs alone and outside a transaction block (PostgreSQL
refuses it inside one and inside a multi-command string), so create is
exactly one statement in autocommit; the comment and privileges follow in
an alter. ALTER DATABASE RENAME TO / OWNER TO / CONNECTION LIMIT /
ALLOW_CONNECTIONS / IS_TEMPLATE, COMMENT ON DATABASE and GRANT / REVOKE run
in one transaction; SET TABLESPACE also runs alone in autocommit, so it is
refused together with other changes. Drop stays with the inherited dialog.
Field ids follow the inherited database dialog (``database.ui.js``).
"""
import re

from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
)

PRIVILEGE_CODES = {'C': 'CREATE', 'T': 'TEMPORARY', 'c': 'CONNECT'}
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
    }


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
    codes = row.get('privileges')
    if isinstance(codes, str):
        codes = list(codes.replace(',', '').replace(' ', ''))
    if not isinstance(codes, list) or not codes or any(
            code not in PRIVILEGE_CODES for code in codes):
        raise PostgreSQLNativeAdminError(
            'database privileges are codes among '
            + ', '.join(PRIVILEGE_CODES))
    words = [PRIVILEGE_CODES[code] for code in PRIVILEGE_CODES
             if code in codes]
    privileges = 'ALL' if len(words) == len(PRIVILEGE_CODES) else ', '.join(
        words)
    option = ' WITH GRANT OPTION' if _flag(row, 'with_grant') else ''
    return (f'GRANT {privileges} ON DATABASE {name} TO '
            f'{_grantee(row.get("grantee"))}{option}')


def _create(draft):
    name = _identifier(draft.get('name'), 'name')
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
        if needs and provider != needs:
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


def form(operation, field):
    """Dialog fields; ids follow the inherited database dialog."""
    grantee = {'field_id': 'grantee', 'label': 'Grantee', 'control': 'text',
               'required': True}
    if operation == 'drop':
        fields = [
            field('force', 'Force (terminate other sessions first)',
                  'boolean', help='DROP DATABASE ... WITH (FORCE); sessions '
                  'in a prepared transaction or that cannot be terminated '
                  'still block it.'),
            field('confirmation', 'Type the database name to confirm',
                  required=True),
        ]
        notes = ('Runs from the server scope outside a transaction. The '
                 'server refuses the connected database and templates.')
    elif operation == 'create':
        providers = [{'value': item, 'label': item}
                     for item in LOCALE_PROVIDERS]
        fields = [
            field('name', 'Database', required=True),
            field('datowner', 'Owner'),
            field('template', 'Template', help='TEMPLATE; template0 for '
                  'locales that differ from the template database.'),
            field('encoding', 'Encoding', help='UTF8, LATIN1, ...'),
            field('datlocaleprovider', 'Locale provider', 'select',
                  options=providers),
            field('datcollate', 'Collation (LC_COLLATE)'),
            field('datctype', 'Character type (LC_CTYPE)'),
            field('daticulocale', 'ICU locale'),
            field('daticurules', 'ICU rules'),
            field('datbuiltinlocale', 'Builtin locale'),
            field('spcname', 'Tablespace'),
            field('datconnlimit', 'Connection limit', 'number',
                  help='-1 for no limit.'),
            field('datallowconn', 'Allow connections', 'boolean',
                  default=True),
            field('is_template', 'Template database', 'boolean'),
        ]
        notes = ('CREATE DATABASE runs alone outside a transaction; set the '
                 'comment and privileges with Alter afterwards.')
    else:
        def initial(key):
            return {'initial_value_path': ['database_facts', key]}
        fields = [
            field('name', 'Database', **initial('name')),
            field('datowner', 'Owner', help='Empty keeps the owner.'),
            field('spcname', 'Tablespace', help=(
                'A different tablespace runs SET TABLESPACE alone, outside '
                'a transaction.'), **initial('spcname')),
            field('datconnlimit', 'Connection limit', 'number',
                  **initial('datconnlimit')),
            field('datallowconn', 'Allow connections', 'boolean',
                  **initial('datallowconn')),
            field('is_template', 'Template database', 'boolean',
                  **initial('is_template')),
            field('comments', 'Comment', 'multiline', **initial('comments')),
            field('datacl', 'Grant privileges', 'grid', columns=[
                grantee, {'field_id': 'privileges',
                          'label': 'Privileges (C create, T temporary, '
                                   'c connect)',
                          'control': 'text', 'required': True},
                {'field_id': 'with_grant', 'label': 'With grant option',
                 'control': 'boolean', 'required': False}]),
            field('revoke', 'Revoke all privileges from', 'grid',
                  columns=[grantee]),
        ]
        notes = ('Renaming the database you are connected to is refused by '
                 'the server; alter it from another database.')
    return {'form_id': f'postgresql-database-{operation}',
            'form_key': 'native:postgresql:server:database',
            'title': f'{operation.title()} database', 'fields': fields,
            'notes': notes}
