"""Owned member admission and original control across browsing-seed failure."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.workspace import mysql_topology_service as service


@pytest.mark.parametrize('target_uuid',['member','origin','unrelated'])
def test_execution_member_requires_current_native_membership_and_releases_private_sessions(monkeypatch,target_uuid):
    clients=[Mock(),Mock()];connections=[object(),object()]
    monkeypatch.setattr(service,'context',Mock(side_effect=[(clients[0],{}),(clients[1],{})]))
    monkeypatch.setattr(service,'private_connection',Mock(side_effect=connections))
    monkeypatch.setattr(service.native,'capture',Mock(side_effect=[
        {'identity':{'server_uuid':'origin'},'metadata':{'instance_uuids':['member']}},
        {'identity':{'server_uuid':target_uuid}}]))
    if target_uuid=='unrelated':
        with pytest.raises(service.native.BinlogArchiveError):service.execution_member(object(),object(),object())
    else:service.execution_member(object(),object(),object())
    for client,connection in zip(clients,connections):client._discard_failed_session.assert_called_once_with(connection)


@pytest.mark.parametrize('operation,payload',[
    ('status',{'job_id':'original'}),('cancel',{'job_id':'original'}),
    ('start',{'job_id':'original','review_digest':'bound','confirmed':True}),
])
def test_original_control_uses_owned_execution_scope_without_reconnecting_browsing_seed(monkeypatch,operation,payload):
    import sys
    monkeypatch.setitem(sys.modules,'pgadmin.model',SimpleNamespace(Server=object))
    origin=SimpleNamespace(id=1,name='offline browsing seed');target=SimpleNamespace(id=2,name='original execution')
    monkeypatch.setattr(service,'admitted_context',Mock())
    monkeypatch.setattr(service,'source_server',Mock(return_value=target))
    jobs=Mock();jobs.load.return_value={'state':'unknown','options':{}}
    jobs.get.return_value=jobs.cancel.return_value=jobs.start.return_value={'job_id':'original','state':'unknown'}
    monkeypatch.setattr(service,'manager',Mock(return_value=(jobs,7,SimpleNamespace(id='endpoint'))))
    membership=Mock(side_effect=AssertionError('Original controls must not reconnect the browsing seed'))
    monkeypatch.setattr(service,'execution_member',membership)
    result=service.action(SimpleNamespace(_principal_id=lambda _:7),origin,operation,{**payload,'execution_server_id':2})
    assert result['state']=='unknown' and result['execution_registration']=={'server_id':2,'name':'original execution','origin_server_id':1}
    membership.assert_not_called()
    service.source_server.assert_called_once_with(7,2)


@pytest.mark.parametrize('value',[True,False,0,-1,'2',None])
def test_untyped_execution_registration_is_refused_before_resolution(monkeypatch,value):
    import sys
    monkeypatch.setitem(sys.modules,'pgadmin.model',SimpleNamespace(Server=object))
    resolve=Mock();monkeypatch.setattr(service,'source_server',resolve)
    with pytest.raises(service.native.BinlogArchiveError):service.action(object(),object(),'inspect',{'execution_server_id':value})
    resolve.assert_not_called()
