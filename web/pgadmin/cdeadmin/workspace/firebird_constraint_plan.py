"""Native constraint replacement is explicit DROP/ADD in one reviewed outcome."""
from copy import deepcopy
from ..providers.firebird.character_metadata import identifier
from . import firebird_index_plan as indexes
from .firebird_domain_plan import clause
from .firebird_table_constraints import creation
from .firebird_view_plan import dependencies

FIELDS = {'constraint_type', 'index_name', 'check_source', 'not_null_column',
          'referenced_relation', 'referenced_index', 'update_rule', 'delete_rule', 'backing_index'}
DERIVED = {'administration'}
WARNING = ('Firebird constraint definition changes replace the constraint using DROP and ADD '
           'inside this transaction. Native data/dependency validation applies; no CASCADE is used. '
           'Firebird CHECK creation/replacement does not validate existing rows; it governs subsequent writes.')


def model(row):
    native = row['native']
    result = {key: native.get(key) for key in FIELDS}
    result['table'] = row['path'][0]
    identifier(result['table'])
    kind = result['constraint_type']
    applicable = {'CHECK': {'check_source'}, 'NOT NULL': {'not_null_column'},
        'PRIMARY KEY': {'index_name', 'backing_index'}, 'UNIQUE': {'index_name', 'backing_index'},
        'FOREIGN KEY': {'index_name', 'backing_index', 'referenced_relation', 'referenced_index', 'update_rule', 'delete_rule'}}
    if kind not in applicable:
        raise ValueError('Unknown native constraint type')
    if any(result[key] is not None for key in FIELDS - applicable[kind] - {'constraint_type'}):
        raise ValueError('Constraint includes fields belonging to a different native kind')
    if kind == 'CHECK':
        result['check_source'] = clause(result['check_source'], 'CHECK')
        if result['check_source'] is None:
            raise ValueError('CHECK requires native source')
    if kind == 'NOT NULL':
        identifier(result['not_null_column'])
    if kind in {'PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY'}:
        identifier(result['index_name'])
        raw = result['backing_index']
        if not isinstance(raw, dict) or raw.get('name') != result['index_name']:
            raise ValueError('Constraint requires an exact backing index definition')
        ignored = {'name', 'system_object', 'statistics', 'ddl', 'recreation_statements', 'state', 'dependencies',
                   'dependents', 'property_sections', 'navigator_parent_resource_id'}
        if set(raw) - indexes.FIELDS - ignored:
            raise ValueError('Unknown backing index properties')
        result['backing_index'] = {key: value for key, value in indexes.model(
            {'native': raw, 'path': [result['table'], raw['name']]}).items() if key != 'table'}
        result['backing_index'].update(name=raw['name'], description=raw.get('description') or None)
    if kind == 'FOREIGN KEY':
        identifier(result['referenced_relation']); identifier(result['referenced_index'])
        if any(result[key] not in {'RESTRICT', 'NO ACTION', 'CASCADE', 'SET NULL', 'SET DEFAULT'}
               for key in ('update_rule', 'delete_rule')):
            raise ValueError('Foreign key requires exact native rules')
    if native.get('description') is not None:
        raise ValueError('Firebird constraints have no native COMMENT ON form')
    return result


def definition(after, current):
    matches = [row for row in current['rows'].values() if row['kind'] == 'table' and row['name'] == after['table']]
    if len(matches) != 1 or matches[0]['system'] == 'true':
        raise ValueError('Constraint requires one observed user table')
    if str(matches[0]['native'].get('relation_type')) not in {'0', '4', '5'}:
        raise ValueError('Constraint operation requires a native persistent or temporary table')
    if after['constraint_type'] == 'NOT NULL':
        raise ValueError('Existing-table NOT NULL changes require column nullability planning')
    parent = deepcopy(matches[0])
    # Compile only this child, using the parent's observed column layout and
    # referenced key metadata; no imported statement is executable authority.
    parent['native']['constraints'] = [{key: value for key, value in after.items()
        if key in FIELDS - {'backing_index'} or key == 'name'}]
    parent['native']['indexes'] = [after['backing_index']] if after['backing_index'] else []
    compiled = creation(parent, current)
    if len(compiled['clauses']) != 1:
        raise ValueError('Constraint must compile to one native definition')
    return compiled['clauses'][0], compiled['statements']


def context(before, after, current):
    if before and any(before[key] != after[key] for key in ('constraint_type', 'index_name')):
        raise ValueError('Constraint kind or backing index identity changes require an explicit lifecycle mapping')
    if before and before['constraint_type'] == 'NOT NULL':
        raise ValueError('Existing-table NOT NULL changes require column nullability planning')
    return dependencies(current)


def statements(before, after, current):
    source, comments = definition(after, current)
    prefix = 'ALTER TABLE ' + identifier(after['table'])
    result = [] if before is None else [prefix + ' DROP CONSTRAINT ' + identifier(before['name'])]
    return result + [prefix + ' ADD ' + source] + comments


def require_embedded_match(row, parent):
    native = parent['native']
    matches = [item for item in native.get('constraints', []) if item.get('name') == row['name']]
    if len(matches) != 1:
        raise ValueError('New-table constraint requires one matching nested definition')
    nested = deepcopy(matches[0])
    backing = [item for item in native.get('indexes', []) if item.get('name') == nested.get('index_name')]
    nested['backing_index'] = backing[0] if len(backing) == 1 else None
    if model({**row, 'native': nested}) != model(row):
        raise ValueError('Nested and standalone constraint definitions disagree')


def index_projection_owner(row, effective, baseline, desired):
    owners = [item for item in desired['rows'].values() if item['kind'] == 'constraint'
              and item['path'][0] == row['path'][0] and item['native'].get('index_name') == row['name']]
    if not owners:
        return None
    if len(owners) != 1:
        raise ValueError('Backing index projection has multiple constraint owners')
    owner = owners[0]
    old = baseline['rows'].get(owner['resource_id'])
    if old is not None and model(old) == model(owner):
        return None
    expected = model(owner)['backing_index']
    if {key: value for key, value in effective.items() if key != 'table'} != expected:
        raise ValueError('Standalone index projection disagrees with the owning constraint')
    return owner['resource_id']
