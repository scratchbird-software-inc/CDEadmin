from copy import deepcopy
import json
import pytest
from pgadmin.cdeadmin.workspace.mariadb_server_plan import plan
from pgadmin.cdeadmin.workspace.mariadb_server_apply import MariaDBServerApplications


def model():
    return {'provenance': {'mapping': 'scratchrobin.mariadb.catalog@1', 'endpoint_id': 'endpoint', 'database_target_id': 'server:uuid'},
            'rows': {'server': {'resource_id': 'server', 'kind': 'server', 'native': {'server_uid': 'uuid',
                'catalog_row': {'server_uid': 'uuid', 'version': '12.2.2'},
                'catalog_observations': [{'section': 'accounts', 'available': True}, {'section':'account-lock-state','available':True}]}}}}


def user(name='u@`é'):
    key = 'mariadb-server:' + json.dumps(['uuid', 'accounts', [name, '%']], ensure_ascii=False, separators=(',', ':'))
    return {'resource_id': key, 'kind': 'user', 'name': name + ' / %', 'system': 'false',
            'native': {'section': 'accounts', 'server_uid': 'uuid', 'system_object': False,
                'catalog_row': {'user': name, 'host': '%'}, 'mariadb_change': {'action': 'create', 'draft': {}}}}


def test_exact_account_names_and_missing_selection_never_requests_removal():
    baseline = model()
    desired = deepcopy(baseline)
    row = user()
    desired['rows'][row['resource_id']] = row
    result = plan(baseline, desired, baseline)
    assert result['ready_for_review']
    assert result['operations'][0]['source'] == 'CREATE USER `u@``é`@`%` ACCOUNT LOCK'
    before = deepcopy(desired)
    before['rows'][row['resource_id']]['native'].pop('mariadb_change')
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
        row['native']['mariadb_change']['draft']['password'] = 'never-store'
    desired['rows'][row['resource_id']] = row
    assert not plan(baseline, desired, baseline)['ready_for_review']


def test_server_receipts_survive_restart_keep_prefix_and_never_redispatch(tmp_path):
    baseline = model(); desired = deepcopy(baseline)
    for name in ('a', 'b', 'c'):
        row = user(name); desired['rows'][row['resource_id']] = row
    preview = plan(baseline, desired, baseline)
    app = MariaDBServerApplications(tmp_path / 'server.json')
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
    restarted = MariaDBServerApplications(tmp_path / 'server.json')
    assert restarted.apply(request, 1, 'route', execute)['state'] == 'unknown_outcome'
    assert len(calls) == 2
    with pytest.raises(ValueError):
        restarted.get(receipt['review_id'], 2, 'route')


def test_native_section_revocation_after_review_refuses_before_dispatch(monkeypatch):
    from unittest.mock import Mock
    from pgadmin.cdeadmin.providers.mariadb_server_application import apply_operation
    baseline = model(); desired = deepcopy(baseline); row = user()
    desired['rows'][row['resource_id']] = row
    preview = plan(baseline, desired, baseline)
    preview['endpoint_id'] = 'endpoint'
    revoked = deepcopy(baseline)
    revoked['rows']['server']['native']['catalog_observations'][0]['available'] = False
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mariadb_server_application.capture',
                        lambda _: {'resources': [], 'server_uid': 'uuid', 'generation': 'g'})
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mariadb_server_application.build_export', lambda *_, **__: revoked)
    cursor = Mock()
    cursor.fetchone.side_effect = [('12.2.2', 'uuid'), (1,), (1,)]
    connection = Mock(server_status=0)
    connection.cursor.return_value = cursor
    outcome = apply_operation(connection, {'plan': preview, 'desired': desired}, preview['operations'][0])
    assert outcome['state'] == 'not_dispatched' and 'unavailable' in outcome['rejection_reason']
    assert not any(call.args[0].startswith('CREATE USER') for call in cursor.execute.call_args_list)


def test_mariadb_role_has_no_host_suffix_and_rejects_mysql_identity():
    baseline=model(); desired=deepcopy(baseline); row=user('native_role')
    key='mariadb-server:'+json.dumps(['uuid','accounts',['native_role','']],separators=(',',':'))
    row.update(resource_id=key,kind='role',name='native_role / ')
    row['native']['catalog_row']={'user':'native_role','host':'','is_role':'Y'}
    desired['rows'][key]=row
    result=plan(baseline,desired,baseline)
    assert result['ready_for_review']
    assert result['operations'][0]['source']=='CREATE ROLE `native_role`'
    row['native']['catalog_row']['host']='%'
    assert not plan(baseline,desired,baseline)['ready_for_review']


def test_native_effects_preserve_case_default_and_reset_semantics():
    from pgadmin.cdeadmin.providers.mariadb_server_application import effect
    def check(kind, action, draft, facts=None):
        row={'resource_id':'target','kind':kind,'native':{'mariadb_change':{'draft':draft}}}
        live={'rows':{} if facts is None else {'target':{'native':{'catalog_row':facts}}}}
        return effect(row,{'operation':action},live)
    assert check('system-variable','set_global',{'value_mode':'DEFAULT'}, {'global_value':'151','default_value':'151'})
    assert not check('system-variable','set_global',{'value_mode':'DEFAULT'}, {'global_value':'151','default_value':None})
    assert check('replication-channel','reset',{'delete_connection':True})
    assert not check('replication-channel','reset',{'delete_connection':True},{'connection_name':'still present'})
    assert not check('server-link','alter',{'change_username':True,'username':'Admin'}, {'username':'admin'})
    assert check('role-membership','revoke',{'admin_option_only':True},{'admin_option':'N'})


def test_effective_package_grants_and_grant_only_rows_exclude_authentication():
    from pgadmin.cdeadmin.providers.mariadb_grants import routine_grants
    principals=[{'user':'role','host':'','is_role':'Y','grantee_identity':"'role'@''"}]
    records=list(routine_grants(principals,lambda _: [
        {'grant': 'GRANT USAGE ON *.* TO `role` IDENTIFIED BY PASSWORD \'must-not-escape\''},
        {'grant': 'GRANT EXECUTE, ALTER ROUTINE ON PACKAGE BODY `d`.`p``x` TO `role` WITH GRANT OPTION'},
        {'grant': 'GRANT USAGE ON PROCEDURE `d`.`p` TO `role` WITH GRANT OPTION'}]))
    assert len(records)==3 and records[0]['routine_name']=='p`x'
    assert records[0]['routine_type']=='PACKAGE BODY' and records[0]['grantee_is_role']
    assert records[-1]['privilege_type']=='USAGE'
    assert 'must-not-escape' not in json.dumps(records)
