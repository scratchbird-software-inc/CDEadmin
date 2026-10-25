"""Built desktop primary routing and native certificate-account acceptance."""
import argparse
import json
from pathlib import Path
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,application,fixture,certificates,binary,driver_binary):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from pgadmin.model import User,Server
    from flask import url_for
    from pgadmin.cdeadmin.workspace import service_for_app
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException,ElementClickInterceptedException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action
    import mysql.connector
    output=Path(output).resolve();output.mkdir(exist_ok=False);prior=Path(application).resolve()
    owned=json.loads(Path(fixture).read_text());assert owned['complete'] and owned['network'].startswith('sr-upgrade246-')
    cert=json.loads(Path(certificates).read_text());app=setup_application(prior);client=app.test_client()
    with app.test_request_context('/'):
        uid=User.query.first().id
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
        servers=[Server.query.filter_by(user_id=uid,host=p['address']).one() for p in owned['peers']]
        registrations=[{'server_id':s.id,'name':s.name,'verify':url_for('NODE-server.verify_endpoint_id',gid=s.servergroup_id,sid=s.id)} for s in servers]
    with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
    for item in registrations:assert client.post(item['verify'],json={'password':'owned-upgrade-private'}).get_json()['success']
    def sql(source,parameters=()):
        connection=mysql.connector.connect(host=owned['peers'][0]['address'],port=3306,user='sr_upgrade',password='owned-upgrade-private',autocommit=True)
        cursor=connection.cursor(dictionary=True)
        try:cursor.execute(source,parameters);return cursor.fetchall() if cursor.with_rows else []
        finally:cursor.close();connection.close()
    primary=sql('SELECT @@server_uuid AS uuid')[0]['uuid']
    assert sql("SELECT MEMBER_ROLE AS role FROM performance_schema.replication_group_members WHERE MEMBER_ID=@@server_uuid")==[{'role':'PRIMARY'}]
    user='sr_cert_desktop';password='Owned-native-browser-private'
    sql('DROP USER IF EXISTS %s@%s',(user,'%'))
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    proof={'complete':False,'checks':[],'history_testing':'ScratchBird history not run'}
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1900,1500'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));wait=WebDriverWait(driver,150,ignored_exceptions=(StaleElementReferenceException,ElementClickInterceptedException))
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/');ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def target(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,registrations[1]['server_id'])),None)
        invoke_context_action(wait,driver,wait.until(target),('Availability','MySQL native topologies...'),handle_endpoint_prompt=False)
        driver.execute_script('''window.srSecurity=[];const send=XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send=function(body){let request;try{request=JSON.parse(body);}catch{}
if(request?.action?.startsWith('mysql_topology_'))this.addEventListener('load',()=>{let reply;try{reply=JSON.parse(this.responseText);}catch{}
window.srSecurity.push({action:request.action,execution_server_id:request.request?.execution_server_id,status:this.status,error:reply?.errormsg,data:reply?.data});});return send.apply(this,arguments);};''')
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
            node.click();node.send_keys(Keys.CONTROL,'a');node.send_keys(text or Keys.BACKSPACE)
            wait.until(lambda browser:node.get_attribute('value')==text)
        click('Load registered topology instances');click('Use execution registration '+registrations[0]['name'])
        click('Load native topology methods');click('Inspect topology seed')
        seed=wait.until(lambda browser:browser.find_elements(By.CSS_SELECTOR,'[aria-label="Native topology seed"]'))
        assert json.loads(seed[0].get_attribute('textContent'))['identity']['server_uuid']==primary
        selector=driver.find_element(By.XPATH,'//label[contains(text(),"Native topology method")]/following::*[@role="combobox"][1]')
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});',selector);selector.click()
        item=wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.get_attribute('textContent')=='cluster.setup_admin_account'),None))
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});',item);item.click()
        field('Native topology arguments',json.dumps([{'user':user,'host':'%'},{'requireCertIssuer':cert['issuer'],'requireCertSubject':cert['subject']}]))
        checkbox=driver.find_element(By.XPATH,'//label[contains(normalize-space(),"Set account password at dispatch")]//input');driver.execute_script('arguments[0].click()',checkbox)
        field('Native account password',password);field('Confirm topology seed UUID',primary)
        click('Review native topology change')
        reviewed=wait.until(lambda browser:browser.find_elements(By.CSS_SELECTOR,'[aria-label="Native topology review"]'))
        assert password not in reviewed[0].get_attribute('textContent')
        click('Confirm and start native topology change')
        def ended(browser):
            return next((item for item in reversed(browser.execute_script('return window.srSecurity'))
                if (item.get('data') or {}).get('options',{}).get('operation')=='cluster.setup_admin_account' and (item.get('data') or {}).get('native_operation_outcome')=='returned'),None)
        finished=wait.until(ended);value=finished['data']
        assert value['execution_registration']['server_id']==registrations[0]['server_id'] and value['target']['server_uuid']==primary
        assert value['result']['account_observation']['exists'] and value['native_process_termination_confirmed']
        assert driver.find_element(By.XPATH,'//label[contains(text(),"Native account password")]/following::input[1]').get_attribute('value')==''
        connection=mysql.connector.connect(host=owned['peers'][0]['address'],port=3306,user=user,password=password,
            ssl_ca=cert['ca'],ssl_cert=cert['certificate'],ssl_key=cert['key'],ssl_verify_cert=True,use_pure=False)
        try:
            cursor=connection.cursor();cursor.execute('SELECT CURRENT_USER()');assert cursor.fetchone()[0]==user+'@%';cursor.close()
        finally:connection.close()
        proof['checks'].append('built-desktop-secondary-origin-explicit-primary-review-confirmation-private-password-clearing-and-independent-native-certificate-login')
        click('Load native topology jobs')
        wait.until(lambda browser:browser.find_elements(By.CSS_SELECTOR,'[aria-label="Native topology jobs"]'))
        assert any(row['action']=='mysql_topology_list' and row['execution_server_id']==registrations[0]['server_id'] for row in driver.execute_script('return window.srSecurity'))
        proof['checks'].append('built-desktop-original-job-list-retains-explicit-execution-registration')
        driver.save_screenshot(str(output/'desktop.png'));proof['console_errors']=[item for item in driver.get_log('browser') if item['level']=='SEVERE']
        assert not proof['console_errors'],proof['console_errors']
        proof.update(complete=True,job_id=value['job_id'])
    except BaseException:
        if driver is not None:
            driver.save_screenshot(str(output/'failure.png'));(output/'browser.html').write_text(driver.page_source)
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();thread.join(timeout=5)
        jobs=getattr(service_for_app(app),'mysql_topology_jobs',None);proof['owned_jobs_stopped']=jobs.close() if jobs else True
        sql('DROP USER IF EXISTS %s@%s',(user,'%'))
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('output','application','fixture','certificates','browser-binary','driver-binary'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();result=qualify(args.output,args.application,args.fixture,args.certificates,args.browser_binary,args.driver_binary)
    print(json.dumps({'complete':result['complete'],'checks':len(result['checks'])}))
