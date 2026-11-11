##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Regression tests for the DDN BI Questions & Dashboards Designer (E1-E10)."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile

import duckdb
from flask import Flask

from pgadmin.cdeadmin.design_store import (
    BI_ANALYTICS_PROFILE,
    BIDesignSync,
    CHART_PROFILE_MAP,
    COMPOSED_PANELS_PROFILE,
    DesignStore,
    DesignStoreConflict,
    DesignStoreError,
    DesignStoreForbidden,
    analyze_sbsql_fanout,
    carry_drill_filter_context,
    compile_bi_question_sql,
    dashboard_to_ddn,
    ddn_to_dashboard,
    ddn_to_question,
    default_dashboard_model,
    default_question_model,
    execute_bi_question_connection,
    init_routes_app,
    is_uuid7,
    question_to_ddn,
    sbsql_to_sql_builder_model,
    sql_builder_model_to_sbsql,
    sql_to_bi_question_model,
)


def _verify_ddn_texts_with_node(documents: dict[str, str]) -> dict[str, dict]:
    """Run ScratchRobin's bundled ddn-verifier.js against generated DDN."""
    repo_root = Path(__file__).resolve().parents[2]
    verifier = (
        repo_root
        / 'web/pgadmin/static/vendor/ddn/current/complete/ddn-verifier.js'
    )
    script = (
        "import { pathToFileURL } from 'node:url';\n"
        "const mod = await import(pathToFileURL(process.argv[1]).href);\n"
        "const verifier = mod.createVerifier(\n"
        "  mod.createCompleteRuntimeOptions()\n"
        ");\n"
        "const docs = JSON.parse(process.argv[2]);\n"
        "const out = {};\n"
        "for (const [k, text] of Object.entries(docs)) {\n"
        "  const res = verifier.verifySources({ 'design.ddn': text });\n"
        "  const errs = (res.diagnostics || []).filter(\n"
        "    d => d.severity === 'error'\n"
        "  );\n"
        "  out[k] = { ok: errs.length === 0, errors: errs };\n"
        "}\n"
        "verifier.destroy();\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    proc = subprocess.run(
        ['node', '--input-type=module', '-e', script, str(verifier),
         json.dumps(documents)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


class BIDesignerBackendTests(unittest.TestCase):
    def test_all_chart_profiles_and_ddn_verifier(self):
        docs: dict[str, str] = {}
        for chart_type in sorted(CHART_PROFILE_MAP):
            q = default_question_model(
                name=f'Chart {chart_type}',
                visualization={'type': chart_type},
                preview_rows=[['North', 120], ['South', 85]],
            )
            ddn_text, id_map = question_to_ddn(q)
            self.assertIn(BI_ANALYTICS_PROFILE, ddn_text)
            self.assertIn(CHART_PROFILE_MAP[chart_type][0], ddn_text)
            self.assertTrue(all(is_uuid7(v) for v in id_map.values()))
            docs[f'q_{chart_type}'] = ddn_text

        q_ref = '01950000-0000-7000-8000-000000000001'
        dash = default_dashboard_model(
            name='Executive Overview',
            tabs=[
                {'id': 'overview', 'name': 'Overview'},
                {'id': 'ops', 'name': 'Operations'},
            ],
            cards=[
                {
                    'id': 'rev_bar',
                    'tab_id': 'overview',
                    'type': 'question',
                    'title': 'Revenue by Region',
                    'question': {
                        'question_design_id': q_ref,
                        'pinned_version': 1,
                    },
                    'visualization': {'type': 'bar'},
                },
                {
                    'id': 'note_card',
                    'tab_id': 'overview',
                    'type': 'text',
                    'title': 'Commentary',
                    'text': {'markdown': 'All figures are net.'},
                },
                {
                    'id': 'snap_card',
                    'tab_id': 'ops',
                    'type': 'metric_panel',
                    'title': 'Buffer Snapshot',
                    'metric_panel': {
                        'panel_id': 'buffers',
                        'columns': [
                            {'id': 'measure', 'label': 'Measure'},
                            {'id': 'value', 'label': 'Value'},
                        ],
                        'rows': [
                            {
                                'id': 'hit_ratio',
                                'measure': 'Hit',
                                'value': '99%',
                            },
                        ],
                    },
                },
            ],
            filters=[
                {
                    'id': 'region_flt',
                    'name': 'Region',
                    'type': 'string',
                    'widget': 'select',
                    'targets': [{'card_id': 'rev_bar', 'parameter': 'region'}],
                },
            ],
        )
        dash_ddn, _ = dashboard_to_ddn(dash)
        self.assertIn(COMPOSED_PANELS_PROFILE, dash_ddn)
        self.assertIn(BI_ANALYTICS_PROFILE, dash_ddn)
        docs['dashboard'] = dash_ddn

        results = _verify_ddn_texts_with_node(docs)
        for key, res in results.items():
            self.assertTrue(
                res['ok'],
                msg=f'DDN verifier failed on {key}: {res["errors"]}',
            )

    def test_unified_sbsql_sql_builder_fanout_and_live_sqlite_duckdb(self):
        sbsql = {
            'from': {'relation': ['customers'], 'alias': 'c'},
            'joins': [
                {
                    'type': 'inner',
                    'relation': ['orders'],
                    'alias': 'o',
                    'cardinality': 'one_to_many',
                    'on': [{
                        'left': ['c', 'id'],
                        'op': '=',
                        'right': ['o', 'customer_id'],
                    }],
                },
            ],
            'columns': [{'column': ['c', 'region'], 'alias': 'region'}],
            'measures': [{
                'function': 'sum',
                'column': ['o', 'amount'],
                'alias': 'total_sales',
            }],
            'filters': [{
                'column': ['o', 'status'],
                'operator': 'eq',
                'parameter': 'order_status',
            }],
            'order_by': [{'expr': ['c', 'region'], 'direction': 'asc'}],
            'limit': 50,
        }
        warnings = analyze_sbsql_fanout(sbsql)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]['code'], 'one_to_many_fanout')

        # Round-trip through sdk.sql_builder model
        builder_model = sbsql_to_sql_builder_model(sbsql)
        restored = sql_builder_model_to_sbsql(builder_model)
        self.assertEqual(
            restored['from'], {'relation': ['customers'], 'alias': 'c'}
        )
        self.assertEqual(len(restored['joins']), 1)
        self.assertEqual(restored['measures'][0]['function'], 'sum')

        question = default_question_model(
            name='Regional Sales',
            sbsql=sbsql,
            parameters=[{
                'id': 'order_status',
                'name': 'Order Status',
                'type': 'string',
                'required': True,
                'default': 'paid',
            }],
        )
        compiled = compile_bi_question_sql(
            question,
            dialect='sqlite',
            parameter_values={'order_status': "paid'; DROP TABLE orders;--"},
        )
        # Bound parameter value must NEVER be spliced into SQL text (E2)
        self.assertNotIn('DROP TABLE', compiled['sql'])
        self.assertIn(':order_status_1', compiled['sql'])
        self.assertEqual(
            compiled['bound_params']['order_status_1'],
            "paid'; DROP TABLE orders;--",
        )

        # Live SQLite execution
        sq = sqlite3.connect(':memory:')
        try:
            sq.executescript("""
                CREATE TABLE customers (id INTEGER PRIMARY KEY, region TEXT);
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY,
                    customer_id INTEGER,
                    status TEXT,
                    amount REAL
                );
                INSERT INTO customers VALUES (1, 'EU'), (2, 'US');
                INSERT INTO orders VALUES
                    (10, 1, 'paid', 150.0),
                    (11, 1, 'cancelled', 999.0),
                    (12, 2, 'paid', 250.0);
            """)
            sq_res = execute_bi_question_connection(
                sq,
                question,
                dialect='sqlite',
                parameter_values={'order_status': 'paid'},
            )
            self.assertEqual(sq_res['rows'], [['EU', 150.0], ['US', 250.0]])
        finally:
            sq.close()

        # Live DuckDB execution
        dk = duckdb.connect(':memory:')
        try:
            dk.execute(
                'CREATE TABLE customers (id INTEGER, region VARCHAR)'
            )
            dk.execute(
                'CREATE TABLE orders '
                '(id INTEGER, customer_id INTEGER, status VARCHAR, '
                'amount DOUBLE)'
            )
            dk.execute("INSERT INTO customers VALUES (1, 'EU'), (2, 'US')")
            dk.execute(
                "INSERT INTO orders VALUES "
                "(10, 1, 'paid', 150.0), "
                "(11, 1, 'draft', 50.0), "
                "(12, 2, 'paid', 250.0)"
            )
            dk_res = execute_bi_question_connection(
                dk,
                question,
                dialect='duckdb',
                parameter_values={'order_status': 'paid'},
            )
            self.assertEqual(dk_res['rows'], [['EU', 150.0], ['US', 250.0]])
        finally:
            dk.close()

        # SQL-to-question fidelity check (E2)
        exact = sql_to_bi_question_model(
            'SELECT region, SUM(amount) AS total FROM orders '
            'WHERE status = {{st}} GROUP BY region LIMIT 25'
        )
        self.assertEqual(exact['fidelity'], 'exact')
        self.assertEqual(exact['question']['query']['kind'], 'sbsql')

        unmappable = sql_to_bi_question_model(
            'WITH cte AS (SELECT 1 AS x) SELECT x FROM cte'
        )
        self.assertEqual(unmappable['fidelity'], 'none')
        self.assertEqual(unmappable['question']['query']['kind'], 'sql')

    def test_lossless_ddn_roundtrip_and_e3_e5_e6_e7_policies(self):
        q = default_question_model(
            name='Filtered Revenue',
            parameters=[{
                'id': 'min_amt',
                'name': 'Min Amount',
                'type': 'number',
                'default': 500,
            }],
            visualization={'type': 'line', 'settings': {'smooth': True}},
        )
        # E3: saved filter value flagged for review
        self.assertEqual(len(q['review_flags']['saved_filter_values']), 1)

        ddn_1, ids_1 = question_to_ddn(
            q,
            layout_positions={},
            question_notes='Initial question note',
        )
        root_id = ids_1['question:root']
        ddn_pos, ids_2 = question_to_ddn(
            q,
            element_ids=ids_1,
            layout_positions={root_id: {'x': 140.0, 'y': 260.0}},
            question_notes='Initial question note',
        )
        self.assertEqual(ids_1, ids_2)
        parsed = ddn_to_question(ddn_pos)
        self.assertEqual(parsed['question'], q)
        self.assertEqual(parsed['element_ids'], ids_1)
        self.assertEqual(
            parsed['layout_positions'][root_id],
            {'x': 140.0, 'y': 260.0},
        )

        # E3: forbidden secrets/recipients/grants rejected
        with self.assertRaises(DesignStoreError):
            default_question_model(
                name='Bad',
                visualization={
                    'type': 'bar',
                    'settings': {'recipients': ['leak@example.com']},
                },
            )
        with self.assertRaises(DesignStoreError):
            default_question_model(
                name='BadSecret',
                visualization={
                    'type': 'bar',
                    'settings': {'password': 's3cr3t'},
                },
            )

        # E6: write-back & mutation SQL rejected
        with self.assertRaises(DesignStoreError):
            default_question_model(
                name='Mutate',
                raw_sql='UPDATE orders SET amount = 0',
            )
        with self.assertRaises(DesignStoreError):
            default_dashboard_model(
                name='BadDash',
                interaction={'write_back': True},
            )

        # E5 & E7: dashboard interaction defaults, per-card override, drill
        # context carry, and static metric_panel snapshot mode
        q_uuid = '01950000-0000-7000-8000-000000000099'
        target_uuid = '01950000-0000-7000-8000-000000000088'
        dash = default_dashboard_model(
            name='Drill Test',
            cards=[
                {
                    'id': 'c_cross',
                    'tab_id': 'main',
                    'type': 'question',
                    'title': 'Cross Filter Card',
                    'click_behavior': 'inherit',
                    'question': {'question_design_id': q_uuid},
                    'visualization': {'type': 'bar'},
                },
                {
                    'id': 'c_none',
                    'tab_id': 'main',
                    'type': 'question',
                    'title': 'No Click Card',
                    'click_behavior': 'none',
                    'question': {'question_design_id': q_uuid},
                    'visualization': {'type': 'pie'},
                },
                {
                    'id': 'c_snap',
                    'tab_id': 'main',
                    'type': 'metric_panel',
                    'title': 'Static Snapshot',
                    'metric_panel': {'panel_id': 'io_stats'},
                },
            ],
            filters=[{
                'id': 'tenant',
                'name': 'Tenant',
                'type': 'string',
                'pinned_by_author': True,
                'default': 'acme',
            }],
            links=[{
                'id': 'lnk_1',
                'card_id': 'c_cross',
                'target_design_id': target_uuid,
                'field_map': {'region_col': 'region'},
            }],
        )
        self.assertEqual(
            dash['cards'][2]['metric_panel']['snapshot_mode'], 'static'
        )
        ctx = carry_drill_filter_context(
            dash,
            card_id='c_cross',
            active_filters={'year': 2026},
            cross_filters={'segment': 'enterprise'},
            clicked_row={'region_col': 'EMEA'},
        )
        self.assertEqual(ctx['effective_click_behavior'], 'cross_filter')
        self.assertTrue(ctx['auto_apply_filters'])
        self.assertEqual(ctx['filter_state_scope'], 'personal')
        self.assertEqual(
            ctx['carried_filters']['tenant'], 'acme'
        )
        self.assertEqual(ctx['carried_filters']['year'], 2026)
        self.assertEqual(ctx['carried_filters']['segment'], 'enterprise')
        self.assertEqual(ctx['carried_filters']['region'], 'EMEA')
        self.assertEqual(ctx['target_design_id'], target_uuid)

        ctx_none = carry_drill_filter_context(
            dash,
            card_id='c_none',
            active_filters={'year': 2026},
            cross_filters={'segment': 'enterprise'},
        )
        self.assertEqual(ctx_none['effective_click_behavior'], 'none')
        self.assertNotIn('segment', ctx_none['carried_filters'])

    def test_e4_acceptance_outward_review_and_git_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DesignStore(f'{tmp}/designs.db')
            sync = BIDesignSync(store)

            q_created = sync.create_question(
                project_id='p1',
                key='rev-q',
                title='Revenue Question',
                actor_id=10,
                question=default_question_model(
                    name='Revenue Question',
                    verification_tier='verified',
                ),
            )
            q_id = q_created['design']['id']

            d_created = sync.create_dashboard(
                project_id='p1',
                key='exec-dash',
                title='Executive Dashboard',
                actor_id=10,
                dashboard=default_dashboard_model(
                    name='Executive Dashboard',
                    cards=[{
                        'id': 'c1',
                        'tab_id': 'main',
                        'type': 'question',
                        'title': 'Rev Card',
                        'question': {'question_design_id': q_id},
                        'visualization': {'type': 'bar'},
                    }],
                ),
            )
            d_id = d_created['design']['id']

            # Cannot accept dashboard while referenced question is unaccepted
            store.advance_status(d_id, 1, 'in_review', actor_id=10)
            with self.assertRaises(DesignStoreConflict):
                sync.accept_bi_design(d_id, 1, actor_id=10)

            # Accept question first -> active, outward_effects_activated False
            store.advance_status(q_id, 1, 'in_review', actor_id=10)
            q_acc = sync.accept_bi_design(q_id, 1, actor_id=10)
            self.assertFalse(q_acc['outward_effects_activated'])
            self.assertEqual(q_acc['active_outward_effects'], [])

            # Now dashboard accepts cleanly, still with 0 outward effects
            d_acc = sync.accept_bi_design(d_id, 1, actor_id=10)
            self.assertFalse(d_acc['outward_effects_activated'])
            self.assertEqual(d_acc['design']['active_version'], 1)

            # Separate outward-effect review flags new recipients
            rev_sub = sync.review_outward_effect(
                d_id,
                effect_kind='subscription',
                enabled=True,
                config={
                    'schedule': '0 8 * * 1',
                    'recipients': ['ops@example.com'],
                },
                reviewer_id=10,
            )
            self.assertTrue(rev_sub['enabled'])
            self.assertEqual(
                rev_sub['exposure_diff']['added_recipients'],
                ['ops@example.com'],
            )

            # Editing a verified question's query drops tier back to draft
            store.branch_draft_from_accepted(q_id, actor_id=10)
            q_head = store.get_design(q_id)
            edited_q = default_question_model(
                name='Revenue Question',
                verification_tier='verified',
                sbsql={
                    'from': {'relation': ['main', 'invoices'], 'alias': 'i'},
                    'columns': [{'column': ['i', 'country'], 'alias': 'c'}],
                    'measures': [{
                        'function': 'count',
                        'column': None,
                        'alias': 'cnt',
                    }],
                },
            )
            saved_q = sync.save_question(
                q_id,
                expected_head_version=q_head['head_version'],
                actor_id=10,
                question=edited_q,
            )
            self.assertEqual(
                saved_q['question']['verification_tier'], 'draft'
            )

            # Git save and load preserve DDN text without secrets
            git_dir = f'{tmp}/git-bi'
            subprocess.run(
                ['git', 'init', git_dir], check=True, capture_output=True
            )
            store.link_git(
                d_id, repository=git_dir, path='bi/exec_dashboard.ddn'
            )
            exp = store.export_to_git(d_id, git_dir, commit=True)
            self.assertEqual(exp['sync_state'], 'synced')
            git_text = (Path(git_dir) / 'bi/exec_dashboard.ddn').read_text()
            self.assertNotIn('ops@example.com', git_text)

    def test_e8_byok_ai_draft_and_agent_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DesignStore(f'{tmp}/designs.db')
            sync = BIDesignSync(store)
            sync.create_question(
                project_id='p1',
                key='monthly-churn',
                title='Monthly Churn Rate',
                actor_id=5,
            )

            # Missing BYOK key is refused
            with self.assertRaises(DesignStoreError):
                sync.propose_ai_draft(
                    project_id='p1',
                    prompt='Monthly Churn',
                    actor_id=5,
                )

            drafted = sync.propose_ai_draft(
                project_id='p1',
                prompt='Monthly Churn',
                actor_id=5,
                byok_api_key='sk-ephemeral-not-persisted',
                schema_hint={
                    'tables': [{
                        'relation': ['analytics', 'subscriptions'],
                        'columns': ['cohort_month', 'churned_mrr'],
                    }],
                },
            )
            self.assertGreaterEqual(len(drafted['existing_matches']), 1)
            self.assertEqual(
                drafted['design']['version']['status'], 'draft'
            )
            self.assertEqual(
                drafted['design']['version']['origin'], 'ai:draft'
            )
            self.assertNotIn(
                'sk-ephemeral-not-persisted',
                drafted['design']['version']['ddn_text'],
            )

            # AI / automated agents are strictly forbidden from accepting or
            # enabling outward exposure
            ai_id = drafted['design']['id']
            store.advance_status(ai_id, 1, 'in_review', actor_id=5)
            with self.assertRaises(DesignStoreForbidden):
                sync.accept_bi_design(
                    ai_id, 1, actor_id=5, actor_kind='agent'
                )

    def test_e9_remote_dashboard_server_and_narrowing_device_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DesignStore(f'{tmp}/designs.db')
            sync = BIDesignSync(store, token_secret='kiosk-hmac-key')
            q = sync.create_question(
                project_id='p1', key='q1', title='Q1', actor_id=1
            )
            store.advance_status(q['design']['id'], 1, 'in_review', actor_id=1)
            sync.accept_bi_design(q['design']['id'], 1, actor_id=1)

            d = sync.create_dashboard(
                project_id='p1',
                key='wallboard',
                title='Warehouse Wallboard',
                actor_id=1,
                dashboard=default_dashboard_model(
                    name='Warehouse Wallboard',
                    cards=[{
                        'id': 'c1',
                        'tab_id': 'main',
                        'type': 'question',
                        'title': 'Orders',
                        'question': {
                            'question_design_id': q['design']['id'],
                        },
                        'visualization': {'type': 'metric'},
                    }],
                ),
            )
            d_id = d['design']['id']
            store.advance_status(d_id, 1, 'in_review', actor_id=1)
            sync.accept_bi_design(d_id, 1, actor_id=1)

            pub = sync.publish_to_dashboard_server(
                d_id,
                publisher_user_id=42,
                reviewer_id=1,
                locked_filters={'region': ['EU', 'US'], 'plant': 'BER-1'},
            )
            token = sync.mint_device_token(
                pub['id'],
                device_label='lobby-tv',
            )

            # Narrowing ['EU', 'US'] -> ['EU'] succeeds and stays display-only
            rendered = sync.render_dashboard_server_view(
                pub['id'],
                device_token=token,
                requested_filters={'region': 'EU'},
            )
            self.assertTrue(rendered['display_only'])
            self.assertEqual(rendered['publisher_user_id'], 42)
            self.assertEqual(rendered['effective_filters']['region'], ['EU'])
            self.assertEqual(rendered['effective_filters']['plant'], 'BER-1')
            self.assertFalse(rendered['capabilities']['can_edit'])
            self.assertFalse(rendered['capabilities']['can_open_sql'])

            # Widening to 'APAC' or changing 'plant' is rejected
            with self.assertRaises(DesignStoreForbidden):
                sync.render_dashboard_server_view(
                    pub['id'],
                    device_token=token,
                    requested_filters={'region': 'APAC'},
                )
            with self.assertRaises(DesignStoreForbidden):
                sync.render_dashboard_server_view(
                    pub['id'],
                    device_token=token,
                    requested_filters={'plant': 'NYC-2'},
                )

    def test_e10_superset_zip_and_metabase_bundle_importers(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DesignStore(f'{tmp}/designs.db')
            sync = BIDesignSync(store)

            # Build an in-memory Apache Superset YAML/JSON export ZIP
            sup_buf = io.BytesIO()
            with zipfile.ZipFile(sup_buf, 'w') as zf:
                zf.writestr(
                    'export/databases/db.json',
                    json.dumps({
                        'uuid': 'db-1',
                        'database_name': 'warehouse',
                        'sqlalchemy_uri': 'postgresql://user:s3cret@host/db',
                    }),
                )
                zf.writestr(
                    'export/datasets/orders.json',
                    json.dumps({
                        'uuid': 'ds-orders',
                        'schema': 'sales',
                        'table_name': 'orders',
                    }),
                )
                zf.writestr(
                    'export/datasets/jinja_ds.json',
                    json.dumps({
                        'uuid': 'ds-jinja',
                        'table_name': 'custom_q',
                        'sql': (
                            "SELECT region, amount FROM orders WHERE "
                            "region = '{{ url_param(\"region\", \"EU\") }}'"
                        ),
                    }),
                )
                zf.writestr(
                    'export/charts/c1.json',
                    json.dumps({
                        'uuid': 'chart-uuid-1',
                        'slice_name': 'Sales by Country',
                        'viz_type': 'echarts_timeseries_bar',
                        'dataset_uuid': 'ds-orders',
                        'params': {
                            'groupby': ['country'],
                            'metrics': [{
                                'label': 'gross_sales',
                                'aggregate': 'SUM',
                                'column': {'column_name': 'amount'},
                            }],
                        },
                    }),
                )
                zf.writestr(
                    'export/charts/c2.json',
                    json.dumps({
                        'uuid': 'chart-uuid-2',
                        'slice_name': 'World Map Custom',
                        'viz_type': 'world_map_custom',
                        'dataset_uuid': 'ds-jinja',
                        'params': {},
                    }),
                )
                zf.writestr(
                    'export/dashboards/d1.json',
                    json.dumps({
                        'uuid': 'dash-uuid-1',
                        'dashboard_title': 'Global Sales Superset',
                        'position': {
                            'CHART-1': {
                                'type': 'CHART',
                                'meta': {'uuid': 'chart-uuid-1'},
                            },
                            'MD-1': {
                                'type': 'MARKDOWN',
                                'meta': {'code': 'Imported header'},
                            },
                        },
                    }),
                )

            sup_res = sync.import_superset_zip(
                sup_buf.getvalue(),
                project_id='p1',
                actor_id=3,
            )
            self.assertEqual(sup_res['status'], 'draft')
            self.assertEqual(len(sup_res['questions']), 2)
            self.assertEqual(len(sup_res['dashboards']), 1)
            self.assertGreaterEqual(
                sup_res['loss_report']['loss_count'], 1
            )
            for q_doc in sup_res['questions']:
                self.assertEqual(q_doc['version']['status'], 'draft')
                self.assertNotIn(
                    's3cret', q_doc['version']['ddn_text']
                )

            # Import Metabase serialization bundle
            mb_bundle = {
                'pulses': [{'name': 'Daily email', 'recipients': ['a@b.c']}],
                'tables': {'tbl_orders': ['public', 'orders']},
                'cards': [
                    {
                        'entity_id': 'mb_card_1',
                        'name': 'MB Orders by Tier',
                        'display': 'bar',
                        'dataset_query': {
                            'type': 'query',
                            'query': {
                                'source-table': 'tbl_orders',
                                'breakout': [['field', 'tier']],
                                'aggregation': [['sum', ['field', 'total']]],
                            },
                        },
                    },
                    {
                        'entity_id': 'mb_card_2',
                        'name': 'MB Native Filter Q',
                        'display': 'funnel_3d',
                        'dataset_query': {
                            'type': 'native',
                            'native': {
                                'query': (
                                    'SELECT id FROM orders WHERE {{date_flt}}'
                                ),
                                'template-tags': {
                                    'date_flt': {
                                        'type': 'dimension',
                                        'display-name': 'Order Date',
                                    },
                                },
                            },
                        },
                    },
                ],
                'dashboards': [
                    {
                        'entity_id': 'mb_dash_1',
                        'name': 'MB Executive Board',
                        'dashcards': [
                            {
                                'card_entity_id': 'mb_card_1',
                                'col': 0,
                                'row': 0,
                                'size_x': 12,
                                'size_y': 8,
                            },
                        ],
                        'parameters': [
                            {'id': 'p1', 'slug': 'tier', 'name': 'Tier'},
                        ],
                    },
                ],
            }
            mb_res = sync.import_metabase_bundle(
                mb_bundle,
                project_id='p1',
                actor_id=3,
            )
            self.assertEqual(mb_res['status'], 'draft')
            self.assertEqual(len(mb_res['questions']), 2)
            self.assertEqual(len(mb_res['dashboards']), 1)
            loss_codes = {
                item['code'] for item in mb_res['loss_report']['items']
            }
            self.assertIn('pulses_alerts_excluded', loss_codes)
            self.assertIn('field_filter_tag_simplified', loss_codes)
            self.assertIn('unsupported_display', loss_codes)

    def test_bi_http_routes_and_remote_kiosk_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Flask(__name__)
            app.secret_key = 'test-bi-route-secret'
            app.config['TESTING'] = True
            app.config['LOGIN_DISABLED'] = True
            app.config['CDEADMIN_DESIGN_STORE_PATH'] = f'{tmp}/designs.db'
            init_routes_app(app)

            client = app.test_client()
            q_resp = client.post(
                '/cdeadmin/api/projects/p1/designs',
                json={
                    'mode': 'create_question',
                    'key': 'orders-q',
                    'title': 'Orders Question',
                },
            )
            self.assertEqual(q_resp.status_code, 200)
            q_id = q_resp.get_json()['data']['id']

            sql_resp = client.post(
                f'/cdeadmin/api/projects/p1/designs/{q_id}/bi/sql-bridge',
                json={'action': 'compile_sql', 'dialect': 'postgresql'},
            )
            self.assertEqual(sql_resp.status_code, 200)
            self.assertIn('SELECT', sql_resp.get_json()['data']['sql'])

            # Advance & accept question
            client.post(
                f'/cdeadmin/api/projects/p1/designs/{q_id}/versions/1/status',
                json={'status': 'in_review'},
            )
            acc_q = client.post(
                f'/cdeadmin/api/projects/p1/designs/{q_id}/versions/1/accept',
                json={},
            )
            self.assertEqual(acc_q.status_code, 200)
            self.assertFalse(
                acc_q.get_json()['data']['outward_effects_activated']
            )

            # Create, advance & accept dashboard
            d_resp = client.post(
                '/cdeadmin/api/projects/p1/designs',
                json={
                    'mode': 'create_dashboard',
                    'key': 'orders-dash',
                    'title': 'Orders Dashboard',
                    'dashboard': default_dashboard_model(
                        name='Orders Dashboard',
                        cards=[{
                            'id': 'c1',
                            'tab_id': 'main',
                            'type': 'question',
                            'title': 'Orders',
                            'question': {'question_design_id': q_id},
                            'visualization': {'type': 'bar'},
                        }],
                    ),
                },
            )
            self.assertEqual(d_resp.status_code, 200)
            d_id = d_resp.get_json()['data']['id']
            client.post(
                f'/cdeadmin/api/projects/p1/designs/{d_id}/versions/1/status',
                json={'status': 'in_review'},
            )
            acc_d = client.post(
                f'/cdeadmin/api/projects/p1/designs/{d_id}/versions/1/accept',
                json={},
            )
            self.assertEqual(acc_d.status_code, 200)

            # Publish to remote dashboard server & mint token
            pub_resp = client.post(
                f'/cdeadmin/api/projects/p1/designs/{d_id}/bi/outward-review',
                json={
                    'effect_kind': 'dashboard_server',
                    'enabled': True,
                    'publisher_user_id': 9,
                    'config': {'locked_filters': {'region': ['EU', 'US']}},
                },
            )
            self.assertEqual(pub_resp.status_code, 200)
            pub_id = pub_resp.get_json()['data']['id']

            tok_resp = client.post(
                f'/cdeadmin/api/projects/p1/designs/{d_id}/bi/outward-review',
                json={
                    'action': 'mint_token',
                    'publication_id': pub_id,
                    'device_label': 'tv-north',
                },
            )
            self.assertEqual(tok_resp.status_code, 200)
            token = tok_resp.get_json()['data']['device_token']

            # Display-only kiosk endpoint works with Bearer token + narrowing
            kiosk_ok = client.get(
                f'/cdeadmin/api/bi-server/dashboards/{pub_id}'
                '?filters=%7B%22region%22%3A%22EU%22%7D',
                headers={'Authorization': f'Bearer {token}'},
            )
            self.assertEqual(kiosk_ok.status_code, 200)
            kiosk_data = kiosk_ok.get_json()['data']
            self.assertTrue(kiosk_data['display_only'])
            self.assertEqual(
                kiosk_data['effective_filters']['region'], ['EU']
            )

            # Widening filter on kiosk endpoint returns 403
            kiosk_bad = client.get(
                f'/cdeadmin/api/bi-server/dashboards/{pub_id}'
                '?filters=%7B%22region%22%3A%22APAC%22%7D',
                headers={'Authorization': f'Bearer {token}'},
            )
            self.assertEqual(kiosk_bad.status_code, 403)

            # Superset base64 ZIP route check
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w') as zf:
                zf.writestr(
                    'export/charts/c.json',
                    json.dumps({
                        'uuid': 'u1',
                        'slice_name': 'Imported Slice',
                        'viz_type': 'pie',
                    }),
                )
            imp_resp = client.post(
                '/cdeadmin/api/projects/p1/designs',
                json={
                    'mode': 'import_superset',
                    'zip_base64': base64.b64encode(buf.getvalue()).decode(),
                },
            )
            self.assertEqual(imp_resp.status_code, 200)
            self.assertEqual(
                len(imp_resp.get_json()['data']['questions']), 1
            )

            # Legacy ScratchRobin BI JSON cutover bridge -> Draft DDN
            legacy_resp = client.post(
                '/cdeadmin/api/projects/p1/designs',
                json={
                    'mode': 'import_legacy_bi',
                    'endpoint_id': 'ep-legacy',
                    'bundle': {
                        'alerts': [{'id': 'a1'}],
                        'embeds': [{'id': 'e1'}],
                        'questions': [
                            {
                                'question_id': 'lq-builder',
                                'status': 'active',
                                'definition': {
                                    'name': 'Legacy Regional Revenue',
                                    'collection_id': 'col-1',
                                    'query': {
                                        'kind': 'builder',
                                        'builder': {
                                            'source': {
                                                'relation': [
                                                    'public', 'orders'
                                                ]
                                            },
                                            'columns': [
                                                {'column': 'region'}
                                            ],
                                            'group_by': [
                                                {'column': 'region'}
                                            ],
                                            'aggregations': [
                                                {
                                                    'function': 'sum',
                                                    'column': 'amount',
                                                    'alias': 'rev',
                                                }
                                            ],
                                            'filters': [
                                                {
                                                    'column': 'region',
                                                    'operator': 'eq',
                                                    'parameter_id': 'reg_p',
                                                }
                                            ],
                                            'order_by': [
                                                {
                                                    'column': 'region',
                                                    'direction': 'asc',
                                                }
                                            ],
                                            'limit': 50,
                                        },
                                    },
                                    'parameters': [
                                        {
                                            'id': 'reg_p',
                                            'name': 'Region',
                                            'type': 'string',
                                        }
                                    ],
                                    'visualization': {'type': 'bar'},
                                },
                            },
                            {
                                'question_id': 'lq-sem',
                                'status': 'archived',
                                'definition': {
                                    'name': 'Legacy Semantic Question',
                                    'semantic_model': {'id': 'sm-99'},
                                    'query': {
                                        'kind': 'semantic',
                                        'builder': {
                                            'group_by': ['tier'],
                                            'aggregations': [
                                                {'measure_id': 'mrr'}
                                            ],
                                        },
                                    },
                                    'visualization': {'type': 'line'},
                                },
                            },
                        ],
                        'dashboards': [
                            {
                                'dashboard_id': 'ld-1',
                                'status': 'active',
                                'definition': {
                                    'name': 'Legacy Executive Board',
                                    'tabs': [{'id': 'main', 'name': 'Main'}],
                                    'cards': [
                                        {
                                            'id': 'c_rev',
                                            'tab_id': 'main',
                                            'type': 'question',
                                            'title': 'Regional Revenue',
                                            'layout': {
                                                'x': 0, 'y': 0,
                                                'w': 12, 'h': 8,
                                            },
                                            'question': {
                                                'question_id': 'lq-builder',
                                                'revision': 1,
                                            },
                                        },
                                        {
                                            'id': 'c_mon',
                                            'tab_id': 'main',
                                            'type': 'metric_panel',
                                            'title': 'CPU Snapshot',
                                            'layout': {
                                                'x': 12, 'y': 0,
                                                'w': 12, 'h': 8,
                                            },
                                            'metric_panel': {
                                                'panel_id': 'cpu',
                                                'columns': [
                                                    {
                                                        'id': 'measure',
                                                        'label': 'Measure',
                                                    }
                                                ],
                                                'rows': [
                                                    {
                                                        'id': 'r1',
                                                        'measure': '42%',
                                                    }
                                                ],
                                            },
                                        },
                                    ],
                                    'filters': [
                                        {
                                            'id': 'f_reg',
                                            'name': 'Region',
                                            'type': 'string',
                                            'widget': 'select',
                                            'operator': 'eq',
                                            'targets': [
                                                {
                                                    'card_id': 'c_rev',
                                                    'parameter_id': 'reg_p',
                                                }
                                            ],
                                        }
                                    ],
                                    'drill_throughs': [
                                        {
                                            'id': 'dt1',
                                            'source_card_id': 'c_rev',
                                            'target': {
                                                'kind': 'question',
                                                'question_id': 'lq-sem',
                                                'revision': 1,
                                                'parameters': {
                                                    'tier': {
                                                        'column': 'region'
                                                    }
                                                },
                                            },
                                        }
                                    ],
                                },
                            }
                        ],
                    },
                },
            )
            self.assertEqual(legacy_resp.status_code, 200)
            legacy_data = legacy_resp.get_json()['data']
            self.assertEqual(legacy_data['status'], 'draft')
            self.assertEqual(
                legacy_data['source_format'], 'legacy_scratchrobin_bi'
            )
            self.assertEqual(len(legacy_data['questions']), 2)
            self.assertEqual(len(legacy_data['dashboards']), 1)
            loss_codes = {
                item['code'] for item in legacy_data['loss_report']['items']
            }
            self.assertIn('legacy_alerts_not_auto_enabled', loss_codes)
            self.assertIn('legacy_embeds_not_auto_enabled', loss_codes)
            self.assertIn('legacy_semantic_query_converted', loss_codes)
            self.assertIn('metric_panel_static_snapshot', loss_codes)
            self.assertIn('archived_status_imported_as_draft', loss_codes)


if __name__ == '__main__':
    unittest.main()
