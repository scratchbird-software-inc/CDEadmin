"""DuckDB attachment plans keep exact file and session boundaries."""

import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider, _create_client
from pgadmin.cdeadmin.workspace.duckdb_attachment import plan
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceError, ProviderWorkspaceService


def files(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    primary, attached = tmp_path/'primary.duckdb', tmp_path/'archive.duckdb'
    for file in (primary, attached):
        connection = duckdb.connect(str(file))
        connection.execute('CREATE TABLE marker(value INTEGER)')
        connection.close()
    return {'database': str(primary), 'filesystem_root': str(tmp_path)}, attached


def test_native_session_attach_and_detach_only_when_reviewed_script_runs(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    route, attached = files(tmp_path)
    preview = plan(route, {'action': 'attach', 'alias': 'history', 'path': str(attached), 'read_only': True})
    assert preview['executed'] is False and preview['session_scope'] == 'selected-retained-connection'
    connection = duckdb.connect(route['database'])
    try:
        assert connection.execute("SELECT count(*) FROM duckdb_databases() WHERE database_name='history'").fetchone()[0] == 0
        connection.execute(preview['source'])
        assert connection.execute('SELECT count(*) FROM history.main.marker').fetchone()[0] == 0
        detached = plan(route, {'action': 'detach', 'alias': 'history'})
        connection.execute(detached['source'])
        assert connection.execute("SELECT count(*) FROM duckdb_databases() WHERE database_name='history'").fetchone()[0] == 0
    finally:
        connection.close()


def test_attachment_refuses_escape_symlink_primary_alias_and_readonly_write(tmp_path):
    route, attached = files(tmp_path)
    outside = tmp_path.parent/(tmp_path.name + '-outside.duckdb')
    outside.write_bytes(attached.read_bytes())
    link = tmp_path/'linked.duckdb'; os.symlink(outside, link)
    try:
        for target in (outside, link):
            with pytest.raises(ValueError): plan(route, {'action': 'attach',
                'alias': 'archive', 'path': str(target), 'read_only': True})
        for alias in ('primary', 'temp'):
            with pytest.raises(ValueError): plan(route, {'action': 'detach', 'alias': alias})
        with pytest.raises(ValueError, match='Read-only'):
            plan({**route, 'read_only': True}, {'action': 'attach',
                'alias': 'archive', 'path': str(attached), 'read_only': False})
    finally:
        outside.unlink()


def test_workspace_attachment_plan_does_not_mutate_any_connection(tmp_path):
    route, attached = files(tmp_path)
    provider = DuckDBPilotProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    context = SimpleNamespace(profile_id='duckdb-native', endpoint_id='owned')
    service = object.__new__(ProviderWorkspaceService)
    service.endpoint_service = SimpleNamespace(workspace=Mock(return_value=(context, {'route': route}, None)),
        provider_registry=SimpleNamespace(resolve=Mock(return_value=SimpleNamespace(instance=provider))))
    try:
        result = service.duckdb_attachment_plan(SimpleNamespace(), {'database_target_id': 'file-1',
            'action': 'attach', 'alias': 'history', 'path': str(attached), 'read_only': True})
        assert not result['executed'] and 'READ_ONLY' in result['source']
        provider.client._connect = Mock(side_effect=AssertionError('must not connect'))
        with pytest.raises(ProviderWorkspaceError):
            service.duckdb_attachment_plan(SimpleNamespace(), {'database_target_id': 'file-1',
                'action': 'attach', 'alias': 'history', 'path': str(attached), 'read_only': True,
                'sql': 'DROP TABLE marker'})
        provider.client._connect.assert_not_called()
    finally:
        provider.client.close()
