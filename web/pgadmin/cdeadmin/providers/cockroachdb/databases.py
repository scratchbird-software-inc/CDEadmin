"""CockroachDB databases.

Checked live on 26.1.3: CREATE DATABASE [ENCODING 'UTF8'] [OWNER], COMMENT
ON DATABASE, ALTER DATABASE ... OWNER TO / RENAME TO / SET var = value /
RESET var. Refused: CONNECTION LIMIT (other than -1), LC_COLLATE, LC_CTYPE.
TEMPLATE template0 is accepted without a notice (probe); its effect was not
checked, so the editor does not offer it.
Regions, survival goals and placement are their own operations (and need
a multi-region cluster; see "Untested on CockroachDB").
"""
import re

from ...sdk.relational import RelationalClientError

CREATE_KEYS = {'name', 'owner', 'encoding', 'comment', 'settings'}
ALTER_KEYS = {'name', 'owner', 'comment', 'settings', 'confirmation'}
_SETTING = re.compile(r'[a-z_][a-z0-9_.]{0,127}')
# A comma list of plain words (search_path = public, x) is written bare:
# quoted, CockroachDB reads it as one element (live, 26.1.3: SHOW
# search_path gave "public, x").
_WORD_LIST = re.compile(r'[A-Za-z_][A-Za-z0-9_$]*(?:\s*,\s*'
                        r'[A-Za-z_][A-Za-z0-9_$]*)+')


def _settings(value):
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
                f'ALTER DATABASE {name} SET {key} = '
                f'{_value(admin, value)}'), 'parameters': ()})
    for key in held:
        if key not in wanted:
            statements.append({'source': f'ALTER DATABASE {name} RESET '
                                         f'{key}', 'parameters': ()})
    return statements


def _comment(admin, name, value):
    text = 'NULL' if value in (None, '') else admin._literal(str(value))
    return {'source': f'COMMENT ON DATABASE {name} IS {text}',
            'parameters': ()}


def create(admin, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown database option: ' + ', '.join(sorted(unknown)))
    name = admin._quote(admin._identifier(draft.get('name')))
    source = f'CREATE DATABASE {name}'
    encoding = draft.get('encoding')
    if encoding not in (None, ''):
        if str(encoding).upper() not in {'UTF8', 'UTF-8'}:
            raise RelationalClientError('CockroachDB databases are UTF8')
        source += " ENCODING = 'UTF8'"
    if draft.get('owner') not in (None, ''):
        source += f' OWNER = {admin._quote(draft["owner"])}'
    statements = [{'source': source, 'parameters': ()}]
    if draft.get('comment') not in (None, ''):
        statements.append(_comment(admin, name, draft['comment']))
    statements += _setting_statements(
        admin, name, _settings(draft.get('settings')), {})
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
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, name, draft['comment']))
    if 'settings' in draft:
        held = {item['name']: item['value']
                for item in native.get('settings') or []}
        statements += _setting_statements(
            admin, name, _settings(draft['settings']), held)
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
              field('comment', 'Comment', 'text')]
    if operation == 'create':
        fields.append(field('encoding', 'Encoding', 'select', False,
                            default='UTF8', options=('UTF8',)))
    else:
        for item in fields:
            item['initial_value_path'] = [item['field_id']]
    return {'form_id': f'cockroachdb.database.{operation}',
            'title': f'{operation.title()} CockroachDB database',
            'fields': fields,
            'notes': 'Session defaults (ALTER DATABASE SET) are a '
                     'descriptor grid (database.form.json).'}
