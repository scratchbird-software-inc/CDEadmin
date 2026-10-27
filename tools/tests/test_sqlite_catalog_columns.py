"""Real native catalog-derived columns, preservation and atomic refusal."""
from contextlib import closing
from copy import deepcopy
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider,_create_client,_resources,_resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import plan
from pgadmin.cdeadmin.workspace.sqlite_schema_apply import SQLiteSchemaApplications,apply_review


BASE=('CREATE TABLE owned(id INTEGER PRIMARY KEY,note TEXT);'
      'CREATE TABLE audit(id INTEGER,note TEXT);'
      'CREATE INDEX retained_index ON owned(note);'
      'CREATE TRIGGER retained_trigger AFTER INSERT ON owned BEGIN INSERT INTO audit VALUES(NEW.id,NEW.note); END;'
      'CREATE VIEW projection AS SELECT * FROM owned;')


def models(path,extra,*,rows=True,base=BASE,tail=''):
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(base)
        if rows:connection.execute("INSERT INTO owned VALUES(7,'preserved')")
        connection.commit()
        baseline=build_export(_resources(connection,{}),endpoint_id='endpoint',target_id='file',
            generation='baseline',engine='sqlite',native_model=True)
    with closing(sqlite3.connect(':memory:')) as prototype:
        prototype.executescript(base)
        for clause in extra:prototype.execute('ALTER TABLE owned ADD COLUMN '+clause)
        if tail:prototype.executescript(tail)
        template=build_export(_resources(prototype,{}),endpoint_id='endpoint',target_id='file',
            generation='desired',engine='sqlite',native_model=True)
    desired=deepcopy(baseline)
    for identity,row in template['rows'].items():
        if len(row['path'])>1:desired['rows'][identity]=row
    return baseline,desired


def apply(path,tmp_path,baseline,desired,preview=None,before_apply=None):
    provider=SQLiteProvider(SimpleNamespace(),SimpleNamespace(require=Mock()),_create_client())
    route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        if preview is None:
            with closing(sqlite3.connect(path)) as connection:preview=plan(baseline,desired,baseline,connection)
        assert preview['ready_for_review'],preview
        info=path.stat();applications=SQLiteSchemaApplications(tmp_path/'receipts.json')
        reviewed=applications.review(preview,baseline,desired,'owner','endpoint','file',
            file_identity=[info.st_dev,info.st_ino])
        request={'review_id':reviewed['review_id'],'review_digest':reviewed['review_digest'],'confirmed':True}
        if before_apply:before_apply()
        result=applications.apply(request,'owner','endpoint',lambda record:apply_review(provider,route,record))
        assert applications.apply(request,'owner','endpoint',lambda _:pytest.fail('must never replay'))==result
        return result
    finally:provider.client.close()


@pytest.mark.parametrize('clauses,rows,expected',[
    (['untyped'],True,(7,'preserved',None)),
    (['doubled AS (id * 2) VIRTUAL'],True,(7,'preserved',14)),
    (['untyped','doubled AS (id * 2) VIRTUAL','stored AS (doubled + 1) STORED'],False,None),
    (["stamp TEXT DEFAULT CURRENT_TIMESTAMP"],False,None),
    (['must_have TEXT NOT NULL'],False,None),
])
def test_native_catalog_adds_untyped_generated_and_empty_table_definitions(tmp_path,clauses,rows,expected):
    path=tmp_path/'native.sqlite';baseline,desired=models(path,clauses,rows=rows)
    with closing(sqlite3.connect(path)) as connection:
        preview=plan(baseline,desired,baseline,connection)
        assert preview['ready_for_review'],preview
        assert len(preview['operations'])==1 and preview['operations'][0]['operation']=='append-columns'
        assert len(connection.execute('PRAGMA table_xinfo(owned)').fetchall())==2
    result=apply(path,tmp_path,baseline,desired,preview)
    assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
    with closing(sqlite3.connect(path)) as connection:
        observed=connection.execute('SELECT * FROM projection').fetchall()
        assert observed==([expected] if expected else [])
        assert connection.execute("SELECT name FROM sqlite_schema WHERE type IN ('index','trigger') AND name LIKE 'retained_%' ORDER BY name").fetchall()==[('retained_index',),('retained_trigger',)]
        if not rows and any('STORED' in clause for clause in clauses):
            connection.execute("INSERT INTO owned(id,note,untyped) VALUES(8,'native','literal')")
            assert connection.execute('SELECT doubled,stored FROM owned').fetchone()==(16,17)


@pytest.mark.parametrize('clause,message',[
    ('stored AS (id * 2) STORED','STORED'),
    ('stamp TEXT DEFAULT CURRENT_TIMESTAMP','non-constant'),
    ('must_have TEXT NOT NULL','NOT NULL'),
    ('checked INTEGER CHECK(id < 0)','CHECK'),
])
def test_actual_rows_own_native_refusal_and_prior_stages_roll_back(tmp_path,clause,message):
    path=tmp_path/'native-refusal.sqlite';baseline,desired=models(path,['first_untyped',clause])
    result=apply(path,tmp_path,baseline,desired)
    assert result['state']=='rolled_back',result
    assert message in result['outcome']['native_error']
    with closing(sqlite3.connect(path)) as connection:
        assert [item[1] for item in connection.execute('PRAGMA table_xinfo(owned)')]==['id','note']
        assert connection.execute('SELECT * FROM owned').fetchall()==[(7,'preserved')]
        assert connection.execute('SELECT * FROM audit').fetchall()==[(7,'preserved')]


def test_append_can_share_native_new_column_index_and_trigger_batch(tmp_path):
    path=tmp_path/'children.sqlite'
    baseline,desired=models(path,['doubled AS (id * 2) VIRTUAL'],tail=(
        'CREATE INDEX generated_index ON owned(doubled);'
        'CREATE TRIGGER generated_trigger AFTER INSERT ON owned BEGIN INSERT INTO audit VALUES(NEW.doubled,\'generated\'); END;'))
    result=apply(path,tmp_path,baseline,desired)
    assert result['state']=='committed',result
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("INSERT INTO owned(id,note) VALUES(9,'next')")
        assert connection.execute('SELECT id FROM owned INDEXED BY generated_index WHERE doubled=18').fetchall()==[(9,)]
        assert set(connection.execute('SELECT * FROM audit'))=={(7,'preserved'),(9,'next'),(18,'generated')}


@pytest.mark.parametrize('tamper',['old-definition','column-fact','parent-fact','missing-index','missing-column'])
def test_catalog_append_refuses_changes_outside_its_native_definition(tmp_path,tamper):
    path=tmp_path/'refuse.sqlite';baseline,desired=models(path,['extra'])
    table=_resource_id('table',['main'],'owned');column=_resource_id('column',['main','owned'],'extra')
    if tamper=='old-definition':desired['rows'][table]['native']['ddl']=desired['rows'][table]['native']['ddl'].replace('note TEXT','note INTEGER')
    if tamper=='column-fact':desired['rows'][column]['native']['catalog_metadata']['hidden']=3
    if tamper=='parent-fact':desired['rows'][table]['native']['columns'][-1]['data_type']='INTEGER'
    if tamper=='missing-index':del desired['rows'][_resource_id('index',['main','owned'],'retained_index')]
    if tamper=='missing-column':del desired['rows'][column]
    with closing(sqlite3.connect(path)) as connection:
        result=plan(baseline,desired,baseline,connection)
        assert not result['ready_for_review'] and result['blockers'],result
        assert [item[1] for item in connection.execute('PRAGMA table_xinfo(owned)')]==['id','note']


@pytest.mark.parametrize('change',['table','child'])
def test_catalog_append_revalidates_parent_and_children_under_write_lock(tmp_path,change):
    path=tmp_path/'stale.sqlite';baseline,desired=models(path,['extra'])
    def concurrent():
        with closing(sqlite3.connect(path)) as connection:
            connection.execute('ALTER TABLE owned ADD COLUMN concurrent' if change=='table' else
                'CREATE INDEX concurrent_index ON owned(id)')
            connection.commit()
    result=apply(path,tmp_path,baseline,desired,before_apply=concurrent)
    assert result['state']=='not_dispatched',result
    with closing(sqlite3.connect(path)) as connection:
        assert 'extra' not in [item[1] for item in connection.execute('PRAGMA table_xinfo(owned)')]


def test_native_append_keeps_strict_without_rowid_and_foreign_key_definitions(tmp_path):
    path=tmp_path/'strict.sqlite'
    baseline,desired=models(path,['extra TEXT','linked INTEGER REFERENCES parent(id)'],base=(
        'CREATE TABLE parent(id INTEGER PRIMARY KEY);'
        'CREATE TABLE owned(id INTEGER PRIMARY KEY,note TEXT) STRICT, WITHOUT ROWID;'))
    result=apply(path,tmp_path,baseline,desired)
    assert result['state']=='committed',result
    with closing(sqlite3.connect(path)) as connection:
        assert next(item for item in connection.execute('PRAGMA table_list') if item[1]=='owned')[4:]==(1,1)
        assert connection.execute('PRAGMA foreign_key_list(owned)').fetchone()[2:5]==('parent','linked','id')
        assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]


@pytest.mark.parametrize('tamper',['type','missing'])
def test_native_projection_postconditions_refuse_forged_or_filtered_view_columns(tmp_path,tamper):
    path=tmp_path/'projection.sqlite';baseline,desired=models(path,['extra'])
    identity=_resource_id('column',['main','projection'],'extra')
    if tamper=='missing':del desired['rows'][identity]
    else:desired['rows'][identity]['native']['catalog_metadata']['data_type']='INTEGER'
    result=apply(path,tmp_path,baseline,desired)
    assert result['state']=='rolled_back',result
    with closing(sqlite3.connect(path)) as connection:
        assert 'extra' not in [item[1] for item in connection.execute('PRAGMA table_xinfo(owned)')]
