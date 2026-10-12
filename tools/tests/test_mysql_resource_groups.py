"""Native MySQL resource-group forms and bounded exact-thread operations."""
import pytest
from pgadmin.cdeadmin.providers import mysql_resource_groups as groups
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from pgadmin.cdeadmin.sdk.relational import RelationalClientError

TARGET={'resource_kind':'resource-group','display_name':'work`group'}


@pytest.mark.parametrize('operation,draft,source',[
    ('create',{'name':'work`group','resource_type':'USER','vcpu':'0 - 3, 5','priority':0,'enabled':True},'CREATE RESOURCE GROUP `work``group` TYPE=USER VCPU=0-3,5 THREAD_PRIORITY=0 ENABLE'),
    ('alter',{'state':'DISABLE','force':True},'ALTER RESOURCE GROUP `work``group` DISABLE FORCE'),
    ('assign',{'thread_ids':[1,str(2**64-1)]},'SET RESOURCE GROUP `work``group` FOR 1,18446744073709551615'),
    ('drop',{'force':True},'DROP RESOURCE GROUP `work``group` FORCE')])
def test_native_group_operation_plans(operation,draft,source):
    request={'resource_kind':'resource-group','operation_id':operation,'target_resource':TARGET,'draft':draft,'_provider_route':{'host':'trusted'}}
    assert not MYSQL_ADMINISTRATION.validate(request)['errors']
    assert MYSQL_ADMINISTRATION.plan(request)['command_preview']['statements'][0]['source']==source


@pytest.mark.parametrize('operation,draft',[
    ('assign',{'thread_ids':[True]}),('assign',{'thread_ids':[2**53]}),('assign',{'thread_ids':['1',1]}),('assign',{'thread_ids':[1,1]}),('assign',{'thread_ids':[]}),
    ('alter',{'vcpu':'0; DROP RESOURCE GROUP x'}),('alter',{'vcpu':'3-1'}),('alter',{'priority':False}),
    ('alter',{'state':'ENABLE','force':True}),('alter',{}),('create',{'name':'a','enabled':1})])
def test_invalid_and_ambiguous_native_options_are_refused(operation,draft):
    with pytest.raises(RelationalClientError):groups.compile_operation(operation,draft,TARGET)


def test_forms_expose_full_group_settings_without_mariadb_inheritance():
    catalog=MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    resource=next(row for row in catalog['objects'] if row['resource_kind']=='resource-group')
    operations={row['operation_id']:row for row in resource['operations']}
    assert groups.OPERATIONS<=operations.keys()
    assert {field['field_id'] for field in operations['create']['form']['fields']}=={'name','resource_type','vcpu','priority','enabled'}
    assert operations['assign']['confirmation_required'] and operations['assign']['target_required']
    assert not MARIADB_ADMINISTRATION.supports('resource-group','assign')
    with pytest.raises(RelationalClientError):groups.compile_operation('drop',{}, {'display_name':'USR_default'})
