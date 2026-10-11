"""Monitoring isolation, transaction freshness, exact counters and cleanup."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.providers.firebird.monitoring import (
    CounterEpoch, DATABASE_FIELDS, IO_FIELDS, MEMORY_FIELDS, RECORD_FIELDS,
    FirebirdMonitor,
)


def fixture():
    cursor = Mock()
    database = {key: 0 for key in DATABASE_FIELDS}
    database.update(DATABASE_NAME='demo.fdb', GUID='guid', FILE_ID='file',
                    OWNER='SYSDBA', PAGE_SIZE=8192, PAGES=2**54,
                    PAGE_BUFFERS=128, NEXT_TRANSACTION=123)
    rows = [
        (100, 200, 'SYSDBA', '5.0.4'),
        tuple(database[key] for key in DATABASE_FIELDS), (True,),
        (3, 1, 2, 0, 1, 1), (1, 0, 0, 12),
        tuple(2**54 for _ in IO_FIELDS),
        tuple(2**54 for _ in RECORD_FIELDS), tuple(100 for _ in MEMORY_FIELDS),
    ]
    cursor.fetchone.side_effect = rows
    cursor.fetchmany.return_value = []
    connection = Mock(cursor=Mock(return_value=cursor))
    connection.info.pages_used = 100
    connection.info.pages_free = 20
    connection.info.get_info.return_value = ''
    connection.main_transaction.info.is_read_only.return_value = True
    client = Mock(_connect=Mock(return_value=connection), _connections=[])
    factory = Mock(return_value=client)
    monitor = FirebirdMonitor(None, {'database': 'demo.fdb'},
                              client_factory=factory)
    return monitor, client, connection, cursor, rows


def test_native_snapshot_is_readonly_exact_and_separate_from_user_defaults():
    monitor, client, connection, cursor, _ = fixture()
    sample = monitor.sample()
    assert sample['status'] == 'available'
    assert sample['collector']['attachment_id'] == '100'
    assert sample['coverage'] == 'database'
    assert sample['derived']['allocated_bytes'] == str(2**54 * 8192)
    assert sample['groups']['io']['values']['page_reads'] == str(2**54)
    assert sample['rates']['status'] == 'gap'
    assert sample['transaction_refresh'] == {
        'status': 'completed', 'read_only': True, 'retaining': False}
    route = client._connect.call_args.args[0]['route']
    assert route['transaction_access'] == 'READ'
    assert route['transaction_lock_timeout'] == 0
    assert route['transaction_auto_commit'] is False
    connection.rollback.assert_called_once_with()
    connection.commit.assert_not_called()
    cursor.close.assert_called_once()
    assert all(call.args[0].startswith('SELECT ')
               for call in cursor.execute.call_args_list)
    assert not any('SQL_TEXT' in call.args[0] or 'CONTEXT_VARIABLES' in call.args[0]
                   for call in cursor.execute.call_args_list)


def test_reuses_only_owned_attachment_with_fresh_nonretaining_transactions():
    monitor, client, connection, cursor, rows = fixture()
    monitor.sample()
    cursor.fetchone.side_effect = rows
    second = monitor.sample()
    assert second['rates']['status'] == 'available'
    client._connect.assert_called_once()
    assert connection.rollback.call_count == 2
    assert all(not c.args and not c.kwargs
               for c in connection.rollback.call_args_list)
    monitor.close()
    client.close.assert_called_once()
    with pytest.raises(Exception, match='closed'):
        monitor.sample()


@pytest.mark.parametrize('visibility', [False, None])
def test_visibility_never_assumes_global_counts(visibility):
    monitor, _, _, cursor, rows = fixture()
    rows[2] = (visibility,)
    cursor.fetchone.side_effect = rows
    assert monitor.sample()['coverage'] == 'visible-to-collector'


def test_error_and_failed_release_are_owned_redacted_and_retry_before_reconnect():
    monitor, client, connection, cursor, rows = fixture()
    cursor.execute.side_effect = RuntimeError('password=secret')
    client._forget_and_close.side_effect = RuntimeError('private-path')
    first = monitor.sample()
    assert first['status'] == 'unavailable'
    assert first['release']['status'] == 'unconfirmed'
    assert 'secret' not in str(first) and 'private-path' not in str(first)
    assert monitor._connection is connection
    monitor.sample()
    client._connect.assert_called_once()  # No new connection until released.
    client._forget_and_close.side_effect = None
    cursor.execute.side_effect = None
    cursor.fetchone.side_effect = rows
    assert monitor.sample()['status'] == 'available'
    assert client._connect.call_count == 2


def test_transaction_end_failure_invalidates_sample_and_forces_release():
    monitor, client, connection, _, _ = fixture()
    connection.rollback.side_effect = RuntimeError('failure')
    sample = monitor.sample()
    assert sample['status'] == 'unavailable'
    assert 'transaction_refresh' not in sample
    client._forget_and_close.assert_called_once_with(connection)
    assert monitor._connection is None


def test_missing_optional_counter_group_produces_gap_not_zero():
    monitor, _, _, cursor, rows = fixture()
    rows[5] = RuntimeError('private-native-diagnostic')
    cursor.fetchone.side_effect = rows
    sample = monitor.sample()
    assert sample['status'] == 'partial'
    assert sample['groups']['io']['status'] == 'unavailable'
    assert 'values' not in sample['groups']['io']
    assert sample['rates']['reason'] == 'missing-counters'
    assert sample['transaction_refresh']['status'] == 'completed'
    assert 'private-native' not in str(sample)


def test_exact_monotonic_rates_and_reset_boundaries():
    rates = CounterEpoch()
    first = rates.observe('db', {'reads': 2**54}, 10**9)
    next_sample = rates.observe('db', {'reads': 2**54 + 3}, 3 * 10**9)
    assert next_sample['epoch'] == first['epoch']
    assert next_sample['per_second']['reads'] == '1.5'
    assert next_sample['delta']['reads'] == '3'
    reset = rates.observe('db', {'reads': 4}, 4 * 10**9)
    assert reset['epoch'] != first['epoch']
    assert reset['reason'] == 'counter-decreased'
    changed = rates.observe('other-db', {'reads': 9}, 5 * 10**9)
    assert changed['reason'] == 'identity-changed'
    assert not changed['per_second']
    missing = rates.observe('other-db', {}, 6 * 10**9)
    assert missing['reason'] == 'counter-coverage-changed'


def test_server_only_uses_dedicated_services_handle():
    info = SimpleNamespace(version='5.0.4', engine_version=5.0,
                           architecture='SuperServer', manager_version=2,
                           capabilities=4, connection_count=7,
                           attached_databases=['demo.fdb'])
    connection = SimpleNamespace(info=info)
    client = Mock(_connect_server=Mock(return_value=connection), _connections=[])
    monitor = FirebirdMonitor(None, {'host': 'localhost'}, scope='server',
                              client_factory=Mock(return_value=client))
    sample = monitor.sample()
    assert sample['status'] == 'available'
    client._connect.assert_not_called()
    assert sample['groups']['connection_count']['values'] == '7'
    assert sample['coverage'] == 'service-visible-attached-databases'
    monitor.close()


def test_native_transaction_must_confirm_readonly_before_monitoring():
    monitor, client, connection, cursor, _ = fixture()
    connection.main_transaction.info.is_read_only.return_value = False
    sample = monitor.sample()
    assert sample['status'] == 'unavailable'
    assert 'transaction_refresh' not in sample
    assert cursor.execute.call_count == 1
    connection.rollback.assert_called_once()
    client._forget_and_close.assert_called_once_with(connection)


def test_activity_details_are_bounded_exact_and_exclude_collector():
    monitor, _, connection, cursor, _ = fixture()
    cursor.fetchmany.side_effect = [
        [(2**54, 'USER', 'ROLE', 'TCPv4', 'localhost', None, 0, 0)] * 101,
        [(9, 2**54, None, 0, 1, 1, 0, 0, 1)], [],
    ]
    sample = monitor.sample()
    attachments = sample['groups']['attachment_details']['values']
    assert len(attachments['rows']) == 100
    assert attachments['truncated'] is True
    assert attachments['rows'][0]['attachment_id'] == str(2**54)
    assert sample['groups']['transaction_details']['values']['truncated'] is False
    queries = [call.args[0] for call in cursor.execute.call_args_list
               if 'FIRST 101' in call.args[0] and 'ORDER BY MON$TIMESTAMP' in call.args[0]]
    assert len(queries) == 3
    assert all('MON$ATTACHMENT_ID <> CURRENT_CONNECTION' in sql for sql in queries)
    connection.rollback.assert_called_once_with()


def test_explicit_statement_inspection_is_bounded_identity_checked_and_refreshed():
    monitor, _, connection, cursor, _ = fixture()
    sample = monitor.sample()
    reference = {'source_epoch': sample['source_epoch'], 'statement_id': '12', 'attachment_id': '13',
                 'compiled_statement_id': '14', 'timestamp': 'time'}
    cursor.fetchone.side_effect = None
    cursor.fetchone.return_value = (12, 13, 14, 'time', 'ü' * 4097, 'native plan')
    observed = monitor.inspect_statement(reference)
    assert observed['status'] == 'available'
    assert observed['sql_text'] == {'value': 'ü' * 4096, 'truncated': True}
    assert observed['explained_plan'] == {'value': 'native plan', 'truncated': False}
    assert connection.rollback.call_count == 2
    assert any('SUBSTRING(MON$SQL_TEXT FROM 1 FOR 4097)' in call.args[0]
               for call in cursor.execute.call_args_list)
    assert 'MON$CALL_STACK WHERE MON$STATEMENT_ID = ?' in cursor.execute.call_args.args[0]
    assert any(len(call.args) == 2 and call.args[1] == (12, 13)
               for call in cursor.execute.call_args_list)
    assert cursor.execute.call_args.args[1] == (12,)
    changed = monitor.inspect_statement({**reference, 'compiled_statement_id': 'other'})
    assert changed['status'] == 'changed' and 'sql_text' not in changed
    cursor.fetchone.return_value = None
    assert monitor.inspect_statement(reference)['status'] == 'gone'
    assert monitor.inspect_statement({**reference, 'source_epoch': 'stale'})['status'] == 'unavailable'
    connection.commit.assert_not_called()


def test_statement_inspection_cannot_publish_text_from_write_transaction():
    monitor, _, connection, cursor, _ = fixture()
    sample = monitor.sample()
    connection.main_transaction.info.is_read_only.return_value = False
    with pytest.raises(Exception, match='read-only'):
        monitor.inspect_statement({'source_epoch': sample['source_epoch'], 'statement_id': '12', 'attachment_id': '13'})
    assert connection.rollback.call_count == 2


def test_inventory_has_independent_cadence_and_retains_observation_time():
    monitor, _, _, cursor, _ = fixture()
    from pgadmin.cdeadmin.providers.firebird.monitoring_inventory import ACTIVITY, METADATA
    first = {'groups': {}, 'started_at': 'first'}
    monitor._inventory(cursor, first, 10**9)
    count = cursor.execute.call_count
    second = {'groups': {}, 'started_at': 'second'}
    monitor._inventory(cursor, second, 6 * 10**9)
    assert cursor.execute.call_count == count + len(ACTIVITY)
    for name in METADATA:
        assert second['groups'][name]['observed_at'] == 'first'
        assert second['groups'][name]['age_seconds'] == '5'
    third = {'groups': {}, 'started_at': 'third'}
    monitor._inventory(cursor, third, 61 * 10**9)
    assert third['groups']['backup_details']['observed_at'] == 'third'


def test_inventory_failure_stays_unavailable_and_cache_is_not_shared():
    monitor, _, _, cursor, _ = fixture()
    cursor.execute.side_effect = RuntimeError('secret')
    result = {'groups': {}, 'started_at': 'first'}
    monitor._inventory(cursor, result, 0)
    assert result['groups']['backup_details']['status'] == 'unavailable'
    assert 'secret' not in str(result)
    result['groups']['backup_details']['status'] = 'tampered'
    assert monitor._metadata_cache['backup_details']['status'] == 'unavailable'


def test_native_inventory_truncation_and_column_validation():
    from pgadmin.cdeadmin.providers.firebird.monitoring_inventory import rows
    cursor = Mock()
    cursor.fetchmany.return_value = [(i,) for i in range(101)]
    result = rows(cursor, 'SELECT example', ('id',))
    assert len(result['rows']) == 100 and result['truncated']
    cursor.fetchmany.return_value = [(1, 2)]
    with pytest.raises(Exception, match='Invalid native inventory row'):
        rows(cursor, 'SELECT example', ('id',))


def test_table_rates_do_not_bridge_missing_observations():
    from pgadmin.cdeadmin.providers.firebird.monitoring_inventory import (
        ACTIVITY, METADATA, TABLE_COUNTERS,
    )
    monitor, _, _, cursor, _ = fixture()
    def observe(value, instant):
        table = [] if value is None else [('TABLE', instant, 7, *([value] * len(TABLE_COUNTERS)))]
        cursor.fetchmany.side_effect = [table if name == 'table_details' else []
                                      for name in ACTIVITY] + [[]] * len(METADATA)
        result = {'groups': {}, 'started_at': 'now', 'coverage': 'database'}
        monitor._inventory(cursor, result, instant * 10**9)
        return result['groups']['table_details']['values']['rows']
    assert observe(10, 1)[0]['rate_status'] == 'gap'
    assert observe(20, 3)[0]['record_seq_reads_per_second'] == '5'
    assert observe(None, 4) == []
    assert observe(30, 5)[0]['rate_status'] == 'gap'


def test_compiled_inspection_rechecks_identity_and_bounds_native_text():
    monitor, _, connection, cursor, _ = fixture()
    sample = monitor.sample()
    reference = {'kind': 'compiled', 'source_epoch': sample['source_epoch'],
                 'compiled_statement_id': '18', 'object_name': None,
                 'object_type': None, 'package_name': None, 'stat_id': '19'}
    cursor.fetchone.side_effect = None
    cursor.fetchone.return_value = (18, None, None, None, 19, 'x' * 4097, None)
    result = monitor.inspect_statement(reference)
    assert result['status'] == 'available'
    assert len(result['sql_text']['value']) == 4096
    assert result['sql_text']['truncated']
    cursor.fetchone.return_value = (18, 'CHANGED_OBJECT', None, None, 20, 'private', None)
    result = monitor.inspect_statement(reference)
    assert result['status'] == 'changed' and 'private' not in str(result)
    assert connection.rollback.call_count == 3


def test_explicit_account_inspection_is_bounded_and_refreshes_snapshot():
    monitor, _, connection, cursor, _ = fixture()
    sample = monitor.sample()
    cursor.fetchmany.return_value = [('ALICE', 'Srp', True, False, 'First', None, None)] * 101
    result = monitor.inspect_details('accounts', sample['source_epoch'])
    assert result['status'] == 'available' and result['truncated']
    assert len(result['rows']) == 100
    assert result['rows'][0]['active'] is True
    assert connection.rollback.call_count == 2
    assert monitor.inspect_details('accounts', 'old')['status'] == 'unavailable'


def test_explicit_log_bounds_bytes_and_always_releases_separate_handle():
    monitor, client, _, _, _ = fixture()
    monitor.scope = 'server'
    monitor._source_epoch = 'epoch'
    monitor._connection = Mock()
    service = Mock()
    service.readline_timed.return_value = 'é' * 50000
    client._connect_server.return_value = service
    result = monitor.inspect_details('server-log', 'epoch')
    assert result['truncated'] and len(result['text'].encode('utf8')) == 65536
    client._forget_and_close.assert_called_once_with(service)
    service.readline_timed.side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        monitor.inspect_details('server-log', 'epoch')
    assert client._forget_and_close.call_count == 2
    assert monitor._needs_release


def test_failed_detail_cursor_release_is_owned_until_connection_cleanup():
    monitor, _, connection, cursor, _ = fixture()
    sample = monitor.sample()
    cursor.close.side_effect = RuntimeError('release-failed')
    with pytest.raises(RuntimeError):
        monitor.inspect_details('accounts', sample['source_epoch'])
    assert monitor._needs_release and connection.rollback.call_count == 2
    assert monitor.inspect_details('accounts', sample['source_epoch'])['status'] == 'unavailable'
