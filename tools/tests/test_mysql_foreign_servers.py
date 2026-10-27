"""Native foreign-server addresses, secret handling and connection ownership."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family import foreign_servers as servers
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin import catalog_for_engine


def draft():
    return {'name': 'remote : . ` ü', 'wrapper': 'mysql',
        'include_host': True, 'host': "host ' \\",
        'include_database': True, 'database': "db ' ü \\",
        'include_username': True, 'username': "user ' ü \\",
        'include_password': True, 'password': "secret ' ü \\",
        'include_port': True, 'port': '2147483647',
        'include_socket': True, 'socket': "socket ' ü \\",
        'include_owner': True, 'owner': "owner ' ü \\"}


def test_options_are_bound_and_exact_identifiers_are_quoted():
    compiled = servers.compile_operation('create', draft())
    statement = compiled['statements'][0]
    assert statement['source'].startswith('CREATE SERVER `remote : . `` ü` FOREIGN DATA WRAPPER %s')
    assert 'PORT 2147483647' in statement['source']
    assert statement['parameters'] == tuple(draft()[key] for key in
        ('wrapper', 'host', 'database', 'username', 'password', 'socket', 'owner'))
    assert draft()['password'] not in statement['source']


@pytest.mark.parametrize('change', [
    {'include_password': False}, {'port': '2147483648'}, {'port': True},
    {'host': 'nul\x00host'}, {'name': ''}, {'name': 'x'*65},
    {'source': 'DROP DATABASE mysql'}, {'include_host': 1},
])
def test_invalid_native_options_never_reach_a_driver(change):
    with pytest.raises(RelationalClientError):
        servers.compile_operation('create', {**draft(), **change})


def test_form_keeps_password_private_and_alter_options_explicit():
    catalog = MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    item = next(row for row in catalog['objects'] if row['resource_kind'] == servers.KIND)
    assert {row['operation_id'] for row in item['operations']} == {'inspect', 'create', 'alter', 'drop'}
    fields = {row['field_id']: row for row in MYSQL_ADMINISTRATION._form(servers.KIND, 'alter')['fields']}
    assert fields['password']['control'] == 'password' and fields['password']['sensitive']
    assert 'initial_value_path' not in fields['password']
    assert all(fields['include_'+key]['default'] is False for key in servers.OPTIONS)
    assert type(MARIADB_ADMINISTRATION) is not type(MYSQL_ADMINISTRATION)


@pytest.mark.parametrize('field,value', [('resource_id', 'server-link:other'),
    ('display_path', ['other']), ('display_name', 'other')])
def test_metadata_cannot_redirect_an_existing_native_identity(field, value):
    target = {'resource_id': 'server-link:original', 'resource_kind': servers.KIND,
        'display_name': 'original', 'display_path': ['original'], 'native': {'server_name': 'original'}}
    target[field] = value
    with pytest.raises(RelationalClientError, match='resource address'):
        servers.compile_operation('drop', {'confirmation': 'original'}, target)


def test_ddl_never_borrows_a_caller_connection():
    client = Mock()
    with pytest.raises(RelationalClientError, match='independently owned'):
        servers.apply(client, {}, object())
    client._connect.assert_not_called()


def test_review_and_compiled_statement_are_required_before_connecting():
    client = Mock();compiled = servers.compile_operation('create', draft())
    with pytest.raises(RelationalClientError, match='instance and principal'):
        servers.apply(client, {'provider_payload': {'compiled': compiled}})
    changed = deepcopy(compiled);changed['statements'][0]['source'] = 'DROP DATABASE mysql'
    with pytest.raises(RelationalClientError, match='operation changed'):
        servers.apply(client, {'provider_payload': {'compiled': changed}})
    client._connect.assert_not_called()


def test_server_inventory_is_not_limited_to_curated_variable_names():
    from pgadmin.cdeadmin.providers.mysql_family.mysql_server_catalog import SECTIONS
    source = next(row[2] for row in SECTIONS if row[0] == 'system-variables')
    assert 'WHERE' not in source and 'variables_info' in source and 'persisted_variables' in source
    source = next(row[2] for row in SECTIONS if row[0] == 'foreign-servers')
    assert 'Password' not in source


def test_post_acknowledgement_read_failure_is_not_reported_as_undispatched():
    client = Mock();handle = client._connect.return_value;cursor = handle.cursor.return_value
    compiled = servers.compile_operation('create', draft())
    observed = {'version': '9.7.0', 'server_uuid': 'owned-instance',
        'effective_principal': 'operator@%', 'authenticated_principal': 'operator@host', 'active_roles': 'NONE'}
    compiled['mysql_foreign_server']['review'] = {'execution_identity': observed,
        'credential_nonce': 'nonce', 'credential_stamp': None}
    cursor.fetchone.side_effect = [tuple(observed.values()), None, None, RuntimeError('read failed after DDL')]
    cursor.warnings = None
    with pytest.raises(RelationalClientError) as failure:
        servers.apply(client, {'provider_payload': {'compiled': compiled, 'route': {'host': 'owned'}}})
    assert failure.value.native_dispatched and failure.value.native_acknowledged
    assert failure.value.automatic_retry is False
    assert len([call for call in cursor.execute.call_args_list if call.args[0].startswith('CREATE SERVER')]) == 1
    client._forget_and_close.assert_called_once_with(handle)
