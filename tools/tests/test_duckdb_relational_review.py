"""DuckDB reverse DDN: forward ERD -> edited ERD -> desired native model."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.catalog import capture
from pgadmin.cdeadmin.workspace import ddn_source as ddn
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export, native_metadata
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff, read_relations

KINDS = {'table', 'view'}


@pytest.fixture
def catalog(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    connection = duckdb.connect(str(tmp_path / 'source.duckdb'))
    try:
        connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, amount DECIMAL(20,3))')
        connection.execute("COMMENT ON COLUMN parent.name IS 'native ü comment'")
        connection.execute('CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER, note VARCHAR, '
                           'CONSTRAINT fk_parent FOREIGN KEY(parent_id) REFERENCES parent(id))')
        connection.execute('CREATE VIEW names AS SELECT name FROM parent')
        resources = capture(connection)['resources']
    finally:
        connection.close()
    export = build_export(resources, endpoint_id='e', target_id='f',
                          generation='g1', engine='duckdb')
    mapped = set(export['diagram']['resource_mapping'].values())
    return SimpleNamespace(rows=[row for row in resources if row['resource_id'] in mapped and row['resource_kind'] in KINDS],
                           export=export, snapshot=export['snapshot'], original=export['diagram']['snapshot'])


def semantic(model):
    """Catalog rows without source offsets, which move when native JSON is re-serialized."""
    return {key: {name: value for name, value in row.items() if name != 'source_location'}
            for key, row in model['rows'].items()}


def named(catalog, name):
    return next(row for row in catalog.rows if row['display_name'] == name)


def test_forward_reverse_identity_reads_every_native_relation_and_field(catalog):
    result = read_relations(catalog.original, engine='duckdb')
    assert set(result) == {row['resource_id'] for row in catalog.rows}
    assert set(result) <= set(catalog.export['diagram']['resource_mapping'].values())
    assert {row['resource_kind'] for row in catalog.rows} == {'table', 'view'}
    for source in catalog.rows:
        read, native = result[source['resource_id']], native_metadata(source, 'duckdb')
        assert read['native'] == json.loads(json.dumps(native))
        assert read['uid'] == 'duckdb:e:f:' + source['resource_id']
        assert len(read['fields']) == len(native.get('columns', []))
        for column in native.get('columns', []):
            field = read['fields']['duckdb:e:f:' + column['resource_id']]
            assert field['_label'] == column['name']
            assert field['nullable'] == bool(column['nullable'])
            assert field['datatype'] == column['data_type']
            assert field.get('description') == (column.get('comment') or None)
    assert catalog.export['diagram']['foreign_keys'] == 1


def test_unedited_design_round_trips_to_the_source_model(catalog):
    review = handoff(catalog.snapshot, catalog.original, deepcopy(catalog.original), engine='duckdb')
    assert review['changed_resource_ids'] == [] and review['executed'] is False
    source = read_catalog(json.dumps(catalog.snapshot), engine='duckdb')
    for key in ('baseline', 'desired'):
        model = read_catalog(review[key], engine='duckdb')
        assert semantic(model) == semantic(source)
        assert model['provenance'] == source['provenance']


def replace(snapshot, old, new):
    result = deepcopy(snapshot)
    result['files'] = {name: text.replace(old, new) for name, text in result['files'].items()}
    assert result['files'] != snapshot['files']
    return result


def test_native_edit_reaches_only_its_relation_and_labels_stay_presentation(catalog):
    target = named(catalog, 'child')
    row = read_relations(catalog.original, engine='duckdb')[target['resource_id']]
    ddl = 'CREATE TABLE child(id INTEGER, note TEXT)'
    authored = replace(catalog.original, ddn.quoted(row['native_json']),
        ddn.quoted(json.dumps({**row['native'], 'ddl': ddl}, ensure_ascii=False, separators=(',', ':'), sort_keys=True)))
    review = handoff(catalog.snapshot, catalog.original, authored, engine='duckdb')
    assert review['changed_resource_ids'] == [target['resource_id']]
    before, after = (read_catalog(review[key], engine='duckdb')['rows'] for key in ('baseline', 'desired'))
    assert before[target['resource_id']]['native']['ddl'] == target['native']['ddl']
    assert after[target['resource_id']]['native']['ddl'] == ddl
    assert {key for key in before if semantic({'rows': before})[key] != semantic({'rows': after})[key]} == {target['resource_id']}
    relabelled = replace(catalog.original, 'title "' + '.'.join(target['display_path']) + '"', 'title "Presentation label"')
    assert handoff(catalog.snapshot, catalog.original, relabelled, engine='duckdb')['changed_resource_ids'] == []


def test_graphical_field_edit_requires_native_column_review(catalog):
    column = next(item for item in native_metadata(named(catalog, 'parent'), 'duckdb')['columns'] if item['name'] == 'name')
    assert column['nullable'] is False
    source = catalog.original['files']['relations.ddn']
    start = source.index('"n_' + __import__('hashlib').sha256(column['resource_id'].encode()).hexdigest() + '" as "field"')
    block = source[start:source.index('\n\n', start) if '\n\n' in source[start:] else len(source)]
    assert 'nullable false' in block
    authored = replace(catalog.original, block, block.replace('nullable false', 'nullable true'))
    with pytest.raises(ValueError, match='native column definition'):
        handoff(catalog.snapshot, catalog.original, authored, engine='duckdb')


def test_foreign_database_and_engine_are_rejected(catalog):
    wrong = replace(catalog.original, 'duckdb:e:f:', 'duckdb:e:g:')
    with pytest.raises(ValueError):
        handoff(catalog.snapshot, catalog.original, wrong, engine='duckdb')
    with pytest.raises(ValueError):
        read_relations(catalog.original, engine='oracle')
