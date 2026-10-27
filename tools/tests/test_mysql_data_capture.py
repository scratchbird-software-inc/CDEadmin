"""Exact relation scope, bounded static DDN and independent read-only cleanup."""
import json
from unittest.mock import Mock
import pytest
from mysql.connector.constants import FieldType
from pgadmin.cdeadmin.providers.mysql_family.mysql_data_capture import capture, relation_address


def address(database='demo',kind='table',name='a`table'):
    root='mysql:'+json.dumps([database,'database',None,database],separators=(',',':'))
    return 'mysql:'+json.dumps([database,kind,root,name],separators=(',',':'))


def connection(rows, *, engine='InnoDB'):
    control=Mock()
    control.fetchone.side_effect=[('demo','9.7.0','server-identity'),('BASE TABLE',engine),None,('',)]
    control.fetchall.return_value=[('value','bigint unsigned','NO','','',None,None,None)]
    stream=Mock()
    stream.description=[('value',FieldType.LONGLONG,None,None,None,None,False,32,63)]
    stream.fetchmany.side_effect=[[(value,) for value in rows],[]]
    native=Mock(in_transaction=False,python_charset='utf8')
    native.cursor.side_effect=[control,stream]
    return native,control,stream


def test_relation_identity_rejects_foreign_targets_system_databases_and_noncanonical_addresses():
    assert relation_address('demo',address())==('table','a`table')
    for database,identity in [('other',address()),('mysql',address('mysql')),
            ('demo',address(kind='procedure')),('demo',address()+' '),('demo','mysql:["demo"]')]:
        with pytest.raises(ValueError):relation_address(database,identity)


def test_sample_preserves_native_uint64_and_explicit_coverage_and_finishes_its_transaction():
    native,control,stream=connection([b'18446744073709551615',b'2'])
    result=capture(native,'demo',address(),endpoint_id='endpoint',target_id='target',row_limit=1)
    assert result['acquisition']['rows']==1 and result['acquisition']['more_rows_observed']
    assert result['acquisition']['consistent_innodb_table_snapshot']
    assert '18446744073709551615' in result['snapshot']['files']['result-1.ddn']
    assert stream.execute.call_args.args==('SELECT `value` FROM `demo`.`a``table` LIMIT %s',(2,))
    assert any(call.args[0]=='START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY' for call in control.execute.call_args_list)
    native.rollback.assert_called_once();stream.close.assert_called_once();control.close.assert_called_once()


def test_full_overflow_permission_and_cleanup_failures_never_return_partial_data():
    native,control,stream=connection([b'1',b'2'])
    with pytest.raises(ValueError,match='Full data capture exceeds'):
        capture(native,'demo',address(),endpoint_id='e',target_id='t',mode='full',row_limit=1)
    native.rollback.assert_called_once()
    native,control,stream=connection([b'1'])
    stream.execute.side_effect=RuntimeError('Permission refused')
    with pytest.raises(RuntimeError,match='Permission refused'):
        capture(native,'demo',address(),endpoint_id='e',target_id='t')
    native.rollback.assert_called_once()
    native,control,stream=connection([b'1'])
    native.rollback.side_effect=RuntimeError('Connection lost')
    with pytest.raises(RuntimeError,match='Connection lost'):
        capture(native,'demo',address(),endpoint_id='e',target_id='t')


def test_nontransactional_storage_is_observational_and_busy_connections_are_refused():
    native,control,stream=connection([b'1'],engine='MyISAM')
    result=capture(native,'demo',address(),endpoint_id='e',target_id='t')
    assert not result['acquisition']['consistent_innodb_table_snapshot'] and result['warnings']
    native,control,stream=connection([]);native.in_transaction=True
    with pytest.raises(ValueError,match='idle'):capture(native,'demo',address(),endpoint_id='e',target_id='t')
    native.rollback.assert_not_called();native.cursor.assert_not_called()
