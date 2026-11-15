"""Native engine diagnostics: admission, private access and bounded results."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_engine_diagnostics as native
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from test_mysql_instance import target, UUID


def draft():
    return {'engine': 'InnoDB', 'private_data_confirmed': True, 'confirmation': 'MySQL'}


@pytest.mark.parametrize('operation', native.OPERATIONS)
def test_native_tasks_are_surfaced_only_for_mysql(operation):
    catalog = MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    task = next(row for item in catalog['objects'] if item['resource_kind'] == 'server'
                for row in item['operations'] if row['operation_id'] == operation)
    assert task['confirmation_required'] and task['target_required']
    assert {field['field_id'] for field in task['form']['fields']} == set(draft()) | {'engine_scope'}
    assert MYSQL_ADMINISTRATION.supports('server', operation)
    assert not MARIADB_ADMINISTRATION.supports('server', operation)
    result = MYSQL_ADMINISTRATION.validate({'resource_kind': 'server', 'operation_id': operation,
                                           'draft': draft(), 'target_resource': target()})
    assert not result['errors']


@pytest.mark.parametrize('change', [{'private_data_confirmed': False}, {'private_data_confirmed': 'true'},
    {'confirmation': 'other'}, {'engine': ''}, {'engine': None}, {'engine': 'a'*65},
    {'engine': 'a\x00b'}, {'sql': 'SHOW STATUS'}])
def test_private_scope_and_exact_fields_are_required(change):
    with pytest.raises(RelationalClientError):
        native.compile_operation('show_engine_status', {**draft(), **change}, target())


def test_native_engine_names_are_quoted_and_bound_without_sql_injection():
    name = "odd`engine; SELECT 'private' --雪"
    result = native.compile_operation('show_engine_status', {**draft(), 'engine': name}, target())
    assert result['statements'][0]['source'] == "SHOW ENGINE `odd``engine; SELECT 'private' --雪` STATUS"
    cursor = Mock(); cursor.fetchmany.return_value = [(name, 'YES')]
    assert native.engine_state(cursor, name)['engine'] == name
    assert cursor.execute.call_args.args[1] == (name,)


@pytest.mark.parametrize('rows', [[], [('InnoDB', 'DISABLED')], [('InnoDB', 'NO')],
                                [('InnoDB', 'YES'), ('InnoDB', 'DEFAULT')]])
def test_missing_disabled_and_ambiguous_engines_are_refused(rows):
    cursor = Mock(); cursor.fetchmany.return_value = rows
    with pytest.raises(RelationalClientError): native.engine_state(cursor, 'InnoDB')


def result_cursor(rows):
    return SimpleNamespace(description=[('Type',), ('Name',), ('Status',)],
                           fetchone=Mock(side_effect=[*rows, None]))


def test_native_no_rows_does_not_claim_implemented_engine_handler():
    result = native.bounded_result(result_cursor([]))
    assert result['complete'] and result['interpretation'] == 'native-no-rows-returned'


def test_row_and_utf8_byte_limits_are_explicit_not_complete():
    result = native.bounded_result(result_cursor([('InnoDB', '', 'row')]*(native.MAX_ROWS+1)))
    assert len(result['rows']) == native.MAX_ROWS and result['truncated'] and not result['complete']
    result = native.bounded_result(result_cursor([('InnoDB', '', '雪'*native.MAX_BYTES)]))
    assert not result['rows'] and result['truncated'] and not result['complete']
    assert result['interpretation'] == 'bounded-native-partial-output'


def planned():
    compiled = native.compile_operation('show_engine_status', draft(), target())
    compiled['mysql_engine_diagnostics']['review'] = {
        'execution_identity': {'server_uuid': UUID}, 'engine': {'engine': 'InnoDB', 'support': 'DEFAULT'}}
    return {'provider_payload': {'compiled': compiled, 'route': {'host': 'owned', 'pool_name': 'interactive', 'pool_size': 3}}}


@pytest.mark.parametrize('changed', ['principal', 'engine'])
def test_changed_native_identity_refuses_before_show_and_closes_owned_connection(monkeypatch, changed):
    request = planned(); cursor = Mock(); handle = SimpleNamespace(cursor=lambda: cursor, close=Mock())
    client = Mock(); client._connect.return_value = handle
    monkeypatch.setattr(native, 'environment', lambda c: {'server_uuid': UUID, **({'principal': 'changed'} if changed == 'principal' else {})})
    monkeypatch.setattr(native, 'engine_state', lambda c, n, scope='ENGINE': {'engine': 'InnoDB', 'support': 'YES' if changed == 'engine' else 'DEFAULT'})
    with pytest.raises(RelationalClientError) as failure: native.apply(client, request)
    assert not failure.value.native_dispatched and not failure.value.automatic_retry
    cursor.execute.assert_not_called(); client._forget_connection.assert_called_once_with(handle)
    assert 'pool_name' not in client._connect.call_args.args[0]['route']
    assert 'pool_size' not in client._connect.call_args.args[0]['route']


def test_native_denial_keeps_status_without_leaking_source(monkeypatch):
    from mysql.connector.errors import DatabaseError
    cursor = Mock(); cursor.execute.side_effect = DatabaseError('private SQL', errno=1227, sqlstate='42000')
    handle = SimpleNamespace(cursor=lambda: cursor, close=Mock()); client = Mock(); client._connect.return_value = handle
    monkeypatch.setattr(native, 'environment', lambda c: {'server_uuid': UUID})
    monkeypatch.setattr(native, 'engine_state', lambda c, n, scope='ENGINE': {'engine': 'InnoDB', 'support': 'DEFAULT'})
    with pytest.raises(RelationalClientError) as caught: native.apply(client, planned())
    assert caught.value.errno == 1227 and caught.value.native_dispatched
    assert not caught.value.native_acknowledged and 'private SQL' not in str(caught.value)
    client._forget_connection.assert_called_once_with(handle)


def test_truncated_output_does_not_claim_native_completion(monkeypatch):
    cursor = result_cursor([('InnoDB', '', 'x'*native.MAX_BYTES)])
    cursor.execute = Mock()
    handle = SimpleNamespace(cursor=lambda: cursor, close=Mock()); client = Mock(); client._connect.return_value = handle
    monkeypatch.setattr(native, 'environment', lambda c: {'server_uuid': UUID})
    monkeypatch.setattr(native, 'engine_state', lambda c, n, scope='ENGINE': {'engine': 'InnoDB', 'support': 'DEFAULT'})
    result = native.apply(client, planned())['engine_diagnostic']
    assert result['native_dispatched'] and not result['native_acknowledged']
    assert result['native_completion'] == 'unconfirmed-output-truncated'
    client._forget_connection.assert_called_once_with(handle)


def test_interactive_connection_and_tampered_review_are_refused():
    with pytest.raises(RelationalClientError): native.apply(Mock(), planned(), connection=object())
    request = planned(); request['provider_payload']['compiled']['statements'][0]['source'] = 'SHUTDOWN'
    client = Mock()
    with pytest.raises(RelationalClientError): native.apply(client, request)
    client._connect.assert_not_called()


def test_cleanup_failure_is_separate_from_native_acknowledgement(monkeypatch):
    cursor = result_cursor([('InnoDB', '', 'native status')]); cursor.execute = Mock()
    handle = SimpleNamespace(cursor=lambda: cursor, close=Mock(side_effect=OSError('private path')))
    client = Mock(); client._connect.return_value = handle
    monkeypatch.setattr(native, 'environment', lambda c: {'server_uuid': UUID})
    monkeypatch.setattr(native, 'engine_state', lambda c, n, scope='ENGINE': {'engine': 'InnoDB', 'support': 'DEFAULT'})
    result = native.apply(client, planned())
    assert result['engine_diagnostic']['native_acknowledged']
    assert not result['connection_release']['connection_released']
    client._forget_connection.assert_not_called()
    assert 'private path' not in str(result)


@pytest.mark.parametrize('operation', native.OPERATIONS)
def test_all_engine_scope_is_native_sql_not_application_fanout(operation):
    selected = {'engine_scope': 'ALL', 'private_data_confirmed': True, 'confirmation': 'MySQL'}
    result = native.compile_operation(operation, selected, target())
    assert result['statements'][0]['source'] == 'SHOW ENGINE ALL ' + operation.removeprefix('show_engine_').upper()
    assert len(result['statements']) == 1
    with pytest.raises(RelationalClientError):
        native.compile_operation(operation, {**selected, 'engine': 'InnoDB'}, target())


def test_all_engine_inventory_is_complete_bounded_and_includes_disabled_states():
    cursor = Mock(); cursor.fetchmany.return_value = [('InnoDB','DEFAULT'),('FEDERATED','NO')]
    assert native.engine_state(cursor, None, 'ALL')['engines'] == [['InnoDB','DEFAULT'],['FEDERATED','NO']]
    for rows in [[], [('x','YES')]*129, [('x','unexpected')]]:
        cursor.fetchmany.return_value = rows
        with pytest.raises(RelationalClientError): native.engine_state(cursor,None,'ALL')


def test_all_output_has_separate_limits_and_explicit_truncation():
    result = native.bounded_result(result_cursor([('InnoDB','','row')]*(native.MAX_ROWS+1)),True)
    assert result['complete'] and len(result['rows']) == native.MAX_ROWS+1
    result = native.bounded_result(result_cursor([('InnoDB','','row')]*(native.ALL_MAX_ROWS+1)),True)
    assert result['truncated'] and not result['complete'] and result['row_limit'] == native.ALL_MAX_ROWS
