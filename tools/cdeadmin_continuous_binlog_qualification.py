#!/usr/bin/env python3
"""Owned MySQL/MariaDB active raw reception and sealed native snapshot proof."""
import argparse
import builtins
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'web'),str(ROOT/'tools'),str(ROOT)]


def qualify(output,family,decoder,*,use_c=False,gtid_mode='ON',browser_binary=None,driver_binary=None):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside the source checkout')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    proof={'complete':False,'checks':[],'history_testing':'not run','full_product_complete':False,
        'family':family,'interface':'mysql-c' if use_c else 'mysql-python' if family=='mysql' else 'mariadb-native',
        'source_sha256':{},'data_recovery_verified':False}
    for directory in ('web/pgadmin/cdeadmin/providers/mysql_family','web/pgadmin/cdeadmin/workspace'):
        for path in (ROOT/directory).glob('*binlog*.py'):
            proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    decoder=Path(decoder).resolve(strict=True)
    os.environ['CDEADMIN_'+('MYSQL_BINLOG_BINARY' if family=='mysql' else 'MARIADB_BINLOG_BINARY')]=str(decoder)
    builtins.SERVER_MODE=None
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False;config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    config.DATA_DIR=str(output/'app');config.SQLITE_PATH=str(output/'app/application.db')
    config.SESSION_DB_PATH=str(output/'app/sessions');config.STORAGE_DIR=str(output/'app/storage')
    config.LOG_FILE=str(output/'app/application.log');config.AZURE_CREDENTIAL_CACHE_DIR=str(output/'app/azure')
    config.CDEADMIN_OPERATION_STORE_PATH=str(output/'app/operations.json')
    setattr(config,'CDEADMIN_'+family.upper()+'_CONTINUOUS_BINLOG_ROOT',str(output/'receivers'))
    setattr(config,'CDEADMIN_'+family.upper()+('_RAW_BINLOG_ROOT' if family=='mysql' else '_BINLOG_ROOT'),str(output/'archives'))
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from flask import url_for
    from mysql_qualification_support import _root_connection
    if family=='mysql':
        from mysql_qualification_support import server
        fixture_options={'gtid_mode':gtid_mode}
    else:
        from mariadb_qualification_support import server
        fixture_options={}
    app=create_app('ScratchRobin-native-continuous-'+family);app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start();client=app.test_client();jobs=None
    password='receiver LF\nquote"slash\\雪-'+secrets.token_urlsafe(24)
    prefix=family+'_binlog_capture_';archive_prefix='mysql_raw_binlog_' if family=='mysql' else 'mariadb_binlog_'
    try:
        with server(output/'fixture',**fixture_options) as (route,container,fixture):
            native=_root_connection(family,route['port']);native.autocommit=True;query=native.cursor()
            try:
                query.execute("CREATE USER 'sr_receiver'@'%' IDENTIFIED BY %s",(password,))
                query.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_receiver'@'%' WITH GRANT OPTION")
                query.execute('CREATE DATABASE sr_receiver_data CHARACTER SET utf8mb4')
                query.execute('CREATE TABLE sr_receiver_data.t(id BIGINT PRIMARY KEY,body TEXT,payload BLOB)')
                query.execute('FLUSH BINARY LOGS')
                query.execute('SHOW BINARY LOG STATUS' if family=='mysql' else 'SHOW MASTER STATUS');start_file=query.fetchone()[0];query.fetchall()
                query.execute('SELECT @@global.log_bin_basename');native_directory=str(PurePosixPath(query.fetchone()[0]).parent)
                with app.test_request_context('/'):
                    user=User.query.first();group=ServerGroup.query.filter_by(user_id=user.id).order_by(ServerGroup.id).first()
                    app.blueprints['NODE-engine_type'].connector_visibility[family].set(True,user_id=user.id)
                    registered=Server(user_id=user.id,servergroup_id=group.id,name='Owned continuous '+family,
                        host=route['host'],port=route['port'],username='sr_receiver',maintenance_db=None,save_password=0)
                    registered._cde_endpoint_registration=registration_profile(family+'-native')
                    registered._cde_endpoint_route_configuration={**route,'user':'sr_receiver','credential_kinds':['database_password'],**({'use_pure':not use_c} if family=='mysql' else {})}
                    db.session.add(registered);db.session.commit()
                    uid,endpoint,registered_id=user.id,registered.endpoint_profile.id,registered.id
                    verify_url=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=registered.id)
                    workspace_url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=registered.id)
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                assert client.post(verify_url,json={'password':password}).get_json().get('success')
                def http(action,request,*,archive=False,refused=False):
                    response=client.post(workspace_url,json={'action':(archive_prefix if archive else prefix)+action,'request':request})
                    value=response.get_json()
                    if refused:assert response.status_code==400 and not value.get('success');return value
                    if response.status_code!=200 or not value.get('success'):
                        (output/'http-failure.json').write_text(json.dumps(value,indent=2).replace(password,'<redacted>')+'\n')
                        raise AssertionError('Native continuous '+family+' HTTP '+action+' failed')
                    return value['data']
                captured=http('catalog',{});source_id=int(captured['identity']['server_id'])
                refused=http('review',{'options':{'start_file':start_file,'receiver_server_id':source_id}},refused=True)
                assert 'different' in refused['errormsg']
                reviewed=http('review',{'options':{'start_file':start_file,'receiver_server_id':4000000101,'timeout_seconds':None}})
                request={'job_id':reviewed['job_id'],'review_digest':reviewed['review_digest'],'confirmed':True}
                started=http('start',request);assert http('start',request)['job_id']==started['job_id']
                service=service_for_app(app);jobs=getattr(service,family+'_continuous_binlog_jobs')
                private=jobs.load(started['job_id'],uid,endpoint);receiving=jobs.directory(private)/'receiving'
                def wait(predicate):
                    deadline=time.monotonic()+90
                    while True:
                        current=http('status',{'job_id':started['job_id']})
                        if predicate(current):return current
                        if current['state'] in {'failed','unknown','not_dispatched','cancelled'}:
                            (output/'receiver-failure.json').write_text(json.dumps(current,indent=2)+'\n')
                            raise AssertionError('Owned native receiver stopped: '+current['state'])
                        if time.monotonic()>deadline:raise TimeoutError('Owned native continuous receiver deadline')
                        time.sleep(.1)
                wait(lambda r:r['state']=='active' and (receiving/start_file).is_file() and (receiving/start_file).stat().st_size>=4)
                first_size=(receiving/start_file).stat().st_size
                query.execute('INSERT INTO sr_receiver_data.t VALUES(%s,%s,%s)',(9007199254740993,'Native 😀 0',b'\x00\x80\xff'))
                active=wait(lambda r:(receiving/start_file).stat().st_size>first_size)
                assert not active.get('progress',{}).get('last_archive_job_ids')
                query.execute('FLUSH BINARY LOGS')
                first=wait(lambda r:r.get('progress',{}).get('published_batches',0)>=1)
                query.execute('INSERT INTO sr_receiver_data.t VALUES(%s,%s,%s)',(9007199254740994,'Native 😀 1',b'\xff\x00'))
                query.execute('FLUSH BINARY LOGS')
                second=wait(lambda r:r.get('progress',{}).get('published_batches',0)>=2)
                http('cancel',{'job_id':started['job_id']})
                stopped=wait(lambda r:r['state']=='cancelled')
                assert stopped['native_process_termination_confirmed'] is True
                assert stopped['result']['published_batches']==2 and len(stopped['result']['last_archive_job_ids'])==2
                assert http('start',request)['state']=='cancelled'
                proof['checks'].extend(['native-explicit-receiver-id-and-once-only-dispatch',
                    'native-active-tail-grows-before-rotation-and-is-never-offered-as-a-complete-archive',
                    'native-two-successive-closed-batches-publish-while-one-receiver-remains-active',
                    'native-cancel-confirms-process-cleanup-and-never-restarts-the-receiver'])
                snapshots=[]
                for job_id in stopped['result']['last_archive_job_ids']:
                    archived=http('status',{'job_id':job_id},archive=True);assert archived['state']=='completed'
                    assert archived['continuation']['continuous_receiver_job_id']==started['job_id']
                    files=http('files',{'job_id':job_id,'limit':100},archive=True)['files'];checks=[]
                    for row in files:
                        response=client.post(workspace_url,data={'action':archive_prefix+'download','payload':json.dumps({'job_id':job_id,'path':row['path']})})
                        assert response.status_code==200
                        data=response.data;response.close();assert hashlib.sha256(data).hexdigest()==row['sha256']
                        if row['path']=='archive.json':continue
                        original=subprocess.run(['docker','exec',container,'cat',native_directory+'/'+row['path']],check=True,capture_output=True,timeout=15).stdout
                        assert len(original)==len(data)
                        # Native FDE in-use is a mutable file flag, excluded
                        # from the vendor event CRC. Compare every other byte.
                        left,right=bytearray(data),bytearray(original)
                        assert left[:4]==right[:4]==b'\xfebin' and left[8]==right[8]==15
                        left[21]&=254;right[21]&=254;assert left==right
                        checks.append({'file':row['path'],'bytes':str(len(data)),'sha256':row['sha256'],
                            'source_bytes_match_except_native_mutable_fde_in_use_flag':True})
                    assert checks;snapshots.append({'job_id':job_id,'files':checks})
                query.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_receiver_data.t ORDER BY id')
                assert query.fetchall()==[('9007199254740993','Native 😀 0','0080FF'),('9007199254740994','Native 😀 1','FF00')]
                proof['checks'].append('native-sealed-snapshots-pass-independent-source-frame-byte-comparison-and-authenticated-download')
                proof.update(receiver_job_id=started['job_id'],source=stopped['source'],program=stopped['program'],snapshots=snapshots)
                reconciled=http('reconcile_writer',{'job_id':started['job_id'],'confirmed':True})
                assert reconciled['writer_reconciliation']['process_scope_stopped']
                assert reconciled['writer_reconciliation']['artifact_verified'] is False
                resume={'resume_job_id':started['job_id'],'options':{'start_file':stopped['result']['next_file'],
                    'receiver_server_id':4000000103,'timeout_seconds':None}}
                restarted_review=http('review',resume)
                assert restarted_review['job_id']!=started['job_id']
                assert restarted_review['continuation']['previous_receiver_job_id']==started['job_id']
                restarted_request={'job_id':restarted_review['job_id'],'review_digest':restarted_review['review_digest'],'confirmed':True}
                from copy import deepcopy
                from unittest.mock import patch
                from pgadmin.cdeadmin.providers.mysql_family.continuous_binlog import adapter
                native_adapter=adapter(family);capture=native_adapter.capture
                def different_source(connection):
                    changed=deepcopy(capture(connection));key='server_uuid' if family=='mysql' else 'server_uid'
                    changed['identity'][key]='different-native-source-fault-injection';return changed
                with patch.object(native_adapter,'capture',different_source):
                    assert 'different native source' in http('review',resume,refused=True)['errormsg']
                    assert 'different native source' in http('start',restarted_request,refused=True)['errormsg']
                assert http('status',{'job_id':restarted_review['job_id']})['state']=='reviewed'
                proof['checks'].append('fault-injected-native-source-identity-change-refuses-both-restart-review-and-dispatch')
                original=started;started=http('start',restarted_request)
                private=jobs.load(started['job_id'],uid,endpoint);receiving=jobs.directory(private)/'receiving'
                wait(lambda r:r['state']=='active' and (receiving/resume['options']['start_file']).is_file())
                query.execute('INSERT INTO sr_receiver_data.t VALUES(%s,%s,%s)',(9007199254740996,'Reviewed restart 😀',b'\x00\xfe'))
                query.execute('FLUSH BINARY LOGS')
                resumed=wait(lambda r:r.get('progress',{}).get('published_batches',0)>=1)
                http('cancel',{'job_id':started['job_id']});resumed=wait(lambda r:r['state']=='cancelled')
                assert resumed['native_process_termination_confirmed']
                assert http('start',restarted_request)['state']=='cancelled'
                checkpoint_archive=http('status',{'job_id':resumed['result']['last_archive_job_ids'][0]},archive=True)
                assert checkpoint_archive['options']['log_names'][0]==resume['options']['start_file']
                query.execute('SHOW BINARY LOG STATUS' if family=='mysql' else 'SHOW MASTER STATUS');latest=query.fetchone()[0];query.fetchall()
                query.execute('PURGE BINARY LOGS TO %s',(latest,))
                refused=http('review',resume,refused=True);assert 'purged' in refused['errormsg']
                proof['checks'].extend(['native-clean-stop-reconciliation-preserves-artifact-and-remote-finality-separation',
                    'native-new-reviewed-restart-rereads-exact-checkpoint-with-new-receiver-identity-and-seals-next-batch',
                    'native-purged-restart-checkpoint-is-refused-without-guessing-a-successor'])
                from native_binlog_qualification_support import waiting_binlog
                interrupted=http('review',{'options':{'start_file':latest,'receiver_server_id':4000000104}})
                interrupted_record=jobs.load(interrupted['job_id'],uid,endpoint)
                directory=jobs.directory(interrupted_record)
                with waiting_binlog(directory,decoder,family,orphan=True) as orphan, waiting_binlog(directory.parent/'owned-neighbor',decoder,family) as neighbor:
                    jobs.update(interrupted_record,state='active',worker_identity=[999999999,0],started_at=time.time()-1)
                    assert http('status',{'job_id':interrupted['job_id']})['state']=='unknown'
                    reconciled=http('reconcile_writer',{'job_id':interrupted['job_id'],'confirmed':True})
                    assert reconciled['state']=='unknown' and reconciled['writer_reconciliation']['processes'][0]['pid']==orphan.pid
                    assert neighbor.is_running() and neighbor.status()!='zombie'
                    assert http('reconcile_writer',{'job_id':interrupted['job_id'],'confirmed':True})['writer_reconciliation']==reconciled['writer_reconciliation']
                    refused=http('review',{'resume_job_id':interrupted['job_id'],'options':{'start_file':latest,'receiver_server_id':4000000105}},refused=True)
                    assert 'clean stopped' in refused['errormsg']
                proof['checks'].append('native-orphan-before-first-heartbeat-stopped-through-owned-HTTP-reconciliation-while-neighbor-survives-and-unknown-cannot-restart')
                started=original
                # Lose publication after a real native rotation, retaining a
                # complete closed file plus its following local native file.
                query.execute('FLUSH BINARY LOGS')
                query.execute('SHOW BINARY LOG STATUS' if family=='mysql' else 'SHOW MASTER STATUS');tail_name=query.fetchone()[0];query.fetchall()
                tail_parent=http('review',{'options':{'start_file':tail_name,'receiver_server_id':4000000106}})
                from pgadmin.cdeadmin.providers.mysql_family.continuous_binlog import ReceiverTransport
                original_publish=ReceiverTransport.publish
                def lost_publication(transport,parent,*args,**kwargs):
                    if parent['job_id']==tail_parent['job_id']:raise BinlogArchiveError('Owned qualification publication fault')
                    return original_publish(transport,parent,*args,**kwargs)
                from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
                with patch.object(ReceiverTransport,'publish',lost_publication):
                    started=http('start',{'job_id':tail_parent['job_id'],'review_digest':tail_parent['review_digest'],'confirmed':True})
                    tail_record=jobs.load(started['job_id'],uid,endpoint);receiving=jobs.directory(tail_record)/'receiving'
                    wait(lambda r:r['state']=='active' and (receiving/tail_name).is_file())
                    query.execute('INSERT INTO sr_receiver_data.t VALUES(%s,%s,%s)',(9007199254740997,'Stopped tail 😀',b'\x00\xfd'))
                    query.execute('FLUSH BINARY LOGS');failed=wait(lambda r:r['state']=='failed')
                    assert failed['native_process_termination_confirmed']
                http('reconcile_writer',{'job_id':tail_parent['job_id'],'confirmed':True})
                candidates=http('tail_catalog',{'job_id':tail_parent['job_id']})
                assert next(row for row in candidates['logs'] if row['Log_name']==tail_name)['eligible']
                assert any(not row['eligible'] for row in candidates['logs'])
                adoption={'job_id':tail_parent['job_id'],'options':{'log_names':[tail_name],'timeout_seconds':None}}
                adopt_review=http('tail_review',adoption)
                source_file=receiving/tail_name
                info=source_file.stat();os.utime(source_file,ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
                refused=http('start',{'job_id':adopt_review['job_id'],'review_digest':adopt_review['review_digest'],'confirmed':True},archive=True,refused=True)
                assert 'postimages changed' in refused['errormsg']
                adopt_review=http('tail_review',adoption)
                adopt_request={'job_id':adopt_review['job_id'],'review_digest':adopt_review['review_digest'],'confirmed':True}
                with patch.object(native_adapter,'capture',different_source):
                    assert 'different native source' in http('tail_review',adoption,refused=True)['errormsg']
                    assert 'different native source' in http('tail_start',adopt_request,refused=True)['errormsg']
                # The ordinary archive Start route must preserve the stopped-
                # receiver admission rather than redispatch remote retrieval.
                http('start',adopt_request,archive=True)
                deadline=time.monotonic()+90
                while True:
                    adopted=http('status',{'job_id':adopt_review['job_id']},archive=True)
                    if adopted['state']=='completed':break
                    assert adopted['state'] in {'dispatching','active'},adopted.get('error_message')
                    if time.monotonic()>deadline:raise TimeoutError('Stopped-file native archive deadline')
                    time.sleep(.1)
                assert adopted['result']['adopted_stopped_files'] and adopted['result']['parent_outcome_rewritten'] is False
                assert http('status',{'job_id':tail_parent['job_id']})['state']=='failed'
                assert http('start',adopt_request,archive=True)['state']=='completed'
                files=http('files',{'job_id':adopt_review['job_id']},archive=True)['files']
                row=next(row for row in files if row['path']==tail_name)
                response=client.post(workspace_url,data={'action':archive_prefix+'download','payload':json.dumps({'job_id':adopt_review['job_id'],'path':tail_name})})
                data=response.data;assert response.status_code==200 and hashlib.sha256(data).hexdigest()==row['sha256'];response.close()
                source_bytes=subprocess.run(['docker','exec',container,'cat',native_directory+'/'+tail_name],check=True,capture_output=True,timeout=15).stdout
                left,right=bytearray(data),bytearray(source_bytes);left[21]&=254;right[21]&=254;assert left==right
                original_size=source_file.stat().st_size
                with source_file.open('ab') as stream:stream.write(b'\x00');stream.flush();os.fsync(stream.fileno())
                assert 'incomplete' in http('tail_review',adoption,refused=True)['errormsg']
                with source_file.open('r+b') as stream:stream.truncate(original_size);stream.flush();os.fsync(stream.fileno())
                proof['checks'].extend(['fault-injected-publication-loss-retains-real-native-closed-file-and-active-tail',
                    'native-stopped-file-review-rejects-active-incomplete-mutated-and-changed-source-inputs',
                    'native-stopped-file-adoption-uses-real-parser-CRC-and-source-byte-comparison-with-independent-archive-download',
                    'ordinary-archive-start-preserves-stopped-file-admission-and-once-only-dispatch-without-rewriting-failed-parent'])
                proof['stopped_tail']={'receiver_job_id':tail_parent['job_id'],'archive_job_id':adopt_review['job_id'],'log_name':tail_name,'bytes':str(len(data))}
                started=original
                if browser_binary:
                    query.execute('FLUSH BINARY LOGS')
                    query.execute('SHOW BINARY LOG STATUS' if family=='mysql' else 'SHOW MASTER STATUS');browser_start=query.fetchone()[0];query.fetchall()
                    def browser_started():
                        deadline=time.monotonic()+30
                        while True:
                            records=jobs.list(uid,endpoint)['jobs']
                            selected=next((r for r in records if r['job_id']!=started['job_id'] and r['options']['start_file']==browser_start),None)
                            if selected is not None and (jobs.directory(jobs.load(selected['job_id'],uid,endpoint))/'receiving'/browser_start).is_file():break
                            if time.monotonic()>deadline:raise TimeoutError('Browser owned receiver connection deadline')
                            time.sleep(.1)
                        query.execute('INSERT INTO sr_receiver_data.t VALUES(%s,%s,%s)',(9007199254740995,'Browser Native 😀',b'\x00\xff'))
                        query.execute('FLUSH BINARY LOGS')
                        return selected['job_id']
                    proof['browser']=browser(app,output,registered_id,family,browser_start,browser_binary,driver_binary,browser_started,
                        stopped_tail=proof['stopped_tail'])
                    proof['checks'].append('native-browser-reviews-starts-observes-cancels-receiver-and-opens-its-produced-archive')
                print('Native '+family+' continuous reception, two sealed batches and cancellation passed',flush=True)
            finally:query.close();native.close()
        assert fixture['owned_server_stopped'];proof['complete']=True
    finally:
        if jobs is not None:jobs.close()
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def browser(app,output,server_id,family,start_file,binary,driver_binary,on_started,*,stopped_tail=None):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand
    http=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for value in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1600,1000','--user-data-dir='+str(output/'browser-profile')):options.add_argument(value)
        options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary) if driver_binary else Service())
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/');wait=WebDriverWait(driver,75)
        ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MariaDB' if family=='mariadb' else 'MySQL')
        def target(browser):
            return browser.execute_script("""
              const tree=window.pgAdmin.Browser.tree;
              return Array.from(document.querySelectorAll('.file-entry')).find(entry => {
                try {const data=tree.itemData(tree.itemFrom(entry));return data?._type==='server' && String(data._id ?? data.id)===String(arguments[0]);}
                catch {return false;}
              }) || null;
            """,server_id)
        element=wait.until(target);driver.get_log('browser')
        driver.execute_script("""
          const tree=window.pgAdmin.Browser.tree,item=tree.itemFrom(arguments[0]);
          const node=window.pgAdmin.Browser.Nodes.server;
          node.callbacks[arguments[1]].call(node,{item});
        """,element,'open_mariadb_binlogs' if family=='mariadb' else 'open_mysql_raw_binlogs')
        summary=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'summary') if node.text.strip()=='Continuous native binary-log collection'),None))
        driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',summary);summary.click()
        def click(label):
            def attempt(browser):
                from selenium.common.exceptions import ElementClickInterceptedException,StaleElementReferenceException,NoSuchElementException
                try:
                    node=next((node for node in browser.find_elements(By.TAG_NAME,'button') if node.is_enabled() and node.get_attribute('textContent').strip()==label),None)
                    if node is None:return False
                    browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node)
                    if not node.is_displayed():
                        # The workspace can finish its initial remount after
                        # the first disclosure click. Reopen its current DOM
                        # summary through the same user action before retrying.
                        disclosure=node.find_element(By.XPATH,'ancestor::details[1]')
                        if not disclosure.get_attribute('open'):disclosure.find_element(By.TAG_NAME,'summary').click()
                        return False
                    node.click();return True
                except (ElementClickInterceptedException,StaleElementReferenceException,NoSuchElementException):return False
            wait.until(attempt)
        click('Inspect receiver source')
        def field(label):
            node=driver.find_element(By.XPATH,'//label[normalize-space()="'+label+'"]')
            return driver.find_element(By.ID,node.get_attribute('for'))
        def select_start(browser):
            from selenium.common.exceptions import ElementClickInterceptedException,StaleElementReferenceException
            try:
                option=next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.text.startswith(start_file+' (')),None)
                if option is not None:option.click();return True
                selected=field('Receiver starting native log')
                if selected.get_attribute('aria-disabled')=='true':return False
                if selected.get_attribute('aria-expanded')!='true':
                    browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',selected);selected.click()
                return False
            except (ElementClickInterceptedException,StaleElementReferenceException):return False
        wait.until(select_start)
        selected=field('Unique receiver server ID');selected.send_keys('4000000102')
        click('Review continuous receiver');wait.until(lambda browser:browser.find_elements(By.CSS_SELECTOR,'pre[aria-label="Native continuous receiver review"]'))
        click('Confirm and start continuous receiver');job_id=on_started()
        def published(browser):
            for node in browser.find_elements(By.TAG_NAME,'button'):
                text=node.get_attribute('textContent').strip()
                if text.startswith('Inspect produced archive ') and node.is_enabled():return text
            return False
        archive_button=wait.until(published)
        click('Cancel continuous receiver')
        wait.until(lambda browser:any(('Receiver '+job_id+': cancelled.') in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        box=driver.find_element(By.XPATH,'//label[contains(normalize-space(),"Confirm stopping this receiver")]/span/input')
        driver.execute_script('arguments[0].click();',box);click('Reconcile receiver writers')
        wait.until(lambda browser:any('Owned receiver and snapshot-parser utilities are stopped.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        click('Review restart from stopped receiver')
        wait.until(lambda browser:any('previous_receiver_job_id' in node.get_attribute('textContent') for node in browser.find_elements(By.TAG_NAME,'pre')))
        click(archive_button);click('Load archive files')
        wait.until(lambda browser:browser.find_elements(By.CSS_SELECTOR,'table[aria-label="Verified native archive files"]'))
        if stopped_tail:
            click('Load binary-log receivers');click('Inspect receiver '+stopped_tail['receiver_job_id'])
            click('Inspect stopped receiver files')
            checkbox=wait.until(lambda browser:browser.find_element(By.CSS_SELECTOR,'input[aria-label="Adopt '+stopped_tail['log_name']+'"]'))
            driver.execute_script('arguments[0].click();',checkbox);click('Review stopped-file adoption')
            wait.until(lambda browser:browser.find_elements(By.CSS_SELECTOR,'pre[aria-label="Stopped-file archive review"]'))
            click('Confirm and adopt stopped logs')
            wait.until(lambda browser:any('adopted_stopped_files' in node.get_attribute('textContent') for node in browser.find_elements(By.TAG_NAME,'pre')))
            click('Load archive files')
        driver.save_screenshot(str(output/'native-continuous-binlogs.png'))
        errors=[node for node in driver.get_log('browser') if node.get('level')=='SEVERE']
        (output/'browser-console.json').write_text(json.dumps(errors,indent=2)+'\n');assert not errors
        return {'complete':True,'job_id':job_id,'produced_archive_job_id':archive_button.removeprefix('Inspect produced archive '),
            'reviewed_start':True,'native_closed_snapshot_visible':True,'cancelled':True,'writer_reconciled':True,'restart_reviewed_without_dispatch':True,'stopped_tail_adopted':bool(stopped_tail),'console_errors':0,'screenshot':'native-continuous-binlogs.png'}
    except Exception:
        if driver is not None:
            driver.save_screenshot(str(output/'browser-failure.png'))
            (output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
            (output/'browser-failure-console.json').write_text(json.dumps(driver.get_log('browser'),indent=2)+'\n')
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True);parser.add_argument('--family',choices=('mysql','mariadb'),required=True)
    parser.add_argument('--decoder',type=Path,required=True);parser.add_argument('--mysql-c',action='store_true');parser.add_argument('--gtid-mode',choices=('ON','OFF'),default='ON')
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();qualify(args.evidence,args.family,args.decoder,use_c=args.mysql_c,gtid_mode=args.gtid_mode,browser_binary=args.browser_binary,driver_binary=args.driver_binary)
