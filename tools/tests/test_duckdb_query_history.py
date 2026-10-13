"""Persistent DuckDB SQL history is target scoped and never replays native work."""

from types import SimpleNamespace
from unittest.mock import Mock

import config  # noqa: F401
import pytest
from sqlalchemy import create_engine
from pgadmin.model import QueryHistoryModel
from pgadmin.cdeadmin.workspace.query_history import QueryHistory, HistoryScope, HistoryError
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError


SCOPE = HistoryScope(1, 2, 'duckdb-file-a', 'duckdb-sql', 'duckdb')
POLICY = {'capture_source': True, 'retention_days': 2, 'max_records': 3}


@pytest.fixture
def store(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'history.db'))
    QueryHistoryModel.__table__.create(engine)
    yield QueryHistory(engine, QueryHistoryModel)
    engine.dispose()


def test_history_persists_in_target_scope_with_request_state_only(store):
    assert not store.record(SCOPE, 'SELECT 1')['recorded']
    store.configure(SCOPE, POLICY)
    result = store.record(SCOPE, 'SELECT 42', kind='script')
    store.observation(SCOPE, result['entry_id'], 'accepted')
    reopened = QueryHistory(store.engine, QueryHistoryModel)
    current = reopened.read(SCOPE)
    assert current['entries'][0]['source'] == 'SELECT 42'
    assert current['entries'][0]['request_state'] == 'accepted'
    assert current['scope'] == {'database_target_id': SCOPE.target,
        'engine_id': 'duckdb', 'language_profile': 'duckdb-sql'}
    for other in (HistoryScope(2, 2, SCOPE.target, 'duckdb-sql', 'duckdb'),
                  HistoryScope(1, 2, 'duckdb-file-b', 'duckdb-sql', 'duckdb'),
                  HistoryScope(1, 2, SCOPE.target, 'mysql-sql', 'mysql')):
        assert not reopened.read(other)['entries']
    assert reopened.clear(SCOPE) == {'removed': 1}


@pytest.mark.parametrize('source', [
    "CREATE SECRET native_secret (TYPE S3, KEY_ID 'private')",
    "ATTACH 'postgres://user:private@host/db' AS foreign_catalog",
    "ATTACH 'local.duckdb' AS catalog",
    "SELECT 'password'",
])
def test_secret_and_attach_sources_are_omitted(store, source):
    store.configure(SCOPE, POLICY)
    store.record(SCOPE, source)
    assert store.read(SCOPE)['entries'][0]['source'] is None


def test_host_requires_exact_registered_file_and_language():
    service = object.__new__(ProviderWorkspaceService)
    service._principal_id = Mock(return_value=1)
    service.endpoint_service = Mock()
    service.endpoint_service.workspace.return_value = (
        SimpleNamespace(profile_id='duckdb-native'), {'route': {'database': '/owned/file.duckdb'}}, None)
    service.endpoint_service.database_catalog.return_value = {
        'targets': [{'target_id': SCOPE.target, 'database': '/owned/file.duckdb'}]}
    server = SimpleNamespace(id=2, endpoint_profile=SimpleNamespace(profile_id='duckdb-native'))
    assert service._history_context(server, SCOPE.target, None) == SCOPE
    for target, dialect in ((None, None), ('foreign', None), (SCOPE.target, 3)):
        with pytest.raises(ProviderWorkspaceError): service._history_context(server, target, dialect)
    service.endpoint_service.workspace.return_value[1]['route']['database'] = '/other/file.duckdb'
    with pytest.raises(ProviderWorkspaceError): service._history_context(server, SCOPE.target, None)


def test_store_failure_cannot_replay_native_execution():
    service = object.__new__(ProviderWorkspaceService)
    history = Mock(); history.record.side_effect = RuntimeError('store unavailable')
    service.query_history_factory = lambda: history
    service._history_context = Mock(return_value=SCOPE)
    execute = Mock(return_value={'occurrence_id': 'original'})
    result = service._record_query_request(
        SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='duckdb-native')),
        SCOPE.target, None, 'SELECT 1', False, 'statement', execute)
    execute.assert_called_once_with()
    assert result['sql_history']['warning']


def test_wrong_duckdb_dialect_is_refused(store):
    with pytest.raises(HistoryError):
        store.read(HistoryScope(1, 2, SCOPE.target, 3, 'duckdb'))
