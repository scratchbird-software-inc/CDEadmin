"""PostgreSQL domains and user-defined types on the provider tree (M4,
2026-11-11).

Domains: CREATE DOMAIN AS type [COLLATE] [DEFAULT] [NOT NULL] with CHECK
constraints, owner and comment; ALTER DOMAIN RENAME TO / OWNER TO / SET |
DROP NOT NULL / SET | DROP DEFAULT / ADD, DROP, VALIDATE CONSTRAINT / SET
SCHEMA; DROP DOMAIN. Types: CREATE TYPE AS (composite), AS ENUM, AS RANGE
with owner and comment; ALTER TYPE RENAME TO / OWNER TO / SET SCHEMA, enum
ADD VALUE and RENAME VALUE, composite ADD / DROP / RENAME / ALTER
ATTRIBUTE; DROP TYPE. Owner direction 2026-11-11: every field of the type
family form is admitted and compiled: external (base) types with their
support functions and storage properties, shell types, USAGE privileges
(stated, revoked through a grid), security labels, a domain's length and
precision, and the dialog's full-set grids (enumeration labels, composite
members, domain constraints) are diffed against the facts. A multirange is
created with its range type and is refused on its own. Field ids follow
the inherited dialogs (``domain.ui.js``, ``type.ui.js``).

Type names are admitted by PostgreSQL's own parser (``_type_reference``),
expressions as the policy editor admits them.
"""
from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified, _type_reference, privilege_words,
)
from .policies import expression

TYPE_KINDS = {'c': 'composite', 'e': 'enum', 'r': 'range', 'b': 'external',
              'p': 'shell', 'm': 'multirange'}
PRIVILEGE_CODES = {'U': 'USAGE'}
_ALIGNMENTS = {'c': 'char', 's': 'int2', 'i': 'int4', 'd': 'double'}
_STORAGES = {'p': 'plain', 'e': 'external', 'm': 'main', 'x': 'extended'}
_EXTERNAL_FUNCTIONS = (('typinput', 'INPUT'), ('typoutput', 'OUTPUT'),
                       ('typreceive', 'RECEIVE'), ('typsend', 'SEND'),
                       ('typmodin', 'TYPMOD_IN'), ('typmodout', 'TYPMOD_OUT'),
                       ('typanalyze', 'ANALYZE'),
                       ('typsubscript', 'SUBSCRIPT'))
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
            'owner': native.get('owner'),
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
            'typeowner': native.get('owner'),
            'typtype': kind,
            'kind': TYPE_KINDS.get(kind, 'other'),
            'enum': [{'label': item.get('enumlabel')} for item in enum],
            'composite': composite,
            'typacl': list(row.get('typacl') or []),
            'description': native.get('comment')}


def _grantee(value):
    value = _name(value, 'grantee')
    return 'PUBLIC' if value.upper() == 'PUBLIC' else _identifier(
        value, 'grantee')


def _extras(keyword, qualified, draft, alter):
    """USAGE grants, revocations and security labels; stated, never
    diffed. ``keyword`` is DOMAIN or TYPE."""
    statements = []
    if alter:
        for row in _rows(draft, 'revoke', 'revoked grantees'):
            statements.append(f'REVOKE ALL ON TYPE {qualified} FROM '
                              + _grantee(row.get('grantee')))
    for row in _rows(draft, 'typacl', 'privileges'):
        privilege_words(row.get('privileges'), PRIVILEGE_CODES, 'type')
        option = ' WITH GRANT OPTION' if _flag(row, 'with_grant') else ''
        statements.append(f'GRANT USAGE ON TYPE {qualified} TO '
                          f'{_grantee(row.get("grantee"))}{option}')
    for row in _rows(draft, 'seclabels', 'security labels'):
        provider = _name(row.get('provider'), 'provider')
        label = row.get('label')
        if not isinstance(label, str) or not label:
            raise PostgreSQLNativeAdminError('a security label needs text')
        statements.append(f'SECURITY LABEL FOR '
                          f'{_identifier(provider, "provider")} ON {keyword} '
                          f'{qualified} IS {_literal(label, "label")}')
    return statements


def _with_modifiers(type_text, row):
    """The dialog's length and precision beside a type without them."""
    text = str(type_text or '')
    length, precision = row.get('tlength', row.get('typlen')), row.get(
        'precision')
    if '(' in text or _blank(length):
        return text
    for value in (length, precision):
        if value is not None and value != '' and (
                isinstance(value, bool) or not isinstance(value, int)
                or value < 0):
            raise PostgreSQLNativeAdminError(
                'length and precision are whole numbers')
    return text + (f'({length}, {precision})' if not _blank(precision)
                   else f'({length})')


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
                 + _type_reference(_with_modifiers(draft.get('basetype'),
                                                   draft), 'base type'))
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
    statements.extend(_extras('DOMAIN', qualified, draft, False))
    return statements


def _constraint_changes(draft, current):
    """The dialog's full Constraints grid against the facts: new rows
    add, missing names drop, a validated flag turned on validates; a
    changed expression is refused (fixed once created)."""
    if 'constraints' not in draft:
        return [], [], []
    rows = _rows(draft, 'constraints', 'constraints')
    held = {item['conname']: item for item in current['constraints']}
    seen, added, validated = set(), [], []
    for row in rows:
        name = row.get('conname')
        if _blank(name) or name not in held:
            added.append(row)
            continue
        seen.add(name)
        if (row.get('consrc') or '') not in ('', held[name]['consrc']):
            raise PostgreSQLNativeAdminError(
                f'the check expression of {name!r} is fixed once created; '
                'drop and add the constraint')
        if row.get('convalidated') is True and not held[name]['convalidated']:
            validated.append(name)
    dropped = [name for name in held if name not in seen]
    return added, dropped, validated


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
    if not _blank(draft.get('owner')) and draft['owner'] != current.get(
            'owner'):
        statements.append(f'ALTER DOMAIN {qualified} OWNER TO '
                          + _identifier(draft['owner'], 'owner'))
    added, dropped, validated = _constraint_changes(draft, current)
    for name in dropped:
        statements.append(f'ALTER DOMAIN {qualified} DROP CONSTRAINT '
                          + _identifier(name, 'constraint'))
    for row in _rows(draft, 'drop_constraints', 'dropped constraints'):
        statements.append(f'ALTER DOMAIN {qualified} DROP CONSTRAINT '
                          + _identifier(row.get('conname'), 'constraint'))
    for name in validated:
        statements.append(f'ALTER DOMAIN {qualified} VALIDATE CONSTRAINT '
                          + _identifier(name, 'constraint'))
    for row in _rows(draft, 'validate_constraints',
                     'validated constraints'):
        statements.append(f'ALTER DOMAIN {qualified} VALIDATE CONSTRAINT '
                          + _identifier(row.get('conname'), 'constraint'))
    for row in _rows(draft, 'rename_constraints', 'renamed constraints'):
        # The inherited domain-constraint node's own edit (M5 review).
        statements.append(f'ALTER DOMAIN {qualified} RENAME CONSTRAINT '
                          + _identifier(row.get('conname'), 'constraint')
                          + ' TO ' + _identifier(row.get('to'), 'new name'))
    for row in added + _rows(draft, 'add_constraints', 'added constraints'):
        statements.append(_check(qualified, row))
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        text = 'NULL' if _blank(draft['description']) else _literal(
            str(draft['description']), 'comment')
        statements.append(f'COMMENT ON DOMAIN {qualified} IS {text}')
    statements.extend(_extras('DOMAIN', qualified, draft, True))
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
            + _type_reference(_with_modifiers(row.get('type'), row),
                              'member type')
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
        options = ['SUBTYPE = '
                   + _type_reference(draft.get('typname'), 'subtype')]
        for key, keyword in _RANGE_OPTIONS:
            if not _blank(draft.get(key)):
                options.append(f'{keyword} = ' + _reference(draft[key],
                                                            keyword))
        statement = f'CREATE TYPE {qualified} AS RANGE (' + ', '.join(
            options) + ')'
    elif kind == 'p':
        statement = f'CREATE TYPE {qualified}'
    elif kind == 'b':
        statement = _external(qualified, draft)
    elif kind == 'm':
        raise PostgreSQLNativeAdminError(
            'a multirange is created with its range type (multirange type '
            'name); it cannot be created on its own')
    else:
        raise PostgreSQLNativeAdminError(
            'type is composite (c), enumeration (e), range (r), external '
            '(b) or shell (p)')
    statements = [statement]
    if not _blank(draft.get('typeowner')):
        statements.append(f'ALTER TYPE {qualified} OWNER TO '
                          + _identifier(draft['typeowner'], 'owner'))
    if not _blank(draft.get('description')):
        statements.append(f'COMMENT ON TYPE {qualified} IS '
                          + _literal(str(draft['description']), 'comment'))
    statements.extend(_extras('TYPE', qualified, draft, False))
    return statements


def _external(qualified, draft):
    """CREATE TYPE name (INPUT = ..., OUTPUT = ..., ...) from the external
    variant's fields; the functions must already exist (or be declared
    against a shell type), as PostgreSQL requires."""
    options = []
    for key, keyword in _EXTERNAL_FUNCTIONS:
        if not _blank(draft.get(key)):
            options.append(f'{keyword} = ' + _reference(draft[key], keyword))
    if not any(option.startswith(('INPUT', 'OUTPUT')) for option in options):
        raise PostgreSQLNativeAdminError(
            'an external type needs its input and output functions')
    length = draft.get('typlen')
    if not _blank(length):
        if length == -1 or str(length).upper() == 'VARIABLE':
            options.append('INTERNALLENGTH = VARIABLE')
        else:
            if isinstance(length, bool) or not isinstance(length, int) or \
                    length < 1:
                raise PostgreSQLNativeAdminError(
                    'the internal length is a whole number or -1')
            options.append(f'INTERNALLENGTH = {length}')
    if _flag(draft, 'typbyval') if 'typbyval' in draft else False:
        options.append('PASSEDBYVALUE')
    for key, keyword, table in (('typalign', 'ALIGNMENT', _ALIGNMENTS),
                                ('typstorage', 'STORAGE', _STORAGES)):
        if not _blank(draft.get(key)):
            value = draft[key]
            value = table.get(value, value)
            if value not in table.values():
                raise PostgreSQLNativeAdminError(
                    f'{keyword.lower()} is ' + ', '.join(table.values()))
            options.append(f'{keyword} = {value}')
    if not _blank(draft.get('typcategory')):
        category = str(draft['typcategory'])
        if len(category) != 1 or not category.isalnum():
            raise PostgreSQLNativeAdminError('the category is one letter')
        options.append('CATEGORY = ' + _literal(category, 'category'))
    if _flag(draft, 'typispreferred') if 'typispreferred' in draft else False:
        options.append('PREFERRED = true')
    if not _blank(draft.get('typdefault')):
        options.append('DEFAULT = ' + _literal(str(draft['typdefault']),
                                               'default'))
    if not _blank(draft.get('element')):
        options.append('ELEMENT = ' + _type_reference(draft['element'],
                                                      'element'))
    if not _blank(draft.get('typdelim')):
        delimiter = str(draft['typdelim'])
        if len(delimiter) != 1:
            raise PostgreSQLNativeAdminError('the delimiter is one character')
        options.append('DELIMITER = ' + _literal(delimiter, 'delimiter'))
    if _flag(draft, 'is_collatable') if 'is_collatable' in draft else False:
        options.append('COLLATABLE = true')
    return f'CREATE TYPE {qualified} (' + ', '.join(options) + ')'


def _grid_changes(draft, current):
    """The dialog's full enumeration and composite grids against the
    facts, as the provider's own change grids."""
    changes = {}
    if 'enum' in draft and draft['enum'] not in (None, ''):
        wanted = _labels(_rows(draft, 'enum', 'enum labels'))
        held = [item['label'] for item in current['enum']]
        missing = [label for label in held if label not in wanted]
        if missing:
            raise PostgreSQLNativeAdminError(
                'PostgreSQL cannot drop or rename an enumeration value '
                'through the list; use Rename enumeration values')
        added = []
        for index, label in enumerate(wanted):
            if label in held:
                continue
            row = {'label': label}
            if index:
                row['after'] = wanted[index - 1]
            elif len(wanted) > 1:
                row['before'] = wanted[1]
            added.append(row)
        changes['add_values'] = added
    if 'composite' in draft and draft['composite'] not in (None, ''):
        rows = _rows(draft, 'composite', 'composite members')
        held = {item['member_name']: item['type']
                for item in current['composite']}
        seen = set()
        changes['add_attributes'], changes['alter_attributes'] = [], []
        for row in rows:
            name = row.get('member_name')
            if name in held:
                seen.add(name)
                if not _blank(row.get('type')) and _with_modifiers(
                        row['type'], row) != held[name]:
                    changes['alter_attributes'].append(row)
            else:
                changes['add_attributes'].append(row)
        changes['drop_attributes'] = [{'member_name': name} for name in held
                                      if name not in seen]
    return changes


def _alter_type(native, draft):
    current = native.get('type_facts') or type_facts(native)
    schema = _name(current['schema'], 'schema')
    name = _name(current['name'], 'name')
    qualified = _qualified(schema, name)
    kind = current['typtype']
    statements = []
    if not _blank(draft.get('typeowner')) and \
            draft['typeowner'] != current.get('typeowner'):
        statements.append(f'ALTER TYPE {qualified} OWNER TO '
                          + _identifier(draft['typeowner'], 'owner'))
    grid = _grid_changes(draft, current)
    labels = [item['label'] for item in current['enum']]
    renames = _rows(draft, 'rename_values', 'renamed enum values')
    added = _rows(draft, 'add_values', 'added enum values') + grid.get(
        'add_values', [])
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
        rows = _rows(draft, key, key.replace('_', ' ')) + grid.get(key, [])
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
                values['type'] = _type_reference(
                    _with_modifiers(row.get('type'), row), 'member type')
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
    statements.extend(_extras('TYPE', qualified, draft, True))
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


# The type family form's field ids (type.form.json: domain, composite,
# enumeration, range, external, shell and multirange variants) plus the
# provider's own change grids; the validator admits exactly these.
_FAMILY_FIELDS = (
    'variant', 'name', 'oid', 'owner', 'basensp', 'typeowner', 'schema',
    'sysdomain', 'is_sys_type', 'description', 'typtype', 'basetype',
    'typlen', 'precision', 'typdefault', 'typnotnull', 'collname',
    'composite', 'enum', 'typname', 'opcname', 'rngcanonical', 'rngsubdiff',
    'rngmultirangetype', 'alias', 'member_list', 'enum_list', 'constraints',
    'typinput', 'typoutput', 'typreceive', 'typsend', 'typmodin',
    'typmodout', 'typanalyze', 'typsubscript', 'typcategory',
    'typispreferred', 'element', 'typdelim', 'typalign', 'typstorage',
    'typbyval', 'is_collatable', 'type_acl', 'typacl', 'seclabels')
_OWN_GRIDS = {
    'domain': ('add_constraints', 'drop_constraints', 'validate_constraints',
               'rename_constraints'),
    'type': ('add_values', 'rename_values', 'add_attributes',
             'alter_attributes', 'rename_attributes', 'drop_attributes'),
}
_GRIDS = ('composite', 'enum', 'constraints', 'typacl', 'seclabels', 'revoke')
_BOOLEANS = ('sysdomain', 'is_sys_type', 'typnotnull', 'typispreferred',
             'typbyval', 'is_collatable')
_NUMBERS = ('typlen', 'precision')
_SELECTS = {
    'typtype': [{'value': code, 'label': word.title()}
                for code, word in TYPE_KINDS.items()],
    'typalign': [{'value': code, 'label': word}
                 for code, word in _ALIGNMENTS.items()],
    'typstorage': [{'value': code, 'label': word.upper()}
                   for code, word in _STORAGES.items()],
}


def _family_form(kind, operation, field):
    """The validator's view of the type family form: every field id the
    dialog sends, typed loosely; the family form file carries the labels,
    tabs, options and grid columns."""
    label = 'domain' if kind == 'domain' else 'type'
    facts_key = 'domain_facts' if kind == 'domain' else 'type_facts'
    if operation == 'drop':
        return {'form_id': f'postgresql-{kind}-drop',
                'form_key': f'native:postgresql:schema:{kind}',
                'title': f'Drop {label}', 'fields': [
                    field('cascade', 'Drop dependent objects', 'boolean'),
                    field('confirmation', f'Type the {label} name to confirm',
                          required=True)]}
    alter = operation == 'alter'

    def initial(key):
        return {'initial_value_path': [facts_key, key]} if alter else {}
    fields = []
    own = _OWN_GRIDS[kind] if alter else ()
    for field_id in _FAMILY_FIELDS + own + (('revoke',) if alter else ()):
        title = field_id.replace('_', ' ').capitalize()
        if field_id in _GRIDS or field_id in own:
            fields.append(field(field_id, title, 'grid', columns=[],
                                **initial(field_id)))
        elif field_id in _BOOLEANS:
            fields.append(field(field_id, title, 'boolean',
                                **initial(field_id)))
        elif field_id in _NUMBERS:
            fields.append(field(field_id, title, 'number'))
        elif field_id in _SELECTS:
            fields.append(field(field_id, title, 'select',
                                options=_SELECTS[field_id],
                                required=(field_id == 'typtype' and
                                          kind == 'type' and not alter),
                                **initial(field_id)))
        elif field_id == 'typcategory':
            fields.append(field(field_id, 'Category', 'text', max_length=1))
        else:
            required = not alter and (
                field_id == 'name' or
                (kind == 'domain' and field_id in ('basensp', 'basetype')) or
                (kind == 'type' and field_id == 'schema'))
            fields.append(field(field_id, title, required=required,
                                **initial(field_id)))
    notes = ('The Constraints grid is the full set: a new row adds, a row '
             'left out drops, a validated flag turned on validates; the '
             'check expression is fixed once created.') if kind == \
        'domain' else (
        'The enumeration and composite grids are the full set: new '
        'labels are added after their predecessor (PostgreSQL cannot drop '
        'or rename a value through the list), new members are added, '
        'members left out are dropped, a changed type is altered. '
        'External and shell types are created from their fields; a '
        'multirange comes with its range type.')
    return {'form_id': f'postgresql-{kind}-{operation}',
            'form_key': f'native:postgresql:schema:{kind}',
            'title': f'{operation.title()} {label}', 'fields': fields,
            'notes': notes + ' Privileges and labels are stated; the Revoke '
                             'grid removes privileges.'}


def domain_form(operation, field):
    return _family_form('domain', operation, field)


def type_form(operation, field):
    return _family_form('type', operation, field)
