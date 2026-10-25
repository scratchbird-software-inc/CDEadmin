"""Cutover requires actual independent acceptance and a current source fence."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import threading
import time
import uuid

import pytest

from pgadmin.cdeadmin.workspace import mysql_recovery_cutover as cutover


def accepted():
    return {'acceptance_outcome':'matched','native_process_termination_confirmed':True,
        'source':{'server_uuid':'recovered'},'source_state':{'scopes':{'data_requested':True,'definitions_requested':True}},
        'result':{'selected_dump_surfaces_verified':True,'server_locks_released':True}}


@pytest.mark.parametrize('change',[{'acceptance_outcome':'unconfirmed'},{'native_process_termination_confirmed':False},
    {'result':{'selected_dump_surfaces_verified':True,'server_locks_released':False}},
    {'source':{'server_uuid':'other'}},{'source_state':{'scopes':{'data_requested':False,'definitions_requested':True}}}])
def test_cutover_refuses_incomplete_mismatched_or_unreleased_acceptance(monkeypatch,change):
    record={**accepted(),**deepcopy(change)};jobs=Mock();jobs.load.return_value=record
    monkeypatch.setattr(cutover,'acceptance_manager',lambda *_:(jobs,1,SimpleNamespace(id='target')))
    with pytest.raises(cutover.native.HostError,match='matched native'):cutover.acceptance_record(None,None,1,'acceptance','recovered')


@pytest.mark.parametrize('active,enabled,pid,observed',[('active','disabled',0,True),('inactive','enabled',0,True),
    ('inactive','disabled',22,True),('inactive','disabled',0,False)])
def test_stale_source_disable_reply_does_not_prove_a_current_source_fence(monkeypatch,active,enabled,pid,observed):
    jobs=Mock();jobs.load.return_value={'job_id':'fence','review_digest':'digest','options':{'operation':'service_disable','connection':{}},
        'source':{'server_uuid':'source'},'state':'native_process_returned','remote_receipt':{'result':{'return_code':0}},'source_state':{'host_binding':{}}}
    transport=Mock();transport.request.return_value={'service_reconciliation':{'observed':observed,'service':{
        'unit':{'ActiveState':active,'UnitFileState':enabled},'manager_main_pid':pid,'native_process':None}}}
    monkeypatch.setattr(cutover.host,'manager',lambda *_:(jobs,1,None));monkeypatch.setattr(cutover.host,'native_request',lambda *_:{})
    monkeypatch.setattr(cutover.host,'credentials',lambda x:x);monkeypatch.setattr(cutover.ssh,'Transport',lambda *_:transport)
    with pytest.raises(cutover.native.HostError,match='inactive and disabled'):
        cutover.source_fence(None,None,1,SimpleNamespace(id='source'),'fence',{},'source')
    transport.close.assert_called_once()


@pytest.mark.parametrize('change',[{'datadir':'/other/'},{'pid_file':'/other/mysql.pid'},{'port':4400},{'hostname':'other'}])
def test_another_listener_cannot_be_accepted_using_only_a_copied_uuid(monkeypatch,change):
    deployment={'options':{'deployment':{'directory':'/permanent','port':3349}},'source_state':{'host_binding':{
        'hostname':'host','server_uuid':'00000000-0000-4000-8000-000000000001','datadir':'/source'}}}
    observed={'datadir':'/permanent/runtime-data/','pid_file':'/permanent/runtime.pid','port':3349,'hostname':'host',**change}
    monkeypatch.setattr(cutover,'rows',lambda *_:[observed])
    with pytest.raises(cutover.native.HostError,match='SQL listener'):cutover.bind_target(object(),deployment)


def test_activation_runs_without_the_http_observer_and_a_second_worker_never_replays_its_claim(tmp_path):
    jobs=cutover.CutoverJobs(tmp_path/'jobs',tmp_path/'files');endpoint=str(uuid.uuid4());entered=threading.Event();finish=threading.Event()
    program={'execution_host':{'kind':'application-host'}};source={'server_uuid':str(uuid.uuid4())}
    ticket=jobs.review(1,endpoint,{}, {'identity':source,'state':{}},'configuration',program)
    calls=[]
    def execute(_record,_directory,_signal):
        calls.append('once');entered.set();assert finish.wait(5)
        raise cutover.native.HostError('Owned loss of original activation acknowledgement')
    close=Mock();admitted=cutover.ActivationTransport(execute,close)
    request={key:ticket[key] for key in ('job_id','review_digest')}|{'confirmed':True}
    try:
        pending=jobs.start(request,1,endpoint,{'configuration':'configuration','source':source,'program':program},admitted)
        assert entered.wait(2) and pending['state'] in {'dispatching','active'}
        other=cutover.CutoverJobs(tmp_path/'jobs',tmp_path/'files');unused=Mock()
        repeated=other.start(request,1,endpoint,{},unused)
        assert repeated['state']=='active' and calls==['once'];unused.close.assert_called_once()
        finish.set();deadline=time.monotonic()+3
        while ticket['job_id'] in jobs.workers and time.monotonic()<deadline:time.sleep(.01)
        receipt=jobs.get(ticket['job_id'],1,endpoint)
        assert receipt['state']=='unknown' and receipt['production_cutover_verified'] is False and receipt['automatic_retry'] is False
        close.assert_called_once()
    finally:finish.set();jobs.close()


def test_cancellation_and_the_startup_claim_have_one_durable_boundary(tmp_path):
    jobs=cutover.CutoverJobs(tmp_path/'jobs',tmp_path/'files');endpoint=str(uuid.uuid4())
    def review():
        ticket=jobs.review(1,endpoint,{}, {'identity':{},'state':{}},'configuration',{'execution_host':{}})
        return jobs.load(ticket['job_id'],1,endpoint)
    cancelled=review();assert jobs.cancel(cancelled['job_id'],1,endpoint)['state']=='cancelled'
    with pytest.raises(InterruptedError):jobs.begin_activation(cancelled,{'matched':True})
    committed=review();jobs.begin_activation(committed,{'matched':True})
    with pytest.raises(cutover.native.HostError,match='may be committed'):jobs.cancel(committed['job_id'],1,endpoint)
    assert jobs.load(committed['job_id'],1,endpoint)['activation_may_have_dispatched']
