"""Owned private-input deletion is reviewed, serialized and never redispatched."""
from pathlib import Path
import socket
import threading
import time
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from pgadmin.cdeadmin.workspace.continuous_binlog_cleanup import CleanupJobs,CleanupTransport,postimages
from pgadmin.cdeadmin.workspace.continuous_binlog_service import ReceiverJobs
from pgadmin.cdeadmin.workspace.continuous_binlog_tails import file_claim
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import MySQLBinlogJobs


@pytest.fixture
def owned(tmp_path):
    jobs=ReceiverJobs(tmp_path/'receivers.json',tmp_path/'receivers');archives=MySQLBinlogJobs(tmp_path/'archives.json',tmp_path/'archives')
    cleanups=CleanupJobs(tmp_path/'cleanups.json',tmp_path/'cleanups');endpoint=str(uuid.uuid4())
    source={'server_uuid':'owned'};program={'executable_sha256':'a'*64,'execution_host':{'hostname':socket.gethostname()}}
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
