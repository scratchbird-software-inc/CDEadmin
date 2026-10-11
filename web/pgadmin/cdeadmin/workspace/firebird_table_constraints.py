"""Named native constraints and indexes for an explicitly authored new table."""
from ..providers.firebird.character_metadata import identifier, literal
from .firebird_domain_plan import clause
from . import firebird_index_plan as indexes
from .firebird_view_plan import dependencies as schema_dependencies


def creation(row, current):
    native, table = row['native'], row['path'][-1]
    constraints, raw_indexes = native.get('constraints') or [], native.get('indexes') or []
    if not isinstance(constraints, list) or not isinstance(raw_indexes, list):
        raise ValueError('Table constraints and indexes must be arrays')
    if len(constraints) > 2048 or len(raw_indexes) > 2048:
        raise ValueError('Table child definition limit exceeded')
    if any(not isinstance(item, dict) for item in constraints):
        raise ValueError('Every constraint definition must be an object')
    columns = set()
    for item in native['columns']:
        identifier(item.get('name'))
        columns.add(item['name'])
    by_name, used, names, nulls, primary = {}, set(), set(), {}, set()
    clauses, statements, dependencies, foreign_keys = [], [], set(), []
    for value in raw_indexes:
        if not isinstance(value, dict):
            raise ValueError('Index definition must be an object')
        name = value.get('name'); identifier(name)
        if name in by_name:
            raise ValueError('Duplicate index identity')
        unknown = set(value) - indexes.FIELDS - {'name', 'system_object', 'state', 'statistics', 'ddl', 'recreation_statements', 'dependencies', 'dependents', 'property_sections', 'navigator_parent_resource_id'}
        if unknown:
            raise ValueError('Unsupported index properties: ' + ', '.join(sorted(unknown)))
        model = {**indexes.model({'native': value, 'path': [table, name]}), 'name': name,
                 'description': value.get('description') or None}
        if any(part['field_name'] not in columns for part in model['segments']):
            raise ValueError('Index refers to an absent authored column')
        by_name[name] = model
    for constraint in sorted(constraints, key=lambda item: (
            {'NOT NULL': 0, 'PRIMARY KEY': 1, 'UNIQUE': 2, 'CHECK': 3, 'FOREIGN KEY': 4}.get(item.get('constraint_type'), 5), str(item.get('name')))):
        if not isinstance(constraint, dict):
            raise ValueError('Constraint definition must be an object')
        name = constraint.get('name'); identifier(name)
        if name in names:
            raise ValueError('Duplicate constraint identity')
        names.add(name)
        unknown = set(constraint) - {'name', 'system_object', 'constraint_type', 'index_name', 'check_source',
            'backing_index', 'not_null_column', 'referenced_relation', 'referenced_index', 'update_rule', 'delete_rule',
            'ddl', 'dependencies', 'dependents', 'property_sections', 'navigator_parent_resource_id'}
        if unknown:
            raise ValueError('Unsupported constraint properties: ' + ', '.join(sorted(unknown)))
        kind = constraint.get('constraint_type')
        applicable = {'NOT NULL': {'not_null_column'}, 'CHECK': {'check_source'},
                      'PRIMARY KEY': {'index_name', 'backing_index'}, 'UNIQUE': {'index_name', 'backing_index'},
                      'FOREIGN KEY': {'index_name', 'backing_index', 'referenced_relation', 'referenced_index', 'update_rule', 'delete_rule'}}.get(kind, set())
        semantic = {'not_null_column', 'check_source', 'index_name', 'backing_index', 'referenced_relation', 'referenced_index', 'update_rule', 'delete_rule'}
        if any(constraint.get(key) is not None for key in semantic - applicable):
            raise ValueError('Constraint contains properties for a different native constraint kind')
        prefix = 'CONSTRAINT ' + identifier(name) + ' '
        if kind == 'NOT NULL':
            column = constraint.get('not_null_column')
            if column not in columns or column in nulls or constraint.get('index_name'):
                raise ValueError('NOT NULL requires one exact column and no backing index')
            nulls[column] = prefix + 'NOT NULL'
            continue
        if kind == 'CHECK':
            if constraint.get('index_name'):
                raise ValueError('CHECK cannot have a backing index')
            source = clause(constraint.get('check_source'), 'CHECK')
            if source is None:
                raise ValueError('CHECK requires its native source')
            clauses.append(prefix + source + '\n')
            dependencies.update(schema_dependencies(current))
            continue
        if kind not in {'PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY'}:
            raise ValueError('Unsupported native table constraint kind')
        index_name = constraint.get('index_name'); index = by_name.get(index_name)
        if index is None or index_name in used:
            raise ValueError('Constraint requires one exact, distinct backing index')
        if constraint.get('backing_index') is not None:
            backing = constraint['backing_index']
            if not isinstance(backing, dict) or backing.get('name') != index_name:
                raise ValueError('Constraint backing index identity disagrees with table index')
            canonical = {**indexes.model({'native': backing, 'path': [table, index_name]}),
                         'name': index_name, 'description': backing.get('description') or None}
            if canonical != index:
                raise ValueError('Constraint backing index definition disagrees with table index')
        used.add(index_name)
        if (index['inactive'] != '0' or index['expression_source'] or index['condition_source'] or
                index['unique'] != ('0' if kind == 'FOREIGN KEY' else '1')):
            raise ValueError('Backing index flags/type disagree with constraint semantics')
        fields = [part['field_name'] for part in index['segments']]
        if kind == 'PRIMARY KEY':
            if primary:
                raise ValueError('A table has only one primary key')
            primary.update(fields)
        sql = prefix + kind + ' (' + ', '.join(identifier(field) for field in fields) + ')'
        if kind == 'FOREIGN KEY':
            target = constraint.get('referenced_relation'); identifier(target)
            reference = constraint.get('referenced_index'); identifier(reference)
            if target == table:
                reference_index = by_name.get(reference)
                keys = constraints
                if reference_index is None:
                    observed = [item for item in current['rows'].values() if item['kind'] == 'table' and item['path'] == [target]]
                    if len(observed) == 1:
                        candidates = [item for item in observed[0]['native'].get('indexes', []) if item.get('name') == reference]
                        if len(candidates) == 1:
                            reference_index = indexes.model({'native': candidates[0], 'path': [target, reference]})
                            keys = observed[0]['native'].get('constraints', [])
            else:
                parents = [item for item in current['rows'].values() if item['kind'] == 'table' and item['path'] == [target]]
                if len(parents) != 1:
                    raise ValueError('Foreign key target must be the authored table or an observed existing table')
                parent = parents[0]; dependencies.add(parent['resource_id'])
                matches = [item for item in parent['native'].get('indexes', []) if item.get('name') == reference]
                if len(matches) != 1:
                    raise ValueError('Referenced index metadata is unavailable')
                reference_index = indexes.model({'native': matches[0], 'path': [target, reference]})
                keys = parent['native'].get('constraints', [])
            if reference_index is None or not any(key.get('constraint_type') in {'PRIMARY KEY', 'UNIQUE'} and key.get('index_name') == reference for key in keys):
                raise ValueError('Foreign key must reference a native primary/unique constraint')
            referenced = [part['field_name'] for part in reference_index['segments']]
            if len(referenced) != len(fields):
                raise ValueError('Foreign key column tuple lengths disagree')
            sql += ' REFERENCES ' + identifier(target) + ' (' + ', '.join(identifier(field) for field in referenced) + ')'
            for field, keyword in [('update_rule', 'ON UPDATE'), ('delete_rule', 'ON DELETE')]:
                rule = constraint.get(field)
                if rule not in {'RESTRICT', 'NO ACTION', 'CASCADE', 'SET NULL', 'SET DEFAULT'}:
                    raise ValueError('Foreign key requires exact native update/delete rules')
                if rule not in {'RESTRICT', 'NO ACTION'}:
                    sql += ' ' + keyword + ' ' + rule
        sql += ' USING ' + ('DESCENDING' if index['index_type'] == '1' else 'ASCENDING') + ' INDEX ' + identifier(index_name)
        clauses.append(sql)
        if kind == 'FOREIGN KEY':
            foreign_keys.append({'referenced_table': target, 'clause': sql, 'index_name': index_name})
    for name, index in sorted(by_name.items()):
        if name not in used:
            statements.extend(indexes.statements(None, index))
            if index['expression_source'] or index['condition_source']:
                dependencies.update(schema_dependencies(current))
        if index['description']:
            statements.append('COMMENT ON INDEX ' + identifier(name) + ' IS ' + literal(index['description']))
    return {'foreign_keys': foreign_keys, 'clauses': clauses, 'column_nulls': nulls, 'primary_columns': primary,
            'statements': statements, 'dependencies': sorted(dependencies)}
