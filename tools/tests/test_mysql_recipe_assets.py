import copy
import pytest
from tools.tests.test_cdeadmin_project_assets import MemoryRepository
from pgadmin.cdeadmin.workspace.assets import ProjectAssetService, ProjectAssetError, ProjectAssetConflict
from pgadmin.cdeadmin.workspace.mysql_recipe_assets import MySQLRecipeAssets

SCOPE = {'endpoint_id': 'endpoint', 'database_target_id': 'database'}
RECIPE = {'format': 'scratchrobin.mysql.test-data@1', 'scope': SCOPE, 'seed': 1, 'tables': []}


def test_recipe_revisions_survive_recreated_service_with_current_version_cas():
    assets = ProjectAssetService(MemoryRepository())
    recipes = MySQLRecipeAssets(assets)
    assert recipes.apply(1, SCOPE, 'read', {})['current_version'] == 0
    request = {'expected_version': 0, 'recipe': copy.deepcopy(RECIPE)}
    first = recipes.apply(1, SCOPE, 'save', request)
    assert first['version'] == 1 and not first['executed']
    with pytest.raises(ProjectAssetConflict):
        recipes.apply(1, SCOPE, 'save', request)
    request.update(expected_version=1, recipe={**RECIPE, 'seed': 2})
    recipes.apply(1, SCOPE, 'save', request)
    restarted = MySQLRecipeAssets(assets)
    historical = restarted.apply(1, SCOPE, 'read', {'version': 1})
    assert historical['recipe']['seed'] == 1 and historical['current_version'] == 2
    assert restarted.apply(1, SCOPE, 'read', {})['recipe']['seed'] == 2
    assert restarted.apply(2, SCOPE, 'read', {})['recipe'] is None
    assert restarted.apply(1, {**SCOPE, 'database_target_id': 'other'}, 'read', {})['recipe'] is None


def test_cross_database_recipe_and_secret_content_fail_before_repository_mutation():
    assets = ProjectAssetService(MemoryRepository())
    recipes = MySQLRecipeAssets(assets)
    for recipe in ({**RECIPE, 'scope': {}}, {**RECIPE, 'password': 'must-not-store'}):
        with pytest.raises(ProjectAssetError):
            recipes.apply(1, SCOPE, 'save', {'expected_version': 0, 'recipe': recipe})
    assert assets.repository.commits == 0
