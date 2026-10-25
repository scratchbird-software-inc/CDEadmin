"""Native MySQL account tuples, forms and parser-qualified operation coverage."""
from copy import deepcopy
import pytest
from pgadmin.cdeadmin.providers import mysql_roles
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
TARGET={'resource_kind':'role','display_name':'ambiguous@role@%',
        'extensions':{'mysql':{'native':{'user':'ambiguous@role','host':'%'}}}}

@pytest.mark.parametrize('operation,options,expected',[
 ('grant',{'admin_option':True},'GRANT `ambiguous@role`@`%` TO `recipient@``\\`@`localhost` WITH ADMIN OPTION'),
 ('revoke',{},'REVOKE `ambiguous@role`@`%` FROM `recipient@``\\`@`localhost`'),
 ('set_default',{'mode':'SELECTED'},'SET DEFAULT ROLE `ambiguous@role`@`%` TO `recipient@``\\`@`localhost`'),
 ('set_default',{'mode':'ALL'},'SET DEFAULT ROLE ALL TO `recipient@``\\`@`localhost`'),
 ('set_default',{'mode':'NONE'},'SET DEFAULT ROLE NONE TO `recipient@``\\`@`localhost`')])
def test_exact_account_tuples_compile_through_native_operation_plans(operation,options,expected):
 request={'resource_kind':'role','operation_id':operation,'target_resource':deepcopy(TARGET),
   'draft':{'member_user':'recipient@`\\','member_host':'localhost',**options},'_provider_route':{'host':'trusted'}}
 assert not MYSQL_ADMINISTRATION.validate(request)['errors']
 assert MYSQL_ADMINISTRATION.plan(request)['command_preview']['statements'][0]['source']==expected


def test_missing_native_identity_and_unsupported_mariadb_admin_option_are_refused():
 for target,draft in [({'display_name':'role@%'},{'member_user':'user'}),
   (TARGET,{'member_user':'user','admin_option_only':True}),
   (TARGET,{'member_user':'user','member_host':'\x00'}),
   (TARGET,{'member_user':'user','mode':'UNSUPPORTED'})]:
  with pytest.raises(RelationalClientError):mysql_roles.compile_operation('set_default',draft,target)
 with pytest.raises(RelationalClientError):mysql_roles.compile_operation('grant',{'member_user':'user','admin_option':1},TARGET)


def test_engine_catalog_uses_separate_host_and_only_mysql_native_choices():
 catalog=MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
 role=next(row for row in catalog['objects'] if row['resource_kind']=='role')
 for operation in mysql_roles.OPERATIONS:
  item=next(row for row in role['operations'] if row['operation_id']==operation)
  from pgadmin.cdeadmin.providers.mysql_family.descriptor_contracts import role_contract
  fields={row['field_id']:row for row in role_contract(operation,[])['fields']}
  assert {'member_user','member_host'}<=set(fields)
  assert 'admin_option_only' not in fields
  assert item['confirmation_required'] and item['target_required']
  if operation=='set_default':assert {row['value'] for row in fields['mode']['options']}=={'SELECTED','ALL','NONE'}
 maria=MARIADB_ADMINISTRATION.catalog(catalog_for_engine('mariadb'))
 role=next(row for row in maria['objects'] if row['resource_kind']=='role')
 assert next(row for row in role['operations'] if row['operation_id']=='grant')['form']['form_id']=='mariadb.role.grant'


def test_default_roles_can_replace_the_native_full_selected_set():
    from pgadmin.cdeadmin.providers.mysql_roles import compile_operation
    selected={'native':{'user':'selected','host':'%'}}
    result=compile_operation('set_default',{'member_user':'u','member_host':'localhost','roles':[
        {'user':'first@literal','host':'%'},{'user':'second','host':'localhost'}]},selected)
    assert result['source']=='SET DEFAULT ROLE `first@literal`@`%`,`second`@`localhost` TO `u`@`localhost`'
