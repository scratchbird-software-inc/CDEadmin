"""Real native recurring expected-checkpoint recovery acceptance and interruption."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading
import time
from unittest.mock import patch


def qualify_checks(app,output,oracle,container,port,password,selected,credentials,binary=None,driver_binary=None):
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_recovery_connection_qualification import endpoint
    from cdeadmin_mysql_physical_replay_qualification import wait_job,start_request
    from pgadmin.cdeadmin.workspace.mysql_physical_check_schedule import ScheduleHost
    from pgadmin.cdeadmin.providers.mysql_family import mysql_instance_acceptance as native
    from pgadmin.model import Server,db
    from flask import url_for
    root=Path(__file__).resolve().parents[1];service=app.extensions['cdeadmin_provider_workspace']
    paths=['tools/cdeadmin_mysql_physical_check_schedule_qualification.py','web/pgadmin/cdeadmin/workspace/mysql_physical_check_schedule.py',
        'web/pgadmin/cdeadmin/workspace/mysql_physical_backup_schedule.py','web/pgadmin/cdeadmin/workspace/mysql_physical_service.py',
        'web/pgadmin/cdeadmin/workspace/mysql_physical_retention.py','web/pgadmin/cdeadmin/workspace/mysql_archive_retention.py',
        'web/pgadmin/cdeadmin/workspace/mysql_physical_batch_retention.py','web/pgadmin/static/js/Dialogs/MySQLPhysicalBackupSchedule.jsx']
    proof={'complete':False,'interfaces':[],'source_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths},'history_testing':'not run'}
    for use_c in (False,True):
        sid,_,_=registration(app,{'host':'127.0.0.1','port':port},password,use_c,username='sr_physical')
        url=endpoint(app,sid)
        with app.test_request_context('/'):
            server=db.session.get(Server,sid);owner=server.user_id;name=server.name
            verification=url_for('NODE-server.verify_endpoint_id',gid=server.servergroup_id,sid=sid)
        client=app.test_client()
        with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
        def post(action,request,refused=False):
            response=client.post(url,json={'action':action,'request':request});value=response.get_json()
            if refused:assert not value.get('success'),value;return value
            assert response.status_code==200 and value.get('success'),value
            return value['data']
        physical=lambda action,request,refused=False:post('mysql_physical_'+action,request,refused)
        logical=lambda action,request,refused=False:post('mysql_instance_backup_'+action,request,refused)
        schedule=lambda action,request,refused=False:physical('check_schedule_'+action,request,refused)
        def dump():return wait_job(logical('start',start_request(logical('review',{'options':{'users':False,'checksum':True,'threads':1,'timeout_seconds':120}}))),logical,'completed')
        def phase(kind,parent=None):
            ticket=physical('review',{'options':{**selected,'phase':kind,'input_job_id':parent},'credentials':credentials})
            value=physical('start',{**start_request(ticket),'delegate_database_credentials':True,'credentials':credentials});deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                value=physical('reconcile',{'job_id':value['job_id'],'credentials':credentials})
                if value.get('remote_observation',{}).get('supervisor_finished'):
                    assert value['file_verification_confirmed'],value;return value
                time.sleep(.1)
            raise TimeoutError('Owned native recovery-check input '+kind)
        def confirm(value):return {'job_id':value['job_id'],'confirmed':True,'schedule_confirmation':value['job_id']}
        def review(backup_id):return schedule('review',{'options':{'physical':recovery,'expected_backup_job_id':backup_id,'threads':1,'interval_seconds':60,'expires_after_days':1},'credentials':credentials})
        def enable(value):return schedule('enable',{**confirm(value),'review_digest':value['review_digest'],'delegate_ssh_credentials':True,'delegate_database_credentials':True,'credentials':credentials})
        def wait(value,attention=False,previous=None):
            deadline=time.monotonic()+240
            while time.monotonic()<deadline:
                current=schedule('status',{'job_id':value['job_id']})
                if current['state']=='attention_required':
                    if attention:return current
                    (output/'check-failure.json').write_text(json.dumps(current,indent=2)+'\n')
                    raise AssertionError(current)
                if not attention and current.get('last_scan_at') and not current.get('scan_state') and current.get('last_occurrence_id')!=previous:return current
                time.sleep(.1)
            raise TimeoutError('Recurring native recovery-check occurrence')
        def occurrence(value):return schedule('occurrence',{'job_id':value['job_id'],'occurrence_id':value['last_occurrence_id']})
        expected=dump();backed=phase('backup');prepared=phase('prepare',backed['job_id']);copied=phase('copy_back',prepared['job_id'])
        recovery={**deepcopy(selected),'phase':'recover','input_job_id':copied['job_id'],'mysqld':'/usr/sbin/mysqld','recovery_gtid_mode':'ON',
            'recovery_mode':'read_only','recovery_port':0,'recovery_local_infile':True,'timeout_seconds':120}
        checks=[];host=service.mysql_check_scheduler;grant=review(expected['job_id'])
        assert not grant['ssh_delegation_present'] and not host.read(grant['job_id']).get('ssh_envelope')
        checks.append('review-binds-retained-physical-and-expected-native-snapshots-without-storing-delegation')
        oracle.autocommit=False
        try:
            with oracle.cursor() as cursor:cursor.execute('INSERT INTO sr_osc.pending VALUES(%s)',(22000+int(use_c),));cursor.execute('SAVEPOINT check_source_guard')
            enable(grant);first=wait(grant);result=occurrence(first)
            assert result['state']=='completed' and result['selected_snapshot_verified'] and result['protection_released']
            assert result['acceptance_receipt']['result']['data']['matched'] and result['acceptance_receipt']['result']['definitions']['matched']
            assert result['database_recovery_verified'] is False and result['production_cutover_verified'] is False
            logical('remove_artifact',{'job_id':expected['job_id'],'confirmation':expected['job_id']},refused=True)
            physical('retention_review',{'job_id':copied['job_id'],'credentials':credentials},refused=True)
            post('endpoint_profile_remove',{'confirmation':name},refused=True)
            with app.app_context():service.endpoint_service.forget_server_credentials(db.session.get(Server,sid))
            assert password not in json.dumps(host.read(grant['job_id'])) and 'BEGIN OPENSSH' not in json.dumps(host.read(grant['job_id']))
            assert host.close();host=service.mysql_check_scheduler=ScheduleHost(app,service)
            host.jobs.update(host.read(grant['job_id']),next_scan_at=0);host.start();second=wait(grant,previous=first['last_occurrence_id'])
            repeated=occurrence(second);assert repeated['selected_snapshot_verified'] and repeated['recovery_job_id']!=result['recovery_job_id']
            assert repeated['acceptance_receipt']['target']['server_uuid']!=result['acceptance_receipt']['target']['server_uuid']
            checks.append('background-native-private-read-only-recovery-full-count-checksum-definition-acceptance-and-stop-preserve-source-transaction-and-savepoint')
            checks.append('both-input-retention-and-registration-removal-guards-plus-idle-worker-restart-with-encrypted-SQL-after-interactive-password-erasure')
            schedule('disable',confirm(second))
            with oracle.cursor() as cursor:cursor.execute('ROLLBACK TO SAVEPOINT check_source_guard');cursor.execute('SELECT COUNT(*) FROM sr_osc.pending');assert cursor.fetchone()[0]==1
        finally:oracle.rollback();oracle.autocommit=True
        assert client.post(verification,json={'password':password}).get_json()['success']
        with oracle.cursor() as cursor:cursor.execute("UPDATE sr_osc.t SET note='different explicit checkpoint' WHERE id=18446744073709551615")
        later=dump();mismatch=review(later['job_id']);enable(mismatch);different=wait(mismatch,attention=True);result=occurrence(different)
        assert result['acceptance_outcome']=='not_matched' and not result['selected_snapshot_verified']
        assert result['acceptance_receipt']['result']['row_counts']['matched'] and not result['acceptance_receipt']['result']['data']['matched']
        assert not different['ssh_delegation_present'] and result['state']=='interrupted'
        released=schedule('release',{**confirm(different),'occurrence_id':result['job_id'],'credentials':credentials})
        assert released['protection_released'] and released['acceptance_outcome']=='not_matched'
        assert schedule('status',{'job_id':different['job_id']})['state']=='attention_required'
        checks.append('same-row-count-native-data-difference-suspends-policy-preserves-original-receipt-and-explicit-native-end-release-never-reenables')
        uncertain=review(expected['job_id']);original=native.run_checks
        def lost(*args,**kwargs):
            observed=original(*args,**kwargs);assert observed['tool']['process_observation']['cleanup_confirmed']
            raise ConnectionError('Owned loss of original scheduled native acceptance reply')
        with patch.object(native,'run_checks',lost):enable(uncertain);unknown=wait(uncertain,attention=True)
        result=occurrence(unknown);assert result['acceptance_outcome']=='unconfirmed' and result['state']=='interrupted'
        assert enable(uncertain)['state']=='attention_required'
        logical('remove_artifact',{'job_id':expected['job_id'],'confirmation':expected['job_id']},refused=True)
        physical('retention_review',{'job_id':copied['job_id'],'credentials':credentials},refused=True)
        assert not result['acceptance_receipt'].get('native_process_termination_confirmed')
        released=schedule('release',{**confirm(unknown),'occurrence_id':result['job_id'],'credentials':credentials})
        assert released['protection_released'] and released['acceptance_outcome']=='unconfirmed'
        assert schedule('occurrence',{'job_id':unknown['job_id'],'occurrence_id':result['job_id']})['acceptance_receipt']==result['acceptance_receipt']
        checks.append('lost-real-native-reply-keeps-unknown-no-replay-until-independent-original-utility-and-exact-native-server-end-release')
        if use_c and binary:
            closed=threading.Event();entered=threading.Event()
            from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_transport as remote
            request=remote.Transport.request
            def hold(channel,body,*args,**kwargs):
                if body['action']=='start' and body['phase']=='recover':entered.set();assert closed.wait(90)
                return request(channel,body,*args,**kwargs)
            with patch.object(remote.Transport,'request',hold):
                proof['browser']=browser(app,output/'check-schedule-desktop',sid,copied['job_id'],expected['job_id'],password,credentials,binary,driver_binary,closed)
                assert entered.wait(10)
                completed=wait({'job_id':proof['browser']['schedule_job_id']})
            assert occurrence(completed)['selected_snapshot_verified'];schedule('disable',confirm(completed))
            checks.append('built-checkpoint-picker-explicit-encrypted-policy-delegation-and-native-recovery-acceptance-after-viewer-closes')
        with oracle.cursor() as cursor:cursor.execute("UPDATE sr_osc.t SET note='native 雪' WHERE id=18446744073709551615")
        proof['interfaces'].append({'use_c':use_c,'checks':checks,'complete':True})
    proof['complete']=True;return proof


def browser(app,output,sid,copy_id,backup_id,password,credentials,binary,driver_binary,closed):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action,complete_endpoint_prompt
    output.mkdir(mode=0o700)
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1900,1600'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,120);ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def source(browser):return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script(
            'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        invoke_context_action(wait,driver,wait.until(source),('Backup','MySQL physical backups...'),handle_endpoint_prompt=False);complete_endpoint_prompt(driver,password,timeout=8)
        def click(text):
            node=wait.until(lambda b:b.execute_script('return Array.from(document.querySelectorAll("button")).find(b=>b.textContent.trim()===arguments[0] && !b.disabled && b.getBoundingClientRect().width>0)||null;',text))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
        def field(label,value):
            node=driver.find_element(By.ID,driver.find_element(By.XPATH,'//label[text()="'+label+'"]').get_attribute('for'))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);wait.until(lambda _b:node.is_enabled());node.send_keys(Keys.CONTROL,'a');node.send_keys(value);node.send_keys(Keys.TAB)
        def check(label):
            node=driver.find_element(By.XPATH,'//label[contains(.,"'+label+'")]');driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
        click('Load physical jobs');node=wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'button[aria-label="Inspect physical job '+copy_id+'"]'));wait.until(lambda _b:node.is_enabled());node.click()
        wait.until(lambda b:any(json.loads(node.get_attribute('textContent')).get('job_id')==copy_id for node in b.find_elements(By.CSS_SELECTOR,'[aria-label="Native physical receipt"]')))
        click('Use copy-back for managed recovery')
        field('Physical SSH private key',credentials['private_key']);field('Recovery loopback TCP port (0 disables)','0');field('Physical native timeout seconds','120')
        check('Enable trusted LOCAL INFILE for native checksum acceptance on this recovery copy')
        click('Load expected full-instance backups')
        node=wait.until(lambda b:b.find_element(By.ID,b.find_element(By.XPATH,'//label[text()="Expected recovery checkpoint backup"]').get_attribute('for')))
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
        wait.until(lambda b:next((row for row in b.find_elements(By.CSS_SELECTOR,'[role="option"]') if row.text==backup_id),None)).click()
        field('Recovery check interval seconds','60');field('Recovery check policy lifetime days','1')
        click('Review recurring physical recovery check policy')
        receipt='Recurring physical recovery check policy receipt'
        value=wait.until(lambda b:next((json.loads(node.get_attribute('textContent')) for node in b.find_elements(By.CSS_SELECTOR,'[aria-label="'+receipt+'"]')),None))
        assert value['preview']['expected_backup']['job_id']==backup_id and value['preview']['input_job_id']==copy_id
        field('Exact recurring recovery check policy UUID',value['job_id']);check('I confirm this exact recurring native recovery check policy.')
        check('Delegate SSH and the registered SQL password encrypted for this expiring recovery check policy.')
        click('Enable reviewed recurring recovery check policy')
        wait.until(lambda b:any(json.loads(node.get_attribute('textContent')).get('state')=='enabled' for node in b.find_elements(By.CSS_SELECTOR,'[aria-label="'+receipt+'"]')))
        driver.execute_script('document.querySelectorAll("textarea,input[type=password]").forEach(e=>e.style.visibility="hidden");');driver.save_screenshot(str(output/'native-recovery-check-policy.png'))
        errors=[row for row in driver.get_log('browser') if row['level']=='SEVERE'];assert not errors,errors
        driver.get('about:blank');closed.set()
        proof={'complete':True,'schedule_job_id':value['job_id'],'console_errors':errors,'checks':['built-source-menu-retained-copy-selection','explicit-expected-backup-picker-and-private-read-only-startup-policy','exact-policy-UUID-and-encrypted-SSH-SQL-delegation','viewer-closes-before-real-native-recovery-dispatch']}
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n');return proof
    except Exception:
        if driver:
            driver.execute_script('document.querySelectorAll("textarea,input[type=password]").forEach(e=>e.style.visibility="hidden");');driver.save_screenshot(str(output/'failure.png'))
            diagnostic=driver.execute_script('const root=document.body.cloneNode(true);root.querySelectorAll("input,textarea").forEach(e=>{e.value="";e.removeAttribute("value");if(e.tagName==="TEXTAREA")e.textContent="";});return root.outerHTML;')
            (output/'failure.dom.html').write_text(diagnostic)
        raise
    finally:
        closed.set()
        if driver:driver.quit()
        http.shutdown();http.server_close();thread.join(5)
