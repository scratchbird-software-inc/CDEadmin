"""Native MySQL archive HTTP/browser workflow; owned fixtures and no history."""
import argparse
import builtins
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'web'),str(ROOT/'tools'),str(ROOT)]


def qualify(output,executable,*,browser_binary=None,driver_binary=None,use_c=False,engine='mysql',raw=False,gtid_mode=None):
    if engine not in {'mysql','mariadb'} or engine=='mariadb' and (use_c or raw):raise ValueError('Select a native archive interface')
    prefix='mysql_raw_binlog_' if raw else engine+'_binlog_'
    gtid_mode=gtid_mode or ('OFF' if raw else 'ON')
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    proof={'complete':False,'checks':[],'history_testing':'not run','source_sha256':{}}
    for path in [*list((ROOT/'web/pgadmin/cdeadmin').rglob('*binlog*.py')),ROOT/'web/pgadmin/static/js/Dialogs/MySQLBinlogArchives.jsx',
                 ROOT/'web/pgadmin/browser/server_groups/servers/__init__.py',Path(__file__)]:
        proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    os.environ['CDEADMIN_MYSQL_BINLOG_BINARY' if raw else 'CDEADMIN_MYSQLSH_BINARY' if engine=='mysql' else 'CDEADMIN_MARIADB_BINLOG_BINARY']=str(Path(executable).resolve(strict=True))
    builtins.SERVER_MODE=None
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    config.DATA_DIR=str(output/'app');config.SQLITE_PATH=str(output/'app/application.db')
    config.SESSION_DB_PATH=str(output/'app/sessions');config.STORAGE_DIR=str(output/'app/storage')
    config.LOG_FILE=str(output/'app/application.log');config.AZURE_CREDENTIAL_CACHE_DIR=str(output/'app/azure')
    config.CDEADMIN_OPERATION_STORE_PATH=str(output/'app/operations.json')
    setattr(config,'CDEADMIN_MYSQL_RAW_BINLOG_ROOT' if raw else 'CDEADMIN_'+engine.upper()+'_BINLOG_ROOT',str(output/'archives'))
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from flask import url_for
    from mysql_qualification_support import server,_root_connection
    if engine=='mariadb':
        from mariadb_qualification_support import server
    app=create_app('ScratchRobin-native-mysql-binlogs');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start();client=app.test_client();jobs=None
    try:
        with server(output/'fixture',**({'gtid_mode':gtid_mode,'keyring':raw} if engine=='mysql' else {})) as (route,_name,owned):
            root=_root_connection(engine,route['port']);root.autocommit=True;cursor=root.cursor()
            password=('native LF\nquote\"slash\\ 雪é-' if engine=='mariadb' or raw else '')+secrets.token_urlsafe(32)
            try:
                archive_user='root'
                if engine=='mariadb':
                    archive_user='sr_archive_operator'
                    cursor.execute("CREATE USER 'sr_archive_operator'@'%' IDENTIFIED BY %s",(password,))
                    cursor.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_archive_operator'@'%' WITH GRANT OPTION")
                else:cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                if engine=='mariadb':
                    import mariadb
                    with mariadb.connect(**{**route,'user':archive_user},password=password) as direct:
                        with direct.cursor() as verified:
                            verified.execute('SELECT CURRENT_USER()');proof['native_fixture_principal']=verified.fetchone()[0]
                cursor.execute('CREATE DATABASE sr_binlog_http');cursor.execute('CREATE TABLE sr_binlog_http.t(v INTEGER)')
                cursor.execute('FLUSH BINARY LOGS');cursor.execute('SHOW BINARY LOG STATUS' if engine=='mysql' else 'SHOW MASTER STATUS');start=cursor.fetchone()[0];cursor.fetchall()
                cursor.execute('INSERT INTO sr_binlog_http.t VALUES(1)');cursor.execute('FLUSH BINARY LOGS')
                with app.test_request_context('/'):
                    user=User.query.first();group=ServerGroup.query.filter_by(user_id=user.id).order_by(ServerGroup.id).first()
                    app.blueprints['NODE-engine_type'].connector_visibility[engine].set(True,user_id=user.id)
                    def register(label,username):
                        item=Server(user_id=user.id,servergroup_id=group.id,name=label,host=route['host'],port=route['port'],username=username,maintenance_db=None,save_password=0)
                        item._cde_endpoint_registration=registration_profile(engine+'-native')
                        item._cde_endpoint_route_configuration={**route,**({'use_pure':not use_c} if engine=='mysql' else {}),'user':username,'credential_kinds':['database_password']}
                        db.session.add(item);db.session.commit()
                        return item.id,url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id),url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id)
                    sid,connect_url,workspace_url=register('Owned native binary-log archives',archive_user);uid=user.id
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                if engine=='mariadb':
                    import mariadb
                    original_connect=mariadb.connect
                    def diagnostic_connect(*args,**kwargs):
                        try:return original_connect(*args,**kwargs)
                        except mariadb.Error as error:
                            diagnostic={'errno':error.errno,'sqlstate':error.sqlstate,'message':str(error).replace(password,'<redacted>'),
                                'credential_equals_owned_fixture':kwargs.get('password')==password}
                            (output/'native-connect-failure.json').write_text(json.dumps(diagnostic,indent=2)+'\n');raise
                    mariadb.connect=diagnostic_connect
                try:connected=client.post(connect_url,json={'password':password}).get_json()
                finally:
                    if engine=='mariadb':mariadb.connect=original_connect
                if not connected.get('success'):
                    (output/'connect-failure.json').write_text(json.dumps(connected,indent=2).replace(password,'<redacted>')+'\n')
                    raise RuntimeError('Native archive registration verification failed')
                def http(action,request):
                    response=client.post(workspace_url,json={'action':prefix+action,'request':request});value=response.get_json()
                    if response.status_code!=200 or not value.get('success'):
                        (output/'http-failure.json').write_text(json.dumps(value,indent=2)+'\n');raise RuntimeError('Native archive HTTP '+action+' failed')
                    return value['data']
                def wait(item):
                    deadline=time.monotonic()+90
                    while item['state'] in {'dispatching','active','cancel_requested'}:
                        if time.monotonic()>deadline:raise TimeoutError('Native HTTP archive deadline')
                        time.sleep(.1);item=http('status',{'job_id':item['job_id']})
                    assert item['state']=='completed',item
                    return item
                observed=http('catalog',{})
                if raw:assert observed['state']['gtid_mode']==gtid_mode
                assert observed['identity']['version'].split('-')[0]==('9.7.0' if engine=='mysql' else '12.2.2') and isinstance(observed['current']['Position'],str)
                selected={'start_file':start,'start_position':'4','compression':'zstd','threads':1} if engine=='mysql' and not raw else {'log_names':[start]}
                item=http('review',{'options':selected})
                request={'job_id':item['job_id'],'review_digest':item['review_digest'],'confirmed':True}
                completed=wait(http('start',request));assert http('start',request)['started_at']==completed['started_at']
                jobs=getattr(service_for_app(app),'mysql_raw_binlog_jobs' if raw else engine+'_binlog_jobs')
                proof['checks'].append('authenticated-native-http-review-confirm-dump-status-and-no-replay')
                reconciled=http('reconcile',{'job_id':item['job_id']})
                assert reconciled['result']==completed['result'] and reconciled['native_process_termination_confirmed'] is True
                proof['checks'].append('independent-native-byte-and-event-verification-preserves-original-sealed-receipt')
                page=http('files',{'job_id':item['job_id'],'offset':0,'limit':200});assert page['total']==len(page['files'])>=(4 if engine=='mysql' and not raw else 2)
                for row in page['files']:
                    response=client.post(workspace_url,data={'action':prefix+'download','payload':json.dumps({'job_id':item['job_id'],'path':row['path']})})
                    assert response.status_code==200 and response.headers['Cache-Control']=='no-store, private'
                    assert len(response.data)==int(row['size']) and hashlib.sha256(response.data).hexdigest()==row['sha256']
                    assert response.headers['X-Content-SHA256']==row['sha256'];response.close()
                proof['checks'].append('authenticated-whole-file-delivery-matches-every-native-artifact-sha256')
                if engine=='mariadb' or raw:
                    cursor.execute('SELECT @@datadir');datadir=cursor.fetchone()[0]
                    for row in page['files']:
                        if row['path']=='archive.json':continue
                        source_file=datadir.rstrip('/')+'/'+row['path']
                        original=subprocess.run(['docker','exec',_name,'sha256sum',source_file],check=True,capture_output=True,text=True,timeout=15).stdout.split()[0]
                        assert original==row['sha256'],row['path']
                    proof['checks'].append('independent-native-server-file-sha256-matches-the-complete-closed-archive')

                refused=client.post(workspace_url,data={'action':prefix+'download','payload':json.dumps({'job_id':item['job_id'],'path':'../../operations.json'})})
                assert refused.status_code==400
                with app.test_request_context('/'):
                    _other,other_verify,other_workspace=register('Other native archive scope',archive_user)
                assert client.post(other_verify,json={'password':password}).get_json()['success']
                assert client.post(other_workspace,json={'action':prefix+'status','request':{'job_id':item['job_id']}}).status_code==400
                proof['checks'].append('cross-endpoint-and-nonmanifest-file-identities-refused')
                cursor.execute("CREATE USER 'sr_denied_binlog'@'%' IDENTIFIED BY %s",(password,))
                with app.test_request_context('/'):
                    _denied,denied_verify,denied_workspace=register('Native binary-log privilege denial','sr_denied_binlog')
                assert client.post(denied_verify,json={'password':password}).get_json()['success']
                refusal=client.post(denied_workspace,json={'action':prefix+'catalog','request':{}})
                assert refusal.status_code==400 and '1227' in refusal.get_json()['errormsg']
                proof['checks'].append('native-restricted-account-observation-is-explicit-denial')
                app.config['CDEADMIN_MYSQL_RAW_BINLOG_MAX_RUNTIME_SECONDS' if raw else 'CDEADMIN_'+engine.upper()+'_BINLOG_MAX_RUNTIME_SECONDS']=1
                policy_refused=client.post(workspace_url,json={'action':prefix+'review','request':{'options':{**selected,'timeout_seconds':None}}})
                assert policy_refused.status_code==400 and 'policy' in policy_refused.get_json()['errormsg']
                app.config['CDEADMIN_MYSQL_RAW_BINLOG_MAX_RUNTIME_SECONDS' if raw else 'CDEADMIN_'+engine.upper()+'_BINLOG_MAX_RUNTIME_SECONDS']=None
                proof['checks'].append('application-native-runtime-policy-enforced')
                from pgadmin.cdeadmin.sdk.tooling import ProviderToolRunner
                original=ProviderToolRunner._resolve
                ProviderToolRunner._resolve=staticmethod(lambda _value:None)
                try:
                    unavailable=client.post(workspace_url,json={'action':prefix+'review','request':{'options':selected}})
                    assert unavailable.status_code==400 and 'unavailable' in unavailable.get_json()['errormsg']
                finally:ProviderToolRunner._resolve=staticmethod(original)
                proof['checks'].append('missing-native-utility-is-an-explicit-admission-refusal')
                if engine=='mariadb' or raw:
                    status_statement='SHOW MASTER STATUS' if engine=='mariadb' else 'SHOW BINARY LOG STATUS'
                    cursor.execute('CREATE TABLE sr_binlog_http.payload(id INTEGER PRIMARY KEY,body LONGBLOB)')
                    for index,(checksum,compressed) in enumerate((('NONE',1),('CRC32',0)),1):
                        cursor.execute('SET GLOBAL binlog_checksum=%s',(checksum,))
                        cursor.execute('SET GLOBAL log_bin_compress=%s' if engine=='mariadb' else 'SET SESSION binlog_transaction_compression=%s',(compressed,))
                        cursor.execute('FLUSH BINARY LOGS');cursor.execute(status_statement);filename=cursor.fetchone()[0];cursor.fetchall()
                        if engine=='mariadb':cursor.execute('SET SESSION gtid_domain_id=%s',(index,))
                        cursor.execute('INSERT INTO sr_binlog_http.payload VALUES(%s,%s)',(index,b'\x00\xffnative payload'*4096))
                        cursor.execute('FLUSH BINARY LOGS')
                        extra=http('review',{'options':{'log_names':[filename]}})
                        extra=wait(http('start',{'job_id':extra['job_id'],'review_digest':extra['review_digest'],'confirmed':True}))
                        stored=jobs.load(extra['job_id'],uid,extra['endpoint_id'])
                        assert {row['checksum_algorithm'] for row in stored['result']['artifact']['event_integrity']}=={'native_none' if checksum=='NONE' else 'crc32'}
                        if raw and compressed:
                            types=[]
                            with (jobs.directory(stored)/'archive'/filename).open('rb') as stream:
                                assert stream.read(4)==b'\xfebin'
                                while header:=stream.read(19):
                                    types.append(header[4]);stream.seek(int.from_bytes(header[9:13],'little')-19,1)
                            assert 40 in types,types
                    proof['checks'].append('native-checksum-off-compressed-row-events-and-multiple-gtid-domains' if engine=='mariadb' else 'native-checksum-off-and-on-with-observed-native-transaction-payload-compression')
                    load_path='/tmp/sr-owned-load.csv' if engine=='mariadb' else '/var/lib/mysql-files/sr-owned-load.csv'
                    subprocess.run(['docker','exec','-i','--user','root',_name,'tee',load_path],input=b'901\n902\n',
                        stdout=subprocess.DEVNULL,check=True,timeout=15)
                    cursor.execute("SET SESSION binlog_format='STATEMENT'");cursor.execute('FLUSH BINARY LOGS')
                    cursor.execute(status_statement);load_file=cursor.fetchone()[0];cursor.fetchall()
                    cursor.execute('LOAD DATA INFILE %s INTO TABLE sr_binlog_http.t',(load_path,))
                    cursor.execute('FLUSH BINARY LOGS')
                    loaded=http('review',{'options':{'log_names':[load_file]}})
                    loaded=wait(http('start',{'job_id':loaded['job_id'],'review_digest':loaded['review_digest'],'confirmed':True}))
                    loaded_directory=jobs.directory(jobs.load(loaded['job_id'],uid,loaded['endpoint_id']))
                    assert not (loaded_directory/'verification-load').exists() and not list(loaded_directory.glob('SQL_LOAD*'))
                    proof['checks'].append('native-statement-load-data-parser-fragments-stay-in-private-grant-and-are-removed')
                    active=http('catalog',{})['current']['File']
                    assert client.post(workspace_url,json={'action':prefix+'review','request':{'options':{'log_names':[active]}}}).status_code==400
                    proof['checks'].append('active-log-refused-without-inventing-a-closed-archive-boundary')
                    if raw:
                        cursor.execute('SET GLOBAL binlog_encryption=ON');cursor.execute('FLUSH BINARY LOGS')
                        cursor.execute(status_statement);encrypted_name=cursor.fetchone()[0];cursor.fetchall()
                        cursor.execute('INSERT INTO sr_binlog_http.t VALUES(903)');cursor.execute('FLUSH BINARY LOGS')
                        encrypted=http('review',{'options':{'log_names':[encrypted_name]}})
                        encrypted=wait(http('start',{'job_id':encrypted['job_id'],'review_digest':encrypted['review_digest'],'confirmed':True}))
                        encrypted_record=jobs.load(encrypted['job_id'],uid,encrypted['endpoint_id'])
                        encrypted_directory=jobs.directory(encrypted_record)/'archive'
                        metadata=json.loads((encrypted_directory/'archive.json').read_text())
                        assert metadata['logs'][0]['server_file_encrypted']=='Yes'
                        assert int(metadata['logs'][0]['server_file_bytes'])-int(metadata['logs'][0]['decoded_bytes'])==512
                        assert (encrypted_directory/encrypted_name).read_bytes()[:4]==b'\xfebin'
                        assert encrypted['result']['artifact']['native_closed_file_length_verified'] is True
                        cursor.execute('SET GLOBAL binlog_encryption=OFF');cursor.execute('FLUSH BINARY LOGS')
                        proof['checks'].append('native-encrypted-server-log-is-decrypted-by-native-stream-with-exact-v1-header-length-accounting')

                if browser_binary:
                    proof['browser']=browser(app,output,sid,start,browser_binary,driver_binary,engine=engine,raw=raw)
                    proof['checks'].append('native-browser-context-menu-review-execution-file-download-and-exact-confirmation-removal')
                if engine=='mariadb' or raw:
                    pending=http('review',{'options':selected})
                    cursor.execute('PURGE BINARY LOGS TO %s',(active,))
                    assert client.post(workspace_url,json={'action':prefix+'start','request':{'job_id':pending['job_id'],'review_digest':pending['review_digest'],'confirmed':True}}).status_code==400
                    assert http('status',{'job_id':pending['job_id']})['state']=='reviewed'
                    http('cancel',{'job_id':pending['job_id']})
                    proof['checks'].append('native-purge-after-review-refuses-dispatch-without-replaying')
                removed=http('remove_artifact',{'job_id':item['job_id'],'confirmation':item['job_id']})
                assert removed['artifact_removed'] and not (jobs.directory(jobs.load(item['job_id'],uid,completed['endpoint_id']))/'archive').exists()
                assert http('status',{'job_id':item['job_id']})['result']['artifact']['file_count']==page['total']
                proof['checks'].append('explicit-archive-removal-preserves-durable-verification-receipt')
                for path in Path(str(jobs.path)+'.jobs').glob('*.json'):assert password not in path.read_text()
            finally:cursor.close();root.close()
        assert owned['owned_server_stopped']
        assert http('list',{})['total']>=1 and http('status',{'job_id':item['job_id']})['artifact_removed']
        proof.update(complete=True,owned_server_stopped=True,engine=engine,raw=raw,gtid_mode=gtid_mode,interface='mariadb-connector-c' if engine=='mariadb' else 'c' if use_c else 'pure')
        proof['checks'].append('offline-authenticated-receipt-access-after-native-server-stops')
    finally:
        if jobs is not None:jobs.close()
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def browser(app,output,server_id,start,binary,driver_binary,*,engine='mysql',raw=False):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    downloads=output/'browser-downloads';downloads.mkdir()
    try:
        opts=webdriver.ChromeOptions();opts.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1600,1000'):opts.add_argument(flag)
        opts.add_argument('--user-data-dir='+str(output/'browser-profile'));opts.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        opts.add_experimental_option('prefs',{'download.default_directory':str(downloads),'download.prompt_for_download':False})
        driver=webdriver.Chrome(options=opts,service=Service(driver_binary) if driver_binary else Service())
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/');wait=WebDriverWait(driver,90)
        engine_label='MariaDB' if engine=='mariadb' else 'MySQL'
        ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,engine_label)
        def target(browser):
            for node in browser.find_elements(By.CSS_SELECTOR,'.file-name'):
                if node.is_displayed() and browser.execute_script('const tree=window.pgAdmin.Browser.tree;const data=tree.itemData(tree.itemFrom(arguments[0].closest(".file-entry")));return data?._type==="server" && String(data._id ?? data.id)===String(arguments[1]);',node,server_id):return node
            return None
        ActionChains(driver).context_click(wait.until(target)).perform()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="menuitem"]') if node.is_displayed() and node.text.strip()=='Backup'),None)).click()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="menuitem"]') if node.is_displayed() and engine_label+(' raw' if raw else '')+' binary-log archives' in node.text),None)).click()
        def click(text):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip()==text:
                        browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node)
                        if node.is_displayed():node.click();return True
                return False
            wait.until(attempt)
        def field(label,value):
            node=driver.find_element(By.XPATH,'//label[normalize-space()="'+label+'"]');control=driver.find_element(By.ID,node.get_attribute('for'))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',control);control.send_keys(Keys.CONTROL,'a');control.send_keys(value)
        if engine=='mariadb' or raw:
            click('Inspect native binary logs')
            def selector(browser):
                label=browser.find_element(By.XPATH,'//label[normalize-space()="Native closed binary logs"]')
                return browser.find_element(By.ID,label.get_attribute('for'))
            select=wait.until(selector);driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',select);select.click()
            wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.text.startswith(start+' (')),None)).click()
            driver.switch_to.active_element.send_keys(Keys.ESCAPE)
        else:field('Native binary-log filename',start)
        click('Review archive');click('Confirm and start archive')
        wait.until(lambda browser:any('completed.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        click('Load archive files')
        table=wait.until(lambda browser:browser.find_element(By.CSS_SELECTOR,'table[aria-label="Verified native archive files"]'))
        rows=table.find_elements(By.CSS_SELECTOR,'tbody tr');assert len(rows)>=(4 if engine=='mysql' and not raw else 2)
        row=rows[0];cells=row.find_elements(By.TAG_NAME,'td');relative=cells[0].get_attribute('textContent');checksum=cells[2].get_attribute('textContent')
        button=row.find_element(By.TAG_NAME,'button');driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',button);button.click()
        file=downloads/relative.rsplit('/',1)[-1]
        wait.until(lambda _browser:file.exists() and hashlib.sha256(file.read_bytes()).hexdigest()==checksum)
        alert=next(node.get_attribute('textContent') for node in driver.find_elements(By.CSS_SELECTOR,'[role="alert"]') if 'completed.' in node.get_attribute('textContent'))
        job_id=alert.split('Archive ',1)[1].split(':',1)[0].strip()
        field('Confirm job identity to remove archive files',job_id);click('Remove application archive files')
        wait.until(lambda browser:any('receipt is retained' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        driver.save_screenshot(str(output/'native-mysql-binlog-archives.png'))
        errors=[entry for entry in driver.get_log('browser') if entry.get('level')=='SEVERE'];(output/'browser-console.json').write_text(json.dumps(errors,indent=2)+'\n');assert not errors
        return {'complete':True,'console_errors':0,'download_sha256':checksum,'download_relative_path':relative}
    except Exception:
        if driver is not None:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--raw',action='store_true');parser.add_argument('--gtid-mode',choices=('ON','OFF'));parser.add_argument('--mysql-binlog',type=Path)
    parser.add_argument('--engine',choices=('mysql','mariadb'),default='mysql');parser.add_argument('--mysql-shell',type=Path);parser.add_argument('--mariadb-binlog',type=Path)
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');parser.add_argument('--use-c',action='store_true');args=parser.parse_args()
    executable=args.mysql_binlog if args.raw else args.mysql_shell if args.engine=='mysql' else args.mariadb_binlog
    if executable is None:parser.error('Select the native utility for this engine')
    qualify(args.evidence,executable,browser_binary=args.browser_binary,driver_binary=args.driver_binary,use_c=args.use_c,engine=args.engine,raw=args.raw,gtid_mode=args.gtid_mode)
