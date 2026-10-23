"""Encrypted delegation, unattended occurrence admission and no automatic replay."""
import base64
import json
import threading
import time
from types import SimpleNamespace

from flask import Flask
import pytest

from test_mysql_physical_batch_retention import setup  # noqa: F401
from pgadmin.cdeadmin.operations.store import JsonOperationStore
from pgadmin.cdeadmin.report_scheduler.crypto import WorkerKeyRing
from pgadmin.cdeadmin.workspace import mysql_physical_retention_schedule as schedule
from pgadmin.cdeadmin.workspace import mysql_physical_batch_retention as batch


@pytest.fixture
def scheduled(setup,tmp_path,monkeypatch):
    s=setup;app=Flask(__name__);hosts=[]
    app.config.update(CDEADMIN_MYSQL_RETENTION_POLL_SECONDS=.1,CDEADMIN_MYSQL_PHYSICAL_WORKER_KEYS={'current':base64.b64encode(b'x'*32).decode()},CDEADMIN_MYSQL_PHYSICAL_WORKER_ACTIVE_KEY_ID='current')
    s.service.operation_bus=SimpleNamespace(store=JsonOperationStore(tmp_path/'operations.json'))
    s.active=True
    def factory():
        host=schedule.ScheduleHost(app,s.service);hosts.append(host)
        def authority(grant):
            anchor=s.jobs.load(grant['options']['scope_job_id'],1,s.endpoint.id)
            if not s.active or grant['configuration']!=batch.digest({}) or schedule.program(s.jobs,anchor,grant['program']['execution_host'])!=grant['program']:
                raise batch.native.HostError('Owned authority changed')
            return SimpleNamespace(id=9),s.jobs,1,s.endpoint
        monkeypatch.setattr(host,'authority',authority)
        host.start_real=host.start;monkeypatch.setattr(host,'start',lambda:None)
        s.service.mysql_physical_scheduler=host
        return host
    s.host=factory();s.host_factory=factory;s.app=app
    def action(operation,body):return s.host.action(SimpleNamespace(id=9),s.jobs,1,s.endpoint,'retention_schedule_'+operation,body)
    s.schedule=action
    def review(anchor):return action('review',{'scope_job_id':anchor['job_id'],'options':{'policy':{'retention_days':0,'keep_latest':1},'interval_seconds':60,'expires_after_days':1},'credentials':{'private_key':'ephemeral-SSH-key'}})
    def confirm(grant):return {'job_id':grant['job_id'],'confirmed':True,'schedule_confirmation':grant['job_id']}
    def enable(grant):return action('enable',{**confirm(grant),'review_digest':grant['review_digest'],'delegate_ssh_credentials':True,'credentials':{'private_key':'ephemeral-SSH-key'}})
    def grant(anchor):return enable(review(anchor))
    s.review=review;s.confirm=confirm;s.enable=enable;s.grant=grant
    yield s
    for host in hosts:host.close()


def test_credentials_persist_only_after_confirmed_delegation_and_never_in_public_receipts(scheduled):
    s=scheduled;old=s.create();s.create();review=s.review(old)
    assert not review['ssh_delegation_present']
    grant=s.enable(review);private=s.host.read(grant['job_id'])
    assert 'ephemeral-SSH-key' not in json.dumps(private) and private['ssh_envelope']
    assert 'ssh_envelope' not in grant and 'ephemeral-SSH-key' not in json.dumps(grant)
    assert s.host.credentials(private)=={'private_key':'ephemeral-SSH-key'}
    assert s.schedule('disable',s.confirm(grant))['ssh_delegation_present'] is False
    assert s.host.read(grant['job_id'])['ssh_envelope'] is None


def test_automatic_occurrences_survive_idle_restart_and_include_later_same_scope_jobs(scheduled):
    s=scheduled;old=s.create();newest=s.create();grant=s.grant(old)
    first=s.host.tick(grant['job_id']);assert first['state']=='enabled' and not first['last_scan_empty']
    assert s.host.tick(grant['job_id'])['last_occurrence_id']==first['last_occurrence_id']
    s.host.close();s.host=s.host_factory();later=s.create()
    s.host.jobs.update(s.host.read(grant['job_id']),next_scan_at=0)
    second=s.host.tick(grant['job_id']);assert second['last_occurrence_id']!=first['last_occurrence_id']
    assert not (s.root/newest['job_id']/'artifact').exists() and (s.root/later['job_id']/'artifact').is_dir()
    assert s.jobs.get(old['job_id'],1,s.endpoint.id)['state']=='native_returned'


def test_real_background_loop_runs_without_a_viewer(scheduled):
    s=scheduled;old=s.create();s.create();grant=s.grant(old);s.host.start_real()
    deadline=time.monotonic()+5
    while (s.root/old['job_id']/'artifact').exists() and time.monotonic()<deadline:time.sleep(.02)
    assert not (s.root/old['job_id']/'artifact').exists()
    s.host.close();assert s.host.read(grant['job_id'])['last_scan_at']


def test_unknown_reply_suspends_future_scans_and_manual_reconciliation_does_not_reenable(scheduled,monkeypatch):
    s=scheduled;old=s.create();s.create();grant=s.grant(old);original=s.Transport.request
    def lost(channel,request):
        result=original(channel,request)
        if request['action']=='retention_remove':raise ConnectionError('owned lost completion reply')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(s.Transport,'request',lost)
        observed=s.host.tick(grant['job_id'])
    assert observed['state']=='attention_required' and not observed['ssh_delegation_present']
    occurrence=s.call('status',{'job_id':observed['last_occurrence_id']});assert occurrence['state']=='interrupted'
    assert s.call('reconcile',{'job_id':occurrence['job_id'],'credentials':{}})['state']=='completed'
    later=s.create();assert s.host.tick(grant['job_id'],force=True)['state']=='attention_required'
    assert (s.root/later['job_id']/'artifact').exists()


def test_disable_between_steps_preserves_all_unattempted_parent_files(scheduled,monkeypatch):
    s=scheduled;old=s.create();child=s.create('prepare',old['job_id']);s.create();grant=s.grant(old)
    original=batch.action
    def revoke(*args,**kwargs):
        value=original(*args,**kwargs)
        if args[5]=='retention_batch_advance' and value['state']=='paused':s.schedule('disable',s.confirm(grant))
        return value
    monkeypatch.setattr(batch,'action',revoke)
    observed=s.host.tick(grant['job_id']);assert observed['state']=='disabled'
    assert not (s.root/child['job_id']/'artifact').exists() and (s.root/old['job_id']/'artifact').is_dir()
    assert s.host.tick(grant['job_id'],force=True)['state']=='disabled'


@pytest.mark.parametrize('scan_state',['preparing','running'])
def test_interrupted_application_never_restarts_an_occurrence(scheduled,scan_state):
    s=scheduled;old=s.create();s.create();grant=s.grant(old)
    s.host.jobs.update(s.host.read(grant['job_id']),scan_state=scan_state)
    s.host=s.host_factory();assert s.host.tick(grant['job_id'])['state']=='attention_required'
    assert (s.root/old['job_id']/'artifact').is_dir()


def test_expiry_and_authority_revocation_remove_delegation_without_removing_files(scheduled):
    s=scheduled;old=s.create();s.create();grant=s.grant(old)
    s.host.jobs.update(s.host.read(grant['job_id']),valid_until=0)
    assert s.host.tick(grant['job_id'])['state']=='expired'
    next_grant=s.grant(old);s.active=False
    observed=s.host.tick(next_grant['job_id']);assert observed['state']=='attention_required' and not observed['ssh_delegation_present']
    assert (s.root/old['job_id']/'artifact').is_dir()


def test_cross_policy_ciphertext_reuse_and_missing_key_suspend_safely(scheduled):
    s=scheduled;old=s.create();s.create();first=s.grant(old);second=s.grant(old)
    s.host.jobs.update(s.host.read(second['job_id']),ssh_envelope=s.host.read(first['job_id'])['ssh_envelope'])
    assert s.host.tick(second['job_id'])['state']=='attention_required'
    s.host.keys=WorkerKeyRing()
    assert s.host.tick(first['job_id'])['state']=='attention_required'
    assert (s.root/old['job_id']/'artifact').is_dir()


def test_rotation_preserves_scope_and_discarded_keys_cannot_read_new_envelope(scheduled):
    s=scheduled;old=s.create();s.create();grant=s.grant(old);prior=s.host.keys
    s.host.keys=WorkerKeyRing({'current':base64.b64encode(b'x'*32).decode(),'next':base64.b64encode(b'y'*32).decode()},'next')
    assert s.schedule('rotate',s.confirm(grant))['ssh_delegation_present']
    private=s.host.read(grant['job_id']);assert json.loads(private['ssh_envelope'])['key_id']=='next'
    assert s.host.credentials(private)=={'private_key':'ephemeral-SSH-key'}
    from pgadmin.cdeadmin.report_scheduler.crypto import WorkerKeyError
    with pytest.raises(WorkerKeyError):prior.decrypt(private['ssh_envelope'],schedule.aad(private))


def test_manual_batch_dispatch_cannot_bypass_enabled_policy_and_no_automatic_resume(scheduled,monkeypatch):
    s=scheduled;old=s.create();s.create();grant=s.grant(old);original=batch.action
    def inspect(*args,**kwargs):
        value=original(*args,**kwargs)
        if args[5]=='retention_batch_review' and value['state']=='reviewed':
            with pytest.raises(batch.native.HostError,match='Disable'):s.step(value)
        return value
    monkeypatch.setattr(batch,'action',inspect)
    assert s.host.tick(grant['job_id'])['state']=='enabled'
    assert not (s.root/old['job_id']/'artifact').exists()


def test_durable_occurrence_binding_precedes_source_reservations_and_cancel_preserves_new_review(scheduled,monkeypatch):
    s=scheduled;old=s.create();s.create();grant=s.grant(old);original=s.jobs.update
    def interrupted(record,**values):
        if values.get('retention_batch_id'):raise OSError('owned interruption before source reservation')
        return original(record,**values)
    with monkeypatch.context() as patch:
        patch.setattr(s.jobs,'update',interrupted)
        observed=s.host.tick(grant['job_id'])
    assert observed['state']=='attention_required' and observed['last_occurrence_id']
    from pgadmin.cdeadmin.workspace import mysql_physical_retention as single
    manual=single.action(s.service,None,s.jobs,1,s.endpoint,'retention_review',{'job_id':old['job_id'],'credentials':{}})
    occurrence=s.call('status',{'job_id':observed['last_occurrence_id']})
    assert s.step(occurrence,'cancel')['state']=='cancelled'
    assert s.jobs.load(old['job_id'],1,s.endpoint.id)['retention_review_job_id']==manual['job_id']


def test_two_pollers_cannot_dispatch_the_same_due_occurrence(scheduled,monkeypatch):
    s=scheduled;old=s.create();s.create();grant=s.grant(old);peer=s.host_factory();entered=threading.Event();release=threading.Event();original=batch.action
    def delayed(*args,**kwargs):
        if args[5]=='retention_batch_review':entered.set();assert release.wait(5)
        return original(*args,**kwargs)
    monkeypatch.setattr(batch,'action',delayed)
    first=s.host;worker=threading.Thread(target=lambda:first.tick(grant['job_id']));worker.start()
    try:
        assert entered.wait(5);assert peer.tick(grant['job_id'])['state']=='enabled'
    finally:release.set();worker.join(5)
    assert not worker.is_alive() and not (s.root/old['job_id']/'artifact').exists()
