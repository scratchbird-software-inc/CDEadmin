"""Native dependent views and INSTEAD OF triggers change with rebuilt tables."""
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


@pytest.mark.parametrize('failure',[None,'view','trigger','stale','filtered'])
def test_native_dependent_view_chain_and_trigger_replace_atomically(tmp_path,failure):
    @dataclass(frozen=True)
    class Context:
        endpoint_id:str='endpoint'
        profile_id:str='sqlite-native'
    path,target_path=tmp_path/'live.sqlite',tmp_path/'desired.sqlite'
    original={
        'owned':'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY,value TEXT)',
        'audit':'CREATE TABLE "main"."audit"(value TEXT)',
        'visible':'CREATE VIEW "main"."visible" AS SELECT id,value FROM owned',
        'outer_view':'CREATE VIEW "main"."outer_view" AS SELECT id,value FROM visible',
        'write_view':'CREATE TRIGGER "main"."write_view" INSTEAD OF UPDATE ON "visible" BEGIN UPDATE owned SET value=new.value WHERE id=old.id; END'}
    target={**original,
        'owned':'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY,renamed INTEGER)',
        'visible':'CREATE VIEW "main"."visible"("id","renamed") AS SELECT id,renamed FROM owned',
        'outer_view':'CREATE VIEW "main"."outer_view" AS SELECT id,renamed FROM visible',
        'write_view':'CREATE TRIGGER "main"."write_view" INSTEAD OF DELETE ON "visible" BEGIN DELETE FROM owned WHERE id=old.id; INSERT INTO audit VALUES(old.renamed || \':gone\'); END'}
    for file,definitions in ((path,original),(target_path,target)):
        with closing(sqlite3.connect(file)) as connection:
            for source in definitions.values():connection.execute(source)
            connection.commit()
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("INSERT INTO owned VALUES(7,'007')");connection.commit()
        before=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client())
    route={'database':str(path),'filesystem_root':str(tmp_path)}
    owner=_resource_id('table',['main'],'owned');renamed=[{'table':owner,'from':'value','to':'renamed'}]
    try:
        def capture(file):
            return build_export(provider.capture_catalog({**route,'database':str(file)})['resources'],
                endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite',native_model=True)
        baseline,desired=capture(path),capture(target_path)
        for identity,row in baseline['rows'].items():
            if row['kind'] in {'database','pragma','extension','metric','native-function','collation','compile-option'} or row['name']=='audit':
                desired['rows'][identity]=deepcopy(row)
        if failure=='view':target['outer_view']=target['outer_view'].replace('FROM visible','FROM missing_relation')
        if failure=='trigger':target['write_view']=target['write_view'].replace('INTO audit','INTO missing_relation')
        for row in desired['rows'].values():
            if row['kind'] in {'table','view','trigger'} and row['name'] in target and row['name']!='audit':row['native']['ddl']=target[row['name']]
        if failure=='trigger':
            desired['rows'][_resource_id('view',['main'],'visible')]['native']['triggers'][0]['ddl']=target['write_view']
        if failure=='filtered':del desired['rows'][_resource_id('column',['main','visible'],'renamed')]
        with closing(sqlite3.connect(path)) as connection:
            preview=plan(baseline,desired,baseline,connection,rebuilds=[owner],column_renames=renamed)
            assert connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==before
            assert not connection.in_transaction
            if failure=='filtered':
                assert not preview['ready_for_review'] and preview['blockers'];return
            assert preview['ready_for_review'],preview['blockers']+preview['conflicts']
            assert [(item['operation'],item['kind']) for item in preview['operations']].count(('replace','view'))==2
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
                connection.execute('DROP VIEW outer_view');connection.execute('CREATE VIEW outer_view AS SELECT value FROM visible');connection.commit()
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
                if failure!='stale':assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==before
            else:
                assert result['outcome']['rediscovery_verified']
                assert observer.execute('SELECT * FROM outer_view').fetchall()==[(7,7)]
                observer.execute('DELETE FROM visible WHERE id=7')
                assert observer.execute('SELECT * FROM audit').fetchall()==[('7:gone',)]
                assert observer.execute('SELECT * FROM owned').fetchall()==[]
    finally:provider.client.close()
