"""Portable delivery ownership, bounded bytes and interruption semantics."""
import base64
import json
from unittest.mock import Mock

import pytest

from tools.tests.test_firebird_result_stream import Blob, stream
from tools.tests.test_firebird_async_queries import rig  # noqa: F401
from pgadmin.cdeadmin.providers.firebird.file_download import FileDownload
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def blob_download(payload):
    reader = Blob(payload)
    reader.length = len(payload)
    result = stream([(reader,)])
    reference = result.fetch(0)['rows'][0][0]['blob_reference']
    delivery = FileDownload(result, 'blob', reference)
    result.download = delivery
    return result, delivery


def call(delivery, action, **values):
    return delivery.dispatch('download_' + action,
                             {'download_id': delivery.identifier, **values})


@pytest.mark.parametrize('payload', [
    b'', b'a' * 65536, bytes(range(256)) * 999])
def test_exact_bytes_one_claim_and_explicit_http_completion(payload):
    result, delivery = blob_download(payload)
    try:
        assert delivery.status()['content_length'] == len(payload)
        assert call(delivery, 'open')['state'] == 'sending'
        with pytest.raises(RelationalClientError, match='claimed'):
            call(delivery, 'open')
        output = bytearray()
        sequence = 0
        while True:
            part = call(delivery, 'chunk', sequence=sequence)
            raw = base64.b64decode(part['data'])
            assert len(raw) <= 65536
            output.extend(raw)
            if part['complete']:
                break
            sequence += 1
        assert bytes(output) == payload
        assert delivery.state == 'sending'
        assert call(delivery, 'finish')['state'] == 'sent'
        assert call(delivery, 'abort')['state'] == 'sent'
    finally:
        result.close()


def test_cancelled_delivery_cannot_pull_or_reclaim_and_close_retains_outcome():
    result, delivery = blob_download(b'x' * 100000)
    call(delivery, 'open')
    call(delivery, 'chunk', sequence=0)
    call(delivery, 'abort')
    for action in ('open', 'chunk', 'finish'):
        with pytest.raises(RelationalClientError):
            call(delivery, action, sequence=1)
    with pytest.raises(RelationalClientError, match='unread'):
        FileDownload(result, 'blob', delivery.reference)
    result.close()
    assert delivery.state == 'interrupted'


def test_wrong_identity_out_of_order_and_length_mismatch():
    result, delivery = blob_download(b'abc')
    try:
        with pytest.raises(RelationalClientError, match='unavailable'):
            delivery.dispatch('download_open', {'download_id': 'other'})
        call(delivery, 'open')
        with pytest.raises(RelationalClientError, match='continuation'):
            call(delivery, 'chunk', sequence=True)
        with pytest.raises(RelationalClientError, match='incomplete'):
            call(delivery, 'finish')
        delivery.length = 4
        with pytest.raises(RelationalClientError, match='length changed'):
            call(delivery, 'chunk', sequence=0)
        assert delivery.state == 'interrupted'
    finally:
        result.close()


def test_array_header_slices_and_mandatory_footer():
    native = Mock()
    native.closed = native.failed = False
    reader = Mock()
    reader.describe.return_value = dict(bounds=[[-2, -1]], element_count=2,
                                        native_element_type=8, scale=0,
                                        subtype=0, charset_id=None)
    native.arrays = {'array': {'offset': 0, 'last': None, 'reader': reader}}
    native.read_array.return_value = dict(
        offset=0, next_offset=2, coordinates=[-2], values=[4, 5],
        complete=True)
    delivery = FileDownload(native, 'array', 'array')
    call(delivery, 'open')
    records = []
    for sequence in range(3):
        part = call(delivery, 'chunk', sequence=sequence)
        records.append(json.loads(base64.b64decode(part['data'])))
        assert part['complete'] == (sequence == 2)
    assert records[0]['format'] == 'cdeadmin.firebird-array.v1'
    assert records[1] == dict(offset=0, coordinates=[-2], values=[4, 5])
    assert records[2] == dict(complete=True, element_count=2)
    native.read_array.assert_called_once_with('array', 0)


def test_session_reservation_blocks_page_reads_and_wrong_owners(rig):
    result, delivery = blob_download(b'xyz')
    state = rig.client._state(rig.handle)
    state.result_stream = result
    state.stream_owner = 'owner'
    base = dict(owner_id='owner', stream_reference=result.reference,
                download_id=delivery.identifier)
    for action in ('next', 'blob', 'array'):
        with pytest.raises(RelationalClientError, match='Finish or stop'):
            rig.client.query_stream(
                rig.handle, dict(base, stream_action=action))
    with pytest.raises(RelationalClientError, match='another workspace'):
        rig.client.query_stream(rig.handle, dict(
            base, owner_id='other', stream_action='download_open'))
    rig.client.query_stream(rig.handle, dict(
        base, stream_action='download_status'))
    assert state.stream_last_activity is not None
    before = state.stream_last_activity
    with state.lock:
        rig.client.query_stream(rig.handle, dict(
            base, stream_action='download_status'))
    assert state.stream_last_activity == before
    rig.client.query_stream(rig.handle, dict(base, stream_action='close'))
    assert delivery.state == 'interrupted'


def test_http_response_is_incremental_and_disconnect_aborts():
    from flask import Flask
    from pgadmin.cdeadmin.workspace.firebird_download import response
    app = Flask(__name__)
    result, delivery = blob_download(b'x' * 200000)
    service = Mock()

    def invoke(server, session, request, target):
        return delivery.dispatch(request['stream_action'], request)

    service.query_stream.side_effect = invoke
    body = {'session_id': 'session', 'database_target_id': 'target',
            'request': {'owner_id': 'owner',
                        'stream_reference': result.reference,
                        'download_id': delivery.identifier}}
    try:
        with app.test_request_context('/'):
            output = response(service, object(), body)
            assert output.content_length == 200000
            assert output.headers['Cache-Control'] == 'no-store, private'
            assert delivery.bytes == 0
            first = next(iter(output.response))
            assert len(first) == 65536
            assert delivery.bytes == 65536
            output.close()
            assert delivery.state == 'interrupted'
            assert service.query_stream.call_count == 3
    finally:
        result.close()


def test_status_and_abort_do_not_wait_for_native_read_or_yield_after_stop():
    import threading
    result, delivery = blob_download(b'x' * 100000)
    reader = result.blobs[delivery.reference]['reader']
    entered, release = threading.Event(), threading.Event()
    original = reader.read
    failures = []

    def read(size):
        entered.set()
        assert release.wait(5)
        return original(size)

    def pull():
        try:
            call(delivery, 'chunk', sequence=0)
        except RelationalClientError as error:
            failures.append(str(error))

    reader.read = read
    call(delivery, 'open')
    worker = threading.Thread(target=pull)
    worker.start()
    try:
        assert entered.wait(5)
        assert call(delivery, 'status')['state'] == 'sending'
        assert call(delivery, 'abort')['state'] == 'interrupted'
    finally:
        release.set()
        worker.join(5)
        result.close()
    assert not worker.is_alive()
    assert failures == ['File delivery was stopped']
    assert delivery.bytes == 0
