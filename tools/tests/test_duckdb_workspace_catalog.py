"""DuckDB DDN exchange stays on its registered embedded database target."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.catalog import capture
from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider, _create_client
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceError, ProviderWorkspaceService
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export


def test_owned_target_export_compare_and_foreign_document_rejection(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path / 'owned.duckdb'
    connection = duckdb.connect(str(path))
    connection.execute('CREATE TABLE native_fact (id INTEGER PRIMARY KEY, value DECIMAL(18,2))')
    provider = DuckDBPilotProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    provider.capture_catalog = Mock(return_value=capture(connection))
    context = SimpleNamespace(profile_id='duckdb-native', endpoint_id='owned-endpoint')
    endpoint = {'route': {'database': str(path), 'filesystem_root': str(tmp_path)}}
    service = object.__new__(ProviderWorkspaceService)
    service.endpoint_service = SimpleNamespace(
        workspace=Mock(return_value=(context, endpoint, None)),
        provider_registry=SimpleNamespace(resolve=Mock(return_value=SimpleNamespace(instance=provider))))
    server = SimpleNamespace()
    try:
        result = service.duckdb_catalog(server, {'database_target_id': 'owned-target'})
        assert result['provenance']['mapping'] == 'scratchrobin.duckdb.catalog@1'
        assert result['diagram']['snapshot']['format'] == 'ddn-workspace@1'
        assert any(item['name'] == 'native_fact' for item in result['objects'])
        provider.capture_catalog.assert_called_once_with(endpoint['route'], include_system=False)
        provider.capture_catalog.reset_mock()
        offered = service.duckdb_test_data(server, {'database_target_id': 'owned-target'})
        selected = next(item for item in offered['tables'] if item['name'] == 'native_fact')
        recipe = {'format': 'scratchrobin.duckdb.test-data@1', 'scope': offered['scope'],
            'seed': 1, 'tables': [{'table': selected['resource_id'], 'count': 1,
                'columns': {'id': {'kind': 'constant', 'value': 14}}}]}
        generated = service.duckdb_test_data(server, {'database_target_id': 'owned-target', 'recipe': recipe})
        assert generated['executed'] is False and 'INSERT INTO' in generated['source']
        assert connection.execute('SELECT count(*) FROM native_fact').fetchone()[0] == 0
        with pytest.raises(ProviderWorkspaceError):
            service.duckdb_test_data(server, {'database_target_id': 'owned-target', 'recipe': recipe,
                'sql': 'DROP TABLE native_fact'})
        with pytest.raises(ProviderWorkspaceError, match='another endpoint'):
            service.duckdb_test_data(server, {'database_target_id': 'owned-target',
                'recipe': {**recipe, 'scope': {'endpoint_id': 'foreign', 'database_target_id': 'owned-target'}}})
        assert result['generation'] == provider.capture_catalog.return_value['generation']
        source = json.dumps(result['snapshot'])
        assert not service.duckdb_catalog(server, {'database_target_id': 'owned-target',
            'source': source}, compare=True)['changes']
        preview = service.duckdb_schema_plan(server, {'database_target_id': 'owned-target',
            'baseline': source, 'desired': source})
        assert preview['operations'] == [] and not preview['executed']
        assert not preview['application_supported']
        other = build_export(provider.capture_catalog.return_value['resources'],
            endpoint_id='foreign-endpoint', target_id='owned-target', generation='native-1', engine='duckdb')
        provider.capture_catalog.reset_mock()
        with pytest.raises(ProviderWorkspaceError, match='another endpoint'):
            service.duckdb_catalog(server, {'database_target_id': 'owned-target',
                'source': json.dumps(other['snapshot'])}, compare=True)
        provider.capture_catalog.assert_not_called()
        with pytest.raises(ProviderWorkspaceError, match='another endpoint'):
            service.duckdb_schema_plan(server, {'database_target_id': 'owned-target',
                'baseline': json.dumps(other['snapshot']), 'desired': source})
        provider.capture_catalog.assert_not_called()
        for invalid in ({'database_target_id': ''},
                        {'database_target_id': 'owned-target', 'source': source, 'sql': 'DROP TABLE native_fact'}):
            with pytest.raises(ProviderWorkspaceError): service.duckdb_catalog(server, invalid)
        provider.capture_catalog.assert_not_called()
    finally:
        provider.client.close(); connection.close()


def test_data_capture_uses_registered_route_and_rejects_unexpected_fields(tmp_path):
    provider = DuckDBPilotProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    provider.capture_data = Mock(return_value={'acquisition': {'engine_id': 'duckdb'}})
    context = SimpleNamespace(profile_id='duckdb-native', endpoint_id='owned-endpoint')
    route = {'database': str(tmp_path / 'owned.duckdb'), 'filesystem_root': str(tmp_path)}
    service = object.__new__(ProviderWorkspaceService)
    service.endpoint_service = SimpleNamespace(
        workspace=Mock(return_value=(context, {'route': route}, None)),
        provider_registry=SimpleNamespace(resolve=Mock(return_value=SimpleNamespace(instance=provider))))
    request = {'database_target_id': 'owned-target', 'resource_id': 'native-table',
               'mode': 'sample', 'row_limit': 12}
    assert service.duckdb_data_capture(SimpleNamespace(), request)['acquisition']['engine_id'] == 'duckdb'
    provider.capture_data.assert_called_once_with(route, 'native-table', endpoint_id='owned-endpoint',
        target_id='owned-target', mode='sample', row_limit=12)
    provider.capture_data.reset_mock()
    with pytest.raises(ProviderWorkspaceError):
        service.duckdb_data_capture(SimpleNamespace(), {**request, 'sql': 'SELECT * FROM secret'})
    provider.capture_data.assert_not_called()
    provider.client.close()
