"""Engine-specific table properties preserve native syntax and exact values."""
import pytest
from pgadmin.cdeadmin.providers.mysql_family import mysql_table_options as native
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError


def test_native_server_options_bind_text_and_json_and_preserve_exact_unsigned_values():
    sql,parameters=native.compile_options({'engine':'FEDERATED','auto_increment':'18446744073709551615',
        'comment':"native % quote'雪",'engine_attribute':{'quoted':'雪'},'secondary_engine':None},'named_server/remote_table')
    assert sql==' ENGINE=%s AUTO_INCREMENT=18446744073709551615 COMMENT=%s ENGINE_ATTRIBUTE=%s SECONDARY_ENGINE=NULL CONNECTION=%s'
    assert parameters==('FEDERATED',"native % quote'雪",'{"quoted":"雪"}','named_server/remote_table')


@pytest.mark.parametrize('value',[{'auto_increment':9007199254740993},{'auto_increment':'18446744073709551616'},
    {'row_format':'DEFAULT; SHUTDOWN'},{'engine':'bad\0engine'},{'unrecognized_option':'native?'},
    {'union':['unsafe raw SQL']},{'engine_attribute':float('nan')}])
def test_unknown_or_unsafe_native_option_values_are_not_silently_ignored(value):
    with pytest.raises((RelationalClientError,ValueError)):native.compile_options(value)


def test_merge_members_are_native_identifier_paths_not_sql_fragments():
    sql,params=native.compile_options({'engine':'MRG_MYISAM','union':[['schema','odd`table'],['other']], 'insert_method':'LAST'})
    assert 'UNION=(`schema`.`odd``table`,`other`)' in sql and 'INSERT_METHOD=LAST' in sql
    assert params==('MRG_MYISAM',)


def test_mysql_table_creation_uses_native_options_without_changing_mariadb_or_default_mysql_sql():
    base={'resource_kind':'table','operation_id':'create','draft':{'name':'owned','schema':'db','columns':[{'name':'id','type':'INTEGER'}]}}
    ordinary=MYSQL_ADMINISTRATION._compile({**base,'draft':MYSQL_ADMINISTRATION._normalize_draft('table','create',base['draft'])})
    assert 'ENGINE=' not in ordinary['statements'][0]['source']
    draft={**base['draft'],'mysql_table_options':{'engine':'FEDERATED'},'mysql_connection':'named_server/remote'}
    result=MYSQL_ADMINISTRATION._compile({**base,'draft':MYSQL_ADMINISTRATION._normalize_draft('table','create',draft)})
    assert result['statements'][0]['source'].endswith(' ENGINE=%s CONNECTION=%s')
    assert result['statements'][0]['parameters']==('FEDERATED','named_server/remote')
    import json
    from pathlib import Path
    descriptor=Path(__file__).resolve().parents[2]/'web/pgadmin/cdeadmin/ui_descriptors/mysql/forms/table.form.json'
    field=next(row for row in json.loads(descriptor.read_text())['fields'] if row['field_id']=='mysql_connection')
    assert field['control']=='password'
    assert not any(row['field_id']=='mysql_table_options' for row in MARIADB_ADMINISTRATION._form('table','create')['fields'])


def test_native_property_sources_cannot_conflict_and_blank_secret_defaults_do_not_add_connection_options():
    with pytest.raises(RelationalClientError):native.selected({'mysql_table_options':{'engine':'InnoDB'},'engine':'FEDERATED'})
    draft=MYSQL_ADMINISTRATION._normalize_draft('table','create',{'name':'t','columns':[{'name':'id','type':'INT'}],'mysql_connection':''})
    assert 'mysql_connection' not in draft['options']


@pytest.mark.parametrize('enabled',[False,True])
@pytest.mark.parametrize('permanent',[False,True])
def test_recovery_and_permanent_startup_require_explicit_federated_remote_access(tmp_path,enabled,permanent):
    from pgadmin.cdeadmin.providers.mysql_family import mysql_recovery_worker as recovery
    request={'recovery_gtid_mode':'ON','memory_bytes':67108864,'recovery_federated':enabled}
    observed={'os_account':{'name':'native-user'},'configuration':{}}
    selected={'bind_address':'127.0.0.1','port':3355,'server_id':33} if permanent else None
    args,_=recovery.runtime_arguments(request,observed,tmp_path,tmp_path/'data',deployment=selected)
    assert ('--federated=ON' in args)==enabled
    assert ('--loose-federated=OFF' in args)==(not enabled)
