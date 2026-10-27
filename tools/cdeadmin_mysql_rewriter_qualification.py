"""Owned MySQL Rewriter rules, native partial reload and independent pure/C API."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output, application=False, binary=None, driver_binary=None):
    import config  # noqa: F401
    from mysql_qualification_support import server, _root_connection, _run
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, MYSQL_ADMINISTRATION, _create_client
    from pgadmin.cdeadmin.providers.mysql_family import mysql_rewriter as adapter
    from pgadmin.cdeadmin.sdk import RelationalClientError
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents: raise ValueError('Keep evidence outside source')
    output.mkdir(parents=True, exist_ok=False)
    paths = ['web/pgadmin/cdeadmin/providers/mysql_family/' + name for name in ('mysql_rewriter.py', 'administration.py', 'provider.py')]
    paths += ['tools/cdeadmin_mysql_rewriter_qualification.py', 'web/pgadmin/cdeadmin/context_menu.py']
    proof = {'complete': False, 'interfaces': [], 'history_testing': 'not run', 'full_mysql_product_complete': False,
             'source_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}}
    owned_status = None
    try:
        with server(output / 'fixture') as (route, name, owned):
            owned_status = owned
            # Execute the official installer shipped in the pinned native image,
            # without reconstructing the plugin's schema or stored procedure.
            found = _run(['docker', 'exec', name, 'sh', '-c', 'find /usr/share -name install_rewriter.sql -type f']).stdout.splitlines()
            if len(found) != 1 or not found[0].startswith('/usr/share/') or any(c not in '/._-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' for c in found[0]):
                raise AssertionError('Native image must supply one Rewriter installer')
            installer = found[0]
            installed = _run(['docker', 'exec', name, 'mysql', '-uroot', '--commands=ON', '--execute=source ' + installer], check=False)
            (output / 'native-installer.log').write_text(installed.stdout + installed.stderr)
            installed.check_returncode()
            proof['native_installer'] = {'path': installer, 'sha256': _run(['docker', 'exec', name, 'sha256sum', installer]).stdout.split()[0]}
            oracle = _root_connection('mysql', route['port']); oracle.autocommit = True; query = oracle.cursor()
            user = 'rewrite_reader'; password = secrets.token_urlsafe(24)
            query.execute('CREATE USER %s@\'%\' IDENTIFIED BY %s', (user, password))
            query.execute('GRANT SELECT ON *.* TO %s@\'%\'', (user,))
            import mysql.connector
            consumer = mysql.connector.connect(host=route['host'], port=route['port'], user=user, password=password, use_pure=True, autocommit=True)
            reader = consumer.cursor()
            try:
                query.execute('SELECT @@server_uuid'); uuid = query.fetchone()[0]
                target = {'resource_id': 'server:MySQL', 'resource_kind': 'server', 'display_name': 'MySQL', 'display_path': ['MySQL'], 'native': {'server_uuid': uuid}}
                query.execute('CREATE DATABASE sr_rewriter')
                query.execute('CREATE TABLE sr_rewriter.pending(id INT PRIMARY KEY)')
                for pure in (True, False):
                    client = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=None), SimpleNamespace())
                    selected = {**route, 'use_pure': pure}; classes = []; templates = {}; original = client._connect
                    def tracked(request):
                        handle = original(request); classes.append(type(handle).__name__); return handle
                    def plan(operation, **draft):
                        if operation != 'inspect_rewrite_rules': draft['confirmation'] = 'MySQL'
                        planned = client.plan_admin_operation({'resource_kind': 'server', 'operation_id': operation, 'draft': draft, 'target_resource': target, '_provider_route': selected})
                        templates[operation] = planned['provider_payload']['compiled']['statements'][0]['source']
                        return planned
                    def apply(operation, **draft): return MYSQL_ADMINISTRATION.apply(client, plan(operation, **draft))['rewriter_observation']
                    checks = []
                    try:
                        with patch.object(client, '_connect', tracked):
                            initial = apply('inspect_rewrite_rules'); assert initial['after']['complete_stored_rules']
                            created = apply('create_rewrite_rule', pattern='SELECT ? + 100700', pattern_database='', replacement='SELECT ? + 200700', enabled='YES')
                            identity = created['inserted_rule_id']; assert type(identity) is int and identity > 0 and created['native_commit_acknowledged']
                            reader.execute('SELECT 3 + 100700'); assert reader.fetchone() == (100703,)
                            apply('reload_rewrite_rules', all_queries_affected=True)
                            reader.execute('SELECT 3 + 100700'); assert reader.fetchone() == (200703,)
                            checks.append('native-table-save-does-not-reload-and-explicit-native-reload-changes-independent-unprivileged-client-query')
                            # Native matching treats literals generically; use a
                            # distinct operator shape for the second rule.
                            invalid = apply('create_rewrite_rule', pattern='SELECT ? * 100701', pattern_database='', replacement='SELECT ? + ?', enabled='YES')['inserted_rule_id']
                            try: apply('reload_rewrite_rules', all_queries_affected=True)
                            except RelationalClientError as error:
                                assert error.native_dispatched and not error.native_acknowledged and error.errno == 1644 and error.sqlstate == '45000'
                            else: raise AssertionError('Native partial rule rejection was hidden')
                            partial = apply('inspect_rewrite_rules')['after']
                            bad = next(row for row in partial['rules'] if row['id'] == invalid)
                            assert bad['message'] and partial['native_status']['Rewriter_reload_error'] == 'ON'
                            reader.execute('SELECT 4 + 100700'); assert reader.fetchone() == (200704,)
                            checks.append('actual-native-1644-partial-reload-retains-valid-rules-and-exposes-per-rule-message-and-global-error-status')
                            stale = plan('drop_rewrite_rule', rule_id=str(identity))
                            query.execute('UPDATE query_rewrite.rewrite_rules SET enabled=\'NO\' WHERE id=%s', (identity,))
                            try: MYSQL_ADMINISTRATION.apply(client, stale)
                            except RelationalClientError as error: assert not error.native_dispatched
                            else: raise AssertionError('Changed rule was deleted')
                            apply('alter_rewrite_rule', rule_id=str(identity), pattern='SELECT ? + 100700', pattern_database='', replacement='SELECT ? + 300700', enabled='NO')
                            apply('drop_rewrite_rule', rule_id=str(invalid))
                            apply('reload_rewrite_rules', all_queries_affected=True)
                            reader.execute('SELECT 4 + 100700'); assert reader.fetchone() == (100704,)
                            checks.append('changed-rule-refused-and-native-disable-edit-delete-reload-observed-by-independent-client')
                            apply('alter_rewrite_rule', rule_id=str(identity), pattern='SELECT ? + 100700', pattern_database='', replacement='SELECT ? + 300700', enabled='YES')
                            planned = plan('drop_rewrite_rule', rule_id=str(identity)); observed = adapter.observe; calls = 0
                            def lost(cursor):
                                nonlocal calls
                                calls += 1
                                if calls == 2: raise OSError('owned post-commit observation loss')
                                return observed(cursor)
                            with patch.object(adapter, 'observe', lost): result = MYSQL_ADMINISTRATION.apply(client, planned)['rewriter_observation']
                            assert result['native_commit_acknowledged'] and result['later_observation_error']
                            query.execute('SELECT COUNT(*) FROM query_rewrite.rewrite_rules WHERE id=%s', (identity,)); assert query.fetchone() == (0,)
                            checks.append('native-committed-delete-survives-later-observer-loss-without-replay')
                            query.execute('SET autocommit=0'); query.execute('INSERT INTO sr_rewriter.pending VALUES(9)'); query.execute('SAVEPOINT rewriter_guard')
                            apply('reload_rewrite_rules', all_queries_affected=True)
                            query.execute('ROLLBACK TO SAVEPOINT rewriter_guard'); query.execute('ROLLBACK'); query.execute('SET autocommit=1')
                            query.execute('SELECT COUNT(*) FROM sr_rewriter.pending'); assert query.fetchone() == (0,)
                            checks.append('native-reload-commit-is-confined-to-owned-handle-and-independent-pending-transaction-savepoint-survives')
                            expected = 'CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection'
                            assert classes and set(classes) == {expected}
                            proof['interfaces'].append({'use_pure': pure, 'native_connection_class': expected, 'checks': checks, 'templates': templates})
                    finally: client.close()
                proof['core_complete'] = True
                if application:
                    password = secrets.token_urlsafe(24); query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                    proof['application'] = workspace(output, route, password, target, binary, driver_binary)
                proof['native_server_uuid'] = uuid; proof['complete'] = True
            finally: reader.close(); consumer.close(); query.close(); oracle.close()
        proof['owned_server_stopped'] = owned['owned_server_stopped']
    finally:
        if owned_status is not None: proof['owned_server_stopped'] = owned_status['owned_server_stopped']
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def workspace(output, route, password, target, binary, driver_binary):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app = setup_application(output)
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    client = app.test_client(); receipts = []
    for pure in (True, False):
        with app.test_request_context('/'):
            uid = User.query.first().id; group = ServerGroup.query.filter_by(user_id=uid).first()
            app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=uid)
            item = Server(user_id=uid, servergroup_id=group.id, name='Owned Rewriter ' + str(pure), host=route['host'], port=route['port'], username='root', maintenance_db='mysql', save_password=0)
            item._cde_endpoint_registration = registration_profile('mysql-native')
            item._cde_endpoint_route_configuration = {**route, 'use_pure': pure, 'credential_kinds': ['database_password']}
            db.session.add(item); db.session.commit()
            url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=item.id)
            verify = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=item.id)
        with client.session_transaction() as session: session['_user_id'] = str(uid); session['_fresh'] = True
        assert client.post(verify, json={'password': password}).get_json()['success']
        def post(action, request):
            reply = client.post(url, json={'action': action, 'request': request}); value = reply.get_json()
            assert reply.status_code == 200 and value.get('success'), (action, str(value).replace(password, '<redacted>'))
            return value['data']
        identity = None
        for operation in ('inspect_rewrite_rules', 'create_rewrite_rule', 'alter_rewrite_rule', 'reload_rewrite_rules', 'drop_rewrite_rule', 'reload_rewrite_rules'):
            draft = {} if operation == 'inspect_rewrite_rules' else {'confirmation': 'MySQL'}
            if operation in ('alter_rewrite_rule', 'drop_rewrite_rule'): draft['rule_id'] = str(identity)
            if operation in ('create_rewrite_rule', 'alter_rewrite_rule'):
                draft.update(pattern='SELECT ? DIV 100707', pattern_database='', replacement='SELECT ? DIV 200707', enabled='YES')
            if operation == 'reload_rewrite_rules': draft['all_queries_affected'] = True
            request = {'resource_kind': 'server', 'operation_id': operation, 'target_resource': target, 'draft': draft}
            assert post('visual_admin_validate', request)['valid']
            plan = post('visual_admin_plan', request); assert plan['state'] == 'ready' and plan['execution_available']
            result = post('visual_admin_apply', {key: plan[key] for key in ('plan_id', 'plan_digest')} | {'confirmed': True})
            native = result['provider_result']['rewriter_observation']; assert native['native_acknowledged']
            if operation == 'create_rewrite_rule': identity = native['inserted_rule_id']
            receipts.append({'use_pure': pure, 'operation': operation, 'native_acknowledged': True})
    result = {'complete': True, 'receipts': receipts}
    (output / 'application-api-summary.json').write_text(json.dumps(result, indent=2) + '\n')
    if binary: result['browser'] = browser(app, output, item.id, password, binary, driver_binary)
    return result


def browser(app, output, sid, password, binary, driver_binary):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, invoke_context_action, complete_endpoint_prompt, fill_fields
    from selenium.webdriver.support import expected_conditions as expected
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
        ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'MySQL')
        def registered(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name') if node.is_displayed() and browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', node, sid)), None)
        def click(label):
            def candidate(browser):
                for node in browser.find_elements(By.TAG_NAME, 'button'):
                    if node.text == label and node.is_enabled():
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});', node)
                        if node.is_displayed(): return node
            wait.until(candidate).click()
        checks = []; identity = None
        actions = [('create_rewrite_rule', 'Add native query rewrite rule...', ['Native SQL pattern (question marks match literals)=SELECT ? MOD 100709', 'Native SQL replacement=SELECT ? MOD 200709']),
                   ('reload_rewrite_rules', 'Reload native query rewrite rules...', ['Reload affects query rewriting for all clients=true']),
                   ('inspect_rewrite_rules', 'Inspect native query rewrite rules...', []),
                   ('drop_rewrite_rule', 'Remove native query rewrite rule...', []),
                   ('reload_rewrite_rules', 'Reload native query rewrite rules...', ['Reload affects query rewriting for all clients=true'])]
        for operation, title, values in actions:
            node = wait.until(registered)
            invoke_context_action(wait, driver, node, ('Maintenance', title), handle_endpoint_prompt=False)
            if operation != 'inspect_rewrite_rules': click('Continue')
            complete_endpoint_prompt(driver, password, timeout=15)
            if operation != 'inspect_rewrite_rules': values = values + ['Exact server name=MySQL']
            if operation == 'drop_rewrite_rule': values = values + ['Exact native rule ID from inspection=' + str(identity)]
            fill_fields(wait, values); click('Validate and preview')
            wait.until(lambda browser: any('"state": "ready"' in node.text for node in browser.find_elements(By.CSS_SELECTOR, '[aria-label="Provider plan preview"]')))
            if operation != 'inspect_rewrite_rules':
                confirmation = wait.until(lambda browser: next((node for node in browser.find_elements(By.TAG_NAME, 'label') if node.is_displayed() and 'I confirm this provider-planned operation.' in node.text), None))
                driver.execute_script('arguments[0].scrollIntoView({block:"center"});', confirmation); confirmation.click()
            click('Apply provider plan')
            result = wait.until(lambda browser: next((json.loads(node.text) for node in browser.find_elements(By.CSS_SELECTOR, '[aria-label="Provider operation result"]') if 'rewriter_observation' in node.text), None))
            native = result['rewriter_observation']; assert native['native_acknowledged']
            if operation == 'create_rewrite_rule': identity = native['inserted_rule_id']
            checks.append({'operation': operation, 'native_acknowledged': True})
            driver.save_screenshot(str(output / 'native-rewriter.png'))
            pane = driver.find_element(By.CSS_SELECTOR, '[aria-label="Provider operation result"]')
            pane = driver.execute_script('return arguments[0].closest(".dock-tabpane");', pane)
            close = next(node for node in pane.find_elements(By.TAG_NAME, 'button') if node.text == 'Close')
            # The native result is rendered before the awaited metadata refresh
            # finishes. Its close guard correctly refuses dismissal in flight.
            wait.until(lambda browser: any(node.text == 'Validate and preview' and node.is_enabled()
                       for node in browser.find_elements(By.TAG_NAME, 'button')) and
                       not any(node.is_displayed() for node in browser.find_elements(By.CSS_SELECTOR, '[role="progressbar"]')))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});', close); close.click()
            wait.until(expected.staleness_of(pane))
        errors = [row for row in driver.get_log('browser') if row['level'] == 'SEVERE']; assert not errors, errors
        return {'complete': True, 'checks': checks, 'version': driver.capabilities['browserVersion'], 'console_errors': errors}
    except Exception:
        if driver:
            driver.save_screenshot(str(output / 'browser-failure.png'))
            (output / 'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME, 'body').text)
        raise
    finally:
        if driver: driver.quit()
        http.shutdown(); thread.join(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', required=True); parser.add_argument('--application', action='store_true')
    parser.add_argument('--browser-binary'); parser.add_argument('--driver-binary')
    args = parser.parse_args(); result = qualify(args.output, args.application, args.browser_binary, args.driver_binary)
    print(json.dumps({'complete': result['complete'], 'interfaces': len(result['interfaces'])}))
