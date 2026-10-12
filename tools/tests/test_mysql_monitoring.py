"""Dedicated MySQL sampling must preserve scope, denial and failure evidence."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mysql.connector.errors import DatabaseError, InterfaceError
from pgadmin.cdeadmin.providers.mysql_family.mysql_monitoring import MySQLMonitor

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
    assert result['groups']['activity'] == {'status': 'unavailable', 'scope': 'database',
                                           'error_code': 1142, 'sqlstate': '42000'}
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
