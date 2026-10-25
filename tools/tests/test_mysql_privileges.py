"""Native privilege input boundaries and descriptor-backed admission."""
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from test_cdeadmin_visual_admin import context, Permissions
from test_mysql_accounts import AccountAdapter
from pgadmin.cdeadmin.providers.mysql_family import mysql_privileges as privileges
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration
from pgadmin.cdeadmin.sdk import RelationalClientError

BASE={'grantees':[{'user':"u'`\\@雪",'host':'localhost'}],'object_type':'TABLE',
      'database':'db.dot','object':'t`dot','privileges':[{'name':'SELECT','columns':['id`literal']}]}


def test_literal_account_object_and_column_names_never_become_sql_fragments():
    result=privileges.compile_operation('grant',{**BASE,'grant_option':True})
    assert result['statements'][0]['source']=="GRANT SELECT (`id``literal`) ON `db.dot`.`t``dot` TO `u'``\\@雪`@`localhost` WITH GRANT OPTION"
    assert result['statements'][0]['parameters']==()
    assert privileges.compile_operation('grant',{'principal':'old@%','object_type':'DATABASE','object_name':'db','privileges':['SELECT']})['statements'][0]['source']=='GRANT SELECT ON `db`.* TO `old`@`%`'


@pytest.mark.parametrize('change',[
    {'grantees':[]},{'grantees':[{'user':'u','host':'%','invented':True}]},
    {'privileges':[{'name':'SELECT; DROP USER root'}]},
    {'privileges':[{'name':'SELECT','expression':'ignored'}]},
    {'privileges':[{'name':'SELECT','columns':'id'}]},
    {'object_type':'DATABASE','object':None}, {'grant_option':'yes'},
    {'if_exists':True},{'ignore_unknown_user':True},{'grant_as_roles_mode':'ALL'},
    {'grant_as_user':'root','grant_as_roles_mode':'SELECTED','grant_as_roles':[]},
    {'grant_as_user':'root'}, {'proxy_user':'ignored'}, {'principal':'ambiguous@name@host'},
])
def test_invalid_and_silently_ignored_inputs_are_refused(change):
    with pytest.raises(RelationalClientError):privileges.compile_operation('grant',{**BASE,**change})


def test_native_proxy_grant_as_and_revoke_variants_have_explicit_inputs():
    recipients={'grantees':[{'user':'u','host':'%'}]}
    assert privileges.compile_operation('grant',{**recipients,'object_type':'PROXY','proxy_user':'mapped','proxy_host':'localhost','grant_option':True})['statements'][0]['source']=='GRANT PROXY ON `mapped`@`localhost` TO `u`@`%` WITH GRANT OPTION'
    assert privileges.compile_operation('revoke',{**recipients,'object_type':'ACCOUNT','if_exists':True,'ignore_unknown_user':True})['statements'][0]['source']=='REVOKE IF EXISTS ALL PRIVILEGES, GRANT OPTION FROM `u`@`%` IGNORE UNKNOWN USER'
    result=privileges.compile_operation('grant',{**recipients,'object_type':'GLOBAL','privileges':[{'name':'BACKUP_ADMIN'}],
        'grant_as_user':'owner','grant_as_host':'localhost','grant_as_roles_mode':'ALL_EXCEPT','grant_as_roles':[{'user':'excluded','host':'%'}]})
    assert result['statements'][0]['source']=='GRANT BACKUP_ADMIN ON *.* TO `u`@`%` AS `owner`@`localhost` WITH ROLE ALL EXCEPT `excluded`@`%`'


def test_typed_privileges_are_admitted_without_raw_json_or_a_renderer_branch():
    provider=ProviderVisualAdministration(context(),Permissions(),'mysql','9.7.0',AccountAdapter(MYSQL_ADMINISTRATION))
    result=provider.validate({'resource_kind':'privilege','operation_id':'grant','draft':BASE})
    assert result['valid'],result['errors']
    result=provider.plan({'resource_kind':'privilege','operation_id':'grant','draft':BASE,'_provider_route':{'host':'owned','user':'root'}})
    assert 'SELECT (`id``literal`)' in result['command_preview']['statements'][0]['source']
