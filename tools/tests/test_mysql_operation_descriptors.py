"""Typed maintenance drafts must retain the native operation input contract."""
import json
from pathlib import Path

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family import (
    mysql_instance, mysql_key_cache, mysql_key_cache_lifecycle, mysql_page_tracking,
    mysql_rewriter, mysql_server_control, mysql_xa,
)
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import backend_draft, engine_operations, operation_draft
from test_mysql_instance import target

MODULES = (mysql_instance, mysql_key_cache, mysql_key_cache_lifecycle,
           mysql_page_tracking, mysql_rewriter, mysql_server_control, mysql_xa)
OPERATIONS = engine_operations('mysql')
CASES = [(module, operation) for module in MODULES for operation in module.OPERATIONS]


def request_for(operation):
    kind = 'table' if operation in mysql_key_cache.OPERATIONS else 'server'
    resource = ({'resource_kind': 'table', 'resource_id': 'table:db:owned',
                 'display_path': ['db', 'owned'], 'display_name': 'owned'}
                if kind == 'table' else target())
    declared = OPERATIONS[operation + '@' + kind]
    samples = {'confirmation': resource['display_name'], 'pattern': 'SELECT ?',
               'replacement': 'SELECT 2', 'rule_id': '1', 'backup_id': '42',
               'decision_reference': 'owned transaction manager decision',
               'gtrid_hex': '00ff', 'bqual_hex': '00', 'format_id': '9223372036854775807',
               'database': 'db', 'files': [{'value': "/native/quote'雪.sdi"}],
               'indexes': [{'value': 'odd`index'}]}
    values = {f['field_id']: (True if f['control'] == 'boolean' else samples[f['field_id']])
              for f in declared['fields'] if f['control'] == 'boolean' or f['field_id'] in samples}
    ui = operation_draft(declared, values, resource['display_name'])
    # This is the documented projection required of the shared dialog. Its
    # current missing dispatch is Decision12, so these entries remain draft.
    draft = backend_draft({'tabs': [{'fields': declared['fields']}]}, ui)
    return {'resource_kind': kind, 'operation_id': operation,
            'target_resource': resource, 'draft': draft}, ui


@pytest.mark.parametrize('module,operation', CASES, ids=[op for _, op in CASES])
def test_declared_maintenance_inputs_validate_and_reach_the_existing_native_compiler(module, operation):
    request, _ui = request_for(operation)
    assert not MYSQL_ADMINISTRATION.validate(request)['errors'], operation
    actual = MYSQL_ADMINISTRATION._compile(request)
    direct = module.compile_operation(operation, request['draft'], request['target_resource'])
    assert actual['statements'] == direct['statements']
    declared = OPERATIONS[operation + '@' + request['resource_kind']]
    assert declared['status'] == 'draft'
    assert set(request['draft']) <= {f.get('backend_field_id', f['field_id']) for f in declared['fields']}


def test_native_default_and_conditional_inputs_do_not_become_false_required_fields():
    request, _ = request_for('configure_key_cache')
    request['draft'].update(value_mode='DEFAULT')
    del request['draft']['value']
    assert not MYSQL_ADMINISTRATION.validate(request)['errors']
    assert MYSQL_ADMINISTRATION._compile(request)['statements'][0] == {
        'source': 'SET GLOBAL `default`.`key_buffer_size` = DEFAULT', 'parameters': ()}
    request['draft']['value_mode'] = 'VALUE'
    with pytest.raises(RelationalClientError):
        MYSQL_ADMINISTRATION._compile(request)


@pytest.mark.parametrize('operation', ['assign_index_cache', 'preload_index_cache', 'import_table_sdi'])
def test_scalar_lists_require_the_declared_projection_and_never_stringify_records(operation):
    request, ui = request_for(operation)
    field = 'files' if operation == 'import_table_sdi' else 'indexes'
    assert isinstance(request['draft'][field][0], str)
    request['draft'][field] = ui[field]
    with pytest.raises(RelationalClientError):
        MYSQL_ADMINISTRATION._compile(request)


def test_unsigned_lsn_and_binary_xa_identities_survive_the_typed_boundary():
    request, _ = request_for('count_tracked_pages')
    request['draft'].update(start_lsn=str(2**64 - 1), stop_lsn='0')
    assert MYSQL_ADMINISTRATION._compile(request)['statements'][0]['parameters'] == (2**64 - 1, 0)
    request, _ = request_for('commit_prepared_xa')
    sql = MYSQL_ADMINISTRATION._compile(request)['statements'][0]
    assert "X'00FF',X'00',9223372036854775807" in sql['source'].upper()


@pytest.mark.parametrize('mode,expected', [('NULL', None), ('VALUE', '')])
def test_empty_pattern_database_remains_distinct_from_native_null(mode, expected):
    request, _ = request_for('create_rewrite_rule')
    request['draft'].update(pattern_database_mode=mode, pattern_database='')
    assert not MYSQL_ADMINISTRATION.validate(request)['errors']
    assert MYSQL_ADMINISTRATION._compile(request)['statements'][0]['parameters'][1] == expected


def test_navigator_covers_only_the_actual_native_catalog_and_declares_table_children():
    folder = Path(__file__).resolve().parents[2] / 'web/pgadmin/cdeadmin/ui_descriptors/mysql'
    navigation = json.loads((folder / 'navigator.json').read_text())
    capabilities = json.loads((folder / 'capabilities.json').read_text())
    expected = {row['resource_kind'] for row in capabilities['kinds']}
    declared = [kind for group in navigation['groups'] for kind in group['kinds']]
    assert set(declared) == expected == set(navigation['kind_icons'])
    assert len(declared) == len(set(declared))
    assert set(navigation['resource_children']['table']) == {'column', 'index', 'trigger', 'constraint', 'partition'}
    assert navigation['system_object_group'] in {group['group_id'] for group in navigation['groups']}
