"""Prepare-only plan ownership and native wire-text boundaries."""
import ctypes
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tools.tests.test_firebird_async_queries import rig  # noqa: F401
from pgadmin.cdeadmin.providers.firebird.query_plans import (
    decode_info, validate_source,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def encoded(item, text, marker=1, codec='utf8'):
    data = text.encode(codec)
    return (bytes([item]) + len(data).to_bytes(2, 'little') +
            data + bytes([marker]))


@pytest.mark.parametrize('marker', [1, 2])
def test_native_plan_charset_and_truncation_are_independent(marker):
    result = decode_info(encoded(22, 'PLAN café', marker, 'latin1'), 22,
                         'latin1')
    assert result == {'text': 'PLAN café', 'truncated': marker == 2,
                      'complete': marker == 1, 'supplied': True}
    with pytest.raises(RelationalClientError, match='decoded'):
        decode_info(encoded(22, 'PLAN café', marker, 'latin1'), 22, 'utf8')


@pytest.mark.parametrize('raw', [b'', b'\x16', b'\x16\x02\x00x',
                                 b'\x16\xff\xffx\x01', b'\x03',
                                 b'\x16\x00\x00\x00', b'\x1a\x00\x00\x01'])
def test_invalid_native_envelopes_are_not_complete_empty_plans(raw):
    with pytest.raises(RelationalClientError):
        decode_info(raw, 22, 'utf8')


def test_native_no_plan_and_truncated_without_payload_are_distinct():
    assert decode_info(b'\x01', 22, 'utf8') == {
        'text': None, 'complete': True, 'truncated': False, 'supplied': False}
    assert decode_info(b'\x02', 22, 'utf8') == {
        'text': None, 'complete': False, 'truncated': True, 'supplied': False}


@pytest.mark.parametrize('source', ['', None, 'SELECT\0', '\ud800',
                                    'é' * (512 * 1024 + 1)])
def test_plan_source_rejects_invalid_or_oversized_text(source):
    with pytest.raises(RelationalClientError):
        validate_source(source)


def prepared(rig, *, active=True):
    rig.handle._statements = []
    rig.handle.sql_dialect = 3
    rig.handle._encoding = 'utf8'
    rig.handle.main_transaction.is_active.return_value = active
    statement = Mock()
    statement.get_type.return_value = SimpleNamespace(name='SELECT')
    statement.get_input_metadata.return_value.get_count.return_value = 1
    from enum import IntEnum
    SQLDataType = IntEnum("SQLDataType", {"LONG": 496})
    metadata = statement.get_input_metadata.return_value
    metadata.get_type.return_value = SQLDataType.LONG
    metadata.get_field.return_value = 'ID'
    metadata.get_relation.return_value = 'T'
    metadata.get_subtype.return_value = 0
    metadata.get_length.return_value = 4
    metadata.get_scale.return_value = 0
    metadata.get_charset.return_value = 0
    metadata.is_nullable.return_value = True
    statement.get_output_metadata.return_value.get_count.return_value = 2

    def info(items, buffer):
        data = encoded(items[0], 'PLAN café' if items[0]
                       == 22 else 'Native tree')
        assert len(buffer) == 65539
        ctypes.memmove(buffer, data, len(data))

    statement.get_info.side_effect = info
    rig.handle._att.prepare.return_value = statement
    return statement


def submit(rig, source='DELETE FROM T WHERE ID=?', **policy):
    query = rig.client.submit_query(rig.handle, {
        'source': source, 'parameters': [], 'output_policy': {
            'firebird_plan': True, 'client_sql_dialect': 1, **policy}})
    query.worker.join(2)
    assert not query.worker.is_alive()
    return rig.client.describe_result(query)['payload']


@pytest.mark.parametrize('active', [False, True])
def test_prepare_never_executes_binds_or_finalizes_user_work(rig, active):
    statement = prepared(rig, active=active)
    result = submit(rig)
    assert result['execution_state'] == 'succeeded'
    plan = result['query_plan']
    assert plan['statement_execution_requested'] is False
    assert plan['transaction_started'] is (not active)
    assert plan['parameter_count'] == 1
    assert plan['column_count'] == 2
    assert plan['client_sql_dialect'] == 1
    assert plan['legacy']['text'] == 'PLAN café'
    statement.execute.assert_not_called()
    statement.open_cursor.assert_not_called()
    rig.cursor.execute.assert_not_called()
    rig.handle.commit.assert_not_called()
    rig.handle.rollback.assert_not_called()
    statement.free.assert_called_once_with()
    statement.get_input_metadata.return_value.release.assert_called_once_with()
    output = statement.get_output_metadata.return_value
    output.release.assert_called_once_with()
    assert rig.handle.main_transaction.begin.call_count == (not active)


def test_release_failure_preserves_owner_and_blocks_the_session(rig):
    statement = prepared(rig)
    statement.free.side_effect = RuntimeError('private detail')
    result = submit(rig)
    assert result['execution_state'] == 'failed'
    assert result['session_reuse_blocked']
    assert len(rig.client._state(rig.handle).failed_cursors) == 1
    assert 'private detail' not in str(result)
    with pytest.raises(RelationalClientError, match='result cleanup'):
        rig.client.submit_query(rig.handle, {'source': 'no retry'})
    statement.execute.assert_not_called()
    statement.free.side_effect = None


def test_plan_failure_redacts_source_and_blocks_dead_attachment(rig):
    prepared(rig)
    rig.handle._att.prepare.side_effect = RuntimeError(
        'private SQL and password')
    rig.handle.ping.side_effect = RuntimeError('lost connection')
    result = submit(rig)
    assert result['session_reuse_blocked_reason'] == (
        'attachment_liveness_failed')
    assert 'private SQL' not in str(result)
    rig.handle.commit.assert_not_called()
    rig.handle.rollback.assert_not_called()


@pytest.mark.parametrize('policy', [{'firebird_plan': 'yes'},
                                    {'firebird_script': True}])
def test_plan_mode_is_explicit_and_cannot_execute_scripts(rig, policy):
    with pytest.raises(RelationalClientError):
        submit(rig, 'SELECT 1;', **policy)
    rig.handle._att.prepare.assert_not_called()


def test_native_prepare_cancellation_releases_ownership_without_execution(rig):
    statement = prepared(rig)
    error = RuntimeError('owned cancellation')
    error.gds_codes = (335544794,)

    def waiting(*_args):
        rig.entered.set()
        assert rig.finish.wait(3)
        raise error

    rig.handle._att.prepare.side_effect = waiting
    query = rig.client.submit_query(rig.handle, {
        'source': 'SELECT * FROM T', 'parameters': [],
        'output_policy': {'firebird_plan': True}})
    assert rig.entered.wait(2)
    rig.client.cancel(query)
    rig.finish.set()
    query.worker.join(2)
    assert not query.worker.is_alive()
    result = rig.client.describe_result(query)['payload']
    assert result['execution_state'] == 'cancelled'
    statement.execute.assert_not_called()
    rig.handle.commit.assert_not_called()
    rig.handle.rollback.assert_not_called()
    assert rig.client._state(rig.handle).query is None


def test_metadata_release_failure_retains_both_native_owners(rig):
    statement = prepared(rig)
    metadata = statement.get_output_metadata.return_value
    metadata.release.side_effect = RuntimeError('owned release failure')
    result = submit(rig)
    assert result['session_reuse_blocked']
    owner = rig.client._state(rig.handle).failed_cursors[0]
    assert owner.metadata == [metadata]
    assert owner.statement is statement
    statement.free.assert_not_called()
    metadata.release.side_effect = None
    owner.close()
    statement.free.assert_called_once_with()


def test_native_parameter_descriptors_are_exact_and_source_bound(rig):
    import hashlib
    statement = prepared(rig)
    source = 'SELECT * FROM T WHERE ID = ?'
    result = submit(rig, source)['query_plan']
    assert result['source_sha256'] == hashlib.sha256(source.encode()).hexdigest()
    assert result['parameters_complete'] is True
    assert result['parameters'] == [{'position': 0, 'native_type': 'LONG', 'type_code': 496,
        'field': 'ID', 'relation': 'T', 'subtype': 0, 'length': 4, 'scale': 0, 'charset': 0, 'nullable': True}]
    statement.get_input_metadata.return_value.release.assert_called_once_with()


def test_large_parameter_metadata_is_explicitly_incomplete_and_released(rig):
    statement = prepared(rig)
    statement.get_input_metadata.return_value.get_count.return_value = 513
    result = submit(rig)['query_plan']
    assert result['parameter_count'] == 513 and result['parameters'] == []
    assert result['parameters_complete'] is False
    statement.get_input_metadata.return_value.release.assert_called_once_with()
