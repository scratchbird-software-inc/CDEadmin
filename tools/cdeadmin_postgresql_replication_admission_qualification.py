"""Owned native WAL capture with HBA-denied SQL and a replication-only user."""
import argparse
import builtins
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,binary_path,*,browser_binary=None,driver_binary=None):
    import psycopg
    from psycopg import sql
    from postgresql_qualification_support import server as owned_server
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False,mode=0o700)
    proof={'complete':False,'full_product_complete':False,'history_testing':'not run','source_sha256':{}}
    for name in ('web/pgadmin/cdeadmin/providers/postgresql/replication_admission.py',
            'web/pgadmin/cdeadmin/providers/postgresql/continuity_transport.py',
            'web/pgadmin/cdeadmin/workspace/postgresql_continuity_service.py',
            'web/pgadmin/cdeadmin/workspace/postgresql_continuity_jobs.py',
            'web/pgadmin/cdeadmin/workspace/postgresql_continuity_capture.py',
            'tools/cdeadmin_postgresql_replication_admission_qualification.py',
            'web/pgadmin/static/js/Dialogs/PostgresqlContinuity.jsx'):
        proof['source_sha256'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    builtins.SERVER_MODE=None
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    for name,value in {'DATA_DIR':'app','SQLITE_PATH':'app/application.db','SESSION_DB_PATH':'app/sessions',
            'STORAGE_DIR':'app/storage','LOG_FILE':'app/application.log','AZURE_CREDENTIAL_CACHE_DIR':'app/azure',
            'CDEADMIN_OPERATION_STORE_PATH':'app/operations.json','CDEADMIN_POSTGRESQL_CONTINUITY_ROOT':'backups',
            'CDEADMIN_POSTGRESQL_WAL_ARCHIVE_ROOT':'wal-archives'}.items():setattr(config,name,str(output/value))
    config.CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH=str(binary_path)
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server
    from flask import url_for
    from pgadmin.cdeadmin.workspace import service_for_app
    app=create_app('ScratchRobin-native-replication-only-admission');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start();client=app.test_client();jobs=None
    try:
        with owned_server(output/'fixture',server_options=('-c','wal_keep_size=64MB'),
                initdb_options=('--wal-segsize=1','--locale=C','--encoding=UTF8')) as (route,password,fixture):
            native_options={'host':route['host'],'port':route['port'],'user':'postgres','dbname':'postgres','password':password}
            with psycopg.connect(**native_options,autocommit=True) as native:
                principal='owned_replication_only';replication_password=secrets.token_urlsafe(32)
                native.execute(sql.SQL('CREATE ROLE {} LOGIN REPLICATION PASSWORD {}').format(sql.Identifier(principal),sql.Literal(replication_password)))
                hba=native.execute('SHOW hba_file').fetchone()[0]
                script='set -eu; cp "$1" "$1.owned-original"; cat > "$1"; cat "$1.owned-original" >> "$1"'
                subprocess.run(['docker','exec','--user','postgres','-i',fixture['owned_container_name'],'sh','-c',script,'fixture',hba],
                    input=('host replication '+principal+' all scram-sha-256\nhost all '+principal+' all reject\n').encode(),
                    check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
                native.execute('SELECT pg_reload_conf()')
                try:psycopg.connect(**{**native_options,'user':principal,'password':replication_password},connect_timeout=3).close()
                except psycopg.OperationalError:pass
                else:raise AssertionError('Owned HBA did not refuse SQL for the replication-only principal')
                with app.test_request_context('/'):
                    user=User.query.first();uid=user.id;group=ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['postgresql'].set(True,user_id=uid)
                    registered=Server(user_id=uid,servergroup_id=group.id,name='Owned replication-only WAL',host=route['host'],port=route['port'],
                        username=principal,maintenance_db='postgres',connection_params={'sslmode':'disable'},save_password=0)
                    db.session.add(registered);db.session.commit();sid=registered.id;endpoint=registered.endpoint_profile.id
                    workspace_url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=sid)
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                def http(operation,request,*,refused=False):
                    response=client.post(workspace_url,json={'action':'postgresql_continuity_'+operation,'request':request})
                    value=response.get_json()
                    if refused:assert response.status_code==400,value;return value
                    assert response.status_code==200 and value.get('success'),value
                    assert replication_password not in json.dumps(value)
                    return value['data']
                def wait(job_id,predicate):
                    deadline=time.monotonic()+60
                    while True:
                        value=http('status',{'job_id':job_id})
                        if predicate(value):return value
                        assert value['state'] not in {'failed','unknown','not_dispatched'},value
                        assert time.monotonic()<deadline,value
                        time.sleep(.05)
                access={'password':replication_password}
                draft={'operation':'wal_capture','options':{'archive':'replication-only','timeout_seconds':30,'status_interval_seconds':1},'replication_access':access}
                http('review',{**draft,'replication_access':{'password':'incorrect-owned-password'}},refused=True)
                http('review',{**draft,'replication_access':{'password':replication_password,'host':'unregistered'}},refused=True)
                http('review',{**draft,'operation':'full_backup'},refused=True)
                first=http('review',draft)
                assert first['source']['authenticated_principal']==principal and first['source']['sql_admission_performed'] is False
                http('start',{'job_id':first['job_id'],'review_digest':first['review_digest'],'confirmed':True},refused=True)
                start={'job_id':first['job_id'],'review_digest':first['review_digest'],'confirmed':True,'replication_access':access}
                http('start',start)
                deadline=time.monotonic()+20
                while not native.execute('SELECT 1 FROM pg_stat_replication WHERE usename=%s',(principal,)).fetchall():
                    assert time.monotonic()<deadline
                    time.sleep(.05)
                for _step in range(3):native.execute('SELECT pg_switch_wal()');time.sleep(.05)
                observed=wait(first['job_id'],lambda r:(r.get('archive_observation') or {}).get('new_files',0)>0)
                http('cancel',{'job_id':first['job_id']})
                stopped=wait(first['job_id'],lambda r:r['state']=='cancelled')
                # Duplicate dispatch remains an offline receipt even after the
                # native login is disabled. Never reconnect or replay it.
                native.execute(sql.SQL('ALTER ROLE {} NOLOGIN').format(sql.Identifier(principal)))
                assert http('start',start)['job_id']==stopped['job_id']
                native.execute(sql.SQL('ALTER ROLE {} LOGIN').format(sql.Identifier(principal)))
                with app.app_context():jobs=service_for_app(app).postgresql_continuity_jobs
                # Native receipts and files use the standard durable job store.
                files=list((output/'wal-archives'/str(uid)/endpoint/'replication-only').glob('*'))
                assert any(path.name.endswith(tuple('0123456789ABCDEF')) and path.stat().st_size==1048576 for path in files if path.is_file())
                assert not native.execute("SELECT 1 FROM pg_stat_activity WHERE usename=%s AND backend_type='client backend'",(principal,)).fetchall()
                second=http('review',draft)
                assert second['source']['system_identifier']==first['source']['system_identifier']
                http('start',{'job_id':second['job_id'],'review_digest':second['review_digest'],'confirmed':True,'replication_access':access})
                wait(second['job_id'],lambda r:r['state']=='active')
                http('cancel',{'job_id':second['job_id']});wait(second['job_id'],lambda r:r['state']=='cancelled')
                for path in (output/'app').rglob('*.json'):
                    assert replication_password.encode() not in path.read_bytes()
                if browser_binary:
                    proof['browser']=qualify_browser(app,output,browser_binary,driver_binary,sid,replication_password,native,principal)
                proof.update(complete=True,native_version='18.3',sql_hba_denied=True,
                    authenticated_api_native_wal_capture_cancel_restart=True,exact_native_principal=principal,
                    no_sql_client_backend=True,native_completed_files=observed['archive_observation']['new_files'],
                    duplicate_start_after_login_revocation_no_replay=True,credentials_absent_from_json_receipts=True)
    finally:
        if jobs is None:
            with app.app_context():jobs=getattr(service_for_app(app),'postgresql_continuity_jobs',None)
        if jobs is not None:jobs.close()
        (output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def qualify_browser(app,output,browser_binary,driver_binary,sid,password,native,principal):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException,ElementClickInterceptedException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None;complete=False
    try:
        options=webdriver.ChromeOptions();options.binary_location=browser_binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1400'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary) if driver_binary else Service())
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/');wait=WebDriverWait(driver,90,ignored_exceptions=(StaleElementReferenceException,ElementClickInterceptedException))
        ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'PostgreSQL')
        def owned_server(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        element=wait.until(owned_server)
        driver.execute_script('const tree=window.pgAdmin.Browser.tree;const item=tree.itemFrom(arguments[0].closest(".file-entry"));const node=window.pgAdmin.Browser.Nodes.server;node.callbacks.open_postgresql_continuity.call(node,{item});',element)
        def field(label):
            # Selecting a disconnected legacy server can raise its existing
            # SQL password challenge. Refuse that separate SQL connection;
            # these credentials belong only to physical replication admission.
            prompts=driver.find_elements(By.CSS_SELECTOR,'[role="dialog"]')
            if any(node.is_displayed() and 'Connect to Server' in node.text and 'Please enter the password' in node.text for node in prompts):
                cancel=next((node for node in driver.find_elements(By.TAG_NAME,'button') if node.is_displayed() and node.text.strip()=='Cancel'),None)
                if cancel is not None:cancel.click()
            node=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'label') if node.is_displayed() and node.text.strip().rstrip('*').strip()==label),None))
            control=driver.find_element(By.ID,node.get_attribute('for'));driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',control);return control
        def click(label):
            def attempt(browser):
                node=next((node for node in browser.find_elements(By.TAG_NAME,'button') if node.is_enabled() and node.text.strip()==label),None)
                if node is None:return False
                browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node);node.click();return True
            wait.until(attempt)
        def open_operation(browser):
            field('Continuity operation').click();return True
        wait.until(open_operation)
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.text.strip()=='Capture native WAL archive'),None)).click()
        checkbox=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'label') if node.text.strip()=='Use replication-only WAL admission'),None))
        driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',checkbox);checkbox.click()
        field('Replication principal password').send_keys(password);field('WAL archive').send_keys('browser-replication-only')
        click('Review native operation')
        wait.until(lambda browser:'physical-replication' in browser.find_element(By.CSS_SELECTOR,'[aria-label="Native backup review"]').text)
        click('Confirm and start reviewed operation')
        assert field('Replication principal password').get_attribute('value')==''
        def active(browser):
            return any('Job ' in node.text and ': active.' in node.text for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]'))
        wait.until(active)
        wait.until(lambda _browser:native.execute('SELECT 1 FROM pg_stat_replication WHERE usename=%s',(principal,)).fetchall())
        for _step in range(3):native.execute('SELECT pg_switch_wal()');time.sleep(.05)
        def published(browser):
            return any('Completed archive files observed:' in node.text and 'Newly published: 0.' not in node.text and 'Newly published:' in node.text for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]'))
        wait.until(published);click('Cancel native job')
        wait.until(lambda browser:any('Job ' in node.text and ': cancelled.' in node.text for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        assert not native.execute("SELECT 1 FROM pg_stat_activity WHERE usename=%s AND backend_type='client backend'",(principal,)).fetchall()
        driver.save_screenshot(str(output/'browser-replication-only.png'));console=driver.get_log('browser')
        challenge=lambda row:'/browser/server/connect/' in row.get('message','') and '428' in row.get('message','')
        expected=[row for row in console if row['level']=='SEVERE' and challenge(row)]
        errors=[row for row in console if row['level']=='SEVERE' and not challenge(row)];assert not errors,errors
        complete=True
        return {'complete':True,'console_errors':0,'expected_legacy_sql_credential_challenges':len(expected),
            'sql_disconnected_native_review_start_publish_cancel':True}
    finally:
        if driver is not None:
            if not complete:
                driver.save_screenshot(str(output/'browser-failure.png'))
                (output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text.replace(password,'<redacted>'))
                (output/'browser-failure-console.json').write_text(json.dumps(driver.get_log('browser'),indent=2).replace(password,'<redacted>')+'\n')
            driver.quit()
        http.shutdown();thread.join(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--binary-path',type=Path,required=True)
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();result=qualify(args.output,args.binary_path,browser_binary=args.browser_binary,driver_binary=args.driver_binary)
    raise SystemExit(0 if result['complete'] else 1)
