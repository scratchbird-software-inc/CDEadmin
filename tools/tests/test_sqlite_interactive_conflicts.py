"""Live public conflict callbacks, scoped responses and native rollback behavior."""
from contextlib import ExitStack,contextmanager
import json
import os
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest
from test_sqlite_changeset_apply import native


@contextmanager
def running(connection,api,path,tmp):
    with ExitStack() as cleanup:
        cr,cw=os.pipe();rr,rw=os.pipe()
        for descriptor in (cr,cw,rr,rw):cleanup.callback(os.close,descriptor)
        event_path=tmp/'events.jsonl';value_path=tmp/'values.bin'
        flags=os.O_RDWR|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0)
        events=os.open(event_path,flags,0o600);values=os.open(value_path,flags,0o600)
        cleanup.callback(os.close,events);cleanup.callback(os.close,values)
        holder={}
        def worker():
            try:
                with path.open('rb') as source:holder['result']=api.call('apply_interactive',source.fileno(),cr,1,2,2,2,2,2,-1,None,events,rr,values)
            except BaseException as error:holder['error']=error
        connection.execute('BEGIN IMMEDIATE');thread=threading.Thread(target=worker,daemon=True);thread.start()
        def event(name='conflict'):
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                rows=[json.loads(line) for line in event_path.read_text().splitlines(keepends=True) if line.endswith('\n')]
                value=next((row for row in reversed(rows) if row['event']==name),None)
                if value is not None:return value
                if 'error' in holder:raise holder['error']
                time.sleep(.01)
            raise AssertionError('Native callback did not emit its event')
        def respond(value,choice=1,remember=False,nonce=None):
            frame=b'SR'+(bytes.fromhex(value['challenge']) if nonce is None else nonce)+bytes([choice,int(remember)])
            assert os.write(rw,frame)==20
        try:yield SimpleNamespace(thread=thread,holder=holder,event=event,respond=respond,cancel=lambda:os.write(cw,b'cancel'),values=value_path,events=event_path)
        finally:
            if thread.is_alive():os.write(cw,b'cancel');thread.join(5)
            assert not thread.is_alive(),'Native callback did not acknowledge cancellation'
            if connection.in_transaction:connection.rollback()


def test_live_conflict_values_and_full_bytes_are_protected_until_the_scoped_response(native,tmp_path):
    connection,api,create,route=native;schema='CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT,p BLOB)';connection.execute(schema)
    target_blob=b'\x00\xff'*100000;connection.execute('INSERT INTO t VALUES(1,?,?)',('target 雪😀',target_blob));connection.commit()
    source=create(schema,'',"INSERT INTO t VALUES(1,'incoming',x'00FF')")
    with running(connection,api,source,tmp_path) as live:
        event=live.event();assert event['kind']==3 and event['apply_change_sequence']=='1'
        assert event['incoming']['new_values'][1]['hex']=='696E636F6D696E67' and event['current_values'][1]['hex']=='74617267657420E99BAAF09F9880'
        assert 'record_number' not in event['incoming'] and event['incoming']['apply_change_sequence']=='1'
        reference=next(row for row in event['byte_values'] if row['side']=='current' and row['column_index']==2)
        with live.values.open('rb') as stream:stream.seek(int(reference['byte_offset']));assert stream.read(int(reference['byte_length']))==target_blob
        with sqlite3.connect(route['database']) as observer:assert observer.execute('SELECT body FROM t').fetchone()==('target 雪😀',)
        live.respond(event);live.thread.join(5);assert not live.thread.is_alive();result=live.holder['result']
        assert result['native_apply_result_code']==0 and result['native_conflict_event_error']==0 and result['native_conflict_events']=='1'
        assert live.event('decision_ack')['choice']==1 and connection.in_transaction
        assert connection.execute('SELECT body,hex(p) FROM t').fetchone()==('incoming','00FF')
        connection.rollback()
    assert connection.execute('SELECT body FROM t').fetchone()==('target 雪😀',)


def test_remember_kind_uses_native_policy_for_later_conflicts_without_replaying(native,tmp_path):
    connection,api,create,_route=native;schema='CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT)';connection.execute(schema)
    connection.executemany('INSERT INTO t VALUES(?,?)',[(1,'old'),(2,'old'),(3,'old')]);connection.commit()
    source=create(schema,'',"INSERT INTO t VALUES(1,'new'),(2,'new'),(3,'new')")
    with running(connection,api,source,tmp_path) as live:
        event=live.event();live.respond(event,remember=True);live.thread.join(5);assert not live.thread.is_alive()
        result=live.holder['result'];assert result['native_conflict_events']=='1' and result['conflicts']['conflict']=='3'
        assert live.event('decision_ack')['remember_kind'] and connection.execute("SELECT count(*) FROM t WHERE body='new'").fetchone()==(3,)
        connection.commit()


def test_wrong_challenge_aborts_native_apply_and_preserves_owned_rollback(native,tmp_path):
    connection,api,create,_route=native;schema='CREATE TABLE t(id INTEGER PRIMARY KEY)';connection.execute(schema);connection.execute('INSERT INTO t VALUES(1)');connection.commit()
    source=create(schema,'','INSERT INTO t VALUES(1)')
    with running(connection,api,source,tmp_path) as live:
        event=live.event();live.respond(event,nonce=b'x'*16);live.thread.join(5);assert not live.thread.is_alive()
        result=live.holder['result'];assert result['native_apply_result_code']==sqlite3.SQLITE_ABORT and result['native_conflict_event_error']==sqlite3.SQLITE_AUTH
        assert connection.in_transaction


def test_cancellation_while_waiting_returns_without_a_decision_ack(native,tmp_path):
    connection,api,create,_route=native;schema='CREATE TABLE t(id INTEGER PRIMARY KEY)';connection.execute(schema);connection.execute('INSERT INTO t VALUES(1)');connection.commit()
    source=create(schema,'','INSERT INTO t VALUES(1)')
    with running(connection,api,source,tmp_path) as live:
        live.event();live.cancel();live.thread.join(5);assert not live.thread.is_alive()
        assert live.holder['result']['native_apply_result_code']!=0 and not any(json.loads(line)['event']=='decision_ack' for line in live.events.read_text().splitlines())


def test_foreign_key_callback_reports_its_aggregate_and_refuses_native_replace(native,tmp_path):
    connection,api,create,_route=native
    schema='CREATE TABLE parent(id INTEGER PRIMARY KEY);CREATE TABLE child(id INTEGER PRIMARY KEY,pid INTEGER REFERENCES parent(id));'
    connection.executescript(schema);connection.execute('PRAGMA foreign_keys=ON')
    source=create(schema,'','INSERT INTO child VALUES(1,9)')
    with running(connection,api,source,tmp_path) as live:
        event=live.event();assert event['kind']==5 and event['foreign_key_count']==1 and 'incoming' not in event
        live.respond(event,choice=1);live.thread.join(5);assert not live.thread.is_alive()
        assert live.holder['result']['native_conflict_event_error']==sqlite3.SQLITE_AUTH and live.holder['result']['native_apply_result_code']==sqlite3.SQLITE_CONSTRAINT


@pytest.mark.parametrize('expected,schema,seed,mutation,target,choice',[
    (1,'CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT)',"INSERT INTO t VALUES(1,'before')","UPDATE t SET body='incoming'","INSERT INTO t VALUES(1,'different')",1),
    (2,'CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT)',"INSERT INTO t VALUES(1,'before')",'DELETE FROM t','',0),
    (4,'CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT UNIQUE)','',"INSERT INTO t VALUES(1,'clash')","INSERT INTO t VALUES(2,'clash')",0),
])
def test_native_data_missing_and_constraint_conflicts_preserve_their_available_vectors(native,tmp_path,expected,schema,seed,mutation,target,choice):
    connection,api,create,_route=native;connection.executescript(schema+';'+target)
    source=create(schema,seed,mutation)
    with running(connection,api,source,tmp_path) as live:
        event=live.event();assert event['kind']==expected
        if expected==1:assert event['current_values'][1]['hex']=='646966666572656E74'
        else:assert event['current_values'] is None
        live.respond(event,choice=choice);live.thread.join(5);assert not live.thread.is_alive()
        assert live.holder['result']['native_apply_result_code']==0 and live.holder['result']['native_conflict_event_error']==0
