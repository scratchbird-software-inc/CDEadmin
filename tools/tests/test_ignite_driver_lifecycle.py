"""Worker context, lossless values and uncertain native decision ownership."""
import contextvars
from unittest.mock import Mock

import pytest
from test_cdeadmin_distributed_providers import IGNITE
from pgadmin.cdeadmin.providers.retained_native import RetainedNativeClient
from pgadmin.cdeadmin.providers.native_distributed import NativeResult
from pgadmin.cdeadmin.providers.apache_ignite.driver import exact, bound


@pytest.fixture
def owner():
    backend = Mock()
    backend.describe_transaction.return_value = {'native_state': 'owned'}
    client = RetainedNativeClient(IGNITE, backend, {})
    client.transaction_actions = ('begin', 'commit', 'rollback')
    session = client.open_session({})
    yield client, backend, session
    backend.close_session.side_effect = None
    client.close()


def test_transaction_context_is_retained_and_isolated(owner):
    client, backend, session = owner
    state = contextvars.ContextVar('owned', default=None)
    seen = []

    def control(handle, action):
        if action == 'begin':
            state.set(handle)
        else:
            seen.append(state.get())
    backend.control_transaction.side_effect = control
    backend.open_session.side_effect = [object()]
    second = client.open_session({})
    client.control_transaction(session, 'begin')
    client.control_transaction(second, 'commit')
    client.control_transaction(session, 'commit')
    assert seen == [None, session.handle]


def test_native_unknown_commit_is_not_replayed(owner):
    client, backend, session = owner
    backend.control_transaction.side_effect = OSError
    with pytest.raises(RuntimeError, match='unknown'):
        client.control_transaction(session, 'commit')
    with pytest.raises(RuntimeError, match='unknown'):
        client.control_transaction(session, 'commit')
    backend.control_transaction.assert_called_once()


def test_unobserved_result_retains_exclusive_owner(owner):
    client, backend, session = owner
    backend.iterate.return_value = iter([
        NativeResult('key_value', 'entries', [{'key': 1}], {}, {})])
    token = client.execute(session, {'source': 'SELECT 1'})
    token.future.result(timeout=2)
    with pytest.raises(RuntimeError, match='active'):
        client.control_transaction(session, 'commit')
    assert client.describe_result(token)['payload']['has_page']
    assert client.describe_result(token)['complete']


def test_cleanup_failure_keeps_session_for_retry(owner):
    client, backend, session = owner
    backend.close_session.side_effect = OSError
    with pytest.raises(RuntimeError, match='cleanup'):
        client.close_session(session)
    assert session in client._sessions


def test_exact_values_and_unsafe_direct_integer():
    assert bound({'type': 'integer', 'value': '9007199254740993'}
                 ) == 9007199254740993
    assert exact(b'\x00\xff') == {'type': 'binary', 'value': 'AP8='}
    with pytest.raises(RuntimeError, match='envelope'):
        bound(9007199254740993)


def test_native_timeout_is_terminal_not_an_infinite_poll(owner):
    client, backend, session = owner

    def failure(*_):
        raise TimeoutError('private command')
        yield
    backend.iterate.side_effect = failure
    token = client.execute(session, {'source': 'SELECT 1'})
    value = client.describe_result(token)
    assert value['complete']
    assert value['payload']['error'] == {'type': 'TimeoutError'}
    assert value['payload']['outcome_unknown']
