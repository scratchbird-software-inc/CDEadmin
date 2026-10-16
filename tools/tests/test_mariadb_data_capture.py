"""Exact relation scope, bounded static DDN and independent read-only cleanup."""
import json
from unittest.mock import Mock
import pytest
from mariadb.constants import FIELD_TYPE as FieldType
from pgadmin.cdeadmin.providers.mysql_family.mariadb_data_capture import capture, relation_address


def address(database='demo',kind='table',name='a`table'):
    root='mariadb:'+json.dumps([database,'database',None,database],separators=(',',':'))
    return 'mariadb:'+json.dumps([database,kind,root,name],separators=(',',':'))


def connection(rows, *, engine='InnoDB'):
    control=Mock()
    control.fetchone.side_effect=[('demo','12.2.2-MariaDB','server-identity'),('BASE TABLE',engine),None,('',)]
    control.fetchall.return_value=[('value','bigint unsigned','NO','','',None,None)]
    stream=Mock()
    stream.metadata={'flags': [32], 'charset': [63]}
    stream.cdeadmin_exact_temporals = False
    stream.description=[('value',FieldType.LONGLONG,None,None,None,None,False,32,63)]
    stream.fetchmany.side_effect=[[(value,) for value in rows],[]]
    native=Mock(server_status=0)
    native.cursor.side_effect=[control,stream]
    return native,control,stream


def test_relation_identity_rejects_foreign_targets_system_databases_and_noncanonical_addresses():
    assert relation_address('demo',address())==('table','a`table')
    for database,identity in [('other',address()),('mysql',address('mysql')),
            ('demo',address(kind='procedure')),('demo',address()+' '),('demo','mariadb:["demo"]')]:
        with pytest.raises(ValueError):relation_address(database,identity)


def test_sample_preserves_native_uint64_and_explicit_coverage_and_finishes_its_transaction():
    native,control,stream=connection([18446744073709551615,2])
    result=capture(native,'demo',address(),endpoint_id='endpoint',target_id='target',expected_server_uid='server-identity',row_limit=1)
    assert result['acquisition']['rows']==1 and result['acquisition']['more_rows_observed']
    assert result['acquisition']['consistent_innodb_table_snapshot']
    assert '18446744073709551615' in result['snapshot']['files']['result-1.ddn']
    assert stream.execute.call_args.args==('SELECT `value` FROM `demo`.`a``table` LIMIT ?',(2,))
    assert result['acquisition']['native_columns'][0]['column_type']=='bigint unsigned'
    assert any(call.args[0]=='START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY' for call in control.execute.call_args_list)
    native.rollback.assert_called_once();stream.close.assert_called_once();control.close.assert_called_once()


def test_full_overflow_permission_and_cleanup_failures_never_return_partial_data():
    native,control,stream=connection([1,2])
    with pytest.raises(ValueError,match='Full data capture exceeds'):
        capture(native,'demo',address(),endpoint_id='e',target_id='t',expected_server_uid='server-identity',mode='full',row_limit=1)
    native.rollback.assert_called_once()
    native,control,stream=connection([1])
    stream.execute.side_effect=RuntimeError('Permission refused')
    with pytest.raises(RuntimeError,match='Permission refused'):
        capture(native,'demo',address(),endpoint_id='e',target_id='t',expected_server_uid='server-identity')
    native.rollback.assert_called_once()
    native,control,stream=connection([1])
    native.rollback.side_effect=RuntimeError('Connection lost')
    with pytest.raises(RuntimeError,match='Connection lost'):
        capture(native,'demo',address(),endpoint_id='e',target_id='t',expected_server_uid='server-identity')


def test_nontransactional_storage_is_observational_and_busy_connections_are_refused():
    native,control,stream=connection([1],engine='MyISAM')
    result=capture(native,'demo',address(),endpoint_id='e',target_id='t',expected_server_uid='server-identity')
    assert not result['acquisition']['consistent_innodb_table_snapshot'] and result['warnings']
    native,control,stream=connection([]);native.server_status=1
    with pytest.raises(ValueError,match='idle'):capture(native,'demo',address(),endpoint_id='e',target_id='t',expected_server_uid='server-identity')
    native.rollback.assert_not_called();native.cursor.assert_not_called()


def test_captured_native_server_uid_must_match_before_any_relation_data_read():
    native,control,stream=connection([1])
    with pytest.raises(ValueError,match='identity changed'):
        capture(native,'demo',address(),endpoint_id='e',target_id='t',expected_server_uid='another-server')
    stream.execute.assert_not_called()
    native.rollback.assert_not_called()
