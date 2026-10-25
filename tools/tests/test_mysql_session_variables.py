"""Independent MySQL metadata must never mutate the original diagnostic area."""
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.providers.mysql_family.mysql_session_variables import (
    SessionVariables, ObserverUnavailable, observe, invalidate, install, prepare, uninstall,
)
from pgadmin.cdeadmin.providers.mysql_family.mysql_values import MySQLParameterAdmissionError


class Source:
    connection_id = 12
    server_host = 'native-host'
    server_port = 3306
    unix_socket = None


def setup():
    source = Source()
    source.cursor = Mock(side_effect=AssertionError('Original-session SQL was dispatched'))
    identity = {'server_uuid': 'original-cluster', 'connection_id': 12,
                'principal_hex': b'user@%'.hex().upper(), 'version': '9.7.0', 'thread_id': 52}
    attribute = {'name': 'scratchrobin_exact', 'value': 'a' * 48}
    query = Mock()
    query.fetchone.return_value = tuple(identity[key] for key in ('server_uuid', 'principal_hex', 'version'))
    query.fetchall.return_value = [('character_set_client', 'latin1'), ('character_set_connection', 'latin1'),
        ('character_set_results', ''), ('collation_connection', 'latin1_general_cs'),
        ('sql_mode', 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES')]
    connection = Mock()
    connection.cursor.return_value = query
    connector = Mock(return_value=connection)
    observer = SessionVariables(source, connector, identity, attribute)
    source._cdeadmin_session_variable_observer = observer
    return source, observer, connector, connection, query


def test_exact_thread_and_handshake_nonce_bind_a_complete_independent_observation():
    source, observer, connect, connection, query = setup()
    result = observe(source)
    assert result['original_session_commands_sent'] == 0
    assert result['variables']['character_set_results'] is None
    assert result['variables']['sql_mode'] == 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'
    assert query.execute.call_args_list[-1].args[1] == (12, 'scratchrobin_exact', 'a' * 48, 52)
    source.cursor.assert_not_called()
    query.close.assert_called_once(); connection.close.assert_not_called()
    result['variables']['sql_mode'] = 'caller mutation'
    assert observe(source)['variables']['sql_mode'] != 'caller mutation'
    assert connect.call_count == 1
    invalidate(source)
    assert connect.call_count == 1
    assert observe(source)['variables']['sql_mode'] == 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'
    assert connect.call_count == 1 and query.close.call_count == 2
    uninstall(source)
    connection.close.assert_called_once()


@pytest.mark.parametrize('column,value', [(0, 'another cluster'), (1, 'another principal'), (2, '9.7.1')])
def test_another_native_peer_is_rejected_before_its_session_variables_are_read(column, value):
    source, observer, _connect, connection, query = setup()
    peer = list(query.fetchone.return_value); peer[column] = value; query.fetchone.return_value = tuple(peer)
    with pytest.raises(ObserverUnavailable, match='another native peer'):
        observer.observe()
    assert query.execute.call_count == 1
    query.fetchall.assert_not_called(); source.cursor.assert_not_called()
    observer.close(); connection.close.assert_called_once()


@pytest.mark.parametrize('rows', [[], [('sql_mode', '')],
    [('character_set_client', 'latin1'), ('character_set_client', 'latin1')],
    [('sql_mode', 'lowercase')], [('sql_mode', 'A' * 4097)],
    [('character_set_client', 'utf8mb4;SELECT')], [('unknown', 'native')]])
def test_partial_ambiguous_or_invalid_variable_sets_never_become_current_language(rows):
    source, observer, _connect, connection, query = setup()
    query.fetchall.return_value = rows
    with pytest.raises(ObserverUnavailable):
        observer.observe()
    assert observer.cached is None and observer.last_observation is None
    source.cursor.assert_not_called()
    observer.close(); connection.close.assert_called_once()


def test_changed_original_handle_never_reconnects_or_borrows_another_threads_settings():
    source, observer, connect, _connection, query = setup()
    source.connection_id = 13
    with pytest.raises(ObserverUnavailable, match='original MySQL session identity changed'):
        observer.observe()
    connect.assert_not_called()
    source.connection_id = 12
    original_fetch = query.fetchall
    def fetch():
        source.connection_id = 13
        return original_fetch.return_value
    query.fetchall.side_effect = fetch
    with pytest.raises(ObserverUnavailable, match='changed during'):
        observer.observe()
    assert observer.cached is None


def test_missing_exact_source_identity_is_distinct_from_an_observer_transport_or_permission_failure():
    from pgadmin.cdeadmin.providers.mysql_family.mysql_execution import Executions
    source, _observer, _connect, _connection, query = setup()
    query.fetchall.return_value = []
    with pytest.raises(MySQLParameterAdmissionError) as caught:
        observe(source)
    assert caught.value.original_session_identity_unconfirmed
    assert not caught.value.original_diagnostics_preserved
    result = Executions._error(caught.value)
    assert result['original_session_identity_unconfirmed']
    assert result['commands_dispatched'] == 0 and 'close this session' in result['message_primary']
    assert query.execute.call_args_list[-1].args[1] == (12, 'scratchrobin_exact', 'a' * 48)
    source.cursor.assert_not_called()


def test_revocation_after_admission_preserves_original_diagnostics_and_refuses_current_command_without_fallback():
    from mysql.connector.errors import ProgrammingError
    source, observer, connect, _connection, query = setup()
    observe(source); invalidate(source)
    query.execute.side_effect = ProgrammingError('private observer denied', errno=1142, sqlstate='42000')
    with pytest.raises(MySQLParameterAdmissionError) as error:
        observe(source)
    assert error.value.native_observer_errno == 1142
    assert error.value.original_diagnostics_preserved and error.value.commands_dispatched == 0
    assert not observer.needs_connection_refresh
    prepare(source)
    assert connect.call_count == 1
    query.execute.side_effect = None
    assert observe(source)['variables']['sql_mode'] == 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'
    source.cursor.assert_not_called()


def test_observer_loss_never_reconnects_in_worker_and_authenticated_prepare_renews_only_private_connection():
    from mysql.connector.errors import OperationalError
    source, observer, connect, connection, query = setup()
    observe(source); invalidate(source)
    query.execute.side_effect = OperationalError('observer disconnected', errno=2013)
    for _ in range(2):
        with pytest.raises(MySQLParameterAdmissionError):
            observe(source)
    assert connect.call_count == 1 and observer.needs_connection_refresh
    query.execute.side_effect = None
    prepare(source)
    assert connect.call_count == 2 and not observer.needs_connection_refresh
    connection.close.assert_called_once()
    assert observe(source)['original_session_commands_sent'] == 0
    source.cursor.assert_not_called()


def test_failed_authenticated_renewal_cannot_shift_credential_acquisition_to_execution_worker():
    source, observer, connect, _connection, _query = setup()
    observe(source)
    observer.needs_connection_refresh = True
    connect.side_effect = RelationalClientError('authenticated credential acquisition failed')
    with pytest.raises(RelationalClientError):
        prepare(source)
    assert observer.needs_connection_refresh and observer.opened
    for _ in range(2):
        with pytest.raises(MySQLParameterAdmissionError):
            observe(source)
    assert connect.call_count == 2
    connect.side_effect = None
    prepare(source)
    assert connect.call_count == 3 and not observer.needs_connection_refresh
    source.cursor.assert_not_called()


def test_local_charset_cache_is_updated_from_the_same_observed_native_variable_set():
    source, _observer, _connect, _connection, _query = setup()
    source._cdeadmin_charset_variables = dict.fromkeys(('character_set_client', 'character_set_connection', 'character_set_results'))
    source._cdeadmin_sync_charset = Mock()
    observe(source)
    assert source._cdeadmin_charset_variables == {'character_set_client': 'latin1',
        'character_set_connection': 'latin1', 'character_set_results': None}
    source._cdeadmin_sync_charset.assert_called_once_with()


def test_pool_release_detaches_observer_and_status_without_changing_physical_handshake_identity():
    source, _observer, _connect, connection, _query = setup()
    observe(source)
    source._cdeadmin_observer_attribute = {'name': 'handshake identity', 'value': 'retained by physical connection'}
    source._cdeadmin_session_variable_observer_status = {'admitted': True}
    uninstall(source)
    assert not hasattr(source, '_cdeadmin_session_variable_observer')
    assert not hasattr(source, '_cdeadmin_session_variable_observer_status')
    assert source._cdeadmin_observer_attribute['name'] == 'handshake identity'
    connection.close.assert_called_once()


@pytest.mark.parametrize('enabled,errno', [(0, None), (1, 1142)])
def test_disabled_or_denied_observer_admission_remains_explicitly_unqualified(enabled, errno):
    from mysql.connector.errors import ProgrammingError
    source, _observer, _connect, _connection, _query = setup()
    uninstall(source)
    source._cdeadmin_observer_attribute = {'name': 'exact', 'value': 'nonce'}
    cursor = Mock()
    cursor.fetchone.return_value = ('original-cluster', 12, '757365724025', '9.7.0', enabled, 52 if enabled else None)
    source.cursor = Mock(return_value=cursor)
    class Client:
        pass
    client = Client()
    if errno:
        client._invoke_connector = Mock(side_effect=ProgrammingError('denied', errno=errno, sqlstate='42000'))
        client.module = Mock(); client.config = Mock()
    install(client, source, {'route': 'exact'})
    status = source._cdeadmin_session_variable_observer_status
    assert not status['admitted'] and status['original_observation_path_qualified'] is False
    assert status['admission_observation_only'] is True
    assert not hasattr(source, '_cdeadmin_session_variable_observer')
    if errno:
        assert status['native_errno'] == errno


def test_denied_editor_candidate_is_readmitted_without_any_source_command_and_released():
    from types import SimpleNamespace
    from pgadmin.cdeadmin.providers.mysql_family.mysql_session_variables import editor_observer
    source,observer,connect,peer,_query=setup()
    del source._cdeadmin_session_variable_observer
    source._cdeadmin_session_variable_observer_candidate=observer
    source._cdeadmin_session_variable_observer_status={'admitted':False,'native_errno':1142}
    observer.close()
    selected=editor_observer(SimpleNamespace(_uncertain_sessions=set()),source)
    assert selected is observer and source._cdeadmin_session_variable_observer is observer
    assert not hasattr(source,'_cdeadmin_session_variable_observer_candidate')
    assert source._cdeadmin_session_variable_observer_status['readmitted_without_source_commands']
    assert source._cdeadmin_session_variable_observer_status['connection_id']=='12'
    source.cursor.assert_not_called();connect.assert_called_once()
    uninstall(source);peer.close.assert_called_once()


def test_failed_editor_readmission_preserves_denial_and_pool_release_forgets_candidate():
    from types import SimpleNamespace
    from mysql.connector.errors import ProgrammingError
    from pgadmin.cdeadmin.providers.mysql_family.mysql_session_variables import editor_observer
    source,observer,connect,_peer,_query=setup()
    del source._cdeadmin_session_variable_observer
    source._cdeadmin_session_variable_observer_candidate=observer
    source._cdeadmin_session_variable_observer_status={'admitted':False}
    connect.side_effect=ProgrammingError('private source-bearing detail',errno=1142,sqlstate='42000')
    with pytest.raises(RelationalClientError) as failure:editor_observer(SimpleNamespace(_uncertain_sessions=set()),source)
    assert failure.value.native_observer_errno==1142 and 'private source-bearing detail' not in str(failure.value)
    assert source._cdeadmin_session_variable_observer_status['native_errno']==1142
    assert not hasattr(source,'_cdeadmin_session_variable_observer')
    source.cursor.assert_not_called()
    uninstall(source);assert not hasattr(source,'_cdeadmin_session_variable_observer_candidate')


@pytest.mark.parametrize('reason', ['performance-schema-disabled', 'native-observer-admission-denied', None])
def test_unadmitted_language_never_falls_back_to_the_original_diagnostic_area(reason):
    from pgadmin.cdeadmin.providers.mysql_family.mysql_values import observed_language
    from pgadmin.cdeadmin.providers.mysql_family.mysql_execution import Executions
    source=Source();source.cursor=Mock(side_effect=AssertionError('Original-session metadata dispatched'))
    source._cdeadmin_session_variable_observer_status={'admitted':False,'reason':reason,'native_errno':1142}
    with pytest.raises(MySQLParameterAdmissionError) as failure:observed_language(source)
    assert failure.value.commands_dispatched==0
    assert failure.value.original_diagnostics_preserved and failure.value.original_session_commands_sent==0
    source.cursor.assert_not_called()
    result=Executions._error(failure.value)
    assert result['original_diagnostics_preserved'] and result['commands_dispatched']==0
    assert result['native_observer_errno']==1142
    assert 'No original-session metadata command' in result['message_primary']
    if reason=='performance-schema-disabled':assert 'reviewed restart' in result['message_primary']
    if reason=='native-observer-admission-denied':assert 'After restoring access' in result['message_primary']


def test_authenticated_execution_readmits_a_denied_candidate_without_source_commands():
    source,observer,connect,_peer,_query=setup()
    del source._cdeadmin_session_variable_observer
    source._cdeadmin_session_variable_observer_candidate=observer
    source._cdeadmin_session_variable_observer_status={'admitted':False,'reason':'native-observer-admission-denied'}
    observer.close()
    prepare(source)
    assert source._cdeadmin_session_variable_observer is observer
    assert source._cdeadmin_session_variable_observer_status['readmitted_without_source_commands']
    assert not hasattr(source,'_cdeadmin_session_variable_observer_candidate')
    source.cursor.assert_not_called();connect.assert_called_once()


def test_failed_execution_readmission_does_not_expose_native_text_or_try_from_the_worker():
    from mysql.connector.errors import ProgrammingError
    from pgadmin.cdeadmin.providers.mysql_family.mysql_values import observed_language
    source,observer,connect,_peer,_query=setup()
    del source._cdeadmin_session_variable_observer
    source._cdeadmin_session_variable_observer_candidate=observer
    source._cdeadmin_session_variable_observer_status={'admitted':False,'reason':'native-observer-admission-denied'}
    connect.side_effect=ProgrammingError('private source-bearing detail',errno=1142,sqlstate='42000')
    prepare(source)
    for _ in range(2):
        with pytest.raises(MySQLParameterAdmissionError) as failure:observed_language(source)
        assert 'private source-bearing detail' not in str(failure.value)
    assert connect.call_count==1
    source.cursor.assert_not_called()


def test_retained_runtime_identity_is_bound_to_admitted_native_connection_without_version_queries():
    from types import SimpleNamespace
    from pgadmin.cdeadmin.providers.mysql_family.provider import MySQLDBAPIClient
    from pgadmin.cdeadmin.providers.mysql_family.session_state import SessionIdentities
    source=Source();source.cursor=Mock(side_effect=AssertionError('Original VERSION query dispatched'))
    identity={'engine_id':'mysql','version':'9.7.0','build_id':'mysql:9.7.0','protocol_id':'mysql-wire'}
    source._cdeadmin_admitted_runtime_identity=dict(identity)
    sessions=SessionIdentities('MySQL');sessions.entries[id(source)]=(source,'native-server',12)
    client=object.__new__(MySQLDBAPIClient);client._session_requests={id(source):{}}
    client._executions=SimpleNamespace(sessions=sessions)
    result=client.runtime_identity({},source)
    assert result==identity
    result['version']='caller mutation'
    assert client.runtime_identity({},source)==identity
    source.connection_id=13
    with pytest.raises(RelationalClientError,match='identity changed'):client.runtime_identity({},source)
    source.cursor.assert_not_called()
    uninstall(source)
    assert not hasattr(source,'_cdeadmin_admitted_runtime_identity')
