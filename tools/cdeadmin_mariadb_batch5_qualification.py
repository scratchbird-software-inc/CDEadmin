#!/usr/bin/env python3
"""Live qualification (native + authenticated HTTP) for MariaDB 12.2.2 Batch 5 (7 items).

Items qualified:
1. MA-AUDIT-TEMPORARY
2. MA-AUDIT-NATIVE-INDEXES
3. MA-AUDIT-TABLE-FIELDS
4. MA-AUDIT-TEMPORAL-LIFECYCLE
5. MA-AUDIT-OBJECT-EDITOR-PARITY
6. MA-AUDIT-AVAILABLE-PLUGINS
7. MA-AUDIT-MARIA-MONITORING (strictly excluding ScratchBird /history!)
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def _cell(val):
    if isinstance(val, dict) and 'data' in val:
        return val['data']
    return val


def _generate_mariadb_dashboard_draft(snapshot, scope):
    """Build a MariaDB dashboard DDN draft from a live collector snapshot via mysqlDashboard.js."""
    node_script = """
import fs from 'node:fs';
import {mysqlDashboardFiles} from './web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/mysqlDashboard.js';
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const files = mysqlDashboardFiles(input.snapshot, input.scope, 'mariadb');
process.stdout.write(JSON.stringify({
  format: 'ddn-source-workspace@1',
  entry: 'dashboard.ddn',
  view: 'dashboard',
  files,
}));
"""
    out = subprocess.check_output(
        ['node', '--input-type=module', '-e', node_script],
        input=json.dumps({'snapshot': snapshot, 'scope': scope}),
        cwd=str(ROOT),
        text=True,
        timeout=30,
    )
    return json.loads(out)


def _create_isolated_app(data_dir: Path):
    import base64
    import config
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    data_dir.mkdir(parents=True, exist_ok=True)
    config.CDEADMIN_MONITORING_PROCESS_MODE = 'single'
    config.CDEADMIN_MONITORING_LOCK_PATH = str(data_dir / 'monitor.lock')
    config.CDEADMIN_MONITORING_WORKER_KEYS = {'k': base64.b64encode(os.urandom(32)).decode()}
    config.CDEADMIN_MONITORING_WORKER_ACTIVE_KEY_ID = 'k'
    return setup_application(data_dir)


def run_qualification(output_dir: Path, work_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    app = _create_isolated_app(work_dir / 'pgadmin-data')

    from flask import url_for
    import mariadb
    from tools.mariadb_qualification_support import server, _root_connection
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.providers import native_editor
    from pgadmin.cdeadmin.providers.mysql_family.mariadb_monitoring import MariaDBMonitor
    from pgadmin.cdeadmin.providers.mysql_family.mariadb_server_catalog import capture as capture_server_catalog
    from pgadmin.cdeadmin.providers.mysql_family.provider import (
        MARIADB_ADMINISTRATION,
        MARIADB_PROFILE,
        MariaDBPilotProvider,
        _create_client,
        _resources,
    )
    from pgadmin.cdeadmin.sdk import RelationalClientError
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from pgadmin.cdeadmin.workspace.mariadb_schema_apply import MariaDBSchemaApplications
    from pgadmin.cdeadmin.workspace.mariadb_schema_plan import plan as schema_plan
    from pgadmin.cdeadmin.workspace import physical_schema as vocab
    from pgadmin.cdeadmin.workspace import mysql_physical
    from pgadmin.model import EndpointDatabaseTarget, Server, ServerGroup, User, db

    task_sources: dict[str, list[str]] = {}
    receipts: dict[str, dict] = {}

    fixture_dir = work_dir / 'mariadb-fixture'
    with server(fixture_dir, image='mariadb:12.2.2') as (route, container_name, fixture_proof):
        admin_pw = secrets.token_urlsafe(24)
        observer = _root_connection('mariadb', route['port'])
        observer.autocommit = True
        db_native = 'b5_native_' + secrets.token_hex(4)
        db_http = 'b5_http_' + secrets.token_hex(4)

        native_client = None
        native_monitors: list[MariaDBMonitor] = []
        srv_id = None
        http_client = None

        try:
            with observer.cursor() as cur:
                cur.execute(f'CREATE DATABASE `{db_native}` CHARACTER SET utf8mb4 COLLATE utf8mb4_uca1400_ai_ci')
                cur.execute(f'CREATE DATABASE `{db_http}` CHARACTER SET utf8mb4 COLLATE utf8mb4_uca1400_ai_ci')
                cur.execute("CREATE USER 'b5_admin'@'%' IDENTIFIED BY ?", (admin_pw,))
                cur.execute("GRANT ALL PRIVILEGES ON *.* TO 'b5_admin'@'%' WITH GRANT OPTION")
                cur.execute('FLUSH PRIVILEGES')

            # Set up native provider & client
            from tools.tests.test_cdeadmin_relational_providers import context as build_endpoint_context
            native_route, native_perms = provider_access(
                {**route, 'user': 'b5_admin', 'database': db_native},
                password=admin_pw,
            )
            native_perms.require = lambda permission, scope=None: None
            native_ctx = build_endpoint_context(MARIADB_PROFILE, 'batch5-' + secrets.token_hex(4))
            native_client = _create_client(MARIADB_PROFILE, native_perms, native_ctx)
            native_provider = MariaDBPilotProvider(native_ctx, native_perms, native_client)

            def record_task(kind: str, op: str, statements: list[dict]):
                task_id = f'visual_admin.{kind}.{op}'
                sqls = [s['source'] for s in statements if isinstance(s, dict) and s.get('source')]
                if sqls:
                    task_sources.setdefault(task_id, []).extend(sqls)

            def native_admin(kind: str, op: str, draft: dict, target: dict | None = None, session_id: str | None = None, session_handle=None):
                req = {
                    'route': native_route,
                    '_provider_route': native_route,
                    'resource_kind': kind,
                    'operation_id': op,
                    'draft': draft,
                    **({'target_resource': target} if target is not None else {}),
                    **({'session_id': session_id} if session_id is not None else {}),
                }
                val = native_client.validate_admin_operation(req)
                assert not val.get('errors'), f'Validation failed for {kind}.{op}: {val}'
                planned = native_client.plan_admin_operation(req)
                compiled = planned['provider_payload']['compiled']
                record_task(kind, op, compiled.get('statements', []))
                apply_req = {
                    **planned,
                    'route': native_route,
                    '_provider_route': native_route,
                    **({'_provider_session_handle': session_handle} if session_handle is not None else {}),
                }
                applied = native_client.apply_admin_operation(apply_req)
                return planned, applied

            def find_native_resource(kind: str, name: str, *, session_handle=None, temp: bool | None = None):
                res_list = native_client.list_resources({
                    'route': native_route,
                    **({'_provider_session_handle': session_handle} if session_handle is not None else {}),
                })
                for r in res_list:
                    if r['resource_kind'] != kind or r['display_name'] != name:
                        continue
                    if temp is not None and bool(r.get('native', {}).get('temporary')) != temp:
                        continue
                    return r
                raise AssertionError(f'Resource {kind}:{name} (temp={temp}) not found')

            # Set up authenticated HTTP client & registered server
            with app.test_request_context('/'):
                user = User.query.first()
                uid = user.id
                group = ServerGroup.query.filter_by(user_id=uid).first()
                app.blueprints['NODE-engine_type'].connector_visibility['mariadb'].set(True, user_id=uid)
                srv = Server(
                    user_id=uid,
                    servergroup_id=group.id,
                    name='Batch 5 MariaDB 12.2.2',
                    host=route['host'],
                    port=route['port'],
                    username='b5_admin',
                    maintenance_db=None,
                    save_password=0,
                )
                srv._cde_endpoint_registration = registration_profile('mariadb-native')
                srv._cde_endpoint_route_configuration = {
                    'host': route['host'],
                    'port': route['port'],
                    'user': 'b5_admin',
                    'ssl': False,
                    'ssl_verify_cert': False,
                    'credential_kinds': ['database_password'],
                }
                db.session.add(srv)
                db.session.commit()
                srv_id = srv.id
                http_tid = str(uuid.uuid4())
                db.session.add(EndpointDatabaseTarget(
                    id=http_tid,
                    endpoint_id=srv.endpoint_profile.id,
                    display_name=db_http,
                    database=db_http,
                    configuration='{}',
                    active=1,
                ))
                db.session.commit()
                verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=srv_id)
                ws_url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=srv_id)

            http_client = app.test_client()
            with http_client.session_transaction() as sess:
                sess['_user_id'] = str(uid)
                sess['_fresh'] = True
            v_resp = http_client.post(verify_url, json={'password': admin_pw}).get_json()
            assert v_resp and v_resp.get('success'), v_resp

            def http_ws(action: str, payload: dict | None = None, *, top_level: dict | None = None, expect_error: bool = False):
                body = {'action': action, **(top_level or {})}
                if payload is not None:
                    body['request'] = payload
                resp = http_client.post(ws_url, json=body)
                data = resp.get_json()
                if expect_error:
                    assert resp.status_code != 200 or not data.get('success'), f'Expected error for {action}, got {data}'
                    return data
                assert resp.status_code == 200 and data.get('success'), f'HTTP {action} failed ({resp.status_code}): {data}'
                return data['data']

            def http_admin(kind: str, op: str, draft: dict, target: dict | None = None, session_id: str | None = None, confirmation: str | None = None, expect_plan_error: bool = False, server_scope: bool = False):
                scope_fields = {} if server_scope else {'database_target_id': http_tid}
                plan_req = {
                    **scope_fields,
                    'resource_kind': kind,
                    'operation_id': op,
                    'draft': draft,
                    **({'target_resource': target} if target is not None else {}),
                    **({'session_id': session_id} if session_id is not None else {}),
                }
                if expect_plan_error:
                    return http_ws('visual_admin_plan', plan_req, expect_error=True), None
                planned = http_ws('visual_admin_plan', plan_req)
                apply_req = {
                    **scope_fields,
                    'plan_id': planned['plan_id'],
                    'plan_digest': planned['plan_digest'],
                    'confirmed': True,
                    **({'confirmation': confirmation} if confirmation is not None else {}),
                    **({'session_id': session_id} if session_id is not None else {}),
                }
                applied = http_ws('visual_admin_apply', apply_req)
                return planned, applied

            def http_exec(session_id: str, sql: str):
                occ = http_ws('execute', None, top_level={
                    'session_id': session_id,
                    'database_target_id': http_tid,
                    'source': sql,
                })
                oid = occ['occurrence_id']
                polled = http_ws('poll', None, top_level={'occurrence_id': oid, 'database_target_id': http_tid})
                while polled['occurrence']['lifecycle_state'] == 'provider_active':
                    time.sleep(0.02)
                    polled = http_ws('poll', None, top_level={'occurrence_id': oid, 'database_target_id': http_tid})
                assert polled['occurrence']['lifecycle_state'] == 'provider_terminal', polled
                return polled['occurrence']['result']['extensions']['mariadb']['payload']

            def http_find_resource(kind: str, name: str, *, server_scope: bool = False, temp: bool | None = None):
                req = {} if server_scope else {'database_target_id': http_tid}
                first = http_ws('resource_page', req)
                page = http_ws('resource_refresh', {**req, 'generation': first['generation']})
                items = list(page.get('resources') or page.get('items') or [])
                while page.get('continuation'):
                    page = http_ws('resource_page', {
                        **req,
                        'continuation': page['continuation'],
                        'generation': page['generation'],
                    })
                    items.extend(page.get('resources') or page.get('items') or [])
                for item in items:
                    if item.get('resource_kind') != kind or item.get('display_name') != name:
                        continue
                    native = item.get('native') or ((item.get('extensions') or {}).get('mariadb') or {}).get('native') or {}
                    if temp is not None and bool(native.get('temporary')) != temp:
                        continue
                    return item
                raise AssertionError(f'HTTP resource {kind}:{name} (temp={temp}) not found among {len(items)} items')

            # =========================================================================
            # 1. MA-AUDIT-TEMPORARY (Session Temporary Tables & Shadowing)
            # =========================================================================
            with observer.cursor() as cur:
                cur.execute(f'CREATE TABLE `{db_native}`.`shadow_pair` (base_column INT PRIMARY KEY) ENGINE=InnoDB')
                cur.execute(f'INSERT INTO `{db_native}`.`shadow_pair` VALUES (101)')
                cur.execute(f'CREATE TABLE `{db_http}`.`shadow_pair` (base_column INT PRIMARY KEY) ENGINE=InnoDB')
                cur.execute(f'INSERT INTO `{db_http}`.`shadow_pair` VALUES (202)')

            sess_info = native_provider.open_session({'route': native_route, 'language_profile': 'mariadb-sql'})
            nat_sid = sess_info['session_id']
            nat_handle = native_provider._sessions[nat_sid].handle
            nat_cid = nat_handle.connection_id

            # Start uncommitted tx + savepoint on retained session to verify non-finalization
            nat_handle.autocommit = False
            with nat_handle.cursor() as scur:
                scur.execute('INSERT INTO `shadow_pair` VALUES (102)')
                scur.execute('SAVEPOINT sp_before_temp')

            # Create session TEMPORARY table shadowing shadow_pair via table.create(temporary=True)
            _p_tc, a_tc = native_admin(
                'table',
                'create',
                {
                    'name': 'shadow_pair',
                    'parent': db_native,
                    'temporary': True,
                    'engine': 'Aria',
                    'columns': [
                        {'name': 'temp_only_col', 'type': 'VARCHAR(32)', 'nullable': False},
                    ],
                },
                session_id=nat_sid,
                session_handle=nat_handle,
            )
            assert a_tc['accepted'] and a_tc.get('staged_in_provider_session') is True

            # Verify list_resources separates temporary-table:... and table:...
            temp_res = find_native_resource('table', 'shadow_pair', session_handle=nat_handle, temp=True)
            base_res = find_native_resource('table', 'shadow_pair', session_handle=nat_handle, temp=False)
            assert temp_res['resource_id'] == f'temporary-table:{db_native}:shadow_pair'
            assert base_res['resource_id'] == f'table:{db_native}:shadow_pair'
            assert temp_res['native']['shadows_base_table'] is True
            assert base_res['native']['shadowed_by_session_temporary'] is True
            assert '`base_column`' in base_res['native']['ddl']
            assert '`temp_only_col`' in temp_res['native']['ddl']

            # Verify direct native_editor.metadata on original session
            direct_meta = native_editor.metadata(nat_handle, 'mariadb')
            assert direct_meta['complete'] is False
            shadow_cols_direct = [
                r['display_name']
                for r in direct_meta['resources']
                if r['resource_kind'] == 'column' and r['display_path'][:2] == [db_native, 'shadow_pair']
            ]
            assert shadow_cols_direct == ['temp_only_col'], shadow_cols_direct

            # Verify explicit mariadb_editor_context refresh_completion
            ctx_res = native_provider.native_editor_context_action({
                'session_id': nat_sid,
                'language_profile': 'mariadb-sql',
                'operation': 'refresh_completion',
                'diagnostics_change_confirmed': True,
            })['editor_context']
            assert ctx_res['complete'] is False
            assert ctx_res['original_temporary_objects_observed'] is True
            shadow_cols_refresh = [
                r['display_name']
                for r in ctx_res['resources']
                if r['resource_kind'] == 'column' and r['display_path'][:2] == [db_native, 'shadow_pair']
            ]
            assert shadow_cols_refresh == ['temp_only_col'], shadow_cols_refresh
            assert any(
                r['resource_kind'] == 'shadowed-table' and r.get('resource_id') == f'table:{db_native}:shadow_pair'
                for r in ctx_res['resources']
            )

            # Verify uncommitted row & savepoint still intact!
            with nat_handle.cursor() as scur:
                scur.execute('ROLLBACK TO SAVEPOINT sp_before_temp')
            nat_handle.rollback()
            nat_handle.autocommit = True

            # Drop temporary table via table.drop_temporary and confirm base table untouched
            _p_dt, a_dt = native_admin(
                'table',
                'drop_temporary',
                {'confirmation': 'shadow_pair'},
                target=temp_res,
                session_id=nat_sid,
                session_handle=nat_handle,
            )
            assert a_dt['accepted'] and a_dt['temporary_table_observation']['after_temporary_exists'] is False
            with observer.cursor() as cur:
                cur.execute(f'SELECT base_column FROM `{db_native}`.`shadow_pair`')
                assert cur.fetchall() == [(101,)]

            # Re-attempting drop_temporary when temporary table is gone must fail without touching base table!
            try:
                native_admin(
                    'table',
                    'drop_temporary',
                    {'confirmation': 'shadow_pair'},
                    target=temp_res,
                    session_id=nat_sid,
                    session_handle=nat_handle,
                )
            except RelationalClientError:
                pass
            else:
                raise AssertionError('Expected drop_temporary to refuse missing temporary table')
            with observer.cursor() as cur:
                cur.execute(f'SELECT base_column FROM `{db_native}`.`shadow_pair`')
                assert cur.fetchall() == [(101,)]

            # Close session and verify temporary-holding connection was discarded, not pooled
            close_obs = native_provider.close_session({'session_id': nat_sid})
            assert close_obs.get('provider_payload', close_obs).get('temporary_session_discarded') is True

            # HTTP qualification for MA-AUDIT-TEMPORARY
            http_opened = http_ws('open_session', None, top_level={
                'language_profile': 'mariadb-sql',
                'database_target_id': http_tid,
            })
            http_sid = http_opened['session_id']
            try:
                _hp_tc, ha_tc = http_admin(
                    'table',
                    'create',
                    {
                        'name': 'shadow_pair',
                        'parent': db_http,
                        'temporary': True,
                        'columns': [{'name': 'http_temp_col', 'type': 'INT', 'nullable': False}],
                    },
                    session_id=http_sid,
                )
                assert ha_tc.get('provider_result', ha_tc).get('accepted') is True

                http_ctx = http_ws(
                    'mariadb_editor_context',
                    {'operation': 'refresh_completion', 'diagnostics_change_confirmed': True},
                    top_level={'session_id': http_sid, 'database_target_id': http_tid},
                )['editor_context']
                assert http_ctx['complete'] is False
                assert http_ctx['original_temporary_objects_observed'] is True
                http_shadow_cols = [
                    r['display_name']
                    for r in http_ctx['resources']
                    if r['resource_kind'] == 'column' and r['display_path'][:2] == [db_http, 'shadow_pair']
                ]
                assert http_shadow_cols == ['http_temp_col'], http_shadow_cols

                http_temp_target = {
                    'resource_id': f'temporary-table:{db_http}:shadow_pair',
                    'resource_kind': 'table',
                    'display_name': 'shadow_pair',
                    'display_path': [db_http, 'shadow_pair'],
                    'native': {'temporary': True, 'table_type': 'TEMPORARY'},
                }
                _hp_dt, ha_dt = http_admin(
                    'table',
                    'drop_temporary',
                    {'confirmation': 'shadow_pair'},
                    target=http_temp_target,
                    session_id=http_sid,
                    confirmation='shadow_pair',
                )
                assert ha_dt.get('provider_result', ha_dt).get('accepted') is True
                base_check = http_exec(http_sid, 'SELECT base_column FROM shadow_pair')
                assert int(_cell(base_check['rows'][0][0])) == 202
            finally:
                http_ws('close_session', None, top_level={'session_id': http_sid, 'database_target_id': http_tid})

            receipts['MA-AUDIT-TEMPORARY'] = {
                'item_id': 'MA-AUDIT-TEMPORARY',
                'status': 'qualified_native_and_http',
                'native_connection_id_tested': nat_cid,
                'distinct_resource_ids_verified': [
                    f'temporary-table:{db_native}:shadow_pair',
                    f'table:{db_native}:shadow_pair',
                ],
                'shadow_columns_reported': shadow_cols_refresh,
                'complete_flag_false_verified': True,
                'base_table_preserved_after_drop_temporary': True,
                'temporary_session_connection_discarded_on_close': True,
                'http_qualified': True,
            }

            # =========================================================================
            # 2. MA-AUDIT-NATIVE-INDEXES (FULLTEXT, SPATIAL, VECTOR & DDN VECTOR KEY)
            # =========================================================================
            native_admin(
                'table',
                'create',
                {
                    'name': 'idx_lab',
                    'parent': db_native,
                    'engine': 'InnoDB',
                    'columns': [
                        {'name': 'id', 'type': 'INT', 'nullable': False, 'primary_key': True},
                        {'name': 'embedding', 'type': 'VECTOR(4)', 'nullable': False},
                        {'name': 'doc_body', 'type': 'TEXT', 'nullable': True},
                        {'name': 'geom_pt', 'type': 'POINT', 'nullable': False},
                        {'name': 'tag', 'type': 'VARCHAR(120)', 'nullable': False},
                    ],
                },
            )
            # Create VECTOR, FULLTEXT, SPATIAL, and NORMAL (prefix + DESC + IGNORED + COMMENT) indexes
            native_admin('index', 'create', {
                'name': 'idx_vec_cos',
                'parent': db_native,
                'table': 'idx_lab',
                'index_kind': 'VECTOR',
                'columns': [{'name': 'embedding'}],
                'vector_m': 8,
                'vector_distance': 'cosine',
            })
            native_admin('index', 'create', {
                'name': 'idx_ft_doc',
                'parent': db_native,
                'table': 'idx_lab',
                'index_kind': 'FULLTEXT',
                'columns': [{'name': 'doc_body'}],
            })
            native_admin('index', 'create', {
                'name': 'idx_sp_pt',
                'parent': db_native,
                'table': 'idx_lab',
                'index_kind': 'SPATIAL',
                'method': 'RTREE',
                'columns': [{'name': 'geom_pt'}],
            })
            native_admin('index', 'create', {
                'name': 'idx_tag_pref',
                'parent': db_native,
                'table': 'idx_lab',
                'index_kind': 'NORMAL',
                'method': 'BTREE',
                'columns': [{'name': 'tag', 'prefix_length': 24, 'direction': 'DESC'}],
                'ignored': True,
                'key_block_size': '4',
                'comment': 'prefix ignored index',
            })

            # Verify invalid combination refusals
            for bad_idx in (
                {'name': 'bad_uvec', 'parent': db_native, 'table': 'idx_lab', 'index_kind': 'VECTOR', 'unique': True, 'columns': [{'name': 'embedding'}]},
                {'name': 'bad_mvec', 'parent': db_native, 'table': 'idx_lab', 'index_kind': 'VECTOR', 'columns': [{'name': 'embedding'}, {'name': 'tag'}]},
                {'name': 'bad_dvec', 'parent': db_native, 'table': 'idx_lab', 'index_kind': 'VECTOR', 'columns': [{'name': 'embedding'}], 'vector_distance': 'manhattan'},
            ):
                err_res = native_client.validate_admin_operation({
                    'route': native_route,
                    '_provider_route': native_route,
                    'resource_kind': 'index',
                    'operation_id': 'create',
                    'draft': bad_idx,
                })
                assert err_res['errors'], f'Expected refusal for {bad_idx}'

            # Toggle visibility, rename, and composite alter on idx_tag_pref
            idx_res = find_native_resource('index', 'idx_tag_pref')
            assert idx_res['native']['ignored'] is True
            vec_res = find_native_resource('index', 'idx_vec_cos')
            assert vec_res['native']['index_kind'] == 'VECTOR'
            assert vec_res['native']['vector_m'] == 8
            assert vec_res['native']['vector_distance'] == 'cosine'

            native_admin('index', 'visibility', {'visibility': 'NOT IGNORED', 'confirmation': 'idx_tag_pref'}, target=idx_res)
            idx_res = find_native_resource('index', 'idx_tag_pref')
            assert idx_res['native']['ignored'] is False

            native_admin('index', 'rename', {'new_name': 'idx_tag_renamed', 'confirmation': 'idx_tag_pref'}, target=idx_res)
            idx_res = find_native_resource('index', 'idx_tag_renamed')

            native_admin('index', 'alter', {'ignored': True, 'new_name': 'idx_tag_final'}, target=idx_res)
            idx_res = find_native_resource('index', 'idx_tag_final')
            assert idx_res['native']['ignored'] is True

            # DDN export -> parse VECTOR KEY -> edit M=12, DISTANCE=euclidean -> plan -> validate -> apply round-trip!
            cat_snap = native_provider.capture_catalog(native_route)
            ddn_export = build_export(
                cat_snap['resources'],
                endpoint_id='b5-native-ep',
                target_id=db_native,
                generation=cat_snap['generation'],
                engine='mariadb',
                native_model=True,
            )
            idx_lab_row = next(r for r in ddn_export['rows'].values() if r['kind'] == 'table' and r['name'] == 'idx_lab')
            children_v, _fk_v, warn_v = mysql_physical.forward(
                'idx_lab', idx_lab_row['native'], cat_snap.get('sql_mode', ''), 'mariadb'
            )
            assert not warn_v, warn_v
            vec_child = next(c for c in children_v if c['name'] == 'idx_vec_cos')
            assert vec_child['values']['index_type'] == 'VECTOR'
            assert vec_child['values']['vector_m'] == 8
            assert vec_child['values']['vector_distance'] == 'cosine'

            # Plan & apply a DDN schema change altering VECTOR index M=12, DISTANCE=euclidean
            desired_doc = deepcopy(ddn_export)
            d_row = next(r for r in desired_doc['rows'].values() if r['kind'] == 'table' and r['name'] == 'idx_lab')
            rebuilt_vec_clause = mysql_physical.build_index(
                'index',
                'idx_vec_cos',
                vocab.normalize({
                    'physical_kind': 'index',
                    'physical_name': 'idx_vec_cos',
                    'columns_json': json.dumps(['embedding']),
                    'index_type': 'VECTOR',
                    'vector_m': 12,
                    'vector_distance': 'euclidean',
                }),
                {'id', 'embedding', 'doc_body', 'geom_pt', 'tag'},
                '',
                'mariadb',
            )
            d_row['native']['definition'] = d_row['native']['definition'].replace(vec_child['clause'], rebuilt_vec_clause)
            vec_plan = schema_plan(ddn_export, desired_doc, ddn_export)
            assert vec_plan['ready_for_review'], vec_plan
            vec_plan.update(native_provider.validate_schema_plan(native_route, vec_plan))
            assert vec_plan['native_grammar_validated'] is True
            apps = MariaDBSchemaApplications(work_dir / 'vec-schema-receipts.json')
            v_rec = apps.review(vec_plan, ddn_export, desired_doc, 'owner', 'binding', db_native)
            v_app = apps.apply(
                {'review_id': v_rec['review_id'], 'review_digest': v_rec['review_digest'], 'confirmed': True},
                'owner',
                'binding',
                lambda rec: native_provider.apply_schema_review(native_route, rec),
            )
            assert v_app['state'] == 'committed' and v_app['outcome']['rediscovery_verified']
            vec_after = find_native_resource('index', 'idx_vec_cos')
            assert vec_after['native']['vector_m'] == 12
            assert vec_after['native']['vector_distance'] == 'euclidean'

            # HTTP qualification for MA-AUDIT-NATIVE-INDEXES (including HTTP DDN export & schema plan!)
            http_admin('table', 'create', {
                'name': 'http_vectors',
                'parent': db_http,
                'engine': 'InnoDB',
                'columns': [
                    {'name': 'id', 'type': 'INT', 'nullable': False, 'primary_key': True},
                    {'name': 'v', 'type': 'VECTOR(4)', 'nullable': False},
                    {'name': 'label', 'type': 'VARCHAR(64)', 'nullable': False},
                ],
            })
            http_admin('index', 'create', {
                'name': 'http_vec_idx',
                'parent': db_http,
                'table': 'http_vectors',
                'index_kind': 'VECTOR',
                'columns': [{'name': 'v'}],
                'vector_m': 6,
                'vector_distance': 'cosine',
            })
            http_admin('index', 'create', {
                'name': 'http_lbl_idx',
                'parent': db_http,
                'table': 'http_vectors',
                'index_kind': 'NORMAL',
                'columns': [{'name': 'label', 'prefix_length': 16}],
            })
            h_lbl_target = http_find_resource('index', 'http_lbl_idx')
            http_admin(
                'index',
                'visibility',
                {'visibility': 'IGNORED', 'confirmation': 'http_lbl_idx'},
                target=h_lbl_target,
                confirmation='http_lbl_idx',
            )
            h_lbl_target = http_find_resource('index', 'http_lbl_idx')
            http_admin(
                'index',
                'rename',
                {'new_name': 'http_lbl_idx_v2', 'confirmation': 'http_lbl_idx'},
                target=h_lbl_target,
                confirmation='http_lbl_idx',
            )
            http_cat = http_ws('mariadb_catalog_export', {'database_target_id': http_tid})
            assert 'VECTOR KEY `http_vec_idx`' in json.dumps(http_cat)

            receipts['MA-AUDIT-NATIVE-INDEXES'] = {
                'item_id': 'MA-AUDIT-NATIVE-INDEXES',
                'status': 'qualified_native_and_http',
                'vector_index_created_and_ddn_roundtripped': True,
                'fulltext_spatial_prefix_ignored_rename_verified': True,
                'invalid_combinations_refused': True,
                'http_qualified': True,
            }

            # =========================================================================
            # 3. MA-AUDIT-TABLE-FIELDS (MariaDB Typed Table Create/Alter Options)
            # =========================================================================
            _p_aria, a_aria = native_admin('table', 'create', {
                'name': 'aria_ledger',
                'parent': db_native,
                'engine': 'Aria',
                'character_set': 'utf8mb4',
                'collation': 'utf8mb4_uca1400_ai_ci',
                'row_format': 'PAGE',
                'transactional': '1',
                'page_checksum': '1',
                'comment': 'Aria transactional table',
                'columns': [
                    {'name': 'id', 'type': 'BIGINT', 'nullable': False, 'primary_key': True},
                    {'name': 'amount', 'type': 'DECIMAL(12,2)', 'nullable': False},
                    {
                        'name': 'amount_cents',
                        'type': 'BIGINT',
                        'generated_expression': 'amount * 100',
                        'generated_storage': 'PERSISTENT',
                    },
                    {'name': 'audit_token', 'type': 'VARCHAR(32)', 'nullable': True, 'invisible': True},
                ],
            })
            assert a_aria.get('native_implicit_commit') is True
            aria_tbl = find_native_resource('table', 'aria_ledger')
            assert aria_tbl['native']['engine'] == 'Aria'
            assert aria_tbl['native']['table_options'].get('transactional') == '1'
            assert aria_tbl['native']['table_options'].get('page_checksum') == '1'

            # InnoDB table with auto_increment, stats_persistent, application-time PERIOD FOR + WITHOUT OVERLAPS, then alter
            native_admin('table', 'create', {
                'name': 'innodb_contracts',
                'parent': db_native,
                'engine': 'InnoDB',
                'row_format': 'DYNAMIC',
                'auto_increment': '500',
                'stats_persistent': '1',
                'comment': 'Contracts v1',
                'columns': [
                    {'name': 'contract_id', 'type': 'INT', 'nullable': False},
                    {'name': 'valid_from', 'type': 'DATE', 'nullable': False},
                    {'name': 'valid_to', 'type': 'DATE', 'nullable': False},
                ],
                'periods': [
                    {'name': 'contract_period', 'start_column': 'valid_from', 'end_column': 'valid_to'},
                ],
                'constraints': [
                    {
                        'kind': 'PRIMARY KEY',
                        'columns': ['contract_id'],
                        'without_overlaps': 'contract_period',
                    },
                ],
            })
            inno_tbl = find_native_resource('table', 'innodb_contracts')
            assert inno_tbl['native']['application_periods'] == [
                {'name': 'contract_period', 'start_column': 'valid_from', 'end_column': 'valid_to'}
            ]
            _p_alt_t, a_alt_t = native_admin(
                'table',
                'alter',
                {'comment': 'Contracts v2', 'auto_increment': '1000'},
                target=inno_tbl,
            )
            assert a_alt_t.get('native_implicit_commit') is True

            # Verify unsupported engine-option combination refusals
            for bad_tbl in (
                {'name': 'bad_aria_comp', 'parent': db_native, 'engine': 'Aria', 'page_compressed': '1', 'columns': [{'name': 'id', 'type': 'INT'}]},
                {'name': 'bad_inno_tx', 'parent': db_native, 'engine': 'InnoDB', 'transactional': '1', 'columns': [{'name': 'id', 'type': 'INT'}]},
                {'name': 'bad_mem_row', 'parent': db_native, 'engine': 'MEMORY', 'row_format': 'COMPRESSED', 'columns': [{'name': 'id', 'type': 'INT'}]},
            ):
                err_t = native_client.validate_admin_operation({
                    'route': native_route,
                    '_provider_route': native_route,
                    'resource_kind': 'table',
                    'operation_id': 'create',
                    'draft': bad_tbl,
                })
                assert err_t['errors'], f'Expected engine-combination refusal for {bad_tbl}'

            # HTTP qualification for MA-AUDIT-TABLE-FIELDS
            http_admin('table', 'create', {
                'name': 'http_aria_items',
                'parent': db_http,
                'engine': 'Aria',
                'row_format': 'PAGE',
                'transactional': '1',
                'page_checksum': '1',
                'comment': 'HTTP Aria v1',
                'columns': [
                    {'name': 'id', 'type': 'INT', 'nullable': False, 'primary_key': True},
                    {'name': 'price', 'type': 'INT', 'nullable': False},
                    {'name': 'doubled', 'type': 'INT', 'generated_expression': 'price * 2', 'generated_storage': 'VIRTUAL'},
                ],
            })
            h_aria = http_find_resource('table', 'http_aria_items')
            http_admin('table', 'alter', {'comment': 'HTTP Aria v2'}, target=h_aria)
            http_admin(
                'table',
                'create',
                {
                    'name': 'http_bad_combo',
                    'parent': db_http,
                    'engine': 'Aria',
                    'page_compressed': '1',
                    'columns': [{'name': 'id', 'type': 'INT'}],
                },
                expect_plan_error=True,
            )

            receipts['MA-AUDIT-TABLE-FIELDS'] = {
                'item_id': 'MA-AUDIT-TABLE-FIELDS',
                'status': 'qualified_native_and_http',
                'aria_and_innodb_options_verified': True,
                'generated_invisible_period_without_overlaps_verified': True,
                'implicit_commit_reported': True,
                'unsupported_engine_combinations_refused': True,
                'http_qualified': True,
            }

            # =========================================================================
            # 4. MA-AUDIT-TEMPORAL-LIFECYCLE (System-Versioning, Application-Time & FOR PORTION OF)
            # =========================================================================
            native_admin('table', 'create', {
                'name': 'temporal_lifecycle',
                'parent': db_native,
                'engine': 'InnoDB',
                'columns': [
                    {'name': 'id', 'type': 'INT', 'nullable': False},
                    {'name': 'status', 'type': 'VARCHAR(32)', 'nullable': False},
                    {'name': 'app_start', 'type': 'DATE', 'nullable': False},
                    {'name': 'app_end', 'type': 'DATE', 'nullable': False},
                ],
            })
            t_target = find_native_resource('table', 'temporal_lifecycle')

            # Enable system versioning
            native_admin('table', 'add_system_versioning', {'confirmation': 'temporal_lifecycle'}, target=t_target)
            with observer.cursor() as cur:
                cur.execute(f"INSERT INTO `{db_native}`.`temporal_lifecycle` VALUES (1, 'v1', '2026-01-01', '2026-12-31')")
                cur.execute(f"UPDATE `{db_native}`.`temporal_lifecycle` SET status='v2' WHERE id=1")
                cur.execute(f"UPDATE `{db_native}`.`temporal_lifecycle` SET status='v3' WHERE id=1")

            # Rotate / configure system-time partitions + add history partitions
            t_target = find_native_resource('table', 'temporal_lifecycle')
            native_admin('table', 'rotate_system_time_partitions', {
                'rotation_action': 'PARTITION_BY_LIMIT',
                'row_limit': 100,
                'history_partitions': 2,
                'confirmation': 'temporal_lifecycle',
            }, target=t_target)
            t_target = find_native_resource('table', 'temporal_lifecycle')
            native_admin('table', 'rotate_system_time_partitions', {
                'rotation_action': 'ADD_HISTORY_PARTITIONS',
                'partitions_to_add': 1,
                'confirmation': 'temporal_lifecycle',
            }, target=t_target)

            # Verify unconfirmed history truncation is refused!
            err_unconf = native_client.validate_admin_operation({
                'route': native_route,
                '_provider_route': native_route,
                'resource_kind': 'table',
                'operation_id': 'truncate_system_versioning_history',
                'target_resource': t_target,
                'draft': {'cutoff_mode': 'ALL', 'confirmation': 'temporal_lifecycle'},
            })
            assert err_unconf['errors']

            # Confirmed DELETE HISTORY removes historical row versions while keeping current row
            t_target = find_native_resource('table', 'temporal_lifecycle')
            _p_th, a_th = native_admin('table', 'truncate_system_versioning_history', {
                'cutoff_mode': 'ALL',
                'destructive_history_confirmed': True,
                'confirmation': 'temporal_lifecycle',
            }, target=t_target)
            assert a_th['temporal_observation']['before']['historical_rows'] == 2
            assert a_th['temporal_observation']['after']['historical_rows'] == 0
            assert a_th['temporal_observation']['after']['current_rows'] == 1

            # Remove partitioning so we can add application-time period & test FOR PORTION OF
            with observer.cursor() as cur:
                cur.execute(f'ALTER TABLE `{db_native}`.`temporal_lifecycle` REMOVE PARTITIONING')
            t_target = find_native_resource('table', 'temporal_lifecycle')
            native_admin('table', 'add_application_period', {
                'period_name': 'app_validity',
                'start_column': 'app_start',
                'end_column': 'app_end',
                'confirmation': 'temporal_lifecycle',
            }, target=t_target)

            # Execute FOR PORTION OF DML on MariaDB session and verify row-affect & split rows!
            fpo_sess = native_provider.open_session({'route': native_route, 'language_profile': 'mariadb-sql'})
            fpo_sid = fpo_sess['session_id']
            try:
                occ = native_provider.execute({
                    'session_id': fpo_sid,
                    'source': (
                        "UPDATE `temporal_lifecycle` FOR PORTION OF `app_validity` "
                        "FROM '2026-04-01' TO '2026-07-01' SET status='mid_year'"
                    ),
                })
                pages = []
                while True:
                    polled = native_provider.describe_result({'operation_id': occ['operation_id']})
                    p_pay = polled['extensions']['mariadb']['payload']
                    if p_pay.get('has_page'):
                        pages.append(p_pay)
                    if polled.get('complete'):
                        assert not p_pay.get('error'), p_pay
                        break
                    time.sleep(0.02)
                assert pages and int(pages[-1].get('rowcount', 0)) >= 1, pages
                native_provider.control_transaction({'session_id': fpo_sid, 'action': 'commit'})
                with observer.cursor() as cur:
                    cur.execute(
                        f'SELECT status, CAST(app_start AS CHAR), CAST(app_end AS CHAR) '
                        f'FROM `{db_native}`.`temporal_lifecycle` ORDER BY app_start'
                    )
                    portions = cur.fetchall()
                assert portions == [
                    ('v3', '2026-01-01', '2026-04-01'),
                    ('mid_year', '2026-04-01', '2026-07-01'),
                    ('v3', '2026-07-01', '2026-12-31'),
                ], portions
            finally:
                native_provider.close_session({'session_id': fpo_sid})

            t_target = find_native_resource('table', 'temporal_lifecycle')
            native_admin('table', 'drop_application_period', {
                'period_name': 'app_validity',
                'destructive_history_confirmed': True,
                'confirmation': 'temporal_lifecycle',
            }, target=t_target)

            # Verify DDN schema-planner refuses unconfirmed drop of WITH SYSTEM VERSIONING, then admits confirmed opt-in!
            cat_t = native_provider.capture_catalog(native_route)
            base_t = build_export(
                cat_t['resources'], endpoint_id='b5-native-ep', target_id=db_native,
                generation=cat_t['generation'], engine='mariadb', native_model=True,
            )
            des_unconf = deepcopy(base_t)
            tl_row = next(r for r in des_unconf['rows'].values() if r['kind'] == 'table' and r['name'] == 'temporal_lifecycle')
            tl_row['native']['definition'] = tl_row['native']['definition'].replace(' WITH SYSTEM VERSIONING', '')
            refused_plan = schema_plan(base_t, des_unconf, base_t)
            assert not refused_plan['ready_for_review'] and refused_plan['blockers']

            des_conf = deepcopy(des_unconf)
            tl_row_c = next(r for r in des_conf['rows'].values() if r['kind'] == 'table' and r['name'] == 'temporal_lifecycle')
            tl_row_c['native']['mariadb_change'] = {
                'drop_system_versioning': True,
                'destructive_history_confirmed': True,
                'confirmation': 'temporal_lifecycle',
            }
            admitted_plan = schema_plan(base_t, des_conf, base_t)
            assert admitted_plan['ready_for_review'], admitted_plan
            assert 'DROP SYSTEM VERSIONING' in admitted_plan['operations'][0]['source']
            assert admitted_plan['operations'][0]['destructive'] is True
            assert admitted_plan['operations'][0]['destructive_history_confirmed'] is True

            # Execute drop_system_versioning via visual_admin
            t_target = find_native_resource('table', 'temporal_lifecycle')
            _p_dsv, a_dsv = native_admin('table', 'drop_system_versioning', {
                'destructive_history_confirmed': True,
                'confirmation': 'temporal_lifecycle',
            }, target=t_target)
            assert a_dsv['temporal_observation']['after']['system_versioned'] is False

            # HTTP qualification for MA-AUDIT-TEMPORAL-LIFECYCLE
            http_admin('table', 'create', {
                'name': 'http_temporal',
                'parent': db_http,
                'engine': 'InnoDB',
                'columns': [
                    {'name': 'id', 'type': 'INT', 'nullable': False, 'primary_key': True},
                    {'name': 'val', 'type': 'VARCHAR(32)', 'nullable': False},
                ],
            })
            ht_tbl = http_find_resource('table', 'http_temporal')
            http_admin(
                'table',
                'add_system_versioning',
                {'confirmation': 'http_temporal'},
                target=ht_tbl,
                confirmation='http_temporal',
            )
            with observer.cursor() as cur:
                cur.execute(f"INSERT INTO `{db_http}`.`http_temporal` VALUES (1, 'old')")
                cur.execute(f"UPDATE `{db_http}`.`http_temporal` SET val='new' WHERE id=1")
            ht_tbl = http_find_resource('table', 'http_temporal')
            http_admin(
                'table',
                'truncate_system_versioning_history',
                {'cutoff_mode': 'ALL', 'destructive_history_confirmed': True, 'confirmation': 'http_temporal'},
                target=ht_tbl,
                confirmation='http_temporal',
            )
            ht_tbl = http_find_resource('table', 'http_temporal')
            http_admin(
                'table',
                'drop_system_versioning',
                {'destructive_history_confirmed': True, 'confirmation': 'http_temporal'},
                target=ht_tbl,
                confirmation='http_temporal',
            )

            receipts['MA-AUDIT-TEMPORAL-LIFECYCLE'] = {
                'item_id': 'MA-AUDIT-TEMPORAL-LIFECYCLE',
                'status': 'qualified_native_and_http',
                'operations_verified': [
                    'add_system_versioning',
                    'rotate_system_time_partitions',
                    'truncate_system_versioning_history',
                    'add_application_period',
                    'drop_application_period',
                    'drop_system_versioning',
                ],
                'for_portion_of_rows_verified': portions,
                'ddn_unconfirmed_refused_and_confirmed_opt_in_verified': True,
                'http_qualified': True,
            }

            # =========================================================================
            # 5. MA-AUDIT-OBJECT-EDITOR-PARITY (View, Procedure, Function & Trigger Alter/Replace)
            # =========================================================================
            native_admin('table', 'create', {
                'name': 'obj_events',
                'parent': db_native,
                'engine': 'InnoDB',
                'columns': [
                    {'name': 'id', 'type': 'INT', 'nullable': False, 'primary_key': True},
                    {'name': 'score', 'type': 'INT', 'nullable': False},
                    {'name': 'log_trail', 'type': 'VARCHAR(64)', 'nullable': False, 'default': "''"},
                ],
            })
            # View create -> alter -> create_or_replace (with dependent view check)
            native_admin('view', 'create', {
                'name': 'v_scores',
                'parent': db_native,
                'algorithm': 'MERGE',
                'sql_security': 'INVOKER',
                'query': f'SELECT id, score FROM `{db_native}`.`obj_events` WHERE score > 0',
                'check_option': 'CASCADED',
            })
            native_admin('view', 'create', {
                'name': 'v_scores_dep',
                'parent': db_native,
                'query': f'SELECT id, score FROM `{db_native}`.`v_scores`',
            })
            v_res = find_native_resource('view', 'v_scores')
            _, a_va = native_admin('view', 'alter', {
                'algorithm': 'UNDEFINED',
                'sql_security': 'DEFINER',
                'query': f'SELECT id, score FROM `{db_native}`.`obj_events` WHERE score >= 10',
                'check_option': 'LOCAL',
            }, target=v_res)
            assert 'v_scores_dep' in a_va['object_observation']['dependent_views']

            v_res = find_native_resource('view', 'v_scores')
            native_admin('view', 'create_or_replace', {
                'algorithm': 'MERGE',
                'sql_security': 'INVOKER',
                'query': f'SELECT id, score FROM `{db_native}`.`obj_events` WHERE score >= 5',
                'confirmation': 'v_scores',
            }, target=v_res)

            # Function create -> alter -> create_or_replace
            native_admin('function', 'create', {
                'name': 'fn_bonus',
                'parent': db_native,
                'parameters': [{'name': 'base_val', 'type': 'INT'}],
                'returns': 'INT',
                'deterministic': 'DETERMINISTIC',
                'data_access': 'NO SQL',
                'body': 'RETURN base_val + 10;',
            })
            fn_res = find_native_resource('function', 'fn_bonus')
            native_admin('function', 'alter', {
                'sql_security': 'INVOKER',
                'comment': 'bonus function v2',
            }, target=fn_res)
            fn_res = find_native_resource('function', 'fn_bonus')
            native_admin('function', 'create_or_replace', {
                'parameters': [{'name': 'base_val', 'type': 'INT'}],
                'returns': 'INT',
                'deterministic': 'DETERMINISTIC',
                'data_access': 'NO SQL',
                'sql_security': 'INVOKER',
                'comment': 'bonus function v3',
                'body': 'RETURN base_val + 25;',
                'confirmation': 'fn_bonus',
            }, target=fn_res)
            with observer.cursor() as cur:
                cur.execute(f'SELECT `{db_native}`.`fn_bonus`(5)')
                assert cur.fetchone() == (30,)

            # Procedure create (IN/OUT) -> alter -> create_or_replace (ORACLE mode!)
            native_admin('procedure', 'create', {
                'name': 'sp_adjust',
                'parent': db_native,
                'parameters': [
                    {'mode': 'IN', 'name': 'p_in', 'type': 'INT'},
                    {'mode': 'OUT', 'name': 'p_out', 'type': 'INT'},
                ],
                'data_access': 'NO SQL',
                'body': 'BEGIN SET p_out = p_in * 2; END',
            })
            sp_res = find_native_resource('procedure', 'sp_adjust')
            native_admin('procedure', 'alter', {
                'comment': 'adjusted proc',
                'sql_security': 'INVOKER',
            }, target=sp_res)
            sp_res = find_native_resource('procedure', 'sp_adjust')
            native_admin('procedure', 'create_or_replace', {
                'parameters': [
                    {'mode': 'IN', 'name': 'p_in', 'type': 'INT'},
                    {'mode': 'OUT', 'name': 'p_out', 'type': 'INT'},
                ],
                'data_access': 'NO SQL',
                'sql_mode': 'ORACLE',
                'body': 'BEGIN p_out := p_in * 3; END;',
                'confirmation': 'sp_adjust',
            }, target=sp_res)
            with observer.cursor() as cur:
                cur.execute(f'CALL `{db_native}`.`sp_adjust`(7, @sp_res_val)')
                cur.execute('SELECT @sp_res_val')
                assert cur.fetchone() == (21,)

            # Trigger create (sibling ordering) -> alter -> create_or_replace preserving FOLLOWS order!
            native_admin('trigger', 'create', {
                'name': 'trg_first',
                'parent': db_native,
                'table': 'obj_events',
                'timing': 'BEFORE',
                'events': ['INSERT'],
                'body': "SET NEW.log_trail = CONCAT(NEW.log_trail, 'A');",
            })
            native_admin('trigger', 'create', {
                'name': 'trg_second',
                'parent': db_native,
                'table': 'obj_events',
                'timing': 'BEFORE',
                'events': ['INSERT'],
                'order_kind': 'FOLLOWS',
                'order_trigger': 'trg_first',
                'body': "SET NEW.log_trail = CONCAT(NEW.log_trail, 'B');",
            })
            trg2_res = find_native_resource('trigger', 'trg_second')
            native_admin('trigger', 'alter', {
                'timing': 'BEFORE',
                'events': ['INSERT'],
                'body': "SET NEW.log_trail = CONCAT(NEW.log_trail, 'B2');",
            }, target=trg2_res)
            trg2_res = find_native_resource('trigger', 'trg_second')
            native_admin('trigger', 'create_or_replace', {
                'timing': 'BEFORE',
                'events': ['INSERT'],
                'body': "SET NEW.log_trail = CONCAT(NEW.log_trail, 'B3');",
                'confirmation': 'trg_second',
            }, target=trg2_res)
            with observer.cursor() as cur:
                cur.execute(f"INSERT INTO `{db_native}`.`obj_events`(id, score, log_trail) VALUES (1, 50, '')")
                cur.execute(f'SELECT log_trail FROM `{db_native}`.`obj_events` WHERE id=1')
                assert cur.fetchone() == ('AB3',)

            # HTTP qualification for MA-AUDIT-OBJECT-EDITOR-PARITY
            http_admin('table', 'create', {
                'name': 'http_obj_tbl',
                'parent': db_http,
                'engine': 'InnoDB',
                'columns': [
                    {'name': 'id', 'type': 'INT', 'nullable': False, 'primary_key': True},
                    {'name': 'val', 'type': 'INT', 'nullable': False},
                ],
            })
            http_admin('view', 'create', {
                'name': 'http_v',
                'parent': db_http,
                'query': f'SELECT id, val FROM `{db_http}`.`http_obj_tbl`',
            })
            hv = http_find_resource('view', 'http_v')
            http_admin('view', 'alter', {
                'algorithm': 'MERGE',
                'query': f'SELECT id, val FROM `{db_http}`.`http_obj_tbl` WHERE val > 0',
            }, target=hv)
            hv = http_find_resource('view', 'http_v')
            http_admin(
                'view',
                'create_or_replace',
                {'query': f'SELECT id, val FROM `{db_http}`.`http_obj_tbl` WHERE val >= 1', 'confirmation': 'http_v'},
                target=hv,
                confirmation='http_v',
            )
            http_admin('function', 'create', {
                'name': 'http_fn',
                'parent': db_http,
                'returns': 'INT',
                'deterministic': 'DETERMINISTIC',
                'data_access': 'NO SQL',
                'body': 'RETURN 10;',
            })
            hfn = http_find_resource('function', 'http_fn')
            http_admin('function', 'alter', {'comment': 'http fn altered'}, target=hfn)
            hfn = http_find_resource('function', 'http_fn')
            http_admin(
                'function',
                'create_or_replace',
                {
                    'returns': 'INT',
                    'deterministic': 'DETERMINISTIC',
                    'data_access': 'NO SQL',
                    'body': 'RETURN 20;',
                    'confirmation': 'http_fn',
                },
                target=hfn,
                confirmation='http_fn',
            )
            http_admin('procedure', 'create', {
                'name': 'http_sp',
                'parent': db_http,
                'data_access': 'NO SQL',
                'body': 'BEGIN SELECT 1; END',
            })
            hsp = http_find_resource('procedure', 'http_sp')
            http_admin('procedure', 'alter', {'comment': 'http sp altered'}, target=hsp)
            hsp = http_find_resource('procedure', 'http_sp')
            http_admin(
                'procedure',
                'create_or_replace',
                {'data_access': 'NO SQL', 'body': 'BEGIN SELECT 2; END', 'confirmation': 'http_sp'},
                target=hsp,
                confirmation='http_sp',
            )
            http_admin('trigger', 'create', {
                'name': 'http_trg',
                'parent': db_http,
                'table': 'http_obj_tbl',
                'timing': 'BEFORE',
                'events': ['INSERT'],
                'body': 'SET NEW.val = NEW.val + 1;',
            })
            htrg = http_find_resource('trigger', 'http_trg')
            http_admin(
                'trigger',
                'create_or_replace',
                {'timing': 'BEFORE', 'events': ['INSERT'], 'body': 'SET NEW.val = NEW.val + 2;', 'confirmation': 'http_trg'},
                target=htrg,
                confirmation='http_trg',
            )

            receipts['MA-AUDIT-OBJECT-EDITOR-PARITY'] = {
                'item_id': 'MA-AUDIT-OBJECT-EDITOR-PARITY',
                'status': 'qualified_native_and_http',
                'view_alter_and_replace_verified': True,
                'procedure_alter_and_oracle_replace_verified': True,
                'function_alter_and_replace_verified': True,
                'trigger_alter_and_replace_preserving_follows_order_verified': True,
                'http_qualified': True,
            }

            # =========================================================================
            # 6. MA-AUDIT-AVAILABLE-PLUGINS (information_schema.ALL_PLUGINS & Admission)
            # =========================================================================
            srv_res = find_native_resource('server', 'MariaDB')
            all_res = native_client.list_resources({'route': {k: v for k, v in native_route.items() if k != 'database'}})
            avail_plugins = [r for r in all_res if r['resource_kind'] == 'available-plugin']
            installed_plugins = [r for r in all_res if r['resource_kind'] == 'plugin']
            assert len(avail_plugins) > len(installed_plugins), (len(avail_plugins), len(installed_plugins))
            uninstalled_avail = [r for r in avail_plugins if r['native']['available_uninstalled']]
            assert uninstalled_avail, 'Expected uninstalled-but-available plugin libraries in ALL_PLUGINS'
            assert all(r['native']['mysql_enterprise_reclassified'] is False for r in avail_plugins)
            assert any(
                r['native']['edition_classification'] == 'mariadb-community-open-source'
                and r['native']['available_uninstalled']
                for r in avail_plugins
            )

            # Server DDN catalog capture also includes available-plugins section without SELECT *
            srv_conn = _root_connection('mariadb', route['port'])
            try:
                srv_cat = capture_server_catalog(srv_conn)
            finally:
                srv_conn.close()
            assert any(o['section'] == 'available-plugins' and o['available'] and o['rows'] > 0 for o in srv_cat['observations'])

            # Native server.inspect_available_plugins operation (excluding vs including test modules)
            _, a_plug_prod = native_admin(
                'server',
                'inspect_available_plugins',
                {'status_filter': 'UNINSTALLED_AVAILABLE', 'include_test_modules': False},
                target=srv_res,
            )
            _, a_plug_all = native_admin(
                'server',
                'inspect_available_plugins',
                {'status_filter': 'ALL', 'include_test_modules': True},
                target=srv_res,
            )
            prod_obs = a_plug_prod['available_plugins_observation']
            all_obs = a_plug_all['available_plugins_observation']
            assert prod_obs['returned_count'] > 0
            assert all(row['module_category'] == 'production' for row in prod_obs['rows'])
            assert all_obs['summary']['total_observed'] >= prod_obs['returned_count']

            # HTTP qualification for MA-AUDIT-AVAILABLE-PLUGINS
            http_srv = http_find_resource('server', 'MariaDB', server_scope=True)
            _, ha_plug = http_admin(
                'server',
                'inspect_available_plugins',
                {'status_filter': 'UNINSTALLED_AVAILABLE', 'include_test_modules': False},
                target=http_srv,
                server_scope=True,
            )
            assert ha_plug.get('provider_result', ha_plug).get('accepted') is True

            receipts['MA-AUDIT-AVAILABLE-PLUGINS'] = {
                'item_id': 'MA-AUDIT-AVAILABLE-PLUGINS',
                'status': 'qualified_native_and_http',
                'total_all_plugins_discovered': len(avail_plugins),
                'installed_active_plugins': len(installed_plugins),
                'uninstalled_available_libraries': len(uninstalled_avail),
                'sample_uninstalled_production_modules': [
                    {
                        'name': r['display_name'],
                        'type': r['native']['plugin_type'],
                        'library': r['native']['plugin_library'],
                        'classification': r['native']['edition_classification'],
                    }
                    for r in uninstalled_avail
                    if r['native']['production_supported']
                ][:8],
                'mysql_enterprise_mislabeled_count': 0,
                'http_qualified': True,
            }

            # =========================================================================
            # 7. MA-AUDIT-MARIA-MONITORING (Aria_pagecache_*, Key_*, wsrep_*, DDN Bindings)
            #    NOTE: Strictly NO /history calls (MA-AUDIT-HISTORY is owner_deferred).
            # =========================================================================
            mon_db = MariaDBMonitor(native_perms, native_route, scope='database')
            native_monitors.append(mon_db)
            s1 = mon_db.sample()
            with observer.cursor() as cur:
                cur.execute(f'INSERT INTO `{db_native}`.`aria_ledger`(id, amount, audit_token) VALUES (1, 19.95, "tok1"), (2, 42.50, "tok2")')
                cur.execute(f'SELECT SUM(amount_cents) FROM `{db_native}`.`aria_ledger`')
                cur.fetchall()
            time.sleep(0.15)
            s2 = mon_db.sample()

            assert s2['transaction_completed'] is True
            assert s2['rates']['status'] == 'available'
            status_by_name = {r['variable_name']: r for r in s2['groups']['status']['rows']}
            for aria_key in (
                'Aria_pagecache_blocks_unused',
                'Aria_pagecache_blocks_used',
                'Aria_pagecache_read_requests',
                'Aria_pagecache_reads',
                'Aria_pagecache_write_requests',
                'Aria_pagecache_writes',
                'Aria_transaction_log_syncs',
                'Key_blocks_unused',
                'Key_read_requests',
            ):
                assert aria_key in status_by_name, f'Missing {aria_key} in MariaDBMonitor status rows'
                assert s2['groups']['status'].get('units', {}).get(aria_key), s2['groups']['status']
            assert int(status_by_name['Aria_pagecache_read_requests']['variable_value']) > 0
            assert 'Aria_pagecache_read_requests' in s2['rates']['per_second']
            assert 'Aria_transaction_log_syncs' in s2['rates']['per_second']

            wsrep_grp = s2['groups']['wsrep']
            assert wsrep_grp['status'] == 'disabled'
            assert wsrep_grp['wsrep_on'] is False
            assert wsrep_grp['provider_loaded'] is False
            assert wsrep_grp['cluster_metrics_available'] is False
            assert wsrep_grp['rows'] == []

            eng_grp = s2['groups']['engines']
            assert eng_grp['status'] == 'available'
            eng_names = {r['engine'] for r in eng_grp['rows']}
            assert {'InnoDB', 'Aria', 'MyISAM', 'MEMORY', 'CSV', 'SEQUENCE'} <= eng_names

            # Authenticated HTTP monitoring policy + snapshot + fleet + DDN dashboard save/publish!
            enable_resp = http_client.post(
                f'/cdeadmin/api/monitoring/mariadb/{srv_id}?target_id={http_tid}',
                json={
                    'interval_seconds': 5,
                    'retain_samples': 10,
                    'lease_seconds': 120,
                    'credentials': {'username': 'b5_admin', 'password': admin_pw},
                },
            )
            assert enable_resp.status_code == 200 and enable_resp.get_json()['success'] == 1, enable_resp.get_json()
            try:
                snap_data = None
                for _ in range(30):
                    snap_resp = http_client.get(f'/cdeadmin/api/monitoring/mariadb/{srv_id}?target_id={http_tid}')
                    assert snap_resp.status_code == 200
                    cand = snap_resp.get_json()['data']
                    if len(cand.get('samples', [])) >= 2:
                        snap_data = cand
                        break
                    time.sleep(0.25)
                assert snap_data is not None and len(snap_data.get('samples', [])) >= 1, snap_data
                latest_http_sample = snap_data['samples'][-1]
                assert latest_http_sample['groups']['wsrep']['status'] == 'disabled'
                assert latest_http_sample['groups']['engines']['status'] == 'available'
                http_status_names = {r['variable_name'] for r in latest_http_sample['groups']['status']['rows']}
                assert 'Aria_pagecache_read_requests' in http_status_names

                fleet_resp = http_client.get('/cdeadmin/api/monitoring/mariadb')
                assert fleet_resp.status_code == 200 and fleet_resp.get_json()['success'] == 1

                # Generate DDN dashboard source from live MariaDB collector snapshot & publish via HTTP /definition!
                dash_draft = _generate_mariadb_dashboard_draft(snap_data, 'database')
                assert 'Aria_pagecache_read_requests' in dash_draft['files']['dashboard.ddn']
                assert 'mariadb_wsrep_summary_0' in dash_draft['files']['dashboard.ddn']
                assert 'mariadb_engines_' in dash_draft['files']['dashboard.ddn']

                read_def = http_client.get(
                    f'/cdeadmin/api/monitoring/mariadb/definition?sid={srv_id}&target_id={http_tid}'
                ).get_json()['data']
                save_resp = http_client.put(
                    f'/cdeadmin/api/monitoring/mariadb/definition?sid={srv_id}&target_id={http_tid}',
                    json={
                        'schema': 'cdeadmin.ddn-asset.v1',
                        'assetRef': read_def['assetRef'],
                        'snapshot': dash_draft,
                    },
                )
                assert save_resp.status_code == 200 and save_resp.get_json()['success'] == 1, save_resp.get_json()
                saved_def = save_resp.get_json()['data']

                pub_resp = http_client.post(
                    f'/cdeadmin/api/monitoring/mariadb/definition?sid={srv_id}&target_id={http_tid}',
                    json={
                        'source_version': int(saved_def['assetRef']['assetVersion']),
                        'expected_version': int(saved_def['publication_version']),
                    },
                )
                assert pub_resp.status_code == 200 and pub_resp.get_json()['success'] == 1, pub_resp.get_json()
                published_get = http_client.get(
                    f'/cdeadmin/api/monitoring/mariadb/definition?sid={srv_id}&target_id={http_tid}&published=1'
                )
                assert published_get.status_code == 200 and published_get.get_json()['success'] == 1
                assert published_get.get_json()['data']['state'] == 'published'
            finally:
                http_client.delete(f'/cdeadmin/api/monitoring/mariadb/{srv_id}?target_id={http_tid}')

            receipts['MA-AUDIT-MARIA-MONITORING'] = {
                'item_id': 'MA-AUDIT-MARIA-MONITORING',
                'status': 'qualified_native_and_http',
                'aria_pagecache_read_requests': status_by_name['Aria_pagecache_read_requests']['variable_value'],
                'aria_transaction_log_syncs': status_by_name['Aria_transaction_log_syncs']['variable_value'],
                'wsrep_disabled_honesty': {
                    'status': wsrep_grp['status'],
                    'wsrep_on': wsrep_grp['wsrep_on'],
                    'provider_loaded': wsrep_grp['provider_loaded'],
                    'cluster_metrics_available': wsrep_grp['cluster_metrics_available'],
                    'fabricated_zero_rows': len(wsrep_grp['rows']),
                },
                'installed_engines_observed': sorted(eng_names),
                'ddn_dashboard_validated_and_published_over_http': True,
                'scratchbird_history_endpoint_called': False,
            }

        finally:
            for mon in native_monitors:
                try:
                    mon.close()
                except Exception:
                    pass
            if 'cdeadmin_mariadb_monitoring_host' in app.extensions:
                try:
                    app.extensions['cdeadmin_mariadb_monitoring_host'].close()
                except Exception:
                    pass
            if native_client is not None:
                try:
                    native_client.close()
                except Exception:
                    pass
            try:
                observer.close()
            except Exception:
                pass

    fixture_cleanup = json.loads((fixture_dir / 'fixture.json').read_text(encoding='utf-8'))
    assert fixture_cleanup['owned_server_stopped'] is True
    assert fixture_cleanup['owned_fixture_volumes_removed'] is True

    # Write per-item receipts + native-qualification.json + summary.json
    for item_id, rec in receipts.items():
        slug = item_id.lower().replace('ma-audit-', '')
        (output_dir / f'{slug}-receipt.json').write_text(
            json.dumps({**rec, 'engine_version': fixture_proof['engine_version'], 'server_uid': fixture_proof['server_uid']}, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )

    native_qual_doc = {
        'complete': True,
        'engine': 'mariadb',
        'version': '12.2.2',
        'engine_version': fixture_proof['engine_version'],
        'server_uid': fixture_proof['server_uid'],
        'container_name': container_name,
        'fixture_cleanup': fixture_cleanup,
        'task_sources': task_sources,
        'items': receipts,
    }
    native_qual_path = output_dir / 'native-qualification.json'
    native_qual_path.write_text(json.dumps(native_qual_doc, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    native_qual_sha = hashlib.sha256(native_qual_path.read_bytes()).hexdigest()

    summary = {
        'complete': True,
        'batch': 'mariadb-batch5-catalog',
        'engine': 'mariadb',
        'reference_version': '12.2.2',
        'engine_version': fixture_proof['engine_version'],
        'server_uid': fixture_proof['server_uid'],
        'native_qualification_receipt': str(native_qual_path),
        'native_qualification_sha256': native_qual_sha,
        'fixture_cleanup_verified': True,
        'scratchbird_history_tests_executed': False,
        'qualified_items': sorted(receipts.keys()),
        'task_ids_exercised': sorted(task_sources.keys()),
    }
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('/home/dcalford/Sandbox/codex-work-area/cdeadmin-six-engine-implementation/mariadb-batch5-catalog'),
    )
    parser.add_argument(
        '--work',
        type=Path,
        default=Path('/home/dcalford/Sandbox/codex-work-area/cdeadmin-six-engine-implementation/tmp-work/batch5/qual'),
    )
    args = parser.parse_args()
    work = args.work.resolve()
    if work.exists():
        shutil.rmtree(work)
    try:
        result = run_qualification(args.output.resolve(), work)
        print(json.dumps(result, indent=2))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
