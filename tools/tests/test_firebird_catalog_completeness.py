"""Visible coverage, plugin identities and complete native navigator traversal."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import _resources
from tools.cdeadmin_firebird_catalog_completeness_gate import reachable
from pgadmin.cdeadmin.providers.firebird.catalog_coverage import coverage
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def users(rows):
    cursor = Mock()
    current = []
    def execute(source, *_):
        nonlocal current
        current = rows if 'FROM SEC$USERS ORDER BY' in source else []
    cursor.execute.side_effect = execute
    cursor.fetchall.side_effect = lambda: current
    return _resources(SimpleNamespace(cursor=lambda: cursor, info=SimpleNamespace()), {})


def test_same_user_name_is_distinct_in_each_authentication_plugin():
    resources = users([('Same', 'Srp'), ('Same', 'CustomPlugin')])
    found = [item for item in resources if item['resource_kind'] == 'user']
    assert len(found) == 2 and len({item['resource_id'] for item in found}) == 2
    assert {item['native']['plugin'] for item in found} == {'Srp', 'CustomPlugin'}
    assert all(item['authority_path'] == ['user', 'Same'] for item in found)
    assert {item['resource_id'] for item in found} <= reachable(resources)


def test_duplicate_native_identity_is_refused_instead_of_overwritten():
    with pytest.raises(RelationalClientError, match='Duplicate Firebird catalog resource identity'):
        users([('Same', 'Srp'), ('Same', 'Srp')])


def test_optional_failure_is_partial_not_a_complete_empty_catalog():
    result = coverage([], [{'section': 'users', 'available': False}],
                      {'global mappings': {'available': False}}, {'available': False})
    assert result['state'] == 'partial'
    assert result['unavailable_sections'] == ['users', 'global mappings', 'database creation authority']
    assert result['resource_counts']['user'] == 0
    assert result['server_wide_completeness_asserted'] is False
    assert result['independent_inventory_verified'] is False


def test_system_package_and_same_named_system_sequence_do_not_hide_children():
    def item(kind, name, path=None, native=None):
        return {'resource_id': kind+':'+name, 'resource_kind': kind, 'display_name': name,
                'display_path': path or [name], 'native': native or {}}
    resources = [item('table', 'RDB$REL', native={'system_object': True}),
                 item('sequence', 'RDB$REL', native={'system_object': True}),
                 item('column', 'FIELD', ['RDB$REL', 'FIELD'], {'system_object': True, 'navigator_parent_resource_id': 'table:RDB$REL'}),
                 item('package', 'RDB$PK', native={'system_object': True}),
                 item('procedure', 'P', ['RDB$PK', 'P'], {'system_object': True, 'navigator_parent_resource_id': 'package:RDB$PK'}),
                 item('metric', 'MON$X', ['RDB$REL', 'MON$X'], {'navigator_parent_resource_id': 'table:RDB$REL'})]
    assert reachable(resources) == {item['resource_id'] for item in resources}


def test_user_attributes_and_plugin_bound_alter_and_drop():
    from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
    value = next(item for item in users([('Same', 'CustomPlugin', 'First', 'Middle', 'Last', True, False, '  comment  ')]) if item['resource_kind'] == 'user')
    assert value['native']['first_name'] == 'First'
    assert value['native']['active'] is True and value['native']['administrator'] is False
    assert value['native']['description'] == '  comment  '
    sql, preview = ADMINISTRATION._alter_user(value, {'active': False})
    assert sql == preview == 'ALTER USER "Same" INACTIVE USING PLUGIN "CustomPlugin"'
    assert ADMINISTRATION._compile_drop({'resource_kind': 'user', 'target_resource': value})['source'] == 'DROP USER "Same" USING PLUGIN "CustomPlugin"'
    with pytest.raises(RelationalClientError, match='redirect'):
        ADMINISTRATION._alter_user(value, {'active': False, 'plugin': 'Srp'})


def test_partial_authority_survives_catalog_export_and_search():
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.firebird_search import search
    metadata = {'coverage_complete': False, 'catalog_coverage': {'state': 'partial'},
                'catalog_observations': [{'section': 'tables', 'available': True}],
                'catalog_warnings': ['Global mappings unavailable']}
    row = {'resource_id': 'db', 'resource_kind': 'database', 'display_name': 'DB', 'display_path': ['DB'], 'native': metadata}
    exported = build_export([row], endpoint_id='e', target_id='d', generation='g')
    assert exported['provenance']['coverage'] == 'partial'
    result = search({'resources': [row], 'generation': 'g'}, 'DB', {'name'})
    assert result['catalog_coverage'] == [{'state': 'partial'}]
    assert result['catalog_warnings'] == ['Global mappings unavailable']


@pytest.mark.parametrize('field', ['stored_page_buffers', 'encryption_key_name', 'encryption_plugin', 'engine_version'])
def test_information_failure_injection_uses_actual_native_info_boundary(field):
    from tools.cdeadmin_firebird_catalog_observation_gate import UnavailableInformation
    from pgadmin.cdeadmin.providers.firebird.attachment_cache import stored_page_buffers
    from pgadmin.cdeadmin.providers.firebird.encryption_info import read_encryption_text
    info = Mock()
    info.get_info.return_value = 25
    wrapped = UnavailableInformation(info, field)
    with pytest.raises(RuntimeError, match='private driver details'):
        if field == 'stored_page_buffers':
            stored_page_buffers(wrapped)
        elif field.startswith('encryption_'):
            read_encryption_text(wrapped, field)
        else:
            getattr(wrapped, field)
    assert wrapped.get_info(999) == 25
