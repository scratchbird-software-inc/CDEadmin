#!/usr/bin/env python3
"""Browser script preview, execution and retained results."""
import argparse
import hashlib
import json
from pathlib import Path

from selenium.webdriver.common.keys import Keys
from tools.cdeadmin_firebird_stream_browser_gate import qualify, run_local
from tools.cdeadmin_firebird_stream_gate import _route_arguments


def exercise(options, driver, wait, click, native, route, password, evidence):
    directory = evidence / 'downloads'
    directory.mkdir(exist_ok=True)
    driver.execute_cdp_cmd('Browser.setDownloadBehavior', {
        'behavior': 'allow', 'downloadPath': str(directory.resolve())})

    def source(text):
        editor = wait.until(lambda d: d.find_element(
            'css selector', 'textarea[aria-label="Query source"]'))
        editor.send_keys(Keys.CONTROL, 'a')
        editor.send_keys(text)

    def export(name):
        click('Export script outcomes and results')
        path = directory / 'firebird-script-results.json'
        wait.until(lambda d: path.exists() and not tuple(
            directory.glob('*.crdownload')))
        result = json.loads(path.read_text())
        path.rename(directory / (name + '.json'))
        return result

    def run(text):
        source(text)
        click('Preview script')
        wait.until(lambda d: d.find_element(
            'css selector', '[aria-label="Script preview"]'))
        click('Run script')
        wait.until(lambda d: not any(e.is_displayed() for e in d.find_elements(
            'css selector', '[role="status"]') if
            'Waiting for provider query completion' in e.text))
        wait.until(lambda d: d.execute_script('''
          return [...document.querySelectorAll('button')].some(e=>
            e.textContent.trim()==='Preview script' && !e.disabled);
        '''))
        return export('case-' + str(len(tuple(directory.glob('case-*.json')))))

    checks = []
    file_source = "SELECT 'é漢' AS FILE_TEXT FROM RDB$DATABASE;"
    input_file = evidence / 'owned-input.sql'
    input_file.write_text(file_source, encoding='utf8')
    wait.until(lambda d: d.find_element('css selector',
               'input[aria-label="Load SQL script file"]')).send_keys(
                   str(input_file.resolve()))
    wait.until(lambda d: d.find_element('css selector',
               'textarea[aria-label="Query source"]').get_attribute('value')
               == file_source)
    click('Save SQL script')
    saved = directory / 'firebird-script.sql'
    wait.until(lambda d: saved.exists() and not tuple(
        directory.glob('*.crdownload')))
    assert saved.read_text(encoding='utf8') == file_source
    checks.append('browser-local-UTF8-load-and-save-without-native-dispatch')
    manual = run('''SET TERM ^ ;
CREATE PROCEDURE OWNED_UI RETURNS (V VARCHAR(40)) AS
BEGIN V = q'{script;value}'; SUSPEND; END^
SET TERM ; ^
SELECT * FROM OWNED_UI;
INSERT INTO SCRIPT_TARGET VALUES (1);
ROLLBACK;
''')
    assert all(e['state'] == 'succeeded' for e in manual['entries'])
    assert manual['entries'][3]['result']['payload']['rows'] == [
        ['script;value']]
    # Select an actual retained statement result through the form.
    selection = driver.find_element('css selector',
                                    '[aria-label="Script outcomes"] '
                                    '[role="combobox"]')
    driver.execute_script('arguments[0].scrollIntoView({block:"center"})',
                          selection)
    selection.click()
    option = wait.until(lambda d: next((e for e in d.find_elements(
        'css selector', '[role="option"]') if e.text.startswith('4:')), None))
    option.click()
    wait.until(lambda d: 'script;value' in d.find_element(
        'css selector', '[aria-label="Script statement result"]').text)
    driver.save_screenshot(str(evidence / 'manual-result.png'))
    checks.append('preview-PSQL-explicit-rollback-and-selected-typed-result')

    partial = run('''SET BAIL OFF;
INSERT INTO SCRIPT_TARGET VALUES (2);
INSERT INTO SCRIPT_TARGET VALUES (2);
SELECT ID FROM SCRIPT_TARGET;
ROLLBACK;
''')
    assert [e['state'] for e in partial['entries']] == [
        'succeeded', 'succeeded', 'failed', 'succeeded', 'succeeded']
    assert partial['entries'][3]['result']['payload']['rows'] == [[2]]
    checks.append('BAIL-OFF-keeps-partial-results-and-explicit-rollback')

    automatic = run('''SET AUTODDL ON;
CREATE TABLE SCRIPT_AUTO (ID INTEGER);
INSERT INTO SCRIPT_AUTO VALUES (3);
ROLLBACK;
''')
    assert all(e['state'] == 'succeeded' for e in automatic['entries'])
    assert automatic['entries'][1]['ddl_transaction']['scope'] == (
        'auxiliary-ddl')
    with native.connect(password=password, **_route_arguments(
            route, native)) as observer:
        with observer.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM SCRIPT_TARGET')
            assert cursor.fetchone() == (0,)
            cursor.execute('SELECT COUNT(*) FROM SCRIPT_AUTO')
            assert cursor.fetchone() == (0,)
    checks.append('auxiliary-DDL-committed-main-DML-rolled-back')

    source('INSERT INTO SCRIPT_TARGET VALUES (99); SHELL forbidden;')
    click('Preview script')
    wait.until(lambda d: 'client command requires its workspace workflow' in
               d.find_element('tag name', 'body').text)
    assert driver.execute_script('''
      return [...document.querySelectorAll('button')].find(e=>
        e.textContent.trim()==='Run script').disabled;
    ''')
    checks.append('late-host-command-refused-before-any-native-dispatch')
    (evidence / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-config', 'runtime', 'assets', 'driver', 'evidence'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--embedded', action='store_true')
    options = parser.parse_args()
    before = hashlib.sha256(options.source_config.read_bytes()).hexdigest()

    def setup(connection):
        with connection.cursor() as cursor:
            cursor.execute(
                'CREATE TABLE SCRIPT_TARGET(ID INTEGER PRIMARY KEY)')
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
