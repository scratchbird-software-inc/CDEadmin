##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2026, The ScratchBird Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Validation for appearance settings and named appearance presets.

A preset is a named set of appearance preference values (fonts, colours,
area sizes, profile, density, motion and theme). Presets are stored per
account as one JSON preference. Every value in a preset is checked by the
same rule as the preference it sets, so a preset can never store what the
preference itself would refuse.
"""

import json
import re

from flask_babel import gettext

PRESETS_SCHEMA = 'cdeadmin.appearance-presets.v1'
MAX_PRESETS = 40
MAX_NAME_LENGTH = 60
PRESET_PREFERENCE = 'appearance_presets'
APPEARANCE_CATEGORIES = ('accessibility', 'accessibility_colors')
EXTRA_PREFERENCES = ('theme',)

# Supported range for each numeric appearance setting; -1 inherits the
# profile. Mirrors PRESENTATION_OVERRIDE_RANGES in
# static/js/cdeadmin_ui/foundations/presentation.js (a test keeps them equal).
NUMERIC_RANGES = {
    'accessibility_ui_scale': (75, 300),
    'accessibility_icon_scale': (75, 300),
    'accessibility_line_height': (1, 2.5),
    'accessibility_letter_spacing': (0, 0.2),
    'accessibility_control_height': (24, 72),
    'accessibility_target_size': (24, 72),
    'accessibility_target_spacing': (0, 24),
    'accessibility_scrollbar_size': (8, 48),
    'accessibility_resize_handle_size': (5, 32),
    'accessibility_panel_gap': (0, 32),
    'accessibility_tree_row_height': (24, 72),
    'accessibility_tree_indent': (12, 48),
    'accessibility_tree_expander_size': (12, 40),
    'accessibility_tree_guide_width': (1, 4),
    'accessibility_grid_row_height': (24, 96),
    'accessibility_grid_header_height': (24, 120),
    'accessibility_grid_cell_padding': (2, 32),
    'accessibility_tab_height': (24, 96),
    'accessibility_toolbar_height': (24, 96),
    'accessibility_menu_row_height': (24, 96),
    'accessibility_menu_font_size': (10, 32),
    'accessibility_activity_bar_width': (32, 120),
    'accessibility_activity_icon_size': (12, 64),
    'accessibility_status_height': (20, 72),
    'accessibility_corner_radius': (0, 24),
    'accessibility_active_tab_scale': (100, 150),
    'accessibility_inactive_brightness': (30, 100),
    'accessibility_focus_width': (2, 8),
    'accessibility_focus_offset': (0, 6),
}

_HEX_COLOR = re.compile(r'^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$')
# Font family lists such as: "Atkinson Hyperlegible", Arial, sans-serif.
# No characters that could end the CSS declaration or open a function.
_FONT_FAMILY = re.compile(r'^[\w \-,.\'"]{0,200}$')
_CONTROL = re.compile(r'[\x00-\x1f\x7f]')


def numeric_validator(name):
    """Keep -1 (inherit); clamp anything else into the supported range."""
    minimum, maximum = NUMERIC_RANGES[name]

    def validate(value):
        if value == -1:
            return value
        bounded = min(maximum, max(minimum, value))
        return int(bounded) if isinstance(value, int) else bounded
    return validate


def color_validator(value):
    """Blank (inherit) or a #RGB / #RRGGBB colour."""
    value = '' if value is None else str(value).strip()
    if value and not _HEX_COLOR.match(value):
        raise ValueError(gettext('Use a #RRGGBB colour, or leave it blank.'))
    return value


def font_family_validator(value):
    """Blank (inherit) or a CSS font family list without markup."""
    value = '' if value is None else str(value).strip()
    if not _FONT_FAMILY.match(value):
        raise ValueError(gettext(
            'A font family may use letters, digits, spaces, commas, quotes, '
            'hyphens and periods only.'))
    return value


def appearance_preferences(module):
    """Name -> registered preference for every value a preset may hold."""
    result = {}
    for category in APPEARANCE_CATEGORIES:
        cat = module.categories.get(category)
        for name, pref in (cat or {}).get('preferences', {}).items():
            if name != PRESET_PREFERENCE:
                result[name] = pref
    for name in EXTRA_PREFERENCES:
        pref = module.preference(name)
        if pref is not None:
            result[name] = pref
    return result


def _preset_value(pref, value):
    """Check one value the way the preference's own set() would."""
    kind = pref._type
    if kind in ('integer', 'numeric'):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(gettext('%(name)s must be a number.',
                                     name=pref.name))
        if kind == 'integer':
            if isinstance(value, float) and not value.is_integer():
                raise ValueError(gettext('%(name)s must be a whole number.',
                                         name=pref.name))
            value = int(value)
        value = pref.normalize_range(value)
    elif kind == 'options':
        if not any(option.get('value') == value
                   for option in pref.options or []):
            raise ValueError(gettext('%(name)s has an unknown option.',
                                     name=pref.name))
    elif kind == 'text':
        if not isinstance(value, str):
            raise ValueError(gettext('%(name)s must be text.',
                                     name=pref.name))
    else:
        raise ValueError(gettext('%(name)s cannot be stored in a preset.',
                                 name=pref.name))
    if pref.validator is not None:
        value = pref.validator(value)
    return value


def validate_presets(value, module):
    """Return the normalized presets document as JSON text.

    Raises ValueError, with a message for the user, for anything that is not
    a presets document of known appearance settings with supported values.
    """
    if isinstance(value, str):
        try:
            document = json.loads(value) if value.strip() else {
                'schema': PRESETS_SCHEMA, 'presets': []}
        except ValueError:
            raise ValueError(gettext('Appearance presets are not valid JSON.'))
    else:
        document = value
    if not isinstance(document, dict) or \
            document.get('schema') != PRESETS_SCHEMA or \
            not isinstance(document.get('presets'), list) or \
            set(document) - {'schema', 'presets'}:
        raise ValueError(gettext('Appearance presets have an unknown format.'))
    if len(document['presets']) > MAX_PRESETS:
        raise ValueError(gettext('Keep at most %(count)d appearance presets.',
                                 count=MAX_PRESETS))

    known = appearance_preferences(module)
    seen = set()
    presets = []
    for preset in document['presets']:
        if not isinstance(preset, dict) or \
                set(preset) - {'name', 'values'} or \
                not isinstance(preset.get('values'), dict):
            raise ValueError(gettext('An appearance preset is malformed.'))
        name = preset.get('name')
        if not isinstance(name, str) or not name.strip() or \
                len(name.strip()) > MAX_NAME_LENGTH or _CONTROL.search(name):
            raise ValueError(gettext(
                'A preset name must be 1 to %(length)d characters.',
                length=MAX_NAME_LENGTH))
        name = name.strip()
        if name.casefold() in seen:
            raise ValueError(gettext('Preset names must be unique.'))
        seen.add(name.casefold())
        values = {}
        for key, item in preset['values'].items():
            if key not in known:
                raise ValueError(gettext(
                    '%(name)s is not an appearance setting.', name=key))
            values[key] = _preset_value(known[key], item)
        presets.append({'name': name, 'values': values})
    return json.dumps({'schema': PRESETS_SCHEMA, 'presets': presets},
                      sort_keys=True)
