"""Built desktop methods over an explicitly owned, running native Router."""
import json
import os
from pathlib import Path
import threading


def qualify(output,fixture,application_directory,sid,binary,driver_binary,mysql_shell):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);prior=Path(application_directory);owned=json.loads(Path(fixture).read_text());live=json.loads((prior/'metadata-live-setup.json').read_text())
    if not owned.get('complete') or not owned['network'].startswith('sr-router240-') or not live.get('desktop_fixture_only'):raise ValueError('Select the owned live native Router fixture')
    os.environ['CDEADMIN_MYSQLSH_BINARY']=str(Path(mysql_shell).resolve(strict=True))
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app=setup_application(prior);client=app.test_client()
    from flask import url_for
    from pgadmin.model import User,Server
    from pgadmin.cdeadmin.workspace import service_for_app
    with app.test_request_context('/'):
        uid=User.query.first().id;server=Server.query.filter_by(id=sid,user_id=uid).one();assert server.endpoint_profile.profile_id=='mysql-native'
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
        verify=url_for('NODE-server.verify_endpoint_id',gid=server.servergroup_id,sid=sid);url=url_for('NODE-server.cde_workspace_id',gid=server.servergroup_id,sid=sid)
    with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
    assert client.post(verify,json={'password':'true'}).get_json()['success']
    import mysql.connector
    oracle=mysql.connector.connect(host=owned['peers'][0]['host'],port=3306,user='root',password='true',autocommit=True)
    def sql(source,parameters=()):
        cursor=oracle.cursor(dictionary=True)
        try:cursor.execute(source,parameters);return cursor.fetchall()
        finally:cursor.close()
    def stop():
        credentials={'private_key':Path(owned['private_key']).read_text()}
        def post(action,request):
            reply=client.post(url,json={'action':'mysql_router_'+action,'request':request});assert reply.status_code==200,reply.get_json();return reply.get_json()['data']
        options={**live['started_options'],'operation':'service_stop','binding_job_id':live['started_job_id'],'disconnect_all_clients':True}
        review=post('review',{'options':options,'credentials':credentials});value=post('start',{'job_id':review['job_id'],'review_digest':review['review_digest'],'confirmed':True,'credentials':credentials})
        import time
        deadline=time.monotonic()+120
        while value['state'] in {'dispatching','active','cancel_requested'}:
            if time.monotonic()>deadline:raise TimeoutError('Owned desktop Router shutdown deadline')
            time.sleep(.1);value=post('status',{'job_id':value['job_id']})
        assert value['state']=='native_process_returned' and value['remote_receipt']['result']['return_code']==0
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException,ElementClickInterceptedException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None;stopped=False
    proof={'complete':False,'checks':[],'history_testing':'not run'}
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1900,1400'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));wait=WebDriverWait(driver,120,ignored_exceptions=(StaleElementReferenceException,ElementClickInterceptedException))
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/');ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def target(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        invoke_context_action(wait,driver,wait.until(target),('Availability','MySQL native topologies...'),handle_endpoint_prompt=False)
        driver.execute_script('''window.srRouterMethods=[];const send=XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send=function(body){let request;try{request=JSON.parse(body);}catch{}
if(request?.action?.startsWith('mysql_topology_'))this.addEventListener('load',()=>{let reply;try{reply=JSON.parse(this.responseText);}catch{}const data=reply?.data;
window.srRouterMethods.push({action:request.action,status:this.status,error:reply?.errormsg,method:data?.options?.operation,arguments:data?.options?.arguments_json,outcome:data?.native_operation_outcome,state:data?.state,job_id:data?.job_id,result:data?.result?.control?.result_json,native_error:data?.native_error});});return send.apply(this,arguments);};''')
        def click(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip()==label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
                        if node.is_displayed():node.click();return True
                return False
            wait.until(attempt)
        def field(prefix,text):
            tag=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'label') if node.get_attribute('textContent').startswith(prefix) and node.get_attribute('for')),None))
            node=driver.find_element(By.ID,tag.get_attribute('for'));driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
            node.send_keys(Keys.CONTROL,'a');node.send_keys(Keys.BACKSPACE);node.send_keys(text);wait.until(lambda browser:node.get_attribute('value')==text)
        click('Load native topology methods');click('Inspect topology seed');wait.until(lambda browser:browser.find_elements(By.CSS_SELECTOR,'[aria-label="Native topology seed"]'))
        completed_jobs=set()
        def method(name,arguments,read=False):
            selector=driver.find_element(By.XPATH,'//label[contains(text(),"Native topology method")]/following::*[@role="combobox"][1]');driver.execute_script('arguments[0].scrollIntoView({block:"center"});',selector);wait.until(lambda browser:(selector.click(),True)[1])
            option=wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.get_attribute('textContent')=='cluster.'+name),None));driver.execute_script('arguments[0].scrollIntoView({block:"center"});',option);option.click()
            field('Native topology arguments',json.dumps(arguments));before=driver.execute_script('return window.srRouterMethods.length')
            if read:click('Run native topology inspection')
            else:
                field('Confirm topology seed UUID',owned['peers'][0]['server_uuid']);click('Review native topology change');wait.until(lambda browser:browser.find_elements(By.CSS_SELECTOR,'[aria-label="Native topology review"]'));click('Confirm and start native topology change')
            def returned(browser):
                rows=browser.execute_script('return window.srRouterMethods.slice(arguments[0])',before)
                for row in rows:
                    if row.get('status',200)>=400:raise AssertionError(row.get('error'))
                    if row.get('job_id') not in completed_jobs and row.get('method')=='cluster.'+name and json.loads(row.get('arguments') or 'null')==arguments and row.get('state') not in {'reviewed','active','dispatching','cancel_requested'} and row.get('action')!='mysql_topology_review':
                        assert row['outcome']=='returned',row
                        return row
                return None
            value=wait.until(returned);completed_jobs.add(value['job_id']);(output/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n');print('Desktop native metadata method: '+name,flush=True)
            return json.loads(value['result'])
        assert live['native_router_label'] in method('list_routers',[],True)['routers']
        method('router_options',[{'router':live['native_router_label']}],True)
        method('set_router_option',[live['native_router_label'],'stats_updates_frequency',7])
        native=sql('SELECT CAST(options AS CHAR) AS value FROM mysql_innodb_cluster_metadata.routers WHERE router_id=%s',(live['router_id'],))[0]['value']
        assert json.loads(native)['stats_updates_frequency']==7
        method('set_router_option',[live['native_router_label'],'stats_updates_frequency',None])
        proof['checks'].append('built-desktop-live-Router-list-options-explicit-selected-native-set-reset-and-independent-row-verification')
        stop();stopped=True;method('remove_router_metadata',[live['native_router_label']])
        assert sql('SELECT COUNT(*) AS n FROM mysql_innodb_cluster_metadata.routers WHERE router_id=%s',(live['router_id'],))==[{'n':0}]
        assert live['native_router_label'] not in method('list_routers',[],True)['routers']
        proof['checks'].append('built-desktop-explicit-native-Router-metadata-removal-independent-absence-and-list-refresh')
        errors=[item for item in driver.get_log('browser') if item['level']=='SEVERE'];assert not errors,errors
        driver.save_screenshot(str(output/'desktop.png'));proof.update(complete=True,console_errors=errors,version=driver.capabilities['browserVersion'])
    except BaseException:
        if driver is not None:driver.save_screenshot(str(output/'failure.png'));(output/'failure.txt').write_text(driver.find_element(By.TAG_NAME,'body').get_attribute('textContent'))
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();thread.join(timeout=10)
        if not stopped:stop()
        oracle.close()
        service=service_for_app(app)
        for name in ('mysql_router_jobs','mysql_topology_jobs','mysql_binlog_replay_jobs'):
            jobs=getattr(service,name,None)
            if jobs is not None:jobs.close()
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof
