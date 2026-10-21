"""Group operations bind native arguments and do not use async channel commands."""
import pytest
from pgadmin.cdeadmin.providers.mysql_group_replication import compile_operation
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
TARGET={'native':{'group_replication_plugin_status':'ACTIVE'}}
UUID='12345678-1234-1234-1234-123456789abc'


def test_native_group_functions_and_start_credentials_are_bound():
    result=compile_operation('start',{'user':'recovery','password':"a'\\b",'default_auth':'caching_sha2_password'},TARGET)
    assert result['source']=='START GROUP_REPLICATION USER=%s,PASSWORD=%s,DEFAULT_AUTH=%s'
    assert result['parameters']==('recovery',"a'\\b",'caching_sha2_password')
    assert "a'\\b" not in result['preview_source'] and 'bootstrap' not in result['source']
    result=compile_operation('set_primary',{'member_uuid':UUID,'timeout':120},TARGET)
    assert result['source']=='SELECT group_replication_set_as_primary(%s,%s)' and result['parameters']==(UUID,120)
    assert compile_operation('single_primary',{},TARGET)['source']=='SELECT group_replication_switch_to_single_primary_mode()'
    assert compile_operation('stop',{},TARGET)['source']=='STOP GROUP_REPLICATION'


def test_recovery_accounts_preserve_native_character_limits_and_password_carriage_returns():
    user='雪'*32
    password='native\rquote"slash\\雪'
    result=compile_operation('start',{'user':user,'password':password},TARGET)
    assert result['parameters']==(user,password) and len(user.encode('utf8'))==96
    assert password not in result['preview_source']
    for value in ('a'*33,'雪'*33,'native\nuser','native\x00user'):
        with pytest.raises(RelationalClientError):compile_operation('start',{'user':value},TARGET)
    with pytest.raises(RelationalClientError):compile_operation('start',{'password':'native\npassword'},TARGET)


@pytest.mark.parametrize('operation,draft',[
    ('set_primary',{'member_uuid':'wrong'}),('set_primary',{'member_uuid':UUID,'timeout':True}),
    ('set_primary',{'member_uuid':UUID,'timeout':3601}),('set_protocol',{'version':'9.7.0; DROP'}),
    ('set_write_concurrency',{'concurrency':0}),('set_write_concurrency',{'concurrency':2**32}),
    ('enable_member_action',{'action_name':'x','event_name':''}),('start',{'bootstrap':True}),
    ('start',{'password':'x'*33}),('stop',{'delete_connection':True}),
])
def test_invalid_or_unrelated_group_options_are_refused(operation,draft):
    with pytest.raises(RelationalClientError):compile_operation(operation,draft,TARGET)


def test_absent_plugin_and_mariadb_cannot_inherit_group_operations():
    with pytest.raises(RelationalClientError):compile_operation('start',{},None)
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MARIADB_ADMINISTRATION,MYSQL_PROFILE,MARIADB_PROFILE
    from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
    catalog=MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    row=next(row for row in catalog['objects'] if row['resource_kind']=='group-replication')
    assert len(row['operations'])==11
    assert 'group-replication' in MYSQL_PROFILE.resource_kinds and 'group-replication' not in MARIADB_PROFILE.resource_kinds
    assert not MARIADB_ADMINISTRATION.supports('group-replication','start')
    for item in row['operations']:
        if item['operation_id']!='inspect':assert item['target_required'] and item['confirmation_required']
