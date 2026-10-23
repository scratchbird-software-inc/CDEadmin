"""Policy graph admission and durable batch execution over real private files."""
from copy import deepcopy
from pathlib import Path
import socket
import threading
from types import SimpleNamespace
import uuid

import pytest
from pgadmin.cdeadmin.workspace import mysql_physical_batch_retention as batch
from pgadmin.cdeadmin.workspace import mysql_physical_retention as single
from pgadmin.cdeadmin.workspace import mysql_physical_service as physical
from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_worker as worker


@pytest.fixture
def setup(tmp_path,monkeypatch):
    jobs=physical.PhysicalJobs(tmp_path/'jobs',tmp_path/'receipts');endpoint=SimpleNamespace(id=str(uuid.uuid4()))
    service=SimpleNamespace(_semantic_lock=threading.RLock())
    root=tmp_path/'host';root.mkdir(mode=0o700);source=tmp_path/'source';source.mkdir()
    binding={'server_uuid':str(uuid.uuid4()),'hostname':socket.gethostname(),'datadir':str(source)}
    peer={'fingerprint':'owned-test-peer'}
    class Transport:
        def __init__(self,*_args):pass
        def connect(self):return peer
        def request(self,request):return worker.dispatch(request)
        def close(self):pass
    monkeypatch.setattr(batch.native,'Transport',Transport)
    monkeypatch.setattr(batch,'registered_jobs',lambda *_args:set())
    monkeypatch.setattr(batch.MySQLMonitoringHost,'_configuration',staticmethod(lambda _server:{}))
    monkeypatch.setattr('pgadmin.cdeadmin.workspace.mysql_host_service.credentials',lambda value:value)
    def create(phase='backup',parent=None,**changes):
        options={'phase':phase,'input_job_id':parent,'connection':{'host':'owned'},'workspace':str(root),
            'executable':'/usr/bin/xtrabackup','mysql':'/usr/bin/mysql','sql_host':'127.0.0.1','sql_port':3306,
            'parallel':2,'memory_bytes':268435456,'timeout_seconds':600}
        reviewed=jobs.review(1,endpoint.id,options,{'identity':{'server_uuid':binding['server_uuid']},
            'state':{'remote_review':{},'host_binding':binding}},batch.digest({}),{'execution_host':{}})
        record=jobs.load(reviewed['job_id'],1,endpoint.id)
        remote={'state':'native_returned','process_termination_confirmed':True,'credential_cleanup_confirmed':True,
            'supervisor_finished':True,'return_code':0,'artifact':{'files':1,'bytes':4}}
        directory=root/record['job_id'];directory.mkdir(mode=0o700)
        (directory/'artifact').mkdir();(directory/'artifact'/'data.ibd').write_bytes(b'data')
        if phase=='backup':
            (directory/'artifact'/'xtrabackup_info').write_text('server_version = 9.7.0\ntool_version = '+worker.VERSION+'\npartial = N\nincremental = N\ncompressed = N\nencrypted = N\nuuid = '+str(uuid.uuid4()))
            (directory/'artifact'/'xtrabackup_checkpoints').write_text('backup_type = full-backuped\nfrom_lsn = 0\nto_lsn = 100\nlast_lsn = 100')
            worker.host.save(directory/'artifact'/'xtrabackup_tablespaces',{'version':3,'external_tablespaces':[]})
            (directory/'artifact'/'xtrabackup_binlog_info').write_text('binlog.000001\t123')
            remote['artifact']=worker.artifact(directory/'artifact',prepared=False)
        jobs.update(record,**{'state':'native_returned','remote_observation':worker.public(remote),'retention_age_anchor':100,**changes})
        record=jobs.load(record['job_id'],1,endpoint.id)
        worker.host.save(directory/'request.json',physical.remote_request(record,'start'))
        worker.host.save(directory/'result.json',{**remote,'input_digest':record['review_digest']})
        return record
    def records():return batch.inventory(jobs,1,endpoint.id)
    def call(operation,request):return batch.action(service,None,jobs,1,endpoint,'retention_batch_'+operation,request)
    def review(anchor,**policy):return call('review',{'scope_job_id':anchor['job_id'],'policy':{'retention_days':0,'keep_latest':1,**policy},'credentials':{}})
    def step(ticket,operation='advance'):
        return call(operation,{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],
            'confirmed':True,'batch_confirmation':ticket['job_id'],'credentials':{}})
    return SimpleNamespace(**locals())


def test_latest_full_chains_age_pins_and_all_inputs_are_preserved(setup):
    s=setup;old=s.create();prepared=s.create('prepare',old['job_id']);young=s.create('copy_back',prepared['job_id'],retention_pinned=True)
    newest=s.create();latest_child=s.create('prepare',newest['job_id'])
    value=batch.plan(s.records(),old,{'retention_days':0,'keep_latest':1},200)
    assert value['job_ids']==[] and value['retained_full_backup_ids']==[newest['job_id']]
    record=s.jobs.load(young['job_id'],1,s.endpoint.id);s.jobs.update(record,retention_pinned=False,retention_age_anchor=201)
    assert batch.plan(s.records(),old,{'retention_days':0,'keep_latest':1},200)['job_ids']==[]
    s.jobs.update(record,retention_age_anchor=100)
    value=batch.plan(s.records(),old,{'retention_days':0,'keep_latest':1},200)
    assert value['job_ids']==[young['job_id'],prepared['job_id'],old['job_id']]
    assert latest_child['job_id'] not in value['job_ids']


@pytest.mark.parametrize('change',[
    {'retention_pinned':True},{'retention_batch_id':'other'},{'artifact_removal':{'state':'unknown'}},
    {'retention_review_job_id':'manual-review'},{'remote_observation':{}},{'retention_age_anchor':None}])
def test_protected_leaf_preserves_its_entire_input_chain(setup,change):
    s=setup;old=s.create();s.create('prepare',old['job_id'],**change);s.create()
    assert not batch.plan(s.records(),old,{'retention_days':0,'keep_latest':1},200)['job_ids']


def test_registration_and_unverified_full_backups_do_not_lower_the_floor(setup):
    s=setup;old=s.create();child=s.create('prepare',old['job_id']);s.create(remote_observation={})
    assert not batch.plan(s.records(),old,{'retention_days':0,'keep_latest':2},200)['job_ids']
    s.create()
    assert not batch.plan(s.records(),old,{'retention_days':0,'keep_latest':1},200,registered=[child['job_id']])['job_ids']


def test_graph_missing_cross_scope_and_cycles_refuse_the_entire_plan(setup):
    s=setup;old=s.create();child=s.create('prepare',old['job_id']);s.create()
    records=s.records();records[child['job_id']]['options']['workspace']='/other-host-scope'
    with pytest.raises(batch.native.HostError,match='another native scope'):batch.plan(records,old,{'retention_days':0,'keep_latest':1},200)
    records=s.records();records[old['job_id']]['options']['input_job_id']=child['job_id']
    with pytest.raises(batch.native.HostError,match='cycle'):batch.plan(records,old,{'retention_days':0,'keep_latest':1},200)
    records=s.records();records.pop(old['job_id'])
    with pytest.raises(batch.native.HostError,match='missing'):batch.plan(records,child,{'retention_days':0,'keep_latest':1},200)


def test_age_starts_at_completion_observation_and_survives_later_polls(setup):
    s=setup;old=s.create();record=s.jobs.load(old['job_id'],1,s.endpoint.id)
    with s.jobs.store(record['job_id']) as store:
        store.change(lambda value:value['mysql_binlog_jobs'][record['job_id']].pop('retention_age_anchor'))
    s.jobs.update(record,observed_at=900)
    records,_=batch.records_for_plan(s.service,s.jobs,1,s.endpoint.id)
    assert records[record['job_id']]['retention_age_anchor']==900
    s.jobs.update(record,observed_at=1000)
    records,_=batch.records_for_plan(s.service,s.jobs,1,s.endpoint.id)
    assert records[record['job_id']]['retention_age_anchor']==900


def test_cancelled_before_dispatch_children_have_no_artifact_dependency(setup):
    s=setup;old=s.create();child=s.create('prepare',old['job_id']);s.create()
    s.jobs.update(child,state='cancelled',native_may_have_dispatched=False)
    assert batch.plan(s.records(),old,{'retention_days':0,'keep_latest':1},200)['job_ids']==[old['job_id']]


@pytest.mark.parametrize('value',[None,{}, {'retention_days':True,'keep_latest':1}, {'retention_days':-1,'keep_latest':1},
    {'retention_days':0,'keep_latest':0},{'retention_days':0,'keep_latest':1001}])
def test_invalid_policy_never_creates_a_review(value):
    with pytest.raises(batch.native.HostError):batch.policy(value)


def test_batch_fixed_plan_leaf_first_restart_and_original_receipt_preservation(setup):
    s=setup;old=s.create();prepared=s.create('prepare',old['job_id']);newest=s.create()
    original=(s.root/old['job_id']/'result.json').read_bytes();ticket=s.review(old)
    assert ticket['plan']['job_ids']==[prepared['job_id'],old['job_id']]
    assert 'credentials' not in str(ticket) and ticket['automatic_retry'] is False
    with pytest.raises(batch.native.HostError,match='owning'):
        single.action(s.service,None,s.jobs,1,s.endpoint,'retention_start',{'job_id':ticket['items'][0]['retention_job_id'],
            'review_digest':ticket['items'][0]['retention_digest'],'confirmed':True,'job_confirmation':prepared['job_id'],'credentials':{}})
    first=s.step(ticket);assert first['state']=='paused' and first['next_index']==1
    assert not (s.root/prepared['job_id']/'artifact').exists() and (s.root/old['job_id']/'artifact').exists()
    delattr(s.service,'mysql_physical_batch_jobs');delattr(s.service,'mysql_physical_retention_jobs')
    assert s.call('status',{'job_id':ticket['job_id']})['next_index']==1
    assert s.step(ticket)['state']=='completed'
    assert (s.root/newest['job_id']/'artifact'/'data.ibd').read_bytes()==b'data'
    assert (s.root/old['job_id']/'result.json').read_bytes()==original


def test_stale_pin_or_full_chain_floor_blocks_every_next_deletion(setup):
    s=setup;old=s.create();newest=s.create();ticket=s.review(old)
    s.jobs.update(newest,artifact_removed=True)
    with pytest.raises(batch.native.HostError,match='floor'):s.step(ticket)
    assert (s.root/old['job_id']/'artifact').exists()
    s.jobs.update(newest,artifact_removed=False);s.jobs.update(old,retention_pinned=True)
    with pytest.raises(batch.native.HostError,match='eligibility'):s.step(ticket)


def test_unknown_reply_requires_independent_observation_and_never_auto_repeats(setup,monkeypatch):
    s=setup;old=s.create();s.create();ticket=s.review(old);original=s.Transport.request
    def lost(channel,request):
        value=original(channel,request)
        if request['action']=='retention_remove':raise ConnectionError('owned lost reply')
        return value
    with monkeypatch.context() as patch:
        patch.setattr(s.Transport,'request',lost)
        with pytest.raises(ConnectionError):s.step(ticket)
    assert s.call('status',{'job_id':ticket['job_id']})['state']=='interrupted'
    with pytest.raises(batch.native.HostError,match='inspect'):s.step(ticket,'resume')
    assert s.call('reconcile',{'job_id':ticket['job_id'],'credentials':{}})['state']=='completed'
    assert s.jobs.get(old['job_id'],1,s.endpoint.id)['state']=='native_returned'


def test_cancel_invalidates_all_unused_previews_and_is_idempotent(setup):
    s=setup;old=s.create();child=s.create('prepare',old['job_id']);s.create();ticket=s.review(old)
    assert s.step(ticket,'cancel')['state']=='cancelled'
    assert s.step(ticket,'cancel')['state']=='cancelled'
    for record in (old,child):
        assert not s.jobs.load(record['job_id'],1,s.endpoint.id).get('retention_batch_id')
        assert (s.root/record['job_id']/'artifact').is_dir()
    assert s.step(ticket)['state']=='cancelled'


def test_partial_removal_can_finish_only_original_item_after_batch_cancel(setup,monkeypatch):
    s=setup;old=s.create();child=s.create('prepare',old['job_id']);s.create();ticket=s.review(old)
    from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_retention_worker as host
    def interrupted(_path):raise OSError('owned filesystem interruption')
    interrupted.avoids_symlink_attacks=True
    with monkeypatch.context() as patch:
        patch.setattr(host.shutil,'rmtree',interrupted)
        with pytest.raises(OSError):s.step(ticket)
    assert s.step(ticket,'cancel')['state']=='interrupted'
    assert s.call('reconcile',{'job_id':ticket['job_id'],'credentials':{}})['state']=='interrupted'
    assert s.step(ticket,'resume')['state']=='cancelling'
    assert (s.root/old['job_id']/'artifact').is_dir() and not (s.root/child['job_id']/'artifact').exists()
    assert s.step(ticket,'cancel')['state']=='cancelled'


def test_remote_batch_preview_cannot_bypass_parent_first_removal(setup):
    s=setup;old=s.create();child=s.create('prepare',old['job_id']);s.create()
    request={**physical.remote_request(old,'retention_inspect'),'retention_id':str(uuid.uuid4()),'planned_job_ids':[child['job_id']]}
    reviewed=worker.dispatch(request)
    from pgadmin.cdeadmin.providers.mysql_family.mysql_physical_retention_worker import Refused
    with pytest.raises(Refused,match='dependent'):
        worker.dispatch({**request,'action':'retention_remove','confirmed':True,'retention_review':reviewed})
    assert (s.root/old['job_id']/'artifact').is_dir()


def test_retained_floor_files_are_reverified_under_host_admission_before_each_removal(setup):
    s=setup;old=s.create();newest=s.create();ticket=s.review(old)
    path=s.root/newest['job_id']/'artifact'/'data.ibd';original=path.read_bytes();path.write_bytes(b'corrupted retained backup')
    from pgadmin.cdeadmin.providers.mysql_family.mysql_physical_retention_worker import Refused
    with pytest.raises(Refused,match='content changed'):s.step(ticket)
    assert (s.root/old['job_id']/'artifact').exists() and not (s.root/old['job_id']/'retention-intent.json').exists()
    path.write_bytes(original)
    assert s.call('reconcile',{'job_id':ticket['job_id'],'credentials':{}})['state']=='interrupted'
    assert s.step(ticket,'resume')['state']=='completed'


def test_fixed_batch_limit_preserves_child_before_input_order(setup):
    s=setup;old=s.create();newest=s.create();records=s.records();parent=old['job_id'];chain=[]
    for created in range(105):
        record=deepcopy(old);record.update(job_id=str(uuid.uuid4()),created_at=created)
        record['options'].update(phase='prepare',input_job_id=parent)
        records[record['job_id']]=record;chain.append(record['job_id']);parent=record['job_id']
    value=batch.plan(records,old,{'retention_days':0,'keep_latest':1},200)
    assert value['job_ids']==list(reversed(chain))[:100] and value['eligible_count']==106
    assert value['retained_full_backup_ids']==[newest['job_id']]


def test_interrupted_application_cannot_advance_a_running_step_or_silently_add_new_jobs(setup):
    s=setup;old=s.create();s.create();ticket=s.review(old)
    batches=batch.manager(s.service,s.jobs);record=batches.load(ticket['job_id'],1,s.endpoint.id)
    batches.update(record,state='running',needs_observation=True)
    with pytest.raises(batch.native.HostError,match='inspect'):s.step(ticket)
    assert (s.root/old['job_id']/'artifact').exists()
    assert s.call('reconcile',{'job_id':ticket['job_id'],'credentials':{}})['state']=='interrupted'
    added=s.create()
    assert s.step(ticket,'resume')['removed_job_ids']==[old['job_id']]
    assert (s.root/added['job_id']/'artifact').is_dir()


def test_cancel_reports_already_removed_files_after_a_lost_original_reply(setup,monkeypatch):
    s=setup;old=s.create();s.create();ticket=s.review(old);original=s.Transport.request
    def lost(channel,request):
        value=original(channel,request)
        if request['action']=='retention_remove':raise ConnectionError('owned lost reply')
        return value
    with monkeypatch.context() as patch:
        patch.setattr(s.Transport,'request',lost)
        with pytest.raises(ConnectionError):s.step(ticket)
    observed=s.step(ticket,'cancel')
    assert observed['state']=='cancelled' and observed['removed_job_ids']==[old['job_id']]
    assert observed['cancellation_observations'][old['job_id']]['removal_confirmed']
