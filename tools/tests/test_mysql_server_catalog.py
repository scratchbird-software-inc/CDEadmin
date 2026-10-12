"""Native server inventory projections, independent scope and bounded expansion."""
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.providers.mysql_family import mysql_server_catalog as module

class Connection:
    in_transaction = False
    def __init__(self, failure=None): self.calls=[];self.failure=failure
    def cursor(self, **options):
        parent=self
        class Cursor:
            def execute(self, source):
                parent.calls.append(source)
                if source.startswith('SET '):return
                if parent.failure and 'mysql.user' in source:raise parent.failure
                if source.startswith('SELECT VERSION'):
                    rows=[{'version':'9.7.0','server_uuid':'server-id','lower_case_table_names':0,'sql_mode':'STRICT_TRANS_TABLES'}]
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
    assert result['server_uuid']=='server-id' and not result['complete']
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
    connection=Connection();connection.in_transaction=True
    with pytest.raises(ValueError,match='idle'):module.capture(connection)
    assert not connection.calls

def test_host_expands_only_explicit_registered_targets_and_checks_native_server(monkeypatch):
    import config
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService,ProviderWorkspaceError
    from pgadmin.cdeadmin.providers.mysql_family.provider import MySQLPilotProvider
    from pgadmin.cdeadmin.workspace import firebird_catalog_export
    service=object.__new__(ProviderWorkspaceService)
    service._principal_id=Mock(return_value=1)
    provider=Mock(spec=MySQLPilotProvider)
    provider.capture_server_catalog.return_value=module.capture(Connection())
    context=SimpleNamespace(profile_id='mysql-native',endpoint_id='endpoint')
    service.endpoint_service=SimpleNamespace(
        database_catalog=Mock(return_value={'targets':[{'target_id':'db','database':'demo','password':'must-not-leak'}]}),
        workspace=Mock(return_value=(context,{'route':{'database':'demo'}},None)),
        provider_registry=SimpleNamespace(resolve=Mock(return_value=SimpleNamespace(instance=provider))))
    service.mysql_catalog=Mock(return_value={'server_uuid':'server-id','snapshot':{}})
    monkeypatch.setattr(firebird_catalog_export,'build_export',lambda *args,**kwargs:{'snapshot':{}})
    server=SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='mysql-native'))
    result=service.mysql_server_catalog(server,{})
    assert not result['databases'] and 'must-not-leak' not in json.dumps(result)
    service.mysql_catalog.assert_not_called()
    result=service.mysql_server_catalog(server,{'targets':['db']})
    assert result['databases'][0]['target_id']=='db'
    service.mysql_catalog.return_value={'server_uuid':'another-server'}
    with pytest.raises(ProviderWorkspaceError,match='UUID'):service.mysql_server_catalog(server,{'targets':['db']})
    for request in ({'targets':['foreign']},{'targets':['db','db']},{'targets':['db']*33},{'include_system':1}):
        with pytest.raises(ProviderWorkspaceError):service.mysql_server_catalog(server,request)
    service._principal_id.side_effect=ProviderWorkspaceError('Not owned')
    with pytest.raises(ProviderWorkspaceError,match='Not owned'):service.mysql_server_catalog(server,{})
