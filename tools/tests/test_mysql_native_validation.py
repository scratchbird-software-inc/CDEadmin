"""Private native PREPARE owns all parser commands and cleanup failures."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_mysql_session_variables import setup
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.providers.mysql_family.mysql_native_validation import validate


def owned(database='odd`雪'):
    source, observer, connect, peer, query = setup()
    variables = query.fetchall.return_value
    query.fetchall.side_effect = [variables, [(database,)]]
    query.fetchone.side_effect = [query.fetchone.return_value, ('9.7.0', 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES', 60)]
    client = SimpleNamespace(_uncertain_sessions=set())
    return source, observer, connect, peer, query, client


def test_native_prepare_uses_exact_observed_language_and_database_without_touching_source():
    source, observer, connect, peer, query, client = owned()
    result = validate(client, source, 'DROP TABLE "do not execute"')
    assert result['grammar_valid'] is True and result['authority'] == 'mysql-native-independent-prepare'
    assert result['original_session_commands_sent'] == 0 and result['original_diagnostics_preserved']
    assert result['original_session_catalog_binding_validated'] is False
    assert result['parser_observation']['default_schema'] == 'odd`雪'
    assert result['parser_observation']['thread_id'] == '52' and result['parser_observation']['connection_id'] == '12'
    assert peer.sql_mode == 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'
    commands = [call.args[0] for call in query.execute.call_args_list]
    assert 'USE `odd``雪`' in commands
    assert any(item.startswith('PREPARE sr_check_') for item in commands)
    assert not any(item.startswith(('EXECUTE ', 'COMMIT', 'ROLLBACK', 'DROP TABLE')) for item in commands)
    assert not client._uncertain_sessions
    source.cursor.assert_not_called(); peer.close.assert_not_called(); connect.assert_called_once()
    observer.close()


def test_database_scope_denial_never_falls_back_to_original_or_marks_it_unusable():
    from mysql.connector.errors import ProgrammingError
    source, observer, _connect, peer, query, client = owned()
    def execute(sql, *_args):
        if 'performance_schema.threads' in sql:
            raise ProgrammingError('private context denied', errno=1142)
    query.execute.side_effect = execute
    with pytest.raises(RelationalClientError, match='no original-session metadata command'):
        validate(client, source, 'SELECT 1')
    source.cursor.assert_not_called(); peer.close.assert_called_once()
    assert observer.needs_connection_refresh and observer.connection is None and not client._uncertain_sessions


def test_lost_private_prepared_release_quarantines_only_the_private_peer(monkeypatch):
    source, observer, _connect, peer, _query, client = owned()
    def fail(_client, handle, *_args):
        assert handle is peer
        client._uncertain_sessions.add(id(peer))
        raise RelationalClientError('source-bearing private release fault')
    monkeypatch.setattr('pgadmin.cdeadmin.providers.native_editor.validate_mysql', fail)
    with pytest.raises(RelationalClientError) as error:
        validate(client, source, 'SELECT secret')
    assert 'source-bearing' not in str(error.value) and 'secret' not in str(error.value)
    assert not client._uncertain_sessions and observer.needs_connection_refresh
    source.cursor.assert_not_called(); peer.close.assert_called_once()


def test_missing_original_identity_blocks_validation_and_requires_source_closure():
    source, observer, connect, _peer, _query, client = owned()
    source.connection_id = 13
    with pytest.raises(RelationalClientError, match='original MySQL session identity is unconfirmed'):
        validate(client, source, 'SELECT 1')
    assert id(source) in client._uncertain_sessions
    source.cursor.assert_not_called(); connect.assert_not_called(); observer.close()


def test_missing_exact_database_thread_preserves_identity_failure_during_peer_cleanup():
    source, observer, _connect, peer, query, client = owned()
    query.fetchall.side_effect = [query.fetchall.return_value, []]
    with pytest.raises(RelationalClientError, match='original MySQL session identity is unconfirmed'):
        validate(client, source, 'SELECT 1')
    assert id(source) in client._uncertain_sessions and observer.needs_connection_refresh
    source.cursor.assert_not_called(); peer.close.assert_called_once()


def test_empty_original_database_renews_only_a_previously_selected_private_peer(monkeypatch):
    source, observer, connect, old, query, client = owned(None)
    variables = query.fetchall.return_value
    query.fetchall.side_effect = [variables, [(None,)]]
    fresh = Mock(); fresh_query = Mock()
    fresh_query.fetchone.return_value = observer.identity['server_uuid'], observer.identity['principal_hex'], '9.7.0'
    fresh_query.fetchall.return_value = variables; fresh.cursor.return_value = fresh_query
    connect.side_effect = [old, fresh]
    observer.parser_database = 'previous private database'
    # Establish the existing owned peer first; opening a new peer correctly
    # initializes its tracked database to empty.
    observer.observe(); observer.parser_database = 'previous private database'
    query.fetchall.side_effect = [variables, [(None,)]]
    query.fetchone.side_effect = [tuple(observer.identity[key] for key in ('server_uuid', 'principal_hex', 'version'))]
    def checked(_client, handle, *_args):
        assert handle is fresh
        return {'parser_version': '9.7.0', 'sql_mode': variables[-1][1], 'grammar_valid': True}
    monkeypatch.setattr('pgadmin.cdeadmin.providers.native_editor.validate_mysql', checked)
    assert validate(client, source, 'SELECT 1')['original_diagnostics_preserved']
    assert observer.connection is fresh and observer.parser_database is None
    assert connect.call_count == 2
    source.cursor.assert_not_called(); old.close.assert_called_once(); observer.close()


def test_a_connector_returning_the_original_native_thread_is_rejected_before_commands():
    source, observer, _connect, peer, query = setup()
    peer.connection_id = source.connection_id
    with pytest.raises(RelationalClientError, match='different native connection'):
        observer.observe()
    query.execute.assert_not_called(); peer.close.assert_not_called(); source.cursor.assert_not_called()
    observer.close(); peer.close.assert_not_called()
