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
    with pytest.raises(ValueError, match='not carried'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, table, physical_name='kid', rename_from='child'), engine='duckdb')
    partial, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'index', 'p_idx',
        {'physical_kind': 'index', 'physical_name': 'p_idx', 'columns_json': '["note"]', 'predicate': 'note IS NOT NULL'}, 'duckdb')
    with pytest.raises(ValueError, match='partial'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], partial, engine='duckdb')


def test_omitted_vocabulary_is_not_drop_intent(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    _, result_plan = env.review(rt.edit_vocabulary(diagram, index, physical_name='child_amount_idx'))
    assert result_plan['operations'] == []
