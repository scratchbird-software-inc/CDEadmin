"""Native X.509 source backup and isolated certificate-authenticated recovery."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def certificates(output,container,oracle):
    directory=output/'private-tls';directory.mkdir(mode=0o700)
    def run(*args):
        environment={key:value for key,value in os.environ.items() if key not in {'LD_LIBRARY_PATH','OPENSSL_MODULES','OPENSSL_CONF'}}
        with (output/'certificate-generation.log').open('ab') as log:
            subprocess.run(args,cwd=directory,env=environment,check=True,stdout=log,stderr=subprocess.STDOUT)
    run('openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.pem','-subj','/CN=Owned native physical CA','-days','2')
    (directory/'extensions.cnf').write_text('[server]\nsubjectAltName=IP:127.0.0.1,DNS:localhost\nextendedKeyUsage=serverAuth\n[client]\nextendedKeyUsage=clientAuth\n')
    for name in ('server','client'):
        run('openssl','req','-new','-newkey','rsa:2048','-nodes','-keyout',name+'.key','-out',name+'.csr','-subj','/CN=Owned physical '+name)
        run('openssl','x509','-req','-in',name+'.csr','-CA','ca.pem','-CAkey','ca.key','-CAcreateserial','-out',name+'.pem','-days','2','-extfile','extensions.cnf','-extensions',name)
    from cdeadmin_mysql_family_object_live_orchestrator import _run
    paths={}
    for name,file in [('ssl_ca','ca.pem'),('ssl_cert','server.pem'),('ssl_key','server.key')]:
        target='/var/lib/mysql/owned-physical-'+file
        _run(['docker','cp',str(directory/file),container+':'+target]);_run(['docker','exec',container,'chown','mysql:mysql',target]);_run(['docker','exec',container,'chmod','600',target]);paths[name]=target
    with oracle.cursor() as cursor:
        for name,path in paths.items():cursor.execute('SET GLOBAL '+name+'=%s',(path,))
        cursor.execute('ALTER INSTANCE RELOAD TLS')
        cursor.execute("ALTER USER 'sr_physical'@'%' REQUIRE X509")
    return {'ssl_ca':str(directory/'ca.pem'),'ssl_cert':str(directory/'client.pem'),'ssl_key':str(directory/'client.key'),
        'ssl_verify_cert':True,'ssl_verify_identity':True,'tls_versions':['TLSv1.2','TLSv1.3']},paths


def qualify_tls(app,output,oracle,container,port,password,selected,credentials,binary=None,driver_binary=None,*,desktop_only=False):
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_recovery_connection_qualification import endpoint,query_post,execute
    from cdeadmin_mysql_family_object_live_orchestrator import _root_connection,_run
    from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_transport as transport
    from unittest.mock import patch
    route,server_tls=certificates(output,container,oracle)
    with oracle.cursor() as cursor:
        cursor.execute('CREATE TABLE sr_osc.a_archive(id INT) ENGINE=ARCHIVE')
        cursor.execute('INSERT INTO sr_osc.a_archive VALUES(1)')
        cursor.execute('CREATE TABLE sr_osc.b_blackhole(id INT) ENGINE=BLACKHOLE')
        cursor.execute('INSERT INTO sr_osc.b_blackhole VALUES(1)')
        cursor.execute('CREATE TABLE sr_osc.v_memory(id INT) ENGINE=MEMORY')
        cursor.execute('INSERT INTO sr_osc.v_memory VALUES(1)')
        cursor.execute('CREATE TABLE sr_osc.m_merge LIKE sr_osc.m')
        cursor.execute('ALTER TABLE sr_osc.m_merge ENGINE=MRG_MyISAM UNION=(sr_osc.m) INSERT_METHOD=LAST')
    root=Path(__file__).resolve().parents[1]
    paths=['tools/cdeadmin_mysql_physical_tls_qualification.py','web/pgadmin/cdeadmin/workspace/mysql_physical_service.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_worker.py','web/pgadmin/cdeadmin/providers/mysql_family/mysql_recovery_worker.py',
        'web/pgadmin/cdeadmin/workspace/mysql_physical_backup_schedule.py','web/pgadmin/cdeadmin/workspace/mysql_physical_check_schedule.py',
        'web/pgadmin/static/js/Dialogs/MySQLPhysical.jsx','web/pgadmin/static/js/Dialogs/MySQLPhysicalBackupSchedule.jsx']
    proof={'complete':False,'interfaces':[],'history_testing':'not run','source_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}}
    if desktop_only:
        proof['browser']=qualify_desktop(app,output,port,password,selected,server_tls,credentials,binary,driver_binary,route)
        proof['qualification_scope']='Built desktop native certificate recovery; separate immutable API/worker receipts qualify both drivers'
        proof['complete']=True;return proof
    for use_c in (False,True):
        with oracle.cursor() as cursor:cursor.execute("UPDATE sr_osc.m SET note='native MyISAM'")
        sid,_,_=registration(app,{'host':'127.0.0.1','port':port,**route},password,use_c,username='sr_physical')
        from pgadmin.model import Server
        with app.test_request_context('/'):owner=Server.query.get(sid).user_id
        client=app.test_client()
        with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
        url=endpoint(app,sid);runtime=attached=None;guard=_root_connection('mysql',port);checks=[]
        def physical(action,body):
            response=client.post(url,json={'action':'mysql_physical_'+action,'request':body});value=response.get_json()
            if response.status_code!=200 or not value.get('success'):
                (output/'tls-api-failure.json').write_text(json.dumps(value,indent=2)+'\n');raise AssertionError('Native TLS API failed; inspect tls-api-failure.json')
            return value['data']
        def review(phase,parent=None,**extra):return physical('review',{'options':{**selected,'phase':phase,'input_job_id':parent,**extra},'credentials':credentials})
        def start(ticket):return physical('start',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})
        def wait(ticket,running=False,failed=False):
            deadline=time.monotonic()+150
            while time.monotonic()<deadline:
                value=physical('reconcile',{'job_id':ticket['job_id'],'credentials':credentials});remote=value.get('remote_observation') or {}
                if running and value['recovery_running']:return value
                if remote.get('supervisor_finished'):
                    if failed:return value
                    if (not running and value['file_verification_confirmed']):return value
                    (output/'tls-native-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                    (output/'tls-native-output.json').write_text(json.dumps(physical('output',{'job_id':ticket['job_id'],'credentials':credentials}),indent=2)+'\n')
                    raise AssertionError('Native TLS operation failed; inspect tls-native-output.json')
                time.sleep(.15)
            raise TimeoutError('Native TLS operation did not finish')
        def phase(name,parent=None,**extra):return wait(start(review(name,parent,**extra)))
        try:
            with guard.cursor() as cursor:cursor.execute('INSERT INTO sr_osc.pending VALUES(%s)',(700+int(use_c),));cursor.execute('SAVEPOINT tls_guard')
            bad=review('backup',sql_host=container);start(bad)
            refused=wait(bad,failed=True)['remote_observation']
            assert refused['state']=='not_dispatched' and not refused['native_may_have_dispatched'] and refused['credential_cleanup_confirmed']
            bad=review('backup');original=transport.Transport.request
            def lowered(channel,request,*args,**kwargs):
                if request['action']=='start':
                    request=deepcopy(request);request['database_credentials']['tls']['policy']['options']['ssl-mode']='REQUIRED'
                return original(channel,request,*args,**kwargs)
            with patch.object(transport.Transport,'request',lowered):start(bad)
            refused=wait(bad,failed=True)['remote_observation']
            assert refused['state']=='not_dispatched' and not refused['native_may_have_dispatched'] and refused['credential_cleanup_confirmed']
            bad=review('backup');assert bad['sql_tls_policy']['options']['ssl-mode']=='VERIFY_IDENTITY';start(bad)
            base=wait(bad);assert base['remote_review'] and base['file_verification_confirmed']
            assert base['volatile_memory_tables']==[{'schema_name':'sr_osc','table_name':'v_memory','current_rows':1}]
            assert 'private-tls' not in json.dumps(base['remote_review'])
            with oracle.cursor() as cursor:
                cursor.execute('INSERT INTO sr_osc.t VALUES(%s,%s,%s)',(800+int(use_c),'native verified TLS 雪',b'\x00\xff'))
                cursor.execute('INSERT INTO sr_osc.a_archive VALUES(%s)',(2+int(use_c),))
            delta=phase('incremental',base['job_id']);redo=phase('prepare_redo',base['job_id'])
            with oracle.cursor() as cursor:cursor.execute("UPDATE sr_osc.m SET note='source changed after retained checkpoint'")
            applied=phase('prepare_redo',redo['job_id'],incremental_job_id=delta['job_id']);final=phase('prepare',applied['job_id']);copy=phase('copy_back',final['job_id'])
            checks+=['native-X509-required-source-full-and-incremental-backups-use-privately-transferred-original-client-material-and-VERIFY_IDENTITY',
                'native-client-rejects-real-server-certificate-hostname-mismatch-before-backup-dispatch',
                'changed-delegated-verification-mode-refuses-before-native-dispatch-and-cleans-secrets',
                'native-private-incremental-apply-and-final-preparation-preserve-original-source-and-backup-bytes']
            runtime=wait(start(review('recover',copy['job_id'],mysqld='/usr/sbin/mysqld',recovery_gtid_mode='ON',recovery_port=33477,
                recovery_tls=server_tls,timeout_seconds=300)),running=True)
            assert runtime['remote_observation']['sql_identity']['authenticated_principal']=='sr_physical@%'
            ticket=physical('connection_review',{'job_id':runtime['job_id'],'name':'Native X509 recovery '+str(use_c),'credentials':credentials})
            attached=physical('connection_connect',{'review_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})['result']
            post=lambda action,**body:query_post(client,endpoint(app,attached['server_id']),attached['database_target_id'],action,**body)
            session=post('open_session',language_profile='mysql-sql',history_sensitive=True)['session_id']
            try:
                value=execute(post,session,'SELECT note,HEX(b) FROM t WHERE id='+str(800+int(use_c)))
                assert value['rows']==[['native verified TLS 雪','00FF']]
                assert execute(post,session,"SHOW SESSION STATUS LIKE 'Ssl_cipher'")['rows'][0][1]
                assert execute(post,session,'SELECT COUNT(*) FROM a_archive')['rows']==[[2+int(use_c)]]
                assert execute(post,session,'SELECT COUNT(*) FROM b_blackhole')['rows']==[[0]]
                assert execute(post,session,'SELECT COUNT(*) FROM v_memory')['rows']==[[0]]
                assert execute(post,session,'SELECT note FROM m_merge')['rows']==[['native MyISAM']]
            finally:post('close_session',session_id=session)
            physical('connection_detach',{'server_id':attached['server_id']});attached=None
            physical('cancel',{'job_id':runtime['job_id'],'credentials':credentials});wait(runtime,failed=True);runtime=None
            qualify_schedule(app,physical,sid,password,selected,server_tls,credentials)
            checks.append('encrypted-TLS-and-SQL-delegation-survives-idle-worker-restart-after-interactive-secret-erasure-and-completes-native-certificate-startup-drills')
            (output/'tls-api-progress.json').write_text(json.dumps({**proof,'interfaces':[*proof['interfaces'],{'use_c':use_c,'complete':True,'checks':list(checks)}]},indent=2)+'\n')
            if use_c and binary and driver_binary:
                proof['browser']=browser(app,output/'tls-desktop',sid,copy['job_id'],password,server_tls,credentials,binary,driver_binary)
                checks.append('built-desktop-reviews-host-server-certificates-and-starts-and-stops-native-X509-recovery')
            files=_run(['docker','exec',container,'find',selected['workspace'],'-name','client*']).stdout
            assert not files.strip(),files
            with guard.cursor() as cursor:cursor.execute('ROLLBACK TO SAVEPOINT tls_guard');cursor.execute('SELECT COUNT(*) FROM sr_osc.pending');assert cursor.fetchone()[0]==1
            guard.rollback()
            checks+=['native-certificate-authenticated-isolated-recovery-and-driver-editor-use-reviewed-server-TLS-and-exact-data',
                'native-ARCHIVE-incremental-data-BLACKHOLE-empty-semantics-and-MRG_MyISAM-member-data-recover-through-original-engines',
                'MERGE-recovery-reads-private-restored-member-bytes-after-live-source-member-changes',
                'MEMORY-definition-persists-with-native-empty-after-restart-semantics-and-source-volatile-row-disclosure',
                'TLS-authentication-and-private-cleanup-preserve-independent-user-transaction-and-savepoint']
            proof['interfaces'].append({'use_c':use_c,'complete':True,'checks':checks})
        finally:
            guard.rollback();guard.close()
            if attached:
                try:physical('connection_detach',{'server_id':attached['server_id']})
                except Exception:pass
            if runtime:
                physical('cancel',{'job_id':runtime['job_id'],'credentials':credentials});wait(runtime,failed=True)
    proof['complete']=True;return proof


def qualify_desktop(app,output,port,password,selected,server_tls,credentials,binary,driver_binary,route):
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_recovery_connection_qualification import endpoint
    from pgadmin.model import Server
    sid,_,_=registration(app,{'host':'127.0.0.1','port':port,**route},password,True,username='sr_physical')
    with app.test_request_context('/'):owner=Server.query.get(sid).user_id
    client=app.test_client()
    with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
    def physical(action,body):
        response=client.post(endpoint(app,sid),json={'action':'mysql_physical_'+action,'request':body});value=response.get_json()
        assert response.status_code==200 and value.get('success'),value
        return value['data']
    parent=None
    for phase in ('backup','prepare','copy_back'):
        ticket=physical('review',{'options':{**selected,'phase':phase,'input_job_id':parent},'credentials':credentials})
        physical('start',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})
        deadline=time.monotonic()+150
        while time.monotonic()<deadline:
            value=physical('reconcile',{'job_id':ticket['job_id'],'credentials':credentials})
            if value.get('remote_observation',{}).get('supervisor_finished'):
                assert value['file_verification_confirmed'],value
                parent=value['job_id'];break
            time.sleep(.15)
        else:raise TimeoutError('Native desktop recovery base did not complete')
    return browser(app,output/'tls-desktop',sid,parent,password,server_tls,credentials,binary,driver_binary)


def qualify_schedule(app,physical,sid,password,selected,server_tls,credentials):
    from flask import url_for
    from pgadmin.model import Server
    from pgadmin.cdeadmin.workspace.mysql_physical_backup_schedule import ScheduleHost
    with app.app_context():service=app.extensions['cdeadmin_provider_workspace']
    schedule=lambda action,body:physical('backup_schedule_'+action,body)
    drill={'mysqld':'/usr/sbin/mysqld','gtid_mode':'ON','timeout_seconds':60}
    if server_tls is not None:drill.update(recovery_tls=server_tls,recovery_port=33477)
    policy=schedule('review',{'options':{'physical':deepcopy(selected),'drill':drill,
        'interval_seconds':60,'expires_after_days':1},'credentials':credentials})
    confirm={'job_id':policy['job_id'],'confirmed':True,'schedule_confirmation':policy['job_id']}
    def wait(previous=None):
        deadline=time.monotonic()+360
        while time.monotonic()<deadline:
            current=schedule('status',{'job_id':policy['job_id']})
            if current['state']=='attention_required':raise AssertionError(current)
            if current.get('last_scan_at') and not current.get('scan_state') and current.get('last_occurrence_id')!=previous:
                occurrence=schedule('occurrence',{'job_id':policy['job_id'],'occurrence_id':current['last_occurrence_id']})
                assert occurrence['state']=='completed' and occurrence['startup_drill_outcome']=='passed' and occurrence['protection_released'],occurrence
                return current
            time.sleep(.2)
        raise TimeoutError('Native certificate backup/drill policy did not finish')
    try:
        schedule('enable',{**confirm,'review_digest':policy['review_digest'],'delegate_ssh_credentials':True,'delegate_database_credentials':True,'credentials':credentials})
        first=wait();host=service.mysql_backup_scheduler
        with app.app_context():
            server=Server.query.get(sid);service.endpoint_service.forget_server_credentials(server)
        raw=host.read(policy['job_id']);assert password not in json.dumps(raw) and 'PRIVATE KEY' not in json.dumps(raw)
        assert host.close();host=service.mysql_backup_scheduler=ScheduleHost(app,service)
        host.jobs.update(raw,next_scan_at=0);host.start();wait(first['last_occurrence_id'])
    finally:
        schedule('disable',confirm)
        with app.test_request_context('/'):
            server=Server.query.get(sid);verify=url_for('NODE-server.verify_endpoint_id',gid=server.servergroup_id,sid=sid);owner=server.user_id
        client=app.test_client()
        with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
        assert client.post(verify,json={'password':password}).get_json()['success']


def browser(app,output,sid,copy_id,password,server_tls,credentials,binary,driver_binary):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.common.keys import Keys
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action,complete_endpoint_prompt
    import threading
    output.mkdir(mode=0o700);http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1900,1600'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,150);ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def source(b):return next((n for n in b.find_elements(By.CSS_SELECTOR,'.file-name') if n.is_displayed() and b.execute_script(
            'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',n,sid)),None)
        invoke_context_action(wait,driver,wait.until(source),('Backup','MySQL physical backups...'),handle_endpoint_prompt=False);complete_endpoint_prompt(driver,password,timeout=8)
        def click(text):
            node=wait.until(lambda b:b.execute_script('return Array.from(document.querySelectorAll("button")).find(e=>e.textContent.trim()===arguments[0] && !e.disabled)',text))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
        def fill(text,value):
            label=driver.find_element(By.XPATH,'//label[normalize-space()="'+text+'"]')
            node=driver.find_element(By.ID,label.get_attribute('for'))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
            wait.until(lambda _b:node.is_displayed() and node.is_enabled());node.click()
            node.send_keys(Keys.CONTROL,'a');node.send_keys(value)
        def check(text):
            label=driver.find_element(By.XPATH,'//label[contains(.,"'+text+'")]');driver.execute_script('arguments[0].scrollIntoView({block:"center"});',label);label.click()
        click('Load physical jobs');node=wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'button[aria-label="Inspect physical job '+copy_id+'"]'));wait.until(lambda _b:node.is_enabled());node.click()
        click('Use copy-back for managed recovery');fill('Physical SSH private key',credentials['private_key'])
        check('Provision recovery server TLS from reviewed host files')
        for key,label in [('ssl_ca','Recovery host TLS CA'),('ssl_cert','Recovery host server certificate'),('ssl_key','Recovery host server key')]:fill(label,server_tls[key])
        click('Review native physical job');wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,'[aria-label="Native physical review"]'))
        assert 'VERIFY_IDENTITY' in driver.find_element(By.CSS_SELECTOR,'[aria-label="Native physical review"]').get_attribute('textContent')
        check('I confirm this exact reviewed physical operation.');check('Delegate the registered database password privately to the pinned SSH host.')
        click('Start reviewed physical job')
        def receipt(b):
            try:return json.loads(b.find_element(By.CSS_SELECTOR,'[aria-label="Native physical receipt"]').get_attribute('textContent'))
            except Exception:return {}
        wait.until(lambda b:receipt(b).get('recovery_running'))
        driver.execute_script('document.querySelectorAll("textarea,input[type=password]").forEach(e=>e.style.visibility="hidden");');driver.save_screenshot(str(output/'native-certificate-recovery.png'))
        click('Stop managed recovery instance')
        def stopped(b):
            if receipt(b).get('remote_observation',{}).get('supervisor_finished'):return True
            click('Observe remote physical job');return False
        wait.until(stopped)
        errors=[row for row in driver.get_log('browser') if row['level']=='SEVERE'];assert not errors,errors
        proof={'complete':True,'console_errors':errors,'checks':['source-menu-retained-copy-back','reviewed-native-host-CA-server-certificate-and-private-key-fingerprints',
            'separate-credential-delegation-and-real-native-X509-recovery','original-native-recovery-stop-and-end-observation']}
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n');return proof
    except Exception:
        if driver:driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=5)
