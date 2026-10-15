import config
import pytest
from types import SimpleNamespace
from unittest.mock import Mock
from pgadmin.cdeadmin.workspace.firebird_templates import context, render, DEFAULTS
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError


def snapshot(kind='table', relation_type=0, system=False):
    return {'generation': 'g', 'resources': [
        {'resource_id': 't', 'resource_kind': kind, 'display_name': 'Mixed"Table',
         'display_path': ['db', 'T'], 'native': {'relation_type': relation_type, 'system_object': system}},
        *[{'resource_id': name, 'resource_kind': 'column', 'display_name': name,
           'display_path': ['db', 'T', name], 'extensions': {'firebird': {'native': native}}}
          for name, native in [('C', {'position': 2, 'computed_source': '1'}),
                               ('ID', {'position': 0, 'identity_type': 0}),
                               ('V', {'position': 1})]] ]}


def test_native_order_identity_and_computed_admission():
    value = context(snapshot(), 't')
    assert render(value, DEFAULTS['select'])['source'] == 'SELECT "ID", "V", "C" FROM "Mixed""Table";'
    result = render(value, DEFAULTS['insert'])
    assert result['source'] == 'INSERT INTO "Mixed""Table" ("V") VALUES (?);'
    assert result['parameters'] == [None]
    assert result['executed'] is False
    assert 'WHERE FALSE' in render(value, DEFAULTS['update'])['source']


@pytest.mark.parametrize('kind,relation,system,absent', [
    ('view', 1, False, {'insert', 'update', 'delete', 'trigger'}),
    ('table', 0, True, {'insert', 'update', 'delete', 'trigger'}),
    ('table', 2, False, {'update', 'delete'})])
def test_native_family_boundaries(kind, relation, system, absent):
    assert not absent.intersection(context(snapshot(kind, relation, system), 't')['templates'])


@pytest.mark.parametrize('source', ['{{password}}', '{{new_object}}', '{{definition}}', '{{object', '}}', '', 'x\0', 'x'*65537])
def test_invalid_or_unavailable_tokens_refused(source):
    with pytest.raises(ValueError):
        render(context(snapshot(), 't'), source)


def test_native_text_not_recursively_interpreted():
    value = context(snapshot(), 't')
    value['substitutions']['definition'] = "SELECT '{{password}}' FROM RDB$DATABASE;"
    assert render(value, '{{definition}}')['source'] == value['substitutions']['definition']
    assert '"a""b"' in render(value, DEFAULTS['procedure'], 'a"b')['source']


def test_host_generation_and_engine_fences():
    service = object.__new__(ProviderWorkspaceService)
    service.navigator_snapshot = Mock(return_value=snapshot())
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='firebird-native'))
    request = {'resource_id': 't', 'database_target_id': 'db', 'generation': 'g'}
    assert service.firebird_object_templates(server, request)['resource_id'] == 't'
    service.navigator_snapshot.assert_called_once_with(server, database_target_id='db')
    for change in [{'generation': 'old'}, {'resource_id': 'missing'}, {'unknown': True}]:
        with pytest.raises(ProviderWorkspaceError):
            service.firebird_object_templates(server, {**request, **change})
    server.endpoint_profile.profile_id = 'mysql-native'
    with pytest.raises(ProviderWorkspaceError):
        service.firebird_object_templates(server, request)



def test_stored_dialect_one_is_bound_to_exact_native_names():
    value=snapshot()
    for row in value['resources']:
        row['display_name']='PLAIN' if row['resource_kind']=='table' else row['display_name']
    value['resources'].append({'resource_kind':'database','resource_id':'db','native':{'sql_dialect':1}})
    selected=context(value,'t')
    assert selected['database_sql_dialect']==1
    assert render(selected,DEFAULTS['select'])['source']=='SELECT ID, V, C FROM PLAIN;'
    with pytest.raises(RelationalClientError):
        render(selected,DEFAULTS['procedure'],'Mixed')


def test_unknown_system_classification_does_not_advertise_mutations():
    value=snapshot()
    value['resources'][0]['native'].pop('system_object')
    assert not {'insert','update','delete','trigger'}.intersection(context(value,'t')['templates'])
