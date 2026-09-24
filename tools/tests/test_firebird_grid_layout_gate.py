"""Qualification assertions must reject compressed or clipped layouts."""

from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from tools.cdeadmin_firebird_grid_ui_gate import (
    _layout_evidence, _shell_layout_evidence,
)


def test_editor_open_failure_masks_values_and_preserves_error(
        monkeypatch, tmp_path):
    from tools import cdeadmin_firebird_grid_ui_gate as gate
    error = RuntimeError('editor missing')
    monkeypatch.setattr(gate, '_button', Mock(side_effect=error))
    capture = Mock(side_effect=RuntimeError('capture failed'))
    monkeypatch.setattr(gate, 'screenshot', capture)
    driver = Mock()
    with pytest.raises(RuntimeError, match='editor missing'):
        gate._wait_for_editor(driver, Mock(),
                              SimpleNamespace(output_root=tmp_path))
    assert 'visibility' in driver.execute_script.call_args.args[0]
    capture.assert_called_once_with(
        driver, tmp_path / 'editor-open-failed.png', reset_scroll=False)


def test_successful_editor_open_does_not_hide_inputs(monkeypatch):
    from tools import cdeadmin_firebird_grid_ui_gate as gate
    button = Mock()
    monkeypatch.setattr(gate, '_button', Mock(return_value=button))
    driver = Mock()
    assert gate._wait_for_editor(driver, Mock(), Mock()) is button
    driver.execute_script.assert_not_called()


def observation(scale=100):
    return {
        'column_widths': [n * scale / 100 for n in
                          (360, 360, 360, 360, 320)],
        'viewport_width': 1200, 'content_width': 1760 * scale / 100,
        'tab_bar': {'top': 100, 'bottom': 160, 'height': 60},
        'tabs': [{'top': 105, 'bottom': 155, 'height': 50,
                  'content': {'top': 105, 'bottom': 155, 'height': 50}}],
    }


@pytest.mark.parametrize('scale', [100, 150, 200, 300])
def test_accepts_scaled_scrollable_columns_and_contained_tabs(scale):
    driver = Mock()
    driver.execute_script.return_value = observation(scale)
    assert _layout_evidence(driver, scale) == observation(scale)


@pytest.mark.parametrize('index', range(5))
def test_rejects_each_compressed_column(index):
    driver = Mock()
    value = observation(200)
    value['column_widths'][index] = 50
    driver.execute_script.return_value = value
    with pytest.raises(RuntimeError, match='compressed'):
        _layout_evidence(driver, 200)


@pytest.mark.parametrize('edge,value', [('top', 99 - 1), ('bottom', 162)])
def test_rejects_vertically_clipped_tabs(edge, value):
    driver = Mock()
    observed = observation()
    observed['tabs'][0][edge] = value
    driver.execute_script.return_value = observed
    with pytest.raises(RuntimeError, match='outside'):
        _layout_evidence(driver, 100)


def test_missing_tab_bar_is_not_a_pass():
    driver = Mock()
    value = observation()
    value['tab_bar'] = None
    driver.execute_script.return_value = value
    with pytest.raises(RuntimeError, match='outside'):
        _layout_evidence(driver, 100)


def test_tab_label_overflow_is_not_hidden_by_a_larger_bar():
    driver = Mock()
    value = observation()
    value['tabs'][0]['content']['bottom'] = 158
    driver.execute_script.return_value = value
    with pytest.raises(RuntimeError, match='outside'):
        _layout_evidence(driver, 100)


@pytest.mark.parametrize('invalid', [None, float('nan'), float('inf')])
def test_unmeasured_column_is_not_a_pass(invalid):
    driver = Mock()
    value = observation()
    value['column_widths'][0] = invalid
    driver.execute_script.return_value = value
    with pytest.raises(RuntimeError, match='compressed'):
        _layout_evidence(driver, 100)


def shell_observation():
    return {
        'inspector': {'left': 0, 'right': 300},
        'empty': {'left': 0, 'right': 300},
        'message': {'left': 32, 'right': 292},
        'panel_width': 300, 'panel_content_width': 300,
        'explorer': {'left': 0, 'right': 300},
        'database_label': {'left': 80, 'right': 900},
        'scrolls': [{'before': 200, 'after': 0}],
    }


def test_recoverable_tree_scroll_is_not_misclassified_as_clipping():
    driver = Mock()
    driver.execute_script.return_value = shell_observation()
    assert _shell_layout_evidence(driver, 'owned.fdb') == shell_observation()


@pytest.mark.parametrize('key', ['empty', 'message'])
def test_rejects_inspector_horizontal_overflow(key):
    driver = Mock()
    value = shell_observation()
    value[key]['right'] = 350
    driver.execute_script.return_value = value
    with pytest.raises(RuntimeError, match='Inspector'):
        _shell_layout_evidence(driver, 'owned.fdb')


def test_rejects_unreachable_navigator_label_start():
    driver = Mock()
    value = shell_observation()
    value['database_label']['left'] = -40
    driver.execute_script.return_value = value
    with pytest.raises(RuntimeError, match='Navigator'):
        _shell_layout_evidence(driver, 'owned.fdb')


@pytest.mark.parametrize('state,reset', [
    ('object-V-ddl-keyboard-bottom', False), ('initial', True)])
def test_inspector_screenshot_preserves_keyboard_scroll(
        monkeypatch, tmp_path, state, reset):
    from tools import cdeadmin_firebird_grid_ui_gate as gate
    screenshot = Mock(return_value='digest')
    monkeypatch.setattr(gate, 'screenshot', screenshot)
    options = SimpleNamespace(width=1600, height=1000, theme='default',
                              font_scale=100, output_root=tmp_path)
    records = {}
    driver = Mock()
    gate._capture(driver, options, state, records)
    assert screenshot.call_args.kwargs == {'reset_scroll': reset}
    assert records[state]['sha256'] == 'digest'
