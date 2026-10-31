"""CockroachDB user-defined types: enums and composites.

Checked live on 26.1.3: CREATE TYPE ... AS ENUM / AS (fields); ALTER TYPE
... ADD VALUE [BEFORE|AFTER], RENAME VALUE, DROP VALUE (refused while a
row uses the value), RENAME TO, COMMENT ON TYPE. A composite's attributes
cannot be added, dropped, renamed or retyped (unimplemented), and enum
values cannot be reordered.
"""
from ...sdk.relational import RelationalClientError

KINDS = ('ENUM', 'COMPOSITE')
CREATE_KEYS = {'name', 'parent', 'type_kind', 'enum_values', 'fields',
               'comment'}
ALTER_KEYS = {'name', 'enum_values', 'rename_values', 'comment',
              'confirmation'}


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


def _comment(admin, name, value):
    text = 'NULL' if value in (None, '') else admin._literal(str(value))
    return {'source': f'COMMENT ON TYPE {name} IS {text}', 'parameters': ()}


def create(admin, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown type option: ' + ', '.join(sorted(unknown)))
    name = admin._new_object_name(admin._identifier(draft.get('name')),
                                  draft)
    kind = str(draft.get('type_kind') or '').upper()
    if kind == 'ENUM':
        definition = 'ENUM (' + ', '.join(
            admin._literal(item)
            for item in _strings(draft.get('enum_values'),
                                 'enum values')) + ')'
    elif kind == 'COMPOSITE':
        fields = draft.get('fields')
        if not isinstance(fields, list) or not fields:
            raise RelationalClientError('a composite type needs fields')
        definition = '(' + ', '.join(
            admin._quote(item.get('name')) + ' ' + admin._safe_type(
                item.get('type'), 'field type', dimensions=1)
            for item in fields) + ')'
    else:
        raise RelationalClientError('type kind is ENUM or COMPOSITE')
    statements = [{'source': f'CREATE TYPE {name} AS {definition}',
                   'parameters': ()}]
    if draft.get('comment') not in (None, ''):
        statements.append(_comment(admin, name, draft['comment']))
    return statements


def alter(admin, draft, target):
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            ', '.join(sorted(unknown)) + ' cannot change in place; '
            "a composite type's fields are fixed once created")
    native = (target or {}).get('native') or {}
    path = admin._target_path(target)
    name = admin._qualified(path)
    statements = []
    current = list(native.get('enum_values') or [])
    renames = draft.get('rename_values') or []
    if (renames or 'enum_values' in draft) and \
            native.get('type_kind') != 'ENUM':
        raise RelationalClientError('only an enum has values')
    for item in renames:
        if not isinstance(item, dict) or item.get('from') not in current:
            raise RelationalClientError(
                'rename a value the enum holds (from)')
        new = _strings([item.get('to')], 'new value')[0]
        if new in current:
            raise RelationalClientError(f'the enum already has {new!r}')
        statements.append({'source': (
            f'ALTER TYPE {name} RENAME VALUE '
            f'{admin._literal(item["from"])} TO {admin._literal(new)}'),
            'parameters': ()})
        current[current.index(item['from'])] = new
    if 'enum_values' in draft:
        statements += _value_changes(admin, name, current, _strings(
            draft['enum_values'], 'enum values'))
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, name, draft['comment']))
    if draft.get('name') not in (None, '', path[-1]):
        statements.append({'source': (
            f'ALTER TYPE {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def _value_changes(admin, name, current, wanted):
    kept = [item for item in current if item in wanted]
    if kept != [item for item in wanted if item in current]:
        raise RelationalClientError(
            'CockroachDB cannot reorder enum values; add and drop instead')
    statements = []
    for index, item in enumerate(wanted):
        if item in current:
            continue
        # Values are added in order, so the previous one is in place.
        if index:
            anchor = f' AFTER {admin._literal(wanted[index - 1])}'
        elif current:
            anchor = f' BEFORE {admin._literal(current[0])}'
        else:
            anchor = ''
        statements.append({'source': (
            f'ALTER TYPE {name} ADD VALUE {admin._literal(item)}{anchor}'),
            'parameters': ()})
    for item in current:
        if item not in wanted:
            statements.append({'source': (
                f'ALTER TYPE {name} DROP VALUE {admin._literal(item)}'),
                'parameters': ()})
    return statements


def form(field, operation):
    if operation == 'create':
        return {'form_id': 'cockroachdb.type.create',
                'title': 'Create CockroachDB type', 'fields': [
                    field('name', 'Name', 'text', True),
                    field('parent', 'Schema', 'text'),
                    field('type_kind', 'Kind', 'select', True,
                          default='ENUM', options=KINDS),
                    field('comment', 'Comment', 'text'),
                ], 'notes': 'Enum values and composite fields are '
                            'descriptor grids (type.form.json).'}
    return {'form_id': 'cockroachdb.type.alter',
            'title': 'Alter CockroachDB type', 'fields': [
                {**field('name', 'Name', 'text', True),
                 'initial_value_path': ['name']},
                {**field('comment', 'Comment', 'text'),
                 'initial_value_path': ['comment']},
            ]}
