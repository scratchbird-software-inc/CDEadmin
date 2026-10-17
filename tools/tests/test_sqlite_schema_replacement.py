"""Native SQLite replacement, dependency guards and rollback of failed DDL."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider, _create_client, _resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import plan
from pgadmin.cdeadmin.workspace.sqlite_schema_apply import SQLiteSchemaApplications, apply_review
from pgadmin.cdeadmin.workspace.sqlite_replace import trigger_event


@contextmanager
def reviewed(tmp_path, kind, name, owner, original, replacement):
    path, desired_path = tmp_path/'live.sqlite', tmp_path/'desired.sqlite'
    for database, source in ((path,original),(desired_path,replacement)):
        with sqlite3.connect(database) as connection:
            connection.executescript('CREATE TABLE owned(id INTEGER PRIMARY KEY,note TEXT); '
                'CREATE TABLE audit(value TEXT); CREATE VIEW projected AS SELECT id,note FROM owned;')
            connection.execute(source)
    provider = SQLiteProvider(SimpleNamespace(),SimpleNamespace(require=Mock()),_create_client())
    route = {'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        def capture(file):
            return build_export(provider.capture_catalog({**route,'database':str(file)})['resources'],
                endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite',native_model=True)
        baseline, template = capture(path), capture(desired_path)
        identity = _resource_id(kind,['main',owner],name)
        desired = deepcopy(baseline)
        desired['rows'][identity] = deepcopy(template['rows'][identity])
        desired['rows'][identity]['native']['ddl'] = replacement
        with sqlite3.connect(path) as connection:
            before = connection.execute('SELECT name,sql FROM main.sqlite_schema ORDER BY name').fetchall()
            preview = plan(baseline,desired,baseline,connection)
            assert plan(baseline,desired,baseline,connection)['execution_sha256'] == preview['execution_sha256']
            assert connection.execute('SELECT name,sql FROM main.sqlite_schema ORDER BY name').fetchall() == before
            assert not connection.in_transaction
        assert preview['ready_for_review'],preview
        assert len(preview['operations']) == 1 and preview['operations'][0]['operation'] == 'replace'
        assert preview['operations'][0]['source'].startswith('DROP ')
        info = path.stat()
        store = SQLiteSchemaApplications(tmp_path/'receipts.json')
        receipt = store.review(preview,baseline,desired,'owner','binding','file',file_identity=[info.st_dev,info.st_ino])
        request = {key:receipt[key] for key in ('review_id','review_digest')}; request['confirmed'] = True
        yield provider,route,path,store,request,baseline,desired
    finally:
        provider.client.close()


def test_partial_expression_unique_index_replacement_is_atomic_and_not_replayed(tmp_path):
    original = 'CREATE INDEX "main"."by_note" ON "owned"(note)'
    replacement = 'CREATE UNIQUE INDEX "main"."by_note" ON "owned"(lower(note) COLLATE NOCASE DESC) WHERE note IS NOT NULL'
    with reviewed(tmp_path,'index','by_note','owned',original,replacement) as (provider,route,path,store,request,*_):
        with sqlite3.connect(path) as connection:
            connection.executemany('INSERT INTO owned VALUES(?,?)',[(1,'one'),(2,'two')])
        result = store.apply(request,'owner','binding',lambda record:apply_review(provider,route,record))
        assert result['state'] == 'committed',result
        assert result['outcome']['rediscovery_verified']
        assert store.apply(request,'owner','binding',lambda _:pytest.fail('replayed'))['state'] == 'committed'
        with sqlite3.connect(path) as observer:
            assert observer.execute('SELECT count(*) FROM owned').fetchone() == (2,)
            index = next(row for row in observer.execute('PRAGMA index_list(owned)') if row[1] == 'by_note')
            assert index[2:] == (1,'c',1)
            with pytest.raises(sqlite3.IntegrityError): observer.execute("INSERT INTO owned VALUES(3,'ONE')")
            assert not observer.execute("SELECT name FROM sqlite_schema WHERE name LIKE '__cde_replace_%'").fetchall()


@pytest.mark.parametrize('kind,owner,original,replacement,mutation,observed',[
    ('trigger','owned','AFTER INSERT ON "owned" BEGIN SELECT new.id; END',
        'AFTER INSERT ON "owned" BEGIN INSERT INTO audit VALUES(new.note || \'; literal\'); END',
        "INSERT INTO owned VALUES(9,'changed')",[('changed; literal',)]),
    ('trigger','projected','INSTEAD OF INSERT ON "projected" BEGIN SELECT new.id; END',
        'INSTEAD OF UPDATE ON "projected" BEGIN INSERT INTO audit VALUES(new.note); END',
        "UPDATE projected SET note='changed' WHERE id=9",[('changed',)]),
])
def test_trigger_body_and_view_event_replacement_never_executes_during_preview(tmp_path,kind,owner,original,replacement,mutation,observed):
    prefix = 'CREATE TRIGGER "main"."touch" '
    with reviewed(tmp_path,kind,'touch',owner,prefix+original,prefix+replacement) as (provider,route,path,store,request,*_):
        with sqlite3.connect(path) as connection:
            connection.execute("INSERT INTO owned VALUES(9,'kept')")
        result = store.apply(request,'owner','binding',lambda record:apply_review(provider,route,record))
        assert result['state'] == 'committed',result
        with sqlite3.connect(path) as observer:
            assert observer.execute('SELECT * FROM audit').fetchall() == []
            if owner == 'owned': observer.execute('DELETE FROM owned')
            observer.execute(mutation)
            assert observer.execute('SELECT * FROM audit').fetchall() == observed


@pytest.mark.parametrize('kind,replacement',[
    ('index','CREATE UNIQUE INDEX "main"."touch" ON "owned"(note)'),
    ('trigger','CREATE TRIGGER "main"."touch" AFTER INSERT ON "owned" BEGIN INSERT INTO missing_relation VALUES(new.id); END'),
])
def test_failed_replacement_restores_original_definition_and_rows(tmp_path,kind,replacement):
    original = ('CREATE INDEX "main"."touch" ON "owned"(note)' if kind == 'index' else
                'CREATE TRIGGER "main"."touch" AFTER INSERT ON "owned" BEGIN SELECT new.id; END')
    with reviewed(tmp_path,kind,'touch','owned',original,replacement) as (provider,route,path,store,request,*_):
        with sqlite3.connect(path) as connection:
            connection.executemany('INSERT INTO owned VALUES(?,?)',[(1,'duplicate'),(2,'duplicate')])
            previous = connection.execute("SELECT sql FROM sqlite_schema WHERE name='touch'").fetchone()
        result = store.apply(request,'owner','binding',lambda record:apply_review(provider,route,record))
        assert result['state'] == 'rolled_back',result
        assert store.apply(request,'owner','binding',lambda _:pytest.fail('replayed'))['state'] == 'rolled_back'
        with sqlite3.connect(path) as observer:
            assert observer.execute("SELECT sql FROM sqlite_schema WHERE name='touch'").fetchone() == previous
            assert observer.execute('SELECT * FROM owned').fetchall() == [(1,'duplicate'),(2,'duplicate')]
            assert observer.execute('SELECT * FROM audit').fetchall() == []


def test_dependency_change_refuses_replacement_before_dispatch(tmp_path):
    with reviewed(tmp_path,'index','touch','owned','CREATE INDEX "main"."touch" ON "owned"(note)',
        'CREATE UNIQUE INDEX "main"."touch" ON "owned"(note)') as (provider,route,path,store,request,*_):
        with sqlite3.connect(path) as connection: connection.execute('ALTER TABLE audit ADD COLUMN changed INT')
        result = store.apply(request,'owner','binding',lambda record:apply_review(provider,route,record))
        assert result['state'] == 'not_dispatched',result
        with sqlite3.connect(path) as observer:
            assert observer.execute('PRAGMA index_list(owned)').fetchone()[2] == 0


@pytest.mark.parametrize('name', ['"after insert"','`after insert`','[after insert]',"'after insert'",'🚀'])
def test_native_trigger_header_event_does_not_scan_names_comments_or_body(name):
    assert trigger_event(f'CREATE TRIGGER {name} /* AFTER INSERT */ INSTEAD OF UPDATE ON v BEGIN SELECT \'DELETE\'; END') == 'UPDATE'


@pytest.mark.parametrize('kind',['index','rebuild'])
def test_production_workspace_replans_reviews_and_applies_the_displayed_native_plan(tmp_path,kind):
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService
    from pgadmin.cdeadmin.operations.store import JsonOperationStore
    @dataclass(frozen=True)
    class Context:
        endpoint_id:str = 'endpoint'
        profile_id:str = 'sqlite-native'
    path,target_path = tmp_path/'live.sqlite',tmp_path/'target.sqlite'
    create = 'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY,note TEXT)'
    wanted = ('CREATE UNIQUE INDEX "main"."by_note" ON "owned"(note)' if kind == 'index' else
              'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY,note INTEGER)')
    for filename in (path,target_path):
        with sqlite3.connect(filename) as connection:
            connection.execute(wanted if kind == 'rebuild' and filename == target_path else create)
            if kind == 'index':
                connection.execute(wanted if filename == target_path else 'CREATE INDEX "main"."by_note" ON "owned"(note)')
    with sqlite3.connect(path) as connection: connection.execute("INSERT INTO owned VALUES(9,'007')")
    provider = SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client())
    route = {'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        def capture(filename):
            return build_export(provider.capture_catalog({**route,'database':str(filename)})['resources'],
                endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite',native_model=True)
        baseline,template = capture(path),capture(target_path)
        desired = deepcopy(baseline)
        for identity,row in template['rows'].items():
            if row['path'][:2] == ['main','owned']: desired['rows'][identity] = row
        identity = _resource_id('table',['main'],'owned') if kind == 'rebuild' else _resource_id('index',['main','owned'],'by_note')
        desired['rows'][identity]['native']['ddl'] = wanted
        def document(model):
            resources = [{'resource_id':row['resource_id'],'resource_kind':row['kind'],
                'display_path':row['path'],'display_name':row['name'],'native':row['native']} for row in model['rows'].values()]
            return json.dumps(build_export(resources,endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        service = object.__new__(ProviderWorkspaceService)
        service.endpoint_service = Mock()
        service.endpoint_service.workspace.return_value = (Context(),{'route':route},None)
        service.endpoint_service.provider_registry.resolve.return_value = SimpleNamespace(instance=provider)
        service.operation_bus = SimpleNamespace(store=JsonOperationStore(tmp_path/'operations.json'))
        service.resource_service = Mock()
        service._principal_id = lambda _server:'owner'
        request = {'database_target_id':'file','baseline':document(baseline),'desired':document(desired),
                   'rebuilds':[identity] if kind == 'rebuild' else []}
        preview = service.sqlite_schema_plan('owned',request)
        assert preview['ready_for_review'],preview
        receipt = service.sqlite_schema_application('owned','sqlite_schema_review',
            {**request,'execution_sha256':preview['execution_sha256']})
        applied = service.sqlite_schema_application('owned','sqlite_schema_apply',
            {'database_target_id':'file','review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True})
        assert applied['state'] == 'committed',applied
        assert applied['outcome']['rediscovery_verified'] and applied['outcome']['explorer_invalidated']
        with sqlite3.connect(path) as observer:
            if kind == 'rebuild': assert observer.execute('SELECT note,typeof(note) FROM owned').fetchone() == (7,'integer')
            else: assert observer.execute('PRAGMA index_list(owned)').fetchone()[2] == 1
        again = service.sqlite_schema_application('owned','sqlite_schema_apply',
            {'database_target_id':'file','review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True})
        assert again['state'] == 'committed'
    finally:
        provider.client.close()


@pytest.mark.parametrize('failure',[None,'unique','trigger-binding'])
def test_replacement_batch_commits_together_or_restores_every_original_object(tmp_path,failure):
    path,target_path = tmp_path/'batch.sqlite',tmp_path/'desired-batch.sqlite'
    originals = {'a_first':'CREATE INDEX "main"."a_first" ON "owned"(id)',
                 'z_last':'CREATE INDEX "main"."z_last" ON "owned"(note)',
                 'touch':'CREATE TRIGGER "main"."touch" AFTER INSERT ON "owned" BEGIN SELECT new.id; END'}
    desired_sql = dict(originals,a_first='CREATE INDEX "main"."a_first" ON "owned"(id DESC)')
    if failure == 'unique': desired_sql['z_last'] = 'CREATE UNIQUE INDEX "main"."z_last" ON "owned"(note)'
    else:
        destination = 'missing_relation' if failure == 'trigger-binding' else 'audit'
        desired_sql['touch'] = f'CREATE TRIGGER "main"."touch" AFTER INSERT ON "owned" BEGIN INSERT INTO {destination} VALUES(new.note); END'
    for filename,definitions in ((path,originals),(target_path,desired_sql)):
        with sqlite3.connect(filename) as connection:
            connection.executescript('CREATE TABLE owned(id INTEGER PRIMARY KEY,note TEXT); CREATE TABLE audit(value TEXT);')
            for source in definitions.values(): connection.execute(source)
    provider = SQLiteProvider(SimpleNamespace(),SimpleNamespace(require=Mock()),_create_client())
    route = {'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        def capture(filename):
            return build_export(provider.capture_catalog({**route,'database':str(filename)})['resources'],
                endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite',native_model=True)
        baseline,template = capture(path),capture(target_path)
        desired = deepcopy(baseline)
        for name,source in desired_sql.items():
            if source == originals[name]: continue
            kind = 'trigger' if name == 'touch' else 'index'
            identity = _resource_id(kind,['main','owned'],name)
            desired['rows'][identity] = deepcopy(template['rows'][identity])
            desired['rows'][identity]['native']['ddl'] = source
        with sqlite3.connect(path) as connection:
            connection.executemany('INSERT INTO owned VALUES(?,?)',[(1,'duplicate'),(2,'duplicate')])
            original_schema = connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
            preview = plan(baseline,desired,baseline,connection)
            assert preview['ready_for_review'],preview
            assert len(preview['operations']) == 2
            assert plan(baseline,desired,baseline,connection)['execution_sha256'] == preview['execution_sha256']
        info = path.stat()
        store = SQLiteSchemaApplications(tmp_path/'batch-receipts.json')
        reviewed = store.review(preview,baseline,desired,'owner','binding','file',file_identity=[info.st_dev,info.st_ino])
        request = {key:reviewed[key] for key in ('review_id','review_digest')}; request['confirmed'] = True
        result = store.apply(request,'owner','binding',lambda record:apply_review(provider,route,record))
        expected = 'rolled_back' if failure else 'committed'
        assert result['state'] == expected,result
        assert store.apply(request,'owner','binding',lambda _:pytest.fail('replayed'))['state'] == expected
        with sqlite3.connect(path) as observer:
            assert observer.execute('SELECT * FROM owned').fetchall() == [(1,'duplicate'),(2,'duplicate')]
            assert observer.execute('SELECT * FROM audit').fetchall() == []
            if failure:
                assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall() == original_schema
            else:
                assert observer.execute('PRAGMA index_xinfo(a_first)').fetchone()[3] == 1
                observer.execute("INSERT INTO owned VALUES(3,'new')")
                assert observer.execute('SELECT * FROM audit').fetchall() == [('new',)]
    finally:
        provider.client.close()
