"""Native characteristics preserve routine bodies; indexes retain table identity."""
import pytest
from pgadmin.cdeadmin.providers import mysql_object_changes as changes
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine

ROUTINE = {'display_name': 'f`é', 'display_path': ['db`é', 'f`é']}
INDEX = {'display_name': 'i`é', 'display_path': ['db`é', 't`é', 'i`é']}


def test_characteristics_are_bound_without_body_replacement():
    result = changes.compile_operation('function', 'alter', {
        'sql_security': 'INVOKER', 'data_access': 'NO SQL',
        'comment': "é'; DROP DATABASE x; --",}, ROUTINE)
    assert result['source'] == 'ALTER FUNCTION `db``é`.`f``é` SQL SECURITY INVOKER NO SQL COMMENT %s'
    assert result['parameters'] == ("é'; DROP DATABASE x; --",)
    assert 'DROP DATABASE' not in result['preview_source']
    with pytest.raises(RelationalClientError):
        changes.compile_operation('procedure', 'alter', {'comment': ''}, ROUTINE)


@pytest.mark.parametrize('draft', [{}, {'definition': 'RETURN 1'}, {'deterministic': True},
                                 {'sql_security': 'ROOT'}, {'data_access': 'READS SQL DATA; DROP TABLE t'},
                                 {'comment': None}, {'comment': '\x00'}])
def test_routine_alter_cannot_silently_recreate_or_change_unsupported_characteristics(draft):
    with pytest.raises(RelationalClientError):
        changes.compile_operation('function', 'alter', draft, ROUTINE)


def test_index_changes_use_database_table_and_index_as_separate_identifiers():
    assert changes.compile_operation('index', 'rename', {'new_name': 'new`é'}, INDEX)['source'] == 'ALTER TABLE `db``é`.`t``é` RENAME INDEX `i``é` TO `new``é`'
    assert changes.compile_operation('index', 'visibility', {'visibility': 'INVISIBLE'}, INDEX)['source'].endswith('ALTER INDEX `i``é` INVISIBLE')
    with pytest.raises(RelationalClientError):
        changes.compile_operation('index', 'visibility', {'visibility': 'HIDDEN'}, INDEX)
    with pytest.raises(RelationalClientError):
        changes.compile_operation('index', 'rename', {'new_name': 'x'}, {**INDEX, 'display_path': ['d','t','PRIMARY']})
    with pytest.raises(RelationalClientError):
        changes.compile_operation('index', 'rename', {'new_name': 'x'}, ROUTINE)


def test_catalog_forms_route_to_native_compiler_only_for_mysql():
    catalog = {row['resource_kind']: row for row in MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))['objects']}
    for kind, operations in changes.OPERATIONS.items():
        nodes = {row['operation_id']: row for row in catalog[kind]['operations']}
        for operation in operations:
            assert MYSQL_ADMINISTRATION.supports(kind, operation)
            assert not MARIADB_ADMINISTRATION.supports(kind, operation)
            assert nodes[operation]['target_required'] and nodes[operation]['confirmation_required']
            if kind != 'index':
                assert nodes[operation]['form']['form_id'] == 'mysql.' + kind + '.' + operation
            else:
                with pytest.raises(RelationalClientError):changes.form(kind,operation,MYSQL_ADMINISTRATION._field)
    request = {'resource_kind': 'function', 'operation_id': 'alter', 'target_resource': ROUTINE,
               'draft': {'comment': 'updated'}, '_provider_route': {'host': 'trusted'}}
    assert not MYSQL_ADMINISTRATION.validate(request)['errors']
    assert MYSQL_ADMINISTRATION._compile(request)['statements'][0]['parameters'] == ('updated',)
