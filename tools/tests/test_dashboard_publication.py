"""Publication uses real DDN validation and versioned asset storage."""
import copy
import pytest
from tools.tests.test_dashboard_definitions import setup, payload
from pgadmin.cdeadmin.workspace.assets import ProjectAssetError, ProjectAssetConflict
from pgadmin.cdeadmin.workspace.dashboard_validation import validate_dashboard

from pgadmin.cdeadmin.workspace import ddn_source as ddn
SOURCE=ddn.header('scratchrobin.firebird.monitoring')+ddn.declaration('source','metric_feed','host',{'channel':'scratchrobin.firebird.monitoring.observations','update':'keyed'})+ddn.declaration('data','observations',None,{'columns':[{'id':key,'type':'text'} for key in ['id','panel','measure','value','unit','rate']], 'rows':[['server_0','server','Version','should-not-persist','version','']], 'source':ddn.ref('metric_feed'),'key':'id'})+ddn.declaration('view','dashboard','table.records@1',{'projection':{'options':{'records':[ddn.ref('observations')],'columns':[{'id':'value','label':'Version'}]}}})


def source():
    return {'format': 'ddn-source-workspace@1', 'entry': 'dashboard.ddn',
            'view': 'dashboard', 'files': {'dashboard.ddn': SOURCE}}


def test_validation_redacts_values_and_rejects_unknown_or_wrong_scope_bindings():
    clean = validate_dashboard(source(), 'server')
    assert 'should-not-persist' not in clean['files']['dashboard.ddn']
    assert 'Unavailable' in clean['files']['dashboard.ddn']
    for scope, text in [('database', SOURCE), ('server', SOURCE.replace('server_0', 'query_0')),
                        ('server', SOURCE.replace('id "observations"', 'id "absent"', 1))]:
        bad = source()
        bad['files']['dashboard.ddn'] = text
        with pytest.raises(ProjectAssetError):
            validate_dashboard(bad, scope)
    bad = source()
    bad['view'] = 'absent'
    with pytest.raises(ProjectAssetError):
        validate_dashboard(bad, 'server')


def test_publish_keeps_draft_and_publication_independent_and_fences_stale_versions():
    definitions, assets = setup()
    request = payload(definitions.read(1, 7)['assetRef'])
    request['snapshot'] = source()
    saved = definitions.save(1, 7, None, request)
    assert definitions.published(1, 7)['state'] == 'standard'
    one = definitions.publish(1, 7, None, {'source_version': 1, 'expected_version': 0})
    assert one['version'] == 1
    assert definitions._publication(1, saved['assetRef'])['assetRef']['path'] != saved['assetRef']['path']
    assert definitions.published(1, 7) == one
    request['assetRef'] = saved['assetRef']
    request['snapshot']['files']['dashboard.ddn'] = SOURCE.replace('"Version"', '"New title"')
    definitions.save(1, 7, None, request)
    assert definitions.published(1, 7) == one
    with pytest.raises(ProjectAssetConflict):
        definitions.publish(1, 7, None, {'source_version': 2, 'expected_version': 0})
    two = definitions.publish(1, 7, None, {'source_version': 2, 'expected_version': 1})
    assert two['version'] == 2 and two['source_version'] == 2
    assert 'New title' in two['snapshot']['files']['dashboard.ddn']
    # A generic asset edit cannot bypass validation on the live-definition route.
    pub = definitions._publication(1, saved['assetRef'])
    malicious = copy.deepcopy(pub['content'])
    malicious['files']['dashboard.ddn'] = 'not DDN'
    assets.save_asset(1, (), pub['assetRef']['projectId'], pub['assetRef']['assetId'],
                     {'schema': 'cdeadmin.ddn-asset.v1', 'assetRef': pub['assetRef'], 'snapshot': malicious})
    with pytest.raises(ProjectAssetError):
        definitions.published(1, 7)


def test_postgresql_publications_have_engine_isolated_assets_and_native_bindings():
    from pgadmin.cdeadmin.workspace.dashboard_definitions import DashboardDefinitions
    firebird, assets = setup()
    def authorize(owner, sid, target):
        return {**firebird.authorize(owner, sid, target), 'engine': 'postgresql'}
    postgres = DashboardDefinitions(assets, authorize,
        lambda snapshot, scope: validate_dashboard(snapshot, scope, engine='postgresql'))
    initial = postgres.read(1, 7)
    assert initial['assetRef']['projectId'] == 'postgresql-dashboard-drafts-1'
    request = payload(initial['assetRef'])
    request['snapshot'] = source()
    request['snapshot']['files']['dashboard.ddn'] = SOURCE.replace('server_0', 'status_0').replace('scratchrobin.firebird.monitoring', 'scratchrobin.postgresql.monitoring')
    postgres.save(1, 7, None, request)
    published = postgres.publish(1, 7, None, {'source_version': 1, 'expected_version': 0})
    assert published['scope']['engine'] == 'postgresql'
    assert 'should-not-persist' not in published['snapshot']['files']['dashboard.ddn']
    assert firebird.published(1, 7)['state'] == 'standard'
    with pytest.raises(ProjectAssetError):
        postgres.save(1, 7, None, payload(firebird.read(1, 7)['assetRef']))


def test_mysql_publications_use_native_scope_and_isolated_versioned_assets():
    from pgadmin.cdeadmin.workspace.dashboard_definitions import DashboardDefinitions
    firebird, assets = setup()
    def authorize(owner, sid, target):
        return {**firebird.authorize(owner, sid, target), 'engine': 'mysql'}
    mysql = DashboardDefinitions(assets, authorize,
        lambda snapshot, scope: validate_dashboard(snapshot, scope, engine='mysql'))
    reference = mysql.read(1, 7)['assetRef']
    assert reference['projectId'] == 'mysql-dashboard-drafts-1'
    assert reference['displayName'] == 'MySQL server dashboard draft'
    request = payload(reference)
    request['snapshot'] = source()
    request['snapshot']['files']['dashboard.ddn'] = SOURCE.replace('server_0', 'availability_0').replace(
        'scratchrobin.firebird.monitoring', 'scratchrobin.mysql.monitoring')
    mysql.save(1, 7, None, request)
    published = mysql.publish(1, 7, None, {'source_version': 1, 'expected_version': 0})
    assert 'should-not-persist' not in published['snapshot']['files']['dashboard.ddn']
    assert mysql._publication(1, reference)['metadata']['binding_contract'] == 'mysql-observations-v1'
    assert firebird.published(1, 7)['state'] == 'standard'
    with pytest.raises(ProjectAssetConflict):
        mysql.publish(1, 7, None, {'source_version': 1, 'expected_version': 0})
