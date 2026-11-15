"""Typed descriptors -> native prototype -> retained review -> native atomic apply."""
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import Mock
import sqlite3
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider,_create_client,_resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.sqlite_object_design import generate
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import plan
from pgadmin.cdeadmin.workspace.sqlite_schema_apply import SQLiteSchemaApplications,apply_review
from ui_descriptor_roundtrip import engine_operations,operation_draft


@pytest.fixture
def owned(tmp_path):
    path=tmp_path/'owned.db'
    with closing(sqlite3.connect(path)) as c:
        c.executescript('CREATE TABLE source(id INTEGER PRIMARY KEY AUTOINCREMENT,value TEXT,CONSTRAINT keep_unique UNIQUE(value));'
            "INSERT INTO source VALUES(1,'001'); INSERT INTO source VALUES(80,'gone'); DELETE FROM source WHERE id=80;"
            'CREATE TABLE audit(value); CREATE INDEX by_value ON source(value);'
            'CREATE TRIGGER source_touch AFTER INSERT ON source BEGIN INSERT INTO audit VALUES(new.id); END;'
            'CREATE VIEW projection AS SELECT id,value FROM source;'
            'CREATE TRIGGER projection_write INSTEAD OF INSERT ON projection BEGIN INSERT INTO source(value) VALUES(new.value); END;')
    provider=SQLiteProvider(SimpleNamespace(),SimpleNamespace(require=Mock()),_create_client())
    route={'database':str(path),'filesystem_root':str(tmp_path)}
    captured=provider.capture_catalog(route,include_system=False)
    baseline=build_export(captured['resources'],endpoint_id='owned',target_id='file',generation=captured['generation'],engine='sqlite',native_model=True)
    try:yield path,provider,route,baseline
    finally:provider.client.close()


def execute(owned,tmp_path,operation,kind,fields):
    path,provider,route,baseline=owned
    identity=_resource_id(kind,['main'],'source' if kind=='table' else 'projection')
    op=engine_operations('sqlite')[operation+'@'+kind]
    draft=operation_draft(op,fields)
    desired=generate(baseline,identity,operation,draft)
    before=path.read_bytes()
    with closing(sqlite3.connect(path)) as c:
        preview=plan(baseline,desired,baseline,c,rebuilds=[identity] if operation=='rebuild' else [])
    assert preview['ready_for_review'],{k:v for k,v in preview.items()if k not in {'operations','sql_preview','statements'}}
    assert path.read_bytes()==before
    state=path.stat();store=SQLiteSchemaApplications(tmp_path/'receipts.json')
    receipt=store.review(preview,baseline,desired,'owner','binding','file',file_identity=[state.st_dev,state.st_ino])
    request={key:receipt[key] for key in ['review_id','review_digest']};request['confirmed']=True
    result=store.apply(request,'owner','binding',lambda record:apply_review(provider,route,record))
    assert store.apply(request,'owner','binding',lambda _:pytest.fail('automatic replay'))==result
    return result


def test_native_typed_rebuild_preserves_rows_constraints_children_and_autoincrement(owned,tmp_path):
    result=execute(owned,tmp_path,'rebuild','table',{'columns':[
        {'name':'id','type':'INTEGER','primary_key':True,'autoincrement':True},
        {'name':'value','type':'INTEGER'}, {'name':'added','type':'TEXT','default':"'kept'"}]})
    assert result['state']=='committed',result
    with closing(sqlite3.connect(owned[0])) as c:
        assert c.execute('SELECT * FROM projection').fetchall()==[(1,1)]
        assert c.execute('SELECT added FROM source').fetchone()==('kept',)
        assert c.execute('SELECT * FROM audit').fetchall()==[]
        c.execute("INSERT INTO projection(value) VALUES('2')")
        assert c.execute('SELECT max(id) FROM source').fetchone()==(81,)
        assert c.execute('SELECT * FROM audit').fetchall()==[(81,)]
        with pytest.raises(sqlite3.IntegrityError):c.execute('INSERT INTO source(value) VALUES(2)')
        assert c.execute("SELECT name FROM sqlite_schema WHERE name='by_value'").fetchone()


def test_native_typed_view_replace_retains_instead_trigger_and_projection(owned,tmp_path):
    result=execute(owned,tmp_path,'replace','view',{'query':'SELECT id,value FROM source WHERE id>0','column_names':[]})
    assert result['state']=='committed',result
    with closing(sqlite3.connect(owned[0])) as c:
        assert c.execute('SELECT * FROM projection').fetchall()==[(1,'001')]
        c.execute("INSERT INTO projection(value) VALUES('via_view')")
        assert c.execute('SELECT value FROM source WHERE id=81').fetchone()==('via_view',)


@pytest.mark.parametrize('query',['SELECT absent FROM source','SELECT 7; DROP TABLE source','DELETE FROM source','SELECT missing_function(value) FROM source'])
def test_native_invalid_view_design_never_changes_registered_file(owned,query):
    before=owned[0].read_bytes()
    with pytest.raises((ValueError,sqlite3.Error)):
        generate(owned[3],_resource_id('view',['main'],'projection'),'replace',{'query':query})
    assert owned[0].read_bytes()==before


def test_rebuild_preview_rejects_forged_or_stale_derived_view_column_types(owned):
    from copy import deepcopy
    baseline=owned[3];identity=_resource_id('table',['main'],'source')
    desired=generate(baseline,identity,'rebuild',{'columns':[
        {'name':'id','type':'INTEGER','primary_key':True,'autoincrement':True},
        {'name':'value','type':'INTEGER'}]})
    projection=_resource_id('column',['main','projection'],'value')
    desired['rows'][projection]['native']['catalog_metadata']['data_type']='not the native view type'
    with closing(sqlite3.connect(owned[0])) as c:
        preview=plan(baseline,desired,baseline,c,rebuilds=[identity])
    assert not preview['ready_for_review']
    assert any('view projection' in b['reason'] for b in preview['blockers'])
