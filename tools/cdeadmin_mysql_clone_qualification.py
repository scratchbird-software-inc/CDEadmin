#!/usr/bin/env python3
"""Owned MySQL 9.7 HTTP local cloning and independent native recovery proof."""
import argparse
import builtins
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'web'),str(ROOT/'tools'),str(ROOT)]


def qualify(output,*,browser_binary=None,driver_binary=None):
    import mysql.connector
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence must be outside the source checkout')
    output.mkdir(parents=True,exist_ok=False)
    proof={'complete':False,'checks':[],'history_testing':'not run','source_sha256':{}}
    for directory in ('web/pgadmin/cdeadmin/workspace','web/pgadmin/cdeadmin/providers/mysql_family'):
        for path in (ROOT/directory).glob('*.py'):
            proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    builtins.SERVER_MODE=None
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    config.DATA_DIR=str(output/'app');config.SQLITE_PATH=str(output/'app/application.db')
    config.SESSION_DB_PATH=str(output/'app/sessions');config.STORAGE_DIR=str(output/'app/storage')
    config.LOG_FILE=str(output/'app/application.log');config.AZURE_CREDENTIAL_CACHE_DIR=str(output/'app/azure')
    config.CDEADMIN_OPERATION_STORE_PATH=str(output/'app/operations.json')
    config.CDEADMIN_MYSQL_CLONE_RECEIPT_ROOT=str(output/'clone-receipts')
    from pgadmin import create_app
    from mysql_qualification_support import server as owned_server
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from flask import url_for
    app=create_app('ScratchRobin-native-mysql-clone-qualification');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start();client=app.test_client();jobs=None
    restored_name='sr-mysql-clone-restore-'+secrets.token_hex(8);restored_started=False
    restored=output/'restored-clone'
    password=secrets.token_urlsafe(32)
    parent='/var/lib/sr-owned-clones'
    try:
        with owned_server(output/'fixture') as (route,name,fixture):
            native=mysql.connector.connect(**route,autocommit=True)
            cursor=native.cursor()
            try:
                cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                route['password']=password
                cursor.execute("SELECT COUNT(*) FROM information_schema.PLUGINS WHERE PLUGIN_NAME='clone' AND PLUGIN_STATUS='ACTIVE'")
                if cursor.fetchone()[0]==0:cursor.execute("INSTALL PLUGIN clone SONAME 'mysql_clone.so'")
                for command in (['mkdir','-p',parent],['chown','mysql:mysql',parent]):
                    subprocess.run(['docker','exec','--user','root',name,*command],check=True,timeout=15,stdout=subprocess.DEVNULL)
                cursor.execute('CREATE DATABASE sr_clone_data CHARACTER SET utf8mb4')
                cursor.execute('CREATE TABLE sr_clone_data.sample(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB) ENGINE=InnoDB')
                cursor.execute('INSERT INTO sr_clone_data.sample VALUES(%s,%s,%s)',(9007199254740993,'Unicode 😀',bytes.fromhex('0080ff')))
                with app.test_request_context('/'):
                    user=User.query.first();group=ServerGroup.query.filter_by(user_id=user.id).order_by(ServerGroup.id).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=user.id)
                    registered=Server(user_id=user.id,servergroup_id=group.id,name='Owned MySQL clone',
                        host=route['host'],port=route['port'],username='root',maintenance_db=None,save_password=0)
                    registered._cde_endpoint_registration=registration_profile('mysql-native')
                    registered._cde_endpoint_route_configuration={key:value for key,value in route.items() if key!='password'}
                    registered._cde_endpoint_route_configuration['credential_kinds']=['database_password']
                    db.session.add(registered);db.session.commit()
                    uid,sid,gid=user.id,registered.id,group.id
                    endpoint=registered.endpoint_profile.id
                    connect_url=url_for('NODE-server.verify_endpoint_id',gid=gid,sid=sid)
                    workspace_url=url_for('NODE-server.cde_workspace_id',gid=gid,sid=sid)
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                connected=client.post(connect_url,json={'password':password}).get_json()
                if not connected.get('success'):
                    (output/'connect-failure.json').write_text(json.dumps(connected,indent=2).replace(password,'<redacted>')+'\n')
                    raise RuntimeError('Owned native MySQL application connection failed')
                def http(operation,request):
                    response=client.post(workspace_url,json={'action':'mysql_clone_'+operation,'request':request})
                    value=response.get_json()
                    if response.status_code!=200 or not value.get('success'):
                        (output/'http-failure.json').write_text(json.dumps(value,indent=2).replace(password,'<redacted>')+'\n')
                        raise RuntimeError('Native clone HTTP '+operation+' failed')
                    return value['data']
                def start(path):
                    review=http('review',{'options':{'destination':path,'confirmation':path,'timeout_seconds':120}})
                    assert review['source']['version'].split('-')[0]=='9.7.0'
                    request={'job_id':review['job_id'],'review_digest':review['review_digest'],'confirmed':True}
                    result=http('start',request);repeated=http('start',request)
                    assert repeated['job_id']==result['job_id']
                    return result,request
                def finish(result,expected):
                    deadline=time.monotonic()+150
                    while result['state'] in {'dispatching','active','cancel_requested'}:
                        if time.monotonic()>deadline:
                            http('cancel',{'job_id':result['job_id']});raise TimeoutError('Native local clone deadline')
                        time.sleep(.1);result=http('status',{'job_id':result['job_id']})
                    if result['state']!=expected:
                        (output/'clone-failure.json').write_text(json.dumps(result,indent=2)+'\n')
                        raise RuntimeError('Native local clone returned '+result['state'])
                    return result
                path=parent+'/Clone "ü" '+secrets.token_hex(8)
                completed,request=start(path);completed=finish(completed,'native_completed')
                assert completed['sql_observation']['acknowledged'] and completed['native_observation']['job_correlated']
                assert completed['files_verified'] is False and completed['recovery_drill_complete'] is False
                proof['checks'].append('authenticated-http-native-innodb-local-clone-to-exact-quoted-unicode-server-directory-and-correlated-pfs-completion')
                print('native local clone completed through application HTTP',flush=True)
                cursor.execute("INSERT INTO sr_clone_data.sample VALUES(9007199254740994,'after clone',X'AABB')")
                restored.mkdir()
                subprocess.run(['docker','cp',name+':'+path+'/.',str(restored)],check=True,timeout=60,stdout=subprocess.DEVNULL)
                subprocess.run(['docker','run','--rm','-d','--name',restored_name,'--publish','127.0.0.1::3306',
                    '--mount','type=bind,source='+str(restored)+',target=/var/lib/mysql','mysql:9.7.0','--server-id=202','--skip-log-bin'],
                    check=True,timeout=30,stdout=subprocess.DEVNULL)
                restored_started=True
                port=int(subprocess.check_output(['docker','port',restored_name,'3306/tcp'],text=True,timeout=15).strip().rsplit(':',1)[1])
                deadline=time.monotonic()+90
                while True:
                    try:
                        recovered=mysql.connector.connect(host='127.0.0.1',port=port,user='root',password=password,
                            use_pure=True,connection_timeout=2,autocommit=True);break
                    except mysql.connector.Error:
                        if time.monotonic()>deadline:raise
                        time.sleep(.2)
                with recovered.cursor() as observed:
                    observed.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_clone_data.sample ORDER BY id')
                    assert observed.fetchall()==[('9007199254740993','Unicode 😀','0080FF')]
                    observed.execute('SELECT VERSION()');assert observed.fetchone()[0].split('-')[0]=='9.7.0'
                recovered.close()
                proof['checks'].append('independent-native-mysql9.7-recovery-of-cloned-files-preserves-exact-int64-unicode-binary-and-excludes-later-source-data')
                print('independent native MySQL clone recovery passed',flush=True)
                cursor.execute('SET GLOBAL clone_max_data_bandwidth=1')
                cancelled,_request=start(parent+'/cancel-'+secrets.token_hex(8))
                deadline=time.monotonic()+30
                while not cancelled.get('native_observation',{}).get('status'):
                    if time.monotonic()>deadline:raise TimeoutError('Native clone never exposed correlated live progress')
                    time.sleep(.1);cancelled=http('status',{'job_id':cancelled['job_id']})
                    if cancelled['state'] not in {'dispatching','active'}:raise RuntimeError('Clone finished before cancellation fixture became active')
                http('cancel',{'job_id':cancelled['job_id']});cancelled=finish(cancelled,'cancelled')
                assert cancelled['cancel_delivery']['acknowledged'] and cancelled['native_completion_observed']
                cursor.execute('SET GLOBAL clone_max_data_bandwidth=0')
                proof['checks'].append('native-pfs-progress-and-identity-bound-kill-query-cancellation-with-confirmed-native-failed-state')
                print('native MySQL clone cancellation passed',flush=True)
                # A repeated terminal start reads its receipt without replaying.
                assert http('start',request)['state']=='native_completed'
                reconciled=http('reconcile',{'job_id':completed['job_id']})
                assert reconciled['state']=='native_completed'
                proof['checks'].append('durable-no-replay-and-native-status-reconciliation')
                import pgadmin.cdeadmin.workspace.mysql_clone_jobs as clone_module
                original_rows=clone_module.rows
                def lose_reply(connection,statement,parameters=()):
                    result=original_rows(connection,statement,parameters)
                    if statement.startswith('CLONE LOCAL DATA DIRECTORY'):raise OSError('fixture loses successful clone acknowledgement')
                    return result
                clone_module.rows=lose_reply
                try:
                    lost,lost_request=start(parent+'/lost-reply-'+secrets.token_hex(8))
                    lost=finish(lost,'native_completed')
                    assert lost['sql_observation']['acknowledged'] is False and lost['native_completion_observed']
                    assert http('start',lost_request)['state']=='native_completed'
                finally:clone_module.rows=original_rows
                proof['checks'].append('lost-success-reply-reconciles-only-from-frozen-native-operation-identity-without-replay')
                refused,_request=start(path);refused=finish(refused,'refused')
                assert refused['sql_observation']['native_refusal'] and refused['native_completion_observed'] is False
                proof['checks'].append('native-existing-directory-refusal-does-not-reuse-a-prior-completed-status')
                cursor.execute("CREATE USER 'sr_no_backup'@'%' IDENTIFIED BY %s",(password,))
                def register(label,username,use_pure,sql_mode=None):
                    with app.test_request_context('/'):
                        item=Server(user_id=uid,servergroup_id=gid,name=label,host=route['host'],port=route['port'],username=username,maintenance_db=None,save_password=0)
                        item._cde_endpoint_registration=registration_profile('mysql-native')
                        item._cde_endpoint_route_configuration={'host':route['host'],'port':route['port'],'user':username,'use_pure':use_pure,'credential_kinds':['database_password']}
                        if sql_mode is not None:item._cde_endpoint_route_configuration['sql_mode']=sql_mode
                        db.session.add(item);db.session.commit()
                        verify=url_for('NODE-server.verify_endpoint_id',gid=gid,sid=item.id)
                        workspace=url_for('NODE-server.cde_workspace_id',gid=gid,sid=item.id)
                    response=client.post(verify,json={'password':password}).get_json()
                    if not response.get('success'):
                        (output/'secondary-connect-failure.json').write_text(json.dumps(response,indent=2).replace(password,'<redacted>')+'\n')
                        raise RuntimeError('Secondary native MySQL endpoint verification failed')
                    return workspace
                original_workspace=workspace_url
                try:
                    workspace_url=register('Owned MySQL denied clone','sr_no_backup',True)
                    denied,_request=start(parent+'/denied-'+secrets.token_hex(8));denied=finish(denied,'refused')
                    assert denied['sql_observation']['error_number']==1227
                    proof['checks'].append('native-backup-admin-denial-is-refused-without-application-privilege-escalation')
                    workspace_url=register('Owned MySQL C clone','root',False,'NO_BACKSLASH_ESCAPES,ANSI_QUOTES')
                    alternate,_request=start(parent+'/C exact \\ quoted "ü" '+secrets.token_hex(8))
                    alternate=finish(alternate,'native_completed')
                    assert alternate['source']['client_interface']=='CMySQLConnection'
                    proof['checks'].append('native-c-extension-worker-and-observer-under-ansi-quotes-no-backslash-escapes-preserve-exact-server-path')
                finally:workspace_url=original_workspace
                jobs=service_for_app(app).mysql_clone_jobs
                for file in Path(str(jobs.path)+'.jobs').glob('*.json'):assert password not in file.read_text()
                if browser_binary:
                    proof['browser']=browser(app,output,parent,sid,browser_binary,driver_binary)
                    proof['checks'].append('native-browser-server-menu-reviews-confirms-and-observes-local-physical-clone')
                proof.update(complete=True,source=completed['source'],job_ids=[completed['job_id'],cancelled['job_id']])
            finally:cursor.close();native.close()
        assert fixture['owned_server_stopped']
        assert http('list',{})['total']>=2
        proof['checks'].append('offline-authenticated-http-owner-bound-clone-receipts-after-source-stopped')
    finally:
        if jobs is not None:jobs.close()
        if restored_started:
            with (output/'restore-server.log').open('wb') as stream:
                subprocess.run(['docker','logs',restored_name],stdout=stream,stderr=subprocess.STDOUT,timeout=15)
            stopped=subprocess.run(['docker','stop',restored_name],stdout=subprocess.DEVNULL,timeout=45)
            proof['owned_restored_server_stopped']=stopped.returncode==0
            ownership=subprocess.run(['docker','run','--rm','--user','0:0','--entrypoint','find','--mount',
                'type=bind,source='+str(restored)+',target=/owned','mysql:9.7.0','/owned','!','-type','l','-exec','chown',
                str(os.getuid())+':'+str(os.getgid()),'{}','+'],check=False,timeout=30,stdout=subprocess.DEVNULL)
            proof['owned_clone_ownership_restored']=ownership.returncode==0
            if ownership.returncode!=0:proof['complete']=False
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    assert proof['complete'] and proof['owned_restored_server_stopped']
    return proof


def browser(app,output,parent,server_id,binary,driver_binary):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand
    http=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        opts=webdriver.ChromeOptions();opts.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1600,1000'):opts.add_argument(flag)
        opts.add_argument('--user-data-dir='+str(output/'browser-profile'));opts.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=opts,service=Service(driver_binary) if driver_binary else Service())
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,60)
        ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def target(browser):
            for node in browser.find_elements(By.CSS_SELECTOR,'.file-name'):
                if node.is_displayed() and browser.execute_script('''
                    const tree=window.pgAdmin.Browser.tree;
                    const data=tree.itemData(tree.itemFrom(arguments[0].closest('.file-entry')));
                    return data?._type==='server' && String(data._id ?? data.id)===String(arguments[1]);
                ''',node,server_id):return node
            return None
        item=wait.until(target)
        ActionChains(driver).context_click(item).perform()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="menuitem"]')
            if node.is_displayed() and node.text.strip()=='Backup'),None)).click()
        menu=wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="menuitem"]')
            if node.is_displayed() and 'MySQL local physical clone' in node.text),None));menu.click()
        def click(text):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip()==text:
                        browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node)
                        if node.is_displayed():node.click();return True
                return False
            wait.until(attempt)
        path=parent+'/browser-'+secrets.token_hex(8)
        for label in ('Destination on database-server host','Confirm exact destination'):
            field_label=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[normalize-space()="'+label+'"]'))
            field=driver.find_element(By.ID,field_label.get_attribute('for'));driver.execute_script('arguments[0].scrollIntoView();',field);field.send_keys(path)
        click('Review local clone');click('Confirm and start local clone')
        def completed(browser):
            for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]'):
                if 'Native clone completion observed' in node.get_attribute('textContent'):
                    browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node)
                    return 'Native clone completion observed' in node.text
            return False
        wait.until(completed);driver.save_screenshot(str(output/'native-mysql-clone.png'))
        errors=[value for value in driver.get_log('browser') if value.get('level')=='SEVERE']
        (output/'browser-console.json').write_text(json.dumps(errors,indent=2)+'\n');assert not errors
        return {'complete':True,'console_errors':0,'server_context_menu':True,'reviewed_native_clone':True}
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
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');args=parser.parse_args()
    qualify(args.evidence,browser_binary=args.browser_binary,driver_binary=args.driver_binary)
