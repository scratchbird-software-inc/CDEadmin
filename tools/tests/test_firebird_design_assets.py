"""Versioned catalog/ERD storage uses shared ownership and optimistic versions."""
import copy
import pytest
from tools.tests.test_cdeadmin_project_assets import MemoryRepository
from pgadmin.cdeadmin.workspace.assets import (
    ProjectAssetService, ProjectAssetError, ProjectAssetConflict, ProjectAssetForbidden)
from pgadmin.cdeadmin.workspace.firebird_design_assets import FirebirdDesignAssets

SCOPE = {'endpoint_id': 'endpoint', 'database_target_id': 'db'}
SNAPSHOT = {'format': 'ddn-source-workspace@1', 'entry': 'catalog.ddn', 'view': 'inventory',
            'files': {'catalog.ddn': 'version ddn-next-1\nerd inventory\n    with\n        id inventory\n    Catalog\n'}}


def fixture():
    assets = ProjectAssetService(MemoryRepository())
    return FirebirdDesignAssets(assets), assets


def test_baseline_layout_and_historical_revision_are_preserved_with_current_cas():
    designs, assets = fixture()
    initial = designs.apply(1, SCOPE, 'read', {'kind': 'catalog'})
    assert assets.repository.commits == 0
    body = {'kind': 'catalog', 'assetRef': initial['assetRef'],
            'snapshot': copy.deepcopy(SNAPSHOT), 'baseline': copy.deepcopy(SNAPSHOT)}
    saved = designs.apply(1, SCOPE, 'save', body)
    with pytest.raises(ProjectAssetConflict):
        designs.apply(1, SCOPE, 'save', body)
    body['assetRef'] = saved['assetRef']
    body['snapshot']['files']['catalog.ddn'] += '\n// authored annotation and appearance'
    second = designs.apply(1, SCOPE, 'save', body)
    old = designs.apply(1, SCOPE, 'read', {'kind': 'catalog', 'version': 1})
    assert old['version'] == 1 and old['assetRef']['assetVersion'] == 2
    assert old['snapshot'] == old['baseline'] == SNAPSHOT
    assert second['baseline'] == SNAPSHOT
    assert 'authored' in second['snapshot']['files']['catalog.ddn']
    assert designs.apply(1, SCOPE, 'read', {'kind': 'relations'})['version'] == 0


def test_cross_scope_and_invalid_save_never_create_project():
    designs, assets = fixture()
    initial = designs.apply(1, SCOPE, 'read', {'kind': 'catalog'})
    body = {'kind': 'catalog', 'assetRef': initial['assetRef'], 'snapshot': SNAPSHOT, 'baseline': SNAPSHOT}
    for owner, scope in [(2, SCOPE), (1, {**SCOPE, 'database_target_id': 'other'})]:
        with pytest.raises(ProjectAssetError):
            designs.apply(owner, scope, 'save', body)
    with pytest.raises(ProjectAssetError):
        designs.apply(1, SCOPE, 'save', {**body, 'baseline': {}})
    assert assets.repository.commits == 0


def test_large_baseline_is_asset_content_not_truncated_metadata():
    designs, _ = fixture()
    initial = designs.apply(1, SCOPE, 'read', {'kind': 'relations'})
    source = {**SNAPSHOT, 'files': {'catalog.ddn': SNAPSHOT['files']['catalog.ddn'] + '\n//' + 'x' * 300000}}
    saved = designs.apply(1, SCOPE, 'save', {'kind': 'relations', 'assetRef': initial['assetRef'],
        'snapshot': source, 'baseline': source})
    assert saved['snapshot'] == saved['baseline'] == source


def test_foreign_owned_project_is_not_reused():
    designs, assets = fixture()
    assets.create_project(2, 'firebird-designs-1', {'name': 'Other owner'})
    with pytest.raises(ProjectAssetForbidden):
        designs.apply(1, SCOPE, 'read', {'kind': 'catalog'})
