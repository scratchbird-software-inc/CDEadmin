"""Owned native MySQL notebook API and production desktop qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]
MODEL = 'web/pgadmin/static/js/cdeadmin_ui/projects/SQLNotebookModel.js'


def model(operation, value):
    script = """import {readFileSync} from 'node:fs';
const m=await import('data:text/javascript;base64,'+readFileSync(process.argv[1]).toString('base64'));
const v=JSON.parse(readFileSync(0,'utf8'));
const result=process.argv[2]==='snapshot' ? m.retainedSnapshot(v.rendered,v.source,v.scope,v.policies) : m.portableNotebook(v);
process.stdout.write(JSON.stringify(result));"""
    result = subprocess.run(['node', '--input-type=module', '-e', script, str(ROOT / MODEL), operation],
        input=json.dumps(value), text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def qualify(output, browser_binary=None, driver_binary=None):
    import config  # noqa: F401
    from unittest.mock import patch
    from flask import url_for
    from mysql_qualification_support import server, _root_connection
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from cdeadmin_mysql_online_ddl_qualification import registration
    from pgadmin.model import User, Server
    from pgadmin.cdeadmin.providers.mysql_family.provider import MySQLDBAPIClient
    from pgadmin.cdeadmin.workspace.sql_notebooks import ASSET_TYPE, FORMAT
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    paths = [MODEL, 'web/pgadmin/static/js/cdeadmin_ui/projects/SQLNotebook.jsx',
        'web/pgadmin/static/js/Dialogs/ProviderWorkspaceContent.jsx', 'web/pgadmin/static/js/BrowserComponent.jsx',
        'web/pgadmin/cdeadmin/workspace/assets.py', 'web/pgadmin/cdeadmin/workspace/sql_notebooks.py',
        'web/pgadmin/static/vendor/ddn/current/resource-manifest.json', str(Path(__file__).relative_to(ROOT))]
    proof = {'complete': False, 'interfaces': [], 'history_testing': 'not run',
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}}
    owned = None
    try:
        with server(output / 'fixture') as (route, _name, owned):
            oracle = _root_connection('mysql', route['port']); oracle.autocommit = True; cursor = oracle.cursor()
            try:
                cursor.execute('SELECT VERSION()'); proof['mysql_version'] = cursor.fetchone()[0]
                cursor.execute('CREATE DATABASE sr_osc'); cursor.execute('USE sr_osc')
                cursor.execute('CREATE TABLE evidence(id BIGINT UNSIGNED PRIMARY KEY,note VARCHAR(80),token VARCHAR(80))')
                cursor.execute("INSERT INTO evidence VALUES(18446744073709551615,'native 雪','private-value')")
                cursor.execute('CREATE TABLE effects(id INT PRIMARY KEY)')
                password = secrets.token_urlsafe(24); cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                app = setup_application(output)
                for use_c in (False, True):
                    sid, target, _raw = registration(app, route, password, use_c)
                    with app.test_request_context('/'):
                        registered = Server.query.get(sid); uid = User.query.first().id
                        endpoint = url_for('NODE-server.cde_workspace_id', gid=registered.servergroup_id, sid=sid)
                        scope = {'engine': 'mysql', 'endpoint_id': str(registered.endpoint_profile.id), 'database_target_id': target}
                    client = app.test_client()
                    with client.session_transaction() as session:
                        session['_user_id'], session['_fresh'] = str(uid), True
                    def post(action, **data):
                        reply = client.post(endpoint, json={'action': action, 'database_target_id': target, **data})
                        result = reply.get_json(); assert reply.status_code == 200 and result.get('success'), result
                        assert reply.headers['Cache-Control'] == 'no-store'
                        return result['data']
                    def asset(method, path, body=None, expected=200):
                        reply = client.open('/cdeadmin/api/projects/' + path, method=method, json=body)
                        result = reply.get_json(); assert reply.status_code == expected, result
                        if expected == 200:
                            assert result['success']; return result['data']
                        assert not result.get('success'); return result
                    project = 'notebook-' + ('c' if use_c else 'pure')
                    asset('PUT', project, {'name': project})
                    source = 'SELECT id,note,token FROM evidence'
                    content = {'format': FORMAT, 'scope': scope, 'cells': [
                        {'id': 'note', 'kind': 'note', 'source': 'Native investigation; notes are inert.'},
                        {'id': 'query', 'kind': 'sql', 'source': source, 'snapshot': None},
                        {'id': 'mutation', 'kind': 'sql', 'source': 'INSERT INTO effects VALUES(2)', 'snapshot': None}]}
                    body = {'asset_type': ASSET_TYPE, 'schema_name': ASSET_TYPE, 'schema_version': 1,
                        'name': 'Native investigation', 'path': 'notebooks/investigation.json', 'content': content, 'expected_version': 0}
                    saved = asset('PUT', project + '/assets/investigation', body)
                    assert saved['version'] == 1
                    for _ in range(2):
                        assert asset('GET', project + '/assets/investigation')['content'] == content
                    portable = model('portable', saved['content']); assert portable['scope'] is None
                    cursor.execute('SELECT COUNT(*) FROM effects'); assert cursor.fetchone()[0] == 0
                    classes = []; original = MySQLDBAPIClient._connect
                    def observed(instance, *args, **kwargs):
                        connection = original(instance, *args, **kwargs); classes.append(type(connection).__name__); return connection
                    with patch.object(MySQLDBAPIClient, '_connect', observed):
                        session_id = post('open_session', language_profile='mysql-sql')['session_id']
                        def execute(sql):
                            started = post('execute', session_id=session_id, source=sql, parameters=[], history_sensitive=True)
                            limit = time.monotonic() + 30
                            while time.monotonic() < limit:
                                reply = post('poll', occurrence_id=started['occurrence_id'], buffer_rows=100)
                                if reply['occurrence']['operation']['terminal']:
                                    native = reply['occurrence'].get('result', {}).get('extensions', {}).get('mysql', {}).get('payload', {})
                                    assert not native.get('error'), native.get('error')
                                    return reply['rendered_result']
                                time.sleep(.02)
                            raise TimeoutError('Native notebook statement did not finish')
                        rendered = execute(source)
                        snapshot = model('snapshot', {'rendered': rendered, 'source': source, 'scope': scope, 'policies': {'0': 'retain', '1': 'retain', '2': 'redact'}})
                        assert snapshot['rows'] == [['18446744073709551615', 'native 雪', '[REDACTED]']], snapshot
                        content['cells'][1]['snapshot'] = snapshot; body['expected_version'] = 1
                        saved = asset('PUT', project + '/assets/investigation', body); assert saved['version'] == 2
                        asset('PUT', project + '/assets/investigation', body, expected=409)
                        assert asset('GET', project + '/assets/investigation?version=1')['content']['cells'][1]['snapshot'] is None
                        assert asset('GET', project + '/assets/investigation')['content']['cells'][1]['snapshot'] == snapshot
                        shared = model('portable', saved['content']); encoded = json.dumps(shared)
                        assert all(s not in encoded for s in (password, scope['endpoint_id'], target, 'private-value', 'session_id', 'result_id'))
                        asset('PUT', project + '/assets/imported', {**body, 'path': 'notebooks/imported.json', 'name': 'Imported investigation', 'expected_version': 0, 'content': shared})
                        bad = {**shared, 'password': password}
                        asset('PUT', project + '/assets/rejected', {**body, 'expected_version': 0, 'content': bad}, expected=400)
                        cursor.execute('SELECT COUNT(*) FROM effects'); assert cursor.fetchone()[0] == 0
                        # Storage and sharing must not commit a user's pending work.
                        post('transaction_action', session_id=session_id, transaction_action='autocommit_off')
                        execute('INSERT INTO effects VALUES(1)'); execute('SAVEPOINT notebook_guard')
                        asset('GET', project + '/assets/investigation'); model('portable', shared)
                        execute('ROLLBACK TO SAVEPOINT notebook_guard')
                        cursor.execute('SELECT COUNT(*) FROM effects'); assert cursor.fetchone()[0] == 0
                        post('transaction_action', session_id=session_id, transaction_action='rollback')
                        post('close_session', session_id=session_id)
                    expected = 'CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection'
                    assert classes and set(classes) == {expected}, classes
                    proof['interfaces'].append({'use_c': use_c, 'native_interface': expected, 'complete': True, 'checks': [
                        'authenticated-save-open-revisions-import-export-never-execute-stored-DML',
                        'explicit-native-session-execution-exact-unsigned64-Unicode-and-redacted-bounded-snapshot',
                        'optimistic-revision-conflict-preserved-and-prior-revision-retrievable',
                        'portable-binding-session-result-credential-and-native-value-exclusion',
                        'pending-native-transaction-savepoint-and-independent-visibility-preserved']})
                if browser_binary:
                    proof['browser'] = browser(app, output, sid, password, project, browser_binary, driver_binary)
                proof['complete'] = True
            finally:
                cursor.close(); oracle.close()
    finally:
        proof['owned_server_stopped'] = bool(owned and owned.get('owned_server_stopped'))
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def browser(app, output, sid, password, project, binary, driver_binary):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.common.exceptions import StaleElementReferenceException
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, wait_for_tree_item, invoke_context_action, complete_endpoint_prompt
    http = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start(); driver = None
    try:
        options = webdriver.ChromeOptions(); options.binary_location = binary
        for flag in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1900,1800'):
            options.add_argument(flag)
        options.add_argument('--user-data-dir=' + str(output / 'browser-profile'))
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
        options.add_experimental_option('prefs', {'download.default_directory': str(output / 'downloads'), 'download.prompt_for_download': False})
        driver = webdriver.Chrome(options=options, service=Service(driver_binary)); driver.get('http://127.0.0.1:' + str(http.server_port) + '/browser/')
        wait = WebDriverWait(driver, 90, ignored_exceptions=(StaleElementReferenceException,))
        ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'MySQL')
        def owned(b):
            return next((n for n in b.find_elements(By.CSS_SELECTOR, '.file-name') if n.is_displayed() and b.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', n, sid)), None)
        label = wait.until(owned).text; expand(wait, label, ('Connectors', 'MySQL'))
        if complete_endpoint_prompt(driver, password, timeout=5): expand(wait, label, ('Connectors', 'MySQL'))
        database = wait_for_tree_item(wait, 'sr_osc', ('Connectors', 'MySQL', label))
        invoke_context_action(wait, driver, database, ('Database workspace', 'Open MySQL SQL editor...'), handle_endpoint_prompt=False)
        complete_endpoint_prompt(driver, password, timeout=15)
        def click(text):
            node = wait.until(lambda b: next((e for e in b.find_elements(By.TAG_NAME, 'button') if e.is_displayed() and e.is_enabled() and e.text == text), None))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});', node); node.click()
        def field(text):
            label = wait.until(lambda b: next((e for e in b.find_elements(By.TAG_NAME, 'label') if e.is_displayed() and e.text == text), None))
            return driver.find_element(By.ID, label.get_attribute('for'))
        def select(text, choice):
            node = wait.until(lambda b: (e if (e := field(text)).is_enabled() and e.get_attribute('aria-disabled') != 'true' else None))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});', node); node.click()
            wait.until(lambda b: next((e for e in b.find_elements(By.CSS_SELECTOR, '[role="option"]') if e.is_displayed() and e.text == choice), None)).click()
        click('SQL notebook'); select('Notebook project', project); select('Saved notebook', 'Native investigation (v2)')
        wait.until(lambda b: 'Loaded revision 2. No SQL executed.' in b.find_element(By.TAG_NAME, 'body').text)
        select('Notebook cell', '2. sql: SELECT id,note,token FROM evidence')
        click('Run selected SQL cell')
        wait.until(lambda b: any(e.is_displayed() for e in b.find_elements(By.XPATH, '//button[normalize-space()="Retain reviewed page snapshot"]')))
        select('Snapshot id', 'Retain value'); select('Snapshot note', 'Retain value'); select('Snapshot token', 'Redact')
        click('Retain reviewed page snapshot'); click('Save notebook revision')
        wait.until(lambda b: 'Saved notebook revision 3.' in b.find_element(By.TAG_NAME, 'body').text)
        retained = driver.find_element(By.CSS_SELECTOR, '[aria-label="Retained notebook snapshot"]').text
        assert '[REDACTED]' in retained and '18446744073709551615' in retained and 'private-value' not in retained
        review = driver.find_element(By.XPATH, '//label[contains(.,"I reviewed notes, SQL literals")]')
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', review); review.click(); click('Export shareable notebook')
        downloaded = output / 'downloads/investigation.sql-notebook.json'
        wait.until(lambda _b: downloaded.is_file())
        exported = json.loads(downloaded.read_text()); assert exported['scope'] is None and exported['cells'][1]['snapshot']['scope'] is None
        assert password not in downloaded.read_text() and 'private-value' not in downloaded.read_text()
        driver.find_element(By.CSS_SELECTOR, '[aria-label="Import SQL notebook file"]').send_keys(str(downloaded))
        wait.until(lambda b: 'Imported an unbound draft.' in b.find_element(By.TAG_NAME, 'body').text)
        select('Notebook cell', '2. sql: SELECT id,note,token FROM evidence')
        run = driver.find_element(By.XPATH, '//button[normalize-space()="Run selected SQL cell"]'); assert not run.is_enabled()
        click('Bind to this SQL editor (clear snapshots)')
        assert not driver.find_elements(By.CSS_SELECTOR, '[aria-label="Retained notebook snapshot"]')
        driver.save_screenshot(str(output / 'native-notebook.png'))
        errors = [row for row in driver.get_log('browser') if row['level'] == 'SEVERE']; assert not errors, errors
        return {'complete': True, 'version': driver.capabilities['browserVersion'], 'console_errors': errors, 'checks': [
            'built-native-editor-load-and-explicit-cell-run', 'built-column-retention-redaction-and-revision-save',
            'built-portable-download-and-inert-import', 'built-unbound-run-refusal-and-explicit-rebinding-clears-snapshots']}
    except Exception:
        if driver:
            driver.save_screenshot(str(output / 'browser-failure.png'))
            (output / 'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME, 'body').text)
        raise
    finally:
        if driver: driver.quit()
        http.shutdown(); thread.join(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True)
    parser.add_argument('--browser-binary'); parser.add_argument('--driver-binary')
    args = parser.parse_args(); qualify(args.output, args.browser_binary, args.driver_binary)
