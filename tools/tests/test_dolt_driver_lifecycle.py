"""Dolt bindings and SQL/version-control boundary regressions."""
from unittest.mock import Mock

from test_cdeadmin_distributed_providers import DOLT
from pgadmin.cdeadmin.sdk.relational import RelationalClientConfig
from pgadmin.cdeadmin.providers.dolt.driver import (
    DoltConverter, DoltNativeClient,
)


def test_arbitrary_binary_binding_has_ascii_only_native_literal():
    converter = DoltConverter(charset='utf8mb4')
    value = bytes(range(256)) + b"'); CALL DOLT_COMMIT('-am','bad'); --"
    converted = converter.to_mysql(value)
    escaped = converter.escape(converted, 'NO_BACKSLASH_ESCAPES')
    result = converter.quote(escaped)
    assert result == b"X'" + value.hex().encode('ascii') + b"'"
    assert result.decode('ascii')


def test_text_is_still_escaped_and_quoted_by_native_connector():
    converter = DoltConverter(charset='utf8mb4')
    converted = converter.to_mysql("a'b")
    assert converter.quote(converter.escape(converted)) == b"'a\\'b'"


def test_sql_commit_does_not_create_a_version_control_commit():
    config = RelationalClientConfig(
        profile=DOLT, module_name='mysql.connector', version_query='SELECT 1',
        version_parser=lambda row: '1.86.6', connect_arguments=lambda r: r,
        metadata_reader=lambda *_: [], security_reader=lambda *_: {})
    client = DoltNativeClient(config, module=Mock())
    handle = Mock(in_transaction=False)
    client._connections.append(handle)
    client._states[id(handle)] = {}
    client._requests[id(handle)] = {}
    client.control_transaction(handle, 'commit')
    handle.commit.assert_called_once()
    handle.cursor.assert_not_called()
    assert client.describe_transaction(handle)['command_returned']
    client.close()
