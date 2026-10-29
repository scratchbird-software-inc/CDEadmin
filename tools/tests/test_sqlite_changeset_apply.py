"""Public native apply semantics, owned transactions and exact conflict policies."""
import os
from pathlib import Path
import sqlite3

import pytest

from pgadmin.cdeadmin.providers.sqlite.native_helpers import helper_supported
from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPI,SessionAPIError
from pgadmin.cdeadmin.providers.sqlite.changeset_apply import ApplyFailure,connect,options,stage,target_snapshot


@pytest.fixture
def native(tmp_path):
    library=os.environ.get('CDEADMIN_SQLITE_SESSION_LIBRARY')
    if not library or not Path(library).is_file() or not helper_supported('session'):pytest.skip('Native session helper required (built, and supported by this SQLite runtime)')
    counter=0
    def changeset(schema,seed,mutations,*,kind='changeset',rowids=False):
        nonlocal counter
        counter+=1;path=tmp_path/(str(counter)+'.'+kind)
        source=sqlite3.connect(':memory:',factory=SQLiteConnection)
        try:
            source.executescript(schema);source.executescript(seed);api=SessionAPI(source,library)
            capture=api.open('main',track_rowids=rowids);api.attach(capture,None);source.executescript(mutations)
            descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            try:api.export(capture,kind,descriptor)
            finally:os.close(descriptor)
        finally:source.close()
        return path
    path=tmp_path/'target.sqlite';sqlite3.connect(path).close();route={'database':str(path),'filesystem_root':str(tmp_path)}
    connection,api=connect(route,library)
    try:yield connection,api,changeset,route
    finally:connection.close()


def apply(connection,api,path,selected=None,*,rebase=None,acknowledge=lambda value:None):
    selected=options(selected or {})
    for name in ('foreign_keys','recursive_triggers'):connection.execute('PRAGMA '+name+'='+str(int(selected[name])))
    connection.execute('BEGIN IMMEDIATE')
    descriptor=os.open(path,os.O_RDONLY);output=-1
    if rebase is not None:output=os.open(rebase,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:return stage(connection,api,descriptor,selected,rebase_descriptor=output,acknowledge=acknowledge)
    except BaseException:
        if connection.in_transaction:connection.rollback()
        raise
    finally:
        os.close(descriptor)
        if output>=0:os.close(output)


def test_native_apply_stages_exact_types_and_inversion_without_committing(native):
    connection,api,create,_route=native
    schema='CREATE TABLE "native\n雪"(id INTEGER PRIMARY KEY,body TEXT,p BLOB)'
    connection.execute(schema);path=create(schema,'',"INSERT INTO \"native\n雪\" VALUES(9007199254740993,'😀',x'0080FF')")
    result=apply(connection,api,path)
    assert result['native_changes_included']=='1' and not result['commit_returned'] and connection.in_transaction
    assert connection.execute('SELECT * FROM "native\n雪"').fetchone()==(9007199254740993,'😀',b'\x00\x80\xff')
    connection.commit();apply(connection,api,path,{'invert':True});connection.commit()
    assert connection.execute('SELECT COUNT(*) FROM "native\n雪"').fetchone()==(0,)


@pytest.mark.parametrize('kind,seed,mutation,target',[
    ('data',"INSERT INTO t VALUES(1,'old')","UPDATE t SET body='new' WHERE id=1","INSERT INTO t VALUES(1,'changed')"),
    ('not_found',"INSERT INTO t VALUES(1,'old')",'DELETE FROM t WHERE id=1',''),
    ('conflict','',"INSERT INTO t VALUES(1,'new')","INSERT INTO t VALUES(1,'target')"),
    ('constraint','',"INSERT INTO t VALUES(1,'duplicate')","INSERT INTO t VALUES(2,'duplicate')"),
])
def test_native_conflict_abort_rolls_back_and_omit_records_exact_kind(native,kind,seed,mutation,target):
    connection,api,create,_route=native;schema='CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT UNIQUE)'
    connection.execute(schema)
    if target:connection.executescript(target)
    before=connection.execute('SELECT * FROM t').fetchall();path=create(schema,seed,mutation);ack=[]
    with pytest.raises(ApplyFailure) as error:apply(connection,api,path,acknowledge=ack.append)
    assert error.value.native_observations['conflicts'][kind]=='1' and ack[0]['native_apply_result_code']!=0
    assert connection.execute('SELECT * FROM t').fetchall()==before and not connection.in_transaction
    selected=options({});selected['conflicts'][kind]='omit';result=apply(connection,api,path,selected);connection.commit()
    assert result['conflicts'][kind]=='1' and connection.execute('SELECT * FROM t').fetchall()==before


def test_replace_conflict_produces_native_rebase_and_ignore_noop_suppresses_duplicate(native,tmp_path):
    connection,api,create,_route=native;schema='CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT)';connection.execute(schema)
    connection.execute("INSERT INTO t VALUES(1,'local')");path=create(schema,'',"INSERT INTO t VALUES(1,'remote')")
    selected=options({'include_rebase':True});selected['conflicts']['conflict']='replace'
    result=apply(connection,api,path,selected,rebase=tmp_path/'native.rebase');connection.commit()
    assert result['conflicts']['conflict']=='1' and int(result['native_rebase_bytes'])>0 and (tmp_path/'native.rebase').stat().st_size==int(result['native_rebase_bytes'])
    assert connection.execute('SELECT body FROM t').fetchone()==('remote',)
    result=apply(connection,api,path,{'ignore_noop':True});connection.commit()
    assert set(result['conflicts'].values())=={'0'}


def test_native_foreign_key_conflict_is_separate_from_row_constraint(native):
    connection,api,create,_route=native
    schema='CREATE TABLE parent(id INTEGER PRIMARY KEY);CREATE TABLE child(id INTEGER PRIMARY KEY,parent_id REFERENCES parent(id))'
    connection.executescript(schema);path=create(schema,'','INSERT INTO child VALUES(1,99)')
    with pytest.raises(ApplyFailure) as error:apply(connection,api,path)
    assert error.value.native_observations['conflicts']['foreign_key']=='1'
    assert connection.execute('SELECT count(*) FROM child').fetchone()==(0,)
    selected=options({});selected['conflicts']['foreign_key']='omit'
    result=apply(connection,api,path,selected);connection.commit()
    assert result['conflicts']['foreign_key']=='1' and connection.execute('PRAGMA foreign_key_check').fetchall()


def test_incompatible_selected_tables_refuse_success_and_rollback_compatible_changes(native):
    connection,api,create,_route=native
    schema='CREATE TABLE t(id INTEGER PRIMARY KEY);CREATE TABLE missing(id INTEGER PRIMARY KEY)'
    connection.execute('CREATE TABLE t(id INTEGER PRIMARY KEY)');path=create(schema,'','INSERT INTO t VALUES(1);INSERT INTO missing VALUES(2)')
    with pytest.raises(ApplyFailure,match='compatibility skipped'):apply(connection,api,path)
    assert connection.execute('SELECT count(*) FROM t').fetchone()==(0,)
    result=apply(connection,api,path,{'table_name':'t'});connection.commit()
    assert result['source_inspection']['native_selected_record_count']=='1' and connection.execute('SELECT id FROM t').fetchone()==(1,)


def test_native_rowid_changes_patchset_and_schema_snapshot(native):
    connection,api,create,route=native;schema='CREATE TABLE t(body TEXT)';connection.execute(schema)
    before=target_snapshot(connection,route);path=create(schema,'',"INSERT INTO t(rowid,body) VALUES(9007199254740993,'rowid')",kind='patchset',rowids=True)
    apply(connection,api,path);connection.commit()
    assert connection.execute('SELECT rowid,body FROM t').fetchone()==(9007199254740993,'rowid')
    with pytest.raises(ApplyFailure):apply(connection,api,path,{'invert':True})
    connection.execute('ALTER TABLE t ADD COLUMN extra BLOB');assert target_snapshot(connection,route)['schema_sha256']!=before['schema_sha256']


def test_apply_options_refuse_unsupported_replacement_and_read_only_connections(native):
    connection,api,_create,route=native
    for kind in ('not_found','constraint','foreign_key'):
        selected=options({});selected['conflicts'][kind]='replace'
        with pytest.raises(SessionAPIError,match='replacement'):options(selected)
    with pytest.raises(SessionAPIError,match='writable'):connect({**route,'read_only':True},'')
    assert not connection.in_transaction
