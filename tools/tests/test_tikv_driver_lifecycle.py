"""Retained helper protocol, paging and TLS policy regression checks."""
import base64
import io
from unittest.mock import Mock

import pytest
import test_cdeadmin_distributed_providers  # noqa: F401
from pgadmin.cdeadmin.providers.tikv.driver import (
    TiKVDriverBackend, HelperOwner,
)


def test_paged_raw_scan_continues_after_binary_key_without_duplication():
    backend = TiKVDriverBackend()
    route = backend._route({'route': {'pd_endpoints': ['localhost:2379']}})
    owner = HelperOwner(None, route)
    first = [{'key_base64': base64.b64encode(bytes([i])).decode(),
              'value': 'v'} for i in range(256)]
    replies = [(first, {}), ([{'key_base64': '/wA=', 'value': 'last'}], {})]
    backend._rpc = Mock(side_effect=replies)
    pages = list(backend.iterate(owner, {'operation': 'scan_all'}, None))
    assert [len(p.records) for p in pages] == [256, 1]
    assert pages[-1].native['row_offset'] == 256
    assert backend._rpc.call_args.args[1]['start_key_base64'] == '/wA='
    assert pages[0].native['scan_consistency'] == 'raw-live-range'


def test_txn_scan_uses_native_more_flag_even_for_short_byte_limited_pages():
    backend = TiKVDriverBackend()
    route = backend._route({'route': {'pd_endpoints': ['localhost:2379']}})
    owner = HelperOwner(None, route)
    backend._rpc = Mock(side_effect=[
        ([{'key_base64': 'AA=='}], {'more': True}),
        ([{'key_base64': 'AAA='}], {'more': False})])
    pages = list(
        backend.iterate(
            owner, {
                'operation': 'txn_scan', 'end_key': 'z'}, None))
    assert len(pages) == 2
    assert pages[1].native['row_offset'] == 1
    assert pages[0].native['scan_consistency'] == 'native-transaction-snapshot'


def test_protocol_refusal_cannot_be_interpreted_as_success():
    backend = TiKVDriverBackend()
    process = Mock(stdin=io.BytesIO(), stdout=io.BytesIO(
        b'{"error":"private native detail"}\n'))
    process.poll.return_value = None
    owner = HelperOwner(process, {'operation_timeout': 1})
    with pytest.raises(RuntimeError, match='native request failed') as error:
        backend._rpc(owner, {'operation': 'commit'})
    assert 'private' not in str(error.value)
    assert process.stdin.getvalue() == b'{"operation":"commit"}\n'


def test_unknown_close_kills_without_issuing_commit_or_rollback():
    backend = TiKVDriverBackend()
    process = Mock()
    process.poll.side_effect = [None, 0]
    owner = HelperOwner(process, {})
    backend._rpc = Mock()
    backend.close_session(owner, True)
    process.kill.assert_called_once()
    process.wait.assert_called_once()
    backend._rpc.assert_not_called()
    process.stdin.close.assert_called_once()


def test_pd_https_cannot_silently_use_plaintext_native_transport():
    with pytest.raises(RuntimeError, match='TLS policies disagree'):
        TiKVDriverBackend._route({'route': {'pd_endpoints': ['localhost:2379'],
                                            'pd_http_scheme': 'https'}})
