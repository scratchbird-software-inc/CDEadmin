"""Built desktop MyISAM cache forms against an owned native MySQL9.7 server."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import threading
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output, binary, driver_binary):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep UI qualification outside source')
    output.mkdir(parents=True,exist_ok=False);app=setup_application(output)
    from mysql_qualification_support import server,_root_connection
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,complete_endpoint_prompt,fill_fields,invoke_context_action,wait_for_tree_item
    from cdeadmin_firebird_ui_form_gate import close_workspace
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/mysql_key_cache.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/administration.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json',
        'tools/cdeadmin_mysql_key_cache_ui_qualification.py']
    proof={'complete':False,'history_testing':'not run','checks':[],
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    driver=http=None;thread=None
    try:
        with server(output/'fixture') as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;query=oracle.cursor()
            try:
                password='cache-ui-'+secrets.token_urlsafe(24)
                query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                query.execute('CREATE DATABASE sr_cache')
                query.execute('CREATE TABLE sr_cache.ui_cache(id INT PRIMARY KEY,value INT,KEY(value)) ENGINE=MyISAM')
                query.executemany('INSERT INTO sr_cache.ui_cache VALUES(%s,%s)',[(i,i*10) for i in range(200)])
                with app.test_request_context('/'):
                    uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
                    item=Server(user_id=uid,servergroup_id=group.id,name='Owned MyISAM UI',host=route['host'],port=route['port'],username='root',maintenance_db='sr_cache',save_password=0)
                    item._cde_endpoint_registration=registration_profile('mysql-native')
                    item._cde_endpoint_route_configuration={**route,'database':'sr_cache','user':'root','use_pure':False,'credential_kinds':['database_password']}
                    db.session.add(item);db.session.commit();target=str(uuid.uuid4())
                    db.session.add(EndpointDatabaseTarget(id=target,endpoint_id=item.endpoint_profile.id,display_name='sr_cache',database='sr_cache',configuration='{}',active=1));db.session.commit()
                    verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id)
                    sid=item.id
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
                def registered(d):
                    return next((node for node in d.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and d.execute_script(
                        'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
                node=wait.until(registered)
                label=node.text;parents=('Connectors','MySQL',label,'sr_cache')
                expand(wait,label,('Connectors','MySQL'))
                if complete_endpoint_prompt(driver,password,timeout=5):expand(wait,label,('Connectors','MySQL'))
                expand(wait,'sr_cache',parents[:-1])
                if complete_endpoint_prompt(driver,password,timeout=5):expand(wait,'sr_cache',parents[:-1])
                expand(wait,'Tables',parents)
                def click(label):
                    node=wait.until(lambda d:next((n for n in d.find_elements(By.TAG_NAME,'button') if n.is_displayed() and n.is_enabled() and n.text==label),None))
                    driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
                for operation in ('assign_index_cache','preload_index_cache'):
                    node=wait_for_tree_item(wait,'ui_cache',(*parents,'Tables'))
                    title='Assign MyISAM index cache...' if operation=='assign_index_cache' else 'Preload MyISAM indexes...'
                    invoke_context_action(wait,driver,node,('Object operations',title),handle_endpoint_prompt=False)
                    click('Continue')
                    fill_fields(wait,['Exact table name=ui_cache'])
                    click('Validate and preview')
                    wait.until(lambda d:any('"state": "ready"' in n.text for n in d.find_elements(By.CSS_SELECTOR,'[aria-label="Provider plan preview"]')))
                    confirmation=wait.until(lambda d:next((n for n in d.find_elements(By.TAG_NAME,'label') if n.is_displayed() and 'I confirm this provider-planned operation.' in n.text),None))
                    driver.execute_script('arguments[0].scrollIntoView({block:"center"});',confirmation);confirmation.click();click('Apply provider plan')
                    native_op='assign_to_keycache' if operation=='assign_index_cache' else 'preload_keys'
                    result=wait.until(lambda d:next((json.loads(n.text) for n in d.find_elements(By.CSS_SELECTOR,'[aria-label="Provider operation result"]') if n.is_displayed() and 'index_cache_observation' in n.text and '"op": "'+native_op+'"' in n.text),None))
                    assert result['index_cache_observation']['native_effect_acknowledged'] and result['accepted'],result
                    proof['checks'].append({'operation':operation,'actual_native_effect_acknowledged':True,'reviewed_and_confirmed':True})
                    wait.until(lambda d:any(node.is_displayed() and node.is_enabled() and node.text=='Validate and preview'
                        for node in d.find_elements(By.TAG_NAME,'button')))
                    driver.save_screenshot(str(output/'native-cache-forms.png'))
                    close_workspace(driver,wait)
                query.execute('SELECT COUNT(*),SUM(value) FROM sr_cache.ui_cache');assert query.fetchone()==(200,199000)
                proof['console_errors']=[row for row in driver.get_log('browser') if row['level']=='SEVERE'];assert not proof['console_errors']
                proof.update(complete=True,browser_version=driver.capabilities['browserVersion'])
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
