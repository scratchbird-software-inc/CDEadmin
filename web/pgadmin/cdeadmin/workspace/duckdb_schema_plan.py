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
    indexes = native.get('indexes')
    catalog = {key: value for key, value in native.get('catalog_metadata', {}).items()
               if key not in {'oid', 'last_value'}}
    return {'ddl': native.get('ddl'),
            'catalog': catalog,
            'columns': native.get('columns') if row['kind'] in {'table', 'view'} else None,
            'constraints': native.get('constraints') if row['kind'] == 'table' else None,
            'indexes': ([{key: value for key, value in item.items() if key != 'oid'}
                if isinstance(item, dict) else item for item in indexes]
                if isinstance(indexes, list) else indexes) if row['kind'] == 'table' else None,
            'overloads': native.get('overloads') if row['kind'] == 'macro' else None,
            'definition': native.get('definition') if row['kind'] == 'macro' else None,
            'parameters': native.get('parameters') if row['kind'] == 'macro' else None,
            'overload_count': native.get('overload_count') if row['kind'] == 'macro' else None}


def _fk_parent_definition(row):
    """Bind parent semantics without DuckDB's file-global constraint ordinals."""
    definition = deepcopy(_definition(row))
    for constraint in definition.get('constraints') or []:
        constraint.pop('constraint_index', None)
        constraint.pop('resource_id', None)
    return definition


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


def _validated_column_properties(before, after, change):
    """Order independently admitted ALTERs for one atomic column review."""
    if (not isinstance(change, dict) or
            set(change) not in ({'action'}, {'action', 'using'}) or
            change.get('action') != 'alter-column-properties'):
        raise ValueError('Combined column alteration requires one exact native intent')
    previous = before['native'].get('catalog_metadata', {})
    desired = after['native'].get('catalog_metadata', {})
    type_changed = previous.get('data_type') != desired.get('data_type')
    default_changed = previous.get('default') != desired.get('default')
    nullable_changed = previous.get('nullable') != desired.get('nullable')
    if (sum((type_changed, default_changed, nullable_changed)) < 2 or
            ('using' in change and not type_changed) or
            (not type_changed and any(previous.get(key) != desired.get(key)
                for key in _TYPE_FIELDS))):
        raise ValueError('Combined column alteration requires two admitted property changes')
    state, statements = deepcopy(before), []
    def advance(action, fields, overrides=None):
        nonlocal state
        next_state = deepcopy(state)
        metadata = next_state['native']['catalog_metadata']
        for key in fields:
            metadata[key] = (overrides[key] if overrides and key in overrides
                else desired.get(key))
        intent = {'action': action}
        if action == 'set-type' and 'using' in change:
            intent['using'] = change['using']
        statements.append(_validated_column_alter(state, next_state, intent))
        state = next_state
    if (default_changed and previous.get('default') is not None and
            (desired.get('default') is None or type_changed)):
        advance('set-default', {'default'}, {'default': None})
    if type_changed:
        advance('set-type', _TYPE_FIELDS)
    if default_changed and desired.get('default') is not None:
        advance('set-default', {'default'})
    if nullable_changed:
        advance('set-nullable', {'nullable'})
    if not _equal(_definition(state), _definition(after)):
        raise ValueError('Combined column alteration contains other native edits')
    return statements, {key: desired.get(key) for key in
        ('data_type', 'default', 'nullable')}


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
    if (previous['catalog'].get('comment') != desired['catalog'].get('comment') or
            previous['catalog'].get('tags') or desired['catalog'].get('tags')):
        raise ValueError('Enum replacement requires unchanged comment and no native tags')
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
    old = before['native'].get('catalog_metadata', {})
    new = after['native'].get('catalog_metadata', {})
    if old.get('tags') or new.get('tags') or old.get('comment') != new.get('comment'):
        raise ValueError('View replacement requires unchanged comment and no native tags')
    old_columns = before['native'].get('columns')
    new_columns = after['native'].get('columns')
    if not isinstance(old_columns, list) or not isinstance(new_columns, list):
        raise ValueError('View replacement requires complete native column facts')
    old_comments = {column['name']: column['comment'] for column in old_columns
        if column.get('comment') is not None}
    new_comments = {column['name']: column['comment'] for column in new_columns
        if column.get('comment') is not None}
    if old_comments != new_comments:
        raise ValueError('View replacement requires unchanged commented columns')
    source = _validated_ddl(after['native'].get('ddl'), 'view', after['path'], replace=True)
    target = '.'.join(_quote(part) for part in after['path'])
    replay = _validated_replayed_comment('view', target, old.get('comment'))
    statements = [replay] if replay is not None else []
    for column in sorted(old_columns, key=lambda item: item['ordinal_position']):
        if column.get('comment') is not None:
            statements.append(_validated_replayed_comment('column',
                target + '.' + _quote(column['name']), column['comment']))
    return source, statements, old_comments


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


def _table_definition_sections(source, *, inline_unique=False):
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
                          ('token_type.keyword', 'unique'),
                          ('token_type.keyword', 'foreign'),
                          ('token_type.keyword', 'constraint')}:
            if not any(token in section for token in
                    (('token_type.keyword', 'check'), ('token_type.keyword', 'unique'),
                     ('token_type.keyword', 'foreign'))):
                return None
            checks.append(section)
        else:
            if inline_unique and section[-1] == ('token_type.keyword', 'unique'):
                checks.append((section[-1],))
                section = section[:-1]
                if not section:
                    return None
            columns.append(section)
    return tuple(columns), tuple(checks)


def _admitted_generated_columns(sections, columns):
    """Find virtual columns whose unchanged expression can be recomputed safely."""
    if sections is None or not isinstance(columns, list):
        return None
    marker = ('token_type.keyword', 'generated')
    generated = {}
    for section in sections[0]:
        if marker not in section:
            continue
        position = section.index(marker)
        if (not section or section[0][0] != 'token_type.identifier' or
                not re.fullmatch(r'[a-z_][a-z0-9_]*', section[0][1]) or
                section[position:position + 3] != (
                    marker, ('token_type.keyword', 'always'),
                    ('token_type.keyword', 'as'))):
            return None
        generated[section[0][1]] = section[position + 3:]
    observed = {item.get('name') for item in columns if isinstance(item, dict)}
    if len(observed) != len(columns) or not set(generated) <= observed:
        return None
    base = observed - set(generated)
    if generated and not base:
        return None
    for expression in generated.values():
        if not expression or any(
                (kind == 'token_type.identifier' and word not in base) or
                (kind == 'token_type.operator' and word not in
                    {'(', ')', '+', '-', '*', '/', '%', '||'}) or
                (kind == 'token_type.keyword' and word not in
                    {'true', 'false', 'null'}) or
                kind not in {'token_type.identifier', 'token_type.operator',
                    'token_type.keyword', 'token_type.numeric_const',
                    'token_type.string_const'}
                for kind, word in expression):
            return None
    return set(generated)


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
    if (previous['catalog'].get('comment') != desired['catalog'].get('comment') or
            previous['catalog'].get('tags') or desired['catalog'].get('tags')):
        raise ValueError('Macro replacement requires unchanged comment and no native tags')
    old_overloads, new_overloads = previous['overloads'], desired['overloads']
    if (not isinstance(old_overloads, list) or len(old_overloads) != 1 or
            not isinstance(new_overloads, list) or len(new_overloads) != 1 or
            previous['overload_count'] != 1 or desired['overload_count'] != 1):
        raise ValueError('Only one native macro overload can be replaced')
    old_definition = old_overloads[0].pop('definition', None)
    new_definition = new_overloads[0].pop('definition', None)
    macro_kind = old_overloads[0].get('catalog_metadata', {}).get('function_type')
    if macro_kind == 'table_macro' and previous['catalog'].get('comment') is not None:
        raise ValueError('DuckDB 1.5.2 cannot comment on table macros')
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
    group_comment = native.get('catalog_metadata', {}).get('comment')
    if (not isinstance(overloads, list) or not 1 <= len(overloads) <= 32 or
            native.get('overload_count') != len(overloads) or
            native.get('catalog_metadata', {}).get('tags')):
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
                metadata.get('comment') != group_comment or metadata.get('tags') or
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
    old_comment = before['native'].get('catalog_metadata', {}).get('comment')
    new_comment = after['native'].get('catalog_metadata', {}).get('comment')
    if old_comment != new_comment:
        raise ValueError('Whole macro replacement requires unchanged native comment')
    previous = _macro_overload_postcondition(before)
    desired = _macro_overload_postcondition(after)
    if previous == desired:
        raise ValueError('Whole macro replacement needs an observable desired overload change')
    if old_comment is not None and desired[0]['kind'] == 'table_macro':
        raise ValueError('DuckDB 1.5.2 cannot comment on table macros')
    source = _validated_ddl(change.get('source'), 'macro', after['path'], replace=True)
    target = '.'.join(_quote(part) for part in after['path'])
    return source, desired, _validated_replayed_comment('macro', target, old_comment)


def _validated_sequence_replacement(before, after, change):
    if change != {'action': 'replace-sequence', 'reset_state_confirmed': True}:
        raise ValueError('Sequence replacement requires explicit generator reset confirmation')
    previous, desired = deepcopy(_definition(before)), deepcopy(_definition(after))
    if (previous['catalog'].get('automatic_dependency_observed') or
            desired['catalog'].get('automatic_dependency_observed')):
        raise ValueError('Sequence replacement is blocked by an observed automatic dependency')
    if (previous['catalog'].get('comment') != desired['catalog'].get('comment') or
            previous['catalog'].get('tags') or desired['catalog'].get('tags')):
        raise ValueError('Sequence replacement requires unchanged comment and no native tags')
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
    if (previous['catalog'].get('comment') != desired['catalog'].get('comment') or
            previous['catalog'].get('tags') or desired['catalog'].get('tags')):
        raise ValueError('Type replacement requires unchanged comment and no native tags')
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


def _validated_replayed_index(index, table_target):
    import duckdb
    ddl = index['native'].get('ddl')
    if not isinstance(ddl, str) or not ddl or len(ddl.encode('utf8')) > 1024 * 1024:
        raise ValueError('Independent index has no bounded native definition to preserve')
    encoded = ddl.encode('utf8')
    try:
        tokens = duckdb.tokenize(ddl)
    except duckdb.Error:
        raise ValueError('Independent index definition cannot be tokenized') from None
    on = next((number for number, (offset, kind) in enumerate(tokens)
        if kind == duckdb.token_type.keyword and
        encoded[offset:tokens[number + 1][0] if number + 1 < len(tokens) else len(encoded)]
            .decode('utf8').strip().casefold() == 'on'), None)
    opening = next((offset for offset, kind in tokens[on + 1:]
        if kind == duckdb.token_type.operator and encoded[offset:offset + 1] == b'('), None) if on is not None else None
    if opening is None:
        raise ValueError('Independent index expression cannot be reconstructed')
    metadata = index['native'].get('catalog_metadata', {})
    if metadata.get('primary') or metadata.get('tags') or type(metadata.get('unique')) is not bool:
        raise ValueError('Independent index has unsupported native metadata')
    source = ('CREATE ' + ('UNIQUE ' if metadata['unique'] else '') + 'INDEX ' +
        _quote(index['name']) + ' ON ' + table_target + encoded[opening:].decode('utf8'))
    return _validated_index_ddl(source, index['path'])


def _validated_replayed_comment(kind, target, comment):
    if comment is None:
        return None
    if not isinstance(comment, str) or len(comment.encode('utf8')) > 8192 or '\x00' in comment:
        raise ValueError('Native comment cannot be preserved within the review budget')
    source = ('COMMENT ON ' + kind.upper() + ' ' + target + ' IS ' +
        "'" + comment.replace("'", "''") + "'")
    import duckdb
    try:
        parsed = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native comment replay is not parseable') from None
    if len(parsed) != 1 or parsed[0].type != duckdb.StatementType.ALTER:
        raise ValueError('Native comment replay requires one ALTER statement')
    return source


def _native_cast_signature(value):
    """Normalize only the built-in target spelling of an unchanged cast."""
    if (not isinstance(value, str) or len(value.encode('utf8')) > 8192 or
            '\x00' in value):
        return None
    scalar = (r'(?:BOOLEAN|TINYINT|SMALLINT|INTEGER|BIGINT|UTINYINT|'
        r'USMALLINT|UINTEGER|UBIGINT|HUGEINT|UHUGEINT|REAL|FLOAT|DOUBLE|'
        r'DECIMAL|VARCHAR|DATE|TIME|TIMESTAMP|TIMESTAMPTZ|UUID|JSON|BLOB|INTERVAL)')
    found = re.fullmatch(r'CAST\(\s*(.+)\s+AS\s+("?' + scalar +
        r'"?)(?:\(\s*([0-9]+)(?:\s*,\s*([0-9]+))?\s*\))?\s*\)',
        value.strip(), re.I | re.S)
    if found is None or found[2].startswith('"') != found[2].endswith('"'):
        return None
    expression = found[1].strip()
    if not expression:
        return None
    if expression.casefold() in {'true', 'false', 'null'}:
        expression = expression.casefold()
    return expression, found[2].strip('"').casefold(), found[3], found[4]


def _native_default_equivalent(expected, observed):
    if expected == observed:
        return True
    signature = _native_cast_signature(expected)
    return signature is not None and signature == _native_cast_signature(observed)


def _inbound_definition_matches(observed, expected):
    """Compare unchanged FK-child facts across native literal-cast rendering."""
    if observed.get('kind') != expected.get('kind'):
        return False
    actual, desired = deepcopy(_definition(observed)), deepcopy(_definition(expected))
    if observed['kind'] == 'table':
        def ddl_tokens(source):
            tokens = create_definition_tokens(source, 'table')
            if tokens is None:
                return None
            return tuple(('word', word) if index and
                tokens[index - 1][1] == 'as' and
                word.casefold() in {'boolean', 'tinyint', 'smallint', 'integer',
                    'bigint', 'utinyint', 'usmallint', 'uinteger', 'ubigint',
                    'hugeint', 'uhugeint', 'real', 'float', 'double', 'decimal',
                    'varchar', 'date', 'time', 'timestamp', 'timestamptz',
                    'uuid', 'json', 'blob', 'interval'} else (kind, word)
                for index, (kind, word) in enumerate(tokens))
        actual['ddl'], desired['ddl'] = ddl_tokens(actual['ddl']), ddl_tokens(desired['ddl'])
        if actual['ddl'] is None or desired['ddl'] is None:
            return False
        old_columns, new_columns = actual.get('columns'), desired.get('columns')
        if (not isinstance(old_columns, list) or not isinstance(new_columns, list) or
                len(old_columns) != len(new_columns)):
            return False
        for old_column, new_column in zip(old_columns, new_columns):
            if _native_default_equivalent(new_column.get('default'),
                    old_column.get('default')):
                old_column['default'] = new_column.get('default')
    elif observed['kind'] == 'column':
        if _native_default_equivalent(desired['catalog'].get('default'),
                actual['catalog'].get('default')):
            actual['catalog']['default'] = desired['catalog'].get('default')
    return _equal(actual, desired)


def _validated_inbound_child(before, child_id, intermediate_ddl,
        baseline, live, desired):
    """Bind one plain FK child for a three-phase parent rebuild."""
    def constant_default(value):
        if value is None:
            return True
        if (not isinstance(value, str) or not value.strip() or
                len(value.encode('utf8')) > 8192 or '\x00' in value):
            return False
        if 'nextval' in value.casefold():
            return re.fullmatch(
                r"nextval\('[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?'\)",
                value.strip(), re.I) is not None
        return True

    child = live['rows'].get(child_id)
    old_child = baseline['rows'].get(child_id)
    new_child = desired['rows'].get(child_id)
    if (not isinstance(child_id, str) or child is None or old_child is None or
            new_child is None or child['kind'] != 'table' or
            child['path'][:2] != before['path'][:2] or child_id == before['resource_id'] or
            child['system'] != 'false' or new_child['native'].get('duckdb_change') is not None or
            not re.fullmatch(r'[a-z_][a-z0-9_]*', child['name']) or
            not _equal(_definition(old_child), _definition(child)) or
            not _equal(_definition(new_child), _definition(child))):
        raise ValueError('Inbound rebuild requires one unchanged same-schema child')
    native = child['native']
    metadata = native.get('catalog_metadata', {})
    columns = native.get('columns')
    constraints = native.get('constraints')
    indexes = sorted((row for row in live['rows'].values()
        if row['kind'] == 'index' and row.get('path', [])[:3] == child['path']),
        key=lambda row: row['resource_id'])
    foreign = [item for item in constraints
        if isinstance(item, dict) and item.get('constraint_type') == 'FOREIGN KEY'] if (
            isinstance(constraints, list)) else []
    checks = [item for item in constraints
        if isinstance(item, dict) and item.get('constraint_type') == 'CHECK'] if (
            isinstance(constraints, list)) else []
    uniques = [item for item in constraints
        if isinstance(item, dict) and item.get('constraint_type') == 'UNIQUE'] if (
            isinstance(constraints, list)) else []
    primary = [item for item in constraints
        if isinstance(item, dict) and item.get('constraint_type') == 'PRIMARY KEY'] if (
            isinstance(constraints, list)) else []
    nulls = [item for item in constraints
        if isinstance(item, dict) and item.get('constraint_type') == 'NOT NULL'] if (
            isinstance(constraints, list)) else []
    original = native.get('ddl')
    original_sections = _table_definition_sections(original, inline_unique=True)
    generated_names = _admitted_generated_columns(original_sections, columns)
    parent_foreign = [item for item in foreign
        if item.get('referenced_table') == before['name']]
    other_foreign = [item for item in foreign
        if item.get('referenced_table') != before['name']]
    if (metadata.get('tags') or
            metadata.get('temporary') is not False or
            type(metadata.get('has_primary_key')) is not bool or
            metadata['has_primary_key'] != bool(primary) or len(primary) > 1 or
            not isinstance(native.get('indexes'), list) or
            {item.get('resource_id') for item in native['indexes']} !=
                {item['resource_id'] for item in indexes} or
            not isinstance(columns, list) or not 1 <= len(columns) <= 128 or
            generated_names is None or
            len({item.get('name') for item in columns if isinstance(item, dict)}) !=
                len(columns) or
            not isinstance(constraints, list) or len(parent_foreign) != 1 or
            len(constraints) != len(checks) + len(uniques) +
                len(primary) + len(nulls) + len(foreign) or
            any(not isinstance(item.get('column_names'), list) or
                not isinstance(item.get('referenced_column_names'), list) or
                not item['column_names'] or
                len(item['column_names']) != len(item['referenced_column_names'])
                for item in foreign) or
            any(not isinstance(item, dict) or
                (item.get('name') not in generated_names and
                    not constant_default(item.get('default'))) for item in columns)):
        raise ValueError('Inbound child requires one parent key, bounded constraints and admitted defaults')
    other_parent_sha256 = {}
    for edge in other_foreign:
        referenced = edge.get('referenced_table')
        if (not isinstance(referenced, str) or not referenced or '.' in referenced or
                referenced == child['name']):
            raise ValueError('Secondary foreign key needs a separate same-schema parent')
        parent_id = _resource_id('table', child['path'][:2], referenced)
        parents = [model['rows'].get(parent_id) for model in
            (baseline, live, desired)]
        if (any(row is None or row['kind'] != 'table' or row['path'] !=
                [*child['path'][:2], referenced] for row in parents) or
                any(not _equal(_fk_parent_definition(parents[0]),
                    _fk_parent_definition(row)) for row in parents[1:])):
            raise ValueError('Secondary foreign-key parent changed or is outside the observed scope')
        other_parent_sha256[parent_id] = digest(_fk_parent_definition(parents[0]))
    for index in indexes:
        observed_index = baseline['rows'].get(index['resource_id'])
        desired_index = desired['rows'].get(index['resource_id'])
        index_metadata = index['native'].get('catalog_metadata', {})
        if (observed_index is None or desired_index is None or
                not _equal(_definition(observed_index), _definition(index)) or
                not _equal(_definition(desired_index), _definition(index)) or
                index_metadata.get('tags') or index_metadata.get('unique') is not False):
            raise ValueError('Inbound child requires unchanged plain independent indexes')
    source = _validated_ddl(intermediate_ddl, 'table', child['path'])
    interim_sections = _table_definition_sections(source, inline_unique=True)
    original_secondary = original_sections[1] if original_sections else ()
    parent_clause = parent_foreign[0].get('constraint_text')
    parent_sections = (_table_definition_sections(
        'CREATE TABLE scratchrobin_fk_clause (id INTEGER, ' + parent_clause + ')')
        if isinstance(parent_clause, str) else None)
    retained_sections = [tuple((*original_secondary[:position],
        *original_secondary[position + 1:]))
        for position, section in enumerate(original_secondary)
        if parent_sections is not None and len(parent_sections[1]) == 1 and
            section == parent_sections[1][0]]
    if (original_sections is None or interim_sections is None or
            original_sections[0] != interim_sections[0] or
            len(original_secondary) != len(checks) + len(uniques) + len(foreign) or
            len(retained_sections) != 1 or
            interim_sections[1] != retained_sections[0]):
        raise ValueError('Intermediate child must remove only the rebuilt parent foreign key')
    original_prefix = re.match(r'^\s*CREATE\s+TABLE\s+(?:' +
        re.escape(child['name']) + '|' + re.escape(_quote(child['name'])) +
        r')(?=\s*\()', original, re.I) if isinstance(original, str) else None
    if original_prefix is None:
        raise ValueError('Inbound child native definition cannot be reconstructed')
    target = '.'.join(_quote(part) for part in child['path'])
    restore = 'CREATE TABLE ' + target + original[original_prefix.end():]
    _validated_ddl(restore, 'table', child['path'])
    stage_names = ['__scratchrobin_inbound_' + digest(source + suffix)[:16]
        for suffix in ('_without_key', '_restore_key')]
    if len(set(stage_names)) != 2 or any(_resource_id('table', child['path'][:2], name)
            in live['rows'] or _resource_id('table', child['path'][:2], name)
            in desired['rows'] for name in stage_names):
        raise ValueError('Inbound child stage identity already exists')
    names = ', '.join(_quote(item['name']) for item in columns)
    copy_names = ', '.join(_quote(item['name']) for item in columns
        if item['name'] not in generated_names)
    def sequence_dependencies(table_name):
        literals = ["'" + value.replace("'", "''") + "'" for value in
            [*child['path'][:2], table_name]]
        return ('SELECT sequence_oid FROM duckdb_sequences() AS s '
            'JOIN duckdb_dependencies() AS d ON d.objid = s.sequence_oid '
            "WHERE d.deptype = 'n' AND d.refobjid = (SELECT table_oid "
            'FROM duckdb_tables() WHERE database_name = ' + literals[0] +
            ' AND schema_name = ' + literals[1] + ' AND table_name = ' +
            literals[2] + ')')
    original_dependencies = sequence_dependencies(child['name'])
    sequence_checks = []
    sequence_counts = []
    for stage_name in stage_names:
        staged = sequence_dependencies(stage_name)
        sequence_checks.append('SELECT count(*) FROM ((' + original_dependencies +
            ' EXCEPT ALL ' + staged + ') UNION ALL (' + staged +
            ' EXCEPT ALL ' + original_dependencies + ')) AS differences')
        sequence_counts.append('SELECT count(*) FROM (' +
            original_dependencies + ') AS dependencies')
    requires_sequence_dependency = any(isinstance(item.get('default'), str) and
        item['default'].strip().casefold().startswith('nextval(')
        for item in columns)
    def phase(definition, stage_name):
        stage = '.'.join(_quote(part) for part in [*child['path'][:2], stage_name])
        prefix = re.match(r'^\s*CREATE\s+TABLE\s+' + re.escape(target), definition, re.I)
        if prefix is None:
            raise ValueError('Inbound child requires an exact qualified definition')
        creation = 'CREATE TABLE ' + stage + definition[prefix.end():]
        _validated_ddl(creation, 'table', [*child['path'][:2], stage_name])
        statements = [creation,
            'INSERT INTO ' + stage + ' (' + copy_names + ') SELECT ' + copy_names + ' FROM ' + target,
            'DROP TABLE ' + target + ' RESTRICT',
            'ALTER TABLE ' + stage + ' RENAME TO ' + _quote(child['name'])]
        check = ('SELECT count(*) FROM ((SELECT ' + names + ' FROM ' + target +
            ' EXCEPT ALL SELECT ' + names + ' FROM ' + stage + ') UNION ALL (SELECT ' +
            names + ' FROM ' + stage + ' EXCEPT ALL SELECT ' + names + ' FROM ' +
            target + ')) AS differences')
        return statements, check
    first, first_check = phase(source, stage_names[0])
    final, final_check = phase(restore, stage_names[1])
    for index in indexes:
        final.append(_validated_replayed_index(index, target))
    comments = [
        ('table', target, metadata.get('comment')),
        *(( 'column', target + '.' + _quote(column['name']), column.get('comment'))
          for column in columns),
        *(( 'index', '.'.join(_quote(part) for part in
            [index['path'][0], index['path'][1], index['name']]),
            index['native'].get('catalog_metadata', {}).get('comment'))
          for index in indexes),
    ]
    comment_statements = []
    for kind, comment_target, comment in comments:
        replay = _validated_replayed_comment(kind, comment_target, comment)
        if replay is not None:
            comment_statements.append(replay)
    final.extend(comment_statements)
    import duckdb
    for statement, expected in zip([*first, *final],
            ['CREATE', 'INSERT', 'DROP', 'ALTER'] * 2 +
            ['CREATE'] * len(indexes) + ['ALTER'] * len(comment_statements)):
        try:
            parsed = duckdb.extract_statements(statement)
        except duckdb.Error:
            raise ValueError('Inbound child rebuild statement cannot be parsed') from None
        if len(parsed) != 1 or parsed[0].type != getattr(duckdb.StatementType, expected):
            raise ValueError('Inbound child rebuild requires exact native statements')
    return child, first, final, {'child_resource_id': child_id,
        'stage_names': stage_names, 'data_checks': [first_check, final_check],
        'sequence_dependency_checks': sequence_checks,
        'sequence_dependency_counts': sequence_counts,
        'requires_sequence_dependency': requires_sequence_dependency,
        'other_parent_sha256': other_parent_sha256,
        'columns': [{key: item.get(key) for key in
            ('name', 'data_type', 'default', 'nullable')} for item in columns],
        'constraints_by_phase': [[{key: item.get(key) for key in
            ('constraint_type', 'column_names', 'referenced_table',
             'referenced_column_names', 'constraint_text')}
            for item in phase] for phase in (
                [*checks, *uniques, *primary, *nulls, *other_foreign], constraints)]}


def _validated_check_rebuild(before, after, change, target, baseline, live, desired):
    action = change.get('action') if isinstance(change, dict) else None
    allowed = {'rebuild-check-constraints': {'CHECK'},
        'rebuild-check-with-inbound-child': {'CHECK'},
        'rebuild-check-with-inbound-children': {'CHECK'},
        'rebuild-unique-constraints': {'CHECK', 'UNIQUE'},
        'rebuild-foreign-keys': {'FOREIGN KEY'},
        'rebuild-column-order': set(),
        'rebuild-add-column-and-reorder': set(),
        'rebuild-add-columns-and-reorder': set(),
        'rebuild-add-generated-column-and-reorder': set(),
        'rebuild-add-generated-column': set(),
        'rebuild-drop-primary-key': {'PRIMARY KEY', 'NOT NULL'},
        'rebuild-retarget-primary-key': {'PRIMARY KEY', 'NOT NULL'}}.get(action)
    expected_change = {'action': action,
        'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
    if action == 'rebuild-check-with-inbound-child':
        expected_change.update(inbound_child_resource_id=change.get(
            'inbound_child_resource_id'), intermediate_child_ddl=change.get(
            'intermediate_child_ddl'))
    elif action == 'rebuild-check-with-inbound-children':
        expected_change['inbound_children'] = change.get('inbound_children')
    if allowed is None or change != expected_change:
        raise ValueError('Constraint rebuild needs complete-definition and row-preservation confirmation')
    old, new = deepcopy(_definition(before)), deepcopy(_definition(after))
    old_constraints, new_constraints = old.pop('constraints'), new.pop('constraints')
    old.pop('ddl'); new.pop('ddl')
    stage_key_columns = None
    if action in {'rebuild-column-order', 'rebuild-add-column-and-reorder',
            'rebuild-add-columns-and-reorder',
            'rebuild-add-generated-column-and-reorder',
            'rebuild-add-generated-column'}:
        shape_addition = action != 'rebuild-column-order'
        old_columns, new_columns = old.pop('columns'), new.pop('columns')
        def column_map(items):
            if (not isinstance(items, list) or len(items) < (
                    1 if action == 'rebuild-add-generated-column' else 2) or
                    any(not isinstance(item, dict) or
                        not isinstance(item.get('name'), str) or
                        item.get('ordinal_position') != position
                        for position, item in enumerate(items, 1))):
                return None
            mapped = {item['name']: {key: value for key, value in item.items()
                if key != 'ordinal_position'} for item in items}
            return mapped if len(mapped) == len(items) else None
        old_map, new_map = column_map(old_columns), column_map(new_columns)
        if old_map is None or new_map is None:
            raise ValueError('Column-order rebuild requires complete native column rows')
        if (not isinstance(old_constraints, list) or
                not isinstance(new_constraints, list) or
                any(not isinstance(item, dict) or
                    type(item.get('constraint_index')) is not int for item in
                    [*old_constraints, *new_constraints])):
            raise ValueError('Column-order rebuild requires complete native constraint rows')
        def key_facts(items, ordered_columns):
            if (not isinstance(items, list) or
                    any(not isinstance(item, dict) for item in items)):
                return None
            if not items:
                return []
            keys = [item.get('column_names') for item in items
                if isinstance(item, dict) and item.get('constraint_type') == 'PRIMARY KEY']
            if (len(keys) != 1 or not isinstance(keys[0], list) or not keys[0] or
                    any(not isinstance(name, str) or not name for name in keys[0]) or
                    len(set(keys[0])) != len(keys[0]) or
                    len(items) != len(keys[0]) + 1 or
                    {item.get('constraint_type') for item in items
                        if isinstance(item, dict)} != {'PRIMARY KEY', 'NOT NULL'}):
                return None
            names = [item['name'] for item in ordered_columns]
            if not set(keys[0]) <= set(names):
                return None
            nulls = [item.get('column_names') for item in items
                if item.get('constraint_type') == 'NOT NULL']
            if (len(nulls) != len(keys[0]) or
                    any(not isinstance(value, list) or len(value) != 1 or
                        not isinstance(value[0], str) for value in nulls) or
                    {tuple(value) for value in nulls} !=
                        {(name,) for name in keys[0]}):
                return None
            for item in items:
                if item.get('column_indexes') != [names.index(name)
                        for name in item['column_names']]:
                    return None
            return keys[0]
        old_key = key_facts([item for item in old_constraints
            if item.get('constraint_type') not in {'UNIQUE', 'CHECK'}], old_columns)
        new_key = key_facts([item for item in new_constraints
            if item.get('constraint_type') not in {'UNIQUE', 'CHECK'}], new_columns)
        def positional_facts(items, ordered_columns, kind):
            if not isinstance(items, list):
                return False
            facts = [item for item in items if isinstance(item, dict) and
                item.get('constraint_type') == kind]
            names = [item['name'] for item in ordered_columns]
            return all(isinstance(item.get('column_names'), list) and
                (kind == 'CHECK' or item['column_names']) and
                all(isinstance(name, str) and name in names
                    for name in item['column_names']) and
                len(set(item['column_names'])) == len(item['column_names']) and
                item.get('column_indexes') == [names.index(name)
                    for name in item['column_names']]
                for item in facts)
        def semantic_constraints(items):
            names = [item.get('name') for item in items]
            if (any(not isinstance(name, str) or not name for name in names) or
                    len(set(names)) != len(items)):
                return None
            return {item['name']: {key: value for key, value in item.items()
                if key not in {'resource_id', 'constraint_index',
                    'column_indexes'}} for item in items}
        old_indices = {item.get('constraint_index') for item in old_constraints}
        new_indices = {item.get('constraint_index') for item in new_constraints}
        old_semantic = semantic_constraints(old_constraints)
        new_semantic = semantic_constraints(new_constraints)
        if shape_addition:
            added_names = set(new_map or ()) - set(old_map or ())
            required_count = (1 if action in {'rebuild-add-column-and-reorder',
                'rebuild-add-generated-column-and-reorder',
                'rebuild-add-generated-column'}
                else 128)
            valid_count = (len(added_names) == 1 if required_count == 1
                else 2 <= len(added_names) <= required_count)
            additions = [new_map[name] for name in sorted(added_names)] if (
                new_map is not None and valid_count) else []
            valid_columns = (old_map is not None and new_map is not None and
                len(new_columns) <= 128 and
                len(new_columns) == len(old_columns) + len(added_names) and
                valid_count and set(old_map) < set(new_map) and
                all(_equal(item, new_map.get(name)) for name, item in old_map.items()) and
                all(item.get('nullable') is True and item.get('comment') is None and
                    (isinstance(item.get('default'), str) and
                        0 < len(item['default']) <= 4096 if action in
                            {'rebuild-add-generated-column-and-reorder',
                             'rebuild-add-generated-column'} else
                        item.get('default') is None) for item in additions))
            if valid_columns:
                for added in additions:
                    _native_column_type(added.get('data_type'))
        else:
            valid_columns = _equal(old_map, new_map)
        if (old_key is None or new_key is None or old_key != new_key or
                len(old_indices) != len(old_constraints) or
                len(new_indices) != len(new_constraints) or
                old_indices != new_indices or
                old_semantic is None or new_semantic is None or
                not positional_facts(old_constraints, old_columns, 'UNIQUE') or
                not positional_facts(new_constraints, new_columns, 'UNIQUE') or
                not positional_facts(old_constraints, old_columns, 'CHECK') or
                not positional_facts(new_constraints, new_columns, 'CHECK') or
                not _equal(old_semantic, new_semantic) or
                not valid_columns or
                ([item['name'] for item in old_columns] ==
                    [item['name'] for item in new_columns
                        if not shape_addition or item['name'] in old_map]) is not
                    (action == 'rebuild-add-generated-column') or
                old['catalog'].get('has_primary_key') is not bool(old_key) or
                not _equal(old, new)):
            raise ValueError('Column-shape rebuild requires complete unchanged columns and admitted constraints')
        stage_key_columns = new_key
    if action in {'rebuild-drop-primary-key', 'rebuild-retarget-primary-key'}:
        def key_facts(constraints):
            keys = [item.get('column_names') for item in constraints
                if item.get('constraint_type') == 'PRIMARY KEY']
            names = keys[0] if len(keys) == 1 else None
            nulls = [item.get('column_names') for item in constraints
                if item.get('constraint_type') == 'NOT NULL']
            if (not isinstance(names, list) or not names or
                    len(set(names)) != len(names) or len(nulls) != len(names) or
                    {tuple(item or []) for item in nulls} != {
                        (name,) for name in names}):
                raise ValueError('Primary-key rebuild requires its complete implicit NOT NULL set')
            return names
        key_columns = key_facts(old_constraints)
        stage_key_columns = (key_facts(new_constraints)
            if action == 'rebuild-retarget-primary-key' else [])
        old_columns, new_columns = old.pop('columns'), new.pop('columns')
        if (old['catalog'].pop('has_primary_key', None) is not True or
                new['catalog'].pop('has_primary_key', None) is not
                    (action == 'rebuild-retarget-primary-key') or
                not isinstance(old_columns, list) or not isinstance(new_columns, list) or
                len(old_columns) != len(new_columns) or
                (action == 'rebuild-drop-primary-key' and new_constraints) or
                (action == 'rebuild-retarget-primary-key' and
                    key_columns == stage_key_columns)):
            raise ValueError('Primary-key rebuild requires a distinct complete desired key')
        for old_column, new_column in zip(old_columns, new_columns):
            if (not isinstance(old_column, dict) or not isinstance(new_column, dict) or
                    not _equal({key: value for key, value in old_column.items()
                        if key != 'nullable'},
                        {key: value for key, value in new_column.items()
                        if key != 'nullable'})):
                raise ValueError('Primary-key rebuild may change only key-column nullability')
            if (old_column.get('nullable') is not (old_column['name'] not in key_columns) or
                    new_column.get('nullable') is not
                        (new_column['name'] not in stage_key_columns)):
                raise ValueError('Primary-key rebuild nullability must follow key membership')
    retained_types = ({'PRIMARY KEY', 'NOT NULL', 'CHECK', 'UNIQUE'} if
        action == 'rebuild-foreign-keys' else {'PRIMARY KEY', 'NOT NULL', 'UNIQUE'} if
        action in {'rebuild-check-constraints', 'rebuild-check-with-inbound-child',
            'rebuild-check-with-inbound-children'} else set() if
        action in {'rebuild-drop-primary-key', 'rebuild-retarget-primary-key',
            'rebuild-column-order', 'rebuild-add-column-and-reorder',
            'rebuild-add-columns-and-reorder',
            'rebuild-add-generated-column-and-reorder',
            'rebuild-add-generated-column'}
        else {'PRIMARY KEY', 'NOT NULL'})
    old_retained = [item for item in old_constraints
        if item.get('constraint_type') in retained_types] if isinstance(old_constraints, list) else []
    new_retained = [item for item in new_constraints
        if item.get('constraint_type') in retained_types] if isinstance(new_constraints, list) else []
    if (action not in {'rebuild-column-order', 'rebuild-add-column-and-reorder',
            'rebuild-add-columns-and-reorder',
            'rebuild-add-generated-column-and-reorder',
            'rebuild-add-generated-column'} and
            (not _equal(old, new) or _equal(old_constraints, new_constraints) or
            not isinstance(old_constraints, list) or not isinstance(new_constraints, list) or
            not _equal(old_retained, new_retained) or
            any(item.get('constraint_type') not in (allowed | retained_types) for item in
                [*old_constraints, *new_constraints]))):
        raise ValueError('Constraint rebuild may change only its admitted native constraint kinds')
    if action == 'rebuild-unique-constraints' and not any(
            item.get('constraint_type') == 'UNIQUE' for item in
            [*old_constraints, *new_constraints]):
        raise ValueError('UNIQUE rebuild requires an observed or desired UNIQUE constraint')
    if action == 'rebuild-foreign-keys' and not any(
            item.get('constraint_type') == 'FOREIGN KEY' for item in
            [*old_constraints, *new_constraints]):
        raise ValueError('Foreign-key rebuild requires an observed or desired foreign key')
    metadata = before['native'].get('catalog_metadata', {})
    columns = before['native'].get('columns')
    if (type(metadata.get('has_primary_key')) is not bool or metadata.get('tags') or
            (metadata['has_primary_key'] != any(item.get('constraint_type') ==
                'PRIMARY KEY' for item in old_constraints)) or
            not isinstance(columns, list) or not 1 <= len(columns) <= 128 or
            any(not isinstance(item, dict) or not isinstance(item.get('name'), str)
                for item in columns) or
            len({item['name'] for item in columns}) != len(columns)):
        raise ValueError('Constraint rebuild requires plain unchanged columns without native tags')
    indexes = sorted((row for row in live['rows'].values()
        if row['kind'] == 'index' and row.get('path', [])[:3] == before['path']),
        key=lambda row: row['resource_id'])
    if {row['resource_id'] for row in indexes} != {
            item.get('resource_id') for item in before['native'].get('indexes', [])}:
        raise ValueError('Constraint rebuild cannot account for every native independent index')
    for index in indexes:
        desired_index = desired['rows'].get(index['resource_id'])
        if (desired_index is None or not _equal(_definition(index), _definition(desired_index)) or
                index['native'].get('catalog_metadata', {}).get('tags')):
            raise ValueError('Constraint rebuild requires unchanged tag-free independent indexes')
    inbound_requests = []
    if action == 'rebuild-check-with-inbound-child':
        inbound_requests = [{'resource_id': change['inbound_child_resource_id'],
            'intermediate_ddl': change['intermediate_child_ddl']}]
    elif action == 'rebuild-check-with-inbound-children':
        inbound_requests = change['inbound_children']
        if (not isinstance(inbound_requests, list) or
                not 2 <= len(inbound_requests) <= 63 or
                any(not isinstance(item, dict) or set(item) !=
                    {'resource_id', 'intermediate_ddl'} for item in inbound_requests)):
            raise ValueError('Inbound review requires two to sixty-three complete child definitions')
    if len({item['resource_id'] for item in inbound_requests}) != len(inbound_requests):
        raise ValueError('Inbound review repeats a child identity')
    inbound = [_validated_inbound_child(before, item['resource_id'],
        item['intermediate_ddl'], baseline, live, desired)
        for item in inbound_requests]
    if len({name for item in inbound for name in item[3]['stage_names']}) != 2 * len(inbound):
        raise ValueError('Inbound child stages must have distinct native identities')
    preserved_views, preserved_macros = [], []
    for row in live['rows'].values():
        if inbound and row['kind'] in {'view', 'macro'}:
            raise ValueError('Inbound child rebuild cannot preserve views or macros')
        if row['kind'] == 'view':
            view_id = row['resource_id']
            old_view = baseline['rows'].get(view_id)
            new_view = desired['rows'].get(view_id)
            if (len(preserved_views) + len(preserved_macros) >= 16 or
                    row['path'][0] != before['path'][0] or
                    row['system'] != 'false' or
                    row['native'].get('catalog_metadata', {}).get('temporary') or
                    old_view is None or new_view is None or
                    old_view['path'] != row['path'] or new_view['path'] != row['path'] or
                    new_view['native'].get('duckdb_change') is not None or
                    not _equal(_definition(old_view), _definition(row)) or
                    not _equal(_definition(new_view), _definition(row))):
                raise ValueError('Constraint rebuild requires unchanged persistent views in one catalog')
            view_columns = [child for child in live['rows'].values()
                if child['kind'] == 'column' and child.get('path', [])[:3] == row['path']]
            if {child['resource_id'] for child in view_columns} != {
                    item.get('resource_id') for item in row['native'].get('columns', [])}:
                raise ValueError('Constraint rebuild cannot account for every view column')
            for child in view_columns:
                old_child = baseline['rows'].get(child['resource_id'])
                new_child = desired['rows'].get(child['resource_id'])
                if (old_child is None or new_child is None or
                        new_child['native'].get('duckdb_change') is not None or
                        not _equal(_definition(old_child), _definition(child)) or
                        not _equal(_definition(new_child), _definition(child))):
                    raise ValueError('Constraint rebuild requires unchanged view columns')
            preserved_views.append(row)
        if row['kind'] == 'macro':
            macro_id = row['resource_id']
            old_macro = baseline['rows'].get(macro_id)
            new_macro = desired['rows'].get(macro_id)
            overloads = row['native'].get('overloads')
            def admitted_overloads():
                if (not isinstance(overloads, list) or not 1 <= len(overloads) <= 8 or
                        row['native'].get('overload_count') != len(overloads)):
                    return False
                arities, kinds = [], set()
                for overload in overloads:
                    if not isinstance(overload, dict):
                        return False
                    metadata = overload.get('catalog_metadata', {})
                    parameters = overload.get('parameters')
                    if (not isinstance(parameters, list) or len(parameters) > 8 or
                            any(not isinstance(item, dict) or
                                not isinstance(item.get('name'), str) or not item['name']
                                for item in parameters) or
                            metadata.get('varargs') is not None or
                            metadata.get('has_side_effects') is not False or
                            metadata.get('function_type') not in {'macro', 'table_macro'}):
                        return False
                    arities.append(len(parameters))
                    kinds.add(metadata['function_type'])
                return len(arities) == len(set(arities)) and len(kinds) == 1
            if (len(preserved_views) + len(preserved_macros) >= 16 or
                    row['path'][0] != before['path'][0] or row['system'] != 'false' or
                    old_macro is None or new_macro is None or
                    old_macro['path'] != row['path'] or new_macro['path'] != row['path'] or
                    new_macro['native'].get('duckdb_change') is not None or
                    not admitted_overloads() or
                    not _equal(_definition(old_macro), _definition(row)) or
                    not _equal(_definition(new_macro), _definition(row))):
                raise ValueError('Constraint rebuild requires complete distinct-arity macro overloads')
            preserved_macros.append(row)
        if row['kind'] == 'attached-database' or (
                row['kind'] == 'sequence' and row['native'].get(
                    'catalog_metadata', {}).get('automatic_dependency_observed') is True):
            raise ValueError('Constraint rebuild is blocked by a native dependent object category')
        if row['kind'] == 'table':
            blocked_types = (set() if action == 'rebuild-foreign-keys' else
                {'FOREIGN KEY'}) if (
                row['resource_id'] == before['resource_id']) else (
                    set() if any(row['resource_id'] == item[0]['resource_id']
                        for item in inbound) else {'FOREIGN KEY'})
            if any(item.get('constraint_type') in blocked_types for item in
                    row['native'].get('constraints', [])):
                raise ValueError('Constraint rebuild is blocked by native key dependencies')
    fk_parents = {key: value for item in inbound
        for key, value in item[3]['other_parent_sha256'].items()}
    if action == 'rebuild-foreign-keys':
        for constraint in [*old_constraints, *new_constraints]:
            if constraint.get('constraint_type') != 'FOREIGN KEY':
                continue
            referenced = constraint.get('referenced_table')
            if (not isinstance(referenced, str) or not referenced or
                    '.' in referenced or referenced == before['name']):
                raise ValueError('Foreign key requires a separate same-schema parent table')
            parent_path = [*before['path'][:2], referenced]
            parent_id = _resource_id('table', parent_path[:2], referenced)
            parent_rows = [model['rows'].get(parent_id) for model in
                (baseline, live, desired)]
            if (any(row is None or row['kind'] != 'table' or row['path'] != parent_path
                    for row in parent_rows) or
                    any(not _equal(_fk_parent_definition(parent_rows[0]),
                        _fk_parent_definition(row))
                        for row in parent_rows[1:])):
                raise ValueError('Foreign-key parent changed or is outside the observed scope')
            fk_parents[parent_id] = digest(_fk_parent_definition(parent_rows[0]))
    source = _validated_ddl(after['native'].get('ddl'), 'table', after['path'])
    body = create_definition_tokens(source, 'table')
    original_sections = _table_definition_sections(before['native'].get('ddl'),
        inline_unique=action in {'rebuild-unique-constraints',
            'rebuild-check-constraints', 'rebuild-foreign-keys',
            'rebuild-check-with-inbound-child', 'rebuild-check-with-inbound-children',
            'rebuild-column-order', 'rebuild-add-column-and-reorder',
            'rebuild-add-columns-and-reorder',
            'rebuild-add-generated-column-and-reorder',
            'rebuild-add-generated-column'})
    desired_sections = _table_definition_sections(source,
        inline_unique=action in {'rebuild-unique-constraints',
            'rebuild-check-constraints', 'rebuild-foreign-keys',
            'rebuild-check-with-inbound-child', 'rebuild-check-with-inbound-children',
            'rebuild-column-order', 'rebuild-add-column-and-reorder',
            'rebuild-add-columns-and-reorder',
            'rebuild-add-generated-column-and-reorder',
            'rebuild-add-generated-column'})
    generated_names = _admitted_generated_columns(original_sections, columns)
    shape_valid = True
    if action in {'rebuild-add-column-and-reorder',
            'rebuild-add-columns-and-reorder',
            'rebuild-add-generated-column-and-reorder',
            'rebuild-add-generated-column'}:
        def section_map(sections):
            if sections is None or any(not section or section[0][0] !=
                    'token_type.identifier' for section in sections[0]):
                return None
            found = {section[0][1]: section for section in sections[0]}
            return found if len(found) == len(sections[0]) else None
        original_tokens = section_map(original_sections)
        desired_tokens = section_map(desired_sections)
        added_names = {item['name'].casefold() for item in after['native']['columns']} - (
            {item['name'].casefold() for item in columns})
        generated_addition = action in {'rebuild-add-generated-column-and-reorder',
            'rebuild-add-generated-column'}
        desired_generated = (_admitted_generated_columns(desired_sections,
            after['native']['columns']) if generated_addition else None)
        valid_additions = (len(added_names) == 1 if
            action in {'rebuild-add-column-and-reorder',
                'rebuild-add-generated-column-and-reorder',
                'rebuild-add-generated-column'} else
            2 <= len(added_names) <= 128)
        shape_valid = (original_tokens is not None and
            desired_tokens is not None and valid_additions and
            (not generated_addition or (generated_names is not None and
                desired_generated is not None and
                desired_generated - generated_names == added_names)) and
            set(desired_tokens) - set(original_tokens) == added_names and
            all(desired_tokens.get(name) == section for name, section in
                original_tokens.items()) and
            all(not any(kind == 'token_type.keyword' and word in
                ({'default', 'primary', 'unique', 'check', 'references'} if
                    generated_addition else
                    {'default', 'generated', 'primary', 'unique', 'check', 'references'})
                for kind, word in desired_tokens[name]) for name in added_names))
    old_inline = sum(item.get('constraint_type') in {'PRIMARY KEY', 'NOT NULL'}
        for item in old_constraints)
    new_inline = sum(item.get('constraint_type') in {'PRIMARY KEY', 'NOT NULL'}
        for item in new_constraints)
    if (body is None or original_sections is None or desired_sections is None or
            generated_names is None or
            not shape_valid or
            (generated_names and action not in {'rebuild-check-constraints',
                'rebuild-unique-constraints', 'rebuild-foreign-keys',
                'rebuild-check-with-inbound-child',
                'rebuild-check-with-inbound-children',
                'rebuild-column-order', 'rebuild-drop-primary-key',
                'rebuild-retarget-primary-key',
                'rebuild-add-column-and-reorder',
                'rebuild-add-columns-and-reorder',
                'rebuild-add-generated-column-and-reorder',
                'rebuild-add-generated-column'}) or
            not original_sections[0] or (action not in {
                'rebuild-drop-primary-key', 'rebuild-retarget-primary-key',
                'rebuild-column-order', 'rebuild-add-column-and-reorder',
                'rebuild-add-columns-and-reorder',
                'rebuild-add-generated-column-and-reorder',
                'rebuild-add-generated-column'} and
                original_sections[0] != desired_sections[0]) or
            (action == 'rebuild-column-order' and
                sorted(original_sections[0]) != sorted(desired_sections[0])) or
            len(original_sections[1]) != len(old_constraints) - old_inline or
            len(desired_sections[1]) != len(new_constraints) - new_inline or any(
            kind == 'token_type.keyword' and word in
                ((set() if action == 'rebuild-column-order' else
                  {'primary'} if action == 'rebuild-drop-primary-key' else set()) |
                 ({'foreign', 'references'} if action != 'rebuild-foreign-keys' else set()) |
                 ({'unique'} if action not in {'rebuild-unique-constraints',
                    'rebuild-check-constraints', 'rebuild-foreign-keys',
                    'rebuild-check-with-inbound-child',
                    'rebuild-check-with-inbound-children',
                    'rebuild-column-order',
                    'rebuild-add-column-and-reorder',
                    'rebuild-add-columns-and-reorder',
                    'rebuild-add-generated-column-and-reorder',
                    'rebuild-add-generated-column'} else set()))
            for kind, word in body)):
        raise ValueError('Constraint rebuild requires a complete plain CREATE TABLE body')
    stage_name = '__scratchrobin_rebuild_' + digest(source)[:16]
    stage_path = [*after['path'][:2], stage_name]
    stage_id = _resource_id('table', stage_path[:2], stage_name)
    if stage_id in live['rows'] or stage_id in desired['rows']:
        raise ValueError('Constraint rebuild staging identity already exists')
    stage = '.'.join(_quote(part) for part in stage_path)
    source_prefix = re.match(r'^\s*CREATE\s+TABLE\s+' + re.escape(target), source, re.I)
    creation = 'CREATE TABLE ' + stage + source[source_prefix.end():]
    _validated_ddl(creation, 'table', stage_path)
    names = ', '.join(_quote(item['name']) for item in columns)
    copy_names = ', '.join(_quote(item['name']) for item in columns
        if item['name'] not in generated_names)
    statements = [creation,
        'INSERT INTO ' + stage + ' (' + copy_names + ') SELECT ' + copy_names + ' FROM ' + target,
        'DROP TABLE ' + target + ' RESTRICT',
        'ALTER TABLE ' + stage + ' RENAME TO ' + _quote(after['name'])]
    expected_types = ['CREATE', 'INSERT', 'DROP', 'ALTER']
    for index in indexes:
        statements.append(_validated_replayed_index(index, target))
        expected_types.append('CREATE')
    for kind, comment_target, comment in [
            ('table', target, metadata.get('comment')),
            *(( 'column', target + '.' + _quote(column['name']), column.get('comment'))
              for column in columns),
            *(( 'index', '.'.join(_quote(part) for part in
                [index['path'][0], index['path'][1], index['name']]),
                index['native'].get('catalog_metadata', {}).get('comment'))
              for index in indexes)]:
        replay = _validated_replayed_comment(kind, comment_target, comment)
        if replay is not None:
            statements.append(replay)
            expected_types.append('ALTER')
    check = ('SELECT count(*) FROM ((SELECT ' + names + ' FROM ' + target +
        ' EXCEPT ALL SELECT ' + names + ' FROM ' + stage + ') UNION ALL (SELECT ' +
        names + ' FROM ' + stage + ' EXCEPT ALL SELECT ' + names + ' FROM ' +
        target + ')) AS differences')
    def sequence_dependencies(table_name):
        literals = ["'" + value.replace("'", "''") + "'" for value in
            [before['path'][0], before['path'][1], table_name]]
        return ('SELECT sequence_oid FROM duckdb_sequences() AS s '
            'JOIN duckdb_dependencies() AS d ON d.objid = s.sequence_oid '
            "WHERE d.deptype = 'n' AND d.refobjid = (SELECT table_oid "
            'FROM duckdb_tables() WHERE database_name = ' + literals[0] +
            ' AND schema_name = ' + literals[1] + ' AND table_name = ' +
            literals[2] + ')')
    original_dependencies = sequence_dependencies(before['name'])
    staged_dependencies = sequence_dependencies(stage_name)
    dependency_check = ('SELECT count(*) FROM ((' + original_dependencies +
        ' EXCEPT ALL ' + staged_dependencies + ') UNION ALL (' +
        staged_dependencies + ' EXCEPT ALL ' + original_dependencies +
        ')) AS differences')
    dependency_count = 'SELECT count(*) FROM (' + original_dependencies + ') AS dependencies'
    requires_sequence_dependency = any(isinstance(item.get('default'), str) and
        'nextval' in item['default'].casefold() for item in columns)
    import duckdb
    for statement, expected in zip(statements, expected_types):
        try:
            parsed = duckdb.extract_statements(statement)
        except duckdb.Error:
            raise ValueError('Native constraint rebuild statement is not parseable') from None
        if len(parsed) != 1 or parsed[0].type != getattr(duckdb.StatementType, expected):
            raise ValueError('Native constraint rebuild requires exact reviewed statements')
    inbound_details = []
    if inbound:
        parent_statements = statements
        first_statements = [statement for item in inbound for statement in item[1]]
        final_statements = [statement for item in inbound for statement in item[2]]
        parent_offset = len(first_statements)
        first_offset, final_offset = 0, parent_offset + len(parent_statements)
        for _child, first, final, details in inbound:
            details['first_offset'] = first_offset
            details['parent_offset'] = parent_offset
            details['final_offset'] = final_offset
            inbound_details.append(details)
            first_offset += len(first)
            final_offset += len(final)
        statements = [*first_statements, *parent_statements, *final_statements]
    stage_columns = ([{key: column.get(key) for key in
        ('name', 'data_type', 'default', 'nullable')}
        for column in after['native']['columns']]
        if action in {'rebuild-drop-primary-key', 'rebuild-retarget-primary-key',
            'rebuild-column-order', 'rebuild-add-column-and-reorder',
            'rebuild-add-columns-and-reorder',
            'rebuild-add-generated-column-and-reorder',
            'rebuild-add-generated-column'}
        else None)
    return (statements, check, dependency_check, dependency_count,
        requires_sequence_dependency, source, new_constraints, indexes,
        fk_parents, stage_name, stage_columns, stage_key_columns,
        preserved_views, preserved_macros, inbound_details)


def _ordered_operations(operations, desired):
    statement_limit = (512 if len(operations) == 1 and
        operations[0]['operation'] == 'rebuild' else 32)
    if (sum(len(item.get('statements', [item['source']])) for item in operations) >
            statement_limit or
            sum(len(item['source'].encode('utf8')) for item in operations) > 1024 * 1024):
        raise ValueError(f'Native batch exceeds {statement_limit} statements or 1 MiB')
    if len(operations) > 1 and any(item['operation'] == 'rename' for item in operations):
        raise ValueError('Rename requires a separate review and descendant refresh')
    if len(operations) > 1 and any(item['operation'] == 'rebuild' for item in operations):
        raise ValueError('Constraint table rebuild requires a separate review')
    replaced_views = {item['resource_id'] for item in operations
        if item['kind'] == 'view' and item['operation'] == 'replace'}
    if replaced_views and any(item['kind'] == 'column' and
            _resource_id('view', desired['rows'][item['resource_id']]['path'][:2],
                desired['rows'][item['resource_id']]['path'][2]) in replaced_views
            for item in operations):
        raise ValueError('View replacement and child comment edits require separate reviews')
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
        and row['native']['duckdb_change'].get('action') in
            {'rebuild-check-constraints', 'rebuild-unique-constraints',
             'rebuild-foreign-keys', 'rebuild-check-with-inbound-child',
             'rebuild-check-with-inbound-children',
             'rebuild-drop-primary-key',
             'rebuild-retarget-primary-key', 'rebuild-column-order',
             'rebuild-add-column-and-reorder',
             'rebuild-add-columns-and-reorder',
             'rebuild-add-generated-column-and-reorder',
             'rebuild-add-generated-column'}}
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
                    'reason': 'Constraint rebuild child identity or intent is not native'})
            continue
        if (after['kind'] == 'column' and len(after.get('path', [])) == 4 and (
                _resource_id('table', after['path'][:2], after['path'][2]) in rebuild_tables) and
                desired['rows'][_resource_id('table', after['path'][:2],
                    after['path'][2])]['native']['duckdb_change']['action'] in
                    {'rebuild-drop-primary-key', 'rebuild-retarget-primary-key',
                     'rebuild-column-order', 'rebuild-add-column-and-reorder',
                     'rebuild-add-columns-and-reorder',
                     'rebuild-add-generated-column-and-reorder',
                     'rebuild-add-generated-column'}):
            parent_action = desired['rows'][_resource_id('table',
                after['path'][:2], after['path'][2])]['native']['duckdb_change']['action']
            if ((before is None and parent_action not in
                    {'rebuild-add-column-and-reorder',
                     'rebuild-add-columns-and-reorder',
                     'rebuild-add-generated-column-and-reorder',
                     'rebuild-add-generated-column'}) or
                    (before is not None and after['resource_id'] != before['resource_id']) or
                    after['system'] != 'false' or
                    after['native'].get('system_object') is not False or
                    after['native'].get('duckdb_change') is not None):
                blockers.append({'resource_id': identity, 'name': after.get('name'),
                    'reason': 'Primary-key rebuild column identity or intent is not native'})
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
                (source, _view_comment_replays,
                 _view_column_comments) = _validated_view_replacement(before, after)
            elif change == {'action': 'extend-enum'} and after['kind'] == 'type':
                operation = 'replace'
                source, _labels = _validated_enum_extension(before, after, target)
            elif (isinstance(change, dict) and change.get('action') == 'replace-definition' and
                  after['kind'] == 'macro'):
                operation = 'replace'
                source, _definition_text = _validated_macro_replacement(before, after, target, change)
                _macro_comment_replay = _validated_replayed_comment('macro', target,
                    before['native'].get('catalog_metadata', {}).get('comment'))
            elif (isinstance(change, dict) and change.get('action') == 'replace-macro' and
                  after['kind'] == 'macro'):
                operation = 'replace'
                source, _macro_overloads, _macro_comment_replay = _validated_macro_group_replacement(
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
                  change.get('action') in
                  {'rebuild-check-constraints', 'rebuild-unique-constraints',
                   'rebuild-foreign-keys', 'rebuild-check-with-inbound-child',
                   'rebuild-check-with-inbound-children',
                   'rebuild-drop-primary-key',
                   'rebuild-retarget-primary-key', 'rebuild-column-order',
                   'rebuild-add-column-and-reorder',
                   'rebuild-add-columns-and-reorder',
                   'rebuild-add-generated-column-and-reorder',
                   'rebuild-add-generated-column'}):
                operation = 'rebuild'
                (_rebuild_statements, _data_check, _dependency_check,
                 _dependency_count, _requires_sequence_dependency,
                 _original_source, _expected_constraints, _replayed_indexes,
                 _fk_parents, _stage_name, _stage_columns, _stage_key_columns,
                 _preserved_views, _preserved_macros, _inbound_details) = (
                    _validated_check_rebuild(before, after, change, target,
                        baseline, live, desired))
                source = ';\n'.join(item.rstrip().rstrip(';') for item in
                    _rebuild_statements) + ';'
            elif (after['kind'] == 'column' and isinstance(change, dict) and
                  change.get('action') in {'set-default', 'set-nullable', 'set-type'}):
                operation = 'alter'
                source = _validated_column_alter(before, after, change)
            elif (after['kind'] == 'column' and isinstance(change, dict) and
                  change.get('action') == 'alter-column-properties'):
                operation = 'alter'
                _column_property_statements, _column_property_postcondition = (
                    _validated_column_properties(before, after, change))
                source = ';\n'.join(item.rstrip().rstrip(';')
                    for item in _column_property_statements) + ';'
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
            if operation == 'replace' and after['kind'] == 'view':
                operation_record['preserved_comment'] = after['native'].get(
                    'catalog_metadata', {}).get('comment')
                operation_record['preserved_column_comments'] = _view_column_comments
                if _view_comment_replays:
                    operation_record['statements'] = [source, *_view_comment_replays]
            if operation == 'replace' and after['kind'] in {'sequence', 'type'}:
                comment = after['native'].get('catalog_metadata', {}).get('comment')
                replay = _validated_replayed_comment(after['kind'], target, comment)
                operation_record['preserved_comment'] = comment
                if replay is not None:
                    operation_record['statements'] = [source, replay]
            if (operation == 'replace' and after['kind'] == 'macro' and
                    change.get('action') in {'replace-definition', 'replace-macro'}):
                operation_record['preserved_comment'] = after['native'].get(
                    'catalog_metadata', {}).get('comment')
                if _macro_comment_replay is not None:
                    operation_record['statements'] = [source, _macro_comment_replay]
            if operation == 'rename':
                operation_record['source_resource_id'] = before['resource_id']
            if (after['kind'] == 'column' and isinstance(change, dict) and
                    change.get('action') == 'alter-column-properties'):
                operation_record['statements'] = _column_property_statements
                operation_record['postcondition'] = _column_property_postcondition
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
                if _inbound_details:
                    inbound_ids = {item['child_resource_id']
                        for item in _inbound_details}
                    inbound_paths = {tuple(baseline['rows'][key]['path'])
                        for key in inbound_ids}
                    inbound_rows = {key: row for key, row in baseline['rows'].items()
                        if key in inbound_ids or (row['kind'] in {'column', 'constraint', 'index'} and
                            tuple(row.get('path', [])[:3]) in inbound_paths)}
                    desired_inbound_ids = {key for key, row in desired['rows'].items()
                        if key in inbound_ids or (row['kind'] in {'column', 'constraint', 'index'} and
                            tuple(row.get('path', [])[:3]) in inbound_paths)}
                    if (not inbound_rows or set(inbound_rows) != desired_inbound_ids or
                            any(key not in desired['rows'] or
                            desired['rows'][key]['native'].get('duckdb_change') is not None or
                            not _equal(_definition(row), _definition(desired['rows'][key]))
                            for key, row in inbound_rows.items())):
                        raise ValueError('Inbound child and descendants must remain unchanged')
                    operation_record.update(inbound_children=_inbound_details,
                        affected_inbound_ids=sorted(inbound_rows),
                        baseline_inbound_sha256={key: digest(_definition(row))
                            for key, row in inbound_rows.items()},
                        desired_inbound_sha256={key: digest(_definition(
                            desired['rows'][key])) for key in inbound_rows})
                if _stage_columns is not None:
                    old_columns = {row['resource_id']: row for row in baseline['rows'].values()
                        if row['kind'] == 'column' and row.get('path', [])[:3] == after['path']}
                    new_columns = {row['resource_id']: row for row in desired['rows'].values()
                        if row['kind'] == 'column' and row.get('path', [])[:3] == after['path']}
                    added_ids = set(new_columns) - set(old_columns)
                    addition_action = change.get('action')
                    added_count_valid = (
                        len(added_ids) == 1 if addition_action in
                            {'rebuild-add-column-and-reorder',
                             'rebuild-add-generated-column-and-reorder',
                             'rebuild-add-generated-column'} else
                        2 <= len(added_ids) <= 128 if addition_action ==
                            'rebuild-add-columns-and-reorder' else
                        not added_ids)
                    if ((not set(old_columns) <= set(new_columns)) or
                            not added_count_valid or
                            any(new_columns[key]['path'] != [*after['path'],
                                new_columns[key]['name']] or
                                key != _resource_id('column', after['path'],
                                    new_columns[key]['name']) for key in added_ids) or
                            {row['name']: row['native'].get('catalog_metadata')
                                for row in new_columns.values()} !=
                            {column['name']: {key: value for key, value in column.items()
                                if key not in {'resource_id', 'name'}}
                                for column in after['native']['columns']}):
                        raise ValueError('Staged rebuild child columns differ from reviewed table')
                    operation_record.update(
                        affected_column_ids=sorted(new_columns),
                        added_column_ids=sorted(added_ids),
                        baseline_column_sha256={key: digest(_definition(row))
                            for key, row in old_columns.items()},
                        desired_column_sha256={key: digest(_definition(row))
                            for key, row in new_columns.items()})
                    if addition_action in {'rebuild-add-column-and-reorder',
                            'rebuild-add-columns-and-reorder',
                            'rebuild-add-generated-column-and-reorder',
                            'rebuild-add-generated-column'}:
                        added_columns = [new_columns[column['resource_id']]
                            for column in after['native']['columns']
                            if column['resource_id'] in added_ids]
                        derived = {column['name']: {key: value for key, value in
                            column['native']['catalog_metadata'].items() if key in {
                                'data_type_id', 'character_maximum_length',
                                'numeric_precision', 'numeric_precision_radix',
                                'numeric_scale'} and value is not None}
                            for column in added_columns}
                        if addition_action == 'rebuild-add-column-and-reorder':
                            operation_record['stage_null_column'] = added_columns[0]['name']
                            operation_record['stage_added_derived'] = derived[
                                added_columns[0]['name']]
                        elif addition_action == 'rebuild-add-columns-and-reorder':
                            operation_record['stage_null_columns'] = list(derived)
                            operation_record['stage_added_derived_columns'] = derived
                        else:
                            operation_record['stage_added_derived_columns'] = derived
                child_rows = {key: row for key, row in desired['rows'].items()
                    if row['kind'] == 'constraint' and row.get('path', [])[:3] == after['path']}
                expected_ids = {item.get('resource_id') for item in _expected_constraints}
                if set(child_rows) != expected_ids:
                    raise ValueError('Constraint rebuild requires complete desired child rows')
                for constraint in _expected_constraints:
                    child = child_rows[constraint['resource_id']]
                    metadata = child['native'].get('catalog_metadata', {})
                    if any(metadata.get(key) != constraint.get(key) for key in
                            ('constraint_index', 'constraint_type', 'constraint_text',
                             'expression', 'column_indexes', 'column_names',
                             'referenced_table', 'referenced_column_names')):
                        raise ValueError('Constraint rebuild child and parent facts differ')
                operation_record.update(statements=_rebuild_statements,
                    data_check=_data_check, sequence_dependency_check=_dependency_check,
                    sequence_dependency_count=_dependency_count,
                    requires_sequence_dependency=_requires_sequence_dependency,
                    original_source=_original_source,
                    stage_unique_constraints=([{
                        'column_names': item['column_names'],
                        'constraint_text': item['constraint_text']}
                        for item in _expected_constraints
                        if item['constraint_type'] == 'UNIQUE']
                        if change.get('action') in {'rebuild-check-constraints',
                            'rebuild-foreign-keys', 'rebuild-check-with-inbound-child',
                            'rebuild-check-with-inbound-children',
                            'rebuild-column-order',
                            'rebuild-add-column-and-reorder',
                            'rebuild-add-columns-and-reorder',
                            'rebuild-add-generated-column-and-reorder',
                            'rebuild-add-generated-column'} else None),
                    stage_check_constraints=([{
                        'column_names': item['column_names'],
                        'constraint_text': item['constraint_text']}
                        for item in _expected_constraints
                        if item['constraint_type'] == 'CHECK']
                        if change.get('action') in {'rebuild-column-order',
                            'rebuild-add-column-and-reorder',
                            'rebuild-add-columns-and-reorder',
                            'rebuild-add-generated-column-and-reorder',
                            'rebuild-add-generated-column'} else None),
                    stage_constraint_order=([[
                        item['constraint_type'], item['column_names'],
                        item['constraint_text']]
                        for item in sorted(_expected_constraints,
                            key=lambda item: item['constraint_index'])]
                        if change.get('action') in {'rebuild-column-order',
                            'rebuild-add-column-and-reorder',
                            'rebuild-add-columns-and-reorder',
                            'rebuild-add-generated-column-and-reorder',
                            'rebuild-add-generated-column'} else None),
                    affected_child_ids=sorted(set(child_rows) | {
                        key for key, row in baseline['rows'].items()
                        if row['kind'] == 'constraint' and row.get('path', [])[:3] == after['path']}),
                    desired_child_sha256={key: digest(_definition(row))
                        for key, row in child_rows.items()},
                    baseline_child_sha256={key: digest(_definition(row))
                        for key, row in baseline['rows'].items()
                        if row['kind'] == 'constraint' and row.get('path', [])[:3] == after['path']},
                    affected_index_ids=[row['resource_id'] for row in _replayed_indexes],
                    desired_index_sha256={row['resource_id']: digest(_definition(
                        desired['rows'][row['resource_id']])) for row in _replayed_indexes},
                    baseline_index_sha256={row['resource_id']: digest(_definition(
                        baseline['rows'][row['resource_id']])) for row in _replayed_indexes},
                    fk_parent_sha256=_fk_parents,
                    affected_view_ids=[row['resource_id'] for row in _preserved_views],
                    baseline_view_sha256={row['resource_id']: digest(_definition(row))
                        for row in _preserved_views},
                    desired_view_sha256={row['resource_id']: digest(_definition(
                        desired['rows'][row['resource_id']]))
                        for row in _preserved_views},
                    affected_macro_ids=[row['resource_id'] for row in _preserved_macros],
                    baseline_macro_sha256={row['resource_id']: digest(_definition(row))
                        for row in _preserved_macros},
                    desired_macro_sha256={row['resource_id']: digest(_definition(
                        desired['rows'][row['resource_id']]))
                        for row in _preserved_macros},
                    affected_view_column_ids=sorted(child['resource_id']
                        for view in _preserved_views for child in live['rows'].values()
                        if child['kind'] == 'column' and child.get('path', [])[:3] ==
                            view['path']),
                    baseline_view_column_sha256={child['resource_id']:
                        digest(_definition(baseline['rows'][child['resource_id']]))
                        for view in _preserved_views for child in live['rows'].values()
                        if child['kind'] == 'column' and child.get('path', [])[:3] ==
                            view['path']},
                    desired_view_column_sha256={child['resource_id']:
                        digest(_definition(desired['rows'][child['resource_id']]))
                        for view in _preserved_views for child in live['rows'].values()
                        if child['kind'] == 'column' and child.get('path', [])[:3] ==
                            view['path']},
                    stage_name=_stage_name, stage_columns=_stage_columns,
                    stage_key_columns=_stage_key_columns,
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
            (['Constraint rebuild assigns a new table object; refresh native table and constraint identities after application.']
             if any(item['operation'] == 'rebuild' for item in operations) else []) +
            (['Replacing a native enum does not retarget existing typed columns; review their conversions separately.']
             if any(item['kind'] == 'type' and item['operation'] == 'replace' for item in operations)
             else [])}
