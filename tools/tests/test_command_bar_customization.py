"""The tabbed command bar customization is validated by the server.

The document (scratch.notebookbar-customization.v1) only arranges commands
the client offers; the server refuses anything that is not that shape, keeps
ids to the bar's id rule and bounds every list and label (2026-11-05).
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Loaded by path: importing the pgadmin.browser package starts the whole
# browser blueprint; this module needs only json, re and flask_babel.
_spec = importlib.util.spec_from_file_location(
    'command_bar', ROOT / 'web/pgadmin/browser/command_bar.py')
command_bar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(command_bar)
validate = command_bar.validate_command_bar_customization
SCHEMA = 'scratch.notebookbar-customization.v1'


def doc(**parts):
    return json.dumps({'schema': SCHEMA, **parts})


def test_a_valid_document_is_normalized():
    stored = json.loads(validate(doc(
        tabs={'file': {'hidden': True, 'label': 'Start', 'order': 2,
                       'groups': {'file.g0': {'hidden': False, 'order': 1}}}},
        added=[{'tab': 'custom', 'label': 'Mine', 'order': 0, 'groups': [
            {'id': 'group', 'label': 'Favourites',
             'controls': ['project.create', 'tools.query.open']}]}],
        quickAccess=['project.create'])))
    assert stored['tabs']['file'] == {'hidden': True, 'label': 'Start',
                                      'order': 2,
                                      'groups': {'file.g0': {'hidden': False,
                                                             'order': 1}}}
    assert stored['added'][0]['groups'][0]['controls'] == [
        'project.create', 'tools.query.open']
    assert stored['quickAccess'] == ['project.create']
    assert validate('') == ''
    assert 'quickAccess' not in json.loads(validate(doc(tabs={}, added=[])))


@pytest.mark.parametrize('document', [
    '{', json.dumps({'schema': 'other'}), doc(extra=1),
    doc(tabs={'bad id': {}}), doc(tabs={'file': {'colour': 'red'}}),
    doc(tabs={'file': {'hidden': 'yes'}}), doc(tabs={'file': {'order': -1}}),
    doc(tabs={'file': {'order': True}}), doc(tabs={'file': {'label': 'x' * 61}}),
    doc(tabs={'file': {'label': 'a\nb'}}),
    doc(tabs={'file': {'groups': {'g': {'hidden': 1}}}}),
    doc(added=[{'tab': 'x', 'groups': [{'id': 'g', 'controls': ['<script>']}]}]),
    doc(added=[{'tab': 'x', 'groups': [{'id': 'g', 'controls': 'cmd'}]}]),
    doc(added=[{'tab': 'x', 'groups': [{'id': 'g', 'html': '<b>'}]}]),
    doc(added=[{'groups': []}]),
    doc(quickAccess=['ok', 'not ok']),
    doc(quickAccess=['c'] * 201),
    doc(tabs={f't{i}': {} for i in range(41)}),
])
def test_anything_else_is_refused(document):
    with pytest.raises(ValueError, match='not valid'):
        validate(document)
