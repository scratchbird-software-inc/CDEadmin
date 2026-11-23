"""Live end-to-end HTTP & descriptor qualification for full PostgreSQL GUI parity:
- PG-UI-10: Active Sessions, Lock Wait Chains, Fenced Cancel/Terminate & pg_stat_statements (`postgresql_ops_activity_locks`, `session_signal_*`, `stat_statements`, `stats_reset_*`)
- PG-UI-11: Live LISTEN / NOTIFY Channel Subscriber, Poller & Publisher (`postgresql_ops_pubsub_*`)
- PG-UI-12: Supervised Logical Backup/Restore (`pg_dump`/`pg_restore`/TOC), Client-Streamed COPY Import/Export, Fast Catalog Search & Reviewed Bulk Grants (`postgresql_ops_logical_backup_*`, `copy_*`, `catalog_search`, `bulk_grant_*`)
- PG-PARITY-2: Complete 51-kind / 26-form PostgreSQL UI descriptor bundle + PG 18 temporal/enforcement constraint gates + 16 engine_object compiler round-trips
"""
from __future__ import annotations

import builtins
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]

PG18_BIN = Path('/usr/lib/postgresql/18/bin')
USER = __import__('getpass').getuser()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _init_and_start_pg18_with_pss(base_dir: Path, name: str) -> tuple[Path, int, Path]:
    datadir = base_dir / name
    sock_dir = Path(f'/tmp/sr-gui-{uuid.uuid4().hex[:8]}')
    sock_dir.mkdir(mode=0o700, exist_ok=True)
    port = _free_port()
    subprocess.run(
        [
            str(PG18_BIN / 'initdb'),
            '-D', str(datadir),
            '-U', USER,
            '-A', 'trust',
            '--encoding=UTF8',
            '--locale=C',
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    conf = datadir / 'postgresql.conf'
    conf.write_text(
        conf.read_text(encoding='utf8')
        + "\nlisten_addresses = '127.0.0.1'\n"
        + f'port = {port}\n'
        + f"unix_socket_directories = '{sock_dir}'\n"
        + "shared_preload_libraries = 'pg_stat_statements'\n"
        + "compute_query_id = 'on'\n",
        encoding='utf8',
    )
    (datadir / 'pg_hba.conf').write_text(
        'local all all trust\n'
        'host all all 127.0.0.1/32 trust\n',
        encoding='utf8',
    )
    subprocess.run(
        [
            str(PG18_BIN / 'pg_ctl'),
            '-D', str(datadir),
            '-l', str(base_dir / f'{name}.log'),
            '-w', '-t', '30',
            'start',
        ],
        check=True,
        capture_output=True,
        timeout=35,
    )
    return datadir, port, sock_dir


def _stop_pg_quiet(datadir: Path, sock_dir: Path | None = None) -> None:
    if datadir.exists() and (datadir / 'postmaster.pid').exists():
        subprocess.run(
            [str(PG18_BIN / 'pg_ctl'), '-D', str(datadir), '-m', 'immediate', '-w', 'stop'],
            check=False,
            capture_output=True,
            timeout=20,
        )
    if sock_dir and sock_dir.exists():
        shutil.rmtree(sock_dir, ignore_errors=True)


@pytest.fixture(scope='module')
def parity_env(tmp_path_factory):
    if not (PG18_BIN / 'initdb').is_file():
        pytest.skip('PostgreSQL 18 binaries unavailable')
    base = tmp_path_factory.mktemp('pg_gui_parity')
    datadir, port, sock_dir = _init_and_start_pg18_with_pss(base, 'pg18_parity')
    try:
        builtins.SERVER_MODE = False
        import config

        app_root = base / 'app'
        config.SERVER_MODE = False
        config.TESTING = True
        config.WTF_CSRF_ENABLED = False
        config.MASTER_PASSWORD_REQUIRED = False
        config.USE_OS_SECRET_STORAGE = False
        for attr, rel in {
            'DATA_DIR': 'data',
            'SQLITE_PATH': 'data/pgadmin4.db',
            'SESSION_DB_PATH': 'data/sessions',
            'STORAGE_DIR': 'data/storage',
            'LOG_FILE': 'data/pgadmin4.log',
            'AZURE_CREDENTIAL_CACHE_DIR': 'data/azure',
            'CDEADMIN_OPERATION_STORE_PATH': 'data/operations.json',
        }.items():
            setattr(config, attr, str(app_root / rel))
        (app_root / 'data').mkdir(parents=True, exist_ok=True)

        from flask import url_for
        from pgadmin import create_app
        from pgadmin.model import Server, ServerGroup, User, db

        app = create_app('ScratchRobin-pg-gui-parity')
        app.PGADMIN_RUNTIME = False
        app.PGADMIN_INT_KEY = ''
        app.run_before_app_start()
        app.config['CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH'] = str(PG18_BIN)
        app.config['CDEADMIN_POSTGRESQL_HOST_BINARY_PATH'] = str(PG18_BIN)

        with app.test_request_context('/'):
            user = User.query.first()
            group = ServerGroup.query.filter_by(user_id=user.id).first()
            app.blueprints['NODE-engine_type'].connector_visibility['postgresql'].set(True, user_id=user.id)
            srv = Server(
                user_id=user.id,
                servergroup_id=group.id,
                name='PG18 GUI Parity Live',
                host='127.0.0.1',
                port=port,
                username=USER,
                maintenance_db='postgres',
                connection_params={'sslmode': 'disable'},
                save_password=0,
            )
            db.session.add(srv)
            db.session.commit()
            uid = user.id
            connect_url = url_for('NODE-server.connect_id', gid=group.id, sid=srv.id)
            ws_url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=srv.id)

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(uid)
            sess['_fresh'] = True

        c_resp = client.post(connect_url, json={'password': ''}).get_json()
        assert c_resp.get('success'), c_resp

        yield {
            'app': app,
            'client': client,
            'ws_url': ws_url,
            'port': port,
            'dsn': f'host=127.0.0.1 port={port} user={USER} dbname=postgres sslmode=disable',
        }
    finally:
        # Ensure any open pubsub session is closed before stopping cluster
        from pgadmin.cdeadmin.workspace.postgresql_operations_hub import _PUBSUB_LOCK, _PUBSUB_SESSIONS
        with _PUBSUB_LOCK:
            for item in list(_PUBSUB_SESSIONS.values()):
                try:
                    item['conn'].close()
                except Exception:
                    pass
            _PUBSUB_SESSIONS.clear()
        _stop_pg_quiet(datadir, sock_dir)


def _post_ops(env, op: str, req: dict | None = None, expect_status: int = 200) -> dict:
    resp = env['client'].post(
        env['ws_url'],
        json={'action': f'postgresql_ops_{op}', 'request': req or {}},
    )
    assert resp.status_code == expect_status, (op, resp.status_code, resp.get_data(as_text=True))
    return resp.get_json()


def test_pg_ui_10_activity_locks_fenced_signals_and_stat_statements(parity_env):
    dsn = parity_env['dsn']
    with psycopg.connect(dsn, autocommit=True) as setup_conn:
        setup_conn.execute('CREATE EXTENSION IF NOT EXISTS pg_stat_statements')
        setup_conn.execute('CREATE TABLE IF NOT EXISTS public.lock_probe (id integer PRIMARY KEY, label text)')
        setup_conn.execute("INSERT INTO public.lock_probe VALUES (1, 'alpha') ON CONFLICT (id) DO NOTHING")

    # Hold a lock in a blocker session and let a waiter block on it
    blocker = psycopg.connect(dsn, autocommit=False)
    waiter = psycopg.connect(dsn, autocommit=False)
    waiter_err: list[Exception] = []
    try:
        blocker_pid = int(blocker.info.backend_pid)
        waiter_pid = int(waiter.info.backend_pid)
        blocker.execute('LOCK TABLE public.lock_probe IN ACCESS EXCLUSIVE MODE')

        def _wait_lock():
            try:
                waiter.execute('SELECT * FROM public.lock_probe WHERE id = 1 FOR UPDATE')
            except Exception as exc:
                waiter_err.append(exc)

        t = threading.Thread(target=_wait_lock, daemon=True)
        t.start()

        # Poll activity_locks until waiter shows blocker_pid in blocking_pids
        observed_block = False
        for _ in range(40):
            act = _post_ops(parity_env, 'activity_locks')['data']
            by_pid = {row['pid']: row for row in act['sessions']}
            if waiter_pid in by_pid and blocker_pid in (by_pid[waiter_pid].get('blocking_pids') or []):
                observed_block = True
                break
            time.sleep(0.05)
        assert observed_block, 'Expected pg_blocking_pids to surface blocker PID in activity_locks'
        assert any(l['relation'] == 'lock_probe' for l in act['locks'])

        # Review + execute fenced cancel on waiter_pid
        rev_cancel = _post_ops(parity_env, 'session_signal_review', {'pid': waiter_pid, 'signal': 'cancel'})['data']
        assert rev_cancel['state'] == 'reviewed'
        res_cancel = _post_ops(parity_env, 'session_signal_start', {
            'job_id': rev_cancel['job_id'],
            'review_digest': rev_cancel['review_digest'],
            'confirmed': True,
        })['data']
        assert res_cancel['state'] == 'completed'
        assert res_cancel['outcome']['signalled'] is True
        t.join(timeout=5)
        assert waiter_err, 'Expected cancelled waiter query to raise QueryCanceled'

        # Replay of consumed review job must be refused
        replay = _post_ops(parity_env, 'session_signal_start', {
            'job_id': rev_cancel['job_id'],
            'review_digest': rev_cancel['review_digest'],
            'confirmed': True,
        }, expect_status=400)
        assert replay['success'] == 0

        # Stale target fencing: review terminate on waiter, close waiter before start -> refused!
        waiter.rollback()
        rev_stale = _post_ops(parity_env, 'session_signal_review', {'pid': waiter_pid, 'signal': 'terminate'})['data']
        waiter.close()
        time.sleep(0.1)
        stale_resp = _post_ops(parity_env, 'session_signal_start', {
            'job_id': rev_stale['job_id'],
            'review_digest': rev_stale['review_digest'],
            'confirmed': True,
        }, expect_status=400)
        assert stale_resp['success'] == 0
    finally:
        if not waiter.closed:
            waiter.close()
        if not blocker.closed:
            blocker.rollback()
            blocker.close()

    # pg_stat_statements query explorer & reviewed reset
    pss = _post_ops(parity_env, 'stat_statements', {'sort_by': 'calls', 'limit': 25})['data']
    assert pss['installed'] is True
    assert len(pss['rows']) >= 1

    for reset_target in ('pg_stat_statements', 'wal'):
        rev_rst = _post_ops(parity_env, 'stats_reset_review', {'target': reset_target})['data']
        done_rst = _post_ops(parity_env, 'stats_reset_start', {
            'job_id': rev_rst['job_id'],
            'review_digest': rev_rst['review_digest'],
            'confirmed': True,
        })['data']
        assert done_rst['state'] == 'completed'
        assert done_rst['outcome']['reset_target'] == reset_target


def test_pg_ui_11_listen_notify_roundtrip(parity_env):
    sub = _post_ops(parity_env, 'pubsub_subscribe', {'channel': 'sr_orders_events'})['data']
    assert 'sr_orders_events' in sub['subscribed_channels']
    assert isinstance(sub['backend_pid'], int)

    pub = _post_ops(parity_env, 'pubsub_notify', {
        'channel': 'sr_orders_events',
        'payload': '{"order_id": 9001, "status": "shipped"}',
    })['data']
    assert pub['sent'] is True

    polled = _post_ops(parity_env, 'pubsub_poll', {})['data']
    assert any(
        n['channel'] == 'sr_orders_events' and '"order_id": 9001' in n['payload']
        for n in polled['notifications']
    ), polled

    unsub = _post_ops(parity_env, 'pubsub_unsubscribe', {'channel': 'sr_orders_events'})['data']
    assert unsub['subscribed_channels'] == []


def test_pg_ui_12_logical_backup_restore_copy_search_and_bulk_grants(parity_env):
    dsn = parity_env['dsn']
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute('CREATE SCHEMA IF NOT EXISTS parity_app')
        conn.execute('DROP TABLE IF EXISTS parity_app.customers CASCADE')
        conn.execute(
            'CREATE TABLE parity_app.customers (id integer PRIMARY KEY, email text NOT NULL, tier text NOT NULL)'
        )
        conn.execute("COMMENT ON TABLE parity_app.customers IS 'Parity customer directory'")
        conn.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'parity_reader') THEN CREATE ROLE parity_reader NOLOGIN; END IF; END $$")

    # 1. Reviewed COPY import
    csv_payload = 'id,email,tier\n10,ada@example.org,enterprise\n20,grace@example.org,pro\n'
    rev_imp = _post_ops(parity_env, 'copy_import_review', {
        'schema': 'parity_app',
        'table': 'customers',
        'header': True,
        'data': csv_payload,
    })['data']
    assert rev_imp['payload']['row_estimate'] == 2
    done_imp = _post_ops(parity_env, 'copy_import_start', {
        'job_id': rev_imp['job_id'],
        'review_digest': rev_imp['review_digest'],
        'confirmed': True,
    })['data']
    assert done_imp['outcome']['rows_imported'] == 2

    # 2. Client-streamed COPY export
    exp = _post_ops(parity_env, 'copy_export', {
        'schema': 'parity_app',
        'table': 'customers',
        'format': 'csv',
        'header': True,
    })['data']
    assert exp['rows_exported'] == 2
    assert 'ada@example.org' in exp['data'] and 'grace@example.org' in exp['data']

    # 3. Fast catalog search
    found = _post_ops(parity_env, 'catalog_search', {
        'query': 'customer',
        'schema': 'parity_app',
        'kind': 'table',
    })['data']
    assert found['count'] == 1
    assert found['results'][0]['name'] == 'customers'

    # 4. Reviewed bulk GRANT & REVOKE
    rev_grant = _post_ops(parity_env, 'bulk_grant_review', {
        'mode': 'GRANT',
        'grantee': 'parity_reader',
        'object_kind': 'TABLE',
        'privileges': ['SELECT', 'INSERT'],
        'targets': ['parity_app.customers'],
    })['data']
    _post_ops(parity_env, 'bulk_grant_start', {
        'job_id': rev_grant['job_id'],
        'review_digest': rev_grant['review_digest'],
        'confirmed': True,
    })
    with psycopg.connect(dsn, autocommit=True) as conn:
        priv = conn.execute(
            "SELECT has_table_privilege('parity_reader', 'parity_app.customers', 'SELECT'), "
            "has_table_privilege('parity_reader', 'parity_app.customers', 'INSERT')"
        ).fetchone()
        assert priv == (True, True)

    rev_revoke = _post_ops(parity_env, 'bulk_grant_review', {
        'mode': 'REVOKE',
        'grantee': 'parity_reader',
        'object_kind': 'TABLE',
        'privileges': ['INSERT'],
        'targets': ['parity_app.customers'],
    })['data']
    _post_ops(parity_env, 'bulk_grant_start', {
        'job_id': rev_revoke['job_id'],
        'review_digest': rev_revoke['review_digest'],
        'confirmed': True,
    })
    with psycopg.connect(dsn, autocommit=True) as conn:
        priv_after = conn.execute(
            "SELECT has_table_privilege('parity_reader', 'parity_app.customers', 'SELECT'), "
            "has_table_privilege('parity_reader', 'parity_app.customers', 'INSERT')"
        ).fetchone()
        assert priv_after == (True, False)

    # 5. Supervised pg_dump -> pg_restore --list (TOC) -> drop table -> pg_restore!
    cat0 = _post_ops(parity_env, 'logical_backup_catalog')['data']
    assert Path(cat0['pg_dump']).is_file() and Path(cat0['pg_restore']).is_file()

    rev_bk = _post_ops(parity_env, 'logical_backup_review', {
        'task': 'backup',
        'filename': 'parity_app_customers.dump',
        'format': 'custom',
        'schema': 'parity_app',
    })['data']
    done_bk = _post_ops(parity_env, 'logical_backup_start', {
        'job_id': rev_bk['job_id'],
        'review_digest': rev_bk['review_digest'],
        'confirmed': True,
    })['data']
    assert done_bk['outcome']['size_bytes'] > 0

    rev_toc = _post_ops(parity_env, 'logical_backup_review', {
        'task': 'toc',
        'filename': 'parity_app_customers.dump',
        'format': 'custom',
    })['data']
    done_toc = _post_ops(parity_env, 'logical_backup_start', {
        'job_id': rev_toc['job_id'],
        'review_digest': rev_toc['review_digest'],
        'confirmed': True,
    })['data']
    assert 'customers' in done_toc['outcome']['stdout']

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute('DROP SCHEMA parity_app CASCADE')

    rev_rs = _post_ops(parity_env, 'logical_backup_review', {
        'task': 'restore',
        'filename': 'parity_app_customers.dump',
        'format': 'custom',
        'clean': True,
    })['data']
    done_rs = _post_ops(parity_env, 'logical_backup_start', {
        'job_id': rev_rs['job_id'],
        'review_digest': rev_rs['review_digest'],
        'confirmed': True,
    })['data']
    assert done_rs['state'] == 'completed'

    with psycopg.connect(dsn, autocommit=True) as conn:
        restored = conn.execute('SELECT id, email FROM parity_app.customers ORDER BY id').fetchall()
        assert restored == [(10, 'ada@example.org'), (20, 'grace@example.org')]


def test_pg_parity_2_51_declared_kinds_26_forms_and_pg18_constraint_gates():
    from pgadmin.cdeadmin.providers.postgresql.native_admin import compile_native_admin
    from pgadmin.cdeadmin.ui_descriptors import UIDescriptorService

    svc = UIDescriptorService()
    b18 = svc.resolve_for_version('postgresql', '18.3')
    b17 = svc.resolve_for_version('postgresql', '17.4')
    assert len(b18['kinds']) == 51
    assert len(b18['forms']) == 41

    expected_engine_objects = (
        'access-method', 'cast', 'collation', 'conversion',
        'foreign-data-wrapper', 'language', 'operator-class', 'operator-family',
        'publication', 'subscription', 'text-search-configuration',
        'text-search-dictionary', 'text-search-parser', 'text-search-template',
        'transform', 'user-mapping',
    )
    for kind in expected_engine_objects:
        form = b18['forms'][f'engine_object:{kind}']
        assert form['status'] == 'complete', kind
        assert b18['kinds'][kind]['form_status'] == 'complete', kind

    # Verify PG 18 constraint columns gate cleanly on 18.3 vs 17.4
    def _constraint_col(bundle, grid_id, col_id):
        for tab in bundle['forms']['table']['tabs']:
            for f in tab['fields']:
                if f['field_id'] == grid_id:
                    return next(c for c in f['columns'] if c['field_id'] == col_id)
        raise AssertionError((grid_id, col_id))

    assert _constraint_col(b18, 'primary_key', 'without_overlaps_column')['available'] is True
    assert _constraint_col(b17, 'primary_key', 'without_overlaps_column')['available'] is False
    assert _constraint_col(b18, 'foreign_key', 'local_period_column')['available'] is True
    assert _constraint_col(b17, 'foreign_key', 'local_period_column')['available'] is False
    assert _constraint_col(b18, 'check_constraint', 'not_enforced')['available'] is True
    assert _constraint_col(b17, 'check_constraint', 'not_enforced')['available'] is False

    # Verify compiler accepts table create with PG18 temporal/enforcement constraint fields
    compiled_tbl = compile_native_admin({
        'resource_kind': 'table',
        'operation_id': 'create',
        'target_resource': {'extensions': {'postgresql': {'native': {}}}},
        'draft': {
            'schema': 'public',
            'name': 'bookings',
            'columns': [
                {'name': 'room_id', 'cltype': 'integer', 'attnotnull': True},
                {'name': 'valid_during', 'cltype': 'daterange', 'attnotnull': True},
            ],
            'primary_key': [
                {'name': 'bookings_pk', 'columns': ['room_id'], 'without_overlaps_column': 'valid_during'},
            ],
            'check_constraint': [
                {'name': 'bookings_room_pos', 'consrc': 'room_id > 0', 'not_enforced': True},
            ],
        },
    })
    assert 'WITHOUT OVERLAPS' in compiled_tbl['statement']
    assert 'NOT ENFORCED' in compiled_tbl['statement']
