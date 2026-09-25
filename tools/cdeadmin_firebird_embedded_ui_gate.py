#!/usr/bin/env python3
"""Register and browse an owned embedded DB using copied application state.

Windows/macOS agents must repeat this UI gate with their platform's native
runtime, file picker/path conventions and accessibility stack. Linux keyboard
and high-contrast results do not substitute for those platform runs.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.cdeadmin_firebird_embedded_gate import (  # noqa: E402
    LocalPermissions, _create_client,
)
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
from selenium.common.exceptions import TimeoutException  # noqa: E402


def run(options):
    evidence = options.evidence_root.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    result = {'status': 'failed', 'original_configuration_changed': False}
    driver = process = None
    with tempfile.TemporaryDirectory(
            prefix='owned-embedded-ui-', dir=evidence) as temp:
        directory = Path(temp)
        configuration = directory / 'cdeadmin.db'
        _snapshot_config(options.source_config_db, configuration)
        with sqlite3.connect(configuration) as connection:
            connection.execute('''DELETE FROM server WHERE id IN (
                SELECT legacy_server_id FROM cde_endpoint
                WHERE experience_family = 'firebird')''')
        database = directory / 'owned_ui.fdb'
        route = {'attachment_mode': 'embedded', 'user': 'SYSDBA',
                 'database': str(database), 'filesystem_root': str(directory)}

        def seed(create):
            client = _create_client(LocalPermissions(),
                                    attachment_mode='embedded')
            try:
                handle = (client.config.database_creator(
                    **client.config.database_create_arguments(
                        route, str(database), {})) if create else
                    client._connect({'route': route}))
                with handle:
                    handle.execute_immediate(
                        'CREATE TABLE OWNED_UI (ID INTEGER)')
                    handle.commit()
            finally:
                client.close()

        if not options.create_and_drop:
            seed(create=True)
        port = _free_port()
        config = directory / 'config.py'
        _write_config(config, directory, options.desktop_user, port)
        environment = dict(os.environ, CONFIG_DISTRO_FILE_PATH=str(config),
                           SQLITE_PATH=str(configuration))
        if options.missing_client_library:
            environment['CDEADMIN_FIREBIRD_CLIENT_LIBRARY'] = str(
                directory / 'missing-client-library.so')
        if options.missing_engine:
            environment['FIREBIRD'] = str(directory / 'missing-runtime')
        with (evidence / 'server.log').open('w') as log:
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
                engine = wait_for_tree_item(wait, 'Firebird', ('Connectors',))
                engine.click()
                label = (('Create new' if options.create_and_drop else
                          'Open existing') +
                         ' Embedded (application host) database file...')
                invoke_context_action(wait, driver, engine,
                                      ['Registration', label],
                                      endpoint_prompt_timeout=1)

                def field(name, value):
                    control = wait.until(lambda browser:
                                         visible_named_control(browser, name))
                    control.send_keys(Keys.CONTROL, 'a')
                    control.send_keys(value)

                def tab(name):
                    return wait.until(lambda browser: next((
                        item for item in browser.find_elements(
                            'css selector', '[role=tab]')
                        if item.is_displayed() and item.text == name), None))

                field('Name', 'Owned embedded Firebird QA')
                tab('Connection').click()
                field('Absolute local Firebird database filename',
                      str(database))
                assert visible_named_control(driver, 'Password') is None
                assert visible_named_control(
                    driver, 'Host name/address') is None
                screenshot(driver, evidence / 'connection.png')
                tab('Embedded access').click()
                wait.until(lambda browser: 'Embedded: Engine13 only' in
                           browser.find_element('tag name', 'body').text)
                identity = wait.until(lambda browser: visible_named_control(
                    browser, 'SQL authorization identity'))
                assert identity.get_attribute('value') == 'SYSDBA'
                result['provider_defaults_visible'] = True
                field('Approved local database directory', str(directory))
                field('SQL authorization identity', 'SYSDBA')
                result['accessible_field_names'] = {}
                for label in ('Approved local database directory',
                              'SQL authorization identity'):
                    control = visible_named_control(driver, label)
                    assert control.accessible_name == label
                    result['accessible_field_names'][label] = (
                        control.accessible_name)
                screenshot(driver, evidence / 'local-access.png')

                def publication_counts():
                    with sqlite3.connect(configuration) as connection:
                        return {table: connection.execute(
                            f'SELECT count(*) FROM {table}').fetchone()[0]
                            for table in (
                                'server', 'cde_endpoint', 'cde_endpoint_route',
                                'cde_endpoint_runtime_identity',
                                'cde_endpoint_database_target')}

                initial_publication = publication_counts()
                wait.until(lambda browser: visible_named_control(
                    browser, 'Save')).send_keys(Keys.ENTER)
                result['registration_keyboard_submit'] = True

                if options.missing_client_library or options.missing_engine:
                    expected = (
                        'Configured Firebird client library was not found'
                        if options.missing_client_library else
                        'Engine13 plugin and its dependencies')
                    wait.until(lambda browser:
                               expected in browser.find_element(
                                   'tag name', 'body').text)
                    screenshot(driver, evidence / 'missing-runtime.png')
                    assert publication_counts() == initial_publication
                    result['failed_verification_published_nothing'] = True
                    with sqlite3.connect(configuration) as connection:
                        assert connection.execute('''SELECT count(*)
                            FROM server s JOIN cde_endpoint e
                            ON e.legacy_server_id = s.id
                            WHERE e.profile_id = 'firebird-embedded'
                            ''').fetchone()[0] == 0
                    assert database.is_file()
                    result.update(missing_runtime_refused=True,
                                  missing_component=(
                                      'client-library' if
                                      options.missing_client_library else
                                      'engine-runtime'),
                                  no_registration_published=True,
                                  existing_database_preserved=True)
                    if not options.recover_runtime:
                        result['status'] = 'passed'
                        return 0
                    # Restore only a dependency path in this owned fixture.
                    # Retry is an explicit user Save, never an automatic
                    # replay of a database mutation. This mode opens an
                    # existing file; creation/drop are mutually exclusive.
                    if options.missing_client_library:
                        Path(environment[
                            'CDEADMIN_FIREBIRD_CLIENT_LIBRARY']).symlink_to(
                                Path(os.environ[
                                    'CDEADMIN_FIREBIRD_CLIENT_LIBRARY']
                                     ).resolve(strict=True))
                    else:
                        Path(environment['FIREBIRD']).symlink_to(
                            Path(os.environ['FIREBIRD']).resolve(strict=True),
                            target_is_directory=True)
                    tab('General').click()
                    field('Name', 'Recovered embedded Firebird QA')
                    save = wait.until(lambda browser: visible_named_control(
                        browser, 'Save'))
                    wait.until(lambda _browser: save.is_enabled())
                    save.click()

                def verified(_browser):
                    with sqlite3.connect(configuration) as connection:
                        row = connection.execute('''SELECT e.id,
                            i.verification_state, s.password, s.save_password
                            FROM cde_endpoint e JOIN server s
                            ON s.id = e.legacy_server_id
                            JOIN cde_endpoint_runtime_identity i
                            ON i.endpoint_id = e.id
                            WHERE e.profile_id = 'firebird-embedded'
                            ''').fetchone()
                        if row is None or row[1] != 'verified':
                            return False
                        assert row[2] is None and not row[3]
                        assert connection.execute('''SELECT count(*) FROM
                            cde_endpoint_secret_reference
                            WHERE endpoint_id = ?''', (row[0],)
                                                  ).fetchone()[0] == 0
                        return True

                wait.until(verified)
                publication = publication_counts()
                for table in ('server', 'cde_endpoint', 'cde_endpoint_route',
                              'cde_endpoint_runtime_identity'):
                    assert publication[table] == initial_publication[table] + 1
                result['publication_counts_before'] = initial_publication
                result['publication_counts_after'] = publication
                result['single_verified_registration_published'] = True
                if options.recover_runtime:
                    result['runtime_recovery_without_restart'] = True
                if options.create_and_drop:
                    assert database.is_file()
                    seed(create=False)
                    result['database_created_by_ui'] = True
                screenshot(driver, evidence / 'registered.png')
                driver.get(f'http://127.0.0.1:{port}/browser/')
                apply_presentation(driver, wait, options)
                ensure_data_explorer(wait)
                expand(wait, 'Connectors')
                expand(wait, 'Firebird', ('Connectors',))
                # Layout/preference restoration can replace this virtual row
                # after the first click. Re-read its expansion state and retry
                # only this read-only navigation, never a database operation.
                for attempt in range(3):
                    expand(wait, 'localhost', ('Connectors', 'Firebird'))
                    endpoint = wait_for_tree_item(
                        wait, 'localhost', ('Connectors', 'Firebird'))
                    # Enlarged text can put the parent at the bottom of the
                    # virtual viewport. Bring its children into the viewport
                    # before asking Selenium for their mounted DOM rows.
                    driver.execute_script(
                        'arguments[0].scrollIntoView({block:"center"})',
                        endpoint)
                    try:
                        wait_for_tree_item(WebDriverWait(driver, 5),
                                           database.name, (
                                               'Connectors', 'Firebird',
                                               'localhost'))
                        break
                    except TimeoutException:
                        if attempt == 2:
                            raise
                expand(wait, database.name,
                       ('Connectors', 'Firebird', 'localhost'))
                ancestry = ('Connectors', 'Firebird', 'localhost',
                            database.name)
                for attempt in range(3):
                    tables = wait_for_tree_item(wait, 'Tables', ancestry)
                    driver.execute_script(
                        'arguments[0].scrollIntoView({block:"center"})',
                        tables)
                    expand(wait, 'Tables', ancestry)
                    try:
                        wait_for_tree_item(WebDriverWait(driver, 5),
                                           'OWNED_UI', (*ancestry, 'Tables'))
                        break
                    except TimeoutException:
                        if attempt == 2:
                            raise
                screenshot(driver, evidence / 'catalog.png')

                if options.create_and_drop:
                    item = wait_for_tree_item(wait, database.name, (
                        'Connectors', 'Firebird', 'localhost'))
                    driver.execute_script(
                        'arguments[0].scrollIntoView({block:"center"})', item)
                    invoke_context_action(wait, driver, item, [
                        'Definition and lifecycle', 'Drop database...'],
                        endpoint_prompt_timeout=1)
                    field('Type the exact Firebird database filename or '
                          'alias to confirm', str(database))
                    preview = wait.until(lambda browser: visible_named_control(
                        browser, 'Validate and preview'))
                    driver.execute_script(
                        'arguments[0].scrollIntoView({block:"center"})',
                        preview)
                    preview.click()
                    confirmation = wait.until(
                        lambda browser: visible_named_control(
                            browser,
                            'I confirm this provider-planned database '
                            'operation.'))
                    driver.execute_script(
                        'arguments[0].scrollIntoView({block:"center"})',
                        confirmation)
                    confirmation.click()
                    screenshot(driver, evidence / 'drop-preview.png')
                    drop = wait.until(lambda browser: visible_named_control(
                        browser, 'Drop Firebird database'))
                    drop.click()
                    wait.until(lambda _browser: not database.exists())
                    result['database_dropped_by_ui'] = True
                    driver.get(f'http://127.0.0.1:{port}/browser/')
                    apply_presentation(driver, wait, options)
                    ensure_data_explorer(wait)
                    expand(wait, 'Connectors')
                    expand(wait, 'Firebird', ('Connectors',))

                item = wait_for_tree_item(wait, 'localhost',
                                          ('Connectors', 'Firebird'))
                driver.execute_script(
                    'arguments[0].scrollIntoView({block:"center"})', item)
                invoke_context_action(wait, driver, item, [
                    'Endpoint registration', 'Edit endpoint properties...'],
                    endpoint_prompt_timeout=1)
                field('Connection profile name', 'Edited embedded Firebird QA')
                result['edit_screenshots'] = screenshot_form_pages(
                    driver, evidence / 'edit', selector=(
                        '[data-form-id="'
                        'cdeadmin.firebird-embedded.server.edit.v1"]'))
                save = wait.until(lambda browser: visible_named_control(
                    browser, 'Save endpoint profile'))
                driver.execute_script(
                    'arguments[0].scrollIntoView({block:"center"})', save)
                save.click()

                def edited(_browser):
                    with sqlite3.connect(configuration) as connection:
                        return connection.execute('''SELECT s.name
                            FROM server s JOIN cde_endpoint e
                            ON e.legacy_server_id = s.id
                            WHERE e.profile_id = 'firebird-embedded'
                            ''').fetchone() == ('Edited embedded Firebird QA',)

                wait.until(edited)
                driver.get(f'http://127.0.0.1:{port}/browser/')
                apply_presentation(driver, wait, options)
                ensure_data_explorer(wait)
                expand(wait, 'Connectors')
                expand(wait, 'Firebird', ('Connectors',))
                item = wait_for_tree_item(wait, 'localhost',
                                          ('Connectors', 'Firebird'))
                driver.execute_script(
                    'arguments[0].scrollIntoView({block:"center"})', item)
                invoke_context_action(wait, driver, item, [
                    'Endpoint registration',
                    'Remove endpoint registration...'],
                    endpoint_prompt_timeout=1)
                field('Type the connection profile name to confirm',
                      'Edited embedded Firebird QA')
                result['remove_screenshots'] = screenshot_form_pages(
                    driver, evidence / 'remove', selector=(
                        '[data-form-id="'
                        'cdeadmin.firebird-embedded.server.remove.v1"]'))
                remove = wait.until(lambda browser: visible_named_control(
                    browser, 'Remove endpoint registration'))
                driver.execute_script(
                    'arguments[0].scrollIntoView({block:"center"})', remove)
                remove.click()

                def removed(_browser):
                    with sqlite3.connect(configuration) as connection:
                        return connection.execute('''SELECT count(*)
                            FROM server s JOIN cde_endpoint e
                            ON e.legacy_server_id = s.id
                            WHERE e.profile_id = 'firebird-embedded'
                            ''').fetchone()[0] == 0

                wait.until(removed)
                assert database.is_file() == (not options.create_and_drop)
                result.update(status='passed', registration_verified=True,
                              saved_secrets=0, native_table_browsed=True,
                              profile_edited=True, profile_removed=True,
                              unregister_preserved_database=(
                                  not options.create_and_drop))
            except Exception as error:
                result['failure'] = type(error).__name__ + ': ' + str(error)
                traceback.print_exc()
                if driver:
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
                    json.dumps(result, indent=2) + '\n')
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-config-db', type=Path, required=True)
    parser.add_argument('--desktop-user', required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--browser-binary')
    scenarios = parser.add_mutually_exclusive_group()
    scenarios.add_argument('--create-and-drop', action='store_true')
    scenarios.add_argument('--missing-client-library', action='store_true')
    scenarios.add_argument('--missing-engine', action='store_true')
    parser.add_argument('--recover-runtime', action='store_true')
    parser.add_argument('--theme', default='default',
                        choices=['default', 'high-contrast'])
    parser.add_argument('--font-scale', type=int, default=100)
    options = parser.parse_args()
    if options.recover_runtime and not (
            options.missing_client_library or options.missing_engine):
        parser.error('--recover-runtime requires a missing-runtime scenario')
    sys.exit(run(options))
