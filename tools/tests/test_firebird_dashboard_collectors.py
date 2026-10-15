"""Embedded collector authority and host/definition separation."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tools.tests.test_monitoring_host import host
from pgadmin.cdeadmin.workspace.firebird_embedded_monitoring import EmbeddedMonitoringGrant
from pgadmin.cdeadmin.workspace.monitoring import MonitoringPolicy
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def local(tmp_path):
    file=tmp_path/'owned.fdb'
    file.touch()
    return {'attachment_mode':'embedded','database':str(file),'filesystem_root':str(tmp_path),'user':'SYSDBA'}


def test_embedded_grant_uses_file_permissions_without_sealing_passwords(tmp_path,monkeypatch):
    route=local(tmp_path)
    permissions=Mock()
    permissions.acquire_secret.side_effect=AssertionError('No password authentication')
    allowed=Mock(return_value=True)
    clock=[0]
    policy=MonitoringPolicy(1,'owned','file',lease_seconds=5)
    grant=EmbeddedMonitoringGrant(policy,route,'generation',permissions,allowed,clock=lambda:clock[0])
    assert grant.authentication['mode']=='local-file'
    permissions.require.assert_any_call('embedded_runtime')
    permissions.require.assert_any_call('filesystem')
    permissions.acquire_secret.assert_not_called()
    clock[0]=5
    with pytest.raises(PermissionError):
        grant.require(policy,'collect')
    grant.revoke()


def test_embedded_grant_refuses_server_wire_and_escaping_files(tmp_path):
    route=local(tmp_path)
    permissions=Mock()
    for policy, selected in [(MonitoringPolicy(1,'owned',None,interval_seconds=15),route),
            (MonitoringPolicy(1,'owned','file',require_wire_encryption=True),route),
            (MonitoringPolicy(1,'owned','file'),{**route,'host':'remote'}),
            (MonitoringPolicy(1,'owned','file'),{**route,'database':'/elsewhere/file.fdb'})]:
        with pytest.raises((ValueError,RelationalClientError)):
            EmbeddedMonitoringGrant(policy,selected,'generation',permissions,lambda *_:True)


def test_host_embedded_policy_does_not_need_worker_keys_or_password(tmp_path,monkeypatch):
    value,scope=host(tmp_path,monkeypatch)
    scope['route']=local(tmp_path)
    scope['permissions']=Mock()
    value.keys=SimpleNamespace(available=False)
    monkeypatch.setattr(EmbeddedMonitoringGrant,'open_source',lambda *_:Mock(
        sample=Mock(return_value={'status':'available','scope':'database','transaction_refresh':{'status':'completed'}})))
    owned=value._owned_server
    def resolve(owner,sid):
        server=owned(owner,sid)
        server.endpoint_profile.profile_id='firebird-embedded'
        return server
    value._owned_server=resolve
    try:
        snapshot=value.snapshot(1,7,'database')
        assert snapshot['collection_available'] and snapshot['attachment_mode']=='embedded'
        assert not value.snapshot(1,7,None)['collection_available']
        with pytest.raises(ValueError):
            value.enable(1,7,'database',{'credentials':{'username':'ignored','password':'unused'}})
        started=value.enable(1,7,'database',{})
        assert started['authentication']['mode']=='local-file'
        assert value.disable(1,7,'database')['released']
        scope['permissions'].acquire_secret.assert_not_called()
    finally:
        value.close()
