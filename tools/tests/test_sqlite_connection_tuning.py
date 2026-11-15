"""Real native timeouts, automatic checkpoints and bounded analysis."""
from contextlib import closing
import sqlite3
import time
from pathlib import Path
import pytest
from test_sqlite_connection_pragmas import native, run  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.connection_tuning import NAMES, CALLBACKS
from ui_descriptor_roundtrip import engine_operations, operation_draft


def set_tuning(native,name,value,*,ack=True):
    review=run(native,'review',pragma=name,value=value)
    op=engine_operations('sqlite')['set_connection_pragma_'+name+'@database']
    values={'value':value,'expected_value':review['expected_value'],'confirmed':True}
    if name in CALLBACKS:values['replace_callback_confirmed']=ack
    draft=operation_draft(op,values)
    result=run(native,'set_connection_pragma',pragma=name,**draft)
    assert result['effective_value']==value and result['outcome']=='applied'
    assert not any(result[k]for k in ['commit_requested','rollback_requested','file_persisted','future_connection_defaults_changed','automatic_retry'])
    return result


def test_busy_timeout_native_lock_wait_and_explicit_callback_replacement(native):
    source=native[2];source.execute('CREATE TABLE locked(value)');source.commit()
    with closing(sqlite3.connect(native[0])) as peer:
        peer.execute('BEGIN IMMEDIATE')
        result=set_tuning(native,'busy_timeout',0)
        assert result['callback_policy']=='busy_handler' and not result['callback_restoration_claimed']
        with pytest.raises(sqlite3.OperationalError) as error:source.execute('INSERT INTO locked VALUES(1)')
        assert error.value.sqlite_errorcode & 255 == sqlite3.SQLITE_BUSY
        source.rollback()
        set_tuning(native,'busy_timeout',1100)
        started=time.monotonic()
        with pytest.raises(sqlite3.OperationalError) as error:source.execute('INSERT INTO locked VALUES(2)')
        elapsed=time.monotonic()-started
        assert error.value.sqlite_errorcode & 255 == sqlite3.SQLITE_BUSY and elapsed>=0.8
        source.rollback();peer.rollback()


def test_wal_autocheckpoint_native_main_file_progress_is_not_transaction_finality(native,tmp_path):
    source=native[2]
    assert source.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
    source.execute('CREATE TABLE rows_owned(value)');source.commit()
    source.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchall()
    set_tuning(native,'wal_autocheckpoint',0)
    source.execute('INSERT INTO rows_owned VALUES(1)');source.commit()
    assert not source.in_transaction
    first=tmp_path/'physical-before.db';first.write_bytes(native[0].read_bytes())
    with closing(sqlite3.connect(first.as_uri()+'?immutable=1',uri=True)) as physical:
        assert physical.execute('SELECT count(*) FROM rows_owned').fetchone()==(0,)
    assert source.execute('SELECT * FROM rows_owned').fetchall()==[(1,)]
    result=set_tuning(native,'wal_autocheckpoint',1)
    assert result['callback_policy']=='wal_hook'
    source.execute('INSERT INTO rows_owned VALUES(2)');source.commit()
    second=tmp_path/'physical-after.db';second.write_bytes(native[0].read_bytes())
    with closing(sqlite3.connect(second.as_uri()+'?immutable=1',uri=True)) as physical:
        assert physical.execute('SELECT count(*) FROM rows_owned').fetchone()==(2,)


def test_analysis_limit_native_sampling_and_full_analysis(native):
    source=native[2]
    source.executescript('CREATE TABLE samples(value); CREATE INDEX sample_idx ON samples(value);')
    source.executemany('INSERT INTO samples VALUES(?)',[(i,)for i in range(1200)]);source.commit()
    steps=[0]
    def tick():
        steps[0]+=1
        return 0
    source.set_progress_handler(tick,1)
    try:
        set_tuning(native,'analysis_limit',5);steps[0]=0
        source.execute('ANALYZE samples /* limited */')
        limited=steps[0]
        assert source.execute("SELECT stat FROM sqlite_stat1 WHERE idx='sample_idx'").fetchone()[0]
        set_tuning(native,'analysis_limit',0);steps[0]=0
        source.execute('ANALYZE samples /* full */')
        full=steps[0]
        assert full>limited
        stat=source.execute("SELECT stat FROM sqlite_stat1 WHERE idx='sample_idx'").fetchone()[0]
        assert int(stat.split()[0])==1200
    finally:source.set_progress_handler(None,0)


@pytest.mark.parametrize('name',NAMES)
def test_numeric_isolation_stale_savepoint_and_mixed_file_refusal(native,name):
    from pgadmin.cdeadmin.sdk import RelationalClientError
    source=native[2]
    with closing(sqlite3.connect(native[0])) as peer:
        peer_before=peer.execute('PRAGMA '+name).fetchone()[0]
        before=run(native,'inspect',pragma=name)['effective_value']
        value=3 if before!=3 else 4
        source.executescript('CREATE TABLE pending(value); SAVEPOINT caller; INSERT INTO pending VALUES(7)')
        result=set_tuning(native,name,value)
        assert result['transaction_open'] and peer.execute('PRAGMA '+name).fetchone()[0]==peer_before
        args=dict(pragma=name,value=before,expected_value=before,confirmed=True)
        if name in CALLBACKS:args['replace_callback_confirmed']=True
        with pytest.raises(RelationalClientError,match='changed'):run(native,'set_connection_pragma',**args)
        source.execute('ROLLBACK TO caller')
        assert source.execute('SELECT * FROM pending').fetchall()==[]
        assert run(native,'inspect',pragma=name)['effective_value']==value
        source.execute('RELEASE caller')
        with pytest.raises(RelationalClientError,match='connection-local'):
            native[1].plan_admin_operation({'resource_kind':'database','operation_id':'alter',
                '_provider_route':{'database':str(native[0]),'filesystem_root':str(native[0].parent)},
                'target_resource':{'display_name':'main','display_path':['main']},
                'draft':{'journal_mode':'WAL',name:value}})
        assert source.execute('PRAGMA journal_mode').fetchone()[0]!='wal'


@pytest.mark.parametrize('name',NAMES)
@pytest.mark.parametrize('bad',[True,-1,2147483648,'3',None,1.5])
def test_numeric_invalid_values_never_mutate(native,name,bad):
    from pgadmin.cdeadmin.sdk import RelationalClientError
    before=run(native,'inspect',pragma=name)['effective_value']
    with pytest.raises(RelationalClientError):run(native,'review',pragma=name,value=bad)
    assert run(native,'inspect',pragma=name)['effective_value']==before


@pytest.mark.parametrize('name',list(CALLBACKS))
def test_numeric_callback_replacement_requires_separate_confirmation(native,name):
    from pgadmin.cdeadmin.sdk import RelationalClientError
    before=run(native,'inspect',pragma=name)['effective_value']
    with pytest.raises(RelationalClientError,match='callback'):
        run(native,'set_connection_pragma',pragma=name,value=3,expected_value=before,confirmed=True)
    assert run(native,'inspect',pragma=name)['effective_value']==before


@pytest.mark.parametrize('missing',[True,False])
def test_numeric_missing_getter_and_failed_readback_never_claim_success(missing):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from pgadmin.cdeadmin.sdk import RelationalClientError
    from pgadmin.cdeadmin.providers.sqlite.connection_tuning import action
    cursor=Mock();cursor.execute.return_value.fetchone.side_effect=[None] if missing else [(0,),(0,)]
    with pytest.raises(RelationalClientError) as error:
        action(SimpleNamespace(cursor=lambda:cursor,in_transaction=False),
            {'operation':'set_connection_pragma','pragma':'analysis_limit','value':3,'expected_value':0,'confirmed':True})
    assert error.value.native_outcome==('not_dispatched' if missing else 'unknown_outcome')
    assert len(cursor.execute.call_args_list)==(1 if missing else 3)
    cursor.close.assert_called_once()
