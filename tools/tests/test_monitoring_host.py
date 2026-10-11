"""Host admission, current-owner scope, and exclusive process ownership."""

import base64
import os
from types import SimpleNamespace
from unittest.mock import Mock

from flask import Flask
import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.security.secrets import SecretLease
from pgadmin.cdeadmin.workspace.monitoring_host import (
    MonitoringHost, MonitoringHostUnavailable, ProcessOwnership,
)


def host(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config.update(
        CDEADMIN_MONITORING_PROCESS_MODE='single',
        CDEADMIN_MONITORING_WORKER_KEYS={
            'test': base64.b64encode(os.urandom(32)).decode()},
        CDEADMIN_MONITORING_WORKER_ACTIVE_KEY_ID='test',
        CDEADMIN_MONITORING_LOCK_PATH=str(tmp_path / 'monitoring.lock'))
    value = MonitoringHost(app, Mock())
    scope = {'endpoint_id': 'endpoint', 'generation': 'one',
             'route': {'host': 'localhost', 'database': 'demo.fdb',
                       'credential_reference_id': 'credential',
                       'principal_reference': 'owner:1'},
             'permissions': SimpleNamespace(acquire_secret=lambda *_:
                 SecretLease('test-password'))}

    def owned(owner, sid):
        if owner != 1 or sid != 7:
            raise PermissionError('Unavailable')
        return SimpleNamespace(name='Native', endpoint_profile=SimpleNamespace(
            database_targets=[SimpleNamespace(id='database', display_name='Demo')]))

    monkeypatch.setattr(value, '_owned_server', owned)

    def resolve(owner, sid, target):
        owned(owner, sid)
        result = {**scope, 'route': dict(scope['route'])}
        if target is None:
            result['route'].pop('database')
        elif target != 'database':
            raise PermissionError('Wrong target')
        return result

    monkeypatch.setattr(value, '_scope', resolve)
    monkeypatch.setattr(
        'pgadmin.cdeadmin.workspace.monitoring_delegation.MonitoringGrant.open_source',
        lambda *_: Mock(sample=Mock(return_value={'status': 'available'})))
    return value, scope


def test_get_never_creates_policy_or_acquires_process_lock(tmp_path, monkeypatch):
    value, _ = host(tmp_path, monkeypatch)
    try:
        assert value.snapshot(1, 7, 'database')['state'] == 'disabled'
        assert value.snapshot(1, 7, None)['navigation']['databases'] == [
            {'target_id': 'database', 'name': 'Demo'}]
        with pytest.raises(PermissionError):
            value.snapshot(1, 7, 'removed-target')
        assert not value._grants
        assert value.ownership.fd is None
        with pytest.raises(PermissionError):
            value.snapshot(2, 7, 'database')
    finally:
        value.close()


def test_route_change_blocks_old_samples_but_allows_owner_cleanup(tmp_path, monkeypatch):
    value, scope = host(tmp_path, monkeypatch)
    try:
        first = value.enable(1, 7, 'database', {})
        assert value.enable(1, 7, 'database', {})['revision'] == first['revision']
        scope['route']['port'] = 9999
        with pytest.raises(PermissionError):
            value.snapshot(1, 7, 'database')
        assert value.disable(1, 7, 'database')['released']
    finally:
        value.close()


def test_server_interval_override_and_no_browser_route_override(tmp_path, monkeypatch):
    value, _ = host(tmp_path, monkeypatch)
    try:
        assert value.enable(1, 7, None, {'interval_seconds': 20})['interval_seconds'] == 20
        with pytest.raises(ValueError):
            value.enable(1, 7, 'database', {'route': {'host': 'other'}})
        with pytest.raises(PermissionError):
            value.enable(2, 7, 'database', {})
    finally:
        value.close()


def test_second_process_owner_is_refused_until_first_releases(tmp_path):
    one = ProcessOwnership(tmp_path / 'monitoring.lock')
    two = ProcessOwnership(tmp_path / 'monitoring.lock')
    try:
        one.acquire()
        with pytest.raises(MonitoringHostUnavailable):
            two.acquire()
        one.close()
        two.acquire()
    finally:
        one.close()
        two.close()


def test_collection_requires_explicit_host_admission():
    value = MonitoringHost(Flask(__name__), Mock())
    try:
        with pytest.raises(MonitoringHostUnavailable):
            value.enable(1, 7, 'database', {})
    finally:
        value.close()


def test_fleet_filters_current_owner_and_native_profile_without_starting_sources(tmp_path, monkeypatch):
    import sys
    from types import ModuleType
    model = ModuleType('pgadmin.model')
    monkeypatch.setitem(sys.modules, 'pgadmin.model', model)
    value, _ = host(tmp_path, monkeypatch)
    query = Mock()
    user_query = Mock()
    query.filter_by.return_value.all.return_value = [
        SimpleNamespace(id=7, name='Native', endpoint_profile=SimpleNamespace(
            profile_id='firebird-native', database_targets=[
                SimpleNamespace(id='database', display_name='Demo')])),
        SimpleNamespace(id=8, name='Other engine', endpoint_profile=SimpleNamespace(
            profile_id='mysql-native', database_targets=[])),
    ]
    monkeypatch.setattr(model, 'Server', SimpleNamespace(query=query), raising=False)
    monkeypatch.setattr(model, 'User', SimpleNamespace(query=user_query), raising=False)
    try:
        result = value.fleet(1)
        query.filter_by.assert_called_once_with(user_id=1)
        assert result['registered_endpoints'] == 1
        assert result['servers'][0]['status'] == 'unknown'
        assert result['servers'][0]['known_databases'] == 1
        assert not value._grants
        assert value.ownership.fd is None
        user_query.filter_by.return_value.first.return_value = None
        with pytest.raises(PermissionError):
            value.fleet(1)
    finally:
        value.close()


def test_dedicated_account_requires_stop_before_replacement(tmp_path, monkeypatch):
    value, scope = host(tmp_path, monkeypatch)
    credentials = {'username': 'MONITOR', 'password': 'test-only-monitor-secret'}
    scope['permissions'].acquire_secret = Mock(side_effect=AssertionError('No registration secret'))
    try:
        result = value.enable(1, 7, 'database', {'credentials': credentials})
        assert result['authentication'] == {'mode': 'dedicated', 'username': 'MONITOR', 'role': ''}
        assert 'test-only-monitor-secret' not in str(value.snapshot(1, 7, 'database'))
        with pytest.raises(ValueError):
            value.enable(1, 7, 'database', {'credentials': {**credentials, 'username': 'NEW'}})
        assert value.disable(1, 7, 'database')['released']
        value.enable(1, 7, 'database', {'credentials': {**credentials, 'username': 'NEW'}})
        assert value.snapshot(1, 7, 'database')['authentication']['username'] == 'NEW'
        scope['permissions'].acquire_secret.assert_not_called()
    finally:
        value.close()


def test_statement_inspection_retains_owner_and_target_scope(tmp_path, monkeypatch):
    value, scope = host(tmp_path, monkeypatch)
    try:
        assert value.inspect_statement(1, 7, 'database', {})['status'] == 'unavailable'
        with pytest.raises(PermissionError):
            value.inspect_statement(2, 7, 'database', {})
        with pytest.raises(PermissionError):
            value.inspect_statement(1, 7, 'removed', {})
        value.enable(1, 7, 'database', {})
        value.runtime.inspect_statement = Mock(return_value={'status': 'gone'})
        reference = {'sample_id': 's'}
        assert value.inspect_statement(1, 7, 'database', reference) == {'status': 'gone'}
        config, authorize, received = value.runtime.inspect_statement.call_args.args
        assert received is reference and config.owner_id == 1 and config.target_id == 'database'
        assert authorize(config, 'view') is True
        scope['route']['port'] = 9999
        assert authorize(config, 'view') is False
    finally:
        value.close()
