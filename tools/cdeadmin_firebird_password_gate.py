#!/usr/bin/env python3
"""Linux password authentication qualification against an owned Firebird 5.

Windows/macOS teams must repeat native client, Services API, saved credential,
prompt, alternate-user and disconnect checks on their platforms. Win_Sspi is
not a Linux password plugin and belongs to its separate qualification row.
Legacy authentication is enabled only in this isolated disposable fixture;
never weaken a user's server or the application's default WireCrypt policy.
"""

import argparse
import json
import os
from pathlib import Path
import secrets
import traceback
from types import SimpleNamespace
import uuid

from tools.cdeadmin_firebird_native_opening_gate import (
    docker, published_port, remove_owned, OWNER, wait_ready,
    _configure_client_library, _route_arguments, _create_client,
)
from pgadmin.cdeadmin.security.secrets import SecretLease
from pgadmin.cdeadmin.sdk.relational import RelationalClientError

PLUGINS = ('Srp256', 'Srp', 'Srp224', 'Srp384', 'Srp512', 'Legacy_Auth')


def authenticate(native, route, user, password, plugin):
    selected = {**route, 'user': user, 'auth_plugin_list': plugin,
                'wire_crypt': 'Enabled' if plugin == 'Legacy_Auth'
                else 'Required', 'credential_reference_id': 'owned-secret',
                'principal_reference': 'owned-principal'}
    client = _create_client(SimpleNamespace(
        acquire_secret=lambda *_args: SecretLease(password)))
    try:
        handle = client.open_session({'route': selected})
        with handle.cursor() as cursor:
            cursor.execute('SELECT CURRENT_USER, MON$AUTH_METHOD '
                           'FROM MON$ATTACHMENTS '
                           'WHERE MON$ATTACHMENT_ID = CURRENT_CONNECTION')
            identity, method = cursor.fetchone()
            assert identity.strip() == user and method.strip() == plugin
        handle.rollback()
        client.close_session(handle)
        service = client._connect_server({'route': {
            key: value for key, value in selected.items()
            if key != 'database'}})
        assert '5.0.4' in service.info.version
        assert client.close_session(service)['service_handle_released']
        assert not client._connections
    finally:
        client.close()


def reject_password(route, user, password, plugin):
    selected = {**route, 'user': user, 'auth_plugin_list': plugin,
                'wire_crypt': 'Enabled' if plugin == 'Legacy_Auth'
                else 'Required', 'credential_reference_id': 'owned-secret',
                'principal_reference': 'owned-principal'}
    for database in (True, False):
        client = _create_client(SimpleNamespace(
            acquire_secret=lambda *_args: SecretLease(password)))
        try:
            request = {'route': selected if database else {
                key: value for key, value in selected.items()
                if key != 'database'}}
            try:
                (client.open_session if database else
                 client._connect_server)(request)
            except RelationalClientError as error:
                assert 335544472 in error.gds_codes
                assert not client._connections
            else:
                raise AssertionError('Wrong password admitted')
        finally:
            client.close()


def run(evidence, browser=None, selected_plugins=None, server_plugins=None,
        fixture_check=None):
    selected = tuple(PLUGINS if selected_plugins is None else selected_plugins)
    if (not selected or len(set(selected)) != len(selected) or
            set(selected).difference(PLUGINS)):
        raise ValueError('Select unique supported password plugins')
    offered = tuple(PLUGINS if server_plugins is None else server_plugins)
    if (not offered or len(set(offered)) != len(offered) or
            set(offered).difference((*PLUGINS, 'CDE_NoSuchAuthPlugin')) or
            'Srp256' not in offered or
            set(selected).difference(offered)):
        raise ValueError('Select supported server plugins including Srp256')
    import firebird.driver as native
    _configure_client_library(native)
    evidence.mkdir(parents=True, exist_ok=False)
    result = {'complete': False, 'cases': [], 'failures': [],
              'owned_container_removed': False,
              'selected_plugins': list(selected),
              'server_plugins': list(offered)}
    container = None
    root_password = secrets.token_urlsafe(24)
    accounts = {
        'Srp': [('OWNED_DÉFAULT', 'Pwd-é-' + secrets.token_hex(12)),
                ('OWNED_ALTERNATE', 'Alt-密-' + secrets.token_hex(12))],
        # Legacy passwords have an eight-byte significant prefix. Wrong
        # password tests change that prefix rather than append a suffix.
        'Legacy_UserManager': [('OWNED_LEGACY', secrets.token_hex(4)),
                               ('OWNED_LEGACY_ALT', secrets.token_hex(4))],
    }
    try:
        container = docker(
            'run', '--detach', '--name',
            'cdeadmin-password-' + uuid.uuid4().hex[:16], '--label',
            'cdeadmin-owned-gate=' + OWNER, '--publish', '127.0.0.1::3050',
            '--env', 'FIREBIRD_ROOT_PASSWORD', '--env', 'FIREBIRD_DATABASE',
            'firebirdsql/firebird:5.0.4', env=dict(
                os.environ, FIREBIRD_ROOT_PASSWORD=root_password,
                FIREBIRD_DATABASE='/var/lib/firebird/data/password.fdb')
        ).decode().strip()
        route = {'host': '127.0.0.1', 'port': published_port(container),
                 'database': '/var/lib/firebird/data/password.fdb',
                 'user': 'SYSDBA', 'auth_plugin_list': 'Srp256', 'timeout': 3}
        wait_ready(native, route, root_password)
        docker('exec', '-i', container, 'tee', '-a',
               '/opt/firebird/firebird.conf',
               input_data=('\nAuthServer = ' + ','.join(offered) +
                           '\nUserManager = Srp, Legacy_UserManager\n'
                           'WireCrypt = Enabled\n').encode())
        docker('restart', container)
        route['port'] = published_port(container)
        wait_ready(native, route, root_password)
        with native.connect(password=root_password,
                            **_route_arguments(route, native)) as admin:
            for manager, users in accounts.items():
                for name, password in users:
                    admin.execute_immediate(
                        f'CREATE USER "{name}" PASSWORD \'{password}\' '
                        f'USING PLUGIN {manager}')
                    # Owned fixture only: creation authentication must be
                    # tested independently of database-creation privilege.
                    admin.execute_immediate(
                        f'GRANT CREATE DATABASE TO USER "{name}"')
            admin.commit()
            # Optional privileged checks run only on this owned fixture;
            # the root password is never passed to callbacks or exported.
            if fixture_check:
                fixture_check(native, admin, route, accounts, evidence)
        for plugin in selected:
            users = accounts['Legacy_UserManager' if plugin == 'Legacy_Auth'
                             else 'Srp']
            try:
                for user, password in users:
                    authenticate(native, route, user, password, plugin)
                    reject_password(route, user, 'WRONG-' + password, plugin)
                reject_password(route, 'OWNED_USER_DOES_NOT_EXIST',
                                users[0][1], plugin)
                observed = {'plugin': plugin, 'native_principals': 2,
                            'database_and_services_authenticated': True,
                            'wrong_passwords_rejected': True,
                            'unknown_principal_rejected': True,
                            'handles_released': True}
                if browser:
                    observed['browser'] = browser(route, plugin, users,
                                                  evidence / plugin)
                result['cases'].append(observed)
            except Exception as error:
                # Only locations/types: driver text may contain credentials.
                result['failures'].append({
                    'plugin': plugin, 'error_type': type(error).__name__,
                    'locations': [{'file': Path(frame.filename).name,
                                   'line': frame.lineno}
                                  for frame in traceback.extract_tb(
                                      error.__traceback__)]})
    finally:
        if container:
            remove_owned(container)
            result['owned_container_removed'] = True
        result['complete'] = (len(result['cases']) == len(selected) and
                              not result['failures'] and
                              result['owned_container_removed'])
        (evidence / 'summary.json').write_text(
            json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', required=True, type=Path)
    options = parser.parse_args()
    raise SystemExit(0 if run(options.evidence_root)['complete'] else 1)
