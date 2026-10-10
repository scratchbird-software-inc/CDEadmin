#!/usr/bin/env python3
"""Linux native text editor save/reject/clear and browser qualification.

Windows/macOS teams repeat native/browser behavior on their own runtimes.
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

    def stored():
        with sqlite3.connect(context.database) as database:
            return json.loads(database.execute(
                'SELECT configuration FROM cde_endpoint_route WHERE id=?',
                (context.route_id,)).fetchone()[0])

    for text, accepted in (
            ('# operator text\nTcpNoNagle=false\n'
             'ClientBatchBuffer=128K', True),
            ('WireCrypt=Disabled', False),
            ('TcpNoNagle=yes\nConnectionTimeout=5', True), ('', True)):
        item = context.load_tree()
        invoke_context_action(wait, driver, item, [
            'Endpoint registration', 'Edit endpoint properties...'],
            handle_endpoint_prompt=False)
        wait.until(form)
        previous = stored()
        fill_fields(wait, [
            'Per-connection wire encryption configuration=' + text,
        ], control_root=form)
        save = visible_named_control(form(driver), 'Save endpoint profile')
        driver.execute_script(
            'arguments[0].scrollIntoView({block:"center"}); '
            'arguments[0].focus()', save)
        assert driver.execute_script(
            'return document.activeElement === arguments[0]', save)
        save.send_keys(Keys.ENTER)
        if accepted:
            wait.until(lambda _: stored().get('wire_config') == (text or None))
        else:
            wait.until(lambda _: 'duplicates the explicit WireCrypt' in
                       driver.find_element('tag name', 'body').text)
            assert stored() == previous
        pages = screenshot_form_pages(
            driver, context.evidence / f'config-{len(observations) + 1}',
            selector=selector)
        if accepted:
            response = context.prompt(context.users[0][1])
            assert response['status'] == 200
            assert response['body']['data']['connected_as'] == (
                context.users[0][0])
            assert context.request('connect', 'DELETE')['status'] == 200
        observations.append({'accepted': accepted, 'pages': pages,
                             'cleared': accepted and not text})
    return {'config_profiles': observations, 'keyboard_save': True,
            'invalid_save_preserves_profile': True}


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
