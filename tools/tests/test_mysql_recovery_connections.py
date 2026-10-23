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


def test_raw_utility_requires_reviewed_replay_mode_and_owns_its_native_route(monkeypatch):
    registry=bridge.Bridges();monkeypatch.setattr(bridge,'bridges',registry)
    binding={'id':'owned','recovery_mode':'replay'}
    original=registry.install(binding,SimpleNamespace(close=Mock()),{})
    route={bridge.ROUTE_KEY:binding,'host':'managed-recovery.invalid','port':3306}
    with pytest.raises(RelationalClientError):bridge.require_raw_utility(route)
    lease=bridge.admit_raw_utility(route)
    try:
        bridge.require_raw_utility(lease.route)
        assert lease.route['host']=='127.0.0.1' and lease.route['port']==original.port
        with pytest.raises(RelationalClientError):bridge.require_raw_utility({**lease.route,'port':original.port+1})
        with pytest.raises(RelationalClientError):registry.detach(binding)
        with pytest.raises(RelationalClientError):bridge.admit_raw_utility({**route,bridge.ROUTE_KEY:{**binding,'recovery_mode':'read_only'}})
    finally:lease.close();registry.close()
    with pytest.raises(RelationalClientError):bridge.require_raw_utility(lease.route)


def test_unknown_native_utility_termination_retains_its_port_reservation(monkeypatch):
    registry=bridge.Bridges();monkeypatch.setattr(bridge,'bridges',registry)
    binding={'id':'owned','recovery_mode':'replay'}
    original=registry.install(binding,SimpleNamespace(close=Mock()),{})
    lease=bridge.admit_raw_utility({bridge.ROUTE_KEY:binding})
    try:
        lease.uncertain=True;lease.close()
        assert not lease.released and original.users==1 and original.uncertain_utilities==[lease]
        with pytest.raises(RelationalClientError):registry.detach(binding)
    finally:lease.uncertain=False;lease.close();registry.close()


def test_independent_termination_releases_only_the_original_jobs_utility(monkeypatch):
    registry=bridge.Bridges();monkeypatch.setattr(bridge,'bridges',registry)
    binding={'id':'owned','recovery_mode':'replay'};original=registry.install(binding,SimpleNamespace(close=Mock()),{})
    first=bridge.admit_raw_utility({bridge.ROUTE_KEY:binding});second=bridge.admit_raw_utility({bridge.ROUTE_KEY:binding})
    try:
        first.job_id='first';second.job_id='second'
        for value in (first,second):value.uncertain=True;value.close()
        bridge.confirm_raw_utility_termination(binding,'first')
        assert first.released and not second.released and original.users==1
        assert original.uncertain_utilities==[second]
        with pytest.raises(RelationalClientError):registry.detach(binding)
    finally:
        for value in (first,second):value.uncertain=False;value.close()
        registry.close()


@pytest.mark.parametrize('extra',[
    {'recovery_mode':'unknown'}, {'recovery_mode':'replay'},
    {'recovery_mode':'replay','recovery_server_id':0},
    {'recovery_mode':'replay','recovery_server_id':True},
    {'recovery_mode':'replay','recovery_server_id':4294967296},
    {'recovery_mode':'replay','recovery_server_id':10001,'recovery_port':0},
    {'recovery_mode':'read_only','recovery_server_id':10001},
])
def test_replay_startup_refuses_ambiguous_or_incomplete_native_configuration(monkeypatch,extra):
    from pgadmin.cdeadmin.workspace import mysql_physical_service as physical
    monkeypatch.setattr(physical.native.ssh,'public_route',lambda value:value)
    value={'connection':{'platform':'posix'},'workspace':'/private','executable':'/bin/xtrabackup','mysql':'/bin/mysql',
        'phase':'recover','sql_host':'127.0.0.1','sql_port':3306,'input_job_id':'6c304f92-1195-4d9c-9c5a-fb7974af691e',
        'parallel':1,'memory_bytes':67108864,'timeout_seconds':120,'accept_release_candidate':True,
        'mysqld':'/bin/mysqld','recovery_gtid_mode':'ON','recovery_port':3307}
    assert physical.options(value)['recovery_mode']=='read_only'
    assert physical.options({**value,'recovery_mode':'replay','recovery_server_id':10001})['recovery_server_id']==10001
    with pytest.raises(physical.native.HostError):physical.options({**value,**extra})
