"""Standalone native routine signatures and bodies, without documentary DDL."""
from ..providers.firebird.character_metadata import identifier, literal, text
from ..providers.firebird.columns import data_type, integer
from ..providers.firebird.column_type_metadata import type_editor_values
from ..providers.firebird.packages import source
from . import firebird_domain_plan as domains
from .firebird_view_plan import dependencies

FIELDS = {'parameters', 'metadata_source', 'engine_name', 'entrypoint', 'sql_security', 'description'}
DERIVED = {'valid_blr', 'procedure_type', 'function_type', 'return_argument', 'legacy', 'private_flag'}
NUMERIC_TYPES = {'field_type', 'field_sub_type', 'field_scale', 'field_precision', 'character_length', 'segment_length'}
PARAMETER_FIELDS = domains.TYPE_FIELDS | {'name', 'mode', 'position', 'domain', 'not_null',
    'default_source', 'description', 'mechanism', 'argument_mechanism', 'relation_name', 'field_name', 'return_value', 'type_sql'}


def flag(value, label, nullable=False):
    if value is None:
        return None if nullable else '0'
    if type(value) is bool:
        return '1' if value else '0'
    if isinstance(value, str) and value.upper() in {'TRUE', 'FALSE'}:
        return '1' if value.upper() == 'TRUE' else '0'
    if type(value) not in (str, int) or str(value) not in {'0', '1'}:
        raise ValueError(label + ' requires a native flag')
    return str(value)


def type_facts(native):
    result = {key: int(integer(0 if native.get(key) is None else native[key], -32768, 65535, key))
              for key in NUMERIC_TYPES}
    if result['field_type'] in {7, 8, 16, 26} and result['field_sub_type'] == 0:
        precision = {7: 4, 8: 9, 16: 18, 26: 38}[result['field_type']]
        if result['field_precision'] not in {0, precision}:
            raise ValueError('Plain integer parameter has inconsistent precision')
        result['field_precision'] = 0
    if result['field_type'] in {24, 25} and not result['field_precision']:
        result['field_precision'] = 16 if result['field_type'] == 24 else 34
    for key in ('character_set', 'collation'):
        result[key] = native.get(key)
        if result[key] is not None:
            identifier(result[key])
    return result


def parameter(native, kind):
    if not isinstance(native, dict) or set(native) - PARAMETER_FIELDS:
        raise ValueError('Unknown native routine parameter properties')
    position = int(integer(native.get('position'), 0, 32766, 'Parameter position'))
    mode = native.get('mode') if kind == 'procedure' else (
        'return' if flag(native.get('return_value'), 'Return identity') == '1' else 'input')
    if mode not in ({'input', 'output'} if kind == 'procedure' else {'input', 'return'}):
        raise ValueError('Unknown native parameter mode')
    name = native.get('name')
    if mode != 'return':
        identifier(name)
    elif name is not None:
        raise ValueError('Function return value cannot have a parameter name')
    domain = native.get('domain')
    if domain is not None:
        identifier(domain)
        if domain.startswith('RDB$'):
            domain = None
    mechanism = native.get('argument_mechanism')
    if mechanism is None:
        mechanism = native.get('mechanism')
    mechanism = int(integer(0 if mechanism is None else mechanism, 0, 1, 'Parameter type mechanism'))
    relation, field = native.get('relation_name'), native.get('field_name')
    if (relation is None) != (field is None):
        raise ValueError('TYPE OF COLUMN requires relation and field identity')
    facts = type_facts(native)
    if relation is not None:
        if mechanism != 1:
            raise ValueError('Column reference requires native TYPE OF mechanism')
        typed = 'TYPE OF COLUMN ' + identifier(relation) + '.' + identifier(field)
    else:
        if mechanism == 1 and domain is None:
            raise ValueError('TYPE OF requires an explicit named domain or column')
        descriptor = type_editor_values({**facts, 'domain': domain})
        if not descriptor:
            raise ValueError('Routine parameter type cannot be rendered without loss')
        typed = ('TYPE OF ' if mechanism else '') + data_type(descriptor)
    nullable = flag(native.get('not_null'), 'Parameter nullability')
    declaration = (identifier(name) + ' ' if mode != 'return' else '') + typed
    if nullable == '1':
        declaration += ' NOT NULL'
    if facts['collation'] is not None:
        declaration += ' COLLATE ' + identifier(facts['collation'])
    default = domains.clause(native.get('default_source'), 'DEFAULT')
    if default is not None:
        if mode != 'input':
            raise ValueError('Only input parameters can declare a default')
        declaration += ' ' + default + '\n'
    description = native.get('description')
    if description is not None:
        description = text(description, 'Parameter comment') or None
    if str(native.get('dimensions') or '0') != '0' or native.get('array_dimensions'):
        raise ValueError('Array parameter layout requires an admitted native routine contract')
    return {'name': name, 'mode': mode, 'position': position, 'domain': domain,
            'mechanism': mechanism, 'relation_name': relation, 'field_name': field,
            'type': facts, 'not_null': nullable, 'default_source': default,
            'description': description, 'declaration': declaration}


def model(row):
    native, kind = row['native'], row['kind']
    if native.get('package'):
        raise ValueError('Packaged members require the package header/body workflow')
    raw = native.get('parameters', [])
    if not isinstance(raw, list) or len(raw) > 1024:
        raise ValueError('Routine parameters require a bounded native array')
    parameters = [parameter(item, kind) for item in raw]
    names = [item['name'] for item in parameters if item['name'] is not None]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate native parameter name')
    for mode in ('input', 'output') if kind == 'procedure' else ('input', 'return'):
        positions = sorted(item['position'] for item in parameters if item['mode'] == mode)
        start = 1 if kind == 'function' and mode == 'input' else 0
        if positions != list(range(start, start + len(positions))) or (mode == 'return' and len(positions) != 1):
            raise ValueError('Native parameter positions must be contiguous with one function return')
    parameters.sort(key=lambda item: (item['mode'], item['position']))
    engine, entrypoint = native.get('engine_name'), native.get('entrypoint')
    if engine is not None:
        identifier(engine)
    if entrypoint is not None:
        entrypoint = text(entrypoint, 'External entrypoint')
    security = flag(native.get('sql_security'), 'Routine SQL SECURITY', True)
    body = native.get('metadata_source')
    if engine:
        if security is not None:
            raise ValueError('External routine clauses do not admit SQL SECURITY')
        body = None if body is None else text(body, 'External routine payload')
    else:
        if entrypoint:
            raise ValueError('External entrypoint requires its engine')
        body = source(body, 'Native routine body')
    result = {'parameters': parameters, 'metadata_source': body, 'sql_security': security,
              'engine_name': engine, 'entrypoint': entrypoint}
    if kind == 'function':
        result['deterministic'] = flag(native.get('deterministic'), 'Function determinism')
    return result


def context(kind, after, current):
    databases = [row for row in current['rows'].values() if row['kind'] == 'database']
    observations = databases[0]['native'].get('catalog_observations', []) if len(databases) == 1 else []
    for section in (kind + ' objects', 'procedure parameters' if kind == 'procedure' else 'function arguments'):
        if not any(item.get('section') == section and item.get('available') is True for item in observations):
            raise ValueError('Routine planning requires available catalog observation: ' + section)
    for item in after['parameters']:
        reference = None
        if item['relation_name'] is not None:
            matches = [row for row in current['rows'].values() if row['kind'] == 'column' and
                       row['path'] == [item['relation_name'], item['field_name']]]
            if len(matches) != 1:
                raise ValueError('TYPE OF COLUMN target must be observed')
            reference = matches[0]['native']
        elif item['domain'] is not None:
            matches = [row for row in current['rows'].values() if row['kind'] == 'domain' and row['path'] == [item['domain']]]
            if len(matches) != 1:
                raise ValueError('Routine parameter domain must be observed')
            reference = matches[0]['native']
        if reference is not None:
            expected = type_facts(reference)
            if any(item['type'][key] != expected[key] for key in expected if key != 'collation'):
                raise ValueError('Expanded parameter type disagrees with its native reference')
        else:
            domains.creation_model({'native': {**item['type'], 'dimensions': 0}}, current)
        if item['type']['character_set'] is not None and item['type']['collation'] is None:
            raise ValueError('Character parameters require an explicit observed collation')
    return dependencies(current)


def statements(kind, before, after):
    name = identifier(after['name'])
    declaration_fields = FIELDS - {'description'} | ({'deterministic'} if kind == 'function' else set())
    changed = before is None or any(before[key] != after[key] for key in declaration_fields)
    if not changed:
        return []
    inputs = [item['declaration'] for item in after['parameters'] if item['mode'] == 'input']
    sql = ('CREATE' if before is None else 'ALTER') + ' ' + kind.upper() + ' ' + name
    if inputs or kind == 'function':
        sql += ' (' + ', '.join(inputs) + ')'
    if kind == 'function':
        sql += ' RETURNS ' + next(item['declaration'] for item in after['parameters'] if item['mode'] == 'return')
        if after['deterministic'] == '1':
            sql += '\nDETERMINISTIC'
    else:
        outputs = [item['declaration'] for item in after['parameters'] if item['mode'] == 'output']
        if outputs:
            sql += ' RETURNS (' + ', '.join(outputs) + ')'
    if after['engine_name']:
        sql += '\nEXTERNAL'
        if after['entrypoint']:
            sql += ' NAME ' + literal(after['entrypoint'])
        sql += ' ENGINE ' + identifier(after['engine_name'])
        if after['metadata_source'] is not None:
            sql += '\nAS ' + literal(after['metadata_source'])
    else:
        if after['sql_security'] is not None:
            sql += '\nSQL SECURITY ' + ('DEFINER' if after['sql_security'] == '1' else 'INVOKER')
        sql += '\nAS\n' + after['metadata_source']
    result = [sql]
    for item in after['parameters']:
        if item['name'] is not None:
            result.append('COMMENT ON ' + kind.upper() + ' PARAMETER ' + name + '.' + identifier(item['name']) +
                          ' IS ' + ('NULL' if item['description'] is None else literal(item['description'])))
    return result
