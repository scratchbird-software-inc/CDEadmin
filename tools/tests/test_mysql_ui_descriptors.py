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


def bind(draft,field,value):
    path=field.get('backend_field_id',field['field_id'])
    match=re.fullmatch(r'constraints\[kind=(.+)\]',path)
    if match:
        for row in value:
            names={c['field_id']:c.get('backend_field_id',c['field_id']) for c in field['columns']}
            draft.setdefault('constraints',[]).append({'kind':match[1],**{names[k]:v for k,v in row.items()}})
    elif '.' in path:
        parent,key=path.split('.');draft.setdefault(parent,{})[key]=value
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
