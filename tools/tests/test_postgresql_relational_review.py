"""Relational PostgreSQL source edits retain exact native catalog provenance."""
from copy import deepcopy
import json
import pytest
from tools.tests.test_postgresql_erd import relation
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export, _json
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.firebird_relational_review import read_relations, handoff


def fixture():
    row = relation(17000, 'public')
    row['native'].update(system_object=False, schema='public', sql_identity='public.same', comment='original')
    return build_export([row], endpoint_id='ep', target_id='postgresql-database:42', generation='g', engine='postgresql')


def edited(snapshot, comment):
    result = deepcopy(snapshot)
    row = read_relations(snapshot, engine='postgresql')['postgresql:pg_class:17000']
    from pgadmin.cdeadmin.workspace.ddn_source import quoted
    old = quoted(row['native_json'])
    new = quoted(_json({**row['native'], 'comment': comment}))
    result['files'] = {name: text.replace(old, new) for name, text in result['files'].items()}
    return result


def test_relational_native_edits_preserve_baseline_and_leave_labels_as_presentation():
    catalog = fixture()
    original = catalog['diagram']['snapshot']
    authored = edited(original, 'changed ü')
    review = handoff(catalog['snapshot'], original, authored, engine='postgresql')
    before, after = (read_catalog(review[key], engine='postgresql') for key in ('baseline', 'desired'))
    assert before['rows']['postgresql:pg_class:17000']['native']['comment'] == 'original'
    assert after['rows']['postgresql:pg_class:17000']['native']['comment'] == 'changed ü'
    assert before['rows'].keys() == after['rows'].keys()
    assert review['changed_resource_ids'] == ['postgresql:pg_class:17000']
    assert review['executed'] is False
    labels = deepcopy(original)
    labels['files'] = {name: text.replace('public.same [table]', 'Presentation label') for name, text in labels['files'].items()}
    assert handoff(catalog['snapshot'], original, labels, engine='postgresql')['changed_resource_ids'] == []


def test_foreign_engine_and_database_are_rejected():
    catalog = fixture(); original = catalog['diagram']['snapshot']
    with pytest.raises(ValueError):
        read_relations(original)
    wrong = deepcopy(original)
    wrong['files'] = {name: text.replace('postgresql:ep:postgresql-database:42:', 'postgresql:ep:postgresql-database:43:') for name, text in original['files'].items()}
    with pytest.raises(ValueError, match='another database'):
        handoff(catalog['snapshot'], original, wrong, engine='postgresql')


def test_live_change_does_not_replace_authored_baseline():
    catalog = fixture(); original = catalog['diagram']['snapshot']
    edited_source = edited(original, 'desired')
    live = deepcopy(catalog['snapshot'])
    live['files'] = {name: text.replace('original', 'live') for name, text in live['files'].items()}
    review = handoff(live, original, edited_source, engine='postgresql')
    assert read_catalog(review['baseline'], engine='postgresql')['rows']['postgresql:pg_class:17000']['native']['comment'] == 'original'
    assert read_catalog(review['desired'], engine='postgresql')['rows']['postgresql:pg_class:17000']['native']['comment'] == 'desired'


def test_graphical_field_nullability_reaches_native_preview():
    catalog = fixture(); original = catalog['diagram']['snapshot']
    authored = deepcopy(original)
    authored['files'] = {name: text.replace('nullable false', 'nullable true') for name, text in original['files'].items()}
    assert authored != original
    result = handoff(catalog['snapshot'], original, authored, engine='postgresql')
    after = read_catalog(result['desired'], engine='postgresql')
    fields = after['rows']['postgresql:pg_class:17000']['native']['children']['pg_attribute']
    assert fields[0]['attnotnull'] is False
    before = read_catalog(result['baseline'], engine='postgresql')
    assert before['rows']['postgresql:pg_class:17000']['native']['children']['pg_attribute'][0]['attnotnull'] is True


def test_graphical_type_change_reaches_native_metadata():
    catalog = fixture(); original = catalog['diagram']['snapshot']
    authored = deepcopy(original)
    authored['files'] = {name: text.replace('datatype "bigint"', 'datatype "text"') for name, text in original['files'].items()}
    assert authored != original
    result = handoff(catalog['snapshot'], original, authored, engine='postgresql')
    after = read_catalog(result['desired'], engine='postgresql')
    assert after['rows']['postgresql:pg_class:17000']['native']['children']['pg_attribute'][0]['formatted_type'] == 'text'


def test_graphical_description_and_native_conflict():
    catalog = fixture(); original = catalog['diagram']['snapshot']
    authored = deepcopy(original)
    authored['files'] = {name: text.replace('description "native ü"', 'description "new description"') for name, text in original['files'].items()}
    result = handoff(catalog['snapshot'], original, authored, engine='postgresql')
    after = read_catalog(result['desired'], engine='postgresql')
    assert after['rows']['postgresql:pg_class:17000']['native']['children']['pg_attribute'][1]['comment'] == 'new description'
    from pgadmin.cdeadmin.workspace.postgresql_relational_fields import merge_fields
    old = read_relations(original, engine='postgresql')['postgresql:pg_class:17000']
    new = read_relations(authored, engine='postgresql')['postgresql:pg_class:17000']
    new['native']['children']['pg_attribute'][1]['comment'] = 'conflicting native edit'
    with pytest.raises(ValueError, match='disagree'):
        merge_fields(old, new)


def test_graphical_property_omission_is_not_drop_intent():
    catalog = fixture(); original = catalog['diagram']['snapshot']
    authored = deepcopy(original)
    authored['files'] = {name: text.replace('nullable false', '') for name, text in original['files'].items()}
    assert handoff(catalog['snapshot'], original, authored, engine='postgresql')['changed_resource_ids'] == []


def with_new_field(snapshot, *, property_text='', uid=None, annotate=True):
    import uuid
    result = deepcopy(snapshot)
    row = read_relations(snapshot, engine='postgresql')['postgresql:pg_class:17000']
    uid = uid or row['uid'] + ':new:' + str(uuid.uuid4())
    from pgadmin.cdeadmin.workspace import ddn_source as ddn
    from hashlib import sha256
    table_id = 'n_' + sha256(b'postgresql:pg_class:17000').hexdigest()
    values = {'datatype': 'numeric(12,2)', 'nullable': True}
    if 'description' in property_text:
        values['description'] = 'must not vanish'
    if 'shape' in property_text:
        values['shape'] = 'array'
    field = ddn.native_field('owned_new', 'added column', uid, values)
    for name, text in result['files'].items():
        # Use the public source edit API for membership, and a typed companion
        # record for the explicit native draft identity required by the provider.
        import subprocess
        request = {'snapshot': {**result, 'files': {**result['files'], name: text + field['source'] + (ddn.annotation(
            'owned_new', 'added column', uid, {'subject_kind': 'field', 'parent_id': table_id,
                'field_properties_json': json.dumps(values)}, 'scratchrobin.postgresql.relations') if annotate else '')}},
            'edits': [{'target': {'file': name, 'id': table_id}, 'path': 'members',
                'value': [ddn.ref('owned_new'), *[ddn.ref(item) for item in ['n_' + sha256((row['resource_id'] + ':' + str(i)).encode()).hexdigest() for i in (1, 2)]]]}]}
        changed = subprocess.run(['node', 'tools/ddn_edit.mjs'], input=json.dumps(request), text=True, capture_output=True, check=True)
        result = json.loads(changed.stdout)
    assert result != snapshot
    return result, uid


def test_new_graphical_field_becomes_explicit_native_creation_draft():
    catalog = fixture(); original = catalog['diagram']['snapshot']
    authored, uid = with_new_field(original)
    result = handoff(catalog['snapshot'], original, authored, engine='postgresql')
    after = read_catalog(result['desired'], engine='postgresql')
    native = after['rows']['postgresql:pg_class:17000']['native']
    assert native['add_columns'] == [{'resource_id': 'postgresql:new:' + uid.rsplit(':', 1)[1],
        'definition': {'name': 'added column', 'data_type': 'numeric(12,2)', 'nullable': True}}]
    assert native['children']['pg_attribute'] == read_relations(original, engine='postgresql')['postgresql:pg_class:17000']['native']['children']['pg_attribute']
    assert result['executed'] is False


@pytest.mark.parametrize('properties', ['description: "must not vanish";', 'shape: array;'])
def test_new_graphical_field_does_not_discard_unadmitted_properties(properties):
    catalog = fixture(); original = catalog['diagram']['snapshot']
    authored, _ = with_new_field(original, property_text=properties)
    with pytest.raises(ValueError, match='unsupported'):
        handoff(catalog['snapshot'], original, authored, engine='postgresql')


def test_new_graphical_field_cannot_cross_parent_identity():
    catalog = fixture(); original = catalog['diagram']['snapshot']
    authored, _ = with_new_field(original, uid='different-parent:new:00000000-0000-4000-8000-000000000001')
    with pytest.raises(ValueError, match='identity reconciliation'):
        handoff(catalog['snapshot'], original, authored, engine='postgresql')


def test_unannotated_sdk_field_gets_stable_parent_scoped_draft_identity():
    catalog = fixture(); original = catalog['diagram']['snapshot']
    authored, _ = with_new_field(original, annotate=False)
    first = handoff(catalog['snapshot'], original, authored, engine='postgresql')
    second = handoff(catalog['snapshot'], original, authored, engine='postgresql')
    one = read_catalog(first['desired'], engine='postgresql')['rows']['postgresql:pg_class:17000']['native']['add_columns']
    two = read_catalog(second['desired'], engine='postgresql')['rows']['postgresql:pg_class:17000']['native']['add_columns']
    assert one == two and len(one) == 1
    assert one[0]['definition'] == {'name': 'added column', 'data_type': 'numeric(12,2)', 'nullable': True}
    assert first['executed'] is False
