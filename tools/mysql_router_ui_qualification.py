"""Built desktop Router context-menu and native deployment/service evidence."""
import json
from pathlib import Path
import secrets
import threading


def qualify(output,fixture,application_directory,sid,binary,driver_binary,resume_job=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);owned=json.loads(Path(fixture).read_text())
    if not owned.get('complete') or not owned['network'].startswith('sr-router240-'):raise ValueError('Select the explicitly owned native fixture')
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app=setup_application(Path(application_directory));client=app.test_client()
    from flask import url_for
    from pgadmin.model import User,Server
    from pgadmin.cdeadmin.workspace import service_for_app
    with app.test_request_context('/'):
        uid=User.query.first().id;server=Server.query.filter_by(id=sid,user_id=uid).one()
        assert server.endpoint_profile.profile_id=='mysql-native' and server.host==owned['peers'][0]['host']
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
        verify=url_for('NODE-server.verify_endpoint_id',gid=server.servergroup_id,sid=sid)
    with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
    assert client.post(verify,json={'password':'true'}).get_json()['success']
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException,ElementClickInterceptedException
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    proof={'complete':False,'checks':[],'history_testing':'not run'}
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1900,1400'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));wait=WebDriverWait(driver,120,ignored_exceptions=(StaleElementReferenceException,ElementClickInterceptedException))
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/');ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def target(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        invoke_context_action(wait,driver,wait.until(target),('Availability','MySQL Router host and service administration...'),handle_endpoint_prompt=False)
        def click(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip()==label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
                        if node.is_displayed():node.click();return True
                return False
            wait.until(attempt)
        def field(label,value):
            print('Desktop field: '+label,flush=True)
            tag=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[normalize-space()="'+label+'"]'))
            node=driver.find_element(By.ID,tag.get_attribute('for'));driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
            node.click();node.send_keys(Keys.CONTROL,'a');node.send_keys(str(value));wait.until(lambda browser:node.get_attribute('value')==str(value))
        def select(label,value):
            tag=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[normalize-space()="'+label+'"]'))
            control=driver.find_element(By.ID,tag.get_attribute('for'));driver.execute_script('arguments[0].scrollIntoView({block:"center"});',control)
            wait.until(lambda browser:(control.click(),True)[1])
            wait.until(lambda browser:browser.find_element(By.CSS_SELECTOR,'li[data-value="'+value+'"]')).click()
        def value(label):
            nodes=driver.find_elements(By.CSS_SELECTOR,'pre[aria-label="'+label+'"]')
            return json.loads(nodes[0].get_attribute('textContent')) if nodes else None
        def authorize():
            label=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[contains(normalize-space(),"Authorize the exact reviewed native Router request")]'))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',label);label.click();click('Confirm native Router request')
        def finish(operation):
            result=wait.until(lambda browser:current if (current:=value('Native Router receipt')) and current['options'].get('operation','bootstrap')==operation and current['state'] not in {'active','dispatching','cancel_requested'} else None)
            (output/(operation+'.json')).write_text(json.dumps(result,indent=2)+'\n')
            assert result['state']=='native_process_returned' and result['remote_receipt']['result']['return_code']==0,result.get('error_message') or result.get('error_type')
            assert result['ssh_reply_observed'] and not result['remote_receipt']['sql_readiness_observed']
            print('Desktop native operation returned: '+operation,flush=True)
            return result
        def inspect(result):
            click('Load Router receipts')
            node=wait.until(lambda browser:browser.find_element(By.CSS_SELECTOR,'button[aria-label="Inspect Router job '+result['job_id']+'"]'))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
            wait.until(lambda browser:browser.find_element(By.XPATH,'//label[normalize-space()="Original Router deployment or service job"]/following-sibling::div//input').get_attribute('value')==result['job_id'])
            field('Router SSH private key',Path(owned['private_key']).read_text())
        if resume_job:
            inspect({'job_id':resume_job})
            click('Inspect original Router invocation')
            bootstrapped=wait.until(lambda browser:current if (current:=value('Native Router receipt')) and current.get('reconciliation') else None)
            facts=bootstrapped['reconciliation']['remote_receipt']
            assert bootstrapped['state']=='unknown' and not bootstrapped.get('ssh_reply_observed')
            assert facts['utility_observation']['return_code']==0 and facts['current_deployment_observation']['observed']
            click('Acknowledge ended Router bootstrap')
            wait.until(lambda browser:current if (current:=value('Native Router receipt')) and current['reconciliation']['remote_receipt'].get('deployment_claim_released') else None)
            (output/'bootstrap.json').write_text(json.dumps(bootstrapped,indent=2)+'\n')
            proof['checks'].append('built-desktop-original-unknown-receipt-current-successful-files-separate-inspection-and-ended-writer-acknowledgement')
        else:
            field('Router SSH host',owned['router_address']);field('Router SSH username','root');field('Expected Router OpenSSH host key',owned['host_key'])
            select('Router SSH authentication','private_key');field('Router SSH private key',Path(owned['private_key']).read_text())
            field('Native Router operating-system user','mysqlrouter');field('Native Router deployment directory','/opt/sr-ui-router-'+secrets.token_hex(8))
            field('Router base port',16446);field('Router bind address','0.0.0.0')
            field('Additional native bootstrap arguments (one per line)','--name=sr-ui-'+secrets.token_hex(6)+'\n--conf-skip-x-protocol')
            click('Use registered metadata seed');wait.until(lambda browser:browser.find_element(By.XPATH,'//label[normalize-space()="Router metadata seed host"]/following-sibling::div//input').get_attribute('value')==owned['peers'][0]['host'])
            click('Review native Router request');wait.until(lambda browser:value('Native Router review'));authorize();bootstrapped=finish('bootstrap')
            assert bootstrapped['remote_receipt']['deployment_observation']['native_router_ids']
            proof['checks'].append('built-desktop-owner-context-menu-private-SSH-native-bootstrap-exact-review-and-native-ID')
        inspect(bootstrapped);field('Exact Router systemd unit','sr-ui-router-'+secrets.token_hex(6)+'.service')
        click('Review native Router request');wait.until(lambda browser:current if (current:=value('Native Router review')) and current['observation'].get('installation') else None);authorize();installed=finish('install_service')
        assert installed['remote_receipt']['service_installation_result']['installed']
        current=installed
        for operation in (('service_start','service_stop') if resume_job else ('service_enable','service_disable','service_start','service_restart','service_stop')):
            inspect(current);select('Native Router operation',operation)
            if operation in {'service_stop','service_restart'}:
                label=driver.find_element(By.XPATH,'//label[contains(normalize-space(),"Disconnect all routed clients")]');driver.execute_script('arguments[0].scrollIntoView({block:"center"});',label);label.click()
            click('Review native Router request');wait.until(lambda browser:current if (current:=value('Native Router review')) and current['observation'].get('service') else None);authorize();current=finish(operation)
        field('Router SSH private key',Path(owned['private_key']).read_text())
        click('Inspect original Router invocation');wait.until(lambda browser:current if (current:=value('Native Router receipt')) and current.get('reconciliation') else None)
        proof['checks'].append('built-desktop-reviewed-unit-installation-start-stop-from-original-unknown-and-separate-service-receipt' if resume_job else 'built-desktop-native-unit-installation-enable-disable-start-restart-stop-and-original-receipt-observation')
        errors=[row for row in driver.get_log('browser') if row['level']=='SEVERE'];assert not errors,errors
        driver.save_screenshot(str(output/'desktop.png'));proof.update(complete=True,console_errors=errors,version=driver.capabilities['browserVersion'])
    except BaseException:
        if driver is not None:
            text=driver.find_element(By.TAG_NAME,'body').get_attribute('textContent').replace(Path(owned['private_key']).read_text(),'[owned fixture private key omitted]')
            driver.execute_script('for(const element of document.querySelectorAll("textarea,input[type=password]"))element.style.visibility="hidden";')
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(text)
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();thread.join(timeout=10)
        jobs=getattr(service_for_app(app),'mysql_router_jobs',None)
        if jobs is not None:jobs.close()
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof
