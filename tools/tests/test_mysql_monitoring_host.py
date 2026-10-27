"""MySQL grants survive browser loss but not persisted registration changes."""
import base64
import os
from types import SimpleNamespace as NS
from unittest.mock import Mock

from flask import Flask
import pytest
from pgadmin.cdeadmin.security.secrets import SecretLease
from pgadmin.cdeadmin.workspace.monitoring_host import MonitoringHost
from pgadmin.cdeadmin.workspace.mysql_monitoring_host import MySQLMonitoringHost


def make_host(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config.update(CDEADMIN_MONITORING_PROCESS_MODE='single',
        CDEADMIN_MONITORING_WORKER_KEYS={'k': base64.b64encode(os.urandom(32)).decode()},
        CDEADMIN_MONITORING_WORKER_ACTIVE_KEY_ID='k', CDEADMIN_MONITORING_LOCK_PATH=str(tmp_path/'monitor.lock'))
    endpoints = Mock()
    shared = MonitoringHost(app, endpoints)
    host = MySQLMonitoringHost(app, shared)
    app.extensions['cdeadmin_mysql_monitoring_host'] = host
    server = NS(user_id=1, username='owner', password='encrypted', name='MySQL',
        endpoint_profile=NS(id='endpoint', provider_id='org.cdeadmin.mysql', provider_version='0.1.0',
            profile_id='mysql-native', profile_version='1.1.0', profile_generation='one', cache_namespace='cache',
            runtime_identity=NS(verification_state='verified', verified_runtime_family='mysql',
                verified_runtime_version='9.7.0', verified_at=None, verification_evidence_reference='proof'),
            tls_profile=None, secret_references=[],
            routes=[NS(id='route', route_reference='native', route_kind='network', priority=0, configuration='{}')],
            database_targets=[NS(id='database', display_name='demo', database='demo', configuration='{}',
                registration_user=None, registration_password=None, registration_credentials=False)]))
    def owned(owner, sid):
        if (owner, sid) != (1, 7): raise PermissionError('Not owned')
        return server
    monkeypatch.setattr(host, '_owned_server', owned)
    endpoints.workspace.return_value = (NS(profile_id='mysql-native'), {'route': {
        'host': 'localhost', 'port': 3306, 'database': 'demo', 'user': 'owner',
        'principal_reference': 'owner:1', 'credential_reference_id': 'current'}}, None)
    permission = NS(acquire_secret=Mock(side_effect=lambda *_: SecretLease('private-credential')))
    endpoints.provider_registry.resolve.return_value = NS(permissions=permission)
    monkeypatch.setattr('pgadmin.cdeadmin.workspace.monitoring_delegation.MonitoringGrant.open_source',
        lambda *_: Mock(sample=Mock(return_value={'status': 'partial', 'scope': 'database', 'transaction_completed': True})))
    return host, shared, server, permission


@pytest.mark.parametrize('change', ['route', 'target', 'generation', 'verification', 'credential'])
def test_browser_free_grant_is_revoked_by_persisted_change(tmp_path, monkeypatch, change):
    host, shared, server, permission = make_host(tmp_path, monkeypatch)
    try:
        host.enable(1, 7, 'database', {})
        assert not host._issuing_permissions
        grant = host._grants[(1, 7, 'database')]
        permission.acquire_secret.side_effect = AssertionError('Browser credential resolver reused')
        assert grant.require(grant.policy, 'collect')
        assert 'private-credential' not in repr(host._admissions)
        endpoint = server.endpoint_profile
        if change == 'route': endpoint.routes[0].configuration = '{"host":"other"}'
        elif change == 'target': endpoint.database_targets[0].database = 'other'
        elif change == 'generation': endpoint.profile_generation = 'two'
        elif change == 'verification': endpoint.runtime_identity.verification_state = 'disconnected'
        else: server.password = 'rotated-ciphertext'
        with pytest.raises(PermissionError): grant.require(grant.policy, 'collect')
        assert host.disable(1, 7, 'database')['released']
        assert not host._admissions
    finally: shared.close()


def test_dedicated_credentials_are_sealed_and_common_lock_is_released(tmp_path, monkeypatch):
    host, shared, _server, permission = make_host(tmp_path, monkeypatch)
    try:
        permission.acquire_secret.side_effect = AssertionError('Registration credential read')
        result = host.enable(1, 7, 'database', {'credentials': {
            'username': 'monitor', 'password': 'dedicated-private', 'role': 'read_metrics'}, 'heartbeat_enabled': True})
        assert result['authentication']['username'] == 'monitor'
        assert set(result['policy']) == host.policy_fields
        assert result['policy']['heartbeat_enabled'] is True
        assert 'dedicated-private' not in str(result)
        assert 'credentials' not in result['policy']
        grant = host._grants[(1, 7, 'database')]
        assert grant.engine == 'mysql' and grant.policy.heartbeat_enabled
        assert 'dedicated-private' not in repr(grant._credentials)
        with pytest.raises(ValueError): host.enable(1, 7, 'database', {'credentials': {'username': 'replacement', 'password': 'other'}})
        with pytest.raises(PermissionError): host.disable(2, 7, 'database')
        assert host.ownership.fd is not None
        assert shared.close()
        assert host.ownership.fd is None
    finally: shared.close()


def test_fleet_is_passive_owner_scoped_and_does_not_expose_authentication(tmp_path, monkeypatch):
    host, shared, server, permission = make_host(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(host, '_registrations', lambda owner: [{'server_id': 7, 'name': 'MySQL',
            'databases': [{'target_id': 'database', 'name': 'demo'}]}] if owner == 1 else [])
        snapshot = Mock(side_effect=lambda owner, sid, target: {'state': 'collecting',
            'authentication': {'username': 'not-fleet-data'}, 'samples': [{'sample_id': 'old'}, {'sample_id': 'latest'}]})
        monkeypatch.setattr(host, 'snapshot', snapshot)
        data = host.fleet(1)
        assert data['engine_id'] == 'mysql' and data['registered_endpoints'] == 1
        assert data['servers'][0]['snapshot']['samples'][0]['sample_id'] == 'latest'
        assert 'not-fleet-data' not in str(data)
        assert not host._grants and not host._admissions
        permission.acquire_secret.assert_not_called()
        assert not host.fleet(2)['servers']
    finally: shared.close()


def test_definition_scope_matches_native_owner_and_database_without_connecting(tmp_path, monkeypatch):
    host, shared, server, permission = make_host(tmp_path, monkeypatch)
    try:
        assert host.definition_scope(1, 7, 'database') == {'engine': 'mysql', 'kind': 'database',
            'owner': 1, 'server_id': 7, 'endpoint_id': 'endpoint', 'target_id': 'database', 'database': 'demo'}
        with pytest.raises(PermissionError): host.definition_scope(1, 7, 'other')
        with pytest.raises(PermissionError): host.definition_scope(2, 7, 'database')
        permission.acquire_secret.assert_not_called()
    finally: shared.close()


def test_same_runtime_reverification_does_not_revoke_browser_free_collector(tmp_path, monkeypatch):
    host, shared, server, permission = make_host(tmp_path, monkeypatch)
    try:
        host.enable(1, 7, 'database', {})
        grant = host._grants[(1, 7, 'database')]
        permission.acquire_secret.side_effect = AssertionError('Browser credential resolver reused')
        server.endpoint_profile.runtime_identity.verified_at = 'later native verification'
        assert grant.require(grant.policy, 'collect')
        assert host.snapshot(1, 7, 'database')['policy']['interval_seconds'] > 0
        server.endpoint_profile.runtime_identity.verified_runtime_version = 'changed'
        with pytest.raises(PermissionError): grant.require(grant.policy, 'collect')
    finally: shared.close()


def test_history_without_collector_or_browser_credentials_reauthorizes_after_read(tmp_path, monkeypatch):
    host, shared, server, permission = make_host(tmp_path, monkeypatch)
    arguments = {'start': '2026-10-15T00:00:00Z', 'end': '2026-10-16T00:00:00Z'}
    host.history = Mock(query=Mock(return_value={'history': 'scratchbird', 'samples': []}))
    try:
        assert 'history_enabled' in host.policy_fields
        assert host.historical(1, 7, 'database', arguments)['history'] == 'scratchbird'
        assert not host._admissions and not host._grants
        permission.acquire_secret.assert_not_called()
        with pytest.raises(PermissionError):
            host.historical(2, 7, 'database', arguments)
        with pytest.raises(PermissionError):
            host.historical(1, 7, 'other', arguments)
        def changed(*args, **kwargs):
            server.endpoint_profile.database_targets[0].database = 'different'
            return {'samples': [{'must_not_escape': True}]}
        host.history.query.side_effect = changed
        with pytest.raises(PermissionError):
            host.historical(1, 7, 'database', arguments)
    finally:
        shared.close()


def test_mysql_history_disabled_when_destination_unconfigured(tmp_path, monkeypatch):
    host, shared, _server, _permission = make_host(tmp_path, monkeypatch)
    try:
        assert host.snapshot(1, 7, 'database')['history_available'] is False
        with pytest.raises(ValueError):
            host.enable(1, 7, 'database', {'history_enabled': True})
        assert not host._grants
    finally:
        shared.close()
