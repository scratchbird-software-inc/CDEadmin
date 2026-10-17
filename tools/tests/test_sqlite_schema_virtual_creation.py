"""Installed native module creation, quoted declarations and external content admission."""
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.operations.store import JsonOperationStore
from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider,_create_client
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService,ProviderWorkspaceError


@dataclass(frozen=True)
class Context:
    endpoint_id:str='endpoint'
    profile_id:str='sqlite-native'


def workspace(tmp_path,provider,route):
    service=object.__new__(ProviderWorkspaceService);service.endpoint_service=Mock()
    service.endpoint_service.workspace.return_value=(Context(),{'route':route},None)
    service.endpoint_service.provider_registry.resolve.return_value=SimpleNamespace(instance=provider)
    service.operation_bus=SimpleNamespace(store=JsonOperationStore(tmp_path/'operations.json'))
    service.resource_service=Mock();service._principal_id=lambda _server:'owner'
    return service


@pytest.mark.parametrize('module,quoted,args',[
    ('fts5','"fts5"','body'),('fts4',"'fts4'",'body'),('fts3','[fts3]','body'),
    ('rtree','`rtree`','id,x1,x2'),('geopoly','"geopoly"','label'),
    ('fts3tokenize','"fts3tokenize"',"'unicode61'"),('dbstat','"dbstat"','main'),
    ('fts4aux','"fts4aux"',"'base'"),('fts5vocab','"fts5vocab"',"'base','row'")])
def test_installed_module_native_ddn_creation_and_real_queries(tmp_path,module,quoted,args):
    path,target=tmp_path/'live.sqlite',tmp_path/'desired.sqlite';name='added:雪'
    source='CREATE VIRTUAL TABLE "main"."'+name+'" USING '+quoted+'('+args+')'
    for file in (path,target):
        with closing(sqlite3.connect(file)) as connection:
            connection.execute('CREATE VIRTUAL TABLE base USING '+('fts5' if module=='fts5vocab' else 'fts4')+'(body)')
            connection.execute("INSERT INTO base(body) VALUES('native token')")
            if file==target:connection.execute(source)
            connection.commit()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client());route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        def capture(file):return build_export(provider.capture_catalog({**route,'database':str(file)},include_system=False)['resources'],
            endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite',native_model=True)
        baseline,template=capture(path),capture(target);desired=deepcopy(baseline)
        for identity,row in template['rows'].items():
            if row['path'][:2]==['main',name]:
                desired['rows'][identity]=deepcopy(row)
                if row['kind'] in {'fts-table','virtual-table'}:desired['rows'][identity]['native']['ddl']=source
        def document(model):
            return json.dumps(build_export([{'resource_id':row['resource_id'],'resource_kind':row['kind'],'display_name':row['name'],
                'display_path':row['path'],'native':row['native']} for row in model['rows'].values()],
                endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        service=workspace(tmp_path,provider,route)
        documents={'database_target_id':'file','baseline':document(baseline),'desired':document(desired)}
        displayed=service.sqlite_schema_plan('owned',documents);assert displayed['ready_for_review'],displayed
        with closing(sqlite3.connect(path)) as observer:assert not observer.execute('SELECT name FROM sqlite_schema WHERE name=?',(name,)).fetchall()
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        result=service.sqlite_schema_application('owned','sqlite_schema_apply',{'database_target_id':'file',
            **{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True})
        assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
        with closing(sqlite3.connect(path)) as observer:
            if module in {'fts3','fts4','fts5'}:
                observer.execute('INSERT INTO "'+name+'"(body) VALUES(?)',('native 雪',))
                assert observer.execute('SELECT body FROM "'+name+'" WHERE "'+name+'" MATCH \'native\'').fetchall()==[('native 雪',)]
            elif module=='fts3tokenize':assert observer.execute('SELECT token FROM "'+name+'" WHERE input=\'Native token\'').fetchall()==[('native',),('token',)]
            elif module=='fts4aux':assert observer.execute('SELECT occurrences FROM "'+name+'" WHERE term=\'native\' AND col=\'*\'').fetchall()==[(1,)]
            elif module=='fts5vocab':assert observer.execute('SELECT doc,cnt FROM "'+name+'" WHERE term=\'native\'').fetchall()==[(1,1)]
            elif module=='dbstat':assert observer.execute('SELECT count(*) FROM "'+name+'"').fetchone()[0]>0
            elif module=='rtree':
                observer.execute('INSERT INTO "'+name+'" VALUES(1,1,2)');assert observer.execute('SELECT id FROM "'+name+'" WHERE x1<=1 AND x2>=2').fetchall()==[(1,)]
            else:
                observer.execute('INSERT INTO "'+name+'"(_shape,label) VALUES(geopoly_blob(?),?)',('[[0,0],[1,0],[1,1],[0,0]]','triangle'))
                assert observer.execute('SELECT label FROM "'+name+'"').fetchall()==[('triangle',)]
    finally:provider.close()


def test_external_content_owner_requires_rebinding_and_does_not_silently_break_fts(tmp_path):
    path=tmp_path/'external.sqlite';owner="Owner'雪"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('CREATE TABLE "'+owner+'"(id INTEGER PRIMARY KEY,body TEXT)')
        connection.execute('INSERT INTO "'+owner+'" VALUES(1,\'native token\')')
        connection.execute('CREATE VIRTUAL TABLE search USING "fts5"(body,content=\'owner\'\'雪\',content_rowid=\'id\')')
        connection.execute("INSERT INTO search(search) VALUES('rebuild')");connection.commit()
        assert connection.execute("SELECT rowid,body FROM search WHERE search MATCH 'native'").fetchall()==[(1,'native token')]
        # Demonstrate the real native dependency: ALTER alone leaves the
        # constructor's external-content string pointing at the old table.
        copy=sqlite3.connect(':memory:')
        try:
            connection.backup(copy);copy.execute('ALTER TABLE "'+owner+'" RENAME TO renamed_owner')
            with pytest.raises(sqlite3.OperationalError):copy.execute("SELECT rowid,body FROM search WHERE search MATCH 'native'").fetchall()
        finally:copy.close()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client());route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        baseline=json.dumps(build_export(provider.capture_catalog(route,include_system=False)['resources'],endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        service=workspace(tmp_path,provider,route)
        with pytest.raises(ProviderWorkspaceError,match='FTS rebinding adapter'):
            service.sqlite_schema_rename_design('owned',{'database_target_id':'file','baseline':baseline,
                'renames':[{'kind':'table','table':owner,'to':'renamed_owner'}]})
        with closing(sqlite3.connect(path)) as observer:assert observer.execute("SELECT rowid,body FROM search WHERE search MATCH 'native'").fetchall()==[(1,'native token')]
    finally:provider.close()


def test_fts3_content_column_is_not_an_fts4_external_content_option(tmp_path):
    path=tmp_path/'fts3.sqlite'
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript("CREATE TABLE owner(body TEXT); INSERT INTO owner VALUES('ordinary'); "
            "CREATE VIRTUAL TABLE search USING fts3(body,content='owner'); "
            "INSERT INTO search(body,content) VALUES('native token','own content');")
        connection.commit()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client());route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        baseline=json.dumps(build_export(provider.capture_catalog(route,include_system=False)['resources'],endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        service=workspace(tmp_path,provider,route);renames=[{'kind':'table','table':'owner','to':'renamed_owner'}]
        generated=service.sqlite_schema_rename_design('owned',{'database_target_id':'file','baseline':baseline,'renames':renames})
        documents={'database_target_id':'file','baseline':baseline,'desired':json.dumps(generated['snapshot']),'renames':renames}
        displayed=service.sqlite_schema_plan('owned',documents);assert displayed['ready_for_review'],displayed
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        result=service.sqlite_schema_application('owned','sqlite_schema_apply',{'database_target_id':'file',
            **{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True})
        assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT * FROM renamed_owner').fetchall()==[('ordinary',)]
            assert observer.execute("SELECT body,content FROM search WHERE search MATCH 'native'").fetchall()==[('native token','own content')]
    finally:provider.close()
