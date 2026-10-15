"""Native server inventory projections, independent scope and bounded expansion."""
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.providers.mysql_family import mariadb_server_catalog as module

class Connection:
    server_status = 0
    def __init__(self, failure=None): self.calls=[];self.failure=failure
    def cursor(self, **options):
        parent=self
        class Cursor:
            def execute(self, source):
                parent.calls.append(source)
                if source.startswith('SET '):return
                if parent.failure and 'mysql.user' in source:raise parent.failure
                if source.startswith('SELECT VERSION'):
                    rows=[{'version':'12.2.2-MariaDB','server_uid':'server-id','lower_case_table_names':0,'sql_mode':'STRICT_TRANS_TABLES'}]
                elif 'SCHEMATA' in source:
                    rows=[{'schema_name':'demo','default_character_set_name':'utf8mb4'}]
                elif 'mysql.user' in source:
                    rows=[{'user':'test','host':'%','account_locked':'N'}]
                else: rows=[]
                self.description=[(key,) for key in rows[0]] if rows else []
                self.rows=[tuple(row.values()) for row in rows]
            def fetchmany(self,count):
                rows,self.rows=self.rows[:count],self.rows[count:];return rows
            def close(self):pass
        return Cursor()

def test_server_identity_and_credential_free_projections():
    connection=Connection();result=module.capture(connection)
    assert result['server_uid']=='server-id' and not result['complete']
    assert all(item['available'] for item in result['observations'])
    assert len({row['resource_id'] for row in result['resources']})==len(result['resources'])
    assert not any('authentication_string' in sql or 'SELECT *' in sql for sql in connection.calls)
    assert next(row for row in result['resources'] if row['resource_kind']=='user')['display_name']=='test / %'
    assert not any(row['resource_kind']=='role' for row in result['resources'])

def test_denied_sections_are_partial_but_source_failures_and_overflow_abort(monkeypatch):
    class Denied(Exception):errno=1142;sqlstate='42000'
    result=module.capture(Connection(Denied()))
    assert any(not row['available'] and row['section']=='accounts' for row in result['observations'])
    with pytest.raises(RuntimeError):module.capture(Connection(RuntimeError('connection lost')))
    monkeypatch.setattr(module,'MAX_FACTS',1)
    with pytest.raises(ValueError,match='20,000'):module.capture(Connection())

def test_busy_session_is_never_repurposed():
    connection=Connection();connection.server_status=1
    with pytest.raises(ValueError,match='idle'):module.capture(connection)
    assert not connection.calls

def test_host_expands_only_explicit_registered_targets_and_checks_native_server(monkeypatch):
    import config
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService,ProviderWorkspaceError
    from pgadmin.cdeadmin.providers.mysql_family.provider import MariaDBPilotProvider
    from pgadmin.cdeadmin.workspace import firebird_catalog_export
    service=object.__new__(ProviderWorkspaceService)
    service._principal_id=Mock(return_value=1)
    provider=Mock(spec=MariaDBPilotProvider)
    provider.capture_server_catalog.return_value=module.capture(Connection())
    context=SimpleNamespace(profile_id='mariadb-native',endpoint_id='endpoint')
    service.endpoint_service=SimpleNamespace(
        database_catalog=Mock(return_value={'targets':[{'target_id':'db','database':'demo','password':'must-not-leak'}]}),
        workspace=Mock(return_value=(context,{'route':{'database':'demo'}},None)),
        provider_registry=SimpleNamespace(resolve=Mock(return_value=SimpleNamespace(instance=provider))))
    service.mariadb_catalog=Mock(return_value={'server_uid':'server-id','snapshot':{}})
    monkeypatch.setattr(firebird_catalog_export,'build_export',lambda *args,**kwargs:{'snapshot':{}})
    server=SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='mariadb-native'))
    result=service.mariadb_server_catalog(server,{})
    assert not result['databases'] and 'must-not-leak' not in json.dumps(result)
    service.mariadb_catalog.assert_not_called()
    result=service.mariadb_server_catalog(server,{'targets':['db']})
    assert result['databases'][0]['target_id']=='db'
    service.mariadb_catalog.return_value={'server_uid':'another-server'}
    with pytest.raises(ProviderWorkspaceError,match='UID'):service.mariadb_server_catalog(server,{'targets':['db']})
    for request in ({'targets':['foreign']},{'targets':['db','db']},{'targets':['db']*33},{'include_system':1}):
        with pytest.raises(ProviderWorkspaceError):service.mariadb_server_catalog(server,request)
    service._principal_id.side_effect=ProviderWorkspaceError('Not owned')
    with pytest.raises(ProviderWorkspaceError,match='Not owned'):service.mariadb_server_catalog(server,{})


def test_explorer_preserves_same_name_plugins_with_different_native_types():
    from pgadmin.cdeadmin.providers.mysql_family.provider import _resources, MARIADB_PROFILE
    class Cursor:
        source = ''
        description = ()
        def execute(self, source, parameters=()): self.source = source
        def fetchall(self):
            if self.source == 'SHOW PLUGINS':
                return [('uuid', 'ACTIVE', 'DATA TYPE', None, 'GPL'),
                        ('uuid', 'ACTIVE', 'FUNCTION', None, 'GPL')]
            return []
        def close(self): pass
    class Native:
        def cursor(self): return Cursor()
    plugins = [row for row in _resources(Native(), {}, MARIADB_PROFILE) if row['resource_kind'] == 'plugin']
    assert len(plugins) == 2
    assert len({row['resource_id'] for row in plugins}) == 2
    assert {row['native']['plugin_type'] for row in plugins} == {'DATA TYPE', 'FUNCTION'}
    assert all(row['display_name'] == row['native']['plugin_name'] == 'uuid' for row in plugins)
