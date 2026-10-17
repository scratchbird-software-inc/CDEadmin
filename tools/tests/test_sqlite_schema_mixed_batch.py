"""Native heterogeneous schema stages commit or roll back as one SQLite job."""
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider, _create_client, _resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import plan, batch_blockers
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService
from pgadmin.cdeadmin.operations.store import JsonOperationStore


@pytest.mark.parametrize('failure',[None,'unique','trigger','view','stale'])
def test_rebuild_create_and_replacement_share_one_native_transaction(tmp_path,failure):
    @dataclass(frozen=True)
    class Context:
        endpoint_id:str='endpoint'
        profile_id:str='sqlite-native'
    path,target_path=tmp_path/'live.sqlite',tmp_path/'desired.sqlite'
    common={'other':'CREATE TABLE "main"."other"(id INTEGER PRIMARY KEY,note TEXT)',
            'audit':'CREATE TABLE "main"."audit"(value TEXT)'}
    original={**common,'owned':'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY,value TEXT)',
        'by_note':'CREATE INDEX "main"."by_note" ON "other"(note)',
        'touch':'CREATE TRIGGER "main"."touch" AFTER INSERT ON "other" BEGIN INSERT INTO audit VALUES(new.note); END'}
    target={**common,'owned':'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY,value INTEGER,added TEXT DEFAULT \'kept\')',
        'by_note':'CREATE UNIQUE INDEX "main"."by_note" ON "other"(lower(note)) WHERE note IS NOT NULL',
        'touch':'CREATE TRIGGER "main"."touch" AFTER DELETE ON "other" BEGIN INSERT INTO audit VALUES(old.note || \':gone\'); END',
        'new_projection':'CREATE VIEW "main"."new_projection" AS SELECT id,value FROM owned'}
    for file,definitions in ((path,original),(target_path,target)):
        with closing(sqlite3.connect(file)) as connection:
            for source in definitions.values():connection.execute(source)
            connection.commit()
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("INSERT INTO owned VALUES(7,'007')")
        connection.executemany('INSERT INTO other VALUES(?,?)',[(1,'one'),(2,'one' if failure=='unique' else 'two')])
        connection.execute('DELETE FROM audit');connection.commit()
        before=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client())
    route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        def capture(file):
            return build_export(provider.capture_catalog({**route,'database':str(file)})['resources'],
                endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite',native_model=True)
        baseline,template=capture(path),capture(target_path)
        desired=deepcopy(baseline)
        for identity,row in list(desired['rows'].items()):
            if row['path'][:2]==['main','owned']:del desired['rows'][identity]
        for identity,row in template['rows'].items():
            if row['kind'] in {'table','view','column','constraint','index','trigger'} and row['system']=='false':
                desired['rows'][identity]=deepcopy(row)
        for identity,row in desired['rows'].items():
            if row['kind'] in {'table','view','index','trigger'} and row['name'] in {'owned','by_note','touch','new_projection'}:
                row['native']['ddl']=target[row['name']]
        if failure=='trigger':
            desired['rows'][_resource_id('trigger',['main','other'],'touch')]['native']['ddl']='CREATE TRIGGER "main"."touch" AFTER DELETE ON "other" BEGIN INSERT INTO missing_relation VALUES(old.id); END'
        if failure=='view':
            desired['rows'][_resource_id('view',['main'],'new_projection')]['native']['ddl']='CREATE VIEW "main"."new_projection" AS SELECT value FROM missing_relation'
        with closing(sqlite3.connect(path)) as connection:
            preview=plan(baseline,desired,baseline,connection,rebuilds=[_resource_id('table',['main'],'owned')])
            assert preview['ready_for_review'],preview
            assert {item['operation'] for item in preview['operations']}=={'create','replace','rebuild'}
            assert plan(baseline,desired,baseline,connection,rebuilds=[_resource_id('table',['main'],'owned')])['execution_sha256']==preview['execution_sha256']
            assert connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==before
            assert not connection.in_transaction
        def document(model):
            resources=[{'resource_id':row['resource_id'],'resource_kind':row['kind'],'display_path':row['path'],
                'display_name':row['name'],'native':row['native']} for row in model['rows'].values()]
            return json.dumps(build_export(resources,endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        service=object.__new__(ProviderWorkspaceService)
        service.endpoint_service=Mock();service.endpoint_service.workspace.return_value=(Context(),{'route':route},None)
        service.endpoint_service.provider_registry.resolve.return_value=SimpleNamespace(instance=provider)
        service.operation_bus=SimpleNamespace(store=JsonOperationStore(tmp_path/'operations.json'))
        service.resource_service=Mock();service._principal_id=lambda _server:'owner'
        documents={'database_target_id':'file','baseline':document(baseline),'desired':document(desired),
                   'rebuilds':[_resource_id('table',['main'],'owned')]}
        displayed=service.sqlite_schema_plan('owned',documents)
        assert displayed['ready_for_review'] and displayed['execution_sha256']==preview['execution_sha256']
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        request={'database_target_id':'file',**{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True}
        if failure=='stale':
            with closing(sqlite3.connect(path)) as connection:
                connection.execute('ALTER TABLE audit ADD COLUMN changed INT');connection.commit()
        result=service.sqlite_schema_application('owned','sqlite_schema_apply',request)
        expected='not_dispatched' if failure=='stale' else 'rolled_back' if failure else 'committed'
        assert result['state']==expected,result
        provider.client._connect=Mock(side_effect=AssertionError('replayed native migration'))
        assert service.sqlite_schema_application('owned','sqlite_schema_apply',request)['state']==expected
        provider.client._connect.assert_not_called()
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT * FROM audit').fetchall()==[]
            if failure:
                assert observer.execute('SELECT value,typeof(value) FROM owned').fetchall()==[('007','text')]
                assert observer.execute('SELECT name FROM sqlite_schema WHERE name=\'new_projection\'').fetchall()==[]
                if failure!='stale':assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==before
            else:
                assert result['outcome']['rediscovery_verified']
                assert observer.execute('SELECT id,value,typeof(value),added FROM owned').fetchall()==[(7,7,'integer','kept')]
                assert observer.execute('SELECT * FROM new_projection').fetchall()==[(7,7)]
                assert observer.execute('PRAGMA index_list(other)').fetchone()[2]==1
                observer.execute('DELETE FROM other WHERE id=1')
                assert observer.execute('SELECT * FROM audit').fetchall()==[('one:gone',)]
    finally:provider.client.close()


def test_mixed_batch_preservation_does_not_claim_rewritten_children_or_delete_intent():
    child={'resource_id':'child','kind':'index','path':['main','owned','by_note']}
    operations=[{'operation':'rebuild','name':'owned','resource_id':'owned'},
                {'operation':'replace','name':'by_note','resource_id':'child'}]
    assert any('dependency rewriting' in reason for reason in batch_blockers(operations,{'rows':{'child':child}}))
    assert batch_blockers([{'operation':'drop','resource_id':'old'},{'operation':'create','resource_id':'new'}],{'rows':{}})==['Review deletion separately from additions']
