"""Native original-handle configuration bridge ownership and lifecycle."""
import gc,os,sqlite3,weakref
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection

pytestmark=pytest.mark.skipif(not os.environ.get('CDEADMIN_SQLITE_CONFIG_LIBRARY'),reason='Native configuration helper not selected')


def connection():return SQLiteConnection(':memory:',cached_statements=0)


def test_capture_uses_original_library_without_sql_loading_or_hook_replacement():
    source=connection()
    api=source._cdeadmin_config_api
    try:
        assert api.program['sqlite_version']==sqlite3.sqlite_version
        assert not source.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION)
        calls=[];source.set_trace_callback(calls.append)
        authorizer=lambda *_:sqlite3.SQLITE_OK
        progress=lambda:0
        source.set_authorizer(authorizer);source.set_progress_handler(progress,1000)
        assert api.module.usage(api.capsule)==(0,0,0)
        assert api.module.lookaside(api.capsule,128,128)==0
        assert calls==[] and source._cdeadmin_authorizer is authorizer
        assert source._cdeadmin_progress_handler==(progress,1000)
        assert source._cdeadmin_trace_callback==calls.append
    finally:source.close()
    assert api.closed

@pytest.mark.parametrize('name',['stmt_scanstatus','reverse_scanorder','enable_attach_create','enable_attach_write','enable_comments'])
def test_native_named_boolean_availability_and_read_write(name):
    source=connection();api=source._cdeadmin_config_api
    try:
        code,before=api.module.boolean(api.capsule,name,-1)
        if code:
            assert code==sqlite3.SQLITE_ERROR
        else:
            assert before in (0,1)
            for value in (0,1):assert api.module.boolean(api.capsule,name,value)==(0,value)
            api.module.boolean(api.capsule,name,before)
    finally:source.close()


def test_native_alias_savepoint_peer_isolation_and_busy_lookaside():
    source=connection();api=source._cdeadmin_config_api;peer=sqlite3.connect(':memory:')
    try:
        assert api.module.lookaside(api.capsule,128,128)==0
        source.executescript('CREATE TABLE owned(value);SAVEPOINT caller;INSERT INTO owned VALUES(7)')
        assert api.module.alias(api.capsule,'Owned 雪')==0
        assert source.execute('PRAGMA database_list').fetchone()[1]=='Owned 雪'
        assert peer.execute('PRAGMA database_list').fetchone()[1]=='main'
        assert source.execute('SELECT * FROM "Owned 雪".owned').fetchall()==[(7,)] and source.in_transaction
        status,current,_=api.module.usage(api.capsule)
        assert status==0 and current>0
        assert api.module.lookaside(api.capsule,256,128)==sqlite3.SQLITE_BUSY
        source.execute('ROLLBACK TO caller');source.execute('RELEASE caller')
        assert source.execute('SELECT * FROM owned').fetchall()==[]
    finally:source.close();peer.close()
    with pytest.raises(RuntimeError):api.module.boolean(api.capsule,'reverse_scanorder',-1)


def test_native_owner_close_confirmation_cannot_target_a_peer_or_live_connection():
    source=connection();peer=connection();api=source._cdeadmin_config_api
    try:
        with pytest.raises(RuntimeError):api.module.closed(api.capsule,source)
        peer.close()
        with pytest.raises(RuntimeError):api.module.closed(api.capsule,peer)
        sqlite3.Connection.close(source)
        with pytest.raises(sqlite3.ProgrammingError):api.module.boolean(api.capsule,'reverse_scanorder',-1)
    finally:source.close();peer.close()
    assert api.closed


def test_owned_gc_closes_native_binding_and_retained_alias_storage():
    source=connection();api=source._cdeadmin_config_api
    assert api.module.alias(api.capsule,'gc_owned')==0
    reference=weakref.ref(source);del source;gc.collect()
    assert reference()is None and api.closed
    with pytest.raises(RuntimeError):api.module.boolean(api.capsule,'reverse_scanorder',-1)


def test_failed_native_open_cancels_capture_before_next_connection(tmp_path):
    with pytest.raises(sqlite3.OperationalError):SQLiteConnection(str(tmp_path/'missing'/'owned.db'))
    source=connection()
    try:assert source._cdeadmin_config_api is not None
    finally:source.close()


def test_unfinished_capture_never_exposes_native_configuration():
    source=connection();module=source._cdeadmin_config_api.module
    try:
        staged=module.begin()
        try:
            with pytest.raises(RuntimeError):module.boolean(staged,'reverse_scanorder',-1)
            with pytest.raises(RuntimeError):module.begin()
        finally:module.cancel(staged)
    finally:source.close()
