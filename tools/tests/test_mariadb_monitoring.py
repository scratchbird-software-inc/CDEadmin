"""MariaDB probes must retain native identity, transaction and visibility rules."""
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock

import pytest
from pgadmin.cdeadmin.providers.mysql_family.mariadb_monitoring import MariaDBMonitor
from pgadmin.cdeadmin.providers.mysql_family.mysql_monitoring import counter_rates

IDENTITY = {'database_name': 'demo', 'version': '12.2.2-MariaDB', 'server_uid': 'native-server',
            'collector_id': '42', 'account': 'monitor@%'}


def source():
    monitor = MariaDBMonitor(SimpleNamespace(), {'host': 'db', 'database': 'demo'})
    monitor._connection = SimpleNamespace(server_status=2, autocommit=True)
    monitor._client = Mock()
    monitor._epoch = 'owned-source'
    monitor._read = Mock(side_effect=lambda sql, params=None: [dict(IDENTITY)]
        if sql.startswith('SELECT DATABASE()') else [])
    return monitor


def test_native_probes_do_not_require_mysql_performance_schema_or_identity():
    monitor = source()
    result = monitor.sample()
    assert result['schema'] == 'mariadb-monitoring-sample@1'
    assert result['identity']['server_uid'] == 'native-server'
    assert result['transaction_completed'] and result['transaction_refresh']['status'] == 'completed'
    queries = '\n'.join(call.args[0] for call in monitor._read.call_args_list)
    for forbidden in ('performance_schema', '@@server_uuid', '@@super_read_only'):
        assert forbidden not in queries
    for required in ('information_schema.GLOBAL_STATUS', 'information_schema.PROCESSLIST',
                     'information_schema.SLAVE_STATUS', 'DB=DATABASE()'):
        assert required in queries
    assert result['groups']['status']['scope'] == 'server'
    assert result['groups']['activity']['scope'] == 'database'
    monitor.close()


@pytest.mark.parametrize('change', ['database', 'version', 'transaction', 'autocommit', 'wire'])
def test_wrong_native_identity_or_pending_scope_cannot_heartbeat(change):
    monitor = source()
    if change in {'database', 'version'}:
        identity = {**IDENTITY, 'database_name' if change == 'database' else 'version': 'other'}
        monitor._read = Mock(return_value=[identity])
    elif change == 'transaction': monitor._connection.server_status = 3
    elif change == 'autocommit': monitor._connection.autocommit = False
    else: monitor._read.side_effect = OSError('private detail')
    result = monitor.sample()
    assert not result['transaction_completed'] and result['status'] == 'unavailable'
    assert result['transaction_refresh']['status'] == 'not-completed'
    assert monitor._connection is None
    assert 'private detail' not in str(result)


def test_dedicated_native_role_and_pool_isolation(monkeypatch):
    client = MagicMock()
    create = Mock(return_value=client)
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mysql_family.provider._create_client', create)
    monitor = MariaDBMonitor(SimpleNamespace(), {'host': 'db', 'database': 'demo', 'role': 'metric`role',
        'pool_name': 'interactive', 'pool_size': 1, 'pool_reset_connection': True,
        'pool_validation_interval': 500, 'autocommit': False})
    monitor._open()
    assert create.call_args.args[0].engine_id == 'mariadb'
    route = client._connect.call_args.args[0]['route']
    assert route['database'] is None and route['autocommit'] is True and route['reconnect'] is False
    assert not {'pool_name', 'pool_size', 'pool_reset_connection', 'pool_validation_interval'} & route.keys()
    assert route['connect_timeout'] == route['read_timeout'] == route['write_timeout'] == 5
    client._connect.return_value.cursor.return_value.__enter__.return_value.execute.assert_called_once_with('SET ROLE `metric``role`')
    assert client._connect.return_value.database == 'demo'
    monitor.close()


def test_denied_native_group_is_a_gap_without_error_text():
    class Denied(Exception):
        errno = 1227
        sqlstate = '42000'
    monitor = source()
    original = monitor._read.side_effect
    monitor._read.side_effect = lambda sql, params=None: (_ for _ in ()).throw(Denied('private detail')) \
        if 'SLAVE_STATUS' in sql else original(sql, params)
    result = monitor.sample()
    assert result['transaction_completed']
    assert result['groups']['replication']['status'] == 'unavailable'
    assert result['groups']['replication']['error_code'] == 1227
    assert 'private detail' not in str(result)
    monitor.close()


def test_native_server_uid_breaks_counter_baseline():
    def sample(uid, value):
        return {'transaction_completed': True, 'source_epoch': 'same', 'identity': {'server_uid': uid},
            'groups': {'status': {'status': 'available', 'rows': [
                {'variable_name': key, 'variable_value': value} for key, value in {
                    'Uptime': '100', 'Uptime_since_flush_status': '90', 'Questions': value}.items()]}}}
    before = sample('one', '9007199254740993')
    after = sample('one', '9007199254740998')
    assert counter_rates(before, after, 2, identity_key='server_uid')['per_second']['Questions'] == '2.5'
    after['identity']['server_uid'] = 'two'
    assert counter_rates(before, after, 2, identity_key='server_uid')['status'] == 'unavailable'


def test_uppercase_native_status_labels_keep_original_and_exact_counter_binding():
    monitor = source()
    original = monitor._read.side_effect
    monitor._read.side_effect = lambda sql, params=None: [
        {'variable_name': 'QUESTIONS', 'variable_value': '9007199254740993'}] \
        if 'GLOBAL_STATUS' in sql else original(sql, params)
    result = monitor.sample()
    assert result['groups']['status']['rows'] == [{
        'variable_name': 'Questions', 'native_variable_name': 'QUESTIONS',
        'variable_value': '9007199254740993'}]
    monitor.close()
