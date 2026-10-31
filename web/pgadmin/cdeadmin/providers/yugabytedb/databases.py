"""YugabyteDB YSQL databases.

Checked live on 2025.2.2.2: CREATE DATABASE with OWNER, TEMPLATE, ENCODING,
LOCALE / LC_COLLATE / LC_CTYPE, LOCALE_PROVIDER icu with ICU_LOCALE,
CONNECTION LIMIT, ALLOW_CONNECTIONS, IS_TEMPLATE and COLOCATION; ALTER
DATABASE OWNER TO / CONNECTION LIMIT / ALLOW_CONNECTIONS / SET / RESET /
RENAME TO and COMMENT ON DATABASE (these run inside a transaction; CREATE
and DROP do not). Refused ("not yet supported"): ALTER DATABASE IS_TEMPLATE,
SET TABLESPACE, and a TABLESPACE other than the default at create.

Colocation is read with yb_is_database_colocated(), which answers only for
the database it runs in, so it is create-only here and the catalog reports
it for the connected database alone.

Field ids match the CockroachDB database form (name, owner, comment,
encoding, settings).
"""
import re

from ...sdk.relational import RelationalClientError

CREATE_KEYS = {'name', 'owner', 'template', 'encoding', 'locale_provider',
               'collate', 'ctype', 'icu_locale', 'connection_limit',
               'allow_connections', 'is_template', 'colocation', 'comment',
               'settings'}
ALTER_KEYS = {'name', 'owner', 'connection_limit', 'allow_connections',
              'comment', 'settings', 'confirmation'}
_SETTING = re.compile(r'[a-z_][a-z0-9_.]{0,127}')
# A comma list of plain words (search_path = public, x) is written bare:
# quoted, PostgreSQL reads it as one element.
_WORD_LIST = re.compile(r'[A-Za-z_][A-Za-z0-9_$]*(?:\s*,\s*'
                        r'[A-Za-z_][A-Za-z0-9_$]*)+')
_LOCALE = re.compile(r'[A-Za-z0-9_.@-]{1,64}')


def _blank(value):
    return value is None or value == ''


def settings(value):
    if value is None:
        return {}
    if not isinstance(value, list):
        raise RelationalClientError('settings must be a list')
    out = {}
    for item in value:
        if not isinstance(item, dict) or not _SETTING.fullmatch(
                str(item.get('name') or '')):
            raise RelationalClientError('a setting needs a variable name')
        if item['name'] in out:
            raise RelationalClientError(f'{item["name"]} is set twice')
        if not isinstance(item.get('value'), str) or '\x00' in item['value']:
            raise RelationalClientError(f'{item["name"]} needs a value')
        out[item['name']] = item['value']
    return out


def _value(admin, value):
    if _WORD_LIST.fullmatch(value.strip()):
        return value.strip()
    return admin._literal(value)


def _setting_statements(admin, name, wanted, held):
    statements = []
    for key, value in wanted.items():
        if held.get(key) != value:
            statements.append({'source': (
                f'ALTER DATABASE {name} SET {key} = {_value(admin, value)}'),
                'parameters': ()})
    for key in held:
        if key not in wanted:
            statements.append({'source': f'ALTER DATABASE {name} RESET '
                                         f'{key}', 'parameters': ()})
    return statements


def _comment(admin, name, value):
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON DATABASE {name} IS {text}',
            'parameters': ()}


def _limit(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < -1:
        raise RelationalClientError(
            'connection limit is a whole number, -1 for no limit')
    return value


def _locale(value, label):
    if not isinstance(value, str) or not _LOCALE.fullmatch(value):
        raise RelationalClientError(f'{label} is a locale name')
    return value


def create(admin, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown database option: ' + ', '.join(sorted(unknown)))
    name = admin._quote(admin._identifier(draft.get('name')))
    clauses = []
    if not _blank(draft.get('owner')):
        clauses.append(f'OWNER {admin._quote(draft["owner"])}')
    if not _blank(draft.get('template')):
        clauses.append(f'TEMPLATE {admin._quote(draft["template"])}')
    if not _blank(draft.get('encoding')):
        clauses.append('ENCODING ' + admin._literal(
            _locale(draft['encoding'], 'encoding')))
    provider = str(draft.get('locale_provider') or '').lower()
    if provider not in {'', 'libc', 'icu'}:
        raise RelationalClientError('locale provider is libc or icu')
    if provider:
        clauses.append(f'LOCALE_PROVIDER {provider}')
    if not _blank(draft.get('icu_locale')):
        if provider != 'icu':
            raise RelationalClientError(
                'an ICU locale needs the icu locale provider')
        clauses.append('ICU_LOCALE ' + admin._literal(
            _locale(draft['icu_locale'], 'ICU locale')))
    elif provider == 'icu':
        raise RelationalClientError('the icu locale provider needs an '
                                    'ICU locale')
    for key, keyword in (('collate', 'LC_COLLATE'), ('ctype', 'LC_CTYPE')):
        if not _blank(draft.get(key)):
            clauses.append(f'{keyword} ' + admin._literal(
                _locale(draft[key], keyword)))
    if not _blank(draft.get('connection_limit')):
        clauses.append(
            f'CONNECTION LIMIT {_limit(draft["connection_limit"])}')
    for key, keyword in (('allow_connections', 'ALLOW_CONNECTIONS'),
                         ('is_template', 'IS_TEMPLATE'),
                         ('colocation', 'COLOCATION')):
        if draft.get(key) is not None:
            clauses.append(
                f'{keyword} = {"true" if draft[key] else "false"}')
    statements = [{'source': ' '.join([f'CREATE DATABASE {name}', *clauses]),
                   'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, name, draft['comment']))
    statements += _setting_statements(
        admin, name, settings(draft.get('settings')), {})
    return statements


def alter(admin, draft, target):
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            ', '.join(sorted(unknown)) + ' cannot change in place')
    native = (target or {}).get('native') or {}
    current = (target or {}).get('display_name')
    name = admin._quote(current)
    statements = []
    if draft.get('owner') not in (None, '', native.get('owner')):
        statements.append({'source': (
            f'ALTER DATABASE {name} OWNER TO '
            f'{admin._quote(draft["owner"])}'), 'parameters': ()})
    if not _blank(draft.get('connection_limit')) and \
            draft['connection_limit'] != native.get('connection_limit'):
        statements.append({'source': (
            f'ALTER DATABASE {name} CONNECTION LIMIT '
            f'{_limit(draft["connection_limit"])}'), 'parameters': ()})
    if draft.get('allow_connections') is not None and bool(
            draft['allow_connections']) != bool(
                native.get('allow_connections', True)):
        statements.append({'source': (
            f'ALTER DATABASE {name} ALLOW_CONNECTIONS '
            f'{"true" if draft["allow_connections"] else "false"}'),
            'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, name, draft['comment']))
    if 'settings' in draft:
        held = {item['name']: item['value']
                for item in native.get('settings') or []}
        statements += _setting_statements(
            admin, name, settings(draft['settings']), held)
    if draft.get('name') not in (None, '', current):
        statements.append({'source': (
            f'ALTER DATABASE {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def form(field, operation):
    fields = [field('name', 'Name', 'text', True),
              field('owner', 'Owner', 'text'),
              field('comment', 'Comment', 'text'),
              field('connection_limit', 'Connection limit', 'number'),
              field('allow_connections', 'Allow connections', 'boolean',
                    False, default=True)]
    if operation == 'create':
        fields += [field('template', 'Template', 'text'),
                   field('encoding', 'Encoding', 'text'),
                   field('locale_provider', 'Locale provider', 'select',
                         False, options=('libc', 'icu')),
                   field('icu_locale', 'ICU locale', 'text'),
                   field('collate', 'Collation (LC_COLLATE)', 'text'),
                   field('ctype', 'Character type (LC_CTYPE)', 'text'),
                   field('is_template', 'Template database', 'boolean',
                         False, default=False),
                   field('colocation', 'Colocation', 'boolean', False,
                         default=False)]
    else:
        for item in fields:
            item['initial_value_path'] = [item['field_id']]
    return {'form_id': f'yugabytedb.database.{operation}',
            'title': f'{operation.title()} YSQL database', 'fields': fields,
            'notes': 'Session defaults (ALTER DATABASE SET) are a '
                     'descriptor grid (database.form.json).'}
