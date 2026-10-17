"""Native production DDN creation of relations and their separately declared children."""
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
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService


@pytest.mark.parametrize('failure',[None,'index','trigger','stale'])
def test_new_native_relations_and_children_share_review_and_atomic_application(tmp_path,failure):
    @dataclass(frozen=True)
    class Context:
        endpoint_id:str='endpoint'
        profile_id:str='sqlite-native'
    path,target=tmp_path/'live.sqlite',tmp_path/'desired.sqlite'
    definitions={
        'orders':'CREATE TABLE "main"."orders"(id INTEGER PRIMARY KEY,note TEXT UNIQUE)',
        'by_note':'CREATE INDEX "main"."by_note" ON "orders"(note DESC)',
        'order_added':'CREATE TRIGGER "main"."order_added" AFTER INSERT ON "orders" BEGIN INSERT INTO audit VALUES(new.note); END',
        'projection':'CREATE VIEW "main"."projection" AS SELECT id,note FROM orders',
        'projection_delete':'CREATE TRIGGER "main"."projection_delete" INSTEAD OF DELETE ON "projection" BEGIN DELETE FROM orders WHERE id=old.id; END'}
    for file in (path,target):
        with closing(sqlite3.connect(file)) as connection:
            connection.execute('CREATE TABLE "main"."audit"(note TEXT)')
            if file==target:
                for source in definitions.values():connection.execute(source)
            connection.commit()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client())
    route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        def capture(file):
            return build_export(provider.capture_catalog({**route,'database':str(file)})['resources'],
                endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite',native_model=True)
        baseline,template=capture(path),capture(target);desired=deepcopy(baseline)
        for identity,row in template['rows'].items():
            if len(row['path'])>1 and row['path'][1] in {'orders','projection'}:
                desired['rows'][identity]=deepcopy(row)
        for row in desired['rows'].values():
            if row['kind'] in {'table','view','index','trigger'} and row['name'] in definitions:
                row['native']['ddl']=definitions[row['name']]
                if failure=='index' and row['name']=='by_note':row['native']['ddl']=definitions['by_note'].replace('(note DESC)','(missing_column)')
                if failure=='trigger' and row['name']=='order_added':row['native']['ddl']=definitions['order_added'].replace('INTO audit','INTO missing_relation')
        def document(model):
            resources=[{'resource_id':row['resource_id'],'resource_kind':row['kind'],'display_path':row['path'],
                'display_name':row['name'],'native':row['native']} for row in model['rows'].values()]
            return json.dumps(build_export(resources,endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        service=object.__new__(ProviderWorkspaceService);service.endpoint_service=Mock()
        service.endpoint_service.workspace.return_value=(Context(),{'route':route},None)
        service.endpoint_service.provider_registry.resolve.return_value=SimpleNamespace(instance=provider)
        service.operation_bus=SimpleNamespace(store=JsonOperationStore(tmp_path/'operations.json'))
        service.resource_service=Mock();service._principal_id=lambda _server:'owner'
        documents={'database_target_id':'file','baseline':document(baseline),'desired':document(desired)}
        displayed=service.sqlite_schema_plan('owned',documents)
        with closing(sqlite3.connect(path)) as observer:
            before=observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
            assert [name for name,_source in before]==['audit']
        if failure=='index':
            assert not displayed['ready_for_review']
            assert any('missing_column' in item['reason'] for item in displayed['blockers'])
            return
        assert displayed['ready_for_review'],displayed
        assert len(displayed['operations'])==5 and all(item['operation']=='create' for item in displayed['operations'])
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        request={'database_target_id':'file',**{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True}
        if failure=='stale':
            with closing(sqlite3.connect(path)) as observer:
                observer.execute('CREATE TABLE orders(other TEXT)');observer.commit()
                before=observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
        result=service.sqlite_schema_application('owned','sqlite_schema_apply',request)
        expected='not_dispatched' if failure=='stale' else 'rolled_back' if failure else 'committed'
        assert result['state']==expected,result
        provider.client._connect=Mock(side_effect=AssertionError('reviewed migration was replayed'))
        assert service.sqlite_schema_application('owned','sqlite_schema_apply',request)['state']==expected
        provider.client._connect.assert_not_called()
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT * FROM audit').fetchall()==[]
            if failure:
                assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==before
            else:
                assert result['outcome']['rediscovery_verified']
                observer.execute("INSERT INTO orders VALUES(9007199254740993,'雪')")
                assert observer.execute('SELECT * FROM projection').fetchall()==[(9007199254740993,'雪')]
                assert observer.execute('SELECT * FROM audit').fetchall()==[('雪',)]
                observer.execute('DELETE FROM projection')
                assert observer.execute('SELECT * FROM orders').fetchall()==[]
                assert observer.execute('PRAGMA index_xinfo(by_note)').fetchone()[3]==1
    finally:provider.close()
