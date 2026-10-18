"""Durable choices reach live callbacks without replaying the owned transaction."""
from contextlib import contextmanager
import os
import sqlite3
import time
import uuid

import pytest
from test_sqlite_changeset_apply import native
from pgadmin.cdeadmin.providers.sqlite.changeset_apply import options,target_snapshot
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPIError
from pgadmin.cdeadmin.workspace.sqlite_changeset_jobs import SQLiteChangesetJobs,ApplyTransport


@pytest.fixture
def setup(native,tmp_path):
    connection,api,create,route=native;schema='CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT,p BLOB)';connection.execute(schema)
    original=b'\x00\xff'*100000;connection.execute('INSERT INTO t VALUES(1,?,?)',('target 雪😀',original));connection.commit()
    source=create(schema,'',"INSERT INTO t VALUES(1,'incoming',x'0080')")
    jobs=SQLiteChangesetJobs(tmp_path/'interactive.json',tmp_path/'interactive');endpoint=str(uuid.uuid4())
    selected=options({'interactive_conflicts':True})
    receipt=jobs.review(1,endpoint,selected,{'identity':{'destination':target_snapshot(connection,route),'export_job_id':'owned'},'state':{}},'owned',api.program)
    record=jobs.load(receipt['job_id'],1,endpoint);request={'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True}
    @contextmanager
    def input_file():
        with source.open('rb') as stream:yield stream,{'path':source.name}
    transport=ApplyTransport(jobs,route,os.environ['CDEADMIN_SQLITE_SESSION_LIBRARY'],input_file)
    try:yield jobs,endpoint,record,request,transport,route,original
    finally:
        value=jobs.get(record['job_id'],1,endpoint)
        if value['state'] in {'active','dispatching','cancel_requested'}:jobs.cancel(record['job_id'],1,endpoint)
        jobs.close()


def start(setup):
    jobs,endpoint,record,request,transport,*_=setup
    return jobs.start(request,1,endpoint,{key:record[key] for key in ('source','configuration','program')},transport)


def wait_for(setup,predicate):
    jobs,endpoint,record,*_=setup;deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        value=jobs.get(record['job_id'],1,endpoint)
        if predicate(value):return value
        time.sleep(.01)
    raise AssertionError(value)


def test_live_durable_replace_consumption_and_commit_are_separate_facts(setup):
    jobs,endpoint,record,request,_transport,route,original=setup;start(setup)
    value=wait_for(setup,lambda row:row.get('pending_conflict',{}).get('waiting'))
    pending=value['pending_conflict'];event=jobs.conflict(record['job_id'],1,endpoint,pending['challenge'])['event']
    assert event['kind_name']=='conflict' and event['current_values'][1]['preview_text']=='target 雪😀'
    assert event['incoming']['new_values'][1]['preview_text']=='incoming'
    with jobs.conflict_value(record['job_id'],1,endpoint,pending['challenge'],'current',2) as (stream,metadata):
        assert stream.read()==original and metadata['size']==len(original) and stream.read()==b''
    with sqlite3.connect(route['database']) as observer:assert observer.execute('SELECT body FROM t').fetchone()==('target 雪😀',)
    response={'challenge':pending['challenge'],'choice':'replace','remember_kind':False}
    jobs.decide(record['job_id'],1,endpoint,response)
    value=wait_for(setup,lambda row:row['state'] not in {'active','dispatching','committing','cancel_requested'})
    assert value['state']=='completed',value
    assert value['last_native_conflict_decision']['choice']==1 and value['commit_returned'] and value.get('owned_rollback_confirmed') is not True
    with sqlite3.connect(route['database']) as observer:assert observer.execute('SELECT body,hex(p) FROM t').fetchone()==('incoming','0080')
    assert jobs.start(request,1,endpoint,{},None)['state']=='completed'
    with pytest.raises(SessionAPIError):jobs.decide(record['job_id'],1,endpoint,response)


def test_native_cancel_while_waiting_preserves_the_original_target(setup):
    jobs,endpoint,record,_request,_transport,route,_original=setup;start(setup)
    value=wait_for(setup,lambda row:row.get('pending_conflict',{}).get('waiting'))
    with pytest.raises(ValueError):jobs.conflict(record['job_id'],2,endpoint,value['pending_conflict']['challenge'])
    jobs.cancel(record['job_id'],1,endpoint)
    value=wait_for(setup,lambda row:row['state'] not in {'active','dispatching','committing','cancel_requested'})
    assert value['state']=='cancelled' and value['owned_rollback_confirmed'] and not value.get('commit_admitted'),value
    with sqlite3.connect(route['database']) as observer:assert observer.execute('SELECT body FROM t').fetchone()==('target 雪😀',)


def test_stale_native_callback_response_is_refused_before_admission(setup):
    jobs,endpoint,record,*_=setup;start(setup);wait_for(setup,lambda row:row.get('pending_conflict',{}).get('waiting'))
    with pytest.raises(SessionAPIError,match='no longer waiting'):jobs.decide(record['job_id'],1,endpoint,{'challenge':'0'*32,'choice':'replace','remember_kind':False})
    value=jobs.get(record['job_id'],1,endpoint);assert value.get('conflict_response') is None and not value.get('commit_admitted')
