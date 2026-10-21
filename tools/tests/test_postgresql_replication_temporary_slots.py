"""Original replication ownership and nonintrusive snapshot admission."""
from collections import deque, OrderedDict
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from psycopg.pq import TransactionStatus

from pgadmin.cdeadmin.providers.postgresql.replication_temporary_slots import (
    ReplicationTemporarySlots, TemporarySlotError, options,
)
from pgadmin.cdeadmin.workspace.postgresql_replication_temporary_service import target


@pytest.mark.parametrize('operation,value', [
    (None, {}), ([], {}), ('unknown', {}), ('drop', []),
    ('drop', {'slot': 'Upper'}), ('drop', {'slot': 'other; DROP'}),
    ('drop', {'slot': 'x' * 64}), ('drop', {'slot': 'native', 'query': 'SQL'}),
    ('drop', {'slot': 'native', 'timeout_seconds': True}),
    ('drop', {'slot': 'native', 'timeout_seconds': 0}),
    ('drop', {'slot': 'native', 'invalidate_snapshot': 1}),
    ('physical_create', {'slot': 'native', 'reserve_wal': 'true'}),
    ('logical_create', {'slot': 'native', 'plugin': ''}),
    ('logical_create', {'slot': 'native', 'plugin': '雪' * 22}),
    ('logical_create', {'slot': 'native', 'plugin': 'native\0plugin'}),
    ('logical_create', {'slot': 'native', 'plugin': '\ud800'}),
    ('logical_create', {'slot': 'native', 'plugin': 'embedded"quote'}),
    ('logical_create', {'slot': 'native', 'snapshot': []}),
    ('logical_create', {'slot': 'native', 'snapshot': 'invalid-native-mode'}),
    ('logical_create', {'slot': 'native', 'two_phase': 1}),
])
def test_native_options_refuse_unadmitted_modes_and_lossy_or_untyped_values(operation, value):
    with pytest.raises(TemporarySlotError):
        options(operation, value)


def test_native_options_preserve_exact_names_flags_and_full_client_deadline():
    selected = options('logical_create', {'slot': '0_native', 'plugin': '雪' * 21,
        'snapshot': 'nothing', 'two_phase': True, 'failover': False,
        'invalidate_snapshot': True, 'timeout_seconds': 2147483647})
    assert selected['plugin'] == '雪' * 21 and selected['timeout_seconds'] == 2147483647
    assert selected['two_phase'] is True and selected['snapshot'] == 'nothing'
    assert options('physical_create', {'slot': 'native', 'timeout_seconds': None})['timeout_seconds'] is None


@pytest.mark.parametrize('value', [None, [], 'postgresql-database:123',
    'postgresql-replication-database:', 'postgresql-replication-database:00',
    'postgresql-replication-database:FF', 'postgresql-replication-database:61 62',
    'postgresql-replication-database:AB', 'postgresql-replication-database:gg'])
def test_native_database_identity_cannot_alias_other_interfaces_or_encodings(value):
    with pytest.raises(TemporarySlotError):
        target(value)


def native():
    value = ReplicationTemporarySlots.__new__(ReplicationTemporarySlots)
    value.connection = SimpleNamespace(closed=False, broken=False, autocommit=True,
        info=SimpleNamespace(transaction_status=TransactionStatus.IDLE), cursor=Mock(side_effect=AssertionError('Native observation dispatched')))
    value.usable = True
    value.resource_id = 'native-resource'
    value.backend_pid = '123'
    value.adapter_sha256 = 'native-adapter'
    value.source = {'database': "Native DB ü '"}
    value.snapshot = {'snapshot_name': '0000007F-00000003-1'}
    value.acknowledgements = deque(maxlen=100)
    value.acknowledgement_count = 0
    value.owned_slots = {'original'}
    value.owned_slot_kinds = {'original': 'logical'}
    value.copy_sources = OrderedDict()
    return value


def test_review_and_status_preserve_snapshot_without_native_commands():
    value = native()
    with patch('psycopg.ClientCursor', side_effect=AssertionError('Native observation dispatched')):
        before = value.snapshot.copy()
        page = value.inventory()
        assert page['snapshot'] == before and not page['slot_catalog_observed']
        assert page['server_health_checked'] is False
        with pytest.raises(TemporarySlotError, match='invalidation'):
            value.review('drop', {'slot': 'original'})
        reviewed = value.review('drop', {'slot': 'original', 'invalidate_snapshot': True})
        assert reviewed['snapshot_before'] == before and value.snapshot == before


def test_old_acknowledgement_cannot_authorize_drop_of_a_reused_foreign_slot_name():
    value = native()
    value.snapshot = None
    value.acknowledgements.append({'slot': 'reused', 'operation': 'physical_create'})
    with pytest.raises(TemporarySlotError, match='original backend'):
        value.review('drop', {'slot': 'reused'})
    value.connection.cursor.assert_not_called()


def test_recent_acknowledgements_are_bounded_and_full_catalog_is_not_fabricated():
    value = native()
    value.acknowledgements.extend({'slot': 's' + str(index)} for index in range(250))
    value.acknowledgement_count = 250
    page = value.inventory(offset=0, limit=2)
    assert page['acknowledgement_count'] == 250 and page['acknowledgement_window_start'] == 150
    assert page['offset'] == 150 and page['acknowledgements'] == [{'slot': 's150'}, {'slot': 's151'}]
    assert page['full_command_receipts_separately_paged'] is True
    assert not page['slot_catalog_observed'] and len(value.acknowledgements) == 100


def test_native_error_keeps_its_sqlstate_while_observer_joins_before_owner_closure():
    from psycopg.errors import UndefinedFile
    value = native()
    reviewed = value.review('logical_create', {'slot': 'new_slot', 'snapshot': 'nothing', 'invalidate_snapshot': True})
    cursor = Mock()
    cursor.execute.side_effect = UndefinedFile('owned native plugin unavailable')
    def finish():
        assert value.usable is True  # The observer itself has not failed.
    factory = Mock()
    factory.return_value.__enter__ = Mock(return_value=cursor)
    factory.return_value.__exit__ = Mock(return_value=False)
    with patch('psycopg.ClientCursor', factory), pytest.raises(TemporarySlotError) as error:
        value.command(reviewed, Mock(), finished=finish)
    assert error.value.sqlstate == '58P01' and value.usable is False
    assert value.snapshot is None
    with pytest.raises(TemporarySlotError, match='original native replication backend'):
        value.review('drop', {'slot': 'original'})


def test_cancelled_before_dispatch_does_not_invalidate_the_held_native_snapshot():
    value = native(); before = value.snapshot.copy()
    reviewed = value.review('drop', {'slot': 'original', 'invalidate_snapshot': True})
    cursor = Mock(); factory = Mock()
    factory.return_value.__enter__ = Mock(return_value=cursor)
    factory.return_value.__exit__ = Mock(return_value=False)
    with patch('psycopg.ClientCursor', factory), pytest.raises(TemporarySlotError, match='before dispatch'):
        value.command(reviewed, Mock(), dispatching=Mock(side_effect=TemporarySlotError('cancelled before dispatch')))
    cursor.execute.assert_not_called()
    assert value.usable and value.snapshot == before and value.owned_slots == {'original'}


@pytest.mark.parametrize('fields', [
    {'start_lsn': '0/0;SQL'}, {'start_lsn': '100000000/0'}, {'start_lsn': None},
    {'acknowledge_flush': 1}, {'max_messages': 0}, {'max_capture_bytes': True},
    {'max_duration_seconds': -1}, {'plugin_options': {}},
    {'plugin_options': [{'name': 'x', 'value': 'x', 'secret': True}]},
    {'plugin_options': [{'name': 'embedded"quote', 'value': 'x'}]},
    {'plugin_options': [{'name': 'x', 'value': 'nul\0'}]},
    {'plugin_options': [{'name': '\ud800', 'value': 'x'}]},
])
def test_stream_admission_preserves_native_lsn_switches_and_option_grammar(fields):
    with pytest.raises(TemporarySlotError):
        options('logical_stream', {'slot': 'original', **fields})


def test_stream_review_requires_current_logical_ownership_and_explicit_export_invalidation():
    value = native()
    with pytest.raises(TemporarySlotError, match='invalidation'):
        value.review('logical_stream', {'slot': 'original'})
    selected = {'slot': 'original', 'invalidate_snapshot': True, 'acknowledge_flush': True,
                'start_lsn': 'a/ff', 'max_messages': None, 'max_capture_bytes': None,
                'max_duration_seconds': None, 'plugin_options': [{'name': 'include-xids', 'value': '0'}]}
    reviewed = value.review('logical_stream', selected)
    assert reviewed['options']['start_lsn'] == 'A/FF' and value.snapshot is not None
    value.owned_slot_kinds['original'] = 'physical'
    with pytest.raises(TemporarySlotError, match='logical temporary slot'):
        value.review('logical_stream', selected)


def test_stream_ack_is_recorded_before_artifact_publication_failure_without_fabricating_new_slot():
    value = native()
    reviewed = value.review('logical_stream', {'slot': 'original', 'invalidate_snapshot': True})
    acknowledged = []
    def capture(_connection, _selected, acknowledge, dispatching):
        dispatching()
        acknowledge({'messages': '3', 'native_command_completions': 2})
        raise OSError('owned publication failure after native completion')
    value.stream_capture = capture
    with pytest.raises(OSError):
        value.command(reviewed, acknowledged.append)
    assert acknowledged[0]['capture']['native_command_completions'] == 2
    assert value.acknowledgement_count == 1 and value.owned_slots == {'original'}
    assert value.owned_slot_kinds == {'original': 'logical'}
    assert value.snapshot is None and not value.usable


def test_stream_artifact_refusal_before_dispatch_keeps_original_snapshot_and_backend():
    value = native()
    before = value.snapshot.copy()
    reviewed = value.review('logical_stream', {'slot': 'original', 'invalidate_snapshot': True})
    value.stream_capture = Mock(side_effect=OSError('owned artifact directory unavailable'))
    dispatching = Mock()
    with pytest.raises(OSError):
        value.command(reviewed, Mock(), dispatching=dispatching)
    dispatching.assert_not_called()
    assert value.snapshot == before and value.usable


def test_snapshot_use_records_native_begin_before_a_failed_slot_without_claiming_final_ack():
    from psycopg.errors import UndefinedFile
    value = native()
    reviewed = value.review('logical_create', {'slot': 'new_slot', 'snapshot': 'use', 'invalidate_snapshot': True})
    phases = []
    value.phase_acknowledge = phases.append
    cursor = Mock()
    def execute(command):
        if command == 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY':
            value.connection.info.transaction_status = TransactionStatus.INTRANS
        else:
            assert phases[0][0]['phase'] == 'snapshot_transaction_begin'
            raise UndefinedFile('owned plugin unavailable')
    cursor.execute.side_effect = execute
    factory = Mock()
    factory.return_value.__enter__ = Mock(return_value=cursor)
    factory.return_value.__exit__ = Mock(return_value=False)
    acknowledge = Mock()
    with patch('psycopg.ClientCursor', factory), pytest.raises(TemporarySlotError) as error:
        value.command(reviewed, acknowledge)
    assert error.value.sqlstate == '58P01' and len(phases) == 1
    acknowledge.assert_not_called()
    assert value.owns_snapshot_transaction and not value.usable


@pytest.mark.parametrize('operation,selected', [
    ('snapshot_end', {}), ('snapshot_end', {'decision': 'automatic'}),
    ('snapshot_end', {'decision': 'commit', 'slot': 'native'}),
    ('snapshot_tables', {'offset': True}), ('snapshot_tables', {'limit': 101}),
    ('snapshot_copy', {'relation_oid': '0'}), ('snapshot_copy', {'relation_oid': '0007'}),
    ('snapshot_copy', {'relation_oid': '4294967296'}), ('snapshot_copy', {'relation_oid': '1;SELECT'}),
    ('snapshot_copy', {'relation_oid': '7', 'include_descendants': 1}),
])
def test_owned_snapshot_options_require_exact_native_scope(operation, selected):
    with pytest.raises(TemporarySlotError):
        options(operation, selected)


def test_original_snapshot_copy_and_end_require_the_owned_native_transaction():
    value = native()
    with pytest.raises(TemporarySlotError, match='No owned'):
        value.review('snapshot_copy', {'relation_oid': '7', 'invalidate_snapshot': True})
    value.snapshot = None
    value.owns_snapshot_transaction = True
    value.used_snapshot = {'slot': 'original', 'consistent_point': '0/1234'}
    value.connection.info.transaction_status = TransactionStatus.INTRANS
    with pytest.raises(TemporarySlotError, match='End the original'):
        value.review('logical_stream', {'slot': 'original'})
    with pytest.raises(TemporarySlotError, match='Inspect the selected relation'):
        value.review('snapshot_copy', {'relation_oid': '7'})
    value.copy_sources['7'] = {'relation_oid': '7'}
    with patch('pgadmin.cdeadmin.providers.postgresql.replication_snapshot_copy.relation', side_effect=AssertionError('Native SQL during review')) as relation:
        reviewed = value.review('snapshot_copy', {'relation_oid': '7'})
    assert reviewed['copy_source'] == {'relation_oid': '7', 'used_snapshot': value.used_snapshot,
                                      'copy_format': 'binary', 'copy_options': {}, 'include_descendants': True}
    relation.assert_not_called()
    reviewed = value.review('snapshot_end', {'decision': 'rollback'})
    assert reviewed['used_snapshot_before'] == value.used_snapshot
    value.connection.info.transaction_status = TransactionStatus.IDLE
    with pytest.raises(TemporarySlotError, match='unavailable'):
        value.review('snapshot_end', {'decision': 'commit'})
