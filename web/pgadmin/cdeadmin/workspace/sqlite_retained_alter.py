"""Property-driven native ALTER TABLE on an original SQLite connection."""
from copy import deepcopy
import sqlite3
from types import SimpleNamespace

from ..providers.sqlite import ddl_prepare
from ..providers.sqlite.declarations import fold,quote,tokens
from ..providers.sqlite.modules import option
from ..providers.sqlite.provider import _resource_id,_resources
from .firebird_schema_plan import digest
from . import sqlite_retained_schema as retained

ACTIONS={
    'rename-table':{'name'},'rename-column':{'column','name'},
    'drop-column':{'column'},'drop-constraint':{'name'},
    'drop-not-null':{'column'},'set-not-null':{'column','conflict'},
    'add-check':{'expression','name','conflict'},
}
CONFLICTS={'','ROLLBACK','ABORT','FAIL','IGNORE','REPLACE'}


def _options(changes):
    if not isinstance(changes,list) or not 1<=len(changes)<=16:
        raise ValueError('Select one to sixteen ordered native table alterations')
    result=[]
    for value in changes:
        if not isinstance(value,dict) or not isinstance(value.get('action'),str) or value['action'] not in ACTIONS:
            raise ValueError('Select a supported native SQLite table alteration')
        action=value['action']
        if set(value)-({'action','resource_id'}|ACTIONS[action]):
            raise ValueError('Native table alteration contains unrelated properties')
        if not isinstance(value.get('resource_id'),str):raise ValueError('Select an observed original table')
        row=deepcopy(value)
        for field in ACTIONS[action]-{'expression','conflict'}:
            if field=='name' and action=='add-check' and row.get(field) in (None,''):continue
            quote(row.get(field))
        if 'conflict' in ACTIONS[action]:
            row.setdefault('conflict','')
            if not isinstance(row['conflict'],str) or row['conflict'] not in CONFLICTS:raise ValueError('Select a native SQLite conflict policy')
        if action=='add-check':
            text=row.get('expression')
            if not isinstance(text,str) or not text.strip() or '\0' in text or len(text.encode('utf8'))>65536:
                raise ValueError('Enter a bounded native CHECK expression')
        result.append(row)
    return result


def _source(row,change):
    prefix='ALTER TABLE '+quote(row['path'][0])+'.'+quote(row['name'])+' '
    action=change['action']
    if action=='rename-table':return prefix+'RENAME TO '+quote(change['name'])
    if action=='rename-column':return prefix+'RENAME COLUMN '+quote(change['column'])+' TO '+quote(change['name'])
    if action=='drop-column':return prefix+'DROP COLUMN '+quote(change['column'])
    if action=='drop-constraint':
        # The pinned native DROP implementation compares its raw name token.
        # Its SQL token must equal the *actual* name, including quote characters
        # when those characters belong to the name. Wrapping another quote pair
        # could select a different constraint. Refuse unrepresentable names.
        name=change['name']
        try:parts=list(tokens(name))
        except ValueError:parts=[]
        if (len(parts)!=1 or parts[0].start!=0 or parts[0].end!=len(name) or
                not (parts[0].quoted or name[0]=='_' or name[0].isalpha() or ord(name[0])>=128)):
            raise ValueError('This constraint name needs a preservation rebuild: pinned SQLite requires its exact raw name as one identifier token')
        return prefix+'DROP CONSTRAINT '+name
    if action=='drop-not-null':return prefix+'ALTER COLUMN '+quote(change['column'])+' DROP NOT NULL'
    suffix=' ON CONFLICT '+change['conflict'] if change.get('conflict') else ''
    if action=='set-not-null':return prefix+'ALTER COLUMN '+quote(change['column'])+' SET NOT NULL'+suffix
    return prefix+'ADD '+('CONSTRAINT '+quote(change['name'])+' ' if change.get('name') else '')+'CHECK ('+change['expression']+')'+suffix


def _fts_dependencies(probe,baseline,table,change):
    if change['action'] not in {'rename-table','rename-column','drop-column'}:return
    for row in baseline['rows'].values():
        if row['kind']!='fts-table':continue
        content=option(row['native']['ddl'],'content')
        if not content:continue
        events=[];previous=probe._cdeadmin_authorizer
        def authorize(code,name,column,database,context):
            if code==sqlite3.SQLITE_READ:events.append((database,name,column))
            return sqlite3.SQLITE_OK
        try:
            probe.set_authorizer(authorize)
            cursor=probe.execute('EXPLAIN SELECT * FROM '+quote(row['path'][0])+'.'+quote(content))
            try:cursor.fetchone()
            finally:cursor.close()
        finally:probe.set_authorizer(previous)
        affected=[column for database,name,column in events if database==table['path'][0] and fold(name)==fold(table['name'])]
        if affected and (change['action']=='rename-table' or any(isinstance(column,str) and fold(column)==fold(change['column']) for column in affected)):
            raise ValueError('This native alteration needs explicit retained external-content FTS preservation')


def generate(client,handle,baseline,endpoint,session,changes):
    retained._scope(baseline,endpoint,session,observed=True)
    selected=_options(changes)
    namespaces={row[1] for row in handle.execute('PRAGMA database_list')}|{'temp'}
    probe=retained._prototype(baseline,namespaces)
    try:
        storage=set(probe._cdeadmin_module_storage)
        live=retained.observe(client,handle,endpoint,session)
        reproduced=retained.model(_resources(probe,{}),endpoint,session)
        if (retained.schema(baseline,storage)!=retained.schema(live,storage) or
                retained._storage_shape(reproduced,storage)!=retained._storage_shape(live,storage)):
            raise ValueError('The original native schema changed; capture a fresh baseline')
        # These modes govern native dependency rewriting. Only this owned empty
        # prototype is committed; the original caller transaction is untouched.
        probe.commit()
        for pragma in ('foreign_keys','legacy_alter_table','recursive_triggers'):
            probe.execute('PRAGMA '+pragma+'='+str(int(handle.execute('PRAGMA '+pragma).fetchone()[0])))
        names={};stages=[]
        for change in selected:
            original=baseline['rows'].get(change['resource_id'])
            if original is None or original['kind']!='table':raise ValueError('Select an observed ordinary original table')
            retained._valid(original,namespaces)
            namespace=original['path'][0];name=names.get(original['resource_id'],original['name'])
            current=retained.model(_resources(probe,{}),endpoint,session)
            row=current['rows'].get(_resource_id('table',[namespace],name))
            if row is None or (namespace,name) in storage:raise ValueError('Native module storage needs module maintenance')
            _fts_dependencies(probe,current,row,change)
            statement=_source(row,change)
            authorization_column=change.get('column') if change['action'] in {'drop-column','set-not-null','drop-not-null'} else None
            stage={'operation':'native-alter','alteration':change,'resource_id':row['resource_id'],
                'kind':'table','name':row['name'],'row':row,'source':statement,
                'authorization_column':authorization_column}
            ddl_prepare.prepare(SimpleNamespace(_uncertain=set()),probe,row,statement,operation='native-alter',authorization_column=authorization_column)
            probe.execute(statement);stages.append(stage)
            if change['action']=='rename-table':names[original['resource_id']]=change['name']
        proposed=retained.model(_resources(probe,{}),endpoint,session)
        if retained._storage_shape(proposed,storage)!=retained._storage_shape(live,storage):
            raise ValueError('Native module storage cannot be preserved by this alteration')
        # The empty prototype supplies schema facts. Files, settings, functions
        # and other untouched facts retain their actual original observation.
        desired=deepcopy(baseline)
        desired['rows']={key:row for key,row in desired['rows'].items() if row['kind'] not in retained.KINDS}
        for key,row in proposed['rows'].items():
            if row['kind'] in retained.KINDS:
                row['native']['observation_scope']='retained-session-design'
                desired['rows'][key]=row
        if '_all_schema_rows' in desired:desired['_all_schema_rows']=proposed['_all_schema_rows']
        return desired,stages,storage,retained._storage_shape(live,storage)
    finally:probe.close()


def plan(client,handle,baseline,desired,live,endpoint,session,changes):
    retained._scope(desired,endpoint,session)
    retained._scope(live,endpoint,session,observed=True)
    generated,stages,storage,storage_schema=generate(client,handle,baseline,endpoint,session,changes)
    if retained.schema(generated,storage)!=retained.schema(desired,storage):
        raise ValueError('Desired DDN differs from the ordered native table alterations; generate the design again')
    if retained.schema(baseline,storage)!=retained.schema(live,storage):
        raise ValueError('The original retained schema changed')
    first=stages[0]
    ddl_prepare.prepare(client,handle,first['row'],first['source'],operation='native-alter',authorization_column=first['authorization_column'])
    return {'format':retained.FORMAT,'engine':'sqlite','provider_session_id':session,'operations':stages,
        'module_storage':[list(key) for key in sorted(storage)],'module_storage_schema':storage_schema,
        'module_storage_after_schema':storage_schema,'execution_sha256':digest(stages),
        'ready_for_review':True,'application_supported':True,'native_grammar_validated':True,
        'transaction_policy':'original-caller-transaction; never commit',
        'warnings':['Native column removal discards that column data within the caller transaction. Inspect every ordered statement before confirming.',
            'Existing rows are checked by SQLite during apply. Native refusal rolls back the owned savepoint; severe native errors can end the caller transaction.']}
