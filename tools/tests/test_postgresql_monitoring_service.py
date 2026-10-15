"""Service monitoring freezes a native endpoint and seals credentials separately."""
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.workspace.postgresql_monitoring_host import PostgreSQLMonitoringHost


def connection():
    info = NS(host='resolved.example', hostaddr='192.0.2.10', port=55432,
        dbname='selected', user='native_user', password='owned-service-secret',
        get_parameters=Mock(return_value={'service': 'alias', 'host': 'first,second',
            'port': '5432,55432', 'user': 'native_user', 'dbname': 'selected',
            'sslmode': 'verify-full', 'sslrootcert': '/ca.pem', 'application_name': 'Explorer'}))
    return NS(conn=NS(info=info), db='selected', password=None, connected=lambda: True)


def test_resolved_peer_replaces_service_alias_and_multihost_list():
    route = PostgreSQLMonitoringHost._resolved_service(connection())
    assert route['host'] == 'resolved.example' and route['port'] == 55432
    assert route['connection_params'] == {'sslmode': 'verify-full', 'sslrootcert': '/ca.pem', 'hostaddr': '192.0.2.10'}
    assert route['user'] == 'native_user' and route['database'] == 'selected'
    assert 'alias' not in repr(route) and 'owned-service-secret' not in repr(route)


def test_unknown_service_settings_are_not_silently_discarded():
    conn = connection()
    conn.conn.info.get_parameters.return_value['sslpassword'] = 'another-secret'
    with pytest.raises(ValueError, match='not yet admitted'):
        PostgreSQLMonitoringHost._resolved_service(conn)


def test_selected_database_mismatch_refused():
    conn = connection();conn.db = 'other'
    with pytest.raises(ValueError, match='selected database'):
        PostgreSQLMonitoringHost._resolved_service(conn)


def test_current_service_password_is_a_lease_not_route_metadata(monkeypatch):
    from pgadmin.utils.driver.registry import DriverRegistry
    conn = connection()
    manager = NS(version=180003, connection=Mock(return_value=conn), user='', password=None)
    monkeypatch.setattr(DriverRegistry, 'get', lambda _: NS(connection_manager=lambda _: manager))
    monkeypatch.setattr('pgadmin.utils.master_password.get_crypt_key', lambda: (False, None))
    server = NS(host=None, port=None, role='', service='alias', use_ssh_tunnel=False,
        kerberos_conn=False, password=None, connection_params={}, endpoint_profile=NS(
            id='endpoint', profile_generation='one', cache_namespace='cache'))
    host = object.__new__(PostgreSQLMonitoringHost)
    host._owned_server = lambda *_: server
    admitted, permissions = host._admit(1, 7, 'postgresql-database:42', False)
    assert admitted['route']['database_oid'] == 42
    assert admitted['route']['host'] == 'resolved.example'
    assert 'owned-service-secret' not in repr(admitted)
    with permissions.acquire_secret(None) as lease:
        assert lease.use(lambda value: bytes(value)) == b'owned-service-secret'
    _, dedicated = host._admit(1, 7, 'postgresql-database:42', True)
    assert dedicated is None


def test_native_effective_certificate_mode_is_preserved():
    conn = connection()
    conn.conn.info.get_parameters.return_value['sslcertmode'] = 'allow'
    route = PostgreSQLMonitoringHost._resolved_service(conn)
    assert route['connection_params']['sslcertmode'] == 'allow'


def test_native_host_keepalive_policy_is_preserved():
    conn = connection()
    options = {'keepalives': '1', 'keepalives_idle': '30', 'keepalives_interval': '10', 'keepalives_count': '3'}
    conn.conn.info.get_parameters.return_value.update(options)
    route = PostgreSQLMonitoringHost._resolved_service(conn)
    assert all(route['connection_params'][key] == value for key,value in options.items())


@pytest.mark.parametrize('key', ['sslcert', 'sslkey', 'sslcrl', 'sslcrldir', 'sslrootcert'])
def test_direct_certificate_paths_use_authorized_native_storage(monkeypatch, key):
    resolver = Mock(return_value='/authorized/storage/certificate')
    monkeypatch.setattr('pgadmin.utils.get_complete_file_path', resolver)
    original = {key: 'uploaded/certificate', 'sslmode': 'verify-full'}
    options = PostgreSQLMonitoringHost._direct_options(original)
    resolver.assert_called_once_with('uploaded/certificate')
    assert options == {key: '/authorized/storage/certificate', 'sslmode': 'verify-full'}
    assert original[key] == 'uploaded/certificate'


def test_system_ca_is_not_resolved_as_a_user_file(monkeypatch):
    resolver = Mock(side_effect=AssertionError('must not resolve system CA'))
    monkeypatch.setattr('pgadmin.utils.get_complete_file_path', resolver)
    assert PostgreSQLMonitoringHost._direct_options({'sslrootcert': 'system'}) == {'sslrootcert': 'system'}
    resolver.assert_not_called()


def test_unauthorized_certificate_path_aborts_admission(monkeypatch):
    monkeypatch.setattr('pgadmin.utils.get_complete_file_path',
                        Mock(side_effect=PermissionError('outside authorized storage')))
    with pytest.raises(PermissionError):
        PostgreSQLMonitoringHost._direct_options({'sslkey': '../other-user/key'})


def test_service_tls_password_is_extracted_before_route_capture():
    conn = connection()
    conn.conn.info.get_parameters.return_value['sslpassword'] = 'owned-tls-secret'
    secrets = {}
    route = PostgreSQLMonitoringHost._resolved_service(conn, secrets=secrets)
    assert secrets == {'tls_private_key_password': 'owned-tls-secret'}
    assert 'owned-tls-secret' not in repr(route)
    assert 'sslpassword' not in route['connection_params']


@pytest.mark.parametrize('dedicated', [False, True])
def test_tls_password_sealed_independently_of_database_credentials(dedicated):
    from tools.tests.test_monitoring_delegation import setup_grant
    from pgadmin.cdeadmin.workspace.monitoring import MonitoringPolicy
    options = {'credentials': {'username': 'metrics', 'password': 'database-only'}} if dedicated else {}
    route = {'database': 'qa', 'database_oid': 42, 'host': 'localhost', 'port': 5432, 'user': 'qa',
             'principal_reference': 'owner:1', 'credential_reference_id': 'db',
             'credential_references': {'tls_private_key_password': 'tls'}}
    grant, policy, permissions, leases, _ = setup_grant(engine='postgresql',
        policy=MonitoringPolicy(1, 'endpoint', 'postgresql-database:42'), route=route, **options)
    assert all(lease.closed for lease in leases)
    factory = Mock(return_value=Mock())
    source = grant.open_source(policy, source_factory=factory)
    delegated, worker_route = factory.call_args.args
    with delegated.acquire_secret(worker_route['credential_references']['tls_private_key_password'],
            worker_route['principal_reference'], 'connect', 'tls_private_key_password') as lease:
        assert lease.use(bytes) == b'test-only-password'
    source.close()
    grant.revoke()


@pytest.mark.parametrize('fail', [False, True])
def test_tls_lease_lives_only_during_connection_attempt(fail):
    from pgadmin.cdeadmin.security.secrets import SecretLease
    from pgadmin.cdeadmin.providers.postgresql.monitoring import PostgreSQLMonitor
    leases = []
    def acquire(reference, principal, purpose, kind):
        lease = SecretLease('tls-secret' if kind == 'tls_private_key_password' else 'db-secret')
        leases.append(lease)
        return lease
    def connect(**kwargs):
        assert kwargs['sslpassword'] == 'tls-secret' and kwargs['password'] == 'db-secret'
        assert all(not lease.closed for lease in leases)
        if fail:
            raise OSError('owned connection failure')
        return Mock(info=NS(server_version=180003))
    route = {'database': 'qa', 'database_oid': 42, 'host': 'localhost', 'port': 5432, 'user': 'qa',
             'principal_reference': 'owner:1', 'credential_reference_id': 'db',
             'credential_references': {'tls_private_key_password': 'tls'}}
    monitor = PostgreSQLMonitor(NS(acquire_secret=acquire), route, connect=connect)
    if fail:
        with pytest.raises(OSError): monitor._open()
    else:
        monitor._open()
    assert len(leases) == 2 and all(lease.closed for lease in leases)
    assert 'tls-secret' not in repr(monitor.route)
    monitor.close()


@pytest.mark.parametrize('overridden_password', [False, True])
def test_native_display_dsn_masks_tls_and_database_passwords(overridden_password):
    from pgadmin.utils.driver.psycopg3.server_manager import ServerManager
    from psycopg.conninfo import conninfo_to_dict
    parameters = {'sslpassword': 'private-key-secret', 'sslmode': 'verify-full'}
    if overridden_password:
        parameters['password'] = 'parameter-db-secret'
    manager = NS(host='localhost', port=5432, use_ssh_tunnel=False,
                 service=None, connection_params=parameters)
    actual = ServerManager.create_connection_string(manager, 'qa', 'user', 'db-secret')
    parsed = conninfo_to_dict(actual)
    assert parsed['sslpassword'] == 'private-key-secret'
    assert parsed['password'] == ('parameter-db-secret' if overridden_password else 'db-secret')
    display = conninfo_to_dict(manager.display_connection_string)
    assert display['sslpassword'] == display['password'] == 'xxxxxxx'
    assert 'secret' not in manager.display_connection_string
    assert display['sslmode'] == 'verify-full'


def test_kerberos_registration_can_admit_explicit_password_collector_without_ticket(monkeypatch):
    from pgadmin.utils.driver.registry import DriverRegistry
    conn = connection()
    manager = NS(version=180003, connection=Mock(return_value=conn), user='ticket_user', password=None)
    monkeypatch.setattr(DriverRegistry, 'get', lambda _: NS(connection_manager=lambda _: manager))
    server = NS(host='localhost', port=5432, role='', service=None, use_ssh_tunnel=False,
        kerberos_conn=True, password=None, connection_params={'sslmode': 'verify-full', 'gssencmode': 'prefer'},
        endpoint_profile=NS(id='endpoint', profile_generation='one', cache_namespace='cache'))
    host = object.__new__(PostgreSQLMonitoringHost)
    host._owned_server = lambda *_: server
    with pytest.raises(ValueError, match='Kerberos'):
        host._admit(1, 7, 'postgresql-database:42', False)
    admitted, permissions = host._admit(1, 7, 'postgresql-database:42', True)
    assert permissions is None
    options = admitted['route']['connection_params']
    assert options['gssencmode'] == 'disable'
    assert options['require_auth'] == 'password,md5,scram-sha-256'
    assert options['sslmode'] == 'verify-full'
    assert server.connection_params['gssencmode'] == 'prefer'
