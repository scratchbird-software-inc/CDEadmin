"""PostgreSQL High Availability, Streaming Replication Topology & Host Service Control (PG-AUDIT-HA-01).

Provides:
- Live primary/standby topology, lag, slot, and WAL receiver inspection
- Production standby bootstrap (`pg_basebackup -R -X stream`) on granted local or SSH hosts
- Controlled standby promotion (`pg_promote` / `pg_ctl promote`)
- Coordinated switchover with primary read-only fencing, LSN catchup verification, and promotion
- Authorized host `pg_ctl` (`status`, `start`, `stop`, `restart`, `reload`) lifecycle management
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .continuity import ContinuityError, PhysicalTools
from ...operations.fileio import private_directory, private_file

SLOT_RE = re.compile(r'[a-z0-9_]{1,63}\Z')


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf8')
    ).hexdigest()


def inspect_topology(dsn_or_params: str | dict) -> dict:
    """Observe live cluster role, replication peers, WAL receiver, and slot lag."""
    conn_kwargs = {'autocommit': True, 'connect_timeout': 10, 'row_factory': dict_row}
    conn_ctx = (
        psycopg.connect(dsn_or_params, **conn_kwargs)
        if isinstance(dsn_or_params, str)
        else psycopg.connect(**{**dsn_or_params, **conn_kwargs})
    )
    with conn_ctx as conn:
        header = conn.execute(
            """
            SELECT
                (SELECT system_identifier::text FROM pg_catalog.pg_control_system()) AS system_identifier,
                (SELECT timeline_id FROM pg_catalog.pg_control_checkpoint()) AS timeline_id,
                pg_catalog.pg_is_in_recovery() AS in_recovery,
                CASE WHEN pg_catalog.pg_is_in_recovery()
                     THEN pg_catalog.pg_last_wal_replay_lsn()::text
                     ELSE pg_catalog.pg_current_wal_lsn()::text
                END AS wal_lsn,
                CASE WHEN pg_catalog.pg_is_in_recovery()
                     THEN pg_catalog.pg_last_wal_receive_lsn()::text
                     ELSE NULL
                END AS receive_lsn,
                CASE WHEN pg_catalog.pg_is_in_recovery()
                     THEN pg_catalog.pg_is_wal_replay_paused()
                     ELSE false
                END AS replay_paused,
                current_setting('default_transaction_read_only') AS default_transaction_read_only,
                current_setting('synchronous_standby_names') AS synchronous_standby_names,
                current_setting('wal_level') AS wal_level,
                current_setting('max_wal_senders')::int AS max_wal_senders,
                current_setting('server_version_num')::int AS server_version_num
            """
        ).fetchone()

        standbys = conn.execute(
            """
            SELECT
                pid,
                usename,
                application_name,
                client_addr::text AS client_addr,
                client_port,
                state,
                sync_state,
                sent_lsn::text AS sent_lsn,
                write_lsn::text AS write_lsn,
                flush_lsn::text AS flush_lsn,
                replay_lsn::text AS replay_lsn,
                CASE WHEN NOT pg_catalog.pg_is_in_recovery() AND replay_lsn IS NOT NULL
                     THEN pg_catalog.pg_wal_lsn_diff(pg_catalog.pg_current_wal_lsn(), replay_lsn)::bigint
                     ELSE NULL
                END AS replay_lag_bytes
            FROM pg_catalog.pg_stat_replication
            ORDER BY application_name, pid
            """
        ).fetchall()

        receiver = conn.execute(
            """
            SELECT
                pid,
                status,
                sender_host,
                sender_port,
                slot_name,
                flushed_lsn::text AS flushed_lsn,
                received_tli
            FROM pg_catalog.pg_stat_wal_receiver
            """
        ).fetchone()

        slots = conn.execute(
            """
            SELECT
                slot_name,
                slot_type,
                plugin,
                database,
                temporary,
                active,
                active_pid,
                wal_status,
                restart_lsn::text AS restart_lsn,
                confirmed_flush_lsn::text AS confirmed_flush_lsn
            FROM pg_catalog.pg_replication_slots
            ORDER BY slot_name
            """
        ).fetchall()

    return {
        'role': 'standby' if header['in_recovery'] else 'primary',
        'system_identifier': header['system_identifier'],
        'timeline_id': int(header['timeline_id']),
        'in_recovery': bool(header['in_recovery']),
        'wal_lsn': header['wal_lsn'],
        'receive_lsn': header['receive_lsn'],
        'replay_paused': bool(header['replay_paused']),
        'default_transaction_read_only': header['default_transaction_read_only'],
        'synchronous_standby_names': header['synchronous_standby_names'],
        'wal_level': header['wal_level'],
        'max_wal_senders': int(header['max_wal_senders']),
        'server_version_num': int(header['server_version_num']),
        'standbys': [
            {**row, 'replay_lag_bytes': int(row['replay_lag_bytes']) if row['replay_lag_bytes'] is not None else None}
            for row in standbys
        ],
        'wal_receiver': dict(receiver) if receiver else None,
        'replication_slots': list(slots),
        'observed_at': time.time(),
    }


def check_host_datadir_grant(app, datadir: str, host_authorized: bool) -> Path:
    if not host_authorized:
        raise ContinuityError('Administrator host authorization is required for PostgreSQL HA host operations')
    if not isinstance(datadir, str) or not datadir.strip() or '\x00' in datadir:
        raise ContinuityError('Select an explicit PostgreSQL cluster data directory')
    raw = Path(datadir)
    if not raw.is_absolute():
        raise ContinuityError('Cluster data directory must be an absolute path')
    resolved = raw.resolve(strict=False)
    grants = (
        app.config.get('CDEADMIN_POSTGRESQL_HA_GRANTS')
        or app.config.get('CDEADMIN_POSTGRESQL_RESTORE_GRANTS')
        or app.config.get('CDEADMIN_POSTGRESQL_HOST_TOOL_GRANTS')
    )
    if isinstance(grants, (list, tuple, set)):
        ok = False
        for g in grants:
            root_str = g.get('datadir') or g.get('scratch_root') or g.get('path') if isinstance(g, dict) else str(g)
            if not root_str:
                continue
            gp = Path(root_str).resolve(strict=False)
            if resolved == gp or resolved.is_relative_to(gp):
                ok = True
                break
        if not ok:
            raise ContinuityError('Cluster data directory is outside operator-granted HA host roots')
    elif grants is None:
        raise ContinuityError('Configure operator HA host directory grants before executing host operations')
    return resolved


def execute_standby_bootstrap(
    paths: dict,
    primary_params: dict,
    standby_datadir: Path,
    *,
    slot_name: str | None = None,
    create_slot: bool = False,
    standby_port: int | None = None,
    start_standby: bool = False,
    application_name: str | None = None,
) -> dict:
    """Bootstrap a physical streaming standby with `pg_basebackup -R -X stream`."""
    if standby_datadir.exists() and any(standby_datadir.iterdir()):
        raise ContinuityError('Standby destination directory must be empty before bootstrap')
    standby_datadir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    pg_basebackup = str(Path(paths['pg_basebackup']))
    cmd = [
        pg_basebackup,
        '-D', str(standby_datadir),
        '-R',
        '-X', 'stream',
        '--checkpoint=fast',
        '--no-password',
    ]
    if slot_name:
        if not SLOT_RE.fullmatch(slot_name):
            raise ContinuityError('Invalid physical replication slot name')
        cmd.extend(['-S', slot_name])
        if create_slot:
            cmd.append('-C')

    env = os.environ.copy()
    if primary_params.get('host'):
        env['PGHOST'] = str(primary_params['host'])
    if primary_params.get('port'):
        env['PGPORT'] = str(primary_params['port'])
    if primary_params.get('user'):
        env['PGUSER'] = str(primary_params['user'])
    if primary_params.get('dbname'):
        env['PGDATABASE'] = str(primary_params['dbname'])
    if application_name:
        env['PGAPPNAME'] = re.sub(r'[^a-zA-Z0-9_.-]', '_', application_name)[:60]

    pw_file = None
    try:
        if primary_params.get('password'):
            pw_file = standby_datadir.parent / f'.pgpass-{uuid.uuid4().hex[:8]}'
            h = primary_params.get('host') or '*'
            p = primary_params.get('port') or '*'
            u = primary_params.get('user') or '*'
            pw = str(primary_params['password']).replace('\\', '\\\\').replace(':', '\\:')
            pw_file.write_text(f'{h}:{p}:*:{u}:{pw}\n', encoding='utf8')
            private_file(pw_file)
            env['PGPASSFILE'] = str(pw_file)

        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300, check=False)
        if proc.returncode != 0:
            raise ContinuityError(
                f'pg_basebackup standby bootstrap failed: {(proc.stderr or proc.stdout).strip()[:512]}'
            )
    finally:
        if pw_file is not None:
            pw_file.unlink(missing_ok=True)

    private_directory(standby_datadir)
    if not (standby_datadir / 'standby.signal').is_file():
        raise ContinuityError('Standby bootstrap did not produce standby.signal')

    sock_dir = None
    extra_lines = ["hot_standby = 'on'", "listen_addresses = '127.0.0.1'"]
    if standby_port:
        sock_dir = Path(f'/tmp/sr-pgsb-{uuid.uuid4().hex[:8]}')
        sock_dir.mkdir(mode=0o700, exist_ok=True)
        extra_lines.append(f'port = {int(standby_port)}')
        extra_lines.append(f"unix_socket_directories = '{sock_dir}'")
    if application_name:
        safe_app = re.sub(r'[^a-zA-Z0-9_.-]', '_', application_name)[:60]
        extra_lines.append(f"cluster_name = '{safe_app}'")
    with (standby_datadir / 'postgresql.auto.conf').open('a', encoding='utf8') as fh:
        fh.write('\n' + '\n'.join(extra_lines) + '\n')
    private_file(standby_datadir / 'postgresql.auto.conf')

    started_info = {'started': False}
    standby_topology = None
    if start_standby:
        if not standby_port:
            raise ContinuityError('standby_port is required when start_standby is True')
        pg_ctl = str(Path(paths['pg_ctl']))
        log_file = standby_datadir / 'standby-postmaster.log'
        start_proc = subprocess.run(
            [pg_ctl, '-D', str(standby_datadir), '-l', str(log_file), '-w', '-t', '30', 'start'],
            capture_output=True,
            text=True,
            check=False,
        )
        if start_proc.returncode != 0:
            raise ContinuityError(
                f'Standby service failed to start: {(start_proc.stderr or start_proc.stdout).strip()[:512]}'
            )
        standby_dsn = f"host=127.0.0.1 port={int(standby_port)} user={primary_params.get('user', '')} dbname={primary_params.get('dbname', 'postgres')}"
        # Wait briefly for walreceiver to establish streaming
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            standby_topology = inspect_topology(standby_dsn)
            if standby_topology.get('wal_receiver') and standby_topology['wal_receiver'].get('status') == 'streaming':
                break
            time.sleep(0.25)
        started_info = {
            'started': True,
            'host': '127.0.0.1',
            'port': int(standby_port),
            'socket_dir': str(sock_dir) if sock_dir else None,
            'log_file': str(log_file),
        }

    return {
        'standby_datadir': str(standby_datadir),
        'standby_signal_present': True,
        'slot_name': slot_name,
        'slot_created': bool(slot_name and create_slot),
        'service': started_info,
        'standby_topology': standby_topology,
    }


def execute_standby_promotion(target_dsn_or_params: str | dict, *, wait_seconds: int = 30) -> dict:
    """Promote a streaming standby using native `pg_promote(true, wait_seconds)` and verify primary role."""
    before = inspect_topology(target_dsn_or_params)
    if not before['in_recovery']:
        raise ContinuityError('Selected PostgreSQL cluster is already a primary (not in recovery)')
    conn_kwargs = {'autocommit': True, 'connect_timeout': 10}
    conn_ctx = (
        psycopg.connect(target_dsn_or_params, **conn_kwargs)
        if isinstance(target_dsn_or_params, str)
        else psycopg.connect(**{**target_dsn_or_params, **conn_kwargs})
    )
    with conn_ctx as conn:
        promoted = conn.execute('SELECT pg_catalog.pg_promote(true, %s)', (int(wait_seconds),)).fetchone()[0]
        if not promoted:
            raise ContinuityError(f'Standby promotion did not complete within {wait_seconds} seconds')
    after = inspect_topology(target_dsn_or_params)
    if after['in_recovery']:
        raise ContinuityError('Cluster remained in recovery after pg_promote')
    return {
        'promoted': True,
        'system_identifier': after['system_identifier'],
        'timeline_before': before['timeline_id'],
        'timeline_after': after['timeline_id'],
        'wal_lsn_after': after['wal_lsn'],
    }


def execute_coordinated_switchover(
    primary_dsn_or_params: str | dict,
    standby_dsn: str,
    *,
    max_lag_bytes: int = 16 * 1024 * 1024,
    wait_seconds: int = 30,
) -> dict:
    """Fence old primary read-only, wait for standby LSN catchup, promote standby, and verify R/W."""
    p_before = inspect_topology(primary_dsn_or_params)
    s_before = inspect_topology(standby_dsn)
    if p_before['in_recovery']:
        raise ContinuityError('Switchover source cluster is in recovery, not an active primary')
    if not s_before['in_recovery']:
        raise ContinuityError('Switchover target cluster is already promoted (not in recovery)')
    if p_before['system_identifier'] != s_before['system_identifier']:
        raise ContinuityError('Primary and standby belong to different PostgreSQL clusters')

    # Fence primary read-only + flush checkpoint
    conn_kwargs = {'autocommit': True, 'connect_timeout': 10}
    p_ctx = (
        psycopg.connect(primary_dsn_or_params, **conn_kwargs)
        if isinstance(primary_dsn_or_params, str)
        else psycopg.connect(**{**primary_dsn_or_params, **conn_kwargs})
    )
    with p_ctx as pconn:
        pconn.execute("ALTER SYSTEM SET default_transaction_read_only = 'on'")
        pconn.execute('SELECT pg_catalog.pg_reload_conf()')
        pconn.execute('CHECKPOINT')
        fence_lsn = pconn.execute('SELECT pg_catalog.pg_current_wal_lsn()::text').fetchone()[0]

    # Wait for standby replay_lsn >= fence_lsn
    caught_up = False
    deadline = time.monotonic() + float(wait_seconds)
    with psycopg.connect(standby_dsn, autocommit=True, connect_timeout=10) as sconn:
        while time.monotonic() < deadline:
            diff = sconn.execute(
                'SELECT pg_catalog.pg_wal_lsn_diff(pg_catalog.pg_last_wal_replay_lsn(), %s::pg_lsn)::bigint',
                (fence_lsn,),
            ).fetchone()[0]
            if diff is not None and int(diff) >= 0:
                caught_up = True
                break
            if diff is not None and abs(int(diff)) > max_lag_bytes:
                raise ContinuityError(f'Standby replay lag ({abs(int(diff))} bytes) exceeds max_lag_bytes ({max_lag_bytes})')
            time.sleep(0.2)
    if not caught_up:
        raise ContinuityError(f'Standby did not replay fenced primary LSN {fence_lsn} within {wait_seconds}s')

    promo = execute_standby_promotion(standby_dsn, wait_seconds=wait_seconds)
    # Verify R/W on newly promoted primary
    probe_name = 'sr_sw_probe_' + uuid.uuid4().hex[:8]
    with psycopg.connect(standby_dsn, autocommit=False, connect_timeout=10) as rw_conn:
        rw_conn.execute(sql.SQL('CREATE TEMP TABLE {} (v int)').format(sql.Identifier(probe_name)))
        rw_conn.execute(sql.SQL('INSERT INTO {} VALUES (1)').format(sql.Identifier(probe_name)))
        rw_conn.commit()
    return {
        'switchover_completed': True,
        'system_identifier': p_before['system_identifier'],
        'old_primary_fenced_read_only': True,
        'fenced_lsn': fence_lsn,
        'standby_caught_up_to_fence_lsn': True,
        'promotion': promo,
        'new_primary_read_write_verified': True,
    }


def execute_host_pg_ctl(
    paths: dict,
    datadir: Path,
    ctl_action: str,
    *,
    stop_mode: str = 'fast',
    wait_seconds: int = 30,
    log_file: str | None = None,
) -> dict:
    """Run authorized host `pg_ctl` (`status`, `start`, `stop`, `restart`, `reload`) on a granted datadir."""
    if ctl_action not in {'status', 'start', 'stop', 'restart', 'reload'}:
        raise ContinuityError('pg_ctl action must be status, start, stop, restart, or reload')
    if stop_mode not in {'smart', 'fast', 'immediate'}:
        raise ContinuityError('stop_mode must be smart, fast, or immediate')
    if not (datadir / 'PG_VERSION').is_file():
        raise ContinuityError('Selected directory is not an initialized PostgreSQL data directory')

    pg_ctl = str(Path(paths['pg_ctl']))
    cmd = [pg_ctl, '-D', str(datadir)]
    if ctl_action in {'start', 'stop', 'restart'}:
        cmd.extend(['-w', '-t', str(int(wait_seconds))])
    if ctl_action in {'stop', 'restart'}:
        cmd.extend(['-m', stop_mode])
    if ctl_action in {'start', 'restart'}:
        lf = Path(log_file) if log_file else (datadir / 'postmaster.log')
        cmd.extend(['-l', str(lf)])
    cmd.append(ctl_action)

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=wait_seconds + 15, check=False)
    # For `pg_ctl status`, exit code 3 means server is stopped (valid status observation!)
    if ctl_action == 'status':
        running = proc.returncode == 0
        if proc.returncode not in {0, 3}:
            raise ContinuityError(f'pg_ctl status failed (rc={proc.returncode}): {(proc.stderr or proc.stdout).strip()[:256]}')
        return {
            'action': 'status',
            'datadir': str(datadir),
            'running': running,
            'return_code': proc.returncode,
            'output': (proc.stdout or proc.stderr).strip()[:1024],
        }
    if proc.returncode != 0:
        raise ContinuityError(
            f'pg_ctl {ctl_action} failed (rc={proc.returncode}): {(proc.stderr or proc.stdout).strip()[:512]}'
        )
    return {
        'action': ctl_action,
        'datadir': str(datadir),
        'return_code': 0,
        'output': (proc.stdout or proc.stderr).strip()[:1024],
        'observed_at': time.time(),
    }
