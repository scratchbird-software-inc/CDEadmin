##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Regression tests for cross-design Where Used and checkpoint DDN diff."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'web') not in sys.path:
    sys.path.insert(0, str(ROOT / 'web'))

from pgadmin.cdeadmin.design_store import DesignStore, StoreDDNProcess
from pgadmin.cdeadmin.design_store.bi_ddn import BIDesignSync
from pgadmin.cdeadmin.design_store.cube_ddn import CubeDesignSync
from pgadmin.cdeadmin.design_store.screen_mesh_ddn import ScreenMeshSync
from pgadmin.cdeadmin.design_store.shared_ddn import build_four_level_erd_ddn
from pgadmin.cdeadmin.design_store.where_used import (
    diff_design_versions,
    query_cross_design_usage,
)


def test_checkpoint_diff_tracks_added_modified_and_removed_ddn_elements(tmp_path: Path):
    store = DesignStore(db_path=tmp_path / 'designs.db')
    proc = StoreDDNProcess(store)

    ddn_v1 = build_four_level_erd_ddn(
        title='Operations Schema',
        physical_tables=[
            {
                'name': 'customers',
                'columns': [
                    {'name': 'id', 'type': 'INTEGER', 'pk': True, 'nullable': False},
                    {'name': 'name', 'type': 'TEXT', 'nullable': False},
                ],
            },
            {
                'name': 'legacy_notes',
                'columns': [{'name': 'id', 'type': 'INTEGER', 'pk': True}],
            },
        ],
    )
    created = store.create_design(
        project_id='proj-diff',
        key='ops_erd',
        kind='erd',
        title='Operations Schema',
        ddn_text=ddn_v1,
        actor_id=1,
        note='Initial schema',
    )
    design_id = created['id']

    ddn_v2 = build_four_level_erd_ddn(
        title='Operations Schema',
        physical_tables=[
            {
                'name': 'customers',
                'columns': [
                    {'name': 'id', 'type': 'INTEGER', 'pk': True, 'nullable': False},
                    {'name': 'name', 'type': 'TEXT', 'nullable': False},
                    {'name': 'email', 'type': 'TEXT', 'nullable': True},
                ],
            },
            {
                'name': 'work_orders',
                'columns': [{'name': 'id', 'type': 'INTEGER', 'pk': True}],
            },
        ],
    )
    proc.save_from_ddn(
        design_id,
        expected_head_version=1,
        ddn_or_workspace=ddn_v2,
        actor_id=1,
        note='Added work_orders and customer email, dropped legacy_notes',
    )

    diff = diff_design_versions(store, design_id, 1, 2)
    assert diff['identical'] is False
    assert diff['base_version'] == 1
    assert diff['target_version'] == 2
    assert 'ops_erd@v1' in diff['unified_diff']
    assert 'ops_erd@v2' in diff['unified_diff']
    added_labels = {e['label'] for e in diff['added_elements']}
    removed_labels = {e['label'] for e in diff['removed_elements']}
    assert 'work_orders' in added_labels or 'email' in added_labels
    assert 'legacy_notes' in removed_labels


def test_cross_design_where_used_spans_erd_cube_bi_and_screen_mesh(tmp_path: Path):
    store = DesignStore(db_path=tmp_path / 'designs.db')
    proc = StoreDDNProcess(store)

    # 1. Cube bound to work_orders
    cube_sync = CubeDesignSync(store, proc, None)
    cube_res = cube_sync.create_cube(
        project_id='proj-impact',
        key='ops_cube',
        title='Work Orders Cube',
        actor_id=1,
        model={
            'name': 'ops_cube',
            'sources': [
                {
                    'id': 'fact_wo',
                    'resource_id': 'main.work_orders',
                    'relation': ['main', 'work_orders'],
                }
            ],
            'measures': [
                {
                    'id': 'order_total',
                    'name': 'Order Total',
                    'aggregation': 'sum',
                    'field': {'source_id': 'fact_wo', 'field': 'amount'},
                }
            ],
            'dimensions': [
                {
                    'id': 'status_dim',
                    'name': 'Order Status',
                    'field': {'source_id': 'fact_wo', 'field': 'status'},
                }
            ],
        },
    )
    assert cube_res['design']['id']

    # 2. BI Question & Dashboard referencing question
    from pgadmin.cdeadmin.design_store.bi_ddn import sql_to_bi_question_model

    bi_sync = BIDesignSync(store, proc)
    mapped_q = sql_to_bi_question_model(
        'SELECT status, COUNT(id) AS orders FROM main.work_orders GROUP BY status',
        name='Work Orders by Status',
    )['question']
    q_res = bi_sync.create_question(
        project_id='proj-impact',
        key='wo_by_status',
        title='Work Orders by Status',
        actor_id=1,
        question=mapped_q,
    )
    q_id = q_res['design']['id']
    bi_sync.create_dashboard(
        project_id='proj-impact',
        key='ops_dash',
        title='Operations Executive Dashboard',
        actor_id=1,
        dashboard={
            'name': 'Operations Executive Dashboard',
            'cards': [
                {
                    'id': 'card_wo',
                    'title': 'Orders by Status',
                    'question': {'question_design_id': q_id},
                }
            ],
        },
    )

    # 3. Screen Mesh bound to main.work_orders.status
    from pgadmin.cdeadmin.design_store import uuid7

    scr_id = uuid7()
    ctl_id = uuid7()
    mesh_sync = ScreenMeshSync(store, proc)
    mesh_sync.create_screen_mesh(
        project_id='proj-impact',
        key='wo_screen',
        title='Work Order Intake Screen',
        actor_id=1,
        mesh={
            'name': 'Work Order Intake Screen',
            'screens': [
                {
                    'id': scr_id,
                    'name': 'Work Order Intake',
                }
            ],
            'controls': [
                {
                    'id': ctl_id,
                    'screen_id': scr_id,
                    'role': 'ui.dropdown',
                    'label': 'Status',
                }
            ],
            'bindings': [
                {
                    'source_id': ctl_id,
                    'target_kind': 'column',
                    'target_ref': 'main.work_orders.status',
                }
            ],
        },
    )

    impact = query_cross_design_usage(
        store,
        'proj-impact',
        target_ref='main.work_orders',
    )
    assert impact['total'] >= 3
    kinds = set(impact['by_design_kind'].keys())
    assert {'cube', 'question', 'screen'} <= kinds

    q_impact = query_cross_design_usage(
        store,
        'proj-impact',
        target_ref=q_id,
    )
    assert any(u['design_kind'] == 'dashboard' for u in q_impact['usages'])
