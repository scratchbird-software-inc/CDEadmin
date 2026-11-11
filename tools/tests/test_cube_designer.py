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
    init_routes_app,
    inspect_ddn_text,
    is_uuid7,
    preview_cube_materialization_plan,
    semantic_model_to_ddn,
)
from pgadmin.cdeadmin.design_store.routes import SEMANTIC_SERVICE_EXTENSION_KEY
from pgadmin.cdeadmin.semantic_models import (
    SemanticModelService,
    public_model,
    validate_model,
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


if __name__ == '__main__':
    unittest.main()
