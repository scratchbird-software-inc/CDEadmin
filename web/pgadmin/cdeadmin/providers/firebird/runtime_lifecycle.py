"""Firebird 5.0.4 host runtime installation staging, daemon lifecycle and ODS migration.

Explicitly separates host binary/daemon lifecycle and cross-version ODS
migration from network maintenance acknowledgements.
"""
from collections.abc import Mapping
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time

from ...operations.fileio import exclusive_file_lock
from .host_runtime_grant import file_sha256, verify_same_host

REQUIRED_BINARIES = ('firebird', 'isql', 'gbak', 'nbackup', 'gfix', 'gstat', 'fb_lock_print')
_ODS_RE = re.compile(r'ODS version\s+(\d+)\.(\d+)', re.IGNORECASE)


def descriptor():
    return {
        'schema': 'scratchrobin.firebird.runtime-lifecycle-api@1',
        'engine_version': '5.0.4',
        'native_ods_version': '13.1',
        'supported_platforms': ['linux'],
        'platform_ownership': {
            'linux': 'qualified-owned-host',
            'windows': 'external-platform-team',
            'macos': 'external-platform-team',
        },
        'network_maintenance_upgrades_runtime': False,
        'requires_permissions': ['administer', 'maintenance_admin'],
        'actions': ['describe', 'inspect', 'inspect_ods', 'review', 'apply', 'get', 'list'],
        'operations': [
            'daemon_start', 'daemon_stop', 'daemon_restart',
            'stage_runtime_bundle', 'migrate_database',
        ],
        'migration_routes': ['gbak_backup_restore', 'ods13_minor_upgrade'],
    }


def _clean_env(runtime_root, lock_dir):
    env = {
        k: v for k, v in os.environ.items()
        if k not in {'ISC_PASSWORD', 'ISC_USER', 'ISC_DATABASE', 'ISC_ROLE'}
    }
    env.update(
        FIREBIRD=str(runtime_root),
        FIREBIRD_LOCK=str(lock_dir),
        LD_LIBRARY_PATH=str(Path(runtime_root) / 'lib'),
    )
    return env


def _tcp_reachable(host, port, timeout=0.5):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _owned_daemon_pid(runtime_root, pid_file):
    pfile = Path(pid_file)
    if not pfile.is_file() or pfile.is_symlink():
        return None
    try:
        pid = int(pfile.read_text(encoding='utf-8').strip())
    except (ValueError, OSError):
        return None
    if pid <= 1:
        return None
    exe_link = Path(f'/proc/{pid}/exe')
    try:
        resolved_exe = exe_link.resolve(strict=True)
    except OSError:
        return None
    expected_exe = (Path(runtime_root) / 'bin/firebird').resolve(strict=True)
    return pid if resolved_exe == expected_exe else None


def inspect_daemon_status(host_scope):
    daemon = host_scope.get('managed_daemon')
    if not daemon:
        return {'configured': False, 'running': False}
    pid = _owned_daemon_pid(host_scope['firebird_runtime_root'], daemon['pid_file'])
    reachable = _tcp_reachable(daemon['bind_host'], daemon['port'])
    return {
        'configured': True,
        'pid': pid,
        'running': pid is not None and reachable,
        'process_alive': pid is not None,
        'tcp_reachable': reachable,
        'bind_host': daemon['bind_host'],
        'port': daemon['port'],
    }


def _reap_and_check_alive(pid):
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass
    status_file = Path(f'/proc/{pid}/status')
    if not status_file.exists():
        return False
    try:
        for line in status_file.read_text(encoding='utf-8', errors='ignore').splitlines():
            if line.startswith('State:'):
                return '\tZ' not in line and ' Z ' not in line
    except OSError:
        return False
    return True


def stop_managed_daemon_process(host_scope):
    daemon = host_scope.get('managed_daemon')
    if not daemon:
        return {'ok': False, 'reason': 'No managed_daemon configured for this host runtime'}
    pid = _owned_daemon_pid(host_scope['firebird_runtime_root'], daemon['pid_file'])
    pfile = Path(daemon['pid_file'])
    if pid is None:
        if pfile.exists() and not pfile.is_symlink():
            pfile.unlink()
        return {'ok': True, 'was_running': False, 'stopped_pid': None}

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not _reap_and_check_alive(pid):
            break
        time.sleep(0.1)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        time.sleep(0.2)
        _reap_and_check_alive(pid)

    if pfile.exists() and not pfile.is_symlink():
        pfile.unlink()
    still_alive = _reap_and_check_alive(pid)
    return {
        'ok': not still_alive,
        'was_running': True,
        'stopped_pid': pid,
        'tcp_closed': not _tcp_reachable(daemon['bind_host'], daemon['port']),
    }


def start_managed_daemon_process(host_scope):
    daemon = host_scope.get('managed_daemon')
    if not daemon:
        return {'ok': False, 'reason': 'No managed_daemon configured for this host runtime'}
    existing_pid = _owned_daemon_pid(host_scope['firebird_runtime_root'], daemon['pid_file'])
    if existing_pid is not None and _tcp_reachable(daemon['bind_host'], daemon['port']):
        return {'ok': True, 'already_running': True, 'pid': existing_pid, 'port': daemon['port']}

    rt = Path(host_scope['firebird_runtime_root'])
    lock_dir = Path(host_scope['firebird_lock_directory'])
    lock_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(daemon['server_log'])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path = Path(daemon['pid_file'])
    pid_path.parent.mkdir(parents=True, exist_ok=True)

    env = _clean_env(rt, lock_dir)
    cmd = [
        str(rt / 'bin/firebird'), '-d',
        '-p', str(daemon['port']),
        '-e', str(rt),
        '-el', str(lock_dir),
        '-em', str(rt),
    ]
    with log_path.open('ab') as log_handle:
        proc = subprocess.Popen(
            cmd,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    pid_path.write_text(f'{proc.pid}\n', encoding='utf-8')
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        rc = proc.poll()
        if rc is not None:
            if pid_path.exists():
                pid_path.unlink()
            tail = log_path.read_bytes()[-500:].decode('utf-8', errors='replace') if log_path.is_file() else ''
            return {
                'ok': False,
                'reason': f'Firebird daemon exited immediately with code {rc}: {tail.strip()}',
            }
        if _tcp_reachable(daemon['bind_host'], daemon['port']):
            return {
                'ok': True,
                'already_running': False,
                'pid': proc.pid,
                'port': daemon['port'],
            }
        time.sleep(0.1)

    # Timed out waiting for TCP readiness; clean up launched process.
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    if pid_path.exists():
        pid_path.unlink()
    return {'ok': False, 'reason': 'Timed out waiting for Firebird daemon TCP listener readiness'}


def restart_managed_daemon_process(host_scope):
    stopped = stop_managed_daemon_process(host_scope)
    if not stopped.get('ok'):
        return {'ok': False, 'reason': 'Failed to stop existing Firebird daemon cleanly'}
    started = start_managed_daemon_process(host_scope)
    return {
        **started,
        'previous_pid': stopped.get('stopped_pid'),
    }


def inspect_runtime_environment(host_scope):
    rt = Path(host_scope['firebird_runtime_root'])
    binaries = {}
    for name in REQUIRED_BINARIES:
        bpath = rt / 'bin' / name
        present = bpath.is_file() and not bpath.is_symlink() and os.access(bpath, os.X_OK)
        binaries[name] = {
            'present': present,
            'sha256': file_sha256(bpath) if present else None,
        }
    fbclient = rt / 'lib/libfbclient.so.5.0.4'
    engine13 = rt / 'plugins/libEngine13.so'
    sec_db = rt / 'security5.fdb'
    return {
        'schema': 'scratchrobin.firebird.runtime-inventory@1',
        'runtime_root': str(rt),
        'engine_version': '5.0.4',
        'native_ods_version': '13.1',
        'platform': sys.platform,
        'platform_ownership': descriptor()['platform_ownership'],
        'network_maintenance_upgrades_runtime': False,
        'binaries': binaries,
        'client_library_sha256': file_sha256(fbclient) if fbclient.is_file() else None,
        'engine13_plugin_sha256': file_sha256(engine13) if engine13.is_file() else None,
        'security_database_present': sec_db.is_file(),
        'daemon_status': inspect_daemon_status(host_scope),
    }


def inspect_database_ods(host_scope, database_path):
    """Inspect physical database ODS version via Firebird gstat -h without SQL mutation."""
    rt = Path(host_scope['firebird_runtime_root'])
    db_file = Path(database_path)
    if not db_file.is_absolute() or db_file.is_symlink() or not db_file.is_file():
        raise ValueError('Database file for ODS inspection must be an existing canonical regular file')
    env = _clean_env(rt, host_scope['firebird_lock_directory'])
    proc = subprocess.run(
        [str(rt / 'bin/gstat'), '-h', str(db_file)],
        env=env, capture_output=True, text=True, timeout=15, check=False,
    )
    output = (proc.stdout or '') + '\n' + (proc.stderr or '')
    match = _ODS_RE.search(output)
    if match:
        major, minor = int(match.group(1)), int(match.group(2))
    else:
        # Fallback to raw Firebird page-0 header (hdr_ods_version at offset 18)
        header = db_file.read_bytes()[:128]
        if len(header) < 68 or header[0] != 1:
            raise ValueError('Unable to determine Firebird ODS version from header: ' + output[-300:].strip())
        raw_ver = int.from_bytes(header[18:20], 'little')
        major = raw_ver & 0x7FFF
        minor = int.from_bytes(header[64:66], 'little')

    if (major, minor) == (13, 1):
        compat = 'current_native_5_0'
        recommended_route = None
    elif (major, minor) == (13, 0):
        compat = 'compatible_minor_upgrade_or_gbak'
        recommended_route = 'ods13_minor_upgrade'
    elif major < 13:
        compat = 'requires_gbak_backup_restore'
        recommended_route = 'gbak_backup_restore'
    else:
        compat = 'unsupported_newer_ods'
        recommended_route = None

    return {
        'database': str(db_file),
        'ods_major': major,
        'ods_minor': minor,
        'ods_text': f'{major}.{minor}',
        'compatibility': compat,
        'recommended_migration_route': recommended_route,
        'sha256': file_sha256(db_file),
    }


def _verify_migrated_database_subprocess(runtime_root, lock_dir, target_db):
    """Attach via Firebird 5.0.4 Engine13 in an isolated subprocess to read back ODS, schema and row counts."""
    script = (
        'import json, sys\n'
        'from pathlib import Path\n'
        'import firebird.driver as fb\n'
        'rt, dbp = Path(sys.argv[1]), Path(sys.argv[2])\n'
        'fb.driver_config.fb_client_library.value = str(rt / "lib/libfbclient.so.5.0.4")\n'
        'cfg = fb.driver_config.register_database("mig_verify")\n'
        'cfg.database.value = str(dbp)\n'
        'cfg.config.value = "ServerMode = SuperClassic\\nProviders = Engine13"\n'
        'con = fb.connect("mig_verify", user="SYSDBA", charset="UTF8")\n'
        'try:\n'
        '    cur = con.cursor()\n'
        '    cur.execute("SELECT RDB$GET_CONTEXT(\'SYSTEM\',\'ENGINE_VERSION\'), MON$ODS_MAJOR, MON$ODS_MINOR FROM MON$DATABASE")\n'
        '    ver, ods_maj, ods_min = cur.fetchone()\n'
        '    cur.execute("SELECT TRIM(TRAILING FROM RDB$RELATION_NAME), RDB$VIEW_BLR IS NOT NULL FROM RDB$RELATIONS WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0 ORDER BY 1")\n'
        '    rels = cur.fetchall()\n'
        '    tables, views, row_counts = [], [], {}\n'
        '    for rname, is_view in rels:\n'
        '        if is_view:\n'
        '            views.append(rname)\n'
        '        else:\n'
        '            tables.append(rname)\n'
        '            qname = \'"\' + rname.replace(\'"\', \'""\') + \'"\'\n'
        '            cur.execute(f"SELECT COUNT(*) FROM {qname}")\n'
        '            row_counts[rname] = int(cur.fetchone()[0])\n'
        '    cur.execute("SELECT TRIM(TRAILING FROM RDB$CONSTRAINT_NAME), TRIM(TRAILING FROM RDB$CONSTRAINT_TYPE) FROM RDB$RELATION_CONSTRAINTS WHERE RDB$CONSTRAINT_TYPE IN (\'PRIMARY KEY\', \'FOREIGN KEY\', \'UNIQUE\') ORDER BY 1")\n'
        '    constraints = [{"name": r[0], "type": r[1]} for r in cur.fetchall()]\n'
        '    cur.execute("SELECT TRIM(TRAILING FROM RDB$PROCEDURE_NAME) FROM RDB$PROCEDURES WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0 ORDER BY 1")\n'
        '    procedures = [r[0] for r in cur.fetchall()]\n'
        '    cur.execute("SELECT COUNT(*) FROM RDB$DEPENDENCIES")\n'
        '    dep_count = int(cur.fetchone()[0])\n'
        '    cur.close()\n'
        '    con.rollback()\n'
        'finally:\n'
        '    con.close()\n'
        'print(json.dumps({"ok": True, "engine_version": ver, "ods": [int(ods_maj), int(ods_min)], "tables": tables, "views": views, "row_counts": row_counts, "constraints": constraints, "procedures": procedures, "dependency_rows": dep_count}))\n'
    )
    env = _clean_env(runtime_root, lock_dir)
    proc = subprocess.run(
        [sys.executable, '-c', script, str(runtime_root), str(target_db)],
        env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError('Migrated database native verification failed: ' + (proc.stderr or proc.stdout)[-500:])
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith('{')]
    return json.loads(lines[-1])


def prepare_runtime_review(host_scope, request):
    if not isinstance(request, Mapping):
        raise ValueError('Runtime lifecycle review request must be an object')
    op = request.get('operation')
    if op not in {'daemon_start', 'daemon_stop', 'daemon_restart', 'stage_runtime_bundle', 'migrate_database'}:
        raise ValueError('Unknown runtime lifecycle operation')

    if op in {'daemon_start', 'daemon_stop', 'daemon_restart'}:
        if not host_scope.get('managed_daemon'):
            raise ValueError(f'{op} requires a managed_daemon grant on this host runtime')
        if op in {'daemon_stop', 'daemon_restart'} and request.get('disruption_confirmed') is not True:
            raise ValueError('Confirm service disruption before stopping or restarting the Firebird daemon')
        return {
            'scope': host_scope,
            'operation': op,
            'observed_daemon_before': inspect_daemon_status(host_scope),
        }

    if op == 'stage_runtime_bundle':
        staging_parent = host_scope.get('staging_directory')
        if not staging_parent:
            raise ValueError('stage_runtime_bundle requires an admitted staging_directory')
        target_name = request.get('target_directory_name', '')
        if not isinstance(target_name, str) or not re.fullmatch(r'[A-Za-z0-9_.\-]{1,64}', target_name):
            raise ValueError('target_directory_name must be a safe directory basename')
        dest = Path(staging_parent).resolve(strict=True) / target_name
        if dest.exists() or dest.is_symlink():
            raise ValueError('Target runtime bundle directory already exists; never overwrite an existing runtime')
        return {
            'scope': host_scope,
            'operation': op,
            'target_runtime_root': str(dest),
        }

    # migrate_database
    mig_route = request.get('migration_route')
    if mig_route not in {'gbak_backup_restore', 'ods13_minor_upgrade'}:
        raise ValueError('migration_route must be gbak_backup_restore or ods13_minor_upgrade')
    staging_dir = host_scope.get('staging_directory')
    if not staging_dir:
        raise ValueError('migrate_database requires an admitted staging_directory for source/target artifacts')
    sroot = Path(staging_dir).resolve(strict=True)
    src_path = Path(request.get('source_path', ''))
    dst_path = Path(request.get('target_database_path', ''))
    if not src_path.is_absolute() or '..' in src_path.parts or src_path.is_symlink() or not src_path.is_file():
        raise ValueError('source_path must be an existing canonical regular file')
    if not dst_path.is_absolute() or '..' in dst_path.parts or dst_path.exists() or dst_path.is_symlink():
        raise ValueError('target_database_path must be a non-existing canonical path (never overwrite in-place)')
    for candidate_p, label in ((src_path.resolve(strict=True), 'source_path'), (dst_path.parent.resolve(strict=True), 'target_database_path')):
        if candidate_p != sroot and sroot not in candidate_p.parents:
            raise ValueError(f'{label} must reside within the admitted staging/migration root')
    if request.get('confirmation') != dst_path.name:
        raise ValueError('Confirm the exact target database filename for migration cutover')

    source_sha = file_sha256(src_path)
    source_ods = None
    if mig_route == 'ods13_minor_upgrade':
        source_ods = inspect_database_ods(host_scope, str(src_path))
        if (source_ods['ods_major'], source_ods['ods_minor']) != (13, 0):
            raise ValueError(
                f"ods13_minor_upgrade admits only ODS 13.0 databases (observed ODS {source_ods['ods_text']}); "
                'use gbak_backup_restore for major cross-version ODS migration'
            )

    return {
        'scope': host_scope,
        'operation': op,
        'migration_route': mig_route,
        'source_path': str(src_path),
        'expected_source_sha256': source_sha,
        'source_ods': source_ods,
        'target_database_path': str(dst_path),
        'page_size': int(request.get('page_size', 8192)),
    }


def apply_runtime_operation(record):
    payload = record['payload']
    host_scope = payload['scope']
    verify_same_host(host_scope)
    rt = Path(host_scope['firebird_runtime_root'])
    op = payload['operation']

    if op == 'daemon_start':
        res = start_managed_daemon_process(host_scope)
        return {
            'state': 'started' if res.get('ok') else 'failed',
            'native_dispatched': True,
            **res,
        }
    if op == 'daemon_stop':
        res = stop_managed_daemon_process(host_scope)
        return {
            'state': 'stopped' if res.get('ok') else 'failed',
            'native_dispatched': True,
            **res,
        }
    if op == 'daemon_restart':
        res = restart_managed_daemon_process(host_scope)
        return {
            'state': 'restarted' if res.get('ok') else 'failed',
            'native_dispatched': True,
            **res,
        }

    if op == 'stage_runtime_bundle':
        dest = Path(payload['target_runtime_root'])
        if dest.exists() or dest.is_symlink():
            return {'state': 'rejected', 'native_dispatched': False, 'reason': 'Target directory already exists'}
        dest.mkdir(parents=True, exist_ok=False)
        for sub in ('bin', 'lib', 'plugins', 'intl', 'tzdata'):
            src_sub = rt / sub
            if src_sub.is_dir():
                shutil.copytree(src_sub, dest / sub, symlinks=True)
        for msg_file in rt.glob('*.msg'):
            shutil.copy2(msg_file, dest / msg_file.name)
        for conf_name in ('plugins.conf', 'fbtrace.conf', 'replication.conf'):
            src_c = rt / conf_name
            if src_c.is_file():
                shutil.copy2(src_c, dest / conf_name)
        if (rt / 'security5.fdb').is_file():
            shutil.copy2(rt / 'security5.fdb', dest / 'security5.fdb')
        (dest / 'lock').mkdir(mode=0o700, exist_ok=True)
        (dest / 'databases.conf').write_text('# Staged Firebird 5.0.4 databases.conf\n', encoding='utf-8')
        (dest / 'firebird.conf').write_text(
            'ServerMode = SuperClassic\nProviders = Remote,Engine13\n'
            f'SecurityDatabase = {dest / "security5.fdb"}\n',
            encoding='utf-8',
        )
        return {
            'state': 'staged',
            'native_dispatched': True,
            'target_runtime_root': str(dest),
            'engine_version': '5.0.4',
            'client_library_sha256': file_sha256(dest / 'lib/libfbclient.so.5.0.4'),
            'engine13_sha256': file_sha256(dest / 'plugins/libEngine13.so'),
        }

    # migrate_database
    src_path = Path(payload['source_path'])
    dst_path = Path(payload['target_database_path'])
    if not src_path.is_file() or file_sha256(src_path) != payload['expected_source_sha256']:
        return {
            'state': 'rejected',
            'native_dispatched': False,
            'reason': 'Migration source artifact changed since review',
        }
    if dst_path.exists() or dst_path.is_symlink():
        return {
            'state': 'rejected',
            'native_dispatched': False,
            'reason': 'Migration target path already exists; refusing to overwrite',
        }

    env = _clean_env(rt, host_scope['firebird_lock_directory'])
    Path(host_scope['firebird_lock_directory']).mkdir(parents=True, exist_ok=True)
    mig_route = payload['migration_route']

    if mig_route == 'gbak_backup_restore':
        page_size = payload.get('page_size', 8192)
        if page_size not in {4096, 8192, 16384, 32768}:
            return {'state': 'rejected', 'native_dispatched': False, 'reason': 'Unsupported Firebird 5 page_size'}
        proc = subprocess.run(
            [
                str(rt / 'bin/gbak'), '-c',
                '-p', str(page_size),
                '-user', 'SYSDBA',
                str(src_path), str(dst_path),
            ],
            env=env, capture_output=True, text=True, timeout=60, check=False,
        )
        if proc.returncode != 0:
            return {
                'state': 'failed',
                'native_dispatched': True,
                'partial_target_exists': dst_path.exists(),
                'reason': (proc.stderr or proc.stdout)[-500:].strip(),
            }
    else:
        # ods13_minor_upgrade: copy source to target (preserving original untouched!), then upgrade_database via Engine13 Services
        shutil.copy2(src_path, dst_path)
        os.chmod(dst_path, 0o600)
        upg_script = (
            'import sys\n'
            'from pathlib import Path\n'
            'import firebird.driver as fb\n'
            'rt, dbp = Path(sys.argv[1]), Path(sys.argv[2])\n'
            'fb.driver_config.fb_client_library.value = str(rt / "lib/libfbclient.so.5.0.4")\n'
            'srv_cfg = fb.driver_config.register_server("mig_upg_srv")\n'
            'srv_cfg.config.value = "ServerMode = SuperClassic\\nProviders = Engine13"\n'
            'with fb.connect_server("mig_upg_srv", user="SYSDBA") as srv:\n'
            '    srv.database.repair(database=str(dbp), flags=fb.SrvRepairFlag.UPGRADE_DB)\n'
        )
        proc = subprocess.run(
            [sys.executable, '-c', upg_script, str(rt), str(dst_path)],
            env=env, capture_output=True, text=True, timeout=60, check=False,
        )
        if proc.returncode != 0:
            return {
                'state': 'failed',
                'native_dispatched': True,
                'partial_target_exists': dst_path.exists(),
                'source_preserved_unchanged': file_sha256(src_path) == payload['expected_source_sha256'],
                'reason': (proc.stderr or proc.stdout)[-500:].strip(),
            }

    verification = _verify_migrated_database_subprocess(rt, host_scope['firebird_lock_directory'], dst_path)
    if verification.get('ods') != [13, 1] or verification.get('engine_version') != '5.0.4':
        raise RuntimeError(f'Unexpected post-migration ODS/version: {verification}')

    return {
        'state': 'migrated',
        'native_dispatched': True,
        'migration_route': mig_route,
        'source_path': str(src_path),
        'source_preserved_unchanged': file_sha256(src_path) == payload['expected_source_sha256'],
        'target_database_path': str(dst_path),
        'target_sha256': file_sha256(dst_path),
        'verified_ods': verification['ods'],
        'verified_engine_version': verification['engine_version'],
        'verified_tables': verification['tables'],
        'verified_views': verification['views'],
        'verified_row_counts': verification['row_counts'],
        'verified_constraints': verification['constraints'],
        'verified_procedures': verification['procedures'],
        'verified_dependency_rows': verification['dependency_rows'],
        'registration_cutover_automatic': False,
        'reconnection_guidance': (
            'Target database is verified on ODS 13.1. Register or clone/move '
            'the database target explicitly after human review.'
        ),
    }
