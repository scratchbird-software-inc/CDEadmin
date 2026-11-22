"""Property-driven native ALTER TABLE on an original SQLite connection."""
from copy import deepcopy
from functools import lru_cache
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


@lru_cache(maxsize=1)
def _drop_constraint_rule():
    """Observe how the loaded SQLite matches a DROP CONSTRAINT name token.

    3.53.0 compares the raw token, so "a" selects the constraint literally
    named "a" (quotes included); 3.53.1 dequotes it and selects a. Only an
    owned in-memory table is touched.
    """
    probe=sqlite3.connect(':memory:')
    try:
        probe.execute('CREATE TABLE t(id INTEGER,CONSTRAINT a CHECK(id>0),CONSTRAINT """a""" CHECK(id<10))')
        try:probe.execute('ALTER TABLE t DROP CONSTRAINT "a"')
        except sqlite3.Error:return None
        source=probe.execute("SELECT sql FROM sqlite_schema WHERE name='t'").fetchone()[0]
    finally:probe.close()
    if source=='CREATE TABLE t(id INTEGER,CONSTRAINT a CHECK(id>0))':return 'raw-token'
    if source=='CREATE TABLE t(id INTEGER,CONSTRAINT """a""" CHECK(id<10))':return 'dequoted'
    return None


def _source(row,change):
    prefix='ALTER TABLE '+quote(row['path'][0])+'.'+quote(row['name'])+' '
    action=change['action']
    if action=='rename-table':return prefix+'RENAME TO '+quote(change['name'])
    if action=='rename-column':return prefix+'RENAME COLUMN '+quote(change['column'])+' TO '+quote(change['name'])
    if action=='drop-column':return prefix+'DROP COLUMN '+quote(change['column'])
    if action=='drop-constraint':
        name=change['name'];rule=_drop_constraint_rule()
        if rule=='dequoted':return prefix+'DROP CONSTRAINT '+quote(name)
        if rule!='raw-token':
            raise ValueError('This SQLite runtime did not confirm how native DROP CONSTRAINT selects a constraint name')
        # SQLite 3.53.0 compares its raw name token. Its SQL token must equal
        # the *actual* name, including quote characters when those characters
        # belong to the name. Wrapping another quote pair could select a
        # different constraint. Refuse unrepresentable names.
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


def _fts_dependencies(probe,baseline,table,change,*,allowed_fts=frozenset()):
    if change['action'] not in {'rename-table','rename-column','drop-column'}:return
    for row in baseline['rows'].values():
        if row['kind']!='fts-table' or row['resource_id'] in allowed_fts:continue
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


def _validate_fts_rebindings(baseline,fts_rebindings):
    if (not isinstance(fts_rebindings,(list,tuple)) or len(fts_rebindings)>16 or
            any(not isinstance(item,str) or not item for item in fts_rebindings) or
            len(set(fts_rebindings))!=len(fts_rebindings)):
        raise ValueError('Select at most sixteen distinct external-content FTS resource identities')
    for fid in fts_rebindings:
        frow=baseline['rows'].get(fid)
        if frow is None or frow['kind']!='fts-table':
            raise ValueError('Selected FTS rebinding target is not an observed FTS table: '+fid)
    return list(fts_rebindings)


def generate(client,handle,baseline,endpoint,session,changes,fts_rebindings=()):
    retained._scope(baseline,endpoint,session,observed=True)
    selected=_options(changes)
    selected_fts=_validate_fts_rebindings(baseline,fts_rebindings)
    namespaces={row[1] for row in handle.execute('PRAGMA database_list')}|{'temp'}
    probe=retained._prototype(baseline,namespaces,live_handle=handle)
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
        names={};stages=[];rebind_details=[]
        pre_rebind_sql=[];post_rebind_sql=[]
        if selected_fts:
            from .sqlite_fts_rebind import plans as rebind_plans,equal
            from .sqlite_fts_views import content_views,preserve_columns
            from ..providers.sqlite.modules import declaration as mod_decl
            if any(c['action']=='drop-column' for c in selected):
                # Ensure dropped columns are not referenced by selected FTS tables before rebinding
                for change in selected:
                    if change['action']=='drop-column':
                        orig=baseline['rows'].get(change['resource_id'])
                        if orig is not None:
                            _fts_dependencies(probe,baseline,orig,change,allowed_fts=frozenset())
            temp_names={}
            by_ns={}
            for change in selected:
                orig=baseline['rows'].get(change['resource_id'])
                if orig is None or orig['kind']!='table':
                    raise ValueError('Select an observed ordinary original table')
                ns=orig['path'][0]
                cur_name=temp_names.get(orig['resource_id'],orig['name'])
                if change['action']=='rename-table':
                    by_ns.setdefault(ns,[]).append({'kind':'table','table':cur_name,'to':change['name'],'namespace':ns})
                    temp_names[orig['resource_id']]=change['name']
                elif change['action']=='rename-column':
                    by_ns.setdefault(ns,[]).append({'kind':'column','table':cur_name,'from':change['column'],'to':change['name'],'namespace':ns})
            used_fts=set()
            for ns in sorted({baseline['rows'][fid]['path'][0] for fid in selected_fts}):
                ns_cviews=content_views(baseline,namespace=ns)
                ns_fts_ids=[fid for fid in selected_fts if baseline['rows'][fid]['path'][0]==ns]
                view_backed_fts=[]
                table_backed_fts=[]
                for fid in ns_fts_ids:
                    frow=baseline['rows'][fid]
                    target_content=option(frow['native']['ddl'],'content') or ''
                    matched_view=next((v for v in ns_cviews.values() if equal(v['name'],target_content)),None)
                    if matched_view is not None:
                        view_backed_fts.append((fid,frow,matched_view))
                    else:
                        table_backed_fts.append(fid)
                ns_plans=rebind_plans(baseline,by_ns.get(ns,[]),table_backed_fts,namespace=ns)
                for item in ns_plans:
                    used_fts.add(item['resource_id'])
                    rebind_details.append(item)
                    frow=baseline['rows'][item['resource_id']]
                    for sql_stmt in item['before']:
                        pre_rebind_sql.append((frow,sql_stmt))
                    for sql_stmt in item['stages']:
                        post_rebind_sql.append((frow,sql_stmt))
                frozen_views=set()
                for fid,frow,vrow in view_backed_fts:
                    used_fts.add(fid)
                    q_ns=quote(ns)
                    if vrow['resource_id'] not in frozen_views:
                        frozen_views.add(vrow['resource_id'])
                        preserved=preserve_columns(vrow)
                        if preserved['native']['ddl']!=vrow['native']['ddl']:
                            drop_v='DROP VIEW '+q_ns+'.'+quote(vrow['name'])
                            create_v=ddl_prepare.source(preserved)
                            pre_rebind_sql.append((vrow,drop_v))
                            pre_rebind_sql.append((preserved,create_v))
                    mod_name=mod_decl(frow['native']['ddl'])[1].lower()
                    q_fts=quote(frow['name'])
                    post_rebind_sql.append((frow,f'INSERT INTO {q_ns}.{q_fts}({q_fts}) VALUES(\'rebuild\')'))
                    post_rebind_sql.append((frow,f'INSERT INTO {q_ns}.{q_fts}({q_fts}'+(',rank' if mod_name=='fts5' else '')+") VALUES('integrity-check'"+(',1' if mod_name=='fts5' else '')+')'))
            if used_fts!=set(selected_fts):
                raise ValueError('Unused external-content FTS rebinding target(s): '+', '.join(sorted(set(selected_fts)-used_fts)))
        for frow,sql_stmt in pre_rebind_sql:
            probe.execute(sql_stmt)
            stages.append({'operation':'fts-rebind-step','resource_id':frow['resource_id'],
                'kind':frow['kind'],'name':frow['name'],'row':frow,'source':sql_stmt})
        allowed_set=frozenset(selected_fts)
        for change in selected:
            original=baseline['rows'].get(change['resource_id'])
            if original is None or original['kind']!='table':raise ValueError('Select an observed ordinary original table')
            retained._valid(original,namespaces,live_handle=handle)
            namespace=original['path'][0];name=names.get(original['resource_id'],original['name'])
            current=retained.model(_resources(probe,{}),endpoint,session)
            row=current['rows'].get(_resource_id('table',[namespace],name))
            if row is None or (namespace,name) in storage:raise ValueError('Native module storage needs module maintenance')
            _fts_dependencies(probe,current,row,change,allowed_fts=allowed_set)
            statement=_source(row,change)
            authorization_column=change.get('column') if change['action'] in {'drop-column','set-not-null','drop-not-null'} else None
            stage={'operation':'native-alter','alteration':change,'resource_id':row['resource_id'],
                'kind':'table','name':row['name'],'row':row,'source':statement,
                'authorization_column':authorization_column}
            ddl_prepare.prepare(SimpleNamespace(_uncertain=set()),probe,row,statement,operation='native-alter',authorization_column=authorization_column)
            probe.execute(statement);stages.append(stage)
            if change['action']=='rename-table':names[original['resource_id']]=change['name']
        for frow,sql_stmt in post_rebind_sql:
            probe.execute(sql_stmt)
            stages.append({'operation':'fts-rebind-step','resource_id':frow['resource_id'],
                'kind':frow['kind'],'name':frow['name'],'row':frow,'source':sql_stmt})
        proposed=retained.model(_resources(probe,{}),endpoint,session)
        after_probe=retained._prototype(proposed,namespaces,live_handle=handle)
        try:
            after_storage=set(after_probe._cdeadmin_module_storage)
        finally:
            after_probe.close()
        if not selected_fts and retained._storage_shape(proposed,storage)!=retained._storage_shape(live,storage):
            raise ValueError('Native module storage cannot be preserved by this alteration')
        after_storage_schema=retained._storage_shape(proposed,after_storage)
        # The empty prototype supplies schema facts. Files, settings, functions
        # and other untouched facts retain their actual original observation.
        desired=deepcopy(baseline)
        desired['rows']={key:row for key,row in desired['rows'].items() if row['kind'] not in retained.KINDS}
        for key,row in proposed['rows'].items():
            if row['kind'] in retained.KINDS:
                row['native']['observation_scope']='retained-session-design'
                desired['rows'][key]=row
        if '_all_schema_rows' in desired:desired['_all_schema_rows']=proposed['_all_schema_rows']
        return desired,stages,storage,retained._storage_shape(live,storage),after_storage,after_storage_schema,rebind_details
    finally:probe.close()


def plan(client,handle,baseline,desired,live,endpoint,session,changes,*,fts_rebindings=()):
    retained._scope(desired,endpoint,session)
    retained._scope(live,endpoint,session,observed=True)
    generated,stages,storage,storage_schema,after_storage,after_storage_schema,rebind_details=generate(
        client,handle,baseline,endpoint,session,changes,fts_rebindings=fts_rebindings)
    if retained.schema(generated,after_storage)!=retained.schema(desired,after_storage):
        raise ValueError('Desired DDN differs from the ordered native table alterations; generate the design again')
    if retained.schema(baseline,storage)!=retained.schema(live,storage):
        raise ValueError('The original retained schema changed')
    first=next((s for s in stages if s['operation']=='native-alter'),None)
    if first is not None and not fts_rebindings:
        ddl_prepare.prepare(client,handle,first['row'],first['source'],operation='native-alter',authorization_column=first['authorization_column'])
    result={'format':retained.FORMAT,'engine':'sqlite','provider_session_id':session,'operations':stages,
        'module_storage':[list(key) for key in sorted(storage)],'module_storage_schema':storage_schema,
        'module_storage_after':[list(key) for key in sorted(after_storage)],
        'module_storage_after_schema':after_storage_schema,'execution_sha256':digest(stages),
        'ready_for_review':True,'application_supported':True,'native_grammar_validated':True,
        'transaction_policy':'original-caller-transaction; never commit',
        'warnings':['Native column removal discards that column data within the caller transaction. Inspect every ordered statement before confirming.',
            'Existing rows are checked by SQLite during apply. Native refusal rolls back the owned savepoint; severe native errors can end the caller transaction.',
            *(['Explicitly selected external-content FTS indexes are dropped, rebound, rebuilt and integrity-checked inside the caller savepoint.'] if fts_rebindings else [])]}
    if fts_rebindings:
        result['fts_rebindings']=list(fts_rebindings)
        result['fts_rebuilds']=[{k:v for k,v in item.items() if k in {'resource_id','namespace','source_name','name','module','original_content','content','column_renames','row_identity_mapping'}} for item in rebind_details]
    return result
