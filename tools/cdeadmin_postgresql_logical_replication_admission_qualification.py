"""Owned authenticated logical receiver qualification with SQL admission blocked."""
import argparse
import builtins
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'web'),str(ROOT/'tools')]


def released(jobs):
    jobs.close()
    with jobs._worker_maps_lock:
        return not any(worker.is_alive() for worker,_signal in jobs.workers.values()) and not jobs.pending_releases


def qualify(output,binary_path,*,browser_binary=None,driver_binary=None,slot_commands=False,slot_client_binary=None):
    import psycopg
    from psycopg import sql
    from postgresql_qualification_support import server as owned_server
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    proof={'complete':False,'full_product_complete':False,'history_testing':'not run'}
    paths=['tools/cdeadmin_postgresql_logical_replication_admission_qualification.py',
        'web/pgadmin/cdeadmin/providers/postgresql/replication_admission.py',
        'web/pgadmin/cdeadmin/providers/postgresql/continuity.py',
        'web/pgadmin/cdeadmin/providers/postgresql/continuity_transport.py',
        'web/pgadmin/cdeadmin/workspace/postgresql_continuity_service.py',
        'web/pgadmin/cdeadmin/workspace/postgresql_continuity_jobs.py',
        'web/pgadmin/cdeadmin/workspace/postgresql_logical_stream.py',
        'web/pgadmin/cdeadmin/workspace/postgresql_logical_slot_command.py',
        'web/pgadmin/static/js/Dialogs/PostgresqlLogicalStream.jsx',
        'web/pgadmin/static/js/Dialogs/PostgresqlContinuity.jsx']
    proof['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}
    builtins.SERVER_MODE=None
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    for name,value in {'DATA_DIR':'app','SQLITE_PATH':'app/application.db','SESSION_DB_PATH':'app/sessions',
        'STORAGE_DIR':'app/storage','LOG_FILE':'app/application.log','AZURE_CREDENTIAL_CACHE_DIR':'app/azure',
        'CDEADMIN_OPERATION_STORE_PATH':'app/operations.json','CDEADMIN_POSTGRESQL_CONTINUITY_ROOT':'jobs'}.items():setattr(config,name,str(output/value))
    config.CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH=str(binary_path)
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.workspace import service_for_app
    from pgadmin.cdeadmin.workspace import postgresql_logical_stream as stream
    from flask import url_for
    app=create_app('ScratchRobin owned logical replication admission');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start();client=app.test_client();jobs=None
    try:
        with owned_server(output/'fixture',server_options=('-c','wal_level=logical','-c','wal_sender_timeout=5s',
                *(('-c','max_prepared_transactions=10') if slot_commands else ())),
                initdb_options=('--locale=C','--encoding=UTF8')) as (route,password,fixture):
            admin={'host':route['host'],'port':route['port'],'user':'postgres','password':password,'dbname':'postgres','autocommit':True}
            database="Native logical database = ü '";principal='owned_logical_replication';secret=secrets.token_urlsafe(32)
            with psycopg.connect(**admin) as bootstrap:
                bootstrap.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
                bootstrap.execute(sql.SQL('CREATE ROLE {} LOGIN REPLICATION PASSWORD {}').format(sql.Identifier(principal),sql.Literal(secret)))
            with psycopg.connect(**{**admin,'dbname':database}) as observer:
                observer.execute('CREATE TABLE native_rows(id bigint PRIMARY KEY,body text,payload bytea)')
                publication='Native publication ü';observer.execute(sql.SQL('CREATE PUBLICATION {} FOR TABLE native_rows').format(sql.Identifier(publication)))
                with app.test_request_context('/'):
                    uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['postgresql'].set(True,user_id=uid)
                    registration=Server(user_id=uid,servergroup_id=group.id,name='Owned logical replication without SQL',
                        host=route['host'],port=route['port'],username=principal,maintenance_db=database,save_password=0,
                        connection_params={'sslmode':'disable'})
                    db.session.add(registration);db.session.commit();sid=registration.id;endpoint=registration.endpoint_profile.id
                    url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=sid)
                    service=service_for_app(app)
                with client.session_transaction() as login:login['_user_id']=str(uid);login['_fresh']=True
                def http(action,request,*,refused=False):
                    response=client.post(url,json={'action':'postgresql_continuity_'+action,'request':request});value=response.get_json()
                    assert secret not in json.dumps(value)
                    if refused:assert response.status_code==400,value;return value
                    assert response.status_code==200 and value.get('success'),value
                    return value['data']
                def wait(job,predicate):
                    deadline=time.monotonic()+45
                    while True:
                        result=http('status',{'job_id':job['job_id']})
                        if predicate(result):return result
                        assert time.monotonic()<deadline,result;time.sleep(.04)
                def prepare(slot,pairs,end=''):
                    return http('review',{'operation':stream.OPERATION,'database_target_id':'registered-replication-database',
                        'options':{'slot':slot,'plugin_options':pairs,'end_lsn':end,'status_interval_seconds':1,'timeout_seconds':30},
                        'replication_access':{'password':secret}})
                def start(job,**fields):
                    return http('start',{'job_id':job['job_id'],'review_digest':job['review_digest'],'confirmed':True,
                        'replication_access':{'password':secret},**fields})
                connect=psycopg.connect;admissions=[]
                def guarded(*args,**kwargs):
                    if kwargs.get('user')==principal:
                        assert kwargs.get('replication')=='database','Unexpected Python SQL admission'
                        admissions.append({'mode':kwargs['replication'],'database':kwargs.get('dbname')})
                    return connect(*args,**kwargs)
                def no_sql(*_args,**_kwargs):raise AssertionError('SQL workspace admission was attempted')
                with patch.object(psycopg,'connect',guarded),patch.object(service.endpoint_service,'workspace',no_sql),\
                        patch('pgadmin.cdeadmin.workspace.postgresql_continuity_service.capture',no_sql),patch.object(stream.private_sql,'attach',no_sql):
                    if slot_commands:
                        proof['native_slot_commands']=qualify_slot_commands(app,observer,http,wait,secret,fixture,slot_client_binary)
                    results={}
                    for mode,plugin,pairs in [('text','test_decoding',[{'name':'include-xids','value':'0'},{'name':'skip-empty-xacts','value':'1'}]),
                            ('binary','pgoutput',[{'name':'proto_version','value':'4'},{'name':'publication_names','value':sql.Identifier(publication).as_string(observer)},{'name':'binary','value':'true'}])]:
                        reference='reference_'+mode;managed='managed_'+mode
                        for name in (reference,managed):observer.execute('SELECT * FROM pg_create_logical_replication_slot(%s,%s)',(name,plugin))
                        observer.execute('INSERT INTO native_rows VALUES(%s,%s,%s)',(9007199254740993 if mode=='text' else 2,"native 😀 newline\nquote'",b'\x00\x80\xff'))
                        end=observer.execute('SELECT pg_current_wal_insert_lsn()::text').fetchone()[0]
                        rows=observer.execute("SELECT encode(data,'hex') FROM pg_logical_slot_peek_binary_changes(%s,NULL,NULL,VARIADIC %s::text[])",
                            (reference,[value for pair in pairs for value in (pair['name'],pair['value'])])).fetchall()
                        expected=b''.join(bytes.fromhex(row[0])+b'\n' for row in rows);assert expected
                        review=prepare(managed,pairs,end)
                        assert review['source']['database']==database and review['source']['slot_catalog_observed'] is False
                        assert review['source']['slot_snapshot'] is None and review['source']['sql_identity'] is None
                        assert review['source']['authenticated_principal']==principal
                        http('start',{'job_id':review['job_id'],'review_digest':review['review_digest'],'confirmed':True},refused=True)
                        start(review)
                        done=wait(review,lambda r:r['state'] in {'captured','failed','unknown'} and (r.get('logical_stream_artifact') or {}).get('state')=='sealed')
                        assert done['state']=='captured' and done['native_receiver_returned'],done
                        with app.app_context():jobs=service_for_app(app).postgresql_continuity_jobs
                        saved=jobs.load(done['job_id'],uid,endpoint)
                        with stream.payload(jobs,saved) as payload:assert payload.read()==expected
                        download=client.post(url,data={'action':'postgresql_continuity_logical_stream_download','payload':json.dumps({'job_id':done['job_id']})})
                        try:assert download.status_code==200 and download.data==expected
                        finally:download.close()
                        assert start(review)['state']=='captured'
                        preview=http('logical_stream_preview',{'job_id':done['job_id'],'limit':17});assert preview['bytes']==min(17,len(expected))
                        confirmed=observer.execute('SELECT confirmed_flush_lsn::text FROM pg_replication_slots WHERE slot_name=%s',(managed,)).fetchone()[0]
                        results[mode]={'bytes':len(expected),'sha256':hashlib.sha256(expected).hexdigest(),'native_confirmed_flush_lsn':confirmed}
                        for name in (reference,managed):observer.execute('SELECT pg_drop_replication_slot(%s)',(name,))
                    # Native refusal remains a returned receiver result; it is
                    # never replaced by invented SQL catalog observations.
                    missing=prepare('absent_owned_slot',[]);start(missing)
                    refused=wait(missing,lambda r:r['state']=='failed' and r.get('worker_io_closed') is True)
                    assert refused['native_receiver_returned'] is False
                    assert start(missing)['state']=='failed'
                    observer.execute("SELECT * FROM pg_create_logical_replication_slot('cancel_owned','test_decoding')")
                    cancellation=prepare('cancel_owned',[{'name':'include-xids','value':'0'}]);start(cancellation)
                    deadline=time.monotonic()+15
                    while not observer.execute("SELECT active FROM pg_replication_slots WHERE slot_name='cancel_owned'").fetchone()[0]:assert time.monotonic()<deadline;time.sleep(.04)
                    observer.execute("INSERT INTO native_rows VALUES(3,'cancellation keeps bytes',NULL)")
                    wait(cancellation,lambda r:int((r.get('progress') or {}).get('captured_bytes','0'))>0)
                    http('cancel',{'job_id':cancellation['job_id']})
                    cancelled=wait(cancellation,lambda r:r['state']=='cancelled' and (r.get('logical_stream_artifact') or {}).get('state')=='sealed')
                    assert start(cancellation)['state']=='cancelled'
                    observer.execute("SELECT pg_drop_replication_slot('cancel_owned')")
                    # Stale credentials cannot cause a SQL fallback.
                    http('review',{'operation':stream.OPERATION,'database_target_id':'registered-replication-database',
                        'options':{'slot':'owned'},'replication_access':{'password':'wrong-owned-password'}},refused=True)
                    if browser_binary:
                        observer.execute("SELECT * FROM pg_create_logical_replication_slot('browser_owned','test_decoding')")
                        observer.execute("INSERT INTO native_rows VALUES(4,'browser native logical admission',NULL)")
                        end=observer.execute('SELECT pg_current_wal_insert_lsn()::text').fetchone()[0]
                        proof['browser']=qualify_browser(app,output,browser_binary,driver_binary,sid,secret,end,slot_commands=slot_commands)
                        observer.execute("SELECT pg_drop_replication_slot('browser_owned')")
                        if slot_commands:
                            properties=observer.execute("SELECT slot_type,plugin,two_phase,failover FROM pg_replication_slots WHERE slot_name='browser_created_slot'").fetchone()
                            assert properties==('logical','pgoutput',True,True),properties
                            observer.execute("SELECT pg_drop_replication_slot('browser_created_slot')")
                assert admissions and all(item['mode']=='database' and item['database']==database for item in admissions)
                assert not observer.execute("SELECT 1 FROM pg_stat_activity WHERE usename=%s AND backend_type='client backend'",(principal,)).fetchall()
                assert released(jobs)
                for path in output.rglob('*.json'):
                    assert secret not in path.read_text(errors='replace')
                proof.update(complete=True,authenticated_original_registration=True,sql_workspace_and_private_sql_admission_blocked=True,
                    native_text_binary_bytes_equal_independent_slots=True,native_receiver_feedback_observed=True,download_and_preview_exact=True,
                    missing_slot_native_refusal_and_no_replay=True,cancellation_seals_retained_bytes=True,
                    credentials_excluded_from_receipts=True,duplicate_start_never_replays=True,captured=results,
                    owned_jobs_released=True,logical_admission_count=len(admissions))
        proof['owned_server_stopped']=fixture['owned_server_stopped']
    finally:
        if jobs is not None:proof['owned_jobs_released']=released(jobs)
        (output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def qualify_slot_commands(app,observer,http,wait,password,fixture,extra_client):
    # A real installed open source output-plugin implementation under quoted
    # and Unicode native library identities, entirely inside the owned server.
    library=subprocess.check_output(['docker','exec',fixture['owned_container_name'],'pg_config','--pkglibdir'],text=True,timeout=15).strip()
    alias="Native ü ' \\";sql_alias='Native " ü'
    subprocess.run(['docker','exec',fixture['owned_container_name'],'cp','--',library+'/test_decoding.so',library+'/'+alias+'.so'],check=True,timeout=15)
    subprocess.run(['docker','exec',fixture['owned_container_name'],'cp','--',library+'/test_decoding.so',library+'/'+sql_alias+'.so'],check=True,timeout=15)
    observer.execute('SELECT * FROM pg_create_logical_replication_slot(%s,%s)',('sql_native_quoted_plugin',sql_alias))
    assert observer.execute("SELECT plugin FROM pg_replication_slots WHERE slot_name='sql_native_quoted_plugin'").fetchone()==(sql_alias,)
    observer.execute("SELECT pg_drop_replication_slot('sql_native_quoted_plugin')")
    http('review',{'operation':'logical_slot_create','options':{'slot':'unrepresentable_owned','plugin':sql_alias},
        'replication_access':{'password':password}},refused=True)
    original=app.config['CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH'];clients=[original]
    if extra_client:clients.append(str(Path(extra_client).resolve().parent))
    results=[]
    try:
        for index,path in enumerate(clients):
            app.config['CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH']=path
            def submit(slot,plugin,*,two_phase=False,failover=False,if_not_exists=False,acknowledged=True):
                review=http('review',{'operation':'logical_slot_create','options':{'slot':slot,'plugin':plugin,
                    'two_phase':two_phase,'failover':failover,'if_not_exists':if_not_exists},'replication_access':{'password':password}})
                request={'job_id':review['job_id'],'review_digest':review['review_digest'],'confirmed':True,'replication_access':{'password':password}}
                http('start',request)
                done=wait(review,lambda r:r['state'] in {'completed','unknown','failed'})
                assert done['native_utility_acknowledged'] is acknowledged,done
                assert done['slot_existed_before'] is None and done['slot_observation'] is None and done['slot_observation_state']=='unavailable'
                assert http('start',request)['state']==done['state']
                return done
            prefix='protocol_'+str(index)+'_'
            created=submit(prefix+'flags','pgoutput',two_phase=True,failover=True)
            properties=observer.execute('SELECT slot_type,plugin,two_phase,failover FROM pg_replication_slots WHERE slot_name=%s',(prefix+'flags',)).fetchone()
            assert properties==('logical','pgoutput',True,True),properties
            submit(prefix+'flags','test_decoding',acknowledged=False)
            submit(prefix+'flags','test_decoding',if_not_exists=True)
            assert observer.execute('SELECT plugin FROM pg_replication_slots WHERE slot_name=%s',(prefix+'flags',)).fetchone()==('pgoutput',)
            quoted=submit(prefix+'quoted',alias)
            assert observer.execute('SELECT plugin FROM pg_replication_slots WHERE slot_name=%s',(prefix+'quoted',)).fetchone()==(alias,)
            observer.execute('SELECT * FROM pg_create_physical_replication_slot(%s)',(prefix+'existing_physical',))
            submit(prefix+'existing_physical','pgoutput',if_not_exists=True)
            assert observer.execute('SELECT slot_type FROM pg_replication_slots WHERE slot_name=%s',(prefix+'existing_physical',)).fetchone()==('physical',)
            submit(prefix+'missing_plugin','absent plugin ü',acknowledged=False)
            assert not observer.execute('SELECT 1 FROM pg_replication_slots WHERE slot_name=%s',(prefix+'missing_plugin',)).fetchall()
            for name in (prefix+'flags',prefix+'quoted',prefix+'existing_physical'):observer.execute('SELECT pg_drop_replication_slot(%s)',(name,))
            results.append({'tool':created['tool_identities']['pg_recvlogical'],'flags_native':True,
                'quoted_unicode_native_plugin':quoted['job_id'],'duplicate_and_missing_plugin_refused':True,
                'if_not_exists_preserves_other_type_and_plugin':True,'catalog_unobserved':True,'duplicate_start_does_not_replay':True,
                'native_protocol_embedded_quote_refusal_and_SQL_support_distinct':True})
    finally:app.config['CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH']=original
    return results


def qualify_browser(app,output,browser_binary,driver_binary,sid,password,end_lsn,*,slot_commands=False):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException,ElementClickInterceptedException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True)
    thread.start();driver=None;complete=False
    try:
        options=webdriver.ChromeOptions();options.binary_location=browser_binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1400'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary) if driver_binary else Service())
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,90,ignored_exceptions=(StaleElementReferenceException,ElementClickInterceptedException))
        ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'PostgreSQL')
        def own_server(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        element=wait.until(own_server)
        driver.execute_script('const t=window.pgAdmin.Browser.tree;const item=t.itemFrom(arguments[0].closest(".file-entry"));const n=window.pgAdmin.Browser.Nodes.server;n.callbacks.open_postgresql_continuity.call(n,{item});',element)
        def cancel_sql_prompt():
            if any(node.is_displayed() and 'Connect to Server' in node.text and 'Please enter the password' in node.text for node in driver.find_elements(By.CSS_SELECTOR,'[role="dialog"]')):
                button=next((node for node in driver.find_elements(By.TAG_NAME,'button') if node.is_displayed() and node.text.strip()=='Cancel'),None)
                if button is not None:button.click()
        def control(label):
            cancel_sql_prompt()
            node=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'label') if node.is_displayed() and node.text.strip().rstrip('*').strip()==label),None))
            identifier=node.get_attribute('for')
            target=driver.find_element(By.ID,identifier) if identifier else node.find_element(By.CSS_SELECTOR,'input')
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',target)
            return target
        def click(label):
            def attempt(browser):
                cancel_sql_prompt()
                node=next((node for node in browser.find_elements(By.TAG_NAME,'button') if node.is_displayed() and node.is_enabled() and node.text.strip()==label),None)
                if node is None:return False
                browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node);node.click();return True
            wait.until(attempt)
        def open_stream(browser):
            cancel_sql_prompt()
            summary=next((node for node in browser.find_elements(By.TAG_NAME,'summary') if node.text.strip()=='PostgreSQL logical replication streams'),None)
            if summary is None:return False
            if summary.find_element(By.XPATH,'..').get_attribute('open') is not None:return True
            browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',summary);summary.click();return True
        wait.until(open_stream)
        control('Use registered logical replication database without SQL admission').click()
        control('Logical replication principal password').send_keys(password)
        control('Logical receiver slot').send_keys('browser_owned')
        control('Logical receiver end lsn').send_keys(end_lsn)
        click('Add ordered logical receiver option')
        control('Logical receiver option 1 name').send_keys('include-xids');control('Logical receiver option 1 value').send_keys('0')
        click('Review logical replication stream')
        def receipt(browser):
            nodes=browser.find_elements(By.CSS_SELECTOR,'[aria-label="Native logical stream receipt"]')
            if not nodes:return None
            return json.loads(nodes[0].get_attribute('textContent'))
        reviewed=wait.until(lambda browser:receipt(browser) if (receipt(browser) or {}).get('state')=='reviewed' else None)
        assert reviewed['source']['admission_interface']=='logical-replication' and reviewed['source']['slot_catalog_observed'] is False
        control('Confirm native logical stream consumption').click();click('Start reviewed logical stream')
        done=wait.until(lambda browser:receipt(browser) if (receipt(browser) or {}).get('logical_stream_artifact',{}).get('state')=='sealed' else None)
        assert done['state']=='captured' and done['native_receiver_returned'] and int(done['logical_stream_artifact']['bytes'])>0
        assert control('Logical replication principal password').get_attribute('value')==''
        click('Preview native logical bytes');wait.until(lambda browser:browser.find_element(By.CSS_SELECTOR,'[aria-label="Native logical byte preview"]'))
        click('Download native logical stream')
        if slot_commands:
            control('Continuity operation').click()
            wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.text.strip()=='Create logical slot through replication'),None)).click()
            assert control('Use native replication-only admission').is_selected()
            control('Replication slot name').send_keys('browser_created_slot')
            plugin=control('Native logical output plugin');plugin.send_keys(Keys.CONTROL,'a');plugin.send_keys('pgoutput')
            control('Logical slot two phase').click();control('Logical slot failover').click()
            control('Replication principal password').send_keys(password)
            click('Review native operation')
            wait.until(lambda browser:'logical_slot_create' in browser.find_element(By.CSS_SELECTOR,'[aria-label="Native backup review"]').text)
            click('Confirm and start reviewed operation')
            def slot_returned(browser):
                for node in browser.find_elements(By.TAG_NAME,'details'):
                    summaries=node.find_elements(By.TAG_NAME,'summary')
                    if not summaries or summaries[0].text.strip()!='Native observations and artifact location':continue
                    values=node.find_elements(By.TAG_NAME,'pre')
                    if not values:continue
                    value=json.loads(values[0].get_attribute('textContent') or '{}')
                    if value.get('operation')=='logical_slot_create' and value.get('state')=='completed':
                        assert value['native_utility_acknowledged'] and value['slot_observation_state']=='unavailable'
                        return value
                return False
            wait.until(slot_returned)
            assert control('Replication principal password').get_attribute('value')==''
        driver.save_screenshot(str(output/'browser-logical-admission.png'))
        errors=[row for row in driver.get_log('browser') if row['level']=='SEVERE' and not ('/browser/server/connect/' in row.get('message','') and '428' in row.get('message',''))]
        assert not errors,errors;complete=True
        return {'complete':True,'console_errors':0,'job_id':done['job_id'],'native_review_start_preview_download':True,
            'password_cleared_on_dispatch':True,'sql_catalog_unobserved':True,'logical_slot_creation':slot_commands}
    finally:
        if driver is not None:
            if not complete:
                driver.save_screenshot(str(output/'browser-failure.png'))
                (output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text.replace(password,'<redacted>'))
                (output/'browser-failure-console.json').write_text(json.dumps(driver.get_log('browser'),indent=2).replace(password,'<redacted>')+'\n')
            driver.quit()
        http.shutdown();thread.join(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    parser.add_argument('--binary-path',default='/usr/lib/postgresql/18/bin')
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    parser.add_argument('--slot-commands',action='store_true');parser.add_argument('--slot-client-binary')
    args=parser.parse_args();proof=qualify(args.evidence,args.binary_path,browser_binary=args.browser_binary,driver_binary=args.driver_binary,
        slot_commands=args.slot_commands,slot_client_binary=args.slot_client_binary)
    print(json.dumps({'complete':proof['complete'],'history_testing':'not run','full_product_complete':False}))
