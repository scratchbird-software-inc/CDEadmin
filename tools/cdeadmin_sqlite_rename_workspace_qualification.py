"""Qualify native SQLite rename generation/review through HTTP and the browser."""
import argparse
import builtins
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import threading
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,*,binary=None,driver_binary=None):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700);builtins.SERVER_MODE=None
    proof={'complete':False,'checks':[],'history_testing':'not run','source_sha256':{}}
    for path in [*list((ROOT/'web/pgadmin/cdeadmin/workspace').glob('sqlite*.py')),
                 ROOT/'web/pgadmin/cdeadmin/workspace/service.py',ROOT/'web/pgadmin/browser/server_groups/servers/__init__.py',
                 ROOT/'web/pgadmin/static/js/Dialogs/SQLiteCatalog.jsx',ROOT/'web/pgadmin/static/js/Dialogs/ProviderWorkspaceContent.jsx',Path(__file__)]:
        proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False;config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    config.DATA_DIR=str(output/'app');config.SQLITE_PATH=str(output/'app/application.db');config.SESSION_DB_PATH=str(output/'app/sessions')
    config.STORAGE_DIR=str(output/'app/storage');config.LOG_FILE=str(output/'app/application.log');config.AZURE_CREDENTIAL_CACHE_DIR=str(output/'app/azure')
    config.CDEADMIN_OPERATION_STORE_PATH=str(output/'app/operations.json')
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from flask import url_for
    path=output/'native.sqlite';connection=sqlite3.connect(path)
    try:
        assert sqlite3.sqlite_version=='3.53.0'
        connection.executescript('CREATE TABLE parent(id INTEGER PRIMARY KEY,note TEXT UNIQUE); '
            'CREATE TABLE child(id INTEGER PRIMARY KEY,parent_id INTEGER REFERENCES parent(id)); '
            'CREATE VIEW projection AS SELECT id,note FROM parent; '
            "INSERT INTO parent VALUES(9007199254740993,'雪'); INSERT INTO child VALUES(1,9007199254740993);")
        connection.commit()
    finally:connection.close()
    app=create_app('ScratchRobin-native-sqlite-rename');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY='';app.run_before_app_start()
    client=app.test_client()
    try:
        with app.test_request_context('/'):
            user=User.query.first();uid=user.id;group=ServerGroup.query.filter_by(user_id=uid).first()
            app.blueprints['NODE-engine_type'].connector_visibility['sqlite'].set(True,user_id=uid)
            server=Server(user_id=uid,servergroup_id=group.id,name='Owned SQLite rename target',host=None,port=1,username='',maintenance_db=str(path),save_password=0)
            server._cde_endpoint_registration=registration_profile('sqlite-native')
            server._cde_endpoint_route_configuration={'database':str(path),'filesystem_root':str(output),'database_create_root':str(output),'timeout':.1}
            db.session.add(server);db.session.commit();sid=server.id
            db.session.add(EndpointDatabaseTarget(id=str(uuid.uuid4()),endpoint_id=server.endpoint_profile.id,
                display_name=path.name,database=str(path),configuration='{}',active=1));db.session.commit()
            verify_url=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=sid);url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=sid)
        with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
        verified=client.post(verify_url,json={}).get_json();assert verified.get('success'),verified
        with app.test_request_context('/'):
            server=db.session.get(Server,sid);targets=EndpointDatabaseTarget.query.filter_by(endpoint_id=server.endpoint_profile.id,active=1).all()
            assert len(targets)==1;target=targets[0].id;target_label=targets[0].display_name
        def post(action,request,*,refused=False):
            response=client.post(url,json={'action':action,'request':{'database_target_id':target,**request}});value=response.get_json()
            if refused:assert response.status_code==400,value;return value
            if response.status_code!=200 or not value.get('success'):
                (output/'http-failure.json').write_text(json.dumps(value,indent=2)+'\n');raise RuntimeError('Native SQLite HTTP '+action+' failed')
            return value['data']
        captured=post('sqlite_catalog_export',{'include_system':False});baseline=json.dumps(captured['snapshot'])
        renames=[{'kind':'table','table':'parent','to':'renamed:雪'},{'kind':'column','table':'renamed:雪','from':'note','to':'body:雪'}]
        generated=post('sqlite_schema_rename_design',{'baseline':baseline,'renames':renames})
        connection=sqlite3.connect(path)
        try:assert connection.execute('SELECT * FROM projection').fetchall()==[(9007199254740993,'雪')]
        finally:connection.close()
        request={'baseline':baseline,'desired':json.dumps(generated['snapshot']),'renames':renames}
        displayed=post('sqlite_schema_plan',request);assert displayed['ready_for_review'],displayed
        reviewed=post('sqlite_schema_review',{**request,'execution_sha256':displayed['execution_sha256']})
        apply_request={**{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True}
        result=post('sqlite_schema_apply',apply_request);assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
        assert post('sqlite_schema_apply',apply_request)==result
        connection=sqlite3.connect(path)
        try:
            assert connection.execute('SELECT * FROM "renamed:雪"').fetchall()==[(9007199254740993,'雪')]
            assert connection.execute('SELECT * FROM projection').fetchall()==[(9007199254740993,'雪')]
            assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
        finally:connection.close()
        proof['checks'].append('authenticated-native-ddn-generation-preview-review-once-only-apply-and-independent-rows')
        assert post('sqlite_schema_receipt',{'review_id':reviewed['review_id']})['state']=='committed'
        proof['checks'].append('authenticated-durable-native-rename-receipt')
        if binary:
            proof['browser']=browser(app,output,path,sid,target_label,binary,driver_binary)
            connection=sqlite3.connect(path)
            try:
                assert connection.execute('SELECT * FROM "browser:雪"').fetchall()==[(9007199254740993,'雪')]
                assert connection.execute('SELECT * FROM projection').fetchall()==[(9007199254740993,'雪')]
                assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
            finally:connection.close()
            proof['checks'].append('browser-context-menu-native-rename-generation-confirmed-apply-and-independent-rows')
        proof.update(complete=True,native_sqlite_version=sqlite3.sqlite_version)
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def browser(app,output,path,sid,target_label,binary,driver_binary):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,wait_for_tree_item,invoke_context_action
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1200'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,90);ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'SQLite')
        def owned_server(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        server_label=wait.until(owned_server).text
        expand(wait,server_label,('Connectors','SQLite'))
        database=wait_for_tree_item(wait,target_label,('Connectors','SQLite',server_label))
        invoke_context_action(wait,driver,database,('Database workspace','SQLite metadata and DDN diagrams...'),handle_endpoint_prompt=False)
        def click(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip()==label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node)
                        if node.is_displayed():node.click();return True
                return False
            wait.until(attempt)
        def select(label,text):
            node=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[normalize-space()="'+label+'"]'));control=driver.find_element(By.ID,node.get_attribute('for'))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',control);control.click()
            wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.text==text),None)).click()
        click('Capture metadata')
        summary=wait.until(lambda browser:browser.find_element(By.XPATH,'//summary[normalize-space()="Native table and column renames"]'));driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',summary);summary.click()
        select('Native rename table','renamed:雪')
        node=driver.find_element(By.XPATH,'//label[normalize-space()="New native name"]');field=driver.find_element(By.ID,node.get_attribute('for'));field.send_keys('browser:雪')
        click('Generate native rename design');wait.until(lambda browser:'The generated rename intent is included' in browser.find_element(By.TAG_NAME,'body').text)
        click('Preview native changes');click('Prepare native change review')
        checkbox=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[contains(.,"Confirm this reviewed SQLite change")]//input'));driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',checkbox);checkbox.click()
        click('Apply reviewed change');wait.until(lambda browser:any('committed' in node.text for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        driver.save_screenshot(str(output/'native-sqlite-rename.png'));errors=[row for row in driver.get_log('browser') if row.get('level')=='SEVERE']
        (output/'browser-console.json').write_text(json.dumps(errors,indent=2)+'\n');assert not errors
        return {'complete':True,'console_errors':0}
    except Exception:
        if driver is not None:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True);parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');args=parser.parse_args()
    qualify(args.evidence,binary=args.browser_binary,driver_binary=args.driver_binary)
