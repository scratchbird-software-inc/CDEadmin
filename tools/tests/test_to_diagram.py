"""To Diagram: the server half (owner direction 2026-11-06).

The six engines whose catalog export builds a relations diagram (Firebird,
MySQL, MariaDB, PostgreSQL, SQLite, DuckDB) offer "To Diagram" on database
targets and on tables and views; the catalog_diagram workspace action
returns the export's relations source, the objects file it goes in and the
nested regions (host, instance, database, containers) of each relation. The
browser merge is covered by web/regression/javascript/cdeadmin/
ToDiagram.spec.jsx.
"""
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from test_cdeadmin_context_menu import profile
from pgadmin.cdeadmin.context_menu import (
    database_target_context_actions, resource_context_actions)
from pgadmin.cdeadmin.workspace import catalog_diagrams
from pgadmin.cdeadmin.workspace.firebird_catalog_export import (
    DIAGRAM_RELATION_KINDS, build_export, diagram_relations)

ENGINES = ('firebird', 'mysql', 'mariadb', 'postgresql', 'sqlite', 'duckdb')


def _commands(actions):
    return {item['command_id']: item for item in actions}


@pytest.mark.parametrize('engine', ENGINES)
def test_database_targets_and_relations_offer_to_diagram(engine):
    database = _commands(database_target_context_actions(
        profile(engine), {'target_id': 't1', 'display_name': 'db'}))
    action = database[f'database.{engine}.to_diagram']
    assert (action['label'], action['handler'], action['menu_group'],
            action['mutation_class']) == (
        'To Diagram', 'add_to_diagram', 'common', 'none')
    assert action['arguments'] == {'resource_id': 't1',
                                   'database_target_id': 't1'}
    for kind in ('table', 'view'):
        resource = {'resource_id': f'{kind}:r', 'resource_kind': kind,
                    'display_name': 'r', 'display_path': ['r']}
        offered = _commands(resource_context_actions(
            profile(engine), resource, None, database_target_id='t1'))
        assert offered[f'resource.{engine}.to_diagram']['arguments'] == {
            'resource_id': f'{kind}:r', 'database_target_id': 't1',
            'resource_kind': kind}
        # Without a database target there is no catalog to read.
        assert f'resource.{engine}.to_diagram' not in _commands(
            resource_context_actions(profile(engine), resource, None))
    column = {'resource_id': 'column:c', 'resource_kind': 'column',
              'display_name': 'c', 'display_path': ['r', 'c']}
    assert f'resource.{engine}.to_diagram' not in _commands(
        resource_context_actions(profile(engine), column, None,
                                 database_target_id='t1'))


def test_engines_without_a_catalog_diagram_do_not_offer_it():
    for engine in ('cockroachdb', 'tidb', 'mongodb'):
        actions = database_target_context_actions(
            profile(engine), {'target_id': 't1', 'display_name': 'db'})
        assert not [item for item in actions
                    if item['handler'] == 'add_to_diagram']


def test_relations_are_the_drawn_tables_and_views_with_their_paths():
    diagram = {'resource_mapping': {'n_t': 'table:t', 'n_v': 'view:v',
                                    'n_c': 'column:c', 'n_fk': 'fk:f'}}
    rows = [
        {'resource_id': 'view:v', 'resource_kind': 'view',
         'display_name': 'v', 'display_path': ['db', 's', 'v']},
        {'resource_id': 'table:t', 'resource_kind': 'table',
         'display_name': 't', 'display_path': ['db', 'a', 't']},
        {'resource_id': 'column:c', 'resource_kind': 'column',
         'display_name': 'c', 'display_path': ['db', 'a', 't', 'c']},
        {'resource_id': 'fk:f', 'resource_kind': 'constraint',
         'display_name': 'f', 'display_path': ['db', 'a', 't', 'f']}]
    assert diagram_relations(diagram, rows) == [
        {'key': 'n_t', 'resource_id': 'table:t', 'kind': 'table',
         'name': 't', 'path': ['db', 'a', 't']},
        {'key': 'n_v', 'resource_id': 'view:v', 'kind': 'view',
         'name': 'v', 'path': ['db', 's', 'v']}]
    assert {'table', 'view', 'fts-table'} <= DIAGRAM_RELATION_KINDS


def test_regions_nest_host_instance_database_and_containers():
    relations = [
        {'key': 'n_1', 'path': ['shop', 'public', 'orders']},
        {'key': 'n_2', 'path': ['shop', 'public', 'items']},
        {'key': 'n_3', 'path': ['shop', 'audit', 'log']},
        {'key': 'n_4', 'path': ['loose']}]
    regions, placed = catalog_diagrams._regions(
        'db.example', '7', 'Production', 5432, 't1', 'shop', relations)
    names = {item['id']: item for item in regions}
    assert [(item['role'], item['name']) for item in regions] == [
        ('host', 'db.example'), ('server', 'Production :5432'),
        ('database', 'shop'), ('schema', 'public'), ('schema', 'audit')]
    database = regions[2]['id']
    # The path's leading database name is not repeated as a region.
    assert names[placed[0]['region']]['name'] == 'public'
    assert placed[0]['region'] == placed[1]['region']
    assert names[placed[2]['region']]['parent'] == database
    assert placed[3]['region'] == database
    # Stable: the same endpoint and target give the same region ids.
    again, _ = catalog_diagrams._regions(
        'db.example', '7', 'Production', 5432, 't1', 'shop', relations)
    assert again == regions


def _sqlite_export(tmp_path):
    from pgadmin.cdeadmin.providers.sqlite.provider import (
        SQLiteProvider, _create_client)
    path = tmp_path / 'shop.sqlite'
    with sqlite3.connect(path) as owner:
        owner.executescript('''
            CREATE TABLE customer(id INTEGER PRIMARY KEY);
            CREATE TABLE purchase(id INTEGER PRIMARY KEY,
              customer_id INTEGER NOT NULL REFERENCES customer(id));
        ''')
    client = _create_client()
    try:
        provider = SQLiteProvider(SimpleNamespace(),
                                  SimpleNamespace(require=Mock()), client)
        captured = provider.capture_catalog({
            'database': str(path), 'filesystem_root': str(tmp_path)})
    finally:
        client.close()
    return build_export(captured['resources'], endpoint_id='7',
                        target_id='t1', generation=captured['generation'],
                        refreshed=True, engine='sqlite')


def _service(profile_id, export):
    context = SimpleNamespace(endpoint_id=7)
    endpoint = {'route': {'database': '/srv/shop.sqlite'}}
    service = SimpleNamespace(
        endpoint_service=SimpleNamespace(
            workspace=Mock(return_value=(context, endpoint, {'root': 1})),
            database_catalog=Mock(return_value={'targets': [
                {'target_id': 't1', 'display_name': 'shop.sqlite'}]})),
        resource_service=SimpleNamespace(list_page=Mock(
            return_value=SimpleNamespace(
                to_dict=lambda: {'generation': 'g-42'}))),
        sqlite_catalog=Mock(return_value=export),
        export_firebird_catalog=Mock(return_value=export))
    server = SimpleNamespace(
        name='Local SQLite',
        endpoint_profile=SimpleNamespace(profile_id=profile_id))
    return service, server


def test_catalog_diagram_returns_the_relations_and_their_regions(tmp_path):
    service, server = _service('sqlite-native', _sqlite_export(tmp_path))
    result = catalog_diagrams.catalog_diagram(
        service, server, {'database_target_id': 't1'})
    service.sqlite_catalog.assert_called_once_with(
        server, {'database_target_id': 't1'})
    assert result['engine'] == 'sqlite'
    assert result['database'] == {'id': 't1', 'name': 'shop.sqlite'}
    assert result['file'].startswith('objects/sqlite-')
    assert result['file'].endswith('.ddn')
    assert [item['name'] for item in result['relations']] == [
        'customer', 'purchase']
    schema = next(item for item in result['regions']
                  if item['role'] == 'schema')
    assert schema['name'] == 'main'
    assert {item['region'] for item in result['relations']} == {schema['id']}
    assert [item['role'] for item in result['regions']] == [
        'host', 'server', 'database', 'schema']
    assert result['regions'][1]['name'] == 'Local SQLite'
    assert 'relations.ddn' in result['snapshot']['files']


def test_firebird_reads_the_cached_generation_first(tmp_path):
    service, server = _service('firebird-embedded', _sqlite_export(tmp_path))
    catalog_diagrams.catalog_diagram(
        service, server, {'database_target_id': 't1'})
    service.export_firebird_catalog.assert_called_once_with(
        server, {'generation': 'g-42', 'database_target_id': 't1'})


@pytest.mark.parametrize('request_value', [
    None, {}, {'database_target_id': ''}, {'database_target_id': 3},
    {'database_target_id': 't1', 'resource_id': 'x'}])
def test_catalog_diagram_requests_are_exact(request_value, tmp_path):
    service, server = _service('sqlite-native', {})
    with pytest.raises(ValueError, match='Select a registered database'):
        catalog_diagrams.catalog_diagram(service, server, request_value)


def test_unsupported_engines_and_empty_catalogs_are_refused():
    service, server = _service('cockroachdb-native', {})
    with pytest.raises(ValueError, match='no catalog diagram'):
        catalog_diagrams.catalog_diagram(
            service, server, {'database_target_id': 't1'})
    service, server = _service('sqlite-native', {'diagram': None})
    with pytest.raises(ValueError, match='no tables or views'):
        catalog_diagrams.catalog_diagram(
            service, server, {'database_target_id': 't1'})
