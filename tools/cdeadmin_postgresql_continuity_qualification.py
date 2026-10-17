#!/usr/bin/env python3
"""Owned PostgreSQL 18.3 HTTP backup chain and independent recovery proof.

Requires Docker and application-host PostgreSQL 18 utilities. Writes only a
fresh external evidence directory; never attaches to a preexisting server.
History and ScratchBird qualification are intentionally excluded.
"""
import argparse
import builtins
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output, binary_path, *, browser_binary=None, driver_binary=None, pitr=False):
    from postgresql_qualification_support import server as owned_server
    import psycopg
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence must be outside the source checkout')
    output.mkdir(parents=True,exist_ok=False)
    proof={'complete':False,'checks':[],'history_testing':'not run','source_sha256':{}}
    for directory in ('web/pgadmin/cdeadmin/providers/postgresql','web/pgadmin/cdeadmin/workspace','web/pgadmin/cdeadmin/sdk'):
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
    config.CDEADMIN_POSTGRESQL_CONTINUITY_ROOT=str(output/'artifacts')
    config.CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH=str(binary_path)
    config.CDEADMIN_POSTGRESQL_WAL_ARCHIVE_ROOT=str(output/'wal-archives')
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server
    from flask import url_for
    from pgadmin.cdeadmin.workspace import service_for_app
    app=create_app('ScratchRobin-native-continuity-qualification');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start()
    client=app.test_client();jobs=None
    restored_name='scratchrobin-continuity-restore-'+secrets.token_hex(8)
    restored_started=False;restored_stopped=False;pitr_jobs=()
    restored=output/'restored-clone'
    try:
        server_options=('-c','summarize_wal=on')
        if pitr:server_options+=('-c','archive_mode=on','-c','archive_command=test ! -f /var/lib/postgresql/sr_pitr_archive/%f && cp %p /var/lib/postgresql/sr_pitr_archive/%f')
        with owned_server(output/'fixture',server_options=server_options,initdb_options=('--locale=C','--encoding=UTF8')) as (route,password,fixture):
            with psycopg.connect(host=route['host'],port=route['port'],user=route['user'],password=password,
                                 dbname=route['database'],autocommit=True) as native:
                hba=native.execute('SHOW hba_file').fetchone()[0]
                subprocess.run(['docker','exec','--user','postgres','-i',fixture['owned_container_name'],'sh','-c','cat >> "$1"','fixture',hba],
                    input=b'\nhost replication postgres all scram-sha-256\n',check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
                native.execute('SELECT pg_reload_conf()')
                if pitr:
                    subprocess.run(['docker','exec','--user','postgres',fixture['owned_container_name'],'mkdir','/var/lib/postgresql/sr_pitr_archive'],check=True,timeout=15)
                    native.execute('CREATE TABLE sr_pitr_state(id bigint PRIMARY KEY, body text)')
                    native.execute("INSERT INTO sr_pitr_state VALUES(0,'base state')")
                subprocess.run(['docker','exec','--user','postgres',fixture['owned_container_name'],'mkdir','/var/lib/postgresql/sr_continuity_space'],check=True,timeout=15)
                native.execute("CREATE TABLESPACE sr_continuity_space LOCATION '/var/lib/postgresql/sr_continuity_space'")
                native.execute('CREATE TABLE sr_continuity_data (id bigint PRIMARY KEY,body text,payload bytea) TABLESPACE sr_continuity_space')
                native.execute("INSERT INTO sr_continuity_data VALUES (9007199254740993,'Unicode 😀',decode('0080ff','hex'))")
                from psycopg import sql
                exact_schema,exact_table='s $$😀\n','t "😀\n'
                native.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(exact_schema)))
                native.execute(sql.SQL('CREATE TABLE {}.{} (id bigint)').format(sql.Identifier(exact_schema),sql.Identifier(exact_table)))
                native.execute(sql.SQL('INSERT INTO {}.{} VALUES (9007199254740993)').format(sql.Identifier(exact_schema),sql.Identifier(exact_table)))
                native.execute("CREATE DATABASE sr_recovery_latin1 TEMPLATE template0 ENCODING 'LATIN1' LOCALE 'C'")
                latin_schema,latin_table='é'*40+'\n$$','t "ñ\n'
                with psycopg.connect(host=route['host'],port=route['port'],user=route['user'],password=password,
                        dbname='sr_recovery_latin1',autocommit=True) as latin:
                    latin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(latin_schema)))
                    latin.execute(sql.SQL('CREATE TABLE {}.{} (id bigint)').format(sql.Identifier(latin_schema),sql.Identifier(latin_table)))
                    latin.execute(sql.SQL('INSERT INTO {}.{} VALUES (9007199254740993)').format(sql.Identifier(latin_schema),sql.Identifier(latin_table)))
                native.execute("ALTER SYSTEM SET shared_preload_libraries='scratchrobin_must_not_load'")
                with app.test_request_context('/'):
                    user=User.query.first()
                    group=ServerGroup.query.filter_by(user_id=user.id).order_by(ServerGroup.id).first()
                    assert group is not None
                    app.blueprints['NODE-engine_type'].connector_visibility['postgresql'].set(True,user_id=user.id)
                    registered=Server(user_id=user.id,servergroup_id=group.id,name='Owned PostgreSQL continuity',
                        host=route['host'],port=route['port'],username=route['user'],maintenance_db=route['database'],
                        connection_params={'sslmode':'disable'},save_password=0)
                    db.session.add(registered);db.session.commit()
                    uid,sid,gid,endpoint=user.id,registered.id,group.id,registered.endpoint_profile.id
                    connect_url=url_for('NODE-server.connect_id',gid=gid,sid=sid)
                    workspace_url=url_for('NODE-server.cde_workspace_id',gid=gid,sid=sid)
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                connected=client.post(connect_url,json={'password':password}).get_json()
                if not connected.get('success'):
                    (output/'connect-failure.json').write_text(json.dumps(connected,indent=2).replace(password,'<redacted>')+'\n')
                    raise RuntimeError('Owned application connection failed')
                def http(operation,request):
                    response=client.post(workspace_url,json={'action':'postgresql_continuity_'+operation,'request':request})
                    value=response.get_json()
                    if response.status_code!=200 or not value.get('success'):
                        (output/'http-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                        raise RuntimeError('Native continuity HTTP '+operation+' failed')
                    return value['data']
                def submit(operation,options=None,expected_state='verified',**inputs):
                    review=http('review',{'operation':operation,'options':options or {},**inputs})
                    assert review['source']['server_version']==180003
                    request={'job_id':review['job_id'],'review_digest':review['review_digest'],'confirmed':True}
                    result=http('start',request)
                    # A duplicate HTTP start must observe the same durable job.
                    repeated=http('start',request);assert repeated['job_id']==result['job_id']
                    deadline=time.monotonic()+180
                    while result['state'] in {'dispatching','active','verifying','verifying_inputs','cancel_requested'}:
                        if time.monotonic()>deadline:http('cancel',{'job_id':result['job_id']});raise TimeoutError('Native backup job deadline')
                        time.sleep(.1);result=http('status',{'job_id':result['job_id']})
                    if result['state']!=expected_state:
                        (output/(operation+'-failure.json')).write_text(json.dumps(result,indent=2)+'\n')
                        raise RuntimeError(operation+' returned '+result['state'])
                    print(operation+' '+result['state']+' through application HTTP',flush=True)
                    return result
                full=submit('full_backup',{'timeout_seconds':None})
                proof['checks'].append('authenticated-http-full-physical-backup-relocated-tablespaces-native-files-and-wal-verification')
                if pitr:
                    pitr_jobs=qualify_pitr(native,full,http,submit,app,fixture,output,uid,endpoint,proof)
                tar_base=submit('full_backup',{'format':'tar','compression':'client-gzip','timeout_seconds':120})
                native.execute("INSERT INTO sr_continuity_data VALUES (9007199254740994,'incremental change',decode('aabb','hex'))")
                native.execute('SELECT pg_switch_wal()')
                incremental=submit('incremental_backup',{'timeout_seconds':120},base_job_id=full['job_id'])
                proof['checks'].append('authenticated-http-native-incremental-backup-against-selected-manifest')
                combined=submit('combine',{'timeout_seconds':120},chain=[full['job_id'],incremental['job_id']])
                proof['checks'].append('native-input-verification-chain-reconstruction-and-output-verification')
                tar_incremental=submit('incremental_backup',{'format':'tar','compression':'client-zstd','timeout_seconds':120},base_job_id=tar_base['job_id'])
                jobs=service_for_app(app).postgresql_continuity_jobs
                def artifact_facts(job):
                    path=jobs.directory(jobs.load(job['job_id'],uid,endpoint))
                    return {str(item.relative_to(path)):os.readlink(item) if item.is_symlink() else hashlib.sha256(item.read_bytes()).hexdigest()
                            for item in path.rglob('*') if item.is_file() or item.is_symlink()}
                chain_before={job['job_id']:artifact_facts(job) for job in (tar_base,tar_incremental)}
                tar_combined=submit('combine',{'timeout_seconds':120},chain=[tar_base['job_id'],tar_incremental['job_id']])
                plain_incremental=submit('incremental_backup',{'timeout_seconds':120},base_job_id=tar_base['job_id'])
                mixed_combined=submit('combine',{'timeout_seconds':120},chain=[tar_base['job_id'],plain_incremental['job_id']])
                wrong_chain=submit('combine',{'timeout_seconds':120},chain=[tar_incremental['job_id'],tar_base['job_id']],expected_state='failed')
                assert wrong_chain['artifact_complete'] is False and wrong_chain['tool_observation']['return_code']!=0
                for job in (tar_base,tar_incremental):assert artifact_facts(job)==chain_before[job['job_id']]
                assert len(tar_combined['input_materializations'])==2 and len(mixed_combined['input_materializations'])==1
                assert all(item['verification_observation']['verification_scope']['wal'] for item in tar_combined['input_materializations'])
                proof['checks'].append('native-gzip-full-zstd-incremental-and-mixed-tar-plain-chain-materialization-input-wal-verification-and-reconstruction')
                tar=submit('full_backup',{'format':'tar','compression':'client-gzip','timeout_seconds':120})
                assert tar['verification_scope']['files'] and not tar['verification_scope']['wal']
                proof['checks'].append('compressed-tar-native-format-verification-and-explicit-wal-exclusion')
                tar_jobs=[tar]
                for compression in ('client-lz4','client-zstd',''):
                    tar_jobs.append(submit('full_backup',{'format':'tar','compression':compression,
                        'wal_method':'stream' if compression else 'fetch','timeout_seconds':120}))
                jobs=service_for_app(app).postgresql_continuity_jobs
                combined_record=jobs.load(tar_combined['job_id'],uid,endpoint)
                combined_path=jobs.directory(combined_record)
                shutil.copytree(combined_path,restored,symlinks=True)
                (restored/'backup/postgresql.auto.conf').write_bytes(b'')
                # Native TAR maps retain source-host paths. This independent
                # recovery copy uses the explicitly relocated links below.
                (restored/'backup/tablespace_map').unlink(missing_ok=True)
                for link in (restored/'backup/pg_tblspc').iterdir():
                    assert link.is_symlink()
                    oid=link.name;link.unlink();link.symlink_to('/owned/tablespaces/'+oid)
                # The drill modifies only the independent clone, including its
                # native tablespace links and ownership. Inputs remain immutable.
                subprocess.run(['docker','run','--rm','--user','0:0','--entrypoint','find','--mount',
                    'type=bind,source='+str(restored)+',target=/owned','postgres:18.3','/owned','!','-type','l','-exec','chown','999:999','{}','+'],
                    check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
                subprocess.run(['docker','run','--rm','-d','--user','postgres','--name',restored_name,'--publish','127.0.0.1::5432',
                    '--env','PGDATA=/owned/backup','--mount','type=bind,source='+str(restored)+',target=/owned','postgres:18.3'],
                    check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
                restored_started=True
                restored_port=int(subprocess.check_output(['docker','port',restored_name,'5432/tcp'],text=True,timeout=15).strip().rsplit(':',1)[1])
                deadline=time.monotonic()+60
                while True:
                    try:
                        recovered=psycopg.connect(host='127.0.0.1',port=restored_port,user=route['user'],password=password,
                            dbname=route['database'],autocommit=True,connect_timeout=2);break
                    except psycopg.OperationalError:
                        if time.monotonic()>deadline:raise
                        time.sleep(.2)
                with recovered:
                    expected=native.execute("SELECT id::text,body,encode(payload,'hex') FROM sr_continuity_data ORDER BY id").fetchall()
                    actual=recovered.execute("SELECT id::text,body,encode(payload,'hex') FROM sr_continuity_data ORDER BY id").fetchall()
                    assert actual==expected and len(actual)==2
                    assert recovered.info.server_version==180003
                    assert recovered.execute('SELECT system_identifier::text FROM pg_control_system()').fetchone()[0]==combined['source']['system_identifier']
                proof['checks'].append('independent-postgresql18.3-recovery-of-compressed-reconstructed-chain-exact-int64-unicode-binary-and-tablespace-data')
                assert combined['recovery_drill_complete'] is False  # Evidence is separate from the product job.
            # Release the source fixture before exercising offline verification.
        assert fixture['owned_server_stopped']
        verified=submit('verify',base_job_id=full['job_id'])
        assert verified['verification_scope']['wal']
        proof['checks'].append('offline-authenticated-http-native-artifact-verification-after-source-server-stopped')
        before={job['job_id']:artifact_facts(job) for job in (full,combined,tar_combined,mixed_combined,*tar_jobs)}
        exact_check={'schema':exact_schema,'table':exact_table,'expected_rows':'1'}
        drill_options={'database':'postgres','checks':[{'schema':'public','table':'sr_continuity_data','expected_rows':'2'},exact_check],'timeout_seconds':120}
        recovered=submit('recovery_drill',drill_options,base_job_id=combined['job_id'],expected_state='recovered')
        assert recovered['recovery_drill_complete'] is True
        assert recovered['recovery_observation']['network_listener_started'] is False
        assert recovered['recovery_observation']['system_identifier']==combined['source']['system_identifier']
        assert recovered['tool_observation']['process_observation']['cleanup_confirmed'] is True
        proof['checks'].append('offline-authenticated-http-independent-combined-backup-single-user-recovery-with-relocated-tablespace-count-and-no-listener')
        chain_recoveries=[submit('recovery_drill',drill_options,base_job_id=job['job_id'],expected_state='recovered') for job in (tar_combined,mixed_combined)]
        assert all(job['recovery_drill_complete'] for job in chain_recoveries)
        proof['checks'].append('offline-native-recovery-of-all-tar-and-mixed-input-reconstructed-chains-and-native-refusal-of-reversed-chain-with-unchanged-source-archives')
        full_recovery=submit('recovery_drill',{**drill_options,'checks':[{'schema':'public','table':'sr_continuity_data','expected_rows':'1'},exact_check]},base_job_id=verified['job_id'],expected_state='recovered')
        assert full_recovery['recovery_drill_complete']
        proof['checks'].append('offline-native-full-backup-recovery-from-verification-receipt-excludes-later-source-changes')
        latin_recovery=submit('recovery_drill',{'database':'sr_recovery_latin1','checks':[{'schema':latin_schema,'table':latin_table,'expected_rows':'1'}]},base_job_id=full['job_id'],expected_state='recovered')
        assert latin_recovery['recovery_observation']['checks'][0]['schema']==latin_schema
        proof['checks'].append('offline-native-latin1-database-recovery-with-exact-non-ascii-newline-names-longer-than-63-utf8-bytes')
        tar_recoveries=[]
        for job in tar_jobs:
            recovered_tar=submit('recovery_drill',drill_options,base_job_id=job['job_id'],expected_state='recovered')
            assert recovered_tar['copy_observation']['source_format']=='tar'
            assert recovered_tar['copy_verification']['verification_scope']['wal'] is True
            tar_recoveries.append(recovered_tar)
        proof['checks'].append('offline-native-none-gzip-lz4-zstd-tar-materialization-relocated-tablespaces-and-native-wal-verification-before-recovery')
        wrong_count=submit('recovery_drill',{**drill_options,'checks':[{'schema':'public','table':'sr_continuity_data','expected_rows':'999'}]},base_job_id=full['job_id'],expected_state='failed')
        assert wrong_count['recovery_drill_complete'] is False and 'row count' in wrong_count['error_reason']
        no_result=submit('recovery_drill',{**drill_options,'checks':[{'schema':'public','table':'missing_recovery_table'}]},base_job_id=full['job_id'],expected_state='failed')
        assert no_result['tool_observation']['return_code']==0 and no_result['recovery_drill_complete'] is False
        proof['checks'].append('native-zero-exit-with-sql-error-and-incorrect-row-count-do-not-qualify-recovery')
        for job in (full,combined,tar_combined,mixed_combined,*tar_jobs):assert artifact_facts(job)==before[job['job_id']]
        proof['checks'].append('source-backup-bytes-and-tablespace-links-unchanged-after-successful-and-refused-drills')
        qualified_jobs=(full,incremental,combined,tar_base,tar_incremental,tar_combined,plain_incremental,mixed_combined,wrong_chain,*tar_jobs,verified,recovered,*chain_recoveries,full_recovery,latin_recovery,*tar_recoveries,wrong_count,no_result,*pitr_jobs)
        page=http('list',{'offset':0,'limit':2});assert page['total']==len(qualified_jobs) and len(page['jobs'])==2 and page['more']
        for path in Path(str(jobs.path)+'.jobs').glob('*.json'):assert password not in path.read_text()
        if browser_binary:
            proof['browser']=qualify_browser(app,output,verified['job_id'],browser_binary,driver_binary,
                pitr_target=proof['pitr']['targets'][0]['target'] if pitr else None)
            proof['checks'].append('native-browser-opens-offline-server-menu-loads-jobs-and-inspects-verification-receipt')
        proof.update(complete=True,job_ids=[value['job_id'] for value in qualified_jobs],
                     source=combined['source'],native_artifact_password_absent_from_receipts=True)
    finally:
        if jobs is not None:jobs.close()
        if restored_started:
            with (output/'restore-server.log').open('wb') as stream:
                subprocess.run(['docker','logs',restored_name],stdout=stream,stderr=subprocess.STDOUT,timeout=15)
            stopped=subprocess.run(['docker','stop',restored_name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=45)
            restored_stopped=stopped.returncode==0
        if restored.exists():
            cleanup=subprocess.run(['docker','run','--rm','--user','0:0','--entrypoint','find','--mount',
                'type=bind,source='+str(restored)+',target=/owned','postgres:18.3','/owned','!','-type','l','-exec','chown',str(os.getuid())+':'+str(os.getgid()),'{}','+'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
            proof['owned_clone_ownership_restored']=cleanup.returncode==0
            if cleanup.returncode!=0:proof['complete']=False
        proof['owned_restored_server_stopped']=restored_stopped
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    assert restored_stopped
    assert proof['complete']
    return proof


def qualify_browser(app, output, job_id, browser_binary, driver_binary, *, pitr_target=None):
    """Exercise the actual disconnected-server callback and compiled panel."""
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,wait_for_tree_item
    http=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=browser_binary
        options.add_argument('--headless=new');options.add_argument('--no-sandbox');options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1600,1000')
        options.add_argument('--user-data-dir='+str(output/'browser-profile'))
        options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary) if driver_binary else Service())
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,60)
        ensure_data_explorer(wait)
        expand(wait,'Connectors')
        wait_for_tree_item(wait,'PostgreSQL')
        expand(wait,'PostgreSQL')
        element=wait_for_tree_item(wait,'localhost',ancestors=('Connectors','PostgreSQL'))
        for control in driver.find_elements(By.CSS_SELECTOR,'[role="dialog"] button'):
            if control.is_displayed() and control.text.strip()=='Cancel':control.click();break
        # Scope console observations to this workspace; the normal shell may
        # previously have offered an interactive connection password prompt.
        driver.get_log('browser')
        driver.execute_script("""
          const tree=window.pgAdmin.Browser.tree;
          const item=tree.itemFrom(arguments[0].closest('.file-entry'));
          const data=tree.itemData(item);
          if(data._type!=='server' || data.connected) throw Error('Expected the owned disconnected server');
          const node=window.pgAdmin.Browser.Nodes.server;
          node.callbacks.open_postgresql_continuity.call(node,{item});
        """,element)
        def button(name):
            return wait.until(lambda browser:next((element for element in browser.find_elements(By.TAG_NAME,'button')
                if element.is_displayed() and element.is_enabled() and element.text.strip()==name),None))
        def click(name):
            from selenium.common.exceptions import ElementClickInterceptedException,StaleElementReferenceException
            def attempt(browser):
                try:
                    # The shell's pending connection prompt can arrive after
                    # the disconnected workspace has mounted. Dismiss it using
                    # its real control, then click the requested workspace UI.
                    password=browser.find_elements(By.CSS_SELECTOR,'input[aria-label="Password"]')
                    if any(item.is_displayed() for item in password):
                        cancel=next((item for item in browser.find_elements(By.TAG_NAME,'button')
                            if item.is_displayed() and item.text.strip()=='Cancel'),None)
                        if cancel is not None:cancel.click()
                        return False
                    control=next((item for item in browser.find_elements(By.TAG_NAME,'button')
                        if item.is_enabled() and item.get_attribute('textContent').strip()==name),None)
                    if control is None:return False
                    browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',control)
                    if not control.is_displayed():return False
                    control.click();return True
                except (ElementClickInterceptedException,StaleElementReferenceException):return False
            wait.until(attempt)
        click('Load backup jobs')
        wait.until(lambda browser:browser.find_elements(By.CSS_SELECTOR,'table[aria-label="Native physical backup jobs"]'))
        wait.until(lambda browser:browser.find_element(By.CSS_SELECTOR,'button[aria-label="Inspect backup '+job_id+'"]')).click()
        def receipt_message(text):
            for element in driver.find_elements(By.CSS_SELECTOR,'[role="alert"]'):
                if text in element.get_attribute('textContent'):
                    driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',element)
                    return text in element.text
            return False
        wait.until(lambda _browser:receipt_message('Recovery drill: not completed'))
        label=driver.find_element(By.XPATH,'//label[normalize-space()="Continuity operation"]')
        operation=driver.find_element(By.ID,label.get_attribute('for'))
        driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',operation)
        operation.click()
        wait.until(lambda browser:next((item for item in browser.find_elements(By.CSS_SELECTOR,'[role="option"]')
            if item.text.strip()=='Recover isolated backup copy'),None)).click()
        row=driver.find_element(By.CSS_SELECTOR,'button[aria-label="Inspect backup '+job_id+'"]').find_element(By.XPATH,'ancestor::tr')
        next(item for item in row.find_elements(By.TAG_NAME,'button') if item.get_attribute('textContent').strip()=='Select input').click()
        if pitr_target is not None:
            def selection(label_text, option_text):
                control=driver.find_element(By.XPATH,'//label[normalize-space()="'+label_text+'"]')
                field=driver.find_element(By.ID,control.get_attribute('for'))
                driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',field)
                wait.until(lambda _browser:field.is_enabled());field.click()
                wait.until(lambda browser:next((item for item in browser.find_elements(By.CSS_SELECTOR,'[role="option"]')
                    if item.text.strip()==option_text),None)).click()
            selection('Recovery target','Named restore point')
            control=driver.find_element(By.XPATH,'//label[normalize-space()="Exact native target value"]')
            driver.find_element(By.ID,control.get_attribute('for')).send_keys(pitr_target['value'])
            click('Load WAL archives')
            wait.until(lambda browser:'Archive directory:' in browser.find_element(By.TAG_NAME,'body').get_attribute('textContent'))
            selection('Native WAL archive','completed')
        click('Add recovery table check')
        for label,value in (('table 1','sr_pitr_state' if pitr_target is not None else 'sr_continuity_data'),('expected rows 1','2' if pitr_target is not None else '1')):
            control=driver.find_element(By.XPATH,'//label[normalize-space()="'+label+'"]')
            field=driver.find_element(By.ID,control.get_attribute('for'))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',field)
            field.send_keys(value)
        click('Review native operation')
        wait.until(lambda browser:'recovery_drill' in browser.find_element(By.CSS_SELECTOR,'[aria-label="Native backup review"]').get_attribute('textContent'))
        click('Confirm and start reviewed operation')
        wait.until(lambda _browser:receipt_message('Isolated native recovery completed'))
        if pitr_target is not None:assert receipt_message('Point-in-time recovery: completed for the reviewed target')
        assert not driver.find_elements(By.CSS_SELECTOR,'[role="alert"] .MuiAlert-icon svg[data-testid="ErrorOutlineIcon"]')
        driver.save_screenshot(str(output/'offline-continuity.png'))
        messages=[item for item in driver.get_log('browser') if item.get('level')=='SEVERE']
        expected=lambda item:'/browser/server/connect/' in item.get('message','') and '428' in item.get('message','')
        errors=[item for item in messages if not expected(item)]
        (output/'browser-console.json').write_text(json.dumps(errors,indent=2)+'\n')
        assert not errors
        return {'complete':True,'source_server_stopped':True,'console_errors':0,'reviewed_native_recovery_drill':True,
                'point_in_time_recovery':pitr_target is not None,
                'console_scope':'offline-continuity-workspace-after-shell-startup',
                'expected_native_password_admission_errors':sum(map(expected,messages)),'screenshot':'offline-continuity.png'}
    except Exception:
        if driver is not None:
            driver.save_screenshot(str(output/'browser-failure.png'))
            (output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text,encoding='utf8')
            (output/'browser-failure-console.json').write_text(json.dumps(driver.get_log('browser'),indent=2)+'\n')
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=5)


def qualify_pitr(native,base,http,submit,app,fixture,output,owner,endpoint,proof):
    from pgadmin.cdeadmin.workspace import service_for_app
    jobs=service_for_app(app).postgresql_continuity_jobs
    xid=native.execute("INSERT INTO sr_pitr_state VALUES(1,'target state ü') RETURNING xmin::text").fetchone()[0]
    timestamp=native.execute('SELECT to_char(clock_timestamp() AT TIME ZONE \'UTC\',\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\')').fetchone()[0]
    point="ScratchRobin ü ' "+secrets.token_hex(6)
    lsn=native.execute('SELECT pg_create_restore_point(%s)::text',(point,)).fetchone()[0]
    native.execute("INSERT INTO sr_pitr_state VALUES(2,'after target')")
    segment=native.execute('SELECT pg_walfile_name(pg_current_wal_insert_lsn())').fetchone()[0]
    native.execute('SELECT pg_switch_wal()')
    deadline=time.monotonic()+90
    while True:
        archived=native.execute('SELECT last_archived_wal FROM pg_stat_archiver').fetchone()[0]
        if archived is not None and archived>=segment:break
        if time.monotonic()>deadline:raise TimeoutError('Owned native WAL archiver deadline')
        time.sleep(.2)
    directory=jobs.archive_directory(owner,endpoint)/'completed';directory.mkdir(parents=True)
    subprocess.run(['docker','cp',fixture['owned_container_name']+':/var/lib/postgresql/sr_pitr_archive/.',str(directory)],check=True,timeout=30)
    archives=http('archives',{});assert 'completed' in archives['archives']
    before={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()}
    outcomes=[];completed=[]
    for kind,value,inclusive,rows in [('name',point,True,'2'),('xid',xid,True,'2'),('xid',xid,False,'1'),
                                      ('time',timestamp,True,'2'),('lsn',lsn,True,'2'),('immediate',None,True,'1')]:
        target={'kind':kind,'inclusive':inclusive,'timeline':'current',**({'value':value} if value is not None else {})}
        result=submit('recovery_drill',{'target':target,'wal_archive':'completed','checks':[{'schema':'public','table':'sr_pitr_state','expected_rows':rows}],'timeout_seconds':120},
                      expected_state='recovered',base_job_id=base['job_id'])
        assert result['recovery_observation']['point_in_time_recovery'] and result['wal_archive_observation']['reviewed_content_matched']
        outcomes.append({'target':target,'checks':result['recovery_observation']['checks'],'job_id':result['job_id']})
        completed.append(result)
    unreachable=submit('recovery_drill',{'target':{'kind':'name','value':'sr_unreachable_'+secrets.token_hex(6)},'wal_archive':'completed','timeout_seconds':120},
                       expected_state='failed',base_job_id=base['job_id'])
    assert unreachable.get('recovery_drill_complete') is False and not unreachable.get('recovery_observation')
    assert {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()}==before
    assert int(native.execute('SELECT count(*) FROM sr_pitr_state').fetchone()[0])==3
    proof['pitr']={'targets':outcomes,'unreachable_target_refused':True,'source_archive_unchanged':True,'live_source_data_unchanged':True,
                   'execution_scope':'independent application-host copy; no listener or source connection during recovery'}
    proof['checks'].append('authenticated-http-native-point-in-time-recovery-name-xid-inclusive-exclusive-time-lsn-immediate-and-unreachable-target')
    return (*completed,unreachable)


def resume_pitr_browser(previous, output, binary_path, browser_binary, driver_binary):
    """Requalify only browser behavior against preserved, owned native evidence."""
    previous,output=Path(previous).resolve(),Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence must be outside the source checkout')
    output.mkdir(parents=True,exist_ok=False)
    prior=json.loads((previous/'summary.json').read_text())
    if len(prior.get('pitr',{}).get('targets',[]))!=6 or not prior.get('owned_restored_server_stopped'):
        raise RuntimeError('Complete native PITR target and cleanup observations are required')
    for name,digest in prior['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Native-qualified product backend inputs changed; run full qualification')
    builtins.SERVER_MODE=None
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    config.DATA_DIR=str(previous/'app');config.SQLITE_PATH=str(previous/'app/application.db')
    config.SESSION_DB_PATH=str(previous/'app/sessions');config.STORAGE_DIR=str(previous/'app/storage')
    config.LOG_FILE=str(output/'application.log');config.AZURE_CREDENTIAL_CACHE_DIR=str(previous/'app/azure')
    config.CDEADMIN_OPERATION_STORE_PATH=str(previous/'app/operations.json')
    config.CDEADMIN_POSTGRESQL_CONTINUITY_ROOT=str(previous/'artifacts')
    config.CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH=str(binary_path)
    config.CDEADMIN_POSTGRESQL_WAL_ARCHIVE_ROOT=str(previous/'wal-archives')
    from pgadmin import create_app
    from pgadmin.cdeadmin.workspace import service_for_app
    app=create_app('ScratchRobin-native-pitr-browser-qualification');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start()
    records=[]
    for path in Path(str(config.CDEADMIN_OPERATION_STORE_PATH)+'.postgresql-continuity.jobs').glob('*.json'):
        records.extend(json.loads(path.read_text()).get('postgresql_continuity_jobs',{}).values())
    base=next(record['inputs'][0]['job_id'] for record in records if record['job_id']==prior['pitr']['targets'][0]['job_id'])
    verified=next(record for record in records if record['operation']=='verify' and record['state']=='verified' and record.get('artifact_job_id')==base)
    try:
        browser=qualify_browser(app,output,verified['job_id'],browser_binary,driver_binary,pitr_target=prior['pitr']['targets'][0]['target'])
        result={'complete':browser['complete'],'browser':browser,'native_receipt':str(previous/'summary.json'),
                'native_backend_hashes_unchanged':True,'native_checks':prior['checks'],'pitr':prior['pitr'],
                'history_tests_executed':False,'full_product_complete':False}
        (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    finally:
        jobs=getattr(service_for_app(app),'postgresql_continuity_jobs',None)
        if jobs is not None:jobs.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--binary-path',type=Path,default=Path('/usr/lib/postgresql/18/bin'))
    parser.add_argument('--browser-binary')
    parser.add_argument('--driver-binary')
    parser.add_argument('--pitr',action='store_true')
    parser.add_argument('--resume-browser-from',type=Path)
    args=parser.parse_args()
    if args.resume_browser_from:
        resume_pitr_browser(args.resume_browser_from,args.evidence,args.binary_path,args.browser_binary,args.driver_binary)
    else:
        qualify(args.evidence,args.binary_path,browser_binary=args.browser_binary,driver_binary=args.driver_binary,pitr=args.pitr)
