"""Real native writes, commit acknowledgements and independent output receipts."""
from contextlib import contextmanager
import time
import uuid

import pytest

from test_sqlite_changeset_apply import native  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.changeset_apply import options,target_snapshot
from pgadmin.cdeadmin.workspace.sqlite_changeset_jobs import SQLiteChangesetJobs,ApplyTransport


@pytest.fixture
def setup(native,tmp_path,monkeypatch):
    import os
    connection,api,create,route=native
    schema='CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT)';connection.execute(schema)
    source=create(schema,'',"INSERT INTO t VALUES(1,'remote')")
    jobs=SQLiteChangesetJobs(tmp_path/'apply.json',tmp_path/'apply-jobs');endpoint=str(uuid.uuid4())
    reviewed=jobs.review(1,endpoint,options({}),{'identity':{'destination':target_snapshot(connection,route),'export_job_id':'owned-source'},'state':{}},'owned',api.program)
    record=jobs.load(reviewed['job_id'],1,endpoint);request={'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True}
    @contextmanager
    def input_file():
        with source.open('rb') as stream:yield stream,{'path':source.name}
    def transport():return ApplyTransport(jobs,route,os.environ['CDEADMIN_SQLITE_SESSION_LIBRARY'],input_file)
    def start():return jobs.start(request,1,endpoint,{key:record[key] for key in ('source','configuration','program')},transport())
    try:yield jobs,connection,record,request,endpoint,start,route
    finally:jobs.close()


def wait(jobs,record,endpoint):
    deadline=time.monotonic()+10
    while True:
        result=jobs.get(record['job_id'],1,endpoint)
        with jobs._maps_lock:known=jobs.workers.get(record['job_id'])
        if result['state'] not in {'dispatching','active','committing','cancel_requested'} and not known:return result
        assert time.monotonic()<deadline;time.sleep(.01)


def test_native_apply_and_commit_have_separate_durable_acknowledgements(setup):
    jobs,connection,record,request,endpoint,start,_route=setup;start();result=wait(jobs,record,endpoint)
    assert result['state']=='completed',result
    assert result['native_returned'] and result['commit_admitted'] and result['commit_returned']
    assert result['result']['data_finality']=='native-commit-returned' and result['worker_io_closed']
    assert connection.execute('SELECT * FROM t').fetchall()==[(1,'remote')]
    assert jobs.start(request,1,endpoint,{},None)['state']=='completed'
    assert jobs.reconcile(record['job_id'],1,endpoint)['output_artifact_verified']


@pytest.mark.parametrize('lost_ack',[False,True])
def test_lost_commit_or_publication_never_repeats_or_infers_commit_from_output(setup,monkeypatch,lost_ack):
    from pgadmin.cdeadmin.workspace import sqlite_changeset_jobs as module
    jobs,connection,record,request,endpoint,start,_route=setup;update=jobs.update
    if lost_ack:
        def broken(selected,**values):
            if values.get('commit_returned'):raise OSError('owned commit acknowledgement fault')
            return update(selected,**values)
        monkeypatch.setattr(jobs,'update',broken)
    else:
        def broken(_source,_target):raise OSError('owned output publication fault')
        monkeypatch.setattr(module,'durable_replace',broken)
    start();result=wait(jobs,record,endpoint)
    assert result['state']=='unknown' and result['commit_admitted'] and bool(result.get('commit_returned')) is (not lost_ack)
    assert connection.execute('SELECT * FROM t').fetchall()==[(1,'remote')]
    assert jobs.start(request,1,endpoint,{},None)['state']=='unknown'
    monkeypatch.undo()
    reconciled=jobs.reconcile(record['job_id'],1,endpoint)
    assert reconciled['state']=='unknown' and reconciled['output_artifact_verified']
    assert bool(reconciled.get('commit_returned')) is (not lost_ack)
    with jobs.output_download(record['job_id'],1,endpoint,'archive.json') as (stream,row):assert len(stream.read())==row['size']>0
    assert jobs.get(record['job_id'],1,endpoint)['state']=='unknown'


def test_stale_schema_is_consumed_without_native_mutation(setup):
    jobs,connection,record,request,endpoint,start,_route=setup
    connection.execute('ALTER TABLE t ADD COLUMN changed TEXT');start();result=wait(jobs,record,endpoint)
    assert result['state']=='failed' and not result.get('native_dispatch_admitted')
    assert connection.execute('SELECT * FROM t').fetchall()==[]
    assert jobs.start(request,1,endpoint,{},None)['state']=='failed'


def test_cancel_before_transaction_never_commits_native_changes(setup,monkeypatch):
    from pgadmin.cdeadmin.workspace import sqlite_changeset_jobs as module
    jobs,connection,record,_request,endpoint,start,_route=setup;connect=module.connect
    def cancelled(*args):
        result=connect(*args);jobs.cancel(record['job_id'],1,endpoint);return result
    monkeypatch.setattr(module,'connect',cancelled);start();result=wait(jobs,record,endpoint)
    assert result['state']=='cancelled' and not result.get('native_dispatch_admitted')
    assert connection.execute('SELECT * FROM t').fetchall()==[] and result['worker_io_closed']


def test_busy_commit_rolls_back_owned_writer_and_keeps_neighbor_read_transaction(setup):
    jobs,connection,record,request,endpoint,start,route=setup
    route['timeout']=.1
    connection.execute('BEGIN');connection.execute('SELECT * FROM t').fetchall()
    start();result=wait(jobs,record,endpoint)
    assert result['state']=='failed' and result['commit_failure_rolled_back'] and result['owned_rollback_confirmed'],result
    assert connection.in_transaction and connection.execute('SELECT * FROM t').fetchall()==[]
    connection.rollback()
    assert jobs.start(request,1,endpoint,{},None)['state']=='failed'
