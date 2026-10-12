"""Relational DDN native facts enter the same explicit catalog review path."""
from copy import deepcopy
import json
import pytest
from tools.tests.test_firebird_erd import fixture, row
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export, _json
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff, read_relations


def capture(rows=None):
    return build_export(rows or fixture(), endpoint_id='endpoint', target_id='db', generation='g')


def edit(snapshot, identity, **changes):
    result = deepcopy(snapshot)
    record = read_relations(snapshot)[identity]
    if record.get('parent_resource_id'):
        parent = read_relations(snapshot)[record['parent_resource_id']]
        native = json.loads(parent['native_json'])
        for item in native['diagram_columns']:
            if item['resource_id'] == identity: item['native'].update(changes)
        before, after = _json(parent['native_json']), _json(_json(native))
    else:
        before = _json(record['native_json']); after = _json(_json({**json.loads(record['native_json']), **changes}))
    count = 0
    for name, source in result['files'].items():
        count += source.count(before)
        result['files'][name] = source.replace(before, after)
    assert count == 1
    return result


def test_native_fields_and_relationships_survive_handoff_and_no_hidden_deletion():
    current = capture(); original = current['diagram']['snapshot']
    mapped = read_relations(original)
    assert len(mapped) == 5  # two relations, two columns and one foreign key
    desired = edit(original, 'column:Child:Exact"A', description='Authored column comment')
    value = handoff(current['snapshot'], original, desired)
    before, after = (read_catalog(value[key]) for key in ('baseline', 'desired'))
    assert set(before['rows']) == set(after['rows'])
    assert after['rows']['column:Child:Exact"A']['native']['description'] == 'Authored column comment'
    assert before['rows']['column:Child:Exact"A']['native'].get('description') is None
    assert value['changed_resource_ids'] == ['column:Child:Exact"A']
    assert not value['executed']
    assert 'source_columns' not in after['rows']['constraint:Child:FK_CHILD']['native']


def test_original_native_facts_are_not_replaced_by_live_changes_and_utf16_offsets_are_exact():
    resources = [row('table', '😀'), row('table', 'Z', description='Original', statistics=0.1)]
    old = capture(resources)
    original = old['diagram']['snapshot']
    desired = edit(original, 'table:Z', description='Authored')
    resources[1]['native']['description'] = 'Concurrent live change'
    current = capture(resources)
    value = handoff(current['snapshot'], original, desired)
    assert read_catalog(value['baseline'])['rows']['table:Z']['native']['description'] == 'Original'
    assert read_catalog(value['desired'])['rows']['table:Z']['native']['description'] == 'Authored'
    assert 'table:😀' in read_catalog(value['desired'])['rows']
    assert str(read_catalog(value['desired'])['rows']['table:Z']['native']['statistics']) == '0.1'


def test_foreign_identity_and_edited_adapter_fields_block_handoff():
    current = capture(); original = current['diagram']['snapshot']
    foreign = deepcopy(original)
    foreign['files'] = {name: source.replace('firebird:endpoint:db:', 'firebird:endpoint:other:') for name, source in foreign['files'].items()}
    with pytest.raises(ValueError, match='another database'):
        handoff(current['snapshot'], original, foreign)
    desired = edit(original, 'constraint:Child:FK_CHILD', source_columns=['other'])
    with pytest.raises(ValueError, match='adapter column'):
        handoff(current['snapshot'], original, desired)


@pytest.mark.parametrize('snapshot', [{}, {'format': 'ddn-workspace@1', 'files': {}, 'entry': 'a', 'view': 'v'},
    {'format': 'ddn-workspace@1', 'files': {'../bad.ddn': ''}, 'entry': '../bad.ddn', 'view': 'v'}])
def test_invalid_source_envelopes_never_reach_native_processing(snapshot):
    with pytest.raises(ValueError): read_relations(snapshot)
