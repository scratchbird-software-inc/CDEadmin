"""Native setter-only callback policy with a one-use source revision review."""
import pytest
from test_sqlite_connection_pragmas import native,run  # noqa: F401
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations,operation_draft


def review(native,value,revision=0):
    return run(native,'review',pragma='case_sensitive_like',value=value,_native_work_revision=revision)


def apply(native,value,receipt,revision=0):
    fields=operation_draft(engine_operations('sqlite')['set_connection_pragma_case_sensitive_like@database'],
        {'value':value,'review_id':receipt['review_id'],'replace_callback_confirmed':True,'confirmed':True})
    return run(native,'set_connection_pragma',pragma='case_sensitive_like',_native_work_revision=revision,**fields)


def test_native_like_replacement_never_probes_or_restores_unknown_application_callbacks(native):
    source=native[2];calls=[]
    def previous(*args):calls.append(args);return 17
    source.create_function('like',2,previous)
    source.executescript('CREATE TABLE pending(value);SAVEPOINT caller;INSERT INTO pending VALUES(7)')
    receipt=review(native,True)
    assert calls==[] and receipt['before_value'] is None and not receipt['before_value_observed']
    result=apply(native,True,receipt)
    assert result['native_pattern_probe']==[0,1,0,1] and calls==[]
    assert source.in_transaction and source.execute('SELECT * FROM pending').fetchall()==[(7,)]
    source.execute('ROLLBACK TO caller')
    assert source.execute("SELECT 'a' LIKE 'A'").fetchone()==(0,)
    assert not result['callback_restoration_claimed'] and not result['file_persisted']
    with pytest.raises(RelationalClientError):apply(native,True,receipt)
    apply(native,False,review(native,False))
    assert source.execute("SELECT 'a' LIKE 'A'").fetchone()==(1,)
    source.execute('RELEASE caller')


def test_policy_stale_revision_value_and_missing_ack_refuse_before_native_replacement(native):
    receipt=review(native,True)
    with pytest.raises(RelationalClientError):apply(native,True,receipt,revision=1)
    with pytest.raises(RelationalClientError):apply(native,False,receipt)
    with pytest.raises(RelationalClientError):
        run(native,'set_connection_pragma',pragma='case_sensitive_like',value=True,review_id=receipt['review_id'],confirmed=True,_native_work_revision=0)
    assert native[2].execute("SELECT 'a' LIKE 'A'").fetchone()==(1,)


def test_native_unknown_pattern_readback_consumes_review_and_never_replays(native):
    import sqlite3
    source=native[2];receipt=review(native,True)
    def authorize(code,a,b,*_):
        if code==sqlite3.SQLITE_FUNCTION and b=='like':return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    source.set_authorizer(authorize)
    with pytest.raises(RelationalClientError) as error:apply(native,True,receipt)
    assert error.value.native_outcome=='unknown_outcome'
    source.set_authorizer(None)
    assert source.execute("SELECT 'a' LIKE 'A'").fetchone()==(0,)
    with pytest.raises(RelationalClientError):apply(native,True,receipt)
