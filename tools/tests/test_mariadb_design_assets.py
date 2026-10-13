"""MariaDB design revisions share storage but retain native owner/engine scopes."""
from copy import deepcopy
import pytest
from tools.tests.test_cdeadmin_project_assets import MemoryRepository
from tools.tests.test_firebird_design_assets import SNAPSHOT, SCOPE
from pgadmin.cdeadmin.workspace.assets import ProjectAssetService, ProjectAssetError, ProjectAssetConflict
from pgadmin.cdeadmin.workspace.firebird_design_assets import NativeDesignAssets


def test_native_maria_historical_design_and_optimistic_versions_preserve_original_baseline():
    assets = ProjectAssetService(MemoryRepository())
    designs = NativeDesignAssets(assets, engine='mariadb')
    original = designs.apply(1, SCOPE, 'read', {'kind': 'relations'})
    assert original['assetRef']['projectId'] == 'mariadb-designs-1'
    body = {'kind': 'relations', 'assetRef': original['assetRef'], 'snapshot': deepcopy(SNAPSHOT), 'baseline': deepcopy(SNAPSHOT)}
    saved = designs.apply(1, SCOPE, 'save', body)
    with pytest.raises(ProjectAssetConflict):designs.apply(1, SCOPE, 'save', body)
    body['assetRef'] = saved['assetRef'];body['snapshot']['files']['catalog.ddn'] += '\n// MariaDB authored design'
    current = designs.apply(1, SCOPE, 'save', body)
    historical = designs.apply(1, SCOPE, 'read', {'kind': 'relations', 'version': 1})
    assert historical['baseline'] == historical['snapshot'] == SNAPSHOT
    assert historical['assetRef']['assetVersion'] == current['version'] == 2
    assert current['baseline'] == SNAPSHOT
    assert 'authored design' in current['snapshot']['files']['catalog.ddn']


def test_native_maria_design_cannot_cross_owner_target_family_or_engine():
    assets = ProjectAssetService(MemoryRepository())
    designs = NativeDesignAssets(assets, engine='mariadb')
    reference = designs.apply(1, SCOPE, 'read', {'kind': 'catalog'})['assetRef']
    body = {'kind': 'catalog', 'assetRef': reference, 'snapshot': SNAPSHOT, 'baseline': SNAPSHOT}
    for owner, scope, engine, kind in [(2, SCOPE, 'mariadb', 'catalog'),
            (1, {**SCOPE, 'database_target_id': 'other'}, 'mariadb', 'catalog'),
            (1, SCOPE, 'mysql', 'catalog'), (1, SCOPE, 'mariadb', 'relations')]:
        with pytest.raises(ProjectAssetError):
            NativeDesignAssets(assets, engine=engine).apply(owner, scope, 'save', {**body, 'kind': kind})
    assert assets.repository.commits == 0
