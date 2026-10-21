"""Native warning rows and errors survive application regex warning filters."""
from types import SimpleNamespace,MethodType
import warnings

import pytest
from mysql.connector.cursor import MySQLCursor
from mysql.connector.errors import DatabaseError,Warning as NativeWarning
from pgadmin.cdeadmin.providers.mysql_family.mysql_warnings import adapted


def cursor(raise_on_warnings=False):
    rows=[('Warning',1292,'Truncated incorrect key_cache_block_size value')]
    value=SimpleNamespace(_connection=SimpleNamespace(get_warnings=True,raise_on_warnings=raise_on_warnings),
        _warning_count=1,_warnings=None,_fetch_warnings=lambda:rows)
    value.handle=MethodType(adapted(MySQLCursor._handle_warnings),value)
    return value,rows


def test_native_warning_message_is_text_and_warning_rows_remain_native_under_regex_filters():
    native,rows=cursor();original=warnings.warn
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter('always');warnings.filterwarnings('ignore',message='unrelated native message')
        native.handle()
    assert warnings.warn is original and native._warnings==rows
    assert len(seen)==1 and str(seen[0].message)==str(NativeWarning(*rows[0][1:]))


def test_native_raise_on_warnings_still_raises_the_original_native_error():
    native,rows=cursor(True)
    with pytest.raises(DatabaseError) as error:native.handle()
    assert error.value.errno==1292 and native._warnings==rows


def test_python_warning_policy_can_still_promote_the_native_warning_to_an_error():
    native,_rows=cursor()
    with warnings.catch_warnings():
        warnings.filterwarnings('error',message=r'\(1292,.*')
        with pytest.raises(UserWarning):native.handle()
