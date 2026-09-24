"""Bounded native cursor/BLOB pulls and retry/cleanup ownership."""
import base64
import io
from dataclasses import replace
from unittest.mock import Mock

import pytest

from tools.tests.test_firebird_async_queries import rig  # noqa: F401
from pgadmin.cdeadmin.providers.firebird.result_stream import (
    BLOB_BYTES, PAGE_BYTES, PAGE_ROWS, BlobUpload, ResultStream,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


class Blob(io.BytesIO):
    sub_type = 1

    def read(self, size=-1):
        assert 0 <= size <= BLOB_BYTES
        return super().read(size)


def stream(rows):
    cursor = Mock()
    cursor.fetchone.side_effect = iter([*rows, None])
    return ResultStream(cursor, [{'name': 'V'}], Blob)


def test_pages_are_pulled_without_lookahead_and_retries_do_not_fetch():
    result = stream([(i,) for i in range(PAGE_ROWS + 2)])
    first = result.fetch(0)
    assert len(first['rows']) == PAGE_ROWS
    assert result.cursor.fetchone.call_count == PAGE_ROWS
    assert not first['end_of_cursor']
    assert result.fetch(0) == first
    assert result.cursor.fetchone.call_count == PAGE_ROWS
    last = result.fetch(1)
    assert last['rows'] == [[100], [101]]
    assert last['end_of_cursor']
    assert result.page is not first
    assert result.fetch(1) == last
    with pytest.raises(RelationalClientError):
        result.fetch(2)
    result.close()
    result.close()
    result.cursor.close.assert_called_once()


@pytest.mark.parametrize('payload', [
    b'', b'x' * BLOB_BYTES, ('é漢🙂' * 20000).encode('utf-8'),
])
def test_blob_chunks_are_bounded_lossless_and_retryable(payload):
    reader = Blob(payload)
    result = stream([(reader,)])
    page = result.fetch(0)
    reference = page['rows'][0][0]['blob_reference']
    assert reader.tell() == 0
    assert reader.sub_type == 0
    offset, collected = 0, bytearray()
    while True:
        part = result.read_blob(reference, offset)
        assert result.read_blob(reference, offset) == part
        data = base64.b64decode(part['data'])
        assert len(data) <= BLOB_BYTES
        collected.extend(data)
        offset = part['next_offset']
        if part['complete']:
            break
    assert bytes(collected) == payload
    assert reader.closed
    result.close()


def test_next_page_expires_blob_references_and_closes_unread_blob():
    reader = Blob(b'x' * 200000)
    result = stream([(reader,)] + [(i,) for i in range(100)])
    reference = result.fetch(0)['rows'][0][0]['blob_reference']
    result.fetch(1)
    assert reader.closed
    with pytest.raises(RelationalClientError, match='unavailable'):
        result.read_blob(reference, 0)


@pytest.mark.parametrize('sequence', [True, -1, '0', None, 2])
def test_invalid_sequences_never_fetch(sequence):
    result = stream([(1,)])
    with pytest.raises(RelationalClientError):
        result.fetch(sequence)
    result.cursor.fetchone.assert_not_called()


def test_payload_budget_and_no_total_result_retention():
    result = stream([('x' * (PAGE_BYTES // 2),)] * 100)
    page = result.fetch(0)
    assert len(page['rows']) == 2
    assert result.cursor.fetchone.call_count == 2
    result.fetch(1)
    assert result.rows_read == 4
    assert len(result.page['rows']) == 2


def test_oversized_scalar_fails_without_reexecution_and_retains_cleanup():
    reader = Blob(b'owned')
    result = stream([('x' * PAGE_BYTES, reader)])
    with pytest.raises(RelationalClientError, match='budget'):
        result.fetch(0)
    with pytest.raises(RelationalClientError, match='must be closed'):
        result.fetch(0)
    result.close()
    assert reader.closed
    result.cursor.execute.assert_not_called()


def test_failed_cursor_close_is_retryable():
    result = stream([])
    result.cursor.close.side_effect = [RuntimeError('owned'), None]
    with pytest.raises(RuntimeError):
        result.close()
    assert not result.closed
    result.close()
    assert result.closed


def test_active_stream_blocks_other_session_work_and_is_closed_on_detach(rig):
    result = Mock()
    state = rig.client._state(rig.handle)
    state.result_stream = result
    with pytest.raises(RelationalClientError, match='streaming result'):
        rig.client.execute(rig.handle, {'source': 'select 1'})
    rig.client.close_session(rig.handle)
    result.close.assert_called_once()


def test_upload_retries_bounds_and_disk_cleanup():
    upload = BlobUpload()
    try:
        encoded = base64.b64encode(b'x' * BLOB_BYTES).decode('ascii')
        assert upload.append(0, encoded) == BLOB_BYTES
        assert upload.append(0, encoded) == BLOB_BYTES
        with pytest.raises(RelationalClientError):
            upload.append(0, 'eQ==')
        with pytest.raises(RelationalClientError):
            upload.append(BLOB_BYTES, encoded + 'AAAA')
        assert upload.finish().read() == b'x' * BLOB_BYTES
        with pytest.raises(RelationalClientError):
            upload.append(BLOB_BYTES, 'eQ==')
    finally:
        upload.close()
    assert upload.file.closed


@pytest.mark.parametrize('value', ['%', 'λ', '!', 'AAAA=garbage'])
def test_invalid_upload_encoding(value):
    upload = BlobUpload()
    try:
        with pytest.raises((RelationalClientError, ValueError)):
            upload.append(0, value)
        assert upload.size == 0
    finally:
        upload.close()


def test_upload_quota_rejects_before_writing(monkeypatch):
    from pgadmin.cdeadmin.providers.firebird import result_stream
    monkeypatch.setattr(result_stream, 'UPLOAD_BYTES', 2)
    upload = BlobUpload()
    try:
        with pytest.raises(RelationalClientError, match='limit'):
            upload.append(0, 'YWJj')
        assert upload.size == 0
        assert upload.finish().read() == b''
    finally:
        upload.close()


def test_failed_upload_write_cannot_be_replayed():
    upload = BlobUpload()
    upload.file.close()
    upload.file = Mock()
    upload.file.write.side_effect = OSError('owned disk failure')
    with pytest.raises(OSError):
        upload.append(0, 'eA==')
    with pytest.raises(RelationalClientError, match='must be closed'):
        upload.append(0, 'eA==')
    with pytest.raises(RelationalClientError, match='must be closed'):
        upload.finish()
    upload.close()
    upload.file.close.assert_called_once()


def test_stream_cancel_only_targets_active_native_call_and_clears_signal(rig):
    client, handle = rig.client, rig.handle
    assert not client.cancel_result_stream(handle)['cancel_request_accepted']
    state = client._state(handle)
    with client._stream_native_call(handle, state):
        assert client.cancel_result_stream(handle)['cancel_request_accepted']
    calls = handle._att.cancel_operation.call_args_list
    assert [call.args[0] for call in calls] == [3, 1, 2]
    assert not state.stream_running


@pytest.mark.parametrize('action', ['close', 'cancel', 'next', 'blob'])
def test_stale_workspace_cannot_close_or_control_new_owner(rig, action):
    state = rig.client._state(rig.handle)
    state.result_stream = Mock()
    state.stream_owner = 'new-workspace'
    with pytest.raises(RelationalClientError, match='another workspace'):
        rig.client.query_stream(rig.handle, {
            'stream_action': action, 'owner_id': 'old-workspace',
        })
    state.result_stream.close.assert_not_called()
    rig.handle._att.cancel_operation.assert_not_called()


def test_stream_cancel_cleanup_failure_quarantines_session(rig):
    state = rig.client._state(rig.handle)
    with pytest.raises(RuntimeError):
        with rig.client._stream_native_call(rig.handle, state):
            rig.client.cancel_result_stream(rig.handle)
            rig.handle._att.cancel_operation.side_effect = RuntimeError(
                'owned')
    assert state.cancellation_state_unknown
    with pytest.raises(RelationalClientError, match='unknown'):
        with rig.client._exclusive(rig.handle):
            pytest.fail('quarantined session admitted')


def test_stream_boundary_uses_admitted_session_not_request_override():
    from tools.tests.test_cdeadmin_data_studio import (
        context, endpoint_payload, harness,
    )
    from pgadmin.cdeadmin.data_studio import DataStudioAccessError
    ctx, provider, _registry, service = harness()
    service.open_session(ctx, endpoint_payload(ctx), 'example-sql')
    provider.query_stream = Mock(return_value={'rows': []})
    native_ctx = replace(ctx, provider_id='org.cdeadmin.firebird')
    result = service.query_stream(native_ctx, 'session-one', {
        'stream_action': 'next', 'session_id': 'injected',
    })
    assert result == {'rows': []}
    admitted = provider.query_stream.call_args.args[0]
    assert admitted['session_id'] == 'session-one'
    with pytest.raises(DataStudioAccessError, match='another endpoint'):
        service.query_stream(context('other'), 'session-one', {})
    with pytest.raises(DataStudioAccessError, match='not admitted'):
        service.query_stream(ctx, 'session-one', {})
    with pytest.raises(DataStudioAccessError, match='unavailable'):
        service.query_stream(native_ctx, 'missing', {})
    provider.query_stream.assert_called_once()
