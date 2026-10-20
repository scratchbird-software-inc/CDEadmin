"""Native schema stages for the original SQLite query connection.

No independent registered-file migration, file reopening, namespace projection
or transaction commit is part of this path.
"""
from copy import deepcopy
import sqlite3
import time
import uuid
from types import SimpleNamespace

from .firebird_schema_plan import digest
from .sqlite_schema_plan import _definition,CREATABLE
from ..providers.sqlite.provider import _resource_id,_resources
from ..providers.sqlite.driver import SQLiteConnection,uncertain_error
from ..providers.sqlite import ddl_prepare
from ..providers.sqlite.declarations import quote
from ..providers.embedded_session_catalog import sqlite_catalog

FORMAT='scratchrobin.sqlite.retained-schema-plan@1'
KINDS=CREATABLE|{'column','constraint'}
SAFE_MODULES={'fts3','fts4','fts5','rtree','rtree_i32'}


def model(resources,endpoint,session):
    def row(value):return {'resource_id':value['resource_id'],'kind':value['resource_kind'],
        'path':value['display_path'],'name':value['display_name'],
        'system':'true' if value['native'].get('system_object') else 'false','native':value['native']}
    return {'provenance':{'mapping':'scratchrobin.sqlite.catalog@1','endpoint_id':endpoint,
        'database_target_id':'retained-session:'+session,'include_system':False},
        'rows':{value['resource_id']:row(value) for value in resources if not value['native'].get('system_object')},
        '_all_schema_rows':{value['resource_id']:row(value) for value in resources if value['resource_kind'] in KINDS}}


def observe(client,handle,endpoint,session):
    return model(sqlite_catalog(client,handle,session,include_system=True)['resources'],endpoint,session)


def _storage_target(row):
    return _owner(row) if row['kind'] in {'index','trigger'} else tuple(row['path'][:2])


def schema(document,storage=()):
    return {identity:_definition(row) for identity,row in document['rows'].items()
        if row['kind'] in KINDS and _storage_target(row) not in storage}


def _storage_shape(document,storage):
    result={}
    for identity,row in document.get('_all_schema_rows',document['rows']).items():
        if row['kind'] not in KINDS or _storage_target(row) not in storage:continue
        shape=deepcopy(_definition(row));shape.pop('system',None)
        if isinstance(shape.get('catalog_metadata'),dict):shape['catalog_metadata'].pop('table_list_type',None)
        result[identity]=shape
    return result


def context(handle,revision):
    if not hasattr(handle,'_cdeadmin_authorizer'):
        raise ValueError('Retained SQLite DDL requires observable native authorization policy')
    databases=[list(row) for row in handle.execute('PRAGMA database_list')]
    return {'revision':revision,'connection_identity':id(handle),'authorizer_identity':id(handle._cdeadmin_authorizer),
        'in_transaction':handle.in_transaction,'total_changes':handle.total_changes,'databases':databases,
        'database_versions':[[name,*[handle.execute('PRAGMA '+quote(name)+'.'+pragma).fetchone()[0]
            for pragma in ('schema_version','user_version','data_version')]] for _,name,_ in databases],
        'settings':{name:handle.execute('PRAGMA '+name).fetchone()[0] for name in
            ('foreign_keys','defer_foreign_keys','recursive_triggers','legacy_alter_table','query_only','writable_schema')},
        'native_capabilities':{name:sorted([list(row) for row in handle.execute('PRAGMA '+name)],key=repr)
            for name in ('function_list','collation_list','module_list')}}


def _scope(document,endpoint,session,*,observed=False):
    provenance=document.get('provenance',{})
    if (provenance.get('mapping')!='scratchrobin.sqlite.catalog@1' or
            provenance.get('endpoint_id')!=endpoint or
            provenance.get('database_target_id')!='retained-session:'+session or
            provenance.get('include_system') is not False):
        raise ValueError('Retained DDN must belong to this exact original SQLite session and endpoint')
    if observed and any(row['native'].get('observation_scope')!='retained-session' for row in document['rows'].values()):
        raise ValueError('Retained DDL requires original-session baseline observations')


def _valid(row,namespaces):
    kind,path,name=row['kind'],row['path'],row['name']
    length=2 if kind=='trigger' and path and path[0]=='temp' else 3 if kind in {'index','trigger','column'} else 2
    if (row['system']!='false' or row['native'].get('system_object') is not False or
            len(path)!=length or path[0] not in namespaces or path[-1]!=name or
            row['resource_id']!=_resource_id(kind,path[:-1],name)):
        raise ValueError('Retained SQLite object identity or namespace is inconsistent')
    if kind in {'fts-table','virtual-table'}:
        from ..providers.sqlite.modules import declaration
        if declaration(row['native']['ddl'])[1].lower() not in SAFE_MODULES:
            raise ValueError('The installed virtual module requires an atomic retained DDL adapter')
    if kind=='trigger' and path[0]=='temp':
        if row['native'].get('catalog_metadata',{}).get('owner_database') not in namespaces:
            raise ValueError('A TEMP trigger requires an observed or explicitly selected native owning database')


def _owner(row):
    metadata=row['native'].get('catalog_metadata',{})
    return (metadata.get('owner_database') if row['path'][0]=='temp' and row['kind']=='trigger' else row['path'][0],
        metadata.get('table_name'))


def _children(parent,rows):
    path=parent['path']
    return {identity for identity,row in rows.items() if identity!=parent['resource_id'] and (
        len(row['path'])>len(path) and row['path'][:len(path)]==path or
        row['kind']=='trigger' and _owner(row)==tuple(path))}


def _prototype(document,namespaces):
    probe=sqlite3.connect(':memory:',factory=SQLiteConnection)
    try:
        for name in sorted(namespaces-{'main','temp'}):probe.execute('ATTACH DATABASE \':memory:\' AS '+quote(name))
        rows=[row for row in document['rows'].values() if row['kind'] in CREATABLE]
        for row in rows:_valid(row,namespaces)
        ordinary={tuple(row['path']):row for row in rows if row['kind']=='table'}
        for row in rows:
            if row['kind'] in {'table','view'}:probe.execute(ddl_prepare.source(row))
        pending=[row for row in rows if row['kind'] in {'fts-table','virtual-table'}]
        probe._cdeadmin_module_storage=set();probe._cdeadmin_module_storage_owners={};started=time.monotonic()
        while pending:
            deferred=[];last_error=None
            for row in pending:
                if time.monotonic()-started>30:raise ValueError('Owned native schema reproduction exceeds its 30-second budget')
                try:_create_virtual(probe,row,ordinary)
                except sqlite3.Error as error:deferred.append(row);last_error=error
            if len(deferred)==len(pending):raise ValueError('Native virtual-table schema reproduction is unavailable: '+str(last_error)[:300])
            pending=deferred
        for row in rows:
            if row['kind'] in {'index','trigger'}:probe.execute(ddl_prepare.source(row))
        return probe
    except BaseException:probe.close();raise


def _create_virtual(probe,row,ordinary):
    """Let the module identify its own storage through actual CREATE actions.

    SQLite can report FTS storage as ordinary tables when a TEMP virtual table
    with the same name uses another module. Never infer ownership from a name
    suffix. Only constructor-requested exact identities may replace a copied
    ordinary declaration in this empty, privately owned prototype.
    """
    from .sqlite_columns import signature
    namespace=row['path'][0];removed=set()
    while True:
        guard='sr_module_'+uuid.uuid4().hex;requested=set();previous=probe._cdeadmin_authorizer
        probe.execute('SAVEPOINT '+guard)
        try:
            for schema_name,name in removed:probe.execute('DROP TABLE '+quote(schema_name)+'.'+quote(name))
            def authorize(action,name,owner,database,context):
                if action in {sqlite3.SQLITE_CREATE_TABLE,sqlite3.SQLITE_CREATE_TEMP_TABLE} and database==namespace and name!=row['name']:
                    requested.add((database,name))
                return sqlite3.SQLITE_OK
            probe.set_authorizer(authorize)
            try:
                probe.execute(ddl_prepare.source(row))
                if row['kind']=='fts-table':
                    from ..providers.sqlite.fts_configuration import statements
                    for statement in statements(row['name'],row['native'].get('fts_configuration'),schema=namespace):probe.execute(statement)
            finally:probe.set_authorizer(previous)
            for schema_name,name in removed:
                actual=probe.execute('SELECT sql FROM '+quote(schema_name)+'.sqlite_schema WHERE type=\'table\' AND name=?',(name,)).fetchone()
                original=ordinary[(schema_name,name)]
                from ..providers.sqlite.declarations import canonical_create
                if actual is None or signature(canonical_create(actual[0],'table',schema_name,name))!=signature(ddl_prepare.source(original)):
                    raise ValueError('Native module-created storage differs from the captured declaration; do not invent a replacement')
            probe.execute('RELEASE SAVEPOINT '+guard)
            probe._cdeadmin_module_storage.update(requested)
            probe._cdeadmin_module_storage_owners.update({key:row['resource_id'] for key in requested})
            return
        except BaseException as error:
            probe.execute('ROLLBACK TO SAVEPOINT '+guard);probe.execute('RELEASE SAVEPOINT '+guard)
            collisions={key for key in requested if key in ordinary}-removed
            if not isinstance(error,sqlite3.Error) or not collisions:raise
            removed.update(collisions)


def plan(client,handle,baseline,desired,live,endpoint,session,*,deletions=()):
    for document in (baseline,live):_scope(document,endpoint,session,observed=True)
    _scope(desired,endpoint,session)
    if (not isinstance(deletions,(list,tuple)) or len(deletions)>32 or
            any(not isinstance(item,str) for item in deletions) or len(set(deletions))!=len(deletions)):
        raise ValueError('Select at most 32 exact native deletion identities')
    namespaces={row[1] for row in handle.execute('PRAGMA database_list')}|{'temp'}
    probe=_prototype(baseline,namespaces)
    storage=set(probe._cdeadmin_module_storage);storage_owners=dict(probe._cdeadmin_module_storage_owners);probe.close()
    if schema(baseline,storage)!=schema(live,storage):raise ValueError('The original retained SQLite schema changed; capture a new baseline')
    actual_storage=_storage_shape(live,storage)
    remaining_storage={key for key in storage if storage_owners[key] not in deletions}
    expected_storage={identity:value for identity,value in actual_storage.items()
        if _storage_target(live['_all_schema_rows'][identity]) in remaining_storage}
    before,after=baseline['rows'],desired['rows'];removed=set();stages=[]
    replaced_views={tuple(row['path']) for identity,row in after.items() if row['kind']=='view' and
        identity in before and _definition(before[identity])!=_definition(row)}
    if any(row['kind']=='table' and identity in before and _definition(before[identity])!=_definition(row)
            for identity,row in after.items()):
        replaced_views.update(tuple(row['path']) for row in after.values() if row['kind']=='view')
    for identity in deletions:
        row=before.get(identity)
        if row is None or row['kind'] not in CREATABLE or identity in after:
            raise ValueError('Explicit retained deletion requires an observed native object absent from the desired design')
        _valid(row,namespaces);children=_children(row,before)
        if children & set(after):raise ValueError('Desired retained DDN still contains a deleted object child')
        stages.append({'operation':'drop','resource_id':identity,'kind':row['kind'],
            'name':row['name'],'row':row,'source':ddl_prepare.drop(row)})
        removed.update({identity,*children})
    for identity,row in before.items():
        if row['kind'] in KINDS and identity not in after and identity not in removed:
            if _storage_target(row) in storage:continue
            if row['kind']=='column' and tuple(row['path'][:2]) in replaced_views:continue
            raise ValueError('An absent retained DDN fact is not an explicit deletion instruction')
    appended=set()
    for identity,row in after.items():
        if row['kind'] not in CREATABLE:continue
        if _storage_target(row) in storage:
            shape=_storage_shape({'rows':{identity:row}},storage)
            if shape.get(identity)!=actual_storage.get(identity):raise ValueError('Native module storage definitions require module maintenance')
            continue
        old=before.get(identity)
        if old is not None and _definition(old)==_definition(row):continue
        _valid(row,namespaces)
        if old is not None:
            if row['kind']=='table':
                from .sqlite_columns import _clauses
                from ..providers.sqlite.declarations import tokens
                old_columns=old['native'].get('columns',[]);new_columns=row['native'].get('columns',[])
                if ([item['name'] for item in new_columns[:len(old_columns)]]!=[item['name'] for item in old_columns] or
                        not 1<=len(new_columns)-len(old_columns)<=32):
                    raise ValueError('The retained table change requires a separately selected native preservation transformation')
                clauses={next(tokens(clause)).value:clause for clause in _clauses(ddl_prepare.source(row))}
                for item in new_columns[len(old_columns):]:
                    column=after.get(_resource_id('column',row['path'],item['name']))
                    if column is None or item['name'] not in clauses:raise ValueError('Desired retained column facts are incomplete')
                    _valid(column,namespaces)
                    stages.append({'operation':'add-column','resource_id':column['resource_id'],'kind':'column',
                        'name':column['name'],'row':column,'source':'ALTER TABLE '+quote(row['path'][0])+'.'+quote(row['name'])+
                        ' ADD COLUMN '+clauses[item['name']]})
                appended.add(tuple(row['path']));continue
            if row['kind'] not in {'index','trigger','view'}:
                raise ValueError('This retained native table transformation needs its own qualified preservation adapter')
            stages.append({'operation':'drop','resource_id':identity,'kind':old['kind'],
                'name':old['name'],'row':old,'source':ddl_prepare.drop(old)})
        stages.append({'operation':'create','resource_id':identity,'kind':row['kind'],
            'name':row['name'],'row':row,'source':ddl_prepare.source(row)})
    if not 1<=len(stages)<=32:raise ValueError('Review one to 32 native retained DDL statements')
    order={'trigger':0,'index':1,'view':2,'table':3,'fts-table':3,'virtual-table':3}
    creation_order={'table':0,'fts-table':0,'virtual-table':0,'column':1,'view':2,'index':3,'trigger':4}
    stages.sort(key=lambda stage:(0 if stage['operation']=='drop' else 1,
        order[stage['kind']] if stage['operation']=='drop' else creation_order[stage['kind']]))
    probe=_prototype(baseline,namespaces)
    try:
        # The empty native prototype validates ordered grammar and definitions.
        # Original-session authorizer checks are repeated before each real step.
        for stage in stages:
            row=stage['row']
            target=tuple(row['path'][:2]) if row['kind'] in {'table','column'} else _owner(row)
            if target in probe._cdeadmin_module_storage:
                raise ValueError('Use module-native maintenance for storage created by a native virtual-table constructor')
            ddl_prepare.prepare(SimpleNamespace(_uncertain=set()),probe,stage['row'],stage['source'],operation=stage['operation'])
            probe.execute(stage['source'])
        proposed=model(_resources(probe,{}),endpoint,session)
        if schema(proposed,storage)!=schema(desired,storage):raise ValueError('Desired retained DDN facts differ from the complete native resulting schema')
        if _storage_shape(proposed,storage)!=expected_storage:raise ValueError('Native module storage schema cannot be preserved')
    finally:probe.close()
    prepared_columns=set()
    for stage in stages:
        row=stage['row']
        if stage['operation']=='drop':
            ddl_prepare.prepare(client,handle,row,stage['source'],operation='drop')
        elif stage['operation']=='add-column':
            parent=tuple(row['path'][:2])
            if parent not in prepared_columns:
                ddl_prepare.prepare(client,handle,row,stage['source'],operation='add-column');prepared_columns.add(parent)
            else:stage['original_binding']='checked-during-ordered-apply'
        elif row['resource_id'] not in before and (row['kind'] not in {'index','trigger'} or
                _owner(row) not in appended and any(other['kind'] in {'table','view','fts-table','virtual-table'} and tuple(other['path'])==_owner(row)
                    for other in before.values())):
            ddl_prepare.prepare(client,handle,row,stage['source'])
        else:stage['original_binding']='checked-during-ordered-apply'
    return {'format':FORMAT,'engine':'sqlite','provider_session_id':session,'operations':stages,
        'module_storage':[list(key) for key in sorted(storage)],'module_storage_schema':actual_storage,
        'module_storage_after_schema':expected_storage,
        'execution_sha256':digest(stages),'ready_for_review':True,'application_supported':True,
        'native_grammar_validated':True,'transaction_policy':'original-caller-transaction; never commit',
        'warnings':['Begin a transaction before applying. Successful DDL remains pending the original caller\'s commit or rollback.',
            'Native cancellation or severe engine errors can end the entire caller transaction. Unknown outcomes never authorize replay.']}


def generate_columns(client,handle,baseline,endpoint,session,identity,columns):
    """Generate desired DDN from properties on this session's empty schema."""
    from .sqlite_column_design import declaration
    _scope(baseline,endpoint,session,observed=True)
    live=observe(client,handle,endpoint,session)
    row=baseline['rows'].get(identity)
    namespaces={item[1] for item in handle.execute('PRAGMA database_list')}|{'temp'}
    if row is None or row['kind']!='table':raise ValueError('Select an observed ordinary retained SQLite table')
    _valid(row,namespaces)
    if not isinstance(columns,list) or not 1<=len(columns)<=32:raise ValueError('Design one to 32 retained native column additions')
    probe=_prototype(baseline,namespaces)
    try:
        if schema(baseline,probe._cdeadmin_module_storage)!=schema(live,probe._cdeadmin_module_storage):
            raise ValueError('The original retained schema changed; capture a fresh baseline')
        for column in columns:
            probe.execute('ALTER TABLE '+quote(row['path'][0])+'.'+quote(row['name'])+' ADD COLUMN '+declaration(column))
        desired=deepcopy(baseline)
        for key,value in list(desired['rows'].items()):
            if value['kind'] in KINDS:del desired['rows'][key]
        for key,value in model(_resources(probe,{}),endpoint,session)['rows'].items():
            if value['kind'] in KINDS:
                value['native']['observation_scope']='retained-session-design'
                desired['rows'][key]=value
        return desired
    finally:probe.close()


def apply(client,handle,record,endpoint,session,revision,*,cancel=None,acknowledge=None):
    """Leave a successful schema pending; rollback only the owned savepoint."""
    if (record['plan'].get('format')!=FORMAT or
            digest(record['plan']['operations'])!=record['plan'].get('execution_sha256')):
        return {'state':'not_dispatched','reason':'Reviewed retained native DDL stages changed'}
    if (not handle.in_transaction or context(handle,revision)!=record['native_context']):
        return {'state':'not_dispatched','reason':'Original retained transaction, authorization or session context changed'}
    live=observe(client,handle,endpoint,session)
    storage={tuple(key) for key in record['plan'].get('module_storage',[])}
    if (schema(live,storage)!=schema(record['baseline'],storage) or
            _storage_shape(live,storage)!=record['plan'].get('module_storage_schema',{})):
        return {'state':'not_dispatched','reason':'Original retained native schema changed'}
    guard='sr_ddl_'+uuid.uuid4().hex;created=False;completed=0;native_ack=False
    try:
        handle.execute('SAVEPOINT '+guard);created=True
        for stage in record['plan']['operations']:
            if cancel is not None and cancel.is_set():raise InterruptedError('Retained DDL canceled before its next stage')
            ddl_prepare.prepare(client,handle,stage['row'],stage['source'],operation=stage['operation'])
            handle.execute(stage['source']);completed+=1
        actual=observe(client,handle,endpoint,session)
        if (schema(actual,storage)!=schema(record['desired'],storage) or
                _storage_shape(actual,storage)!=record['plan'].get('module_storage_after_schema',{})):
            raise ValueError('Retained native schema postconditions differ from the desired DDN')
        handle.execute('RELEASE SAVEPOINT '+guard);created=False;native_ack=True
        outcome={'state':'applied_pending_caller_transaction','native_ddl_acknowledged':True,
            'rediscovery_verified':True,'caller_transaction_active':handle.in_transaction,
            'completed_statements':completed,'commit_dispatched':False}
        if acknowledge is not None:
            try:acknowledge(deepcopy(outcome))
            except BaseException as error:outcome['acknowledgement_store_error']=type(error).__name__
        return outcome
    except BaseException as error:
        uncertain=not isinstance(error,(ValueError,InterruptedError)) and uncertain_error(error)
        cleanup=True
        if created and handle.in_transaction:
            try:
                handle.execute('ROLLBACK TO SAVEPOINT '+guard);handle.execute('RELEASE SAVEPOINT '+guard)
            except BaseException:cleanup=False
        if uncertain or not cleanup:client._uncertain.add(id(handle))
        return {'state':'unknown_outcome' if uncertain or not cleanup else
            'rolled_back_to_savepoint' if handle.in_transaction else 'caller_transaction_ended_by_native_engine',
            'native_ddl_acknowledged':native_ack,'completed_statements':completed,'commit_dispatched':False,
            'caller_transaction_active':handle.in_transaction,'savepoint_cleanup_confirmed':cleanup,
            'error_type':type(error).__name__,'native_error':str(error)[:400]}
