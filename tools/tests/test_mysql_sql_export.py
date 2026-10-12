"""DDN/native SQL exchange preserves context, names and complete bodies."""
from copy import deepcopy
import json
import pytest
from pgadmin.cdeadmin.workspace.mysql_sql_export import build_metadata
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog


def model(specs):
    db = 'demo`db'
    root_id = 'mysql:' + json.dumps([db, 'database', None, db], separators=(',', ':'))
    resources = []
    for kind, name, definition, extras in [('database', db, 'CREATE DATABASE `demo``db`', {}), *specs]:
        parent = None if kind == 'database' else root_id
        identity = 'mysql:' + json.dumps([db, kind, parent, name], separators=(',', ':'))
        native = {'database': db, 'definition': definition, 'system_object': False, **extras}
        if parent: native['navigator_parent_resource_id'] = parent
        if kind == 'database':
            native.update(catalog_row={'database_name': db, 'version': '9.7.0', 'server_uuid': 'server',
                'sql_mode': 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES', 'character_set_client': 'utf8mb4',
                'collation_connection': 'utf8mb4_0900_ai_ci'},
                catalog_observations=[{'section': section, 'available': True} for section in ['KEY_COLUMN_USAGE','VIEW_TABLE_USAGE']])
        resources.append({'resource_id': identity, 'resource_kind': kind, 'display_name': name,
            'display_path': [db] + ([] if kind == 'database' else [name]), 'native': native})
    for resource in resources:
        for index, fk in enumerate(resource['native'].get('children', {}).get('KEY_COLUMN_USAGE', [])):
            fk.update(constraint_name='fk_'+str(index), column_name='id', ordinal_position=1, referenced_column_name='id')
    export = build_export(resources, engine='mysql', endpoint_id='endpoint', target_id='target', generation='gen')
    return read_catalog(json.dumps(export['snapshot']), engine='mysql')


def test_native_ddn_export_preserves_body_context_and_dependency_order():
    context = {'sql_mode': 'NO_BACKSLASH_ESCAPES', 'character_set_client': 'utf8mb4', 'collation_connection': 'utf8mb4_bin'}
    child = {'children': {'KEY_COLUMN_USAGE': [{'referenced_table_schema': 'demo`db', 'referenced_table_name': 'z_parent'}]}}
    document = model([('table','a_child','CREATE TABLE `a_child` (`id` int)', child),
        ('table','z_parent','CREATE TABLE `z_parent` (`id` int PRIMARY KEY)',{}),
        ('procedure','routine',"CREATE PROCEDURE `routine`() BEGIN SELECT 'a;b'; SELECT 2; END",{'definition_context':context})])
    result = build_metadata(document)
    assert result['script_available'] and not result['executed'] and not result['deployment_authorized']
    names = [item['name'] for item in result['statements']]
    assert names.index('z_parent') < names.index('a_child')
    assert "BEGIN SELECT 'a;b'; SELECT 2; END" in result['script']
    assert len(result['script'].split('DELIMITER ',1)[1].splitlines()[0]) <= 15
    assert 'USE `demo``db`' in result['script'] and 'DELIMITER __sr_' in result['script']
    assert 'SET SESSION sql_mode = CONVERT(' in result['script']
    assert result['statements'][-1]['kind'] == 'table' or result['prerequisites']
    assert all(item['context'] == context for item in result['statements'] if item['kind'] == 'procedure')
    assert 'FOREIGN_KEY_CHECKS' not in result['script'].upper()


def test_cycles_denied_dependencies_and_missing_native_definitions_block_script():
    specs = [('table',name,'CREATE TABLE `'+name+'` (`id` int)', {'children':{'KEY_COLUMN_USAGE':[
        {'referenced_table_schema':'demo`db','referenced_table_name':other}]}}) for name,other in [('a','b'),('b','a')]]
    document=model(specs)
    result=build_metadata(document)
    assert not result['script_available'] and any('cycle' in row['reason'] for row in result['blockers'])
    document=model([('table','a',None,{})])
    assert not build_metadata(document)['script_available']
    document=model([('table','a','CREATE TABLE a(id int)',{})])
    root=next(row for row in document['rows'].values() if row['kind']=='database')
    root['native']['catalog_observations'][0]['available']=False
    assert not build_metadata(document)['script_available']


def test_context_encoding_scope_and_name_tampering_never_silently_normalize():
    document=model([('view','v','CREATE VIEW v AS SELECT 1',{'definition_context':{
        'character_set_client':'latin1','collation_connection':'latin1_swedish_ci'}})])
    assert any('encoding' in row['reason'] for row in build_metadata(document)['blockers'])
    row=next(row for row in document['rows'].values() if row['kind']=='view')
    row['native']['definition_context']={'character_set_client':'utf8mb4','collation_connection':'utf8mb4_bin'}
    row['name']='different'
    assert any('identity' in item['reason'] for item in build_metadata(document)['blockers'])
    changed=deepcopy(document);changed['provenance']['mapping']='scratchrobin.firebird.catalog@1'
    with pytest.raises(ValueError):build_metadata(changed)


def test_visible_filter_is_not_deletion_and_external_dependencies_are_explicit():
    document=model([('table','a','CREATE TABLE a(id int)',{'children':{'KEY_COLUMN_USAGE':[
        {'referenced_table_schema':'outside','referenced_table_name':'not_selected'}]}})])
    result=build_metadata(document)
    assert result['prerequisites'][0]['database']=='outside'
    assert not any('DROP ' in item['statement'].upper() for item in result['statements'])
    assert result['mode']=='export-only'


def test_native_metadata_host_authorizes_exact_owner_target_without_executing():
    import config
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError
    from pgadmin.cdeadmin.providers.mysql_family.provider import MySQLPilotProvider
    document = model([('table','a','CREATE TABLE a(id int)',{})])
    service = object.__new__(ProviderWorkspaceService)
    service._principal_id = Mock(return_value=1)
    service.endpoint_service = Mock()
    service.endpoint_service.workspace.return_value = (SimpleNamespace(endpoint_id='endpoint',profile_id='mysql-native'), {'route':{'database':'demo`db'}}, None)
    service.endpoint_service.database_catalog.return_value={'targets':[{'target_id':'target','database':'demo`db'}]}
    server=SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='mysql-native'))
    provider = Mock(spec=MySQLPilotProvider)
    service.endpoint_service.provider_registry.resolve.return_value.instance = provider
    with patch('pgadmin.cdeadmin.workspace.firebird_catalog_import.read_catalog', return_value=document):
        result = service.mysql_native_metadata(server, {'database_target_id':'target','source':'document'})
        assert result['mode'] == 'export-only' and not provider.mock_calls
        with pytest.raises(ProviderWorkspaceError,match='identity changed'):
            service.mysql_native_metadata(server, {'database_target_id':'other','source':'document'})
    service._principal_id.side_effect = ProviderWorkspaceError('Not owned')
    with pytest.raises(ProviderWorkspaceError, match='Not owned'):
        service.mysql_native_metadata(server, {'database_target_id':'target','source':'document'})
