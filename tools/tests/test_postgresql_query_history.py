"""PostgreSQL history ownership and native execution remain independent."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import config
from sqlalchemy import create_engine
from pgadmin.model import QueryHistoryModel
from pgadmin.cdeadmin.workspace.query_history import QueryHistory, HistoryScope, HistoryError
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError

SCOPE = HistoryScope(1, 2, 'postgresql-database:42', 'postgresql-sql', engine='postgresql')
POLICY = {'capture_source': True, 'retention_days': 2, 'max_records': 3}


@pytest.fixture
def store(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'history.db'))
    QueryHistoryModel.__table__.create(engine)
    yield QueryHistory(engine, QueryHistoryModel)
    engine.dispose()


def test_postgresql_persistence_does_not_share_firebird_or_other_owner_scope(store):
    assert not store.record(SCOPE, 'SELECT 1')['recorded']
    store.configure(SCOPE, POLICY)
    entry = store.record(SCOPE, "SELECT 'é漢'", kind='script-prepared')
    store.observation(SCOPE, entry['entry_id'], 'prepared')
    reopened = QueryHistory(store.engine, QueryHistoryModel)
    observed = reopened.read(SCOPE)
    assert observed['entries'][0]['source'] == "SELECT 'é漢'"
    assert observed['scope']['language_profile'] == 'postgresql-sql'
    for other in (HistoryScope(1, 2, SCOPE.target, 3),
                  HistoryScope(2, 2, SCOPE.target, 'postgresql-sql', 'postgresql'),
                  HistoryScope(1, 2, 'postgresql-database:43', 'postgresql-sql', 'postgresql')):
        assert not reopened.read(other)['entries']
        assert not reopened.observation(other, entry['entry_id'], 'accepted')
    assert reopened.clear(SCOPE) == {'removed': 1}
    assert reopened.read(SCOPE)['policy'] == POLICY


@pytest.mark.parametrize('source', ["ALTER ROLE x PASSWORD 'secret-value'", "SELECT 'postgresql://name:private@host/db'", "SELECT 'postgres://name:private@host/db'"])
def test_postgresql_credentials_are_not_retained(store, source):
    store.configure(SCOPE, POLICY)
    store.record(SCOPE, source)
    assert store.read(SCOPE)['entries'][0]['source'] is None


def test_native_target_and_language_are_host_selected(store):
    service = object.__new__(ProviderWorkspaceService)
    service.query_history_factory = lambda: store
    service._principal_id = Mock(return_value=1)
    service.endpoint_service = Mock()
    service.endpoint_service.workspace.return_value = (SimpleNamespace(profile_id='postgresql-native'), {}, None)
    server = SimpleNamespace(id=2, endpoint_profile=None)
    assert service._history_context(server, SCOPE.target, None) == SCOPE
    for target, dialect in ((None, None), ('postgresql-database:0', None), (SCOPE.target, 3)):
        with pytest.raises(ProviderWorkspaceError): service._history_context(server, target, dialect)
    with pytest.raises(ProviderWorkspaceError):
        service.query_history_action(server, 'query_history_read', {'database_target_id': SCOPE.target, 'owner': 2})
    with pytest.raises(HistoryError): store.read(HistoryScope(1, 2, SCOPE.target, 3, 'postgresql'))
    service.endpoint_service.workspace.side_effect = PermissionError('not connected')
    with pytest.raises(PermissionError): service._history_context(server, SCOPE.target, None)


def test_history_failure_does_not_replay_or_block_postgresql_execution():
    service = object.__new__(ProviderWorkspaceService)
    history = Mock(); history.record.side_effect = RuntimeError('store down')
    service.query_history_factory = lambda: history
    service._history_context = Mock(return_value=SCOPE)
    execute = Mock(return_value={'occurrence_id': 'original'})
    result = service._record_query_request(SimpleNamespace(endpoint_profile=None), SCOPE.target, None,
        'SELECT 1', False, 'statement', execute)
    execute.assert_called_once_with()
    assert result['occurrence_id'] == 'original' and result['sql_history']['warning']
