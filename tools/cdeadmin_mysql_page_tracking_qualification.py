"""Owned Community page-tracking UDFs, native status codes and reviewed API."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def checkpoint(query, start):
    deadline = time.monotonic() + 45
    while True:
        query.execute("SHOW GLOBAL STATUS LIKE 'Innodb_redo_log_checkpoint_lsn'")
        value = int(query.fetchone()[1])
        if value > start: return value
        if time.monotonic() > deadline: raise AssertionError('Owned native checkpoint did not advance beyond the tracking start')
        time.sleep(0.25)


def qualify(output, application=False, binary=None, driver_binary=None):
    import config  # noqa: F401
    from mysql_qualification_support import server, _root_connection, _run
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, MYSQL_ADMINISTRATION, _create_client
    from pgadmin.cdeadmin.providers.mysql_family import mysql_page_tracking as adapter
    from pgadmin.cdeadmin.sdk import RelationalClientError
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents: raise ValueError('Keep evidence outside source')
    output.mkdir(parents=True, exist_ok=False)
    paths = ['web/pgadmin/cdeadmin/providers/mysql_family/' + name for name in ('mysql_page_tracking.py', 'administration.py', 'provider.py')]
    paths += ['tools/cdeadmin_mysql_page_tracking_qualification.py', 'web/pgadmin/cdeadmin/context_menu.py']
    proof = {'complete': False, 'interfaces': [], 'history_testing': 'not run', 'full_mysql_product_complete': False,
             'source_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}}
    owned_status = None
    try:
        with server(output / 'fixture') as (route, name, owned):
            owned_status = owned
            oracle = _root_connection('mysql', route['port']); oracle.autocommit = True; query = oracle.cursor()
            try:
                query.execute("INSTALL COMPONENT 'file://component_mysqlbackup'")
                query.execute('SET GLOBAL innodb_max_dirty_pages_pct=0')  # Owned fixture checkpoint control only.
                query.execute('CREATE DATABASE sr_page_tracking')
                query.execute('CREATE TABLE sr_page_tracking.t(id INT PRIMARY KEY,value TEXT)')
                query.execute('CREATE TABLE sr_page_tracking.pending(id INT PRIMARY KEY)')
                query.execute('SELECT @@server_uuid'); uuid = query.fetchone()[0]
                target = {'resource_id': 'server:MySQL', 'resource_kind': 'server', 'display_name': 'MySQL', 'display_path': ['MySQL'], 'native': {'server_uuid': uuid}}
                for pure in (True, False):
                    client = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=None), SimpleNamespace())
                    selected = {**route, 'use_pure': pure}; classes = []; templates = {}; variants = {}; original = client._connect
                    def tracked(request):
                        handle = original(request); classes.append(type(handle).__name__); return handle
                    def plan(operation, **draft):
                        if operation not in adapter.READS: draft['confirmation'] = 'MySQL'
                        if operation in {'start_page_tracking', 'stop_page_tracking', 'set_page_tracking_backup_id', 'purge_page_tracking'}: draft['coordinated_backup_window'] = True
                        if operation == 'set_page_tracking_backup_id': draft['prior_index_removal_confirmed'] = True
                        if operation == 'purge_page_tracking': draft['tracking_files_not_required'] = True
                        value = client.plan_admin_operation({'resource_kind': 'server', 'operation_id': operation, 'draft': draft, 'target_resource': target, '_provider_route': selected})
                        sql = value['provider_payload']['compiled']['statements'][0]['source']
                        templates.setdefault(operation, sql); variants.setdefault(operation, set()).add(sql)
                        return value
                    def apply(operation, **draft): return MYSQL_ADMINISTRATION.apply(client, plan(operation, **draft))['page_tracking_observation']
                    checks = []; index_id = '182010' if pure else '182011'; base = 0 if pure else 2000
                    try:
                        with patch.object(client, '_connect', tracked):
                            initial = apply('inspect_page_tracking'); assert not initial['after']['native_active_window_observed']
                            active = apply('start_page_tracking'); first = int(active['native_scalar_result'])
                            assert first > 0 and active['after']['native_active_window_observed']
                            query.executemany('INSERT INTO sr_page_tracking.t VALUES(%s,%s)', [(base + i, 'x' * 1024) for i in range(1000)])
                            stop = checkpoint(query, first)
                            counted = apply('count_tracked_pages', start_lsn=str(first), stop_lsn=str(stop))
                            count = int(counted['native_scalar_result']); assert count > 0 and not counted['native_outcome_failed']
                            apply('set_page_tracking_backup_id', value_mode='VALUE', backup_id=index_id)
                            exported = apply('export_tracked_pages', start_lsn=str(first), stop_lsn=str(stop))
                            assert exported['native_acknowledged'] and exported['native_scalar_result'] == '0' and not exported['export_file_observed']
                            path = '/var/lib/mysql/#meb/' + index_id + '.idx'
                            size = int(_run(['docker', 'exec', name, 'stat', '--format=%s', path]).stdout)
                            digest = _run(['docker', 'exec', name, 'sha256sum', path]).stdout.split()[0]
                            assert size == count * 8
                            checks.append({'scope': 'native-active-window-count-and-export', 'native_count': str(count), 'independent_fixture_file_bytes': size, 'sha256': digest})
                            duplicate = apply('export_tracked_pages', start_lsn=str(first), stop_lsn=str(stop))
                            assert duplicate['native_acknowledged'] and duplicate['native_outcome_failed'] and duplicate['native_scalar_result'] == '-1'
                            assert _run(['docker', 'exec', name, 'sha256sum', path]).stdout.split()[0] == digest
                            bad_count = apply('count_tracked_pages', start_lsn='18446744073709551615', stop_lsn='1')
                            assert bad_count['native_scalar_result'] == '-3803' and bad_count['native_outcome_failed']
                            apply('set_page_tracking_backup_id', value_mode='VALUE', backup_id=index_id + '1')
                            bad_export = apply('export_tracked_pages', start_lsn='18446744073709551615', stop_lsn='1')
                            assert bad_export['native_scalar_result'] == '3803' and bad_export['native_outcome_failed']
                            assert _run(['docker', 'exec', name, 'test', '!', '-e', path], check=False).returncode == 0
                            checks.append({'scope': 'native-nonexception-failures-and-prior-index-removal', 'duplicate_status': '-1', 'count_status': '-3803', 'export_status': '3803', 'prior_native_index_removed': True})
                            apply('set_page_tracking_backup_id', value_mode='NULL')
                            assert apply('inspect_page_tracking')['after']['native_backup_id'] is None
                            apply('set_page_tracking_backup_id', value_mode='DEFAULT')
                            assert apply('inspect_page_tracking')['after']['native_backup_id'] is None
                            checks.append({'scope': 'native-null-and-default-backup-id', 'runtime_only': True})
                            stale = plan('start_page_tracking')
                            query.execute('SET GLOBAL `mysqlbackup.backupid`=%s', ('182999',))
                            try: MYSQL_ADMINISTRATION.apply(client, stale)
                            except RelationalClientError as error: assert not error.native_dispatched
                            else: raise AssertionError('Changed native tracking inputs were dispatched')
                            changes = plan('set_page_tracking_backup_id', value_mode='VALUE', backup_id=index_id)
                            observed = adapter.observe; calls = 0
                            def lost(cursor):
                                nonlocal calls
                                calls += 1
                                if calls == 2: raise OSError('owned later observation loss')
                                return observed(cursor)
                            with patch.object(adapter, 'observe', lost): result = MYSQL_ADMINISTRATION.apply(client, changes)['page_tracking_observation']
                            assert result['native_acknowledged'] and result['later_observation_error']
                            query.execute('SELECT @@GLOBAL.`mysqlbackup.backupid`'); assert query.fetchone() == (index_id,)
                            checks.append({'scope': 'changed-input-refusal-and-post-ack-loss', 'no_automatic_replay': True})
                            query.execute('SET autocommit=0'); query.execute('INSERT INTO sr_page_tracking.pending VALUES(7)'); query.execute('SAVEPOINT tracking_guard')
                            stopped = apply('stop_page_tracking'); assert not stopped['after']['native_active_window_observed']
                            purged = apply('purge_page_tracking', purge_lsn=stopped['native_scalar_result'])
                            query.execute('ROLLBACK TO SAVEPOINT tracking_guard'); query.execute('ROLLBACK'); query.execute('SET autocommit=1')
                            query.execute('SELECT COUNT(*) FROM sr_page_tracking.pending'); assert query.fetchone() == (0,)
                            checks.append({'scope': 'native-stop-purge-and-independent-pending-transaction', 'native_purge_return': purged['native_scalar_result'], 'savepoint_preserved': True})
                            expected = 'CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection'; assert classes and set(classes) == {expected}
                            proof['interfaces'].append({'use_pure': pure, 'native_connection_class': expected, 'checks': checks, 'templates': templates, 'source_variants': {k: sorted(v) for k, v in variants.items()}})
                    finally: client.close()
                proof['core_complete'] = True
                if application:
                    password = secrets.token_urlsafe(24); query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                    proof['application'] = workspace(output, route, password, target, query, binary, driver_binary)
                proof['native_server_uuid'] = uuid; proof['complete'] = True
            finally: query.close(); oracle.close()
    finally:
        if owned_status is not None: proof['owned_server_stopped'] = owned_status['owned_server_stopped']
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def workspace(output, route, password, target, oracle, binary=None, driver_binary=None):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from pgadmin.cdeadmin.providers.mysql_family.mysql_page_tracking import READS
    app = setup_application(output)
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    client = app.test_client(); receipts = []
    for pure in (True, False):
        with app.test_request_context('/'):
            uid = User.query.first().id; group = ServerGroup.query.filter_by(user_id=uid).first()
            app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=uid)
            item = Server(user_id=uid, servergroup_id=group.id, name='Owned page tracking ' + str(pure), host=route['host'], port=route['port'], username='root', maintenance_db='mysql', save_password=0)
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
        for operation, draft in [('inspect_page_tracking', {}), ('start_page_tracking', {'coordinated_backup_window': True}),
                                 ('set_page_tracking_backup_id', {'value_mode': 'VALUE', 'backup_id': '182030' if pure else '182031', 'coordinated_backup_window': True, 'prior_index_removal_confirmed': True}),
                                 ('count_tracked_pages', {'start_lsn': '18446744073709551615', 'stop_lsn': '1'}),
                                 ('export_tracked_pages', {'start_lsn': '18446744073709551615', 'stop_lsn': '1'}),
                                 ('stop_page_tracking', {'coordinated_backup_window': True}),
                                 ('purge_page_tracking', {'purge_lsn': '0', 'coordinated_backup_window': True, 'tracking_files_not_required': True})]:
            if operation not in READS: draft['confirmation'] = 'MySQL'
            request = {'resource_kind': 'server', 'operation_id': operation, 'target_resource': target, 'draft': draft}
            assert post('visual_admin_validate', request)['valid']
            plan = post('visual_admin_plan', request); assert plan['state'] == 'ready' and plan['execution_available']
            result = post('visual_admin_apply', {key: plan[key] for key in ('plan_id', 'plan_digest')} | {'confirmed': True})
            native = result['provider_result']['page_tracking_observation']; assert native['native_acknowledged']
            if operation in {'count_tracked_pages', 'export_tracked_pages'}: assert native['native_outcome_failed']
            receipts.append({'use_pure': pure, 'operation': operation, 'native_acknowledged': True, 'native_scalar_result': native['native_scalar_result']})
    result = {'complete': True, 'receipts': receipts}
    (output / 'application-api-summary.json').write_text(json.dumps(result, indent=2) + '\n')
    if binary: result['browser'] = browser(app, output, item.id, password, oracle, binary, driver_binary)
    return result


def browser(app, output, sid, password, oracle, binary, driver_binary):
    # The reusable Rewriter browser function is not a generic action runner;
    # this native workflow has different confirmations and live checkpoint input.
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as expected
    from selenium.common.exceptions import StaleElementReferenceException
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, invoke_context_action, complete_endpoint_prompt, fill_fields
    from pgadmin.cdeadmin.providers.mysql_family.mysql_page_tracking import OPERATIONS, READS
    http = make_server('127.0.0.1', 0, app, threaded=True); thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start(); driver = None
    try:
        options = webdriver.ChromeOptions(); options.binary_location = binary
        for flag in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1800,1200'): options.add_argument(flag)
        options.add_argument('--user-data-dir=' + str(output / 'browser-profile')); options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        driver = webdriver.Chrome(options=options, service=Service(driver_binary)); driver.get('http://127.0.0.1:' + str(http.server_port) + '/browser/')
        wait = WebDriverWait(driver, 90, ignored_exceptions=(StaleElementReferenceException,)); ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'MySQL')
        def registered(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name') if node.is_displayed() and browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', node, sid)), None)
        def click(label):
            def candidate(browser):
                for node in browser.find_elements(By.TAG_NAME, 'button'):
                    if node.text == label and node.is_enabled():
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});', node)
                        if node.is_displayed(): return node
            wait.until(candidate).click()
        checks = []; coordinated = 'This change is coordinated with all native backup/page-tracking clients=true'
        actions = [('start_page_tracking', [coordinated]), ('inspect_page_tracking', []),
                   ('set_page_tracking_backup_id', [coordinated, 'Native backup ID text (export requires digits)=182040', 'The prior exported index may be deleted, including when reusing the same ID=true']),
                   ('count_tracked_pages', []), ('export_tracked_pages', []),
                   ('stop_page_tracking', [coordinated]), ('purge_page_tracking', [coordinated, 'Tracking files are no longer required by any backup=true'])]
        for operation, values in actions:
            if operation == 'count_tracked_pages':
                oracle.execute('SELECT mysqlbackup_page_track_get_start_lsn()'); start = oracle.fetchone()[0]
                oracle.executemany('INSERT INTO sr_page_tracking.t VALUES(%s,%s)', [(10000 + i, 'b' * 1024) for i in range(1000)])
                checkpoint(oracle, start)
            node = wait.until(registered); invoke_context_action(wait, driver, node, ('Maintenance', OPERATIONS[operation] + '...'), handle_endpoint_prompt=False)
            if operation not in READS: click('Continue')
            complete_endpoint_prompt(driver, password, timeout=15)
            if operation not in READS: values = values + ['Exact server name=MySQL']
            fill_fields(wait, values); click('Validate and preview')
            wait.until(lambda browser: any('"state": "ready"' in node.text for node in browser.find_elements(By.CSS_SELECTOR, '[aria-label="Provider plan preview"]')))
            if operation not in READS:
                confirmation = wait.until(lambda browser: next((node for node in browser.find_elements(By.TAG_NAME, 'label') if node.is_displayed() and 'I confirm this provider-planned operation.' in node.text), None))
                driver.execute_script('arguments[0].scrollIntoView({block:"center"});', confirmation); confirmation.click()
            click('Apply provider plan')
            result = wait.until(lambda browser: next((json.loads(node.text) for node in browser.find_elements(By.CSS_SELECTOR, '[aria-label="Provider operation result"]') if 'page_tracking_observation' in node.text), None))
            native = result['page_tracking_observation']; assert native['native_acknowledged'] and not native['native_outcome_failed']
            checks.append({'operation': operation, 'native_acknowledged': True, 'native_scalar_result': native['native_scalar_result']})
            wait.until(lambda browser: any(node.text == 'Validate and preview' and node.is_enabled() for node in browser.find_elements(By.TAG_NAME, 'button')) and not any(node.is_displayed() for node in browser.find_elements(By.CSS_SELECTOR, '[role="progressbar"]')))
            driver.save_screenshot(str(output / 'native-page-tracking.png'))
            pane = driver.find_element(By.CSS_SELECTOR, '[aria-label="Provider operation result"]'); pane = driver.execute_script('return arguments[0].closest(".dock-tabpane");', pane)
            close = next(node for node in pane.find_elements(By.TAG_NAME, 'button') if node.text == 'Close')
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});', close); close.click(); wait.until(expected.staleness_of(pane))
        errors = [row for row in driver.get_log('browser') if row['level'] == 'SEVERE']; assert not errors, errors
        return {'complete': True, 'checks': checks, 'version': driver.capabilities['browserVersion'], 'console_errors': errors}
    except Exception:
        if driver:
            driver.save_screenshot(str(output / 'browser-failure.png')); (output / 'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME, 'body').text)
        raise
    finally:
        if driver: driver.quit()
        http.shutdown(); thread.join(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', required=True); parser.add_argument('--application', action='store_true')
    parser.add_argument('--browser-binary'); parser.add_argument('--driver-binary')
    args = parser.parse_args(); result = qualify(args.output, args.application, args.browser_binary, args.driver_binary)
    print(json.dumps({'complete': result['complete'], 'interfaces': len(result['interfaces'])}))
