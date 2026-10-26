"""Qualify controlled DDN ALTER on Oracle MySQL 9.7 with both native interfaces."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def registration(app,route,password,use_c,username='root'):
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    with app.test_request_context('/'):
        owner=User.query.first();group=ServerGroup.query.filter_by(user_id=owner.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=owner.id)
        server=Server(user_id=owner.id,servergroup_id=group.id,name='Owned controlled DDL '+str(use_c),
            host=route['host'],port=route['port'],username=username,maintenance_db='sr_osc',save_password=0)
        server._cde_endpoint_registration=registration_profile('mysql-native')
        server._cde_endpoint_route_configuration={**route,'database':'sr_osc','user':username,'use_pure':not use_c,
            'autocommit':True,'credential_kinds':['database_password']}
        db.session.add(server);db.session.commit();target=str(uuid.uuid4())
        db.session.add(EndpointDatabaseTarget(id=target,endpoint_id=server.endpoint_profile.id,display_name='sr_osc',database='sr_osc',configuration='{}',active=1));db.session.commit()
        endpoint=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=server.id)
        verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=server.id);uid=owner.id;sid=server.id
    client=app.test_client()
    with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(uid),True
    assert client.post(verify,json={'password':password}).get_json()['success']
    def post(action,request):
        reply=client.post(endpoint,json={'action':action,'request':{'database_target_id':target,**request}})
        data=reply.get_json();assert reply.status_code==200 and data.get('success'),data
        assert reply.headers['Cache-Control']=='no-store'
        return data['data']
    post.raw=lambda action,request:client.post(endpoint,json={'action':action,'request':{'database_target_id':target,**request}})
    post.body=lambda action,**data:client.post(endpoint,json={'action':action,'database_target_id':target,**data})
    return sid,target,post


def terminal(post,review):
    limit=time.monotonic()+40
    while not review.get('controlled_terminal') and time.monotonic()<limit:
        time.sleep(.05);review=post('mysql_online_ddl_status',{'review_id':review['review_id']})
    assert review.get('controlled_terminal'),review
    return review


def qualify(output,online_copy=False,browser_binary=None,driver_binary=None):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False,mode=0o700)
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    paths=['tools/cdeadmin_mysql_online_ddl_qualification.py','web/pgadmin/cdeadmin/workspace/mysql_online_policy.py',
        'web/pgadmin/cdeadmin/workspace/mysql_online_jobs.py','web/pgadmin/cdeadmin/workspace/mysql_online_service.py',
        'web/pgadmin/cdeadmin/providers/mysql_schema_application.py','web/pgadmin/cdeadmin/workspace/mysql_schema_plan.py',
        'web/pgadmin/cdeadmin/providers/mysql_online_copy.py','web/pgadmin/cdeadmin/providers/mysql_online_copy_hook.pl',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_charsets.py']
    proof={'complete':False,'interfaces':[],'history_testing':'not run','source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    owned=None
    try:
        with server(output/'fixture') as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;cursor=oracle.cursor()
            try:
                cursor.execute('CREATE DATABASE sr_osc CHARACTER SET utf8mb4');cursor.execute('USE sr_osc')
                cursor.execute('CREATE TABLE t(id INT PRIMARY KEY,note VARCHAR(80)) ENGINE=InnoDB');cursor.execute("INSERT INTO t VALUES(1,'preserved')")
                cursor.execute('CREATE TABLE parent(id INT PRIMARY KEY)');cursor.execute('INSERT INTO parent VALUES(1)')
                cursor.execute('CREATE TABLE child(id INT PRIMARY KEY,pid INT,CONSTRAINT fk FOREIGN KEY(pid) REFERENCES parent(id))');cursor.execute('INSERT INTO child VALUES(1,1)')
                cursor.execute('CREATE TABLE audit(id INT)');cursor.execute('CREATE TRIGGER child_audit AFTER INSERT ON child FOR EACH ROW INSERT INTO audit VALUES(NEW.id)')
                cursor.execute("CREATE TABLE typed(flags SET('a','雪'))")
                cursor.execute("INSERT INTO typed VALUES('a,雪')")
                for flag in (False,True):
                    cursor.execute('CREATE TABLE interrupt_'+str(flag)+'(id INT PRIMARY KEY,note VARCHAR(80))')
                    cursor.execute("INSERT INTO interrupt_"+str(flag)+" VALUES(1,'preserved')")
                password=secrets.token_urlsafe(24);cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,));app=setup_application(output)
                for use_c in (False,True):
                    sid,target,post=registration(app,route,password,use_c);checks=[]
                    from types import SimpleNamespace
                    from decimal import Decimal
                    from pgadmin.cdeadmin.security import SecretLease
                    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client,MYSQL_PROFILE
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=lambda *_:SecretLease(password.encode('utf8'))),None)
                    native=client._connect({'route':{**route,'database':'sr_osc','use_pure':not use_c,'user':'root','autocommit':True,
                        'credential_reference_id':'owned-secret','principal_reference':'owned-operator'}})
                    try:
                        with native.cursor() as current:
                            current.execute("SELECT flags,CAST('0.000000000000000000000000000001' AS DECIMAL(65,30)),CAST('18446744073709551615' AS UNSIGNED),X'00FF' FROM typed")
                            values=current.fetchone();assert values==({'a','雪'},Decimal('1e-30'),18446744073709551615,b'\0\xff'),values
                            current.execute("SELECT '雪',17");assert current.fetchone()==('雪',17)
                            current.execute("SELECT flags,STRING_TO_VECTOR('[1,-2,3]') FROM typed")
                            import struct
                            vector=current.fetchone()[1];assert bytes(vector)==struct.pack('<fff',1,-2,3)
                    finally:client._discard_failed_session(native);client.close()
                    checks.append('native-SET-charset-conversion-with-exact-Decimal-unsigned-and-binary-neighbours')
                    selected={'method':'native','algorithm':'INSTANT','lock':'DEFAULT','lock_wait_seconds':2,'timeout_seconds':20}
                    def review(table,change,options=None):
                        baseline=post('mysql_catalog_export',{})['snapshot'];desired=deepcopy(baseline)
                        # Native DDN rows are read using the same maintained importer.
                        from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
                        parsed=read_catalog(json.dumps(baseline),engine='mysql')
                        row=next(v for v in parsed['rows'].values() if v['kind']=='table' and v['name']==table)
                        from pgadmin.cdeadmin.workspace.firebird_catalog_export import _json
                        original=_json(_json(row['native']));native=deepcopy(row['native'])
                        native['definition']=change(native['definition'])
                        changed=_json(_json(native));count=0
                        for filename,text in desired['files'].items():
                            count+=text.count(original);desired['files'][filename]=text.replace(original,changed)
                        assert count==1
                        request={'baseline':json.dumps(baseline),'source':json.dumps(desired),'execution':options or selected}
                        preview=post('mysql_schema_validate',request);assert preview['ready_for_review'] and preview['native_grammar_validated'],preview
                        return post('mysql_schema_review',{**request,'execution_sha256':preview['execution_sha256']})
                    def start(receipt):return post('mysql_online_ddl_start',{'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True})
                    def add(name):return lambda source:source.replace(') ENGINE=',', `'+name+'` INT NULL) ENGINE=')
                    column='added_'+str(use_c)
                    receipt=review('t',add(column));job=terminal(post,start(receipt))
                    assert job['state']=='committed' and job['outcome']['rediscovery_verified'],job
                    assert job['controlled_job']['native_interface']==('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')
                    cursor.execute('SELECT note FROM t WHERE id=1');assert cursor.fetchone()==('preserved',)
                    assert start(receipt)['state']=='committed'
                    observed=post('mysql_online_ddl_observe',{'review_id':receipt['review_id']})
                    assert observed['observed'] and not observed['observed_thread_still_present']
                    checks.append('native-INSTANT-DDN-review-dispatch-rediscovery-and-no-replay')
                    receipt=review('child',add('child_'+str(use_c)))
                    job=terminal(post,start(receipt));assert job['state']=='committed',job
                    cursor.execute('SELECT COUNT(*) FROM audit');audit_count=cursor.fetchone()[0]
                    cursor.execute('INSERT INTO child(id,pid) VALUES(%s,1)',(2+int(use_c),))
                    cursor.execute('SELECT COUNT(*) FROM audit');assert cursor.fetchone()[0]==audit_count+1
                    checks.append('native-foreign-keys-triggers-and-data-preserved')
                    receipt=review('t',lambda source:source.replace('varchar(80)','text'),{**selected,'algorithm':'INPLACE','lock':'NONE'})
                    job=terminal(post,start(receipt));assert job['state']=='unknown_outcome' and job['outcome']['error_code'] in {1845,1846},job
                    cursor.execute("SHOW COLUMNS FROM t LIKE 'note'");assert cursor.fetchone()[1]=='varchar(80)'
                    checks.append('native-online-refusal-with-no-algorithm-fallback')
                    for deadline in (False,True):
                        receipt=review('t',add('cancel_'+str(deadline)+'_'+str(use_c)),{**selected,'timeout_seconds':1 if deadline else 20})
                        cursor.execute('LOCK TABLES t WRITE')
                        try:
                            job=start(receipt);time.sleep(.15)
                            if not deadline:post('mysql_online_ddl_cancel',{'review_id':receipt['review_id']})
                            job=terminal(post,job)
                            assert job['state'] in {'not_dispatched','unknown_outcome'} and job['controlled_job']['cancellation_requested'],job
                        finally:cursor.execute('UNLOCK TABLES')
                    checks.append('owned-native-cancellation-and-runtime-budget')
                    cursor.execute('SET autocommit=0');cursor.execute("UPDATE t SET note='private pending' WHERE id=1")
                    cursor.execute('SAVEPOINT independent');cursor.execute("SELECT CAST('warning' AS UNSIGNED)");cursor.fetchall()
                    receipt=review('parent',add('parent_'+str(use_c)));job=terminal(post,start(receipt));assert job['state']=='committed',job
                    cursor.execute('SHOW WARNINGS');assert cursor.fetchall()
                    cursor.execute('ROLLBACK TO SAVEPOINT independent');cursor.execute('ROLLBACK');cursor.execute('SET autocommit=1')
                    checks.append('independent-interactive-transaction-savepoint-and-warning-area')
                    if online_copy:
                        copying={**selected,'method':'pt-online-schema-change','algorithm':'COPY','lock':'NONE','timeout_seconds':30}
                        receipt=review('t',lambda source:source.replace('varchar(80)','text'),copying)
                        job=start(receipt);deadline=time.monotonic()+20
                        while job.get('controlled_job',{}).get('copy_stage')!='cutover-waiting' and not job.get('controlled_terminal') and time.monotonic()<deadline:
                            time.sleep(.1);job=post('mysql_online_ddl_status',{'review_id':receipt['review_id']})
                        assert job.get('controlled_job',{}).get('copy_stage')=='cutover-waiting',job
                        cursor.execute("UPDATE t SET note='concurrent copy write' WHERE id=1")
                        post('mysql_online_ddl_cutover',{'review_id':receipt['review_id']})
                        job=terminal(post,job);assert job['state']=='committed',job
                        cursor.execute("SHOW COLUMNS FROM t LIKE 'note'");assert cursor.fetchone()[1]=='text'
                        cursor.execute('SELECT note FROM t WHERE id=1');assert cursor.fetchone()[0]=='concurrent copy write'
                        checks.append('admitted-source-utility-native-copy-concurrent-DML-reviewed-cutover-and-cleanup')
                        cursor.execute('ALTER TABLE t MODIFY note VARCHAR(80)')
                        cursor.execute("UPDATE t SET note='preserved' WHERE id=1")
                        for table_name in ('child','parent'):
                            receipt=review(table_name,add('copy_'+str(use_c)),copying);job=start(receipt);deadline=time.monotonic()+20
                            while job.get('controlled_job',{}).get('copy_stage')!='cutover-waiting' and not job.get('controlled_terminal') and time.monotonic()<deadline:
                                time.sleep(.1);job=post('mysql_online_ddl_status',{'review_id':receipt['review_id']})
                            assert job.get('controlled_job',{}).get('copy_stage')=='cutover-waiting',job
                            post('mysql_online_ddl_cutover',{'review_id':receipt['review_id']})
                            job=terminal(post,job);assert job['state']=='committed' and job['outcome']['utility_cleanup_confirmed'],job
                        cursor.execute('INSERT INTO child(id,pid) VALUES(%s,1)',(10+int(use_c),))
                        cursor.execute('SELECT COUNT(*) FROM audit WHERE id=%s',(10+int(use_c),));assert cursor.fetchone()[0]==1
                        cursor.execute("SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA='sr_osc' AND TABLE_NAME='child' AND REFERENCED_TABLE_NAME='parent'")
                        assert cursor.fetchone()[0]==1
                        checks.append('source-utility-existing-trigger-and-incoming-outgoing-foreign-key-preservation')
                        table_name='interrupt_'+str(use_c)
                        receipt=review(table_name,lambda source:source.replace('varchar(80)','text'),copying)
                        job=start(receipt);deadline=time.monotonic()+20
                        while job.get('controlled_job',{}).get('copy_stage')!='cutover-waiting' and not job.get('controlled_terminal') and time.monotonic()<deadline:
                            time.sleep(.1);job=post('mysql_online_ddl_status',{'review_id':receipt['review_id']})
                        assert job.get('controlled_job',{}).get('copy_stage')=='cutover-waiting',job
                        post('mysql_online_ddl_cancel',{'review_id':receipt['review_id']});job=terminal(post,job)
                        assert job['state']=='unknown_outcome' and not job.get('outcome',{}).get('native_copy_cutover_acknowledged'),job
                        observed=post('mysql_online_ddl_observe',{'review_id':receipt['review_id']})
                        assert observed['utility_process']['complete'] and observed['utility_process']['cleanup_confirmed'],observed
                        assert not observed['artifacts']['automatic_removal_authorized']
                        cursor.execute('SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s AND EVENT_OBJECT_TABLE=%s',('sr_osc',table_name))
                        assert cursor.fetchone()[0]==len(observed['artifacts']['additional_source_triggers']),observed
                        cursor.execute('SHOW COLUMNS FROM '+table_name+" LIKE 'note'");assert cursor.fetchone()[1]=='varchar(80)'
                        cursor.execute('SELECT note FROM '+table_name+' WHERE id=1');assert cursor.fetchone()[0]=='preserved'
                        checks.append('native-copy-interruption-retains-original-data-and-independent-cleanup-observations')
                    proof['interfaces'].append({'use_c':use_c,'complete':True,'checks':checks})
                if browser_binary:proof['browser']=browser(app,output,sid,target,post,password,browser_binary,driver_binary,online_copy)
                proof['complete']=True
            finally:cursor.close();oracle.close()
    finally:
        proof['owned_server_stopped']=bool(owned and owned['owned_server_stopped']);proof['complete'] &= proof['owned_server_stopped']
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def browser(app,output,sid,target,post,password,binary,driver_binary,online_copy):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,wait_for_tree_item,invoke_context_action,complete_endpoint_prompt
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import _json
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    driver=None;checks=[]
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1200'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,90);ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def owned(browser):
            return next((n for n in browser.find_elements(By.CSS_SELECTOR,'.file-name') if n.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',n,sid)),None)
        label=wait.until(owned).text;expand(wait,label,('Connectors','MySQL'))
        if complete_endpoint_prompt(driver,password,timeout=5):expand(wait,label,('Connectors','MySQL'))
        database=wait_for_tree_item(wait,'sr_osc',('Connectors','MySQL',label))
        invoke_context_action(wait,driver,database,('Database workspace','MySQL metadata and DDN diagrams...'),handle_endpoint_prompt=False)
        complete_endpoint_prompt(driver,password,timeout=10)
        def click(label):
            item=wait.until(lambda b:next((e for e in b.find_elements(By.TAG_NAME,'button') if e.is_displayed() and e.is_enabled() and e.text==label),None))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',item);item.click()
        def field(label):
            def ready(browser):
                nodes=browser.find_elements(By.XPATH,'//label[contains(text(),"'+label+'")]/following-sibling::div/input | //label[contains(text(),"'+label+'")]/following-sibling::div/textarea')
                return next((n for n in nodes if n.is_displayed() and n.is_enabled()),None)
            return wait.until(ready)
        def select(label,choice):
            node=wait.until(lambda b:b.find_element(By.XPATH,'//label[contains(text(),"'+label+'")]/following-sibling::div/div[@role="combobox"]'))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
            wait.until(lambda b:next((n for n in b.find_elements(By.CSS_SELECTOR,'[role="option"]') if n.is_displayed() and n.text==choice),None)).click()
        for copying in ([False,True] if online_copy else [False]):
            baseline=post('mysql_catalog_export',{})['snapshot'];desired=deepcopy(baseline)
            parsed=read_catalog(json.dumps(baseline),engine='mysql');row=next(r for r in parsed['rows'].values() if r['kind']=='table' and r['name']=='t')
            original=_json(_json(row['native']));native=deepcopy(row['native'])
            native['definition']=(native['definition'].replace('varchar(80)','text') if copying else
                native['definition'].replace(') ENGINE=',', `desktop_native_column` INT NULL) ENGINE='))
            altered=_json(_json(native));desired['files']={name:text.replace(original,altered) for name,text in desired['files'].items()}
            files=[('MySQL baseline DDN file','desktop-baseline.json',baseline),('MySQL catalog DDN file','desktop-desired.json',desired)]
            for aria,name,value in files:
                filename=output/name;filename.write_text(json.dumps(value))
                wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'input[aria-label="'+aria+'"]')).send_keys(str(filename))
            select('Table change execution','Percona online copy' if copying else 'Controlled native ALTER')
            if not copying:select('Native ALTER algorithm','INSTANT')
            click('Preview native changes')
            wait.until(lambda _b:'ALTER TABLE' in field('Native MySQL change preview').get_attribute('value'))
            if not copying:assert 'ALGORITHM=INSTANT, LOCK=DEFAULT' in field('Native MySQL change preview').get_attribute('value')
            click('Validate native changes');click('Prepare reviewed change')
            consent=wait.until(lambda b:b.find_element(By.XPATH,'//label[contains(. ,"Confirm reviewed native DDL and implicit commit")]'))
            wait.until(lambda _b:consent.find_element(By.TAG_NAME,'input').is_enabled())
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',consent);consent.click()
            wait.until(lambda _b:consent.find_element(By.TAG_NAME,'input').is_selected())
            click('Start controlled ALTER')
            if copying:click('Allow reviewed copy cutover')
            wait.until(lambda b:'Controlled job: terminal' in b.find_element(By.CSS_SELECTOR,'[aria-label="Controlled MySQL DDN change"]').text)
            panel=driver.find_element(By.CSS_SELECTOR,'[aria-label="Controlled MySQL DDN change"]');assert 'Native outcome: committed' in panel.text
            click('Observe current native table');definition=field('Controlled ALTER current native definition')
            wait.until(lambda _b:('text' if copying else 'desktop_native_column') in definition.get_attribute('value'))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',definition)
            driver.save_screenshot(str(output/('native-online-copy.png' if copying else 'native-controlled-ddl.png')))
            checks.append('built-DDN-online-copy-review-explicit-cutover-and-native-observation' if copying else 'built-DDN-INSTANT-policy-validation-review-dispatch-and-native-observation')
        errors=[r for r in driver.get_log('browser') if r['level']=='SEVERE'];assert not errors,errors
        return {'complete':True,'checks':checks,'console_errors':errors}
    except Exception:
        if driver:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();thread.join(timeout=10)


def qualify_desktop(output,binary,driver_binary):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    paths=[str(Path(__file__).relative_to(ROOT)),'web/pgadmin/static/js/Dialogs/MySQLCatalog.jsx',
        'web/pgadmin/static/js/Dialogs/MySQLControlledChange.jsx']
    proof={'complete':False,'scope':'built desktop','history_testing':'not run',
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    owned=None
    try:
        with server(output/'fixture') as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;cursor=oracle.cursor()
            try:
                cursor.execute('CREATE DATABASE sr_osc CHARACTER SET utf8mb4')
                cursor.execute('CREATE TABLE sr_osc.t(id INT PRIMARY KEY,note VARCHAR(80))')
                cursor.execute("INSERT INTO sr_osc.t VALUES(1,'preserved')")
                password=secrets.token_urlsafe(24);cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                app=setup_application(output);sid,target,post=registration(app,route,password,True)
                proof['browser']=browser(app,output,sid,target,post,password,binary,driver_binary,True)
                cursor.execute("SHOW COLUMNS FROM sr_osc.t LIKE 'note'");assert cursor.fetchone()[1]=='text'
                cursor.execute('SELECT note FROM sr_osc.t WHERE id=1');assert cursor.fetchone()[0]=='preserved'
                proof['independent_native_oracle']=True;proof['complete']=True
            finally:cursor.close();oracle.close()
    finally:
        proof['owned_server_stopped']=bool(owned and owned['owned_server_stopped']);proof['complete'] &= proof['owned_server_stopped']
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--online-copy',action='store_true');parser.add_argument('--desktop-only',action='store_true');parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');args=parser.parse_args();qualify_desktop(args.output,args.browser_binary,args.driver_binary) if args.desktop_only else qualify(args.output,args.online_copy,args.browser_binary,args.driver_binary)
