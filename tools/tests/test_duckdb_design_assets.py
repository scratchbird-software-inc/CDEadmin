"""DuckDB DDN design revisions remain owner/file scoped and retain baselines."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.tests.test_cdeadmin_project_assets import MemoryRepository
from tools.tests.test_firebird_design_assets import SNAPSHOT, SCOPE
from pgadmin.cdeadmin.workspace.assets import ProjectAssetService, ProjectAssetError, ProjectAssetConflict
from pgadmin.cdeadmin.workspace.firebird_design_assets import NativeDesignAssets
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError


def test_duckdb_catalog_design_revisions_and_exact_scope():
    assets = ProjectAssetService(MemoryRepository())
    designs = NativeDesignAssets(assets, engine='duckdb')
    first = designs.apply(7, SCOPE, 'read', {'kind': 'catalog'})
    assert first['assetRef']['projectId'] == 'duckdb-designs-7'
    body = {'kind': 'catalog', 'assetRef': first['assetRef'],
            'snapshot': deepcopy(SNAPSHOT), 'baseline': deepcopy(SNAPSHOT)}
    saved = designs.apply(7, SCOPE, 'save', body)
    assert saved['version'] == 1 and saved['baseline'] == SNAPSHOT
    with pytest.raises(ProjectAssetConflict):
        designs.apply(7, SCOPE, 'save', body)
    commits = assets.repository.commits
    for owner, scope, engine in (
            (8, SCOPE, 'duckdb'),
            (7, {**SCOPE, 'database_target_id': 'other'}, 'duckdb'),
            (7, SCOPE, 'mysql')):
        with pytest.raises(ProjectAssetError):
            NativeDesignAssets(assets, engine=engine).apply(owner, scope,
                'save', {**body, 'assetRef': saved['assetRef']})
    assert assets.repository.commits == commits


def test_duckdb_design_read_keeps_original_baseline_after_edit():
    assets = ProjectAssetService(MemoryRepository())
    designs = NativeDesignAssets(assets, engine='duckdb')
    reference = designs.apply(7, SCOPE, 'read', {'kind': 'catalog'})['assetRef']
    body = {'kind': 'catalog', 'assetRef': reference,
            'snapshot': deepcopy(SNAPSHOT), 'baseline': deepcopy(SNAPSHOT)}
    saved = designs.apply(7, SCOPE, 'save', body)
    body['assetRef'] = saved['assetRef']
    body['snapshot']['files']['catalog.ddn'] += '\n// authored DuckDB design'
    designs.apply(7, SCOPE, 'save', body)
    old = designs.apply(7, SCOPE, 'read', {'kind': 'catalog', 'version': 1})
    current = designs.apply(7, SCOPE, 'read', {'kind': 'catalog'})
    assert old['snapshot'] == old['baseline'] == SNAPSHOT
    assert current['baseline'] == SNAPSHOT
    assert 'authored DuckDB design' in current['snapshot']['files']['catalog.ddn']


def test_workspace_design_action_binds_native_file_and_owner():
    assets = ProjectAssetService(MemoryRepository())
    context = SimpleNamespace(profile_id='duckdb-native',
        provider_id='org.cdeadmin.duckdb', endpoint_id='endpoint-one')
    service = object.__new__(ProviderWorkspaceService)
    service.endpoint_service = SimpleNamespace(workspace=Mock(return_value=(context, {}, None)))
    service.firebird_design_assets = SimpleNamespace(assets=assets)
    service._principal_id = Mock(return_value=7)
    request = {'kind': 'catalog', 'database_target_id': 'target-one'}
    result = service.duckdb_design_asset(SimpleNamespace(), 'read', request)
    assert result['scope']['endpoint_id'] == 'endpoint-one'
    assert result['scope']['database_target_id'] == 'target-one'
    with pytest.raises(ProviderWorkspaceError):
        service.duckdb_design_asset(SimpleNamespace(), 'read', {**request, 'database_target_id': ''})
    service.endpoint_service.workspace.return_value = (
        SimpleNamespace(profile_id='mysql-native', provider_id='org.cdeadmin.mysql', endpoint_id='endpoint-one'), {}, None)
    with pytest.raises(ProviderWorkspaceError, match='DuckDB endpoint'):
        service.duckdb_design_asset(SimpleNamespace(), 'read', request)
