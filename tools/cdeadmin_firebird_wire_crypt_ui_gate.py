#!/usr/bin/env python3
"""Linux WireCrypt form controls and native admission at both UI scales.

Windows/macOS teams repeat loader/policy/browser accessibility qualification.
Only a disposable server and private configuration snapshot are modified.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from selenium.webdriver.common.keys import Keys
from tools.cdeadmin_firebird_password_gate import run
from tools.cdeadmin_firebird_password_ui_gate import browser_case
from tools.cdeadmin_firebird_ui_form_gate import screenshot_form_pages
from tools.cdeadmin_ui_evidence import (
    fill_fields, invoke_context_action, visible_named_control,
)


def profile_checks(context):
    driver, wait = context.driver, context.wait
    selector = '[data-form-id="cdeadmin.firebird-native.server.edit.v1"]'
    observations = []

    def form(browser):
        return next((element for element in browser.find_elements(
            'css selector', selector) if element.is_displayed()), None)

    for policy, plugins, status in (
            ('Required', 'ChaCha64', 200), ('Enabled', 'ChaCha', 200),
            ('Disabled', 'ChaCha64', 200),
            ('Required', 'CDE_NoSuchWirePlugin', 401),
            ('Required', '', 200),
            ('Required', 'ChaCha64', 200)):
        item = context.load_tree()
        invoke_context_action(wait, driver, item, [
            'Endpoint registration', 'Edit endpoint properties...'],
            handle_endpoint_prompt=False)
        wait.until(form)
        fill_fields(wait, [
            f'Wire encryption policy={policy}',
            f'Wire encryption plugin preference list={plugins}',
        ], control_root=form)
        save = visible_named_control(form(driver), 'Save endpoint profile')
        driver.execute_script(
            'arguments[0].scrollIntoView({block:"center"}); '
            'arguments[0].focus()', save)
        assert driver.execute_script(
            'return document.activeElement === arguments[0]', save)
        save.send_keys(Keys.ENTER)

        def persisted(_):
            with sqlite3.connect(context.database) as database:
                values = json.loads(database.execute(
                    'SELECT configuration FROM cde_endpoint_route WHERE id=?',
                    (context.route_id,)).fetchone()[0])
            return (values.get('wire_crypt') == policy and
                    values.get('wire_crypt_plugins') == (plugins or None))

        wait.until(persisted)
        pages = screenshot_form_pages(
            driver, context.evidence / f'wire-{len(observations) + 1}',
            selector=selector)
        response = context.prompt(context.users[0][1])
        assert response['status'] == status
        if status == 200:
            assert response['body']['data']['connected_as'] == (
                context.users[0][0])
            assert context.request('connect', 'DELETE')['status'] == 200
        observations.append({'policy': policy, 'plugins': plugins,
                             'status': status, 'pages': pages})
    return {'wire_profiles': observations, 'keyboard_save': True,
            'explicit_recovery': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-config-db', type=Path, required=True)
    parser.add_argument('--desktop-user', required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--theme', default='high-contrast')
    parser.add_argument('--font-scale', type=int, default=100)
    options = parser.parse_args()
    original = hashlib.sha256(
        options.source_config_db.read_bytes()).hexdigest()
    result = run(options.evidence_root, lambda *args: browser_case(
        options, *args, profile_check=profile_checks), ['Srp256'])
    result['source_config_unchanged'] = original == hashlib.sha256(
        options.source_config_db.read_bytes()).hexdigest()
    result['complete'] &= result['source_config_unchanged']
    (options.evidence_root / 'summary.json').write_text(
        json.dumps(result, indent=2) + '\n')
    raise SystemExit(0 if result['complete'] else 1)
