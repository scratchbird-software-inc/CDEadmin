"""Receiver ownership, interruption fencing and native option preservation."""
from contextlib import contextmanager
import struct
import hashlib
import os
import threading
import time
import tracemalloc
import uuid

import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
from pgadmin.cdeadmin.providers.postgresql.continuity_transport import ContinuityTransport
from pgadmin.cdeadmin.workspace.postgresql_continuity_jobs import PostgreSQLContinuityJobs
from pgadmin.cdeadmin.workspace.postgresql_continuity_capture import options, arguments, archive_claim
from pgadmin.cdeadmin.operations.fileio import exclusive_file_lock


@pytest.mark.parametrize('value',[
    {'archive':'../outside'},{'archive':'ok','synchronous':True,'sync':False},
    {'archive':'ok','compression':'zstd'},{'archive':'ok','slot':'UPPER'},
    {'archive':'ok','end_lsn':'0/1; SELECT'},{'archive':'ok','timeout_seconds':True},
    {'archive':'ok','status_interval_seconds':-1},{'archive':'ok','no_loop':'true'},
])
def test_inadmissible_receiver_options_do_not_become_native_commands(value):
    with pytest.raises(ContinuityError):options(value)


def test_native_receiver_options_preserve_native_compression_lsn_and_slot_without_shell(tmp_path):
    selected=options({'archive':'Owned.native','compression':'gzip:level=3',
                      'slot':'owned_slot','end_lsn':'A/FFFFFFFF','synchronous':False,'sync':False,'no_loop':True})
    result=arguments(selected,tmp_path/'owned receiver')
    assert '--compress=gzip:level=3' in result and '--endpos=A/FFFFFFFF' in result
    assert '--slot=owned_slot' in result and '--no-sync' in result and '--no-loop' in result
    assert '--directory='+str(tmp_path/'owned receiver') in result


def test_native_zero_status_interval_and_legacy_compression_level_are_preserved():
    result=options({'archive':'owned','status_interval_seconds':0,'compression':'5'})
    assert result['status_interval_seconds']==0 and result['compression']=='5'


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    from pgadmin.cdeadmin.workspace import postgresql_continuity_capture as module
    class Tools:
        def __init__(self,_paths):pass
        def identify(self,*_args):return {'available':True,'version':'(PostgreSQL) 18.3','executable_sha256':'a'*64}
    monkeypatch.setattr(module,'PhysicalTools',Tools)
    import pgadmin.cdeadmin.workspace.postgresql_continuity_jobs as jobs_module
    monkeypatch.setattr(jobs_module,'PhysicalTools',Tools)
    jobs=PostgreSQLContinuityJobs(tmp_path/'jobs.json',tmp_path/'artifacts')
    source={'system_identifier':'18446744073709551615','server_version':180003,'timeline':1,'lsn':'0/100',
            'tablespaces':[],'wal_segment_bytes':1024**2,'wal_block_bytes':8192}
    endpoint=str(uuid.uuid4())
    try:yield jobs,source,endpoint,Tools
    finally:jobs.close()


def review(fixture,**changes):
    jobs,source,endpoint,_tools=fixture
    result=jobs.review({'operation':'wal_capture','options':{'archive':'owned',**changes}},1,endpoint,source,'configuration',{})
    return jobs.load(result['job_id'],1,endpoint)


def test_archive_claim_is_source_bound_and_refuses_an_unreconciled_previous_worker(fixture):
    jobs,source,endpoint,_tools=fixture
    first=review(fixture);jobs.directory(first).mkdir(parents=True)
    with archive_claim(jobs,first) as archive:assert archive.is_dir()
    second=review(fixture);jobs.directory(second).mkdir(parents=True)
    jobs.update(first,state='active',worker_identity=[999999999,0])
    with pytest.raises(ContinuityError,match='termination is unconfirmed'):
        with archive_claim(jobs,second):pytest.fail('Unobserved native writer was replaced')
    jobs.reconcile_writer({'job_id':first['job_id'],'confirmed':True},1,endpoint)
    with archive_claim(jobs,second):pass
    other=jobs.review({'operation':'wal_capture','options':{'archive':'owned'}},1,endpoint,
        {**source,'system_identifier':'1'},'configuration',{})
    with pytest.raises(ContinuityError,match='different cluster'):
        with archive_claim(jobs,jobs.load(other['job_id'],1,endpoint)):pytest.fail('Archive cluster binding was replaced')


def test_unbound_existing_archive_is_never_silently_adopted(fixture):
    jobs,_source,endpoint,_tools=fixture
    record=review(fixture);directory=jobs.archive_directory(1,endpoint)/'owned';directory.mkdir(parents=True)
    (directory/'000000010000000000000001').write_bytes(b'unbound native bytes')
    with pytest.raises(ContinuityError,match='explicit source adoption'):
        with archive_claim(jobs,record):pytest.fail('Unbound files were relabeled')


def wait(jobs,record,endpoint):
    deadline=time.monotonic()+5
    while True:
        value=jobs.get(record['job_id'],1,endpoint)
        if value['state'] not in {'active','dispatching','cancel_requested'}:return value
        if time.monotonic()>deadline:raise AssertionError('Owned fake native worker failed to stop')
        time.sleep(.01)


def test_a_publisher_failure_cancels_the_native_receiver_even_when_callbacks_are_swallowed(fixture,monkeypatch):
    jobs,source,endpoint,tools=fixture
    dispatched=threading.Event()
    def execute(_self,_name,directory,_arguments,**kwargs):
        dispatched.set();staging=directory/'wal-capture'
        (staging/'000000010000000000000003').write_bytes(b'incomplete closed WAL')
        kwargs['progress']({'pid':999999999,'process_create_time':0})
        assert kwargs['cancel_signal'].is_set()
        return {'return_code':-15,'process_observation':{'cleanup_confirmed':True,'cancel_requested':True}}
    monkeypatch.setattr(tools,'execute',execute,raising=False)
    record=review(fixture)
    jobs.start({'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True},
        1,endpoint,source,'configuration',ContinuityTransport({}))
    result=wait(jobs,record,endpoint)
    assert dispatched.is_set() and result['state']=='failed'
    assert result['automatic_retry'] is False and result['tool_observation']['process_observation']['cleanup_confirmed']
    assert not list((jobs.archive_directory(1,endpoint)/'owned').iterdir())


def test_continuous_job_keeps_one_reconnect_segment_and_retains_published_files_after_cancel(fixture,monkeypatch):
    jobs,source,endpoint,tools=fixture
    def execute(_self,_name,directory,_arguments,**kwargs):
        staging=directory/'wal-capture'
        for number in (3,4,5):
            header=bytearray(40)
            struct.pack_into('<HHIQI',header,0,0xD118,2,1,number*1024**2,0)
            struct.pack_into('<QII',header,24,int(source['system_identifier']),1024**2,8192)
            (staging/('0000000100000000'+format(number,'08X'))).write_bytes(header+b'\0'*(1024**2-40))
            kwargs['progress']({'pid':999999999,'process_create_time':0})
        assert len(list(staging.iterdir()))==1
        kwargs['cancel_signal'].set()
        return {'return_code':-15,'process_observation':{'cleanup_confirmed':True,'cancel_requested':True}}
    monkeypatch.setattr(tools,'execute',execute,raising=False)
    record=review(fixture)
    jobs.start({'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True},
        1,endpoint,source,'configuration',ContinuityTransport({}))
    result=wait(jobs,record,endpoint)
    assert result['state']=='cancelled' and result['archive_observation']['new_files']==3
    assert result['archive_observation']['bytes']==str(3*1024**2)
    assert len(list((jobs.archive_directory(1,endpoint)/'owned').iterdir()))==3
    next_record=review(fixture)
    with archive_claim(jobs,next_record):pass


def test_orphan_reconciliation_receipts_stay_small_for_thousands_of_closed_native_files(fixture,monkeypatch):
    jobs,source,endpoint,_tools=fixture
    from pgadmin.cdeadmin.providers.postgresql import continuity_archive
    first=review(fixture);directory=jobs.directory(first);directory.mkdir(parents=True)
    with archive_claim(jobs,first):pass
    staging=directory/'wal-capture';staging.mkdir()
    for index in range(5000):(staging/(format(index+1,'08X')+'.history')).touch()
    jobs.update(first,state='cancelled',tool_observation={'process_observation':{'cleanup_confirmed':True,'return_code':0}})
    def receipt(path,*_args,**_kwargs):
        # Isolate receipt memory from file IO. Native bytes/recovery have their
        # independent acceptance; these are synthetic publication observations.
        return {'name':path.name,'source_file':path.name,'bytes':1048576,
                'sha256':hashlib.sha256(path.name.encode()).hexdigest(),'published':True,
                'system_identifier':str(int(source['system_identifier'])),'page_timeline':1,'file_timeline':1,
                'segment_bytes':1048576,'block_bytes':8192,'native_record_verification':False,
                'completed_native_file_observed':True}
    monkeypatch.setattr(continuity_archive,'publish_file',receipt)
    second=review(fixture);tracemalloc.start()
    try:
        with archive_claim(jobs,second):pass
        _current,peak=tracemalloc.get_traced_memory()
    finally:tracemalloc.stop()
    observed=jobs.load(first['job_id'],1,endpoint)['archive_reconciliation']
    assert observed['completed_file_count']==5000 and len(observed['completed_files'])==10
    assert observed['completed_files_truncated'] and observed['bytes']==str(5000*1048576)
    assert peak<8*1024**2


def test_archive_claim_can_be_cancelled_while_another_owner_of_the_lock_is_active(fixture,monkeypatch):
    jobs,_source,endpoint,_tools=fixture
    record=review(fixture);root=jobs.archive_directory(1,endpoint);root.mkdir(parents=True)
    metadata=root/'.owned.metadata.json';descriptor=os.open(str(metadata)+'.lock',os.O_RDWR|os.O_CREAT,0o600)
    signal=threading.Event();started=threading.Event();contended=threading.Event();errors=[];admitted=[]
    from pgadmin.cdeadmin.workspace import postgresql_continuity_capture as module
    @contextmanager
    def observed_lock(descriptor,**kwargs):
        try:
            with exclusive_file_lock(descriptor,**kwargs):yield
        except OSError:
            contended.set();raise
    monkeypatch.setattr(module,'exclusive_file_lock',observed_lock)
    def worker():
        started.set()
        try:
            with archive_claim(jobs,record,cancel_signal=signal):admitted.append(True)
        except ContinuityError as error:errors.append(str(error))
    thread=threading.Thread(target=worker,daemon=True)
    try:
        with exclusive_file_lock(descriptor):
            thread.start();assert started.wait(2);assert contended.wait(2)
            # A different application worker writes cancellation to the durable
            # receipt; it cannot signal this worker's in-memory Event directly.
            jobs.update(record,cancel_requested=True);thread.join(timeout=2)
            assert not thread.is_alive() and errors==['Native WAL archive claim was cancelled']
            assert signal.is_set()
            assert not admitted and not metadata.exists()
    finally:
        signal.set();os.close(descriptor);thread.join(timeout=5)


def test_cancelled_orphan_publication_keeps_completed_bytes_and_can_resume(fixture):
    jobs,_source,endpoint,_tools=fixture
    first=review(fixture);directory=jobs.directory(first);directory.mkdir(parents=True)
    with archive_claim(jobs,first) as archive:pass
    staging=directory/'wal-capture';staging.mkdir()
    for index in range(1,4):(staging/(format(index,'08X')+'.history')).write_bytes(b'1\t0/100\towned timeline\n')
    jobs.update(first,state='cancelled',tool_observation={'process_observation':{'cleanup_confirmed':True,'return_code':0}})
    second=review(fixture);signal=threading.Event()
    with pytest.raises(ContinuityError,match='publication was cancelled'):
        with archive_claim(jobs,second,cancel_signal=signal,progress=lambda _event:signal.set()):
            pytest.fail('Cancelled reconciliation claimed the next writer')
    assert len(list(archive.iterdir()))==1
    retained=next(archive.iterdir());assert retained.read_bytes()==(staging/retained.name).read_bytes()
    with archive_claim(jobs,second):pass
    assert len(list(archive.iterdir()))==3
    assert jobs.load(first['job_id'],1,endpoint)['archive_reconciliation']['completed_file_count']==3


def test_user_cancellation_during_publication_keeps_a_cancelled_outcome(fixture,monkeypatch):
    jobs,source,endpoint,tools=fixture
    record=review(fixture)
    def execute(_self,_name,directory,_arguments,**kwargs):
        (directory/'wal-capture/000000010000000000000003').write_bytes(b'not ready for publication')
        jobs.cancel(record['job_id'],1,endpoint)
        kwargs['progress']({'pid':999999999,'process_create_time':0})
        return {'return_code':-15,'process_observation':{'cleanup_confirmed':True,'cancel_requested':True}}
    monkeypatch.setattr(tools,'execute',execute,raising=False)
    jobs.start({'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True},
        1,endpoint,source,'configuration',ContinuityTransport({}))
    result=wait(jobs,record,endpoint)
    assert result['state']=='cancelled' and 'error_reason' not in result
