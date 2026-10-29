"""Live PostgreSQL forward -> edit -> reverse -> plan -> apply -> re-plan for physical-schema edits.

Needs a PostgreSQL server (QA_PG_PORT, default 54329, superuser qa). Each test builds a
private schema, draws the ERD, edits the x_record vocabulary through DDN's public source
API, hands the edit to the reviewed-plan machinery, executes the planned statements on the
live server and proves the result converges (re-planning yields nothing to do).
"""
import json
import os
import uuid

import pytest

psycopg = pytest.importorskip('psycopg')

import test_cdeadmin_relational_providers  # noqa: F401,E402  (puts the web tree on sys.path)
import physical_roundtrip as rt  # noqa: E402
from pgadmin.cdeadmin.providers.postgresql import catalog_capture as capture  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff, read_relations  # noqa: E402
from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan  # noqa: E402

TARGET = 'postgresql-database:1'


class Env:
    def __init__(self, connection, schema):
        self.connection, self.schema = connection, schema
        self.database = connection.execute("SELECT oid FROM pg_database WHERE datname = current_database()").fetchone()[0]

    def sql(self, statement):
        self.connection.execute(statement.replace('S.', self.schema + '.'))

    def resources(self):
        original = capture.GLOBAL
        # Subscriptions read PostgreSQL 17+ columns; this container runs 16.
        capture.GLOBAL = tuple(item for item in original if item[0] != 'pg_subscription')
        try:
            captured = capture.capture(self.connection, self.database)
        finally:
            capture.GLOBAL = original
        return [row for row in captured['resources'] if row['resource_kind'] == 'database' or
                (len(row['display_path']) > 1 and row['display_path'][1] == self.schema)]

    def export(self):
        self.catalog = build_export(self.resources(), endpoint_id='ep', target_id=TARGET, generation='g1', engine='postgresql')
        self.diagram = self.catalog['diagram']
        return self.diagram

    def rid(self, kind, name):
        rows = [row for row in self.resources() if row['resource_kind'] == kind and row['display_name'] == name]
        assert len(rows) == 1, (kind, name, len(rows))
        return rows[0]['resource_id']

    def uid(self, resource_id):
        return 'postgresql:ep:' + TARGET + ':' + resource_id

    def review(self, edited):
        result = handoff(self.catalog['snapshot'], self.diagram['snapshot'], edited, engine='postgresql')
        self.pair = (read_catalog(result['baseline'], engine='postgresql'), read_catalog(result['desired'], engine='postgresql'))
        return result, self.plan()

    def plan(self):
        current = build_export(self.resources(), endpoint_id='ep', target_id=TARGET, generation='g2',
                               engine='postgresql', native_model=True)
        return build_plan(self.pair[0], self.pair[1], current)

    def apply(self, plan):
        assert plan['ready_for_review'] and plan['application_supported'], plan['blockers']
        for operation in plan['operations']:
            self.connection.execute(operation['statement'])

    def settle(self, plan):
        """Apply, then re-plan against the new live state: nothing may remain."""
        self.apply(plan)
        again = self.plan()
        assert again['blockers'] == [] and again['operations'] == [], again
        return again


@pytest.fixture
def env():
    try:
        connection = psycopg.connect(host='127.0.0.1', port=int(os.environ.get('QA_PG_PORT', '54329')),
                                     user='qa', dbname='postgres', autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as error:
        pytest.skip('PostgreSQL unavailable: ' + str(error)[:80])
    schema = 'physrt_' + uuid.uuid4().hex[:8]
    connection.execute('CREATE SCHEMA ' + schema)
    instance = Env(connection, schema)
    instance.sql('''CREATE TABLE S.parent(id integer PRIMARY KEY, code text, region text, CONSTRAINT parent_code_key UNIQUE (code))''')
    instance.sql('''CREATE TABLE S.child(id integer NOT NULL, parent_id integer, amount integer, note text,
        CONSTRAINT child_amount_check CHECK (amount > 0),
        CONSTRAINT child_parent_fk FOREIGN KEY (parent_id) REFERENCES S.parent(id) ON DELETE CASCADE ON UPDATE RESTRICT)''')
    instance.sql('CREATE INDEX child_amount_idx ON S.child (amount)')
    try:
        yield instance
    finally:
        connection.execute('DROP SCHEMA ' + schema + ' CASCADE')
        connection.close()


def operations(plan, *kinds):
    return [item['operation'] for item in plan['operations'] if not kinds or item['operation'] in kinds]


def statements(plan):
    # Identifier quoting is the generator's concern; compare the shape of the statement.
    return [item['statement'].replace('"', '') for item in plan['operations']]


# ------------------------------------------------------------------ forward/reverse

def test_forward_emits_vocabulary_for_every_physical_object(env):
    diagram = env.export()
    rows = read_relations(diagram['snapshot'], engine='postgresql')
    physical = {row['physical']['physical_name']: row['physical'] for row in rows.values() if row.get('physical')}
    assert physical['child_amount_idx'] == {'physical_kind': 'index', 'physical_name': 'child_amount_idx',
        'columns_json': '["amount"]', 'unique': False, 'method': 'btree'}
    assert physical['parent_pkey']['physical_kind'] == 'primary-key' and physical['parent_pkey']['columns_json'] == '["id"]'
    assert physical['parent_code_key']['physical_kind'] == 'unique'
    assert physical['child_amount_check'] == {'physical_kind': 'check', 'physical_name': 'child_amount_check', 'expression': '(amount > 0)'}
    fk = physical['child_parent_fk']
    assert (fk['on_delete'], fk['on_update'], fk['referenced_columns_json']) == ('CASCADE', 'RESTRICT', '["id"]')
    fk_row = rows[env.rid('constraint', 'child_parent_fk')]
    assert fk_row['endpoints'] == {'source': env.rid('table', 'child'), 'target': env.rid('table', 'parent')}
    # Constraint-backed indexes are the constraint, not a second object.
    assert 'parent_pkey' in physical and sum(1 for row in rows.values() if row.get('physical', {}).get('physical_name') == 'parent_pkey') == 1
    assert physical['child'] == {'physical_name': 'child'}


def test_unedited_diagram_yields_an_empty_plan(env):
    diagram = env.export()
    _, plan = env.review(diagram['snapshot'])
    assert plan['operations'] == [] and plan['blockers'] == []


def test_omitted_vocabulary_is_never_a_drop_or_clear(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    edited = rt.edit_vocabulary(diagram, index, physical_name='child_amount_idx')
    _, plan = env.review(edited)
    assert plan['operations'] == [] and plan['blockers'] == []


# ------------------------------------------------------------------ indexes

def test_index_columns_and_uniqueness_replace_it(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    edited = rt.edit_vocabulary(diagram, index, columns_json='["amount","note"]', unique=True)
    result, plan = env.review(edited)
    assert result['changed_resource_ids'] == [index]
    assert operations(plan) == ['drop_index', 'add_index']
    assert plan['operations'][0]['replacement'] is True and 'destructive' not in plan['operations'][0]
    assert statements(plan)[1].startswith('CREATE UNIQUE INDEX child_amount_idx ON ' + env.schema + '.child USING btree (amount, note)')
    env.settle(plan)
    assert env.connection.execute("SELECT indisunique FROM pg_index WHERE indexrelid = %s::regclass",
                                  (env.schema + '.child_amount_idx',)).fetchone() == (True,)


def test_index_partial_predicate_and_method(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    edited = rt.edit_vocabulary(diagram, index, method='hash', columns_json='["note"]', predicate='note IS NOT NULL')
    _, plan = env.review(edited)
    assert 'USING hash (note) WHERE (note IS NOT NULL)' in statements(plan)[1]
    env.settle(plan)


def test_new_index_from_annotated_draft(env):
    diagram = env.export()
    table = env.rid('table', 'child')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'index', 'child_note_idx',
        {'physical_kind': 'index', 'physical_name': 'child_note_idx', 'columns_json': '["note"]', 'unique': False, 'method': 'btree'},
        'postgresql')
    _, plan = env.review(edited)
    assert operations(plan) == ['add_index'] and plan['counts']['proposed_creations'] == 1
    env.settle(plan)


def test_index_rename_needs_an_explicit_mapping(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    with pytest.raises(ValueError, match='explicit rename_from'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, index, physical_name='renamed_idx'), engine='postgresql')
    with pytest.raises(ValueError, match='does not name the baseline'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, index, physical_name='renamed_idx', rename_from='something_else'), engine='postgresql')
    edited = rt.edit_vocabulary(diagram, index, physical_name='renamed_idx', rename_from='child_amount_idx')
    _, plan = env.review(edited)
    assert operations(plan) == ['rename_index']
    assert statements(plan) == ['ALTER INDEX ' + env.schema + '.child_amount_idx RENAME TO renamed_idx']
    env.settle(plan)


def test_index_drop_needs_exact_confirmation_and_is_flagged(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    with pytest.raises(ValueError, match='drop_confirmation'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, index, drop=True), engine='postgresql')
    with pytest.raises(ValueError, match='drop_confirmation'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, index, drop=True, drop_confirmation='other'), engine='postgresql')
    edited = rt.edit_vocabulary(diagram, index, drop=True, drop_confirmation='child_amount_idx')
    _, plan = env.review(edited)
    assert operations(plan) == ['drop_index']
    assert plan['operations'][0]['destructive'] is True and plan['operations'][0]['confirmation'] == 'child_amount_idx'
    assert statements(plan) == ['DROP INDEX ' + env.schema + '.child_amount_idx RESTRICT']
    env.settle(plan)


def test_live_drift_blocks_instead_of_overwriting(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    edited = rt.edit_vocabulary(diagram, index, unique=True)
    env.sql('ALTER INDEX S.child_amount_idx RENAME TO drifted_idx')
    _, plan = env.review(edited)
    assert plan['operations'] == [] and 'changed independently' in plan['blockers'][0]['reason']


def test_replaced_or_dropped_live_object_is_not_resurrected(env):
    diagram = env.export()
    index = env.rid('index', 'child_amount_idx')
    edited = rt.edit_vocabulary(diagram, index, unique=True)
    env.sql('DROP INDEX S.child_amount_idx')
    _, plan = env.review(edited)
    assert plan['operations'] == [] and 'no longer exists' in plan['blockers'][0]['reason']


# ------------------------------------------------------------------ UNIQUE / CHECK / PRIMARY KEY

def test_unique_constraint_columns_rename_and_drop(env):
    diagram = env.export()
    unique = env.rid('constraint', 'parent_code_key')
    edited = rt.edit_vocabulary(diagram, unique, columns_json='["code","region"]')
    _, plan = env.review(edited)
    assert operations(plan) == ['drop_constraint', 'add_constraint']
    assert 'ADD CONSTRAINT parent_code_key UNIQUE (code, region)' in statements(plan)[1]
    env.settle(plan)


def test_unique_constraint_rename_and_drop(env):
    diagram = env.export()
    unique = env.rid('constraint', 'parent_code_key')
    _, plan = env.review(rt.edit_vocabulary(diagram, unique, physical_name='parent_code_uq', rename_from='parent_code_key'))
    assert statements(plan) == ['ALTER TABLE ONLY ' + env.schema + '.parent RENAME CONSTRAINT parent_code_key TO parent_code_uq']
    env.settle(plan)
    diagram = env.export()
    unique = env.rid('constraint', 'parent_code_uq')
    _, plan = env.review(rt.edit_vocabulary(diagram, unique, drop=True, drop_confirmation='parent_code_uq'))
    assert operations(plan) == ['drop_constraint'] and plan['operations'][0]['destructive'] is True
    env.settle(plan)


def test_new_unique_constraint_draft(env):
    diagram = env.export()
    table = env.rid('table', 'child')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'constraint', 'child_id_uq',
        {'physical_kind': 'unique', 'physical_name': 'child_id_uq', 'columns_json': '["id"]'}, 'postgresql')
    _, plan = env.review(edited)
    assert operations(plan) == ['add_constraint'] and 'UNIQUE (id)' in statements(plan)[0]
    env.settle(plan)


def test_check_expression_edit_rename_and_new_check(env):
    diagram = env.export()
    check = env.rid('constraint', 'child_amount_check')
    _, plan = env.review(rt.edit_vocabulary(diagram, check, expression='amount >= 10'))
    assert operations(plan) == ['drop_constraint', 'add_constraint']
    assert 'CHECK (amount >= 10)' in statements(plan)[1]
    env.settle(plan)
    with pytest.raises(Exception):
        env.sql('INSERT INTO S.child(id, amount) VALUES (1, 5)')
    diagram = env.export()
    table = env.rid('table', 'child')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'constraint', 'child_note_check',
        {'physical_kind': 'check', 'physical_name': 'child_note_check', 'expression': "note <> ''"}, 'postgresql')
    _, plan = env.review(edited)
    assert operations(plan) == ['add_constraint']
    env.settle(plan)


def test_invalid_check_expression_is_a_blocker_not_sql(env):
    diagram = env.export()
    check = env.rid('constraint', 'child_amount_check')
    _, plan = env.review(rt.edit_vocabulary(diagram, check, expression='1); DROP TABLE S.child; --'))
    assert plan['operations'] == [] and plan['blockers']


def test_primary_key_add_replace_rename_and_referenced_block(env):
    diagram = env.export()
    table = env.rid('table', 'child')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'constraint', 'child_pkey',
        {'physical_kind': 'primary-key', 'physical_name': 'child_pkey', 'columns_json': '["id"]'}, 'postgresql')
    _, plan = env.review(edited)
    assert 'PRIMARY KEY (id)' in statements(plan)[0]
    env.settle(plan)
    diagram = env.export()
    pkey = env.rid('constraint', 'child_pkey')
    _, plan = env.review(rt.edit_vocabulary(diagram, pkey, columns_json='["id","parent_id"]'))
    assert operations(plan) == ['drop_constraint', 'add_constraint']
    env.settle(plan)
    # parent_pkey backs child_parent_fk: replacing it alone is refused before any SQL.
    diagram = env.export()
    parent_key = env.rid('constraint', 'parent_pkey')
    _, plan = env.review(rt.edit_vocabulary(diagram, parent_key, columns_json='["id","code"]'))
    assert plan['operations'] == [] and 'Foreign keys depend' in plan['blockers'][0]['reason']


def test_second_primary_key_is_refused(env):
    diagram = env.export()
    table = env.rid('table', 'parent')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'constraint', 'parent_pkey2',
        {'physical_kind': 'primary-key', 'physical_name': 'parent_pkey2', 'columns_json': '["code"]'}, 'postgresql')
    _, plan = env.review(edited)
    assert plan['operations'] == [] and 'already has a PRIMARY KEY' in plan['blockers'][0]['reason']


# ------------------------------------------------------------------ FOREIGN KEY

def test_foreign_key_actions_columns_and_rename(env):
    diagram = env.export()
    fk = env.rid('constraint', 'child_parent_fk')
    _, plan = env.review(rt.edit_vocabulary(diagram, fk, on_delete='SET NULL', on_update='CASCADE'))
    assert operations(plan) == ['drop_constraint', 'add_constraint']
    assert 'ON UPDATE CASCADE ON DELETE SET NULL' in statements(plan)[1]
    env.settle(plan)
    row = env.connection.execute("SELECT confdeltype, confupdtype FROM pg_constraint WHERE conname = 'child_parent_fk' AND connamespace = %s::regnamespace",
                                 (env.schema,)).fetchone()
    assert row == ('n', 'c')
    diagram = env.export()
    fk = env.rid('constraint', 'child_parent_fk')
    _, plan = env.review(rt.edit_vocabulary(diagram, fk, physical_name='child_parent_ref', rename_from='child_parent_fk'))
    assert operations(plan) == ['rename_constraint']
    env.settle(plan)


def test_foreign_key_invalid_action_and_unreferenceable_target_are_rejected(env):
    diagram = env.export()
    fk = env.rid('constraint', 'child_parent_fk')
    with pytest.raises(ValueError, match='action'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, fk, on_delete='EXPLODE'), engine='postgresql')
    _, plan = env.review(rt.edit_vocabulary(diagram, fk, referenced_columns_json='["code","region"]', columns_json='["parent_id","note"]'))
    assert plan['operations'] == [] and plan['blockers']


def test_new_foreign_key_draft_edge(env):
    diagram = env.export()
    child, parent = env.rid('table', 'child'), env.rid('table', 'parent')
    edited, _ = rt.add_draft_foreign_key(diagram, diagram['snapshot'], child, parent, env.uid(child), 'child_id_fk',
        {'physical_kind': 'foreign-key', 'physical_name': 'child_id_fk', 'columns_json': '["id"]',
         'referenced_columns_json': '["id"]', 'on_delete': 'RESTRICT', 'on_update': 'NO ACTION'}, 'postgresql')
    _, plan = env.review(edited)
    assert operations(plan) == ['add_constraint']
    assert 'FOREIGN KEY (id) REFERENCES ' + env.schema + '.parent (id)' in statements(plan)[0]
    env.settle(plan)


def test_foreign_key_drop_with_confirmation(env):
    diagram = env.export()
    fk = env.rid('constraint', 'child_parent_fk')
    _, plan = env.review(rt.edit_vocabulary(diagram, fk, drop=True, drop_confirmation='child_parent_fk'))
    assert operations(plan) == ['drop_constraint'] and plan['operations'][0]['destructive'] is True
    env.settle(plan)


# ------------------------------------------------------------------ renames and drops

def test_column_then_table_rename_with_explicit_mapping(env):
    diagram = env.export()
    table = env.rid('table', 'child')
    field_key = rt.key_of(diagram, table + ':4')
    snapshot = rt._run(diagram['snapshot'], [
        {'target': {'file': rt.FILE, 'id': 'relations.mapping_' + field_key}, 'path': 'metadata.x_record.record.' + name, 'value': value}
        for name, value in (('physical_name', 'memo'), ('rename_from', 'note'))])
    _, plan = env.review(snapshot)
    assert operations(plan) == ['rename_column']
    assert statements(plan) == ['ALTER TABLE ONLY ' + env.schema + '.child RENAME COLUMN note TO memo']
    env.settle(plan)
    # A relation rename is reviewed on its own (the existing relation-rename rule).
    diagram = env.export()
    table = env.rid('table', 'child')
    _, plan = env.review(rt.edit_vocabulary(diagram, table, physical_name='kid', rename_from='child'))
    assert operations(plan) == ['rename_relation']
    env.settle(plan)
    assert env.connection.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema = %s AND table_name = 'kid' AND column_name = 'memo'",
                                  (env.schema,)).fetchone() == (1,)


def test_combined_table_and_column_rename_is_blocked_not_guessed(env):
    diagram = env.export()
    table = env.rid('table', 'child')
    field_key = rt.key_of(diagram, table + ':4')
    snapshot = rt.edit_vocabulary(diagram, table, physical_name='kid', rename_from='child')
    snapshot = rt._run(snapshot, [
        {'target': {'file': rt.FILE, 'id': 'relations.mapping_' + field_key}, 'path': 'metadata.x_record.record.' + name, 'value': value}
        for name, value in (('physical_name', 'memo'), ('rename_from', 'note'))])
    _, plan = env.review(snapshot)
    assert plan['operations'] == [] and 'separately' in plan['blockers'][0]['reason']


def test_name_change_without_mapping_is_never_inferred_as_rename(env):
    diagram = env.export()
    table = env.rid('table', 'child')
    with pytest.raises(ValueError, match='explicit rename_from'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, table, physical_name='kid'), engine='postgresql')


def test_drop_plus_add_stays_drop_plus_add(env):
    diagram = env.export()
    table = env.rid('table', 'child')
    field_id = next(k for k, v in diagram['resource_mapping'].items() if v == table + ':4')
    dropped = rt._run(diagram['snapshot'], [
        {'target': {'file': rt.FILE, 'id': 'relations.mapping_' + field_id}, 'path': 'metadata.x_record.record.drop', 'value': True},
        {'target': {'file': rt.FILE, 'id': 'relations.mapping_' + field_id}, 'path': 'metadata.x_record.record.drop_confirmation', 'value': 'note'}])
    _, plan = env.review(dropped)
    assert operations(plan) == ['drop_column'] and plan['operations'][0]['destructive'] is True
    assert plan['operations'][0]['statement'].endswith('DROP COLUMN "note" RESTRICT')
    env.settle(plan)


def test_table_drop_requires_confirmation_and_is_flagged(env):
    diagram = env.export()
    child = env.rid('table', 'child')
    with pytest.raises(ValueError, match='drop_confirmation'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, child, drop=True), engine='postgresql')
    _, plan = env.review(rt.edit_vocabulary(diagram, child, drop=True, drop_confirmation='child'))
    assert operations(plan) == ['drop_relation'] and plan['operations'][0]['destructive'] is True
    env.settle(plan)
