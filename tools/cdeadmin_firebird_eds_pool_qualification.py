"""Owned Firebird5.0.4 network/embedded process-pool and authenticated API proof."""
import argparse
import builtins
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(runtime,output,*,browser_binary=None,driver_binary=None):
    from tools.cdeadmin_native_editor_gate import provider
    from tools.cdeadmin_firebird_local_fixture import run_local
    from tools.cdeadmin_firebird_password_gate import _route_arguments
    from pgadmin.cdeadmin.providers.firebird import eds_pool
    from pgadmin.cdeadmin.workspace.firebird_eds_pool_receipts import EDSPoolReceipts
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    proof={'complete':False,'full_product_complete':False,'history_testing':'not run','interfaces':[]}
    paths=['tools/cdeadmin_firebird_eds_pool_qualification.py',
        'web/pgadmin/cdeadmin/providers/firebird/eds_pool.py','web/pgadmin/cdeadmin/providers/firebird/query_client.py',
        'web/pgadmin/cdeadmin/providers/firebird/provider.py','web/pgadmin/cdeadmin/workspace/firebird_eds_pool_receipts.py',
        'web/pgadmin/cdeadmin/workspace/service.py','web/pgadmin/cdeadmin/data_studio/studio.py',
        'web/pgadmin/browser/server_groups/servers/__init__.py','web/pgadmin/static/js/Dialogs/FirebirdEDSPool.jsx',
        'web/pgadmin/static/js/Dialogs/ProviderWorkspaceContent.jsx']
    proof['source_sha256']={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in paths}

    def check(native,network_admin,network_route,accounts,_evidence,root):
        user,password=accounts['Srp'][0]
        def native_session(route,secret,embedded):
            instance,target=provider('firebird',route,secret,embedded=embedded)
            opened=instance.open_session({'route':target});handle=instance._sessions[opened['session_id']].handle
            archive=EDSPoolReceipts(output/('embedded-receipts.json' if embedded else 'network-receipts.json'),1,'owned',str(embedded))
            def action(operation,**fields):return instance.eds_pool_action({'session_id':opened['session_id'],
                'language_profile':'firebird-sql','operation':operation,**fields},archive)
            def command(draft,acknowledged=True):
                review=action('review',draft=draft)
                request={'review_id':review['review_id'],'review_digest':review['review_digest'],
                    'confirmation':review['native_before']['server_process_id'],'confirmed':True}
                action('apply',**request)
                task=instance.client._eds_pool_reviews[review['review_id']]['token'];task.worker.join(15)
                assert task.done
                receipt=action('receipt',review_id=review['review_id'])
                assert receipt['native_acknowledged'] is acknowledged,receipt
                assert not receipt.get('session_reuse_blocked'),receipt
                assert action('apply',**request)['state']==receipt['state']
                return receipt
            try:
                before=action('inventory')['native_pool'];assert not handle.main_transaction.is_active()
                assert before['database']==route['database'] and before['server_process_id'].isdecimal()
                with handle.cursor() as cursor:
                    cursor.execute('SELECT MON$REMOTE_PROTOCOL FROM MON$ATTACHMENTS WHERE MON$ATTACHMENT_ID=CURRENT_CONNECTION')
                    protocol=cursor.fetchone()[0]
                assert (protocol is None) if embedded else bool(protocol)
                handle.rollback()
                # Native privilege refusal is observed before granting the exact system privilege.
                if not embedded:
                    denied=command({'action':'set_size','value':31},False)
                    assert denied['native_returned_error'] and denied['native_status_codes']
                    handle.rollback()
                    network_admin.execute_immediate('CREATE ROLE OWNED_EDS_ROLE SET SYSTEM PRIVILEGES TO MODIFY_EXT_CONN_POOL')
                    network_admin.execute_immediate('GRANT DEFAULT OWNED_EDS_ROLE TO USER '+user)
                    network_admin.commit()
                    with handle.cursor() as cursor:cursor.execute('SET ROLE OWNED_EDS_ROLE')
                    handle.commit()
                    network_admin.execute_immediate('CREATE TABLE EDS_KEEP(ID INTEGER)')
                    network_admin.execute_immediate('GRANT SELECT,INSERT ON EDS_KEEP TO USER '+user)
                    network_admin.commit()
                else:
                    with handle.cursor() as cursor:cursor.execute('CREATE TABLE EDS_KEEP(ID INTEGER)')
                    handle.commit()
                from pgadmin.cdeadmin.providers.firebird.provider import _resources
                resources=_resources(handle,route)
                catalog=next(value for value in resources if value['resource_kind']=='database')['native']['external_connection_pool']
                assert catalog['available'] and catalog['attachment_id']==before['attachment_id']
                handle.rollback()
                def configuration():
                    with handle.cursor() as cursor:
                        cursor.execute("SELECT RDB$CONFIG_NAME,RDB$CONFIG_VALUE FROM RDB$CONFIG WHERE RDB$CONFIG_NAME STARTING WITH 'ExtConnPool'")
                        return cursor.fetchall()
                configured=configuration() if embedded else None
                if handle.main_transaction.is_active():handle.rollback()
                with handle.cursor() as cursor:
                    cursor.execute('INSERT INTO EDS_KEEP VALUES(1)');cursor.execute('SAVEPOINT EDS_KEEP_POINT')
                transaction=handle.main_transaction.info.id
                size=command({'action':'set_size','value':31})
                lifetime=command({'action':'set_lifetime','value':1,'unit':'MINUTE'})
                assert size['native_after']['size']=='31' and lifetime['native_after']['lifetime_seconds']=='60'
                if embedded:assert configuration()==configured
                assert handle.main_transaction.info.id==transaction
                with handle.cursor() as cursor:
                    cursor.execute('ROLLBACK TO SAVEPOINT EDS_KEEP_POINT')
                    cursor.execute('SELECT COUNT(*) FROM EDS_KEEP');assert cursor.fetchone()==(1,)
                handle.rollback()
                assert action('inventory')['native_pool']['size']=='31'
                with handle.cursor() as cursor:
                    cursor.execute('SELECT COUNT(*) FROM EDS_KEEP');assert cursor.fetchone()==(0,)
                handle.rollback()
                # A real owned EDS connection, using native credentials only in fixture memory.
                external={**route,'database':str(root/('eds-external-'+str(embedded)+'.fdb'))}
                with native.create_database(**_route_arguments(external,native),**({'password':secret} if secret else {})) as external_setup:
                    external_setup.execute_immediate('CREATE TABLE EDS_MARKER(ID INTEGER)');external_setup.commit()
                destination=external['database'] if embedded else str(route['host'])+'/'+str(route['port'])+':'+external['database']
                literal=lambda value:"'"+value.replace("'","''")+"'"
                sql="EXECUTE BLOCK RETURNS(V INTEGER) AS BEGIN EXECUTE STATEMENT 'SELECT 1 FROM RDB$DATABASE' ON EXTERNAL DATA SOURCE "+literal(destination)
                sql+=' AS USER '+literal(route['user'])
                if secret:sql+=' PASSWORD '+literal(secret)
                sql+=' INTO :V; SUSPEND; END'
                command({'action':'clear_all'})
                with handle.cursor() as cursor:cursor.execute(sql);assert cursor.fetchone()==(1,)
                handle.commit()
                idle=action('inventory')['native_pool'];assert int(idle['idle_count'])>=1,idle
                command({'action':'clear_oldest'})
                assert int(action('inventory')['native_pool']['idle_count'])>=1
                command({'action':'set_lifetime','value':1,'unit':'SECOND'})
                time.sleep(1.1);command({'action':'clear_oldest'})
                assert action('inventory')['native_pool']['idle_count']=='0'
                insert=sql.replace("EXECUTE STATEMENT 'SELECT 1 FROM RDB$DATABASE'", "EXECUTE STATEMENT 'INSERT INTO EDS_MARKER VALUES(73) RETURNING ID'")
                with handle.cursor() as cursor:cursor.execute(insert);assert cursor.fetchone()==(73,)
                active=action('inventory')['native_pool'];assert int(active['active_count'])>=1,active
                command({'action':'clear_all'})
                assert action('inventory')['native_pool']['active_count']=='0'
                # Clearing tracked bindings does not cancel the caller's external transaction.
                with handle.cursor() as cursor:cursor.execute(sql);assert cursor.fetchone()==(1,)
                handle.commit()
                with native.connect(**_route_arguments(external,native),**({'password':secret} if secret else {})) as independent:
                    with independent.cursor() as cursor:
                        cursor.execute('SELECT ID FROM EDS_MARKER');assert cursor.fetchall()==[(73,)]
                rejected=False
                try:
                    with handle.cursor() as cursor:cursor.execute("ALTER EXTERNAL CONNECTIONS POOL CLEAR 'owned database'")
                except native.DatabaseError:rejected=True
                assert rejected;handle.rollback()
                command({'action':'set_size','value':int(before['size'])})
                command({'action':'set_lifetime','value':int(before['lifetime_seconds'])//60,'unit':'MINUTE'})
                command({'action':'clear_all'});handle.rollback()
                saved=archive.get(size['review_id'])
                assert saved['native_acknowledged'] and not saved['transaction_finality_inferred']
                proof['interfaces'].append({'embedded':embedded,'native_before':before,
                    'exact_system_privilege_enforced':not embedded,'pending_transaction_and_savepoint_preserved':True,
                    'pool_settings_survive_caller_rollback':True,'actual_external_connections_pooled':True,
                    'clear_oldest_removes_expired_idle_only':True,'clear_all_removes_active_bindings_preserves_external_transaction':True,
                    'native_clear_database_refused':True,'durable_acknowledgement_no_replay':True})
            finally:instance.client.close()
            restored=EDSPoolReceipts(archive.path,*archive.binding)
            assert restored.get(size['review_id'])['native_acknowledged']

        native_session({**network_route,'user':user},password,False)
        path=root/'embedded-eds.fdb'
        with native.create_database(database=str(path),user='SYSDBA',charset='UTF8'):
            native_session({'database':str(path),'filesystem_root':str(root),'user':'SYSDBA',
                'attachment_mode':'embedded','charset':'UTF8'},None,True)
        proof['authenticated_api']=qualify_api(output,network_route,user,password,str(path),str(root),
            browser_binary=browser_binary,driver_binary=driver_binary)
    try:
        fixture=run_local(runtime,output,check)
        proof.update(complete=fixture['complete'],owned_process_stopped=fixture['owned_process_stopped'],owned_state_removed=fixture['owned_state_removed'])
    finally:
        output.mkdir(parents=True,exist_ok=True)
        (output/'proof.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False)+'\n')
    assert proof['complete'],proof
    return proof


def qualify_api(output,route,username,password,embedded_database,root,*,browser_binary=None,driver_binary=None):
    builtins.SERVER_MODE=None
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    for name,value in {'DATA_DIR':'app','SQLITE_PATH':'app/application.db','SESSION_DB_PATH':'app/sessions',
        'STORAGE_DIR':'app/storage','LOG_FILE':'app/application.log','AZURE_CREDENTIAL_CACHE_DIR':'app/azure',
        'CDEADMIN_OPERATION_STORE_PATH':'app/operations.json'}.items():setattr(config,name,str(output/value))
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from flask import url_for,request as flask_request
    app=create_app('ScratchRobin owned Firebird EDS pool');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start();client=app.test_client();results=[]
    verification_audit=[]
    @app.after_request
    def observe_verification(response):
        if '/verify_endpoint/' in flask_request.path:
            values=flask_request.form or flask_request.get_json(silent=True) or {}
            body=response.get_json(silent=True) or {}
            verification_audit.append({'status':response.status_code,'password_present':bool(values.get('password')),
                'matches_owned_secret':values.get('password')==password,'alternate_user_supplied':bool(values.get('connect_as')),
                'error':str(body.get('errormsg','')).replace(password,'[owned secret]')})
            (output/'verification-audit.json').write_text(json.dumps(verification_audit,indent=2)+'\n')
        return response
    for embedded in (False,True):
        session=None
        with app.test_request_context('/'):
            owner=User.query.first().id;group=ServerGroup.query.filter_by(user_id=owner).first()
            profile='firebird-embedded' if embedded else 'firebird-native'
            database=embedded_database if embedded else route['database']
            server=Server(user_id=owner,servergroup_id=group.id,name='Owned EDS '+profile,
                host=None if embedded else route['host'],port=1 if embedded else route['port'],
                username='SYSDBA' if embedded else username,maintenance_db=database,save_password=0)
            server._cde_endpoint_registration=registration_profile(profile)
            server._cde_endpoint_route_configuration=({'database':database,'filesystem_root':root,'attachment_mode':'embedded','user':'SYSDBA'} if embedded else
                {**route,'user':username,'auth_plugin_list':'Srp256'})
            db.session.add(server);db.session.commit();target=str(uuid.uuid4());other=str(uuid.uuid4())
            for identity in (target,other):db.session.add(EndpointDatabaseTarget(id=identity,endpoint_id=server.endpoint_profile.id,
                display_name=identity,database=database,configuration='{}',active=1))
            db.session.commit()
            url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=server.id)
            verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=server.id)
            service=service_for_app(app)
            if browser_binary:
                for key in app.blueprints['NODE-engine_type'].connector_visibility:
                    if 'firebird' in key:app.blueprints['NODE-engine_type'].connector_visibility[key].set(True,user_id=owner)
            server_id=server.id
        with client.session_transaction() as login:login['_user_id']=str(owner);login['_fresh']=True
        response=client.post(verify,json={} if embedded else {'password':password})
        assert response.get_json().get('success'),response.get_json()
        def post(action,refused=False,**fields):
            response=client.post(url,json={'action':action,'database_target_id':target,**fields});value=response.get_json()
            assert password not in json.dumps(value)
            if refused:assert response.status_code in {400,403,409},value;return value
            assert response.status_code==200 and value.get('success'),value
            return value['data']
        def eds(operation,**fields):return post('firebird_eds_pool',session_id=session,request={'operation':operation,**fields})
        try:
            session=post('open_session',language_profile='firebird-sql')['session_id']
            inventory=eds('inventory');size=int(inventory['native_pool']['size'])
            review=eds('review',draft={'action':'set_size','value':31 if size!=31 else 32})
            options={'review_id':review['review_id'],'review_digest':review['review_digest'],'confirmed':True,
                'confirmation':review['native_before']['server_process_id']}
            eds('apply',**options);deadline=time.monotonic()+15
            while True:
                receipt=eds('receipt',review_id=review['review_id'])
                if not receipt['native_operation_running']:break
                assert time.monotonic()<deadline;time.sleep(.03)
            assert receipt['native_acknowledged'] and receipt['requested_settings_observed']
            post('firebird_eds_pool',True,database_target_id=other,session_id=session,request={'operation':'receipt','review_id':review['review_id']})
            post('firebird_eds_pool_receipts',True,database_target_id=other,request={'operation':'receipt','review_id':review['review_id']})
            mismatch=client.post(url+'?database_target_id='+target,json={'action':'firebird_eds_pool_receipts',
                'database_target_id':other,'request':{'operation':'list'}})
            assert mismatch.status_code==400
            # Restore owned process settings via the same reviewed native path.
            restore=eds('review',draft={'action':'set_size','value':size})
            eds('apply',review_id=restore['review_id'],review_digest=restore['review_digest'],confirmed=True,confirmation=restore['native_before']['server_process_id'])
            deadline=time.monotonic()+15
            while eds('receipt',review_id=restore['review_id'])['native_operation_running']:
                assert time.monotonic()<deadline;time.sleep(.03)
            post('close_session',session_id=session);session=None
            browser=None
            if browser_binary:
                browser=qualify_browser(app,output/('browser-embedded' if embedded else 'browser-network'),
                    browser_binary,driver_binary,server_id,target,None if embedded else password,url)
                assert not app.extensions['cdeadmin_data_studio']._sessions
            with patch.object(service.endpoint_service,'workspace',side_effect=AssertionError('Archive opened SQL workspace')):
                kept=post('firebird_eds_pool_receipts',request={'operation':'receipt','review_id':review['review_id']})
                page=post('firebird_eds_pool_receipts',request={'operation':'list','offset':0,'limit':1})
                assert kept['archived_read_only'] and kept['native_acknowledged'] and page['more']
                post('firebird_eds_pool_receipts',True,request={'operation':'remove','review_id':review['review_id'],
                    'review_digest':review['review_digest'],'confirmed':False})
                removed=post('firebird_eds_pool_receipts',request={'operation':'remove','review_id':review['review_id'],
                    'review_digest':review['review_digest'],'confirmed':True})
                assert not removed['native_operation_requested']
                post('firebird_eds_pool_receipts',True,request={'operation':'receipt','review_id':review['review_id']})
            results.append({'embedded':embedded,'original_session_control':True,'native_acknowledgement':True,
                'cross_target_and_url_scope_refused':True,'post_close_archive_without_sql_workspace':True,'browser':browser})
        finally:
            if session:post('close_session',session_id=session)
    assert not app.extensions['cdeadmin_data_studio']._sessions
    return results


def qualify_browser(app,output,binary,driver_binary,server_id,target,password,workspace_url):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException,ElementClickInterceptedException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand
    output.mkdir(parents=True,exist_ok=False)
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True)
    thread.start();driver=None
    original_sessions=set(app.extensions['cdeadmin_data_studio']._sessions)
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1400'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary) if driver_binary else Service())
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,90,ignored_exceptions=(StaleElementReferenceException,ElementClickInterceptedException))
        ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'Firebird')
        def own(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,server_id)),None)
        element=wait.until(own)
        driver.execute_script('const t=window.pgAdmin.Browser.tree;const item=t.itemFrom(arguments[0].closest(".file-entry"));const n=window.pgAdmin.Browser.Nodes.server;n.callbacks.open_cde_workspace.call(n,{item},"studio",{database_target_id:arguments[1]});',element,target)
        def click(label):
            def attempt(browser):
                node=next((node for node in browser.find_elements(By.TAG_NAME,'button') if node.is_displayed() and node.is_enabled() and node.text.strip()==label),None)
                if node is None:return False
                browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node);node.click();return True
            wait.until(attempt)
        opened_at=time.monotonic();reopened=False
        def summary(browser):
            nonlocal reopened
            dialogs=[node for node in browser.find_elements(By.CSS_SELECTOR,'[role="dialog"]') if node.is_displayed() and 'Verify Endpoint' in node.text]
            if dialogs:
                dialog=dialogs[0]
                fields=[node for node in dialog.find_elements(By.CSS_SELECTOR,'input[type="password"]') if node.is_displayed()]
                if fields:
                    assert password
                    if not fields[0].get_attribute('value'):fields[0].send_keys(password)
                button=next((node for node in dialog.find_elements(By.TAG_NAME,'button') if node.is_enabled() and node.text.strip()=='OK'),None)
                if button:button.click()
                return False
            node=next((node for node in browser.find_elements(By.TAG_NAME,'summary') if node.is_displayed() and node.text.strip()=='Firebird external connection pool'),None)
            if node is None:
                options_tab=next((node for node in browser.find_elements(By.TAG_NAME,'button') if node.is_displayed() and node.is_enabled() and node.text.strip()=='Engine options'),None)
                if options_tab:
                    browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',options_tab);options_tab.click()
                    return False
                if not reopened and time.monotonic()-opened_at>3:
                    selected=own(browser)
                    # Initial explorer restoration can replace the tree item
                    # while the credential prompt owns its original callback.
                    # Reopen through the normal action on the current item;
                    # readiness and native verification remain application-owned.
                    if selected is not None:
                        reopened=True
                        browser.execute_script('const t=window.pgAdmin.Browser.tree;const item=t.itemFrom(arguments[0].closest(".file-entry"));const n=window.pgAdmin.Browser.Nodes.server;n.callbacks.open_cde_workspace.call(n,{item},"studio",{database_target_id:arguments[1]});',selected,target)
                return False
            browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node)
            if node.find_element(By.XPATH,'..').get_attribute('open') is None:node.click()
            return True
        wait.until(summary);click('Inspect native EDS pool')
        def observation(browser):
            nodes=browser.find_elements(By.CSS_SELECTOR,'[aria-label="Native Firebird EDS pool"]')
            return json.loads(nodes[0].text) if nodes and nodes[0].text else False
        observed=wait.until(observation);pid=observed['native_pool']['server_process_id']
        def input_named(label):
            node=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'label') if node.is_displayed() and node.text.strip()==label),None))
            identifier=node.get_attribute('for');return driver.find_element(By.ID,identifier) if identifier else node.find_element(By.CSS_SELECTOR,'input')
        quantity=input_named('Native EDS pool quantity');quantity.send_keys(Keys.CONTROL,'a');quantity.send_keys(observed['native_pool']['size'])
        click('Review native EDS pool change')
        confirmation=input_named('Confirm native EDS engine process ID');confirmation.send_keys(pid)
        check=input_named('I reviewed the shared process scope and effects outside rollback');check.click()
        click('Apply reviewed EDS change once')
        def completed(browser):
            nodes=browser.find_elements(By.CSS_SELECTOR,'[aria-label="Firebird EDS operation receipt"]')
            value=json.loads(nodes[0].text) if nodes and nodes[0].text else {}
            return value if value.get('native_acknowledged') and value.get('native_operation_running') is False else False
        result=wait.until(completed);assert result['requested_settings_observed']
        driver.save_screenshot(str(output/'acknowledged.png'))
        click('Load retained EDS receipts')
        wait.until(lambda browser:any(node.is_displayed() and 'Inspect EDS receipt' in node.text for node in browser.find_elements(By.TAG_NAME,'button')))
        close=wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'button[aria-label="Close query session"]') if node.is_displayed() and node.is_enabled()),None))
        driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',close);close.click()
        wait.until(lambda browser:'Session not open' in browser.find_element(By.TAG_NAME,'body').text)
        severe=[entry for entry in driver.get_log('browser') if entry['level']=='SEVERE']
        challenges=[entry for entry in severe if entry.get('source')=='network' and
            entry['message'].startswith('http://127.0.0.1:'+str(http.server_port)+'/browser/server/verify_endpoint/') and
            'status of 401 (UNAUTHORIZED)' in entry['message']]
        errors=[entry for entry in severe if entry not in challenges]
        assert not errors,[{'level':item['level'],'message':item['message'][:200]} for item in errors]
        return {'complete':True,'native_pool_observed':True,'reviewed_original_attachment_change_acknowledged':True,
            'retained_receipts_discoverable':True,'unexpected_console_errors':len(errors),
            'expected_credential_challenges':len(challenges),'console_errors_total':len(severe)}
    except BaseException:
        if driver:
            driver.save_screenshot(str(output/'failure.png'))
            logs=driver.get_log('browser')
            (output/'browser-errors.json').write_text(json.dumps([entry for entry in logs if entry['level']=='SEVERE'],indent=2)+'\n')
        raise
    finally:
        try:
            if driver:
                try:
                    for identity in set(app.extensions['cdeadmin_data_studio']._sessions)-original_sessions:
                        driver.set_script_timeout(30)
                        driver.execute_async_script('const done=arguments[3];fetch(arguments[0],{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"close_session",database_target_id:arguments[1],session_id:arguments[2]})}).then(r=>done(r.status)).catch(()=>done(0));',workspace_url,target,identity)
                finally:driver.quit()
        finally:http.shutdown();thread.join(10);http.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');args=parser.parse_args()
    value=qualify(args.runtime,args.evidence,browser_binary=args.browser_binary,driver_binary=args.driver_binary)
    print(json.dumps({'complete':value['complete']}))
