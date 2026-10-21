"""Built desktop native named MyISAM cache workflows against an owned fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,binary,driver_binary):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep UI evidence outside source')
    output.mkdir(parents=True,exist_ok=False);app=setup_application(output)
    from mysql_qualification_support import server,_root_connection
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,complete_endpoint_prompt,fill_fields,invoke_context_action
    from cdeadmin_firebird_ui_form_gate import close_workspace
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_key_cache_lifecycle.py','administration.py','provider.py','mysql_dialect_9_7_0.json','mysql_charsets.py','mysql_warnings.py')]
    paths+=['web/pgadmin/cdeadmin/context_menu.py','tools/cdeadmin_mysql_key_cache_lifecycle_ui_qualification.py']
    proof={'complete':False,'checks':[],'history_testing':'not run',
        'source_sha256':{path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in paths}}
    driver=http=None;thread=None
    try:
        with server(output/'fixture') as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;query=oracle.cursor()
            try:
                password='instance-ui-'+secrets.token_urlsafe(24)
                query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                with app.test_request_context('/'):
                    uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
                    item=Server(user_id=uid,servergroup_id=group.id,name='Owned native key-cache UI',host=route['host'],port=route['port'],username='root',maintenance_db='mysql',save_password=0)
                    item._cde_endpoint_registration=registration_profile('mysql-native')
                    item._cde_endpoint_route_configuration={**route,'user':'root','use_pure':False,'credential_kinds':['database_password']}
                    db.session.add(item);db.session.commit();sid=item.id
                    verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=sid)
                client=app.test_client()
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                assert client.post(verify,json={'password':password}).get_json()['success']
                http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
                options=webdriver.ChromeOptions();options.binary_location=binary
                for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1200'):options.add_argument(flag)
                options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
                driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
                wait=WebDriverWait(driver,90,ignored_exceptions=(StaleElementReferenceException,))
                ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
                def registered(browser):
                    return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script(
                        'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
                def click(label):
                    node=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'button') if node.is_displayed() and node.is_enabled() and node.text==label),None))
                    driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
                for operation,title in (('configure_key_cache','Configure MyISAM key cache...'),('inspect_key_cache','Inspect named MyISAM key cache...'),('release_key_cache','Release named MyISAM key cache...')):
                    node=wait.until(registered)
                    invoke_context_action(wait,driver,node,('Maintenance',title),handle_endpoint_prompt=False)
                    if operation!='inspect_key_cache':click('Continue')
                    complete_endpoint_prompt(driver,password,timeout=15)
                    fill_fields(wait,['Exact native key-cache name=ui_native_cache']+(['Exact server name=MySQL'] if operation!='inspect_key_cache' else []))
                    click('Validate and preview')
                    wait.until(lambda browser:any('"state": "ready"' in node.text for node in browser.find_elements(By.CSS_SELECTOR,'[aria-label="Provider plan preview"]')))
                    if operation!='inspect_key_cache':
                        confirmation=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'label') if node.is_displayed() and 'I confirm this provider-planned operation.' in node.text),None))
                        driver.execute_script('arguments[0].scrollIntoView({block:"center"});',confirmation);confirmation.click()
                    click('Apply provider plan')
                    result=wait.until(lambda browser:next((json.loads(node.text) for node in browser.find_elements(By.CSS_SELECTOR,'[aria-label="Provider operation result"]') if node.is_displayed() and 'key_cache_observation' in node.text),None))
                    assert result['accepted'] and result['key_cache_observation']['native_acknowledged'] and result['key_cache_observation']['operation']==operation
                    proof['checks'].append({'operation':operation,'reviewed_and_confirmed':True,'actual_native_acknowledged':True})
                    wait.until(lambda browser:any(node.is_displayed() and node.is_enabled() and node.text=='Validate and preview' for node in browser.find_elements(By.TAG_NAME,'button')))
                    driver.save_screenshot(str(output/'native-key-cache-lifecycle.png'));close_workspace(driver,wait)
                proof['console_errors']=[row for row in driver.get_log('browser') if row['level']=='SEVERE'];assert not proof['console_errors']
                proof.update(complete=True,browser_version=driver.capabilities['browserVersion'])
            except Exception:
                if driver:
                    driver.save_screenshot(str(output/'browser-failure.png'))
                    (output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
                raise
            finally:
                if driver:driver.quit();driver=None
                if http:http.shutdown();thread.join(timeout=10);http=None
                query.close();oracle.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
    finally:
        if driver:driver.quit()
        if http:http.shutdown();thread.join(timeout=10)
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    parser.add_argument('--browser-binary',required=True);parser.add_argument('--driver-binary',required=True)
    args=parser.parse_args();value=qualify(args.output,args.browser_binary,args.driver_binary)
    print(json.dumps({'complete':value['complete'],'checks':len(value['checks'])}))
