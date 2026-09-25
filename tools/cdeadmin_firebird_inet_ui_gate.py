#!/usr/bin/env python3
"""Linux INET/INET4/INET6 form selection, verification and failure recovery.

Windows/macOS teams repeat the resolver, keyboard, native timeout and prompt
flows on their application hosts. Only owned fixtures/configuration copies
are modified; browser-host addressing is never used as server addressing.
"""

import argparse
import hashlib
import json
from pathlib import Path
import socket
import sqlite3

from selenium.webdriver.common.keys import Keys
from tools.cdeadmin_firebird_password_gate import run as native_run
from tools.cdeadmin_firebird_password_ui_gate import browser_case
from tools.cdeadmin_firebird_inet_gate import relay
from tools.cdeadmin_firebird_ui_form_gate import screenshot_form_pages
from tools.cdeadmin_ui_evidence import (
    fill_fields, invoke_context_action, visible_named_control,
)


def profile_checks(context, *, ipv6=False):
    driver, wait = context.driver, context.wait
    observations = []
    selector = '[data-form-id="cdeadmin.firebird-native.server.edit.v1"]'

    def form(browser):
        return next((item for item in browser.find_elements(
            'css selector', selector) if item.is_displayed()), None)

    def stored():
        with sqlite3.connect(context.database) as db:
            return json.loads(db.execute(
                'SELECT configuration FROM cde_endpoint_route WHERE id=?',
                (context.route_id,)).fetchone()[0])

    def edit(protocol, host, port, label):
        item = context.load_tree()
        invoke_context_action(wait, driver, item, [
            'Endpoint registration', 'Edit endpoint properties...'],
            handle_endpoint_prompt=False)
        wait.until(form)
        fill_fields(wait, [f'Network protocol={protocol}',
                           f'Server host or address={host}',
                           f'Server port={port}',
                           'Connection timeout (seconds)=1'],
                    control_root=form)
        save = visible_named_control(form(driver), 'Save endpoint profile')
        driver.execute_script(
            'arguments[0].scrollIntoView({block:"center"}); '
            'arguments[0].focus()', save)
        assert driver.execute_script(
            'return document.activeElement === arguments[0]', save)
        save.send_keys(Keys.ENTER)
        wait.until(lambda _: all(stored().get(key) == value for key, value in {
            'protocol': protocol, 'host': host, 'port': port,
            'timeout': 1}.items()))
        pages = screenshot_form_pages(driver, context.evidence / label,
                                      selector=selector)
        return pages

    with relay((context.route['host'], context.route['port']),
               host='::1' if ipv6 else '127.0.0.10') as link:
        for protocol, host, port in (
                ('INET', 'localhost', link.port if ipv6 else
                 context.route['port']),
                ('INET6' if ipv6 else 'INET4', link.host, link.port)):
            pages = edit(protocol, host, port, protocol.lower())
            response = context.prompt(context.users[0][1])
            assert response['status'] == 200
            assert response['body']['data']['connected_as'] == (
                context.users[0][0])
            observations.append({'protocol': protocol, 'pages': pages,
                                 'native_verification': True})
            assert context.request('connect', 'DELETE')['status'] == 200
        with socket.socket(socket.AF_INET6 if ipv6 else
                           socket.AF_INET) as refused:
            refused.bind(('::1' if ipv6 else '127.0.0.1', 0))
            edit('INET6' if ipv6 else 'INET4',
                 '::1' if ipv6 else '127.0.0.1',
                 refused.getsockname()[1], 'refused')
            response = context.prompt(context.users[0][1])
            assert response['status'] == 401
        pages = edit('INET6' if ipv6 else 'INET4',
                     '[::1]' if ipv6 else context.route['host'],
                     link.port if ipv6 else context.route['port'], 'recovered')
        assert context.prompt(context.users[0][1])['status'] == 200
        assert context.request('connect', 'DELETE')['status'] == 200
        if ipv6:
            # The relay belongs to this task only. Return the private profile
            # to the fixture's direct endpoint for the credential regression.
            edit('INET4', context.route['host'], context.route['port'],
                 'baseline-restored')
    return {'address_variants': observations, 'connection_refused': True,
            'explicit_recovery': True, 'recovery_pages': pages,
            'keyboard_save': True, 'relay_removed': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-config-db', type=Path, required=True)
    parser.add_argument('--desktop-user', required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--theme', default='high-contrast')
    parser.add_argument('--font-scale', type=int, default=100)
    parser.add_argument('--ipv6', action='store_true')
    options = parser.parse_args()
    original = hashlib.sha256(
        options.source_config_db.read_bytes()).hexdigest()
    outcome = native_run(options.evidence_root, lambda *args: browser_case(
        options, *args, profile_check=lambda context: profile_checks(
            context, ipv6=options.ipv6)), ['Srp256'])
    outcome['source_config_unchanged'] = original == hashlib.sha256(
        options.source_config_db.read_bytes()).hexdigest()
    outcome['complete'] &= outcome['source_config_unchanged']
    (options.evidence_root / 'summary.json').write_text(
        json.dumps(outcome, indent=2) + '\n')
    raise SystemExit(0 if outcome['complete'] else 1)
