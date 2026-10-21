"""Owned MySQL9.7 restore and separate native checksum acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output, shell, use_c=False, browser_binary=None, driver_binary=None):
    from types import SimpleNamespace
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Keep native fixtures outside source')
    output.mkdir(parents=True, exist_ok=False)
    app = setup_application(output)
    from mysql_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client, MYSQL_PROFILE
    from pgadmin.cdeadmin.security import SecretLease
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    os.environ['CDEADMIN_MYSQLSH_BINARY'] = str(Path(shell).resolve(strict=True))
    proof = {'complete': False, 'history_testing': 'not run', 'checks': [],
             'mysql_interface': 'c' if use_c else 'pure', 'source_sha256': {}}
    for name in ('web/pgadmin/cdeadmin/providers/mysql_family/mysql_dump_verification.py',
                 'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
                 'web/pgadmin/cdeadmin/providers/relational_admin.py',
                 'web/pgadmin/cdeadmin/context_menu.py',
                 'web/pgadmin/cdeadmin/visual_admin/portfolio_catalog.json',
                 'tools/cdeadmin_mysql_dump_verification_qualification.py'):
        proof['source_sha256'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    password = 'sr-owned-' + secrets.token_urlsafe(24)
    client = _create_client(MYSQL_PROFILE,
        SimpleNamespace(acquire_secret=lambda *_args: SecretLease(password.encode('utf8'))), SimpleNamespace())
    runner = client._tool_runner.run
    def recorded(grant, arguments, **kwargs):
        result = runner(grant, arguments, **kwargs)
        if result['return_code']:
            (output / 'native-tool-failure.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
    client._tool_runner.run = recorded
    try:
        with server(output / 'fixture') as (route, _name, fixture):
            root = _root_connection('mysql', route['port']); root.autocommit = True
            query = root.cursor()
            try:
                query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                query.execute('CREATE DATABASE sr_accept CHARACTER SET utf8mb4')
                query.execute('CREATE TABLE sr_accept.`wide`(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
                query.execute('INSERT INTO sr_accept.`wide` VALUES(%s,%s,%s)', (9007199254740993, 'native 😀 雪', b'\x00\xff'))
                query.execute('CREATE TABLE sr_accept.`empty`(id BIGINT)')
                query.execute('CREATE TABLE sr_accept.`no key`(value TEXT)')
                query.execute('INSERT INTO sr_accept.`no key` VALUES(NULL),("duplicate"),("duplicate")')
                selected = {**route, 'use_pure': not use_c, 'database': 'sr_accept', 'ssl_disabled': False,
                    'tool_workspace': str(output), 'credential_reference_id': 'owned-native-password',
                    'principal_reference': 'owned-native-operator'}
                backup = client.run_database_operation(None, selected, 'backup_logical',
                    {'path': 'dump', 'checksum': True, 'threads': 2, 'show_progress': False})
                assert backup['mysql_shell_completed']
                query.execute('UPDATE sr_accept.wide SET body="after dump"')
                restored = client.run_database_operation(None, selected, 'restore_logical',
                    {'path': 'dump', 'confirmation': 'sr_accept', 'drop_existing_objects': True,
                     'reset_progress': True, 'enable_local_infile': True, 'show_progress': False})
                assert restored['restore_postcondition']['schema_postcondition_passed']
                proof['checks'].append('actual-native-Shell-checksummed-backup-mutation-and-independent-restore')
                query.execute('CREATE DATABASE sr_renamed CHARACTER SET utf8mb4')
                renamed = {**selected, 'database': 'sr_renamed'}
                client.run_database_operation(None, renamed, 'restore_logical',
                    {'path': 'dump', 'confirmation': 'sr_renamed', 'schema': 'sr_renamed',
                     'reset_progress': True, 'enable_local_infile': True, 'show_progress': False})
                value = client.run_database_operation(None, renamed, 'verify_logical',
                    {'path': 'dump', 'confirmation': 'sr_renamed', 'source_schema': 'sr_accept',
                     'enable_local_infile': True, 'threads': 2})
                assert value['data_recovery_verified'] and all(row['target_schema'] == 'sr_renamed' for row in value['tables'])
                (output / 'renamed-schema.json').write_text(json.dumps(value, indent=2) + '\n')
                query.execute('DROP DATABASE sr_renamed')
                proof['checks'].append('actual-native-restore-and-data-acceptance-with-renamed-target-schema')
                # The verifier uses JSON credentials, preserving all password
                # characters without a command-line or line-oriented channel.
                password = 'LF\nquote"slash\\雪-' + secrets.token_urlsafe(20)
                query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                options = {'path': 'dump', 'confirmation': 'sr_accept', 'enable_local_infile': True, 'threads': 2}
                def verify(label):
                    value = client.run_database_operation(None, selected, 'verify_logical', options)
                    assert value['restore_issued'] is False and value['server_read_lock_released']
                    query.execute('SELECT @@GLOBAL.local_infile'); assert query.fetchone()[0] == 0
                    (output / (label + '.json')).write_text(json.dumps(value, indent=2) + '\n')
                    return value
                accepted = verify('accepted')
                assert accepted['data_recovery_verified'] and accepted['row_counts_matched']
                assert accepted['native_checksums_returned'] and accepted['artifact_unchanged']
                query.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_accept.wide')
                assert query.fetchall() == [('9007199254740993', 'native 😀 雪', '00FF')]
                proof['checks'].append('separate-native-checksum-read-lock-and-exact-wide-Unicode-BLOB-empty-and-duplicate-NULL-row-acceptance')
                query.execute('INSERT INTO sr_accept.wide VALUES(9007199254740994,"outside native checksum boundary",NULL)')
                extra = verify('extra-row')
                assert extra['native_checksums_returned'] and not extra['row_counts_matched'] and not extra['data_recovery_verified']
                query.execute('DELETE FROM sr_accept.wide WHERE id=9007199254740994')
                proof['checks'].append('extra-row-outside-native-chunk-boundaries-fails-independent-full-row-count')
                query.execute('UPDATE sr_accept.wide SET body="same count different payload"')
                changed = verify('changed-value')
                assert changed['row_counts_matched'] and not changed['native_checksums_returned'] and not changed['data_recovery_verified']
                assert changed['native_control']['stage'] == 'checksums'
                query.execute('UPDATE sr_accept.wide SET body=%s', ('native 😀 雪',))
                proof['checks'].append('same-count-native-checksum-mismatch-is-a-separate-failed-acceptance-without-restore-replay')
                query.execute('CREATE TABLE sr_accept.unexpected(id INT)')
                extra = verify('extra-table')
                assert extra['native_checksums_returned'] and not extra['target_table_inventory_matched'] and not extra['data_recovery_verified']
                query.execute('DROP TABLE sr_accept.unexpected')
                proof['checks'].append('unexpected-target-base-table-refuses-complete-dump-data-acceptance')
                original = client._tool_runner.run
                def fault(grant, args, **kwargs):
                    if '--version' not in args:
                        raise OSError('Owned verifier launch fault after native lock')
                    return original(grant, args, **kwargs)
                client._tool_runner.run = fault
                try:
                    try: verify('launch-fault')
                    except OSError: pass
                    else: raise AssertionError('Owned native launch fault was not observed')
                finally: client._tool_runner.run = original
                query.execute('SELECT @@GLOBAL.local_infile'); assert query.fetchone()[0] == 0
                query.execute('SET SESSION lock_wait_timeout=2')
                query.execute('UPDATE sr_accept.wide SET body=body')
                proof['checks'].append('native-launch-fault-releases-server-read-lock-and-restores-local-infile-without-retry')
                assert verify('accepted-again')['data_recovery_verified']
                # Native checksum removal is rejected before locks or utility
                # dispatch, rather than becoming a vacuous success.
                path = output / 'dump/@.checksums.json'; saved = path.read_bytes(); path.unlink()
                try:
                    try: verify('missing-checksums')
                    except (OSError, RelationalClientError): pass
                    else: raise AssertionError('A dump without checksum evidence was accepted')
                finally: path.write_bytes(saved)
                proof['checks'].append('missing-native-checksum-evidence-refused')
                if browser_binary:
                    # Native/API cases above qualify LF/Unicode credentials.
                    # The ordinary HTML password control is single-line; use
                    # an independent ASCII credential for browser navigation.
                    password = 'browser-' + secrets.token_urlsafe(24)
                    query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                proof['application'] = application(app, output, selected, password,
                    browser_binary=browser_binary, driver_binary=driver_binary)
                proof['checks'].append('authenticated-provider-review-apply-and-separate-durable-data-acceptance')
                proof['native_version'] = fixture['engine_version']
                proof['complete'] = True
            finally:
                query.close(); root.close()
        proof['owned_server_stopped'] = fixture['owned_server_stopped']
    finally:
        client.close()
        proof['owned_sessions_released'] = not client._connections
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def setup_application(output):
    import builtins
    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False
    for name, path in {'DATA_DIR': 'app', 'SQLITE_PATH': 'app/application.db',
            'SESSION_DB_PATH': 'app/sessions', 'STORAGE_DIR': 'app/storage',
            'LOG_FILE': 'app/application.log', 'AZURE_CREDENTIAL_CACHE_DIR': 'app/azure',
            'CDEADMIN_OPERATION_STORE_PATH': 'app/operations.json'}.items():
        setattr(config, name, str(output / path))
    from pgadmin import create_app
    app = create_app('ScratchRobin-native-mysql-dump-acceptance')
    app.PGADMIN_RUNTIME = False; app.PGADMIN_INT_KEY = ''; app.run_before_app_start()
    return app


def application(app, output, route, password, *, browser_binary=None, driver_binary=None):
    import uuid
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    client = app.test_client()
    with app.test_request_context('/'):
        user = User.query.first(); uid = user.id
        group = ServerGroup.query.filter_by(user_id=uid).order_by(ServerGroup.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=uid)
        server = Server(user_id=uid, servergroup_id=group.id, name='Owned MySQL dump acceptance',
            host=route['host'], port=route['port'], username='root', maintenance_db=None, save_password=0)
        server._cde_endpoint_registration = registration_profile('mysql-native')
        server._cde_endpoint_route_configuration = {key: value for key, value in route.items()
            if key not in {'credential_reference_id', 'principal_reference', 'database'}}
        server._cde_endpoint_route_configuration['credential_kinds'] = ['database_password']
        db.session.add(server); db.session.commit()
        target = str(uuid.uuid4())
        db.session.add(EndpointDatabaseTarget(id=target, endpoint_id=server.endpoint_profile.id,
            display_name='sr_accept', database='sr_accept', configuration='{}', active=1)); db.session.commit()
        verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=server.id)
        url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=server.id)
    with client.session_transaction() as session:
        session['_user_id'] = str(uid); session['_fresh'] = True
    assert client.post(verify_url, json={'password': password}).get_json()['success']
    def post(action, request):
        response = client.post(url, json={'action': action, 'request': {'database_target_id': target, **request}})
        result = response.get_json()
        if response.status_code != 200 or not result.get('success'):
            (output / 'application-failure.json').write_text(json.dumps(result, indent=2) + '\n')
            raise AssertionError('Native dump application operation failed: ' + action)
        return result['data']
    request = {'resource_kind': 'database', 'operation_id': 'verify_logical',
        'target_resource': {'resource_kind': 'database', 'display_name': 'sr_accept', 'display_path': ['sr_accept']},
        'draft': {'path': 'dump', 'confirmation': 'sr_accept', 'enable_local_infile': True, 'threads': 2}}
    plan = post('visual_admin_plan', request)
    assert plan['state'] == 'ready' and plan['execution_available'], plan
    assert plan['command_preview']['mysql_data_verification_review']['server_wide_write_pause'] is True
    result = post('visual_admin_apply', {key: plan[key] for key in ('plan_id', 'plan_digest')} | {'confirmed': True})
    (output / 'application-result.json').write_text(json.dumps(result, indent=2) + '\n')
    assert result['provider_result']['driver_observation']['data_recovery_verified'], result
    proof = {'complete': True, 'provider_planned': True, 'independent_data_verified': True}
    stale = post('visual_admin_plan', request)
    path = output / 'dump/@.done.json'; before = path.read_bytes()
    try:
        path.write_bytes(before + b'\n')
        refused = client.post(url, json={'action': 'visual_admin_apply', 'request': {
            'database_target_id': target, **{key: stale[key] for key in ('plan_id', 'plan_digest')}, 'confirmed': True}})
        assert refused.status_code != 200 or not refused.get_json().get('success'), refused.get_json()
    finally:
        path.write_bytes(before)
    proof['stale_review_refused_without_dispatch'] = True
    if browser_binary:
        proof['browser'] = browser(app, output, server.id, password, browser_binary, driver_binary)
    return proof


def browser(app, output, server_id, password, binary, driver_binary):
    import threading
    from types import SimpleNamespace
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_firebird_ui_form_gate import prepare_tree
    from cdeadmin_mysql_backup_restore_ui_gate import _fill, _preview
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, invoke_context_action, wait_for_tree_item, visible_named_control
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
        wait = WebDriverWait(driver, 90)
        ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'MySQL')
        def registered(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', node, server_id)), None)
        label = wait.until(registered).text.strip()
        prepare_tree(driver, wait, SimpleNamespace(engine='MySQL', server=label, database='sr_accept',
            url='http://127.0.0.1:' + str(http.server_port), output_root=output,
            theme='default', font_scale=100, width=1800, height=1200), password)
        invoke_context_action(wait, driver, wait_for_tree_item(wait, 'sr_accept'),
            ['Restore', 'Verify restored dump data (MySQL Shell)...'], password)
        wait.until(lambda current: visible_named_control(current, 'Validate and preview'))
        catalog = json.loads((ROOT / 'web/pgadmin/cdeadmin/visual_admin/portfolio_catalog.json').read_text())
        operation = {'operation_id': 'verify_logical', 'form': catalog['forms']['mysql_verify_logical']}
        _fill(driver, wait, operation, {'path': 'dump', 'confirmation': 'sr_accept', 'threads': 2, 'enable_local_infile': True}, 'sr_accept')
        _preview(wait, {'case_id': 'verify_logical'})
        confirmation = visible_named_control(driver, 'I confirm this provider-planned operation.')
        if confirmation is not None: driver.execute_script('arguments[0].click()', confirmation)
        button = wait.until(lambda current: visible_named_control(current, 'Apply provider plan'))
        wait.until(lambda _current: button.is_enabled()); button.click()
        rendered = wait.until(lambda current: current.find_element(By.CSS_SELECTOR, '[aria-label="Provider operation result"]'))
        result = json.loads(rendered.get_attribute('textContent'))
        assert result['driver_observation']['data_recovery_verified'], result
        driver.save_screenshot(str(output / 'mysql-dump-data-acceptance.png'))
        errors = [entry for entry in driver.get_log('browser') if entry['level'] == 'SEVERE']
        (output / 'browser-console.json').write_text(json.dumps(errors, indent=2) + '\n')
        assert not errors
        return {'complete': True, 'console_errors': 0, 'context_menu_review_apply_and_native_data_accepted': True}
    except BaseException:
        if driver is not None:
            driver.save_screenshot(str(output / 'browser-failure.png'))
            (output / 'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME, 'body').text)
        raise
    finally:
        if driver is not None: driver.quit()
        http.shutdown(); http.server_close(); thread.join(timeout=5)
        if thread.is_alive(): raise RuntimeError('Owned HTTP server did not stop')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mysql-shell', type=Path, required=True)
    parser.add_argument('--use-c', action='store_true')
    parser.add_argument('--browser-binary'); parser.add_argument('--driver-binary')
    args = parser.parse_args()
    print(json.dumps(qualify(args.output, args.mysql_shell, args.use_c,
        args.browser_binary, args.driver_binary), indent=2))
