"""Native connection captures, streamed exports and authenticated offline delivery."""
import argparse
import base64
import builtins
import ctypes
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def independent_apply(core,cli,changeset,database,query=None):
    """Use the pinned core's public C API, independently of the capture bridge."""
    native=ctypes.CDLL(str(core));db=ctypes.c_void_p()
    native.sqlite3_open_v2.argtypes=[ctypes.c_char_p,ctypes.POINTER(ctypes.c_void_p),ctypes.c_int,ctypes.c_char_p]
    native.sqlite3_close.argtypes=[ctypes.c_void_p]
    assert native.sqlite3_open_v2(str(database).encode(),ctypes.byref(db),6,None)==0
    callback=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int))
    @callback
    def read(_context,buffer,length):
        block=stream.read(length[0]);ctypes.memmove(buffer,block,len(block));length[0]=len(block);return 0
    native.sqlite3changeset_apply_strm.argtypes=[ctypes.c_void_p,callback,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
    try:
        with changeset.open('rb') as stream:assert native.sqlite3changeset_apply_strm(db,read,None,None,None,None)==0
    finally:assert native.sqlite3_close(db)==0
    sql=query or 'SELECT CAST(id AS TEXT),length(body),hex(payload) FROM "native\n雪"'
    return subprocess.check_output([str(cli),'-json',str(database),sql],text=True)


def independent_rebase(core,local,buffer):
    native=ctypes.CDLL(str(core));handle=ctypes.c_void_p();result=ctypes.c_void_p();length=ctypes.c_int()
    native.sqlite3rebaser_create.argtypes=[ctypes.POINTER(ctypes.c_void_p)]
    native.sqlite3rebaser_configure.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p]
    native.sqlite3rebaser_rebase.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_void_p)]
    native.sqlite3rebaser_delete.argtypes=[ctypes.c_void_p];native.sqlite3_free.argtypes=[ctypes.c_void_p]
    local_buffer=ctypes.create_string_buffer(local);rebase_buffer=ctypes.create_string_buffer(buffer)
    assert native.sqlite3rebaser_create(ctypes.byref(handle))==0
    try:
        assert native.sqlite3rebaser_configure(handle,len(buffer),rebase_buffer)==0
        assert native.sqlite3rebaser_rebase(handle,len(local),local_buffer,ctypes.byref(length),ctypes.byref(result))==0
        return ctypes.string_at(result,length.value)
    finally:native.sqlite3_free(result);native.sqlite3rebaser_delete(handle)


def qualify(output,library,core,cli,*,browser_binary=None,driver_binary=None,array_library=None,preupdate_library=None):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    proof={'complete':False,'history_testing':'not run','checks':[],'source_sha256':{}}
    for path in [Path(__file__),ROOT/'tools/native/sqlite_sessions/api.c',
                 *list((ROOT/'web/pgadmin/cdeadmin/providers/sqlite').glob('session*.py')),
                 *list((ROOT/'web/pgadmin/cdeadmin/workspace').glob('sqlite_capture*.py')),
                 *list((ROOT/'web/pgadmin/cdeadmin/workspace').glob('sqlite_changeset*.py')),
                 *list((ROOT/'web/pgadmin/cdeadmin/workspace').glob('sqlite_upload*.py')),
                 *list((ROOT/'web/pgadmin/cdeadmin/workspace').glob('sqlite_transform*.py')),
                 ROOT/'web/pgadmin/cdeadmin/workspace/sqlite_native_files.py',
                 ROOT/'web/pgadmin/cdeadmin/providers/sqlite/changeset_transform.py',ROOT/'web/pgadmin/cdeadmin/providers/sqlite/transform_context.py',
                 ROOT/'web/pgadmin/static/js/Dialogs/SQLiteNativeTransforms.jsx',
                 ROOT/'web/pgadmin/cdeadmin/providers/sqlite/changeset_apply.py',
                 ROOT/'web/pgadmin/static/js/Dialogs/SQLiteChangesetApply.jsx',ROOT/'web/pgadmin/static/js/Dialogs/SQLiteNativeUpload.jsx',
                 ROOT/'web/pgadmin/cdeadmin/data_studio/studio.py',ROOT/'web/pgadmin/cdeadmin/workspace/service.py',
                 ROOT/'web/pgadmin/browser/server_groups/servers/__init__.py']:
        proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    for path in [*list((ROOT/'web/pgadmin/cdeadmin/providers/sqlite').glob('array*.py')),ROOT/'tools/native/sqlite_arrays/api.c',ROOT/'tools/native/sqlite_arrays/CMakeLists.txt',ROOT/'web/pgadmin/static/js/Dialogs/SQLiteNativeArrays.jsx']:
        proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    for path in [*list((ROOT/'web/pgadmin/cdeadmin/providers/sqlite').glob('preupdate*.py')),ROOT/'tools/native/sqlite_preupdate/api.c',ROOT/'tools/native/sqlite_preupdate/CMakeLists.txt',ROOT/'tools/native/sqlite_hook_ownership.h',ROOT/'web/pgadmin/static/js/Dialogs/SQLitePreupdate.jsx']:
        proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    for path in [ROOT/'web/pgadmin/cdeadmin/providers/sqlite/changeset_inspection.py',ROOT/'web/pgadmin/cdeadmin/workspace/sqlite_inspection_jobs.py',ROOT/'web/pgadmin/cdeadmin/workspace/sqlite_inspection_service.py',ROOT/'web/pgadmin/static/js/Dialogs/SQLiteChangesetInspection.jsx']:
        proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    for path in [ROOT/'web/pgadmin/cdeadmin/providers/sqlite/conflict_channel.py',ROOT/'web/pgadmin/static/js/Dialogs/SQLiteConflictDecisions.jsx']:
        proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    for path in [ROOT/'web/pgadmin/cdeadmin/providers/sqlite/diff_export.py',
                 *list((ROOT/'web/pgadmin/cdeadmin/workspace').glob('sqlite_diff*.py')),
                 ROOT/'web/pgadmin/static/js/Dialogs/SQLiteNativeDiff.jsx',ROOT/'web/pgadmin/static/js/Dialogs/SQLiteNativeSessions.jsx']:
        proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    builtins.SERVER_MODE=None
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    for name,filename in {'DATA_DIR':'app','SQLITE_PATH':'app/application.db','SESSION_DB_PATH':'app/sessions',
            'STORAGE_DIR':'app/storage','LOG_FILE':'app/application.log','AZURE_CREDENTIAL_CACHE_DIR':'app/azure',
            'CDEADMIN_OPERATION_STORE_PATH':'app/operations.json','CDEADMIN_SQLITE_CAPTURE_ROOT':'capture-jobs'}.items():
        setattr(config,name,str(output/filename))
    config.CDEADMIN_SQLITE_SESSION_LIBRARY=str(Path(library).resolve(strict=True))
    if array_library:config.CDEADMIN_SQLITE_ARRAY_LIBRARY=str(Path(array_library).resolve(strict=True))
    if preupdate_library:config.CDEADMIN_SQLITE_PREUPDATE_LIBRARY=str(Path(preupdate_library).resolve(strict=True))
    source=output/'native.sqlite';schema='CREATE TABLE "native\n雪"(id INTEGER PRIMARY KEY,body TEXT,payload BLOB)'
    assert sqlite3.sqlite_version=='3.53.0'
    with sqlite3.connect(source) as connection:
        connection.execute('PRAGMA journal_mode=WAL');connection.execute(schema)
    baseline=output/'baseline.sqlite'
    with sqlite3.connect(baseline) as connection:
        connection.execute(schema);connection.execute('INSERT INTO "native'+chr(10)+'雪" VALUES(44,?,?)',('baseline',b'\x01'))
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from flask import url_for
    app=create_app('ScratchRobin-native-sqlite-capture');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY='';app.run_before_app_start()
    client=app.test_client()
    try:
        with app.test_request_context('/'):
            user=User.query.first();uid=user.id;group=ServerGroup.query.filter_by(user_id=uid).first()
            app.blueprints['NODE-engine_type'].connector_visibility['sqlite'].set(True,user_id=uid)
            server=Server(user_id=uid,servergroup_id=group.id,name='Owned SQLite native captures',host=None,port=1,username='',maintenance_db=str(source),save_password=0)
            server._cde_endpoint_registration=registration_profile('sqlite-native')
            server._cde_endpoint_route_configuration={'database':str(source),'filesystem_root':str(output),'attached_databases':[{'name':'baseline 雪','database':str(baseline)}]}
            db.session.add(server);db.session.commit();target=str(uuid.uuid4());other=str(uuid.uuid4())
            for identity,path in ((target,source),(other,output/'another.sqlite')):
                if identity==other:
                    with sqlite3.connect(path) as connection:
                        connection.execute(schema);connection.execute('CREATE TABLE external_file(id INTEGER PRIMARY KEY,body TEXT,payload BLOB)')
                db.session.add(EndpointDatabaseTarget(id=identity,endpoint_id=server.endpoint_profile.id,display_name=path.name,database=str(path),configuration='{}',active=1))
            db.session.commit();server_id=server.id;url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=server.id)
            verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=server.id)
        with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
        assert client.post(verify,json={}).get_json()['success']
        cli_identity=json.loads(subprocess.check_output([str(cli),'-json',':memory:',
            'SELECT sqlite_version() AS version,sqlite_source_id() AS source_id'],text=True))[0]
        assert cli_identity['version']=='3.53.0'
        proof['independent_cli']={**cli_identity,'binary_sha256':hashlib.sha256(Path(cli).read_bytes()).hexdigest()}
        def post(action,**fields):
            response=client.post(url,json={'action':action,'database_target_id':target,**fields});value=response.get_json()
            assert response.status_code==200 and value.get('success'),(action,response.status_code,value)
            return value['data']
        session_id=post('open_session',language_profile='sqlite-sql')['session_id']
        def capture(operation,**fields):return post('sqlite_native_sessions',session_id=session_id,request={'operation':operation,**fields})
        def export(operation,**fields):return post('sqlite_capture_export_'+operation,request={'database_target_id':target,**fields})
        def execute(source,parameters=None,*,retained_session_id=None,database_target_id=None):
            database_target_id=database_target_id or target
            started=post('execute',database_target_id=database_target_id,session_id=retained_session_id or session_id,source=source,parameters=parameters or {},history_sensitive=True)
            deadline=time.monotonic()+30;rows=[]
            while time.monotonic()<deadline:
                occurrence=post('poll',database_target_id=database_target_id,occurrence_id=started['occurrence_id'])['occurrence']
                payload=(occurrence.get('result') or {}).get('extensions',{}).get('sqlite',{}).get('payload',{})
                rows.extend(payload.get('rows') or [])
                if occurrence['operation']['terminal']:
                    assert not payload.get('error'),payload
                    return rows,payload
                time.sleep(.02)
            raise TimeoutError('Native SQLite query worker')
        if array_library:
            def array(operation,**fields):return post('sqlite_native_arrays',session_id=session_id,request={'operation':operation,**fields})
            inventory=array('inventory');assert inventory['helper_available'] and not inventory['native_context_initialized']
            proof['native_array_program']=inventory['program']
            for kind,values,expected in [
                ('int32',[-2147483648,2147483647],[[-2147483648,'integer'],[2147483647,'integer']]),
                ('int64',['9007199254740993','9223372036854775807'],[['9007199254740993','integer'],['9223372036854775807','integer']]),
                ('double',['0.1','inf','nan'],[['0.1','real'],['inf','real'],[None,'null']]),
                ('text',['雪😀','',None],[['雪😀','text'],['','text'],[None,'null']]),
                ('blob',[{'encoding':'base64','data':'AP8='},None,{'encoding':'base64','data':''}],[[{'encoding':'base64','data':'AP8=','byte_length':2},'blob'],[None,'null'],[{'encoding':'base64','data':'','byte_length':0},'blob']])]:
                created=array('create',type=kind,values=values)['array'];binding=created['binding']
                observed,_payload=execute('SELECT value,typeof(value) FROM carray(:items)',{'items':binding});assert observed==expected,(kind,observed)
                refused=client.post(url,json={'action':'sqlite_native_arrays','database_target_id':other,'session_id':session_id,'request':{'operation':'status','array_id':created['array_id']}})
                assert refused.status_code!=200 or not refused.get_json().get('success')
                assert array('close',array_id=created['array_id'],confirmed=True)['closed']
            assert array('inventory')['total']==0
            proof['checks'].append('authenticated-retained-native-array-bindings-all-five-types-wide-int64-null-empty-binary-and-target-ownership')
        if preupdate_library:
            def preupdate(operation,**fields):return post('sqlite_native_preupdate',session_id=session_id,request={'operation':operation,**fields})
            assert preupdate('inventory')['helper_available']
            execute('CREATE TEMP TABLE preupdate_check(id INTEGER PRIMARY KEY,body TEXT,b BLOB)')
            started=preupdate('start',max_events=100,max_json_bytes='1048576');run=started['status']['run_id'];proof['native_preupdate_program']=started['program']
            execute('BEGIN');execute('INSERT INTO preupdate_check VALUES(?,?,?)',[{'encoding':'integer','data':'9007199254740993'},'雪'+chr(0)+'😀',{'encoding':'base64','data':'AP8='}])
            execute('UPDATE preupdate_check SET body=NULL');execute('DELETE FROM preupdate_check');execute('ROLLBACK')
            page=preupdate('events',run_id=run,after_sequence='0',limit=25)
            assert [event['operation'] for event in page['events']]==['insert','update','delete']
            assert page['events'][0]['database']=='temp' and page['events'][0]['new_values']==[
                {'native_type':'integer','data':'9007199254740993'},{'native_type':'text','data':'雪'+chr(0)+'😀'},
                {'native_type':'blob','data':{'encoding':'base64','data':'AP8=','byte_length':2}}]
            observed,_payload=execute('SELECT count(*) FROM preupdate_check');assert observed==[[0]]
            refused=client.post(url,json={'action':'sqlite_native_sessions','database_target_id':target,'session_id':session_id,'request':{'operation':'open','database':'main'}})
            assert refused.status_code!=200 or not refused.get_json().get('success')
            preupdate('stop',run_id=run);preupdate('clear',run_id=run,confirmed=True)
            refused=client.post(url,json={'action':'sqlite_native_preupdate','database_target_id':target,'session_id':session_id,'request':{'operation':'events','run_id':run}})
            assert refused.status_code!=200 or not refused.get_json().get('success')
            proof['checks'].append('authenticated-native-preupdate-insert-update-delete-typed-data-rollback-observations-hook-exclusion-and-generation-refusal')
        comparison=capture('open',database='main')['capture']['capture_id']
        compared=capture('diff',capture_id=comparison,source_database='baseline 雪',table_name='native'+chr(10)+'雪')
        assert not compared['capture']['empty'] and compared['capture']['tables']==['native'+chr(10)+'雪']
        assert not compared['database_mutation']
        capture('close',capture_id=comparison,confirmed=True)
        filtered=capture('open',database='main')['capture']['capture_id']
        capture('table_filter',capture_id=filtered,pattern='filter_keep*',exclude=False)
        execute('CREATE TABLE filter_keep(id INTEGER PRIMARY KEY)');execute('CREATE TABLE filter_skip(id INTEGER PRIMARY KEY)')
        execute('BEGIN');execute('INSERT INTO filter_keep VALUES(1)');execute('INSERT INTO filter_skip VALUES(1)')
        assert not capture('status',capture_id=filtered)['capture']['empty']
        capture('table_filter',capture_id=filtered,pattern=None,exclude=False)
        execute('ROLLBACK');capture('close',capture_id=filtered,confirmed=True)
        proof['checks'].append('authenticated-native-table-glob-filter-and-attached-baseline-diff-change-only-capture-memory-with-explicit-attachment-metadata')
        assert capture('inventory')['helper_available']
        opened=capture('open',database='main',estimate_size=True,track_rowids=False)['capture'];capture_id=opened['capture_id']
        capture('attach',capture_id=capture_id,table_name='native\n雪')
        execute('BEGIN');execute('INSERT INTO "native\n雪" VALUES(9007199254740993,?,x\'0080FF\')',['native 😀'*300000])
        proof['checks'].append('authenticated-capture-on-retained-query-with-exact-newline-unicode-table-and-pending-large-data')
        exports={}
        for kind in ('changeset','patchset'):
            reviewed=export('review',session_id=session_id,capture_id=capture_id,kind=kind,timeout_seconds=60)
            exports[kind]=reviewed['job_id']
            request={'job_id':reviewed['job_id'],'review_digest':reviewed['review_digest'],'confirmed':True}
            started=export('start',**request);deadline=time.monotonic()+30
            while started['state'] in {'active','dispatching','publishing','cancel_requested'}:
                assert time.monotonic()<deadline;time.sleep(.02);started=export('status',job_id=reviewed['job_id'])
            assert started['state']=='completed',started
            assert started['native_returned'] and started['source_transaction_open'] and started['source_transaction_open_after']
            assert started['result']['artifact']['native_record_count']=='1'
            assert export('start',**request)['state']=='completed'
            files=export('files',job_id=reviewed['job_id'])['files'];row=next(row for row in files if row['path']=='capture.'+kind)
            payload={'database_target_id':target,'job_id':reviewed['job_id'],'path':row['path']}
            response=client.post(url,data={'action':'sqlite_capture_export_download','payload':json.dumps(payload)})
            assert response.status_code==200 and response.headers.get('X-Content-Type-Options')=='nosniff'
            data=response.data;assert len(data)==int(row['size'])>2200000 and hashlib.sha256(data).hexdigest()==row['sha256']
            artifact=output/row['path'];artifact.write_bytes(data)
            destination=output/('independent-'+kind+'.sqlite')
            with sqlite3.connect(destination) as connection:connection.execute(schema)
            observed=json.loads(independent_apply(core,cli,artifact,destination))
            assert observed==[{'CAST(id AS TEXT)':'9007199254740993','length(body)':2400000,'hex(payload)':'0080FF'}],observed
            proof['checks'].append('native-'+kind+'-stream-download-sha-independent-public-C-apply-and-CLI-exact-int64-text-blob-comparison')
            rejected=client.post(url,json={'action':'sqlite_capture_export_status','request':{'database_target_id':other,'job_id':reviewed['job_id']}})
            assert rejected.status_code!=200 or not rejected.get_json().get('success')
        assert execute('SELECT count(*) FROM "native\n雪"')[0]==[[1]]
        with sqlite3.connect(source) as connection:assert connection.execute('SELECT count(*) FROM "native\n雪"').fetchone()==(0,)
        post('close_session',session_id=session_id)
        assert export('reconcile',job_id=reviewed['job_id'])['state']=='artifact_verified'
        assert export('files',job_id=reviewed['job_id'])['files']
        response=client.post(url,data={'action':'sqlite_capture_export_download','payload':json.dumps(payload)})
        assert response.status_code==200 and hashlib.sha256(response.data).hexdigest()==row['sha256']
        assert export('start',**request)['state']=='artifact_verified'
        proof['checks'].append('target-scope-refusal-pending-SQL-not-committed-no-replay-and-offline-reconcile-download-after-query-close')
        def inspect_reference(reference,selected):
            def inspection(operation,**fields):return post('sqlite_changeset_inspect_'+operation,request={'database_target_id':target,**fields})
            review=inspection('review',input=reference,options=selected)
            value=inspection('start',job_id=review['job_id'],review_digest=review['review_digest'],confirmed=True);deadline=time.monotonic()+30
            while value['state'] in {'active','dispatching','publishing','cancel_requested'}:
                assert time.monotonic()<deadline;time.sleep(.02);value=inspection('status',job_id=review['job_id'])
            assert value['state']=='completed' and value['native_returned'],value
            assert inspection('start',job_id=review['job_id'],review_digest=review['review_digest'],confirmed=True)['state']=='completed'
            return value,inspection('result',job_id=review['job_id'])
        reference={'database_target_id':target,'kind':'capture','job_id':exports['changeset'],'path':'capture.changeset'}
        inspected,metadata=inspect_reference(reference,{'mode':'page','preview_bytes':4,'timeout_seconds':60})
        row=metadata['inspection']['rows'][0]
        assert row['new_values'][0]=={'native_type':'integer','data':'9007199254740993'} and row['primary_key']==[1,0,0]
        assert metadata['inspection']['column_name_scope'] and metadata['apply_input'] is False
        extracted,metadata=inspect_reference(reference,{'mode':'extract','record_number':row['record_number'],'column_index':1,'side':'new','timeout_seconds':60})
        response=client.post(url,data={'action':'sqlite_changeset_inspect_download','payload':json.dumps({'database_target_id':target,'job_id':extracted['job_id'],'path':'value.bin'})})
        assert response.status_code==200 and response.data==('native 😀'*300000).encode('utf8') and response.headers.get('X-Content-Type-Options')=='nosniff'
        proof['native_inspection']={'page_job_id':inspected['job_id'],'extracted_job_id':extracted['job_id'],'extracted_bytes':len(response.data),'extracted_sha256':hashlib.sha256(response.data).hexdigest()}
        proof['checks'].append('authenticated-native-typed-file-inspection-and-complete-text-byte-extraction-with-exact-independent-bytes-and-no-repeat')
        def apply_action(operation,**fields):
            return post('sqlite_changeset_'+operation,database_target_id=other,request={'database_target_id':other,**fields})
        for inverted in (False,True):
            apply_review=apply_action('review',source_database_target_id=target,source_job_id=exports['changeset'],path='capture.changeset',
                options={'invert':inverted,'include_rebase':True,'timeout_seconds':60})
            apply_request={'job_id':apply_review['job_id'],'review_digest':apply_review['review_digest'],'confirmed':True}
            applied=apply_action('start',**apply_request);deadline=time.monotonic()+30
            while applied['state'] in {'active','dispatching','committing','cancel_requested'}:
                assert time.monotonic()<deadline;time.sleep(.02);applied=apply_action('status',job_id=apply_review['job_id'])
            assert applied['state']=='completed' and applied['native_returned'] and applied['commit_returned'],applied
            assert apply_action('start',**apply_request)['state']=='completed'
            with sqlite3.connect(output/'another.sqlite') as connection:
                rows=connection.execute('SELECT CAST(id AS TEXT),length(body),hex(payload) FROM "native\n雪"').fetchall()
            assert rows==([] if inverted else [('9007199254740993',2400000,'0080FF')]),rows
            assert apply_action('reconcile',job_id=apply_review['job_id'])['output_artifact_verified']
            output_files=apply_action('files',job_id=apply_review['job_id'])['files']
            for output_row in output_files:
                response=client.post(url,data={'action':'sqlite_changeset_download','payload':json.dumps({'database_target_id':other,'job_id':apply_review['job_id'],'path':output_row['path']})})
                assert response.status_code==200 and hashlib.sha256(response.data).hexdigest()==output_row['sha256']
        proof['checks'].append('authenticated-native-apply-and-inversion-to-separate-registration-independent-row-comparison-rebase-output-and-no-replay')
        original_conflict_bytes=b'\x80\x00'*100000
        with sqlite3.connect(output/'another.sqlite') as connection:connection.execute('INSERT INTO "native'+chr(10)+'雪" VALUES(?,?,?)',(9007199254740993,'target conflict',original_conflict_bytes))
        interactive=apply_action('review',source_database_target_id=target,source_job_id=exports['changeset'],path='capture.changeset',options={'interactive_conflicts':True,'timeout_seconds':60})
        live=apply_action('start',job_id=interactive['job_id'],review_digest=interactive['review_digest'],confirmed=True);deadline=time.monotonic()+30
        while not (live.get('pending_conflict') or {}).get('waiting'):
            assert time.monotonic()<deadline and live['state'] in {'active','dispatching'},live
            time.sleep(.02);live=apply_action('status',job_id=interactive['job_id'])
        challenge=live['pending_conflict']['challenge'];event=apply_action('conflict',job_id=interactive['job_id'],challenge=challenge)['event']
        assert event['kind_name']=='conflict' and event['current_values'][1]['preview_text']=='target conflict'
        delivered=client.post(url,data={'action':'sqlite_changeset_conflict_value_download','payload':json.dumps({'database_target_id':other,'job_id':interactive['job_id'],'challenge':challenge,'side':'current','column_index':2})})
        assert delivered.status_code==200 and delivered.data==original_conflict_bytes
        refused=client.post(url,json={'action':'sqlite_changeset_decide','request':{'database_target_id':other,'job_id':interactive['job_id'],'response':{'challenge':'0'*32,'choice':'replace','remember_kind':False}}})
        assert refused.status_code!=200 or not refused.get_json().get('success')
        apply_action('decide',job_id=interactive['job_id'],response={'challenge':challenge,'choice':'replace','remember_kind':False})
        deadline=time.monotonic()+30
        while live['state'] in {'active','dispatching','committing','cancel_requested'}:
            assert time.monotonic()<deadline;time.sleep(.02);live=apply_action('status',job_id=interactive['job_id'])
        assert live['state']=='completed' and live['commit_returned'] and live['last_native_conflict_decision']['choice']==1,live
        with sqlite3.connect(output/'another.sqlite') as connection:
            assert connection.execute('SELECT CAST(id AS TEXT),length(body),hex(payload) FROM "native'+chr(10)+'雪"').fetchall()==[('9007199254740993',2400000,'0080FF')]
            connection.execute('DELETE FROM "native'+chr(10)+'雪"')
        proof['checks'].append('authenticated-live-native-conflict-byte-download-stale-challenge-refusal-scoped-response-native-consumption-and-separate-commit')
        apply_review=apply_action('review',source_database_target_id=target,source_job_id=exports['changeset'],path='capture.changeset',options={})
        with sqlite3.connect(output/'another.sqlite') as connection:connection.execute('CREATE TABLE stale_review(id INTEGER PRIMARY KEY)')
        response=client.post(url,json={'action':'sqlite_changeset_start','request':{'database_target_id':other,'job_id':apply_review['job_id'],
            'review_digest':apply_review['review_digest'],'confirmed':True}})
        assert response.status_code!=200 or not response.get_json().get('success')
        proof['checks'].append('native-apply-start-refuses-changed-destination-schema-review')
        external={kind:output/('external.'+kind) for kind in ('changeset','patchset')}
        producer_sql="CREATE TABLE external_file(id INTEGER PRIMARY KEY,body TEXT,payload BLOB);\n.session open main producer\n.session producer attach external_file\nINSERT INTO external_file VALUES(9007199254740997,printf('%.*c',2500000,'Z')||'雪😀',x'00FF80');\n"
        producer_sql+=''.join('.session producer '+kind+' '+json.dumps(str(path),ensure_ascii=False)+'\n' for kind,path in external.items())
        subprocess.run([str(cli),':memory:'],input=producer_sql,encoding='utf8',check=True,capture_output=True)
        external_uploads={}
        for kind,path in external.items():
            data=path.read_bytes();checksum=hashlib.sha256(data).hexdigest()
            uploaded=apply_action('upload_create',options={'filename':'external native 雪.'+kind,'length':str(len(data)),'expected_sha256':checksum,'kind':'auto','timeout_seconds':60})
            external_uploads[kind]=uploaded['job_id']
            for offset in range(0,len(data),262144):
                block=data[offset:offset+262144];packet={'offset':str(offset),'data_base64':base64.b64encode(block).decode('ascii'),'sha256':hashlib.sha256(block).hexdigest()}
                received=apply_action('upload_chunk',job_id=uploaded['job_id'],chunk=packet)
                assert received['uploaded_bytes']==str(offset+len(block)) and received['chunk_sha256']==packet['sha256']
                if offset==0:assert apply_action('upload_chunk',job_id=uploaded['job_id'],chunk=packet)==received
            validated=apply_action('upload_seal',job_id=uploaded['job_id']);deadline=time.monotonic()+30
            while validated['state'] in {'active','dispatching','publishing','cancel_requested'}:
                assert time.monotonic()<deadline;time.sleep(.02);validated=apply_action('upload_status',job_id=uploaded['job_id'])
            assert validated['state']=='completed' and validated['result']['artifact']['native_kind']==kind,validated
            delivered=client.post(url,data={'action':'sqlite_changeset_upload_download','payload':json.dumps({'database_target_id':other,'job_id':uploaded['job_id'],'path':'uploaded.native'})})
            assert delivered.status_code==200 and delivered.data==data
            source_fields={'source_kind':'upload','source_database_target_id':other,'source_job_id':uploaded['job_id'],'path':'uploaded.native'}
            for inverse in ((False,True) if kind=='changeset' else (False,)):
                reviewed_upload=apply_action('review',**source_fields,options={'invert':inverse,'timeout_seconds':60})
                applied_upload=apply_action('start',job_id=reviewed_upload['job_id'],review_digest=reviewed_upload['review_digest'],confirmed=True);deadline=time.monotonic()+30
                while applied_upload['state'] in {'active','dispatching','committing','cancel_requested'}:
                    assert time.monotonic()<deadline;time.sleep(.02);applied_upload=apply_action('status',job_id=reviewed_upload['job_id'])
                assert applied_upload['state']=='completed' and applied_upload['commit_returned'],applied_upload
                observed=json.loads(subprocess.check_output([str(cli),'-json',str(output/'another.sqlite'),
                    'SELECT CAST(id AS TEXT) AS id,length(body) AS characters,substr(body,-2) AS suffix,hex(payload) AS payload FROM external_file'],text=True) or '[]')
                assert observed==([] if inverse else [{'id':'9007199254740997','characters':2500002,'suffix':'雪😀','payload':'00FF80'}]),observed
        with sqlite3.connect(output/'another.sqlite') as connection:connection.execute('DELETE FROM external_file')
        proof['checks'].append('independent-native-CLI-produced-changeset-patchset-bounded-upload-retry-whole-SHA-native-detection-download-reviewed-apply-and-exact-CLI-comparison')
        def apply_reference(reference,selected=None):
            review=apply_action('review',source_kind=reference['kind'],source_database_target_id=reference['database_target_id'],source_job_id=reference['job_id'],path=reference['path'],options=selected or {})
            value=apply_action('start',job_id=review['job_id'],review_digest=review['review_digest'],confirmed=True);deadline=time.monotonic()+30
            while value['state'] in {'active','dispatching','committing','cancel_requested'}:
                assert time.monotonic()<deadline;time.sleep(.02);value=apply_action('status',job_id=review['job_id'])
            assert value['state']=='completed' and value['commit_returned'],value
            return value
        def transform_reference(inputs,selected):
            review=apply_action('transform_review',inputs=inputs,options=selected)
            value=apply_action('transform_start',job_id=review['job_id'],review_digest=review['review_digest'],confirmed=True);deadline=time.monotonic()+30
            while value['state'] in {'active','dispatching','publishing','cancel_requested'}:
                assert time.monotonic()<deadline;time.sleep(.02);value=apply_action('transform_status',job_id=review['job_id'])
            assert value['state']=='completed' and value['result']['artifact']['native_iterator_complete'],value
            assert apply_action('transform_start',job_id=review['job_id'],review_digest=review['review_digest'],confirmed=True)['state']=='completed'
            delivered=client.post(url,data={'action':'sqlite_changeset_transform_download','payload':json.dumps({'database_target_id':other,'job_id':review['job_id'],'path':'transformed.native'})})
            assert delivered.status_code==200
            reference={'database_target_id':other,'kind':'transform','job_id':review['job_id'],'path':'transformed.native'}
            return reference,value,delivered.data
        uploaded_reference={'database_target_id':other,'kind':'upload','job_id':external_uploads['changeset'],'path':'uploaded.native'}
        inverted,invert_receipt,_bytes=transform_reference([uploaded_reference],{'operation':'invert','timeout_seconds':60})
        apply_reference(uploaded_reference);apply_reference(inverted)
        with sqlite3.connect(output/'another.sqlite') as connection:assert connection.execute('SELECT count(*) FROM external_file').fetchone()==(0,)
        _concatenated,concat_receipt,concatenated_bytes=transform_reference([uploaded_reference,inverted],{'operation':'concat','timeout_seconds':60})
        assert concat_receipt['result']['artifact']['native_record_count']=='0'
        merged,merge_receipt,_bytes=transform_reference([uploaded_reference],{'operation':'merge','schema_database':'main','timeout_seconds':60})
        apply_reference(merged);apply_reference(inverted)
        with sqlite3.connect(output/'another.sqlite') as connection:assert connection.execute('SELECT count(*) FROM external_file').fetchone()==(0,)
        retained_id=post('open_session',database_target_id=other,language_profile='sqlite-sql')['session_id']
        def retained_sql(sql):return execute(sql,retained_session_id=retained_id,database_target_id=other)[0]
        retained_sql('BEGIN');retained_sql('SAVEPOINT owner_pending')
        retained_schema="external_file(id INTEGER PRIMARY KEY,body TEXT,payload BLOB,extra TEXT DEFAULT 'transient 😀')"
        retained_sql('CREATE TEMP TABLE '+retained_schema);retained_sql("INSERT INTO temp.external_file(id) VALUES(99)")
        schemas=apply_action('transform_schemas',session_id=retained_id)
        assert schemas['transaction_open'] and 'temp' in {row['name'] for row in schemas['schemas']}
        refused=client.post(url,json={'action':'sqlite_changeset_transform_schemas','request':{'database_target_id':target,'session_id':retained_id}})
        assert refused.status_code!=200 or not refused.get_json().get('success')
        _transient,transient_receipt,transient_bytes=transform_reference([uploaded_reference],
            {'operation':'merge','schema_database':'temp','schema_session_id':retained_id,'timeout_seconds':60})
        assert transient_receipt['source_transaction_open'] and transient_receipt['source_transaction_open_after']
        transient_file=output/'retained-temp.changeset';transient_file.write_bytes(transient_bytes);independent=output/'retained-independent.sqlite'
        with sqlite3.connect(independent) as connection:connection.execute('CREATE TABLE '+retained_schema)
        observed=json.loads(independent_apply(core,cli,transient_file,independent,
            'SELECT CAST(id AS TEXT) AS id,length(body) AS characters,hex(payload) AS payload,extra FROM external_file'))
        assert observed==[{'id':'9007199254740997','characters':2500002,'payload':'00FF80','extra':'transient 😀'}],observed
        assert retained_sql('SELECT id,extra FROM temp.external_file')==[[99,'transient 😀']]
        existing=post('sqlite_native_sessions',database_target_id=other,session_id=retained_id,request={'operation':'open','database':'main'})['capture']['capture_id']
        post('sqlite_native_sessions',database_target_id=other,session_id=retained_id,request={'operation':'attach','capture_id':existing,'table_name':'native\n雪'})
        retained_sql('DELETE FROM "native\n雪"');retained_sql('INSERT INTO "native\n雪" VALUES(777,\'pending difference 雪😀\',x\'0080FF\')')
        comparisons={}
        for kind in ('changeset','patchset'):
            comparison=apply_action('diff_review',session_id=retained_id,options={'database':'main','source_database':'baseline 雪','table_name':'native\n雪','kind':kind,'timeout_seconds':60})
            value=apply_action('diff_start',job_id=comparison['job_id'],review_digest=comparison['review_digest'],confirmed=True);deadline=time.monotonic()+30
            while value['state'] in {'active','dispatching','publishing','cancel_requested'}:
                assert time.monotonic()<deadline;time.sleep(.02);value=apply_action('diff_status',job_id=comparison['job_id'])
            assert value['state']=='completed' and value['diff_returned'] and value['export_returned'] and value['capture_closed'],value
            assert value['source_transaction_open'] and value['source_transaction_open_after']
            assert apply_action('diff_start',job_id=comparison['job_id'],review_digest=comparison['review_digest'],confirmed=True)['state']=='completed'
            delivered=client.post(url,data={'action':'sqlite_changeset_diff_download','payload':json.dumps({'database_target_id':other,'job_id':comparison['job_id'],'path':'difference.native'})})
            assert delivered.status_code==200
            path=output/('managed-diff.'+kind);path.write_bytes(delivered.data);independent_diff=output/('independent-managed-diff-'+kind+'.sqlite')
            with sqlite3.connect(independent_diff) as connection:
                connection.execute(schema);connection.execute('INSERT INTO "native\n雪" VALUES(44,?,?)',('baseline',b'\x01'))
            observed=json.loads(independent_apply(core,cli,path,independent_diff,'SELECT id,body,hex(payload) AS payload FROM "native\n雪"'))
            assert observed==[{'id':777,'body':'pending difference 雪😀','payload':'0080FF'}],observed
            comparisons[kind]={'database_target_id':other,'kind':'diff','job_id':comparison['job_id'],'path':'difference.native'}
            _inspection,result=inspect_reference(comparisons[kind],{'mode':'page','offset':'0','limit':10,'preview_bytes':32,'max_json_bytes':1048576,'timeout_seconds':60})
            assert len(result['inspection']['rows'])==2
        assert post('sqlite_native_sessions',database_target_id=other,session_id=retained_id,request={'operation':'status','capture_id':existing})['capture']['capture_id']==existing
        assert retained_sql('SELECT id,body,hex(payload) FROM "native\n雪"')==[[777,'pending difference 雪😀','0080FF']]
        post('sqlite_native_sessions',database_target_id=other,session_id=retained_id,request={'operation':'close','capture_id':existing,'confirmed':True})
        stale=apply_action('transform_review',inputs=[uploaded_reference],options={'operation':'merge','schema_database':'temp','schema_session_id':retained_id})
        retained_sql('ALTER TABLE temp.external_file ADD COLUMN changed TEXT')
        refused=client.post(url,json={'action':'sqlite_changeset_transform_start','request':{'database_target_id':other,'job_id':stale['job_id'],'review_digest':stale['review_digest'],'confirmed':True}})
        assert refused.status_code!=200 or not refused.get_json().get('success') or refused.get_json()['data']['state']=='reviewed'
        retained_sql('ROLLBACK TO owner_pending');retained_sql('RELEASE owner_pending');retained_sql('ROLLBACK')
        post('close_session',database_target_id=other,session_id=retained_id)
        refused=client.post(url,json={'action':'sqlite_changeset_transform_schemas','request':{'database_target_id':other,'session_id':retained_id}})
        assert refused.status_code<500 and (refused.status_code!=200 or not refused.get_json().get('success'))
        assert apply_action('transform_reconcile',job_id=transient_receipt['job_id'])['state']=='artifact_verified'
        for reference in comparisons.values():assert apply_action('diff_reconcile',job_id=reference['job_id'])['state']=='artifact_verified'
        with sqlite3.connect(output/'another.sqlite') as connection:
            saved=connection.execute('SELECT * FROM "native\n雪"').fetchall()
            connection.execute('DELETE FROM "native\n雪"');connection.execute('INSERT INTO "native\n雪" VALUES(44,?,?)',('baseline',b'\x01'))
        applied_difference=apply_reference(comparisons['changeset'])
        assert applied_difference['source']['source_kind']=='diff'
        with sqlite3.connect(output/'another.sqlite') as connection:
            assert connection.execute('SELECT id,body,hex(payload) FROM "native\n雪"').fetchall()==[(777,'pending difference 雪😀','0080FF')]
            connection.execute('DELETE FROM "native\n雪"');connection.executemany('INSERT INTO "native\n雪" VALUES(?,?,?)',saved)
        proof['checks'].append('authenticated-retained-uncommitted-temp-schema-native-defaults-independent-apply-exact-bytes-stale-target-and-schema-refusal-savepoint-preservation-and-offline-reconcile')
        proof['checks'].append('authenticated-managed-native-diff-changeset-and-patchset-private-capture-closure-pending-SQL-preservation-typed-inspection-independent-apply-offline-reconcile-and-reviewed-managed-apply')
        local_file=output/'local-branch.changeset'
        local_sql="CREATE TABLE external_file(id INTEGER PRIMARY KEY,body TEXT,payload BLOB);\n.session open main local\n.session local attach external_file\nINSERT INTO external_file VALUES(9007199254740997,'local branch',x'01');\n.session local changeset "+json.dumps(str(local_file),ensure_ascii=False)+'\n'
        subprocess.run([str(cli),':memory:'],input=local_sql,encoding='utf8',check=True,capture_output=True)
        local_data=local_file.read_bytes();local_upload=apply_action('upload_create',options={'filename':local_file.name,'length':str(len(local_data)),'timeout_seconds':60})
        apply_action('upload_chunk',job_id=local_upload['job_id'],chunk={'offset':'0','data_base64':base64.b64encode(local_data).decode('ascii'),'sha256':hashlib.sha256(local_data).hexdigest()})
        local_value=apply_action('upload_seal',job_id=local_upload['job_id']);deadline=time.monotonic()+30
        while local_value['state'] in {'active','dispatching','publishing','cancel_requested'}:
            assert time.monotonic()<deadline;time.sleep(.02);local_value=apply_action('upload_status',job_id=local_upload['job_id'])
        assert local_value['state']=='completed',local_value
        local_reference={'database_target_id':other,'kind':'upload','job_id':local_upload['job_id'],'path':'uploaded.native'}
        apply_reference(local_reference)
        remote_apply=apply_reference(uploaded_reference,{'include_rebase':True,'conflicts':{'data':'abort','not_found':'abort','conflict':'replace','constraint':'abort','foreign_key':'abort'},'timeout_seconds':60})
        assert remote_apply['native_apply']['conflicts']['conflict']=='1'
        rebase_reference={'database_target_id':other,'kind':'rebase','job_id':remote_apply['job_id'],'path':'native.rebase'}
        _rebased,rebase_receipt,rebased_bytes=transform_reference([local_reference,rebase_reference],{'operation':'rebase','timeout_seconds':60})
        rebase_response=client.post(url,data={'action':'sqlite_changeset_download','payload':json.dumps({'database_target_id':other,'job_id':remote_apply['job_id'],'path':'native.rebase'})})
        assert rebase_response.status_code==200
        assert rebased_bytes==independent_rebase(core,local_data,rebase_response.data) and rebase_receipt['result']['artifact']['native_record_count']=='0'
        with sqlite3.connect(output/'another.sqlite') as connection:connection.execute('DELETE FROM external_file')
        proof['checks'].extend(['authenticated-native-invert-concat-and-readonly-schema-merge-with-reviewed-transformed-apply-and-no-repeat',
            'acknowledged-native-conflict-replacement-rebase-buffer-and-streaming-local-rebase-agree-with-native-empty-result'])
        if browser_binary:
            proof['browser']=browser(app,output,server_id,browser_binary,driver_binary,core,cli)
            proof['checks'].append('browser-native-capture-attach-sensitive-source-export-confirmation-and-streamed-three-megabyte-download')
            proof['checks'].append('browser-external-native-CLI-file-bounded-upload-validation-reviewed-apply-and-independent-exact-row-check')
        proof.update(complete=True,native_sqlite_version=sqlite3.sqlite_version,native_source_id=sqlite3.connect(':memory:').execute('SELECT sqlite_source_id()').fetchone()[0])
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def browser(app,output,server_id,binary,driver_binary,core,cli):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import StaleElementReferenceException,ElementClickInterceptedException,ElementNotInteractableException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,wait_for_tree_item,named_tree_item,invoke_context_action
    from cdeadmin_sqlite_query_ui_gate import _run_query
    downloads=output/'browser-downloads';downloads.mkdir(mode=0o700)
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1200'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'))
        options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        options.add_experimental_option('prefs',{'download.default_directory':str(downloads),'download.prompt_for_download':False})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.execute_cdp_cmd('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(downloads)})
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/');wait=WebDriverWait(driver,90,ignored_exceptions=(StaleElementReferenceException,))
        ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'SQLite')
        def owned(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,server_id)),None)
        label=wait.until(owned).text
        def database_child(browser):
            mounted=named_tree_item(browser,'native.sqlite',('Connectors','SQLite',label))
            if mounted is not None:return mounted
            # Verification can replace the registration row after a click.
            # Expand only a currently collapsed row and wait for the real child.
            expand(wait,label,('Connectors','SQLite'));return False
        database=wait.until(database_child)
        invoke_context_action(wait,driver,database,('Database workspace','Open SQLite SQL editor...'),handle_endpoint_prompt=False)
        def expose(node):
            ancestors=driver.execute_script('let n=arguments[0].parentElement,a=[];while(n){if(n.tagName==="DETAILS" && !n.open && n.querySelector(":scope > summary")!==arguments[0])a.unshift(n);n=n.parentElement;}return a;',node)
            for ancestor in ancestors:
                summary=ancestor.find_element(By.XPATH,'./summary');driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',summary)
                if summary.is_displayed():summary.click()
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node)
        def click(label,tag='button'):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,tag):
                    if node.get_attribute('textContent').strip()!=label or not node.is_enabled():continue
                    try:
                        expose(node)
                        if node.is_displayed():node.click();return True
                    except (StaleElementReferenceException,ElementClickInterceptedException,ElementNotInteractableException):continue
                return False
            wait.until(attempt)
        def engine_options():
            def attempt(browser):
                for node in browser.find_elements(By.XPATH,'//*[@role="tab" and normalize-space()="Engine options"]'):
                    try:
                        expose(node)
                        if node.is_displayed() and node.is_enabled():node.click();return True
                    except (StaleElementReferenceException,ElementClickInterceptedException,ElementNotInteractableException):continue
                return False
            wait.until(attempt)
        engine_options();click('SQLite native captures','summary');click('Inspect native captures');click('Open native capture')
        click('Automatic native capture table filter','summary')
        pattern_label=driver.find_element(By.XPATH,'//label[normalize-space()="Native capture GLOB pattern"]')
        field=driver.find_element(By.ID,pattern_label.get_attribute('for'));expose(field);field.clear();field.send_keys('native*')
        click('Set automatic native table filter');click('Track all future native table names')
        click('Compare an attached source into this capture','summary')
        source_label=driver.find_element(By.XPATH,'//label[normalize-space()="Native diff source database"]')
        field=driver.find_element(By.ID,source_label.get_attribute('for'));expose(field);field.click()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.is_displayed() and node.text.strip()=='baseline 雪'),None)).click()
        table_label=driver.find_element(By.XPATH,'//label[normalize-space()="Exact native diff table"]');field=driver.find_element(By.ID,table_label.get_attribute('for'));expose(field);field.send_keys('native'+chr(10)+'雪')
        click('Add native table difference to capture')
        def difference_ready(browser):
            for node in browser.find_elements(By.CSS_SELECTOR,'[aria-label="Native SQLite capture observations"]'):
                expose(node)
                if node.is_displayed():
                    value=json.loads(node.get_attribute('textContent'))
                    if not value['empty'] and value['tables']==['native'+chr(10)+'雪']:return value
            return False
        compared=wait.until(difference_ready)
        with sqlite3.connect(output/'baseline.sqlite') as independent:assert independent.execute('SELECT id,body FROM "native'+chr(10)+'雪"').fetchall()==[(44,'baseline')]
        def discard_capture(browser):
            for label in browser.find_elements(By.XPATH,'//label[contains(.,"Discard this capture and any unexported changes")]'):
                expose(label)
                if label.is_displayed() and label.find_element(By.TAG_NAME,'input').is_enabled():return label
            return False
        wait.until(discard_capture).click();click('Close native capture');click('Open native capture')
        wait.until(lambda browser:browser.find_elements(By.XPATH,'//button[normalize-space()="Refresh native capture"]'))
        table_label=driver.find_element(By.XPATH,'//label[normalize-space()="Exact native capture table"]')
        field=driver.find_element(By.ID,table_label.get_attribute('for'));expose(field);field.send_keys('native\n雪');click('Attach native capture tables')
        sensitive=driver.find_element(By.XPATH,'//label[contains(.,"Omit this sensitive source from SQL history")]//input');expose(sensitive)
        if not sensitive.is_selected():sensitive.click()
        _run_query(driver,wait,'INSERT INTO "native\n雪" VALUES(2,printf(\'%.*c\',3000000,\'x\'),x\'01\') RETURNING id','2','SQLite',output)
        engine_options();click('SQLite capture exports and receipts','summary');click('Review native capture export')
        confirmation=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[contains(.,"Confirm the reviewed native capture export")]//input'));expose(confirmation);confirmation.click()
        click('Start reviewed capture export')
        wait.until(lambda browser:any('Capture export ' in node.get_attribute('textContent') and ': completed.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        click('Load verified capture files');click('Download capture.changeset')
        artifact=downloads/'capture.changeset';wait.until(lambda _browser:artifact.is_file() and not list(downloads.glob('*.crdownload')))
        assert artifact.stat().st_size>3000000
        click('Native capture export receipt','summary')
        receipt=json.loads(driver.find_element(By.CSS_SELECTOR,'[aria-label="SQLite capture export receipt"]').get_attribute('textContent'))
        assert receipt['result']['artifact']['native_iterator_complete'] and receipt['native_returned']
        checksum=hashlib.sha256(artifact.read_bytes()).hexdigest()
        destination=wait_for_tree_item(wait,'another.sqlite',('Connectors','SQLite',label))
        invoke_context_action(wait,driver,destination,('Database workspace','Open SQLite SQL editor...'),handle_endpoint_prompt=False)
        engine_options();click('SQLite changeset application','summary');click('Inspect native apply sources')
        source_label=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[normalize-space()="Native source database"]'))
        source_field=driver.find_element(By.ID,source_label.get_attribute('for'));expose(source_field);source_field.click()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]')
            if node.is_displayed() and node.text.strip()=='native.sqlite'),None)).click()
        click('Load verified source exports')
        click('SQLite typed changeset inspection','summary');click('Inspect typed native file support');click('Inspect selected native records')
        click('Select native record 1')
        position_label=driver.find_element(By.XPATH,'//label[normalize-space()="Native column position (first is 1)"]')
        field=driver.find_element(By.ID,position_label.get_attribute('for'));expose(field);field.click();field.send_keys(Keys.CONTROL,'a');field.send_keys('2')
        wait.until(lambda _browser:field.get_attribute('value')=='2')
        click('Extract complete native TEXT or BLOB value')
        wait.until(lambda browser:any('Native inspection ' in node.get_attribute('textContent') and ': completed.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        click('Load native inspection files');click('Download inspection value.bin')
        extracted_value=downloads/'value.bin';wait.until(lambda _browser:extracted_value.is_file() and not list(downloads.glob('*.crdownload')))
        assert extracted_value.stat().st_size==3000000 and hashlib.sha256(extracted_value.read_bytes()).hexdigest()==hashlib.sha256(b'x'*3000000).hexdigest()
        click('Review native changeset application')
        confirmation=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[contains(.,"Confirm native changes and commit to this destination")]//input'));expose(confirmation);confirmation.click()
        click('Apply reviewed native changeset')
        wait.until(lambda browser:any('Native apply ' in node.get_attribute('textContent') and ': completed.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        click('Native SQLite apply receipt','summary')
        applied=json.loads(driver.find_element(By.CSS_SELECTOR,'[aria-label="Native SQLite apply receipt"]').get_attribute('textContent'))
        assert applied['commit_returned'] and applied['native_returned'] and applied['source']['source_job_id']==receipt['job_id']
        with sqlite3.connect(output/'another.sqlite') as independent:
            assert independent.execute('SELECT id,length(body),hex(payload) FROM "native\n雪"').fetchall()==[(2,3000000,'01')]
        click('Load native apply output files');click('Download apply archive.json')
        metadata=downloads/'archive.json';wait.until(lambda _browser:metadata.is_file() and not list(downloads.glob('*.crdownload')))
        assert json.loads(metadata.read_text())['source']['input_file']['sha256']==checksum
        conflict_original=b'\x80\x00'*100000
        with sqlite3.connect(output/'another.sqlite') as connection:connection.execute('UPDATE "native'+chr(10)+'雪" SET body=?,payload=? WHERE id=2',('target live',conflict_original))
        def interactive_label(browser):
            for label in browser.find_elements(By.XPATH,'//label[contains(.,"Decide conflicts while the native apply waits")]'):
                expose(label)
                if label.is_displayed() and label.find_element(By.TAG_NAME,'input').is_enabled():return label
            return False
        wait.until(interactive_label).click();click('Review native changeset application')
        confirmation=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[contains(.,"Confirm native changes and commit to this destination")]//input'));expose(confirmation);confirmation.click()
        click('Apply reviewed native changeset');click('Download current column 3 bytes')
        conflict_value=downloads/'conflict-current-3.bin';wait.until(lambda _browser:conflict_value.is_file() and not list(downloads.glob('*.crdownload')))
        assert conflict_value.read_bytes()==conflict_original
        click('Use native replace for this conflict')
        wait.until(lambda browser:any('Native apply ' in node.get_attribute('textContent') and ': completed.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        with sqlite3.connect(output/'another.sqlite') as connection:assert connection.execute('SELECT length(body),hex(payload) FROM "native'+chr(10)+'雪" WHERE id=2').fetchone()==(3000000,'01')
        wait.until(interactive_label).click()
        click('External SQLite changeset files','summary');click('Inspect native upload support')
        def upload_input(browser):
            for node in browser.find_elements(By.CSS_SELECTOR,'input[aria-label="External native SQLite file"]'):
                try:
                    expose(node)
                    if node.is_enabled() and node.is_displayed():return node
                except (StaleElementReferenceException,ElementNotInteractableException):continue
            return False
        upload=wait.until(upload_input);upload.send_keys(str(output/'external.changeset'));click('Upload and validate native file')
        wait.until(lambda browser:any('Native file intake ' in node.get_attribute('textContent') and ': completed.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        click('Use validated native file for apply');click('Review native changeset application')
        confirmation=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[contains(.,"Confirm native changes and commit to this destination")]//input'));expose(confirmation);confirmation.click()
        click('Apply reviewed native changeset')
        wait.until(lambda browser:any('Native apply ' in node.get_attribute('textContent') and ': completed.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        uploaded_apply=json.loads(driver.find_element(By.CSS_SELECTOR,'[aria-label="Native SQLite apply receipt"]').get_attribute('textContent'))
        assert uploaded_apply['commit_returned'] and uploaded_apply['source']['source_kind']=='upload'
        assert uploaded_apply['source']['input_file']['sha256']==hashlib.sha256((output/'external.changeset').read_bytes()).hexdigest()
        with sqlite3.connect(output/'another.sqlite') as independent:
            assert independent.execute('SELECT CAST(id AS TEXT),length(body),substr(body,-2),hex(payload) FROM external_file').fetchall()==[('9007199254740997',2500002,'雪😀','00FF80')]
        click('SQLite native file transformations','summary');click('Inspect native transform support')
        source_kind_label=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[normalize-space()="Transform source kind"]'))
        source_kind_field=driver.find_element(By.ID,source_kind_label.get_attribute('for'));expose(source_kind_field);source_kind_field.click()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.is_displayed() and node.text.strip()=='Uploaded native file'),None)).click()
        click('Load native transform inputs');click('Add ordered native input');click('Review native file transformation')
        transform_confirmation=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[contains(.,"Confirm new native transformed artifact")]//input'));expose(transform_confirmation);transform_confirmation.click()
        click('Start reviewed native transformation')
        wait.until(lambda browser:any('Native transform ' in node.get_attribute('textContent') and ': completed.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        click('Use transformed native file for apply');click('Review native changeset application')
        confirmation=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[contains(.,"Confirm native changes and commit to this destination")]//input'));expose(confirmation);confirmation.click()
        click('Apply reviewed native changeset')
        wait.until(lambda browser:any('Native apply ' in node.get_attribute('textContent') and ': completed.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        transformed_apply=json.loads(driver.find_element(By.CSS_SELECTOR,'[aria-label="Native SQLite apply receipt"]').get_attribute('textContent'))
        assert transformed_apply['commit_returned'] and transformed_apply['source']['source_kind']=='transform'
        with sqlite3.connect(output/'another.sqlite') as independent:assert independent.execute('SELECT count(*) FROM external_file').fetchone()==(0,)
        def visible_retained_sensitive(browser):
            for label in browser.find_elements(By.XPATH,'//label[contains(.,"Omit this sensitive source from SQL history")]'):
                expose(label)
                if label.is_displayed() and label.find_element(By.TAG_NAME,'input').is_enabled():return label
            return False
        sensitive=wait.until(visible_retained_sensitive)
        if not sensitive.find_element(By.TAG_NAME,'input').is_selected():sensitive.click()
        _run_query(driver,wait,'SELECT 9173 AS retained_schema_probe','9173','SQLite',output)
        engine_options()
        operation_label=driver.find_element(By.XPATH,'//label[normalize-space()="Native file transformation"]')
        field=driver.find_element(By.ID,operation_label.get_attribute('for'));expose(field);field.click()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.is_displayed() and node.text.strip()=='Merge native changegroup'),None)).click()
        def retained_label(browser):
            for label in browser.find_elements(By.XPATH,'//label[contains(.,"Use current query session schema for merge")]'):
                expose(label)
                if label.is_displayed() and label.find_element(By.TAG_NAME,'input').is_enabled():return label
            return False
        wait.until(retained_label).click();click('Inspect retained merge schemas')
        schema_label=driver.find_element(By.XPATH,'//label[normalize-space()="Native merge schema basis"]')
        field=driver.find_element(By.ID,schema_label.get_attribute('for'));expose(field);field.click()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.is_displayed() and node.text.strip().startswith('main —')),None)).click()
        click('Review native file transformation')
        transform_confirmation=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[contains(.,"Confirm new native transformed artifact")]//input'));expose(transform_confirmation);transform_confirmation.click()
        click('Start reviewed native transformation')
        wait.until(lambda browser:any('Native transform ' in node.get_attribute('textContent') and ': completed.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        retained_merge=json.loads(driver.find_element(By.CSS_SELECTOR,'[aria-label="Native SQLite transform receipt"]').get_attribute('textContent'))
        assert retained_merge['options']['schema_session_id']==retained_merge['source']['schema_binding']['studio_session_id']
        assert retained_merge['native_returned'] and retained_merge['source_transaction_open_after'] is False
        click('Load native transformed files');click('Download transform transformed.native')
        merged_file=downloads/'transformed.native';wait.until(lambda _browser:merged_file.is_file() and not list(downloads.glob('*.crdownload')))
        independent_path=output/'browser-retained-independent.sqlite'
        with sqlite3.connect(independent_path) as independent:independent.execute('CREATE TABLE external_file(id INTEGER PRIMARY KEY,body TEXT,payload BLOB)')
        observed=json.loads(independent_apply(core,cli,merged_file,independent_path,
            'SELECT CAST(id AS TEXT) AS id,length(body) AS characters,hex(payload) AS payload FROM external_file'))
        assert observed==[{'id':'9007199254740997','characters':2500002,'payload':'00FF80'}],observed
        click('SQLite managed table differences','summary');click('Inspect retained table comparison support');click('Load native comparison tables')
        table_label=driver.find_element(By.XPATH,'//label[normalize-space()="Exact native comparison table"]')
        field=driver.find_element(By.ID,table_label.get_attribute('for'));expose(field);field.click()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]')
            if node.is_displayed() and node.get_attribute('textContent').strip()=='native\n雪'),None)).click()
        click('Review native table comparison')
        confirmation=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[contains(.,"Confirm disposable native table comparison")]//input'));expose(confirmation);confirmation.click()
        click('Start reviewed native table comparison')
        wait.until(lambda browser:any('Native table comparison ' in node.get_attribute('textContent') and ': completed.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        comparison=json.loads(driver.find_element(By.CSS_SELECTOR,'[aria-label="Native SQLite table comparison receipt"]').get_attribute('textContent'))
        assert comparison['diff_returned'] and comparison['export_returned'] and comparison['capture_closed']
        click('Load native comparison files');click('Download comparison difference.native')
        difference=downloads/'difference.native';wait.until(lambda _browser:difference.is_file() and not list(downloads.glob('*.crdownload')))
        independent_diff=output/'browser-managed-diff-independent.sqlite'
        with sqlite3.connect(independent_diff) as independent:
            independent.execute('CREATE TABLE "native\n雪"(id INTEGER PRIMARY KEY,body TEXT,payload BLOB)')
            independent.execute('INSERT INTO "native\n雪" VALUES(44,?,?)',('baseline',b'\x01'))
        independent_apply(core,cli,difference,independent_diff)
        with sqlite3.connect(independent_diff) as independent,sqlite3.connect(output/'another.sqlite') as expected:
            assert independent.execute('SELECT * FROM "native\n雪" ORDER BY id').fetchall()==expected.execute('SELECT * FROM "native\n雪" ORDER BY id').fetchall()
        native_preupdate=False
        if app.config.get('CDEADMIN_SQLITE_PREUPDATE_LIBRARY'):
            engine_options();click('SQLite before-change diagnostics','summary');click('Inspect native preupdate support');click('Start native preupdate observations')
            wait.until(lambda browser:any('Preupdate hook: enabled.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
            def visible_sensitive(browser):
                for label in browser.find_elements(By.XPATH,'//label[contains(.,"Omit this sensitive source from SQL history")]'):
                    expose(label)
                    if label.is_displayed() and label.find_element(By.TAG_NAME,'input').is_enabled():return label
                return False
            sensitive=wait.until(visible_sensitive)
            if not sensitive.find_element(By.TAG_NAME,'input').is_selected():sensitive.click()
            statement='INSERT INTO '+chr(34)+'native'+chr(10)+'雪'+chr(34)+" VALUES(73,'before change',x'00FF') RETURNING id"
            _run_query(driver,wait,statement,'73','SQLite',output)
            engine_options();click('Load first native preupdate events');click('Inspect native event 1','summary')
            def visible_event(browser):
                for node in browser.find_elements(By.CSS_SELECTOR,'[aria-label="Native SQLite before-change events"] pre'):
                    expose(node)
                    if node.is_displayed():return node
                return False
            event=wait.until(visible_event)
            event=json.loads(event.get_attribute('textContent'));assert event['operation']=='insert' and event['new_values'][0]=={'native_type':'integer','data':'73'}
            click('Stop native preupdate observations')
            wait.until(lambda browser:any('Preupdate hook: stopped.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
            def discard_label(browser):
                for label in browser.find_elements(By.XPATH,'//label[contains(.,"Discard retained before-change observations")]'):
                    expose(label)
                    if label.is_displayed() and label.find_element(By.TAG_NAME,'input').is_enabled():return label
                return False
            wait.until(discard_label).click();click('Clear native preupdate observations');native_preupdate=True
        native_arrays=False
        if app.config.get('CDEADMIN_SQLITE_ARRAY_LIBRARY'):
            engine_options();click('SQLite native arrays','summary');click('Inspect native arrays');click('Create native array')
            click('Use native array in editor')
            def sensitive_label(browser):
                for label in browser.find_elements(By.XPATH,'//label[contains(.,"Omit this sensitive source from SQL history")]'):
                    expose(label)
                    if label.is_displayed() and label.find_element(By.TAG_NAME,'input').is_enabled():return label
                return False
            sensitive=wait.until(sensitive_label)
            if not sensitive.find_element(By.TAG_NAME,'input').is_selected():sensitive.click()
            _run_query(driver,wait,'SELECT value, typeof(value) AS storage_class FROM carray(:items)','9007199254740993','SQLite',output)
            engine_options()
            def close_confirmation(browser):
                for node in browser.find_elements(By.XPATH,'//label[contains(.,"Release this array and its parameter bindings")]'):
                    expose(node)
                    if node.is_displayed() and node.find_element(By.TAG_NAME,'input').is_enabled():return node
                return False
            wait.until(close_confirmation).click();click('Close native array');native_arrays=True
        driver.save_screenshot(str(output/'native-sqlite-capture.png'))
        errors=[row for row in driver.get_log('browser') if row.get('level')=='SEVERE'];(output/'browser-console.json').write_text(json.dumps(errors,indent=2));assert not errors
        return {'complete':True,'console_errors':0,'job_id':receipt['job_id'],'downloaded_bytes':artifact.stat().st_size,'downloaded_sha256':checksum,
            'native_apply_job_id':applied['job_id'],'native_apply_commit_returned':True,'independent_destination_rows_verified':True,'apply_metadata_download_verified':True,
            'external_upload_apply_job_id':uploaded_apply['job_id'],'external_upload_bytes':(output/'external.changeset').stat().st_size,
            'native_managed_diff_verified':True,'native_retained_schema_merge_verified':True,'native_live_conflict_decisions_verified':True,'native_typed_inspection_and_value_download_verified':True,'native_capture_filter_and_diff_verified':True,'native_preupdate_verified':native_preupdate,'native_arrays_verified':native_arrays,'external_native_upload_and_apply_verified':True,'native_transform_and_apply_verified':True,'transformed_apply_job_id':transformed_apply['job_id']}
    except BaseException:
        if driver is not None:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--library',type=Path,required=True);parser.add_argument('--sqlite-core',type=Path,required=True);parser.add_argument('--sqlite-cli',type=Path,required=True)
    parser.add_argument('--preupdate-library',type=Path);parser.add_argument('--array-library',type=Path);parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();qualify(args.evidence,args.library,args.sqlite_core,args.sqlite_cli,browser_binary=args.browser_binary,driver_binary=args.driver_binary,array_library=args.array_library,preupdate_library=args.preupdate_library)
