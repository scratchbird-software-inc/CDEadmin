"""Durable archive admission, ownership, uncertainty and credential delegation."""
from copy import deepcopy
import json
import threading
import time
from types import SimpleNamespace
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError,delegate_credentials,options
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import MySQLBinlogJobs


@pytest.fixture
def manager(tmp_path):
    jobs=MySQLBinlogJobs(tmp_path/'jobs.json',tmp_path/'archives');endpoint=str(uuid.uuid4())
    captured={'identity':{'server_uuid':str(uuid.uuid4()),'version':'9.7.0','authenticated_principal':'archive@%','active_role':'NONE'},
        'state':{'gtid_executed':'native:1-7'}}
    program={'executable_sha256':'exact-native-program','tool_version':'9.7.0','execution_host':{'kind':'application-host','platform':'linux'}}
    review=jobs.review(1,endpoint,options({'start_file':'mysql-bin.000001','start_position':'9007199254740993'}),captured,'configuration',program)
    request={key:review[key] for key in ('job_id','review_digest')};request['confirmed']=True
    current={'source':captured['identity'],'configuration':'configuration','program':program}
    yield jobs,endpoint,review,request,current
    jobs.close()


class Transport:
    def __init__(self):self.closed=False;self.entered=threading.Event();self.stopped=threading.Event();self.calls=0
    def close(self):self.closed=True
    def execute(self,record,directory,cancel,progress):
        self.calls+=1;self.entered.set();deadline=time.monotonic()+10
        while not cancel.is_set() and time.monotonic()<deadline:time.sleep(.01)
        self.stopped.set();raise InterruptedError('Owned cancellation')


def test_review_preserves_wide_native_position_and_owner_scope_after_restart(manager):
    jobs,endpoint,review,_request,_current=manager
    restarted=MySQLBinlogJobs(jobs.path,jobs.root)
    assert restarted.list(1,endpoint)['jobs'][0]['options']['start_position']=='9007199254740993'
    for owner,scope in ((2,endpoint),(True,endpoint),(1,str(uuid.uuid4()))):
        with pytest.raises(BinlogArchiveError):restarted.get(review['job_id'],owner,scope)
    assert 'source_state' not in review and 'configuration' not in review


@pytest.mark.parametrize('changed',['source','configuration','program'])
def test_changed_native_identity_configuration_or_program_cannot_dispatch(manager,changed):
    jobs,endpoint,_review,request,current=manager;transport=Transport();current=deepcopy(current)
    current[changed]='different'
    with pytest.raises(BinlogArchiveError):jobs.start(request,1,endpoint,current,transport)
    assert transport.closed and transport.calls==0


def test_changed_review_cannot_dispatch(manager):
    jobs,endpoint,review,request,current=manager;transport=Transport()
    record=jobs.load(review['job_id'],1,endpoint);jobs.update(record,options={**record['options'],'start_file':'other.000001'})
    with pytest.raises(BinlogArchiveError,match='review changed'):jobs.start(request,1,endpoint,current,transport)
    assert transport.closed and transport.calls==0


def test_duplicate_start_never_replays_and_restarted_manager_cancels_worker(manager):
    jobs,endpoint,review,request,current=manager;transport=Transport()
    jobs.start(request,1,endpoint,current,transport);assert transport.entered.wait(3)
    restarted=MySQLBinlogJobs(jobs.path,jobs.root)
    assert restarted.start(request,1,endpoint,{},None)['job_id']==review['job_id']
    restarted.cancel(review['job_id'],1,endpoint);assert transport.stopped.wait(3)
    assert jobs.close() and transport.closed and transport.calls==1
    assert restarted.get(review['job_id'],1,endpoint)['state']=='cancelled'


def test_dead_archive_worker_stays_unknown_without_automatic_replay_or_removal(manager):
    jobs,endpoint,review,request,_current=manager
    record=jobs.load(review['job_id'],1,endpoint);jobs.update(record,state='active',worker_identity=[999999999,0])
    assert jobs.get(review['job_id'],1,endpoint)['state']=='unknown'
    assert jobs.start(request,1,endpoint,{},None)['state']=='unknown'
    with pytest.raises(BinlogArchiveError,match='termination'):jobs.remove_artifact(review['job_id'],1,endpoint,review['job_id'])


def test_durable_cancellation_is_observed_without_the_process_local_signal(manager):
    jobs,endpoint,review,request,current=manager;transport=Transport()
    jobs.start(request,1,endpoint,current,transport);assert transport.entered.wait(3)
    record=jobs.load(review['job_id'],1,endpoint)
    jobs.update(record,cancel_requested=True,state='cancel_requested')
    assert transport.stopped.wait(3) and jobs.close()
    assert jobs.get(review['job_id'],1,endpoint)['state']=='cancelled'


def test_failed_worker_start_is_durable_not_dispatched_and_closes_credentials(manager,monkeypatch):
    jobs,endpoint,review,request,current=manager;transport=Transport()
    monkeypatch.setattr(threading.Thread,'start',lambda _thread:(_ for _ in ()).throw(RuntimeError('Owned launch fault')))
    with pytest.raises(RuntimeError):jobs.start(request,1,endpoint,current,transport)
    assert transport.closed and jobs.get(review['job_id'],1,endpoint)['state']=='not_dispatched'
    assert jobs.start(request,1,endpoint,{},None)['state']=='not_dispatched'


def test_artifact_reconciliation_preserves_tool_receipt_and_uncertain_process_finality(manager,monkeypatch):
    jobs,endpoint,review,_request,_current=manager
    record=jobs.load(review['job_id'],1,endpoint)
    jobs.update(record,state='unknown',result={'tool':{'return_code':0}},native_process_termination_confirmed=False)
    monkeypatch.setattr(jobs,'native_verify',lambda *_args:{'files':[],'event_integrity':[],'total_bytes':9007199254740993})
    value=jobs.reconcile(review['job_id'],1,endpoint)
    assert value['state']=='artifact_verified' and value['native_process_termination_confirmed'] is False
    assert value['result']['tool']=={'return_code':0} and value['result']['artifact']['total_bytes']=='9007199254740993'
    with pytest.raises(BinlogArchiveError):jobs.remove_artifact(review['job_id'],1,endpoint,review['job_id'])


def test_no_new_snapshot_has_empty_files_without_fabricating_an_archive(manager):
    jobs,endpoint,review,_request,_current=manager;record=jobs.load(review['job_id'],1,endpoint)
    jobs.update(record,state='no_new_snapshot',result={'artifact':None,'continuation_cursor_advanced':False})
    assert jobs.files(review['job_id'],1,endpoint)['files']==[]


def test_factor_two_credential_keeps_its_native_binding_and_all_password_characters():
    password='LF\nquote\"slash\\雪'
    client=SimpleNamespace(_tool_secrets=lambda route,callback:callback([password]))
    lease=delegate_credentials(client,{'credential_references':{'database_password_2':'registered-secret'}})
    try:assert lease.use(lambda view:json.loads(bytes(view)))=={'password':'','password2':password}
    finally:lease.close()
    assert lease.closed


@pytest.mark.parametrize('value',[{'start_file':'bin.1','start_position':True},{'start_file':'bin.1','start_position':'04'},
    {'start_file':'bin.1','start_position':'18446744073709551616'},{'start_file':'bin.1','threads':False},
    {'start_file':'bin.1','compression':'zstd;level=23'},{'since_job_id':str(uuid.uuid4()),'start_file':'bin.1'},
    {'start_file':'bin.1','output':'/arbitrary/path'}])
def test_ambiguous_native_requests_are_refused(value):
    with pytest.raises(BinlogArchiveError):options(value)
