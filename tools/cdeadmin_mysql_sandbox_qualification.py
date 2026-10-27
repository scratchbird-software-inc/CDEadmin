"""Actual native sandbox lifecycle through an offline application registration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def qualify(output, shell, server_binary, *, use_c=False, browser_exchange=False):
    os.environ['CDEADMIN_MYSQLSH_BINARY'] = str(shell)
    os.environ['CDEADMIN_MYSQL_SERVER_BINARY'] = str(server_binary)
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from pgadmin.cdeadmin.workspace.mysql_sandbox_service import SandboxTransport, authority
    import config
    import mysql.connector
    from mysql.connector.connection import MySQLConnection
    from mysql.connector.connection_cext import CMySQLConnection
    import psutil
    app = setup_application(output); service = service_for_app(app); http = app.test_client()
    proof = {'complete': False, 'full_mysql_product_complete': False, 'use_c': use_c, 'checks': [], 'operations': []}
    paths = ['web/pgadmin/cdeadmin/providers/mysql_family/mysql_sandbox.py',
        'web/pgadmin/cdeadmin/workspace/mysql_sandbox_service.py', 'web/pgadmin/static/js/Dialogs/MySQLSandboxes.jsx',
        'tools/cdeadmin_mysql_sandbox_qualification.py']
    proof['source_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}
    password = "Private-sandbox:雪'\\test"
    root = None
    http_server = None
    try:
        with app.test_request_context('/'):
            uid = User.query.first().id; group = ServerGroup.query.filter_by(user_id=uid).first()
            app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=uid)
            item = Server(user_id=uid, servergroup_id=group.id, name='Offline native MySQL sandbox host',
                host='203.0.113.1', port=1, username='root', maintenance_db=None, save_password=0)
            item._cde_endpoint_registration = registration_profile('mysql-native')
            item._cde_endpoint_route_configuration = {'host': '203.0.113.1', 'port': 1, 'user': 'root', 'use_pure': not use_c}
            db.session.add(item); db.session.commit(); sid = item.id
            url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=sid)
            jobs, _owner, _endpoint, native_client, _directories = authority(service, item)
        with http.session_transaction() as session: session['_user_id'] = str(uid); session['_fresh'] = True
        def post(action, request=None, *, refused=False):
            response = http.post(url, json={'action': 'mysql_sandbox_'+action, 'request': request or {}})
            value = response.get_json()
            if refused:
                assert response.status_code == 400, value
                return value
            assert response.status_code == 200 and value.get('success'), value
            return value['data']
        # Native sandbox operations must not depend on an online SQL seed.
        def no_sql(*_args, **_kwargs): raise AssertionError('Offline sandbox workflow attempted registered SQL admission')
        native_client._connect = no_sql
        capabilities = post('catalog'); root = Path(capabilities['sandbox_directories'][0]); port = 3310
        assert set(capabilities['methods']) == {'deploy', 'start', 'stop', 'kill', 'delete'}
        selected = {'operation': 'deploy', 'port': port, 'sandbox_directory': str(root),
            'native_options': {'portx': 33101, 'allowRootFrom': '127.0.0.1', 'ignoreSslError': False,
                'mysqldOptions': ['max_connections=47']}, 'timeout_seconds': 300}
        inspected = post('inspect', {'options': selected})
        assert not inspected['state']['exists'] and 'server_uuid' not in inspected['state']
        proof['checks'].append('offline-registration-no-sql-seed-and-no-fabricated-server-uuid')
        def wait(job):
            deadline = time.monotonic()+420
            while job['state'] in {'dispatching', 'active', 'cancel_requested'} and time.monotonic() < deadline:
                time.sleep(.3); job = post('status', {'job_id': job['job_id']})
            (output/('job-'+job['job_id']+'.json')).write_text(json.dumps(job, indent=2)+'\n')
            return job
        def execute(operation, *, wrong_password=False, uncertain=False):
            options = {**selected, 'operation': operation, 'native_options': selected['native_options'] if operation == 'deploy' else {}}
            reviewed = post('review', {'options': options})
            assert password not in json.dumps(reviewed)
            request = {'job_id': reviewed['job_id'], 'review_digest': reviewed['review_digest'], 'confirmed': True}
            if operation in {'deploy', 'stop'}: request['sandbox_secret'] = {'password': 'incorrect-native-password' if wrong_password else password}
            original = SandboxTransport.execute
            def lost_reply(self, *args, **kwargs):
                result = original(self, *args, **kwargs)
                assert (result.get('control') or {}).get('returned') is True, result.get('control')
                result['control'] = None
                return result
            if uncertain: SandboxTransport.execute = lost_reply
            try: job = wait(post('start', request))
            finally: SandboxTransport.execute = original
            if uncertain: assert job['state'] == 'unknown' and job['native_operation_outcome'] == 'unknown', job
            elif wrong_password:
                assert job['native_operation_outcome'] == 'native_error' and job['native_error'].get('code') == 1045, job
            else: assert job['native_operation_outcome'] == 'returned', job
            assert post('start', request)['job_id'] == job['job_id']
            assert password not in json.dumps(job)
            proof['operations'].append({'operation': operation, 'job_id': job['job_id'], 'outcome': job['native_operation_outcome']})
            (output/'progress.json').write_text(json.dumps(proof, indent=2)+'\n')
            return job
        deployed = execute('deploy')
        state = deployed['result']['sandbox_observation']['state']
        configured = state['native_configuration']
        assert state['process']['qualified'] and configured.get('mysqlx_port', configured.get('loose_mysqlx_port')) == '33101', state
        native_uuid = state['server_uuid']; proof['native_server_uuid'] = native_uuid
        def sql(source, *, rows=False):
            connection = mysql.connector.connect(host='127.0.0.1', port=port, user='root', password=password,
                use_pure=not use_c, autocommit=True)
            assert isinstance(connection, CMySQLConnection if use_c else MySQLConnection)
            proof['connector_class'] = type(connection).__module__+'.'+type(connection).__name__
            try:
                cursor = connection.cursor(); cursor.execute(source)
                return cursor.fetchall() if rows else None
            finally: connection.close()
        assert sql('SELECT @@server_uuid,@@max_connections,@@mysqlx_port', rows=True) == [(native_uuid,47,33101)]
        sql('CREATE DATABASE sr_sandbox'); sql('CREATE TABLE sr_sandbox.payload(id BIGINT UNSIGNED PRIMARY KEY, body TEXT)')
        sql("INSERT INTO sr_sandbox.payload VALUES (18446744073709551615,'native persistence 雪')")
        proof['checks'].append('native-deploy-custom-x-port-server-option-real-uuid-and-independent-driver-login')
        # A foreign PID must never be accepted merely because the native port is up.
        pidfile = root / str(port) / (str(port)+'.pid'); pidbytes = pidfile.read_bytes()
        pidfile.write_text(str(os.getpid()))
        try: post('review', {'options': {**selected, 'operation': 'kill', 'native_options': {}}}, refused=True)
        finally: pidfile.write_bytes(pidbytes)
        execute('stop', wrong_password=True)
        assert sql('SELECT @@server_uuid', rows=True) == [(native_uuid,)]
        unknown = execute('stop', uncertain=True)
        observed = post('reconcile', {'job_id': unknown['job_id']})
        assert observed['native_process_termination_confirmed'] and observed['reconciliation']['state']['process']['qualified'], observed
        blocked = post('review', {'options': {**selected, 'operation': 'start', 'native_options': {}}})
        post('start', {'job_id': blocked['job_id'], 'review_digest': blocked['review_digest'], 'confirmed': True}, refused=True)
        acknowledged = post('acknowledge', {'job_id': unknown['job_id'], 'observation_digest': observed['observation_digest'], 'sandbox_confirmation': str(port)})
        assert acknowledged['native_operation_outcome'] == 'unknown' and acknowledged['target_state_acknowledged_at']
        execute('start')
        expected = [(18446744073709551615, 'native persistence 雪')]
        assert sql('SELECT * FROM sr_sandbox.payload', rows=True) == expected
        proof['checks'].append('foreign-pid-refusal-native-password-error-unknown-reply-observe-fence-acknowledge-and-persistent-restart')
        # Review binds control file bytes before native destructive dispatch.
        reviewed = post('review', {'options': {**selected, 'operation': 'kill', 'native_options': {}}})
        script = root / str(port) / 'start.sh'; original = script.read_bytes(); script.write_bytes(original+b'\n# concurrent edit\n')
        try: post('start', {'job_id': reviewed['job_id'], 'review_digest': reviewed['review_digest'], 'confirmed': True}, refused=True)
        finally: script.write_bytes(original)
        execute('kill'); execute('start')
        assert sql('SELECT * FROM sr_sandbox.payload', rows=True) == expected
        execute('stop'); execute('delete')
        assert not (root / str(port)).exists()
        proof['checks'].append('stale-control-refusal-native-kill-crash-recovery-data-persistence-stop-and-delete')
        # Server mode never grants local OS authority from SQL ownership alone.
        config.SERVER_MODE = True
        try: post('catalog', refused=True)
        finally: config.SERVER_MODE = False
        proof['checks'].append('server-mode-local-host-authority-disabled-by-default')
        if browser_exchange:
            from werkzeug.serving import make_server
            original = SandboxTransport.execute
            proof['browser_native_observations'] = []
            def observed_gui(self, record, *args, **kwargs):
                result = original(self, record, *args, **kwargs)
                if record['options']['port'] == 3311 and (result.get('control') or {}).get('returned'):
                    method = record['options']['operation']
                    observed = {'operation': method, 'native_returned': True}
                    if method in {'deploy', 'start'}:
                        connection = mysql.connector.connect(host='127.0.0.1', port=3311, user='root', password='', use_pure=not use_c, autocommit=True)
                        try:
                            cursor = connection.cursor(); cursor.execute('SELECT @@server_uuid,@@max_connections')
                            identity, connections = cursor.fetchone(); assert connections == 53
                            if method == 'deploy':
                                cursor.execute('CREATE DATABASE sr_gui_sandbox')
                                cursor.execute('CREATE TABLE sr_gui_sandbox.payload(id BIGINT UNSIGNED PRIMARY KEY)')
                                cursor.execute('INSERT INTO sr_gui_sandbox.payload VALUES (18446744073709551615)')
                            cursor.execute('SELECT id FROM sr_gui_sandbox.payload')
                            assert cursor.fetchall() == [(18446744073709551615,)]
                            observed.update(native_uuid=identity, unsigned64_data_verified=True)
                        finally: connection.close()
                    proof['browser_native_observations'].append(observed)
                return result
            SandboxTransport.execute = observed_gui
            try:
                http_server = make_server('0.0.0.0', 5000, app, threaded=True)
                threading.Thread(target=http_server.serve_forever, daemon=True).start()
                (output/'browser-request.json').write_text(json.dumps({'server_id': sid})+'\n')
                deadline = time.monotonic()+600
                while not (output/'browser-response.json').exists():
                    if time.monotonic() > deadline: raise TimeoutError('Native sandbox desktop deadline')
                    time.sleep(.25)
                proof['browser'] = json.loads((output/'browser-response.json').read_text())
                assert proof['browser']['complete'], proof['browser']
                assert [item['operation'] for item in proof['browser_native_observations']] == ['deploy','stop','start','kill','start','stop','delete']
            finally: SandboxTransport.execute = original
        for path in jobs.root.rglob('*'):
            if path.is_file() and path.suffix in {'.json', '.py'}:
                assert password.encode('utf8') not in path.read_bytes(), str(path)
        proof['complete'] = True
    finally:
        if http_server: http_server.shutdown(); http_server.server_close()
        jobs = getattr(service, 'mysql_sandbox_jobs', None)
        if jobs: jobs.close()
        # A failed acceptance run still owns its disposable sandbox process.
        if root is not None:
            for port in (3310, 3311):
                pidfile = root/str(port)/(str(port)+'.pid')
                if pidfile.exists():
                    try:
                        process = psutil.Process(int(pidfile.read_text().strip()))
                        if any(str(root/str(port)/'my.cnf') in item for item in process.cmdline()): process.kill(); process.wait(10)
                    except (psutil.Error, ValueError): pass
        (output/'summary.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


def browser(base_url, output, request, binary, driver_binary):
    from selenium import webdriver
    from selenium.webdriver import ActionChains
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException
    from cdeadmin_ui_evidence import ensure_data_explorer, expand
    driver = None; proof = {'complete': False, 'checks': []}
    try:
        options = webdriver.ChromeOptions(); options.binary_location = binary
        for flag in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1800,1200'): options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'))
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        driver = webdriver.Chrome(options=options, service=Service(driver_binary))
        wait = WebDriverWait(driver, 150, ignored_exceptions=(StaleElementReferenceException,))
        driver.get(base_url+'/browser/'); ensure_data_explorer(wait); expand(wait,'Connectors'); expand(wait,'MySQL')
        def target(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and
                browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,request['server_id'])),None)
        ActionChains(driver).context_click(wait.until(target)).perform()
        for label in ('Availability','MySQL local testing sandboxes...'):
            wait.until(lambda b: next((node for node in b.find_elements(By.CSS_SELECTOR,'[role="menuitem"]') if node.is_displayed() and node.text.strip()==label),None)).click()
        def click(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip()==label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
                        if node.is_displayed(): node.click(); return True
                return False
            wait.until(attempt)
        def control(label):
            for item in driver.find_elements(By.TAG_NAME,'label'):
                if item.get_attribute('textContent').startswith(label):
                    for node in driver.find_elements(By.ID,item.get_attribute('for')):
                        driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
                        if node.is_displayed(): return node
            return None
        def fill(label,value):
            node=wait.until(lambda _browser:control(label));node.send_keys(Keys.CONTROL,'a');node.send_keys(value)
        def content(label):
            for node in driver.find_elements(By.CSS_SELECTOR,'[aria-label="'+label+'"]'):
                driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
                if node.is_displayed(): return node.get_attribute('textContent')
            return None
        click('Load native sandbox capabilities')
        fill('Sandbox classic protocol port','3311')
        fill('Native sandbox deployment options (JSON object)','{"portx":33111,"mysqldOptions":["max_connections=53"]}')
        previous = None
        for method in ('deploy','stop','start','kill','start','stop','delete'):
            if method != 'deploy':
                wait.until(lambda _browser:control('Native sandbox method')).click()
                wait.until(lambda b:next((node for node in b.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.is_displayed() and node.text.strip()==method+'_sandbox_instance'),None)).click()
            click('Review native sandbox operation')
            reviewed=wait.until(lambda _browser:content('Native sandbox review'))
            assert json.loads(reviewed)['options']['operation']==method
            if method in {'deploy','stop'}: click('Use empty native sandbox password')
            fill('Confirm reviewed sandbox port','3311')
            click('Confirm and start native sandbox operation')
            def completed(_browser):
                text=content('Native sandbox receipt')
                if not text:return None
                result=json.loads(text)
                if result['job_id']==previous or result['state'] in {'dispatching','active','cancel_requested'}:return None
                assert result['native_operation_outcome']=='returned',result
                return result
            result=wait.until(completed);previous=result['job_id']
            proof['checks'].append('native-'+method+'-explicit-review-dispatch-and-receipt')
        driver.save_screenshot(str(output/'native-sandbox-desktop.png'))
        logs=driver.get_log('browser');(output/'browser-console.json').write_text(json.dumps(logs,indent=2)+'\n')
        assert not [entry for entry in logs if entry['level']=='SEVERE'],logs
        proof.update(complete=True,severe_console_errors=0)
    finally:
        if driver:
            if not proof['complete']: driver.save_screenshot(str(output/'native-sandbox-failure.png'))
            driver.quit()
        (output/'browser-summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--mysql-shell', type=Path, required=True)
    parser.add_argument('--mysql-server', type=Path, required=True); parser.add_argument('--use-c', action='store_true')
    parser.add_argument('--browser-exchange', action='store_true')
    args = parser.parse_args(); args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    qualify(args.output.resolve(), args.mysql_shell, args.mysql_server, use_c=args.use_c, browser_exchange=args.browser_exchange)
