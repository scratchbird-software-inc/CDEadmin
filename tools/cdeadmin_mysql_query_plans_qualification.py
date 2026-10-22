"""Qualify native MySQL JSON/TREE/analyze plans through the workspace and GUI."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output, browser_binary=None, driver_binary=None):
    import config  # noqa: F401
    from mysql_qualification_support import server, _root_connection
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Native evidence belongs outside application source')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    paths = [str(Path(__file__).relative_to(ROOT)), 'tools/mysql_query_plan_probe.cjs',
             'web/pgadmin/static/js/Dialogs/mysqlQueryPlan.js',
             'web/pgadmin/static/js/Dialogs/MySQLQueryPlan.jsx',
             'web/pgadmin/static/js/Dialogs/ProviderWorkspaceContent.jsx',
             'web/pgadmin/cdeadmin/providers/mysql_family/provider.py']
    proof = {'complete': False, 'history_testing': 'not run', 'interfaces': [],
             'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}}
    owned = None
    try:
        with server(output / 'fixture') as (route, _name, owned):
            oracle = _root_connection('mysql', route['port'])
            oracle.autocommit = True
            query = oracle.cursor()
            try:
                query.execute('CREATE DATABASE sr_plans CHARACTER SET utf8mb4')
                query.execute('CREATE TABLE sr_plans.t(id INT PRIMARY KEY, label VARCHAR(80), parent_id INT, KEY(parent_id))')
                query.executemany('INSERT INTO sr_plans.t VALUES(%s,%s,%s)',
                                  [(1, 'native café 雪', None), (2, 'second', 1), (3, 'third', 1)])
                password = secrets.token_urlsafe(24)
                query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                app = setup_application(output)
                cases = []
                for use_c in (False, True):
                    interface, saved, sid = workspace(app, output, route, password, use_c)
                    proof['interfaces'].append(interface)
                    cases.extend(saved)
                probe = subprocess.run(['node', str(ROOT / 'tools/mysql_query_plan_probe.cjs')],
                                       input=json.dumps(cases), text=True, capture_output=True, cwd=ROOT, check=True)
                proof['production_normalizer'] = json.loads(probe.stdout)
                assert proof['production_normalizer']['complete']
                if browser_binary:
                    proof['browser'] = browser(app, output, sid, password, browser_binary, driver_binary)
                proof['complete'] = True
            finally:
                query.close()
                oracle.close()
    finally:
        proof['owned_server_stopped'] = bool(owned and owned['owned_server_stopped'])
        proof['complete'] = proof['complete'] and proof['owned_server_stopped']
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def workspace(app, output, route, password, use_c):
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, _create_client
    from pgadmin.cdeadmin.security import SecretLease
    from types import SimpleNamespace
    selected = {**route, 'database': 'sr_plans', 'autocommit': True, 'use_pure': not use_c}
    native = _create_client(MYSQL_PROFILE, SimpleNamespace(
        acquire_secret=lambda *_args: SecretLease(password.encode('utf8'))), SimpleNamespace())
    try:
        handle = native.open_session({'route': {**selected,
            'credential_reference_id': 'owned-native-plan-password', 'principal_reference': 'owned-native-plan-operator'}})
        connection_class = type(handle).__name__
        assert connection_class == ('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')
        native.close_session(handle)
    finally:
        native.close()
    with app.test_request_context('/'):
        user = User.query.first()
        group = ServerGroup.query.filter_by(user_id=user.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=user.id)
        item = Server(user_id=user.id, servergroup_id=group.id, name='Owned native plans ' + str(use_c),
                      host=route['host'], port=route['port'], username='root', maintenance_db='sr_plans', save_password=0)
        item._cde_endpoint_registration = registration_profile('mysql-native')
        item._cde_endpoint_route_configuration = {**{k: v for k, v in selected.items() if k != 'password'},
                                                 'credential_kinds': ['database_password']}
        db.session.add(item)
        db.session.commit()
        target = str(uuid.uuid4())
        db.session.add(EndpointDatabaseTarget(id=target, endpoint_id=item.endpoint_profile.id,
                       display_name='sr_plans', database='sr_plans', configuration='{}', active=1))
        db.session.commit()
        sid, uid = item.id, user.id
        url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=sid)
        verify = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=sid)
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'], session['_fresh'] = str(uid), True
    assert client.post(verify, json={'password': password}).get_json()['success']

    def post(action, **data):
        response = client.post(url, json={'action': action, 'database_target_id': target, **data})
        value = response.get_json()
        if response.status_code != 200 or not value.get('success'):
            raise AssertionError('Native plan workspace request failed: ' + action + ' ' + json.dumps(value).replace(password, '<redacted>'))
        return value['data']

    session_id = post('open_session', language_profile='mysql-sql')['session_id']

    def execute(source, expected_error=None):
        occurrence = post('execute', session_id=session_id, source=source, parameters=[], history_sensitive=True)
        rows, rendered = [], None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            value = post('poll', occurrence_id=occurrence['occurrence_id'])
            occurrence = {**occurrence, **value['occurrence']}
            payload = value['occurrence'].get('result', {}).get('extensions', {}).get('mysql', {}).get('payload', {})
            if payload.get('has_page'):
                rows.extend(payload.get('rows', []))
            if value.get('rendered_result'):
                rendered = value['rendered_result']
            if value['occurrence']['operation']['terminal']:
                error = payload.get('error')
                if expected_error is None:
                    assert not error, error
                else:
                    assert error and error['errno'] == expected_error, error
                (output / 'last-execution.json').write_text(json.dumps({
                    'source': source, 'rows': rows, 'rendered': rendered,
                    'native_payload': payload, 'terminal_result': value['occurrence'].get('result'),
                }, indent=2) + '\n')
                return rows, rendered
            time.sleep(.01)
        raise TimeoutError('Native plan workspace execution did not finish')

    checks, cases = [], []
    source = 'SELECT a.id,b.label FROM t a JOIN t b ON b.parent_id=a.id WHERE a.id>=1'
    try:
        response = client.get(url, query_string={'database_target_id': target})
        assert response.status_code == 200 and response.get_json()['success']
        bootstrap = response.get_json()['data']
        language = next(x for x in bootstrap['languages'] if x['language_profile'] == 'mysql-sql')
        assert {x['source_template'] for x in language['query_plan_templates']} >= {
            'EXPLAIN FORMAT=JSON {source}', 'EXPLAIN FORMAT=TREE {source}',
            'EXPLAIN ANALYZE FORMAT=TREE {source}', 'EXPLAIN ANALYZE FORMAT=JSON {source}'}
        for version in (1, 2):
            execute('SET SESSION explain_json_format_version=' + str(version))
            rows, rendered = execute('EXPLAIN FORMAT=JSON ' + source)
            assert len(rows) == 1 and len(rows[0]) == 1, 'Native plan row shape: see last-execution.json'
            text = rows[0][0]
            parsed = json.loads(text)
            assert ('query_block' if version == 1 else 'query_plan') in parsed
            cases.append({'name': connection_class + '-JSON-' + str(version), 'native_text': text,
                          'format': 'JSON version ' + str(version), 'min_nodes': 2, 'rendered': rendered})
            checks.append('native-JSON-' + str(version) + '-through-authenticated-workspace')
        rows, rendered = execute('EXPLAIN ANALYZE FORMAT=JSON ' + source)
        assert len(rows) == 1 and 'query_plan' in json.loads(rows[0][0])
        cases.append({'name': connection_class + '-JSON-ANALYZE', 'native_text': rows[0][0],
                      'format': 'JSON version 2', 'actual': True, 'min_nodes': 2, 'rendered': rendered})
        checks.append('native-JSON-version-2-actual-measurements')
        execute('SET @sr_plan_probe=0')
        expression = 'SELECT @sr_plan_probe:=@sr_plan_probe+1 FROM t ORDER BY id'
        rows, rendered = execute('EXPLAIN FORMAT=TREE ' + expression)
        assert execute('SELECT @sr_plan_probe')[0] == [[0]]
        cases.append({'name': connection_class + '-TREE', 'native_text': rows[0][0], 'format': 'TREE', 'rendered': rendered})
        rows, rendered = execute('EXPLAIN ANALYZE FORMAT=TREE ' + expression)
        assert execute('SELECT @sr_plan_probe')[0] == [[3]]
        assert 'actual time=' in rows[0][0]
        cases.append({'name': connection_class + '-ANALYZE', 'native_text': rows[0][0], 'format': 'TREE', 'actual': True, 'rendered': rendered})
        checks.append('native-estimate-versus-explicit-analyze-session-effects')
        execute('EXPLAIN FORMAT=JSON SELECT * FROM missing_plan_table', expected_error=1146)
        assert execute('SELECT 7')[0] == [[7]]
        checks.append('native-error-and-subsequent-explicit-session-use')
        execute('SET autocommit=0')
        execute("INSERT INTO t VALUES(9,'pending',1)")
        execute('SAVEPOINT plan_guard')
        execute('EXPLAIN ANALYZE FORMAT=TREE SELECT * FROM t')
        execute('ROLLBACK TO SAVEPOINT plan_guard')
        execute('ROLLBACK')
        assert execute('SELECT COUNT(*) FROM t')[0] == [[3]]
        checks.append('analyze-does-not-imply-commit-or-rollback-and-savepoint-survives')
        (output / ('native-plans-' + str(use_c) + '.json')).write_text(json.dumps(cases, indent=2) + '\n')
        return {'complete': True, 'use_c': use_c, 'native_connection_class': connection_class, 'checks': checks}, cases, sid
    finally:
        post('close_session', session_id=session_id)


def browser(app, output, sid, password, binary, driver_binary):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, wait_for_tree_item, invoke_context_action, complete_endpoint_prompt
    from cdeadmin_sqlite_query_ui_gate import _set_query
    http = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.binary_location = binary
        for flag in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1800,1200'):
            options.add_argument(flag)
        options.add_argument('--user-data-dir=' + str(output / 'browser-profile'))
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        driver = webdriver.Chrome(options=options, service=Service(driver_binary))
        driver.get('http://127.0.0.1:' + str(http.server_port) + '/browser/')
        wait = WebDriverWait(driver, 90, ignored_exceptions=(StaleElementReferenceException,))
        ensure_data_explorer(wait)
        expand(wait, 'Connectors')
        expand(wait, 'MySQL')
        def owned(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', node, sid)), None)
        label = wait.until(owned).text
        expand(wait, label, ('Connectors', 'MySQL'))
        if complete_endpoint_prompt(driver, password, timeout=5):
            expand(wait, label, ('Connectors', 'MySQL'))
        database = wait_for_tree_item(wait, 'sr_plans', ('Connectors', 'MySQL', label))
        invoke_context_action(wait, driver, database, ('Database workspace', 'Open MySQL SQL editor...'), handle_endpoint_prompt=False)
        complete_endpoint_prompt(driver, password, timeout=15)
        def tab(label):
            node = wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '[role="tab"]')
                                                   if node.is_displayed() and node.text == label), None))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});', node)
            node.click()
        tab('Engine options')
        sensitive = wait.until(lambda browser: browser.find_element(By.XPATH, '//label[contains(.,"Omit this sensitive source from SQL history")]'))
        if not sensitive.find_element(By.CSS_SELECTOR, 'input').is_selected():
            sensitive.click()
        tab('Data Output')
        checks = []
        for title, kind in [('MySQL JSON query plan', 'JSON version 2'), ('MySQL TREE query plan', 'TREE'),
                            ('MySQL execution plan (executes query)', 'TREE'),
                            ('MySQL JSON execution plan (executes query)', 'JSON version 2')]:
            _set_query(driver, wait, 'SELECT a.id,b.label FROM t a JOIN t b ON b.parent_id=a.id WHERE a.id>=1')
            button = wait.until(lambda browser: next((b for b in browser.find_elements(By.TAG_NAME, 'button') if b.is_displayed() and b.is_enabled() and b.get_attribute('aria-label') == title), None))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});', button)
            button.click()
            graph = wait.until(lambda browser: next((n for n in browser.find_elements(By.CSS_SELECTOR, '[aria-label="Native MySQL operator graph"]') if n.is_displayed()), None))
            wait.until(lambda browser: kind in browser.find_element(By.CSS_SELECTOR, '[aria-label="MySQL query plan"]').text)
            assert len(graph.find_elements(By.CSS_SELECTOR, '[role="treeitem"]')) >= 2
            inspect = graph.find_element(By.CSS_SELECTOR, '[aria-label="Inspect operator 2"]')
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});', inspect)
            inspect.click()
            wait.until(lambda browser: 'inputs' in browser.find_element(By.CSS_SELECTOR, '[aria-label="Selected native operator"]').text
                       if kind == 'JSON version 2' else bool(browser.find_element(By.CSS_SELECTOR, '[aria-label="Selected native operator"]').text))
            raw = driver.find_element(By.CSS_SELECTOR, '[aria-label="Original MySQL plan text"]')
            text = driver.execute_script('return arguments[0].textContent;', raw)
            assert text and ('query_plan' in text if kind.startswith('JSON') else '->' in text)
            if title.endswith('(executes query)'):
                marker = 'actual time=' if kind == 'TREE' else '"actual_rows"'
                wait.until(lambda browser: marker in browser.execute_script(
                    'return arguments[0].textContent;', browser.find_element(By.CSS_SELECTOR, '[aria-label="Original MySQL plan text"]')))
            checks.append({'control': title, 'format': kind, 'native_text_available': True})
        driver.save_screenshot(str(output / 'native-query-plans.png'))
        errors = [row for row in driver.get_log('browser') if row['level'] == 'SEVERE']
        assert not errors, errors
        return {'complete': True, 'checks': checks, 'console_errors': errors}
    except Exception:
        if driver is not None:
            driver.save_screenshot(str(output / 'browser-failure.png'))
            (output / 'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME, 'body').text)
        raise
    finally:
        if driver is not None:
            driver.quit()
        http.shutdown()
        thread.join(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--browser-binary')
    parser.add_argument('--driver-binary')
    args = parser.parse_args()
    qualify(args.output, args.browser_binary, args.driver_binary)
