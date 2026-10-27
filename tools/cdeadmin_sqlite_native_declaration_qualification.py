"""Authenticated native SQLite catalog-DDL import and original-scope refusal."""
import argparse
import builtins
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    builtins.SERVER_MODE=None
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    for key,value in {'DATA_DIR':'app','SQLITE_PATH':'app/application.db','SESSION_DB_PATH':'app/sessions',
        'STORAGE_DIR':'app/storage','LOG_FILE':'app/application.log','AZURE_CREDENTIAL_CACHE_DIR':'app/azure',
        'CDEADMIN_OPERATION_STORE_PATH':'app/operations.json'}.items():setattr(config,key,str(output/value))
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.providers.sqlite.provider import _resources
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from flask import url_for
    paths=['tools/cdeadmin_sqlite_native_declaration_qualification.py',
        'web/pgadmin/cdeadmin/providers/sqlite/declarations.py',
        'web/pgadmin/cdeadmin/workspace/sqlite_schema_plan.py',
        'web/pgadmin/cdeadmin/workspace/sqlite_replace.py',
        'web/pgadmin/cdeadmin/workspace/sqlite_columns.py',
        'web/pgadmin/cdeadmin/workspace/sqlite_column_design.py',
        'web/pgadmin/cdeadmin/workspace/sqlite_catalog_service.py',
        'web/pgadmin/cdeadmin/workspace/service.py',
        'web/pgadmin/browser/server_groups/servers/__init__.py',
        'web/pgadmin/cdeadmin/providers/sqlite/ddl_prepare.py',
        'web/pgadmin/cdeadmin/providers/sqlite/fts_configuration.py',
        'web/pgadmin/cdeadmin/workspace/sqlite_retained_schema.py',
        'web/pgadmin/cdeadmin/workspace/sqlite_retained_alter.py',
        'web/pgadmin/cdeadmin/workspace/sqlite_retained_applications.py',
        'web/pgadmin/cdeadmin/workspace/sqlite_retained_service.py',
        'web/pgadmin/cdeadmin/data_studio/studio.py',
        'web/pgadmin/cdeadmin/data_studio/models.py',
        'web/pgadmin/cdeadmin/data_studio/scripts.py',
        'web/pgadmin/cdeadmin/workspace/sqlite_schema_apply.py']
    proof={'complete':False,'full_product_complete':False,'history_testing':'not run','sqlite_version':sqlite3.sqlite_version,
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}}
    assert sqlite3.sqlite_version=='3.53.0'
    path=output/'owned.sqlite'
    with sqlite3.connect(path) as connection:
        connection.executescript('CREATE TABLE owned(id INTEGER);CREATE TABLE effects(id INTEGER,note TEXT);')
        proof['sqlite_source_id']=connection.execute('SELECT sqlite_source_id()').fetchone()[0]
    app=create_app('ScratchRobin owned native SQLite declaration import');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start();client=app.test_client();session=None
    try:
        with app.test_request_context('/'):
            owner=User.query.first().id;group=ServerGroup.query.filter_by(user_id=owner).first()
            server=Server(user_id=owner,servergroup_id=group.id,name='Owned native declaration import',host=None,
                port=1,username='',maintenance_db=str(path),save_password=0)
            server._cde_endpoint_registration=registration_profile('sqlite-native')
            server._cde_endpoint_route_configuration={'database':str(path),'filesystem_root':str(output)}
            db.session.add(server);db.session.commit();target=str(uuid.uuid4());other=str(uuid.uuid4())
            for identity in (target,other):db.session.add(EndpointDatabaseTarget(id=identity,endpoint_id=server.endpoint_profile.id,
                display_name=identity,database=str(path),configuration='{}',active=1))
            db.session.commit()
            url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=server.id)
            verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=server.id)
        with client.session_transaction() as login:login['_user_id']=str(owner);login['_fresh']=True
        assert client.post(verify,json={}).get_json()['success']
        def post(action,refused=False,**fields):
            response=client.post(url,json={'action':action,'database_target_id':target,**fields});value=response.get_json()
            if refused:assert response.status_code in {400,403,409},value;return value
            assert response.status_code==200 and value.get('success'),value
            return value['data']
        def schema(action,request,refused=False):return post('sqlite_schema_'+action,refused,request={'database_target_id':target,**request})
        captured=post('sqlite_catalog_export',request={'database_target_id':target,'include_system':False})
        baseline=read_catalog(json.dumps(captured['snapshot']),engine='sqlite')
        # Desired catalog facts come from a real, empty native prototype. Bind
        # those new objects to this selected target's existing root and baseline.
        long_name='native_'+'ü'*180
        with sqlite3.connect(':memory:') as prototype:
            prototype.executescript('CREATE TABLE owned(id INTEGER);CREATE TABLE effects(id INTEGER,note TEXT);'
                'CREATE TABLE [new data](id INTEGER,txt TEXT DEFAULT \'ON main.owned CREATE TABLE\');'
                'CREATE VIEW "native_view"AS SELECT id,txt FROM [new data];'
                'CREATE UNIQUE INDEX native_index /* ON decoy */ ON owned(id) WHERE id>=0;'
                'CREATE TRIGGER native_trigger INSERT ON owned BEGIN INSERT INTO effects VALUES(NEW.id,\'CREATE TABLE main.never\'); END;'
                'CREATE TABLE "'+long_name+'"(n INTEGER);')
            proposed=_resources(prototype,{})
        identities=set(baseline['rows'])
        resources=[{'resource_id':row['resource_id'],'resource_kind':row['kind'],'display_name':row['name'],
            'display_path':row['path'],'native':deepcopy(row['native'])} for row in baseline['rows'].values()]
        resources.extend(row for row in proposed if row['resource_id'] not in identities and
            row['resource_kind'] in {'table','view','index','trigger','column','constraint'} and not row['native'].get('system_object'))
        desired=build_export(resources,endpoint_id=baseline['provenance']['endpoint_id'],target_id=target,
            generation='owned-native-prototype',include_system=False,refreshed=True,engine='sqlite')
        options={'baseline':json.dumps(captured['snapshot']),'desired':json.dumps(desired['snapshot'])}
        preview=schema('plan',options);assert preview['ready_for_review'],preview
        assert len(preview['operations'])==5 and all('"main".' in row['source'] for row in preview['operations'])
        review=schema('review',{**options,'execution_sha256':preview['execution_sha256']})
        request={'review_id':review['review_id'],'review_digest':review['review_digest'],'confirmed':True}
        result=schema('apply',request)
        assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
        assert schema('apply',request)['state']=='committed'
        schema('receipt',{'review_id':review['review_id'],'database_target_id':other},True)
        with sqlite3.connect(path) as independent:
            independent.execute('INSERT INTO "new data"(id) VALUES(7)');independent.execute('INSERT INTO owned VALUES(73)')
            assert independent.execute('SELECT * FROM native_view').fetchall()==[(7,'ON main.owned CREATE TABLE')]
            assert independent.execute('SELECT * FROM effects').fetchall()==[(73,'CREATE TABLE main.never')]
            assert not independent.execute("SELECT name FROM sqlite_schema WHERE name='never'").fetchall()
            assert independent.execute("SELECT sql FROM sqlite_schema WHERE name='native_index'").fetchone()[0].startswith('CREATE UNIQUE INDEX "native_index" /* ON decoy */ ON "owned"')
            assert independent.execute('SELECT name FROM sqlite_schema WHERE name=?',(long_name,)).fetchone()==(long_name,)
        proof.update(authenticated_native_catalog_DDN_import=True,native_table_view_index_trigger_creation=True,
            reviewed_apply_and_independent_rediscovery=True,duplicate_apply_never_replays=True,
            expression_and_trigger_literals_preserved=True,actual_view_and_trigger_execution=True,cross_target_receipt_refused=True)
        proof['native_identifier_over256bytes_preserved']=True
        def column_design(stages,extra=()):
            captured=post('sqlite_catalog_export',request={'database_target_id':target,'include_system':False})
            baseline=read_catalog(json.dumps(captured['snapshot']),engine='sqlite')
            with sqlite3.connect(path) as observer:
                definitions=observer.execute("SELECT type,sql FROM sqlite_schema WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'").fetchall()
            with sqlite3.connect(':memory:') as prototype:
                for _,source in sorted(definitions,key=lambda item:{'table':0,'view':1,'index':2,'trigger':3}[item[0]]):prototype.execute(source)
                for source in (*stages,*extra):prototype.execute(source)
                proposed=_resources(prototype,{})
            desired_resources=[{'resource_id':row['resource_id'],'resource_kind':row['kind'],'display_name':row['name'],
                'display_path':row['path'],'native':deepcopy(row['native'])} for row in baseline['rows'].values() if len(row['path'])==1]
            desired_resources.extend(row for row in proposed if len(row['display_path'])>1 and not row['native'].get('system_object'))
            document=build_export(desired_resources,endpoint_id=baseline['provenance']['endpoint_id'],target_id=target,
                generation='native-column-prototype',include_system=False,refreshed=True,engine='sqlite')
            options={'baseline':json.dumps(captured['snapshot']),'desired':json.dumps(document['snapshot'])}
            preview=schema('plan',options);assert preview['ready_for_review'],preview
            assert any(row['operation']=='append-columns' for row in preview['operations'])
            review=schema('review',{**options,'execution_sha256':preview['execution_sha256']})
            request={'review_id':review['review_id'],'review_digest':review['review_digest'],'confirmed':True}
            result=schema('apply',request);assert schema('apply',request)['state']==result['state']
            return result
        result=column_design(('ALTER TABLE owned ADD untyped',
            'ALTER TABLE owned ADD doubled AS (id * 2) VIRTUAL'),
            ('CREATE INDEX native_generated_index ON owned(doubled)',
             'CREATE TRIGGER native_generated_trigger AFTER INSERT ON owned BEGIN INSERT INTO effects VALUES(NEW.doubled,\'generated\'); END',
             'CREATE VIEW owned_projection AS SELECT * FROM owned'))
        assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
        with sqlite3.connect(path) as observer:
            assert observer.execute('SELECT doubled,untyped FROM owned_projection WHERE id=73').fetchone()==(146,None)
            observer.execute('INSERT INTO owned(id) VALUES(81)')
            assert observer.execute('SELECT id FROM owned INDEXED BY native_generated_index WHERE doubled=162').fetchall()==[(81,)]
            assert observer.execute("SELECT id FROM effects WHERE note='generated'").fetchall()==[(162,)]
        result=column_design(('ALTER TABLE "'+long_name+'" ADD stored AS (n * 2) STORED',))
        assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
        with sqlite3.connect(path) as observer:
            observer.execute('INSERT INTO "'+long_name+'"(n) VALUES(19)')
            assert observer.execute('SELECT stored FROM "'+long_name+'"').fetchone()==(38,)
        result=column_design(('ALTER TABLE owned ADD rolled_back_first',
            'ALTER TABLE owned ADD refused_stored AS (id * 2) STORED'))
        assert result['state']=='rolled_back' and 'STORED' in result['outcome']['native_error'],result
        with sqlite3.connect(path) as observer:
            assert not {'rolled_back_first','refused_stored'} & {row[1] for row in observer.execute('PRAGMA table_xinfo(owned)')}
            assert observer.execute('SELECT id FROM owned ORDER BY id').fetchall()==[(73,),(81,)]
        proof.update(native_catalog_derived_untyped_and_virtual_columns=True,
            new_column_indexes_triggers_and_view_projections=True,stored_generated_column_on_empty_table=True,
            stored_generated_column_native_nonempty_refusal=True,prior_column_stage_rolled_back=True,
            column_receipts_never_replay=True)
        with sqlite3.connect(path) as fixture:fixture.execute('CREATE TABLE column_parent(id INTEGER PRIMARY KEY)')
        captured=post('sqlite_catalog_export',request={'database_target_id':target,'include_system':False})
        from pgadmin.cdeadmin.providers.sqlite.provider import _resource_id
        specs=[{'name':'property untyped:雪'},
            {'name':'property generated','data_type':'INTEGER','generated':{'expression':'id * 3','storage':'virtual'},
                'constraint_names':{'generated':'calculated value'}},
            {'name':'property default','data_type':'TEXT','default':"'native, ON owned'",'nullable':False,
                'check':'length("property default") > 2','collation':'NOCASE',
                'constraint_names':{'not_null':'must exist','default':'native default','check':'length guard','collation':'case rule'}},
            {'name':'property reference','data_type':'INTEGER','references':{'table':'column_parent','column':'id',
                'on_update':'CASCADE','on_delete':'SET NULL','match':'simple','deferrable':True,'initially':'DEFERRED'},
                'constraint_names':{'references':'native link'}}]
        design_request={'baseline':json.dumps(captured['snapshot']),'resource_id':_resource_id('table',['main'],'owned'),'columns':specs}
        with sqlite3.connect(path) as observer:before_sql=observer.execute("SELECT sql FROM sqlite_schema WHERE name='owned'").fetchone()[0]
        generated=schema('column_design',design_request)
        with sqlite3.connect(path) as observer:
            assert observer.execute("SELECT sql FROM sqlite_schema WHERE name='owned'").fetchone()[0]==before_sql
            assert observer.execute('SELECT id FROM owned ORDER BY id').fetchall()==[(73,),(81,)]
        schema('column_design',{**design_request,'database_target_id':other},True)
        response=client.post(url+'?database_target_id='+target,json={'action':'sqlite_schema_column_design',
            'request':{**design_request,'database_target_id':other}})
        assert response.status_code==400
        options={'baseline':design_request['baseline'],'desired':json.dumps(generated['snapshot'])}
        preview=schema('plan',options);assert preview['ready_for_review'],preview
        reviewed=schema('review',{**options,'execution_sha256':preview['execution_sha256']})
        request={'review_id':reviewed['review_id'],'review_digest':reviewed['review_digest'],'confirmed':True}
        result=schema('apply',request);assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
        assert schema('apply',request)['state']=='committed'
        schema('column_design',design_request,True)
        with sqlite3.connect(path) as observer:
            assert observer.execute('SELECT "property generated","property default","property untyped:雪" FROM owned WHERE id=73').fetchone()==(219,'native, ON owned',None)
            observer.execute('PRAGMA foreign_keys=ON');observer.execute('BEGIN')
            observer.execute('UPDATE owned SET "property reference"=9 WHERE id=73')
            observer.execute('INSERT INTO column_parent VALUES(9)');observer.commit()
            observer.execute('UPDATE column_parent SET id=10')
            assert observer.execute('SELECT "property reference" FROM owned WHERE id=73').fetchone()==(10,)
            observer.execute('DELETE FROM column_parent')
            assert observer.execute('SELECT "property reference" FROM owned WHERE id=73').fetchone()==(None,)
        proof.update(structured_column_properties_generate_DDN=True,generation_does_not_mutate_registered_file=True,
            structured_constraint_names_and_native_properties=True,native_deferred_reference_and_actions=True,
            column_generation_target_and_URL_scope_refused=True,stale_column_generation_refused=True)
        session=post('open_session',language_profile='sqlite-sql')['session_id']
        def execute(source):
            started=post('execute',session_id=session,source=source,parameters={},history_sensitive=True)
            deadline=time.monotonic()+20
            while True:
                occurrence=post('poll',occurrence_id=started['occurrence_id'])['occurrence']
                payload=(occurrence.get('result') or {}).get('extensions',{}).get('sqlite',{}).get('payload',{})
                if occurrence['operation']['terminal']:
                    assert not payload.get('error'),payload
                    return payload.get('rows',[])
                assert time.monotonic()<deadline;time.sleep(.02)
        execute('CREATE TEMP TABLE same_name(id INTEGER)');execute('BEGIN');execute('INSERT INTO owned(id) VALUES(99)')
        retained=post('source_catalog',session_id=session)
        retained_model=read_catalog(json.dumps(retained['document']['snapshot']),engine='sqlite')
        rebound=build_export([{'resource_id':row['resource_id'],'resource_kind':row['kind'],'display_name':row['name'],
            'display_path':row['path'],'native':row['native']} for row in retained_model['rows'].values()],
            endpoint_id=baseline['provenance']['endpoint_id'],target_id=target,generation='owned-retained-rebinding-refusal',
            include_system=False,refreshed=True,engine='sqlite')
        schema('plan',{'baseline':json.dumps(rebound['snapshot']),'desired':json.dumps(rebound['snapshot'])},True)
        schema('column_design',{'baseline':json.dumps(rebound['snapshot']),
            'resource_id':_resource_id('table',['main'],'owned'),'columns':[{'name':'never'}]},True)
        execute('CREATE TABLE main.same_name(id INTEGER)');execute('INSERT INTO main.same_name VALUES(301)')
        attached=str(output/'retained-attached.sqlite').replace("'","''")
        execute("ATTACH DATABASE '"+attached+"' AS \"retained.雪\"")
        execute('CREATE TABLE "retained.雪".same_name(id INTEGER)');execute('INSERT INTO "retained.雪".same_name VALUES(17)')
        execute('SAVEPOINT original_design_guard')
        receipts=[]
        def retained_action(operation,fields=None,archived=False,**extra):
            return post('sqlite_retained_schema_receipts' if archived else 'sqlite_retained_schema',
                **({} if archived else {'session_id':session}),request={'operation':operation,**(fields or {})},**extra)
        def prepare_columns(namespace,columns):
            observed=post('source_catalog',session_id=session)
            baseline=json.dumps(observed['document']['snapshot'])
            if not proof.get('native_retained_grammar_refusal_before_mutation'):
                native_model=read_catalog(baseline,engine='sqlite')
                bad_id=_resource_id('table',['temp'],'never_created')
                resources=[{'resource_id':row['resource_id'],'resource_kind':row['kind'],'display_name':row['name'],
                    'display_path':row['path'],'native':row['native']} for row in native_model['rows'].values()]
                resources.append({'resource_id':bad_id,'resource_kind':'table','display_name':'never_created',
                    'display_path':['temp','never_created'],'native':{'system_object':False,
                    'ddl':'CREATE TABLE "temp"."never_created"(id INTEGER,)','observation_scope':'retained-session-design',
                    'catalog_metadata':{'schema_object_type':'table','table_name':'never_created','table_list_type':'table',
                        'without_rowid':False,'strict':False}}})
                invalid=build_export(resources,endpoint_id=native_model['provenance']['endpoint_id'],
                    target_id='retained-session:'+session,generation='native-grammar-refusal',engine='sqlite')
                post('sqlite_retained_schema',True,session_id=session,request={'operation':'preview','baseline':baseline,
                    'desired':json.dumps(invalid['snapshot']),'deletions':[]})
                assert execute("SELECT name FROM temp.sqlite_schema WHERE name='never_created'")==[]
                proof['native_retained_grammar_refusal_before_mutation']=True
            generated=retained_action('columns',{'baseline':baseline,
                'resource_id':_resource_id('table',[namespace],'same_name'),'columns':columns})
            options={'baseline':baseline,'desired':json.dumps(generated['snapshot']),'deletions':[]}
            preview=retained_action('preview',options);assert preview['ready_for_review'],preview
            review=retained_action('review',{**options,'execution_sha256':preview['execution_sha256']})
            receipts.append(review['review_id'])
            return {'review_id':review['review_id'],'review_digest':review['review_digest'],'confirmed':True}
        def apply_retained(request):
            value=retained_action('start',request);deadline=time.monotonic()+30
            while not value['native_session_release_confirmed']:
                assert time.monotonic()<deadline;time.sleep(.02)
                value=retained_action('receipt',{'review_id':request['review_id']},True)
            return value
        request=prepare_columns('temp',[{'name':'native label','data_type':'TEXT','default':"'TEMP literal'"},
            {'name':'native stored','generated':{'expression':'id * 4','storage':'stored'}}])
        value=apply_retained(request)
        assert value['state']=='applied_pending_caller_transaction' and value['outcome']['commit_dispatched'] is False,value
        execute('INSERT INTO temp.same_name(id) VALUES(7)')
        assert execute('SELECT "native label","native stored" FROM temp.same_name')==[['TEMP literal',28]]
        assert execute('SELECT * FROM main.same_name')==[[301]]
        request=prepare_columns('retained.雪',[{'name':'native computed','generated':{'expression':'id * 5','storage':'virtual'}}])
        value=apply_retained(request);assert value['state']=='applied_pending_caller_transaction',value
        assert execute('SELECT "native computed" FROM "retained.雪".same_name')==[[85]]
        assert retained_action('start',request)['state']=='applied_pending_caller_transaction'
        scoped=client.post(url+'?database_target_id='+target,json={'action':'sqlite_retained_schema_receipts',
            'database_target_id':other,'request':{'operation':'list'}})
        assert scoped.status_code==400
        request=prepare_columns('main',[{'name':'must_not_dispatch'}])
        execute('SELECT 1')  # Same schema/transaction/data; the original request revision changed.
        value=apply_retained(request);assert value['state']=='not_dispatched',value
        assert execute('SELECT count(*) FROM pragma_table_xinfo(\'same_name\',\'main\')')==[[1]]
        execute('ROLLBACK TO original_design_guard');execute('RELEASE original_design_guard')
        assert execute('SELECT * FROM main.same_name')==[[301]]
        assert execute('SELECT * FROM "retained.雪".same_name')==[[17]]
        assert execute('SELECT * FROM temp.same_name')==[]
        proof.update(original_session_DDN_column_workflow=True,actual_temp_stored_and_attached_virtual_columns=True,
            same_name_namespace_shadowing_preserved=True,original_caller_savepoint_preserved=True,
            original_session_revision_drift_refused=True,retained_DDL_URL_scope_refused=True)
        # Native3.53 ALTER forms use the same authenticated review, original
        # handle, durable acknowledgement and caller-owned transaction path.
        for namespace in ('main','temp','retained.雪'):
            execute('CREATE TABLE "'+namespace+'".alter_source(id INTEGER,payload TEXT,removed INTEGER,nn TEXT NOT NULL DEFAULT \'x\',CONSTRAINT positive CHECK(id>0))')
            execute('INSERT INTO "'+namespace+'".alter_source(id,payload,removed) VALUES(7,\'pending\',8)')
        def prepare_alterations(changes):
            observed=post('source_catalog',session_id=session)
            baseline=json.dumps(observed['document']['snapshot'])
            generated=retained_action('alter',{'baseline':baseline,'alterations':changes})
            from pgadmin.cdeadmin.workspace.sqlite_retained_schema import KINDS
            original_model=read_catalog(baseline,engine='sqlite')
            generated_model=read_catalog(json.dumps(generated['snapshot']),engine='sqlite')
            for key,row in original_model['rows'].items():
                if row['kind'] not in KINDS:
                    actual=generated_model['rows'][key]
                    assert all(actual[field]==row[field] for field in ('kind','path','name','native'))
            proof['native_alter_original_non_schema_observations_preserved']=True
            options={'baseline':baseline,'desired':json.dumps(generated['snapshot']),'deletions':[],'alterations':changes}
            preview=retained_action('preview',options);assert preview['ready_for_review'],preview
            review=retained_action('review',{**options,'execution_sha256':preview['execution_sha256']})
            receipts.append(review['review_id'])
            return {'review_id':review['review_id'],'review_digest':review['review_digest'],'confirmed':True}
        alterations={'rename-table':{'name':'renamed:雪'},'rename-column':{'column':'payload','name':'renamed:雪'},
            'drop-column':{'column':'removed'},'drop-constraint':{'name':'positive'},'drop-not-null':{'column':'nn'},
            'set-not-null':{'column':'payload','conflict':'ABORT'},'add-check':{'expression':'id < 10','name':'bounded','conflict':'FAIL'}}
        native_alter_receipts=[]
        for namespace in ('main','temp','retained.雪'):
            for action,fields in alterations.items():
                execute('SAVEPOINT native_alter_guard')
                changes=[{'action':action,'resource_id':_resource_id('table',[namespace],'alter_source'),**fields}]
                request=prepare_alterations(changes);value=apply_retained(request)
                assert value['state']=='applied_pending_caller_transaction' and value['outcome']['rediscovery_verified'],value
                name='renamed:雪' if action=='rename-table' else 'alter_source'
                expected=[[7,'pending','x']] if action=='drop-column' else [[7,'pending',8,'x']]
                assert execute('SELECT * FROM "'+namespace+'"."'+name+'"')==expected
                assert retained_action('start',request)['state']=='applied_pending_caller_transaction'
                execute('ROLLBACK TO native_alter_guard');execute('RELEASE native_alter_guard')
                assert execute('SELECT * FROM "'+namespace+'".alter_source')==[[7,'pending',8,'x']]
                native_alter_receipts.append({'namespace':namespace,'action':action,'review_id':request['review_id']})
        identity=_resource_id('table',['temp'],'alter_source')
        request=prepare_alterations([{'action':'add-check','resource_id':identity,'name':'"positive"','expression':'id < 10'}])
        assert apply_retained(request)['state']=='applied_pending_caller_transaction'
        request=prepare_alterations([{'action':'drop-constraint','resource_id':identity,'name':'"positive"'}])
        assert apply_retained(request)['state']=='applied_pending_caller_transaction'
        execute('INSERT INTO temp.alter_source(id,payload,removed) VALUES(20,\'exact constraint\',8)')
        assert execute('SELECT id FROM temp.alter_source ORDER BY id')==[[7],[20]]
        execute('DELETE FROM temp.alter_source WHERE id=20')
        proof['native_constraint_literal_quote_identity_preserved']=True
        execute('INSERT INTO temp.alter_source(id,payload,removed) VALUES(17,\'bad\',NULL)')
        request=prepare_alterations([{'action':'rename-column','resource_id':identity,'column':'payload','name':'renamed'},
            {'action':'set-not-null','resource_id':identity,'column':'removed'}])
        value=apply_retained(request)
        assert value['state']=='rolled_back_to_savepoint' and value['outcome']['completed_statements']==1,value
        assert execute('SELECT id,payload,removed FROM temp.alter_source ORDER BY id')==[[7,'pending',8],[17,'bad',None]]
        assert retained_action('start',request)['state']=='rolled_back_to_savepoint'
        proof.update(native_original_session_alter_forms=native_alter_receipts,
            actual_native_alter_in_main_temp_attached=True,native_alter_data_refusal_restored_prior_stage=True,
            native_alter_receipts_never_replay=True)
        assert execute('SELECT count(*) FROM owned WHERE id=99')==[[1]]
        with sqlite3.connect(path) as independent:assert independent.execute('SELECT count(*) FROM owned WHERE id=99').fetchone()==(0,)
        post('transaction_action',session_id=session,transaction_action='rollback')
        post('close_session',session_id=session);session=None
        from unittest.mock import patch
        workspace=app.extensions['cdeadmin_provider_workspace']
        with patch.object(workspace.endpoint_service,'workspace',side_effect=AssertionError('archive must not resolve SQL workspace')):
            for identity in receipts:
                value=retained_action('receipt',{'review_id':identity},True)
                assert value['native_session_release_confirmed'] and not value['native_sql_requested']
            assert retained_action('list',archived=True)['total']==len(receipts)
        proof['retained_DDL_archives_read_after_close_without_SQL_workspace']=True
        proof.update(retained_scope_not_promoted_to_independent_authority=True,original_pending_rows_preserved=True,complete=True)
    finally:
        if session:post('close_session',session_id=session)
        proof['owned_sessions_released']=not app.extensions['cdeadmin_data_studio']._sessions
        (output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    value=qualify(parser.parse_args().evidence);print(json.dumps({'complete':value['complete']}))
