"""tools.json: declared tool openers replace engine_id branches in context_menu.py."""
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.context_menu import (  # noqa: E402
    connector_context_actions, database_target_context_actions, declared_tool_actions,
    endpoint_context_actions, resource_context_actions,
)
sys.path.insert(0, str(ROOT / 'tools/tests'))
from test_cdeadmin_context_menu import profile  # noqa: E402

DESCRIPTORS = ROOT / 'web/pgadmin/cdeadmin/ui_descriptors'


def ids(actions):
    return [item['command_id'] for item in actions]


def test_declared_tools_are_well_formed_for_every_engine_that_declares_them():
    for path in DESCRIPTORS.glob('*/tools.json'):
        document = json.loads(path.read_text(encoding='utf-8'))
        assert document['engine'] == path.parent.name
        for tool in document['tools']:
            assert tool['command_id'].split('.')[0] in {'connector', 'endpoint', 'database', 'resource'}, tool['command_id']
            assert tool['scope'] in {'connector', 'endpoint', 'database', 'resource_group', 'resource'}


def test_slot_scope_and_when_filters():
    state = {'engine_id': 'duckdb', 'route_kind': 'network', 'localhost_placeholder': False}
    assert ids(declared_tool_actions('duckdb', 'connector', state=state)) == [
        'connector.duckdb.monitoring', 'connector.duckdb.dashboard_editor']
    assert declared_tool_actions('duckdb', 'connector', state={**state, 'localhost_placeholder': True}) == []
    assert declared_tool_actions('duckdb', 'connector', 'profile', state=state) == []
    assert declared_tool_actions('no-such-engine', 'connector', state=state) == []
    # Firebird network-only entries disappear for the embedded profile.
    network = ids(declared_tool_actions('firebird', 'database', 'pre_lifecycle',
                                        state={'engine_id': 'firebird', 'route_kind': 'network'}, base={}))
    embedded = ids(declared_tool_actions('firebird', 'database', 'pre_lifecycle',
                                         state={'engine_id': 'firebird', 'route_kind': 'embedded_file'}, base={}))
    assert 'database.firebird.isql' in network and 'database.firebird.isql' not in embedded


def test_enablement_reasons_follow_the_declared_conditions():
    base = {'engine_id': 'sqlite', 'display': 'Sqlite', 'route_kind': 'embedded_file',
            'verified_reason': 'Verify this endpoint before using it.'}
    blocked = {item['command_id']: item for item in declared_tool_actions(
        'sqlite', 'endpoint', 'after_verify', state={**base, 'verified': False, 'owner': True})}
    assert blocked['endpoint.sqlite.monitoring']['enabled'] is False
    assert blocked['endpoint.sqlite.monitoring']['disabled_reason'] == 'Verify this endpoint before using it.'
    assert blocked['endpoint.sqlite.recovery']['enabled'] is True  # owner-only condition
    not_owner = {item['command_id']: item for item in declared_tool_actions(
        'sqlite', 'endpoint', 'after_verify', state={**base, 'verified': True, 'owner': False})}
    assert not_owner['endpoint.sqlite.recovery']['disabled_reason'] == 'Only the endpoint owner can recover its files.'
    assert not_owner['endpoint.sqlite.dashboard_editor']['disabled_reason'] == 'Only the endpoint owner can edit it.'


def test_arguments_merge_over_the_scope_base_and_labels_format():
    actions = {item['command_id']: item for item in declared_tool_actions(
        'firebird', 'database', 'post_lifecycle', state={'engine_id': 'firebird'},
        base={'resource_id': 't1', 'database_target_id': 't1'})}
    privilege = actions['database.firebird.security.privilege']
    # collection tasks keep the database route only
    assert privilege['arguments'] == {'database_target_id': 't1', 'tab': 'administration',
                                      'resource_kind': 'privilege', 'operation_id': 'grant'}
    endpoint = {item['command_id']: item for item in declared_tool_actions(
        'firebird', 'endpoint', 'after_verify', state={'engine_id': 'firebird', 'display': 'Firebird',
                                                       'verified': True, 'owner': True, 'route_kind': 'network'})}
    assert endpoint['endpoint.firebird.disconnect']['label'] == 'Disconnect Firebird endpoint...'


def test_builders_still_emit_the_migrated_entries():
    assert 'connector.firebird.docker' in ids(connector_context_actions('firebird', [profile('firebird')]))
    assert 'connector.firebird.create_database' in ids(connector_context_actions('firebird', [profile('firebird')]))
    endpoint = ids(endpoint_context_actions(profile('duckdb', route_kind='embedded_file'), 'verified'))
    assert {'endpoint.duckdb.monitoring', 'endpoint.duckdb.catalog_ddn', 'endpoint.duckdb.dashboard_editor'} <= set(endpoint)
    database = ids(database_target_context_actions(profile('sqlite', route_kind='embedded_file'),
                                                   {'target_id': 't1', 'display_name': 'demo'}))
    assert {'database.sqlite.recovery', 'database.sqlite.test_data', 'database.sqlite.monitoring'} <= set(database)
    catalog = {'objects': [{'resource_kind': 'table', 'title': 'Table', 'operations': [], 'editor': {'sections': ['data']}}]}
    resource = {'resource_id': 'table:t', 'resource_kind': 'table', 'display_name': 't', 'display_path': ['t']}
    assert 'resource.sqlite.table.export_sql' in ids(resource_context_actions(
        profile('sqlite', route_kind='embedded_file'), resource, catalog, database_target_id='t1'))
    system = {**resource, 'native': {'system_object': True}}
    assert 'resource.sqlite.table.export_sql' not in ids(resource_context_actions(
        profile('sqlite', route_kind='embedded_file'), system, catalog, database_target_id='t1'))
