"""Built desktop recovered-service observation, review and native activation."""
import json
from pathlib import Path
import threading


def qualify(app,output,sid,staged,selection,binary,driver_binary):
    assert (Path(app.static_folder)/'js/generated/app.bundle.js').is_file(), 'Build the immutable desktop bundle before browser qualification'
    from pgadmin.model import User
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException,ElementClickInterceptedException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action
    output=Path(output);output.mkdir(exist_ok=False)
    with app.test_request_context('/'):
        uid=User.query.first().id
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    driver=None;proof={'complete':False,'checks':[],'history_testing':'ScratchBird history not run'}
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1900,1500'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary))
        wait=WebDriverWait(driver,150,ignored_exceptions=(StaleElementReferenceException,ElementClickInterceptedException))
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/');ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def target(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        invoke_context_action(wait,driver,wait.until(target),('Backup','MySQL physical backups...'),handle_endpoint_prompt=False)
        driver.execute_script('''window.srCutover=[];const send=XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send=function(body){let request;try{request=JSON.parse(body);}catch{}
if(request?.action?.startsWith('mysql_physical_'))this.addEventListener('load',()=>{let reply;try{reply=JSON.parse(this.responseText);}catch{}
window.srCutover.push({action:request.action,status:this.status,error:reply?.errormsg,data:reply?.data});});return send.apply(this,arguments);};''')
        def click(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,'button'):
                    if node.is_enabled() and (node.get_attribute('textContent').strip()==label or node.get_attribute('aria-label')==label):
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
                        if node.is_displayed():node.click();return True
                return False
            wait.until(attempt)
        def field(prefix,text):
            tag=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'label') if node.get_attribute('textContent').startswith(prefix) and node.get_attribute('for')),None))
            node=driver.find_element(By.ID,tag.get_attribute('for'));driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
            node.click();node.send_keys(Keys.CONTROL,'a');node.send_keys(str(text) if text else Keys.BACKSPACE)
            wait.until(lambda _:node.get_attribute('value')==str(text))
        def check(label):
            node=driver.find_element(By.XPATH,'//label[contains(normalize-space(),'+json.dumps(label)+')]//input')
            driver.execute_script('arguments[0].click()',node)
        click('Load physical jobs');click('Inspect physical job '+staged['job_id'])
        wait.until(lambda browser:browser.find_elements(By.CSS_SELECTOR,'[aria-label="Permanent recovered service receipt"]'))
        field('Physical SSH private key',selection['credentials']['private_key'])
        for label,key in [('Registered recovered target ID','target_server_id'),('Matched target acceptance job','acceptance_job_id'),
                ('Original source disable job','source_fence_job_id'),('Confirm recovered UUID','target_confirmation')]:field(label,selection[key])
        check('I acknowledge the selected expected-dump scope and its exclusions')
        click('Review recovered service activation')
        reviewed=wait.until(lambda browser:browser.find_elements(By.CSS_SELECTOR,'[aria-label="Recovered activation review"]'))
        review=json.loads(reviewed[0].get_attribute('textContent'));assert review['options']['deployment_job_id']==staged['job_id']
        assert selection['credentials']['private_key'] not in reviewed[0].get_attribute('textContent')
        check('Confirm this exact recovered activation review');click('Confirm and activate recovered service')
        def ended(browser):
            return next((row['data'] for row in reversed(browser.execute_script('return window.srCutover')) if
                row['action'].startswith('mysql_physical_cutover_') and (row.get('data') or {}).get('production_cutover_verified')),None)
        value=wait.until(ended)
        click('Observe activation without replay')
        wait.until(lambda browser:any(row['action']=='mysql_physical_cutover_reconcile' and row.get('data') for row in browser.execute_script('return window.srCutover')))
        driver.save_screenshot(str(output/'desktop.png'));proof['console_errors']=[row for row in driver.get_log('browser') if row['level']=='SEVERE']
        assert not proof['console_errors'],proof['console_errors']
        proof.update(complete=True,job_id=value['job_id'],checks=['built-desktop-permanent-stage-receipt-target-acceptance-source-fence-review-confirmation-and-real-native-activation','built-desktop-independent-activation-observation-without-replay'])
        return value
    except BaseException:
        if driver is not None:
            driver.save_screenshot(str(output/'failure.png'));(output/'browser.html').write_text(driver.page_source)
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();thread.join(timeout=5)
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
