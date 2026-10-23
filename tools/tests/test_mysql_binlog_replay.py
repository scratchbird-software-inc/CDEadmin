"""Native replay claims, uncertain commits and target fencing without retry."""
import threading
import time
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_replay import options
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import digest
from pgadmin.cdeadmin.workspace.mysql_binlog_replay_jobs import MySQLBinlogReplayJobs


@pytest.fixture(params=['mysql','mariadb'])
def manager(tmp_path,request):
    from pgadmin.cdeadmin.workspace.mariadb_binlog_replay_jobs import MariaDBBinlogReplayJobs
    from pgadmin.cdeadmin.providers.mysql_family.mariadb_binlog_replay import options as maria_options
    maria=request.param=='mariadb';cls=MariaDBBinlogReplayJobs if maria else MySQLBinlogReplayJobs
    jobs=cls(tmp_path/'jobs.json',tmp_path/'replays');endpoint=str(uuid.uuid4())
    target={'version':'9.7.0','server_uuid':str(uuid.uuid4()),'authenticated_principal':'restore@%','active_role':'NONE'}
    if maria:target['server_uid']='aBcDeFgHiJkLmNoPqRsTuVwXyZ0=';target.pop('server_uuid')
    native_options=maria_options if maria else options
    state={'target':{'identity':target,'state':{'gtid_executed':'native-baseline'}},'input_reference':{
        'server_id':7,'endpoint_id':str(uuid.uuid4()),'job_id':str(uuid.uuid4()),'artifact_digest':'sealed',
        'summary':{'total_bytes':9007199254740993,'start_from':{'position':9007199254740993},'end_at':{'position':4}}}}
    program={'execution_host':{'kind':'application-host'},'executable_sha256':'native'}
    def review(scope=endpoint):
        value=jobs.review(1,scope,native_options({'target_confirmation':target.get('server_uuid',target.get('server_uid'))}),{'identity':target,'state':state},'configuration',program)
        return value,{'job_id':value['job_id'],'review_digest':value['review_digest'],'confirmed':True}
    current={'source':target,'program':program,'configuration':'configuration'}
    yield jobs,endpoint,target,review,current
    jobs.close()


class Transport:
    def __init__(self,mode):self.mode=mode;self.entered=threading.Event();self.closed=False;self.calls=0
    def close(self):self.closed=True
    def execute(self,record,directory,cancel,progress,boundary):
        self.calls+=1
        if self.mode!='cancel-before':boundary()
        self.entered.set()
        if self.mode.startswith('cancel'):
            assert cancel.wait(5)
            error=InterruptedError('Owned native interruption')
            error.observation={'process_observation':{'cleanup_confirmed':True},'stdout':'private SQL','stderr':'private SQL'}
            raise error
        if self.mode=='lost-ack':
            error=ConnectionError('Native return was not acknowledged')
            error.observation={'process_observation':{'cleanup_confirmed':True}}
            raise error
        return {'control':None if self.mode=='missing-control' else {'native_load_invoked':self.mode!='refused','native_load_returned':self.mode!='refused'},
            'tool':{'return_code':0,'process_observation':{'cleanup_confirmed':self.mode!='lost-child'}}}


def finished(jobs,review,endpoint):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        with jobs._maps_lock:known=jobs.workers.get(review['job_id'])
        if not known or not known[0].is_alive():return jobs.get(review['job_id'],1,endpoint)
        time.sleep(.01)
    raise TimeoutError('Owned replay worker did not stop')


def test_replay_review_is_owned_durable_and_preserves_wide_archive_numbers(manager):
    jobs,endpoint,_target,review,_current=manager;item,_request=review()
    restarted=type(jobs)(jobs.path,jobs.root);value=restarted.get(item['job_id'],1,endpoint)
    assert value['remote_database_mutation'] and value['automatic_retry'] is False and value['data_recovery_verified'] is False
    assert value['source_archive']['summary']['total_bytes']=='9007199254740993'
    assert value['source_archive']['summary']['start_from']['position']=='9007199254740993'
    assert 'source' not in value and 'source_state' not in value and 'configuration' not in value
    for owner,scope in ((2,endpoint),(1,str(uuid.uuid4()))):
        with pytest.raises(BinlogArchiveError):restarted.get(item['job_id'],owner,scope)


@pytest.mark.parametrize('mode,outcome,state,blocked',[
    ('returned','returned','native_load_returned',False),('refused','not_dispatched','not_dispatched',False),
    ('lost-ack','unknown','unknown',True),('missing-control','unknown','unknown',True),('lost-child','unknown','unknown',True)])
def test_native_control_and_process_finality_keep_distinct_outcomes(manager,mode,outcome,state,blocked):
    jobs,endpoint,_target,review,current=manager;item,request=review();transport=Transport(mode)
    jobs.start(request,1,endpoint,current,transport);value=finished(jobs,item,endpoint)
    assert value['state']==state and value['native_load_outcome']==outcome and transport.closed and transport.calls==1
    restarted=type(jobs)(jobs.path,jobs.root)
    assert restarted.start(request,1,endpoint,{},None)['state']==state and transport.calls==1
    other,_other_request=review(str(uuid.uuid4()))
    if blocked:
        with pytest.raises(BinlogArchiveError,match='unresolved'):restarted.claim_fence(jobs.load(other['job_id'],1,other['endpoint_id']))
    else:restarted.claim_fence(jobs.load(other['job_id'],1,other['endpoint_id']))


@pytest.mark.parametrize('mode,expected',[('cancel-before','cancelled'),('cancel-after','unknown')])
def test_cancellation_does_not_infer_rollback_after_dispatch(manager,mode,expected):
    jobs,endpoint,_target,review,current=manager;item,request=review();transport=Transport(mode)
    jobs.start(request,1,endpoint,current,transport);assert transport.entered.wait(3)
    other=type(jobs)(jobs.path,jobs.root);other.cancel(item['job_id'],1,endpoint)
    value=finished(jobs,item,endpoint)
    assert value['state']==expected and value['native_process_termination_confirmed'] is True and transport.closed
    assert 'stdout' not in value['tool_observation'] and 'stderr' not in value['tool_observation']


def test_unknown_reconciliation_never_relabels_return_or_replays_and_ack_is_exact(manager):
    jobs,endpoint,target,review,current=manager;item,request=review();transport=Transport('lost-ack')
    jobs.start(request,1,endpoint,current,transport);finished(jobs,item,endpoint)
    record=jobs.load(item['job_id'],1,endpoint);observation={'all_archive_gtids_present':1,'native_lock_free':True}
    reconciled=jobs.reconcile(record,observation)
    assert reconciled['native_load_outcome']=='unknown' and reconciled['state']=='unknown'
    acknowledgement={'target_confirmation':target.get('server_uuid',target.get('server_uid')),'observation_digest':digest(observation)}
    with pytest.raises(BinlogArchiveError,match='exact'):jobs.acknowledge(record,{**observation,'all_archive_gtids_present':0},acknowledgement)
    with pytest.raises(BinlogArchiveError,match='termination'):jobs.acknowledge(record,{**observation,'native_lock_free':False},{**acknowledgement,'observation_digest':digest({**observation,'native_lock_free':False})})
    acknowledged=jobs.acknowledge(record,observation,acknowledgement)
    assert acknowledged['target_state_acknowledged_at'] and acknowledged['native_load_outcome']=='unknown'
    assert jobs.start(request,1,endpoint,{},None)['native_load_outcome']=='unknown' and transport.calls==1
    next_item,_next_request=review();jobs.claim_fence(jobs.load(next_item['job_id'],1,endpoint))


@pytest.mark.parametrize('client_complete',[False,True])
def test_raw_reconciliation_requires_both_original_utilities_and_preserves_unknown(tmp_path,monkeypatch,client_complete):
    jobs=MySQLBinlogReplayJobs(tmp_path/'jobs',tmp_path/'replays');endpoint=str(uuid.uuid4());target=str(uuid.uuid4())
    value=jobs.review(1,endpoint,options({'target_confirmation':target}),{'identity':{'server_uuid':target},'state':{
        'target':{},'input_reference':{'family':'raw','server_id':7,'endpoint_id':endpoint,'job_id':str(uuid.uuid4()),'artifact_digest':'bytes','summary':{'total_bytes':'1'}}}},
        'configuration',{'execution_host':{'hostname':'owned-test'},'decoder':{'executable_sha256':'decoder'},'client':{'executable_sha256':'client'}})
    record=jobs.load(value['job_id'],1,endpoint);jobs.claim_fence(record)
    jobs.update(record,state='unknown',native_load_outcome='unknown',native_load_may_have_dispatched=True,native_process_termination_confirmed=False)
    for name in ('raw-replay-decoder','raw-replay-client'):jobs.progress(record,{'durable_tool':{'name':name,'nonce':name}})
    calls=[]
    def observe(directory,reference,expected):
        calls.append((reference['name'],expected));complete=client_complete or reference['name']=='raw-replay-decoder'
        return {'complete':complete,'cleanup_confirmed':complete,'credential_file_cleanup_confirmed':complete,'input_file_cleanup_confirmed':complete}
    monkeypatch.setattr('pgadmin.cdeadmin.sdk.durable_tool.observe',observe)
    result=jobs.reconcile(jobs.load(value['job_id'],1,endpoint),{'native_lock_free':True})
    assert result['native_load_outcome']=='unknown' and result['state']=='unknown'
    assert result['native_process_termination_confirmed'] is client_complete
    assert set(calls)=={('raw-replay-decoder','decoder'),('raw-replay-client','client')}
    assert result['utility_cancellation_available'] is (not client_complete)
    other=jobs.review(1,str(uuid.uuid4()),options({'target_confirmation':target}),{'identity':{'server_uuid':target},'state':{
        'target':{},'input_reference':record['source_state']['input_reference']}},'configuration',record['program'])
    with pytest.raises(BinlogArchiveError,match='unresolved'):jobs.claim_fence(jobs.load(other['job_id'],1,other['endpoint_id']))


@pytest.mark.parametrize('manager',['mysql'],indirect=True)
def test_shell_original_guardian_reconciles_without_changing_unknown_database_outcome(manager,monkeypatch):
    jobs,endpoint,_target,review,_current=manager;item,_request=review();record=jobs.load(item['job_id'],1,endpoint)
    jobs.update(record,state='unknown',native_load_outcome='unknown',native_load_may_have_dispatched=True,native_process_termination_confirmed=False)
    reference={'name':'shell-replay-client','nonce':'original-shell'};jobs.progress(record,{'durable_tool':reference})
    calls=[]
    def observe(directory,selected,expected):
        calls.append((selected,expected));return {'complete':True,'cleanup_confirmed':True,'credential_file_cleanup_confirmed':True}
    monkeypatch.setattr('pgadmin.cdeadmin.sdk.durable_tool.observe',observe)
    result=jobs.reconcile(jobs.load(item['job_id'],1,endpoint),{'native_lock_free':False})
    assert result['native_load_outcome']=='unknown' and result['native_process_termination_confirmed'] is True
    assert result['staged_input_cleanup']['complete'] and not result['utility_cancellation_available']
    assert calls==[(reference,'native')]
    with pytest.raises(BinlogArchiveError,match='replaced'):
        jobs.progress(record,{'durable_tool':{**reference,'nonce':'another-invocation'}})


@pytest.mark.parametrize('manager',['mysql'],indirect=True)
def test_raw_utility_reference_cannot_be_replaced_after_admission(manager):
    jobs,endpoint,_target,review,_current=manager
    item,_request=review();record=jobs.load(item['job_id'],1,endpoint)
    record['source_state']['input_reference']['family']='raw';jobs.update(record,source_state=record['source_state'])
    reference={'name':'raw-replay-client','nonce':'original'}
    jobs.progress(record,{'durable_tool':reference})
    with pytest.raises(BinlogArchiveError,match='replaced'):jobs.progress(record,{'durable_tool':{**reference,'nonce':'replacement'}})


@pytest.mark.parametrize('manager',['mysql'],indirect=True)
def test_lost_decoder_observer_before_sql_dispatch_does_not_infer_process_exit(manager,monkeypatch):
    jobs,endpoint,_target,review,current=manager;item,request=review();record=jobs.load(item['job_id'],1,endpoint)
    record['source_state']['input_reference']['family']='raw'
    record['program'].update(decoder={'executable_sha256':'decoder'},client={'executable_sha256':'client'})
    item=jobs.review(1,endpoint,record['options'],{'identity':record['source'],'state':record['source_state']},'configuration',record['program'])
    request={'job_id':item['job_id'],'review_digest':item['review_digest'],'confirmed':True}
    current={**current,'program':record['program']}
    class DecoderObserver(Transport):
        def execute(self,record,directory,cancel,progress,boundary):
            progress({'durable_tool':{'name':'raw-replay-decoder','nonce':'original'}})
            raise SystemExit('Original decoder observer exited before SQL dispatch')
    calls=[]
    def observe(directory,reference,expected):
        calls.append((reference['name'],expected));return {'complete':False,'cleanup_confirmed':False}
    monkeypatch.setattr('pgadmin.cdeadmin.sdk.durable_tool.observe',observe)
    monkeypatch.setattr('pgadmin.cdeadmin.sdk.durable_tool.cancel',observe)
    jobs.start(request,1,endpoint,current,DecoderObserver('returned'))
    result=finished(jobs,item,endpoint)
    assert result['native_load_outcome']=='not_dispatched' and result['state']=='not_dispatched'
    assert result['native_process_termination_confirmed'] is False and result['utility_cancellation_available']
    jobs.cancel(item['job_id'],1,endpoint)
    assert len(calls)==2 and set(calls)=={('raw-replay-decoder','decoder')}


def test_active_native_worker_cannot_be_acknowledged_or_superseded(manager):
    jobs,endpoint,target,review,current=manager;item,request=review();transport=Transport('cancel-after')
    jobs.start(request,1,endpoint,current,transport);assert transport.entered.wait(3)
    record=jobs.load(item['job_id'],1,endpoint);observation={'native_lock_free':True}
    with pytest.raises(BinlogArchiveError,match='active'):jobs.acknowledge(record,observation,{'target_confirmation':target.get('server_uuid',target.get('server_uid')),'observation_digest':digest(observation)})
    other,other_request=review(str(uuid.uuid4()));other_transport=Transport('returned')
    with pytest.raises(BinlogArchiveError,match='unresolved'):jobs.start(other_request,1,other['endpoint_id'],current,other_transport)
    assert other_transport.closed and other_transport.calls==0
    jobs.cancel(item['job_id'],1,endpoint);finished(jobs,item,endpoint)


def test_stale_review_releases_undispatched_fence_and_credentials(manager):
    jobs,endpoint,_target,review,current=manager;item,request=review();transport=Transport('returned')
    with pytest.raises(BinlogArchiveError,match='changed'):jobs.start(request,1,endpoint,{**current,'configuration':'changed'},transport)
    assert transport.closed and transport.calls==0 and jobs.get(item['job_id'],1,endpoint)['state']=='reviewed'
    other,_request=review();jobs.claim_fence(jobs.load(other['job_id'],1,endpoint))


def test_dead_worker_keeps_target_fenced_without_automatic_process_finality(manager):
    jobs,endpoint,_target,review,_current=manager;item,request=review();record=jobs.load(item['job_id'],1,endpoint)
    jobs.claim_fence(record);jobs.update(record,state='active',worker_identity=[999999999,0],native_load_may_have_dispatched=True)
    assert jobs.get(item['job_id'],1,endpoint)['state']=='unknown'
    assert jobs.start(request,1,endpoint,{},None)['native_process_termination_confirmed'] is False
    next_item,_request=review()
    with pytest.raises(BinlogArchiveError):jobs.claim_fence(jobs.load(next_item['job_id'],1,endpoint))


def test_cancelled_unadmitted_review_releases_its_stale_target_claim_after_restart(manager):
    jobs,endpoint,_target,review,current=manager;item,request=review()
    jobs.claim_fence(jobs.load(item['job_id'],1,endpoint))
    restarted=type(jobs)(jobs.path,jobs.root)
    assert restarted.cancel(item['job_id'],1,endpoint)['state']=='cancelled'
    other,_other_request=review();other_record=jobs.load(other['job_id'],1,endpoint)
    jobs.claim_fence(other_record)
    transport=Transport('returned')
    assert jobs.start(request,1,endpoint,current,transport)['state']=='cancelled'
    assert transport.calls==0 and transport.closed
    with jobs.fence_store(jobs.target_identity(other_record)) as store:
        assert store.read()['replay_fence']['job_id']==other['job_id']


def test_cancellation_between_target_claim_and_atomic_admission_never_dispatches(manager,monkeypatch):
    jobs,endpoint,_target,review,current=manager;_item,request=review()
    claim=jobs.claim_fence
    def cancel_after_claim(record):
        claim(record)
        jobs.cancel(record['job_id'],1,endpoint)
    monkeypatch.setattr(jobs,'claim_fence',cancel_after_claim)
    transport=Transport('returned')
    assert jobs.start(request,1,endpoint,current,transport)['state']=='cancelled'
    assert transport.calls==0 and transport.closed
    other,_other_request=review();claim(jobs.load(other['job_id'],1,endpoint))


@pytest.mark.parametrize('marker',['worker_identity','started_at','native_load_may_have_dispatched','native_checks_may_have_started','durable_tool','server_lock_owner'])
def test_cancel_never_retires_a_claim_with_admission_or_native_ownership_evidence(manager,marker):
    jobs,endpoint,_target,review,_current=manager;item,_request=review();record=jobs.load(item['job_id'],1,endpoint)
    jobs.claim_fence(record)
    # Even false/empty marker values cannot turn a post-admission receipt into
    # a never-admitted review. Native cleanup still needs its original path.
    jobs.update(record,state='cancelled',**{marker:False})
    jobs.cancel(item['job_id'],1,endpoint)
    other,_other_request=review()
    with pytest.raises(BinlogArchiveError):jobs.claim_fence(jobs.load(other['job_id'],1,endpoint))


@pytest.mark.parametrize('extra',[{'stop_mode':'before','stop_gtid':'arbitrary'}, {'stop_mode':'all','stop_gtid':'unexpected'},
    {'stop_mode':'after','stop_gtid':'00000000-0000-0000-0000-000000000001:9223372036854775808'},
    {'stop_mode':'before','stop_gtid':'00000000-0000-0000-0000-000000000001:9tag:1'}, {'timeout_seconds':True}, {'path':'/unregistered'}])
def test_native_replay_options_reject_ambiguous_or_unscoped_requests(extra):
    with pytest.raises(BinlogArchiveError):options({'target_confirmation':str(uuid.uuid4()),**extra})


def test_native_tagged_gtid_and_int64_boundary_remain_exact():
    target=str(uuid.uuid4());gtid=str(uuid.uuid4())+':Native_Tag:9223372036854775807'
    assert options({'target_confirmation':target,'stop_mode':'after','stop_gtid':gtid})['stop_gtid']==gtid


def test_unavailable_native_credentials_are_an_admission_refusal(monkeypatch):
    from pgadmin.cdeadmin.sdk.relational import RelationalCredentialError
    from pgadmin.cdeadmin.workspace import mysql_binlog_replay_service
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceError,ProviderWorkspaceService
    def refuse(*_args):raise RelationalCredentialError('Private native diagnostic')
    monkeypatch.setattr(mysql_binlog_replay_service,'action',refuse)
    with pytest.raises(ProviderWorkspaceError,match='binding is unavailable') as caught:
        ProviderWorkspaceService.mysql_binlog_replay(object(),object(),'review',{})
    assert 'Private' not in str(caught.value)
