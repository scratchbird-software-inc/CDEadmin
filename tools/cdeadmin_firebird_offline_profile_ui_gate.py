#!/usr/bin/env python3
"""Exercise offline Firebird profile editing in an isolated configuration.

No database engine is started or changed. Only a temporary copy of the supplied
configuration is mutated. Evidence belongs outside the source tree.
"""

import argparse
import json
import os
from pathlib import Path
import socket
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.cdeadmin_firebird_ui_completed_orchestrator import (  # noqa: E402
    _free_port, _snapshot_config, _wait_for_server, _write_config,
)
from tools.cdeadmin_firebird_ui_form_gate import (  # noqa: E402
    apply_presentation, create_driver, screenshot, screenshot_form_pages,
)
from tools.cdeadmin_ui_evidence import (  # noqa: E402
    ensure_data_explorer, expand, invoke_context_action,
    visible_named_control, wait_for_tree_item,
)
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402


def prepare_copy(database, user, port):
    with sqlite3.connect(database) as connection:
        rows = connection.execute('''
            SELECT s.id, e.id, r.id, r.configuration
            FROM server s JOIN user u ON u.id = s.user_id
            JOIN cde_endpoint e ON e.legacy_server_id = s.id
            JOIN cde_endpoint_route r ON r.endpoint_id = e.id
            WHERE u.email = ? AND e.profile_id = 'firebird-native'
            AND r.priority = 0
        ''', (user,)).fetchall()
        if len(rows) != 1:
            raise RuntimeError('Expected one owned Firebird primary route')
        server, endpoint, route_id, raw = rows[0]
        route = json.loads(raw)
        route.pop('database', None)
        route.update(host='127.0.0.1', port=port)
        connection.execute('''UPDATE server SET name = 'Offline Firebird QA',
            host = '127.0.0.1', port = ?, password = NULL, save_password = 0
            WHERE id = ?''', (port, server))
        connection.execute('''DELETE FROM cde_endpoint_database_target
            WHERE endpoint_id = ?''', (endpoint,))
        connection.execute('''UPDATE cde_endpoint_route SET configuration = ?
            WHERE id = ?''', (json.dumps(route), route_id))
        connection.execute('''UPDATE cde_endpoint_runtime_identity
            SET verification_state = 'unverified',
                verified_runtime_family = NULL, verified_runtime_version = NULL
            WHERE endpoint_id = ?''', (endpoint,))
    return server, endpoint


def run(options):
    evidence = options.evidence_root.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    result = {'status': 'failed', 'native_engine_mutations': False}
    driver = process = None
    with tempfile.TemporaryDirectory(prefix='cdeadmin-offline-') as temp:
        directory = Path(temp)
        database = directory / 'cdeadmin.db'
        _snapshot_config(options.source_config_db, database)
        # Bound but not listening: unavailable without touching a running demo.
        log_path = evidence / 'server.log'
        with socket.socket() as unavailable, log_path.open(
                'w', encoding='utf-8') as log:
            unavailable.bind(('127.0.0.1', 0))
            server, endpoint = prepare_copy(
                database, options.desktop_user, unavailable.getsockname()[1])
            port = _free_port()
            config = directory / 'config.py'
            _write_config(config, directory, options.desktop_user, port)
            environment = os.environ.copy()
            environment['CONFIG_DISTRO_FILE_PATH'] = str(config)
            environment['SQLITE_PATH'] = str(database)
            try:
                process = subprocess.Popen(
                    [sys.executable, str(ROOT / 'web/CDEadmin.py')],
                    cwd=ROOT, env=environment, stdout=log,
                    stderr=subprocess.STDOUT)
                _wait_for_server(process, port)
                driver = create_driver(SimpleNamespace(
                    browser_binary=options.browser_binary,
                    width=1600, height=1000))
                wait = WebDriverWait(driver, 60)
                driver.get(f'http://127.0.0.1:{port}/browser/')
                apply_presentation(driver, wait, options)
                ensure_data_explorer(wait)
                expand(wait, 'Connectors')
                expand(wait, 'Firebird', ('Connectors',))
                item = wait_for_tree_item(wait, 'localhost',
                                          ('Connectors', 'Firebird'))
                invoke_context_action(wait, driver, item, [
                    'Endpoint registration', 'Edit endpoint properties...'],
                    endpoint_prompt_timeout=1)
                control = wait.until(lambda browser: visible_named_control(
                    browser, 'Save endpoint profile'))
                selector = ('[data-form-id="'
                            'cdeadmin.firebird-native.server.edit.v1"]')
                result['edit_screenshots'] = screenshot_form_pages(
                    driver, evidence / 'edit', selector=selector)

                def host_control(browser):
                    inputs = browser.find_elements(
                        'css selector', selector + ' input')
                    for item in inputs:
                        if item.get_attribute('value') == '127.0.0.1':
                            return item
                    return None

                # Use the rendered host control and normal Save button.
                host = wait.until(host_control)
                host.send_keys(Keys.CONTROL, 'a')
                host.send_keys('127.0.0.10')
                driver.execute_script(
                    'arguments[0].scrollIntoView({block:"center"})', control)
                control.click()

                def saved(_browser):
                    with sqlite3.connect(database) as connection:
                        return connection.execute(
                            'SELECT host FROM server WHERE id = ?',
                            (server,)).fetchone() == ('127.0.0.10',)

                wait.until(saved)
                label = driver.execute_script('''
                    const tree = window.pgAdmin.Browser.tree;
                    return tree.itemData(tree.selected()).label;
                ''')
                if label != 'localhost':
                    raise AssertionError('Post-save server label changed')
                with sqlite3.connect(database) as connection:
                    count = connection.execute('''SELECT count(*) FROM
                        cde_endpoint_database_target WHERE endpoint_id = ?''',
                                               (endpoint,)).fetchone()[0]
                if count:
                    raise AssertionError('Offline editing created a target')
                screenshot(driver, evidence / 'saved.png')
                driver.get(f'http://127.0.0.1:{port}/browser/')
                apply_presentation(driver, wait, options)
                ensure_data_explorer(wait)
                expand(wait, 'Connectors')
                expand(wait, 'Firebird', ('Connectors',))
                item = wait_for_tree_item(wait, 'localhost',
                                          ('Connectors', 'Firebird'))
                invoke_context_action(wait, driver, item, [
                    'Endpoint registration',
                    'Remove endpoint registration...'],
                    endpoint_prompt_timeout=1)
                confirmation = wait.until(
                    lambda browser: visible_named_control(
                        browser,
                        'Type the connection profile name to confirm'))
                confirmation.send_keys('Offline Firebird QA')
                result['remove_screenshots'] = screenshot_form_pages(
                    driver, evidence / 'remove', selector=(
                        '[data-form-id="'
                        'cdeadmin.firebird-native.server.remove.v1"]'))
                remove = wait.until(lambda browser: visible_named_control(
                    browser, 'Remove endpoint registration'))
                remove.click()

                def removed(_browser):
                    with sqlite3.connect(database) as connection:
                        return connection.execute(
                            'SELECT id FROM server WHERE id = ?',
                            (server,)).fetchone() is None

                wait.until(removed)
                screenshot(driver, evidence / 'removed.png')
                if options.registration_entry == 'localhost':
                    driver.get(f'http://127.0.0.1:{port}/browser/')
                    apply_presentation(driver, wait, options)
                    ensure_data_explorer(wait)
                    expand(wait, 'Connectors')
                    expand(wait, 'Firebird', ('Connectors',))
                engine = wait_for_tree_item(wait, 'Firebird', ('Connectors',))
                if options.registration_entry == 'localhost':
                    driver.execute_script(
                        'arguments[0].scrollIntoView({block:"center"})',
                        engine)
                    engine = wait_for_tree_item(wait, 'localhost',
                                                ('Connectors', 'Firebird'))
                engine.click()
                registration_label = driver.execute_script('''
                    const tree = window.pgAdmin.Browser.tree;
                    const data = tree.itemData(tree.selected());
                    return data.cde_context_actions.find(action =>
                        action.command_id ===
                        'connector.firebird.register_endpoint.firebird-native'
                    ).label;
                ''')
                invoke_context_action(wait, driver, engine, [
                    'Registration', registration_label],
                    endpoint_prompt_timeout=1)

                def verification_switch(browser):
                    switches = [item for item in browser.find_elements(
                        'css selector', '.MuiSwitch-root')
                        if item.is_displayed()]
                    return switches[0] if len(switches) == 1 else None

                verify = wait.until(verification_switch)
                switch_input = verify.find_element('css selector', 'input')
                result['verification_switch_accessible_name'] = (
                    switch_input.accessible_name)
                if switch_input.is_selected():
                    verify.click()
                for name, value in (
                        ('Name', 'New offline Firebird QA'),
                        ('Host name/address', '127.0.0.10'),
                        ('Port', str(unavailable.getsockname()[1])),
                        ('Username', 'SYSDBA')):
                    if name == 'Host name/address':
                        def connection_tab(browser):
                            tabs = browser.find_elements(
                                'css selector', '[role=tab]')
                            return next((tab for tab in tabs if
                                         tab.text == 'Connection' and
                                         tab.is_displayed()), None)
                        wait.until(connection_tab).click()
                    field = wait.until(lambda browser, label=name:
                                       visible_named_control(browser, label))
                    field.send_keys(Keys.CONTROL, 'a')
                    field.send_keys(value)
                screenshot(driver, evidence / 'register.png')
                save = wait.until(lambda browser: visible_named_control(
                    browser, 'Save'))
                save.click()

                def registered(_browser):
                    with sqlite3.connect(database) as connection:
                        row = connection.execute('''SELECT s.host, e.id
                            FROM server s JOIN cde_endpoint e
                            ON e.legacy_server_id = s.id
                            WHERE s.name = 'New offline Firebird QA'
                        ''').fetchone()
                        if not row:
                            return False
                        assert row[0] == '127.0.0.10'
                        assert connection.execute('''SELECT count(*) FROM
                            cde_endpoint_database_target
                            WHERE endpoint_id = ?''', (row[1],)
                                                  ).fetchone()[0] == 0
                        return True

                wait.until(registered)
                screenshot(driver, evidence / 'registered.png')
                result.update(status='passed', edited_host='127.0.0.10',
                              database_target_count=count, removed=True,
                              navigator_label=label, registered_offline=True,
                              registration_entry=options.registration_entry)
            except Exception as error:
                result['failure'] = type(error).__name__ + ': ' + str(error)
                traceback.print_exc()
                if driver:
                    controls = [{
                        'tag': item.tag_name, 'name': item.accessible_name,
                        'id': item.get_attribute('id'),
                        'type': item.get_attribute('type'),
                        'displayed': item.is_displayed(),
                    } for item in driver.find_elements(
                        'css selector',
                        'input, button')]
                    (evidence / 'failed-controls.json').write_text(
                        json.dumps(controls, indent=2) + '\n')
                    screenshot(driver, evidence / 'failure.png')
            finally:
                if driver:
                    driver.quit()
                if process:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                for application_log in directory.glob('*.log'):
                    shutil.copy2(application_log,
                                 evidence / ('app-' + application_log.name))
                (evidence / 'summary.json').write_text(
                    json.dumps(result, indent=2, default=str) + '\n',
                    encoding='utf-8')
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-config-db', type=Path, required=True)
    parser.add_argument('--desktop-user', required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--browser-binary')
    parser.add_argument('--theme', default='default',
                        choices=['default', 'high-contrast'])
    parser.add_argument('--font-scale', type=int, default=100)
    parser.add_argument('--registration-entry', default='connector',
                        choices=['connector', 'localhost'])
    sys.exit(run(parser.parse_args()))
