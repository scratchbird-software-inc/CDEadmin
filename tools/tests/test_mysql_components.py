"""Native component forms and bindings remain separate from plugin semantics."""
import pytest
from pgadmin.cdeadmin.providers.mysql_components import compile_operation
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def test_component_install_binds_urns_and_scoped_scalar_settings():
    result=compile_operation('create',{'urns':['file://component_validate_password'],
        'settings':[{'scope':'GLOBAL','name':'validate_password.length','value':10},
                    {'scope':'PERSIST','name':'validate_password.mixed_case_count','value':1}]},None)
    assert result=={'source':'INSTALL COMPONENT %s SET GLOBAL validate_password.length=%s,PERSIST validate_password.mixed_case_count=%s',
        'parameters':('file://component_validate_password',10,1)}
    assert compile_operation('drop',{'confirmation':'exact'},{'display_path':["file://component_'quoted"]})['parameters']==("file://component_'quoted",)


@pytest.mark.parametrize('draft',[
    {},{'urns':[]},{'urns':['same','same']},{'urns':['x\x00']},
    {'urns':['file://a'],'settings':[{'scope':'SESSION','name':'a','value':1}]},
    {'urns':['file://a'],'settings':[{'scope':'GLOBAL','name':'a; DROP','value':1}]},
    {'urns':['file://a'],'settings':[{'scope':'GLOBAL','name':'a','value':float('nan')}]},
    {'urns':['file://a'],'settings':[{'scope':'GLOBAL','name':'a','value':{'expression':'1'}}]},
    {'urns':['file://a'],'settings':[{'scope':'GLOBAL','name':'a','value':2**64}]},
])
def test_invalid_native_component_options_refuse_compile(draft):
    with pytest.raises(RelationalClientError):compile_operation('create',draft,None)


def test_mysql_component_catalog_has_compact_install_remove_forms_without_mariadb_inheritance():
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MARIADB_ADMINISTRATION,MYSQL_PROFILE,MARIADB_PROFILE
    from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
    catalog=MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    row=next(row for row in catalog['objects'] if row['resource_kind']=='component')
    assert {item['operation_id'] for item in row['operations']}=={'inspect','create','drop'}
    assert not MARIADB_ADMINISTRATION.supports('component','create')
    assert 'component' in MYSQL_PROFILE.resource_kinds and 'component' not in MARIADB_PROFILE.resource_kinds
    assert next(item for item in row['operations'] if item['operation_id']=='create')['form']['fields'][0]['field_id']=='urns'
    request={'resource_kind':'component','operation_id':'create','draft':{'urns':['file://component_validate_password']}}
    assert not MYSQL_ADMINISTRATION.validate(request)['errors']
    assert MYSQL_ADMINISTRATION._compile(request)['statements'][0]['source']=='INSTALL COMPONENT %s'
