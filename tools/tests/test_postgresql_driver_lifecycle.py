"""Retained provider ownership and unknown-outcome regressions."""
import threading
import time
from unittest.mock import Mock, patch

import pytest

from test_cdeadmin_postgresql_provider import (
    FakeDriver, FakePermissions, PostgreSQLProvider, endpoint,
)
from pgadmin.cdeadmin.providers.postgresql.execution import (
    Execution, parameters,
)


PROVIDER = 'pgadmin.cdeadmin.providers.postgresql.provider'
EXECUTION = 'pgadmin.cdeadmin.providers.postgresql.execution'


@pytest.fixture
def provider():
    return PostgreSQLProvider(endpoint(), FakePermissions(), FakeDriver())


def open_session(provider, **route):
    return provider.open_session({'route': {'server_id': 7, **route}})


def finish(provider, operation):
    deadline = time.monotonic() + 5
    results = []
    while time.monotonic() < deadline:
        result = provider.describe_result(operation)
        results.append(result)
        if result['complete']:
            return results
    raise AssertionError('worker did not finish')


def test_delegated_close_releases_original_manager(provider):
    session = open_session(provider, owner_id=19,
                           principal_reference='worker:owned')
    manager = provider._sessions[session['session_id']].manager
    with patch(PROVIDER + '.native_control',
               return_value=(True, 'ROLLBACK')):
        provider.close_session(session)
    assert provider._driver.server_ids == [(7, 19, 'server')]
    assert manager.release_calls == [{
        'conn_id': session['provider_state']['connection_id']}]


def test_caller_cannot_alias_retained_connections(provider):
    a = open_session(provider, connection_id='existing-query-tool')
    b = open_session(provider, connection_id='existing-query-tool')
    assert (a['provider_state']['connection_id'] !=
            b['provider_state']['connection_id'])
    assert all(not call['auto_reconnect'] and not call['async_']
               for call in provider._driver.manager.connection_calls)


def test_lost_commit_is_quarantined_and_not_retried(provider):
    session = open_session(provider)
    with patch(PROVIDER + '.native_control',
               side_effect=OSError('private material')) as command:
        with pytest.raises(RuntimeError, match='unknown; do not replay'):
            provider.control_transaction(dict(session, action='commit'))
        with pytest.raises(RuntimeError, match='unknown'):
            provider.control_transaction(dict(session, action='commit'))
        with pytest.raises(RuntimeError, match='unknown'):
            provider.execute(dict(session, source='SELECT 1'))
        assert command.call_count == 1
    assert provider.describe_transaction(
        session)['provider_payload']['session_reuse_blocked']
    receipt = provider.close_session(session)
    assert receipt['provider_payload']['outcome_unknown']


def test_failed_rollback_still_releases_and_preserves_uncertainty(provider):
    session = open_session(provider)
    with patch(PROVIDER + '.native_control',
               side_effect=OSError):
        receipt = provider.close_session(session)
    assert receipt['provider_payload']['outcome_unknown']
    assert provider._driver.manager.release_calls


def test_release_failure_retains_owner_for_retry(provider):
    session = open_session(provider)
    manager = provider._driver.manager
    original = manager.release
    manager.release = Mock(side_effect=OSError)
    with patch(PROVIDER + '.native_control',
               return_value=(True, 'ROLLBACK')):
        with pytest.raises(RuntimeError, match='release failed'):
            provider.close_session(session)
    assert session['session_id'] in provider._sessions
    manager.release = original
    provider.close_session(session)
    assert not provider._sessions


def test_lost_attachment_does_not_reconnect(provider):
    session = open_session(provider)
    connection = provider._driver.manager._connection
    connection.connected = lambda: False
    connection.connect = Mock()
    with pytest.raises(RuntimeError, match='was lost'):
        provider.execute(dict(session, source='INSERT INTO t VALUES(1)'))
    connection.connect.assert_not_called()


def test_closed_provider_refuses_new_sessions(provider):
    provider.close()
    with pytest.raises(RuntimeError, match='closed'):
        open_session(provider)


def test_execution_owns_session_until_native_observation(provider):
    session = open_session(provider)
    release = threading.Event()

    def pages(*_args):
        assert release.wait(5)
        yield {'rows': [['1']], 'columns': [], 'has_page': True}

    with patch(EXECUTION + '.result_pages', pages):
        op = provider.execute(dict(session, source='SELECT 1'))
        try:
            for action in (
                lambda: provider.execute(dict(session, source='SELECT 2')),
                lambda: provider.control_transaction(
                    dict(session, action='commit')),
                lambda: provider.complete(session),
            ):
                with pytest.raises(RuntimeError, match='execution is active'):
                    action()
        finally:
            release.set()
        finish(provider, op)
    # Terminal cancellation cannot target the next execution.
    provider._operations[op['operation_id']].execution.cancel = Mock()
    provider.cancel(op)
    provider._operations[op['operation_id']
                         ].execution.cancel.assert_not_called()


@pytest.mark.parametrize('sqlstate,blocked,closed', [
    ('42601', False, False), (None, True, True), ('57P01', True, True)])
def test_native_errors_are_sanitized_and_classified(
        provider, sqlstate, blocked, closed):
    session = open_session(provider)

    class Failure(Exception):
        pass

    provider._driver.manager._connection.closed = closed
    error = Failure('private SQL and credential material')
    error.sqlstate = sqlstate
    with patch(EXECUTION + '.result_pages',
               side_effect=error):
        op = provider.execute(dict(session, source='SELECT 1'))
        pages = finish(provider, op)
    payload = pages[-1]['extensions']['postgresql']
    assert payload['session_reuse_blocked'] is blocked
    assert payload['error'] == {'type': 'Failure', 'sqlstate': sqlstate}
    assert 'private' not in str(pages)


def test_queue_applies_backpressure_and_close_discards_pending_pages(provider):
    session = open_session(provider)
    produced = []

    def pages(*_args):
        for i in range(20):
            produced.append(i)
            yield {'rows': [[str(i)]], 'columns': [], 'has_page': True}

    with patch(EXECUTION + '.result_pages', pages), \
            patch(PROVIDER + '.native_control',
                  return_value=(True, 'ROLLBACK')):
        op = provider.execute(dict(session, source='SELECT lots'))
        token = provider._operations[op['operation_id']].execution
        token.connection.cancel = Mock()
        deadline = time.monotonic() + 2
        while len(produced) < 3 and time.monotonic() < deadline:
            time.sleep(.01)
        assert len(produced) == 3
        assert token.pages.qsize() == 2
        provider.close_session(session)
        assert token.finished.is_set()
        assert not provider._sessions
        assert provider.describe_result(op)['complete']


def test_parameter_envelopes_preserve_precision_and_binary():
    from decimal import Decimal
    assert parameters([{'type': 'decimal', 'value': '1.000000000000000001'},
                       {'type': 'integer', 'value': '9223372036854775808'},
                       {'type': 'binary', 'value': 'AP8='}]) == [
                           Decimal('1.000000000000000001'),
                           9223372036854775808, b'\x00\xff']
    with pytest.raises(ValueError):
        parameters({'x': {'type': 'decimal', 'value': 1.5}})
    with pytest.raises(ValueError):
        parameters('SELECT injection')


def test_worker_start_failure_does_not_leave_phantom_operation(provider):
    session = open_session(provider)
    with patch.object(Execution, 'start', side_effect=RuntimeError):
        with pytest.raises(RuntimeError, match='could not start'):
            provider.execute(dict(session, source='SELECT 1'))
    assert not provider._operations


def test_commit_initial_attachment_and_failed_close_receipt(provider):
    session = open_session(provider)
    state = provider._sessions[session['session_id']]
    state.attached = False
    state.connection.connected = Mock(return_value=False)
    state.connection.connect = Mock(return_value=(True, None))
    with patch(PROVIDER + '.native_control',
               return_value=(True, 'COMMIT')):
        observation = provider.control_transaction(
            dict(session, action='commit'))
    assert observation['provider_payload']['command_status'] == 'COMMIT'
    state.connection.connect.assert_called_once_with()
    with patch(PROVIDER + '.native_control',
               side_effect=OSError):
        receipt = provider.close_session(session)
    assert receipt['provider_payload']['rollback_requested']
    assert receipt['provider_payload']['outcome_unknown']


def test_sql_ascii_bytes_are_preserved_without_replacement():
    from pgadmin.cdeadmin.providers.postgresql.execution import value
    assert value(b'\xff\x00', 'ascii') == {
        'encoding': 'base64', 'data': '/wA=', 'byte_length': 2,
        'native_encoding': 'SQL_ASCII'}
    with pytest.raises(UnicodeDecodeError):
        value(b'\xff', 'utf-8')


def test_profile_change_refuses_open_owned_sessions(provider):
    session = open_session(provider)
    with pytest.raises(RuntimeError, match='Close PostgreSQL SQL sessions'):
        with provider.profile_change_guard():
            pytest.fail('active session admitted a profile change')
    assert session['session_id'] in provider._sessions
    with patch(PROVIDER + '.native_control', return_value=(True, 'ROLLBACK')):
        provider.close_session(session)
    with provider.profile_change_guard():
        provider.release_for_profile_change()
    assert provider._closed
