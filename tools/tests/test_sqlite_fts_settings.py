"""Native configuration-only FTS designs retain content, receipts and outcomes."""
from contextlib import closing
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider, _create_client, _resource_id
from pgadmin.cdeadmin.providers.sqlite.fts_configuration import capture
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceError
from test_sqlite_schema_virtual_creation import Context, workspace

CASES = [(module, failure) for module in ('fts4', 'fts5')
         for failure in (None, 'stale', 'rollback', 'denied', 'lost_commit', 'postimage', 'busy')]
CASES += [('fts3', None)]


@pytest.mark.parametrize('module,failure', CASES)
def test_native_fts_configuration_review_application_and_once_only_outcomes(tmp_path, monkeypatch, module, failure):
    path = tmp_path / 'settings.sqlite'; name = 'search:雪'; quoted = '"' + name + '"'
    with closing(sqlite3.connect(path)) as seed:
        seed.execute('CREATE VIRTUAL TABLE ' + quoted + ' USING ' + module + '(body)')
        seed.executemany('INSERT INTO ' + quoted + '(rowid,body) VALUES(?,?)', [(1, 'native token'), (9007199254740993, 'native 雪 token')])
        seed.execute('CREATE TABLE pending(value INTEGER)'); seed.commit()
        original = capture(seed, 'main', name, module)
    provider = SQLiteProvider(Context(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path), 'timeout': .05}
    try:
        service = workspace(tmp_path, provider, route)
        exported = service.sqlite_catalog('owned', {'database_target_id': 'file', 'include_system': False})
        baseline = json.dumps(exported['snapshot']); resource_id = _resource_id('fts-table', ['main'], name)
        settings = {'automerge': '8', 'usermerge': 4, 'crisismerge': 10, 'deletemerge': 11,
                    'pgsz': 1024, 'hashsize': 16384, 'rank': 'bm25(2.0)', 'secure-delete': 1, 'insttoken': 1} if module == 'fts5' else {'automerge': 8}
        generated = service.sqlite_fts_configuration_design('owned', {'database_target_id': 'file',
            'baseline': baseline, 'resource_id': resource_id, 'settings': settings})
        desired = read_catalog(json.dumps(generated['snapshot']), engine='sqlite')
        expected = desired['rows'][resource_id]['native']['fts_configuration']
        assert dict(expected['commands'])['automerge'] == 8
        with closing(sqlite3.connect(path)) as observer:
            assert capture(observer, 'main', name, module) == original
        request = {'database_target_id': 'file', 'baseline': baseline, 'desired': json.dumps(generated['snapshot'])}
        displayed = service.sqlite_schema_plan('owned', request)
        assert displayed['ready_for_review'], displayed
        assert displayed['operations'][0]['operation'] == 'fts-configure'
        reviewed = service.sqlite_schema_application('owned', 'sqlite_schema_review', {**request, 'execution_sha256': displayed['execution_sha256']})
        apply_request = {'database_target_id': 'file', 'review_id': reviewed['review_id'],
                         'review_digest': reviewed['review_digest'], 'confirmed': True}
        if failure == 'stale':
            with closing(sqlite3.connect(path)) as observer:
                observer.execute('INSERT INTO ' + quoted + '(' + quoted + (",rank) VALUES('automerge',6)" if module == 'fts5' else ") VALUES('automerge=6')")); observer.commit()
                original = capture(observer, 'main', name, module)
        connect = provider.client._connect
        if failure in {'rollback', 'denied', 'lost_commit'}:
            class Injected:
                def __init__(self, connection):
                    self.connection = connection
                    if failure == 'denied':
                        connection.set_authorizer(lambda action, *_args: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT else sqlite3.SQLITE_OK)
                def __getattr__(self, key): return getattr(self.connection, key)
                def execute(self, source, *args):
                    result = self.connection.execute(source, *args)
                    if failure == 'rollback' and source.startswith('INSERT INTO "main".' + quoted):
                        self.connection.execute('SELECT * FROM owned_missing_native_relation')
                    return result
                def commit(self):
                    self.connection.commit()
                    if failure == 'lost_commit': raise ConnectionError('Owned missing reply after actual native FTS configuration commit')
            provider.client._connect = Mock(side_effect=lambda payload: Injected(connect(payload)))
        if failure == 'postimage':
            from pgadmin.cdeadmin.providers.sqlite import fts_configuration
            actual = fts_configuration.capture
            def wrong(connection, schema, table, mod):
                value = actual(connection, schema, table, mod)
                if table == name and dict(value.get('commands', [])).get('automerge') == 8:
                    value = deepcopy(value); value['commands'] = [['automerge', 6]]
                return value
            monkeypatch.setattr(fts_configuration, 'capture', wrong)
        if failure == 'busy':
            writer = sqlite3.connect(path)
            try:
                writer.execute('INSERT INTO pending VALUES(99)'); writer.execute('SAVEPOINT retained')
                result = service.sqlite_schema_application('owned', 'sqlite_schema_apply', apply_request)
                assert writer.in_transaction and writer.execute('SELECT * FROM pending').fetchall() == [(99,)]
                writer.execute('ROLLBACK TO retained'); writer.rollback()
            finally: writer.close()
        else:
            result = service.sqlite_schema_application('owned', 'sqlite_schema_apply', apply_request)
        state = ('not_dispatched' if failure in {'stale', 'busy'} else 'rolled_back' if failure in {'rollback', 'denied', 'postimage'}
                 else 'unknown_outcome' if failure == 'lost_commit' else 'committed')
        assert result['state'] == state, result
        provider.client._connect = Mock(side_effect=AssertionError('Native FTS configuration was replayed'))
        assert service.sqlite_schema_application('owned', 'sqlite_schema_apply', apply_request)['state'] == state
        provider.client._connect.assert_not_called()
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT rowid,body FROM ' + quoted + ' WHERE ' + quoted + " MATCH 'native' ORDER BY rowid").fetchall() == [(1, 'native token'), (9007199254740993, 'native 雪 token')]
            assert capture(observer, 'main', name, module)['commands'] == (expected if failure in {None, 'lost_commit'} else original)['commands']
            assert observer.execute('SELECT * FROM pending').fetchall() == []
    finally:
        provider.client._connect = connect if 'connect' in locals() else provider.client._connect
        provider.close()


def test_native_fts_settings_refusal_and_private_row_deletion_are_not_silent_resets(tmp_path):
    path = tmp_path / 'settings.sqlite'
    with closing(sqlite3.connect(path)) as seed:
        seed.execute('CREATE VIRTUAL TABLE search USING fts5(body)')
        seed.execute("INSERT INTO search(search,rank) VALUES('automerge',4)"); seed.commit()
    provider = SQLiteProvider(Context(), SimpleNamespace(require=Mock()), _create_client())
    try:
        route = {'database': str(path), 'filesystem_root': str(tmp_path)}; service = workspace(tmp_path, provider, route)
        baseline = json.dumps(service.sqlite_catalog('owned', {'database_target_id': 'file', 'include_system': False})['snapshot'])
        request = {'database_target_id': 'file', 'baseline': baseline, 'resource_id': _resource_id('fts-table', ['main'], 'search')}
        for settings in [{'rank': 'bm25('}, {'unavailable_native_command': 1}]:
            with pytest.raises(ProviderWorkspaceError):
                service.sqlite_fts_configuration_design('owned', {**request, 'settings': settings})
        model = read_catalog(baseline, engine='sqlite'); wanted = deepcopy(model['rows'][request['resource_id']])
        wanted['native']['fts_configuration']['commands'] = []
        from pgadmin.cdeadmin.workspace.sqlite_fts_settings import plan
        with pytest.raises(ValueError, match='reset using explicit'):
            plan(model['rows'][request['resource_id']], wanted)
        with closing(sqlite3.connect(path)) as observer:
            assert capture(observer, 'main', 'search', 'fts5')['commands'] == [['automerge', 4]]
    finally: provider.close()


def test_configuration_generation_preserves_observed_secure_delete_index_format(tmp_path):
    path = tmp_path / 'format.sqlite'
    with closing(sqlite3.connect(path)) as seed:
        seed.execute('CREATE VIRTUAL TABLE search USING fts5(body)')
        seed.execute("INSERT INTO search(search,rank) VALUES('secure-delete',1)")
        seed.execute("INSERT INTO search VALUES('removed token')"); seed.execute('DELETE FROM search')
        seed.execute("INSERT INTO search VALUES('retained token')"); seed.commit()
        original = capture(seed, 'main', 'search', 'fts5')
        assert original['native_format_version'] == 5
    provider = SQLiteProvider(Context(), SimpleNamespace(require=Mock()), _create_client())
    try:
        route = {'database': str(path), 'filesystem_root': str(tmp_path)}; service = workspace(tmp_path, provider, route)
        baseline = json.dumps(service.sqlite_catalog('owned', {'database_target_id': 'file', 'include_system': False})['snapshot'])
        resource_id = _resource_id('fts-table', ['main'], 'search')
        generated = service.sqlite_fts_configuration_design('owned', {'database_target_id': 'file', 'baseline': baseline,
            'resource_id': resource_id, 'settings': {'automerge': 8}})
        desired = read_catalog(json.dumps(generated['snapshot']), engine='sqlite')
        assert desired['rows'][resource_id]['native']['fts_configuration']['native_format_version'] == 5
        with closing(sqlite3.connect(path)) as observer:
            assert capture(observer, 'main', 'search', 'fts5') == original
    finally: provider.close()
