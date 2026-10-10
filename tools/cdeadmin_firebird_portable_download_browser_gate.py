#!/usr/bin/env python3
"""Real browser download-manager files from native Firebird streams."""
import argparse
import hashlib
import json
from pathlib import Path

from selenium.webdriver.common.keys import Keys

from tools.cdeadmin_firebird_stream_browser_gate import qualify, run_local


def exercise(options, driver, wait, click, native, route, password, evidence):
    directory = evidence / 'downloads'
    directory.mkdir(exist_ok=True)
    if options.browser == 'chrome':
        driver.execute_cdp_cmd('Browser.setDownloadBehavior', {
            'behavior': 'allow', 'downloadPath': str(directory.resolve()),
            'eventsEnabled': True})
    driver.execute_script('''
      delete window.showSaveFilePicker;
      const original=HTMLFormElement.prototype.submit;
      HTMLFormElement.prototype.submit=function() {
        if(this.elements.action?.value==='firebird_file_download') {
          window.ownedFileSubmission={url:this.getAttribute('action'),
            payload:JSON.parse(this.elements.payload.value)};
        }
        if(window.ownedAbortDownload) {
          window.ownedAbortDownload=false;
          const controller=new AbortController();
          fetch(this.getAttribute('action'), {method:'POST',
            body:new URLSearchParams(new FormData(this)),
            credentials:'same-origin',signal:controller.signal})
            .then(async response=>{
              const part=await response.body.getReader().read();
              window.ownedAbortedBytes=part.value?.length || 0;
              controller.abort();
            }).catch(()=>{});
          return;
        }
        return original.call(this);
      };
    ''')

    def set_source(sql):
        editor = wait.until(lambda d: d.find_element(
            'css selector', 'textarea[aria-label="Query source"]'))
        editor.send_keys(Keys.CONTROL, 'a')
        editor.send_keys(sql)

    def transaction_identity():
        set_source('SELECT CURRENT_TRANSACTION AS TX FROM RDB$DATABASE')
        click('Run streaming')
        cell = wait.until(lambda d: d.find_element(
            'css selector', '[aria-label="Streaming rows"] tbody td'))
        identity = cell.text
        click('Close stream')
        return identity

    transaction = transaction_identity()
    cases = [('binary', 'SELECT B FROM DOWNLOAD_TEST WHERE ID=1',
              'BLOB', bytes(n % 251 for n in range(3600000))),
             ('utf8', 'SELECT T FROM DOWNLOAD_TEST WHERE ID=1',
              'BLOB', ('é漢🙂' * 400000).encode('utf8')),
             ('empty', 'SELECT B FROM DOWNLOAD_TEST WHERE ID=2', 'BLOB', b''),
             ('boundary', 'SELECT B FROM DOWNLOAD_TEST WHERE ID=3',
              'BLOB', b'x' * 65536),
             ('array', 'SELECT A FROM ARRAY_TEST', 'ARRAY', None)]
    checks = []
    for name, sql, kind, expected in cases:
        editor = wait.until(lambda d: d.find_element(
            'css selector', 'textarea[aria-label="Query source"]'))
        editor.send_keys(Keys.CONTROL, 'a')
        editor.send_keys(sql)
        click('Run streaming')
        click('Download ' + kind + ' to browser')
        wait.until(lambda d: 'File sent to browser. Verify completion' in
                   d.find_element('tag name', 'body').text)
        filename = ('firebird-blob.bin' if kind == 'BLOB'
                    else 'firebird-array.jsonl')
        path = directory / filename
        wait.until(lambda d: path.exists() and not tuple(
            directory.glob('*.crdownload')))
        data = path.read_bytes()
        if expected is not None:
            assert data == expected, name
        else:
            records = [json.loads(line) for line in data.splitlines()]
            assert records[0]['format'] == 'cdeadmin.firebird-array.v1'
            assert records[0]['bounds'] == [[-2, -1], [3, 602]]
            assert records[-1] == {'complete': True, 'element_count': 1200}
            assert [value for record in records[1:-1]
                    for value in record['values']] == list(range(1200))
        refused = driver.execute_async_script('''
          const done=arguments[arguments.length-1];
          (async()=>{
            const capture=window.ownedFileSubmission;
            const statuses=[];
            for(const variant of ['replay','owner','csrf']) {
              const payload=structuredClone(capture.payload);
              if(variant==='owner') payload.request.owner_id='wrong-owner';
              const form=new URLSearchParams({action:'firebird_file_download',
                csrf_token:variant==='csrf'?'invalid':window.pgAdmin.csrf_token,
                payload:JSON.stringify(payload)});
              const response=await fetch(capture.url,{method:'POST',body:form,
                credentials:'same-origin'});
              statuses.push(response.status);
              await response.text();
            }
            done(statuses);
          })().catch(()=>done([]));
        ''')
        assert refused == [400, 400, 401], refused
        checks.append({'case': name, 'bytes': len(data),
                       'replay_owner_csrf_refused': True,
                       'sha256': hashlib.sha256(data).hexdigest(),
                       'actual_browser_file': True})
        path.rename(directory / (name + path.suffix))
        driver.save_screenshot(str(evidence / (name + '.png')))
        click('Close stream')
    driver.execute_script('window.ownedAbortDownload=true')
    set_source('SELECT B FROM DOWNLOAD_TEST WHERE ID=4')
    click('Run streaming')
    click('Download BLOB to browser')
    wait.until(lambda d: 'File delivery interrupted.' in
               d.find_element('tag name', 'body').text)
    received = driver.execute_script('return window.ownedAbortedBytes')
    assert 0 < received < 16 * 1024 * 1024
    click('Close stream')
    assert transaction_identity() == transaction
    checks.append({'case': 'http-disconnect', 'first_chunk_bytes': received,
                   'interrupted_observed': True,
                   'same_native_transaction_after_transfers': True})
    (evidence / 'checks.json').write_text(json.dumps({
        'checks': checks, 'picker_used': False,
        'browser': driver.capabilities['browserVersion'],
        'os_picker_claim': False}, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-config', 'runtime', 'assets', 'driver', 'evidence'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--embedded', action='store_true')
    parser.add_argument('--browser', choices=('chrome', 'firefox'),
                        default='chrome')
    options = parser.parse_args()
    before = hashlib.sha256(options.source_config.read_bytes()).hexdigest()

    def setup(connection):
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO DOWNLOAD_TEST VALUES (4, ?, NULL)',
                           (b'x' * (16 * 1024 * 1024),))
        connection.commit()

    def check(*args):
        return qualify(options, *args, setup=setup, exercise=(
            lambda *values: exercise(options, *values)))

    if options.embedded:
        from tools.cdeadmin_firebird_recovery_group_gate import run_embedded
        result = run_embedded(options.runtime, options.evidence,
                              fixture_check=check, shared_process_access=True)
    else:
        result = run_local(options.runtime, options.evidence, check)
    result['source_configuration_unchanged'] = before == hashlib.sha256(
        options.source_config.read_bytes()).hexdigest()
    result['complete'] &= result['source_configuration_unchanged']
    (options.evidence / 'summary.json').write_text(
        json.dumps(result, indent=2) + '\n')
    raise SystemExit(0 if result['complete'] else 1)
