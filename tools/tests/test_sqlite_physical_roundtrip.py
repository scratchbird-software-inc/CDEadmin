"""SQLite forward -> edit -> reverse -> plan -> execute -> re-inspect for index edits.

Real sqlite3 throughout. Only indexes are carried from the diagram for SQLite; constraint,
rename and deletion edits are rejected with a reason rather than guessed (see
docs/en_US/ddn_physical_schema_vocabulary.rst).
"""
import sqlite3

import pytest

import test_cdeadmin_relational_providers  # noqa: F401  (puts the web tree on sys.path)
import physical_roundtrip as rt
from pgadmin.cdeadmin.providers.sqlite.provider import _resources
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff, read_relations
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import plan

TARGET = 'file'
KINDS = {'table', 'view', 'virtual-table', 'fts-table', 'index'}


class Env:
    def __init__(self, path):
        self.path = path
        self.connection = sqlite3.connect(path, isolation_level=None)

    def resources(self):
        return _resources(self.connection, {})

    def export(self):
        self.catalog = build_export(self.resources(), endpoint_id='e', target_id=TARGET, generation='g1',
                                    refreshed=True, engine='sqlite')
        self.diagram = self.catalog['diagram']
        return self.diagram

    def rid(self, kind, name):
        rows = [row for row in self.resources() if row['resource_kind'] == kind and row['display_name'] == name]
        assert len(rows) == 1
        return rows[0]['resource_id']

    def uid(self, resource_id):
        return 'sqlite:e:' + TARGET + ':' + resource_id

    def review(self, edited):
        result = handoff(self.catalog['snapshot'], self.diagram['snapshot'], edited, engine='sqlite')
        baseline, desired = (read_catalog(result[key], engine='sqlite') for key in ('baseline', 'desired'))
        live = build_export(self.resources(), endpoint_id='e', target_id=TARGET, generation='g2', engine='sqlite', native_model=True)
        return result, plan(baseline, desired, live, self.connection), (baseline, desired)

    def execute(self, result_plan):
        assert result_plan['ready_for_review'] and result_plan['application_supported'], result_plan
        for operation in result_plan['operations']:
            for stage in operation.get('stages') or [operation['source']]:
                self.connection.execute(stage)

    def index_sql(self, name):
        row = self.connection.execute("SELECT sql FROM sqlite_schema WHERE type='index' AND name=?", (name,)).fetchone()
        return row[0] if row else None


@pytest.fixture
def env(tmp_path):
    instance = Env(tmp_path / 'physical.sqlite')
    instance.connection.executescript('''
        CREATE TABLE parent(id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT);
        CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER, amount INTEGER, note TEXT,
            CONSTRAINT fk_parent FOREIGN KEY(parent_id) REFERENCES parent(id) ON DELETE CASCADE);
        CREATE INDEX child_amount_idx ON child(amount);
    ''')
    yield instance
    instance.connection.close()


def test_forward_emits_index_vocabulary_and_reverse_reads_it(env):
    diagram = env.export()
    rows = read_relations(diagram['snapshot'], engine='sqlite')
    index = rows[env.rid('index', 'child_amount_idx')]
    assert index['physical'] == {'physical_kind': 'index', 'physical_name': 'child_amount_idx',
                                 'columns_json': '["amount"]', 'unique': False}
    assert index['parent_resource_id'] == env.rid('table', 'child')
    # Constraint-backed autoindexes and the primary key are not diagram indexes.
    assert [row['physical']['physical_name'] for row in rows.values() if row.get('physical')] == ['child_amount_idx']


def test_unedited_diagram_has_nothing_to_plan(env):
    env.export()
    _, result_plan, _ = env.review(env.diagram['snapshot'])
    assert result_plan['operations'] == [] and result_plan['blockers'] == [] and result_plan['conflicts'] == []


def test_index_columns_uniqueness_and_predicate_replace_it(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    edited = rt.edit_vocabulary(diagram, index, columns_json='["amount","note"]', unique=True, predicate='note IS NOT NULL')
    result, result_plan, (_, desired) = env.review(edited)
    assert result['changed_resource_ids'] == [index]
    assert [item['operation'] for item in result_plan['operations']] == ['replace']
    env.execute(result_plan)
    sql = env.index_sql('child_amount_idx')
    assert 'UNIQUE' in sql.upper() and 'note IS NOT NULL' in sql
    # Re-inspection equals the desired native row.
    live = build_export(env.resources(), endpoint_id='e', target_id=TARGET, generation='g3', engine='sqlite', native_model=True)
    assert live['rows'][index]['native']['catalog_metadata'] == desired['rows'][index]['native']['catalog_metadata']


def test_new_index_from_annotated_draft(env):
    diagram = env.export()
    table = env.rid('table', 'child')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'index', 'child_note_idx',
        {'physical_kind': 'index', 'physical_name': 'child_note_idx', 'columns_json': '["note"]', 'unique': True}, 'sqlite')
    result, result_plan, _ = env.review(edited)
    assert len(result['changed_resource_ids']) == 1
    assert [item['operation'] for item in result_plan['operations']] == ['create']
    env.execute(result_plan)
    assert 'UNIQUE' in env.index_sql('child_note_idx').upper()


def test_unknown_column_and_dangerous_predicate_are_rejected(env):
    diagram = env.export()
    table = env.rid('table', 'child')
    unknown, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'index', 'bad_idx',
        {'physical_kind': 'index', 'physical_name': 'bad_idx', 'columns_json': '["missing"]'}, 'sqlite')
    with pytest.raises(ValueError, match='existing columns'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], unknown, engine='sqlite')
    hostile, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'index', 'bad_idx',
        {'physical_kind': 'index', 'physical_name': 'bad_idx', 'columns_json': '["note"]', 'predicate': '1=1; DROP TABLE parent'}, 'sqlite')
    with pytest.raises(ValueError, match='one native statement|rejected'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], hostile, engine='sqlite')


def test_uncarried_edits_fail_loudly_instead_of_vanishing(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    for values, message in (({'physical_name': 'renamed', 'rename_from': 'child_amount_idx'}, 'not carried'),
                            ({'drop': True, 'drop_confirmation': 'child_amount_idx'}, 'not carried')):
        with pytest.raises(ValueError, match=message):
            handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, index, **values), engine='sqlite')
    table = env.rid('table', 'child')
    with pytest.raises(ValueError, match='not carried'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, table, physical_name='kid', rename_from='child'), engine='sqlite')


def test_omitted_vocabulary_is_not_deletion_or_clear_intent(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    _, result_plan, _ = env.review(rt.edit_vocabulary(diagram, index, physical_name='child_amount_idx'))
    assert result_plan['operations'] == []
