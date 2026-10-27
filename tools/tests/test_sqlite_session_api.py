"""Public native session APIs retain driver transaction, trace and lifetime rules."""
import json
import os
from pathlib import Path
import shutil
import sqlite3

import pytest

from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPI,SessionAPIError,_LIVE


@pytest.fixture
def native(tmp_path):
    filename=os.environ.get('CDEADMIN_SQLITE_SESSION_LIBRARY')
    if not filename or not Path(filename).is_file():pytest.skip('An explicit native session bridge is required')
    if sqlite3.sqlite_version!='3.53.0':pytest.skip('The pinned native SQLite3.53.0 binding is required')
    connection=sqlite3.connect(':memory:',factory=SQLiteConnection)
    try:yield connection,filename,tmp_path
    finally:connection.close()


def test_private_control_tokens_never_reach_user_trace_and_loading_preserves_transaction(native):
    connection,filename,_tmp=native;trace=[]
    connection.execute('CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT,payload BLOB)');connection.commit()
    connection.execute('BEGIN');connection.set_trace_callback(trace.append)
    api=SessionAPI(connection,filename);session=api.open('main',estimate_size=True,track_rowids=True);api.attach(session,'t')
    connection.execute('INSERT INTO t VALUES(?,?,?)',(9007199254740993,'Unicode 😀',b'\x00\xff'))
    status=api.status(session)
    assert connection.in_transaction and status['enabled'] and not status['empty']
    assert int(status['memory_bytes'])>0 and int(status['changeset_estimate_bytes'])>0
    assert any('INSERT INTO t' in row for row in trace)
    assert not any('_cdeadmin_session' in row or api.token.hex() in row.lower() for row in trace)
    assert not connection.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION)
    connection.rollback();api.close(session)
    assert id(connection) not in _LIVE


def test_stream_export_cancel_and_output_failure_preserve_pending_transaction(native):
    connection,filename,tmp=native
    connection.execute('CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT,payload BLOB)');connection.commit()
    api=SessionAPI(connection,filename);session=api.open('main');api.attach(session,'t')
    connection.execute('INSERT INTO t VALUES(?,?,?)',(9007199254740993,'😀'*(600000),b'\x00\x80\xff'))
    path=tmp/'native.changeset';descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:written=api.export(session,'changeset',descriptor);os.fsync(descriptor)
    finally:os.close(descriptor)
    assert written==path.stat().st_size and written>2200000 and connection.in_transaction
    read,write=os.pipe();os.write(write,b'cancel')
    descriptor=os.open(tmp/'cancelled',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with pytest.raises(SessionAPIError) as failure:api.export(session,'patchset',descriptor,read)
        assert failure.value.native_result_code==sqlite3.SQLITE_INTERRUPT and connection.in_transaction
    finally:os.close(read);os.close(write);os.close(descriptor)
    read,write=os.pipe()
    try:
        with pytest.raises(SessionAPIError) as failure:api.export(session,'changeset',read)
    finally:os.close(read);os.close(write)
    assert failure.value.native_result_code==sqlite3.SQLITE_IOERR_WRITE and connection.in_transaction
    assert connection.execute('SELECT CAST(id AS TEXT),length(body),hex(payload) FROM t').fetchone()==('9007199254740993',600000,'0080FF')
    connection.rollback()


def test_wrong_capability_and_rebinding_never_reconfigure_owned_sessions(native):
    connection,filename,_tmp=native;api=SessionAPI(connection,filename);session=api.open('main')
    error=json.loads(connection.execute('SELECT "'+api._call_name+'"(?,?,?)',(b'x'*32,'close',session)).fetchone()[0])
    assert error['native_result_code']==sqlite3.SQLITE_AUTH
    error=json.loads(connection.execute('SELECT "'+api._bind_name+'"(?)',(b'y'*32,)).fetchone()[0])
    assert error['native_result_code']==sqlite3.SQLITE_AUTH and api.status(session)['empty']
    with pytest.raises(SessionAPIError,match='already owns'):SessionAPI(connection,filename)


def test_native_controller_reinitialization_preserves_capture_and_capability(native):
    connection,filename,_tmp=native;api=SessionAPI(connection,filename);session=api.open('main')
    connection.enable_load_extension(False);connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION,True)
    try:connection.load_extension(filename,entrypoint='sqlite3_cdeadminsessions_init')
    finally:connection.enable_load_extension(False)
    assert api.status(session)['empty'] and api.status(session)['enabled']


def test_authorization_revocation_cannot_prevent_owned_capture_cleanup_or_idempotent_close(native):
    connection,filename,_tmp=native;api=SessionAPI(connection,filename);api.open('main')
    connection.set_authorizer(lambda *_arguments:sqlite3.SQLITE_DENY)
    connection.close();connection.close()
    assert not api.captures and id(connection) not in _LIVE


def test_changed_library_provenance_never_dispatches_native_initialization(native):
    connection,filename,tmp=native;staged=tmp/Path(filename).name;shutil.copy2(filename,staged)
    metadata=json.loads(Path(filename+'.json').read_text());metadata['library_sha256']='0'*64
    Path(str(staged)+'.json').write_text(json.dumps(metadata))
    with pytest.raises(SessionAPIError,match='provenance'):SessionAPI(connection,str(staged))
    assert connection._cdeadmin_session_api is None
    assert not any(isinstance(row[0],str) and row[0].startswith(('_cdeadmin_session_bind_','_cdeadmin_session_call_')) for row in connection.execute('PRAGMA function_list'))


def test_native_controls_preserve_existing_user_function_names_and_source_id_overrides(native):
    connection,filename,_tmp=native
    connection.create_function('_cdeadmin_session',-1,lambda *_arguments:'owned user function')
    connection.create_function('_cdeadmin_session_bind',1,lambda _argument:'owned user binding')
    connection.create_function('sqlite_source_id',0,lambda:'user override')
    api=SessionAPI(connection,filename);session=api.open('main')
    assert api.status(session)['empty']
    assert api.program['sqlite_source_id'].startswith('2026-04-09')
    assert connection.execute('SELECT _cdeadmin_session()').fetchone()==('owned user function',)
    assert connection.execute('SELECT _cdeadmin_session_bind(NULL)').fetchone()==('owned user binding',)
