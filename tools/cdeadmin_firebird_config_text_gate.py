#!/usr/bin/env python3
"""Linux raw client configuration, native precedence and default isolation.

Windows/macOS teams repeat native configuration/plugin and browser tests.
Only process-private driver defaults and an owned fixture are modified;
native host configuration files and the donor source remain read-only.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import json
from pathlib import Path
import re
import socket
import time
import traceback
from types import SimpleNamespace

import psutil

from tools.cdeadmin_firebird_password_gate import (
    run, _create_client, SecretLease,
)
from tools.cdeadmin_firebird_wire_crypt_gate import check
from tools.cdeadmin_firebird_wire_compression_gate import observe_compression
from tools.cdeadmin_firebird_inet_gate import relay
from pgadmin.cdeadmin.providers.firebird.config_text import CLIENT_KEYS
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def audit(source, evidence):
    text = (source / 'src/common/config/config.h').read_text()
    definitions = {(name, kind, scope) for kind, name, scope in re.findall(
        r'\{(TYPE_\w+),\s*"(\w+)",\s*(true|false)', text)}
    admitted = ({name.lower() for name, _, _ in definitions} &
                CLIENT_KEYS.keys())
    assert admitted == CLIENT_KEYS.keys()
    result = []
    for name, kind, scope in sorted(definitions):
        allowed = name.lower() in CLIENT_KEYS
        if allowed:
            assert scope == 'false'
            expected = {'integer': 'TYPE_INTEGER', 'boolean': 'TYPE_BOOLEAN'}
            assert kind == expected.get(
                CLIENT_KEYS[name.lower()], 'TYPE_STRING')
        result.append({'key': name, 'native_type': kind,
                       'native_global': scope == 'true',
                       'admitted_in_network_client_text': allowed,
                       'disposition': 'validated client option' if allowed else
                       'use endpoint, database or host administration; '
                       'not accepted as a network-client override'})
    (evidence / 'setting-audit.json').write_text(
        json.dumps(result, indent=2) + '\n')


def matrix(native, admin, route, accounts, evidence, *,
           creation_root='/var/lib/firebird/data'):
    user, password = accounts['Srp'][0]
    selected = {**route, 'user': user}
    selected.pop('auth_plugin_list', None)
    result = {'checks': [], 'failures': []}
    registry = native.driver_config
    saved = [(obj, obj.config.value) for obj in
             (registry.db_defaults, registry.server_defaults)]
    before = [obj.get_config() for obj, _ in saved]

    def case(name, operation):
        try:
            result['checks'].append({'case': name, 'result': operation()})
        except Exception as error:
            result['failures'].append({
                'case': name, 'type': type(error).__name__,
                'lines': [f.lineno for f in traceback.extract_tb(
                    error.__traceback__)]})
        (evidence / 'config-matrix.json').write_text(
            json.dumps(result, indent=2) + '\n')

    def profile(text, encrypted, compressed, creation=True):
        return check({**selected, 'wire_config': text}, password, None, None,
                     True, encrypted, 'ChaCha64' if encrypted else None,
                     creation=creation, creation_root=creation_root,
                     observation=partial(
                         observe_compression, compressed=compressed))

    profiles = (
        (None, True, False),
        ('# native text\r\nWireCrypt = "Required" # secure\r\n'
         'WireCryptPlugin=ChaCha64\nWireCompression=yes\n'
         'AuthClient=Srp256\nTcpNoNagle=false\nClientBatchBuffer=128K\n'
         'DummyPacketInterval=0\nConnectionTimeout=5', True, True),
        ('WireCrypt=Disabled\nWireCompression=false\nTcpNoNagle=true\n'
         'ClientBatchBuffer=0', False, False),
    )
    try:
        for obj, _ in saved:
            obj.config.value = 'Providers=Engine13\nWireCrypt=Disabled'
        for index, (text, encrypted, compressed) in enumerate(profiles):
            case(f'isolated-profile/{index}', lambda: profile(
                text, encrypted, compressed))

        for text in ('AuthClient=CDE_NoSuchAuthPlugin',
                     'WireCrypt=Required\nWireCryptPlugin=CDE_NoSuchCipher'):
            case('native-refusal/' + text.split('=')[0], lambda: check(
                {**selected, 'wire_config': text}, password,
                None, None, False, False, None,
                creation_root=creation_root))

        def socket_policy(enabled, scope):
            process = psutil.Process()
            before_fds = {c.fd for c in process.net_connections(kind='tcp')}
            client = _create_client(SimpleNamespace(
                acquire_secret=lambda *_: SecretLease(password)))
            values = {**selected, 'wire_config': 'TcpNoNagle=' +
                      str(enabled).lower(),
                      'credential_reference_id': 'owned-config',
                      'principal_reference': 'owned-principal'}
            try:
                opening = (client.open_session if scope == 'database' else
                           client._connect_server)
                handle = opening({'route': values})
                connections = [c for c in process.net_connections(kind='tcp')
                               if c.fd not in before_fds and c.raddr and
                               c.raddr.port == route['port'] and c.fd >= 0]
                assert len(connections) == 1
                connection = connections[0]
                # fromfd duplicates our owned socket descriptor; closing this
                # inspection handle must not close the driver's descriptor.
                with socket.fromfd(connection.fd, connection.family,
                                   connection.type) as inspected:
                    actual = inspected.getsockopt(socket.IPPROTO_TCP,
                                                  socket.TCP_NODELAY)
                assert actual == int(enabled)
                client.close_session(handle)
                return {'tcp_nodelay': actual}
            finally:
                client.close()
        for scope in ('database', 'service'):
            for enabled in (False, True):
                case(f'tcp/{scope}/{enabled}', lambda: socket_policy(
                    enabled, scope))

        def concurrent():
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(profile, *values, creation=False)
                           for values in profiles]
                return [future.result() for future in futures]
        case('concurrent-raw-default-isolation', concurrent)

        def precedence(scope, explicit):
            with relay((route['host'], route['port']), stalled=True) as link:
                values = {**selected, 'host': link.host, 'port': link.port,
                          'wire_config': 'ConnectionTimeout=2',
                          'timeout': 1 if explicit else None,
                          'credential_reference_id': 'owned-config',
                          'principal_reference': 'owned-principal'}
                client = _create_client(SimpleNamespace(
                    acquire_secret=lambda *_: SecretLease(password)))
                started = time.monotonic()
                try:
                    opening = (client.open_session if scope == 'database'
                               else client._connect_server)
                    try:
                        handle = opening({'route': values})
                    except RelationalClientError as error:
                        elapsed = time.monotonic() - started
                        expected = 1 if explicit else 2
                        assert expected * .8 <= elapsed < expected + .8
                        assert error.gds_codes and password not in str(error)
                        assert not client._connections
                        return {'explicit_timeout': values['timeout'],
                                'raw_timeout': 2, 'elapsed': elapsed}
                    else:
                        client.close_session(handle)
                        raise AssertionError('Silent connection admitted')
                finally:
                    client.close()
        for scope in ('database', 'service'):
            for explicit in (False, True):
                case(f'precedence/{scope}/{explicit}', lambda: precedence(
                    scope, explicit))
    finally:
        for obj, value in saved:
            obj.config.value = value
        assert before == [obj.get_config() for obj, _ in saved]
    result['driver_defaults_restored'] = True
    (evidence / 'config-matrix.json').write_text(
        json.dumps(result, indent=2) + '\n')
    assert len(result['checks']) == 14 and not result['failures']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path,
                        help='Use an isolated copy of a local 5.0.4 runtime')
    options = parser.parse_args()

    def qualify(*args):
        audit(options.source_root, args[-1])
        matrix(*args)

    if options.runtime_root:
        from tools.cdeadmin_firebird_local_fixture import run_local

        def qualify_local(native, admin, route, accounts, evidence, root):
            audit(options.source_root, evidence)
            matrix(native, admin, route, accounts, evidence,
                   creation_root=root)

        outcome = run_local(options.runtime_root, options.evidence_root,
                            qualify_local)
    else:
        outcome = run(options.evidence_root, selected_plugins=['Srp256'],
                      fixture_check=qualify)
    raise SystemExit(0 if outcome['complete'] else 1)
