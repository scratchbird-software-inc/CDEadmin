"""Exact native SRIDs, driver bindings, target selection and operation admission."""
from copy import deepcopy
from unittest.mock import Mock

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family import spatial_reference_systems as srs
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin import catalog_for_engine


def draft():
    return {'srs_id': '4294967001', 'name': "name ' ü \\", 'definition': 'native WKT',
        'include_organization': True, 'organization': "organization ' ü \\",
        'organization_id': '4294967295', 'include_description': True,
        'description': "description ' ü \\"}


@pytest.mark.parametrize('value', [True, 1.0, -1, '1e9', '01', '+1', '١', '4294967296'])
def test_non_native_srid_never_reaches_a_driver(value):
    with pytest.raises(RelationalClientError):
        srs.compile_operation('create', {**draft(), 'srs_id': value})


def test_native_literal_attributes_are_driver_parameters_with_exact_uint32():
    result = srs.compile_operation('create', draft())
    statement = result['statements'][0]
    assert statement['parameters'] == (draft()['name'], draft()['definition'], draft()['organization'], draft()['description'])
    assert 'IDENTIFIED BY 4294967295' in statement['source']
    assert '4294967001' in statement['source']
    assert draft()['description'] not in statement['source']


def test_only_mysql_exposes_native_srs_tasks():
    catalog = MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    object = next(row for row in catalog['objects'] if row['resource_kind'] == srs.KIND)
    assert {row['operation_id'] for row in object['operations']} == {'create', 'inspect', 'alter', 'drop'}
    assert not MARIADB_ADMINISTRATION.supports(srs.KIND, 'create')
    altered = MYSQL_ADMINISTRATION._form(srs.KIND, 'alter')
    field = next(row for row in altered['fields'] if row['field_id'] == 'definition')
    assert field['initial_value_path'] == ['definition', 'definition'] and field['submit_unchanged']


@pytest.mark.parametrize('change', [
    {'include_description': 'true'}, {'include_organization': 1}, {'srs_id': '0; DROP DATABASE mysql'},
    {'organization_id': '4294967296'}, {'name': 'line\nname'},
    {'definition': None}, {'source': 'DROP SERVER existing'},
])
def test_invalid_srs_options_are_refused(change):
    with pytest.raises(RelationalClientError):
        srs.compile_operation('create', {**draft(), **change})


def test_srs_ddl_does_not_borrow_an_interactive_connection():
    client = Mock()
    with pytest.raises(RelationalClientError, match='independently owned'):
        srs.apply(client, {}, object())
    client._connect.assert_not_called()


def test_changed_compiled_operation_cannot_dispatch():
    client = Mock()
    compiled = deepcopy(srs.compile_operation('create', draft()))
    compiled['statements'][0]['source'] = 'DROP DATABASE mysql'
    with pytest.raises(RelationalClientError, match='operation changed'):
        srs.apply(client, {'provider_payload': {'compiled': compiled}})
    client._connect.assert_not_called()


def test_native_review_identity_is_required_before_connection_or_dispatch():
    client = Mock()
    compiled = srs.compile_operation('create', draft())
    with pytest.raises(RelationalClientError, match='instance and principal'):
        srs.apply(client, {'provider_payload': {'compiled': compiled}})
    client._connect.assert_not_called()


def test_changed_principal_is_refused_before_native_ddl():
    client = Mock();handle = client._connect.return_value;cursor = handle.cursor.return_value
    compiled = srs.compile_operation('create', draft())
    compiled['mysql_spatial_reference']['execution_identity'] = {
        'version': '9.7.0', 'server_uuid': 'owned-instance',
        'effective_principal': 'original@%', 'authenticated_principal': 'original@host', 'active_roles': 'NONE'}
    cursor.fetchone.return_value = ('9.7.0', 'owned-instance', 'changed@%', 'changed@host', 'NONE')
    with pytest.raises(RelationalClientError, match='identity changed') as failure:
        srs.apply(client, {'provider_payload': {'compiled': compiled, 'route': {'host': 'owned'}}})
    assert failure.value.native_dispatched is False and failure.value.native_acknowledged is False
    cursor.execute.assert_called_once_with('SELECT VERSION(),@@server_uuid,CURRENT_USER(),USER(),CURRENT_ROLE()')


@pytest.mark.parametrize('field,value', [('resource_id', srs.KIND+':2'), ('display_path', ['2']), ('display_name', '2')])
def test_srs_metadata_cannot_redirect_an_existing_resource(field, value):
    target = {'resource_kind': srs.KIND, 'resource_id': srs.KIND+':1',
        'display_path': ['1'], 'display_name': '1', 'native': {'srs_id': 1}}
    target[field] = value
    with pytest.raises(RelationalClientError, match='resource address'):
        srs.compile_operation('drop', {'confirmation': target['display_name']}, target)
