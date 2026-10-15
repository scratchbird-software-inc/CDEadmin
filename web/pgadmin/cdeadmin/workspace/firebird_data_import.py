"""Review data archives against destination-native identities and layouts."""
import hashlib
import json
import re

from .firebird_data_export import MAX_BYTES, MAX_ROWS

TYPE_FIELDS = frozenset({'field_type', 'field_sub_type', 'field_length', 'field_scale',
    'field_precision', 'character_length', 'segment_length', 'character_set', 'collation',
    'array_dimensions', 'dimensions', 'identity_type', 'computed_source'})
NUMBER_FIELDS = frozenset({'field_type', 'field_sub_type', 'field_length', 'field_scale',
    'field_precision', 'character_length', 'segment_length', 'dimensions', 'identity_type'})


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON property in data archive')
        result[key] = value
    return result


def safe_integer(text):
    value = int(text)
    if abs(value) > (1 << 53) - 1:
        raise ValueError('Large exact values must use text transport')
    return value


def parse(source):
    if not isinstance(source, str) or len(source.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Data archive exceeds 8 MiB')
    if re.match(r'\s*ddn\s', source):
        from .firebird_data_ddn import read
        return parse(read(source))
    try:
        value = json.loads(source, object_pairs_hook=unique, parse_int=safe_integer, parse_float=str,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON number')))
    except (ValueError, RecursionError):
        raise ValueError('Invalid data archive JSON or duplicate property') from None
    if isinstance(value, dict) and value.get('format') == 'ddn-workspace@1':
        from .firebird_data_ddn import read
        return parse(read(source))
    if (not isinstance(value, dict) or value.get('format') != 'scratchrobin.firebird.data@1' or
            value.get('contents') not in {'data', 'both'} or not isinstance(value.get('tables'), list)):
        raise ValueError('Expected a versioned Firebird data archive')
    return value


def layout(column):
    result = {}
    for field in TYPE_FIELDS:
        value = column.get(field)
        if field in NUMBER_FIELDS and value is not None:
            if type(value) not in (int, str) or not re.fullmatch(r'-?\d+', str(value), re.ASCII):
                raise ValueError('Invalid numeric native type property')
            try:
                value = int(value)
            except (ValueError, TypeError):
                raise ValueError('Invalid native type layout') from None
        result[field] = value
    return result


def preview(source, current, *, row_order=None):
    document = parse(source)
    native_tables = {}
    for row in current['rows'].values():
        if row['kind'] == 'table' and row['system'] != 'true':
            if row['name'] in native_tables:
                raise ValueError('Ambiguous destination table name')
            native_tables[row['name']] = row
    operations, catalogs, edges, prerequisites, identities = [], {}, {}, [], []
    counts = {}
    for table in document['tables']:
        if not isinstance(table, dict) or not isinstance(table.get('name'), str):
            raise ValueError('Invalid archived table identity')
        name = table['name']
        if name in catalogs:
            raise ValueError('Duplicate archived table')
        target = native_tables.get(name)
        if not target or str(target['native'].get('relation_type')) != '0':
            raise ValueError('Destination persistent table unavailable: ' + name)
        exported = table.get('native_columns')
        if not isinstance(exported, list) or not exported:
            raise ValueError('Archive native column metadata is unavailable')
        columns = target['native'].get('columns') or []
        by_name = {column['name']: column for column in columns}
        if len(by_name) != len(columns):
            raise ValueError('Ambiguous destination columns')
        names = [column.get('name') for column in exported if isinstance(column, dict)]
        if (len(names) != len(exported) or any(not isinstance(name, str) or not name for name in names) or
                len(set(names)) != len(names) or set(names) != by_name.keys()):
            raise ValueError('Archive columns differ from destination: ' + name)
        for column in exported:
            if layout(column) != layout(by_name[column['name']]):
                raise ValueError('Native column type/layout differs: ' + name + '.' + column['name'])
        computed = {column['name'] for column in columns if column.get('computed_source')}
        identity = [column['name'] for column in columns if column.get('identity_type') is not None]
        if identity:
            identities.append({'table': name, 'columns': identity,
                               'allocation_reconciliation': 'required-before-enabling-generated-inserts'})
        values = table.get('rows')
        if not isinstance(values, list) or len(operations) + len(values) > MAX_ROWS:
            raise ValueError('Invalid row list or row limit exceeded')
        for index, row in enumerate(values):
            if not isinstance(row, dict) or set(row) != by_name.keys():
                raise ValueError('Archived row does not match destination columns')
            operations.append({'table': name, 'row': index,
                'values': {key: value for key, value in row.items() if key not in computed},
                'override_identity': bool(identity)})
        counts[name] = len(values)
        catalogs[name] = {'resource': {'resource_id': target['resource_id'], 'resource_kind': 'table',
            'display_name': name, 'display_path': target['path'],
            'extensions': {'firebird': {'native': target['native']}}}}
        edges[name] = {constraint['referenced_relation'] for constraint in target['native'].get('constraints', [])
                       if constraint.get('constraint_type') == 'FOREIGN KEY' and constraint.get('referenced_relation')}
    if not catalogs or type(document.get('row_count')) is not int or document['row_count'] != len(operations):
        raise ValueError('Archive row count does not match its complete table contents')
    for name, required in edges.items():
        for external in sorted(required - catalogs.keys()):
            prerequisites.append({'table': name, 'requires_existing_rows_in': external})
    if row_order is not None:
        if not isinstance(row_order, list) or len(row_order) != len(operations):
            raise ValueError('Explicit row order must include every archived row exactly once')
        remaining_rows = {(item['table'], item['row']): item for item in operations}
        ordered = []
        for item in row_order:
            if (not isinstance(item, dict) or set(item) != {'table', 'row'} or
                    not isinstance(item['table'], str) or type(item['row']) is not int):
                raise ValueError('Explicit row order requires table names and integer row offsets')
            operation = remaining_rows.pop((item['table'], item['row']), None)
            if operation is None:
                raise ValueError('Unknown or duplicate archive row in explicit order')
            ordered.append(operation)
        operations = ordered
        order = list(dict.fromkeys(item['table'] for item in operations))
    else:
        remaining = {name: (required & catalogs.keys()) for name, required in edges.items()}
        order = []
        while remaining:
            ready = sorted(name for name, required in remaining.items() if not required)
            if not ready:
                raise ValueError('Data dependency cycle requires an explicit row staging strategy: ' + ', '.join(sorted(remaining)))
            order.extend(ready)
            for name in ready: del remaining[name]
            for required in remaining.values(): required.difference_update(ready)
        rank = {name: index for index, name in enumerate(order)}
        operations.sort(key=lambda item: (rank[item['table']], item['row']))
    identity_paths = {(item['table'], column) for item in identities for column in item['columns']}
    allocation_targets = []
    for row in current['rows'].values():
        if ((row['kind'] == 'column' and tuple(row['path']) in identity_paths) or
                (row['kind'] == 'sequence' and row['system'] == 'false')):
            allocation_targets.append({'resource_id': row['resource_id'],
                'resource_kind': row['kind'], 'display_name': row['name'],
                'display_path': row['path']})
    allocation_targets.sort(key=lambda item: (item['resource_kind'], item['display_path']))
    return {'format': 'scratchrobin.firebird.data-import-preview@1',
            'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'operations': operations, 'catalogs': catalogs, 'order': order, 'counts': counts,
            'external_prerequisites': prerequisites, 'identity_requirements': identities,
            'allocation_targets': allocation_targets,
            'metadata_execution': False, 'constraints_disabled': False,
            'ordering': 'explicit-row-order' if row_order is not None else 'table-dependencies',
            'generation': current['provenance']['generation']}
