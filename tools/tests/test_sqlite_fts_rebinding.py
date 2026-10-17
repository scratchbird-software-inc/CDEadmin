"""Native external-content FTS reconstruction, settings, review and failure effects."""
from contextlib import closing
import json
import sqlite3
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider,_create_client,_resource_id
from pgadmin.cdeadmin.providers.sqlite.fts_configuration import capture as configuration
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from test_sqlite_schema_virtual_creation import Context,workspace
from types import SimpleNamespace
from copy import deepcopy

CASES=[(module,'owner',failure) for module in ('fts4','fts5') for failure in (None,'stale','rollback','denied','lost_commit')]
CASES += [(module,mode,None) for module in ('fts4','fts5') for mode in ('chain','rowid','unrelated')]


@pytest.mark.parametrize('module,mode,failure',CASES)
def test_reviewed_native_external_content_rebinding_preserves_rows_and_settings(tmp_path,module,mode,failure):
    path=tmp_path/'external.sqlite';owner="Owner'雪";search="search'雪";new_owner='renamed:雪';new_search='rebuilt:雪';wide=9007199254740993
    quote=lambda value:'"'+value.replace('"','""')+'"'
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('CREATE TABLE '+quote(owner)+'(id INTEGER PRIMARY KEY AUTOINCREMENT,body TEXT,extra TEXT)')
        connection.executemany('INSERT INTO '+quote(owner)+'(id,body,extra) VALUES(?,?,?)',[(1,'native token','one'),(wide,'native 雪 token','two')])
        connection.execute('CREATE VIRTUAL TABLE '+quote(search)+' USING "'+module+'"(body,content=\'owner\'\'雪\''+(",content_rowid='id'" if module=='fts5' else '')+')')
        connection.execute('INSERT INTO '+quote(search)+'('+quote(search)+") VALUES('rebuild')")
        if module=='fts5':
            for key,value in [('automerge',8),('usermerge',4),('crisismerge',10),('deletemerge',11),('pgsz',1024),('hashsize',16384),('rank','bm25(2.0)'),('secure-delete',1),('insttoken',1)]:
                connection.execute('INSERT INTO '+quote(search)+'('+quote(search)+',rank) VALUES(?,?)',(key,value))
        else:connection.execute('INSERT INTO '+quote(search)+'('+quote(search)+") VALUES('automerge=4')")
        connection.execute('CREATE VIEW projection AS SELECT rowid,body FROM '+quote(search));connection.commit()
        original=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
        saved=configuration(connection,'main',search,module)
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client());route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        service=workspace(tmp_path,provider,route)
        baseline=json.dumps(build_export(provider.capture_catalog(route,include_system=False)['resources'],endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        renames=([{'kind':'table','table':owner,'to':new_owner}] if mode in {'owner','chain'} else
            [{'kind':'column','table':owner,'from':'id' if mode=='rowid' else 'extra','to':'new_id' if mode=='rowid' else 'new_extra'}])
        if mode=='chain':renames.append({'kind':'table','table':search,'to':new_search})
        required=mode in {'owner','chain'} or module=='fts5' and mode=='rowid'
        selected=[_resource_id('fts-table',['main'],search)] if required else []
        request={'database_target_id':'file','baseline':baseline,'renames':renames,'fts_rebindings':selected}
        generated=service.sqlite_schema_rename_design('owned',request)
        documents={**request,'desired':json.dumps(generated['snapshot'])}
        displayed=service.sqlite_schema_plan('owned',documents);assert displayed['ready_for_review'],displayed
        assert len(displayed['operations'][0]['fts_rebuilds'])==int(required)
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==original
            assert configuration(observer,'main',search,module)['commands']==saved['commands']
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        apply_request={'database_target_id':'file',**{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True}
        if failure=='stale':
            with closing(sqlite3.connect(path)) as observer:
                observer.execute('INSERT INTO '+quote(search)+'('+quote(search)+(',rank) VALUES(\'automerge\',6)' if module=='fts5' else ") VALUES('automerge=6')"));observer.commit()
                saved=configuration(observer,'main',search,module)
        if failure in {'rollback','denied','lost_commit'}:
            connect=provider.client._connect
            class Injected:
                def __init__(self,connection):
                    self.connection=connection
                    if failure=='denied':connection.set_authorizer(lambda action,*_args:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_DROP_VTABLE else sqlite3.SQLITE_OK)
                def __getattr__(self,name):return getattr(self.connection,name)
                def execute(self,source,*args):
                    result=self.connection.execute(source,*args)
                    if failure=='rollback' and source.startswith('CREATE VIRTUAL TABLE "main".'):
                        self.connection.execute('SELECT * FROM owned_injected_missing_relation')
                    return result
                def commit(self):
                    self.connection.commit()
                    if failure=='lost_commit':raise ConnectionError('Owned loss after actual external-content reconstruction commit')
            provider.client._connect=Mock(side_effect=lambda payload:Injected(connect(payload)))
        result=service.sqlite_schema_application('owned','sqlite_schema_apply',apply_request)
        expected='not_dispatched' if failure=='stale' else 'rolled_back' if failure in {'rollback','denied'} else 'unknown_outcome' if failure=='lost_commit' else 'committed'
        assert result['state']==expected,result
        provider.client._connect=Mock(side_effect=AssertionError('external-content review was replayed'))
        assert service.sqlite_schema_application('owned','sqlite_schema_apply',apply_request)['state']==expected
        provider.client._connect.assert_not_called()
        applied=failure in {None,'lost_commit'}
        actual_owner=new_owner if applied and mode in {'owner','chain'} else owner
        actual_search=new_search if applied and mode=='chain' else search
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT rowid,* FROM '+quote(actual_owner)+' ORDER BY rowid').fetchall()==[(1,1,'native token','one'),(wide,wide,'native 雪 token','two')]
            assert observer.execute('SELECT rowid,body FROM '+quote(actual_search)+' WHERE '+quote(actual_search)+" MATCH 'native' ORDER BY rowid").fetchall()==[(1,'native token'),(wide,'native 雪 token')]
            assert observer.execute('SELECT * FROM projection ORDER BY rowid').fetchall()==[(1,'native token'),(wide,'native 雪 token')]
            assert configuration(observer,'main',actual_search,module)['commands']==saved['commands']
            if not applied:assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==original
            else:
                observer.execute('INSERT INTO '+quote(actual_search)+'('+quote(actual_search)+(',rank) VALUES(\'integrity-check\',1)' if module=='fts5' else ") VALUES('integrity-check')"))
                assert observer.execute('SELECT seq FROM sqlite_sequence WHERE name=?',(actual_owner,)).fetchone()==(wide,)
    finally:provider.close()


@pytest.mark.parametrize('unnormalized',[False,True])
def test_native_fts_creation_preserves_settings_and_refuses_unreachable_catalog_values(tmp_path,unnormalized):
    path,target=tmp_path/'live.sqlite',tmp_path/'desired.sqlite'
    source='CREATE VIRTUAL TABLE "main"."added" USING "fts5"(body)'
    for file in (path,target):
        with closing(sqlite3.connect(file)) as connection:
            connection.execute('CREATE TABLE owner(id INTEGER PRIMARY KEY)')
            if file==target:
                connection.execute(source)
                for key,value in [('automerge',8),('pgsz',1024),('rank','bm25(2.0)'),('secure-delete',1)]:connection.execute('INSERT INTO added(added,rank) VALUES(?,?)',(key,value))
            connection.commit()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client());route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        def capture(file):return build_export(provider.capture_catalog({**route,'database':str(file)},include_system=False)['resources'],endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite',native_model=True)
        baseline,template=capture(path),capture(target);desired=deepcopy(baseline)
        for identity,row in template['rows'].items():
            if row['path'][:2]==['main','added']:
                desired['rows'][identity]=deepcopy(row)
                if row['kind']=='fts-table':
                    desired['rows'][identity]['native']['ddl']=source
                    if unnormalized:desired['rows'][identity]['native']['fts_configuration']['commands'][0][1]='8'
        def document(model):return json.dumps(build_export([{'resource_id':row['resource_id'],'resource_kind':row['kind'],'display_name':row['name'],'display_path':row['path'],'native':row['native']} for row in model['rows'].values()],endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        service=workspace(tmp_path,provider,route);documents={'database_target_id':'file','baseline':document(baseline),'desired':document(desired)}
        displayed=service.sqlite_schema_plan('owned',documents)
        if unnormalized:
            assert not displayed['ready_for_review']
            assert any('normalized' in item['reason'] for item in displayed['blockers'])
            with closing(sqlite3.connect(path)) as observer:assert not observer.execute("SELECT name FROM sqlite_schema WHERE name='added'").fetchall()
            return
        assert displayed['ready_for_review'],displayed
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        result=service.sqlite_schema_application('owned','sqlite_schema_apply',{'database_target_id':'file',**{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True})
        assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
        with closing(sqlite3.connect(path)) as observer:
            assert configuration(observer,'main','added','fts5')['commands']==[['automerge',8],['pgsz',1024],['rank','bm25(2.0)'],['secure-delete',1]]
    finally:provider.close()
