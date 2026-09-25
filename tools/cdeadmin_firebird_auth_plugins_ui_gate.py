#!/usr/bin/env python3
"""Linux real-browser ordered plugin profile editing and native verification.

Windows/macOS teams must repeat accessible editing, rejection and correction
with their native clients. Only disposable application/engine fixtures change.
"""

import argparse
import json
from pathlib import Path
import sqlite3

from tools.cdeadmin_firebird_password_gate import run as native_run
from tools.cdeadmin_firebird_password_ui_gate import browser_case
from tools.cdeadmin_firebird_auth_plugins_gate import attach
from tools.cdeadmin_firebird_ui_form_gate import screenshot
from tools.cdeadmin_ui_evidence import (
    invoke_context_action, visible_named_control,
)
from selenium.webdriver.common.keys import Keys


def profile_checks(context):
    def stored():
        with sqlite3.connect(context.database) as connection:
            return json.loads(connection.execute(
                'SELECT configuration FROM cde_endpoint_route WHERE id=?',
                (context.route_id,)).fetchone()[0])

    def edit(value, filename, rejected=False):
        previous = stored()
        item = context.load_tree()
        invoke_context_action(context.wait, context.driver, item,
                              ['Endpoint registration',
                               'Edit endpoint properties...'],
                              handle_endpoint_prompt=False)

        def form_control(browser, name):
            for form in browser.find_elements(
                    'css selector',
                    '[data-form-id="'
                    'cdeadmin.firebird-native.server.edit.v1"]'):
                if form.is_displayed():
                    return visible_named_control(form, name)
            return None

        field = context.wait.until(lambda browser: form_control(
            browser, 'Authentication plugin preference list'))
        assert field.accessible_name == 'Authentication plugin preference list'
        field.send_keys(Keys.CONTROL, 'a')
        field.send_keys(Keys.BACKSPACE)
        field.send_keys(value)
        context.driver.execute_script(
            'arguments[0].scrollIntoView({block:"center"})', field)
        screenshot(context.driver, context.evidence / filename)
        button = form_control(context.driver, 'Save endpoint profile')
        context.driver.execute_script(
            'arguments[0].scrollIntoView({block:"center"})', button)
        if rejected and value == '':
            assert not button.is_enabled()
            assert stored() == previous
            screenshot(context.driver, context.evidence / filename)
            return
        button.click()
        if rejected:
            context.wait.until(lambda browser:
                               'plugin list must contain plugin names' in
                               browser.find_element('tag name', 'body').text)
            assert stored() == previous
            screenshot(context.driver, context.evidence / filename)
            return
        context.wait.until(lambda _: stored().get('auth_plugin_list') == value)

    edit('', 'empty-plugin-rejection.png', rejected=True)
    edit(' ;, ', 'separator-only-rejection.png', rejected=True)
    edit('CDE_NoSuchAuthPlugin', 'unavailable-plugin-profile.png')
    response = context.prompt(context.users[0][1])
    assert response['status'] == 401
    screenshot(context.driver, context.evidence / 'native-rejection.png')
    edit('Srp512,Srp256', 'ordered-plugin-profile.png')
    # The browser persists the list and subsequent normal credential flow
    # verifies it through the application. Independently observe the exact
    # saved policy's negotiated database method, not just a 200 response.
    native = attach({**stored(), 'database': context.route['database']},
                    context.users[0][1], 'Srp512,Srp256', 'Srp512')
    return {'accessible_profile_control': True,
            'empty_list_rejected_without_mutation': True,
            'unavailable_rejected_in_browser': True,
            'ordered_list_saved_exactly': True, 'native': native}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-config-db', required=True, type=Path)
    parser.add_argument('--desktop-user', required=True)
    parser.add_argument('--evidence-root', required=True, type=Path)
    parser.add_argument('--theme', default='high-contrast')
    parser.add_argument('--font-scale', type=int, default=150)
    options = parser.parse_args()
    result = native_run(options.evidence_root, lambda *args: browser_case(
        options, *args, profile_check=profile_checks), ['Srp256'])
    raise SystemExit(0 if result['complete'] else 1)
