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
    with pytest.raises(ValueError, match='drops are not carried'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, table, drop=True, drop_confirmation='child'), engine='sqlite')
    with pytest.raises(ValueError, match='primary key|Primary-key'):
        edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'constraint', 'child_pk',
            {'physical_kind': 'primary-key', 'physical_name': 'child_pk', 'columns_json': '["id"]'}, 'sqlite')
        handoff(env.catalog['snapshot'], diagram['snapshot'], edited, engine='sqlite')


def test_omitted_vocabulary_is_not_deletion_or_clear_intent(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    _, result_plan, _ = env.review(rt.edit_vocabulary(diagram, index, physical_name='child_amount_idx'))
    assert result_plan['operations'] == []


# ------------------------------------------------------------------ renames

def rename_plan(env, result):
    """Diagram handoff -> native rename design (desired DDN) -> native rename plan."""
    from pgadmin.cdeadmin.workspace import sqlite_rename
    baseline = read_catalog(result['baseline'], engine='sqlite')
    desired, selected, _ = sqlite_rename.generate(baseline, result['renames'])
    live = build_export(env.resources(), endpoint_id='e', target_id=TARGET, generation='g2', engine='sqlite', native_model=True)
    return sqlite_rename.plan(baseline, desired, live, selected)


def test_table_and_column_renames_become_native_rename_arguments(env):
    diagram = env.export()
    table, column = env.rid('table', 'child'), env.rid('column', 'note')
    edited = rt.edit_vocabulary(diagram, table, physical_name='kid', rename_from='child')
    edited = rt.edit_vocabulary(diagram, column, snapshot=edited, physical_name='remark', rename_from='note')
    result = handoff(env.catalog['snapshot'], diagram['snapshot'], edited, engine='sqlite')
    assert result['renames'] == [{'kind': 'column', 'table': 'child', 'from': 'note', 'to': 'remark'},
                                 {'kind': 'table', 'table': 'child', 'to': 'kid'}]
    assert result['baseline'] == result['desired']          # SQLite rewrites references itself
    result_plan = rename_plan(env, result)
    assert result_plan['ready_for_review'] and result_plan['application_supported'], result_plan
    for stage in result_plan['operations'][0]['stages']:
        env.connection.execute(stage)
    assert env.connection.execute('SELECT remark FROM kid').fetchall() == []
    assert 'kid' in env.index_sql('child_amount_idx')       # native ALTER rewrote the dependent index


def test_rename_needs_the_exact_baseline_name(env):
    diagram = env.export()
    table = env.rid('table', 'child')
    with pytest.raises(ValueError, match='rename_from'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, table, physical_name='kid'), engine='sqlite')
    with pytest.raises(ValueError, match='rename_from'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, table, physical_name='kid', rename_from='parent'), engine='sqlite')


# ------------------------------------------------------------------ opt-in rebuild-backed constraints

def rebuild_review(env, edited, **options):
    result = handoff(env.catalog['snapshot'], env.diagram['snapshot'], edited, engine='sqlite', **options)
    baseline, desired = (read_catalog(result[key], engine='sqlite') for key in ('baseline', 'desired'))
    live = build_export(env.resources(), endpoint_id='e', target_id=TARGET, generation='g2', engine='sqlite', native_model=True)
    return result, plan(baseline, desired, live, env.connection, rebuilds=result.get('rebuilds', []))


def constraint_edit(env, diagram, drafts):
    table = env.rid('table', 'child')
    edited = diagram['snapshot']
    for title, values in drafts:
        edited, _ = rt.add_draft_element(diagram, edited, table, env.uid(table), 'constraint', title, values, 'sqlite')
    return edited


def test_constraint_additions_need_the_rebuild_opt_in(env):
    diagram = env.export()
    edited = constraint_edit(env, diagram, [('child_note_uq', {'physical_kind': 'unique', 'physical_name': 'child_note_uq',
                                                               'columns_json': '["note"]'})])
    with pytest.raises(ValueError, match='rebuild-backed constraint additions'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], edited, engine='sqlite')
    with pytest.raises(ValueError, match='only for SQLite and DuckDB'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], edited, engine='firebird', allow_rebuilds=True)


def test_unique_and_check_additions_rebuild_the_table_and_keep_rows(env):
    env.connection.execute("INSERT INTO parent VALUES (1, 'p', 'c')")
    env.connection.execute("INSERT INTO child VALUES (10, 1, 5, 'a'), (11, 1, 6, 'b')")
    diagram = env.export()
    edited = constraint_edit(env, diagram, [
        ('child_note_uq', {'physical_kind': 'unique', 'physical_name': 'child_note_uq', 'columns_json': '["note"]'}),
        ('child_amount_ck', {'physical_kind': 'check', 'physical_name': 'child_amount_ck', 'expression': 'amount > 0'})])
    result, result_plan = rebuild_review(env, edited, allow_rebuilds=True)
    assert result['rebuilds'] == [env.rid('table', 'child')]
    assert [item['operation'] for item in result_plan['operations']] == ['rebuild']
    env.execute(result_plan)
    assert env.connection.execute('SELECT id, note FROM child ORDER BY id').fetchall() == [(10, 'a'), (11, 'b')]
    sql = env.connection.execute("SELECT sql FROM sqlite_schema WHERE name='child'").fetchone()[0]
    assert 'child_note_uq' in sql and 'amount > 0' in sql
    with pytest.raises(sqlite3.IntegrityError):
        env.connection.execute("INSERT INTO child VALUES (12, 1, 7, 'a')")
    with pytest.raises(sqlite3.IntegrityError):
        env.connection.execute("INSERT INTO child VALUES (12, 1, -1, 'z')")
    env.export()
    _, again, _ = env.review(env.diagram['snapshot'])
    assert again['operations'] == []


def test_a_constraint_the_existing_rows_violate_is_refused_by_the_rebuild(env):
    env.connection.execute("INSERT INTO parent VALUES (1, 'p', 'c')")
    env.connection.execute("INSERT INTO child VALUES (10, 1, 5, 'dup'), (11, 1, 6, 'dup')")
    diagram = env.export()
    edited = constraint_edit(env, diagram, [('child_note_uq', {'physical_kind': 'unique', 'columns_json': '["note"]'})])
    _, result_plan = rebuild_review(env, edited, allow_rebuilds=True)
    assert result_plan['operations'][0]['operation'] == 'rebuild'     # reviewed; the data check happens at apply
    with pytest.raises(sqlite3.IntegrityError):
        env.execute(result_plan)
    assert env.connection.execute('SELECT count(*) FROM child').fetchone() == (2,)


def test_constraint_drafts_reject_bad_definitions(env):
    diagram = env.export()
    for values, message in (({'physical_kind': 'unique', 'columns_json': '["missing"]'}, 'existing columns'),
                            ({'physical_kind': 'check', 'expression': '1=1; DROP TABLE parent'}, 'one native expression'),
                            ({'physical_kind': 'check', 'expression': 'amount >'}, 'rejected')):
        edited = constraint_edit(env, diagram, [('bad', values)])
        with pytest.raises(ValueError, match=message):
            handoff(env.catalog['snapshot'], diagram['snapshot'], edited, engine='sqlite', allow_rebuilds=True)


def test_foreign_key_addition_rebuilds_the_table(env):
    env.connection.execute('CREATE TABLE ledger(id INTEGER PRIMARY KEY, parent_id INTEGER)')
    env.connection.execute("INSERT INTO parent VALUES (1, 'p', 'c')")
    env.connection.execute('INSERT INTO ledger VALUES (1, 1)')
    diagram = env.export()
    ledger, parent = env.rid('table', 'ledger'), env.rid('table', 'parent')
    edited, _ = rt.add_draft_foreign_key(diagram, diagram['snapshot'], ledger, parent, env.uid(ledger), 'ledger_parent_fk',
        {'physical_kind': 'foreign-key', 'physical_name': 'ledger_parent_fk', 'columns_json': '["parent_id"]',
         'referenced_columns_json': '["id"]', 'on_delete': 'CASCADE'}, 'sqlite')
    result, result_plan = rebuild_review(env, edited, allow_rebuilds=True)
    assert result['rebuilds'] == [ledger]
    env.execute(result_plan)
    assert env.connection.execute('SELECT * FROM ledger').fetchall() == [(1, 1)]
    row = env.connection.execute("PRAGMA foreign_key_list('ledger')").fetchone()
    assert (row[2], row[3], row[4], row[6]) == ('parent', 'parent_id', 'id', 'CASCADE')
    env.export()
    _, again, _ = env.review(env.diagram['snapshot'])
    assert again['operations'] == []
