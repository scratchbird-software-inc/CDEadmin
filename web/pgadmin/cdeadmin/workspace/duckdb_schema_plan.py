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
            'overloads': native.get('overloads') if row['kind'] == 'macro' else None}


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
            if before is None:
                if change is not None:
                    raise ValueError('Creation cannot carry replacement or deletion intent')
                if after['kind'] in {'index', 'column'}:
                    parent_path = after['path'][:3]
                    parent_id = _resource_id('table', parent_path[:2], parent_path[2])
                    parent = live['rows'].get(parent_id)
                    if parent is None:
                        raise ValueError('Child creation requires an observed native parent table')
                    _address(parent, catalog)
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
            if after['kind'] == 'column' and isinstance(change, dict) and change.get('action') == 'set-type':
                operation_record['postcondition'] = {
                    'data_type': after['native']['catalog_metadata']['data_type']}
            operations.append(operation_record)
        except (ValueError, KeyError, TypeError) as error:
            blockers.append({'resource_id': identity, 'name': after.get('name'), 'reason': str(error)})
    for identity, row in baseline['rows'].items():
        if identity not in desired['rows']:
            ignored.append({'resource_id': identity, 'name': row['name'],
                'reason': 'Missing desired selection is not deletion intent'})
    return {'format': 'scratchrobin.duckdb.schema-plan@1', 'engine_id': 'duckdb',
        'catalog': catalog, 'operations': operations, 'blockers': blockers,
        'conflicts': conflicts, 'ignored': ignored,
        'execution_sha256': digest(operations), 'native_grammar_validated': True,
        'ready_for_review': bool(operations) and not blockers and not conflicts,
        'application_supported': len(operations) == 1 and not blockers and not conflicts,
        'executed': False,
        'warnings': ['This native preview does not authorize or execute SQL.',
            'Catalog capture may be partial; absent desired rows never authorize drops.',
            'A separate durable review and fresh in-transaction baseline check are required before execution.']}
