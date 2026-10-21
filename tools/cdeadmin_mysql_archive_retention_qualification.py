"""Owned MySQL 9.7 archives, authenticated retention and offline recovery of cleanup."""
import argparse
import builtins
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output, shell, decoder, *, use_c=False, browser_binary=None, driver_binary=None):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Keep qualification artifacts outside source')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    proof = {'complete': False, 'history_testing': 'not run', 'checks': [],
             'mysql_interface': 'c' if use_c else 'pure', 'source_sha256': {}}
    for name in ('web/pgadmin/cdeadmin/workspace/mysql_archive_retention.py',
                 'web/pgadmin/cdeadmin/workspace/mysql_raw_binlog_service.py',
                 'web/pgadmin/cdeadmin/workspace/mysql_binlog_service.py',
                 'web/pgadmin/static/js/Dialogs/MySQLArchiveRetention.jsx',
                 'web/pgadmin/static/js/Dialogs/MySQLBinlogArchives.jsx',
                 'web/pgadmin/browser/server_groups/servers/__init__.py',
                 'tools/cdeadmin_mysql_archive_retention_qualification.py'):
        proof['source_sha256'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    os.environ['CDEADMIN_MYSQLSH_BINARY'] = str(Path(shell).resolve(strict=True))
    os.environ['CDEADMIN_MYSQL_BINLOG_BINARY'] = str(Path(decoder).resolve(strict=True))
    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False
    for name, path in {'DATA_DIR': 'app', 'SQLITE_PATH': 'app/application.db',
                       'SESSION_DB_PATH': 'app/sessions', 'STORAGE_DIR': 'app/storage',
                       'LOG_FILE': 'app/application.log', 'AZURE_CREDENTIAL_CACHE_DIR': 'app/azure',
                       'CDEADMIN_OPERATION_STORE_PATH': 'app/operations.json',
                       'CDEADMIN_MYSQL_BINLOG_ROOT': 'shell-archives',
                       'CDEADMIN_MYSQL_RAW_BINLOG_ROOT': 'raw-archives'}.items():
        setattr(config, name, str(output / path))
    from flask import url_for
    from pgadmin import create_app
    from pgadmin.model import db, User, ServerGroup, Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from pgadmin.cdeadmin.workspace import mysql_archive_retention as retention
    from mysql_qualification_support import server, _root_connection
    app = create_app('ScratchRobin-native-mysql-archive-retention')
    app.PGADMIN_RUNTIME = False; app.PGADMIN_INT_KEY = ''; app.run_before_app_start()
    client = app.test_client(); service = service_for_app(app)
    password = 'retention LF\nquote"slash\\雪-' + secrets.token_urlsafe(24)
    paused = False
    try:
        with server(output / 'native-fixture') as (route, native_name, owned):
            root = _root_connection('mysql', route['port']); root.autocommit = True
            query = root.cursor()
            try:
                query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                query.execute('CREATE DATABASE sr_retention')
                query.execute('CREATE TABLE sr_retention.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
                query.execute('FLUSH BINARY LOGS')
                query.execute('SHOW BINARY LOG STATUS'); start = query.fetchone()[0]; query.fetchall()
                query.execute('INSERT INTO sr_retention.t VALUES(%s,%s,%s)', (9007199254740993, 'native 😀 雪', b'\x00\xff'))
                query.execute('FLUSH BINARY LOGS')
                with app.test_request_context('/'):
                    user = User.query.first(); uid = user.id
                    group = ServerGroup.query.filter_by(user_id=uid).order_by(ServerGroup.id).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=uid)
                    def register(label):
                        item = Server(user_id=uid, servergroup_id=group.id, name=label,
                                      host=route['host'], port=route['port'], username='root', maintenance_db=None, save_password=0)
                        item._cde_endpoint_registration = registration_profile('mysql-native')
                        item._cde_endpoint_route_configuration = {**route, 'use_pure': not use_c, 'credential_kinds': ['database_password']}
                        db.session.add(item); db.session.commit()
                        return (item.id, url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=item.id),
                                url_for('NODE-server.cde_workspace_id', gid=group.id, sid=item.id))
                    sid, verify_url, url = register('Owned MySQL archive retention')
                    _other_id, _other_verify, other_url = register('Other archive registration')
                with client.session_transaction() as session:
                    session['_user_id'] = str(uid); session['_fresh'] = True
                assert client.post(verify_url, json={'password': password}).get_json()['success']
                def http(prefix, action, request, *, refused=False, endpoint_url=None):
                    response = client.post(endpoint_url or url, json={'action': prefix + action, 'request': request})
                    value = response.get_json()
                    if refused:
                        assert response.status_code == 400, value
                        return value
                    assert response.status_code == 200 and value.get('success'), value
                    return value['data']
                def wait(prefix, value, expected, action='status'):
                    deadline = time.monotonic() + 120
                    while value['state'] in {'active', 'dispatching', 'cancel_requested'}:
                        if time.monotonic() > deadline:
                            raise TimeoutError('Owned native archive deadline')
                        time.sleep(.05); value = http(prefix, action, {'job_id': value['job_id']})
                    assert value['state'] == expected, value
                    return value
                def accepted(value):
                    return {**{key: value[key] for key in ('job_id', 'review_digest')}, 'confirmed': True}
                captured = {}
                for family, prefix in (('raw', 'mysql_raw_binlog_'), ('shell', 'mysql_binlog_')):
                    values = []
                    for index in range(3):
                        options = {'log_names': [start]} if family == 'raw' else {'start_file': start, 'compression': 'zstd', 'threads': 1}
                        reviewed = http(prefix, 'review', {'options': options})
                        value = wait(prefix, http(prefix, 'start', accepted(reviewed)), 'completed')
                        archives = getattr(service, 'mysql_raw_binlog_jobs' if family == 'raw' else 'mysql_binlog_jobs')
                        record = archives.load(value['job_id'], uid, value['endpoint_id'])
                        archives.update(record, created_at=time.time() - (100 - index) * 86400)
                        values.append(http(prefix, 'status', {'job_id': value['job_id']}))
                    captured[family] = (prefix, archives, values)
                    proof['checks'].append(family + '-three-actual-native-verified-archives')
                query.execute('SELECT @@global.gtid_executed'); before_gtids = query.fetchone()[0]
                query.execute('SHOW BINARY LOGS'); before_logs = query.fetchall()
                subprocess.run(['docker', 'pause', native_name], check=True, timeout=30, stdout=subprocess.DEVNULL)
                paused = True
                for family, (prefix, archives, values) in captured.items():
                    protected, candidate, newest = values
                    http(prefix, 'pin', {'job_id': protected['job_id'], 'pinned': True})
                    http(prefix, 'remove_artifact', {'job_id': protected['job_id'], 'confirmation': protected['job_id']}, refused=True)
                    http(prefix, 'status', {'job_id': candidate['job_id']}, refused=True, endpoint_url=other_url)
                    selected = {'policy': {'retention_days': 30, 'keep_latest': 1}}
                    plan = http(prefix, 'retention_review', selected)
                    assert [row['job_id'] for row in plan['continuation']['archives']] == [candidate['job_id']]
                    http(prefix, 'pin', {'job_id': candidate['job_id'], 'pinned': True})
                    interrupted = wait(prefix, http(prefix, 'retention_start', accepted(plan)), 'interrupted', 'retention_status')
                    assert 'Unprotect' in interrupted['error_message']
                    reconciled = http(prefix, 'retention_reconcile', {'job_id': plan['job_id'], 'confirmed': True})
                    assert reconciled['result']['unattempted_job_ids'] == [candidate['job_id']]
                    http(prefix, 'pin', {'job_id': candidate['job_id'], 'pinned': False})
                    proof['checks'].append(family + '-offline-protection-owner-scope-and-stale-review-refusal')
                    plan = http(prefix, 'retention_review', selected)
                    original = retention.shutil.rmtree
                    def interrupted_removal(path, *args, **kwargs):
                        if Path(path).name.startswith('.removing-'):
                            raise OSError('Owned native cleanup interruption after durable detach')
                        return original(path, *args, **kwargs)
                    retention.shutil.rmtree = interrupted_removal
                    try:
                        interrupted = wait(prefix, http(prefix, 'retention_start', accepted(plan)), 'interrupted', 'retention_status')
                    finally:
                        retention.shutil.rmtree = original
                    receipt = http(prefix, 'status', {'job_id': candidate['job_id']})
                    assert receipt['artifact_removal']['state'] == 'pending' and not receipt.get('artifact_removed')
                    assert http(prefix, 'retention_start', accepted(plan))['state'] == 'interrupted'
                    reconciled = http(prefix, 'retention_reconcile', {'job_id': plan['job_id'], 'confirmed': True})
                    assert reconciled['result']['removed_job_ids'] == [candidate['job_id']]
                    receipt = http(prefix, 'status', {'job_id': candidate['job_id']})
                    assert receipt['artifact_removed'] and receipt['artifact_removal']['state'] == 'completed'
                    removed_record = archives.load(receipt['job_id'], uid, receipt['endpoint_id'])
                    assert not (archives.directory(removed_record) / 'archive').exists()
                    for item in (protected, newest):
                        record = archives.load(item['job_id'], uid, item['endpoint_id'])
                        assert archives.native_verify(archives.directory(record) / 'archive', record['source']) == record['result']['artifact']
                    (output / (family + '-retention-receipt.json')).write_text(json.dumps(reconciled, indent=2) + '\n')
                    proof['checks'].append(family + '-offline-interrupted-detach-explicit-reconciliation-and-unchanged-protected-bytes')
                if browser_binary:
                    proof['browser'] = browser(app, output, sid, browser_binary, driver_binary)
                subprocess.run(['docker', 'unpause', native_name], check=True, timeout=30, stdout=subprocess.DEVNULL)
                paused = False
                query.execute('SELECT @@global.gtid_executed'); assert query.fetchone()[0] == before_gtids
                query.execute('SHOW BINARY LOGS'); assert query.fetchall() == before_logs
                query.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_retention.t')
                assert query.fetchall() == [('9007199254740993', 'native 😀 雪', '00FF')]
                proof['checks'].append('independent-native-source-gtids-log-inventory-and-exact-data-unchanged')
            finally:
                if paused:
                    subprocess.run(['docker', 'unpause', native_name], check=True, timeout=30, stdout=subprocess.DEVNULL)
                    paused = False
                query.close(); root.close()
                for attribute in vars(service).copy():
                    value = getattr(service, attribute)
                    if isinstance(value, retention.MySQLBinlogJobs):
                        assert value.close()
        proof['owned_server_stopped'] = owned['owned_server_stopped']
        proof['complete'] = proof['owned_server_stopped']
    finally:
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def browser(app, output, sid, binary, driver_binary):
    """Exercise the production archive controls while its native source is paused."""
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer, expand
    http = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start(); driver = None
    proof = {'complete': False, 'source_paused': True}
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
        def click(text):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME, 'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip() == text:
                        browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});', node)
                        if node.is_displayed():
                            node.click(); return True
                return False
            wait.until(attempt)
        wait.until(lambda browser: browser.find_element(By.XPATH, '//summary[normalize-space()="Archive retention"]')).click()
        click('Load retention receipts')
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, '[aria-label="Archive retention receipts"]'))
        # The oldest protected archive and the newest retained archive remain.
        # Unprotect through the ordinary archive controls, then review deletion.
        click('Load archive jobs')
        row = wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '[aria-label="Native MySQL archive jobs"] tbody tr') if 'completed' in node.text), None))
        row.find_element(By.TAG_NAME, 'button').click()
        # Choose the protected receipt by inspecting each surviving archive.
        for candidate in driver.find_elements(By.CSS_SELECTOR, '[aria-label="Native MySQL archive jobs"] tbody tr'):
            candidate.find_element(By.TAG_NAME, 'button').click()
            time.sleep(.15)
            buttons = [node for node in driver.find_elements(By.TAG_NAME, 'button') if node.is_displayed() and node.text.strip() == 'Unprotect archive from removal']
            if buttons:
                driver.execute_script('arguments[0].scrollIntoView({block:"center"});', buttons[0]); buttons[0].click(); break
        else:
            raise AssertionError('Owned protected native archive was not reachable')
        click('Review archive retention')
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, '[aria-label="Reviewed archive retention candidates"]'))
        click('Confirm removal of reviewed archives')
        wait.until(lambda browser: any('Retention ' in node.text and ': completed.' in node.text for node in browser.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        driver.save_screenshot(str(output / 'mysql-archive-retention.png'))
        errors = [entry for entry in driver.get_log('browser') if entry['level'] == 'SEVERE']
        (output / 'browser-console.json').write_text(json.dumps(errors, indent=2) + '\n')
        assert not errors
        proof.update(complete=True, browser_severe_errors=0)
    except BaseException:
        if driver is not None:
            driver.save_screenshot(str(output / 'browser-failure.png'))
            (output / 'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME, 'body').text)
        raise
    finally:
        if driver is not None:
            driver.quit()
        http.shutdown(); http.server_close(); thread.join(timeout=5)
        proof['owned_http_stopped'] = not thread.is_alive()
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mysql-shell', type=Path, required=True)
    parser.add_argument('--mysql-binlog', type=Path, required=True)
    parser.add_argument('--use-c', action='store_true')
    parser.add_argument('--browser-binary'); parser.add_argument('--driver-binary')
    args = parser.parse_args()
    qualify(args.output, args.mysql_shell, args.mysql_binlog, use_c=args.use_c,
            browser_binary=args.browser_binary, driver_binary=args.driver_binary)
