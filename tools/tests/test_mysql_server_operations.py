"""Native MySQL configuration scopes and exact process-control identities."""
import pytest
from pgadmin.cdeadmin.providers import mysql_server_operations as operations
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('operation,scope',[('set_global','GLOBAL'),('set_persist','PERSIST'),('set_persist_only','PERSIST_ONLY')])
def test_bound_variable_values_are_not_in_command_previews(operation,scope):
    request={'resource_kind':'system-variable','operation_id':operation,'target_resource':{'display_name':'max_execution_time'},'draft':{'value':'exact-value'},'_provider_route':{'host':'trusted'}}
    assert not MYSQL_ADMINISTRATION.validate(request)['errors']
    compiled=MYSQL_ADMINISTRATION._compile(request)['statements'][0]
    assert compiled['source']==f'SET {scope} `max_execution_time` = %s' and compiled['parameters']==('exact-value',)
    preview=MYSQL_ADMINISTRATION.plan(request)['command_preview']['statements'][0]
    assert preview['source'].endswith('<redacted>') and 'exact-value' not in preview['source'] and preview['parameters_redacted']


def test_default_and_persistent_reset_do_not_bind_values_or_change_scope():
    target={'display_name':'max_execution_time'}
    assert operations.compile_operation('system-variable','reset_persist',{},target)['source']=='RESET PERSIST `max_execution_time`'
    assert operations.compile_operation('system-variable','set_global',{'value_mode':'DEFAULT'},target)['source']=='SET GLOBAL `max_execution_time` = DEFAULT'
    for name,value in [('x; DROP TABLE t','a'),('max_execution_time',2**53),('max_execution_time',{'sql':'x'}),('max_execution_time','\x00')]:
        with pytest.raises(RelationalClientError):operations.compile_operation('system-variable','set_persist',{'value':value},{'display_name':name})


def test_native_process_id_is_separate_from_thread_id_and_display_label():
    target={'display_name':'ambiguous','extensions':{'mysql':{'native':{'processlist_id':'18446744073709551615','thread_id':'3'}}}}
    assert operations.compile_operation('session','terminate_query',{},target)['source']=='KILL QUERY 18446744073709551615'
    assert operations.compile_operation('session','terminate_connection',{},target)['source']=='KILL CONNECTION 18446744073709551615'
    with pytest.raises(RelationalClientError):operations.compile_operation('session','terminate_query',{}, {'display_name':'3','native':{'thread_id':'3'}})


def test_native_catalog_surfaces_scoped_confirmed_forms():
    objects={row['resource_kind']:row for row in MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))['objects']}
    for kind,choices in operations.OPERATIONS.items():
        catalog={row['operation_id']:row for row in objects[kind]['operations']}
        assert choices<=catalog.keys()
        for operation in choices:
            assert catalog[operation]['confirmation_required'] and catalog[operation]['target_required']
            assert catalog[operation]['form']['form_id']=='mysql.'+kind+'.'+operation


def test_exact_numeric_text_keeps_native_numeric_type_and_avoids_json_rounding():
    target={'display_name':'max_execution_time'}
    result=operations.compile_operation('system-variable','set_global',{'value':str(2**64-1),'value_type':'INTEGER'},target)
    assert result['parameters']==(str(2**64-1),) and 'CAST(%s AS UNSIGNED)' in result['source']
    result=operations.compile_operation('system-variable','set_global',{'value':'0.1234567890123456789','value_type':'DECIMAL'},target)
    assert result['parameters']==('0.1234567890123456789',) and 'CAST(%s AS DECIMAL(65,30))' in result['source']
    import json
    json.dumps(result)


@pytest.mark.parametrize('operation',['set_global','set_persist','set_persist_only','reset_persist'])
def test_component_variables_keep_the_exact_native_dotted_name(operation):
    target={'display_name':'validate_password.length'}
    draft={} if operation=='reset_persist' else {'value':12}
    result=operations.compile_operation('system-variable',operation,draft,target)
    assert '`validate_password.length`' in result['source']
    assert result['parameters']==(() if operation=='reset_persist' else (12,))


@pytest.mark.parametrize('name',['.length','validate_password.','a.b.c','a.; DROP TABLE t','a.`b`','a..b'])
def test_component_variable_admission_refuses_ambiguous_or_injected_names(name):
    with pytest.raises(RelationalClientError):
        operations.compile_operation('system-variable','set_global',{'value':12},{'display_name':name})
