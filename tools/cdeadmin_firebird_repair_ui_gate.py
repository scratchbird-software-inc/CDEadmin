#!/usr/bin/env python3
"""Exercise gfix task controls on an explicitly owned healthy database."""

import json
import os
import re

from cdeadmin_firebird_role_ui_gate import (
    arguments, forms, firebird, _route_arguments, create_driver,
    close_workspace, plan_preview, WebDriverWait, visible_named_control,
)
from cdeadmin_firebird_query_ui_gate import _load_profile
from cdeadmin_firebird_ui_form_gate import (
    click_unobscured, screenshot_form_pages, screenshot, fill_form_values,
    MENU_GROUP_LABELS, invoke_context_action, accessibility_observation,
    open_workspace, PREVIEW_VALUES,
)
from cdeadmin_firebird_logical_volumes_gate import docker, OWNER
from pgadmin.cdeadmin.providers.firebird import repair
from pgadmin.cdeadmin.providers.relational_admin import (
    _FIREBIRD_SERVICE_OPERATIONS,
)


def service_role_forms(browser, wait, options, route, descriptor, checks):
    """All service forms: native roles, preview and keyboard/layout evidence.

    Linux browser qualification; Windows/macOS teams must repeat these controls
    and their native client transport. Preview never grants native privileges.
    """
    for operation_id in sorted(_FIREBIRD_SERVICE_OPERATIONS):
        operation = {**next(item for item in descriptor['operations']
                            if item['operation_id'] == operation_id),
                     'resource_kind': 'database'}
        item = forms.wait_for_tree_item(wait, options.database)
        forms._context_click_visible_label(browser, wait, item)
        command = browser.execute_script('''
            const tree = window.pgAdmin.Browser.tree;
            return (tree.itemData(tree.selected()).cde_context_actions || [])
              .find(item => item.command_id === arguments[0] && item.enabled);
        ''', 'database.firebird.' + operation_id)
        assert command
        forms.ActionChains(browser).send_keys(forms.Keys.ESCAPE).perform()
        open_workspace(browser, wait, options, route['password'], command,
                       operation)
        controls = forms.assert_form_controls(
            wait, operation['form']['fields'])
        accessibility = accessibility_observation(
            browser, wait, operation, controls)
        fill_form_values(browser, wait, operation['form']['fields'], {
            **PREVIEW_VALUES.get(operation_id, {}),
            'SQL role': 'ROLE WITH SPACE'})
        validate = visible_named_control(browser, 'Validate and preview')
        click_unobscured(browser, wait, validate)
        wait.until(lambda driver: 'whitespace or control characters' in
                   driver.find_element('tag name', 'body').text)
        assert not browser.find_elements(
            'css selector', '[aria-label="Provider plan preview"]')
        previews = []
        for role in ('', 'CDE_OWNED_TASK_ROLE', ''):
            values = {**PREVIEW_VALUES.get(operation_id, {}), 'SQL role': role}
            plan = plan_preview(browser, wait, operation, values)
            auth = plan['command_preview']['service_authentication_requested']
            assert auth['requested_role'] == (role or route.get('role'))
            assert auth['role_source'] == ('task' if role else 'connection')
            assert auth['authorization_verified'] is False
            previews.append(auth)
        pages = screenshot_form_pages(
            browser, options.output_root / ('roles-' + operation_id))
        close_workspace(browser, wait)
        checks.append({'operation_id': operation_id, 'previews': previews,
                       'unsafe_role_rejected': True,
                       'accessibility': accessibility, 'screenshots': pages})
    return checks


def run(options, profiles):
    route = _load_profile(profiles)
    container = route.get('owned_container_id', '')
    database = ('/var/lib/firebird/data/owned_repair_browser_' +
                str(options.font_scale) + '.fdb')
    if (route.get('fixture_kind') != 'firebird-repair-qualification' or
            route['host'] != '127.0.0.1' or route['database'] != database or
            options.database_path != database or
            not re.fullmatch('[0-9a-f]{64}', container)):
        raise ValueError('Repair tests require an owned server')
    if docker('inspect', '--format',
              '{{index .Config.Labels "cdeadmin-owned-gate"}}',
              container).decode().strip() != OWNER:
        raise ValueError('Owned repair server identity differs')
    if docker('port', container, '3050/tcp').decode().strip() != (
            '127.0.0.1:' + str(route['port'])):
        raise ValueError('Owned repair server port differs')
    firebird.driver_config.fb_client_library.value = os.environ[
        'CDEADMIN_FIREBIRD_CLIENT_LIBRARY']
    browser = None
    result = {'passed': False, 'checks': [], 'failures': [],
              'invalid_forms': [],
              'credential_values_exported': False,
              'damaged_database_recovery_qualified': False}
    try:
        browser = create_driver(options)
        browser.set_script_timeout(120)
        wait = WebDriverWait(browser, options.timeout)
        forms._prepare_tree(browser, wait, options)
        probe = forms._workspace_probe(browser, ['database'], False)
        descriptor = next(item for item in probe['catalog']['objects']
                          if item['resource_kind'] == 'database')
        operation = {**next(item for item in descriptor['operations']
                            if item['operation_id'] == 'repair_database'),
                     'resource_kind': 'database'}
        if route.get('role'):
            result['service_role_forms'] = []
            service_role_forms(browser, wait, options, route, descriptor,
                               result['service_role_forms'])
        browser.execute_script('''
            window.__ownedRepairDispatches = 0;
            const send = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.send = function(body) {
              try {
                if (JSON.parse(body)?.action === 'visual_admin_apply')
                  window.__ownedRepairDispatches++;
              } catch (_) { /* Count only exact JSON apply actions. */ }
              return send.apply(this, arguments);
            };
        ''')
        cases = [(action, modifiers, None, False) for action, modifiers in (
                ('VALIDATE_DB', []),
                ('VALIDATE_DB', ['FULL', 'CHECK_DB']),
                ('VALIDATE_DB', ['IGNORE_CHECKSUM']),
                ('MEND_DB', ['CHECK_DB']),
                ('CORRUPTION_CHECK', []), ('REPAIR', []),
                ('KILL_SHADOWS', []), ('ICU', []), ('UPGRADE_DB', []))]
        cases.extend(('ICU', [], count, False) for count in (0, 2, 32767))
        cases.extend((action, [], None, True) for action in repair.ACTIONS)
        cases.append(('ICU', [], 2, True))
        for action, modifiers, workers, no_linger in cases:
            item = forms.wait_for_tree_item(wait, options.database)
            forms._context_click_visible_label(browser, wait, item)
            command = wait.until(lambda driver: driver.execute_script('''
                const tree = window.pgAdmin.Browser.tree;
                return (tree.itemData(tree.selected())
                  .cde_context_actions || []).find(item =>
                  item.command_id === 'database.firebird.repair_database' &&
                  item.enabled);
            '''))
            assert command['arguments']['database_target_id'] == (
                probe['database_target_id'])
            forms.ActionChains(browser).send_keys(forms.Keys.ESCAPE).perform()
            item = forms.wait_for_tree_item(wait, options.database)
            invoke_context_action(wait, browser, item, [
                MENU_GROUP_LABELS[command['menu_group']], command['label']],
                route['password'], endpoint_prompt_timeout=1)
            if command['requires_confirmation']:
                button = wait.until(lambda driver: visible_named_control(
                    driver, 'Continue'))
                click_unobscured(browser, wait, button)
            forms._wait_for_operation(wait, operation)
            fields = operation['form']['fields']
            controls = forms.assert_form_controls(wait, fields)
            accessibility = accessibility_observation(
                browser, wait, operation, controls)
            invalid_cases = (
                ('UPGRADE_DB', 'does not accept validation modifiers'),
                ('ICU', 'ICU does not apply checksum-ignore'),
                ('KILL_SHADOWS', 'KILL_SHADOWS does not apply checksum-ignore')
            ) if not result['checks'] else ()
            for invalid_action, expected_error in invalid_cases:
                fill_form_values(browser, wait, fields, {
                    'Repair action': invalid_action,
                    'Native validation modifiers': ['IGNORE_CHECKSUM']})
                click_unobscured(browser, wait, visible_named_control(
                    browser, 'Validate and preview'))
                rejection = wait.until(lambda driver: next((
                    item for item in driver.find_elements(
                        'css selector', '[role="alert"]')
                    if expected_error in item.text),
                    None))
                browser.execute_script(
                    'arguments[0].scrollIntoView({block:"center"});',
                    rejection)
                screenshot_form_pages(
                    browser, options.output_root / (
                        'invalid-' + invalid_action))
                assert not browser.find_elements(
                    'css selector', '[aria-label="Provider plan preview"]')
                result['invalid_forms'].append(invalid_action)
            worker_errors = (
                ('VALIDATE_DB', 1, 'require the ICU action'),
                ('ICU', -1, 'below its minimum'),
                ('ICU', 32768, 'exceeds its maximum'),
            ) if not result['checks'] else ()
            for invalid_action, count, expected_error in worker_errors:
                fill_form_values(browser, wait, fields, {
                    'Repair action': invalid_action,
                    'Native validation modifiers': [],
                    'ICU parallel workers requested': count})
                click_unobscured(browser, wait, visible_named_control(
                    browser, 'Validate and preview'))
                rejection = wait.until(lambda driver: next((
                    item for item in driver.find_elements(
                        'css selector', '[role="alert"]')
                    if expected_error in item.text), None))
                browser.execute_script(
                    'arguments[0].scrollIntoView({block:"center"});',
                    rejection)
                screenshot_form_pages(browser, options.output_root / (
                    'invalid-workers-' + invalid_action + '-' + str(count)))
                assert not browser.find_elements(
                    'css selector', '[aria-label="Provider plan preview"]')
                result['invalid_forms'].append(
                    'workers-' + invalid_action + '-' + str(count))
            task_role = ('CDE_OWNED_TASK_ROLE'
                         if route.get('role') and len(result['checks']) == 1
                         else '')
            values = {
                'Repair action': action,
                'Native validation modifiers': modifiers,
                'ICU parallel workers requested': (
                    workers if workers is not None else ''),
                'Do not linger after this maintenance task': no_linger,
                'SQL role': task_role}
            plan = plan_preview(browser, wait, operation, values)
            selection = repair.selection(database, {
                'repair_action': action, 'repair_modifiers': modifiers,
                'role': task_role, 'parallel_workers': workers,
                'no_linger': no_linger},
                route.get('role'))
            assert plan['command_preview']['repair_selection'] == selection
            authentication = plan['command_preview'][
                'service_authentication_requested']
            assert authentication['requested_role'] == (
                task_role or route.get('role') or None)
            assert authentication['role_source'] == (
                'task' if task_role else
                'connection' if route.get('role') else 'none')
            assert authentication['authorization_verified'] is False
            assert authentication['role_transport'] == 'service_attachment'
            assert browser.execute_script(
                'return window.__ownedRepairDispatches') == len(
                    result['checks'])
            prefix = str(len(result['checks'])) + '-' + action
            pages = screenshot_form_pages(
                browser, options.output_root / (prefix + '-plan'))
            confirmation = visible_named_control(
                browser, 'I confirm this provider-planned operation.')
            assert confirmation is not None
            if not confirmation.is_selected():
                click_unobscured(browser, wait, confirmation)
            button = wait.until(lambda driver: visible_named_control(
                driver, 'Apply provider plan'))
            wait.until(lambda _driver: button.is_enabled())
            click_unobscured(browser, wait, button)
            wait.until(lambda driver: any(item.is_displayed()
                       for item in driver.find_elements(
                           'css selector',
                           '[aria-label="Firebird service result"]')))
            observed = browser.find_element(
                'css selector', '[aria-label="Firebird service result"]')
            assert 'Requested service role' in observed.text
            assert (authentication['requested_role'] or
                    'None requested') in observed.text
            assert 'Service authentication database' in observed.text
            assert 'not a grant of privileges' in observed.text
            connection = firebird.connect(
                password=route['password'],
                **_route_arguments(route, firebird))
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT ID, NOTE FROM REPAIR_MARKER')
                    assert cursor.fetchall() == [(1, 'preserve healthy data')]
            finally:
                connection.close()
            result_pages = screenshot_form_pages(
                browser, options.output_root / (prefix + '-result'))
            assert browser.execute_script(
                'return window.__ownedRepairDispatches') == len(
                    result['checks']) + 1
            result['checks'].append({
                'reviewed_selection': selection, 'apply_dispatch_count': 1,
                'service_authentication_requested': authentication,
                'service_identity_result_visible': True,
                'healthy_rows_preserved': True,
                'database_popup_verified': True,
                'accessibility': accessibility,
                'plan_screenshots': pages, 'result_screenshots': result_pages})
            wait.until(lambda driver: (button := visible_named_control(
                driver, 'Validate and preview')) is not None and
                button.is_enabled())
            close_workspace(browser, wait)
        result['passed'] = (len(result['checks']) == len(cases) and
                            len(result['invalid_forms']) == 6)
    except Exception as error:
        result['failures'].append({'type': type(error).__name__})
        if browser is not None:
            screenshot(browser, options.output_root / 'failure.png')
        raise
    finally:
        if browser is not None:
            forms._quit_driver(browser)
        options.summary_output.parent.mkdir(parents=True, exist_ok=True)
        options.summary_output.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    options, profiles = arguments()
    outcome = run(options, profiles)
    print(json.dumps(outcome))
    raise SystemExit(0 if outcome['passed'] else 1)
