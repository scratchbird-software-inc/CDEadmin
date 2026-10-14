"""Native editor fetch settings are owned by each retained query session."""
import inspect
import pickle
from types import SimpleNamespace
from unittest.mock import Mock

from flask import Flask
import pytest
import pgadmin.tools.sqleditor as editor


@pytest.fixture
def endpoint(monkeypatch):
    app = Flask(__name__)
    commands = {7: SimpleNamespace(), 8: SimpleNamespace()}
    connections = {key: Mock(transaction_status=Mock(return_value=0), connected=Mock(return_value=True)) for key in commands}
    monkeypatch.setattr(editor, 'check_transaction_status', lambda key:
        (True, None, connections[key], commands[key], {}) if key in commands else
        (False, 'missing', None, None, None))
    persist = Mock()
    monkeypatch.setattr(editor, 'update_session_grid_transaction', persist)
    def invoke(key, value):
        with app.test_request_context('/', method='POST', json=value):
            return inspect.unwrap(editor.set_result_page_size)(key)
    return invoke, commands, connections, persist


def test_fetch_size_is_acknowledged_and_isolated(endpoint):
    invoke, commands, connections, persist = endpoint
    response = invoke(7, 23)
    assert response.status_code == 200
    assert response.get_json()['data'] == {'status': True, 'result': 23}
    assert commands[7].result_page_size == 23
    assert not hasattr(commands[8], 'result_page_size')
    saved = pickle.loads(persist.call_args.args[1]['command_obj'])
    assert saved.result_page_size == 23
    connections[7].execute_void.assert_not_called()
    connections[7].execute_async.assert_not_called()


@pytest.mark.parametrize('value', [0, -1, 100001, True, 1.5, '23', {}, None])
def test_invalid_fetch_sizes_cannot_mutate_or_execute(endpoint, value):
    invoke, commands, _, persist = endpoint
    assert invoke(7, value).status_code == 400
    assert not hasattr(commands[7], 'result_page_size')
    persist.assert_not_called()


def test_running_or_missing_session_cannot_change_fetch_size(endpoint):
    invoke, commands, connections, persist = endpoint
    connections[7].transaction_status.return_value = 1
    assert invoke(7, 23).status_code == 409
    assert invoke(99, 23).status_code == 409
    assert not hasattr(commands[7], 'result_page_size')
    persist.assert_not_called()


def test_disconnected_session_does_not_acknowledge_new_buffer_policy(endpoint):
    invoke, _, connections, persist = endpoint
    connections[7].connected.return_value = False
    assert invoke(7, 23).status_code == 409
    connections[7].transaction_status.assert_not_called()
    persist.assert_not_called()


def test_source_validation_uses_owned_session_and_never_reconnects(monkeypatch):
    app = Flask(__name__)
    connection = Mock(connected=Mock(return_value=True), transaction_status=Mock(return_value=0))
    connection.conn.info = SimpleNamespace(server_version=180003,
        parameter_status=Mock(return_value='on'))
    lookup = Mock(return_value=(True, None, connection, SimpleNamespace(), {}))
    monkeypatch.setattr(editor, 'check_transaction_status', lookup)
    def invoke(source, query=''):
        with app.test_request_context('/' + query, method='POST', json={'source': source}):
            return inspect.unwrap(editor.validate_query_source)(7)
    result = invoke('DROP TABLE never_execute')
    assert result.get_json()['data']['grammar_valid']
    assert invoke('SELECT (').get_json()['data']['grammar_valid'] is False
    assert invoke(None).status_code == 400
    lookup.reset_mock()
    assert invoke('SELECT 1', '?connect=1').status_code == 400
    lookup.assert_not_called()
    connection.connected.return_value = False
    assert invoke('SELECT 1').status_code == 409
    connection.connect.assert_not_called()
    connection.execute_async.assert_not_called()
    connection.conn.execute.assert_not_called()
