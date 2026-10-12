"""Exact MySQL conversion, loss refusal and Unicode control-query restoration."""
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.providers.mysql_statement_encoding import statement_context

CONTEXT = {'character_set_client':'latin1','collation_connection':'utf8mb4_bin'}


def test_native_conversion_retains_mysql_latin1_euro_and_restores_unicode_controls():
    connection,cursor=Mock(),Mock()
    source="SELECT 'é€'";cursor.fetchone.return_value=(source.encode('cp1252'),source)
    with statement_context(connection,cursor,source,CONTEXT) as encoded:
        assert encoded==b"SELECT '\xe9\x80'"
        assert cursor.execute.call_args.args==('SET SESSION collation_connection=%s',('utf8mb4_bin',))
    assert connection.set_charset_collation.call_count==2
    cursor.close.assert_not_called()


@pytest.mark.parametrize('context,source,observed',[
    (CONTEXT,"SELECT '漢'",(b"SELECT '?'","SELECT '?'")),
    ({**CONTEXT,'character_set_client':'latin1; DROP'},'SELECT 1',None),
    ({**CONTEXT,'character_set_client':'utf8mb3'},"SELECT '😀'",None),
])
def test_loss_or_invalid_context_refuses_body(context,source,observed):
    connection,cursor=Mock(),Mock();cursor.fetchone.return_value=observed
    with pytest.raises(ValueError):
        with statement_context(connection,cursor,source,context):
            pytest.fail('Unrepresentable statement reached dispatch')


def test_unknown_dispatch_exception_is_not_masked_by_successful_context_restore():
    connection,cursor=Mock(),Mock()
    with pytest.raises(OSError):
        with statement_context(connection,cursor,'SELECT 1',{'character_set_client':'utf8mb4','collation_connection':'latin1_bin'}) as encoded:
            assert encoded=='SELECT 1'
            raise OSError('lost reply')
    assert connection.set_charset_collation.call_count==2
