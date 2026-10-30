"""YugabyteDB YSQL user-defined types and domains.

Checked live on 2025.2.2.2: CREATE TYPE AS ENUM / AS (fields) / AS RANGE
(subtype, subtype_diff); ALTER TYPE ADD VALUE [BEFORE|AFTER], RENAME VALUE,
RENAME TO; COMMENT ON TYPE. CREATE DOMAIN with a base type, COLLATE,
DEFAULT, NOT NULL and CHECK constraints; ALTER DOMAIN SET / DROP DEFAULT,
RENAME TO; COMMENT ON DOMAIN. Refused ("not supported yet"): composite
ADD / DROP / ALTER / RENAME ATTRIBUTE, ALTER DOMAIN SET / DROP NOT NULL,
ADD / DROP / VALIDATE / RENAME CONSTRAINT. Enum values cannot be dropped
(as in PostgreSQL) or reordered.

Field ids: enum_values and fields as YugabyteDB's and DuckDB's type forms
have them; rename_values as CockroachDB's.
"""
from ...sdk.relational import RelationalClientError

TYPE_KINDS = ('ENUM', 'COMPOSITE', 'RANGE')
TYPE_CREATE = {'name', 'parent', 'type_kind', 'enum_values', 'fields',
               'subtype', 'subtype_diff', 'comment'}
TYPE_ALTER = {'name', 'enum_values', 'rename_values', 'comment',
              'confirmation'}
DOMAIN_CREATE = {'name', 'parent', 'base_type', 'collation', 'default',
                 'not_null', 'checks', 'comment'}
DOMAIN_ALTER = {'name', 'default', 'comment', 'confirmation'}


def _blank(value):
    return value is None or value == ''


def _strings(value, label):
    if value is None:
        return []
    if not isinstance(value, list) or any(
            not isinstance(item, str) or not item or '\x00' in item
            for item in value):
        raise RelationalClientError(f'{label} must be non-empty text')
    if len(set(value)) != len(value):
        raise RelationalClientError(f'{label} must not repeat')
    return list(value)


def _comment(admin, keyword, name, value):
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON {keyword} {name} IS {text}',
            'parameters': ()}


def _unknown(draft, allowed, what):
    unknown = set(draft) - allowed
    if unknown:
        raise RelationalClientError(
            ', '.join(sorted(unknown)) + f' is not a {what} option here')


def create_type(admin, draft):
    _unknown(draft, TYPE_CREATE, 'type')
    name = admin._new_object_name(admin._identifier(draft.get('name')),
                                  draft)
    kind = str(draft.get('type_kind') or '').upper()
    if kind == 'ENUM':
        definition = 'ENUM (' + ', '.join(
            admin._literal(item) for item in _strings(
                draft.get('enum_values'), 'enum values')) + ')'
    elif kind == 'COMPOSITE':
        fields = draft.get('fields')
        if not isinstance(fields, list) or not fields:
            raise RelationalClientError('a composite type needs fields')
        definition = '(' + ', '.join(
            f'{admin._quote(item.get("name"))} '
            f'{admin._safe_fragment(item.get("type"), "field type")}'
            for item in fields) + ')'
    elif kind == 'RANGE':
        options = ['subtype = ' + admin._safe_fragment(
            draft.get('subtype'), 'subtype')]
        if not _blank(draft.get('subtype_diff')):
            options.append('subtype_diff = ' + admin._safe_fragment(
                draft['subtype_diff'], 'subtype difference function'))
        definition = 'RANGE (' + ', '.join(options) + ')'
    else:
        raise RelationalClientError('type kind is ENUM, COMPOSITE or RANGE')
    statements = [{'source': f'CREATE TYPE {name} AS {definition}',
                   'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, 'TYPE', name, draft['comment']))
    return statements


def alter_type(admin, draft, target):
    if set(draft) & {'fields', 'subtype', 'subtype_diff', 'type_kind'}:
        raise RelationalClientError(
            "a composite or range type's definition is fixed once created "
            '(YugabyteDB does not alter attributes)')
    _unknown(draft, TYPE_ALTER, 'type change')
    native = (target or {}).get('native') or {}
    path = admin._target_path(target)
    name = admin._qualified(path)
    statements = []
    current = list(native.get('enum_values') or [])
    if (draft.get('rename_values') or 'enum_values' in draft) and \
            native.get('type_kind') != 'ENUM':
        raise RelationalClientError('only an enum has values')
    for item in draft.get('rename_values') or []:
        if not isinstance(item, dict) or item.get('from') not in current:
            raise RelationalClientError(
                'rename a value the enum holds (from)')
        new = _strings([item.get('to')], 'new value')[0]
        if new in current:
            raise RelationalClientError(f'the enum already has {new!r}')
        statements.append({'source': (
            f'ALTER TYPE {name} RENAME VALUE {admin._literal(item["from"])} '
            f'TO {admin._literal(new)}'), 'parameters': ()})
        current[current.index(item['from'])] = new
    if 'enum_values' in draft:
        wanted = _strings(draft['enum_values'], 'enum values')
        if [item for item in current if item not in wanted]:
            raise RelationalClientError(
                'an enum value cannot be dropped (PostgreSQL has no DROP '
                'VALUE); rename it instead')
        if [item for item in wanted if item in current] != current:
            raise RelationalClientError('enum values cannot be reordered')
        for index, item in enumerate(wanted):
            if item in current:
                continue
            anchor = (f' AFTER {admin._literal(wanted[index - 1])}' if index
                      else f' BEFORE {admin._literal(current[0])}'
                      if current else '')
            statements.append({'source': (
                f'ALTER TYPE {name} ADD VALUE {admin._literal(item)}'
                f'{anchor}'), 'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, 'TYPE', name, draft['comment']))
    if draft.get('name') not in (None, '', path[-1]):
        statements.append({'source': (
            f'ALTER TYPE {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def create_domain(admin, draft):
    _unknown(draft, DOMAIN_CREATE, 'domain')
    name = admin._new_object_name(admin._identifier(draft.get('name')),
                                  draft)
    source = f'CREATE DOMAIN {name} AS ' + admin._safe_fragment(
        draft.get('base_type'), 'base type')
    if not _blank(draft.get('collation')):
        source += ' COLLATE ' + admin._quote(draft['collation'])
    if not _blank(draft.get('default')):
        source += ' DEFAULT ' + admin._safe_fragment(draft['default'],
                                                     'default')
    if draft.get('not_null'):
        source += ' NOT NULL'
    for item in draft.get('checks') or []:
        if not isinstance(item, dict):
            raise RelationalClientError('a check must be an object')
        prefix = (f' CONSTRAINT {admin._quote(item["name"])}'
                  if not _blank(item.get('name')) else '')
        source += prefix + ' CHECK (' + admin._safe_fragment(
            item.get('expression'), 'check expression') + ')'
    statements = [{'source': source, 'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, 'DOMAIN', name, draft['comment']))
    return statements


def alter_domain(admin, draft, target):
    fixed = set(draft) & {'base_type', 'collation', 'not_null', 'checks'}
    if fixed:
        raise RelationalClientError(
            ', '.join(sorted(fixed)) + ' cannot change: YugabyteDB does '
            'not support ALTER DOMAIN SET / DROP NOT NULL or constraint '
            'changes yet')
    _unknown(draft, DOMAIN_ALTER, 'domain change')
    native = (target or {}).get('native') or {}
    path = admin._target_path(target)
    name = admin._qualified(path)
    statements = []
    if 'default' in draft and (draft['default'] or None) != (
            native.get('default') or None):
        clause = ('DROP DEFAULT' if _blank(draft['default']) else
                  'SET DEFAULT ' + admin._safe_fragment(draft['default'],
                                                        'default'))
        statements.append({'source': f'ALTER DOMAIN {name} {clause}',
                           'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, 'DOMAIN', name, draft['comment']))
    if draft.get('name') not in (None, '', path[-1]):
        statements.append({'source': (
            f'ALTER DOMAIN {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements
