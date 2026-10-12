import config  # Initialize application configuration before ORM imports.
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.workspace.firebird_search import search, validate
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError


def snapshot():
    return {'generation': 'g', 'resources': [
        {'resource_id': 'db', 'resource_kind': 'database', 'display_name': 'DB', 'native': {
            'catalog_observations': [{'section': 'security', 'available': False}]}},
        {'resource_id': 'p', 'resource_kind': 'procedure', 'display_name': 'P', 'display_path': ['P'],
         'native': {'body_source': 'select Straße from T', 'description': 'stored program',
                    'password': 'SECRET_NOT_SEARCHABLE', 'parameters': [{'name': 'INPUT_F'}]}},
        {'resource_id': 'v', 'resource_kind': 'view', 'display_name': 'V',
         'native': {'ddl_unavailable_reason': 'unavailable'}}]}


def test_literal_fields_visibility_and_unicode():
    result = search(snapshot(), 'strasse', {'source'})
    assert [item['resource_id'] for item in result['matches']] == ['p']
    assert result['missing_ddl_count'] == 1
    assert result['catalog_observations'][0]['available'] is False
    assert search(snapshot(), 'input_f', {'fields'})['match_count'] == 1
    assert search(snapshot(), 'secret_not_searchable', {'source', 'fields'})['match_count'] == 0
    assert search(snapshot(), 'strasse', {'source'}, 'table')['match_count'] == 0
    assert search(snapshot(), '.*', {'source'})['match_count'] == 0
    assert search(snapshot(), 'p', {'name'}, limit=0)['truncated']


@pytest.mark.parametrize('change', [{'query': ''}, {'query': 'a'*257}, {'fields': ['credentials']}, {'fields': []}, {'target_id': None}, {'owner': 'other'}, {'query': '\0'}])
def test_request_validation(change):
    with pytest.raises(ValueError):
        validate({'target_id': 'db', 'query': 'x', 'fields': ['name'], **change})


def test_host_validates_registration_and_uses_explicit_target():
    service = object.__new__(ProviderWorkspaceService)
    service.endpoint_service = SimpleNamespace(database_catalog=Mock(return_value={'targets': [{'target_id': 'db'}]}))
    service.navigator_snapshot = Mock(return_value=snapshot())
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='firebird-native'))
    request = {'target_id': 'db', 'query': 'program', 'fields': ['description']}
    assert service.firebird_metadata_search(server, request)['match_count'] == 1
    service.navigator_snapshot.assert_called_once_with(server, database_target_id='db')
    with pytest.raises(ProviderWorkspaceError):
        service.firebird_metadata_search(server, {**request, 'target_id': 'unregistered'})
    server.endpoint_profile.profile_id = 'mysql-native'
    with pytest.raises(ProviderWorkspaceError):
        service.firebird_metadata_search(server, request)
