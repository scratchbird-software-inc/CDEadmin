#!/usr/bin/env python3
"""FM-FB03-001/002 Linux INET/INET4/INET6 and owned network failures.

Windows/macOS teams must repeat resolver ordering, alternate addresses,
native timeout/release and browser recovery with their own client libraries.
Relays simulate network interruption, not physical remote-machine failure.
IPv6 listeners are IPv6-only; native remote server tests are in the companion
IPv6 remote gate. Interface-scoped address syntax has separate unit coverage.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
import select
import socket
import socketserver
import threading
import time
import traceback
from types import SimpleNamespace
import uuid

from tools.cdeadmin_firebird_password_gate import (
    run as native_run, _create_client, SecretLease,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.providers.firebird.provider import ADMINISTRATION
from pgadmin.cdeadmin.providers.firebird.connection_strings import server_host
from tools.cdeadmin_firebird_native_opening_gate import (
    docker, published_port, OWNER,
)


@contextmanager
def relay(upstream, host='127.0.0.10', stalled=False):
    """Only listeners/sockets owned by this context can be interrupted."""
    stopping = threading.Event()
    sockets = set()
    lock = threading.Lock()
    accepted = []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            remote = None
            with lock:
                sockets.add(self.request)
                accepted.append(1)
            try:
                if stalled:
                    stopping.wait(15)
                    return
                remote = socket.create_connection(upstream, timeout=3)
                with lock:
                    sockets.add(remote)
                while not stopping.is_set():
                    ready, _, _ = select.select(
                        [self.request, remote], [], [], 0.1)
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        (remote if source is self.request else
                         self.request).sendall(data)
            except OSError:
                # Expected when the owned link is cut or the client times out.
                pass
            finally:
                if remote is not None:
                    remote.close()
                with lock:
                    sockets.discard(self.request)
                    sockets.discard(remote)

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = False
        address_family = socket.AF_INET6 if ':' in host else socket.AF_INET

        def server_bind(self):
            if self.address_family == socket.AF_INET6:
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY,
                                       1)
            super().server_bind()

    server = Server((host, 0), Handler)
    worker = threading.Thread(target=server.serve_forever)
    worker.start()

    def cut():
        stopping.set()
        with lock:
            for connection in tuple(sockets):
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    try:
        yield SimpleNamespace(host=host, port=server.server_address[1],
                              cut=cut, accepted=accepted)
    finally:
        cut()
        server.shutdown()
        server.server_close()
        worker.join(5)
        assert not worker.is_alive()


def native_cases(native, admin, route, accounts, evidence, *, ipv6=False):
    user, password = accounts['Srp'][0]
    admin.execute_immediate('CREATE TABLE INET_MARKER (ID INTEGER)')
    admin.execute_immediate('GRANT ALL ON INET_MARKER TO "' + user + '"')
    admin.commit()
    report = {'checks': [], 'failures': []}

    def client():
        return _create_client(SimpleNamespace(
            acquire_secret=lambda *_: SecretLease(password)))

    def selected(**values):
        return {**route, 'user': user,
                'credential_reference_id': 'owned-inet-secret',
                'principal_reference': 'owned-inet-principal', **values}

    def case(name, operation):
        try:
            detail = operation() or {}
            report['checks'].append({'case': name, **detail})
        except Exception as error:
            report['failures'].append({
                'case': name, 'type': type(error).__name__,
                'lines': [frame.lineno for frame in
                          traceback.extract_tb(error.__traceback__)]})
        (evidence / 'inet-native.json').write_text(
            json.dumps(report, indent=2) + '\n')

    def attach(values):
        owned = client()
        try:
            handle = owned.open_session({'route': values})
            with handle.cursor() as cursor:
                cursor.execute("SELECT RDB$GET_CONTEXT('SYSTEM', 'DB_NAME'), "
                               'CURRENT_USER FROM RDB$DATABASE')
                path, principal = cursor.fetchone()
                assert path == route['database'] and principal == user
            handle.rollback()
            owned.close_session(handle)
            service = owned._connect_server({'route': values})
            assert '5.0.4' in service.info.version
            owned.close_session(service)
            assert not owned._connections
            return {'database_and_service_identity': True}
        finally:
            owned.close()

    upstream = (route['host'], route['port'])
    candidates = docker('ps', '--filter', 'label=cdeadmin-owned-gate=' + OWNER,
                        '--format', '{{.ID}}', '--no-trunc').decode().split()
    matches = []
    for item in candidates:
        try:
            port = published_port(item)
        except RuntimeError:
            # Concurrent owned client containers have no published server
            # port and may already have exited. Never select those fixtures.
            continue
        if port == route['port']:
            matches.append(item)
    assert len(matches) == 1
    container = matches[0]
    details = json.loads(docker('inspect', container))[0]
    assert details['Config']['Labels']['cdeadmin-owned-gate'] == OWNER
    bridge = next(value['IPAddress'] for value in
                  details['NetworkSettings']['Networks'].values()
                  if value['IPAddress'])
    bridge_reachable = False
    engine_os = docker('info', '--format', '{{.OperatingSystem}}').decode()
    # Docker Desktop bridge addresses belong to its VM. Do not send probes
    # for those addresses onto an unrelated host LAN route.
    if 'Docker Desktop' not in engine_os:
        try:
            with socket.create_connection((bridge, 3050), timeout=0.5):
                bridge_reachable = True
        except OSError:
            pass
    report['direct_bridge_reachable'] = bridge_reachable
    alias = 'owned_inet_' + uuid.uuid4().hex
    docker('exec', '-i', container, 'tee', '-a',
           '/opt/firebird/databases.conf',
           input_data=(
               '\n' + alias + ' = ' + route['database'] + '\n').encode())
    protocols = ('INET', 'INET6') if ipv6 else ('INET', 'INET4')
    with relay(upstream, host='::1' if ipv6 else '127.0.0.10') as link:
        for protocol in protocols:
            addresses = ([('::1', link.port), ('[::1]', link.port),
                          ('0:0:0:0:0:0:0:1', link.port),
                          ('localhost', link.port)] if ipv6 else
                         [(route['host'], route['port']),
                          ('localhost', route['port']),
                          (link.host, link.port)])
            if bridge_reachable and not ipv6:
                addresses.append((bridge, 3050))
            for host, port in addresses:
                values = selected(host=host, port=port, protocol=protocol)
                case(f'{protocol}-{host}', lambda v=values: attach(v))
                legacy = f'{server_host(host)}/{port}:' + route['database']
                case(f'{protocol}-{host}-legacy-database',
                     lambda v={**values, 'database': legacy}: attach(v))
            case(protocol + '-server-alias', lambda p=protocol: attach(
                selected(database=alias, protocol=p,
                         host=link.host, port=link.port)))

            def lifecycle():
                owned = client()
                path = ('/var/lib/firebird/data/inet_' +
                        uuid.uuid4().hex + '.fdb')
                values = selected(protocol=protocol, host=link.host,
                                  port=link.port)
                try:
                    plan = ADMINISTRATION.plan({
                        '_provider_route': values, 'resource_kind': 'database',
                        'operation_id': 'create', 'target_resource': None,
                        'draft': {'database_path': path}})
                    assert ADMINISTRATION.apply(owned, plan)['accepted']
                    handle = owned.open_session({'route': {
                        **values, 'database': path}})
                    # Native drop is exercised only for this unique fixture.
                    handle.drop_database()
                    owned.close_session(handle)
                    return {'create_open_drop': True}
                finally:
                    owned.close()

            case(protocol + '-database-lifecycle', lifecycle)

        def concurrent():
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda protocol: attach(selected(
                    host=link.host, port=link.port, protocol=protocol)),
                    list(protocols) * 2))
            assert len(results) == 4
            return {'independent_connections': 4}

        case('concurrent-address-family-isolation', concurrent)

        if ipv6:
            from tools.cdeadmin_firebird_password_gate import reject_password
            case('ipv6-wrong-password', lambda: reject_password(
                selected(host=link.host, port=link.port, protocol='INET6'),
                user, 'WRONG-' + password, 'Srp256'))

            def wrong_family(protocol, host, port):
                owned = client()
                try:
                    for opening in (owned.open_session, owned._connect_server):
                        try:
                            opening({'route': selected(
                                protocol=protocol, host=host, port=port)})
                        except RelationalClientError:
                            pass
                        else:
                            raise AssertionError('Address family substituted')
                    assert not owned._connections
                finally:
                    owned.close()

            case('inet4-cannot-use-ipv6', lambda: wrong_family(
                'INET4', link.host, link.port))
            case('inet6-cannot-use-ipv4', lambda: wrong_family(
                'INET6', route['host'], route['port']))

    for protocol in protocols:
        for stalled in (False, True):
            with relay(upstream, host='::1' if ipv6 else '127.0.0.10',
                       stalled=stalled) as link:
                # A bound but non-listening socket makes refusal deterministic
                # without racing another process for a recently freed port.
                with socket.socket(socket.AF_INET6 if ipv6 else
                                   socket.AF_INET) as refused:
                    refused.bind(('::1' if ipv6 else '127.0.0.1', 0))
                    values = selected(
                        protocol=protocol, timeout=1,
                        host=link.host if stalled or ipv6 else '127.0.0.1',
                        port=link.port if stalled else
                        refused.getsockname()[1])

                    def rejected():
                        owned = client()
                        started = time.monotonic()
                        try:
                            for opening in (owned.open_session,
                                            owned._connect_server):
                                try:
                                    opening({'route': values})
                                except RelationalClientError as error:
                                    assert password not in str(error)
                                else:
                                    raise AssertionError('Bad link accepted')
                            assert not owned._connections
                            assert time.monotonic() - started < 12
                            return {'bounded_database_service_failure': True}
                        finally:
                            owned.close()

                    case(f'{protocol}-' + (
                        'handshake-timeout' if stalled else 'refused'),
                        rejected)

        def severed():
            owned = client()
            with relay(upstream, host='::1' if ipv6 else '127.0.0.10') as link:
                try:
                    handle = owned.open_session({'route': selected(
                        protocol=protocol, host=link.host, port=link.port)})
                    attachment_id = handle.info.id
                    handle.execute_immediate(
                        'INSERT INTO INET_MARKER VALUES (1)')
                    link.cut()
                    try:
                        owned.execute(handle, {
                            'source': 'SELECT ID FROM INET_MARKER'})
                    except RelationalClientError:
                        pass
                    else:
                        raise AssertionError('Severed connection succeeded')
                    assert len(link.accepted) == 1  # No automatic reconnect.
                    # An error is not a rollback receipt. Observe the server
                    # independently after it processes the disconnected link.
                    for attempt in range(50):
                        if admin.main_transaction.is_active():
                            admin.rollback()
                        with admin.cursor() as cursor:
                            cursor.execute(
                                'SELECT COUNT(*) FROM MON$ATTACHMENTS '
                                'WHERE MON$ATTACHMENT_ID = ?', [attachment_id])
                            remaining = cursor.fetchone()[0]
                            cursor.execute('SELECT COUNT(*) FROM INET_MARKER')
                            count = cursor.fetchone()[0]
                        if remaining == 0:
                            break
                        time.sleep(0.1)
                    assert remaining == 0 and count == 0
                finally:
                    owned.close()
            host = '::1' if ipv6 else '127.0.0.10'
            with relay(upstream, host=host) as fresh:
                attach(selected(protocol=protocol, host=fresh.host,
                                port=fresh.port))
            return {'no_reconnect_or_replay': True,
                    'independent_committed_rows': 0,
                    'explicit_fresh_connection': True}

        case(protocol + '-established-link-loss', severed)

    (evidence / 'inet-native.json').write_text(
        json.dumps(report, indent=2) + '\n')
    expected = 30 if ipv6 else 27 if bridge_reachable else 23
    assert len(report['checks']) == expected
    assert not report['failures']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', required=True, type=Path)
    parser.add_argument('--ipv6', action='store_true',
                        help='Qualify INET/INET6 through IPv6-only listeners')
    options = parser.parse_args()
    outcome = native_run(options.evidence_root, selected_plugins=['Srp256'],
                         fixture_check=lambda *args: native_cases(
                             *args, ipv6=options.ipv6))
    raise SystemExit(0 if outcome['complete'] else 1)
