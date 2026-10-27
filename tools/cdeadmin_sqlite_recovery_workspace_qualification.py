"""Qualify native offline SQLite recovery, authenticated receipts and copy activation."""
import argparse
import builtins
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output, library, *, binary=None, driver_binary=None):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents: raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    proof = {'complete': False, 'history_testing': 'not run', 'checks': [], 'source_sha256': {}}
    for path in [Path(__file__), *list((ROOT / 'web/pgadmin/cdeadmin/providers/sqlite').glob('recovery*.py')),
                 *list((ROOT / 'web/pgadmin/cdeadmin/workspace').glob('sqlite_recovery*.py')),
                 ROOT / 'web/pgadmin/cdeadmin/workspace/service.py', ROOT / 'web/pgadmin/cdeadmin/context_menu.py',
                 ROOT / 'web/pgadmin/browser/server_groups/servers/__init__.py',
                 ROOT / 'web/pgadmin/static/js/Dialogs/SQLiteRecovery.jsx', ROOT / 'web/pgadmin/static/js/Dialogs/index.jsx']:
        proof['source_sha256'][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False
    for name, filename in {'DATA_DIR': 'app', 'SQLITE_PATH': 'app/application.db',
            'SESSION_DB_PATH': 'app/sessions', 'STORAGE_DIR': 'app/storage', 'LOG_FILE': 'app/application.log',
            'AZURE_CREDENTIAL_CACHE_DIR': 'app/azure', 'CDEADMIN_OPERATION_STORE_PATH': 'app/operations.json',
            'CDEADMIN_SQLITE_RECOVERY_ROOT': 'recovery-jobs'}.items():
        setattr(config, name, str(output / filename))
    config.CDEADMIN_SQLITE_RECOVERY_LIBRARY = str(Path(library).resolve(strict=True))
    source = output / 'native-source.sqlite'; target_path = output / 'http-recovered.sqlite'
    connection = sqlite3.connect(source)
    try:
        assert sqlite3.sqlite_version == '3.53.0'
        connection.execute('CREATE TABLE healthy(id INTEGER PRIMARY KEY,v TEXT,p BLOB)')
        connection.execute('INSERT INTO healthy VALUES(?,?,?)', (9007199254740993, 'é 雪\x00end', b'\x00\xff'))
        connection.execute('CREATE TABLE damaged(id INTEGER PRIMARY KEY,v BLOB)')
        connection.executemany('INSERT INTO damaged(v) VALUES(?)', [(b'owned corrupted leaf' * 30,)] * 100)
        connection.commit()
        page_size = connection.execute('PRAGMA page_size').fetchone()[0]
        page = connection.execute("SELECT pageno FROM dbstat WHERE name='damaged' AND pagetype='leaf' LIMIT 1").fetchone()[0]
    finally: connection.close()
    with source.open('r+b') as stream:
        stream.seek((page - 1) * page_size); stream.write(b'\x00')
    source_checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    from pgadmin import create_app
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from flask import url_for
    app = create_app('ScratchRobin-native-sqlite-recovery')
    app.PGADMIN_RUNTIME = False; app.PGADMIN_INT_KEY = ''; app.run_before_app_start()
    client = app.test_client()
    try:
        with app.test_request_context('/'):
            user = User.query.first(); uid = user.id; group = ServerGroup.query.filter_by(user_id=uid).first()
            app.blueprints['NODE-engine_type'].connector_visibility['sqlite'].set(True, user_id=uid)
            server = Server(user_id=uid, servergroup_id=group.id, name='Owned offline SQLite recovery',
                host=None, port=1, username='', maintenance_db=str(source), save_password=0)
            server._cde_endpoint_registration = registration_profile('sqlite-native')
            server._cde_endpoint_route_configuration = {'database': str(source), 'filesystem_root': str(output),
                'database_create_root': str(output), 'timeout': .1}
            db.session.add(server); db.session.commit(); sid = server.id; endpoint_id = server.endpoint_profile.id
            target = str(uuid.uuid4())
            db.session.add(EndpointDatabaseTarget(id=target, endpoint_id=endpoint_id, display_name='Recovery source',
                database=str(source), configuration='{}', active=1)); db.session.commit()
            verification_before = server.endpoint_profile.runtime_identity.verification_state
            url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=sid)
        with client.session_transaction() as session: session['_user_id'] = str(uid); session['_fresh'] = True
        def post(action, fields, *, refused=False, scoped=None):
            response = client.post(url + ('?database_target_id=' + scoped if scoped else ''),
                json={'action': 'sqlite_recovery_' + action, 'request': {'database_target_id': target, **fields}})
            value = response.get_json()
            if refused:
                assert response.status_code == 400, value
                return value
            if response.status_code != 200 or not value.get('success'):
                (output / 'http-failure.json').write_text(json.dumps(value, indent=2) + '\n')
                raise RuntimeError('Native SQLite recovery HTTP ' + action + ' failed')
            return value['data']
        catalog = post('catalog', {})
        assert catalog['runtime']['available'] and catalog['runtime_verification_state'] == verification_before
        proof['checks'].append('offline-registration-catalog-and-independently-qualified-native-recovery-runtime')
        reviewed = post('review', {'options': {'output_path': str(target_path), 'source_isolated': True}})
        request = {'job_id': reviewed['job_id'], 'review_digest': reviewed['review_digest'], 'confirmed': True}
        post('start', request)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            receipt = post('status', {'job_id': reviewed['job_id']})
            if receipt['state'] not in {'dispatching', 'active', 'cancel_requested', 'publishing'}: break
            time.sleep(.05)
        assert receipt['state'] == 'completed' and receipt['result']['integrity_check'] == 'ok', receipt
        assert receipt['result']['application_data_verified'] is False
        assert post('start', request)['state'] == 'completed'
        post('status', {'job_id': reviewed['job_id'], 'database_target_id': str(uuid.uuid4())}, refused=True)
        post('status', {'job_id': reviewed['job_id']}, scoped=str(uuid.uuid4()), refused=True)
        assert post('list', {})['jobs'][0]['job_id'] == reviewed['job_id']
        assert post('reconcile', {'job_id': reviewed['job_id']})['current_artifact']['matches_expected']
        check_copy(target_path)
        with app.test_request_context('/'):
            assert db.session.get(Server, sid).endpoint_profile.runtime_identity.verification_state == verification_before
        proof['checks'].append('authenticated-reviewed-once-only-native-corruption-recovery-scoping-and-independent-exact-data')
        if binary:
            proof['browser'] = browser(app, output, sid, binary, driver_binary)
            check_copy(output / 'browser-recovered.sqlite')
        activated = post('activate', {'job_id': reviewed['job_id'], 'confirmation': str(target_path)})
        repeated = post('activate', {'job_id': reviewed['job_id'], 'confirmation': str(target_path)})
        assert repeated['database_target_id'] == activated['database_target_id']
        with app.test_request_context('/'):
            selected = db.session.get(EndpointDatabaseTarget, activated['database_target_id'])
            assert selected.database == str(target_path) and selected.active
        proof['checks'].append('recovered-copy-registered-verified-and-activated-without-original-replacement')
        removed = post('remove_images', {'job_id': reviewed['job_id'], 'confirmation': reviewed['job_id']})
        assert removed['staged_images_removed'] and target_path.is_file()
        assert post('status', {'job_id': reviewed['job_id']})['state'] == 'completed'
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_checksum
        proof.update(complete=True, native_sqlite_version=sqlite3.sqlite_version,
            source_unchanged=True, initial_runtime_verification_state=verification_before,
            native=receipt['result']['native'], process=receipt['result']['process_observation'])
    finally:
        jobs = getattr(app.extensions.get('cdeadmin_provider_workspace'), 'sqlite_recovery_jobs', None)
        if jobs is not None: jobs.close()
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def check_copy(path):
    connection = sqlite3.connect(path)
    try:
        assert connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert connection.execute('SELECT * FROM healthy').fetchall() == [(9007199254740993, 'é 雪\x00end', b'\x00\xff')]
    finally: connection.close()


def browser(app, output, sid, binary, driver_binary):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import StaleElementReferenceException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, invoke_context_action, fill_fields
    http = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start(); driver = None
    try:
        options = webdriver.ChromeOptions(); options.binary_location = binary
        for flag in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1800,1200'): options.add_argument(flag)
        options.add_argument('--user-data-dir=' + str(output / 'browser-profile'))
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        driver = webdriver.Chrome(options=options, service=Service(driver_binary))
        driver.get('http://127.0.0.1:' + str(http.server_port) + '/browser/')
        wait = WebDriverWait(driver, 90, ignored_exceptions=(StaleElementReferenceException,))
        ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'SQLite')
        def registration(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name')
                if node.is_displayed() and browser.execute_script(
                    'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', node, sid)), None)
        node = wait.until(registration)
        # First selection mounts the inspector asynchronously. Let its native
        # registration form settle before opening a pointer-owned context menu.
        node.click()
        wait.until(lambda browser: 'SQLite embedded connection' in browser.find_element(By.TAG_NAME, 'body').text)
        node = wait.until(registration)
        invoke_context_action(wait, driver, node, ('Database workspace', 'Recover SQLite file...'), handle_endpoint_prompt=False)
        def click(label):
            def attempt(browser):
                for button in browser.find_elements(By.TAG_NAME, 'button'):
                    if button.is_displayed() and button.is_enabled() and button.text == label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});', button); button.click(); return True
                return False
            wait.until(attempt)
        field = wait.until(lambda browser: browser.find_element(By.XPATH, '//label[normalize-space()="Registered source file"]'))
        control = driver.find_element(By.ID, field.get_attribute('for')); control.click()
        wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '[role="option"]') if node.text == 'Recovery source'), None)).click()
        fill_fields(wait, ['New recovered database filename (application host)=' + str(output / 'browser-recovered.sqlite')])
        for label in ('Writers to the source file are stopped or isolated',):
            checkbox = wait.until(lambda browser: browser.find_element(By.XPATH, '//label[contains(. ,"' + label + '")]//input'))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});', checkbox); checkbox.click()
        click('Review native recovery')
        wait.until(lambda browser: any('Recovery state: reviewed.' in node.text for node in browser.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        checkbox = driver.find_element(By.XPATH, '//label[contains(. ,"Confirm recovery into this new file")]//input')
        driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});', checkbox); checkbox.click()
        click('Start reviewed recovery')
        wait.until(lambda browser: any('Recovery state: completed.' in node.text for node in browser.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        assert 'Application data still requires verification.' in driver.find_element(By.TAG_NAME, 'body').text
        click('Register and activate recovered copy')
        wait.until(lambda browser: any('The recovered copy is registered and active.' in node.text for node in browser.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        driver.save_screenshot(str(output / 'native-sqlite-recovery.png'))
        errors = [row for row in driver.get_log('browser') if row['level'] == 'SEVERE']
        assert not errors, errors
        return {'complete': True, 'console_errors': 0, 'offline_native_recovery_and_copy_activation': True}
    except Exception:
        if driver is not None:
            driver.save_screenshot(str(output / 'browser-failure.png'))
            (output / 'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME, 'body').text)
        raise
    finally:
        if driver is not None: driver.quit()
        http.shutdown(); http.server_close(); thread.join(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True); parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--browser-binary'); parser.add_argument('--driver-binary'); arguments = parser.parse_args()
    qualify(arguments.evidence, arguments.library, binary=arguments.browser_binary, driver_binary=arguments.driver_binary)
