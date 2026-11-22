"""SQLite-owned schema rewriting for reviewed DDN table and column renames."""
from copy import deepcopy
from collections import Counter
import os
import sqlite3
import stat

from .firebird_catalog_export import build_export
from .firebird_schema_plan import digest
from .sqlite_schema_plan import FORMAT,_definition,_quote
from ..providers.sqlite.provider import _resources
from ..providers.sqlite.driver import uncertain_error

KINDS={'table','view','column','constraint','index','trigger','fts-table','virtual-table'}
RENAME_MODULES={'fts3','fts4','fts5','rtree','rtree_i32','geopoly','fts3tokenize','dbstat','fts4aux','fts5vocab'}


def virtual_module(connection,row,*,namespace='main'):
    """Use native authorizer arguments, including quoted module declarations."""
    from ..providers.sqlite import ddl_prepare
    from ..providers.sqlite.custom_virtual_modules import is_custom_creatable
    observed=[]
    def authorize(action,name,module,database,_context):
        if action==sqlite3.SQLITE_CREATE_VTABLE:observed.append((name,module,database))
        return sqlite3.SQLITE_OK
    stmt=row['native']['ddl'] if namespace=='main' else ddl_prepare.source(row)
    connection.set_authorizer(authorize)
    try:connection.execute('EXPLAIN '+stmt).fetchone()
    finally:connection.set_authorizer(None)
    if len(observed)!=1 or observed[0][0]!=row['name'] or observed[0][2]!=namespace:
        raise ValueError('Native virtual-table declaration targets a different rename scope')
    module=observed[0][1]
    if module.lower() not in RENAME_MODULES and not is_custom_creatable(module):
        raise ValueError('Native rename design generation requires an adapter for installed module '+module)
    return module


def schema(model,*,namespaces=('main',)):
    ns_set=set(namespaces)
    return {identity:_definition(row) for identity,row in model['rows'].items()
            if row['kind'] in KINDS and row['system']=='false' and row['path'][0] in ns_set}


def model(connection,baseline):
    return build_export(_resources(connection,{}),endpoint_id=baseline['provenance']['endpoint_id'],
        target_id=baseline['provenance']['database_target_id'],generation='native-rename',
        engine='sqlite',native_model=True)


def validate_dependencies(connection,*,namespaces=('main',)):
    import uuid
    from .sqlite_schema_apply import _validate_dependencies,_PreservationRefused
    observed={row['resource_id']:row for row in _resources(connection,{})}
    try:
        if 'main' in namespaces:
            main_only={k:r for k,r in observed.items() if r.get('display_path',[None])[0]=='main'}
            _validate_dependencies(connection,main_only)
        fresh=' /* cdeadmin-native-ns-prepare:'+uuid.uuid4().hex+' */'
        for ns in sorted(set(namespaces)-{'main'}):
            q_ns=_quote(ns)
            for row in observed.values():
                if row['resource_kind']=='view' and row['display_path'][0]==ns:
                    if (row['native'].get('column_observation',{}).get('available') is False or
                            row['native'].get('view_binding_observation',{}).get('available') is False):
                        raise _PreservationRefused(f'SQLite final view columns or native bindings are unavailable in {ns}')
                    connection.execute(f'EXPLAIN SELECT * FROM {q_ns}.{_quote(row["display_name"])} LIMIT 0{fresh}').fetchone()
                elif row['resource_kind']=='trigger' and row['display_path'][0]==ns:
                    meta=row['native'].get('catalog_metadata',{})
                    owner_db=meta.get('owner_database') if ns=='temp' else ns
                    owner_tbl=meta.get('table_name') or (row['display_path'][1] if len(row['display_path'])>=3 else None)
                    if owner_db and owner_tbl:
                        q_odb=_quote(owner_db);q_otbl=_quote(owner_tbl)
                        rel=connection.execute(f'SELECT type FROM {q_odb}.sqlite_schema WHERE name=?',(owner_tbl,)).fetchone()
                        if rel and rel[0]=='table':
                            cols=[r[1] for r in connection.execute(f'PRAGMA {q_odb}.table_xinfo({q_otbl})') if not r[6]]
                            connection.execute(f'EXPLAIN INSERT INTO {q_odb}.{q_otbl} DEFAULT VALUES{fresh}').fetchone()
                            connection.execute(f'EXPLAIN DELETE FROM {q_odb}.{q_otbl}{fresh}').fetchone()
                            if cols:
                                set_clause=', '.join(f'{_quote(c)}={_quote(c)}' for c in cols)
                                connection.execute(f'EXPLAIN UPDATE {q_odb}.{q_otbl} SET {set_clause}{fresh}').fetchone()
    except (_PreservationRefused,sqlite3.Error) as error:
        raise ValueError('Native SQLite rename refused: '+str(error)) from None


def _parse_attachment_policy(baseline,rows,attachment_policy):
    all_namespaces={'main'}|{row['path'][0] for row in rows}|{
        row['name'] for row in baseline['rows'].values()
        if row['kind']=='database' and row['system']=='false'
    }
    if attachment_policy is None:
        if any(row['path'][0]!='main' for row in rows):
            raise ValueError('Native rename design generation for attached environments requires its attachment adapter')
        return 'main',{'main'},None
    if not isinstance(attachment_policy,dict) or set(attachment_policy)-{'target_namespace','attached_authorities','allow_non_carried_context'}:
        raise ValueError('Invalid SQLite rename attachment_policy')
    target_ns=attachment_policy.get('target_namespace','main')
    if not isinstance(target_ns,str) or not target_ns or target_ns not in (all_namespaces|{'temp'}):
        raise ValueError('Select an observed SQLite namespace in attachment_policy.target_namespace')
    all_namespaces.add(target_ns)
    non_carried=sorted(ns for ns in all_namespaces if ns!=target_ns)
    report={
        'target_namespace':target_ns,
        'observed_namespaces':sorted(all_namespaces),
        'non_carried_namespaces':non_carried,
        'attachment_authority':'retained-session-only' if (target_ns!='main' or any(ns!='main' for ns in all_namespaces)) else 'independent-main-file',
    }
    return target_ns,all_namespaces,report


def options(renames):
    if not isinstance(renames,(list,tuple)) or not 1<=len(renames)<=16:
        raise ValueError('Select one to sixteen exact native SQLite renames')
    result=[]
    for row in renames:
        if (not isinstance(row,dict) or row.get('kind') not in {'table','column'} or
                set(row)!=({'kind','table','to'} if row['kind']=='table' else {'kind','table','from','to'})):
            raise ValueError('Native rename requires exact kind, owning table and names')
        for key,value in row.items():
            if key!='kind':_quote(value)
        if row['to']==row.get('from',row['table']):raise ValueError('Select a different native name')
        result.append(dict(row))
    return result


def generate(baseline,renames,fts_rebindings=(),*,attachment_policy=None,loaded_extensions=(),_native_rebinding=False,_rewrite_runtime=None,_freeze_views=()):
    """Run schema-only native rewriting in an empty independent database."""
    from ..providers.sqlite import ddl_prepare
    from ..providers.sqlite.driver import SQLiteConnection
    conn_kw={'factory':SQLiteConnection} if attachment_policy is not None else {}
    selected=options(renames);probe=sqlite3.connect(':memory:',cached_statements=0,**conn_kw);rebindings=[];original=None;schema_ready=False
    try:
        if loaded_extensions and hasattr(sqlite3,'SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION'):
            try:
                probe.enable_load_extension(False)
                probe.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION,True)
                for ext in loaded_extensions:
                    kw={'entrypoint':ext['entrypoint']} if ext.get('entrypoint') else {}
                    probe.load_extension(ext['staged'],**kw)
            finally:
                probe.enable_load_extension(False)
                probe.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION,False)
        probe.execute('PRAGMA legacy_alter_table=OFF')
        probe.execute('PRAGMA foreign_keys=ON')
        rows=[row for row in baseline['rows'].values() if row['kind'] in KINDS and row['system']=='false']
        target_ns,all_namespaces,attachment_report=_parse_attachment_policy(baseline,rows,attachment_policy)
        for ns in sorted(all_namespaces-{'main','temp'}):
            probe.execute('ATTACH DATABASE \':memory:\' AS '+_quote(ns))
        from .sqlite_fts_rebind import plans as rebind_plans,equal
        if target_ns!='temp' and 'temp' in all_namespaces:
            temp_objects={r['name'] for r in rows if r['path'][0]=='temp' and r['kind'] in {'table','view','fts-table','virtual-table'}}
            for item in selected:
                candidates=[item['table'],item['to']] if item['kind']=='table' else [item['table']]
                for cand in candidates:
                    if any(equal(tname,cand) for tname in temp_objects):
                        raise ValueError(f'TEMP object shadows rename target {cand!r} in namespace {target_ns!r}; resolve TEMP masking before renaming')
        ns_selected=[{**item,'namespace':target_ns} for item in selected]
        rebindings=rebind_plans(baseline,ns_selected if target_ns!='main' else selected,fts_rebindings,namespace=target_ns)
        declarations=sorted((row for row in rows if row['kind'] in {'table','view','index','trigger','fts-table','virtual-table'}),
            key=lambda row:({'table':0,'fts-table':0,'virtual-table':0,'view':1,'index':2,'trigger':3}[row['kind']],0 if row['path'][0]!='temp' else 1,row['resource_id']))
        for row in declarations:
            raw_source=row['native'].get('ddl')
            if not isinstance(raw_source,str) or not raw_source or len(raw_source.encode('utf8'))>1024*1024:
                raise ValueError('Native rename requires complete bounded schema declarations')
            row_ns=row['path'][0]
            exec_source=raw_source if (attachment_policy is None and row_ns=='main') else ddl_prepare.source(row)
            if row['kind'] in {'fts-table','virtual-table'}:virtual_module(probe,row,namespace=row_ns)
            probe.execute(exec_source)
        from ..providers.sqlite.fts_configuration import statements
        for row in rows:
            if row['kind']=='fts-table':
                for source in statements(row['name'],row['native'].get('fts_configuration'),schema=row['path'][0]):probe.execute(source)
        view_names={(row['path'][0],row['name']) for row in declarations if row['kind']=='view'};view_reads=set()
        def observe_view_reads(action,name,column,database,context):
            if action==sqlite3.SQLITE_READ and (database,name) in view_names and context:
                view_reads.add((database,name,column))
            return sqlite3.SQLITE_OK
        probe.set_authorizer(observe_view_reads)
        try:
            reproduced=model(probe,baseline)
            if not _native_rebinding and (view_names or len(all_namespaces)>1):
                validate_dependencies(probe,namespaces=all_namespaces)
        finally:probe.set_authorizer(None)
        if schema(reproduced,namespaces=all_namespaces)!=schema(baseline,namespaces=all_namespaces):
            raise ValueError('The empty native rename schema cannot reproduce all baseline facts')
        schema_ready=True
        q_target_ns=_quote(target_ns)
        stages=[];rewritten=[]
        if _native_rebinding and target_ns=='main' and all_namespaces=={'main'}:
            from .sqlite_native_rebind import rewrite
            probe.commit();original=sqlite3.connect(':memory:',cached_statements=0);probe.backup(original)
            from .sqlite_fts_views import preserve_columns
            binding_declarations=[preserve_columns(row) if row['resource_id'] in _freeze_views else row for row in declarations]
            rewritten,runtime=rewrite(original,binding_declarations,selected,rebindings)
            if _rewrite_runtime is not None:_rewrite_runtime.update(runtime)
            for kind in ('trigger','view'):
                for row,_source in rewritten:
                    if row['kind']==kind:
                        source='DROP '+kind.upper()+' "main".'+_quote(row['name'])
                        probe.execute(source);stages.append(source)
        elif _freeze_views:
            from .sqlite_fts_views import preserve_columns
            for row in declarations:
                if row['resource_id'] in _freeze_views and row['kind']=='view' and row['path'][0]==target_ns:
                    preserved_ddl=ddl_prepare.source(preserve_columns(row))
                    drop_sql=f'DROP VIEW {q_target_ns}.{_quote(row["name"])}'
                    probe.execute(drop_sql);stages.append(drop_sql)
                    probe.execute(preserved_ddl);stages.append(preserved_ddl)
        for rebind in rebindings:
            for source in rebind['before']:probe.execute(source);stages.append(source)
        for item in selected:
            if probe.execute(f'SELECT type FROM {q_target_ns}.sqlite_schema WHERE name=?',(item['table'],)).fetchone()!=('table',):
                raise ValueError('Select an observed native table for each rename')
            source=f'ALTER TABLE {q_target_ns}.{_quote(item["table"])} RENAME '+(
                'TO '+_quote(item['to']) if item['kind']=='table' else 'COLUMN '+_quote(item['from'])+' TO '+_quote(item['to']))
            probe.execute(source);stages.append(source)
        for rebind in rebindings:
            for source in rebind['stages']:probe.execute(source);stages.append(source)
        for kind in ('view','trigger'):
            for row,source in rewritten:
                if row['kind']==kind:probe.execute(source);stages.append(source)
        if rewritten:
            views=[row for row,_source in rewritten if row['kind']=='view']
            before={row['name']:original.execute('PRAGMA main.table_xinfo('+_quote(row['name'])+')').fetchall() for row in views}
            inferred={}
            for _pass in range(len(views)+1):
                changed=False
                for row in views:
                    name=row['name']
                    try:after=probe.execute('PRAGMA main.table_xinfo('+_quote(name)+')').fetchall()
                    except sqlite3.Error:continue
                    if len(after)!=len(before[name]):raise ValueError('Native rename changed a derived view projection width')
                    for old,new in zip(before[name],after):
                        key=(name,old[0]);value=new[1]
                        if old[0]!=new[0]:raise ValueError('Native rename changed a derived view column ordinal')
                        if value!=inferred.get(key,old[1]):
                            inferred[key]=value;changed=True
                if not changed:break
                rebound,observed_runtime=rewrite(original,binding_declarations,selected,rebindings,
                    view_columns=[(name,index,value) for (name,index),value in sorted(inferred.items())])
                if observed_runtime!=runtime:raise ValueError('Native schema rewriter changed during derived-view binding')
                for kind in ('trigger','view'):
                    for row,_source in rewritten:
                        if row['kind']==kind:
                            source='DROP '+kind.upper()+' "main".'+_quote(row['name'])
                            probe.execute(source);stages.append(source)
                rewritten=rebound
                for kind in ('view','trigger'):
                    for row,source in rewritten:
                        if row['kind']==kind:probe.execute(source);stages.append(source)
            else:raise ValueError('Native derived-view bindings did not converge')
            validate_dependencies(probe,namespaces=all_namespaces)
        elif attachment_policy is not None:
            validate_dependencies(probe,namespaces=all_namespaces)
        generated=model(probe,baseline)
        from .sqlite_fts_views import changed_columns
        freeze=set(_freeze_views)|changed_columns(baseline,generated,namespace=target_ns)
        if freeze!=set(_freeze_views):
            probe.close()
            return generate(baseline,renames,fts_rebindings,attachment_policy=attachment_policy,
                loaded_extensions=loaded_extensions,_native_rebinding=(target_ns=='main' and all_namespaces=={'main'}),
                _rewrite_runtime=_rewrite_runtime,_freeze_views=freeze)
        if not _native_rebinding and target_ns=='main' and all_namespaces=={'main'} and view_reads:
            for row in declarations:
                if row['kind']!='view':continue
                current=generated['rows'].get(row['resource_id'])
                if current is None:continue
                old=row['native']['columns'];new=current['native']['columns']
                if len(old)!=len(new):raise ValueError('Native rename changed a dependent view projection width')
                if any(left['name']!=right['name'] and ('main',row['name'],left['name']) in view_reads for left,right in zip(old,new)):
                    probe.close()
                    return generate(baseline,renames,fts_rebindings,attachment_policy=attachment_policy,
                        loaded_extensions=loaded_extensions,_native_rebinding=True,_rewrite_runtime=_rewrite_runtime,_freeze_views=_freeze_views)
        desired=deepcopy(baseline)
        desired['rows']={identity:row for identity,row in desired['rows'].items() if row['kind'] not in KINDS}
        desired['rows'].update({identity:deepcopy(row) for identity,row in generated['rows'].items()
            if row['kind'] in KINDS and row['system']=='false'})
        if attachment_report is not None and _rewrite_runtime is not None:
            _rewrite_runtime['attachment_report']=attachment_report
        if _freeze_views and _rewrite_runtime is not None:_rewrite_runtime['preserved_fts_view_columns']=sorted(_freeze_views)
        return desired,selected,stages
    except sqlite3.Error as error:
        if not _native_rebinding and schema_ready and attachment_policy is None:
            probe.close()
            return generate(baseline,renames,fts_rebindings,attachment_policy=attachment_policy,
                loaded_extensions=loaded_extensions,_native_rebinding=True,_rewrite_runtime=_rewrite_runtime,_freeze_views=_freeze_views)
        raise ValueError('Native SQLite rename refused ('+str(getattr(error,'sqlite_errorname','SQLITE_ERROR'))+'): '+str(error)) from None
    finally:
        probe.close()
        if original is not None:original.close()


def plan(baseline,desired,live,renames,fts_rebindings=(),*,attachment_policy=None,loaded_extensions=()):
    runtime={}
    rows=[row for row in baseline['rows'].values() if row['kind'] in KINDS and row['system']=='false']
    target_ns,all_namespaces,attachment_report=_parse_attachment_policy(baseline,rows,attachment_policy)
    generated,selected,stages=generate(baseline,renames,fts_rebindings,attachment_policy=attachment_policy,
        loaded_extensions=loaded_extensions,_rewrite_runtime=runtime)
    from .sqlite_fts_rebind import plans as rebind_plans
    ns_selected=[{**item,'namespace':target_ns} for item in selected]
    rebuilds=rebind_plans(baseline,ns_selected if target_ns!='main' else selected,fts_rebindings,namespace=target_ns)
    conflicts=[];blockers=[]
    if schema(baseline,namespaces=all_namespaces)!=schema(live,namespaces=all_namespaces):
        conflicts.append({'resource_id':'','name':'SQLite rename','reason':'Native schema changed since the captured baseline'})
    if schema(generated,namespaces=all_namespaces)!=schema(desired,namespaces=all_namespaces):
        blockers.append({'resource_id':'','name':'SQLite rename','reason':'Desired DDN differs from the native rewritten schema; generate the rename design again'})
    if attachment_report is not None and attachment_report['non_carried_namespaces']:
        non_carried=set(attachment_report['non_carried_namespaces'])
        # Check whether any non-target persistent namespace was silently mutated (TEMP triggers targeting target_ns are allowed)
        non_temp_other=non_carried-{'temp'}
        if non_temp_other and schema(baseline,namespaces=non_temp_other)!=schema(generated,namespaces=non_temp_other):
            blockers.append({'resource_id':'','name':'SQLite rename','reason':'Cross-namespace persistent schema mutation detected outside target_namespace'})
    operation={'operation':'rename-batch','kind':'table','resource_id':'sqlite-native-rename-batch',
        'name':'Native table/column renames','renames':selected,'fts_rebindings':list(fts_rebindings),'stages':stages,
        'fts_rebuilds':[{**{key:item[key] for key in ('resource_id','source_name','name','module','original_content','content','configuration','column_renames')},
            **({'row_identity_mapping':item['row_identity_mapping']} if 'row_identity_mapping' in item else {})} for item in rebuilds],
        'source':'\n'.join(stage+';' for stage in stages),
        'baseline_schema_sha256':digest(schema(baseline,namespaces=all_namespaces)),
        'desired_schema_sha256':digest(schema(generated,namespaces=all_namespaces))}
    if attachment_policy is not None:
        operation['attachment_policy']=deepcopy(attachment_policy)
        operation['attachment_report']=attachment_report
    if runtime:operation['rewrite_runtime']=runtime
    ready=not conflicts and not blockers
    application_supported=ready and (attachment_report is None or (
        attachment_report['target_namespace']=='main' and not attachment_report['non_carried_namespaces']))
    return {'format':FORMAT,'engine':'sqlite','database_target_id':baseline['provenance']['database_target_id'],
        'operations':[operation],'blockers':blockers,'conflicts':conflicts,'execution_sha256':digest([operation]),
        **({'attachment_report':attachment_report} if attachment_report is not None else {}),
        'native_grammar_validated':True,'ready_for_review':ready,'application_supported':application_supported,
        'warnings':['SQLite rewrites table/column references using its native ALTER TABLE implementation. All original schema facts are rechecked before dispatch; the complete rewritten schema and bindings are checked before commit. Owner rows are not copied and trigger DML is not executed by this operation.',
            *(['Attached/TEMP namespaces ('+', '.join(attachment_report['non_carried_namespaces'])+') are non-carried by independent single-file apply; execute multi-namespace/TEMP renames through retained-session DDL or detach non-carried namespaces before single-file apply.'] if attachment_report and attachment_report['non_carried_namespaces'] else []),
            *(['The explicitly selected external-content FTS indexes are dropped, recreated and rebuilt from current content rows in this same transaction. Existing index drift is repaired. Native settings are preserved; index file formats remain engine-owned.'] if rebuilds else []),
            *(['Native document identities are preserved with the reviewed content mapping. FTS4 may create a content view; FTS5 uses its native content_rowid option.'] if any('row_identity_mapping' in item for item in rebuilds) else [])]}


def apply(provider,route,record):
    from ..providers.embedded_route import contained_database
    from .sqlite_schema_apply import _validate_dependencies
    path=contained_database(route);connection=None;dispatched=False;committed=False;close_failed=False
    def identity():
        info=os.stat(path)
        return stat.S_ISREG(info.st_mode) and [info.st_dev,info.st_ino]==record['file_identity']
    try:
        if path==':memory:' or route.get('read_only') is True or not identity():
            return {'state':'not_dispatched','reason':'Native SQLite rename file identity changed'}
        operation=record['plan']['operations'][0]
        expected=plan(record['baseline'],record['desired'],record['baseline'],operation['renames'],operation.get('fts_rebindings',()))
        if expected['operations']!=[operation] or not expected['ready_for_review']:
            return {'state':'not_dispatched','reason':'Reviewed native rename design changed'}
        connection=provider.client._connect({'route':route})
        connection.execute('PRAGMA legacy_alter_table=OFF');connection.execute('PRAGMA foreign_keys=ON')
        if connection.execute('PRAGMA legacy_alter_table').fetchone()!=(0,) or connection.execute('PRAGMA foreign_keys').fetchone()!=(1,):
            return {'state':'not_dispatched','reason':'Native SQLite rename modes unavailable'}
        connection.execute('BEGIN IMMEDIATE')
        if not identity() or digest(schema(model(connection,record['baseline'])))!=operation['baseline_schema_sha256']:
            connection.rollback();return {'state':'not_dispatched','reason':'Native SQLite rename schema or file changed since review'}
        violations=list(connection.execute('PRAGMA foreign_key_check'))
        for source in operation['stages']:
            dispatched=True;connection.execute(source)
        if digest(schema(model(connection,record['baseline'])))!=operation['desired_schema_sha256']:
            raise ValueError('Native SQLite rewritten schema differs from the reviewed postimage')
        _validate_dependencies(connection,{row['resource_id']:row for row in _resources(connection,{})})
        def renamed(name):
            for item in operation['renames']:
                if item['kind']=='table' and name==item['table']:name=item['to']
            return name
        preserved=Counter((renamed(table),rowid,renamed(parent),foreign_id) for table,rowid,parent,foreign_id in violations)
        if Counter(connection.execute('PRAGMA foreign_key_check'))!=preserved:
            raise ValueError('Native SQLite rename changed foreign-key violations')
        connection.commit();committed=True
    except Exception as error:
        uncertain=committed or (dispatched and uncertain_error(error) and not isinstance(error,ValueError))
        if connection is not None:
            try:connection.rollback()
            except Exception:uncertain=True
        return {'state':'unknown_outcome' if uncertain else 'rolled_back' if dispatched else 'not_dispatched',
            'rediscovery_verified':False,'error_type':type(error).__name__}
    finally:
        if connection is not None:
            try:provider.client._discard_failed_session(connection)
            except Exception:close_failed=True
    if close_failed:
        return {'state':'unknown_outcome','rediscovery_verified':False,'error_type':'SQLiteConnectionReleaseError'}
    try:
        captured=provider.capture_catalog(route,include_system=False)
        fresh=build_export(captured['resources'],endpoint_id=record['baseline']['provenance']['endpoint_id'],
            target_id=record['baseline']['provenance']['database_target_id'],generation=captured['generation'],engine='sqlite',native_model=True)
        verified=identity() and digest(schema(fresh))==operation['desired_schema_sha256']
        return {'state':'committed' if verified else 'unknown_outcome','rediscovery_verified':verified,'operations':len(operation['stages'])}
    except Exception as error:return {'state':'unknown_outcome','rediscovery_verified':False,'error_type':type(error).__name__}
