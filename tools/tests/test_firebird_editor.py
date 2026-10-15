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



def test_completion_includes_public_native_families_without_source_text():
    from pgadmin.cdeadmin.workspace.firebird_editor import metadata
    entries=[]
    for kind in ('procedure','function','external-function','package','sequence','domain','exception','collation','character-set'):
        entries.append({'resource_kind':kind,'resource_id':kind,'display_name':kind,'display_path':[kind],
            'native':{'metadata_source':'private source','parameters':[{'name':'ARG','mode':'input','position':0,'default_source':"secret"}]}})
    entries.append({'resource_kind':'function','resource_id':'private','display_name':'HIDDEN','native':{'package':'PKG','private_flag':1}})
    value=metadata({'generation':'g','resources':entries})
    assert len(value['resources'])==9
    assert 'private source' not in str(value) and 'default_source' not in str(value)
    assert value['resources'][0]['parameters']==[{'name':'ARG','mode':'input','position':0}]
