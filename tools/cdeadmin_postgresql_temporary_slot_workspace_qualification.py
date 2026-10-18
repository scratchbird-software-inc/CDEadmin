#!/usr/bin/env python3
"""Owned PostgreSQL18.3 temporary-slot authenticated workflow and browser evidence."""
import argparse
import builtins
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,*,browser_binary=None,driver_binary=None):
    root=ROOT;out=Path(output).resolve()
    if out==ROOT or ROOT in out.parents:raise ValueError('Evidence belongs outside source')
    out.mkdir(mode=0o700,parents=True,exist_ok=False);builtins.SERVER_MODE=None
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False;config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    for name,value in {'DATA_DIR':'app','SQLITE_PATH':'app/application.db','SESSION_DB_PATH':'app/sessions','STORAGE_DIR':'app/storage','LOG_FILE':'app/application.log','AZURE_CREDENTIAL_CACHE_DIR':'app/azure','CDEADMIN_OPERATION_STORE_PATH':'app/operations.json'}.items():setattr(config,name,str(out/value))
    import psycopg
    from postgresql_qualification_support import server
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.workspace import service_for_app
    from flask import url_for
    app=create_app('ScratchRobin-native-temporary-http');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY='';app.run_before_app_start();client=app.test_client();jobs=None;proof={'complete':False,'history_testing':'not run','full_product_complete':False,'source_sha256':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [Path(__file__),ROOT/'web/pgadmin/cdeadmin/providers/postgresql/temporary_slots.py',ROOT/'web/pgadmin/cdeadmin/providers/postgresql/large_object_files.py',*list((ROOT/'web/pgadmin/cdeadmin/workspace').glob('postgresql_temporary_slot*.py')),ROOT/'web/pgadmin/cdeadmin/workspace/postgresql_slot_changes.py',ROOT/'web/pgadmin/cdeadmin/workspace/service.py',ROOT/'web/pgadmin/browser/server_groups/servers/__init__.py',ROOT/'web/pgadmin/static/js/Dialogs/PostgresqlTemporarySlots.jsx',ROOT/'web/pgadmin/static/js/Dialogs/PostgresqlContinuity.jsx',ROOT/'web/pgadmin/static/js/Dialogs/PostgresqlLogicalStream.jsx',ROOT/'web/pgadmin/cdeadmin/workspace/postgresql_logical_stream.py',ROOT/'web/pgadmin/cdeadmin/workspace/postgresql_continuity_service.py',ROOT/'web/pgadmin/cdeadmin/workspace/postgresql_continuity_jobs.py',ROOT/'web/pgadmin/cdeadmin/providers/postgresql/continuity.py']}}
    try:
     with server(out/'fixture',server_options=('-c','wal_level=logical','-c','wal_sender_timeout=5s')) as (route,password,fixture):
      args={'host':route['host'],'port':route['port'],'user':route['user'],'dbname':route['database'],'password':password,'autocommit':True}
      with psycopg.connect(**args) as observer:
       from psycopg.types.string import ByteaLoader
       observer.adapters.register_loader(17,ByteaLoader)
       target='postgresql-database:'+str(observer.execute("SELECT oid FROM pg_database WHERE datname=current_database()").fetchone()[0])
       with app.test_request_context('/'):
        user=User.query.first();group=ServerGroup.query.filter_by(user_id=user.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility['postgresql'].set(True,user_id=user.id)
        registered=Server(user_id=user.id,servergroup_id=group.id,name='Owned native temporary slots',host=route['host'],port=route['port'],username=route['user'],maintenance_db=route['database'],connection_params={'sslmode':'disable'},save_password=0)
        db.session.add(registered);db.session.commit();uid=user.id;endpoint=registered.endpoint_profile.id;server_id=registered.id
        connect=url_for('NODE-server.connect_id',gid=group.id,sid=registered.id);url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=registered.id)
       with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
       assert client.post(connect,json={'password':password}).get_json()['success']
       def http(action,**fields):
        response=client.post(url,json={'action':'postgresql_temporary_slots_'+action,'request':{'database_target_id':target,**fields}});value=response.get_json()
        if response.status_code!=200 or not value.get('success'):
         (out/'http-failure.json').write_text(json.dumps(value,indent=2).replace(password,'<redacted>')+'\n');raise AssertionError((action,response.status_code))
        return value['data']
       resource=http('review',options={'max_lifetime_seconds':120});rid=resource['job_id']
       http('start',job_id=rid,review_digest=resource['review_digest'],confirmed=True)
       def wait_resource(predicate):
        deadline=time.monotonic()+20
        while True:
         value=http('status',job_id=rid)
         if predicate(value):return value
         assert time.monotonic()<deadline,value;time.sleep(.03)
       opened=wait_resource(lambda r:r.get('ready'))
       def wait_child(identity,states):
        deadline=time.monotonic()+20
        while True:
         child=http('command_status',resource_id=rid,job_id=identity);parent=http('status',job_id=rid)
         if child['state'] in states and not parent.get('pending_command'):return child
         assert time.monotonic()<deadline,child;time.sleep(.03)
       review=http('command_review',resource_id=rid,operation='physical_create',options={'slot':'sr_http_temporary'})
       review=wait_child(review['job_id'],{'reviewed'})
       refused=client.post(url,json={'action':'postgresql_temporary_slots_command_start','request':{'database_target_id':target,'resource_id':rid,'job_id':review['job_id'],'review_digest':review['review_digest'],'confirmed':False}})
       assert refused.status_code<500 and (refused.status_code!=200 or not refused.get_json().get('success'))
       start={'resource_id':rid,'job_id':review['job_id'],'review_digest':review['review_digest'],'confirmed':True}
       http('command_start',**start);done=wait_child(review['job_id'],{'completed'})
       assert done['native_command_acknowledged'];assert http('command_start',**start)['state']=='completed'
       assert observer.execute("SELECT temporary,active_pid::text FROM pg_replication_slots WHERE slot_name='sr_http_temporary'").fetchone()==(True,opened['backend_pid'])
       page=http('inventory',resource_id=rid,offset=0,limit=1);page=wait_child(page['job_id'],{'completed'})
       assert page['result']['total']==1 and page['result']['slots'][0]['slot_name']=='sr_http_temporary'
       def run_command(operation,**options):
        review=http('command_review',resource_id=rid,operation=operation,options=options)
        review=wait_child(review['job_id'],{'reviewed'})
        admitted={'resource_id':rid,'job_id':review['job_id'],'review_digest':review['review_digest'],'confirmed':True}
        http('command_start',**admitted);done=wait_child(review['job_id'],{'completed'})
        assert http('command_start',**admitted)['state']=='completed'
        return done
       observer.execute('CREATE TABLE sr_http_data(id bigint PRIMARY KEY,body text,payload bytea)')
       observer.execute('CREATE PUBLICATION sr_http_publication FOR TABLE sr_http_data')
       for suffix,plugin in [('text','test_decoding'),('binary','pgoutput')]:
        observer.execute('SELECT * FROM pg_create_logical_replication_slot(%s,%s)',('sr_http_reference_'+suffix,plugin))
        run_command('logical_create',slot='sr_http_'+suffix,plugin=plugin)
       observer.execute('INSERT INTO sr_http_data VALUES(%s,%s,%s)',(9007199254740993,'native 😀 雪',b'\x00\x80\xff'))
       saved_capture=None
       for mode,pairs in [('text',[{'name':'include-xids','value':'0'},{'name':'skip-empty-xacts','value':'1'}]),('binary',[{'name':'proto_version','value':'4'},{'name':'publication_names','value':'sr_http_publication'},{'name':'binary','value':'true'}])]:
        flattened=[part for pair in pairs for part in (pair['name'],pair['value'])]
        function='pg_logical_slot_peek_binary_changes' if mode=='binary' else 'pg_logical_slot_peek_changes'
        data="encode(data,'base64')" if mode=='binary' else 'data'
        expected=observer.execute('SELECT lsn::text,xid::text,'+data+' FROM '+function+'(%s,NULL,NULL,VARIADIC %s::text[])',('sr_http_reference_'+mode,flattened)).fetchall()
        assert expected
        for operation in ('peek_'+mode,'get_'+mode,'get_'+mode):
         done=run_command(operation,slot='sr_http_'+mode,upto_nchanges=None,plugin_options=pairs)
         request={'database_target_id':target,'resource_id':rid,'job_id':done['job_id']}
         response=client.post(url,data={'action':'postgresql_temporary_slots_change_download','payload':json.dumps(request)})
         assert response.status_code==200 and response.headers['X-Export-Completeness']=='verified'
         raw=response.get_data();response.close()
         assert hashlib.sha256(raw).hexdigest()==done['change_artifact']['sha256']
         assert [(row['lsn'],row['xid'],row['data']) for row in map(json.loads,raw.splitlines())]==expected
         page=http('change_preview',resource_id=rid,job_id=done['job_id'],offset='0',limit=1)
         assert len(page['rows'])==min(1,len(expected))
         if operation.startswith('get_'):expected=[]
         saved_capture=(done,request,raw)
        observer.execute('SELECT pg_drop_replication_slot(%s)',('sr_http_reference_'+mode,))
       # Keep one nonempty artifact for download after backend release below.
       observer.execute("INSERT INTO sr_http_data VALUES(2,'offline artifact',NULL)")
       done=run_command('get_text',slot='sr_http_text',upto_nchanges=None,plugin_options=[{'name':'include-xids','value':'0'},{'name':'skip-empty-xacts','value':'1'}])
       saved_capture=(done,{'database_target_id':target,'resource_id':rid,'job_id':done['job_id']})
       other='postgresql-database:1' if target!='postgresql-database:1' else 'postgresql-database:2'
       refused=client.post(url,json={'action':'postgresql_temporary_slots_status','request':{'database_target_id':other,'job_id':rid}})
       assert refused.status_code<500 and (refused.status_code!=200 or not refused.get_json().get('success'))
       http('release',job_id=rid,confirmation=rid);closed=wait_resource(lambda r:r['state']=='closed' and r.get('worker_io_closed'))
       assert closed['native_owner_connection_close_returned'] and closed['remote_cleanup_inferred'] is False
       deadline=time.monotonic()+10
       while True:
        observed=http('reconcile',job_id=rid)
        if observed['backend_cleanup_observation']['temporary_slot_cleanup_observed']:break
        assert time.monotonic()<deadline;time.sleep(.05)
       assert int(observer.execute("SELECT count(*) FROM pg_replication_slots WHERE slot_name='sr_http_temporary'").fetchone()[0])==0
       done,request=saved_capture
       response=client.post(url,data={'action':'postgresql_temporary_slots_change_download','payload':json.dumps(request)})
       assert response.status_code==200 and response.get_data();response.close()
       http('change_reconcile',resource_id=rid,job_id=done['job_id'])
       bad=client.post(url,json={'action':'postgresql_temporary_slots_change_remove','request':{**request,'confirmation':'wrong'}})
       assert bad.status_code<500 and (bad.status_code!=200 or not bad.get_json().get('success'))
       removed=http('change_remove',resource_id=rid,job_id=done['job_id'],confirmation=done['job_id'])
       assert removed['artifact_removed'] and http('change_remove',resource_id=rid,job_id=done['job_id'],confirmation=done['job_id'])['artifact_removed']
       response=client.post(url,data={'action':'postgresql_temporary_slots_change_download','payload':json.dumps(request)})
       assert response.status_code==400;response.close()
       refused=client.post(url,json={'action':'postgresql_temporary_slots_change_reconcile','request':request})
       assert refused.status_code<500 and (refused.status_code!=200 or not refused.get_json().get('success'))
       def continuity(action,**fields):
        response=client.post(url,json={'action':'postgresql_continuity_'+action,'request':fields});value=response.get_json()
        assert response.status_code==200 and value.get('success'),(action,response.status_code,value)
        return value['data']
       observer.execute("SELECT * FROM pg_create_logical_replication_slot('sr_http_stream','test_decoding')")
       observer.execute("INSERT INTO sr_http_data VALUES(10,'HTTP logical receiver 😀',NULL)")
       end=observer.execute('SELECT pg_current_wal_insert_lsn()::text').fetchone()[0]
       expected=b''.join(bytes(row[0])+b'\n' for row in observer.execute("SELECT data FROM pg_logical_slot_peek_binary_changes('sr_http_stream',NULL,NULL,'include-xids','0','skip-empty-xacts','1')").fetchall())
       logical=continuity('review',operation='logical_stream_capture',database_target_id=target,options={'slot':'sr_http_stream','end_lsn':end,'status_interval_seconds':1,'timeout_seconds':30,'plugin_options':[{'name':'include-xids','value':'0'},{'name':'skip-empty-xacts','value':'1'}]})
       admission={'job_id':logical['job_id'],'review_digest':logical['review_digest'],'confirmed':True}
       continuity('start',**admission);deadline=time.monotonic()+40
       while True:
        logical=continuity('status',job_id=logical['job_id'])
        if logical['state']=='captured' and (logical.get('logical_stream_artifact') or {}).get('state')=='sealed':break
        assert time.monotonic()<deadline,logical;time.sleep(.03)
       assert logical['native_receiver_returned'] and logical['worker_io_closed']
       response=client.post(url,data={'action':'postgresql_continuity_logical_stream_download','payload':json.dumps({'job_id':logical['job_id']})})
       assert response.status_code==200 and response.get_data()==expected and response.headers['X-Transaction-Completeness']=='not-inferred';response.close()
       assert continuity('start',**admission)['logical_stream_artifact']['sha256']==hashlib.sha256(expected).hexdigest()
       assert continuity('logical_stream_reconcile',job_id=logical['job_id'])['state']=='captured'
       page=continuity('logical_stream_preview',job_id=logical['job_id'],offset='0',limit=17)
       import base64
       assert base64.b64decode(page['data_base64'])==expected[:17]
       response=client.post(url+'?database_target_id='+other,data={'action':'postgresql_continuity_logical_stream_download','payload':json.dumps({'job_id':logical['job_id']})})
       assert response.status_code==400;response.close()
       deadline=time.monotonic()+10
       while observer.execute("SELECT active FROM pg_replication_slots WHERE slot_name='sr_http_stream'").fetchone()[0]:assert time.monotonic()<deadline;time.sleep(.03)
       observer.execute("SELECT pg_drop_replication_slot('sr_http_stream')")
       proof['authenticated_native_logical_stream_capture_and_download']=True
       proof.update(native_logical_text_and_binary_independently_compared=True,offline_artifact_download_and_confirmed_removal=True,duplicate_native_get_not_replayed=True)
       proof.update(complete=not bool(browser_binary),authenticated_native_resource_and_command_workflow=True,confirmation_and_database_scope_refusals=True,native_inventory_paging=True,independent_native_temporary_slot_verified=True,separate_local_close_and_backend_cleanup=True,original_command_outcomes_inferred=observed['backend_cleanup_observation']['original_command_outcomes_inferred'])
       if browser_binary:proof['browser']=browser(app,out,server_id,password,observer,browser_binary,driver_binary)
       proof['complete']=True
       proof['full_product_complete']=False
    finally:
     for manager in getattr(service_for_app(app),'postgresql_temporary_slot_resources',{}).values():manager.close()
     (out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def browser(app,output,server_id,password,observer,binary,driver_binary):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import StaleElementReferenceException,ElementClickInterceptedException,ElementNotInteractableException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1200','--user-data-dir='+str(output/'browser-profile')):options.add_argument(flag)
        options.add_experimental_option('prefs',{'download.default_directory':str(output/'downloads'),'download.prompt_for_download':False});options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary) if driver_binary else Service())
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/');wait=WebDriverWait(driver,90,ignored_exceptions=(StaleElementReferenceException,))
        ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'PostgreSQL')
        def owned(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,server_id)),None)
        node=wait.until(owned)
        driver.execute_script('const t=window.pgAdmin.Browser.tree;const item=t.itemFrom(arguments[0].closest(".file-entry"));const n=window.pgAdmin.Browser.Nodes.server;n.callbacks.open_postgresql_continuity.call(n,{item});',node)
        def expose(node):
            ancestors=driver.execute_script('let n=arguments[0].parentElement,a=[];while(n){if(n.tagName==="DETAILS" && !n.open && n.querySelector(":scope > summary")!==arguments[0])a.unshift(n);n=n.parentElement;}return a;',node)
            for ancestor in ancestors:
                summary=ancestor.find_element(By.XPATH,'./summary');driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',summary)
                if summary.is_displayed():summary.click()
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node)
        def authenticate(browser):
            for field in browser.find_elements(By.CSS_SELECTOR,'input[aria-label="Password"]'):
                if not field.is_displayed():continue
                if field.is_enabled():
                    if field.get_attribute('value')!=password:field.clear();field.send_keys(password)
                    button=next((node for node in browser.find_elements(By.TAG_NAME,'button') if node.is_displayed() and node.is_enabled() and node.text.strip()=='OK'),None)
                    if button is not None:button.click()
                return True
            return False
        def click(text,tag='button'):
            def attempt(browser):
                if authenticate(browser):return False
                for node in browser.find_elements(By.TAG_NAME,tag):
                    if node.get_attribute('textContent').strip()!=text or not node.is_enabled():continue
                    try:
                        expose(node)
                        if node.is_displayed():node.click();return True
                    except (StaleElementReferenceException,ElementClickInterceptedException,ElementNotInteractableException):continue
                return False
            wait.until(attempt)
        def field(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,'label'):
                    if node.get_attribute('textContent').strip()!=label:continue
                    try:
                        control=browser.find_element(By.ID,node.get_attribute('for'));expose(control)
                        if control.is_displayed() and control.is_enabled():return control
                    except (StaleElementReferenceException,ElementNotInteractableException):continue
                return False
            return wait.until(attempt)
        def checked(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,'label'):
                    if node.get_attribute('textContent').strip()!=label:continue
                    expose(node)
                    if node.is_displayed() and node.find_element(By.TAG_NAME,'input').is_enabled():return node
                return False
            wait.until(attempt).click()
        def receipt(label,predicate):
            def attempt(browser):
                for node in browser.find_elements(By.CSS_SELECTOR,'[aria-label="'+label+'"]'):
                    expose(node)
                    if not node.is_displayed():continue
                    value=json.loads(node.get_attribute('textContent'))
                    if predicate(value):return value
                return False
            return wait.until(attempt)
        click('PostgreSQL temporary replication slots','summary');click('Load temporary slot databases')
        authentication_log=driver.get_log('browser')
        (output/'browser-authentication-console.json').write_text(json.dumps(authentication_log,indent=2)+'\n')
        unexpected=[item for item in authentication_log if item.get('level')=='SEVERE' and not (
            item.get('source')=='network' and '/browser/server/connect/' in item.get('message','') and '428 (PRECONDITION REQUIRED)' in item.get('message',''))]
        assert not unexpected,unexpected
        control=field('Temporary slot database');control.click()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.is_displayed() and node.get_attribute('textContent').strip()=='postgres'),None)).click()
        click('Review temporary slot resource');checked('Confirm independent temporary slot resource');click('Open reviewed temporary slot resource')
        resource=receipt('Native temporary slot resource receipt',lambda r:r.get('ready') and r['state']=='active')
        control=field('Exact temporary slot name');control.send_keys('sr_browser_temporary')
        click('Review temporary slot command');checked('Confirm native temporary slot command');click('Run reviewed temporary slot command')
        command=receipt('Native temporary slot command receipt',lambda r:r['state']=='completed' and r.get('native_command_acknowledged'))
        assert observer.execute("SELECT temporary,active_pid::text FROM pg_replication_slots WHERE slot_name='sr_browser_temporary'").fetchone()==(True,resource['backend_pid'])
        click('Inspect owned temporary slots')
        inventory=receipt('Owned native temporary slots',lambda r:r.get('total')==1)
        assert inventory['slots'][0]['slot_name']=='sr_browser_temporary'
        control=field('Temporary slot operation');control.click()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.is_displayed() and node.get_attribute('textContent').strip()=='Create temporary logical slot'),None)).click()
        from selenium.webdriver.common.keys import Keys
        def replace_field(label,value):
            control=field(label);control.send_keys(Keys.CONTROL,'a');control.send_keys(value)
        replace_field('Exact temporary slot name','sr_browser_logical');replace_field('Temporary slot output plugin','test_decoding')
        click('Review temporary slot command');checked('Confirm native temporary slot command');click('Run reviewed temporary slot command')
        created=receipt('Native temporary slot command receipt',lambda r:r['state']=='completed' and r['options']['operation']=='logical_create')
        observer.execute('INSERT INTO sr_http_data VALUES(%s,%s,NULL)',(3,'browser native 😀'))
        control=field('Temporary slot operation');control.click()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.is_displayed() and node.get_attribute('textContent').strip()=='Consume temporary logical text'),None)).click()
        click('Add ordered temporary plugin option');replace_field('Temporary plugin option 1 name','include-xids');replace_field('Temporary plugin option 1 value','0')
        click('Review temporary slot command');checked('Confirm native temporary slot command');click('Run reviewed temporary slot command')
        logical=receipt('Native temporary slot command receipt',lambda r:r['state']=='completed' and r['options']['operation']=='get_text' and (r.get('change_artifact') or {}).get('state')=='verified')
        click('Preview temporary logical records')
        preview=receipt('Temporary logical output preview',lambda r:any('browser native' in row.get('data','') for row in r.get('rows',[])))
        assert logical['native_sql_acknowledged'] and preview['native_sql_acknowledged']
        click('Download temporary logical capture')
        def downloaded(browser):
            paths=list((output/'downloads').glob('slot-changes*.jsonl'))
            return paths[0] if paths and not list((output/'downloads').glob('*.crdownload')) else False
        downloaded=wait.until(downloaded);assert hashlib.sha256(downloaded.read_bytes()).hexdigest()==logical['change_artifact']['sha256']
        checked('Remove this temporary logical capture; retain receipt');click('Remove temporary logical capture')
        receipt('Native temporary slot command receipt',lambda r:r.get('artifact_removed') is True)
        checked('Release this backend and all its temporary slots');click('Release temporary slot resource')
        closed=receipt('Native temporary slot resource receipt',lambda r:r['state']=='closed' and r.get('worker_io_closed'))
        assert closed['native_owner_connection_close_returned'] and closed['remote_cleanup_inferred'] is False
        click('Verify native temporary slot cleanup')
        verified=receipt('Native temporary slot resource receipt',lambda r:(r.get('backend_cleanup_observation') or {}).get('temporary_slot_cleanup_observed'))
        assert verified['backend_cleanup_observation']['original_command_outcomes_inferred'] is False
        assert int(observer.execute("SELECT count(*) FROM pg_replication_slots WHERE slot_name='sr_browser_temporary'").fetchone()[0])==0
        observer.execute("SELECT * FROM pg_create_logical_replication_slot('sr_browser_stream','test_decoding')")
        observer.execute("INSERT INTO sr_http_data VALUES(11,'browser replication stream 😀',NULL)")
        end=observer.execute('SELECT pg_current_wal_insert_lsn()::text').fetchone()[0]
        click('PostgreSQL logical replication streams','summary');click('Load logical stream databases')
        control=field('Logical stream database');control.click()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.is_displayed() and node.get_attribute('textContent').strip()=='postgres'),None)).click()
        replace_field('Logical receiver slot','sr_browser_stream');replace_field('Logical receiver end lsn',end);replace_field('Logical receiver timeout seconds','30');replace_field('Logical receiver status interval seconds','1')
        click('Add ordered logical receiver option');replace_field('Logical receiver option 1 name','include-xids');replace_field('Logical receiver option 1 value','0')
        click('Review logical replication stream');checked('Confirm native logical stream consumption');click('Start reviewed logical stream')
        captured=receipt('Native logical stream receipt',lambda r:r['state']=='captured' and (r.get('logical_stream_artifact') or {}).get('state')=='sealed')
        click('Preview native logical bytes')
        receipt('Native logical byte preview',lambda r:'browser replication stream' in (r.get('utf8_preview') or ''))
        click('Download native logical stream')
        def stream_downloaded(browser):
            paths=list((output/'downloads').glob('postgresql-logical-stream-*.native'))
            return paths[0] if paths and not list((output/'downloads').glob('*.crdownload')) else False
        path=wait.until(stream_downloaded);assert hashlib.sha256(path.read_bytes()).hexdigest()==captured['logical_stream_artifact']['sha256']
        deadline=time.monotonic()+10
        while observer.execute("SELECT active FROM pg_replication_slots WHERE slot_name='sr_browser_stream'").fetchone()[0]:assert time.monotonic()<deadline;time.sleep(.03)
        observer.execute("SELECT pg_drop_replication_slot('sr_browser_stream')")
        console=[item for item in driver.get_log('browser') if item.get('level')=='SEVERE']
        (output/'browser-console.json').write_text(json.dumps(console,indent=2)+'\n');assert not console,console
        return {'complete':True,'resource_id':resource['job_id'],'command_id':command['job_id'],'console_errors':0,
            'native_temporary_slot_lifetime_verified':True,'native_inventory_verified':True,'logical_text_preview_download_and_remove_verified':True,'native_replication_stream_preview_download_verified':True,'independent_backend_cleanup_verified':True}
    except BaseException:
        if driver is not None:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();result=qualify(args.evidence,browser_binary=args.browser_binary,driver_binary=args.driver_binary)
    print(json.dumps({'complete':result['complete'],'browser':result.get('browser'),'history_testing':'not run','full_product_complete':False}))
