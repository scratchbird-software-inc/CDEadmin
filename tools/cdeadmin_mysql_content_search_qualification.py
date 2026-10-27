"""MySQL 9.7 native content-search, private observers and desktop evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def register(app,route,password,use_c,user='root'):
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    with app.test_request_context('/'):
        owner=User.query.first();group=ServerGroup.query.filter_by(user_id=owner.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=owner.id)
        item=Server(user_id=owner.id,servergroup_id=group.id,name='Owned search '+user+' '+str(use_c),
            host=route['host'],port=route['port'],username=user,maintenance_db='sr_search',save_password=0)
        item._cde_endpoint_registration=registration_profile('mysql-native')
        item._cde_endpoint_route_configuration={**route,'database':'sr_search','user':user,'use_pure':not use_c,
            'autocommit':True,'sql_mode':'NO_BACKSLASH_ESCAPES','credential_kinds':['database_password']}
        db.session.add(item);db.session.commit()
        target=str(uuid.uuid4());db.session.add(EndpointDatabaseTarget(id=target,endpoint_id=item.endpoint_profile.id,
            display_name='sr_search',database='sr_search',configuration='{}',active=1));db.session.commit()
        sid,uid=item.id,owner.id
        endpoint=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=sid)
        verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=sid)
    client=app.test_client()
    with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(uid),True
    assert client.post(verify,json={'password':password}).get_json()['success']
    def post(operation,request):
        response=client.post(endpoint,json={'action':'mysql_content_search_'+operation,'request':request})
        data=response.get_json()
        assert response.status_code==200 and data.get('success'),data
        assert response.headers['Cache-Control']=='no-store'
        return data['data']
    return sid,post


def finish(post,job):
    deadline=time.monotonic()+25
    while not job['terminal'] and time.monotonic()<deadline:
        time.sleep(.03);job=post('status',{'job_id':job['job_id']})
    assert job['terminal'],job
    return job


def qualify(output,browser_binary=None,driver_binary=None):
    import config  # noqa: F401
    from types import SimpleNamespace
    from pgadmin.cdeadmin.security import SecretLease
    from pgadmin.cdeadmin.providers.mysql_family.mysql_content_search import Observer
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Native evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    paths=['tools/cdeadmin_mysql_content_search_qualification.py','web/pgadmin/cdeadmin/providers/mysql_family/mysql_content_search.py',
        'web/pgadmin/cdeadmin/workspace/mysql_content_search.py','web/pgadmin/cdeadmin/workspace/mysql_content_search_service.py',
        'web/pgadmin/static/js/Dialogs/MySQLContentSearch.jsx']
    proof={'complete':False,'history_testing':'not run','interfaces':[],
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    owned=None
    try:
        with server(output/'fixture') as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;cursor=oracle.cursor()
            try:
                cursor.execute('CREATE DATABASE sr_search CHARACTER SET utf8mb4')
                cursor.execute('USE sr_search')
                cursor.execute("SET SESSION sql_mode='NO_ENGINE_SUBSTITUTION'")
                cursor.execute('CREATE TABLE t(id BIGINT UNSIGNED PRIMARY KEY,note VARCHAR(100),n DECIMAL(65,0),'
                    'b VARBINARY(64),j JSON,d DATE,tm TIME(6),bits BIT(64),KEY(note),KEY(n),KEY(b))')
                huge='12345678901234567890123456789012345678901234567890123456789012345'
                cursor.execute('INSERT INTO t VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                    (18446744073709551615,'café %_! <img src=x> 雪',huge,b'\x00\xff%\x00','{"tag":"雪"}',
                     '0000-00-00','838:59:58.123456',18446744073709551615))
                cursor.execute("INSERT INTO t(id,note,n,b) VALUES(2,'ordinary',2,X'0102')")
                for key,end in ((3,'0'),(4,'1')):
                    cursor.execute('INSERT INTO t(id,note,n) VALUES(%s,%s,%s)',(key,'exact numeric neighbour',huge[:-1]+end))
                cursor.execute('CREATE TABLE `odd``雪`(id INT PRIMARY KEY,note VARCHAR(80))')
                cursor.execute("INSERT INTO `odd``雪` VALUES(1,'needle across tables')")
                cursor.execute('CREATE TABLE no_key(note VARCHAR(80))')
                cursor.execute("INSERT INTO no_key VALUES('needle without key')")
                cursor.execute('CREATE TABLE zero_key(d DATE PRIMARY KEY,note VARCHAR(80))')
                cursor.execute("INSERT INTO zero_key VALUES('0000-00-00','zero date identity')")
                cursor.execute('CREATE TABLE auto_key(id INT AUTO_INCREMENT PRIMARY KEY,note VARCHAR(80))')
                cursor.execute('CREATE TABLE binary_key(id VARBINARY(16) PRIMARY KEY,note VARCHAR(80))')
                cursor.execute("INSERT INTO binary_key VALUES(X'00ff2500','binary key identity')")
                cursor.execute('CREATE TABLE decimal_key(id DECIMAL(65,30) PRIMARY KEY,note VARCHAR(80))')
                cursor.execute("INSERT INTO decimal_key VALUES(0.000000000000000000000000000001,'fractional key identity')")
                password=secrets.token_urlsafe(24)
                cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                cursor.execute("CREATE USER 'search_limited'@'%' IDENTIFIED BY %s",(password,))
                cursor.execute("GRANT SELECT(note) ON sr_search.t TO 'search_limited'@'%'")
                app=setup_application(output)
                for use_c in (False,True):
                    sid,post=register(app,route,password,use_c);checks=[]
                    observer=Observer(SimpleNamespace(acquire_secret=lambda *_: SecretLease(password.encode('utf8'))),
                        {**route,'password':None,'database':'sr_search','use_pure':not use_c,
                         'credential_reference_id':'owned-search-secret','principal_reference':'owned-search-operator'})
                    try:
                        connection_class=type(observer.connection).__name__
                        assert connection_class==('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')
                    finally:observer.close()
                    catalog=post('tables',{'schema_name':'sr_search'})
                    assert {'t','odd`雪','no_key','zero_key','auto_key'}<={r['name'] for r in catalog['rows']}
                    descriptions={name:post('columns',{'schema_name':'sr_search','table_name':name}) for name in ('t','odd`雪','no_key','zero_key','auto_key','binary_key','decimal_key')}
                    def search(mode,value,choices,**options):
                        tables=[dict(table_name=t,
                            fingerprint=descriptions[t]['fingerprint'],columns=c) for t,c in choices]
                        return finish(post,post('start',{'schema_name':'sr_search','tables':tables,'confirmed':True,
                            'options':{'mode':mode,'value':value,**options}}))
                    text=search('text_contains','%_!',[('t',['note'])]);assert len(text['matches'])==1,text
                    match=text['matches'][0]
                    row=post('row',{'job_id':text['job_id'],'match_id':match['match_id']})
                    assert row['state']=='current-row' and next(c for c in row['values'] if c['column_name']=='id')['preview']=='18446744073709551615'
                    assert next(c for c in row['values'] if c['column_name']=='d')['preview']=='0000-00-00'
                    assert next(c for c in row['values'] if c['column_name']=='tm')['preview']=='838:59:58.123456',row
                    assert next(c for c in row['values'] if c['column_name']=='bits')['preview']=='18446744073709551615'
                    post('forget',{'job_id':text['job_id']})
                    for mode,value,cols in [('numeric_equal',huge,['n']),('numeric_equal',huge[:-1]+'0',['n']),('numeric_equal','18446744073709551615',['id']),
                        ('binary_exact','00ff2500',['b']),('binary_contains','ff25',['b']),('text_contains','雪',['j'])]:
                        result=search(mode,value,[('t',cols)]);assert len(result['matches'])==1,result
                        post('forget',{'job_id':result['job_id']})
                    checks.append('native-literal-unicode-numeric-binary-json-and-exact-key-navigation')
                    result=search('text_contains','needle',[('odd`雪',['note']),('no_key',['note'])])
                    assert len(result['matches'])==2 and any(not m['navigation_available'] for m in result['matches']),result
                    post('forget',{'job_id':result['job_id']})
                    result=search('text_exact','zero date identity',[('zero_key',['note'])])
                    assert post('row',{'job_id':result['job_id'],'match_id':result['matches'][0]['match_id']})['state']=='current-row'
                    post('forget',{'job_id':result['job_id']})
                    result=search('text_exact','binary key identity',[('binary_key',['note'])])
                    binary_row=post('row',{'job_id':result['job_id'],'match_id':result['matches'][0]['match_id']})
                    assert binary_row['state']=='current-row' and next(c for c in binary_row['values'] if c['column_name']=='id')['preview']=='00FF2500',binary_row
                    post('forget',{'job_id':result['job_id']})
                    result=search('numeric_equal','1e-30',[('decimal_key',['id'])])
                    decimal_row=post('row',{'job_id':result['job_id'],'match_id':result['matches'][0]['match_id']})
                    assert decimal_row['state']=='current-row' and next(c for c in decimal_row['values'] if c['column_name']=='id')['preview']=='0.000000000000000000000000000001',decimal_row
                    post('forget',{'job_id':result['job_id']})
                    indexed=search('text_prefix','café',[('t',['note'])],indexed_only=True)
                    assert len(indexed['matches'])==1,indexed;post('forget',{'job_id':indexed['job_id']})
                    skipped=search('text_contains','%_!',[('t',['note'])],indexed_only=True)
                    assert not skipped['matches'] and skipped['coverage'][0]['columns'][0]['state']=='unsearched',skipped
                    post('forget',{'job_id':skipped['job_id']})
                    checks.append('multi-table-native-identifiers-keyless-scope-and-native-index-plans')
                    cursor.execute("INSERT INTO auto_key(note) VALUES('stable source')")
                    stable=search('text_exact','stable source',[('auto_key',['note'])]);assert stable['matches'],stable
                    post('forget',{'job_id':stable['job_id']})
                    cursor.execute('ALTER TABLE auto_key ADD COLUMN added_by_native_ddl INT')
                    stale=search('text_exact','stable source',[('auto_key',['note'])])
                    assert stale['state']=='partial' and stale['coverage'][0]['state']=='unsearched' and not stale['matches'],stale
                    post('forget',{'job_id':stale['job_id']})
                    descriptions['auto_key']=post('columns',{'schema_name':'sr_search','table_name':'auto_key'})
                    bounded=search('text_contains','needle',[('odd`雪',['note']),('no_key',['note'])],limit=1)
                    assert bounded['state']=='bounded' and len(bounded['matches'])==1 and bounded['coverage'][1]['state']=='unsearched',bounded
                    post('forget',{'job_id':bounded['job_id']})
                    checks.append('native-DDL-stale-source-refusal-and-global-result-bound-coverage')
                    cursor.execute('SET autocommit=0');cursor.execute("INSERT INTO t(id,note) VALUES(9,'pending original')")
                    cursor.execute('SAVEPOINT search_guard');cursor.execute("SELECT CAST('original warning' AS UNSIGNED)");cursor.fetchall()
                    result=search('text_exact','pending original',[('t',['note'])]);assert not result['matches'] and result['state']=='completed',result
                    cursor.execute('SHOW WARNINGS');assert cursor.fetchall()
                    cursor.execute('ROLLBACK TO SAVEPOINT search_guard');cursor.execute('ROLLBACK');cursor.execute('SET autocommit=1')
                    post('forget',{'job_id':result['job_id']})
                    checks.append('stable-source-under-DML-and-independent-native-transaction-diagnostics')
                    for deadline in (False,True):
                        cursor.execute('LOCK TABLES t WRITE')
                        try:
                            job=post('start',{'schema_name':'sr_search','tables':[{'table_name':'t','fingerprint':descriptions['t']['fingerprint'],'columns':['note']}],
                                'confirmed':True,'options':{'mode':'text_contains','value':'café','seconds':1 if deadline else 30}})
                            time.sleep(.15)
                            if not deadline:job=post('cancel',{'job_id':job['job_id']})
                            job=finish(post,job)
                            assert job['state']==('bounded' if deadline else 'cancelled') and job['cancellation']['native_kill_sent'],job
                        finally:cursor.execute('UNLOCK TABLES')
                        post('forget',{'job_id':job['job_id']})
                    cursor.execute('SELECT 1');assert cursor.fetchone()[0]==1
                    checks.append('native-owned-thread-cancellation-and-wall-budget-with-unrelated-session-preserved')
                    denied_sid,limited=register(app,route,password,use_c,'search_limited')
                    limited_desc=limited('columns',{'schema_name':'sr_search','table_name':'t'})
                    denied=finish(limited,limited('start',{'schema_name':'sr_search','tables':[{'table_name':'t','fingerprint':limited_desc['fingerprint'],'columns':['id']}],
                        'confirmed':True,'options':{'mode':'numeric_equal','value':'2'}}))
                    assert denied['coverage'][0]['state']=='denied' and not denied['matches'],denied
                    limited('forget',{'job_id':denied['job_id']})
                    allowed=finish(limited,limited('start',{'schema_name':'sr_search','tables':[{'table_name':'t','fingerprint':limited_desc['fingerprint'],'columns':['note']}],
                        'confirmed':True,'options':{'mode':'text_contains','value':'%_!'}}))
                    assert allowed['matches'] and not allowed['matches'][0]['navigation_available'],allowed
                    limited('forget',{'job_id':allowed['job_id']})
                    checks.append('native-column-grants-and-denied-scope-are-not-zero-results')
                    proof['interfaces'].append({'complete':True,'use_c':use_c,'native_connection_class':connection_class,'checks':checks})
                    cursor.execute('ALTER TABLE auto_key DROP COLUMN added_by_native_ddl')
                if browser_binary:proof['browser']=browser(app,output,sid,password,browser_binary,driver_binary)
                proof['complete']=True
            finally:cursor.close();oracle.close()
    finally:
        proof['owned_server_stopped']=bool(owned and owned['owned_server_stopped'])
        proof['complete']=proof['complete'] and proof['owned_server_stopped']
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def browser(app,output,sid,password,binary,driver_binary):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action,complete_endpoint_prompt
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    driver=None
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
        invoke_context_action(wait,driver,wait.until(owned),('Diagnostics and verification','MySQL database content search...'),handle_endpoint_prompt=False)
        complete_endpoint_prompt(driver,password,timeout=10)
        def click(label):
            item=wait.until(lambda b:next((e for e in b.find_elements(By.TAG_NAME,'button') if e.is_displayed() and e.is_enabled() and e.text==label),None))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',item);item.click()
        def field(label):
            def ready(browser):
                item=browser.find_element(By.XPATH,'//label[contains(text(),"'+label+'")]/following-sibling::div/input')
                return item if item.is_displayed() and item.is_enabled() else None
            item=wait.until(ready);driver.execute_script('arguments[0].scrollIntoView({block:"center"});',item)
            return item
        field('Search database').send_keys('sr_search');click('Discover tables');click('t')
        checkbox=wait.until(lambda b:b.find_element(By.XPATH,'//label[contains(. ,"Allow private table-value search")]'))
        wait.until(lambda _b:checkbox.find_element(By.TAG_NAME,'input').is_enabled())
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});',checkbox);checkbox.click()
        wait.until(lambda _b:checkbox.find_element(By.TAG_NAME,'input').is_selected())
        field('Private search value').send_keys('%_!');click('Start native content search')
        click('Open current row')
        wait.until(lambda b:'18446744073709551615' in b.find_element(By.CSS_SELECTOR,'[aria-label="Current native search row"]').text)
        assert not driver.find_elements(By.CSS_SELECTOR,'[aria-label="MySQL database content search"] img')
        driver.save_screenshot(str(output/'native-content-search.png'));click('Clear private results')
        wait.until(lambda b:not b.find_elements(By.CSS_SELECTOR,'[aria-label="Native content matches"]'))
        errors=[r for r in driver.get_log('browser') if r['level']=='SEVERE'];assert not errors,errors
        return {'complete':True,'checks':['provider-menu-native-search','exact-key-row-navigation','escaped-preview','private-clear'],'console_errors':errors}
    except Exception:
        if driver:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();thread.join(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');args=parser.parse_args()
    qualify(args.output,args.browser_binary,args.driver_binary)
