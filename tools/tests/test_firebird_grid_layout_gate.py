"""Qualification assertions must reject compressed or clipped layouts."""

from unittest.mock import Mock

import pytest

from tools.cdeadmin_firebird_grid_ui_gate import _layout_evidence


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
