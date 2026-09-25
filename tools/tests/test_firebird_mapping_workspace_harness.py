"""Guard the mapping harness against legacy modal-only assumptions."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest


def test_close_workspace_waits_for_control_removal_without_modal_parent():
    path = Path(__file__).resolve().parents[1] / (
        'cdeadmin_firebird_ui_form_gate.py')
    function = next(item for item in ast.parse(path.read_text()).body
                    if isinstance(item, ast.FunctionDef)
                    and item.name == 'close_workspace')
    close, driver = Mock(), Mock()
    close.find_element.side_effect = AssertionError('not a dialog')
    until_stale = Mock(return_value=True)
    wait = SimpleNamespace(until=lambda callback: callback(driver))
    scope = {'visible_named_control': lambda *_: close,
             'expected': SimpleNamespace(
                 staleness_of=lambda item: until_stale)}
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 str(path), 'exec'), scope)
    scope['close_workspace'](driver, wait)
    close.click.assert_called_once_with()
    close.find_element.assert_not_called()
    until_stale.assert_called_once_with(driver)


def test_create_form_keeps_scope_kind_without_fake_catalog_identity():
    path = Path(__file__).resolve().parents[1] / (
        'cdeadmin_provider_object_form_gate.py')
    function = next(item for item in ast.parse(path.read_text()).body
                    if isinstance(item, ast.FunctionDef)
                    and item.name == '_open_focused_form')
    scope = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 str(path), 'exec'), scope)
    driver = Mock()
    operation = {'resource_kind': 'authentication-mapping',
                 'operation_id': 'create'}
    scope['_open_focused_form'](driver, operation, {
        'resource_id': 'cdeadmin-create-scope:authentication-mapping'}, 'db')
    script = driver.execute_script.call_args.args[0]
    assert "startsWith('cdeadmin-create-scope:')" in script
    assert 'null : target?.resource_id' in script
    assert 'resource_kind: operation.resource_kind' in script


@pytest.mark.parametrize('still_connected', [False, True])
def test_keyboard_cancellation_tracks_only_the_dismissed_workspace(
        still_connected):
    path = Path(__file__).resolve().parents[1] / (
        'cdeadmin_firebird_ui_form_gate.py')
    function = next(item for item in ast.parse(path.read_text()).body
                    if isinstance(item, ast.FunctionDef)
                    and item.name == 'cancellation_observation')
    scope = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 str(path), 'exec'), scope)
    driver = Mock()
    driver.execute_script.side_effect = [False, still_connected,
                                         'keyboard_close_button']
    if still_connected:
        with pytest.raises(RuntimeError, match='remained visible'):
            scope['cancellation_observation'](driver)
    else:
        assert scope['cancellation_observation'](driver)[
            'dismissal_input'] == 'keyboard_close_button'
