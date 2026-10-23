"""Built desktop full-scope native comparison and private report acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import threading
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def browser(app,output,sid,peer,password,binary,driver_binary):
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
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1400'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        options.add_experimental_option('prefs',{'download.default_directory':str(output/'downloads'),'download.prompt_for_download':False})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,90);ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def owned(browser):
            return next((n for n in browser.find_elements(By.CSS_SELECTOR,'.file-name') if n.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',n,sid)),None)
        node=wait.until(owned)
        buttons=node.find_element(By.XPATH,'ancestor::div[contains(@class,"file-entry")][1]').find_elements(By.CSS_SELECTOR,'button[aria-label^="Expand "]')
        if buttons:buttons[0].click();complete_endpoint_prompt(driver,password,timeout=5)
        invoke_context_action(wait,driver,wait.until(owned),('Diagnostics and verification','MySQL full-table data comparison...'),handle_endpoint_prompt=False)
        complete_endpoint_prompt(driver,password,timeout=10)
        def click(label):
            item=wait.until(lambda b:next((e for e in b.find_elements(By.TAG_NAME,'button') if e.is_displayed() and e.is_enabled() and e.text==label),None))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',item);item.click()
        def field(label):
            def ready(browser):
                value=browser.find_element(By.XPATH,'//label[text()="'+label+'"]')
                item=browser.find_element(By.ID,value.get_attribute('for'))
                return item if item.is_displayed() and item.is_enabled() else None
            item=wait.until(ready);driver.execute_script('arguments[0].scrollIntoView({block:"center"});',item);return item
        def fill(label,value):
            item=field(label);item.send_keys(Keys.CONTROL,'a');item.send_keys(Keys.BACKSPACE);item.send_keys(value)
        click('Discover registered comparison endpoints');field('Comparison target endpoint').click()
        wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'li[role="option"][data-value="'+str(peer)+'"]')).click()
        for target_schema,expected in [('sr_other','different'),('sr_osc','matched')]:
            fill('Source comparison database','sr_osc');fill('Target comparison database',target_schema)
            fill('Source complete table','t');fill('Target complete table','t')
            click('Observe source table');click('Observe target table');click('Add complete table pair')
            consent=wait.until(lambda b:b.find_element(By.XPATH,'//label[contains(. ,"Allow native server read locks and complete private table scans")]'))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',consent);consent.click()
            wait.until(lambda _b:consent.find_element(By.TAG_NAME,'input').is_selected());click('Start full native comparison')
            panel=wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'[aria-label="Native full-table comparison report"]'))
            wait.until(lambda _b:'Comparison: completed' in panel.text)
            assert 't → t: '+expected in panel.text,panel.text
            if expected=='different':
                assert 'Source-only rows: 1; target-only rows: 1.' in panel.text,panel.text
                click('Download private comparison report')
                path=output/'downloads/mysql-data-comparison.json';wait.until(lambda _b:path.exists())
                downloaded=json.loads(path.read_text());assert downloaded['coverage'][0]['state']=='different' and not downloaded['repair_dispatched']
                checks.append('built-private-report-download-with-complete-mismatch-counts')
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',panel)
            driver.save_screenshot(str(output/('native-drift-'+expected+'.png')))
            checks.append('built-native-complete-table-'+expected+'-and-recorded-positions')
            click('Clear private comparison');wait.until(lambda b:not b.find_elements(By.CSS_SELECTOR,'[aria-label="Native full-table comparison report"]'))
        checks.append('built-private-comparison-clear')
        errors=[r for r in driver.get_log('browser') if r['level']=='SEVERE'];assert not errors,errors
        return {'complete':True,'checks':checks,'console_errors':errors}
    except Exception:
        if driver:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();thread.join(timeout=10)


def qualify(output,binary,driver_binary):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from cdeadmin_mysql_online_ddl_qualification import registration
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    paths=['web/pgadmin/static/js/Dialogs/MySQLDataDrift.jsx',str(Path(__file__).relative_to(ROOT))]
    proof={'complete':False,'history_testing':'not run','source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    owned=None
    try:
        with server(output/'fixture') as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;cursor=oracle.cursor()
            try:
                for database,value in [('sr_osc','left'),('sr_other','right')]:
                    cursor.execute('CREATE DATABASE '+database);cursor.execute('CREATE TABLE '+database+'.t(id INT PRIMARY KEY,note VARCHAR(80))')
                    cursor.execute('INSERT INTO '+database+'.t VALUES(1,%s)',(value,))
                password=secrets.token_urlsafe(24);cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                app=setup_application(output);sid,_target,_=registration(app,route,password,True);peer,_target,_=registration(app,route,password,True)
                proof['browser']=browser(app,output,sid,peer,password,binary,driver_binary)
                for database,value in [('sr_osc','left'),('sr_other','right')]:
                    cursor.execute('SELECT note FROM '+database+'.t');assert cursor.fetchall()==[(value,)]
                proof.update(independent_native_oracle=True,complete=True)
            finally:cursor.close();oracle.close()
    finally:
        proof['owned_server_stopped']=bool(owned and owned['owned_server_stopped']);proof['complete'] &= proof['owned_server_stopped']
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--browser-binary',required=True);parser.add_argument('--driver-binary',required=True)
    args=parser.parse_args();qualify(args.output,args.browser_binary,args.driver_binary)
