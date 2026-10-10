"""Idle resource cleanup preserves native ownership and transaction outcome."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.tests.test_firebird_async_queries import rig  # noqa: F401
from pgadmin.cdeadmin.providers.firebird import query_client, stream_leases
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.fixture
def clock(monkeypatch):
    value = SimpleNamespace(now=0, watched=[])
    monkeypatch.setattr(query_client, 'time', SimpleNamespace(
        monotonic=lambda: value.now))
    monkeypatch.setattr(stream_leases, 'watch', value.watched.append)
    return value


def upload(rig, owner='owned'):
    return rig.client.query_stream(rig.handle, {
        'stream_action': 'upload_begin', 'owner_id': owner})


def test_idle_upload_preserves_attachment_and_transaction(rig, clock):
    token = upload(rig)
    state = rig.client._state(rig.handle)
    spool = state.blob_upload
    assert clock.watched == [rig.client]
    rig.client.reap_idle_streams(now=299)
    assert not spool.closed
    rig.client.reap_idle_streams(now=300)
    assert spool.closed and state.blob_upload is None
    assert state.stream_expired and state.stream_owner == 'owned'
    for method in ('commit', 'rollback', 'close'):
        getattr(rig.handle, method).assert_not_called()
    assert rig.handle in rig.client._connections
    with pytest.raises(RelationalClientError, match='expired'):
        rig.client.query_stream(rig.handle, {
            'stream_action': 'upload_finish', 'owner_id': 'owned', **token})
    with pytest.raises(RelationalClientError, match='another workspace'):
        rig.client.query_stream(rig.handle, {
            'stream_action': 'close', 'owner_id': 'other'})
    assert state.stream_expired
    rig.client.query_stream(rig.handle, {
        'stream_action': 'close', 'owner_id': 'owned'})
    assert not state.stream_expired
    upload(rig, 'new-owner')


def test_request_checks_deadline_before_renewing_without_waiting_for_sweep(
        rig, clock):
    token = upload(rig)
    clock.now = 300
    with pytest.raises(RelationalClientError, match='expired'):
        rig.client.query_stream(rig.handle, {
            'stream_action': 'upload_chunk', 'owner_id': 'owned',
            'offset': 0, 'data': 'eA==', **token})
    assert rig.client._state(rig.handle).blob_upload is None


def test_foreign_owner_cannot_extend_lease(rig, clock):
    token = upload(rig)
    clock.now = 250
    with pytest.raises(RelationalClientError, match='another workspace'):
        rig.client.query_stream(rig.handle, {
            'stream_action': 'upload_finish', 'owner_id': 'other', **token})
    assert rig.client._state(rig.handle).stream_last_activity == 0
    rig.client.reap_idle_streams(now=300)
    assert rig.client._state(rig.handle).stream_expired


def test_owner_activity_renews_and_busy_attachment_is_skipped(rig, clock):
    token = upload(rig)
    clock.now = 250
    rig.client.query_stream(rig.handle, {
        'stream_action': 'upload_finish', 'owner_id': 'owned', **token})
    state = rig.client._state(rig.handle)
    rig.client.reap_idle_streams(now=300)
    assert state.blob_upload is not None
    held, release = threading.Event(), threading.Event()

    def hold():
        with state.lock:
            held.set()
            release.wait(5)

    worker = threading.Thread(target=hold)
    worker.start()
    assert held.wait(5)
    try:
        rig.client.reap_idle_streams(now=600)
        assert state.blob_upload is not None
    finally:
        release.set()
        worker.join(5)
    rig.client.reap_idle_streams(now=600)
    assert state.blob_upload is None


def test_failed_cursor_cleanup_retains_owner_for_background_retry(rig, clock):
    state = rig.client._state(rig.handle)
    resource = Mock()
    resource.close.side_effect = [RuntimeError('owned'), None]
    state.result_stream = resource
    state.stream_owner = 'owned'
    state.stream_last_activity = 0
    rig.client.reap_idle_streams(now=300)
    assert state.result_stream is resource
    assert state.result_cleanup_failed and state.stream_expired
    rig.client.reap_idle_streams(now=330)
    assert state.result_stream is None
    assert state.stream_expired and state.stream_owner == 'owned'
    rig.handle.commit.assert_not_called()
    rig.handle.rollback.assert_not_called()


def test_native_call_completion_starts_idle_clock(rig, clock):
    state = rig.client._state(rig.handle)
    state.result_stream = Mock()
    state.stream_last_activity = 0
    with rig.client._stream_lease(rig.handle, state, 'next', None):
        state.stream_running = True
        clock.now = 900
        rig.client.reap_idle_streams()
        state.result_stream.close.assert_not_called()
        state.stream_running = False
    assert state.stream_last_activity == 900
    rig.client.reap_idle_streams(now=1199)
    state.result_stream.close.assert_not_called()
    resource = state.result_stream
    rig.client.reap_idle_streams(now=1200)
    resource.close.assert_called_once()


def test_scheduler_bounds_queue_and_does_not_duplicate_pending_clients():
    scheduler = stream_leases.StreamLeaseSweeper()
    clients = [Mock() for _ in range(25)]
    for client in clients:
        scheduler._clients.add(client)
    scheduler.schedule()
    assert scheduler._queue.qsize() == 16
    scheduler.schedule()
    assert scheduler._queue.qsize() == 16
    queued = [scheduler._queue.get_nowait() for _ in range(16)]
    assert len(set(queued)) == 16
    scheduler._pending.clear()
    scheduler.schedule()
    following = [scheduler._queue.get_nowait() for _ in range(16)]
    assert set(queued + following) == set(clients)


def test_scheduler_workers_run_without_new_owner_requests(monkeypatch):
    monkeypatch.setattr(stream_leases, 'SWEEP_SECONDS', 0.01)
    scheduler = stream_leases.StreamLeaseSweeper()
    called = threading.Event()
    client = Mock()
    client.reap_idle_streams.side_effect = called.set
    scheduler.watch(client)
    assert called.wait(5)


def test_stalled_cleanup_does_not_block_the_other_worker(monkeypatch):
    monkeypatch.setattr(stream_leases, 'SWEEP_SECONDS', 0.01)
    scheduler = stream_leases.StreamLeaseSweeper()
    started, release, finished = (threading.Event() for _ in range(3))
    blocked, other = Mock(), Mock()

    def stall():
        started.set()
        assert release.wait(5)

    blocked.reap_idle_streams.side_effect = stall
    other.reap_idle_streams.side_effect = finished.set
    scheduler.watch(blocked)
    try:
        assert started.wait(5)
        scheduler.watch(other)
        assert finished.wait(5)
        assert blocked.reap_idle_streams.call_count == 1
    finally:
        release.set()
