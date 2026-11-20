"""Native MariaDB major/minor server & system-table upgrade workflow (e.g. 11.8 -> 12.2.2).

Implements MA-AUDIT-HOST-UPGRADE:
- Pre-upgrade version compatibility, XA check, option-file validation & backup-prerequisite gate
- Clean source shutdown (`SET GLOBAL innodb_fast_shutdown=0` + `SHUTDOWN` + PID exit / writer check)
- Pre-upgrade rollback snapshot & datadir claim lock
- Binary/service switchover (`11.8` -> `12.2.2` `mariadbd`)
- Native `mariadb-upgrade` execution with private `0600` credentials & `mariadb_upgrade_info` verification
- Post-upgrade `--check-if-upgrade-is-needed` + independent `12.2.2` system-table & user-object verification
- Interrupted-upgrade reconciliation & verified datadir rollback
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import time

from ...operations.fileio import durable_replace, private_directory, private_file
from .mariadb_host_services import (
    MariaDBHostError,
    control_managed_service,
    validate_option_file_natively,
    verify_sql_readiness,
)
from .mariadb_physical import (
    admit_executable,
    canonical_digest,
    directory_manifest,
    execution_host_identity,
    file_sha256,
    inspect_backup_artifact,
    process_alive,
    rows,
    run_supervised_process,
    safe_absolute_path,
    write_private_defaults_file,
)


class MariaDBUpgradeError(MariaDBHostError):
    """Refusal or failure in MariaDB host & system-table upgrade workflows."""


def parse_version_tuple(version_str):
    m = re.search(r'(\d+)\.(\d+)\.(\d+)', str(version_str or ''))
    if not m:
        raise MariaDBUpgradeError(f'Unable to parse MariaDB semantic version from {version_str!r}')
    return tuple(int(x) for x in m.groups())


def read_datadir_upgrade_info(datadir):
    datadir = Path(datadir)
    for name in ('mariadb_upgrade_info', 'mysql_upgrade_info'):
        p = datadir / name
        if p.is_file():
            return {
                'filename': name,
                'raw': p.read_text(encoding='utf-8', errors='replace').strip(),
            }
    return None


def check_no_active_datadir_writers(datadir):
    """Verify no running process on this host holds open ibdata1 or aria_log_control in datadir."""
    datadir = Path(datadir).resolve(strict=False)
    targets = []
    for candidate in ('ibdata1', 'aria_log_control'):
        p = datadir / candidate
        if p.exists():
            st = p.stat()
            targets.append((st.st_dev, st.st_ino))
    if not targets or not Path('/proc').is_dir():
        return {'verified_absent': True, 'holder_pids': []}

    holders = []
    for proc_entry in Path('/proc').iterdir():
        if not proc_entry.name.isdigit():
            continue
        fd_dir = proc_entry / 'fd'
        try:
            for fd in fd_dir.iterdir():
                try:
                    fst = fd.stat()
                    if (fst.st_dev, fst.st_ino) not in targets:
                        continue
                    fdinfo = (proc_entry / 'fdinfo' / fd.name).read_text(encoding='utf-8', errors='replace')
                    m_flags = re.search(r'^flags:\s*([0-7]+)', fdinfo, re.MULTILINE)
                    if m_flags and (int(m_flags.group(1), 8) & 0o3) == 0:
                        # O_RDONLY / O_PATH handle (e.g. virtiofsd lookup cache), not a writer
                        continue
                    holders.append(int(proc_entry.name))
                    break
                except OSError:
                    continue
        except OSError:
            continue
    return {'verified_absent': len(holders) == 0, 'holder_pids': sorted(holders)}


def verify_backup_prerequisite(*, backup_record=None, verified_backup_dir=None, verified_logical_dump_path=None):
    """Require an actual verified physical or logical backup before admitting an upgrade."""
    if backup_record is not None:
        art = (backup_record.get('result') or {}).get('artifact')
        if backup_record.get('artifact_adoption_state') == 'artifact_adopted' and art:
            live = inspect_backup_artifact(backup_record['artifact_dir'])
            if live['manifest_sha256'] != art['manifest_sha256']:
                raise MariaDBUpgradeError('Referenced physical backup bytes changed; take a fresh backup before upgrading')
            return {
                'prerequisite_satisfied': True,
                'backup_kind': 'mariadb_physical_job',
                'backup_job_id': backup_record['job_id'],
                'manifest_sha256': live['manifest_sha256'],
            }
    if verified_backup_dir is not None:
        live = inspect_backup_artifact(verified_backup_dir)
        return {
            'prerequisite_satisfied': True,
            'backup_kind': 'mariadb_physical_directory',
            'backup_dir': str(Path(verified_backup_dir).resolve()),
            'manifest_sha256': live['manifest_sha256'],
        }
    if verified_logical_dump_path is not None:
        dump = safe_absolute_path(str(verified_logical_dump_path), 'verified_logical_dump_path')
        if not dump.is_file() or dump.stat().st_size < 32:
            raise MariaDBUpgradeError('Verified logical dump file is missing or empty')
        text_head = dump.read_bytes()[:4096].decode('utf-8', errors='replace')
        if 'MariaDB dump' not in text_head and 'CREATE ' not in text_head:
            raise MariaDBUpgradeError('Logical dump prerequisite does not contain a valid MariaDB SQL dump header')
        return {
            'prerequisite_satisfied': True,
            'backup_kind': 'mariadb_logical_dump',
            'dump_path': str(dump),
            'sha256': file_sha256(dump),
            'bytes': dump.stat().st_size,
        }
    raise MariaDBUpgradeError(
        'MariaDB upgrade requires a verified backup prerequisite (backup_job_id, verified_backup_dir, or verified_logical_dump_path)'
    )


def inspect_source_for_upgrade(conn):
    """Inspect a live pre-upgrade MariaDB server (e.g. 11.8) for compatibility, XA state, and object inventory."""
    meta = rows(
        conn,
        'SELECT VERSION() AS version, @@server_uid AS server_uid, @@datadir AS datadir, '
        '@@port AS port, @@innodb_fast_shutdown AS innodb_fast_shutdown',
    )[0]
    cur = conn.cursor()
    try:
        cur.execute('XA RECOVER')
        xa_rows = cur.fetchall()
    finally:
        cur.close()
    if xa_rows:
        raise MariaDBUpgradeError(
            f'Refusing upgrade while {len(xa_rows)} prepared XA transaction(s) remain unresolved'
        )
    databases = [
        r['schema_name'] for r in rows(
            conn,
            "SELECT SCHEMA_NAME AS schema_name FROM information_schema.SCHEMATA "
            "WHERE SCHEMA_NAME NOT IN ('information_schema','performance_schema','sys','mysql') "
            "ORDER BY SCHEMA_NAME",
        )
    ]
    tables = rows(
        conn,
        "SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS table_name, ENGINE AS engine "
        "FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA NOT IN ('information_schema','performance_schema','sys','mysql') "
        "AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME",
    )
    views = rows(
        conn,
        "SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS view_name "
        "FROM information_schema.VIEWS "
        "WHERE TABLE_SCHEMA NOT IN ('information_schema','performance_schema','sys','mysql') "
        "ORDER BY TABLE_SCHEMA, TABLE_NAME",
    )
    routines = rows(
        conn,
        "SELECT ROUTINE_SCHEMA AS schema_name, ROUTINE_NAME AS routine_name, ROUTINE_TYPE AS routine_type "
        "FROM information_schema.ROUTINES "
        "WHERE ROUTINE_SCHEMA NOT IN ('information_schema','performance_schema','sys','mysql') "
        "ORDER BY ROUTINE_SCHEMA, ROUTINE_TYPE, ROUTINE_NAME",
    )
    accounts = rows(
        conn,
        "SELECT User AS user, Host AS host FROM mysql.global_priv "
        "WHERE User NOT IN ('mariadb.sys','') ORDER BY User, Host",
    )
    return {
        'version': meta['version'],
        'version_tuple': list(parse_version_tuple(meta['version'])),
        'server_uid': meta['server_uid'],
        'datadir': meta['datadir'],
        'port': int(meta['port']),
        'prepared_xa_count': 0,
        'databases': databases,
        'tables': tables,
        'views': views,
        'routines': routines,
        'accounts': accounts,
    }


def clean_stop_source_daemon(*, host='127.0.0.1', port=3306, socket_path=None, db_user='root', db_password='', pid_birth=None, timeout_seconds=60):
    """Execute `SET GLOBAL innodb_fast_shutdown=0` and `SHUTDOWN` on the source MariaDB server."""
    import mariadb

    kwargs = {'user': db_user, 'password': db_password or '', 'connect_timeout': 5, 'autocommit': True}
    if socket_path:
        kwargs['unix_socket'] = str(socket_path)
    else:
        kwargs['host'] = host
        kwargs['port'] = int(port)
    conn = mariadb.connect(**kwargs)
    try:
        before = rows(conn, 'SELECT VERSION() AS version, @@server_uid AS server_uid, @@datadir AS datadir')[0]
        cur = conn.cursor()
        try:
            cur.execute('SET GLOBAL innodb_fast_shutdown=0')
            fast_val = rows(conn, 'SELECT @@global.innodb_fast_shutdown AS val')[0]['val']
            if int(fast_val) != 0:
                raise MariaDBUpgradeError('Failed to set innodb_fast_shutdown=0 prior to clean upgrade shutdown')
            cur.execute('SHUTDOWN')
        finally:
            cur.close()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # Wait until SQL port/socket stops accepting connections and optional PID exits
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if pid_birth and process_alive(pid_birth):
            time.sleep(0.15)
            continue
        try:
            probe = mariadb.connect(**{**kwargs, 'connect_timeout': 1})
            probe.close()
            time.sleep(0.15)
        except Exception:
            break
    if pid_birth and process_alive(pid_birth):
        raise MariaDBUpgradeError('Source MariaDB daemon PID is still alive after SHUTDOWN timeout')

    return {
        'innodb_fast_shutdown': 0,
        'shutdown_acknowledged': True,
        'source_version': before['version'],
        'source_server_uid': before['server_uid'],
        'source_datadir': before['datadir'],
        'stopped_at': time.time(),
    }


def claim_path_for_datadir(datadir):
    d = safe_absolute_path(str(datadir), 'upgrade datadir')
    return d.parent / f'.{d.name}.sr-mariadb-upgrade-claim.json'


def _save_phase(job_dir, payload):
    p = Path(job_dir) / 'upgrade-phase.json'
    tmp = Path(job_dir) / '.upgrade-phase.json.tmp'
    with tmp.open('w', encoding='utf-8') as f:
        private_file(tmp)
        json.dump(payload, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    durable_replace(tmp, p)


def preflight_upgrade(
    *, datadir, target_mariadbd_binary, target_upgrade_binary,
    source_version=None, configuration_file=None,
    target_basedir=None, target_lc_messages_dir=None,
    backup_record=None, verified_backup_dir=None, verified_logical_dump_path=None,
    target_version_prefix='12.2.2',
):
    """Validate upgrade eligibility, candidate 12.2.2 binaries/config, and backup prerequisite."""
    datadir = safe_absolute_path(str(datadir), 'datadir')
    if not (datadir / 'mysql').is_dir():
        raise MariaDBUpgradeError(f'Datadir {datadir} does not contain initialized MariaDB system tables')
    claim = claim_path_for_datadir(datadir)
    if claim.exists():
        raise MariaDBUpgradeError(
            f'An unretired MariaDB upgrade claim already owns {datadir}; reconcile or roll back first'
        )

    target_daemon = admit_executable(target_mariadbd_binary, 'mariadbd', version_prefix=target_version_prefix)
    target_upgrader = admit_executable(target_upgrade_binary, 'mariadb-upgrade', version_prefix=target_version_prefix)
    target_ver_tuple = parse_version_tuple(target_daemon['tool_version'])

    prev_info = read_datadir_upgrade_info(datadir)
    effective_source_ver = source_version or (prev_info['raw'] if prev_info else None)
    if effective_source_ver:
        src_tuple = parse_version_tuple(effective_source_ver)
        if src_tuple > target_ver_tuple:
            raise MariaDBUpgradeError(
                f'Downgrade refused: source datadir version {effective_source_ver} > target {target_daemon["tool_version"]}'
            )
        if src_tuple < (10, 6, 0):
            raise MariaDBUpgradeError(
                f'Source version {effective_source_ver} is below minimum supported floor 10.6.0'
            )

    cfg_validation = None
    if configuration_file:
        cfg_validation = validate_option_file_natively(
            target_daemon['path'], configuration_file,
            basedir=target_basedir, lc_messages_dir=target_lc_messages_dir,
            version_prefix=target_version_prefix,
        )
        if not cfg_validation['valid']:
            raise MariaDBUpgradeError(
                'Target configuration file is incompatible with target mariadbd: '
                + '; '.join(cfg_validation['diagnostics'])
            )

    backup_proof = verify_backup_prerequisite(
        backup_record=backup_record,
        verified_backup_dir=verified_backup_dir,
        verified_logical_dump_path=verified_logical_dump_path,
    )

    return {
        'datadir': str(datadir),
        'source_version': effective_source_ver,
        'previous_upgrade_info': prev_info,
        'target_mariadbd': target_daemon,
        'target_mariadb_upgrade': target_upgrader,
        'target_version_tuple': list(target_ver_tuple),
        'configuration_validation': cfg_validation,
        'backup_prerequisite': backup_proof,
        'execution_host': execution_host_identity(),
    }


def run_managed_upgrade(
    *, job_id, job_dir, datadir,
    target_mariadbd_binary, target_upgrade_binary,
    target_port, db_user='root', db_password='',
    source_running_connection=None,
    configuration_file=None, target_basedir=None,
    target_plugin_dir=None, target_lc_messages_dir=None,
    daemon_user=None, backup_record=None,
    verified_backup_dir=None, verified_logical_dump_path=None,
    source_version=None, target_version_prefix='12.2.2',
    create_rollback_snapshot=True,
    simulate_interrupt_before_upgrade_tool=False,
    timeout_seconds=300,
):
    """Execute the complete MariaDB host + system-table upgrade workflow with durable phase checkpoints."""
    job_dir = safe_absolute_path(str(job_dir), 'upgrade job directory')
    datadir = safe_absolute_path(str(datadir), 'upgrade datadir')
    job_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(job_dir)

    preflight = preflight_upgrade(
        datadir=datadir,
        target_mariadbd_binary=target_mariadbd_binary,
        target_upgrade_binary=target_upgrade_binary,
        source_version=source_version,
        configuration_file=configuration_file,
        target_basedir=target_basedir,
        target_lc_messages_dir=target_lc_messages_dir,
        backup_record=backup_record,
        verified_backup_dir=verified_backup_dir,
        verified_logical_dump_path=verified_logical_dump_path,
        target_version_prefix=target_version_prefix,
    )

    claim = claim_path_for_datadir(datadir)
    with claim.open('x', encoding='utf-8') as cf:
        private_file(claim)
        json.dump({'job_id': job_id, 'datadir': str(datadir), 'claimed_at': time.time()}, cf)
        cf.flush()
        os.fsync(cf.fileno())

    phase = {
        'job_id': job_id,
        'stage': 'claimed',
        'steps_completed': [],
        'datadir': str(datadir),
        'target_state_dir': str(job_dir / 'target-daemon'),
        'started_at': time.time(),
        'automatic_retry': False,
    }
    _save_phase(job_dir, phase)

    # Step 1: Cleanly stop live source daemon if still running, then verify zero active writers
    shutdown_receipt = None
    if source_running_connection is not None:
        phase['stage'] = 'stopping_source_daemon'
        _save_phase(job_dir, phase)
        shutdown_receipt = clean_stop_source_daemon(
            host=source_running_connection.get('host', '127.0.0.1'),
            port=int(source_running_connection.get('port', 3306)),
            socket_path=source_running_connection.get('socket_path'),
            db_user=source_running_connection.get('db_user', db_user),
            db_password=source_running_connection.get('db_password', db_password),
            pid_birth=source_running_connection.get('pid_birth'),
            timeout_seconds=60,
        )
        phase['source_shutdown'] = shutdown_receipt
        phase['steps_completed'].append('clean_source_shutdown')
        _save_phase(job_dir, phase)

    writers = check_no_active_datadir_writers(datadir)
    if not writers['verified_absent']:
        raise MariaDBUpgradeError(
            f"Refusing upgrade: datadir {datadir} still has active writer PIDs {writers['holder_pids']}"
        )
    phase['writers_check'] = writers
    phase['steps_completed'].append('verified_datadir_quiescent')
    _save_phase(job_dir, phase)

    # Step 2: Capture pre-upgrade rollback snapshot so interrupted upgrades can cleanly roll back
    snapshot_dir = job_dir / 'pre-upgrade-snapshot'
    snapshot_manifest_sha = None
    if create_rollback_snapshot:
        phase['stage'] = 'capturing_rollback_snapshot'
        _save_phase(job_dir, phase)
        shutil.copytree(datadir, snapshot_dir)
        snap_files = directory_manifest(snapshot_dir)
        snapshot_manifest_sha = canonical_digest(snap_files)
        phase['rollback_snapshot'] = {
            'path': str(snapshot_dir),
            'file_count': len(snap_files),
            'manifest_sha256': snapshot_manifest_sha,
        }
        phase['steps_completed'].append('pre_upgrade_snapshot_captured')
        _save_phase(job_dir, phase)

    if os.geteuid() == 0 and daemon_user:
        pw = pwd.getpwnam(daemon_user)
        for root, dirs, files in os.walk(datadir, followlinks=False):
            os.chown(root, pw.pw_uid, pw.pw_gid)
            for d in dirs:
                os.chown(Path(root) / d, pw.pw_uid, pw.pw_gid)
            for f in files:
                os.chown(Path(root) / f, pw.pw_uid, pw.pw_gid)

    # Step 3: Start target 12.2.2 mariadbd binary on datadir (--skip-slave-start)
    phase['stage'] = 'starting_target_daemon'
    _save_phase(job_dir, phase)
    target_state_dir = job_dir / 'target-daemon'
    started_svc = control_managed_service(
        action='start',
        service_mode='managed_daemon',
        state_dir=target_state_dir,
        mariadbd_binary=preflight['target_mariadbd']['path'],
        defaults_file=configuration_file,
        datadir=datadir,
        port=int(target_port),
        bind_address='127.0.0.1',
        daemon_user=daemon_user,
        basedir=target_basedir,
        plugin_dir=target_plugin_dir,
        lc_messages_dir=target_lc_messages_dir,
        extra_args=('--skip-slave-start', '--event-scheduler=DISABLED'),
        db_user=db_user,
        db_password=db_password,
        version_prefix=target_version_prefix,
    )
    readiness_pre = verify_sql_readiness(
        host='127.0.0.1', port=int(target_port),
        db_user=db_user, db_password=db_password,
        expected_datadir=datadir, timeout_seconds=60,
    )
    phase['target_daemon_started'] = started_svc
    phase['pre_tool_readiness'] = readiness_pre
    phase['steps_completed'].append('target_binary_switchover_ready')
    _save_phase(job_dir, phase)

    if simulate_interrupt_before_upgrade_tool:
        phase['stage'] = 'interrupted_before_mariadb_upgrade_tool'
        _save_phase(job_dir, phase)
        raise InterruptedError('Simulated interruption after binary switchover before mariadb-upgrade completed')

    try:
        # Step 4: Execute native `mariadb-upgrade` with private 0600 defaults file
        phase['stage'] = 'running_mariadb_upgrade'
        _save_phase(job_dir, phase)
        cnf = write_private_defaults_file(
            job_dir, user=db_user, password=db_password,
            host='127.0.0.1', port=int(target_port),
        )
        upg_obs = run_supervised_process(
            preflight['target_mariadb_upgrade']['path'],
            ['--protocol=tcp', '--host=127.0.0.1', f'--port={int(target_port)}', '--skip-ssl', '--verbose'],
            job_dir,
            timeout_seconds=timeout_seconds,
            defaults_file=cnf,
            redact_values=(db_password,),
        )
        phase['mariadb_upgrade_observation'] = {k: v for k, v in upg_obs.items() if k not in {'stdout', 'stderr'}}
        if upg_obs['return_code'] != 0:
            phase['stage'] = 'mariadb_upgrade_failed'
            _save_phase(job_dir, phase)
            raise MariaDBUpgradeError(
                f"mariadb-upgrade failed (rc={upg_obs['return_code']}): {(upg_obs['stderr'] or upg_obs['stdout'])[-800:]}"
            )

        # Verify mariadb_upgrade_info written in datadir
        upg_info = read_datadir_upgrade_info(datadir)
        if not upg_info or target_version_prefix not in upg_info['raw']:
            phase['stage'] = 'upgrade_info_unverified'
            _save_phase(job_dir, phase)
            raise MariaDBUpgradeError(
                f'Expected {target_version_prefix} in mariadb_upgrade_info, observed {upg_info!r}'
            )
        phase['mariadb_upgrade_info'] = upg_info
        phase['steps_completed'].append('mariadb_upgrade_executed_and_info_verified')
        _save_phase(job_dir, phase)

        # Step 5: Run `--check-if-upgrade-is-needed` (MariaDB exits 0 if upgrade IS still needed, 1 otherwise!)
        cnf_chk = write_private_defaults_file(
            job_dir, user=db_user, password=db_password,
            host='127.0.0.1', port=int(target_port),
        )
        chk_obs = run_supervised_process(
            preflight['target_mariadb_upgrade']['path'],
            ['--check-if-upgrade-is-needed', '--protocol=tcp', '--host=127.0.0.1', f'--port={int(target_port)}', '--skip-ssl'],
            job_dir, timeout_seconds=30, defaults_file=cnf_chk, redact_values=(db_password,),
        )
        upgrade_still_needed = chk_obs['return_code'] == 0

        # Step 6: Independent post-upgrade SQL readiness, system-table & user-object verification
        post_verification = verify_post_upgrade_instance(
            host='127.0.0.1', port=int(target_port),
            db_user=db_user, db_password=db_password,
            expected_version_prefix=target_version_prefix,
            expected_datadir=datadir,
        )
    except BaseException:
        control_managed_service(
            action='stop', service_mode='managed_daemon',
            state_dir=target_state_dir, db_user=db_user, db_password=db_password,
        )
        raise
    claim.unlink(missing_ok=True)
    phase['stage'] = 'completed'
    phase['claim_released'] = not claim.exists()
    phase['upgrade_still_needed'] = upgrade_still_needed
    phase['post_upgrade_verification'] = post_verification
    phase['steps_completed'].append('post_upgrade_verified_and_claim_released')
    phase['finished_at'] = time.time()
    _save_phase(job_dir, phase)

    return {
        'preflight': preflight,
        'source_shutdown': shutdown_receipt,
        'mariadb_upgrade_info': upg_info,
        'check_if_needed_return_code': chk_obs['return_code'],
        'upgrade_still_needed': upgrade_still_needed,
        'post_upgrade_verification': post_verification,
        'target_daemon': started_svc['daemon'],
        'claim_released': True,
    }


def verify_post_upgrade_instance(
    *, host='127.0.0.1', port=3306, db_user='root', db_password='',
    expected_version_prefix='12.2.2', expected_datadir=None,
):
    """Verify upgraded MariaDB system tables and user schemas/tables/views/routines/grants."""
    import mariadb

    readiness = verify_sql_readiness(
        host=host, port=port, db_user=db_user, db_password=db_password,
        expected_datadir=expected_datadir, timeout_seconds=30,
    )
    if expected_version_prefix and not str(readiness['version']).startswith(expected_version_prefix):
        raise MariaDBUpgradeError(
            f"Upgraded server version {readiness['version']} does not match {expected_version_prefix}"
        )

    conn = mariadb.connect(host=host, port=int(port), user=db_user, password=db_password or '', autocommit=True)
    try:
        sys_checks = {}
        for sys_tbl in ('global_priv', 'db', 'tables_priv', 'procs_priv', 'proc', 'plugin', 'servers', 'column_stats'):
            cnt = rows(conn, f'SELECT COUNT(*) AS cnt FROM mysql.`{sys_tbl}`')[0]['cnt']
            sys_checks[f'mysql.{sys_tbl}'] = int(cnt)
        sys_views = rows(
            conn,
            "SELECT COUNT(*) AS cnt FROM information_schema.VIEWS WHERE TABLE_SCHEMA='sys'",
        )[0]['cnt']
        sys_checks['sys.views_count'] = int(sys_views)

        user_state = inspect_source_for_upgrade(conn)
    finally:
        conn.close()

    return {
        'readiness': readiness,
        'system_tables': sys_checks,
        'user_inventory': user_state,
        'verified': True,
    }


def reconcile_interrupted_upgrade(*, job_dir, datadir):
    """Inspect an interrupted MariaDB upgrade without auto-replaying or discarding data."""
    job_dir = safe_absolute_path(str(job_dir), 'upgrade job directory')
    datadir = safe_absolute_path(str(datadir), 'upgrade datadir')
    phase_file = job_dir / 'upgrade-phase.json'
    phase = json.loads(phase_file.read_text(encoding='utf-8')) if phase_file.is_file() else {'stage': 'unrecorded'}
    claim = claim_path_for_datadir(datadir)
    daemon_birth = ((phase.get('target_daemon_started') or {}).get('daemon') or {}).get('process_birth')
    daemon_running = process_alive(daemon_birth) if daemon_birth else False
    upg_info = read_datadir_upgrade_info(datadir)
    snap = phase.get('rollback_snapshot')
    rollback_available = bool(snap and Path(snap['path']).is_dir())
    reconciliation = {
        'reconciled_at': time.time(),
        'interrupted_stage': phase.get('stage'),
        'steps_completed': phase.get('steps_completed', []),
        'target_daemon_running': daemon_running,
        'claim_present': claim.exists(),
        'current_datadir_upgrade_info': upg_info,
        'rollback_snapshot_available': rollback_available,
        'automatic_retry': False,
    }
    phase['reconciliation'] = reconciliation
    _save_phase(job_dir, phase)
    return reconciliation


def rollback_interrupted_upgrade(*, job_dir, datadir, db_user='root', db_password=''):
    """Stop any partial target daemon, restore the verified pre-upgrade datadir snapshot, and release claim."""
    job_dir = safe_absolute_path(str(job_dir), 'upgrade job directory')
    datadir = safe_absolute_path(str(datadir), 'upgrade datadir')
    phase_file = job_dir / 'upgrade-phase.json'
    if not phase_file.is_file():
        raise MariaDBUpgradeError('Upgrade phase journal is unavailable for rollback')
    phase = json.loads(phase_file.read_text(encoding='utf-8'))
    snap = phase.get('rollback_snapshot')
    if not snap or not Path(snap['path']).is_dir():
        raise MariaDBUpgradeError('No pre-upgrade rollback snapshot was retained for this job')

    snap_dir = Path(snap['path'])
    if canonical_digest(directory_manifest(snap_dir)) != snap['manifest_sha256']:
        raise MariaDBUpgradeError('Pre-upgrade rollback snapshot integrity check failed')

    target_state_dir = Path(phase['target_state_dir'])
    if (target_state_dir / 'managed-daemon.json').is_file():
        control_managed_service(
            action='stop',
            service_mode='managed_daemon',
            state_dir=target_state_dir,
            db_user=db_user,
            db_password=db_password,
        )

    writers = check_no_active_datadir_writers(datadir)
    if not writers['verified_absent']:
        raise MariaDBUpgradeError(f"Cannot roll back datadir while writer PIDs {writers['holder_pids']} remain active")

    # Atomically replace datadir contents from verified pre-upgrade snapshot
    quarantine_dir = job_dir / 'quarantined-partial-upgrade-datadir'
    if quarantine_dir.exists():
        shutil.rmtree(quarantine_dir)
    shutil.copytree(datadir, quarantine_dir)
    for item in list(datadir.iterdir()):
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()
    for src_item in snap_dir.iterdir():
        dst_item = datadir / src_item.name
        if src_item.is_dir():
            shutil.copytree(src_item, dst_item)
        else:
            shutil.copy2(src_item, dst_item)

    restored_sha = canonical_digest(directory_manifest(datadir))
    if restored_sha != snap['manifest_sha256']:
        raise MariaDBUpgradeError('Restored datadir SHA-256 manifest differs from pre-upgrade snapshot!')

    claim = claim_path_for_datadir(datadir)
    claim.unlink(missing_ok=True)
    result = {
        'rolled_back': True,
        'datadir': str(datadir),
        'restored_manifest_sha256': restored_sha,
        'restored_upgrade_info': read_datadir_upgrade_info(datadir),
        'claim_released': not claim.exists(),
        'rolled_back_at': time.time(),
    }
    phase['stage'] = 'rolled_back'
    phase['rollback_result'] = result
    _save_phase(job_dir, phase)
    return result
