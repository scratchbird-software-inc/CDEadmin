"""Native opaque transform bytes checked by actual native apply and exact values."""
import os
import sqlite3

import pytest

from test_sqlite_changeset_apply import native,apply  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.changeset_transform import transform
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPIError


def execute(api,tmp_path,operation,inputs,**selected):
    path=tmp_path/(operation+str(len(list(tmp_path.iterdir())))+'.native');descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    sources=[os.open(item,os.O_RDONLY) for item in inputs]
    try:observed=transform(api,sources,descriptor,{'operation':operation,**selected})
    finally:
        for source in sources:os.close(source)
        os.close(descriptor)
    assert str(path.stat().st_size)==observed['native_written_bytes']
    return path,observed


def test_native_invert_concat_and_group_merge_preserve_exact_values(native,tmp_path):
    connection,api,create,_route=native;schema='CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT,p BLOB)';connection.execute(schema)
    seed="INSERT INTO t VALUES(9007199254740993,'old 雪',x'00FF')"
    first=create(schema,'',seed);second=create(schema,seed,"UPDATE t SET body='new 😀',p=x'0080FF'")
    for operation in ('concat','merge'):
        combined,result=execute(api,tmp_path,operation,[first,second]);assert len(result['native_input_bytes'])==2
        apply(connection,api,combined);connection.commit()
        assert connection.execute('SELECT * FROM t').fetchone()==(9007199254740993,'new 😀',b'\x00\x80\xff')
        inverse,_result=execute(api,tmp_path,'invert',[combined]);apply(connection,api,inverse);connection.commit()
        assert connection.execute('SELECT COUNT(*) FROM t').fetchone()==(0,)


def test_native_schema_aware_changegroups_fill_defaults_across_column_counts(native,tmp_path):
    connection,api,create,_route=native
    old='CREATE TABLE t(id INTEGER PRIMARY KEY)';new="CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT DEFAULT 'native default 雪')"
    connection.execute(new);first=create(old,'','INSERT INTO t VALUES(1)');second=create(new,'',"INSERT INTO t VALUES(2,'explicit 😀')")
    with pytest.raises(SessionAPIError):execute(api,tmp_path,'merge',[first,second])
    combined,_result=execute(api,tmp_path,'merge',[first,second],schema_database='main')
    apply(connection,api,combined);connection.commit()
    assert connection.execute('SELECT * FROM t ORDER BY id').fetchall()==[(1,'native default 雪'),(2,'explicit 😀')]


def test_native_rebase_uses_actual_conflict_resolution_buffer(native,tmp_path):
    connection,api,create,_route=native;schema='CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT)';connection.execute(schema)
    local=create(schema,'',"INSERT INTO t VALUES(1,'local')");remote=create(schema,'',"INSERT INTO t VALUES(1,'remote')")
    apply(connection,api,local);connection.commit();rebase=tmp_path/'native.rebase'
    selected={'include_rebase':True,'conflicts':{'data':'abort','not_found':'abort','conflict':'replace','constraint':'abort','foreign_key':'abort'}}
    apply(connection,api,remote,selected,rebase=rebase);connection.commit()
    rebased,result=execute(api,tmp_path,'rebase',[local,rebase])
    assert result['native_input_bytes'][1]==str(rebase.stat().st_size)
    descriptor=os.open(rebased,os.O_RDONLY)
    try:observed=api.call('inspect_file',descriptor,-1)
    finally:os.close(descriptor)
    assert observed['native_iterator_complete'] and observed['native_record_count']=='0'


def test_native_patchset_merge_and_inversion_error_are_not_emulated(native,tmp_path):
    connection,api,create,_route=native;schema='CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT)';connection.execute(schema)
    first=create(schema,'',"INSERT INTO t VALUES(1,'native')",kind='patchset')
    combined,_result=execute(api,tmp_path,'merge',[first],patchset_output=True)
    apply(connection,api,combined);connection.commit();assert connection.execute('SELECT * FROM t').fetchone()==(1,'native')
    with pytest.raises(SessionAPIError) as error:execute(api,tmp_path,'invert',[combined])
    assert error.value.native_result_code==sqlite3.SQLITE_CORRUPT or error.value.native_result_code==sqlite3.SQLITE_ERROR


def test_cancelled_native_transform_preserves_existing_pending_work(native,tmp_path):
    connection,api,create,_route=native;schema='CREATE TABLE t(id INTEGER PRIMARY KEY)';connection.execute(schema)
    first=create(schema,'','INSERT INTO t VALUES(1)');connection.execute('BEGIN');connection.execute('INSERT INTO t VALUES(99)')
    read,write=os.pipe();source=os.open(first,os.O_RDONLY);output=os.open(tmp_path/'cancelled.native',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        os.write(write,b'cancel')
        with pytest.raises(SessionAPIError) as error:transform(api,[source],output,{'operation':'invert'},cancel_descriptor=read)
        assert error.value.native_result_code==sqlite3.SQLITE_INTERRUPT
        assert connection.in_transaction and connection.execute('SELECT id FROM t').fetchall()==[(99,)]
    finally:
        for descriptor in (source,output,read,write):os.close(descriptor)
