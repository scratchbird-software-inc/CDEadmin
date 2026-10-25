"""MySQL UI bindings must reach the real native plan compiler."""
import json
from pathlib import Path
import re

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MYSQL_PROFILE
from pgadmin.cdeadmin.providers.mysql_family import mysql_table_options
from pgadmin.cdeadmin.visual_admin import catalog_for_engine

FOLDER=Path(__file__).resolve().parents[2]/'web/pgadmin/cdeadmin/ui_descriptors/mysql'


def load(name):return json.loads((FOLDER/name).read_text())


def test_capabilities_match_current_admin_catalog_including_read_only_and_post_beta_scope():
    actual=MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    expected={row['resource_kind']:{op['operation_id'] for op in row['operations']} for row in actual['objects']}
    for kind in MYSQL_PROFILE.resource_kinds:expected.setdefault(kind,set())
    declared={row['resource_kind']:{op['operation_id'] for op in row['operations']} for row in load('capabilities.json')['kinds']}
    assert declared==expected
    column=next(row for row in load('capabilities.json')['kinds'] if row['resource_kind']=='column')
    assert all(op['support_state']=='post_beta_closed_source' for op in column['operations'] if 'masking_policy' in op['operation_id'])


def test_every_stored_routine_field_binding_reaches_its_native_create_or_alter_path():
    for kind, filename in [('procedure','routine'),('function','routine-function')]:
        form=load('forms/'+filename+'.form.json')
        for mode in ('create','alter'):
            base=({'name':'owned','database':'db','body':'BEGIN SELECT 1; END' if kind=='procedure' else 'RETURN 1',
                   'definer_user':'owner','definer_host':'localhost',**({'returns':'INT'} if kind=='function' else {})}
                  if mode=='create' else {})
            target={'display_path':['db','owned'],'display_name':'owned'}
            def compiled(draft):
                request={'resource_kind':kind,'operation_id':mode,'draft':draft,'target_resource':target}
                assert not MYSQL_ADMINISTRATION.validate(request)['errors']
                return MYSQL_ADMINISTRATION._compile(request)['statements']
            samples={'name':'changed','parent':'changed_db','body':'BEGIN SELECT 2; END' if kind=='procedure' else 'RETURN 2',
                'comment':'changed','returns':'BIGINT','if_not_exists':True,'parameters':[{'name':'arg','type':'INT','mode':'IN'}],
                'security_create':'INVOKER','security_alter':'INVOKER','data_access_create':'NO SQL','data_access_alter':'NO SQL',
                'deterministic':True,'language':'SQL','definer_user':'changed_owner','definer_host':'changed_host'}
            for field in form['fields']:
                if mode not in field.get('modes',['create','alter']) or field['field_id']=='confirmation':continue
                draft=json.loads(json.dumps(base))
                if field['field_id']=='parent':draft.pop('database')
                bind(draft,field,samples[field['field_id']])
                actual=compiled(draft)
                if mode=='create':assert actual!=compiled(base),field['field_id']
                else:assert actual[0]['source'].startswith('ALTER '+kind.upper()),field['field_id']


def bind(draft,field,value):
    path=field.get('backend_field_id',field['field_id'])
    match=re.fullmatch(r'constraints\[kind=(.+)\]',path)
    if match:
        for row in value:
            names={c['field_id']:c.get('backend_field_id',c['field_id']) for c in field['columns']}
            draft.setdefault('constraints',[]).append({'kind':match[1],**{names[k]:v for k,v in row.items()}})
    elif '.' in path:
        parent,key=path.split('.');draft.setdefault(parent,{})[key]=value
    elif field['control']=='grid':
        names={c['field_id']:c.get('backend_field_id',c['field_id']) for c in field['columns']}
        draft[path]=[{names[key]:item for key,item in row.items()} for row in value]
    else:draft[path]=value


def test_every_table_binding_changes_the_real_provider_plan_and_uses_accepted_native_values():
    form=load('forms/table.form.json')
    samples={'name':'changed_table','parent':['changed_database'],'columns':[{'name':'changed_column','type':'BIGINT'}],
        'primary_key':[{'name':'pk','columns':['id']}], 'unique_constraints':[{'name':'uq','columns':['id']}],
        'foreign_keys':[{'name':'fk','columns':['id'],'references':['db','parent'],'referenced_columns':['id']}],
        'check_constraints':[{'name':'ck','expression':'id>0'}], 'engine':'InnoDB','character_set':'utf8mb4',
        'collation':'utf8mb4_bin','tablespace':'owned_space','row_format':'DYNAMIC','auto_increment':'9007199254740993',
        'compression':'ZLIB','encryption':'Y','secondary_engine':'owned_secondary',
        'engine_attribute':{'attribute':'literal'},'secondary_engine_attribute':{'attribute':'literal'},
        'comment':"quoted' 雪",'data_directory':'/owned/data','index_directory':'/owned/index','mysql_connection':'owned_server/remote'}
    base={'name':'owned','columns':[{'name':'id','type':'INT'}]}
    def planned(draft):
        request={'resource_kind':'table','operation_id':'create','draft':draft,'_provider_route':{'host':'owned','port':3306,'user':'operator'}}
        assert not MYSQL_ADMINISTRATION.validate(request)['errors']
        return MYSQL_ADMINISTRATION.plan(request)['provider_payload']['compiled']['statements']
    original=planned(base)
    for field in form['fields']:
        assert field['modes']==['create']
        name=field['field_id'];value=samples.get(name)
        if name not in samples:value=(field.get('options') or [{'value':'1'}])[0]['value']
        draft=json.loads(json.dumps(base));bind(draft,field,value)
        assert planned(draft)!=original,name
        path=field.get('backend_field_id',name)
        if path.startswith('mysql_table_options.'):
            assert path.split('.')[1] in mysql_table_options.KEYS
            if path.split('.')[1] in mysql_table_options.NUMBERS:assert isinstance(value,str),name
    columns=next(f for f in form['fields'] if f['field_id']=='columns')
    assert {c['field_id'] for c in columns['columns']}=={'name','type','nullable','default','unique','primary_key'}
    assert not form['omitted_tabs']  # Missing native controls are gaps, never absent engine concepts.
    assert form['status']=='draft' and form['gaps']


def test_table_constraint_discriminators_and_foreign_identity_names_match_backend_contract():
    fields={f['field_id']:f for f in load('forms/table.form.json')['fields']}
    assert fields['primary_key']['backend_field_id']=='constraints[kind=PRIMARY KEY]'
    assert fields['unique_constraints']['backend_field_id']=='constraints[kind=UNIQUE]'
    assert fields['foreign_keys']['backend_field_id']=='constraints[kind=FOREIGN KEY]'
    assert fields['check_constraints']['backend_field_id']=='constraints[kind=CHECK]'
    children={c['field_id']:c for c in fields['foreign_keys']['columns']}
    assert children['references']['backend_field_id']=='references_table'
    assert children['referenced_columns']['backend_field_id']=='references_columns'


def test_every_view_binding_reaches_the_real_create_and_alter_compiler():
    form=load('forms/view.form.json')
    samples={'name':'changed_view','parent':'changed_database','query':'SELECT 2 AS changed',
        'algorithm':'MERGE','check_option':'LOCAL','sql_security':'INVOKER',
        'definer_user':'changed_user','definer_host':'changed_host'}
    target={'display_path':['db','owned'],'display_name':'owned'}
    for mode in ('create','alter'):
        base={'definition':'SELECT 1 AS id','definer_user':'owner','definer_host':'localhost'}
        if mode=='create':base.update(name='owned',database='db')
        def compiled(draft):
            request={'resource_kind':'view','operation_id':mode,'draft':draft,'target_resource':target}
            assert not MYSQL_ADMINISTRATION.validate(request)['errors']
            return MYSQL_ADMINISTRATION._compile(request)['statements']
        original=compiled(base)
        for field in form['fields']:
            if mode not in field.get('modes',['create','alter']):continue
            draft=dict(base);bind(draft,field,samples[field['field_id']])
            assert compiled(draft)!=original,(mode,field['field_id'])
    assert form['status']=='draft'
    assert any(row['concept']=='Ordered output aliases' for row in form['gaps'])
    assert any(row['tab']=='Triggers' for row in form['omitted_tabs'])


def test_every_index_binding_reaches_its_native_create_or_rename_path():
    form=load('forms/index.form.json')
    samples={'name':'changed_index','table':['db','changed_table'],'index_kind':'FULLTEXT','unique':True,
        'columns':[{'column':'other','direction':'DESC','prefix_length':4}], 'comment':"quote' 雪",'method':'HASH',
        'visible':False,'algorithm':'INPLACE','lock':'NONE','key_block_size':'8','parser':'ngram',
        'engine_attribute':{'native':True},'secondary_engine_attribute':{'native':True}}
    base={'name':'owned','table':['db','t'],'columns':['word']}
    def compiled(draft):
        request={'resource_kind':'index','operation_id':'create','draft':draft}
        assert not MYSQL_ADMINISTRATION.validate(request)['errors']
        return MYSQL_ADMINISTRATION._compile(request)['statements']
    for field in form['fields']:
        if field['field_id']=='new_name':
            request={'resource_kind':'index','operation_id':'rename','draft':{'new_name':'changed'},
                'target_resource':{'display_name':'owned','display_path':['db','t','owned']}}
            assert 'TO `changed`' in MYSQL_ADMINISTRATION._compile(request)['statements'][0]['source']
            continue
        draft=dict(base)
        if field['field_id']=='parser':draft['index_kind']='FULLTEXT'
        original=compiled(draft)
        bind(draft,field,samples[field['field_id']])
        assert compiled(draft)!=original,field['field_id']
    assert form['status']=='draft' and not form['omitted_tabs']
    visibility=next(op for op in load('operations.json')['operations'] if op['resource_kind']=='index' and op['operation_id']=='visibility')
    assert visibility['menu']['category']=='maintenance'
