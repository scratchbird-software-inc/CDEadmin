"""Independent native snapshot ownership, import boundaries and refusal paths."""
from collections import deque, OrderedDict
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
import uuid

import pytest
from psycopg.pq import TransactionStatus

from pgadmin.cdeadmin.providers.postgresql.replication_snapshot_import import (
    install, reference, TemporarySlotError,
)
from pgadmin.cdeadmin.providers.postgresql.replication_temporary_slots import ReplicationTemporarySlots
from pgadmin.cdeadmin.workspace.postgresql_replication_temporary_jobs import ReplicationTemporaryResources


def exported():
    database = "Independent DB ü '"
    return {'exporter_job_id': str(uuid.uuid4()), 'exporter_resource_id': str(uuid.uuid4()),
            'exporter_backend_pid': '123',
            'source': {'system_identifier': '1234567890123456789', 'timeline': 1, 'server_version': 180003,
                       'authenticated_principal': 'native_repl', 'database': database,
                       'database_target_id': 'postgresql-replication-database:' + database.encode('utf8').hex(),
                       'admission_interface': 'logical-replication', 'provider_isolation_key': ['exact-registration']},
            'snapshot': {'snapshot_name': '0000007E-00000002-1', 'consistent_point': '0/12345', 'slot': 'source_slot'}}


def consumer(selected):
    value = ReplicationTemporarySlots.__new__(ReplicationTemporarySlots)
    value.connection = SimpleNamespace(closed=False, broken=False, autocommit=True,
        info=SimpleNamespace(transaction_status=TransactionStatus.IDLE))
    value.usable = True
    value.source = deepcopy(selected['source'])
    value.resource_id = str(uuid.uuid4())
    value.backend_pid = '456'
    value.adapter_sha256 = 'adapter'
    value.owns_snapshot_transaction = False
    value.snapshot = value.used_snapshot = None
    value.owned_slots = set()
    value.owned_slot_kinds = {}
    value.copy_sources = OrderedDict()
    value.acknowledgements = deque(maxlen=100)
    value.acknowledgement_count = 0
    return value


def cursor_for(native, selected, *, after=None, execute=None):
    row = (selected['source']['database'], selected['source']['authenticated_principal'],
           'ScratchRobin repl temp ' + selected['exporter_job_id'], '1792555457.624842', 'walsender')
    cursor = Mock()
    cursor.fetchone.side_effect = [row, row if after is None else after]
    def default(command, parameters=None):
        if command.startswith('BEGIN '):
            native.connection.info.transaction_status = TransactionStatus.INTRANS
    cursor.execute.side_effect = execute or default
    context = Mock()
    context.return_value.__enter__ = Mock(return_value=cursor)
    context.return_value.__exit__ = Mock(return_value=False)
    return context, cursor, row


def test_independent_import_sets_snapshot_as_first_transaction_command_without_owning_the_exporters_slot():
    selected = exported(); native = consumer(selected)
    factory, cursor, row = cursor_for(native, selected)
    acknowledgements = []
    with patch('psycopg.ClientCursor', factory):
        install(native, selected, acknowledgements.append, Mock())
    commands = cursor.execute.call_args_list
    assert len(commands) == 4
    assert commands[0].args[1] == (123,) and commands[3].args[1] == (123,)
    assert commands[1].args == ('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY',)
    assert commands[2].args == ('SET TRANSACTION SNAPSHOT %s', (selected['snapshot']['snapshot_name'],))
    assert [next(iter(value)) for value in acknowledgements] == [
        'snapshot_exporter_preverified', 'snapshot_transaction_begin_acknowledged',
        'snapshot_import_acknowledged', 'snapshot_exporter_postverified']
    assert native.used_snapshot['source_slot'] == 'source_slot'
    assert native.used_snapshot['exporter_backend_started_epoch'] == row[3]
    assert native.used_snapshot['exporter_connection_required_after_import'] is False
    assert native.inventory()['acknowledged_owned_slot_count'] == 0
    assert native.owned_slots == set() and native.snapshot is None
    with pytest.raises(TemporarySlotError, match='End the original'):
        native.review('logical_stream', {'slot': 'source_slot'})
    native.copy_sources['7'] = {'relation_oid': '7'}
    reviewed = native.review('snapshot_copy', {'relation_oid': '7'})
    assert reviewed['copy_source']['used_snapshot'] == native.used_snapshot
    assert reviewed['copy_source']['used_snapshot']['origin'] == 'imported-exported-snapshot'


@pytest.mark.parametrize('change', [
    {'exporter_job_id': 'other'}, {'exporter_resource_id': None}, {'exporter_backend_pid': '00123'},
    {'exporter_backend_pid': '2147483648'}, {'snapshot': {'snapshot_name': '../file'}},
    {'snapshot_name': '0000007E-00000002-1'}, {'source': {}},
])
def test_import_references_cannot_be_arbitrary_names_partial_metadata_or_aliases(change):
    selected = {**exported(), **change}
    with pytest.raises(TemporarySlotError):
        reference(selected)


@pytest.mark.parametrize('column,replacement', [(0, 'other database'), (1, 'other principal'),
    (2, 'another backend'), (3, None), (4, 'client backend')])
def test_native_exporter_refusal_never_starts_an_import_transaction(column, replacement):
    selected = exported(); native = consumer(selected)
    factory, cursor, row = cursor_for(native, selected)
    changed = list(row); changed[column] = replacement
    cursor.fetchone.side_effect = [tuple(changed)]
    acknowledge = Mock()
    with patch('psycopg.ClientCursor', factory), pytest.raises(TemporarySlotError, match='exporter backend identity'):
        install(native, selected, acknowledge, Mock())
    assert cursor.execute.call_count == 1 and not native.owns_snapshot_transaction and not native.usable
    acknowledge.assert_not_called()


def test_native_import_error_retains_begin_ack_and_sqlstate_without_false_import_ack_or_replay():
    from psycopg.errors import UndefinedObject
    selected = exported(); native = consumer(selected)
    def execute(command, parameters=None):
        if command.startswith('BEGIN '):
            native.connection.info.transaction_status = TransactionStatus.INTRANS
        elif command.startswith('SET TRANSACTION SNAPSHOT'):
            raise UndefinedObject('export disappeared after BEGIN')
    factory, cursor, _ = cursor_for(native, selected, execute=execute)
    acknowledged = []
    with patch('psycopg.ClientCursor', factory), pytest.raises(TemporarySlotError) as error:
        install(native, selected, acknowledged.append, Mock())
    assert error.value.sqlstate == '42704'
    assert acknowledged[-1]['snapshot_transaction_begin_acknowledged']
    assert not any(value.get('snapshot_import_acknowledged') for value in acknowledged)
    assert cursor.execute.call_count == 3 and not native.usable and native.used_snapshot is None


def test_import_ack_survives_changed_exporter_before_postverification_without_exposing_a_usable_snapshot():
    selected = exported(); native = consumer(selected)
    factory, cursor, row = cursor_for(native, selected)
    cursor.fetchone.side_effect = [row, (*row[:3], '1792555458.624842', row[4])]
    acknowledged = []
    with patch('psycopg.ClientCursor', factory), pytest.raises(TemporarySlotError, match='changed during'):
        install(native, selected, acknowledged.append, Mock())
    assert acknowledged[-1]['snapshot_import_acknowledged']
    assert not any(value.get('snapshot_import_verified') for value in acknowledged)
    assert native.used_snapshot is None and not native.usable and cursor.execute.call_count == 4


def test_begin_publication_failure_and_cancelled_dispatch_prevent_later_native_import():
    selected = exported(); native = consumer(selected)
    factory, cursor, _ = cursor_for(native, selected)
    def acknowledge(value):
        if value.get('snapshot_transaction_begin_acknowledged'):
            raise OSError('BEGIN receipt publication failed')
    with patch('psycopg.ClientCursor', factory), pytest.raises(OSError):
        install(native, selected, acknowledge, Mock())
    assert cursor.execute.call_count == 2 and not native.usable
    native = consumer(selected); factory, cursor, _ = cursor_for(native, selected)
    dispatch = Mock(side_effect=[None, None, TemporarySlotError('operator cancelled')])
    with patch('psycopg.ClientCursor', factory), pytest.raises(TemporarySlotError, match='operator cancelled'):
        install(native, selected, Mock(), dispatch)
    assert cursor.execute.call_count == 2 and not native.usable


def test_import_requires_exact_native_source_and_a_fresh_independent_connection():
    selected = exported(); native = consumer(selected)
    native.source['authenticated_principal'] = 'substituted_role'
    with patch('psycopg.ClientCursor', side_effect=AssertionError('unexpected native command')):
        with pytest.raises(TemporarySlotError, match='another native source'):
            install(native, selected, Mock(), Mock())
        native.source = deepcopy(selected['source']); native.owned_slots.add('other')
        with pytest.raises(TemporarySlotError, match='new independent'):
            install(native, selected, Mock(), Mock())


def test_server_derivation_binds_current_owner_scope_adapter_and_export_without_native_commands():
    selected = exported()
    record = {'job_id': selected['exporter_job_id'], 'native_resource_id': selected['exporter_resource_id'],
              'backend_pid': selected['exporter_backend_pid'], 'source': selected['source'], 'program': {'adapter': 'current'},
              'latest_native_inventory': {'snapshot': selected['snapshot']}}
    jobs = ReplicationTemporaryResources.__new__(ReplicationTemporaryResources)
    jobs.load = Mock(return_value=record); jobs.require_open = Mock()
    assert jobs.snapshot_reference(record['job_id'], 7, 'endpoint', record['source'], record['program']) == selected
    jobs.load.assert_called_once_with(record['job_id'], 7, 'endpoint')
    jobs.require_open.assert_called_once_with(record)
    for source, program in [({**record['source'], 'provider_isolation_key': ['other']}, record['program']),
                            (record['source'], {'adapter': 'changed'})]:
        with pytest.raises(TemporarySlotError, match='another native source'):
            jobs.snapshot_reference(record['job_id'], 7, 'endpoint', source, program)
    record['latest_native_inventory']['snapshot'] = None
    with pytest.raises(TemporarySlotError, match='no acknowledged'):
        jobs.snapshot_reference(record['job_id'], 7, 'endpoint', record['source'], record['program'])
