#!/usr/bin/env python3
"""FM-FB02-009 Linux native profile replacement and browser recovery.

Windows/macOS teams must repeat native detach/network failure, credential
storage, concurrent admission and accessible refusal/retry on their clients.
Only the password gate's owned server and copied application configuration
are changed. Failure injection below is labelled, never called a network test.
"""

import argparse
from contextlib import nullcontext
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import traceback
from types import SimpleNamespace
import uuid
from unittest.mock import Mock, patch

from tools.cdeadmin_firebird_password_gate import (
    run as native_run, _create_client, SecretLease,
)
from tools.cdeadmin_firebird_password_ui_gate import browser_case
from tools.cdeadmin_firebird_ui_form_gate import (
    screenshot_form_pages,
)
from tools.cdeadmin_ui_evidence import (
    invoke_context_action, visible_named_control,
)
from selenium.webdriver.common.keys import Keys
from pgadmin.cdeadmin.core import (
    EndpointContext, ProviderRegistry, ProviderReleaseError,
)
from pgadmin.cdeadmin.providers.firebird.provider import FirebirdProvider
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def registered(client):
    path = Path(__file__).resolve().parents[1] / (
        'web/pgadmin/cdeadmin/providers/firebird/provider_manifest.json')
    manifest = json.loads(path.read_text())
    identity = manifest['identity']
    context = EndpointContext(
        endpoint_id=str(uuid.uuid4()), mode='legacy_native',
        experience_family='firebird', **{
            key: identity[key] for key in (
                'provider_id', 'provider_version', 'profile_id',
                'profile_version')},
        target_adapter_id=manifest['composition']['target_adapter_ids'][0],
        target_adapter_version='owned-profile-test',
        **{key: str(uuid.uuid4()) for key in (
            'pool_namespace', 'session_namespace', 'cache_namespace',
            'diagnostic_namespace')},
        effective_permissions=frozenset(
            item['permission_id'] for item in manifest['permissions']
            if item['granted']),
        runtime_identity_generation='owned-profile-generation')
    registry = ProviderRegistry()
    with patch('pgadmin.cdeadmin.providers.firebird.provider.create_provider',
               side_effect=lambda context, permissions: FirebirdProvider(
                   context, permissions, client)):
        registry.register_package(
            manifest, 'pgadmin.cdeadmin.providers.firebird.provider')
        binding = registry.resolve(context)
    return registry, binding


def native_cases(native, admin, route, accounts, evidence):
    users = accounts['Srp']
    admin.execute_immediate('CREATE TABLE PROFILE_MARKER (ID INTEGER)')
    for user, _password in users:
        admin.execute_immediate(
            'GRANT ALL ON PROFILE_MARKER TO "' + user + '"')
    admin.commit()
    report = {'checks': [], 'failures': []}
    for state in ('idle', 'pending-rollback', 'pending-commit', 'sql-error',
                  'cursor', 'service', 'detach-failure-injected',
                  'initialization-release-failure-injected',
                  'opening', 'temporary'):
        client = _create_client(SimpleNamespace(
            acquire_secret=lambda *_: SecretLease(users[0][1])))
        selected = {**route, 'user': users[0][0],
                    'credential_reference_id': 'owned-profile-secret',
                    'principal_reference': 'owned-profile-principal'}
        registry, binding = registered(client)
        handle = cursor = None
        try:
            if state == 'initialization-release-failure-injected':
                original = client.config
                failure = RelationalClientError('injected initialization')
                client.config = replace(
                    original, session_initializer=Mock(side_effect=failure),
                    failed_session_releaser=Mock(side_effect=failure))
                try:
                    client.open_session({'route': selected})
                except RelationalClientError:
                    pass
                finally:
                    client.config = original
                assert len(client._connections) == 1
                handle = client._connections[0]
                assert id(handle) in client._failed_initializations
            elif state not in {'opening', 'temporary'}:
                handle = (client._connect_server if state == 'service' else
                          client.open_session)({'route': selected})
            if state.startswith('pending'):
                handle.execute_immediate(
                    'INSERT INTO PROFILE_MARKER VALUES (1)')
            if state == 'sql-error':
                try:
                    handle.execute_immediate('SELECT FROM INVALID_NATIVE_SQL')
                except native.Error:
                    pass
                else:
                    raise AssertionError('Expected native SQL failure')
            if state == 'cursor':
                cursor = handle.cursor()
                cursor.execute('SELECT RDB$RELATION_NAME FROM RDB$RELATIONS')
                assert cursor.fetchone()
            if state == 'detach-failure-injected':
                with patch.object(
                        client, '_release_attachment',
                        side_effect=RelationalClientError('injected detach')):
                    try:
                        client.close_session(handle)
                    except RelationalClientError:
                        pass
                    else:
                        raise AssertionError('Expected failed release')
            scope = (client._connecting() if state == 'opening' else
                     client._temporary_operation() if state == 'temporary'
                     else nullcontext())
            with scope:
                try:
                    with registry.endpoint_configuration_change(
                            binding.context.endpoint_id):
                        raise AssertionError('Unsafe replacement admitted')
                except ProviderReleaseError:
                    pass
            assert registry.resolve(binding.context) is binding
            assert not client._closed
            if state.startswith('pending'):
                assert handle.main_transaction.is_active()
                if admin.main_transaction.is_active():
                    admin.rollback()
                with admin.cursor() as observer:
                    observer.execute('SELECT COUNT(*) FROM PROFILE_MARKER')
                    assert observer.fetchone() == (0,)
                getattr(handle, 'commit' if state.endswith('commit') else
                        'rollback')()
                admin.rollback()
                with admin.cursor() as observer:
                    observer.execute('SELECT COUNT(*) FROM PROFILE_MARKER')
                    assert observer.fetchone() == (
                        1 if state.endswith('commit') else 0,)
                admin.execute_immediate('DELETE FROM PROFILE_MARKER')
                admin.commit()
            if cursor:
                cursor.close()
            if handle:
                client.close_session(handle)
            with registry.endpoint_configuration_change(
                    binding.context.endpoint_id):
                assert client._closed
            try:
                client.open_session({'route': selected})
            except RelationalClientError:
                pass
            else:
                raise AssertionError('Stale client reconnected')
            report['checks'].append({'state': state, 'refused': True,
                                     'explicit_cleanup_and_retry': True})
        except Exception as error:
            report['failures'].append({
                'state': state, 'type': type(error).__name__,
                'lines': [frame.lineno for frame in
                          traceback.extract_tb(error.__traceback__)]})
        finally:
            client.close()
    (evidence / 'profile-native.json').write_text(
        json.dumps(report, indent=2) + '\n')
    assert len(report['checks']) == 10 and not report['failures']


def profile_checks(context):
    """Real Save/credential prompt refusal with public API-owned sessions."""
    driver, wait = context.driver, context.wait
    assert context.prompt(context.users[0][1])['status'] == 200

    def request(action, **values):
        return context.request('cde_workspace', 'POST',
                               {'action': action, **values})

    attached = request('database_target_attach', request={
        'database': context.route['database'], 'display_name': 'Profile gate'})
    assert attached['status'] == 200, attached
    target = attached['body']['data']['active_target_id']

    def stored():
        with sqlite3.connect(context.database) as db:
            return db.execute('SELECT configuration FROM cde_endpoint_route '
                              'WHERE id=?', (context.route_id,)).fetchone()[0]

    def edit(expect_refusal, state='idle'):
        previous = stored()
        item = context.load_tree()
        invoke_context_action(wait, driver, item,
                              ['Endpoint registration',
                               'Edit endpoint properties...'],
                              handle_endpoint_prompt=False)
        selector = ('[data-form-id="'
                    'cdeadmin.firebird-native.server.edit.v1"]')

        def control(name):
            return wait.until(lambda browser: next((
                value for form in browser.find_elements(
                    'css selector', selector)
                if form.is_displayed()
                for value in [visible_named_control(form, name)] if value),
                None))

        field = control('Authentication plugin preference list')
        field.send_keys(Keys.CONTROL, 'a', Keys.BACKSPACE)
        field.send_keys('Srp256,Srp')
        save = control('Save endpoint profile')
        driver.execute_script(
            'arguments[0].scrollIntoView({block:"center"}); '
            'arguments[0].focus()', save)
        assert driver.execute_script(
            'return document.activeElement === arguments[0]', save)
        save.send_keys(Keys.ENTER)
        if expect_refusal:
            wait.until(lambda browser: 'open sessions' in
                       browser.find_element('tag name', 'body').text)
            assert stored() == previous
        else:
            wait.until(lambda _: json.loads(stored()).get(
                'auth_plugin_list') == 'Srp256,Srp')
        return screenshot_form_pages(driver, context.evidence / (
            'profile-refused-' + state if expect_refusal else 'profile-saved'),
            selector=selector)

    opened = request('open_session', language_profile='firebird-sql',
                     database_target_id=target)
    assert opened['status'] == 200, opened
    session = opened['body']['data']['session_id']
    try:
        pages = edit(True)
        state_pages = {}
        for state, sql in (
                ('pending', 'INSERT INTO PROFILE_MARKER VALUES (2)'),
                ('sql-error', 'SELECT FROM INVALID_NATIVE_SQL')):
            execution = request('execute', session_id=session, source=sql,
                                database_target_id=target)
            assert execution['status'] == 200, execution
            occurrence = execution['body']['data']['occurrence_id']

            def terminal(_browser):
                polled = request('poll', occurrence_id=occurrence,
                                 database_target_id=target)
                assert polled['status'] == 200, polled
                value = polled['body']['data']['occurrence']
                return value if value['operation']['terminal'] else False

            ended = wait.until(terminal)
            assert ended['result']['extensions']['firebird'][
                'payload']['execution_state'] == (
                'failed' if state == 'sql-error' else 'succeeded'), ended
            state_pages[state] = edit(True, state)
        # Credentials and Forget/Disconnect cannot bypass Save admission.
        for payload in ({'password': context.users[0][1]},
                        {'password': context.users[1][1],
                         'connect_as': context.users[1][0]}):
            rejected = context.request('verify_endpoint', 'POST', payload)
            assert rejected['status'] != 200
            assert 'open sessions' in json.dumps(rejected)
        rejected = context.request('connect', 'DELETE')
        assert rejected['status'] != 200
        assert 'open sessions' in json.dumps(rejected)
        assert request('transaction', session_id=session,
                       database_target_id=target)['status'] == 200
        assert request('transaction_action', session_id=session,
                       database_target_id=target,
                       transaction_action='rollback')['status'] == 200
    finally:
        assert request('close_session', session_id=session,
                       database_target_id=target)['status'] == 200
    saved = edit(False)
    # Return to the password gate's expected empty credential state.
    assert context.request('connect', 'DELETE')['status'] == 200
    return {'refusal_screenshots': pages, 'recovery_screenshots': saved,
            'state_refusal_screenshots': state_pages,
            'save_keyboard_activation': True,
            'open_session_preserved': True, 'credential_bypasses_refused': 3,
            'explicit_rollback_close_then_save': True}


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
    outcome = native_run(options.evidence_root, lambda *args: browser_case(
        options, *args, profile_check=profile_checks), ['Srp256'],
        fixture_check=native_cases)
    outcome['source_config_unchanged'] = original == hashlib.sha256(
        options.source_config_db.read_bytes()).hexdigest()
    outcome['complete'] &= outcome['source_config_unchanged']
    (options.evidence_root / 'summary.json').write_text(
        json.dumps(outcome, indent=2) + '\n')
    raise SystemExit(0 if outcome['complete'] else 1)
