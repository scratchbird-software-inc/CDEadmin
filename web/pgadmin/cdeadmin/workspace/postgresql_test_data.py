"""Bounded native test-data scripts; generation performs no database writes."""
import base64
import hashlib
import json
import re
from ..providers.postgresql.native_admin import _identifier, _qualified

FORMAT = 'scratchrobin.postgresql.test-data@1'
LIMIT = 4 * 1024 * 1024
SQL_LIMIT = 1024 * 1024


def _integer(value):
    if not isinstance(value, str) or not re.fullmatch(r'[+-]?[0-9]{1,39}', value):
        raise ValueError('Integer generator values require exact decimal strings')
    return int(value)


def _literal(value):
    if value is None:
        return 'NULL'
    if type(value) is bool:
        return 'TRUE' if value else 'FALSE'
    if type(value) is int and abs(value) <= 2**53 - 1:
        return str(value)
    if isinstance(value, str):
        if '\0' in value or len(value.encode()) > 1024 * 1024:
            raise ValueError('Generated text is invalid or exceeds 1 MiB')
        return "E'" + value.replace('\\', '\\\\').replace("'", "''") + "'"
    if isinstance(value, dict) and set(value) == {'type', 'value'} and isinstance(value['value'], str):
        data = value['value']
        if len(data) > 1024 * 1024:
            raise ValueError('Typed value exceeds 1 MiB')
        if value['type'] == 'integer':
            return str(_integer(data))
        if value['type'] == 'decimal' and re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?', data):
            return _literal(data) + '::numeric'
        if value['type'] == 'binary':
            try:
                base64.b64decode(data, validate=True)
            except ValueError:
                raise ValueError('Invalid binary value') from None
            return 'pg_catalog.decode(' + _literal(data) + ", 'base64')"
    raise ValueError('Use exact text, safe integers or explicit integer/decimal/binary values')


def tables(model):
    return {identity: row for identity, row in model['rows'].items()
            if row['kind'] in {'table', 'partitioned-table'} and row.get('system') == 'false'}


def template(model):
    result = []
    for identity, row in tables(model).items():
        attributes = row['native'].get('children', {}).get('pg_attribute', [])
        result.append({'resource_id': identity, 'schema': row['native']['schema'], 'name': row['name'],
            'columns': [{'name': column['attname'], 'data_type': column.get('formatted_type'),
                         'insertable': not column.get('attgenerated') and column.get('attidentity') != 'a'}
                        for column in attributes]})
    return {'tables': result, 'format': FORMAT, 'executed': False,
            'scope': {key: model['provenance'][key] for key in ('endpoint_id', 'database_target_id')}}


def generate(model, recipe):
    if (not isinstance(recipe, dict) or set(recipe) != {'format', 'seed', 'tables', 'scope'} or
            recipe['format'] != FORMAT or type(recipe['seed']) is not int or not 0 <= recipe['seed'] <= 2**32 - 1 or
            not isinstance(recipe['tables'], list) or not 1 <= len(recipe['tables']) <= 32):
        raise ValueError('Invalid native test-data recipe')
    expected_scope = {key: model['provenance'][key] for key in ('endpoint_id', 'database_target_id')}
    if recipe['scope'] != expected_scope:
        raise ValueError('Recipe belongs to another endpoint or database; reconcile identities explicitly')
    if len(json.dumps(recipe, allow_nan=False).encode()) > LIMIT:
        raise ValueError('Recipe exceeds 4 MiB')
    available, selected, dependencies, returned, samples = tables(model), {}, {}, {}, {}
    total = 0
    fields = {'constant': {'value'}, 'default': set(), 'sequential': {'start', 'step'},
              'random-integer': {'min', 'max'}, 'choice': {'values'}, 'file': {'values'},
              'generated': {'table', 'column'}, 'returned': {'table', 'column'},
              'existing': {'table', 'column', 'order_by'}}
    for entry in recipe['tables']:
        if not isinstance(entry, dict) or set(entry) != {'table', 'count', 'columns'}:
            raise ValueError('Invalid recipe table')
        identity, count, columns = entry['table'], entry['count'], entry['columns']
        if (not isinstance(identity, str) or identity not in available or identity in selected or
                type(count) is not int or not 1 <= count <= 1000 or not isinstance(columns, dict)):
            raise ValueError('Unknown/duplicate table or invalid row count/columns')
        total += count
        if total > 5000:
            raise ValueError('Recipe exceeds 5000 rows')
        native_columns = {column['attname']: column for column in available[identity]['native'].get('children', {}).get('pg_attribute', [])}
        required = set()
        for name, source in columns.items():
            if name not in native_columns or not isinstance(source, dict):
                raise ValueError('Unknown native column or invalid source')
            kind = source.get('kind')
            if not isinstance(kind, str) or kind not in fields or set(source) != fields[kind] | {'kind'}:
                raise ValueError('Unsupported generator source kind or fields')
            column = native_columns[name]
            if kind != 'default' and (column.get('attgenerated') or column.get('attidentity') == 'a'):
                raise ValueError('Generated and ALWAYS identity columns must use native defaults')
            if kind == 'constant': _literal(source['value'])
            elif kind == 'sequential': _integer(source['start']); _integer(source['step'])
            elif kind == 'random-integer':
                if not 1 <= _integer(source['max']) - _integer(source['min']) + 1 <= 2**32:
                    raise ValueError('Random integer range must contain 1 to 2^32 values')
            elif kind in {'choice', 'file'}:
                if not isinstance(source['values'], list) or not 1 <= len(source['values']) <= 1000:
                    raise ValueError('Choice/file values require a bounded nonempty list')
                for value in source['values']: _literal(value)
            elif kind == 'existing':
                parent, column, ordering = source['table'], source['column'], source['order_by']
                if (not isinstance(parent, str) or parent not in available or not isinstance(column, str) or
                        not isinstance(ordering, list) or not 1 <= len(ordering) <= 32 or
                        any(not isinstance(key, str) for key in ordering) or len(set(ordering)) != len(ordering)):
                    raise ValueError('Existing source requires a native table, column and ordered column list')
                columns_available = {col['attname'] for col in available[parent]['native'].get('children', {}).get('pg_attribute', [])}
                if not {column, *ordering}.issubset(columns_available):
                    raise ValueError('Unknown existing source or ordering column')
                sample = samples.setdefault(parent, {'columns': set(), 'order_by': ordering})
                if sample['order_by'] != ordering:
                    raise ValueError('Existing references to one table must use the same ordering')
                sample['columns'].add(column)
            elif kind in {'generated', 'returned'}:
                if not isinstance(source['table'], str) or not isinstance(source['column'], str):
                    raise ValueError('Parent source requires an exact table and column')
                required.add(source['table'])
                if kind == 'returned':
                    returned.setdefault(source['table'], set()).add(source['column'])
        selected[identity], dependencies[identity] = entry, required
    for entry in selected.values():
        for source in entry['columns'].values():
            if source['kind'] == 'returned':
                parent = source['table']
                if (parent not in selected or source['column'] not in {
                        column['attname'] for column in available[parent]['native'].get('children', {}).get('pg_attribute', [])}):
                    raise ValueError('Returned parent requires a selected table and native column')
            if source['kind'] == 'generated':
                parent = selected.get(source['table'], {}).get('columns', {}).get(source['column'])
                if not parent or parent['kind'] == 'default':
                    raise ValueError('Generated parent value must have an explicit recipe source')
    order = []
    while dependencies:
        ready = sorted(key for key, required in dependencies.items() if not required)
        if not ready: raise ValueError('Generated-value dependencies contain a cycle')
        order.extend(ready)
        for key in ready: del dependencies[key]
        for required in dependencies.values(): required.difference_update(ready)
    counter = 0
    def random_index(length):
        nonlocal counter
        # SHA-256 counter stream with rejection sampling: stable and unbiased.
        ceiling = 2**256 - 2**256 % length
        while True:
            value = int.from_bytes(hashlib.sha256(f'{recipe["seed"]}:{counter}'.encode()).digest(), 'big')
            counter += 1
            if value < ceiling: return value % length
    sql, generated, size = [], {}, 0
    aliases = {identity: [f'srb_recipe_{index}_{number}' for number in range(selected[identity]['count'])]
               for index, identity in enumerate(order)}
    for index, (identity, sample) in enumerate(sorted(samples.items())):
        sample['alias'] = f'srb_sample_{index}'
        sample['columns'] = {name: f'srb_column_{number}' for number, name in enumerate(sorted(sample['columns']))}
        row = available[identity]
        relation = _qualified(row['native']['schema'], row['native']['catalog_row']['relname'])
        ordering = ', '.join(_identifier(name, 'column') for name in sample['order_by'])
        query = sample['alias'] + ' (' + ', '.join(sample['columns'].values()) + ', srb_position) AS MATERIALIZED (SELECT '
        query += ', '.join(_identifier(name, 'column') for name in sample['columns'])
        query += ', row_number() OVER (ORDER BY ' + ordering + ') FROM ' + relation + ' ORDER BY ' + ordering + ' LIMIT 200)'
        sql.append(query)
        size += len(query.encode()) + 2
    for identity in order:
        entry, row = selected[identity], available[identity]
        relation = _qualified(row['native']['schema'], row['native']['catalog_row']['relname'])
        generated[identity] = []
        table_statements, tuples = [], []
        for number in range(entry['count']):
            values = {}
            for name, source in entry['columns'].items():
                kind = source['kind']
                if kind == 'default': continue
                if kind == 'constant': value = source['value']
                elif kind == 'sequential': value = str(_integer(source['start']) + number * _integer(source['step']))
                elif kind == 'random-integer': value = str(_integer(source['min']) + random_index(_integer(source['max']) - _integer(source['min']) + 1))
                elif kind in {'choice', 'file'}: value = source['values'][number % len(source['values']) if kind == 'file' else random_index(len(source['values']))]
                elif kind == 'generated':
                    values[name] = generated[source['table']][number % len(generated[source['table']])][source['column']]
                    continue
                elif kind == 'returned':
                    parent_aliases = aliases[source['table']]
                    values[name] = '(SELECT ' + _identifier(source['column'], 'column') + ' FROM ' + parent_aliases[number % len(parent_aliases)] + ')'
                    continue
                elif kind == 'existing':
                    sample = samples[source['table']]
                    values[name] = '(SELECT ' + sample['columns'][source['column']] + ' FROM ' + sample['alias']
                    values[name] += ' WHERE srb_position = 1 + ' + str(number) + ' % NULLIF((SELECT count(*) FROM ' + sample['alias'] + '), 0))'
                    continue
                values[name] = _literal(value)
            statement = 'INSERT INTO ' + relation
            if values:
                statement += ' (' + ', '.join(_identifier(name, 'column') for name in values) + ') VALUES (' + ', '.join(values.values()) + ');'
            else: statement += ' DEFAULT VALUES;'
            if returned or samples:
                columns = ', '.join(_identifier(name, 'column') for name in sorted(returned.get(identity, set()))) or '1'
                statement = aliases[identity][number] + ' AS (' + statement[:-1] + ' RETURNING ' + columns + ')'
            size += len(statement.encode()) + 1
            if size > LIMIT: raise ValueError('Generated SQL exceeds 4 MiB')
            table_statements.append(statement)
            if values:
                tuples.append('(' + ', '.join(values.values()) + ')')
            generated[identity].append(values)
        if returned or samples:
            sql.extend(table_statements)
        elif tuples:
            sql.append('INSERT INTO ' + relation + ' (' + ', '.join(_identifier(name, 'column') for name in values) + ') VALUES ' + ',\n'.join(tuples) + ';')
        else:
            inserts = [alias + ' AS (INSERT INTO ' + relation + ' DEFAULT VALUES RETURNING 1)'
                       for alias in aliases[identity]]
            counts = ['((SELECT count(*) FROM ' + alias + '))' for alias in aliases[identity]]
            sql.append('WITH ' + ',\n'.join(inserts) + '\nSELECT sum(n) AS inserted_rows FROM (VALUES ' + ', '.join(counts) + ') AS srb_counts(n);')
    if returned or samples:
        counts = ['((SELECT count(*) FROM ' + alias + '))' for names in aliases.values() for alias in names]
        source = 'WITH ' + ',\n'.join(sql) + '\nSELECT sum(n) AS inserted_rows FROM (VALUES ' + ', '.join(counts) + ') AS srb_counts(n);\n'
    else:
        source = '\n'.join(sql) + '\n'
    if len(source.encode()) > SQL_LIMIT:
        raise ValueError('Generated SQL exceeds the shared SQL file limit of 1 MiB; use a smaller recipe')
    return {'format': 'scratchrobin.postgresql.test-data-script@1', 'source': source,
            'rows': total, 'tables': len(order), 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'algorithm': 'sha256-counter-rejection@1', 'executed': False}
