"""Native configuration observations are complete, exact and read-only."""
import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.providers.firebird import configuration
from pgadmin.cdeadmin.providers.firebird.provider import PROFILE
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine


@pytest.mark.parametrize('value', [None, '', ' trailing ', '0', 'false'])
def test_preserve_native_values_without_guessing_coercion(value):
    native = configuration.metadata(('WireCryptPlugin', 1, value,
                                     None, False, 'config source '))
    assert native['value'] == value
    assert native['default_value'] is None
    assert native['value_source'] == 'config source '
    assert native['explicitly_set'] is False
    assert native['sql_mutable'] is False


@pytest.mark.parametrize('name,kind,scope', [
    ('ServerMode', 'string', 'global'),
    ('MaxParallelWorkers', 'integer', 'global'),
    ('ReadConsistency', 'boolean', 'database-overridable'),
    ('AuthServer', 'string', 'database-overridable'),
    ('UnknownFutureSetting', 'unknown', 'unknown'),
])
def test_native_scope_is_separate_from_observed_value(name, kind, scope):
    value = configuration.metadata((name, 3, 'unparsed', '', True, None))
    assert value['native_type'] == kind
    assert value['configuration_scope'] == scope
    assert value['value'] == 'unparsed'


@pytest.mark.parametrize('row', [
    None, {}, (), ('X',), ('X', True, '', '', True, None),
    ('X', 1, 3, '', True, None), ('X', 1, '', '', 'false', None),
    ('X', 1, '', '', True, 0), ('', 1, '', '', True, None),
])
def test_malformed_observations_are_not_silently_coerced(row):
    with pytest.raises(RelationalClientError, match='invalid native fields'):
        configuration.metadata(row)


def test_configuration_is_not_an_installable_plugin_or_mutable_sql_object():
    assert 'configuration' in PROFILE.resource_kinds
    assert 'plugin' not in PROFILE.resource_kinds
    catalog = catalog_for_engine('firebird')
    descriptor = next(item for item in catalog['objects']
                      if item['resource_kind'] == 'configuration')
    assert [item['operation_id'] for item in descriptor['operations']] == [
        'inspect']
    assert not any(item['resource_kind'] == 'plugin'
                   for item in catalog['objects'])
    for operation in ('create', 'alter', 'drop'):
        with pytest.raises(RelationalClientError, match='unavailable'):
            ADMINISTRATION.plan({
                '_provider_route': {'database': 'owned.fdb'},
                'resource_kind': 'configuration', 'operation_id': operation,
                'target_resource': {'resource_kind': 'configuration',
                                    'display_path': ['ServerMode']},
                'draft': {'name': 'ServerMode', 'value': 'Classic'}})
