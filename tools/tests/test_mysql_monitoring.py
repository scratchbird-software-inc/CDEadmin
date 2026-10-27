"""Dedicated MySQL sampling must preserve scope, denial and failure evidence."""
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock

import pytest
from mysql.connector.errors import DatabaseError, InterfaceError
from pgadmin.cdeadmin.providers.mysql_family.mysql_monitoring import MySQLMonitor
from pgadmin.cdeadmin.providers.mysql_family.mysql_monitoring import counter_rates

IDENTITY = {'database_name': 'demo', 'version': '9.7.0', 'server_uuid': 'native-server',
            'collector_id': 42, 'account': 'monitor@%'}


def source():
    monitor = MySQLMonitor(SimpleNamespace(), {'host': 'db', 'database': 'demo'})
    monitor._connection = SimpleNamespace(in_transaction=False)
    monitor._client = Mock()
    monitor._epoch = 'owned-source'
    return monitor


def test_denied_group_is_unavailable_not_zero_and_success_is_completed_probe():
    monitor = source()
    def read(sql, params=None):
        if sql.startswith('SELECT DATABASE()'):
            return [dict(IDENTITY)]
        if 'performance_schema.threads' in sql:
            raise DatabaseError('private-source-text', errno=1142, sqlstate='42000')
        return []
    monitor._read = Mock(side_effect=read)
    result = monitor.sample()
    assert result['status'] == 'partial' and result['transaction_completed']
    assert result['groups']['activity']['status'] == 'unavailable'
    assert result['groups']['activity']['scope'] == 'database'
    assert result['groups']['activity']['error_code'] == 1142
    assert result['groups']['activity']['sqlstate'] == '42000'
    assert result['groups']['status']['scope'] == 'server'
    assert result['transaction_refresh']['status'] == 'completed'
    assert 'private-source-text' not in str(result)
    monitor.close()


@pytest.mark.parametrize('fault', [InterfaceError('private-wire-detail', errno=2013),
                                  ValueError('private-error-detail')])
def test_connection_or_unknown_failure_retires_owned_attachment_without_heartbeat(fault):
    monitor = source()
    native, client = monitor._connection, monitor._client
    monitor._read = Mock(side_effect=fault)
    result = monitor.sample()
    assert result['status'] == 'unavailable' and not result['transaction_completed']
    assert result['transaction_refresh']['status'] == 'not-completed'
    assert 'private-' not in str(result)
    client._discard_failed_session.assert_called_once_with(native)
    client.close.assert_called_once_with()
    assert monitor._connection is None


def test_changed_native_database_is_not_a_successful_sample():
    monitor = source()
    monitor._read = Mock(return_value=[{**IDENTITY, 'database_name': 'other'}])
    result = monitor.sample()
    assert result['status'] == 'unavailable' and not result['transaction_completed']
    assert not result['groups']


def test_dedicated_connection_does_not_enter_registered_pool(monkeypatch):
    client = Mock()
    create = Mock(return_value=client)
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mysql_family.provider._create_client', create)
    monitor = MySQLMonitor(SimpleNamespace(), {'host': 'db', 'database': 'demo',
        'autocommit': False, 'pool_size': 1, 'pool_name': 'interactive', 'pool_reset_session': True})
    monitor._open()
    route = client._connect.call_args.args[0]['route']
    assert route['autocommit'] is True
    assert not {'pool_size', 'pool_name', 'pool_reset_session'} & route.keys()
    assert route['read_timeout'] == route['write_timeout'] == route['connection_timeout'] == 5
    monitor.close()
    with pytest.raises(ValueError, match='closed'): monitor.sample()


def counter_sample(epoch='a', uptime='100', since_flush='90', questions='9007199254740993'):
    return {'transaction_completed': True, 'source_epoch': epoch, 'identity': {'server_uuid': 'server'},
        'groups': {'status': {'status': 'available', 'rows': [
            {'variable_name': key, 'variable_value': value} for key, value in {
                'Uptime': uptime, 'Uptime_since_flush_status': since_flush,
                'Questions': questions, 'Threads_connected': '2'}.items()]}}}


def test_rates_preserve_exact_differences_without_float_counter_rounding():
    result = counter_rates(counter_sample(), counter_sample(uptime='102', since_flush='92', questions='9007199254740998'), 2)
    assert result['per_second']['Questions'] == '2.5'
    assert 'Threads_connected' not in result['per_second']
    assert result['scope'] == 'server'


@pytest.mark.parametrize('change', ['epoch', 'server', 'uptime', 'flush', 'denied', 'incomplete', 'time'])
def test_rates_break_on_ownership_failure_or_native_reset(change):
    before, after, elapsed = counter_sample(), counter_sample(uptime='102', since_flush='92'), 2
    if change == 'epoch': after['source_epoch'] = 'b'
    elif change == 'server': after['identity']['server_uuid'] = 'other'
    elif change == 'uptime': after['groups']['status']['rows'][0]['variable_value'] = '1'
    elif change == 'flush': after['groups']['status']['rows'][1]['variable_value'] = '1'
    elif change == 'denied': after['groups']['status']['status'] = 'unavailable'
    elif change == 'incomplete': after['transaction_completed'] = False
    else: elapsed = 0
    assert counter_rates(before, after, elapsed)['status'] == 'unavailable'


def test_counter_decrease_remains_a_gap_and_zero_difference_is_zero():
    reset = counter_rates(counter_sample(), counter_sample(questions='1'), 2)
    assert reset['gaps']['Questions'] == 'counter-reset'
    zero = counter_rates(counter_sample(), counter_sample(), 2)
    assert zero['per_second']['Questions'] == '0'


def test_metadata_interval_preserves_original_time_and_refreshes_after_deadline(monkeypatch):
    monitor = source()
    now = [10.0]
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mysql_family.mysql_monitoring.time.monotonic', lambda: now[0])
    def read(sql, params=None):
        return [dict(IDENTITY)] if sql.startswith('SELECT DATABASE()') else []
    monitor._read = Mock(side_effect=read)
    first = monitor.sample()
    now[0] = 15
    second = monitor.sample()
    assert first['groups']['settings']['observed_at'] == second['groups']['settings']['observed_at']
    assert second['groups']['settings']['observation_age_seconds'] == 5
    settings_queries = lambda: sum(sql.args[0] == monitor.settings_source for sql in monitor._read.call_args_list)
    assert settings_queries() == 1
    now[0] = 71
    assert monitor.sample()['groups']['settings']['observation_age_seconds'] == 0
    assert settings_queries() == 2
    monitor.close()


def test_role_is_activated_before_selecting_database(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mysql_family.provider._create_client', Mock(return_value=client))
    monitor = MySQLMonitor(SimpleNamespace(), {'host': 'db', 'database': 'restricted', 'role': 'metric`role'})
    monitor._open()
    assert client._connect.call_args.args[0]['route']['database'] is None
    client._connect.return_value.cursor.return_value.__enter__.return_value.execute.assert_called_once_with('SET ROLE `metric``role`')
    assert client._connect.return_value.database == 'restricted'
    monitor.close()


def test_native_probe_integer_identity_is_exact_over_json():
    monitor = source()
    monitor._connection = MagicMock()
    cursor = monitor._connection.cursor.return_value.__enter__.return_value
    cursor.description = [('processlist_id',)]
    cursor.fetchmany.return_value = [(9007199254740993,)]
    cursor.fetchone.return_value = None
    assert monitor._read('SELECT PROCESSLIST_ID LIMIT 101') == [{'processlist_id': '9007199254740993'}]
    monitor.close()
