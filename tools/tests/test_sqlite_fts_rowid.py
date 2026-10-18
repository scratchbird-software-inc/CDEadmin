"""Native row identity preservation across content alias shadowing and renames."""
from contextlib import closing
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider,_create_client,_resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_schema_plan import digest
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceError
from test_sqlite_schema_virtual_creation import Context,workspace


CASES=[(module,mode,failure) for module in ('fts4','fts5')
    for mode in ('physical','new-shadow','generated')
    for failure in (None,'stale','denied','rollback','lost_commit')]
CASES += [(module,mode,None) for module in ('fts4','fts5') for mode in ('primary-alias','hidden-alias')]


@pytest.mark.parametrize('module,mode,failure',CASES)
def test_native_row_identity_mapping_preserves_exact_search_rows_and_durable_outcomes(tmp_path,module,mode,failure):
    path=tmp_path/'identity.sqlite';wide=9007199254740993;quote=lambda name:'"'+name.replace('"','""')+'"'
    with closing(sqlite3.connect(path)) as connection:
        definition=('rowid INTEGER PRIMARY KEY,body TEXT' if mode=='primary-alias' else
            'rowid INTEGER,body TEXT' if mode=='physical' else
            'id INTEGER,rowid INTEGER GENERATED ALWAYS AS(id+7),body TEXT' if mode=='generated' else
            'tag INTEGER,body TEXT' if mode=='hidden-alias' else 'id INTEGER PRIMARY KEY,tag INTEGER,body TEXT')
        connection.execute('CREATE TABLE owner('+definition+')')
        if mode=='new-shadow':connection.execute('INSERT INTO owner VALUES(?,?,?)',(wide,wide+7,'native 雪 token'))
        elif mode=='hidden-alias':connection.execute('INSERT INTO owner(rowid,tag,body) VALUES(?,?,?)',(wide,wide+7,'native 雪 token'))
        elif mode=='generated':connection.execute('INSERT INTO owner(id,body) VALUES(?,?)',(wide,'native 雪 token'))
        else:connection.execute('INSERT INTO owner VALUES(?,?)',(wide,'native 雪 token'))
        connection.execute("CREATE VIRTUAL TABLE search USING "+module+"(body,content='owner')")
        connection.execute("INSERT INTO search(search) VALUES('rebuild')");connection.commit()
        expected=connection.execute("SELECT rowid,body FROM search WHERE search MATCH 'native'").fetchall()
        assert expected==[(wide+7 if mode=='generated' else wide,'native 雪 token')]
        original=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
        data=connection.execute('SELECT * FROM owner').fetchall()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client());route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        service=workspace(tmp_path,provider,route)
        baseline=json.dumps(build_export(provider.capture_catalog(route,include_system=False)['resources'],endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        former='tag' if mode in {'new-shadow','hidden-alias'} else 'rowid';renamed='rowid' if former=='tag' else 'legacy:雪'
        rebuild=module=='fts5' or mode!='primary-alias'
        request={'database_target_id':'file','baseline':baseline,
            'renames':[{'kind':'column','table':'owner','from':former,'to':renamed}],
            'fts_rebindings':[_resource_id('fts-table',['main'],'search')] if rebuild else []}
        generated=service.sqlite_schema_rename_design('owned',request);documents={**request,'desired':json.dumps(generated['snapshot'])}
        displayed=service.sqlite_schema_plan('owned',documents);assert displayed['ready_for_review'],displayed
        if module=='fts4' and rebuild:
            mapping=displayed['operations'][0]['fts_rebuilds'][0]['row_identity_mapping']
            assert mapping['changed'] and mapping['content_view'].startswith('__scratchrobin_fts4_content_')
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==original
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        apply_request={'database_target_id':'file',**{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True}
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
                    if failure=='rollback' and source.startswith('CREATE VIRTUAL TABLE "main".'):
                        self.connection.execute('SELECT * FROM injected_missing_relation')
                    return result
                def commit(self):
                    self.connection.commit()
                    if failure=='lost_commit':raise ConnectionError('Owned lost row identity mapping commit reply')
            provider.client._connect=Mock(side_effect=lambda payload:Injected(connect(payload)))
        result=service.sqlite_schema_application('owned','sqlite_schema_apply',apply_request)
        state='not_dispatched' if failure=='stale' else 'rolled_back' if failure in {'denied','rollback'} else 'unknown_outcome' if failure=='lost_commit' else 'committed'
        # FTS5 preserves this mapping with content_rowid, without creating a
        # mapping view, so a CREATE VIEW refusal is irrelevant to that engine.
        if module=='fts5' and failure=='denied':state='committed'
        assert result['state']==state,result
        provider.client._connect=Mock(side_effect=AssertionError('Row identity review was replayed'))
        assert service.sqlite_schema_application('owned','sqlite_schema_apply',apply_request)['state']==state
        provider.client._connect.assert_not_called()
        applied=state in {'committed','unknown_outcome'}
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT * FROM owner').fetchall()==data
            assert observer.execute("SELECT rowid,body FROM search WHERE search MATCH 'native'").fetchall()==expected
            if applied:observer.execute("INSERT INTO search(search) VALUES('integrity-check')")
            elif failure!='stale':assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==original
    finally:provider.close()


@pytest.mark.parametrize('module',['fts4','fts5'])
def test_unnameable_native_row_identity_is_refused_before_dispatch(tmp_path,module):
    path=tmp_path/'unnameable.sqlite'
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript('CREATE TABLE owner(oid INTEGER,_rowid_ INTEGER,tag INTEGER,body); '
            "INSERT INTO owner(rowid,oid,_rowid_,tag,body) VALUES(501,10,20,30,'native token');")
        connection.execute('CREATE VIRTUAL TABLE search USING '+module+"(body,content='owner')")
        connection.execute("INSERT INTO search(search) VALUES('rebuild')");connection.commit()
        original=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client());route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        service=workspace(tmp_path,provider,route)
        baseline=json.dumps(build_export(provider.capture_catalog(route,include_system=False)['resources'],endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        with pytest.raises(ProviderWorkspaceError,match='no longer expressible'):
            service.sqlite_schema_rename_design('owned',{'database_target_id':'file','baseline':baseline,
                'renames':[{'kind':'column','table':'owner','from':'tag','to':'rowid'}],
                'fts_rebindings':[_resource_id('fts-table',['main'],'search')]})
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==original
            assert observer.execute("SELECT rowid,body FROM search WHERE search MATCH 'native'").fetchall()==[(501,'native token')]
    finally:provider.close()


@pytest.mark.parametrize('collision',['index','rename'])
def test_native_mapping_view_reserves_existing_indexes_and_selected_new_names(tmp_path,collision):
    path=tmp_path/'reserved.sqlite';identity=_resource_id('fts-table',['main'],'search')
    reserved='__scratchrobin_fts4_content_'+digest({'resource_id':identity,'owner':'owner','expression':'id','fields':['body']})[:24]
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript("CREATE TABLE owner(id INTEGER PRIMARY KEY,tag INTEGER,body);INSERT INTO owner VALUES(501,1001,'native token');")
        if collision=='index':connection.execute('CREATE INDEX "'+reserved+'" ON owner(tag)')
        else:connection.execute('CREATE TABLE occupied(id)')
        connection.execute("CREATE VIRTUAL TABLE search USING fts4(body,content='owner')")
        connection.execute("INSERT INTO search(search) VALUES('rebuild')");connection.commit()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client());route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        service=workspace(tmp_path,provider,route)
        baseline=json.dumps(build_export(provider.capture_catalog(route,include_system=False)['resources'],endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        renames=[{'kind':'column','table':'owner','from':'tag','to':'rowid'}]
        if collision=='rename':renames.append({'kind':'table','table':'occupied','to':reserved})
        request={'database_target_id':'file','baseline':baseline,'renames':renames,'fts_rebindings':[identity]}
        generated=service.sqlite_schema_rename_design('owned',request);documents={**request,'desired':json.dumps(generated['snapshot'])}
        displayed=service.sqlite_schema_plan('owned',documents);assert displayed['ready_for_review'],displayed
        assert displayed['operations'][0]['fts_rebuilds'][0]['row_identity_mapping']['content_view']==reserved+'1'
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        result=service.sqlite_schema_application('owned','sqlite_schema_apply',{'database_target_id':'file',
            **{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True})
        assert result['state']=='committed',result
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT type FROM sqlite_schema WHERE name=?',(reserved,)).fetchone()==('index' if collision=='index' else 'table',)
            assert observer.execute("SELECT rowid,body FROM search WHERE search MATCH 'native'").fetchall()==[(501,'native token')]
    finally:provider.close()


@pytest.mark.parametrize('mode',['shadow','physical'])
def test_fts4_public_rowid_and_document_identity_keep_distinct_native_roles(tmp_path,mode):
    path=tmp_path/'public-rowid.sqlite';wide=9007199254740993
    with closing(sqlite3.connect(path)) as connection:
        if mode=='shadow':
            connection.execute('CREATE TABLE owner(id INTEGER PRIMARY KEY,tag INTEGER,body)')
            connection.execute('INSERT INTO owner VALUES(?,?,?)',(wide,wide+7,'native token'))
        else:
            connection.execute('CREATE TABLE owner(rowid INTEGER,body)')
            connection.execute('INSERT INTO owner VALUES(?,?)',(wide,'native token'))
        connection.execute("CREATE VIRTUAL TABLE search USING fts4(rowid,body,content='owner')")
        connection.execute("INSERT INTO search(search) VALUES('rebuild')");connection.commit()
        assert connection.execute("SELECT docid,rowid,body FROM search WHERE search MATCH 'native'").fetchall()==[(wide,wide,'native token')]
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client());route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        service=workspace(tmp_path,provider,route)
        baseline=json.dumps(build_export(provider.capture_catalog(route,include_system=False)['resources'],endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        request={'database_target_id':'file','baseline':baseline,
            'renames':[{'kind':'column','table':'owner','from':'tag' if mode=='shadow' else 'rowid','to':'rowid' if mode=='shadow' else 'legacy'}],
            'fts_rebindings':[_resource_id('fts-table',['main'],'search')]}
        generated=service.sqlite_schema_rename_design('owned',request);documents={**request,'desired':json.dumps(generated['snapshot'])}
        displayed=service.sqlite_schema_plan('owned',documents);assert displayed['ready_for_review'],displayed
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        result=service.sqlite_schema_application('owned','sqlite_schema_apply',{'database_target_id':'file',
            **{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True})
        assert result['state']=='committed',result
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT docid,'+('rowid' if mode=='shadow' else 'legacy')+",body FROM search WHERE search MATCH 'native'").fetchall()==[(wide,wide,'native token')]
    finally:provider.close()
