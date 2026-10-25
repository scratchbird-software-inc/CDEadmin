"""Native MySQL account policy clauses and secret-bound plugin authentication."""
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from test_cdeadmin_visual_admin import context, Permissions
from test_visual_admin_field_contracts import IndexAdapter
from pgadmin.cdeadmin.providers.mysql_family import mysql_accounts as accounts
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MySQLDBAPIClient
from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration
from pgadmin.cdeadmin.sdk import RelationalClientError

TARGET={'display_name':'user@literal@host','native':{'user':'user@literal','host':'host'}}
BASE={'name':'user@literal','host':'host','password':"private quote' 雪",'plugin':'caching_sha2_password'}


def test_plugin_choice_and_secret_are_native_inputs_not_ignored_labels():
    result=accounts.compile_operation('create',BASE)
    sql=result['statements'][0]
    assert sql['source']=='CREATE USER `user@literal`@`host` IDENTIFIED WITH `caching_sha2_password` BY %s'
    assert sql['parameters']==(BASE['password'],)
    assert BASE['password'] not in sql['source'] and BASE['password'] not in sql['parser_source']
    assert sql['parser_source'].endswith(" BY ''")
    assert accounts.compile_operation('create',{'name':'','anonymous':True,'host':'localhost','authentication_mode':'NONE'})['statements'][0]['source']=="CREATE USER ''@`localhost`"


def test_native_account_and_password_policies_are_typed_and_bound():
    result=accounts.compile_operation('alter',{'authentication_mode':'AUTHENTICATION_STRING','plugin':'caching_sha2_password',
        'authentication_string':'native hash','retain_current_password':True,'account_lock':'LOCK',
        'tls_mode':'SPECIFIED','tls_cipher':'native-cipher','tls_issuer':'native issuer','tls_subject':'native subject',
        'max_queries_per_hour':4294967295,'max_updates_per_hour':0,'max_connections_per_hour':7,'max_user_connections':3,
        'password_expire':'INTERVAL','password_expire_days':65535,'password_history':'DEFAULT','password_reuse_days':12,
        'password_require_current':'OPTIONAL','failed_login_attempts':32767,'password_lock_time':'UNBOUNDED','comment':'owned comment'},TARGET)
    statement=result['statements'][0]
    assert 'IDENTIFIED WITH `caching_sha2_password` AS %s RETAIN CURRENT PASSWORD REQUIRE CIPHER %s AND ISSUER %s AND SUBJECT %s' in statement['source']
    assert 'MAX_QUERIES_PER_HOUR 4294967295 MAX_UPDATES_PER_HOUR 0' in statement['source']
    assert 'PASSWORD EXPIRE INTERVAL 65535 DAY PASSWORD HISTORY DEFAULT PASSWORD REUSE INTERVAL 12 DAY PASSWORD REQUIRE CURRENT OPTIONAL' in statement['source']
    assert statement['parameters']==('native hash','native-cipher','native issuer','native subject','owned comment')


@pytest.mark.parametrize('change',[
    {'plugin':{}}, {'authentication_mode':{}}, {'authentication_mode':'RANDOM_PASSWORD'},
    {'authentication_mode':'NONE','plugin':'ignored?'}, {'if_exists':True}, {'administrator':True},
    {'password':None}, {'tls_mode':[]}, {'tls_cipher':'ignored?'}, {'tls_mode':'SPECIFIED'},
    {'password_expire':'INTERVAL','password_expire_days':0}, {'password_expire_days':3},
    {'failed_login_attempts':32768}, {'password_lock_time':'-1'}, {'password_history':True},
    {'max_queries_per_hour':4294967296}, {'attributes':[]}, {'attributes':{'bad':float('nan')}},
    {'attributes':{},'comment':'conflict'}, {'retain_current_password':True}, {'discard_old_password':True},
    {'active':'LOCK'}, {'anonymous':True}, {'invented':True},
])
def test_invalid_ignored_or_protected_result_inputs_are_refused(change):
    with pytest.raises(RelationalClientError):accounts.compile_operation('create',{**BASE,**change})


def test_alter_preserves_every_omitted_policy_and_accepts_legacy_changes():
    result=accounts.compile_operation('alter',{'changes':{'password':'new private'}},TARGET)
    assert result['statements'][0]['source']=='ALTER USER `user@literal`@`host` IDENTIFIED BY %s'
    assert accounts.compile_operation('alter',{'comment':'changed'},TARGET)['statements'][0]['source']=='ALTER USER `user@literal`@`host` COMMENT %s'
    with pytest.raises(RelationalClientError):accounts.compile_operation('alter',{'account_lock':'UNCHANGED'},TARGET)
    with pytest.raises(RelationalClientError):accounts.compile_operation('alter',{'comment':'changed'},{'display_name':'ambiguous@user@host'})


class AccountAdapter(IndexAdapter):
    admin_operation_field_contract=MySQLDBAPIClient.admin_operation_field_contract


def test_descriptor_fields_reach_the_native_compiler_and_secret_redaction():
    provider=ProviderVisualAdministration(context(),Permissions(),'mysql','9.7.0',AccountAdapter(MYSQL_ADMINISTRATION))
    request={'resource_kind':'user','operation_id':'create','draft':BASE,'_provider_route':{'host':'owned','user':'root'}}
    value=provider.validate(request);assert value['valid'],value['errors']
    assert value['draft']['password']=='<redacted>'
    planned=provider.plan(request);assert planned['draft']['password']=='<redacted>'
    assert BASE['password'] not in str(planned)
    request={'resource_kind':'user','operation_id':'alter','draft':{'comment':'changed','confirmation':TARGET['display_name']},'target_resource':TARGET,'_provider_route':{'host':'owned','user':'root'}}
    planned=provider.plan(request)
    assert planned['command_preview']['statements'][0]['source']=='ALTER USER `user@literal`@`host` COMMENT %s'


def test_native_factor_lifecycle_keeps_credentials_out_of_public_drafts():
    provider=ProviderVisualAdministration(context(),Permissions(),'mysql','9.7.0',AccountAdapter(MYSQL_ADMINISTRATION))
    request={'resource_kind':'user','operation_id':'create','draft':{**BASE,'authentication_factors':[
        {'mode':'AUTHENTICATION_STRING','plugin':'auth_socket','authentication_string':'private-factor-canary'}]},
        '_provider_route':{'host':'owned','user':'root'}}
    result=provider.validate(request);assert result['valid'],result['errors']
    assert result['draft']['authentication_factors']=='<redacted>'
    planned=provider.plan(request);assert 'private-factor-canary' not in str(planned)
    assert ' AND IDENTIFIED WITH `auth_socket` AS %s' in planned['command_preview']['statements'][0]['source']
    for action in ('ADD','MODIFY','DROP'):
        row={'action':action,'factor':2}
        if action!='DROP':row.update(mode='AUTHENTICATION_STRING',plugin='auth_socket',authentication_string='native-map')
        result=accounts.compile_operation('alter',{'factor_actions':[row]},TARGET)
        assert ' '+action+' 2 FACTOR' in result['statements'][0]['source']
        assert 'native-map' not in result['statements'][0]['source']


def test_native_role_create_keeps_exact_hosts_and_separate_grant_steps():
    result=accounts.compile_role({'name':'role@literal','host':'host',
        'if_not_exists':True,'members':[{'user':'member@literal','host':'localhost'}]})
    assert [row['source'] for row in result['statements']]==[
        'CREATE ROLE IF NOT EXISTS `role@literal`@`host`',
        'GRANT `role@literal`@`host` TO `member@literal`@`localhost`']
    assert accounts.compile_operation('create_role',{'name':'r','members':[]})['statements'][0]['source']=='CREATE ROLE `r`@`%`'


@pytest.mark.parametrize('actions',[
    [{'action':'ADD','factor':True,'plugin':'auth_socket'}],
    [{'action':'ADD','factor':4,'plugin':'auth_socket'}],
    [{'action':'DROP','factor':2,'plugin':'ignored'}],
    [{'action':'ADD','factor':3,'plugin':'auth_socket'},{'action':'ADD','factor':2,'plugin':'auth_socket'}],
    [{'action':'DROP','factor':2},{'action':'DROP','factor':2}],
    [{'action':'MODIFY','factor':2,'plugin':'auth_socket'},{'action':'DROP','factor':3}],
])
def test_native_factor_grammar_limits_are_not_guessed_or_ignored(actions):
    with pytest.raises(RelationalClientError):accounts.compile_operation('alter',{'factor_actions':actions},TARGET)


def test_drop_and_rename_bind_native_identity_without_reparsing_display_labels():
    target={'display_name':'display only','native':{'user':"user'`\\@雪",'host':"host'`\\"}}
    selected=accounts.account(target['native']['user'],target['native']['host'])
    for operation,keyword in [('drop_user','USER'),('drop_role','ROLE')]:
        assert accounts.compile_operation(operation,{'confirmation':'display only'},target)['statements'][0]['source']=='DROP '+keyword+' '+selected
    changed=accounts.compile_operation('rename_user',{'new_name':"renamed'`\\@雪",'new_host':'localhost'},target)
    assert changed['statements'][0]['source']=='RENAME USER '+selected+' TO '+accounts.account("renamed'`\\@雪",'localhost')
    assert changed['mysql_account_change']['new_user']=="renamed'`\\@雪"
