"""Shared harness for forward -> edit -> reverse -> plan tests of physical-schema edits.

Edits use DDN's public source-patch API (tools/ddn_edit.mjs) on the x_record vocabulary
of the annotation record that belongs to a diagram element, exactly as a designer
records-table edit would.
"""
import json
import re
import subprocess
import uuid
from pathlib import Path

from pgadmin.cdeadmin.workspace import ddn_source as ddn

ROOT = Path(__file__).resolve().parents[2]
FILE = 'relations.ddn'


def _run(snapshot, edits):
    done = subprocess.run(['node', str(ROOT / 'tools/ddn_edit.mjs')], input=json.dumps({'snapshot': snapshot, 'edits': edits}),
                          text=True, capture_output=True)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def key_of(diagram, resource_id):
    return next(k for k, v in diagram['resource_mapping'].items() if v == resource_id)


def edit_vocabulary(diagram, resource_id, snapshot=None, **values):
    """Edit physical-schema x_record keys of the element mapped to resource_id."""
    key = key_of(diagram, resource_id)
    return _run(snapshot or diagram['snapshot'], [
        {'target': {'file': FILE, 'id': 'relations.mapping_' + key},
         'path': 'metadata.x_record.record.' + name, 'value': value} for name, value in values.items()])


def _members(snapshot, parent_key):
    text = snapshot['files'][FILE]
    start = text.index('element ' + ddn.quoted(parent_key) + ' as ')
    stop = text.find('\nelement ', start + 1)
    block = text[start:stop if stop > 0 else len(text)]
    return re.findall(r'^\s+item\n\s+id "([^"]+)"', block, re.M)


def add_draft_element(diagram, snapshot, parent_resource_id, parent_uid, role, title, values, module):
    """A vocabulary-annotated draft index/constraint, joined to its table through `members`."""
    parent_key = key_of(diagram, parent_resource_id)
    identity = 'draft_' + uuid.uuid4().hex
    uid = parent_uid + ':new:' + str(uuid.uuid4())
    source = ddn.physical_object(identity, title, role, parent_key, uid, values, 'scratchrobin.' + module + '.relations')
    seeded = {**snapshot, 'files': {**snapshot['files'], FILE: snapshot['files'][FILE] + source}}
    refs = [ddn.ref(item) for item in [*_members(seeded, parent_key), identity]]
    return _run(seeded, [{'target': {'file': FILE, 'id': parent_key}, 'path': 'members', 'value': refs}]), uid


def add_draft_foreign_key(diagram, snapshot, source_resource_id, target_resource_id, parent_uid, title, values, module):
    identity = 'draft_' + uuid.uuid4().hex
    uid = parent_uid + ':new:' + str(uuid.uuid4())
    source = ddn.relation_edge(identity, title, key_of(diagram, source_resource_id), key_of(diagram, target_resource_id),
                               uid, {}, 'scratchrobin.' + module + '.relations', values)
    return {**snapshot, 'files': {**snapshot['files'], FILE: snapshot['files'][FILE] + source}}, uid
