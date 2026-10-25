"""Descriptor field admission preserves backend validation and secret handling."""
from copy import deepcopy

import pytest
from test_cdeadmin_visual_admin import NativeAdapter, Permissions, context
from test_cdeadmin_relational_visual_admin import AdministrationClient
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MYSQL_ADMINISTRATION, MySQLDBAPIClient,
)
from pgadmin.cdeadmin.visual_admin import (
    ProviderVisualAdministration, VisualAdminValidationError,
)


class IndexAdapter(AdministrationClient):
    admin_operation_field_contract = MySQLDBAPIClient.admin_operation_field_contract


def test_index_api_admits_typed_records_defaults_and_existing_scalar_lists():
    client = IndexAdapter(MYSQL_ADMINISTRATION)
    provider = ProviderVisualAdministration(context(), Permissions(), 'mysql', '9.7.0', client)
    for columns in (['id'], [{'name': 'id', 'direction': 'DESC'}],
                    [{'expression': 'lower(word)'}]):
        request = {'resource_kind': 'index', 'operation_id': 'create',
                   '_provider_route': {'host': 'owned', 'user': 'operator'},
                   'draft': {'name': 'owned', 'table': ['db', 't'],
                             'columns': columns, 'unique': True}}
        result = provider.validate(request)
        assert result['valid'], result['errors']
        assert result['draft']['columns'] == columns
        assert result['draft']['unique'] is True
        assert result['draft']['visible'] is True
        # Plan through the real native compiler, not the legacy catalog form.
        planned = provider.plan(request)
        assert 'CREATE UNIQUE INDEX' in planned['command_preview']['statements'][0]['source']


@pytest.mark.parametrize('draft,code', [
    ({'visible': 'false'}, 'type'),
    ({'columns': {'expression': 'id'}}, 'type'),
    ({'table': ['db', 1]}, 'type'),
    ({'algorithm': 'INSTANT'}, 'choice'),
    ({'secondary_engine_attribute': []}, 'type'),
    ({'invented_option': True}, 'unknown_fields'),
    ({'columns': [{'name': 'id', 'expression': 'id+1'}]}, 'invalid_mysql_index'),
])
def test_index_api_keeps_transport_and_native_rejection(draft, code):
    provider = ProviderVisualAdministration(
        context(), Permissions(), 'mysql', '9.7.0', IndexAdapter(MYSQL_ADMINISTRATION))
    result = provider.validate({'resource_kind': 'index', 'operation_id': 'create',
        'draft': {'name': 'owned', 'table': 'db.t', 'columns': ['id'], **draft}})
    assert not result['valid']
    assert any(error['code'] == code for error in result['errors']), result


def test_provider_contract_fallback_preserves_legacy_validation():
    client = NativeAdapter()
    client.admin_operation_field_contract = lambda request: None
    provider = ProviderVisualAdministration(context(), Permissions(), 'mysql', '9.7.0', client)
    result = provider.validate({'resource_kind': 'database', 'operation_id': 'create',
                                'draft': {'name': 'owned'}})
    assert result['valid']
    assert client.validated[-1]['draft']['name'] == 'owned'


@pytest.mark.parametrize('contract', [[], {'fields': {}}, {'fields': [{}]}])
def test_malformed_backend_contract_fails_before_planning(contract):
    client = NativeAdapter()
    client.admin_operation_field_contract = lambda request: contract
    provider = ProviderVisualAdministration(context(), Permissions(), 'mysql', '9.7.0', client)
    with pytest.raises(VisualAdminValidationError, match='field contract'):
        provider.plan({'resource_kind': 'database', 'operation_id': 'create',
                       'draft': {'name': 'owned'}})


def test_descriptor_secret_is_retained_for_native_planner_and_redacted_publicly():
    client = NativeAdapter()
    fields = [{'field_id': 'name', 'label': 'Name', 'control': 'text', 'required': True},
              {'field_id': 'password', 'label': 'Password', 'control': 'password',
               'required': True, 'sensitive': True}]
    client.admin_operation_field_contract = lambda request: {'fields': deepcopy(fields)}
    captured = []
    def plan(request):
        captured.append(request)
        return {'command_preview': None, 'provider_payload': {}}
    client.plan_admin_operation = plan
    provider = ProviderVisualAdministration(context(), Permissions(), 'mysql', '9.7.0', client)
    request = {'resource_kind': 'database', 'operation_id': 'create',
               'draft': {'name': 'owned', 'password': 'private fixture'}}
    assert provider.validate(request)['draft']['password'] != 'private fixture'
    assert provider.plan(request)['draft']['password'] != 'private fixture'
    assert captured[-1]['draft']['password'] == 'private fixture'
