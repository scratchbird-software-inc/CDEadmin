"""Appearance settings and presets are validated by the server.

View > Appearance and Accessibility stores fonts, colours, area sizes and
named presets as misc preferences (2026-11-05). The server checks every value
with the same rule whether it arrives directly, through `setup.py set-prefs`,
or inside a preset; File > Preferences no longer lists these hidden settings.
"""
import json
import re
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'web'
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(WEB / 'pgadmin')]
    sys.modules['pgadmin'] = package

import config  # noqa: F401,E402
from pgadmin.misc import MiscModule  # noqa: E402
from pgadmin.misc.appearance_presets import (  # noqa: E402
    NUMERIC_RANGES, PRESETS_SCHEMA, color_validator, font_family_validator,
    numeric_validator, validate_presets,
)
from pgadmin.utils.preferences import _Preference  # noqa: E402

PRESENTATION = ROOT / 'web/pgadmin/static/js/cdeadmin_ui/foundations/presentation.js'


class Recorder:
    """Stands in for the misc Preferences object: keeps real _Preference
    objects (built without the configuration database) by category."""

    def __init__(self):
        self.categories = {}

    def register(self, category, name, label, _type, default, **kwargs):
        pref = _Preference.__new__(_Preference)
        pref.name, pref.label, pref._type, pref.default = name, label, _type, default
        for key in ('min_val', 'max_val', 'options', 'validator', 'hidden',
                    'control_props', 'allow_blanks'):
            setattr(pref, key, kwargs.get(key))
        cat = self.categories.setdefault(category, {'preferences': {}})
        cat['preferences'][name] = pref
        return pref

    def preference(self, name):
        for cat in self.categories.values():
            if name in cat['preferences']:
                return cat['preferences'][name]
        return None


@pytest.fixture(scope='module')
def misc():
    recorder = Recorder()
    MiscModule.register_preferences(SimpleNamespace(preference=recorder))
    return recorder


def appearance(misc):
    return {**misc.categories['accessibility']['preferences'],
            **misc.categories['accessibility_colors']['preferences']}


def test_server_ranges_match_the_presentation_authority():
    source = PRESENTATION.read_text()
    block = source[source.index('PRESENTATION_OVERRIDE_RANGES = Object.freeze({'):]
    block = block[:block.index('});')]
    client = {name: (float(low), float(high)) for name, low, high in re.findall(
        r'(accessibility_\w+): \[([\d.]+), ([\d.]+)\]', block)}
    assert client == {name: (float(low), float(high))
                      for name, (low, high) in NUMERIC_RANGES.items()}


def test_every_numeric_setting_is_registered_hidden_and_bounded(misc):
    prefs = misc.categories['accessibility']['preferences']
    for name, (_low, high) in NUMERIC_RANGES.items():
        pref = prefs[name]
        assert (pref.min_val, pref.max_val, pref.default) == (-1, high, -1)
        assert pref.hidden is True and pref.validator is not None
    for name in ('accessibility_menu_font_size', 'accessibility_activity_bar_width',
                 'accessibility_activity_icon_size'):
        assert name in prefs


def test_appearance_settings_leave_file_preferences(misc):
    hidden = {name for name, pref in appearance(misc).items() if pref.hidden}
    assert hidden == set(appearance(misc))
    assert misc.preference('theme').hidden is None  # still in File > Preferences
    for name, pref in appearance(misc).items():
        if '_color_' in name:
            assert pref.validator is color_validator
        if name.endswith('font_family'):
            assert pref.validator is font_family_validator


def test_numeric_values_keep_inherit_and_clamp_into_range():
    height = numeric_validator('accessibility_control_height')
    assert height(-1) == -1
    assert height(10) == 24 and height(40) == 40 and height(500) == 72
    assert numeric_validator('accessibility_line_height')(0.5) == 1


@pytest.mark.parametrize('value', ['', '#abc', '#AABBCC', ' #aabbcc '])
def test_colours_accept_blank_and_hex(value):
    assert color_validator(value) == value.strip()


@pytest.mark.parametrize('value', ['red', '#12345', 'url(x)', '#AABBCCDD',
                                   '#aabbcc;}'])
def test_colours_refuse_anything_else(value):
    with pytest.raises(ValueError):
        color_validator(value)


def test_font_families_refuse_css_markup():
    assert font_family_validator('"Atkinson Hyperlegible", sans-serif') == \
        '"Atkinson Hyperlegible", sans-serif'
    for value in ('Arial; } body { display:none', 'url(evil)', 'a<b>', 'x' * 201):
        with pytest.raises(ValueError):
            font_family_validator(value)


def test_set_refuses_a_value_its_validator_refuses_before_storing():
    pref = _Preference.__new__(_Preference)
    pref.name, pref._type, pref.min_val, pref.max_val = 'c', 'text', None, None
    pref.options = pref.control_props = None
    pref.validator = color_validator
    assert pref.set('not-a-colour', user_id=1) == (
        False, 'Use a #RRGGBB colour, or leave it blank.')


def presets(*items):
    return json.dumps({'schema': PRESETS_SCHEMA, 'presets': list(items)})


def test_a_valid_presets_document_is_normalized(misc):
    stored = json.loads(validate_presets(presets(
        {'name': '  Large text ', 'values': {
            'accessibility_ui_scale': 175, 'accessibility_line_height': 1.75,
            'accessibility_menu_font_size': 99, 'accessibility_color_text': '#101010',
            'accessibility_profile': 'low_vision', 'theme': 'dark',
            'accessibility_ui_font_family': 'Atkinson Hyperlegible'}},
        {'name': 'Compact', 'values': {'accessibility_control_height': 10}}),
        misc))
    assert stored['schema'] == PRESETS_SCHEMA
    large, compact = stored['presets']
    assert large['name'] == 'Large text'
    assert large['values']['accessibility_menu_font_size'] == 32  # clamped
    assert large['values']['theme'] == 'dark'
    assert compact['values']['accessibility_control_height'] == 24
    assert validate_presets('', misc) == json.dumps(
        {'schema': PRESETS_SCHEMA, 'presets': []}, sort_keys=True)


@pytest.mark.parametrize('document,message', [
    ('{', 'not valid JSON'),
    (json.dumps({'schema': 'other', 'presets': []}), 'unknown format'),
    (json.dumps({'schema': PRESETS_SCHEMA, 'presets': [], 'extra': 1}), 'unknown format'),
    (presets({'name': 'A', 'values': {'password': 'x'}}), 'not an appearance setting'),
    (presets({'name': 'A', 'values': {'appearance_presets': ''}}), 'not an appearance setting'),
    (presets({'name': 'A', 'values': {'accessibility_color_text': 'red'}}), '#RRGGBB'),
    (presets({'name': 'A', 'values': {'accessibility_profile': 'evil'}}), 'unknown option'),
    (presets({'name': 'A', 'values': {'theme': 'neon'}}), 'unknown option'),
    (presets({'name': 'A', 'values': {'accessibility_ui_scale': True}}), 'must be a number'),
    (presets({'name': 'A', 'values': {'accessibility_ui_scale': '150'}}), 'must be a number'),
    (presets({'name': 'A', 'values': {'accessibility_ui_scale': 150.5}}), 'whole number'),
    (presets({'name': 'A', 'values': {'accessibility_ui_font_family': '}'}}), 'font family'),
    (presets({'name': '', 'values': {}}), 'preset name'),
    (presets({'name': 'x' * 61, 'values': {}}), 'preset name'),
    (presets({'name': 'a\nb', 'values': {}}), 'preset name'),
    (presets({'name': 'Same', 'values': {}}, {'name': 'same ', 'values': {}}), 'unique'),
    (presets({'name': 'A', 'values': []}), 'malformed'),
    (presets(*[{'name': f'P{i}', 'values': {}} for i in range(41)]), 'at most 40'),
])
def test_presets_refuse_what_their_settings_refuse(misc, document, message):
    with pytest.raises(ValueError, match=message):
        validate_presets(document, misc)


def test_the_presets_preference_validates_through_its_own_registration(misc):
    pref = misc.preference('appearance_presets')
    assert pref.hidden is True and pref._type == 'text'
    with pytest.raises(ValueError):
        pref.validator(presets({'name': 'A', 'values': {'accessibility_color_text': 'x'}}))
    assert json.loads(pref.validator(presets()))['presets'] == []


def test_file_preferences_lists_only_visible_settings():
    # Loaded by path: importing the pgadmin.preferences package starts the
    # whole browser blueprint; listing.py itself needs only flask_babel.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'preferences_listing', WEB / 'pgadmin/preferences/listing.py')
    listing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(listing)
    _iterate_categories = listing._iterate_categories
    module = {'id': 1, 'label': 'Miscellaneous', 'name': 'misc', 'categories': [
        {'id': 10, 'name': 'user_interface', 'label': 'User interface', 'preferences': [
            {'name': 'theme', 'label': 'Theme', 'hidden': None},
            {'name': 'secret_switch', 'label': 'Hidden', 'hidden': True}]},
        {'id': 11, 'name': 'accessibility', 'label': 'Accessibility', 'preferences': [
            {'name': 'accessibility_ui_scale', 'label': 'Scale', 'hidden': True}]},
    ]}
    listed = []
    _iterate_categories(module, lambda item: item['label'], listed)
    [entry] = listed
    assert [c['name'] for c in entry['children']] == ['user_interface']
    assert [p['name'] for p in entry['children'][0]['preferences']] == ['theme']

    only_hidden = {'id': 2, 'label': 'Browser', 'name': 'browser', 'categories': [
        {'id': 20, 'name': 'commands', 'label': 'Commands', 'preferences': [
            {'name': 'command_customizations', 'label': 'C', 'hidden': True}]}]}
    listed = []
    _iterate_categories(only_hidden, lambda item: item['label'], listed)
    assert listed == []
