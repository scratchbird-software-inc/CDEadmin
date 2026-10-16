"""Durable native recipe revisions retain owner, engine and database isolation."""
import pytest
from tools.tests.test_cdeadmin_project_assets import MemoryRepository
from pgadmin.cdeadmin.workspace.assets import ProjectAssetService, ProjectAssetConflict, ProjectAssetError
from pgadmin.cdeadmin.workspace.mysql_recipe_assets import MySQLRecipeAssets


@pytest.mark.parametrize('engine', ['postgresql', 'duckdb', 'sqlite'])
def test_recipe_revisions_survive_restart_with_cas_and_scope_isolation(engine):
    assets = ProjectAssetService(MemoryRepository())
    scope = {'endpoint_id': 'owner endpoint', 'database_target_id': 'native:42'}
    recipe = {'format': f'scratchrobin.{engine}.test-data@1', 'scope': scope, 'seed': 1, 'tables': []}
    service = MySQLRecipeAssets(assets, engine=engine)
    request = {'expected_version': 0, 'recipe': recipe}
    assert service.apply(1, scope, 'save', request)['version'] == 1
    with pytest.raises(ProjectAssetConflict): service.apply(1, scope, 'save', request)
    service.apply(1, scope, 'save', {'expected_version': 1, 'recipe': {**recipe, 'seed': 2}})
    restarted = MySQLRecipeAssets(assets, engine=engine)
    old = restarted.apply(1, scope, 'read', {'version': 1})
    assert old['recipe']['seed'] == 1 and old['current_version'] == 2 and not old['executed']
    assert restarted.apply(2, scope, 'read', {})['recipe'] is None
    assert restarted.apply(1, {**scope, 'database_target_id': 'other'}, 'read', {})['recipe'] is None
    assert MySQLRecipeAssets(assets, engine='mysql').apply(1, scope, 'read', {})['recipe'] is None
    with pytest.raises(ProjectAssetError):
        service.apply(1, scope, 'save', {'expected_version': 2, 'recipe': {**recipe, 'format': 'scratchrobin.mysql.test-data@1'}})
