"""Native physical-chain retention; called inside the owned physical fixture."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from unittest.mock import patch


def qualify_retention(app,output,oracle,container,port,password,selected,credentials,binary=None,driver_binary=None):
    from flask import url_for
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_family_object_live_orchestrator import _run
    from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_transport as transport
    output=Path(output);root=Path(__file__).resolve().parents[1]
    proof={'complete':False,'interfaces':[],'history_testing':'not run','source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [Path(__file__),root/'web/pgadmin/cdeadmin/workspace/mysql_physical_retention.py',
            root/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_retention_worker.py',
            root/'web/pgadmin/static/js/Dialogs/MySQLPhysical.jsx']}}
    for use_c in (False,True):
        sid,_target,_post=registration(app,{'host':'127.0.0.1','port':port},password,use_c,username='sr_physical')
        with app.test_request_context('/'):
            item=__import__('pgadmin.model',fromlist=['Server']).Server.query.get(sid)
            endpoint=url_for('NODE-server.cde_workspace_id',gid=item.servergroup_id,sid=sid);owner=item.user_id
        client=app.test_client()
        with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
        checks=[]
        def post(operation,request,refused=False):
            response=client.post(endpoint,json={'action':'mysql_physical_'+operation,'request':request});value=response.get_json()
            if refused:assert not value.get('success'),value;return value
            assert response.status_code==200 and value.get('success'),value
            return value['data']
        def review(phase,parent=None):
            options={**deepcopy(selected),'phase':phase,'input_job_id':parent}
            if phase=='recover':options.update(mysqld='/usr/sbin/mysqld',recovery_gtid_mode='ON',recovery_port=33448,
                recovery_mode='replay',recovery_server_id=40001+int(use_c),timeout_seconds=600)
            return post('review',{'options':options,'credentials':credentials})
        def start(ticket):
            value=post('start',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,
                'delegate_database_credentials':True,'credentials':credentials})
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                value=post('reconcile',{'job_id':value['job_id'],'credentials':credentials})
                if value['recovery_running'] if ticket['options']['phase']=='recover' else value.get('remote_observation',{}).get('supervisor_finished'):
                    assert value['recovery_running'] if ticket['options']['phase']=='recover' else value['file_verification_confirmed'],value
                    return value
                time.sleep(.15)
            raise TimeoutError('Native retention chain did not become ready')
        def retain_review(job):return post('retention_review',{'job_id':job['job_id'],'credentials':credentials})
        def retain_start(ticket,job):
            return post('retention_start',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],
                'confirmed':True,'job_confirmation':job['job_id'],'credentials':credentials})
        backup=start(review('backup'))
        post('retention_pin',{'job_id':backup['job_id'],'pinned':True})
        post('retention_review',{'job_id':backup['job_id'],'credentials':credentials},refused=True)
        post('retention_pin',{'job_id':backup['job_id'],'pinned':False});ticket=retain_review(backup)
        abandoned=post('retention_abandon',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],
            'confirmed':True,'job_confirmation':backup['job_id'],'credentials':credentials})
        assert abandoned['state']=='not_dispatched' and abandoned['remote_observation']['late_dispatch_refused']
        assert retain_start(ticket,backup)['state']=='not_dispatched'
        checks.append('native-backup-pin-and-explicit-unclaimed-review-invalidation-with-no-late-dispatch')
        pending=review('prepare',backup['job_id'])
        post('retention_review',{'job_id':backup['job_id'],'credentials':credentials},refused=True)
        post('cancel',{'job_id':pending['job_id'],'credentials':credentials})
        prepared=start(review('prepare',backup['job_id']));copied=start(review('copy_back',prepared['job_id']))
        runtime=start(review('recover',copied['job_id']))
        post('retention_review',{'job_id':runtime['job_id'],'credentials':credentials},refused=True)
        connection=post('connection_review',{'job_id':runtime['job_id'],'name':'Retention recovered '+str(use_c),'credentials':credentials})
        registered=post('connection_connect',{'review_id':connection['job_id'],'review_digest':connection['review_digest'],
            'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})['result']
        post('cancel',{'job_id':runtime['job_id'],'credentials':credentials});deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            runtime=post('reconcile',{'job_id':runtime['job_id'],'credentials':credentials})
            if runtime['remote_observation'].get('supervisor_finished'):break
            time.sleep(.1)
        else:raise TimeoutError('Retention runtime did not stop')
        post('retention_review',{'job_id':runtime['job_id'],'credentials':credentials},refused=True)
        from cdeadmin_mysql_recovery_connection_qualification import endpoint as target_endpoint
        response=client.post(target_endpoint(app,registered['server_id']),json={'action':'endpoint_profile_remove','request':{'confirmation':registered['name']}})
        assert response.get_json()['success'],response.get_json()
        post('retention_review',{'job_id':backup['job_id'],'credentials':credentials},refused=True)
        # The host independently protects the same parent even without the
        # application dependency inventory.
        service=app.extensions['cdeadmin_provider_workspace'];jobs=service.mysql_physical_jobs
        original=jobs.load(backup['job_id'],owner,backup['endpoint_id'])
        from pgadmin.cdeadmin.workspace.mysql_physical_service import remote_request
        import uuid
        channel=transport.Transport(selected['connection'],credentials)
        try:
            channel.connect()
            try:channel.request({**remote_request(original,'retention_inspect'),'retention_id':str(uuid.uuid4())})
            except transport.HostError as error:assert 'dependent physical artifacts' in str(error)
            else:raise AssertionError('Native host lost its parent dependency')
        finally:channel.close()
        checks.append('reviewed-and-remote-child-dependencies-live-processes-and-stopped-recovery-registrations-refuse-retention')
        if use_c and binary:
            proof['browser']=browser(app,output/'physical-retention-desktop',sid,runtime['job_id'],password,credentials,binary,driver_binary)
            removed=post('status',{'job_id':runtime['job_id']});assert removed['artifact_removed']
        else:assert retain_start(retain_review(runtime),runtime)['removal_confirmed']
        assert _run(['docker','exec',container,'test','!','-e',selected['workspace']+'/'+runtime['job_id']+'/runtime-data']).returncode==0
        checks.append('reviewed-recovery-data-and-private-binlog-removal-preserves-original-native-outcome')
        ticket=retain_review(copied);request=transport.Transport.request
        def lost(channel,payload,*args,**kwargs):
            value=request(channel,payload,*args,**kwargs)
            if payload['action']=='retention_remove':raise transport.HostError('Owned loss after actual native physical removal')
            return value
        with patch.object(transport.Transport,'request',lost):
            post('retention_start',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,
                'job_confirmation':copied['job_id'],'credentials':credentials},refused=True)
        assert post('retention_status',{'job_id':ticket['job_id']})['state']=='unknown'
        reconciled=post('retention_reconcile',{'job_id':ticket['job_id'],'credentials':credentials})
        assert reconciled['removal_confirmed'] and reconciled['state']=='removed'
        checks.append('lost-original-removal-reply-stays-unknown-until-independent-host-reconciliation')
        ticket=retain_review(prepared);sources=transport.sources
        def interrupted(channel,payload,*args,**kwargs):
            if payload['action']!='retention_remove':return request(channel,payload,*args,**kwargs)
            code=sources();needle="if current['identity']['kind']=='directory':shutil.rmtree(detached)"
            assert code['retention'].count(needle)==1
            code['retention']=code['retention'].replace(needle,"if current['identity']['kind']=='directory':\n            victim=next(p for p in detached.rglob('*') if p.is_file());victim.unlink()\n            raise OSError('Owned partial native filesystem removal')")
            with patch.object(transport,'sources',return_value=code):return request(channel,payload,*args,**kwargs)
        with patch.object(transport.Transport,'request',interrupted):
            post('retention_start',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,
                'job_confirmation':prepared['job_id'],'credentials':credentials},refused=True)
        observed=post('retention_reconcile',{'job_id':ticket['job_id'],'credentials':credentials})
        assert observed['state']=='unknown' and not observed['remote_observation']['removal_confirmed']
        assert retain_start(ticket,prepared)['removal_confirmed']
        checks.append('genuine-host-file-unlink-interruption-resumes-only-original-detached-intent')
        # Lock the registered SQL principal while the independent root session
        # retains pending work. SSH cleanup needs neither that SQL login nor a
        # user transaction decision.
        ticket=retain_review(backup);oracle.autocommit=False
        with oracle.cursor() as cursor:cursor.execute('INSERT INTO sr_osc.pending VALUES(%s)',(7001+int(use_c),));cursor.execute('SAVEPOINT physical_retention_guard')
        from mysql_qualification_support import _root_connection
        control=_root_connection('mysql',port);control.autocommit=True;locked=False
        try:
            with control.cursor() as cursor:cursor.execute("ALTER USER 'sr_physical'@'%' ACCOUNT LOCK")
            locked=True
            import mysql.connector
            try:mysql.connector.connect(host='127.0.0.1',port=port,user='sr_physical',password=password,use_pure=not use_c)
            except mysql.connector.Error as error:assert error.errno==3118
            else:raise AssertionError('Owned SQL account lock did not deny a new native connection')
            assert retain_start(ticket,backup)['removal_confirmed']
        finally:
            if locked:
                with control.cursor() as cursor:cursor.execute("ALTER USER 'sr_physical'@'%' ACCOUNT UNLOCK")
            control.close()
            with oracle.cursor() as cursor:
                cursor.execute('ROLLBACK TO SAVEPOINT physical_retention_guard');cursor.execute('SELECT COUNT(*) FROM sr_osc.pending');assert cursor.fetchone()[0]==1
            oracle.rollback();oracle.autocommit=True
        checks.append('registered-SQL-principal-unavailable-retention-preserves-independent-pending-transaction-and-savepoint')
        for job in (backup,prepared,copied,runtime):
            current=post('status',{'job_id':job['job_id']})
            assert current['artifact_removed'] and current['state']==job['state'] and not current['file_verification_confirmed']
        post('review',{'options':{**deepcopy(selected),'phase':'prepare','input_job_id':backup['job_id']},'credentials':credentials},refused=True)
        checks.append('all-four-chain-artifacts-retired-in-dependency-order-and-reuse-refused')
        proof['interfaces'].append({'use_c':use_c,'checks':checks,'complete':True})
    proof['complete']=True
    (output/'physical-retention-summary.json').write_text(json.dumps(proof,indent=2)+'\n');return proof


def browser(app,output,sid,job_id,password,credentials,binary,driver_binary,*,batch=False):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action,complete_endpoint_prompt
    output=Path(output);output.mkdir(mode=0o700,parents=True,exist_ok=False)
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1200'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,90,ignored_exceptions=(StaleElementReferenceException,))
        ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def registered(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        invoke_context_action(wait,driver,wait.until(registered),('Backup','MySQL physical backups...'),handle_endpoint_prompt=False)
        complete_endpoint_prompt(driver,password,timeout=8)
        def click(label):
            node=wait.until(lambda browser:browser.execute_script('return Array.from(document.querySelectorAll("button")).find(b=>b.textContent.trim()===arguments[0] && !b.disabled && b.getBoundingClientRect().width>0) || null;',label))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
        click('Load physical jobs')
        node=wait.until(lambda browser:browser.find_element(By.CSS_SELECTOR,'button[aria-label="Inspect physical job '+job_id+'"]'))
        wait.until(lambda _browser:node.is_enabled());node.click()
        wait.until(lambda browser:any(json.loads(node.get_attribute('textContent')).get('job_id')==job_id for node in browser.find_elements(By.CSS_SELECTOR,'[aria-label="Native physical receipt"]')))
        label=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'label') if node.is_displayed() and node.text=='Physical SSH private key'),None))
        field=driver.find_element(By.ID,label.get_attribute('for'));wait.until(lambda _browser:field.is_enabled());field.send_keys(credentials['private_key'])
        if batch:
            for label,value in [('Physical retention days','0'),('Minimum full-backup chains','1')]:
                field=driver.find_element(By.ID,driver.find_element(By.XPATH,'//label[text()="'+label+'"]').get_attribute('for'))
                driver.execute_script('arguments[0].scrollIntoView({block:"center"});',field);field.click()
                from selenium.webdriver.common.keys import Keys
                field.send_keys(Keys.CONTROL,'a');field.send_keys(value);field.send_keys(Keys.TAB)
        click('Review physical retention policy' if batch else 'Review physical artifact retention')
        receipt='Physical retention batch receipt' if batch else 'Physical retention review'
        value=wait.until(lambda browser:next((json.loads(node.text) for node in browser.find_elements(By.CSS_SELECTOR,'[aria-label="'+receipt+'"]') if node.is_displayed()),None))
        if batch:assert job_id in value['plan']['job_ids'] and value['plan']['retained_full_backup_ids']
        exact='Exact physical retention batch UUID' if batch else 'Exact physical job UUID to remove'
        field=driver.find_element(By.ID,driver.find_element(By.XPATH,'//label[text()="'+exact+'"]').get_attribute('for'))
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});',field)
        wait.until(lambda _browser:field.is_displayed() and field.is_enabled());field.click()
        field.send_keys(value['job_id'] if batch else job_id)
        confirmation='I confirm this exact physical retention batch.' if batch else 'I confirm removal of these reviewed physical files.'
        label=driver.find_element(By.XPATH,'//label[contains(.,"'+confirmation+'")]')
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});',label);label.click()
        click('Run reviewed physical retention batch' if batch else 'Remove reviewed physical artifacts')
        value=wait.until(lambda browser:next((json.loads(node.text) for node in browser.find_elements(By.CSS_SELECTOR,'[aria-label="'+receipt+'"]') if node.is_displayed() and (json.loads(node.text).get('state')=='completed' if batch else json.loads(node.text).get('removal_confirmed'))),None))
        assert value['state']==('completed' if batch else 'removed')
        driver.execute_script('document.querySelectorAll("textarea,input[type=password]").forEach(e=>e.style.visibility="hidden");')
        driver.save_screenshot(str(output/'native-physical-retention.png'))
        errors=[row for row in driver.get_log('browser') if row['level']=='SEVERE'];assert not errors,errors
        proof={'complete':True,'batch':batch,'checks':['built-source-menu-native-physical-job-inspection',
            'reviewed-age-count-policy-and-exact-batch-UUID-native-removal' if batch else 'reviewed-exact-UUID-and-confirmed-native-host-removal',
            'original-receipt-refresh-without-automatic-replay'],'console_errors':errors}
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n');return proof
    except Exception:
        if driver:
            diagnostic=driver.execute_script('const root=document.body.cloneNode(true);root.querySelectorAll("input,textarea").forEach(e=>{e.value="";e.removeAttribute("value");if(e.tagName==="TEXTAREA")e.textContent="";});return root.outerHTML;')
            (output/'browser-failure.dom.html').write_text(diagnostic)
            driver.execute_script('document.querySelectorAll("textarea,input[type=password]").forEach(e=>e.style.visibility="hidden");')
            driver.save_screenshot(str(output/'browser-failure.png'))
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();http.server_close();thread.join(5)
