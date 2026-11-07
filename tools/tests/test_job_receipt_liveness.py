"""A receipt read before its worker's terminal write is stale, not abandoned.

Job workers store their terminal receipt and then stop. A reader that loads a
receipt outside the store lock can see the worker stop after that load, so the
liveness check must not turn the earlier copy into an "unknown" outcome, and a
later write must not store one. Each test places the worker's terminal write
between the reader's first load and its liveness check with a load hook; none
of them depends on timing.
"""
import os
import uuid

import psutil
import pytest

from pgadmin.cdeadmin.sdk import durable_tool
from pgadmin.cdeadmin.workspace import job_liveness
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import MySQLBinlogJobs
from pgadmin.cdeadmin.workspace.mysql_binlog_replay_jobs import (
    MySQLBinlogReplayJobs)
from pgadmin.cdeadmin.workspace.mysql_clone_jobs import MySQLCloneJobs
from pgadmin.cdeadmin.workspace.postgresql_continuity_jobs import (
    PostgreSQLContinuityJobs)
from pgadmin.cdeadmin.workspace.sqlite_capture_jobs import SQLiteCaptureJobs

OWNER = 1


def _put(jobs, key, record):
    with jobs.store(record['job_id']) as store:
        store.change(lambda state: state.setdefault(key, {}).update(
            {record['job_id']: record}))


def _record(jobs, **values):
    # No worker thread is registered for this job in this process, so the
    # receipt's worker is observed as stopped.
    return {'job_id': str(uuid.uuid4()), 'owner': OWNER,
            'endpoint_id': str(uuid.uuid4()),
            'worker_identity': list(jobs.worker_identity), **values}


def _finish_after_first_load(monkeypatch, cls, finish):
    """Run ``finish`` (the worker's terminal write) right after the first
    load."""
    original = cls.load
    pending = [True]

    def load(self, *args):
        record = original(self, *args)
        if pending:
            pending.clear()
            finish(self, record)
        return record
    monkeypatch.setattr(cls, 'load', load)


def _get(jobs, record):
    return jobs.get(record['job_id'], OWNER, record['endpoint_id'])


def _stored(jobs, record):
    return jobs.load(record['job_id'], OWNER, record['endpoint_id'])


@pytest.fixture
def binlog_jobs(tmp_path):
    return MySQLBinlogJobs(tmp_path / 'jobs.json', tmp_path / 'receipts')


def test_get_judges_the_receipt_read_after_the_worker_was_seen_stopped(
        binlog_jobs, monkeypatch):
    record = _record(binlog_jobs, state='active')
    _put(binlog_jobs, 'mysql_binlog_jobs', record)
    _finish_after_first_load(
        monkeypatch, MySQLBinlogJobs, lambda jobs, current: jobs.update(
            current, state='completed',
            native_process_termination_confirmed=True))
    result = _get(binlog_jobs, record)
    assert result['state'] == 'completed'
    assert result['native_process_termination_confirmed'] is True


def test_a_worker_that_stopped_without_a_terminal_receipt_is_still_unknown(
        binlog_jobs):
    record = _record(binlog_jobs, state='active')
    _put(binlog_jobs, 'mysql_binlog_jobs', record)
    result = _get(binlog_jobs, record)
    assert result['state'] == 'unknown'
    assert result['native_process_termination_confirmed'] is False
    assert _stored(binlog_jobs, record)['state'] == 'active'


def test_a_running_local_worker_keeps_its_active_receipt(binlog_jobs):
    record = _record(binlog_jobs, state='active')
    _put(binlog_jobs, 'mysql_binlog_jobs', record)

    class Running:
        @staticmethod
        def is_alive():
            return True
    with binlog_jobs._maps_lock:
        binlog_jobs.workers[record['job_id']] = (Running(), None)
    try:
        assert _get(binlog_jobs, record)['state'] == 'active'
    finally:
        with binlog_jobs._maps_lock:
            binlog_jobs.workers.pop(record['job_id'], None)


def test_a_remapped_publishing_receipt_is_read_again(tmp_path, monkeypatch):
    jobs = SQLiteCaptureJobs(tmp_path / 'jobs.json', tmp_path / 'receipts')
    record = _record(jobs, state='publishing')
    _put(jobs, 'mysql_binlog_jobs', record)
    _finish_after_first_load(
        monkeypatch, SQLiteCaptureJobs,
        lambda store, current: store.update(current, state='completed'))
    assert _get(jobs, record)['state'] == 'completed'


def test_list_reports_the_settled_receipt(binlog_jobs, monkeypatch):
    record = _record(binlog_jobs, state='active')
    _put(binlog_jobs, 'mysql_binlog_jobs', record)
    scope = binlog_jobs.prepare_scope(OWNER, record['endpoint_id'])
    (scope / 'index' / ('00000000000000000001_' + record['job_id'])).touch()
    _finish_after_first_load(
        monkeypatch, MySQLBinlogJobs,
        lambda jobs, current: jobs.update(current, state='completed'))
    listed = binlog_jobs.list(OWNER, record['endpoint_id'])
    assert [job['state'] for job in listed['jobs']] == ['completed']


def _terminated_utility(monkeypatch):
    observation = {'complete': True, 'cleanup_confirmed': True,
                   'native_outcome_inferred': False}
    monkeypatch.setattr(durable_tool, 'observe',
                        lambda *_args, **_kwargs: dict(observation))
    monkeypatch.setattr(durable_tool, 'cancel',
                        lambda *_args, **_kwargs: dict(observation))


def _utility_record(jobs):
    return _record(jobs, state='active', durable_tool={'name': 'utility'},
                   program={'executable_sha256': '0' * 64})


def test_utility_observation_never_stores_unknown_over_a_terminal_receipt(
        binlog_jobs, monkeypatch):
    _terminated_utility(monkeypatch)
    record = _utility_record(binlog_jobs)
    _put(binlog_jobs, 'mysql_binlog_jobs', record)
    stale = _stored(binlog_jobs, record)
    binlog_jobs.update(stale, state='completed', finished_at=1.0)
    binlog_jobs.observe_utility(stale)
    stored = _stored(binlog_jobs, record)
    assert stored['state'] == 'completed'
    assert stored['native_process_termination_confirmed'] is True


def test_utility_observation_still_marks_an_abandoned_receipt_unknown(
        binlog_jobs, monkeypatch):
    _terminated_utility(monkeypatch)
    record = _utility_record(binlog_jobs)
    _put(binlog_jobs, 'mysql_binlog_jobs', record)
    binlog_jobs.observe_utility(_stored(binlog_jobs, record))
    assert _stored(binlog_jobs, record)['state'] == 'unknown'


def test_replay_utility_observation_keeps_a_terminal_receipt(
        tmp_path, monkeypatch):
    _terminated_utility(monkeypatch)
    jobs = MySQLBinlogReplayJobs(tmp_path / 'jobs.json',
                                 tmp_path / 'receipts')
    reference = {'server_id': 1, 'endpoint_id': str(uuid.uuid4()),
                 'job_id': str(uuid.uuid4()), 'artifact_digest': '0' * 64,
                 'summary': {'total_bytes': 1}, 'family': 'shell'}
    record = _record(
        jobs, state='active', source={},
        source_state={'input_reference': reference},
        program={'executable_sha256': '0' * 64},
        durable_tools={'shell-replay-client': {
            'name': 'shell-replay-client'}})
    _put(jobs, 'mysql_binlog_jobs', record)
    stale = _stored(jobs, record)
    jobs.update(stale, state='completed', finished_at=1.0)
    jobs.observe_utility(stale)
    assert _stored(jobs, record)['state'] == 'completed'


def test_clone_get_and_list_judge_the_settled_receipt(tmp_path, monkeypatch):
    jobs = MySQLCloneJobs(tmp_path / 'jobs.json', tmp_path / 'receipts')

    def finish(store, current):
        store.update(current, state='native_completed')
    record = _record(jobs, state='active')
    _put(jobs, 'mysql_clone_jobs', record)
    _finish_after_first_load(monkeypatch, MySQLCloneJobs, finish)
    assert _get(jobs, record)['state'] == 'native_completed'

    listed = _record(jobs, state='active')
    _put(jobs, 'mysql_clone_jobs', listed)
    index = jobs.scope(OWNER, listed['endpoint_id']) / 'index'
    index.mkdir(parents=True)
    (index / ('00000000000000000001_' + listed['job_id'])).touch()
    _finish_after_first_load(monkeypatch, MySQLCloneJobs, finish)
    page = jobs.list(OWNER, listed['endpoint_id'])
    assert [job['state'] for job in page['jobs']] == ['native_completed']


def test_continuity_get_reports_a_slot_observed_before_the_worker_stopped(
        tmp_path, monkeypatch):
    jobs = PostgreSQLContinuityJobs(tmp_path / 'jobs.json',
                                    tmp_path / 'receipts')
    record = _record(jobs, state='completed', slot_observation_state='pending')
    _put(jobs, 'postgresql_continuity_jobs', record)
    _finish_after_first_load(
        monkeypatch, PostgreSQLContinuityJobs,
        lambda store, current: store.update(
            current, slot_observation_state='observed'))
    assert _get(jobs, record)['slot_observation_state'] == 'observed'


def test_continuity_get_still_reports_an_abandoned_slot_observation(tmp_path):
    jobs = PostgreSQLContinuityJobs(tmp_path / 'jobs.json',
                                    tmp_path / 'receipts')
    record = _record(jobs, state='completed', slot_observation_state='pending')
    _put(jobs, 'postgresql_continuity_jobs', record)
    assert _get(jobs, record)['slot_observation_state'] == 'unavailable'


class _FinishingWorker:
    """A local worker that is running when first asked, then stores its
    terminal receipt and stops before anyone asks again."""

    def __init__(self, finish):
        self.finish = finish
        self.asked = 0

    def is_alive(self):
        self.asked += 1
        if self.asked == 1:
            self.finish()
            return True
        return False


def _register(jobs, lock, record, worker):
    with lock:
        jobs.workers[record['job_id']] = (worker, None)


def test_continuity_judges_liveness_once_per_read(tmp_path):
    jobs = PostgreSQLContinuityJobs(tmp_path / 'jobs.json',
                                    tmp_path / 'receipts')
    record = _record(jobs, state='completed', slot_observation_state='pending')
    _put(jobs, 'postgresql_continuity_jobs', record)
    worker = _FinishingWorker(lambda: jobs.update(
        record, slot_observation_state='observed'))
    _register(jobs, jobs._worker_maps_lock, record, worker)
    # Running when checked, so the copy read before its last write is shown
    # as pending, never as an abandoned observation.
    assert _get(jobs, record)['slot_observation_state'] == 'pending'
    assert worker.asked == 1
    assert _get(jobs, record)['slot_observation_state'] == 'observed'


def test_binlog_and_clone_reads_judge_liveness_once(binlog_jobs, tmp_path):
    clone_jobs = MySQLCloneJobs(tmp_path / 'clone.json', tmp_path / 'clones')
    for jobs, key in ((binlog_jobs, 'mysql_binlog_jobs'),
                      (clone_jobs, 'mysql_clone_jobs')):
        record = _record(jobs, state='active')
        _put(jobs, key, record)
        worker = _FinishingWorker(lambda: jobs.update(
            record, state='completed'))
        _register(jobs, jobs._maps_lock, record, worker)
        assert _get(jobs, record)['state'] == 'active'
        assert worker.asked == 1
        assert _get(jobs, record)['state'] == 'completed'


def test_worker_stopped_follows_the_recorded_process_and_the_local_thread():
    own = [os.getpid(), psutil.Process().create_time()]

    class Thread:
        def __init__(self, alive):
            self.alive = alive

        def is_alive(self):
            return self.alive

    def stopped(identity, local_worker):
        return job_liveness.worker_stopped(
            {'worker_identity': identity}, own, local_worker)
    assert stopped(own, (Thread(True), None)) is False
    assert stopped(own, (Thread(False), None)) is True
    assert stopped(own, None) is True
    assert stopped([own[0], own[1] + 1], None) is True
    assert job_liveness.worker_stopped({}, own, None) is True
