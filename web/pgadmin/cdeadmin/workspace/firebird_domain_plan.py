"""Domain properties and canonical scalar creation through native types."""
import re

from ..providers.firebird.character_metadata import identifier, text
from ..providers.firebird_expressions import index_expression
from ..providers.firebird.column_type_metadata import type_editor_values
from ..providers.firebird.columns import data_type, integer

TYPE_FIELDS = {'field_type', 'field_sub_type', 'field_length', 'field_scale',
               'field_precision', 'character_length', 'segment_length',
               'character_set', 'collation', 'dimensions', 'array_dimensions'}

FIELDS = {'default_source', 'validation_source', 'not_null', 'description'}


def clause(value, keyword):
    if value is None:
        return None
    value = text(value, 'Domain ' + keyword).strip()
    match = re.fullmatch(keyword + r'\b\s*(.+)', value, re.IGNORECASE | re.DOTALL)
    if not match:
        raise ValueError('Domain source requires ' + keyword + ' and its expression')
    index_expression(match.group(1), 'Domain ' + keyword,
                     require_outer=keyword == 'CHECK',
                     forbidden_top_level={'SET', 'DROP', 'ADD', 'TO', 'TYPE', 'NOT', 'CHECK', 'COLLATE'} if keyword == 'DEFAULT' else ())
    return value


def model(row):
    native = row['native']
    for key in ('default_source', 'validation_source', 'not_null'):
        if key not in native:
            raise ValueError('Exact domain metadata is missing: ' + key)
    flag = native['not_null']
    if native.get('dimensions') not in (None, 0, '0') and native['default_source'] is not None:
        raise ValueError('Firebird array domains cannot have defaults')
    if flag is not None and (type(flag) not in (str, int) or str(flag) not in ('0', '1')):
        raise ValueError('Domain nullability must be a native zero/one flag')
    return {'default_source': clause(native['default_source'], 'DEFAULT'),
            'validation_source': clause(native['validation_source'], 'CHECK'),
            'not_null': '0' if flag is None else str(flag)}


def context(current):
    databases = [row for row in current['rows'].values() if row['kind'] == 'database']
    observations = databases[0]['native'].get('catalog_observations', []) if len(databases) == 1 else []
    evidence = [item for item in observations if item.get('section') == 'domain objects']
    if len(evidence) != 1 or evidence[0].get('available') is not True:
        raise ValueError('Domain planning requires available catalog observation: domain objects')



def array_layout(native, current):
    count = native.get('dimensions')
    count = int(integer(0 if count is None else count, 0, 16, 'Array dimension count'))
    bounds = native.get('array_dimensions', [])
    if not isinstance(bounds, list) or len(bounds) != count:
        raise ValueError('Array domain creation requires exact qualified bounds')
    if not count:
        return []
    databases = [row for row in current['rows'].values() if row['kind'] == 'database']
    observations = databases[0]['native'].get('catalog_observations', []) if len(databases) == 1 else []
    evidence = [item for item in observations if item.get('section') == 'array dimensions']
    if len(evidence) != 1 or evidence[0].get('available') is not True:
        raise ValueError('Array domain creation requires available array dimensions observation')
    result = []
    for position, bound in enumerate(bounds):
        if not isinstance(bound, dict) or set(bound) != {'position', 'lower_bound', 'upper_bound'}:
            raise ValueError('Array dimension requires position, lower_bound and upper_bound')
        if int(integer(bound['position'], 0, 15, 'Array dimension position')) != position:
            raise ValueError('Array dimension positions must be contiguous and ordered')
        lower = integer(bound['lower_bound'], -2147483648, 2147483647, 'Array lower bound')
        upper = integer(bound['upper_bound'], -2147483648, 2147483647, 'Array upper bound')
        if int(lower) >= int(upper):
            raise ValueError('Array upper bound must exceed lower bound')
        result.append({'lower': lower, 'upper': upper})
    return result


def render_type(typed):
    rendered = data_type(typed['descriptor'])
    if typed.get('dimensions'):
        base, separator, charset = rendered.partition(' CHARACTER SET ')
        rendered = base + '[' + ', '.join(item['lower'] + ':' + item['upper']
            for item in typed['dimensions']) + ']' + (separator + charset if separator else '')
    return rendered


def creation_model(row, current):
    native = row['native']
    for key in ('field_type', 'field_sub_type', 'field_scale', 'dimensions'):
        if key not in native:
            raise ValueError('Exact scalar domain metadata is missing: ' + key)
    def number(key, fallback=0):
        value = native.get(key)
        return int(integer(fallback if value is None else value, -32768, 65535, key))
    kind, subtype, scale = number('field_type'), number('field_sub_type'), number('field_scale')
    dimensions = array_layout(native, current)
    if dimensions and kind == 261:
        raise ValueError('Firebird array elements cannot be BLOBs')
    descriptor = type_editor_values(native)
    if not descriptor or descriptor.get('data_type') == 'DOMAIN':
        raise ValueError('Domain native type cannot be rendered without loss')
    if kind in (7, 8, 16, 26) and subtype in (1, 2):
        precision = number('field_precision')
        expected = (7 if subtype == 1 and precision <= 4 else
                    8 if precision <= 9 else 16 if precision <= 18 else 26)
        if kind != expected:
            raise ValueError('Numeric precision and physical storage type disagree')
    elif kind not in (14, 37, 261) and (subtype != 0 or scale != 0):
        raise ValueError('Unknown scalar subtype or scale encoding')
    if kind in (14, 37, 261) and scale != 0:
        raise ValueError('Character/BLOB scale is not a scalar type property')
    if kind in (24, 25):
        if native.get('field_precision') is not None and number('field_precision') != (16 if kind == 24 else 34):
            raise ValueError('DECFLOAT precision disagrees with the native type code')
    elif not (kind in (7, 8, 16, 26) and subtype in (1, 2)) and number('field_precision') != 0:
        raise ValueError('Declared precision does not apply to this native type')
    if kind not in (14, 37) and number('character_length') != 0:
        raise ValueError('Character length does not apply to this native type')
    if kind != 261 and number('segment_length') != 0:
        raise ValueError('BLOB segment size does not apply to this native type')
    if kind == 261 and native.get('segment_length') is None:
        raise ValueError('BLOB domain requires an exact native segment size')
    dependencies = []
    charset = native.get('character_set')
    collation = native.get('collation')
    character = kind in (14, 37) or (kind == 261 and subtype == 1)
    if character:
        databases = [item for item in current['rows'].values() if item['kind'] == 'database']
        observations = databases[0]['native'].get('catalog_observations', []) if len(databases) == 1 else []
        for section in ('character-set objects', 'collation objects'):
            evidence = [item for item in observations if item.get('section') == section]
            if len(evidence) != 1 or evidence[0].get('available') is not True:
                raise ValueError('Domain creation requires available catalog observation: ' + section)
        if not isinstance(charset, str) or not charset:
            raise ValueError('Character domain creation requires an explicit native character set')
        if kind in (14, 37) and subtype == 1 and charset != 'OCTETS':
            raise ValueError('Binary domain metadata requires OCTETS')
        matches = [item for item in current['rows'].values()
                   if item['kind'] == 'character-set' and item['path'] == [charset]]
        if len(matches) != 1:
            raise ValueError('Domain character set is not observed in the current catalog')
        dependencies.append(matches[0]['resource_id'])
        if collation is None:
            collation = matches[0]['native'].get('default_collation')
            if not isinstance(collation, str) or not collation:
                raise ValueError('Default collation is not observed for this character set')
    elif charset is not None or collation is not None:
        raise ValueError('Character metadata does not apply to this domain type')
    if collation is not None:
        identifier(collation)
        matches = [item for item in current['rows'].values()
                   if item['kind'] == 'collation' and item['name'] == collation
                   and item['native'].get('character_set') == charset]
        if len(matches) != 1:
            raise ValueError('Domain collation is not observed for its character set')
        dependencies.append(matches[0]['resource_id'])
    # Render now to run the native compiler's ranges and byte/name checks.
    typed = {'descriptor': descriptor, 'collation': collation,
             'dimensions': dimensions, 'dependencies': dependencies}
    rendered = render_type(typed)
    if collation is not None:
        rendered += ' COLLATE ' + identifier(collation)
    typed['sql'] = rendered
    return typed


def statements(before, after):
    if before is None:
        typed = after['creation_type']
        # COLLATE belongs after default/nullability/check in domain grammar.
        source = 'CREATE DOMAIN ' + identifier(after['name']) + ' AS ' + render_type(typed)
        if after['default_source']:
            source += ' ' + after['default_source'] + '\n'
        if after['not_null'] == '1':
            source += ' NOT NULL'
        if after['validation_source']:
            source += ' ' + after['validation_source'] + '\n'
        if typed['collation'] is not None:
            source += ' COLLATE ' + identifier(typed['collation'])
        return [source]
    prefix = 'ALTER DOMAIN ' + identifier(after['name']) + ' '
    result = []
    if before['default_source'] != after['default_source']:
        result.append(prefix + ('SET ' + after['default_source'] + '\n'
                                if after['default_source'] else 'DROP DEFAULT'))
    if before['not_null'] != after['not_null']:
        result.append(prefix + ('SET NOT NULL' if after['not_null'] == '1' else 'DROP NOT NULL'))
    if before['validation_source'] != after['validation_source']:
        if before['validation_source'] is not None:
            result.append(prefix + 'DROP CONSTRAINT')
        if after['validation_source'] is not None:
            result.append(prefix + 'ADD ' + after['validation_source'] + '\n')
    return result
