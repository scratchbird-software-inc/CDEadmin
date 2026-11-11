"""PostgreSQL domains and user-defined types on the provider tree (M4,
2026-11-11).

Domains: CREATE DOMAIN AS type [COLLATE] [DEFAULT] [NOT NULL] with CHECK
constraints, owner and comment; ALTER DOMAIN RENAME TO / OWNER TO / SET |
DROP NOT NULL / SET | DROP DEFAULT / ADD, DROP, VALIDATE CONSTRAINT / SET
SCHEMA; DROP DOMAIN. Types: CREATE TYPE AS (composite), AS ENUM, AS RANGE
with owner and comment; ALTER TYPE RENAME TO / OWNER TO / SET SCHEMA, enum
ADD VALUE and RENAME VALUE, composite ADD / DROP / RENAME / ALTER
ATTRIBUTE; DROP TYPE. External (base) and shell types, type privileges and
security labels stay with the inherited dialog. Field ids follow the
inherited dialogs (``domain.ui.js``, ``type.ui.js``).

Type names are admitted by PostgreSQL's own parser (``_type_reference``),
expressions as the policy editor admits them.
"""
from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified, _type_reference,
)
from .policies import expression

TYPE_KINDS = {'c': 'composite', 'e': 'enum', 'r': 'range'}
_RANGE_OPTIONS = (('opcname', 'SUBTYPE_OPCLASS'), ('collname', 'COLLATION'),
                  ('rngcanonical', 'CANONICAL'),
                  ('rngsubdiff', 'SUBTYPE_DIFF'),
                  ('rngmultirangetype', 'MULTIRANGE_TYPE_NAME'))


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


def _reference(value, label):
    """A possibly qualified catalog name (collation, function, opclass)."""
    from .native_admin import _reference as catalog_reference
    return catalog_reference(value, label)


# -- facts --------------------------------------------------------------------

def domain_facts(native, constraints=None):
    """Current values of a domain. ``constraints`` lists the captured
    pg_constraint resources (same capture) keyed by the domain OID."""
    row = native.get('catalog_row') or {}
    checks = []
    for item in (constraints or {}).get(native.get('oid'), []):
        definition = item.get('definition') or ''
        if not definition.startswith('CHECK'):
            continue
        # pg_get_constraintdef appends NOT VALID to an unvalidated check.
        if definition.endswith(' NOT VALID'):
            definition = definition[:-len(' NOT VALID')]
        checks.append({'conname': item.get('name'),
                       'consrc': definition[len('CHECK ('):-1]
                       if definition.endswith(')') else definition,
                       'convalidated': bool(
                           (item.get('catalog_row') or {}).get(
                               'convalidated', True))})
    return {'name': native.get('name') or row.get('typname'),
            'basensp': native.get('schema'),
            'typnotnull': bool(row.get('typnotnull', False)),
            'typdefault': row.get('typdefault'),
            'description': native.get('comment'),
            'constraints': checks}


def type_facts(native, attributes=None):
    """Current values of a type. ``attributes`` maps relation OID to the
    captured pg_attribute rows of a composite type's relation."""
    row = native.get('catalog_row') or {}
    kind = row.get('typtype')
    enum = sorted((native.get('children') or {}).get('pg_enum') or [],
                  key=lambda item: item.get('enumsortorder', 0))
    try:
        relation = int(row.get('typrelid') or 0)
    except (TypeError, ValueError):
        relation = 0
    composite = [{'member_name': item.get('attname'),
                  'type': item.get('formatted_type')}
                 for item in (attributes or {}).get(relation, [])
                 if not item.get('attisdropped')]
    return {'name': native.get('name') or row.get('typname'),
            'schema': native.get('schema'),
            'typtype': kind,
            'kind': TYPE_KINDS.get(kind, 'other'),
            'enum': [{'label': item.get('enumlabel')} for item in enum],
            'composite': composite,
            'description': native.get('comment')}


# -- domains ------------------------------------------------------------------

def _check(qualified, row):
    name = row.get('conname')
    prefix = ('' if _blank(name) else
              f'CONSTRAINT {_identifier(name, "constraint name")} ')
    clause = (f'{prefix}CHECK ('
              + expression(row.get('consrc'), 'check') + ')')
    if row.get('convalidated') is False:
        clause += ' NOT VALID'
    return f'ALTER DOMAIN {qualified} ADD {clause}'


def _create_domain(draft):
    schema = _name(draft.get('basensp'), 'schema')
    qualified = _qualified(schema, draft.get('name'))
    statement = (f'CREATE DOMAIN {qualified} AS '
                 + _type_reference(draft.get('basetype'), 'base type'))
    if not _blank(draft.get('collname')):
        statement += ' COLLATE ' + _reference(draft['collname'],
                                              'collation')
    if not _blank(draft.get('typdefault')):
        statement += ' DEFAULT ' + expression(draft['typdefault'],
                                              'default')
    if _flag(draft, 'typnotnull'):
        statement += ' NOT NULL'
    statements = [statement]
    if not _blank(draft.get('owner')):
        statements.append(f'ALTER DOMAIN {qualified} OWNER TO '
                          + _identifier(draft['owner'], 'owner'))
    for row in _rows(draft, 'constraints', 'constraints'):
        statements.append(_check(qualified, row))
    if not _blank(draft.get('description')):
        statements.append(f'COMMENT ON DOMAIN {qualified} IS '
                          + _literal(str(draft['description']), 'comment'))
    return statements


def _alter_domain(native, draft):
    current = native.get('domain_facts') or domain_facts(native)
    schema = _name(current['basensp'], 'schema')
    name = _name(current['name'], 'name')
    qualified = _qualified(schema, name)
    statements = []
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER DOMAIN {qualified} RENAME TO '
                          + _identifier(new_name, 'name'))
        qualified = _qualified(schema, new_name)
    if 'typnotnull' in draft and draft['typnotnull'] is not None and \
            _flag(draft, 'typnotnull') != current['typnotnull']:
        statements.append(f'ALTER DOMAIN {qualified} '
                          + ('SET NOT NULL' if draft['typnotnull']
                             else 'DROP NOT NULL'))
    if 'typdefault' in draft and (draft['typdefault'] or None) != (
            current['typdefault'] or None):
        statements.append(f'ALTER DOMAIN {qualified} ' + (
            'DROP DEFAULT' if _blank(draft['typdefault']) else
            'SET DEFAULT ' + expression(draft['typdefault'], 'default')))
    if not _blank(draft.get('owner')):
        statements.append(f'ALTER DOMAIN {qualified} OWNER TO '
                          + _identifier(draft['owner'], 'owner'))
    for row in _rows(draft, 'drop_constraints', 'dropped constraints'):
        statements.append(f'ALTER DOMAIN {qualified} DROP CONSTRAINT '
                          + _identifier(row.get('conname'), 'constraint'))
    for row in _rows(draft, 'validate_constraints',
                     'validated constraints'):
        statements.append(f'ALTER DOMAIN {qualified} VALIDATE CONSTRAINT '
                          + _identifier(row.get('conname'), 'constraint'))
    for row in _rows(draft, 'rename_constraints', 'renamed constraints'):
        # The inherited domain-constraint node's own edit (M5 review).
        statements.append(f'ALTER DOMAIN {qualified} RENAME CONSTRAINT '
                          + _identifier(row.get('conname'), 'constraint')
                          + ' TO ' + _identifier(row.get('to'), 'new name'))
    for row in _rows(draft, 'add_constraints', 'added constraints'):
        statements.append(_check(qualified, row))
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        text = 'NULL' if _blank(draft['description']) else _literal(
            str(draft['description']), 'comment')
        statements.append(f'COMMENT ON DOMAIN {qualified} IS {text}')
    new_schema = draft.get('basensp')
    if not _blank(new_schema) and new_schema != schema:
        statements.append(f'ALTER DOMAIN {qualified} SET SCHEMA '
                          + _identifier(new_schema, 'schema'))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _drop(keyword, current, draft):
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    schema = current.get('basensp') or current.get('schema')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP {keyword} {_qualified(schema, name)}{cascade}']


# -- types --------------------------------------------------------------------

def _attribute(row):
    return (f'{_identifier(row.get("member_name"), "member name")} '
            + _type_reference(row.get('type'), 'member type')
            + ('' if _blank(row.get('collation')) else
               ' COLLATE ' + _reference(row['collation'], 'collation')))


def _labels(rows):
    labels = []
    for row in rows:
        label = row.get('label')
        if not isinstance(label, str) or not label or '\x00' in label:
            raise PostgreSQLNativeAdminError('enum labels must be text')
        if label in labels:
            raise PostgreSQLNativeAdminError(f'enum label {label!r} repeats')
        labels.append(label)
    return labels


def _create_type(draft):
    schema = _name(draft.get('schema'), 'schema')
    qualified = _qualified(schema, draft.get('name'))
    kind = draft.get('typtype')
    if kind == 'c':
        members = _rows(draft, 'composite', 'composite members')
        if not members:
            raise PostgreSQLNativeAdminError(
                'a composite type needs at least one member')
        statement = f'CREATE TYPE {qualified} AS (' + ', '.join(
            _attribute(row) for row in members) + ')'
    elif kind == 'e':
        labels = _labels(_rows(draft, 'enum', 'enum labels'))
        statement = f'CREATE TYPE {qualified} AS ENUM (' + ', '.join(
            _literal(label, 'enum label') for label in labels) + ')'
    elif kind == 'r':
        options = ['SUBTYPE = ' + _type_reference(draft.get('typname'),
                                                 'subtype')]
        for key, keyword in _RANGE_OPTIONS:
            if not _blank(draft.get(key)):
                options.append(f'{keyword} = ' + _reference(draft[key],
                                                            keyword))
        statement = f'CREATE TYPE {qualified} AS RANGE (' + ', '.join(
            options) + ')'
    else:
        raise PostgreSQLNativeAdminError(
            'type is composite (c), enumeration (e) or range (r); external '
            'and shell types stay with the inherited dialog')
    statements = [statement]
    if not _blank(draft.get('typeowner')):
        statements.append(f'ALTER TYPE {qualified} OWNER TO '
                          + _identifier(draft['typeowner'], 'owner'))
    if not _blank(draft.get('description')):
        statements.append(f'COMMENT ON TYPE {qualified} IS '
                          + _literal(str(draft['description']), 'comment'))
    return statements


def _alter_type(native, draft):
    current = native.get('type_facts') or type_facts(native)
    schema = _name(current['schema'], 'schema')
    name = _name(current['name'], 'name')
    qualified = _qualified(schema, name)
    kind = current['typtype']
    statements = []
    if not _blank(draft.get('typeowner')):
        statements.append(f'ALTER TYPE {qualified} OWNER TO '
                          + _identifier(draft['typeowner'], 'owner'))
    labels = [item['label'] for item in current['enum']]
    renames = _rows(draft, 'rename_values', 'renamed enum values')
    added = _rows(draft, 'add_values', 'added enum values')
    if (renames or added) and kind != 'e':
        raise PostgreSQLNativeAdminError('only an enumeration has values')
    for row in renames:
        source, target = row.get('from'), row.get('to')
        if source not in labels:
            raise PostgreSQLNativeAdminError(
                f'the enumeration has no value {source!r}')
        if not isinstance(target, str) or not target or target in labels:
            raise PostgreSQLNativeAdminError(
                'rename to a new, non-empty value')
        statements.append(f'ALTER TYPE {qualified} RENAME VALUE '
                          f'{_literal(source, "value")} TO '
                          f'{_literal(target, "value")}')
        labels[labels.index(source)] = target
    for row in added:
        label = _labels([row])[0]
        if label in labels:
            raise PostgreSQLNativeAdminError(
                f'the enumeration already has {label!r}')
        clause = f'ALTER TYPE {qualified} ADD VALUE {_literal(label, "value")}'
        for key, keyword in (('before', 'BEFORE'), ('after', 'AFTER')):
            if not _blank(row.get(key)):
                if row[key] not in labels:
                    raise PostgreSQLNativeAdminError(
                        f'the enumeration has no value {row[key]!r}')
                clause += f' {keyword} {_literal(row[key], "value")}'
        statements.append(clause)
        labels.append(label)
    attribute_changes = [
        ('drop_attributes', 'DROP ATTRIBUTE {name}'),
        ('rename_attributes', 'RENAME ATTRIBUTE {name} TO {target}'),
        ('alter_attributes', 'ALTER ATTRIBUTE {name} SET DATA TYPE {type}'),
        ('add_attributes', 'ADD ATTRIBUTE {definition}')]
    members = {item['member_name'] for item in current['composite']}
    for key, template in attribute_changes:
        rows = _rows(draft, key, key.replace('_', ' '))
        if rows and kind != 'c':
            raise PostgreSQLNativeAdminError(
                'only a composite type has attributes')
        for row in rows:
            member = row.get('member_name')
            if key != 'add_attributes' and member not in members:
                raise PostgreSQLNativeAdminError(
                    f'the type has no attribute {member!r}')
            values = {'name': _identifier(member, 'member name')
                      if key != 'add_attributes' else ''}
            if key == 'rename_attributes':
                values['target'] = _identifier(row.get('to'), 'new name')
                members.discard(member)
                members.add(row.get('to'))
            elif key == 'alter_attributes':
                values['type'] = _type_reference(row.get('type'),
                                                 'member type')
            elif key == 'add_attributes':
                values['definition'] = _attribute(row)
                members.add(member)
            else:
                members.discard(member)
            statements.append(f'ALTER TYPE {qualified} '
                              + template.format(**values))
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        text = 'NULL' if _blank(draft['description']) else _literal(
            str(draft['description']), 'comment')
        statements.append(f'COMMENT ON TYPE {qualified} IS {text}')
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER TYPE {qualified} RENAME TO '
                          + _identifier(new_name, 'name'))
        qualified = _qualified(schema, new_name)
    new_schema = draft.get('schema')
    if not _blank(new_schema) and new_schema != schema:
        statements.append(f'ALTER TYPE {qualified} SET SCHEMA '
                          + _identifier(new_schema, 'schema'))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def compile_operation(kind, operation, native, draft):
    """One exact native text for a domain or type lifecycle."""
    if kind == 'domain':
        if operation == 'create':
            statements = _create_domain(draft)
        elif operation == 'alter':
            statements = _alter_domain(native, draft)
        elif operation == 'drop':
            statements = _drop('DOMAIN', native.get('domain_facts')
                               or domain_facts(native), draft)
        else:
            raise PostgreSQLNativeAdminError(
                'domain inspection stays with the provider tree')
    else:
        if operation == 'create':
            statements = _create_type(draft)
        elif operation == 'alter':
            statements = _alter_type(native, draft)
        elif operation == 'drop':
            statements = _drop('TYPE', native.get('type_facts')
                               or type_facts(native), draft)
        else:
            raise PostgreSQLNativeAdminError(
                'type inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


# -- forms --------------------------------------------------------------------

def _grid(field, name, label, columns, **kw):
    return field(name, label, 'grid', columns=columns, **kw)


def _column(field_id, label, control='text', required=False, **extra):
    return {'field_id': field_id, 'label': label, 'control': control,
            'required': required, **extra}


def domain_form(operation, field):
    """Dialog fields; ids follow the inherited domain dialog."""
    check_columns = [_column('conname', 'Name'),
                     _column('consrc', 'Check expression', required=True),
                     _column('convalidated', 'Validated', 'boolean')]
    name_column = [_column('conname', 'Name', required=True)]
    if operation == 'drop':
        fields = [field('cascade', 'Drop dependent objects', 'boolean'),
                  field('confirmation', 'Type the domain name to confirm',
                        required=True)]
    elif operation == 'create':
        fields = [field('name', 'Name', required=True),
                  field('basensp', 'Schema', required=True),
                  field('basetype', 'Base type', required=True,
                        help='A native type, with its modifiers.'),
                  field('collname', 'Collation'),
                  field('typdefault', 'Default', 'code'),
                  field('typnotnull', 'Not NULL', 'boolean'),
                  field('owner', 'Owner'),
                  field('description', 'Comment', 'multiline'),
                  _grid(field, 'constraints', 'Check constraints',
                        check_columns)]
    else:
        def initial(key):
            return {'initial_value_path': ['domain_facts', key]}
        fields = [field('name', 'Name', **initial('name')),
                  field('basensp', 'Schema', help='A different schema runs '
                        'SET SCHEMA.', **initial('basensp')),
                  field('typdefault', 'Default', 'code',
                        **initial('typdefault')),
                  field('typnotnull', 'Not NULL', 'boolean',
                        **initial('typnotnull')),
                  field('owner', 'Owner', help='Empty keeps the owner.'),
                  field('description', 'Comment', 'multiline',
                        **initial('description')),
                  _grid(field, 'add_constraints', 'Add check constraints',
                        check_columns),
                  _grid(field, 'drop_constraints', 'Drop constraints',
                        name_column),
                  _grid(field, 'validate_constraints',
                        'Validate constraints', name_column),
                  _grid(field, 'rename_constraints', 'Rename constraints',
                        name_column + [_column('to', 'New name',
                                               required=True)])]
    return {'form_id': f'postgresql-domain-{operation}',
            'form_key': 'native:postgresql:schema:domain',
            'title': f'{operation.title()} domain', 'fields': fields}


def type_form(operation, field):
    """Dialog fields; ids follow the inherited type dialog."""
    member_columns = [_column('member_name', 'Member name', required=True),
                      _column('type', 'Type', required=True),
                      _column('collation', 'Collation')]
    if operation == 'drop':
        fields = [field('cascade', 'Drop dependent objects', 'boolean'),
                  field('confirmation', 'Type the type name to confirm',
                        required=True)]
    elif operation == 'create':
        fields = [
            field('name', 'Name', required=True),
            field('schema', 'Schema', required=True),
            field('typtype', 'Type', 'select', required=True, options=[
                {'value': 'c', 'label': 'Composite'},
                {'value': 'e', 'label': 'Enumeration'},
                {'value': 'r', 'label': 'Range'}], default='e'),
            _grid(field, 'composite', 'Composite members', member_columns,
                  visible_when={'field_id': 'typtype', 'equals': 'c'}),
            _grid(field, 'enum', 'Enumeration labels',
                  [_column('label', 'Label', required=True)],
                  visible_when={'field_id': 'typtype', 'equals': 'e'}),
            field('typname', 'Subtype',
                  visible_when={'field_id': 'typtype', 'equals': 'r'}),
            field('opcname', 'Subtype operator class',
                  visible_when={'field_id': 'typtype', 'equals': 'r'}),
            field('collname', 'Collation',
                  visible_when={'field_id': 'typtype', 'equals': 'r'}),
            field('rngcanonical', 'Canonical function',
                  visible_when={'field_id': 'typtype', 'equals': 'r'}),
            field('rngsubdiff', 'Subtype diff function',
                  visible_when={'field_id': 'typtype', 'equals': 'r'}),
            field('rngmultirangetype', 'Multirange type name',
                  visible_when={'field_id': 'typtype', 'equals': 'r'}),
            field('typeowner', 'Owner'),
            field('description', 'Comment', 'multiline')]
    else:
        def initial(key):
            return {'initial_value_path': ['type_facts', key]}
        fields = [
            field('name', 'Name', **initial('name')),
            field('schema', 'Schema', help='A different schema runs SET '
                  'SCHEMA.', **initial('schema')),
            field('typeowner', 'Owner', help='Empty keeps the owner.'),
            field('description', 'Comment', 'multiline',
                  **initial('description')),
            _grid(field, 'add_values', 'Add enumeration values', [
                _column('label', 'Label', required=True),
                _column('before', 'Before'), _column('after', 'After')]),
            _grid(field, 'rename_values', 'Rename enumeration values', [
                _column('from', 'From', required=True),
                _column('to', 'To', required=True)]),
            _grid(field, 'add_attributes', 'Add attributes', member_columns),
            _grid(field, 'alter_attributes', 'Change attribute types', [
                _column('member_name', 'Member name', required=True),
                _column('type', 'Type', required=True)]),
            _grid(field, 'rename_attributes', 'Rename attributes', [
                _column('member_name', 'Member name', required=True),
                _column('to', 'To', required=True)]),
            _grid(field, 'drop_attributes', 'Drop attributes', [
                _column('member_name', 'Member name', required=True)])]
    return {'form_id': f'postgresql-type-{operation}',
            'form_key': 'native:postgresql:schema:type',
            'title': f'{operation.title()} type', 'fields': fields,
            'notes': 'External and shell types, type privileges and '
                     'security labels stay with the inherited dialog.'}
