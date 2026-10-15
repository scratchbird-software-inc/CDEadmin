"""Native COPY preview uses exact registered table and contained files."""

from types import SimpleNamespace
from unittest.mock import Mock
import os

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider, _create_client
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.duckdb_copy import plan
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceError, ProviderWorkspaceService
from pgadmin.cdeadmin.context_menu import resource_context_actions


def captured(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    file = tmp_path/'registered.duckdb'
    connection = duckdb.connect(str(file))
    connection.execute('CREATE TABLE facts(n INTEGER, v VARCHAR)')
    connection.execute("INSERT INTO facts VALUES (1, 'first')")
    connection.close()
    provider = DuckDBPilotProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(file), 'filesystem_root': str(tmp_path)}
    result = provider.capture_catalog(route)
    model = build_export(result['resources'], endpoint_id='owned', target_id='file-1',
        generation=result['generation'], engine='duckdb', native_model=True)
    table = next(identity for identity, row in model['rows'].items()
        if row['kind'] == 'table' and row['name'] == 'facts')
    return provider, route, model, table


def test_real_native_copy_roundtrip_uses_only_generated_reviewed_source(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, model, table = captured(tmp_path)
    output = tmp_path/'native.parquet'
    try:
        exported = plan(model, {'resource_id': table, 'direction': 'to',
            'format': 'PARQUET', 'path': str(output)}, str(tmp_path))
        assert not output.exists() and not exported['executed']
        assert len(duckdb.extract_statements(exported['source'])) == 1
        connection = duckdb.connect(route['database'])
        connection.execute(exported['source'])
        assert output.is_file()
        connection.execute('DELETE FROM facts')
        imported = plan(model, {'resource_id': table, 'direction': 'from',
            'format': 'PARQUET', 'path': str(output)}, str(tmp_path))
        connection.execute(imported['source'])
        assert connection.execute('SELECT * FROM facts').fetchall() == [(1, 'first')]
        connection.close()
    finally:
        provider.client.close()


def test_copy_refuses_foreign_paths_symlinks_and_other_resources(tmp_path):
    provider, _route, model, table = captured(tmp_path)
    outside = tmp_path.parent/(tmp_path.name + '-outside.parquet'); outside.write_bytes(b'not parquet')
    link = tmp_path/'link.parquet'; os.symlink(outside, link)
    try:
        for path in (str(outside), str(link)):
            with pytest.raises(ValueError): plan(model, {'resource_id': table,
                'direction': 'from', 'format': 'PARQUET', 'path': path}, str(tmp_path))
        with pytest.raises(ValueError, match='absent destination'):
            plan(model, {'resource_id': table, 'direction': 'to',
                'format': 'CSV', 'path': str(tmp_path/'registered.duckdb')}, str(tmp_path))
        with pytest.raises(ValueError, match='persistent table'):
            plan(model, {'resource_id': 'other', 'direction': 'to',
                'format': 'PARQUET', 'path': str(tmp_path/'unused.parquet')}, str(tmp_path))
    finally:
        provider.client.close()
        outside.unlink()


def test_workspace_copy_plan_binds_registered_target_and_write_permission(tmp_path):
    provider, route, _model, table = captured(tmp_path)
    context = SimpleNamespace(profile_id='duckdb-native', endpoint_id='owned')
    service = object.__new__(ProviderWorkspaceService)
    service.endpoint_service = SimpleNamespace(workspace=Mock(return_value=(context, {'route': route}, None)),
        provider_registry=SimpleNamespace(resolve=Mock(return_value=SimpleNamespace(instance=provider))))
    body = {'database_target_id': 'file-1', 'resource_id': table, 'direction': 'to',
        'format': 'CSV', 'path': str(tmp_path/'facts.csv')}
    try:
        result = service.duckdb_copy_plan(SimpleNamespace(), body)
        assert result['executed'] is False and 'HEADER TRUE' in result['source']
        with pytest.raises(ProviderWorkspaceError):
            service.duckdb_copy_plan(SimpleNamespace(), {**body, 'source': 'DROP TABLE facts'})
        service.endpoint_service.workspace.return_value = (context, {'route': {**route, 'read_only': True}}, None)
        with pytest.raises(ProviderWorkspaceError, match='Read-only'):
            service.duckdb_copy_plan(SimpleNamespace(), {**body, 'direction': 'from'})
    finally:
        provider.client.close()


def test_table_context_offers_copy_only_for_persistent_user_tables():
    profile = {'engine_id': 'duckdb', 'engine_display_name': 'DuckDB'}
    catalog = {'objects': [{'resource_kind': 'table', 'operations': [], 'editor': {'sections': []}}]}
    resource = {'resource_id': 'native-table', 'resource_kind': 'table', 'display_name': 'facts',
        'native': {'system_object': False, 'catalog_metadata': {'temporary': False}}}
    def actions(item):
        return {action['command_id'] for action in resource_context_actions(
            profile, item, catalog, database_target_id='file-1')}
    assert 'resource.duckdb.table.copy' in actions(resource)
    assert 'resource.duckdb.table.copy' not in actions({**resource,
        'native': {'system_object': False, 'catalog_metadata': {'temporary': True}}})
