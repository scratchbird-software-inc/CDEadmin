#!/usr/bin/env python3
"""Actual application legacy-charset identifiers and returned values."""
import argparse
import hashlib
import json
from pathlib import Path

from selenium.webdriver.common.keys import Keys
from tools.cdeadmin_firebird_stream_browser_gate import qualify, run_local
from tools.cdeadmin_firebird_stream_gate import _route_arguments


def exercise(options, driver, wait, click, native, route, password, evidence):
    table, column, first, changed, charset_id = options.identifier_case
    editor = wait.until(lambda d: d.find_element(
        'css selector', 'textarea[aria-label="Query source"]'))
    editor.send_keys(Keys.CONTROL, 'a')
    editor.send_keys(f'SELECT "{column}" AS "{first}" FROM "{table}"')
    click('Run')
    wait.until(lambda d: [e.text for e in d.find_elements('css selector',
               '[aria-label="Tabular provider results"] [role="gridcell"]')]
               == [first])
    assert first in driver.find_element(
        'css selector', '[aria-label="Tabular provider results"]').text
    driver.save_screenshot(str(evidence / 'latin1-result.png'))
    editor.send_keys(Keys.CONTROL, 'a')
    editor.send_keys(f'UPDATE "{table}" SET "{column}"=? '
                     f'RETURNING "{column}"')
    parameters = driver.execute_script('''
      const label=[...document.querySelectorAll('label')].find(e=>
        e.textContent.trim()==='Query parameters (JSON array)');
      return label && document.getElementById(label.htmlFor);
    ''')
    parameters.send_keys(Keys.CONTROL, 'a')
    parameters.send_keys(json.dumps([changed], ensure_ascii=False))
    click('Run')
    wait.until(lambda d: [e.text for e in d.find_elements('css selector',
               '[aria-label="Tabular provider results"] [role="gridcell"]')]
               == [changed])
    click('rollback')
    with native.connect(password=password, **_route_arguments(
            dict(route, charset='UTF8'), native)) as observer:
        with observer.cursor() as cursor:
            cursor.execute(f'SELECT COUNT(*) FROM "{table}" '
                           f'WHERE "{column}"=?', [first])
            assert cursor.fetchone() == (1,)
    parameters.send_keys(Keys.CONTROL, 'a')
    parameters.send_keys('[]')
    editor.send_keys(Keys.CONTROL, 'a')
    editor.send_keys('SELECT MON$CHARACTER_SET_ID FROM MON$ATTACHMENTS '
                     'WHERE MON$ATTACHMENT_ID=CURRENT_CONNECTION')
    click('Run')
    wait.until(lambda d: [e.text for e in d.find_elements('css selector',
               '[aria-label="Tabular provider results"] [role="gridcell"]')]
               == [str(charset_id)])
    click('rollback')
    (evidence / 'checks.json').write_text(json.dumps({
        'observed_native_charset_id': charset_id,
        'non_ascii_relation_column_alias_and_values': True,
        'native_returning_metadata': True,
        'explicit_rollback_preserved_original': True}, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-config', 'runtime', 'assets', 'driver', 'evidence'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--embedded', action='store_true')
    parser.add_argument('--charset', default='ISO8859_1',
                        choices=['ISO8859_1', 'NEXT', 'CP943C'])
    options = parser.parse_args()
    options.attachment_charset = options.charset
    options.identifier_case = {
        'ISO8859_1': ('café', 'clé', 'été', 'Noël', 21),
        'NEXT': ('café', 'clé', 'été', 'Noël', 19),
        'CP943C': ('日本', '列', '日本語', '漢字', 68),
    }[options.charset]
    before = hashlib.sha256(options.source_config.read_bytes()).hexdigest()

    def setup(connection):
        table, column, first, _, _ = options.identifier_case
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE TABLE "{table}"("{column}" VARCHAR(40) '
                           'CHARACTER SET UTF8)')
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute(f'INSERT INTO "{table}" VALUES(?)', [first])
        connection.commit()

    def check(native, admin, route, accounts, evidence, root):
        return qualify(options, native, admin, route, accounts,
                       evidence, root, setup=setup, exercise=(
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
