"""Preserve named FTS content-view contracts during ordinary owner renames."""
from contextlib import closing
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider,_create_client
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from test_sqlite_schema_virtual_creation import Context,workspace


@pytest.mark.parametrize('module',['fts4','fts5'])
@pytest.mark.parametrize('mode',['rowid','body','star','nested','quoted','bracket'])
@pytest.mark.parametrize('failure',[None,'stale','denied','rollback','lost_commit'])
def test_native_fts_content_view_keeps_its_named_document_and_field_contract(tmp_path,module,mode,failure):
    path=tmp_path/'content.sqlite';wide=9007199254740993;view="[[content '雪" if mode=='bracket' else "content '雪" if mode=='quoted' else 'content'
    quote=lambda value:'"'+value.replace('"','""')+'"'
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('CREATE TABLE owner(rowid INTEGER,body TEXT,tag)')
        connection.execute('INSERT INTO owner VALUES(?,?,?)',(wide,'native token','kept'))
        if mode=='nested':connection.execute('CREATE VIEW source AS SELECT rowid,body FROM owner')
        source='SELECT * FROM source' if mode=='nested' else 'SELECT * FROM owner' if mode=='star' else 'SELECT rowid,body FROM owner'
        connection.execute('CREATE VIEW '+('['+view+']' if mode=='bracket' else quote(view))+' /* retained header comment */ AS '+source)
        connection.execute('CREATE VIRTUAL TABLE search USING '+module+"(body,content='"+view.replace("'","''")+"')")
        connection.execute("INSERT INTO search(search) VALUES('rebuild')")
        connection.execute('CREATE TRIGGER maintain_search AFTER INSERT ON owner BEGIN INSERT INTO search(rowid,body) VALUES(new.rowid,new.body); END')
        connection.commit();original=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client());route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        service=workspace(tmp_path,provider,route)
        baseline=json.dumps(build_export(provider.capture_catalog(route,include_system=False)['resources'],endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        former='body' if mode=='body' else 'rowid';renamed='renamed:雪'
        request={'database_target_id':'file','baseline':baseline,'renames':[{'kind':'column','table':'owner','from':former,'to':renamed}]}
        generated=service.sqlite_schema_rename_design('owned',request);documents={**request,'desired':json.dumps(generated['snapshot'])}
        displayed=service.sqlite_schema_plan('owned',documents);assert displayed['ready_for_review'],displayed
        assert displayed['operations'][0]['fts_rebuilds']==[]
        assert displayed['operations'][0]['rewrite_runtime']['preserved_fts_view_columns']
        with closing(sqlite3.connect(path)) as observer:assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==original
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        request={'database_target_id':'file',**{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True}
        if failure=='stale':
            with closing(sqlite3.connect(path)) as observer:observer.execute('CREATE TABLE changed_after_review(id)');observer.commit()
        if failure in {'denied','rollback','lost_commit'}:
            connect=provider.client._connect
            class Injected:
                def __init__(self,connection):
                    self.connection=connection
                    if failure=='denied':connection.set_authorizer(lambda action,*_args:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_VIEW else sqlite3.SQLITE_OK)
                def __getattr__(self,name):return getattr(self.connection,name)
                def execute(self,source,*args):
                    result=self.connection.execute(source,*args)
                    if failure=='rollback' and source.startswith('CREATE VIEW '):self.connection.execute('SELECT * FROM injected_missing_content_view')
                    return result
                def commit(self):
                    self.connection.commit()
                    if failure=='lost_commit':raise ConnectionError('Owned lost content view commit reply')
            provider.client._connect=Mock(side_effect=lambda payload:Injected(connect(payload)))
        result=service.sqlite_schema_application('owned','sqlite_schema_apply',request)
        state='not_dispatched' if failure=='stale' else 'rolled_back' if failure in {'denied','rollback'} else 'unknown_outcome' if failure=='lost_commit' else 'committed'
        assert result['state']==state,result
        provider.client._connect=Mock(side_effect=AssertionError('Content view review was replayed'))
        assert service.sqlite_schema_application('owned','sqlite_schema_apply',request)['state']==state
        provider.client._connect.assert_not_called()
        applied=state in {'committed','unknown_outcome'}
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT rowid,body FROM '+quote(view)).fetchall()==[(wide,'native token')]
            assert observer.execute("SELECT rowid,body FROM search WHERE search MATCH 'native'").fetchall()==[(wide,'native token')]
            assert observer.execute('SELECT * FROM owner').fetchall()==[(wide,'native token','kept')]
            assert 'retained header comment' in observer.execute('SELECT sql FROM sqlite_schema WHERE name=?',(view,)).fetchone()[0]
            if not applied and failure!='stale':assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==original
            if applied:
                observer.execute('INSERT INTO owner('+quote(renamed if former=='rowid' else 'rowid')+','+quote(renamed if former=='body' else 'body')+',tag) VALUES(?,?,?)',(wide+1,'fresh native term','second'))
                assert observer.execute("SELECT rowid,body FROM search WHERE search MATCH 'fresh'").fetchall()==[(wide+1,'fresh native term')]
    finally:provider.close()
