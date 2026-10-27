"""Owned private-input deletion is reviewed, serialized and never redispatched."""
from pathlib import Path
import os
import socket
import threading
import time
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from pgadmin.cdeadmin.workspace.continuous_binlog_cleanup import CleanupJobs,CleanupTransport,postimages,reconcile
from pgadmin.cdeadmin.workspace.continuous_binlog_service import ReceiverJobs
from pgadmin.cdeadmin.workspace.continuous_binlog_tails import file_claim
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import MySQLBinlogJobs


@pytest.fixture
def owned(tmp_path):
    jobs=ReceiverJobs(tmp_path/'receivers.json',tmp_path/'receivers');archives=MySQLBinlogJobs(tmp_path/'archives.json',tmp_path/'archives')
    cleanups=CleanupJobs(tmp_path/'cleanups.json',tmp_path/'cleanups');endpoint=str(uuid.uuid4())
    source={'server_uuid':'owned'};program={'executable_sha256':'a'*64,'execution_host':{'hostname':socket.gethostname(),'platform':os.name}}
    review=jobs.review(1,endpoint,{}, {'identity':source,'state':{}},'owned',program,{'writer_scope_index':1})
    parent=jobs.load(review['job_id'],1,endpoint);jobs.update(parent,state='failed',native_process_termination_confirmed=True)
    receiving=jobs.directory(parent)/'receiving';receiving.mkdir()
    for name in ('native.000001','native.000002'):(receiving/name).write_bytes(b'private\x00\xff')
    neighbor=tmp_path/'retained-archive';neighbor.write_bytes(b'independent archive sentinel')
    selected={'log_names':['native.000001','native.000002']}
    reviewed=cleanups.review(1,endpoint,selected,{'identity':source,'state':{}},'owned',program,
        {'receiver_job_id':parent['job_id'],'file_postimages':postimages(jobs.directory(parent),selected['log_names'])})
    record=cleanups.load(reviewed['job_id'],1,endpoint)
    try:yield jobs,archives,cleanups,parent,record,receiving,neighbor
    finally:cleanups.close();archives.close();jobs.close()


def test_removal_preserves_neighbor_and_parent_and_records_each_acknowledgement(owned):
    jobs,archives,_cleanups,parent,record,receiving,neighbor=owned;events=[]
    result=CleanupTransport(jobs,archives,parent).execute(record,None,threading.Event(),events.append)
    assert result['removed_files']==record['options']['log_names'] and result['removed_bytes']=='18'
    assert not list(receiving.iterdir()) and neighbor.read_bytes()==b'independent archive sentinel'
    assert result['archives_removed'] is False and result['database_recovery_verified'] is False
    assert [event['removal_acknowledged'] for event in events]==[False,True,False,True]
    assert jobs.get(parent['job_id'],1,parent['endpoint_id'])['state']=='failed'


def test_all_postimages_are_checked_before_the_first_removal(owned):
    jobs,archives,_cleanups,parent,record,receiving,_neighbor=owned
    (receiving/'native.000002').write_bytes(b'changed')
    with pytest.raises(BinlogArchiveError,match='postimages changed'):
        CleanupTransport(jobs,archives,parent).execute(record,None,threading.Event(),lambda _event:None)
    assert (receiving/'native.000001').exists() and (receiving/'native.000002').read_bytes()==b'changed'


def test_claim_contention_is_cancellable_and_never_unlinks_a_readers_inputs(owned):
    jobs,archives,_cleanups,parent,record,receiving,_neighbor=owned;cancel=threading.Event();errors=[]
    def worker():
        try:CleanupTransport(jobs,archives,parent).execute(record,None,cancel,lambda _event:None)
        except BaseException as error:errors.append(error)
    with file_claim(jobs.directory(parent)):
        with pytest.raises(BinlogArchiveError,match='Another operation'):
            with file_claim(jobs.directory(parent)):pass
        thread=threading.Thread(target=worker);thread.start();cancel.set();thread.join(timeout=2)
        assert not thread.is_alive() and len(errors)==1 and isinstance(errors[0],InterruptedError)
        assert len(list(receiving.iterdir()))==2


def test_cancel_between_files_preserves_the_acknowledged_partial_result(owned):
    jobs,archives,_cleanups,parent,record,receiving,_neighbor=owned;cancel=threading.Event();events=[]
    def progress(event):
        events.append(event)
        if event['removal_acknowledged']:cancel.set()
    with pytest.raises(InterruptedError):CleanupTransport(jobs,archives,parent).execute(record,None,cancel,progress)
    assert not (receiving/'native.000001').exists() and (receiving/'native.000002').exists()
    assert events[-1]['removed_files']==['native.000001']


@pytest.mark.parametrize('fault',['owner','endpoint','unconfirmed'])
def test_unconfirmed_or_unowned_cleanup_never_dispatches(owned,fault):
    jobs,archives,cleanups,parent,record,receiving,_neighbor=owned
    request={'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':fault!='unconfirmed'}
    with pytest.raises(BinlogArchiveError):
        cleanups.start(request,2 if fault=='owner' else 1,str(uuid.uuid4()) if fault=='endpoint' else record['endpoint_id'],
            {key:record[key] for key in ('source','configuration','program')},CleanupTransport(jobs,archives,parent))
    assert len(list(receiving.iterdir()))==2


@pytest.mark.parametrize('lost_ack',[False,True])
def test_durable_worker_once_only_dispatch_and_lost_acknowledgement(owned,monkeypatch,lost_ack):
    jobs,archives,cleanups,parent,record,receiving,neighbor=owned
    if lost_ack:
        update=cleanups.update
        def fail_ack(current,**values):
            if values.get('progress',{}).get('removal_acknowledged'):raise OSError('owned receipt fault')
            return update(current,**values)
        monkeypatch.setattr(cleanups,'update',fail_ack)
    request={'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True}
    cleanups.start(request,1,record['endpoint_id'],{key:record[key] for key in ('source','configuration','program')},CleanupTransport(jobs,archives,parent))
    deadline=time.monotonic()+5
    while True:
        receipt=cleanups.get(record['job_id'],1,record['endpoint_id'])
        if receipt['state'] not in {'active','dispatching'}:break
        assert time.monotonic()<deadline;time.sleep(.01)
    assert receipt['state']==('unknown' if lost_ack else 'completed')
    if lost_ack:
        assert receipt['progress']['removal_intent_recorded'] and receipt['progress']['removal_acknowledged'] is False
        assert (receiving/'native.000002').exists() and receipt['local_removal_may_have_started']
    else:assert receipt['result']['removed_bytes']=='18'
    assert not (receiving/'native.000001').exists() and neighbor.exists()
    assert cleanups.start(request,1,record['endpoint_id'],{},None)['state']==receipt['state']


def interrupted(owned,*,absent=False):
    _jobs,_archives,cleanups,_parent,record,receiving,_neighbor=owned
    progress={'removed_files':[],'removed_bytes':'0','current_file':'native.000001',
        'removal_intent_recorded':True,'removal_acknowledged':False}
    cleanups.update(record,state='unknown',progress=progress)
    if absent:(receiving/'native.000001').unlink()
    return {'job_id':record['job_id'],'confirmed':True},progress


@pytest.mark.parametrize('absent',[False,True])
def test_offline_reconciliation_after_restart_only_handles_recorded_pending_file(owned,absent):
    jobs,archives,cleanups,parent,record,receiving,neighbor=owned
    request,original_progress=interrupted(owned,absent=absent)
    # A fresh manager simulates process restart. No source connection exists.
    restarted=CleanupJobs(cleanups.path,cleanups.root)
    try:receipt=reconcile(restarted,jobs,archives,request,1,record['endpoint_id'])
    finally:restarted.close()
    result=receipt['result']
    assert receipt['state']=='reconciled' and receipt['progress']==original_progress
    assert result['pending_file_absence_observed'] and result['pending_file_removed_during_reconciliation'] is (not absent)
    assert result['reconciliation_removed_bytes']==('0' if absent else '9')
    assert result['original_pending_unlink_acknowledged'] is False
    assert result['unattempted_files']==['native.000002'] and (receiving/'native.000002').read_bytes()==b'private\x00\xff'
    assert neighbor.read_bytes()==b'independent archive sentinel'
    assert jobs.get(parent['job_id'],1,record['endpoint_id'])['state']=='failed'
    # Idempotent observation must never delete a subsequently reappearing path.
    (receiving/'native.000001').write_bytes(b'new unrelated content')
    assert reconcile(cleanups,jobs,archives,request,1,record['endpoint_id'])==receipt
    assert (receiving/'native.000001').read_bytes()==b'new unrelated content'


def test_no_pending_intent_never_continues_unattempted_removals(owned):
    jobs,archives,cleanups,_parent,record,receiving,_neighbor=owned
    (receiving/'native.000001').unlink()
    progress={'removed_files':['native.000001'],'removed_bytes':'9','current_file':'native.000001',
        'removal_intent_recorded':True,'removal_acknowledged':True}
    cleanups.update(record,state='cancelled',progress=progress)
    receipt=reconcile(cleanups,jobs,archives,{'job_id':record['job_id'],'confirmed':True},1,record['endpoint_id'])
    assert receipt['progress']==progress and receipt['result']['pending_file'] is None
    assert receipt['result']['acknowledged_removed_bytes']=='9' and receipt['result']['unattempted_files']==['native.000002']
    assert (receiving/'native.000002').exists()


@pytest.mark.parametrize('fault',['owner','endpoint','confirmation','extra','changed','link','host','scope','source','review','progress','live','reviewed','completed','claim'])
def test_reconcile_refuses_changed_authority_postimages_and_live_workers(owned,fault):
    jobs,archives,cleanups,parent,record,receiving,neighbor=owned;request,_=interrupted(owned)
    owner=2 if fault=='owner' else 1;endpoint=str(uuid.uuid4()) if fault=='endpoint' else record['endpoint_id']
    if fault=='confirmation':request['confirmed']=False
    if fault=='extra':request['continue_unattempted']=True
    if fault=='changed':(receiving/'native.000001').write_bytes(b'replaced file')
    if fault=='link':
        (receiving/'native.000001').unlink();(receiving/'native.000001').symlink_to(neighbor)
    if fault in {'host','source','review'}:
        item=cleanups.load(record['job_id'],1,record['endpoint_id'])
        if fault=='host':item['program']['execution_host']['hostname']='different-host'
        elif fault=='source':item['source']={'server_uuid':'different'}
        else:item['options']['log_names']=['native.000002']
        from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import review_digest
        values={key:item[key] for key in ('program','source','options')}
        if fault!='review':values['review_digest']=review_digest(item)
        cleanups.update(record,**values)
    if fault=='scope':cleanups.update(record,execution_host={'filesystem_scope':str(cleanups.root/'different')})
    if fault=='progress':cleanups.update(record,progress={'removed_files':['unreviewed'],'removal_intent_recorded':False})
    if fault in {'reviewed','completed'}:cleanups.update(record,state=fault)
    if fault=='live':cleanups.workers[record['job_id']]=(threading.current_thread(),threading.Event())
    def attempt():return reconcile(cleanups,jobs,archives,request,owner,endpoint)
    try:
        with pytest.raises((BinlogArchiveError,OSError)):
            if fault=='claim':
                with file_claim(jobs.directory(parent)):attempt()
            else:attempt()
    finally:
        if fault=='live':cleanups.workers.pop(record['job_id'],None)
    assert (receiving/'native.000001').exists() and (receiving/'native.000002').exists() and neighbor.read_bytes()==b'independent archive sentinel'


def test_failure_after_reconciled_unlink_retries_observation_without_continuing(owned,monkeypatch):
    from pgadmin.cdeadmin.operations.store import JsonOperationStore
    jobs,archives,cleanups,_parent,record,receiving,_neighbor=owned;request,original_progress=interrupted(owned)
    original=JsonOperationStore.change;calls=0
    def fail_ack(store,callback):
        nonlocal calls
        calls+=1
        if calls==2:raise OSError('lost reconciliation acknowledgement')
        return original(store,callback)
    with monkeypatch.context() as context:
        context.setattr(JsonOperationStore,'change',fail_ack)
        with pytest.raises(OSError,match='lost reconciliation'):
            reconcile(cleanups,jobs,archives,request,1,record['endpoint_id'])
    assert not (receiving/'native.000001').exists() and (receiving/'native.000002').exists()
    pending=cleanups.get(record['job_id'],1,record['endpoint_id'])
    assert pending['state']=='unknown' and pending['reconciliation_attempt']['removal_acknowledged'] is False
    receipt=reconcile(cleanups,jobs,archives,request,1,record['endpoint_id'])
    assert receipt['state']=='reconciled' and receipt['progress']==original_progress
    assert receipt['result']['pending_file_absence_observed'] and receipt['result']['pending_file_removed_during_reconciliation'] is False
