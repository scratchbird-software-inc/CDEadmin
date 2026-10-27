"""SQLite monitoring grants bind registered file routes without credentials."""

from contextlib import nullcontext
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.workspace.monitoring import MonitoringPolicy
from pgadmin.cdeadmin.workspace.sqlite_monitoring_host import (
    SQLiteFileGrant, SQLiteMonitoringHost)


def test_file_grant_rechecks_scope_and_rejects_credentials(tmp_path):
    path = tmp_path / 'owned.sqlite'
    sqlite3.connect(path).close()
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    policy = MonitoringPolicy(7, 'endpoint', 'target')
    admitted = {'value': True}
    grant = SQLiteFileGrant(policy, route, 'generation',
                           lambda *_args: admitted['value'])
    source = grant.open_source(policy)
    try:
        assert source.sample()['transaction_refresh']['status'] == 'completed'
        assert grant.authentication['mode'] == 'local-file'
        admitted['value'] = False
        with pytest.raises(PermissionError):
            grant.require(policy, 'collect')
    finally:
        source.close()
        grant.revoke()
    with pytest.raises(PermissionError):
        grant.open_source(policy)
    with pytest.raises(ValueError, match='credentials'):
        SQLiteFileGrant(policy, {**route, 'password': 'private'},
                        'generation', lambda *_args: True)


def test_host_policy_admission_is_file_scoped(tmp_path):
    path = tmp_path / 'owned.sqlite'
    sqlite3.connect(path).close()
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    context = SimpleNamespace(profile_id='sqlite-native')
    endpoint = SimpleNamespace(id='endpoint', profile_generation='generation',
                               cache_namespace='cache')
    server = SimpleNamespace(endpoint_profile=endpoint)
    endpoints = SimpleNamespace(workspace=Mock(return_value=(
        context, {'route': route}, None)))
    shared = SimpleNamespace(endpoints=endpoints, ownership=Mock(), keys=Mock())
    app = SimpleNamespace(extensions={}, config={'CDEADMIN_MONITORING_PROCESS_MODE': 'single',
        'CDEADMIN_MONITORING_LOCK_PATH': '/tmp/unused'},
        app_context=lambda: nullcontext())
    host = SQLiteMonitoringHost(app, shared)
    host._owned_server = Mock(return_value=server)
    host._configuration = Mock(return_value='configuration')
    host._authorizer = Mock(return_value=lambda *_args: True)
    host.runtime = Mock()
    host.runtime.snapshot.return_value = {'state': 'collecting', 'samples': []}
    for target, body in ((None, {}),
                         ('target', {'credentials': {'password': 'private'}})):
        with pytest.raises(ValueError):
            host.enable(7, 9, target, body)
    result = host.enable(7, 9, 'target', {'heartbeat_enabled': True})
    assert result['authentication']['mode'] == 'local-file'
    assert result['policy']['heartbeat_enabled'] is True
    host.runtime.enable.assert_called_once()
    host._grants[(7, 9, 'target')].revoke()
