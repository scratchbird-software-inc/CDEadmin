"""Disposable native diffs preserve SQL and existing native session captures."""
import os
import sqlite3
import threading

import pytest

from test_sqlite_changeset_apply import native,apply  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPI,SessionAPIError
from pgadmin.cdeadmin.providers.sqlite.diff_export import export_difference,options


def exported(api,capture,path):
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:api.export(capture,'changeset',descriptor)
    finally:os.close(descriptor)
    return path.read_bytes()


@pytest.mark.parametrize('database',['main','temp','attached 雪'])
@pytest.mark.parametrize('kind',['changeset','patchset'])
def test_disposable_diff_exports_native_changes_and_preserves_prior_capture_and_savepoint(native,tmp_path,database,kind):
    connection,api,_create,_route=native
    if database not in {'main','temp'}:connection.execute('ATTACH ? AS "attached 雪"',(':memory:',))
    connection.execute("ATTACH ':memory:' AS baseline")
    schema='t(id INTEGER PRIMARY KEY,body TEXT,payload BLOB)'
    connection.execute('CREATE TABLE "'+database+'".'+schema);connection.execute('CREATE TABLE baseline.'+schema)
    for selected in (database,'baseline'):
        connection.execute('INSERT INTO "'+selected+'".t VALUES(1,?,?),(2,?,?)',('old 雪',b'\x00\xff','deleted',b''))
    original=api.open(database);api.attach(original,'t')
    connection.execute('BEGIN');connection.execute('SAVEPOINT owner_sql')
    connection.execute('UPDATE "'+database+'".t SET body=?,payload=? WHERE id=1',('new 😀',b'\x00\x80\xff'))
    connection.execute('DELETE FROM "'+database+'".t WHERE id=2')
    connection.execute('INSERT INTO "'+database+'".t VALUES(9007199254740993,?,?)',('pending',b''))
    before=exported(api,original,tmp_path/'existing-before.native');events=[];progress={'vm_progress_callbacks':0}
    output=tmp_path/'difference.native';descriptor=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        observed=export_difference(api,database,'baseline','t',kind,descriptor,cancel_event=threading.Event(),cancel_descriptor=-1,
            progress=progress,acknowledge=lambda event,data:events.append((event,data)),estimate_size=True)
    finally:os.close(descriptor)
    assert str(output.stat().st_size)==observed['native_written_bytes']
    assert [event for event,_data in events]==['capture_created','diff_returned','export_returned','capture_closed']
    assert events[-1][1]['native_capture_close_returned'] and connection.in_transaction
    assert list(api.captures)==[original] and exported(api,original,tmp_path/'existing-after.native')==before
    independent=sqlite3.connect(':memory:',factory=SQLiteConnection)
    try:
        independent.execute('CREATE TABLE '+schema);independent.execute('INSERT INTO t VALUES(1,?,?),(2,?,?)',('old 雪',b'\x00\xff','deleted',b''));independent.commit()
        independent_api=SessionAPI(independent,os.environ['CDEADMIN_SQLITE_SESSION_LIBRARY'])
        apply(independent,independent_api,output);independent.commit()
        assert independent.execute('SELECT * FROM t ORDER BY id').fetchall()==[(1,'new 😀',b'\x00\x80\xff'),(9007199254740993,'pending',b'')]
    finally:independent.close()
    connection.execute('ROLLBACK TO owner_sql');connection.execute('RELEASE owner_sql')
    assert connection.in_transaction and connection.execute('SELECT body FROM "'+database+'".t WHERE id=1').fetchone()==('old 雪',)


def test_cancel_during_native_diff_preserves_existing_capture_exact_bytes_and_pending_sql(native,tmp_path):
    connection,api,_create,_route=native
    connection.executescript("ATTACH ':memory:' AS old;CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT);CREATE TABLE old.t(id INTEGER PRIMARY KEY,body TEXT);WITH RECURSIVE n(v) AS(VALUES(1) UNION ALL SELECT v+1 FROM n WHERE v<30000) INSERT INTO t SELECT v,'current' FROM n;INSERT INTO old.t SELECT id,'old' FROM t;")
    original=api.open('main');api.attach(original,'t')
    connection.execute('BEGIN');connection.execute('SAVEPOINT owner_sql');connection.execute("UPDATE t SET body='pending' WHERE id=1")
    before=exported(api,original,tmp_path/'before.native');cancel=threading.Event();events=[]
    class Progress(dict):
        def __setitem__(self,key,value):
            super().__setitem__(key,value)
            if value>=3:cancel.set()
    progress=Progress(vm_progress_callbacks=0);descriptor=os.open(tmp_path/'cancelled.native',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with pytest.raises(SessionAPIError) as error:
            export_difference(api,'main','old','t','changeset',descriptor,cancel_event=cancel,cancel_descriptor=-1,
                progress=progress,acknowledge=lambda event,data:events.append((event,data)))
        assert error.value.native_result_code==sqlite3.SQLITE_INTERRUPT
    finally:os.close(descriptor)
    assert progress['vm_progress_callbacks']==3 and events[-1][0]=='capture_closed'
    assert events[1][1]['native_result_code']==sqlite3.SQLITE_INTERRUPT and events[1][1]['partial_capture_discarded_on_failure']
    assert connection._cdeadmin_progress_handler==(None,0)
    assert list(api.captures)==[original] and exported(api,original,tmp_path/'after.native')==before
    assert connection.in_transaction and connection.execute('SELECT body FROM t WHERE id=1').fetchone()==('pending',)
    connection.execute('ROLLBACK TO owner_sql');connection.execute('RELEASE owner_sql')
    assert connection.in_transaction and connection.execute('SELECT body FROM t WHERE id=1').fetchone()==('current',)


def test_prior_progress_owner_is_preserved_and_acknowledgement_failure_still_closes_private_capture(native,tmp_path):
    connection,api,_create,_route=native
    connection.executescript("CREATE TABLE t(id INTEGER PRIMARY KEY);ATTACH ':memory:' AS old;CREATE TABLE old.t(id INTEGER PRIMARY KEY)")
    descriptor=os.open(tmp_path/'owned.native',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);prior=lambda:0
    selected=dict(cancel_event=threading.Event(),cancel_descriptor=-1,progress={'vm_progress_callbacks':0})
    try:
        connection.set_progress_handler(prior,200)
        with pytest.raises(SessionAPIError,match='already owns'):
            export_difference(api,'main','old','t','changeset',descriptor,acknowledge=lambda *_args:None,**selected)
        assert connection._cdeadmin_progress_handler==(prior,200) and not api.captures
        connection.set_progress_handler(None,0)
        def broken(event,_data):
            if event=='capture_created':raise OSError('durable receipt failure')
        with pytest.raises(OSError,match='receipt failure'):
            export_difference(api,'main','old','t','changeset',descriptor,acknowledge=broken,**selected)
        assert not api.captures and connection._cdeadmin_progress_handler==(None,0)
    finally:os.close(descriptor)


@pytest.mark.parametrize('change',[
    {'database':None},{'source_database':[]},{'table_name':'bad\x00name'},
    {'kind':[]},{'kind':'sql'},{'track_rowids':1},{'estimate_size':'yes'},
    {'timeout_seconds':True},{'timeout_seconds':0},{'path':'arbitrary-file'}])
def test_invalid_comparison_options_are_refused_before_native_capture(change):
    with pytest.raises(SessionAPIError):options({'database':'main','source_database':'old','table_name':'native\n雪',**change})


def test_native_rowid_comparison_retains_exact_unkeyed_row_identity(native,tmp_path):
    connection,api,_create,_route=native
    connection.executescript("CREATE TABLE unkeyed(body TEXT);ATTACH ':memory:' AS old;CREATE TABLE old.unkeyed(body TEXT);INSERT INTO old.unkeyed(rowid,body) VALUES(9007199254740993,'old');INSERT INTO unkeyed(rowid,body) VALUES(9007199254740993,'new 雪😀');")
    descriptor=os.open(tmp_path/'rowid.native',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        export_difference(api,'main','old','unkeyed','changeset',descriptor,cancel_event=threading.Event(),cancel_descriptor=-1,
            progress={'vm_progress_callbacks':0},acknowledge=lambda *_args:None,track_rowids=True)
    finally:os.close(descriptor)
    independent=sqlite3.connect(':memory:',factory=SQLiteConnection)
    try:
        independent.executescript("CREATE TABLE unkeyed(body TEXT);INSERT INTO unkeyed(rowid,body) VALUES(9007199254740993,'old');")
        independent_api=SessionAPI(independent,os.environ['CDEADMIN_SQLITE_SESSION_LIBRARY'])
        apply(independent,independent_api,tmp_path/'rowid.native');independent.commit()
        assert independent.execute('SELECT rowid,body FROM unkeyed').fetchall()==[(9007199254740993,'new 雪😀')]
    finally:independent.close()
