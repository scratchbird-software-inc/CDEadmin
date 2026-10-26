"""Installed interface metadata retains native fields and read-only boundaries."""
from copy import deepcopy
import json
import pytest
from test_mysql_server_catalog import Connection
from pgadmin.cdeadmin.providers.mysql_family import mysql_server_catalog as catalog
from pgadmin.cdeadmin.providers.mysql_family.installed_catalog import PLUGIN_COLUMNS, PLUGINS, FUNCTIONS
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.mysql_server_plan import plan, state

PLUGIN = dict(zip((key.lower() for key in PLUGIN_COLUMNS), [
    'native_example', 'ACTIVE', 'AUTHENTICATION', None, 'GPL', '1.2', '1.3', None,
    'Native author', 'Description 雪\nsecond line', 'FORCE_PLUS_PERMANENT']))
FUNCTION = {'udf_name': 'service.fn`雪', 'udf_return_type': 'STRING', 'udf_type': 'function',
            'udf_library': None, 'udf_usage_count': 2**63-1}


class Installed(Connection):
    def __init__(self, denied=False):
        super().__init__(); self.denied = denied

    def cursor(self, **options):
        parent = self
        original = super().cursor(**options)
        execute = original.execute
        def selected(source, parameters=None):
            if source in {PLUGINS, FUNCTIONS}:
                if parent.denied and source == FUNCTIONS:
                    error = RuntimeError('Native denied details must not be exposed')
                    error.errno, error.sqlstate = 1142, '42000'
                    raise error
                row = PLUGIN if source == PLUGINS else FUNCTION
                original.description = [(key,) for key in row]
                original.rows = [tuple(row.values())]
                parent.calls.append(source)
            else:
                execute(source, parameters)
        original.execute = selected
        return original


def model(captured):
    export = build_export(captured['resources'], endpoint_id='ep', target_id='server:server-id',
                          generation=captured['generation'], engine='mysql')
    return read_catalog(json.dumps(export['snapshot']), engine='mysql')


def test_every_native_plugin_field_and_null_library_survive_server_capture_and_ddn():
    captured = catalog.capture(Installed())
    plugin = next(row for row in captured['resources'] if row['resource_kind'] == 'plugin')
    assert plugin['native']['catalog_row'] == PLUGIN
    assert len(PLUGIN_COLUMNS) == 11 and len(set(PLUGIN_COLUMNS)) == 11
    restored = model(captured)
    assert restored['rows'][plugin['resource_id']]['native']['catalog_row'] == PLUGIN
    assert not captured['complete']


def test_runtime_service_function_identity_null_library_and_wide_usage_are_preserved():
    captured = catalog.capture(Installed())
    function = next(row for row in captured['resources'] if row['resource_kind'] == 'loadable-function')
    assert function['native']['catalog_row'] == FUNCTION
    restored = model(captured)
    assert restored['rows'][function['resource_id']]['native']['catalog_row'] == FUNCTION
    changed = deepcopy(restored)
    changed['rows'][function['resource_id']]['native']['catalog_row']['udf_usage_count'] -= 1
    assert state(changed['rows'][function['resource_id']]) == state(restored['rows'][function['resource_id']])
    result = plan(restored, changed, changed)
    assert not result['operations'] and not result['blockers'] and not result['conflicts']


def test_denied_runtime_catalog_is_an_unavailable_section_not_a_successful_empty_inventory():
    captured = catalog.capture(Installed(denied=True))
    assert next(row for row in captured['observations'] if row['section'] == 'runtime-functions') == {
        'section': 'runtime-functions', 'available': False, 'error_code': 1142, 'sqlstate': '42000'}
    assert not any(row['resource_kind'] == 'loadable-function' for row in captured['resources'])
    assert 'Native denied details' not in json.dumps(captured)


@pytest.mark.parametrize('action', ['create', 'drop'])
def test_runtime_function_metadata_does_not_authorize_server_ddl(action):
    baseline = model(catalog.capture(Installed())); desired = deepcopy(baseline)
    row = next(row for row in desired['rows'].values() if row['kind'] == 'loadable-function')
    row['native']['mysql_change'] = {'action': action, 'draft': {}}
    result = plan(baseline, desired, baseline)
    assert not result['ready_for_review'] and not result['operations'] and result['blockers']


def test_catalog_queries_select_only_explicit_native_metadata_columns():
    assert '*' not in PLUGINS + FUNCTIONS
    assert not any(value in (PLUGINS + FUNCTIONS).lower() for value in ['authentication_string', 'password', 'keyring_key_fetch('])
