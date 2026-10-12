#!/usr/bin/env python3
"""Real retained-session prepare-only Firebird plan controls."""
import argparse
import hashlib
import json
from pathlib import Path

from selenium.webdriver.common.keys import Keys
from tools.cdeadmin_firebird_stream_browser_gate import qualify, run_local
from tools.cdeadmin_firebird_stream_gate import _route_arguments


def exercise(options, driver, wait, click, native, route, password, evidence):
    def source(text):
        editor = wait.until(lambda d: d.find_element(
            'css selector', 'textarea[aria-label="Query source"]'))
        editor.send_keys(Keys.CONTROL, 'a')
        editor.send_keys(text)

    source('INSERT INTO PLAN_TARGET VALUES (7)')
    click('Run')
    wait.until(lambda d: d.execute_script('''
      const root=document.querySelector(
        '[aria-label="Provider query workspace"]');
      return [...root.querySelectorAll('button')].some(e=>
        e.textContent.trim()==='Run' && !e.disabled);
    '''))
    parameters = driver.execute_script('''
      const label=[...document.querySelectorAll('label')].find(e=>
        e.textContent.trim()==='Query parameters (JSON array)');
      return label && document.getElementById(label.htmlFor);
    ''')
    parameters.send_keys(Keys.CONTROL, 'a')
    parameters.send_keys('invalid JSON must not be bound')
    checks = []
    for sql, kind in [('DELETE FROM PLAN_TARGET WHERE ID=?', 'DELETE'),
                      ('COMMIT', 'COMMIT'), ('ROLLBACK', 'ROLLBACK'),
                      ('CREATE TABLE PLAN_NEVER(ID INT)', 'DDL'),
                      ('SELECT * FROM PLAN_TARGET WHERE ID=?', 'SELECT')]:
        source(sql)
        click('Explain / query plan')
        panel = wait.until(lambda d: next((e for e in d.find_elements(
            'css selector', '[aria-label="Firebird query plan"]')
            if 'Statement type: ' + kind in e.text), None))
        assert 'statement was not executed' in panel.text
        assert 'Preparation used the existing transaction.' in panel.text
        if kind in ('DELETE', 'SELECT'):
            assert 'PLAN_TARGET' in driver.find_element(
                'css selector', '[aria-label="Legacy plan text"]').text
            assert 'PLAN_TARGET' in driver.find_element(
                'css selector', '[aria-label="Detailed plan text"]').text
            assert 'Parameters: 1' in panel.text
        else:
            assert 'supplied no plan text' in panel.text
        driver.save_screenshot(str(evidence / (kind.lower() + '.png')))
        checks.append({'statement_type': kind, 'prepare_only': True})
    parameters.send_keys(Keys.CONTROL, 'a')
    parameters.send_keys('[]')
    source('SELECT ID FROM PLAN_TARGET ORDER BY ID')
    click('Run')
    wait.until(lambda d: [e.text for e in d.find_elements('css selector',
               '[aria-label="Tabular provider results"] [role="gridcell"]')]
               == ['5', '7'])
    with native.connect(password=password, **_route_arguments(
            route, native)) as observer:
        with observer.cursor() as cursor:
            cursor.execute('SELECT ID FROM PLAN_TARGET ORDER BY ID')
            assert cursor.fetchall() == [(5,)]
            cursor.execute("SELECT COUNT(*) FROM RDB$RELATIONS WHERE "
                           "RDB$RELATION_NAME='PLAN_NEVER'")
            assert cursor.fetchone() == (0,)
    # Explicit finality remains a separate control and ignores editor bindings.
    click('rollback')
    checks.append({'native_pending_work_not_committed_by_preparation': True,
                   'native_DDL_not_executed': True})
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
            cursor.execute('CREATE TABLE PLAN_TARGET(ID INTEGER PRIMARY KEY)')
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO PLAN_TARGET VALUES (5)')
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
