#!/usr/bin/env python3
"""FM-FB02-004 Linux browser security-context selection in owned fixtures.

Windows/macOS must repeat path, Unicode, environment and browser checks using
their native clients. No changes to demo engines or original user profiles.
"""

import argparse
import json
from pathlib import Path
import sqlite3

from tools.cdeadmin_firebird_service_security_gate import run
from tools.cdeadmin_firebird_password_ui_gate import browser_case
from tools.cdeadmin_firebird_ui_form_gate import screenshot
from tools.cdeadmin_ui_evidence import (
    invoke_context_action, visible_named_control,
)
from selenium.webdriver.common.keys import Keys


def profile_check(context, alias):
    failed = context.prompt(context.users[0][1])
    assert failed['status'] == 401
    screenshot(context.driver,
               context.evidence / 'default-security-denial.png')
    item = context.load_tree()
    invoke_context_action(context.wait, context.driver, item,
                          ['Endpoint registration',
                           'Edit endpoint properties...'],
                          handle_endpoint_prompt=False)
    form = context.wait.until(lambda browser: browser.find_element(
        'css selector', '[data-form-id="'
        'cdeadmin.firebird-native.server.edit.v1"]'))
    field = visible_named_control(
        form, 'Service authentication database context')
    assert field.accessible_name == 'Service authentication database context'
    field.send_keys(Keys.CONTROL, 'a')
    field.send_keys(alias)
    context.driver.execute_script(
        'arguments[0].scrollIntoView({block:"center"})', field)
    screenshot(context.driver, context.evidence / 'selected-context.png')
    button = visible_named_control(form, 'Save endpoint profile')
    context.driver.execute_script(
        'arguments[0].scrollIntoView({block:"center"})', button)
    button.click()

    def saved(_browser):
        with sqlite3.connect(context.database) as connection:
            route = json.loads(connection.execute(
                'SELECT configuration FROM cde_endpoint_route WHERE id=?',
                (context.route_id,)).fetchone()[0])
        return (route.get('service_expected_database') == alias and
                not route.get('database'))

    context.wait.until(saved)
    return {'default_context_rejected_alternate_password': True,
            'accessible_context_field': True,
            'saved_context_separate_from_database_target': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-config-db', required=True, type=Path)
    parser.add_argument('--desktop-user', required=True)
    parser.add_argument('--evidence-root', required=True, type=Path)
    parser.add_argument('--theme', default='high-contrast')
    parser.add_argument('--font-scale', type=int, default=150)
    options = parser.parse_args()
    options.evidence_root.mkdir(parents=True, exist_ok=False)

    def browser(route, plugin, users, alias):
        return browser_case(options, route, plugin, users,
                            options.evidence_root / 'browser',
                            profile_check=lambda context:
                            profile_check(context, alias))

    result = run('firebirdsql/firebird:5.0.4', browser=browser)
    (options.evidence_root / 'summary.json').write_text(
        json.dumps(result, indent=2) + '\n')
    raise SystemExit(0 if result['complete'] else 1)
