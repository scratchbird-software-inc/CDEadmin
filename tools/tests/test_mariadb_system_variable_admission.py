"""MariaDB native scope labels and FLAGSET assignment contracts."""
import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_ADMINISTRATION


def request(scope='SESSION', variable_type='BIGINT UNSIGNED', **draft):
    return {'resource_kind': 'system-variable', 'operation_id': 'set_global',
            '_provider_route': {'host': 'owned', 'database': 'owned'},
            'target_resource': {
                'resource_kind': 'system-variable', 'display_name': 'sort_buffer_size',
                'display_path': ['Configuration', 'sort_buffer_size'],
                'native': {'read_only': 'NO', 'variable_scope': scope,
                           'variable_type': variable_type,
                           'enum_value_list': 'index_merge,mrr,default',
                           'numeric_min_value': '0',
                           'numeric_max_value': '4294967295'}},
            'draft': {'value_mode': 'VALUE', 'value': '262144', **draft}}


@pytest.mark.parametrize('scope', ['SESSION', 'GLOBAL'])
def test_native_global_capable_scope_classes(scope):
    value = request(scope)
    assert not MARIADB_ADMINISTRATION.validate(value)['errors']
    assert 'SET GLOBAL' in MARIADB_ADMINISTRATION.plan(value)[
        'command_preview']['statements'][0]['source']


@pytest.mark.parametrize('scope', ['SESSION ONLY', '', None, 'UNKNOWN'])
def test_session_only_or_missing_native_scope_never_becomes_global(scope):
    errors = MARIADB_ADMINISTRATION.validate(request(scope))['errors']
    assert any(error['code'] == 'mariadb_system_variable_not_global'
               for error in errors)


@pytest.mark.parametrize('value', [
    '', 'default', 'index_merge=on', 'index_merge=off,mrr=default',
    'default,index_merge=ON', 'INDEX_MERGE=DEFAULT',
])
def test_flagset_assignments_use_native_flags_and_value_grammar(value):
    target = request(variable_type='FLAGSET', value=value)
    assert not MARIADB_ADMINISTRATION.validate(target)['errors']
    source = MARIADB_ADMINISTRATION.plan(target)[
        'command_preview']['statements'][0]['source']
    assert source.endswith("= '" + value + "'")


@pytest.mark.parametrize('value', [
    'index_merge', 'not_installed=on', 'mrr=maybe', 'default=on',
    'default,default', 'mrr=on,MRR=off', 'mrr=on,',
    "mrr=on'; DROP TABLE innocent; --", 7, True, None,
])
def test_invalid_flagset_does_not_reach_native_dispatch(value):
    errors = MARIADB_ADMINISTRATION.validate(request(
        variable_type='FLAGSET', value=value))['errors']
    assert any(error['code'] == 'invalid_mariadb_system_variable_value'
               for error in errors)


def test_readonly_and_compiled_default_keep_their_native_contracts():
    target = request(variable_type='FLAGSET', value_mode='DEFAULT')
    assert not MARIADB_ADMINISTRATION.validate(target)['errors']
    assert MARIADB_ADMINISTRATION.plan(target)['command_preview'][
        'statements'][0]['source'].endswith('= DEFAULT')
    target['target_resource']['native']['read_only'] = 'YES'
    assert any(error['code'] == 'mariadb_system_variable_read_only'
               for error in MARIADB_ADMINISTRATION.validate(target)['errors'])


@pytest.mark.parametrize('mask', ['0', '1', '7'])
def test_numeric_flagset_is_an_unquoted_native_expression(mask):
    target = request(variable_type='FLAGSET', value_mode='BITMASK', bitmask=mask)
    assert not MARIADB_ADMINISTRATION.validate(target)['errors']
    assert MARIADB_ADMINISTRATION.plan(target)['command_preview'][
        'statements'][0]['source'].endswith('= ' + mask)


@pytest.mark.parametrize('mask', ['8', '-1', '1.0', '1e0', ' 1', '01',
                                   '1; SELECT 1', 1, True, None])
def test_numeric_flagset_refuses_out_of_range_or_inexact_input(mask):
    target = request(variable_type='FLAGSET', value_mode='BITMASK', bitmask=mask)
    assert any(error['code'] == 'invalid_mariadb_flagset_bitmask'
               for error in MARIADB_ADMINISTRATION.validate(target)['errors'])


def test_numeric_mode_refuses_non_flagset_and_missing_metadata():
    target = request(value_mode='BITMASK', bitmask='1')
    assert MARIADB_ADMINISTRATION.validate(target)['errors']
    target = request(variable_type='FLAGSET', value_mode='BITMASK', bitmask='1')
    target['target_resource']['native']['enum_value_list'] = None
    assert MARIADB_ADMINISTRATION.validate(target)['errors']


def test_numeric_flagset_uses_exact_uint64_text():
    from pgadmin.cdeadmin.providers.mysql_family.mariadb_variables import flagset_bitmask
    options = ','.join(['flag_' + str(i) for i in range(63)] + ['default'])
    assert flagset_bitmask('18446744073709551615', options) == (1 << 64) - 1
    with pytest.raises(ValueError):
        flagset_bitmask('18446744073709551616', options)


@pytest.mark.parametrize('rows,reset,expected', [
    ([], False, ''), ([], True, 'default'),
    ([{'flag': 'mrr', 'state': 'on'}], False, 'mrr=on'),
    ([{'flag': 'mrr', 'state': 'default', '_id': 'row'}], True,
     'default,mrr=default'),
    ([{'flag': 'index_merge', 'state': 'off'}, {'flag': 'mrr', 'state': 'on'}],
     False, 'index_merge=off,mrr=on'),
])
def test_structured_flags_preserve_native_reset_and_partial_assignments(rows, reset, expected):
    target = request(variable_type='FLAGSET', value_mode='FLAGS',
                     flags=rows, reset_defaults=reset)
    assert not MARIADB_ADMINISTRATION.validate(target)['errors']
    assert MARIADB_ADMINISTRATION.plan(target)['command_preview'][
        'statements'][0]['source'].endswith("= '" + expected + "'")


@pytest.mark.parametrize('rows,reset', [
    (None, False), ({}, False), (['mrr=on'], False),
    ([{'flag': 'mrr', 'state': 'on', 'extra': 'ignored'}], False),
    ([{'flag': 'default', 'state': 'on'}], False),
    ([{'flag': 'missing', 'state': 'on'}], False),
    ([{'flag': 'mrr', 'state': 'maybe'}], False),
    ([{'flag': 'mrr', 'state': 'on'}, {'flag': 'MRR', 'state': 'off'}], False),
    ([{'flag': "mrr'; SELECT 1", 'state': 'on'}], False),
    ([], 'false'), ([], 0),
])
def test_structured_flags_refuse_malformed_unknown_duplicate_and_untyped_rows(rows, reset):
    target = request(variable_type='FLAGSET', value_mode='FLAGS',
                     flags=rows, reset_defaults=reset)
    assert any(error['code'] == 'invalid_mariadb_flagset_assignments'
               for error in MARIADB_ADMINISTRATION.validate(target)['errors'])


def test_structured_flags_are_restricted_to_flagset_targets():
    assert MARIADB_ADMINISTRATION.validate(request(
        value_mode='FLAGS', flags=[], reset_defaults=False))['errors']


def test_structured_flags_descriptor_draft_and_visibility():
    from ui_descriptor_roundtrip import engine_operations, operation_draft, field_visible
    operation = engine_operations('mariadb')['set_global@system-variable']
    draft = operation_draft(operation, {'value_mode': 'FLAGS',
        'flags': [{'flag': 'mrr', 'state': 'off'}]})
    target = request(variable_type='FLAGSET', **draft)
    assert not MARIADB_ADMINISTRATION.validate(target)['errors']
    visible = {field['field_id'] for field in operation['fields']
               if field_visible(field, draft)}
    assert visible == {'value_mode', 'reset_defaults', 'flags'}
    assert MARIADB_ADMINISTRATION.plan(target)['command_preview'][
        'statements'][0]['source'].endswith("= 'mrr=off'")
