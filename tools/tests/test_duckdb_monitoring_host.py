"""DuckDB monitoring grants bind file routes without database credentials."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.workspace.monitoring import MonitoringPolicy
from pgadmin.cdeadmin.workspace.duckdb_monitoring_host import (
    DuckDBFileGrant, DuckDBMonitoringHost)


def test_file_grant_rechecks_owner_scope_and_rejects_credentials(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path / 'owned.duckdb'
    duckdb.connect(str(path)).close()
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    policy = MonitoringPolicy(7, 'endpoint', 'target')
    admitted = {'value': True}
    authorize = lambda *_args: admitted['value']
    grant = DuckDBFileGrant(policy, route, 'generation', authorize)
    source = grant.open_source(policy)
    try:
        assert source.sample()['transaction_refresh']['status'] == 'completed'
        assert grant.authentication['mode'] == 'local-file'
        admitted['value'] = False
        with pytest.raises(PermissionError): grant.require(policy, 'collect')
    finally:
        source.close(); grant.revoke()
    with pytest.raises(PermissionError): grant.open_source(policy)
    with pytest.raises(ValueError, match='credentials'):
        DuckDBFileGrant(policy, {**route, 'password': 'private'}, 'generation', authorize)


def test_host_enable_requires_file_target_and_never_accepts_password_fields(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path / 'owned.duckdb'
    duckdb.connect(str(path)).close()
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    context = SimpleNamespace(profile_id='duckdb-native')
    endpoint = SimpleNamespace(id='endpoint', profile_generation='generation', cache_namespace='cache')
    server = SimpleNamespace(endpoint_profile=endpoint)
    endpoints = SimpleNamespace(workspace=Mock(return_value=(context, {'route': route}, None)))
    shared = SimpleNamespace(endpoints=endpoints, ownership=Mock(), keys=Mock())
    app = SimpleNamespace(extensions={}, config={'CDEADMIN_MONITORING_PROCESS_MODE': 'single',
        'CDEADMIN_MONITORING_LOCK_PATH': '/tmp/unused'}, app_context=lambda: nullcontext())
    host = DuckDBMonitoringHost(app, shared)
    host._owned_server = Mock(return_value=server)
    host._configuration = Mock(return_value='configuration')
    host._authorizer = Mock(return_value=lambda *_args: True)
    host.runtime = Mock()
    host.runtime.snapshot.return_value = {'state': 'collecting', 'samples': []}
    for target, body in ((None, {}), ('target', {'credentials': {'password': 'private'}})):
        with pytest.raises(ValueError): host.enable(7, 9, target, body)
    result = host.enable(7, 9, 'target', {'heartbeat_enabled': True})
    assert result['authentication']['mode'] == 'local-file'
    assert result['policy']['heartbeat_enabled'] is True
    host.ownership.acquire.assert_called_once_with()
    host.runtime.enable.assert_called_once()
    host._grants[(7, 9, 'target')].revoke()


def test_server_dashboard_aggregates_only_registered_file_collectors():
    host = object.__new__(DuckDBMonitoringHost)
    host._owned_server = Mock(return_value=SimpleNamespace(
        name='Local', endpoint_profile=SimpleNamespace(database_targets=[
            SimpleNamespace(id='first', display_name='first.duckdb'),
            SimpleNamespace(id='second', display_name='second.duckdb')])))
    host.app = SimpleNamespace(app_context=lambda: nullcontext())
    host._lock = __import__('threading').RLock()
    host._grants = {}
    host._admissions = {}
    host.admitted = True
    host.history = None
    host.ownership = Mock()
    result = host.snapshot(7, 9, None)
    assert result['state'] == 'aggregate'
    assert [(item['target_id'], item['snapshot']['state'])
            for item in result['databases']] == [
                ('first', 'disabled'), ('second', 'disabled')]
    assert 'no remote server process' in result['aggregation']
