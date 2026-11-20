#!/usr/bin/env python3
"""Live native + authenticated HTTP qualification for all 11 Batch 4 MySQL 9.7.0 & MariaDB 12.2.2 utilities."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]

MYSQL_RPM_BASE = 'https://repo.mysql.com/yum/mysql-9.7-community/el/9/x86_64'
MYSQL_RPMS = (
    'mysql-community-libs-9.7.0-1.el9.x86_64.rpm',
    'mysql-community-client-9.7.0-1.el9.x86_64.rpm',
    'mysql-community-server-9.7.0-1.el9.x86_64.rpm',
)


def _docker_cmd(*args: str) -> list[str]:
    ctx = os.environ.get('DOCKER_CONTEXT')
    return ['docker', *(['--context', ctx] if ctx else []), *args]


def _run(cmd: list[str], *, check: bool = True, input_bytes: bytes | None = None, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=timeout,
        shell=False,
    )


def _container_exec(container: str, script: str, *args: str, user: str = 'root', timeout: int = 120) -> str:
    res = _run(
        _docker_cmd('exec', '--user', user, '-i', container, 'sh', '-c', script, 'sr-qual', *args),
        timeout=timeout,
    )
    return res.stdout.decode('utf-8', errors='replace')


def _host_port(container: str, internal_port: int = 3306) -> int:
    out = _run(_docker_cmd('port', container, f'{internal_port}/tcp')).stdout.decode('utf-8').strip()
    for line in out.splitlines():
        if ':' in line:
            return int(line.rsplit(':', 1)[1])
    raise RuntimeError(f'Could not resolve mapped port for {container}: {out}')


def _prepare_mysql_970_binaries(work_dir: Path) -> Path:
    extract_dir = work_dir / 'mysql970-extract'
    extract_dir.mkdir(parents=True, exist_ok=True)
    for rpm_name in MYSQL_RPMS:
        rpm_path = extract_dir / rpm_name
        if not rpm_path.exists():
            _run(['curl', '-fsSL', '-o', str(rpm_path), f'{MYSQL_RPM_BASE}/{rpm_name}'], timeout=240)
        cpio_proc = subprocess.Popen(
            ['rpm2cpio', str(rpm_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert cpio_proc.stdout is not None
        subprocess.run(
            [
                'cpio', '-idmu', '--quiet',
                './usr/bin/myisamchk',
                './usr/bin/myisampack',
                './usr/bin/innochecksum',
                './usr/bin/ibd2sdi',
                './usr/bin/mysqlslap',
                './usr/lib64/mysql/libmysqlclient*',
            ],
            cwd=str(extract_dir),
            stdin=cpio_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        cpio_proc.stdout.close()
        cpio_proc.wait(timeout=60)
    for bname in ('myisamchk', 'myisampack', 'innochecksum', 'ibd2sdi', 'mysqlslap'):
        bpath = extract_dir / 'usr' / 'bin' / bname
        if not bpath.is_file():
            raise RuntimeError(f'Missing extracted MySQL 9.7.0 utility binary: {bpath}')
    return extract_dir


def _setup_flask_app(app_root: Path):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app_root.mkdir(parents=True, exist_ok=True)
    return setup_application(app_root)


def _register_http_endpoint(app, *, profile_id: str, engine_key: str, name: str, host: str, port: int, password: str, database: str, use_pure: bool = True):
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile

    with app.test_request_context('/'):
        owner = User.query.first()
        group = ServerGroup.query.filter_by(user_id=owner.id).order_by(ServerGroup.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility[engine_key].set(True, user_id=owner.id)
        srv = Server(
            user_id=owner.id,
            servergroup_id=group.id,
            name=name,
            host=host,
            port=port,
            username='root',
            maintenance_db=database,
            save_password=0,
        )
        srv._cde_endpoint_registration = registration_profile(profile_id)
        route_cfg = {
            'host': host,
            'port': port,
            'database': database,
            'user': 'root',
            'credential_kinds': ['database_password'],
        }
        if engine_key == 'mysql':
            route_cfg['use_pure'] = use_pure
            route_cfg['autocommit'] = True
        else:
            route_cfg['ssl'] = False
            route_cfg['ssl_verify_cert'] = False
        srv._cde_endpoint_route_configuration = route_cfg
        db.session.add(srv)
        db.session.commit()
        db_target_id = str(uuid.uuid4())
        db.session.add(
            EndpointDatabaseTarget(
                id=db_target_id,
                endpoint_id=srv.endpoint_profile.id,
                display_name=database,
                database=database,
                configuration='{}',
                active=1,
            )
        )
        db.session.commit()
        ws_url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=srv.id)
        verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=srv.id)
        uid = owner.id

    http_client = app.test_client()
    with http_client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    v_resp = http_client.post(verify_url, json={'password': password})
    v_json = v_resp.get_json()
    assert v_resp.status_code == 200 and v_json.get('success'), f'Endpoint verify failed: {v_json}'

    def post_ok(action: str, req: dict):
        r = http_client.post(ws_url, json={'action': action, 'request': {'database_target_id': db_target_id, **req}})
        body = r.get_json()
        assert r.status_code == 200 and body.get('success'), f'{action} failed ({r.status_code}): {body}'
        return body['data']

    def post_raw(action: str, req: dict):
        return http_client.post(ws_url, json={'action': action, 'request': {'database_target_id': db_target_id, **req}})

    return SimpleNamespace(ok=post_ok, raw=post_raw, url=ws_url, db_target_id=db_target_id)


def qualify_mariadb(app, tmp_root: Path, output_dir: Path) -> dict:
    import mariadb
    from pgadmin.cdeadmin.providers.mysql_family.provider import (
        MARIADB_ADMINISTRATION,
        MARIADB_PROFILE,
        _create_client,
    )
    from pgadmin.cdeadmin.sdk import RelationalClientError
    from pgadmin.cdeadmin.security import SecretLease

    cname = 'sr-batch4-mariadb-' + secrets.token_hex(6)
    password = 'MaBatch4Secret_' + secrets.token_urlsafe(18)
    receipt: dict = {
        'engine': 'mariadb',
        'version': None,
        'server_uid': None,
        'utilities': {},
        'container_removed': False,
    }

    _run(
        _docker_cmd(
            'run', '-d', '--name', cname,
            '-p', '127.0.0.1::3306',
            '--entrypoint', 'sh',
            'mariadb:12.2.2',
            '-c', 'trap "exit 0" TERM INT; while :; do sleep 1; done',
        )
    )
    try:
        # Initialize MariaDB datadir and private workspace
        _container_exec(
            cname,
            '''
set -e
mkdir -p /var/lib/mysql /run/mysqld /var/lib/sr-utility-workspace
chown -R mysql:mysql /var/lib/mysql /run/mysqld
chmod 700 /var/lib/sr-utility-workspace
rm -rf /var/lib/mysql/*
mariadb-install-db --user=mysql --datadir=/var/lib/mysql --auth-root-authentication-method=normal >/dev/null
''',
        )

        def start_mariadbd():
            _container_exec(
                cname,
                '''
set -e
mkdir -p /run/mysqld && chown mysql:mysql /run/mysqld
mariadbd --user=mysql --datadir=/var/lib/mysql \
  --pid-file=/var/lib/mysql/mariadbd.pid \
  --socket=/run/mysqld/mysqld.sock \
  --port=3306 --bind-address=0.0.0.0 \
  --log-error=/var/lib/mysql/mariadbd.err >/dev/null 2>&1 &
''',
            )

        def stop_mariadbd():
            _container_exec(
                cname,
                r'''
if [ -f /var/lib/mysql/mariadbd.pid ]; then
  p=$(tr -d ' \t\r\n' < /var/lib/mysql/mariadbd.pid)
  if [ -n "$p" ] && [ -d "/proc/$p" ]; then
    kill -TERM "$p" 2>/dev/null || true
    for _ in $(seq 1 60); do
      [ ! -d "/proc/$p" ] && break
      sleep 0.25
    done
    [ ! -d "/proc/$p" ] || { kill -KILL "$p" 2>/dev/null || true; sleep 0.5; }
  fi
fi
rm -f /var/lib/mysql/mariadbd.pid /run/mysqld/mysqld.sock
''',
            )

        start_mariadbd()
        port = _host_port(cname, 3306)

        # Bootstrap root@localhost and root@% over local Unix socket inside container
        bootstrap_sql = (
            f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{password}';\n"
            f"CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY '{password}';\n"
            f"ALTER USER 'root'@'%' IDENTIFIED BY '{password}';\n"
            "GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;\n"
            "FLUSH PRIVILEGES;\n"
        ).encode('utf-8')
        sock_ready = False
        for _ in range(60):
            probe = _run(
                _docker_cmd('exec', cname, 'mariadb', '--protocol=socket', '--socket=/run/mysqld/mysqld.sock', '-u', 'root', '-e', 'SELECT 1'),
                check=False,
            )
            if probe.returncode == 0:
                sock_ready = True
                break
            time.sleep(0.5)
        if not sock_ready:
            err_log = _container_exec(cname, 'cat /var/lib/mysql/mariadbd.err 2>/dev/null | tail -n 40 || true')
            raise RuntimeError(f'mariadbd socket did not become ready: {err_log}')
        _run(
            _docker_cmd('exec', '-i', cname, 'mariadb', '--protocol=socket', '--socket=/run/mysqld/mysqld.sock', '-u', 'root'),
            input_bytes=bootstrap_sql,
        )

        # Connect from host over TCP with ssl=False
        conn = None
        for _ in range(60):
            try:
                conn = mariadb.connect(host='127.0.0.1', port=port, user='root', password=password, ssl=False, connect_timeout=3)
                break
            except Exception:
                time.sleep(0.5)
        if conn is None:
            err_log = _container_exec(cname, 'cat /var/lib/mysql/mariadbd.err 2>/dev/null | tail -n 40 || true')
            raise RuntimeError(f'mariadbd did not become ready on port {port}: {err_log}')
        with closing(conn):
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute('SELECT VERSION(), @@server_uid')
            ver, server_uid = cur.fetchone()
            assert str(ver).startswith('12.2.2'), f'Unexpected MariaDB version: {ver}'
            receipt['version'] = str(ver)
            receipt['server_uid'] = str(server_uid)
            cur.execute('CREATE DATABASE sr_util_ma CHARACTER SET utf8mb4')
            cur.execute(
                'CREATE TABLE sr_util_ma.aria_items('
                'id INT PRIMARY KEY, code VARCHAR(64), payload VARCHAR(255), KEY idx_code(code)'
                ') ENGINE=Aria TRANSACTIONAL=0 PAGE_CHECKSUM=1'
            )
            cur.execute(
                'CREATE TABLE sr_util_ma.aria_pack_tbl('
                'id INT PRIMARY KEY, grp VARCHAR(32), body VARCHAR(200), KEY idx_grp(grp)'
                ') ENGINE=Aria TRANSACTIONAL=0 PAGE_CHECKSUM=1'
            )
            cur.execute(
                'CREATE TABLE sr_util_ma.myisam_items('
                'id INT PRIMARY KEY, tag VARCHAR(64), payload VARCHAR(255), KEY idx_tag(tag)'
                ') ENGINE=MyISAM'
            )
            cur.execute(
                'CREATE TABLE sr_util_ma.myisam_pack_tbl('
                'id INT PRIMARY KEY, grp VARCHAR(32), body VARCHAR(200), KEY idx_grp(grp)'
                ') ENGINE=MyISAM'
            )
            cur.execute(
                'CREATE TABLE sr_util_ma.inno_items('
                'id INT PRIMARY KEY, title VARCHAR(120), notes TEXT, KEY idx_title(title)'
                ') ENGINE=InnoDB'
            )
            aria_rows = [(i, f'ARIA-{i:04d}', 'compressible_aria_payload_' * 6) for i in range(1, 501)]
            cur.executemany('INSERT INTO sr_util_ma.aria_items VALUES (?, ?, ?)', aria_rows)
            pack_rows = [(i, f'G{i % 10}', 'REPEATED_COMPRESSIBLE_SEGMENT_' * 6) for i in range(1, 601)]
            cur.executemany('INSERT INTO sr_util_ma.aria_pack_tbl VALUES (?, ?, ?)', pack_rows)
            cur.executemany('INSERT INTO sr_util_ma.myisam_items VALUES (?, ?, ?)', aria_rows)
            cur.executemany('INSERT INTO sr_util_ma.myisam_pack_tbl VALUES (?, ?, ?)', pack_rows)
            inno_rows = [(i, f'INNO-TITLE-{i:04d}', 'InnoDB tablespace row payload ' * 12) for i in range(1, 201)]
            cur.executemany('INSERT INTO sr_util_ma.inno_items VALUES (?, ?, ?)', inno_rows)
            cur.execute('FLUSH TABLES')
            cur.close()

        target = {
            'resource_kind': 'server',
            'resource_id': 'server:MariaDB',
            'display_name': 'MariaDB',
            'display_path': ['MariaDB'],
            'native': {'server_uid': server_uid},
        }
        route = {
            'host': '127.0.0.1',
            'port': port,
            'user': 'root',
            'database': 'sr_util_ma',
            'ssl': False,
            'ssl_verify_cert': False,
            'principal_reference': 'qual-ma-operator',
            'credential_reference_id': 'qual-ma-secret',
        }
        native_client = _create_client(
            MARIADB_PROFILE,
            SimpleNamespace(acquire_secret=lambda *_: SecretLease(password.encode('utf-8'))),
            SimpleNamespace(pool_namespace='qual-ma-' + uuid.uuid4().hex),
        )
        http = _register_http_endpoint(
            app,
            profile_id='mariadb-native',
            engine_key='mariadb',
            name='Qual MariaDB 12.2.2 Utilities',
            host='127.0.0.1',
            port=port,
            password=password,
            database='sr_util_ma',
        )
        host_base = {
            'execution_host_kind': 'container',
            'container_name': cname,
            'datadir': '/var/lib/mysql',
            'workspace': '/var/lib/sr-utility-workspace',
            'pid_file': '/var/lib/mysql/mariadbd.pid',
            'socket_path': '/run/mysqld/mysqld.sock',
            'timeout_seconds': 90,
            'confirmation': 'MariaDB',
        }

        try:
            # --- ONLINE PHASE 1: Active-server refusal for all 5 offline MariaDB utilities (native + HTTP) ---
            offline_refusal_cases = [
                ('run_aria_chk', {'database_name': 'sr_util_ma', 'table_name': 'aria_items', 'mode': 'check'}),
                ('run_aria_pack', {'database_name': 'sr_util_ma', 'table_name': 'aria_pack_tbl', 'dry_run_test': True}),
                ('run_myisamchk', {'database_name': 'sr_util_ma', 'table_name': 'myisam_items', 'mode': 'check'}),
                ('run_myisampack', {'database_name': 'sr_util_ma', 'table_name': 'myisam_pack_tbl', 'dry_run_test': True}),
                ('run_innochecksum', {'database_name': 'sr_util_ma', 'table_name': 'inno_items', 'count_only': True}),
            ]
            active_refusals = {}
            for op_id, extra in offline_refusal_cases:
                draft = {**host_base, **extra}
                try:
                    native_client.plan_admin_operation({
                        'resource_kind': 'server',
                        'operation_id': op_id,
                        'target_resource': target,
                        'draft': draft,
                        '_provider_route': route,
                    })
                    raise AssertionError(f'{op_id} did not refuse active mariadbd natively!')
                except RelationalClientError as exc:
                    native_msg = str(exc)
                    assert 'Refused offline' in native_msg
                http_resp = http.raw('visual_admin_plan', {
                    'resource_kind': 'server',
                    'operation_id': op_id,
                    'target_resource': target,
                    'draft': draft,
                })
                assert http_resp.status_code != 200 or not http_resp.get_json().get('success')
                job_resp = http.raw('mariadb_utility_review', {
                    'operation_id': op_id,
                    'target_resource': target,
                    'draft': draft,
                })
                assert job_resp.status_code != 200 or not job_resp.get_json().get('success')
                active_refusals[op_id] = {'native_refused': True, 'http_refused': True, 'message': native_msg}

            # --- ONLINE PHASE 2: MA-AUDIT-UTILITY-MARIADB-SLAP (native + HTTP + cancel + timeout + redaction) ---
            slap_draft_native = {
                **host_base,
                'benchmark_schema': 'cdeadmin_slap_ma_native',
                'concurrency': '1,4',
                'iterations': 2,
                'number_of_queries': 40,
                'workload_mode': 'auto_generate',
                'auto_load_type': 'mixed',
                'isolated_scratch_confirmed': True,
            }
            slap_plan = native_client.plan_admin_operation({
                'resource_kind': 'server',
                'operation_id': 'run_mariadb_slap',
                'target_resource': target,
                'draft': slap_draft_native,
                '_provider_route': route,
            })
            assert password not in json.dumps(slap_plan['command_preview'])
            slap_res = MARIADB_ADMINISTRATION.apply(native_client, slap_plan)['mariadb_utility']
            assert password not in json.dumps(slap_res)
            assert slap_res['tool']['tool_version_identity'] == '12.2.2-MariaDB'
            assert slap_res['metrics']['run_count'] >= 2
            assert slap_res['metrics']['average_seconds'] is not None
            assert slap_res['scratch_schema_cleaned_up'] is True

            # HTTP visual_admin explicit SQL benchmark + replay refusal
            slap_http_req = {
                'resource_kind': 'server',
                'operation_id': 'run_mariadb_slap',
                'target_resource': target,
                'draft': {
                    **host_base,
                    'benchmark_schema': 'cdeadmin_slap_ma_http',
                    'concurrency': '3',
                    'iterations': 2,
                    'number_of_queries': 30,
                    'workload_mode': 'explicit_sql',
                    'create_sql': "CREATE TABLE bench_kv (k INT PRIMARY KEY, v VARCHAR(64)); INSERT INTO bench_kv VALUES (1, 'alpha'), (2, 'beta');",
                    'query_sql': 'SELECT v FROM bench_kv WHERE k = 1;',
                    'isolated_scratch_confirmed': True,
                },
            }
            v_chk = http.ok('visual_admin_validate', slap_http_req)
            assert v_chk['valid'], v_chk
            v_plan = http.ok('visual_admin_plan', slap_http_req)
            assert password not in json.dumps(v_plan)
            v_apply_body = {'plan_id': v_plan['plan_id'], 'plan_digest': v_plan['plan_digest'], 'confirmed': True}
            v_applied = http.ok('visual_admin_apply', v_apply_body)
            assert password not in json.dumps(v_applied)
            http_slap_obs = v_applied['provider_result']['mariadb_utility']
            assert http_slap_obs['metrics']['clients_per_run'] == 3
            assert http_slap_obs['scratch_schema_cleaned_up'] is True
            replay_resp = http.raw('visual_admin_apply', v_apply_body)
            assert replay_resp.status_code != 200 or not replay_resp.get_json().get('success')

            # HTTP mid-flight cancellation via mariadb_utility_* workspace actions
            cancel_rev = http.ok('mariadb_utility_review', {
                'operation_id': 'run_mariadb_slap',
                'target_resource': target,
                'draft': {
                    **host_base,
                    'benchmark_schema': 'cdeadmin_slap_ma_cancel',
                    'concurrency': '2',
                    'iterations': 5,
                    'workload_mode': 'explicit_sql',
                    'query_sql': 'SELECT SLEEP(2);',
                    'number_of_queries': 20,
                    'isolated_scratch_confirmed': True,
                },
            })
            http.ok('mariadb_utility_start', {
                'job_id': cancel_rev['job_id'],
                'review_digest': cancel_rev['review_digest'],
                'confirmed': True,
                'async_execution': True,
            })
            time.sleep(0.6)
            cancelled_job = http.ok('mariadb_utility_cancel', {'job_id': cancel_rev['job_id']})
            assert cancelled_job['state'] == 'cancelled' and cancelled_job['cleanup_confirmed'] is True

            # Bounded timeout check (timeout_seconds=1 on SLEEP(5))
            to_plan = native_client.plan_admin_operation({
                'resource_kind': 'server',
                'operation_id': 'run_mariadb_slap',
                'target_resource': target,
                'draft': {
                    **host_base,
                    'timeout_seconds': 1,
                    'benchmark_schema': 'cdeadmin_slap_ma_timeout',
                    'concurrency': '1',
                    'iterations': 1,
                    'workload_mode': 'explicit_sql',
                    'query_sql': 'SELECT SLEEP(5);',
                    'isolated_scratch_confirmed': True,
                },
                '_provider_route': route,
            })
            try:
                MARIADB_ADMINISTRATION.apply(native_client, to_plan)
                raise AssertionError('Expected mariadb-slap timeout')
            except RelationalClientError as exc:
                assert 'timed out' in str(exc) and exc.cleanup_confirmed is True

            receipt['utilities']['MA-AUDIT-UTILITY-MARIADB-SLAP'] = {
                'native': slap_res,
                'http': http_slap_obs,
                'cancellation_verified': True,
                'timeout_verified': True,
                'credential_redaction_verified': True,
                'replay_refused': True,
            }

            # --- STOP MARIADBD FOR OFFLINE PHASE ---
            stop_mariadbd()

            def run_ma_both(op_id: str, native_extra: dict, http_extra: dict):
                n_plan = native_client.plan_admin_operation({
                    'resource_kind': 'server',
                    'operation_id': op_id,
                    'target_resource': target,
                    'draft': {**host_base, **native_extra},
                    '_provider_route': route,
                })
                n_res = MARIADB_ADMINISTRATION.apply(native_client, n_plan)['mariadb_utility']
                h_req = {
                    'resource_kind': 'server',
                    'operation_id': op_id,
                    'target_resource': target,
                    'draft': {**host_base, **http_extra},
                }
                assert http.ok('visual_admin_validate', h_req)['valid']
                h_plan = http.ok('visual_admin_plan', h_req)
                h_res = http.ok(
                    'visual_admin_apply',
                    {'plan_id': h_plan['plan_id'], 'plan_digest': h_plan['plan_digest'], 'confirmed': True},
                )['provider_result']['mariadb_utility']
                return n_res, h_res

            # 6. MA-AUDIT-UTILITY-ARIA_CHK
            aria_desc, aria_ext = run_ma_both(
                'run_aria_chk',
                {'database_name': 'sr_util_ma', 'table_name': 'aria_items', 'mode': 'describe', 'include_information': True},
                {'database_name': 'sr_util_ma', 'table_name': 'aria_items', 'mode': 'extend_check'},
            )
            aria_rec, aria_zero = run_ma_both(
                'run_aria_chk',
                {'database_name': 'sr_util_ma', 'table_name': 'aria_items', 'mode': 'safe_recover', 'backup': True, 'destructive_confirmed': True},
                {'database_name': 'sr_util_ma', 'table_name': 'aria_items', 'mode': 'zerofill', 'destructive_confirmed': True},
            )
            assert aria_desc['check_passed'] and aria_ext['check_passed'] and aria_rec['repaired'] and aria_zero['repaired']

            # 7. MA-AUDIT-UTILITY-ARIA_PACK (dry-run --test native, real pack + aria_chk -rq over HTTP!)
            aria_pack_dry, aria_pack_real = run_ma_both(
                'run_aria_pack',
                {'database_name': 'sr_util_ma', 'table_name': 'aria_pack_tbl', 'dry_run_test': True},
                {'database_name': 'sr_util_ma', 'table_name': 'aria_pack_tbl', 'dry_run_test': False, 'backup': True, 'force': True, 'rebuild_indexes': True, 'destructive_confirmed': True},
            )
            assert aria_pack_dry['dry_run_test'] is True and aria_pack_dry['before_mad_bytes'] == aria_pack_dry['after_mad_bytes']
            assert aria_pack_real['after_mad_bytes'] < aria_pack_real['before_mad_bytes']
            assert aria_pack_real['index_rebuild_executed'] is True

            # 8. MA-AUDIT-UTILITY-MYISAMCHK
            ma_mychk_ext, ma_mychk_rec = run_ma_both(
                'run_myisamchk',
                {'database_name': 'sr_util_ma', 'table_name': 'myisam_items', 'mode': 'extend_check', 'include_information': True},
                {'database_name': 'sr_util_ma', 'table_name': 'myisam_items', 'mode': 'recover', 'backup': True, 'destructive_confirmed': True},
            )
            assert ma_mychk_ext['tool']['tool_version_identity'] == '12.2.2-MariaDB'
            assert ma_mychk_rec['repaired'] is True

            # 9. MA-AUDIT-UTILITY-MYISAMPACK
            ma_mypack_dry, ma_mypack_real = run_ma_both(
                'run_myisampack',
                {'database_name': 'sr_util_ma', 'table_name': 'myisam_pack_tbl', 'dry_run_test': True},
                {'database_name': 'sr_util_ma', 'table_name': 'myisam_pack_tbl', 'dry_run_test': False, 'backup': True, 'force': True, 'rebuild_indexes': True, 'destructive_confirmed': True},
            )
            assert ma_mypack_real['after_myd_bytes'] < ma_mypack_real['before_myd_bytes']
            assert ma_mypack_real['index_rebuild_executed'] is True

            # 10. MA-AUDIT-UTILITY-INNOCHECKSUM (count, page range, corrupt-copy detection, --write rewrite)
            ma_inno_cnt, ma_inno_range = run_ma_both(
                'run_innochecksum',
                {'database_name': 'sr_util_ma', 'table_name': 'inno_items', 'count_only': True},
                {'database_name': 'sr_util_ma', 'table_name': 'inno_items', 'start_page': 0, 'end_page': 2, 'page_type_summary': True, 'enable_private_log': True},
            )
            assert ma_inno_cnt['page_count'] >= 4 and ma_inno_range['checksum_valid'] is True

            # Stage corrupted copy of inno_items.ibd inside private workspace and detect corruption!
            _container_exec(
                cname,
                '''
set -e
cp /var/lib/mysql/sr_util_ma/inno_items.ibd /var/lib/sr-utility-workspace/corrupt_ma.ibd
chmod 600 /var/lib/sr-utility-workspace/corrupt_ma.ibd
printf '\\xFF\\xAA\\x55\\xFF' | dd of=/var/lib/sr-utility-workspace/corrupt_ma.ibd bs=1 seek=16600 conv=notrunc 2>/dev/null
''',
            )
            ma_inno_corrupt, ma_inno_rewrite = run_ma_both(
                'run_innochecksum',
                {'tablespace_scope': 'workspace_staged', 'tablespace_relpath': 'corrupt_ma.ibd'},
                {'tablespace_scope': 'workspace_staged', 'tablespace_relpath': 'corrupt_ma.ibd', 'no_check': True, 'rewrite_checksum': True, 'destructive_confirmed': True},
            )
            assert ma_inno_corrupt['corruption_detected'] is True and ma_inno_corrupt['checksum_valid'] is False
            assert ma_inno_rewrite['rewrite_applied'] is True
            # Verify rewritten staged .ibd now passes checksum verification!
            ma_inno_recheck_plan = native_client.plan_admin_operation({
                'resource_kind': 'server',
                'operation_id': 'run_innochecksum',
                'target_resource': target,
                'draft': {**host_base, 'tablespace_scope': 'workspace_staged', 'tablespace_relpath': 'corrupt_ma.ibd'},
                '_provider_route': route,
            })
            assert MARIADB_ADMINISTRATION.apply(native_client, ma_inno_recheck_plan)['mariadb_utility']['checksum_valid'] is True

            # --- RESTART MARIADBD & INDEPENDENT SQL READ-BACK VERIFICATION ---
            start_mariadbd()
            re_conn = None
            for _ in range(60):
                try:
                    re_conn = mariadb.connect(host='127.0.0.1', port=port, user='root', password=password, database='sr_util_ma', ssl=False, connect_timeout=3)
                    break
                except Exception:
                    time.sleep(0.5)
            assert re_conn is not None, 'mariadbd did not restart cleanly after offline utility operations'
            sql_readback = {}
            with closing(re_conn):
                re_conn.autocommit = True
                cur = re_conn.cursor()
                for tname, expected_cnt in (('aria_items', 500), ('aria_pack_tbl', 600), ('myisam_items', 500), ('myisam_pack_tbl', 600), ('inno_items', 200)):
                    cur.execute(f'CHECK TABLE `{tname}` EXTENDED')
                    chk_rows = cur.fetchall()
                    cur.execute(f'SELECT COUNT(*) FROM `{tname}`')
                    cnt = int(cur.fetchone()[0])
                    assert cnt == expected_cnt, (tname, cnt)
                    assert any(str(r[-1]).upper() == 'OK' for r in chk_rows), (tname, chk_rows)
                    sql_readback[tname] = {'row_count': cnt, 'check_extended_ok': True}

                for packed_tbl in ('aria_pack_tbl', 'myisam_pack_tbl'):
                    cur.execute('SHOW TABLE STATUS LIKE ?', (packed_tbl,))
                    st_row = cur.fetchone()
                    col_names = [d[0] for d in cur.description]
                    st_map = dict(zip(col_names, st_row))
                    read_only_errno = None
                    try:
                        cur.execute(f"INSERT INTO `{packed_tbl}` VALUES (999999, 'RO', 'should fail')")
                    except mariadb.Error as db_err:
                        read_only_errno = db_err.errno
                    assert read_only_errno == 1036, f'{packed_tbl} expected read-only errno 1036, got {read_only_errno}'
                    sql_readback[packed_tbl].update({
                        'row_format': str(st_map.get('Row_format')),
                        'read_only_write_refused_errno': read_only_errno,
                    })
                cur.close()

            receipt['utilities']['MA-AUDIT-UTILITY-ARIA_CHK'] = {
                'active_server_refusal': active_refusals['run_aria_chk'],
                'native_describe': aria_desc,
                'http_extend_check': aria_ext,
                'native_safe_recover': aria_rec,
                'http_zerofill': aria_zero,
                'post_restart_sql_readback': sql_readback['aria_items'],
            }
            receipt['utilities']['MA-AUDIT-UTILITY-ARIA_PACK'] = {
                'active_server_refusal': active_refusals['run_aria_pack'],
                'native_dry_run_test': aria_pack_dry,
                'http_pack_and_rebuild': aria_pack_real,
                'post_restart_sql_readback': sql_readback['aria_pack_tbl'],
            }
            receipt['utilities']['MA-AUDIT-UTILITY-MYISAMCHK'] = {
                'active_server_refusal': active_refusals['run_myisamchk'],
                'native_extend_check': ma_mychk_ext,
                'http_recover': ma_mychk_rec,
                'post_restart_sql_readback': sql_readback['myisam_items'],
            }
            receipt['utilities']['MA-AUDIT-UTILITY-MYISAMPACK'] = {
                'active_server_refusal': active_refusals['run_myisampack'],
                'native_dry_run_test': ma_mypack_dry,
                'http_pack_and_rebuild': ma_mypack_real,
                'post_restart_sql_readback': sql_readback['myisam_pack_tbl'],
            }
            receipt['utilities']['MA-AUDIT-UTILITY-INNOCHECKSUM'] = {
                'active_server_refusal': active_refusals['run_innochecksum'],
                'native_count': ma_inno_cnt,
                'http_page_range': ma_inno_range,
                'corrupt_copy_detected': ma_inno_corrupt,
                'http_rewrite_and_reverify': ma_inno_rewrite,
                'post_restart_sql_readback': sql_readback['inno_items'],
            }
        finally:
            native_client.close()
    finally:
        _run(_docker_cmd('rm', '-f', '-v', cname), check=False)
        inspect_after = _run(_docker_cmd('inspect', cname), check=False)
        receipt['container_removed'] = inspect_after.returncode != 0

    (output_dir / 'mariadb_utilities_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


def qualify_mysql(app, tmp_root: Path, output_dir: Path) -> dict:
    import mysql.connector
    from pgadmin.cdeadmin.providers.mysql_family.provider import (
        MYSQL_ADMINISTRATION,
        MYSQL_PROFILE,
        _create_client,
    )
    from pgadmin.cdeadmin.sdk import RelationalClientError
    from pgadmin.cdeadmin.security import SecretLease

    extracted = _prepare_mysql_970_binaries(tmp_root)
    cname = 'sr-batch4-mysql-' + secrets.token_hex(6)
    password = 'MyBatch4Secret_' + secrets.token_urlsafe(18)
    receipt: dict = {
        'engine': 'mysql',
        'version': None,
        'server_uuid': None,
        'utilities': {},
        'container_removed': False,
    }

    _run(
        _docker_cmd(
            'run', '-d', '--name', cname,
            '-p', '127.0.0.1::3306',
            '--entrypoint', 'sh',
            'mysql:9.7.0',
            '-c', 'trap "exit 0" TERM INT; while :; do sleep 1; done',
        )
    )
    try:
        # Copy exact MySQL 9.7.0 utility binaries and libmysqlclient.so.24 into disposable container
        for bname in ('myisamchk', 'myisampack', 'innochecksum', 'ibd2sdi', 'mysqlslap'):
            _run(_docker_cmd('cp', str(extracted / 'usr' / 'bin' / bname), f'{cname}:/usr/bin/{bname}'))
        for libfile in (extracted / 'usr' / 'lib64' / 'mysql').glob('libmysqlclient*'):
            if not libfile.is_symlink():
                _run(_docker_cmd('cp', str(libfile), f'{cname}:/usr/lib64/{libfile.name}'))
        _container_exec(
            cname,
            '''
set -e
chmod 755 /usr/bin/myisamchk /usr/bin/myisampack /usr/bin/innochecksum /usr/bin/ibd2sdi /usr/bin/mysqlslap
ln -sf /usr/lib64/libmysqlclient.so.24.* /usr/lib64/libmysqlclient.so.24
ldconfig
mkdir -p /var/lib/mysql /var/run/mysqld /var/lib/sr-utility-workspace
chown -R mysql:mysql /var/lib/mysql /var/run/mysqld
chmod 700 /var/lib/sr-utility-workspace
rm -rf /var/lib/mysql/*
mysqld --initialize-insecure --user=mysql --datadir=/var/lib/mysql
''',
        )

        def start_mysqld():
            _container_exec(
                cname,
                '''
set -e
mkdir -p /var/run/mysqld && chown mysql:mysql /var/run/mysqld
mysqld --user=mysql --datadir=/var/lib/mysql \
  --pid-file=/var/lib/mysql/mysqld.pid \
  --socket=/var/run/mysqld/mysqld.sock \
  --port=3306 --bind-address=0.0.0.0 \
  --log-error=/var/lib/mysql/mysqld.err >/dev/null 2>&1 &
''',
            )

        def stop_mysqld():
            _container_exec(
                cname,
                r'''
if [ -f /var/lib/mysql/mysqld.pid ]; then
  p=$(tr -d ' \t\r\n' < /var/lib/mysql/mysqld.pid)
  if [ -n "$p" ] && [ -d "/proc/$p" ]; then
    kill -TERM "$p" 2>/dev/null || true
    for _ in $(seq 1 80); do
      [ ! -d "/proc/$p" ] && break
      sleep 0.25
    done
    [ ! -d "/proc/$p" ] || { kill -KILL "$p" 2>/dev/null || true; sleep 0.5; }
  fi
fi
rm -f /var/lib/mysql/mysqld.pid /var/run/mysqld/mysqld.sock
''',
            )

        start_mysqld()
        port = _host_port(cname, 3306)

        bootstrap_my_sql = (
            f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{password}';\n"
            f"CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY '{password}';\n"
            f"ALTER USER 'root'@'%' IDENTIFIED BY '{password}';\n"
            "GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;\n"
            "FLUSH PRIVILEGES;\n"
        ).encode('utf-8')
        my_sock_ready = False
        for _ in range(80):
            probe = _run(
                _docker_cmd('exec', cname, 'mysql', '--protocol=socket', '--socket=/var/run/mysqld/mysqld.sock', '-u', 'root', '-e', 'SELECT 1'),
                check=False,
            )
            if probe.returncode == 0:
                my_sock_ready = True
                break
            time.sleep(0.5)
        if not my_sock_ready:
            err_log = _container_exec(cname, 'cat /var/lib/mysql/mysqld.err 2>/dev/null | tail -n 40 || true')
            raise RuntimeError(f'mysqld 9.7.0 socket did not become ready: {err_log}')
        _run(
            _docker_cmd('exec', '-i', cname, 'mysql', '--protocol=socket', '--socket=/var/run/mysqld/mysqld.sock', '-u', 'root'),
            input_bytes=bootstrap_my_sql,
        )

        conn = None
        for _ in range(80):
            try:
                conn = mysql.connector.connect(host='127.0.0.1', port=port, user='root', password=password, connection_timeout=3, use_pure=True)
                break
            except Exception:
                time.sleep(0.5)
        if conn is None:
            err_log = _container_exec(cname, 'cat /var/lib/mysql/mysqld.err 2>/dev/null | tail -n 40 || true')
            raise RuntimeError(f'mysqld 9.7.0 did not become ready on port {port}: {err_log}')

        with closing(conn):
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute('SELECT VERSION(), @@server_uuid')
            ver, server_uuid = cur.fetchone()
            assert str(ver).split('-')[0] == '9.7.0', f'Unexpected MySQL version: {ver}'
            receipt['version'] = str(ver)
            receipt['server_uuid'] = str(server_uuid)
            cur.execute('CREATE DATABASE sr_util_my CHARACTER SET utf8mb4')
            cur.execute(
                'CREATE TABLE sr_util_my.myisam_items('
                'id INT PRIMARY KEY, tag VARCHAR(64), payload VARCHAR(255), KEY idx_tag(tag)'
                ') ENGINE=MyISAM'
            )
            cur.execute(
                'CREATE TABLE sr_util_my.myisam_pack_tbl('
                'id INT PRIMARY KEY, grp VARCHAR(32), body VARCHAR(200), KEY idx_grp(grp)'
                ') ENGINE=MyISAM'
            )
            cur.execute(
                'CREATE TABLE sr_util_my.inno_orders('
                'order_id BIGINT PRIMARY KEY, customer_code VARCHAR(64) NOT NULL, notes TEXT, KEY idx_cust(customer_code)'
                ') ENGINE=InnoDB'
            )
            my_rows = [(i, f'MYTAG-{i:04d}', 'compressible_myisam_payload_' * 6) for i in range(1, 501)]
            cur.executemany('INSERT INTO sr_util_my.myisam_items VALUES (%s, %s, %s)', my_rows)
            pack_rows = [(i, f'G{i % 10}', 'REPEATED_MYSQL_MYISAM_BLOCK_' * 6) for i in range(1, 601)]
            cur.executemany('INSERT INTO sr_util_my.myisam_pack_tbl VALUES (%s, %s, %s)', pack_rows)
            inno_rows = [(i, f'CUST-{i:04d}', 'InnoDB 9.7.0 order payload ' * 12) for i in range(1, 201)]
            cur.executemany('INSERT INTO sr_util_my.inno_orders VALUES (%s, %s, %s)', inno_rows)
            cur.execute('FLUSH TABLES')
            cur.close()

        target = {
            'resource_kind': 'server',
            'resource_id': 'server:MySQL',
            'display_name': 'MySQL',
            'display_path': ['MySQL'],
            'native': {'server_uuid': server_uuid},
        }
        route_pure = {
            'host': '127.0.0.1',
            'port': port,
            'user': 'root',
            'database': 'sr_util_my',
            'use_pure': True,
            'autocommit': True,
            'principal_reference': 'qual-my-operator',
            'credential_reference_id': 'qual-my-secret',
        }
        route_c = {**route_pure, 'use_pure': False}
        native_client = _create_client(
            MYSQL_PROFILE,
            SimpleNamespace(acquire_secret=lambda *_: SecretLease(password.encode('utf-8'))),
            SimpleNamespace(pool_namespace='qual-my-' + uuid.uuid4().hex),
        )
        http = _register_http_endpoint(
            app,
            profile_id='mysql-native',
            engine_key='mysql',
            name='Qual MySQL 9.7.0 Utilities',
            host='127.0.0.1',
            port=port,
            password=password,
            database='sr_util_my',
            use_pure=True,
        )
        host_base = {
            'execution_host_kind': 'container',
            'container_name': cname,
            'datadir': '/var/lib/mysql',
            'workspace': '/var/lib/sr-utility-workspace',
            'pid_file': '/var/lib/mysql/mysqld.pid',
            'socket_path': '/var/run/mysqld/mysqld.sock',
            'timeout_seconds': 90,
            'confirmation': 'MySQL',
        }

        try:
            # --- ONLINE PHASE 1: Active-server refusal for all 4 offline MySQL utilities (native + HTTP) ---
            offline_refusal_cases = [
                ('run_myisamchk', {'database_name': 'sr_util_my', 'table_name': 'myisam_items', 'mode': 'check'}),
                ('run_myisampack', {'database_name': 'sr_util_my', 'table_name': 'myisam_pack_tbl', 'dry_run_test': True}),
                ('run_innochecksum', {'database_name': 'sr_util_my', 'table_name': 'inno_orders', 'count_only': True}),
                ('run_ibd2sdi', {'database_name': 'sr_util_my', 'table_name': 'inno_orders'}),
            ]
            active_refusals = {}
            for op_id, extra in offline_refusal_cases:
                draft = {**host_base, **extra}
                try:
                    native_client.plan_admin_operation({
                        'resource_kind': 'server',
                        'operation_id': op_id,
                        'target_resource': target,
                        'draft': draft,
                        '_provider_route': route_pure,
                    })
                    raise AssertionError(f'{op_id} did not refuse active mysqld natively!')
                except RelationalClientError as exc:
                    native_msg = str(exc)
                    assert 'Refused offline' in native_msg
                http_resp = http.raw('visual_admin_plan', {
                    'resource_kind': 'server',
                    'operation_id': op_id,
                    'target_resource': target,
                    'draft': draft,
                })
                assert http_resp.status_code != 200 or not http_resp.get_json().get('success')
                job_resp = http.raw('mysql_utility_review', {
                    'operation_id': op_id,
                    'target_resource': target,
                    'draft': draft,
                })
                assert job_resp.status_code != 200 or not job_resp.get_json().get('success')
                active_refusals[op_id] = {'native_refused': True, 'http_refused': True, 'message': native_msg}

            # --- ONLINE PHASE 2: MY-AUDIT-UTILITY-MYSQLSLAP (pure + C native + HTTP + cancel + timeout + redaction) ---
            slap_pure_plan = native_client.plan_admin_operation({
                'resource_kind': 'server',
                'operation_id': 'run_mysqlslap',
                'target_resource': target,
                'draft': {
                    **host_base,
                    'benchmark_schema': 'cdeadmin_slap_my_pure',
                    'concurrency': '1,4',
                    'iterations': 2,
                    'number_of_queries': 40,
                    'workload_mode': 'auto_generate',
                    'auto_load_type': 'mixed',
                    'isolated_scratch_confirmed': True,
                },
                '_provider_route': route_pure,
            })
            assert password not in json.dumps(slap_pure_plan['command_preview'])
            slap_pure_res = MYSQL_ADMINISTRATION.apply(native_client, slap_pure_plan)['mysql_utility']
            assert password not in json.dumps(slap_pure_res)
            assert slap_pure_res['tool']['tool_version_identity'] == '9.7.0'
            assert slap_pure_res['metrics']['run_count'] >= 2
            assert slap_pure_res['scratch_schema_cleaned_up'] is True

            # C extension interface check
            slap_c_plan = native_client.plan_admin_operation({
                'resource_kind': 'server',
                'operation_id': 'run_mysqlslap',
                'target_resource': target,
                'draft': {
                    **host_base,
                    'benchmark_schema': 'cdeadmin_slap_my_cext',
                    'concurrency': '2',
                    'iterations': 1,
                    'number_of_queries': 20,
                    'workload_mode': 'auto_generate',
                    'auto_load_type': 'read',
                    'isolated_scratch_confirmed': True,
                },
                '_provider_route': route_c,
            })
            slap_c_res = MYSQL_ADMINISTRATION.apply(native_client, slap_c_plan)['mysql_utility']
            assert slap_c_res['scratch_schema_cleaned_up'] is True

            # HTTP visual_admin explicit SQL benchmark + replay refusal
            slap_http_req = {
                'resource_kind': 'server',
                'operation_id': 'run_mysqlslap',
                'target_resource': target,
                'draft': {
                    **host_base,
                    'benchmark_schema': 'cdeadmin_slap_my_http',
                    'concurrency': '3',
                    'iterations': 2,
                    'number_of_queries': 30,
                    'workload_mode': 'explicit_sql',
                    'create_sql': "CREATE TABLE bench_kv (k INT PRIMARY KEY, v VARCHAR(64)); INSERT INTO bench_kv VALUES (1, 'alpha'), (2, 'beta');",
                    'query_sql': 'SELECT v FROM bench_kv WHERE k = 1;',
                    'isolated_scratch_confirmed': True,
                },
            }
            assert http.ok('visual_admin_validate', slap_http_req)['valid']
            v_plan = http.ok('visual_admin_plan', slap_http_req)
            assert password not in json.dumps(v_plan)
            v_apply_body = {'plan_id': v_plan['plan_id'], 'plan_digest': v_plan['plan_digest'], 'confirmed': True}
            v_applied = http.ok('visual_admin_apply', v_apply_body)
            assert password not in json.dumps(v_applied)
            http_slap_obs = v_applied['provider_result']['mysql_utility']
            assert http_slap_obs['metrics']['clients_per_run'] == 3
            assert http_slap_obs['scratch_schema_cleaned_up'] is True
            replay_resp = http.raw('visual_admin_apply', v_apply_body)
            assert replay_resp.status_code != 200 or not replay_resp.get_json().get('success')

            # HTTP mid-flight cancellation via mysql_utility_* workspace actions
            cancel_rev = http.ok('mysql_utility_review', {
                'operation_id': 'run_mysqlslap',
                'target_resource': target,
                'draft': {
                    **host_base,
                    'benchmark_schema': 'cdeadmin_slap_my_cancel',
                    'concurrency': '2',
                    'iterations': 5,
                    'workload_mode': 'explicit_sql',
                    'query_sql': 'SELECT SLEEP(2);',
                    'number_of_queries': 20,
                    'isolated_scratch_confirmed': True,
                },
            })
            http.ok('mysql_utility_start', {
                'job_id': cancel_rev['job_id'],
                'review_digest': cancel_rev['review_digest'],
                'confirmed': True,
                'async_execution': True,
            })
            time.sleep(0.6)
            cancelled_job = http.ok('mysql_utility_cancel', {'job_id': cancel_rev['job_id']})
            assert cancelled_job['state'] == 'cancelled' and cancelled_job['cleanup_confirmed'] is True

            # Bounded timeout check
            to_plan = native_client.plan_admin_operation({
                'resource_kind': 'server',
                'operation_id': 'run_mysqlslap',
                'target_resource': target,
                'draft': {
                    **host_base,
                    'timeout_seconds': 1,
                    'benchmark_schema': 'cdeadmin_slap_my_timeout',
                    'concurrency': '1',
                    'iterations': 1,
                    'workload_mode': 'explicit_sql',
                    'query_sql': 'SELECT SLEEP(5);',
                    'isolated_scratch_confirmed': True,
                },
                '_provider_route': route_pure,
            })
            try:
                MYSQL_ADMINISTRATION.apply(native_client, to_plan)
                raise AssertionError('Expected mysqlslap timeout')
            except RelationalClientError as exc:
                assert 'timed out' in str(exc) and exc.cleanup_confirmed is True

            receipt['utilities']['MY-AUDIT-UTILITY-MYSQLSLAP'] = {
                'native_pure': slap_pure_res,
                'native_c': slap_c_res,
                'http': http_slap_obs,
                'cancellation_verified': True,
                'timeout_verified': True,
                'credential_redaction_verified': True,
                'replay_refused': True,
            }

            # --- STOP MYSQLD FOR OFFLINE PHASE ---
            stop_mysqld()

            def run_my_both(op_id: str, native_extra: dict, http_extra: dict):
                n_plan = native_client.plan_admin_operation({
                    'resource_kind': 'server',
                    'operation_id': op_id,
                    'target_resource': target,
                    'draft': {**host_base, **native_extra},
                    '_provider_route': route_pure,
                })
                n_res = MYSQL_ADMINISTRATION.apply(native_client, n_plan)['mysql_utility']
                h_req = {
                    'resource_kind': 'server',
                    'operation_id': op_id,
                    'target_resource': target,
                    'draft': {**host_base, **http_extra},
                }
                assert http.ok('visual_admin_validate', h_req)['valid']
                h_plan = http.ok('visual_admin_plan', h_req)
                h_res = http.ok(
                    'visual_admin_apply',
                    {'plan_id': h_plan['plan_id'], 'plan_digest': h_plan['plan_digest'], 'confirmed': True},
                )['provider_result']['mysql_utility']
                return n_res, h_res

            # 1. MY-AUDIT-UTILITY-MYISAMCHK
            mychk_info, mychk_rec = run_my_both(
                'run_myisamchk',
                {'database_name': 'sr_util_my', 'table_name': 'myisam_items', 'mode': 'information'},
                {'database_name': 'sr_util_my', 'table_name': 'myisam_items', 'mode': 'recover', 'backup': True, 'destructive_confirmed': True},
            )
            mychk_sort, mychk_anlz = run_my_both(
                'run_myisamchk',
                {'database_name': 'sr_util_my', 'table_name': 'myisam_items', 'mode': 'sort_index', 'backup': True, 'destructive_confirmed': True},
                {'database_name': 'sr_util_my', 'table_name': 'myisam_items', 'mode': 'analyze', 'backup': True, 'destructive_confirmed': True},
            )
            assert mychk_info['check_passed'] and mychk_rec['repaired'] and mychk_sort['repaired'] and mychk_anlz['repaired']

            # 2. MY-AUDIT-UTILITY-MYISAMPACK (dry-run --test native, real pack + myisamchk -rq over HTTP!)
            mypack_dry, mypack_real = run_my_both(
                'run_myisampack',
                {'database_name': 'sr_util_my', 'table_name': 'myisam_pack_tbl', 'dry_run_test': True},
                {'database_name': 'sr_util_my', 'table_name': 'myisam_pack_tbl', 'dry_run_test': False, 'backup': True, 'force': True, 'rebuild_indexes': True, 'destructive_confirmed': True},
            )
            assert mypack_dry['dry_run_test'] is True and mypack_dry['before_myd_bytes'] == mypack_dry['after_myd_bytes']
            assert mypack_real['after_myd_bytes'] < mypack_real['before_myd_bytes']
            assert mypack_real['index_rebuild_executed'] is True

            # 3. MY-AUDIT-UTILITY-INNOCHECKSUM (count, page range, corrupt-copy detection, --write=crc32)
            my_inno_cnt, my_inno_range = run_my_both(
                'run_innochecksum',
                {'database_name': 'sr_util_my', 'table_name': 'inno_orders', 'count_only': True},
                {'database_name': 'sr_util_my', 'table_name': 'inno_orders', 'start_page': 0, 'end_page': 2, 'strict_check': 'crc32', 'enable_private_log': True},
            )
            assert my_inno_cnt['page_count'] >= 4 and my_inno_range['checksum_valid'] is True

            _container_exec(
                cname,
                '''
set -e
cp /var/lib/mysql/sr_util_my/inno_orders.ibd /var/lib/sr-utility-workspace/corrupt_my.ibd
chmod 600 /var/lib/sr-utility-workspace/corrupt_my.ibd
printf '\\xFF\\xAA\\x55\\xFF' | dd of=/var/lib/sr-utility-workspace/corrupt_my.ibd bs=1 seek=16600 conv=notrunc 2>/dev/null
''',
            )
            my_inno_corrupt, my_inno_rewrite = run_my_both(
                'run_innochecksum',
                {'tablespace_scope': 'workspace_staged', 'tablespace_relpath': 'corrupt_my.ibd', 'strict_check': 'crc32'},
                {'tablespace_scope': 'workspace_staged', 'tablespace_relpath': 'corrupt_my.ibd', 'no_check': True, 'write_algorithm': 'crc32', 'destructive_confirmed': True},
            )
            assert my_inno_corrupt['corruption_detected'] is True and my_inno_corrupt['checksum_valid'] is False
            assert my_inno_rewrite['rewrite_applied'] is True
            recheck_plan = native_client.plan_admin_operation({
                'resource_kind': 'server',
                'operation_id': 'run_innochecksum',
                'target_resource': target,
                'draft': {**host_base, 'tablespace_scope': 'workspace_staged', 'tablespace_relpath': 'corrupt_my.ibd', 'strict_check': 'crc32'},
                '_provider_route': route_pure,
            })
            assert MYSQL_ADMINISTRATION.apply(native_client, recheck_plan)['mysql_utility']['checksum_valid'] is True

            # 4. MY-AUDIT-UTILITY-IBD2SDI (full table metadata extraction + --skip-data over HTTP)
            my_sdi_full, my_sdi_skip = run_my_both(
                'run_ibd2sdi',
                {'database_name': 'sr_util_my', 'table_name': 'inno_orders', 'sdi_type': 1, 'strict_check': 'crc32'},
                {'database_name': 'sr_util_my', 'table_name': 'inno_orders', 'skip_data': True, 'strict_check': 'crc32'},
            )
            sdi_objs = my_sdi_full['sdi_metadata']['objects']
            assert len(sdi_objs) == 1 and sdi_objs[0]['name'] == 'inno_orders'
            extracted_cols = [c['name'] for c in sdi_objs[0]['columns']]
            extracted_idxs = sdi_objs[0]['indexes']
            assert extracted_cols == ['order_id', 'customer_code', 'notes']
            assert 'PRIMARY' in extracted_idxs and 'idx_cust' in extracted_idxs
            assert my_sdi_skip['sdi_metadata']['record_count'] >= 1

            # --- RESTART MYSQLD & INDEPENDENT SQL READ-BACK VERIFICATION (BOTH PURE & C CONNECTORS) ---
            start_mysqld()
            re_conn = None
            for _ in range(80):
                try:
                    re_conn = mysql.connector.connect(host='127.0.0.1', port=port, user='root', password=password, database='sr_util_my', connection_timeout=2, use_pure=False)
                    break
                except Exception:
                    time.sleep(0.5)
            assert re_conn is not None, 'mysqld did not restart cleanly after offline utility operations'
            sql_readback = {}
            with closing(re_conn):
                re_conn.autocommit = True
                cur = re_conn.cursor()
                for tname, expected_cnt in (('myisam_items', 500), ('myisam_pack_tbl', 600), ('inno_orders', 200)):
                    cur.execute(f'CHECK TABLE `{tname}` EXTENDED')
                    chk_rows = cur.fetchall()
                    cur.execute(f'SELECT COUNT(*) FROM `{tname}`')
                    cnt = int(cur.fetchone()[0])
                    assert cnt == expected_cnt, (tname, cnt)
                    assert any(str(r[-1]).upper() == 'OK' for r in chk_rows), (tname, chk_rows)
                    sql_readback[tname] = {'row_count': cnt, 'check_extended_ok': True}

                cur.execute("SHOW TABLE STATUS LIKE 'myisam_pack_tbl'")
                st_row = cur.fetchone()
                st_map = dict(zip([d[0] for d in cur.description], st_row))
                assert st_map.get('Row_format') == 'Compressed', st_map
                read_only_errno = None
                try:
                    cur.execute("INSERT INTO `myisam_pack_tbl` VALUES (999999, 'RO', 'should fail')")
                except mysql.connector.Error as db_err:
                    read_only_errno = db_err.errno
                assert read_only_errno == 1036, f'Expected MySQL read-only errno 1036, got {read_only_errno}'
                sql_readback['myisam_pack_tbl'].update({
                    'row_format': str(st_map.get('Row_format')),
                    'read_only_write_refused_errno': read_only_errno,
                })

                # Cross-check live InnoDB columns against ibd2sdi extracted columns!
                cur.execute(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = 'sr_util_my' AND TABLE_NAME = 'inno_orders' ORDER BY ORDINAL_POSITION"
                )
                live_cols = [r[0] for r in cur.fetchall()]
                assert live_cols == extracted_cols
                sql_readback['inno_orders']['live_columns_match_ibd2sdi'] = True
                cur.close()

            receipt['utilities']['MY-AUDIT-UTILITY-MYISAMCHK'] = {
                'active_server_refusal': active_refusals['run_myisamchk'],
                'native_information': mychk_info,
                'http_recover': mychk_rec,
                'native_sort_index': mychk_sort,
                'http_analyze': mychk_anlz,
                'post_restart_sql_readback': sql_readback['myisam_items'],
            }
            receipt['utilities']['MY-AUDIT-UTILITY-MYISAMPACK'] = {
                'active_server_refusal': active_refusals['run_myisampack'],
                'native_dry_run_test': mypack_dry,
                'http_pack_and_rebuild': mypack_real,
                'post_restart_sql_readback': sql_readback['myisam_pack_tbl'],
            }
            receipt['utilities']['MY-AUDIT-UTILITY-INNOCHECKSUM'] = {
                'active_server_refusal': active_refusals['run_innochecksum'],
                'native_count': my_inno_cnt,
                'http_page_range': my_inno_range,
                'corrupt_copy_detected': my_inno_corrupt,
                'http_rewrite_and_reverify': my_inno_rewrite,
                'post_restart_sql_readback': sql_readback['inno_orders'],
            }
            receipt['utilities']['MY-AUDIT-UTILITY-IBD2SDI'] = {
                'active_server_refusal': active_refusals['run_ibd2sdi'],
                'native_full_sdi': my_sdi_full,
                'http_skip_data_sdi': my_sdi_skip,
                'post_restart_sql_readback': sql_readback['inno_orders'],
            }
        finally:
            native_client.close()
    finally:
        _run(_docker_cmd('rm', '-f', '-v', cname), check=False)
        inspect_after = _run(_docker_cmd('inspect', cname), check=False)
        receipt['container_removed'] = inspect_after.returncode != 0

    (output_dir / 'mysql_utilities_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tmp-root', type=Path, required=True)
    args = parser.parse_args(argv)

    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_root = args.tmp_root.resolve()
    tmp_root.mkdir(parents=True, exist_ok=True)
    run_tmp = Path(tempfile.mkdtemp(prefix='batch4-qual-', dir=str(tmp_root)))

    tracked_sources = [
        'web/pgadmin/cdeadmin/providers/mysql_family/utility_host_worker.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_utilities.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_utilities.py',
        'web/pgadmin/cdeadmin/workspace/mysql_utility_service.py',
        'web/pgadmin/cdeadmin/workspace/mariadb_utility_service.py',
        'web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',
        'web/pgadmin/cdeadmin/ui_descriptors/mysql/capabilities.json',
        'web/pgadmin/cdeadmin/ui_descriptors/mariadb/operations.json',
        'web/pgadmin/cdeadmin/ui_descriptors/mariadb/capabilities.json',
    ]

    summary = {
        'schema': 'cdeadmin.mysql-mariadb-batch4-utilities-qualification.v1',
        'complete': False,
        'history_testing': 'ScratchBird persistent monitoring /history not run',
        'source_sha256': {
            rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
            for rel in tracked_sources
        },
        'mysql': None,
        'mariadb': None,
    }
    try:
        app = _setup_flask_app(run_tmp / 'flask-app')
        ma_receipt = qualify_mariadb(app, tmp_root, output_dir)
        my_receipt = qualify_mysql(app, tmp_root, output_dir)
        expected_my = {
            'MY-AUDIT-UTILITY-MYISAMCHK',
            'MY-AUDIT-UTILITY-MYISAMPACK',
            'MY-AUDIT-UTILITY-INNOCHECKSUM',
            'MY-AUDIT-UTILITY-IBD2SDI',
            'MY-AUDIT-UTILITY-MYSQLSLAP',
        }
        expected_ma = {
            'MA-AUDIT-UTILITY-ARIA_CHK',
            'MA-AUDIT-UTILITY-ARIA_PACK',
            'MA-AUDIT-UTILITY-MYISAMCHK',
            'MA-AUDIT-UTILITY-MYISAMPACK',
            'MA-AUDIT-UTILITY-INNOCHECKSUM',
            'MA-AUDIT-UTILITY-MARIADB-SLAP',
        }
        assert set(my_receipt['utilities']) == expected_my
        assert set(ma_receipt['utilities']) == expected_ma
        assert my_receipt['container_removed'] is True
        assert ma_receipt['container_removed'] is True
        summary['mysql'] = {
            'version': my_receipt['version'],
            'server_uuid': my_receipt['server_uuid'],
            'qualified_items': sorted(my_receipt['utilities']),
            'container_removed': my_receipt['container_removed'],
        }
        summary['mariadb'] = {
            'version': ma_receipt['version'],
            'server_uid': ma_receipt['server_uid'],
            'qualified_items': sorted(ma_receipt['utilities']),
            'container_removed': ma_receipt['container_removed'],
        }
        summary['total_qualified_utilities'] = 11
        summary['complete'] = True
    finally:
        shutil.rmtree(run_tmp, ignore_errors=True)
        (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')

    print(json.dumps(summary, indent=2))
    return 0 if summary['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
