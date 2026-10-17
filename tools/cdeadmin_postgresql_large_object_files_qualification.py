"""Owned PostgreSQL 18.3 whole-file HTTP transfers and native failure evidence."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'web'),str(ROOT/'tools'),str(ROOT)]


def qualify(output,*,browser_binary=None,driver_binary=None,browser_only=False):
    if browser_only and not browser_binary:raise ValueError('Browser-only qualification requires a browser binary')
    import config
    import psycopg
    from psycopg import sql,Cursor
    from psycopg.rows import tuple_row
    from psycopg.types.string import ByteaLoader
    from postgresql_qualification_support import server as owned_server
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside the source checkout')
    output.mkdir(parents=True,exist_ok=False)
    proof={'complete':False,'checks':[],'history_testing':'not run','source_sha256':{}}
    for name in ('web/pgadmin/cdeadmin/providers/postgresql/large_object_files.py',
                 'web/pgadmin/cdeadmin/workspace/postgresql_large_object_jobs.py',
                 'web/pgadmin/cdeadmin/workspace/postgresql_large_object_service.py',
                 'web/pgadmin/browser/server_groups/servers/__init__.py',__file__):
        path=ROOT/name if not Path(name).is_absolute() else Path(name)
        proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False;config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    config.DATA_DIR=str(output/'app');config.SQLITE_PATH=str(output/'app/application.db')
    config.SESSION_DB_PATH=str(output/'app/sessions');config.STORAGE_DIR=str(output/'app/storage')
    config.LOG_FILE=str(output/'app/application.log');config.AZURE_CREDENTIAL_CACHE_DIR=str(output/'app/azure')
    config.CDEADMIN_OPERATION_STORE_PATH=str(output/'app/operations.json');config.CDEADMIN_POSTGRESQL_LARGE_OBJECT_ROOT=str(output/'files')
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.workspace import service_for_app
    from flask import url_for
    app=create_app('ScratchRobin-native-large-object-files');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start();client=app.test_client();jobs=None
    try:
        with owned_server(output/'fixture',initdb_options=('--locale=C','--encoding=UTF8')) as (route,password,fixture):
            arguments={'host':route['host'],'port':route['port'],'user':route['user'],'dbname':route['database'],'password':password,**route['connection_params']}
            with psycopg.connect(**arguments,autocommit=True) as observer:
                observer.adapters.register_loader(17,ByteaLoader)
                def query(source,params=()):
                    with Cursor(observer,row_factory=tuple_row) as cursor:
                        cursor.execute(source,params or None)
                        return cursor.fetchall() if cursor.description else []
                database_oid=int(query('SELECT oid FROM pg_database WHERE datname=current_database()')[0][0])
                target='postgresql-database:'+str(database_oid)
                with app.test_request_context('/'):
                    user=User.query.first();group=ServerGroup.query.filter_by(user_id=user.id).order_by(ServerGroup.id).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['postgresql'].set(True,user_id=user.id)
                    registered=Server(user_id=user.id,servergroup_id=group.id,name='Owned PostgreSQL file transfers',host=route['host'],port=route['port'],username=route['user'],maintenance_db=route['database'],connection_params={'sslmode':'disable'},save_password=0)
                    db.session.add(registered);db.session.commit()
                    uid,sid,gid,endpoint=user.id,registered.id,group.id,registered.endpoint_profile.id
                    connect_url=url_for('NODE-server.connect_id',gid=gid,sid=sid)
                    workspace_url=url_for('NODE-server.cde_workspace_id',gid=gid,sid=sid)
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                connected=client.post(connect_url,json={'password':password}).get_json()
                if not connected.get('success'):raise RuntimeError('Owned PostgreSQL HTTP connection failed')
                def http(action,request):
                    response=client.post(workspace_url,json={'action':'postgresql_large_object_'+action,'request':{**request,'database_target_id':target}})
                    value=response.get_json()
                    if response.status_code!=200 or not value.get('success'):
                        (output/'http-failure.json').write_text(json.dumps(value,indent=2)+'\n');raise RuntimeError('Native file HTTP '+action+' failed')
                    return value['data']
                def wait(item,expected):
                    deadline=time.monotonic()+60
                    while item['state'] in {'reviewing','dispatching','active','cancel_requested'}:
                        if time.monotonic()>deadline:raise TimeoutError('Native file transfer deadline')
                        time.sleep(.05);item=http('status',{'job_id':item['job_id']})
                    if item['state']!=expected:
                        (output/'transfer-failure.json').write_text(json.dumps(item,indent=2)+'\n');raise RuntimeError('Native file transfer returned '+item['state'])
                    return item
                data=bytes(range(256))*12345+b'\x00\xffcomplete'
                def upload(data,oid='0'):
                    item=http('create',{'options':{'operation':'import','oid':oid,'length':str(len(data)),'filename':'Native "ü" 😀.bin'}})
                    for offset in range(0,len(data),1048576):
                        part=data[offset:offset+1048576]
                        request={'job_id':item['job_id'],'offset':str(offset),'data_base64':base64.b64encode(part).decode('ascii'),'sha256':hashlib.sha256(part).hexdigest()}
                        first=http('upload',request);assert http('upload',request)==first
                    return wait(http('seal',{'job_id':item['job_id']}),'reviewed')
                def start(item,expected='committed'):
                    request={'job_id':item['job_id'],'review_digest':item['review_digest'],'confirmed':True}
                    result=wait(http('start',request),expected)
                    assert http('start',request)['state']==expected
                    return result
                if not browser_only:
                    imported=start(upload(data));oid=imported['result']['oid']
                    assert imported['result']['native_postimage_verified'] and imported['result']['sha256']==hashlib.sha256(data).hexdigest()
                    assert bytes(query('SELECT lo_get(%s::oid)',(oid,))[0][0])==data
                    proof['checks'].append('authenticated-http-multichunk-import-with-idempotent-upload-and-native-precommit-checksum')
                    exported=start(http('create',{'options':{'operation':'export','oid':oid,'filename':'Complete "ü" 😀.bin'}}))
                    downloaded=client.post(workspace_url,data={'action':'postgresql_large_object_download','payload':json.dumps({'job_id':exported['job_id'],'database_target_id':target})})
                    assert downloaded.status_code==200 and downloaded.data==data
                    assert downloaded.headers['X-Content-SHA256']==hashlib.sha256(data).hexdigest();downloaded.close()
                    proof['checks'].append('native-repeatable-read-whole-file-export-and-authenticated-binary-http-download')
                    jobs=service_for_app(app).postgresql_large_object_jobs
                    from pgadmin.cdeadmin.workspace import postgresql_large_object_jobs as implementation
                    original_read=implementation.read_chunks;changed=[]
                    def concurrently_changed(*args,**kwargs):
                        for part in original_read(*args,**kwargs):
                            yield part
                            if not changed:
                                query('SELECT lo_put(%s::oid,1048576::bigint,%s::bytea)',(oid,b'changed after snapshot'));changed.append(True)
                    implementation.read_chunks=concurrently_changed
                    try:snapshot=start(http('create',{'options':{'operation':'export','oid':oid,'filename':'snapshot.bin'}}))
                    finally:implementation.read_chunks=original_read
                    observed=client.post(workspace_url,data={'action':'postgresql_large_object_download','payload':json.dumps({'job_id':snapshot['job_id'],'database_target_id':target})})
                    assert observed.data==data;observed.close()
                    assert bytes(query('SELECT lo_get(%s::oid,1048576::bigint,22)',(oid,))[0][0])==b'changed after snapshot'
                    query('SELECT lo_put(%s::oid,0::bigint,%s::bytea)',(oid,data))
                    proof['checks'].append('native-repeatable-read-export-preserves-one-snapshot-during-concurrent-large-object-writes')
                    empty=start(upload(b''));assert bytes(query('SELECT lo_get(%s::oid)',(empty['result']['oid'],))[0][0])==b''
                    refused=start(upload(b'unchanged',oid),'failed')
                    assert refused['native_transaction_outcome']=='rolled_back' and bytes(query('SELECT lo_get(%s::oid)',(oid,))[0][0])==data
                    proof['checks'].append('native-empty-file-import-and-existing-oid-refusal-with-confirmed-rollback')
                    original=implementation.import_file
                    def wrong_hash(connection,stream,selected,expected,**kwargs):return original(connection,stream,selected,'0'*64,**kwargs)
                    implementation.import_file=wrong_hash
                    try:failed=start(upload(b'checksum refusal'),'failed')
                    finally:implementation.import_file=original
                    assert failed['native_transaction_outcome']=='rolled_back'
                    assert query('SELECT oid FROM pg_largeobject_metadata WHERE oid=%s::oid',(failed['native_oid'],))==[]
                    proof['checks'].append('native-import-checksum-refusal-removes-uncommitted-object')
                    entered=threading.Event();release=threading.Event()
                    def delayed(*args,**kwargs):entered.set();release.wait(10);return original(*args,**kwargs)
                    implementation.import_file=delayed
                    try:
                        reviewed=upload(data)
                        active=http('start',{'job_id':reviewed['job_id'],'review_digest':reviewed['review_digest'],'confirmed':True})
                        assert entered.wait(5);http('cancel',{'job_id':active['job_id']});release.set();cancelled=wait(http('status',{'job_id':active['job_id']}),'cancelled')
                    finally:release.set();implementation.import_file=original
                    assert cancelled['native_transaction_outcome']=='rolled_back'
                    proof['checks'].append('owned-native-cancellation-rolls-back-the-import-transaction')
                    # A real successful COMMIT with a lost acknowledgement must be
                    # unknown until the native transaction-status function answers.
                    from contextlib import contextmanager
                    original_cursor=implementation.cursor
                    @contextmanager
                    def lose_commit(connection):
                        with original_cursor(connection) as actual:
                            class Proxy:
                                def execute(self,source,*args,**kwargs):
                                    value=actual.execute(source,*args,**kwargs)
                                    if source=='COMMIT':raise OSError('Owned commit acknowledgement fault')
                                    return value
                                def __getattr__(self,key):return getattr(actual,key)
                            yield Proxy()
                    implementation.cursor=lose_commit
                    try:unknown=start(upload(b'unknown commit'),'unknown')
                    finally:implementation.cursor=original_cursor
                    assert unknown['native_transaction_outcome']=='unknown'
                    reconciled=http('reconcile',{'job_id':unknown['job_id']})
                    assert reconciled['state']=='committed' and reconciled['reconciliation']['native_transaction_status']=='committed'
                    assert bytes(query('SELECT lo_get(%s::oid)',(reconciled['result']['oid'],))[0][0])==b'unknown commit'
                    proof['checks'].append('lost-native-commit-reply-remains-unknown-without-replay-and-reconciles-from-native-xid8-status')
                    implementation.cursor=lose_commit
                    try:unknown_export=start(http('create',{'options':{'operation':'export','oid':oid,'filename':'reconciled-export.bin'}}),'unknown')
                    finally:implementation.cursor=original_cursor
                    artifact=http('reconcile',{'job_id':unknown_export['job_id']})
                    assert artifact['state']=='artifact_verified' and artifact['native_transaction_outcome']=='unknown'
                    delivered=client.post(workspace_url,data={'action':'postgresql_large_object_download','payload':json.dumps({'job_id':artifact['job_id'],'database_target_id':target})})
                    assert delivered.data==data;delivered.close()
                    proof['checks'].append('lost-read-only-commit-reply-retains-unknown-native-finality-while-independent-export-artifact-verifies')
                    from pgadmin.cdeadmin.providers.postgresql import large_object_files as native_files
                    role='File reader ü "'+str(time.time_ns())
                    query(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
                    try:
                        selected_source={**imported['source'],'effective_principal':role}
                        with native_files.attach(arguments,selected_source) as limited:
                            with native_files.cursor(limited) as selected:selected.execute('BEGIN READ ONLY')
                            try:native_files.metadata(limited,oid)
                            except psycopg.errors.InsufficientPrivilege:pass
                            else:raise AssertionError('Native large-object SELECT privilege was bypassed')
                            with native_files.cursor(limited) as selected:selected.execute('ROLLBACK')
                        query(sql.SQL('GRANT SELECT ON LARGE OBJECT {} TO {}').format(sql.Literal(int(oid)),sql.Identifier(role)))
                        with native_files.attach(arguments,selected_source) as limited:
                            with native_files.cursor(limited) as selected:selected.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
                            observed=native_files.metadata(limited,oid)
                            checksum=hashlib.sha256()
                            for part in native_files.read_chunks(limited,oid,observed['length']):checksum.update(part)
                            assert checksum.hexdigest()==hashlib.sha256(data).hexdigest()
                            with native_files.cursor(limited) as selected:selected.execute('ROLLBACK')
                    finally:
                        query(sql.SQL('REVOKE ALL ON LARGE OBJECT {} FROM {}').format(sql.Literal(int(oid)),sql.Identifier(role)))
                        query(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
                    proof['checks'].append('separate-native-attachment-preserves-quoted-effective-role-and-enforces-large-object-select-privilege')
                    with app.test_request_context('/'):
                        for owner,ep,dbtarget in ((uid+1,endpoint,target),(uid,endpoint,'other-database')):
                            try:jobs.get(imported['job_id'],owner,ep,dbtarget)
                            except ValueError:pass
                            else:raise AssertionError('Cross-owner or database file receipt was exposed')
                    proof['checks'].append('durable-file-receipts-and-artifacts-are-owner-endpoint-database-bound')
                    removed=http('remove_artifact',{'job_id':exported['job_id'],'confirmation':exported['job_id']})
                    assert removed['artifact_available'] is False and removed['state']=='committed'
                    unavailable=client.post(workspace_url,data={'action':'postgresql_large_object_download','payload':json.dumps({'job_id':exported['job_id'],'database_target_id':target})})
                    assert unavailable.status_code==400
                    assert bytes(query('SELECT lo_get(%s::oid)',(oid,))[0][0])==data
                    proof['checks'].append('confirmed-application-artifact-removal-preserves-durable-receipt-and-native-large-object')
                if browser_binary:
                    proof['browser']=qualify_browser(app,output,password,data,browser_binary,driver_binary)
                    proof['checks'].append('native-browser-database-callback-whole-file-upload-confirmation-export-and-download-byte-verification')
                jobs=service_for_app(app).postgresql_large_object_jobs
                proof.update(complete=True,native_version='18.3',qualification_scope='native-browser-only' if browser_only else 'native-http-and-browser')
                if not browser_only:proof['source']=imported['source']
        assert fixture['owned_server_stopped']
        assert http('list',{})['total']>=(1 if browser_only else 5)
        proof['checks'].append('offline-authenticated-file-receipts-after-owned-source-stopped')
    finally:
        if jobs is not None:jobs.close()
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    assert proof['complete']
    return proof


def qualify_browser(app,output,password,data,binary,driver_binary):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.common.exceptions import StaleElementReferenceException,ElementClickInterceptedException
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,wait_for_tree_item
    http=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    downloads=output/'browser-downloads';downloads.mkdir()
    source=output/'Browser input ü.bin';source.write_bytes(data)
    try:
        opts=webdriver.ChromeOptions();opts.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1600,1000'):opts.add_argument(flag)
        opts.add_argument('--user-data-dir='+str(output/'browser-profile'));opts.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        opts.add_experimental_option('prefs',{'download.default_directory':str(downloads),'download.prompt_for_download':False,'download.directory_upgrade':True})
        driver=webdriver.Chrome(options=opts,service=Service(driver_binary) if driver_binary else Service())
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/');wait=WebDriverWait(driver,60)
        ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'PostgreSQL')
        server=wait_for_tree_item(wait,'localhost',ancestors=('Connectors','PostgreSQL'))
        driver.execute_script('''
          const tree=window.pgAdmin.Browser.tree,item=tree.itemFrom(arguments[0].closest('.file-entry'));
          const node=window.pgAdmin.Browser.Nodes.server;
          if(!tree.itemData(item).connected)node.callbacks.connect_server.call(node,{item});
        ''',server)
        submitted=False
        def connected(browser):
            nonlocal submitted
            fields=[item for item in browser.find_elements(By.CSS_SELECTOR,'input[type="password"]') if item.is_displayed()]
            if fields and not submitted:
                fields[-1].send_keys(password)
                buttons=[item for item in browser.find_elements(By.TAG_NAME,'button') if item.is_displayed() and item.is_enabled() and item.text.strip() in {'Connect','OK'}]
                if buttons:buttons[-1].click();submitted=True
                return False
            for item in browser.find_elements(By.CSS_SELECTOR,'.file-name'):
                if item.is_displayed() and item.text.startswith('localhost') and browser.execute_script('''
                    const tree=window.pgAdmin.Browser.tree;
                    return tree.itemData(tree.itemFrom(arguments[0].closest('.file-entry'))).connected===true;
                ''',item):return item
            return False
        server=wait.until(connected);expand(wait,server.text,ancestors=('Connectors','PostgreSQL'))
        databases=wait_for_tree_item(wait,'Databases');expand(wait,databases.text)
        database=wait_for_tree_item(wait,'postgres',ancestors=('Databases',))
        driver.execute_script('''
          const tree=window.pgAdmin.Browser.tree,item=tree.itemFrom(arguments[0].closest('.file-entry'));
          const node=window.pgAdmin.Browser.Nodes.database;
          if(!tree.itemData(item).connected)node.callbacks.connect_database.call(node,{item});
        ''',database)
        def database_connected(browser):
            for item in browser.find_elements(By.CSS_SELECTOR,'.file-name'):
                if item.is_displayed() and item.text.strip()=='postgres' and browser.execute_script('''
                    const tree=window.pgAdmin.Browser.tree,data=tree.itemData(tree.itemFrom(arguments[0].closest('.file-entry')));
                    return data._type==='database' && data.connected===true;
                ''',item):return item
            return False
        database=wait.until(database_connected)
        driver.get_log('browser')
        driver.execute_script('''
          const tree=window.pgAdmin.Browser.tree,item=tree.itemFrom(arguments[0].closest('.file-entry'));
          const data=tree.itemData(item);if(data._type!=='database' || !data.connected)throw Error('Expected the connected owned PostgreSQL database');
          const node=window.pgAdmin.Browser.Nodes.database;
          node.callbacks.open_large_object_files.call(node,{item});
        ''',database)
        def find_button(browser,name):
            try:return next((item for item in browser.find_elements(By.TAG_NAME,'button') if item.is_displayed() and item.is_enabled() and item.get_attribute('textContent').strip()==name),None)
            except StaleElementReferenceException:return None
        def button(name):return wait.until(lambda browser:find_button(browser,name))
        def click(name):
            def attempt(browser):
                try:
                    control=find_button(browser,name)
                    if control is None:return False
                    browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',control);control.click();return True
                except (StaleElementReferenceException,ElementClickInterceptedException):return False
            wait.until(attempt)
        def field(label):
            def find(browser):
                for item in browser.find_elements(By.TAG_NAME,'label'):
                    if item.is_displayed() and item.text==label:
                        result=browser.find_element(By.ID,item.get_attribute('for'))
                        if result.is_displayed():return result
                return False
            return wait.until(find)
        upload=wait.until(lambda browser:browser.find_element(By.CSS_SELECTOR,'input[aria-label="Binary file to import"]'))
        upload.send_keys(str(source));click('Upload and review file')
        button('Confirm and start native file transfer')
        reviewed=json.loads(driver.find_element(By.CSS_SELECTOR,'pre[aria-label="Native file transfer review"]').get_attribute('textContent'))
        click('Confirm and start native file transfer')
        def receipt(job_id):
            for item in driver.find_elements(By.CSS_SELECTOR,'details pre'):
                try:observed=json.loads(item.get_attribute('textContent'))
                except (ValueError,TypeError,StaleElementReferenceException):continue
                if observed.get('job_id')==job_id and observed.get('state')=='committed':return observed
            return False
        imported=wait.until(lambda _browser:receipt(reviewed['job_id']))
        operation=field('File operation');operation.click()
        wait.until(lambda browser:next((item for item in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if item.is_displayed() and item.text=='Export large object'),None)).click()
        for label,value in (('Large-object OID (import: 0 allocates)',imported['result']['oid']),('Download filename','Browser output ü.bin')):
            control=field(label);control.send_keys(Keys.CONTROL,'a');control.send_keys(value)
        click('Review native export');button('Confirm and start native file transfer')
        reviewed=json.loads(driver.find_element(By.CSS_SELECTOR,'pre[aria-label="Native file transfer review"]').get_attribute('textContent'))
        click('Confirm and start native file transfer');wait.until(lambda _browser:receipt(reviewed['job_id']))
        click('Download complete binary file')
        received=downloads/'Browser output ü.bin'
        wait.until(lambda _browser:received.is_file() and received.stat().st_size==len(data))
        assert received.read_bytes()==data
        driver.save_screenshot(str(output/'native-large-object-files.png'))
        errors=[item for item in driver.get_log('browser') if item.get('level')=='SEVERE']
        (output/'browser-console.json').write_text(json.dumps(errors,indent=2)+'\n');assert not errors
        return {'complete':True,'console_errors':0,'whole_file_upload':True,'whole_file_export':True,
                'native_browser_download_sha256':hashlib.sha256(received.read_bytes()).hexdigest(),'database_callback':True}
    except Exception:
        if driver is not None:
            driver.save_screenshot(str(output/'browser-failure.png'))
            (output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');parser.add_argument('--browser-only',action='store_true')
    args=parser.parse_args();qualify(args.evidence,browser_binary=args.browser_binary,driver_binary=args.driver_binary,browser_only=args.browser_only)
