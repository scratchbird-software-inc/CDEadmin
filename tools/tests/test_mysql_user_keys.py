"""User-key operations have typed descriptors and exact native dispatch."""
import json
from pathlib import Path

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family import mysql_user_keys as keys
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin import catalog_for_engine

TARGET={'resource_kind':'server','resource_id':'server:MySQL','display_path':['MySQL'],'display_name':'MySQL',
    'native':{'server_uuid':'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'}}


def test_all_key_operations_have_descriptor_fields_matching_the_real_backend_contract():
    root=Path(__file__).resolve().parents[2]/'web/pgadmin/cdeadmin/ui_descriptors/mysql'
    operations=[op for op in json.loads((root/'operations.json').read_text())['operations']
        if op['resource_kind']=='server' and op['operation_id'] in keys.OPERATIONS]
    actual=next(row for row in MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))['objects'] if row['resource_kind']=='server')
    declared={row['operation_id']:row for row in actual['operations'] if row['operation_id'] in keys.OPERATIONS}
    assert set(declared)==keys.OPERATIONS
    for op in operations:
        name=op['operation_id'];assert op['menu']['category']=='security' and op['tier']==2
        assert declared[name]['form']['fields']==op['fields']
        assert all(field['control']!='json' for field in op['fields'])
        draft={field['field_id']:field.get('default','owned-key') for field in op['fields']}
        draft.update(confirmation='MySQL')
        if name=='install_user_key_functions':draft['trusted_library']=True
        if name=='store_user_key':draft['password']="private ' 雪"
        result=keys.compile_operation(name,draft,TARGET)
        assert result['mysql_user_keys']['operation']==name
        assert all('private' not in row['source'] for row in result['statements'])


@pytest.mark.parametrize('value',[None,'','bad\0key'])
def test_invalid_key_identity_never_reaches_native_dispatch(value):
    with pytest.raises(RelationalClientError):keys.compile_operation('inspect_user_key',{'confirmation':'MySQL','key_id':value},TARGET)


@pytest.mark.parametrize('value',[True,0,16385,'1; SHUTDOWN'])
def test_key_generation_rejects_non_native_length_values(value):
    with pytest.raises(RelationalClientError):keys.compile_operation('generate_user_key',{'confirmation':'MySQL','key_id':'key','key_type':'AES','key_length':value},TARGET)


def test_native_store_text_rejects_truncating_nul_and_preserves_bound_secret_and_literal_identifier():
    draft={'confirmation':'MySQL','key_id':"key ' 雪",'key_type':'SECRET','password':"private quote'\\雪"}
    statement=keys.compile_operation('store_user_key',draft,TARGET)['statements'][0]
    assert statement=={'source':'SELECT keyring_key_store(%s,%s,%s)','parameters':(draft['key_id'],'SECRET',draft['password'])}
    with pytest.raises(RelationalClientError):keys.compile_operation('store_user_key',{**draft,'password':'prefix\0truncated'},TARGET)


def test_existing_functions_are_preserved_and_foreign_native_definitions_cannot_be_replaced():
    compiled=keys.compile_operation('install_user_key_functions',{'confirmation':'MySQL','library':'keyring_udf.so','trusted_library':True},TARGET)
    matching={'plugin':[['ACTIVE','keyring_udf.so']],'functions':[[name,result,'keyring_udf.so','function'] for name,result in keys.FUNCTIONS.items()]}
    assert keys.effective(compiled,matching)==[]
    assert len(keys.effective(compiled,{'plugin':[],'functions':[]}))==7
    matching['functions'][0][2]='another_library.so'
    with pytest.raises(RelationalClientError):keys.effective(compiled,matching)
    assert keys.public({'key_type':'AES','key_length':32,'private_fingerprint':'do not publish'})=={'key_type':'AES','key_length':32}
