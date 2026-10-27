"""Owned MySQL full-instance backup, file delivery and reply-loss recovery."""
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
    from pgadmin.cdeadmin.providers.mysql_family import mysql_instance_dumps as native
    from pgadmin.cdeadmin.workspace import mysql_instance_backup_jobs as worker
    from mysql_qualification_support import server,_root_connection
    client=app.test_client();service=service_for_app(app);fixture=None
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/mysql_instance_dumps.py',
        'web/pgadmin/cdeadmin/providers/relational_admin.py',
        *('web/pgadmin/cdeadmin/workspace/'+name for name in ('mysql_instance_backup_jobs.py','mysql_instance_backup_service.py','mysql_backup_protection.py','mysql_recovery_chains.py','mysql_binlog_service.py','service.py')),
        'web/pgadmin/browser/server_groups/servers/__init__.py','web/pgadmin/cdeadmin/context_menu.py',
        'web/pgadmin/static/js/Dialogs/MySQLInstanceBackups.jsx','tools/cdeadmin_mysql_instance_backup_qualification.py']
    proof={'complete':False,'full_mysql_product_complete':False,'history_testing':'not run','use_c':use_c,'checks':[],
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    password='true'  # Valid native password must not corrupt protocol booleans during masking.
    try:
        with server(output/'fixture') as (route,_name,fixture):
            root=_root_connection('mysql',route['port']);root.autocommit=True;q=root.cursor()
            try:
                q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                for schema in ('sr_instance_a','sr_instance_b'):
                    q.execute('CREATE DATABASE '+schema+' CHARACTER SET utf8mb4')
                    q.execute('CREATE TABLE '+schema+'.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
                    q.execute('INSERT INTO '+schema+'.t VALUES(%s,%s,%s)',(9007199254740993,'native 雪',b'\x00\xff'))
                q.execute('CREATE VIEW sr_instance_a.v AS SELECT id FROM sr_instance_b.t')
                q.execute('CREATE PROCEDURE sr_instance_a.p() SELECT 1')
                q.execute("CREATE ROLE 'sr_instance_role'@'%'")
                q.execute("CREATE USER 'sr_instance_user'@'%' IDENTIFIED BY %s",(password,))
                q.execute("GRANT SELECT ON sr_instance_a.* TO 'sr_instance_role'@'%'")
                q.execute("GRANT 'sr_instance_role'@'%' TO 'sr_instance_user'@'%'")
                q.execute("CREATE USER 'sr_instance_denied'@'%' IDENTIFIED BY %s",(password,))
                q.execute("GRANT SELECT ON performance_schema.* TO 'sr_instance_denied'@'%'")
                with app.test_request_context('/'):
                    uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
                    def register(label,user):
                        item=Server(user_id=uid,servergroup_id=group.id,name=label,host=route['host'],port=route['port'],username=user,maintenance_db=None,save_password=0)
                        item._cde_endpoint_registration=registration_profile('mysql-native')
                        item._cde_endpoint_route_configuration={**route,'user':user,'use_pure':not use_c,'credential_kinds':['database_password']}
                        db.session.add(item);db.session.commit()
                        return item.id,url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id),url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id),item.endpoint_profile.id
                    sid,verify,url,endpoint=register('Owned native full-instance backups','root')
                    _denied_sid,denied_verify,denied_url,_denied_endpoint=register('Owned denied backup actor','sr_instance_denied')
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                for verify_url in (verify,denied_verify):assert client.post(verify_url,json={'password':password}).get_json()['success']
                with app.app_context():
                    context,_payload,_root=service.endpoint_service.workspace(db.session.get(Server,sid),database_target_id=None)
                    db_client=service.endpoint_service.provider_registry.resolve(context).instance.client
                original_connect=db_client._connect;classes=[]
                def connect(*args,**kwargs):
                    handle=original_connect(*args,**kwargs);classes.append(type(handle).__name__);return handle
                db_client._connect=connect
                def http(action,request,*,target=url,refused=False,prefix='mysql_instance_backup_'):
                    response=client.post(target,json={'action':prefix+action,'request':request});value=response.get_json()
                    if refused:
                        assert response.status_code==400,value
                        return value
                    if response.status_code!=200 or not value.get('success'):
                        (output/'http-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                        raise AssertionError('Native instance backup API failed: '+action)
                    return value['data']
                selected={'users':True,'checksum':True,'consistent':True,'threads':1,'timeout_seconds':120}
                def review(target=url):return http('review',{'options':selected},target=target)
                def start(planned,target=url):return http('start',{key:planned[key] for key in ('job_id','review_digest')}|{'confirmed':True},target=target)
                def wait(value,target=url):
                    deadline=time.monotonic()+180
                    while value['state'] in {'dispatching','active','cancel_requested'}:
                        if time.monotonic()>deadline:raise TimeoutError('Owned instance backup deadline')
                        time.sleep(.05);value=http('status',{'job_id':value['job_id']},target=target)
                    return value
                q.execute("SET @instance_backup_guard='native'");q.execute('UPDATE sr_instance_a.t SET body=CONCAT(body,"!")')
                completed=wait(start(review()))
                assert completed['state']=='completed' and completed['native_dump_acknowledged'],completed
                q.execute('SELECT ROW_COUNT(),@instance_backup_guard');assert q.fetchone()==(1,'native')
                artifact=completed['result']['artifact'];assert {row['schema'] for row in artifact['schemas']}=={'sr_instance_a','sr_instance_b'}
                assert "'sr_instance_role'@'%'" in artifact['users'] and "'sr_instance_user'@'%'" in artifact['users']
                assert next(row for row in artifact['schemas'] if row['schema']=='sr_instance_a')['objects']['procedures']==['p']
                assert not completed['data_recovery_verified'] and artifact['native_checksums_included']
                listed=http('files',{'job_id':completed['job_id']});accounts=next(row for row in listed['files'] if row['path']=='@.users.sql')
                delivered=client.post(url,data={'action':'mysql_instance_backup_download','payload':json.dumps({'job_id':completed['job_id'],'path':accounts['path']})})
                assert delivered.status_code==200 and hashlib.sha256(delivered.data).hexdigest()==accounts['sha256'];delivered.close()
                assert http('reconcile',{'job_id':completed['job_id']})['native_dump_acknowledged']
                protection=completed['result']['archive_backup_protection'];assert protection['backup_kind']=='mysql_native_logical_instance'
                http('remove_artifact',{'job_id':completed['job_id'],'confirmation':completed['job_id']},refused=True)
                proof['checks'].append('actual-native-instance-dump-includes-two-schemas-code-accounts-roles-and-checksums-with-private-file-delivery-and-preserved-source-diagnostics')
                cancelled=review();assert http('cancel',{'job_id':cancelled['job_id']})['state']=='cancelled'
                assert start(cancelled)['state']=='cancelled'
                proof['checks'].append('cancel-before-dispatch-and-repeated-start-do-not-produce-a-new-backup')
                blocked_review=review();q.execute('LOCK TABLES sr_instance_a.t WRITE')
                try:
                    blocked=start(blocked_review);deadline=time.monotonic()+30
                    while not (blocked.get('progress') or {}).get('pid'):
                        if blocked['state'] not in {'dispatching','active'} or time.monotonic()>deadline:
                            raise AssertionError('Owned native backup did not enter its blocked utility process')
                        time.sleep(.05);blocked=http('status',{'job_id':blocked['job_id']})
                    stopped=wait(http('cancel',{'job_id':blocked['job_id']}))
                    assert stopped['state']=='cancelled' and not stopped['native_dump_acknowledged'] and stopped['native_process_termination_confirmed'],stopped
                    http('reconcile',{'job_id':blocked['job_id']},refused=True)
                finally:q.execute('UNLOCK TABLES')
                q.execute('SET SESSION lock_wait_timeout=2')
                q.execute('UPDATE sr_instance_a.t SET body=CONCAT(body,"!")')
                proof['checks'].append('active-native-utility-cancellation-confirms-process-cleanup-and-incomplete-files-are-not-adopted')
                denied=wait(start(review(denied_url),denied_url),denied_url)
                assert denied['state']=='failed' and not denied['native_dump_acknowledged'] and denied['native_error']['message'],denied
                assert password not in denied['native_error']['message']
                proof['checks'].append('native-privilege-refusal-is-visible-with-redacted-error-details-and-no-false-backup-completion')
                original_dump=native.run_dump;calls=[]
                def lost(*args,**kwargs):
                    result=original_dump(*args,**kwargs);calls.append('native-utility-returned')
                    failure=OSError('Owned suppressed native reply');failure.observation=result['tool'];failure.native_dump_acknowledged=False
                    raise failure
                native.run_dump=lost
                try:missing=wait(start(review()))
                finally:native.run_dump=original_dump
                assert len(calls)==1 and missing['state']=='failed' and not missing['native_dump_acknowledged'],missing
                accepted=http('reconcile',{'job_id':missing['job_id']})
                assert accepted['state']=='artifact_verified' and not accepted['native_dump_acknowledged'] and len(calls)==1
                assert accepted['result']['archive_backup_protection']['native_artifact_completion_observed']
                assert not accepted['result']['archive_backup_protection']['native_dump_completion_acknowledged']
                proof['checks'].append('lost-wrapper-reply-reconciles-real-native-files-without-replaying-the-utility-or-inventing-the-original-ack')
                original_seal=worker.seal
                def failed_seal(*_args,**_kwargs):raise OSError('Owned post-ack file publication failure')
                worker.seal=failed_seal
                try:unverified=wait(start(review()))
                finally:worker.seal=original_seal
                assert unverified['state']=='native_returned_unverified' and unverified['native_dump_acknowledged'],unverified
                accepted=http('reconcile',{'job_id':unverified['job_id']})
                assert accepted['state']=='artifact_verified' and accepted['native_dump_acknowledged']
                proof['checks'].append('native-ack-survives-later-file-publication-failure-and-explicit-acceptance-never-reissues-the-dump')
                original_unlink=Path.unlink
                def failed_script_unlink(path,*args,**kwargs):
                    if path.name.startswith('native-instance-dump-'):raise OSError('Owned private-script cleanup failure')
                    return original_unlink(path,*args,**kwargs)
                Path.unlink=failed_script_unlink
                try:cleanup=wait(start(review()))
                finally:Path.unlink=original_unlink
                assert cleanup['state']=='completed' and cleanup['native_dump_acknowledged'] and not cleanup['result']['private_script_cleanup']['complete']
                cleaned=http('cleanup_script',{'job_id':cleanup['job_id']})
                assert cleaned['result']['private_script_cleanup']['complete'] and cleaned['native_dump_acknowledged']
                assert http('cleanup_script',{'job_id':cleanup['job_id']})==cleaned
                proof['checks'].append('private-script-cleanup-failure-retains-the-native-ack-and-has-an-explicit-idempotent-retry')
                browser_job = None
                if binary:
                    proof['browser'] = browser(app,output,sid,binary,driver_binary)
                    browser_job = http('status',{'job_id':proof['browser']['job_id']})
                boundary=protection['native_boundary']
                q.execute('INSERT INTO sr_instance_b.t VALUES(2,"recovery edge",NULL)')
                q.execute('FLUSH BINARY LOGS')
                archive_review=http('review',{'options':{'start_file':boundary['file'],'start_position':boundary['position'],
                    'threads':1,'compression':'zstd;level=1','timeout_seconds':120}},prefix='mysql_binlog_')
                archive=http('start',{key:archive_review[key] for key in ('job_id','review_digest')}|{'confirmed':True},prefix='mysql_binlog_')
                deadline=time.monotonic()+120
                while archive['state'] in {'dispatching','active','cancel_requested'}:
                    if time.monotonic()>deadline:raise TimeoutError('Owned instance-base archive deadline')
                    time.sleep(.05);archive=http('status',{'job_id':archive['job_id']},prefix='mysql_binlog_')
                assert archive['state']=='completed',archive
                dependency=http('recovery_chain_review',{'backup_id':protection['backup_id'],'archive_job_ids':[archive['job_id']],
                    'stop_mode':'all','stop_gtid':None},prefix='mysql_binlog_')
                active=http('recovery_chain_activate',{key:dependency[key] for key in ('review_id','review_digest')}|
                    {'confirmed':True,'source_lineage_confirmed':True},prefix='mysql_binlog_')
                assert active['backup_instance_job_id']==completed['job_id'] and not active['database_recovery_verified']
                holds=http('list',{'all_registrations':True},prefix='mysql_binlog_backup_protection_')['backups']
                for hold in holds:
                    scope={'protection_endpoint_id':hold['protection_endpoint_id']}
                    reviewed=http('review_retire',{'backup_id':hold['backup_id'],**scope},prefix='mysql_binlog_backup_protection_')
                    http('retire',{key:reviewed[key] for key in ('review_id','review_digest')}|{'confirmed':True,**scope},prefix='mysql_binlog_backup_protection_')
                http('remove_artifact',{'job_id':completed['job_id'],'confirmation':completed['job_id']},refused=True)
                http('remove_artifact',{'job_id':archive['job_id'],'confirmation':archive['job_id']},prefix='mysql_binlog_',refused=True)
                dependency=http('recovery_chain_review_retire',{'chain_id':active['chain_id']},prefix='mysql_binlog_')
                http('recovery_chain_retire',{key:dependency[key] for key in ('review_id','review_digest')}|{'confirmed':True},prefix='mysql_binlog_')
                assert http('remove_artifact',{'job_id':archive['job_id'],'confirmation':archive['job_id']},prefix='mysql_binlog_')['artifact_removed']
                proof['checks'].append('native-instance-base-and-shell-archive-dependency-retain-both-exact-inputs-after-broad-hold-retirement-until-chain-retirement')
                for item in (completed,missing,unverified,cleanup)+((browser_job,) if browser_job else ()):
                    assert http('remove_artifact',{'job_id':item['job_id'],'confirmation':item['job_id']})['artifact_removed']
                proof['checks'].append('separate-reviewed-protection-retirement-and-file-removal-preserve-backup-receipts')
                proof['native_connection_classes']=sorted(set(classes))
                assert proof['native_connection_classes']==[('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')]
                proof['complete']=True
            finally:q.close();root.close()
    finally:
        if fixture is not None:proof['owned_server_stopped']=fixture['owned_server_stopped']
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def browser(app,output,sid,binary,driver_binary):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver import ActionChains
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
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
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        ActionChains(driver).context_click(wait.until(target)).perform()
        wait.until(lambda b:next((node for node in b.find_elements(By.CSS_SELECTOR,'[role="menuitem"]') if node.is_displayed() and node.text.strip()=='Backup'),None)).click()
        wait.until(lambda b:next((node for node in b.find_elements(By.CSS_SELECTOR,'[role="menuitem"]') if node.is_displayed() and node.text.strip()=='MySQL full-instance backups...'),None)).click()
        def click(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip()==label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
                        if node.is_displayed():node.click();return True
                return False
            wait.until(attempt)
        click('Review full-instance backup')
        wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'[aria-label="Instance backup review"]'))
        click('Confirm and start instance backup')
        def completed(browser):
            for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]'):
                value=node.get_attribute('textContent')
                if 'Instance backup ' in value and ': completed.' in value and 'acknowledged: yes' in value:return value
            return None
        status=wait.until(completed)
        import re
        job_id=re.search(r'Instance backup ([0-9a-f-]{36}):',status)[1]
        click('Verify instance backup files')
        wait.until(lambda b:any(': artifact_verified.' in node.get_attribute('textContent') and 'acknowledged: yes' in node.get_attribute('textContent') for node in b.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        click('Load instance backup files')
        wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'[aria-label="Verified instance backup files"]'))
        assert '@.users.sql' in driver.find_element(By.CSS_SELECTOR,'[aria-label="Verified instance backup files"]').get_attribute('textContent')
        driver.save_screenshot(str(output/'native-instance-backup.png'))
        errors=[entry for entry in driver.get_log('browser') if entry['level']=='SEVERE'];assert not errors,errors
        return {'complete':True,'job_id':job_id,'version':driver.capabilities['browserVersion'],'console_errors':errors,
                'checks':['native-server-context-action','review-and-explicit-dispatch','native-dump-completion-and-independent-file-verification','account-artifact-file-inventory']}
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
    args=parser.parse_args();value=qualify(args.output,args.mysql_shell,args.use_c,args.browser_binary,args.driver_binary);print(json.dumps({'complete':value['complete'],'checks':len(value['checks'])}))
