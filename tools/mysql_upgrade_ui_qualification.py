"""Built desktop review, native preflight, upgrade and original acknowledgement."""
import json
from pathlib import Path
import threading


def qualify(app,output,sid,selected,key,binary,driver_binary):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException,ElementClickInterceptedException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action
    output=Path(output);http=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1900,1500'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary))
        wait=WebDriverWait(driver,150,ignored_exceptions=(StaleElementReferenceException,ElementClickInterceptedException))
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/');ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def target(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        invoke_context_action(wait,driver,wait.until(target),('Maintenance','MySQL database-host administration...'),handle_endpoint_prompt=False)
        def click(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip()==label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
                        if node.is_displayed():node.click();return True
                return False
            wait.until(attempt)
        def field(label,value):
            tag=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'label') if node.get_attribute('textContent')==label and node.get_attribute('for')),None))
            node=driver.find_element(By.ID,tag.get_attribute('for'));driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
            node.click();node.send_keys(Keys.CONTROL,'a');node.send_keys(str(value) if str(value) else Keys.BACKSPACE)
            WebDriverWait(driver,15).until(lambda browser:node.get_attribute('value')==str(value))
        def select(label,value):
            tag=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'label') if node.get_attribute('textContent')==label and node.get_attribute('for')),None))
            node=driver.find_element(By.ID,tag.get_attribute('for'));driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
            option=wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.get_attribute('data-value')==value),None));driver.execute_script('arguments[0].scrollIntoView({block:"center"});',option);option.click()
        field('Database SSH host',selected['connection']['host']);field('SSH port',selected['connection']['port'])
        field('SSH username',selected['connection']['username']);field('Expected OpenSSH public host key',selected['connection']['host_key'])
        select('SSH authentication','private_key');driver.find_element(By.CSS_SELECTOR,'input[type="file"]').send_keys(str(key))
        field('Native mysqld executable',selected['executable']);field('Native configuration file (blank: no defaults)',selected['configuration_file'])
        field('Private workspace on SSH host',selected['workspace']);field('Native diagnostic timeout seconds',selected['timeout_seconds'])
        select('Native host operation','upgrade_service');field('Exact systemd MySQL unit',selected['service']['name'])
        upgrade=selected['upgrade']
        for label,name in [('Candidate MySQL 9.7 executable','executable'),('Candidate native option file','configuration_file'),
                ('Candidate native base directory','basedir'),('Candidate native service user','user'),
                ('Original native data directory','source_datadir'),('Original native PID file','source_pid_file'),
                ('Native MySQL Shell 9.7 on SSH host','shell_executable')]:field(label,upgrade[name])
        field('Native upgrade-check connection JSON (no passwords)',json.dumps(upgrade['check_connection']))
        field('Upgrade-check password','owned-upgrade-private')
        checkbox=driver.find_element(By.XPATH,'//label[contains(normalize-space(),"Disconnect all native service clients")]//input')
        driver.execute_script('arguments[0].click()',checkbox)
        click('Review native host service action')
        reviewed=wait.until(lambda browser:browser.find_element(By.CSS_SELECTOR,'[aria-label="Native host diagnostic review"]').get_attribute('textContent'))
        assert 'owned-upgrade-private' not in reviewed and 'preflight' in reviewed and 'errorCount' in reviewed
        assert json.loads(reviewed)['observation']['upgrade_plan']['preflight']['report']['errorCount']==0
        checkbox=driver.find_element(By.XPATH,'//label[contains(normalize-space(),"Authorize the reviewed native MySQL service action")]//input')
        driver.execute_script('arguments[0].click()',checkbox);click('Confirm native host service action')
        def receipt(browser):
            nodes=browser.find_elements(By.CSS_SELECTOR,'[aria-label="Native host diagnostic receipt"]')
            if not nodes:return None
            value=json.loads(nodes[0].get_attribute('textContent'))
            return value if value['state']=='native_process_returned' else None
        original=wait.until(receipt);assert original['remote_receipt']['result']['return_code']==0
        click('Reconcile native host receipt')
        def observed(browser):
            value=receipt(browser) or {}
            later=value.get('reconciliation',{}).get('remote_receipt',{}).get('upgrade_reconciliation',{})
            versions=later.get('native_upgrade_history',{}).get('upgrade_history',[])
            if later.get('observed') is True and versions and versions[-1].get('version')=='9.7.0':return True
            for node in browser.find_elements(By.TAG_NAME,'button'):
                if node.is_enabled() and node.get_attribute('textContent').strip()=='Reconcile native host receipt':
                    browser.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click();break
            return False
        wait.until(observed)
        click('Acknowledge ended original upgrade and release its data-directory claim')
        acknowledged=wait.until(lambda browser:(value if (value:=receipt(browser)) and value.get('reconciliation',{}).get('remote_receipt',{}).get('upgrade_reconciliation',{}).get('data_directory_claim_released') else None))
        driver.execute_script('document.querySelectorAll("input,textarea").forEach(e=>e.style.visibility="hidden")')
        driver.save_screenshot(str(output/'native-upgrade.png'))
        errors=[row for row in driver.get_log('browser') if row['level']=='SEVERE'];assert not errors,errors
        return {'complete':True,'original':original,'acknowledged':acknowledged,'console_errors':errors,
            'checks':['built-owner-context-menu-private-authentication-native-preflight-review-confirm-and-actual-service-upgrade',
                'separate-native-process-history-observation-and-explicit-original-upgrade-claim-acknowledgement']}
    except BaseException:
        if driver:
            driver.execute_script('document.querySelectorAll("input,textarea").forEach(e=>e.style.visibility="hidden")')
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=5)
