"""Live DuckDB 1.5.2 tests for Batch 3: DDN preservation & retained-session DDN (DU-AUD-09..17)."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import duckdb
import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider, _create_client, _resource_id
from pgadmin.cdeadmin.providers.duckdb.schema_application import apply_review
from pgadmin.cdeadmin.workspace.duckdb_retained_applications import DuckDBRetainedApplications
from pgadmin.cdeadmin.workspace import duckdb_retained_schema as retained_ddn
from pgadmin.cdeadmin.workspace.duckdb_schema_apply import DuckDBSchemaApplications
from pgadmin.cdeadmin.workspace.duckdb_schema_plan import plan
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export


def _capture_file_model(provider, db_path, root_dir, *, target_id='file-1', include_macro_source=True):
    route = {'database': str(db_path), 'filesystem_root': str(root_dir)}
    obs = provider.capture_catalog(route, include_macro_source=include_macro_source)
    model = build_export(
        obs['resources'],
        endpoint_id='ep-1',
        target_id=target_id,
        generation=obs['generation'],
        refreshed=True,
        engine='duckdb',
        native_model=True,
    )
    # Qualify CREATE TABLE/VIEW/SEQUENCE/TYPE/MACRO DDLs in desired models where needed
    db_name = next(r['name'] for r in model['rows'].values() if r['kind'] == 'database')
    return route, model, db_name


def _qualify_table_ddl(row):
    cat, sch, name = row['path']
    ddl = row['native']['ddl']
    open_paren = ddl.index('(')
    row['native']['ddl'] = f'CREATE TABLE "{cat}"."{sch}"."{name}" ' + ddl[open_paren:]


def _make_provider():
    ctx = SimpleNamespace(endpoint_id='ep-1', session_namespace='ns-1')
    return DuckDBPilotProvider(ctx, SimpleNamespace(require=Mock()), _create_client())


# ---------------------------------------------------------------------------
# DU-AUD-09: General combined table & column transformations
# ---------------------------------------------------------------------------

def test_du_aud_09_general_combined_table_rebuild_and_loss_refusals(tmp_path):
    db_file = tmp_path / 'work.duckdb'
    con = duckdb.connect(str(db_file))
    con.execute(
        'CREATE TABLE items ('
        '  id INTEGER PRIMARY KEY,'
        '  old_label VARCHAR,'
        '  raw_amt VARCHAR DEFAULT \'0\','
        '  obsolete VARCHAR'
        ')'
    )
    con.execute("INSERT INTO items VALUES (1, 'alpha', '42', 'dropme'), (2, 'beta', '108', 'dropme2')")
    con.close()

    # Build desired catalog on a scratch file with exact same stem 'work.duckdb' in a subdir
    desired_dir = tmp_path / 'desired_spec'
    desired_dir.mkdir()
    desired_file = desired_dir / 'work.duckdb'
    dcon = duckdb.connect(str(desired_file))
    dcon.execute(
        'CREATE TABLE items ('
        '  id INTEGER PRIMARY KEY,'
        '  amt INTEGER NOT NULL DEFAULT 0 CHECK (amt >= 0),'
        '  item_label VARCHAR NOT NULL,'
        '  tier VARCHAR NOT NULL,'
        '  notes VARCHAR,'
        '  UNIQUE (item_label)'
        ')'
    )
    dcon.execute("COMMENT ON COLUMN items.notes IS 'optional note'")
    dcon.close()

    provider = _make_provider()
    try:
        route, baseline, db_name = _capture_file_model(provider, db_file, tmp_path)
        _, desired, _ = _capture_file_model(provider, desired_file, desired_dir)

        tid = _resource_id('table', [db_name, 'main'], 'items')
        obs_col_id = _resource_id('column', [db_name, 'main', 'items'], 'obsolete')
        _qualify_table_ddl(desired['rows'][tid])

        # 1. Refusal when CREATE OR REPLACE TABLE is attempted
        bad_replace = deepcopy(desired)
        bad_replace['rows'][tid]['native']['ddl'] = bad_replace['rows'][tid]['native']['ddl'].replace(
            'CREATE TABLE', 'CREATE OR REPLACE TABLE', 1
        )
        bad_replace['rows'][tid]['native']['duckdb_change'] = {
            'action': 'rebuild-table-general',
            'complete_definition_confirmed': True,
            'preserve_rows_confirmed': True,
            'drop_column_ids': [obs_col_id],
            'discard_columns_confirmed': True,
            'column_renames': {'old_label': 'item_label', 'raw_amt': 'amt'},
            'column_conversions': {'amt': 'CAST("raw_amt" AS INTEGER)'},
            'loss_acknowledged': True,
            'added_column_fills': {'tier': "'standard'"},
        }
        p_bad_rep = plan(baseline, bad_replace, baseline)
        assert not p_bad_rep['ready_for_review']
        assert p_bad_rep['blockers']

        # 2. Refusal when type conversion omits loss_acknowledged or column_conversions
        bad_no_loss = deepcopy(desired)
        bad_no_loss['rows'][tid]['native']['duckdb_change'] = {
            'action': 'rebuild-table-general',
            'complete_definition_confirmed': True,
            'preserve_rows_confirmed': True,
            'drop_column_ids': [obs_col_id],
            'discard_columns_confirmed': True,
            'column_renames': {'old_label': 'item_label', 'raw_amt': 'amt'},
            'added_column_fills': {'tier': "'standard'"},
        }
        p_no_loss = plan(baseline, bad_no_loss, baseline)
        assert not p_no_loss['ready_for_review']
        assert any('loss_acknowledged' in b['reason'] for b in p_no_loss['blockers'])

        # 3. Positive combined transformation: rename + type conversion + drop + NOT NULL fill + reorder + CHECK + UNIQUE + comment
        desired['rows'][tid]['native']['duckdb_change'] = {
            'action': 'rebuild-table-general',
            'complete_definition_confirmed': True,
            'preserve_rows_confirmed': True,
            'drop_column_ids': [obs_col_id],
            'discard_columns_confirmed': True,
            'column_renames': {'old_label': 'item_label', 'raw_amt': 'amt'},
            'column_conversions': {'amt': 'CAST("raw_amt" AS INTEGER)'},
            'loss_acknowledged': True,
            'added_column_fills': {'tier': "'standard'"},
        }
        preview = plan(baseline, desired, baseline)
        assert preview['ready_for_review'], preview['blockers']

        apps = DuckDBSchemaApplications(tmp_path / 'receipts.json', clock=lambda: 100)
        receipt = apps.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        applied = apps.apply(
            {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding',
            lambda rec: apply_review(provider, route, rec),
        )
        assert applied['state'] == 'committed', applied
        assert applied['outcome']['rediscovery_verified'] is True

        # Verify actual data & metadata in an independent DuckDB connection
        verify_con = duckdb.connect(str(db_file))
        rows = verify_con.execute('SELECT id, amt, item_label, tier, notes FROM items ORDER BY id').fetchall()
        assert rows == [(1, 42, 'alpha', 'standard', None), (2, 108, 'beta', 'standard', None)]
        # Verify no replay
        replay_fn = Mock()
        replayed = apps.apply(
            {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', replay_fn,
        )
        assert replayed == applied
        replay_fn.assert_not_called()
        verify_con.close()
    finally:
        provider.client.close()


# ---------------------------------------------------------------------------
# DU-AUD-10 & DU-AUD-11: Broadened generated chains + PK/explicit NOT NULL retention
# ---------------------------------------------------------------------------

def test_du_aud_10_and_11_generated_chains_volatile_refusals_and_pk_not_null(tmp_path):
    db_file = tmp_path / 'genpk.duckdb'
    con = duckdb.connect(str(db_file))
    con.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, first_name VARCHAR, last_name VARCHAR)')
    con.execute("INSERT INTO users VALUES (10, '  Ada ', 'Lovelace '), (20, 'Grace', 'Hopper')")
    con.close()

    # Desired drops PRIMARY KEY on id while RETAINING explicit NOT NULL on id, adds explicit NOT NULL on first_name,
    # and adds a 2-hop generated-on-generated column chain (clean_first -> display_tag)!
    desired_dir = tmp_path / 'des_gen'
    desired_dir.mkdir()
    desired_file = desired_dir / 'genpk.duckdb'
    dcon = duckdb.connect(str(desired_file))
    dcon.execute(
        'CREATE TABLE users ('
        '  id INTEGER NOT NULL,'
        '  first_name VARCHAR NOT NULL,'
        '  last_name VARCHAR,'
        '  clean_first VARCHAR GENERATED ALWAYS AS (upper(trim(first_name))),'
        '  display_tag VARCHAR GENERATED ALWAYS AS (coalesce(clean_first, \'NONE\') || \'-\' || substr(coalesce(last_name, \'\'), 1, 3))'
        ')'
    )
    dcon.close()

    provider = _make_provider()
    try:
        route, baseline, db_name = _capture_file_model(provider, db_file, tmp_path)
        _, desired, _ = _capture_file_model(provider, desired_file, desired_dir)
        tid = _resource_id('table', [db_name, 'main'], 'users')
        _qualify_table_ddl(desired['rows'][tid])

        # Volatile function refusal check (random() in generated column)
        volatile_des = deepcopy(desired)
        volatile_des['rows'][tid]['native']['ddl'] = (
            f'CREATE TABLE "{db_name}"."main"."users" ('
            'id INTEGER NOT NULL, first_name VARCHAR NOT NULL, last_name VARCHAR, '
            'clean_first VARCHAR GENERATED ALWAYS AS (random()::VARCHAR), '
            'display_tag VARCHAR GENERATED ALWAYS AS (clean_first))'
        )
        volatile_des['rows'][tid]['native']['duckdb_change'] = {
            'action': 'rebuild-table-general',
            'complete_definition_confirmed': True,
            'preserve_rows_confirmed': True,
        }
        p_vol = plan(baseline, volatile_des, baseline)
        assert not p_vol['ready_for_review']
        assert any('volatile' in b['reason'] for b in p_vol['blockers'])

        # Cyclic generated column refusal check
        cyclic_des = deepcopy(desired)
        cyclic_des['rows'][tid]['native']['ddl'] = (
            f'CREATE TABLE "{db_name}"."main"."users" ('
            'id INTEGER NOT NULL, first_name VARCHAR NOT NULL, last_name VARCHAR, '
            'clean_first VARCHAR GENERATED ALWAYS AS (display_tag), '
            'display_tag VARCHAR GENERATED ALWAYS AS (clean_first))'
        )
        cyclic_des['rows'][tid]['native']['duckdb_change'] = {
            'action': 'rebuild-table-general',
            'complete_definition_confirmed': True,
            'preserve_rows_confirmed': True,
        }
        p_cyc = plan(baseline, cyclic_des, baseline)
        assert not p_cyc['ready_for_review']
        assert any('cycle' in b['reason'] for b in p_cyc['blockers'])

        # Positive apply: drop PK while keeping id NOT NULL + generated-on-generated chain
        desired['rows'][tid]['native']['duckdb_change'] = {
            'action': 'rebuild-table-general',
            'complete_definition_confirmed': True,
            'preserve_rows_confirmed': True,
        }
        preview = plan(baseline, desired, baseline)
        assert preview['ready_for_review'], preview['blockers']
        assert preview['operations'][0]['generated_column_order'] == ['clean_first', 'display_tag']

        apps = DuckDBSchemaApplications(tmp_path / 'receipts.json', clock=lambda: 100)
        receipt = apps.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        applied = apps.apply(
            {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding',
            lambda rec: apply_review(provider, route, rec),
        )
        assert applied['state'] == 'committed', applied
        assert applied['outcome']['rediscovery_verified'] is True

        vcon = duckdb.connect(str(db_file))
        rows = vcon.execute('SELECT id, clean_first, display_tag FROM users ORDER BY id').fetchall()
        assert rows == [(10, 'ADA', 'ADA-Lov'), (20, 'GRACE', 'GRACE-Hop')]
        # Verify PK is gone while explicit NOT NULL on id and first_name is enforced!
        pks = vcon.execute("SELECT count(*) FROM duckdb_constraints() WHERE table_name='users' AND constraint_type='PRIMARY KEY'").fetchone()[0]
        assert pks == 0
        with pytest.raises(duckdb.ConstraintException):
            vcon.execute("INSERT INTO users (id, first_name, last_name) VALUES (NULL, 'X', 'Y')")
        vcon.close()
    finally:
        provider.client.close()


# ---------------------------------------------------------------------------
# DU-AUD-12, DU-AUD-13, DU-AUD-14, DU-AUD-15:
# Self-FK, multi-hop inbound-on-child DAG, UNIQUE/expression child indexes,
# variadic/typed-overload macros + co-updated views, tag loss ack, sequence defaults
# ---------------------------------------------------------------------------

def test_du_aud_12_self_fk_hierarchical_rebuild(tmp_path):
    db_file = tmp_path / 'org.duckdb'
    con = duckdb.connect(str(db_file))
    con.execute('CREATE TABLE emp (id INTEGER PRIMARY KEY, mgr INTEGER REFERENCES emp(id), name VARCHAR)')
    con.execute("INSERT INTO emp VALUES (1, NULL, 'CEO')")
    con.execute("INSERT INTO emp VALUES (2, 1, 'VP'), (3, 1, 'CFO')")
    con.execute("INSERT INTO emp VALUES (4, 2, 'Dir')")
    con.close()

    desired_dir = tmp_path / 'des_org'
    desired_dir.mkdir()
    desired_file = desired_dir / 'org.duckdb'
    dcon = duckdb.connect(str(desired_file))
    dcon.execute(
        'CREATE TABLE emp ('
        '  id INTEGER PRIMARY KEY,'
        '  mgr INTEGER REFERENCES emp(id),'
        '  name VARCHAR NOT NULL,'
        '  level_code VARCHAR DEFAULT \'L1\''
        ')'
    )
    dcon.close()

    provider = _make_provider()
    try:
        route, baseline, db_name = _capture_file_model(provider, db_file, tmp_path)
        _, desired, _ = _capture_file_model(provider, desired_file, desired_dir)
        tid = _resource_id('table', [db_name, 'main'], 'emp')
        # Supply clean qualified DDL with self-FK (since DuckDB's duckdb_tables().sql omits self-FK text)
        desired['rows'][tid]['native']['ddl'] = (
            f'CREATE TABLE "{db_name}"."main"."emp" ('
            'id INTEGER PRIMARY KEY, mgr INTEGER REFERENCES emp(id), '
            "name VARCHAR NOT NULL, level_code VARCHAR DEFAULT 'L1')"
        )
        desired['rows'][tid]['native']['duckdb_change'] = {
            'action': 'rebuild-table-general',
            'complete_definition_confirmed': True,
            'preserve_rows_confirmed': True,
        }
        preview = plan(baseline, desired, baseline)
        assert preview['ready_for_review'], preview['blockers']

        apps = DuckDBSchemaApplications(tmp_path / 'receipts.json', clock=lambda: 100)
        receipt = apps.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        applied = apps.apply(
            {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding',
            lambda rec: apply_review(provider, route, rec),
        )
        assert applied['state'] == 'committed', applied
        assert applied['outcome']['rediscovery_verified'] is True

        vcon = duckdb.connect(str(db_file))
        rows = vcon.execute('SELECT id, mgr, name, level_code FROM emp ORDER BY id').fetchall()
        assert rows == [(1, None, 'CEO', 'L1'), (2, 1, 'VP', 'L1'), (3, 1, 'CFO', 'L1'), (4, 2, 'Dir', 'L1')]
        # Self-FK still enforced after rebuild!
        with pytest.raises(duckdb.ConstraintException):
            vcon.execute("INSERT INTO emp VALUES (99, 777, 'Ghost', 'L9')")
        vcon.close()
    finally:
        provider.client.close()


def test_du_aud_12_13_14_15_multihop_inbound_child_indexes_macros_views_tags_and_sequences(tmp_path):
    db_file = tmp_path / 'complex.duckdb'
    con = duckdb.connect(str(db_file), config={'storage_compatibility_version': 'v1.5.2'})
    con.execute('CREATE SEQUENCE seq_ord START 1000')
    con.execute('CREATE SEQUENCE seq_fallback START 5000')
    con.execute(
        "CREATE TABLE orders ("
        "  id INTEGER PRIMARY KEY,"
        "  ord_code VARCHAR DEFAULT ('ORD-' || lpad(nextval('seq_ord')::VARCHAR, 5, '0') || '-' || coalesce(nextval('seq_fallback'), 0)::VARCHAR),"
        "  old_status VARCHAR"
        ")"
    )
    con.execute('CREATE TABLE order_lines (id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id), sku VARCHAR)')
    con.execute('CREATE UNIQUE INDEX idx_lines_uq ON order_lines (order_id, sku)')
    con.execute('CREATE INDEX idx_lines_expr ON order_lines ((lower(sku)))')
    con.execute("COMMENT ON INDEX idx_lines_uq IS 'unique line sku per order'")
    con.execute('CREATE TABLE shipments (id INTEGER PRIMARY KEY, line_id INTEGER REFERENCES order_lines(id), carrier VARCHAR)')
    con.execute('CREATE VIEW v_order_summary AS SELECT id, old_status FROM orders')
    # Same-arity typed overloaded macro + variadic macro!
    con.execute(
        'CREATE MACRO fmt_val(x INTEGER, y INTEGER) AS x + y, '
        '(x VARCHAR, y VARCHAR) AS x || y'
    )
    con.execute('CREATE MACRO count_orders() AS (SELECT count(*) FROM orders)')
    con.execute("INSERT INTO orders (id, ord_code, old_status) VALUES (1, 'ORD-00001-1', 'NEW')")
    con.execute("INSERT INTO order_lines VALUES (10, 1, 'SKU-A')")
    con.execute("INSERT INTO shipments VALUES (100, 10, 'DHL')")
    # Advance sequence once (returns 1000; on close/reopen DuckDB checkpoints next value 1001)
    assert con.execute("SELECT nextval('seq_ord')").fetchone()[0] == 1000
    con.close()
    rcon = duckdb.connect(str(db_file))
    seq_ord_before = rcon.execute("SELECT last_value FROM duckdb_sequences() WHERE sequence_name='seq_ord'").fetchone()[0]
    rcon.close()

    desired_dir = tmp_path / 'des_complex'
    desired_dir.mkdir()
    desired_file = desired_dir / 'complex.duckdb'
    dcon = duckdb.connect(str(desired_file), config={'storage_compatibility_version': 'v1.5.2'})
    dcon.execute('CREATE SEQUENCE seq_ord START 1000')
    dcon.execute('CREATE SEQUENCE seq_fallback START 5000')
    dcon.execute(
        "CREATE TABLE orders ("
        "  id INTEGER PRIMARY KEY,"
        "  ord_code VARCHAR DEFAULT ('ORD-' || lpad(nextval('seq_ord')::VARCHAR, 5, '0') || '-' || coalesce(nextval('seq_fallback'), 0)::VARCHAR),"
        "  status_code VARCHAR NOT NULL CHECK (length(status_code) > 0)"
        ")"
    )
    dcon.execute('CREATE TABLE order_lines (id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id), sku VARCHAR)')
    dcon.execute('CREATE UNIQUE INDEX idx_lines_uq ON order_lines (order_id, sku)')
    dcon.execute('CREATE INDEX idx_lines_expr ON order_lines ((lower(sku)))')
    dcon.execute("COMMENT ON INDEX idx_lines_uq IS 'unique line sku per order'")
    dcon.execute('CREATE TABLE shipments (id INTEGER PRIMARY KEY, line_id INTEGER REFERENCES order_lines(id), carrier VARCHAR)')
    dcon.execute('CREATE VIEW v_order_summary AS SELECT id, status_code FROM orders')
    dcon.execute(
        'CREATE MACRO fmt_val(x INTEGER, y INTEGER) AS x + y, '
        '(x VARCHAR, y VARCHAR) AS x || y'
    )
    dcon.execute('CREATE MACRO count_orders() AS (SELECT count(*) FROM orders)')
    dcon.close()

    provider = _make_provider()
    try:
        route, baseline, db_name = _capture_file_model(provider, db_file, tmp_path)
        _, desired, _ = _capture_file_model(provider, desired_file, desired_dir)

        orders_id = _resource_id('table', [db_name, 'main'], 'orders')
        lines_id = _resource_id('table', [db_name, 'main'], 'order_lines')
        ship_id = _resource_id('table', [db_name, 'main'], 'shipments')
        view_id = _resource_id('view', [db_name, 'main'], 'v_order_summary')
        seq_ord_id = _resource_id('sequence', [db_name, 'main'], 'seq_ord')
        desired['rows'][seq_ord_id] = deepcopy(baseline['rows'][seq_ord_id])

        _qualify_table_ddl(desired['rows'][orders_id])
        desired['rows'][view_id]['native']['ddl'] = (
            f'CREATE OR REPLACE VIEW "{db_name}"."main"."v_order_summary" AS SELECT id, status_code FROM "{db_name}"."main"."orders"'
        )

        # Simulate C++ tag on orders in baseline to verify tag_loss_acknowledged enforcement (DU-AUD-14)
        tagged_base = deepcopy(baseline)
        tagged_base['rows'][orders_id]['native']['catalog_metadata']['tags'] = {'cpp_origin': 'ext_v1'}
        tagged_des = deepcopy(desired)
        tagged_des['rows'][orders_id]['native']['duckdb_change'] = {
            'action': 'rebuild-table-general',
            'complete_definition_confirmed': True,
            'preserve_rows_confirmed': True,
            'column_renames': {'old_status': 'status_code'},
            'inbound_children': [
                {
                    'resource_id': lines_id,
                    'intermediate_ddl': f'CREATE TABLE "{db_name}"."main"."order_lines" (id INTEGER PRIMARY KEY, order_id INTEGER, sku VARCHAR)',
                },
                {
                    'resource_id': ship_id,
                    'intermediate_ddl': f'CREATE TABLE "{db_name}"."main"."shipments" (id INTEGER PRIMARY KEY, line_id INTEGER, carrier VARCHAR)',
                },
            ],
            'updated_views': [view_id],
        }
        p_tag_refused = plan(tagged_base, tagged_des, tagged_base)
        assert not p_tag_refused['ready_for_review']
        assert any('tag_loss_acknowledged=True' in b['reason'] for b in p_tag_refused['blockers'])

        # Cross-schema FK refusal check (DU-AUD-12)
        bad_xschema = deepcopy(desired)
        bad_xschema['rows'][orders_id]['native']['constraints'].append({
            'resource_id': 'fake-fk',
            'name': 'fk_x',
            'constraint_index': 99,
            'constraint_type': 'FOREIGN KEY',
            'constraint_text': 'FOREIGN KEY (id) REFERENCES other_schema.parent(id)',
            'expression': None,
            'column_indexes': [0],
            'column_names': ['id'],
            'referenced_table': 'other_schema.parent',
            'referenced_column_names': ['id'],
        })
        bad_xschema['rows'][orders_id]['native']['duckdb_change'] = {
            'action': 'rebuild-table-general',
            'complete_definition_confirmed': True,
            'preserve_rows_confirmed': True,
            'column_renames': {'old_status': 'status_code'},
        }
        p_xschema = plan(baseline, bad_xschema, baseline)
        assert not p_xschema['ready_for_review']
        assert any('across schemas or catalogs' in b['reason'] for b in p_xschema['blockers'])

        # Full positive multi-hop rebuild (shipments -> order_lines -> orders) + co-updated view + same-arity typed macros + compound sequence defaults
        desired['rows'][orders_id]['native']['duckdb_change'] = {
            'action': 'rebuild-table-general',
            'complete_definition_confirmed': True,
            'preserve_rows_confirmed': True,
            'column_renames': {'old_status': 'status_code'},
            'inbound_children': [
                {
                    'resource_id': lines_id,
                    'intermediate_ddl': f'CREATE TABLE "{db_name}"."main"."order_lines" (id INTEGER PRIMARY KEY, order_id INTEGER, sku VARCHAR)',
                },
                {
                    'resource_id': ship_id,
                    'intermediate_ddl': f'CREATE TABLE "{db_name}"."main"."shipments" (id INTEGER PRIMARY KEY, line_id INTEGER, carrier VARCHAR)',
                },
            ],
            'updated_views': [view_id],
        }
        preview = plan(baseline, desired, baseline)
        assert preview['ready_for_review'], preview['blockers']
        assert any('OWNED BY' in w for w in preview['warnings'])

        apps = DuckDBSchemaApplications(tmp_path / 'receipts.json', clock=lambda: 100)
        receipt = apps.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        applied = apps.apply(
            {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding',
            lambda rec: apply_review(provider, route, rec),
        )
        assert applied['state'] == 'committed', applied
        assert applied['outcome']['rediscovery_verified'] is True

        vcon = duckdb.connect(str(db_file))
        # Sequence last_value did NOT advance during table rebuild, and nextval yields 1001!
        assert vcon.execute("SELECT last_value FROM duckdb_sequences() WHERE sequence_name='seq_ord'").fetchone()[0] == seq_ord_before
        assert vcon.execute("SELECT nextval('seq_ord')").fetchone()[0] == 1001
        assert vcon.execute("SELECT last_value FROM duckdb_sequences() WHERE sequence_name='seq_fallback'").fetchone()[0] is None
        # Data intact across all 3 levels + co-updated view + macros
        assert vcon.execute('SELECT id, status_code FROM v_order_summary').fetchall() == [(1, 'NEW')]
        assert vcon.execute('SELECT count_orders()').fetchone()[0] == 1
        assert vcon.execute("SELECT fmt_val(2, 3), fmt_val('a', 'b')").fetchone() == (5, 'ab')
        assert vcon.execute('SELECT * FROM shipments').fetchall() == [(100, 10, 'DHL')]
        # Child UNIQUE index + index comment + expression index survived!
        idx_rows = vcon.execute(
            "SELECT index_name, is_unique, comment FROM duckdb_indexes() WHERE table_name='order_lines' ORDER BY index_name"
        ).fetchall()
        assert idx_rows == [
            ('idx_lines_expr', False, None),
            ('idx_lines_uq', True, 'unique line sku per order'),
        ]
        vcon.close()
    finally:
        provider.client.close()


# ---------------------------------------------------------------------------
# DU-AUD-16: Macro default-preserving replacement from captured source_ddl
# ---------------------------------------------------------------------------

def test_du_aud_16_macro_preserve_defaults_and_refusals(tmp_path):
    db_file = tmp_path / 'macros.duckdb'
    con = duckdb.connect(str(db_file), config={'storage_compatibility_version': 'v1.5.2'})
    con.execute(
        "CREATE MACRO calc_tax(amount DOUBLE, rate DOUBLE := 0.08, label VARCHAR := 'STD') AS "
        "label || ':' || round(amount * rate, 2)::VARCHAR, "
        "(tag VARCHAR) AS 'TAG:' || tag"
    )
    con.execute("COMMENT ON MACRO calc_tax IS 'tax helper'")
    con.close()

    desired_dir = tmp_path / 'des_mac'
    desired_dir.mkdir()
    desired_file = desired_dir / 'macros.duckdb'
    dcon = duckdb.connect(str(desired_file), config={'storage_compatibility_version': 'v1.5.2'})
    dcon.execute(
        "CREATE MACRO calc_tax(amount DOUBLE, rate DOUBLE := 0.08, label VARCHAR := 'STD') AS "
        "label || '=' || round(amount * (1 + rate), 2)::VARCHAR, "
        "(tag VARCHAR) AS 'TAG:' || tag"
    )
    dcon.execute("COMMENT ON MACRO calc_tax IS 'tax helper updated'")
    dcon.close()

    provider = _make_provider()
    try:
        route, baseline, db_name = _capture_file_model(provider, db_file, tmp_path, include_macro_source=True)
        _, desired, _ = _capture_file_model(provider, desired_file, desired_dir, include_macro_source=True)
        mid = _resource_id('macro', [db_name, 'main'], 'calc_tax')

        # 1. Refusal when source_ddl is absent (OID/names alone cannot reconstruct defaults)
        no_src_base = deepcopy(baseline)
        no_src_base['rows'][mid]['native'].pop('source_ddl', None)
        des_try = deepcopy(desired)
        des_try['rows'][mid]['native']['duckdb_change'] = {
            'action': 'replace-macro-preserve-defaults',
            'metadata_reset_acknowledged': True,
            'overload_updates': [{'op': 'update', 'overload_index': 0, 'definition': "label || '=' || round(amount * (1 + rate), 2)::VARCHAR"}],
        }
        p_nosrc = plan(no_src_base, des_try, no_src_base)
        assert not p_nosrc['ready_for_review']
        assert any('source_ddl' in b['reason'] for b in p_nosrc['blockers'])

        # 2. Positive update: updates overload 0 body + comment while automatically preserving `rate := 0.08`, `label := 'STD'`, and overload 1!
        desired['rows'][mid]['native']['duckdb_change'] = {
            'action': 'replace-macro-preserve-defaults',
            'metadata_reset_acknowledged': True,
            'overload_updates': [
                {
                    'op': 'update',
                    'overload_index': 0,
                    'definition': "label || '=' || round(amount * (1 + rate), 2)::VARCHAR",
                }
            ],
        }
        preview = plan(baseline, desired, baseline)
        assert preview['ready_for_review'], preview['blockers']

        apps = DuckDBSchemaApplications(tmp_path / 'receipts.json', clock=lambda: 100)
        receipt = apps.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        applied = apps.apply(
            {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding',
            lambda rec: apply_review(provider, route, rec),
        )
        assert applied['state'] == 'committed', applied
        assert applied['outcome']['rediscovery_verified'] is True

        vcon = duckdb.connect(str(db_file))
        # Calling with 1 arg proves BOTH `rate := 0.08` AND `label := 'STD'` defaults were preserved!
        assert vcon.execute('SELECT calc_tax(100.0)').fetchone()[0] == 'STD=108.0'
        # Calling with 2 args proves `label := 'STD'` default was preserved!
        assert vcon.execute('SELECT calc_tax(100.0, 0.10)').fetchone()[0] == 'STD=110.0'
        # Overload 1 also preserved!
        assert vcon.execute("SELECT calc_tax('VIP')").fetchone()[0] == 'TAG:VIP'
        assert vcon.execute("SELECT comment FROM duckdb_functions() WHERE function_name='calc_tax' LIMIT 1").fetchone()[0] == 'tax helper updated'
        vcon.close()
    finally:
        provider.client.close()


# ---------------------------------------------------------------------------
# DU-AUD-17: Retained-session native DDN transformations & non-transferability
# ---------------------------------------------------------------------------

def test_du_aud_17_retained_session_ddn_temp_attached_uncommitted_and_non_transfer(tmp_path):
    db_file = tmp_path / 'session_main.duckdb'
    att_file = tmp_path / 'attached_aux.duckdb'
    duckdb.connect(str(db_file)).close()
    duckdb.connect(str(att_file)).close()

    provider = _make_provider()
    route = {'database': str(db_file), 'filesystem_root': str(tmp_path)}
    session_info = provider.open_session({'endpoint_id': 'ep-1', 'route': route, 'language_profile': 'duckdb-sql'})
    handle = provider._editor_session({'session_id': session_info['session_id']})
    sid = 'studio-sess-1'

    try:
        # Create uncommitted TEMP table with rows + attach auxiliary database on the retained session
        handle.execute('CREATE TEMP TABLE temp_events (id INTEGER, raw_val VARCHAR)')
        handle.execute("INSERT INTO temp_events VALUES (1, '10'), (2, '25')")
        handle.execute(f"ATTACH '{att_file}' AS aux_db")
        handle.execute('CREATE TABLE aux_db.main.metrics (k VARCHAR, v INTEGER)')

        baseline = retained_ddn.observe(provider.client, handle, 'ep-1', sid)
        assert baseline['provenance']['database_target_id'] == f'retained-session:{sid}'

        # 1. Verify retained-session model is REJECTED by independent-file `plan()`
        with pytest.raises(ValueError, match='Retained-session observations cannot authorize an independent DuckDB migration'):
            plan(baseline, baseline, baseline)

        # 2. Verify independent-file model is REJECTED by retained-session `plan()`
        _, file_model, _ = _capture_file_model(provider, db_file, tmp_path)
        with pytest.raises(ValueError, match='Independent-file DuckDB DDN models cannot authorize a retained-session migration'):
            retained_ddn.plan(provider.client, handle, file_model, file_model, baseline, 'ep-1', sid)

        # 3. Build desired retained DDN:
        #    - Rebuild TEMP table `temp_events` (converting raw_val VARCHAR -> val INTEGER while preserving uncommitted rows!),
        #    - Add column `unit VARCHAR DEFAULT 'ms'` to `aux_db.main.metrics`,
        #    - Create TEMP view `v_temp_events`!
        desired = deepcopy(baseline)
        temp_tid = _resource_id('table', ['temp', 'main'], 'temp_events')
        raw_cid = _resource_id('column', ['temp', 'main', 'temp_events'], 'raw_val')
        val_cid = _resource_id('column', ['temp', 'main', 'temp_events'], 'val')
        desired['rows'].pop(raw_cid)
        desired['rows'][val_cid] = {
            'resource_id': val_cid,
            'kind': 'column',
            'path': ['temp', 'main', 'temp_events', 'val'],
            'name': 'val',
            'system': 'false',
            'native': {
                'system_object': False,
                'observation_scope': 'retained-session',
                'catalog_metadata': {'ordinal_position': 2, 'data_type': 'INTEGER', 'nullable': True, 'default': None},
            },
        }
        desired['rows'][temp_tid]['native']['ddl'] = 'CREATE TEMP TABLE "temp_events" ("id" INTEGER, "val" INTEGER)'
        desired['rows'][temp_tid]['native']['columns'] = [
            {'resource_id': _resource_id('column', ['temp', 'main', 'temp_events'], 'id'), 'name': 'id', 'ordinal_position': 1, 'data_type': 'INTEGER', 'nullable': True, 'default': None},
            {'resource_id': val_cid, 'name': 'val', 'ordinal_position': 2, 'data_type': 'INTEGER', 'nullable': True, 'default': None},
        ]

        # Add column to attached `aux_db.main.metrics`
        unit_cid = _resource_id('column', ['aux_db', 'main', 'metrics'], 'unit')
        metrics_tid = _resource_id('table', ['aux_db', 'main'], 'metrics')
        desired['rows'][unit_cid] = {
            'resource_id': unit_cid,
            'kind': 'column',
            'path': ['aux_db', 'main', 'metrics', 'unit'],
            'name': 'unit',
            'system': 'false',
            'native': {
                'system_object': False,
                'observation_scope': 'retained-session',
                'catalog_metadata': {'ordinal_position': 3, 'data_type': 'VARCHAR', 'nullable': True, 'default': "'ms'"},
            },
        }
        desired['rows'][metrics_tid]['native']['columns'].append({
            'resource_id': unit_cid, 'name': 'unit', 'ordinal_position': 3, 'data_type': 'VARCHAR', 'nullable': True, 'default': "'ms'",
        })

        # Create TEMP view
        tview_id = _resource_id('view', ['temp', 'main'], 'v_temp_events')
        desired['rows'][tview_id] = {
            'resource_id': tview_id,
            'kind': 'view',
            'path': ['temp', 'main', 'v_temp_events'],
            'name': 'v_temp_events',
            'system': 'false',
            'native': {
                'system_object': False,
                'observation_scope': 'retained-session',
                'catalog_metadata': {'temporary': True},
                'ddl': 'CREATE TEMP VIEW "v_temp_events" AS SELECT id, val FROM temp.main.temp_events',
            },
        }

        # Absent fact without explicit deletion must be refused!
        bad_absent = deepcopy(desired)
        bad_absent['rows'].pop(metrics_tid)
        with pytest.raises(ValueError, match='absent retained DDN fact is not an explicit deletion'):
            retained_ddn.plan(provider.client, handle, baseline, bad_absent, baseline, 'ep-1', sid)

        ret_plan = retained_ddn.plan(
            provider.client, handle, baseline, desired, baseline, 'ep-1', sid,
            rebuilds=[{
                'resource_id': temp_tid,
                'complete_definition_confirmed': True,
                'preserve_rows_confirmed': True,
                'column_renames': {'raw_val': 'val'},
                'column_conversions': {'val': 'CAST("raw_val" AS INTEGER)'},
                'loss_acknowledged': True,
            }],
        )
        assert ret_plan['ready_for_review'] is True
        assert ret_plan['format'] == retained_ddn.FORMAT

        ret_archive = DuckDBRetainedApplications(tmp_path / 'ret_receipts.json', clock=lambda: 200)
        # Verify independent-file plan is rejected by DuckDBRetainedApplications.review!
        with pytest.raises( Exception, match='non-transferable'):
            ret_archive.review({'format': 'scratchrobin.duckdb.schema-plan@1'}, baseline, desired, {}, 'owner', 'bind', 'file-1', sid)

        ctx = retained_ddn.context(provider.client, handle, 0)
        ret_receipt = ret_archive.review(ret_plan, baseline, desired, ctx, 'owner', 'bind', 'file-1', sid)
        applied = ret_archive.apply(
            {'review_id': ret_receipt['review_id'], 'review_digest': ret_receipt['review_digest'], 'confirmed': True},
            'owner', 'bind', sid, provider.client, handle, 'ep-1', 0,
        )
        assert applied['state'] == 'applied_pending_caller_transaction', applied
        assert applied['outcome']['commit_dispatched'] is False
        assert applied['outcome']['rediscovery_verified'] is True

        # Uncommitted TEMP rows converted & preserved on original handle!
        assert handle.execute('SELECT id, val FROM temp.main.v_temp_events ORDER BY id').fetchall() == [(1, 10), (2, 25)]
        # Attached table column added!
        cols = [r[0] for r in handle.execute("SELECT column_name FROM duckdb_columns() WHERE database_name='aux_db' AND table_name='metrics' ORDER BY column_index").fetchall()]
        assert cols == ['k', 'v', 'unit']

        # One-shot no-replay check
        replay_attempt = ret_archive.apply(
            {'review_id': ret_receipt['review_id'], 'review_digest': ret_receipt['review_digest'], 'confirmed': True},
            'owner', 'bind', sid, provider.client, handle, 'ep-1', 1,
        )
        assert replay_attempt.get('replay_refused') is True

        # Archive read-only list & get require zero SQL
        listed = ret_archive.list('owner', 'bind')
        assert listed['total'] == 1
    finally:
        provider.client.close()
