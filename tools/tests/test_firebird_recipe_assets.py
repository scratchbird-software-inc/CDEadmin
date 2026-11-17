"""Private immutable recipe revisions and native-input admission boundaries."""
import copy

import pytest

from tools.tests.test_cdeadmin_project_assets import MemoryRepository
from pgadmin.cdeadmin.workspace.assets import ProjectAssetService, ProjectAssetError, ProjectAssetConflict
from pgadmin.cdeadmin.workspace.firebird_recipe_assets import FirebirdRecipeAssets, validate, FORMAT

SCOPE = {'endpoint_id': 'owned', 'database_target_id': 'native:42'}
RECIPE = {'format': FORMAT, 'scope': SCOPE, 'seed': 1, 'tables': [
    {'table': 'Owned 雪', 'count': 2, 'columns': {'ID': {'kind': 'sequential', 'start': '9007199254740993', 'step': '1'}}}]}
RESOURCES = [{'resource_kind': 'table', 'display_name': 'Owned 雪', 'native': {'system_object': False}},
             {'resource_kind': 'column', 'display_name': 'ID', 'display_path': ['Owned 雪', 'ID'], 'native': {}}]


def test_private_revisions_preserve_exact_values_and_isolate_owner_engine_endpoint_target():
    assets = ProjectAssetService(MemoryRepository())
    service = FirebirdRecipeAssets(assets)
    request = {'recipe': copy.deepcopy(RECIPE), 'expected_version': 0}
    first = service.apply(1, SCOPE, 'save', request, RESOURCES)
    assert first['version'] == 1 and not first['executed']
    assert first['requires_native_preview'] and first['contains_user_values']
    assert first['source_control_eligible'] is False
    with pytest.raises(ProjectAssetConflict):
        service.apply(1, SCOPE, 'save', request, RESOURCES)
    service.apply(1, SCOPE, 'save', {'recipe': {**RECIPE, 'seed': 2},
                  'expected_version': 1}, RESOURCES)
    restarted = FirebirdRecipeAssets(ProjectAssetService(assets.repository))
    old = restarted.apply(1, SCOPE, 'read', {'version': 1})
    assert old['recipe'] == RECIPE and old['current_version'] == 2
    assert restarted.apply(2, SCOPE, 'read', {})['recipe'] is None
    for field in SCOPE:
        assert restarted.apply(1, {**SCOPE, field: 'other'}, 'read', {})['recipe'] is None
    from pgadmin.cdeadmin.workspace.mysql_recipe_assets import MySQLRecipeAssets
    assert MySQLRecipeAssets(assets).apply(1, SCOPE, 'read', {})['recipe'] is None


@pytest.mark.parametrize('source', [
    {'kind': 'default'}, {'kind': 'constant', 'value': {
        'type': 'int128', 'value': '170141183460469231731687303715884105727'}},
    {'kind': 'sequential', 'start': '-99999999999999999999999999999999999999', 'step': '1'},
    {'kind': 'random-integer', 'min': '0', 'max': '4294967295'},
    {'kind': 'choice', 'values': [None, True, '0.100000000000000000001']},
    {'kind': 'file', 'values': ['雪', {'type': 'binary', 'value': 'AP8='}], 'nullPercent': 12.5},
    {'kind': 'existing', 'table': 'Owned 雪', 'column': 'ID'},
    {'kind': 'generated', 'table': 'not selected', 'column': 'not selected', 'nullPercent': 100},
])
def test_source_contract_retains_exact_native_values_without_materializing_or_dispatching(source):
    recipe = copy.deepcopy(RECIPE)
    recipe['tables'][0]['columns']['ID'] = source
    assert validate(recipe, SCOPE, RESOURCES) == recipe


@pytest.mark.parametrize('source', [
    {'kind': []}, {'kind': 'unknown'}, {'kind': 'constant'},
    {'kind': 'constant', 'value': 0.1}, {'kind': 'constant', 'value': -0.0},
    {'kind': 'constant', 'value': 9007199254740993},
    {'kind': 'choice', 'values': []}, {'kind': 'file', 'values': list(range(1001))},
    {'kind': 'sequential', 'start': '1e3', 'step': '1'},
    {'kind': 'sequential', 'start': '1', 'step': 1},
    {'kind': 'random-integer', 'min': '2', 'max': '1'},
    {'kind': 'random-integer', 'min': '0', 'max': '4294967296'},
    {'kind': 'default', 'nullPercent': True}, {'kind': 'default', 'nullPercent': 10**1000},
    {'kind': 'default', 'nullPercent': float('nan')},
    {'kind': 'default', 'sql': 'not executable'},
    {'kind': 'generated', 'table': 'missing', 'column': 'ID'},
    {'kind': 'generated', 'table': 'Owned 雪', 'column': 'ID'},
    {'kind': 'existing', 'table': 'missing', 'column': 'ID'},
])
def test_invalid_generator_refused_before_any_repository_mutation(source):
    recipe = copy.deepcopy(RECIPE)
    recipe['tables'][0]['columns']['ID'] = source
    assets = ProjectAssetService(MemoryRepository())
    with pytest.raises(ProjectAssetError):
        FirebirdRecipeAssets(assets).apply(1, SCOPE, 'save', {
            'recipe': recipe, 'expected_version': 0}, RESOURCES)
    assert assets.repository.commits == 0


@pytest.mark.parametrize('change', [
    {'scope': {}}, {'format': 'scratchrobin.mysql.test-data@1'}, {'seed': True},
    {'seed': 2**32}, {'tables': []}, {'tables': RECIPE['tables'] * 33},
    {'password': 'never persist'},
])
def test_invalid_recipe_scope_shape_and_bounds(change):
    with pytest.raises(ProjectAssetError):
        validate({**RECIPE, **change}, SCOPE, RESOURCES)


@pytest.mark.parametrize('native', [{'computed_source': 'ID + 1'}, {'identity_type': 0}])
def test_noninsertable_native_columns_are_refused(native):
    resources = copy.deepcopy(RESOURCES)
    resources[1]['native'] = native
    with pytest.raises(ProjectAssetError):
        validate(RECIPE, SCOPE, resources)


def test_size_depth_secret_and_missing_native_identity_fail_before_storage():
    for value in ('x' * 1024**2, {'password': 'must not store'}):
        recipe = copy.deepcopy(RECIPE)
        recipe['tables'][0]['columns']['ID'] = {'kind': 'constant', 'value': value}
        assets = ProjectAssetService(MemoryRepository())
        with pytest.raises(ProjectAssetError):
            FirebirdRecipeAssets(assets).apply(1, SCOPE, 'save', {
                'recipe': recipe, 'expected_version': 0}, RESOURCES)
        assert assets.repository.commits == 0
    value = None
    for _ in range(34):
        value = [value]
    recipe = copy.deepcopy(RECIPE)
    recipe['tables'][0]['columns']['ID'] = {'kind': 'constant', 'value': value}
    with pytest.raises(ProjectAssetError):
        validate(recipe, SCOPE, RESOURCES)
    with pytest.raises(ProjectAssetError):
        validate(RECIPE, SCOPE, [])


def test_parent_generated_dependencies_are_admitted_without_retaining_sample_or_materialized_rows():
    recipe = copy.deepcopy(RECIPE)
    recipe['tables'].append({'table': 'Child', 'count': 3, 'columns': {
        'FK': {'kind': 'generated', 'table': 'Owned 雪', 'column': 'ID'}}})
    assert validate(recipe, SCOPE) == recipe
    recipe['tables'][0]['columns']['ID'] = {'kind': 'generated', 'table': 'Child', 'column': 'FK'}
    with pytest.raises(ProjectAssetError):
        validate(recipe, SCOPE)
