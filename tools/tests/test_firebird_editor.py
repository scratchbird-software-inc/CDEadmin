from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.workspace.firebird_editor import languages
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError


def test_native_lexical_display_hints_do_not_change_other_engines():
    source = [{'language_profile': 'firebird-sql'}, {'language_profile': 'mysql-sql'}]
    result = languages(source)
    assert result[1] == source[1]
    assert 'editor' not in source[0]
    assert {'SELECT', 'RDB$GET_CONTEXT', 'DECFLOAT'} <= set(result[0]['editor']['keywords'].split())
    assert result[0]['editor']['reference_version'] == '5.0.4'


def test_metadata_completion_preserves_target_and_omits_source_and_credentials():
    service = object.__new__(ProviderWorkspaceService)
    service.navigator_snapshot = Mock(return_value={'generation': 'fresh', 'resources': [
        {'resource_kind': 'table', 'resource_id': 't', 'display_name': 'T', 'display_path': ['db', 'T'],
         'native': {'source': 'unneeded'}, 'credentials': 'not returned'},
        {'resource_kind': 'user', 'display_name': 'unneeded'}]})
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='firebird-native'))
    result = service.firebird_editor_metadata(server, 'target')
    service.navigator_snapshot.assert_called_once_with(server, database_target_id='target')
    assert len(result['resources']) == 1
    assert 'native' not in result['resources'][0] and 'credentials' not in result['resources'][0]
    server.endpoint_profile.profile_id = 'mysql'
    with pytest.raises(ProviderWorkspaceError):
        service.firebird_editor_metadata(server, 'target')
