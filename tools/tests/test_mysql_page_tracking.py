"""Native page-tracking effects, exact values and acknowledgement boundaries."""
from copy import deepcopy
from unittest.mock import Mock
import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_page_tracking as tracking
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from test_mysql_instance import target, UUID


def draft(operation):
    value = {} if operation in tracking.READS else {'confirmation': 'MySQL'}
    if operation in {'start_page_tracking', 'stop_page_tracking', 'set_page_tracking_backup_id', 'purge_page_tracking'}:
        value['coordinated_backup_window'] = True
    if operation in {'export_tracked_pages', 'count_tracked_pages'}: value.update(start_lsn='0', stop_lsn='18446744073709551615')
    if operation == 'set_page_tracking_backup_id': value.update(value_mode='VALUE', backup_id='182001', prior_index_removal_confirmed=True)
    if operation == 'purge_page_tracking': value.update(purge_lsn='0', tracking_files_not_required=True)
    return value


def observation():
    return {'native_backup_id': '182001', 'native_first_active_start_lsn': '9007199254740993'}


def request(operation):
    compiled = tracking.compile_operation(operation, draft(operation), target())
    compiled['mysql_page_tracking']['review'] = {'execution_identity': {'server_uuid': UUID}, 'before': observation()}
    return {'provider_payload': {'route': {'host': 'owned'}, 'compiled': compiled}}


def test_all_native_inputs_remain_exact_and_export_does_not_change_global_backup_id():
    statement = request('export_tracked_pages')['provider_payload']['compiled']['statements'][0]
    assert statement == {'source': 'SELECT mysqlbackup_page_track_get_changed_pages(%s,%s)', 'parameters': (0, 2**64 - 1)}
    for mode in ('NULL', 'DEFAULT'):
        checked = tracking.compile_operation('set_page_tracking_backup_id', {**draft('set_page_tracking_backup_id'), 'value_mode': mode}, target())
        assert checked['statements'][0]['source'].endswith(' = ' + mode) and not checked['statements'][0]['parameters']


@pytest.mark.parametrize('change', [{'prior_index_removal_confirmed': False}, {'coordinated_backup_window': 'true'}, {'confirmation': 'another'}])
def test_native_backup_id_deletion_requires_exact_explicit_review(change):
    with pytest.raises(RelationalClientError):
        tracking.compile_operation('set_page_tracking_backup_id', {**draft('set_page_tracking_backup_id'), **change}, target())


@pytest.mark.parametrize('value', ['01', '-1', str(2**64), '0; SHUTDOWN', True, 2**53])
def test_lsn_inputs_cannot_be_rounded_or_injected(value):
    with pytest.raises(RelationalClientError):
        tracking.compile_operation('count_tracked_pages', {'start_lsn': value, 'stop_lsn': '0'}, target())


def test_catalog_exposes_mysql_only_actions_and_marks_destructive_native_operations():
    server = next(row for row in MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))['objects'] if row['resource_kind'] == 'server')
    actions = {row['operation_id']: row for row in server['operations']}
    for operation in tracking.OPERATIONS:
        assert MYSQL_ADMINISTRATION.supports('server', operation) and not MARIADB_ADMINISTRATION.supports('server', operation)
        assert actions[operation]['form']['form_id'] == 'mysql.server.' + operation
    assert actions['set_page_tracking_backup_id']['mutation_class'] == actions['purge_page_tracking']['mutation_class'] == 'destructive'


@pytest.mark.parametrize('operation,result,interpretation', [
    ('count_tracked_pages', -3803, 'native-returned-failure'),
    ('export_tracked_pages', 3803, 'native-returned-failure'),
    ('export_tracked_pages', -1, 'native-returned-failure'),
    ('export_tracked_pages', 0, 'native-status-zero'),
    ('purge_page_tracking', 2**63 - 1, 'native-no-purge-boundary-sentinel'),
    ('start_page_tracking', 9007199254740993, 'native-integer-result'),
])
def test_sql_reply_is_separate_from_native_function_status_and_does_not_attest_backup(monkeypatch, operation, result, interpretation):
    client = Mock(); cursor = client._connect.return_value.cursor.return_value; cursor.warnings = []
    cursor.fetchone.return_value = (result,)
    monkeypatch.setattr(tracking, 'environment', lambda _: {'server_uuid': UUID})
    monkeypatch.setattr(tracking, 'observe', lambda _: observation())
    value = tracking.apply(client, request(operation))['page_tracking_observation']
    assert value['native_acknowledged'] and value['native_scalar_result'] == str(result)
    assert value['native_result_interpretation'] == interpretation
    assert not value['export_file_observed'] and not value['incremental_backup_established'] and not value['recoverability_established']
    assert value['native_outcome_failed'] == (interpretation == 'native-returned-failure')
    client._forget_and_close.assert_called_once()


@pytest.mark.parametrize('outcome', ['changed-inputs', 'post-ack-loss', 'missing-reply'])
def test_changed_inputs_and_lost_observations_do_not_replay_global_effects(monkeypatch, outcome):
    client = Mock(); cursor = client._connect.return_value.cursor.return_value; cursor.warnings = []
    monkeypatch.setattr(tracking, 'environment', lambda _: {'server_uuid': UUID})
    calls = 0
    def observe(_):
        nonlocal calls
        calls += 1
        if outcome == 'post-ack-loss' and calls == 2: raise OSError('owned later loss')
        value = observation()
        if outcome == 'changed-inputs': value['native_backup_id'] = 'another'
        return value
    monkeypatch.setattr(tracking, 'observe', observe)
    if outcome == 'missing-reply': cursor.execute.side_effect = OSError('owned reply loss')
    if outcome == 'post-ack-loss':
        value = tracking.apply(client, request('set_page_tracking_backup_id'))['page_tracking_observation']
        assert value['native_acknowledged'] and value['prior_export_removal_possible'] and value['later_observation_error']
    else:
        with pytest.raises(RelationalClientError) as failure: tracking.apply(client, request('set_page_tracking_backup_id'))
        assert failure.value.native_dispatched == (outcome == 'missing-reply') and not failure.value.native_acknowledged
        assert not failure.value.automatic_retry
    assert cursor.execute.call_count == (0 if outcome == 'changed-inputs' else 1)


def test_forged_and_borrowed_actions_never_open_a_native_connection():
    client = Mock(); value = deepcopy(request('start_page_tracking'))
    value['provider_payload']['compiled']['statements'][0]['source'] = 'SHUTDOWN'
    with pytest.raises(RelationalClientError): tracking.apply(client, value)
    with pytest.raises(RelationalClientError): tracking.apply(client, request('start_page_tracking'), object())
    client._connect.assert_not_called()
