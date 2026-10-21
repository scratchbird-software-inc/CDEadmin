"""Reviewed instance identity, native effects and uncertain post-ACK outcomes."""
from copy import deepcopy
from unittest.mock import Mock
import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_instance as instance
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine

UUID='01234567-89ab-cdef-0123-456789abcdef'


def target():
    return {'resource_id':'server:MySQL','resource_kind':'server','display_name':'MySQL','display_path':['MySQL'],'native':{'server_uuid':UUID}}


def planned(operation='enable_innodb_redo'):
    compiled=instance.compile_operation(operation,{'confirmation':'MySQL'},target())
    compiled['mysql_instance']['review']={'execution_identity':{'server_uuid':UUID},'before':{'available':True,'rows':[['Innodb_redo_log_enabled','ON']]}}
    return {'provider_payload':{'route':{'host':'owned'},'compiled':compiled}}


@pytest.mark.parametrize('operation',instance.OPERATIONS)
def test_exact_native_instance_tasks_have_confirmed_engine_specific_forms(operation):
    catalog=MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    item=next(row for row in catalog['objects'] if row['resource_kind']=='server')
    task=next(row for row in item['operations'] if row['operation_id']==operation)
    assert task['confirmation_required'] and task['target_required']
    assert task['form']['form_id']=='mysql.server.'+operation
    assert MYSQL_ADMINISTRATION.supports('server',operation) and not MARIADB_ADMINISTRATION.supports('server',operation)
    draft={'confirmation':'MySQL',**({'initial_load_only':True} if operation=='disable_innodb_redo' else {})}
    checked=MYSQL_ADMINISTRATION._compile({'resource_kind':'server','operation_id':operation,'target_resource':target(),'draft':draft})
    assert checked['statements'][0]['source'].startswith('ALTER INSTANCE ')


@pytest.mark.parametrize('change',[{'confirmation':'other'},{'lock_wait_seconds':0},{'lock_wait_seconds':True},{'source':'SHUTDOWN'},{'channel':'mysql_main; SHUTDOWN'},{'rollback_on_error':'false'}])
def test_ambiguous_or_changed_native_instance_options_cannot_dispatch(change):
    with pytest.raises(RelationalClientError):instance.compile_operation('reload_tls',{'confirmation':'MySQL',**change},target())


def test_redo_disable_requires_explicit_initial_load_acknowledgement():
    with pytest.raises(RelationalClientError,match='initial load'):instance.compile_operation('disable_innodb_redo',{'confirmation':'MySQL'},target())


@pytest.mark.parametrize('change',[{'resource_id':'server:MariaDB'},{'display_path':['another']},{'native':{}},{'native':{'server_uuid':'not native'}}])
def test_exact_server_resource_identity_is_required(change):
    with pytest.raises(RelationalClientError):instance.compile_operation('reload_keyring',{'confirmation':'MySQL'},{**target(),**change})


@pytest.mark.parametrize('outcome',['ack','changed-identity','changed-state','no-reply','after-ack'])
def test_owned_native_dispatch_ack_and_later_observation_are_separate(monkeypatch,outcome):
    client=Mock();cursor=client._connect.return_value.cursor.return_value;cursor.warnings=[]
    monkeypatch.setattr(instance,'environment',lambda _:{'server_uuid':'other' if outcome=='changed-identity' else UUID})
    observed={'available':True,'rows':[['Innodb_redo_log_enabled','ON']]}
    if outcome=='changed-state':observed={'available':True,'rows':[['Innodb_redo_log_enabled','OFF']]}
    calls=0
    def observe(*_):
        nonlocal calls
        calls+=1
        if outcome=='after-ack' and calls==2:raise OSError('owned lost later observation')
        return deepcopy(observed)
    monkeypatch.setattr(instance,'observe',observe)
    def execute(source,*_):
        if source.startswith('ALTER INSTANCE') and outcome=='no-reply':raise OSError('owned missing reply')
    cursor.execute.side_effect=execute
    if outcome=='ack':
        result=instance.apply(client,planned());assert result['accepted'] and result['instance_observation']['native_acknowledged']
        assert result['instance_observation']['redo_state_verified'] and not result['automatic_retry']
    else:
        with pytest.raises(RelationalClientError) as failure:instance.apply(client,planned())
        assert failure.value.native_dispatched==(outcome in {'no-reply','after-ack'})
        assert failure.value.native_acknowledged==(outcome=='after-ack') and not failure.value.automatic_retry
        if outcome.startswith('changed'):cursor.execute.assert_not_called()
    client._forget_and_close.assert_called_once()


def test_changed_compiled_plan_and_borrowed_session_are_refused_before_native_access():
    client=Mock();request=planned();request['provider_payload']['compiled']['statements'][0]['source']='SHUTDOWN'
    with pytest.raises(RelationalClientError):instance.apply(client,request)
    with pytest.raises(RelationalClientError):instance.apply(client,planned(),object())
    client._connect.assert_not_called()


def test_native_instance_context_actions_require_verified_owner_and_explicit_confirmation():
    from pgadmin.cdeadmin.context_menu import endpoint_context_actions
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    profile=registration_profile('mysql-native')
    for state,owner,expected in [('verified',True,True),('unverified',True,False),('verified',False,False)]:
        actions={row['command_id']:row for row in endpoint_context_actions(profile,state,can_manage=owner)}
        for operation in instance.OPERATIONS:
            item=actions['endpoint.mysql.'+operation]
            assert item['enabled']==expected and item['requires_confirmation']
            assert item['arguments']['database_target_id'] is None
