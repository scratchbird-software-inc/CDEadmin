#!/usr/bin/env python3
"""Exercise each Linux password plugin through the real credential prompt.

Windows/macOS teams: repeat with native clients, OS credential storage,
keyboard/accessibility stack and platform-specific authentication plugins.
Only an owned Docker engine and a disposable copy of application state change.
"""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from types import SimpleNamespace

from tools.cdeadmin_firebird_password_gate import PLUGINS, run as native_run
from tools.cdeadmin_firebird_ui_completed_orchestrator import (
    _free_port, _snapshot_config, _wait_for_server, _write_config,
)
from tools.cdeadmin_firebird_ui_form_gate import (
    create_driver, screenshot, apply_presentation,
)
from tools.cdeadmin_ui_evidence import (
    ensure_data_explorer, expand, invoke_context_action,
    visible_named_control, wait_for_tree_item,
)
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[1]


def browser_case(options, route, plugin, users, evidence, profile_check=None):
    evidence.mkdir()
    driver = process = None
    result = {}
    with tempfile.TemporaryDirectory(prefix='owned-password-',
                                     dir=evidence) as temp:
        directory = Path(temp)
        database = directory / 'configuration.db'
        _snapshot_config(options.source_config_db, database)
        with sqlite3.connect(database) as connection:
            rows = connection.execute('''SELECT s.id, s.servergroup_id, e.id,
                r.id FROM server s JOIN user u ON u.id=s.user_id
                JOIN cde_endpoint e ON e.legacy_server_id=s.id
                JOIN cde_endpoint_route r ON r.endpoint_id=e.id
                WHERE u.email=? AND e.profile_id='firebird-native'
                AND r.priority=0''', (options.desktop_user,)).fetchall()
            assert len(rows) == 1
            server, group, endpoint, route_id = rows[0]
            selected = {**route, 'user': users[0][0],
                        'auth_plugin_list': plugin, 'wire_crypt':
                        'Enabled' if plugin == 'Legacy_Auth' else 'Required'}
            connection.execute('UPDATE cde_endpoint_route SET configuration=? '
                               'WHERE id=?', (json.dumps(selected), route_id))
            connection.execute('''UPDATE server SET username=?, password=NULL,
                save_password=0, host='127.0.0.1', port=? WHERE id=?''',
                               (users[0][0], route['port'], server))
            connection.execute('DELETE FROM cde_endpoint_database_target '
                               'WHERE endpoint_id=?', (endpoint,))
            connection.execute('UPDATE cde_endpoint_runtime_identity SET '
                               "verification_state='unverified' "
                               'WHERE endpoint_id=?', (endpoint,))
        port = _free_port()
        config = directory / 'config.py'
        _write_config(config, directory, options.desktop_user, port)
        with (evidence / 'server.log').open('w') as log:
            try:
                process = subprocess.Popen(
                    [sys.executable, str(ROOT / 'web/CDEadmin.py')], cwd=ROOT,
                    env=dict(os.environ, CONFIG_DISTRO_FILE_PATH=str(config),
                             SQLITE_PATH=str(database)), stdout=log,
                    stderr=subprocess.STDOUT)
                _wait_for_server(process, port)
                driver = create_driver(SimpleNamespace(
                    browser_binary=None, width=1600, height=1000))
                wait = WebDriverWait(driver, 45)
                base = '/browser/server/'

                def request(action, method, payload=None):
                    return driver.execute_async_script('''
                        const done = arguments[arguments.length-1];
                        const app = window.pgAdmin;
                        const headers = {'Content-Type': 'application/json'};
                        headers[app.csrf_token_header] = app.csrf_token;
                        fetch(arguments[0], {method: arguments[1], headers,
                          credentials: 'same-origin',
                          ...(arguments[1] === 'DELETE' ? {} :
                            {body: JSON.stringify(arguments[2] || {})})})
                          .then(async r => done({status:r.status,
                            body:await r.json()}))
                          .catch(() => done({status:0}));
                    ''', base + f'{action}/{group}/{server}', method, payload)

                def load_tree():
                    driver.get(f'http://127.0.0.1:{port}/browser/')
                    apply_presentation(driver, wait, options)
                    ensure_data_explorer(wait)
                    expand(wait, 'Connectors')
                    expand(wait, 'Firebird', ('Connectors',))
                    return wait_for_tree_item(
                        wait, 'localhost', ('Connectors', 'Firebird'))

                def prompt(password, alternate=False, save=False):
                    item = load_tree()
                    driver.execute_script('''
                        window.__authResult = null;
                        const original = XMLHttpRequest.prototype.open;
                        XMLHttpRequest.prototype.open = function(m,url,...r) {
                          if (String(url).includes('/verify_endpoint/')) {
                            this.addEventListener('load', () => {
                              window.__authResult = {status:this.status,
                                body:JSON.parse(this.responseText)};
                            });
                          }
                          return original.call(this, m, url, ...r);
                        };
                    ''')
                    invoke_context_action(wait, driver, item,
                                          ['Connection',
                                           'Verify Firebird 5.0 endpoint...'],
                                          handle_endpoint_prompt=False)
                    if alternate:
                        label = 'Connect as a different user'
                        checkbox = wait.until(lambda browser:
                                              visible_named_control(
                                                  browser, label))
                        checkbox.click()
                        field = wait.until(lambda browser:
                                           visible_named_control(
                                               browser,
                                               'Alternate user or principal'))
                        field.send_keys(users[1][0])
                        saved = visible_named_control(driver, 'Save Password')
                        assert not saved.is_enabled()
                    field = wait.until(lambda browser: visible_named_control(
                        browser, 'Password'))
                    assert field.accessible_name == 'Password'
                    field.send_keys(password)
                    visible_named_control(driver, 'Show password').click()
                    assert field.get_attribute('type') == 'text'
                    visible_named_control(driver, 'Hide password').click()
                    assert field.get_attribute('type') == 'password'
                    if save:
                        visible_named_control(driver, 'Save Password').click()
                    filename = ('alternate-prompt.png' if alternate
                                else 'default-prompt.png')
                    screenshot(driver, evidence / filename)
                    visible_named_control(driver, 'OK').click()
                    return wait.until(lambda browser: browser.execute_script(
                        'return window.__authResult'))

                profile_observation = None
                if profile_check:
                    profile_observation = profile_check(SimpleNamespace(
                        driver=driver, wait=wait, load_tree=load_tree,
                        prompt=prompt, request=request, database=database,
                        route_id=route_id, route=selected, users=users,
                        evidence=evidence))
                # FM-FB02-005: failed authentication must never persist the
                # supplied password, even when the user requests storage.
                load_tree()
                rejected_password = 'Rejected-' + users[0][1]
                rejected = request('verify_endpoint', 'POST', {
                    'password': rejected_password, 'save_password': True})
                assert rejected['status'] == 401
                assert rejected_password not in json.dumps(rejected)
                with sqlite3.connect(database) as connection:
                    assert connection.execute(
                        'SELECT password, save_password FROM server '
                        'WHERE id=?', (server,)).fetchone() == (None, 0)
                # String form values are accepted deliberately; an arbitrary
                # truthy value must not accidentally opt into persistence.
                assert request('verify_endpoint', 'POST', {
                    'password': users[0][1],
                    'save_password': 'yes'})['status'] == 400
                response = prompt(users[0][1], save=True)
                assert response['status'] == 200
                assert response['body']['data']['connected_as'] == users[0][0]
                with sqlite3.connect(database) as connection:
                    stored = connection.execute(
                        'SELECT username, password, save_password FROM server '
                        'WHERE id=?', (server,)).fetchone()
                assert stored[0] == users[0][0] and stored[2] == 1
                assert stored[1] and users[0][1] not in str(stored[1])
                item = load_tree()
                invoke_context_action(
                    wait, driver, item,
                    ['Connection', 'Disconnect Firebird 5.0 endpoint...'],
                    endpoint_prompt_timeout=1)
                confirm = wait.until(lambda browser: visible_named_control(
                    browser, 'Disconnect'))
                screenshot(driver, evidence / 'disconnect-confirmation.png')
                confirm.click()

                def disconnected(_browser):
                    with sqlite3.connect(database) as connection:
                        return connection.execute(
                            'SELECT verification_state FROM '
                            'cde_endpoint_runtime_identity '
                            'WHERE endpoint_id=?',
                            (endpoint,)).fetchone() == ('unverified',)

                wait.until(disconnected)
                assert request('verify_endpoint', 'POST')['status'] == 200
                assert request('connect', 'DELETE')['status'] == 200
                response = prompt(users[1][1], alternate=True)
                assert response['status'] == 200
                assert response['body']['data']['connected_as'] == users[1][0]
                assert not response['body']['data']['uses_default_user']
                with sqlite3.connect(database) as connection:
                    assert connection.execute(
                        'SELECT username, password, save_password FROM server '
                        'WHERE id=?', (server,)).fetchone() == stored
                assert request('verify_endpoint', 'POST', {
                    'connect_as': users[1][0], 'save_password': True,
                    'password': users[1][1]})['status'] == 400
                assert request('verify_endpoint', 'POST')['status'] == 401
                assert request('connect', 'DELETE')['status'] == 200
                default = request('verify_endpoint', 'POST')
                assert default['status'] == 200
                assert default['body']['data']['connected_as'] == users[0][0]
                assert request('connect', 'DELETE')['status'] == 200
                assert request('clear_saved_password', 'PUT')['status'] == 200
                assert request('verify_endpoint', 'POST')['status'] == 401
                response = prompt(users[0][1])
                assert response['status'] == 200
                with sqlite3.connect(database) as connection:
                    credentials = connection.execute(
                        'SELECT password, save_password '
                        'FROM server WHERE id=?', (server,)).fetchone()
                    assert credentials == (None, 0)
                assert request('connect', 'DELETE')['status'] == 200
                assert request('verify_endpoint', 'POST')['status'] == 401
                result = {'passed': True, 'saved_default_encrypted': True,
                          'saved_reconnect': True,
                          'alternate_session_only': True,
                          'explicit_principal_required': True,
                          'default_restored_after_disconnect': True,
                          'prompt_only_erased_on_disconnect': True,
                          'show_hide_password': True,
                          'accessible_password_name': True}
                result['navigator_disconnect_confirmation'] = True
                result['failed_authentication_never_saved'] = True
                result['invalid_save_flag_rejected'] = True
                log.flush()
                log_text = (evidence / 'server.log').read_text()
                for application_log in directory.glob('*.log*'):
                    log_text += application_log.read_text(errors='replace')
                for secret in (users[0][1], users[1][1], rejected_password):
                    assert secret not in log_text
                result['passwords_absent_from_server_log'] = True
                if profile_observation is not None:
                    result['plugin_profile'] = profile_observation
            except Exception as error:
                result = {'passed': False, 'error_type': type(error).__name__,
                          'locations': [
                              {'file': Path(frame.filename).name,
                               'line': frame.lineno}
                              for frame in traceback.extract_tb(
                                  error.__traceback__)]}
                if driver:
                    screenshot(driver, evidence / 'failure.png')
                raise
            finally:
                if driver:
                    driver.quit()
                if process:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=15)
                # Preserve application-file logs as well as stdout. Strip
                # known disposable canaries before publishing any evidence,
                # but fail qualification if either original log contained one.
                canaries = [users[0][1], users[1][1],
                            'Rejected-' + users[0][1]]
                leaked = False
                for application_log in [evidence / 'server.log',
                                        *directory.glob('*.log*')]:
                    original = application_log.read_text(errors='replace')
                    safe = original
                    for secret in canaries:
                        leaked = leaked or secret in original
                        safe = safe.replace(secret, '[REDACTED]')
                    (evidence / application_log.name).write_text(safe)
                if leaked:
                    result['passed'] = False
                    result['log_secret_leak'] = True
                (evidence / 'browser.json').write_text(
                    json.dumps(result, indent=2) + '\n')
                if leaked:
                    raise AssertionError('credential appeared in a log')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-config-db', type=Path, required=True)
    parser.add_argument('--desktop-user', required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--theme', default='high-contrast')
    parser.add_argument('--font-scale', type=int, default=150)
    parser.add_argument('--plugin', action='append', choices=PLUGINS)
    options = parser.parse_args()
    result = native_run(options.evidence_root, lambda *args:
                        browser_case(options, *args), options.plugin)
    raise SystemExit(0 if result['complete'] else 1)
