"""PostgreSQL host authorization and independent sealed credential lifecycle."""
import base64
import os
from types import SimpleNamespace
from unittest.mock import Mock
from flask import Flask
import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.security.secrets import SecretLease
from pgadmin.cdeadmin.workspace.monitoring_host import MonitoringHost
from pgadmin.cdeadmin.workspace.postgresql_monitoring_host import PostgreSQLMonitoringHost


def make_host(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config.update(CDEADMIN_MONITORING_PROCESS_MODE='single',
        CDEADMIN_MONITORING_WORKER_KEYS={'k': base64.b64encode(os.urandom(32)).decode()},
        CDEADMIN_MONITORING_WORKER_ACTIVE_KEY_ID='k',
        CDEADMIN_MONITORING_LOCK_PATH=str(tmp_path/'monitor.lock'))
    shared = MonitoringHost(app, Mock())
    host = PostgreSQLMonitoringHost(app, shared)
    app.extensions['cdeadmin_postgresql_monitoring_host'] = host
    server = SimpleNamespace(name='PG', password='encrypted', host='localhost', port=5432,
        endpoint_profile=SimpleNamespace(id='endpoint', profile_generation='one', cache_namespace='cache'))

    def owned(owner, sid):
        if owner != 1 or sid != 7:
            raise PermissionError('Not owned')
        return server

    def admit(owner, sid, target, dedicated):
        owned(owner, sid)
        return {'endpoint_id': 'endpoint', 'generation': 'one',
                'configuration': host._configuration(server),
                'route': {'host': 'localhost', 'port': 5432, 'database': 'qa', 'database_oid': 42,
                          'user': 'owner', 'principal_reference': 'user:1', 'credential_reference_id': 'current'}}, \
            SimpleNamespace(acquire_secret=lambda *_: SecretLease('test-password'))

    monkeypatch.setattr(host, '_owned_server', owned)
    monkeypatch.setattr(host, '_admit', admit)
    monkeypatch.setattr('pgadmin.cdeadmin.workspace.monitoring_delegation.MonitoringGrant.open_source',
                        lambda *_: Mock(sample=Mock(return_value={'status': 'available'})))
    return host, shared, server


def test_disabled_read_does_not_connect_or_lock(tmp_path, monkeypatch):
    host, shared, _ = make_host(tmp_path, monkeypatch)
    try:
        assert host.snapshot(1, 7, 'postgresql-database:42')['state'] == 'disabled'
        assert host.ownership is shared.ownership and host.ownership.fd is None
        with pytest.raises(PermissionError): host.snapshot(2, 7, None)
        with pytest.raises(ValueError): host.snapshot(1, 7, '42')
    finally: shared.close()


def test_grant_survives_without_browser_credentials_and_route_changes_revoke(tmp_path, monkeypatch):
    host, shared, server = make_host(tmp_path, monkeypatch)
    try:
        host.enable(1, 7, 'postgresql-database:42', {})
        assert not host._issuing_permissions
        grant = host._grants[(1, 7, 'postgresql-database:42')]
        assert grant.engine == 'postgresql'
        assert grant.require(grant.policy, 'collect')
        assert 'test-password' not in repr(host._admissions)
        server.port = 6543
        with pytest.raises(PermissionError): host.snapshot(1, 7, 'postgresql-database:42')
        assert host.disable(1, 7, 'postgresql-database:42')['released']
        assert not host._admissions
    finally: shared.close()


def test_only_native_policy_fields_and_owned_cleanup(tmp_path, monkeypatch):
    host, shared, _ = make_host(tmp_path, monkeypatch)
    try:
        with pytest.raises(ValueError): host.enable(1, 7, None, {'require_wire_encryption': True})
        host.enable(1, 7, None, {})
        with pytest.raises(PermissionError): host.disable(2, 7, None)
        assert host.ownership.fd is not None
        assert shared.close()
        assert host.ownership.fd is None
    finally: shared.close()


def test_fleet_reads_only_owned_collectors_and_discards_revoked_samples(tmp_path, monkeypatch):
    host, shared, server = make_host(tmp_path, monkeypatch)
    monkeypatch.setattr(host, '_registrations', lambda owner:
        [{'server_id': 7, 'name': 'PG'}] if owner == 1 else [])
    try:
        assert host.fleet(1)['servers'][0]['snapshot']['state'] == 'disabled'
        assert not host._grants and host.ownership.fd is None
        host.enable(1, 7, 'postgresql-database:42', {})
        fleet = host.fleet(1)
        assert fleet['registered_endpoints'] == 1
        database = fleet['servers'][0]['databases'][0]
        assert database['name'] == 'qa'
        assert database['target_id'] == 'postgresql-database:42'
        assert len(database['snapshot']['samples']) <= 1
        assert 'authentication' not in database['snapshot']
        assert host.fleet(2)['servers'] == []
        server.port = 6543
        database = host.fleet(1)['servers'][0]['databases'][0]
        assert database['name'] == 'Unavailable target'
        assert database['snapshot'] == {'state': 'authorization-denied', 'samples': []}
    finally: shared.close()


def test_dashboard_scope_requires_owned_server_and_exact_connected_database(tmp_path, monkeypatch):
    from pgadmin.utils.driver.registry import DriverRegistry
    host, shared, _ = make_host(tmp_path, monkeypatch)
    connection = Mock(db='qa')
    connection.connected.return_value = True
    manager = Mock()
    manager.connection.return_value = connection
    driver = Mock()
    driver.connection_manager.return_value = manager
    monkeypatch.setattr(DriverRegistry, 'get', lambda name: driver)
    try:
        scope = host.definition_scope(1, 7, 'postgresql-database:42')
        assert scope['engine'] == 'postgresql' and scope['database'] == 'qa'
        assert scope['target_id'] == 'postgresql-database:42'
        manager.connection.assert_called_once_with(did=42)
        with pytest.raises(PermissionError):
            host.definition_scope(2, 7, 'postgresql-database:42')
        with pytest.raises(ValueError):
            host.definition_scope(1, None, 'postgresql-database:42')
        connection.connected.return_value = False
        with pytest.raises(PermissionError):
            host.definition_scope(1, 7, 'postgresql-database:42')
        assert host.definition_scope(1, 7, None)['kind'] == 'server'
        assert not host._grants and host.ownership.fd is None
    finally:
        shared.close()


@pytest.mark.parametrize('provider,version,profile,profile_version,accepted', [
    ('org.pgadmin.postgresql', None, None, None, True),
    ('org.pgadmin.postgresql', '9.17.0', 'postgresql-native', '18.3', True),
    ('org.pgadmin.postgresql', '9.17.0', 'postgresql-native', '17', False),
    ('org.pgadmin.postgresql', 'unqualified', 'postgresql-native', '18.3', False),
    ('org.pgadmin.cockroachdb', None, None, None, False),
])
def test_monitoring_accepts_both_native_registration_paths_only(provider, version, profile, profile_version, accepted):
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(provider_id=provider,
        provider_version=version, profile_id=profile, profile_version=profile_version))
    assert PostgreSQLMonitoringHost._native_registration(server) is accepted
