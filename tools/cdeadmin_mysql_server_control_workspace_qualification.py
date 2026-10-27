"""Authenticated API and built desktop requests to a supervised owned MySQL."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,binary=None,driver_binary=None):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep evidence outside source')
    output.mkdir(parents=True,exist_ok=False);app=setup_application(output)
    from cdeadmin_mysql_server_control_qualification import wait_state
    from mysql_qualification_support import server,_root_connection,_run,_wait_until_ready
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    paths=['tools/cdeadmin_mysql_server_control_workspace_qualification.py','tools/cdeadmin_mysql_server_control_qualification.py','tools/mysql_qualification_support.py','web/pgadmin/cdeadmin/context_menu.py']
    paths+=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_server_control.py','administration.py','provider.py','mysql_dialect_9_7_0.json')]
    proof={'complete':False,'application':[],'history_testing':'not run','source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    def recover(name,route,before,operation):
        if operation=='restart_server':
            wait_state(name,lambda row:row['RestartCount']>before['RestartCount'] and row['State']['Running'] and not row['State']['Restarting'] and row['State']['StartedAt']!=before['State']['StartedAt'])
        else:
            stopped=wait_state(name,lambda row:not row['State']['Running']);assert stopped['State']['ExitCode']==0
            _run(['docker','start',name])  # Qualification fixture recovery, not a product host-start assertion.
        _wait_until_ready('mysql',name,90)
    try:
        with server(output/'fixture',restartable=True,supervised_restart=True) as (route,name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor();password='control-ui-'+secrets.token_urlsafe(24)
            q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,));q.execute('SELECT @@server_uuid');uuid=q.fetchone()[0];q.close();oracle.close()
            # The fixture readiness helper expects its standard empty-password
            # root. Restore that account only in this private test fixture and
            # use a separate passworded native administrator for the application.
            import mysql.connector
            oracle=mysql.connector.connect(host=route['host'],port=route['port'],user='root',password=password);oracle.autocommit=True;q=oracle.cursor()
            q.execute('CREATE USER control_operator IDENTIFIED BY %s',(password,));q.execute('GRANT ALL ON *.* TO control_operator WITH GRANT OPTION');q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',('',));q.close();oracle.close()
            target={'resource_id':'server:MySQL','resource_kind':'server','display_name':'MySQL','display_path':['MySQL'],'native':{'server_uuid':uuid}}
            client=app.test_client();browser_sid=None
            for pure in (True,False):
                with app.test_request_context('/'):
                    uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
                    item=Server(user_id=uid,servergroup_id=group.id,name='Owned native control '+str(pure),host=route['host'],port=route['port'],username='control_operator',maintenance_db='mysql',save_password=0)
                    item._cde_endpoint_registration=registration_profile('mysql-native');item._cde_endpoint_route_configuration={**route,'user':'control_operator','use_pure':pure,'credential_kinds':['database_password']}
                    db.session.add(item);db.session.commit();url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id);verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id)
                    if not pure:browser_sid=item.id
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                assert client.post(verify,json={'password':password}).get_json()['success']
                def post(action,request):
                    response=client.post(url,json={'action':action,'request':request});value=response.get_json()
                    if response.status_code!=200 or not value.get('success'):
                        (output/'application-failure.json').write_text(json.dumps(value,indent=2).replace(password,'<redacted>')+'\n');raise AssertionError('Native control API failed: '+action)
                    return value['data']
                for operation in ('restart_server','shutdown_server'):
                    request={'resource_kind':'server','operation_id':operation,'target_resource':target,'draft':{'confirmation':'MySQL','disconnect_all_clients':True}}
                    checked=post('visual_admin_validate',request);assert checked['valid'],checked['errors']
                    plan=post('visual_admin_plan',request);assert plan['state']=='ready'
                    before=wait_state(name,lambda row:row['State']['Running'])
                    result=post('visual_admin_apply',{key:plan[key] for key in ('plan_id','plan_digest')}|{'confirmed':True})
                    assert result['provider_result']['server_control_observation']['native_acknowledged']
                    recover(name,route,before,operation)
                    proof['application'].append({'use_pure':pure,'operation':operation,'native_request_acknowledged':True,'separate_fixture_process_effect_observed':True})
            if binary:proof['browser']=browser(app,output,browser_sid,password,binary,driver_binary,name,route,recover,wait_state)
            proof['complete']=True
        proof['owned_server_stopped']=owned['owned_server_stopped'];proof['owned_container_removed']=owned['owned_container_removed']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def browser(app,output,sid,password,binary,driver_binary,name,route,recover,wait_state):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action,complete_endpoint_prompt,fill_fields
    from cdeadmin_firebird_ui_form_gate import close_workspace
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1200'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,90,ignored_exceptions=(StaleElementReferenceException,));ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def registered(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        def click(label):
            node=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'button') if node.is_displayed() and node.is_enabled() and node.text==label),None));driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
        checks=[]
        for operation,title in [('restart_server','Restart native MySQL server...'),('shutdown_server','Shut down native MySQL server...')]:
            node=wait.until(registered);invoke_context_action(wait,driver,node,('Maintenance',title),handle_endpoint_prompt=False);click('Continue');complete_endpoint_prompt(driver,password,timeout=15)
            fill_fields(wait,['Disconnect all clients on this native server=true','Exact server name=MySQL']);click('Validate and preview')
            wait.until(lambda browser:any('"state": "ready"' in node.text for node in browser.find_elements(By.CSS_SELECTOR,'[aria-label="Provider plan preview"]')))
            confirmation=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'label') if node.is_displayed() and 'I confirm this provider-planned operation.' in node.text),None));driver.execute_script('arguments[0].scrollIntoView({block:"center"});',confirmation);confirmation.click()
            before=wait_state(name,lambda row:row['State']['Running']);click('Apply provider plan')
            result=wait.until(lambda browser:next((json.loads(node.text) for node in browser.find_elements(By.CSS_SELECTOR,'[aria-label="Provider operation result"]') if node.is_displayed() and 'server_control_observation' in node.text),None))
            assert result['server_control_observation']['native_acknowledged'];recover(name,route,before,operation)
            checks.append({'operation':operation,'native_request_acknowledged':True,'separate_fixture_process_effect_observed':True})
            driver.save_screenshot(str(output/'native-server-control.png'));close_workspace(driver,wait)
        errors=[row for row in driver.get_log('browser') if row['level']=='SEVERE'];assert not errors,errors
        return {'complete':True,'checks':checks,'version':driver.capabilities['browserVersion'],'console_errors':errors}
    except Exception:
        if driver:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();thread.join(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();value=qualify(args.output,args.browser_binary,args.driver_binary);print(json.dumps({'complete':value['complete'],'application_checks':len(value['application'])}))
