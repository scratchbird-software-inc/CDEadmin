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
    outcome = apply_operation(connection, {'plan': preview, 'baseline': baseline, 'desired': desired}, preview['operations'][0])
    assert outcome['state'] == 'not_dispatched' and 'unavailable' in outcome['rejection_reason']
    assert not any(call.args[0].startswith('CREATE USER') for call in cursor.execute.call_args_list)


def foreign(name='remote : . ` é'):
    key = 'mysql-server:' + json.dumps(['uuid', 'foreign-servers', [name]], ensure_ascii=False, separators=(',', ':'))
    return {'resource_id': key, 'kind': 'server-link', 'name': name, 'system': 'false',
        'native': {'section': 'foreign-servers', 'server_uuid': 'uuid', 'system_object': False,
            'catalog_row': {'server_name': name, 'wrapper': 'mysql'},
            'mysql_change': {'action': 'create', 'draft': {'name': name, 'wrapper': 'mysql',
                'include_host': True, 'host': "host ' \\", 'include_port': True, 'port': '2147483647'}}}}


def test_foreign_server_ddn_uses_bound_native_attributes_and_exact_address():
    baseline = model();baseline['rows']['server']['native']['catalog_observations'].append({'section': 'foreign-servers', 'available': True})
    desired = deepcopy(baseline);row = foreign();desired['rows'][row['resource_id']] = row
    result = plan(baseline, desired, baseline)
    assert result['ready_for_review'] and not result['blockers']
    operation = result['operations'][0]
    assert operation['source'] == 'CREATE SERVER `remote : . `` é` FOREIGN DATA WRAPPER %s OPTIONS (HOST %s, PORT 2147483647)'
    assert operation['parameters'] == ['mysql', "host ' \\"]
    assert plan(desired, baseline, desired)['operations'] == []


@pytest.mark.parametrize('change', ['password', 'identity', 'confirmation', 'operation'])
def test_foreign_server_ddn_refuses_credentials_redirection_and_invalid_intent(change):
    baseline = model();baseline['rows']['server']['native']['catalog_observations'].append({'section': 'foreign-servers', 'available': True})
    desired = deepcopy(baseline);row = foreign();desired['rows'][row['resource_id']] = row
    if change == 'password':
        row['native']['mysql_change']['draft'].update(include_password=True, password='never store')
    elif change == 'identity':
        row['native']['mysql_change']['draft']['name'] = 'another'
    elif change == 'confirmation':
        row['native']['mysql_change'] = {'action': 'drop', 'draft': {}, 'confirmation': 'another'}
    else:
        row['native']['mysql_change']['action'] = 'rename'
    result = plan(baseline, desired, baseline)
    assert not result['ready_for_review'] and result['blockers']


def test_foreign_server_postconditions_check_attributes_and_preserved_fields():
    from pgadmin.cdeadmin.providers.mysql_server_application import effect
    row = foreign('remote');row['native']['catalog_row'].update(host='old', db='db', username='user', port=3306, socket='', owner='owner')
    row['native']['mysql_change'] = {'action': 'alter', 'draft': {'include_host': True, 'host': 'new'}}
    key = row['resource_id'];live = {'rows': {key: deepcopy(row)}}
    operation = {'operation': 'alter'}
    assert not effect(row, operation, live)
    live['rows'][key]['native']['catalog_row']['host'] = 'new'
    assert effect(row, operation, live)
    live['rows'][key]['native']['catalog_row']['owner'] = 'changed unexpectedly'
    assert not effect(row, operation, live)


def spatial(srid=4294967000):
    key='mysql-server:'+json.dumps(['uuid','spatial-reference-systems',[srid]],separators=(',',':'))
    return {'resource_id':key,'kind':'spatial-reference-system','name':str(srid),'system':'false',
        'native':{'section':'spatial-reference-systems','server_uuid':'uuid','system_object':False,
            'catalog_row':{'srs_id':srid},'mysql_change':{'action':'create',
                'draft':{'srs_id':str(srid),'name':"DDN ' é",'definition':'native WKT'}}}}


def test_spatial_ddn_binds_native_fields_and_requires_observed_srid_scope():
    from pgadmin.cdeadmin.workspace.mysql_server_plan import spatial_selection
    baseline=model();desired=deepcopy(baseline);row=spatial();desired['rows'][row['resource_id']]=row
    assert spatial_selection(baseline,desired)==[4294967000]
    baseline['rows']['server']['native']['catalog_observations'].append({'section':'spatial-reference-systems','available':True,'selected_ids':[4294967000]})
    result=plan(baseline,desired,baseline);assert result['ready_for_review']
    assert result['operations'][0]['source']=='CREATE SPATIAL REFERENCE SYSTEM 4294967000 NAME %s DEFINITION %s'
    assert result['operations'][0]['parameters']==["DDN ' é",'native WKT']
    baseline['rows']['server']['native']['catalog_observations'][-1]['selected_ids']=[4326]
    assert not plan(baseline,desired,baseline)['ready_for_review']


@pytest.mark.parametrize('change',['draft_id','resource_id','label','range','secret'])
def test_spatial_ddn_refuses_identity_changes_and_credentials(change):
    baseline=model();baseline['rows']['server']['native']['catalog_observations'].append({'section':'spatial-reference-systems','available':True,'selected_ids':[4294967000]})
    desired=deepcopy(baseline);row=spatial();desired['rows'][row['resource_id']]=row
    if change=='draft_id':row['native']['mysql_change']['draft']['srs_id']='4326'
    elif change=='resource_id':row['resource_id']+='borrowed'
    elif change=='label':row['name']='another'
    elif change=='range':row['native']['catalog_row']['srs_id']=4294967296
    else:row['native']['mysql_change']['draft']['password']='never store'
    assert not plan(baseline,desired,baseline)['ready_for_review']


def test_spatial_postconditions_compare_all_six_native_fields():
    from pgadmin.cdeadmin.providers.mysql_server_application import effect
    row=spatial();draft=row['native']['mysql_change']['draft'];key=row['resource_id']
    facts={'srs_id':4294967000,'srs_name':draft['name'],'definition':draft['definition'],
        'organization':None,'organization_coordsys_id':None,'description':None}
    live={'rows':{key:{'native':{'catalog_row':facts}}}}
    assert effect(row,{'operation':'create'},live)
    facts['description']='unexpected external change'
    assert not effect(row,{'operation':'create'},live)


def test_persistent_reset_distinguishes_redaction_disappearance_and_denied_catalog():
    from pgadmin.cdeadmin.providers.mysql_server_application import effect
    row={'resource_id':'setting','kind':'system-variable','native':{
        'catalog_row':{'variable_name':'component.option'},
        'mysql_change':{'action':'reset_persist','draft':{}}}}
    live={'rows':{'setting':{'native':{'catalog_row':{
        'persisted_value':None,'persisted_present':1,'persisted_value_redacted':1}}}}}
    assert not effect(row,{'operation':'reset_persist'},live)
    live['rows']['setting']['native']['catalog_row']['persisted_present']=0
    assert effect(row,{'operation':'reset_persist'},live)
    del live['rows']['setting']
    assert not effect(row,{'operation':'reset_persist'},live)
    live['rows']['root']={'kind':'server','native':{'catalog_observations':[
        {'section':'system-variables','available':False}]}}
    assert not effect(row,{'operation':'reset_persist'},live)
    live['rows']['root']['native']['catalog_observations'][0]['available']=True
    assert effect(row,{'operation':'reset_persist'},live)


def test_hidden_persisted_value_cannot_prove_a_set_postcondition():
    from pgadmin.cdeadmin.providers.mysql_server_application import effect
    row={'resource_id':'setting','kind':'system-variable','native':{
        'catalog_row':{},'mysql_change':{'draft':{'value_mode':'DEFAULT'}}}}
    live={'rows':{'setting':{'native':{'catalog_row':{'persisted_value_redacted':1}}}}}
    assert not effect(row,{'operation':'set_persist_only'},live)
