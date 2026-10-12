"""Native channel scoping, exact options and credential redaction."""
import pytest
from pgadmin.cdeadmin.providers import mysql_replication as replication
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine

TARGET={'display_name':'named channel','native':{'channel_name':'channel\'é'}}


def test_source_values_and_channel_are_bound_and_preview_redacted():
    draft={'source_options':{'SOURCE_HOST':"host'",'SOURCE_AUTO_POSITION':True,'SOURCE_SSL':True},'source_password':'test-only-secret'}
    request={'resource_kind':'replication-channel','operation_id':'alter','target_resource':TARGET,'draft':draft,'_provider_route':{'host':'trusted'}}
    assert not MYSQL_ADMINISTRATION.validate(request)['errors']
    compiled=MYSQL_ADMINISTRATION._compile(request)['statements'][0]
    assert compiled['source']=='CHANGE REPLICATION SOURCE TO SOURCE_HOST=%s, SOURCE_AUTO_POSITION=1, SOURCE_SSL=1, SOURCE_PASSWORD=%s FOR CHANNEL %s'
    assert compiled['parameters']==("host'",'test-only-secret',"channel'é")
    preview=MYSQL_ADMINISTRATION.plan(request)['command_preview']['statements'][0]
    assert 'test-only-secret' not in str(preview) and 'host\'' not in str(preview)


def test_default_channel_is_scoped_explicitly_and_reset_preserves_configuration():
    target={'native':{'channel_name':''}}
    for operation in ('start','stop','reset'):
        result=replication.compile_operation(operation,{},target)
        assert result['source']==operation.upper()+' REPLICA FOR CHANNEL %s' and result['parameters']==('',)
    assert replication.compile_operation('reset',{'delete_connection':True},target)['source']=='RESET REPLICA ALL FOR CHANNEL %s'
    with pytest.raises(RelationalClientError):replication.compile_operation('stop',{}, {'native':{'channel_name':'group_replication_applier'}})


def test_native_exact_position_and_until_condition_families():
    result=replication.compile_operation('alter',{'source_options':{'SOURCE_LOG_POS':str(2**64-1),'SOURCE_LOG_FILE':'bin.1'}},TARGET)
    assert 'SOURCE_LOG_POS=18446744073709551615' in result['source']
    result=replication.compile_operation('start',{'thread':'SQL_THREAD','until':{'SQL_AFTER_GTIDS':'uuid:1-10'}},TARGET)
    assert result['source']=='START REPLICA SQL_THREAD UNTIL SQL_AFTER_GTIDS=%s FOR CHANNEL %s'
    for value in [{'SOURCE_LOG_FILE':'bin.1'},{'SQL_AFTER_GTIDS':'uuid:1','SQL_AFTER_MTS_GAPS':True},{'SOURCE_PASSWORD':'secret'}]:
        with pytest.raises(RelationalClientError):replication.compile_operation('start',{'until':value},TARGET)


def test_replication_filter_exact_table_names_and_empty_lists():
    result=replication.compile_operation('filter',{'filters':{'REPLICATE_DO_TABLE':[['db`é','t`é']],'REPLICATE_REWRITE_DB':[['old','new']],'REPLICATE_IGNORE_DB':[]}},TARGET)
    assert result['source']=='CHANGE REPLICATION FILTER REPLICATE_DO_TABLE=(`db``é`.`t``é`), REPLICATE_REWRITE_DB=((`old`,`new`)), REPLICATE_IGNORE_DB=() FOR CHANNEL %s'
    assert result['parameters']==("channel'é",)


@pytest.mark.parametrize('options',[{'SOURCE_PASSWORD':'not allowed here'},{'NONEXISTENT':1},{'SOURCE_AUTO_POSITION':1},{'SOURCE_HEARTBEAT_PERIOD':float('nan')},{'SOURCE_LOG_POS':2**53},{'PRIVILEGE_CHECKS_USER':{'user':'x'}},[]])
def test_unadmitted_native_option_shapes_fail(options):
    with pytest.raises(RelationalClientError):replication.compile_operation('alter',{'source_options':options},TARGET)


def test_native_channel_forms_expose_password_as_sensitive():
    resource=next(row for row in MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))['objects'] if row['resource_kind']=='replication-channel')
    operations={row['operation_id']:row for row in resource['operations']}
    assert replication.OPERATIONS<=operations.keys()
    for operation in replication.OPERATIONS:
        assert operations[operation]['form']['form_id']=='mysql.replication-channel.'+operation
        if operation!='create':assert operations[operation]['confirmation_required'] and operations[operation]['target_required']
    field=next(row for row in operations['create']['form']['fields'] if row['field_id']=='source_password')
    assert field['sensitive'] and field['control']=='password'


def test_channel_labels_keep_empty_default_visible_without_name_collisions():
    assert replication.channel_label('')=='Default channel'
    assert replication.channel_label('Default channel')=='Channel "Default channel"'
    assert replication.channel_label('x"é')=='Channel "x\\"é"'
