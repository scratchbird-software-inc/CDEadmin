"""Private native recovery connection identity and lease boundaries."""
import socket
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pgadmin.cdeadmin.providers.mysql_family import mysql_recovery_bridge as bridge
from pgadmin.cdeadmin.providers.mysql_family import mysql_recovery_stream as stream
from pgadmin.cdeadmin.providers.mysql_family import mysql_recovery_worker as recovery
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.endpoints import EndpointRegistrationError,EndpointService


def test_absent_and_forged_bindings_never_fall_back_to_native_network():
    connect=Mock()
    with pytest.raises(RelationalClientError):bridge.native_connection(connect,(),{bridge.ROUTE_KEY:{'id':'missing'},'host':'source'})
    connect.assert_not_called()


@pytest.mark.parametrize('changes',[
    {'mysql_recovery_binding':None},{'host':'production.example'},
    {'port':3307},{'unix_socket':'/other/mysql.sock'},
    {'failover':[{'host':'production.example'}]},
    {'mysql_recovery_binding':{'id':'owned','owner':2,'endpoint_id':'endpoint'}},
])
def test_recovery_registration_rejects_changed_or_missing_private_route(changes):
    binding={'id':'owned','owner':1,'endpoint_id':'endpoint'}
    route={'host':'managed-recovery.invalid','port':3306,bridge.ROUTE_KEY:binding,**changes}
    endpoint=SimpleNamespace(id='endpoint',profile_id='mysql-native',
        extension_profile=SimpleNamespace(schema_reference=bridge.SCHEMA,profile_data=json.dumps({'binding':binding})))
    server=SimpleNamespace(user_id=1)
    with pytest.raises(EndpointRegistrationError,match='reviewed private transport'):
        EndpointService.__new__(EndpointService)._route_and_reference(server,endpoint,
            route_model=SimpleNamespace(configuration=json.dumps(route)))


def test_listener_binding_and_stop_are_scoped_to_the_original_native_process():
    import os,sys
    if not sys.platform.startswith('linux'):pytest.skip('Native Linux host listener facts')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));listener.listen()
        assert stream.listener_owned(os.getpid(),listener.getsockname()[1])
        assert not stream.listener_owned(os.getpid(),listener.getsockname()[1]+1)


def test_recovery_port_admission_allows_completed_native_connections_but_not_another_listener():
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind(('127.0.0.1',0));listener.listen();port=listener.getsockname()[1]
        with pytest.raises(recovery.Refused,match='occupied'):recovery.check_listener_port(port)
        with socket.create_connection(('127.0.0.1',port)) as client:
            accepted,_=listener.accept();accepted.close();assert client.recv(1)==b''
    recovery.check_listener_port(port)


def test_detached_transport_keeps_its_port_reserved_until_original_native_leases_end():
    transport=SimpleNamespace(close=Mock())
    value=bridge.Bridge({'id':'owned'},transport,{})
    lease=value.acquire();port=value.port
    try:
        value.close()
        with socket.socket() as other:
            with pytest.raises(OSError):other.bind(('127.0.0.1',port))
        with pytest.raises(RelationalClientError):value.acquire()
        lease.release();lease.release()
        assert value.listener.fileno()==-1 and value.users==0
    finally:value.close();lease.release()


@pytest.mark.parametrize('operation',['detach','replace'])
def test_registered_transport_preserves_original_connections_until_explicit_close(operation):
    registry=bridge.Bridges();binding={'id':'owned'}
    transport=SimpleNamespace(close=Mock());original=registry.install(binding,transport,{})
    lease=original.acquire()
    try:
        with pytest.raises(RelationalClientError,match='Close this recovery'):
            if operation=='detach':registry.detach(binding)
            else:registry.install(binding,SimpleNamespace(close=Mock()),{})
        assert registry.get(binding) is original and original.active
        transport.close.assert_not_called()
        lease.release()
        registry.detach(binding)
        assert not original.active
    finally:lease.release();registry.close()


def test_failed_attachment_cleanup_cannot_detach_a_different_original_transport():
    registry=bridge.Bridges();binding={'id':'owned'}
    original=registry.install(binding,SimpleNamespace(close=Mock()),{})
    try:
        registry.detach(binding,expected=SimpleNamespace(),force=True)
        assert registry.get(binding) is original
    finally:registry.close()


def test_native_reconnect_cannot_use_a_replaced_recovery_transport(monkeypatch):
    binding={'id':'owned','server_uuid':'target','version':'9.7.0','datadir':'/recovered'}
    old=SimpleNamespace(port=1234,acquire=Mock(),active=True)
    leases=[]
    def acquire():
        lease=SimpleNamespace(release=Mock());leases.append(lease);return lease
    old.acquire.side_effect=acquire
    registry=SimpleNamespace(get=Mock(return_value=old));monkeypatch.setattr(bridge,'bridges',registry)
    class Native:pass
    native=Native();native.close=Mock();native.reconnect=Mock();native.cursor=Mock()
    native.cursor.return_value.fetchone.return_value=('target','9.7.0','/recovered/')
    connect=Mock(return_value=native)
    result=bridge.native_connection(connect,(),{bridge.ROUTE_KEY:binding,'host':'invalid'})
    assert connect.call_args.kwargs['host']=='127.0.0.1'
    registry.get.return_value=SimpleNamespace()
    with pytest.raises(RelationalClientError,match='replaced'):result.reconnect()
    result.close();assert leases[0].release.call_count==1
