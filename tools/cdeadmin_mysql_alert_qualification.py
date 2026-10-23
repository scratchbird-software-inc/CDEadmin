"""Native MySQL alert lifecycle, dedicated observers and real TLS SMTP proof."""
import argparse
import base64
from email import policy as email_policy
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def register(app, route, password, use_c):
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    with app.test_request_context('/'):
        owner = User.query.first(); group = ServerGroup.query.filter_by(user_id=owner.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=owner.id)
        server = Server(user_id=owner.id, servergroup_id=group.id, name='Owned alerts '+str(use_c),
            host=route['host'], port=route['port'], username='root', maintenance_db='sr_alerts', save_password=0)
        server._cde_endpoint_registration = registration_profile('mysql-native')
        server._cde_endpoint_route_configuration = {**route, 'database': 'sr_alerts', 'user': 'root',
            'use_pure': not use_c, 'autocommit': True, 'credential_kinds': ['database_password']}
        db.session.add(server); db.session.commit(); target = str(uuid.uuid4())
        db.session.add(EndpointDatabaseTarget(id=target, endpoint_id=server.endpoint_profile.id,
            display_name='sr_alerts', database='sr_alerts', configuration='{}', active=1)); db.session.commit()
        sid, uid = server.id, owner.id
        verify = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=sid)
    client = app.test_client()
    with client.session_transaction() as session: session['_user_id'], session['_fresh'] = str(uid), True
    assert client.post(verify, json={'password': password}).get_json()['success']
    return sid, target, uid, client


def wait_for(callback, seconds=25):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = callback()
        if value: return value
        time.sleep(.05)
    raise AssertionError('Native alert condition timed out')


def qualify(output, browser_binary=None, driver_binary=None):
    import config
    from mysql_qualification_support import server, _root_connection
    from mysql_alert_qualification_support import smtp_sink
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from pgadmin.cdeadmin.providers.mysql_family.mysql_monitoring import MySQLMonitor
    from pgadmin.cdeadmin.workspace.mysql_alerts import measurement
    from pgadmin.cdeadmin.security import SecretLease
    from types import SimpleNamespace
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents: raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    paths = ['web/pgadmin/cdeadmin/workspace/mysql_alerts.py', 'web/pgadmin/cdeadmin/workspace/mysql_alert_delivery.py',
        'web/pgadmin/cdeadmin/workspace/mysql_monitoring_host.py', 'web/pgadmin/cdeadmin/workspace/monitoring.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_monitoring.py', 'web/pgadmin/static/js/Dialogs/MySQLAlerts.jsx',
        'web/pgadmin/static/js/Dialogs/MySQLMonitoring.jsx',
        'web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/mysqlDashboard.js',
        'web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs',
        str(Path(__file__).relative_to(ROOT)), 'tools/mysql_alert_qualification_support.py']
    proof = {'complete': False, 'history_testing': 'not run', 'interfaces': [],
        'source_sha256': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    owned = app = None
    try:
        with smtp_sink(output/'smtp') as (smtp, messages, modes):
            config.CDEADMIN_REPORT_DELIVERY_PROFILES = {'owned-alert-smtp': smtp}
            config.CDEADMIN_MONITORING_PROCESS_MODE = 'single'
            config.CDEADMIN_MONITORING_LOCK_PATH = str(output/'monitor.lock')
            config.CDEADMIN_MONITORING_WORKER_KEYS = {'k': base64.b64encode(os.urandom(32)).decode()}
            config.CDEADMIN_MONITORING_WORKER_ACTIVE_KEY_ID = 'k'
            with server(output/'fixture') as (route, _name, owned):
                oracle = _root_connection('mysql', route['port']); oracle.autocommit = True; cursor = oracle.cursor()
                try:
                    password = secrets.token_urlsafe(24)
                    cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                    cursor.execute('CREATE DATABASE sr_alerts'); cursor.execute('USE sr_alerts')
                    cursor.execute('CREATE TABLE t(id INT PRIMARY KEY,n INT)'); cursor.execute('INSERT INTO t VALUES(1,0)')
                    cursor.execute("CREATE USER 'limited_alert'@'%' IDENTIFIED BY %s", (password,))
                    cursor.execute("GRANT SELECT ON sr_alerts.* TO 'limited_alert'@'%'")
                    app = setup_application(output)
                    host = app.extensions['cdeadmin_mysql_monitoring_host']
                    for use_c in (False, True):
                        sid, target, uid, client = register(app, route, password, use_c)
                        app.config['CDEADMIN_MYSQL_ALERT_ROUTES'] = {'ops': {'label': 'Owned loopback operations',
                            'owner_ids': [uid], 'profile_id': 'owned-alert-smtp', 'target': {'recipients': ['ops@localhost']}}}
                        url = f'/cdeadmin/api/monitoring/mysql/{sid}?target_id={target}'
                        def call(method='get', body=None, path=url, expected=200):
                            response = getattr(client, method)(path, **({'json': body} if body is not None else {}))
                            assert response.status_code == expected, response.get_json()
                            assert response.headers['Cache-Control'] == 'no-store'
                            return response.get_json().get('data')
                        checks = []
                        before = call(); assert before['state'] == 'disabled' and before['alert_catalog']['routes']
                        assert not host._grants
                        rules = [{'id': 'busy', 'metric': 'threads_running', 'threshold': '0', 'duration_seconds': 5, 'route_id': 'ops'},
                            {'id': 'transaction', 'metric': 'oldest_transaction_seconds', 'threshold': '0', 'route_id': 'ops'}]
                        oracle.autocommit = False
                        cursor.execute('UPDATE t SET n=n+1 WHERE id=1'); cursor.execute('SAVEPOINT alert_guard')
                        cursor.execute("SELECT CAST('original warning' AS UNSIGNED)"); cursor.fetchall()
                        cursor.execute('SHOW COUNT(*) WARNINGS'); warnings = cursor.fetchone()[0]; assert warnings
                        started = call('post', {'interval_seconds': 5, 'mysql_alert_rules': rules,
                            'credentials': {'username': 'root', 'password': password}})
                        # No viewer read drives either sampling or event delivery.
                        time.sleep(11)
                        current = call(); assert len(current['samples']) >= 3, current
                        assert any(item['state'] == 'firing' for item in current['alerts']['rules'])
                        wait_for(lambda: any(e['delivery']['state'] == 'delivered' for e in call()['alerts']['events']))
                        current = call(); native = current['samples'][-1]
                        assert native['identity']['collector_id'] != str(oracle.connection_id)
                        grant = host._grants[(uid, sid, target)]
                        actual_connection = host.runtime._jobs[grant.policy.key].source._source._connection
                        assert ('CMySQLConnection' in type(actual_connection).__name__) == use_c
                        assert not actual_connection.in_transaction
                        assert measurement('connection_usage_percent', native)['status'] == 'available'
                        assert measurement('oldest_transaction_seconds', native)['value'] is not None
                        cursor.execute('SHOW COUNT(*) WARNINGS'); assert cursor.fetchone()[0] == warnings and oracle.in_transaction
                        cursor.execute('ROLLBACK TO SAVEPOINT alert_guard')
                        checks.append('native-pure-or-C-dedicated-collector-duration-fires-without-viewers-and-preserves-transaction-savepoint-warnings')
                        count = len(messages); previous = len(current['alerts']['events'])
                        silence_url = url
                        call('post', {'action': 'silence', 'rule_id': 'transaction', 'seconds': 60}, silence_url)
                        oracle.rollback(); oracle.autocommit = True
                        wait_for(lambda: any(e['transition'] == 'resolved' and e['rule_id'] == 'transaction' for e in call()['alerts']['events']))
                        current = call(); event = next(e for e in reversed(current['alerts']['events']) if e['rule_id'] == 'transaction')
                        assert event['delivery']['state'] == 'silenced' and len(messages) == count
                        assert len(current['alerts']['events']) == previous + 1
                        call('post', {'action': 'silence', 'rule_id': 'busy', 'seconds': 0}, silence_url)
                        wait_for(lambda: any(e['transition'] == 'firing-after-silence' and e['delivery']['state'] == 'delivered' for e in call()['alerts']['events']))
                        checks.append('native-resolution-silence-suppression-and-explicit-unsilence-one-delivery')
                        call('delete')
                        # Real SMTP authentication/TLS/JSON attachment, and an
                        # accepted DATA payload with no acknowledgement.
                        modes['drop_after_data'] = True
                        call('post', {'mysql_alert_rules': [{'id': 'uncertain', 'metric': 'threads_running', 'route_id': 'ops'}],
                            'credentials': {'username': 'root', 'password': password}})
                        wait_for(lambda: any(e['delivery']['state'] == 'outcome_unknown' for e in call()['alerts']['events']))
                        count = len(messages); time.sleep(5.2); assert len(messages) == count
                        call('delete'); modes['drop_after_data'] = False
                        decoded = [json.loads(next(BytesParser(policy=email_policy.default).parsebytes(raw).iter_attachments()).get_content()) for raw in messages]
                        assert decoded and all(m['schema'] == 'cdeadmin.mysql-alert.v1' for m in decoded)
                        assert password not in json.dumps(decoded) and 'owned-secret' not in json.dumps(decoded)
                        checks.append('real-loopback-TLS-authenticated-SMTP-JSON-and-unknown-outcome-without-retry')
                        permissions = SimpleNamespace(acquire_secret=lambda *_: SecretLease(password.encode()))
                        limited = MySQLMonitor(permissions, {**route, 'database': 'sr_alerts', 'user': 'limited_alert',
                            'use_pure': not use_c, 'credential_reference_id': 'owned', 'principal_reference': 'owned'})
                        try:
                            observed = limited.sample()
                            assert observed['groups']['alert_transactions']['status'] == 'unavailable'
                            assert measurement('oldest_transaction_seconds', observed)['value'] is None
                        finally: limited.close()
                        checks.append('native-denied-metrics-remain-unavailable-without-fabricated-health')
                        # Native receiver/applier state is measured even when
                        # a configured channel cannot reach its source.
                        cursor.execute("CHANGE REPLICATION SOURCE TO SOURCE_HOST='127.0.0.1',SOURCE_PORT=1,SOURCE_USER='owned',SOURCE_PASSWORD='owned',SOURCE_AUTO_POSITION=1 FOR CHANNEL 'owned_alert'")
                        observer = MySQLMonitor(permissions, {**route, 'database': 'sr_alerts', 'user': 'root', 'use_pure': not use_c,
                            'credential_reference_id': 'owned', 'principal_reference': 'owned'})
                        try:
                            stopped = observer.sample(); assert measurement('replication_stopped', stopped)['value'] == '2'
                            cursor.execute("START REPLICA FOR CHANNEL 'owned_alert'"); time.sleep(1)
                            broken = observer.sample(); assert measurement('replication_errors', broken)['value'] != '0'
                            cursor.execute('FLUSH STATUS')
                            reset = observer.sample()
                            assert reset['rates']['status'] == 'unavailable', reset['rates']
                            assert measurement('slow_queries_per_second', reset)['value'] is None
                        finally:
                            observer.close(); cursor.execute("STOP REPLICA FOR CHANNEL 'owned_alert'"); cursor.execute("RESET REPLICA ALL FOR CHANNEL 'owned_alert'")
                        checks.append('native-configured-stopped-and-failed-replication-channel-evidence')
                        checks.append('native-FLUSH-STATUS-breaks-rate-baseline-without-zero-fallback')
                        import mysql.connector
                        import threading
                        blocked = mysql.connector.connect(**{**route, 'password': password, 'use_pure': not use_c, 'autocommit': False})
                        finished = threading.Event()
                        def contend():
                            try:
                                with blocked.cursor() as waiting:
                                    waiting.execute('SET innodb_lock_wait_timeout=10')
                                    waiting.execute('UPDATE sr_alerts.t SET n=n+1 WHERE id=1')
                            finally:
                                blocked.rollback(); finished.set()
                        oracle.autocommit = False; cursor.execute('UPDATE t SET n=n+1 WHERE id=1')
                        thread = threading.Thread(target=contend, daemon=True); thread.start()
                        lock_observer = MySQLMonitor(permissions, {**route, 'database': 'sr_alerts', 'user': 'root', 'use_pure': not use_c,
                            'credential_reference_id': 'owned', 'principal_reference': 'owned'})
                        try:
                            wait_for(lambda: measurement('lock_waits', lock_observer.sample())['value'] not in {None, '0'}, seconds=8)
                        finally:
                            oracle.rollback(); oracle.autocommit = True
                            assert finished.wait(5); thread.join(timeout=5); blocked.close(); lock_observer.close()
                        checks.append('native-InnoDB-blocked-writer-produces-lock-wait-evidence-and-releases-both-transactions')
                        # A changed registration revokes collector, view and
                        # silence authority; owner cleanup remains possible.
                        call('post', {'mysql_alert_rules': [{'id': 'busy', 'metric': 'threads_running'}],
                            'credentials': {'username': 'root', 'password': password}})
                        from pgadmin.model import db, EndpointDatabaseTarget
                        with app.app_context():
                            db.session.get(EndpointDatabaseTarget, target).configuration = '{"changed":true}'; db.session.commit()
                        call(expected=403)
                        call('post', {'action': 'silence', 'rule_id': 'busy', 'seconds': 60}, silence_url, expected=403)
                        call('delete')
                        call(path='/cdeadmin/api/monitoring/mysql/2147483647', expected=403)
                        checks.append('live-registration-revocation-blocks-old-observations-and-silence-with-owner-cleanup')
                        proof['interfaces'].append({'use_c': use_c, 'complete': True, 'checks': checks})
                    if browser_binary:
                        with app.app_context():
                            db.session.get(EndpointDatabaseTarget, target).configuration = '{}'; db.session.commit()
                        proof['browser'] = browser(app, output, sid, target, uid, password, browser_binary, driver_binary)
                    proof['smtp_messages'] = len(messages)
                    proof['complete'] = True
                finally:
                    oracle.rollback(); cursor.close(); oracle.close()
                    if app is not None: proof['collector_closed'] = app.extensions['cdeadmin_monitoring_host'].close()
    finally:
        proof['owned_server_stopped'] = bool(owned and owned.get('owned_server_stopped'))
        (output/'summary.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


def browser(app, output, sid, target, uid, password, binary, driver_binary):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, wait_for_tree_item, invoke_context_action, complete_endpoint_prompt
    http = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    driver = None; checks = []
    try:
        options = webdriver.ChromeOptions(); options.binary_location = binary
        for flag in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1800,1600'): options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'))
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        driver = webdriver.Chrome(options=options, service=Service(driver_binary))
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait = WebDriverWait(driver, 90); ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'MySQL')
        def owned(browser):
            return next((n for n in browser.find_elements(By.CSS_SELECTOR, '.file-name') if n.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', n, sid)), None)
        label = wait.until(owned).text; expand(wait, label, ('Connectors', 'MySQL'))
        if complete_endpoint_prompt(driver, password, timeout=5): expand(wait, label, ('Connectors', 'MySQL'))
        def open_panel(action):
            database = wait_for_tree_item(wait, 'sr_alerts', ('Connectors', 'MySQL', label))
            invoke_context_action(wait, driver, database, ('Availability', action), handle_endpoint_prompt=False)
            complete_endpoint_prompt(driver, password, timeout=5)
        def click(text):
            item = wait.until(lambda b: next((e for e in b.find_elements(By.TAG_NAME, 'button') if e.is_displayed() and e.is_enabled() and e.text == text), None))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});', item); item.click()
        def field(text):
            def ready(browser):
                label = browser.find_element(By.XPATH, '//label[text()="'+text+'"]')
                node = browser.find_element(By.ID, label.get_attribute('for'))
                return node if node.is_displayed() and node.is_enabled() else None
            item = wait.until(ready); driver.execute_script('arguments[0].scrollIntoView({block:"center"});', item); return item
        open_panel('Configure monitoring collection...'); click('Add alert rule')
        field('Notification route 1').click()
        wait.until(lambda b: next((n for n in b.find_elements(By.CSS_SELECTOR, '[role="option"]') if n.is_displayed() and n.text == 'Owned loopback operations'), None)).click()
        click('Start collection')
        wait.until(lambda b: 'rule-1: firing' in b.find_element(By.TAG_NAME, 'body').text and 'Delivery: delivered' in b.find_element(By.TAG_NAME, 'body').text)
        driver.save_screenshot(str(output/'native-alert-firing.png'))
        checks.append('built-rule-editor-start-native-firing-and-actual-delivery-receipt')
        node = field('Silence seconds'); node.send_keys(Keys.CONTROL, 'a'); node.send_keys(Keys.BACKSPACE); node.send_keys('45')
        click('Silence rule-1'); wait.until(lambda b: 'rule-1: silenced' in b.find_element(By.TAG_NAME, 'body').text)
        click('Unsilence rule-1')
        wait.until(lambda b: 'firing-after-silence' in b.find_element(By.TAG_NAME, 'body').text)
        checks.append('built-native-silence-and-unsilence-lifecycle')
        open_panel('MySQL database dashboard...')
        wait.until(lambda b: any(n.is_displayed() and n.text == 'Display' for n in b.find_elements(By.TAG_NAME, 'label')))
        # The paired DDN host embeds its rendered SVG as an image, so inspect
        # the image payload rather than searching for inline SVG DOM nodes.
        from urllib.parse import unquote
        wait.until(lambda b: any('MySQL alert findings' in unquote(img.get_attribute('src')) and
            'firing' in unquote(img.get_attribute('src')) for img in b.find_elements(By.CSS_SELECTOR, '[aria-label="DDN diagram"] img')))
        assert not [n for n in driver.find_elements(By.TAG_NAME, 'button') if n.is_displayed() and n.text in {'Add alert rule', 'Start collection', 'Silence rule-1'}]
        driver.save_screenshot(str(output/'native-alert-viewer.png'))
        checks.append('built-dashboard-viewer-exposes-no-alert-administration')
        open_panel('Configure monitoring collection...'); click('Stop collection')
        wait.until(lambda b: any(n.is_enabled() and n.text == 'Start collection' for n in b.find_elements(By.TAG_NAME, 'button')))
        checks.append('built-owned-collector-stop-and-release')
        errors = [r for r in driver.get_log('browser') if r['level'] == 'SEVERE']; assert not errors, errors
        return {'complete': True, 'checks': checks, 'console_errors': errors}
    except Exception:
        if driver:
            driver.save_screenshot(str(output/'browser-failure.png'))
            (output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME, 'body').text)
        raise
    finally:
        if driver: driver.quit()
        http.shutdown(); thread.join(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True)
    parser.add_argument('--browser-binary'); parser.add_argument('--driver-binary')
    args = parser.parse_args()
    qualify(args.output, args.browser_binary, args.driver_binary)
