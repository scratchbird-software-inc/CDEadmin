##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Regression tests for the DDN Cube Designer, Store <-> DDN roundtrip,
filtered measure SQL execution, 3-way active drift merge, Git DDN sync,
and native-review materialization plans.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

import duckdb
from flask import Flask

from pgadmin.cdeadmin.design_store import (
    AGGREGATION_GRID_PROFILE,
    CUBE_PROFILE,
    USAGE_MATRIX_PROFILE,
    CubeDesignSync,
    DesignStore,
    DesignStoreConflict,
    ddn_to_semantic_model,
    diff_cube_ddn,
    export_cube_to_ossie,
    export_cube_to_sml,
    init_routes_app,
    inspect_ddn_text,
    is_uuid7,
    preview_cube_materialization_plan,
    semantic_model_to_ddn,
)
from pgadmin.cdeadmin.design_store.routes import SEMANTIC_SERVICE_EXTENSION_KEY
from pgadmin.cdeadmin.semantic_models import (
    SemanticModelError,
    SemanticModelService,
    localize_model,
    public_model,
    validate_model,
    validate_query,
)
from pgadmin.cdeadmin.semantic_models.compiler import compile_sql


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


def _sample_c3_cube() -> dict:
    return {
        'name': 'Order Fulfillment Cube',
        'description': 'C3 dimensional cube with role-playing and filters',
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
                'join_type': 'inner',
                'cardinality': 'many-to-one',
                'active': True,
                'predicates': [{
                    'left': {'source_id': 'orders', 'field': 'customer_id'},
                    'right': {
                        'source_id': 'customers', 'field': 'customer_id',
                    },
                    'operator': 'eq',
                }],
            },
            {
                'id': 'orders_order_date',
                'left_source': 'orders',
                'right_source': 'calendar',
                'join_type': 'inner',
                'cardinality': 'many-to-one',
                'active': True,
                'predicates': [{
                    'left': {'source_id': 'orders', 'field': 'order_date'},
                    'right': {'source_id': 'calendar', 'field': 'date_key'},
                    'operator': 'eq',
                }],
            },
            {
                'id': 'orders_ship_date',
                'left_source': 'orders',
                'right_source': 'calendar',
                'join_type': 'left',
                'cardinality': 'many-to-one',
                'active': False,
                'predicates': [{
                    'left': {'source_id': 'orders', 'field': 'ship_date'},
                    'right': {'source_id': 'calendar', 'field': 'date_key'},
                    'operator': 'eq',
                }],
            },
        ],
        'dimensions': [
            {
                'id': 'customer',
                'name': 'Customer',
                'field': {'source_id': 'customers', 'field': 'customer_id'},
                'key_field': {
                    'source_id': 'customers', 'field': 'customer_id',
                },
                'name_field': {
                    'source_id': 'customers', 'field': 'customer_name',
                },
                'sort_field': {
                    'source_id': 'customers', 'field': 'customer_name',
                },
                'attributes': [
                    {
                        'id': 'customer_segment',
                        'name': 'Segment',
                        'field': {
                            'source_id': 'customers', 'field': 'segment',
                        },
                    },
                ],
                'hierarchies': [{
                    'id': 'cust_geo',
                    'name': 'Customer Geography',
                    'levels': [{
                        'id': 'cust_region',
                        'name': 'Region',
                        'field': {
                            'source_id': 'customers', 'field': 'region',
                        },
                    }],
                }],
            },
            {
                'id': 'order_date',
                'name': 'Order Date',
                'field': {'source_id': 'calendar', 'field': 'date_key'},
                'join_id': 'orders_order_date',
                'active': True,
            },
            {
                'id': 'ship_date',
                'name': 'Ship Date',
                'field': {'source_id': 'calendar', 'field': 'date_key'},
                'role_of': 'order_date',
                'join_id': 'orders_ship_date',
                'active': False,
            },
        ],
        'measures': [
            {
                'id': 'gross_sales',
                'name': 'Gross Sales',
                'aggregation': 'sum',
                'field': {'source_id': 'orders', 'field': 'amount'},
                'format': '$0.00',
                'measure_group_id': 'mg_orders',
                'certification': {
                    'status': 'certified',
                    'owner': 'Analytics',
                    'definition': 'Total order amount',
                },
            },
            {
                'id': 'priority_sales',
                'name': 'Priority Sales',
                'aggregation': 'sum',
                'field': {'source_id': 'orders', 'field': 'amount'},
                'format': '$0.00',
                'measure_group_id': 'mg_orders',
                'filters': [{
                    'field': {'source_id': 'orders', 'field': 'status'},
                    'operator': 'eq',
                    'value': 'PRIORITY',
                }],
            },
            {
                'id': 'priority_orders',
                'name': 'Priority Order Count',
                'aggregation': 'count',
                'field': None,
                'measure_group_id': 'mg_orders',
                'filters': [{
                    'field': {'source_id': 'orders', 'field': 'status'},
                    'operator': 'eq',
                    'value': 'PRIORITY',
                }],
            },
        ],
        'measure_groups': [{
            'id': 'mg_orders',
            'name': 'Orders Fact Group',
            'fact_source': 'orders',
            'measures': ['gross_sales', 'priority_sales', 'priority_orders'],
            'dimension_usage': [
                {
                    'dimension_id': 'customer',
                    'relationship_kind': 'regular',
                    'granularity_field': {
                        'source_id': 'orders', 'field': 'customer_id',
                    },
                    'join_id': 'orders_customer',
                    'active': True,
                },
                {
                    'dimension_id': 'order_date',
                    'relationship_kind': 'regular',
                    'join_id': 'orders_order_date',
                    'active': True,
                },
                {
                    'dimension_id': 'ship_date',
                    'relationship_kind': 'regular',
                    'join_id': 'orders_ship_date',
                    'active': False,
                },
            ],
        }],
        'parameters': [{
            'id': 'min_amount',
            'name': 'Minimum Amount',
            'type': 'number',
            'default': 0,
        }],
        'default_filters': [],
        'materializations': [{
            'id': 'agg_segment_sales',
            'name': 'Segment Sales Rollup',
            'strategy': 'materialized_view',
            'enabled': True,
            'measure_group_id': 'mg_orders',
            'grain_dimensions': ['customer_segment'],
            'measures': ['gross_sales', 'priority_sales'],
            'target_relation': ['agg_segment_sales'],
            'refresh_policy': 'on_accept_review',
        }],
        'security': {'row_filters': [], 'tenant_filter': None, 'roles': []},
        'annotations': {'domain': 'fulfillment'},
    }


class CubeDesignerTests(unittest.TestCase):
    def test_lossless_ddn_roundtrip_and_three_ddn_views(self):
        original = public_model(validate_model(_sample_c3_cube()))
        ddn_text, id_map = semantic_model_to_ddn(
            original,
            cube_notes=['Reviewed grain with finance', 'Ship date inactive'],
        )
        self.assertTrue(all(is_uuid7(v) for v in id_map.values()))

        info = inspect_ddn_text(ddn_text)
        views = {(v['id'], v['profile']) for v in info['views']}
        self.assertIn(('cube_star', CUBE_PROFILE), views)
        self.assertIn(('cube_usage_matrix', USAGE_MATRIX_PROFILE), views)
        self.assertIn(
            ('cube_aggregation_grid', AGGREGATION_GRID_PROFILE), views
        )

        parsed = ddn_to_semantic_model(ddn_text)
        self.assertEqual(
            parsed['notes'],
            ['Reviewed grain with finance', 'Ship date inactive'],
        )
        expected = copy.deepcopy(original)
        expected['annotations']['ddn_notes'] = [
            'Reviewed grain with finance', 'Ship date inactive',
        ]
        self.assertEqual(parsed['model'], expected)

        # Second roundtrip keeps the exact same UUIDv7 element IDs.
        ddn_text_2, id_map_2 = semantic_model_to_ddn(
            parsed['model'], element_ids=parsed['element_ids']
        )
        self.assertEqual(id_map, id_map_2)
        self.assertEqual(ddn_to_semantic_model(ddn_text_2)['model'], expected)

    def test_live_sqlite_and_duckdb_filtered_measures_and_attributes(self):
        cube = validate_model(_sample_c3_cube())
        query = {
            'axes': {
                'rows': ['customer_segment'], 'columns': [], 'pages': [],
            },
            'measures': ['gross_sales', 'priority_sales', 'priority_orders'],
            'filters': [],
            'totals': False,
            'limit': 50,
        }
        setup_sql = [
            'CREATE TABLE customers ('
            'customer_id INT, customer_name TEXT, segment TEXT, region TEXT)',
            'CREATE TABLE calendar (date_key TEXT)',
            'CREATE TABLE orders ('
            'order_id INT, customer_id INT, order_date TEXT, '
            'ship_date TEXT, status TEXT, amount REAL)',
            "INSERT INTO customers VALUES "
            "(1, 'Acme', 'Enterprise', 'NA'), "
            "(2, 'Beta', 'SMB', 'EU')",
            "INSERT INTO calendar VALUES ('2026-11-01'), ('2026-11-02')",
            "INSERT INTO orders VALUES "
            "(10, 1, '2026-11-01', '2026-11-02', 'PRIORITY', 120.0), "
            "(11, 1, '2026-11-01', '2026-11-02', 'STANDARD', 80.0), "
            "(12, 2, '2026-11-02', '2026-11-02', 'PRIORITY', 50.0)",
        ]

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
        compiled_sqlite = compile_sql(cube, query, sqlite_dialect)
        with sqlite3.connect(':memory:') as sconn:
            for stmt in setup_sql:
                sconn.execute(stmt)
            rows = sconn.execute(compiled_sqlite['source']).fetchall()
        self.assertEqual(
            rows,
            [('Enterprise', 200.0, 120.0, 1), ('SMB', 50.0, 50.0, 1)],
        )

        duck_dialect = {
            **sqlite_dialect,
            'language_profile': 'duckdb',
            'supports_rollup': True,
            'true_literal': 'TRUE',
            'false_literal': 'FALSE',
        }
        compiled_duck = compile_sql(cube, query, duck_dialect)
        dconn = duckdb.connect(':memory:')
        try:
            for stmt in setup_sql:
                dconn.execute(stmt)
            drows = dconn.execute(compiled_duck['source']).fetchall()
        finally:
            dconn.close()
        self.assertEqual(
            drows,
            [('Enterprise', 200.0, 120.0, 1), ('SMB', 50.0, 50.0, 1)],
        )

    def test_accept_applies_to_store_and_detects_active_drift_and_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DesignStore(f'{tmp}/designs.db')
            sem_repo = _MemorySemanticRepo()
            sem_svc = SemanticModelService(repository=sem_repo)
            sync = CubeDesignSync(store, semantic_service=sem_svc)

            created = sync.create_cube(
                project_id='proj-cube',
                key='fulfillment-cube',
                title='Order Fulfillment Cube',
                actor_id=7,
                model=_sample_c3_cube(),
                endpoint_id='ep-1',
            )
            design_id = created['design']['id']
            # Draft does NOT touch the semantic-model store.
            self.assertEqual(sem_svc.list(7, 'ep-1'), [])

            store.advance_status(design_id, 1, 'in_review', actor_id=7)
            self.assertEqual(sem_svc.list(7, 'ep-1'), [])

            # Accepting v1 applies it to SemanticModelService and returns a
            # native-review materialization plan without direct DB execution.
            accepted = sync.accept_cube(
                design_id,
                1,
                actor_id=7,
                endpoint_id='ep-1',
                target_engine='duckdb',
            )
            self.assertEqual(accepted['design']['active_version'], 1)
            self.assertEqual(
                accepted['applied_semantic_model']['status'], 'published'
            )
            self.assertEqual(len(sem_svc.list(7, 'ep-1')), 1)
            plan = accepted['materialization_review_plan']
            self.assertTrue(plan['has_database_changes'])
            self.assertTrue(plan['requires_native_review'])
            self.assertFalse(plan['applied_immediately'])
            self.assertIn(
                'CREATE MATERIALIZED VIEW "agg_segment_sales"',
                plan['sql_preview'],
            )

            # Branch v2 minor-bump draft (1.0 -> 1.1) from v1.
            branched = sync.leave_accepted(
                design_id, mode='branch_minor_draft', actor_id=7
            )
            self.assertEqual(branched['cube_version_label'], '1.1')
            self.assertEqual(branched['design']['head_version'], 2)

            # Simulate someone else accepting v2 with a new parameter, while
            # another draft v3 branched from v1 edits description.
            v2_model = copy.deepcopy(branched['cube']['model'])
            v2_model['parameters'].append({
                'id': 'currency', 'name': 'Currency',
                'type': 'string', 'default': 'CAD',
            })
            sync.save_cube_model(
                design_id,
                expected_head_version=2,
                actor_id=7,
                model=v2_model,
                status='in_review',
            )
            sync.accept_cube(design_id, 3, actor_id=7, endpoint_id='ep-1')

            # Create v4 draft with base_version=1 (stale base vs active=3).
            stale_model = copy.deepcopy(created['cube']['model'])
            stale_model['description'] = 'Draft edited while v3 was accepted'
            stale_ddn, _ = semantic_model_to_ddn(
                stale_model, element_ids=created['cube']['element_ids']
            )
            store.save_version(
                design_id,
                expected_head_version=3,
                ddn_text=stale_ddn,
                actor_id=7,
                base_version=1,
                status='in_review',
                allow_conflict_note=True,
            )
            with self.assertRaises(DesignStoreConflict):
                sync.accept_cube(design_id, 4, actor_id=7, endpoint_id='ep-1')

            # Sync active v3 into draft -> clean 3-way merge creating v5.
            merged = sync.sync_draft_with_active(design_id, actor_id=7)
            self.assertTrue(merged['merged'])
            self.assertEqual(
                merged['cube']['model']['description'],
                'Draft edited while v3 was accepted',
            )
            param_ids = [
                p['id'] for p in merged['cube']['model']['parameters']
            ]
            self.assertIn('currency', param_ids)

            # Git save and load keep DDN text (not runtime store rows).
            git_dir = f'{tmp}/git-repo'
            subprocess.run(
                ['git', 'init', git_dir], check=True, capture_output=True
            )
            store.link_git(
                design_id, repository=git_dir, path='cubes/fulfillment.ddn'
            )
            exported = store.export_to_git(design_id, git_dir, commit=True)
            self.assertEqual(exported['sync_state'], 'synced')
            loaded = store.import_from_git(design_id, git_dir, actor_id=7)
            self.assertEqual(loaded['head_version'], 6)

    def test_cube_http_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Flask(__name__)
            app.secret_key = 'test-cube-secret'
            app.config['TESTING'] = True
            app.config['LOGIN_DISABLED'] = True
            app.config['CDEADMIN_DESIGN_STORE_PATH'] = f'{tmp}/designs.db'
            sem_svc = SemanticModelService(repository=_MemorySemanticRepo())
            app.extensions[SEMANTIC_SERVICE_EXTENSION_KEY] = sem_svc
            init_routes_app(app)

            client = app.test_client()
            resp = client.post(
                '/cdeadmin/api/projects/p1/designs',
                json={
                    'mode': 'create_cube',
                    'key': 'sales-cube',
                    'title': 'Sales Cube',
                    'model': _sample_c3_cube(),
                    'endpoint_id': 'ep-http',
                },
            )
            self.assertEqual(resp.status_code, 200)
            design_id = resp.get_json()['data']['id']

            get_resp = client.get(
                f'/cdeadmin/api/projects/p1/designs/{design_id}/cube/model'
            )
            self.assertEqual(get_resp.status_code, 200)
            cube_data = get_resp.get_json()['data']['cube']['model']
            self.assertEqual(len(cube_data['dimensions']), 3)

            plan_resp = client.post(
                f'/cdeadmin/api/projects/p1/designs/{design_id}'
                '/cube/materialization-plan',
                json={'target_engine': 'postgresql'},
            )
            self.assertEqual(plan_resp.status_code, 200)
            self.assertTrue(
                plan_resp.get_json()['data']['requires_native_review']
            )

    def test_parent_child_recursive_hierarchy_execution_and_ddn(self):
        pc_raw = {
            'contract_version': '1.0.0',
            'name': 'Org Quota Cube',
            'semantic_family': 'relational',
            'sources': [
                {
                    'id': 'quotas',
                    'resource_id': 'table:main:quotas',
                    'kind': 'table',
                    'classification': 'fact',
                    'relation': ['quotas'],
                    'grain': [{'source_id': 'quotas', 'field': 'quota_id'}],
                },
                {
                    'id': 'reps',
                    'resource_id': 'table:main:reps',
                    'kind': 'table',
                    'classification': 'dimension',
                    'relation': ['reps'],
                    'grain': [{'source_id': 'reps', 'field': 'rep_id'}],
                },
            ],
            'joins': [{
                'id': 'quotas_reps',
                'left_source': 'quotas',
                'right_source': 'reps',
                'join_type': 'inner',
                'cardinality': 'many-to-one',
                'active': True,
                'predicates': [{
                    'left': {'source_id': 'quotas', 'field': 'rep_id'},
                    'operator': 'eq',
                    'right': {'source_id': 'reps', 'field': 'rep_id'},
                }],
            }],
            'dimensions': [{
                'id': 'org_rep',
                'name': 'Org Representative',
                'type': 'categorical',
                'field': {'source_id': 'reps', 'field': 'rep_id'},
                'key_field': {'source_id': 'reps', 'field': 'rep_id'},
                'name_field': {'source_id': 'reps', 'field': 'rep_name'},
                'hierarchies': [{
                    'id': 'reporting_line',
                    'name': 'Reporting Line',
                    'hierarchy_kind': 'parent_child',
                    'child_field': {'source_id': 'reps', 'field': 'rep_id'},
                    'parent_field': {
                        'source_id': 'reps', 'field': 'manager_id'
                    },
                    'name_field': {'source_id': 'reps', 'field': 'rep_name'},
                    'max_depth': 6,
                    'ragged': True,
                }],
            }],
            'measures': [{
                'id': 'total_quota',
                'name': 'Total Quota',
                'aggregation': 'sum',
                'field': {'source_id': 'quotas', 'field': 'amount'},
            }],
        }
        cube = validate_model(pc_raw)
        ddn_text, _ = semantic_model_to_ddn(cube)
        roundtripped = ddn_to_semantic_model(ddn_text)['model']
        self.assertEqual(roundtripped['dimensions'], cube['dimensions'])

        query = validate_query(
            roundtripped,
            {
                'axes': {'rows': ['org_rep']},
                'measures': ['total_quota'],
                'order_by': [{'id': 'org_rep', 'direction': 'asc'}],
            },
        )
        setup_sql = [
            'CREATE TABLE reps ('
            'rep_id INTEGER, manager_id INTEGER, rep_name TEXT)',
            'CREATE TABLE quotas (quota_id INTEGER, rep_id INTEGER, '
            'amount DOUBLE PRECISION)',
            "INSERT INTO reps VALUES (1, NULL, 'CEO'), (2, 1, 'VP Sales'),"
            " (3, 2, 'Alice'), (4, 2, 'Bob'), (5, 1, 'Advisor')",
            'INSERT INTO quotas VALUES (10, 1, 100.0), (11, 2, 0.0),'
            ' (12, 3, 200.0), (13, 4, 50.0), (14, 5, 40.0)',
        ]
        from pgadmin.cdeadmin.design_store.cube_ddn import _PORTABLE_DIALECTS

        sqlite_dialect = _PORTABLE_DIALECTS['sqlite']
        compiled_sq = compile_sql(roundtripped, query, sqlite_dialect)
        self.assertTrue(
            compiled_sq['source'].lstrip().startswith('WITH RECURSIVE')
        )
        with sqlite3.connect(':memory:') as sconn:
            for stmt in setup_sql:
                sconn.execute(stmt)
            sq_rows = sconn.execute(compiled_sq['source']).fetchall()
        # CEO(1) = 100+0+200+50+40=390; VP(2) = 0+200+50=250;
        # Alice(3)=200; Bob(4)=50; Advisor(5)=40
        self.assertEqual(
            sq_rows,
            [(1, 390.0), (2, 250.0), (3, 200.0), (4, 50.0), (5, 40.0)],
        )

        duck_dialect = _PORTABLE_DIALECTS['duckdb']
        compiled_dk = compile_sql(roundtripped, query, duck_dialect)
        dconn = duckdb.connect(':memory:')
        try:
            for stmt in setup_sql:
                dconn.execute(stmt)
            dk_rows = dconn.execute(compiled_dk['source']).fetchall()
        finally:
            dconn.close()
        self.assertEqual(dk_rows, sq_rows)

    def test_semi_additive_measures_and_grain_warnings(self):
        inv_raw = {
            'contract_version': '1.0.0',
            'name': 'Warehouse Balances',
            'semantic_family': 'relational',
            'sources': [{
                'id': 'balances',
                'resource_id': 'table:main:balances',
                'kind': 'table',
                'classification': 'fact',
                'relation': ['balances'],
                'grain': [
                    {'source_id': 'balances', 'field': 'snap_date'},
                    {'source_id': 'balances', 'field': 'warehouse'},
                ],
            }],
            'dimensions': [
                {
                    'id': 'snap_date',
                    'name': 'Snapshot Date',
                    'type': 'time',
                    'field': {'source_id': 'balances', 'field': 'snap_date'},
                },
                {
                    'id': 'warehouse',
                    'name': 'Warehouse',
                    'type': 'categorical',
                    'field': {'source_id': 'balances', 'field': 'warehouse'},
                },
            ],
            'measures': [
                {
                    'id': 'units_moved',
                    'name': 'Units Moved',
                    'aggregation': 'sum',
                    'field': {'source_id': 'balances', 'field': 'moved'},
                },
                {
                    'id': 'closing_raw',
                    'name': 'Closing Raw',
                    'aggregation': 'last_value',
                    'semi_additive_dimension': 'snap_date',
                    'within_group_aggregation': 'sum',
                    'field': {'source_id': 'balances', 'field': 'on_hand'},
                },
                {
                    'id': 'closing_non_empty',
                    'name': 'Closing Non-Empty',
                    'aggregation': 'last_non_empty',
                    'semi_additive_dimension': 'snap_date',
                    'within_group_aggregation': 'sum',
                    'field': {'source_id': 'balances', 'field': 'on_hand'},
                },
                {
                    'id': 'opening_balance',
                    'name': 'Opening Balance',
                    'aggregation': 'first_non_empty',
                    'semi_additive_dimension': 'snap_date',
                    'within_group_aggregation': 'sum',
                    'field': {'source_id': 'balances', 'field': 'on_hand'},
                },
                {
                    'id': 'avg_daily_balance',
                    'name': 'Average Daily Balance',
                    'aggregation': 'avg_over_time',
                    'semi_additive_dimension': 'snap_date',
                    'within_group_aggregation': 'sum',
                    'field': {'source_id': 'balances', 'field': 'on_hand'},
                },
                {
                    'id': 'closing_vs_opening_delta',
                    'name': 'Closing vs Opening Delta',
                    'aggregation': 'none',
                    'expression': {
                        'operator': 'subtract',
                        'left': {'measure': 'closing_non_empty'},
                        'right': {'measure': 'opening_balance'},
                    },
                },
            ],
            'materializations': [{
                'id': 'bad_grain_agg',
                'name': 'Warehouse Only Rollup',
                'strategy': 'materialized_view',
                'enabled': True,
                'grain_dimensions': ['warehouse'],
                'measures': ['closing_non_empty'],
                'target_relation': ['agg_wh_bad'],
            }],
        }
        cube = validate_model(inv_raw)
        ddn_text, _ = semantic_model_to_ddn(cube)
        parsed = ddn_to_semantic_model(ddn_text)['model']
        self.assertEqual(parsed['measures'], cube['measures'])

        plan = preview_cube_materialization_plan(
            None, parsed, target_engine='postgresql'
        )
        self.assertGreaterEqual(len(plan['grain_warnings']), 1)
        self.assertIn('snap_date', plan['grain_warnings'][0])

        query = validate_query(
            parsed,
            {
                'axes': {'rows': ['warehouse']},
                'measures': [
                    'units_moved',
                    'closing_raw',
                    'closing_non_empty',
                    'opening_balance',
                    'avg_daily_balance',
                    'closing_vs_opening_delta',
                ],
                'order_by': [{'id': 'warehouse', 'direction': 'asc'}],
            },
        )
        setup_sql = [
            'CREATE TABLE balances ('
            'snap_date TEXT, warehouse TEXT, on_hand DOUBLE PRECISION, '
            'moved DOUBLE PRECISION)',
            "INSERT INTO balances VALUES "
            "('2026-01-01', 'East', 100.0, 10.0),"
            "('2026-01-02', 'East', 150.0, 20.0),"
            "('2026-01-03', 'East', 170.0, 5.0),"
            "('2026-01-01', 'West', 80.0, 8.0),"
            "('2026-01-02', 'West', 120.0, 12.0),"
            "('2026-01-03', 'West', NULL, 4.0)",
        ]
        from pgadmin.cdeadmin.design_store.cube_ddn import _PORTABLE_DIALECTS

        sqlite_dialect = _PORTABLE_DIALECTS['sqlite']
        compiled_sq = compile_sql(parsed, query, sqlite_dialect)
        with sqlite3.connect(':memory:') as sconn:
            for stmt in setup_sql:
                sconn.execute(stmt)
            sq_rows = sconn.execute(compiled_sq['source']).fetchall()
        # East: moved=35, closing_raw=170, closing_non_empty=170,
        #       opening=100, avg=(100+150+170)/3=140, delta=70
        # West: moved=24, closing_raw=None, closing_non_empty=120,
        #       opening=80, avg=(80+120)/2=100, delta=40
        self.assertEqual(len(sq_rows), 2)
        self.assertEqual(sq_rows[0][0], 'East')
        self.assertAlmostEqual(sq_rows[0][1], 35.0)
        self.assertAlmostEqual(sq_rows[0][2], 170.0)
        self.assertAlmostEqual(sq_rows[0][3], 170.0)
        self.assertAlmostEqual(sq_rows[0][4], 100.0)
        self.assertAlmostEqual(sq_rows[0][5], 140.0)
        self.assertAlmostEqual(sq_rows[0][6], 70.0)
        self.assertEqual(sq_rows[1][0], 'West')
        self.assertAlmostEqual(sq_rows[1][1], 24.0)
        self.assertIsNone(sq_rows[1][2])
        self.assertAlmostEqual(sq_rows[1][3], 120.0)
        self.assertAlmostEqual(sq_rows[1][4], 80.0)
        self.assertAlmostEqual(sq_rows[1][5], 100.0)
        self.assertAlmostEqual(sq_rows[1][6], 40.0)

        duck_dialect = _PORTABLE_DIALECTS['duckdb']
        compiled_dk = compile_sql(parsed, query, duck_dialect)
        dconn = duckdb.connect(':memory:')
        try:
            for stmt in setup_sql:
                dconn.execute(stmt)
            dk_rows = dconn.execute(compiled_dk['source']).fetchall()
        finally:
            dconn.close()
        self.assertEqual(dk_rows[0][0], 'East')
        self.assertAlmostEqual(dk_rows[0][3], 170.0)
        self.assertIsNone(dk_rows[1][2])
        self.assertAlmostEqual(dk_rows[1][3], 120.0)

    def test_perspectives_translations_and_interchange_exports(self):
        raw = _sample_c3_cube()
        raw['security'] = {
            'row_filters': [{
                'field': {'source_id': 'orders', 'field': 'customer_id'},
                'operator': 'eq',
                'value': 'secret_tenant_val',
            }],
            'tenant_filter': {
                'field': {'source_id': 'orders', 'field': 'customer_id'},
                'principal_claim': 'tenant_id',
                'required': True,
            },
            'roles': [],
        }
        raw['perspectives'] = [{
            'id': 'exec_sales',
            'name': 'Executive Sales',
            'description': 'Focused executive subset',
            'dimensions': ['customer', 'order_date'],
            'measures': ['gross_sales', 'priority_sales'],
            'default_measure': 'gross_sales',
        }]
        raw['translations'] = [
            {
                'locale': 'fr-CA',
                'caption': 'Cube des commandes',
                'description': 'Modèle dimensionnel',
                'entries': [
                    {
                        'kind': 'dimension',
                        'target_id': 'customer',
                        'caption': 'Client',
                    },
                    {
                        'kind': 'measure',
                        'target_id': 'gross_sales',
                        'caption': 'Ventes brutes',
                    },
                    {
                        'kind': 'perspective',
                        'target_id': 'exec_sales',
                        'caption': 'Ventes direction',
                    },
                ],
            },
            {
                'locale': 'es',
                'caption': 'Cubo de pedidos',
                'entries': [{
                    'kind': 'measure',
                    'target_id': 'gross_sales',
                    'caption': 'Ventas brutas',
                }],
            },
        ]
        cube = validate_model(raw)

        # Perspective query enforcement: ship_date is excluded from exec_sales.
        ok_q = validate_query(
            cube,
            {
                'perspective': 'exec_sales',
                'rows': ['customer'],
                'measures': ['gross_sales'],
            },
        )
        self.assertEqual(ok_q['perspective'], 'exec_sales')
        with self.assertRaises(SemanticModelError):
            validate_query(
                cube,
                {
                    'perspective': 'exec_sales',
                    'rows': ['ship_date'],
                    'measures': ['gross_sales'],
                },
            )
        with self.assertRaises(SemanticModelError):
            validate_query(
                cube,
                {
                    'perspective': 'exec_sales',
                    'axes': {'rows': ['customer']},
                    'measures': ['priority_orders'],
                },
            )

        # Localization exact & prefix fallback
        fr_model = localize_model(cube, 'fr-CA')
        self.assertEqual(fr_model['name'], 'Cube des commandes')
        self.assertEqual(fr_model['dimensions'][0]['name'], 'Client')
        self.assertEqual(fr_model['measures'][0]['name'], 'Ventes brutes')
        es_mx_model = localize_model(cube, 'es-MX')
        self.assertEqual(es_mx_model['name'], 'Cubo de pedidos')

        # Invalid translation target rejected
        bad_trans = copy.deepcopy(raw)
        bad_trans['translations'][0]['entries'].append({
            'kind': 'measure',
            'target_id': 'nonexistent_measure',
            'caption': 'Oups',
        })
        with self.assertRaises(SemanticModelError):
            validate_model(bad_trans)

        # Lossless DDN round-trip & 3-way merge of perspectives + translations
        base_ddn, eids = semantic_model_to_ddn(cube)
        parsed = ddn_to_semantic_model(base_ddn)['model']
        self.assertEqual(parsed['perspectives'], cube['perspectives'])
        self.assertEqual(parsed['translations'], cube['translations'])

        active_cube = copy.deepcopy(cube)
        active_cube['perspectives'].append({
            'id': 'shipping_ops',
            'name': 'Shipping Ops',
            'dimensions': ['ship_date'],
            'measures': ['priority_orders'],
        })
        active_ddn, _ = semantic_model_to_ddn(active_cube, element_ids=eids)

        draft_cube = copy.deepcopy(cube)
        draft_cube['translations'].append({
            'locale': 'de-DE',
            'caption': 'Bestellwürfel',
            'entries': [],
        })
        draft_ddn, _ = semantic_model_to_ddn(draft_cube, element_ids=eids)

        merged = diff_cube_ddn(base_ddn, active_ddn, draft_ddn)
        self.assertEqual(merged['conflicts'], [])
        merged_parsed = ddn_to_semantic_model(
            merged['merged_ddn_text']
        )['model']
        self.assertEqual(
            {p['id'] for p in merged_parsed['perspectives']},
            {'exec_sales', 'shipping_ops'},
        )
        self.assertEqual(
            {t['locale'] for t in merged_parsed['translations']},
            {'fr-CA', 'es', 'de-DE'},
        )

        # SML v1.8 export (primary) & Apache Ossie v0.2.0 lossy export
        sml = export_cube_to_sml(cube)
        self.assertEqual(sml['format'], 'sml@1.8')
        self.assertIn('sml_manifest.yml', sml['files'])
        self.assertIn('perspectives/exec_sales.yml', sml['files'])
        self.assertIn('locales/fr-CA.yml', sml['files'])
        all_sml_text = '\n'.join(sml['files'].values())
        self.assertNotIn('tenant_id', all_sml_text)
        self.assertNotIn('secret_tenant_val', all_sml_text)
        self.assertEqual(
            sml['loss_report']['items'][0]['category'],
            'security_policy_excluded',
        )

        ossie = export_cube_to_ossie(cube, include_custom_extensions=True)
        self.assertEqual(ossie['format'], 'apache-ossie@0.2.0')
        self.assertEqual(ossie['loss_report']['fidelity'], 'lossy')
        ossie_cats = {i['category'] for i in ossie['loss_report']['items']}
        self.assertIn('role_playing_dimension', ossie_cats)
        self.assertIn('filtered_measure', ossie_cats)
        self.assertIn('perspective', ossie_cats)
        self.assertIn('translation', ossie_cats)
        self.assertIn('materialization_plan', ossie_cats)
        self.assertIn('security_policy_excluded', ossie_cats)
        self.assertNotIn('tenant_id', ossie['yaml'])
        self.assertNotIn('secret_tenant_val', ossie['yaml'])

        ossie_no_ext = export_cube_to_ossie(
            cube, include_custom_extensions=False
        )
        self.assertNotIn(
            'custom_extensions', ossie_no_ext['document']['semantic_models'][0]
        )

        # Verify HTTP export & locale routes
        with tempfile.TemporaryDirectory() as tmp:
            app = Flask(__name__)
            app.secret_key = 'test-cube-interchange'
            app.config['TESTING'] = True
            app.config['LOGIN_DISABLED'] = True
            app.config['CDEADMIN_DESIGN_STORE_PATH'] = f'{tmp}/designs.db'
            app.extensions[SEMANTIC_SERVICE_EXTENSION_KEY] = (
                SemanticModelService(repository=_MemorySemanticRepo())
            )
            init_routes_app(app)
            client = app.test_client()
            c_resp = client.post(
                '/cdeadmin/api/projects/p1/designs',
                json={
                    'mode': 'create_cube',
                    'key': 'intl-cube',
                    'title': 'Intl Cube',
                    'model': cube,
                },
            )
            did = c_resp.get_json()['data']['id']

            loc_resp = client.get(
                f'/cdeadmin/api/projects/p1/designs/{did}'
                '/cube/model?locale=fr-CA'
            )
            self.assertEqual(loc_resp.status_code, 200)
            self.assertEqual(
                loc_resp.get_json()['data']['localized_model']['name'],
                'Cube des commandes',
            )

            sml_http = client.post(
                f'/cdeadmin/api/projects/p1/designs/{did}/cube/export',
                json={'format': 'sml'},
            )
            self.assertEqual(sml_http.status_code, 200)
            self.assertEqual(sml_http.get_json()['data']['format'], 'sml@1.8')

            ossie_http = client.get(
                f'/cdeadmin/api/projects/p1/designs/{did}'
                '/cube/export?format=ossie&include_custom_extensions=0'
            )
            self.assertEqual(ossie_http.status_code, 200)
            self.assertEqual(
                ossie_http.get_json()['data']['format'], 'apache-ossie@0.2.0'
            )


if __name__ == '__main__':
    unittest.main()
