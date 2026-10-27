"""Server export preserves database identity and refuses unbounded selections."""
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.providers.postgresql import server_catalog as module


@pytest.mark.parametrize('ids', [[], [True], [0], [4294967296], [1,1], list(range(1,34)), ['42']])
def test_invalid_selections_do_not_connect(ids):
    provider = Mock()
    with pytest.raises(ValueError):module.bundle(provider, {'server_id': 1}, 'ep', ids)
    provider.open_session.assert_not_called()


def test_missing_and_unconnectable_database_never_falls_back(monkeypatch):
    monkeypatch.setattr(module, 'inventory', lambda *_: {'databases': [
        {'oid': 42, 'name': 'denied', 'allows_connections': True, 'connect_privilege': False}],
        'resources': [], 'observations': [], 'generation': 'g', 'warnings': []})
    provider = Mock()
    result = module.bundle(provider, {'server_id': 1}, 'ep', [42,43])
    assert [row['database_oid'] for row in result['databases']] == [42,43]
    assert all(not row['available'] for row in result['databases'])
    assert not result['all_selected_captured']
    provider.open_session.assert_not_called()
    assert result['server']['document']['provenance']['database_target_id'] == 'postgresql-server:1'


def test_native_connection_failure_is_redacted_and_not_retried(monkeypatch):
    monkeypatch.setattr(module, 'inventory', lambda *_: {'databases': [
        {'oid': 42, 'name': ' spaced name ', 'allows_connections': True, 'connect_privilege': True}],
        'resources': [], 'observations': [], 'generation': 'g', 'warnings': []})
    provider = Mock()
    provider.open_session.side_effect = RuntimeError('Secret native error text')
    result = module.bundle(provider, {'server_id': 1}, 'ep', [42])
    assert 'Secret' not in str(result)
    provider.open_session.assert_called_once_with({'route': {'server_id': 1, 'database_id': 42}}, _resolved_database=' spaced name ')
    assert result['databases'][0]['database_oid'] == 42


def test_server_only_native_document_preserves_properties_without_database_expansion():
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    import json
    server = {'resources': [{'resource_id':'postgresql:pg_authid:42','resource_kind':'role',
        'display_name':'Quoted / ü','display_path':['1','roles','Quoted / ü'],
        'native':{'system_object':False,'catalog_row':{'oid':42,'rolname':'Quoted / ü','rolcanlogin':True}}}],
        'observations':[{'section':'authentication-rules','available':False,'sqlstate':'42501'}],
        'warnings':['Credentials are redacted.'],'coverage':{'state':'partial'},'generation':'g'}
    result = module.export_inventory(server, 'endpoint', 1)
    model = read_catalog(json.dumps(result['snapshot']), engine='postgresql')
    assert model['provenance']['database_target_id'] == 'postgresql-server:1'
    assert model['provenance']['coverage'] == 'partial'
    assert model['rows']['postgresql:pg_authid:42']['native']['catalog_row']['rolcanlogin'] is True
    assert len(model['rows']) == 2
