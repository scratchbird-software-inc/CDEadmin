"""Native coordinated rebuilds preserve data while replacing retained children."""
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider,_create_client,_resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import plan
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService
from pgadmin.cdeadmin.operations.store import JsonOperationStore


@pytest.mark.parametrize('failure',[None,'unique','trigger','stale','metadata','filtered'])
def test_native_rebuild_coordinates_renamed_column_indexes_and_trigger(tmp_path,failure):
    @dataclass(frozen=True)
    class Context:
        endpoint_id:str='endpoint'
        profile_id:str='sqlite-native'
    path,target_path=tmp_path/'live.sqlite',tmp_path/'desired.sqlite'
    common={'audit':'CREATE TABLE "main"."audit"(value TEXT)'}
    original={**common,'owned':'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY AUTOINCREMENT,value TEXT)',
        'by_value':'CREATE INDEX "main"."by_value" ON "owned"(value)',
        'by_id':'CREATE INDEX "main"."by_id" ON "owned"(id DESC)',
        'touch':'CREATE TRIGGER "main"."touch" AFTER INSERT ON "owned" BEGIN INSERT INTO audit VALUES(new.value); END'}
    target={**common,'owned':'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY AUTOINCREMENT,renamed INTEGER,added TEXT DEFAULT \'kept\')',
        'by_value':'CREATE UNIQUE INDEX "main"."by_value" ON "owned"(abs(renamed)) WHERE renamed IS NOT NULL',
        'by_id':original['by_id'],
        'touch':'CREATE TRIGGER "main"."touch" AFTER DELETE ON "owned" BEGIN INSERT INTO audit VALUES(old.renamed || \':gone\'); END',
        'projection':'CREATE VIEW "main"."projection" AS SELECT id,renamed FROM owned'}
    if failure=='trigger':target['touch']=target['touch'].replace('INTO audit','INTO missing_relation')
    for file,definitions in ((path,original),(target_path,target)):
        with closing(sqlite3.connect(file)) as connection:
            for source in definitions.values():connection.execute(source)
            connection.commit()
    with closing(sqlite3.connect(path)) as connection:
        connection.executemany('INSERT INTO owned VALUES(?,?)',[(7,'007'),(8,'007' if failure=='unique' else '008'),(80,'080')])
        connection.execute('DELETE FROM owned WHERE id=80');connection.execute('DELETE FROM audit');connection.commit()
        before=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client())
    route={'database':str(path),'filesystem_root':str(tmp_path)}
    owner=_resource_id('table',['main'],'owned')
    renamed=[{'table':owner,'from':'value','to':'renamed'}]
    try:
        def capture(file):
            return build_export(provider.capture_catalog({**route,'database':str(file)})['resources'],
                endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite',native_model=True)
        baseline,template=capture(path),capture(target_path)
        desired=deepcopy(baseline)
        for identity,row in list(desired['rows'].items()):
            if row['path'][:2]==['main','owned']:del desired['rows'][identity]
        for identity,row in template['rows'].items():
            if row['path'][:2]==['main','owned'] or row['name']=='projection':desired['rows'][identity]=deepcopy(row)
        for row in desired['rows'].values():
            if row['kind'] in {'table','view','index','trigger'} and row['name'] in target and row['name']!='audit':row['native']['ddl']=target[row['name']]
        index_id=_resource_id('index',['main','owned'],'by_value')
        if failure=='metadata':desired['rows'][index_id]['native']['catalog_metadata']['unique']=False
        if failure=='filtered':del desired['rows'][index_id]
        with closing(sqlite3.connect(path)) as connection:
            preview=plan(baseline,desired,baseline,connection,rebuilds=[owner],column_renames=renamed)
            assert connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==before
            assert not connection.in_transaction
            if failure in {'metadata','filtered'}:
                assert not preview['ready_for_review'] and preview['blockers']
                return
            assert preview['ready_for_review'],preview['blockers']+preview['conflicts']
            assert {item['operation'] for item in preview['operations']}=={'create','rebuild'}
            rebuilt=next(item for item in preview['operations'] if item['operation']=='rebuild')
            assert rebuilt['coordinated_children'] and len(rebuilt['target_child_sources'])==3
            assert rebuilt['preserve_rowid'] and rebuilt['preserve_autoincrement']
            assert plan(baseline,desired,baseline,connection,rebuilds=[owner],column_renames=renamed)['execution_sha256']==preview['execution_sha256']
        def document(model):
            resources=[{'resource_id':row['resource_id'],'resource_kind':row['kind'],'display_path':row['path'],
                'display_name':row['name'],'native':row['native']} for row in model['rows'].values()]
            return json.dumps(build_export(resources,endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        service=object.__new__(ProviderWorkspaceService)
        service.endpoint_service=Mock();service.endpoint_service.workspace.return_value=(Context(),{'route':route},None)
        service.endpoint_service.provider_registry.resolve.return_value=SimpleNamespace(instance=provider)
        service.operation_bus=SimpleNamespace(store=JsonOperationStore(tmp_path/'operations.json'))
        service.resource_service=Mock();service._principal_id=lambda _server:'owner'
        documents={'database_target_id':'file','baseline':document(baseline),'desired':document(desired),'rebuilds':[owner],'column_renames':renamed}
        displayed=service.sqlite_schema_plan('owned',documents)
        assert displayed['ready_for_review'] and displayed['execution_sha256']==preview['execution_sha256']
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        request={'database_target_id':'file',**{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True}
        if failure=='stale':
            with closing(sqlite3.connect(path)) as connection:
                connection.execute('DROP INDEX by_id');connection.execute('CREATE INDEX by_id ON owned(value)');connection.commit()
        result=service.sqlite_schema_application('owned','sqlite_schema_apply',request)
        expected='not_dispatched' if failure=='stale' else 'rolled_back' if failure else 'committed'
        assert result['state']==expected,result
        provider.client._connect=Mock(side_effect=AssertionError('replayed native migration'))
        assert service.sqlite_schema_application('owned','sqlite_schema_apply',request)['state']==expected
        provider.client._connect.assert_not_called()
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT * FROM audit').fetchall()==[]
            if failure:
                assert observer.execute('SELECT value,typeof(value) FROM owned WHERE id=7').fetchall()==[('007','text')]
                if failure!='stale':assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==before
            else:
                assert result['outcome']['rediscovery_verified']
                assert observer.execute('SELECT rowid,id,renamed,typeof(renamed),added FROM owned ORDER BY id').fetchall()==[(7,7,7,'integer','kept'),(8,8,8,'integer','kept')]
                assert observer.execute('SELECT * FROM projection ORDER BY id').fetchall()==[(7,7),(8,8)]
                assert observer.execute('SELECT seq FROM sqlite_sequence WHERE name=\'owned\'').fetchone()==(80,)
                assert any(row[1]=='by_value' and row[2]==1 and row[4]==1 for row in observer.execute('PRAGMA index_list(owned)'))
                observer.execute('DELETE FROM owned WHERE id=7')
                assert observer.execute('SELECT * FROM audit').fetchall()==[('7:gone',)]
    finally:provider.client.close()
