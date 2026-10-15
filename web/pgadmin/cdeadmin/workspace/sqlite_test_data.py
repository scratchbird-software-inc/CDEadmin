"""Bounded SQLite test-data recipes that generate SQL without executing it."""

import base64
import hashlib
import json
import re
import sqlite3

FORMAT = 'scratchrobin.sqlite.test-data@1'
MAX_RECIPE_BYTES = 4 * 1024 * 1024
MAX_SQL_BYTES = 1024 * 1024


def _quote(name):
    if (not isinstance(name, str) or not name or '\x00' in name or
            len(name.encode('utf8')) > 256):
        raise ValueError('Invalid SQLite identifier')
    return '"' + name.replace('"', '""') + '"'


def _integer(value):
    if not isinstance(value, str) or not re.fullmatch(r'[+-]?[0-9]{1,19}', value):
        raise ValueError('SQLite integer requires an exact decimal string')
    number = int(value)
    if not -(2**63) <= number < 2**63:
        raise ValueError('SQLite integer exceeds signed 64-bit range')
    return number


def _literal(value):
    if value is None:
        return 'NULL'
    if type(value) is bool:
        return '1' if value else '0'
    if type(value) is int and abs(value) <= 2**53 - 1:
        return str(value)
    if isinstance(value, str):
        if '\x00' in value or len(value.encode('utf8')) > MAX_SQL_BYTES:
            raise ValueError('Invalid or oversized SQLite text')
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, dict) and set(value) == {'type', 'value'} and isinstance(value['value'], str):
        kind, raw = value['type'], value['value']
        if kind == 'integer':
            return str(_integer(raw))
        if kind == 'binary':
            try:
                binary = base64.b64decode(raw, validate=True)
            except (ValueError, base64.binascii.Error):
                raise ValueError('Invalid base64 SQLite binary value') from None
            if len(binary) > MAX_SQL_BYTES // 2:
                raise ValueError('SQLite binary value exceeds SQL budget')
            return "X'" + binary.hex() + "'"
    raise ValueError('Use SQLite text, safe integers, or explicit integer/binary values')


def _tables(model):
    if model['provenance'].get('mapping') != 'scratchrobin.sqlite.catalog@1':
        raise ValueError('Native SQLite catalog capture is required')
    roots = [row for row in model['rows'].values()
             if row['kind'] == 'database' and row['name'] == 'main' and row['system'] == 'false']
    if len(roots) != 1:
        raise ValueError('One exact registered SQLite file root is required')
    return {identity: row for identity, row in model['rows'].items()
            if row['kind'] == 'table' and row['system'] == 'false' and
            len(row['path']) == 2 and row['path'][0] == 'main' and
            row['native'].get('catalog_metadata', {}).get('table_list_type') == 'table'}


def template(model):
    tables = _tables(model)
    return {'format': FORMAT, 'executed': False,
        'scope': {key: model['provenance'][key] for key in ('endpoint_id', 'database_target_id')},
        'tables': [{'resource_id': identity, 'schema': row['path'][0], 'name': row['name'],
            'columns': [{'name': column['name'], 'data_type': column.get('data_type'),
                'nullable': column.get('nullable'), 'has_default': column.get('default') is not None,
                'hidden': column.get('hidden', 0)}
                for column in row['native'].get('columns', []) if not column.get('hidden')]}
            for identity, row in sorted(tables.items())]}


def generate(model, recipe):
    if (not isinstance(recipe, dict) or set(recipe) != {'format', 'scope', 'seed', 'tables'} or
            recipe['format'] != FORMAT or type(recipe['seed']) is not int or
            not 0 <= recipe['seed'] < 2**32 or not isinstance(recipe['tables'], list) or
            not 1 <= len(recipe['tables']) <= 32):
        raise ValueError('Invalid SQLite test-data recipe')
    scope = {key: model['provenance'][key] for key in ('endpoint_id', 'database_target_id')}
    if recipe['scope'] != scope:
        raise ValueError('Recipe belongs to another endpoint or registered file')
    if len(json.dumps(recipe, allow_nan=False).encode('utf8')) > MAX_RECIPE_BYTES:
        raise ValueError('SQLite recipe exceeds 4 MiB')
    available, seen, lines, total = _tables(model), set(), [
        '-- SQLite native test data; review in the shared Query Tool.',
        '-- No SQL was executed. Native constraints and defaults apply.',
    ], 0
    counter = 0
    source_bytes = sum(len(line.encode('utf8')) + 1 for line in lines)

    def random_index(length):
        nonlocal counter
        ceiling = 2**256 - 2**256 % length
        while True:
            value = int.from_bytes(hashlib.sha256(
                f'{recipe["seed"]}:{counter}'.encode()).digest(), 'big')
            counter += 1
            if value < ceiling:
                return value % length

    for entry in recipe['tables']:
        if not isinstance(entry, dict) or set(entry) != {'table', 'count', 'columns'}:
            raise ValueError('Invalid SQLite table recipe')
        identity, count, sources = entry['table'], entry['count'], entry['columns']
        if (not isinstance(identity, str) or identity not in available or identity in seen or
                type(count) is not int or not 1 <= count <= 1000 or not isinstance(sources, dict)):
            raise ValueError('Unknown, duplicate or oversized SQLite table recipe')
        seen.add(identity)
        total += count
        if total > 5000:
            raise ValueError('SQLite recipe exceeds 5,000 rows')
        row = available[identity]
        columns = {column['name']: column for column in row['native'].get('columns', [])}
        if len(columns) != len(row['native'].get('columns', [])):
            raise ValueError('Ambiguous native SQLite columns')
        for name, source in sources.items():
            if name not in columns or not isinstance(source, dict) or columns[name].get('hidden'):
                raise ValueError('Unknown or generated SQLite column')
            kind = source.get('kind')
            shape = {'default': set(), 'constant': {'value'}, 'sequential': {'start', 'step'},
                'random-integer': {'min', 'max'}, 'choice': {'values'}, 'file': {'values'}}.get(kind)
            if shape is None or set(source) != shape | {'kind'}:
                raise ValueError('Unsupported SQLite generator or fields')
            if kind == 'constant':
                _literal(source['value'])
            if kind == 'sequential':
                _integer(source['start']); _integer(source['step'])
            if kind == 'random-integer' and not 1 <= _integer(source['max']) - _integer(source['min']) + 1 <= 2**32:
                raise ValueError('SQLite random range requires 1 to 2^32 values')
            if kind in {'choice', 'file'}:
                if not isinstance(source['values'], list) or not 1 <= len(source['values']) <= 1000:
                    raise ValueError('SQLite choice/file values require 1 to 1000 entries')
                for value in source['values']:
                    _literal(value)
        target = '.'.join(_quote(part) for part in row['path'])
        for position in range(count):
            values = {}
            for name, source in sorted(sources.items()):
                kind = source['kind']
                if kind == 'default':
                    continue
                if kind == 'constant':
                    value = _literal(source['value'])
                elif kind == 'sequential':
                    number = _integer(source['start']) + position * _integer(source['step'])
                    if not -(2**63) <= number < 2**63:
                        raise ValueError('SQLite sequence exceeds signed 64-bit range')
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
            if not sqlite3.complete_statement(statement):
                raise ValueError('SQLite rejected generated statement boundary')
            lines.append(statement)
            source_bytes += len(statement.encode('utf8')) + 1
            if source_bytes > MAX_SQL_BYTES:
                raise ValueError('Generated SQLite SQL exceeds 1 MiB')
    source = '\n'.join(lines) + '\n'
    return {'format': FORMAT, 'source': source,
        'source_sha256': hashlib.sha256(source.encode('utf8')).hexdigest(),
        'rows': total, 'tables': len(seen), 'executed': False,
        'warnings': ['Generation performs no writes; review native types, constraints and file effects before execution.']}
