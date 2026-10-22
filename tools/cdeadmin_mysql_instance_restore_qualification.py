"""Owned two-instance native restore, log continuation and uncertain outcomes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,shell,use_c=False,binary=None,driver_binary=None):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep native evidence outside source')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    os.environ['CDEADMIN_MYSQLSH_BINARY']=str(Path(shell).resolve(strict=True))
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app=setup_application(output)
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from pgadmin.cdeadmin.workspace.mysql_instance_restore_jobs import InstanceRestoreTransport
    from mysql_qualification_support import server,_root_connection
    client=app.test_client();service=service_for_app(app);fixtures=[]
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_instance_restores.py','mysql_instance_dumps.py','mysql_binlog_archives.py')]
    paths+=['web/pgadmin/cdeadmin/workspace/'+name for name in ('mysql_instance_restore_jobs.py','mysql_instance_restore_service.py','mysql_binlog_replay_jobs.py','service.py')]
    paths+=['web/pgadmin/browser/server_groups/servers/__init__.py','web/pgadmin/cdeadmin/context_menu.py',
        'web/pgadmin/static/js/Dialogs/MySQLInstanceRestores.jsx','tools/cdeadmin_mysql_instance_restore_qualification.py']
    proof={'complete':False,'full_mysql_product_complete':False,'history_testing':'not run','use_c':use_c,'checks':[],
        'source_sha256':{path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in paths}}
    password='true'
    try:
        with server(output/'source-fixture') as (source,_source_name,sfixture),server(output/'target-fixture',server_id=102) as (target,_target_name,tfixture):
            fixtures.extend([sfixture,tfixture]);handles=[];cursors=[]
            try:
                for route in (source,target):
                    handle=_root_connection('mysql',route['port']);handle.autocommit=True;handles.append(handle);q=handle.cursor();cursors.append(q)
                    q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                qs,qt=cursors
                for schema in ('sr_restored_a','sr_restored_b'):
                    qs.execute('CREATE DATABASE '+schema+' CHARACTER SET utf8mb4')
                    qs.execute('CREATE TABLE '+schema+'.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
                    qs.execute('INSERT INTO '+schema+'.t VALUES(%s,%s,%s)',(9007199254740993,'native 雪',b'\x00\xff'))
                qs.execute('CREATE VIEW sr_restored_a.v AS SELECT id FROM sr_restored_b.t')
                qs.execute('CREATE PROCEDURE sr_restored_a.p() SELECT 1')
                qs.execute("CREATE ROLE 'sr_restored_role'@'%'");qs.execute("CREATE USER 'sr_restored_user'@'%' IDENTIFIED BY %s",(password,))
                qs.execute("GRANT SELECT ON sr_restored_a.* TO 'sr_restored_role'@'%'");qs.execute("GRANT 'sr_restored_role'@'%' TO 'sr_restored_user'@'%'")
                qt.execute('SET GLOBAL local_infile=ON')
                qt.execute("CREATE USER 'sr_restore_denied'@'%' IDENTIFIED BY %s",(password,));qt.execute("GRANT SELECT ON performance_schema.* TO 'sr_restore_denied'@'%'")
                with app.test_request_context('/'):
                    uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
                    def register(label,route,user='root'):
                        item=Server(user_id=uid,servergroup_id=group.id,name=label,host=route['host'],port=route['port'],username=user,maintenance_db=None,save_password=0)
                        item._cde_endpoint_registration=registration_profile('mysql-native')
                        item._cde_endpoint_route_configuration={**route,'user':user,'use_pure':not use_c,'credential_kinds':['database_password']}
                        db.session.add(item);db.session.commit()
                        return item.id,url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id),url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id)
                    sid,sv,surl=register('Owned instance recovery source',source)
                    tid,tv,turl=register('Owned instance recovery target',target)
                    _did,dv,durl=register('Owned denied recovery actor',target,'sr_restore_denied')
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                for endpoint in (sv,tv,dv):assert client.post(endpoint,json={'password':password}).get_json()['success']
                with app.app_context():
                    context,_payload,_root=service.endpoint_service.workspace(db.session.get(Server,tid),database_target_id=None)
                    db_client=service.endpoint_service.provider_registry.resolve(context).instance.client
                connect=db_client._connect;classes=[]
                def recorded(*args,**kwargs):
                    handle=connect(*args,**kwargs);classes.append(type(handle).__name__);return handle
                db_client._connect=recorded
                def http(action,request,*,url=turl,prefix='mysql_instance_restore_',refused=False):
                    response=client.post(url,json={'action':prefix+action,'request':request});value=response.get_json()
                    if refused:assert response.status_code==400,value;return value
                    if response.status_code!=200 or not value.get('success'):
                        (output/'http-failure.json').write_text(json.dumps(value,indent=2)+'\n');raise AssertionError('Native instance recovery API failed: '+action)
                    return value['data']
                def start(planned,**kwargs):return http('start',{key:planned[key] for key in ('job_id','review_digest')}|{'confirmed':True},**kwargs)
                def wait(value,**kwargs):
                    deadline=time.monotonic()+180
                    while value['state'] in {'dispatching','active','cancel_requested'}:
                        if time.monotonic()>deadline:raise TimeoutError('Owned native instance recovery deadline')
                        time.sleep(.05);value=http('status',{'job_id':value['job_id']},**kwargs)
                    return value
                backup=wait(start(http('review',{'options':{'users':True,'checksum':True,'threads':1}},url=surl,prefix='mysql_instance_backup_'),url=surl,prefix='mysql_instance_backup_'),url=surl,prefix='mysql_instance_backup_')
                assert backup['state']=='completed',backup
                target_uuid=http('inspect',{})['identity']['server_uuid']
                selected={'target_confirmation':target_uuid,'load_users':True,'exclude_users':['root'],
                    'checksum':True,'threads':1,'skip_binlog':True,'update_gtid_set':'append','timeout_seconds':120}
                def review(options=None,**kwargs):return http('review',{'source_server_id':sid,'backup_job_id':backup['job_id'],'options':options or selected},**kwargs)
                http('review',{'source_server_id':sid,'backup_job_id':backup['job_id'],
                    'options':{**selected,'target_confirmation':backup['source']['server_uuid']}},url=surl,refused=True)
                restored=wait(start(review()))
                assert restored['state']=='native_load_returned' and restored['native_load_outcome']=='returned',restored
                assert not restored['data_recovery_verified'] and restored['native_process_termination_confirmed']
                qt.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_restored_a.t');assert qt.fetchall()==[('9007199254740993','native 雪','00FF')]
                qt.execute('SELECT CAST(id AS CHAR) FROM sr_restored_a.v');assert qt.fetchall()==[('9007199254740993',)]
                qt.execute("SELECT User FROM mysql.user WHERE User IN ('sr_restored_user','sr_restored_role') ORDER BY User");assert qt.fetchall()==[('sr_restored_role',),('sr_restored_user',)]
                qt.execute("SHOW GRANTS FOR 'sr_restored_user'@'%'");assert any('sr_restored_role' in row[0] for row in qt.fetchall())
                for q in (qs,qt):q.execute('SHOW CREATE PROCEDURE sr_restored_a.p')
                assert qs.fetchone()[2]==qt.fetchone()[2]
                boundary=backup['result']['artifact']['native_boundary']
                qt.execute('SELECT GTID_SUBSET(%s,@@GLOBAL.gtid_executed)',(boundary['gtidExecuted'],));assert qt.fetchone()==(1,)
                assert start({'job_id':restored['job_id'],'review_digest':restored['review_digest']})['native_load_outcome']=='returned'
                proof['checks'].append('native-instance-load-restores-two-schemas-wide-unicode-blob-cross-schema-view-procedure-accounts-and-roles-with-reviewed-native-GTID-base-installation')
                qs.execute('INSERT INTO sr_restored_b.t VALUES(2,"after backup",NULL)');qs.execute('FLUSH BINARY LOGS')
                archived=wait(start(http('review',{'options':{'start_file':boundary['file'],'start_position':boundary['position'],'threads':1,'timeout_seconds':120}},url=surl,prefix='mysql_binlog_'),url=surl,prefix='mysql_binlog_'),url=surl,prefix='mysql_binlog_')
                assert archived['state']=='completed'
                replay=wait(start(http('review',{'source_server_id':sid,'archive_job_id':archived['job_id'],
                    'options':{'target_confirmation':target_uuid}},prefix='mysql_binlog_replay_'),prefix='mysql_binlog_replay_'),prefix='mysql_binlog_replay_')
                assert replay['state']=='native_load_returned',replay
                qt.execute('SELECT COUNT(*) FROM sr_restored_b.t');assert qt.fetchone()==(2,)
                proof['checks'].append('actual-application-instance-base-to-native-log-continuation-restores-later-source-row-on-separate-target')
                cancelled=review({**selected,'load_users':False,'exclude_users':[],'update_gtid_set':'off','drop_existing_objects':True})
                assert http('cancel',{'job_id':cancelled['job_id']})['state']=='cancelled' and start(cancelled)['state']=='cancelled'
                proof['checks'].append('cancelled-review-and-repeated-dispatch-never-reissue-a-native-load')
                plain={**selected,'load_users':False,'update_gtid_set':'off','drop_existing_objects':True};plain.pop('exclude_users')
                original=InstanceRestoreTransport.execute
                def post_ack(*args,**kwargs):
                    result=original(*args,**kwargs);failure=OSError('Owned suppressed post-ack wrapper reply');failure.control=result['control'];failure.observation=result['tool'];raise failure
                InstanceRestoreTransport.execute=post_ack
                try:failed=wait(start(review(plain)))
                finally:InstanceRestoreTransport.execute=original
                assert failed['state']=='native_returned_unverified' and failed['native_load_outcome']=='returned',failed
                assert http('reconcile',{'job_id':failed['job_id']})['native_load_outcome']=='returned'
                qt.execute('SELECT COUNT(*) FROM sr_restored_b.t');assert qt.fetchone()==(1,)
                proof['checks'].append('real-native-load-ack-survives-later-wrapper-failure-and-observer-reconciliation-never-reissues-the-restore')
                def lost(*args,**kwargs):
                    result=original(*args,**kwargs);failure=OSError('Owned lost native reply');failure.observation=result['tool'];raise failure
                InstanceRestoreTransport.execute=lost
                try:uncertain=wait(start(review(plain)))
                finally:InstanceRestoreTransport.execute=original
                assert uncertain['state']=='unknown' and uncertain['native_load_outcome']=='unknown',uncertain
                observed=http('reconcile',{'job_id':uncertain['job_id']});assert observed['reconciliation']['native_lock_free']
                acknowledged=http('acknowledge',{'job_id':uncertain['job_id'],'target_confirmation':target_uuid,'observation_digest':observed['observation_digest']})
                assert acknowledged['native_load_outcome']=='unknown' and start(uncertain)['state']=='unknown'
                proof['checks'].append('lost-native-reply-keeps-unknown-outcome-and-target-fence-until-explicit-current-state-acknowledgement-without-replay')
                denied=wait(start(review(plain,url=durl),url=durl),url=durl)
                assert denied['state']=='unknown' and denied['native_error']['message'] and denied['native_load_outcome']=='unknown',denied
                assert password not in denied['native_error']['message']
                observed=http('reconcile',{'job_id':denied['job_id']},url=durl)
                http('acknowledge',{'job_id':denied['job_id'],'target_confirmation':target_uuid,'observation_digest':observed['observation_digest']},url=durl)
                proof['checks'].append('actual-native-privilege-refusal-exposes-redacted-error-and-retains-partial-effect-uncertainty-until-reviewed-target-acknowledgement')
                planned=review(plain);qt.execute('LOCK TABLES sr_restored_b.t WRITE')
                try:
                    blocked=start(planned);deadline=time.monotonic()+30
                    while blocked.get('phase')!='native_dispatch' or (blocked.get('progress') or {}).get('elapsed_seconds',0)<.5:
                        if blocked['state'] not in {'dispatching','active'} or time.monotonic()>deadline:
                            raise AssertionError('Owned native instance load did not enter its blocked utility')
                        time.sleep(.05);blocked=http('status',{'job_id':blocked['job_id']})
                    cancelled=wait(http('cancel',{'job_id':blocked['job_id']}))
                    assert cancelled['state']=='unknown' and cancelled['native_load_outcome']=='unknown' and cancelled['native_process_termination_confirmed'],cancelled
                finally:qt.execute('UNLOCK TABLES')
                deadline=time.monotonic()+30
                observed=http('reconcile',{'job_id':cancelled['job_id']})
                while not observed['reconciliation']['native_lock_free']:
                    if time.monotonic()>deadline:raise TimeoutError('Owned cancelled native restore still holds its target lock')
                    time.sleep(.1);observed=http('reconcile',{'job_id':cancelled['job_id']})
                accepted=http('acknowledge',{'job_id':cancelled['job_id'],'target_confirmation':target_uuid,'observation_digest':observed['observation_digest']})
                assert accepted['native_load_outcome']=='unknown'
                proof['checks'].append('active-native-load-cancellation-confirms-local-process-cleanup-and-requires-released-native-lock-and-explicit-target-acknowledgement-without-inferred-rollback')
                if binary:proof['browser']=browser(app,output,tid,backup['job_id'],target_uuid,binary,driver_binary)
                proof['native_connection_classes']=sorted(set(classes));assert proof['native_connection_classes']==[('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')]
                proof['complete']=True
            finally:
                for q in cursors:q.close()
                for handle in handles:handle.close()
    finally:
        proof['owned_servers_stopped']=[fixture['owned_server_stopped'] for fixture in fixtures]
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def browser(app,output,tid,backup_id,target_uuid,binary,driver_binary):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver import ActionChains
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1200'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,120);ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def target(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,tid)),None)
        ActionChains(driver).context_click(wait.until(target)).perform()
        wait.until(lambda b:next((node for node in b.find_elements(By.CSS_SELECTOR,'[role="menuitem"]') if node.is_displayed() and node.text.strip()=='Restore'),None)).click()
        wait.until(lambda b:next((node for node in b.find_elements(By.CSS_SELECTOR,'[role="menuitem"]') if node.is_displayed() and 'MySQL full-instance restores' in node.text),None)).click()
        def click(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip()==label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
                        if node.is_displayed():node.click();return True
                return False
            wait.until(attempt)
        click('Inspect instance restore target');wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,'[aria-label="Native instance restore target"]'))
        click('Load instance backup sources');click('Use backup source Owned instance recovery source');click('Load source instance backups');click('Use instance backup '+backup_id)
        confirmation=driver.find_element(By.XPATH,'//label[contains(text(),"Confirm native restore target UUID")]/following::input[1]')
        confirmation.send_keys(target_uuid)
        editor=driver.find_element(By.XPATH,'//label[contains(text(),"Native instance restore options")]/following::textarea[1]')
        selected=json.dumps({'load_users':False,'checksum':True,'threads':1,'drop_existing_objects':True,'skip_binlog':True,'update_gtid_set':'off','timeout_seconds':120})
        editor.send_keys(Keys.CONTROL,'a');editor.send_keys(Keys.BACKSPACE);editor.send_keys(selected)
        wait.until(lambda _browser:editor.get_attribute('value')==selected)
        click('Review full-instance restore');wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,'[aria-label="Instance restore review"]'))
        click('Confirm and start instance restore')
        wait.until(lambda b:any(': native_load_returned.' in node.get_attribute('textContent') and 'outcome: returned.' in node.get_attribute('textContent') for node in b.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        click('Observe instance restore target')
        wait.until(lambda b:any('native_lock_free' in node.get_attribute('textContent') for node in b.find_elements(By.TAG_NAME,'pre')))
        driver.save_screenshot(str(output/'native-instance-restore.png'))
        errors=[entry for entry in driver.get_log('browser') if entry['level']=='SEVERE'];assert not errors,errors
        return {'complete':True,'version':driver.capabilities['browserVersion'],'console_errors':errors,
            'checks':['native-target-context-action','owned-source-and-backup-selection-with-exact-target-confirmation','review-and-explicit-native-instance-load','separate-target-observation-preserves-original-native-outcome']}
    except Exception:
        if driver:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--mysql-shell',required=True);parser.add_argument('--use-c',action='store_true')
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();proof=qualify(args.output,args.mysql_shell,args.use_c,args.browser_binary,args.driver_binary);print(json.dumps({'complete':proof['complete'],'checks':len(proof['checks'])}))
