"""SQLite endpoint DDN bundles preserve independent registered file identities."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider, _create_client
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceError, ProviderWorkspaceService


def test_registered_files_have_independent_catalogs_and_missing_file(tmp_path):
    import sqlite3

    paths = {name: tmp_path / (name + '.sqlite') for name in ('first', 'second')}
    for name, path in paths.items():
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE same_name (value ' +
                               ('INTEGER' if name == 'first' else 'TEXT') + ')')
    provider = SQLiteProvider(SimpleNamespace(),
        SimpleNamespace(require=Mock()), _create_client())
    context = SimpleNamespace(profile_id='sqlite-native', endpoint_id='owned-endpoint')
    registered = [{'target_id': name, 'display_name': name, 'active': name == 'first'}
        for name in ('first', 'second', 'missing')]

    def workspace(_server, *, database_target_id):
        route = {'filesystem_root': str(tmp_path)}
        if database_target_id is not None:
            route['database'] = str(paths.get(database_target_id,
                                             tmp_path / 'missing.sqlite'))
        return context, {'route': route}, None

    service = object.__new__(ProviderWorkspaceService)
    service.endpoint_service = SimpleNamespace(workspace=workspace,
        database_catalog=lambda _server: {'endpoint_id': 'owned-endpoint',
            'multiple': True, 'targets': registered},
        provider_registry=SimpleNamespace(resolve=lambda _context:
            SimpleNamespace(instance=provider)))
    server = SimpleNamespace()
    try:
        inventory = service.sqlite_catalog(server, {})
        assert inventory['format'] == 'scratchrobin.sqlite.registered-files@1'
        assert [item['target_id'] for item in inventory['files']] == [
            'first', 'missing', 'second']
        bundle = service.sqlite_catalog(server, {'database_target_ids': [
            'first', 'second', 'missing'], 'include_system': False})
        assert bundle['format'] == 'scratchrobin.sqlite.registered-files-ddn@1'
        assert not bundle['all_selected_captured']
        assert [item['available'] for item in bundle['files']] == [True, True, False]
        assert 'document' not in bundle['files'][2]
        first, second = (item['document'] for item in bundle['files'][:2])
        assert first['provenance']['database_target_id'] == 'first'
        assert second['provenance']['database_target_id'] == 'second'
        assert first['snapshot']['files'] != second['snapshot']['files']
        overview = read_catalog(json.dumps(bundle['server']['document']['snapshot']),
                                engine='sqlite')
        assert sum(row['kind'] == 'database' for row in overview['rows'].values()) == 3
        for invalid in (['first', 'first'], ['foreign'], [], ['first'] * 33):
            with pytest.raises(ProviderWorkspaceError):
                service.sqlite_catalog(server, {'database_target_ids': invalid})
    finally:
        provider.client.close()
