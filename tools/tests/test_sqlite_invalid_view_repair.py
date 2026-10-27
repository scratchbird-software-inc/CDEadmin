"""Invalid native views remain discoverable and can be repaired through DDN."""
from contextlib import closing
from copy import deepcopy
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider,_create_client,_resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import plan
from pgadmin.cdeadmin.workspace.sqlite_schema_apply import SQLiteSchemaApplications,apply_review


@pytest.mark.parametrize('definition',[
    'CREATE VIEW broken AS SELECT id,value FROM missing_relation',
    'CREATE VIEW broken(id,value) AS SELECT id,value FROM missing_relation',
    'CREATE VIEW broken AS SELECT * FROM broken',
])
def test_invalid_view_definition_and_native_failures_survive_capture_and_repair(tmp_path,definition):
    path,target=tmp_path/'live.sqlite',tmp_path/'desired.sqlite'
    for file,source in ((path,definition),(target,'CREATE VIEW broken AS SELECT id,value FROM owned')):
        with closing(sqlite3.connect(file)) as connection:
            connection.execute('CREATE TABLE owned(id INTEGER PRIMARY KEY,value TEXT)')
            connection.execute(source)
            connection.execute('CREATE TRIGGER no_write INSTEAD OF DELETE ON broken BEGIN SELECT 1; END')
            connection.execute("INSERT INTO owned VALUES(7,'kept')");connection.commit()
    provider=SQLiteProvider(SimpleNamespace(),SimpleNamespace(require=Mock()),_create_client())
    route={'database':str(path),'filesystem_root':str(tmp_path)}
    identity=_resource_id('view',['main'],'broken')
    try:
        def capture(file):
            result=provider.capture_catalog({**route,'database':str(file)})
            return result,build_export(result['resources'],endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite',native_model=True)
        snapshot,baseline=capture(path);_result,template=capture(target)
        row=next(row for row in snapshot['resources'] if row['resource_id']==identity)
        assert row['native']['ddl']==definition
        assert row['native']['view_binding_observation']['available'] is False
        assert row['native']['view_binding_observation']['native_error_code']==sqlite3.SQLITE_ERROR
        assert row['native']['triggers'][0]['name']=='no_write'
        root=next(row for row in snapshot['resources'] if row['resource_kind']=='database')
        assert any(item.get('unavailable_resource_ids')==[identity] and item['available'] is False for item in root['native']['catalog_observations'])
        desired=deepcopy(baseline)
        for key,item in list(desired['rows'].items()):
            if item['path'][:2]==['main','broken']:del desired['rows'][key]
        desired['rows'].update({key:deepcopy(item) for key,item in template['rows'].items() if item['path'][:2]==['main','broken']})
        desired['rows'][identity]['native']['ddl']='CREATE VIEW "main"."broken" AS SELECT id,value FROM owned'
        with closing(sqlite3.connect(path)) as connection:
            before=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
            preview=plan(baseline,desired,baseline,connection)
            assert preview['ready_for_review'],preview['blockers']+preview['conflicts']
            assert connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==before
        applications=SQLiteSchemaApplications(tmp_path/'receipts.json')
        info=path.stat();reviewed=applications.review(preview,baseline,desired,'owner','binding','file',file_identity=[info.st_dev,info.st_ino])
        request={**{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True}
        receipt=applications.apply(request,'owner','binding',lambda record:apply_review(provider,route,record))
        assert receipt['state']=='committed' and receipt['outcome']['rediscovery_verified'],receipt
        assert applications.apply(request,'owner','binding',lambda _record:pytest.fail('replayed native repair'))['state']=='committed'
        repaired=next(row for row in provider.capture_catalog(route)['resources'] if row['resource_id']==identity)
        assert repaired['native']['view_binding_observation']['available'] is True
        assert repaired['native']['column_observation']['available'] is True
        assert repaired['native']['triggers'][0]['name']=='no_write'
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT * FROM broken').fetchall()==[(7,'kept')]
            observer.execute('DELETE FROM broken')
            assert observer.execute('SELECT * FROM owned').fetchall()==[(7,'kept')]
    finally:provider.client.close()
