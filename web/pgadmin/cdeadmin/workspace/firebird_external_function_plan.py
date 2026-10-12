"""Exact legacy UDF declarations, distinct from PSQL/UDR signatures."""
from ..providers.firebird import external_functions as udf
from ..providers.firebird.columns import integer
from ..providers.firebird.column_type_metadata import type_editor_values
from .firebird_routine_plan import PARAMETER_FIELDS, type_facts

FIELDS = {'parameters', 'return_argument', 'module_name', 'entrypoint', 'description'}
DERIVED = {'legacy'}
WARNING = udf.WARNING
LENGTHS = {7: 2, 8: 4, 16: 8, 26: 16, 10: 4, 27: 8, 12: 4,
           13: 4, 35: 8, 23: 1, 24: 8, 25: 16, 28: 8, 29: 12, 261: 8}


def descriptor(facts):
    if facts['field_type'] == 40:
        return {'data_type': 'CSTRING', 'length': facts['character_length'],
                'character_set': facts['character_set']}
    value = type_editor_values(facts)
    if value.get('data_type') == 'BLOB':
        value = {'data_type': 'BLOB'}
    if not value:
        raise ValueError('Legacy UDF type cannot be rendered without loss')
    udf.type_sql(value)
    return value


def parameter(raw, returned):
    if not isinstance(raw, dict) or set(raw) - PARAMETER_FIELDS:
        raise ValueError('Unknown legacy UDF parameter properties')
    if any(raw.get(key) not in (None, '', 0) for key in (
            'name', 'mode', 'domain', 'not_null', 'default_source', 'description',
            'argument_mechanism', 'relation_name', 'field_name', 'dimensions')) or raw.get('array_dimensions'):
        raise ValueError('Legacy UDF parameters cannot carry PSQL signature properties')
    position = int(integer(raw.get('position'), 0, 15, 'UDF parameter position'))
    if raw.get('return_value') is not None and raw['return_value'] is not (position == returned):
        raise ValueError('UDF return identity disagrees with its position')
    facts = type_facts(raw)
    facts['field_length'] = int(integer(raw.get('field_length'), 1, 32767, 'UDF physical length'))
    kind, subtype, scale = (facts[key] for key in ('field_type', 'field_sub_type', 'field_scale'))
    if kind not in {7, 8, 16, 26} and (subtype not in ({0, 1} if kind in {14, 37} else {0}) or scale != 0):
        raise ValueError('Unsupported legacy UDF subtype or scale')
    if kind in LENGTHS and facts['field_length'] != LENGTHS[kind]:
        raise ValueError('Legacy UDF physical length disagrees with its native type')
    if kind in {7, 8, 16, 26} and subtype in {1, 2}:
        precision = facts['field_precision']
        expected = 7 if subtype == 1 and precision <= 4 else 8 if precision <= 9 else 16 if precision <= 18 else 26
        if kind != expected:
            raise ValueError('Legacy UDF precision and physical numeric type disagree')
    elif kind in {24, 25}:
        if facts['field_precision'] != (16 if kind == 24 else 34):
            raise ValueError('Legacy UDF DECFLOAT precision disagrees with its type')
    elif facts['field_precision']:
        raise ValueError('Declared precision does not apply to this legacy UDF type')
    if kind in {14, 37} and subtype == 1 and facts['character_set'] != 'OCTETS':
        raise ValueError('Legacy UDF binary types require OCTETS')
    if kind not in {14, 37, 40} and (facts['character_length'] or facts['character_set'] or facts['collation']):
        raise ValueError('Character metadata does not apply to this UDF type')
    if facts['segment_length']:
        raise ValueError('Legacy UDF BLOB grammar has no segment size')
    descriptor(facts)
    mechanism = int(integer(raw.get('mechanism'), -2, 5, 'UDF mechanism'))
    permitted = {-2, -1, 0, 1, 2} if position == 0 else {1, 2, 3, 4, 5}
    if mechanism not in permitted or (mechanism == 3) != (kind == 261):
        raise ValueError('Legacy UDF mechanism does not match its argument role/type')
    return {'position': position, 'mechanism': mechanism, 'type': facts}


def model(row):
    native = row['native']
    if native.get('package') or native.get('engine_name') or str(native.get('legacy', 1)) != '1':
        raise ValueError('Legacy UDF planning requires a standalone legacy declaration')
    returned = int(integer(native.get('return_argument'), 0, 15, 'UDF return position'))
    raw = native.get('parameters')
    if not isinstance(raw, list) or not 1 <= len(raw) <= 16:
        raise ValueError('Legacy UDF requires a complete bounded parameter signature')
    parameters = sorted((parameter(item, returned) for item in raw), key=lambda item: item['position'])
    positions = [item['position'] for item in parameters]
    if positions != list(range(0 if returned == 0 else 1, len(parameters) + (0 if returned == 0 else 1))) or returned not in positions:
        raise ValueError('Legacy UDF parameter positions must be unique and contiguous')
    result = {'parameters': parameters, 'return_argument': returned}
    for key in ('module_name', 'entrypoint'):
        udf.external_name(native.get(key), key)
        result[key] = native[key]
    # Validate role-specific grammar even for comment-only models.
    declaration({'name': row['name'], **result})
    return result


def declaration(after):
    draft = {key: after[key] for key in ('name', 'module_name', 'entrypoint')}
    arguments = []
    for item in after['parameters']:
        value = descriptor(item['type'])
        if item['position'] == 0:
            draft.update({'return_' + key: value for key, value in value.items()})
            draft['return_mechanism'] = {0: 'VALUE', 1: 'REFERENCE', 2: 'DESCRIPTOR',
                                         -1: 'FREE_IT', -2: 'DESCRIPTOR_FREE_IT'}[item['mechanism']]
        else:
            arguments.append({**value, 'mechanism': {1: 'REFERENCE', 2: 'DESCRIPTOR',
                3: 'REFERENCE', 4: 'SCALAR_ARRAY', 5: 'NULL'}[item['mechanism']]})
    draft['arguments'] = arguments
    if after['return_argument']:
        draft.update(return_mode='PARAMETER', return_parameter=after['return_argument'])
    return udf.compile_operation('create', draft)


def context(after, current):
    databases = [row for row in current['rows'].values() if row['kind'] == 'database']
    observations = databases[0]['native'].get('catalog_observations', []) if len(databases) == 1 else []
    for section in ('external-function objects', 'function arguments'):
        if not any(item.get('section') == section and item.get('available') is True for item in observations):
            raise ValueError('Legacy UDF planning requires available catalog observation: ' + section)
    dependencies = set()
    for parameter in after['parameters']:
        facts = parameter['type']
        if facts['field_type'] not in {14, 37, 40}: continue
        for section in ('character-set objects', 'collation objects'):
            if not any(item.get('section') == section and item.get('available') is True for item in observations):
                raise ValueError('Legacy UDF planning requires available catalog observation: ' + section)
        matches = [row for row in current['rows'].values() if row['kind'] == 'character-set' and row['name'] == facts['character_set']]
        if len(matches) != 1 or matches[0]['native'].get('default_collation') != facts['collation']:
            raise ValueError('Legacy UDF requires the observed character set default collation')
        charset = matches[0]
        width = int(integer(charset['native'].get('bytes_per_character'), 1, 8, 'Character width'))
        if facts['field_length'] != facts['character_length'] * width:
            raise ValueError('Legacy UDF character length does not match native byte width')
        dependencies.add(charset['resource_id'])
    return sorted(dependencies)


def statements(before, after):
    if before is None: return declaration(after)
    if any(before[key] != after[key] for key in ('parameters', 'return_argument')):
        raise ValueError('Legacy UDF signature changes require explicit removal/recreation')
    changed = [key for key in ('module_name', 'entrypoint') if before[key] != after[key]]
    if not changed: return []
    return udf.compile_operation('alter', {'alter_target': 'BOTH' if len(changed) == 2 else
        {'module_name': 'MODULE_NAME', 'entrypoint': 'ENTRY_POINT'}[changed[0]],
        **{key: after[key] for key in changed}}, {'display_name': after['name']})
