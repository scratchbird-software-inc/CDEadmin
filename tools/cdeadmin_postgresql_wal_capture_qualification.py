#!/usr/bin/env python3
"""Owned PostgreSQL 18.3 HTTP WAL streaming, resume and native recovery proof."""
import argparse
import builtins
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,binary_path,*,browser_binary=None,driver_binary=None):
    import psycopg
    from postgresql_qualification_support import server as owned_server
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence must be outside the source checkout')
    output.mkdir(parents=True,exist_ok=False)
    proof={'complete':False,'checks':[],'history_testing':'not run','full_product_complete':False,
           'source_sha256':{}}
    for directory in ('web/pgadmin/cdeadmin/providers/postgresql','web/pgadmin/cdeadmin/workspace','web/pgadmin/cdeadmin/sdk'):
        for path in (ROOT/directory).glob('*.py'):proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ('fileio.py','store.py'):
        path=ROOT/'web/pgadmin/cdeadmin/operations'/name
        proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    builtins.SERVER_MODE=None
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    config.DATA_DIR=str(output/'app');config.SQLITE_PATH=str(output/'app/application.db')
    config.SESSION_DB_PATH=str(output/'app/sessions');config.STORAGE_DIR=str(output/'app/storage')
    config.LOG_FILE=str(output/'app/application.log');config.AZURE_CREDENTIAL_CACHE_DIR=str(output/'app/azure')
    config.CDEADMIN_OPERATION_STORE_PATH=str(output/'app/operations.json')
    config.CDEADMIN_POSTGRESQL_CONTINUITY_ROOT=str(output/'backups')
    config.CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH=str(binary_path)
    config.CDEADMIN_POSTGRESQL_WAL_ARCHIVE_ROOT=str(output/'wal-archives')
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server
    from flask import url_for
    from pgadmin.cdeadmin.workspace import service_for_app
    app=create_app('ScratchRobin-native-wal-capture-qualification');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start();client=app.test_client();jobs=None
    try:
        with owned_server(output/'fixture',server_options=('-c','wal_keep_size=64MB'),
                initdb_options=('--wal-segsize=1','--locale=C','--encoding=UTF8')) as (route,password,fixture):
            with psycopg.connect(host=route['host'],port=route['port'],user=route['user'],password=password,
                                 dbname=route['database'],autocommit=True) as native:
                hba=native.execute('SHOW hba_file').fetchone()[0]
                subprocess.run(['docker','exec','--user','postgres','-i',fixture['owned_container_name'],'sh','-c','cat >> "$1"','fixture',hba],
                    input=b'\nhost replication postgres all scram-sha-256\n',check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
                native.execute('SELECT pg_reload_conf()')
                native.execute('CREATE TABLE sr_continuity_data(id bigint PRIMARY KEY,body text)')
                native.execute("INSERT INTO sr_continuity_data VALUES(9007199254740993,'base 😀')")
                with app.test_request_context('/'):
                    user=User.query.first();group=ServerGroup.query.filter_by(user_id=user.id).order_by(ServerGroup.id).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['postgresql'].set(True,user_id=user.id)
                    registered=Server(user_id=user.id,servergroup_id=group.id,name='Owned PostgreSQL WAL capture',
                        host=route['host'],port=route['port'],username=route['user'],maintenance_db=route['database'],
                        connection_params={'sslmode':'disable'},save_password=0)
                    db.session.add(registered);db.session.commit()
                    uid,endpoint=user.id,registered.endpoint_profile.id
                    connect_url=url_for('NODE-server.connect_id',gid=group.id,sid=registered.id)
                    workspace_url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=registered.id)
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                assert client.post(connect_url,json={'password':password}).get_json().get('success')
                def http(operation,request):
                    response=client.post(workspace_url,json={'action':'postgresql_continuity_'+operation,'request':request})
                    value=response.get_json()
                    if response.status_code!=200 or not value.get('success'):
                        (output/'http-failure.json').write_text(json.dumps(value,indent=2).replace(password,'<redacted>')+'\n')
                        raise AssertionError('Owned native WAL HTTP '+operation+' failed')
                    return value['data']
                def wait(job_id,predicate):
                    deadline=time.monotonic()+120
                    while True:
                        current=http('status',{'job_id':job_id})
                        if predicate(current):return current
                        if current['state'] in {'unknown','failed','not_dispatched'}:
                            (output/'job-failure.json').write_text(json.dumps(current,indent=2)+'\n')
                            raise AssertionError('Owned native WAL job returned '+current['state'])
                        if time.monotonic()>deadline:raise TimeoutError('Owned native WAL qualification deadline')
                        time.sleep(.1)
                def start(operation,options,*,before_start=None,**inputs):
                    reviewed=http('review',{'operation':operation,'options':options,**inputs})
                    if before_start is not None:before_start(reviewed)
                    request={'job_id':reviewed['job_id'],'review_digest':reviewed['review_digest'],'confirmed':True}
                    current=http('start',request)
                    assert http('start',request)['job_id']==current['job_id']
                    return reviewed,current
                base,_current=start('full_backup',{'timeout_seconds':120})
                base=wait(base['job_id'],lambda r:r['state']=='verified')
                proof['native_server']=base['source'];proof['native_tools']=dict(base['tool_identities'])
                jobs=service_for_app(app).postgresql_continuity_jobs
                proof['checks'].append('native-full-base-backup-before-managed-streaming')
                def streaming(job_id):
                    wait(job_id,lambda r:r['state']=='active' and (r.get('progress') or {}).get('pid') is not None)
                    deadline=time.monotonic()+15
                    while int(native.execute('SELECT count(*) FROM pg_stat_replication').fetchone()[0])<1:
                        if time.monotonic()>deadline:raise TimeoutError('Owned native receiver connection deadline')
                        time.sleep(.1)
                receipts=[];target='ScratchRobin managed WAL target ü'
                for index,compression in enumerate(('none','gzip:level=3','lz4:level=3')):
                    name='managed-'+str(index)
                    reviewed,_current=start('wal_capture',{'archive':name,'compression':compression,'timeout_seconds':None})
                    proof['native_tools'].update(reviewed['tool_identities'])
                    assert reviewed['source']['wal_segment_bytes']==1024**2 and reviewed['source']['wal_block_bytes']==8192
                    streaming(reviewed['job_id'])
                    if index==0:
                        native.execute("INSERT INTO sr_continuity_data VALUES(9007199254740994,'target state 😀')")
                        native.execute('SELECT pg_create_restore_point(%s)',(target,))
                        native.execute("INSERT INTO sr_continuity_data VALUES(9007199254740995,'after target')")
                    for segment in range(2):
                        native.execute('SELECT pg_logical_emit_message(false,%s,%s)',('scratchrobin-owned-wal','x'*8192))
                        native.execute('SELECT pg_switch_wal()')
                        wait(reviewed['job_id'],lambda r:(r.get('archive_observation') or {}).get('new_files',0)>=segment+1)
                    http('cancel',{'job_id':reviewed['job_id']})
                    cancelled=wait(reviewed['job_id'],lambda r:r['state']=='cancelled')
                    assert cancelled['tool_observation']['process_observation']['cleanup_confirmed']
                    directory=jobs.archive_directory(uid,endpoint)/name
                    files={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()}
                    assert len(files)>=2
                    for filename,digest in files.items():
                        original=native.execute("SELECT encode(pg_read_binary_file(%s),'hex')",('pg_wal/'+filename,)).fetchone()[0]
                        assert hashlib.sha256(bytes.fromhex(original)).hexdigest()==digest
                    receipts.append({'compression':compression,'job_id':reviewed['job_id'],'files':files,
                                     'native_server_bytes_match':True,'cancelled_writer_stopped':True})
                    print('Native '+compression+' WAL capture, exact source bytes and cancellation passed',flush=True)
                prior=receipts[0]['files']
                resumed,_current=start('wal_capture',{'archive':'managed-0','compression':'gzip:level=3','timeout_seconds':None})
                streaming(resumed['job_id'])
                native.execute("SELECT pg_logical_emit_message(false,'scratchrobin-owned-wal','resume')")
                native.execute('SELECT pg_switch_wal()')
                wait(resumed['job_id'],lambda r:(r.get('archive_observation') or {}).get('new_files',0)>=1)
                http('cancel',{'job_id':resumed['job_id']})
                resumed=wait(resumed['job_id'],lambda r:r['state']=='cancelled')
                assert resumed['archive_observation']['resumed_after_segment']==max(prior)
                directory=jobs.archive_directory(uid,endpoint)/'managed-0'
                for name,digest in prior.items():assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest
                proof['checks'].extend(['native-raw-gzip-lz4-capture-with-exact-server-byte-comparison',
                    'native-cancellation-stops-receiver-and-retains-completed-files',
                    'native-resume-from-completed-archive-with-unchanged-prior-segments'])
                proof['captures']=receipts;proof['resumed_job_id']=resumed['job_id']
                if browser_binary:
                    def browser_streaming():
                        selected=next(job for job in jobs.list(uid,endpoint)['jobs']
                                      if job['operation']=='wal_capture' and job['options']['archive']=='browser-managed')
                        streaming(selected['job_id'])
                        native.execute("SELECT pg_logical_emit_message(false,'scratchrobin-owned-wal','browser')")
                        native.execute('SELECT pg_switch_wal()')
                        return selected['job_id']
                    proof['capture_browser']=qualify_capture_browser(app,output,browser_binary,driver_binary,browser_streaming,password)
                    selected=wait(proof['capture_browser']['job_id'],lambda r:r['state']=='cancelled')
                    assert selected['tool_observation']['process_observation']['cleanup_confirmed']
                    for path in (jobs.archive_directory(uid,endpoint)/'browser-managed').iterdir():
                        original=native.execute("SELECT encode(pg_read_binary_file(%s),'hex')",('pg_wal/'+path.name,)).fetchone()[0]
                        assert path.read_bytes()==bytes.fromhex(original)
                    proof['checks'].append('native-browser-reviews-starts-observes-and-cancels-managed-wal-capture-with-independent-source-bytes')
        assert fixture['owned_server_stopped']
        # This separate owned recovery archive grows by one genuine completed
        # source segment after the native review has pinned its input hashes.
        original=jobs.archive_directory(uid,endpoint)/'managed-0'
        growing=jobs.archive_directory(uid,endpoint)/'managed-growth-review';growing.mkdir(mode=0o700)
        files=sorted(original.iterdir());assert len(files)>=3
        for path in files[:-1]:shutil.copyfile(path,growing/path.name)
        reviewed,_current=start('recovery_drill',{'target':{'kind':'name','value':target},'wal_archive':'managed-growth-review',
            'checks':[{'schema':'public','table':'sr_continuity_data','expected_rows':'2'}],'timeout_seconds':120},base_job_id=base['job_id'],
            before_start=lambda _review:shutil.copyfile(files[-1],growing/files[-1].name))
        recovered=wait(reviewed['job_id'],lambda r:r['state']=='recovered')
        assert recovered['recovery_observation']['point_in_time_recovery'] and recovered['wal_archive_observation']['reviewed_content_matched']
        assert recovered['wal_archive_observation']['unreviewed_files_at_start']==1 and recovered['wal_archive_observation']['unreviewed_files_staged'] is False
        proof['checks'].append('offline-native-pitr-uses-managed-receiver-archive-and-excludes-later-commits')
        proof['checks'].append('native-recovery-ignores-new-completed-archive-file-added-after-review')
        proof['recovery_job_id']=recovered['job_id']
        if browser_binary:
            from cdeadmin_postgresql_continuity_qualification import qualify_browser
            proof['browser']=qualify_browser(app,output,base['job_id'],browser_binary,driver_binary)
        proof['complete']=True
    finally:
        if jobs is not None:jobs.close()
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def qualify_capture_browser(app,output,browser_binary,driver_binary,on_started,password):
    import re
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,wait_for_tree_item
    http=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=browser_binary
        for value in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1600,1000',
                      '--user-data-dir='+str(output/'capture-browser-profile')):options.add_argument(value)
        options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary) if driver_binary else Service())
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/');wait=WebDriverWait(driver,60)
        ensure_data_explorer(wait);expand(wait,'Connectors');wait_for_tree_item(wait,'PostgreSQL');expand(wait,'PostgreSQL')
        element=wait_for_tree_item(wait,'localhost',ancestors=('Connectors','PostgreSQL'))
        driver.get_log('browser')
        driver.execute_script("""
          const tree=window.pgAdmin.Browser.tree;
          const item=tree.itemFrom(arguments[0].closest('.file-entry'));
          if(tree.itemData(item)._type!=='server')throw Error('Expected owned native server');
          const node=window.pgAdmin.Browser.Nodes.server;
          node.callbacks.open_postgresql_continuity.call(node,{item});
        """,element)
        def authenticate(browser):
            fields=[item for item in browser.find_elements(By.CSS_SELECTOR,'input[aria-label="Password"]') if item.is_displayed()]
            if not fields:return False
            field=fields[0]
            if field.is_enabled():
                if field.get_attribute('value')!=password:field.clear();field.send_keys(password)
                submit=next((item for item in browser.find_elements(By.TAG_NAME,'button') if item.is_displayed() and item.is_enabled() and item.text.strip()=='OK'),None)
                if submit is not None:submit.click()
            return True
        def click(name):
            def attempt(browser):
                from selenium.common.exceptions import ElementClickInterceptedException,StaleElementReferenceException
                try:
                    if authenticate(browser):return False
                    control=next((item for item in browser.find_elements(By.TAG_NAME,'button') if item.is_enabled() and item.text.strip()==name),None)
                    if control is None:return False
                    browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',control)
                    if not control.is_displayed():return False
                    control.click();return True
                except (ElementClickInterceptedException,StaleElementReferenceException):return False
            wait.until(attempt)
        wait.until(lambda browser:browser.find_elements(By.XPATH,'//label[normalize-space()="Continuity operation"]'))
        def select_capture(browser):
            from selenium.common.exceptions import ElementClickInterceptedException,StaleElementReferenceException
            try:
                if authenticate(browser):return False
                selected=next((item for item in browser.find_elements(By.CSS_SELECTOR,'[role="option"]')
                               if item.text.strip()=='Capture native WAL archive'),None)
                if selected is not None:selected.click();return True
                label=browser.find_element(By.XPATH,'//label[normalize-space()="Continuity operation"]')
                field=browser.find_element(By.ID,label.get_attribute('for'))
                browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',field)
                if field.get_attribute('aria-expanded')!='true':field.click()
                return False
            except (ElementClickInterceptedException,StaleElementReferenceException):return False
        wait.until(select_capture)
        for label_text,value in (('WAL archive','browser-managed'),('WAL compression','gzip:level=3')):
            label=driver.find_element(By.XPATH,'//label[normalize-space()="'+label_text+'"]')
            field=driver.find_element(By.ID,label.get_attribute('for'))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',field)
            field.send_keys(Keys.COMMAND if sys.platform=='darwin' else Keys.CONTROL,'a');field.send_keys(Keys.BACKSPACE);field.send_keys(value)
            wait.until(lambda _browser:field.get_attribute('value')==value)
        click('Review native operation')
        wait.until(lambda browser:'wal_capture' in browser.find_element(By.CSS_SELECTOR,'[aria-label="Native backup review"]').get_attribute('textContent'))
        click('Confirm and start reviewed operation')
        wait.until(lambda browser:any(re.search(r'Job .*: active\.',item.get_attribute('textContent')) for item in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        job_id=on_started()
        def published(browser):
            for item in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]'):
                text=item.get_attribute('textContent');match=re.search(r'Newly published: ([0-9]+)',text)
                if match and int(match[1])>=1:return True
            return False
        wait.until(published);click('Cancel native job')
        wait.until(lambda browser:any(('Job '+job_id+': cancelled.') in item.get_attribute('textContent') for item in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        driver.save_screenshot(str(output/'native-wal-capture.png'))
        expected=lambda item:'/browser/server/connect/' in item.get('message','') and '428' in item.get('message','')
        errors=[item for item in driver.get_log('browser') if item.get('level')=='SEVERE' and not expected(item)]
        (output/'capture-browser-console.json').write_text(json.dumps(errors,indent=2)+'\n');assert not errors
        return {'complete':True,'job_id':job_id,'reviewed_start':True,'native_files_observed':True,
                'cancelled':True,'console_errors':0,'screenshot':'native-wal-capture.png'}
    except Exception:
        if driver is not None:
            driver.save_screenshot(str(output/'capture-browser-failure.png'))
            (output/'capture-browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
            (output/'capture-browser-failure-console.json').write_text(json.dumps(driver.get_log('browser'),indent=2)+'\n')
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--binary-path',type=Path,default=Path('/usr/lib/postgresql/18/bin'))
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args()
    qualify(args.evidence,args.binary_path,browser_binary=args.browser_binary,driver_binary=args.driver_binary)
