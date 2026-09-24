"""Retain timeout evidence before replacing a failed navigator page."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from selenium.common.exceptions import TimeoutException

from tools import cdeadmin_firebird_ui_form_gate as gate


def test_setup_keeps_engine_server_and_database_ancestry(monkeypatch):
    for name in ('apply_presentation', 'ensure_data_explorer'):
        monkeypatch.setattr(gate, name, Mock())
    expand, lookup = Mock(), Mock()
    monkeypatch.setattr(gate, 'expand', expand)
    monkeypatch.setattr(gate, 'wait_for_tree_item', lookup)
    monkeypatch.setattr(gate, 'complete_endpoint_prompt',
                        Mock(return_value=True))
    monkeypatch.setattr(gate, 'selected_database_actions',
                        Mock(return_value=['inspect']))
    monkeypatch.setattr(gate, 'ActionChains', Mock())
    options = SimpleNamespace(url='http://test', engine='Firebird',
                              server='localhost', database='example.fdb')
    assert gate._prepare_tree_once(Mock(), Mock(), options, 'secret') == [
        'inspect']
    assert [(call.args[1], call.args[2]) for call in
            expand.call_args_list] == [
                ('Connectors', ()), ('Firebird', ('Connectors',)),
                ('localhost', ('Connectors', 'Firebird'))]
    assert [call.args[2] for call in lookup.call_args_list] == [
        ('Connectors',), ('Connectors', 'Firebird'),
        ('Connectors', 'Firebird', 'localhost'),
        ('Connectors', 'Firebird', 'localhost'),
        ('Connectors', 'Firebird', 'localhost')]


@pytest.mark.parametrize('capture_fails', [False, True])
def test_both_timeouts_are_captured_without_hiding_original_error(
        monkeypatch, tmp_path, capture_fails):
    first, last = TimeoutException('first'), TimeoutException('last')
    prepare = Mock(side_effect=[first, last])
    monkeypatch.setattr(gate, '_prepare_tree_once', prepare)
    capture = Mock(side_effect=(
        RuntimeError('capture') if capture_fails else None))
    monkeypatch.setattr(gate, 'screenshot', capture)
    driver = Mock()
    with pytest.raises(TimeoutException, match='last'):
        gate.prepare_tree(driver, Mock(),
                          SimpleNamespace(output_root=tmp_path),
                          'private-password')
    driver.get.assert_called_once_with('about:blank')
    assert capture.call_count == 2
    assert [call.args[1].name for call in capture.call_args_list] == [
        'tree-navigation-timeout-1.png', 'tree-navigation-timeout-2.png']
    assert all(call.kwargs == {'reset_scroll': False}
               for call in capture.call_args_list)
    assert all('visibility' in call.args[0] for call in
               driver.execute_script.call_args_list)
    assert 'private-password' not in repr(driver.mock_calls)


def test_success_after_retry_retains_first_failure_only(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, '_prepare_tree_once',
                        Mock(side_effect=[TimeoutException(), ['action']]))
    capture = Mock()
    monkeypatch.setattr(gate, 'screenshot', capture)
    result = gate.prepare_tree(Mock(), Mock(),
                               SimpleNamespace(output_root=tmp_path), 'secret')
    assert result == ['action']
    capture.assert_called_once()
