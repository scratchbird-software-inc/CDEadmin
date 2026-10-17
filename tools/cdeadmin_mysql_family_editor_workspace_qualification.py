"""Native nonexecuting checks through the authenticated workspace and query UI."""
import argparse
import builtins
import hashlib
import json
from pathlib import Path
import secrets
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(engine, output, browser_binary=None, driver_binary=None):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside application source')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    proof = {'complete': False, 'engine': engine, 'history_testing': 'not run',
             'interfaces': [], 'source_sha256': {}}
    for name in ('web/pgadmin/cdeadmin/providers/native_editor.py',
                 'web/pgadmin/cdeadmin/providers/mysql_family/prepare_classification.py',
                 'web/pgadmin/cdeadmin/data_studio/language_tools.py',
                 'web/pgadmin/cdeadmin/data_studio/mysql_quoting.py',
                 'web/pgadmin/static/js/cdeadmin_ui/editors/nativeLexing.js',
                 'web/pgadmin/static/js/cdeadmin_ui/editors/nativeFormatting.js',
                 str(Path(__file__).relative_to(ROOT))):
        proof['source_sha256'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False
    for name, filename in {'DATA_DIR': 'app', 'SQLITE_PATH': 'app/application.db',
                           'SESSION_DB_PATH': 'app/sessions', 'STORAGE_DIR': 'app/storage',
                           'LOG_FILE': 'app/application.log', 'AZURE_CREDENTIAL_CACHE_DIR': 'app/azure',
                           'CDEADMIN_OPERATION_STORE_PATH': 'app/operations.json'}.items():
        setattr(config, name, str(output / filename))
    from pgadmin import create_app
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from flask import url_for
    from mysql_qualification_support import server, _root_connection
    if engine == 'mariadb':
        from mariadb_qualification_support import server
    app = create_app('ScratchRobin-native-editor-workspace')
    app.PGADMIN_RUNTIME = False; app.PGADMIN_INT_KEY = ''; app.run_before_app_start()
    client = app.test_client()
    try:
        with server(output / 'fixture') as (route, _name, owned):
            connection = _root_connection(engine, route['port']); connection.autocommit = True
            query = connection.cursor()
            try:
                password = secrets.token_urlsafe(32)
                query.execute("CREATE USER 'sr_editor_operator'@'%' IDENTIFIED BY %s", (password,))
                query.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_editor_operator'@'%' WITH GRANT OPTION")
                query.execute('CREATE DATABASE sr_workspace')
                query.execute('CREATE TABLE sr_workspace.pending(id INT PRIMARY KEY)')
                query.execute('INSERT INTO sr_workspace.pending VALUES(1)')
                for pure in ([True, False] if engine == 'mysql' else [None]):
                    selected = {**route, 'database': 'sr_workspace', 'sql_mode': 'ANSI_QUOTES',
                                'user': 'sr_editor_operator', 'credential_kinds': ['database_password']}
                    if pure is not None: selected['use_pure'] = pure
                    with app.test_request_context('/'):
                        user = User.query.first(); uid = user.id
                        group = ServerGroup.query.filter_by(user_id=uid).first()
                        app.blueprints['NODE-engine_type'].connector_visibility[engine].set(True, user_id=uid)
                        registration = Server(user_id=uid, servergroup_id=group.id,
                            name='Owned ' + engine + ' source checker ' + str(pure),
                            host=route['host'], port=route['port'], username='sr_editor_operator',
                            maintenance_db='sr_workspace', save_password=0)
                        registration._cde_endpoint_registration = registration_profile(engine + '-native')
                        registration._cde_endpoint_route_configuration = selected
                        db.session.add(registration); db.session.commit(); sid = registration.id
                        target = str(uuid.uuid4())
                        db.session.add(EndpointDatabaseTarget(id=target, endpoint_id=registration.endpoint_profile.id,
                            display_name='sr_workspace', database='sr_workspace', configuration='{}', active=1))
                        db.session.commit()
                        verify = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=sid)
                        url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=sid)
                    with client.session_transaction() as session:
                        session['_user_id'] = str(uid); session['_fresh'] = True
                    verified = client.post(verify, json={'password': password}).get_json(); assert verified.get('success'), verified
                    def post(action, **data):
                        response = client.post(url, json={'action': action, 'database_target_id': target, **data})
                        result = response.get_json()
                        assert response.status_code == 200 and result.get('success'), result
                        return result['data']
                    opened = post('open_session', language_profile=engine + '-sql')
                    session_id = opened['session_id']; checks = []
                    cases = [('valid-body', 'CREATE PROCEDURE not_created() BEGIN SELECT 1; END', True),
                             ('invalid-body', 'CREATE PROCEDURE not_created() BEGIN SELEC 1; END', False),
                             ('missing-context', 'SELECT * FROM absent_relation', None),
                             ('backslash-identifier', 'SELECT 1 AS `back\\`, %s', True)]
                    if engine == 'mysql':
                        cases += [('role', "CREATE ROLE 'sr_not_created'", True),
                                  ('transaction', 'START TRANSACTION', True),
                                  ('component', "INSTALL COMPONENT 'file://sr_absent'", True),
                                  ('commented-invalid-body', '# comment\rCREATE PROCEDURE p() BEGIN SELEC 1; END', None)]
                        cases += [('dollar-library', 'CREATE LIBRARY not_created LANGUAGE JAVASCRIPT AS $tag$// %s;\nexport const value=1;$tag$', True),
                                  ('unterminated-dollar-library', 'CREATE LIBRARY not_created LANGUAGE JAVASCRIPT AS $tag$export const value=1;', False)]
                    for name, source, expected in cases:
                        result = post('source_validate', session_id=session_id, source=source)
                        assert result['grammar_valid'] is expected, result
                        checks.append({'name': name, 'grammar_valid': expected,
                                       'authority': result['authority'], 'parser_version': result['parser_version']})
                    framed = post('source_validate', session_id=session_id, script=True,
                                  source='SELECT 1 AS `back\\`; SELECT 2;')
                    assert framed['script_ready'] and framed['grammar_valid'] is True and len(framed['statements']) == 2
                    if engine == 'mysql':
                        def execute(source, parameters):
                            started = post('execute', session_id=session_id, source=source,
                                           parameters=parameters, history_sensitive=True)
                            deadline = time.monotonic() + 20; rows = []
                            while time.monotonic() < deadline:
                                observed = post('poll', occurrence_id=started['occurrence_id'])['occurrence']
                                payload = (observed.get('result') or {}).get('extensions', {}).get('mysql', {}).get('payload', {})
                                rows.extend(payload.get('rows') or [])
                                if observed['operation']['terminal']: return rows, payload
                                time.sleep(.05)
                            raise TimeoutError('Native parameter workspace execution')
                        text = 'DELIMITER $$\nnative HTTP binding'
                        rows, result = execute("SELECT '%s' AS literal, %(value)s AS bound_value", {'value':text})
                        assert rows == [['%s',text]] and not result.get('error'), result
                        rows, result = execute('INSERT INTO pending VALUES(%s)', [99,100])
                        assert result['error']['query_dispatch'] == 'not_started' and not result['session_reuse_blocked']
                        rows, result = execute('SELECT COUNT(*) FROM pending', {})
                        assert rows == [[1]] and not result.get('error')
                        checks.append({'name':'native-HTTP-literal-bindings-execution-refusal-and-session-reuse','passed':True})
                    post('close_session', session_id=session_id)
                    if browser_binary and pure is not False:
                        proof['browser'] = browser(app, output, engine, sid, browser_binary, driver_binary, password)
                    query.execute('SELECT COUNT(*) FROM sr_workspace.pending'); assert query.fetchone() == (1,)
                    query.execute("SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA='sr_workspace'")
                    assert query.fetchone() == (0,)
                    if engine == 'mysql':
                        query.execute("SELECT COUNT(*) FROM mysql.user WHERE User='sr_not_created'")
                        assert query.fetchone() == (0,)
                        query.execute("SELECT COUNT(*) FROM information_schema.LIBRARIES WHERE LIBRARY_SCHEMA='sr_workspace'")
                        assert query.fetchone() == (0,)
                    proof['interfaces'].append({'use_pure': pure, 'checks': checks,
                        'native_two_statement_script_checked': True, 'submitted_ddl_not_executed': True})
            finally:
                query.close(); connection.close()
        proof.update(complete=owned['owned_server_stopped'], owned_server_stopped=owned['owned_server_stopped'])
    finally:
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    assert proof['complete']
    return proof


def browser(app, output, engine, sid, binary, driver_binary, password):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import StaleElementReferenceException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, wait_for_tree_item, invoke_context_action, complete_endpoint_prompt, fill_fields
    from cdeadmin_sqlite_query_ui_gate import _set_query, _run_query
    from cdeadmin_firebird_query_ui_gate import _query_editor
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
        title = 'MySQL' if engine == 'mysql' else 'MariaDB'
        ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, title)
        def owned(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name')
                if node.is_displayed() and browser.execute_script(
                    'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',
                    node, sid)), None)
        label = wait.until(owned).text
        expand(wait, label, ('Connectors', title))
        database = wait_for_tree_item(wait, 'sr_workspace', ('Connectors', title, label))
        invoke_context_action(wait, driver, database, ('Database workspace', 'Open ' + title + ' SQL editor...'), handle_endpoint_prompt=False)
        assert complete_endpoint_prompt(driver, password, timeout=15)
        summary = wait.until(lambda d: next((n for n in d.find_elements(By.TAG_NAME, 'summary') if n.is_displayed() and n.text == 'Source tools'), None))
        summary.click(); checks = []
        cases = [
            ('valid-body', 'CREATE PROCEDURE not_created() BEGIN SELECT 1; END', 'accepted by the reported parser'),
            ('invalid-body', 'CREATE PROCEDURE not_created() BEGIN SELEC 1; END', 'rejected'),
            ('valid-control', 'START TRANSACTION', 'accepted by the reported parser'),
            ('invalid-control', 'START TRANSACTION TRAILING_INVALID +', 'rejected')]
        literal='$tag$// %s;\nexport const value=1;$tag$'
        if engine=='mysql':
            cases += [('dollar-library','CREATE  LIBRARY not_created LANGUAGE JAVASCRIPT AS '+literal,'accepted by the reported parser'),
                      ('unterminated-dollar-library','CREATE LIBRARY not_created LANGUAGE JAVASCRIPT AS $tag$export const value=1;','rejected')]
        for name, source, expected in cases:
            _set_query(driver, wait, source)
            def click(browser, label):
                for node in browser.find_elements(By.TAG_NAME, 'button'):
                    if node.is_displayed() and node.is_enabled() and node.text == label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});', node)
                        node.click(); return True
                return False
            wait.until(lambda browser:click(browser,'Check source'))
            wait.until(lambda d: any('SQL grammar: ' + expected + '.' in n.text for n in d.find_elements(By.CSS_SELECTOR, '[role="status"]')))
            checks.append({'name': name, 'displayed_native_result': expected})
            if name=='dollar-library':
                wait.until(lambda browser:click(browser,'Format native source'))
                def formatted(browser):
                    editor=_query_editor(browser)
                    if editor is None:return False
                    value=browser.execute_script('return [...arguments[0].querySelectorAll(".cm-line")].map(n=>n.textContent).join("\\n");',editor)
                    return value if value!=source and literal in value else False
                value=wait.until(formatted)
                assert literal in value
                checks.append({'name':'dollar-library-format','native_literal_bytes_preserved':True})
        if engine == 'mysql':
            options = wait.until(lambda browser: browser.find_element(By.XPATH,'//*[@role="tab" and normalize-space()="Engine options"]'))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',options); options.click()
            fill_fields(wait, ['Query parameters (JSON object or array)=' + json.dumps({'value':'DELIMITER $$\nnative UI binding'})])
            sensitive = wait.until(lambda browser: browser.find_element(By.XPATH,
                '//label[contains(.,"Omit this sensitive source from SQL history")]'))
            if not sensitive.find_element(By.CSS_SELECTOR,'input').is_selected():
                driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',sensitive); sensitive.click()
            data = wait.until(lambda browser: browser.find_element(By.XPATH,'//*[@role="tab" and normalize-space()="Data Output"]'))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',data); data.click()
            _run_query(driver,wait,"SELECT '%s' AS literal, %(value)s AS bound_value",'%s','MySQL',output)
            wait.until(lambda browser:any(node.is_displayed() and node.text=='DELIMITER $$\nnative UI binding'
                for node in browser.find_elements(By.CSS_SELECTOR,'[role="gridcell"]')))
            checks.append({'name':'native-browser-JSON-bindings-and-literal-placeholder-execution','passed':True})
        driver.save_screenshot(str(output / 'native-checking.png'))
        errors = [row for row in driver.get_log('browser') if row['level'] == 'SEVERE']
        assert not errors, errors
        return {'version': driver.capabilities['browserVersion'], 'checks': checks, 'console_errors': errors}
    finally:
        if driver is not None: driver.quit()
        http.shutdown(); thread.join(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('mysql', 'mariadb'), required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--browser-binary'); parser.add_argument('--driver-binary')
    args = parser.parse_args()
    qualify(args.engine, args.evidence, args.browser_binary, args.driver_binary)
