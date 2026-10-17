"""Native approved-library load through authenticated HTTP and the query UI."""
import argparse
import builtins
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]
from tools.sqlite_extension_fixture import build  # noqa: E402


def qualify(output, headers, binary=None, driver_binary=None):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    proof = {'complete': False, 'history_testing': 'not run', 'checks': [],
             'native_sqlite_version': sqlite3.sqlite_version, 'source_sha256': {}}
    source = ROOT / 'tools/fixtures/sqlite_loadable_probe.c'
    for path in [source, Path(__file__), ROOT / 'tools/sqlite_extension_fixture.py', ROOT / 'web/pgadmin/cdeadmin/providers/sqlite/extensions.py',
                 ROOT / 'web/pgadmin/cdeadmin/providers/sqlite/driver.py', ROOT / 'web/pgadmin/cdeadmin/data_studio/studio.py',
                 ROOT / 'web/pgadmin/static/js/Dialogs/SQLiteExtensions.jsx']:
        proof['source_sha256'][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False
    for name, filename in {'DATA_DIR': 'app', 'SQLITE_PATH': 'app/application.db', 'SESSION_DB_PATH': 'app/sessions',
                           'STORAGE_DIR': 'app/storage', 'LOG_FILE': 'app/application.log',
                           'AZURE_CREDENTIAL_CACHE_DIR': 'app/azure', 'CDEADMIN_OPERATION_STORE_PATH': 'app/operations.json'}.items():
        setattr(config, name, str(output / filename))
    library = build(source, output / 'probe', headers)
    digest = hashlib.sha256(library.read_bytes()).hexdigest()
    manifest = output / 'approved.json'
    manifest.write_text(json.dumps({'format': 'scratchrobin.sqlite.extensions@1', 'extensions': [
        {'id': 'native-probe', 'path': str(library), 'sha256': digest}]}))
    config.CDEADMIN_SQLITE_EXTENSION_MANIFEST = str(manifest)
    from pgadmin import create_app
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from flask import url_for
    database = output / 'native.sqlite'
    sqlite3.connect(database).close()
    app = create_app('ScratchRobin-native-sqlite-extension')
    app.PGADMIN_RUNTIME = False; app.PGADMIN_INT_KEY = ''; app.run_before_app_start()
    client = app.test_client()
    try:
        assert sqlite3.sqlite_version == '3.53.0'
        with app.test_request_context('/'):
            user = User.query.first(); uid = user.id; group = ServerGroup.query.filter_by(user_id=uid).first()
            app.blueprints['NODE-engine_type'].connector_visibility['sqlite'].set(True, user_id=uid)
            server = Server(user_id=uid, servergroup_id=group.id, name='Owned SQLite extension target',
                            host=None, port=1, username='', maintenance_db=str(database), save_password=0)
            server._cde_endpoint_registration = registration_profile('sqlite-native')
            server._cde_endpoint_route_configuration = {'database': str(database), 'filesystem_root': str(output)}
            db.session.add(server); db.session.commit(); sid = server.id
            target = str(uuid.uuid4())
            db.session.add(EndpointDatabaseTarget(id=target, endpoint_id=server.endpoint_profile.id,
                display_name=database.name, database=str(database), configuration='{}', active=1)); db.session.commit()
            verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=sid)
            url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=sid)
        with client.session_transaction() as session:
            session['_user_id'] = str(uid); session['_fresh'] = True
        verified = client.post(verify_url, json={}).get_json(); assert verified.get('success'), verified
        def post(action, **data):
            response = client.post(url, json={'action': action, 'database_target_id': target, **data})
            result = response.get_json()
            if response.status_code != 200 or not result.get('success'):
                (output / 'http-failure.json').write_text(json.dumps(result, indent=2))
                raise AssertionError('Native extension HTTP request failed: ' + action)
            return result['data']
        opened = post('open_session', language_profile='sqlite-sql'); session_id = opened['session_id']
        def extension(operation, **options):
            return post('sqlite_extensions', session_id=session_id, request={'operation': operation, **options})
        assert extension('inventory')['loader_available']
        reviewed = extension('review', extension_id='native-probe')
        result = extension('load', review_id=reviewed['review_id'], confirmed=True)
        assert result['state'] == 'loaded' and result['extension']['sha256'] == digest
        assert extension('receipt', review_id=reviewed['review_id']) == result
        assert extension('load', review_id=reviewed['review_id'], confirmed=True) == result
        catalog = post('source_catalog', session_id=session_id)
        assert any(row['native'].get('name') == 'cde_native_probe' for row in catalog['resources'])
        assert post('source_validate', session_id=session_id, source='SELECT cde_native_probe()')['grammar_valid']
        post('close_session', session_id=session_id)
        proof['checks'].append('authenticated-approved-file-review-load-receipt-no-replay-retained-catalog-and-native-checking')
        if binary:
            proof['browser'] = browser(app, output, sid, binary, driver_binary)
            proof['checks'].append('browser-query-context-review-confirm-load-and-native-function-result')
        proof.update(complete=True, library_sha256=digest)
    finally:
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def browser(app, output, sid, binary, driver_binary):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import StaleElementReferenceException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, wait_for_tree_item, invoke_context_action
    from cdeadmin_sqlite_query_ui_gate import _run_query
    http = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start(); driver = None
    try:
        options = webdriver.ChromeOptions(); options.binary_location = binary
        for flag in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1800,1200'):
            options.add_argument(flag)
        options.add_argument('--user-data-dir=' + str(output / 'browser-profile'))
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        driver = webdriver.Chrome(options=options, service=Service(driver_binary))
        driver.get('http://127.0.0.1:' + str(http.server_port) + '/browser/')
        wait = WebDriverWait(driver, 90, ignored_exceptions=(StaleElementReferenceException,))
        ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'SQLite')
        def owned(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', node, sid)), None)
        label = wait.until(owned).text; expand(wait, label, ('Connectors', 'SQLite'))
        database = wait_for_tree_item(wait, 'native.sqlite', ('Connectors', 'SQLite', label))
        invoke_context_action(wait, driver, database, ('Database workspace', 'Open SQLite SQL editor...'), handle_endpoint_prompt=False)
        engine_options = wait.until(lambda browser: browser.find_element(By.XPATH, '//*[@role="tab" and normalize-space()="Engine options"]'))
        driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});', engine_options); engine_options.click()
        summary = wait.until(lambda browser: browser.find_element(By.XPATH, '//summary[normalize-space()="SQLite native extensions"]'))
        driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});', summary); summary.click()
        def click(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME, 'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip() == label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});', node)
                        if node.is_displayed(): node.click(); return True
                return False
            wait.until(attempt)
        click('Inspect approved extensions'); click('Review native library')
        checkbox = wait.until(lambda browser: browser.find_element(By.XPATH,
            '//label[contains(.,"Load this reviewed native library into the query session")]//input'))
        driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});', checkbox); checkbox.click()
        click('Load native library')
        wait.until(lambda browser: any(node.text.endswith(': loaded') for node in browser.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        _run_query(driver, wait, 'SELECT cde_native_probe() AS native_value', 'native extension: 雪', 'SQLite', output)
        driver.save_screenshot(str(output / 'native-sqlite-extension.png'))
        errors = [row for row in driver.get_log('browser') if row.get('level') == 'SEVERE']
        (output / 'browser-console.json').write_text(json.dumps(errors, indent=2)); assert not errors
        return {'complete': True, 'console_errors': 0}
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
    parser.add_argument('--evidence', type=Path, required=True); parser.add_argument('--sqlite-headers', type=Path, required=True)
    parser.add_argument('--browser-binary'); parser.add_argument('--driver-binary'); args = parser.parse_args()
    qualify(args.evidence, args.sqlite_headers, args.browser_binary, args.driver_binary)
