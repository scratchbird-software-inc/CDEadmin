"""Real native transform workers preserve inputs, schema snapshots and SQL work."""
from contextlib import contextmanager
import os
import time
import uuid

import pytest

from test_sqlite_changeset_apply import native  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.changeset_transform import options
from pgadmin.cdeadmin.providers.sqlite.transform_context import schema_snapshot
from pgadmin.cdeadmin.workspace.sqlite_transform_jobs import SQLiteTransformJobs,TransformTransport


@pytest.fixture
def setup(native,tmp_path):
    connection,api,create,route=native;schema='CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT)';connection.execute(schema)
    source=create(schema,'',"INSERT INTO t VALUES(9007199254740993,'native 😀')")
    jobs=SQLiteTransformJobs(tmp_path/'transforms.json',tmp_path/'transforms');endpoint=str(uuid.uuid4())
    def reviewed(operation='invert',basis=None,cancel_on_open=False):
        selected=options({'operation':operation,'schema_database':basis})
        source_state={'inputs':[{'file':{'path':source.name}}],'schema':None if basis is None else schema_snapshot(connection,basis)}
        receipt=jobs.review(1,endpoint,selected,{'identity':source_state,'state':{}},'owned',api.program)
        record=jobs.load(receipt['job_id'],1,endpoint);request={'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True}
        @contextmanager
        def input_file():
            if cancel_on_open:jobs.cancel(record['job_id'],1,endpoint)
            with source.open('rb') as stream:yield stream,{'path':source.name}
        transport=TransformTransport(jobs,os.environ['CDEADMIN_SQLITE_SESSION_LIBRARY'],[input_file],route if basis else None)
        return record,request,transport
    try:yield jobs,connection,endpoint,reviewed,source
    finally:jobs.close()


def start(jobs,record,request,transport,endpoint):
    return jobs.start(request,1,endpoint,{key:record[key] for key in ('source','configuration','program')},transport)


def wait(jobs,record,endpoint):
    deadline=time.monotonic()+10
    while True:
        value=jobs.get(record['job_id'],1,endpoint)
        with jobs._maps_lock:known=jobs.workers.get(record['job_id'])
        if value['state'] not in {'active','dispatching','publishing','cancel_requested'} and not known:return value
        assert time.monotonic()<deadline;time.sleep(.01)


def test_native_transform_seals_exact_input_output_and_does_not_repeat(setup):
    jobs,connection,endpoint,reviewed,source=setup;before=source.read_bytes();record,request,transport=reviewed()
    start(jobs,record,request,transport,endpoint);value=wait(jobs,record,endpoint)
    assert value['state']=='completed',value
    assert value['native_returned'] and value['result']['artifact']['native_record_count']=='1'
    assert value['native_transform']['native_input_bytes']==[str(len(before))]
    assert source.read_bytes()==before and connection.execute('SELECT count(*) FROM t').fetchone()==(0,)
    with jobs.download(record['job_id'],1,endpoint,'transformed.native') as (stream,row):assert len(stream.read())==row['size']>0
    assert jobs.start(request,1,endpoint,{},None)['state']=='completed'


def test_lost_native_transform_publication_reconciles_the_sealed_candidate(setup,monkeypatch):
    from pgadmin.cdeadmin.workspace import sqlite_transform_jobs as module
    jobs,_connection,endpoint,reviewed,_source=setup;record,request,transport=reviewed();replace=module.durable_replace
    def broken(_source,_target):raise OSError('owned transform publication fault')
    monkeypatch.setattr(module,'durable_replace',broken);start(jobs,record,request,transport,endpoint);value=wait(jobs,record,endpoint)
    assert value['state']=='unknown' and value['native_returned'] and value['sealed_candidate']
    monkeypatch.setattr(module,'durable_replace',replace)
    assert jobs.reconcile(record['job_id'],1,endpoint)['state']=='artifact_verified'


def test_registered_schema_merge_is_read_only_and_preserves_neighbor_pending_sql(setup):
    jobs,connection,endpoint,reviewed,_source=setup;record,request,transport=reviewed('merge','main')
    connection.execute('BEGIN');connection.execute("INSERT INTO t VALUES(7,'pending')")
    start(jobs,record,request,transport,endpoint);value=wait(jobs,record,endpoint)
    assert value['state']=='completed',value
    assert connection.in_transaction and connection.execute('SELECT * FROM t').fetchall()==[(7,'pending')]
    connection.rollback()


def test_changed_schema_refuses_native_transform_without_touching_source_or_target(setup):
    jobs,connection,endpoint,reviewed,source=setup;before=source.read_bytes();record,request,transport=reviewed('merge','main')
    connection.execute('ALTER TABLE t ADD COLUMN changed TEXT')
    start(jobs,record,request,transport,endpoint);value=wait(jobs,record,endpoint)
    assert value['state']=='failed' and not value.get('native_returned')
    assert source.read_bytes()==before and connection.execute('SELECT COUNT(*) FROM t').fetchone()==(0,)


def test_native_transform_cancel_before_dispatch_keeps_inputs_and_releases_worker(setup):
    jobs,_connection,endpoint,reviewed,source=setup;before=source.read_bytes();record,request,transport=reviewed(cancel_on_open=True)
    start(jobs,record,request,transport,endpoint);value=wait(jobs,record,endpoint)
    assert value['state']=='cancelled' and value['worker_io_closed'] and not value.get('native_returned')
    assert source.read_bytes()==before
