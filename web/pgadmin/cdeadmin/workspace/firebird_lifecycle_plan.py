"""Explicit native identity transitions, never inferred from missing objects."""
import re

from ..providers.firebird.identity import column_rename, domain_rename, catalog_resource_id
from ..providers.firebird.character_metadata import identifier
from .firebird_view_plan import dependencies
from .firebird_sql_export import grant_statement, DEPENDENCY_KINDS
from .firebird_physical import NOT_CARRIED

INSTRUCTION = 'lifecycle'

GRANT_FIELDS = ('grantee', 'grantor', 'grant_option', 'user_type', 'object_type', 'privilege', 'object_name', 'field')


def plan(old, wanted, live, current, desired):
    """One operation, or None when the live catalog already shows the intended outcome
    (a replayed review converges instead of failing)."""
    if live is not None and live['system'] != 'false':
        raise ValueError('Lifecycle changes require an explicitly observed user object')
    intent = wanted['native'][INSTRUCTION]
    if isinstance(intent, dict) and intent.get('operation') == 'drop':
        return drop(old, wanted, live, current, desired)
    if isinstance(intent, dict) and intent.get('operation') == 'replace':
        return replace_index(old, wanted, live, current)
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


def drop(old, wanted, live, current, desired=None):
    from .firebird_schema_plan import native_guard, _model
    from .firebird_index_plan import context as index_context
    intent = wanted['native'][INSTRUCTION]
    if set(intent) != {'operation', 'confirmation'} or old is None or INSTRUCTION in old['native']:
        raise ValueError('DROP requires an observed baseline and exact explicit confirmation')
    if intent['confirmation'] != old['name']:
        raise ValueError('DROP requires exact name confirmation and unchanged native properties')
    if live is None:
        return None  # Already absent: the drop converged.
    if not (native_guard(old) == native_guard(wanted) == native_guard(live)):
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
    implicit = _removal_guards(kind, live, current, desired) if desired is not None else []
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
    children = sorted(set(children) | set(implicit))
    return {'resource_id': wanted['resource_id'], 'kind': kind, 'operation': 'drop',
            'source_location': wanted.get('source_location'), 'before': before, 'after': None,
            'statements': [], 'deferred_statements': [statement], 'implicit_child_removals': sorted(children),
            'dependencies': guards, 'order_dependencies': [], 'lifecycle_confirmation': intent['confirmation'],
            'destructive': True, 'confirmation': intent['confirmation'],
            'native_preconditions': {key: native_guard(current['rows'][key]) for key in guards},
            'precondition': 'Unchanged native object and exact removal confirmation',
            'permissions': 'Native DROP/ALTER authority and dependency admission required',
            'transaction': 'Destructive removal in the owned native transaction'}


def _removed(desired, row):
    """True when the desired document also removes this row (or its table) with its own confirmation."""
    def dropped(candidate):
        wanted = desired['rows'].get(candidate['resource_id'])
        intent = wanted['native'].get(INSTRUCTION) if wanted else None
        return isinstance(intent, dict) and intent.get('operation') == 'drop' and intent.get('confirmation') == candidate['name']
    if dropped(row):
        return True
    if len(row['path']) > 1:
        table = desired['rows'].get(catalog_resource_id('table', [], row['path'][0]))
        return table is not None and dropped(table)
    return False


def _mentions(source, name):
    """Conservative identifier search in native expression text."""
    return isinstance(source, str) and re.search(r'(?<![\w$])"?' + re.escape(name) + r'"?(?![\w$])', source, re.I) is not None


def _column_users(live, current):
    """Rows of the same table that use a column: (constraints, standalone indexes, computed indexes)."""
    table, name = live['path']
    backed = {row['native'].get('index_name') for row in current['rows'].values()
              if row['kind'] == 'constraint' and row['path'][0] == table}
    constraints, indexes, computed = [], [], []
    for row in current['rows'].values():
        if row['path'][:1] != [table]:
            continue
        native = row['native']
        if row['kind'] == 'constraint':
            segments = (native.get('backing_index') or {}).get('segments') or []
            if (any(item.get('field_name') == name for item in segments) or
                    (native.get('constraint_type') == 'CHECK' and _mentions(native.get('check_source'), name))):
                constraints.append(row)
        elif row['kind'] == 'index' and row['name'] not in backed:
            if _mentions(native.get('expression_source'), name) or _mentions(native.get('condition_source'), name):
                computed.append(row)
            elif any(item.get('field_name') == name for item in native.get('segments') or []):
                indexes.append(row)
    return constraints, indexes, computed


def _key_users(row, current, desired):
    """Foreign keys of other constraints that need this PRIMARY KEY/UNIQUE and are not removed with it."""
    return [item['name'] for item in current['rows'].values() if item['kind'] == 'constraint'
            and item['native'].get('constraint_type') == 'FOREIGN KEY'
            and item['native'].get('referenced_relation') == row['path'][0]
            and item['native'].get('referenced_index') == row['native'].get('index_name')
            and not _removed(desired, item)]


def _removal_guards(kind, live, current, desired):
    """Dependencies Firebird 5.0 refuses at DROP, proven from the observed catalog, and the
    constraints and backing indexes that Firebird removes implicitly. Returns the implicit rids."""
    implicit = []
    if kind == 'constraint':
        index = catalog_resource_id('index', live['path'][:1], live['native'].get('index_name'))
        if live['native'].get('index_name') and index in current['rows']:
            implicit.append(index)  # The backing index goes with its constraint.
    if kind == 'constraint' and live['native'].get('constraint_type') in {'PRIMARY KEY', 'UNIQUE'}:
        users = _key_users(live, current, desired)
        if users:
            raise ValueError('Foreign keys depend on this key and are not removed by the same review: ' + ', '.join(sorted(users)))
    if kind == 'table':
        users = sorted(row['name'] for row in current['rows'].values() if row['kind'] == 'constraint'
                       and row['native'].get('constraint_type') == 'FOREIGN KEY'
                       and row['native'].get('referenced_relation') == live['name'] and row['path'][0] != live['name']
                       and not _removed(desired, row))
        if users:
            raise ValueError('Foreign keys of other tables reference this table and are not removed by the same review: ' + ', '.join(users))
    if kind == 'column':
        constraints, indexes, computed = _column_users(live, current)
        blocking = sorted(row['name'] for row in [*indexes, *computed] if not _removed(desired, row))
        if blocking:
            raise ValueError('Firebird refuses to drop column ' + live['name'] + ' while indexes use it; remove them in the same review: ' + ', '.join(blocking))
        for row in constraints:
            if row['native'].get('constraint_type') in {'PRIMARY KEY', 'UNIQUE'}:
                users = _key_users(row, current, desired)
                if users:
                    raise ValueError('Dropping column ' + live['name'] + ' would remove ' + row['name'] + ' that foreign keys depend on: ' + ', '.join(sorted(users)))
            if not _removed(desired, row):
                implicit.append(row['resource_id'])
                index = catalog_resource_id('index', row['path'][:1], row['native'].get('index_name'))
                if row['native'].get('index_name') and index in current['rows']:
                    implicit.append(index)
    return sorted(set(implicit))


def _rename_blockers(live, current):
    """Column uses for which Firebird 5.0 refuses ALTER COLUMN ... TO (plain indexes are rewritten)."""
    constraints, _, computed = _column_users(live, current)
    return sorted(row['name'] for row in [*constraints, *computed])


def replace_index(old, wanted, live, current):
    """Explicit rebuild of a standalone index whose key, uniqueness, direction, computed
    expression or condition changed. Firebird has no ALTER INDEX for any of these, so the
    reviewed outcome is DROP INDEX and CREATE INDEX under the same name inside one
    transaction. The index data is rebuilt at commit; a uniqueness violation in existing
    rows fails the whole review and nothing is committed."""
    from .firebird_schema_plan import native_guard, _model, _native_changes, DERIVED
    from . import firebird_index_plan as indexes
    from ..providers.firebird.character_metadata import literal
    intent = wanted['native'][INSTRUCTION]
    if (wanted['kind'] != 'index' or set(intent) != {'operation', 'confirmation'} or old is None
            or INSTRUCTION in old['native']):
        raise ValueError('Index replacement requires an observed standalone index and exact confirmation')
    if intent['confirmation'] != old['name']:
        raise ValueError('Index replacement confirmation must equal the exact index name')
    if _native_changes(old, wanted, DERIVED | indexes.FIELDS | {'statistics'}):
        raise ValueError('Index replacement cannot combine unrelated property changes')
    if live is None:
        raise ValueError('Native index no longer exists')
    before, after, actual = _model(old), _model(wanted), _model(live)
    if actual == after:
        return None  # The live index already has the reviewed definition.
    if native_guard(old) != native_guard(live):
        raise ValueError('Native index changed independently since the baseline')
    if before == after:
        raise ValueError('No index definition change was requested')
    owner = indexes.context(live, current, after['segments'])
    statements = ['DROP INDEX ' + identifier(live['name']), *indexes.statements(None, after)]
    if after['description'] is not None:
        statements.append('COMMENT ON INDEX ' + identifier(live['name']) + ' IS ' + literal(after['description']))
    guards = sorted({owner, *dependencies(current)})
    return {'resource_id': wanted['resource_id'], 'kind': 'index', 'operation': 'replace',
            'source_location': wanted.get('source_location'), 'before': actual, 'after': after,
            'statements': statements, 'deferred_statements': [], 'dependencies': guards,
            'order_dependencies': [owner], 'lifecycle_confirmation': intent['confirmation'],
            'replacement': True,
            'native_preconditions': {key: native_guard(current['rows'].get(key)) for key in [wanted['resource_id'], *guards]},
            'precondition': 'Exact native index definition and exact replacement confirmation',
            'permissions': 'Native DROP INDEX and CREATE INDEX authority on the owning table required',
            'transaction': ('DROP INDEX then CREATE INDEX in the one owned transaction; the index is rebuilt at '
                            'commit and any rejected row rolls back the whole review')}


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
    kind = wanted['kind']
    if kind not in {'column', 'domain'}:
        raise ValueError('Not carried to Firebird: ' + NOT_CARRIED.get(kind, 'this object kind has no native rename statement'))
    if old is None or INSTRUCTION in old['native']:
        raise ValueError('Rename requires an observed original baseline and current object')
    if intent['confirmation'] != old['name']:
        raise ValueError('Rename confirmation must equal the original native name')
    if live is None:
        moved = current['rows'].get((column_rename if kind == 'column' else domain_rename)(
            old['path'], intent['new_name'])['resource_id'])
        if moved is not None and _model(moved) == {**_model(old), 'name': intent['new_name']}:
            return None  # The reviewed rename already happened.
        raise ValueError('Rename requires an observed original baseline and current object')
    if not (native_guard(old) == native_guard(wanted) == native_guard(live)):
        raise ValueError('Rename cannot combine property changes or overwrite native drift')
    before = _model(live)
    transition = (column_rename if kind == 'column' else domain_rename)(
        live['path'], intent['new_name'])
    destination = transition['resource_id']
    if destination in current['rows'] or destination in desired['rows']:
        raise ValueError('Rename destination is already present or independently authored')
    before_grants, after_grants, revokes, grants = [], [], [], []
    if kind == 'column':
        blockers = _rename_blockers(live, current)
        if blockers:
            raise ValueError('Firebird 5.0 refuses ALTER COLUMN ... TO while a PRIMARY KEY, UNIQUE, FOREIGN KEY, CHECK or '
                             'computed index uses the column (' + ', '.join(blockers) + '); this rename is not carried')
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
