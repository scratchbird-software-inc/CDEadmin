##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2026, The ScratchBird Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Validation for a user's tabbed command bar customization.

The document is the notebook bar package's customization
(scratch.notebookbar-customization.v1): per-tab visibility, labels and order,
user tabs and groups that reference commands by id, and the quick-access
command list. It only arranges commands the client already offers; the
client drops references to anything else, and command execution keeps its
own permission checks.
"""

import json
import re

from flask_babel import gettext

SCHEMA = 'scratch.notebookbar-customization.v1'
ID = re.compile(r'^[A-Za-z0-9][\w.:-]{0,127}$')
MAX_TABS = 40
MAX_GROUPS = 40
MAX_COMMANDS = 200
MAX_LABEL = 60


def _refuse():
    raise ValueError(gettext('The command bar customization is not valid.'))


def _label(value, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str) or len(value) > MAX_LABEL or \
            any(ord(char) < 32 for char in value):
        _refuse()
    return value


def _order(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or \
            not 0 <= value <= 1000:
        _refuse()
    return value


def _ids(values, limit):
    if not isinstance(values, list) or len(values) > limit or \
            not all(isinstance(item, str) and ID.match(item)
                    for item in values):
        _refuse()
    return values


def _clean(mapping):
    return {key: value for key, value in mapping.items() if value is not None}


def validate_command_bar_customization(value):
    """Return the normalized document as JSON text, or raise ValueError."""
    if isinstance(value, str):
        if not value.strip():
            return ''
        try:
            document = json.loads(value)
        except ValueError:
            _refuse()
    else:
        document = value
    if not isinstance(document, dict) or document.get('schema') != SCHEMA or \
            set(document) - {'schema', 'tabs', 'added', 'quickAccess'}:
        _refuse()
    tabs = document.get('tabs', {})
    if not isinstance(tabs, dict) or len(tabs) > MAX_TABS:
        _refuse()
    clean_tabs = {}
    for tab_id, settings in tabs.items():
        if not ID.match(tab_id) or not isinstance(settings, dict) or \
                set(settings) - {'hidden', 'label', 'order', 'groups'}:
            _refuse()
        groups = settings.get('groups', {})
        if not isinstance(groups, dict) or len(groups) > MAX_GROUPS:
            _refuse()
        clean_groups = {}
        for group_id, group in groups.items():
            if not ID.match(group_id) or not isinstance(group, dict) or \
                    set(group) - {'hidden', 'label', 'order'} or \
                    not isinstance(group.get('hidden', False), bool):
                _refuse()
            clean_groups[group_id] = _clean({
                'hidden': group.get('hidden'),
                'label': _label(group.get('label')),
                'order': _order(group.get('order'))})
        if not isinstance(settings.get('hidden', False), bool):
            _refuse()
        clean_tabs[tab_id] = _clean({
            'hidden': settings.get('hidden'),
            'label': _label(settings.get('label')),
            'order': _order(settings.get('order')),
            'groups': clean_groups or None})
    added = document.get('added', [])
    if not isinstance(added, list) or len(added) > MAX_TABS:
        _refuse()
    clean_added = []
    for tab in added:
        if not isinstance(tab, dict) or \
                set(tab) - {'tab', 'label', 'order', 'groups'} or \
                not isinstance(tab.get('tab'), str) or \
                not ID.match(tab['tab']) or \
                not isinstance(tab.get('groups', []), list) or \
                len(tab.get('groups', [])) > MAX_GROUPS:
            _refuse()
        groups = []
        for group in tab.get('groups', []):
            if not isinstance(group, dict) or \
                    set(group) - {'id', 'label', 'controls'} or \
                    not isinstance(group.get('id'), str) or \
                    not ID.match(group['id']):
                _refuse()
            groups.append({'id': group['id'],
                           'label': _label(group.get('label')) or '',
                           'controls': _ids(group.get('controls', []),
                                            MAX_COMMANDS)})
        clean_added.append(_clean({
            'tab': tab['tab'], 'label': _label(tab.get('label')),
            'order': _order(tab.get('order')), 'groups': groups}))
    result = {'schema': SCHEMA, 'tabs': clean_tabs, 'added': clean_added}
    if 'quickAccess' in document:
        result['quickAccess'] = _ids(document['quickAccess'], MAX_COMMANDS)
    return json.dumps(result, sort_keys=True)
