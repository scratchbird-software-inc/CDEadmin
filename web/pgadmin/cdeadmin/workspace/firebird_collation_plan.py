"""Native collation models without implicit comparison-rule replacement."""
from ..providers.firebird import character_metadata
from ..providers.firebird.identity import catalog_resource_id

FIELDS = {'character_set', 'base_collation', 'attributes', 'specific_attributes', 'description'}
DEFINITION = FIELDS - {'description'}
DERIVED = {'character_set_id', 'system_flag'}
WARNING = ('Collation implementations must already be installed on the server. '
           'Changing comparison rules requires explicit dependency-aware removal/recreation.')


def model(row):
    native = row['native']
    charset = native.get('character_set')
    character_metadata.identifier(charset)
    base = native.get('base_collation')
    if base == '': base = None
    if base is not None: character_metadata.metadata_name(base)
    attributes = native.get('attributes')
    if isinstance(attributes, str) and attributes in tuple(str(value) for value in range(8)):
        attributes = int(attributes)
    if type(attributes) is not int or not 0 <= attributes <= 7:
        raise ValueError('Collation attribute bits must be a native integer from 0 through 7')
    specific = native.get('specific_attributes')
    if specific == '': specific = None
    if specific is not None: character_metadata.text(specific, 'Specific collation attributes')
    return {'character_set': charset, 'base_collation': base,
            'attributes': attributes, 'specific_attributes': specific}


def context(after, current):
    databases = [row for row in current['rows'].values() if row['kind'] == 'database']
    observations = databases[0]['native'].get('catalog_observations', []) if len(databases) == 1 else []
    for section in ('collation objects', 'character-set objects'):
        evidence = [item for item in observations if item.get('section') == section]
        if len(evidence) != 1 or evidence[0].get('available') is not True:
            raise ValueError('Collation planning requires available catalog observation: ' + section)
    identity = catalog_resource_id('character-set', [], after['character_set'])
    if identity not in current['rows']:
        raise ValueError('Collation character set is not observed in the current catalog')
    return [identity]


def statements(before, after):
    if before is None:
        return character_metadata.recreation('collation', after['name'], {**after, 'description': None})
    if any(before[key] != after[key] for key in DEFINITION):
        raise ValueError('Collation comparison changes require explicit removal/recreation')
    return []


def attributes(value):
    """IntlUtil native escaping, ordered last-wins values and empty removal."""
    import re
    if value is None: return {}
    character_metadata.text(value, 'Specific collation attributes')
    parts, part, escaped = [], '', False
    for char in value:
        if escaped:
            part += '\\' + char
            escaped = False
        elif char == '\\': escaped = True
        elif char == ';':
            parts.append(part); part = ''
        else: part += char
    if escaped: raise ValueError('Incomplete collation attribute escape')
    if part.strip(' '): parts.append(part)
    result = {}
    for part in parts:
        match = re.fullmatch(r' *([A-Za-z_-]+) *= *(.*?) *', part, re.DOTALL)
        if not match: raise ValueError('Invalid native collation attribute')
        name, raw = match.groups()
        decoded = re.sub(r'\\(.)', r'\1', raw, flags=re.DOTALL)
        if decoded: result[name] = decoded
        else: result.pop(name, None)
    return result


def created_matches(observed, expected):
    if observed is None: return False
    if any(observed.get(key) != value for key, value in expected.items() if key != 'specific_attributes'):
        return False
    actual, requested = attributes(observed.get('specific_attributes')), attributes(expected.get('specific_attributes'))
    # Firebird persists installed implementation versions even when the
    # CREATE omitted them. Explicit requested versions must still match.
    return all(actual.get(key) == value for key, value in requested.items()) and (
        actual.keys() - requested.keys() <= {'ICU-VERSION', 'COLL-VERSION'})
