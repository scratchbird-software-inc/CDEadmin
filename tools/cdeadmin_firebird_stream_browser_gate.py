#!/usr/bin/env python3
"""Full application/native BLOB downloads with a substituted file picker.

Only the picker returns an origin-private file handle for automation. Native
queries, transport, forms, file writes and file-content checks remain real.
No claim is made about operating-system picker gestures or other platforms.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from tools.cdeadmin_firebird_recovery_browser_gate import (
    ROOT, configuration, _write_config, _free_port, _wait_for_server,
    browser_binary, ensure_data_explorer, expand, complete_endpoint_prompt,
    run_local, _route_arguments,
)

PICKER = '''
window.ownedFiles = [];
window.ownedSlowWrite = false;
window.showSaveFilePicker = async () => {
  const root = await navigator.storage.getDirectory();
  const handle = await root.getFileHandle(
    'owned-' + window.ownedFiles.length + '.bin', {create: true});
  const original = await handle.createWritable();
  await original.write('retained original');
  await original.close();
  const entry = {handle, writes: 0, largest: 0, closed: false, aborted: false};
  window.ownedFiles.push(entry);
  return {createWritable: async options => {
    const writer = await handle.createWritable(options);
    return {
      write: async bytes => {
        entry.writes++;
        entry.largest = Math.max(entry.largest, bytes.length);
        if (window.ownedSlowWrite) {
          await new Promise(resolve => setTimeout(resolve, 100));
        }
        await writer.write(bytes);
      },
      close: async () => { await writer.close(); entry.closed = true; },
      abort: async () => { await writer.abort(); entry.aborted = true; },
    };
  }};
};
'''
ORACLE = '''
const done = arguments[arguments.length - 1];
(async () => {
  const entry = window.ownedFiles[arguments[0]];
  const file = await entry.handle.getFile();
  const bytes = await file.arrayBuffer();
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return {size: file.size, writes: entry.writes, largest: entry.largest,
    closed: entry.closed, aborted: entry.aborted,
    sha256: [...new Uint8Array(digest)]
      .map(n => n.toString(16).padStart(2, '0')).join('')};
})().then(done).catch(error => done({error: error.name}));
'''


def qualify(options, native, admin, route, accounts, evidence, root,
            setup=None, exercise=None):
    embedded = getattr(options, 'embedded', False)
    user, password = ('OWNED_LOCAL', None) if embedded else accounts['Srp'][0]
    if embedded:
        route = {'attachment_mode': 'embedded', 'filesystem_root': str(root)}
    selected = dict(route, user=user, database=str(root / 'downloads.fdb'))
    binary = bytes(n % 251 for n in range(3600000))
    text = 'é漢🙂' * 400000
    boundary = b'x' * 65536
    with native.create_database(password=password, **_route_arguments(
            selected, native)) as connection:
        connection.execute_immediate(
            'CREATE TABLE DOWNLOAD_TEST (ID INTEGER, '
            'B BLOB SUB_TYPE BINARY, T BLOB SUB_TYPE TEXT CHARACTER SET UTF8)')
        connection.commit()
        connection.execute_immediate(
            'CREATE TABLE ARRAY_TEST (A INTEGER[-2:-1,3:602])')
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO ARRAY_TEST VALUES (?)',
                           ([[n for n in range(600)],
                             [n for n in range(600, 1200)]],))
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO DOWNLOAD_TEST VALUES (1, ?, ?)',
                           (binary, text))
            cursor.execute('INSERT INTO DOWNLOAD_TEST VALUES (2, ?, NULL)',
                           (b'',))
            cursor.execute('INSERT INTO DOWNLOAD_TEST VALUES (3, ?, NULL)',
                           (boundary,))
        connection.commit()
        if setup is not None:
            setup(connection)
    if getattr(options, 'attachment_charset', None):
        selected['charset'] = options.attachment_charset
    with tempfile.TemporaryDirectory(prefix='fb-app-') as temporary:
        directory = Path(temporary)
        database = directory / 'configuration.db'
        email, group, registrations = configuration(
            options.source_config, database, [selected])
        registration = registrations[0]
        # Keep the private fixture from discovering unrelated saved endpoints.
        with sqlite3.connect(database) as copied:
            copied.execute('DELETE FROM server WHERE id<>?',
                           (registration['id'],))
        port = _free_port()
        config = directory / 'config.py'
        _write_config(config, directory, email, port)
        with config.open('a') as output:
            output.write('\nCDEADMIN_OPERATION_STORE_PATH = ' +
                         repr(str(directory / 'operations.json')) + '\n')
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
                if getattr(options, 'browser', 'chrome') == 'firefox':
                    from selenium.webdriver.firefox.service import (
                        Service as FirefoxService,
                    )
                    browser_options = webdriver.FirefoxOptions()
                    browser_options.binary_location = '/usr/sbin/firefox'
                    browser_options.add_argument('-headless')
                    downloads = evidence / 'downloads'
                    downloads.mkdir(exist_ok=True)
                    for key, value in {
                            'browser.download.folderList': 2,
                            'browser.download.dir': str(downloads.resolve()),
                            'browser.download.useDownloadDir': True,
                            'browser.helperApps.neverAsk.saveToDisk':
                            'application/octet-stream',
                            'browser.download.alwaysOpenPanel': False,
                    }.items():
                        browser_options.set_preference(key, value)
                    driver = webdriver.Firefox(
                        service=FirefoxService(str(options.driver)),
                        options=browser_options)
                else:
                    chrome = webdriver.ChromeOptions()
                    chrome.binary_location = browser_binary()
                    for flag in ('--headless=new', '--no-sandbox',
                                 '--disable-dev-shm-usage',
                                 f'--user-data-dir={directory / "chrome"}'):
                        chrome.add_argument(flag)
                    driver = webdriver.Chrome(
                        service=Service(str(options.driver)), options=chrome)
                    driver.execute_cdp_cmd(
                        'Page.addScriptToEvaluateOnNewDocument',
                        {'source': PICKER})
                driver.set_window_size(1600, 1100)
                driver.set_script_timeout(60)
                wait = WebDriverWait(driver, 90)
                driver.get(f'http://127.0.0.1:{port}/browser/')
                wait.until(lambda d: d.execute_script(
                    'return !!window.pgAdmin?.csrf_token'))
                endpoint_url = (f'/browser/server/verify_endpoint/{group}/'
                                f'{registration["id"]}')
                response = driver.execute_async_script('''
                    const done=arguments[arguments.length-1];
                    const headers={'Content-Type':'application/json'};
                    headers[window.pgAdmin.csrf_token_header]=
                      window.pgAdmin.csrf_token;
                    fetch(arguments[0], {method:'POST', headers,
                      credentials:'same-origin',
                      body:JSON.stringify({password:arguments[1]})})
                      .then(async r=>{const body=await r.json();
                        done({status:r.status,ok:body.success});})
                      .catch(()=>done({status:0}));
                ''', endpoint_url, password)
                assert response == {'status': 200, 'ok': 1}, response
                driver.refresh()
                wait.until(lambda d: not any(element.is_displayed()
                           for element in d.find_elements(
                               'css selector', '#pg-spinner')))
                ensure_data_explorer(wait)
                expand(wait, 'Connectors')
                expand(wait, 'Firebird', ('Connectors',))
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
                ''', registration['id']))
                driver.execute_script('''
                    const tree=window.pgAdmin.Browser.tree;
                    const item=tree.itemFrom(arguments[0]);
                    const node=window.pgAdmin.Browser.Nodes.server;
                    node.callbacks.open_cde_workspace.call(
                      node,{item},arguments[2],
                      {database_target_id:arguments[1]});
                ''', row, registration['target'],
                                      getattr(options, 'workspace_tab',
                                              'studio'))
                if not embedded:
                    complete_endpoint_prompt(driver, password, timeout=30)

                def button(name):
                    return wait.until(lambda d: d.execute_script('''
                        const root = arguments[0] === 'Run' ?
                          document.querySelector(
                            '[aria-label="Provider query workspace"]') :
                          document;
                        return [...root.querySelectorAll('button')]
                          .find(e => e.getClientRects().length &&
                            e.textContent.trim()===arguments[0] &&
                            !e.disabled);
                    ''', name))

                def click(name):
                    element = button(name)
                    driver.execute_script(
                        'arguments[0].scrollIntoView({block:"center"})',
                        element)
                    element.click()

                if exercise is not None:
                    options.exercise_context = {
                        'endpoint_id': registration['id'],
                        'database_target_id': registration['target'],
                    }
                    exercise(driver, wait, click, native, selected, password,
                             evidence)
                    return

                def set_source(source):
                    editor = wait.until(lambda d: d.find_element(
                        'css selector', 'textarea[aria-label="Query source"]'))
                    editor.send_keys(Keys.CONTROL, 'a')
                    editor.send_keys(source)

                def open_blob(column, identifier):
                    set_source(f'SELECT {column} FROM DOWNLOAD_TEST '
                               f'WHERE ID={identifier}')
                    click('Run streaming')
                    button('Save BLOB to file')

                checks = []
                parameter_editor = wait.until(lambda d: d.execute_script('''
                    const label=[...document.querySelectorAll('label')]
                      .find(e=>e.textContent.startsWith('Query parameters'));
                    return label ?
                      document.getElementById(label.htmlFor) : null;
                '''))
                if embedded:
                    set_source('SELECT MON$REMOTE_PROTOCOL,MON$SERVER_PID '
                               'FROM MON$ATTACHMENTS WHERE MON$ATTACHMENT_ID='
                               'CURRENT_CONNECTION')
                    click('Run streaming')
                    selector = '[aria-label="Firebird streaming result"]'
                    wait.until(lambda d: str(process.pid) in d.find_element(
                        'css selector', selector).text)
                    cells = [cell.text for cell in driver.find_elements(
                        'css selector', selector + ' tbody td')]
                    assert 'null' in cells and str(process.pid) in cells
                    checks.append({'case': 'application-process-embedded',
                                   'native_pid': process.pid,
                                   'remote_protocol_absent': True})
                    click('Close stream')
                    button('Run streaming')
                if not options.zoned_only:
                    for index, (name, column, identifier, raw) in enumerate([
                            ('binary', 'B', 1, binary),
                            ('utf8', 'T', 1, text.encode('utf-8')),
                            ('empty', 'B', 2, b''),
                            ('boundary', 'B', 3, boundary)]):
                        open_blob(column, identifier)
                        click('Save BLOB to file')
                        wait.until(lambda d: 'BLOB file saved. Bytes:' in
                                   d.find_element('tag name', 'body').text)
                        result = driver.execute_async_script(ORACLE, index)
                        assert result['size'] == len(raw), result
                        assert result['sha256'] == hashlib.sha256(
                            raw).hexdigest()
                        assert result['closed'] and not result['aborted']
                        assert result['largest'] <= 65536
                        driver.save_screenshot(str(evidence / f'{name}.png'))
                        checks.append({'case': name, **result})
                        (evidence / 'completed-cases.json').write_text(
                            json.dumps(checks, indent=2) + '\n')
                        click('Close stream')
                        button('Run streaming')
                    driver.execute_script('window.ownedSlowWrite=true')
                    open_blob('B', 1)
                    click('Save BLOB to file')
                    wait.until(lambda d: d.execute_script(
                        'return window.ownedFiles[4]?.writes > 0'))
                    click('Stop BLOB save')
                    wait.until(lambda d: 'BLOB save stopped.' in
                               d.find_element('tag name', 'body').text)
                    result = driver.execute_async_script(ORACLE, 4)
                    assert result['aborted'] and not result['closed']
                    assert result['sha256'] == hashlib.sha256(
                        b'retained original').hexdigest()
                    checks.append({'case': 'stop', **result})
                    driver.save_screenshot(str(evidence / 'stop.png'))
                    click('Close stream')
                    button('Run streaming')

                    # Stage a file, use its one-shot binding and verify
                    # rollback through the same native query session.
                    driver.execute_script('window.ownedSlowWrite=false')
                    staged = b'\x00\xffupload' * 10000
                    staged_file = directory / 'staged.bin'
                    staged_file.write_bytes(staged)
                    upload_input = driver.find_element(
                        'css selector',
                        '[aria-label="Firebird streaming result"] '
                        'input[type=file]')
                    upload_input.send_keys(str(staged_file))
                    token = wait.until(lambda d: d.execute_script('''
                        const codes=document.querySelectorAll(
                          '[aria-label="Firebird streaming result"] code');
                        return [...codes].find(e=>e.textContent.startsWith(
                          '{"blob_upload":'))?.textContent || null;
                    '''))
                    parameter_editor = driver.execute_script('''
                        const label=[...document.querySelectorAll('label')]
                          .find(e=>e.textContent.startsWith(
                            'Query parameters'));
                        return document.getElementById(label.htmlFor);
                    ''')
                    parameter_editor.send_keys(Keys.CONTROL, 'a')
                    parameter_editor.send_keys('[' + token + ']')
                    set_source('UPDATE DOWNLOAD_TEST SET B=? WHERE ID=3')
                    click('Run streaming')
                    click('Close stream')
                    parameter_editor.send_keys(Keys.CONTROL, 'a')
                    parameter_editor.send_keys('[]')
                    with native.connect(password=password, **_route_arguments(
                            selected, native)) as observer:
                        with observer.cursor() as cursor:
                            cursor.execute('SELECT OCTET_LENGTH(B) FROM '
                                           'DOWNLOAD_TEST WHERE ID=3')
                            assert cursor.fetchone()[0] == len(boundary)
                    for index, (name, expected) in enumerate([
                            ('staged-upload', staged),
                            ('explicit-rollback', boundary)], 5):
                        if name == 'explicit-rollback':
                            click('rollback')
                            button('Run streaming')
                        open_blob('B', 3)
                        click('Save BLOB to file')
                        wait.until(lambda d: 'BLOB file saved. Bytes:' in
                                   d.find_element('tag name', 'body').text)
                        result = driver.execute_async_script(ORACLE, index)
                        assert result['size'] == len(expected)
                        assert result['sha256'] == hashlib.sha256(
                            expected).hexdigest()
                        assert result['closed'] and not result['aborted']
                        assert result['largest'] <= 65536
                        checks.append({'case': name, **result})
                        driver.save_screenshot(str(evidence / f'{name}.png'))
                        click('Close stream')
                        button('Run streaming')
                    checks.append({'uncommitted_upload_invisible_to_observer':
                                   True})
                    set_source('SELECT A FROM ARRAY_TEST')
                    click('Run streaming')
                    button('Read ARRAY slice')
                    assert 'ARRAY bounds: [[-2,-1],[3,602]]' in (
                        driver.find_element('tag name', 'body').text)
                    offset, slices = 0, []
                    while offset < 1200:
                        click('Read ARRAY slice' if offset == 0 else
                              'Next ARRAY slice')
                        end = offset + min(256, 600 - offset % 600)
                        wait.until(lambda d:
                                   f'ARRAY elements: {offset}–{end}' in
                                   d.find_element('tag name', 'body').text)
                        payload = driver.find_element(
                            'css selector',
                            '[aria-label="Firebird streaming result"] pre'
                        ).text
                        assert json.loads(payload) == list(range(offset, end))
                        coordinates = [-2 + offset // 600, 3 + offset % 600]
                        compact = json.dumps(
                            coordinates, separators=(',', ':'))
                        assert 'Starting coordinates: ' + compact in (
                            driver.find_element('tag name', 'body').text)
                        slices.append({'offset': offset, 'next_offset': end,
                                       'coordinates': coordinates})
                        offset = end
                    assert driver.execute_script('''
                        return [...document.querySelectorAll('button')]
                          .filter(e=>['Read ARRAY slice','Next ARRAY slice']
                            .includes(e.textContent.trim())).every(e=>e.disabled);
                    ''')
                    driver.save_screenshot(str(evidence / 'array-slices.png'))
                    click('Close stream')
                    button('Run streaming')
                    checks.append({'case': 'array-slices', 'slices': slices,
                                   'all_1200_values_verified': True})
                    click('Run streaming')
                    click('Save ARRAY to file')
                    wait.until(lambda d: 'ARRAY file saved. Elements: 1200' in
                               d.find_element('tag name', 'body').text)
                    expected_records = [{
                        'format': 'cdeadmin.firebird-array.v1',
                        'bounds': [[-2, -1], [3, 602]], 'element_count': 1200,
                        'native_element_type': 8, 'scale': 0,
                        'subtype': 0, 'charset_id': None,
                    }]
                    for part in slices:
                        expected_records.append({
                            'offset': part['offset'],
                            'coordinates': part['coordinates'],
                            'values': list(range(part['offset'],
                                                 part['next_offset'])),
                        })
                    expected_records.append({'complete': True,
                                             'element_count': 1200})
                    expected_file = ''.join(json.dumps(
                        record, separators=(',', ':')) + '\n'
                        for record in expected_records).encode('utf8')
                    result = driver.execute_async_script(ORACLE, 7)
                    assert result['sha256'] == hashlib.sha256(
                        expected_file).hexdigest()
                    assert result['closed'] and not result['aborted']
                    assert result['writes'] == 8
                    checks.append({'case': 'array-file', **result})
                    driver.save_screenshot(str(evidence / 'array-file.png'))
                    click('Close stream')
                    button('Run streaming')
                    changed_records = json.loads(json.dumps(expected_records))
                    for record in changed_records:
                        if 'values' in record:
                            record['values'] = [
                                n+10000 for n in record['values']]
                    changed_file = ''.join(json.dumps(
                        record, separators=(',', ':')) + '\n'
                        for record in changed_records).encode('utf8')
                    array_file = directory / 'staged-array.jsonl'
                    array_file.write_bytes(changed_file)
                    array_input = driver.find_element(
                        'css selector',
                        '[aria-label="Firebird streaming result"] '
                        'input[accept=".jsonl,application/x-ndjson"]'
                    )
                    array_input.send_keys(str(array_file))
                    array_token = wait.until(lambda d: d.execute_script('''
                        return [...document.querySelectorAll(
                          '[aria-label="Firebird streaming result"] code')]
                          .find(e=>e.textContent.startsWith('{"array_upload":'))
                          ?.textContent || null;
                    '''))
                    parameter_editor.send_keys(Keys.CONTROL, 'a')
                    parameter_editor.send_keys('[' + array_token + ']')
                    set_source('UPDATE ARRAY_TEST SET A=?')
                    click('Run streaming')
                    click('Close stream')
                    parameter_editor.send_keys(Keys.CONTROL, 'a')
                    parameter_editor.send_keys('[]')
                    with native.connect(password=password, **_route_arguments(
                            selected, native)) as observer:
                        with observer.cursor() as query:
                            query.execute('SELECT A[-2,3] FROM ARRAY_TEST')
                            assert query.fetchone()[0] == 0
                    for index, (name, expected) in enumerate([
                            ('array-upload', changed_file),
                            ('array-rollback', expected_file)], 8):
                        if name == 'array-rollback':
                            click('rollback')
                        set_source('SELECT A FROM ARRAY_TEST')
                        click('Run streaming')
                        click('Save ARRAY to file')
                        wait.until(lambda d:
                                   'ARRAY file saved. Elements: 1200' in
                                   d.find_element('tag name', 'body').text)
                        result = driver.execute_async_script(ORACLE, index)
                        assert result['sha256'] == hashlib.sha256(
                            expected).hexdigest()
                        assert result['closed'] and not result['aborted']
                        checks.append({'case': name, **result})
                        driver.save_screenshot(str(evidence / f'{name}.png'))
                        click('Close stream')
                        button('Run streaming')
                for clock in ('05:30', '06:30'):
                    zoned = {'encoding': 'firebird-timestamp-tz',
                             'utc': '2025-11-02 ' + clock + ':00.000100',
                             'time_zone': 'America/New_York'}
                    parameter_editor.send_keys(Keys.CONTROL, 'a')
                    parameter_editor.send_keys(json.dumps([zoned]))
                    set_source('SELECT CAST(? AS TIMESTAMP WITH TIME ZONE) '
                               'AS ZONED FROM RDB$DATABASE')
                    expected = json.dumps(zoned, separators=(',', ':'))
                    for action in ('Run streaming', 'Run'):
                        click(action)
                        selector = (
                            '[aria-label="Firebird streaming result"]'
                            if action == 'Run streaming' else 'body')
                        wait.until(lambda d: expected in d.find_element(
                            'css selector', selector).text)
                        if action == 'Run streaming':
                            click('Close stream')
                            button('Run streaming')
                    checks.append({'case': 'zoned-scalar-DST',
                                   'value': zoned,
                                   'ordinary_and_streaming': True})
                driver.save_screenshot(str(evidence / 'zoned-dst.png'))
                for kind, declaration in (('float32', 'FLOAT'),
                                          ('float64', 'DOUBLE PRECISION')):
                    for text in ('NaN', 'Infinity', '-Infinity', '-0.0'):
                        parameter_editor.send_keys(Keys.CONTROL, 'a')
                        parameter_editor.send_keys(json.dumps([
                            {'encoding': kind, 'data': text}]))
                        marker = kind + ':' + text
                        set_source("SELECT '" + marker + "' AS CASE_NAME, "
                                   'CAST(? AS ' + declaration + ') AS IEEE '
                                   'FROM RDB$DATABASE')
                        for action in ('Run streaming', 'Run'):
                            click(action)
                            selector = (
                                '[aria-label="Firebird streaming result"]'
                                if action == 'Run streaming' else
                                '[aria-label="Tabular provider results"]')
                            wait.until(lambda d: marker in d.find_element(
                                'css selector', selector).text)
                            cell_selector = (
                                ' tbody td' if action == 'Run streaming'
                                else ' [role=gridcell]')
                            displayed = [cell.text for cell in
                                         driver.find_elements(
                                             'css selector',
                                             selector + cell_selector)]
                            expected_float = repr(float(text))
                            if action == 'Run streaming':
                                expected_float = json.dumps(expected_float)
                            assert expected_float in displayed
                            if action == 'Run streaming':
                                click('Close stream')
                                button('Run streaming')
                        checks.append({'case': 'IEEE scalar', 'kind': kind,
                                       'value': text,
                                       'ordinary_and_streaming': True})
                driver.save_screenshot(str(evidence / 'ieee-scalars.png'))
                (evidence / 'checks.json').write_text(json.dumps({
                    'checks': checks,
                    'browser': driver.capabilities['browserVersion'],
                    'picker_substituted': True,
                    'native_queries_and_file_writes': True,
                }, indent=2) + '\n')
        except Exception:
            if driver is not None:
                driver.save_screenshot(str(evidence / 'failure.png'))
                (evidence / 'failure-body.txt').write_text(
                    driver.find_element('tag name', 'body').text)
            raise
        finally:
            try:
                if driver is not None:
                    driver.quit()
            finally:
                if process is not None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                (evidence / 'application-cleanup.json').write_text(json.dumps({
                    'application_stopped': (
                        process is None or process.poll() is not None),
                }, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-config', 'runtime', 'assets', 'driver', 'evidence'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--zoned-only', '--scalar-only',
                        dest='zoned_only', action='store_true')
    parser.add_argument('--embedded', action='store_true')
    options = parser.parse_args()
    before = hashlib.sha256(options.source_config.read_bytes()).hexdigest()
    if options.embedded:
        from tools.cdeadmin_firebird_recovery_group_gate import run_embedded
        result = run_embedded(options.runtime, options.evidence,
                              fixture_check=lambda *args: qualify(
                                  options, *args),
                              shared_process_access=True)
    else:
        result = run_local(options.runtime, options.evidence,
                           lambda *args: qualify(options, *args))
    result['source_configuration_unchanged'] = before == hashlib.sha256(
        options.source_config.read_bytes()).hexdigest()
    result['complete'] &= result['source_configuration_unchanged']
    (options.evidence / 'summary.json').write_text(
        json.dumps(result, indent=2) + '\n')
    raise SystemExit(0 if result['complete'] else 1)
