"""The Vitess keyspace VSchema editor: rows, merge, and what it refuses."""
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.vitess import vschema_editor  # noqa: E402
from pgadmin.cdeadmin.providers.vitess.control_plane import (  # noqa: E402
    compile_action,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

SHARDED = {
    'sharded': True,
    'vindexes': {'xxhash': {'type': 'xxhash'},
                 'by_email': {'type': 'lookup_unique', 'owner': 'users',
                              'params': {'table': 'lk.users_email',
                                         'from': 'email',
                                         'to': 'keyspace_id'}}},
    'tables': {'users': {
        'column_vindexes': [{'name': 'xxhash', 'columns': ['id']},
                            {'name': 'by_email', 'column': 'email'}],
        'auto_increment': {'column': 'id', 'sequence': 'lk.user_seq'},
        'columns': [{'name': 'id', 'type': 'INT64'}],
        'column_list_authoritative': True}},
}
LOOKUP = {'tables': {'user_seq': {'type': 'sequence'}, 'countries': {}}}


def test_rows_reopen_every_section_in_primary_order():
    rows = vschema_editor.flatten(SHARDED)
    assert (rows['sharded'], rows['foreign_key_mode'],
            rows['require_explicit_routing']) == (True, 'unspecified', False)
    assert rows['tables'] == [{
        'name': 'users', 'type': '', 'source': '', 'pinned': '',
        'auto_increment_column': 'id', 'auto_increment_sequence':
            'lk.user_seq'}]
    assert rows['table_vindexes'] == [
        {'table': 'users', 'vindex': 'xxhash', 'columns': 'id'},
        {'table': 'users', 'vindex': 'by_email', 'columns': 'email'}]
    assert [row['name'] for row in rows['vindexes']] == ['by_email',
                                                         'xxhash']


def test_merge_replaces_sent_sections_and_keeps_what_the_editor_hides():
    sections = vschema_editor.normalize({'table_vindexes': [
        {'table': 'users', 'vindex': 'by_email', 'columns': 'email'},
        {'table': 'users', 'vindex': 'xxhash', 'columns': 'id'}]})
    merged = vschema_editor.merge(SHARDED, sections)
    users = merged['tables']['users']
    # The primary vindex changed in one apply; nothing else was lost.
    assert [entry['name'] for entry in users['column_vindexes']] == [
        'by_email', 'xxhash']
    assert users['auto_increment'] == SHARDED['tables']['users'][
        'auto_increment']
    assert users['columns'] == [{'name': 'id', 'type': 'INT64'}]
    assert merged['vindexes'] == SHARDED['vindexes']
    assert vschema_editor.applied(sections, merged)
    assert not vschema_editor.applied(sections, SHARDED)


def test_unsent_sections_are_untouched_and_staleness_is_per_section():
    baseline = vschema_editor.flatten(SHARDED)
    sections = vschema_editor.normalize({'require_explicit_routing': True})
    changed = json.loads(json.dumps(SHARDED))
    changed['vindexes']['other'] = {'type': 'hash'}
    # A vindex added elsewhere does not block a settings edit...
    assert vschema_editor.stale_sections(changed, baseline, sections) == []
    merged = vschema_editor.merge(changed, sections)
    assert 'other' in merged['vindexes']
    # ...but blocks an edit of the vindexes it would overwrite.
    vindexes = vschema_editor.normalize({'vindexes': baseline['vindexes']})
    assert vschema_editor.stale_sections(changed, baseline, vindexes) == [
        'vindexes']


@pytest.mark.parametrize('change, reason', [
    ({'tables': [{'name': 'users'}, {'name': 'ref', 'type': 'reference',
                                     'source': 'lk.missing'}]},
     'not a table in that keyspace'),
    ({'tables': [{'name': 'users', 'auto_increment_column': 'id',
                  'auto_increment_sequence': 'lk.countries'}]},
     'is not a sequence'),
    ({'table_vindexes': [{'table': 'users', 'vindex': 'nope',
                          'columns': 'id'}]}, 'is not defined'),
    ({'tables': [{'name': 'users'}, {'name': 'loose'}]},
     'needs a primary vindex'),
    ({'sharded': False}, 'would route every query to one'),
])
def test_refuses_what_vtgate_cannot_serve(change, reason):
    merged = vschema_editor.merge(SHARDED, vschema_editor.normalize(change))
    with pytest.raises(RelationalClientError, match=reason):
        vschema_editor.validate('main', merged, 2, {'lk': LOOKUP})


def test_accepts_a_reference_table_whose_source_is_registered():
    merged = vschema_editor.merge(SHARDED, vschema_editor.normalize({
        'tables': [{'name': 'users', 'auto_increment_column': 'id',
                    'auto_increment_sequence': 'lk.user_seq'},
                   {'name': 'countries', 'type': 'reference',
                    'source': 'lk.countries'}]}))
    text = vschema_editor.validate('main', merged, 2, {'lk': LOOKUP})
    assert json.loads(text)['tables']['countries'] == {
        'type': 'reference', 'source': 'lk.countries'}
    assert vschema_editor.referenced_keyspaces('main', merged) == ['lk']


@pytest.mark.parametrize('draft, reason', [
    ({}, 'nothing to change'),
    ({'foreign_key_mode': 'cascade'}, 'foreign key mode'),
    ({'tables': [{'name': 't', 'pinned': 'zz'}]}, 'hex bytes'),
    ({'tables': [{'name': 't', 'auto_increment_column': 'id'}]},
     'needs both'),
    ({'tables': [{'name': 't', 'source': 'a.b'}]}, 'only for'),
    ({'vindexes': [{'name': 'v', 'type': 'hash'},
                   {'name': 'v', 'type': 'hash'}]}, 'appears twice'),
    ({'table_vindexes': [{'table': 't', 'vindex': 'v', 'columns': ''}]},
     'at least one column'),
])
def test_normalize_refuses_malformed_rows(draft, reason):
    with pytest.raises(RelationalClientError, match=reason):
        vschema_editor.normalize(draft)


def test_oversized_vschema_is_refused_with_the_reason():
    merged = vschema_editor.merge({'sharded': False}, vschema_editor.normalize(
        {'tables': [{'name': f't{index:05d}'} for index in range(4096)]}))
    merged['padding'] = 'x' * vschema_editor.MAX_DOCUMENT_BYTES
    with pytest.raises(RelationalClientError, match='128 KiB'):
        vschema_editor.validate('main', merged, 1, {})


def test_the_plan_carries_the_edit_and_its_baseline_not_a_document():
    target = {'resource_kind': 'vschema', 'display_name': 'main',
              'display_path': ['main', 'VSchema'],
              'native': vschema_editor.flatten(SHARDED)}
    action = compile_action({
        'resource_kind': 'vschema', 'operation_id': 'alter',
        'target_resource': target,
        'draft': {'require_explicit_routing': True, 'cells': ['zone1']},
    })['provider_action']
    assert action['arguments'] == ['ApplyVSchema', 'main']
    edit = action['vschema_edit']
    assert (edit['keyspace'], edit['sections'], edit['cells']) == (
        'main', {'require_explicit_routing': True}, ['zone1'])
    assert edit['baseline'] == target['native']
