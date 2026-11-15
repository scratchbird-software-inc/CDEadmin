"""Descriptor-to-facade/native acceptance for five recorded SQLite form gaps."""
import sqlite3
from types import SimpleNamespace
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import _create_client
from pgadmin.cdeadmin.visual_admin.provider import ProviderVisualAdministration, VisualAdminValidationError, VisualAdminExecutionError
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import resolved_form, backend_draft


@pytest.fixture
def native(tmp_path):
    path = tmp_path/'forms.db'
    with sqlite3.connect(path) as c:
        c.executescript("CREATE TABLE owned(id INTEGER PRIMARY KEY,label TEXT,enabled INTEGER); INSERT INTO owned VALUES(1,'ONE',1),(2,'one',0)")
    client = _create_client()
    facade = ProviderVisualAdministration(SimpleNamespace(endpoint_id='owned', mode='direct',runtime_verification_state='verified'),
        SimpleNamespace(require=lambda *_:None),'sqlite',sqlite3.sqlite_version,client)
    route={'database':str(path),'filesystem_root':str(tmp_path)}
    try:yield path,client,facade,route
    finally:client.close()


def apply(native, kind, family, values):
    path,client,facade,route=native
    draft=backend_draft(resolved_form('sqlite',family),values)
    request={'resource_kind':kind,'operation_id':'create','_provider_route':route,'draft':draft}
    validation=facade.validate(request);assert validation['valid'],str(validation)
    plan=facade.plan(request)
    result=facade.apply({'plan_id':plan['plan_id'],'plan_digest':plan['plan_digest'],'confirmed':True})
    assert result['provider_result']['accepted']
    return result


def test_form1_partial_expression_index_is_used_and_uniqueness_is_native(native):
    apply(native,'index','index',{'name':'partial_expr','table':'main.owned','unique':True,
        'terms':[{'kind':'expression','value':'lower(label)','collation':'NOCASE','order':'DESC'}],
        'predicate':'enabled=1'})
    with sqlite3.connect(native[0]) as c:
        sql=c.execute("SELECT sql FROM sqlite_schema WHERE name='partial_expr'").fetchone()[0]
        assert 'WHERE' in sql and 'lower(label)' in sql and 'DESC' in sql
        assert any('partial_expr' in row[3] for row in c.execute("EXPLAIN QUERY PLAN SELECT * FROM owned WHERE enabled=1 AND lower(label) COLLATE NOCASE='one'"))
        with pytest.raises(sqlite3.IntegrityError):c.execute("INSERT INTO owned VALUES(3,'OnE',1)")
        c.execute("INSERT INTO owned VALUES(4,'ONE',0)")


@pytest.mark.parametrize('value',["label)); DROP TABLE owned; --",'label,id','(label',"'unterminated"])
def test_form1_expression_boundary_refusal_does_not_mutate(native,value):
    with pytest.raises(RelationalClientError):
        native[1].plan_admin_operation({'resource_kind':'index','operation_id':'create','_provider_route':native[3],
            'draft':{'name':'bad','table':'main.owned','terms':[{'kind':'expression','value':value}]}})
    with sqlite3.connect(native[0])as c:assert c.execute('SELECT count(*) FROM owned').fetchone()[0]==2


def test_form2_spatial_auxiliary_columns_and_module_grid(native):
    apply(native,'virtual-table','table',{'variant':'virtual','name':'boxes','module':'rtree',
        'module_columns':[{'name':n,'unindexed':False} for n in ['id','xmin','xmax']],
        'auxiliary_columns':[{'value':'label'}]})
    with sqlite3.connect(native[0]) as c:
        c.execute("INSERT INTO boxes VALUES(1,2,4,'kept')")
        assert c.execute('SELECT label FROM boxes WHERE xmin<=3 AND xmax>=3').fetchall()==[('kept',)]


def test_form2_vocabulary_tokenizer_and_dbstat(native):
    with sqlite3.connect(native[0]) as c:
        c.executescript("CREATE VIRTUAL TABLE search USING fts5(body); INSERT INTO search VALUES('hello world'); CREATE VIRTUAL TABLE oldsearch USING fts4(body); INSERT INTO oldsearch VALUES('hello world')")
    for module,name,values in [
        ('fts5vocab','vocab',{'source_table':'search','source_database':'main','vocabulary_mode':'instance'}),
        ('fts4aux','aux',{'source_table':'oldsearch','source_database':'main'}),
        ('fts3tokenize','tokens',{'tokenizer_name':'simple'}),
        ('dbstat','stats',{'source_database':'main'})]:
        apply(native,'virtual-table','table',{'variant':'virtual','name':name,'module':module,**values})
    with sqlite3.connect(native[0]) as c:
        assert c.execute("SELECT term FROM vocab ORDER BY term").fetchall()==[('hello',),('world',)]
        assert c.execute("SELECT term FROM aux WHERE col='*' ORDER BY term").fetchall()==[('hello',),('world',)]
        assert c.execute("SELECT token FROM tokens WHERE input='HELLO world'").fetchall()==[('hello',),('world',)]
        assert c.execute("SELECT count(*) FROM stats WHERE name='owned'").fetchone()[0]>0


def test_form2_inapplicable_options_refused(native):
    with pytest.raises(RelationalClientError):
        native[1].plan_admin_operation({'resource_kind':'virtual-table','operation_id':'create','_provider_route':native[3],
            'draft':{'name':'bad','module':'geopoly','columns':[], 'auxiliary_columns':['ignored']}})


@pytest.mark.parametrize('module',['fts3','fts4','fts5'])
def test_form3_typed_tokenizer_and_prefix_match(native,module):
    values={'variant':'fts','name':'typed_search','module':module,
        'module_columns':[{'name':'body'}],'tokenizer_name':'unicode61',
        'tokenizer_arguments':[{'value':'remove_diacritics'},{'value':'2'}] if module=='fts5' else [{'value':'remove_diacritics=2'}]}
    if module!='fts3':values['prefix_lengths']=[{'value':2},{'value':3}]
    apply(native,'fts-table','table',values)
    with sqlite3.connect(native[0]) as c:
        c.execute("INSERT INTO typed_search VALUES('Héllo world')")
        assert c.execute("SELECT count(*) FROM typed_search WHERE typed_search MATCH 'hel*'").fetchone()==(1,)


@pytest.mark.parametrize('option,minimum',[('contentless_delete',(3,43,0)),('tokendata',(3,45,0)),('locale',(3,47,0)),('contentless_unindexed',(3,47,0))])
def test_form3_actual_runtime_gates_and_native_feature(native,option,minimum):
    values={'variant':'fts','name':'feature','module':'fts5','module_columns':[{'name':'body'},{'name':'tag','unindexed':True}],
        'fts_'+option:'1'}
    if option in {'contentless_delete','contentless_unindexed'}:values['content_mode']='CONTENTLESS'
    if sqlite3.sqlite_version_info < minimum:
        with pytest.raises((RelationalClientError,AssertionError,VisualAdminValidationError),match='requires SQLite'):
            apply(native,'fts-table','table',values)
        # Legacy native-option callers cannot bypass the same gate.
        with pytest.raises(RelationalClientError,match='requires SQLite'):
            native[1].plan_admin_operation({'resource_kind':'fts-table','operation_id':'create',
                '_provider_route':native[3],'draft':{'name':'legacy','module':'fts5','columns':['body'],'module_options':{option:1}}})
    else:
        apply(native,'fts-table','table',values)
        with sqlite3.connect(native[0]) as c:
            c.execute("INSERT INTO feature(rowid,body,tag) VALUES(1,'hello','kept')")
            assert c.execute("SELECT rowid FROM feature WHERE feature MATCH 'hello'").fetchall()==[(1,)]
            if option=='contentless_delete':
                c.execute('DELETE FROM feature WHERE rowid=1')
                assert c.execute("SELECT rowid FROM feature WHERE feature MATCH 'hello'").fetchall()==[]
            if option=='contentless_unindexed':assert c.execute('SELECT body,tag FROM feature').fetchone()==(None,'kept')
            if option=='locale':
                c.execute("INSERT INTO feature(rowid,body) VALUES(2,fts5_locale('en_US','world'))")
                assert c.execute('SELECT fts5_get_locale(feature,0) FROM feature WHERE rowid=2').fetchone()==('en_US',)


def test_form3_external_content_is_explicitly_populated(native):
    apply(native,'fts-table','table',{'variant':'fts','name':'external','module':'fts5',
        'module_columns':[{'name':'label'}],'content_mode':'EXTERNAL','content_table':'owned',
        'fts_content_rowid':'id','fts_detail':'column','fts_columnsize':'0'})
    with sqlite3.connect(native[0]) as c:
        assert c.execute("SELECT rowid FROM external WHERE external MATCH 'one'").fetchall()==[]
        c.execute("INSERT INTO external(external) VALUES('rebuild')")
        assert c.execute("SELECT rowid FROM external WHERE external MATCH 'one' ORDER BY rowid").fetchall()==[(1,),(2,)]


def test_form4_generated_collation_check_and_autoincrement(native):
    apply(native,'table','table',{'variant':'default','name':'deep','columns':[
        {'name':'id','type':'INTEGER','primary_key':True,'autoincrement':True},
        {'name':'label','type':'TEXT','collation':'NOCASE','unique':True,'check_expression':'length(label)>1'},
        {'name':'v','type':'TEXT','generated_storage':'VIRTUAL','generated_expression':'upper(label)'},
        {'name':'s','type':'INTEGER','generated_storage':'STORED','generated_expression':'length(label)'}]})
    with sqlite3.connect(native[0]) as c:
        c.execute("INSERT INTO deep(label) VALUES('Hello')")
        assert c.execute('SELECT * FROM deep').fetchone()==(1,'Hello','HELLO',5)
        assert [row[6] for row in c.execute('PRAGMA table_xinfo(deep)')]==[0,0,2,3]
        with pytest.raises(sqlite3.IntegrityError):c.execute("INSERT INTO deep(label) VALUES('hello')")
        with pytest.raises(sqlite3.IntegrityError):c.execute("INSERT INTO deep(label) VALUES('x')")
        c.execute('DELETE FROM deep')
        c.execute("INSERT INTO deep(label) VALUES('Again')")
        assert c.execute('SELECT id FROM deep').fetchone()==(2,)


@pytest.mark.parametrize('policy',['ABORT','FAIL','IGNORE','REPLACE','ROLLBACK'])
def test_form4_native_conflict_semantics(native,policy):
    apply(native,'table','table',{'variant':'default','name':'conflicts','columns':[
        {'name':'id','type':'INTEGER','primary_key':True},
        {'name':'label','type':'TEXT','unique':True,'unique_conflict':policy}]})
    with sqlite3.connect(native[0]) as c:
        c.execute("INSERT INTO conflicts VALUES(1,'old')");c.commit()
        c.execute("INSERT INTO conflicts VALUES(2,'pending')")
        if policy in {'IGNORE','REPLACE'}:c.execute("INSERT INTO conflicts VALUES(3,'old')")
        else:
            with pytest.raises(sqlite3.IntegrityError):c.execute("INSERT INTO conflicts VALUES(3,'old')")
        assert c.in_transaction == (policy!='ROLLBACK')
        rows=c.execute('SELECT id FROM conflicts ORDER BY id').fetchall()
        assert rows == ([(1,)] if policy=='ROLLBACK' else [(2,),(3,)] if policy=='REPLACE' else [(1,),(2,)])


@pytest.mark.parametrize('column',[{'autoincrement':True}, {'generated_storage':'STORED','generated_expression':'id+1','default':'1'}, {'unique_conflict':'IGNORE'}, {'generated_expression':'id+1'}, {'check_expression':'1); DROP TABLE owned; --'}])
def test_form4_invalid_column_controls_refused_before_mutation(native,column):
    with pytest.raises((RelationalClientError,AssertionError,VisualAdminValidationError)):
        apply(native,'table','table',{'variant':'default','name':'bad','columns':[{'name':'id','type':'INTEGER',**column}]})
    with sqlite3.connect(native[0]) as c:assert c.execute("SELECT count(*) FROM sqlite_schema WHERE name='bad'").fetchone()==(0,)


@pytest.mark.parametrize('view',[False,True])
def test_form6_native_when_on_table_or_view(native,view):
    with sqlite3.connect(native[0]) as c:c.executescript('CREATE TABLE log(value TEXT); CREATE VIEW exposed AS SELECT * FROM owned')
    values={'name':'guarded','timing':'INSTEAD OF' if view else 'AFTER','events':'INSERT',
        'view' if view else 'table':'main.exposed' if view else 'main.owned',
        'when':'NEW.enabled=1','body':"INSERT INTO log VALUES(NEW.label);"}
    apply(native,'trigger','trigger',values)
    with sqlite3.connect(native[0]) as c:
        target='exposed' if view else 'owned'
        c.execute(f"INSERT INTO {target} VALUES(3,'yes',1)")
        c.execute(f"INSERT INTO {target} VALUES(4,'no',0)")
        assert c.execute('SELECT value FROM log').fetchall()==[('yes',)]
        assert c.execute('SELECT count(*) FROM owned').fetchone()==((2 if view else 4),)


@pytest.mark.parametrize('timing,target',[('INSTEAD OF','main.owned'),('AFTER','main.exposed'),('AFTER','main.absent')])
def test_form6_native_target_timing_refusal_rolls_back(native,timing,target):
    with sqlite3.connect(native[0]) as c:c.execute('CREATE VIEW exposed AS SELECT * FROM owned')
    with pytest.raises((RelationalClientError,VisualAdminValidationError,VisualAdminExecutionError)):
        apply(native,'trigger','trigger',{'name':'bad','timing':timing,'events':'INSERT',
            'view' if timing=='INSTEAD OF' else 'table':target,'body':'SELECT 1;'})
    with sqlite3.connect(native[0]) as c:
        assert c.execute("SELECT count(*) FROM sqlite_schema WHERE name='bad'").fetchone()==(0,)
        assert c.execute('SELECT count(*) FROM owned').fetchone()==(2,)


def test_form6_when_escape_refused(native):
    with pytest.raises((RelationalClientError,VisualAdminValidationError,VisualAdminExecutionError)):
        apply(native,'trigger','trigger',{'name':'bad','timing':'AFTER','events':'INSERT','table':'main.owned',
            'when':'1) BEGIN SELECT 1; END; DROP TABLE owned; --','body':'SELECT 1;'})


def test_form3_fts4_native_options_and_unindexed_value(native):
    apply(native,'fts-table','table',{'variant':'fts','name':'old_options','module':'fts4',
        'module_columns':[{'name':'body'},{'name':'label'}],'fts_order':'desc','fts_matchinfo':'fts3',
        'fts_compress':'upper','fts_uncompress':'lower','fts_languageid':'lang',
        'notindexed_columns':[{'value':'label'}]})
    with sqlite3.connect(native[0]) as c:
        c.execute("INSERT INTO old_options(body,label,lang) VALUES('HELLO','SECRET',0)")
        assert c.execute("SELECT body,label FROM old_options WHERE old_options MATCH 'hello'").fetchall()==[('hello','secret')]
        assert c.execute("SELECT rowid FROM old_options WHERE old_options MATCH 'secret'").fetchall()==[]
        assert len(c.execute("SELECT matchinfo(old_options) FROM old_options WHERE old_options MATCH 'hello'").fetchone()[0])>0


def test_form4_primary_and_not_null_conflict_policies(native):
    apply(native,'table','table',{'variant':'default','name':'key_conflicts','columns':[
        {'name':'id','type':'INTEGER','primary_key':True,'primary_key_conflict':'REPLACE'},
        {'name':'label','type':'TEXT','nullable':False,'not_null_conflict':'IGNORE'}]})
    with sqlite3.connect(native[0]) as c:
        c.execute("INSERT INTO key_conflicts VALUES(1,'old')")
        c.execute("INSERT INTO key_conflicts VALUES(1,'new')")
        c.execute("INSERT INTO key_conflicts VALUES(2,NULL)")
        assert c.execute('SELECT * FROM key_conflicts').fetchall()==[(1,'new')]
