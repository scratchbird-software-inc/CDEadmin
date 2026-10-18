"""Lossless logical output, bounded previews and no-replay artifact recovery."""
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from types import SimpleNamespace

import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
from pgadmin.cdeadmin.workspace import postgresql_slot_changes as changes
from test_postgresql_continuity_slot_sql import fixture, review, start, wait


@pytest.fixture
def decoding(fixture, monkeypatch):
    _jobs, _source, _endpoint, connection = fixture
    original = changes.private_sql.cursor
    connection.rows = [('FFFFFFFF/FFFFFFFF', '4294967295', 'exact\n😀\x00')]
    connection.stream_failure = None
    @contextmanager
    def cursor(native):
        with original(native) as query:
            def stream(command, parameters, *, size):
                assert size == 1
                connection.calls.append((command, parameters))
                yield from connection.rows
                if connection.stream_failure is not None: raise connection.stream_failure
            query.stream = stream
            yield query
    monkeypatch.setattr(changes.private_sql, 'cursor', cursor)
    return fixture


def finished(decoding, item):
    jobs, _source, _endpoint, connection = decoding
    result = wait(decoding, item)
    assert connection.closed_event.wait(2)
    with jobs._worker_maps_lock: worker = jobs.workers.get(item['job_id'])
    if worker is not None: worker[0].join(2)
    return result


@pytest.mark.parametrize('operation', sorted(changes.OPERATIONS))
def test_native_output_is_lossless_and_ack_precedes_verified_artifact(decoding, operation):
    jobs, _source, endpoint, connection = decoding
    if operation.endswith('_binary'): connection.rows = [('0/100', '4294967295', base64.b64encode(b'\x00\x80\xff\n').decode())]
    item = review(decoding, operation, upto_nchanges=None, upto_lsn='0/0',
                  plugin_options=[{'name': 'same', 'value': 'first'}, {'name': 'same', 'value': 'second'}])
    start(decoding, item); result = finished(decoding, item)
    assert result['state'] == 'completed' and result['native_sql_acknowledged']
    assert result['change_artifact']['state'] == 'verified' and result['native_sql_result']['rows'] == '1'
    assert 'file_identity' not in result['change_artifact']
    saved = jobs.load(item['job_id'], 1, endpoint)
    with changes.payload(jobs, saved) as source: data = source.read()
    row = json.loads(data)
    assert (row['lsn'], row['xid'], row['data']) == connection.rows[0]
    assert hashlib.sha256(data).hexdigest() == result['change_artifact']['sha256']
    assert connection.calls[0][1] == ('owned_slot', '0/0', None, ['same', 'first', 'same', 'second'])
    start(decoding, item)
    assert len(connection.calls) == 1


@pytest.mark.parametrize('options', [
    {'upto_nchanges': True}, {'upto_nchanges': 2147483648}, {'upto_nchanges': -2147483649},
    {'upto_lsn': '1/100000000'}, {'plugin_options': [{'name': 'x', 'value': None}]},
    {'plugin_options': [{'name': '', 'value': 'x'}]}, {'plugin_options': [{'name': 'x', 'value': 'a\x00b'}]},
    {'plugin_options': 'proto_version=4'}, {'unsafe_sql': 'SELECT 1'},
    {'plugin_options': [{'name': 'x', 'value': '\ud800'}]},
    {'plugin_options': [{'name': '\udfff', 'value': 'x'}]},
])
def test_invalid_decoding_options_do_not_dispatch(options):
    with pytest.raises(ContinuityError): changes.options({'slot': 'owned_slot', **options})


def test_preview_preserves_native_text_and_pages_by_record_boundaries(decoding):
    jobs, _source, endpoint, connection = decoding
    connection.rows = [('0/100', '1', '😀' * 5000), ('0/200', '2', '<script>native text</script>')]
    item = review(decoding, 'wal_slot_sql_peek_text'); start(decoding, item); finished(decoding, item)
    saved = jobs.load(item['job_id'], 1, endpoint)
    first = changes.preview(jobs, saved, {'job_id': item['job_id'], 'limit': 1})
    assert first['rows'][0]['data'] == '😀' * 4096 and first['rows'][0]['data_preview_truncated']
    second = changes.preview(jobs, saved, {'job_id': item['job_id'], 'offset': first['next_offset'], 'limit': 1})
    assert second['rows'][0]['data'] == '<script>native text</script>' and second['next_offset'] is None
    with pytest.raises(ContinuityError, match='record boundary'):
        changes.preview(jobs, saved, {'offset': '1'})


def test_large_record_preview_is_bounded_and_keeps_the_next_native_record(decoding):
    jobs, _source, endpoint, connection = decoding
    connection.rows = [('0/100', '1', 'x' * 1500000), ('0/200', '2', 'after large native message')]
    item = review(decoding, 'wal_slot_sql_peek_text'); start(decoding, item); finished(decoding, item)
    page = changes.preview(jobs, jobs.load(item['job_id'], 1, endpoint), {})
    assert page['rows'][0]['native_values_previewed'] is False and page['rows'][0]['record_offset'] == '0'
    assert 'lsn' not in page['rows'][0] and page['rows'][1]['lsn'] == '0/200'
    assert len(json.dumps(page)) < 2048


def test_partial_bytes_do_not_prove_native_consumption_and_are_never_replayed(decoding):
    jobs, _source, endpoint, connection = decoding
    connection.stream_failure = RuntimeError('private-output-password-canary')
    item = review(decoding, 'wal_slot_sql_get_text'); start(decoding, item)
    result = finished(decoding, item)
    assert result['state'] == 'unknown' and not result['native_sql_acknowledged']
    assert result['change_artifact']['state'] == 'unavailable'
    result = changes.reconcile(jobs, jobs.load(item['job_id'], 1, endpoint))
    assert result['state'] == 'unknown' and result['change_artifact']['state'] == 'partial'
    assert result['change_artifact']['complete_record_lines'] == '1' and not result['change_artifact']['incomplete_tail']
    with changes.payload(jobs, jobs.load(item['job_id'], 1, endpoint)) as source:
        assert json.loads(source.read())['data'] == 'exact\n😀\x00'
    assert not result['native_sql_acknowledged'] and 'private-output-password-canary' not in json.dumps(result)
    start(decoding, item); assert len(connection.calls) == 1


def test_saved_native_ack_can_reconcile_a_failed_local_publication_without_sql(decoding, monkeypatch):
    jobs, _source, endpoint, connection = decoding
    replace = changes.durable_replace
    def failed(*_args): raise OSError('private-filesystem-detail')
    monkeypatch.setattr(changes, 'durable_replace', failed)
    item = review(decoding, 'wal_slot_sql_get_text'); start(decoding, item)
    result = finished(decoding, item)
    assert result['state'] == 'completed' and result['native_sql_acknowledged']
    assert result['change_artifact']['state'] == 'unavailable'
    monkeypatch.setattr(changes, 'durable_replace', replace)
    result = changes.reconcile(jobs, jobs.load(item['job_id'], 1, endpoint))
    assert result['state'] == 'completed' and result['change_artifact']['state'] == 'verified'
    assert result['change_artifact']['publication_reconciled'] and len(connection.calls) == 1


def test_reconciliation_preserves_an_incomplete_last_record_without_inventing_fields(decoding):
    jobs, _source, endpoint, connection = decoding
    connection.stream_failure = RuntimeError('lost response')
    item = review(decoding, 'wal_slot_sql_get_text'); start(decoding, item); finished(decoding, item)
    saved = jobs.load(item['job_id'], 1, endpoint)
    with (jobs.directory(saved)/changes.PARTIAL).open('ab') as target: target.write(b'{"lsn":"0/200"')
    reconciled = changes.reconcile(jobs, saved)
    assert reconciled['change_artifact']['incomplete_tail'] and reconciled['state'] == 'unknown'
    page = changes.preview(jobs, jobs.load(item['job_id'], 1, endpoint), {})
    assert page['rows'][-1]['native_values_previewed'] is False and 'lsn' not in page['rows'][-1]


def test_changed_or_linked_artifacts_are_refused(decoding):
    jobs, _source, endpoint, _connection = decoding
    item = review(decoding, 'wal_slot_sql_peek_text'); start(decoding, item); finished(decoding, item)
    saved = jobs.load(item['job_id'], 1, endpoint); path = jobs.directory(saved)/changes.FILENAME
    with path.open('ab') as output: output.write(b'changed')
    with pytest.raises(ContinuityError, match='changed after verification'):
        with changes.payload(jobs, saved): pass
    if os.name != 'nt':
        relocated = path.with_suffix('.moved'); path.rename(relocated); path.symlink_to(relocated)
        with pytest.raises(ContinuityError, match='owned regular file'): changes.reconcile(jobs, saved)


def test_damaged_partial_records_are_reported_as_raw_bytes_without_native_fields(decoding):
    jobs, _source, endpoint, connection = decoding
    connection.stream_failure = RuntimeError('lost response')
    item = review(decoding, 'wal_slot_sql_get_text'); start(decoding, item); finished(decoding, item)
    saved = jobs.load(item['job_id'], 1, endpoint)
    with (jobs.directory(saved)/changes.PARTIAL).open('ab') as output: output.write(b'{"data":\xff}\n')
    changes.reconcile(jobs, saved)
    page = changes.preview(jobs, jobs.load(item['job_id'], 1, endpoint), {})
    assert page['rows'][0]['lsn'] == 'FFFFFFFF/FFFFFFFF'
    assert page['rows'][1]['native_values_previewed'] is False and 'lsn' not in page['rows'][1]


@pytest.mark.parametrize('server_encoding,client_encoding', [
    ('SQL_ASCII','UTF8'), ('SQL_ASCII','SQL_ASCII'), ('UTF8','SQL_ASCII'), ('LATIN1','SQL_ASCII')])
@pytest.mark.parametrize('binary', [False, True])
def test_ascii_wire_modes_preserve_exact_native_payload_bytes(decoding, server_encoding, client_encoding, binary):
    jobs, _source, endpoint, connection = decoding
    settings = {b'server_encoding': server_encoding.encode(), b'client_encoding': client_encoding.encode()}
    connection.pgconn = SimpleNamespace(parameter_status=settings.get)
    raw = b"native\x80\xff\x00\r\n"
    connection.rows = [(b'FFFFFFFF/FFFFFFFF', b'4294967295', base64.b64encode(raw))]
    item = review(decoding, 'wal_slot_sql_peek_binary' if binary else 'wal_slot_sql_peek_text')
    start(decoding, item); result = finished(decoding, item)
    assert result['native_sql_acknowledged'] and result['state']=='completed'
    with changes.payload(jobs, jobs.load(item['job_id'], 1, endpoint)) as source: row=json.loads(source.read())
    assert row['lsn']=='FFFFFFFF/FFFFFFFF' and row['xid']=='4294967295'
    assert row['data_encoding']==('base64' if binary else 'base64-native-text')
    assert base64.b64decode(row['data'])==raw
    assert result['native_sql_result']['native_server_encoding']==server_encoding
    assert result['native_sql_result']['native_client_encoding']==client_encoding
    assert ('pg_catalog.convert_to(data,' in connection.calls[0][0]) is (not binary)
