"""Three-way SQLite DDN preview with a deliberately bounded native DDL set."""

import re
import sqlite3

from .firebird_catalog_import import _equal
from .firebird_schema_plan import digest
from ..providers.sqlite.provider import _resource_id

FORMAT = 'scratchrobin.sqlite.schema-plan@1'
CREATABLE = {'table', 'view', 'index', 'trigger', 'fts-table', 'virtual-table'}


def _quote(name):
    if not isinstance(name, str) or not name or '\x00' in name or len(name.encode('utf8')) > 1024 * 1024:
        raise ValueError('Invalid SQLite schema identifier')
    return '"' + name.replace('"', '""') + '"'


def _scope(model):
    if model.get('provenance',{}).get('observation_scope')=='retained-session' or any(
            row.get('native',{}).get('observation_scope')=='retained-session' for row in model.get('rows',{}).values()):
        raise ValueError('Retained-session observations cannot authorize an independent SQLite migration')
    provenance = model['provenance']
    if provenance.get('mapping') != 'scratchrobin.sqlite.catalog@1':
        raise ValueError('Native SQLite DDN catalog is required')
    roots = [row for row in model['rows'].values()
             if row['kind'] == 'database' and row['path'] == ['main'] and row['system'] == 'false']
    if len(roots) != 1:
        raise ValueError('One exact SQLite main file root is required')
    return provenance['endpoint_id'], provenance['database_target_id']


def _definition(row):
    if row is None:
        return None
    native = row['native']
    result={'kind': row['kind'], 'path': row['path'], 'name': row['name'],
        'system': row['system'], 'ddl': _normalized_ddl(row),
        'catalog_metadata': native.get('catalog_metadata')}
    if row['kind']=='fts-table':
        from ..providers.sqlite.fts_configuration import identity
        result['fts_configuration']=identity(native.get('fts_configuration'))
    return result


def _normalized_ddl(row, *, strict=False):
    ddl=row['native'].get('ddl')
    if row['kind'] not in CREATABLE or not isinstance(ddl,str) or not ddl:
        return ddl
    if not isinstance(row.get('path'),(list,tuple)) or not row['path']:
        if strict:raise ValueError('Native SQLite declaration namespace is unavailable')
        return ddl
    from ..providers.sqlite.declarations import canonical_create
    metadata=row['native'].get('catalog_metadata',{})
    try:
        source=canonical_create(ddl,row['kind'],row['path'][0],row['name'],
            owner=metadata.get('table_name') if row['kind'] in {'index','trigger'} else None,
            owner_schema=metadata.get('owner_database') if row['path'][0]=='temp' else row['path'][0])
        return source if strict else source.strip().rstrip(';')
    except ValueError:
        if strict:raise
        return ddl


def _source(row):
    kind, path, name = row['kind'], row['path'], row['name']
    if kind not in CREATABLE | {'column'} or row['system'] != 'false' or row['native'].get('system_object') is not False:
        raise ValueError('Only user-owned native SQLite schema additions are admitted')
    if len(path) != (3 if kind in {'index', 'trigger', 'column'} else 2) or path[0] != 'main' or path[-1] != name:
        raise ValueError('SQLite creation must belong to the main registered file')
    if row['resource_id'] != _resource_id(kind, path[:-1], name):
        raise ValueError('SQLite native resource identity is inconsistent')
    ddl = row['native'].get('ddl')
    if (not isinstance(ddl, str) or not ddl.strip() or '\x00' in ddl or
            len(ddl.encode('utf8')) > 1024 * 1024 or
            not sqlite3.complete_statement(ddl.rstrip() + ';' if not ddl.rstrip().endswith(';') else ddl)):
        raise ValueError('One bounded complete native SQLite CREATE statement is required')
    if kind in CREATABLE:
        _quote(name)
        if kind in {'index','trigger'} and row['native'].get('catalog_metadata',{}).get('table_name')!=path[1]:
            raise ValueError('SQLite declaration owner differs from native metadata')
        ddl=_normalized_ddl(row,strict=True)
    if kind == 'column':
        prefix = (r'^\s*ALTER\s+TABLE\s+' + re.escape(_quote('main') + '.' + _quote(path[1])) +
                  r'\s+ADD\s+COLUMN\s+' + re.escape(_quote(name)) + r'\s+')
        metadata = row['native'].get('catalog_metadata', {})
        if (metadata.get('hidden') not in (None, 0) or
                metadata.get('primary_key_position') not in (None, 0) or
                not isinstance(metadata.get('data_type'), str) or
                not metadata['data_type']):
            raise ValueError('SQLite column addition requires ordinary declared native type facts')
        pattern = prefix + re.escape(metadata['data_type']) + r'(?=\s|;|$)'
    elif kind in {'fts-table', 'virtual-table'}:
        from ..providers.sqlite.modules import declaration
        native=declaration(ddl)
        if (native is None or native[0]!=name or native[2]!='main' or
                (native[1].lower() in {'fts3','fts4','fts5'})!=(kind=='fts-table')):
            raise ValueError('Native virtual-table module, target or kind differs from the desired SQLite object')
        if row['native'].get('catalog_metadata', {}).get('table_list_type') not in (None, 'virtual'):
            raise ValueError('SQLite virtual table kind differs from native metadata')
        if kind=='fts-table' and row['native'].get('fts_configuration') is not None:
            from ..providers.sqlite.fts_configuration import validate
            configuration=row['native']['fts_configuration']
            if configuration.get('module')!=native[1].lower():raise ValueError('Native FTS configuration belongs to another module')
            validate(configuration)
        return ddl
    else:
        # Declaration names and owners are bound above; native EXPLAIN and its
        # authorizer facts own grammar, including SQLite's optional timing and
        # comments/spacing between header tokens.
        return ddl
    if not re.match(pattern, ddl, re.I):
        raise ValueError('DDL must name the exact quoted SQLite object and owning table')
    # sqlite3.execute rejects multiple statements. EXPLAIN compiles the exact
    # native grammar without executing the CREATE VM or its trigger body.
    return ddl


def _require_virtual_module(connection, row, source):
    if row['kind'] not in {'fts-table', 'virtual-table'}:
        return
    from ..providers.sqlite.modules import declaration
    native=declaration(source)
    if native is None:
        raise ValueError('SQLite virtual table module is missing')
    fold=str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')
    available = {str(item[0]).translate(fold)
                 for item in connection.execute('PRAGMA module_list')}
    if native[1].translate(fold) not in available:
        raise ValueError('SQLite virtual table module is not installed')


def _compile_exact(connection, row, source):
    """Use SQLite's own authorizer facts to bind compiled DDL to its owner."""
    actions = []
    relevant = {sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_CREATE_VIEW,
                sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_CREATE_TRIGGER,
                sqlite3.SQLITE_CREATE_VTABLE, sqlite3.SQLITE_ALTER_TABLE}
    def record(action, name, owner, database, _context):
        if action in relevant:
            actions.append((action, name, owner, database))
        return sqlite3.SQLITE_OK
    connection.set_authorizer(record)
    try:
        cursor = connection.execute('EXPLAIN ' + source)
        try:
            cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.set_authorizer(None)
    kind = row['kind']
    action = {'table': sqlite3.SQLITE_CREATE_TABLE,
              'view': sqlite3.SQLITE_CREATE_VIEW,
              'index': sqlite3.SQLITE_CREATE_INDEX,
              'trigger': sqlite3.SQLITE_CREATE_TRIGGER,
              'fts-table': sqlite3.SQLITE_CREATE_VTABLE,
              'virtual-table': sqlite3.SQLITE_CREATE_VTABLE,
              'column': sqlite3.SQLITE_ALTER_TABLE}[kind]
    from ..providers.sqlite.modules import declaration
    module = declaration(source) if kind in {'fts-table','virtual-table'} else None
    expected = ((action, 'main', row['path'][1], None) if kind == 'column'
                else (action, row['name'], row['path'][1] if kind in {'index', 'trigger'}
                      else module[1] if module else None, 'main'))
    if len([item for item in actions if item[0] == action]) != 1 or expected not in actions:
        raise ValueError('SQLite native compiled DDL targets a different object or owner')


def batch_blockers(operations, desired):
    """Keep preservation contracts explicit when combining admitted stages."""
    blockers=[]
    mixed=any(item['operation']=='drop' for item in operations) and any(item['operation']!='drop' for item in operations)
    if mixed and any(item['operation']=='drop' and item.get('kind') not in {'view','index','trigger'} for item in operations):
        blockers.append('Review deletion separately from additions')
    rebuilt={item['name'] for item in operations if item['operation']=='rebuild'}
    for item in operations:
        row=desired['rows'].get(item['resource_id'])
        if item['operation']!='rebuild' and row and row['kind'] in {'column','index','trigger'} and len(row['path'])==3 and row['path'][0]=='main' and row['path'][1] in rebuilt:
            blockers.append('Changes to a rebuilt table\'s own columns, indexes or triggers require coordinated dependency rewriting')
    return blockers


def _created_owner(row, desired, baseline):
    """Bind a child to an ordinary relation added by this same native plan."""
    if row['kind'] not in {'index', 'trigger'}:
        return None
    kinds = {'table', 'view'} if row['kind'] == 'trigger' else {'table'}
    owners = [desired['rows'].get(_resource_id(kind, ['main'], row['path'][1]))
              for kind in kinds]
    owners = [owner for owner in owners if owner is not None and
              owner['resource_id'] not in baseline['rows']]
    if len(owners) > 1:
        raise ValueError('SQLite child has ambiguous new relation ownership')
    return owners[0] if owners else None


def _compile_created_child(row, source, owner):
    # A separate empty native database provides the new owner for EXPLAIN.
    # No CREATE or trigger DML is executed on the registered file at preview.
    probe = sqlite3.connect(':memory:')
    try:
        probe.execute(_source(owner))
        _compile_exact(probe, row, source)
    finally:
        probe.close()


def plan(baseline, desired, live, connection, *, deletions=(), rebuilds=(),
         column_renames=(), renames=(), fts_rebindings=()):
    scope = _scope(baseline)
    if _scope(desired) != scope or _scope(live) != scope:
        raise ValueError('Native designs refer to different registered SQLite files')
    def file_identity(model):
        return next(row['native'].get('registered_file_identity')
            for row in model['rows'].values()
            if row['kind'] == 'database' and row['path'] == ['main'])
    if (file_identity(baseline) != file_identity(desired) or
            file_identity(baseline) != file_identity(live)):
        raise ValueError('Native designs refer to different SQLite file identities')
    if renames:
        if deletions or rebuilds or column_renames:
            raise ValueError('Review native renames separately from rebuilds and other transformations')
        from .sqlite_rename import plan as rename_plan
        return rename_plan(baseline,desired,live,renames,fts_rebindings)
    if fts_rebindings:raise ValueError('FTS rebinding requires an explicit native owner rename')
    operations, blockers, conflicts = [], [], []
    before, after, current = baseline['rows'], desired['rows'], live['rows']
    if (not isinstance(deletions, (list, tuple)) or len(deletions) > 32 or
            any(not isinstance(item, str) or not item for item in deletions) or
            len(set(deletions)) != len(deletions)):
        raise ValueError('SQLite deletion intent requires at most 32 distinct native identities')
    deletions = set(deletions)
    if (not isinstance(rebuilds, (list, tuple)) or len(rebuilds) > 32 or
            any(not isinstance(item, str) or not item for item in rebuilds) or
            len(set(rebuilds)) != len(rebuilds) or set(rebuilds) & deletions):
        raise ValueError('SQLite rebuild intent requires distinct nondeleted table identities')
    rebuilds = set(rebuilds)
    if (not isinstance(column_renames, (list, tuple)) or len(column_renames) > 16 or
            any(not isinstance(item, dict) or set(item) != {'table', 'from', 'to'} or
                any(not isinstance(item[key], str) or not item[key] or '\x00' in item[key]
                    for key in ('table', 'from', 'to'))
                for item in column_renames)):
        raise ValueError('SQLite column rename intent requires bounded exact mappings')
    rename_maps = {}
    for item in column_renames:
        if item['table'] not in rebuilds or item['from'] in rename_maps.setdefault(item['table'], {}):
            raise ValueError('SQLite column rename must belong to one selected rebuild')
        rename_maps[item['table']][item['from']] = item['to']
    if any(len(set(mapping.values())) != len(mapping) for mapping in rename_maps.values()):
        raise ValueError('SQLite column rename targets must be distinct')
    if len(after) > 20_000:
        raise ValueError('SQLite design exceeds 20,000 native facts')
    created_relations = {row['resource_id'] for row in after.values()
        if row['kind'] in {'table', 'view', 'fts-table', 'virtual-table'} and row['resource_id'] not in before}
    replaced_views={identity for identity,row in after.items() if row['kind']=='view' and identity in before and
        not _equal(_definition(before[identity]),_definition(row))}
    def derived_view_column(row):
        return (row['kind']=='column' and len(row['path'])==3 and row['path'][0]=='main' and
            _resource_id('view',['main'],row['path'][1]) in replaced_views)
    for identity in sorted(rebuilds):
        old, wanted = before.get(identity), after.get(identity)
        if old is None or wanted is None or old['kind'] != 'table':
            blockers.append({'resource_id': identity, 'name': identity,
                'reason': 'SQLite rebuild requires the same observed user table in both designs'})
            continue
        if identity not in current or not _equal(_definition(old), _definition(current[identity])):
            conflicts.append({'resource_id': identity, 'name': old['name'],
                'reason': 'SQLite rebuild source changed since baseline'})
            continue
        baseline_children = {child_id: child for child_id, child in before.items()
            if child_id != identity and child['path'][:len(old['path'])] == old['path']}
        live_children = {child_id: child for child_id, child in current.items()
            if child_id != identity and child['path'][:len(old['path'])] == old['path']}
        if (set(baseline_children) != set(live_children) or
                any(not _equal(_definition(child), _definition(live_children[child_id]))
                    for child_id, child in baseline_children.items())):
            conflicts.append({'resource_id': identity, 'name': old['name'],
                'reason': 'SQLite rebuild child definitions changed since baseline'})
            continue
        try:
            from .sqlite_rebuild import plan_rebuild
            operation = plan_rebuild(old, wanted, baseline, connection,
                column_renames=rename_maps.get(identity),desired=desired,
                child_deletions=sorted(child_id for child_id in deletions if child_id in baseline_children and baseline_children[child_id]['kind'] in {'index','trigger'}))
            expected_ids = {_resource_id('column', old['path'], item['name'])
                for item in operation['target_columns']}
            present = {row_id for row_id, row in after.items()
                if row['kind'] == 'column' and row['path'][:2] == old['path']}
            if present != expected_ids:
                raise ValueError('Desired DDN must contain every rebuilt SQLite column record')
            for item in operation['target_columns']:
                column = after[_resource_id('column', old['path'], item['name'])]
                facts = column['native'].get('catalog_metadata', {})
                if any(facts.get(key) != value for key, value in {
                        'data_type': item['type'], 'primary_key_position': item['pk'],
                        'hidden': item['hidden'], 'ordinal_position': item['ordinal_position'],
                        'nullable': item['nullable'], 'default': item['default']}.items()):
                    raise ValueError('Desired SQLite column record differs from native CREATE TABLE')
            operations.append(operation)
        except (ValueError, sqlite3.Error) as error:
            blockers.append({'resource_id': identity, 'name': old['name'],
                'reason': str(error)[:400]})
    for identity, row in sorted(after.items()):
        if identity in before:
            old = before[identity]
            observed = current.get(identity)
            rebuilding_child = (len(row['path']) > 2 and
                _resource_id('table', ['main'], row['path'][1]) in rebuilds and
                row['kind'] in {'column', 'constraint', 'index', 'trigger'})
            rebuilding_child = rebuilding_child or derived_view_column(row)
            if observed is None or not _equal(_definition(old), _definition(observed)):
                if row['kind'] not in {'database', 'pragma', 'extension', 'metric', 'native-function', 'collation', 'compile-option'}:
                    conflicts.append({'resource_id': identity, 'name': row['name'],
                        'reason': 'Native baseline differs from the freshly observed file'})
            if row['kind'] in {'database', 'pragma', 'extension', 'metric', 'native-function', 'collation', 'compile-option'}:
                continue
            if not _equal(_definition(old), _definition(row)) and identity not in rebuilds and not rebuilding_child:
                if row['kind'] == 'fts-table' and observed is not None:
                    try:
                        from .sqlite_fts_settings import plan as configure
                        operations.append(configure(old, row))
                    except (ValueError, sqlite3.Error) as error:
                        blockers.append({'resource_id': identity, 'name': row['name'], 'reason': str(error)[:400]})
                elif row['kind'] in {'view','index', 'trigger'} and observed is not None:
                    try:
                        from .sqlite_replace import plan_replace,validate_view_children
                        if row['kind']=='view':validate_view_children(row,desired)
                        operations.append(plan_replace(old, row, baseline, connection))
                    except (ValueError, sqlite3.Error) as error:
                        blockers.append({'resource_id': identity, 'name': row['name'], 'reason': str(error)[:400]})
                else:
                    blockers.append({'resource_id': identity, 'name': row['name'],
                        'reason': 'Changing an existing native definition requires a separately qualified SQLite migration'})
            continue
        if derived_view_column(row):continue  # The defining SELECT owns its columns.
        if (row['kind'] in {'index','trigger'} and len(row['path'])==3 and row['path'][0]=='main' and
                _resource_id('table',['main'],row['path'][1]) in rebuilds):
            continue  # The coordinated rebuild compiles and creates this child.
        if row['kind'] in {'column', 'constraint', 'index'} and len(row['path']) == 3:
            parents = {_resource_id(kind, row['path'][:1], row['path'][1])
                       for kind in ('table', 'view', 'fts-table', 'virtual-table')}
            if (row['kind'] in {'column', 'constraint'} and
                    _resource_id('table', ['main'], row['path'][1]) in rebuilds):
                continue
            if parents & created_relations and (row['kind'] != 'index' or
                                                row['native'].get('ddl') is None):
                continue  # CREATE TABLE owns its captured child facts.
        if identity in current:
            conflicts.append({'resource_id': identity, 'name': row['name'],
                'reason': 'Native target already exists outside the baseline'})
            continue
        if row['kind'] not in CREATABLE | {'column'}:
            blockers.append({'resource_id': identity, 'name': row['name'],
                'reason': 'No admitted SQLite CREATE adapter for this object kind'})
            continue
        try:
            source = _source(row)
            _require_virtual_module(connection, row, source)
            parent_baseline_sha256 = None
            if row['kind'] == 'column':
                owner = _resource_id('table', ['main'], row['path'][1])
                parent = before.get(owner)
                if parent is None or owner in created_relations:
                    raise ValueError('SQLite ADD COLUMN requires an observed existing table')
                parent_baseline_sha256 = digest(_definition(parent))
            if row['kind'] in {'index', 'trigger'}:
                owners={_resource_id(kind,['main'],row['path'][1]) for kind in ({'table','view'} if row['kind']=='trigger' else {'table'})}
                if not owners & (set(before) | created_relations):
                    raise ValueError('SQLite child requires a retained or explicitly created owning relation')
            new_owner = _created_owner(row, desired, baseline)
            if new_owner is not None:
                _compile_created_child(row, source, new_owner)
            else:
                _compile_exact(connection, row, source)
            operations.append({'operation': 'add-column' if row['kind'] == 'column' else 'create', 'resource_id': identity,
                'name': row['name'], 'kind': row['kind'], 'source': source,
                'desired_sha256': digest(_definition(row)),
                'baseline_sha256': None,
                **({'parent_baseline_sha256': parent_baseline_sha256}
                   if parent_baseline_sha256 else {})})
        except (ValueError, sqlite3.Error) as error:
            blockers.append({'resource_id': identity, 'name': row['name'],
                'reason': str(error)[:400]})
    covered_deletions = {identity for operation in operations if operation['operation']=='rebuild'
        for identity in operation.get('child_deletions',[])}
    planned_deleted_ids = set(deletions)
    for deleted_id in deletions:
        parent = before.get(deleted_id)
        if parent is not None:
            planned_deleted_ids.update(child_id for child_id, child in before.items()
                if child_id != deleted_id and
                child['path'][:len(parent['path'])] == parent['path'])
    for identity in sorted(deletions):
        if identity in covered_deletions:continue
        row = before.get(identity)
        if (row is None or row['kind'] not in CREATABLE or row['system'] != 'false' or
                row['native'].get('system_object') is not False or
                len(row['path']) != (3 if row['kind'] in {'index', 'trigger'} else 2) or
                row['path'][0] != 'main' or row['path'][-1] != row['name'] or
                identity != _resource_id(row['kind'], row['path'][:-1], row['name'])):
            blockers.append({'resource_id': identity, 'name': identity,
                'reason': 'Deletion target is not an observed user table, view, index or trigger'})
            continue
        if identity in after:
            blockers.append({'resource_id': identity, 'name': row['name'],
                'reason': 'Explicit deletion requires the target to be absent from the desired DDN'})
            continue
        descendant_ids = {child_id for child_id, child in before.items()
            if child_id != identity and child['path'][:len(row['path'])] == row['path']}
        current_descendant_ids = {child_id for child_id, child in current.items()
            if child_id != identity and child['path'][:len(row['path'])] == row['path']}
        if any(child_id in after for child_id in descendant_ids):
            blockers.append({'resource_id': identity, 'name': row['name'],
                'reason': 'Desired DDN still includes a child of the deleted object'})
            continue
        if current_descendant_ids != descendant_ids or any(child_id not in current or not _equal(_definition(before[child_id]),
                                                      _definition(current[child_id]))
               for child_id in descendant_ids):
            conflicts.append({'resource_id': identity, 'name': row['name'],
                'reason': 'SQLite target children changed since the baseline'})
            continue
        if row['kind'] == 'table' and any(
                other['native'].get('dependencies') and
                any(dep.get('referenced_table') == row['name']
                    for dep in other['native']['dependencies'])
                for other_id, other in current.items()
                if other_id != identity and other['kind'] == 'table' and other_id not in deletions):
            blockers.append({'resource_id': identity, 'name': row['name'],
                'reason': 'Another retained table has a foreign key to this table'})
            continue
        if row['kind'] in {'table', 'fts-table', 'virtual-table'} and any(
                other_id != identity and other_id not in planned_deleted_ids and
                other['kind'] in {'view', 'trigger', 'fts-table', 'virtual-table'}
                for other_id, other in current.items()):
            blockers.append({'resource_id': identity, 'name': row['name'],
                'reason': 'Retained views, triggers or virtual tables need a dependency review'})
            continue
        source = 'DROP ' + ('TABLE' if row['kind'] in {'fts-table', 'virtual-table'}
                           else row['kind'].upper()) + ' ' + _quote('main') + '.' + _quote(row['name'])
        try:
            connection.execute('EXPLAIN ' + source).fetchone()
        except sqlite3.Error as error:
            blockers.append({'resource_id': identity, 'name': row['name'],
                'reason': str(error)[:400]})
            continue
        operations.append({'operation': 'drop', 'resource_id': identity,
            'name': row['name'], 'kind': row['kind'], 'source': source,
            'baseline_sha256': digest(_definition(row)), 'desired_sha256': None,
            'affected_child_sha256': {child_id: digest(_definition(before[child_id]))
                for child_id in sorted(descendant_ids)}})
        covered_deletions.add(identity)
        covered_deletions.update(descendant_ids)
    for identity, row in sorted(before.items()):
        if identity not in after and row['kind'] not in {'metric', 'pragma', 'extension', 'native-function', 'collation', 'compile-option'}:
            if derived_view_column(row):continue
            if (len(row['path']) > 2 and row['kind'] in {'column', 'constraint'} and
                    _resource_id('table', ['main'], row['path'][1]) in rebuilds):
                continue
            if identity not in covered_deletions:
                blockers.append({'resource_id': identity, 'name': row['name'],
                    'reason': 'Absent DDN row is not an explicit SQLite deletion instruction'})
    if len(operations) > 32:
        raise ValueError('SQLite preview exceeds 32 native statements')
    for reason in batch_blockers(operations,desired):
        blockers.append({'resource_id':'','name':'SQLite design batch','reason':reason})
    operations.sort(key=lambda item: (
        0 if item['operation'] == 'drop' else 1,
        {'trigger': 0, 'index': 1, 'view': 2, 'table': 3, 'fts-table': 3,
         'virtual-table': 3, 'column': 4}[item['kind']]
        if item['operation'] == 'drop' else
        {'table': 0, 'fts-table': 0, 'virtual-table': 0,
         'column': 1, 'view': 2, 'index': 3, 'trigger': 4}[item['kind']]))
    executable = bool(operations) and not blockers and not conflicts
    return {'format': FORMAT, 'engine': 'sqlite', 'database_target_id': scope[1],
        'operations': operations, 'blockers': blockers, 'conflicts': conflicts,
        'execution_sha256': digest(operations), 'native_grammar_validated': True,
        'ready_for_review': executable, 'application_supported': executable,
        'warnings': ['Deletions require exact explicit identities; missing DDN rows alone never delete. Table and virtual-table deletions require a separate review. Explicit view, index and trigger removals can share a reviewed batch with admitted creations, replacements and rebuilds. Table rebuilds require explicit selection and their native preservation checks.']}
