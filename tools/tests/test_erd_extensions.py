##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Comprehensive tests for ERD & Data Modelling Phase 1 + Phase 2 extensions.

Covers:
- Clean-room SQL DDL (.sql), DBML (.dbml) and Live Catalog ERD importers
  with 0-diagnostic ddn-next-1 verification and explicit loss reports.
- 4-level ERD element inspection and interactive CRUD / whiteboard sketch
  mutation (conceptual, logical, physical, deployment, notes, sketch look).
- Conceptual Whiteboard -> Logical + Physical promotion ("Make it a design...",
  SR-F-030011) with catalog matching and surrogate PK/FK generation.
- Naming Standards checker, 1-click auto-fix and persistent waiver storage
  (SR-F-030012).
- Alter-plan 4-category risk classification, Flyway/Liquibase/Atlas/plain_sql
  migration wrappers, OperationBus native-operation review submission in
  awaiting_approval state, and Dev/Staging/Prod Multi-Target Deployment
  Environment Matrix (SR-F-030013 & SR-F-030014).
- End-to-end Flask API routes (/erd/import, /erd/elements,
  /erd/promote-whiteboard, /erd/standards, /erd/deploy).
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess

from flask import Flask
import pytest

from pgadmin.cdeadmin.design_store import (
    DesignStore,
    DesignStoreError,
    StoreDDNProcess,
    build_four_level_erd_ddn,
    ddn_text_to_workspace,
    init_routes_app,
)
from pgadmin.cdeadmin.design_store.erd_extensions import (
    evaluate_or_apply_erd_standards,
    import_erd_external,
    inspect_erd_elements,
    mutate_erd_elements,
    plan_or_submit_erd_deployment,
    promote_whiteboard_to_design,
)
from pgadmin.cdeadmin.operations import OperationBus, OperationStateError
from pgadmin.cdeadmin.workspace import ddn_source as ddn

_ADMIT_MJS = (
    Path(__file__).resolve().parents[2]
    / 'web/pgadmin/cdeadmin/workspace/ddn/workspace_admission.mjs'
)


def _verify_ddn_zero_diagnostics(ddn_text: str) -> dict:
    """Admit workspace via ddn-next-1 runtime and assert zero diagnostics."""
    workspace = ddn_text_to_workspace(ddn_text)
    script = (
        f'import {{admitWorkspace}} from {json.dumps(_ADMIT_MJS.as_uri())};'
        'let input = "";'
        'for await (const chunk of process.stdin) input += chunk;'
        'const admitted = await admitWorkspace(JSON.parse(input));'
        'const diags = admitted.diagnostics || [];'
        'process.stdout.write(JSON.stringify({diagnosticCount: diags.length, diagnostics: diags}));'
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
    parsed = json.loads(proc.stdout)
    assert parsed['diagnosticCount'] == 0, parsed['diagnostics']
    return parsed


def test_import_erd_sql_dbml_and_live_sqlite_catalog(tmp_path):
    store = DesignStore(db_path=tmp_path / 'designs.db')
    proc = StoreDDNProcess(store)

    # 1. Clean-room SQL DDL import
    sql_source = """
    -- Core customer & order schema
    CREATE TABLE public.customers (
        customer_id BIGINT PRIMARY KEY,
        email VARCHAR(255) NOT NULL UNIQUE,
        status VARCHAR(32) NOT NULL DEFAULT 'active',
        credit_score INT CHECK (credit_score >= 0),
        CONSTRAINT uq_customers_email UNIQUE (email)
    );

    CREATE TABLE public.orders (
        order_id BIGINT NOT NULL,
        customer_id BIGINT NOT NULL,
        placed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        total_cents BIGINT NOT NULL,
        CONSTRAINT pk_orders PRIMARY KEY (order_id)
    );

    ALTER TABLE public.orders
        ADD CONSTRAINT fk_orders_customers
        FOREIGN KEY (customer_id) REFERENCES public.customers (customer_id)
        ON DELETE CASCADE;

    CREATE UNIQUE INDEX ix_orders_customer_placed
        ON public.orders (customer_id, placed_at);

    CREATE VIEW public.active_customers AS
        SELECT customer_id, email FROM public.customers WHERE status = 'active';
    """
    sql_res = import_erd_external(
        store,
        proc,
        project_id='proj-import',
        actor_id=1,
        payload={
            'format': 'sql',
            'title': 'Imported Commerce SQL',
            'target_engine': 'postgresql',
            'source': sql_source,
        },
    )
    assert sql_res['design']['version']['status'] == 'draft'
    assert sql_res['design']['version']['origin'] == 'import:sql'
    assert sql_res['summary']['tables_imported'] == 2
    assert sql_res['summary']['relationships_imported'] == 1
    assert sql_res['summary']['indexes_imported'] >= 2
    # CHECK constraint + CREATE VIEW explicitly reported in loss_report
    loss_codes = {item['code'] for item in sql_res['loss_report']['items']}
    assert 'sql_column_check_omitted' in loss_codes
    assert 'unsupported_sql_object_in_erd_import' in loss_codes
    _verify_ddn_zero_diagnostics(sql_res['design']['version']['ddn_text'])

    inspected_sql = inspect_erd_elements(
        store, design_id=sql_res['design']['id']
    )
    assert len(inspected_sql['conceptual_entities']) == 2
    assert len(inspected_sql['logical_entities']) == 2
    assert len(inspected_sql['physical_tables']) == 2
    orders_tbl = next(
        t for t in inspected_sql['physical_tables'] if t['name'] == 'orders'
    )
    assert orders_tbl['pk_constraint_name'] == 'pk_orders'
    assert len(orders_tbl['foreign_keys']) == 1
    assert orders_tbl['foreign_keys'][0]['ref_table'] == 'customers'
    assert orders_tbl['foreign_keys'][0]['on_delete'] == 'CASCADE'

    # 2. Clean-room DBML import
    dbml_source = """
    Enum order_state {
      pending
      shipped
    }

    Table users as U {
      id bigint [pk]
      username varchar(64) [not null, unique, note: 'Login handle']
      created_at timestamp [default: `now()`]
      Note: 'Application users'
    }

    Table invoices {
      id bigint [pk]
      user_id bigint [not null, ref: > U.id]
      amount numeric(12,2) [not null]
      state order_state

      indexes {
        (user_id, state) [unique, name: 'ix_invoices_user_state']
      }
    }

    Table payments {
      id bigint [pk]
      invoice_id bigint [not null]
    }

    Ref fk_payments_invoices: payments.invoice_id > invoices.id
    """
    dbml_res = import_erd_external(
        store,
        proc,
        project_id='proj-import',
        actor_id=1,
        payload={
            'format': 'dbml',
            'title': 'Imported Billing DBML',
            'target_engine': 'postgresql',
            'dbml': dbml_source,
        },
    )
    assert dbml_res['design']['version']['origin'] == 'import:dbml'
    assert dbml_res['summary']['tables_imported'] == 3
    assert dbml_res['summary']['relationships_imported'] == 2
    assert any(
        i['code'] == 'dbml_enum_mapped_to_string_check'
        for i in dbml_res['loss_report']['items']
    )
    _verify_ddn_zero_diagnostics(dbml_res['design']['version']['ddn_text'])

    # 3. Live SQLite Catalog import
    sqlite_file = tmp_path / 'live_catalog.sqlite'
    conn = sqlite3.connect(str(sqlite_file))
    try:
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute(
            'CREATE TABLE departments (dept_id INTEGER PRIMARY KEY, name TEXT NOT NULL)'
        )
        conn.execute(
            'CREATE TABLE employees ('
            'emp_id INTEGER PRIMARY KEY, '
            'dept_id INTEGER NOT NULL REFERENCES departments(dept_id), '
            'email TEXT NOT NULL'
            ')'
        )
        conn.execute(
            'CREATE UNIQUE INDEX ix_employees_email ON employees(email)'
        )
        conn.commit()
    finally:
        conn.close()

    cat_res = import_erd_external(
        store,
        proc,
        project_id='proj-import',
        actor_id=1,
        payload={
            'format': 'catalog',
            'title': 'HR Live SQLite Catalog',
            'target_engine': 'sqlite',
            'endpoint_id': 'ep-hr-sqlite',
            'sqlite_path': str(sqlite_file),
        },
    )
    assert cat_res['design']['version']['origin'] == 'import:catalog'
    assert cat_res['summary']['tables_imported'] == 2
    assert cat_res['summary']['relationships_imported'] == 1
    assert len(cat_res['design']['bindings']) >= 2
    _verify_ddn_zero_diagnostics(cat_res['design']['version']['ddn_text'])


def test_four_level_crud_sketch_look_and_whiteboard_promotion(tmp_path):
    store = DesignStore(db_path=tmp_path / 'designs.db')
    proc = StoreDDNProcess(store)

    # Start with a blank ERD whiteboard
    blank_ddn = build_four_level_erd_ddn(title='Whiteboard Sketch')
    created = store.create_design(
        project_id='proj-wb',
        key='whiteboard-erd',
        kind='erd',
        title='Whiteboard Sketch',
        ddn_text=blank_ddn,
        actor_id=1,
    )
    design_id = created['id']

    # Toggle hand-drawn sketch look on an empty model + add conceptual note
    sketch_res = mutate_erd_elements(
        store,
        proc,
        design_id=design_id,
        actor_id=1,
        payload={
            'operation': 'set_sketch_look',
            'look_handdrawn': True,
        },
    )
    assert sketch_res['elements']['look_handdrawn'] is True
    _verify_ddn_zero_diagnostics(sketch_res['design']['version']['ddn_text'])

    note_res = mutate_erd_elements(
        store,
        proc,
        design_id=design_id,
        actor_id=1,
        payload={
            'operation': 'upsert_conceptual_note',
            'note_item': {
                'title': 'Domain Scope',
                'body': 'Order fulfilment bounded context',
                'area': 'Sales',
            },
        },
    )
    assert len(note_res['elements']['conceptual_notes']) == 1

    # Add two conceptual boxes + connect them
    c1 = mutate_erd_elements(
        store,
        proc,
        design_id=design_id,
        actor_id=1,
        payload={
            'operation': 'upsert_conceptual',
            'entity': {'name': 'Customer', 'area': 'CRM'},
        },
    )['elements']['conceptual_entities'][0]

    c2_all = mutate_erd_elements(
        store,
        proc,
        design_id=design_id,
        actor_id=1,
        payload={
            'operation': 'upsert_conceptual',
            'entity': {'name': 'Purchase Order', 'area': 'Sales'},
        },
    )['elements']['conceptual_entities']
    c2 = next(e for e in c2_all if e['name'] == 'Purchase Order')

    # Pin Customer node and connect Purchase Order -> Customer
    conn_res = mutate_erd_elements(
        store,
        proc,
        design_id=design_id,
        actor_id=1,
        payload={
            'operation': 'connect_conceptual',
            'relation': {
                'source': c2['id'],
                'target': c1['id'],
                'title': 'placed by',
            },
            'pinned_positions': {
                c1['id']: {'x': 420.0, 'y': 180.0, 'pinned': True}
            },
        },
    )
    assert len(conn_res['elements']['conceptual_relations']) == 1
    _verify_ddn_zero_diagnostics(conn_res['design']['version']['ddn_text'])

    # Add a deployment node and verify 0 diagnostics in ddn-next-1
    dep_res = mutate_erd_elements(
        store,
        proc,
        design_id=design_id,
        actor_id=1,
        payload={
            'operation': 'upsert_deployment_node',
            'node': {
                'name': 'pg-primary-east',
                'engine': 'postgresql',
                'endpoint_id': 'ep-pg-1',
                'location': 'us-east-1',
                'role': 'primary',
                'host': 'db1.internal',
                'tables': ['customers', 'purchase_orders'],
            },
        },
    )
    assert len(dep_res['elements']['deployment_nodes']) == 1
    assert dep_res['elements']['deployment_nodes'][0]['role'] == 'primary'
    _verify_ddn_zero_diagnostics(dep_res['design']['version']['ddn_text'])

    # Preview promotion without saving (save_version=False), matching Customer to catalog
    preview_promo = promote_whiteboard_to_design(
        store,
        proc,
        design_id=design_id,
        actor_id=1,
        payload={
            'target_engine': 'postgresql',
            'save_version': False,
            'catalog_tables': [
                {
                    'name': 'customers',
                    'columns': [
                        {'name': 'customer_id', 'type': 'BIGINT', 'pk': True},
                        {'name': 'full_name', 'type': 'VARCHAR(200)', 'nullable': False},
                    ],
                }
            ],
        },
    )
    assert preview_promo['promoted_logical_count'] == 2
    assert preview_promo['promoted_physical_count'] == 2
    assert preview_promo['matched_catalog_tables'] == ['customers']
    assert preview_promo['inferred_foreign_keys'] == 1
    # Head version unchanged during preview
    assert store.get_design(design_id)['head_version'] == dep_res['design']['head_version']

    # Execute promotion & save checkpoint
    saved_promo = promote_whiteboard_to_design(
        store,
        proc,
        design_id=design_id,
        actor_id=1,
        payload={
            'target_engine': 'postgresql',
            'save_version': True,
            'catalog_tables': [
                {
                    'name': 'customers',
                    'columns': [
                        {'name': 'customer_id', 'type': 'BIGINT', 'pk': True},
                        {'name': 'full_name', 'type': 'VARCHAR(200)', 'nullable': False},
                    ],
                }
            ],
        },
    )
    _verify_ddn_zero_diagnostics(saved_promo['ddn_text'])
    after = inspect_erd_elements(store, design_id=design_id)
    phys_by_name = {t['name']: t for t in after['physical_tables']}
    assert 'customers' in phys_by_name
    assert 'purchase_orders' in phys_by_name
    po_cols = {c['name']: c for c in phys_by_name['purchase_orders']['fields']}
    assert 'purchase_order_id' in po_cols
    assert 'customer_id' in po_cols
    assert po_cols['customer_id']['references'] == 'customers.customer_id'
    # Pinned position on c1 was preserved across mutations and promotion!
    assert 'layout_x "420.0"' in saved_promo['ddn_text']


def test_naming_standards_check_waivers_and_auto_fix(tmp_path):
    store = DesignStore(db_path=tmp_path / 'designs.db')
    proc = StoreDDNProcess(store)

    imp = import_erd_external(
        store,
        proc,
        project_id='proj-std',
        actor_id=1,
        payload={
            'format': 'sql',
            'title': 'Legacy Naming Schema',
            'target_engine': 'postgresql',
            'sql': """
            CREATE TABLE "CustomerAccounts" (
                "AccountID" BIGINT,
                "FirstName" VARCHAR(100) NOT NULL,
                CONSTRAINT "PK_CustAcct" PRIMARY KEY ("AccountID")
            );
            CREATE TABLE "OrderHeaders" (
                "OrderID" BIGINT PRIMARY KEY,
                "AccountID" BIGINT NOT NULL,
                CONSTRAINT "bad_fk_name" FOREIGN KEY ("AccountID")
                    REFERENCES "CustomerAccounts" ("AccountID")
            );
            CREATE INDEX "idx_bad_order_acct" ON "OrderHeaders" ("AccountID");
            """,
        },
    )
    design_id = imp['design']['id']

    # 1. Check naming violations
    chk = evaluate_or_apply_erd_standards(
        store,
        proc,
        design_id=design_id,
        actor_id=1,
        payload={'action': 'check'},
    )
    assert chk['active_count'] >= 6
    assert chk['waived_count'] == 0
    rules_triggered = {v['rule'] for v in chk['violations']}
    assert {
        'table_case',
        'column_case',
        'pk_pattern',
        'fk_pattern',
        'ix_pattern',
    }.issubset(rules_triggered)

    # 2. Save a persistent waiver for CustomerAccounts table_case
    waived = evaluate_or_apply_erd_standards(
        store,
        proc,
        design_id=design_id,
        actor_id=7,
        payload={
            'action': 'save_waivers',
            'waivers': [
                {
                    'rule_id': 'table_case',
                    'target': 'table:CustomerAccounts',
                    'reason': 'Legacy ERP view contract',
                }
            ],
        },
    )
    assert waived['waived_count'] == 1
    _verify_ddn_zero_diagnostics(waived['design']['version']['ddn_text'])

    # 3. Apply 1-click auto-fixes: fixes all non-waived items, preserves waived table name
    fixed = evaluate_or_apply_erd_standards(
        store,
        proc,
        design_id=design_id,
        actor_id=7,
        payload={'action': 'apply_fixes'},
    )
    assert fixed['fixed_count'] >= 5
    assert fixed['active_count'] == 0
    assert fixed['waived_count'] == 1
    _verify_ddn_zero_diagnostics(fixed['design']['version']['ddn_text'])

    state = inspect_erd_elements(store, design_id=design_id)
    t_names = {t['name'] for t in state['physical_tables']}
    assert 'CustomerAccounts' in t_names  # Waived -> preserved!
    assert 'order_headers' in t_names  # Non-waived -> auto-fixed!


def test_alter_plan_risks_migrations_operation_bus_and_env_matrix(tmp_path):
    store = DesignStore(db_path=tmp_path / 'designs.db')
    proc = StoreDDNProcess(store)
    bus = OperationBus()

    # v1 baseline schema
    imp = import_erd_external(
        store,
        proc,
        project_id='proj-deploy',
        actor_id=1,
        payload={
            'format': 'sql',
            'title': 'Billing Schema',
            'target_engine': 'postgresql',
            'sql': """
            CREATE TABLE customers (
                id BIGINT PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                legacy_token VARCHAR(64)
            );
            CREATE TABLE temp_staging (
                id BIGINT PRIMARY KEY
            );
            """,
        },
    )
    design_id = imp['design']['id']
    store.advance_status(design_id, 1, 'in_review', actor_id=1)
    store.accept_version(design_id, 1, actor_id=1, approval_ref='v1 baseline')

    # Mutate v2: drop temp_staging, drop legacy_token, alter email type, add invoices + FK
    state = inspect_erd_elements(store, design_id=design_id)
    cust_tbl = next(
        t for t in state['physical_tables'] if t['name'] == 'customers'
    )
    cust_tbl['fields'] = [
        f for f in cust_tbl['fields'] if f['name'] != 'legacy_token'
    ]
    for f in cust_tbl['fields']:
        if f['name'] == 'email':
            f['datatype'] = ' VARCHAR(120)'
    cust_tbl['fields'].append({
        'name': 'tenant_code',
        'datatype': 'VARCHAR(32)',
        'nullable': False,
    })
    new_tables = [
        cust_tbl,
        {
            'name': 'invoices',
            'engine': 'postgresql',
            'fields': [
                {'name': 'invoice_id', 'datatype': 'BIGINT', 'pk': True, 'nullable': False},
                {
                    'name': 'customer_id',
                    'datatype': 'BIGINT',
                    'nullable': False,
                    'references': 'customers.id',
                },
            ],
            'foreign_keys': [
                {
                    'name': 'fk_invoices_customers',
                    'columns': ['customer_id'],
                    'ref_table': 'customers',
                    'ref_columns': ['id'],
                }
            ],
        },
    ]
    mutate_erd_elements(
        store,
        proc,
        design_id=design_id,
        actor_id=1,
        payload={'physical_tables': new_tables, 'note': 'v2 schema evolution'},
    )

    # Preview alter plan across migration formats
    prev = plan_or_submit_erd_deployment(
        store,
        proc,
        design_id=design_id,
        actor_id=1,
        payload={
            'action': 'preview',
            'baseline_mode': 'active',
            'target_engine': 'postgresql',
            'migration_format': 'flyway',
        },
    )
    assert prev['plan']['requires_native_review'] is True
    assert prev['plan']['applied_immediately'] is False
    assert prev['risk_summary']['loses_data'] >= 2  # drop_table + drop_column
    assert prev['risk_summary']['may_fail_on_existing_data'] >= 1
    assert prev['risk_summary']['breaks_running_clients'] >= 2
    assert prev['risk_summary']['locks_or_copies_table'] >= 1
    assert prev['migration_sql'].startswith('-- File: V2__')
    assert '--liquibase formatted sql' in prev['migration_scripts']['liquibase']
    assert '-- atlas:pos' in prev['migration_scripts']['atlas']
    assert 'BEGIN;' in prev['migration_scripts']['plain_sql']
    assert [e['environment'] for e in prev['environments'][:3]] == [
        'dev',
        'staging',
        'prod',
    ]
    assert all(e['drift_status'] == 'not_deployed' for e in prev['environments'][:3])

    # Submit to OperationBus review -> lands in awaiting_approval, never executed!
    sub = plan_or_submit_erd_deployment(
        store,
        proc,
        design_id=design_id,
        actor_id=5,
        payload={
            'action': 'submit_review',
            'environment': 'staging',
            'target_engine': 'postgresql',
            'migration_format': 'liquibase',
            'approvers': ['dba-reviewer'],
            'operation_bus': bus,
        },
    )
    assert sub['status'] == 'awaiting_approval'
    assert sub['applied_immediately'] is False
    assert sub['statement_count'] >= 4
    op_record = bus.get_operation(sub['operation_id'], 'user:5')
    assert op_record['stage'] == 'awaiting_approval'
    assert op_record['request']['risk_class'] == 'destructive'
    # Attempting start before approval raises OperationStateError; approval moves to 'approved'
    with pytest.raises(OperationStateError):
        bus.start(sub['operation_id'], 'user:5')
    approved = bus.approve(sub['operation_id'], 'dba-reviewer')
    assert approved['stage'] == 'approved'
    assert approved['provider_operation'] is None

    # Record verified deployment in Dev (v2 -> in_sync) and Prod (v1 -> behind)
    rec_dev = plan_or_submit_erd_deployment(
        store,
        proc,
        design_id=design_id,
        actor_id=5,
        payload={
            'action': 'record_environment_deployment',
            'environment': 'dev',
            'deployed_version': 2,
            'target_engine': 'postgresql',
        },
    )
    rec_prod = plan_or_submit_erd_deployment(
        store,
        proc,
        design_id=design_id,
        actor_id=5,
        payload={
            'action': 'record_environment_deployment',
            'environment': 'prod',
            'deployed_version': 1,
            'target_engine': 'postgresql',
        },
    )
    env_by_id = {e['environment']: e for e in rec_prod['environments']}
    assert env_by_id['dev']['drift_status'] == 'in_sync'
    assert env_by_id['dev']['has_drift'] is False
    assert env_by_id['staging']['drift_status'] == 'not_deployed'
    assert env_by_id['prod']['drift_status'] == 'behind'
    assert env_by_id['prod']['deployed_version'] == 1

    # Also verify live catalog baseline mode
    cat_prev = plan_or_submit_erd_deployment(
        store,
        proc,
        design_id=design_id,
        actor_id=1,
        payload={
            'action': 'preview',
            'baseline_mode': 'catalog',
            'target_engine': 'postgresql',
            'catalog_tables': [
                {
                    'name': 'customers',
                    'columns': [
                        {'name': 'id', 'type': 'BIGINT', 'pk': True, 'nullable': False},
                    ],
                },
                {
                    'name': 'obsolete_audit',
                    'columns': [{'name': 'id', 'type': 'BIGINT', 'pk': True}],
                },
            ],
        },
    )
    cat_kinds = {d['change_kind'] for d in cat_prev['plan']['differences']}
    assert {'create_table', 'add_column', 'drop_table'}.issubset(cat_kinds)


def test_erd_phase1_and_phase2_flask_routes_end_to_end(tmp_path):
    app = Flask(__name__)
    app.secret_key = 'erd-ext-test-key'
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    app.config['CDEADMIN_DESIGN_STORE_PATH'] = str(tmp_path / 'erd_routes.db')
    init_routes_app(app)
    client = app.test_client()

    # 1. POST /erd/import
    imp_res = client.post(
        '/cdeadmin/api/projects/p1/erd/import',
        json={
            'format': 'dbml',
            'title': 'Route DBML Import',
            'dbml': """
            Table Accounts {
              AccountId int [pk]
              EmailAddr varchar(120) [not null]
            }
            """,
        },
    )
    assert imp_res.status_code == 200
    design_id = imp_res.get_json()['data']['design']['id']

    # 2. GET & POST /erd/elements
    get_el = client.get(
        f'/cdeadmin/api/projects/p1/designs/{design_id}/erd/elements'
    )
    assert get_el.status_code == 200
    assert len(get_el.get_json()['data']['physical_tables']) == 1

    post_el = client.post(
        f'/cdeadmin/api/projects/p1/designs/{design_id}/erd/elements',
        json={
            'operation': 'upsert_conceptual',
            'entity': {'name': 'Shipment'},
        },
    )
    assert post_el.status_code == 200
    assert any(
        c['name'] == 'Shipment'
        for c in post_el.get_json()['data']['elements']['conceptual_entities']
    )

    # 3. POST /erd/promote-whiteboard
    promo_res = client.post(
        f'/cdeadmin/api/projects/p1/designs/{design_id}/erd/promote-whiteboard',
        json={'target_engine': 'postgresql', 'save_version': True},
    )
    assert promo_res.status_code == 200
    assert promo_res.get_json()['data']['promoted_physical_count'] >= 2

    # 4. POST /erd/standards (check & apply_fixes)
    std_chk = client.post(
        f'/cdeadmin/api/projects/p1/designs/{design_id}/erd/standards',
        json={'action': 'check'},
    )
    assert std_chk.status_code == 200
    assert std_chk.get_json()['data']['active_count'] >= 2

    std_fix = client.post(
        f'/cdeadmin/api/projects/p1/designs/{design_id}/erd/standards',
        json={'action': 'apply_fixes'},
    )
    assert std_fix.status_code == 200
    assert std_fix.get_json()['data']['active_count'] == 0

    # 5. POST /erd/deploy (preview & submit_review)
    dep_prev = client.post(
        f'/cdeadmin/api/projects/p1/designs/{design_id}/erd/deploy',
        json={'action': 'preview', 'migration_format': 'atlas'},
    )
    assert dep_prev.status_code == 200
    assert '-- atlas:pos' in dep_prev.get_json()['data']['migration_sql']

    dep_sub = client.post(
        f'/cdeadmin/api/projects/p1/designs/{design_id}/erd/deploy',
        json={'action': 'submit_review', 'environment': 'dev'},
    )
    assert dep_sub.status_code == 200
    assert dep_sub.get_json()['data']['status'] == 'awaiting_approval'
