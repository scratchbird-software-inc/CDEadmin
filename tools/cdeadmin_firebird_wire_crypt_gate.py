#!/usr/bin/env python3
"""FM-FB03-004 Linux native WireCrypt policy/plugin matrix.

Windows/macOS teams must repeat native loader, negotiation, transactions and
browser tests. Only an owned fixture is reconfigured. Services admission is
observed, not reported as a nonexistent Services negotiated-plugin metric.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import traceback
from types import SimpleNamespace
import uuid

from tools.cdeadmin_firebird_password_gate import run
from tools.cdeadmin_firebird_native_opening_gate import (
    docker, published_port, OWNER, wait_ready, _create_client,
)
from pgadmin.cdeadmin.security.secrets import SecretLease
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.providers.firebird.provider import (
    _database_create_arguments,
)
from pgadmin.cdeadmin.providers.firebird.database_creation import (
    create_database,
)
from pgadmin.cdeadmin.providers.firebird.connection_strings import database_dsn


def observe(handle, encrypted, plugin):
    with handle.cursor() as cursor:
        cursor.execute('SELECT MON$WIRE_ENCRYPTED, MON$WIRE_CRYPT_PLUGIN '
                       'FROM MON$ATTACHMENTS WHERE '
                       'MON$ATTACHMENT_ID=CURRENT_CONNECTION')
        active, actual = cursor.fetchone()
    assert bool(active) == encrypted
    assert (actual.strip() if actual else None) == plugin
    handle.rollback()
    return {'encrypted': bool(active), 'plugin': actual}


def check(route, password, policy, plugins, admitted, encrypted, plugin,
          *, creation=True, observation=observe):
    import firebird.driver as native
    import firebird.driver.core as core
    values = {**route, 'wire_crypt': policy, 'wire_crypt_plugins': plugins,
              'credential_reference_id': 'owned-secret',
              'principal_reference': 'owned-principal'}
    result = {}
    client = _create_client(SimpleNamespace(
        acquire_secret=lambda *_: SecretLease(password)))
    try:
        for kind in ('database', 'services'):
            try:
                handle = (client.open_session if kind == 'database' else
                          client._connect_server)({'route': values})
            except RelationalClientError as error:
                assert not admitted and error.gds_codes
                assert password not in str(error)
                result[kind] = {'rejected': True,
                                'gds_codes': list(error.gds_codes)}
            else:
                try:
                    assert admitted
                    if kind == 'database':
                        result[kind] = observation(handle, encrypted, plugin)
                    else:
                        assert '5.0.4' in handle.info.version
                        result[kind] = {'admitted': True}
                finally:
                    client.close_session(handle)
            assert not client._connections
        if creation:
            target = database_dsn(
                '/var/lib/firebird/data/wire-' + uuid.uuid4().hex + '.fdb',
                route['host'], route['port'])
            handle = None
            try:
                args = _database_create_arguments(values, target, {}, native)
                try:
                    handle = create_database(native, core, password=password,
                                             **args)
                except native.Error as error:
                    assert not admitted and error.gds_codes
                    result['create'] = {'rejected': True}
                else:
                    assert admitted
                    result['create'] = observation(handle, encrypted, plugin)
                    handle.execute_immediate('CREATE TABLE WIRE_TX (ID INT)')
                    handle.commit()
                    observer = client.open_session({'route': {
                        **values, 'database': target}})
                    try:
                        for commit, expected in ((False, 0), (True, 1)):
                            handle.execute_immediate(
                                'INSERT INTO WIRE_TX VALUES (1)')
                            (handle.commit if commit else handle.rollback)()
                            with observer.cursor() as cursor:
                                cursor.execute('SELECT COUNT(*) FROM WIRE_TX')
                                assert cursor.fetchone()[0] == expected
                            observer.rollback()
                        result['create']['commit_rollback_observed'] = True
                    finally:
                        client.close_session(observer)
                    handle.drop_database()
            finally:
                if handle is not None:
                    handle.close()
    finally:
        client.close()
    return result


def matrix(native, admin, route, accounts, evidence):
    candidates = docker('ps', '--filter', 'label=cdeadmin-owned-gate=' + OWNER,
                        '--format', '{{.ID}}').decode().split()
    matches = []
    for item in candidates:
        try:
            if published_port(item) == route['port']:
                matches.append(item)
        except RuntimeError:
            continue
    assert len(matches) == 1
    server = matches[0]
    original = docker('exec', server, 'cat', '/opt/firebird/firebird.conf')
    user, password = accounts['Srp'][0]
    selected = {**route, 'user': user}
    admin.close()
    results = {'checks': [], 'failures': []}

    def configure(policy, plugins):
        config = re.sub(rb'(?mi)^\s*WireCrypt(?:Plugin)?\s*=.*$',
                        b'', original)
        config += ('\nWireCrypt = ' + policy + '\nWireCryptPlugin = ' +
                   plugins + '\n').encode()
        docker('exec', '-i', server, 'tee', '/opt/firebird/firebird.conf',
               input_data=config)
        docker('restart', server)
        route['port'] = selected['port'] = published_port(server)
        wait_ready(native, {**selected, 'wire_crypt': 'Enabled'}, password)

    def case(name, operation):
        try:
            results['checks'].append({'case': name, 'result': operation()})
        except Exception as error:
            results['failures'].append({
                'case': name, 'type': type(error).__name__,
                'lines': [f.lineno for f in traceback.extract_tb(
                    error.__traceback__)]})
        (evidence / 'wire-matrix.json').write_text(
            json.dumps(results, indent=2) + '\n')

    try:
        for server_policy in ('Disabled', 'Enabled', 'Required'):
            configure(server_policy, 'ChaCha64')
            for client_policy in ('Disabled', 'Enabled', 'Required'):
                for plugins in ('ChaCha64', 'ChaCha', 'CDE_NoSuchWirePlugin'):
                    required = 'Required' in (client_policy, server_policy)
                    disabled = 'Disabled' in (client_policy, server_policy)
                    compatible = plugins == 'ChaCha64'
                    admitted = not (required and (disabled or not compatible))
                    encrypted = not disabled and compatible
                    case('/'.join((server_policy, client_policy, plugins)),
                         lambda: check(selected, password, client_policy,
                                       plugins, admitted, encrypted,
                                       'ChaCha64' if encrypted else None))
        configure('Enabled', 'ChaCha64,ChaCha,Arc4')
        for plugins, expected in (
                (None, 'ChaCha64'),
                ('ChaCha64', 'ChaCha64'), ('ChaCha', 'ChaCha'),
                ('Arc4', 'Arc4'),
                ('CDE_NoSuchWirePlugin,ChaCha64', 'ChaCha64'),
                ('ChaCha,ChaCha64', 'ChaCha')):
            case('installed/' + (plugins or 'native-default'), lambda: check(
                selected, password, 'Required', plugins, True, True, expected))

        def concurrent():
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(check, selected, password, 'Required',
                                       name, True, True, name, creation=False)
                           for name in ('ChaCha64', 'ChaCha', 'Arc4')]
                return [future.result() for future in futures]
        case('concurrent-plugin-isolation', concurrent)
        legacy_user, legacy_password = accounts['Legacy_UserManager'][0]
        for policy in ('Disabled', 'Enabled', 'Required'):
            case('legacy-key/' + policy, lambda: check(
                {**selected, 'user': legacy_user,
                 'auth_plugin_list': 'Legacy_Auth'}, legacy_password,
                policy, 'ChaCha64', policy != 'Required', False, None))
    finally:
        docker('exec', '-i', server, 'tee', '/opt/firebird/firebird.conf',
               input_data=original)
        docker('restart', server)
        route['port'] = published_port(server)
        wait_ready(native, {**route, 'user': user}, password)
    assert len(results['checks']) == 37 and not results['failures']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, required=True)
    options = parser.parse_args()
    outcome = run(options.evidence_root, selected_plugins=['Srp256'],
                  fixture_check=matrix)
    raise SystemExit(0 if outcome['complete'] else 1)
