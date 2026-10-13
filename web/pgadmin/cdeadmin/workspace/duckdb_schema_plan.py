"""Three-way DuckDB DDN design preview; never an execution authorization."""

from copy import deepcopy
import re

from .firebird_catalog_import import _equal
from .firebird_schema_plan import digest
from ..providers.duckdb.provider import _resource_id


_KINDS = {'schema': 'SCHEMA', 'table': 'TABLE', 'view': 'VIEW',
          'sequence': 'SEQUENCE', 'type': 'TYPE', 'macro': 'MACRO',
          'index': 'INDEX', 'column': 'COLUMN'}
_NAME = r'"(?:""|[^"])+"'
_TYPE_FIELDS = frozenset({'data_type', 'data_type_id',
    'character_maximum_length', 'numeric_precision',
    'numeric_precision_radix', 'numeric_scale'})
_SEQUENCE_OPTIONS = ('start_value', 'min_value', 'max_value', 'increment_by', 'cycle')
_TYPE_CATALOG_FIELDS = ('size_bytes', 'logical_type', 'category', 'labels', 'resolved_type')


def _quote(value):
    if not isinstance(value, str) or not value or '\x00' in value or len(value.encode('utf8')) > 256:
        raise ValueError('Native identifier is empty or exceeds 256 bytes')
    return '"' + value.replace('"', '""') + '"'


def _root(model):
    if model['provenance'].get('mapping') != 'scratchrobin.duckdb.catalog@1':
        raise ValueError('Native DuckDB DDN catalog is required')
    roots = [row for row in model['rows'].values() if row['kind'] == 'database']
    if len(roots) != 1 or roots[0]['system'] != 'false':
        raise ValueError('One exact registered DuckDB file root is required')
    return roots[0]['name']


def _address(row, catalog):
    kind, path = row['kind'], row['path']
    if kind not in _KINDS or not isinstance(path, list):
        raise ValueError('Native adapter for this object kind is not admitted')
    expected = 2 if kind == 'schema' else 4 if kind in {'index', 'column'} else 3
    if len(path) != expected or path[0] != catalog or path[-1] != row['name']:
        raise ValueError('Object must identify this exact catalog and native schema')
    if row['resource_id'] != _resource_id(kind, path[:-1], path[-1]) or row['system'] != 'false':
        raise ValueError('Native object identity or system classification changed')
    native = row['native']
    if native.get('system_object') is not False or native.get('catalog_metadata', {}).get('temporary') is True:
        raise ValueError('System or temporary definitions are not deployable from a file design')
    return '.'.join(_quote(part) for part in path)


def _require_table_parent(row, live, catalog):
    path = row['path']
    parent_id = _resource_id('table', path[:2], path[2])
    parent = live['rows'].get(parent_id)
    if parent is None or parent['kind'] != 'table':
        raise ValueError('Native column mutation requires an observed table parent')
    _address(parent, catalog)


def _definition(row):
    native = row['native']
    catalog = {key: value for key, value in native.get('catalog_metadata', {}).items()
               if key not in {'oid', 'last_value'}}
    return {'ddl': native.get('ddl'),
            'catalog': catalog,
            'columns': native.get('columns') if row['kind'] in {'table', 'view'} else None,
            'constraints': native.get('constraints') if row['kind'] == 'table' else None,
            'indexes': native.get('indexes') if row['kind'] == 'table' else None,
            'overloads': native.get('overloads') if row['kind'] == 'macro' else None,
            'definition': native.get('definition') if row['kind'] == 'macro' else None,
            'parameters': native.get('parameters') if row['kind'] == 'macro' else None,
            'overload_count': native.get('overload_count') if row['kind'] == 'macro' else None}


def _validated_ddl(source, kind, path, *, replace=False):
    if (not isinstance(source, str) or not source or '\x00' in source or
            len(source.encode('utf8')) > 1024 * 1024):
        raise ValueError('One bounded native DDL statement is required')
    qualified = '.'.join(_quote(part) for part in path)
    prefix = 'CREATE ' + ('OR REPLACE ' if replace else '') + _KINDS[kind] + ' ' + qualified
    # Only exact, fully qualified targets are admitted. Captured unqualified
    # DuckDB DDL must be edited to an explicit target before review.
    pattern = re.compile(r'^\s*' + re.escape(prefix) + r'(?=\s|\(|;|$)', re.I)
    if not pattern.match(source):
        raise ValueError('DDL must start with the exact fully qualified native CREATE target')
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected this DDL') from None
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.CREATE:
        raise ValueError('Exactly one native CREATE statement is required')
    return source


def _validated_index_ddl(source, path):
    if (not isinstance(source, str) or not source or '\x00' in source or
            len(source.encode('utf8')) > 1024 * 1024):
        raise ValueError('One bounded native index DDL statement is required')
    # DuckDB qualifies the table, but its CREATE INDEX grammar accepts a
    # separate local index name. Exact quoted segments prevent name confusion.
    table = '.'.join(_quote(part) for part in path[:3])
    index = _quote(path[3])
    prefix = (r'^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+' +
              re.escape(index) + r'\s+ON\s+' + re.escape(table) + r'(?=\s*\()')
    if not re.match(prefix, source, re.I):
        raise ValueError('Index DDL must name the exact index and fully qualified native table')
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected this index DDL') from None
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.CREATE:
        raise ValueError('Exactly one native CREATE INDEX statement is required')
    return source


def _native_column_type(data_type):
    if (not isinstance(data_type, str) or not data_type.strip() or
            len(data_type.encode('utf8')) > 1024 or '\x00' in data_type):
        raise ValueError('Column change requires one bounded native data type')
    if (any(marker in data_type for marker in (';', '--', '/*', '*/')) or
            re.search(r'\b(?:DEFAULT|CONSTRAINT|CHECK|GENERATED|PRIMARY|UNIQUE|REFERENCES|USING)\b',
                      data_type, re.I)):
        raise ValueError('Column data type cannot contain SQL clauses or comments')
    return data_type.strip()


def _validated_column_add(row):
    native = row['native']
    metadata = native.get('catalog_metadata', {})
    data_type = _native_column_type(metadata.get('data_type'))
    if metadata.get('nullable') is False or metadata.get('comment') or native.get('ddl'):
        raise ValueError('Column constraints, comments and direct DDL are not admitted by ADD COLUMN')
    parent = '.'.join(_quote(part) for part in row['path'][:3])
    source = 'ALTER TABLE ' + parent + ' ADD COLUMN ' + _quote(row['name']) + ' ' + data_type
    default = metadata.get('default')
    if default is not None:
        if not isinstance(default, str) or not default.strip():
            raise ValueError('Native column default must be a nonempty SQL expression')
        source += ' DEFAULT ' + default.strip()
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected this column addition') from None
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.ALTER:
        raise ValueError('Exactly one native ADD COLUMN statement is required')
    return source


def _validated_column_alter(before, after, change):
    previous = before['native'].get('catalog_metadata', {})
    desired = after['native'].get('catalog_metadata', {})
    action = change.get('action')
    field = {'set-default': 'default', 'set-nullable': 'nullable',
             'set-type': 'data_type'}.get(action)
    if field is None or _equal(previous.get(field), desired.get(field)):
        raise ValueError('Column alteration must change its one declared native field')
    if set(change) - ({'action', 'using'} if action == 'set-type' else {'action'}):
        raise ValueError('Column alteration has unsupported change options')
    allowed = _TYPE_FIELDS if action == 'set-type' else {field}
    if not _equal({k: v for k, v in previous.items() if k not in allowed},
                  {k: v for k, v in desired.items() if k not in allowed}) or (
            before['native'].get('ddl') != after['native'].get('ddl')):
        raise ValueError('Review other native column edits separately')
    prefix = ('ALTER TABLE ' + '.'.join(_quote(part) for part in after['path'][:3]) +
              ' ALTER COLUMN ' + _quote(after['name']) + ' ')
    if field == 'default':
        value = desired.get('default')
        if value is None:
            source = prefix + 'DROP DEFAULT'
        elif isinstance(value, str) and value.strip() and len(value.encode('utf8')) <= 8192 and '\x00' not in value:
            source = prefix + 'SET DEFAULT ' + value.strip()
        else:
            raise ValueError('Column default requires one bounded native SQL expression')
    elif field == 'nullable':
        value = desired.get('nullable')
        if type(value) is not bool:
            raise ValueError('Column nullability requires an explicit Boolean')
        source = prefix + ('DROP NOT NULL' if value else 'SET NOT NULL')
    else:
        source = prefix + 'TYPE ' + _native_column_type(desired.get('data_type'))
        if 'using' in change:
            expression = change['using']
            if (not isinstance(expression, str) or not expression.strip() or
                    len(expression.encode('utf8')) > 8192 or '\x00' in expression or
                    any(marker in expression for marker in (';', '--', '/*', '*/'))):
                raise ValueError('USING requires one bounded native expression')
            source += ' USING ' + expression.strip()
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected the column alteration') from None
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.ALTER:
        raise ValueError('Exactly one native ALTER COLUMN statement is required')
    return source


def _validated_struct_field_add(before, after, change):
    if set(change) != {'action', 'field', 'data_type'}:
        raise ValueError('STRUCT field addition requires one exact field and type')
    field = change['field']
    if not isinstance(field, str) or not re.fullmatch(r'[a-z_][a-z0-9_]*', field):
        raise ValueError('STRUCT field addition requires a simple native field name')
    field_type = _native_column_type(change['data_type'])
    previous, desired = deepcopy(_definition(before)), deepcopy(_definition(after))
    old_type = _native_column_type(previous['catalog'].get('data_type'))
    new_type = _native_column_type(desired['catalog'].get('data_type'))
    if not re.fullmatch(r'STRUCT\(.+\)', old_type, re.I | re.S):
        raise ValueError('STRUCT field addition requires an observed native STRUCT column')
    if any(re.match(re.escape(field) + r'\s+', member)
           for member in _struct_members(old_type)):
        raise ValueError('STRUCT field addition cannot duplicate an observed field')
    expected = old_type[:-1] + ', ' + field + ' ' + field_type + ')'
    if new_type != expected:
        raise ValueError('STRUCT field addition must append exactly one native field')
    for key in _TYPE_FIELDS:
        previous['catalog'].pop(key, None)
        desired['catalog'].pop(key, None)
    if not _equal(previous, desired):
        raise ValueError('Review other native column edits separately')
    source = ('ALTER TABLE ' + '.'.join(_quote(part) for part in after['path'][:3]) +
              ' ADD COLUMN ' + _quote(after['name']) + '.' + _quote(field) + ' ' + field_type)
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected the STRUCT field addition') from None
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.ALTER:
        raise ValueError('Exactly one native STRUCT field addition is required')
    return source


def _struct_members(data_type):
    if not re.fullmatch(r'STRUCT\(.+\)', data_type, re.I | re.S):
        raise ValueError('STRUCT field removal requires an observed native STRUCT column')
    body = data_type[data_type.index('(') + 1:-1]
    members, start, depth, quote = [], 0, 0, None
    index = 0
    while index < len(body):
        char = body[index]
        if quote is not None:
            if char == quote:
                if index + 1 < len(body) and body[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif char in {'"', "'"}:
            quote = char
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth < 0:
                raise ValueError('Native STRUCT definition is malformed')
        elif char == ',' and depth == 0:
            members.append(body[start:index].strip())
            start = index + 1
        index += 1
    members.append(body[start:].strip())
    if quote is not None or depth != 0 or any(not member for member in members):
        raise ValueError('Native STRUCT definition is malformed')
    return members


def _validated_struct_field_drop(before, after, change):
    field = change.get('field') if isinstance(change, dict) else None
    if (set(change) != {'action', 'field'} or not isinstance(field, str) or
            not re.fullmatch(r'[a-z_][a-z0-9_]*', field)):
        raise ValueError('STRUCT field removal requires one exact simple field name')
    previous, desired = deepcopy(_definition(before)), deepcopy(_definition(after))
    old_type = _native_column_type(previous['catalog'].get('data_type'))
    new_type = _native_column_type(desired['catalog'].get('data_type'))
    members = _struct_members(old_type)
    kept = [member for member in members
            if not re.match(re.escape(field) + r'\s+', member)]
    if len(members) - len(kept) != 1 or not kept or new_type != 'STRUCT(' + ', '.join(kept) + ')':
        raise ValueError('STRUCT field removal must drop exactly one observed field')
    for key in _TYPE_FIELDS:
        previous['catalog'].pop(key, None)
        desired['catalog'].pop(key, None)
    if not _equal(previous, desired):
        raise ValueError('Review other native column edits separately')
    source = ('ALTER TABLE ' + '.'.join(_quote(part) for part in after['path'][:3]) +
              ' DROP COLUMN ' + _quote(after['name']) + '.' + _quote(field) + ' RESTRICT')
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected the STRUCT field removal') from None
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.ALTER:
        raise ValueError('Exactly one native STRUCT field removal is required')
    return source


def _nested_struct_result(data_type, path, *, add_type=None):
    members = _struct_members(data_type)
    selected = [index for index, member in enumerate(members)
                if re.match(re.escape(path[0]) + r'\s+', member)]
    if len(path) == 1:
        if add_type is not None:
            if selected:
                raise ValueError('Nested STRUCT field already exists')
            members.append(path[0] + ' ' + add_type)
        else:
            if len(selected) != 1 or len(members) == 1:
                raise ValueError('Nested STRUCT removal requires one field and a nonempty parent')
            members.pop(selected[0])
    else:
        if len(selected) != 1:
            raise ValueError('Nested STRUCT path must name one observed parent field')
        match = re.fullmatch(re.escape(path[0]) + r'\s+(.+)', members[selected[0]], re.S)
        members[selected[0]] = (path[0] + ' ' +
            _nested_struct_result(match.group(1), path[1:], add_type=add_type))
    return 'STRUCT(' + ', '.join(members) + ')'


def _validated_nested_struct_change(before, after, change):
    action = change.get('action')
    add = action == 'add-nested-field'
    expected_keys = {'action', 'field_path', 'data_type'} if add else {'action', 'field_path'}
    path = change.get('field_path')
    if (action not in {'add-nested-field', 'drop-nested-field'} or
            set(change) != expected_keys or not isinstance(path, list) or
            not 2 <= len(path) <= 8 or
            any(not isinstance(part, str) or
                not re.fullmatch(r'[a-z_][a-z0-9_]*', part) for part in path)):
        raise ValueError('Nested STRUCT edit requires one exact simple-identifier path')
    field_type = _native_column_type(change['data_type']) if add else None
    previous, desired = deepcopy(_definition(before)), deepcopy(_definition(after))
    old_type = _native_column_type(previous['catalog'].get('data_type'))
    new_type = _native_column_type(desired['catalog'].get('data_type'))
    if new_type != _nested_struct_result(old_type, path, add_type=field_type):
        raise ValueError('Nested STRUCT edit must change exactly one terminal field')
    for key in _TYPE_FIELDS:
        previous['catalog'].pop(key, None)
        desired['catalog'].pop(key, None)
    if not _equal(previous, desired):
        raise ValueError('Review other native column edits separately')
    source = ('ALTER TABLE ' + '.'.join(_quote(part) for part in after['path'][:3]) +
              (' ADD COLUMN ' if add else ' DROP COLUMN ') +
              '.'.join(_quote(part) for part in [after['name'], *path]) +
              (' ' + field_type if add else ' RESTRICT'))
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected the nested STRUCT edit') from None
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.ALTER:
        raise ValueError('Exactly one native nested STRUCT edit is required')
    return source


def _validated_enum_extension(before, after, target):
    previous = deepcopy(_definition(before))
    desired = deepcopy(_definition(after))
    if (previous['catalog'].get('comment') is not None or previous['catalog'].get('tags') or
            desired['catalog'].get('comment') is not None or desired['catalog'].get('tags')):
        raise ValueError('Enum replacement would discard native comment or tags')
    old_labels = previous['catalog'].pop('labels', None)
    new_labels = desired['catalog'].pop('labels', None)
    if (previous['catalog'].get('logical_type') != 'ENUM' or
            not _equal(previous, desired)):
        raise ValueError('Enum extension may change only native labels')
    if (not isinstance(old_labels, list) or not old_labels or
            not isinstance(new_labels, list) or len(new_labels) <= len(old_labels) or
            len(new_labels) > 1000 or new_labels[:len(old_labels)] != old_labels or
            any(not isinstance(label, str) or not label or '\x00' in label or
                len(label.encode('utf8')) > 256 for label in new_labels) or
            len(set(new_labels)) != len(new_labels)):
        raise ValueError('Enum extension requires distinct appended native labels')
    source = ('CREATE OR REPLACE TYPE ' + target + ' AS ENUM (' +
              ', '.join("'" + label.replace("'", "''") + "'" for label in new_labels) + ')')
    if len(source.encode('utf8')) > 64 * 1024:
        raise ValueError('Enum extension exceeds the native statement budget')
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected the enum extension') from None
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.CREATE:
        raise ValueError('Exactly one native enum replacement is required')
    return source, new_labels


def _validated_view_replacement(before, after):
    for row in (before, after):
        metadata = row['native'].get('catalog_metadata', {})
        if metadata.get('comment') is not None or metadata.get('tags'):
            raise ValueError('View replacement would discard native comment or tags')
    return _validated_ddl(after['native'].get('ddl'), 'view', after['path'], replace=True)


def view_query_tokens(source):
    """Compare submitted view aliases/body with the catalog's normalized SQL.

    Native CREATE VIEW text may rewrite the target and remove OR REPLACE.
    Token comparison is deliberately strict: an equivalent rewrite that does
    not match remains committed but unverified.
    """
    if not isinstance(source, str):
        return None
    import duckdb
    try:
        positions = duckdb.tokenize(source)
    except duckdb.Error:
        return None
    encoded = source.encode('utf8')
    tokens = []
    for index, (offset, kind) in enumerate(positions):
        following = positions[index + 1][0] if index + 1 < len(positions) else len(encoded)
        word = encoded[offset:following].decode('utf8').strip()
        if kind in {duckdb.token_type.keyword, duckdb.token_type.identifier}:
            word = word.casefold()
        tokens.append((str(kind), word))
    view_index = None
    for index, (kind, word) in enumerate(tokens):
        if kind == str(duckdb.token_type.keyword) and word == 'view':
            view_index = index
        elif view_index is not None and kind == str(duckdb.token_type.keyword) and word == 'as':
            header = tokens[view_index + 1:index]
            alias_start = next((offset for offset, token in enumerate(header)
                if token == (str(duckdb.token_type.operator), '(')), None)
            aliases = tuple(header[alias_start:]) if alias_start is not None else ()
            body = tokens[index + 1:]
            if body and body[-1] == (str(duckdb.token_type.operator), ';'):
                body = body[:-1]
            return (aliases, tuple(body)) if body else None
    return None


def create_definition_tokens(source, kind):
    """Strictly compare the native body of a created table or index.

    DuckDB rewrites the qualified target in its catalog SQL. If the submitted
    form cannot be compared, the committed creation must remain unverified.
    """
    if kind not in {'table', 'index'} or not isinstance(source, str):
        return None
    import duckdb
    try:
        positions = duckdb.tokenize(source)
    except duckdb.Error:
        return None
    encoded = source.encode('utf8')
    tokens = []
    for index, (offset, token_kind) in enumerate(positions):
        following = positions[index + 1][0] if index + 1 < len(positions) else len(encoded)
        word = encoded[offset:following].decode('utf8').strip()
        if (token_kind == duckdb.token_type.identifier and
                len(word) >= 2 and word[0] == word[-1] == '"'):
            word = word[1:-1].replace('""', '"')
        if token_kind in {duckdb.token_type.keyword, duckdb.token_type.identifier}:
            word = word.casefold()
        tokens.append((str(token_kind), word))
    if not tokens or tokens[0] != (str(duckdb.token_type.keyword), 'create'):
        return None
    kind_index = next((index for index, token in enumerate(tokens)
        if token == (str(duckdb.token_type.keyword), kind)), None)
    if kind_index is None:
        return None
    unique = ((str(duckdb.token_type.keyword), 'unique') in tokens[:kind_index])
    on_seen = False
    for index in range(kind_index + 1, len(tokens)):
        token = tokens[index]
        if token == (str(duckdb.token_type.keyword), 'as') and kind == 'table':
            return None
        if token == (str(duckdb.token_type.keyword), 'on'):
            on_seen = True
        if token == (str(duckdb.token_type.operator), '('):
            if kind == 'index' and not on_seen:
                return None
            body = tokens[index:]
            if body and body[-1] == (str(duckdb.token_type.operator), ';'):
                body = body[:-1]
            return (unique, tuple(body)) if kind == 'index' else tuple(body)
    return None


def _table_definition_sections(source):
    body = create_definition_tokens(source, 'table')
    if not body or body[0] != ('token_type.operator', '(') or body[-1] != ('token_type.operator', ')'):
        return None
    sections, start, depth = [], 1, 1
    for index, token in enumerate(body[1:-1], 1):
        depth += (token == ('token_type.operator', '(')) - (token == ('token_type.operator', ')'))
        if depth < 1:
            return None
        if depth == 1 and token == ('token_type.operator', ','):
            sections.append(body[start:index])
            start = index + 1
    if depth != 1:
        return None
    sections.append(body[start:-1])
    columns, checks = [], []
    for section in sections:
        if not section:
            return None
        if section[0] in {('token_type.keyword', 'check'),
                          ('token_type.keyword', 'constraint')}:
            if ('token_type.keyword', 'check') not in section:
                return None
            checks.append(section)
        else:
            columns.append(section)
    return tuple(columns), tuple(checks)


def type_expression_tokens(source, *, created):
    """Compare CREATE TYPE's expression with the native resolved expression."""
    if not isinstance(source, str) or not source:
        return None
    import duckdb
    try:
        positions = duckdb.tokenize(source)
    except duckdb.Error:
        return None
    encoded = source.encode('utf8')
    tokens = []
    for index, (offset, token_kind) in enumerate(positions):
        following = positions[index + 1][0] if index + 1 < len(positions) else len(encoded)
        word = encoded[offset:following].decode('utf8').strip()
        if (token_kind == duckdb.token_type.identifier and
                len(word) >= 2 and word[0] == word[-1] == '"'):
            word = word[1:-1].replace('""', '"')
        if token_kind in {duckdb.token_type.keyword, duckdb.token_type.identifier}:
            word = word.casefold()
        tokens.append((str(token_kind), word))
    if created:
        if len(tokens) < 5 or tokens[:2] != [
                (str(duckdb.token_type.keyword), 'create'),
                (str(duckdb.token_type.keyword), 'type')]:
            return None
        marker = next((index for index, token in enumerate(tokens[2:], 2)
            if token == (str(duckdb.token_type.keyword), 'as')), None)
        if marker is None:
            return None
        tokens = tokens[marker + 1:]
    if tokens and tokens[-1] == (str(duckdb.token_type.operator), ';'):
        tokens = tokens[:-1]
    return tuple(tokens) if tokens else None


def sequence_creation_postcondition(source, path):
    """Derive the effective options of one canonical DuckDB 1.5.2 CREATE."""
    if not isinstance(source, str):
        return None
    target = '.'.join(_quote(part) for part in path)
    prefix = re.match(r'^\s*CREATE\s+SEQUENCE\s+' + re.escape(target) +
        r'(?=\s|;|$)', source, re.I)
    if prefix is None:
        return None
    remainder = source[prefix.end():].strip()
    if remainder.endswith(';'):
        remainder = remainder[:-1].strip()
    patterns = (
        ('increment_by', r'INCREMENT(?:\s+BY)?\s+([+-]?\d+)(?=\s|$)'),
        ('min_value', r'MINVALUE\s+([+-]?\d+)(?=\s|$)'),
        ('min_value', r'NO\s+MINVALUE(?=\s|$)'),
        ('max_value', r'MAXVALUE\s+([+-]?\d+)(?=\s|$)'),
        ('max_value', r'NO\s+MAXVALUE(?=\s|$)'),
        ('start_value', r'START(?:\s+WITH)?\s+([+-]?\d+)(?=\s|$)'),
        ('cycle', r'CYCLE(?=\s|$)'),
        ('cycle', r'NO\s+CYCLE(?=\s|$)'),
    )
    precedence = {'increment_by': 0, 'min_value': 1, 'max_value': 2,
        'start_value': 3, 'cycle': 4}
    explicit = {}
    last = -1
    while remainder:
        match = next(((key, re.match(pattern, remainder, re.I))
            for key, pattern in patterns if re.match(pattern, remainder, re.I)), None)
        if match is None:
            return None
        key, found = match
        if key in explicit or precedence[key] <= last:
            return None
        if found.lastindex:
            explicit[key] = int(found.group(1))
        elif key == 'cycle':
            explicit[key] = remainder[:found.end()].upper() == 'CYCLE'
        else:
            explicit[key] = None
        last = precedence[key]
        remainder = remainder[found.end():].strip()
    increment = explicit.get('increment_by', 1)
    if increment == 0:
        return None
    ascending = increment > 0
    minimum = explicit.get('min_value')
    maximum = explicit.get('max_value')
    minimum = (1 if ascending else -(2 ** 63)) if minimum is None else minimum
    maximum = ((2 ** 63) - 1 if ascending else -1) if maximum is None else maximum
    start = explicit.get('start_value')
    return {'start_value': (minimum if ascending else maximum) if start is None else start,
        'min_value': minimum, 'max_value': maximum,
        'increment_by': increment, 'cycle': explicit.get('cycle', False)}


def _macro_tokens(source):
    if not isinstance(source, str):
        return None
    import duckdb
    try:
        positions = duckdb.tokenize(source)
    except duckdb.Error:
        return None
    encoded = source.encode('utf8')
    tokens = []
    for index, (offset, kind) in enumerate(positions):
        following = positions[index + 1][0] if index + 1 < len(positions) else len(encoded)
        word = encoded[offset:following].decode('utf8').strip()
        if kind == duckdb.token_type.identifier and len(word) >= 2 and word[0] == word[-1] == '"':
            word = word[1:-1].replace('""', '"')
        if kind in {duckdb.token_type.keyword, duckdb.token_type.identifier}:
            word = word.casefold()
        tokens.append((str(kind), word))
    if tokens and tokens[-1] == (str(duckdb.token_type.operator), ';'):
        tokens.pop()
    return tokens


def _macro_body_tokens(tokens, *, table=False):
    import duckdb
    opening = (str(duckdb.token_type.operator), '(')
    closing = (str(duckdb.token_type.operator), ')')
    keyword = str(duckdb.token_type.keyword)
    identifier = str(duckdb.token_type.identifier)
    tokens = list(tokens)
    if table:
        depth = 0
        for index, token in enumerate(tokens):
            if (index and depth == 0 and tokens[index - 1] == (keyword, 'as') and
                    token[0] in {keyword, identifier}):
                tokens[index] = (identifier, token[1])
            depth += (token == opening) - (token == closing)
    while len(tokens) >= 2 and tokens[0] == opening and tokens[-1] == closing:
        depth = 0
        wrapped = True
        for index, token in enumerate(tokens):
            depth += (token == opening) - (token == closing)
            if depth == 0 and index < len(tokens) - 1:
                wrapped = False
                break
        if not wrapped or depth != 0:
            break
        tokens = tokens[1:-1]
    return tuple(tokens) if tokens else None


def macro_creation_matches(source, current):
    """Verify only a complete observed single-overload native macro."""
    if current['kind'] != 'macro':
        return False
    target = '.'.join(_quote(part) for part in current['path'])
    prefix = re.match(r'^\s*CREATE\s+MACRO\s+' + re.escape(target) +
        r'(?=\s|\()', source, re.I) if isinstance(source, str) else None
    if prefix is None:
        return False
    tokens = _macro_tokens(source[prefix.end():])
    observed = current['native'].get('overloads')
    if not isinstance(tokens, list) or not isinstance(observed, list) or len(observed) != 1:
        return False
    import duckdb
    opening = (str(duckdb.token_type.operator), '(')
    closing = (str(duckdb.token_type.operator), ')')
    comma = (str(duckdb.token_type.operator), ',')
    keyword = str(duckdb.token_type.keyword)
    identifier = str(duckdb.token_type.identifier)
    if not tokens or tokens[0] != opening:
        return False
    close = next((index for index, token in enumerate(tokens[1:], 1)
        if token == closing), None)
    if close is None or len(tokens) <= close + 2 or tokens[close + 1] != (keyword, 'as'):
        return False
    parameter_tokens = tokens[1:close]
    parameters = []
    if parameter_tokens:
        for part in (list(group) for group in _split_macro_parameters(parameter_tokens, comma)):
            if len(part) != 1 or part[0][0] != identifier:
                return False
            parameters.append(part[0][1])
    body = tokens[close + 2:]
    is_table = bool(body and body[0] == (keyword, 'table'))
    if is_table:
        body = body[1:]
    expected_body = _macro_body_tokens(body, table=is_table)
    overload = observed[0]
    native_parameters = overload.get('parameters')
    if (expected_body is None or current['native'].get('overload_count') != 1 or
            overload.get('catalog_metadata', {}).get('function_type') !=
                ('table_macro' if is_table else 'macro') or
            not isinstance(native_parameters, list) or len(native_parameters) != len(parameters) or
            any(not isinstance(item, dict) or item.get('data_type') is not None or
                not isinstance(item.get('name'), str) or
                item['name'].casefold() != expected
                for item, expected in zip(native_parameters, parameters))):
        return False
    observed_tokens = _macro_tokens(overload.get('definition'))
    return (isinstance(observed_tokens, list) and expected_body ==
        _macro_body_tokens(observed_tokens, table=is_table))


def _split_macro_parameters(tokens, comma):
    start = 0
    for index, token in enumerate(tokens):
        if token == comma:
            yield tokens[start:index]
            start = index + 1
    yield tokens[start:]


def _validated_macro_replacement(before, after, target, change):
    if change != {'action': 'replace-definition',
                   'parameters_without_defaults_confirmed': True}:
        raise ValueError('Macro replacement requires explicit confirmation that the original signature has no parameter defaults')
    previous = deepcopy(_definition(before))
    desired = deepcopy(_definition(after))
    if previous['catalog'].get('comment') is not None or previous['catalog'].get('tags'):
        raise ValueError('Macro replacement would discard existing native comment or tags')
    old_overloads, new_overloads = previous['overloads'], desired['overloads']
    if (not isinstance(old_overloads, list) or len(old_overloads) != 1 or
            not isinstance(new_overloads, list) or len(new_overloads) != 1 or
            previous['overload_count'] != 1 or desired['overload_count'] != 1):
        raise ValueError('Only one native macro overload can be replaced')
    old_definition = old_overloads[0].pop('definition', None)
    new_definition = new_overloads[0].pop('definition', None)
    macro_kind = old_overloads[0].get('catalog_metadata', {}).get('function_type')
    if (macro_kind not in {'macro', 'table_macro'} or
            new_overloads[0].get('catalog_metadata', {}).get('function_type') != macro_kind or
            old_overloads[0].get('catalog_metadata', {}).get('varargs') or
            not isinstance(new_definition, str) or not new_definition.strip() or
            new_definition == old_definition or
            len(new_definition.encode('utf8')) > 8192 or '\x00' in new_definition or
            any(marker in new_definition for marker in (';', '--', '/*', '*/'))):
        raise ValueError('Macro replacement requires one changed bounded definition of the same native kind')
    if (previous['definition'] != old_definition or
            desired['definition'] != new_definition):
        raise ValueError('Macro group and overload definitions must agree')
    previous['definition'] = desired['definition'] = None
    if not _equal(previous, desired):
        raise ValueError('Macro replacement may change only its native definition')
    parameters = after['native'].get('parameters')
    if (not isinstance(parameters, list) or len(parameters) > 64 or
            any(not isinstance(parameter, dict) or
                not isinstance(parameter.get('name'), str) or
                parameter.get('data_type') is not None
                for parameter in parameters)):
        raise ValueError('Macro replacement requires unchanged native parameters')
    source = ('CREATE OR REPLACE MACRO ' + target + '(' +
              ', '.join(_quote(parameter['name']) for parameter in parameters) +
              ') AS ' + ('TABLE ' if macro_kind == 'table_macro' else '') +
              new_definition.strip())
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected the macro replacement') from None
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.CREATE:
        raise ValueError('Exactly one native macro replacement is required')
    return source, new_definition


def _macro_overload_postcondition(row):
    native = row['native']
    overloads = native.get('overloads')
    if (not isinstance(overloads, list) or not 1 <= len(overloads) <= 32 or
            native.get('overload_count') != len(overloads)):
        raise ValueError('Macro replacement requires a complete bounded overload group')
    kinds = set()
    result = []
    for overload in overloads:
        metadata = overload.get('catalog_metadata')
        parameters = overload.get('parameters')
        definition = overload.get('definition')
        if (not isinstance(metadata, dict) or
                metadata.get('function_type') not in {'macro', 'table_macro'} or
                metadata.get('internal') is not False or metadata.get('varargs') is not None or
                metadata.get('comment') is not None or metadata.get('tags') or
                not isinstance(parameters, list) or len(parameters) > 64 or
                not isinstance(definition, str) or not definition.strip() or
                len(definition.encode('utf8')) > 8192 or '\x00' in definition):
            raise ValueError('Macro overload has unsupported native metadata or definition')
        names = []
        for parameter in parameters:
            if (not isinstance(parameter, dict) or set(parameter) != {'name', 'data_type'} or
                    not isinstance(parameter['name'], str) or not parameter['name'] or
                    '\x00' in parameter['name'] or len(parameter['name'].encode('utf8')) > 256 or
                    (parameter['data_type'] is not None and
                     (not isinstance(parameter['data_type'], str) or
                      not parameter['data_type'].strip() or
                      len(parameter['data_type'].encode('utf8')) > 1024))):
                raise ValueError('Macro overload has unsupported native parameters')
            names.append(parameter['name'])
        if len(set(names)) != len(names):
            raise ValueError('Macro overload parameters must be distinct')
        kinds.add(metadata['function_type'])
        result.append({'kind': metadata['function_type'],
                       'parameters': deepcopy(parameters), 'definition': definition})
    if len(kinds) != 1:
        raise ValueError('One macro group cannot mix scalar and table overloads')
    return sorted(result, key=digest)


def _validated_macro_group_replacement(before, after, change):
    if (set(change) != {'action', 'source', 'complete_signature_set_confirmed'} or
            change.get('complete_signature_set_confirmed') is not True):
        raise ValueError('Whole macro replacement requires explicit complete-signature confirmation')
    if (before['native'].get('catalog_metadata', {}).get('comment') is not None or
            after['native'].get('catalog_metadata', {}).get('comment') is not None):
        raise ValueError('Whole macro replacement would discard an existing native comment')
    previous = _macro_overload_postcondition(before)
    desired = _macro_overload_postcondition(after)
    if previous == desired:
        raise ValueError('Whole macro replacement needs an observable desired overload change')
    source = _validated_ddl(change.get('source'), 'macro', after['path'], replace=True)
    return source, desired


def _validated_sequence_replacement(before, after, change):
    if change != {'action': 'replace-sequence', 'reset_state_confirmed': True}:
        raise ValueError('Sequence replacement requires explicit generator reset confirmation')
    previous, desired = deepcopy(_definition(before)), deepcopy(_definition(after))
    if (previous['catalog'].get('automatic_dependency_observed') or
            desired['catalog'].get('automatic_dependency_observed')):
        raise ValueError('Sequence replacement is blocked by an observed automatic dependency')
    if (previous['catalog'].get('comment') is not None or previous['catalog'].get('tags') or
            desired['catalog'].get('comment') is not None or desired['catalog'].get('tags')):
        raise ValueError('Sequence replacement would discard native comment or tags')
    old_options = {key: previous['catalog'].pop(key, None) for key in _SEQUENCE_OPTIONS}
    new_options = {key: desired['catalog'].pop(key, None) for key in _SEQUENCE_OPTIONS}
    if (old_options == new_options or
            any(type(new_options[key]) is not int for key in _SEQUENCE_OPTIONS[:-1]) or
            type(new_options['cycle']) is not bool or
            not _equal(previous, {**desired, 'ddl': previous['ddl']})):
        raise ValueError('Sequence replacement may change only its complete native generator options')
    source = _validated_ddl(after['native'].get('ddl'), 'sequence', after['path'], replace=True)
    return source, new_options


def _validated_type_replacement(before, after, change):
    if change != {'action': 'replace-type', 'complete_definition_confirmed': True}:
        raise ValueError('Type replacement requires explicit whole-definition confirmation')
    previous, desired = deepcopy(_definition(before)), deepcopy(_definition(after))
    if (previous['catalog'].get('comment') is not None or previous['catalog'].get('tags') or
            desired['catalog'].get('comment') is not None or desired['catalog'].get('tags')):
        raise ValueError('Type replacement would discard native comment or tags')
    old_fields = {key: previous['catalog'].pop(key, None) for key in _TYPE_CATALOG_FIELDS}
    new_fields = {key: desired['catalog'].pop(key, None) for key in _TYPE_CATALOG_FIELDS}
    resolved = new_fields['resolved_type']
    if (old_fields == new_fields or
            not isinstance(old_fields['resolved_type'], str) or
            not isinstance(resolved, str) or not resolved.strip() or
            len(resolved.encode('utf8')) > 8192 or '\x00' in resolved or
            type(new_fields['size_bytes']) is not int or new_fields['size_bytes'] < 0 or
            not isinstance(new_fields['logical_type'], str) or
            (new_fields['category'] is not None and
             not isinstance(new_fields['category'], str)) or
            (new_fields['labels'] is not None and
             (not isinstance(new_fields['labels'], list) or
              any(not isinstance(label, str) for label in new_fields['labels']))) or
            not _equal(previous, {**desired, 'ddl': previous['ddl']})):
        raise ValueError('Type replacement requires one complete observed native type definition')
    source = _validated_ddl(after['native'].get('ddl'), 'type', after['path'], replace=True)
    return source, new_fields


def _validated_rename(before, after, change, catalog):
    if after['kind'] not in {'table', 'view', 'column'} or before['kind'] != after['kind']:
        raise ValueError('Native rename is admitted only for tables, views and columns')
    if change != {'action': 'rename', 'from_resource_id': before['resource_id'],
                  'confirmation': before['name']}:
        raise ValueError('Rename requires the exact baseline source and name confirmation')
    if before['path'][:-1] != after['path'][:-1] or before['name'] == after['name']:
        raise ValueError('Native rename must retain its parent and change its name')
    if not _equal(_definition(before), _definition(after)):
        raise ValueError('Review native definition edits separately from rename')
    source_target = _address(before, catalog)
    if after['kind'] == 'column':
        statement = ('ALTER TABLE ' + '.'.join(_quote(part) for part in before['path'][:3]) +
                     ' RENAME COLUMN ' + _quote(before['name']) + ' TO ' + _quote(after['name']))
    else:
        statement = ('ALTER ' + _KINDS[after['kind']] + ' ' + source_target +
                     ' RENAME TO ' + _quote(after['name']))
    import duckdb
    try:
        parsed = duckdb.extract_statements(statement)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected the rename') from None
    if len(parsed) != 1 or parsed[0].type != duckdb.StatementType.ALTER:
        raise ValueError('Exactly one native rename statement is required')
    return statement


def _validated_comment(before, after, target):
    if after['kind'] not in {'table', 'view', 'column', 'sequence', 'type', 'macro', 'index'}:
        raise ValueError('Native comments are unavailable for this object kind')
    previous, desired = deepcopy(_definition(before)), deepcopy(_definition(after))
    old_comment = previous['catalog'].pop('comment', None)
    new_comment = desired['catalog'].pop('comment', None)
    if old_comment == new_comment or not _equal(previous, desired):
        raise ValueError('Review the one native comment edit separately')
    if new_comment is not None and (not isinstance(new_comment, str) or
            len(new_comment.encode('utf8')) > 8192 or '\x00' in new_comment):
        raise ValueError('Native comment must be bounded text or NULL')
    if after['kind'] == 'index':
        target = '.'.join(_quote(part) for part in
            [after['path'][0], after['path'][1], after['name']])
    literal = 'NULL' if new_comment is None else "'" + new_comment.replace("'", "''") + "'"
    source = 'COMMENT ON ' + _KINDS[after['kind']] + ' ' + target + ' IS ' + literal
    import duckdb
    try:
        parsed = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected the comment') from None
    if len(parsed) != 1 or parsed[0].type != duckdb.StatementType.ALTER:
        raise ValueError('Exactly one native COMMENT ON statement is required')
    return source, new_comment


def _validated_primary_key(before, after, change, target):
    if after['kind'] != 'table' or before['native'].get('catalog_metadata', {}).get('has_primary_key') is not False:
        raise ValueError('Primary-key addition requires an observed table without a key')
    if not _equal(_definition(before), _definition(after)) or set(change) != {'action', 'columns'}:
        raise ValueError('Review native table edits separately from key addition')
    columns = change['columns']
    observed = {item.get('name') for item in before['native'].get('columns', [])
                if isinstance(item, dict)}
    if (not isinstance(columns, list) or not 1 <= len(columns) <= 16 or
            any(not isinstance(name, str) or name not in observed for name in columns) or
            len(set(columns)) != len(columns)):
        raise ValueError('Primary key requires distinct observed native columns')
    source = ('ALTER TABLE ' + target + ' ADD PRIMARY KEY (' +
              ', '.join(_quote(name) for name in columns) + ')')
    import duckdb
    try:
        parsed = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected primary-key addition') from None
    if len(parsed) != 1 or parsed[0].type != duckdb.StatementType.ALTER:
        raise ValueError('Exactly one native ADD PRIMARY KEY statement is required')
    return source, columns


def _validated_check_rebuild(before, after, change, target, live, desired):
    if change != {'action': 'rebuild-check-constraints',
                  'complete_definition_confirmed': True,
                  'preserve_rows_confirmed': True}:
        raise ValueError('CHECK rebuild needs complete-definition and row-preservation confirmation')
    old, new = deepcopy(_definition(before)), deepcopy(_definition(after))
    old_constraints, new_constraints = old.pop('constraints'), new.pop('constraints')
    old.pop('ddl'); new.pop('ddl')
    if (not _equal(old, new) or _equal(old_constraints, new_constraints) or
            not isinstance(old_constraints, list) or not isinstance(new_constraints, list) or
            any(item.get('constraint_type') != 'CHECK' for item in
                [*old_constraints, *new_constraints])):
        raise ValueError('CHECK rebuild may change only complete native CHECK constraints')
    metadata = before['native'].get('catalog_metadata', {})
    columns = before['native'].get('columns')
    if (metadata.get('has_primary_key') is not False or metadata.get('comment') is not None or
            metadata.get('tags') or before['native'].get('indexes') or
            not isinstance(columns, list) or not 1 <= len(columns) <= 128 or
            any(not isinstance(item, dict) or not isinstance(item.get('name'), str) or
                item.get('comment') is not None or item.get('default') is not None
                for item in columns) or
            len({item['name'] for item in columns}) != len(columns)):
        raise ValueError('CHECK rebuild requires plain unchanged columns without indexes or comments')
    for row in live['rows'].values():
        if row['kind'] in {'view', 'macro', 'sequence', 'attached-database'}:
            raise ValueError('CHECK rebuild is blocked by a native dependent object category')
        if row['kind'] == 'table' and any(item.get('constraint_type') in
                ({'FOREIGN KEY', 'PRIMARY KEY', 'UNIQUE'} if
                 row['resource_id'] == before['resource_id'] else {'FOREIGN KEY'}) for item in
                row['native'].get('constraints', [])):
            raise ValueError('CHECK rebuild is blocked by native key dependencies')
    source = _validated_ddl(after['native'].get('ddl'), 'table', after['path'])
    body = create_definition_tokens(source, 'table')
    original_sections = _table_definition_sections(before['native'].get('ddl'))
    desired_sections = _table_definition_sections(source)
    if (body is None or original_sections is None or desired_sections is None or
            not original_sections[0] or original_sections[0] != desired_sections[0] or
            len(original_sections[1]) != len(old_constraints) or
            len(desired_sections[1]) != len(new_constraints) or any(
            kind == 'token_type.keyword' and word in
                {'primary', 'unique', 'foreign', 'references', 'default'}
            for kind, word in body)):
        raise ValueError('CHECK rebuild requires a complete plain CREATE TABLE body')
    stage_name = '__scratchrobin_rebuild_' + digest(source)[:16]
    stage_path = [*after['path'][:2], stage_name]
    stage_id = _resource_id('table', stage_path[:2], stage_name)
    if stage_id in live['rows'] or stage_id in desired['rows']:
        raise ValueError('CHECK rebuild staging identity already exists')
    stage = '.'.join(_quote(part) for part in stage_path)
    source_prefix = re.match(r'^\s*CREATE\s+TABLE\s+' + re.escape(target), source, re.I)
    creation = 'CREATE TABLE ' + stage + source[source_prefix.end():]
    _validated_ddl(creation, 'table', stage_path)
    names = ', '.join(_quote(item['name']) for item in columns)
    statements = [creation,
        'INSERT INTO ' + stage + ' (' + names + ') SELECT ' + names + ' FROM ' + target,
        'DROP TABLE ' + target + ' RESTRICT',
        'ALTER TABLE ' + stage + ' RENAME TO ' + _quote(after['name'])]
    check = ('SELECT count(*) FROM ((SELECT ' + names + ' FROM ' + target +
        ' EXCEPT ALL SELECT ' + names + ' FROM ' + stage + ') UNION ALL (SELECT ' +
        names + ' FROM ' + stage + ' EXCEPT ALL SELECT ' + names + ' FROM ' +
        target + ')) AS differences')
    import duckdb
    for statement, expected in zip(statements,
            (duckdb.StatementType.CREATE, duckdb.StatementType.INSERT,
             duckdb.StatementType.DROP, duckdb.StatementType.ALTER)):
        try:
            parsed = duckdb.extract_statements(statement)
        except duckdb.Error:
            raise ValueError('Native CHECK rebuild statement is not parseable') from None
        if len(parsed) != 1 or parsed[0].type != expected:
            raise ValueError('Native CHECK rebuild requires four exact statements')
    return statements, check, source, new_constraints


def _ordered_operations(operations, desired):
    if (sum(len(item.get('statements', [item['source']])) for item in operations) > 32 or
            sum(len(item['source'].encode('utf8')) for item in operations) > 1024 * 1024):
        raise ValueError('Native batch exceeds 32 statements or 1 MiB')
    if len(operations) > 1 and any(item['operation'] == 'rename' for item in operations):
        raise ValueError('Rename requires a separate review and descendant refresh')
    if len(operations) > 1 and any(item['operation'] == 'rebuild' for item in operations):
        raise ValueError('CHECK table rebuild requires a separate review')
    by_id = {item['resource_id']: item for item in operations}
    for item in operations:
        row = desired['rows'][item['resource_id']]
        if item['kind'] in {'column', 'index'}:
            parent = _resource_id('table', row['path'][:2], row['path'][2])
            parent_op = by_id.get(parent)
            if parent_op and parent_op['operation'] == 'drop' and item['operation'] != 'drop':
                raise ValueError('Cannot change a child while dropping its parent table')
            if parent_op and parent_op['operation'] == 'create' and item['kind'] == 'column':
                raise ValueError('New table columns belong in its CREATE TABLE statement')
        elif item['kind'] not in {'schema'} and len(row['path']) >= 3:
            parent = _resource_id('schema', row['path'][:1], row['path'][1])
            parent_op = by_id.get(parent)
            if parent_op and parent_op['operation'] == 'drop' and item['operation'] != 'drop':
                raise ValueError('Cannot create or change an object while dropping its schema')

    def order(item):
        operation, kind = item['operation'], item['kind']
        if operation == 'drop':
            priority = {'index': 0, 'column': 0, 'view': 55, 'macro': 55,
                        'table': 60, 'sequence': 65, 'type': 65,
                        'schema': 70}.get(kind, 60)
        elif operation == 'create':
            priority = {'schema': 10, 'sequence': 15, 'type': 15,
                        'macro': 15, 'table': 20, 'view': 25,
                        'column': 30, 'index': 40}.get(kind, 25)
        else:
            priority = 35 if kind == 'column' else 50
        return (priority, item['target'], item['resource_id'])
    return sorted(operations, key=order)


def plan(baseline, desired, live):
    catalog = _root(live)
    for model in (baseline, desired):
        if (_root(model) != catalog or any(model['provenance'].get(field) != live['provenance'].get(field)
            for field in ('endpoint_id', 'database_target_id'))):
            raise ValueError('Design belongs to another endpoint or registered DuckDB file')
    operations, blockers, conflicts, ignored = [], [], [], []
    rebuild_tables = {identity for identity, row in desired['rows'].items()
        if row['kind'] == 'table' and isinstance(row['native'].get('duckdb_change'), dict)
        and row['native']['duckdb_change'].get('action') == 'rebuild-check-constraints'}
    for identity, after in sorted(desired['rows'].items()):
        before, current = baseline['rows'].get(identity), live['rows'].get(identity)
        if before is not None and (after.get('resource_id') != identity or
                any(not _equal(before.get(field), after.get(field)) for field in
                    ('kind', 'path', 'name', 'system'))):
            blockers.append({'resource_id': identity, 'name': after.get('name'),
                'reason': 'Existing native object identity changed under its resource ID'})
            continue
        if after['kind'] == 'constraint' and len(after.get('path', [])) == 4 and (
                _resource_id('table', after['path'][:2], after['path'][2]) in rebuild_tables):
            native_index = after['native'].get('catalog_metadata', {}).get('constraint_index')
            if (type(native_index) is not int or after['resource_id'] !=
                    _resource_id('constraint', after['path'][:-1], after['name'],
                        discriminator=native_index) or after['system'] != 'false' or
                    after['native'].get('system_object') is not False or
                    after['native'].get('duckdb_change') is not None):
                blockers.append({'resource_id': identity, 'name': after.get('name'),
                    'reason': 'CHECK rebuild child identity or intent is not native'})
            continue
        if before is not None and _equal(_definition(before), _definition(after)) and not after['native'].get('duckdb_change'):
            continue
        try:
            if before is None and current is not None:
                raise ValueError('New native target already exists')
            target = _address(after, catalog)
            if before is not None:
                _address(before, catalog)
                if current is None or current['kind'] != before['kind'] or not _equal(_definition(current), _definition(before)):
                    conflicts.append({'resource_id': identity, 'reason': 'Live native definition changed since baseline'})
                    continue
                if after['kind'] == 'column' and after['native'].get('duckdb_change') != {'action': 'set-comment'}:
                    _require_table_parent(after, live, catalog)
            change = after['native'].get('duckdb_change')
            if (before is None and isinstance(change, dict) and
                    change.get('action') == 'rename'):
                source_id = change.get('from_resource_id')
                if not isinstance(source_id, str):
                    raise ValueError('Rename requires a baseline source resource ID')
                source_before = baseline['rows'].get(source_id)
                source_current = live['rows'].get(source_id)
                if source_before is None or source_current is None:
                    raise ValueError('Rename source is absent from baseline or live catalog')
                _address(source_before, catalog)
                _address(source_current, catalog)
                if after['kind'] == 'column':
                    _require_table_parent(after, live, catalog)
                if (source_current['kind'] != source_before['kind'] or
                        not _equal(_definition(source_current), _definition(source_before))):
                    conflicts.append({'resource_id': identity,
                        'reason': 'Live rename source changed since baseline'})
                    continue
                operation = 'rename'
                source = _validated_rename(source_before, after, change, catalog)
                before = source_before
            elif before is None:
                if change is not None:
                    raise ValueError('Creation cannot carry replacement or deletion intent')
                if after['kind'] in {'index', 'column'}:
                    parent_path = after['path'][:3]
                    parent_id = _resource_id('table', parent_path[:2], parent_path[2])
                    parent = live['rows'].get(parent_id)
                    parent_new = desired['rows'].get(parent_id) if parent is None else None
                    if parent is None and (parent_new is None or parent_new['kind'] != 'table' or
                            parent_id in baseline['rows']):
                        raise ValueError('Child creation requires an observed native parent table')
                    _address(parent if parent is not None else parent_new, catalog)
                operation = 'create'
                source = (_validated_index_ddl(after['native'].get('ddl'), after['path'])
                          if after['kind'] == 'index' else
                          _validated_column_add(after) if after['kind'] == 'column' else
                          _validated_ddl(after['native'].get('ddl'), after['kind'], after['path']))
                if after['kind'] == 'sequence':
                    _sequence_creation_options = sequence_creation_postcondition(
                        source, after['path'])
                    if _sequence_creation_options is None:
                        raise ValueError('Sequence creation requires ordered numeric native options without ownership')
            elif change == {'action': 'drop', 'confirmation': before['name']}:
                retained = deepcopy(after)
                retained['native'].pop('duckdb_change')
                if not _equal(_definition(retained), _definition(before)):
                    raise ValueError('Review deletion separately from other native edits')
                operation = 'drop'
                drop_target = ('.'.join(_quote(part) for part in
                    [after['path'][0], after['path'][1], after['name']])
                    if after['kind'] == 'index' else target)
                source = ('ALTER TABLE ' + '.'.join(_quote(part) for part in
                    after['path'][:3]) + ' DROP COLUMN ' + _quote(after['name']) + ' RESTRICT'
                    if after['kind'] == 'column' else
                    'DROP ' + _KINDS[after['kind']] + ' ' + drop_target + ' RESTRICT')
                import duckdb
                try:
                    statements = duckdb.extract_statements(source)
                except duckdb.Error:
                    raise ValueError('Native DuckDB removal grammar is unavailable') from None
                expected_type = duckdb.StatementType.ALTER if after['kind'] == 'column' else duckdb.StatementType.DROP
                if len(statements) != 1 or statements[0].type != expected_type:
                    raise ValueError('Native removal grammar is unavailable')
            elif change == {'action': 'replace'} and after['kind'] == 'view':
                operation = 'replace'
                source = _validated_view_replacement(before, after)
            elif change == {'action': 'extend-enum'} and after['kind'] == 'type':
                operation = 'replace'
                source, _labels = _validated_enum_extension(before, after, target)
            elif (isinstance(change, dict) and change.get('action') == 'replace-definition' and
                  after['kind'] == 'macro'):
                operation = 'replace'
                source, _definition_text = _validated_macro_replacement(before, after, target, change)
            elif (isinstance(change, dict) and change.get('action') == 'replace-macro' and
                  after['kind'] == 'macro'):
                operation = 'replace'
                source, _macro_overloads = _validated_macro_group_replacement(
                    before, after, change)
            elif (isinstance(change, dict) and change.get('action') == 'replace-sequence' and
                  after['kind'] == 'sequence'):
                operation = 'replace'
                source, _sequence_options = _validated_sequence_replacement(before, after, change)
            elif (isinstance(change, dict) and change.get('action') == 'replace-type' and
                  after['kind'] == 'type'):
                operation = 'replace'
                source, _type_catalog = _validated_type_replacement(before, after, change)
            elif change == {'action': 'set-comment'}:
                operation = 'alter'
                source, _comment = _validated_comment(before, after, target)
            elif (after['kind'] == 'table' and isinstance(change, dict) and
                  change.get('action') == 'add-primary-key'):
                operation = 'alter'
                source, _pk_columns = _validated_primary_key(before, after, change, target)
            elif (after['kind'] == 'table' and isinstance(change, dict) and
                  change.get('action') == 'rebuild-check-constraints'):
                operation = 'rebuild'
                _rebuild_statements, _data_check, _original_source, _expected_constraints = (
                    _validated_check_rebuild(before, after, change, target, live, desired))
                source = ';\n'.join(item.rstrip().rstrip(';') for item in
                    _rebuild_statements) + ';'
            elif (after['kind'] == 'column' and isinstance(change, dict) and
                  change.get('action') in {'set-default', 'set-nullable', 'set-type'}):
                operation = 'alter'
                source = _validated_column_alter(before, after, change)
            elif (after['kind'] == 'column' and isinstance(change, dict) and
                  change.get('action') == 'add-field'):
                operation = 'alter'
                source = _validated_struct_field_add(before, after, change)
            elif (after['kind'] == 'column' and isinstance(change, dict) and
                  change.get('action') == 'drop-field'):
                operation = 'alter'
                source = _validated_struct_field_drop(before, after, change)
            elif (after['kind'] == 'column' and isinstance(change, dict) and
                  change.get('action') in {'add-nested-field', 'drop-nested-field'}):
                operation = 'alter'
                source = _validated_nested_struct_change(before, after, change)
            else:
                raise ValueError('Alteration requires a qualified native adapter; only explicit view replacement is previewed')
            operation_record = {'resource_id': identity, 'kind': after['kind'],
                'name': after['name'], 'operation': operation, 'target': target,
                'source': source, 'baseline_sha256': digest(_definition(before)) if before else None,
                'desired_sha256': digest(_definition(after))}
            if operation == 'rename':
                operation_record['source_resource_id'] = before['resource_id']
            if operation == 'create' and after['kind'] == 'column':
                metadata = after['native'].get('catalog_metadata', {})
                operation_record['postcondition'] = {
                    'data_type': metadata['data_type'],
                    'nullable': True,
                    'default': metadata.get('default'),
                }
            elif operation == 'create' and after['kind'] == 'sequence':
                operation_record['postcondition'] = {
                    'sequence_options': _sequence_creation_options}
            elif after['kind'] == 'column' and isinstance(change, dict) and change.get('action') in {'set-type', 'add-field', 'drop-field', 'add-nested-field', 'drop-nested-field'}:
                operation_record['postcondition'] = {
                    'data_type': after['native']['catalog_metadata']['data_type']}
            elif after['kind'] == 'type' and change == {'action': 'extend-enum'}:
                operation_record['postcondition'] = {'labels': _labels}
            elif after['kind'] == 'macro' and isinstance(change, dict) and change.get('action') == 'replace-definition':
                operation_record['postcondition'] = {'definition': _definition_text}
            elif after['kind'] == 'macro' and isinstance(change, dict) and change.get('action') == 'replace-macro':
                operation_record['postcondition'] = {'overloads': _macro_overloads}
            elif after['kind'] == 'sequence' and isinstance(change, dict) and change.get('action') == 'replace-sequence':
                operation_record['postcondition'] = {'sequence_options': _sequence_options}
            elif after['kind'] == 'type' and isinstance(change, dict) and change.get('action') == 'replace-type':
                operation_record['postcondition'] = {'type_catalog': _type_catalog}
            elif change == {'action': 'set-comment'}:
                operation_record['postcondition'] = {'comment': _comment}
            elif after['kind'] == 'table' and isinstance(change, dict) and change.get('action') == 'add-primary-key':
                operation_record['postcondition'] = {'primary_key_columns': _pk_columns}
            elif operation == 'rebuild':
                child_rows = {key: row for key, row in desired['rows'].items()
                    if row['kind'] == 'constraint' and row.get('path', [])[:3] == after['path']}
                expected_ids = {item.get('resource_id') for item in _expected_constraints}
                if set(child_rows) != expected_ids:
                    raise ValueError('CHECK rebuild requires complete desired constraint child rows')
                for constraint in _expected_constraints:
                    child = child_rows[constraint['resource_id']]
                    metadata = child['native'].get('catalog_metadata', {})
                    if any(metadata.get(key) != constraint.get(key) for key in
                            ('constraint_index', 'constraint_type', 'constraint_text',
                             'expression', 'column_indexes', 'column_names',
                             'referenced_table', 'referenced_column_names')):
                        raise ValueError('CHECK rebuild child and parent constraint facts differ')
                operation_record.update(statements=_rebuild_statements,
                    data_check=_data_check, original_source=_original_source,
                    affected_child_ids=sorted(set(child_rows) | {
                        key for key, row in baseline['rows'].items()
                        if row['kind'] == 'constraint' and row.get('path', [])[:3] == after['path']}),
                    desired_child_sha256={key: digest(_definition(row))
                        for key, row in child_rows.items()},
                    baseline_child_sha256={key: digest(_definition(row))
                        for key, row in baseline['rows'].items()
                        if row['kind'] == 'constraint' and row.get('path', [])[:3] == after['path']},
                    postcondition={'constraints': _expected_constraints})
            operations.append(operation_record)
        except (ValueError, KeyError, TypeError) as error:
            blockers.append({'resource_id': identity, 'name': after.get('name'), 'reason': str(error)})
    for identity, row in baseline['rows'].items():
        if identity not in desired['rows'] and not (row['kind'] == 'constraint' and
                len(row.get('path', [])) == 4 and
                _resource_id('table', row['path'][:2], row['path'][2]) in rebuild_tables):
            ignored.append({'resource_id': identity, 'name': row['name'],
                'reason': 'Missing desired selection is not deletion intent'})
    if not blockers and not conflicts:
        try:
            operations = _ordered_operations(operations, desired)
        except ValueError as error:
            blockers.append({'resource_id': None, 'name': None, 'reason': str(error)})
    return {'format': 'scratchrobin.duckdb.schema-plan@1', 'engine_id': 'duckdb',
        'catalog': catalog, 'operations': operations, 'blockers': blockers,
        'conflicts': conflicts, 'ignored': ignored,
        'execution_sha256': digest(operations), 'native_grammar_validated': True,
        'ready_for_review': bool(operations) and not blockers and not conflicts,
        'application_supported': bool(operations) and not blockers and not conflicts,
        'executed': False,
        'warnings': ['This native preview does not authorize or execute SQL.',
            'Catalog capture may be partial; absent desired rows never authorize drops.',
            'A separate durable review and fresh in-transaction baseline check are required before execution.'] +
            (['CHECK rebuild assigns a new table object; refresh native table and constraint identities after application.']
             if any(item['operation'] == 'rebuild' for item in operations) else []) +
            (['Replacing a native enum does not retarget existing typed columns; review their conversions separately.']
             if any(item['kind'] == 'type' and item['operation'] == 'replace' for item in operations)
             else [])}
