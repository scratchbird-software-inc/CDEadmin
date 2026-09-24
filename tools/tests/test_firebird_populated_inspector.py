"""Read-only native snapshot safety for populated browser qualification."""

from unittest.mock import Mock

import pytest

from tools import cdeadmin_firebird_populated_inspector as gate


@pytest.fixture
def native(monkeypatch):
    import firebird.driver as driver
    connection = Mock()
    connection.cursor.return_value.fetchall.return_value = [('ID',), ('NAME',)]
    monkeypatch.setattr(driver, 'connect', Mock(return_value=connection))
    monkeypatch.setattr(gate, '_load_profile', lambda _path: {
        'password': 'private-test-password', 'database': '/owned.fdb'})
    monkeypatch.setattr(gate, '_route_arguments', lambda route, _driver: route)
    monkeypatch.setattr(gate, '_create_client', Mock())
    monkeypatch.setattr(gate, '_resources', lambda *_args: [
        {'resource_kind': kind, 'display_name': name,
         'native': {'ddl': f'CREATE {kind} {name}'}}
        for _group, kind, name in gate.CASES])
    return connection


def test_snapshot_is_read_only_and_does_not_export_credentials(native):
    result = gate.native_expectations('private-profile')
    assert set(result) == {case[2] for case in gate.CASES}
    assert result['CUSTOMERS']['columns'] == ['ID', 'NAME']
    assert result['INSPECTION_NUMBER']['columns'] == []
    assert 'private-test-password' not in repr(result)
    native.commit.assert_not_called()
    native.rollback.assert_called_once()
    native.close.assert_called_once()
    assert native.cursor.return_value.execute.call_count == 3


def test_catalog_failure_closes_native_attachment(native, monkeypatch):
    monkeypatch.setattr(gate, '_resources',
                        Mock(side_effect=RuntimeError('bad')))
    with pytest.raises(RuntimeError, match='bad'):
        gate.native_expectations('private-profile')
    native.rollback.assert_called_once()
    native.close.assert_called_once()


def test_absent_columns_are_failure_not_empty_success(native):
    native.cursor.return_value.fetchall.return_value = []
    with pytest.raises(RuntimeError, match='columns are absent'):
        gate.native_expectations('private-profile')
    native.rollback.assert_called_once()
    native.close.assert_called_once()


def test_rollback_failure_still_attempts_detach(native):
    native.rollback.side_effect = RuntimeError('lost')
    with pytest.raises(RuntimeError, match='lost'):
        gate.native_expectations('private-profile')
    native.close.assert_called_once()


@pytest.mark.parametrize('ddl', [None, '', '   ', {}])
def test_missing_ddl_is_failure(native, monkeypatch, ddl):
    monkeypatch.setattr(gate, '_resources', lambda *_args: [{
        'resource_kind': 'table', 'display_name': 'CUSTOMERS',
        'native': {'ddl': ddl}}])
    with pytest.raises(RuntimeError, match='DDL is absent'):
        gate.native_expectations('private-profile')
    native.close.assert_called_once()


def test_virtual_tree_scan_scrolls_without_clicking(monkeypatch):
    browser = Mock()
    row = Mock()
    monkeypatch.setattr(gate, 'named_tree_item',
                        Mock(side_effect=[None, row]))
    wait = Mock()

    def until(predicate):
        assert predicate(browser) is None
        return predicate(browser)

    wait.until.side_effect = until
    assert gate.reveal_tree_item(browser, wait, 'Tables') is row
    assert browser.execute_script.call_args_list[0].args[1] == 'reset'
    assert browser.execute_script.call_args_list[1].args[1] == 'next'
    assert browser.execute_script.call_args_list[2].args[1] is row
    row.click.assert_not_called()


def test_final_glyph_inside_clipping_ancestors_passes():
    gate.assert_text_visible({'glyph': {
        'left': 10, 'right': 20, 'top': 30, 'bottom': 40,
        'width': 10, 'height': 10},
        'clip': {'left': 0, 'right': 25, 'top': 0, 'bottom': 45}})


@pytest.mark.parametrize('key,value', [
    ('left', -5), ('right', 40), ('top', -5), ('bottom', 60),
    ('width', 0), ('height', 0)])
def test_clipped_or_missing_final_glyph_is_rejected(key, value):
    glyph = {'left': 10, 'right': 20, 'top': 30, 'bottom': 40,
             'width': 10, 'height': 10}
    glyph[key] = value
    with pytest.raises(RuntimeError, match='clipped'):
        gate.assert_text_visible({'glyph': glyph, 'clip': {
            'left': 0, 'right': 25, 'top': 0, 'bottom': 45}})


def test_keyboard_check_uses_tab_and_end_without_programmatic_scroll():
    browser, panel, selector, wait = Mock(), Mock(), Mock(), Mock()
    browser.find_element.return_value = selector
    browser.find_elements.return_value = []
    browser.switch_to.active_element = panel
    layout = {'white_space': 'normal', 'text_overflow': 'clip',
              'content_width': 200, 'viewport_width': 200}
    observation = {'glyph': {'left': 10, 'right': 20, 'top': 30,
                             'bottom': 40, 'width': 10, 'height': 10},
                   'clip': {'left': 0, 'right': 25, 'top': 0, 'bottom': 45}}
    browser.execute_script.side_effect = [layout, True, observation]

    def until(predicate):
        assert predicate(browser)
        return True

    wait.until.side_effect = until
    result = gate.ddl_keyboard_evidence(browser, wait, panel)
    selector.send_keys.assert_called_once_with(gate.Keys.TAB)
    panel.send_keys.assert_called_once_with(gate.Keys.END)
    assert result['selector'] == layout
    for call in browser.execute_script.call_args_list:
        assert 'scrollIntoView' not in call.args[0]
        assert 'scrollTop =' not in call.args[0]


@pytest.mark.parametrize('override', [
    {'white_space': 'nowrap'}, {'text_overflow': 'ellipsis'},
    {'content_width': 210}])
def test_truncated_section_label_is_rejected(override):
    browser = Mock()
    browser.execute_script.return_value = {
        'white_space': 'normal', 'text_overflow': 'clip',
        'content_width': 200, 'viewport_width': 200, **override}
    with pytest.raises(RuntimeError, match='selector truncates'):
        gate.ddl_keyboard_evidence(browser, Mock(), Mock())
