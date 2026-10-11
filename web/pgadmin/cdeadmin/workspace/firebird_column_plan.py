"""Exact existing-column changes; native catalog owns structural admission."""
from ..providers.firebird import columns
from ..providers.firebird.identity import catalog_resource_id
from ..providers.firebird_expressions import index_expression
from .firebird_domain_plan import clause
from .firebird_catalog_import import _equal
from .firebird_view_plan import dependencies as schema_dependencies
from . import firebird_table_plan as table_plan
from .firebird_domain_plan import TYPE_FIELDS
from . import firebird_domain_plan as domains

TYPE_EDITS = {'field_type', 'field_sub_type', 'field_scale', 'field_precision', 'character_length'}
FIELDS = {'default_source', 'not_null', 'identity_type', 'computed_source', 'description'} | TYPE_EDITS
DERIVED = {'alteration', 'type_editor', 'field_length'}
CREATION = TYPE_FIELDS | {'domain', 'domain_not_null', 'position', 'generator_name',
                         'identity_initial_value', 'identity_increment'}


def flag(value, name, nullable=False):
    if value is None:
        return None if nullable else '0'
    if type(value) not in (int, str) or str(value) not in {'0', '1'}:
        raise ValueError(name + ' requires a native zero/one flag')
    return str(value)


def model(row):
    native = row['native']
    for field in ('default_source', 'not_null', 'identity_type'):
        if field not in native:
            raise ValueError('Exact column metadata is missing: ' + field)
    computed = native.get('computed_source')
    if computed is not None:
        computed = index_expression(computed, 'Computed expression', require_outer=True)
    facts = {key: int(columns.integer(0 if native.get(key) is None else native[key], -32768, 65535, key)) for key in TYPE_EDITS}
    if facts['field_type'] in {7, 8, 16, 26} and facts['field_sub_type'] == 0:
        physical = {7: 4, 8: 9, 16: 18, 26: 38}[facts['field_type']]
        if facts['field_precision'] not in {0, physical}:
            raise ValueError('Plain integer precision must match native physical metadata')
        facts['field_precision'] = 0
    if facts['field_type'] in {24, 25} and facts['field_precision'] == 0:
        facts['field_precision'] = 16 if facts['field_type'] == 24 else 34
    return {**facts, 'table': row['path'][0], 'computed_source': computed,
            'default_source': clause(native['default_source'], 'DEFAULT'),
            'not_null': flag(native['not_null'], 'Column nullability'),
            'identity_type': flag(native['identity_type'], 'Identity mode', True)}


def context(row, current, before, after):
    parent = current['rows'].get(catalog_resource_id('table', [], row['path'][0]))
    if parent is None or parent['system'] == 'true':
        raise ValueError('Column alteration requires an observed user table')
    databases = [r for r in current['rows'].values() if r['kind'] == 'database']
    observations = databases[0]['native'].get('catalog_observations', []) if len(databases) == 1 else []
    for section in ('column objects', 'constraint objects', 'index objects', 'system index objects'):
        if not any(item.get('section') == section and item.get('available') is True for item in observations):
            raise ValueError('Column planning requires available catalog observation: ' + section)
    related = [item for item in current['rows'].values() if item['kind'] in {'constraint', 'index'}
               and item['path'][:-1] == row['path'][:-1]]
    primary = set()
    for constraint in related:
        if constraint['kind'] != 'constraint' or constraint['native'].get('constraint_type') != 'PRIMARY KEY':
            continue
        indexes = [item for item in related if item['kind'] == 'index' and item['name'] == constraint['native'].get('index_name')]
        if len(indexes) != 1 or not isinstance(indexes[0]['native'].get('segments'), list):
            raise ValueError('Primary-key column membership is not fully observed')
        primary.update(segment['field_name'] for segment in indexes[0]['native']['segments'])
    native = row['native']
    allowed = columns.alteration_context(native, parent['native'],
        primary_key=row['path'][-1] in primary,
        array=bool(native.get('array_dimensions')) or str(native.get('dimensions') or '0') != '0')['allowed_actions']
    for action, _ in changes(before, after, check_only=True):
        if action not in allowed:
            raise ValueError('Native column structure does not admit ' + action)
    dependencies = {parent['resource_id'], *(item['resource_id'] for item in related)}
    type_clause = None
    if any(before[key] != after[key] for key in TYPE_EDITS):
        domain = native.get('domain')
        if domain and not domain.startswith('RDB$'):
            raise ValueError('Named-domain type rebinding requires explicit lifecycle intent')
        if str(after['field_type']) == '261' and after['computed_source'] is None:
            raise ValueError('Ordinary BLOB type replacement requires explicit lifecycle intent')
        facts = {**native, **{key: after[key] for key in TYPE_EDITS}, 'domain': None}
        typed = domains.creation_model({'native': facts}, current)
        type_clause = 'TYPE ' + domains.render_type(typed)
        if after['computed_source'] is not None:
            type_clause += ' COMPUTED BY ' + after['computed_source'] + '\n'
        dependencies.update(typed['dependencies'])
    if type_clause or any(before[key] != after[key] for key in ('computed_source', 'default_source')):
        dependencies.update(schema_dependencies(current))
    return sorted(dependencies), type_clause


def changes(before, after, *, check_only=False):
    if before is None:
        raise ValueError('Column creation requires an explicit parent layout plan')
    result = []
    type_changed = any(before[key] != after[key] for key in TYPE_EDITS)
    if type_changed:
        if not check_only and not after.get('_type_clause'):
            raise ValueError('Column type alteration requires catalog validation')
        result.append(('TYPE COMPUTED' if before['computed_source'] is not None else 'TYPE', after.get('_type_clause')))
    if before['default_source'] != after['default_source']:
        result.append(('SET DEFAULT', 'SET ' + after['default_source'] + '\n') if after['default_source']
                      else ('DROP DEFAULT', 'DROP DEFAULT'))
    if before['not_null'] != after['not_null']:
        action = 'SET NOT NULL' if after['not_null'] == '1' else 'DROP NOT NULL'
        result.append((action, action))
    if before['identity_type'] != after['identity_type']:
        if before['identity_type'] is None or after['identity_type'] is None:
            raise ValueError('Adding or removing identity status requires explicit lifecycle intent')
        result.append(('IDENTITY', 'SET GENERATED ' + ('ALWAYS' if after['identity_type'] == '0' else 'BY DEFAULT')))
    if before['computed_source'] != after['computed_source']:
        if before['computed_source'] is None or after['computed_source'] is None:
            raise ValueError('Stored/computed conversion requires explicit replacement intent')
        if not type_changed:
            result.append(('COMPUTED', 'COMPUTED BY ' + after['computed_source'] + '\n'))
    return result


def statements(before, after):
    from ..providers.firebird.character_metadata import identifier
    if before is None:
        definition = after['creation_column']
        return ['ALTER TABLE ' + identifier(after['table']) + ' ADD ' + definition['definition']]
    prefix = 'ALTER TABLE ' + identifier(after['table']) + ' ALTER COLUMN ' + identifier(after['name']) + ' '
    return [prefix + sql for _, sql in changes(before, after)]


def creation_model(row, current, *, observed=False, added_count=1):
    parent = current['rows'].get(catalog_resource_id('table', [], row['path'][0]))
    if parent is None or parent['system'] == 'true':
        raise ValueError('Column creation requires an observed user table')
    databases = [item for item in current['rows'].values() if item['kind'] == 'database']
    observations = databases[0]['native'].get('catalog_observations', []) if len(databases) == 1 else []
    if not any(item.get('section') == 'column objects' and item.get('available') is True for item in observations):
        raise ValueError('Column creation requires available column objects observation')
    children = [item for item in current['rows'].values() if item['kind'] == 'column'
                and item['path'][:-1] == row['path'][:-1]]
    position = int(columns.integer(row['native'].get('position'), 0, 1023, 'Column position'))
    if position > len(children) - 1 + (0 if observed else added_count):
        raise ValueError('Column position exceeds the observed table layout')
    facts = {key: value for key, value in row['native'].items() if key not in {
        'ddl', 'recreation_statements', 'creation_dependencies', 'system_object', 'state'}
        and not (observed and key == 'privileges')}
    native = {**parent['native'], 'columns': [{**facts, 'name': row['path'][-1], 'position': 0}],
              'constraints': [], 'indexes': [], 'triggers': []}
    typed = table_plan.creation_model({**parent, 'native': native}, current, observed=observed)
    if len(typed['definitions']) != 1 or typed['foreign_keys']:
        raise ValueError('Column creation requires a single exact definition')
    return {'definition': typed['definitions'][0], 'position': position,
            'dependencies': sorted({parent['resource_id'], *(item['resource_id'] for item in children),
                                    *typed['dependencies']})}


def final_positions(operations):
    from ..providers.firebird.character_metadata import identifier
    groups = {}
    for operation in operations:
        if operation['kind'] == 'column' and operation['operation'] == 'create' and not operation.get('embedded_column_definition'):
            groups.setdefault(operation['after']['table'], []).append(operation)
    for table, added in groups.items():
        ordered = sorted(added, key=lambda operation: operation['after']['creation_column']['position'])
        positions = [operation['after']['creation_column']['position'] for operation in ordered]
        if len(set(positions)) != len(positions):
            raise ValueError('New columns require distinct final positions within ' + table)
        # All ADD statements precede this phase; ascending positions preserve
        # earlier placements when several new fields are inserted in a table.
        added[-1]['deferred_statements'].extend('ALTER TABLE ' + identifier(table) +
            ' ALTER COLUMN ' + identifier(operation['after']['name']) + ' POSITION ' +
            str(operation['after']['creation_column']['position'] + 1) for operation in ordered)


def require_embedded_match(row, parent):
    nested = [item for item in parent['native'].get('columns', [])
              if isinstance(item, dict) and item.get('name') == row['path'][-1]]
    if len(nested) != 1:
        raise ValueError('New table must contain the standalone column definition exactly once')
    ignored = DERIVED | {'name', 'ddl', 'recreation_statements', 'creation_dependencies',
        'system_object', 'state', 'property_sections', 'dependencies', 'dependents', 'navigator_parent_resource_id'}
    left, right = nested[0], row['native']
    if any(not _equal(left.get(key), right.get(key)) for key in left.keys() | right.keys() if key not in ignored):
        raise ValueError('Nested and standalone column definitions disagree')


def nested_changes_match(old, wanted, baseline, desired):
    """Allow a repeated projection only when exact standalone edits own it."""
    left, right = old['native'].get('columns'), wanted['native'].get('columns')
    if _equal(left, right):
        return True
    if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
        return False
    for before, after in zip(left, right):
        if not isinstance(before, dict) or not isinstance(after, dict) or before.get('name') != after.get('name'):
            return False
        if _equal(before, after):
            continue
        identity = catalog_resource_id('column', old['path'], before.get('name'))
        base, target = baseline['rows'].get(identity), desired['rows'].get(identity)
        if base is None or target is None or base['path'] != target['path']:
            return False
        for key in before.keys() | after.keys():
            if key in DERIVED:
                continue
            if key not in before or key not in after or not _equal(before[key], after[key]):
                if key not in FIELDS or not _equal(before.get(key), base['native'].get(key)) or not _equal(after.get(key), target['native'].get(key)):
                    return False
    return True
