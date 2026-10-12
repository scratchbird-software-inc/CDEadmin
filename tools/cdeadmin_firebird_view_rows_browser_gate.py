#!/usr/bin/env python3
"""Actual view row controls backed by native Firebird and explicit rollback."""
import argparse
import hashlib
import json
from pathlib import Path

from selenium.webdriver.common.keys import Keys
from tools.cdeadmin_firebird_stream_browser_gate import (
    qualify, run_local, _route_arguments,
)


def setup(connection):
    for source in (
            'CREATE TABLE UI_BASE (ID INTEGER PRIMARY KEY,V INTEGER)',
            'CREATE TABLE UI_LOOKUP (ID INTEGER PRIMARY KEY,W INTEGER)',
            'CREATE TABLE UI_DUP (V INTEGER,B BLOB SUB_TYPE -42)',
            'CREATE VIEW UI_INNER AS SELECT ID,V FROM UI_BASE',
            'CREATE VIEW UI_NESTED AS SELECT ID AS K,V AS VAL FROM UI_INNER',
            'CREATE VIEW UI_KEYLESS AS SELECT V FROM UI_DUP',
            'CREATE VIEW UI_JOINED AS SELECT B.ID,B.V,L.W FROM UI_BASE B '
            'JOIN UI_LOOKUP L ON B.ID=L.ID',
            'CREATE TRIGGER UI_JOINED_BI FOR UI_JOINED ACTIVE BEFORE INSERT '
            'AS BEGIN INSERT INTO UI_BASE VALUES(NEW.ID,NEW.V); '
            'INSERT INTO UI_LOOKUP VALUES(NEW.ID,NEW.W); END'):
        connection.execute_immediate(source)
        connection.commit()
    with connection.cursor() as query:
        for source in ('INSERT INTO UI_BASE VALUES(1,11)',
                       'INSERT INTO UI_BASE VALUES(2,12)',
                       'INSERT INTO UI_LOOKUP VALUES(1,21)',
                       'INSERT INTO UI_LOOKUP VALUES(2,22)',
                       'INSERT INTO UI_DUP(V) VALUES(7)',
                       'INSERT INTO UI_DUP(V) VALUES(7)'):
            query.execute(source)
        query.execute('UPDATE UI_DUP SET B=?', [b'\xff\0'])
    connection.commit()


def exercise(driver, wait, click, native, route, password, evidence):
    checks = []
    wait._timeout = 30

    def select(name):
        control = wait.until(lambda d: d.execute_script('''
            const label=[...document.querySelectorAll('label')]
              .find(e=>e.textContent==='Table or view');
            return label && document.getElementById(label.htmlFor);
        '''))
        control.click()
        option = wait.until(lambda d: next((item for item in d.find_elements(
            'css selector', '[role=option]') if item.text == name), None))
        option.click()
        click('Load rows')
        wait.until(lambda d: d.find_elements(
            'css selector', '[aria-label="Provider table or view rows"]'))

    def inputs(column, new=False):
        return driver.find_elements('css selector',
                                    f'input[aria-label="{column} '
                                    f'{"new value" if new else "value"}"]')

    def set_value(field, text):
        field.send_keys(Keys.CONTROL, 'a')
        field.send_keys(text)

    def row_action(column, action):
        def ready(driver):
            fields = inputs(column)
            if not fields or not fields[0].is_enabled():
                return None
            row = fields[0].find_element(
                'xpath', './ancestor::*[@role="row"][1]')
            return next((button for button in row.find_elements(
                'tag name', 'button') if button.text == action and
                button.is_enabled()), None)
        button = wait.until(ready)
        driver.execute_script(
            'arguments[0].scrollIntoView({block:"center"})', button)
        button.click()

    def observe(source):
        with native.connect(password=password, **_route_arguments(
                route, native)) as connection:
            with connection.cursor() as query:
                query.execute(source)
                return query.fetchall()

    select('UI_KEYLESS')
    wait.until(lambda d: len(inputs('V')) == 2)
    assert all(field.is_enabled() for field in inputs('V'))
    set_value(inputs('V', True)[0], '33')
    click('Insert row')
    wait.until(lambda d: len(inputs('V')) == 3)
    assert observe('SELECT V FROM UI_DUP') == [(7,), (7,)]
    driver.save_screenshot(str(evidence / 'keyless-insert.png'))
    click('Rollback changes')
    wait.until(lambda d: len(inputs('V')) == 2)
    checks.append('Keyless duplicate rows render and support staged insertion')
    field = inputs('V')[0]
    set_value(field, '41')
    row_action('V', 'Save')
    wait.until(lambda d: sorted(item.get_attribute('value') for item in
                                inputs('V')) == ['41', '7'])
    wait.until(lambda d: '1 grid change(s)' in
               d.find_element('tag name', 'body').text)
    assert observe('SELECT V FROM UI_DUP') == [(7,), (7,)]
    click('Rollback changes')
    wait.until(lambda d: [item.get_attribute('value') for item in
                          inputs('V')] == ['7', '7'])
    driver.execute_script('''
      window.rowClickEvents=[];
      for (const kind of ['mousedown','mouseup','click']) {
        document.addEventListener(kind, e => {
          if (kind==='mousedown') window.clickedButton=e.target;
          window.rowClickEvents.push({
            kind, tag:e.target.tagName, text:e.target.textContent,
            disabled:e.target.disabled,
            connected:window.clickedButton.isConnected,
            rect:window.clickedButton.getBoundingClientRect().toJSON(),
            x:e.clientX, y:e.clientY});
        }, {capture:true});
      }
    ''')
    row_action('V', 'Delete')
    pointer_events = driver.execute_script('return window.rowClickEvents')
    (evidence / 'delete-click.json').write_text(json.dumps(
        pointer_events, indent=2))
    assert [event['kind'] for event in pointer_events] == [
        'mousedown', 'mouseup', 'click']
    assert all(event['tag'] == 'BUTTON' and event['text'] == 'Delete'
               for event in pointer_events)
    click('Confirm delete')
    wait.until(lambda d: len(inputs('V')) == 1)
    assert observe('SELECT V FROM UI_DUP') == [(7,), (7,)]
    driver.save_screenshot(str(evidence / 'keyless-single-delete.png'))
    click('Rollback changes')
    wait.until(lambda d: len(inputs('V')) == 2)
    checks.append('Physical identity edits/deletes only one duplicate row')
    select('UI_DUP')
    field = wait.until(lambda d: inputs('B')[0] if inputs('B') else None)
    assert field.get_attribute('value') == '/wA='
    set_value(field, 'AP8=')
    row_action('B', 'Save')
    wait.until(lambda d: '1 grid change(s)' in
               d.find_element('tag name', 'body').text)
    assert observe('SELECT B FROM UI_DUP') == [(b'\xff\0',), (b'\xff\0',)]
    click('Rollback changes')
    wait.until(lambda d: all(field.get_attribute('value') == '/wA='
                             for field in inputs('B')))
    checks.append(
        'Native negative BLOB subtype has a reversible binary editor')

    select('UI_NESTED')
    field = wait.until(lambda d: inputs('VAL')[0] if inputs('VAL') else None)
    set_value(field, '77')
    row_action('VAL', 'Save')
    wait.until(lambda d: inputs('VAL')[0].get_attribute('value') == '77')
    wait.until(lambda d: '1 grid change(s)' in
               d.find_element('tag name', 'body').text)
    assert observe('SELECT V FROM UI_BASE WHERE ID=1') == [(11,)]
    driver.save_screenshot(str(evidence / 'nested-update.png'))
    click('Rollback changes')
    wait.until(lambda d: inputs('VAL')[0].get_attribute('value') == '11')
    checks.append('Nested aliased primary key supports staged update/rollback')

    select('UI_JOINED')
    wait.until(lambda d: len(inputs('V')) == 2)
    for column, value in (('ID', '101'), ('V', '33'), ('W', '44')):
        set_value(inputs(column, True)[0], value)
    click('Insert row')
    wait.until(lambda d: len(inputs('V')) == 3)
    assert observe('SELECT COUNT(*) FROM UI_BASE')[0][0] == 2
    assert observe('SELECT COUNT(*) FROM UI_LOOKUP')[0][0] == 2
    driver.save_screenshot(str(evidence / 'joined-trigger-insert.png'))
    click('Rollback changes')
    wait.until(lambda d: len(inputs('V')) == 2)
    checks.append(
        'Joined view insertion executes native trigger under rollback')
    (evidence / 'checks.json').write_text(json.dumps({
        'checks': checks, 'browser': driver.capabilities['browserVersion'],
        'native_queries_and_forms': True}, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-config', 'runtime', 'assets', 'driver', 'evidence'):
        parser.add_argument('--'+name, type=Path, required=True)
    options = parser.parse_args()
    options.workspace_tab = 'data'
    before = hashlib.sha256(options.source_config.read_bytes()).hexdigest()
    result = run_local(options.runtime, options.evidence,
                       lambda *args: qualify(options, *args, setup=setup,
                                             exercise=exercise))
    result['source_configuration_unchanged'] = before == hashlib.sha256(
        options.source_config.read_bytes()).hexdigest()
    result['complete'] &= result['source_configuration_unchanged']
    (options.evidence / 'summary.json').write_text(
        json.dumps(result, indent=2)+'\n')
    raise SystemExit(0 if result['complete'] else 1)
