"""Remaining native sqlite3_limit categories, including recoverable VM refusal."""
from contextlib import closing
import sqlite3
import pytest
from test_sqlite_connection_limits import native, run  # noqa: F401
from ui_descriptor_roundtrip import engine_operations, operation_draft


def apply_limit(native,name,value):
    before=run(native,'inspect',limit=name)['effective_value']
    op=engine_operations('sqlite')['set_connection_limit_'+name+'@database']
    draft=operation_draft(op,{'value':value,'expected_value':before,'confirmed':True})
    result=run(native,'set_connection_limit',limit=name,**draft)
    return before,result


def test_vdbe_op_native_prepare_limit_and_original_handle_recovery(native):
    source=native[2];code=sqlite3.SQLITE_LIMIT_VDBE_OP
    query=' UNION ALL '.join('SELECT '+str(i) for i in range(80))
    before,receipt=apply_limit(native,'vdbe_op',64)
    assert receipt['effective_value']==source.getlimit(code)==64
    with pytest.raises(MemoryError):source.execute(query).fetchall()
    # SQLite reports SQLITE_NOMEM for this native opcode budget. Restoring
    # via the C limit API needs no SQL and does not replace this connection.
    with closing(sqlite3.connect(native[0])) as peer:
        assert peer.getlimit(code)==before
        assert len(peer.execute(query).fetchall())==80
    restored=run(native,'set_connection_limit',limit='vdbe_op',value=before,expected_value=64,confirmed=True)
    assert restored['effective_value']==before
    assert source.execute(query).fetchall()==[(i,)for i in range(80)]


def test_worker_threads_native_budget_alias_clamp_and_query_correctness(native):
    source=native[2];code=sqlite3.SQLITE_LIMIT_WORKER_THREADS
    before,receipt=apply_limit(native,'worker_threads',2)
    effective=source.getlimit(code)
    assert receipt['effective_value']==effective and 0<=effective<=2
    assert receipt['outcome']==('applied' if effective==2 else 'native_adjusted')
    assert source.execute('PRAGMA threads').fetchone()==(effective,)
    source.execute('CREATE TABLE sort_owned(value)')
    source.executemany('INSERT INTO sort_owned VALUES(?)',[(i,)for i in range(100,-1,-1)])
    assert source.execute('SELECT value FROM sort_owned ORDER BY value').fetchall()==[(i,)for i in range(101)]
    assert source.in_transaction
    with closing(sqlite3.connect(native[0])) as peer:assert peer.getlimit(code)==before
    run(native,'set_connection_limit',limit='worker_threads',value=before,expected_value=effective,confirmed=True)
    assert source.in_transaction
    source.rollback()
