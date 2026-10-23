"""Independent expected-dump acceptance on real managed physical recovery copies."""
import hashlib
import json
from pathlib import Path
import threading
import time
from unittest.mock import patch


def qualify_acceptance(app, output, root, port, password, options, credentials, binary=None, driver_binary=None):
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_recovery_connection_qualification import endpoint, query_post, execute
    from cdeadmin_mysql_physical_replay_qualification import wait_job, start_request
    from pgadmin.cdeadmin.providers.mysql_family import mysql_instance_acceptance as native
    from pgadmin.cdeadmin.providers.mysql_family import mysql_recovery_bridge as bridge
    from pgadmin.model import User, Server
    base = Path(__file__).resolve().parents[1]
    paths = [str(Path(__file__).relative_to(base))] + [
        'web/pgadmin/cdeadmin/' + value for value in (
            'providers/mysql_family/mysql_instance_acceptance.py', 'providers/mysql_family/mysql_recovery_bridge.py',
            'providers/mysql_family/mysql_recovery_stream.py', 'workspace/mysql_instance_acceptance_jobs.py',
            'workspace/mysql_instance_acceptance_service.py', 'workspace/mysql_recovery_connections.py')]
    paths += ['web/pgadmin/static/js/Dialogs/MySQLInstanceAcceptance.jsx']
    proof = {'complete': False, 'interfaces': [], 'source_sha256': {p: hashlib.sha256((base/p).read_bytes()).hexdigest() for p in paths}}
    cursor = root.cursor(); service = app.extensions['cdeadmin_provider_workspace']
    for use_c in (False, True):
        sid, _, _ = registration(app, {'host': '127.0.0.1', 'port': port}, password, use_c, username='sr_physical')
        with app.test_request_context('/'):
            uid = User.query.first().id
        client = app.test_client()
        with client.session_transaction() as session: session['_user_id'], session['_fresh'] = str(uid), True
        source_url = endpoint(app, sid); checks = []; runtimes = []; targets = []
        def http(url, prefix, action, request, refused=False):
            response = client.post(url, json={'action': prefix + action, 'request': request}); value = response.get_json()
            if refused: assert not value.get('success'), value; return value
            assert response.status_code == 200 and value.get('success'), value
            return value['data']
        physical = lambda action, request, refused=False: http(source_url, 'mysql_physical_', action, request, refused)
        backups = lambda action, request: http(source_url, 'mysql_instance_backup_', action, request)
        def dump():
            return wait_job(backups('start', start_request(backups('review', {'options': {
                'users': False, 'checksum': True, 'threads': 1, 'timeout_seconds': 120}}))), backups, 'completed')
        def phase(kind, source=None, replay=False):
            extra = {'mysqld': '/usr/sbin/mysqld', 'recovery_gtid_mode': 'ON', 'recovery_port': 33447 if replay else 0,
                'recovery_local_infile': True, 'timeout_seconds': 600,
                **({'recovery_mode': 'replay', 'recovery_server_id': 19001 + int(use_c)} if replay else {})} if kind == 'recover' else {}
            ticket = physical('review', {'options': {**options, 'phase': kind, 'input_job_id': source, **extra}, 'credentials': credentials})
            value = physical('start', {**start_request(ticket), 'delegate_database_credentials': True, 'credentials': credentials})
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                value = physical('reconcile', {'job_id': value['job_id'], 'credentials': credentials})
                remote = value.get('remote_observation') or {}
                if kind == 'recover' and value.get('recovery_running'): runtimes.append(value); return value
                if remote.get('supervisor_finished'):
                    assert remote.get('return_code') == 0 and value.get('file_verification_confirmed'), value
                    assert kind != 'recover', value
                    return value
                time.sleep(.1)
            raise TimeoutError('Owned physical acceptance native ' + kind)
        def attach(runtime):
            ticket = physical('connection_review', {'job_id': runtime['job_id'], 'name': 'Physical acceptance ' + str(use_c), 'credentials': credentials})
            target = physical('connection_connect', {'review_id': ticket['job_id'], 'review_digest': ticket['review_digest'],
                'confirmed': True, 'delegate_database_credentials': True, 'credentials': credentials})['result']
            if target['server_id'] not in [item['server_id'] for item in targets]: targets.append(target)
            return target
        def acceptance(target, backup):
            post = lambda action, request, refused=False: http(endpoint(app, target['server_id']), 'mysql_instance_acceptance_', action, request, refused)
            ticket = post('review', {'source_server_id': sid, 'backup_job_id': backup['job_id'], 'options': {
                'target_confirmation': target['binding']['server_uuid'], 'server_wide_write_pause_confirmed': True,
                'threads': 1, 'timeout_seconds': 120}})
            return post, ticket
        def accept(target, backup):
            post, ticket = acceptance(target, backup)
            value = wait_job(post('start', start_request(ticket)), post, 'verification_observed')
            (output / ('acceptance-last-' + str(use_c) + '.json')).write_text(json.dumps(value, indent=2) + '\n')
            assert value['physical_recovery']['job_id'] == target['binding']['job_id'] and value['restore_issued'] is False
            return value
        def sql(target, statement):
            post = lambda action, **body: query_post(client, endpoint(app, target['server_id']), target['database_target_id'], action, **body)
            session = post('open_session', language_profile='mysql-sql')['session_id']
            try: return execute(post, session, statement)['rows']
            finally: post('close_session', session_id=session)
        try:
            cursor.execute('SHOW CREATE PROCEDURE sr_osc.p'); original_procedure = cursor.fetchone()[2]; cursor.fetchall()
            expected = dump()
            backed = phase('backup'); prepared = phase('prepare', backed['job_id']); copied = phase('copy_back', prepared['job_id'])
            readonly = phase('recover', copied['job_id']); target = attach(readonly)
            assert readonly['remote_observation']['sql_identity']['skip_networking'] == 1
            assert readonly['remote_observation']['sql_identity']['local_infile'] == 1
            assert sql(target, 'SELECT CAST(id AS CHAR),note,HEX(b) FROM t') == [['18446744073709551615', 'native 雪', '00FF']]
            matched = accept(target, expected)
            assert matched['acceptance_outcome'] == 'matched', matched
            assert matched['result']['data']['matched'] and matched['result']['definitions']['matched']
            checks.append('private-Unix-socket-read-only-physical-base-native-editor-full-count-checksum-and-definition-match-against-independent-source-dump')
            post, ticket = acceptance(target, expected)
            original = native.run_checks
            def lost(*args, **kwargs):
                result = original(*args, **kwargs)
                assert result['tool']['process_observation']['cleanup_confirmed']
                raise ConnectionError('Owned loss of original native acceptance reply')
            with patch.object(native, 'run_checks', lost):
                unknown = wait_job(post('start', start_request(ticket)), post, 'unknown')
            assert unknown['acceptance_outcome'] == 'unconfirmed' and unknown['native_process_termination_confirmed'] is not True
            deadline = time.monotonic() + 30
            while service.mysql_instance_acceptance_jobs.workers.get(ticket['job_id']):
                if time.monotonic() > deadline: raise TimeoutError('Owned acceptance observer did not end')
                time.sleep(.02)
            physical('connection_detach', {'server_id': target['server_id']}, refused=True)
            original_bridge = bridge.bridges.get(target['binding']); original_bridge.close()
            post('reconcile', {'job_id': ticket['job_id']}, refused=True)
            observed = post('observe_utilities', {'job_id': ticket['job_id']})
            assert observed['state'] == 'unknown' and observed['acceptance_outcome'] == 'unconfirmed'
            assert observed['native_process_termination_confirmed'] and observed['recovery_utility_release']['released_reservations'] == 1
            assert post('start', start_request(ticket))['started_at'] == unknown['started_at']
            target = attach(readonly)
            facts = post('reconcile', {'job_id': ticket['job_id']})
            assert facts['reconciliation']['private_server_lock_cleanup']['released']
            post('acknowledge', {'job_id': ticket['job_id'], 'target_confirmation': target['binding']['server_uuid'], 'observation_digest': facts['observation_digest']})
            checks.append('lost-real-acceptance-reply-and-relay-loss-retain-unknown-no-replay-until-independent-original-utility-end-and-fresh-SQL-lock-observation')
            physical('connection_detach', {'server_id': target['server_id']})
            stop = physical('cancel', {'job_id': readonly['job_id'], 'credentials': credentials})
            deadline = time.monotonic() + 60
            while not stop.get('remote_observation', {}).get('process_termination_confirmed'):
                if time.monotonic() > deadline: raise TimeoutError('Read-only recovery stop')
                time.sleep(.1); stop = physical('reconcile', {'job_id': readonly['job_id'], 'credentials': credentials})
            writable = phase('recover', copied['job_id'], replay=True); target = attach(writable)
            assert accept(target, expected)['acceptance_outcome'] == 'matched'
            sql(target, "UPDATE t SET note='different same-count data' WHERE id=18446744073709551615")
            different = accept(target, expected)
            assert different['acceptance_outcome'] == 'not_matched' and different['result']['data']['matched'] is False
            assert different['result']['row_counts']['matched'] is True
            assert sql(target, 'SELECT note FROM t') == [['different same-count data']]
            sql(target, "UPDATE t SET note='native 雪' WHERE id=18446744073709551615")
            sql(target, 'DROP PROCEDURE p'); sql(target, 'CREATE PROCEDURE p() SELECT id FROM t')
            different = accept(target, expected)
            assert different['acceptance_outcome'] == 'not_matched' and different['result']['definitions']['matched'] is False
            assert different['result']['data']['matched'] is True
            sql(target, 'DROP PROCEDURE p'); sql(target, original_procedure)
            checks.append('actual-same-row-count-native-checksum-and-routine-definition-differences-are-separate-and-never-repaired')
            cursor.execute('FLUSH BINARY LOGS'); cursor.execute('SHOW BINARY LOG STATUS'); filename = cursor.fetchone()[0]; cursor.fetchall()
            cursor.execute("INSERT INTO sr_osc.t VALUES(91,'post replay 雪',X'00FF7F')"); cursor.execute('FLUSH BINARY LOGS')
            desired = dump()
            archive = lambda action, request: http(source_url, 'mysql_raw_binlog_', action, request)
            sealed = wait_job(archive('start', start_request(archive('review', {'options': {'log_names': [filename]}}))), archive, 'completed')
            replay = lambda action, request: http(endpoint(app, target['server_id']), 'mysql_binlog_replay_', action, request)
            ticket = replay('review', {'source_server_id': sid, 'archive_job_id': sealed['job_id'], 'archive_family': 'raw',
                'options': {'target_confirmation': target['binding']['server_uuid'], 'stop_mode': 'all'}})
            wait_job(replay('start', start_request(ticket)), replay, 'native_load_returned')
            matched = accept(target, desired)
            assert matched['acceptance_outcome'] == 'matched', matched
            assert matched['physical_recovery']['expected_boundary'] == desired['result']['artifact']['native_boundary']
            assert accept(target, expected)['acceptance_outcome'] == 'not_matched'
            checks.append('native-raw-replay-then-independent-full-data-and-definition-acceptance-against-selected-post-replay-source-snapshot-with-old-snapshot-difference')
            if use_c and binary:
                proof['browser'] = browser(app, output, target, sid, desired['job_id'], binary, driver_binary)
                checks.append('built-recovery-target-source-checkpoint-selection-reviewed-read-lock-and-independent-surface-receipt')
            proof['interfaces'].append({'use_c': use_c, 'checks': checks, 'complete': True})
        finally:
            for target in targets:
                try: physical('connection_detach', {'server_id': target['server_id']})
                except Exception: pass
            for runtime in runtimes:
                physical('cancel', {'job_id': runtime['job_id'], 'credentials': credentials})
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    value = physical('reconcile', {'job_id': runtime['job_id'], 'credentials': credentials})
                    if value.get('remote_observation', {}).get('process_termination_confirmed'): break
                    time.sleep(.1)
                else: raise TimeoutError('Owned physical acceptance native process did not stop')
            cursor.execute('DELETE FROM sr_osc.t WHERE id=91')
            jobs=getattr(service,'mysql_instance_acceptance_jobs',None)
            if jobs is not None: jobs.close()
    cursor.close(); proof['complete'] = True
    return proof


def browser(app, output, target, source_id, backup_id, binary, driver_binary):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, invoke_context_action
    from pgadmin.model import Server
    with app.test_request_context('/'):
        source_name = Server.query.get(source_id).name
    evidence = output/'physical-acceptance-desktop'; evidence.mkdir(mode=0o700)
    http = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start(); driver = None
    try:
        options = webdriver.ChromeOptions(); options.binary_location = binary
        for flag in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1900,1600'): options.add_argument(flag)
        options.add_argument('--user-data-dir=' + str(evidence/'browser-profile'))
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        driver = webdriver.Chrome(options=options, service=Service(driver_binary))
        driver.get('http://127.0.0.1:' + str(http.server_port) + '/browser/')
        wait = WebDriverWait(driver, 120); ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'MySQL')
        def node(browser):
            return next((item for item in browser.find_elements(By.CSS_SELECTOR, '.file-name') if item.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', item, target['server_id'])), None)
        invoke_context_action(wait, driver, wait.until(node), ('Restore', 'MySQL full-instance restores...'), handle_endpoint_prompt=False)
        def click(label, tag='button'):
            def attempt(browser):
                for item in browser.find_elements(By.TAG_NAME, tag):
                    if item.is_enabled() and item.get_attribute('textContent').strip() == label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});', item)
                        if item.is_displayed(): item.click(); return True
                return False
            wait.until(attempt)
        click('Inspect instance restore target')
        wait.until(lambda b: b.find_elements(By.CSS_SELECTOR, '[aria-label="Native instance restore target"]'))
        click('Load instance backup sources'); click('Use backup source ' + source_name)
        click('Load source instance backups'); click('Use instance backup ' + backup_id)
        label = driver.find_element(By.XPATH, '//label[contains(text(),"Confirm native restore target UUID")]')
        field = driver.find_element(By.ID, label.get_attribute('for'))
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', field); field.send_keys(target['binding']['server_uuid'])
        click('Independent dump acceptance', 'summary')
        consent = driver.find_element(By.XPATH, '//label[contains(.,"Confirm server-wide write pause for independent acceptance")]')
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', consent); consent.click()
        click('Review independent dump acceptance')
        wait.until(lambda b: b.find_elements(By.CSS_SELECTOR, '[aria-label="Independent dump acceptance review"]'))
        click('Confirm and start independent acceptance')
        wait.until(lambda b: any('Recorded outcome: matched.' in item.get_attribute('textContent') for item in b.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        table = driver.find_element(By.CSS_SELECTOR, '[aria-label="Recorded dump acceptance surfaces"]')
        assert table.get_attribute('textContent').count('Matched') == 2
        reference = wait.until(lambda b: next((item for item in b.find_elements(By.CSS_SELECTOR, '[role="alert"]') if
            'Managed physical recovery ' + target['binding']['job_id'] in item.get_attribute('textContent')), None))
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', reference)
        assert reference.is_displayed()
        click('Observe original acceptance utility without SQL connection')
        wait.until(lambda b: any('Interrupted utility cleanup: confirmed.' in item.get_attribute('textContent') for item in b.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        driver.save_screenshot(str(evidence/'native-physical-acceptance.png'))
        errors = [item for item in driver.get_log('browser') if item['level'] == 'SEVERE']; assert not errors, errors
        proof = {'complete': True, 'console_errors': errors, 'checks': ['recovery-target-context-menu', 'selected-source-checkpoint-and-explicit-write-pause',
            'reviewed-native-data-and-definition-match-with-physical-reference', 'independent-original-utility-observation-preserves-comparison']}
        (evidence/'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
        return proof
    except Exception:
        if driver:
            driver.save_screenshot(str(evidence/'failure.png'))
            (evidence/'failure-text.txt').write_text(driver.find_element(By.TAG_NAME, 'body').text)
        raise
    finally:
        if driver: driver.quit()
        http.shutdown(); http.server_close(); thread.join(timeout=10)
