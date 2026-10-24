"""Native MySQL service workflows on an explicitly owned SSH/systemd fixture.

The fixture JSON contains owned_fixture=true, hostname, ssh_port, mysql_port,
private_key (filename), mysql_user/password, service_name, native_executable,
configuration_file, native_datadir and native_pid_file. Use a disposable host;
this qualification deliberately restarts/stops/starts its native MySQL service.
No ScratchBird or persistent history qualification is performed.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output, fixture, browser_binary=None, driver_binary=None,installation=False,installation_only=False):
    output = Path(output).resolve(); fixture = Path(fixture).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Keep native fixture evidence outside source')
    configuration = json.loads(fixture.read_text())
    if configuration.get('owned_fixture') is not True:
        raise ValueError('Select an explicitly owned disposable MySQL/systemd fixture')
    output.mkdir(parents=True, exist_ok=False)
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app = setup_application(output)
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from pgadmin.cdeadmin.providers.mysql_family import mysql_host_transport as native
    import mysql.connector
    key = Path(configuration['private_key']).read_text()
    credentials = {'private_key': key}
    peer = native.probe('127.0.0.1', configuration['ssh_port'])
    selected = {'connection': {'host': '127.0.0.1', 'port': configuration['ssh_port'],
        'username': 'root', 'host_key': peer['openssh_key'], 'authentication': 'private_key',
        'platform': 'posix', 'python': 'python3'}, 'executable': configuration['native_executable'],
        'configuration_file': configuration['configuration_file'], 'workspace': '/tmp/scratchrobin-mysql-services',
        'timeout_seconds': 90, 'service': {'manager': 'systemd', 'name': configuration['service_name']},
        'disconnect_all_clients': True}
    def host_script(source):
        transport = native.Transport(selected['connection'], credentials)
        try:
            transport.connect(); channel = transport.transport.open_session(timeout=5)
            channel.exec_command('python3 -'); channel.sendall(source.encode()); channel.shutdown_write()
            output_data = bytearray(); errors = bytearray(); deadline = time.monotonic() + 30
            while not channel.exit_status_ready() or channel.recv_ready() or channel.recv_stderr_ready():
                if channel.recv_ready(): output_data.extend(channel.recv(32768))
                if channel.recv_stderr_ready(): errors.extend(channel.recv_stderr(32768))
                if time.monotonic() > deadline: raise TimeoutError('Owned fixture host setup deadline')
                time.sleep(.01)
            assert channel.recv_exit_status() == 0, errors.decode(errors='replace')
            channel.close()
            return bytes(output_data)
        finally: transport.close()
    proof = {'complete': False, 'interfaces': [], 'history_testing': 'not run', 'full_mysql_product_complete': False}
    paths = ['tools/cdeadmin_mysql_service_qualification.py', 'web/pgadmin/cdeadmin/workspace/mysql_host_service.py']
    paths += ['web/pgadmin/cdeadmin/providers/mysql_family/' + name for name in
              ('mysql_host_services.py', 'mysql_host_worker.py', 'mysql_host_transport.py','mysql_host_installation.py','mysql_host_initialization.py')]
    paths+=['tools/mysql_service_installation_qualification.py','web/pgadmin/static/js/Dialogs/MySQLHost.jsx']
    proof['source_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}
    def connection(pure=False):
        return mysql.connector.connect(host='127.0.0.1', port=configuration['mysql_port'],
            user=configuration['mysql_user'], password=configuration['mysql_password'], use_pure=pure,
            connection_timeout=2)
    def ready():
        deadline = time.monotonic() + 90
        while True:
            try:
                handle = connection(); handle.autocommit = True
                return handle
            except mysql.connector.Error:
                if time.monotonic() > deadline: raise TimeoutError('Owned native MySQL service readiness deadline')
                time.sleep(.25)
    oracle = ready(); cursor = oracle.cursor()
    cursor.execute('CREATE DATABASE IF NOT EXISTS sr_service_native')
    cursor.execute('CREATE TABLE IF NOT EXISTS sr_service_native.committed(id INT PRIMARY KEY)')
    cursor.execute('INSERT IGNORE INTO sr_service_native.committed VALUES(1)')
    cursor.execute('CREATE TABLE IF NOT EXISTS sr_service_native.pending(id INT PRIMARY KEY)')
    cursor.execute('SELECT @@server_uuid'); server_uuid = cursor.fetchone()[0]
    if configuration.get('native_uuid') not in (None, server_uuid):
        raise ValueError('The owned native fixture UUID changed')
    proof['native_server_uuid'] = server_uuid
    cursor.close(); oracle.close()
    client = app.test_client(); service = service_for_app(app)
    try:
        for pure in (True, False):
            with app.test_request_context('/'):
                uid = User.query.first().id; group = ServerGroup.query.filter_by(user_id=uid).first()
                app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=uid)
                item = Server(user_id=uid, servergroup_id=group.id, name='Owned native service ' + str(pure),
                    host='127.0.0.1', port=configuration['mysql_port'], username=configuration['mysql_user'], maintenance_db='mysql', save_password=0)
                item._cde_endpoint_registration = registration_profile('mysql-native')
                item._cde_endpoint_route_configuration = {'host': '127.0.0.1', 'port': configuration['mysql_port'],
                    'user': configuration['mysql_user'], 'use_pure': pure, 'credential_kinds': ['database_password']}
                db.session.add(item); db.session.commit()
                url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=item.id)
                verify = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=item.id)
            with client.session_transaction() as session: session['_user_id'] = str(uid); session['_fresh'] = True
            assert client.post(verify, json={'password': configuration['mysql_password']}).get_json()['success']
            def post(action, request, refused=False):
                response = client.post(url, json={'action': 'mysql_host_' + action, 'request': request}); value = response.get_json()
                if refused:
                    assert response.status_code != 200 or not value.get('success'); return value
                if response.status_code != 200 or not value.get('success'):
                    (output / 'application-failure.json').write_text(json.dumps({'action': action, 'status': response.status_code,
                        'response': value}, indent=2).replace(configuration['mysql_password'], '<redacted>') + '\n')
                    raise AssertionError('Owned native service API failed: ' + action)
                assert configuration['mysql_password'] not in json.dumps(value) and json.dumps(key)[1:-1] not in json.dumps(value)
                return value['data']
            def wait(record, state='native_process_returned'):
                deadline = time.monotonic() + 120
                while record['state'] in {'dispatching', 'active'}:
                    if time.monotonic() > deadline: raise TimeoutError('Owned native service job deadline')
                    time.sleep(.05); record = post('status', {'job_id': record['job_id']})
                assert record['state'] == state, record['state']
                return record
            def admitted(record):
                return {'job_id': record['job_id'], 'review_digest': record['review_digest'], 'confirmed': True, 'credentials': credentials}
            row = {'use_pure': pure, 'checks': []}; proof['interfaces'].append(row)
            if installation_only:
                from mysql_service_installation_qualification import qualify as install
                row['installation']=install(app,client,selected,credentials,host_script,output,pure)
                continue
            wrong = {**selected, 'operation': 'service_restart', 'service': {'manager': 'systemd', 'name': 'ssh.service'}}
            post('review', {'options': wrong, 'credentials': credentials}, refused=True)
            row['checks'].append('another-service-refused-before-dispatch')
            reviewed = post('review', {'options': {**selected, 'operation': 'service_restart'}, 'credentials': credentials})
            unit_file = reviewed['remote_observation']['service']['unit']['FragmentPath']
            original = host_script('from pathlib import Path;import sys;sys.stdout.buffer.write(Path(' + repr(unit_file) + ').read_bytes())')
            try:
                host_script('from pathlib import Path;Path(' + repr(unit_file) + ').write_bytes(' + repr(original + b'\n# owned qualification changed after review\n') + ')')
                post('start', admitted(reviewed), refused=True)
                assert post('status', {'job_id': reviewed['job_id']})['state'] == 'reviewed'
                post('cancel', {'job_id': reviewed['job_id']})
            finally: host_script('from pathlib import Path;Path(' + repr(unit_file) + ').write_bytes(' + repr(original) + ')')
            row['checks'].append('changed-unit-fragment-refused-before-native-service-dispatch')
            previous = None
            for index, operation in enumerate(('service_restart', 'service_stop', 'service_start')):
                options = {**selected, 'operation': operation}
                if operation == 'service_start': options['binding_job_id'] = previous['job_id']
                review = post('review', {'options': options, 'credentials': credentials})
                assert review['source_connection_class'] == ('CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection')
                row['native_connection_class'] = review['source_connection_class']
                row['native_program'] = review['remote_observation']['program']
                associated = review['remote_observation']['service']
                assert associated['service_binding_verified']
                if operation == 'service_start':
                    assert review['source_identity_scope'] == 'previous_online_service_association'
                    assert associated['source_association'] == 'last_observed_native_process' and associated['native_process'] is None
                pending = None
                if operation != 'service_start':
                    pending = connection(pure); query = pending.cursor()
                    query.execute('INSERT INTO sr_service_native.pending VALUES(%s)', (100 + 10 * int(pure) + index,))
                    query.execute('SAVEPOINT owned_service_pending'); query.close()
                result = wait(post('start', admitted(review))); remote = result['remote_receipt']
                assert remote['service_request']['manager_client_completed'] and not remote['service_request']['database_readiness_observed']
                assert not remote['transaction_finality_interpreted_by_common_code']
                assert post('start', admitted(result))['remote_receipt'] == remote
                disconnected = False
                if pending is not None:
                    try:
                        pending.cmd_query('SELECT CONNECTION_ID()')
                    except mysql.connector.Error:
                        disconnected = True
                    finally:
                        pending.close()
                    assert disconnected, 'Native service stop/restart did not disconnect the owned pending session'
                if operation != 'service_stop':
                    oracle = ready(); query = oracle.cursor()
                    query.execute('SELECT @@server_uuid'); assert query.fetchone()[0] == server_uuid
                    query.execute('SELECT COUNT(*),SUM(id) FROM sr_service_native.committed'); assert query.fetchone() == (1, 1)
                    query.execute('SELECT COUNT(*) FROM sr_service_native.pending'); assert query.fetchone()[0] == 0
                    query.close(); oracle.close()
                reconciled = post('reconcile', {'job_id': result['job_id'], 'credentials': credentials})
                later = reconciled['reconciliation']['remote_receipt']
                assert later['result'] == remote['result'] and later['service_reconciliation']['original_native_result_unchanged']
                assert later['service_reconciliation']['observed']
                facts = later['service_reconciliation']['service']
                assert facts['unit']['ActiveState'] == ('inactive' if operation == 'service_stop' else 'active')
                if operation == 'service_restart':
                    assert facts['native_process'] != associated['native_process']
                row['checks'].append({'operation': operation, 'native_manager_client_returned': True,
                    'independent_unit_observation': facts['unit']['ActiveState'], 'sql_ready_claimed_by_product': False,
                    'before_native_process': associated['native_process'], 'after_native_process': facts['native_process'],
                    'owned_pending_session_disconnected_before_disposal': disconnected,
                    'independent_committed_data_and_uuid_preserved': operation != 'service_stop',
                    'independent_unfinished_work_rolled_back': operation == 'service_restart', 'no_replay': True})
                previous = result
            # Native service-manager policy refusal remains a returned client
            # result; it is not misreported as successful MySQL shutdown.
            dropin = unit_file + '.d/99-owned-refusal.conf'
            setup = ('from pathlib import Path;import subprocess;p=Path(' + repr(dropin) + ');p.parent.mkdir(exist_ok=True);'
                'p.write_text("[Unit]\\nRefuseManualStop=yes\\n");subprocess.run(["systemctl","daemon-reload"],check=True)')
            try:
                host_script(setup)
                denied = post('review', {'options': {**selected, 'operation': 'service_stop'}, 'credentials': credentials})
                denied = wait(post('start', admitted(denied)))
                receipt = denied['remote_receipt']
                assert receipt['result']['return_code'] != 0 and not receipt['service_request']['manager_client_completed']
                assert receipt['service_after_process']['service']['unit']['ActiveState'] == 'active'
                assert post('start', admitted(denied))['remote_receipt'] == receipt
            finally:
                host_script('from pathlib import Path;import subprocess;Path(' + repr(dropin) + ').unlink(missing_ok=True);subprocess.run(["systemctl","daemon-reload"],check=True)')
            row['checks'].append('actual-native-service-policy-refusal-keeps-client-outcome-unit-state-and-no-replay')
            uncertain = post('review', {'options': {**selected, 'operation': 'service_stop'}, 'credentials': credentials})
            original_request = native.Transport.request; suppressed = []
            def lost(transport, request, *args, **kwargs):
                value = original_request(transport, request, *args, **kwargs)
                if request.get('action') == 'service_stop':
                    suppressed.append(value)
                    raise OSError('Owned suppressed SSH reply after native service client completed')
                return value
            native.Transport.request = lost
            try: uncertain = wait(post('start', admitted(uncertain)), 'unknown')
            finally: native.Transport.request = original_request
            assert len(suppressed) == 1 and suppressed[0]['service_request']['manager_client_completed']
            assert not uncertain.get('ssh_reply_observed')
            reconciled = post('reconcile', {'job_id': uncertain['job_id'], 'credentials': credentials})
            assert reconciled['state'] == 'unknown' and not reconciled.get('ssh_reply_observed')
            assert reconciled['reconciliation']['original_ssh_acknowledgement_unchanged']
            assert reconciled['reconciliation']['remote_receipt']['service_reconciliation']['service']['unit']['ActiveState'] == 'inactive'
            assert post('start', admitted(uncertain))['state'] == 'unknown' and len(suppressed) == 1
            recovery = post('review', {'options': {**selected, 'operation': 'service_start', 'binding_job_id': uncertain['job_id']}, 'credentials': credentials})
            recovery = wait(post('start', admitted(recovery)))
            assert recovery['remote_receipt']['service_request']['manager_client_completed']
            oracle = ready(); oracle.close()
            row['checks'].append('native-completed-stop-with-lost-SSH-reply-remains-unknown-reconciles-without-replay-and-allows-new-reviewed-offline-start')
            if installation:
                from mysql_service_installation_qualification import qualify as install
                row['installation']=install(app,client,selected,credentials,host_script,output,pure)
        if browser_binary:
            proof['browser'] = browser(app, output, item.id, selected, configuration, ready, browser_binary, driver_binary,proof['interfaces'][-1].get('installation'))
        if installation:
            from mysql_service_installation_qualification import cleanup
            for pure in (True,False):cleanup(host_script,pure)
        proof['complete'] = True
    finally:
        jobs = getattr(service, 'mysql_host_jobs', None)
        if jobs is not None: proof['owned_jobs_stopped'] = jobs.close()
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def browser(app, output, sid, selected, configuration, ready, binary, driver_binary,installation=None):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, invoke_context_action
    from cdeadmin_firebird_ui_form_gate import close_workspace
    http = make_server('127.0.0.1', 0, app, threaded=True); thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start(); driver = None
    try:
        options = webdriver.ChromeOptions(); options.binary_location = binary
        for flag in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1900,1400'): options.add_argument(flag)
        options.add_argument('--user-data-dir=' + str(output / 'browser-profile')); options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        driver = webdriver.Chrome(options=options, service=Service(driver_binary))
        driver.get('http://127.0.0.1:' + str(http.server_port) + '/browser/')
        wait = WebDriverWait(driver, 120, ignored_exceptions=(StaleElementReferenceException,))
        ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'MySQL')
        def open_workspace():
            def target(browser):
                return next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name') if node.is_displayed() and browser.execute_script(
                    'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', node, sid)), None)
            invoke_context_action(wait, driver, wait.until(target), ('Maintenance', 'MySQL database-host administration...'), handle_endpoint_prompt=False)
            wait.until(lambda browser: browser.find_elements(By.XPATH, '//label[normalize-space()="Database SSH host"]'))
        def click(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME, 'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip() == label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});', node)
                        if node.is_displayed(): node.click(); return True
                return False
            wait.until(attempt)
        def field(label, value):
            tag = wait.until(lambda browser: browser.find_element(By.XPATH, '//label[normalize-space()="' + label + '"]'))
            node = driver.find_element(By.ID, tag.get_attribute('for'))
            node.click(); node.send_keys(Keys.CONTROL, 'a'); node.send_keys(str(value))
            wait.until(lambda browser: node.get_attribute('value') == str(value))
        def select(label, value):
            tag = driver.find_element(By.XPATH, '//label[normalize-space()="' + label + '"]')
            control=driver.find_element(By.ID, tag.get_attribute('for'))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',control)
            wait.until(lambda _browser:control.is_displayed() and control.is_enabled());control.click()
            wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, 'li[data-value="' + value + '"]')).click()
        def load_key():
            node = wait.until(lambda browser: browser.find_element(By.XPATH, '//label[contains(normalize-space(),"Load SSH private key")]//input[@type="file"]'))
            node.send_keys(configuration['private_key'])
        def value(label):
            nodes = driver.find_elements(By.CSS_SELECTOR, '[aria-label="' + label + '"]')
            return json.loads(nodes[0].get_attribute('textContent')) if nodes and nodes[0].get_attribute('textContent').startswith('{') else None
        open_workspace()
        field('Database SSH host', selected['connection']['host']); field('SSH port', selected['connection']['port'])
        field('SSH username', 'root'); field('Expected OpenSSH public host key', selected['connection']['host_key'])
        select('SSH authentication', 'private_key'); load_key()
        field('Native mysqld executable', selected['executable']); field('Native configuration file (blank: no defaults)', selected['configuration_file'])
        field('Private workspace on SSH host', selected['workspace']); field('Native diagnostic timeout seconds', 90)
        checks = []; stopped_job = None
        for operation in ('service_restart', 'service_stop', 'service_start'):
            if operation == 'service_start':
                close_workspace(driver, wait); open_workspace()
                click('Load native host receipts')
                button = wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, 'button[aria-label="Inspect native host job ' + stopped_job + '"]'))
                driver.execute_script('arguments[0].scrollIntoView({block:"center"});', button); button.click()
                wait.until(lambda browser: stopped_job in browser.find_element(By.XPATH, '//label[normalize-space()="Prior verified service job (for offline SQL)"]/following-sibling::div//input').get_attribute('value'))
                load_key()
            select('Native host operation', operation)
            field('Exact systemd MySQL unit', selected['service']['name'])
            if operation != 'service_start':
                checkbox = driver.find_element(By.XPATH, '//label[contains(normalize-space(),"Disconnect all native service clients")]//input')
                if not checkbox.is_selected(): driver.execute_script('arguments[0].click()', checkbox)
            click('Review native host service action')
            review = wait.until(lambda browser: value('Native host diagnostic review'))
            if operation == 'service_start': assert review['source_identity_scope'] == 'previous_online_service_association'
            checkbox = driver.find_element(By.XPATH, '//label[contains(normalize-space(),"Authorize the reviewed native MySQL service action")]//input')
            driver.execute_script('arguments[0].click()', checkbox); click('Confirm native host service action')
            receipt = wait.until(lambda browser: current if (current := value('Native host diagnostic receipt')) and current['options']['operation']==operation and current['state'] == 'native_process_returned' else None)
            assert receipt['remote_receipt']['service_request']['manager_client_completed']
            assert not receipt['remote_receipt']['service_request']['database_readiness_observed']
            if operation == 'service_stop': stopped_job = receipt['job_id']
            else:
                oracle = ready(); oracle.close()
            click('Reconcile native host receipt')
            reconciled = wait.until(lambda browser: current if (current := value('Native host diagnostic receipt')) and current.get('reconciliation') else None)
            assert reconciled['reconciliation']['remote_receipt']['service_reconciliation']['observed']
            checks.append({'operation': operation, 'native_service_manager_completed': True,
                'offline_workspace_reopened_with_prior_binding': operation == 'service_start'})
        if installation:
            close_workspace(driver,wait);sid=installation['server_id'];open_workspace()
            click('Load native host receipts')
            button=wait.until(lambda browser:browser.find_element(By.CSS_SELECTOR,'button[aria-label="Inspect native host job '+installation['initialized_job_id']+'"]'))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',button);button.click();load_key()
            select('Native host operation','install_service');field('Exact systemd MySQL unit','sr-installed-desktop.service')
            click('Review native host service action')
            reviewed=wait.until(lambda browser:current if (current:=value('Native host diagnostic review')) and current['observation'].get('service_installation') else None)
            assert reviewed['source_identity_scope']=='previous_native_initializer_uuid_checked_on_host'
            checkbox=driver.find_element(By.XPATH,'//label[contains(normalize-space(),"Authorize the reviewed native MySQL service action")]//input')
            driver.execute_script('arguments[0].click()',checkbox);click('Confirm native host service action')
            installed=wait.until(lambda browser:current if (current:=value('Native host diagnostic receipt')) and current['options']['operation']=='install_service' and current['state']=='native_process_returned' else None)
            result=installed['remote_receipt']['service_installation_result']
            assert result['installed'] and result['daemon_reload']['return_code']==0 and result['installed_service_binding']['unit']['ActiveState']=='inactive'
            assert not result['restart_issued'] and not result['enable_issued']
            field('Prior verified service job (for offline SQL)',installed['job_id'])
            for operation,state in (('service_enable','enabled'),('service_disable','disabled')):
                select('Native host operation',operation);click('Review native host service action')
                wait.until(lambda browser:current if (current:=value('Native host diagnostic review')) and current['observation'].get('service') else None)
                checkbox=driver.find_element(By.XPATH,'//label[contains(normalize-space(),"Authorize the reviewed native MySQL service action")]//input')
                driver.execute_script('arguments[0].click()',checkbox);click('Confirm native host service action')
                current=wait.until(lambda browser:current if (current:=value('Native host diagnostic receipt')) and current['options']['operation']==operation and current['state']=='native_process_returned' else None)
                assert current['remote_receipt']['service_after_process']['service']['unit']['UnitFileState']==state
            checks.append({'operation':'native_service_installation','unverified_SQL_registration':True,'native_file_installed':True,'automatic_start':False,'automatic_enable':False,'separate_enable_disable':True})
        driver.execute_script('document.querySelectorAll("input,textarea").forEach(e=>e.style.visibility="hidden")')
        driver.save_screenshot(str(output / 'native-host-service.png'))
        errors = [row for row in driver.get_log('browser') if row['level'] == 'SEVERE']; assert not errors, errors
        close_workspace(driver, wait)
        return {'complete': True, 'checks': checks, 'console_errors': errors, 'version': driver.capabilities['browserVersion']}
    except Exception:
        if driver:
            driver.execute_script('document.querySelectorAll("input,textarea").forEach(e=>e.style.visibility="hidden")')
            driver.save_screenshot(str(output / 'browser-failure.png'))
            text = driver.find_element(By.TAG_NAME, 'body').text.replace(configuration['mysql_password'], '<redacted>')
            (output / 'browser-failure-text.txt').write_text(text)
        raise
    finally:
        if driver: driver.quit()
        http.shutdown(); thread.join(timeout=10)


def browser_only(output, fixture, application_directory, sid, binary, driver_binary,installation_evidence=None):
    """Repeat browser evidence against the same persisted owner/registration."""
    output = Path(output).resolve(); configuration = json.loads(Path(fixture).read_text())
    if output == ROOT or ROOT in output.parents or configuration.get('owned_fixture') is not True:
        raise ValueError('Select external evidence and an owned fixture')
    output.mkdir(parents=True, exist_ok=False)
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app = setup_application(Path(application_directory).resolve())
    from flask import url_for
    from pgadmin.model import User, Server
    from pgadmin.cdeadmin.workspace import service_for_app
    from pgadmin.cdeadmin.providers.mysql_family import mysql_host_transport as native
    import mysql.connector
    with app.test_request_context('/'):
        uid = User.query.first().id; server = Server.query.filter_by(id=sid, user_id=uid).one()
        assert server.port == configuration['mysql_port'] and server.endpoint_profile.profile_id == 'mysql-native'
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=uid)
        verify = url_for('NODE-server.verify_endpoint_id', gid=server.servergroup_id, sid=sid)
    client = app.test_client()
    with client.session_transaction() as session: session['_user_id'] = str(uid); session['_fresh'] = True
    assert client.post(verify, json={'password': configuration['mysql_password']}).get_json()['success']
    peer = native.probe('127.0.0.1', configuration['ssh_port'])
    selected = {'connection': {'host': '127.0.0.1', 'port': configuration['ssh_port'], 'username': 'root',
        'host_key': peer['openssh_key'], 'authentication': 'private_key', 'platform': 'posix', 'python': 'python3'},
        'executable': configuration['native_executable'], 'configuration_file': configuration['configuration_file'],
        'workspace': '/tmp/scratchrobin-mysql-services', 'service': {'manager': 'systemd', 'name': configuration['service_name']}}
    def ready():
        deadline = time.monotonic() + 90
        while True:
            try:
                return mysql.connector.connect(host='127.0.0.1', port=configuration['mysql_port'], user=configuration['mysql_user'],
                    password=configuration['mysql_password'], use_pure=False, connection_timeout=2)
            except mysql.connector.Error:
                if time.monotonic() > deadline: raise TimeoutError('Owned native SQL readiness deadline')
                time.sleep(.25)
    proof = {'complete': False, 'history_testing': 'not run', 'full_mysql_product_complete': False}
    names = ['tools/cdeadmin_mysql_service_qualification.py', 'web/pgadmin/cdeadmin/workspace/mysql_host_service.py',
        'web/pgadmin/cdeadmin/context_menu.py', 'web/pgadmin/static/js/Dialogs/MySQLHost.jsx',
        'web/pgadmin/browser/server_groups/servers/static/js/server.js']
    names += ['web/pgadmin/cdeadmin/providers/mysql_family/' + name for name in ('mysql_host_services.py', 'mysql_host_worker.py', 'mysql_host_transport.py')]
    names+=['web/pgadmin/cdeadmin/providers/mysql_family/mysql_host_installation.py','web/pgadmin/cdeadmin/providers/mysql_family/mysql_host_initialization.py','tools/mysql_service_installation_qualification.py']
    proof['source_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
    try:
        installation=json.loads(Path(installation_evidence).read_text()) if installation_evidence else None
        if installation:
            assert installation['complete'] and installation['history_testing']=='not run'
            from cdeadmin_mysql_service_fixture import ssh
            script='from pathlib import Path;import subprocess;name="sr-installed-desktop.service";subprocess.run(["systemctl","stop","--",name],capture_output=True);subprocess.run(["systemctl","disable","--",name],capture_output=True);Path("/etc/systemd/system/"+name).unlink(missing_ok=True);subprocess.run(["systemctl","daemon-reload"],check=True)'
            subprocess.run([*ssh(configuration),'python3 -'],input=script,text=True,check=True,capture_output=True)
        proof['browser'] = browser(app, output, sid, selected, configuration, ready, binary, driver_binary,installation)
        proof['complete'] = True
    finally:
        service = service_for_app(app); jobs = getattr(service, 'mysql_host_jobs', None)
        proof['owned_jobs_stopped'] = jobs.close() if jobs is not None else True
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True); parser.add_argument('--fixture', required=True)
    parser.add_argument('--browser-binary'); parser.add_argument('--driver-binary')
    parser.add_argument('--browser-only-application'); parser.add_argument('--server-id', type=int)
    parser.add_argument('--installation',action='store_true')
    parser.add_argument('--installation-only',action='store_true')
    parser.add_argument('--installation-evidence')
    args = parser.parse_args()
    if args.browser_only_application:
        if not args.server_id or not args.browser_binary: parser.error('Browser-only evidence requires server ID and browser binary')
        result = browser_only(args.output, args.fixture, args.browser_only_application, args.server_id, args.browser_binary, args.driver_binary,args.installation_evidence)
    else:
        result = qualify(args.output, args.fixture, args.browser_binary, args.driver_binary,args.installation or args.installation_only,args.installation_only)
    print(json.dumps({'complete': result['complete'], 'interfaces': len(result.get('interfaces', []))}))
