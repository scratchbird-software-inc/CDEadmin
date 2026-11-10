##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Tests for the shared server-side DDN library, StoreDDNProcess, Flask routes
and ERD 4-level modelling, conversion and drift overlays.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from flask import Flask
import pytest

from pgadmin.cdeadmin.design_store import (
    DESTRUCTIVE_METADATA_WARNING,
    DesignStore,
    DesignStoreError,
    DesignStoreForbidden,
    StoreDDNProcess,
    build_four_level_erd_ddn,
    compute_server_layout,
    compute_system_diagram_drift,
    convert_erd_design_engine,
    ddn_text_to_workspace,
    init_routes_app,
    preview_erd_alter_plan,
    propose_system_diagram_change,
)
from pgadmin.cdeadmin.workspace import ddn_source as ddn, firebird_erd

_ADMIT_MJS = (
    Path(__file__).resolve().parents[2]
    / 'web/pgadmin/cdeadmin/workspace/ddn/workspace_admission.mjs'
)


def _verify_workspace_with_ddn(workspace: dict) -> None:
    script = (
        f'import {{admitWorkspace}} from {json.dumps(_ADMIT_MJS.as_uri())};'
        'let input = "";'
        'for await (const chunk of process.stdin) input += chunk;'
        'await admitWorkspace(JSON.parse(input));'
    )
    proc = subprocess.run(
        [
            ddn.node_executable(),
            ddn.NODE_HEAP_OPTION,
            '--input-type=module',
            '-e',
            script,
        ],
        input=json.dumps(workspace, ensure_ascii=False),
        text=True,
        encoding='utf-8',
        capture_output=True,
        timeout=30,
        env=ddn.runner_environment(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def _sample_erd_ddn() -> str:
    fb_resources = [
        {
            'resource_id': 'firebird:table:CUSTOMERS',
            'resource_kind': 'table',
            'display_name': 'CUSTOMERS',
            'display_path': ['CUSTOMERS'],
            'system': False,
            'native': {'relation_name': 'CUSTOMERS', 'relation_type': 0},
        },
        {
            'resource_id': 'firebird:column:CUSTOMERS.ID',
            'resource_kind': 'column',
            'display_name': 'ID',
            'display_path': ['CUSTOMERS', 'ID'],
            'system': False,
            'native': {
                'position': 0,
                'field_type': 8,
                'field_sub_type': 0,
                'field_length': 4,
                'field_scale': 0,
                'not_null': 1,
            },
        },
        {
            'resource_id': 'firebird:column:CUSTOMERS.BALANCE',
            'resource_kind': 'column',
            'display_name': 'BALANCE',
            'display_path': ['CUSTOMERS', 'BALANCE'],
            'system': False,
            'native': {
                'position': 1,
                'field_type': 16,
                'field_sub_type': 2,
                'field_precision': 18,
                'field_length': 8,
                'field_scale': -2,
                'not_null': 1,
            },
        },
        {
            'resource_id': 'firebird:table:ORDERS',
            'resource_kind': 'table',
            'display_name': 'ORDERS',
            'display_path': ['ORDERS'],
            'system': False,
            'native': {'relation_name': 'ORDERS', 'relation_type': 0},
        },
        {
            'resource_id': 'firebird:column:ORDERS.CUSTOMER_ID',
            'resource_kind': 'column',
            'display_name': 'CUSTOMER_ID',
            'display_path': ['ORDERS', 'CUSTOMER_ID'],
            'system': False,
            'native': {
                'position': 0,
                'field_type': 8,
                'field_sub_type': 0,
                'field_length': 4,
                'field_scale': 0,
                'not_null': 1,
            },
        },
        {
            'resource_id': 'firebird:index:PK_CUSTOMERS',
            'resource_kind': 'index',
            'display_name': 'PK_CUSTOMERS',
            'display_path': ['CUSTOMERS', 'PK_CUSTOMERS'],
            'system': False,
            'native': {
                'index_name': 'PK_CUSTOMERS',
                'relation_name': 'CUSTOMERS',
                'unique_flag': 1,
                'segments': [{'field_name': 'ID', 'position': 0}],
            },
        },
        {
            'resource_id': 'firebird:index:FK_ORDERS_CUST',
            'resource_kind': 'index',
            'display_name': 'FK_ORDERS_CUST',
            'display_path': ['ORDERS', 'FK_ORDERS_CUST'],
            'system': False,
            'native': {
                'index_name': 'FK_ORDERS_CUST',
                'relation_name': 'ORDERS',
                'unique_flag': 0,
                'segments': [{'field_name': 'CUSTOMER_ID', 'position': 0}],
            },
        },
        {
            'resource_id': 'firebird:constraint:PK_CUSTOMERS',
            'resource_kind': 'constraint',
            'display_name': 'PK_CUSTOMERS',
            'display_path': ['CUSTOMERS', 'PK_CUSTOMERS'],
            'system': False,
            'native': {
                'constraint_name': 'PK_CUSTOMERS',
                'relation_name': 'CUSTOMERS',
                'constraint_type': 'PRIMARY KEY',
                'index_name': 'PK_CUSTOMERS',
            },
        },
        {
            'resource_id': 'firebird:constraint:FK_ORDERS_CUST',
            'resource_kind': 'constraint',
            'display_name': 'FK_ORDERS_CUST',
            'display_path': ['ORDERS', 'FK_ORDERS_CUST'],
            'system': False,
            'native': {
                'constraint_name': 'FK_ORDERS_CUST',
                'relation_name': 'ORDERS',
                'constraint_type': 'FOREIGN KEY',
                'index_name': 'FK_ORDERS_CUST',
                'referenced_relation': 'CUSTOMERS',
                'referenced_index': 'PK_CUSTOMERS',
                'update_rule': 'RESTRICT',
                'delete_rule': 'CASCADE',
            },
        },
    ]
    diag = firebird_erd.build_diagram(
        fb_resources,
        {'endpoint_id': 'ep-fb', 'database_target_id': 'fb-main'},
    )
    return diag['snapshot']['files']['relations.ddn']


def test_server_layered_layout_pinned_nodes_and_tiling(tmp_path):
    store = DesignStore(db_path=tmp_path / 'designs.db')
    proc = StoreDDNProcess(store)

    created = store.create_design(
        project_id='proj-erd',
        key='sales-erd',
        kind='erd',
        title='Sales Physical ERD',
        ddn_text=_sample_erd_ddn(),
        actor_id=1,
        observe_resources=True,
    )
    session = proc.open_session(created['id'], tile_size=512)
    layout = session['layout']
    assert layout['algorithm'] == 'scratchrobin-server-layered@1'
    assert len(layout['nodes']) == 2
    assert len(layout['edges']) == 1
    assert len(layout['tiles']) >= 1

    by_name = {n['name']: n for n in layout['nodes']}
    # ORDERS -> CUSTOMERS edge puts ORDERS in layer 0 and CUSTOMERS in layer 1
    assert by_name['ORDERS']['layer'] == 0
    assert by_name['CUSTOMERS']['layer'] == 1

    # Pin CUSTOMERS at (640, 420) and save through StoreDDNProcess
    cust_id = by_name['CUSTOMERS']['id']
    saved = proc.save_from_ddn(
        created['id'],
        expected_head_version=1,
        ddn_or_workspace=session['workspace'],
        actor_id=1,
        pinned_positions={
            cust_id: {'x': 640.0, 'y': 420.0, 'pinned': True}
        },
        note='Pinned CUSTOMERS table',
    )
    new_ddn = saved['design']['version']['ddn_text']
    assert 'layout_x "640.0"' in new_ddn
    assert 'layout_y "420.0"' in new_ddn
    assert 'layout_pinned "true"' in new_ddn

    recomputed = compute_server_layout(new_ddn, use_cache=False)
    cust_after = next(n for n in recomputed['nodes'] if n['id'] == cust_id)
    assert cust_after['x'] == 640.0
    assert cust_after['y'] == 420.0
    assert cust_after['pinned'] is True


def test_acceptance_policy_a9_and_design_inclusion_pinning_a10(tmp_path):
    store = DesignStore(db_path=tmp_path / 'designs.db')
    proc = StoreDDNProcess(store)

    shared_dim = store.create_design(
        project_id='proj-1',
        key='shared-customer-dim',
        kind='cube',
        title='Shared Customer Dimension',
        ddn_text=_sample_erd_ddn(),
        actor_id=1,
    )
    # A9: without ScratchRobin permission, accept is forbidden
    with pytest.raises(
        DesignStoreForbidden, match='ScratchRobin acceptance permission'
    ):
        proc.accept_with_policy(
            shared_dim['id'],
            1,
            actor_id=2,
            has_scratchrobin_permission=False,
        )

    # A9: when project requires Git review, missing git_review_ref is rejected
    with pytest.raises(
        DesignStoreForbidden, match='requires a Git review reference'
    ):
        proc.accept_with_policy(
            shared_dim['id'],
            1,
            actor_id=1,
            has_scratchrobin_permission=True,
            require_git_review=True,
        )

    accepted_v1 = proc.accept_with_policy(
        shared_dim['id'],
        1,
        actor_id=1,
        has_scratchrobin_permission=True,
        require_git_review=True,
        git_review_ref='git:commit:a1b2c3d4',
        comment='Approved v1',
    )
    assert accepted_v1['active_version'] == 1
    assert (
        accepted_v1['version']['approval_ref']
        == 'scratchrobin+git:git:commit:a1b2c3d4'
    )

    # Create a consumer design that includes shared_dim
    consumer = store.create_design(
        project_id='proj-1',
        key='sales-cube',
        kind='cube',
        title='Sales Cube',
        ddn_text=_sample_erd_ddn(),
        actor_id=1,
    )
    # Default A10 behavior: pin to current active version (1)
    proc.include_design(
        consumer['id'],
        1,
        depends_on_design_id=shared_dim['id'],
        pin_version=True,
    )

    # Advance shared_dim to v2 and accept v2
    branched = store.branch_draft_from_accepted(shared_dim['id'], actor_id=1)
    proc.accept_with_policy(
        shared_dim['id'],
        branched['head_version'],
        actor_id=1,
        has_scratchrobin_permission=True,
    )

    # Pinned include still resolves to version 1
    resolved_pinned = proc.resolve_includes(consumer['id'], 1)
    assert resolved_pinned[0]['mode'] == 'pinned'
    assert resolved_pinned[0]['resolved_version'] == 1

    # Opt in to follow_latest_accepted (pin_version=False) -> resolves to v2
    proc.include_design(
        consumer['id'],
        1,
        depends_on_design_id=shared_dim['id'],
        pin_version=False,
    )
    resolved_latest = proc.resolve_includes(consumer['id'], 1)
    assert resolved_latest[0]['mode'] == 'follow_latest_accepted'
    assert resolved_latest[0]['resolved_version'] == 2


def test_four_level_erd_ddn_conversion_d4_and_system_drift_d1():
    # D3: ORM mapping keys are rejected
    with pytest.raises(DesignStoreError, match='ORM/application mapping'):
        build_four_level_erd_ddn(
            title='Invalid ORM Model',
            conceptual_entities=[{'name': 'Customer'}],
            extensions={'orm_class': 'app.models.Customer'},
        )

    c_id = '019a0000-0000-7000-8000-000000000001'
    l_id = '019a0000-0000-7000-8000-000000000002'
    p_id = '019a0000-0000-7000-8000-000000000003'
    d_id = '019a0000-0000-7000-8000-000000000004'

    four_level_ddn = build_four_level_erd_ddn(
        title='Commerce Architecture',
        conceptual_entities=[{'id': c_id, 'name': 'Customer Concept'}],
        logical_entities=[
            {
                'id': l_id,
                'name': 'Customer Entity',
                'fields': [
                    {'name': 'customer_id', 'datatype': 'uuid'},
                    {'name': 'credit_limit', 'datatype': 'decimal'},
                ],
            }
        ],
        physical_tables=[
            {
                'id': p_id,
                'name': 'customers',
                'engine': 'postgresql',
                'fields': [
                    {'name': 'customer_id', 'datatype': 'uuid'},
                    {'name': 'credit_limit', 'datatype': 'numeric(18,4)'},
                ],
            }
        ],
        deployment_nodes=[
            {
                'id': d_id,
                'name': 'db-primary-01',
                'role': 'table',
                'resource_id': 'host:db-primary-01',
                'host': '10.0.1.15',
                'rack': 'rack-east-02',
                'cloud_region': 'us-east-1',
                'instance_type': 'bare-metal-64g',
            }
        ],
        level_links=[
            {'source': l_id, 'target': c_id, 'kind': 'refines'},
            {'source': p_id, 'target': l_id, 'kind': 'implements'},
            {'source': d_id, 'target': p_id, 'kind': 'hosts'},
        ],
        extensions={'governance_tier': 'gold'},
    )
    workspace = ddn_text_to_workspace(
        four_level_ddn, entry='commerce.ddn', view='erd_all_levels'
    )
    _verify_workspace_with_ddn(workspace)

    # D4: Engine-to-engine conversion through neutral logical level
    fb_ddn = _sample_erd_ddn()
    # Converting Firebird NUMERIC(18,2) -> SQLite NUMERIC is lossy; strict
    # mode requires an explicit choice.
    with pytest.raises(
        DesignStoreError, match='Lossy type conversions require explicit'
    ):
        convert_erd_design_engine(
            fb_ddn,
            source_engine='firebird',
            target_engine='sqlite',
            strict=True,
        )

    converted = convert_erd_design_engine(
        fb_ddn,
        source_engine='firebird',
        target_engine='sqlite',
        custom_type_map={'integer': {'physical': 'INT64', 'lossy': False}},
        loss_choices={'BALANCE': 'accept_loss'},
        strict=True,
    )
    assert converted['loss_report']['lossy_count'] == 1
    assert 'datatype "INT64"' in converted['ddn_text']
    assert 'datatype "NUMERIC"' in converted['ddn_text']

    # D1: System diagram drift overlay and native review change proposal
    drift = compute_system_diagram_drift(
        four_level_ddn,
        live_nodes=[
            {
                'resource_id': 'host:db-primary-01',
                'name': 'db-primary-01',
                'host': '10.0.1.15',
                'rack': 'rack-west-99',
                'cloud_region': 'us-east-1',
                'instance_type': 'bare-metal-64g',
            },
            {
                'resource_id': 'host:db-replica-02',
                'name': 'db-replica-02',
            },
        ],
    )
    assert drift['has_drift'] is True
    assert len(drift['property_drift']) == 1
    assert (
        drift['property_drift'][0]['differences']['rack']['designed']
        == 'rack-east-02'
    )
    assert (
        drift['property_drift'][0]['differences']['rack']['live']
        == 'rack-west-99'
    )
    assert len(drift['unmodeled_live']) == 1

    proposal = propose_system_diagram_change(
        design_id=d_id,
        version=1,
        element_id=d_id,
        action='relocate_replica',
        parameters={'target_rack': 'rack-west-99'},
        actor_id=1,
    )
    assert proposal['requires_native_review'] is True
    assert proposal['applied_immediately'] is False
    assert 'non-reversible' in proposal['destructive_warning']


def test_design_store_flask_routes_end_to_end(tmp_path):
    app = Flask(__name__)
    app.secret_key = 'test-secret-key'
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    app.config['CDEADMIN_DESIGN_STORE_PATH'] = str(tmp_path / 'routes.db')
    init_routes_app(app)

    client = app.test_client()

    # 1. Create design via POST
    res = client.post(
        '/cdeadmin/api/projects/demo-proj/designs',
        json={
            'key': 'orders-erd',
            'kind': 'erd',
            'title': 'Orders Physical ERD',
            'ddn_text': _sample_erd_ddn(),
            'observe_resources': True,
        },
    )
    assert res.status_code == 200
    created = res.get_json()['data']
    design_id = created['id']

    # 2. Open session via GET (includes workspace, layout, tiles, bindings)
    res = client.get(
        f'/cdeadmin/api/projects/demo-proj/designs/{design_id}?tile_size=512'
    )
    assert res.status_code == 200
    session = res.get_json()['data']
    assert session['design']['id'] == design_id
    assert len(session['layout']['nodes']) == 2
    assert session['binding_summary']['valid'] >= 2

    # 3. Save version via PUT with pinned node position
    node0 = session['layout']['nodes'][0]['id']
    res = client.put(
        f'/cdeadmin/api/projects/demo-proj/designs/{design_id}',
        json={
            'expected_head_version': 1,
            'workspace': session['workspace'],
            'pinned_positions': {
                node0: {'x': 500.0, 'y': 300.0, 'pinned': True}
            },
            'status': 'in_review',
            'note': 'Pinned first table for review',
        },
    )
    assert res.status_code == 200
    saved = res.get_json()['data']
    assert saved['design']['head_version'] == 2

    # 4. Accept version 2 via POST
    res = client.post(
        f'/cdeadmin/api/projects/demo-proj/designs/{design_id}'
        '/versions/2/accept',
        json={
            'require_git_review': True,
            'git_review_ref': 'pr:108',
            'comment': 'Accepted after review',
        },
    )
    assert res.status_code == 200
    accepted = res.get_json()['data']
    assert accepted['active_version'] == 2

    # 5. Convert engine via POST /erd/convert
    res = client.post(
        f'/cdeadmin/api/projects/demo-proj/designs/{design_id}/erd/convert',
        json={
            'source_engine': 'firebird',
            'target_engine': 'sqlite',
            'loss_choices': {'BALANCE': 'accept_loss'},
            'strict': True,
            'save_version': True,
        },
    )
    assert res.status_code == 200
    conv = res.get_json()['data']
    assert conv['loss_report']['target_engine'] == 'sqlite'
    assert conv['saved']['design']['head_version'] == 3

    # 6. Create 4-level ERD via mode='create_erd' and preview alter plan
    res_erd = client.post(
        '/cdeadmin/api/projects/demo-proj/designs',
        json={
            'mode': 'create_erd',
            'key': 'billing-erd',
            'title': 'Billing ERD',
            'conceptual_entities': [{'name': 'Invoice Concept'}],
            'physical_tables': [
                {
                    'id': '019a0000-0000-7000-8000-000000000101',
                    'name': 'customers',
                    'engine': 'sqlite',
                    'fields': [
                        {
                            'id': '019a0000-0000-7000-8000-000000000102',
                            'name': 'id',
                            'datatype': 'INTEGER',
                            'nullable': False,
                        },
                        {
                            'id': '019a0000-0000-7000-8000-000000000103',
                            'name': 'legacy_code',
                            'datatype': 'TEXT',
                            'nullable': True,
                        },
                    ],
                }
            ],
        },
    )
    assert res_erd.status_code == 200
    erd_id = res_erd.get_json()['data']['id']

    # Accept v1 as baseline
    acc_erd = client.post(
        f'/cdeadmin/api/projects/demo-proj/designs/{erd_id}/versions/1/accept',
        json={'comment': 'Baseline physical schema'},
    )
    assert acc_erd.status_code == 200

    # Save v2 via POST /erd/model: rename customers -> accounts (same UUIDv7),
    # drop legacy_code, add credit_limit, and add invoices table
    upd_erd = client.post(
        f'/cdeadmin/api/projects/demo-proj/designs/{erd_id}/erd/model',
        json={
            'title': 'Billing ERD',
            'expected_head_version': 1,
            'conceptual_entities': [{'name': 'Invoice Concept'}],
            'physical_tables': [
                {
                    'id': '019a0000-0000-7000-8000-000000000101',
                    'name': 'accounts',
                    'engine': 'sqlite',
                    'fields': [
                        {
                            'id': '019a0000-0000-7000-8000-000000000102',
                            'name': 'id',
                            'datatype': 'INTEGER',
                            'nullable': False,
                        },
                        {
                            'id': '019a0000-0000-7000-8000-000000000104',
                            'name': 'credit_limit',
                            'datatype': 'NUMERIC',
                            'nullable': False,
                        },
                    ],
                },
                {
                    'id': '019a0000-0000-7000-8000-000000000105',
                    'name': 'invoices',
                    'engine': 'sqlite',
                    'fields': [
                        {
                            'id': '019a0000-0000-7000-8000-000000000106',
                            'name': 'invoice_id',
                            'datatype': 'INTEGER',
                            'nullable': False,
                        }
                    ],
                },
            ],
            'note': 'Renamed customers to accounts and added invoices',
        },
    )
    assert upd_erd.status_code == 200

    # Preview full alter plan (v1 -> v2)
    plan_res = client.post(
        f'/cdeadmin/api/projects/demo-proj/designs/{erd_id}/erd/alter-plan',
        json={'target_engine': 'duckdb'},
    )
    assert plan_res.status_code == 200
    plan = plan_res.get_json()['data']
    assert plan['requires_native_review'] is True
    assert plan['applied_immediately'] is False
    assert plan['destructive_warning'] == DESTRUCTIVE_METADATA_WARNING
    assert plan['has_destructive_changes'] is True
    kinds = {d['change_kind'] for d in plan['differences']}
    assert kinds == {
        'rename_table',
        'add_column',
        'drop_column',
        'create_table',
    }
    # Conceptual entity 'Invoice Concept' must not appear in SQL DDL
    assert 'Invoice Concept' not in plan['script']

    # Filter to non-destructive subset only
    safe_ids = [
        d['difference_id']
        for d in plan['differences']
        if not d['destructive']
    ]
    sub_res = client.post(
        f'/cdeadmin/api/projects/demo-proj/designs/{erd_id}/erd/alter-plan',
        json={
            'target_engine': 'duckdb',
            'selected_difference_ids': safe_ids,
        },
    )
    assert sub_res.status_code == 200
    sub_plan = sub_res.get_json()['data']
    assert sub_plan['has_destructive_changes'] is False
    assert 'DROP COLUMN' not in sub_plan['script']
    assert 'RENAME TO "accounts"' in sub_plan['script']


def test_live_sqlite_and_duckdb_erd_roundtrip_and_alter_preview(tmp_path):
    import sqlite3
    import test_cdeadmin_relational_providers  # noqa: F401
    from pgadmin.cdeadmin.providers.sqlite.provider import (
        _resources as capture_sqlite_resources,
    )
    from pgadmin.cdeadmin.workspace import duckdb_erd, sqlite_erd

    store = DesignStore(db_path=tmp_path / 'live_erd.db')

    # 1. Live SQLite catalog -> physical ERD import -> alter plan preview
    sq_file = tmp_path / 'sample.sqlite'
    conn = sqlite3.connect(str(sq_file))
    try:
        conn.execute(
            'CREATE TABLE widgets '
            '(id INTEGER PRIMARY KEY, label TEXT NOT NULL)'
        )
        conn.commit()
        sq_rows = capture_sqlite_resources(
            conn, {'capability_generation': 'gen-1'}
        )
    finally:
        conn.close()

    sq_diag = sqlite_erd.build_diagram(
        sq_rows,
        {'endpoint_id': 'local-sqlite', 'database_target_id': 'main'},
    )
    imported_sq = store.import_physical_erd_workspace(
        project_id='live-proj',
        key='sqlite-widgets',
        title='SQLite Widgets',
        workspace=sq_diag['snapshot'],
        actor_id=1,
    )
    sq_plan = preview_erd_alter_plan(
        store,
        imported_sq['id'],
        base_version=0,
        desired_version=1,
        target_engine='sqlite',
    )
    assert sq_plan['requires_native_review'] is True
    assert any(
        d['change_kind'] == 'create_table'
        and d['object_name'].endswith('widgets')
        for d in sq_plan['differences']
    )

    # 2. Live DuckDB catalog -> physical ERD import -> alter plan preview
    duckdb = pytest.importorskip('duckdb')
    from pgadmin.cdeadmin.providers.duckdb.catalog import (
        capture as duckdb_capture,
    )

    dk_conn = duckdb.connect(str(tmp_path / 'sample.duckdb'))
    try:
        dk_conn.execute(
            'CREATE TABLE metrics (id INTEGER PRIMARY KEY, val DOUBLE)'
        )
        dk_rows = duckdb_capture(dk_conn)['resources']
    finally:
        dk_conn.close()

    dk_diag = duckdb_erd.build_diagram(
        dk_rows,
        {'endpoint_id': 'local-duckdb', 'database_target_id': 'metrics-db'},
    )
    imported_dk = store.import_physical_erd_workspace(
        project_id='live-proj',
        key='duckdb-metrics',
        title='DuckDB Metrics',
        workspace=dk_diag['snapshot'],
        actor_id=1,
    )
    dk_plan = preview_erd_alter_plan(
        store,
        imported_dk['id'],
        base_version=0,
        desired_version=1,
        target_engine='duckdb',
    )
    assert dk_plan['requires_native_review'] is True
    assert any(
        d['change_kind'] == 'create_table'
        and d['object_name'].endswith('metrics')
        for d in dk_plan['differences']
    )
