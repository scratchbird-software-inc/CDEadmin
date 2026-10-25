"""Native variable catalog, typed assignments and private editor metadata."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]

META='SELECT VARIABLE_NAME,VARIABLE_SCOPE,DATA_TYPE,MIN_VALUE,MAX_VALUE,DOCUMENTATION FROM performance_schema.variables_metadata ORDER BY VARIABLE_NAME'
CASES=[('SELECT @@ba|','basedir'),('SELECT @@GLOBAL.vali|','validate_password.length'),
       ('SELECT @@GLOBAL.validate_password.le|','validate_password.length'),
       ('SELECT @@SESSION.sql_m|','sql_mode'),('SELECT @@LOCAL.sql_m|','sql_mode'),
       ('SELECT @@gtid_ne|','gtid_next'),('SET SESSION sql_m| = DEFAULT','sql_mode'),
       ('SET PERSIST validate_password.le| = DEFAULT','validate_password.length'),
       ('SET @@PERSIST_ONLY.validate_password.le| = DEFAULT','validate_password.length'),
       ('SELECT @@GLOBAL.`validate_password.le|`','validate_password.length'),
       ("SELECT @@GLOBAL.'validate_password.le|'",'validate_password.length')]


def qualify(output,library=None,binary=None,driver_binary=None):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION,_create_client,_resources
    from pgadmin.cdeadmin.providers.mysql_family.mysql_server_catalog import capture
    from pgadmin.cdeadmin.providers.mysql_family.mysql_completion import complete
    from pgadmin.cdeadmin.providers.mysql_server_application import apply_operation
    from pgadmin.cdeadmin.workspace.mysql_server_plan import plan
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep evidence outside source')
    output.mkdir(parents=True,exist_ok=False)
    if binary:
        library=Path(library).resolve(strict=True);os.environ['CDEADMIN_MYSQL_PARSER_LIBRARY']=str(library)
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('system_variables.py','mysql_server_catalog.py','provider.py')]
    paths+=['web/pgadmin/cdeadmin/providers/'+name for name in ('native_editor.py','mysql_server_operations.py','mysql_server_application.py')]
    paths+=['web/pgadmin/static/js/cdeadmin_ui/editors/'+name for name in ('nativeCompletion.js','nativeScopes.js','mysqlVariables.js')]
    paths+=['tools/cdeadmin_mysql_variable_metadata_qualification.py']
    proof={'complete':False,'interfaces':[],'full_mysql_product_complete':False,'history_testing':'not run',
           'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    fixture={'groups':[]};owned_status=None
    try:
        with server(output/'fixture') as (route,_name,owned):
            owned_status=owned;oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
            try:
                q.execute("INSTALL COMPONENT 'file://component_validate_password'")
                q.execute("INSTALL COMPONENT 'file://component_mysqlbackup'")
                q.execute('CREATE DATABASE sr_workspace');q.execute('CREATE TABLE sr_workspace.t(id INT PRIMARY KEY)')
                q.execute('CREATE TABLE sr_workspace.pending(id INT PRIMARY KEY)')
                q.execute('SELECT @@GLOBAL.sql_mode');initial_mode=q.fetchone()[0]
                q.execute(META);expected={r[0]:r[1:] for r in q.fetchall()}
                assert expected['gtid_next'][0]=='SESSION_ONLY' and expected['validate_password.length'][1]=='Integer'
                for pure in (True,False):
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    selected={**route,'use_pure':pure,'database':'sr_workspace'};native=client._connect({'route':selected});native.autocommit=True
                    checks=[];templates={};variants={}
                    try:
                        cls=type(native).__name__;assert cls==('CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection')
                        discovery=capture(native)
                        catalog={r['display_name']:r for r in discovery['resources'] if r['resource_kind']=='system-variable'}
                        for name,(scope,kind,minimum,maximum,documentation) in expected.items():
                            facts=catalog[name]['native']['catalog_row']
                            assert (facts['variable_scope'],facts['data_type'],facts['native_min_value'],facts['native_max_value'],facts['documentation'])==(scope,kind,minimum,maximum,documentation)
                        resources=_resources(native,{'route':selected},MYSQL_PROFILE)
                        navigation={r['display_name']:r for r in resources if r['resource_kind']=='system-variable'}
                        assert set(expected)<=set(navigation)
                        assert navigation['gtid_next']['native']['administration']['allowed_operations']==['inspect']
                        checks.append({'scope':'native-metadata-and-navigation','metadata_names':len(expected),'all_native_rows_reconciled':True,'session_only_global_actions_excluded':True})
                        def execute(operation,name,**draft):
                            target=navigation[name]
                            request={'resource_kind':'system-variable','operation_id':operation,'target_resource':target,
                                     'draft':{'confirmation':name,**draft},'_provider_route':selected}
                            planned=client.plan_admin_operation(request)
                            sql=planned['provider_payload']['compiled']['statements'][0]['source']
                            templates.setdefault(operation,sql);variants.setdefault(operation,set()).add(sql)
                            reply=MYSQL_ADMINISTRATION.apply(client,planned);assert reply['accepted']
                            return reply
                        execute('set_global','innodb_max_dirty_pages_pct',value_type='DOUBLE',value='1e-31')
                        q.execute('SELECT @@GLOBAL.innodb_max_dirty_pages_pct');observed=q.fetchone()[0]
                        execute('set_global','mysqlbackup.backupid',value_mode='NULL')
                        q.execute('SELECT @@GLOBAL.`mysqlbackup.backupid` IS NULL');assert q.fetchone()==(1,)
                        execute('set_persist','long_query_time',value_type='DOUBLE',value='1.25')
                        q.execute('SELECT @@GLOBAL.long_query_time');assert q.fetchone()==(1.25,)
                        execute('set_persist_only','long_query_time',value_type='DOUBLE',value='2.5')
                        q.execute('SELECT @@GLOBAL.long_query_time');assert q.fetchone()==(1.25,)
                        execute('reset_persist','long_query_time')
                        execute('set_global','max_execution_time',value_type='INTEGER',value='0')
                        checks.append({'scope':'typed-double-null-and-persistence','native_double_observation':str(observed),'native_runtime_null_observed':True,'persist_only_left_runtime_unchanged':True})
                        acquired=capture(native)
                        baseline=build_export(acquired['resources'],endpoint_id='owned',target_id='server:'+acquired['server_uuid'],generation=acquired['generation'],include_system=True,refreshed=True,engine='mysql',native_model=True)
                        import copy
                        desired=copy.deepcopy(baseline)
                        row=next(r for r in desired['rows'].values() if r['kind']=='system-variable' and r['native']['catalog_row']['variable_name']=='mysqlbackup.backupid')
                        row['native']['mysql_change']={'action':'set_global','draft':{'value_mode':'NULL'},'confirmation':'mysqlbackup.backupid'}
                        reviewed=plan(baseline,desired,baseline);reviewed['endpoint_id']='owned';assert reviewed['ready_for_review'] and len(reviewed['operations'])==1
                        result=apply_operation(native,{'plan':reviewed,'baseline':baseline,'desired':desired},reviewed['operations'][0])
                        assert result['state']=='acknowledged' and result['rediscovery_verified'] and result['native_runtime_null']
                        checks.append({'scope':'native-ddn-null-rediscovery','explicit_native_is_null':True,'persisted_null_identity_inferred':False})
                        # Native P_S exposes a persisted NULL as empty text,
                        # not a nullable typed value. Preserve its presence and
                        # ACK without claiming that this proves NULL identity.
                        for name,assignment,initial_value in [('innodb_tmpdir',{'value_mode':'NULL'},'/tmp'),
                                ('init_connect',{'value':''},'SET @sr_owned_init=1')]:
                            for action in ('set_persist_only','set_persist'):
                                execute('set_global',name,value=initial_value,value_type='AUTO')
                                acquired=capture(native)
                                baseline=build_export(acquired['resources'],endpoint_id='owned',target_id='server:'+acquired['server_uuid'],generation=acquired['generation'],include_system=True,refreshed=True,engine='mysql',native_model=True)
                                desired=copy.deepcopy(baseline)
                                row=next(r for r in desired['rows'].values() if r['kind']=='system-variable' and r['name']==name)
                                row['native']['mysql_change']={'action':action,'draft':assignment,'confirmation':name}
                                reviewed=plan(baseline,desired,baseline);reviewed['endpoint_id']='owned'
                                assert reviewed['ready_for_review'] and len(reviewed['operations'])==1
                                reply=apply_operation(native,{'plan':reviewed,'baseline':baseline,'desired':desired},reviewed['operations'][0])
                                assert reply['state']=='acknowledged' and not reply['rediscovery_verified'],reply
                                q.execute('SELECT @@GLOBAL.`'+name+'` IS NULL,@@GLOBAL.`'+name+'`')
                                expected_runtime=((0,initial_value) if action=='set_persist_only' else (1,None) if name=='innodb_tmpdir' else (0,''))
                                assert q.fetchone()==expected_runtime
                                q.execute('SELECT VARIABLE_VALUE FROM performance_schema.persisted_variables WHERE VARIABLE_NAME=%s',(name,))
                                assert q.fetchone()==('',)
                                facts=next(r for r in capture(native)['resources'] if r['resource_kind']=='system-variable' and r['display_name']==name)['native']['catalog_row']
                                assert facts['persisted_present']==1 and facts['persisted_value']==''
                                assert facts['persisted_value_state']=='null_or_empty'
                                assert reply['persisted_value_identity_unconfirmed'] and reply['native_persisted_value_state']=='null_or_empty'
                                execute('reset_persist',name)
                                q.execute('SELECT VARIABLE_VALUE FROM performance_schema.persisted_variables WHERE VARIABLE_NAME=%s',(name,))
                                assert q.fetchone() is None
                                checks.append({'scope':'native-persisted-'+name+'-'+action,'native_ack_preserved':True,
                                    'persisted_presence_retained':True,'native_persisted_value_is_empty_text':True,
                                    'persisted_null_identity_inferred':False,'reset_removes_identity':True})
                        execute('set_global','init_connect',value='',value_type='AUTO')
                        for mode in ('','ANSI_QUOTES,NO_BACKSLASH_ESCAPES'):
                            q.execute('SET GLOBAL sql_mode=%s',(mode,));q.execute('SET SESSION sql_mode=%s',(mode,))
                            handle=client.open_session({'route':selected});work=handle.cursor()
                            try:
                                client.control_transaction(handle,'autocommit_off')
                                work.execute('SAVEPOINT variable_metadata_guard');work.execute('INSERT INTO pending VALUES(7)')
                                connection_id=handle.connection_id
                                q.execute('SELECT THREAD_ID FROM performance_schema.threads WHERE PROCESSLIST_ID=%s',(connection_id,));thread=q.fetchone()[0]
                                def commands():
                                    q.execute('SELECT COALESCE(SUM(COUNT_STAR),0) FROM performance_schema.events_statements_summary_by_thread_by_event_name WHERE THREAD_ID=%s',(thread,))
                                    return int(q.fetchone()[0])
                                before=commands();metadata=complete(client,handle);after=commands()
                                assert before>0 and before==after and metadata['original_diagnostics_preservation_qualified'] and metadata['original_session_commands_sent']==0
                                work.execute('SELECT ROW_COUNT()');assert work.fetchone()==(1,)
                                observed_vars={r['display_name']:r for r in metadata['resources'] if r['resource_kind']=='system-variable'}
                                assert set(expected)<=set(observed_vars)
                                assert observed_vars['gtid_next']['native_variable']['scope']=='SESSION_ONLY'
                                cases=[]
                                for marked,name in CASES:
                                    text=marked.replace('|','');position=marked.index('|');start=text.rfind('@@',0,position)
                                    # Expected canonical insertions are explicit native SQL,
                                    # independently executed before the JS fixture consumes them.
                                    quote='`'+name.replace('`','``')+'`'
                                    if text.startswith('SET SESSION'):sql='SET SESSION '+quote+' = DEFAULT'
                                    elif text.startswith('SET PERSIST '):sql='SET PERSIST '+quote+' = DEFAULT'
                                    elif text.startswith('SET @@PERSIST_ONLY.'):sql='SET @@PERSIST_ONLY.'+quote+' = DEFAULT'
                                    else:
                                        prefix='SELECT @@GLOBAL.' if '@@GLOBAL.' in text else 'SELECT @@SESSION.' if '@@SESSION.' in text else 'SELECT @@LOCAL.' if '@@LOCAL.' in text else 'SELECT @@'
                                        sql=prefix+quote
                                    q.execute(sql)
                                    if q.with_rows:q.fetchall()
                                    cases.append({'marked':marked,'native_sql':sql,'expected_apply':quote,'native_sql_accepted':True})
                                fixture['groups'].append({'use_pure':pure,'sql_mode':mode,'metadata':{**metadata,'resources':list(observed_vars.values())},'cases':cases})
                                work.execute('ROLLBACK TO SAVEPOINT variable_metadata_guard');work.execute('ROLLBACK')
                                try:work.execute('SELECT missing_variable_column FROM t')
                                except Exception as error:assert error.errno==1054
                                else:raise AssertionError('Owned native error was not raised')
                                before_error=commands();complete(client,handle);after_error=commands();assert before_error>0 and after_error==before_error
                                work.execute('SHOW ERRORS');assert any(row[1]==1054 for row in work.fetchall())
                                checks.append({'scope':'private-completion-'+(mode or 'default-mode'),'source_commands_sent':0,'native_statement_counters':[before,after],'native_error_area_statement_counters':[before_error,after_error],'row_count_preserved':True,'error_area_preserved':True,'pending_savepoint_preserved':True})
                            finally:work.close();client._forget_and_close(handle)
                        q.execute('SET GLOBAL sql_mode=%s',(initial_mode,));q.execute('SET SESSION sql_mode=%s',(initial_mode,))
                        q.execute('RESET PERSIST IF EXISTS `validate_password.length`')
                        proof['interfaces'].append({'use_pure':pure,'native_connection_class':cls,'checks':checks,'templates':templates,'source_variants':{k:sorted(v) for k,v in variants.items()}})
                    finally:client._forget_and_close(native);client.close()
                (output/'mysql-native-variable-fixture.json').write_text(json.dumps(fixture,indent=2)+'\n')
                proof['core_complete']=True
                if binary:
                    password='VariablesA1!'+secrets.token_urlsafe(24);q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    proof['browser']=workspace(output,route,password,binary,driver_binary)
                proof['complete']=True
            finally:q.close();oracle.close()
    finally:
        if owned_status is not None:proof['owned_server_stopped']=owned_status['owned_server_stopped']
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def workspace(output,route,password,binary,driver_binary):
    import uuid
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app=setup_application(output)
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    with app.test_request_context('/'):
        uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
        item=Server(user_id=uid,servergroup_id=group.id,name='Owned native variables',host=route['host'],port=route['port'],username='root',maintenance_db='sr_workspace',save_password=0)
        item._cde_endpoint_registration=registration_profile('mysql-native')
        item._cde_endpoint_route_configuration={**route,'user':'root','database':'sr_workspace','use_pure':False,'credential_kinds':['database_password']}
        db.session.add(item);db.session.commit();sid=item.id;target=str(uuid.uuid4())
        db.session.add(EndpointDatabaseTarget(id=target,endpoint_id=item.endpoint_profile.id,display_name='sr_workspace',database='sr_workspace',configuration='{}',active=1));db.session.commit()
        verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=sid)
    client=app.test_client()
    with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
    assert client.post(verify,json={'password':password}).get_json()['success']
    return browser(app,output,sid,password,binary,driver_binary)


def browser(app,output,sid,password,binary,driver_binary):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,wait_for_tree_item,invoke_context_action,complete_endpoint_prompt
    from cdeadmin_sqlite_query_ui_gate import _set_query
    from cdeadmin_firebird_query_ui_gate import _query_editor
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1200'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,90,ignored_exceptions=(StaleElementReferenceException,));ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def owned(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        label=wait.until(owned).text;expand(wait,label,('Connectors','MySQL'))
        if complete_endpoint_prompt(driver,password,timeout=5):expand(wait,label,('Connectors','MySQL'))
        database=wait_for_tree_item(wait,'sr_workspace',('Connectors','MySQL',label));invoke_context_action(wait,driver,database,('Database workspace','Open MySQL SQL editor...'),handle_endpoint_prompt=False)
        complete_endpoint_prompt(driver,password,timeout=15)
        wait.until(lambda b:next((n for n in b.find_elements(By.TAG_NAME,'summary') if n.is_displayed() and n.text=='Source tools'),None)).click()
        checks=[]
        for marked,name,expected in [('SELECT @@GLOBAL.validate_password.le|','validate_password.length','SELECT @@GLOBAL.`validate_password.length`'),('SELECT @@SESSION.sql_m|','sql_mode','SELECT @@SESSION.`sql_mode`')]:
            source=marked.replace('|','');_set_query(driver,wait,source);editor=wait.until(_query_editor);editor.click();editor.send_keys(Keys.CONTROL,Keys.HOME)
            editor.send_keys(Keys.ARROW_RIGHT*marked.index('|'));editor.send_keys(Keys.CONTROL,' ')
            def choices(browser):
                rows=[n for n in browser.find_elements(By.CSS_SELECTOR,'.cm-tooltip-autocomplete li') if n.is_displayed()]
                return rows if any(n.find_element(By.CSS_SELECTOR,'.cm-completionLabel').text==name for n in rows) else None
            rows=wait.until(choices);wanted=next(i for i,n in enumerate(rows) if n.find_element(By.CSS_SELECTOR,'.cm-completionLabel').text==name)
            selected=next((i for i,n in enumerate(rows) if n.get_attribute('aria-selected')=='true'),-1);steps=wanted+1 if selected<0 else (wanted-selected)%len(rows)
            if steps:editor.send_keys(Keys.ARROW_DOWN*steps)
            editor.send_keys(Keys.ENTER)
            actual=driver.execute_script('return [...arguments[0].querySelectorAll(".cm-line")].map(n=>n.textContent).join("\\n");',editor);assert actual==expected,(actual,expected)
            def check(browser):
                for n in browser.find_elements(By.TAG_NAME,'button'):
                    if n.text=='Check source' and n.is_displayed() and n.is_enabled():n.click();return True
                return False
            wait.until(check);wait.until(lambda b:any('SQL grammar: accepted by the reported parser.' in n.text for n in b.find_elements(By.CSS_SELECTOR,'[role="status"]')))
            checks.append({'native_variable':name,'inserted_source':actual,'native_grammar_accepted':True})
        driver.save_screenshot(str(output/'native-variable-completion.png'))
        errors=[r for r in driver.get_log('browser') if r['level']=='SEVERE'];assert not errors,errors
        return {'complete':True,'checks':checks,'version':driver.capabilities['browserVersion'],'console_errors':errors}
    except Exception:
        if driver:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();thread.join(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--library');parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();value=qualify(args.output,args.library,args.browser_binary,args.driver_binary);print(json.dumps({'complete':value['complete'],'interfaces':len(value['interfaces'])}))
