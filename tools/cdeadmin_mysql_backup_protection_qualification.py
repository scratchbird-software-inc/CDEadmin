"""Owned native MySQL managed backup archive protection and local retirement."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output, *, mysql_shell, mysql_binlog, use_c=False, gtid_mode='ON', browser_binary=None, driver_binary=None):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Keep native evidence outside source')
    output.mkdir(parents=True, exist_ok=False)
    os.environ['CDEADMIN_MYSQL_BINLOG_BINARY'] = str(Path(mysql_binlog).resolve(strict=True))
    os.environ['CDEADMIN_MYSQLSH_BINARY'] = str(Path(mysql_shell).resolve(strict=True))
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app = setup_application(output)
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from mysql_qualification_support import server, _root_connection
    client = app.test_client(); service = service_for_app(app)
    proof = {'complete': False, 'history_testing': 'not run', 'checks': [], 'gtid_mode': gtid_mode,
             'mysql_interface': 'c' if use_c else 'pure', 'source_sha256': {}}
    for name in ('web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
                 'web/pgadmin/cdeadmin/providers/mysql_family/mysql_backup_events.py',
                 'web/pgadmin/cdeadmin/workspace/mysql_backup_protection.py',
                 'web/pgadmin/cdeadmin/workspace/mysql_archive_retention.py',
                 'web/pgadmin/cdeadmin/workspace/mysql_binlog_service.py',
                 'web/pgadmin/cdeadmin/workspace/mysql_raw_binlog_service.py',
                 'web/pgadmin/cdeadmin/workspace/service.py',
                 'web/pgadmin/browser/server_groups/servers/__init__.py',
                 'web/pgadmin/static/js/Dialogs/MySQLBackupProtection.jsx',
                 'web/pgadmin/static/js/Dialogs/MySQLArchiveRetention.jsx',
                 'tools/cdeadmin_mysql_backup_protection_qualification.py'):
        proof['source_sha256'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    password = 'native-backup-protection-' + secrets.token_urlsafe(24)
    try:
        with server(output / 'fixture', gtid_mode=gtid_mode) as (route, _native_name, fixture):
            root = _root_connection('mysql', route['port']); root.autocommit = True; query = root.cursor()
            try:
                query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                query.execute('CREATE DATABASE sr_source_purge')
                query.execute('CREATE TABLE sr_source_purge.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
                query.execute('INSERT INTO sr_source_purge.t VALUES(9007199254740993,"native 雪",X\'00FF\'),(9007199254740994,"second",NULL)')
                query.execute("CREATE USER 'sr_log_reader'@'%' IDENTIFIED BY %s", (password,))
                query.execute("GRANT REPLICATION CLIENT ON *.* TO 'sr_log_reader'@'%'")
                for _ in range(3): query.execute('FLUSH BINARY LOGS')
                (output / 'backups').mkdir()
                with app.test_request_context('/'):
                    user = User.query.first(); uid = user.id
                    group = ServerGroup.query.filter_by(user_id=uid).order_by(ServerGroup.id).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=uid)
                    def register(label, username):
                        item = Server(user_id=uid, servergroup_id=group.id, name=label, host=route['host'],
                            port=route['port'], username=username, maintenance_db=None, save_password=0)
                        item._cde_endpoint_registration = registration_profile('mysql-native')
                        item._cde_endpoint_route_configuration = {**route, 'user': username, 'use_pure': not use_c,
                                                                 'credential_kinds': ['database_password'], 'tool_workspace': str(output / 'backups')}
                        db.session.add(item); db.session.commit()
                        return item.id, url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=item.id), url_for('NODE-server.cde_workspace_id', gid=group.id, sid=item.id)
                    sid, verify_url, url = register('Owned MySQL source purge', 'root')
                    _reader_id, reader_verify, reader_url = register('Owned log reader', 'sr_log_reader')
                    registered = db.session.get(Server, sid)
                    database_target = str(__import__('uuid').uuid4())
                    db.session.add(EndpointDatabaseTarget(id=database_target, endpoint_id=registered.endpoint_profile.id,
                        display_name='sr_source_purge', database='sr_source_purge', configuration='{}', active=1)); db.session.commit()
                with client.session_transaction() as session:
                    session['_user_id'] = str(uid); session['_fresh'] = True
                assert client.post(verify_url, json={'password': password}).get_json()['success']
                assert client.post(reader_verify, json={'password': password}).get_json()['success']
                def http(action, request, *, target=None, prefix='mysql_binlog_backup_protection_', refused=False):
                    response = client.post(target or url, json={'action': prefix + action, 'request': request})
                    value = response.get_json()
                    if refused:
                        assert response.status_code == 400, value
                        return value
                    if response.status_code != 200 or not value.get('success'):
                        (output / 'http-failure.json').write_text(json.dumps(value, indent=2) + '\n')
                        raise AssertionError('Native source log HTTP failed: ' + action)
                    return value['data']
                def request(review):
                    return {**{key: review[key] for key in ('job_id', 'review_digest')}, 'confirmed': True}
                def wait(value, *, prefix='mysql_binlog_backup_protection_', expected='native_acknowledged', target=None):
                    deadline = time.monotonic() + 60
                    while value['state'] in {'active', 'dispatching', 'cancel_requested'}:
                        if time.monotonic() > deadline: raise TimeoutError('Native source log job deadline')
                        time.sleep(.05); value = http('status', {'job_id': value['job_id']}, prefix=prefix, target=target)
                    assert value['state'] == expected, value
                    return value
                # Retain two real native archives so age/count retention can
                # select the older one before a backup intent is admitted.
                initial = http('catalog', {}, prefix='mysql_raw_binlog_')
                retained = []
                for row in initial['logs'][:2]:
                    review = http('review', {'options': {'log_names': [row['Log_name']]}}, prefix='mysql_raw_binlog_')
                    retained.append(wait(http('start', request(review), prefix='mysql_raw_binlog_'), prefix='mysql_raw_binlog_', expected='completed'))
                archives = service.mysql_raw_binlog_jobs
                records = [archives.load(item['job_id'], uid, item['endpoint_id']) for item in retained]
                before = [archives.native_verify(archives.directory(item) / 'archive', item['source']) for item in records]
                retention = http('retention_review', {'policy': {'retention_days': 0, 'keep_latest': 1}}, prefix='mysql_raw_binlog_')
                def graphical_backup(path, *, refused=False):
                    payload = {'database_target_id': database_target, 'resource_kind': 'database', 'operation_id': 'backup_logical',
                        'target_resource': {'resource_kind': 'database', 'display_name': 'sr_source_purge', 'display_path': ['sr_source_purge']},
                        'draft': {'path': path, 'checksum': True, 'threads': 1, 'show_progress': False}}
                    plan = client.post(url, json={'action': 'visual_admin_plan', 'request': payload}).get_json()
                    assert plan['success'] and plan['data']['state'] == 'ready', plan
                    response = client.post(url, json={'action': 'visual_admin_apply', 'request': {
                        'database_target_id': database_target, **{key: plan['data'][key] for key in ('plan_id', 'plan_digest')}, 'confirmed': True}})
                    value = response.get_json()
                    if refused:
                        assert response.status_code != 200 or not value.get('success'), value
                        return value
                    assert response.status_code == 200 and value.get('success'), value
                    return value['data']['provider_result']['driver_observation']
                from pgadmin.cdeadmin.providers.mysql_family import mysql_shell_tools
                from pgadmin.cdeadmin.workspace.mysql_backup_protection import Registry
                original = mysql_shell_tools.run; calls = []
                def observed_tool(*args, **kwargs):
                    with app.app_context():
                        listed = service.mysql_backup_protection.list(uid, retained[0]['endpoint_id'])
                    assert listed['backups'][0]['state'] == 'pending_native_reply'
                    calls.append('native-dump-with-durable-intent')
                    return original(*args, **kwargs)
                mysql_shell_tools.run = observed_tool
                try:
                    query.execute('UPDATE sr_source_purge.t SET body=CONCAT(body,"!")')
                    backup = graphical_backup('managed-dump')
                    query.execute('SELECT ROW_COUNT()'); assert query.fetchone()[0] == 2
                finally: mysql_shell_tools.run = original
                protection = backup['archive_backup_protection']
                assert backup['mysql_shell_completed'] and protection['state'] == 'native_dump_returned' and len(calls) == 1
                top = json.loads((output / 'backups/managed-dump/@.json').read_text())
                assert protection['source']['server_uuid'] == top['source']['sysvars']['server_uuid']
                assert protection['native_boundary']['position'] == str(top['source']['binlog']['position'])
                (output / 'managed-backup-protection.json').write_text(json.dumps(protection, indent=2)+'\n')
                proof['checks'].append('actual-graphical-native-dump-persisted-intent-before-tool-with-exact-native-source-boundary-and-preserved-source-row-count')
                listed = http('list', {})
                assert len(listed['backups']) == 1 and not listed['external_backups_discovered']
                assert http('list', {}, target=reader_url)['backups'] == []
                review = http('review_retire', {'backup_id': protection['backup_id']})
                http('retire', {key: review[key] for key in ('review_id', 'review_digest')} | {'confirmed': True}, target=reader_url, refused=True)
                proof['checks'].append('offline-protection-list-and-retirement-authority-remain-owner-and-registration-scoped')
                for item in records:
                    http('remove_artifact', {'job_id': item['job_id'], 'confirmation': item['job_id']}, prefix='mysql_raw_binlog_', refused=True)
                stopped = wait(http('retention_start', request(retention), prefix='mysql_raw_binlog_'), prefix='mysql_raw_binlog_retention_', expected='interrupted')
                for item, expected in zip(records, before):
                    assert archives.native_verify(archives.directory(item) / 'archive', item['source']) == expected
                    assert not archives.load(item['job_id'], uid, item['endpoint_id']).get('artifact_removal')
                proof['checks'].append('new-backup-hold-blocks-individual-removal-and-already-reviewed-retention-before-file-intent')
                native_dump_before = hashlib.sha256((output / 'backups/managed-dump/@.done.json').read_bytes()).hexdigest()
                http('retire', {key: review[key] for key in ('review_id', 'review_digest')} | {'confirmed': False}, refused=True)
                retired = http('retire', {key: review[key] for key in ('review_id', 'review_digest')} | {'confirmed': True})
                assert retired['state'] == 'retired' and not retired['backup_files_removed']
                removed = http('remove_artifact', {'job_id': records[0]['job_id'], 'confirmation': records[0]['job_id']}, prefix='mysql_raw_binlog_')
                assert removed['artifact_removed'] and not (archives.directory(records[0]) / 'archive').exists()
                assert hashlib.sha256((output / 'backups/managed-dump/@.done.json').read_bytes()).hexdigest() == native_dump_before
                proof['checks'].append('reviewed-retirement-releases-only-local-protection-keeps-native-dump-files-and-permits-separate-archive-removal')
                delivered = []
                def lost(*args, **kwargs):
                    value = observed_tool(*args, **kwargs)
                    delivered.append('actual-native-dump-returned')
                    raise OSError('Owned suppressed native dump acknowledgement')
                mysql_shell_tools.run = lost
                try: graphical_backup('uncertain-dump', refused=True)
                finally: mysql_shell_tools.run = original
                assert len(delivered) == 1 and (output / 'backups/uncertain-dump/@.done.json').is_file()
                listed = http('list', {})
                uncertain = next(row for row in listed['backups'] if row['state'] != 'retired')
                assert uncertain['state'] == 'unconfirmed_native_reply'
                restarted = Registry(service.mysql_backup_protection.root)
                assert restarted.list(uid, retained[0]['endpoint_id']) == listed
                http('remove_artifact', {'job_id': records[1]['job_id'], 'confirmation': records[1]['job_id']}, prefix='mysql_raw_binlog_', refused=True)
                (output / 'unconfirmed-backup-protection.json').write_text(json.dumps(uncertain, indent=2)+'\n')
                proof['checks'].append('fault-injected-lost-reply-after-real-native-dump-keeps-restart-readable-hold-without-replay')
                if browser_binary:
                    proof['browser'] = browser(app, output, sid, password, browser_binary, driver_binary, uncertain['backup_id'])
                else:
                    review = http('review_retire', {'backup_id': uncertain['backup_id']})
                    assert http('retire', {key: review[key] for key in ('review_id', 'review_digest')} | {'confirmed': True})['state'] == 'retired'
                assert len(delivered) == 1 and (output / 'backups/uncertain-dump/@.done.json').is_file()
                assert archives.native_verify(archives.directory(records[1]) / 'archive', records[1]['source']) == before[1]
                query.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_source_purge.t ORDER BY id')
                assert query.fetchall() == [('9007199254740993', 'native 雪!', '00FF'), ('9007199254740994', 'second!', None)]
                proof['checks'].append('explicit-abandonment-of-uncertain-protection-never-repeats-native-backup-or-changes-retained-data-and-archive-bytes')
                proof.update(complete=True, native_version=fixture['engine_version'])
            finally:
                from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import MySQLBinlogJobs
                for jobs in vars(service).values():
                    if isinstance(jobs, MySQLBinlogJobs): assert jobs.close()
                query.close(); root.close()
        proof['owned_server_stopped'] = fixture['owned_server_stopped']
    finally:
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def browser(app, output, sid, password, binary, driver_binary, backup_id):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer, expand
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
        wait = WebDriverWait(driver, 90); ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'MySQL')
        def target(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', node, sid)), None)
        ActionChains(driver).context_click(wait.until(target)).perform()
        wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '[role="menuitem"]') if node.is_displayed() and node.text.strip() == 'Backup'), None)).click()
        wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '[role="menuitem"]') if node.is_displayed() and 'MySQL raw' in node.text), None)).click()
        def click(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME, 'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip() == label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});', node)
                        if node.is_displayed(): node.click(); return True
                return False
            wait.until(attempt)
        section = wait.until(lambda browser: browser.find_element(By.XPATH, '//summary[normalize-space()="Archive retention"]'))
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', section);section.click()
        section = driver.find_element(By.XPATH, '//summary[normalize-space()="Managed backup protection"]')
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', section);section.click()
        click('Load managed backup protection')
        button = wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, 'button[aria-label="Review retirement of backup '+backup_id+'"]'))
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', button);button.click()
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, '[aria-label="Managed backup retirement review"]'))
        checkbox = driver.find_element(By.XPATH, '//label[contains(normalize-space(),"Retire this backup from archive protection")]//input')
        driver.execute_script('arguments[0].click()', checkbox)
        click('Confirm backup protection retirement')
        wait.until(lambda browser: any('Backup protection '+backup_id+': retired.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        driver.save_screenshot(str(output / 'managed-backup-protection.png'))
        errors = [entry for entry in driver.get_log('browser') if entry['level'] == 'SEVERE']
        (output / 'browser-console.json').write_text(json.dumps(errors, indent=2) + '\n')
        assert not errors
        return {'complete': True, 'console_errors': 0, 'native_backups_list_review_and_explicit_uncertain_hold_retirement': True}
    except BaseException:
        if driver is not None:
            driver.save_screenshot(str(output / 'browser-failure.png'))
            (output / 'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME, 'body').text)
        raise
    finally:
        if driver is not None: driver.quit()
        http.shutdown(); http.server_close(); thread.join(timeout=5)
        if thread.is_alive(): raise RuntimeError('Owned source log HTTP server did not stop')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--mysql-shell', required=True)
    parser.add_argument('--mysql-binlog', required=True)
    parser.add_argument('--use-c', action='store_true')
    parser.add_argument('--gtid-mode', choices=['ON','OFF'], default='ON')
    parser.add_argument('--browser-binary')
    parser.add_argument('--driver-binary')
    args = parser.parse_args()
    proof = qualify(args.output, mysql_shell=args.mysql_shell, mysql_binlog=args.mysql_binlog, use_c=args.use_c,
        gtid_mode=args.gtid_mode, browser_binary=args.browser_binary, driver_binary=args.driver_binary)
    print(json.dumps({'complete':proof['complete'],'checks':len(proof['checks'])}))
