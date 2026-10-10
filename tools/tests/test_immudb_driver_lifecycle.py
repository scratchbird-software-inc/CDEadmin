"""Native immudb bindings and retained-session failure ownership."""
from unittest.mock import Mock, patch

import pytest

from test_cdeadmin_distributed_providers import IMMUDB
from pgadmin.cdeadmin.sdk.relational import RelationalClientConfig
from pgadmin.cdeadmin.providers.immudb.provider import ImmudbDBAPIClient
from pgadmin.cdeadmin.providers.immudb.driver import BlobDumper
from pgadmin.cdeadmin.providers.temporal_wire import TemporalExecution


@pytest.fixture
def owner():
    config = RelationalClientConfig(
        profile=IMMUDB, module_name='psycopg', version_query='SELECT 1',
        version_parser=lambda row: '1.11.0', connect_arguments=lambda r: r,
        metadata_reader=lambda *_: [], security_reader=lambda *_: {})
    client = ImmudbDBAPIClient(config, module=Mock())
    handle = Mock(closed=False)
    del handle._connection
    handle.info.transaction_status.name = 'IDLE'
    client._connections.append(handle)
    yield client, handle
    client.close()


def test_blob_literal_is_native_hex_and_cannot_inject():
    dumper = BlobDumper(bytes)
    assert dumper.oid == 0
    value = b"\x00\xff';DROP TABLE owned;--"
    assert dumper.quote(value) == b"x'" + value.hex().encode() + b"'"


def test_lossless_result_envelopes(owner):
    client, _ = owner
    assert client.json_value([9007199254740993, b'\x00\xff']) == [
        {'type': 'integer', 'value': '9007199254740993'},
        {'encoding': 'base64', 'data': 'AP8=', 'byte_length': 2}]


def test_unobserved_execution_blocks_decision_and_admin(owner):
    client, handle = owner
    token = TemporalExecution(client, handle, 'SELECT 1', ())
    token.finished.set()
    client._operations.append(token)
    with pytest.raises(RuntimeError, match='active'):
        client.control_transaction(handle, 'commit')
    with pytest.raises(RuntimeError, match='active'):
        client.runtime_identity({}, handle)
    with pytest.raises(RuntimeError, match='active'):
        client.read_admin_rows({'_provider_session_handle': handle})
    handle.cursor.assert_not_called()


def test_unknown_commit_is_never_replayed(owner):
    client, handle = owner
    handle.cursor.return_value.execute.side_effect = OSError
    with pytest.raises(RuntimeError, match='unknown'):
        client.control_transaction(handle, 'commit')
    with pytest.raises(RuntimeError, match='unknown'):
        client.control_transaction(handle, 'commit')
    handle.cursor.return_value.execute.assert_called_once_with('COMMIT')


def test_native_command_tag_preserved(owner):
    client, handle = owner
    handle.cursor.return_value.statusmessage = 'ROLLBACK'
    client.control_transaction(handle, 'commit')
    assert client.describe_transaction(
        handle)['native_observation'] == 'ROLLBACK'


def test_failed_close_retains_owner(owner):
    client, handle = owner
    handle.close.side_effect = OSError
    with pytest.raises(RuntimeError, match='cleanup'):
        client.close_session(handle)
    assert handle in client._connections
    handle.close.side_effect = None
    client.close_session(handle)
    assert not client._connections


def test_catalog_does_not_borrow_user_transaction(owner):
    client, handle = owner
    parent = 'pgadmin.cdeadmin.sdk.relational.RelationalDBAPIClient'
    with patch(parent + '.list_resources', return_value=[]) as metadata:
        # Test the SQL catalog seam without invoking native REST discovery.
        super(ImmudbDBAPIClient, client).list_resources({
            'route': {}, '_provider_session_handle': handle})
        metadata.assert_called_once_with({'route': {}})
