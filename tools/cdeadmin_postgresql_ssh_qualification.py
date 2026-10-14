"""Real owned SSH forwarding and PostgreSQL monitoring qualification.

The in-process SSH fixture only forwards to the explicitly supplied test server.
It never installs a daemon, changes system configuration or persists private keys.
"""
import base64
import io
import os
import select
import socket
import threading
from types import SimpleNamespace

import paramiko
import psycopg


class ForwardingPeer:
    def __init__(self, destination):
        self.destination = destination
        self.host_key = paramiko.RSAKey.generate(2048)
        self.client_key = paramiko.RSAKey.generate(2048)
        self.password = os.urandom(24).hex()
        self.stop = threading.Event()
        self.transports = []
        self.threads = []
        self.errors = []
        self.lock = threading.Lock()
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(8)
        self.listener.settimeout(.2)
        self.port = self.listener.getsockname()[1]
        self._spawn(self._accept)

    def _spawn(self, function, *args):
        thread = threading.Thread(target=function, args=args, daemon=True)
        with self.lock:
            self.threads.append(thread)
        thread.start()

    def _accept(self):
        while not self.stop.is_set():
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if self.stop.is_set(): return
                raise
            self._spawn(self._serve, conn)

    def _serve(self, conn):
        peer = self
        class Admission(paramiko.ServerInterface):
            def get_allowed_auths(self, username): return 'password,publickey'
            def check_auth_password(self, username, password):
                return paramiko.AUTH_SUCCESSFUL if username == 'fixture' and password == peer.password else paramiko.AUTH_FAILED
            def check_auth_publickey(self, username, key):
                return paramiko.AUTH_SUCCESSFUL if username == 'fixture' and key == peer.client_key else paramiko.AUTH_FAILED
            def check_channel_direct_tcpip_request(self, chanid, origin, destination):
                return paramiko.OPEN_SUCCEEDED if destination == peer.destination else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
        transport = paramiko.Transport(conn)
        with self.lock: self.transports.append(transport)
        try:
            transport.add_server_key(self.host_key)
            transport.start_server(server=Admission())
            while not self.stop.is_set() and transport.is_active():
                channel = transport.accept(.2)
                if channel is not None: self._spawn(self._forward, channel)
        except (EOFError, OSError, paramiko.SSHException):
            # Intentional pin mismatch and forced disconnect are exercised.
            pass
        finally:
            transport.close()
            conn.close()

    def _forward(self, channel):
        remote = None
        try:
            remote = socket.create_connection(self.destination, timeout=5)
            while not self.stop.is_set():
                ready, _, _ = select.select([channel, remote], [], [], .2)
                for source in ready:
                    value = source.recv(65536)
                    if not value: return
                    (remote if source is channel else channel).sendall(value)
        except (OSError, EOFError):
            pass
        finally:
            channel.close()
            if remote: remote.close()

    def close(self):
        self.stop.set()
        self.listener.close()
        for transport in self.transports: transport.close()
        # Closing the listener first prevents creation of new transport threads.
        index = 0
        while index < len(self.threads):
            thread = self.threads[index]
            thread.join(5)
            assert not thread.is_alive(), 'Owned SSH fixture thread did not stop'
            index += 1


def qualify(route, password, receipt):
    from pgadmin.cdeadmin.providers.postgresql.monitoring import PostgreSQLMonitor
    from pgadmin.cdeadmin.providers.postgresql.monitoring_ssh import MonitoringSSHTunnel, MonitoringSSHError
    from pgadmin.cdeadmin.report_scheduler.crypto import WorkerKeyRing
    from pgadmin.cdeadmin.security.secrets import SecretLease
    from pgadmin.cdeadmin.workspace.monitoring import MonitoringPolicy
    from pgadmin.cdeadmin.workspace.monitoring_delegation import MonitoringGrant, MonitoringGrantError
    peer = ForwardingPeer((route['host'], route['port']))
    owned = []
    try:
        with psycopg.connect(host=route['host'], port=route['port'], user=route['user'], password=password,
                dbname=route['database'], autocommit=True, **route.get('connection_params', {})) as observer:
            oid = int(observer.execute('SELECT oid FROM pg_database WHERE datname=current_database()').fetchone()[0])
            key_text = io.StringIO()
            peer.client_key.write_private_key(key_text, password='ephemeral-key-passphrase')
            values = {'database_password': password, 'ssh_password': peer.password,
                      'ssh_private_key': key_text.getvalue(), 'ssh_private_key_password': 'ephemeral-key-passphrase'}
            permissions = SimpleNamespace(acquire_secret=lambda ref, principal, purpose, kind: SecretLease(values[kind]))
            for mode in ('password', 'private_key'):
                selected = {**route, 'database_oid': oid, 'principal_reference': 'owner:1',
                            'credential_reference_id': 'database',
                            'credential_references': {'database_password': 'database'},
                            'ssh': {'host': '127.0.0.1', 'port': peer.port, 'username': 'fixture',
                                    'remote_host': route['host'], 'remote_port': route['port'],
                                    'host_key_type': peer.host_key.get_name(), 'host_key': peer.host_key.get_base64(),
                                    'authentication': mode, 'keep_alive': 5}}
                kinds = ['ssh_password'] if mode == 'password' else ['ssh_private_key', 'ssh_private_key_password']
                selected['credential_references'].update({kind: kind for kind in kinds})
                interactive = MonitoringSSHTunnel(permissions, selected); owned.append(interactive)
                interactive_port = interactive.start()
                browser = psycopg.connect(host='127.0.0.1', port=interactive_port, user=route['user'],
                    password=password, dbname=route['database'], autocommit=True, **route.get('connection_params', {}))
                owned.append(browser)
                policy = MonitoringPolicy(1, 'owned-ssh', 'postgresql-database:'+str(oid), interval_seconds=15)
                keys = WorkerKeyRing({'owned': base64.b64encode(os.urandom(32)).decode()}, 'owned')
                grant = MonitoringGrant.issue(policy, selected, 'ssh-fixture', permissions, keys,
                    lambda *args: True, engine='postgresql',
                    credentials={'username': route['user'], 'password': password})
                collector = grant.open_source(policy, source_factory=PostgreSQLMonitor); owned.append(collector)
                first = collector.sample()
                assert first['status'] == 'available' and first['transaction_completed'], first
                assert int(first['identity']['collector_pid']) != browser.info.backend_pid
                browser.close(); interactive.close()
                second = collector.sample()
                assert second['transaction_completed'] and second['source_epoch'] == first['source_epoch']
                assert collector._source._connection.info.transaction_status == 0
                # A real attachment loss requires a fresh independent SSH+DB pair.
                pid = int(second['identity']['collector_pid'])
                assert observer.execute('SELECT pg_terminate_backend(%s)', (pid,)).fetchone()[0]
                failed = collector.sample()
                assert not failed['transaction_completed'] and failed['status'] == 'unavailable'
                recovered = collector.sample()
                assert recovered['transaction_completed'] and recovered['source_epoch'] != first['source_epoch']
                assert int(recovered['identity']['collector_pid']) != pid
                tunnel = collector._source._tunnel._forwarder
                grant.revoke()
                try:
                    collector.sample()
                except MonitoringGrantError:
                    pass
                else:
                    raise AssertionError('Revoked grant accepted a sample')
                collector.close()
                assert not tunnel.is_active
                receipt['checks'].append('native-ssh-'+mode+'-independent-monitoring-reconnect-revocation-and-release')
            bad = {**selected, 'ssh': {**selected['ssh'], 'host_key': peer.client_key.get_base64()}}
            wrong = MonitoringSSHTunnel(permissions, bad); owned.append(wrong)
            try:
                wrong.start()
            except MonitoringSSHError:
                pass
            else:
                raise AssertionError('Mismatched SSH peer key accepted')
            wrong.close()
            receipt['checks'].append('native-ssh-monitoring-peer-key-mismatch-refused')
    finally:
        for item in reversed(owned): item.close()
        peer.close()
