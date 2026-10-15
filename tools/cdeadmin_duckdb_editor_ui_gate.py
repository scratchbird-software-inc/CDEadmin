#!/usr/bin/env python3
"""Exercise DuckDB's shared SQL source, parameters, history and script UI."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cdeadmin_firebird_query_ui_gate import _query_editor  # noqa: E402
from tools.cdeadmin_firebird_ui_form_gate import create_driver, prepare_tree, screenshot  # noqa: E402
from tools.cdeadmin_sqlite_query_ui_gate import _run_query, _set_query  # noqa: E402
from tools.cdeadmin_ui_evidence import (  # noqa: E402
    complete_endpoint_prompt, invoke_context_action,
    wait_for_tree_item,
)


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('url', 'database'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--engine', default='DuckDB')
    parser.add_argument('--server', default='localhost')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int)
    parser.add_argument('--user')
    parser.add_argument('--endpoint-password-env')
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--summary-output', type=Path, required=True)
    parser.add_argument('--width', type=int, default=1600)
    parser.add_argument('--height', type=int, default=1000)
    parser.add_argument('--theme', default='default')
    parser.add_argument('--font-scale', type=int, default=100)
    parser.add_argument('--timeout', type=int, default=90)
    parser.add_argument('--browser-binary')
    return parser.parse_args(argv)


def _details(driver, name):
    item = next((item for item in driver.find_elements(By.CSS_SELECTOR, 'details > summary')
                 if item.is_displayed() and item.text.strip() == name), None)
    if item is None:
        raise RuntimeError('Missing shared SQL section: ' + name)
    if not driver.execute_script('return arguments[0].parentElement.open', item):
        item.click()


def _input(driver, name, value):
    control = next((item for item in driver.find_elements(
        By.CSS_SELECTOR, 'input, textarea') if item.accessible_name == name), None)
    if control is None:
        raise RuntimeError('Missing shared SQL control: ' + name)
    driver.execute_script('arguments[0].scrollIntoView({block: "center"});', control)
    driver.execute_script('''
      const prototype = arguments[0] instanceof HTMLTextAreaElement ?
        HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(prototype, 'value').set;
      setter.call(arguments[0], arguments[1]);
      arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
      arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
    ''', control, value)


def _screen(driver, options, name, screenshots):
    path = options.output_root / f'{name}-{options.width}x{options.height}-{options.theme}.png'
    screenshots[name] = {'path': str(path), 'sha256': screenshot(driver, path)}


def _show_engine_options(driver, wait):
    panels = driver.find_elements(By.CSS_SELECTOR,
        '[role="tabpanel"][aria-label="Engine options"]')
    if not panels:
        _details(driver, 'Execution options, scripts and diagnostics')
        return
    panel = panels[0]
    if panel.get_attribute('hidden') is not None:
        tab = wait.until(lambda value: next((item for item in value.find_elements(
            By.CSS_SELECTOR, '[role="tab"]') if item.text.strip() == 'Engine options'), None))
        driver.execute_script('arguments[0].scrollIntoView({block: "center"});', tab)
        tab.click()
    wait.until(lambda value: value.find_element(By.CSS_SELECTOR,
        '[role="tabpanel"][aria-label="Engine options"]').get_attribute('hidden') is None)


def _show_data_output(driver, wait):
    panels = driver.find_elements(By.CSS_SELECTOR,
        '[role="tabpanel"][aria-label="Data Output"]')
    if panels and panels[0].get_attribute('hidden') is not None:
        tab = wait.until(lambda value: next((item for item in value.find_elements(
            By.CSS_SELECTOR, '[role="tab"]') if item.text.strip() == 'Data Output'), None))
        driver.execute_script('arguments[0].scrollIntoView({block: "center"});', tab)
        tab.click()


def _workspace_button(driver, wait, name):
    def found(value):
        return next((item for item in value.find_elements(By.CSS_SELECTOR,
            '[role="region"][aria-label="Provider query workspace"] button')
            if (item.get_attribute('textContent') or '').strip() == name or
            item.get_attribute('aria-label') == name), None)
    button = wait.until(found)
    driver.execute_script('arguments[0].scrollIntoView({block: "center"});', button)
    return button


def _click_workspace_button(driver, wait, name):
    driver.execute_script('arguments[0].click()',
                          _workspace_button(driver, wait, name))


def _workspace_checkbox(driver, wait, name):
    control = wait.until(lambda value: next((item for item in value.find_elements(
        By.CSS_SELECTOR, '[role="region"][aria-label="Provider query workspace"] input[type="checkbox"]')
        if item.accessible_name == name), None))
    driver.execute_script('arguments[0].scrollIntoView({block: "center"});', control)
    return control


def run(options):
    options.download_dir = options.output_root / 'downloads'
    options.download_dir.mkdir(parents=True, exist_ok=True)
    driver = create_driver(options)
    wait = WebDriverWait(driver, options.timeout)
    screenshots = {}
    try:
        password = os.environ.get(options.endpoint_password_env or '', '')
        prepare_tree(driver, wait, options, password)
        database = wait_for_tree_item(wait, options.database)
        invoke_context_action(wait, driver, database,
            ['Database workspace', 'Open DuckDB SQL editor...'], password,
            endpoint_prompt_timeout=5 if password else 1)
        complete_endpoint_prompt(driver, password, timeout=5 if password else 1)
        wait.until(lambda value: _query_editor(value))
        _details(driver, 'Source tools')
        _screen(driver, options, 'source-tools', screenshots)

        # History source retention is an explicit user policy in the isolated
        # configuration clone. No bound values or result rows enter history.
        _show_engine_options(driver, wait)
        _click_workspace_button(driver, wait, 'SQL history')
        remembered = _workspace_checkbox(driver, wait, 'Remember SQL source')
        if not remembered.is_selected():
            remembered.click()
        _click_workspace_button(driver, wait, 'Save history policy')
        wait.until(lambda value: (
            (control := _workspace_checkbox(value, wait, 'Remember SQL source'))
            is not None and control.is_selected()))
        _screen(driver, options, 'history-policy', screenshots)
        _input(driver, 'Query parameters (JSON object or array)', '[42]')
        _show_data_output(driver, wait)
        _run_query(driver, wait, 'SELECT ? AS bound_value', '42', 'DuckDB', options.output_root)
        _screen(driver, options, 'bound-result', screenshots)
        _show_engine_options(driver, wait)
        _click_workspace_button(driver, wait, 'Search / refresh history')
        wait.until(lambda value: any(item.is_displayed() and 'SELECT ? AS bound_value' in item.text
            for item in value.find_elements(By.CSS_SELECTOR, '[aria-label="Retained SQL history"]')))
        _screen(driver, options, 'retained-history', screenshots)
        _input(driver, 'Query parameters (JSON object or array)', '{}')
        _show_data_output(driver, wait)

        source = ('CREATE TABLE ui_script_probe(value INTEGER); '
                  'INSERT INTO ui_script_probe VALUES (42);')
        _set_query(driver, wait, source)
        file_controls = [item for item in driver.find_elements(By.CSS_SELECTOR,
            '[role="region"][aria-label="Provider query workspace"] button')
            if (item.get_attribute('textContent') or '').strip() == 'Save source file']
        if file_controls:
            _click_workspace_button(driver, wait, 'Save source file')
            deadline = time.monotonic() + options.timeout
            while time.monotonic() < deadline:
                saved = [item for item in options.download_dir.glob('*.sql')
                         if item.is_file() and item.read_text(encoding='utf8') == source]
                if saved:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError('Shared DuckDB source file was not downloaded')
            _set_query(driver, wait, 'SELECT 0 AS placeholder')
            upload = driver.find_element(By.CSS_SELECTOR, 'input[type="file"][aria-label="Load source file"]')
            upload.send_keys(str(saved[0]))
            wait.until(lambda value: source in value.execute_script('return document.body.innerText') or
                value.execute_script('''return [...document.querySelectorAll('.cm-line')]
                  .map(line => line.textContent).join(String.fromCharCode(10))''') == source)
            _screen(driver, options, 'source-file-loaded', screenshots)

        _click_workspace_button(driver, wait, 'Check source')
        validation_text = wait.until(lambda value: next((item.get_attribute('textContent') or ''
            for item in value.find_elements(By.CSS_SELECTOR, '[role="status"]')
            if ('accepted by the reported parser' in (item.get_attribute('textContent') or '') or
                'Full grammar validation:' in (item.get_attribute('textContent') or ''))), None))
        native_parse_ui = ('accepted by the reported parser' in validation_text or
                           'confirmed by native validator' in validation_text)
        _screen(driver, options, 'native-source-checked', screenshots)
        _click_workspace_button(driver, wait, 'Preview script')
        wait.until(lambda value: any(item.is_displayed() and '"state": "ready"' in item.text
            for item in value.find_elements(By.CSS_SELECTOR, 'pre[aria-label="Script progress"]')))
        _screen(driver, options, 'script-reviewed', screenshots)
        _click_workspace_button(driver, wait, 'Run / resume retained script')
        wait.until(lambda value: any(item.is_displayed() and '"state": "complete"' in item.text
            for item in value.find_elements(By.CSS_SELECTOR, 'pre[aria-label="Script progress"]')))
        _screen(driver, options, 'script-complete', screenshots)
        return {
            'schema': 'cdeadmin.duckdb-editor-ui-gate.v1',
            'captured_at': datetime.now(timezone.utc).isoformat(),
            'engine_id': 'duckdb', 'reference_version': '1.5.2',
            'source_file_roundtrip': bool(file_controls),
            'native_parse_only_validation': native_parse_ui,
            'bound_parameter_result': True, 'owner_history_source_retained': True,
            'retained_script_completed': True, 'screenshots': screenshots,
            'passed': bool(file_controls) and native_parse_ui,
        }
    except Exception:
        options.output_root.joinpath('failure.html').write_text(driver.page_source,
            encoding='utf8')
        screenshot(driver, options.output_root / 'failure.png')
        raise
    finally:
        driver.quit()


def main(argv=None):
    options = arguments(argv)
    result = run(options)
    options.summary_output.parent.mkdir(parents=True, exist_ok=True)
    options.summary_output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': result['passed'], 'screenshot_count': len(result['screenshots'])}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
