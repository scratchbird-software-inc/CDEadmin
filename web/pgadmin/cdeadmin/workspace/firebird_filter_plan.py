"""Exact BLOB filter declaration models using the native provider compiler."""
from ..providers.firebird import blob_filters
from ..providers.firebird.character_metadata import text
from ..providers.firebird.external_functions import external_name

FIELDS = {'input_subtype', 'output_subtype', 'module_name', 'entrypoint', 'description'}
DEFINITION = FIELDS - {'description'}
WARNING = blob_filters.WARNING


def model(row):
    native = row['native']
    result = {}
    for prefix in ('input', 'output'):
        key = prefix + '_subtype'
        result[key] = blob_filters.subtype({key: native.get(key)}, prefix)
    for key in ('module_name', 'entrypoint'):
        external_name(native.get(key), key)
        result[key] = text(native[key], key)
    return result


def context(current):
    databases = [row for row in current['rows'].values() if row['kind'] == 'database']
    observations = databases[0]['native'].get('catalog_observations', []) if len(databases) == 1 else []
    evidence = [item for item in observations if item.get('section') == 'blob-filter objects']
    if len(evidence) != 1 or evidence[0].get('available') is not True:
        raise ValueError('BLOB filter planning requires available catalog observation: blob-filter objects')


def statements(before, after):
    if before is None:
        # Comments are emitted by the planner to retain NULL versus empty text.
        return blob_filters.compile_operation('create', {
            key: after[key] for key in DEFINITION | {'name'}})
    if any(before[key] != after[key] for key in DEFINITION):
        raise ValueError('BLOB filter definition changes require an explicit drop/redeclare plan')
    return []
