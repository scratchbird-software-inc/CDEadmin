"""Bounded, nonexecuting DuckDB 1.5.2 native test-data recipes."""

import base64
import hashlib
import json
import re

FORMAT = 'scratchrobin.duckdb.test-data@1'
MAX_RECIPE = 4 * 1024 * 1024
MAX_SQL = 1024 * 1024


def _quote(name):
    if not isinstance(name, str) or not name or '\x00' in name or len(name.encode()) > 256:
        raise ValueError('Invalid native DuckDB identifier')
    return '"' + name.replace('"', '""') + '"'


def _integer(value):
    if not isinstance(value, str) or not re.fullmatch(r'[+-]?[0-9]{1,19}', value):
        raise ValueError('Integer source requires an exact 64-bit decimal string')
    number = int(value)
    if not -(2**63) <= number < 2**63:
        raise ValueError('Integer source exceeds signed 64-bit range')
    return number


def _literal(value):
    if value is None:
        return 'NULL'
    if type(value) is bool:
        return 'TRUE' if value else 'FALSE'
    if type(value) is int and abs(value) <= 2**53 - 1:
        return str(value)
    if isinstance(value, str):
        if '\x00' in value or len(value.encode()) > MAX_SQL:
            raise ValueError('Invalid or oversized native text value')
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, dict) and set(value) == {'type', 'value'} and isinstance(value['value'], str):
        kind, raw = value['type'], value['value']
        if len(raw.encode()) > MAX_SQL:
            raise ValueError('Typed value exceeds 1 MiB')
        if kind == 'integer':
            return str(_integer(raw))
        if kind == 'decimal' and re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)', raw):
            return raw
        if kind == 'binary':
            try:
                binary = base64.b64decode(raw, validate=True)
            except (ValueError, base64.binascii.Error):
                raise ValueError('Invalid base64 binary value') from None
            return 'from_base64(' + _literal(base64.b64encode(binary).decode('ascii')) + ')'
    raise ValueError('Use exact native text, safe integers or explicit integer/decimal/binary values')


def _tables(model):
    if model['provenance'].get('mapping') != 'scratchrobin.duckdb.catalog@1':
        raise ValueError('Native DuckDB catalog capture is required')
    roots = [row for row in model['rows'].values() if row['kind'] == 'database' and row['system'] == 'false']
    if len(roots) != 1:
        raise ValueError('One exact native file root is required')
    catalog = roots[0]['name']
    return {identity: row for identity, row in model['rows'].items()
            if row['kind'] == 'table' and row['system'] == 'false' and
            row['path'][:1] == [catalog] and len(row['path']) == 3 and
            row['native'].get('catalog_metadata', {}).get('temporary') is False}


def template(model):
    available = _tables(model)
    return {'format': FORMAT, 'executed': False,
        'scope': {key: model['provenance'][key] for key in ('endpoint_id', 'database_target_id')},
        'tables': [{'resource_id': identity, 'catalog': row['path'][0], 'schema': row['path'][1],
            'name': row['name'], 'columns': [{'name': col['name'], 'data_type': col.get('data_type'),
                'nullable': col.get('nullable'), 'has_default': col.get('default') is not None}
                for col in row['native'].get('columns', [])]}
            for identity, row in sorted(available.items())]}


def generate(model, recipe):
    if (not isinstance(recipe, dict) or set(recipe) != {'format', 'scope', 'seed', 'tables'} or
            recipe['format'] != FORMAT or type(recipe['seed']) is not int or
            not 0 <= recipe['seed'] < 2**32 or not isinstance(recipe['tables'], list) or
            not 1 <= len(recipe['tables']) <= 32):
        raise ValueError('Invalid DuckDB test-data recipe')
    scope = {key: model['provenance'][key] for key in ('endpoint_id', 'database_target_id')}
    if recipe['scope'] != scope:
        raise ValueError('Recipe belongs to another endpoint or registered file')
    if len(json.dumps(recipe, allow_nan=False).encode()) > MAX_RECIPE:
        raise ValueError('Recipe exceeds 4 MiB')
    available, seen, lines, total = _tables(model), set(), [], 0
    lines.extend(['-- DuckDB native test data; review in the shared Query Tool.',
        '-- No SQL was executed. Native defaults, constraints and permissions apply.',
        '-- Execution transaction and file effects are owned by the Query Tool.'])
    size = sum(len(line.encode()) + 1 for line in lines)
    counter = 0

    def random_index(length):
        nonlocal counter
        ceiling = 2**256 - 2**256 % length
        while True:
            value = int.from_bytes(hashlib.sha256(f'{recipe["seed"]}:{counter}'.encode()).digest(), 'big')
            counter += 1
            if value < ceiling:
                return value % length

    for entry in recipe['tables']:
        if not isinstance(entry, dict) or set(entry) != {'table', 'count', 'columns'}:
            raise ValueError('Invalid native table recipe')
        identity, count, sources = entry['table'], entry['count'], entry['columns']
        if (not isinstance(identity, str) or identity not in available or identity in seen or
                type(count) is not int or not 1 <= count <= 1000 or not isinstance(sources, dict)):
            raise ValueError('Unknown or duplicate native table, invalid count or sources')
        seen.add(identity); total += count
        if total > 5000:
            raise ValueError('Recipe exceeds 5000 rows')
        row = available[identity]
        columns = {column['name']: column for column in row['native'].get('columns', [])}
        if len(columns) != len(row['native'].get('columns', [])):
            raise ValueError('Native column names are ambiguous')
        for name, source in sources.items():
            if name not in columns or not isinstance(source, dict):
                raise ValueError('Unknown native column or invalid source')
            kind = source.get('kind')
            shape = {'default': set(), 'constant': {'value'}, 'sequential': {'start', 'step'},
                'random-integer': {'min', 'max'}, 'choice': {'values'}, 'file': {'values'}}.get(kind)
            if shape is None or set(source) != shape | {'kind'}:
                raise ValueError('Unsupported native generator or fields')
            if kind == 'constant': _literal(source['value'])
            if kind == 'sequential': _integer(source['start']); _integer(source['step'])
            if kind == 'random-integer' and not 1 <= _integer(source['max']) - _integer(source['min']) + 1 <= 2**32:
                raise ValueError('Random range requires 1 to 2^32 values')
            if kind in {'choice', 'file'}:
                if not isinstance(source['values'], list) or not 1 <= len(source['values']) <= 1000:
                    raise ValueError('Choice/file values require 1 to 1000 entries')
                for value in source['values']: _literal(value)
        target = '.'.join(_quote(part) for part in row['path'])
        for position in range(count):
            values = {}
            for name, source in sorted(sources.items()):
                kind = source['kind']
                if kind == 'default': continue
                if kind == 'constant': value = _literal(source['value'])
                elif kind == 'sequential':
                    number = _integer(source['start']) + position * _integer(source['step'])
                    if not -(2**63) <= number < 2**63: raise ValueError('Sequence exceeds signed 64-bit range')
                    value = str(number)
                elif kind == 'random-integer':
                    low, high = _integer(source['min']), _integer(source['max'])
                    value = str(low + random_index(high - low + 1))
                else:
                    choices = source['values']
                    value = _literal(choices[random_index(len(choices))] if kind == 'choice'
                        else choices[position % len(choices)])
                values[name] = value
            statement = (('INSERT INTO ' + target + ' (' + ', '.join(_quote(name) for name in values) +
                ') VALUES (' + ', '.join(values.values()) + ');') if values else
                'INSERT INTO ' + target + ' DEFAULT VALUES;')
            size += len(statement.encode()) + 1
            if size > MAX_SQL:
                raise ValueError('Generated native SQL exceeds 1 MiB')
            lines.append(statement)
    source = '\n'.join(lines) + '\n'
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected generated SQL') from None
    if len(statements) != total or any(statement.type != duckdb.StatementType.INSERT for statement in statements):
        raise ValueError('Generated SQL has an unexpected native statement boundary')
    return {'format': FORMAT, 'source': source, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'rows': total, 'tables': len(seen), 'executed': False,
        'warnings': ['Generation performs no writes; review native types, defaults, constraints and privileges before execution.']}
