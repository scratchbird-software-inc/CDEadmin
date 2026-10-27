"""Native managed diff/export jobs retain exact capture and SQL ownership."""
import os
import threading
import time
import uuid

import pytest

from test_sqlite_changeset_apply import native,apply  # noqa: F401
from test_sqlite_driver import client,open_database  # noqa: F401
from test_sqlite_diff_export import exported
from test_sqlite_transform_jobs import start,wait
from pgadmin.cdeadmin.providers.sqlite.diff_export import options
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPI
from pgadmin.cdeadmin.providers.sqlite.transform_context import retained_snapshot,schema_snapshot
from pgadmin.cdeadmin.workspace.sqlite_diff_jobs import SQLiteDiffJobs,DiffTransport


@pytest.fixture
def setup(native,client,tmp_path):
    independent,independent_api,_create,_route=native;connection,route=open_database(client,tmp_path)
    connection.executescript("CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT);ATTACH ':memory:' AS old;CREATE TABLE old.t(id INTEGER PRIMARY KEY,body TEXT);WITH RECURSIVE n(v) AS(VALUES(1) UNION ALL SELECT v+1 FROM n WHERE v<30000) INSERT INTO t SELECT v,'current' FROM n;INSERT INTO old.t SELECT id,'old' FROM t;")
    api=SessionAPI(connection,os.environ['CDEADMIN_SQLITE_SESSION_LIBRARY']);original=api.open('main');api.attach(original,'t')
    connection.execute('BEGIN');connection.execute('SAVEPOINT owner_sql');connection.execute("UPDATE t SET body='pending' WHERE id=1")
    before=exported(api,original,tmp_path/'existing-before.native')
    jobs=SQLiteDiffJobs(tmp_path/'diffs.json',tmp_path/'diffs');endpoint=str(uuid.uuid4());session=str(uuid.uuid4())
    selected=options({'database':'main','source_database':'old','table_name':'t','timeout_seconds':60})
    source={'schema_binding':retained_snapshot(connection,api,session,'main'),'source_schema':schema_snapshot(connection,'old',transient=True)}
    value=jobs.review(1,endpoint,selected,{'identity':source,'state':{}},'owned',api.program);record=jobs.load(value['job_id'],1,endpoint)
    request={'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True}
    transport=DiffTransport(jobs,os.environ['CDEADMIN_SQLITE_SESSION_LIBRARY'],{'client':client,'handle':connection,'api':api})
    try:yield jobs,endpoint,record,request,transport,connection,api,original,before,independent,independent_api
    finally:jobs.close()


def preserved(setup,tmp_path):
    _jobs,_endpoint,_record,_request,_transport,connection,api,original,before,_independent,_api=setup
    assert connection.in_transaction and connection.execute('SELECT body FROM t WHERE id=1').fetchone()==('pending',)
    assert list(api.captures)==[original] and exported(api,original,tmp_path/'existing-after.native')==before
    connection.execute('ROLLBACK TO owner_sql');connection.execute('RELEASE owner_sql')
    assert connection.in_transaction and connection.execute('SELECT body FROM t WHERE id=1').fetchone()==('current',)


def test_native_managed_diff_seals_once_and_independently_applies_without_settling_sql(setup,tmp_path):
    jobs,endpoint,record,request,transport,_connection,_api,_original,_before,independent,independent_api=setup
    start(jobs,record,request,transport,endpoint);value=wait(jobs,record,endpoint)
    assert value['state']=='completed',value
    assert value['diff_returned'] and value['export_returned'] and value['capture_closed'] and value['native_returned']
    assert value['source_transaction_open'] and value['source_transaction_open_after']
    assert value['result']['artifact']['native_record_count']=='30000'
    independent.executescript("CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT);WITH RECURSIVE n(v) AS(VALUES(1) UNION ALL SELECT v+1 FROM n WHERE v<30000) INSERT INTO t SELECT v,'old' FROM n;")
    apply(independent,independent_api,jobs.directory(record)/'archive/difference.native');independent.commit()
    assert independent.execute('SELECT body,count(*) FROM t GROUP BY body ORDER BY body').fetchall()==[('current',29999),('pending',1)]
    with jobs.download(record['job_id'],1,endpoint,'difference.native') as (stream,row):assert len(stream.read())==row['size']>0
    assert jobs.start(request,1,endpoint,{},None)['state']=='completed'
    preserved(setup,tmp_path)


def test_managed_cancellation_during_native_comparison_discards_only_private_capture(setup,tmp_path,monkeypatch):
    from pgadmin.cdeadmin.workspace import sqlite_diff_jobs as module
    jobs,endpoint,record,request,transport,_connection,_api,_original,_before,_independent,_api2=setup
    entered=threading.Event();release=threading.Event();original=module.export_difference
    class Progress(dict):
        def __setitem__(self,key,value):
            super().__setitem__(key,value)
            if value==3:entered.set();assert release.wait(5)
    def observed(*args,**kwargs):
        kwargs['progress']=Progress(kwargs['progress']);return original(*args,**kwargs)
    monkeypatch.setattr(module,'export_difference',observed)
    start(jobs,record,request,transport,endpoint)
    try:
        assert entered.wait(5);jobs.cancel(record['job_id'],1,endpoint)
        deadline=time.monotonic()+5
        while not jobs.get(record['job_id'],1,endpoint).get('progress',{}).get('elapsed_seconds'):
            assert time.monotonic()<deadline;time.sleep(.02)
    finally:release.set()
    value=wait(jobs,record,endpoint)
    assert value['state']=='cancelled' and value['capture_closed'] and value['worker_io_closed'],value
    assert value['diff_returned_details']['native_result_code']==9 and not value.get('export_returned')
    assert id(transport.binding['handle']) not in transport.binding['client']._busy
    preserved(setup,tmp_path)


def test_managed_diff_refuses_changed_attached_source_schema_before_dispatch(setup,tmp_path):
    jobs,endpoint,record,request,transport,connection,_api,_original,_before,_independent,_api2=setup
    connection.execute('ALTER TABLE old.t ADD COLUMN changed TEXT')
    start(jobs,record,request,transport,endpoint);value=wait(jobs,record,endpoint)
    assert value['state']=='failed' and not value.get('native_dispatch_admitted'),value
    preserved(setup,tmp_path)


def test_unconfirmed_private_capture_close_blocks_connection_without_settling_sql(setup,monkeypatch):
    from pgadmin.cdeadmin.sdk import RelationalClientError
    jobs,endpoint,record,request,transport,connection,api,existing,_before,_independent,_api2=setup
    close=api.close
    def broken(capture):
        if capture!=existing:raise OSError('native capture closure unavailable')
        return close(capture)
    monkeypatch.setattr(api,'close',broken)
    start(jobs,record,request,transport,endpoint);value=wait(jobs,record,endpoint)
    assert value['state']=='unknown' and value['native_capture_close_unconfirmed'] and value['source_connection_blocked'],value
    assert value['export_returned'] and not value.get('capture_closed')
    with transport.binding['client']._lock:
        with pytest.raises(RelationalClientError,match='unknown'):transport.binding['client']._require_idle(connection)
    assert connection.in_transaction and connection.execute('SELECT body FROM t WHERE id=1').fetchone()==('pending',)
    for capture in tuple(api.captures):
        if capture!=existing:close(capture)
    assert jobs.start(request,1,endpoint,{},None)['state']=='unknown'


def test_lost_diff_publication_reconciles_sealed_bytes_without_repeating_comparison(setup,tmp_path,monkeypatch):
    from pgadmin.cdeadmin.workspace import sqlite_diff_jobs as module
    jobs,endpoint,record,request,transport,_connection,_api,_original,_before,_independent,_api2=setup
    replace=module.durable_replace
    def broken(*_args):raise OSError('diff publication fault')
    monkeypatch.setattr(module,'durable_replace',broken)
    start(jobs,record,request,transport,endpoint);value=wait(jobs,record,endpoint)
    assert value['state']=='unknown' and value['native_returned'] and value['capture_closed'] and value['sealed_candidate'],value
    monkeypatch.setattr(module,'durable_replace',replace)
    assert jobs.reconcile(record['job_id'],1,endpoint)['state']=='artifact_verified'
    assert jobs.start(request,1,endpoint,{},None)['state']=='artifact_verified'
    preserved(setup,tmp_path)
