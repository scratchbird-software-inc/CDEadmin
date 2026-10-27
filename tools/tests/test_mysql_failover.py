"""Typed native failover functions, independent grants and exact review binding."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.providers.mysql_family import mysql_failover as module
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.providers.mysql_descriptor_contract import operation_documents
from pgadmin.cdeadmin.providers.mysql_family.installed_catalog import CHANNEL_OBSERVATIONS
from test_mysql_applier_catalog import Observed, restored
from pgadmin.cdeadmin.providers.mysql_family.mysql_server_catalog import capture
from pgadmin.cdeadmin.providers.mysql_family.provider import _resources,MYSQL_PROFILE
from pgadmin.cdeadmin.workspace.mysql_server_plan import state,plan

UUID='01234567-89ab-cdef-0123-456789abcdef'
TARGET={'resource_kind':'replication-channel','display_name':'Channel "owned 雪"','native':{'server_uuid':UUID,'channel_name':"owned 雪'"}}
SERVER={'resource_kind':'server','resource_id':'server:MySQL','display_name':'MySQL','display_path':['MySQL'],'native':{'server_uuid':UUID}}


def draft(op):
    value={'confirmation':SERVER['display_name'] if op=='reset_failover_sources' else TARGET['display_name']}
    if op=='reset_failover_sources':value['all_channels']=True
    if op in {'add_failover_source','remove_failover_source','add_managed_failover'}:value.update(host="quoted'host",port=3307)
    if 'managed' in op:value['managed_name']=UUID.upper()
    return value


@pytest.mark.parametrize('op',list(module.OPERATIONS))
def test_each_native_action_has_typed_fields_and_exact_parameter_binding(op):
    target=SERVER if op=='reset_failover_sources' else TARGET
    value=module.compile_operation(op,draft(op),target)
    statement=value['statements'][0]
    assert statement['source'].startswith('SELECT asynchronous_connection_failover_'+module.OPERATIONS[op]+'(')
    assert "quoted'host" not in statement['source']
    if 'managed' in op:assert UUID.upper() in statement['parameters']
    kind=target['resource_kind'];assert MYSQL_ADMINISTRATION.supports(kind,op)
    descriptor=operation_documents()[kind,op]
    fields={row.get('backend_field_id',row['field_id']) for row in descriptor['fields']}
    assert set(draft(op))<=fields and all(row['control']!='json' for row in descriptor['fields'])
    assert MYSQL_ADMINISTRATION.validate({'resource_kind':kind,'operation_id':op,'draft':draft(op),'target_resource':target})=={'errors':[]}


@pytest.mark.parametrize('key,value',[('host',''),('host','é.example'),('host','host\n'),('port',True),('port',-1),('port',2**32),
 ('weight',0),('weight',101),('weight','50'),('network_namespace','ignored'),('unexpected',None),('confirmation','wrong')])
def test_unmanaged_options_are_exact_and_deprecated_namespace_is_not_faked(key,value):
    with pytest.raises(RelationalClientError):module.compile_operation('add_failover_source',{**draft('add_failover_source'),key:value},TARGET)


@pytest.mark.parametrize('port',[0,2**32-1])
def test_unmanaged_native_unsigned32_port_domain_is_not_narrowed(port):
    assert module.compile_operation('add_failover_source',{**draft('add_failover_source'),'port':port},TARGET)['statements'][0]['parameters'][2]==port


def test_managed_seed_bounds_and_native_remove_identity_are_distinct():
    for key,value in [('port',0),('port',65536),('managed_name','not-uuid'),('primary_weight',0),('secondary_weight',101)]:
        with pytest.raises(RelationalClientError):module.compile_operation('add_managed_failover',{**draft('add_managed_failover'),key:value},TARGET)
    value=module.compile_operation('remove_managed_failover',{'managed_name':'Existing Case Name','confirmation':TARGET['display_name']},TARGET)
    assert value['statements'][0]['parameters']==(TARGET['native']['channel_name'],'Existing Case Name')


def test_internal_channel_and_unobserved_server_are_refused():
    for native in [{'server_uuid':UUID,'channel_name':'group_replication_applier'}, {'channel_name':''}, {'server_uuid':'not-uuid','channel_name':''}]:
        with pytest.raises(RelationalClientError):module.compile_operation('add_failover_source',draft('add_failover_source'),{**TARGET,'native':native})
    with pytest.raises(RelationalClientError):module.compile_operation('reset_failover_sources',{'confirmation':'MySQL','all_channels':False},SERVER)


def test_source_actions_read_only_the_native_source_table():
    cursor=Mock();cursor.description=[('CHANNEL_NAME',),('HOST',)];cursor.fetchmany.return_value=[]
    assert module.observe(cursor,'','add_failover_source')=={'failover_sources':[]}
    assert cursor.execute.call_count==1 and cursor.execute.call_args.args[1]==('',)
    assert 'failover_managed' not in cursor.execute.call_args.args[0]


def fixture(monkeypatch):
    cursor=Mock();cursor.description=[('result',)];cursor.fetchall.return_value=[('native success',)]
    handle=Mock();handle.cursor.return_value=cursor
    client=SimpleNamespace(_connect=Mock(return_value=handle),_safe_close=Mock(),_forget_and_close=Mock())
    actor={'version':'9.7.0','server_uuid':UUID,'effective_principal':'owner@%'}
    monkeypatch.setattr(module,'environment',lambda *_:actor)
    monkeypatch.setattr(module,'observe',Mock(return_value={'failover_sources':[]}))
    compiled=module.compile_operation('add_failover_source',draft('add_failover_source'),TARGET)
    request={'provider_payload':{'compiled':compiled,'route':{}},'command_preview':{}}
    module.bind_review(client,request);client._connect.reset_mock();cursor.execute.reset_mock()
    return client,cursor,request,actor


def test_changed_review_and_state_refuse_before_native_dispatch(monkeypatch):
    client,cursor,request,actor=fixture(monkeypatch)
    changed=deepcopy(request);changed['provider_payload']['compiled']['statements'][0]['source']='SELECT unsafe()'
    with pytest.raises(RelationalClientError):module.apply(client,changed)
    client._connect.assert_not_called()
    module.observe.return_value={'failover_sources':[{'host':'external'}]}
    with pytest.raises(RelationalClientError) as caught:module.apply(client,request)
    assert not caught.value.native_dispatched and not caught.value.automatic_retry
    cursor.execute.assert_not_called()


@pytest.mark.parametrize('stage',['native','fetch','after','close'])
def test_unknown_and_post_ack_failures_do_not_replay_or_replace_native_outcome(monkeypatch,stage):
    client,cursor,request,actor=fixture(monkeypatch)
    error=OSError('private native diagnostics')
    if stage=='native':cursor.execute.side_effect=error
    elif stage=='fetch':cursor.fetchall.side_effect=error
    elif stage=='after':module.observe.side_effect=[{'failover_sources':[]},error]
    else:client._forget_and_close.side_effect=error
    with pytest.raises(RelationalClientError) as caught:module.apply(client,request)
    assert caught.value.native_dispatched and caught.value.native_acknowledged is (stage in {'after','close'})
    assert not caught.value.automatic_retry and 'private native diagnostics' not in str(caught.value)
    assert cursor.execute.call_count==1


def test_native_primary_failure_survives_connection_cleanup_loss(monkeypatch):
    client,cursor,request,_=fixture(monkeypatch);error=RuntimeError('private');error.errno=1234
    cursor.execute.side_effect=error;client._forget_and_close.side_effect=OSError('cleanup')
    with pytest.raises(RelationalClientError) as caught:module.apply(client,request)
    assert caught.value.errno==1234 and not caught.value.native_acknowledged


def test_failover_only_discovery_and_observed_empty_versus_denied_collections():
    connection=Observed(receiver=False,config=False,status=False)
    connection.observed['failover_sources']=[{'channel_name':'only','host':'source','port':3306,'network_namespace':'','weight':100,'managed_name':''}]
    connection.observed['failover_managed']=[]
    native=next(row['native'] for row in _resources(connection,{'route':{}},MYSQL_PROFILE) if row['resource_kind']=='replication-channel')
    assert native['failover_sources']==connection.observed['failover_sources'] and native['failover_managed']==[] and 'host' not in native
    row=next(row for row in restored(capture(connection))['rows'].values() if row['kind']=='replication-channel')
    before=state(row);changed=deepcopy(row);changed['native']['failover_sources'][0]['weight']=99
    assert state(changed)!=before
    assert row['native']['catalog_row']=={'channel_name':'only'}
    connection.observed['failover_managed']=None
    row=next(row for row in capture(connection)['resources'] if row['resource_kind']=='replication-channel')
    assert 'failover_managed' not in row['native']


def test_ddn_failover_postconditions_require_observed_effects_not_only_a_channel_row():
    from pgadmin.cdeadmin.providers.mysql_server_application import effect
    row={'kind':'replication-channel','resource_id':'channel','native':{'mysql_change':{'draft':{'host':'chosen','port':3307,'weight':99}}}}
    source={'channel_name':'owned','host':'chosen','port':3307,'network_namespace':'','managed_name':'','weight':1}
    root={'kind':'server','native':{'catalog_observations':[{'section':'replication-failover_sources','available':True},
        {'section':'replication-failover_managed','available':True}]}}
    observed={'kind':'replication-channel','native':{'catalog_row':{'channel_name':'owned'},'failover_sources':[source],'failover_managed':[]}}
    live={'rows':{'server':root,'channel':observed}}
    operation={'operation':'add_failover_source'}
    assert not effect(row,operation,live)
    source['weight']=99;assert effect(row,operation,live)
    assert not effect(row,{'operation':'remove_failover_source'},live)
    live['rows'].pop('channel');assert effect(row,{'operation':'remove_failover_source'},live)
    root['native']['catalog_observations'][0]['available']=False
    assert not effect(row,{'operation':'remove_failover_source'},live)


def test_ddn_managed_postconditions_check_both_weights_and_authoritative_absence():
    from pgadmin.cdeadmin.providers.mysql_server_application import effect
    row={'kind':'replication-channel','resource_id':'channel','native':{'mysql_change':{'draft':{'managed_name':UUID,'primary_weight':100,'secondary_weight':1}}}}
    group={'channel_name':'owned','managed_name':UUID,'managed_type':'GroupReplication','configuration':'{"Primary_weight":100,"Secondary_weight":2}'}
    observed={'kind':'replication-channel','native':{'catalog_row':{'channel_name':'owned'},'failover_sources':[],'failover_managed':[group]}}
    root={'kind':'server','native':{'catalog_observations':[{'section':'replication-failover_sources','available':True},
        {'section':'replication-failover_managed','available':True}]}}
    live={'rows':{'server':root,'channel':observed}}
    assert not effect(row,{'operation':'add_managed_failover'},live)
    group['configuration']='{"Primary_weight":100,"Secondary_weight":1}'
    assert effect(row,{'operation':'add_managed_failover'},live)
    assert not effect(row,{'operation':'remove_managed_failover'},live)
    observed['native']['failover_managed']=[];assert effect(row,{'operation':'remove_managed_failover'},live)
    observed['native']['failover_sources']=[{'managed_name':UUID}]
    assert not effect(row,{'operation':'remove_managed_failover'},live)
