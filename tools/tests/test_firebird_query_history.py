"""Persistent history isolation, retention and native-request independence."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import config  # Initialize application configuration before the ORM package.
from sqlalchemy import create_engine
from pgadmin.model import QueryHistoryModel
from pgadmin.cdeadmin.workspace.query_history import QueryHistory, HistoryScope, HistoryError
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceError


@pytest.fixture
def history(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'history.db'))
    QueryHistoryModel.__table__.create(engine)
    clock = [1000000]
    store = QueryHistory(engine, QueryHistoryModel, lambda: clock[0])
    yield store, clock
    engine.dispose()


SCOPE = HistoryScope(1, 2, 'registered-database', 3)
POLICY = dict(capture_source=True, retention_days=2, max_records=3)


def test_opt_in_persistence_and_scope_isolation(history):
    store, _ = history
    assert not store.record(SCOPE, 'select 1')['recorded']
    store.configure(SCOPE, POLICY)
    receipt = store.record(SCOPE, 'select ☃ from rdb$database')
    assert store.observation(SCOPE, receipt['entry_id'], 'accepted')
    reopened = QueryHistory(store.engine, QueryHistoryModel, store.clock)
    assert reopened.read(SCOPE)['entries'][0]['source'] == 'select ☃ from rdb$database'
    for other in [HistoryScope(2, 2, SCOPE.target, 3), HistoryScope(1, 3, SCOPE.target, 3),
                  HistoryScope(1, 2, 'other', 3), HistoryScope(1, 2, SCOPE.target, 1)]:
        assert not reopened.read(other)['entries']
        assert not reopened.observation(other, receipt['entry_id'], 'request-error')


def test_retention_search_clear_and_policy_preservation(history):
    store, clock = history
    store.configure(SCOPE, POLICY)
    for index in range(5):
        store.record(SCOPE, f'select {index}')
    assert [row['source'] for row in store.read(SCOPE)['entries']] == ['select 4', 'select 3', 'select 2']
    assert len(store.read(SCOPE, 'SELECT 3')['entries']) == 1
    clock[0] += 3 * 86400
    assert not store.read(SCOPE)['entries']
    store.record(SCOPE, 'select current_date')
    assert store.clear(SCOPE) == {'removed': 1}
    assert store.read(SCOPE)['policy'] == POLICY


@pytest.mark.parametrize('source,sensitive,reason', [
    ("create user alice password 'never store me'", False, 'Sensitive'),
    ('select confidential_literal', True, 'Sensitive'),
    ('☃' * 22000, False, '64 KiB'),
])
def test_source_omission(history, source, sensitive, reason):
    store, _ = history
    store.configure(SCOPE, POLICY)
    store.record(SCOPE, source, sensitive=sensitive)
    row = store.read(SCOPE)['entries'][0]
    assert row['source'] is None and reason in row['source_omitted_reason']


@pytest.mark.parametrize('values', [dict(POLICY, retention_days=True), dict(POLICY, max_records=1001),
                                      dict(POLICY, capture_source='true'), {}])
def test_invalid_policy(history, values):
    with pytest.raises(HistoryError):
        history[0].configure(SCOPE, values)


@pytest.mark.parametrize('record_fails,observation_fails', [(True, False), (False, True), (False, False)])
def test_history_failure_never_reexecutes_native_request(record_fails, observation_fails):
    history = Mock()
    history.record.return_value = {'recorded': True, 'entry_id': 'event'}
    if record_fails:
        history.record.side_effect = RuntimeError('store down')
    if observation_fails:
        history.observation.side_effect = RuntimeError('store down')
    service = object.__new__(ProviderWorkspaceService)
    service.query_history_factory = lambda: history
    service._history_context = Mock(return_value=SCOPE)
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='firebird-native'))
    execute = Mock(return_value={'occurrence_id': 'native-one'})
    result = service._record_query_request(server, SCOPE.target, 3, 'select 1', False, 'statement', execute)
    execute.assert_called_once_with()
    assert result['occurrence_id'] == 'native-one'
    assert bool(result['sql_history']['warning']) == (record_fails or observation_fails)


def test_rejected_script_is_not_recorded_as_prepared(history):
    store, _ = history
    store.configure(SCOPE, POLICY)
    service = object.__new__(ProviderWorkspaceService)
    service.query_history_factory = lambda: store
    service._history_context = Mock(return_value=SCOPE)
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='firebird-native'))
    service._record_query_request(server, SCOPE.target, 3, 'invalid syntax', False,
                                  'script-prepared', lambda: {'state': 'invalid'})
    assert store.read(SCOPE)['entries'][0]['request_state'] == 'preparation-rejected'


def test_host_scope_is_derived_from_authenticated_principal(history):
    store, _ = history
    service = object.__new__(ProviderWorkspaceService)
    service.query_history_factory = lambda: store
    service._principal_id = Mock(return_value=1)
    service.endpoint_service = Mock()
    service.endpoint_service.workspace.return_value = (None, {'route': {'database': 'native.fdb'}}, None)
    service.endpoint_service.database_catalog.return_value = {'targets': [
        {'target_id': SCOPE.target, 'database': 'native.fdb'}]}
    server = SimpleNamespace(id=2, endpoint_profile=SimpleNamespace(profile_id='firebird-native'))
    request = {'database_target_id': SCOPE.target, 'client_sql_dialect': 3}
    service.query_history_action(server, 'query_history_configure', dict(request, policy=POLICY))
    store.record(SCOPE, 'select 1')
    assert len(service.query_history_action(server, 'query_history_read', request)['entries']) == 1
    service._principal_id.return_value = 2
    assert service.query_history_action(server, 'query_history_read', request)['entries'] == []
    with pytest.raises(ProviderWorkspaceError):
        service.query_history_action(server, 'query_history_read', dict(request, owner=1))
    with pytest.raises(ProviderWorkspaceError):
        service.query_history_action(server, 'query_history_clear', request)
    service.endpoint_service.workspace.side_effect = PermissionError('target denied')
    with pytest.raises(PermissionError):
        service.query_history_action(server, 'query_history_read', request)


def test_native_error_is_preserved_when_history_observation_also_fails():
    service = object.__new__(ProviderWorkspaceService)
    history = Mock()
    history.record.return_value = {'recorded': True, 'entry_id': 'event'}
    history.observation.side_effect = RuntimeError('history unavailable')
    service.query_history_factory = lambda: history
    service._history_context = Mock(return_value=SCOPE)
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='firebird-native'))
    native_error = ValueError('native request rejected')
    execute = Mock(side_effect=native_error)
    with pytest.raises(ValueError) as raised:
        service._record_query_request(server, SCOPE.target, 3, 'select 1', False, 'statement', execute)
    assert raised.value is native_error
    execute.assert_called_once_with()



@pytest.mark.parametrize('source',["CONNECT 'remote:db' USER 'name' PASS 'test-only-credential';", "CREATE DATABASE 'newdb' USER 'name' PASS 'test-only-credential';"])
def test_connection_source_never_persists_abbreviated_credentials(history,source):
    store,_=history
    store.configure(SCOPE,POLICY)
    store.record(SCOPE,source,kind='script-prepared')
    assert store.read(SCOPE)['entries'][0]['source'] is None
    from sqlalchemy.orm import Session
    with Session(store.engine) as session:
        assert b'test-only-credential' not in b''.join(row.query_info for row in session.query(QueryHistoryModel).all())
