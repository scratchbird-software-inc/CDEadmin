"""Native conversion proof and exact-byte mysql-client output."""
import base64
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.providers.mysql_native_encoding import encode_metadata


def metadata():
    return {'database':'db漢','server_uuid':'server','statements':[{'resource_id':'p','name':'p','kind':'procedure',
        'statement':"CREATE PROCEDURE p() SELECT 'é€'",'context':{'sql_mode':'NO_BACKSLASH_ESCAPES','character_set_client':'latin1','collation_connection':'utf8mb4_bin'}}],
        'blockers':[],'native_encoding_required':True,'script':None}


def native(roundtrip=None):
    data=metadata();statement=data['statements'][0]['statement']
    cursor=Mock();cursor.fetchone.side_effect=[('9.7.0','server','db漢'),(statement.encode('cp1252'),statement if roundtrip is None else roundtrip)]
    connection=Mock(in_transaction=False);connection.cursor.return_value=cursor
    return connection,cursor,data


def test_native_conversion_accepts_independent_client_and_connection_charset_and_retains_bytes():
    connection,cursor,data=native();result=encode_metadata(connection,data)
    payload=base64.b64decode(result['encoded_script']['data_base64'])
    assert b'\\C latin1\n' in payload and b"SELECT '\xe9\x80'" in payload
    assert 'USE `db漢`'.encode('utf8') in payload
    assert result['script'] is None and result['script_available'] and not result['native_encoding_required']
    assert result['encoded_script']['byte_size']==len(payload)
    commands=[call.args[0] for call in cursor.execute.call_args_list]
    assert not any(command.startswith(('CREATE ','DROP ','ALTER ','EXECUTE ')) for command in commands)
    assert 'USING latin1' in commands[-1]
    cursor.close.assert_called_once()


def test_lossy_conversion_or_wrong_native_identity_cannot_produce_download():
    connection,cursor,data=native('lost text')
    with pytest.raises(ValueError,match='lose'):encode_metadata(connection,data)
    cursor.close.assert_called_once()
    connection,cursor,data=native();cursor.fetchone.side_effect=[('9.7.0','different','db漢')]
    with pytest.raises(ValueError,match='identity'):encode_metadata(connection,data)


def test_native_client_charset_refusal_restores_owned_utf8_connection_without_dispatch():
    connection,cursor,data=native()
    def execute(source,*args):
        if source.startswith('SET SESSION character_set_client'):raise RuntimeError('native charset refused')
    cursor.execute.side_effect=execute
    with pytest.raises(RuntimeError):encode_metadata(connection,data)
    assert connection.set_charset_collation.call_count==2
    cursor.close.assert_called_once()
