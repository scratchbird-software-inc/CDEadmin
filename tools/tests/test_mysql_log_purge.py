"""Native source log intent, durable acknowledgement and non-replay boundaries."""
from copy import deepcopy
import threading
import time
import uuid
from types import SimpleNamespace

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_log_purge as native
from pgadmin.cdeadmin.workspace.mysql_log_purge import PurgeJobs


def captured():
    return {'identity': {'version': '9.7.0', 'server_uuid': str(uuid.uuid4()),
                        'authenticated_principal': 'operator@%', 'active_role': 'NONE'},
            'status': 'available', 'logs': [{'Log_name': 'native.000001', 'File_size': 9007199254740993},
                {'Log_name': 'native.000002', 'File_size': 512}], 'current': {'File': 'native.000002', 'Position': 512},
            'state': {'gtid_mode': 'ON', 'gtid_executed': 'native:1-7', 'gtid_purged': ''}}


def test_native_filename_boundary_is_preserved_and_timestamp_candidates_are_explicitly_potential(monkeypatch):
    source = captured()
    chosen = native.selection(None, source, native.options({'mode': 'TO', 'to_file': 'native.000002'}))
    assert chosen['candidate_names'] == ['native.000001']
    monkeypatch.setattr(native, 'rows', lambda *_args: [{'native_epoch': 'native evaluated epoch'}])
    chosen = native.selection(None, source, native.options({'mode': 'BEFORE', 'before_utc': '2026-10-21 01:02:03'}))
    assert chosen['native_epoch'] == 'native evaluated epoch'
    assert chosen['candidate_selection'] == 'potential-closed-logs-native-server-evaluates-file-timestamps'


@pytest.mark.parametrize('options', [None, {'mode': 'TO', 'to_file': 'a', 'before_utc': '2026-10-21 00:00:00'},
    {'mode': 'BEFORE', 'before_utc': 'NOW()'}, {'mode': 'BEFORE', 'before_utc': '2026-02-30 00:00:00'},
    {'mode': 'TO', 'to_file': 'a', 'timeout_seconds': True}, {'mode': 'TO', 'to_file': '\x00'},
    {'mode': 'TO', 'to_file': 'a', 'route': {}}])
def test_ambiguous_native_source_log_requests_are_refused(options):
    with pytest.raises(native.BinlogArchiveError): native.options(options)


@pytest.fixture
def review(tmp_path):
    source = captured(); source['state']['purge_selection'] = native.selection(None, source,
        native.options({'mode': 'TO', 'to_file': 'native.000002'}))
    jobs = PurgeJobs(tmp_path / 'jobs.json', tmp_path / 'receipts'); endpoint = str(uuid.uuid4())
    program = native.program(source)
    value = jobs.review(1, endpoint, native.options({'mode': 'TO', 'to_file': 'native.000002'}), source, 'registration', program)
    request = {**{key: value[key] for key in ('job_id', 'review_digest')}, 'confirmed': True}
    current = {'source': source['identity'], 'configuration': 'registration', 'program': program}
    yield jobs, endpoint, source, value, request, current
    assert jobs.close()


class Transport:
    def __init__(self, acknowledgement=False, fault=False):
        self.calls = 0; self.closed = False; self.acknowledgement = acknowledgement; self.fault = fault
    def execute(self, _record, _cancel, boundary, progress):
        self.calls += 1; boundary()
        if self.acknowledgement: progress({'native_acknowledged': True})
        if self.fault: raise OSError('Owned missing native reply or postcondition')
        return {'native_acknowledged': self.acknowledgement, 'native_error_returned': False}
    def close(self): self.closed = True


def finish(jobs, endpoint, value):
    deadline = time.monotonic() + 5
    while True:
        result = jobs.get(value['job_id'], 1, endpoint)
        if result['state'] not in {'active', 'dispatching', 'cancel_requested'}: return result
        if time.monotonic() > deadline: raise TimeoutError('Owned source job deadline')
        time.sleep(.01)


def test_missing_reply_reconciliation_preserves_original_unknown_and_never_replays(review):
    jobs, endpoint, source, value, request, current = review
    transport = Transport(fault=True)
    jobs.start(request, 1, endpoint, current, transport)
    result = finish(jobs, endpoint, value); assert result['state'] == 'unknown'
    observed = deepcopy(source); observed['logs'].pop(0)
    reconciled = jobs.reconcile_source(jobs.load(value['job_id'], 1, endpoint), observed)
    assert reconciled['state'] == 'unknown' and reconciled['reconciliation']['absent_before_names'] == ['native.000001']
    assert jobs.start(request, 1, endpoint, {}, None)['state'] == 'unknown'
    assert transport.calls == 1 and transport.closed


def test_native_acknowledgement_survives_a_later_postcondition_failure(review):
    jobs, endpoint, _source, value, request, current = review
    transport = Transport(acknowledgement=True, fault=True)
    jobs.start(request, 1, endpoint, current, transport)
    result = finish(jobs, endpoint, value)
    assert result['state'] == 'native_acknowledged' and result['native_acknowledged'] is True
    assert result['error']['type'] == 'OSError' and transport.calls == 1


def test_native_receipts_keep_wide_file_sizes_owner_scope_and_explicit_confirmation(review):
    jobs, endpoint, source, value, request, current = review
    with pytest.raises(native.BinlogArchiveError): jobs.start({**request, 'confirmed': False}, 1, endpoint, current, Transport())
    record = jobs.load(value['job_id'], 1, endpoint)
    jobs.update(record, result={'after': source})
    assert jobs.get(value['job_id'], 1, endpoint)['result']['after']['logs'][0]['File_size'] == '9007199254740993'
    for owner, other in ((2, endpoint), (1, str(uuid.uuid4()))):
        with pytest.raises(native.BinlogArchiveError): jobs.get(value['job_id'], owner, other)


def test_changed_native_program_or_source_cannot_dispatch(review):
    jobs, endpoint, _source, _value, request, current = review
    transport = Transport()
    with pytest.raises(native.BinlogArchiveError): jobs.start(request, 1, endpoint, {**current, 'program': {}}, transport)
    assert transport.closed and transport.calls == 0


@pytest.mark.parametrize('command,expected', [('PURGE BINARY LOGS TO \'native.000002\'', True), ('SELECT SLEEP(10)', False), (None, False)])
def test_cancellation_requires_the_original_handshake_and_an_active_purge(monkeypatch, command, expected):
    source = captured()
    monitor = SimpleNamespace()
    def rows(_connection, sql, _parameters=()):
        if '@@server_uuid' in sql: return [{'server_uuid': source['identity']['server_uuid']}]
        if 'session_account_connect_attrs' in sql: return [{'PROCESSLIST_ID': 12}]
        return [{'PROCESSLIST_INFO': command}]
    monkeypatch.setattr(native, 'rows', rows)
    monkeypatch.setattr(native, 'thread_matches', lambda *_args: True)
    transport = native.Transport(None, None, monitor, source, {})
    assert transport.matches({'connection_id': '12', 'thread_id': '42'}, {'name': 'nonce', 'value': 'exact'}, active=True) is expected
    assert not transport.matches({'connection_id': '12', 'thread_id': '42'}, None, active=True)


def test_cancellation_at_the_durable_boundary_never_becomes_an_unknown_dispatched_purge(monkeypatch):
    from unittest.mock import Mock
    source = captured(); selected = native.options({'mode': 'TO', 'to_file': 'native.000002'})
    source['state']['purge_selection'] = native.selection(None, source, selected)
    cursor = Mock()
    worker = SimpleNamespace(cursor=lambda: cursor, _cdeadmin_observer_attribute={'name': 'nonce', 'value': 'exact'})
    transport = native.Transport(None, worker, None, source, selected)
    transport.matches = lambda *_args, **_kwargs: True
    monkeypatch.setattr(native, 'capture', lambda _worker: source)
    monkeypatch.setattr(native, 'thread_identity', lambda _worker: {'connection_id': '12', 'thread_id': '42'})
    monkeypatch.setattr(native, 'rows', lambda _worker, sql, _params=(): [{'valid': 1}] if 'GTID_SUBSET' in sql else [{'acquired': 1}])
    def cancelled(): raise InterruptedError('Owned cancellation at the durable boundary')
    with pytest.raises(InterruptedError):
        transport.execute({'source': source['identity'], 'source_state': source['state'], 'options': selected},
            SimpleNamespace(is_set=lambda: False), cancelled, lambda _value: None)
    cursor.execute.assert_not_called(); cursor.close.assert_called_once()


def test_job_connection_ownership_is_transferred_under_the_interactive_shutdown_lock():
    from unittest.mock import Mock
    handle = object()
    client = SimpleNamespace(_executions=SimpleNamespace(lock=threading.RLock(), closing=False),
        _connect=Mock(return_value=handle), _forget_connection=Mock(), _discard_failed_session=Mock())
    assert native.private_connection(client, {'host': 'native'}) is handle
    client._forget_connection.assert_called_once_with(handle)
    client._executions.closing = True
    with pytest.raises(native.BinlogArchiveError): native.private_connection(client, {'host': 'native'})
    assert client._connect.call_count == 1
