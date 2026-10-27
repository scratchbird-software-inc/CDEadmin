"""Real native capture exports retain their connection and private file outcomes."""
import os
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace
import uuid

import pytest

from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPI
from pgadmin.cdeadmin.workspace.sqlite_capture_jobs import SQLiteCaptureJobs,ExportTransport


@pytest.fixture
def native(tmp_path):
    library=os.environ.get('CDEADMIN_SQLITE_SESSION_LIBRARY')
    if not library or not Path(library).is_file() or sqlite3.sqlite_version!='3.53.0':pytest.skip('Pinned native SQLite session bridge is required')
    connection=sqlite3.connect(':memory:',factory=SQLiteConnection,check_same_thread=False)
    connection.execute('CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT,payload BLOB)');connection.commit()
    api=SessionAPI(connection,library);capture=api.open('main');api.attach(capture,'t')
    connection.execute('INSERT INTO t VALUES(?,?,?)',(9007199254740993,'Native 😀'*300000,b'\x00\x80\xff'))
    jobs=SQLiteCaptureJobs(tmp_path/'jobs.json',tmp_path/'artifacts');endpoint=str(uuid.uuid4())
    source={'capture_id':capture,'database':'main','databases':[list(row) for row in connection.execute('PRAGMA database_list')]}
    client=SimpleNamespace(_lock=threading.RLock(),_busy=set(),_require_idle=lambda handle:None)
    review=jobs.review(1,endpoint,{'kind':'changeset','timeout_seconds':60},{'identity':source,'state':{}},'owned',api.program)
    record=jobs.load(review['job_id'],1,endpoint);request={'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True}
    try:yield jobs,client,connection,api,record,request,endpoint
    finally:jobs.close();connection.close()


def wait(jobs,record,endpoint):
    deadline=time.monotonic()+10
    while True:
        receipt=jobs.get(record['job_id'],1,endpoint)
        with jobs._maps_lock:known=jobs.workers.get(record['job_id'])
        if receipt['state'] not in {'active','dispatching','publishing','cancel_requested'} and not known:return receipt
        assert time.monotonic()<deadline;time.sleep(.01)


def test_native_export_parsed_sealed_downloaded_once_without_settling_transaction(native):
    jobs,client,connection,api,record,request,endpoint=native
    jobs.start(request,1,endpoint,{key:record[key] for key in ('source','configuration','program')},ExportTransport(jobs,client,connection,api,record['source']))
    receipt=wait(jobs,record,endpoint)
    assert receipt['state']=='completed',receipt.get('error_message')
    assert receipt['result']['artifact']['native_iterator_complete'] and receipt['result']['artifact']['native_record_count']=='1'
    assert receipt['source_transaction_open'] and receipt['source_transaction_open_after'] and connection.in_transaction
    assert not client._busy and receipt['worker_io_closed']
    assert jobs.start(request,1,endpoint,{},None)['state']=='completed'
    files=jobs.files(record['job_id'],1,endpoint)['files'];row=next(row for row in files if row['path']=='capture.changeset')
    with jobs.download(record['job_id'],1,endpoint,row['path']) as (stream,observed):
        assert len(stream.read())==int(row['size'])>2200000 and observed['sha256']==row['sha256']
    assert jobs.reconcile(record['job_id'],1,endpoint)['state']=='artifact_verified'


def test_native_return_survives_lost_publication_and_reconciles_sealed_candidate(native,monkeypatch):
    from pgadmin.cdeadmin.workspace import sqlite_capture_jobs as module
    jobs,client,connection,api,record,request,endpoint=native
    original=module.durable_replace
    def broken(_source,_target):raise OSError('owned publication fault')
    monkeypatch.setattr(module,'durable_replace',broken)
    jobs.start(request,1,endpoint,{key:record[key] for key in ('source','configuration','program')},ExportTransport(jobs,client,connection,api,record['source']))
    receipt=wait(jobs,record,endpoint)
    assert receipt['state']=='unknown' and receipt['native_returned'] and receipt['sealed_candidate']
    assert connection.in_transaction and not client._busy
    monkeypatch.setattr(module,'durable_replace',original)
    reconciled=jobs.reconcile(record['job_id'],1,endpoint)
    assert reconciled['state']=='artifact_verified' and reconciled['result']['native_returned']


def test_cancel_before_native_stream_preserves_capture_and_pending_data(native,monkeypatch):
    jobs,client,connection,api,record,request,endpoint=native;status=api.status
    def cancelled(capture):
        result=status(capture);jobs.cancel(record['job_id'],1,endpoint);return result
    monkeypatch.setattr(api,'status',cancelled)
    jobs.start(request,1,endpoint,{key:record[key] for key in ('source','configuration','program')},ExportTransport(jobs,client,connection,api,record['source']))
    receipt=wait(jobs,record,endpoint)
    assert receipt['state']=='cancelled' and receipt['native_result_code']==sqlite3.SQLITE_INTERRUPT
    assert connection.in_transaction and connection.execute('SELECT COUNT(*) FROM t').fetchone()==(1,)
    assert not client._busy and receipt['worker_io_closed']


def test_observer_start_failure_releases_owned_descriptors_and_connection(native,monkeypatch):
    jobs,client,connection,api,record,request,endpoint=native;start=threading.Thread.start
    def fail_observer(thread):
        if thread.name.startswith('sqlite-capture-progress-'):raise RuntimeError('owned observer start fault')
        return start(thread)
    monkeypatch.setattr(threading.Thread,'start',fail_observer)
    jobs.start(request,1,endpoint,{key:record[key] for key in ('source','configuration','program')},ExportTransport(jobs,client,connection,api,record['source']))
    receipt=wait(jobs,record,endpoint)
    assert receipt['state']=='failed' and receipt['error_type']=='RuntimeError'
    assert receipt['worker_io_closed'] and not client._busy and connection.in_transaction


@pytest.mark.parametrize('acknowledged',[False,True])
def test_unsealed_native_stream_stays_uncertain_after_diagnostic_inspection(native,monkeypatch,acknowledged):
    from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPIError
    jobs,client,connection,api,record,request,endpoint=native;export=api.export;update=jobs.update
    if acknowledged:
        def lose_seal(selected,**values):
            if values.get('state')=='publishing':raise OSError('owned seal receipt fault')
            return update(selected,**values)
        monkeypatch.setattr(jobs,'update',lose_seal)
    else:
        def lose_return(*args):
            export(*args);raise RuntimeError('owned lost native return acknowledgement')
        monkeypatch.setattr(api,'export',lose_return)
    jobs.start(request,1,endpoint,{key:record[key] for key in ('source','configuration','program')},ExportTransport(jobs,client,connection,api,record['source']))
    receipt=wait(jobs,record,endpoint)
    assert receipt['state']=='unknown' and bool(receipt.get('native_returned'))==acknowledged
    assert not receipt.get('sealed_candidate') and connection.in_transaction
    def inspect(descriptor,program):
        assert program==api.program
        return api.call('inspect_file',descriptor,-1)
    inspected=jobs.reconcile(record['job_id'],1,endpoint,inspect)
    partial=inspected['partial_output']
    assert inspected['state']=='unknown' and partial['observations']['native_iterator_complete']
    assert partial['diagnostic_only'] and not partial['complete_export_verified'] and not partial['original_export_bytes_verified']
    with jobs.diagnostic_download(record['job_id'],1,endpoint,partial['path']) as (stream,row):assert len(stream.read())==row['size']>2200000
    assert jobs.start(request,1,endpoint,{},None)['state']=='unknown'
    path=jobs.directory(record)/'archive.incoming'/('capture.'+record['options']['kind'])
    with path.open('ab') as stream:stream.write(b'changed')
    with pytest.raises(SessionAPIError,match='changed after inspection'):
        with jobs.diagnostic_download(record['job_id'],1,endpoint,partial['path']):pass
