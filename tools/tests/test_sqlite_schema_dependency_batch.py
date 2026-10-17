"""Native explicit dependency retirement, rebuild and replacement as one DDN job."""
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.operations.store import JsonOperationStore
from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider,_create_client,_resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import plan


@pytest.mark.parametrize('failure',[None,'unique','view','trigger','stale','unselected','drop_index','drop_trigger'])
def test_explicit_dependent_view_retirement_and_column_rename_share_native_transaction(tmp_path,failure):
    extra_drop=failure.removeprefix('drop_') if failure in {'drop_index','drop_trigger'} else None
    if extra_drop:failure=None
    @dataclass(frozen=True)
    class Context:
        endpoint_id:str='endpoint'
        profile_id:str='sqlite-native'
    path,target=tmp_path/'live.sqlite',tmp_path/'desired.sqlite'
    common=['CREATE TABLE "main"."other"(id INTEGER PRIMARY KEY)', 'CREATE TABLE "main"."audit"(id INTEGER)']
    original={
        'owned':'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY,old_value TEXT)',
        'by_value':'CREATE INDEX "main"."by_value" ON "owned"(old_value)',
        'owned_touch':'CREATE TRIGGER "main"."owned_touch" AFTER UPDATE ON "owned" BEGIN INSERT INTO audit VALUES(new.id); END',
        'external_touch':'CREATE TRIGGER "main"."external_touch" AFTER INSERT ON "other" BEGIN UPDATE owned SET old_value=old_value WHERE id=new.id; END',
        'retired':'CREATE VIEW "main"."retired" AS SELECT id,old_value FROM owned',
        'retired_delete':'CREATE TRIGGER "main"."retired_delete" INSTEAD OF DELETE ON "retired" BEGIN DELETE FROM owned WHERE id=old.id; END'}
    desired_sources={
        'owned':'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY,new_value INTEGER)',
        'by_value':'CREATE '+('UNIQUE ' if failure=='unique' else '')+'INDEX "main"."by_value" ON "owned"(new_value)',
        'owned_touch':original['owned_touch'],
        'external_touch':'CREATE TRIGGER "main"."external_touch" AFTER INSERT ON "other" BEGIN UPDATE owned SET new_value=new_value+1 WHERE id=new.id; END',
        'current_projection':'CREATE VIEW "main"."current_projection" AS SELECT id,new_value FROM owned'}
    if extra_drop:
        original['retired_extra']=('CREATE INDEX "main"."retired_extra" ON "other"(id)' if extra_drop=='index' else
            'CREATE TRIGGER "main"."retired_extra" AFTER DELETE ON "other" BEGIN INSERT INTO audit VALUES(old.id); END')
    for file,sources in ((path,original),(target,desired_sources)):
        with closing(sqlite3.connect(file)) as connection:
            for source in [*common,*sources.values()]:connection.execute(source)
            connection.commit()
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("INSERT INTO owned VALUES(7,'007')")
        if failure=='unique':connection.execute("INSERT INTO owned VALUES(8,'0007')")
        connection.commit()
        before=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
        rows=connection.execute('SELECT rowid,* FROM owned ORDER BY id').fetchall()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client())
    route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        def capture(file):
            return build_export(provider.capture_catalog({**route,'database':str(file)})['resources'],
                endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite',native_model=True)
        baseline,template=capture(path),capture(target);desired=deepcopy(baseline)
        for identity,row in list(desired['rows'].items()):
            if len(row['path'])>=2 and row['path'][1] in {'owned','retired'}:del desired['rows'][identity]
        for identity,row in template['rows'].items():
            if row['system']=='false' and row['kind'] in {'table','view','column','constraint','index','trigger'}:
                desired['rows'][identity]=deepcopy(row)
        changed={'owned','by_value','external_touch','current_projection'}
        for row in desired['rows'].values():
            if row['kind'] in {'table','view','index','trigger'} and row['name'] in changed:
                row['native']['ddl']=desired_sources[row['name']]
        if failure=='view':desired['rows'][_resource_id('view',['main'],'current_projection')]['native']['ddl']='CREATE VIEW "main"."current_projection" AS SELECT id,new_value FROM missing_relation'
        if failure=='trigger':desired['rows'][_resource_id('trigger',['main','other'],'external_touch')]['native']['ddl']='CREATE TRIGGER "main"."external_touch" AFTER INSERT ON "other" BEGIN UPDATE owned SET absent_column=1; END'
        rebuild=_resource_id('table',['main'],'owned');deleted=_resource_id('view',['main'],'retired')
        extra_id=_resource_id(extra_drop,['main','other'],'retired_extra') if extra_drop else None
        if extra_id:desired['rows'].pop(extra_id)
        selections={'rebuilds':[rebuild],'column_renames':[{'table':rebuild,'from':'old_value','to':'new_value'}],
            'deletions':[] if failure=='unselected' else [deleted,*([extra_id] if extra_id else [])]}
        # Use the public service and DDN roundtrip, rather than a synthetic plan.
        def document(model):
            resources=[{'resource_id':row['resource_id'],'resource_kind':row['kind'],'display_path':row['path'],
                'display_name':row['name'],'native':row['native']} for row in model['rows'].values()]
            return json.dumps(build_export(resources,endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        service=object.__new__(ProviderWorkspaceService);service.endpoint_service=Mock()
        service.endpoint_service.workspace.return_value=(Context(),{'route':route},None)
        service.endpoint_service.provider_registry.resolve.return_value=SimpleNamespace(instance=provider)
        service.operation_bus=SimpleNamespace(store=JsonOperationStore(tmp_path/'operations.json'))
        service.resource_service=Mock();service._principal_id=lambda _server:'owner'
        documents={'database_target_id':'file','baseline':document(baseline),'desired':document(desired),**selections}
        displayed=service.sqlite_schema_plan('owned',documents)
        if failure=='unselected':
            assert not displayed['ready_for_review']
            assert any('explicit SQLite deletion' in item['reason'] for item in displayed['blockers'])
            with closing(sqlite3.connect(path)) as observer:assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==before
            return
        assert displayed['ready_for_review'],displayed
        assert {item['operation'] for item in displayed['operations']}=={'drop','rebuild','create','replace'}
        if extra_drop:assert any(item['operation']=='drop' and item['kind']==extra_drop for item in displayed['operations'])
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==before
            assert observer.execute('SELECT * FROM audit').fetchall()==[]
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        request={'database_target_id':'file',**{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True}
        if failure=='stale':
            with closing(sqlite3.connect(path)) as observer:
                observer.execute('CREATE VIEW appeared AS SELECT id,old_value FROM owned');observer.commit()
                before=observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
        result=service.sqlite_schema_application('owned','sqlite_schema_apply',request)
        expected='not_dispatched' if failure=='stale' else 'rolled_back' if failure else 'committed'
        assert result['state']==expected,result
        provider.client._connect=Mock(side_effect=AssertionError('uncertain or completed work must not replay'))
        assert service.sqlite_schema_application('owned','sqlite_schema_apply',request)['state']==expected
        provider.client._connect.assert_not_called()
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert observer.execute('SELECT * FROM audit').fetchall()==[]
            if failure:
                assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==before
                assert observer.execute('SELECT rowid,* FROM owned ORDER BY id').fetchall()==rows
            else:
                assert result['outcome']['rediscovery_verified']
                assert observer.execute('SELECT rowid,id,new_value,typeof(new_value) FROM owned').fetchall()==[(7,7,7,'integer')]
                assert observer.execute("SELECT name FROM sqlite_schema WHERE name IN ('retired','retired_delete','retired_extra')").fetchall()==[]
                assert observer.execute('SELECT * FROM current_projection').fetchall()==[(7,7)]
                observer.execute('INSERT INTO other VALUES(7)')
                assert observer.execute('SELECT * FROM current_projection').fetchall()==[(7,8)]
                assert observer.execute('SELECT * FROM audit').fetchall()==[(7,)]
    finally:provider.close()
