#!/usr/bin/env python3
"""FM-FB02-002: Linux ordered native authentication negotiation.

Uses the password gate's owned disposable Firebird 5.0.4 fixture. Never changes
demo servers. Windows/macOS teams must repeat native loader/order/rejection and
concurrent isolation checks; Win_Sspi requires separate Windows qualification.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import traceback
from types import SimpleNamespace
import uuid

from tools.cdeadmin_firebird_password_gate import PLUGINS, run as password_run
from tools.cdeadmin_firebird_native_opening_gate import _create_client
from pgadmin.cdeadmin.security.secrets import SecretLease
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.providers.firebird.provider import (
    _database_create_arguments,
)
from pgadmin.cdeadmin.providers.firebird.connection_strings import database_dsn
from pgadmin.cdeadmin.providers.firebird.database_creation import (
    create_database,
)


# Expected methods follow the native ParsedList merge order, not a CDEadmin
# retry loop. MON$AUTH_METHOD provides the database-side observation.
CASES = (
    ('client-order-sha512', 'Srp512,Srp256', 'Srp512', 'Required'),
    ('client-order-sha256', 'Srp256,Srp512', 'Srp256', 'Required'),
    ('spaces-semicolons-tabs', 'Srp384;\tSrp256 Srp', 'Srp384', 'Required'),
    ('skip-unavailable', 'CDE_NoSuchAuthPlugin,Srp224', 'Srp224', 'Required'),
    ('duplicate-order', 'Srp,Srp,Srp256', 'Srp', 'Required'),
    ('unavailable-only', 'CDE_NoSuchAuthPlugin', None, 'Required'),
    ('case-sensitive-mismatch', 'srp256', None, 'Required'),
    ('wrong-user-manager', 'Legacy_Auth', None, 'Enabled'),
    ('native-default', None, 'Srp256', 'Required'),
)


def attach(route, password, plugins, expected, wire='Required',
           creation=False):
    selected = {**route, 'auth_plugin_list': plugins, 'wire_crypt': wire,
                'credential_reference_id': 'owned-secret',
                'principal_reference': 'owned-principal'}
    observed = {}
    for kind in ('database', 'services'):
        client = _create_client(SimpleNamespace(
            acquire_secret=lambda *_args: SecretLease(password)))
        try:
            try:
                if kind == 'database':
                    handle = client.open_session({'route': selected})
                else:
                    handle = client._connect_server({'route': {
                        key: value for key, value in selected.items()
                        if key != 'database'}})
            except RelationalClientError as error:
                if expected is not None:
                    raise
                assert set(error.gds_codes).intersection({
                    335544472, 335545106, 335545065,
                }), 'Expected authentication or wire-encryption rejection'
                assert not client._connections
                observed[kind] = {'rejected': True,
                                  'gds_codes': list(error.gds_codes)}
            else:
                assert expected is not None, 'Unexpected authentication'
                if kind == 'database':
                    with handle.cursor() as cursor:
                        cursor.execute('SELECT MON$AUTH_METHOD '
                                       'FROM MON$ATTACHMENTS WHERE '
                                       'MON$ATTACHMENT_ID=CURRENT_CONNECTION')
                        actual = cursor.fetchone()[0].strip()
                    assert actual == expected, (actual, expected)
                    handle.rollback()
                    observed[kind] = {'method': actual}
                else:
                    assert '5.0.4' in handle.info.version
                    # Services API exposes no MON$AUTH_METHOD. Record only
                    # admission using the exact configured SPB, not a guessed
                    # negotiated method for the service attachment.
                    observed[kind] = {'authenticated': True}
                client.close_session(handle)
                assert not client._connections
        finally:
            client.close()
    if creation:
        import firebird.driver as native
        import firebird.driver.core as core
        target = database_dsn(
            '/var/lib/firebird/data/plugins-' + uuid.uuid4().hex + '.fdb',
            route['host'], route['port'])
        handle = None
        try:
            arguments = _database_create_arguments(
                selected, target, {}, native)
            try:
                handle = create_database(native, core, password=password,
                                         **arguments)
            except native.Error as error:
                if expected is not None:
                    raise
                assert set(error.gds_codes).intersection({
                    335544472, 335545106, 335545065})
                observed['creation'] = {'rejected': True,
                                        'gds_codes': list(error.gds_codes)}
            else:
                assert expected is not None, 'Unexpected creation admission'
                with handle.cursor() as cursor:
                    cursor.execute('SELECT MON$AUTH_METHOD '
                                   'FROM MON$ATTACHMENTS WHERE '
                                   'MON$ATTACHMENT_ID=CURRENT_CONNECTION')
                    method = cursor.fetchone()[0].strip()
                assert method == expected
                handle.rollback()
                handle.drop_database()
                observed['creation'] = {'method': method,
                                        'owned_database_dropped': True}
        finally:
            if handle is not None:
                handle.close()
    return observed


def run(evidence, restricted=False):
    def qualify(route, plugin, users, directory):
        directory.mkdir()
        selected = {**route, 'user': users[0][0]}
        results = {'cases': [], 'failures': []}
        cases = (
            ('installed-but-server-disabled', 'Srp512', None, 'Required'),
            ('restricted-server-fallback', 'Srp512,Srp256',
             'Srp256', 'Required'),
        ) if restricted else CASES
        if plugin == 'Legacy_Auth':
            cases = (
                ('legacy-valid-control', 'Legacy_Auth',
                 'Legacy_Auth', 'Enabled'),
                ('legacy-cannot-encrypt', 'Legacy_Auth', None, 'Required'),
            )
        for name, plugins, expected, wire in cases:
            try:
                observation = attach(selected, users[0][1], plugins,
                                     expected, wire, creation=True)
                results['cases'].append({'name': name, **observation})
            except Exception as error:
                results['failures'].append({
                    'name': name, 'type': type(error).__name__,
                    'gds_codes': list(getattr(error, 'gds_codes', ())),
                    'locations': [frame.lineno for frame in
                                  traceback.extract_tb(error.__traceback__)]})
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(attach, selected, users[0][1],
                                       plugins, expected, wire)
                           for _, plugins, expected, wire in cases[:4]]
                results['concurrent'] = [future.result() for future in futures]
        except Exception as error:
            results['failures'].append({'name': 'concurrent-isolation',
                                       'type': type(error).__name__})
        (directory / 'negotiation.json').write_text(
            json.dumps(results, indent=2) + '\n')
        assert not results['failures'], 'Native negotiation failures recorded'
        return results

    return password_run(evidence, browser=qualify, selected_plugins=(
        ['Srp256'] if restricted else ['Srp256', 'Legacy_Auth']),
                        server_plugins=(['Srp256'] if restricted else
                                        ['CDE_NoSuchAuthPlugin', *PLUGINS]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', required=True, type=Path)
    parser.add_argument('--restricted-server', action='store_true')
    options = parser.parse_args()
    outcome = run(options.evidence_root, options.restricted_server)
    raise SystemExit(0 if outcome['complete'] else 1)
