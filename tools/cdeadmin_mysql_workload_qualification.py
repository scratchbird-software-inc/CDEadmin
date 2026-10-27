"""Native MySQL workload ranking/privacy/slow-log/observer and desktop proof."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def registration(app, route, password, use_c, username='root'):
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    with app.test_request_context('/'):
        user = User.query.first()
        group = ServerGroup.query.filter_by(user_id=user.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=user.id)
        item = Server(user_id=user.id, servergroup_id=group.id, name='Owned workload '+username+' '+str(use_c),
            host=route['host'], port=route['port'], username=username, maintenance_db='sr_workload', save_password=0)
        item._cde_endpoint_registration = registration_profile('mysql-native')
        item._cde_endpoint_route_configuration = {**{k: v for k, v in route.items() if k != 'password'},
            'database': 'sr_workload', 'user': username, 'use_pure': not use_c, 'autocommit': True, 'credential_kinds': ['database_password']}
        db.session.add(item); db.session.commit()
        target = str(uuid.uuid4())
        db.session.add(EndpointDatabaseTarget(id=target, endpoint_id=item.endpoint_profile.id,
            display_name='sr_workload', database='sr_workload', configuration='{}', active=1)); db.session.commit()
        sid, uid = item.id, user.id
        url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=sid)
        verify = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=sid)
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'], session['_fresh'] = str(uid), True
    assert client.post(verify, json={'password': password}).get_json()['success']
    def post(operation, request, error=False):
        response = client.post(url, json={'action': 'mysql_workload_'+operation, 'request': request})
        value = response.get_json()
        if error:
            assert not value.get('success'), value
        else:
            assert response.status_code == 200 and value.get('success'), value
            assert response.headers['Cache-Control'] == 'no-store'
        return value.get('data') if not error else value
    return sid, post


def qualify(output, browser_binary=None, driver_binary=None):
    import config  # noqa: F401
    from mysql_qualification_support import server, _root_connection
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from pgadmin.cdeadmin.providers.mysql_family import mysql_workload as native
    from pgadmin.cdeadmin.providers.mysql_family.mysql_monitoring import MySQLMonitor
    from pgadmin.cdeadmin.security import SecretLease
    from types import SimpleNamespace
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Native evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    proof = {'complete': False, 'history_testing': 'not run', 'interfaces': [], 'source_sha256': {
        path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in [
            'tools/cdeadmin_mysql_workload_qualification.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mysql_workload.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mysql_monitoring.py',
            'web/pgadmin/cdeadmin/workspace/mysql_workload_service.py',
            'web/pgadmin/static/js/Dialogs/MySQLWorkload.jsx']}}
    owned = None
    try:
        with server(output/'fixture') as (route, _name, owned):
            oracle = _root_connection('mysql', route['port']); oracle.autocommit = True
            cursor = oracle.cursor()
            try:
                cursor.execute('CREATE DATABASE sr_workload')
                cursor.execute('CREATE TABLE sr_workload.t(id INT PRIMARY KEY, label VARCHAR(80), KEY(label))')
                cursor.executemany('INSERT INTO sr_workload.t VALUES(%s,%s)', [(1, 'private literal'), (2, 'second')])
                cursor.execute("UPDATE performance_schema.setup_consumers SET ENABLED='YES' WHERE NAME IN ('events_waits_current','events_waits_history_long','events_statements_current','events_statements_history_long')")
                cursor.execute("UPDATE performance_schema.setup_instruments SET ENABLED='YES',TIMED='YES' WHERE NAME LIKE 'wait/%%'")
                cursor.execute("SET GLOBAL log_output='TABLE,FILE'")
                cursor.execute('SET GLOBAL slow_query_log=ON')
                cursor.execute('USE sr_workload')
                cursor.execute('SET SESSION long_query_time=0')
                for i in range(4):
                    cursor.execute('SELECT id,label FROM t WHERE id=%s', (1,)); cursor.fetchall()
                cursor.execute('SELECT SLEEP(0.002),label FROM t ORDER BY label'); cursor.fetchall()
                cursor.execute("SELECT CAST('workload warning' AS UNSIGNED)"); cursor.fetchall()
                cursor.execute('SHOW WARNINGS'); warnings = cursor.fetchall(); assert warnings
                password = secrets.token_urlsafe(24)
                cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                cursor.execute("CREATE USER 'sr_workload_limited'@'%' IDENTIFIED BY %s", (password,))
                cursor.execute("GRANT SELECT ON sr_workload.* TO 'sr_workload_limited'@'%'")
                app = setup_application(output)
                for use_c in (False, True):
                    sid, post = registration(app, route, password, use_c)
                    checks = []
                    snapshots = []
                    for rank, field in native.RANKS.items():
                        result = post('snapshot', {'schema_name': 'sr_workload', 'rank': rank})
                        rows = result['groups']['workload_digests']['rows']
                        assert rows and all(r['schema_name'] == 'sr_workload' for r in rows)
                        assert all(int(a[field.lower()]) >= int(b[field.lower()]) for a, b in zip(rows, rows[1:]))
                        assert 'private literal' not in json.dumps(result) and 'query_sample_text' not in json.dumps(result)
                        assert result['groups']['workload_indexes']['status'] == 'available'
                        assert result['groups']['workload_waits']['scope'] == 'server'
                        assert all(r['enabled_count'].isdigit() and r['timed_count'].isdigit()
                            for r in result['groups']['workload_instruments']['rows'])
                        snapshots.append(result)
                    checks.append('six-native-rankings-scoped-and-private-samples-excluded')
                    result = snapshots[0]
                    selected = next(r for r in result['groups']['workload_digests']['rows']
                        if r['digest_text'].startswith('SELECT `id` , `label` FROM `t`'))
                    selected = {k: selected[k] for k in ('schema_name', 'digest')}
                    failure = post('sample', selected, error=True)
                    assert 'Explicit private' in failure['errormsg']
                    sample = post('sample', {**selected, 'confirmed': True})
                    assert 'private literal' not in sample['query_sample_text']  # selected source uses id literal
                    plan = post('plan', {**selected, 'confirmed': True, 'sample_sha256': sample['sample_sha256']})
                    assert 'query_block' in plan['rendered']['view_model']['rows'][0][0] or 'query_plan' in plan['rendered']['view_model']['rows'][0][0]
                    assert 'changed' in post('plan', {**selected, 'confirmed': True, 'sample_sha256': 'stale'}, error=True)['errormsg']
                    waits = post('waits', selected)
                    assert waits['groups']['direct_statement_waits']['status'] == 'available'
                    assert 'retained' in waits['coverage']
                    checks.append('explicit-private-sample-fingerprint-plan-and-direct-waits')
                    window = {'schema_name': 'sr_workload', 'start_utc': '2026-01-01T00:00:00Z', 'end_utc': '2026-01-02T00:00:00Z'}
                    cursor.execute('SELECT UTC_TIMESTAMP()'); now = cursor.fetchone()[0]
                    from datetime import timedelta
                    window.update(start_utc=(now-timedelta(hours=1)).isoformat()+'Z', end_utc=(now+timedelta(hours=1)).isoformat()+'Z')
                    slow = post('slow_table', {**window, 'confirmed': True})
                    assert slow['entries'] > 0 and 'private literal' not in json.dumps(slow)
                    cursor.execute('SELECT @@slow_query_log_file'); log_path = cursor.fetchone()[0]
                    raw_file = subprocess.run(['docker', 'exec', _name, 'cat', log_path], check=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode('utf8', errors='strict')
                    real_file = post('slow_file', {**window, 'text': raw_file, 'confirmed': True})
                    assert real_file['entries'] > 0 and real_file['normalized_entries'] > 0
                    assert 'private literal' not in json.dumps(real_file)
                    text = ('# Time: '+now.isoformat()+'Z\n# User@Host: root[root] @ localhost [] Id: 1\n'
                        '# Query_time: 0.123456 Lock_time: 0.000001 Rows_sent: 1 Rows_examined: 2\n'
                        "use sr_workload;\nSET timestamp=1;\nUPDATE sr_workload.t SET label='import must not execute' WHERE id=2;\n")
                    slow_file = post('slow_file', {**window, 'text': text, 'confirmed': True})
                    assert slow_file['entries'] == 1 and slow_file['rows'][0]['total_seconds'] == '0.123456'
                    assert 'import must not execute' not in json.dumps(slow_file)
                    cursor.execute('SELECT label FROM sr_workload.t WHERE id=2'); assert cursor.fetchone()[0] == 'second'
                    checks.append('native-table-and-file-log-analysis-without-executing-imported-SQL')
                    permissions = SimpleNamespace(acquire_secret=lambda *_: SecretLease(password.encode('utf8')))
                    observer = MySQLMonitor(permissions, {**route, 'password': None, 'database': 'sr_workload', 'use_pure': not use_c,
                        'credential_reference_id': 'owned-workload-secret', 'principal_reference': 'owned-workload-operator'})
                    try:
                        cursor.execute('SET autocommit=0')
                        cursor.execute("INSERT INTO t VALUES(9,'pending')")
                        cursor.execute('SAVEPOINT workload_guard')
                        cursor.execute("SELECT CAST('original warning' AS UNSIGNED)"); cursor.fetchall()
                        observed = observer.sample()
                        assert observed['transaction_completed'] and observed['groups']['workload_digests']['rows']
                        connection_class = type(observer._connection).__name__
                        assert connection_class == ('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')
                        cursor.execute('SHOW WARNINGS'); assert cursor.fetchall()
                        cursor.execute('ROLLBACK TO SAVEPOINT workload_guard')
                        cursor.execute('ROLLBACK')
                        cursor.execute('SELECT COUNT(*) FROM t WHERE id=9'); assert cursor.fetchone()[0] == 0
                        before = observer.sample()
                        cursor.execute('TRUNCATE performance_schema.events_statements_summary_by_digest')
                        cursor.execute('SELECT id,label FROM t WHERE id=1'); cursor.fetchall()
                        observer._metadata_clock = None
                        after = observer.sample()
                        assert after['workload_reset']['state'] == 'reset-observed', after['workload_reset']
                        assert all('query_sample_text' not in str(g) for g in observed['groups'].values())
                    finally:
                        observer.close(); cursor.execute('SET autocommit=1')
                    checks.append('collector-isolation-diagnostics-savepoint-rollback-and-native-reset')
                    denied_sid, denied = registration(app, route, password, use_c, 'sr_workload_limited')
                    limited = denied('snapshot', {'schema_name': 'sr_workload'})
                    assert limited['groups']['workload_digests']['status'] == 'unavailable'
                    assert limited['groups']['workload_digests']['error_code'] == 1142
                    assert limited['identity']['account'].startswith('sr_workload_limited@')
                    checks.append('native-denied-profile-remains-unavailable-not-zero')
                    cursor.execute("UPDATE performance_schema.setup_consumers SET ENABLED='NO' WHERE NAME='statements_digest'")
                    try:
                        disabled = post('snapshot', {'schema_name': 'sr_workload'})
                        consumers = disabled['groups']['workload_consumers']['rows']
                        assert next(r for r in consumers if r['name'] == 'statements_digest')['enabled'] == 'NO'
                    finally:
                        cursor.execute("UPDATE performance_schema.setup_consumers SET ENABLED='YES' WHERE NAME='statements_digest'")
                    checks.append('native-disabled-instrumentation-remains-explicit')
                    proof['interfaces'].append({'use_c': use_c, 'native_connection_class': connection_class, 'complete': True, 'checks': checks})
                    (output/('snapshot-'+str(use_c)+'.json')).write_text(json.dumps(result, indent=2)+'\n')
                if browser_binary:
                    proof['browser'] = browser(app, output, sid, password, browser_binary, driver_binary, window)
                proof['complete'] = True
            finally:
                cursor.close(); oracle.close()
    finally:
        proof['owned_server_stopped'] = bool(owned and owned['owned_server_stopped'])
        proof['complete'] = proof['complete'] and proof['owned_server_stopped']
        (output/'summary.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


def browser(app, output, sid, password, binary, driver_binary, window):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, invoke_context_action, complete_endpoint_prompt
    http = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    driver = None
    try:
        options = webdriver.ChromeOptions(); options.binary_location = binary
        for flag in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1800,1200'):
            options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'))
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        driver = webdriver.Chrome(options=options, service=Service(driver_binary))
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait = WebDriverWait(driver, 90)
        ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'MySQL')
        def owned(browser):
            return next((n for n in browser.find_elements(By.CSS_SELECTOR, '.file-name') if n.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', n, sid)), None)
        item = wait.until(owned)
        name = item.text
        expand(wait, name, ('Connectors', 'MySQL'))
        if complete_endpoint_prompt(driver, password, timeout=5):
            expand(wait, name, ('Connectors', 'MySQL'))
        item = wait.until(owned)
        invoke_context_action(wait, driver, item, ('Diagnostics and verification', 'MySQL workload analysis...'), handle_endpoint_prompt=False)
        complete_endpoint_prompt(driver, password, timeout=10)
        def click(label):
            node = wait.until(lambda b: next((n for n in b.find_elements(By.TAG_NAME, 'button') if n.is_displayed() and n.is_enabled() and n.text == label), None))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});', node); node.click()
        schema = wait.until(lambda b: b.find_element(By.XPATH, '//label[contains(text(),"Schema (blank for server)")]/following-sibling::div/input'))
        schema.send_keys('sr_workload'); click('Refresh workload')
        wait.until(lambda b: len(b.find_elements(By.CSS_SELECTOR, '[aria-label="Ranked native statement digests"] tbody tr')) > 0)
        image = wait.until(lambda b: b.find_element(By.CSS_SELECTOR, '[aria-label="MySQL workload analysis"] [data-cde-surface="diagram.ddn.viewer"] img'))
        svg = driver.execute_script('return decodeURIComponent(arguments[0].src.split(",").slice(1).join(","));', image)
        assert 'MySQL workload coverage' in svg
        candidates = driver.find_elements(By.CSS_SELECTOR, '[aria-label="Ranked native statement digests"] tbody tr')
        row = next(r for r in candidates if 'SELECT `id` , `label` FROM `t`' in r.text)
        node = row.find_element(By.TAG_NAME, 'button'); driver.execute_script('arguments[0].scrollIntoView({block:"center"});', node); node.click()
        click('Inspect retained direct waits')
        wait.until(lambda b: 'Only directly nested waits' in b.find_element(By.TAG_NAME, 'body').text)
        label = driver.find_element(By.XPATH, '//label[contains(. ,"Allow private SQL inspection")]')
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', label); label.click()
        click('Inspect private native sample')
        wait.until(lambda b: b.find_element(By.CSS_SELECTOR, '[aria-label="Private native SQL sample"]'))
        click('Capture native estimated plan')
        wait.until(lambda b: b.find_element(By.CSS_SELECTOR, '[aria-label="Native MySQL operator graph"]'))
        driver.save_screenshot(str(output/'native-workload.png'))
        click('Clear private SQL')
        assert not driver.find_elements(By.CSS_SELECTOR, '[aria-label="Private native SQL sample"]')
        label = driver.find_element(By.XPATH, '//label[contains(. ,"Allow private SQL inspection")]')
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', label); label.click()
        for text, key in [('Start UTC (ISO 8601)', 'start_utc'), ('End UTC (ISO 8601)', 'end_utc')]:
            field = driver.find_element(By.XPATH, '//label[contains(text(),"'+text+'")]/following-sibling::div/input')
            field.send_keys(window[key])
        click('Analyze native slow-log table')
        wait.until(lambda b: len(b.find_elements(By.CSS_SELECTOR, '[aria-label="Slow-log digest analysis"] tbody tr')) > 0)
        errors = [r for r in driver.get_log('browser') if r['level'] == 'SEVERE']; assert not errors, errors
        return {'complete': True, 'checks': ['native-ranking-and-DDN', 'digest-waits', 'private-consent-sample-plan', 'clear-private-SQL', 'scoped-native-slow-log-analysis'], 'console_errors': errors}
    except Exception:
        if driver:
            driver.save_screenshot(str(output/'browser-failure.png'))
            (output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME, 'body').text)
        raise
    finally:
        if driver: driver.quit()
        http.shutdown(); thread.join(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--browser-binary')
    parser.add_argument('--driver-binary')
    args = parser.parse_args()
    qualify(args.output, args.browser_binary, args.driver_binary)
