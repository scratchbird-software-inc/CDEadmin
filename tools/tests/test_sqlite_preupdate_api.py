"""Public native preupdate observations and ownership of the single hook."""
import os
from pathlib import Path
import sqlite3
import pytest
from pgadmin.cdeadmin.providers.sqlite.native_helpers import helper_supported
from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
from pgadmin.cdeadmin.providers.sqlite.preupdate_api import PreupdateAPI
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPI,SessionAPIError


@pytest.fixture
def native():
    library=os.environ.get('CDEADMIN_SQLITE_PREUPDATE_LIBRARY');sessions=os.environ.get('CDEADMIN_SQLITE_SESSION_LIBRARY')
    if not library or not Path(library).is_file() or not sessions or not Path(sessions).is_file() or not helper_supported('preupdate') or not helper_supported('session'):pytest.skip('Native preupdate and session helpers required (built, and supported by this SQLite runtime)')
    connection=sqlite3.connect(':memory:',factory=SQLiteConnection)
    try:yield connection,PreupdateAPI(connection,library),sessions
    finally:connection.close()


def test_typed_native_values_trigger_depth_and_rolled_back_observations(native):
    connection,api,_sessions=native
    connection.executescript('CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT,b BLOB,n REAL);CREATE TABLE audit(id INTEGER);CREATE TRIGGER copied AFTER INSERT ON t BEGIN INSERT INTO audit VALUES(new.id);END;')
    api.start(100,1048576)
    connection.execute('INSERT INTO t VALUES(?,?,?,?)',(9007199254740993,'雪\x00😀',b'\x00\xff',.1))
    events=api.call('events',0,100)['events'];assert len(events)==2
    event=events[0];assert event['operation']=='insert' and event['old_values'] is None and event['column_count']==4 and event['depth']==0
    assert event['new_values']==[{'native_type':'integer','data':'9007199254740993'},{'native_type':'text','hex':'E99BAA00F09F9880'},{'native_type':'blob','hex':'00FF'},{'native_type':'real','data':'0.1'}]
    assert events[1]['table_hex']=='6175646974' and events[1]['depth']==1
    connection.execute('UPDATE t SET body=NULL,b=x\'\' WHERE id=9007199254740993')
    connection.execute('DELETE FROM t');connection.rollback()
    events=api.call('events',0,100)['events'];assert len(events)==4 and events[-1]['operation']=='delete' and events[-1]['new_values'] is None
    assert events[2]['old_values'][1]['hex']=='E99BAA00F09F9880' and events[2]['new_values'][1]['native_type']=='null'
    assert connection.execute('SELECT * FROM t').fetchall()==[] and api.status()['observed_events']=='4'
    assert api.stop()['retained_events']==4


def test_native_blob_write_and_without_rowid_columns(native):
    connection,api,_sessions=native
    connection.executescript("CREATE TABLE wr(k TEXT PRIMARY KEY,v BLOB) WITHOUT ROWID;CREATE TABLE b(id INTEGER PRIMARY KEY,v BLOB);INSERT INTO b VALUES(1,zeroblob(4));")
    api.start(100,1048576)
    connection.execute("INSERT INTO wr VALUES('k',x'')")
    with connection.blobopen('b','v',1) as blob:blob.write(b'\x00\xff\x80\x01')
    events=api.call('events',0,100)['events'];assert events[0]['new_values']==[{'native_type':'text','hex':'6B'},{'native_type':'blob','hex':''}]
    assert events[1]['operation']=='delete' and events[1]['blobwrite_column']==1 and events[1]['new_values'] is None
    assert connection.in_transaction


def test_retention_limits_lost_events_pagination_and_explicit_reset(native):
    connection,api,_sessions=native;connection.execute('CREATE TABLE t(x)');api.start(2,100000)
    connection.executemany('INSERT INTO t VALUES(?)',[(1,),(2,),(3,)])
    status=api.status();assert status['observed_events']=='3' and status['dropped_events']=='1' and status['retained_events']==2
    one=api.call('events',0,1);assert one['more'] and one['events'][0]['sequence']=='1'
    two=api.call('events',1,1);assert not two['more'] and two['events'][0]['sequence']=='2'
    assert connection.in_transaction
    api.stop()
    with pytest.raises(SessionAPIError):api.start(2,100000)
    old=api.run_id;api.clear();assert api.run_id!=old and api.status()['retained_events']==0
    api.start(10,100);connection.execute('INSERT INTO t VALUES(?)',('x'*1000,));status=api.status()
    assert status['observed_events']=='1' and status['dropped_events']=='1' and status['last_native_result_code']==sqlite3.SQLITE_TOOBIG
    assert connection.in_transaction and connection.execute('SELECT count(*) FROM t').fetchone()==(4,)


def test_session_and_preupdate_controllers_refuse_hook_replacement_in_both_directions(native):
    connection,api,library=native;connection.execute('CREATE TABLE t(id INTEGER PRIMARY KEY)');sessions=SessionAPI(connection,library)
    assert sessions.program['native_session_revision']>=4
    capture=sessions.open('main');sessions.attach(capture,'t')
    with pytest.raises(SessionAPIError,match='Close native'):api.start(10,100000)
    with pytest.raises(SessionAPIError) as error:api.call('start',10,100000)
    assert error.value.native_result_code==sqlite3.SQLITE_BUSY
    connection.execute('INSERT INTO t VALUES(1)');assert not sessions.status(capture)['empty']
    sessions.close(capture);api.start(10,100000)
    with pytest.raises(SessionAPIError,match='Stop'):sessions.open('main')
    with pytest.raises(SessionAPIError) as error:sessions.call('open','direct-request','main',0,0)
    assert error.value.native_result_code==sqlite3.SQLITE_BUSY
    connection.execute('INSERT INTO t VALUES(2)');assert api.status()['observed_events']=='1'
    api.stop();capture=sessions.open('main');sessions.attach(capture,'t');connection.execute('INSERT INTO t VALUES(3)');assert not sessions.status(capture)['empty']
    assert api.status()['observed_events']=='1' and connection.in_transaction


def test_control_privacy_loader_and_authorizer_cleanup(native):
    connection,api,_sessions=native;trace=[];connection.set_trace_callback(trace.append);connection.execute('CREATE TABLE t(x)');api.start(10,100000);connection.execute('INSERT INTO t VALUES(1)')
    api.status();api.call('events',0,100)
    assert not any(api.token.hex().lower() in line.lower() for line in trace) and not connection.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION)
    def deny(*_args):return sqlite3.SQLITE_DENY
    connection.set_authorizer(deny);api.close_all();assert connection._cdeadmin_authorizer is deny
    connection.set_authorizer(None);assert connection.in_transaction;connection.commit();connection.close();connection.close()
