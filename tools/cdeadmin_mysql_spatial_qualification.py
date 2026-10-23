"""Owned native MySQL spatial, source-byte and built desktop acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,browser_binary=None,driver_binary=None):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from cdeadmin_mysql_online_ddl_qualification import registration
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/mysql_spatial.py','web/pgadmin/cdeadmin/workspace/mysql_spatial_service.py',
        'web/pgadmin/static/js/Dialogs/MySQLSpatial.jsx','web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/mysqlSpatial.js',
        'web/pgadmin/static/vendor/ddn/current/resource-manifest.json',str(Path(__file__).relative_to(ROOT))]
    proof={'complete':False,'interfaces':[],'history_testing':'not run','source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    owned=None
    try:
        with server(output/'fixture') as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;cursor=oracle.cursor()
            try:
                password=secrets.token_urlsafe(24);cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                cursor.execute('CREATE DATABASE sr_osc');cursor.execute('USE sr_osc')
                cursor.execute('CREATE TABLE geo(id BIGINT UNSIGNED PRIMARY KEY,g GEOMETRY,b LONGBLOB)')
                cases=[(1,'POINT(1000000 -2000000)',0),(2,'POINT(43 -79)',4326),(3,'LINESTRING(-180 91,200 450)',0),
                    (4,'MULTIPOINT((1 2),(3 4))',0),(5,'POLYGON((0 0,10 0,10 10,0 10,0 0),(2 2,8 2,8 8,2 8,2 2))',0),
                    (6,'MULTIPOLYGON(((0 0,1 0,1 1,0 0)),((3 3,4 3,4 4,3 3)))',0),
                    (7,'MULTILINESTRING((0 0,1 1),(3 4,7 9))',0),(8,'GEOMETRYCOLLECTION(POINT(1 2),LINESTRING(0 0,1 2),POLYGON((0 0,1 0,1 1,0 0)))',0),
                    (10,'GEOMETRYCOLLECTION EMPTY',0),(11,'POLYGON((0 0,2 2,0 2,2 0,0 0))',0),(13,'POINT(1e150 1e150)',0)]
                for identity,wkt,srid in cases:cursor.execute('INSERT INTO geo(id,g) VALUES(%s,ST_GeomFromText(%s,%s))',(identity,wkt,srid))
                cursor.execute('INSERT INTO geo(id,g) VALUES(9,NULL),(12,ST_Transform(ST_GeomFromText(\'POINT(43 -79)\',4326),3857))')
                cursor.execute("UPDATE geo SET b=ST_AsWKB(g,'axis-order=long-lat')")
                cursor.execute('UPDATE geo SET b=ST_AsWKB(g) WHERE id=2')
                cursor.execute('INSERT INTO geo VALUES(14,NULL,%s),(15,NULL,%s),(16,NULL,%s),(17,NULL,%s)',
                    (b'bad native binary',struct.pack('>BI2d',0,1,-79,43),b'0'*65537,(4294967294).to_bytes(4,'little')+struct.pack('<BI2d',1,1,1,2)))
                cursor.execute('CREATE TABLE pending(id INT PRIMARY KEY)')
                cursor.execute('CREATE TABLE dense(id INT PRIMARY KEY,g GEOMETRY)')
                dense='LINESTRING('+','.join(str(i)+' '+str(i%13) for i in range(4090))+')'
                for i in range(3):cursor.execute('INSERT INTO dense VALUES(%s,ST_GeomFromText(%s))',(i,dense))
                cursor.execute("CREATE USER 'spatial_denied'@'%' IDENTIFIED BY %s",(password,))
                cursor.execute("GRANT UPDATE(g) ON sr_osc.geo TO 'spatial_denied'@'%'")
                cursor.execute('SELECT id,HEX(CAST(g AS BINARY)),HEX(b) FROM geo ORDER BY id');before=cursor.fetchall()
                app=setup_application(output)
                for use_c in (False,True):
                    sid,target,raw=registration(app,route,password,use_c);checks=[]
                    def post(operation,request):return raw('mysql_spatial_'+operation,request)
                    def failure(operation,request):
                        reply=raw.raw('mysql_spatial_'+operation,request);assert not reply.get_json().get('success'),reply.get_json();return reply.get_json()
                    assert post('databases',{})['rows']==[{'name':'sr_osc'}]
                    columns=post('columns',{'schema_name':'sr_osc','table_name':'geo'})
                    assert {c['COLUMN_NAME'] for c in columns['rows']}=={'g','b'}
                    selected={'format':'mysql','srid':'0','axis_order':'long-lat','map':'native','limit':100,'offset':0,'seconds':30}
                    request={'schema_name':'sr_osc','table_name':'geo','column_name':'g','fingerprint':columns['fingerprint'],'confirmed':True,'options':selected}
                    value=post('read',request);(output/('native-'+str(use_c)+'.json')).write_text(json.dumps(value,indent=2)+'\n')
                    assert len(value['rows'])==17 and value['consistent_snapshot'] and not value['external_requests']
                    assert value['native_interface']==('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection'),value['native_interface']
                    for entry,row in zip(value['rows'],before):
                        assert entry['raw_hex']==(row[1].lower() if row[1] is not None else None)
                    for index in [0,1,2,3,4,5,6,7,11,12]:assert value['rows'][index]['map_geometry'] is not None,value['rows'][index]
                    toronto=value['rows'][1]
                    assert toronto['geojson']['coordinates']==[-79,43] and toronto['wkt_srs']=='POINT(43 -79)' and toronto['wkt_xy']=='POINT(-79 43)',toronto
                    assert value['srs']['4326']['status']=='available' and 'AXIS' in value['srs']['4326']['definition']
                    assert value['rows'][8]['state']=='null' and value['rows'][9]['map_status']=='empty'
                    assert value['rows'][10]['validity']=='invalid' and value['rows'][10]['map_geometry'] is None
                    checks.append('all-native-geometry-types-holes-collections-SRID-axis-null-empty-invalid-and-exact-internal-bytes')
                    wgs=post('read',{**request,'options':{**selected,'map':'wgs84'}})
                    projected=wgs['rows'][11]['map_geometry']['coordinates'];assert abs(projected[0]+79)<1e-8 and abs(projected[1]-43)<1e-8,projected
                    assert wgs['rows'][0]['map_geometry'] is None and wgs['rows'][0]['errors']
                    checks.append('native-3857-to-4326-transform-and-SRID-zero-refusal-with-source-preservation')
                    wkb=post('read',{**request,'column_name':'b','options':{**selected,'format':'wkb','srid':'4326','axis_order':'srid-defined','offset':1,'limit':1}})['rows'][0]
                    assert wkb['geojson']['coordinates']==[-79,43] and wkb['raw_hex']==before[1][2].lower()
                    binary=post('read',{**request,'column_name':'b','options':{**selected,'format':'wkb','srid':'4326','offset':14,'limit':1}})['rows'][0]
                    assert binary['geojson']['coordinates']==[-79,43] and binary['raw_hex']==before[14][2].lower()
                    bad=post('read',{**request,'column_name':'b','options':{**selected,'format':'wkb','offset':13,'limit':1}})['rows'][0]
                    assert bad['state']=='binary-fallback' and bad['raw_hex']==before[13][2].lower() and bad['errors']
                    large=post('read',{**request,'column_name':'b','options':{**selected,'format':'wkb','offset':15,'limit':1}})['rows'][0]
                    assert large['state']=='value-too-large' and large['raw_hex'] is None
                    unknown=post('read',{**request,'column_name':'b','options':{**selected,'offset':16,'limit':1}})['rows'][0]
                    assert unknown['state']=='binary-fallback' and unknown['srid']=='4294967294' and unknown['errors']
                    checks.append('native-WKB-big-endian-SRS-defined-order-malformed-unknown-SRID-and-whole-value-byte-bound')
                    page=post('read',{**request,'options':{**selected,'limit':3}});assert len(page['rows'])==3 and page['next_offset']==3
                    dense_source=post('columns',{'schema_name':'sr_osc','table_name':'dense'})
                    dense_report=post('read',{**request,'table_name':'dense','fingerprint':dense_source['fingerprint']})
                    assert dense_report['rows'][2]['map_geometry'] is None and dense_report['rows'][2]['map_status']=='map-position-or-feature-bound'
                    checks.append('bounded-independent-pages-and-total-DDN-position-coverage-without-geometry-sampling')
                    failure('read',{**request,'confirmed':False});failure('read',{**request,'fingerprint':'stale'})
                    failure('read',{**request,'schema_name':'mysql'})
                    denied_sid,denied_target,denied_raw=registration(app,route,password,use_c,username='spatial_denied')
                    denied_columns=denied_raw('mysql_spatial_columns',{'schema_name':'sr_osc','table_name':'geo'})
                    denied=denied_raw.raw('mysql_spatial_read',{**request,'fingerprint':denied_columns['fingerprint']})
                    assert not denied.get_json().get('success') and any(code in denied.get_json()['errormsg'] for code in ('1142','1143')),denied.get_json()
                    checks.append('explicit-consent-observed-fingerprint-database-scope-and-native-column-privilege-refusals')
                    oracle.autocommit=False
                    try:
                        cursor.execute('INSERT INTO pending VALUES(99)');cursor.execute('SAVEPOINT spatial_guard')
                        cursor.execute("SELECT CAST('original warning' AS UNSIGNED)");cursor.fetchall();cursor.execute('SHOW COUNT(*) WARNINGS');warnings=cursor.fetchone()[0];assert warnings
                        fresh=post('read',request);assert fresh['identity']['connection_id']!=str(oracle.connection_id) and oracle.in_transaction
                        cursor.execute('SHOW COUNT(*) WARNINGS');assert cursor.fetchone()[0]==warnings
                        cursor.execute('ROLLBACK TO SAVEPOINT spatial_guard');cursor.execute('SELECT COUNT(*) FROM pending');assert cursor.fetchone()[0]==1
                    finally:oracle.rollback();oracle.autocommit=True
                    cursor.execute('SELECT id,HEX(CAST(g AS BINARY)),HEX(b) FROM geo ORDER BY id');assert cursor.fetchall()==before
                    checks.append('independent-readonly-native-session-preserves-interactive-transaction-savepoint-warnings-and-all-source-bytes')
                    proof['interfaces'].append({'use_c':use_c,'native_interface':value['native_interface'],'complete':True,'checks':checks})
                if browser_binary:proof['browser']=browser(app,output,sid,password,browser_binary,driver_binary,bytes.fromhex(before[1][1]))
                proof['complete']=True
            finally:cursor.close();oracle.close()
    finally:
        proof['owned_server_stopped']=bool(owned and owned.get('owned_server_stopped'))
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def browser(app,output,sid,password,binary,driver_binary,expected):
    import threading
    from urllib.parse import unquote,urlsplit
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action,complete_endpoint_prompt
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    driver=None;checks=[]
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1600'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'))
        options.set_capability('goog:loggingPrefs',{'browser':'ALL','performance':'ALL'})
        options.add_experimental_option('prefs',{'download.default_directory':str(output/'downloads'),'download.prompt_for_download':False})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,90);ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def owned(browser):
            return next((n for n in browser.find_elements(By.CSS_SELECTOR,'.file-name') if n.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',n,sid)),None)
        node=wait.until(owned);buttons=node.find_element(By.XPATH,'ancestor::div[contains(@class,"file-entry")][1]').find_elements(By.CSS_SELECTOR,'button[aria-label^="Expand "]')
        if buttons:buttons[0].click();complete_endpoint_prompt(driver,password,timeout=5)
        invoke_context_action(wait,driver,wait.until(owned),('Diagnostics and verification','MySQL spatial data inspection...'),handle_endpoint_prompt=False)
        complete_endpoint_prompt(driver,password,timeout=5)
        def click(text):
            item=wait.until(lambda b:next((e for e in b.find_elements(By.TAG_NAME,'button') if e.is_displayed() and e.is_enabled() and e.text==text),None))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',item);item.click()
        def field(text):
            label=wait.until(lambda b:b.find_element(By.XPATH,'//label[text()="'+text+'"]'))
            item=driver.find_element(By.ID,label.get_attribute('for'));driver.execute_script('arguments[0].scrollIntoView({block:"center"});',item);return item
        def fill(text,value):
            item=field(text);item.send_keys(Keys.CONTROL,'a');item.send_keys(Keys.BACKSPACE);item.send_keys(value)
        def select(text,choice):
            item=field(text)
            wait.until(lambda _b:item.is_enabled() and item.get_attribute('aria-disabled')!='true')
            item.click();wait.until(lambda b:next((n for n in b.find_elements(By.CSS_SELECTOR,'[role="option"]') if n.is_displayed() and n.text==choice),None)).click()
        fill('Spatial database','sr_osc');fill('Spatial table','geo');click('Observe geometry columns')
        select('Geometry or binary column','g (geometry; SRID unrestricted)')
        consent=driver.find_element(By.XPATH,'//label[contains(. ,"Allow private geometry inspection")]');consent.click();click('Inspect native geometry')
        wait.until(lambda b:any('cartesian' in unquote(i.get_attribute('src')) for i in b.find_elements(By.CSS_SELECTOR,'[aria-label="DDN diagram"] img')))
        select('Inspect spatial row','row-1: inspected / native-X/Y')
        assert field('WKT in native SRS order').get_attribute('value')=='POINT(43 -79)'
        assert field('WKT X/Y (longitude/latitude for geographic SRS)').get_attribute('value')=='POINT(-79 43)'
        driver.save_screenshot(str(output/'native-spatial-inspection.png'));checks.append('built-native-DDN-Cartesian-map-and-SRID-defined-versus-X/Y-inspection')
        click('Download exact original bytes');download=output/'downloads/mysql-geometry.bin';wait.until(lambda _b:download.exists());assert download.read_bytes()==expected
        checks.append('built-exact-original-native-binary-download')
        events=[json.loads(item['message'])['message'] for item in driver.get_log('performance')]
        external=[e['params']['request']['url'] for e in events if e['method']=='Network.requestWillBeSent' and
            urlsplit(e['params']['request']['url']).scheme in {'http','https'} and urlsplit(e['params']['request']['url']).hostname not in {'127.0.0.1','localhost'}]
        assert not external,external;checks.append('built-inspection-and-map-with-no-external-network-or-tile-requests')
        click('Clear private inspection');wait.until(lambda b:not b.find_elements(By.CSS_SELECTOR,'[aria-label="Native spatial inspection report"]'))
        checks.append('built-private-native-values-and-map-clear')
        errors=[r for r in driver.get_log('browser') if r['level']=='SEVERE'];assert not errors,errors
        return {'complete':True,'checks':checks,'console_errors':errors,'external_requests':external}
    except Exception:
        if driver:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();thread.join(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();qualify(args.output,args.browser_binary,args.driver_binary)
