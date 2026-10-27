"""Native SQLite constructor HTTP and explorer creation qualification."""
import argparse
import builtins
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output, binary=None, driver_binary=None, *, fts_maintenance=False):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    proof = {'complete': False, 'native_sqlite_version': sqlite3.sqlite_version,
             'history_testing': 'not run', 'checks': [], 'source_sha256': {}}
    for relative in ('tools/cdeadmin_sqlite_virtual_constructor_qualification.py',
                     'web/pgadmin/cdeadmin/providers/sqlite/virtual_tables.py',
                     'web/pgadmin/cdeadmin/providers/sqlite/fts_maintenance.py',
                     'web/pgadmin/cdeadmin/providers/sqlite/driver.py',
                     'web/pgadmin/cdeadmin/providers/sqlite/sqlite_dialect_3_53_0.json',
                     'web/pgadmin/static/js/Dialogs/SQLiteSessionFTS.jsx',
                     'web/pgadmin/static/js/Dialogs/ProviderWorkspaceContent.jsx',
                     'web/pgadmin/cdeadmin/providers/sqlite/provider.py'):
        proof['source_sha256'][relative] = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False
    for name, filename in {'DATA_DIR': 'app', 'SQLITE_PATH': 'app/application.db', 'SESSION_DB_PATH': 'app/sessions',
                           'STORAGE_DIR': 'app/storage', 'LOG_FILE': 'app/application.log',
                           'AZURE_CREDENTIAL_CACHE_DIR': 'app/azure', 'CDEADMIN_OPERATION_STORE_PATH': 'app/operations.json'}.items():
        setattr(config, name, str(output / filename))
    from pgadmin import create_app
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from flask import url_for
    database = output / 'native.sqlite'
    with closing(sqlite3.connect(database)) as seed:
        seed.executescript("CREATE VIRTUAL TABLE base4 USING fts4(body); INSERT INTO base4 VALUES('native token'); "
                           "CREATE VIRTUAL TABLE base5 USING fts5(body); INSERT INTO base5 VALUES('native token');")
    app = create_app('ScratchRobin-native-sqlite-constructors')
    app.PGADMIN_RUNTIME = False; app.PGADMIN_INT_KEY = ''; app.run_before_app_start()
    client = app.test_client()
    try:
        assert sqlite3.sqlite_version == '3.53.0'
        with app.test_request_context('/'):
            user = User.query.first(); uid = user.id; group = ServerGroup.query.filter_by(user_id=uid).first()
            app.blueprints['NODE-engine_type'].connector_visibility['sqlite'].set(True, user_id=uid)
            server = Server(user_id=uid, servergroup_id=group.id, name='Owned SQLite constructor target', host=None,
                            port=1, username='', maintenance_db=str(database), save_password=0)
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
        assert client.post(verify_url, json={}).get_json().get('success')
        def post(action, request):
            response = client.post(url, json={'action': action, 'request': {'database_target_id': target, **request}})
            result = response.get_json()
            if response.status_code != 200 or not result.get('success'):
                (output / 'http-failure.json').write_text(json.dumps(result, indent=2))
                raise AssertionError('Native constructor HTTP failed: ' + action)
            return result['data']
        modules = [
            ('fts3', ['body'], {}), ('fts4', ['body'], {'prefix': [2, 3]}),
            ('fts5', ['body'], {'tokenizer': {'name': 'unicode61', 'arguments': ['remove_diacritics', '2']}}),
            ('rtree', ['id', 'x0', 'x1'], {'auxiliary_columns': ['label']}),
            ('rtree_i32', ['id', 'x0', 'x1'], {}), ('geopoly', ['label'], {}),
            ('fts4aux', [], {'table': 'base4'}), ('fts5vocab', [], {'table': 'base5', 'mode': 'instance'}),
            ('fts3tokenize', [], {'tokenizer': {'name': 'unicode61'}}), ('dbstat', [], {'database': 'main'}),
        ]
        proof['http'] = []
        for module, columns, options in modules:
            name = 'http_' + module
            request = {'resource_kind': 'fts-table' if module in {'fts3', 'fts4', 'fts5'} else 'virtual-table',
                       'operation_id': 'create', 'draft': {'name': name, 'module': module, 'columns': columns,
                                                         'module_options': options, 'parent': 'main'}}
            planned = post('visual_admin_plan', request)
            assert planned['state'] == 'ready' and planned['execution_available'], planned
            applied = post('visual_admin_apply', {key: planned[key] for key in ('plan_id', 'plan_digest')} | {'confirmed': True})
            assert applied['provider_result']['native_outcome'] == 'committed', applied
            operation = applied['control_operation']['operation_id']
            observed = post('visual_admin_operation_post_state', {'operation_id': operation})
            assert observed['post_state']['confirmed'], observed
            repeat = client.post(url, json={'action': 'visual_admin_apply', 'request': {'database_target_id': target,
                'plan_id': planned['plan_id'], 'plan_digest': planned['plan_digest'], 'confirmed': True}})
            assert repeat.status_code != 200 or not repeat.get_json().get('success')
            with closing(sqlite3.connect(database)) as observer:
                assert observer.execute('SELECT sql FROM sqlite_schema WHERE name=?', (name,)).fetchone()
                assert observer.execute('PRAGMA table_xinfo("' + name + '")').fetchall()
            proof['http'].append({'module': module, 'native_outcome': 'committed', 'fresh_post_state_confirmed': True, 'replay_refused': True})
        proof['checks'].append('authenticated-all-ten-native-constructors-preview-apply-fresh-post-state-no-replay')
        if fts_maintenance:
            from pgadmin.cdeadmin.providers.sqlite.provider import _resources
            proof['fts_maintenance'] = []
            for module in ('fts3', 'fts4', 'fts5'):
                name = 'http_' + module
                with closing(sqlite3.connect(database)) as observer:
                    observer.execute('INSERT INTO "' + name + '"(rowid,body) VALUES(9007199254740993,\'native 雪\')'); observer.commit()
                for operation in ('fts_optimize', 'fts_rebuild', 'fts_merge', 'fts_integrity_check'):
                    with closing(sqlite3.connect(database)) as observer:
                        resource = next(row for row in _resources(observer, {}) if row['display_name'] == name and row['resource_kind'] == 'fts-table')
                    planned = post('visual_admin_plan', {'resource_kind': 'fts-table', 'operation_id': operation,
                                   'target_resource': resource, 'draft': {'timeout_seconds': 30}})
                    applied = post('visual_admin_apply', {key: planned[key] for key in ('plan_id', 'plan_digest')} | {'confirmed': True})
                    receipt = applied['provider_result']['native_fts_maintenance']
                    assert receipt['native_outcome'] == 'committed' and receipt['native_integrity_verified'], receipt
                    refreshed = post('visual_admin_operation_refresh', {'operation_id': applied['control_operation']['operation_id']})
                    assert refreshed['provider_observation'] == receipt
                    with closing(sqlite3.connect(database)) as observer:
                        assert observer.execute('SELECT rowid,body FROM "' + name + '" WHERE "' + name + '" MATCH \'native\'').fetchall() == [(9007199254740993, 'native 雪')]
                    proof['fts_maintenance'].append({'module': module, 'operation': operation, 'native_outcome': receipt['native_outcome']})
            proof['checks'].append('authenticated-native-fts3-fts4-fts5-index-maintenance-and-live-operation-observations')
        if binary:
            proof['browser'] = browser(app, output, sid, database, binary, driver_binary, fts_maintenance=fts_maintenance)
            proof['checks'].append('explorer-native-module-options-preview-confirm-apply-independent-spatial-query')
        proof['complete'] = True
    finally:
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def browser(app, output, sid, database, binary, driver_binary, *, fts_maintenance=False):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import StaleElementReferenceException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import (ensure_data_explorer, expand, wait_for_tree_item,
                                      invoke_context_action, fill_fields, visible_named_control)
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
        def enabled(label):
            return wait.until(lambda b: next((node for node in [visible_named_control(b, label)] if node and node.is_enabled()), None))
        ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'SQLite')
        def owned(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', node, sid)), None)
        label = wait.until(owned).text; expand(wait, label, ('Connectors', 'SQLite'))
        expand(wait, 'native.sqlite', ('Connectors', 'SQLite', label))
        folder = wait_for_tree_item(wait, 'Virtual tables', ('Connectors', 'SQLite', label, 'native.sqlite'))
        invoke_context_action(wait, driver, folder, ('New Virtual table',), handle_endpoint_prompt=False)
        fill_fields(wait, ['Name=browser_spatial', 'Native module=rtree_i32',
                          'Module columns=["id","x0","x1"]', 'Native constructor options={"auxiliary_columns":["label"]}'])
        enabled('Validate and preview').click()
        preview = wait.until(lambda b: next((node for node in b.find_elements(By.CSS_SELECTOR, '[aria-label="Provider plan preview"]') if node.is_displayed()), None))
        plan = json.loads(preview.text)
        assert 'rtree_i32' in plan['command_preview']['statements'][0]['source']
        assert '+"label"' in plan['command_preview']['statements'][0]['source']
        checkbox = visible_named_control(driver, 'I confirm this provider-planned operation.')
        if checkbox: driver.execute_script('arguments[0].click()', checkbox)
        enabled('Apply provider plan').click()
        result_node = wait.until(lambda b: next((node for node in b.find_elements(By.CSS_SELECTOR, '[aria-label="Provider operation result"]') if node.is_displayed()), None))
        result = json.loads(result_node.text)
        assert result['native_outcome'] == 'committed', result
        with closing(sqlite3.connect(database)) as observer:
            observer.execute("INSERT INTO browser_spatial VALUES(1,0,1,'browser native')")
            assert observer.execute('SELECT label FROM browser_spatial WHERE x0<=0 AND x1>=0').fetchall() == [('browser native',)]
        if fts_maintenance:
            from cdeadmin_firebird_ui_form_gate import close_workspace_with_keyboard
            close_workspace_with_keyboard(driver, wait)
            expand(wait, 'Fts tables', ('Connectors', 'SQLite', label, 'native.sqlite'))
            resource = wait_for_tree_item(wait, 'http_fts5', ('Connectors', 'SQLite', label, 'native.sqlite', 'Fts tables'))
            invoke_context_action(wait, driver, resource, ('Object operations', 'Rebuild FTS index...'), handle_endpoint_prompt=False)
            enabled('Continue').click()
            enabled('Validate and preview').click()
            preview = wait.until(lambda b: next((node for node in b.find_elements(By.CSS_SELECTOR, '[aria-label="Provider plan preview"]') if node.is_displayed()), None))
            plan = json.loads(preview.text)
            assert "VALUES('rebuild')" in plan['command_preview']['statements'][0]['source']
            checkbox = visible_named_control(driver, 'I confirm this provider-planned operation.')
            if checkbox: driver.execute_script('arguments[0].click()', checkbox)
            enabled('Apply provider plan').click()
            result_node = wait.until(lambda b: next((node for node in b.find_elements(By.CSS_SELECTOR, '[aria-label="Provider operation result"]') if node.is_displayed()), None))
            result = json.loads(result_node.text)
            assert result['native_fts_maintenance']['native_outcome'] == 'committed', result
            with closing(sqlite3.connect(database)) as observer:
                assert observer.execute("SELECT rowid,body FROM http_fts5 WHERE http_fts5 MATCH 'native'").fetchall() == [(9007199254740993, 'native 雪')]
            close_workspace_with_keyboard(driver, wait)
            database_node = wait_for_tree_item(wait, 'native.sqlite', ('Connectors', 'SQLite', label))
            invoke_context_action(wait, driver, database_node, ('Database workspace', 'Open SQLite SQL editor...'), handle_endpoint_prompt=False)
            from cdeadmin_sqlite_query_ui_gate import _run_query
            _run_query(driver, wait, "INSERT INTO http_fts5(rowid,body) VALUES(9007199254740995,'pending native session') RETURNING body", 'pending native session', 'SQLite', output)
            driver.find_element(By.XPATH, '//*[@role="tab" and normalize-space()="Engine options"]').click()
            summary = wait.until(lambda b: b.find_element(By.XPATH, '//summary[normalize-space()="SQLite session FTS maintenance"]'))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});', summary); summary.click()
            wait.until(lambda b: visible_named_control(b, 'Inspect session FTS tables')).click()
            selector = wait.until(lambda b: visible_named_control(b, 'Session FTS table'))
            wait.until(lambda _b: selector.is_enabled()); selector.click()
            wait.until(lambda b: next((node for node in b.find_elements(By.CSS_SELECTOR, '[role="option"]') if node.is_displayed() and node.text.strip() == 'main / http_fts5'), None)).click()
            enabled('Validate and preview').click()
            preview = wait.until(lambda b: next((node for node in b.find_elements(By.CSS_SELECTOR, '[aria-label="Provider plan preview"]') if node.is_displayed()), None))
            assert "VALUES('flush')" in json.loads(preview.text)['command_preview']['statements'][0]['source']
            checkbox = enabled('I confirm this provider-planned operation.'); driver.execute_script('arguments[0].click()', checkbox)
            enabled('Apply provider plan').click()
            result_node = wait.until(lambda b: next((node for node in b.find_elements(By.CSS_SELECTOR, '[aria-label="Provider operation result"]') if node.is_displayed()), None))
            assert json.loads(result_node.text)['native_fts_maintenance']['native_outcome'] == 'staged'
            with closing(sqlite3.connect(database)) as observer:
                assert observer.execute('SELECT count(*) FROM http_fts5 WHERE rowid=9007199254740995').fetchone() == (0,)
            enabled('commit').click()
            def committed(_browser):
                with closing(sqlite3.connect(database)) as observer:
                    return observer.execute('SELECT body FROM http_fts5 WHERE rowid=9007199254740995').fetchall() == [('pending native session',)]
            wait.until(committed)
            enabled('Read session FTS operation receipts').click()
            wait.until(lambda b: any('"native_outcome": "staged"' in node.text for node in b.find_elements(By.TAG_NAME, 'pre')))
        driver.save_screenshot(str(output / 'native-constructor.png'))
        errors = [row for row in driver.get_log('browser') if row.get('level') == 'SEVERE']
        (output / 'browser-console.json').write_text(json.dumps(errors, indent=2)); assert not errors
        return {'complete': True, 'console_errors': 0, 'module': 'rtree_i32', 'native_query_confirmed': True, 'fts_maintenance': fts_maintenance,
                'retained_fts_flush_and_explicit_commit': fts_maintenance}
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
    parser.add_argument('--output', required=True)
    parser.add_argument('--browser-binary'); parser.add_argument('--driver-binary')
    parser.add_argument('--fts-maintenance', action='store_true')
    options = parser.parse_args()
    print(json.dumps(qualify(options.output, options.browser_binary, options.driver_binary, fts_maintenance=options.fts_maintenance), indent=2))
