#!/usr/bin/env python3
"""Full application recovery forms against disposable native databases.

The application configuration is a private temporary copy; native passwords
exist only in process memory and credential requests. Generated assets must
be supplied from a fresh external build. No installed service is modified.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import uuid

from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_password_gate import _route_arguments
from tools.cdeadmin_firebird_ui_completed_orchestrator import (
    _snapshot_config, _write_config, _free_port, _wait_for_server,
)
from tools.cdeadmin_firebird_ui_form_gate import screenshot_form_pages
from tools.cdeadmin_ui_evidence import (
    browser_binary, ensure_data_explorer, expand,
    complete_endpoint_prompt,
)
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[1]


def configuration(source, target, routes):
    _snapshot_config(source, target)
    with sqlite3.connect(target) as db:
        db.row_factory = sqlite3.Row
        original = db.execute('''
            SELECT s.id, s.servergroup_id, e.id AS endpoint,
            u.email FROM server s JOIN user u ON u.id=s.user_id
            JOIN cde_endpoint e ON e.legacy_server_id=s.id
            WHERE e.profile_id='firebird-native' ORDER BY s.id LIMIT 1'''
                              ).fetchone()
        if original is None:
            raise ValueError('A source Firebird registration is required')
        server = dict(db.execute('SELECT * FROM server WHERE id=?',
                                 (original['id'],)).fetchone())
        endpoint = dict(db.execute('SELECT * FROM cde_endpoint WHERE id=?',
                                   (original['endpoint'],)).fetchone())
        registrations = []

        def insert(table, values):
            keys = list(values)
            db.execute(f'INSERT INTO {table} ({",".join(keys)}) VALUES '
                       f'({",".join("?" for _ in keys)})',
                       [values[key] for key in keys])

        next_id = db.execute('SELECT MAX(id) FROM server').fetchone()[0] + 1
        for index, route in enumerate(routes):
            embedded = route.get('attachment_mode') == 'embedded'
            identifier = next_id + index
            name = f'Owned recovery {index + 1}'
            values = {**server, 'id': identifier, 'name': name,
                      'host': route.get('host', 'localhost'),
                      'port': route.get('port', 3050),
                      'username': route['user'], 'password': None,
                      'save_password': 0, 'shared': False,
                      'connection_params': '{}', 'use_ssh_tunnel': 0,
                      'passexec_cmd': None, 'post_connection_sql': None}
            insert('server', values)
            endpoint_id, target_id = str(uuid.uuid4()), str(uuid.uuid4())
            values = {**endpoint, 'id': endpoint_id,
                      'legacy_server_id': identifier}
            if embedded:
                values.update(provider_id='org.cdeadmin.firebird.embedded',
                              profile_id='firebird-embedded',
                              target_adapter_id='firebird-embedded-client')
            for key in ('pool_namespace', 'session_namespace',
                        'cache_namespace', 'diagnostic_namespace'):
                values[key] = str(uuid.uuid4())
            insert('cde_endpoint', values)
            if not embedded:
                insert('cde_endpoint_secret_reference', {
                    'id': str(uuid.uuid4()), 'endpoint_id': endpoint_id,
                    'secret_kind': 'database_password',
                    'storage_kind': 'legacy_protected_column',
                    'secret_reference': (
                        f'server:{identifier}:password:database_password')})
            insert('cde_endpoint_route', {
                'id': str(uuid.uuid4()), 'endpoint_id': endpoint_id,
                'route_kind': 'embedded_file' if embedded else 'tcp',
                'route_reference': name, 'priority': 0,
                'configuration': json.dumps(route)})
            insert('cde_endpoint_runtime_identity', {
                'endpoint_id': endpoint_id, 'declared_runtime_family':
                'firebird', 'declared_runtime_version': '5.0.4',
                'verification_state': 'unverified'})
            insert('cde_endpoint_database_target', {
                'id': target_id, 'endpoint_id': endpoint_id,
                'display_name': name, 'database': route['database'],
                'configuration': '{}', 'active': True,
                'created_at': '2026-10-09 00:00:00',
                'updated_at': '2026-10-09 00:00:00'})
            registrations.append({'id': identifier, 'name': name,
                                  'target': target_id})
        return original['email'], original['servergroup_id'], registrations


def browser_checks(options, native, admin, route, accounts, evidence, root):
    password = secrets.token_urlsafe(24)
    admin.execute_immediate(
        f"CREATE USER OWNED_BROWSER PASSWORD '{password}' USING PLUGIN Srp")
    admin.execute_immediate('GRANT CREATE DATABASE TO USER OWNED_BROWSER')
    admin.commit()
    credentials = [accounts['Srp'][0], ('OWNED_BROWSER', password)]
    routes = [{**route, 'user': user,
               'database': str(root / f'browser-{index}.fdb')}
              for index, (user, _) in enumerate(credentials)]
    for selected, (_, secret) in zip(routes, credentials):
        with native.create_database(password=secret, **_route_arguments(
                selected, native)) as handle:
            handle.execute_immediate(
                'CREATE TABLE RECOVERY_MARKER (ID INTEGER)')
            handle.commit()
    with tempfile.TemporaryDirectory(prefix='recovery-browser-') as tmp:
        directory = Path(tmp)
        database = directory / 'configuration.db'
        user, group, registrations = configuration(
            options.source_config, database, routes)
        port = _free_port()
        config = directory / 'config.py'
        _write_config(config, directory, user, port)
        with config.open('a') as output:
            output.write(f'\nCDEADMIN_OPERATION_STORE_PATH = '
                         f'{str(directory / "operations.json")!r}\n')
        launcher = directory / 'launch.py'
        launcher.write_text(
            'import sys\n'
            f'sys.path.insert(0, {str(ROOT / "web")!r})\n'
            'from pgAdmin4 import app, main\n'
            'from flask import request, send_from_directory\n'
            '@app.before_request\n'
            'def qualification_assets():\n'
            '    prefix = "/static/js/generated/"\n'
            '    if request.path.startswith(prefix):\n'
            f'        return send_from_directory({str(options.assets)!r}, '
            'request.path[len(prefix):])\n'
            'main()\n')
        driver = process = None
        try:
            with (evidence / 'application.log').open('w') as log:
                process = subprocess.Popen(
                    [sys.executable, '-B', str(launcher)], cwd=ROOT,
                    env={**os.environ, 'CONFIG_DISTRO_FILE_PATH': str(config),
                         'SQLITE_PATH': str(database)}, stdout=log,
                    stderr=subprocess.STDOUT)
                _wait_for_server(process, port)
                chrome = webdriver.ChromeOptions()
                chrome.binary_location = browser_binary()
                for argument in ('--headless=new', '--no-sandbox',
                                 '--disable-dev-shm-usage',
                                 f'--user-data-dir={directory / "chrome"}'):
                    chrome.add_argument(argument)
                driver = webdriver.Chrome(
                    service=Service(str(options.driver)), options=chrome)
                driver.set_window_size(1600, 1100)
                driver.set_script_timeout(60)
                wait = WebDriverWait(driver, 60)
                driver.get(f'http://127.0.0.1:{port}/browser/')
                wait.until(lambda d: d.execute_script(
                    'return !!window.pgAdmin?.csrf_token'))
                for item, (_, secret) in zip(registrations, credentials):
                    endpoint_url = (
                        f'/browser/server/verify_endpoint/{group}/'
                        f'{item["id"]}')
                    response = driver.execute_async_script('''
                        const done=arguments[arguments.length-1];
                        const headers={'Content-Type':'application/json'};
                        headers[window.pgAdmin.csrf_token_header]=
                          window.pgAdmin.csrf_token;
                        fetch(arguments[0], {method:'POST', headers,
                          credentials:'same-origin',
                          body:JSON.stringify({password:arguments[1]})})
                          .then(async r=>{const body=await r.json();
                            done({status:r.status,ok:body.success,
                              error:String(body.errormsg || '').replaceAll(
                                arguments[1], '[redacted]')});})
                          .catch(()=>done({status:0}));
                    ''', endpoint_url, secret)
                    (evidence / f'verification-{item["id"]}.json').write_text(
                        json.dumps(response, indent=2) + '\n')
                    assert response['status'] == 200 and response['ok'] == 1
                driver.refresh()
                ensure_data_explorer(wait)
                expand(wait, 'Connectors')
                expand(wait, 'Firebird', ('Connectors',))
                # Native server labels can differ from registration names.
                # Select the visible node by its actual owned server identity.
                row = wait.until(lambda d: d.execute_script('''
                    const tree=window.pgAdmin.Browser.tree;
                    const rows=document.querySelectorAll('.file-entry');
                    for (const row of rows) {
                      const item=tree.itemFrom(row);
                      const data=item && tree.itemData(item);
                      if (data?._type==='server' &&
                          String(data._id)===String(arguments[0])) return row;
                    }
                    return null;
                ''', registrations[0]['id']))
                driver.execute_script('''
                    const tree=window.pgAdmin.Browser.tree;
                    const item=tree.itemFrom(arguments[0]);
                    const node=window.pgAdmin.Browser.Nodes.server;
                    node.callbacks.open_cde_workspace.call(
                      node,{item},'administration');
                ''', row)
                complete_endpoint_prompt(driver, credentials[0][1], timeout=30)

                def control(name):
                    return wait.until(lambda d: d.execute_script('''
                        const visible = e => e && e.getClientRects().length;
                        const labels=document.querySelectorAll('label');
                        for (const label of labels) {
                          if (!visible(label) ||
                              label.textContent.trim()!==arguments[0])
                            continue;
                          const input=document.getElementById(label.htmlFor) ||
                            label.querySelector('input');
                          if (input?.type==='checkbox') return label;
                          if (visible(input)) return input;
                        }
                        const buttons=document.querySelectorAll('button');
                        for (const button of buttons) {
                          if (visible(button) &&
                              button.textContent.trim()===arguments[0])
                            return button;
                        }
                        return null;
                    ''', name))

                def click(name):
                    element = control(name)
                    wait.until(lambda _: element.is_enabled() and
                               element.get_attribute('aria-disabled') !=
                               'true')
                    driver.execute_script(
                        'arguments[0].scrollIntoView({block:"center"})',
                        element)
                    element.click()

                def fill(name, value):
                    element = control(name)
                    wait.until(lambda _: element.is_enabled())
                    element.send_keys(Keys.CONTROL, 'a')
                    element.send_keys(value)

                def choose(name, value):
                    click(name)
                    option = wait.until(lambda d: d.execute_script('''
                        const options=document.querySelectorAll(
                          '[role=option]');
                        return [...options].find(e=>
                          e.getClientRects().length &&
                          e.dataset.value===arguments[0]) || null;
                    ''', str(value)))
                    option.click()

                click('Prepared Transaction Recovery')
                checks = []
                for decision in ('commit', 'rollback'):
                    handles = [native.connect(password=secret,
                               **_route_arguments(selected, native))
                               for selected, (_, secret) in zip(
                                   routes, credentials)]
                    manager = native.DistributedTransactionManager(
                        handles, default_action=native.DefaultAction.ROLLBACK)
                    identifiers = []
                    for handle in handles:
                        with manager.cursor(handle) as cursor:
                            cursor.execute(
                                'INSERT INTO RECOVERY_MARKER VALUES (1)')
                            cursor.execute(
                                'SELECT CURRENT_TRANSACTION FROM RDB$DATABASE')
                            identifiers.append(str(cursor.fetchone()[0]))
                    manager._tra.prepare()
                    for handle in handles:
                        handle._att.detach()
                        handle._att = None
                    manager._tra.release()
                    manager._tra = None
                    for handle in handles:
                        handle.main_transaction._tra = None
                    click('Load owned Firebird endpoints')
                    choose('Recovery decision', decision)
                    if decision == 'commit':
                        click('Add participant')
                    for index, item in enumerate(registrations, 1):
                        choose(f'Participant {index} endpoint', item['id'])
                        choose(f'Participant {index} database', item['target'])
                        fill(
                            f'Participant {index} transaction ID',
                            identifiers[index - 1])
                    click('Inspect and review participants')
                    apply = control('Apply reviewed recovery decision')
                    assert not apply.is_enabled()
                    for index, selected in enumerate(routes, 1):
                        fill(
                            f'Confirm participant {index} database',
                            selected['database'])
                        fill(
                            f'Confirm participant {index} transaction ID',
                            identifiers[index - 1])
                    click(
                        'Coordinator decision and every participant reviewed')
                    wait.until(lambda _: apply.is_enabled())
                    review_pages = screenshot_form_pages(
                        driver, evidence / f'{decision}-review',
                        selector='section[aria-label='
                        '"Coordinated Firebird recovery"]')
                    click('Apply reviewed recovery decision')
                    wait.until(lambda d: 'Recorded workflow state: '
                               'native_calls_returned' in
                               d.find_element('tag name', 'body').text)
                    driver.save_screenshot(
                        str(evidence / f'{decision}-result.png'))
                    observed = []
                    for selected, (_, secret) in zip(routes, credentials):
                        arguments = _route_arguments(selected, native)
                        with native.connect(
                                password=secret, **arguments) as handle:
                            with handle.cursor() as cursor:
                                cursor.execute(
                                    'SELECT COUNT(*) FROM RECOVERY_MARKER')
                                observed.append(cursor.fetchone()[0])
                    assert observed == [1, 1]
                    checks.append({'decision': decision,
                                   'observed_rows': observed,
                                   'review_pages': review_pages,
                                   'exact_confirmations_required': True})
                    retained_id = control(
                        'Recorded recovery group ID').get_attribute('value')
                    click('Start a separate review')
                fill('Recorded recovery group ID', retained_id)
                click('Read recorded status')
                wait.until(lambda d: 'Recorded workflow state: '
                           'native_calls_returned' in
                           d.find_element('tag name', 'body').text)
                assert not driver.find_elements(
                    'xpath', '//button[normalize-space(.)='
                    '"Apply reviewed recovery decision"]')
                checks.append({'retained_group_lookup_without_apply': True,
                               'browser_version': driver.capabilities[
                                   'browserVersion']})
                (evidence / 'browser-checks.json').write_text(
                    json.dumps(checks, indent=2) + '\n')
        except Exception:
            if driver is not None:
                driver.save_screenshot(str(evidence / 'failure.png'))
            raise
        finally:
            browser_closed = driver is None
            try:
                if driver is not None:
                    driver.quit()
                    browser_closed = True
            finally:
                if process is not None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                (evidence / 'application-cleanup.json').write_text(json.dumps({
                    'browser_closed': browser_closed,
                    'application_process_stopped': (
                        process is None or process.poll() is not None),
                }, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-config', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--driver', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    before = hashlib.sha256(options.source_config.read_bytes()).hexdigest()
    result = run_local(options.runtime, options.evidence,
                       lambda *args: browser_checks(options, *args))
    result['source_configuration_unchanged'] = before == hashlib.sha256(
        options.source_config.read_bytes()).hexdigest()
    result['complete'] &= result['source_configuration_unchanged']
    (options.evidence / 'summary.json').write_text(
        json.dumps(result, indent=2) + '\n')
    raise SystemExit(0 if result['complete'] else 1)
