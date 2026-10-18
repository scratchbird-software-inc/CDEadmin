"""Once-only SQL slot dispatch, cancellation and durable acknowledgement."""
from contextlib import contextmanager
from copy import deepcopy
import json
import threading
import time
from types import SimpleNamespace
import uuid

import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
from pgadmin.cdeadmin.providers.postgresql.continuity_transport import ContinuityTransport
from pgadmin.cdeadmin.workspace.postgresql_continuity_jobs import PostgreSQLContinuityJobs
from pgadmin.cdeadmin.workspace import postgresql_continuity_slot_sql as native


@pytest.mark.parametrize('suffix,options', [
    ('physical_create', {'slot': 'a', 'temporary': True}),
    ('physical_create', {'slot': 'a', 'reserve_wal': 'true'}),
    ('physical_create', {'slot': 'a', 'timeout_seconds': 2147484}),
    ('physical_create', {'slot': 'a', 'timeout_seconds': True}),
    ('physical_create', {'slot': 'Upper'}),
    ('logical_create', {'slot': 'a', 'plugin': ''}),
    ('logical_create', {'slot': 'a', 'plugin': 'bad\x00plugin'}),
    ('logical_create', {'slot': 'a', 'two_phase': 1}),
    ('logical_create', {'slot': 'a', 'failover': 'false'}),
    ('physical_copy', {'slot': 'a', 'source_slot': 'a'}),
    ('logical_copy', {'slot': 'a', 'source_slot': 'UPPER'}),
    ('advance', {'slot': 'a', 'upto_lsn': '0/0'}),
    ('advance', {'slot': 'a', 'upto_lsn': '0/100000000'}),
    ('advance', {'slot': 'a', 'upto_lsn': '1/1; SELECT 1'}),
    ('drop', {'slot': 'a', 'if_not_exists': True}),
])
def test_invalid_slot_semantics_are_refused_before_admission(suffix, options):
    with pytest.raises(ContinuityError): native.options('wal_slot_sql_' + suffix, options)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    jobs = PostgreSQLContinuityJobs(tmp_path/'jobs.json', tmp_path/'artifacts')
    endpoint = str(uuid.uuid4())
    source = {'sql_identity': {'database': 'Owned "ü"', 'effective_principal': 'selected_role'},
              'slot_snapshot': None, 'slot_identity': None, 'copy_slot_snapshot': None, 'copy_slot_identity': None}
    class Connection:
        info = SimpleNamespace(backend_pid=123)
        calls = []; closed = False; outcome = None; observed = None
        def close(self): self.closed = True; self.closed_event.set()
        def cancel_safe(self, *, timeout): self.cancelled.set()
        def __init__(self): self.cancelled = threading.Event(); self.closed_event = threading.Event()
    connection = Connection()
    @contextmanager
    def cursor(_connection):
        class Cursor:
            row = None
            def execute(self, command, params=None):
                self.row = None
                if command.startswith('SELECT slot_name') or command.startswith('SELECT pg_catalog.pg_drop'):
                    connection.calls.append((command, params))
                    if connection.outcome is not None: connection.outcome()
                    self.row = ('owned_slot', '0/200')
                elif command.startswith('SELECT %s'): self.row = params
            def fetchone(self): return self.row
        yield Cursor()
    monkeypatch.setattr(native.private_sql, 'cursor', cursor)
    monkeypatch.setattr(native.private_sql, 'attach', lambda _parameters, identity: connection)
    monkeypatch.setattr(native, 'enrich', lambda *_args: deepcopy(source))
    monkeypatch.setattr(native, 'observation', lambda *_args: connection.observed)
    try: yield jobs, source, endpoint, connection
    finally: jobs.close()


def review(fixture, operation='wal_slot_sql_physical_create', **options):
    jobs, source, endpoint, _connection = fixture
    return jobs.review({'operation': operation, 'database_target_id': 'postgresql-database:123',
                        'options': {'slot': 'owned_slot', **options}}, 1, endpoint, source, 'config', {})


def start(fixture, reviewed, **changes):
    jobs, source, endpoint, _connection = fixture
    return jobs.start({'job_id': reviewed['job_id'], 'review_digest': reviewed['review_digest'], 'confirmed': True},
                      1, endpoint, changes.get('source', source), 'config', ContinuityTransport({}))


def wait(fixture, reviewed):
    jobs, _source, endpoint, _connection = fixture; deadline = time.monotonic() + 5
    while True:
        result = jobs.get(reviewed['job_id'], 1, endpoint)
        if result['state'] not in {'dispatching', 'active', 'cancel_requested'} and result.get('slot_observation_state') != 'pending': return result
        if time.monotonic() > deadline: raise AssertionError('Owned SQL slot worker did not finish')
        time.sleep(.01)


def test_actual_ack_is_durable_before_catalog_and_never_redispatched(fixture, monkeypatch):
    jobs, _source, endpoint, connection = fixture
    entered = threading.Event(); release = threading.Event()
    def observation(*_args): entered.set(); assert release.wait(5); return {'slot_name': 'owned_slot', 'slot_type': 'physical'}
    monkeypatch.setattr(native, 'observation', observation)
    reviewed = review(fixture)
    try:
        start(fixture, reviewed); assert entered.wait(2)
        saved = jobs.load(reviewed['job_id'], 1, endpoint)
        assert saved['state'] == 'completed' and saved['native_sql_acknowledged']
        assert saved['native_sql_result'] == {'slot_name': 'owned_slot', 'end_lsn': '0/200'}
        assert saved['slot_observation_state'] == 'pending'
        assert jobs.observed({**saved, 'worker_identity': [999999999, 0]})['state'] == 'completed'
        start(fixture, reviewed)
        assert len(connection.calls) == 1
    finally: release.set()
    assert wait(fixture, reviewed)['slot_observation_state'] == 'observed'


def test_lost_native_reply_stays_unknown_even_if_slot_now_exists(fixture):
    _jobs, _source, _endpoint, connection = fixture
    def lost_reply(): raise RuntimeError('private-password-canary')
    connection.outcome = lost_reply; connection.observed = {'slot_name': 'owned_slot'}
    reviewed = review(fixture); start(fixture, reviewed)
    result = wait(fixture, reviewed)
    assert result['state'] == 'unknown' and result['sql_dispatched'] and not result['native_sql_acknowledged']
    assert not result['automatic_retry'] and not result['remote_finality_inferred']
    assert 'private-password-canary' not in json.dumps(result)
    start(fixture, reviewed); assert len(connection.calls) == 1


def test_late_cancel_and_unavailable_catalog_cannot_demote_a_real_ack(fixture, monkeypatch):
    jobs, _source, endpoint, connection = fixture
    reviewed = review(fixture)
    connection.outcome = lambda: jobs.cancel(reviewed['job_id'], 1, endpoint)
    def unavailable(*_args): raise RuntimeError('private-catalog-secret')
    monkeypatch.setattr(native, 'observation', unavailable)
    start(fixture, reviewed); result = wait(fixture, reviewed)
    assert result['state'] == 'completed' and result['native_sql_acknowledged']
    assert result['cancel_requested'] and result['slot_observation_state'] == 'unavailable'
    assert 'private-catalog-secret' not in json.dumps(result)


def test_shared_store_cancel_interrupts_only_the_owned_connection(fixture):
    jobs, _source, endpoint, connection = fixture; entered = threading.Event()
    def blocked():
        entered.set(); assert connection.cancelled.wait(3)
        import psycopg
        raise psycopg.errors.QueryCanceled('private-cancel-text')
    connection.outcome = blocked
    reviewed = review(fixture); start(fixture, reviewed); assert entered.wait(2)
    # Simulate a cancellation handled by another application worker: no local
    # Event is signalled by this second manager.
    other = PostgreSQLContinuityJobs(jobs.path, jobs.root)
    other._worker_maps_lock = threading.RLock(); other.workers = {}
    other.cancel(reviewed['job_id'], 1, endpoint)
    result = wait(fixture, reviewed)
    assert result['state'] == 'unknown' and result['native_sqlstate'] == '57014'
    assert connection.closed_event.wait(2) and len(connection.calls) == 1


def test_worker_rechecks_stable_slot_identity_before_dispatch(fixture, monkeypatch):
    _jobs, source, _endpoint, connection = fixture
    reviewed = review(fixture)
    monkeypatch.setattr(native, 'enrich', lambda *_args: {**source, 'slot_identity': {'slot_type': 'logical'}})
    start(fixture, reviewed); result = wait(fixture, reviewed)
    assert result['state'] == 'not_dispatched' and not result['sql_dispatched'] and not connection.calls


def test_copy_live_positions_may_change_but_database_or_source_type_requires_review(fixture):
    _jobs, source, _endpoint, connection = fixture
    reviewed = review(fixture, 'wal_slot_sql_physical_copy', source_slot='source_slot')
    with pytest.raises(ContinuityError, match='target or registration changed'):
        start(fixture, reviewed, source={**source, 'sql_identity': {'database': 'other'}})
    with pytest.raises(ContinuityError, match='target or registration changed'):
        start(fixture, reviewed, source={**source, 'copy_slot_identity': {'slot_type': 'logical'}})
    start(fixture, reviewed, source={**source, 'copy_slot_snapshot': {'restart_lsn': '0/300'}})
    assert wait(fixture, reviewed)['state'] == 'completed' and len(connection.calls) == 1


def test_client_change_is_not_dispatched(fixture, monkeypatch):
    _jobs, _source, _endpoint, connection = fixture
    reviewed = review(fixture)
    monkeypatch.setattr(native, 'client_identity', lambda: {'libpq_version': 160000})
    start(fixture, reviewed)
    assert wait(fixture, reviewed)['state'] == 'not_dispatched' and not connection.calls
