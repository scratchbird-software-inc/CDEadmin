"""MySQL history uses authorized database scope and never replays native work."""
from types import SimpleNamespace
from unittest.mock import Mock

import config
import pytest
from sqlalchemy import create_engine
from pgadmin.model import QueryHistoryModel
from pgadmin.cdeadmin.workspace.query_history import QueryHistory, HistoryScope, HistoryError
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError

SCOPE = HistoryScope(1, 2, 'mysql-target-a', 'mysql-sql', 'mysql')
POLICY = {'capture_source': True, 'retention_days': 2, 'max_records': 3}


@pytest.fixture
def store(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'history.db'))
    QueryHistoryModel.__table__.create(engine)
    yield QueryHistory(engine, QueryHistoryModel)
    engine.dispose()


def test_persistence_and_owner_server_database_engine_isolation(store):
    assert not store.record(SCOPE, 'SELECT 1')['recorded']
    store.configure(SCOPE, POLICY)
    entry = store.record(SCOPE, "SELECT 'é漢'", kind='script')
    store.observation(SCOPE, entry['entry_id'], 'accepted')
    reopened = QueryHistory(store.engine, QueryHistoryModel)
    assert reopened.read(SCOPE)['entries'][0]['source'] == "SELECT 'é漢'"
    assert reopened.read(SCOPE)['scope'] == {
        'database_target_id': SCOPE.target, 'engine_id': 'mysql', 'language_profile': 'mysql-sql'}
    for scope in (HistoryScope(2, 2, SCOPE.target, 'mysql-sql', 'mysql'),
                  HistoryScope(1, 3, SCOPE.target, 'mysql-sql', 'mysql'),
                  HistoryScope(1, 2, 'mysql-target-b', 'mysql-sql', 'mysql'),
                  HistoryScope(1, 2, SCOPE.target, 3, 'firebird'),
                  HistoryScope(1, 2, SCOPE.target, 'postgresql-sql', 'postgresql')):
        assert not reopened.read(scope)['entries']
        assert not reopened.observation(scope, entry['entry_id'], 'accepted')
    assert reopened.clear(SCOPE) == {'removed': 1}
    assert reopened.read(SCOPE)['policy'] == POLICY


@pytest.mark.parametrize('source', ["ALTER USER x IDENTIFIED BY 'private-value'",
    "CREATE USER x IDENTIFIED WITH caching_sha2_password AS 'private-hash'",
    "SELECT 'mysql://u:private@host/db'", "SELECT 'mysqlx://u:private@host/db'",
    "SET PASSWORD = 'private'", "SELECT 'token'"])
def test_credential_source_is_omitted(store, source):
    store.configure(SCOPE, POLICY)
    store.record(SCOPE, source)
    assert store.read(SCOPE)['entries'][0]['source'] is None


def test_host_requires_owned_target_and_mysql_language():
    service = object.__new__(ProviderWorkspaceService)
    service._principal_id = Mock(return_value=1)
    service.endpoint_service = Mock()
    service.endpoint_service.workspace.return_value = (
        SimpleNamespace(profile_id='mysql-native'), {'route': {'database': 'demo'}}, None)
    service.endpoint_service.database_catalog.return_value = {
        'targets': [{'target_id': SCOPE.target, 'database': 'demo'}]}
    server = SimpleNamespace(id=2, endpoint_profile=SimpleNamespace(profile_id='mysql-native'))
    assert service._history_context(server, SCOPE.target, None) == SCOPE
    for target, dialect in ((None, None), ('other', None), (SCOPE.target, 3)):
        with pytest.raises(ProviderWorkspaceError):
            service._history_context(server, target, dialect)
    service.endpoint_service.workspace.return_value[1]['route']['database'] = 'other'
    with pytest.raises(ProviderWorkspaceError): service._history_context(server, SCOPE.target, None)


def test_store_failure_cannot_block_or_replay_native_request():
    service = object.__new__(ProviderWorkspaceService)
    history = Mock(); history.record.side_effect = RuntimeError('store unavailable')
    service.query_history_factory = lambda: history
    service._history_context = Mock(return_value=SCOPE)
    execute = Mock(return_value={'occurrence_id': 'original'})
    result = service._record_query_request(
        SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='mysql-native')),
        SCOPE.target, None, 'SELECT 1', False, 'statement', execute)
    execute.assert_called_once_with()
    assert result['sql_history']['warning']


def test_invalid_native_language_refused(store):
    with pytest.raises(HistoryError): store.read(HistoryScope(1, 2, SCOPE.target, 3, 'mysql'))
