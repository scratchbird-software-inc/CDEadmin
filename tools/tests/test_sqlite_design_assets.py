"""SQLite DDN designs retain revisions within the selected registered file."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.tests.test_cdeadmin_project_assets import MemoryRepository
from tools.tests.test_firebird_design_assets import SNAPSHOT, SCOPE
from pgadmin.cdeadmin.workspace.assets import ProjectAssetService, ProjectAssetError, ProjectAssetConflict
from pgadmin.cdeadmin.workspace.firebird_design_assets import NativeDesignAssets
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError


def test_sqlite_design_versions_and_file_scope():
    assets = ProjectAssetService(MemoryRepository())
    designs = NativeDesignAssets(assets, engine='sqlite')
    reference = designs.apply(7, SCOPE, 'read', {'kind': 'catalog'})['assetRef']
    assert reference['projectId'] == 'sqlite-designs-7'
    body = {'kind': 'catalog', 'assetRef': reference,
            'snapshot': deepcopy(SNAPSHOT), 'baseline': deepcopy(SNAPSHOT)}
    saved = designs.apply(7, SCOPE, 'save', body)
    assert saved['version'] == 1 and saved['baseline'] == SNAPSHOT
    with pytest.raises(ProjectAssetConflict):
        designs.apply(7, SCOPE, 'save', body)

    body['assetRef'] = saved['assetRef']
    body['snapshot']['files']['catalog.ddn'] += '\n// edited SQLite design'
    current = designs.apply(7, SCOPE, 'save', body)
    old = designs.apply(7, SCOPE, 'read', {'kind': 'catalog', 'version': 1})
    assert old['snapshot'] == old['baseline'] == SNAPSHOT
    assert current['baseline'] == SNAPSHOT
    assert 'edited SQLite design' in current['snapshot']['files']['catalog.ddn']

    commits = assets.repository.commits
    for owner, scope, engine in (
            (8, SCOPE, 'sqlite'),
            (7, {**SCOPE, 'database_target_id': 'other-file'}, 'sqlite'),
            (7, SCOPE, 'duckdb')):
        with pytest.raises(ProjectAssetError):
            NativeDesignAssets(assets, engine=engine).apply(
                owner, scope, 'save', {**body, 'assetRef': current['assetRef']})
    assert assets.repository.commits == commits


def test_sqlite_workspace_design_requires_native_file_endpoint():
    assets = ProjectAssetService(MemoryRepository())
    context = SimpleNamespace(profile_id='sqlite-native',
        provider_id='org.cdeadmin.sqlite', endpoint_id='endpoint-one')
    service = object.__new__(ProviderWorkspaceService)
    service.endpoint_service = SimpleNamespace(workspace=Mock(return_value=(context, {}, None)))
    service.firebird_design_assets = SimpleNamespace(assets=assets)
    service._principal_id = Mock(return_value=7)
    request = {'kind': 'catalog', 'database_target_id': 'file-one'}
    result = service.sqlite_design_asset(SimpleNamespace(), 'read', request)
    assert result['scope']['endpoint_id'] == 'endpoint-one'
    assert result['scope']['database_target_id'] == 'file-one'
    with pytest.raises(ProviderWorkspaceError):
        service.sqlite_design_asset(SimpleNamespace(), 'read', {**request, 'database_target_id': ''})
    service.endpoint_service.workspace.return_value = (
        SimpleNamespace(profile_id='duckdb-native',
                        provider_id='org.cdeadmin.duckdb', endpoint_id='endpoint-one'), {}, None)
    with pytest.raises(ProviderWorkspaceError, match='SQLite endpoint'):
        service.sqlite_design_asset(SimpleNamespace(), 'read', request)
