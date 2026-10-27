"""Real native incremental chains, immutable apply, recovery and acceptance."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading
import time
from unittest.mock import patch


def qualify_incrementals(app,output,oracle,container,port,password,selected,credentials,binary=None,driver_binary=None):
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_recovery_connection_qualification import endpoint
    from cdeadmin_mysql_physical_replay_qualification import wait_job,start_request
    from cdeadmin_mysql_family_object_live_orchestrator import _root_connection
    from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_transport as remote
    root=Path(__file__).resolve().parents[1];checks=[];source_cursor=oracle.cursor()
    paths=['tools/cdeadmin_mysql_physical_incremental_qualification.py','web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_worker.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_retention_worker.py','web/pgadmin/cdeadmin/workspace/mysql_physical_service.py',
        'web/pgadmin/cdeadmin/workspace/mysql_physical_retention.py','web/pgadmin/cdeadmin/workspace/mysql_physical_batch_retention.py',
        'web/pgadmin/static/js/Dialogs/MySQLPhysical.jsx']
    proof={'complete':False,'interfaces':[],'history_testing':'not run','source_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}}
    for use_c in (False,True):
        sid,_,_=registration(app,{'host':'127.0.0.1','port':port},password,use_c,username='sr_physical')
        from pgadmin.model import Server
        with app.test_request_context('/'):owner=Server.query.get(sid).user_id
        client=app.test_client()
        with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
        url=endpoint(app,sid)
        def post(url,prefix,action,body,refused=False):
            response=client.post(url,json={'action':prefix+action,'request':body});value=response.get_json()
            if refused:assert not value.get('success'),value;return value
            assert response.status_code==200 and value.get('success'),value
            return value['data']
        physical=lambda action,body,refused=False:post(url,'mysql_physical_',action,body,refused)
        def review(kind,parent=None,delta=None):
            extra={'incremental_job_id':delta} if kind=='prepare_redo' else {}
            return physical('review',{'options':{**deepcopy(selected),'phase':kind,'input_job_id':parent,**extra},'credentials':credentials})
        def start(ticket):return physical('start',{**start_request(ticket),'delegate_database_credentials':True,'credentials':credentials})
        def terminal(value):
            deadline=time.monotonic()+240
            while time.monotonic()<deadline:
                value=physical('reconcile',{'job_id':value['job_id'],'credentials':credentials});observed=value.get('remote_observation') or {}
                if observed.get('supervisor_finished'):
                    if not value['file_verification_confirmed']:
                        (output/'incremental-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                        (output/'incremental-native-output.json').write_text(json.dumps(physical('output',{'job_id':value['job_id'],'credentials':credentials}),indent=2)+'\n')
                        raise AssertionError('Native incremental work did not publish verified files')
                    return value
                time.sleep(.1)
            raise TimeoutError('Native incremental operation did not end')
        def phase(kind,parent=None,delta=None):return terminal(start(review(kind,parent,delta)))
        def raw(record):
            from pgadmin.cdeadmin.workspace.mysql_physical_service import manager
            with app.app_context():
                jobs,_,_=manager(app.extensions['cdeadmin_provider_workspace'],Server.query.get(sid))
                return jobs.load(record['job_id'],owner,record['endpoint_id'])
        checks=[];runtime=None;attached=None;guard=_root_connection('mysql',port);guard.autocommit=False
        try:
            with guard.cursor() as cursor:cursor.execute('INSERT INTO sr_osc.pending VALUES(%s)',(22100+int(use_c),));cursor.execute('SAVEPOINT incremental_guard')
            base=phase('backup');base_manifest=base['remote_observation']['artifact']['manifest_sha256']
            source_cursor.execute("INSERT INTO sr_osc.t VALUES(1,'incremental one 雪',X'00FF01')")
            source_cursor.execute("UPDATE sr_osc.m SET note='MyISAM incremental one'")
            source_cursor.execute("INSERT INTO sr_osc.c VALUES('CSV incremental one')")
            source_cursor.execute('CREATE TABLE sr_osc.added_after_base(id INT PRIMARY KEY,note VARCHAR(40))')
            source_cursor.execute("INSERT INTO sr_osc.added_after_base VALUES(1,'after full')")
            ticket=review('incremental',base['job_id']);request=remote.Transport.request
            def lost(channel,body,*args,**kwargs):
                value=request(channel,body,*args,**kwargs)
                if body['action']=='start' and body['phase']=='incremental':raise remote.HostError('Owned loss of original incremental dispatch reply')
                return value
            with patch.object(remote.Transport,'request',lost):
                physical('start',{**start_request(ticket),'delegate_database_credentials':True,'credentials':credentials},refused=True)
            first=terminal(ticket);assert first['state']=='unknown'
            assert first['remote_observation']['artifact']['format']=='xtrabackup-9.7-incremental'
            assert start(ticket)['state']=='unknown'
            source_cursor.execute("INSERT INTO sr_osc.t VALUES(2,'incremental two 雪',X'00FF02')")
            source_cursor.execute("UPDATE sr_osc.m SET note='MyISAM incremental two'")
            source_cursor.execute("INSERT INTO sr_osc.c VALUES('CSV incremental two')")
            source_cursor.execute("ALTER TABLE sr_osc.added_after_base ADD COLUMN extra VARCHAR(20) DEFAULT 'native second'")
            source_cursor.execute('CREATE PROCEDURE sr_osc.incremental_routine() SELECT * FROM sr_osc.added_after_base')
            second=phase('incremental',first['job_id'])
            assert first['remote_observation']['artifact']['checkpoint']['to_lsn']==second['remote_observation']['artifact']['checkpoint']['from_lsn']
            redo=phase('prepare_redo',base['job_id']);assert redo['remote_observation']['artifact']['redo_only']
            physical('review',{'options':{**selected,'phase':'prepare_redo','input_job_id':redo['job_id'],'incremental_job_id':second['job_id']},'credentials':credentials},refused=True)
            physical('review',{'options':{**selected,'phase':'copy_back','input_job_id':redo['job_id']},'credentials':credentials},refused=True)
            applied=phase('prepare_redo',redo['job_id'],first['job_id'])
            physical('review',{'options':{**selected,'phase':'prepare_redo','input_job_id':applied['job_id'],'incremental_job_id':first['job_id']},'credentials':credentials},refused=True)
            merged=phase('prepare_redo',applied['job_id'],second['job_id'])
            lineage={'base_job_id':base['job_id'],'incremental_job_ids':[first['job_id'],second['job_id']]}
            assert merged['remote_observation']['lineage']==lineage
            final=phase('prepare',merged['job_id']);copied=phase('copy_back',final['job_id'])
            for value in (base,first,second):
                observed=physical('reconcile',{'job_id':value['job_id'],'credentials':credentials})
                assert observed['remote_observation']['artifact']['manifest_sha256']==value['remote_observation']['artifact']['manifest_sha256']
                physical('retention_review',{'job_id':value['job_id'],'credentials':credentials},refused=True)
            assert physical('status',{'job_id':base['job_id']})['remote_observation']['artifact']['manifest_sha256']==base_manifest
            with guard.cursor() as cursor:cursor.execute('ROLLBACK TO SAVEPOINT incremental_guard');cursor.execute('SELECT COUNT(*) FROM sr_osc.pending');assert cursor.fetchone()[0]==1
            guard.rollback()
            checks.append('native-full-two-incrementals-InnoDB-MyISAM-CSV-and-DDL-with-pending-source-savepoint-preserved')
            checks.append('lost-original-incremental-dispatch-reply-stays-unknown-after-independent-native-file-and-end-observation-without-replay')
            checks.append('native-redo-only-private-two-input-apply-final-undo-and-copy-back-preserve-full-and-both-incremental-byte-manifests')
            checks.append('missing-order-and-repeated-incrementals-and-copy-back-before-finalization-refuse-native-admission-and-retention-protects-both-inputs')
            logical=lambda action,body:post(url,'mysql_instance_backup_',action,body)
            expected=wait_job(logical('start',start_request(logical('review',{'options':{'users':False,'checksum':True,'threads':1,'timeout_seconds':120}}))),logical,'completed')
            ticket=physical('review',{'options':{**selected,'phase':'recover','input_job_id':copied['job_id'],'mysqld':'/usr/sbin/mysqld','recovery_gtid_mode':'ON',
                'recovery_mode':'read_only','recovery_port':0,'recovery_local_infile':True,'timeout_seconds':300},'credentials':credentials})
            runtime=start(ticket);deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                runtime=physical('reconcile',{'job_id':runtime['job_id'],'credentials':credentials})
                if runtime['recovery_running']:break
                if runtime.get('remote_observation',{}).get('supervisor_finished'):raise AssertionError(runtime)
                time.sleep(.1)
            else:raise TimeoutError('Incremental recovery startup')
            ticket=physical('connection_review',{'job_id':runtime['job_id'],'name':'Recovered incremental '+str(use_c),'credentials':credentials})
            attached=physical('connection_connect',{'review_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})['result']
            accept=lambda action,body:post(endpoint(app,attached['server_id']),'mysql_instance_acceptance_',action,body)
            ticket=accept('review',{'source_server_id':sid,'backup_job_id':expected['job_id'],'options':{'target_confirmation':attached['binding']['server_uuid'],
                'server_wide_write_pause_confirmed':True,'threads':1,'timeout_seconds':120}})
            accepted=wait_job(accept('start',start_request(ticket)),accept,'verification_observed')
            (output/('incremental-acceptance-'+str(use_c)+'.json')).write_text(json.dumps(accepted,indent=2)+'\n')
            assert accepted['acceptance_outcome']=='matched',accepted
            assert accepted['result']['data']['matched'] and accepted['result']['definitions']['matched']
            checks.append('fresh-private-native-MySQL-recovery-full-count-checksum-and-exported-definition-acceptance-match-latest-independent-source-snapshot')
            if use_c and binary:
                proof['browser']=browser(app,output/'incremental-desktop',sid,redo['job_id'],first['job_id'],password,credentials,binary,driver_binary)
                checks.append('built-source-menu-native-incremental-picker-reviewed-private-apply-and-explicit-final-preparation')
            proof['interfaces'].append({'use_c':use_c,'checks':checks,'complete':True})
        finally:
            guard.rollback();guard.close()
            if attached:
                try:physical('connection_detach',{'server_id':attached['server_id']})
                except Exception:pass
            if runtime:
                physical('cancel',{'job_id':runtime['job_id'],'credentials':credentials});deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    value=physical('reconcile',{'job_id':runtime['job_id'],'credentials':credentials})
                    if value.get('remote_observation',{}).get('process_termination_confirmed'):break
                    time.sleep(.1)
                else:raise TimeoutError('Original incremental recovery did not stop')
            for sql in ('DROP PROCEDURE IF EXISTS sr_osc.incremental_routine','DROP TABLE IF EXISTS sr_osc.added_after_base','DELETE FROM sr_osc.t WHERE id<1000',
                "UPDATE sr_osc.m SET note='native MyISAM'","DELETE FROM sr_osc.c WHERE note<>'native CSV'"):
                source_cursor.execute(sql)
    source_cursor.close();proof['complete']=True;return proof


def browser(app,output,sid,redo_id,delta_id,password,credentials,binary,driver_binary):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action,complete_endpoint_prompt
    output.mkdir(mode=0o700);http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1900,1600'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,120);ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def source(b):return next((n for n in b.find_elements(By.CSS_SELECTOR,'.file-name') if n.is_displayed() and b.execute_script(
            'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',n,sid)),None)
        invoke_context_action(wait,driver,wait.until(source),('Backup','MySQL physical backups...'),handle_endpoint_prompt=False);complete_endpoint_prompt(driver,password,timeout=8)
        def click(text):
            node=wait.until(lambda b:b.execute_script('return Array.from(document.querySelectorAll("button")).find(b=>b.textContent.trim()===arguments[0] && !b.disabled && b.getBoundingClientRect().width>0)||null;',text))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
        def receipt(b):return json.loads(b.find_element(By.CSS_SELECTOR,'[aria-label="Native physical receipt"]').get_attribute('textContent'))
        click('Load physical jobs');node=wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'button[aria-label="Inspect physical job '+redo_id+'"]'));wait.until(lambda _b:node.is_enabled());node.click()
        wait.until(lambda b:receipt(b)['job_id']==redo_id)
        label=driver.find_element(By.XPATH,'//label[text()="Physical SSH private key"]');field=driver.find_element(By.ID,label.get_attribute('for'));wait.until(lambda _b:field.is_enabled());field.send_keys(credentials['private_key'])
        click('Use separate redo-only copy for incrementals');click('Load retained incremental inputs')
        field=wait.until(lambda b:b.find_element(By.ID,b.find_element(By.XPATH,'//label[text()="Retained incremental to apply"]').get_attribute('for')))
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});',field);field.click()
        wait.until(lambda b:next((row for row in b.find_elements(By.CSS_SELECTOR,'[role="option"]') if row.text.startswith(delta_id+':')),None)).click()
        def execute():
            click('Review native physical job');wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,'[aria-label="Native physical review"]'))
            label=driver.find_element(By.XPATH,'//label[contains(.,"I confirm this exact reviewed physical operation.")]');driver.execute_script('arguments[0].scrollIntoView({block:"center"});',label);label.click();click('Start reviewed physical job')
            click('Observe remote physical job')
            return wait.until(lambda b:(value if (value:=receipt(b)).get('file_verification_confirmed') else None))
        applied=execute();assert applied['remote_observation']['artifact']['redo_only'] and applied['remote_observation']['lineage']['incremental_job_ids']==[delta_id]
        click('Finalize redo-only copy for recovery');final=execute();assert final['remote_observation']['artifact']['prepared']
        driver.execute_script('document.querySelectorAll("textarea,input[type=password]").forEach(e=>e.style.visibility="hidden");');driver.save_screenshot(str(output/'native-incremental-prepare.png'))
        errors=[row for row in driver.get_log('browser') if row['level']=='SEVERE'];assert not errors,errors
        proof={'complete':True,'console_errors':errors,'checks':['source-menu-retained-redo-only-base','native-incremental-picker-with-exact-LSNs','reviewed-private-native-delta-apply','explicit-native-final-preparation-before-recovery']}
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n');return proof
    except Exception:
        if driver:
            driver.execute_script('document.querySelectorAll("textarea,input[type=password]").forEach(e=>e.style.visibility="hidden");');driver.save_screenshot(str(output/'failure.png'))
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();http.server_close();thread.join(5)
