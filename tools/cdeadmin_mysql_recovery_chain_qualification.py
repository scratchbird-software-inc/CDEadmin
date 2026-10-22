"""Owned native Shell recovery dependencies, registration aliases and retention."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,shell,use_c=False,binary=None,driver_binary=None):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep owned evidence outside source')
    output.mkdir(parents=True,exist_ok=False)
    os.environ['CDEADMIN_MYSQLSH_BINARY']=str(Path(shell).resolve(strict=True))
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app=setup_application(output)
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.workspace.mysql_backup_protection import Registry
    client=app.test_client();service=service_for_app(app);fixture=None
    paths=['web/pgadmin/cdeadmin/workspace/'+name for name in ('mysql_recovery_chains.py','mysql_backup_protection.py','mysql_binlog_service.py')]
    paths+=['web/pgadmin/browser/server_groups/servers/__init__.py',
            'web/pgadmin/static/js/Dialogs/MySQLRecoveryChains.jsx','web/pgadmin/static/js/Dialogs/MySQLBackupProtection.jsx',
            'tools/cdeadmin_mysql_recovery_chain_qualification.py']
    proof={'complete':False,'full_mysql_product_complete':False,'history_testing':'not run','use_c':use_c,
           'checks':[],'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    password='NativeChainA1!'+secrets.token_urlsafe(24)
    try:
        with server(output/'fixture') as (route,_name,fixture):
            native=_root_connection('mysql',route['port']);native.autocommit=True;q=native.cursor()
            try:
                q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                q.execute('CREATE DATABASE sr_chain');q.execute('CREATE TABLE sr_chain.t(id INT PRIMARY KEY)')
                q.execute('INSERT INTO sr_chain.t VALUES(1)')
                (output/'backups').mkdir()
                with app.test_request_context('/'):
                    uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
                    def register(label):
                        item=Server(user_id=uid,servergroup_id=group.id,name=label,host=route['host'],port=route['port'],username='root',maintenance_db=None,save_password=0)
                        item._cde_endpoint_registration=registration_profile('mysql-native')
                        item._cde_endpoint_route_configuration={**route,'user':'root','use_pure':not use_c,'credential_kinds':['database_password'],'tool_workspace':str(output/'backups')}
                        db.session.add(item);db.session.commit()
                        return item.id,url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id),url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id),item.endpoint_profile.id
                    sid,verify,url,endpoint=register('Owned native recovery chains')
                    _alias_sid,alias_verify,alias_url,alias_endpoint=register('Owned same-instance alias')
                    database_target=str(uuid.uuid4())
                    db.session.add(EndpointDatabaseTarget(id=database_target,endpoint_id=endpoint,display_name='sr_chain',database='sr_chain',configuration='{}',active=1));db.session.commit()
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                for verify_url in (verify,alias_verify):assert client.post(verify_url,json={'password':password}).get_json()['success']
                with app.app_context():
                    registered=db.session.get(Server,sid)
                    context,_payload,_root=service.endpoint_service.workspace(registered,database_target_id=None)
                    native_client=service.endpoint_service.provider_registry.resolve(context).instance.client
                original_connect=native_client._connect;connection_classes=[]
                def recorded_connect(*args,**kwargs):
                    handle=original_connect(*args,**kwargs);connection_classes.append(type(handle).__name__);return handle
                native_client._connect=recorded_connect
                def http(action,request,*,target=url,refused=False):
                    response=client.post(target,json={'action':'mysql_binlog_'+action,'request':request});value=response.get_json()
                    if refused:
                        assert response.status_code==400,value
                        return value
                    if response.status_code!=200 or not value.get('success'):
                        (output/'http-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                        raise AssertionError('Native recovery HTTP failed: '+action)
                    return value['data']
                def confirm(review):return {key:review[key] for key in ('review_id','review_digest')}|{'confirmed':True}
                def archive(options,target=url):
                    review=http('review',{'options':{**options,'threads':1,'compression':'zstd;level=1','timeout_seconds':120}},target=target)
                    value=http('start',{key:review[key] for key in ('job_id','review_digest')}|{'confirmed':True},target=target)
                    deadline=time.monotonic()+120
                    while value['state'] in {'dispatching','active','cancel_requested'}:
                        if time.monotonic()>deadline:raise TimeoutError('Owned native archive deadline')
                        time.sleep(.05);value=http('status',{'job_id':value['job_id']},target=target)
                    assert value['state']=='completed',value
                    return value
                q.execute('FLUSH BINARY LOGS');q.execute('SHOW BINARY LOG STATUS');start=q.fetchone()
                old=archive({'start_file':start[0],'start_position':'4'})
                alias_old=archive({'start_file':start[0],'start_position':'4'},target=alias_url)
                request={'database_target_id':database_target,'resource_kind':'database','operation_id':'backup_logical',
                    'target_resource':{'resource_kind':'database','display_name':'sr_chain','display_path':['sr_chain']},
                    'draft':{'path':'managed-base','checksum':True,'threads':1,'show_progress':False}}
                planned=client.post(url,json={'action':'visual_admin_plan','request':request}).get_json()
                assert planned['success'] and planned['data']['state']=='ready',planned
                reply=client.post(url,json={'action':'visual_admin_apply','request':{'database_target_id':database_target,
                    **{key:planned['data'][key] for key in ('plan_id','plan_digest')},'confirmed':True}}).get_json()
                assert reply['success'],reply
                backup=reply['data']['provider_result']['driver_observation']['archive_backup_protection']
                assert backup['state']=='native_dump_returned' and backup['native_consistent'] and not backup['native_gtid_snapshot_inconsistent']
                boundary=backup['native_boundary']
                q.execute('INSERT INTO sr_chain.t VALUES(2)');q.execute('FLUSH BINARY LOGS')
                first=archive({'start_file':boundary['file'],'start_position':boundary['position']})
                q.execute('SELECT @@GLOBAL.gtid_executed');before=q.fetchone()[0]
                q.execute("SET SESSION gtid_next='AUTOMATIC:recovery_chain'")
                q.execute('INSERT INTO sr_chain.t VALUES(3)');q.execute("SET SESSION gtid_next='AUTOMATIC'")
                q.execute('SELECT GTID_SUBTRACT(@@GLOBAL.gtid_executed,%s)',(before,));stop=q.fetchone()[0]
                assert ':recovery_chain:' in stop
                q.execute('FLUSH BINARY LOGS');second=archive({'since_job_id':first['job_id']})
                selected={'backup_id':backup['backup_id'],'archive_job_ids':[first['job_id'],second['job_id']],'stop_mode':'after','stop_gtid':stop}
                http('recovery_chain_review',{**selected,'archive_job_ids':[second['job_id']]},refused=True)
                http('recovery_chain_review',selected,target=alias_url,refused=True)
                review=http('recovery_chain_review',selected)
                assert len(review['inputs']['coverage']['archive_edges'])==2 and not review['inputs']['database_recovery_verified']
                q.execute('SELECT GTID_SUBSET(%s,%s)',(stop,review['inputs']['coverage']['all_selected_archive_gtids']));assert q.fetchone()==(1,)
                http('recovery_chain_activate',confirm(review)|{'source_lineage_confirmed':False},refused=True)
                active=http('recovery_chain_activate',confirm(review)|{'source_lineage_confirmed':True})
                assert active['state']=='active' and not active['native_log_generation_attested'] and not active['blanket_backup_hold_retirement_issued']
                assert http('recovery_chain_activate',confirm(review)|{'source_lineage_confirmed':True})==active
                proof['checks'].append('native-checksummed-base-and-two-archives-with-tagged-GTID-gap-refusal-and-reviewed-idempotent-protection')
                http('remove_artifact',{'job_id':alias_old['job_id'],'confirmation':alias_old['job_id']},target=alias_url,refused=True)
                all_holds=http('backup_protection_list',{'all_registrations':True},target=alias_url)
                assert any(row['backup_id']==backup['backup_id'] and row['protection_endpoint_id']==endpoint for row in all_holds['backups'])
                retire=http('backup_protection_review_retire',{'backup_id':backup['backup_id'],'protection_endpoint_id':endpoint},target=alias_url)
                http('backup_protection_retire',confirm(retire)|{'protection_endpoint_id':endpoint},target=alias_url)
                for item in (first,second):http('remove_artifact',{'job_id':item['job_id'],'confirmation':item['job_id']},refused=True)
                for item,target_url in ((old,url),(alias_old,alias_url)):
                    assert http('remove_artifact',{'job_id':item['job_id'],'confirmation':item['job_id']},target=target_url)['artifact_removed']
                proof['checks'].append('same-owner-alias-hold-inspection-scoped-retirement-and-unneeded-archive-release-with-chain-edges-retained')
                restarted=Registry(service.mysql_backup_protection.root)
                with expect_protection_refusal():
                    with restarted.guard(uid,endpoint,{'job_id':first['job_id'],'operation':first['operation'],'endpoint_id':endpoint,'source':first['source']}):pass
                chain_retire=http('recovery_chain_review_retire',{'chain_id':active['chain_id']})
                assert http('recovery_chain_retire',confirm(chain_retire))['state']=='retired'
                assert http('recovery_chain_retire',confirm(chain_retire))['state']=='retired'
                review=http('recovery_chain_review',selected)
                jobs=service.mysql_binlog_jobs;raw=jobs.load(first['job_id'],uid,endpoint)
                extra=jobs.directory(raw)/'archive/owned-unexpected-file';extra.write_text('owned mutation')
                try:http('recovery_chain_activate',confirm(review)|{'source_lineage_confirmed':True},refused=True)
                finally:extra.unlink()
                proof['checks'].append('restart-keeps-exact-dependencies-and-changed-archive-is-refused-before-protection-activation')
                proof['native_connection_classes']=sorted(set(connection_classes))
                assert proof['native_connection_classes']==[('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')]
                if binary:proof['browser']=browser(app,output,sid,binary,driver_binary,backup['backup_id'],[first['job_id'],second['job_id']])
                q.execute('RESET BINARY LOGS AND GTIDS')
                http('recovery_chain_review',selected,refused=True)
                proof['checks'].append('actual-native-GTID-reset-refuses-old-chain-despite-unchanged-server-UUID')
                for item in (first,second):assert http('remove_artifact',{'job_id':item['job_id'],'confirmation':item['job_id']})['artifact_removed']
                q.execute('SELECT COUNT(*) FROM sr_chain.t');assert q.fetchone()==(3,)
                proof['checks'].append('separate-chain-retirement-permits-removal-without-replaying-backup-or-user-data')
                proof['complete']=True
            finally:q.close();native.close()
    finally:
        if fixture is not None:proof['owned_server_stopped']=fixture['owned_server_stopped']
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def expect_protection_refusal():
    from contextlib import contextmanager
    from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
    @contextmanager
    def check():
        try:yield
        except BinlogArchiveError:return
        raise AssertionError('Expected owned archive protection refusal')
    return check()


def browser(app,output,sid,binary,driver_binary,backup_id,archive_ids):
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
        wait=WebDriverWait(driver,90);ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def target(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        ActionChains(driver).context_click(wait.until(target)).perform()
        wait.until(lambda b:next((n for n in b.find_elements(By.CSS_SELECTOR,'[role="menuitem"]') if n.is_displayed() and n.text.strip()=='Backup'),None)).click()
        wait.until(lambda b:next((n for n in b.find_elements(By.CSS_SELECTOR,'[role="menuitem"]') if n.is_displayed() and 'MySQL raw' in n.text),None)).click()
        def click(label,tag='button'):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,tag):
                    if node.is_enabled() and node.get_attribute('textContent').strip()==label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
                        if node.is_displayed():node.click();return True
                return False
            wait.until(attempt)
        for label in ('Archive retention','Managed backup protection','Recovery chain dependencies'):click(label,'summary')
        click('Load recovery base backups');click('Use backup '+backup_id)
        click('Load recovery chain archives')
        for archive in archive_ids:click('Append archive '+archive)
        click('Review recovery dependencies')
        wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'[aria-label="Recovery dependency review"]'))
        protect=wait.until(lambda b:next((n for n in b.find_elements(By.TAG_NAME,'button') if n.get_attribute('textContent').strip()=='Protect reviewed recovery chain'),None))
        assert not protect.is_enabled()
        node=driver.find_element(By.XPATH,'//label[contains(normalize-space(),"I confirm these inputs belong")]//input');driver.execute_script('arguments[0].click()',node)
        click('Protect reviewed recovery chain')
        wait.until(lambda b:any('Its selected archives are protected.' in n.text for n in b.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        click('Load recovery chains')
        retirement=wait.until(lambda b:next((n.get_attribute('textContent').strip() for n in b.find_elements(By.TAG_NAME,'button') if n.is_enabled() and n.get_attribute('textContent').strip().startswith('Review retirement of chain ')),None))
        click(retirement)
        wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'[aria-label="Recovery dependency retirement"]'))
        node=driver.find_element(By.XPATH,'//label[contains(normalize-space(),"Release this recovery chain")]//input');driver.execute_script('arguments[0].click()',node)
        click('Confirm recovery chain retirement')
        wait.until(lambda b:not b.find_elements(By.CSS_SELECTOR,'[aria-label="Recovery dependency retirement"]'))
        driver.save_screenshot(str(output/'native-recovery-chain.png'))
        errors=[entry for entry in driver.get_log('browser') if entry['level']=='SEVERE'];assert not errors,errors
        return {'complete':True,'version':driver.capabilities['browserVersion'],'console_errors':errors,'checks':['native-input-selection','native-dependency-review','lineage-confirmed-protection','reviewed-chain-retirement']}
    except Exception:
        if driver:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--mysql-shell',required=True)
    parser.add_argument('--use-c',action='store_true');parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();value=qualify(args.output,args.mysql_shell,args.use_c,args.browser_binary,args.driver_binary)
    print(json.dumps({'complete':value['complete'],'checks':len(value['checks'])}))
