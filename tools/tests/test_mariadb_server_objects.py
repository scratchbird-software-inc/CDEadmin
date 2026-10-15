"""Native global objects preserve scope, selected options and secret bindings."""
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.providers import mariadb_server_objects as objects
from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine


SERVER = {'resource_kind': 'server-link', 'display_path': ['r`é']}
UDF = {'resource_kind': 'loadable-function', 'display_path': ['u`é'],
       'extensions': {'mariadb': {'native': {'registration_origin': 'mysql.func'}}}}


def test_selected_server_options_bind_secrets_without_overwriting_omitted_values():
    result = objects.compile_operation('server-link', 'alter', {
        'change_password': True, 'password': "secret'\\",
        'host': 'unselected', 'port': 3306}, SERVER)
    assert result == {'source': 'ALTER SERVER `r``é` OPTIONS (PASSWORD %s)',
                      'parameters': ("secret'\\",)}
    result = objects.compile_operation('server-link', 'create', {
        'name': 'r`é', 'wrapper': 'mysql', 'port': 3307}, None)
    assert 'FOREIGN DATA WRAPPER `mysql`' in result['source']
    assert result['parameters'][4] == 3307


@pytest.mark.parametrize('draft', [{}, {'change_host': 'true'},
    {'change_port': True, 'port': '3306'}, {'change_port': True, 'port': 65536},
    {'change_host': True, 'host': 'bad\x00'}, {'options': 'PASSWORD raw'}])
def test_unadmitted_server_changes_refuse_before_dispatch(draft):
    with pytest.raises(RelationalClientError):
        objects.compile_operation('server-link', 'alter', draft, SERVER)


def test_udf_is_distinct_from_stored_routines_and_mariadb_has_no_mysql_libraries():
    assert objects.compile_operation('loadable-function', 'drop', {}, UDF)['source'] == 'DROP FUNCTION `u``é`'
    with pytest.raises(RelationalClientError):
        objects.compile_operation('loadable-function', 'drop', {}, {**UDF, 'resource_kind': 'function'})
    assert not MARIADB_ADMINISTRATION.supports('library', 'create')
    catalog = MARIADB_ADMINISTRATION.catalog(catalog_for_engine('mariadb'))
    for kind, operations in objects.OPERATIONS.items():
        row = next(item for item in catalog['objects'] if item['resource_kind'] == kind)
        assert {item['operation_id'] for item in row['operations']} == operations | {'inspect'}
        for operation in row['operations']:
            if operation['operation_id'] == 'inspect': continue
            assert operation['form']['form_id'].startswith('mariadb.')


def test_global_udf_dispatch_refuses_borrowed_or_database_selected_connection():
    compiled = MARIADB_ADMINISTRATION._compile({'resource_kind': 'loadable-function',
        'operation_id': 'drop', 'draft': {}, 'target_resource': UDF})
    request = {'provider_payload': {'route': {'database': 'demo'}, 'compiled': compiled}}
    client = Mock(); connection = Mock(); client._connect.return_value = connection
    with pytest.raises(RelationalClientError, match='owned connection'):
        MARIADB_ADMINISTRATION.apply(client, request, connection=connection)
    client._connect.assert_not_called()
    cursor = connection.cursor.return_value; cursor.fetchone.return_value = ('unexpected',)
    client.config.execute_on_connection = False
    with pytest.raises(RelationalClientError, match='dispatch refused'):
        MARIADB_ADMINISTRATION.apply(client, request)
    assert client._connect.call_args.args[0]['route']['database'] is None
    cursor.execute.assert_called_once_with('SELECT DATABASE()')
    client._forget_and_close.assert_called_once_with(connection)
