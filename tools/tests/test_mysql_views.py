"""Exact native view options and lifecycle admission."""
import pytest
from pgadmin.cdeadmin.providers import mysql_views
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine

TARGET = {'display_path': ['d`é', 'v`é'], 'display_name': 'v`é'}


def test_view_create_and_alter_admit_native_clauses_without_replacement():
    draft = {'database': 'd`é', 'name': 'v`é', 'definition': "SELECT 1 AS id, 'semi;colon' AS note;",
             'columns': ['i`d', 'n'], 'algorithm': 'MERGE', 'sql_security': 'INVOKER',
             'definer_user': 'u`é', 'definer_host': 'local`host', 'check_option': 'LOCAL'}
    created = mysql_views.compile_operation('create', draft, None)
    assert created['parameters'] == ()
    assert created['source'].startswith('CREATE ALGORITHM=MERGE DEFINER=`u``é`@`local``host` SQL SECURITY INVOKER VIEW `d``é`.`v``é` (`i``d`, `n`) AS SELECT')
    assert created['source'].endswith('\nWITH LOCAL CHECK OPTION')
    assert 'REPLACE' not in created['source']
    altered = mysql_views.compile_operation('alter', {key: value for key, value in draft.items() if key not in {'database', 'name'}}, TARGET)
    assert altered['source'].startswith('ALTER ALGORITHM=MERGE')


@pytest.mark.parametrize('change', [
    {'definition': 'SELECT 1; DROP TABLE t'}, {'definition': 'SELECT 1 /*'},
    {'definition': 'DELETE FROM t'}, {'algorithm': 'MERGE; DROP TABLE t'},
    {'sql_security': 'ROOT'}, {'check_option': 'FULL'}, {'columns': ['a', 'a']},
    {'columns': [None]}, {'columns': 'a'}, {'definer_user': 'u'},
    {'definer_host': 'localhost'}, {'definer_user': 'x\x00', 'definer_host': 'h'},
    {'replace': True}, {'name': 'new'},
])
def test_view_refuses_partial_identity_extra_statements_and_unknown_options(change):
    with pytest.raises(RelationalClientError):
        mysql_views.compile_operation('alter', {'definition': 'SELECT 1', **change}, TARGET)


def test_trailing_comment_cannot_swallow_view_check_option():
    source = mysql_views.compile_operation('alter', {'definition': 'SELECT id FROM t -- comment', 'check_option': 'CASCADED'}, TARGET)['source']
    assert source.endswith('-- comment\nWITH CASCADED CHECK OPTION')


def test_mysql_catalog_retains_native_operations_after_descriptor_migration():
    catalog = MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    view = next(row for row in catalog['objects'] if row['resource_kind'] == 'view')
    operations = {row['operation_id']: row for row in view['operations']}
    assert MYSQL_ADMINISTRATION.supports('view', 'alter')
    assert not MARIADB_ADMINISTRATION.supports('view', 'alter')
    assert not operations['create']['target_required']
    assert operations['alter']['confirmation_required']
    assert not hasattr(mysql_views, 'form')
    request = {'resource_kind': 'view', 'operation_id': 'alter', 'draft': {'definition': 'SELECT 1'}, 'target_resource': TARGET}
    assert not MYSQL_ADMINISTRATION.validate(request)['errors']
    assert MYSQL_ADMINISTRATION._compile(request)['statements'][0]['source'].startswith('ALTER ALGORITHM=UNDEFINED')


def test_existing_visual_request_names_remain_exact_and_unambiguous():
    result = mysql_views.compile_operation('create', {'name': 'v', 'parent': 'db', 'query': 'SELECT 1'}, None)
    assert 'VIEW `db`.`v` AS SELECT 1' in result['source']
    with pytest.raises(RelationalClientError):
        mysql_views.compile_operation('create', {'name': 'v', 'parent': 'db', 'database': 'other', 'query': 'SELECT 1'}, None)
