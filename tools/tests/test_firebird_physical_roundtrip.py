"""Live Firebird 5 forward -> edit -> reverse -> plan -> apply -> re-inspect for physical-schema edits.

Needs a Firebird 5 server: set ``CDEADMIN_ROUNDTRIP_FIREBIRD`` to the JSON object described in
test_ui_descriptor_roundtrip_firebird.py and ``CDEADMIN_FIREBIRD_CLIENT_LIBRARY`` to a Firebird 5
``libfbclient``. Each test creates its own database, draws the ERD, edits the x_record vocabulary
through DDN's public source API, hands the edit to the reviewed-plan machinery, applies the review
through the real owned-transaction applier (one native transaction, commit, rediscovery) and proves
the result converges: re-planning the same reviewed documents against the new live catalog yields
nothing to do, and the next diagram carries the intended vocabulary.
"""
import json
import os
import sys
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_FIREBIRD')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_FIREBIRD is not set', allow_module_level=True)
driver = pytest.importorskip('firebird.driver')

import physical_roundtrip as rt  # noqa: E402
from pgadmin.cdeadmin.providers.firebird.provider import FirebirdProvider, _create_client, _resources  # noqa: E402
from pgadmin.cdeadmin.providers.firebird.schema_application import apply_review  # noqa: E402
from pgadmin.cdeadmin.security.secrets import SecretLease  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff, read_relations  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan  # noqa: E402

SETTINGS = json.loads(SETTINGS)
UNIQUE = uuid.uuid4().hex[:6]
SCHEMA = [
    '''CREATE TABLE PARENT (ID INTEGER NOT NULL, CODE VARCHAR(10), REGION VARCHAR(10),
        CONSTRAINT PK_PARENT PRIMARY KEY (ID), CONSTRAINT PARENT_CODE_KEY UNIQUE (CODE))''',
    '''CREATE TABLE CHILD (ID INTEGER NOT NULL, PARENT_ID INTEGER, AMOUNT INTEGER, NOTE VARCHAR(20),
        CONSTRAINT CHILD_AMOUNT_CHECK CHECK (AMOUNT > 0),
        CONSTRAINT CHILD_PARENT_FK FOREIGN KEY (PARENT_ID) REFERENCES PARENT (ID) ON DELETE CASCADE ON UPDATE SET NULL)''',
    'CREATE INDEX CHILD_AMOUNT_IDX ON CHILD (AMOUNT)',
    'CREATE DESCENDING INDEX CHILD_NOTE_IDX ON CHILD (NOTE)',
    'COMMENT ON INDEX CHILD_AMOUNT_IDX IS \'amount lookups\'',
]


class Env:
    def __init__(self, client, path, tmp):
        self.client, self.path, self.tmp = client, path, tmp
        self.dsn = f"{SETTINGS['host']}/{SETTINGS['port']}:{path}"
        self.route = {'host': SETTINGS['host'], 'port': int(SETTINGS['port']), 'database': path, 'user': SETTINGS['user'],
                      'credential_reference_id': 'physrt', 'principal_reference': 'physrt'}
        permissions = SimpleNamespace(require=lambda *_: True,
                                      acquire_secret=lambda *_: SecretLease(SETTINGS['password']))
        self.provider = object.__new__(FirebirdProvider)
        self.provider.client, self.provider.permissions, self.provider.attachment_mode = client, permissions, 'network'
        self.store = SchemaApplications(tmp / 'receipts.json')
        self.outcome = None

    def sql(self, *statements):
        connection = driver.connect(self.dsn, user=SETTINGS['user'], password=SETTINGS['password'])
        try:
            for statement in statements:
                connection.execute_immediate(statement)
            connection.commit()
        finally:
            connection.close()

    def query(self, statement, params=()):
        connection = driver.connect(self.dsn, user=SETTINGS['user'], password=SETTINGS['password'])
        try:
            with connection.cursor() as cursor:
                cursor.execute(statement, params)
                return cursor.fetchall()
        finally:
            connection.close()

    def resources(self):
        connection = self.client._connect({'route': dict(self.route)})
        try:
            return list(_resources(connection, {}))
        finally:
            self.client._forget_and_close(connection)

    def export(self):
        self.catalog = build_export(self.resources(), endpoint_id='ep', target_id='db', generation='g1')
        self.diagram = self.catalog['diagram']
        assert self.diagram and not self.diagram.get('unavailable'), self.diagram
        return self.diagram

    def rid(self, kind, name):
        rows = [row for row in self.resources() if row['resource_kind'] == kind and row['display_name'] == name]
        assert len(rows) == 1, (kind, name, len(rows))
        return rows[0]['resource_id']

    def uid(self, resource_id):
        return 'firebird:ep:db:' + resource_id

    def physical(self):
        """name -> vocabulary of the next diagram (re-inspect)."""
        diagram = self.export()
        return {row['physical']['physical_name']: row['physical']
                for row in read_relations(diagram['snapshot']).values() if row.get('physical')}

    def review(self, edited):
        result = handoff(self.catalog['snapshot'], self.diagram['snapshot'], edited)
        self.pair = (read_catalog(result['baseline']), read_catalog(result['desired']))
        return result, self.plan()

    def plan(self):
        current = build_export(self.resources(), endpoint_id='ep', target_id='db', generation='g2',
                               include_system=True, native_model=True)
        return build_plan(self.pair[0], self.pair[1], current)

    def apply(self, plan):
        assert plan['status'] == 'review-ready', plan['blockers']
        review = self.store.review(plan, self.pair[0], self.pair[1], 'owner', 'binding', self.path)
        response = self.store.apply({'review_id': review['review_id'], 'review_digest': review['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(self.provider, self.route, record))
        self.outcome = response['outcome']
        assert self.outcome['native_commit_returned'] and self.outcome['rediscovery']['available'], self.outcome
        assert all(item['matches_reviewed_properties'] for item in self.outcome['rediscovery']['objects']), self.outcome
        return self.outcome

    def settle(self, plan):
        """Apply for real, then re-plan the same reviewed documents: nothing may remain."""
        self.apply(plan)
        again = self.plan()
        assert again['blockers'] == [] and again['operations'] == [] and again['status'] == 'no-op', again
        return again


@pytest.fixture(scope='module')
def client():
    instance = _create_client(SimpleNamespace(acquire_secret=lambda *_: SecretLease(SETTINGS['password'])))
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
def env(client, tmp_path):
    path = str(Path(SETTINGS['database_root']) / f'physrt_{UNIQUE}_{uuid.uuid4().hex[:6]}.fdb')
    seed = driver.create_database(f"{SETTINGS['host']}/{SETTINGS['port']}:{path}", user=SETTINGS['user'], password=SETTINGS['password'])
    for statement in SCHEMA:
        seed.execute_immediate(statement)
        seed.commit()
    seed.close()
    instance = Env(client, path, tmp_path)
    try:
        yield instance
    finally:
        try:
            driver.connect(instance.dsn, user=SETTINGS['user'], password=SETTINGS['password']).drop_database()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            Path(path).unlink(missing_ok=True)


def operations(plan, *kinds):
    return [(item['kind'], item['operation']) for item in plan['operations'] if not kinds or item['kind'] in kinds]


def statements(plan):
    return [statement.replace('"', '').strip() for item in plan['operations']
            for statement in item.get('statements', []) + item.get('deferred_statements', [])]


def field_edit(diagram, column, **values):
    key = rt.key_of(diagram, column)
    return [{'target': {'file': rt.FILE, 'id': 'relations.mapping_' + key}, 'path': 'metadata.x_record.record.' + name, 'value': value}
            for name, value in values.items()]


# ------------------------------------------------------------------ engine and forward/reverse

def test_the_target_is_firebird_5_with_ods_13(env):
    assert env.query("SELECT RDB$GET_CONTEXT('SYSTEM', 'ENGINE_VERSION') FROM RDB$DATABASE")[0][0].startswith('5.0.')
    assert env.query('SELECT MON$ODS_MAJOR FROM MON$DATABASE')[0][0] == 13


def test_forward_emits_vocabulary_for_every_physical_object(env):
    diagram = env.export()
    rows = read_relations(diagram['snapshot'])
    physical = {row['physical']['physical_name']: row['physical'] for row in rows.values() if row.get('physical')}
    assert physical['CHILD_AMOUNT_IDX'] == {'physical_kind': 'index', 'physical_name': 'CHILD_AMOUNT_IDX',
        'columns_json': '["AMOUNT"]', 'unique': False, 'descending': False, 'inactive': False}
    assert physical['CHILD_NOTE_IDX']['descending'] is True
    assert physical['PK_PARENT'] == {'physical_kind': 'primary-key', 'physical_name': 'PK_PARENT',
        'columns_json': '["ID"]', 'descending': False}
    assert physical['PARENT_CODE_KEY']['physical_kind'] == 'unique'
    assert physical['CHILD_AMOUNT_CHECK'] == {'physical_kind': 'check', 'physical_name': 'CHILD_AMOUNT_CHECK', 'expression': '(AMOUNT > 0)'}
    fk = physical['CHILD_PARENT_FK']
    assert (fk['on_delete'], fk['on_update'], fk['referenced_columns_json'], fk['columns_json']) == ('CASCADE', 'SET NULL', '["ID"]', '["PARENT_ID"]')
    assert rows[env.rid('constraint', 'CHILD_PARENT_FK')]['endpoints'] == {
        'source': env.rid('table', 'CHILD'), 'target': env.rid('table', 'PARENT')}
    # Constraint-backing indexes are the constraint, not a second object.
    assert sum(1 for row in rows.values() if row.get('physical', {}).get('physical_name') == 'PK_PARENT') == 1
    assert physical['CHILD'] == {'physical_name': 'CHILD'}
    assert rows['column:CHILD:NOTE']['fields']['_physical'] == {'physical_name': 'NOTE'}


def test_expression_and_partial_indexes_round_trip_their_vocabulary(env):
    env.sql('CREATE INDEX CHILD_EXPR_IDX ON CHILD COMPUTED BY (AMOUNT * 2)',
            'CREATE UNIQUE INDEX CHILD_PART_IDX ON CHILD (AMOUNT, NOTE) WHERE AMOUNT > 5',
            'ALTER INDEX CHILD_NOTE_IDX INACTIVE')
    physical = env.physical()
    assert physical['CHILD_EXPR_IDX']['expression'] == '(AMOUNT * 2)' and 'columns_json' not in physical['CHILD_EXPR_IDX']
    part = physical['CHILD_PART_IDX']
    assert (part['unique'], part['predicate'], part['columns_json']) == (True, 'AMOUNT > 5', '["AMOUNT","NOTE"]')
    assert physical['CHILD_NOTE_IDX']['inactive'] is True


def test_unedited_diagram_yields_an_empty_plan(env):
    diagram = env.export()
    _, plan = env.review(diagram['snapshot'])
    assert plan['operations'] == [] and plan['blockers'] == [] and plan['status'] == 'no-op'


def test_omitted_vocabulary_is_never_a_drop_or_clear(env):
    diagram = env.export()
    index = env.rid('index', 'CHILD_AMOUNT_IDX')
    edited = rt.edit_vocabulary(diagram, index, physical_name='CHILD_AMOUNT_IDX')
    _, plan = env.review(edited)
    assert plan['operations'] == [] and plan['blockers'] == []


# ------------------------------------------------------------------ indexes

def test_index_columns_uniqueness_and_direction_replace_it(env):
    diagram = env.export()
    index = env.rid('index', 'CHILD_AMOUNT_IDX')
    edited = rt.edit_vocabulary(diagram, index, columns_json='["AMOUNT","NOTE"]', unique=True, descending=True)
    result, plan = env.review(edited)
    assert result['changed_resource_ids'] == [index]
    assert operations(plan) == [('index', 'replace')]
    operation = plan['operations'][0]
    assert operation['replacement'] is True and 'destructive' not in operation
    assert statements(plan) == ['DROP INDEX CHILD_AMOUNT_IDX',
        'CREATE UNIQUE DESCENDING INDEX CHILD_AMOUNT_IDX ON CHILD (AMOUNT, NOTE)',
        "COMMENT ON INDEX CHILD_AMOUNT_IDX IS 'amount lookups'"]
    env.settle(plan)
    row = env.query("SELECT RDB$UNIQUE_FLAG, RDB$INDEX_TYPE FROM RDB$INDICES WHERE RDB$INDEX_NAME = 'CHILD_AMOUNT_IDX'")[0]
    assert tuple(int(item) for item in row) == (1, 1)
    assert env.physical()['CHILD_AMOUNT_IDX']['columns_json'] == '["AMOUNT","NOTE"]'


def test_index_becomes_computed_by_and_partial(env):
    diagram = env.export()
    index = env.rid('index', 'CHILD_AMOUNT_IDX')
    _, plan = env.review(rt.edit_vocabulary(diagram, index, expression='(AMOUNT * 2)'))
    assert 'COMPUTED BY (AMOUNT * 2)' in statements(plan)[1]
    env.settle(plan)
    diagram = env.export()
    index = env.rid('index', 'CHILD_NOTE_IDX')
    _, plan = env.review(rt.edit_vocabulary(diagram, index, predicate='NOTE IS NOT NULL'))
    assert 'WHERE NOTE IS NOT NULL' in statements(plan)[1]
    env.settle(plan)
    assert env.physical()['CHILD_NOTE_IDX']['predicate'] == 'NOTE IS NOT NULL'


def test_index_active_and_inactive(env):
    diagram = env.export()
    index = env.rid('index', 'CHILD_AMOUNT_IDX')
    _, plan = env.review(rt.edit_vocabulary(diagram, index, inactive=True))
    assert operations(plan) == [('index', 'alter')] and statements(plan) == ['ALTER INDEX CHILD_AMOUNT_IDX INACTIVE']
    env.settle(plan)
    assert env.query("SELECT RDB$INDEX_INACTIVE FROM RDB$INDICES WHERE RDB$INDEX_NAME = 'CHILD_AMOUNT_IDX'")[0][0] == 1
    diagram = env.export()
    index = env.rid('index', 'CHILD_AMOUNT_IDX')
    _, plan = env.review(rt.edit_vocabulary(diagram, index, inactive=False))
    assert statements(plan) == ['ALTER INDEX CHILD_AMOUNT_IDX ACTIVE']
    env.settle(plan)


def test_new_index_from_annotated_draft(env):
    diagram = env.export()
    table = env.rid('table', 'CHILD')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'index', 'CHILD_PARENT_IDX',
        {'physical_kind': 'index', 'physical_name': 'CHILD_PARENT_IDX', 'columns_json': '["PARENT_ID","NOTE"]',
         'unique': True, 'descending': True, 'inactive': True}, 'firebird')
    _, plan = env.review(edited)
    assert operations(plan) == [('index', 'create')]
    assert statements(plan) == ['CREATE UNIQUE DESCENDING INDEX CHILD_PARENT_IDX ON CHILD (PARENT_ID, NOTE)',
                                'ALTER INDEX CHILD_PARENT_IDX INACTIVE']
    env.settle(plan)
    assert env.physical()['CHILD_PARENT_IDX']['inactive'] is True


def test_new_computed_and_partial_index_drafts(env):
    diagram = env.export()
    table = env.rid('table', 'CHILD')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'index', 'CHILD_EXPR_IDX',
        {'physical_kind': 'index', 'physical_name': 'CHILD_EXPR_IDX', 'expression': '(AMOUNT + 1)'}, 'firebird')
    edited, _ = rt.add_draft_element(diagram, edited, table, env.uid(table), 'index', 'CHILD_PART_IDX',
        {'physical_kind': 'index', 'physical_name': 'CHILD_PART_IDX', 'columns_json': '["AMOUNT"]', 'predicate': 'AMOUNT > 100'}, 'firebird')
    _, plan = env.review(edited)
    assert len(plan['operations']) == 2
    assert sorted(statements(plan)) == [
        'CREATE ASCENDING INDEX CHILD_EXPR_IDX ON CHILD COMPUTED BY (AMOUNT + 1)',
        'CREATE ASCENDING INDEX CHILD_PART_IDX ON CHILD (AMOUNT) WHERE AMOUNT > 100']
    env.settle(plan)
    physical = env.physical()
    assert physical['CHILD_EXPR_IDX']['expression'] == '(AMOUNT + 1)'
    assert physical['CHILD_PART_IDX']['predicate'] == 'AMOUNT > 100'


def test_index_rename_needs_a_mapping_and_is_then_not_carried(env):
    diagram = env.export()
    index = env.rid('index', 'CHILD_AMOUNT_IDX')
    with pytest.raises(ValueError, match='explicit rename_from'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, index, physical_name='RENAMED_IDX'))
    with pytest.raises(ValueError, match='does not name the baseline'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, index, physical_name='RENAMED_IDX', rename_from='SOMETHING_ELSE'))
    with pytest.raises(ValueError, match='Not carried to Firebird: Firebird 5.0 has no ALTER INDEX'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, index, physical_name='RENAMED_IDX', rename_from='CHILD_AMOUNT_IDX'))


def test_index_drop_needs_exact_confirmation_and_is_flagged(env):
    diagram = env.export()
    index = env.rid('index', 'CHILD_AMOUNT_IDX')
    with pytest.raises(ValueError, match='drop_confirmation'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, index, drop=True))
    with pytest.raises(ValueError, match='drop_confirmation'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, index, drop=True, drop_confirmation='other'))
    _, plan = env.review(rt.edit_vocabulary(diagram, index, drop=True, drop_confirmation='CHILD_AMOUNT_IDX'))
    assert operations(plan) == [('index', 'drop')]
    assert plan['operations'][0]['destructive'] is True and plan['operations'][0]['confirmation'] == 'CHILD_AMOUNT_IDX'
    assert statements(plan) == ['DROP INDEX CHILD_AMOUNT_IDX']
    env.settle(plan)


def test_live_drift_blocks_instead_of_overwriting(env):
    diagram = env.export()
    index = env.rid('index', 'CHILD_AMOUNT_IDX')
    edited = rt.edit_vocabulary(diagram, index, unique=True)
    env.sql('DROP INDEX CHILD_AMOUNT_IDX', 'CREATE DESCENDING INDEX CHILD_AMOUNT_IDX ON CHILD (AMOUNT)')
    _, plan = env.review(edited)
    assert plan['operations'] == [] and 'changed independently' in plan['blockers'][0]['reason']


def test_replaced_or_dropped_live_object_is_not_resurrected(env):
    diagram = env.export()
    index = env.rid('index', 'CHILD_AMOUNT_IDX')
    edited = rt.edit_vocabulary(diagram, index, unique=True)
    env.sql('DROP INDEX CHILD_AMOUNT_IDX')
    _, plan = env.review(edited)
    assert plan['operations'] == [] and 'no longer exists' in plan['blockers'][0]['reason']


def test_a_constraint_backing_index_is_edited_through_its_constraint(env):
    diagram = env.export()
    backing = env.rid('index', 'PK_PARENT')
    # The backing index has no element of its own; forcing vocabulary onto its row is refused.
    rows = read_relations(diagram['snapshot'])
    assert backing not in rows


# ------------------------------------------------------------------ UNIQUE / CHECK / PRIMARY KEY

def test_unique_constraint_columns_replace_it(env):
    diagram = env.export()
    unique = env.rid('constraint', 'PARENT_CODE_KEY')
    result, plan = env.review(rt.edit_vocabulary(diagram, unique, columns_json='["CODE","REGION"]', descending=True))
    assert set(result['changed_resource_ids']) == {unique, env.rid('index', 'PARENT_CODE_KEY')}
    assert operations(plan, 'constraint') == [('constraint', 'alter')]
    assert statements(plan) == ['ALTER TABLE PARENT DROP CONSTRAINT PARENT_CODE_KEY',
        'ALTER TABLE PARENT ADD CONSTRAINT PARENT_CODE_KEY UNIQUE (CODE, REGION) USING DESCENDING INDEX PARENT_CODE_KEY']
    env.settle(plan)
    assert env.physical()['PARENT_CODE_KEY']['columns_json'] == '["CODE","REGION"]'


def test_constraint_rename_is_not_carried_and_drop_is_flagged(env):
    diagram = env.export()
    unique = env.rid('constraint', 'PARENT_CODE_KEY')
    with pytest.raises(ValueError, match='Not carried to Firebird: Firebird 5.0 has no ALTER TABLE ... RENAME CONSTRAINT'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, unique, physical_name='PARENT_CODE_UQ', rename_from='PARENT_CODE_KEY'))
    _, plan = env.review(rt.edit_vocabulary(diagram, unique, drop=True, drop_confirmation='PARENT_CODE_KEY'))
    assert operations(plan, 'constraint') == [('constraint', 'drop')]
    operation = plan['operations'][0]
    assert operation['destructive'] is True and operation['confirmation'] == 'PARENT_CODE_KEY'
    assert operation['implicit_child_removals'] == [env.rid('index', 'PARENT_CODE_KEY')]
    env.settle(plan)
    assert env.query("SELECT COUNT(*) FROM RDB$RELATION_CONSTRAINTS WHERE RDB$CONSTRAINT_NAME = 'PARENT_CODE_KEY'")[0][0] == 0


def test_new_unique_constraint_draft(env):
    diagram = env.export()
    table = env.rid('table', 'CHILD')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'constraint', 'CHILD_NOTE_UQ',
        {'physical_kind': 'unique', 'physical_name': 'CHILD_NOTE_UQ', 'columns_json': '["NOTE"]', 'descending': False}, 'firebird')
    result, plan = env.review(edited)
    assert any(item.endswith('CHILD_NOTE_UQ') for item in result['changed_resource_ids'])
    assert 'ALTER TABLE CHILD ADD CONSTRAINT CHILD_NOTE_UQ UNIQUE (NOTE) USING ASCENDING INDEX CHILD_NOTE_UQ' in statements(plan)
    env.settle(plan)
    assert env.physical()['CHILD_NOTE_UQ']['physical_kind'] == 'unique'


def test_check_expression_edit_and_new_check(env):
    diagram = env.export()
    check = env.rid('constraint', 'CHILD_AMOUNT_CHECK')
    _, plan = env.review(rt.edit_vocabulary(diagram, check, expression='(AMOUNT >= 10)'))
    assert statements(plan) == ['ALTER TABLE CHILD DROP CONSTRAINT CHILD_AMOUNT_CHECK',
                                'ALTER TABLE CHILD ADD CONSTRAINT CHILD_AMOUNT_CHECK CHECK (AMOUNT >= 10)']
    env.settle(plan)
    with pytest.raises(Exception):
        env.sql('INSERT INTO CHILD (ID, AMOUNT) VALUES (1, 5)')
    diagram = env.export()
    table = env.rid('table', 'CHILD')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'constraint', 'CHILD_NOTE_CHECK',
        {'physical_kind': 'check', 'physical_name': 'CHILD_NOTE_CHECK', 'expression': "(NOTE <> '')"}, 'firebird')
    _, plan = env.review(edited)
    assert operations(plan, 'constraint') == [('constraint', 'create')]
    env.settle(plan)
    assert env.physical()['CHILD_NOTE_CHECK']['expression'] == "(NOTE <> '')"


def test_invalid_check_expression_is_a_blocker_not_sql(env):
    diagram = env.export()
    check = env.rid('constraint', 'CHILD_AMOUNT_CHECK')
    _, plan = env.review(rt.edit_vocabulary(diagram, check, expression='(1); DROP TABLE CHILD; --'))
    assert plan['operations'] == [] and plan['blockers']


def test_primary_key_add_replace_and_referenced_block(env):
    diagram = env.export()
    table = env.rid('table', 'CHILD')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'constraint', 'PK_CHILD',
        {'physical_kind': 'primary-key', 'physical_name': 'PK_CHILD', 'columns_json': '["ID"]'}, 'firebird')
    _, plan = env.review(edited)
    assert 'ALTER TABLE CHILD ADD CONSTRAINT PK_CHILD PRIMARY KEY (ID) USING ASCENDING INDEX PK_CHILD' in statements(plan)
    env.settle(plan)
    # Firebird refuses a PRIMARY KEY over a nullable column; the plan says so before any SQL.
    diagram = env.export()
    pkey = env.rid('constraint', 'PK_CHILD')
    with pytest.raises(ValueError, match='must be NOT NULL'):
        env.review(rt.edit_vocabulary(diagram, pkey, columns_json='["ID","NOTE"]'))
    # PK_PARENT backs CHILD_PARENT_FK: replacing it alone is refused before any SQL.
    diagram = env.export()
    parent_key = env.rid('constraint', 'PK_PARENT')
    with pytest.raises(ValueError, match='Foreign keys depend'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, parent_key, descending=True))


def test_second_primary_key_is_refused(env):
    diagram = env.export()
    table = env.rid('table', 'PARENT')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'constraint', 'PK_PARENT2',
        {'physical_kind': 'primary-key', 'physical_name': 'PK_PARENT2', 'columns_json': '["ID"]'}, 'firebird')
    with pytest.raises(ValueError, match='already has a PRIMARY KEY'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], edited)


def test_a_draft_cannot_reuse_a_database_wide_name(env):
    diagram = env.export()
    table = env.rid('table', 'CHILD')
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], table, env.uid(table), 'index', 'PK_PARENT',
        {'physical_kind': 'index', 'physical_name': 'PK_PARENT', 'columns_json': '["NOTE"]'}, 'firebird')
    with pytest.raises(ValueError, match='already exists'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], edited)


# ------------------------------------------------------------------ FOREIGN KEY

def test_foreign_key_actions_and_columns(env):
    diagram = env.export()
    fk = env.rid('constraint', 'CHILD_PARENT_FK')
    _, plan = env.review(rt.edit_vocabulary(diagram, fk, on_delete='SET NULL', on_update='CASCADE'))
    assert statements(plan) == ['ALTER TABLE CHILD DROP CONSTRAINT CHILD_PARENT_FK',
        'ALTER TABLE CHILD ADD CONSTRAINT CHILD_PARENT_FK FOREIGN KEY (PARENT_ID) REFERENCES PARENT (ID) '
        'ON UPDATE CASCADE ON DELETE SET NULL USING ASCENDING INDEX CHILD_PARENT_FK']
    env.settle(plan)
    assert tuple(rule.strip() for rule in env.query("SELECT RDB$UPDATE_RULE, RDB$DELETE_RULE FROM RDB$REF_CONSTRAINTS WHERE RDB$CONSTRAINT_NAME = 'CHILD_PARENT_FK'")[0]) == ('CASCADE', 'SET NULL')
    physical = env.physical()['CHILD_PARENT_FK']
    assert (physical['on_delete'], physical['on_update']) == ('SET NULL', 'CASCADE')


def test_foreign_key_no_action_is_firebirds_restrict(env):
    diagram = env.export()
    fk = env.rid('constraint', 'CHILD_PARENT_FK')
    _, plan = env.review(rt.edit_vocabulary(diagram, fk, on_delete='NO ACTION', on_update='RESTRICT'))
    assert 'ON UPDATE' not in statements(plan)[1] and 'ON DELETE' not in statements(plan)[1]
    env.settle(plan)


def test_foreign_key_rename_is_not_carried(env):
    diagram = env.export()
    fk = env.rid('constraint', 'CHILD_PARENT_FK')
    with pytest.raises(ValueError, match='Not carried to Firebird'):
        handoff(env.catalog['snapshot'], diagram['snapshot'],
                rt.edit_vocabulary(diagram, fk, physical_name='CHILD_PARENT_REF', rename_from='CHILD_PARENT_FK'))


def test_foreign_key_invalid_action_and_unreferenceable_target_are_rejected(env):
    diagram = env.export()
    fk = env.rid('constraint', 'CHILD_PARENT_FK')
    with pytest.raises(ValueError, match='action'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, fk, on_delete='EXPLODE'))
    with pytest.raises(ValueError, match='PRIMARY KEY or UNIQUE'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, fk, referenced_columns_json='["REGION"]'))


def test_new_foreign_key_draft_edge(env):
    diagram = env.export()
    child, parent = env.rid('table', 'CHILD'), env.rid('table', 'PARENT')
    edited, _ = rt.add_draft_foreign_key(diagram, diagram['snapshot'], child, parent, env.uid(child), 'CHILD_CODE_FK',
        {'physical_kind': 'foreign-key', 'physical_name': 'CHILD_CODE_FK', 'columns_json': '["NOTE"]',
         'referenced_columns_json': '["CODE"]', 'on_delete': 'CASCADE', 'on_update': 'NO ACTION'}, 'firebird')
    _, plan = env.review(edited)
    assert ('ALTER TABLE CHILD ADD CONSTRAINT CHILD_CODE_FK FOREIGN KEY (NOTE) REFERENCES PARENT (CODE) '
            'ON DELETE CASCADE USING ASCENDING INDEX CHILD_CODE_FK') in statements(plan)
    env.settle(plan)
    assert env.physical()['CHILD_CODE_FK']['referenced_columns_json'] == '["CODE"]'


def test_foreign_key_drop_with_confirmation(env):
    diagram = env.export()
    fk = env.rid('constraint', 'CHILD_PARENT_FK')
    _, plan = env.review(rt.edit_vocabulary(diagram, fk, drop=True, drop_confirmation='CHILD_PARENT_FK'))
    assert operations(plan, 'constraint') == [('constraint', 'drop')] and plan['operations'][0]['destructive'] is True
    env.settle(plan)


# ------------------------------------------------------------------ renames and drops

def test_column_rename_with_explicit_mapping(env):
    diagram = env.export()
    snapshot = rt._run(diagram['snapshot'], field_edit(diagram, 'column:CHILD:NOTE', physical_name='MEMO', rename_from='NOTE'))
    result, plan = env.review(snapshot)
    assert operations(plan) == [('column', 'rename')]
    assert statements(plan) == ['ALTER TABLE CHILD ALTER COLUMN NOTE TO MEMO']
    env.settle(plan)
    assert env.query("SELECT COUNT(*) FROM RDB$RELATION_FIELDS WHERE RDB$RELATION_NAME = 'CHILD' AND RDB$FIELD_NAME = 'MEMO'")[0][0] == 1
    # A plain index follows the rename; the next diagram shows the new column name in its key.
    assert env.physical()['CHILD_NOTE_IDX']['columns_json'] == '["MEMO"]'


def test_column_rename_without_mapping_is_never_inferred(env):
    diagram = env.export()
    snapshot = rt._run(diagram['snapshot'], field_edit(diagram, 'column:CHILD:NOTE', physical_name='MEMO'))
    with pytest.raises(ValueError, match='explicit rename_from'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], snapshot)


def test_column_rename_the_engine_refuses_is_blocked_with_the_reason(env):
    diagram = env.export()
    snapshot = rt._run(diagram['snapshot'], field_edit(diagram, 'column:CHILD:AMOUNT', physical_name='SUM_', rename_from='AMOUNT'))
    _, plan = env.review(snapshot)
    assert plan['operations'] == [] and 'not carried' in plan['blockers'][0]['reason']
    assert 'CHILD_AMOUNT_CHECK' in plan['blockers'][0]['reason']
    # The engine really refuses it.
    with pytest.raises(Exception):
        env.sql('ALTER TABLE CHILD ALTER COLUMN AMOUNT TO SUM_')


def test_table_rename_is_not_carried(env):
    diagram = env.export()
    table = env.rid('table', 'CHILD')
    with pytest.raises(ValueError, match='explicit rename_from'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, table, physical_name='KID'))
    with pytest.raises(ValueError, match='Not carried to Firebird: Firebird 5.0 has no ALTER TABLE ... RENAME TO'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, table, physical_name='KID', rename_from='CHILD'))


def test_column_drop_needs_confirmation_and_names_the_constraints_it_removes(env):
    diagram = env.export()
    with pytest.raises(ValueError, match='drop_confirmation'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt._run(diagram['snapshot'], field_edit(diagram, 'column:CHILD:AMOUNT', drop=True)))
    # CHILD_AMOUNT_IDX still uses AMOUNT: Firebird refuses, so the plan does.
    _, plan = env.review(rt._run(diagram['snapshot'], field_edit(diagram, 'column:CHILD:AMOUNT', drop=True, drop_confirmation='AMOUNT')))
    assert plan['operations'] == [] and 'CHILD_AMOUNT_IDX' in plan['blockers'][0]['reason']
    # Dropping the column used only by a CHECK removes that constraint with it: the plan lists it.
    env.sql('DROP INDEX CHILD_AMOUNT_IDX')
    diagram = env.export()
    _, plan = env.review(rt._run(diagram['snapshot'], field_edit(diagram, 'column:CHILD:AMOUNT', drop=True, drop_confirmation='AMOUNT')))
    operation = plan['operations'][0]
    assert operation['destructive'] is True and operation['confirmation'] == 'AMOUNT'
    assert operation['implicit_child_removals'] == [env.rid('constraint', 'CHILD_AMOUNT_CHECK')]
    assert statements(plan) == ['ALTER TABLE CHILD DROP AMOUNT']
    env.settle(plan)
    assert env.query("SELECT COUNT(*) FROM RDB$RELATION_CONSTRAINTS WHERE RDB$CONSTRAINT_NAME = 'CHILD_AMOUNT_CHECK'")[0][0] == 0


def test_table_drop_requires_confirmation_and_respects_foreign_keys(env):
    diagram = env.export()
    child, parent = env.rid('table', 'CHILD'), env.rid('table', 'PARENT')
    with pytest.raises(ValueError, match='drop_confirmation'):
        handoff(env.catalog['snapshot'], diagram['snapshot'], rt.edit_vocabulary(diagram, child, drop=True))
    _, plan = env.review(rt.edit_vocabulary(diagram, parent, drop=True, drop_confirmation='PARENT'))
    assert plan['operations'] == [] and 'Foreign keys of other tables' in plan['blockers'][0]['reason']
    _, plan = env.review(rt.edit_vocabulary(diagram, child, drop=True, drop_confirmation='CHILD'))
    assert operations(plan) == [('table', 'drop')] and plan['operations'][0]['destructive'] is True
    env.settle(plan)
    assert env.query("SELECT COUNT(*) FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = 'CHILD'")[0][0] == 0


def test_dropping_parent_and_child_together_orders_the_foreign_key_first(env):
    diagram = env.export()
    child, parent = env.rid('table', 'CHILD'), env.rid('table', 'PARENT')
    edited = rt.edit_vocabulary(diagram, child, drop=True, drop_confirmation='CHILD')
    edited = rt.edit_vocabulary(diagram, parent, snapshot=edited, drop=True, drop_confirmation='PARENT')
    _, plan = env.review(edited)
    assert statements(plan) == ['DROP TABLE CHILD', 'DROP TABLE PARENT']
    env.settle(plan)
