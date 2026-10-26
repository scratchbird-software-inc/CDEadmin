"""Native-generated credentials cross only a reserved protected result boundary."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
import pytest
from pgadmin.cdeadmin.providers.mysql_family import mysql_accounts as accounts, mysql_passwords as passwords
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.security import SecretReference

CANARY='private-generated-雪-secret'


class Receiver:
    def __init__(self):
        self.binding_id=str(uuid4());self.leases=[];self.values={};self.events=[]
    def reserve(self,user,host,factors):
        self.events.append(('reserve',user,host,factors));return object()
    def publish(self,reservation,factor,lease):
        self.events.append(('publish',factor));self.leases.append(lease)
        reference=SecretReference(str(uuid4()),str(uuid4()),'legacy_native','password','memory','owned','private',frozenset({'authenticate'}))
        self.values[reference.reference_id]=lease.use(bytes)
        return reference
    def release(self,reservation):self.events.append(('release',))


def intent():return accounts.compile_operation('create',{'name':'owned','host':'%','authentication_mode':'RANDOM_PASSWORD'})['mysql_account_change']


def cursor(rows=None):
    value=Mock();value.description=[(key,) for key in ['user','host','generated password','auth_factor']]
    value.fetchall.return_value=rows if rows is not None else [('owned','%',CANARY,1)]
    return value


def test_native_generated_modes_include_create_alter_and_factor_identity_without_secret_parameters():
    compiled=accounts.compile_operation('create',{'name':'owned','authentication_mode':'RANDOM_PASSWORD',
        'authentication_factors':[{'mode':'RANDOM_PASSWORD','plugin':'caching_sha2_password'}]})
    assert compiled['statements'][0]['source'].endswith('BY RANDOM PASSWORD AND IDENTIFIED WITH `caching_sha2_password` BY RANDOM PASSWORD')
    assert compiled['statements'][0]['parameters']==()
    assert passwords.factors(compiled['mysql_account_change'])==(1,2)
    compiled=accounts.compile_operation('alter',{'authentication_mode':'RANDOM_PASSWORD','replace_password':'old','retain_current_password':True},
        {'native':{'user':'owned','host':'%'}})
    assert 'BY RANDOM PASSWORD REPLACE %s RETAIN CURRENT PASSWORD' in compiled['statements'][0]['source']
    for operation in ('ADD','MODIFY'):
        compiled=accounts.compile_operation('alter',{'factor_actions':[{'action':operation,'factor':2,'mode':'RANDOM_PASSWORD'}]},
            {'native':{'user':'owned','host':'%'}})
        assert passwords.factors(compiled['mysql_account_change'])==(2,)


def test_only_a_secret_reference_crosses_delivery_and_the_lease_is_closed():
    receiver=Receiver();value=passwords.deliver(receiver,object(),cursor(),intent())
    assert len(value)==1 and value[0]['factor']==1
    assert receiver.values[value[0]['secret_reference_id']]==CANARY.encode()
    assert CANARY not in str(value)+str(receiver.leases)
    assert all(lease.closed for lease in receiver.leases)


@pytest.mark.parametrize('rows',[[('other','%',CANARY,1)],[('owned','other',CANARY,1)],
    [('owned','%',CANARY,2)],[('owned','%',CANARY,True)],[],
    [('owned','%',CANARY,1),('owned','%',CANARY,1)]])
def test_wrong_or_incomplete_native_result_is_never_a_success(rows):
    receiver=Receiver()
    with pytest.raises(RelationalClientError):passwords.deliver(receiver,object(),cursor(rows),intent())
    assert all(lease.closed for lease in receiver.leases)


def test_callback_failure_still_closes_secret_lease():
    receiver=Receiver();publish=receiver.publish
    def failed(*args):publish(*args);raise RuntimeError(CANARY)
    receiver.publish=failed
    with pytest.raises(RuntimeError):passwords.deliver(receiver,object(),cursor(),intent())
    assert receiver.leases[0].closed


@pytest.mark.parametrize('binding',[None,'malformed',str(uuid4())])
def test_missing_or_changed_receiver_refuses_review_before_any_connection(binding):
    client=SimpleNamespace(_connect=Mock())
    if binding:client.protected_password_receiver=SimpleNamespace(binding_id=binding)
    planned={'provider_payload':{'compiled':accounts.compile_operation('create',intent()['draft']),'route':{}}}
    with pytest.raises(RelationalClientError,match='Protected generated-password'):accounts.bind_review(client,planned)
    client._connect.assert_not_called()


def prepare(monkeypatch):
    receiver=Receiver();native=cursor();native.warnings=[('Warning',1000,CANARY)]
    handle=Mock();handle.cursor.return_value=native
    client=SimpleNamespace(protected_password_receiver=receiver,_connect=Mock(return_value=handle),_safe_close=Mock(),_forget_and_close=Mock())
    identity={'sql_mode':''};before={'public':{'present':False}}
    monkeypatch.setattr(accounts,'check_grammar',lambda *_:{'qualified':True})
    monkeypatch.setattr(accounts,'observe',lambda *_:before)
    from pgadmin.cdeadmin.providers.mysql_family import mysql_indexes
    monkeypatch.setattr(mysql_indexes,'context',lambda *_:identity)
    compiled=accounts.compile_operation('create',intent()['draft'])
    compiled['mysql_account_change']['review']={'identity':identity,'before':before,'grammar':{'qualified':True},'password_delivery':receiver.binding_id}
    return client,receiver,native,{'provider_payload':{'compiled':compiled,'route':{}}}


def test_apply_reserves_before_ddl_and_keeps_generated_text_out_of_receipts(monkeypatch):
    client,receiver,native,request=prepare(monkeypatch)
    native.execute.side_effect=lambda *_:receiver.events.append(('DDL',))
    result=accounts.apply(client,request)
    assert [row[0] for row in receiver.events]==['reserve','DDL','publish','release']
    assert CANARY not in str(result) and result['native_warnings']==[{'level':'Warning','code':1000}]
    assert result['protected_password_results'][0]['secret_reference_id'] in receiver.values
    assert receiver.leases[0].closed


@pytest.mark.parametrize('stage',['reserve','publish','release','fetch','dispatch','close'])
def test_delivery_and_transport_failures_never_leak_or_replay_credentials(monkeypatch,stage):
    client,receiver,native,request=prepare(monkeypatch)
    def failed(*_):raise RuntimeError(CANARY)
    if stage in {'reserve','publish','release'}:setattr(receiver,stage,failed)
    elif stage=='fetch':native.fetchall.side_effect=failed
    elif stage=='dispatch':native.execute.side_effect=failed
    else:client._forget_and_close.side_effect=failed
    with pytest.raises(RelationalClientError) as caught:accounts.apply(client,request)
    error=caught.value
    assert CANARY not in str(error) and error.automatic_retry is False
    assert error.native_dispatched is (stage!='reserve')
    assert error.native_acknowledged is (stage not in {'reserve','dispatch'})
    assert native.execute.call_count==int(stage!='reserve')
    assert all(lease.closed for lease in receiver.leases)


def test_changed_receiver_binding_and_missing_review_fail_before_connect(monkeypatch):
    for change in ('replace','missing'):
        client,receiver,_native,request=prepare(monkeypatch)
        if change=='replace':receiver.binding_id=str(uuid4())
        else:request['provider_payload']['compiled']['mysql_account_change']['review'].pop('password_delivery')
        with pytest.raises(RelationalClientError):accounts.apply(client,request)
        client._connect.assert_not_called()


def test_bad_later_row_is_rejected_before_any_secret_is_published():
    receiver=Receiver()
    with pytest.raises(RelationalClientError):passwords.deliver(receiver,object(),cursor([('owned','%',CANARY,1),('owned','%',CANARY,1)]),intent())
    assert not receiver.values


def test_no_result_is_only_accepted_for_explicit_native_existence_clauses():
    receiver=Receiver();native=cursor();native.description=None
    with pytest.raises(RelationalClientError):passwords.deliver(receiver,object(),native,intent())
    value=intent();value['draft']['if_not_exists']=True
    assert passwords.deliver(receiver,object(),native,value)==[]
    native.description=cursor().description;native.fetchall.return_value=[]
    assert passwords.deliver(receiver,object(),native,value)==[]


def test_no_reservation_prevents_native_mutation(monkeypatch):
    client,receiver,native,request=prepare(monkeypatch)
    receiver.reserve=lambda *_:None
    with pytest.raises(RelationalClientError) as caught:accounts.apply(client,request)
    assert not caught.value.native_dispatched and not caught.value.native_acknowledged
    native.execute.assert_not_called()


def test_client_validation_reports_missing_delivery_without_connecting():
    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client,MYSQL_PROFILE
    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
    client._connect=Mock(side_effect=AssertionError('Validation connected'))
    try:
        request={'resource_kind':'user','operation_id':'create','draft':intent()['draft']}
        value=client.validate_admin_operation(request)
        assert value['errors'][0]['code']=='protected_password_delivery_unavailable'
        client.protected_password_receiver=Receiver()
        assert client.validate_admin_operation(request)=={'errors':[]}
        client._connect.assert_not_called()
    finally:client.close()
