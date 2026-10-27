"""Physical clone holds and independent native acknowledgement/ownership."""
from copy import deepcopy
from types import SimpleNamespace
import threading
from unittest.mock import Mock
import uuid

import pytest

from pgadmin.cdeadmin.workspace.mysql_backup_protection import Registry, finish_clone
from pgadmin.cdeadmin.workspace import mysql_clone_jobs as jobs_module
from test_mysql_clone import manager, review, Transport


def clone_record():
    return {'job_id': str(uuid.uuid4()), 'source': {'server_uuid': str(uuid.uuid4()),
        'version': '9.7.0', 'authenticated_principal': 'native@host', 'active_role': 'NONE'},
        'options': {'destination': '/native/clone'}, 'execution_host': {'kind': 'database-server'}, 'donor': None}


def test_local_clone_hold_is_idempotent_source_scoped_and_retirement_never_resurrects(tmp_path):
    registry = Registry(tmp_path); endpoint = str(uuid.uuid4()); record = clone_record()
    tickets = registry.begin_clone(1, endpoint, record)
    assert len(registry.begin_clone(1, endpoint, record)) == 1 and registry.list(1, endpoint)['total'] == 1
    other = {'source': {'server_uuid': str(uuid.uuid4())}}
    assert registry.protected(other, registry.protections(1, endpoint))
    result = finish_clone(tickets, {'acknowledged': True}, {'job_correlated': True,
        'status': {'binlog_file': 'native.000007', 'binlog_position': '9007199254740993', 'gtid_executed_truncated': False}})[0]
    assert result['state'] == 'native_clone_returned' and result['native_boundary']['binlog_position'] == '9007199254740993'
    assert result['native_clone_completion_acknowledged'] and not result['database_recovery_verified']
    assert not registry.protected(other, registry.protections(1, endpoint))
    assert registry.protected({'source': record['source']}, registry.protections(1, endpoint))
    selected = registry.review_retire(1, endpoint, record['job_id'])
    registry.retire(1, endpoint, {key: selected[key] for key in ('review_id','review_digest')} | {'confirmed': True})
    assert finish_clone(tickets, {'acknowledged': True}, {})[0]['native_clone_acknowledged_after_retirement']
    assert registry.protections(1, endpoint) == []
    with pytest.raises(ValueError, match='retired'): registry.begin_clone(1, endpoint, record)


def test_remote_clone_keeps_both_registrations_conservative_after_returned_native_sql(tmp_path):
    registry = Registry(tmp_path); endpoint = str(uuid.uuid4()); donor = str(uuid.uuid4()); record = clone_record()
    record['donor'] = {'endpoint_id': donor, 'native_identity': {**record['source'], 'server_uuid': str(uuid.uuid4())}}
    tickets = registry.begin_clone(1, endpoint, record)
    assert {ticket.sink.endpoint for ticket in tickets} == {endpoint, donor}
    result = finish_clone(tickets, {'acknowledged': True}, {})
    assert all(row['state'] == 'native_clone_returned_unattested_source' for row in result)
    unrelated = {'source': {'server_uuid': str(uuid.uuid4())}}
    for scope in (endpoint, donor):
        assert registry.protected(unrelated, registry.protections(1, scope))
        assert registry.list(2, scope)['backups'] == []
    assert registry.list(1, endpoint)['backups'][0]['clone_role'] == 'recipient'
    assert registry.list(1, donor)['backups'][0]['clone_role'] == 'registered_donor'


def test_lost_clone_reply_and_bookkeeping_failure_keep_durable_uncertainty(tmp_path, monkeypatch):
    registry = Registry(tmp_path); endpoint = str(uuid.uuid4()); record = clone_record()
    tickets = registry.begin_clone(1, endpoint, record)
    result = finish_clone(tickets, {'acknowledged': False}, {'job_correlated': True, 'status': {'state': 'Completed'}})[0]
    assert result['state'] == 'unconfirmed_native_reply' and not result['native_clone_completion_acknowledged']
    monkeypatch.setattr(tickets[0], 'clone_returned', Mock(side_effect=OSError('owned bookkeeping fault')))
    assert finish_clone(tickets, {'acknowledged': True}, {})[0]['native_backup_acknowledgement_unchanged']
    assert Registry(tmp_path).list(1, endpoint)['backups'][0]['state'] == 'unconfirmed_native_reply'


def test_changed_clone_cannot_rebind_an_existing_native_backup_intent(tmp_path):
    registry = Registry(tmp_path); endpoint = str(uuid.uuid4()); record = clone_record()
    registry.begin_clone(1, endpoint, record)
    changed = deepcopy(record); changed['options']['destination'] = '/different/clone'
    with pytest.raises(ValueError, match='differs'): registry.begin_clone(1, endpoint, changed)


@pytest.fixture
def runner(manager, tmp_path, monkeypatch):
    jobs, source, endpoint = manager; item = review(manager)
    registry = jobs.backup_protection = Registry(tmp_path / 'protection')
    transport = Transport(); transport.monitor = object(); transport.worker = object()
    calls = []
    monkeypatch.setattr(jobs_module, 'capture', lambda _connection: source)
    monkeypatch.setattr(jobs_module, 'thread_identity', lambda _connection: {'connection_id': '13', 'thread_id': '27'})
    monkeypatch.setattr(jobs_module, 'thread_matches', lambda *_args: True)
    def rows(_connection, sql, _args=()):
        if sql.startswith('SELECT GET_LOCK'): return [{'acquired': 1}]
        if sql.startswith('CLONE LOCAL'):
            assert registry.list(1, endpoint)['backups'][0]['state'] == 'pending_native_reply'
            calls.append(sql)
        return []
    monkeypatch.setattr(jobs_module, 'rows', rows)
    sequence = iter([{'available': True, 'status': None}, {'available': True, 'status': {'id': '1', 'pid': '13',
        'begin_time': 'native-start', 'state': 'Completed', 'error_number': 0, 'source': 'LOCAL INSTANCE',
        'destination': item['options']['destination']}}])
    monkeypatch.setattr(jobs_module, 'observation', lambda _connection: next(sequence))
    return SimpleNamespace(jobs=jobs, source=source, endpoint=endpoint, item=item, registry=registry, transport=transport, calls=calls)


def execute(runner):
    f = runner
    # Run the same admitted worker directly so fault assertions are deterministic.
    record = f.jobs.load(f.item['job_id'], 1, f.endpoint)
    f.jobs.run(record, f.transport, threading.Event())
    return f.jobs.get(record['job_id'], 1, f.endpoint)


def test_clone_worker_persists_protection_before_native_sql_and_ack_before_terminal_observation(runner):
    f = runner; result = execute(f)
    assert len(f.calls) == 1 and result['state'] == 'native_completed' and result['sql_observation']['acknowledged']
    assert result['archive_backup_protections'][0]['state'] == 'native_clone_returned'
    assert f.transport.closed and f.registry.list(1, f.endpoint)['total'] == 1


def test_clone_observer_failure_preserves_original_ack_and_native_backup_hold(runner, monkeypatch):
    f = runner; calls = []
    def observation(_connection):
        calls.append(1)
        if len(calls) == 1: return {'available': True, 'status': None}
        raise OSError('Owned post-ack PFS observation fault')
    monkeypatch.setattr(jobs_module, 'observation', observation)
    result = execute(f)
    assert result['state'] == 'unknown' and result['sql_observation']['acknowledged'] and len(f.calls) == 1
    assert result['archive_backup_protections'][0]['state'] == 'native_clone_returned'
    assert result['archive_backup_protections'][0]['native_boundary_observed'] is False


def test_clone_protection_failure_prevents_native_dispatch(runner, monkeypatch):
    f = runner
    monkeypatch.setattr(f.registry, 'begin_clone', Mock(side_effect=OSError('Owned intent write refusal')))
    result = execute(f)
    assert result['state'] == 'not_dispatched' and not f.calls and f.transport.closed


def test_native_clone_connections_transfer_out_of_interactive_shutdown_under_its_admission_lock(monkeypatch):
    from pgadmin.cdeadmin.providers.mysql_family import mysql_clone as clone
    lock = threading.RLock(); handles = [object(), object()]; tracked = []; forgotten = []; disposed = []
    def connect(_context):
        assert lock._is_owned()
        handle = handles[len(forgotten)]; tracked.append(handle); return handle
    def forget(handle):
        assert lock._is_owned(); tracked.remove(handle); forgotten.append(handle)
    client = SimpleNamespace(_executions=SimpleNamespace(lock=lock, closing=False), _connect=connect,
                             _forget_connection=forget, _discard_failed_session=disposed.append)
    monkeypatch.setattr(clone, 'configure', lambda _connection: None)
    monkeypatch.setattr(clone, 'capture', lambda _connection: {'server_uuid': 'owned-native-source'})
    _source, transport = clone.connect(SimpleNamespace(client=client), {'host': 'native'}, 30)
    assert forgotten == handles and tracked == [] and disposed == []
    transport.close(); assert disposed == handles
