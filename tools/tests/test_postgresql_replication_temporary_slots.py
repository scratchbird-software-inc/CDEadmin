"""Original replication ownership and nonintrusive snapshot admission."""
from collections import deque
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
    ('logical_create', {'slot': 'native', 'snapshot': 'use'}),
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
