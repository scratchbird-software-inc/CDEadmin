##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Regression tests for the ScratchRobin DDN design store (designs.db)."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess

import duckdb
import pytest

from pgadmin.cdeadmin.design_store import (
    MAX_BLOB_BYTES,
    DesignStore,
    DesignStoreConflict,
    DesignStoreError,
    DesignStoreForbidden,
    DesignStoreNotFound,
    deterministic_uuid7,
    is_uuid7,
    sha256_text,
    uuid7,
)
from pgadmin.cdeadmin.workspace import (
    ddn_source as ddn,
    duckdb_erd,
    firebird_erd,
    mysql_erd,
    sqlite_erd,
)
from pgadmin.cdeadmin.providers.duckdb.catalog import (
    capture as capture_duckdb_catalog,
)
from pgadmin.cdeadmin.providers.sqlite.provider import (
    _resources as capture_sqlite_resources,
)

_READ_RELATIONS_MJS = (
    Path(__file__).resolve().parents[2]
    / 'web/pgadmin/cdeadmin/workspace/ddn/read_relations.mjs'
)

SAMPLE_DDN = """version ddn-next-1
// ScratchRobin mapping: scratchrobin.erd.design

element "customers" as "table"
    with
        id "customers"
        title "customers"
        members
            item
                id "customers_id"

element "customers_id" as "field"
    with
        id "customers_id"
        title "id"
        content
            datatype "INTEGER"
            nullable false

view "main" as "ddn@1"
    with
        id "main"
        title "Main ERD"
        selection
            include
                item
                    id "customers"
    use "customers" named "appearance:main:customers"
"""


def _run_read_relations(engine: str, workspace: dict) -> dict:
    proc = subprocess.run(
        [
            ddn.node_executable(),
            ddn.NODE_HEAP_OPTION,
            str(_READ_RELATIONS_MJS),
            engine,
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
    return json.loads(proc.stdout)


def test_uuid7_format_monotonicity_and_deterministic_backfill():
    ids = [uuid7() for _ in range(200)]
    assert all(is_uuid7(item) for item in ids)
    assert len(set(ids)) == 200
    assert ids == sorted(ids)

    det_a = deterministic_uuid7(
        'sqlite:ep1:db1:table:customers', 1700000000000
    )
    det_b = deterministic_uuid7(
        'sqlite:ep1:db1:table:customers', 1700000000000
    )
    det_c = deterministic_uuid7('sqlite:ep1:db1:table:orders', 1700000000000)
    assert is_uuid7(det_a)
    assert det_a == det_b
    assert det_a != det_c
    assert not is_uuid7('not-a-uuid')
    assert not is_uuid7('550e8400-e29b-41d4-a716-446655440000')


def test_store_schema_and_immutability_trigger(tmp_path):
    db_file = tmp_path / 'designs.db'
    store = DesignStore(db_path=db_file)
    created = store.create_design(
        project_id='proj-1',
        key='crm-erd',
        kind='erd',
        title='CRM Data Model',
        ddn_text=SAMPLE_DDN,
        actor_id=7,
        note='Initial sketch',
    )
    assert db_file.is_file()
    assert is_uuid7(created['id'])
    assert created['head_version'] == 1
    assert created['active_version'] is None
    assert created['version']['status'] == 'draft'
    assert created['version']['actor_id'] == 7
    assert all(is_uuid7(elem['id']) for elem in created['elements'])
    assert {elem['name'] for elem in created['elements']} == {
        'customers',
        'id',
    }

    conn = sqlite3.connect(str(db_file))
    try:
        cols = {
            row[1]
            for row in conn.execute('PRAGMA table_info(design_version)')
        }
        assert 'ddn_text' in cols
        assert 'layout_text' not in cols
        with pytest.raises(
            sqlite3.IntegrityError,
            match='design_version content is immutable',
        ):
            conn.execute(
                'UPDATE design_version SET ddn_text = ? WHERE design_id = ?',
                ('tampered', created['id']),
            )
    finally:
        conn.close()


def test_save_points_acceptance_conflicts_rollback_and_branch(tmp_path):
    store = DesignStore(db_path=tmp_path / 'designs.db')
    design = store.create_design(
        project_id='proj-cube',
        key='sales-cube',
        kind='cube',
        title='Sales Cube',
        ddn_text=SAMPLE_DDN,
        actor_id=10,
    )
    did = design['id']

    with pytest.raises(DesignStoreError, match='must be in_review'):
        store.accept_version(did, 1, actor_id=10)

    store.advance_status(did, 1, 'in_progress', actor_id=10)
    in_rev = store.advance_status(did, 1, 'in_review', actor_id=10)
    assert in_rev['version']['status'] == 'in_review'

    with pytest.raises(DesignStoreForbidden):
        store.accept_version(did, 1, actor_id=10, authorized=False)

    accepted = store.accept_version(
        did, 1, actor_id=99, approval_ref='security:role:architect'
    )
    assert accepted['active_version'] == 1
    assert accepted['version']['status'] == 'accepted'
    assert accepted['version']['accepted_by'] == 99
    assert accepted['version']['approval_ref'] == 'security:role:architect'

    branched = store.branch_draft_from_accepted(
        did, actor_id=10, note='v2 draft'
    )
    assert branched['head_version'] == 2
    assert branched['version']['base_version'] == 1
    assert branched['version']['status'] == 'draft'

    store.advance_status(did, 2, 'in_review', actor_id=10)
    store.accept_version(did, 2, actor_id=99)
    assert store.get_design(did)['active_version'] == 2

    with pytest.raises(
        DesignStoreConflict, match='active version advanced to 2'
    ):
        store.save_version(
            did,
            expected_head_version=2,
            ddn_text=SAMPLE_DDN + '\n// concurrent edit from v1\n',
            actor_id=11,
            base_version=1,
        )

    noted = store.save_version(
        did,
        expected_head_version=2,
        ddn_text=SAMPLE_DDN + '\n// concurrent edit noted\n',
        actor_id=11,
        base_version=1,
        status='in_review',
        note='Stale draft saved with conflict note',
        allow_conflict_note=True,
    )
    assert noted['head_version'] == 3
    assert '[conflicts recorded at save:' in noted['version']['note']

    with pytest.raises(
        DesignStoreConflict, match='reconcile via DDN diff before accepting'
    ):
        store.accept_version(did, 3, actor_id=99)

    returned = store.return_accepted_version(
        did, 2, actor_id=99, target_status='in_progress'
    )
    assert returned['version']['status'] == 'in_progress'
    assert returned['version']['returned_by'] == 99
    assert returned['active_version'] == 1

    rolled = store.rollback_to_version(did, 1, actor_id=99)
    assert rolled['head_version'] == 4
    assert rolled['version']['origin'] == 'rollback:1'
    assert len(store.list_versions(did)) == 4


def test_resource_identity_rename_drop_suspect_and_confirmation(tmp_path):
    store = DesignStore(db_path=tmp_path / 'designs.db')
    res = store.register_resource_identity(
        engine='sqlite',
        endpoint_id='ep-1',
        database_target_id='main',
        resource_kind='table',
        resource_id='sqlite:table:main.customers',
    )
    assert is_uuid7(res['id'])

    design = store.create_design(
        project_id='proj-erd',
        key='main-erd',
        kind='erd',
        title='Main ERD',
        ddn_text=SAMPLE_DDN,
        actor_id=1,
    )
    did = design['id']
    table_elem = next(
        e for e in design['elements'] if e['role'] == 'table'
    )
    binding = store.add_binding(
        design_id=did,
        element_id=table_elem['id'],
        target_kind='resource',
        target_ref=res['id'],
        target_engine='sqlite',
        target_endpoint_id='ep-1',
        target_database_target_id='main',
        state='valid',
    )
    assert is_uuid7(binding['id'])
    assert binding['state'] == 'valid'

    rename_out = store.record_resource_rename(
        engine='sqlite',
        endpoint_id='ep-1',
        database_target_id='main',
        old_resource_id='sqlite:table:main.customers',
        new_resource_id='sqlite:table:main.clients',
    )
    assert rename_out['suspect_bindings_marked'] == 1
    suspect_list = store.list_bindings(did, state='suspect')
    assert len(suspect_list) == 1
    assert suspect_list[0]['state_reason'] == 'target renamed'

    store.advance_status(did, 1, 'in_review', actor_id=1)
    with pytest.raises(
        DesignStoreConflict, match='Cannot accept while bindings are suspect'
    ):
        store.accept_version(did, 1, actor_id=1)

    confirmed = store.confirm_binding(binding['id'], actor_id=5)
    assert confirmed['state'] == 'valid'
    assert confirmed['confirmed_by'] == 5

    accepted = store.accept_version(did, 1, actor_id=1)
    assert accepted['active_version'] == 1

    drop_out = store.record_resource_drop(
        engine='sqlite',
        endpoint_id='ep-1',
        database_target_id='main',
        resource_id='sqlite:table:main.clients',
    )
    assert drop_out['suspect_bindings_marked'] == 1
    assert store.list_bindings(did, state='suspect')[0]['state_reason'] == (
        'target dropped'
    )


def test_asset_blob_cap_git_sync_dependencies_deployments_and_fts(tmp_path):
    store = DesignStore(db_path=tmp_path / 'designs.db')
    png_bytes = b'\x89PNG\r\n\x1a\nfake-screenshot-payload'
    blob = store.put_blob('image/png', png_bytes)
    assert len(blob['sha256']) == 64
    assert store.get_blob(blob['sha256'])['bytes'] == png_bytes

    with pytest.raises(DesignStoreError, match='exceeds the 16 MiB cap'):
        store.put_blob('image/png', b'x' * (MAX_BLOB_BYTES + 1))

    q_design = store.create_design(
        project_id='proj-bi',
        key='q-revenue',
        kind='question',
        title='Monthly Revenue Question',
        ddn_text=SAMPLE_DDN,
        actor_id=2,
        note='quarterly revenue metric',
    )
    d_design = store.create_design(
        project_id='proj-bi',
        key='dash-exec',
        kind='dashboard',
        title='Executive Dashboard',
        ddn_text=SAMPLE_DDN,
        actor_id=2,
    )
    store.attach_blob(
        d_design['id'], 1, 'screenshots/wireframe.png', blob['sha256']
    )
    deps = store.set_dependencies(
        d_design['id'],
        1,
        [{'depends_on_design_id': q_design['id'], 'depends_on_version': 1}],
    )
    assert len(deps) == 1
    assert deps[0]['depends_on_design_id'] == q_design['id']

    dep_rec = store.record_deployment(
        design_id=q_design['id'],
        deployed_version=1,
        engine='sqlite',
        endpoint_id='ep-1',
        database_target_id='main',
        plan_sha256='a' * 64,
        target_fingerprint='b' * 64,
        applied_by=2,
    )
    assert dep_rec['deployed_version'] == 1
    assert len(store.list_deployments(q_design['id'])) == 1

    hits = store.search('quarterly', project_id='proj-bi')
    assert [h['id'] for h in hits] == [q_design['id']]
    elem_hits = store.search('customers', project_id='proj-bi')
    assert len(elem_hits) == 2

    git_repo = tmp_path / 'git-designs'
    git_repo.mkdir()
    subprocess.run(
        ['git', '-C', str(git_repo), 'init', '-b', 'main'],
        check=True,
        capture_output=True,
    )
    store.link_git(
        q_design['id'],
        repository='local/designs',
        path='bi/q-revenue.ddn',
        branch='main',
    )
    pushed = store.export_to_git(q_design['id'], git_repo, commit=True)
    assert pushed['sync_state'] == 'synced'
    assert pushed['last_pushed_commit']

    drift_clean = store.check_git_drift(q_design['id'], repo_root=git_repo)
    assert drift_clean['sync_state'] == 'synced'

    ddn_file = git_repo / 'bi/q-revenue.ddn'
    ddn_file.write_text(
        ddn_file.read_text(encoding='utf-8') + '\n// edited in git\n',
        encoding='utf-8',
    )
    drift_remote = store.check_git_drift(q_design['id'], repo_root=git_repo)
    assert drift_remote['sync_state'] == 'out_of_sync'

    pulled = store.import_from_git(
        q_design['id'], git_repo, actor_id=3, note='Pulled from git'
    )
    assert pulled['head_version'] == 2
    assert pulled['git_link']['sync_state'] == 'synced'
    assert pulled['version']['ddn_sha256'] == sha256_text(
        ddn_file.read_text(encoding='utf-8')
    )


def test_live_sqlite_and_duckdb_physical_erd_bridge(tmp_path):
    store = DesignStore(db_path=tmp_path / 'designs.db')

    # 1. Live SQLite catalog -> physical ERD workspace -> DesignStore -> DDN
    sqlite_path = tmp_path / 'demo_sqlite.db'
    sconn = sqlite3.connect(str(sqlite_path))
    try:
        sconn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK (length(status) > 0)
            );
            CREATE TABLE work_orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL
                    REFERENCES customers(id) ON DELETE CASCADE,
                summary TEXT NOT NULL
            );
            CREATE INDEX idx_work_orders_customer
                ON work_orders(customer_id);
            """
        )
        sconn.commit()
        sqlite_resources = capture_sqlite_resources(
            sconn, {'capability_generation': 'gen-1'}
        )
    finally:
        sconn.close()

    sqlite_diag = sqlite_erd.build_diagram(
        sqlite_resources,
        {'endpoint_id': 'ep-sqlite', 'database_target_id': 'main'},
    )
    assert sqlite_diag is not None
    sqlite_design = store.import_physical_erd_workspace(
        project_id='demo',
        key='sqlite-physical',
        title='SQLite Physical ERD',
        workspace=sqlite_diag['snapshot'],
        actor_id=1,
    )
    assert sqlite_design['kind'] == 'erd'
    assert all(is_uuid7(e['id']) for e in sqlite_design['elements'])
    assert all(b['state'] == 'valid' for b in sqlite_design['bindings'])
    exported_sqlite = store.export_ddn(
        sqlite_design['id'], entry='relations.ddn'
    )
    parsed_sqlite = _run_read_relations('sqlite', exported_sqlite['workspace'])
    assert len(parsed_sqlite['rows']) >= 2
    assert len(parsed_sqlite['field_records']) == 6

    # 2. Live DuckDB catalog -> physical ERD workspace -> DesignStore -> DDN
    duck_path = tmp_path / 'demo_duck.duckdb'
    dconn = duckdb.connect(str(duck_path))
    try:
        dconn.execute(
            """
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                name VARCHAR NOT NULL UNIQUE
            );
            CREATE TABLE assets (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                tag VARCHAR NOT NULL CHECK (length(tag) > 0)
            );
            CREATE INDEX idx_assets_tag ON assets(tag);
            """
        )
        duck_capture = capture_duckdb_catalog(dconn)
    finally:
        dconn.close()

    duck_diag = duckdb_erd.build_diagram(
        duck_capture['resources'],
        {'endpoint_id': 'ep-duck', 'database_target_id': 'demo_duck'},
    )
    assert duck_diag is not None
    duck_design = store.import_physical_erd_workspace(
        project_id='demo',
        key='duckdb-physical',
        title='DuckDB Physical ERD',
        workspace=duck_diag['snapshot'],
        actor_id=1,
    )
    assert all(is_uuid7(e['id']) for e in duck_design['elements'])
    assert all(b['state'] == 'valid' for b in duck_design['bindings'])
    exported_duck = store.export_ddn(
        duck_design['id'], entry='relations.ddn'
    )
    parsed_duck = _run_read_relations('duckdb', exported_duck['workspace'])
    assert len(parsed_duck['rows']) >= 2
    assert len(parsed_duck['field_records']) == 5


def test_firebird_and_mysql_family_physical_erd_bridge(tmp_path):
    store = DesignStore(db_path=tmp_path / 'designs.db')

    # Firebird 5 physical ERD fixture
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
    fb_diag = firebird_erd.build_diagram(
        fb_resources,
        {'endpoint_id': 'ep-fb', 'database_target_id': 'fb-main'},
    )
    fb_design = store.import_physical_erd_workspace(
        project_id='demo',
        key='firebird-physical',
        title='Firebird Physical ERD',
        workspace=fb_diag['snapshot'],
        actor_id=1,
    )
    assert all(is_uuid7(e['id']) for e in fb_design['elements'])
    assert all(b['state'] == 'valid' for b in fb_design['bindings'])
    exported_fb = store.export_ddn(fb_design['id'], entry='relations.ddn')
    parsed_fb = _run_read_relations('firebird', exported_fb['workspace'])
    assert len(parsed_fb['rows']) >= 2
    assert len(parsed_fb['field_records']) == 2

    # MySQL & MariaDB physical ERD bridge
    for engine in ('mysql', 'mariadb'):
        my_resources = [
            {
                'resource_id': f'{engine}:database:crm',
                'resource_kind': 'database',
                'display_name': 'crm',
                'display_path': ['crm'],
                'system': False,
                'native': {'database': 'crm', 'sql_mode': ''},
            },
            {
                'resource_id': f'{engine}:table:crm.customers',
                'resource_kind': 'table',
                'display_name': 'customers',
                'display_path': ['crm', 'customers'],
                'system': False,
                'native': {
                    'database': 'crm',
                    'create_statement': (
                        'CREATE TABLE `customers` (\n'
                        '  `id` int NOT NULL,\n'
                        '  PRIMARY KEY (`id`)\n'
                        ') ENGINE=InnoDB'
                    ),
                    'children': {
                        'COLUMNS': [
                            {
                                'column_name': 'id',
                                'ordinal_position': 1,
                                'column_type': 'int',
                                'is_nullable': 'NO',
                            }
                        ],
                        'KEY_COLUMN_USAGE': [],
                    },
                },
            },
        ]
        my_diag = mysql_erd.build_diagram(
            my_resources,
            {'endpoint_id': f'ep-{engine}', 'database_target_id': 'crm'},
            engine=engine,
        )
        my_design = store.import_physical_erd_workspace(
            project_id='demo',
            key=f'{engine}-physical',
            title=f'{engine.upper()} Physical ERD',
            workspace=my_diag['snapshot'],
            actor_id=1,
        )
        assert all(is_uuid7(e['id']) for e in my_design['elements'])
        assert all(b['state'] == 'valid' for b in my_design['bindings'])
        exported_my = store.export_ddn(my_design['id'], entry='relations.ddn')
        parsed_my = _run_read_relations(engine, exported_my['workspace'])
        assert len(parsed_my['rows']) >= 1
        assert len(parsed_my['field_records']) == 1
