"""Structured native column properties produce complete DDN, not direct writes."""
from contextlib import closing
from copy import deepcopy
import sqlite3

import pytest
from test_sqlite_catalog_columns import models,apply
from pgadmin.cdeadmin.providers.sqlite.provider import _resource_id
from pgadmin.cdeadmin.workspace.sqlite_column_design import generate
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import plan


def test_structured_native_columns_preserve_properties_projection_and_rows(tmp_path):
    path=tmp_path/'typed.sqlite';baseline,_=models(path,[])
    table=_resource_id('table',['main'],'owned')
    before=deepcopy(baseline)
    desired=generate(baseline,table,[{'name':'untyped:雪'},
        {'name':'default text','data_type':'TEXT','nullable':False,'default':"'a, ON main.owned'",
         'collation':'NOCASE','check':'length("default text") > 1',
         'constraint_names':{'not_null':'required:雪','default':'default value','check':'check value','collation':'case name'}},
        {'name':'doubled','generated':{'expression':'id * 2','storage':'virtual'},
         'constraint_names':{'generated':'native generation'}}])
    assert baseline==before
    with closing(sqlite3.connect(path)) as connection:
        assert [row[1] for row in connection.execute('PRAGMA table_xinfo(owned)')]==['id','note']
        preview=plan(baseline,desired,baseline,connection)
    assert preview['ready_for_review'],preview
    result=apply(path,tmp_path,baseline,desired,preview)
    assert result['state']=='committed',result
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute('SELECT * FROM projection').fetchone()==(7,'preserved',None,'a, ON main.owned',14)
        sql=connection.execute("SELECT sql FROM sqlite_schema WHERE name='owned'").fetchone()[0]
        for name in ('required:雪','default value','check value','case name','native generation'):assert '"'+name+'"' in sql


def test_structured_native_reference_actions_timing_names_and_default_key(tmp_path):
    path=tmp_path/'reference.sqlite';baseline,_=models(path,[],rows=False,base=(
        'CREATE TABLE parent(id INTEGER PRIMARY KEY);'
        'CREATE TABLE owned(id INTEGER PRIMARY KEY,note TEXT);'))
    table=_resource_id('table',['main'],'owned')
    desired=generate(baseline,table,[{'name':'parent id','data_type':'INTEGER','references':{
        'table':'parent','column':'id','on_update':'CASCADE','on_delete':'SET NULL','match':'simple',
        'deferrable':True,'initially':'DEFERRED'},'constraint_names':{'references':'link:雪'}},
        {'name':'implicit key','data_type':'INTEGER','references':{'table':'parent'}}])
    result=apply(path,tmp_path,baseline,desired);assert result['state']=='committed',result
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('PRAGMA foreign_keys=ON');connection.execute('BEGIN')
        connection.execute('INSERT INTO owned(id,"parent id","implicit key") VALUES(3,9,NULL)')
        connection.execute('INSERT INTO parent VALUES(9)');connection.commit()
        connection.execute('UPDATE parent SET id=10')
        assert connection.execute('SELECT "parent id" FROM owned').fetchone()==(10,)
        connection.execute('DELETE FROM parent')
        assert connection.execute('SELECT "parent id" FROM owned').fetchone()==(None,)


def test_structured_stored_generation_uses_native_empty_table_capability(tmp_path):
    path=tmp_path/'stored.sqlite';baseline,_=models(path,[],rows=False)
    desired=generate(baseline,_resource_id('table',['main'],'owned'),[
        {'name':'stored','data_type':'INTEGER','generated':{'expression':'id * 2','storage':'stored'}}])
    result=apply(path,tmp_path,baseline,desired);assert result['state']=='committed',result
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('INSERT INTO owned(id) VALUES(9)')
        assert connection.execute('SELECT stored FROM owned').fetchone()==(18,)


@pytest.mark.parametrize('column',[
    {'name':'x','data_type':'TEXT); DROP TABLE owned; --'},
    {'name':'x','data_type':'TEXT, unintended INTEGER'},
    {'name':'x','generated':{'expression':'id * 2','storage':'invalid'}},
    {'name':'x','references':{'table':'owned','on_delete':'DROP TABLE owned'}},
    {'name':'x','constraint_names':{'generated':'lost definition'}},
    {'name':'x','nullable':'false'},
])
def test_structured_generation_never_mutates_file_on_native_or_admission_refusal(tmp_path,column):
    path=tmp_path/'refuse.sqlite';baseline,_=models(path,[])
    with pytest.raises((ValueError,sqlite3.Error)):
        generate(baseline,_resource_id('table',['main'],'owned'),[column])
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute('SELECT * FROM owned').fetchall()==[(7,'preserved')]
        assert [row[1] for row in connection.execute('PRAGMA table_xinfo(owned)')]==['id','note']


def test_structured_generation_keeps_retained_session_boundary(tmp_path):
    path=tmp_path/'scope.sqlite';baseline,_=models(path,[])
    baseline['provenance']['observation_scope']='retained-session'
    with pytest.raises(ValueError,match='Retained-session'):
        generate(baseline,_resource_id('table',['main'],'owned'),[{'name':'native'}])
