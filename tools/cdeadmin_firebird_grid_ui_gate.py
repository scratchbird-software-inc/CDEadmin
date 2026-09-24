#!/usr/bin/env python3
##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Exercise Firebird row editing through the rendered provider grid."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support import expected_conditions as expected
from selenium.webdriver.support.ui import WebDriverWait


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cdeadmin_firebird_seeded_transaction_gate import (  # noqa: E402
    _load_profile,
    run as verify_and_clean_seeded_database,
)
from tools.cdeadmin_firebird_ui_form_gate import (  # noqa: E402
    MANIFEST_FIELDS,
    _relative_evidence_path,
    create_driver,
    evidence_variant,
    prepare_tree,
    screenshot,
)
from tools.cdeadmin_ui_evidence import (  # noqa: E402
    complete_endpoint_prompt,
    invoke_context_action,
    visible_named_control,
    wait_for_tree_item,
)


MARKER = '2147483001'


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:5052')
    parser.add_argument('--engine', default='Firebird')
    parser.add_argument('--server', default='localhost')
    parser.add_argument('--database', default='cdeadmin_demo.fdb')
    parser.add_argument(
        '--profiles', type=Path,
        default=ROOT / 'tools/reference_engine_demos/runtime/'
        'connection_profiles.json',
    )
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--summary-output', type=Path, required=True)
    parser.add_argument('--manifest-output', type=Path, required=True)
    parser.add_argument('--width', type=int, default=1600)
    parser.add_argument('--height', type=int, default=1000)
    parser.add_argument(
        '--theme', choices=('default', 'high-contrast'), default='default',
    )
    parser.add_argument(
        '--font-scale', type=int, choices=(100, 150, 200, 300), default=100,
    )
    parser.add_argument('--timeout', type=int, default=45)
    parser.add_argument('--browser-binary')
    return parser.parse_args()


def _button(wait, name):
    return wait.until(lambda driver: visible_named_control(driver, name))


def _choose_table(driver, wait, name):
    selector = _button(wait, 'Table')
    selector.click()
    option = wait.until(lambda value: next((
        item for item in value.find_elements(
            By.CSS_SELECTOR, '[role="option"]'
        ) if item.is_displayed() and item.text.strip().upper().endswith(name)
    ), None))
    option.click()


def _visible_inputs(driver, accessible_name):
    try:
        return [
            item for item in driver.find_elements(By.CSS_SELECTOR, 'input')
            if item.is_displayed() and (
                item.accessible_name == accessible_name or
                item.get_attribute('aria-label') == accessible_name
            )
        ]
    except StaleElementReferenceException:
        return []


def _row_for_input(control):
    return control.find_element(By.XPATH, 'ancestor::*[@role="row"]')


def _reveal_grid_column(driver, wait, index):
    """Exercise horizontal scrolling without disabling grid virtualization."""
    driver.execute_script("""
        const grid = document.querySelector(
          '[role="grid"][aria-label="Provider table or view rows"]');
        if (!grid) throw new Error('Provider grid is missing');
        const widths = getComputedStyle(grid).gridTemplateColumns
          .split(' ').map(Number.parseFloat);
        grid.scrollLeft = widths.slice(0, arguments[0] - 1)
          .reduce((sum, width) => sum + width, 0);
    """, index)
    wait.until(lambda browser: browser.find_elements(
        By.CSS_SELECTOR,
        '[role="grid"][aria-label="Provider table or view rows"] '
        f'[role="columnheader"][aria-colindex="{index}"]',
    ))


def _row_button(row, name):
    return next((
        item for item in row.find_elements(By.TAG_NAME, 'button')
        if item.is_displayed() and item.text.strip() == name
    ), None)


def _layout_evidence(driver, scale):
    observation = driver.execute_script("""
        const grid = document.querySelector(
          '[role="grid"][aria-label="Provider table or view rows"]');
        const bar = grid.closest('.dock-panel')?.querySelector('.dock-bar');
        const bounds = element => {
          const r = element.getBoundingClientRect();
          return {top: r.top, bottom: r.bottom, height: r.height};
        };
        return {
          column_widths: getComputedStyle(grid).gridTemplateColumns
            .split(' ').map(Number.parseFloat),
          viewport_width: grid.clientWidth, content_width: grid.scrollWidth,
          tab_bar: bar ? bounds(bar) : null,
          tabs: bar ? [...bar.querySelectorAll('.dock-tab')].map(tab => ({
            ...bounds(tab),
            content: bounds(tab.querySelector('.dock-tab-btn') ||
              tab.firstElementChild || tab)
          })) : []
        };
    """)
    widths = observation['column_widths']
    if len(widths) != 5 or any(
            not isinstance(width, (int, float)) or not math.isfinite(width) or
            width < minimum * scale / 100 - 1
            for width, minimum in zip(widths, [360, 360, 360, 360, 320])):
        raise RuntimeError('Grid columns compressed below editor minimums')
    bar = observation['tab_bar']
    if not bar or not observation['tabs'] or any(
            tab['top'] < bar['top'] - 1 or
            tab['bottom'] > bar['bottom'] + 1 or
            tab['content']['top'] < tab['top'] - 1 or
            tab['content']['bottom'] > tab['bottom'] + 1
            for tab in observation['tabs']):
        raise RuntimeError('Workspace tabs extend outside their tab bar')
    return observation


def _grid_control_evidence(driver):
    """Atomically inventory visible grid controls without their values."""
    return driver.execute_script(
        """
        const selector = [
          'button', 'input', 'textarea', '[role="button"]',
          '[role="combobox"]', '[role="checkbox"]', '[role="radio"]',
          '[role="tab"]', 'select',
        ].join(', ');
        return [...document.querySelectorAll(selector)]
          .filter((element) => {
            const style = window.getComputedStyle(element);
            return style.display !== 'none' && style.visibility !== 'hidden' &&
              element.getClientRects().length > 0;
          })
          .map((element, position) => ({
            position,
            tag: element.tagName.toLowerCase(),
            role: element.getAttribute('role') || '',
            accessible_name: element.getAttribute('aria-label') ||
              element.getAttribute('title') ||
              (element.tagName === 'BUTTON' ? element.innerText.trim() : ''),
            input_type: element.getAttribute('type') || '',
            enabled: !element.disabled,
            displayed: true,
          }));
        """
    )


def _shell_layout_evidence(driver, database):
    """Separate recoverable tree scrolling from inaccessible pane overflow."""
    observed = driver.execute_script("""
      const rect = element => {
        const r = element.getBoundingClientRect();
        return {left: r.left, right: r.right, width: r.width};
      };
      const inspector = document.querySelector(
        'aside[aria-label="Inspector"]');
      const empty = inspector?.querySelector('[data-cde-empty-state]');
      if (!empty) throw new Error('Inspector empty-state fixture is absent');
      const panel = empty.closest('[role="tabpanel"]');
      const label = [...document.querySelectorAll('.file-name')]
        .find(item => item.textContent.trim() === arguments[0]);
      if (!label) throw new Error('Registered database label is absent');
      const explorer = label.closest('aside');
      const scrolls = [];
      for (let node = label.parentElement; node && node !== explorer;
           node = node.parentElement) {
        if (node.scrollWidth > node.clientWidth) {
          const before = node.scrollLeft;
          node.scrollLeft = 0;
          scrolls.push({before, after: node.scrollLeft});
        }
      }
      return {inspector: rect(inspector), empty: rect(empty),
        message: rect(empty.querySelector('span')),
        panel_width: panel.clientWidth, panel_content_width: panel.scrollWidth,
        explorer: rect(explorer), database_label: rect(label), scrolls};
    """, database)
    pane = observed['inspector']
    if any(observed[key]['left'] < pane['left'] - 1 or
           observed[key]['right'] > pane['right'] + 1
           for key in ('empty', 'message')) or (
            observed['panel_content_width'] > observed['panel_width'] + 1):
        raise RuntimeError('Inspector empty-state overflows its pane')
    if not (observed['explorer']['left'] - 1 <=
            observed['database_label']['left'] <
            observed['explorer']['right']):
        raise RuntimeError('Navigator label start is unreachable by scrolling')
    return observed


def _capture(driver, options, state, records):
    viewport = f'{options.width}x{options.height}'
    variant = evidence_variant(options)
    path = options.output_root / f'{state}-{viewport}-{variant}.png'
    records[state] = {
        'path': str(path),
        'sha256': screenshot(driver, path),
    }


def _inspector_keyboard_evidence(driver, wait, capture):
    inspector = driver.find_element(
        By.CSS_SELECTOR, 'aside[aria-label="Inspector"]')
    tabs = inspector.find_elements(By.CSS_SELECTOR, '[role="tab"]')
    if len(tabs) < 2:
        raise RuntimeError('Inspector tab fixture is incomplete')

    def selected(index):
        def ready(browser):
            current = inspector.find_elements(By.CSS_SELECTOR, '[role="tab"]')
            item = current[index]
            panel = inspector.find_element(
                By.CSS_SELECTOR, '[role="tabpanel"]')
            return (item.get_attribute('aria-selected') == 'true' and
                    browser.switch_to.active_element == item and
                    panel.get_attribute('aria-labelledby') ==
                    item.get_attribute('id'))
        wait.until(ready)

    tabs[0].send_keys(Keys.HOME)
    selected(0)
    pages = [tabs[0].text]
    for index in range(1, len(tabs)):
        driver.switch_to.active_element.send_keys(Keys.ARROW_RIGHT)
        selected(index)
        pages.append(driver.switch_to.active_element.text)
        capture(f'inspector-keyboard-page-{index}')
    driver.switch_to.active_element.send_keys(Keys.HOME)
    selected(0)
    driver.switch_to.active_element.send_keys(Keys.END)
    selected(len(tabs) - 1)
    driver.switch_to.active_element.send_keys(Keys.ARROW_RIGHT)
    selected(0)
    driver.switch_to.active_element.send_keys(Keys.ARROW_LEFT)
    selected(len(tabs) - 1)
    driver.switch_to.active_element.send_keys(Keys.HOME)
    selected(0)
    driver.switch_to.active_element.send_keys(Keys.TAB)
    panel = inspector.find_element(By.CSS_SELECTOR, '[role="tabpanel"]')
    wait.until(lambda browser: browser.switch_to.active_element == panel)
    panel.send_keys(Keys.END)
    wait.until(lambda browser: browser.execute_script(
        'return arguments[0].scrollTop >= arguments[0].scrollHeight - '
        'arguments[0].clientHeight - 1', panel))
    bottom = driver.execute_script("""
      const panel = arguments[0];
      const message = panel.querySelector('[data-cde-empty-state] span');
      if (!message) throw new Error('Properties empty-state is absent');
      return {scroll_top: panel.scrollTop, scroll_height: panel.scrollHeight,
        client_height: panel.clientHeight,
        message_bottom: message.getBoundingClientRect().bottom,
        panel_bottom: panel.getBoundingClientRect().bottom};
    """, panel)
    if bottom['message_bottom'] > bottom['panel_bottom'] + 1:
        raise RuntimeError(
            'Inspector message bottom is not keyboard reachable')
    capture('inspector-keyboard-bottom')
    panel.send_keys(Keys.HOME)
    wait.until(lambda browser: browser.execute_script(
        'return arguments[0].scrollTop <= 1', panel))
    capture('inspector-keyboard-top')
    return {'pages': pages, 'arrow_wrap_home_end': True,
            'tab_enters_panel': True, 'home_returns_to_top': True,
            'bottom': bottom}


def _write_records(options, evidence):
    manifest = options.manifest_output
    existing = []
    if manifest.exists():
        with manifest.open(newline='', encoding='utf-8') as source:
            existing = list(csv.DictReader(source))
    keys = {
        (row['interface_id'], row['command_id'], row['state'],
         row['screenshot_path'])
        for row in existing
    }
    rows = []
    viewport = f'{options.width}x{options.height}'
    for state, value in evidence['screenshots'].items():
        subject = next((item for item in evidence.get(
            'populated_inspector_checks', [])
            if state.startswith('object-' + item['name'] + '-')), None)
        command_id = '' if subject else 'database.firebird.data'
        form_id = ('provider_object_properties' if subject else
                   'firebird_structured_data_grid')
        screenshot_path = Path(value['path'])
        occurrence_path = screenshot_path.with_suffix('.json')
        occurrence = {
            'schema': 'cdeadmin.ui-form-evidence.v1',
            'captured_at': evidence['captured_at'],
            'engine_id': 'firebird',
            'interface_id': 'firebird-native',
            'reference_version': '5.0.4',
            'server_label': options.server,
            'database_label': options.database,
            'command_id': command_id,
            'form_id': form_id,
            'state': state,
            'viewport': viewport,
            'theme': options.theme,
            'locale': 'en-US',
            'controls': evidence['controls'][state],
            'screenshot': value,
            'control_values_recorded': False,
            'credential_values_exported': False,
            'transaction_proof_id': (
                'firebird-seeded-object-transactions'
            ),
        }
        occurrence_path.write_text(
            json.dumps(occurrence, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        row = {
            'interface_id': 'firebird-native',
            'reference_version': '5.0.4',
            'profile_id': 'firebird-native',
            'server_id': options.server,
            'database_target_id': options.database,
            'command_id': command_id,
            'form_id': form_id,
            'resource_kind': subject['kind'] if subject else 'table',
            'resource_id': subject['name'] if subject else 'CUSTOMERS',
            'state': state,
            'viewport': viewport,
            'device_scale': '1',
            'font_scale': f'{options.font_scale}%',
            'theme': options.theme,
            'locale': 'en-US',
            'screenshot_path': _relative_evidence_path(
                screenshot_path, manifest
            ),
            'occurrence_path': _relative_evidence_path(
                occurrence_path, manifest
            ),
            'interaction_result': (
                f'Firebird provider grid state {state}; '
                f'sha256={value["sha256"]}'
            ),
            'transaction_proof_id': (
                'firebird-seeded-object-transactions'
            ),
            'captured_at_utc': evidence['captured_at'],
        }
        key = (
            row['interface_id'], row['command_id'], row['state'],
            row['screenshot_path'],
        )
        if key not in keys:
            rows.append(row)
            keys.add(key)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open('w', newline='', encoding='utf-8') as target:
        writer = csv.DictWriter(target, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(existing + rows)


def run(options, password):
    driver = create_driver(options)
    # Commit/rollback replaces rendered row controls. Retry observations of
    # detached elements, never the mutation button clicks themselves.
    wait = WebDriverWait(
        driver, options.timeout,
        ignored_exceptions=(StaleElementReferenceException,),
    )
    screenshots = {}
    controls = {}

    def capture(state):
        _capture(driver, options, state, screenshots)
        controls[state] = _grid_control_evidence(driver)

    try:
        prepare_tree(driver, wait, options, password)
        database = wait_for_tree_item(wait, options.database)
        invoke_context_action(
            wait, driver, database,
            ['Database workspace',
             'Browse and edit Firebird table data...'],
            password, endpoint_prompt_timeout=1,
        )
        complete_endpoint_prompt(driver, password, timeout=1)
        _button(wait, 'Load rows')
        _choose_table(driver, wait, 'CUSTOMERS')
        capture('initial')
        load_button = _button(wait, 'Load rows')
        load_button.click()
        wait.until(lambda _value: load_button.is_enabled())
        if not _visible_inputs(driver, 'NAME value'):
            capture('load-response-error')
            alerts = [
                item.text.strip()
                for item in driver.find_elements(
                    By.CSS_SELECTOR, '[role="alert"]'
                )
                if item.is_displayed() and item.text.strip()
            ]
            visible_input_labels = [
                {
                    'aria_label': item.get_attribute('aria-label'),
                    'accessible_name': item.accessible_name,
                    'value': item.get_attribute('value'),
                }
                for item in driver.find_elements(By.CSS_SELECTOR, 'input')
                if item.is_displayed()
            ]
            raise RuntimeError(
                'Firebird row controls were not rendered after Load rows. '
                f'Visible alerts: {alerts or ["none"]}. '
                f'Visible inputs: {visible_input_labels}'
            )
        capture('loaded')
        layout = _layout_evidence(driver, options.font_scale)
        shell_layout = _shell_layout_evidence(driver, options.database)
        capture('shell-layout')
        inspector_keyboard = _inspector_keyboard_evidence(
            driver, wait, capture)

        _reveal_grid_column(driver, wait, 2)
        name = _visible_inputs(driver, 'NAME value')[0]
        original_name = name.get_attribute('value')
        name.send_keys(Keys.CONTROL, 'a')
        name.send_keys('CDEadmin rollback probe')
        edited_row = _row_for_input(name)
        _reveal_grid_column(driver, wait, 5)
        save = wait.until(lambda _driver: _row_button(edited_row, 'Save'))
        if save is None:
            raise RuntimeError('Firebird row Save control is unavailable')
        save.click()
        wait.until(expected.visibility_of_element_located((
            By.CSS_SELECTOR,
            '[aria-label="Staged provider grid changes"]',
        )))
        capture('update-staged')
        _button(wait, 'Rollback changes').click()
        _reveal_grid_column(driver, wait, 2)
        wait.until(expected.invisibility_of_element_located((
            By.CSS_SELECTOR,
            '[aria-label="Staged provider grid changes"]',
        )))
        restored = wait.until(lambda value: any(
            item.get_attribute('value') == original_name
            for item in _visible_inputs(value, 'NAME value')
        ))
        if not restored:
            raise RuntimeError('Firebird grid rollback did not restore row')
        capture('update-rolled-back')

        new_values = {
            'CUSTOMER_ID new value': MARKER,
            'NAME new value': 'CDEadmin browser transaction row',
            'CITY new value': 'Toronto',
            'REGION new value': 'QA',
        }
        new_control = None
        for index, (label, value) in enumerate(new_values.items(), 1):
            _reveal_grid_column(driver, wait, index)
            candidates = wait.until(lambda browser: _visible_inputs(
                browser, label))
            if len(candidates) != 1:
                raise RuntimeError(f'Firebird grid field {label} is missing')
            candidates[0].send_keys(value)
            new_control = candidates[0]
        insert_row = _row_for_input(new_control)
        _reveal_grid_column(driver, wait, 5)
        insert = wait.until(lambda _driver: _row_button(
            insert_row, 'Insert row'))
        if insert is None:
            raise RuntimeError('Firebird Insert row control is unavailable')
        insert.click()
        wait.until(expected.visibility_of_element_located((
            By.CSS_SELECTOR,
            '[aria-label="Staged provider grid changes"]',
        )))
        capture('insert-staged')
        _button(wait, 'Commit changes').click()
        _reveal_grid_column(driver, wait, 1)
        wait.until(lambda value: any(
            item.get_attribute('value') == MARKER
            for item in _visible_inputs(value, 'CUSTOMER_ID value')
        ))
        capture('insert-committed')

        marker_control = next(
            item for item in _visible_inputs(driver, 'CUSTOMER_ID value')
            if item.get_attribute('value') == MARKER
        )
        marker_row = _row_for_input(marker_control)
        _reveal_grid_column(driver, wait, 5)
        delete = wait.until(lambda _driver: _row_button(marker_row, 'Delete'))
        if delete is None:
            raise RuntimeError('Firebird Delete control is unavailable')
        delete.click()
        wait.until(lambda _value: _row_button(
            marker_row, 'Confirm delete'
        ) is not None)
        capture('safe-delete-confirmation')
        _row_button(marker_row, 'Confirm delete').click()
        wait.until(expected.visibility_of_element_located((
            By.CSS_SELECTOR,
            '[aria-label="Staged provider grid changes"]',
        )))
        capture('delete-staged')
        _button(wait, 'Commit changes').click()
        _reveal_grid_column(driver, wait, 1)
        wait.until(lambda value: not any(
            item.get_attribute('value') == MARKER
            for item in _visible_inputs(value, 'CUSTOMER_ID value')
        ))
        capture('delete-committed-clean')
        close_session = _button(wait, 'Close data session')
        close_session.click()
        wait.until(lambda value: (
            (control := visible_named_control(
                value, 'Close data session'
            )) is not None and not control.is_enabled()
        ))
        capture('session-closed')
        from tools.cdeadmin_firebird_populated_inspector import verify
        populated_inspector = verify(driver, wait, options, capture)
        return {
            'schema': 'cdeadmin.firebird-grid-ui-gate.v1',
            'captured_at': datetime.now(timezone.utc).isoformat(),
            'engine_id': 'firebird',
            'interface_id': 'firebird-native',
            'reference_version': '5.0.4',
            'database': options.database,
            'table': 'CUSTOMERS',
            'rollback_restored_original': True,
            'commit_visibility_observed': True,
            'safe_delete_confirmation_observed': True,
            'committed_cleanup_observed': True,
            'provider_session_closed': True,
            'provider_finality_authority': True,
            'common_finality_interpreted': False,
            'credential_values_exported': False,
            'screenshots': screenshots,
            'controls': controls,
            'layout_checks': layout,
            'shell_layout_checks': shell_layout,
            'inspector_keyboard_checks': inspector_keyboard,
            'populated_inspector_checks': populated_inspector,
            'passed': True,
        }
    finally:
        try:
            rollback = next((
                item for item in driver.find_elements(By.TAG_NAME, 'button')
                if item.is_displayed() and item.is_enabled() and
                item.text.strip() == 'Rollback changes'
            ), None)
            if rollback is not None:
                rollback.click()
                WebDriverWait(driver, 10).until(
                    expected.invisibility_of_element_located((
                        By.CSS_SELECTOR,
                        '[aria-label="Staged provider grid changes"]',
                    ))
                )
        except Exception:
            # The independent provider gate below still verifies and removes
            # the fixed disposable marker after the browser has been closed.
            pass
        driver.quit()


def main():
    options = arguments()
    profile = _load_profile(options.profiles)
    password = str(profile.get('password', ''))
    if not password:
        raise SystemExit('Firebird demo credential is unavailable')
    try:
        evidence = run(options, password)
    finally:
        # This provider-driven gate also removes the fixed disposable marker
        # if browser execution stopped after its commit but before UI cleanup.
        independent = verify_and_clean_seeded_database(options.profiles)
        password = ''
    evidence['independent_transaction_verification'] = independent
    options.summary_output.parent.mkdir(parents=True, exist_ok=True)
    options.summary_output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    _write_records(options, evidence)
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
