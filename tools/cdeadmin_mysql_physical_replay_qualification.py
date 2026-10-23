"""Native raw-log replay into a reviewed physical recovery instance."""
import argparse
import json
import os
from pathlib import Path
import threading
import time
from unittest.mock import patch


def wait_job(value,post,expected):
    deadline=time.monotonic()+120
    while value['state'] in {'dispatching','active','cancel_requested'}:
        if time.monotonic()>deadline:raise TimeoutError('Native physical raw replay deadline')
        time.sleep(.05);value=post('status',{'job_id':value['job_id']})
    assert value['state']==expected,value
    return value


def start_request(value):return {key:value[key] for key in ('job_id','review_digest')}|{'confirmed':True}


def native_replay(app,client,sid,root,physical,credentials,review,start,copied,output,use_c,*,browser_binary=None,driver_binary=None):
    from cdeadmin_mysql_recovery_connection_qualification import endpoint,query_post,execute
    from pgadmin.cdeadmin.providers.mysql_family import mysql_raw_binlog_replay as raw
    source_url=endpoint(app,sid)
    def http(url,prefix,action,request,refused=False):
        response=client.post(url,json={'action':prefix+action,'request':request});value=response.get_json()
        if refused:assert not value.get('success'),value;return value
        assert response.status_code==200 and value.get('success'),value
        return value['data']
    archive=lambda action,request:http(source_url,'mysql_raw_binlog_',action,request)
    runtime=target=None;cursor=root.cursor();checks=[]
    try:
        runtime=start(review('recover',copied['job_id'],lifetime=600,startup='replay'))
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            runtime=physical('reconcile',{'job_id':runtime['job_id'],'credentials':credentials})
            if runtime['recovery_running']:break
            if runtime.get('remote_observation',{}).get('supervisor_finished'):raise AssertionError(runtime)
            time.sleep(.1)
        else:raise TimeoutError('Writable physical recovery startup')
        identity=runtime['remote_observation']['sql_identity']
        assert identity['log_bin']==1 and identity['super_read_only']==0 and identity['read_only']==0
        assert identity['server_id']==10001+int(use_c) and identity['binlog_format']=='ROW' and identity['log_replica_updates']==1
        ticket=physical('connection_review',{'job_id':runtime['job_id'],'name':'Physical raw replay '+str(use_c),'credentials':credentials})
        attached=physical('connection_connect',{'review_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,
            'delegate_database_credentials':True,'credentials':credentials})
        target=attached['result'];url=endpoint(app,target['server_id'])
        def replay(action,request,refused=False):
            if action in {'inspect','review','archives','boundaries'}:request={**request,'archive_family':'raw'}
            return http(url,'mysql_binlog_replay_',action,request,refused)
        assert replay('inspect',{})['identity']['server_uuid']==identity['server_uuid']
        cursor.execute('FLUSH BINARY LOGS');cursor.execute('SHOW BINARY LOG STATUS');filename=cursor.fetchone()[0];cursor.fetchall()
        for index in range(1,4):
            cursor.execute('INSERT INTO sr_osc.t VALUES(%s,%s,%s)',(index,'physical raw 雪 '+str(index),b'\x00\xff'+bytes([index])))
        cursor.execute('FLUSH BINARY LOGS')
        sealed=archive('review',{'options':{'log_names':[filename]}})
        sealed=wait_job(archive('start',start_request(sealed)),archive,'completed')
        groups=replay('boundaries',{'source_server_id':sid,'archive_job_id':sealed['job_id']})['groups'];assert len(groups)==3
        selected={'source_server_id':sid,'archive_job_id':sealed['job_id'],'options':{'target_confirmation':identity['server_uuid'],
            'stop_mode':'before','stop_file':groups[1]['file'],'stop_position':groups[1]['position']}}
        ticket=replay('review',selected)
        reached=threading.Event();release=threading.Event();original=raw.run_load
        def lost_reply(*args,**kwargs):
            reached.set();assert release.wait(30)
            result=original(*args,**kwargs);assert result['control']['native_load_returned']
            raise ConnectionError('Owned loss of the original raw utility reply and termination observation')
        with patch.object(raw,'run_load',lost_reply):
            try:
                value=replay('start',start_request(ticket));assert reached.wait(30)
                physical('connection_detach',{'server_id':target['server_id']},refused=True)
            finally:release.set()
            unknown=wait_job(value,replay,'unknown')
        assert unknown.get('native_process_termination_confirmed') is not True and unknown['native_load_outcome']=='unknown'
        assert set(unknown['durable_tools'])=={'raw-replay-decoder','raw-replay-client'}
        deadline=time.monotonic()+30
        while app.extensions['cdeadmin_provider_workspace'].mysql_binlog_replay_jobs.workers.get(ticket['job_id']):
            if time.monotonic()>deadline:raise TimeoutError('Original native replay observer did not end')
            time.sleep(.02)
        physical('connection_detach',{'server_id':target['server_id']},refused=True)
        assert replay('start',start_request(ticket))['started_at']==unknown['started_at']
        facts=replay('reconcile',{'job_id':ticket['job_id']});assert facts['reconciliation']['native_lock_free']
        assert facts['native_process_termination_confirmed'] and facts['native_load_outcome']=='unknown'
        assert facts['staged_input_cleanup']['complete']
        assert all(value['cleanup_confirmed'] and value['credential_file_cleanup_confirmed'] and value['input_file_cleanup_confirmed']
            for value in facts['interrupted_utility_observation']['tools'].values())
        replay('acknowledge',{'job_id':ticket['job_id'],'target_confirmation':identity['server_uuid'],'observation_digest':facts['observation_digest']})
        post=lambda action,**body:query_post(client,url,target['database_target_id'],action,**body)
        session=post('open_session',language_profile='mysql-sql')['session_id']
        try:
            assert execute(post,session,'SELECT CAST(id AS CHAR),note,HEX(b) FROM t WHERE id<10 ORDER BY id')['rows']==[['1','physical raw 雪 1','00FF01']]
        finally:post('close_session',session_id=session)
        for mode,count in [('after',2),('all',3)]:
            selected['options']={'target_confirmation':identity['server_uuid'],'stop_mode':mode,
                **({'stop_file':groups[1]['file'],'stop_position':groups[1]['position']} if mode=='after' else {})}
            ticket=replay('review',selected)
            value=wait_job(replay('start',start_request(ticket)),replay,'native_load_returned')
            assert value['result']['native_coverage']['baseline_preserved']==1
            session=post('open_session',language_profile='mysql-sql')['session_id']
            try:
                rows=execute(post,session,'SELECT CAST(id AS CHAR),note,HEX(b) FROM t WHERE id<10 ORDER BY id')['rows']
                assert rows==[[str(i),'physical raw 雪 '+str(i),'00FF0'+str(i)] for i in range(1,count+1)]
            finally:post('close_session',session_id=session)
        from cdeadmin_mysql_physical_shell_qualification import shell_replay
        shell_archive=lambda action,request:http(source_url,'mysql_binlog_',action,request)
        shell_post=lambda action,request,refused=False:http(url,'mysql_binlog_replay_',action,request,refused)
        def reattach(*,refused=False):
            ticket=physical('connection_review',{'job_id':target['binding']['job_id'],'name':target['name'],'credentials':credentials})
            value=physical('connection_connect',{'review_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,
                'delegate_database_credentials':True,'credentials':credentials},refused=refused)
            if not refused:assert value['result']['server_id']==target['server_id'] and value['result']['binding']==target['binding']
            return value
        checks.extend(shell_replay(app,client,sid,root,shell_archive,shell_post,physical,target,url,output,browser_binary,driver_binary,reattach=reattach))
        checks.extend(cancel_independent_replay(app,client,sid,root,archive,replay,physical,target,url,output,browser_binary,driver_binary)['checks'])
        physical('connection_detach',{'server_id':target['server_id']})
        checks.extend(['physical-base-writable-startup-native-GTID-ROW-binlogs-and-separate-leased-raw-replay-registration',
            'native-mysqlbinlog-mysql-before-after-all-replay-exact-selected-Unicode-BLOB-data',
            'active-native-raw-utility-refuses-detach-and-original-lost-reply-remains-unknown-after-independent-observation'])
        return checks
    finally:
        if runtime:
            physical('cancel',{'job_id':runtime['job_id'],'credentials':credentials})
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                value=physical('reconcile',{'job_id':runtime['job_id'],'credentials':credentials})
                if value.get('remote_observation',{}).get('supervisor_finished'):break
                time.sleep(.1)
            else:raise TimeoutError('Writable physical recovery did not stop')
        cursor.execute('DELETE FROM sr_osc.t WHERE id<1000');cursor.close()


def cancel_independent_replay(app,client,sid,root,archive,replay,physical,target,url,output,browser_binary=None,driver_binary=None,*,family='raw',lose_transport=False,reattach=None):
    """Lose only the original observer; the real native client stays blocked."""
    from flask_login import login_user
    from pgadmin.model import User,Server
    from pgadmin.cdeadmin.sdk import durable_tool
    native=connection=cursor=None
    with app.test_request_context('/'):
        registered=Server.query.get(target['server_id']);login_user(User.query.get(registered.user_id))
        job_owner=registered.user_id;job_endpoint=registered.endpoint_profile.id
        service=app.extensions['cdeadmin_provider_workspace'];context,payload,_=service.endpoint_service.workspace(registered,database_target_id=None)
        provider=service.endpoint_service.provider_registry.resolve(context).instance
        native=provider.client;connection=native._connect({'route':payload['route']});cursor=connection.cursor()
        cursor.execute('LOCK TABLES sr_osc.t READ')
    source=root.cursor();ticket=None
    try:
        source.execute('FLUSH BINARY LOGS');source.execute('SHOW BINARY LOG STATUS');filename=source.fetchone()[0];source.fetchall()
        source.execute('INSERT INTO sr_osc.t VALUES(%s,%s,%s)',(15 if lose_transport else 4 if family=='raw' else 14,'cancelled native outcome stays unknown',b'\x00\xff\x04'))
        source.execute('FLUSH BINARY LOGS')
        selected_archive={'log_names':[filename]} if family=='raw' else {'start_file':filename,'start_position':'4','compression':'zstd','threads':1}
        sealed=archive('review',{'options':selected_archive});sealed=wait_job(archive('start',start_request(sealed)),archive,'completed')
        selected={'source_server_id':sid,'archive_job_id':sealed['job_id'],'options':{'target_confirmation':target['binding']['server_uuid']}}
        ticket=replay('review',selected);original=durable_tool.run
        def observer_lost(*args,**kwargs):
            if kwargs.get('name')==('raw-replay-client' if family=='raw' else 'shell-replay-client'):
                callback=kwargs.get('progress')
                def progress(event):
                    if callback:callback(event)
                    if event.get('pid'):raise SystemExit('Owned original native observer loss')
                kwargs['progress']=progress
            return original(*args,**kwargs)
        with patch.object(durable_tool,'run',observer_lost):
            unknown=wait_job(replay('start',start_request(ticket)),replay,'unknown')
        deadline=time.monotonic()+30
        while service.mysql_binlog_replay_jobs.workers.get(ticket['job_id']):
            if time.monotonic()>deadline:raise TimeoutError('Original native observer remained active')
            time.sleep(.02)
        assert unknown['utility_cancellation_available'] and unknown.get('native_process_termination_confirmed') is not True
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            facts=replay('reconcile',{'job_id':ticket['job_id']})
            if facts['reconciliation']['native_lock_free'] is False and facts['reconciliation'].get('native_principal_work_free') is False:break
            assert not facts['native_process_termination_confirmed'],facts
            time.sleep(.1)
        else:raise TimeoutError('Original native replay did not acquire its SQL lock')
        assert facts['native_load_outcome']=='unknown'
        if family=='shell':
            job=service.mysql_binlog_replay_jobs.load(ticket['job_id'],job_owner,job_endpoint)
            request=json.loads((service.mysql_binlog_replay_jobs.directory(job)/'.cdeadmin-tool-shell-replay-client'/'request.json').read_text())
            reserved=request['endpoint_reservation']
            assert os.readlink('/proc/'+str(facts['progress']['pid'])+'/fd/'+str(reserved['fd']))=='socket:['+str(reserved['inode'])+']'
        assert not facts['interrupted_utility_observation']['native_process_termination_confirmed']
        replay('acknowledge',{'job_id':ticket['job_id'],'target_confirmation':target['binding']['server_uuid'],'observation_digest':facts['observation_digest']},refused=True)
        if lose_transport:
            from pgadmin.cdeadmin.providers.mysql_family.mysql_recovery_bridge import bridges
            original_bridge=bridges.get(target['binding']);original_bridge.close()
            try:cursor.close()
            except Exception:pass
            cursor=None
            try:native._discard_failed_session(connection)
            finally:connection=None
            assert original_bridge.users==1
            replay('reconcile',{'job_id':ticket['job_id']},refused=True)
            reattach(refused=True)
            if browser_binary:
                browser_cancel(app,output,target,ticket['job_id'],browser_binary,driver_binary,lambda:None,
                    folder='lost-transport-replay-desktop',reattach=reattach)
            else:
                replay('cancel',{'job_id':ticket['job_id']})
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    stopped=replay('observe_utilities',{'job_id':ticket['job_id']})
                    if stopped['native_process_termination_confirmed']:break
                    time.sleep(.1)
                else:raise TimeoutError('Original utility stop could not be observed without SQL transport')
                assert stopped['native_load_outcome']=='unknown' and stopped['staged_input_cleanup']['complete']
                assert stopped['recovery_utility_release']['released_reservations']==1 and original_bridge.users==0
                replay('acknowledge',{'job_id':ticket['job_id'],'target_confirmation':target['binding']['server_uuid'],'observation_digest':facts['observation_digest']},refused=True)
                reattach()
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    facts=replay('reconcile',{'job_id':ticket['job_id']})
                    if facts['reconciliation']['native_lock_free'] and facts['reconciliation'].get('native_principal_work_free') is True:break
                    time.sleep(.1)
                else:raise TimeoutError('Original native SQL work still holds the replay lock')
                replay('acknowledge',{'job_id':ticket['job_id'],'target_confirmation':target['binding']['server_uuid'],'observation_digest':facts['observation_digest']})
            final=replay('status',{'job_id':ticket['job_id']})
            assert final['target_state_acknowledged_at'] and final['native_load_outcome']=='unknown' and final['native_process_termination_confirmed']
            return {'checks':['original-native-'+family+'-utility-observation-with-lost-SSH-transport-releases-only-its-lease-before-reviewed-reattachment-and-fresh-SQL-acknowledgement'],'archive_job_id':sealed['job_id']}
        if browser_binary:
            def unlock():
                nonlocal cursor,connection
                cursor.execute('UNLOCK TABLES');cursor.close();cursor=None
                native._discard_failed_session(connection);connection=None
            browser_cancel(app,output,target,ticket['job_id'],browser_binary,driver_binary,unlock,folder='independent-replay-desktop' if family=='raw' else 'shell-independent-replay-desktop')
            facts=replay('reconcile',{'job_id':ticket['job_id']})
            assert facts['target_state_acknowledged_at'] and facts['native_load_outcome']=='unknown' and facts['native_process_termination_confirmed']
            assert facts['staged_input_cleanup']['complete']
            assert all(value.get('cleanup_confirmed') and value.get('credential_file_cleanup_confirmed') and value.get('input_file_cleanup_confirmed')
                for value in facts['interrupted_utility_observation']['tools'].values())
            return {'checks':['built-original-unknown-'+family+'-replay-native-cancellation-termination-facts-and-explicit-target-acknowledgement'],'archive_job_id':sealed['job_id']}
        replay('cancel',{'job_id':ticket['job_id']})
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            facts=replay('reconcile',{'job_id':ticket['job_id']})
            if facts['native_process_termination_confirmed']:break
            time.sleep(.1)
        else:raise TimeoutError('Independent native replay cancellation was not observed')
        if not facts['reconciliation']['native_lock_free'] or not facts['reconciliation'].get('native_principal_work_free'):
            replay('acknowledge',{'job_id':ticket['job_id'],'target_confirmation':target['binding']['server_uuid'],'observation_digest':facts['observation_digest']},refused=True)
        cursor.execute('UNLOCK TABLES');cursor.close();cursor=None
        native._discard_failed_session(connection);connection=None
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            facts=replay('reconcile',{'job_id':ticket['job_id']})
            if facts['reconciliation']['native_lock_free'] and facts['reconciliation'].get('native_principal_work_free') is True:break
            time.sleep(.1)
        else:raise TimeoutError('Original native replay SQL lock remained active')
        assert facts['native_load_outcome']=='unknown' and facts['staged_input_cleanup']['complete']
        assert all(value.get('cleanup_confirmed') and value.get('credential_file_cleanup_confirmed') and value.get('input_file_cleanup_confirmed')
            for value in facts['interrupted_utility_observation']['tools'].values())
        replay('acknowledge',{'job_id':ticket['job_id'],'target_confirmation':target['binding']['server_uuid'],'observation_digest':facts['observation_digest']})
        (output/('independent-native-'+family+'-replay-'+str(target['server_id'])+'.json')).write_text(json.dumps(facts,indent=2)+'\n')
        return {'checks':['independent-native-'+family+'-client-cancel-after-observer-loss-preserves-unknown-data-outcome-and-proves-utility-input-credential-cleanup'],'archive_job_id':sealed['job_id']}
    finally:
        if ticket:replay('cancel',{'job_id':ticket['job_id']})
        if cursor is not None:
            try:cursor.execute('UNLOCK TABLES')
            finally:cursor.close()
        if connection is not None:native._discard_failed_session(connection)
        source.close()


def browser_cancel(app,output,target,job_id,binary,driver_binary,unlock,*,folder='independent-replay-desktop',reattach=None):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action
    evidence=output/folder;evidence.mkdir(mode=0o700)
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1900,1600'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(evidence/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,90);ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def target_node(b):
            return next((e for e in b.find_elements(By.CSS_SELECTOR,'.file-name') if e.is_displayed() and b.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',e,target['server_id'])),None)
        invoke_context_action(wait,driver,wait.until(target_node),('Restore','MySQL binary-log replay...'),handle_endpoint_prompt=False)
        def click(text):
            node=wait.until(lambda b:next((e for e in b.find_elements(By.TAG_NAME,'button') if e.is_displayed() and e.is_enabled() and e.text==text),None))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
        click('Load replay jobs')
        inspect=wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'button[aria-label="Inspect replay '+job_id+'"]'));inspect.click()
        if reattach:
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                click('Inspect original replay utilities')
                wait.until(lambda b:next((e for e in b.find_elements(By.TAG_NAME,'button') if e.is_enabled() and e.text=='Inspect original replay utilities'),None))
                original=json.loads(driver.find_element(By.CSS_SELECTOR,'[aria-label="Original replay utility observations"]').text)
                if original['utilities']['native_process_termination_confirmed']:break
                time.sleep(.1)
            else:raise TimeoutError('Built original utility inspection did not observe termination while the SQL relay was absent')
            assert original['recovery_utility_release']['released_reservations']==1
            assert not driver.find_elements(By.XPATH,'//button[normalize-space()="Acknowledge facts and release target fence"]')
            reattach()
        click('Inspect current target facts')
        def facts():
            wait.until(lambda b:next((e for e in b.find_elements(By.TAG_NAME,'button') if e.is_displayed() and e.is_enabled() and e.text=='Inspect current target facts'),None))
            return json.loads(wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'[aria-label="Native replay reconciliation"]')).text)
        if not reattach:
            assert wait.until(lambda b:facts().get('native_lock_free') is False)
            assert not driver.find_element(By.XPATH,'//button[normalize-space()="Acknowledge facts and release target fence"]').is_enabled()
            click('Cancel replay')
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                click('Inspect current target facts')
                if facts().get('native_utilities',{}).get('native_process_termination_confirmed'):break
                time.sleep(.1)
            else:raise TimeoutError('Built native utility cancellation did not terminate its original process')
            unlock()
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            click('Inspect current target facts')
            if facts().get('native_lock_free') and facts().get('native_principal_work_free') is True:break
            time.sleep(.1)
        else:raise TimeoutError('Built original native SQL lock did not end')
        label=driver.find_element(By.XPATH,'//label[normalize-space()="Acknowledge uncertain target UUID"]')
        value=wait.until(lambda b:(e if (e:=b.find_element(By.ID,label.get_attribute('for'))).is_enabled() else None))
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});',value)
        value.send_keys(Keys.CONTROL,'a');value.send_keys(target['binding']['server_uuid'])
        click('Acknowledge facts and release target fence')
        wait.until(lambda b:'original native load outcome remains uncertain' in b.find_element(By.TAG_NAME,'body').text)
        driver.save_screenshot(str(evidence/'native-independent-replay.png'))
        errors=[v for v in driver.get_log('browser') if v['level']=='SEVERE'];assert not errors,errors
        (evidence/'summary.json').write_text(json.dumps({'complete':True,'console_errors':errors,'original_native_outcome':'unknown','native_utility_termination_observed':True},indent=2)+'\n')
    except BaseException:
        if driver:driver.save_screenshot(str(evidence/'browser-failure.png'));(evidence/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=5)


def browser_replay(app,output,sid,password,target,root,binary,driver_binary):
    from pgadmin.model import db,Server
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_recovery_connection_qualification import endpoint,query_post,execute
    from cdeadmin_mysql_binlog_replay_workspace_qualification import browser
    with app.test_request_context('/'):
        source=Server.query.get(sid);route={'host':source.host,'port':source.port};username=source.username;owner=source.user_id
    alias,_selected,_post=registration(app,route,password,True,username=username)
    with app.test_request_context('/'):
        source=Server.query.get(alias);source.name='Owned replay archive source';db.session.commit()
    client=app.test_client()
    with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
    source_url=endpoint(app,alias);url=endpoint(app,target['server_id'])
    def archive(family,action,request):
        response=client.post(source_url,json={'action':('mysql_raw_binlog_' if family=='raw' else 'mysql_binlog_')+action,'request':request});value=response.get_json()
        assert response.status_code==200 and value.get('success'),value
        return value['data']
    cursor=root.cursor()
    try:
        checks=[]
        for family,row in [('raw',1001001),('shell',1001002)]:
            cursor.execute('FLUSH BINARY LOGS');cursor.execute('SHOW BINARY LOG STATUS');filename=cursor.fetchone()[0];cursor.fetchall()
            note='desktop '+family+' replay 雪'
            cursor.execute('INSERT INTO sr_osc.t VALUES(%s,%s,%s)',(row,note,b'\x00\xff\x7f'))
            cursor.execute('FLUSH BINARY LOGS')
            selected={'log_names':[filename]} if family=='raw' else {'start_file':filename,'start_position':'4','compression':'zstd','threads':1}
            sealed=archive(family,'review',{'options':selected})
            source_post=lambda action,request:archive(family,action,request)
            sealed=wait_job(archive(family,'start',start_request(sealed)),source_post,'completed')
            evidence=output/(family+'-replay-desktop');evidence.mkdir(mode=0o700)
            value=browser(app,evidence,target['server_id'],alias,sealed['job_id'],target['binding']['server_uuid'],binary,driver_binary,raw=family=='raw')
            value['source_offline']=False
            (evidence/'summary.json').write_text(json.dumps(value,indent=2)+'\n')
            post=lambda action,**body:query_post(client,url,target['database_target_id'],action,**body)
            session=post('open_session',language_profile='mysql-sql')['session_id']
            try:assert execute(post,session,'SELECT CAST(id AS CHAR),note,HEX(b) FROM t WHERE id='+str(row))['rows']==[[str(row),note,'00FF7F']]
            finally:post('close_session',session_id=session)
            checks.append('built-recovery-target-menu-reviewed-native-'+family+'-replay-and-independent-exact-data')
        return checks
    finally:
        cursor.execute('DELETE FROM sr_osc.t WHERE id IN(1001001,1001002)');cursor.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--fixture-image',default='sr-mysql-physical:phase213')
    parser.add_argument('--mysql-shell',required=True)
    parser.add_argument('--private-key');parser.add_argument('--prepare-fixture',action='store_true');parser.add_argument('--decoder',required=True);parser.add_argument('--client',required=True)
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');parser.add_argument('--retention',action='store_true');parser.add_argument('--retention-only',action='store_true');parser.add_argument('--batch-only',action='store_true');parser.add_argument('--schedule-only',action='store_true');parser.add_argument('--backup-only',action='store_true');args=parser.parse_args()
    os.environ['CDEADMIN_MYSQL_BINLOG_BINARY']=str(Path(args.decoder).resolve(strict=True));os.environ['CDEADMIN_MYSQL_CLIENT_BINARY']=str(Path(args.client).resolve(strict=True))
    os.environ['CDEADMIN_MYSQLSH_BINARY']=str(Path(args.mysql_shell).resolve(strict=True))
    from cdeadmin_mysql_physical_qualification import qualify
    qualify(args.output,args.fixture_image,args.private_key,args.prepare_fixture,args.browser_binary,args.driver_binary,connections=True,replay=True,retention=args.retention,retention_only=args.retention_only,batch_only=args.batch_only,schedule_only=args.schedule_only,backup_only=args.backup_only)
