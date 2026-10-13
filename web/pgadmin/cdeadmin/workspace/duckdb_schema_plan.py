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


def _validated_enum_extension(before, after, target):
    previous = deepcopy(_definition(before))
    desired = deepcopy(_definition(after))
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


def _validated_macro_replacement(before, after, target):
    previous = deepcopy(_definition(before))
    desired = deepcopy(_definition(after))
    old_overloads, new_overloads = previous['overloads'], desired['overloads']
    if (not isinstance(old_overloads, list) or len(old_overloads) != 1 or
            not isinstance(new_overloads, list) or len(new_overloads) != 1 or
            previous['overload_count'] != 1 or desired['overload_count'] != 1):
        raise ValueError('Only one native scalar macro overload can be replaced')
    old_definition = old_overloads[0].pop('definition', None)
    new_definition = new_overloads[0].pop('definition', None)
    if (old_overloads[0].get('catalog_metadata', {}).get('function_type') != 'macro' or
            old_overloads[0].get('catalog_metadata', {}).get('varargs') or
            not isinstance(new_definition, str) or not new_definition.strip() or
            new_definition == old_definition or
            len(new_definition.encode('utf8')) > 8192 or '\x00' in new_definition or
            any(marker in new_definition for marker in (';', '--', '/*', '*/'))):
        raise ValueError('Macro replacement requires one changed bounded scalar definition')
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
        raise ValueError('Macro replacement requires unchanged scalar parameters')
    source = ('CREATE OR REPLACE MACRO ' + target + '(' +
              ', '.join(_quote(parameter['name']) for parameter in parameters) +
              ') AS ' + new_definition.strip())
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected the macro replacement') from None
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.CREATE:
        raise ValueError('Exactly one native scalar macro replacement is required')
    return source, new_definition


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


def _ordered_operations(operations, desired):
    if len(operations) > 32 or sum(len(item['source'].encode('utf8')) for item in operations) > 1024 * 1024:
        raise ValueError('Native batch exceeds 32 statements or 1 MiB')
    if len(operations) > 1 and any(item['operation'] == 'rename' for item in operations):
        raise ValueError('Rename requires a separate review and descendant refresh')
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
    for identity, after in sorted(desired['rows'].items()):
        before, current = baseline['rows'].get(identity), live['rows'].get(identity)
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
                source = _validated_ddl(after['native'].get('ddl'), 'view', after['path'], replace=True)
            elif change == {'action': 'extend-enum'} and after['kind'] == 'type':
                operation = 'replace'
                source, _labels = _validated_enum_extension(before, after, target)
            elif change == {'action': 'replace-definition'} and after['kind'] == 'macro':
                operation = 'replace'
                source, _definition_text = _validated_macro_replacement(before, after, target)
            elif change == {'action': 'set-comment'}:
                operation = 'alter'
                source, _comment = _validated_comment(before, after, target)
            elif (after['kind'] == 'column' and isinstance(change, dict) and
                  change.get('action') in {'set-default', 'set-nullable', 'set-type'}):
                operation = 'alter'
                source = _validated_column_alter(before, after, change)
            else:
                raise ValueError('Alteration requires a qualified native adapter; only explicit view replacement is previewed')
            operation_record = {'resource_id': identity, 'kind': after['kind'],
                'name': after['name'], 'operation': operation, 'target': target,
                'source': source, 'baseline_sha256': digest(_definition(before)) if before else None,
                'desired_sha256': digest(_definition(after))}
            if operation == 'rename':
                operation_record['source_resource_id'] = before['resource_id']
            if after['kind'] == 'column' and isinstance(change, dict) and change.get('action') == 'set-type':
                operation_record['postcondition'] = {
                    'data_type': after['native']['catalog_metadata']['data_type']}
            elif after['kind'] == 'type' and change == {'action': 'extend-enum'}:
                operation_record['postcondition'] = {'labels': _labels}
            elif after['kind'] == 'macro' and change == {'action': 'replace-definition'}:
                operation_record['postcondition'] = {'definition': _definition_text}
            elif change == {'action': 'set-comment'}:
                operation_record['postcondition'] = {'comment': _comment}
            operations.append(operation_record)
        except (ValueError, KeyError, TypeError) as error:
            blockers.append({'resource_id': identity, 'name': after.get('name'), 'reason': str(error)})
    for identity, row in baseline['rows'].items():
        if identity not in desired['rows']:
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
            (['Replacing a native enum does not retarget existing typed columns; review their conversions separately.']
             if any(item['kind'] == 'type' and item['operation'] == 'replace' for item in operations)
             else [])}
