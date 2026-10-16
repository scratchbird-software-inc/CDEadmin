#!/usr/bin/env python3
##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Exercise MariaDB 12.2.2 SQL Studio against an exact live runtime."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import mariadb
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as expected
from selenium.webdriver.support.ui import WebDriverWait


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cdeadmin_firebird_grid_ui_gate import (  # noqa: E402
    _button,
    _capture,
    _grid_control_evidence,
)
from tools.cdeadmin_firebird_ui_form_gate import (  # noqa: E402
    create_driver,
)
from tools.cdeadmin_provider_object_form_gate import _prepare_tree as prepare_provider_tree  # noqa: E402
from tools.cdeadmin_ui_evidence import (  # noqa: E402
    complete_endpoint_prompt,
    invoke_context_action,
    visible_named_control,
    wait_for_tree_item,
)


ORIGINAL_VALUE = 'mariadb-ui-gate'
COMMITTED_VALUE = 'mariadb-data-studio-commit'


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--engine', default='MariaDB')
    parser.add_argument('--server', default='localhost')
    parser.add_argument('--database', required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--endpoint-password-env', required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--summary-output', type=Path, required=True)
    parser.add_argument('--width', type=int, default=1600)
    parser.add_argument('--height', type=int, default=1000)
    parser.add_argument(
        '--theme', choices=('default', 'high-contrast'), default='default',
    )
    parser.add_argument(
        '--font-scale', type=int, choices=(100, 150, 200, 300), default=100,
    )
    parser.add_argument('--timeout', type=int, default=90)
    parser.add_argument('--browser-binary')
    return parser.parse_args(argv)


def _observer(options):
    password = os.environ.get(options.endpoint_password_env, '')
    if not password:
        raise RuntimeError('MariaDB SQL Studio password environment is empty')
    return mariadb.connect(
        host=options.host, port=options.port, user=options.user,
        password=password, database=options.database,
        connect_timeout=10,
    )


def _qualification_value(options):
    connection = _observer(options)
    cursor = connection.cursor()
    try:
        cursor.execute('SELECT value FROM qualification WHERE id = 1')
        row = cursor.fetchone()
        return None if row is None else row[0]
    finally:
        cursor.close()
        connection.close()


def _sleep_query_present(options):
    connection = _observer(options)
    cursor = connection.cursor()
    try:
        cursor.execute('SHOW FULL PROCESSLIST')
        return any(
            row[4] == 'Query' and row[7] and 'SLEEP(30)' in str(row[7])
            for row in cursor.fetchall()
        )
    finally:
        cursor.close()
        connection.close()


def _source_editor(driver):
    return next((
        item for item in driver.find_elements(By.CSS_SELECTOR, '.cm-content')
        if item.is_displayed()
    ), None)


def _set_query_source(driver, wait, source):
    # A native final result can arrive before its terminal receipt. Finish
    # the current bounded stream through its real navigation control first.
    def ready_editor(value):
        editor = _source_editor(value)
        if editor is not None and editor.get_attribute('contenteditable') == 'true':
            return editor
        next_page = next((item for item in value.find_elements(
            By.CSS_SELECTOR, 'button[aria-label="Next result page"]'
        ) if item.is_displayed() and item.is_enabled()), None)
        if next_page is not None:
            next_page.click()
        return False
    control = wait.until(ready_editor)
    control.click()
    control.send_keys(Keys.CONTROL, 'a')
    control.send_keys(source)
    wait.until(lambda value: _source_editor(value).text == source)


def _visible_result_actions(driver):
    try:
        return next((
            item for item in driver.find_elements(
                By.CSS_SELECTOR, '[aria-label="Result actions"]'
            ) if item.is_displayed()
        ), None)
    except StaleElementReferenceException:
        return None


def _alerts(driver):
    return [
        item.text.strip() for item in driver.find_elements(
            By.CSS_SELECTOR, '[role="alert"]'
        ) if item.is_displayed() and item.text.strip() and not (
            item.text.startswith('Provider workspace:')
        )
    ]


def _run_source(driver, wait, source, button='Run'):
    previous = _visible_result_actions(driver)
    _set_query_source(driver, wait, source)
    observed_source = _source_editor(driver).text
    if observed_source != source:
        raise RuntimeError(
            'MariaDB SQL editor did not retain the exact requested source'
        )
    _button(wait, button).click()
    if previous is not None:
        wait.until(expected.staleness_of(previous))
    try:
        if button == 'Run':
            wait.until(lambda value: _visible_result_actions(value) is not None)
        else:
            wait.until(lambda current: any(item.is_displayed() for item in current.find_elements(
                By.CSS_SELECTOR, '[aria-label="Query plan results"]')))
        if re.match(r'^\s*(UPDATE|INSERT|DELETE)\b', source, re.I):
            def finished(current):
                if _button(wait, 'Provider transaction state').is_enabled():
                    return True
                poll = _button(wait, 'Poll')
                if poll.is_enabled(): poll.click()
                return False
            wait.until(finished)
    except Exception as exc:
        raise RuntimeError(
            f'MariaDB SQL Studio execution did not render a result; '
            f'visible alerts: {_alerts(driver) or ["none"]}'
        ) from exc


def _wait_for_downloads(directory, count, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        files = [
            item for item in directory.iterdir()
            if item.is_file() and item.suffix.lower() in {
                '.json', '.csv', '.xlsx', '.svg', '.pdf',
            } and item.stat().st_size > 0
        ]
        if len(files) >= count:
            return sorted(files)
        time.sleep(0.1)
    raise RuntimeError(
        f'expected {count} MariaDB result downloads were not completed'
    )


def _assert_download_payloads(files):
    by_suffix = {
        suffix: [item for item in files if item.suffix.lower() == suffix]
        for suffix in ('.json', '.csv', '.xlsx', '.svg', '.pdf')
    }
    if any(len(items) != 1 for items in by_suffix.values()):
        raise RuntimeError(
            'MariaDB result downloads do not contain one file per format'
        )
    document = json.loads(
        by_suffix['.json'][0].read_text(encoding='utf-8')
    )
    if 'mariadb-ui-gate' not in json.dumps(document, sort_keys=True):
        raise RuntimeError('MariaDB JSON export lacks the live result row')
    with by_suffix['.csv'][0].open(
            encoding='utf-8', newline='') as stream:
        rows = list(csv.reader(stream))
    if not any('mariadb-ui-gate' in row for row in rows):
        raise RuntimeError('MariaDB CSV export lacks the live result row')
    if not by_suffix['.xlsx'][0].read_bytes().startswith(b'PK'):
        raise RuntimeError('MariaDB XLSX export is not an OOXML archive')
    if b'<svg' not in by_suffix['.svg'][0].read_bytes()[:512]:
        raise RuntimeError('MariaDB SVG export lacks an SVG root')
    if not by_suffix['.pdf'][0].read_bytes().startswith(b'%PDF-'):
        raise RuntimeError('MariaDB PDF export lacks a PDF signature')


def run(options):
    if mariadb.__version__ != '1.1.14':
        raise RuntimeError('MariaDB SQL Studio gate requires mariadb 1.1.14')
    downloads = options.output_root / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    options.download_dir = downloads
    driver = create_driver(options)
    wait = WebDriverWait(driver, options.timeout)
    screenshots = {}
    controls = {}

    def capture(state):
        _capture(driver, options, state, screenshots)
        controls[state] = _grid_control_evidence(driver)

    try:
        password = os.environ[options.endpoint_password_env]
        driver.get(options.url.rstrip('/') + '/browser/')
        prepare_provider_tree(driver, wait, options)
        database = wait_for_tree_item(wait, options.database)
        invoke_context_action(
            wait, driver, database,
            ['Database workspace', 'Open MariaDB SQL editor...'],
            password, endpoint_prompt_timeout=5,
        )
        complete_endpoint_prompt(driver, password, timeout=5)
        wait.until(lambda value: visible_named_control(
            value, 'Provider language'
        ))
        language = visible_named_control(driver, 'Provider language')
        language_value = language.get_attribute('value') or ''
        language_text = language.get_attribute('textContent') or ''
        if 'mariadb-sql' not in language_value and (
                'MariaDB SQL' not in language_text):
            raise RuntimeError('MariaDB SQL language profile was not selected')
        if 'SELECT id, value, event_date' not in wait.until(_source_editor).text:
            raise RuntimeError('MariaDB native starter source was not loaded')
        if _button(wait, 'Explain / query plan') is None:
            raise RuntimeError('MariaDB JSON query plan action is unavailable')
        capture('studio-opened')

        _run_source(
            driver, wait,
            'SELECT id, value, event_date FROM qualification ORDER BY id',
        )
        wait.until(lambda value: ORIGINAL_VALUE in value.page_source)
        capture('native-query-result')

        for index, export_format in enumerate(
                ('JSON', 'CSV', 'XLSX', 'SVG', 'PDF'), start=1):
            _button(wait, f'Export {export_format}').click()
            _wait_for_downloads(downloads, index, options.timeout)
        downloaded = _wait_for_downloads(downloads, 5, options.timeout)
        _assert_download_payloads(downloaded)
        capture('result-exported')

        _run_source(
            driver, wait,
            "SELECT id, CONCAT(value, '-comparison') AS value "
            'FROM qualification ORDER BY id',
        )
        compare = _button(wait, 'Compare with previous result')
        if not compare.is_enabled():
            raise RuntimeError('MariaDB result comparison is disabled')
        compare.click()
        wait.until(lambda value: any(
            item.is_displayed() for item in value.find_elements(
                By.CSS_SELECTOR, '[aria-label="Result comparison"]'
            )
        ))
        capture('result-compared')

        _run_source(
            driver, wait,
            'SELECT id, label FROM pagination_probe ORDER BY id',
        )
        next_page = _button(wait, 'Next result page')
        if not next_page.is_enabled():
            raise RuntimeError('MariaDB result paging is disabled')
        first_buffer = wait.until(lambda value: re.search(
            r'Rows on displayed page: (\d+)', value.find_element(
                By.CSS_SELECTOR, '[aria-label="Statement metrics"]'
            ).text))
        next_row = int(first_buffer.group(1)) + 1
        capture('result-page-one')
        next_page.click()
        wait.until(lambda value: f'row-{next_row}' in value.page_source)
        capture('result-page-two')
        # Native fetch batches and browser buffers have separate limits.
        # Drain the remaining qualified rows before authoring another query.
        def drain(current):
            if _button(wait, 'Provider transaction state').is_enabled():
                return True
            for label in ('Next result page', 'Poll'):
                control = _button(wait, label)
                if control.is_enabled():
                    control.click()
                    break
            return False
        wait.until(drain)

        _set_query_source(driver, wait, 'SELECT SLEEP(30) AS cancellation_probe')
        _button(wait, 'Run').click()
        wait.until(lambda _value: _sleep_query_present(options))
        def cancel_running_query(value):
            try:
                control = next((item for item in value.find_elements(
                    By.CSS_SELECTOR, 'button[aria-label="Cancel request"]'
                ) if item.is_displayed()), None)
                if control is None or not control.is_enabled():
                    return False
                control.click()
                return True
            except StaleElementReferenceException:
                return False
        wait.until(cancel_running_query)
        wait.until(lambda _value: not _sleep_query_present(options))
        wait.until(lambda _value: not _button(
            wait, 'Cancel request'
        ).is_enabled())
        capture('query-cancelled')

        _run_source(
            driver, wait,
            'SELECT id, value FROM qualification WHERE id = 1',
            button='Explain / query plan',
        )
        wait.until(lambda value: any(
            item.is_displayed() for item in value.find_elements(
                By.CSS_SELECTOR, '[aria-label="Query plan results"]'
            )
        ))
        capture('json-query-plan')

        _run_source(
            driver, wait,
            'SELECT id, value FROM qualification WHERE id = 1',
            button='MariaDB JSON execution analysis',
        )
        wait.until(lambda value: any(
            item.is_displayed() for item in value.find_elements(
                By.CSS_SELECTOR, '[aria-label="Query plan results"]'
            )
        ))
        capture('json-execution-analysis')

        _run_source(
            driver, wait,
            "UPDATE qualification SET value = 'mariadb-rollback-probe' "
            'WHERE id = 1',
        )
        if _qualification_value(options) != ORIGINAL_VALUE:
            raise RuntimeError(
                'MariaDB uncommitted change leaked to an independent session'
            )
        _button(wait, 'rollback').click()
        wait.until(lambda _value: _qualification_value(options) ==
                   ORIGINAL_VALUE)
        capture('transaction-rolled-back')

        _run_source(
            driver, wait,
            f"UPDATE qualification SET value = '{COMMITTED_VALUE}' "
            'WHERE id = 1',
        )
        if _qualification_value(options) != ORIGINAL_VALUE:
            raise RuntimeError(
                'MariaDB pre-commit change leaked to an independent session'
            )
        _button(wait, 'commit').click()
        wait.until(lambda _value: _qualification_value(options) ==
                   COMMITTED_VALUE)
        capture('transaction-committed')

        _button(wait, 'Provider transaction state').click()
        _button(wait, 'Messages').click()
        wait.until(lambda value: 'mariadb-session-transaction' in
                   value.page_source)
        capture('transaction-state')

        close_session = _button(wait, 'Close query session')
        if not close_session.is_enabled():
            raise RuntimeError('MariaDB query session is not open')
        close_session.click()
        wait.until(lambda value: not value.find_element(
            By.CSS_SELECTOR, 'button[aria-label="Close query session"]'
        ).is_enabled())
        capture('session-closed')

        return {
            'schema': 'cdeadmin.mariadb-data-studio-ui-gate.v1',
            'captured_at': datetime.now(timezone.utc).isoformat(),
            'engine_id': 'mariadb', 'interface_id': 'mariadb-native',
            'reference_version': '12.2.2',
            'language_profile': 'mariadb-sql',
            'native_starter_source_observed': True,
            'native_query_result_observed': True,
            'json_query_plan_observed': True,
            'json_execution_analysis_observed': True,
            'provider_streaming_observed': True,
            'native_query_cancellation_observed': True,
            'all_declared_export_formats_verified': True,
            'result_comparison_observed': True,
            'rollback_hidden_from_independent_session': True,
            'commit_observed_by_independent_session': True,
            'provider_transaction_state_observed': True,
            'provider_session_closed': True,
            'provider_finality_authority': True,
            'common_finality_interpreted': False,
            'credential_values_exported': False,
            'downloads': [
                {'name': item.name, 'bytes': item.stat().st_size}
                for item in downloaded
            ],
            'screenshots': screenshots, 'controls': controls,
            'passed': True,
        }
    except Exception:
        capture('failure')
        (options.output_root / 'failure.html').write_text(driver.page_source)
        raise
    finally:
        try:
            connection = _observer(options)
            cursor = connection.cursor()
            cursor.execute(
                'UPDATE qualification SET value = ? WHERE id = 1',
                (ORIGINAL_VALUE,),
            )
            connection.commit()
            cursor.close()
            connection.close()
        finally:
            driver.quit()


def main(argv=None):
    options = arguments(argv)
    evidence = run(options)
    options.summary_output.parent.mkdir(parents=True, exist_ok=True)
    options.summary_output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    print(json.dumps({
        'engine_id': evidence['engine_id'],
        'reference_version': evidence['reference_version'],
        'screenshot_count': len(evidence['screenshots']),
        'passed': evidence['passed'],
        'credential_values_exported': False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
