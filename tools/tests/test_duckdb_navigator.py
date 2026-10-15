"""Native DuckDB catalogs must remain reachable from their actual tree parents."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.navigator import resource_children
from pgadmin.cdeadmin.providers.duckdb.provider import (
    DuckDBPilotProvider, _create_client, _resource_id,
)


def test_primary_file_schema_and_descendants_are_reachable(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    main, secondary = tmp_path / 'owned.duckdb', tmp_path / 'archive.duckdb'
    connection = duckdb.connect(str(main))
    connection.execute('CREATE TABLE facts(id INTEGER)')
    connection.execute('CREATE INDEX facts_id_ix ON facts(id)')
    connection.execute('CREATE SEQUENCE fact_seq')
    connection.execute("CREATE TYPE state AS ENUM ('ready', 'done')")
    connection.execute('CREATE VIEW fact_view AS SELECT id FROM facts')
    connection.close()
    connection = duckdb.connect(str(secondary))
    connection.execute('CREATE TABLE archived(id INTEGER)')
    connection.close()
    provider = DuckDBPilotProvider(
        SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(main), 'filesystem_root': str(tmp_path),
             'attached_databases': [{'name': 'archive', 'database': str(secondary),
                                     'read_only': True}]}
    try:
        resources = provider.capture_catalog(route, include_system=False)['resources']
        scope = {'database': str(main), 'display_name': main.name, 'target_id': 'owned'}

        def children(**state):
            return resource_children(resources, {**scope, **state})

        root = children(scope='database', parent_path=[])
        assert ('schema', 'Schemas') in [(item['resource_kind'], item['label'])
                                         for item in root]
        schemas = children(scope='kind', resource_kind='schema', parent_path=[])
        primary = next(item for item in schemas if item['label'] == 'main')
        assert primary['resource_id'] == _resource_id('schema', [main.stem], 'main')
        groups = children(scope='resource', resource_id=primary['resource_id'],
                          parent_path=['main'])
        assert {'table', 'view', 'sequence', 'type'} <= {
            item['resource_kind'] for item in groups}
        for kind, label in (('sequence', 'fact_seq'), ('type', 'state'),
                            ('view', 'fact_view')):
            actual = children(scope='kind', resource_kind=kind,
                              resource_id=primary['resource_id'], parent_path=['main'])
            assert label in [item['label'] for item in actual]
        tables = children(scope='kind', resource_kind='table',
                          resource_id=primary['resource_id'], parent_path=['main'])
        facts = next(item for item in tables if item['label'] == 'facts')
        table_groups = children(scope='resource', resource_id=facts['resource_id'],
                                parent_path=['main', 'facts'])
        assert 'index' in {item['resource_kind'] for item in table_groups}
        indexes = children(scope='kind', resource_kind='index',
                           resource_id=facts['resource_id'], parent_path=['main', 'facts'])
        assert 'facts_id_ix' in [item['label'] for item in indexes]
        attached = next(item for item in resources
                        if item['resource_kind'] == 'schema' and
                        item['display_path'] == ['archive', 'main'])
        assert attached['native']['navigator_parent_resource_id'] == (
            _resource_id('attached-database', [], 'archive'))
    finally:
        provider.client.close()
