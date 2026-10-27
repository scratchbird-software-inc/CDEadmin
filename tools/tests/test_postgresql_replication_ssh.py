"""Pinned native SSH credentials, peer observations and release ownership."""
from types import SimpleNamespace
from unittest.mock import Mock

import paramiko
import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
from pgadmin.cdeadmin.providers.postgresql.continuity_transport import ContinuityTransport
from pgadmin.cdeadmin.providers.postgresql import replication_ssh,replication_admission


@pytest.fixture
def peer():return paramiko.RSAKey.generate(2048)


def server(**changes):
    return SimpleNamespace(**{'use_ssh_tunnel':1,'tunnel_host':'ssh.native','tunnel_port':22,'tunnel_username':'registered-user',
        'host':'database.native','port':5432,'tunnel_authentication':0,'tunnel_keep_alive':5,'tunnel_password':None,**changes})


def test_registered_transport_description_does_not_probe_or_authenticate(monkeypatch):
    connect=Mock(side_effect=AssertionError('Metadata inspection performed network IO'))
    monkeypatch.setattr(replication_ssh.socket,'create_connection',connect)
    result=replication_ssh.describe(server())
    assert result['ssh']['remote_host']=='database.native' and result['probe_authenticated'] is False
    connect.assert_not_called()


def test_text_port_from_saved_registration_preserves_exact_native_destination():
    assert replication_ssh.route(server(tunnel_port='2222'))['port']==2222


@pytest.mark.parametrize('port',[True,False,'22.0',' 22','-22','65536','0','２２'])
def test_invalid_saved_port_cannot_select_a_native_transport(port):
    with pytest.raises(ContinuityError):replication_ssh.route(server(tunnel_port=port))


def test_native_ssh_pin_and_credential_are_exactly_bound_to_registration(peer):
    pin=peer.get_name()+' '+peer.get_base64()
    selected,secrets,identity=replication_ssh.material(server(),SimpleNamespace(tunnel_password=None),
        {'ssh_host_key':pin,'ssh_password':'ephemeral-ssh'})
    assert selected['host_key']==peer.get_base64() and selected['remote_host']=='database.native'
    assert secrets=={'ssh_password':'ephemeral-ssh'}
    assert identity['host_key_fingerprint']==replication_ssh.fingerprint(peer)
    assert 'ephemeral-ssh' not in repr(identity) and 'ephemeral-ssh' not in repr(selected)


@pytest.mark.parametrize('selected',[{}, {'ssh_host_key':'invalid'}, {'ssh_host_key':'ssh-rsa invalid'},
    {'ssh_host_key':'missing-public-key','ssh_password':'secret'}])
def test_native_admission_requires_a_real_expected_key(selected):
    with pytest.raises(ContinuityError):replication_ssh.material(server(),SimpleNamespace(),selected)


def test_credentials_do_not_cross_registered_ssh_authentication_modes(peer):
    with pytest.raises(ContinuityError):
        replication_ssh.material(server(),SimpleNamespace(),{'ssh_host_key':peer.get_name()+' '+peer.get_base64(),'ssh_private_key_password':'wrong-mode'})


def test_failed_tunnel_close_is_retained_for_explicit_retry_and_credentials_are_destroyed(monkeypatch):
    from pgadmin.cdeadmin.providers.postgresql import monitoring_ssh
    created=[]
    class Tunnel:
        def __init__(self,*args):self.calls=0;created.append(self)
        def start(self):return 6543
        def close(self):
            self.calls+=1
            if self.calls<3:raise RuntimeError('Owned tunnel close remains unconfirmed')
    monkeypatch.setattr(monitoring_ssh,'MonitoringSSHTunnel',Tunnel)
    transport=ContinuityTransport({'host':'native','port':5432},ssh={'selected':True},secrets={'ssh_password':'secret'})
    with pytest.raises(RuntimeError):
        with transport.parameters() as values:assert values['hostaddr']=='127.0.0.1'
    assert created[0] in transport._tunnels
    with pytest.raises(ContinuityError):transport.close()
    assert transport.closed and all(value.closed for value in transport._secrets.values())
    transport.close();assert not transport._tunnels and created[0].calls==3


def test_worker_transport_does_not_reuse_admission_loopback_or_forwarder(monkeypatch):
    from pgadmin.cdeadmin.providers.postgresql import monitoring_ssh
    forwards=[]
    class Tunnel:
        def __init__(self,*args):self.port=6500+len(forwards);self.closed=False;forwards.append(self)
        def start(self):return self.port
        def close(self):self.closed=True
    monkeypatch.setattr(monitoring_ssh,'MonitoringSSHTunnel',Tunnel)
    def observed(parameters, *, logical=False):
        assert not logical
        assert parameters['host']=='database.native' and parameters['hostaddr']=='127.0.0.1'
        return {'host':'database.native','port':parameters['port'],'server_version':180003},ContinuityTransport(parameters)
    monkeypatch.setattr(replication_admission,'_native_capture',observed)
    source,transport=replication_admission.capture({'host':'database.native','port':5432,'password':'db-private'},
        ssh={'selected':True},ssh_secrets={'ssh_password':'ssh-private'})
    try:
        assert source['port']==5432 and forwards[0].closed
        with transport.parameters() as values:
            assert values['port']==6501 and values['hostaddr']=='127.0.0.1'
            assert values['password']=='db-private'
        assert all(peer.closed for peer in forwards)
    finally:transport.close()
