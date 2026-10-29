"""Structured three-way schema previews; never execute documentary DDL."""
import hashlib
import json
from decimal import Decimal

from ..providers.firebird import sequences
from ..providers.firebird.character_metadata import identifier, literal, text
from ..providers.firebird.identity import catalog_resource_id
from ..sdk.relational import RelationalClientError
from .firebird_catalog_import import _equal
from . import firebird_index_plan as indexes
from . import firebird_role_plan as roles
from . import firebird_filter_plan as filters
from . import firebird_collation_plan as collations
from . import firebird_external_function_plan as external_functions
from . import firebird_domain_plan as domains
from . import firebird_view_plan as views
from . import firebird_table_plan as tables
from . import firebird_column_plan as columns
from . import firebird_package_plan as packages
from . import firebird_routine_plan as routines
from . import firebird_trigger_plan as triggers
from . import firebird_constraint_plan as constraints
from .firebird_routine_stages import WARNING as ROUTINE_STAGE_WARNING
from .firebird_sql_export import script as native_script
from . import firebird_creation_graph as creation_graph
from . import firebird_lifecycle_plan as lifecycle
from . import firebird_privilege_plan as privileges

SUPPORTED = {'external-function', 'collation', 'sequence', 'exception', 'index', 'role', 'blob-filter', 'domain', 'view', 'table', 'column', 'package', 'procedure', 'function', 'trigger', 'constraint'}
DERIVED = {'ddl', 'recreation_statements', 'recreation_primary_statements', 'recreation_deferred_statements', 'property_sections', 'dependencies', 'system_object',
           'dependents', 'state', 'navigator_parent_resource_id', creation_graph.INSTRUCTION, lifecycle.INSTRUCTION, privileges.INSTRUCTION}
FIELDS = {'external-function': external_functions.FIELDS, 'collation': collations.FIELDS, 'sequence': {'initial_value', 'increment', 'description'},
          'exception': {'message', 'description'}, 'index': indexes.FIELDS, 'role': roles.FIELDS, 'blob-filter': filters.FIELDS, 'domain': domains.FIELDS, 'view': views.FIELDS, 'table': tables.FIELDS, 'column': columns.FIELDS, 'package': packages.FIELDS,
          'constraint': constraints.FIELDS, 'trigger': triggers.FIELDS, 'procedure': routines.FIELDS, 'function': routines.FIELDS | {'deterministic'}}


def digest(value):
    def tagged(item):
        if isinstance(item, Decimal):
            return ['decimal', str(item)]
        if isinstance(item, dict):
            return ['object', [[key, tagged(value)] for key, value in sorted(item.items())]]
        if isinstance(item, (list, tuple)):
            return ['array', [tagged(value) for value in item]]
        if isinstance(item, (set, frozenset)):
            return ['set', [tagged(value) for value in sorted(item)]]
        return [type(item).__name__, item]
    return hashlib.sha256(json.dumps(tagged(value), ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def native_guard(row):
    if row is None:
        return None
    return digest({'kind': row['kind'], 'path': row['path'], 'system': row['system'],
        'native': {key: value for key, value in row['native'].items()
                   if key not in DERIVED | {'statistics'}}})


def _model(row):
    kind, native = row['kind'], row['native']
    if kind == 'privilege':
        return privileges.model(row)
    if row['system'] == 'true':
        raise ValueError('System-managed objects are not admitted for schema changes')
    expected_path = ([native['relation'], row['name']] if kind == 'trigger' and native.get('relation') else None)
    identity_parent = [] if kind == 'trigger' else row['path'][:-1]
    if ((expected_path is not None and row['path'] != expected_path) or
            len(row['path']) != (2 if kind in {'index', 'column', 'constraint'} or expected_path is not None else 1) or
            row['resource_id'] != catalog_resource_id(kind, identity_parent, row['path'][-1])):
        raise ValueError('Object path and native identity disagree; renames need explicit mapping')
    name = row['path'][-1]
    identifier(name)
    description = native.get('description')
    if description is not None:
        text(description, 'Object comment')
        if description == '':
            description = None  # Native COMMENT stores empty text as NULL.
    result = {'name': name, 'description': description}
    if kind == 'sequence':
        result['initial_value'] = sequences.number(native.get('initial_value'), 'Initial value')
        result['increment'] = sequences.number(native.get('increment'), 'Increment', increment=True)
    elif kind == 'index':
        result.update(indexes.model(row))
    elif kind == 'role':
        result.update(roles.model(row))
    elif kind == 'blob-filter':
        result.update(filters.model(row))
    elif kind == 'collation':
        result.update(collations.model(row))
    elif kind == 'external-function':
        result.update(external_functions.model(row))
    elif kind == 'domain':
        result.update(domains.model(row))
    elif kind == 'view':
        result.update(views.model(row))
    elif kind == 'table':
        result.update(tables.model(row))
    elif kind == 'column':
        result.update(columns.model(row))
    elif kind == 'constraint':
        result.update(constraints.model(row))
    elif kind == 'trigger':
        result.update(triggers.model(row))
    elif kind == 'package':
        result.update(packages.model(row))
    elif kind in {'procedure', 'function'}:
        result.update(routines.model(row))
    else:
        result['message'] = text(native.get('message'), 'Exception message')
    return result


def _native_changes(old, new, ignored):
    left, right = old['native'], new['native']
    return sorted(key for key in left.keys() | right.keys() if key not in ignored and
                  (key not in left or key not in right or not _equal(left[key], right[key])))


def _statements(kind, before, after):
    name = identifier(after['name'])
    target = {'resource_kind': kind, 'display_name': after['name']}
    statements = []
    if kind == 'sequence':
        if before is None:
            statements = sequences.compile_operation('create', {
                'name': after['name'], 'start': after['initial_value'], 'increment': after['increment']})
        elif before['increment'] != after['increment']:
            statements = sequences.compile_operation('alter', {'increment': after['increment']}, target)
    elif kind == 'index':
        statements = indexes.statements(before, after)
    elif kind == 'role':
        statements = roles.statements(before, after)
    elif kind == 'blob-filter':
        statements = filters.statements(before, after)
    elif kind == 'collation':
        statements = collations.statements(before, after)
    elif kind == 'external-function':
        statements = external_functions.statements(before, after)
    elif kind == 'domain':
        statements = domains.statements(before, after)
    elif kind == 'view':
        statements = views.statements(before, after)
    elif kind == 'table':
        statements = tables.statements(before, after)
    elif kind == 'column':
        statements = columns.statements(before, after)
    elif kind == 'trigger':
        statements = triggers.statements(before, after)
    elif kind == 'package':
        statements = packages.parts(before, after)[0]
    elif kind in {'procedure', 'function'}:
        statements = routines.statements(kind, before, after)
    elif before is None or before['message'] != after['message']:
        statements = [('CREATE' if before is None else 'ALTER') + ' EXCEPTION ' + name + ' ' + literal(after['message'])]
    if (before is None and after['description'] is not None) or (
            before is not None and before['description'] != after['description']):
        comment_name = identifier(after['table']) + '.' + name if kind == 'column' else name
        statements.append('COMMENT ON ' + ({'blob-filter': 'FILTER', 'external-function': 'FUNCTION'}.get(kind, kind.upper())) + ' ' + comment_name + ' IS ' + (
            'NULL' if after['description'] is None else literal(after['description'])))
    return statements


def build_plan(baseline, desired, current):
    from ..providers.firebird.ddl_dialect import generated_dialect
    databases = [row['native'] for row in current['rows'].values() if row['kind'] == 'database']
    if len(databases) != 1 or str(databases[0].get('sql_dialect')) not in {'1', '3'}:
        raise ValueError('Structured planning requires an observed Firebird database dialect')
    for document in (baseline, desired):
        roots = [row['native'] for row in document['rows'].values() if row['kind'] == 'database']
        if roots and (len(roots) != 1 or str(roots[0].get('sql_dialect')) != str(databases[0]['sql_dialect'])):
            raise ValueError('Database dialect changed since the design baseline; capture and review again')
    with generated_dialect(int(databases[0]['sql_dialect'])):
        return _build_plan(baseline, desired, current)


def _build_plan(baseline, desired, current):
    """Return an inspectable plan, including blockers, without touching a DB."""
    for document in (baseline, desired):
        for key in ('endpoint_id', 'database_target_id'):
            if document['provenance'][key] != current['provenance'][key]:
                raise ValueError('Plan documents must identify the selected registered database')
    servers = [row['native'] for row in current['rows'].values() if row['kind'] == 'server']
    databases = [row['native'] for row in current['rows'].values() if row['kind'] == 'database']
    if (len(servers) != 1 or len(databases) != 1 or
            not str(servers[0].get('version', '')).startswith('5.') or
            str(databases[0].get('sql_dialect')) not in {'1', '3'}):
        raise ValueError('Structured planning requires a Firebird 5 dialect 1 or 3 catalog')
    blockers, operations = [], []
    stats = {'unchanged': 0, 'converged': 0, 'preserved_live_changes': 0}
    projected = creation_graph.projected_catalog(baseline, desired, current)
    new_tables = {row['name'] for key, row in desired['rows'].items()
                  if row['kind'] == 'table' and key not in baseline['rows'] and key not in current['rows']}
    added_columns = {}
    for key, row in desired['rows'].items():
        if row['kind'] == 'column' and len(row['path']) == 2 and key not in baseline['rows'] and key not in current['rows']:
            added_columns[row['path'][0]] = added_columns.get(row['path'][0], 0) + 1

    def block(identity, reason, fields=None):
        blockers.append({'resource_id': identity, 'reason': reason, 'fields': fields or []})

    for identity in sorted(baseline['rows'].keys() | desired['rows'].keys()):
        old, wanted = baseline['rows'].get(identity), desired['rows'].get(identity)
        live = current['rows'].get(identity)
        if wanted is None:
            block(identity, 'Absent desired object is not deletion intent; reconcile document scope')
            continue
        kind = wanted['kind']
        if old and (old['kind'] != kind or old['path'] != wanted['path']):
            block(identity, 'Native kind/path change requires an explicit identity mapping')
            continue
        if kind == 'privilege' and privileges.INSTRUCTION in wanted['native']:
            try:
                operation = privileges.plan(old, wanted, live, current)
                if operation is not None:
                    operations.append(operation)
                else:
                    stats['converged'] += 1
            except (ValueError, RelationalClientError) as error:
                block(identity, str(error))
            continue
        if lifecycle.INSTRUCTION in wanted['native']:
            try:
                operation = lifecycle.plan(old, wanted, live, current, desired)
                if operation is None:
                    stats['converged'] += 1
                else:
                    operations.append(operation)
            except (ValueError, RelationalClientError) as error:
                block(identity, str(error))
            continue
        if kind not in SUPPORTED:
            if old is None or _native_changes(old, wanted, DERIVED):
                block(identity, 'Changed object kind is not yet admitted by this planner')
            else:
                stats['unchanged'] += 1
            continue
        try:
            order_dependencies = creation_graph.dependencies(identity, wanted, baseline, desired, current)
            derived = DERIVED | ({'statistics'} if kind == 'index' else roles.DERIVED if kind == 'role' else views.DERIVED if kind == 'view' else tables.DERIVED if kind == 'table' else columns.DERIVED if kind == 'column' else packages.DERIVED if kind == 'package' else set())
            if kind == 'constraint':
                derived = derived | constraints.DERIVED
            if kind == 'collation':
                derived = derived | collations.DERIVED
            if kind == 'external-function':
                derived = derived | external_functions.DERIVED
            if kind == 'trigger':
                derived = derived | triggers.DERIVED
            if kind in {'procedure', 'function'}:
                derived = derived | routines.DERIVED
            if kind == 'table' and old and columns.nested_changes_match(old, wanted, baseline, desired):
                derived = derived | {'columns'}
            if old and not _native_changes(old, wanted, derived):
                stats['unchanged'] += 1
                continue
            if kind == 'view' and old and not _equal(old['native'].get('columns'), wanted['native'].get('columns')):
                raise ValueError('View output metadata edits require explicit column identity/type reconciliation')
            after = _model(wanted)
            before = _model(old) if old else None
            if old:
                unsupported = _native_changes(old, wanted, FIELDS[kind] | derived)
            else:
                # Newly authored definitions cannot silently transfer ownership
                # or restore grants using documentary fields.
                unsupported = sorted(key for key, value in wanted['native'].items()
                                     if key not in FIELDS[kind] | derived | (domains.TYPE_FIELDS if kind == 'domain' else {'relation_type'} if kind == 'view' else tables.STRUCTURE if kind == 'table' else columns.CREATION if kind == 'column' else set()) and value not in (None, [], {}))
            if unsupported:
                block(identity, 'Unsupported native property changes', unsupported)
                continue
            if before == after:
                stats['unchanged'] += 1
                continue
            embedded_column = False
            embedded_constraint = False
            if old is None:
                if live is not None:
                    # A replayed review of a creation converges when the live object already carries
                    # exactly the reviewed definition; anything else was added outside the baseline.
                    if live['kind'] == kind and live['path'] == wanted['path'] and _model(live) == after:
                        stats['converged'] += 1
                    else:
                        block(identity, 'Object was added outside the baseline; capture a new baseline')
                    continue
                effective = after
                if kind == 'domain':
                    effective['creation_type'] = domains.creation_model(wanted, projected)
                elif kind == 'table':
                    effective['creation_table'] = tables.creation_model(wanted, projected)
                elif kind == 'constraint' and wanted['path'][0] in new_tables:
                    parent = desired['rows'][catalog_resource_id('table', [], wanted['path'][0])]
                    constraints.require_embedded_match(wanted, parent)
                    embedded_constraint = True
                elif kind == 'column':
                    if wanted['path'][0] in new_tables:
                        parent = desired['rows'][catalog_resource_id('table', [], wanted['path'][0])]
                        columns.require_embedded_match(wanted, parent)
                        embedded_column = True
                    else:
                        effective['creation_column'] = columns.creation_model(wanted, current,
                            added_count=added_columns.get(wanted['path'][0], 1))
                actual = None
            else:
                if live is None or live['kind'] != kind or live['path'] != old['path']:
                    block(identity, 'Live object was removed or changed identity')
                    continue
                actual = _model(live)
                effective = dict(actual)
                conflicts = []
                for key in FIELDS[kind]:
                    if after[key] == before[key]:
                        if actual[key] != before[key]:
                            stats['preserved_live_changes'] += 1
                        continue
                    if actual[key] != before[key] and actual[key] != after[key]:
                        conflicts.append(key)
                    else:
                        effective[key] = after[key]
                if conflicts:
                    block(identity, 'Competing baseline/live/desired changes', sorted(conflicts))
                    continue
                if kind == 'sequence' and effective['initial_value'] != actual['initial_value']:
                    block(identity, 'Stored initial value cannot be changed by a sequence restart', ['initial_value'])
                    continue
                if effective == actual:
                    stats['converged'] += 1
                    continue
            index_owner = constraints.index_projection_owner(wanted, effective, baseline, desired) if kind == 'index' else None
            embedded_index = index_owner is not None
            if index_owner:
                order_dependencies = sorted(set(order_dependencies) | {index_owner})
            dependencies = ([index_owner, catalog_resource_id('table', [], wanted['path'][0])] if index_owner else
                [indexes.context(wanted, projected, effective['segments'])]) if kind == 'index' else []
            column_type_clause = None
            if kind == 'view':
                dependencies = views.dependencies(current)
            if kind == 'table' and actual is None:
                dependencies = effective['creation_table']['dependencies']
            if kind == 'column':
                if actual is None:
                    dependencies = [catalog_resource_id('table', [], wanted['path'][0])] if embedded_column else effective['creation_column']['dependencies']
                else:
                    dependencies, column_type_clause = columns.context(live, current, actual, effective)
            if kind == 'constraint':
                dependencies = ([catalog_resource_id('table', [], wanted['path'][0])] if embedded_constraint else
                    constraints.context(actual, effective, projected))
            if kind == 'trigger':
                dependencies = triggers.context(effective, projected if actual is None else current)
            if kind == 'package':
                dependencies = packages.context(current)
            if kind in {'procedure', 'function'}:
                dependencies = routines.context(kind, effective, projected if actual is None else current)
            if kind == 'role':
                roles.context(current)
            elif kind == 'blob-filter':
                filters.context(current)
            elif kind == 'collation':
                dependencies = collations.context(effective, current)
            elif kind == 'external-function':
                dependencies = external_functions.context(effective, current)
            elif kind == 'domain':
                domains.context(current)
                if actual is None:
                    dependencies = effective['creation_type']['dependencies']
            if actual is None and kind in {'domain', 'table', 'column'}:
                # Type prerequisites are real creation edges. Broad dependency
                # guards (e.g. expression catalogs) are not ordering edges.
                order_dependencies = sorted(set(order_dependencies) | {
                    key for key in dependencies
                    if projected['rows'].get(key, {}).get('kind') in {'domain', 'collation'}})
            dependencies = sorted(set(dependencies) | set(order_dependencies))
            rendered, deferred_statements = effective, []
            if column_type_clause:
                rendered = {**effective, '_type_clause': column_type_clause}
            if kind == 'table' and actual is None:
                rendered, deferred_statements = tables.staged_creation(effective, new_tables)
            if kind == 'package':
                deferred_statements = packages.parts(actual, effective)[1]
            statements = (constraints.statements(actual, effective, projected) if kind == 'constraint' and not embedded_constraint else
                [] if embedded_column or embedded_constraint or embedded_index else _statements(kind, actual, rendered))
            if kind == 'index' and actual is None and not embedded_index:
                parent_id = catalog_resource_id('table', [], wanted['path'][0])
                parent = desired['rows'].get(parent_id)
                if parent is not None and parent_id not in baseline['rows']:
                    nested = [item for item in parent['native'].get('indexes', []) if item.get('name') == wanted['name']]
                    if nested:
                        if len(nested) != 1 or _model({**wanted, 'native': nested[0]}) != effective:
                            raise ValueError('Nested and standalone index definitions disagree')
                        # The parent table emits this exact index once. Retain
                        # a separate observation/guard for its exported identity.
                        statements = []
                        embedded_index = True
            operations.append({'resource_id': identity, 'kind': kind,
                               'source_location': wanted.get('source_location'),
                               'operation': 'create' if actual is None else 'alter',
                               'before': actual, 'after': effective, 'statements': statements,
                               'deferred_statements': deferred_statements,
                               'dependencies': dependencies,
                               'order_dependencies': order_dependencies,
                               'embedded_index_definition': embedded_index,
                               'embedded_column_definition': embedded_column,
                               'embedded_constraint_definition': embedded_constraint,
                               'precondition': 'absent' if actual is None else 'exact native properties',
                               'permissions': 'Native CREATE/ALTER and COMMENT authority required',
                               'transaction': 'Execute through native provider; no outcome inferred by preview'})
            operations[-1]['native_preconditions'] = {
                item: native_guard(current['rows'].get(item))
                for item in [identity, *dependencies]}
            if kind == 'role':
                operations[-1]['security_changes'] = roles.security_change(actual, effective)
                operations[-1]['permissions'] = (
                    'Native CREATE/ALTER ROLE and COMMENT authority; setting system privileges '
                    'requires native privileged-role authority. Membership and owner are not changed.')
            elif kind == 'package':
                operations[-1]['permissions'] = (
                    'Native CREATE/ALTER PACKAGE, CREATE/RECREATE/DROP PACKAGE BODY and COMMENT authority required.')
        except (ValueError, RelationalClientError) as error:
            block(identity, str(error))
    new_views = [item for item in operations if item['kind'] == 'view' and item['operation'] == 'create']
    if len(new_views) > 1 and any(creation_graph.INSTRUCTION not in desired['rows'][item['resource_id']]['native'] for item in new_views):
        block('view-plan', 'Multiple new views require explicit creation_dependencies arrays')
    try:
        if any(item['kind'] == 'privilege' for item in operations) and any(item['kind'] != 'privilege' for item in operations):
            raise ValueError('Privilege changes require a separate review from structural DDL')
        operations = creation_graph.order(operations)
        columns.final_positions(operations)
        renames = [item for item in operations if item['operation'] == 'rename']
        if len({item['result_resource_id'] for item in renames}) != len(renames):
            raise ValueError('Rename operations claim the same destination')
        operations = [item for item in operations if item['operation'] != 'rename'] + renames
        operations = lifecycle.order_removals(operations, current)
        # Statements for indexes and constraints are written with the pre-rename column
        # names; Firebird rewrites segments on ALTER COLUMN ... TO, so mixing them is unsafe.
        renamed = {item['before']['table'] for item in operations
                   if item['operation'] == 'rename' and item['kind'] == 'column'}
        mixed = sorted(item['resource_id'] for item in operations if item['kind'] in {'index', 'constraint'}
                       and item['operation'] != 'drop' and (item.get('after') or {}).get('table') in renamed)
        if mixed:
            raise ValueError('Review a column rename separately from index and constraint changes on the same table: ' + ', '.join(mixed))
        for conversion in ('alter_type', 'bind_domain'):
            if any(item['operation'] == conversion for item in operations) and any(item['operation'] != conversion for item in operations):
                raise ValueError('Domain conversion/rebinding requires a separate review before dependent definition/property edits')
    except ValueError as error:
        block('creation-graph', str(error))
    status = 'blocked' if blockers else 'review-ready' if operations else 'no-op'
    script = None if blockers else (f"-- Firebird 5 dialect {databases[0]['sql_dialect']} schema review artifact.\n"
        '-- Revalidate target metadata immediately before any execution.\n' +
        native_script([statement for phase in ('statements', 'deferred_statements')
                for operation in operations for statement in operation.get(phase, [])]))
    result = {'format': 'scratchrobin.firebird.schema-plan@1', 'status': status,
              'target': {key: current['provenance'][key] for key in ('endpoint_id', 'database_target_id', 'generation')},
              'engine_version': str(servers[0]['version']), 'sql_dialect': int(databases[0]['sql_dialect']),
              'database_identity': {key: databases[0].get(key) for key in ('guid', 'file_id')},
              'observation': current['provenance'].get('observation', 'unknown'),
              'catalog_coverage': current['provenance'].get('coverage', 'unknown'),
              'coverage': sorted(SUPPORTED | {'privilege'}), 'statistics': stats,
              'lifecycle_coverage': {'rename': ['column', 'domain'], 'alter_type': ['domain'],
                 'bind_domain': ['column'], 'replace': ['index'],
                 'drop': sorted(SUPPORTED | {'collation', 'external-function'})},
              'baseline_sha256': baseline['sha256'], 'desired_sha256': desired['sha256'],
              'current_sha256': current['sha256'], 'operations': operations,
              'current_hash_format': current.get('format', 'scratchrobin.firebird.catalog-ddn@1'),
              'blockers': blockers, 'script': script, 'apply_available': False,
              'warnings': ['Preview does not execute SQL or provide apply-time drift protection.',
                           'Current sequence values are preserved; sequence restart is not an initial-value alteration.']}
    if any(operation['kind'] == 'constraint' or (operation['kind'] == 'table' and operation['before'] is None
           and desired['rows'][operation['resource_id']]['native'].get('constraints')) for operation in operations):
        result['warnings'].append(constraints.WARNING)
    if any(operation.get('signature_first') for operation in operations):
        result['warnings'].append(ROUTINE_STAGE_WARNING)
    if any(operation['operation'] == 'alter_type' for operation in operations):
        result['warnings'].append('Native domain conversion can affect dependent columns. Firebird ALTER DOMAIN TYPE uses the target character set default collation; it does not retain an explicit nondefault collation.')
    if any(operation['operation'] == 'replace' for operation in operations):
        result['warnings'].append('Firebird has no ALTER INDEX for key, uniqueness, direction, computed or partial definitions: an index replacement is DROP INDEX and CREATE INDEX under the same name inside this transaction. The index is rebuilt at commit; a row that violates the new definition rolls back the whole review.')
    if any(operation['kind'] in {'index', 'constraint'} for operation in operations):
        result['warnings'].append('Firebird DDL runs in the one transaction of this review with every other statement and becomes visible only at commit. Firebird 5.0 has no rename for tables, views, indexes or constraints; those renames are not carried.')
    if any(operation['operation'] == 'drop' for operation in operations):
        result['warnings'].append('Explicit DROP permanently removes the selected objects and their owned children/data on commit. This review does not create a backup.')
    if any(operation.get('before_column_grants') for operation in operations):
        result['warnings'].append('Column rename revokes the observed column grants and grants them on the new name inside the same transaction. Original grantor authority and native grant checks are required.')
    if any(operation['kind'] == 'collation' for operation in operations):
        result['warnings'].append(collations.WARNING)
    if any(operation['kind'] == 'privilege' for operation in operations):
        result['warnings'].append('Security review preserves the exact native principal, grantor and grant options. Acknowledged native REVOKE cascades may remove dependent grants; re-discover security after execution.')
    if any(operation['kind'] == 'external-function' for operation in operations):
        result['warnings'].append(external_functions.WARNING)
    if any(operation['kind'] == 'blob-filter' for operation in operations):
        result['warnings'].append(filters.WARNING)
    if any(operation['kind'] == 'package' and operation['operation'] != 'drop' and (operation['before'] is None or
           any(operation['before'][key] != operation['after'][key] for key in ('header_source', 'sql_security')))
           for operation in operations):
        result['warnings'].append(packages.WARNING)
    result['execution_sha256'] = digest({key: result[key] for key in (
        'engine_version', 'sql_dialect', 'database_identity', 'status', 'operations')})
    result['plan_sha256'] = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return result
