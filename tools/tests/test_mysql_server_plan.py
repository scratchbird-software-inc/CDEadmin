from copy import deepcopy
import json
import pytest
from pgadmin.cdeadmin.workspace.mysql_server_plan import plan
from pgadmin.cdeadmin.workspace.mysql_server_apply import MySQLServerApplications


def model():
    return {'provenance': {'mapping': 'scratchrobin.mysql.catalog@1', 'endpoint_id': 'endpoint', 'database_target_id': 'server:uuid'},
            'rows': {'server': {'resource_id': 'server', 'kind': 'server', 'native': {'server_uuid': 'uuid',
                'catalog_row': {'server_uuid': 'uuid', 'version': '9.7.0'},
                'catalog_observations': [{'section': 'accounts', 'available': True}]}}}}


def user(name='u@`é'):
    key = 'mysql-server:' + json.dumps(['uuid', 'accounts', [name, '%']], ensure_ascii=False, separators=(',', ':'))
    return {'resource_id': key, 'kind': 'user', 'name': name + ' / %', 'system': 'false',
            'native': {'section': 'accounts', 'server_uuid': 'uuid', 'system_object': False,
                'catalog_row': {'user': name, 'host': '%'}, 'mysql_change': {'action': 'create', 'draft': {}}}}


def test_exact_account_names_and_missing_selection_never_requests_removal():
    baseline = model()
    desired = deepcopy(baseline)
    row = user()
    desired['rows'][row['resource_id']] = row
    result = plan(baseline, desired, baseline)
    assert result['ready_for_review']
    assert result['operations'][0]['source'] == 'CREATE USER `u@``é`@`%` ACCOUNT LOCK'
    before = deepcopy(desired)
    before['rows'][row['resource_id']]['native'].pop('mysql_change')
    assert plan(before, baseline, before)['operations'] == []
    assert plan(before, baseline, before)['ignored_missing_selections'] == [row['resource_id']]


@pytest.mark.parametrize('change', ['identity', 'permission', 'secret'])
def test_imported_server_identity_denied_sections_and_credentials_refuse_planning(change):
    baseline = model(); desired = deepcopy(baseline); row = user()
    if change == 'identity':
        row['resource_id'] += 'borrowed'
    elif change == 'permission':
        baseline['rows']['server']['native']['catalog_observations'][0]['available'] = False
    else:
        row['native']['mysql_change']['draft']['password'] = 'never-store'
    desired['rows'][row['resource_id']] = row
    assert not plan(baseline, desired, baseline)['ready_for_review']


def test_server_receipts_survive_restart_keep_prefix_and_never_redispatch(tmp_path):
    baseline = model(); desired = deepcopy(baseline)
    for name in ('a', 'b', 'c'):
        row = user(name); desired['rows'][row['resource_id']] = row
    preview = plan(baseline, desired, baseline)
    app = MySQLServerApplications(tmp_path / 'server.json')
    receipt = app.review(preview, baseline, desired, 1, 'route')
    calls = []
    def execute(record, operation):
        persisted = app.get(record['review_id'], 1, 'route')
        assert persisted['statement_outcomes'][len(calls)]['state'] == 'unknown_outcome'
        calls.append(operation['resource_id'])
        return {'state': 'acknowledged', 'rediscovery_verified': True} if len(calls) == 1 else {'state': 'unknown_outcome'}
    request = {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True}
    result = app.apply(request, 1, 'route', execute)
    assert result['state'] == 'unknown_outcome' and len(calls) == 2
    assert result['statement_outcomes'][2]['state'] == 'not_dispatched'
    restarted = MySQLServerApplications(tmp_path / 'server.json')
    assert restarted.apply(request, 1, 'route', execute)['state'] == 'unknown_outcome'
    assert len(calls) == 2
    with pytest.raises(ValueError):
        restarted.get(receipt['review_id'], 2, 'route')


def test_native_section_revocation_after_review_refuses_before_dispatch(monkeypatch):
    from unittest.mock import Mock
    from pgadmin.cdeadmin.providers.mysql_server_application import apply_operation
    baseline = model(); desired = deepcopy(baseline); row = user()
    desired['rows'][row['resource_id']] = row
    preview = plan(baseline, desired, baseline)
    preview['endpoint_id'] = 'endpoint'
    revoked = deepcopy(baseline)
    revoked['rows']['server']['native']['catalog_observations'][0]['available'] = False
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mysql_server_application.capture',
                        lambda _: {'resources': [], 'server_uuid': 'uuid', 'generation': 'g'})
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mysql_server_application.build_export', lambda *_, **__: revoked)
    cursor = Mock()
    cursor.fetchone.side_effect = [('9.7.0', 'uuid'), (1,), (1,)]
    connection = Mock(in_transaction=False)
    connection.cursor.return_value = cursor
    outcome = apply_operation(connection, {'plan': preview, 'desired': desired}, preview['operations'][0])
    assert outcome['state'] == 'not_dispatched' and 'unavailable' in outcome['rejection_reason']
    assert not any(call.args[0].startswith('CREATE USER') for call in cursor.execute.call_args_list)
