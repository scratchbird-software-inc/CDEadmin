"""Owned native MySQL server log reset, lost replies and offline receipts."""
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


def qualify(output, *, mysql_binlog, use_c=False, gtid_mode='ON', binary_logging=True, browser_binary=None, driver_binary=None):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Keep native evidence outside source')
    output.mkdir(parents=True, exist_ok=False)
    os.environ['CDEADMIN_MYSQL_BINLOG_BINARY'] = str(Path(mysql_binlog).resolve(strict=True))
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app = setup_application(output)
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from pgadmin.cdeadmin.providers.mysql_family import mysql_log_reset as native
    from mysql_qualification_support import server, _root_connection
    from mysql.connector.errors import OperationalError
    client = app.test_client(); service = service_for_app(app)
    proof = {'complete': False, 'history_testing': 'not run', 'checks': [], 'gtid_mode': gtid_mode,
             'binary_logging': binary_logging, 'mysql_interface': 'c' if use_c else 'pure', 'source_sha256': {}}
    for name in ('web/pgadmin/cdeadmin/providers/mysql_family/mysql_log_reset.py',
                 'web/pgadmin/cdeadmin/workspace/mysql_log_reset.py',
                 'tools/mysql_qualification_support.py',
                 'web/pgadmin/cdeadmin/providers/mysql_family/mysql_log_purge.py',
                 'web/pgadmin/cdeadmin/workspace/mysql_log_purge.py',
                 'web/pgadmin/cdeadmin/workspace/mysql_binlog_service.py',
                 'web/pgadmin/browser/server_groups/servers/__init__.py',
                 'web/pgadmin/static/js/Dialogs/MySQLSourceLogs.jsx',
                 'web/pgadmin/static/js/Dialogs/MySQLBinlogArchives.jsx',
                 'tools/cdeadmin_mysql_source_log_reset_qualification.py'):
        proof['source_sha256'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    password = 'native-purge-' + secrets.token_urlsafe(24)
    try:
        with server(output / 'fixture', gtid_mode=gtid_mode, binary_logging=binary_logging) as (route, _native_name, fixture):
            root = _root_connection('mysql', route['port']); root.autocommit = True; query = root.cursor()
            try:
                query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                query.execute('CREATE DATABASE sr_source_purge')
                query.execute('CREATE TABLE sr_source_purge.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
                query.execute('INSERT INTO sr_source_purge.t VALUES(9007199254740993,"native 雪",X\'00FF\'),(9007199254740994,"second",NULL)')
                query.execute("CREATE USER 'sr_log_reader'@'%' IDENTIFIED BY %s", (password,))
                query.execute("GRANT REPLICATION CLIENT ON *.* TO 'sr_log_reader'@'%'")
                if binary_logging:
                    for _ in range(3): query.execute('FLUSH BINARY LOGS')
                elif gtid_mode == 'ON':
                    query.execute("SET GLOBAL gtid_purged=CONCAT(@@server_uuid,':1-4')")
                with app.test_request_context('/'):
                    user = User.query.first(); uid = user.id
                    group = ServerGroup.query.filter_by(user_id=uid).order_by(ServerGroup.id).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=uid)
                    def register(label, username):
                        item = Server(user_id=uid, servergroup_id=group.id, name=label, host=route['host'],
                            port=route['port'], username=username, maintenance_db=None, save_password=0)
                        item._cde_endpoint_registration = registration_profile('mysql-native')
                        item._cde_endpoint_route_configuration = {**route, 'user': username, 'use_pure': not use_c,
                                                                 'credential_kinds': ['database_password']}
                        db.session.add(item); db.session.commit()
                        return item.id, url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=item.id), url_for('NODE-server.cde_workspace_id', gid=group.id, sid=item.id)
                    sid, verify_url, url = register('Owned MySQL source reset', 'root')
                    _reader_id, reader_verify, reader_url = register('Owned log reader', 'sr_log_reader')
                with client.session_transaction() as session:
                    session['_user_id'] = str(uid); session['_fresh'] = True
                assert client.post(verify_url, json={'password': password}).get_json()['success']
                assert client.post(reader_verify, json={'password': password}).get_json()['success']
                def http(action, request, *, target=None, prefix='mysql_binlog_source_reset_', refused=False):
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
                def wait(value, *, prefix='mysql_binlog_source_reset_', expected='native_acknowledged', target=None):
                    deadline = time.monotonic() + 60
                    while value['state'] in {'active', 'dispatching', 'cancel_requested'}:
                        if time.monotonic() > deadline: raise TimeoutError('Native source log job deadline')
                        time.sleep(.05); value = http('status', {'job_id': value['job_id']}, prefix=prefix, target=target)
                    assert value['state'] == expected, value
                    return value
                initial = http('catalog', {})
                archives = archive_record = archive_before = None
                if binary_logging:
                    first = initial['logs'][0]['Log_name']
                    raw = http('review', {'options': {'log_names': [first]}}, prefix='mysql_raw_binlog_')
                    archive = wait(http('start', request(raw), prefix='mysql_raw_binlog_'), prefix='mysql_raw_binlog_', expected='completed')
                    archives = service.mysql_raw_binlog_jobs
                    archive_record = archives.load(archive['job_id'], uid, archive['endpoint_id'])
                    archive_before = archives.native_verify(archives.directory(archive_record) / 'archive', archive_record['source'])
                reviewed = http('review', {'options': {'to_sequence': 7}})
                http('start', {**request(reviewed), 'confirmed': False}, refused=True)
                http('status', {'job_id': reviewed['job_id']}, target=reader_url, refused=True)
                assert http('cancel', {'job_id': reviewed['job_id']})['state'] == 'cancelled'
                assert http('start', request(reviewed))['state'] == 'cancelled'
                assert http('catalog', {}) == initial
                proof['checks'].append('explicit-confirmation-owner-endpoint-and-pre-dispatch-cancellation-without-native-reset')
                reviewed = http('review', {'options': {'to_sequence': 7}})
                if binary_logging:
                    query.execute('FLUSH BINARY LOGS')
                else:
                    query.execute("SET GLOBAL gtid_purged=CONCAT(@@server_uuid,':1-5')")
                http('start', request(reviewed), refused=True)
                http('cancel', {'job_id': reviewed['job_id']})
                proof['checks'].append('changed-native-log-or-GTID-state-refuses-reviewed-reset-before-dispatch')
                reviewed = http('review', {'options': {}}, target=reader_url)
                denied = wait(http('start', request(reviewed), target=reader_url), expected='native_failed', target=reader_url)
                assert denied['result']['native_error']['errno'] == 1227 and denied['result']['native_error_returned']
                proof['checks'].append('actual-native-RELOAD-denial-without-privilege-substitution')
                query.execute('UPDATE sr_source_purge.t SET body=CONCAT(body,"!")')
                query.execute('SET GLOBAL super_read_only=ON')
                try:
                    reviewed = http('review', {'options': {'to_sequence': 7}})
                    result = wait(http('start', request(reviewed)))
                    query.execute('SELECT ROW_COUNT()'); assert query.fetchone()[0] == 0
                    assert result['native_acknowledged'] and result['result']['gtid_executed_empty_observed'] and result['result']['gtid_purged_empty_observed']
                    assert result['cancel_capability']['available']
                    if binary_logging:
                        query.execute('SHOW BINARY LOGS'); logs = query.fetchall()
                        assert len(logs) == 1 and logs[0][0].endswith('.000007')
                    else:
                        assert result['result']['after']['status'] == 'native_binary_logging_disabled'
                    query.execute('SELECT @@global.gtid_executed,@@global.gtid_purged'); assert query.fetchone() == ('', '')
                    (output / 'native-reset-receipt.json').write_text(json.dumps(result, indent=2)+'\n')
                finally:
                    query.execute('SET GLOBAL super_read_only=OFF');query.execute('SET GLOBAL read_only=OFF')
                proof['checks'].append('native-RESET-TO-clears-executed-and-purged-GTIDs-in-super-read-only-with-independent-observation')
                reviewed = http('review', {'options': {}})
                completed = wait(http('start', request(reviewed)))
                if binary_logging:
                    assert len(completed['result']['after']['logs']) == 1 and completed['result']['after']['current']['File'].endswith('.000001')
                assert completed['result']['filename_reuse_does_not_identify_original_log_files']
                proof['checks'].append('native-default-reset-retains-explicit-filename-reuse-and-generation-limits')
                original = native.Transport.execute; deliveries = []
                class LostReplyCursor:
                    def __init__(self, cursor): self.cursor = cursor
                    def __getattr__(self, name): return getattr(self.cursor, name)
                    def execute(self, source, parameters=()):
                        value = self.cursor.execute(source, parameters)
                        if source.startswith('RESET BINARY LOGS AND GTIDS'):
                            deliveries.append(source)
                            raise OperationalError('Owned suppressed native reset reply', errno=2013, sqlstate='HY000')
                        return value
                def lost(transport, *args, **kwargs):
                    assert transport.worker not in transport.client._connections and transport.monitor not in transport.client._connections
                    cursor = transport.worker.cursor
                    transport.worker.cursor = lambda *a, **k: LostReplyCursor(cursor(*a, **k))
                    try: return original(transport, *args, **kwargs)
                    finally: transport.worker.cursor = cursor
                native.Transport.execute = lost
                try:
                    reviewed = http('review', {'options': {'to_sequence': 17}})
                    uncertain = wait(http('start', request(reviewed)), expected='unknown')
                finally: native.Transport.execute = original
                assert len(deliveries) == 1 and not uncertain['native_acknowledged']
                reconciled = http('reconcile', {'job_id': uncertain['job_id']})
                assert reconciled['state'] == 'unknown' and not reconciled['reconciliation']['native_log_generation_attested']
                assert http('start', request(reviewed))['state'] == 'unknown' and len(deliveries) == 1
                (output / 'unknown-reconciled.json').write_text(json.dumps(reconciled, indent=2)+'\n')
                proof['checks'].append('fault-injected-lost-reply-after-real-reset-remains-unknown-through-reconciliation-and-duplicate-start')
                observe = native.Transport.observe
                def failed_observation(_transport): raise OSError('Owned post-acknowledgement observation failure')
                native.Transport.observe = failed_observation
                try:
                    reviewed = http('review', {'options': {'to_sequence': 23}})
                    acknowledged = wait(http('start', request(reviewed)))
                finally: native.Transport.observe = observe
                assert acknowledged['native_acknowledged'] and acknowledged['result']['postcondition_error']['type'] == 'OSError'
                http('reconcile', {'job_id': acknowledged['job_id']})
                proof['checks'].append('actual-native-acknowledgement-survives-fault-injected-later-observation-failure')
                if browser_binary:
                    proof['browser'] = browser(app, output, sid, password, browser_binary, driver_binary)
                query.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_source_purge.t ORDER BY id')
                assert query.fetchall() == [('9007199254740993', 'native 雪!', '00FF'), ('9007199254740994', 'second!', None)]
                if archives is not None:
                    assert archives.native_verify(archives.directory(archive_record) / 'archive', archive_record['source']) == archive_before
                proof['checks'].append('independent-wide-Unicode-BLOB-data-and-existing-application-archive-bytes-preserved')
                proof.update(complete=True, native_version=fixture['engine_version'])
            finally:
                for attribute in ('mysql_source_log_reset_jobs', 'mysql_raw_binlog_jobs'):
                    jobs = getattr(service, attribute, None)
                    if jobs is not None: assert jobs.close()
                query.close(); root.close()
        proof['owned_server_stopped'] = fixture['owned_server_stopped']
    finally:
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def browser(app, output, sid, password, binary, driver_binary):
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
        section = wait.until(lambda browser: browser.find_element(By.XPATH, '//summary[normalize-space()="Reset native binary logs and GTID history"]'))
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', section); section.click()
        click('Inspect source log and GTID reset catalog')
        click('Review native server log and GTID reset')
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, '[aria-label="Native source log and GTID reset review"]'))
        checkbox = driver.find_element(By.XPATH, '//label[contains(normalize-space(),"I checked backups, replicas and receivers")]//input')
        driver.execute_script('arguments[0].click()', checkbox)
        click('Confirm native server log and GTID reset')
        wait.until(lambda browser: any('Source log and GTID reset ' in node.get_attribute('textContent') and ': native_acknowledged.' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        click('Reconcile source log and GTID reset')
        details = driver.find_element(By.XPATH, '//summary[normalize-space()="Native source log and GTID reset observations"]')
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', details); details.click()
        wait.until(lambda browser: 'original_acknowledgement_unchanged' in browser.find_element(By.CSS_SELECTOR, '[aria-label="Native source log and GTID reset receipt"]').get_attribute('textContent'))
        driver.save_screenshot(str(output / 'native-source-log-reset.png'))
        errors = [entry for entry in driver.get_log('browser') if entry['level'] == 'SEVERE']
        (output / 'browser-console.json').write_text(json.dumps(errors, indent=2) + '\n')
        assert not errors
        return {'complete': True, 'console_errors': 0, 'native_reset_review_confirm_acknowledgement_and_reconciliation': True}
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
    parser.add_argument('--mysql-binlog', required=True)
    parser.add_argument('--use-c', action='store_true')
    parser.add_argument('--gtid-mode', choices=['ON','OFF'], default='ON')
    parser.add_argument('--no-binary-logging', action='store_true')
    parser.add_argument('--browser-binary')
    parser.add_argument('--driver-binary')
    args = parser.parse_args()
    result = qualify(args.output, mysql_binlog=args.mysql_binlog, use_c=args.use_c, gtid_mode=args.gtid_mode,
                     binary_logging=not args.no_binary_logging, browser_binary=args.browser_binary, driver_binary=args.driver_binary)
    print(json.dumps({'complete': result['complete'], 'checks': len(result['checks'])}))
