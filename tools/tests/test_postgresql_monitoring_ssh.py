"""Collector transport ownership, credential isolation and peer pinning."""
import base64
import io
from types import SimpleNamespace
from unittest.mock import Mock

import paramiko
import pytest

from tools.tests.test_monitoring_delegation import setup_grant
from pgadmin.cdeadmin.security.secrets import SecretLease
from pgadmin.cdeadmin.workspace.monitoring import MonitoringPolicy
from pgadmin.cdeadmin.providers.postgresql.monitoring import PostgreSQLMonitor
from pgadmin.cdeadmin.providers.postgresql.monitoring_ssh import (
    MonitoringSSHTunnel, MonitoringSSHError, validate_ssh_route,
)


@pytest.fixture(scope='module')
def peer():
    return paramiko.RSAKey.generate(2048)


def route(peer, authentication='password'):
    return {'database': 'qa', 'database_oid': 42, 'host': 'db.example.test',
            'port': 5432, 'user': 'collector', 'principal_reference': 'owner:1',
            'credential_reference_id': 'database',
            'credential_references': {'database_password': 'database',
                                      'ssh_password': 'ssh'},
            'ssh': {'host': 'gateway.example.test', 'port': 22,
                    'username': 'tunnel', 'remote_host': 'db.internal',
                    'remote_port': 5432, 'host_key_type': peer.get_name(),
                    'host_key': base64.b64encode(peer.asbytes()).decode(),
                    'authentication': authentication, 'keep_alive': 30}}


@pytest.mark.parametrize('dedicated', [False, True])
def test_sealed_ssh_grant_preserves_transport_with_dedicated_database_account(peer, dedicated):
    options = {'credentials': {'username': 'metrics', 'password': 'database-only'}} if dedicated else {}
    grant, policy, permissions, leases, _ = setup_grant(
        engine='postgresql', policy=MonitoringPolicy(1, 'endpoint', 'postgresql-database:42'),
        route=route(peer), **options)
    assert all(lease.closed for lease in leases)
    acquired = [call.args[-1] for call in permissions.acquire_secret.call_args_list]
    assert acquired == (['ssh_password'] if dedicated else ['database_password', 'ssh_password'])
    permissions.acquire_secret.side_effect = AssertionError('No browser credential access')
    factory = Mock(return_value=Mock())
    source = grant.open_source(policy, source_factory=factory)
    delegated, worker_route = factory.call_args.args
    for kind, ref in worker_route['credential_references'].items():
        with delegated.acquire_secret(ref, worker_route['principal_reference'], 'connect', kind) as lease:
            expected = b'database-only' if dedicated and kind == 'database_password' else b'test-only-password'
            assert lease.use(bytes) == expected
    source.close()


@pytest.mark.parametrize('authentication', ['password', 'private_key'])
def test_tunnel_pins_peer_disables_ambient_auth_and_releases_credentials(peer, authentication):
    selected = route(peer, authentication)
    pem = io.StringIO()
    peer.write_private_key(pem, password='key-passphrase')
    values = {'ssh_password': 'ssh-secret', 'ssh_private_key': pem.getvalue(),
              'ssh_private_key_password': 'key-passphrase'}
    if authentication == 'private_key':
        selected['credential_references'] = {key: key for key in values if key != 'ssh_password'}
    leases = []
    def acquire(ref, principal, purpose, kind):
        assert principal == 'owner:1' and purpose == 'connect'
        lease = SecretLease(values[kind]); leases.append(lease); return lease
    forwarder = Mock(is_active=True, local_bind_port=49152)
    factory = Mock(return_value=forwarder)
    owned = MonitoringSSHTunnel(SimpleNamespace(acquire_secret=acquire), selected, forwarder_factory=factory)
    assert owned.start() == 49152
    kwargs = factory.call_args.kwargs
    assert kwargs['ssh_host_key'] == peer
    assert kwargs['local_bind_address'] == ('127.0.0.1', 0)
    assert kwargs['remote_bind_address'] == ('db.internal', 5432)
    assert not kwargs['allow_agent'] and not kwargs['ssh_proxy_enabled']
    assert kwargs['host_pkey_directories'] == [] and kwargs['ssh_config_file'] is None
    assert all(lease.closed for lease in leases)
    assert forwarder.ssh_password is None and forwarder.ssh_pkeys == []
    forwarder.is_active = False
    owned.close()
    forwarder.stop.assert_called_once_with(force=True)


def test_failed_start_retains_transport_until_confirmed_release(peer):
    forwarder = Mock(is_active=True)
    forwarder.start.side_effect = RuntimeError('private credential must not escape')
    owned = MonitoringSSHTunnel(Mock(acquire_secret=lambda *args: SecretLease('secret')), route(peer),
                                forwarder_factory=Mock(return_value=forwarder))
    with pytest.raises(MonitoringSSHError, match='^Independent monitoring SSH connection failed$'):
        owned.start()
    with pytest.raises(MonitoringSSHError, match='release remains unconfirmed'):
        owned.close()
    assert owned._forwarder is forwarder
    forwarder.is_active = False
    owned.close()
    assert owned._forwarder is None


def test_libpq_preserves_tls_hostname_and_owns_release_order(peer, monkeypatch):
    selected = route(peer)
    selected['connection_params'] = {'sslmode': 'verify-full', 'hostaddr': '192.0.2.1'}
    owned = Mock(start=Mock(return_value=49152))
    monkeypatch.setattr('pgadmin.cdeadmin.providers.postgresql.monitoring_ssh.MonitoringSSHTunnel',
                        Mock(return_value=owned))
    events = []
    conn = Mock(info=SimpleNamespace(server_version=180003))
    conn.close.side_effect = lambda: events.append('database')
    owned.close.side_effect = [OSError('not released'), lambda: events.append('ssh')]
    connect = Mock(return_value=conn)
    monitor = PostgreSQLMonitor(Mock(acquire_secret=lambda *args: SecretLease('db-secret')), selected, connect=connect)
    monitor._open()
    assert connect.call_args.kwargs['host'] == 'db.example.test'
    assert connect.call_args.kwargs['hostaddr'] == '127.0.0.1'
    assert connect.call_args.kwargs['port'] == 49152
    with pytest.raises(OSError): monitor.close()
    assert events == ['database'] and monitor._tunnel is owned and not monitor._closed
    owned.close.side_effect = lambda: events.append('ssh')
    monitor.close()
    assert events == ['database', 'ssh'] and monitor._closed


@pytest.mark.parametrize('field,value', [('port', True), ('remote_port', 0), ('host_key', 'invalid'),
                                       ('keep_alive', -1), ('authentication', 'agent')])
def test_route_rejects_invalid_or_unadmitted_transports(peer, field, value):
    selected = route(peer)['ssh']; selected[field] = value
    with pytest.raises(MonitoringSSHError): validate_ssh_route(selected)


def ssh_registration(peer):
    server = SimpleNamespace(host='db.internal', port=5432, tunnel_host='gateway.example.test',
        tunnel_port=22, tunnel_username='tunnel', tunnel_authentication=0,
        tunnel_identity_file='', tunnel_password='encrypted', tunnel_keep_alive=30)
    manager = SimpleNamespace(**vars(server))
    manager.tunnel_object = SimpleNamespace(is_active=True, _remote_binds=[('db.internal', 5432)],
        _transport=Mock(is_authenticated=Mock(return_value=True),
                        get_remote_server_key=Mock(return_value=peer)))
    return server, manager


def test_host_freezes_observed_peer_and_does_not_keep_interactive_tunnel(peer, monkeypatch):
    from pgadmin.cdeadmin.workspace.postgresql_monitoring_host import PostgreSQLMonitoringHost
    monkeypatch.setattr('pgadmin.utils.master_password.get_crypt_key', lambda: (True, 'key'))
    monkeypatch.setattr('pgadmin.utils.crypto.decrypt', lambda value, key: b'tunnel-secret')
    server, manager = ssh_registration(peer)
    selected, secrets = PostgreSQLMonitoringHost._ssh_admission(server, manager)
    assert selected == route(peer)['ssh']
    assert secrets == {'ssh_password': b'tunnel-secret'}
    assert manager.tunnel_object not in selected.values()


@pytest.mark.parametrize('field,value', [('tunnel_host', 'changed'), ('tunnel_port', 2222),
    ('tunnel_username', 'other'), ('tunnel_authentication', 1), ('host', 'other-db'), ('port', 5433)])
def test_host_requires_reconnect_after_ssh_registration_changes(peer, field, value):
    from pgadmin.cdeadmin.workspace.postgresql_monitoring_host import PostgreSQLMonitoringHost
    server, manager = ssh_registration(peer)
    setattr(server, field, value)
    with pytest.raises(ValueError, match='Reconnect'):
        PostgreSQLMonitoringHost._ssh_admission(server, manager)


def test_host_reads_key_once_at_admission_and_rejects_changed_path(peer, monkeypatch, tmp_path):
    from pgadmin.cdeadmin.workspace.postgresql_monitoring_host import PostgreSQLMonitoringHost
    pem = io.StringIO(); peer.write_private_key(pem)
    path = tmp_path / 'owned-key'; path.write_bytes(pem.getvalue().encode('utf-8'))
    monkeypatch.setattr('pgadmin.utils.get_complete_file_path', lambda value: str(path))
    server, manager = ssh_registration(peer)
    server.tunnel_authentication = manager.tunnel_authentication = 1
    server.tunnel_identity_file = manager.tunnel_identity_file = 'owned-key'
    server.tunnel_password = manager.tunnel_password = None
    selected, secrets = PostgreSQLMonitoringHost._ssh_admission(server, manager)
    assert selected['authentication'] == 'private_key'
    assert secrets['ssh_private_key'] == pem.getvalue().encode()
    path.unlink()
    assert secrets['ssh_private_key'] == pem.getvalue().encode()
    server.tunnel_identity_file = 'replacement-key'
    with pytest.raises(ValueError, match='Reconnect'):
        PostgreSQLMonitoringHost._ssh_admission(server, manager)


@pytest.mark.parametrize('session_backed,succeeds', [(True, True), (True, False), (False, True)])
def test_native_manager_retains_only_successful_interactive_encrypted_credential(monkeypatch, session_backed, succeeds):
    from flask import Flask
    from pgadmin.utils.driver.psycopg3 import server_manager as native
    app = Flask(__name__)
    monkeypatch.setattr(native, 'current_user', SimpleNamespace(id=1))
    monkeypatch.setattr(native, 'User', Mock())
    monkeypatch.setattr(native, 'get_crypt_key', lambda: (True, 'crypt-key'))
    monkeypatch.setattr(native, 'decrypt', lambda value, key: b'plain-test-secret')
    monkeypatch.setattr(native, 'gettext', lambda value: value)
    forwarder = Mock(local_bind_port=49152)
    if not succeeds:
        forwarder.start.side_effect = native.BaseSSHTunnelForwarderError('owned auth refusal')
    factory = Mock(return_value=forwarder)
    monkeypatch.setattr(native, 'SSHTunnelForwarder', factory)
    manager = SimpleNamespace(session_backed=session_backed, delegated_owner_id=1,
        tunnel_authentication=0, tunnel_host='localhost', tunnel_port=22,
        tunnel_username='fixture', tunnel_keep_alive=5, host='db.internal', port=5432,
        tunnel_password='prior-encrypted', tunnel_created=False)
    supplied = b'new-encrypted' if session_backed else 'delegated-plaintext'
    with app.app_context():
        status, _ = native.ServerManager.create_ssh_tunnel(manager, supplied)
    assert status is succeeds
    assert manager.tunnel_password == (supplied if session_backed and succeeds else 'prior-encrypted')
    assert factory.call_args.kwargs['ssh_password'] == ('plain-test-secret' if session_backed else supplied)
