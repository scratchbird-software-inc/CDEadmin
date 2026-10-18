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


def independent_apply(core,cli,changeset,database):
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
    sql='SELECT CAST(id AS TEXT),length(body),hex(payload) FROM "native\n雪"'
    return subprocess.check_output([str(cli),'-json',str(database),sql],text=True)


def qualify(output,library,core,cli,*,browser_binary=None,driver_binary=None):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    proof={'complete':False,'history_testing':'not run','checks':[],'source_sha256':{}}
    for path in [Path(__file__),ROOT/'tools/native/sqlite_sessions/api.c',
                 *list((ROOT/'web/pgadmin/cdeadmin/providers/sqlite').glob('session*.py')),
                 *list((ROOT/'web/pgadmin/cdeadmin/workspace').glob('sqlite_capture*.py')),
                 *list((ROOT/'web/pgadmin/cdeadmin/workspace').glob('sqlite_changeset*.py')),
                 *list((ROOT/'web/pgadmin/cdeadmin/workspace').glob('sqlite_upload*.py')),
                 ROOT/'web/pgadmin/cdeadmin/providers/sqlite/changeset_apply.py',
                 ROOT/'web/pgadmin/static/js/Dialogs/SQLiteChangesetApply.jsx',ROOT/'web/pgadmin/static/js/Dialogs/SQLiteNativeUpload.jsx',
                 ROOT/'web/pgadmin/cdeadmin/data_studio/studio.py',ROOT/'web/pgadmin/cdeadmin/workspace/service.py',
                 ROOT/'web/pgadmin/browser/server_groups/servers/__init__.py']:
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
    source=output/'native.sqlite';schema='CREATE TABLE "native\n雪"(id INTEGER PRIMARY KEY,body TEXT,payload BLOB)'
    assert sqlite3.sqlite_version=='3.53.0'
    with sqlite3.connect(source) as connection:
        connection.execute('PRAGMA journal_mode=WAL');connection.execute(schema)
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
            server._cde_endpoint_route_configuration={'database':str(source),'filesystem_root':str(output)}
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
        def execute(source,parameters=None):
            started=post('execute',session_id=session_id,source=source,parameters=parameters or {},history_sensitive=True)
            deadline=time.monotonic()+30;rows=[]
            while time.monotonic()<deadline:
                occurrence=post('poll',occurrence_id=started['occurrence_id'])['occurrence']
                payload=(occurrence.get('result') or {}).get('extensions',{}).get('sqlite',{}).get('payload',{})
                rows.extend(payload.get('rows') or [])
                if occurrence['operation']['terminal']:
                    assert not payload.get('error'),payload
                    return rows,payload
                time.sleep(.02)
            raise TimeoutError('Native SQLite query worker')
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
        for kind,path in external.items():
            data=path.read_bytes();checksum=hashlib.sha256(data).hexdigest()
            uploaded=apply_action('upload_create',options={'filename':'external native 雪.'+kind,'length':str(len(data)),'expected_sha256':checksum,'kind':'auto','timeout_seconds':60})
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
        if browser_binary:
            proof['browser']=browser(app,output,server_id,browser_binary,driver_binary)
            proof['checks'].append('browser-native-capture-attach-sensitive-source-export-confirmation-and-streamed-three-megabyte-download')
            proof['checks'].append('browser-external-native-CLI-file-bounded-upload-validation-reviewed-apply-and-independent-exact-row-check')
        proof.update(complete=True,native_sqlite_version=sqlite3.sqlite_version,native_source_id=sqlite3.connect(':memory:').execute('SELECT sqlite_source_id()').fetchone()[0])
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def browser(app,output,server_id,binary,driver_binary):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import StaleElementReferenceException,ElementClickInterceptedException,ElementNotInteractableException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,wait_for_tree_item,invoke_context_action
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
        label=wait.until(owned).text;expand(wait,label,('Connectors','SQLite'))
        database=wait_for_tree_item(wait,'native.sqlite',('Connectors','SQLite',label))
        invoke_context_action(wait,driver,database,('Database workspace','Open SQLite SQL editor...'),handle_endpoint_prompt=False)
        def expose(node):
            ancestors=driver.execute_script('let n=arguments[0].parentElement,a=[];while(n){if(n.tagName==="DETAILS" && !n.open)a.unshift(n);n=n.parentElement;}return a;',node)
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
        click('Load verified source exports');click('Review native changeset application')
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
        driver.save_screenshot(str(output/'native-sqlite-capture.png'))
        errors=[row for row in driver.get_log('browser') if row.get('level')=='SEVERE'];(output/'browser-console.json').write_text(json.dumps(errors,indent=2));assert not errors
        return {'complete':True,'console_errors':0,'job_id':receipt['job_id'],'downloaded_bytes':artifact.stat().st_size,'downloaded_sha256':checksum,
            'native_apply_job_id':applied['job_id'],'native_apply_commit_returned':True,'independent_destination_rows_verified':True,'apply_metadata_download_verified':True,
            'external_upload_apply_job_id':uploaded_apply['job_id'],'external_upload_bytes':(output/'external.changeset').stat().st_size,
            'external_native_upload_and_apply_verified':True}
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
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();qualify(args.evidence,args.library,args.sqlite_core,args.sqlite_cli,browser_binary=args.browser_binary,driver_binary=args.driver_binary)
