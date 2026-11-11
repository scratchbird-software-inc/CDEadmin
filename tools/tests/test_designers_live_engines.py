##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Live engine & production create_app() qualification for DDN designers.

Covers owner decisions A2, A5-A7, C3, E1-E2, and F1 across:
- Production ``pgadmin.create_app()`` mounting ``designs.db`` in ``DATA_DIR``
- Live SQLite (stdlib ``sqlite3``)
- Live DuckDB (``duckdb``)
- Live Firebird embedded (``firebird.driver.create_database``)
- Live Firebird 5 network (``127.0.0.1/53050``, read-only when running)
- Live MySQL 9.7 (``127.0.0.1:53306``, read-only when running)
- Live MariaDB 12.2 (``127.0.0.1:53307``, read-only when running)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys

import duckdb
import pytest

from pgadmin.cdeadmin.design_store import (
    CubeDesignSync,
    DesignStore,
    ScreenMeshSync,
    StoreDDNProcess,
    convert_erd_design_engine,
    default_cube_model,
    default_question_model,
    default_screen_mesh_model,
    execute_bi_question_connection,
    is_uuid7,
    preview_cube_materialization_plan,
    uuid7,
)
from pgadmin.cdeadmin.providers.duckdb.catalog import (
    capture as capture_duckdb_catalog,
)
from pgadmin.cdeadmin.providers.sqlite.provider import (
    _resources as capture_sqlite_resources,
)
from pgadmin.cdeadmin.workspace import (
    duckdb_erd,
    firebird_erd,
    mysql_erd,
    sqlite_erd,
)

ROOT = Path(__file__).resolve().parents[2]
DEMO_PASSWORD = os.environ.get(
    'CDEADMIN_DEMO_PASSWORD', 'CDEadminDemo-2026!'
)


def _port_open(host: str, port: int) -> bool:
    sock = socket.socket()
    sock.settimeout(0.5)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _capture_live_firebird_resources(conn) -> list[dict]:
    """Read live Firebird system catalogs into firebird_erd resource dicts."""
    resources: list[dict] = []
    cur = conn.cursor()
    cur.execute(
        'SELECT TRIM(RDB$RELATION_NAME), COALESCE(RDB$RELATION_TYPE, 0) '
        'FROM RDB$RELATIONS '
        'WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0 '
        'AND RDB$VIEW_BLR IS NULL '
        'ORDER BY RDB$RELATION_NAME'
    )
    tables = cur.fetchall()
    for rel_name, rel_type in tables:
        resources.append({
            'resource_id': f'firebird:table:{rel_name}',
            'resource_kind': 'table',
            'display_name': rel_name,
            'display_path': [rel_name],
            'system': False,
            'native': {
                'relation_name': rel_name,
                'relation_type': int(rel_type or 0),
            },
        })
        cur.execute(
            'SELECT TRIM(rf.RDB$FIELD_NAME), COALESCE(rf.RDB$FIELD_POSITION, '
            '0), COALESCE(f.RDB$FIELD_TYPE, 8), '
            'COALESCE(f.RDB$FIELD_SUB_TYPE, 0), '
            'COALESCE(f.RDB$FIELD_LENGTH, 4), '
            'COALESCE(f.RDB$FIELD_SCALE, 0), COALESCE(rf.RDB$NULL_FLAG, 0) '
            'FROM RDB$RELATION_FIELDS rf '
            'JOIN RDB$FIELDS f ON rf.RDB$FIELD_SOURCE = f.RDB$FIELD_NAME '
            'WHERE TRIM(rf.RDB$RELATION_NAME) = ? '
            'ORDER BY rf.RDB$FIELD_POSITION',
            [rel_name],
        )
        for (
            fname, pos, ftype, fsub, flen, fscale, nflag
        ) in cur.fetchall():
            resources.append({
                'resource_id': f'firebird:column:{rel_name}.{fname}',
                'resource_kind': 'column',
                'display_name': fname,
                'display_path': [rel_name, fname],
                'system': False,
                'native': {
                    'position': int(pos),
                    'field_type': int(ftype),
                    'field_sub_type': int(fsub),
                    'field_length': int(flen),
                    'field_scale': int(fscale),
                    'not_null': int(nflag),
                },
            })
    cur.execute(
        'SELECT TRIM(i.RDB$INDEX_NAME), TRIM(i.RDB$RELATION_NAME), '
        'COALESCE(i.RDB$UNIQUE_FLAG, 0) '
        'FROM RDB$INDICES i '
        'JOIN RDB$RELATIONS r ON r.RDB$RELATION_NAME = i.RDB$RELATION_NAME '
        'WHERE COALESCE(r.RDB$SYSTEM_FLAG, 0) = 0 '
        'ORDER BY i.RDB$INDEX_NAME'
    )
    for idx_name, rel_name, uflag in cur.fetchall():
        cur.execute(
            'SELECT TRIM(RDB$FIELD_NAME), COALESCE(RDB$FIELD_POSITION, 0) '
            'FROM RDB$INDEX_SEGMENTS WHERE TRIM(RDB$INDEX_NAME) = ? '
            'ORDER BY RDB$FIELD_POSITION',
            [idx_name],
        )
        segs = [
            {'field_name': seg_f, 'position': int(seg_p)}
            for seg_f, seg_p in cur.fetchall()
        ]
        resources.append({
            'resource_id': f'firebird:index:{idx_name}',
            'resource_kind': 'index',
            'display_name': idx_name,
            'display_path': [rel_name, idx_name],
            'system': False,
            'native': {
                'index_name': idx_name,
                'relation_name': rel_name,
                'unique_flag': int(uflag),
                'segments': segs,
            },
        })
    cur.execute(
        'SELECT TRIM(rc.RDB$CONSTRAINT_NAME), TRIM(rc.RDB$RELATION_NAME), '
        'TRIM(rc.RDB$CONSTRAINT_TYPE), TRIM(COALESCE(rc.RDB$INDEX_NAME, '
        "'')), TRIM(COALESCE(refc.RDB$CONST_NAME_UQ, '')), "
        "TRIM(COALESCE(refc.RDB$UPDATE_RULE, 'RESTRICT')), "
        "TRIM(COALESCE(refc.RDB$DELETE_RULE, 'RESTRICT')) "
        'FROM RDB$RELATION_CONSTRAINTS rc '
        'LEFT JOIN RDB$REF_CONSTRAINTS refc '
        'ON refc.RDB$CONSTRAINT_NAME = rc.RDB$CONSTRAINT_NAME '
        'JOIN RDB$RELATIONS r ON r.RDB$RELATION_NAME = rc.RDB$RELATION_NAME '
        'WHERE COALESCE(r.RDB$SYSTEM_FLAG, 0) = 0 '
        "AND TRIM(rc.RDB$CONSTRAINT_TYPE) IN ('PRIMARY KEY', 'FOREIGN KEY') "
        'ORDER BY rc.RDB$CONSTRAINT_NAME'
    )
    rows = cur.fetchall()
    pk_lookup: dict[str, tuple[str, str]] = {}
    for cname, rname, ctype, iname, *_ in rows:
        if ctype == 'PRIMARY KEY':
            pk_lookup[cname] = (rname, iname)
    for cname, rname, ctype, iname, uq_const, urule, drule in rows:
        native = {
            'constraint_name': cname,
            'relation_name': rname,
            'constraint_type': ctype,
            'index_name': iname,
        }
        if ctype == 'FOREIGN KEY' and uq_const in pk_lookup:
            ref_rel, ref_idx = pk_lookup[uq_const]
            native['referenced_relation'] = ref_rel
            native['referenced_index'] = ref_idx
            native['update_rule'] = urule
            native['delete_rule'] = drule
        resources.append({
            'resource_id': f'firebird:constraint:{cname}',
            'resource_kind': 'constraint',
            'display_name': cname,
            'display_path': [rname, cname],
            'system': False,
            'native': native,
        })
    cur.close()
    return resources


def _capture_live_mysql_family_resources(
    conn, engine: str, db_name: str
) -> list[dict]:
    """Read live MySQL / MariaDB INFORMATION_SCHEMA into mysql_erd dicts."""
    resources: list[dict] = [{
        'resource_id': f'{engine}:database:{db_name}',
        'resource_kind': 'database',
        'display_name': db_name,
        'display_path': [db_name],
        'system': False,
        'native': {'database': db_name, 'sql_mode': ''},
    }]
    cur = conn.cursor()
    cur.execute(
        'SELECT TABLE_NAME, COALESCE(ENGINE, \'InnoDB\') '
        'FROM INFORMATION_SCHEMA.TABLES '
        'WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = \'BASE TABLE\' '
        'ORDER BY TABLE_NAME',
        (db_name,),
    )
    tables = cur.fetchall()
    for tname, _storage_engine in tables:
        cur.execute(f'SHOW CREATE TABLE `{db_name}`.`{tname}`')
        show_row = cur.fetchone()
        create_stmt = (
            str(show_row[1]) if show_row and len(show_row) > 1 else ''
        )
        cur.execute(
            'SELECT COLUMN_NAME, ORDINAL_POSITION, COLUMN_TYPE, IS_NULLABLE '
            'FROM INFORMATION_SCHEMA.COLUMNS '
            'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s '
            'ORDER BY ORDINAL_POSITION',
            (db_name, tname),
        )
        cols = [
            {
                'column_name': cname,
                'ordinal_position': int(pos),
                'column_type': ctype,
                'is_nullable': is_null,
            }
            for cname, pos, ctype, is_null in cur.fetchall()
        ]
        cur.execute(
            'SELECT CONSTRAINT_NAME, COLUMN_NAME, ORDINAL_POSITION, '
            'REFERENCED_TABLE_SCHEMA, REFERENCED_TABLE_NAME, '
            'REFERENCED_COLUMN_NAME '
            'FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE '
            'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s '
            'ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION',
            (db_name, tname),
        )
        kcu = [
            {
                'constraint_name': cname,
                'column_name': col_n,
                'ordinal_position': int(pos),
                'referenced_table_schema': ref_db,
                'referenced_table_name': ref_tbl,
                'referenced_column_name': ref_col,
            }
            for cname, col_n, pos, ref_db, ref_tbl, ref_col in cur.fetchall()
        ]
        resources.append({
            'resource_id': f'{engine}:table:{db_name}.{tname}',
            'resource_kind': 'table',
            'display_name': tname,
            'display_path': [db_name, tname],
            'system': False,
            'native': {
                'database': db_name,
                'create_statement': create_stmt,
                'children': {
                    'COLUMNS': cols,
                    'KEY_COLUMN_USAGE': kcu,
                },
            },
        })
    cur.close()
    return resources


def test_production_create_app_mounts_design_store_in_data_dir(tmp_path):
    """Verify real pgadmin.create_app() wires designs.db and HTTP routes."""
    data = tmp_path / 'data'
    for sub in ('sessions', 'storage', 'azure'):
        (data / sub).mkdir(parents=True, exist_ok=True)
    isolated = {
        'SERVER_MODE': False,
        'TESTING': True,
        'LOGIN_DISABLED': True,
        'WTF_CSRF_ENABLED': False,
        'CONFIG_DATABASE_URI': '',
        'DATA_DIR': str(data),
        'SQLITE_PATH': str(data / 'cdeadmin_test.db'),
        'CDEADMIN_OPERATION_STORE_PATH': str(data / 'operations.json'),
        'LOG_FILE': str(data / 'application.log'),
        'SESSION_DB_PATH': str(data / 'sessions'),
        'STORAGE_DIR': str(data / 'storage'),
        'AZURE_CREDENTIAL_CACHE_DIR': str(data / 'azure'),
        'KERBEROS_CCACHE_DIR': str(data / 'kerberos'),
    }
    (tmp_path / 'config_local.py').write_text(
        ''.join(f'{k} = {v!r}\n' for k, v in isolated.items()),
        encoding='utf-8',
    )
    probe = (
        'import json\n'
        'from pgadmin import create_app\n'
        'app = create_app()\n'
        'app.PGADMIN_INT_KEY = ""\n'
        'app.config["WTF_CSRF_ENABLED"] = False\n'
        'store = app.extensions["cdeadmin_design_store"]\n'
        'client = app.test_client()\n'
        'forms_r = client.get("/cdeadmin/api/ui/descriptor-forms")\n'
        'erd_r = client.post(\n'
        '    "/cdeadmin/api/projects/qual/designs",\n'
        '    json={\n'
        '        "mode": "create_erd",\n'
        '        "key": "m1",\n'
        '        "title": "Qual Model",\n'
        '    },\n'
        ')\n'
        'list_r = client.get("/cdeadmin/api/projects/qual/designs")\n'
        'print(json.dumps({\n'
        '    "db_path": str(store.db_path),\n'
        '    "forms_status": forms_r.status_code,\n'
        '    "forms_count": len(forms_r.get_json()["data"]),\n'
        '    "erd_status": erd_r.status_code,\n'
        '    "list_count": len(list_r.get_json()["data"]),\n'
        '}))\n'
    )
    completed = subprocess.run(
        [sys.executable, '-c', probe],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
        env={
            **{
                k: v for k, v in os.environ.items()
                if k not in (
                    'FLASK_RUN_FROM_CLI',
                    'CDEADMIN_DESIGN_STORE_PATH',
                )
            },
            'PYTHONPATH': os.pathsep.join([str(tmp_path), str(ROOT / 'web')]),
        },
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    out = json.loads(completed.stdout.strip().splitlines()[-1])
    assert out['db_path'] == str(data / 'designs.db')
    assert (data / 'designs.db').is_file()
    assert out['forms_status'] == 200
    assert out['forms_count'] >= 122
    assert out['erd_status'] == 200
    assert out['list_count'] == 1


def test_live_sqlite_duckdb_and_firebird_embedded_qualification(tmp_path):
    """Qualify ERD, conversion, BI SBsql, Cube and Screen Mesh on 3 engines."""
    store = DesignStore(db_path=tmp_path / 'designs.db')
    proc = StoreDDNProcess(store)
    mesh_sync = ScreenMeshSync(store, proc)
    cube_sync = CubeDesignSync(store, proc)

    # 1. Live SQLite
    sq_path = tmp_path / 'field_service.sqlite'
    sconn = sqlite3.connect(sq_path)
    try:
        sconn.executescript(
            'PRAGMA foreign_keys = ON;'
            'CREATE TABLE customers ('
            '  customer_id INTEGER PRIMARY KEY,'
            '  name TEXT NOT NULL,'
            '  region TEXT NOT NULL'
            ');'
            'CREATE TABLE work_orders ('
            '  work_order_id INTEGER PRIMARY KEY,'
            '  customer_id INTEGER NOT NULL REFERENCES customers(customer_id),'
            '  status TEXT NOT NULL,'
            '  priority INTEGER NOT NULL'
            ');'
            "INSERT INTO customers VALUES (1, 'Northwind', 'ON'),"
            " (2, 'Contoso', 'QC');"
            "INSERT INTO work_orders VALUES (101, 1, 'open', 3),"
            " (102, 1, 'open', 5), (103, 2, 'closed', 1);"
        )
        sq_res = capture_sqlite_resources(sconn, {})
        sq_diag = sqlite_erd.build_diagram(
            sq_res,
            {'endpoint_id': 'ep-sqlite', 'database_target_id': 'sq-main'},
        )
        sq_erd = store.import_physical_erd_workspace(
            project_id='live',
            key='sqlite-erd',
            title='Live SQLite ERD',
            workspace=sq_diag['snapshot'],
            actor_id=1,
        )
        assert all(is_uuid7(e['id']) for e in sq_erd['elements'])

        # Neutral-logical conversion SQLite -> DuckDB & Firebird
        conv_duck = convert_erd_design_engine(
            sq_erd['version']['ddn_text'],
            source_engine='sqlite',
            target_engine='duckdb',
            strict=False,
        )
        assert conv_duck['loss_report']['target_engine'] == 'duckdb'

        # Live parameterized BI SBsql execution on SQLite
        q_sq = default_question_model(
            name='Open SQLite Work Orders',
            endpoint_id='ep-sqlite',
            sbsql={
                'from': {
                    'relation': ['main', 'work_orders'],
                    'alias': 'wo',
                },
                'columns': [{'column': ['wo', 'status'], 'alias': 'status'}],
                'measures': [{
                    'function': 'sum',
                    'column': ['wo', 'priority'],
                    'alias': 'priority_sum',
                }],
                'filters': [{
                    'column': ['wo', 'status'],
                    'operator': 'eq',
                    'parameter': 'status_p',
                }],
                'limit': 10,
            },
            parameters=[{
                'id': 'status_p',
                'name': 'Status',
                'type': 'string',
                'default': 'open',
            }],
        )
        exec_sq = execute_bi_question_connection(
            sconn,
            q_sq,
            dialect='sqlite',
            parameter_values={'status_p': 'open'},
        )
        assert exec_sq['rows'] == [['open', 8]]
    finally:
        sconn.close()

    # 2. Live DuckDB
    dk_path = tmp_path / 'field_service.duckdb'
    dconn = duckdb.connect(str(dk_path))
    try:
        dconn.execute('CREATE SCHEMA service')
        dconn.execute(
            'CREATE TABLE service.customers ('
            'customer_id INTEGER PRIMARY KEY, name VARCHAR NOT NULL)'
        )
        dconn.execute(
            'CREATE TABLE service.work_orders ('
            'work_order_id INTEGER PRIMARY KEY, '
            'customer_id INTEGER REFERENCES service.customers(customer_id), '
            'status VARCHAR, priority INTEGER)'
        )
        dconn.execute(
            "INSERT INTO service.customers VALUES (1, 'Northwind')"
        )
        dconn.execute(
            "INSERT INTO service.work_orders VALUES "
            "(101, 1, 'open', 4), (102, 1, 'scheduled', 2)"
        )
        dk_res = capture_duckdb_catalog(dconn)['resources']
        dk_diag = duckdb_erd.build_diagram(
            dk_res,
            {'endpoint_id': 'ep-duck', 'database_target_id': 'dk-main'},
        )
        dk_erd = store.import_physical_erd_workspace(
            project_id='live',
            key='duckdb-erd',
            title='Live DuckDB ERD',
            workspace=dk_diag['snapshot'],
            actor_id=1,
        )
        assert any(b['state'] == 'valid' for b in dk_erd['bindings'])
        q_dk = default_question_model(
            name='DuckDB Open Orders',
            endpoint_id='ep-duck',
            sbsql={
                'from': {
                    'relation': ['service', 'work_orders'],
                    'alias': 'wo',
                },
                'columns': [{'column': ['wo', 'status'], 'alias': 'status'}],
                'measures': [{
                    'function': 'max',
                    'column': ['wo', 'priority'],
                    'alias': 'max_priority',
                }],
                'filters': [{
                    'column': ['wo', 'status'],
                    'operator': 'eq',
                    'parameter': 'st',
                }],
                'limit': 5,
            },
            parameters=[{'id': 'st', 'name': 'Status', 'type': 'string'}],
        )
        exec_dk = execute_bi_question_connection(
            dconn, q_dk, dialect='duckdb', parameter_values={'st': 'open'}
        )
        assert exec_dk['rows'] == [['open', 4]]
    finally:
        dconn.close()

    # 3. Live Firebird Embedded
    import firebird.driver as fbd

    fb_path = tmp_path / 'field_service.fdb'
    fconn = fbd.create_database(str(fb_path))
    try:
        fcur = fconn.cursor()
        fcur.execute(
            'CREATE TABLE CUSTOMERS ('
            'CUSTOMER_ID INTEGER NOT NULL PRIMARY KEY, '
            'NAME VARCHAR(120) NOT NULL)'
        )
        fcur.execute(
            'CREATE TABLE WORK_ORDERS ('
            'WORK_ORDER_ID INTEGER NOT NULL PRIMARY KEY, '
            'CUSTOMER_ID INTEGER NOT NULL REFERENCES CUSTOMERS(CUSTOMER_ID), '
            'STATUS VARCHAR(20), PRIORITY INTEGER)'
        )
        fconn.commit()
        fcur.execute("INSERT INTO CUSTOMERS VALUES (1, 'Northwind')")
        fcur.execute(
            "INSERT INTO WORK_ORDERS VALUES (1001, 1, 'open', 3)"
        )
        fcur.execute(
            "INSERT INTO WORK_ORDERS VALUES (1002, 1, 'open', 4)"
        )
        fconn.commit()
        fcur.close()

        fb_res = _capture_live_firebird_resources(fconn)
        fb_diag = firebird_erd.build_diagram(
            fb_res,
            {'endpoint_id': 'ep-fb-emb', 'database_target_id': 'fb-emb'},
        )
        fb_erd = store.import_physical_erd_workspace(
            project_id='live',
            key='firebird-embedded-erd',
            title='Live Firebird Embedded ERD',
            workspace=fb_diag['snapshot'],
            actor_id=1,
        )
        assert len(fb_erd['elements']) >= 4

        q_fb = default_question_model(
            name='Firebird Open Orders',
            endpoint_id='ep-fb-emb',
            sbsql={
                'from': {
                    'relation': ['main', 'WORK_ORDERS'],
                    'alias': 'WO',
                },
                'columns': [{'column': ['WO', 'STATUS'], 'alias': 'STATUS'}],
                'measures': [{
                    'function': 'sum',
                    'column': ['WO', 'PRIORITY'],
                    'alias': 'TOTAL_PRIORITY',
                }],
                'filters': [{
                    'column': ['WO', 'STATUS'],
                    'operator': 'eq',
                    'parameter': 'st',
                }],
                'limit': 5,
            },
            parameters=[{'id': 'st', 'name': 'Status', 'type': 'string'}],
        )
        exec_fb = execute_bi_question_connection(
            fconn, q_fb, dialect='firebird', parameter_values={'st': 'open'}
        )
        assert exec_fb['rows'] == [['open', 7]]
        assert 'ROWS 1 TO 5' in exec_fb['sql']
    finally:
        fconn.close()

    # 4. Cube materialization SQL across engines + Screen Mesh suspect rename
    cube_model = default_cube_model(name='Work Order Cube')
    cube_model['materializations'] = [{
        'id': 'agg_work_orders',
        'name': 'Work Order Totals Rollup',
        'strategy': 'materialized_view',
        'enabled': True,
        'measure_group_id': 'default_measures',
        'grain_dimensions': [],
        'measures': ['row_count'],
        'target_relation': ['agg_work_orders'],
        'refresh_policy': 'on_accept_review',
    }]
    cube = cube_sync.create_cube(
        project_id='live',
        key='work-order-cube',
        title='Work Order Cube',
        model=cube_model,
        actor_id=1,
    )
    for eng in ('duckdb', 'firebird', 'mysql'):
        plan = preview_cube_materialization_plan(
            None, cube['cube']['model'], target_engine=eng
        )
        assert plan['requires_native_review'] is True
        assert plan['applied_immediately'] is False
        assert len(plan['statements']) >= 1

    store.register_resource_identity(
        engine='firebird',
        endpoint_id='ep-fb-emb',
        database_target_id='fb-emb',
        resource_kind='column',
        resource_id='WORK_ORDERS.STATUS',
    )
    screen_id = uuid7()
    status_ctl_id = uuid7()
    mesh_model = default_screen_mesh_model(
        name='Work Order Editor',
        screens=[{'id': screen_id, 'name': 'Work Order Form'}],
        controls=[{
            'id': status_ctl_id,
            'screen_id': screen_id,
            'role': 'ui.dropdown',
            'name': 'Order Status',
            'options': ['open', 'closed'],
        }],
        bindings=[{
            'id': uuid7(),
            'source_id': status_ctl_id,
            'target_kind': 'column',
            'target_ref': 'WORK_ORDERS.STATUS',
            'access_mode': 'read_write',
            'target_engine': 'firebird',
            'target_endpoint_id': 'ep-fb-emb',
            'target_database_target_id': 'fb-emb',
        }],
    )
    created_mesh = mesh_sync.create_screen_mesh(
        project_id='live',
        key='wo-mesh',
        title='Work Order Editor',
        actor_id=1,
        mesh=mesh_model,
    )
    assert created_mesh['suspect_binding_count'] == 0
    mesh_design_id = created_mesh['design']['id']

    # Simulate catalog column rename -> binding becomes suspect (A6)
    renamed = store.record_resource_rename(
        engine='firebird',
        endpoint_id='ep-fb-emb',
        database_target_id='fb-emb',
        old_resource_id='WORK_ORDERS.STATUS',
        new_resource_id='WORK_ORDERS.ORDER_STATUS',
    )
    assert renamed['suspect_bindings_marked'] >= 1
    after_rename = mesh_sync.get_screen_mesh(mesh_design_id)
    assert after_rename['suspect_binding_count'] == 1
    assert after_rename['mesh']['bindings'][0]['state'] == 'suspect'


@pytest.mark.skipif(
    not _port_open('127.0.0.1', 53050),
    reason='Firebird 5 demo daemon (127.0.0.1:53050) is not running',
)
def test_live_firebird5_network_readonly_qualification(tmp_path):
    """Read-only live qualification against Firebird 5.0.4 on port 53050."""
    import firebird.driver as fbd

    store = DesignStore(db_path=tmp_path / 'designs.db')
    dsn = '127.0.0.1/53050:/var/lib/firebird/data/cdeadmin_demo.fdb'
    conn = fbd.connect(dsn, user='SYSDBA', password=DEMO_PASSWORD)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT rdb$get_context('SYSTEM', 'ENGINE_VERSION') "
            'FROM rdb$database'
        )
        fb_ver = str(cur.fetchone()[0])
        cur.close()
        assert fb_ver.startswith('5.')

        resources = _capture_live_firebird_resources(conn)
        diag = firebird_erd.build_diagram(
            resources,
            {'endpoint_id': 'ep-fb5-net', 'database_target_id': 'fb5-demo'},
        )
        erd = store.import_physical_erd_workspace(
            project_id='live-net',
            key='fb5-net-erd',
            title=f'Firebird {fb_ver} Network ERD',
            workspace=diag['snapshot'],
            actor_id=1,
        )
        assert len(erd['elements']) >= 6

        q = default_question_model(
            name='Firebird 5 Open Work Orders',
            endpoint_id='ep-fb5-net',
            sbsql={
                'from': {
                    'relation': ['main', 'WORK_ORDERS'],
                    'alias': 'WO',
                },
                'columns': [{'column': ['WO', 'STATUS'], 'alias': 'STATUS'}],
                'measures': [{
                    'function': 'count',
                    'column': None,
                    'alias': 'ORDER_COUNT',
                }],
                'filters': [{
                    'column': ['WO', 'STATUS'],
                    'operator': 'eq',
                    'parameter': 'st',
                }],
                'limit': 10,
            },
            parameters=[{'id': 'st', 'name': 'Status', 'type': 'string'}],
        )
        res = execute_bi_question_connection(
            conn, q, dialect='firebird', parameter_values={'st': 'open'}
        )
        assert res['rows'] == [['open', 2]]
    finally:
        conn.close()


@pytest.mark.parametrize(
    ('engine', 'port'),
    [('mysql', 53306), ('mariadb', 53307)],
)
def test_live_mysql_and_mariadb_readonly_qualification(tmp_path, engine, port):
    """Read-only live qualification against MySQL 9.7 & MariaDB 12.2 demos."""
    if not _port_open('127.0.0.1', port):
        pytest.skip(f'{engine} demo daemon (127.0.0.1:{port}) is not running')

    import mysql.connector

    store = DesignStore(db_path=tmp_path / f'{engine}_designs.db')
    conn = mysql.connector.connect(
        host='127.0.0.1',
        port=port,
        user='cdeadmin_demo',
        password=DEMO_PASSWORD,
        database='cdeadmin_demo',
        connection_timeout=5,
    )
    try:
        resources = _capture_live_mysql_family_resources(
            conn, engine, 'cdeadmin_demo'
        )
        diag = mysql_erd.build_diagram(
            resources,
            {
                'endpoint_id': f'ep-{engine}',
                'database_target_id': 'cdeadmin_demo',
            },
            engine=engine,
        )
        erd = store.import_physical_erd_workspace(
            project_id='live-net',
            key=f'{engine}-erd',
            title=f'Live {engine.upper()} ERD',
            workspace=diag['snapshot'],
            actor_id=1,
        )
        assert len(erd['elements']) >= 6
        assert all(b['state'] == 'valid' for b in erd['bindings'])

        converted = convert_erd_design_engine(
            erd['version']['ddn_text'],
            source_engine=engine,
            target_engine='postgresql',
            strict=False,
        )
        assert converted['loss_report']['target_engine'] == 'postgresql'

        q = default_question_model(
            name=f'{engine.upper()} Open Work Orders',
            endpoint_id=f'ep-{engine}',
            sbsql={
                'from': {
                    'relation': ['cdeadmin_demo', 'work_orders'],
                    'alias': 'wo',
                },
                'columns': [{'column': ['wo', 'status'], 'alias': 'status'}],
                'measures': [{
                    'function': 'sum',
                    'column': ['wo', 'priority'],
                    'alias': 'priority_total',
                }],
                'filters': [{
                    'column': ['wo', 'status'],
                    'operator': 'eq',
                    'parameter': 'st',
                }],
                'limit': 10,
            },
            parameters=[{'id': 'st', 'name': 'Status', 'type': 'string'}],
        )
        res = execute_bi_question_connection(
            conn, q, dialect=engine, parameter_values={'st': 'open'}
        )
        assert len(res['rows']) == 1
        assert res['rows'][0][0] == 'open'
        assert int(res['rows'][0][1]) == 7
    finally:
        conn.close()


def test_live_cube_parent_child_and_semi_additive_across_engines(tmp_path):
    """Execute parent-child WITH RECURSIVE & semi-additive SQL on 4 engines."""
    from pgadmin.cdeadmin.semantic_models import validate_model, validate_query
    from pgadmin.cdeadmin.semantic_models.compiler import compile_sql

    cube = validate_model({
        'contract_version': '1.0.0',
        'name': 'Team Balances Cube',
        'semantic_family': 'relational',
        'sources': [
            {
                'id': 'BALANCES',
                'resource_id': 'table:main:BALANCES',
                'kind': 'table',
                'classification': 'fact',
                'relation': ['BALANCES'],
                'grain': [
                    {'source_id': 'BALANCES', 'field': 'SNAP_DAY'},
                    {'source_id': 'BALANCES', 'field': 'TEAM_ID'},
                ],
            },
            {
                'id': 'TEAMS',
                'resource_id': 'table:main:TEAMS',
                'kind': 'table',
                'classification': 'dimension',
                'relation': ['TEAMS'],
                'grain': [{'source_id': 'TEAMS', 'field': 'TEAM_ID'}],
            },
        ],
        'joins': [{
            'id': 'bal_teams',
            'left_source': 'BALANCES',
            'right_source': 'TEAMS',
            'join_type': 'inner',
            'cardinality': 'many-to-one',
            'active': True,
            'predicates': [{
                'left': {'source_id': 'BALANCES', 'field': 'TEAM_ID'},
                'operator': 'eq',
                'right': {'source_id': 'TEAMS', 'field': 'TEAM_ID'},
            }],
        }],
        'dimensions': [
            {
                'id': 'team',
                'name': 'Team',
                'type': 'categorical',
                'field': {'source_id': 'TEAMS', 'field': 'TEAM_ID'},
                'hierarchies': [{
                    'id': 'team_tree',
                    'name': 'Team Tree',
                    'hierarchy_kind': 'parent_child',
                    'child_field': {'source_id': 'TEAMS', 'field': 'TEAM_ID'},
                    'parent_field': {
                        'source_id': 'TEAMS', 'field': 'PARENT_ID'
                    },
                    'max_depth': 5,
                    'ragged': True,
                }],
            },
            {
                'id': 'snap_day',
                'name': 'Snapshot Day',
                'type': 'time',
                'field': {'source_id': 'BALANCES', 'field': 'SNAP_DAY'},
            },
        ],
        'measures': [
            {
                'id': 'closing_bal',
                'name': 'Closing Non-Empty Balance',
                'aggregation': 'last_non_empty',
                'semi_additive_dimension': 'snap_day',
                'within_group_aggregation': 'sum',
                'field': {'source_id': 'BALANCES', 'field': 'AMOUNT'},
            },
            {
                'id': 'total_flow',
                'name': 'Total Flow',
                'aggregation': 'sum',
                'field': {'source_id': 'BALANCES', 'field': 'FLOW'},
            },
        ],
    })
    query = validate_query(
        cube,
        {
            'axes': {'rows': ['team']},
            'measures': ['closing_bal', 'total_flow'],
            'order_by': [{'id': 'team', 'direction': 'asc'}],
        },
    )

    ddl_and_seed = [
        'CREATE TABLE TEAMS (TEAM_ID INTEGER NOT NULL PRIMARY KEY, '
        'PARENT_ID INTEGER)',
        'CREATE TABLE BALANCES (SNAP_DAY INTEGER NOT NULL, '
        'TEAM_ID INTEGER NOT NULL, AMOUNT DOUBLE PRECISION, '
        'FLOW DOUBLE PRECISION)',
        'INSERT INTO TEAMS VALUES (1, NULL)',
        'INSERT INTO TEAMS VALUES (2, 1)',
        'INSERT INTO BALANCES VALUES (1, 1, 50.0, 5.0)',
        'INSERT INTO BALANCES VALUES (2, 1, 60.0, 10.0)',
        'INSERT INTO BALANCES VALUES (1, 2, 100.0, 20.0)',
        'INSERT INTO BALANCES VALUES (2, 2, NULL, 4.0)',
    ]
    # Team 1 rolls up Team 1 + Team 2:
    # Day 1 sum = 50+100 = 150; Day 2 sum = 60+NULL = 60 -> last_non_empty=60
    # Total flow for Team 1 + Team 2 = 5+10+20+4 = 39
    # Team 2 alone: Day 1 = 100, Day 2 = NULL -> last_non_empty=100; flow=24
    expected = [(1, 60.0, 39.0), (2, 100.0, 24.0)]

    from pgadmin.cdeadmin.design_store.cube_ddn import _PORTABLE_DIALECTS

    # 1. SQLite
    sq_sql = compile_sql(
        cube, query, _PORTABLE_DIALECTS['sqlite']
    )['source']
    with sqlite3.connect(':memory:') as sconn:
        for st in ddl_and_seed:
            sconn.execute(st)
        assert sconn.execute(sq_sql).fetchall() == expected

    # 2. DuckDB
    dk_sql = compile_sql(
        cube, query, _PORTABLE_DIALECTS['duckdb']
    )['source']
    dconn = duckdb.connect(':memory:')
    try:
        for st in ddl_and_seed:
            dconn.execute(st)
        assert dconn.execute(dk_sql).fetchall() == expected
    finally:
        dconn.close()

    # 3. Firebird 5 Embedded
    import firebird.driver as fbd

    fb_sql = compile_sql(
        cube, query, _PORTABLE_DIALECTS['firebird']
    )['source']
    fconn = fbd.create_database(str(tmp_path / 'cube_pc_sa.fdb'))
    try:
        fcur = fconn.cursor()
        for st in ddl_and_seed[:2]:
            fcur.execute(st)
        fconn.commit()
        for st in ddl_and_seed[2:]:
            fcur.execute(st)
        fconn.commit()
        fcur.execute(fb_sql)
        fb_rows = [
            (int(r[0]), float(r[1]), float(r[2])) for r in fcur.fetchall()
        ]
        fcur.close()
        assert fb_rows == expected
    finally:
        fconn.close()

    # 4. Read-only semi-additive query against live MySQL 9.7 if running
    if _port_open('127.0.0.1', 53306):
        import mysql.connector

        mysql_cube = validate_model({
            'contract_version': '1.0.0',
            'name': 'MySQL Demo Semi-Additive',
            'semantic_family': 'relational',
            'sources': [{
                'id': 'wo',
                'resource_id': 'table:cdeadmin_demo:work_orders',
                'kind': 'table',
                'classification': 'fact',
                'relation': ['cdeadmin_demo', 'work_orders'],
                'grain': [{'source_id': 'wo', 'field': 'work_order_id'}],
            }],
            'dimensions': [
                {
                    'id': 'status',
                    'name': 'Status',
                    'type': 'categorical',
                    'field': {'source_id': 'wo', 'field': 'status'},
                },
                {
                    'id': 'wo_seq',
                    'name': 'Work Order Sequence',
                    'type': 'time',
                    'field': {'source_id': 'wo', 'field': 'work_order_id'},
                },
            ],
            'measures': [{
                'id': 'latest_priority',
                'name': 'Latest Priority',
                'aggregation': 'last_non_empty',
                'semi_additive_dimension': 'wo_seq',
                'within_group_aggregation': 'max',
                'field': {'source_id': 'wo', 'field': 'priority'},
            }],
        })
        mq = validate_query(
            mysql_cube,
            {
                'axes': {'rows': ['status']},
                'measures': ['latest_priority'],
                'order_by': [{'id': 'status', 'direction': 'asc'}],
            },
        )
        msql = compile_sql(
            mysql_cube,
            mq,
            _PORTABLE_DIALECTS['mysql'],
        )['source']
        mconn = mysql.connector.connect(
            host='127.0.0.1',
            port=53306,
            user='cdeadmin_demo',
            password=DEMO_PASSWORD,
            database='cdeadmin_demo',
            connection_timeout=5,
        )
        try:
            mcur = mconn.cursor()
            mcur.execute(msql)
            mrows = mcur.fetchall()
            mcur.close()
            assert len(mrows) >= 1
            assert any(r[0] == 'open' for r in mrows)
        finally:
            mconn.close()
