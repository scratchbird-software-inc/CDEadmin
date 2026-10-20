"""Native catalog spelling must bind exact DDN declarations and preserve bodies."""
from copy import deepcopy
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite.declarations import canonical_create
from pgadmin.cdeadmin.providers.sqlite.provider import _resource_id,SQLiteProvider,_create_client
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import plan,_definition
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import _source,_compile_exact
from pgadmin.cdeadmin.workspace.sqlite_schema_apply import SQLiteSchemaApplications,apply_review
from tools.tests.test_sqlite_schema_plan import _model


@pytest.mark.parametrize('source',[
    'CREATE TABLE owned (id INTEGER, txt TEXT DEFAULT \'CREATE TABLE main.other(x)\')',
    'create table [owned] (id INTEGER, txt TEXT DEFAULT \'CREATE TABLE main.other(x)\')',
    'CREATE TABLE `owned` (id INTEGER, txt TEXT DEFAULT \'CREATE TABLE main.other(x)\')',
    'CREATE TABLE \'owned\' (id INTEGER, txt TEXT DEFAULT \'CREATE TABLE main.other(x)\')',
    'CREATE TABLE IF NOT EXISTS "mAiN".owned (id INTEGER, txt TEXT DEFAULT \'CREATE TABLE main.other(x)\')',
    '/* native comment */ CREATE /* declaration */ TABLE owned (id INTEGER, txt TEXT DEFAULT \'CREATE TABLE main.other(x)\')',
])
def test_catalog_header_spellings_generate_the_exact_native_target(source):
    result=canonical_create(source,'table','main','owned')
    assert result=='CREATE TABLE "main"."owned" (id INTEGER, txt TEXT DEFAULT \'CREATE TABLE main.other(x)\')'
    with sqlite3.connect(':memory:') as connection:
        connection.execute('EXPLAIN '+result).fetchone()
        assert not connection.execute("SELECT 1 FROM sqlite_schema WHERE name='owned'").fetchall()
        connection.execute(result);connection.execute('INSERT INTO owned(id) VALUES(1)')
        assert connection.execute('SELECT txt FROM owned').fetchone()==('CREATE TABLE main.other(x)',)


@pytest.mark.parametrize('schema',['main','temp','Other schema ü'])
def test_unqualified_catalog_declarations_bind_the_selected_native_namespace(schema):
    with sqlite3.connect(':memory:') as connection:
        connection.execute("ATTACH ':memory:' AS \"Other schema ü\"")
        source=canonical_create('CREATE TABLE "a.b ü"(id INTEGER)','table',schema,'a.b ü')
        connection.execute(source)
        for namespace in ('main','temp','Other schema ü'):
            assert bool(connection.execute('SELECT name FROM "'+namespace+'".sqlite_schema WHERE name=?',('a.b ü',)).fetchone()) is (namespace==schema)


def test_native_temp_trigger_binds_attached_owner_without_touching_body_or_caller_savepoint():
    with sqlite3.connect(':memory:') as connection:
        connection.executescript("ATTACH ':memory:' AS aux;CREATE TABLE main.owner(id);CREATE TEMP TABLE owner(id);CREATE TABLE aux.owner(id);CREATE TABLE effects(id,note);")
        connection.execute('INSERT INTO effects VALUES(1,\'pending\')');connection.execute('SAVEPOINT caller')
        body=" AFTER INSERT ON aux.owner BEGIN INSERT INTO effects VALUES(NEW.id,'ON main.owner CREATE TRIGGER'); END"
        source=canonical_create('CREATE TEMP TRIGGER \'tr ü\''+body,'trigger','temp','tr ü',owner='owner',owner_schema='aux')
        assert source=='CREATE TRIGGER "temp"."tr ü" AFTER INSERT ON "aux"."owner"'+body[body.index(' BEGIN'):]
        connection.execute('EXPLAIN '+source).fetchone()
        assert connection.execute('SELECT count(*) FROM temp.sqlite_schema WHERE type=\'trigger\'').fetchone()==(0,)
        connection.execute(source);connection.execute('INSERT INTO aux.owner VALUES(73)')
        assert connection.execute('SELECT id FROM effects ORDER BY id').fetchall()==[(1,),(73,)]
        connection.execute('ROLLBACK TO caller')
        assert connection.execute('SELECT id FROM effects').fetchall()==[(1,)]
        assert connection.execute('SELECT count(*) FROM temp.sqlite_schema WHERE type=\'trigger\'').fetchone()==(0,)


@pytest.mark.parametrize('kind,name,source',[
    ('view','native_view','CREATE VIEW "native_view"AS SELECT id FROM owned'),
    ('index','native_index','CREATE INDEX "native_index"/* declaration */ON owned /* keys */(id)'),
    ('trigger','native_trigger','CREATE TRIGGER "native_trigger"INSERT ON "owned"BEGIN SELECT NEW.id; END'),
])
def test_native_header_spacing_comments_and_default_trigger_timing_are_compiled(kind,name,source):
    parent=['main','owned'] if kind in {'index','trigger'} else ['main']
    row={'resource_id':_resource_id(kind,parent,name),'kind':kind,'path':[*parent,name],'name':name,'system':'false',
        'native':{'system_object':False,'ddl':source,'catalog_metadata':{'table_name':'owned'} if kind in {'index','trigger'} else {}}}
    with sqlite3.connect(':memory:') as connection:
        connection.execute('CREATE TABLE owned(id INTEGER)')
        generated=_source(row);_compile_exact(connection,row,generated)
        assert connection.execute('SELECT count(*) FROM main.sqlite_schema WHERE name=?',(name,)).fetchone()==(0,)
        connection.execute(generated)
        assert connection.execute('SELECT count(*) FROM main.sqlite_schema WHERE name=?',(name,)).fetchone()==(1,)


@pytest.mark.parametrize('source,kind,schema,name,owner',[
    ('CREATE TABLE other(id)','table','main','owned',None),
    ('CREATE TABLE aux.owned(id)','table','main','owned',None),
    ('CREATE TEMP TABLE owned(id)','table','main','owned',None),
    ('CREATE TEMP INDEX owned ON t(id)','index','temp','owned','t'),
    ('CREATE UNIQUE TABLE owned(id)','table','main','owned',None),
    ('CREATE VIRTUAL VIEW owned AS SELECT 1','view','main','owned',None),
    ('CREATE INDEX owned ON main.t(id)','index','main','owned','t'),
    ('CREATE INDEX owned ON other(id)','index','main','owned','t'),
    ('CREATE TRIGGER owned AFTER INSERT ON aux.t BEGIN SELECT 1; END','trigger','main','owned','t'),
    ('CREATE TRIGGER owned AFTER INSERT ON t BEGIN SELECT 1; END','trigger','temp','owned','t'),
    ('CREATE\u00a0TABLE owned(id)','table','main','owned',None),
    ('CREATE TABLE "open(id)','table','main','owned',None),
    ('CREATE TABLE owned','table','main','owned',None),
    ('CREATE TABLE owned AS SELECT 1','table','main','owned',None),
])
def test_conflicting_scope_and_malformed_headers_never_become_accepted_sql(source,kind,schema,name,owner):
    with pytest.raises(ValueError):canonical_create(source,kind,schema,name,owner=owner)


def test_malformed_design_path_has_a_bounded_refusal_before_native_compilation():
    row={'resource_id':'invalid','kind':'table','path':[],'name':'owned','system':'false',
        'native':{'system_object':False,'ddl':'CREATE TABLE owned(id INTEGER)'}}
    assert _definition(row)['ddl']==row['native']['ddl']
    with pytest.raises(ValueError,match='main registered file'):_source(row)


def test_sqlite_ascii_keyword_rules_preserve_distinct_unicode_identifier_names():
    with sqlite3.connect(':memory:') as connection:
        connection.execute('CREATE TABLE ıf(id INTEGER)')
        source=connection.execute("SELECT sql FROM sqlite_schema WHERE name='ıf'").fetchone()[0]
        assert canonical_create(source,'table','main','ıf')=='CREATE TABLE "main"."ıf"(id INTEGER)'
    with pytest.raises(ValueError):canonical_create('CREATE TABLE IF NOT EXIſTS owned(id INTEGER)','table','main','owned')


@pytest.mark.parametrize('name',['long name '*40,'日本🙂"'*70])
def test_sqlite_identifier_generation_uses_its_statement_budget(name):
    source="CREATE TABLE '"+name+"'(id INTEGER)"
    row={'resource_id':_resource_id('table',['main'],name),'kind':'table','path':['main',name],'name':name,'system':'false',
        'native':{'system_object':False,'ddl':source}}
    with sqlite3.connect(':memory:') as connection:
        generated=_source(row);_compile_exact(connection,row,generated);connection.execute(generated)
        assert connection.execute('SELECT name FROM sqlite_schema WHERE type=\'table\'').fetchall()==[(name,)]


def test_main_catalog_source_creates_once_and_native_rediscovery_matches_generated_sql(tmp_path):
    path=tmp_path/'native.sqlite'
    with sqlite3.connect(path) as setup:setup.execute('CREATE TABLE owned(id INTEGER)')
    provider=SQLiteProvider(SimpleNamespace(),SimpleNamespace(require=Mock()),_create_client())
    route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:
        resources=provider.capture_catalog(route)['resources']
        baseline=_model();baseline['rows']={row['resource_id']:{'resource_id':row['resource_id'],'kind':row['resource_kind'],
            'path':row['display_path'],'name':row['display_name'],'system':'true' if row['native'].get('system_object') else 'false',
            'native':row['native']} for row in resources}
        desired=deepcopy(baseline)
        for kind,name,source in (
            ('table','bare ü',"CREATE TABLE [bare ü](id INTEGER, txt TEXT DEFAULT 'main.owned')"),
            ('view','native_view','CREATE VIEW native_view AS SELECT id FROM owned'),
            ('index','native_index','CREATE UNIQUE INDEX native_index ON [owned](id)'),
            ('trigger','native_trigger','CREATE TRIGGER native_trigger AFTER INSERT ON owned BEGIN SELECT NEW.id; END')):
            parent=['main','owned'] if kind in {'index','trigger'} else ['main']
            identity=_resource_id(kind,parent,name)
            desired['rows'][identity]={'resource_id':identity,'kind':kind,'path':[*parent,name],'name':name,'system':'false',
                'native':{'system_object':False,'ddl':source,'catalog_metadata':{'table_name':'owned'} if kind in {'index','trigger'} else {}}}
        with sqlite3.connect(path) as connection:preview=plan(baseline,desired,baseline,connection)
        assert preview['ready_for_review'],preview
        archive=SQLiteSchemaApplications(tmp_path/'receipts.json');info=path.stat()
        review=archive.review(preview,baseline,desired,'owner','binding','file',file_identity=[info.st_dev,info.st_ino])
        request={'review_id':review['review_id'],'review_digest':review['review_digest'],'confirmed':True}
        result=archive.apply(request,'owner','binding',lambda record:apply_review(provider,route,record))
        assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
        assert archive.apply(request,'owner','binding',lambda _record:pytest.fail('native DDL replayed'))['state']=='committed'
        observed=provider.capture_catalog(route)['resources']
        wanted=next(row for row in desired['rows'].values() if row['kind']=='table' and row['name']=='bare ü')
        actual=next(row for row in observed if row['resource_kind']=='table' and row['display_name']=='bare ü')
        assert _definition(wanted)['ddl']==_definition({'kind':'table','path':actual['display_path'],'name':actual['display_name'],'system':'false','native':actual['native']})['ddl']
    finally:provider.client.close()
