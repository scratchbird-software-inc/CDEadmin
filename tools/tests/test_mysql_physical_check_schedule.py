"""Recovery schedules admit explicit immutable checkpoints and isolated startup."""
from copy import deepcopy
import uuid
import pytest
from pgadmin.cdeadmin.workspace import mysql_physical_check_schedule as check


@pytest.fixture
def selected(monkeypatch):
    monkeypatch.setattr(check.physical.native.ssh,'public_route',lambda value:value)
    return {'physical':{'connection':{'platform':'posix'},'workspace':'/private','executable':'/bin/xtrabackup','mysql':'/bin/mysql',
        'phase':'recover','sql_host':'127.0.0.1','sql_port':3306,'input_job_id':str(uuid.uuid4()),'parallel':1,'memory_bytes':67108864,
        'timeout_seconds':300,'accept_release_candidate':True,'mysqld':'/bin/mysqld','recovery_gtid_mode':'ON',
        'recovery_port':0,'recovery_mode':'read_only','recovery_local_infile':True},
        'expected_backup_job_id':str(uuid.uuid4()),'threads':4,'interval_seconds':60,'expires_after_days':1}


@pytest.mark.parametrize('change',[{'recovery_port':3307},{'recovery_local_infile':False},{'timeout_seconds':29},
    {'timeout_seconds':3601},{'recovery_mode':'replay','recovery_port':3307,'recovery_server_id':12}])
def test_schedules_refuse_writable_network_or_untrusted_recovery_inputs(selected,change):
    assert check.options(selected)['physical']['recovery_local_infile'] is True
    value=deepcopy(selected);value['physical'].update(change)
    with pytest.raises(check.physical.native.HostError):check.options(value)


@pytest.mark.parametrize('changes',[{'expected_backup_job_id':'unknown'},{'threads':True},{'interval_seconds':59},{'expires_after_days':0}])
def test_policy_requires_exact_expected_identity_native_threads_and_expiry(selected,changes):
    with pytest.raises((check.physical.native.HostError,check.native.BinlogArchiveError)):check.options({**selected,**changes})


def test_enable_uses_the_existing_cross_worker_lifecycle_lock_without_reentering_it(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    grant={'job_id':str(uuid.uuid4()),'state':'reviewed','options':{'expected_backup_job_id':str(uuid.uuid4())},'source_state':{'expected':{'sealed':True}},'review_digest':'exact','expires_at':float('inf')}
    monkeypatch.setattr(check,'review_digest',lambda _grant:'exact')
    host=check.ScheduleHost.__new__(check.ScheduleHost)
    host.jobs=SimpleNamespace(load=lambda *_args:grant);host.read=lambda _id:grant
    host.expected=lambda *_args:({'sealed':True},None,None,None);held=[]
    host.hold=lambda *_args:held.append(_args[-1])
    service=SimpleNamespace(mysql_check_scheduler=host);endpoint=SimpleNamespace(id=str(uuid.uuid4()));jobs=object()
    monkeypatch.setattr(check.physical,'manager',lambda *_args:(jobs,1,endpoint))
    lock=[]
    @contextmanager
    def admission(_jobs):
        assert not lock,'Lifecycle lock was reentered through a second file descriptor'
        lock.append(True)
        try:yield
        finally:lock.pop()
    monkeypatch.setattr(check.retention,'admission',admission)
    def enabled(_self,*_args):
        assert lock==[True]
        grant['state']='enabled';return dict(grant)
    monkeypatch.setattr(check.backups.ScheduleHost,'action',enabled)
    value=check.physical.action(service,None,'check_schedule_enable',{'job_id':grant['job_id'],'review_digest':'exact',
        'confirmed':True,'schedule_confirmation':grant['job_id'],'delegate_ssh_credentials':True,'delegate_database_credentials':True,'credentials':{}})
    assert value['state']=='enabled' and held==[True] and not lock


@pytest.mark.parametrize('state',['enabled','attention_required','disabled','expired'])
def test_enabling_an_old_policy_never_releases_its_existing_input_holds(monkeypatch,state):
    from types import SimpleNamespace
    grant={'job_id':str(uuid.uuid4()),'state':state};held=[]
    host=check.ScheduleHost.__new__(check.ScheduleHost)
    host.jobs=SimpleNamespace(load=lambda *_args:grant);host.read=lambda _id:grant
    host.hold=lambda *_args:held.append(_args[-1])
    monkeypatch.setattr(check.backups.ScheduleHost,'action',lambda *_args:dict(grant))
    assert host.action(None,None,1,SimpleNamespace(id=str(uuid.uuid4())),'check_schedule_enable',{'job_id':grant['job_id']})['state']==state
    assert not held


def test_unconfirmed_policy_does_not_acquire_retention_holds(monkeypatch):
    from types import SimpleNamespace
    grant={'job_id':str(uuid.uuid4()),'state':'reviewed','review_digest':'exact','expires_at':float('inf')};held=[]
    host=check.ScheduleHost.__new__(check.ScheduleHost);host.jobs=SimpleNamespace(load=lambda *_args:grant)
    host.hold=lambda *_args:held.append(_args[-1])
    with pytest.raises(check.physical.native.HostError,match='Confirm the exact reviewed'):
        host.action(None,None,1,SimpleNamespace(id=str(uuid.uuid4())),'check_schedule_enable',{'job_id':grant['job_id']})
    assert not held
