"""Live native & authenticated HTTP qualification for all 8 PostgreSQL 18 Batch 2 utilities:
- PG-AUDIT-UTILITY-INITDB (host_initdb)
- PG-AUDIT-UTILITY-PG_AMCHECK (host_pg_amcheck)
- PG-AUDIT-UTILITY-PG_CREATESUBSCRIBER (host_pg_createsubscriber)
- PG-AUDIT-UTILITY-PG_RESETWAL (host_pg_resetwal)
- PG-AUDIT-UTILITY-PG_REWIND (host_pg_rewind)
- PG-AUDIT-UTILITY-PGARCHIVECLEANUP (host_pg_archivecleanup)
- PG-AUDIT-UTILITY-PGBENCH (host_pgbench)
- PG-AUDIT-UTILITY-PGUPGRADE (host_pg_upgrade — live cross-major PG 17 -> PG 18!)
"""
from __future__ import annotations

import builtins
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError  # noqa: E402
from pgadmin.cdeadmin.providers.postgresql.host_tools import (  # noqa: E402
    OPERATIONS,
    HostTools,
    grants,
    options,
)
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import digest  # noqa: E402
from pgadmin.cdeadmin.workspace.postgresql_host_tool_jobs import (  # noqa: E402
    HostToolTransport,
    PostgreSQLHostToolJobs,
)

PG18_BIN = Path('/usr/lib/postgresql/18/bin')
PG17_BIN = Path('/usr/lib/postgresql/17/bin')
USER = __import__('getpass').getuser()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _start_pg(bin_dir: Path, datadir: Path, port: int, extra_args: str = '') -> None:
    opts = f"-h 127.0.0.1 -p {port} -c unix_socket_directories='' {extra_args}".strip()
    subprocess.run(
        [str(bin_dir / 'pg_ctl'), '-D', str(datadir), '-l', str(datadir.parent / f'pg_{port}.log'), '-o', opts, '-w', 'start'],
        check=True,
        capture_output=True,
        timeout=30,
    )


def _stop_pg(bin_dir: Path, datadir: Path, mode: str = 'fast') -> None:
    if (datadir / 'postmaster.pid').exists():
        subprocess.run(
            [str(bin_dir / 'pg_ctl'), '-D', str(datadir), '-m', mode, '-w', 'stop'],
            check=True,
            capture_output=True,
            timeout=25,
        )


@pytest.fixture
def host_env(tmp_path):
    if not (PG18_BIN / 'initdb').is_file():
        pytest.skip('PostgreSQL 18 host binaries unavailable')
    endpoint = str(uuid.uuid4())
    manifest = tmp_path / 'grants.json'
    init_root = tmp_path / 'init_root'
    init_root.mkdir()
    arch_dir = tmp_path / 'wal_archive'
    arch_dir.mkdir()
    manifest.write_text(
        json.dumps({
            'format': 'scratchrobin.postgresql.host-tools@1',
            'grants': [{
                'endpoint_id': endpoint,
                'clusters': [],
                'summary_files': [],
                'benchmark_roots': [],
                'init_roots': [{'id': 'init_main', 'path': str(init_root)}],
                'archive_dirs': [{'id': 'arch_main', 'path': str(arch_dir)}],
                'upgrade_pairs': [],
            }],
        }),
        encoding='utf-8',
    )
    tools = HostTools({name: str(PG18_BIN / name) for name in OPERATIONS.values()})
    jobs = PostgreSQLHostToolJobs(tmp_path / 'receipts.json', tmp_path / 'jobs')
    ws = jobs.prepare_scope(1, endpoint)
    env = SimpleNamespace(
        tmp=tmp_path,
        endpoint=endpoint,
        manifest=manifest,
        init_root=init_root,
        arch_dir=arch_dir,
        tools=tools,
        jobs=jobs,
        workspace=ws,
    )
    try:
        yield env
    finally:
        jobs.close(10)


def _run_job(env, operation: str, **draft):
    selected = options(operation, draft)

    def refresh():
        grant, sha = grants(str(env.manifest), env.endpoint)
        program = env.tools.identify(OPERATIONS[operation], env.workspace)
        source = env.tools.observe(operation, selected, grant, env.workspace)
        return source, program, digest({'manifest_sha256': sha})

    source, program, cfg = refresh()
    rec = env.jobs.review(1, env.endpoint, {'operation': operation, 'draft': selected}, {'identity': source, 'state': {}}, cfg, program)
    req = {'job_id': rec['job_id'], 'review_digest': rec['review_digest'], 'confirmed': True}
    env.jobs.start(req, 1, env.endpoint, {'source': source, 'program': program, 'configuration': cfg}, HostToolTransport(env.jobs, env.tools, refresh))
    deadline = time.monotonic() + 90
    while True:
        cur = env.jobs.get(rec['job_id'], 1, env.endpoint)
        with env.jobs._maps_lock:
            worker = env.jobs.workers.get(rec['job_id'])
        if not worker and cur['state'] not in {'dispatching', 'active', 'cancel_requested'}:
            return cur
        assert time.monotonic() < deadline, cur
        time.sleep(0.03)


def _update_manifest(env, mutator):
    doc = json.loads(env.manifest.read_text(encoding='utf-8'))
    mutator(doc['grants'][0])
    env.manifest.write_text(json.dumps(doc), encoding='utf-8')


def test_initdb_resetwal_archivecleanup_amcheck_and_pgbench_live(host_env):
    # 1. host_initdb: initialize new cluster + refuse re-initializing non-empty target!
    res_init = _run_job(
        host_env,
        'host_initdb',
        init_root_id='init_main',
        subdir='cluster_a',
        encoding='UTF8',
        locale_provider='libc',
        locale='C',
        data_checksums=True,
        wal_segsize_mb=16,
        username=USER,
        auth_host='trust',
        auth_local='trust',
        confirmation='init_main/cluster_a',
    )
    assert res_init['state'] == 'completed', res_init
    cdir = host_env.init_root / 'cluster_a'
    assert res_init['result']['initialized_control_fields']['Data page checksum version'] == '1'
    with pytest.raises(ContinuityError, match='non-empty'):
        _run_job(
            host_env,
            'host_initdb',
            init_root_id='init_main',
            subdir='cluster_a',
            username=USER,
            auth_host='trust',
            auth_local='trust',
            confirmation='init_main/cluster_a',
        )

    _update_manifest(host_env, lambda g: g['clusters'].append({'id': 'cluster_a', 'path': str(cdir)}))

    # 2. host_pg_resetwal: dry-run preview & live WAL reset on stopped cluster (and active-cluster refusal!)
    res_rw_dry = _run_job(
        host_env,
        'host_pg_resetwal',
        cluster_id='cluster_a',
        dry_run=True,
        offline_quiescence_confirmed=True,
        confirmation='cluster_a',
    )
    assert res_rw_dry['state'] == 'completed' and 'Current pg_control values' in res_rw_dry['result']['native']['stdout']

    res_rw_live = _run_job(
        host_env,
        'host_pg_resetwal',
        cluster_id='cluster_a',
        dry_run=False,
        next_oid='30000',
        offline_quiescence_confirmed=True,
        destructive_reset_confirmed=True,
        confirmation='cluster_a',
    )
    assert res_rw_live['state'] == 'completed', res_rw_live
    assert int(res_rw_live['result']['control_fields_after']['Latest checkpoint\'s NextOID']) >= 30000

    # Start cluster_a to test active-cluster refusal on pg_resetwal, plus live pg_amcheck & pgbench!
    port = _free_port()
    _start_pg(PG18_BIN, cdir, port)
    try:
        with pytest.raises(ContinuityError, match='postmaster.pid'):
            _run_job(
                host_env,
                'host_pg_resetwal',
                cluster_id='cluster_a',
                dry_run=True,
                offline_quiescence_confirmed=True,
                confirmation='cluster_a',
            )

        with psycopg.connect(host='127.0.0.1', port=port, user=USER, dbname='postgres', autocommit=True) as conn:
            conn.execute('CREATE EXTENSION amcheck')
            conn.execute('CREATE TABLE public.am_target (id int primary key, body text)')
            conn.execute("INSERT INTO public.am_target SELECT g, md5(g::text) FROM generate_series(1, 200) g")
            conn.execute('CREATE DATABASE cdeadmin_pgbench_demo')

        # 3. host_pg_amcheck: clean heapallindexed + rootdescend verification
        res_am = _run_job(
            host_env,
            'host_pg_amcheck',
            host='127.0.0.1',
            port=port,
            username=USER,
            database='postgres',
            schema_pattern='public',
            table_pattern='am_target',
            heapallindexed=True,
            rootdescend=True,
            confirmation='postgres',
        )
        assert res_am['state'] == 'completed', res_am
        assert res_am['result']['corruption_detected'] is False

        # 4. host_pgbench: refuse non-cdeadmin_pgbench_* database, then INIT + RUN!
        with pytest.raises(ContinuityError, match='cdeadmin_pgbench_'):
            options('host_pgbench', {'mode': 'INIT', 'database': 'postgres', 'confirmation': 'postgres'})

        res_bi = _run_job(
            host_env,
            'host_pgbench',
            mode='INIT',
            host='127.0.0.1',
            port=port,
            username=USER,
            database='cdeadmin_pgbench_demo',
            scale=1,
            confirmation='cdeadmin_pgbench_demo',
        )
        assert res_bi['state'] == 'completed', res_bi

        res_br = _run_job(
            host_env,
            'host_pgbench',
            mode='RUN',
            host='127.0.0.1',
            port=port,
            username=USER,
            database='cdeadmin_pgbench_demo',
            clients=2,
            jobs=1,
            transactions=15,
            builtin_script='select-only',
            protocol='prepared',
            confirmation='cdeadmin_pgbench_demo',
        )
        assert res_br['state'] == 'completed', res_br
        metrics = res_br['result']['benchmark_metrics']
        assert metrics['transactions_processed'] == 30 and metrics['tps'] > 0
    finally:
        _stop_pg(PG18_BIN, cdir)

    # 5. host_pg_archivecleanup: continuity hold protection + dry-run + live cleanup!
    seg1 = '000000010000000000000001'
    seg2 = '000000010000000000000002'
    seg3 = '000000010000000000000003'
    for seg in (seg1, seg2, seg3):
        (host_env.arch_dir / seg).write_bytes(b'\x00' * 64)
    hold_file = host_env.arch_dir / '.scratchrobin-archive-holds.json'
    hold_file.write_text(json.dumps({'protected_wal_files': [seg2]}), encoding='utf-8')
    with pytest.raises(ContinuityError, match='protected by an active recovery/consumer hold'):
        _run_job(
            host_env,
            'host_pg_archivecleanup',
            archive_id='arch_main',
            oldest_kept_wal_file=seg3,
            dry_run=False,
            confirmation='arch_main',
        )
    # Cleaning older than seg2 (keeping seg2 & seg3) is allowed!
    res_ac_dry = _run_job(
        host_env,
        'host_pg_archivecleanup',
        archive_id='arch_main',
        oldest_kept_wal_file=seg2,
        dry_run=True,
        confirmation='arch_main',
    )
    assert res_ac_dry['state'] == 'completed' and (host_env.arch_dir / seg1).exists()
    res_ac_live = _run_job(
        host_env,
        'host_pg_archivecleanup',
        archive_id='arch_main',
        oldest_kept_wal_file=seg2,
        dry_run=False,
        confirmation='arch_main',
    )
    assert res_ac_live['state'] == 'completed'
    assert not (host_env.arch_dir / seg1).exists() and (host_env.arch_dir / seg2).exists()


def test_rewind_createsubscriber_and_cross_major_pg17_to_pg18_upgrade_live(host_env):
    # --- 6. host_pg_createsubscriber (physical standby -> logical replica!) ---
    pub_dir = host_env.tmp / 'pub18'
    sub_dir = host_env.tmp / 'sub18'
    subprocess.run(
        [str(PG18_BIN / 'initdb'), '-D', str(pub_dir), '--data-checksums', '--auth=trust', '--no-locale', '--encoding=UTF8', f'--username={USER}'],
        check=True,
        capture_output=True,
    )
    pub_port = _free_port()
    sub_port = _free_port()
    _start_pg(
        PG18_BIN,
        pub_dir,
        pub_port,
        '-c wal_level=logical -c max_wal_senders=6 -c max_replication_slots=6 -c max_worker_processes=8',
    )
    try:
        with psycopg.connect(host='127.0.0.1', port=pub_port, user=USER, dbname='postgres', autocommit=True) as conn:
            conn.execute('CREATE TABLE public.rep_items (id int primary key, v text)')
            conn.execute("INSERT INTO public.rep_items VALUES (1, 'before_sub')")
        subprocess.run(
            [str(PG18_BIN / 'pg_basebackup'), '-h', '127.0.0.1', '-p', str(pub_port), '-U', USER, '-D', str(sub_dir), '-R', '-X', 'stream'],
            check=True,
            capture_output=True,
            timeout=30,
        )
        # Ensure standby also has logical wal_level & replication settings and reaches clean shut down in recovery
        with (sub_dir / 'postgresql.auto.conf').open('a', encoding='utf-8') as f:
            f.write('\nwal_level = logical\nmax_replication_slots = 6\nmax_logical_replication_workers = 4\nmax_worker_processes = 8\n')
        _start_pg(PG18_BIN, sub_dir, sub_port)
        _stop_pg(PG18_BIN, sub_dir, mode='fast')
        _update_manifest(host_env, lambda g: g['clusters'].extend([
            {'id': 'pub18', 'path': str(pub_dir)},
            {'id': 'sub18', 'path': str(sub_dir)},
        ]))

        res_cs_dry = _run_job(
            host_env,
            'host_pg_createsubscriber',
            cluster_id='sub18',
            publisher_host='127.0.0.1',
            publisher_port=pub_port,
            publisher_user=USER,
            databases=['postgres'],
            dry_run=True,
            subscriber_port=sub_port,
            subscriber_username=USER,
            offline_quiescence_confirmed=True,
            confirmation='sub18',
        )
        assert res_cs_dry['state'] == 'completed', res_cs_dry

        res_cs_live = _run_job(
            host_env,
            'host_pg_createsubscriber',
            cluster_id='sub18',
            publisher_host='127.0.0.1',
            publisher_port=pub_port,
            publisher_user=USER,
            databases=['postgres'],
            dry_run=False,
            subscriber_port=sub_port,
            subscriber_username=USER,
            publication_name='sr_pub_main',
            subscription_name='sr_sub_main',
            offline_quiescence_confirmed=True,
            confirmation='sub18',
        )
        assert res_cs_live['state'] == 'completed', res_cs_live
        assert res_cs_live['result']['verification_complete'] is True
    finally:
        _stop_pg(PG18_BIN, sub_dir)
        _stop_pg(PG18_BIN, pub_dir)

    # --- 7. host_pg_rewind (diverged timeline resynchronization!) ---
    rw_pri = host_env.tmp / 'rw_pri'
    rw_stb = host_env.tmp / 'rw_stb'
    subprocess.run(
        [str(PG18_BIN / 'initdb'), '-D', str(rw_pri), '--data-checksums', '--auth=trust', '--no-locale', '--encoding=UTF8', f'--username={USER}'],
        check=True,
        capture_output=True,
    )
    rw_port = _free_port()
    with (rw_pri / 'postgresql.auto.conf').open('a', encoding='utf-8') as f:
        f.write("\nwal_log_hints = on\nwal_keep_size = '64MB'\nmax_wal_senders = 4\n")
    _start_pg(PG18_BIN, rw_pri, rw_port)
    try:
        with psycopg.connect(host='127.0.0.1', port=rw_port, user=USER, dbname='postgres', autocommit=True) as c:
            c.execute('CREATE TABLE public.rw_tbl (id int primary key)')
            c.execute('INSERT INTO public.rw_tbl VALUES (1)')
        subprocess.run(
            [str(PG18_BIN / 'pg_basebackup'), '-h', '127.0.0.1', '-p', str(rw_port), '-U', USER, '-D', str(rw_stb), '-R', '-X', 'stream'],
            check=True,
            capture_output=True,
            timeout=30,
        )
        # Diverge old primary cleanly, then stop old primary and promote standby to timeline 2!
        with psycopg.connect(host='127.0.0.1', port=rw_port, user=USER, dbname='postgres', autocommit=True) as c:
            c.execute('INSERT INTO public.rw_tbl VALUES (999)')
        _stop_pg(PG18_BIN, rw_pri, mode='fast')

        stb_port = _free_port()
        _start_pg(PG18_BIN, rw_stb, stb_port, '-c wal_log_hints=on')
        with psycopg.connect(host='127.0.0.1', port=stb_port, user=USER, dbname='postgres', autocommit=True) as cs:
            cs.execute('SELECT pg_promote(true)')
            cs.execute('INSERT INTO public.rw_tbl VALUES (2)')
            cs.execute('CHECKPOINT')
        _stop_pg(PG18_BIN, rw_stb, mode='fast')

        _update_manifest(host_env, lambda g: g['clusters'].extend([
            {'id': 'rw_pri', 'path': str(rw_pri)},
            {'id': 'rw_stb', 'path': str(rw_stb)},
        ]))
        res_rewind = _run_job(
            host_env,
            'host_pg_rewind',
            cluster_id='rw_pri',
            source_mode='cluster',
            source_cluster_id='rw_stb',
            dry_run=False,
            offline_quiescence_confirmed=True,
            confirmation='rw_pri',
        )
        assert res_rewind['state'] == 'completed', res_rewind['result']['native']
        _start_pg(PG18_BIN, rw_pri, rw_port)
        with psycopg.connect(host='127.0.0.1', port=rw_port, user=USER, dbname='postgres', autocommit=True) as c:
            assert c.execute('SELECT id FROM public.rw_tbl ORDER BY id').fetchall() == [(1,), (2,)]
    finally:
        _stop_pg(PG18_BIN, rw_pri)
        _stop_pg(PG18_BIN, rw_stb)

    # --- 8. host_pg_upgrade: REAL cross-major PG 17 -> PG 18 upgrade! ---
    if (PG17_BIN / 'initdb').is_file():
        old17 = host_env.tmp / 'old_pg17'
        new18 = host_env.tmp / 'new_pg18'
        subprocess.run(
            [str(PG17_BIN / 'initdb'), '-D', str(old17), '--data-checksums', '--auth=trust', '--no-locale', '--encoding=UTF8', f'--username={USER}'],
            check=True,
            capture_output=True,
        )
        p17 = _free_port()
        _start_pg(PG17_BIN, old17, p17)
        try:
            with psycopg.connect(host='127.0.0.1', port=p17, user=USER, dbname='postgres', autocommit=True) as c17:
                c17.execute('CREATE TABLE public.upgraded_data (id int primary key, note text)')
                c17.execute("INSERT INTO public.upgraded_data VALUES (42, 'migrated_17_to_18')")
        finally:
            _stop_pg(PG17_BIN, old17, mode='fast')

        subprocess.run(
            [str(PG18_BIN / 'initdb'), '-D', str(new18), '--data-checksums', '--auth=trust', '--no-locale', '--encoding=UTF8', f'--username={USER}'],
            check=True,
            capture_output=True,
        )
        _update_manifest(host_env, lambda g: g['upgrade_pairs'].append({
            'id': 'up_17_18',
            'old_bindir': str(PG17_BIN),
            'new_bindir': str(PG18_BIN),
            'old_datadir': str(old17),
            'new_datadir': str(new18),
        }))
        res_chk = _run_job(
            host_env,
            'host_pg_upgrade',
            pair_id='up_17_18',
            check_only=True,
            username=USER,
            offline_quiescence_confirmed=True,
            confirmation='up_17_18',
        )
        assert res_chk['state'] == 'completed', res_chk
        assert 'Clusters are compatible' in res_chk['result']['native']['stdout']

        res_upg = _run_job(
            host_env,
            'host_pg_upgrade',
            pair_id='up_17_18',
            check_only=False,
            transfer_mode='copy',
            username=USER,
            offline_quiescence_confirmed=True,
            upgrade_mutation_confirmed=True,
            confirmation='up_17_18',
        )
        assert res_upg['state'] == 'completed', res_upg

        p18_new = _free_port()
        _start_pg(PG18_BIN, new18, p18_new)
        try:
            with psycopg.connect(host='127.0.0.1', port=p18_new, user=USER, dbname='postgres', autocommit=True) as c18:
                ver_num = int(c18.execute('SHOW server_version_num').fetchone()[0])
                assert ver_num >= 180000
                rows = c18.execute('SELECT id, note FROM public.upgraded_data').fetchall()
                assert rows == [(42, 'migrated_17_to_18')]
        finally:
            _stop_pg(PG18_BIN, new18, mode='fast')


def test_authenticated_http_host_tools_catalog_and_initdb(host_env, tmp_path):
    builtins.SERVER_MODE = None
    import config

    app_root = tmp_path / 'http_app'
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

    app = create_app('ScratchRobin-pg-batch2-http')
    app.PGADMIN_RUNTIME = False
    app.PGADMIN_INT_KEY = ''
    # The tests authenticate through the session, not the encrypted user-configuration login.
    app.config['USER_CONFIG_LOGIN_REQUIRED'] = False
    app.run_before_app_start()

    with app.test_request_context('/'):
        user = User.query.first()
        group = ServerGroup.query.filter_by(user_id=user.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility['postgresql'].set(True, user_id=user.id)
        srv = Server(
            user_id=user.id,
            servergroup_id=group.id,
            name='PG18 Batch2 HTTP',
            host='127.0.0.1',
            port=5432,
            username=USER,
            maintenance_db='postgres',
            connection_params={'sslmode': 'disable'},
            save_password=0,
        )
        db.session.add(srv)
        db.session.commit()
        uid = user.id
        endpoint_id = srv.endpoint_profile.id
        ws_url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=srv.id)

    http_manifest = tmp_path / 'http_grants.json'
    http_init_root = tmp_path / 'http_init_root'
    http_init_root.mkdir()
    http_manifest.write_text(
        json.dumps({
            'format': 'scratchrobin.postgresql.host-tools@1',
            'grants': [{
                'endpoint_id': endpoint_id,
                'init_roots': [{'id': 'http_init', 'path': str(http_init_root)}],
            }],
        }),
        encoding='utf-8',
    )
    app.config['CDEADMIN_POSTGRESQL_HOST_TOOL_MANIFEST'] = str(http_manifest)
    app.config['CDEADMIN_POSTGRESQL_HOST_BINARY_PATH'] = str(PG18_BIN)
    app.config['CDEADMIN_POSTGRESQL_HOST_TOOL_ROOT'] = str(tmp_path / 'http_jobs')

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True

    cat = client.post(ws_url, json={'action': 'postgresql_host_tools', 'request': {'stage': 'catalog'}}).get_json()['data']
    assert cat['init_roots'] == [{'id': 'http_init'}]
    assert all(cat['tools'][t]['available'] for t in OPERATIONS.values())

    rev = client.post(
        ws_url,
        json={
            'action': 'postgresql_host_tools',
            'request': {
                'stage': 'review',
                'operation_id': 'host_initdb',
                'draft': {
                    'init_root_id': 'http_init',
                    'subdir': 'http_cluster',
                    'username': USER,
                    'auth_host': 'trust',
                    'auth_local': 'trust',
                    'confirmation': 'http_init/http_cluster',
                },
            },
        },
    ).get_json()['data']
    client.post(
        ws_url,
        json={
            'action': 'postgresql_host_tools',
            'request': {
                'stage': 'start',
                'job_id': rev['job_id'],
                'review_digest': rev['review_digest'],
                'confirmed': True,
            },
        },
    )
    deadline = time.monotonic() + 45
    while True:
        st = client.post(ws_url, json={'action': 'postgresql_host_tools', 'request': {'stage': 'status', 'job_id': rev['job_id']}}).get_json()['data']
        if st['state'] == 'completed':
            break
        assert time.monotonic() < deadline, st
        time.sleep(0.05)
    assert (http_init_root / 'http_cluster' / 'PG_VERSION').read_text().strip() == '18'
