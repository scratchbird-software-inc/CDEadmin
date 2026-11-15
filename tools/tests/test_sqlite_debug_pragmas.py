"""Actual release-build refusal and DEBUG-build original-handle controls."""
import sqlite3
import pytest
from test_sqlite_connection_pragmas import native,run  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.connection_pragmas import DEBUG_FLAGS
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations,operation_draft


@pytest.mark.parametrize('name',DEBUG_FLAGS)
def test_debug_native_gate_and_sensitive_output_ack(native,name):
    source=native[2]
    debugging='DEBUG'in {row[0]for row in source.execute('PRAGMA compile_options')}
    names={row[0]for row in source.execute('PRAGMA pragma_list')}
    if not debugging or name not in names:
        with pytest.raises(RelationalClientError,match='SQLITE_DEBUG'):run(native,'review',pragma=name,value=True)
        return
    source.executescript('CREATE TABLE owned(value);SAVEPOINT caller;INSERT INTO owned VALUES(7)')
    before=run(native,'inspect',pragma=name)['effective_value']
    with pytest.raises(RelationalClientError,match='sensitive'):
        run(native,'set_connection_pragma',pragma=name,value=True,expected_value=before,confirmed=True)
    review=run(native,'review',pragma=name,value=True)
    draft=operation_draft(engine_operations('sqlite')['set_connection_pragma_'+name+'@database'],
        {'value':True,'expected_value':review['expected_value'],'confirmed':True,'sensitive_output_confirmed':True})
    result=run(native,'set_connection_pragma',pragma=name,**draft)
    assert result['effective_value']is True and result['sensitive_host_output_possible']
    assert source.in_transaction
    # Explicitly disable native output; this is test fixture cleanup, not an
    # application promise to restore original flags or host diagnostics.
    run(native,'set_connection_pragma',pragma=name,value=False,expected_value=True,confirmed=True)
    assert source.execute('SELECT * FROM owned').fetchall()==[(7,)]
    source.execute('ROLLBACK TO caller');source.execute('RELEASE caller')
    assert source.execute('SELECT * FROM owned').fetchall()==[]
