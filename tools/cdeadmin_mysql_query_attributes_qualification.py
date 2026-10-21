"""Owned native per-query attributes, NULL metadata and source charset changes."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time
from types import SimpleNamespace
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output, use_c=False, application=False, browser_binary=None, driver_binary=None):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,_create_client
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep native evidence outside source')
    output.mkdir(parents=True,exist_ok=False)
    paths=['tools/cdeadmin_mysql_query_attributes_qualification.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_query_attributes.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_values.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_execution.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
        'web/pgadmin/cdeadmin/providers/native_editor.py',
        'web/pgadmin/cdeadmin/data_studio/scripts.py','web/pgadmin/cdeadmin/workspace/service.py',
        'web/pgadmin/browser/server_groups/servers/__init__.py']
    proof={'complete':False,'history_testing':'not run','full_product_complete':False,'use_c':use_c,'checks':[],
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    try:
        with server(output/'fixture') as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;query=oracle.cursor()
            try:
                query.execute("INSTALL COMPONENT 'file://component_query_attributes'")
                query.execute('CREATE DATABASE sr_attributes CHARACTER SET utf8mb4')
                query.execute('CREATE TABLE sr_attributes.t(id INT PRIMARY KEY,value INT)')
                query.execute('INSERT INTO sr_attributes.t VALUES(1,1),(2,1)')
                selected={**route,'database':'sr_attributes','use_pure':not use_c,'autocommit':True}
                client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                handle=client.open_session({'route':selected})
                try:
                    proof['native_connection_class']=type(handle).__name__
                    assert proof['native_connection_class']==('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')
                    handle.query_attrs_append(('previous_marker','original client state'))
                    original=list(handle.query_attrs)
                    def execute(source,attributes=None,parameters=None,expected_error=None):
                        token=client.execute(handle,{'source':source,'parameters':parameters or {},
                            'output_policy':{'mysql_query_attributes':attributes or {}}})
                        rows=[];deadline=time.monotonic()+30;last=None
                        while time.monotonic()<deadline:
                            last=client._executions.describe(token);rows.extend(last['payload'].get('rows') or [])
                            if last['complete']:break
                        else:raise TimeoutError('Native attribute execution did not terminate')
                        error=last['payload'].get('error')
                        if expected_error is None:assert not error,last
                        else:assert error and error.get('errno')==expected_error,last
                        assert not last['payload']['session_reuse_blocked'] and handle.query_attrs==original
                        return rows
                    sample={'label':'é €','null':None,'integer':{'encoding':'integer','data':'9007199254740993'},
                        'decimal':{'encoding':'decimal','data':'1.2300'},'binary':{'encoding':'base64','data':base64.b64encode(b"x '\\").decode()},
                        'day':{'encoding':'date','data':'2026-10-21'},'stamp':{'encoding':'datetime','data':'2026-10-21 12:34:56.123456'},
                        'duration':{'encoding':'time','data':'-25:00:00.123400'}}
                    scalar="SELECT mysql_query_attribute_string('label'),mysql_query_attribute_string('null') IS NULL,mysql_query_attribute_string('integer'),mysql_query_attribute_string('decimal'),HEX(mysql_query_attribute_string('binary')),mysql_query_attribute_string('day'),mysql_query_attribute_string('stamp')"
                    expected=[('é €',1,'9007199254740993','1.2300','7820275C','2026-10-21','2026-10-21 12:34:56.123456')]
                    if use_c:
                        from pgadmin.cdeadmin.providers.mysql_family.mysql_query_attributes import Scope,decoded,AttributeAdmissionError
                        refused=Scope(handle,decoded({'duration':sample.pop('duration')}))
                        try:refused.install()
                        except AttributeAdmissionError:pass
                        else:raise AssertionError('Unsafe native C TIME duration must not dispatch')
                        assert handle.query_attrs==original
                        proof['native_driver_gaps']=['TIME durations read with datetime.time layout','unsigned integers above signed64 use a signed conversion','attribute names always use UTF8 even when source charset differs']
                    else:
                        scalar+=",mysql_query_attribute_string('duration')";expected=[expected[0]+('-25:00:00.123400',)]
                    for charset in ('utf8mb4','latin1'):
                        execute('SET NAMES '+charset)
                        actual=execute(scalar,sample);assert actual==expected,(charset,actual,expected)
                        assert execute("SELECT mysql_query_attribute_string('only_null') IS NULL",{'only_null':None})==[(1,)]
                        if use_c and charset=='latin1':
                            refused=Scope(handle,{'clé €':'named é €'});refused.install()
                            try:refused.bind()
                            except AttributeAdmissionError:pass
                            else:raise AssertionError('C native names must not silently use UTF8 in latin1')
                            finally:refused.restore()
                            assert handle.query_attrs==original
                        else:
                            named=execute('SELECT mysql_query_attribute_string(%s)',{'clé €':'named é €'},['clé €'])
                            assert named==[('named é €',)],(charset,named)
                    assert execute("SET NAMES utf8mb4; SELECT mysql_query_attribute_string('label'); SET NAMES latin1; SELECT mysql_query_attribute_string('label'); SET NAMES utf8mb4",{'label':'é €'})==[('é €',),('é €',)]
                    if not use_c:
                        assert execute("SELECT mysql_query_attribute_string('maximum'),mysql_query_attribute_string('minimum')",
                            {'maximum':{'encoding':'integer','data':'18446744073709551615'},'minimum':{'encoding':'integer','data':'-9223372036854775808'}})==[('18446744073709551615','-9223372036854775808')]
                    proof['checks'].append('native-NULL-and-exact-scalar-attributes-in-utf8mb4-and-latin1; Unicode-names-and-TIME-supported-by-pure; C-unsafe-native-values-refused-before-dispatch')
                    proof['checks'].append('one-execution-follows-actual-native-charset-switches-before-every-submitted-command-with-native-value-encoding')
                    execute('SELECT absent_column FROM t',{'label':'owned error'},expected_error=1054)
                    raw=handle.cursor();raw.execute('SHOW ERRORS');assert any(row[1]==1054 for row in raw.fetchall());raw.close()
                    raw=handle.cursor();raw.execute("SELECT mysql_query_attribute_string('previous_marker'),mysql_query_attribute_string('label')");assert raw.fetchone()==('original client state',None);raw.close()
                    proof['checks'].append('driver-attribute-state-and-original-native-error-area-restored-after-decoded-error-without-extra-source-settings-or-replay')
                    token=client.execute(handle,{'source':'SELECT SLEEP(10)','parameters':{},'output_policy':{'mysql_query_attributes':{'label':'cancelled query'}}})
                    deadline=time.monotonic()+15
                    while time.monotonic()<deadline:
                        query.execute('SELECT PROCESSLIST_STATE FROM performance_schema.threads WHERE PROCESSLIST_ID=%s',(handle.connection_id,))
                        if query.fetchone()==('User sleep',):break
                        time.sleep(.02)
                    else:raise TimeoutError('Native attribute cancellation target did not sleep')
                    assert client._executions.cancel(token)
                    while time.monotonic()<deadline:
                        page=client._executions.describe(token)
                        if page['complete']:break
                    else:raise TimeoutError('Native attribute cancellation did not drain')
                    assert handle.query_attrs==original and not page['payload']['session_reuse_blocked']
                    proof['checks'].append('actual-native-query-cancellation-drains-owned-protocol-and-restores-driver-attributes')
                    query.execute('SELECT COUNT(*),SUM(value) FROM sr_attributes.t');assert query.fetchone()==(2,2)
                finally:client._forget_and_close(handle);client.close()
                if application:
                    password='attributes-'+secrets.token_urlsafe(24)
                    query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    proof['application']=workspace(output,route,password,use_c,sample,scalar,browser_binary,driver_binary)
                proof['complete']=True
            finally:query.close();oracle.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def workspace(output, route, password, use_c, sample, scalar, browser_binary=None, driver_binary=None):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app=setup_application(output)
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    client=app.test_client()
    with app.test_request_context('/'):
        uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
        item=Server(user_id=uid,servergroup_id=group.id,name='Owned native attributes',host=route['host'],port=route['port'],username='root',maintenance_db='sr_attributes',save_password=0)
        item._cde_endpoint_registration=registration_profile('mysql-native')
        item._cde_endpoint_route_configuration={**route,'database':'sr_attributes','user':'root','autocommit':True,'use_pure':not use_c,'credential_kinds':['database_password']}
        db.session.add(item);db.session.commit();target=str(uuid.uuid4())
        db.session.add(EndpointDatabaseTarget(id=target,endpoint_id=item.endpoint_profile.id,display_name='sr_attributes',database='sr_attributes',configuration='{}',active=1));db.session.commit()
        url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id);verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id)
    with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
    assert client.post(verify,json={'password':password}).get_json()['success']
    def post(action,**data):
        response=client.post(url,json={'action':action,'database_target_id':target,**data});value=response.get_json()
        if response.status_code!=200 or not value.get('success'):
            (output/'application-failure.json').write_text(json.dumps(value,indent=2).replace(password,'<redacted>')+'\n')
            raise AssertionError('Native attribute application request failed: '+action)
        return value['data']
    session=post('open_session',language_profile='mysql-sql')['session_id']
    try:
        occurrence=post('execute',session_id=session,source=scalar,parameters=[],mysql_query_attributes=sample,history_sensitive=True)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            row=post('poll',occurrence_id=occurrence['occurrence_id'])['occurrence']
            if row['operation']['terminal']:break
        else:raise TimeoutError('Attribute application query did not finish')
        payload=row['result']['extensions']['mysql']['payload'];assert not payload.get('error') and payload['rows'][0][:4]==['é €',1,'9007199254740993','1.2300']
        catalog=post('source_complete',session_id=session,source='SELECT mysql_query_',source_before_cursor='SELECT mysql_query_')['editor_context']
        assert any(item['resource_kind']=='function' and item['display_path']==['mysql_query_attribute_string'] for item in catalog['resources'])
        marker='private-script-attribute-value'
        plan=post('native_script_prepare',session_id=session,source="SELECT mysql_query_attribute_string('label'); SELECT mysql_query_attribute_string('nil') IS NULL",mysql_query_attributes={'label':marker,'nil':None},history_sensitive=True)
        assert plan['state']=='ready' and marker not in json.dumps(plan)
        deadline=time.monotonic()+30
        while plan['state'] not in {'complete','stopped'}:
            if time.monotonic()>deadline:raise TimeoutError('Retained attribute script did not finish')
            plan=post('native_script_advance',plan_id=plan['plan_id'],revision=plan['revision'])
            assert marker not in json.dumps(plan)
        assert plan['state']=='complete' and len(plan['history'])==2
        post('native_script_discard',plan_id=plan['plan_id'])
        proof={'complete':True,'native_exact_attribute_rows_received':True,'runtime_component_function_completion_visible':True,
            'retained_script_complete':True,'attribute_values_excluded_from_public_plans':True}
        if browser_binary:proof['browser']=browser(app,output,item.id,password,browser_binary,driver_binary)
        return proof
    finally:post('close_session',session_id=session)


def browser(app,output,sid,password,binary,driver_binary):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,wait_for_tree_item,invoke_context_action,complete_endpoint_prompt,fill_fields
    from cdeadmin_sqlite_query_ui_gate import _set_query,_run_query
    http=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1200'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'))
        options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary))
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,90,ignored_exceptions=(StaleElementReferenceException,))
        ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def owned(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        label=wait.until(owned).text;expand(wait,label,('Connectors','MySQL'))
        if complete_endpoint_prompt(driver,password,timeout=5):expand(wait,label,('Connectors','MySQL'))
        database=wait_for_tree_item(wait,'sr_attributes',('Connectors','MySQL',label))
        invoke_context_action(wait,driver,database,('Database workspace','Open MySQL SQL editor...'),handle_endpoint_prompt=False)
        complete_endpoint_prompt(driver,password,timeout=15)
        def tab(label):
            node=wait.until(lambda browser:browser.find_element(By.XPATH,'//*[@role="tab" and normalize-space()="'+label+'"]'))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node);node.click()
        def click(label):
            node=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'button') if node.is_displayed() and node.is_enabled() and node.text==label),None))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node);node.click()
        tab('Engine options')
        marker='native attributes é €'
        fill_fields(wait,['MySQL query attributes (JSON object)='+json.dumps({'label':marker,'nil':None})])
        sensitive=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[contains(.,"Omit this sensitive source from SQL history")]'))
        if not sensitive.find_element(By.CSS_SELECTOR,'input').is_selected():sensitive.click()
        tab('Data Output')
        _run_query(driver,wait,"SELECT mysql_query_attribute_string('label') AS native_value,mysql_query_attribute_string('nil') IS NULL AS native_null",marker,'MySQL',output)
        summary=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'summary') if node.is_displayed() and node.text=='Source tools'),None));summary.click()
        _set_query(driver,wait,"SET NAMES latin1; SELECT mysql_query_attribute_string('label'); SET NAMES utf8mb4")
        click('Preview script')
        def progress(browser):
            return next((json.loads(node.text) for node in browser.find_elements(By.CSS_SELECTOR,'[aria-label="Script progress"]') if node.is_displayed() and node.text.startswith('{')),None)
        wait.until(lambda browser:(progress(browser) or {}).get('state')=='ready')
        assert marker not in json.dumps(progress(driver))
        click('Run / resume retained script')
        wait.until(lambda browser:(progress(browser) or {}).get('state')=='complete')
        final=progress(driver);assert len(final['history'])==3 and all(row['outcome']=='success' for row in final['history'])
        driver.save_screenshot(str(output/'native-query-attributes.png'))
        errors=[row for row in driver.get_log('browser') if row['level']=='SEVERE'];assert not errors,errors
        return {'complete':True,'version':driver.capabilities['browserVersion'],'checks':['native-editor-attribute-input-and-NULL-query-output','native-retained-script-attributes-across-latin1-and-utf8mb4'],'console_errors':errors}
    except Exception:
        if driver is not None:
            driver.save_screenshot(str(output/'browser-failure.png'))
            (output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();thread.join(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    parser.add_argument('--use-c',action='store_true');parser.add_argument('--application',action='store_true')
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();value=qualify(args.output,args.use_c,args.application,args.browser_binary,args.driver_binary)
    print(json.dumps({'complete':value['complete'],'checks':len(value['checks'])}))
