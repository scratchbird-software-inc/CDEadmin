"""Independent native Router host/seed identity and no-replay boundaries."""
import base64
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_router_worker as worker
from pgadmin.cdeadmin.providers.mysql_family import mysql_router_transport as transport


@pytest.fixture
def router(tmp_path,monkeypatch):
    executable=tmp_path/'mysqlrouter';executable.write_bytes(b'owned Router unit fixture')
    seed={'version':'9.7.0','server_uuid':str(uuid.uuid4()),'cluster_id':'native-cluster','cluster_type':'gr','clusterset_id':None,
        'authenticated_principal':'operator@host','active_role':'NONE','connector_version':'26.7.0','sql_connection_closed_after_observation':True}
    options={'executable':str(executable),'directory':str(tmp_path/'new-router'),'workspace':str(tmp_path/'jobs'),
        'user':'router','base_port':6446,'bind_address':'127.0.0.1','timeout_seconds':60,'extra_arguments':[],
        'seed':{'host':'127.0.0.1','port':3306,'user':'operator','ssl_mode':'REQUIRED','ssl_ca':None,'ssl_cert':None,'ssl_key':None}}
    native=SimpleNamespace(file_hash=lambda path:'owned-executable-hash',process=Mock(return_value={'return_code':0,'outputs':{
        'stdout':{'base64':base64.b64encode(b'MySQL Router Ver 9.7.0 for owned unit fixture').decode()}}}))
    monkeypatch.setattr(worker,'host_module',lambda:native);probe=Mock(return_value=seed);monkeypatch.setattr(worker,'peer',probe)
    request={'schema':'cdeadmin.mysql-router-host.v1','action':'inspect','options':options,'expected_seed':seed,'database_password':'private-bootstrap-value'}
    return SimpleNamespace(request=request,probe=probe,native=native,target=Path(options['directory']))


def test_router_host_preview_binds_remote_seed_without_requiring_a_database_directory(router):
    value=worker.dispatch(router.request,transport.sources())
    assert value['seed']['server_uuid']==router.request['expected_seed']['server_uuid']
    assert 'server_uuid' not in value['host'] and 'datadir' not in value['host'] and not router.target.exists()
    router.probe.assert_called_once_with(router.request['options']['seed'],'private-bootstrap-value')


def test_wrong_native_seed_or_existing_deployment_refuses_without_creating_job_or_replacing_files(router):
    changed=deepcopy(router.request);changed['expected_seed']['server_uuid']=str(uuid.uuid4())
    with pytest.raises(worker.Refused,match='different native metadata seed'):worker.dispatch(changed,{})
    router.target.mkdir();configuration=router.target/'mysqlrouter.conf';configuration.write_bytes(b'original native configuration')
    router.probe.reset_mock()
    with pytest.raises(worker.Refused,match='never replaces'):worker.dispatch(router.request,{})
    assert configuration.read_bytes()==b'original native configuration';router.probe.assert_not_called()
    assert not Path(router.request['options']['workspace']).exists()


@pytest.mark.parametrize('action',['status','cancel','acknowledge'])
def test_missing_original_router_receipt_never_dispatches_or_creates_a_workspace(router,action):
    request={**router.request,'action':action,'job_id':str(uuid.uuid4()),'input_digest':'original'}
    request.pop('database_password')
    value=worker.dispatch(request,{})
    assert value['state']=='unknown' and value['remote_receipt_available'] is False and value['automatic_retry'] is False
    assert not Path(request['options']['workspace']).exists();router.probe.assert_not_called();router.native.process.assert_not_called()


def test_native_router_arguments_keep_private_password_out_and_preserve_exact_uri_user_and_ipv6(router):
    value=worker.inspect(router.request);options=deepcopy(router.request['options']);options['seed'].update(host='::1',user='operator 雪@host')
    argv=worker.arguments(options,value)
    assert '--bootstrap=mysql://operator%20%E9%9B%AA%40host@[::1]:3306' in argv
    assert 'private-bootstrap-value' not in repr(argv)
    for option in ('--force','--directory=/another','--bootstrap=another','-uother'):
        changed=deepcopy(router.request);changed['options']['extra_arguments']=[option]
        with pytest.raises(worker.Refused):worker.selected(changed)


def test_original_router_sdk_is_job_scoped_and_reconciles_without_current_adapter_sources(tmp_path):
    sources=transport.sources();first=tmp_path/'first';first.mkdir();second=tmp_path/'second';second.mkdir()
    left=worker.sdk(first,sources);right=worker.sdk(second,sources)
    assert left is not right and Path(left.__file__).is_relative_to(first) and Path(right.__file__).is_relative_to(second)
    assert worker.sdk(first,expected=worker.sdk_hashes(sources)) is left
    original=Path(left.__file__);original.write_text(original.read_text()+'\n# changed helper\n')
    with pytest.raises(worker.Refused,match='original|Original'):worker.sdk(first,expected=worker.sdk_hashes(sources))


@pytest.mark.parametrize('password',['','native 雪 password'])
def test_background_router_dispatch_uses_admitted_credential_without_reopening_request_vault(password):
    from pgadmin.cdeadmin.workspace.mysql_router_service import Invocation
    events=[]
    @contextmanager
    def guard():
        events.append('acquire')
        try:yield
        finally:events.append('release')
    client=Mock();client._native_operation.side_effect=guard
    client._tool_secrets.side_effect=lambda route,callback:callback([password])
    native=Mock();invocation=Invocation(native,client,{},None);invocation.acquire();sealed=invocation.secret
    client._tool_secrets.side_effect=AssertionError('Background worker accessed request Vault')
    record={'job_id':str(uuid.uuid4()),'review_digest':'review','options':{'timeout_seconds':60},'source_state':{'seed':{},'remote_review':{}}}
    invocation.execute(record)
    assert native.request.call_args.args[0]['database_password']==password
    invocation.close();invocation.close()
    assert sealed.closed and not any(sealed._buffer) and events.count('acquire')==events.count('release')==2
    native.close.assert_called_once()


def test_router_service_dispatch_requires_no_database_client_or_secret():
    from pgadmin.cdeadmin.workspace.mysql_router_service import Invocation
    native=Mock();invocation=Invocation(native,None,None,None);invocation.acquire()
    record={'job_id':str(uuid.uuid4()),'review_digest':'review','options':{'operation':'service_start','timeout_seconds':60},
        'source_state':{'seed':{},'remote_review':{},'deployment_binding':{'native':'original'}}}
    invocation.execute(record);invocation.close()
    request=native.request.call_args.args[0]
    assert request['action']=='service_start' and request['deployment_binding']=={'native':'original'} and 'database_password' not in request


def test_changed_native_router_configuration_refuses_service_control_before_manager_mutation(router,monkeypatch):
    from pgadmin.cdeadmin.providers.mysql_family import mysql_router_services as services
    request=deepcopy(router.request);request['options'].update(operation='service_start',service={'manager':'systemd','name':'owned.service'})
    request['deployment_binding']={'observation':{'program':{'path':request['options']['executable'],'sha256':'owned-executable-hash'}},
        'deployment':{'configuration_sha256':'original'}}
    monkeypatch.setattr(worker,'deployment',lambda path:{'directory':str(router.target),'directory_identity':[1,2],
        'configuration_path':str(router.target/'mysqlrouter.conf'),'configuration_sha256':'changed','native_router_ids':['native']})
    with pytest.raises(worker.Refused,match='configuration changed'):services.runtime(request,worker)
    router.native.process.assert_not_called()
