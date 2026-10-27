"""Native coordinated table conversions and whole-batch rollback."""
from contextlib import closing, contextmanager
from copy import deepcopy
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider, _create_client, _resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import plan
from pgadmin.cdeadmin.workspace.sqlite_schema_apply import SQLiteSchemaApplications, apply_review


@contextmanager
def prepared(tmp_path,original,target,seeds):
    path,target_path = tmp_path/'graph.sqlite',tmp_path/'desired.sqlite'
    for filename,definitions in ((path,original),(target_path,target)):
        with closing(sqlite3.connect(filename)) as connection:
            for source in definitions.values(): connection.execute(source)
            connection.executescript('CREATE TABLE audit(value TEXT); '
                'CREATE INDEX by_parent ON a_child(parent_id); '
                'CREATE VIEW retained AS SELECT c.id,c.parent_id,p.id AS parent_key FROM a_child c JOIN z_parent p ON c.parent_id=p.id; '
                'CREATE TRIGGER parent_touch AFTER INSERT ON z_parent BEGIN INSERT INTO audit VALUES(new.id); END;')
            connection.commit()
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        for source,args in seeds: connection.execute(source,args)
        connection.execute('DELETE FROM audit')
        connection.commit()
        original_schema = connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
    provider = SQLiteProvider(SimpleNamespace(),SimpleNamespace(require=Mock()),_create_client())
    route = {'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        def capture(filename):
            return build_export(provider.capture_catalog({**route,'database':str(filename)})['resources'],
                endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite',native_model=True)
        baseline,template = capture(path),capture(target_path)
        desired = deepcopy(baseline)
        for name,source in target.items():
            for identity,row in list(desired['rows'].items()):
                if row['path'][:2] == ['main',name]: del desired['rows'][identity]
            desired['rows'].update({identity:row for identity,row in template['rows'].items() if row['path'][:2] == ['main',name]})
            desired['rows'][_resource_id('table',['main'],name)]['native']['ddl'] = source
        rebuilds = [_resource_id('table',['main'],name) for name in sorted(target)]
        with closing(sqlite3.connect(path)) as connection:
            preview = plan(baseline,desired,baseline,connection,rebuilds=rebuilds)
            assert preview['ready_for_review'],preview
            assert [operation['name'] for operation in preview['operations']] == sorted(target)
            assert plan(baseline,desired,baseline,connection,rebuilds=rebuilds)['execution_sha256'] == preview['execution_sha256']
        info = path.stat()
        store = SQLiteSchemaApplications(tmp_path/'receipts.json')
        receipt = store.review(preview,baseline,desired,'owner','binding','file',file_identity=[info.st_dev,info.st_ino])
        request = {key:receipt[key] for key in ('review_id','review_digest')}; request['confirmed'] = True
        yield provider,route,path,store,request,original_schema
    finally:
        provider.client.close()


@pytest.mark.parametrize('failure',[None,'unique','foreign-key','stale'])
def test_related_parent_child_key_conversion_uses_final_schema_and_rolls_back_together(tmp_path,failure):
    original = {'z_parent':'CREATE TABLE "main"."z_parent"(id TEXT PRIMARY KEY,note TEXT)',
                'a_child':'CREATE TABLE "main"."a_child"(id INTEGER PRIMARY KEY,parent_id TEXT REFERENCES z_parent(id))'}
    target = {'z_parent':('CREATE TABLE "main"."z_parent"(id TEXT PRIMARY KEY,note TEXT,added INT DEFAULT 1)' if failure == 'foreign-key' else
                          'CREATE TABLE "main"."z_parent"(id INTEGER PRIMARY KEY,note TEXT)'),
              'a_child':'CREATE TABLE "main"."a_child"(id INTEGER PRIMARY KEY,parent_id INTEGER REFERENCES z_parent(id))'}
    seeds = [('INSERT INTO z_parent VALUES(?,?)',('001','kept')),('INSERT INTO a_child VALUES(?,?)',(9,'001'))]
    if failure == 'unique': seeds.insert(1,('INSERT INTO z_parent VALUES(?,?)',('1','distinct text key')))
    with prepared(tmp_path,original,target,seeds) as (provider,route,path,store,request,original_schema):
        if failure == 'stale':
            with closing(sqlite3.connect(path)) as connection:
                connection.execute('ALTER TABLE z_parent ADD COLUMN changed INT'); connection.commit()
        result = store.apply(request,'owner','binding',lambda record:apply_review(provider,route,record))
        expected = 'not_dispatched' if failure == 'stale' else 'rolled_back' if failure else 'committed'
        assert result['state'] == expected,result
        assert store.apply(request,'owner','binding',lambda _:pytest.fail('replayed'))['state'] == expected
        with closing(sqlite3.connect(path)) as observer:
            observer.execute('PRAGMA foreign_keys=ON')
            assert observer.execute('PRAGMA foreign_key_check').fetchall() == []
            assert observer.execute('SELECT * FROM audit').fetchall() == []
            if failure:
                assert observer.execute('SELECT parent_id,typeof(parent_id) FROM a_child').fetchone() == ('001','text')
                if failure != 'stale': assert observer.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall() == original_schema
            else:
                assert result['outcome']['rediscovery_verified']
                assert observer.execute('SELECT * FROM retained').fetchall() == [(9,1,1)]
                assert observer.execute('SELECT typeof(parent_id) FROM a_child').fetchone() == ('integer',)
                assert observer.execute('SELECT typeof(id) FROM z_parent').fetchone() == ('integer',)
                observer.execute("INSERT INTO z_parent VALUES(2,'after commit')")
                assert observer.execute('SELECT * FROM audit').fetchall() == [('2',)]


def test_each_table_retains_autoincrement_high_water_mark_in_the_rebuild_batch(tmp_path):
    original = {'z_parent':'CREATE TABLE "main"."z_parent"(id INTEGER PRIMARY KEY AUTOINCREMENT,note TEXT)',
                'a_child':'CREATE TABLE "main"."a_child"(id INTEGER PRIMARY KEY AUTOINCREMENT,parent_id INTEGER REFERENCES z_parent(id),note TEXT)'}
    target = {'z_parent':'CREATE TABLE "main"."z_parent"(id INTEGER PRIMARY KEY AUTOINCREMENT,note TEXT,added INTEGER DEFAULT 1)',
              'a_child':'CREATE TABLE "main"."a_child"(id INTEGER PRIMARY KEY AUTOINCREMENT,parent_id INTEGER REFERENCES z_parent(id),note INTEGER)'}
    seeds = [('INSERT INTO z_parent VALUES(?,?)',(1,'kept')),('INSERT INTO z_parent VALUES(?,?)',(100,'removed')),
             ('INSERT INTO a_child VALUES(?,?,?)',(1,1,'007')),('INSERT INTO a_child VALUES(?,?,?)',(200,1,'008')),
             ('DELETE FROM a_child WHERE id=?',(200,)),('DELETE FROM z_parent WHERE id=?',(100,))]
    with prepared(tmp_path,original,target,seeds) as (provider,route,path,store,request,_):
        result = store.apply(request,'owner','binding',lambda record:apply_review(provider,route,record))
        assert result['state'] == 'committed',result
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT name,seq FROM sqlite_sequence ORDER BY name').fetchall() == [('a_child',200),('z_parent',100)]
            assert observer.execute('SELECT note,typeof(note) FROM a_child').fetchone() == (7,'integer')
            assert observer.execute('INSERT INTO z_parent(note) VALUES(?) RETURNING id',('next',)).fetchone() == (101,)
            assert observer.execute('INSERT INTO a_child(parent_id,note) VALUES(?,?) RETURNING id',(101,9)).fetchone() == (201,)
