#!/usr/bin/env python3
"""Linux unsupported-trust UI boundary, not Windows SSPI qualification.

Windows team: test real SSPI principals, trust failures, app-service identity,
creation, Services API and browser flows. macOS team: repeat rejection checks.
An owned Linux fixture proves password authentication still works after a
rejected trusted selection, not that Windows authentication works on Linux.
"""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from tools.cdeadmin_firebird_password_gate import run as native_run
from tools.cdeadmin_firebird_password_ui_gate import browser_case
from tools.cdeadmin_firebird_auth_plugins_gate import attach
from tools.cdeadmin_firebird_ui_form_gate import screenshot
from tools.cdeadmin_ui_evidence import (
    invoke_context_action, visible_named_control,
)


def native_boundary(route, users):
    if sys.platform != 'linux':
        raise RuntimeError('This evidence gate requires Linux')
    target = {**route, 'user': users[0][0]}
    return {
        'win_sspi_only_native_rejected': attach(
            target, users[0][1], 'Win_Sspi', None, creation=True),
        'mixed_list_native': attach(
            target, users[0][1], 'Win_Sspi,Srp256', 'Srp256', creation=True),
    }


def check_platform(context):
    if sys.platform != 'linux':
        raise RuntimeError('This evidence gate requires Linux')

    def stored():
        with sqlite3.connect(context.database) as connection:
            return json.loads(connection.execute(
                'SELECT configuration FROM cde_endpoint_route WHERE id=?',
                (context.route_id,)).fetchone()[0])

    previous = stored()
    item = context.load_tree()
    invoke_context_action(context.wait, context.driver, item,
                          ['Endpoint registration',
                           'Edit endpoint properties...'],
                          handle_endpoint_prompt=False)
    form = context.wait.until(lambda browser: browser.find_element(
        'css selector', '[data-form-id="'
        'cdeadmin.firebird-native.server.edit.v1"]'))
    checkbox = visible_named_control(form, 'Use trusted authentication')
    assert checkbox is not None
    checkbox.click()
    button = visible_named_control(form, 'Save endpoint profile')
    context.driver.execute_script(
        'arguments[0].scrollIntoView({block:"center"})', button)
    button.click()
    context.wait.until(lambda browser: 'host to run Windows' in
                       browser.find_element('tag name', 'body').text)
    assert stored() == previous
    screenshot(context.driver, context.evidence / 'trusted-linux-rejected.png')
    checkbox.click()
    button.click()
    context.wait.until(lambda browser: 'Endpoint profile saved' in
                       browser.find_element('tag name', 'body').text)
    assert not stored().get('trusted_auth')
    screenshot(context.driver,
               context.evidence / 'password-policy-restored.png')
    # A mixed native list may legitimately negotiate SRP on Linux. Do not
    # confuse this with trusted_auth=True or forbid Windows names in profiles.
    return {'trusted_selection_rejected_without_mutation': True,
            'password_policy_restored': True,
            **native_boundary({**stored(),
                               'database': context.route['database']},
                              context.users)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-config-db', type=Path)
    parser.add_argument('--desktop-user')
    parser.add_argument('--native-only', action='store_true')
    parser.add_argument('--evidence-root', required=True, type=Path)
    parser.add_argument('--theme', default='high-contrast')
    parser.add_argument('--font-scale', type=int, default=150)
    options = parser.parse_args()
    if not options.native_only and not (
            options.source_config_db and options.desktop_user):
        parser.error('Browser mode needs source config and desktop user')
    if sys.platform != 'linux':
        parser.error('This evidence gate requires Linux')

    def callback(route, plugin, users, evidence):
        if options.native_only:
            return native_boundary(route, users)
        return browser_case(options, route, plugin, users, evidence,
                            profile_check=check_platform)

    result = native_run(options.evidence_root, callback, ['Srp256'])
    raise SystemExit(0 if result['complete'] else 1)
