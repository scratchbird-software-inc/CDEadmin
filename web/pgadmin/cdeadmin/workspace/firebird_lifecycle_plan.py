"""Explicit native identity transitions, never inferred from missing objects."""
from ..providers.firebird.identity import column_rename, domain_rename, catalog_resource_id
from ..providers.firebird.character_metadata import identifier
from .firebird_view_plan import dependencies
from .firebird_sql_export import grant_statement, DEPENDENCY_KINDS

INSTRUCTION = 'lifecycle'

GRANT_FIELDS = ('grantee', 'grantor', 'grant_option', 'user_type', 'object_type', 'privilege', 'object_name', 'field')


def plan(old, wanted, live, current, desired):
    if live is not None and live['system'] != 'false':
        raise ValueError('Lifecycle changes require an explicitly observed user object')
    intent = wanted['native'][INSTRUCTION]
    if isinstance(intent, dict) and intent.get('operation') == 'drop':
        return drop(old, wanted, live, current)
    if isinstance(intent, dict) and intent.get('operation') == 'type':
        return domain_type(old, wanted, live, current)
    if isinstance(intent, dict) and intent.get('operation') == 'bind_domain':
        return bind_domain(old, wanted, live, current)
    return rename(old, wanted, live, current, desired)


def bind_domain(old, wanted, live, current):
    from .firebird_schema_plan import native_guard, _model, _native_changes, DERIVED
    from . import firebird_domain_plan as domains
    from .firebird_column_plan import creation_model
    intent = wanted['native'][INSTRUCTION]
    if (wanted['kind'] != 'column' or set(intent) != {'operation', 'confirmation'}
            or old is None or live is None or INSTRUCTION in old['native']):
        raise ValueError('Domain rebinding requires an observed column and exact confirmation')
    if intent['confirmation'] != old['name'] or native_guard(old) != native_guard(live):
        raise ValueError('Domain rebinding requires exact confirmation and unchanged native facts')
    if _native_changes(old, wanted, DERIVED | domains.TYPE_FIELDS | {'domain', 'domain_not_null'}):
        raise ValueError('Domain rebinding cannot combine unrelated column edits')
    name = wanted['native'].get('domain')
    targets = [row for row in current['rows'].values() if row['kind'] == 'domain'
               and row['name'] == name and row['system'] == 'false']
    if len(targets) != 1 or name == old['native'].get('domain'):
        raise ValueError('Choose a different, observed user domain')
    for row in (live, wanted):
        native = row['native']
        if (native.get('computed_source') is not None or native.get('identity_type') is not None
                or str(native.get('dimensions') or '0') != '0' or str(native.get('field_type')) == '261'):
            raise ValueError('Domain rebinding requires an ordinary stored scalar column')
    before, after = _model(live), _model(wanted)
    cleaned = {**wanted, 'native': {key: value for key, value in wanted['native'].items() if key != INSTRUCTION}}
    after['creation_column'] = creation_model(cleaned, current, observed=True)
    guards = dependencies(current)
    return {'resource_id': wanted['resource_id'], 'kind': 'column', 'operation': 'bind_domain',
            'source_location': wanted.get('source_location'), 'before': before, 'after': after,
            'statements': ['ALTER TABLE ' + identifier(wanted['path'][0]) + ' ALTER COLUMN ' +
                           identifier(wanted['name']) + ' TYPE ' + identifier(name)],
            'deferred_statements': [], 'dependencies': guards, 'order_dependencies': [],
            'lifecycle_confirmation': intent['confirmation'], 'target_domain': name,
            'native_preconditions': {key: native_guard(current['rows'][key]) for key in guards},
            'precondition': 'Exact column, target domain and dependency facts',
            'permissions': 'Native ALTER authority, domain use and conversion admission required',
            'transaction': 'Native domain rebinding without row copying'}


def domain_type(old, wanted, live, current):
    from .firebird_schema_plan import native_guard, _model, _native_changes, DERIVED
    from . import firebird_domain_plan as domains
    intent = wanted['native'][INSTRUCTION]
    if (wanted['kind'] != 'domain' or set(intent) != {'operation', 'confirmation'}
            or old is None or live is None or INSTRUCTION in old['native']):
        raise ValueError('Type lifecycle requires an observed domain and exact confirmation')
    if intent['confirmation'] != old['name'] or native_guard(old) != native_guard(live):
        raise ValueError('Domain type change requires exact confirmation and unchanged native facts')
    if _native_changes(old, wanted, DERIVED | domains.TYPE_FIELDS):
        raise ValueError('Domain type lifecycle cannot combine unrelated property changes')
    domains.context(current)
    before, after = _model(live), _model(wanted)
    before['creation_type'] = domains.creation_model(live, current)
    after['creation_type'] = domains.creation_model(wanted, current)
    typed = after['creation_type']
    if before['creation_type']['dimensions'] or typed['dimensions']:
        raise ValueError('Native ALTER DOMAIN TYPE does not admit array layout changes')
    if before == after:
        raise ValueError('No domain type change was requested')
    if typed['collation'] is not None:
        charset = wanted['native'].get('character_set')
        observed = [row for row in current['rows'].values() if row['kind'] == 'character-set' and row['name'] == charset]
        if len(observed) != 1 or typed['collation'] != observed[0]['native'].get('default_collation'):
            raise ValueError('ALTER DOMAIN TYPE requires the target character set default collation')
    guards = dependencies(current)
    return {'resource_id': wanted['resource_id'], 'kind': 'domain', 'operation': 'alter_type',
            'source_location': wanted.get('source_location'), 'before': before, 'after': after,
            'statements': ['ALTER DOMAIN ' + identifier(wanted['name']) + ' TYPE ' + domains.render_type(typed)],
            'deferred_statements': [], 'dependencies': guards, 'order_dependencies': [],
            'lifecycle_confirmation': intent['confirmation'],
            'native_preconditions': {key: native_guard(current['rows'][key]) for key in guards},
            'precondition': 'Exact native domain and dependency facts',
            'permissions': 'Native ALTER DOMAIN authority and data conversion admission required',
            'transaction': 'Native conversion; never rebuild or copy values in the application'}


def drop(old, wanted, live, current):
    from .firebird_schema_plan import native_guard, _model
    from .firebird_index_plan import context as index_context
    intent = wanted['native'][INSTRUCTION]
    if set(intent) != {'operation', 'confirmation'} or old is None or live is None or INSTRUCTION in old['native']:
        raise ValueError('DROP requires an observed baseline and exact explicit confirmation')
    if intent['confirmation'] != old['name'] or not (native_guard(old) == native_guard(wanted) == native_guard(live)):
        raise ValueError('DROP requires exact name confirmation and unchanged native properties')
    kind = wanted['kind']
    kinds = {'table': 'TABLE', 'view': 'VIEW', 'domain': 'DOMAIN', 'sequence': 'SEQUENCE',
             'exception': 'EXCEPTION', 'procedure': 'PROCEDURE', 'function': 'FUNCTION',
             'package': 'PACKAGE', 'trigger': 'TRIGGER', 'index': 'INDEX', 'role': 'ROLE',
             'blob-filter': 'FILTER', 'collation': 'COLLATION', 'external-function': 'EXTERNAL FUNCTION'}
    if kind not in kinds and kind not in {'column', 'constraint'}:
        raise ValueError('This object requires its specialized removal workflow')
    if kind in {'collation', 'external-function'}:
        if live['path'] != [live['name']] or live['resource_id'] != catalog_resource_id(kind, [], live['name']):
            raise ValueError('Removal requires an exact standalone native identity')
        before = {'name': live['name'], 'description': live['native'].get('description')}
    else:
        before = _model(live)
    if kind == 'index':
        index_context(live, current, before['segments'])
    if kind == 'constraint' and before['constraint_type'] == 'NOT NULL':
        raise ValueError('NOT NULL removal requires the column nullability workflow')
    if kind in {'column', 'constraint'}:
        if not any(row['kind'] == 'table' and row['name'] == live['path'][0]
                   and row['system'] == 'false' for row in current['rows'].values()):
            raise ValueError('Child removal requires an observed user table')
        statement = ('ALTER TABLE ' + identifier(live['path'][0]) + ' DROP ' +
                     ('CONSTRAINT ' if kind == 'constraint' else '') + identifier(live['name']))
    else:
        statement = 'DROP ' + kinds[kind] + ' ' + identifier(live['name'])
    guards = sorted(set(dependencies(current)) | {key for key, row in current['rows'].items() if row['kind'] == 'privilege'})
    children = [key for key, row in current['rows'].items()
                if kind in {'table', 'view', 'package'} and row['path'][:-1] == live['path']
                and row['kind'] in {'column', 'index', 'constraint', 'trigger', 'function', 'procedure'}]
    return {'resource_id': wanted['resource_id'], 'kind': kind, 'operation': 'drop',
            'source_location': wanted.get('source_location'), 'before': before, 'after': None,
            'statements': [], 'deferred_statements': [statement], 'implicit_child_removals': sorted(children),
            'dependencies': guards, 'order_dependencies': [], 'lifecycle_confirmation': intent['confirmation'],
            'native_preconditions': {key: native_guard(current['rows'][key]) for key in guards},
            'precondition': 'Unchanged native object and exact removal confirmation',
            'permissions': 'Native DROP/ALTER authority and dependency admission required',
            'transaction': 'Destructive removal in the owned native transaction'}


def order_removals(operations, current):
    selected = {item['resource_id']: item for item in operations if item['operation'] == 'drop'}
    edges = {key: set() for key in selected}
    for key in selected:
        row = current['rows'][key]
        references = [(item.get('package_name') or item.get('object_name'),
                       {'package'} if item.get('package_name') else DEPENDENCY_KINDS.get(item.get('object_type_code'), set()))
                      for item in row['native'].get('dependencies') or []]
        if len(row['path']) > 1:
            references.append((row['path'][0], {'table', 'view', 'package'}))
        constraints = row['native'].get('constraints', []) if row['kind'] == 'table' else [row['native']] if row['kind'] == 'constraint' else []
        if row['kind'] == 'table':
            removed_constraints = {current['rows'][item]['name'] for item in selected
                                   if current['rows'][item]['kind'] == 'constraint'
                                   and current['rows'][item]['path'][0] == row['name']}
            constraints = [item for item in constraints if item.get('name') not in removed_constraints]
        typed = row['native'].get('columns', []) if row['kind'] in {'table', 'view'} else row['native'].get('parameters', []) if row['kind'] in {'procedure', 'function', 'external-function'} else [row['native']] if row['kind'] in {'column', 'domain'} else []
        references.extend((item.get('domain'), {'domain'}) for item in typed)
        references.extend((item.get('collation'), {'collation'}) for item in typed)
        references.extend((item.get('referenced_relation'), {'table'}) for item in constraints)
        for name, kinds in references:
            for parent in selected:
                candidate = current['rows'][parent]
                if parent != key and candidate['kind'] in kinds and candidate['name'] == name:
                    edges[parent].add(key)
    result = []
    while edges:
        ready = sorted(key for key, required in edges.items() if not required)
        if not ready:
            raise ValueError('Removal dependency cycle requires an explicit reconstruction plan')
        for key in ready:
            result.append(selected[key]); del edges[key]
        for required in edges.values(): required.difference_update(ready)
    return [item for item in operations if item['operation'] != 'drop'] + result


def column_grants(catalog, table, field):
    rows = [row for row in catalog['rows'].values() if row['kind'] == 'privilege'
            and row['native'].get('object_type') == 0 and row['native'].get('object_name') == table
            and row['native'].get('field') == field]
    return sorted([{key: row['native'].get(key) for key in GRANT_FIELDS} for row in rows], key=repr)


def rename(old, wanted, live, current, desired):
    # Import at execution time to share the planner's canonical guard/model.
    from .firebird_schema_plan import native_guard, _model
    intent = wanted['native'][INSTRUCTION]
    if (not isinstance(intent, dict) or set(intent) != {'operation', 'confirmation', 'new_name'}
            or intent['operation'] != 'rename'):
        raise ValueError('Explicit rename requires operation, confirmation and new_name')
    if old is None or live is None or INSTRUCTION in old['native']:
        raise ValueError('Rename requires an observed original baseline and current object')
    if intent['confirmation'] != old['name']:
        raise ValueError('Rename confirmation must equal the original native name')
    if not (native_guard(old) == native_guard(wanted) == native_guard(live)):
        raise ValueError('Rename cannot combine property changes or overwrite native drift')
    kind = wanted['kind']
    if kind not in {'column', 'domain'}:
        raise ValueError('This kind has no admitted native rename operation')
    before = _model(live)
    transition = (column_rename if kind == 'column' else domain_rename)(
        live['path'], intent['new_name'])
    destination = transition['resource_id']
    if destination in current['rows'] or destination in desired['rows']:
        raise ValueError('Rename destination is already present or independently authored')
    before_grants, after_grants, revokes, grants = [], [], [], []
    if kind == 'column':
        parent = next((row for row in current['rows'].values() if row['kind'] == 'table'
                       and row['name'] == transition['table']), None)
        if parent is None or parent['system'] != 'false':
            raise ValueError('Column rename requires an observed user table')
        observations = [item for row in current['rows'].values() if row['kind'] == 'database'
                        for item in row['native'].get('catalog_observations', [])]
        if not any(item.get('section') == 'object privileges' and item.get('available') is True for item in observations):
            raise ValueError('Column rename requires an available object privileges observation')
        before_grants = column_grants(current, transition['table'], transition['old_name'])
        after_grants = [{**item, 'field': transition['new_name']} for item in before_grants]
        revokes = [grant_statement({**item, 'target_resolution': {'state': 'resolved'}}, 'revoke') for item in before_grants]
        grants = [grant_statement({**item, 'target_resolution': {'state': 'resolved'}}) for item in after_grants]
        statement = ('ALTER TABLE ' + identifier(transition['table']) + ' ALTER COLUMN ' +
                     identifier(transition['old_name']) + ' TO ' + identifier(transition['new_name']))
    else:
        statement = 'ALTER DOMAIN ' + identifier(transition['old_name']) + ' TO ' + identifier(transition['new_name'])
    guards = dependencies(current) + [key for key, row in current['rows'].items() if row['kind'] == 'privilege']
    return {'resource_id': wanted['resource_id'], 'result_resource_id': destination,
            'kind': kind, 'source_location': wanted.get('source_location'),
            'operation': 'rename', 'before': before,
            'after': {**before, 'name': transition['new_name']},
            'rename_transition': transition, 'lifecycle_confirmation': intent['confirmation'],
            'statements': [], 'deferred_statements': [*revokes, statement, *grants],
            'rename_statement_index': len(revokes), 'before_column_grants': before_grants,
            'after_column_grants': after_grants,
            'dependencies': guards, 'order_dependencies': [],
            'native_preconditions': {key: native_guard(current['rows'].get(key))
                                     for key in [*guards, destination]},
            'precondition': 'Exact original native facts and absent destination',
            'permissions': 'Native ALTER authority and dependency admission required',
            'transaction': 'Verify retained native identity in the owned transaction'}
