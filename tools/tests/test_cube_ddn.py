##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Regression suite for Cube Designer Phase 1 DDN verification & extensions."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

import duckdb
from flask import Flask

from pgadmin.cdeadmin.design_store import (
    DesignStore,
    StoreDDNProcess,
    init_routes_app,
)
from pgadmin.cdeadmin.design_store.routes import SEMANTIC_SERVICE_EXTENSION_KEY
from pgadmin.cdeadmin.design_store.cube_ddn import (
    CubeDesignSync,
    ddn_to_semantic_model,
    default_cube_model,
    preview_cube_materialization_plan,
    semantic_model_to_ddn,
)
from pgadmin.cdeadmin.design_store.cube_extensions import (
    check_cube_against_connection,
    execute_cube_try_query,
    propose_cube_ai_draft,
    reduce_cube_aggregations,
)
from pgadmin.cdeadmin.semantic_models import (
    SemanticModelError,
    SemanticModelService,
    public_model,
    validate_model,
)
from pgadmin.cdeadmin.semantic_models.compiler import compile_sql
from pgadmin.cdeadmin.semantic_models.models import (
    CubeAggregationPlan,
    CubeDimension,
    CubeMeasure,
    CubePerspective,
    filter_model_for_role,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER_JS = (
    REPO_ROOT
    / 'web/pgadmin/static/vendor/ddn/current/complete/ddn-verifier.js'
)


class _MemorySemanticRepo:
    def __init__(self):
        self.rows = {}
        self.snapshots = {}

    @staticmethod
    def new_definition(**values):
        return SimpleNamespace(**values)

    def list(self, user_id, endpoint_id):
        return [
            r for r in self.rows.values()
            if r.user_id == user_id and r.endpoint_id == endpoint_id
        ]

    def get(self, user_id, endpoint_id, model_id):
        row = self.rows.get(model_id)
        if row and row.user_id == user_id and row.endpoint_id == endpoint_id:
            return row
        return None

    def save(self, row, snapshot):
        self.rows[row.id] = row
        self.snapshots.setdefault(row.id, []).append(SimpleNamespace(
            revision=row.revision,
            status=row.status,
            definition=snapshot,
            created_at=datetime.now(timezone.utc),
        ))

    def revisions(self, model_id):
        return list(reversed(self.snapshots.get(model_id, [])))


def _verify_ddn_documents(documents: dict[str, str]) -> dict[str, dict]:
    """Run the real vendored ddn-verifier.js with review=true on DDN texts."""
    node_script = f"""
import * as api from {json.dumps('./' + str(VERIFIER_JS.relative_to(REPO_ROOT)))};
const payload = JSON.parse(process.argv[1]);
const v = api.createVerifier(api.createCompleteRuntimeOptions());
const out = {{}};
try {{
  for (const [label, src] of Object.entries(payload)) {{
    const res = await api.verifySourcesWithModel(
      v,
      {{
        entry: 'cube.ddn',
        files: [{{
          id: 'cube.ddn',
          text: src,
          revision: '1',
          encoding: 'utf-8',
          writable: true,
        }}],
      }},
      {{
        level: 'semantic',
        scope: {{ kind: 'workarea' }},
        purpose: 'view',
        review: true,
      }}
    );
    out[label] = {{
      outcome: res.report.outcome,
      complete: Boolean(res.report.coverage && res.report.coverage.complete),
      diagnostics: res.report.diagnostics || [],
    }};
  }}
  console.log(JSON.stringify(out));
}} finally {{
  v.destroy();
}}
"""
    proc = subprocess.run(
        ['node', '--input-type=module', '-e', node_script, json.dumps(documents)],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


def _sample_phase1_cube() -> dict:
    return {
        'name': 'Fulfillment Revenue Cube',
        'description': 'Enterprise revenue cube with "quoted" notes & KPIs',
        'semantic_family': 'relational',
        'sources': [
            {
                'id': 'orders',
                'resource_id': 'table:main:orders',
                'relation': ['orders'],
                'alias': 'orders',
                'source_kind': 'table',
                'classification': 'fact',
                'grain': [{'source_id': 'orders', 'field': 'order_id'}],
            },
            {
                'id': 'customers',
                'resource_id': 'table:main:customers',
                'relation': ['customers'],
                'alias': 'customers',
                'source_kind': 'table',
                'classification': 'dimension',
                'grain': [{'source_id': 'customers', 'field': 'customer_id'}],
            },
            {
                'id': 'calendar',
                'resource_id': 'table:main:calendar',
                'relation': ['calendar'],
                'alias': 'calendar',
                'source_kind': 'table',
                'classification': 'dimension',
                'grain': [{'source_id': 'calendar', 'field': 'date_key'}],
            },
        ],
        'joins': [
            {
                'id': 'orders_customer',
                'left_source': 'orders',
                'right_source': 'customers',
                'join_type': 'left',
                'cardinality': 'many-to-one',
                'active': True,
                'predicates': [{
                    'left': {'source_id': 'orders', 'field': 'customer_id'},
                    'right': {
                        'source_id': 'customers', 'field': 'customer_id',
                    },
                }],
            },
            {
                'id': 'orders_calendar',
                'left_source': 'orders',
                'right_source': 'calendar',
                'join_type': 'left',
                'cardinality': 'many-to-one',
                'active': True,
                'predicates': [{
                    'left': {'source_id': 'orders', 'field': 'order_date'},
                    'right': {'source_id': 'calendar', 'field': 'date_key'},
                }],
            },
        ],
        'dimensions': [
            CubeDimension(
                id='customer',
                name='Customer',
                field={'source_id': 'customers', 'field': 'customer_name'},
                key_field={'source_id': 'customers', 'field': 'customer_id'},
                name_field={
                    'source_id': 'customers', 'field': 'customer_name',
                },
                join_id='orders_customer',
                unknown_member_policy='unknown',
                unknown_member_caption='Unassigned Customer',
                visible_roles=('analyst', 'finance_exec'),
                attributes=(
                    {
                        'id': 'customer_tier',
                        'name': 'Customer Tier',
                        'field': {'source_id': 'customers', 'field': 'tier'},
                        'relationship_type': 'changing',
                    },
                    {
                        'id': 'customer_country',
                        'name': 'Founding Country',
                        'field': {
                            'source_id': 'customers', 'field': 'country',
                        },
                        'relationship_type': 'fixed',
                    },
                ),
                hierarchies=({
                    'id': 'customer_geo',
                    'name': 'Customer Geography',
                    'levels': [
                        {
                            'id': 'geo_country',
                            'name': 'Country',
                            'field': {
                                'source_id': 'customers', 'field': 'country',
                            },
                            'relationship_type': 'fixed',
                        },
                        {
                            'id': 'geo_customer',
                            'name': 'Customer Name',
                            'field': {
                                'source_id': 'customers',
                                'field': 'customer_name',
                            },
                            'relationship_type': 'changing',
                        },
                    ],
                },),
            ).to_dict(),
            CubeDimension(
                id='order_date',
                name='Order Date',
                field={'source_id': 'calendar', 'field': 'date_key'},
                is_time=True,
                time_role='event-time',
                join_id='orders_calendar',
                unknown_member_policy='hide',
                unknown_member_caption='Missing Date',
                hierarchies=({
                    'id': 'cal_ymd',
                    'name': 'Calendar Y-Q-M',
                    'levels': [
                        {
                            'id': 'cal_year',
                            'name': 'Year',
                            'field': {
                                'source_id': 'calendar', 'field': 'cal_year',
                            },
                            'relationship_type': 'fixed',
                        },
                        {
                            'id': 'cal_quarter',
                            'name': 'Quarter',
                            'field': {
                                'source_id': 'calendar',
                                'field': 'cal_quarter',
                            },
                            'relationship_type': 'fixed',
                        },
                        {
                            'id': 'cal_month',
                            'name': 'Month',
                            'field': {
                                'source_id': 'calendar', 'field': 'cal_month',
                            },
                            'relationship_type': 'fixed',
                        },
                    ],
                },),
            ).to_dict(),
        ],
        'measures': [
            CubeMeasure(
                id='gross_revenue',
                name='Gross Revenue',
                aggregation='sum',
                field={'source_id': 'orders', 'field': 'amount'},
                format='$#,##0.00',
                measure_group_id='mg_orders',
            ).to_dict(),
            CubeMeasure(
                id='margin_secret',
                name='Executive Net Margin',
                aggregation='sum',
                field={'source_id': 'orders', 'field': 'margin'},
                format='$#,##0.00',
                measure_group_id='mg_orders',
                visible_roles=('finance_exec',),
            ).to_dict(),
        ],
        'measure_groups': [{
            'id': 'mg_orders',
            'name': 'Orders Measure Group',
            'fact_source': 'orders',
            'measures': ['gross_revenue', 'margin_secret'],
            'dimension_usage': [
                {
                    'dimension_id': 'customer',
                    'relationship_kind': 'regular',
                    'active': True,
                    'join_id': 'orders_customer',
                },
                {
                    'dimension_id': 'order_date',
                    'relationship_kind': 'regular',
                    'active': True,
                    'join_id': 'orders_calendar',
                },
            ],
        }],
        'materializations': [
            CubeAggregationPlan(
                id='agg_monthly_customer',
                name='Monthly Customer Summary',
                strategy='aggregate_table',
                enabled=True,
                measure_group_id='mg_orders',
                grain_dimensions=('customer', 'cal_month'),
                measures=('gross_revenue',),
                target_relation=('agg_monthly_customer',),
                partition_field={
                    'source_id': 'orders', 'field': 'order_date',
                },
                partition_grain='month',
                refresh_policy='incremental',
                rule_group={
                    'mandatory_dimensions': ['customer'],
                    'hierarchy_sets': [['cal_year', 'cal_quarter', 'cal_month']],
                    'max_dimension_combinations': 3,
                },
            ).to_dict(),
        ],
        'perspectives': [
            CubePerspective(
                id='finance_perspective',
                name='Finance Executive View',
                description='Executive P&L perspective without subtitle errors',
                dimensions=('customer', 'order_date'),
                measures=('gross_revenue', 'margin_secret'),
                default_measure='gross_revenue',
                visible_roles=('finance_exec',),
            ).to_dict(),
        ],
        'translations': [{
            'id': 'loc_fr_ca',
            'locale': 'fr-CA',
            'caption': 'Cube des revenus',
            'entries': [
                {
                    'target_kind': 'dimension',
                    'target_id': 'customer',
                    'caption': 'Client',
                },
                {
                    'target_kind': 'measure',
                    'target_id': 'gross_revenue',
                    'caption': 'Revenu brut',
                },
            ],
        }],
    }


class CubeDDNAndExtensionsTests(unittest.TestCase):
    def test_ddn_verifier_zero_diagnostics_with_descriptions_and_agg_grid(
        self,
    ):
        """Bugs 1 & 2: zero subtitle errors and zero table.records missing cols."""
        cube = public_model(validate_model(_sample_phase1_cube()))
        ddn_populated, id_map = semantic_model_to_ddn(cube)
        self.assertNotIn('\n        subtitle ', ddn_populated)
        self.assertIn('// @cube.description:', ddn_populated)
        self.assertIn(
            '// @cube.perspective_description finance_perspective:',
            ddn_populated,
        )

        ddn_empty, _ = semantic_model_to_ddn(default_cube_model('Blank Cube'))

        verified = _verify_ddn_documents({
            'populated': ddn_populated,
            'empty': ddn_empty,
        })
        for key in ('populated', 'empty'):
            self.assertEqual(
                verified[key]['outcome'],
                'valid',
                f"{key} DDN diagnostics: {verified[key]['diagnostics']}",
            )
            self.assertTrue(verified[key]['complete'])
            self.assertEqual(verified[key]['diagnostics'], [])

        roundtripped = ddn_to_semantic_model(ddn_populated)
        self.assertEqual(roundtripped['model'], cube)
        self.assertEqual(roundtripped['element_ids'], id_map)
        self.assertEqual(
            ddn_to_semantic_model(ddn_empty)['model']['materializations'], []
        )

        # Direct DDN text edit of @cube.description round-trips cleanly.
        edited_ddn = ddn_populated.replace(
            json.dumps(cube['description']),
            json.dumps('Updated directly in DDN comment'),
            1,
        )
        self.assertEqual(
            ddn_to_semantic_model(edited_ddn)['model']['description'],
            'Updated directly in DDN comment',
        )

    def test_unknown_member_policy_relationship_type_and_role_visibility(self):
        """Phase 1 compiler: COALESCE unknown member, INNER JOIN hide, roles."""
        cube = validate_model(_sample_phase1_cube())
        sqlite_dialect = {
            'contract_complete': True,
            'language_profile': 'sqlite',
            'quote_open': '"',
            'quote_close': '"',
            'supports_rollup': False,
            'limit_style': 'limit',
            'true_literal': '1',
            'false_literal': '0',
            'time_operations': ['as_of', 'range'],
            'window_operations': ['running_sum'],
        }
        duck_dialect = {
            **sqlite_dialect,
            'language_profile': 'duckdb',
            'supports_rollup': True,
            'true_literal': 'TRUE',
            'false_literal': 'FALSE',
        }
        query = {
            'axes': {'rows': ['customer'], 'columns': [], 'pages': []},
            'measures': ['gross_revenue'],
            'filters': [],
            'totals': False,
            'limit': 50,
        }

        compiled_sq = compile_sql(
            cube, query, sqlite_dialect, role='analyst'
        )
        self.assertIn(
            'COALESCE("customers"."customer_name", \'Unassigned Customer\')',
            compiled_sq['source'],
        )
        # order_date has unknown_member_policy='hide', forcing INNER JOIN on calendar
        self.assertIn('INNER JOIN "calendar"', compiled_sq['source'])
        self.assertIn('LEFT JOIN "customers"', compiled_sq['source'])

        setup_sql = [
            'CREATE TABLE customers ('
            'customer_id INT, customer_name TEXT, tier TEXT, country TEXT)',
            'CREATE TABLE calendar ('
            'date_key TEXT, cal_year TEXT, cal_quarter TEXT, cal_month TEXT)',
            'CREATE TABLE orders ('
            'order_id INT, customer_id INT, order_date TEXT, '
            'amount REAL, margin REAL)',
            "INSERT INTO customers VALUES (1, 'Acme Corp', 'Gold', 'CA')",
            "INSERT INTO calendar VALUES ('2026-11-01', '2026', '2026-Q4', '2026-11')",
            # Order 10: valid customer & valid date -> included under 'Acme Corp'
            # Order 11: orphan customer 999 & valid date -> included under 'Unassigned Customer'
            # Order 12: valid customer 1 & orphan date '1999-01-01' -> hidden by INNER JOIN!
            "INSERT INTO orders VALUES "
            "(10, 1, '2026-11-01', 100.0, 40.0), "
            "(11, 999, '2026-11-01', 55.0, 20.0), "
            "(12, 1, '1999-01-01', 999.0, 500.0)",
        ]
        with sqlite3.connect(':memory:') as sconn:
            for stmt in setup_sql:
                sconn.execute(stmt)
            sq_rows = sorted(
                sconn.execute(compiled_sq['source']).fetchall()
            )
        self.assertEqual(
            sq_rows,
            [('Acme Corp', 100.0), ('Unassigned Customer', 55.0)],
        )

        compiled_dk = compile_sql(cube, query, duck_dialect, role='analyst')
        dconn = duckdb.connect(':memory:')
        try:
            for stmt in setup_sql:
                dconn.execute(stmt)
            dk_rows = sorted(dconn.execute(compiled_dk['source']).fetchall())
        finally:
            dconn.close()
        self.assertEqual(dk_rows, sq_rows)

        # Role visibility blocks analyst from querying finance_exec-only measure
        with self.assertRaisesRegex(SemanticModelError, 'not visible to role'):
            compile_sql(
                cube,
                {**query, 'measures': ['margin_secret']},
                sqlite_dialect,
                role='analyst',
            )
        # finance_exec can query margin_secret
        exec_sql = compile_sql(
            cube,
            {**query, 'measures': ['margin_secret']},
            sqlite_dialect,
            role='finance_exec',
        )
        self.assertIn('"margin"', exec_sql['source'])

        filtered_for_analyst = filter_model_for_role(cube, 'analyst')
        self.assertEqual(
            [m['id'] for m in filtered_for_analyst['measures']],
            ['gross_revenue'],
        )
        self.assertEqual(filtered_for_analyst['perspectives'], [])

        # visible_roles rejects user emails / non-identifier grants per AGENTS.md
        bad_cube = copy.deepcopy(_sample_phase1_cube())
        bad_cube['measures'][0]['visible_roles'] = ['alice@example.com']
        with self.assertRaisesRegex(
            SemanticModelError, 'portable identifier'
        ):
            validate_model(bad_cube)

        # Partition DDL & destructive rebuild warning in materialization plan
        plan = preview_cube_materialization_plan(
            None, cube, target_engine='postgresql'
        )
        self.assertIn('PARTITION BY RANGE', plan['sql_preview'])
        self.assertIn('Refresh policy: incremental', plan['sql_preview'])
        dropped_plan = preview_cube_materialization_plan(
            cube, {**cube, 'materializations': []}, target_engine='postgresql'
        )
        self.assertIn('agg_monthly_customer', dropped_plan['destructive_warning'])

    def test_extensions_and_http_routes_end_to_end(self):
        """Test all 4 cube_extensions entry points directly and via Flask API."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = f'{tmp}/designs.db'
            sample_sqlite = f'{tmp}/warehouse.sqlite'
            with sqlite3.connect(sample_sqlite) as wh:
                wh.execute(
                    'CREATE TABLE customers ('
                    'customer_id INT, customer_name TEXT, tier TEXT, country TEXT)'
                )
                wh.execute(
                    'CREATE TABLE calendar ('
                    'date_key TEXT, cal_year TEXT, cal_quarter TEXT, cal_month TEXT)'
                )
                wh.execute(
                    'CREATE TABLE orders ('
                    'order_id INT, customer_id INT, order_date TEXT, '
                    'amount REAL, margin REAL)'
                )
                # Intentional duplicate key on customers (id=1 twice) to trigger fanout_risk!
                wh.execute(
                    "INSERT INTO customers VALUES "
                    "(1, 'Acme', 'Gold', 'CA'), "
                    "(1, 'Acme Dup', 'Silver', 'CA'), "
                    "(2, 'Beta', 'Bronze', 'US')"
                )
                wh.execute(
                    "INSERT INTO calendar VALUES "
                    "('2026-11-01', '2026', '2026-Q4', '2026-11')"
                )
                wh.execute(
                    "INSERT INTO orders VALUES "
                    "(100, 1, '2026-11-01', 250.0, 90.0), "
                    "(101, 2, '2026-11-01', 125.0, 45.0)"
                )

            app = Flask(__name__)
            app.secret_key = 'test-cube-phase1'
            app.config['TESTING'] = True
            app.config['LOGIN_DISABLED'] = True
            app.config['CDEADMIN_DESIGN_STORE_PATH'] = db_path
            sem_svc = SemanticModelService(repository=_MemorySemanticRepo())
            app.extensions[SEMANTIC_SERVICE_EXTENSION_KEY] = sem_svc
            init_routes_app(app)
            client = app.test_client()

            create_resp = client.post(
                '/cdeadmin/api/projects/p1/designs',
                json={
                    'mode': 'create_cube',
                    'key': 'fulfillment-cube',
                    'title': 'Fulfillment Revenue Cube',
                    'model': _sample_phase1_cube(),
                },
            )
            self.assertEqual(create_resp.status_code, 200)
            design_id = create_resp.get_json()['data']['id']

            # 1. Check against connection: fanout_risk on duplicate customer PK
            chk_resp = client.post(
                f'/cdeadmin/api/projects/p1/designs/{design_id}'
                '/cube/check-connection',
                json={'sqlite_path': sample_sqlite},
            )
            self.assertEqual(chk_resp.status_code, 200)
            chk_data = chk_resp.get_json()['data']
            self.assertEqual(chk_data['overall_status'], 'fanout_risk')
            by_dim = {d['dimension_id']: d for d in chk_data['dimensions']}
            self.assertEqual(by_dim['customer']['status'], 'fanout_risk')
            self.assertEqual(by_dim['customer']['duplicate_keys'], 1)
            self.assertGreater(by_dim['customer']['fanout_ratio'], 1.0)
            self.assertEqual(by_dim['order_date']['status'], 'valid')

            # Clean sample_rows harness -> overall_status == 'valid'
            clean_resp = client.post(
                f'/cdeadmin/api/projects/p1/designs/{design_id}'
                '/cube/check-connection',
                json={
                    'sample_rows': {
                        'customers': [
                            {'customer_id': 1, 'customer_name': 'Acme'},
                            {'customer_id': 2, 'customer_name': 'Beta'},
                        ],
                        'calendar': [{'date_key': '2026-11-01'}],
                        'orders': [
                            {
                                'order_id': 10,
                                'customer_id': 1,
                                'order_date': '2026-11-01',
                                'amount': 50.0,
                            },
                        ],
                    },
                },
            )
            self.assertEqual(clean_resp.status_code, 200)
            self.assertEqual(
                clean_resp.get_json()['data']['overall_status'], 'valid'
            )

            # 2. Combinatorial rule-group reducer: D=4 -> 16 -> 8 -> 5
            red_resp = client.post(
                f'/cdeadmin/api/projects/p1/designs/{design_id}'
                '/cube/reduce-aggregations',
                json={
                    'candidate_dimensions': [
                        'customer', 'cal_year', 'cal_quarter', 'cal_month',
                    ],
                    'mandatory_dimensions': ['customer'],
                    'hierarchy_sets': [['cal_year', 'cal_quarter']],
                    'joint_sets': [],
                    'max_dimension_combinations': 3,
                    'measures': ['gross_revenue'],
                    'partition_field': {
                        'source_id': 'orders', 'field': 'order_date',
                    },
                    'partition_grain': 'month',
                    'refresh_policy': 'incremental',
                    'save_version': True,
                },
            )
            self.assertEqual(red_resp.status_code, 200)
            red_data = red_resp.get_json()['data']
            self.assertEqual(red_data['naive_cuboid_count'], 16)
            self.assertEqual(red_data['after_mandatory_and_joint_count'], 8)
            self.assertEqual(red_data['final_cuboid_count'], 5)
            self.assertEqual(red_data['reduction_summary'], '16 -> 8 -> 5')
            self.assertEqual(len(red_data['generated_plans']), 5)
            self.assertEqual(red_data['design']['head_version'], 2)

            # Verify saved v2 DDN still has 0 verifier diagnostics!
            v2_ver = _verify_ddn_documents({
                'v2': red_data['design']['version']['ddn_text'],
            })
            self.assertEqual(v2_ver['v2']['outcome'], 'valid')
            self.assertEqual(v2_ver['v2']['diagnostics'], [])

            # 3. Try a Query: SQL compilation, routing hit, locale & execution
            try_resp = client.post(
                f'/cdeadmin/api/projects/p1/designs/{design_id}/cube/try-query',
                json={
                    'dimensions': ['customer'],
                    'measures': ['gross_revenue'],
                    'role': 'analyst',
                    'locale': 'fr-CA',
                    'dialect': 'sqlite',
                    'sample_rows': {
                        'customers': [
                            {'customer_id': 1, 'customer_name': 'Acme'},
                        ],
                        'calendar': [{'date_key': '2026-11-01'}],
                        'orders': [
                            {
                                'order_id': 1,
                                'customer_id': 1,
                                'order_date': '2026-11-01',
                                'amount': 320.5,
                            },
                        ],
                    },
                },
            )
            self.assertEqual(try_resp.status_code, 200)
            try_data = try_resp.get_json()['data']
            self.assertTrue(try_data['executed'])
            self.assertTrue(try_data['aggregate_routing_hit']['matched'])
            self.assertEqual(
                [c['label'] for c in try_data['columns']],
                ['Client', 'Revenu brut'],
            )
            self.assertEqual(
                try_data['preview_rows'],
                [{'customer': 'Acme', 'gross_revenue': 320.5}],
            )

            # 4. BYOK AI Draft: searches existing cubes first, Draft-only
            ai_resp = client.post(
                '/cdeadmin/api/projects/p1/cube/ai-draft',
                json={
                    'prompt': 'Analyze customer order fulfillment revenue',
                    'fact_table': 'public.orders',
                    'columns': [
                        {'name': 'order_id', 'type': 'integer'},
                        {'name': 'customer_id', 'type': 'integer'},
                        {'name': 'order_date', 'type': 'date'},
                        {'name': 'channel', 'type': 'text'},
                        {'name': 'revenue', 'type': 'numeric'},
                    ],
                    'api_key': 'sk-ephemeral-never-persisted',
                },
            )
            self.assertEqual(ai_resp.status_code, 200)
            ai_data = ai_resp.get_json()['data']
            self.assertTrue(ai_data['requires_human_review'])
            self.assertFalse(ai_data['auto_accepted'])
            self.assertFalse(ai_data['published'])
            self.assertEqual(ai_data['status'], 'draft')
            self.assertGreaterEqual(len(ai_data['matched_existing_cubes']), 1)
            self.assertEqual(
                ai_data['matched_existing_cubes'][0]['design_id'], design_id
            )
            self.assertNotIn(
                'sk-ephemeral-never-persisted', ai_data['proposed_ddn_text']
            )
            ai_ver = _verify_ddn_documents({
                'ai_draft': ai_data['proposed_ddn_text'],
            })
            self.assertEqual(ai_ver['ai_draft']['outcome'], 'valid')
            self.assertEqual(ai_ver['ai_draft']['diagnostics'], [])


if __name__ == '__main__':
    unittest.main()
