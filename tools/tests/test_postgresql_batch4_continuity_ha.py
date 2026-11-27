"""Live native & authenticated HTTP qualification for PostgreSQL Batch 4:
- PG-AUDIT-RESTORE-01: Production destination restore, independent R/W service acceptance, cutover & rollback
- PG-AUDIT-ARCHIVE-01: Dependency-aware WAL archive holds, retention pruning, and interrupted stream restart review
- PG-AUDIT-HA-01: Streaming standby bootstrap, topology/lag inspection, coordinated switchover, and host pg_ctl
- PG-AUDIT-SNAPSHOT-01: Output-plugin admission, cross-registration & ordinary-SQL-principal snapshot consumers, and coordinated destination table load/cutover
"""
from __future__ import annotations

import builtins
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

import psycopg
from psycopg import sql
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]

PG18_BIN = Path('/usr/lib/postgresql/18/bin')
USER = __import__('getpass').getuser()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _init_and_start_pg18(base_dir: Path, name: str) -> tuple[Path, int, Path]:
    datadir = base_dir / name
    sock_dir = Path(f'/tmp/sr-b4-{uuid.uuid4().hex[:8]}')
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
        + f"\nlisten_addresses = '127.0.0.1'\n"
        + f'port = {port}\n'
        + f"unix_socket_directories = '{sock_dir}'\n"
        + "wal_level = 'logical'\n"
        + 'max_wal_senders = 10\n'
        + 'max_replication_slots = 10\n'
        + "summarize_wal = 'on'\n"
        + "wal_keep_size = '64MB'\n",
        encoding='utf8',
    )
    hba = datadir / 'pg_hba.conf'
    hba.write_text(
        'local all all trust\n'
        'host all all 127.0.0.1/32 trust\n'
        'local replication all trust\n'
        'host replication all 127.0.0.1/32 trust\n',
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
        import shutil
        shutil.rmtree(sock_dir, ignore_errors=True)


@pytest.fixture(scope='module')
def flask_env(tmp_path_factory):
    if not (PG18_BIN / 'initdb').is_file():
        pytest.skip('PostgreSQL 18 binaries unavailable')
    base = tmp_path_factory.mktemp('pg_batch4')
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

    from pgadmin import create_app
    from pgadmin.model import ServerGroup, User

    app = create_app('ScratchRobin-pg-batch4-http')
    app.PGADMIN_RUNTIME = False
    app.PGADMIN_INT_KEY = ''
    # The tests authenticate through the session, not the encrypted user-configuration login.
    app.config['USER_CONFIG_LOGIN_REQUIRED'] = False
    app.run_before_app_start()

    grant_root = base / 'granted_roots'
    grant_root.mkdir(mode=0o700)
    app.config['CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH'] = str(PG18_BIN)
    app.config['CDEADMIN_POSTGRESQL_CONTINUITY_ROOT'] = str(base / 'continuity_jobs')
    app.config['CDEADMIN_POSTGRESQL_WAL_ARCHIVE_ROOT'] = str(base / 'wal_archives')
    app.config['CDEADMIN_POSTGRESQL_RESTORE_GRANTS'] = [str(grant_root)]
    app.config['CDEADMIN_POSTGRESQL_HA_GRANTS'] = [str(grant_root)]

    with app.test_request_context('/'):
        user = User.query.first()
        group = ServerGroup.query.filter_by(user_id=user.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility['postgresql'].set(True, user_id=user.id)
        uid = user.id
        gid = group.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True

    return {
        'app': app,
        'client': client,
        'uid': uid,
        'gid': gid,
        'base': base,
        'grant_root': grant_root,
    }


def _register_server(flask_env: dict, name: str, port: int, username: str = USER, db_name: str = 'postgres') -> tuple[int, str]:
    from flask import url_for
    from pgadmin.model import Server, db

    app = flask_env['app']
    with app.test_request_context('/'):
        srv = Server(
            user_id=flask_env['uid'],
            servergroup_id=flask_env['gid'],
            name=name,
            host='127.0.0.1',
            port=port,
            username=username,
            maintenance_db=db_name,
            connection_params={'sslmode': 'disable'},
            save_password=0,
        )
        db.session.add(srv)
        db.session.commit()
        sid = srv.id
        connect_url = url_for('NODE-server.connect_id', gid=flask_env['gid'], sid=sid)
        ws_url = url_for('NODE-server.cde_workspace_id', gid=flask_env['gid'], sid=sid)
    c_resp = flask_env['client'].post(connect_url, json={'password': ''}).get_json()
    assert c_resp.get('success'), c_resp
    return sid, ws_url


def _wait_continuity_job(client, ws_url: str, job_id: str, terminal_states: set[str], timeout: float = 45.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.post(
            ws_url,
            json={'action': 'postgresql_continuity_status', 'request': {'job_id': job_id}},
        ).get_json()
        data = resp['data']
        if data['state'] in terminal_states:
            return data
        time.sleep(0.1)
    raise AssertionError(f'Continuity job {job_id} did not reach {terminal_states}')


def test_restore_and_archive_orchestration_live_http(flask_env):
    """Qualifies PG-AUDIT-RESTORE-01 and PG-AUDIT-ARCHIVE-01 end-to-end over authenticated HTTP."""
    datadir, port, sock_dir = _init_and_start_pg18(flask_env['base'], 'restore_src')
    restored_dir = flask_env['grant_root'] / 'restored_prod_cluster'
    restored_port = _free_port()
    restored_sock = None
    try:
        dsn = f'host=127.0.0.1 port={port} user={USER} dbname=postgres'
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute('CREATE TABLE public.accounts (id int primary key, balance int not null)')
            conn.execute('INSERT INTO public.accounts VALUES (1, 100), (2, 250)')

        _sid, ws_url = _register_server(flask_env, 'Restore & Archive Primary', port)
        client = flask_env['client']

        # 1. Start WAL archive capture (pg_receivewal), wait until active, switch 3 WAL segments, cancel & reconcile!
        wal_rev = client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_review',
                'request': {
                    'operation': 'wal_capture',
                    'options': {'archive': 'prod_wal_arch', 'synchronous': False, 'sync': True, 'status_interval_seconds': 1},
                },
            },
        ).get_json()['data']
        client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_start',
                'request': {
                    'job_id': wal_rev['job_id'],
                    'review_digest': wal_rev['review_digest'],
                    'confirmed': True,
                },
            },
        )
        # Wait for pg_receivewal process to attach to replication before switching WAL!
        act_deadline = time.monotonic() + 15.0
        while time.monotonic() < act_deadline:
            with psycopg.connect(dsn, autocommit=True) as conn:
                attached = conn.execute(
                    "SELECT count(*) FROM pg_catalog.pg_stat_replication WHERE state = 'streaming'"
                ).fetchone()[0]
                if int(attached) >= 1:
                    break
            time.sleep(0.15)
        with psycopg.connect(dsn, autocommit=True) as conn:
            for i in range(3):
                conn.execute('INSERT INTO public.accounts VALUES (%s, %s)', (10 + i, 50 * i))
                conn.execute('SELECT pg_catalog.pg_switch_wal()')
        # Wait until at least 2 completed segments are published
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            st = client.post(
                ws_url, json={'action': 'postgresql_continuity_status', 'request': {'job_id': wal_rev['job_id']}}
            ).get_json()['data']
            if (st.get('archive_observation') or {}).get('completed_files', 0) >= 2:
                break
            time.sleep(0.2)

        client.post(
            ws_url, json={'action': 'postgresql_continuity_cancel', 'request': {'job_id': wal_rev['job_id']}}
        )
        _wait_continuity_job(client, ws_url, wal_rev['job_id'], {'cancelled', 'captured', 'failed'})
        client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_reconcile_writer',
                'request': {'job_id': wal_rev['job_id'], 'confirmed': True},
            },
        )

        # 2. Test interrupted-stream restart review (PG-AUDIT-ARCHIVE-01)
        restart_rev = client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_stream_restart_review',
                'request': {'prior_job_id': wal_rev['job_id']},
            },
        ).get_json()['data']
        assert restart_rev['state'] == 'reviewed'
        assert restart_rev['reconciled_prior_job']['prior_job_id'] == wal_rev['job_id']
        assert restart_rev['reconciled_prior_job']['resume_after_segment'] is not None
        assert restart_rev['reconciled_prior_job']['automatic_dispatch'] is False

        # 3. Take a full physical backup & verify it BEFORE testing archive retention floor!
        bkp_rev = client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_review',
                'request': {'operation': 'full_backup', 'options': {'format': 'plain', 'wal_method': 'stream'}},
            },
        ).get_json()['data']
        client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_start',
                'request': {'job_id': bkp_rev['job_id'], 'review_digest': bkp_rev['review_digest'], 'confirmed': True},
            },
        )
        _wait_continuity_job(client, ws_url, bkp_rev['job_id'], {'verified'})

        # 4. Evaluate archive retention & verify hold protection + pruning of strictly older segments!
        eval_initial = client.post(
            ws_url,
            json={'action': 'postgresql_continuity_archive_retention_evaluate', 'request': {'archive': 'prod_wal_arch'}},
        ).get_json()['data']
        assert eval_initial['prune_allowed'] is True
        all_segs = sorted(eval_initial['removable_segments'] + eval_initial['retained_segments'])
        assert len(all_segs) >= 2

        # Register hold on earliest segment -> blocks pruning past earliest segment!
        hold_resp = client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_archive_hold_register',
                'request': {
                    'archive': 'prod_wal_arch',
                    'hold_id': 'dr_consumer_1',
                    'min_retain_segment': all_segs[0],
                    'reason': 'Standby DR consumer lag hold',
                },
            },
        ).get_json()['data']
        assert hold_resp['registered'] is True

        blocked_eval = client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_archive_retention_evaluate',
                'request': {'archive': 'prod_wal_arch', 'retain_before_segment': all_segs[-1]},
            },
        ).get_json()['data']
        assert blocked_eval['prune_allowed'] is False
        assert any('protected WAL segment' in b for b in blocked_eval['blockers'])

        # Release hold, then prune segments older than effective_protected_floor!
        client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_archive_hold_release',
                'request': {'archive': 'prod_wal_arch', 'hold_id': 'dr_consumer_1', 'confirmed': True},
            },
        )
        ret_rev = client.post(
            ws_url,
            json={'action': 'postgresql_continuity_archive_retention_review', 'request': {'archive': 'prod_wal_arch'}},
        ).get_json()['data']
        ret_done = client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_archive_retention_start',
                'request': {
                    'review_id': ret_rev['review_id'],
                    'review_digest': ret_rev['review_digest'],
                    'confirmed': True,
                },
            },
        ).get_json()['data']
        assert ret_done['state'] == 'completed'
        assert ret_done['removed_count'] >= 1

        # Replay of retention review must fail closed!
        replay_ret = client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_archive_retention_start',
                'request': {
                    'review_id': ret_rev['review_id'],
                    'review_digest': ret_rev['review_digest'],
                    'confirmed': True,
                },
            },
        )
        assert replay_ret.status_code == 400

        # 5. Production destination restore + live service startup + independent R/W verification (PG-AUDIT-RESTORE-01)
        rest_rev = client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_restore_review',
                'request': {
                    'base_job_id': bkp_rev['job_id'],
                    'destination_mode': 'local',
                    'destination_datadir': str(restored_dir),
                    'start_service': True,
                    'listen_port': restored_port,
                    'verify_read_write': True,
                    'database': 'postgres',
                },
            },
        ).get_json()['data']
        assert rest_rev['state'] == 'reviewed'

        rest_done = client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_restore_start',
                'request': {
                    'restore_id': rest_rev['restore_id'],
                    'review_digest': rest_rev['review_digest'],
                    'confirmed': True,
                },
            },
        ).get_json()['data']
        restored_sock = Path(rest_done['service_receipt']['socket_dir']) if rest_done.get('service_receipt', {}).get('socket_dir') else None
        assert rest_done['state'] == 'completed'
        assert rest_done['restored_service_acceptance']['verified'] is True
        assert rest_done['restored_service_acceptance']['read_write_transaction_committed'] is True

        # Verify restored data independently!
        restored_dsn = f'host=127.0.0.1 port={restored_port} user={USER} dbname=postgres'
        with psycopg.connect(restored_dsn, autocommit=True) as rconn:
            cnt = rconn.execute('SELECT count(*) FROM public.accounts').fetchone()[0]
            assert int(cnt) == 5

        # 6. Coordinated replacement cutover + rollback!
        cut_rev = client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_cutover_review',
                'request': {'restore_id': rest_rev['restore_id'], 'terminate_source_writers': False},
            },
        ).get_json()['data']
        cut_done = client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_cutover_start',
                'request': {
                    'cutover_id': cut_rev['cutover_id'],
                    'review_digest': cut_rev['review_digest'],
                    'confirmed': True,
                },
            },
        ).get_json()['data']
        assert cut_done['state'] == 'completed'
        assert cut_done['source_fenced_read_only'] is True
        with psycopg.connect(dsn, autocommit=True) as conn:
            assert conn.execute('SHOW default_transaction_read_only').fetchone()[0] == 'on'

        rb_done = client.post(
            ws_url,
            json={
                'action': 'postgresql_continuity_cutover_rollback',
                'request': {'cutover_id': cut_rev['cutover_id'], 'confirmed': True},
            },
        ).get_json()['data']
        assert rb_done['state'] == 'rolled_back'
        assert rb_done['source_restored_read_only'] == 'off'
    finally:
        _stop_pg_quiet(restored_dir, restored_sock)
        _stop_pg_quiet(datadir, sock_dir)


def test_ha_standby_bootstrap_switchover_and_host_pg_ctl_live_http(flask_env):
    """Qualifies PG-AUDIT-HA-01 live over authenticated HTTP."""
    prim_dir, prim_port, prim_sock = _init_and_start_pg18(flask_env['base'], 'ha_primary')
    sb_dir = flask_env['grant_root'] / 'ha_standby'
    sb_port = _free_port()
    sb_sock = None
    try:
        prim_dsn = f'host=127.0.0.1 port={prim_port} user={USER} dbname=postgres'
        with psycopg.connect(prim_dsn, autocommit=True) as conn:
            conn.execute('CREATE TABLE public.ha_ledger (id int primary key, note text)')
            conn.execute("INSERT INTO public.ha_ledger VALUES (1, 'before-bootstrap')")

        _sid, ws_url = _register_server(flask_env, 'HA Primary', prim_port)
        client = flask_env['client']

        # 1. Inspect primary topology
        topo0 = client.post(
            ws_url, json={'action': 'postgresql_ha_topology', 'request': {}}
        ).get_json()['data']
        assert topo0['role'] == 'primary'
        assert topo0['in_recovery'] is False

        # 2. Bootstrap streaming standby with physical replication slot & start it!
        bs_rev = client.post(
            ws_url,
            json={
                'action': 'postgresql_ha_review',
                'request': {
                    'operation': 'standby_bootstrap',
                    'options': {
                        'standby_datadir': str(sb_dir),
                        'slot_name': 'sr_ha_standby_slot',
                        'create_slot': True,
                        'standby_port': sb_port,
                        'start_standby': True,
                        'application_name': 'sr_ha_standby_1',
                    },
                },
            },
        ).get_json()['data']
        bs_done = client.post(
            ws_url,
            json={
                'action': 'postgresql_ha_start',
                'request': {'job_id': bs_rev['job_id'], 'review_digest': bs_rev['review_digest'], 'confirmed': True},
            },
        ).get_json()['data']
        sb_sock = Path(bs_done['result']['service']['socket_dir']) if bs_done['result']['service'].get('socket_dir') else None
        assert bs_done['state'] == 'completed'
        assert bs_done['result']['standby_topology']['role'] == 'standby'
        assert bs_done['result']['standby_topology']['wal_receiver']['status'] == 'streaming'

        # Write another row on primary before switchover!
        with psycopg.connect(prim_dsn, autocommit=True) as conn:
            conn.execute("INSERT INTO public.ha_ledger VALUES (2, 'streamed-to-standby')")

        topo1 = client.post(ws_url, json={'action': 'postgresql_ha_topology', 'request': {}}).get_json()['data']
        assert any(s['application_name'] == 'sr_ha_standby_1' for s in topo1['standbys'])

        # 3. Coordinated switchover (fences old primary R/O, catches up standby LSN, promotes standby, verifies R/W!)
        sb_dsn = f'host=127.0.0.1 port={sb_port} user={USER} dbname=postgres'
        sw_rev = client.post(
            ws_url,
            json={
                'action': 'postgresql_ha_review',
                'request': {'operation': 'switchover', 'options': {'standby_dsn': sb_dsn, 'wait_seconds': 20}},
            },
        ).get_json()['data']
        sw_done = client.post(
            ws_url,
            json={
                'action': 'postgresql_ha_start',
                'request': {'job_id': sw_rev['job_id'], 'review_digest': sw_rev['review_digest'], 'confirmed': True},
            },
        ).get_json()['data']
        assert sw_done['state'] == 'completed'
        assert sw_done['result']['switchover_completed'] is True
        assert sw_done['result']['new_primary_read_write_verified'] is True

        # Verify promoted standby has both rows and accepts writes!
        with psycopg.connect(sb_dsn, autocommit=True) as sconn:
            assert sconn.execute('SELECT pg_catalog.pg_is_in_recovery()').fetchone()[0] is False
            rows = sconn.execute('SELECT id, note FROM public.ha_ledger ORDER BY id').fetchall()
            assert rows == [(1, 'before-bootstrap'), (2, 'streamed-to-standby')]
            sconn.execute("INSERT INTO public.ha_ledger VALUES (3, 'written-on-new-primary')")

        # 4. Authorized host pg_ctl status & stop on granted standby directory!
        ctl_rev = client.post(
            ws_url,
            json={
                'action': 'postgresql_ha_review',
                'request': {'operation': 'host_pg_ctl', 'options': {'datadir': str(sb_dir), 'ctl_action': 'stop', 'stop_mode': 'fast'}},
            },
        ).get_json()['data']
        ctl_done = client.post(
            ws_url,
            json={
                'action': 'postgresql_ha_start',
                'request': {'job_id': ctl_rev['job_id'], 'review_digest': ctl_rev['review_digest'], 'confirmed': True},
            },
        ).get_json()['data']
        assert ctl_done['state'] == 'completed'
        assert ctl_done['result']['return_code'] == 0
    finally:
        _stop_pg_quiet(sb_dir, sb_sock)
        _stop_pg_quiet(prim_dir, prim_sock)


def test_snapshot_cross_registration_ordinary_sql_consumer_and_load_cutover_live_http(flask_env):
    """Qualifies PG-AUDIT-SNAPSHOT-01 live over authenticated HTTP."""
    src_dir, src_port, src_sock = _init_and_start_pg18(flask_env['base'], 'snap_src')
    dst_dir, dst_port, dst_sock = _init_and_start_pg18(flask_env['base'], 'snap_dst')
    exporter_conn = None
    try:
        src_dsn = f'host=127.0.0.1 port={src_port} user={USER} dbname=postgres'
        dst_dsn = f'host=127.0.0.1 port={dst_port} user={USER} dbname=postgres'

        with psycopg.connect(src_dsn, autocommit=True) as conn:
            conn.execute('CREATE ROLE sr_ordinary_reader LOGIN NOREPLICATION')
            conn.execute('CREATE TABLE public.snap_items (id int primary key, label text not null)')
            conn.execute("INSERT INTO public.snap_items VALUES (1, 'alpha'), (2, 'beta')")
            conn.execute('GRANT SELECT ON public.snap_items TO sr_ordinary_reader')

        with psycopg.connect(dst_dsn, autocommit=True) as dconn:
            dconn.execute('CREATE TABLE public.snap_items (id int primary key, label text not null)')
            dconn.execute("INSERT INTO public.snap_items VALUES (99, 'stale-destination-row')")

        # Register Exporter Server A (superuser), Cross-Registration Consumer Server B (ordinary SQL user!), and Destination Server C
        sid_a, ws_a = _register_server(flask_env, 'Snapshot Exporter Reg A', src_port, username=USER)
        _sid_b, ws_b = _register_server(flask_env, 'Snapshot Consumer Reg B (Ordinary SQL)', src_port, username='sr_ordinary_reader')
        sid_c, _ws_c = _register_server(flask_env, 'Snapshot Destination Reg C', dst_port, username=USER)
        client = flask_env['client']

        # 1. Output-plugin discovery & admission (pgoutput + test_decoding installed, fake plugin refused!)
        plugins = client.post(
            ws_a,
            json={
                'action': 'postgresql_snapshot_output_plugins',
                'request': {'plugins': ['pgoutput', 'test_decoding', 'nonexistent_sr_plugin']},
            },
        ).get_json()['data']
        by_name = {p['plugin']: p for p in plugins['plugins']}
        assert by_name['pgoutput']['installed'] is True
        assert by_name['test_decoding']['installed'] is True
        assert by_name['nonexistent_sr_plugin']['installed'] is False, by_name['nonexistent_sr_plugin']
        assert by_name['nonexistent_sr_plugin']['sqlstate'] in {'58P01', '42704', '22023', '42501'}

        # 2. Export a live snapshot on Exporter A and hold the exporter transaction open
        exporter_conn = psycopg.connect(src_dsn, autocommit=True)
        exporter_conn.execute('BEGIN ISOLATION LEVEL REPEATABLE READ')
        snap_name = exporter_conn.execute('SELECT pg_catalog.pg_export_snapshot()').fetchone()[0]
        exp_pid = exporter_conn.info.backend_pid

        # 3. Open cross-registration ordinary-SQL-principal consumer on Registration B!
        crev = client.post(
            ws_b,
            json={
                'action': 'postgresql_snapshot_consumer_review',
                'request': {
                    'exporter_server_id': sid_a,
                    'snapshot_name': snap_name,
                    'exporter_backend_pid': exp_pid,
                    'database': 'postgres',
                    'max_lifetime_seconds': 60,
                },
            },
        ).get_json()['data']
        assert crev['cross_registration'] is True
        assert crev['consumer_principal']['authenticated_principal'] == 'sr_ordinary_reader'
        assert crev['consumer_principal']['rolreplication'] is False

        copen = client.post(
            ws_b,
            json={
                'action': 'postgresql_snapshot_consumer_start',
                'request': {
                    'consumer_id': crev['consumer_id'],
                    'review_digest': crev['review_digest'],
                    'confirmed': True,
                },
            },
        ).get_json()['data']
        assert copen['state'] == 'open'
        assert copen['snapshot_exporter_preverified'] is True
        assert copen['snapshot_exporter_postverified'] is True
        assert copen['consumer_backend_pid'] != exp_pid

        # 4. Mutate source table AND close exporter session completely — consumer MUST retain exact historical snapshot!
        exporter_conn.close()
        exporter_conn = None
        with psycopg.connect(src_dsn, autocommit=True) as mconn:
            mconn.execute("INSERT INTO public.snap_items VALUES (3, 'post-snapshot-mutation')")
            mconn.execute("DELETE FROM public.snap_items WHERE id = 1")

        copied = client.post(
            ws_b,
            json={
                'action': 'postgresql_snapshot_consumer_copy',
                'request': {'consumer_id': crev['consumer_id'], 'schema': 'public', 'table': 'snap_items', 'format': 'json'},
            },
        ).get_json()['data']
        assert copied['row_count'] == 2
        assert copied['rows'] == [{'id': 1, 'label': 'alpha'}, {'id': 2, 'label': 'beta'}]

        # 5. Coordinated destination table load + atomic swap cutover onto Destination Registration C!
        lrev = client.post(
            ws_b,
            json={
                'action': 'postgresql_snapshot_load_review',
                'request': {
                    'consumer_id': crev['consumer_id'],
                    'destination_server_id': sid_c,
                    'source_schema': 'public',
                    'source_table': 'snap_items',
                    'destination_database': 'postgres',
                    'destination_schema': 'public',
                    'destination_table': 'snap_items',
                    'cutover_mode': 'atomic_swap',
                },
            },
        ).get_json()['data']
        ldone = client.post(
            ws_b,
            json={
                'action': 'postgresql_snapshot_load_start',
                'request': {'load_id': lrev['load_id'], 'review_digest': lrev['review_digest'], 'confirmed': True},
            },
        ).get_json()['data']
        assert ldone['state'] == 'completed'
        assert ldone['rows_copied'] == 2
        assert ldone['cutover_applied'] is True

        with psycopg.connect(dst_dsn, autocommit=True) as dconn:
            dst_rows = dconn.execute('SELECT id, label FROM public.snap_items ORDER BY id').fetchall()
            assert dst_rows == [(1, 'alpha'), (2, 'beta')]

        # Release SQL snapshot consumer cleanly
        rel = client.post(
            ws_b,
            json={
                'action': 'postgresql_snapshot_consumer_release',
                'request': {'consumer_id': crev['consumer_id'], 'confirmed': True},
            },
        ).get_json()['data']
        assert rel['state'] == 'released'
    finally:
        if exporter_conn is not None:
            exporter_conn.close()
        _stop_pg_quiet(src_dir, src_sock)
        _stop_pg_quiet(dst_dir, dst_sock)
