#!/usr/bin/env python3
"""Live native + authenticated HTTP qualification for MySQL 9.7.0 & MariaDB 12.2.2 Batches 2 & 3."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / 'web') not in sys.path:
    sys.path.insert(0, str(ROOT / 'web'))
if str(ROOT / 'tools') not in sys.path:
    sys.path.insert(0, str(ROOT / 'tools'))

DOCKER_ENV = {**os.environ, 'DOCKER_CONTEXT': os.environ.get('DOCKER_CONTEXT', 'desktop-linux')}


def _docker(args, *, check=True, timeout=180):
    res = subprocess.run(
        ['docker', *args],
        env=DOCKER_ENV,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and res.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} failed ({res.returncode}): {res.stderr.strip()}")
    return res


def _host_port(container_name, port_spec):
    out = _docker(['port', container_name, port_spec]).stdout.strip().splitlines()
    for line in out:
        if ':' in line:
            return int(line.rsplit(':', 1)[1])
    raise RuntimeError(f'No host port mapping for {container_name} {port_spec}')


def _image_digest(image):
    inspected = json.loads(_docker(['image', 'inspect', image]).stdout)[0]
    return {
        'image': image,
        'id': inspected.get('Id'),
        'repo_digests': inspected.get('RepoDigests', []),
    }


@contextmanager
def owned_mysql_9_7(work_dir: Path):
    work_dir.mkdir(parents=True, exist_ok=True)
    name = 'sr-b23-mysql-' + secrets.token_hex(6)
    proof = {'container_name': name, 'image': _image_digest('mysql:9.7.0'), 'owned_server_stopped': False}
    started = False
    try:
        _docker([
            'run', '-d', '--rm', '--name', name, '--cap-add=SYS_NICE',
            '-e', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes',
            '-p', '127.0.0.1::3306',
            '-p', '127.0.0.1::33060',
            'mysql:9.7.0',
            '--server-id=201',
            '--gtid-mode=ON',
            '--enforce-gtid-consistency=ON',
            '--log-bin=sr-b23-bin',
            '--log-replica-updates=ON',
        ])
        started = True
        import mysql.connector
        sql_port = None
        x_port = None
        deadline = time.monotonic() + 180
        last_err = None
        while time.monotonic() < deadline:
            try:
                sql_port = _host_port(name, '3306/tcp')
                x_port = _host_port(name, '33060/tcp')
                conn = mysql.connector.connect(host='127.0.0.1', port=sql_port, user='root', connection_timeout=3)
                try:
                    with conn.cursor() as cur:
                        cur.execute('SELECT VERSION(), @@server_uuid')
                        ver, suuid = cur.fetchone()
                        if str(ver).split('-')[0] == '9.7.0':
                            proof.update(engine_version=str(ver), server_uuid=str(suuid), sql_port=sql_port, mysqlx_port=x_port)
                            break
                finally:
                    conn.close()
            except Exception as exc:
                last_err = exc
                time.sleep(0.5)
        else:
            raise RuntimeError(f'MySQL 9.7.0 container did not become ready: {last_err}')
        yield {'host': '127.0.0.1', 'port': sql_port, 'mysqlx_port': x_port, 'user': 'root', 'use_pure': True}, proof
    finally:
        if started:
            logs = _docker(['logs', name], check=False)
            (work_dir / 'mysql-server.log').write_text(logs.stdout + logs.stderr)
            stopped = _docker(['rm', '-f', '-v', name], check=False)
            proof['owned_server_stopped'] = stopped.returncode == 0


@contextmanager
def owned_mariadb_12_2(work_dir: Path):
    work_dir.mkdir(parents=True, exist_ok=True)
    name = 'sr-b23-mariadb-' + secrets.token_hex(6)
    proof = {'container_name': name, 'image': _image_digest('mariadb:12.2.2'), 'owned_server_stopped': False}
    started = False
    volumes = []
    try:
        _docker([
            'run', '-d', '--name', name,
            '-e', 'MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1',
            '-p', '127.0.0.1::3306',
            'mariadb:12.2.2',
            '--server-id=202',
            '--log-bin=sr-b23-maria-bin',
            '--gtid-strict-mode=ON',
            '--binlog-format=ROW',
        ])
        started = True
        inspected = json.loads(_docker(['inspect', name]).stdout)[0]
        volumes = [m['Name'] for m in inspected.get('Mounts', []) if m.get('Type') == 'volume']
        import mariadb
        sql_port = None
        deadline = time.monotonic() + 180
        last_err = None
        while time.monotonic() < deadline:
            try:
                sql_port = _host_port(name, '3306/tcp')
                conn = mariadb.connect(host='127.0.0.1', port=sql_port, user='root', connect_timeout=3)
                try:
                    with conn.cursor() as cur:
                        cur.execute('SELECT VERSION(), @@server_uid')
                        ver, suid = cur.fetchone()
                        if str(ver).split('-')[0] == '12.2.2':
                            proof.update(engine_version=str(ver), server_uid=str(suid), sql_port=sql_port)
                            break
                finally:
                    conn.close()
            except Exception as exc:
                last_err = exc
                time.sleep(0.5)
        else:
            raise RuntimeError(f'MariaDB 12.2.2 container did not become ready: {last_err}')
        yield {'host': '127.0.0.1', 'port': sql_port, 'user': 'root', 'ssl': False, 'ssl_verify_cert': False}, proof
    finally:
        if started:
            logs = _docker(['logs', name], check=False)
            (work_dir / 'mariadb-server.log').write_text(logs.stdout + logs.stderr)
            rm_res = _docker(['rm', '-f', '-v', name], check=False)
            for vol in volumes:
                _docker(['volume', 'rm', '-f', vol], check=False)
            proof['owned_server_stopped'] = rm_res.returncode == 0


@contextmanager
def owned_ndb_cluster_9_7(work_dir: Path):
    image = 'container-registry.oracle.com/mysql/community-cluster:9.7.0'
    work_dir.mkdir(parents=True, exist_ok=True)
    suffix = secrets.token_hex(5)
    mgm_name = f'sr-b23-mgmd-{suffix}'
    ndbd_name = f'sr-b23-ndbd-{suffix}'
    sql_name = f'sr-b23-ndbsql-{suffix}'
    containers = []
    volumes = []
    proof = {
        'image': _image_digest(image),
        'network_mode': f'container:{mgm_name}',
        'containers': [mgm_name, ndbd_name, sql_name],
        'owned_cluster_stopped': False,
    }
    try:
        cnf = work_dir / 'mysql-cluster.cnf'
        cnf.write_text(
            '[ndbd default]\n'
            'NoOfReplicas=1\n'
            'DataMemory=96M\n'
            'DiskPageBufferMemory=16M\n\n'
            '[ndb_mgmd]\n'
            'NodeId=1\n'
            'hostname=127.0.0.1\n'
            'datadir=/var/lib/mysql\n\n'
            '[ndbd]\n'
            'NodeId=2\n'
            'hostname=127.0.0.1\n'
            'datadir=/var/lib/mysql\n\n'
            '[mysqld]\n'
            'NodeId=4\n'
            'hostname=127.0.0.1\n\n'
            '[mysqld]\n'
            'NodeId=5\n'
            'hostname=127.0.0.1\n'
        )
        _docker([
            'create', '--name', mgm_name,
            '-p', '127.0.0.1::1186',
            '-p', '127.0.0.1::3306',
            image, 'ndb_mgmd', '--ndb-nodeid=1', '--config-cache=FALSE',
        ])
        containers.append(mgm_name)
        _docker(['cp', str(cnf), f'{mgm_name}:/etc/mysql-cluster.cnf'])
        _docker(['start', mgm_name])

        from pgadmin.cdeadmin.providers.mysql_family.mysql_ndb import NdbMgmClient
        mgm_port = None
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                mgm_port = _host_port(mgm_name, '1186/tcp')
                c = NdbMgmClient.connect('127.0.0.1', mgm_port, timeout=3.0)
                try:
                    st = c.get_status()
                    if st.get('node_count', 0) >= 3:
                        break
                finally:
                    c.close()
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError('ndb_mgmd did not start listening on 1186')

        _docker([
            'run', '-d', '--name', ndbd_name, f'--network=container:{mgm_name}',
            image, 'ndbd', '--ndb-nodeid=2', '--ndb-connectstring=127.0.0.1:1186',
        ])
        containers.append(ndbd_name)

        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            c = NdbMgmClient.connect('127.0.0.1', mgm_port, timeout=3.0)
            try:
                st = c.get_status()
                n2 = next((n for n in st['nodes'] if n['node_id'] == 2), None)
                if n2 and str(n2.get('status', '')).upper() == 'STARTED':
                    break
            finally:
                c.close()
            time.sleep(1.0)
        else:
            raise RuntimeError('ndbd node 2 did not reach STARTED state')

        _docker([
            'run', '-d', '--name', sql_name, f'--network=container:{mgm_name}',
            '-e', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes',
            '-e', 'MYSQL_ROOT_HOST=%',
            image, 'mysqld', '--ndbcluster', '--ndb-nodeid=4', '--ndb-connectstring=127.0.0.1:1186',
        ])
        containers.append(sql_name)

        for cname in containers:
            insp = json.loads(_docker(['inspect', cname]).stdout)[0]
            volumes.extend(m['Name'] for m in insp.get('Mounts', []) if m.get('Type') == 'volume')

        import mysql.connector
        sql_port = None
        deadline = time.monotonic() + 180
        last_err = None
        while time.monotonic() < deadline:
            try:
                sql_port = _host_port(mgm_name, '3306/tcp')
                conn = mysql.connector.connect(host='127.0.0.1', port=sql_port, user='root', connection_timeout=3)
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT VERSION(), @@server_uuid, (SELECT SUPPORT FROM information_schema.ENGINES WHERE ENGINE='ndbcluster')")
                        ver, suuid, ndb_sup = cur.fetchone()
                        if str(ver).split('-')[0] == '9.7.0' and str(ndb_sup).upper() in {'YES', 'DEFAULT'}:
                            proof.update(
                                engine_version=str(ver),
                                server_uuid=str(suuid),
                                sql_port=sql_port,
                                mgm_port=mgm_port,
                                ndbcluster_support=str(ndb_sup),
                            )
                            break
                finally:
                    conn.close()
            except Exception as exc:
                last_err = exc
                time.sleep(1.0)
        else:
            raise RuntimeError(f'NDB SQL node did not become ready with ndbcluster=YES: {last_err}')

        yield {
            'host': '127.0.0.1',
            'port': sql_port,
            'user': 'root',
            'use_pure': True,
            'mgm_host': '127.0.0.1',
            'mgm_port': mgm_port,
        }, proof
    finally:
        all_ok = True
        for cname in reversed(containers):
            logs = _docker(['logs', cname], check=False)
            (work_dir / f'{cname}.log').write_text(logs.stdout + logs.stderr)
            rm = _docker(['rm', '-f', '-v', cname], check=False)
            all_ok = all_ok and (rm.returncode == 0)
        for vol in set(volumes):
            _docker(['volume', 'rm', '-f', vol], check=False)
        proof['owned_cluster_stopped'] = all_ok


def create_flask_app(app_dir: Path):
    import base64
    import builtins
    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE = False
    config.TESTING = True
    config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False
    config.USE_OS_SECRET_STORAGE = False
    config.CDEADMIN_MONITORING_PROCESS_MODE = 'single'
    config.CDEADMIN_MONITORING_LOCK_PATH = str(app_dir / 'monitor.lock')
    config.CDEADMIN_MONITORING_WORKER_KEYS = {'k': base64.b64encode(os.urandom(32)).decode('ascii')}
    config.CDEADMIN_MONITORING_WORKER_ACTIVE_KEY_ID = 'k'
    for attr, rel in {
        'DATA_DIR': 'data',
        'SQLITE_PATH': 'data/application.db',
        'SESSION_DB_PATH': 'data/sessions',
        'STORAGE_DIR': 'data/storage',
        'LOG_FILE': 'data/application.log',
        'AZURE_CREDENTIAL_CACHE_DIR': 'data/azure',
        'CDEADMIN_OPERATION_STORE_PATH': 'data/operations.json',
    }.items():
        p = app_dir / rel
        if not rel.endswith(('.db', '.log', '.json')):
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
        setattr(config, attr, str(p))
    from pgadmin import create_app
    app = create_app('ScratchRobin-batch23-qualification')
    app.PGADMIN_RUNTIME = False
    app.PGADMIN_INT_KEY = ''
    app.run_before_app_start()
    return app


def register_http_endpoint(app, engine_id, profile_id, route, password, database):
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile

    with app.test_request_context('/'):
        owner = User.query.first()
        group = ServerGroup.query.filter_by(user_id=owner.id).order_by(ServerGroup.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility[engine_id].set(True, user_id=owner.id)
        srv = Server(
            user_id=owner.id,
            servergroup_id=group.id,
            name=f'Owned {engine_id} {secrets.token_hex(3)}',
            host=route['host'],
            port=route['port'],
            username=route.get('user', 'root'),
            maintenance_db=database,
            save_password=0,
        )
        srv._cde_endpoint_registration = registration_profile(profile_id)
        clean_route = {
            k: v for k, v in route.items()
            if k not in {'password', 'credential_reference_id', 'principal_reference', 'mgm_host', 'mgm_port', 'mysqlx_port'}
        }
        clean_route['database'] = database
        clean_route['credential_kinds'] = ['database_password']
        srv._cde_endpoint_route_configuration = clean_route
        db.session.add(srv)
        db.session.commit()
        target_id = str(uuid.uuid4())
        db.session.add(
            EndpointDatabaseTarget(
                id=target_id,
                endpoint_id=srv.endpoint_profile.id,
                display_name=database,
                database=database,
                configuration='{}',
                active=1,
            )
        )
        db.session.commit()
        sid, uid = srv.id, owner.id
        verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=sid)
        ws_url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=sid)

    http = app.test_client()
    with http.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    ver_resp = http.post(verify_url, json={'password': password}).get_json()
    assert ver_resp and ver_resp.get('success'), f'Endpoint verify failed: {ver_resp}'
    return sid, target_id, uid, ws_url, http


def ws_call(http, ws_url, target_id, action, req=None, *, expect_ok=True):
    if action.startswith('visual_admin_') or action in {'resource_page'} or action.startswith('database_target_'):
        payload = {'action': action, 'request': {'database_target_id': target_id, **(req or {})}}
    else:
        payload = {'action': action, 'database_target_id': target_id, **(req or {})}
    resp = http.post(ws_url, json=payload)
    body = resp.get_json()
    if expect_ok:
        assert resp.status_code == 200 and body.get('success'), f'{action} failed ({resp.status_code}): {body}'
        return body['data']
    return resp.status_code, body


def ws_exec_sync(http, ws_url, target_id, session_id, source):
    occ = ws_call(http, ws_url, target_id, 'execute', {'session_id': session_id, 'source': source})
    occ_id = occ['occurrence_id']
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        polled = ws_call(http, ws_url, target_id, 'poll', {'occurrence_id': occ_id})
        if polled['occurrence']['operation']['terminal']:
            return polled
        time.sleep(0.05)
    raise RuntimeError(f'Timed out polling occurrence {occ_id}')


def make_native_client(profile, password, pool_ns='b23'):
    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client
    from pgadmin.cdeadmin.security import SecretLease
    perms = SimpleNamespace(
        require=lambda *_a, **_k: None,
        allows=lambda *_a, **_k: True,
        acquire_secret=lambda *_a, **_k: SecretLease(password.encode('utf-8')),
    )
    ctx = SimpleNamespace(pool_namespace=pool_ns)
    return _create_client(profile, perms, ctx)


def source_hashes(*rel_paths):
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in rel_paths}


def run_all(output_dir: Path, tmp_root: Path):
    import mariadb
    import mysql.connector
    from pgadmin.cdeadmin.providers.mysql_family.provider import (
        MARIADB_PROFILE,
        MYSQL_PROFILE,
        _resources,
    )
    from pgadmin.cdeadmin.providers.mysql_family.mysql_monitoring import MySQLMonitor, counter_rates
    from pgadmin.cdeadmin.providers.native_editor import NativeEditorProvider
    from pgadmin.cdeadmin.sdk import RelationalClientError
    from pgadmin.cdeadmin.workspace.dashboard_validation import validate_dashboard

    output_dir.mkdir(parents=True, exist_ok=True)
    work = tmp_root / ('qual-' + secrets.token_hex(4))
    work.mkdir(parents=True, exist_ok=True)

    receipts = {}
    try:
        app = create_flask_app(work / 'flask-app')

        # ===================================================================
        # PHASE 1: Owned MySQL 9.7.0 (Identity, Flush, Explain, Component Metrics,
        #          Language Semantics, X Collections, Non-NDB Gate)
        # ===================================================================
        identity_evidence = {'mysql': [], 'mariadb': []}
        flush_evidence = {'mysql': [], 'mariadb': []}
        explain_evidence = {'interfaces': []}
        comp_metrics_evidence = {}
        lang_semantics_evidence = {}
        xcoll_evidence = {'interfaces': []}
        ndb_non_cluster_evidence = {}

        with owned_mysql_9_7(work / 'mysql97') as (my_base_route, my_fixture):
            root_pw = 'MyB23#' + secrets.token_urlsafe(18)
            lim_pw = 'LimB23#' + secrets.token_urlsafe(18)
            adm = mysql.connector.connect(host='127.0.0.1', port=my_base_route['port'], user='root', autocommit=True)
            try:
                with adm.cursor() as cur:
                    cur.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (root_pw,))
                    cur.execute('CREATE DATABASE sr_b23 CHARACTER SET utf8mb4')
                    cur.execute("CREATE USER 'sr_limited'@'%' IDENTIFIED BY %s", (lim_pw,))
                    cur.execute("GRANT SELECT, INSERT, CREATE, DROP ON sr_b23.* TO 'sr_limited'@'%'")
                    cur.execute("CREATE USER 'sr_mon_ro'@'%' IDENTIFIED BY %s", (lim_pw,))
                    cur.execute("GRANT SELECT ON performance_schema.* TO 'sr_mon_ro'@'%'")
                    cur.execute("GRANT SELECT ON sr_b23.* TO 'sr_mon_ro'@'%'")

                server_uuid = my_fixture['server_uuid']
                server_target = {
                    'resource_id': 'server:MySQL',
                    'resource_kind': 'server',
                    'display_name': 'MySQL',
                    'display_path': ['MySQL'],
                    'native': {'server_uuid': server_uuid},
                }

                # --- Native pure & C checks on MySQL 9.7.0 ---
                for use_pure in (True, False):
                    route = {
                        **my_base_route,
                        'use_pure': use_pure,
                        'database': 'sr_b23',
                        'credential_reference_id': 'root-pw',
                        'principal_reference': 'op-1',
                    }
                    lim_route = {
                        **route,
                        'user': 'sr_limited',
                        'credential_reference_id': 'lim-pw',
                    }
                    cli = make_native_client(MYSQL_PROFILE, root_pw, f'my-{use_pure}')
                    lim_cli = make_native_client(MYSQL_PROFILE, lim_pw, f'mylim-{use_pure}')
                    try:
                        # 1) MY-AUDIT-IDENTITY-01 native
                        with adm.cursor() as cur:
                            cur.execute('DROP TABLE IF EXISTS sr_b23.drop_ok, sr_b23.drop_race')
                            cur.execute('CREATE TABLE sr_b23.drop_ok (id INT PRIMARY KEY, v VARCHAR(32)) ENGINE=InnoDB')
                            cur.execute("INSERT INTO sr_b23.drop_ok VALUES (1, 'initial')")
                            cur.execute('CREATE TABLE sr_b23.drop_race (id INT PRIMARY KEY, v VARCHAR(32)) ENGINE=InnoDB')
                            cur.execute("INSERT INTO sr_b23.drop_race VALUES (1, 'old')")

                        res_list = _resources(adm, {'route': {'database': 'sr_b23'}}, MYSQL_PROFILE)
                        t_ok = next(r for r in res_list if r['resource_kind'] == 'table' and r['display_name'] == 'drop_ok')
                        t_race = next(r for r in res_list if r['resource_kind'] == 'table' and r['display_name'] == 'drop_race')

                        plan_ok = cli.plan_admin_operation({
                            'resource_kind': 'table',
                            'operation_id': 'drop',
                            'target_resource': t_ok,
                            'draft': {'confirmation': 'drop_ok'},
                            '_provider_route': route,
                        })
                        id_obs_ok = plan_ok['command_preview']['native_target_identity']
                        assert id_obs_ok['innodb_table_id'] and id_obs_ok['server_identity']['server_uuid'] == server_uuid
                        # Prove no lock held during review
                        with adm.cursor() as cur:
                            cur.execute("INSERT INTO sr_b23.drop_ok VALUES (2, 'unlocked_during_review')")
                        apply_ok = cli.apply_admin_operation(plan_ok)
                        assert apply_ok['accepted'] is True
                        # Replay refused
                        replay_refused = False
                        try:
                            cli.apply_admin_operation(plan_ok)
                        except RelationalClientError:
                            replay_refused = True
                        assert replay_refused

                        # Same-name replacement refused with replacement table + rows preserved
                        plan_race = cli.plan_admin_operation({
                            'resource_kind': 'table',
                            'operation_id': 'drop',
                            'target_resource': t_race,
                            'draft': {'confirmation': 'drop_race'},
                            '_provider_route': route,
                        })
                        old_tid = plan_race['command_preview']['native_target_identity']['innodb_table_id']
                        with adm.cursor() as cur:
                            cur.execute('DROP TABLE sr_b23.drop_race')
                            cur.execute('CREATE TABLE sr_b23.drop_race (id INT PRIMARY KEY, v VARCHAR(32)) ENGINE=InnoDB')
                            cur.execute("INSERT INTO sr_b23.drop_race VALUES (99, 'replacement_preserved')")
                        race_refused = False
                        try:
                            cli.apply_admin_operation(plan_race)
                        except RelationalClientError as err:
                            race_refused = getattr(err, 'stale_target_conflict', False) and not getattr(err, 'native_dispatched', True)
                        assert race_refused
                        with adm.cursor() as cur:
                            cur.execute('SELECT id, v FROM sr_b23.drop_race')
                            assert cur.fetchall() == [(99, 'replacement_preserved')]

                        # Cross-server UUID mismatch refused during review
                        wrong_srv_refused = False
                        try:
                            cli.plan_admin_operation({
                                'resource_kind': 'table',
                                'operation_id': 'drop',
                                'target_resource': {**t_race, 'native': {**t_race['native'], 'server_uuid': '00000000-0000-0000-0000-000000000000'}},
                                'draft': {'confirmation': 'drop_race'},
                                '_provider_route': route,
                            })
                        except RelationalClientError as err:
                            wrong_srv_refused = getattr(err, 'conflict_reason', '') == 'server_identity_mismatch'
                        assert wrong_srv_refused
                        identity_evidence['mysql'].append({
                            'use_pure': use_pure,
                            'observed_table_id': old_tid,
                            'valid_drop_succeeded': True,
                            'unlocked_during_review_verified': True,
                            'same_name_replacement_refused_and_rows_preserved': True,
                            'cross_server_mismatch_refused': True,
                            'replay_refused': True,
                        })

                        # 2) MY-AUDIT-FLUSH native
                        fl_plan = cli.plan_admin_operation({
                            'resource_kind': 'server',
                            'operation_id': 'flush',
                            'target_resource': server_target,
                            'draft': {'targets': ['STATUS', 'OPTIMIZER_COSTS', 'ENGINE LOGS'], 'binlog_mode': 'NO_WRITE_TO_BINLOG', 'confirmation': 'MySQL'},
                            '_provider_route': route,
                        })
                        fl_res = cli.apply_admin_operation(fl_plan)
                        assert fl_res['flush_observation']['native_acknowledged'] is True

                        # Retained-session table FLUSH WITH READ LOCK + UNLOCK
                        ret_sess = cli.open_session({'route': route})
                        try:
                            t_lock_plan = cli.plan_admin_operation({
                                'resource_kind': 'table',
                                'operation_id': 'flush',
                                'session_id': 'retained-1',
                                'target_resource': t_race,
                                'draft': {'lock_mode': 'WITH_READ_LOCK', 'confirmation': 'drop_race'},
                                '_provider_route': route,
                            })
                            t_lock_res = cli.apply_admin_operation({**t_lock_plan, '_provider_session_handle': ret_sess})
                            assert t_lock_res['flush_observation']['retained_lock_active'] is True
                            t_unlock_plan = cli.plan_admin_operation({
                                'resource_kind': 'table',
                                'operation_id': 'flush',
                                'session_id': 'retained-1',
                                'target_resource': t_race,
                                'draft': {'lock_mode': 'UNLOCK', 'confirmation': 'drop_race'},
                                '_provider_route': route,
                            })
                            t_unlock_res = cli.apply_admin_operation({**t_unlock_plan, '_provider_session_handle': ret_sess})
                            assert t_unlock_res['flush_observation']['retained_lock_active'] is False
                        finally:
                            cli.close_session(ret_sess)

                        # Restricted user FLUSH denied with 1227
                        lim_fl_plan = lim_cli.plan_admin_operation({
                            'resource_kind': 'server',
                            'operation_id': 'flush',
                            'target_resource': server_target,
                            'draft': {'targets': ['STATUS'], 'binlog_mode': 'LOCAL', 'confirmation': 'MySQL'},
                            '_provider_route': lim_route,
                        })
                        denied_1227 = False
                        try:
                            lim_cli.apply_admin_operation(lim_fl_plan)
                        except RelationalClientError as err:
                            denied_1227 = getattr(err, 'errno', None) == 1227
                        assert denied_1227
                        flush_evidence['mysql'].append({
                            'use_pure': use_pure,
                            'server_flush_acknowledged': True,
                            'retained_table_lock_and_unlock_verified': True,
                            'restricted_1227_denied': True,
                        })

                        # 3) MY-AUDIT-EXPLAIN_FOR_CONNECTION native
                        bg_conn = mysql.connector.connect(
                            host='127.0.0.1', port=my_base_route['port'], user='root', password=root_pw,
                            database='sr_b23', autocommit=True, use_pure=use_pure,
                        )
                        with bg_conn.cursor() as bcur:
                            bcur.execute('SELECT CONNECTION_ID()')
                            bg_cid = str(bcur.fetchone()[0])

                        # Idle connection check (returns structured idle_no_explainable_statement without executing SQL)
                        idle_plan = cli.plan_admin_operation({
                            'resource_kind': 'server',
                            'operation_id': 'explain_for_connection',
                            'target_resource': server_target,
                            'draft': {'connection_id': bg_cid, 'output_format': 'JSON', 'private_data_confirmed': True, 'confirmation': 'MySQL'},
                            '_provider_route': route,
                        })
                        idle_res = cli.apply_admin_operation(idle_plan)
                        assert idle_res['live_plan']['plan_state'] == 'idle_no_explainable_statement'

                        # Non-explainable running statement (DO SLEEP(4)) returns native MySQL errno 3012
                        def run_non_explainable():
                            c = bg_conn.cursor()
                            try:
                                c.execute('DO SLEEP(4)')
                                c.fetchall()
                            except Exception:
                                pass
                            finally:
                                c.close()

                        ne_worker = threading.Thread(target=run_non_explainable, daemon=True)
                        ne_worker.start()
                        non_explainable_3012 = False
                        try:
                            deadline = time.monotonic() + 5
                            while time.monotonic() < deadline:
                                with adm.cursor() as cur:
                                    cur.execute('SELECT PROCESSLIST_COMMAND FROM performance_schema.threads WHERE PROCESSLIST_ID = %s', (int(bg_cid),))
                                    r = cur.fetchone()
                                    if r and r[0] == 'Query':
                                        break
                                time.sleep(0.05)
                            nep = cli.plan_admin_operation({
                                'resource_kind': 'server',
                                'operation_id': 'explain_for_connection',
                                'target_resource': server_target,
                                'draft': {'connection_id': bg_cid, 'output_format': 'JSON', 'private_data_confirmed': True, 'confirmation': 'MySQL'},
                                '_provider_route': route,
                            })
                            try:
                                cli.apply_admin_operation(nep)
                            except RelationalClientError as err:
                                non_explainable_3012 = getattr(err, 'errno', None) == 3012
                            assert non_explainable_3012
                        finally:
                            with adm.cursor() as cur:
                                cur.execute(f'KILL QUERY {int(bg_cid)}')
                            ne_worker.join(timeout=5)

                        # Active running query across TRADITIONAL, JSON, TREE
                        def run_slow():
                            c = bg_conn.cursor()
                            try:
                                c.execute('SELECT id, v, SLEEP(4) FROM sr_b23.drop_race')
                                c.fetchall()
                            except Exception:
                                pass
                            finally:
                                c.close()

                        worker = threading.Thread(target=run_slow, daemon=True)
                        worker.start()
                        try:
                            deadline = time.monotonic() + 5
                            while time.monotonic() < deadline:
                                with adm.cursor() as cur:
                                    cur.execute('SELECT PROCESSLIST_COMMAND FROM performance_schema.threads WHERE PROCESSLIST_ID = %s', (int(bg_cid),))
                                    r = cur.fetchone()
                                    if r and r[0] == 'Query':
                                        break
                                time.sleep(0.05)
                            fmt_outputs = {}
                            for fmt in ('TRADITIONAL', 'JSON', 'TREE'):
                                ep = cli.plan_admin_operation({
                                    'resource_kind': 'server',
                                    'operation_id': 'explain_for_connection',
                                    'target_resource': server_target,
                                    'draft': {'connection_id': bg_cid, 'output_format': fmt, 'private_data_confirmed': True, 'confirmation': 'MySQL'},
                                    '_provider_route': route,
                                })
                                er = cli.apply_admin_operation(ep)
                                assert er['live_plan']['plan_state'] == 'captured' and er['live_plan']['rows']
                                fmt_outputs[fmt] = len(er['live_plan']['rows'])

                            # Restricted non-owner without PROCESS refused when targeting root's connection
                            non_owner_refused = False
                            try:
                                lp = lim_cli.plan_admin_operation({
                                    'resource_kind': 'server',
                                    'operation_id': 'explain_for_connection',
                                    'target_resource': server_target,
                                    'draft': {'connection_id': bg_cid, 'output_format': 'JSON', 'private_data_confirmed': True, 'confirmation': 'MySQL'},
                                    '_provider_route': lim_route,
                                })
                                lim_cli.apply_admin_operation(lp)
                            except RelationalClientError:
                                non_owner_refused = True
                            assert non_owner_refused
                        finally:
                            with adm.cursor() as cur:
                                cur.execute(f'KILL QUERY {int(bg_cid)}')
                            worker.join(timeout=5)
                            bg_conn.close()

                        # Unknown connection ID (1094 / invisible) refused cleanly
                        unknown_refused = False
                        try:
                            up = cli.plan_admin_operation({
                                'resource_kind': 'server',
                                'operation_id': 'explain_for_connection',
                                'target_resource': server_target,
                                'draft': {'connection_id': '99999999', 'output_format': 'JSON', 'private_data_confirmed': True, 'confirmation': 'MySQL'},
                                '_provider_route': route,
                            })
                            cli.apply_admin_operation(up)
                        except RelationalClientError:
                            unknown_refused = True
                        assert unknown_refused
                        explain_evidence['interfaces'].append({
                            'use_pure': use_pure,
                            'formats_captured_rows': fmt_outputs,
                            'idle_state': idle_res['live_plan']['plan_state'],
                            'non_explainable_3012_verified': non_explainable_3012,
                            'non_owner_without_process_refused': True,
                            'unknown_thread_refused': True,
                        })

                        # 6) MY-AUDIT-XCOLLECTIONS native
                        with adm.cursor() as cur:
                            cur.execute('DROP TABLE IF EXISTS sr_b23.plain_json_sql, sr_b23.orders_x')
                            cur.execute('CREATE TABLE sr_b23.plain_json_sql (id INT PRIMARY KEY, doc JSON)')

                        def x_exec(op, draft, tgt=None):
                            p = cli.plan_admin_operation({
                                'resource_kind': 'x-collection',
                                'operation_id': op,
                                'target_resource': tgt,
                                'draft': {**draft, 'mysqlx_port': my_base_route['mysqlx_port']},
                                '_provider_route': route,
                            })
                            return cli.apply_admin_operation(p)['xcollection_result']

                        db_target = {'resource_kind': 'database', 'display_name': 'sr_b23', 'display_path': ['sr_b23']}
                        created_x = x_exec('create', {'database': 'sr_b23', 'name': 'orders_x', 'validation_level': 'OFF'}, db_target)
                        assert created_x['after']['object_type'] == 'COLLECTION'

                        # Verify catalog discovery distinguishes orders_x from plain_json_sql
                        disc = _resources(adm, {'route': {'database': 'sr_b23'}}, MYSQL_PROFILE)
                        x_names = [r['display_name'] for r in disc if r['resource_kind'] == 'x-collection']
                        assert x_names == ['orders_x'] and 'plain_json_sql' not in x_names
                        coll_target = next(r for r in disc if r['resource_kind'] == 'x-collection' and r['display_name'] == 'orders_x')

                        # Ensure & strict schema validation
                        strict_schema = json.dumps({
                            'type': 'object',
                            'properties': {'sku': {'type': 'string'}, 'qty': {'type': 'integer'}},
                            'required': ['sku', 'qty'],
                        })
                        mod_opt = x_exec('modify_options', {
                            'validation_level': 'STRICT',
                            'validation_schema': strict_schema,
                            'confirmation': 'orders_x',
                        }, coll_target)
                        assert mod_opt['after']['validation']['level'] == 'strict'

                        # Invalid doc rejected by X Plugin (5180)
                        invalid_doc_errno = None
                        try:
                            x_exec('insert_documents', {
                                'documents': [{'document': '{"sku": "A1", "qty": "not_an_int"}'}],
                                'confirmation': 'orders_x',
                            }, coll_target)
                        except RelationalClientError as err:
                            invalid_doc_errno = getattr(err, 'errno', None)
                        assert invalid_doc_errno == 5180

                        # Valid CRUD + index lifecycle
                        ins_res = x_exec('insert_documents', {
                            'documents': [
                                {'document': '{"_id": "d1", "sku": "A1", "qty": 5}'},
                                {'document': '{"_id": "d2", "sku": "B2", "qty": 12}'},
                            ],
                            'confirmation': 'orders_x',
                        }, coll_target)
                        assert ins_res['rows_affected'] == 2
                        fnd_res = x_exec('find_documents', {
                            'predicates': [{'path': '$.qty', 'operator': '>', 'value_type': 'INTEGER', 'value': '6'}],
                            'confirmation': 'orders_x',
                        }, coll_target)
                        assert len(fnd_res['documents']) == 1 and fnd_res['documents'][0]['sku'] == 'B2'
                        upd_res = x_exec('modify_documents', {
                            'predicates': [{'path': '$.sku', 'operator': '==', 'value_type': 'STRING', 'value': 'B2'}],
                            'updates': [{'operation': 'ITEM_SET', 'path': '$.qty', 'value_type': 'INTEGER', 'value': '20'}],
                            'confirmation': 'orders_x',
                        }, coll_target)
                        assert upd_res['rows_affected'] == 1
                        x_exec('create_index', {
                            'index_name': 'idx_sku',
                            'index_type': 'INDEX',
                            'fields': [{'field': '$.sku', 'type': 'TEXT(32)', 'required': True}],
                            'confirmation': 'orders_x',
                        }, coll_target)
                        x_exec('drop_index', {'index_name': 'idx_sku', 'confirmation': 'orders_x'}, coll_target)
                        del_res = x_exec('remove_documents', {
                            'predicates': [{'path': '$.sku', 'operator': '==', 'value_type': 'STRING', 'value': 'A1'}],
                            'confirmation': 'orders_x',
                        }, coll_target)
                        assert del_res['rows_affected'] == 1
                        drp_res = x_exec('drop', {'confirmation': 'orders_x'}, coll_target)
                        assert drp_res['after']['exists'] is False

                        xcoll_evidence['interfaces'].append({
                            'use_pure': use_pure,
                            'ordinary_json_table_excluded': True,
                            'strict_schema_5180_enforced': True,
                            'crud_and_index_lifecycle_passed': True,
                        })
                    finally:
                        cli.close()
                        lim_cli.close()

                # 4) MY-AUDIT-COMPONENT-METRICS (native + DDN publication + HTTP monitoring)
                from pgadmin.cdeadmin.security import SecretLease
                mon_route = {
                    'host': '127.0.0.1',
                    'port': my_base_route['port'],
                    'user': 'root',
                    'database': 'sr_b23',
                    'use_pure': True,
                    'credential_reference_id': 'mon-pw',
                    'principal_reference': 'mon-op',
                }
                mon = MySQLMonitor(
                    SimpleNamespace(
                        require=lambda *_a, **_k: None,
                        allows=lambda *_a, **_k: True,
                        acquire_secret=lambda *_a, **_k: SecretLease(root_pw.encode('utf-8')),
                    ),
                    mon_route,
                )
                try:
                    s_before = mon.sample()
                    assert s_before['groups']['component_replication_applier_metrics']['status'] == 'not_installed'
                    assert s_before['groups']['component_group_replication_flow_control']['status'] == 'not_installed'

                    with adm.cursor() as cur:
                        cur.execute("INSTALL COMPONENT 'file://component_replication_applier_metrics'")
                        cur.execute("INSTALL PLUGIN group_replication SONAME 'group_replication.so'")
                        cur.execute("INSTALL COMPONENT 'file://component_group_replication_flow_control_stats'")
                    try:
                        s_inst1 = mon.sample()
                        time.sleep(0.2)
                        s_inst2 = mon.sample()
                        assert s_inst2['groups']['component_replication_applier_metrics']['status'] == 'available'
                        assert s_inst2['groups']['component_replication_applier_worker_progress']['status'] == 'available'
                        assert s_inst2['groups']['component_group_replication_flow_control']['status'] == 'available'
                        assert 'Gr_flow_control_throttle_count' in s_inst2['rates']['per_second']

                        # Read-only monitoring user check
                        ro_mon = MySQLMonitor(
                            SimpleNamespace(
                                require=lambda *_a, **_k: None,
                                allows=lambda *_a, **_k: True,
                                acquire_secret=lambda *_a, **_k: SecretLease(lim_pw.encode('utf-8')),
                            ),
                            {**mon_route, 'user': 'sr_mon_ro', 'credential_reference_id': 'mon-ro'},
                        )
                        try:
                            s_ro = ro_mon.sample()
                            assert s_ro['groups']['component_replication_applier_metrics']['status'] == 'available'
                            assert s_ro['groups']['component_group_replication_flow_control']['status'] == 'available'
                        finally:
                            ro_mon.close()

                        # DDN published dashboard validation & live binding resolution
                        ddn_check = json.loads(subprocess.check_output([
                            'node', '--input-type=module', '-e',
                            f"""
                            import {{ mysqlDashboardFiles }} from './web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/mysqlDashboard.js';
                            const sample = {json.dumps(s_inst2)};
                            const snap = {{ state: 'collecting', sample_age_seconds: 0.5, stale_after_seconds: 30, samples: [sample] }};
                            const files = mysqlDashboardFiles(snap, 'database', 'mysql');
                            process.stdout.write(JSON.stringify({{ format: 'ddn-source-workspace@1', entry: 'dashboard.ddn', view: 'dashboard', files }}));
                            """
                        ], cwd=ROOT, text=True))
                        validated_ddn = validate_dashboard(ddn_check, 'database', engine='mysql')
                        assert 'mysql_gr_flow_control_' in validated_ddn['files']['dashboard.ddn']

                        # Authenticated HTTP monitoring (NO /history calls!)
                        sid_my, tid_my, _uid_my, ws_my, http_my = register_http_endpoint(
                            app, 'mysql', 'mysql-native', my_base_route, root_pw, 'sr_b23'
                        )
                        mon_url = f'/cdeadmin/api/monitoring/mysql/{sid_my}?target_id={tid_my}'
                        r_start = http_my.post(mon_url, json={
                            'interval_seconds': 5,
                            'credentials': {'username': 'root', 'password': root_pw},
                        })
                        assert r_start.status_code == 200 and r_start.get_json()['success']
                        deadline = time.monotonic() + 12
                        http_comp_ok = False
                        while time.monotonic() < deadline:
                            snap = http_my.get(mon_url).get_json()['data']
                            if snap.get('samples'):
                                latest = snap['samples'][-1]
                                if latest['groups']['component_group_replication_flow_control']['status'] == 'available':
                                    http_comp_ok = True
                                    break
                            time.sleep(0.5)
                        http_my.delete(mon_url)
                        assert http_comp_ok
                    finally:
                        with adm.cursor() as cur:
                            cur.execute("UNINSTALL COMPONENT 'file://component_group_replication_flow_control_stats'")
                            cur.execute('UNINSTALL PLUGIN group_replication')
                            cur.execute("UNINSTALL COMPONENT 'file://component_replication_applier_metrics'")

                    s_after = mon.sample()
                    assert s_after['groups']['component_replication_applier_metrics']['status'] == 'not_installed'
                    assert s_after['groups']['component_group_replication_flow_control']['status'] == 'not_installed'
                    comp_metrics_evidence = {
                        'before_install_status': 'not_installed',
                        'installed_applier_metrics_status': 'available',
                        'installed_gr_flow_control_status': 'available',
                        'readonly_account_verified': True,
                        'ddn_published_dashboard_validated': True,
                        'http_monitoring_verified': True,
                        'after_uninstall_status': 'not_installed',
                        'history_tested': False,
                    }
                finally:
                    mon.close()

                # 5) MY-AUDIT-LANGUAGE-SEMANTICS & HTTP checks for Identity / Flush / Explain / XCollections / Non-NDB Gate
                # Open interactive session over authenticated HTTP
                opened = ws_call(http_my, ws_my, tid_my, 'open_session', {'language_profile': 'mysql-sql'})
                http_sess_id = opened['session_id']
                try:
                    v_body = ws_call(http_my, ws_my, tid_my, 'source_validate', {
                        'session_id': http_sess_id,
                        'source': 'CREATE TABLE sr_b23.never_created_by_validate (id INT PRIMARY KEY)',
                    })
                    assert v_body['grammar_valid'] is True
                    assert v_body['context_mode'] == 'live_session'
                    assert v_body['catalog_binding_status'] == 'unknown'
                    assert v_body['privilege_evaluation'] == 'not_evaluated'
                    assert v_body['execution_verified'] is False
                    with adm.cursor() as cur:
                        cur.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='sr_b23' AND TABLE_NAME='never_created_by_validate'")
                        assert cur.fetchone()[0] == 0

                    val_nonexistent = ws_call(http_my, ws_my, tid_my, 'source_validate', {
                        'session_id': http_sess_id,
                        'source': 'SELECT * FROM sr_b23.nonexistent_future_table_xyz WHERE a = 1',
                    })
                    assert val_nonexistent['grammar_valid'] is True
                    assert val_nonexistent['catalog_binding_status'] == 'unknown'
                    assert val_nonexistent['privilege_evaluation'] == 'not_evaluated'
                    assert val_nonexistent['execution_verified'] is False

                    # Script-unconfirmed multi-statement validation check
                    val_script = ws_call(http_my, ws_my, tid_my, 'source_validate', {
                        'session_id': http_sess_id,
                        'source': 'CREATE TABLE sr_b23.future_a (id INT); SELECT id FROM sr_b23.future_a',
                        'script': True,
                    })
                    assert val_script['grammar_valid'] is True
                    assert val_script['context_mode'] == 'script_unconfirmed'
                    assert val_script['catalog_binding_status'] == 'unknown'
                    assert val_script['execution_verified'] is False

                    # Create temporary table in retained session, refresh_session_metadata -> retained_snapshot -> execute -> live_session
                    ws_exec_sync(http_my, ws_my, tid_my, http_sess_id, 'CREATE TEMPORARY TABLE sr_b23.tmp_sem (k INT)')
                    ref_plan = ws_call(http_my, ws_my, tid_my, 'visual_admin_plan', {
                        'session_id': http_sess_id,
                        'resource_kind': 'server',
                        'operation_id': 'refresh_session_metadata',
                        'target_resource': server_target,
                        'draft': {
                            'confirmation': 'MySQL',
                            'replace_diagnostics': True,
                            'temporary_tables': [{'database': 'sr_b23', 'name': 'tmp_sem'}],
                        },
                    })
                    ws_call(http_my, ws_my, tid_my, 'visual_admin_apply', {
                        'session_id': http_sess_id,
                        'plan_id': ref_plan['plan_id'],
                        'plan_digest': ref_plan['plan_digest'],
                        'confirmed': True,
                    })
                    comp_snap = ws_call(http_my, ws_my, tid_my, 'source_complete', {
                        'session_id': http_sess_id,
                        'source': 'SELECT * FROM ',
                        'source_before_cursor': 'SELECT * FROM ',
                    })['editor_context']
                    assert comp_snap['context_mode'] == 'retained_snapshot'
                    assert comp_snap['catalog_binding_status'] == 'unknown'
                    assert comp_snap['privilege_evaluation'] == 'not_evaluated'
                    assert comp_snap['execution_verified'] is False

                    # Any subsequent session command invalidates snapshot back to live_session
                    ws_exec_sync(http_my, ws_my, tid_my, http_sess_id, 'SELECT 1')
                    comp_after = ws_call(http_my, ws_my, tid_my, 'source_complete', {
                        'session_id': http_sess_id,
                        'source': 'SELECT * FROM ',
                        'source_before_cursor': 'SELECT * FROM ',
                    })['editor_context']
                    assert comp_after['context_mode'] == 'live_session'
                    lang_semantics_evidence = {
                        'non_execution_verified': True,
                        'nonexistent_table_grammar_valid_unknown_binding': True,
                        'script_unconfirmed_verified': True,
                        'retained_snapshot_and_immediate_invalidation_verified': True,
                        'http_verified': True,
                    }
                finally:
                    ws_call(http_my, ws_my, tid_my, 'close_session', {'session_id': http_sess_id})

                # HTTP checks for Identity, Flush, Explain, XCollections, and Non-NDB Gate
                with adm.cursor() as cur:
                    cur.execute('CREATE TABLE sr_b23.http_drop_tbl (id INT PRIMARY KEY) ENGINE=InnoDB')
                h_tbl = next(r for r in _resources(adm, {'route': {'database': 'sr_b23'}}, MYSQL_PROFILE)
                             if r['resource_kind'] == 'table' and r['display_name'] == 'http_drop_tbl')
                hp_drop = ws_call(http_my, ws_my, tid_my, 'visual_admin_plan', {
                    'resource_kind': 'table',
                    'operation_id': 'drop',
                    'target_resource': h_tbl,
                    'draft': {'confirmation': 'http_drop_tbl'},
                })
                assert hp_drop['command_preview']['native_target_identity']['innodb_table_id']
                ws_call(http_my, ws_my, tid_my, 'visual_admin_apply', {
                    'plan_id': hp_drop['plan_id'],
                    'plan_digest': hp_drop['plan_digest'],
                    'confirmed': True,
                })
                identity_evidence['mysql_http_verified'] = True

                hp_flush = ws_call(http_my, ws_my, tid_my, 'visual_admin_plan', {
                    'resource_kind': 'server',
                    'operation_id': 'flush',
                    'target_resource': server_target,
                    'draft': {'targets': ['STATUS'], 'binlog_mode': 'NO_WRITE_TO_BINLOG', 'confirmation': 'MySQL'},
                })
                ws_call(http_my, ws_my, tid_my, 'visual_admin_apply', {
                    'plan_id': hp_flush['plan_id'],
                    'plan_digest': hp_flush['plan_digest'],
                    'confirmed': True,
                })
                flush_evidence['mysql_http_verified'] = True

                with adm.cursor() as cur:
                    cur.execute('SELECT CONNECTION_ID()')
                    adm_cid = str(cur.fetchone()[0])
                hp_exp = ws_call(http_my, ws_my, tid_my, 'visual_admin_plan', {
                    'resource_kind': 'server',
                    'operation_id': 'explain_for_connection',
                    'target_resource': server_target,
                    'draft': {'connection_id': adm_cid, 'output_format': 'JSON', 'private_data_confirmed': True, 'confirmation': 'MySQL'},
                })
                ws_call(http_my, ws_my, tid_my, 'visual_admin_apply', {
                    'plan_id': hp_exp['plan_id'],
                    'plan_digest': hp_exp['plan_digest'],
                    'confirmed': True,
                })
                explain_evidence['http_verified'] = True

                hp_xc = ws_call(http_my, ws_my, tid_my, 'visual_admin_plan', {
                    'resource_kind': 'x-collection',
                    'operation_id': 'create',
                    'target_resource': {'resource_kind': 'database', 'display_name': 'sr_b23', 'display_path': ['sr_b23']},
                    'draft': {'database': 'sr_b23', 'name': 'http_coll', 'validation_level': 'OFF', 'mysqlx_port': my_base_route['mysqlx_port']},
                })
                ws_call(http_my, ws_my, tid_my, 'visual_admin_apply', {
                    'plan_id': hp_xc['plan_id'],
                    'plan_digest': hp_xc['plan_digest'],
                    'confirmed': True,
                })
                xcoll_evidence['http_verified'] = True

                # 7a) Non-NDB capability gate over HTTP & native on standard mysql:9.7.0
                ndb_status, ndb_body = ws_call(http_my, ws_my, tid_my, 'visual_admin_plan', {
                    'resource_kind': 'logfile-group',
                    'operation_id': 'create',
                    'draft': {'name': 'lg_fail', 'undofile': 'u1.log', 'initial_size': 16777216},
                }, expect_ok=False)
                assert ndb_status != 200 or not ndb_body.get('success')
                ndb_non_cluster_evidence = {
                    'standard_mysql_9_7_refused_before_dispatch': True,
                    'http_status': ndb_status,
                }
            finally:
                adm.close()

        # ===================================================================
        # PHASE 2: Owned MariaDB 12.2.2 (MA-AUDIT-IDENTITY & MA-AUDIT-FLUSH)
        # ===================================================================
        with owned_mariadb_12_2(work / 'mariadb122') as (ma_base_route, ma_fixture):
            ma_pw = 'MaB23#' + secrets.token_urlsafe(18)
            ma_lim_pw = 'MaLim#' + secrets.token_urlsafe(18)
            madm = mariadb.connect(host='127.0.0.1', port=ma_base_route['port'], user='root', autocommit=True)
            try:
                with madm.cursor() as cur:
                    cur.execute("CREATE USER 'sr_ma_admin'@'%' IDENTIFIED BY ?", (ma_pw,))
                    cur.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_ma_admin'@'%' WITH GRANT OPTION")
                    cur.execute('CREATE DATABASE sr_ma_b23 CHARACTER SET utf8mb4')
                    cur.execute("CREATE USER 'ma_limited'@'%' IDENTIFIED BY ?", (ma_lim_pw,))
                    cur.execute("GRANT SELECT, INSERT, CREATE, DROP ON sr_ma_b23.* TO 'ma_limited'@'%'")
            finally:
                madm.close()

            ma_base_route = {**ma_base_route, 'user': 'sr_ma_admin'}
            madm = mariadb.connect(host='127.0.0.1', port=ma_base_route['port'], user='sr_ma_admin', password=ma_pw, autocommit=True)
            try:
                server_uid = ma_fixture['server_uid']
                ma_srv_target = {
                    'resource_id': 'server:MariaDB',
                    'resource_kind': 'server',
                    'display_name': 'MariaDB',
                    'display_path': ['MariaDB'],
                    'native': {'server_uid': server_uid},
                }
                ma_route = {
                    **ma_base_route,
                    'database': 'sr_ma_b23',
                    'credential_reference_id': 'ma-pw',
                    'principal_reference': 'ma-op',
                }
                ma_lim_route = {**ma_route, 'user': 'ma_limited', 'credential_reference_id': 'ma-lim'}
                ma_cli = make_native_client(MARIADB_PROFILE, ma_pw, 'ma-root')
                ma_lim_cli = make_native_client(MARIADB_PROFILE, ma_lim_pw, 'ma-lim')
                try:
                    # MA-AUDIT-IDENTITY native
                    with madm.cursor() as cur:
                        cur.execute('CREATE TABLE sr_ma_b23.ma_drop_ok (id INT PRIMARY KEY, v VARCHAR(32)) ENGINE=InnoDB')
                        cur.execute('CREATE TABLE sr_ma_b23.ma_drop_race (id INT PRIMARY KEY, v VARCHAR(32)) ENGINE=InnoDB')
                        cur.execute("INSERT INTO sr_ma_b23.ma_drop_race VALUES (1, 'initial')")
                    ma_res_list = _resources(madm, {'route': {'database': 'sr_ma_b23'}}, MARIADB_PROFILE)
                    mt_ok = next(r for r in ma_res_list if r['resource_kind'] == 'table' and r['display_name'] == 'ma_drop_ok')
                    mt_race = next(r for r in ma_res_list if r['resource_kind'] == 'table' and r['display_name'] == 'ma_drop_race')

                    mp_ok = ma_cli.plan_admin_operation({
                        'resource_kind': 'table',
                        'operation_id': 'drop',
                        'target_resource': mt_ok,
                        'draft': {'confirmation': 'ma_drop_ok'},
                        '_provider_route': ma_route,
                    })
                    assert mp_ok['command_preview']['native_target_identity']['innodb_table_id']
                    assert ma_cli.apply_admin_operation(mp_ok)['accepted'] is True

                    mp_race = ma_cli.plan_admin_operation({
                        'resource_kind': 'table',
                        'operation_id': 'drop',
                        'target_resource': mt_race,
                        'draft': {'confirmation': 'ma_drop_race'},
                        '_provider_route': ma_route,
                    })
                    with madm.cursor() as cur:
                        cur.execute('DROP TABLE sr_ma_b23.ma_drop_race')
                        cur.execute('CREATE TABLE sr_ma_b23.ma_drop_race (id INT PRIMARY KEY, v VARCHAR(32)) ENGINE=InnoDB')
                        cur.execute("INSERT INTO sr_ma_b23.ma_drop_race VALUES (77, 'kept_on_mariadb')")
                    ma_race_refused = False
                    try:
                        ma_cli.apply_admin_operation(mp_race)
                    except RelationalClientError as err:
                        ma_race_refused = getattr(err, 'stale_target_conflict', False)
                    assert ma_race_refused
                    with madm.cursor() as cur:
                        cur.execute('SELECT id, v FROM sr_ma_b23.ma_drop_race')
                        assert cur.fetchall() == [(77, 'kept_on_mariadb')]

                    # MA-AUDIT-FLUSH native (including QUERY_RESPONSE_TIME plugin check + restricted 1227)
                    mf_plan = ma_cli.plan_admin_operation({
                        'resource_kind': 'server',
                        'operation_id': 'flush',
                        'target_resource': ma_srv_target,
                        'draft': {'targets': ['STATUS', 'HOSTS', 'USER_STATISTICS', 'TABLE_STATISTICS', 'SSL'], 'binlog_mode': 'NO_WRITE_TO_BINLOG', 'confirmation': 'MariaDB'},
                        '_provider_route': ma_route,
                    })
                    assert ma_cli.apply_admin_operation(mf_plan)['flush_observation']['native_acknowledged'] is True

                    # QUERY_RESPONSE_TIME uninstalled -> refused -> install -> succeeds -> uninstall
                    qrt_refused = False
                    try:
                        ma_cli.plan_admin_operation({
                            'resource_kind': 'server',
                            'operation_id': 'flush',
                            'target_resource': ma_srv_target,
                            'draft': {'targets': ['QUERY_RESPONSE_TIME'], 'confirmation': 'MariaDB'},
                            '_provider_route': ma_route,
                        })
                    except RelationalClientError as err:
                        qrt_refused = getattr(err, 'error_code', None) == 'plugin_not_installed'
                    assert qrt_refused

                    with madm.cursor() as cur:
                        cur.execute("INSTALL SONAME 'query_response_time'")
                    try:
                        qrt_plan = ma_cli.plan_admin_operation({
                            'resource_kind': 'server',
                            'operation_id': 'flush',
                            'target_resource': ma_srv_target,
                            'draft': {'targets': ['QUERY_RESPONSE_TIME'], 'confirmation': 'MariaDB'},
                            '_provider_route': ma_route,
                        })
                        assert ma_cli.apply_admin_operation(qrt_plan)['flush_observation']['native_acknowledged'] is True
                    finally:
                        with madm.cursor() as cur:
                            cur.execute("UNINSTALL SONAME 'query_response_time'")

                    # Restricted account FLUSH denied with 1227
                    ma_lim_plan = ma_lim_cli.plan_admin_operation({
                        'resource_kind': 'server',
                        'operation_id': 'flush',
                        'target_resource': ma_srv_target,
                        'draft': {'targets': ['HOSTS'], 'binlog_mode': 'LOCAL', 'confirmation': 'MariaDB'},
                        '_provider_route': ma_lim_route,
                    })
                    ma_denied_1227 = False
                    try:
                        ma_lim_cli.apply_admin_operation(ma_lim_plan)
                    except RelationalClientError as err:
                        ma_denied_1227 = getattr(err, 'errno', None) == 1227
                    assert ma_denied_1227

                    # Authenticated HTTP on MariaDB 12.2.2
                    sid_ma, tid_ma, _uid_ma, ws_ma, http_ma = register_http_endpoint(
                        app, 'mariadb', 'mariadb-native', ma_base_route, ma_pw, 'sr_ma_b23'
                    )
                    hp_ma_flush = ws_call(http_ma, ws_ma, tid_ma, 'visual_admin_plan', {
                        'resource_kind': 'server',
                        'operation_id': 'flush',
                        'target_resource': ma_srv_target,
                        'draft': {'targets': ['STATUS'], 'binlog_mode': 'LOCAL', 'confirmation': 'MariaDB'},
                    })
                    ws_call(http_ma, ws_ma, tid_ma, 'visual_admin_apply', {
                        'plan_id': hp_ma_flush['plan_id'],
                        'plan_digest': hp_ma_flush['plan_digest'],
                        'confirmed': True,
                    })
                    mt_race_fresh = next(
                        r for r in _resources(madm, {'route': {'database': 'sr_ma_b23'}}, MARIADB_PROFILE)
                        if r['resource_kind'] == 'table' and r['display_name'] == 'ma_drop_race'
                    )
                    hp_ma_drop = ws_call(http_ma, ws_ma, tid_ma, 'visual_admin_plan', {
                        'resource_kind': 'table',
                        'operation_id': 'drop',
                        'target_resource': mt_race_fresh,
                        'draft': {'confirmation': 'ma_drop_race'},
                    })
                    ws_call(http_ma, ws_ma, tid_ma, 'visual_admin_apply', {
                        'plan_id': hp_ma_drop['plan_id'],
                        'plan_digest': hp_ma_drop['plan_digest'],
                        'confirmed': True,
                    })

                    identity_evidence['mariadb'].append({
                        'valid_drop_succeeded': True,
                        'same_name_replacement_refused_and_rows_preserved': True,
                        'http_verified': True,
                    })
                    flush_evidence['mariadb'].append({
                        'server_flush_acknowledged': True,
                        'query_response_time_plugin_gate_and_live_flush_verified': True,
                        'restricted_1227_denied': True,
                        'http_verified': True,
                    })
                finally:
                    ma_cli.close()
                    ma_lim_cli.close()
            finally:
                madm.close()

        # ===================================================================
        # PHASE 3: Live MySQL NDB Cluster 9.7.0 (MY-AUDIT-NDB)
        # ===================================================================
        ndb_cluster_evidence = {}
        with owned_ndb_cluster_9_7(work / 'ndb97') as (ndb_route, ndb_fixture):
            ndb_pw = 'NdbB23#' + secrets.token_urlsafe(18)
            nadm = mysql.connector.connect(host='127.0.0.1', port=ndb_route['port'], user='root', autocommit=True)
            try:
                with nadm.cursor() as cur:
                    cur.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (ndb_pw,))
                    cur.execute('CREATE DATABASE sr_ndb CHARACTER SET utf8mb4')
                ndb_uuid = ndb_fixture['server_uuid']
                ndb_srv_target = {
                    'resource_id': 'server:MySQL',
                    'resource_kind': 'server',
                    'display_name': 'MySQL',
                    'display_path': ['MySQL'],
                    'native': {'server_uuid': ndb_uuid},
                }
                n_route = {
                    'host': '127.0.0.1',
                    'port': ndb_route['port'],
                    'user': 'root',
                    'database': 'sr_ndb',
                    'use_pure': True,
                    'credential_reference_id': 'ndb-pw',
                    'principal_reference': 'ndb-op',
                }
                n_cli = make_native_client(MYSQL_PROFILE, ndb_pw, 'ndb-cli')
                try:
                    # 1. Inspect NDB cluster (ndbinfo + ndb_mgmd get status)
                    insp_plan = n_cli.plan_admin_operation({
                        'resource_kind': 'server',
                        'operation_id': 'inspect_ndb_cluster',
                        'target_resource': ndb_srv_target,
                        'draft': {'mgm_host': '127.0.0.1', 'mgm_port': ndb_route['mgm_port'], 'confirmation': 'MySQL'},
                        '_provider_route': n_route,
                    })
                    insp_res = n_cli.apply_admin_operation(insp_plan)['ndb_result']
                    assert insp_res['ndbinfo']['ndbinfo_available'] is True
                    assert len(insp_res['ndbinfo']['nodes']) >= 1
                    assert insp_res['mgm_status']['node_count'] >= 3

                    # 2. Logfile group CREATE -> ALTER -> NDB Tablespace CREATE -> ALTER -> DROP -> Logfile group DROP
                    lg_c = n_cli.plan_admin_operation({
                        'resource_kind': 'logfile-group',
                        'operation_id': 'create',
                        'draft': {'name': 'sr_lg1', 'undofile': 'sr_undo1.log', 'initial_size': 16777216, 'undo_buffer_size': 2097152},
                        '_provider_route': n_route,
                    })
                    assert n_cli.apply_admin_operation(lg_c)['accepted'] is True

                    ndb_disc = _resources(nadm, {'route': {'database': 'sr_ndb'}}, MYSQL_PROFILE)
                    lg_target = next(r for r in ndb_disc if r['resource_kind'] == 'logfile-group' and r['display_name'] == 'sr_lg1')
                    node2_target = next(r for r in ndb_disc if r['resource_kind'] == 'ndb-node' and r['display_name'] == '2')

                    lg_a = n_cli.plan_admin_operation({
                        'resource_kind': 'logfile-group',
                        'operation_id': 'alter',
                        'target_resource': lg_target,
                        'draft': {'undofile': 'sr_undo2.log', 'initial_size': 16777216, 'confirmation': 'sr_lg1'},
                        '_provider_route': n_route,
                    })
                    assert n_cli.apply_admin_operation(lg_a)['accepted'] is True

                    ts_c = n_cli.plan_admin_operation({
                        'resource_kind': 'tablespace',
                        'operation_id': 'create',
                        'draft': {
                            'name': 'sr_ndb_ts1',
                            'space_type': 'NDB',
                            'datafile': 'sr_ts1_a.dat',
                            'logfile_group': 'sr_lg1',
                            'initial_size': 33554432,
                            'extent_size': 1048576,
                        },
                        '_provider_route': n_route,
                    })
                    assert n_cli.apply_admin_operation(ts_c)['accepted'] is True

                    ndb_disc2 = _resources(nadm, {'route': {'database': 'sr_ndb'}}, MYSQL_PROFILE)
                    ts_target = next(r for r in ndb_disc2 if r['resource_kind'] == 'tablespace' and r['display_name'] == 'sr_ndb_ts1')
                    assert ts_target['native']['engine'] == 'ndbcluster'

                    ts_add = n_cli.plan_admin_operation({
                        'resource_kind': 'tablespace',
                        'operation_id': 'alter',
                        'target_resource': ts_target,
                        'draft': {'change': 'ADD_DATAFILE', 'datafile': 'sr_ts1_b.dat', 'initial_size': 33554432, 'confirmation': 'sr_ndb_ts1'},
                        '_provider_route': n_route,
                    })
                    assert n_cli.apply_admin_operation(ts_add)['accepted'] is True

                    ts_drop_df = n_cli.plan_admin_operation({
                        'resource_kind': 'tablespace',
                        'operation_id': 'alter',
                        'target_resource': ts_target,
                        'draft': {'change': 'DROP_DATAFILE', 'datafile': 'sr_ts1_b.dat', 'confirmation': 'sr_ndb_ts1'},
                        '_provider_route': n_route,
                    })
                    assert n_cli.apply_admin_operation(ts_drop_df)['accepted'] is True

                    ts_drop_df_a = n_cli.plan_admin_operation({
                        'resource_kind': 'tablespace',
                        'operation_id': 'alter',
                        'target_resource': ts_target,
                        'draft': {'change': 'DROP_DATAFILE', 'datafile': 'sr_ts1_a.dat', 'confirmation': 'sr_ndb_ts1'},
                        '_provider_route': n_route,
                    })
                    assert n_cli.apply_admin_operation(ts_drop_df_a)['accepted'] is True

                    ts_d = n_cli.plan_admin_operation({
                        'resource_kind': 'tablespace',
                        'operation_id': 'drop',
                        'target_resource': ts_target,
                        'draft': {'confirmation': 'sr_ndb_ts1'},
                        '_provider_route': n_route,
                    })
                    assert n_cli.apply_admin_operation(ts_d)['accepted'] is True

                    lg_d = n_cli.plan_admin_operation({
                        'resource_kind': 'logfile-group',
                        'operation_id': 'drop',
                        'target_resource': lg_target,
                        'draft': {'confirmation': 'sr_lg1'},
                        '_provider_route': n_route,
                    })
                    assert n_cli.apply_admin_operation(lg_d)['accepted'] is True

                    # 3. Online NDB Backup via MGM wire protocol + HTTP verification
                    bk_plan = n_cli.plan_admin_operation({
                        'resource_kind': 'server',
                        'operation_id': 'start_ndb_backup',
                        'target_resource': ndb_srv_target,
                        'draft': {
                            'mgm_host': '127.0.0.1',
                            'mgm_port': ndb_route['mgm_port'],
                            'wait_mode': 'WAIT_COMPLETED',
                            'snapshot_point': 'COMPLETE_TIME',
                            'confirmation': 'MySQL',
                        },
                        '_provider_route': n_route,
                    })
                    bk_res = n_cli.apply_admin_operation(bk_plan)['ndb_result']
                    assert bk_res['mgm_response']['result'] == 'Ok'

                    sid_ndb, tid_ndb, _u_ndb, ws_ndb, http_ndb = register_http_endpoint(
                        app, 'mysql', 'mysql-native', ndb_route, ndb_pw, 'sr_ndb'
                    )
                    hp_ndb = ws_call(http_ndb, ws_ndb, tid_ndb, 'visual_admin_plan', {
                        'resource_kind': 'server',
                        'operation_id': 'inspect_ndb_cluster',
                        'target_resource': ndb_srv_target,
                        'draft': {'mgm_host': '127.0.0.1', 'mgm_port': ndb_route['mgm_port'], 'confirmation': 'MySQL'},
                    })
                    ws_call(http_ndb, ws_ndb, tid_ndb, 'visual_admin_apply', {
                        'plan_id': hp_ndb['plan_id'],
                        'plan_digest': hp_ndb['plan_digest'],
                        'confirmed': True,
                    })

                    ndb_cluster_evidence = {
                        'ndbinfo_nodes_observed': len(insp_res['ndbinfo']['nodes']),
                        'mgm_nodes_observed': insp_res['mgm_status']['node_count'],
                        'logfile_group_lifecycle_passed': True,
                        'ndb_tablespace_lifecycle_passed': True,
                        'ndb_node_discovered': node2_target['display_name'],
                        'mgm_online_backup_passed': True,
                        'http_verified': True,
                    }
                finally:
                    n_cli.close()
            finally:
                nadm.close()

        # Verify fixture cleanups
        assert my_fixture['owned_server_stopped'] is True
        assert ma_fixture['owned_server_stopped'] is True
        assert ndb_fixture['owned_cluster_stopped'] is True

        # Write per-item receipts
        now_iso = datetime.now(timezone.utc).isoformat()
        files_to_write = {
            'identity-receipt.json': {
                'complete': True,
                'audit_ids': ['MY-AUDIT-IDENTITY-01', 'MA-AUDIT-IDENTITY'],
                'qualified_at': now_iso,
                'mysql_fixture': my_fixture,
                'mariadb_fixture': ma_fixture,
                'evidence': identity_evidence,
                'source_sha256': source_hashes(
                    'web/pgadmin/cdeadmin/providers/mysql_family/destructive_identity.py',
                    'web/pgadmin/cdeadmin/providers/mysql_family/administration.py',
                    'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_administration.py',
                    'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
                ),
            },
            'flush-receipt.json': {
                'complete': True,
                'audit_ids': ['MY-AUDIT-FLUSH', 'MA-AUDIT-FLUSH'],
                'qualified_at': now_iso,
                'mysql_fixture': my_fixture,
                'mariadb_fixture': ma_fixture,
                'evidence': flush_evidence,
                'source_sha256': source_hashes(
                    'web/pgadmin/cdeadmin/providers/mysql_family/mysql_flush.py',
                    'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_flush.py',
                    'web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',
                    'web/pgadmin/cdeadmin/ui_descriptors/mariadb/operations.json',
                ),
            },
            'explain-for-connection-receipt.json': {
                'complete': True,
                'audit_ids': ['MY-AUDIT-EXPLAIN_FOR_CONNECTION'],
                'qualified_at': now_iso,
                'mysql_fixture': my_fixture,
                'evidence': explain_evidence,
                'source_sha256': source_hashes(
                    'web/pgadmin/cdeadmin/providers/mysql_family/mysql_live_plans.py',
                    'web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',
                ),
            },
            'component-metrics-receipt.json': {
                'complete': True,
                'audit_ids': ['MY-AUDIT-COMPONENT-METRICS'],
                'qualified_at': now_iso,
                'mysql_fixture': my_fixture,
                'evidence': comp_metrics_evidence,
                'source_sha256': source_hashes(
                    'web/pgadmin/cdeadmin/providers/mysql_family/mysql_monitoring.py',
                    'web/pgadmin/cdeadmin/providers/mysql_family/mysql_metrics_9_7_0.json',
                    'web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/mysqlDashboard.js',
                    'web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs',
                ),
            },
            'language-semantics-receipt.json': {
                'complete': True,
                'audit_ids': ['MY-AUDIT-LANGUAGE-SEMANTICS'],
                'qualified_at': now_iso,
                'mysql_fixture': my_fixture,
                'evidence': lang_semantics_evidence,
                'source_sha256': source_hashes(
                    'web/pgadmin/cdeadmin/providers/mysql_family/mysql_parser.py',
                    'web/pgadmin/cdeadmin/providers/mysql_family/mysql_native_validation.py',
                    'web/pgadmin/cdeadmin/providers/mysql_family/mysql_completion.py',
                    'web/pgadmin/cdeadmin/providers/mysql_family/mysql_session_catalog.py',
                ),
            },
            'xcollections-receipt.json': {
                'complete': True,
                'audit_ids': ['MY-AUDIT-XCOLLECTIONS'],
                'qualified_at': now_iso,
                'mysql_fixture': my_fixture,
                'evidence': xcoll_evidence,
                'source_sha256': source_hashes(
                    'web/pgadmin/cdeadmin/providers/mysql_family/mysql_xprotocol.py',
                    'web/pgadmin/cdeadmin/providers/mysql_family/mysql_xcollections.py',
                    'web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',
                ),
            },
            'ndb-receipt.json': {
                'complete': True,
                'audit_ids': ['MY-AUDIT-NDB'],
                'qualified_at': now_iso,
                'standard_mysql_fixture': my_fixture,
                'ndb_cluster_fixture': ndb_fixture,
                'non_ndb_gate_evidence': ndb_non_cluster_evidence,
                'ndb_cluster_evidence': ndb_cluster_evidence,
                'source_sha256': source_hashes(
                    'web/pgadmin/cdeadmin/providers/mysql_family/mysql_ndb.py',
                    'web/pgadmin/cdeadmin/providers/mysql_tablespaces.py',
                    'web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',
                ),
            },
        }
        receipt_index = {}
        for fname, doc in files_to_write.items():
            fpath = output_dir / fname
            fpath.write_text(json.dumps(doc, indent=2, sort_keys=True) + '\n')
            receipt_index[fname] = {
                'audit_ids': doc['audit_ids'],
                'complete': doc['complete'],
                'sha256': hashlib.sha256(fpath.read_bytes()).hexdigest(),
            }
            receipts[fname] = doc

        summary = {
            'complete': True,
            'qualified_at': now_iso,
            'history_testing': 'not run',
            'audit_items_closed': [
                'MY-AUDIT-IDENTITY-01',
                'MA-AUDIT-IDENTITY',
                'MY-AUDIT-FLUSH',
                'MA-AUDIT-FLUSH',
                'MY-AUDIT-EXPLAIN_FOR_CONNECTION',
                'MY-AUDIT-COMPONENT-METRICS',
                'MY-AUDIT-LANGUAGE-SEMANTICS',
                'MY-AUDIT-XCOLLECTIONS',
                'MY-AUDIT-NDB',
            ],
            'receipts': receipt_index,
            'owned_cleanup_verified': True,
        }
        (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
        return summary
    finally:
        for ext_key in ('cdeadmin_mysql_monitoring_host', 'cdeadmin_mariadb_monitoring_host'):
            try:
                if ext_key in app.extensions:
                    app.extensions[ext_key].close()
            except Exception:
                pass
        shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tmp-root', type=Path, required=True)
    args = parser.parse_args()
    summary = run_all(args.output.resolve(), args.tmp_root.resolve())
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
