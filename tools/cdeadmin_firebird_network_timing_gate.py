#!/usr/bin/env python3
"""FM-FB03-006 Linux native timing with owned TCP listeners and relays.

Windows/macOS teams repeat timing/traffic tests with native client libraries.
No OS keepalive or firewall settings are changed; relay silence is not a
physical network outage. Only packet lengths/times and plaintext op_dummy
recognition are retained, never credentials or wire payloads.
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

from tools.cdeadmin_firebird_inet_gate import relay
from tools.cdeadmin_firebird_password_gate import (
    run, _create_client, SecretLease,
)
from tools.cdeadmin_firebird_wire_crypt_gate import (
    check, _database_create_arguments, create_database, database_dsn,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@contextmanager
def observed_relay(upstream):
    stop, hold, sent = (threading.Event() for _ in range(3))
    records, sockets = [], set()
    lock = threading.Lock()

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            remote = socket.create_connection(upstream, timeout=3)
            remote.settimeout(None)
            with lock:
                sockets.update((self.request, remote))
            pending = bytearray()
            try:
                while not stop.is_set():
                    if pending and not hold.is_set():
                        self.request.sendall(pending)
                        pending.clear()
                    ready, _, _ = select.select(
                        [self.request, remote], [], [], 0.05)
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        if source is self.request:
                            with lock:
                                records.append((time.monotonic(), len(data),
                                                data == b'\0\0\0G'))
                            sent.set()
                            remote.sendall(data)
                        elif hold.is_set():
                            pending.extend(data)
                        else:
                            self.request.sendall(data)
            except OSError:
                pass  # Owned link teardown, never counted as native success.
            finally:
                remote.close()
                with lock:
                    sockets.difference_update((self.request, remote))

    server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever)
    worker.start()

    def snapshot():
        with lock:
            return list(records)

    try:
        yield SimpleNamespace(host='127.0.0.1', port=server.server_address[1],
                              hold=hold, sent=sent, records=snapshot)
    finally:
        stop.set()
        hold.clear()
        with lock:
            for connection in tuple(sockets):
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        server.shutdown()
        server.server_close()
        worker.join(5)
        assert not worker.is_alive()


def matrix(native, admin, route, accounts, evidence):
    import firebird.driver.core as core
    user, password = accounts['Srp'][0]
    selected = {**route, 'user': user,
                'credential_reference_id': 'owned-timing-secret',
                'principal_reference': 'owned-timing-principal'}
    results = {'checks': [], 'failures': []}

    def client():
        return _create_client(SimpleNamespace(
            acquire_secret=lambda *_: SecretLease(password)))

    def case(name, operation):
        try:
            results['checks'].append({'case': name, 'result': operation()})
        except Exception as error:
            results['failures'].append({
                'case': name, 'type': type(error).__name__,
                'lines': [frame.lineno for frame in traceback.extract_tb(
                    error.__traceback__)]})
        (evidence / 'timing-matrix.json').write_text(
            json.dumps(results, indent=2) + '\n')

    def failed_open(seconds, scope, stalled):
        owned = client()
        with relay((route['host'], route['port']), stalled=True) as link:
            with socket.socket() as refused:
                refused.bind(('127.0.0.1', 0))
                values = {**selected, 'timeout': seconds,
                          'host': link.host if stalled else '127.0.0.1',
                          'port': link.port if stalled else
                          refused.getsockname()[1]}
                started = time.monotonic()
                try:
                    if scope == 'create':
                        target = database_dsn(
                            '/var/lib/firebird/data/timing-' +
                            uuid.uuid4().hex + '.fdb',
                            values['host'], values['port'])
                        args = _database_create_arguments(
                            values, target, {}, native)
                        handle = create_database(native, core,
                                                 password=password, **args)
                    else:
                        opening = (owned.open_session if scope == 'database'
                                   else owned._connect_server)
                        handle = opening({'route': values})
                except (RelationalClientError, native.Error) as error:
                    elapsed = time.monotonic() - started
                    assert password not in str(error)
                    assert error.gds_codes
                    assert elapsed < seconds + 4
                    if stalled:
                        assert elapsed >= seconds * 0.65
                    assert not owned._connections
                    return {'seconds': seconds, 'elapsed': elapsed,
                            'native_codes': list(error.gds_codes),
                            'handles_released': True}
                else:
                    handle.close()
                    raise AssertionError('Silent/refused target accepted')
                finally:
                    owned.close()

    for scope in ('database', 'service', 'create'):
        for seconds in (0, 1, 2):
            case(f'handshake/{scope}/{seconds}', lambda: failed_open(
                seconds, scope, True))
        case(f'refused/{scope}', lambda: failed_open(1, scope, False))

    def concurrent():
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(failed_open, seconds, 'database', True)
                       for seconds in (1, 2)]
            return [future.result() for future in futures]
    case('independent-concurrent-timeouts', concurrent)

    def idle(interval, encrypted, scope):
        owned = client()
        with observed_relay((route['host'], route['port'])) as link:
            values = {**selected, 'host': link.host, 'port': link.port,
                      'dummy_packet_interval': interval, 'timeout': 2,
                      'wire_crypt': 'Required' if encrypted else 'Disabled'}
            handle = (owned.open_session if scope == 'database' else
                      owned._connect_server)({'route': values})
            try:
                if (scope == 'database' and
                        handle.main_transaction.is_active()):
                    handle.rollback()
                # A positive dummy interval must not become an application
                # idle disconnect, or a fabricated background heartbeat.
                time.sleep(0.2)
                before = len(link.records())
                threading.Event().wait(2.2)
                assert len(link.records()) == before
                link.hold.set()
                link.sent.clear()

                def query():
                    if scope == 'service':
                        handle.info._cache.clear()
                        assert '5.0.4' in handle.info.version
                    else:
                        with handle.cursor() as cursor:
                            cursor.execute('SELECT 1 FROM RDB$DATABASE')
                            assert cursor.fetchone()[0] == 1
                        handle.rollback()

                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(query)
                    try:
                        assert link.sent.wait(5)
                        baseline = time.monotonic()
                        threading.Event().wait(3.4)
                        events = [item for item in link.records()
                                  if item[0] > baseline + 0.2]
                        assert not future.done()
                        if interval:
                            assert len(events) >= 2
                            if not encrypted:
                                assert all(item[2] for item in events)
                        else:
                            assert not events
                    finally:
                        link.hold.clear()
                    future.result(timeout=10)
                return {'interval': interval, 'encrypted': encrypted,
                        'idle_client_packets': 0,
                        'waiting_client_packets': len(events),
                        'plaintext_dummy_verified': not encrypted and
                        bool(interval), 'resumed_without_reconnect': True}
            finally:
                owned.close()

    for scope in ('database', 'service'):
        for encrypted in (False, True):
            for interval in (0, 1):
                case(f'idle/{scope}/{encrypted}/{interval}', lambda: idle(
                    interval, encrypted, scope))
    for interval in (0, 1):
        case(f'transactions/{interval}', lambda: check(
            {**selected, 'timeout': 2, 'dummy_packet_interval': interval},
            password, 'Required', 'ChaCha64', True, True, 'ChaCha64'))
    assert len(results['checks']) == 23 and not results['failures']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, required=True)
    options = parser.parse_args()
    result = run(options.evidence_root, selected_plugins=['Srp256'],
                 fixture_check=matrix)
    raise SystemExit(0 if result['complete'] else 1)
