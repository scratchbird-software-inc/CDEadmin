"""Native virtual-table renames preserve FTS postings, spatial data and shadow storage."""
from contextlib import closing
from dataclasses import dataclass
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import PROFILE
from pgadmin.cdeadmin.operations.store import JsonOperationStore
from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider,_create_client
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService


@pytest.mark.parametrize('module',['fts3','fts4','fts5','rtree','rtree_i32','geopoly'])
@pytest.mark.parametrize('failure',[None,'stale','lost_commit'])
def test_native_virtual_rename_uses_real_module_and_preserves_native_queries(tmp_path,module,failure):
    @dataclass(frozen=True)
    class Context:
        endpoint_id:str='endpoint'
        profile_id:str='sqlite-native'
    path=tmp_path/'virtual.sqlite';name='source:雪';target='renamed:雪';wide=9007199254740993
    columns='body' if module.startswith('fts') else 'id,x1,x2,y1,y2' if module.startswith('rtree') else 'label'
    with closing(sqlite3.connect(path)) as connection:
        assert PROFILE.accepts_runtime_version(sqlite3.sqlite_version)
        connection.execute('CREATE VIRTUAL TABLE "'+name+'" USING "'+module+'"('+columns+')')
        if module.startswith('fts'):connection.execute('INSERT INTO "'+name+'"(rowid,body) VALUES(?,?)',(wide,'native token 雪'))
        elif module.startswith('rtree'):connection.execute('INSERT INTO "'+name+'" VALUES(?,?,?,?,?)',(wide,1,2,3,4))
        else:connection.execute('INSERT INTO "'+name+'"(rowid,_shape,label) VALUES(?,geopoly_blob(?),?)',(wide,'[[0,0],[1,0],[1,1],[0,0]]','native 雪'))
        connection.execute('CREATE VIEW projection AS SELECT rowid AS native_id,* FROM "'+name+'"')
        original_rows=connection.execute('SELECT * FROM projection').fetchall();connection.commit()
        original=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client());route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        resources=provider.capture_catalog(route,include_system=False)['resources']
        observed=next(row for row in resources if row['display_path']==['main',name])
        assert observed['resource_kind']==('fts-table' if module.startswith('fts') else 'virtual-table')
        assert observed['native']['module_observation']['available'] and observed['native']['module_observation']['module']==module
        baseline=json.dumps(build_export(resources,endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        service=object.__new__(ProviderWorkspaceService);service.endpoint_service=Mock()
        service.endpoint_service.workspace.return_value=(Context(),{'route':route},None)
        service.endpoint_service.provider_registry.resolve.return_value=SimpleNamespace(instance=provider)
        service.operation_bus=SimpleNamespace(store=JsonOperationStore(tmp_path/'operations.json'))
        service.resource_service=Mock();service._principal_id=lambda _server:'owner'
        renames=[{'kind':'table','table':name,'to':target}]
        generated=service.sqlite_schema_rename_design('owned',{'database_target_id':'file','baseline':baseline,'renames':renames})
        documents={'database_target_id':'file','baseline':baseline,'desired':json.dumps(generated['snapshot']),'renames':renames}
        displayed=service.sqlite_schema_plan('owned',documents);assert displayed['ready_for_review'],displayed
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==original
            assert observer.execute('SELECT * FROM projection').fetchall()==original_rows
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        request={'database_target_id':'file',**{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True}
        if failure=='stale':
            with closing(sqlite3.connect(path)) as observer:
                observer.execute('CREATE VIEW appeared AS SELECT * FROM "'+name+'"');observer.commit()
                original=observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
        if failure=='lost_commit':
            connect=provider.client._connect
            class LostCommit:
                def __init__(self,connection):self.connection=connection
                def __getattr__(self,name):return getattr(self.connection,name)
                def commit(self):self.connection.commit();raise ConnectionError('Owned loss after real native virtual rename commit')
            provider.client._connect=Mock(side_effect=lambda payload:LostCommit(connect(payload)))
        result=service.sqlite_schema_application('owned','sqlite_schema_apply',request)
        expected='not_dispatched' if failure=='stale' else 'unknown_outcome' if failure=='lost_commit' else 'committed'
        assert result['state']==expected,result
        provider.client._connect=Mock(side_effect=AssertionError('native virtual rename review replayed'))
        assert service.sqlite_schema_application('owned','sqlite_schema_apply',request)['state']==expected
        provider.client._connect.assert_not_called()
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT * FROM projection').fetchall()==original_rows
            current=name if failure=='stale' else target
            if failure=='stale':assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==original
            else:assert not observer.execute('SELECT name FROM sqlite_schema WHERE name=?',(name,)).fetchall()
            if module.startswith('fts'):
                assert observer.execute('SELECT rowid,body FROM "'+current+'" WHERE "'+current+'" MATCH \'token\'').fetchall()==[(wide,'native token 雪')]
            elif module.startswith('rtree'):
                assert observer.execute('SELECT id FROM "'+current+'" WHERE x1<=1 AND x2>=2 AND y1<=3 AND y2>=4').fetchall()==[(wide,)]
            else:
                assert observer.execute('SELECT rowid,label FROM "'+current+'" WHERE geopoly_overlap(_shape,geopoly_blob(?))',('[[0,0],[1,0],[1,1],[0,0]]',)).fetchall()==[(wide,'native 雪')]
    finally:provider.close()
