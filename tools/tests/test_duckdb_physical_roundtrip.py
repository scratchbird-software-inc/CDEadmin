"""DuckDB forward -> edit -> reverse -> plan -> execute -> re-inspect for index edits.

Real duckdb throughout. Indexes are carried (new index, explicit drop with the exact name);
constraints, renames and replacement are rejected with a reason (see
docs/en_US/ddn_physical_schema_vocabulary.rst).
"""
import pytest

import test_cdeadmin_relational_providers  # noqa: F401  (puts the web tree on sys.path)
import physical_roundtrip as rt
from pgadmin.cdeadmin.providers.duckdb.catalog import capture
from pgadmin.cdeadmin.workspace.duckdb_schema_plan import plan
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff, read_relations

duckdb = pytest.importorskip('duckdb')
TARGET = 'file'


class Env:
    def __init__(self, path):
        self.connection = duckdb.connect(str(path))

    def resources(self):
        return capture(self.connection)['resources']

    def export(self):
        self.catalog = build_export(self.resources(), endpoint_id='e', target_id=TARGET, generation='g1', engine='duckdb')
        self.diagram = self.catalog['diagram']
        return self.diagram

    def rid(self, kind, name):
        rows = [row for row in self.resources() if row['resource_kind'] == kind and row['display_name'] == name]
        assert len(rows) == 1
        return rows[0]['resource_id']

    def uid(self, resource_id):
        return 'duckdb:e:' + TARGET + ':' + resource_id

    def review(self, edited):
        result = handoff(self.catalog['snapshot'], self.diagram['snapshot'], edited, engine='duckdb')
        baseline, desired = (read_catalog(result[key], engine='duckdb') for key in ('baseline', 'desired'))
        live = build_export(self.resources(), endpoint_id='e', target_id=TARGET, generation='g2', engine='duckdb', native_model=True)
        return result, plan(baseline, desired, live)

    def execute(self, result_plan):
        assert result_plan['ready_for_review'] and result_plan['application_supported'], result_plan
        for operation in result_plan['operations']:
            self.connection.execute(operation['source'])

    def index_names(self):
        return sorted(row[0] for row in self.connection.execute('SELECT index_name FROM duckdb_indexes()').fetchall())


@pytest.fixture
def env(tmp_path):
    instance = Env(tmp_path / 'physical.duckdb')
    instance.connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, code VARCHAR)')
    instance.connection.execute('CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER, amount INTEGER, note VARCHAR, '
                                'CONSTRAINT fk_parent FOREIGN KEY(parent_id) REFERENCES parent(id))')
    instance.connection.execute('CREATE INDEX child_amount_idx ON child(amount)')
    yield instance
    instance.connection.close()


def test_forward_emits_index_vocabulary_and_reverse_reads_it(env):
    diagram = env.export()
    rows = read_relations(diagram['snapshot'], engine='duckdb')
    index = rows[env.rid('index', 'child_amount_idx')]
    assert index['physical'] == {'physical_kind': 'index', 'physical_name': 'child_amount_idx',
                                 'columns_json': '["amount"]', 'unique': False}
    assert index['parent_resource_id'] == env.rid('table', 'child')
    assert [row['physical']['physical_name'] for row in rows.values() if row.get('physical')] == ['child_amount_idx']


def test_unedited_diagram_has_nothing_to_plan(env):
    env.export()
    _, result_plan = env.review(env.diagram['snapshot'])
    assert result_plan['operations'] == [] and result_plan['blockers'] == [] and result_plan['conflicts'] == []


def test_new_index_from_annotated_draft(env):
    diagram = env.export()
    table = env.rid('table', 'child')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'index', 'child_note_idx',
        {'physical_kind': 'index', 'physical_name': 'child_note_idx', 'columns_json': '["note"]', 'unique': True}, 'duckdb')
    result, result_plan = env.review(edited)
    assert len(result['changed_resource_ids']) == 1
    assert [item['operation'] for item in result_plan['operations']] == ['create']
    assert result_plan['operations'][0]['source'].startswith('CREATE UNIQUE INDEX "child_note_idx" ON ')
    env.execute(result_plan)
    assert 'child_note_idx' in env.index_names()
    env.export()
    _, again = env.review(env.diagram['snapshot'])
    assert again['operations'] == []


def test_index_drop_needs_the_exact_name_and_is_planned_as_a_drop(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    for values in ({'drop': True}, {'drop': True, 'drop_confirmation': 'other'}):
        with pytest.raises(ValueError, match='drop_confirmation'):
            handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, index, **values), engine='duckdb')
    _, result_plan = env.review(rt.edit_vocabulary(diagram, index, drop=True, drop_confirmation='child_amount_idx'))
    assert [item['operation'] for item in result_plan['operations']] == ['drop']
    assert result_plan['operations'][0]['source'].endswith('RESTRICT')
    env.execute(result_plan)
    assert 'child_amount_idx' not in env.index_names()


def test_replacement_is_a_drop_plus_a_new_index_under_a_new_name(env):
    diagram = env.export()
    index, table = env.rid('index', 'child_amount_idx'), env.rid('table', 'child')
    with pytest.raises(ValueError, match='no index replacement'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, index, unique=True), engine='duckdb')
    edited = rt.edit_vocabulary(diagram, index, drop=True, drop_confirmation='child_amount_idx')
    edited, _ = rt.add_draft_element(diagram, edited, table, env.uid(table), 'index', 'child_amount_uq',
        {'physical_kind': 'index', 'physical_name': 'child_amount_uq', 'columns_json': '["amount"]', 'unique': True}, 'duckdb')
    _, result_plan = env.review(edited)
    assert sorted(item['operation'] for item in result_plan['operations']) == ['create', 'drop']
    env.execute(result_plan)
    assert env.index_names() == ['child_amount_uq']


def test_uncarried_edits_fail_loudly_instead_of_vanishing(env):
    diagram = env.export()
    index, table = env.rid('index', 'child_amount_idx'), env.rid('table', 'child')
    with pytest.raises(ValueError, match='not carried'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, index, physical_name='renamed', rename_from='child_amount_idx'), engine='duckdb')
    with pytest.raises(ValueError, match='drops are not carried'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, table, drop=True, drop_confirmation='child'), engine='duckdb')
    partial, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'index', 'p_idx',
        {'physical_kind': 'index', 'physical_name': 'p_idx', 'columns_json': '["note"]', 'predicate': 'note IS NOT NULL'}, 'duckdb')
    with pytest.raises(ValueError, match='partial'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], partial, engine='duckdb')


def test_omitted_vocabulary_is_not_drop_intent(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    _, result_plan = env.review(rt.edit_vocabulary(diagram, index, physical_name='child_amount_idx'))
    assert result_plan['operations'] == []


# ------------------------------------------------------------------ renames and primary keys

def test_table_rename_with_explicit_mapping(env):
    # DuckDB itself refuses to rename a table that an index depends on, so use an index-free table.
    env.connection.execute('CREATE TABLE loose(a INTEGER)')
    diagram = env.export()
    table = env.rid('table', 'loose')
    for values in ({'physical_name': 'kid'}, {'physical_name': 'kid', 'rename_from': 'other'}):
        with pytest.raises(ValueError, match='rename_from'):
            handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, table, **values), engine='duckdb')
    result, result_plan = env.review(rt.edit_vocabulary(diagram, table, physical_name='kid', rename_from='loose'))
    assert [item['operation'] for item in result_plan['operations']] == ['rename']
    assert result_plan['operations'][0]['source'].endswith('RENAME TO "kid"')
    env.execute(result_plan)
    assert env.connection.execute('SELECT count(*) FROM kid').fetchone() == (0,)
    env.export()
    _, again = env.review(env.diagram['snapshot'])
    assert again['operations'] == []


def test_column_rename_from_the_field_record(env):
    env.connection.execute('CREATE TABLE loose(a INTEGER, label VARCHAR)')  # DuckDB refuses ALTER on indexed tables
    diagram = env.export()
    column = env.rid('column', 'label')
    edited = rt.edit_vocabulary(diagram, column, physical_name='remark', rename_from='label')
    result, result_plan = env.review(edited)
    assert [item['operation'] for item in result_plan['operations']] == ['rename']
    assert 'RENAME COLUMN "label" TO "remark"' in result_plan['operations'][0]['source']
    env.execute(result_plan)
    assert env.connection.execute('SELECT remark FROM loose').fetchall() == []


def test_rename_cannot_hide_other_vocabulary_or_a_drop(env):
    diagram = env.export()
    column = env.rid('column', 'note')  # child.note
    with pytest.raises(ValueError, match='drops are not carried'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, column, drop=True, drop_confirmation='note'), engine='duckdb')
    with pytest.raises(ValueError, match='only an explicit rename|Only an explicit rename'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, column, unique=True), engine='duckdb')


def test_primary_key_draft_on_a_table_without_a_key(env):
    env.connection.execute('CREATE TABLE keyless(a INTEGER NOT NULL, b VARCHAR)')
    diagram = env.export()
    table = env.rid('table', 'keyless')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'constraint', 'keyless_pkey',
        {'physical_kind': 'primary-key', 'physical_name': 'keyless_pkey', 'columns_json': '["a"]'}, 'duckdb')
    result, result_plan = env.review(edited)
    assert [item['operation'] for item in result_plan['operations']] == ['alter']
    assert result_plan['operations'][0]['source'].endswith('ADD PRIMARY KEY ("a")')
    env.execute(result_plan)
    assert env.connection.execute('SELECT count(*) FROM duckdb_constraints() WHERE constraint_type=\'PRIMARY KEY\' AND table_name=\'keyless\'').fetchone() == (1,)
    # A table that already has a key refuses a second one.
    again = env.export()
    parent = env.rid('table', 'parent')
    edited, _ = rt.add_draft_element(again, again['snapshot'], parent, env.uid(parent), 'constraint', 'parent_pk2',
        {'physical_kind': 'primary-key', 'physical_name': 'parent_pk2', 'columns_json': '["code"]'}, 'duckdb')
    with pytest.raises(ValueError, match='without a key'):
        handoff(env.catalog['snapshot'], again['snapshot'], edited, engine='duckdb')
