"""Native MariaDB host configuration, validation, datadir initialization & service control.

Implements MA-AUDIT-HOST-CONFIG-SERVICE:
- Option-file (my.cnf / 50-server.cnf / !include / !includedir) graph inspection
- Native non-starting validation via `mariadbd --defaults-file=... --help --verbose`
- Reviewed atomic option-file backup, deployment & rollback
- Datadir initialization via `mariadb-install-db` (never calling `--version` on it!)
- Managed daemon / OS-service (systemd, sysv, or supervised daemon) start/stop/restart/boot-policy
- Independent SQL readiness verification separate from process/service state
"""
from copy import deepcopy
import glob
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid

from ...operations.fileio import durable_replace, private_directory, private_file
from .mariadb_physical import (
    MariaDBPhysicalError,
    _proc_birth,
    _short_unix_socket_base,
    admit_executable,
    canonical_digest,
    execution_host_identity,
    file_sha256,
    mariadb_bool,
    process_alive,
    rows,
    safe_absolute_path,
)


class MariaDBHostError(MariaDBPhysicalError):
    """Refusal or error during MariaDB host configuration or service management."""


SECRET_OPTION_KEYS = frozenset({
    'password', 'pass', 'ssl_key_password', 'wsrep_sst_auth',
    'master_password', 'report_password',
})


def _file_metadata(path):
    p = Path(path)
    st = p.lstat()
    if stat.S_ISLNK(st.st_mode):
        resolved = p.resolve(strict=True)
        rst = resolved.stat()
    else:
        resolved = p.resolve(strict=True)
        rst = st
    if not stat.S_ISREG(rst.st_mode):
        raise MariaDBHostError(f'Option file is not a regular file: {p}')
    return {
        'path': str(p),
        'resolved_path': str(resolved),
        'device': rst.st_dev,
        'inode': rst.st_ino,
        'mode': oct(stat.S_IMODE(rst.st_mode)),
        'mode_int': stat.S_IMODE(rst.st_mode),
        'uid': rst.st_uid,
        'gid': rst.st_gid,
        'bytes': rst.st_size,
        'sha256': file_sha256(resolved),
    }


def _parse_cnf_file(path):
    """Parse MariaDB option file sections, key-values (redacting secrets), and !include directives."""
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    sections = {}
    includes = []
    includedirs = []
    current_section = 'GLOBAL'
    base_dir = Path(path).resolve(strict=False).parent

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or line.startswith(';'):
            continue
        lower = line.lower()
        if lower.startswith('!includedir '):
            inc_dir = line[len('!includedir '):].strip()
            resolved_dir = (Path(inc_dir) if Path(inc_dir).is_absolute() else (base_dir / inc_dir)).resolve(strict=False)
            includedirs.append(str(resolved_dir))
            continue
        if lower.startswith('!include '):
            inc_file = line[len('!include '):].strip()
            resolved_file = (Path(inc_file) if Path(inc_file).is_absolute() else (base_dir / inc_file)).resolve(strict=False)
            includes.append(str(resolved_file))
            continue
        if line.startswith('[') and line.endswith(']'):
            current_section = line[1:-1].strip()
            sections.setdefault(current_section, {})
            continue
        if '=' in line:
            k, _, v = line.partition('=')
            key_norm = k.strip().lower().replace('-', '_')
            val_clean = v.strip()
            if key_norm in SECRET_OPTION_KEYS or 'password' in key_norm:
                val_clean = '<redacted>'
            sections.setdefault(current_section, {})[k.strip()] = val_clean
        else:
            sections.setdefault(current_section, {})[line] = True

    return {
        'sections': sections,
        'includes': includes,
        'includedirs': includedirs,
    }


def inspect_option_file_graph(root_config_path):
    """Recursively inspect a MariaDB option file (`my.cnf` / `50-server.cnf`) and its include graph."""
    root_path = safe_absolute_path(str(root_config_path), 'configuration file')
    if not root_path.exists():
        raise MariaDBHostError(f'MariaDB option file does not exist: {root_path}')

    visited = set()
    files_out = []
    effective_server_options = {}

    def _walk(file_path):
        meta = _file_metadata(file_path)
        real = meta['resolved_path']
        if real in visited:
            return
        visited.add(real)
        parsed = _parse_cnf_file(real)
        for sec_name in ('server', 'mysqld', 'mariadbd', 'mariadb', 'galera'):
            for k, v in (parsed['sections'].get(sec_name) or {}).items():
                effective_server_options[k.lower().replace('-', '_')] = v
        files_out.append({
            **meta,
            'sections': parsed['sections'],
            'includes': parsed['includes'],
            'includedirs': parsed['includedirs'],
        })
        for inc in parsed['includes']:
            if Path(inc).exists():
                _walk(inc)
        for inc_dir in parsed['includedirs']:
            d = Path(inc_dir)
            if d.is_dir():
                for child in sorted(glob.glob(str(d / '*.cnf'))):
                    if Path(child).is_file():
                        _walk(child)

    _walk(root_path)
    return {
        'root_file': str(root_path),
        'files': files_out,
        'file_count': len(files_out),
        'effective_server_options': effective_server_options,
        'graph_digest': canonical_digest([
            {'resolved_path': f['resolved_path'], 'sha256': f['sha256'], 'mode': f['mode']}
            for f in files_out
        ]),
        'execution_host': execution_host_identity(),
    }


def validate_option_file_natively(mariadbd_binary, defaults_file_path, *, basedir=None, lc_messages_dir=None, version_prefix=None, timeout_seconds=30):
    """Validate a MariaDB option file via `mariadbd --defaults-file=... --help --verbose` without starting the server."""
    daemon = admit_executable(mariadbd_binary, 'mariadbd', version_prefix=version_prefix)
    cfg_path = safe_absolute_path(str(defaults_file_path), 'defaults file')
    if not cfg_path.is_file():
        raise MariaDBHostError(f'Defaults file to validate does not exist: {cfg_path}')

    with tempfile.TemporaryDirectory(prefix='sr-mcfg-val-') as isolated_tmp:
        # --defaults-file MUST be the first argument immediately after mariadbd!
        cmd = [
            daemon['path'],
            f'--defaults-file={cfg_path}',
        ]
        if basedir:
            cmd.append(f'--basedir={safe_absolute_path(str(basedir), "basedir")}')
        if lc_messages_dir:
            cmd.append(f'--lc-messages-dir={safe_absolute_path(str(lc_messages_dir), "lc_messages_dir")}')
        cmd.extend(['--help', '--verbose'])

        proc = subprocess.run(
            cmd,
            cwd=isolated_tmp,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'PATH': os.defpath, 'TMPDIR': isolated_tmp},
            check=False,
        )

    resolved_vars = {}
    in_vars_table = False
    for line in (proc.stdout or '').splitlines():
        if line.startswith('Variables (--variable-name=value)'):
            in_vars_table = True
            continue
        if in_vars_table:
            if line.startswith('---') or not line.strip():
                continue
            parts = line.split(None, 1)
            if len(parts) == 2 and re.fullmatch(r'[a-z0-9_-]+', parts[0]):
                resolved_vars[parts[0]] = parts[1].strip()

    stderr_lines = [
        ln.strip() for ln in (proc.stderr or '').splitlines()
        if ln.strip() and 'io_uring_queue_init' not in ln and 'falling back to libaio' not in ln
    ]
    valid = proc.returncode == 0
    return {
        'valid': valid,
        'return_code': proc.returncode,
        'server_started': False,
        'defaults_file': str(cfg_path),
        'defaults_file_sha256': file_sha256(cfg_path),
        'mariadbd': daemon,
        'diagnostics': stderr_lines[:25],
        'resolved_variables_sample': {
            k: resolved_vars[k]
            for k in (
                'port', 'datadir', 'socket', 'pid-file', 'max-connections',
                'innodb-buffer-pool-size', 'log-bin', 'server-id', 'wsrep-on',
            )
            if k in resolved_vars
        },
        'resolved_variable_count': len(resolved_vars),
    }


def deploy_option_file_atomically(
    *, mariadbd_binary, target_config_path, replacement_text, job_dir,
    expected_original_sha256=None, basedir=None, lc_messages_dir=None,
    version_prefix=None,
):
    """Validate proposed option-file content natively, save an atomic 0600 backup, and os.replace atomically."""
    if not isinstance(replacement_text, str) or '\x00' in replacement_text or len(replacement_text.encode('utf-8')) > 524288:
        raise MariaDBHostError('Replacement option-file content must be bounded UTF-8 text without NUL bytes')
    target = safe_absolute_path(str(target_config_path), 'target option file')
    if not target.exists():
        raise MariaDBHostError(f'Target option file does not exist: {target}')
    job_dir = safe_absolute_path(str(job_dir), 'deployment job directory')
    job_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(job_dir)

    orig_meta = _file_metadata(target)
    resolved_target = Path(orig_meta['resolved_path'])
    if expected_original_sha256 and orig_meta['sha256'] != expected_original_sha256:
        raise MariaDBHostError('Original option file changed since review; atomic deployment refused')

    data = replacement_text.encode('utf-8')
    if not data.endswith(b'\n'):
        data += b'\n'

    # 1. Stage candidate and run native non-starting validation via mariadbd --help --verbose
    staged_candidate = job_dir / 'candidate-validation.cnf'
    with staged_candidate.open('wb') as f:
        private_file(staged_candidate)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

    validation = validate_option_file_natively(
        mariadbd_binary, staged_candidate,
        basedir=basedir, lc_messages_dir=lc_messages_dir, version_prefix=version_prefix,
    )
    if not validation['valid']:
        raise MariaDBHostError(
            'Native mariadbd option-file validation refused candidate configuration: '
            + '; '.join(validation['diagnostics'] or [f"rc={validation['return_code']}"])
        )

    # 2. Re-verify target inode & sha256 and write atomic 0600 backup
    current_meta = _file_metadata(resolved_target)
    if (current_meta['device'], current_meta['inode'], current_meta['sha256']) != (
        orig_meta['device'], orig_meta['inode'], orig_meta['sha256']
    ):
        raise MariaDBHostError('Concurrent modification detected on target option file before replacement')

    original_bytes = resolved_target.read_bytes()
    backup_path = job_dir / 'original-option-file.backup'
    with backup_path.open('wb') as bf:
        os.fchmod(bf.fileno(), 0o600)
        private_file(backup_path)
        bf.write(original_bytes)
        bf.flush()
        os.fsync(bf.fileno())

    # 3. Atomic os.replace in target parent directory preserving permissions & ownership
    parent_fd = os.open(resolved_target.parent, os.O_RDONLY | os.O_DIRECTORY)
    tmp_name = f'.sr-mariadb-cnf-{uuid.uuid4().hex}.tmp'
    created = False
    try:
        out_fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent_fd)
        created = True
        with os.fdopen(out_fd, 'wb') as out_stream:
            out_stream.write(data)
            out_stream.flush()
            os.fsync(out_stream.fileno())
            if os.geteuid() == 0:
                os.fchown(out_stream.fileno(), orig_meta['uid'], orig_meta['gid'])
            os.fchmod(out_stream.fileno(), orig_meta['mode_int'])
        # Final CAS check immediately before replace
        pre_replace_meta = _file_metadata(resolved_target)
        if pre_replace_meta['sha256'] != orig_meta['sha256']:
            raise MariaDBHostError('Target option file changed immediately prior to atomic replace')
        os.replace(tmp_name, resolved_target.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        created = False
        os.fsync(parent_fd)
    finally:
        if created:
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except OSError:
                pass
        os.close(parent_fd)

    after_meta = _file_metadata(resolved_target)
    meta_record = {
        'target_path': str(resolved_target),
        'original_meta': orig_meta,
        'backup_path': str(backup_path),
        'backup_sha256': file_sha256(backup_path),
        'deployed_meta': after_meta,
        'validation': validation,
        'restart_issued': False,
        'sql_readiness_verified': False,
    }
    (job_dir / 'config-deployment.json').write_text(json.dumps(meta_record, indent=2, sort_keys=True) + '\n')
    return meta_record


def rollback_deployed_option_file(job_dir):
    """Atomically restore the backed-up original option file from a deployment job."""
    job_dir = safe_absolute_path(str(job_dir), 'deployment job directory')
    rec_path = job_dir / 'config-deployment.json'
    if not rec_path.is_file():
        raise MariaDBHostError('Configuration deployment receipt is unavailable for rollback')
    rec = json.loads(rec_path.read_text(encoding='utf-8'))
    backup_path = Path(rec['backup_path'])
    target = Path(rec['target_path'])
    if not backup_path.is_file() or file_sha256(backup_path) != rec['backup_sha256']:
        raise MariaDBHostError('Atomic option-file backup is missing or corrupted')
    data = backup_path.read_bytes()
    orig = rec['original_meta']

    parent_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    tmp_name = f'.sr-mariadb-rb-{uuid.uuid4().hex}.tmp'
    created = False
    try:
        out_fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent_fd)
        created = True
        with os.fdopen(out_fd, 'wb') as s:
            s.write(data)
            s.flush()
            os.fsync(s.fileno())
            if os.geteuid() == 0:
                os.fchown(s.fileno(), orig['uid'], orig['gid'])
            os.fchmod(s.fileno(), orig['mode_int'])
        os.replace(tmp_name, target.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        created = False
        os.fsync(parent_fd)
    finally:
        if created:
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except OSError:
                pass
        os.close(parent_fd)

    restored_meta = _file_metadata(target)
    return {
        'rolled_back': restored_meta['sha256'] == orig['sha256'],
        'target_path': str(target),
        'restored_sha256': restored_meta['sha256'],
        'restart_issued': False,
    }


def admit_install_db_script(install_db_binary, mariadbd_binary, *, version_prefix=None):
    """Safely admit `mariadb-install-db` via `--help` (NEVER `--version`!) alongside `mariadbd`."""
    daemon = admit_executable(mariadbd_binary, 'mariadbd', version_prefix=version_prefix)
    candidate = Path(install_db_binary)
    if not candidate.is_absolute():
        found = shutil.which(install_db_binary)
        if not found:
            raise MariaDBHostError('Native mariadb-install-db utility is unavailable')
        candidate = Path(found)
    resolved = candidate.resolve(strict=False)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise MariaDBHostError(f'mariadb-install-db is not executable: {resolved}')
    help_proc = subprocess.run(
        [str(resolved), '--no-defaults', '--help'],
        capture_output=True, text=True, timeout=15,
        env={
            'LANG': 'C.UTF-8',
            'LC_ALL': 'C.UTF-8',
            'PATH': os.pathsep.join([
                str(Path(daemon['path']).parent),
                str(resolved.parent),
                os.defpath,
            ]),
        },
        check=False,
    )
    combined = (help_proc.stdout or '') + (help_proc.stderr or '')
    if help_proc.returncode not in {0, 1} or '--datadir' not in combined or '--auth-root-authentication-method' not in combined:
        raise MariaDBHostError('mariadb-install-db --help check failed')
    return {
        'path': str(resolved),
        'executable_sha256': file_sha256(resolved),
        'companion_mariadbd': daemon,
        'execution_host': execution_host_identity(),
    }


def initialize_datadir(
    *, install_db_binary, mariadbd_binary, datadir, job_dir,
    auth_root_method='normal', daemon_user=None, basedir=None,
    skip_test_db=True, version_prefix=None, timeout_seconds=120,
):
    """Initialize a new empty MariaDB datadir using `mariadb-install-db`."""
    if auth_root_method not in {'normal', 'socket'}:
        raise MariaDBHostError("Select auth_root_method 'normal' or 'socket'")
    admitted = admit_install_db_script(install_db_binary, mariadbd_binary, version_prefix=version_prefix)
    datadir = safe_absolute_path(str(datadir), 'target datadir')
    job_dir = safe_absolute_path(str(job_dir), 'initialization job directory')
    if datadir.exists() and any(datadir.iterdir()):
        raise MariaDBHostError(f'Refusing to initialize non-empty MariaDB datadir: {datadir}')
    datadir.mkdir(parents=True, exist_ok=True, mode=0o700)
    job_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(job_dir)

    if os.geteuid() == 0 and daemon_user:
        pw = pwd.getpwnam(daemon_user)
        os.chown(datadir, pw.pw_uid, pw.pw_gid)

    cmd = [
        admitted['path'],
        '--no-defaults',
        f'--datadir={datadir}',
        f'--auth-root-authentication-method={auth_root_method}',
    ]
    if skip_test_db:
        cmd.append('--skip-test-db')
    if daemon_user:
        cmd.append(f'--user={daemon_user}')
    if basedir:
        bdir = safe_absolute_path(str(basedir), 'basedir')
        cmd.append(f'--basedir={bdir}')

    env = {
        'LANG': 'C.UTF-8',
        'LC_ALL': 'C.UTF-8',
        'PATH': os.pathsep.join([
            str(Path(admitted['companion_mariadbd']['path']).parent),
            str(Path(admitted['path']).parent),
            os.defpath,
        ]),
        'TMPDIR': str(job_dir),
    }
    proc = subprocess.run(
        cmd, cwd=str(job_dir), capture_output=True, text=True,
        timeout=timeout_seconds, env=env, check=False,
    )
    mysql_sys_dir = datadir / 'mysql'
    initialized_ok = proc.returncode == 0 and mysql_sys_dir.is_dir() and any(mysql_sys_dir.iterdir())
    if not initialized_ok:
        raise MariaDBHostError(
            f'mariadb-install-db failed (rc={proc.returncode}): {(proc.stderr or proc.stdout)[-800:]}'
        )
    return {
        'initialized': True,
        'datadir': str(datadir),
        'auth_root_method': auth_root_method,
        'skip_test_db': skip_test_db,
        'system_tables_present': True,
        'tool': admitted,
        'return_code': proc.returncode,
        'server_started': False,
        'sql_readiness_verified': False,
    }


def _short_daemon_socket_dir(state_dir):
    candidate = Path(state_dir) / 'run'
    if len(str(candidate / 'mariadbd.sock')) <= 96:
        candidate.mkdir(parents=True, exist_ok=True, mode=0o700)
        return candidate
    digest_tag = hashlib.sha256(str(Path(state_dir).resolve()).encode('utf-8')).hexdigest()[:12]
    short = _short_unix_socket_base() / f'sr-md-{digest_tag}'
    short.mkdir(parents=True, exist_ok=True, mode=0o700)
    return short


def control_managed_service(
    *, action, service_mode='managed_daemon', state_dir,
    mariadbd_binary=None, defaults_file=None, datadir=None,
    port=None, bind_address='127.0.0.1', daemon_user=None,
    basedir=None, plugin_dir=None, lc_messages_dir=None,
    extra_args=(), db_user='root', db_password='',
    systemd_unit='mariadb.service', boot_enabled=None,
    version_prefix=None, timeout_seconds=60,
):
    """Start, stop, restart, inspect, or set boot_policy on a MariaDB service / managed daemon."""
    if action not in {'status', 'start', 'stop', 'restart', 'set_boot_policy'}:
        raise MariaDBHostError(f'Unsupported MariaDB service control action: {action!r}')
    if service_mode not in {'managed_daemon', 'systemd', 'sysv'}:
        raise MariaDBHostError("Select service_mode 'managed_daemon', 'systemd', or 'sysv'")

    state_dir = safe_absolute_path(str(state_dir), 'managed service state_dir')
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(state_dir)
    manifest_file = state_dir / 'managed-daemon.json'
    boot_policy_file = state_dir / 'boot-policy.json'

    if service_mode == 'systemd':
        systemctl = shutil.which('systemctl')
        if not systemctl:
            raise MariaDBHostError('systemctl is unavailable on this host')
        if action == 'set_boot_policy':
            if type(boot_enabled) is not bool:
                raise MariaDBHostError('Supply boolean boot_enabled for set_boot_policy')
            verb = 'enable' if boot_enabled else 'disable'
            res = subprocess.run([systemctl, '--no-ask-password', verb, systemd_unit], capture_output=True, text=True, timeout=timeout_seconds, check=False)
            if res.returncode != 0:
                raise MariaDBHostError(f'systemctl {verb} failed: {res.stderr.strip()}')
        elif action in {'start', 'stop', 'restart'}:
            res = subprocess.run([systemctl, '--no-ask-password', action, systemd_unit], capture_output=True, text=True, timeout=timeout_seconds, check=False)
            if res.returncode != 0:
                raise MariaDBHostError(f'systemctl {action} failed: {res.stderr.strip()}')
        active = subprocess.run([systemctl, 'is-active', systemd_unit], capture_output=True, text=True, check=False)
        enabled = subprocess.run([systemctl, 'is-enabled', systemd_unit], capture_output=True, text=True, check=False)
        return {
            'service_mode': 'systemd',
            'unit': systemd_unit,
            'action': action,
            'active_state': active.stdout.strip(),
            'running': active.returncode == 0,
            'boot_policy': enabled.stdout.strip(),
            'sql_readiness_verified': False,
        }

    if service_mode == 'sysv':
        svc_bin = shutil.which('service')
        if not svc_bin:
            raise MariaDBHostError('sysv service utility is unavailable on this host')
        unit_name = systemd_unit.removesuffix('.service')
        if action in {'start', 'stop', 'restart'}:
            res = subprocess.run([svc_bin, unit_name, action], capture_output=True, text=True, timeout=timeout_seconds, check=False)
            if res.returncode != 0:
                raise MariaDBHostError(f'service {unit_name} {action} failed: {(res.stderr or res.stdout).strip()}')
        st = subprocess.run([svc_bin, unit_name, 'status'], capture_output=True, text=True, timeout=15, check=False)
        return {
            'service_mode': 'sysv',
            'service_name': unit_name,
            'action': action,
            'running': st.returncode == 0,
            'status_output': (st.stdout + st.stderr).strip()[:500],
            'sql_readiness_verified': False,
        }

    # managed_daemon mode: direct supervised mariadbd with PID birth & boot-policy persistence
    current = json.loads(manifest_file.read_text(encoding='utf-8')) if manifest_file.is_file() else {}
    boot_doc = json.loads(boot_policy_file.read_text(encoding='utf-8')) if boot_policy_file.is_file() else {'boot_enabled': False}

    if action == 'set_boot_policy':
        if type(boot_enabled) is not bool:
            raise MariaDBHostError('Supply boolean boot_enabled for set_boot_policy')
        boot_doc = {
            'boot_enabled': boot_enabled,
            'updated_at': time.time(),
            'defaults_file': str(defaults_file) if defaults_file else current.get('defaults_file'),
            'datadir': str(datadir) if datadir else current.get('datadir'),
        }
        boot_policy_file.write_text(json.dumps(boot_doc, indent=2, sort_keys=True) + '\n')
        return {
            'service_mode': 'managed_daemon',
            'action': 'set_boot_policy',
            'running': process_alive(current.get('process_birth')),
            'boot_policy': 'enabled' if boot_enabled else 'disabled',
            'boot_enabled': boot_enabled,
            'sql_readiness_verified': False,
        }

    def _stop_daemon(info):
        birth = info.get('process_birth')
        if not birth or not process_alive(birth):
            return True
        if info.get('port'):
            try:
                import mariadb
                conn = mariadb.connect(
                    host=info.get('bind_address', '127.0.0.1'),
                    port=int(info['port']),
                    user=db_user, password=db_password or '',
                    connect_timeout=3, autocommit=True,
                )
                try:
                    c = conn.cursor()
                    c.execute('SHUTDOWN')
                    c.close()
                finally:
                    conn.close()
            except Exception:
                pass
        deadline = time.monotonic() + min(timeout_seconds, 20)
        while process_alive(birth) and time.monotonic() < deadline:
            time.sleep(0.1)
        if process_alive(birth):
            try:
                os.kill(int(birth['pid']), signal.SIGTERM)
            except ProcessLookupError:
                pass
            grace = time.monotonic() + 8.0
            while process_alive(birth) and time.monotonic() < grace:
                time.sleep(0.1)
            if process_alive(birth):
                try:
                    os.kill(int(birth['pid']), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        if info.get('run_dir'):
            shutil.rmtree(info['run_dir'], ignore_errors=True)
        return not process_alive(birth)

    def _start_daemon():
        daemon = admit_executable(
            mariadbd_binary or current.get('mariadbd_binary') or 'mariadbd',
            'mariadbd', version_prefix=version_prefix,
        )
        ddir = safe_absolute_path(str(datadir or current.get('datadir')), 'daemon datadir')
        cfg = safe_absolute_path(str(defaults_file or current['defaults_file']), 'defaults_file') if (defaults_file or current.get('defaults_file')) else None
        listen_port = int(port if port is not None else current.get('port', 3306))
        run_dir = _short_daemon_socket_dir(state_dir)
        sock_path = run_dir / 'mariadbd.sock'
        pid_path = run_dir / 'mariadbd.pid'
        err_log = state_dir / 'mariadbd.err'
        tmp_dir = state_dir / 'tmpdir'
        tmp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        if os.geteuid() == 0 and daemon_user:
            pw = pwd.getpwnam(daemon_user)
            for p in (run_dir, tmp_dir, state_dir):
                os.chown(p, pw.pw_uid, pw.pw_gid)

        cmd = [daemon['path']]
        if cfg is not None:
            cmd.append(f'--defaults-file={cfg}')
        else:
            cmd.append('--no-defaults')
        cmd.extend([
            f'--datadir={ddir}',
            f'--tmpdir={tmp_dir}',
            f'--socket={sock_path}',
            f'--pid-file={pid_path}',
            f'--bind-address={bind_address}',
            f'--port={listen_port}',
            f'--log-error={err_log}',
        ])
        if basedir or current.get('basedir'):
            cmd.append(f"--basedir={safe_absolute_path(str(basedir or current['basedir']), 'basedir')}")
        if plugin_dir or current.get('plugin_dir'):
            cmd.append(f"--plugin-dir={safe_absolute_path(str(plugin_dir or current['plugin_dir']), 'plugin_dir')}")
        if lc_messages_dir or current.get('lc_messages_dir'):
            cmd.append(f"--lc-messages-dir={safe_absolute_path(str(lc_messages_dir or current['lc_messages_dir']), 'lc_messages_dir')}")
        if daemon_user:
            cmd.append(f'--user={daemon_user}')
        cmd.extend(str(a) for a in extra_args)

        proc = subprocess.Popen(
            cmd, cwd=str(state_dir),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        birth = _proc_birth(proc.pid)
        # Wait briefly to verify process did not immediately crash on startup
        wait_until = time.monotonic() + 1.2
        while time.monotonic() < wait_until:
            if proc.poll() is not None:
                tail = err_log.read_text(encoding='utf-8', errors='replace')[-1500:] if err_log.exists() else ''
                raise MariaDBHostError(f'Managed mariadbd exited on startup (rc={proc.returncode}): {tail}')
            time.sleep(0.1)
        record = {
            'mariadbd_binary': daemon['path'],
            'mariadbd_sha256': daemon['executable_sha256'],
            'tool_version': daemon['tool_version'],
            'defaults_file': str(cfg) if cfg else None,
            'datadir': str(ddir),
            'port': listen_port,
            'bind_address': bind_address,
            'socket_path': str(sock_path),
            'pid_path': str(pid_path),
            'run_dir': str(run_dir) if run_dir != state_dir / 'run' else None,
            'basedir': str(basedir or current.get('basedir')) if (basedir or current.get('basedir')) else None,
            'plugin_dir': str(plugin_dir or current.get('plugin_dir')) if (plugin_dir or current.get('plugin_dir')) else None,
            'lc_messages_dir': str(lc_messages_dir or current.get('lc_messages_dir')) if (lc_messages_dir or current.get('lc_messages_dir')) else None,
            'process_birth': birth,
            'started_at': time.time(),
        }
        manifest_file.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        return record

    if action == 'status':
        alive = process_alive(current.get('process_birth'))
        return {
            'service_mode': 'managed_daemon',
            'action': 'status',
            'running': alive,
            'daemon': current if current else None,
            'boot_policy': 'enabled' if boot_doc.get('boot_enabled') else 'disabled',
            'boot_enabled': bool(boot_doc.get('boot_enabled')),
            'sql_readiness_verified': False,
        }

    if action == 'stop':
        stopped = _stop_daemon(current)
        if not stopped:
            raise MariaDBHostError('Failed to confirm termination of managed mariadbd process')
        return {
            'service_mode': 'managed_daemon',
            'action': 'stop',
            'running': False,
            'process_termination_confirmed': True,
            'boot_policy': 'enabled' if boot_doc.get('boot_enabled') else 'disabled',
            'sql_readiness_verified': False,
        }

    if action == 'start':
        if process_alive(current.get('process_birth')):
            raise MariaDBHostError('Managed mariadbd is already running; use restart or stop first')
        started = _start_daemon()
        return {
            'service_mode': 'managed_daemon',
            'action': 'start',
            'running': process_alive(started['process_birth']),
            'daemon': started,
            'boot_policy': 'enabled' if boot_doc.get('boot_enabled') else 'disabled',
            'sql_readiness_verified': False,
        }

    if action == 'restart':
        if not _stop_daemon(current):
            raise MariaDBHostError('Failed to stop existing managed mariadbd during restart')
        started = _start_daemon()
        return {
            'service_mode': 'managed_daemon',
            'action': 'restart',
            'running': process_alive(started['process_birth']),
            'daemon': started,
            'boot_policy': 'enabled' if boot_doc.get('boot_enabled') else 'disabled',
            'sql_readiness_verified': False,
        }


def verify_sql_readiness(
    *, host='127.0.0.1', port=3306, socket_path=None,
    db_user='root', db_password='', expected_datadir=None,
    expected_server_uid=None, timeout_seconds=30,
):
    """Independently verify SQL wire readiness & identity on a MariaDB host daemon."""
    import mariadb

    deadline = time.monotonic() + timeout_seconds
    last_error = None
    conn = None
    while time.monotonic() < deadline:
        try:
            kwargs = {'user': db_user, 'password': db_password or '', 'connect_timeout': 3, 'autocommit': True}
            if socket_path:
                kwargs['unix_socket'] = str(socket_path)
            else:
                kwargs['host'] = host
                kwargs['port'] = int(port)
            conn = mariadb.connect(**kwargs)
            break
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)

    if conn is None:
        raise MariaDBHostError(f'Independent SQL readiness probe failed within {timeout_seconds}s: {last_error}')

    try:
        obs = rows(
            conn,
            'SELECT VERSION() AS version, @@server_uid AS server_uid, @@datadir AS datadir, '
            '@@port AS port, @@socket AS socket, @@read_only AS read_only, '
            '@@innodb_read_only AS innodb_read_only',
        )[0]
        cur = conn.cursor()
        cur.execute("SHOW GLOBAL STATUS LIKE 'Uptime'")
        uptime_row = cur.fetchone()
        cur.close()
    finally:
        conn.close()

    if 'MariaDB' not in str(obs['version']):
        raise MariaDBHostError('Readiness probe reached a non-MariaDB listener')
    if expected_datadir and Path(obs['datadir']).resolve(strict=False) != Path(expected_datadir).resolve(strict=False):
        raise MariaDBHostError(
            f"SQL readiness datadir mismatch: expected {expected_datadir}, observed {obs['datadir']}"
        )
    if expected_server_uid and obs['server_uid'] != expected_server_uid:
        raise MariaDBHostError(
            f"SQL readiness server_uid mismatch: expected {expected_server_uid}, observed {obs['server_uid']}"
        )

    return {
        'sql_readiness_verified': True,
        'version': obs['version'],
        'server_uid': obs['server_uid'],
        'datadir': obs['datadir'],
        'port': int(obs['port']),
        'socket': obs['socket'],
        'read_only': mariadb_bool(obs['read_only']),
        'innodb_read_only': mariadb_bool(obs['innodb_read_only']),
        'uptime_seconds': int(uptime_row[1]) if uptime_row else None,
        'observed_at': time.time(),
    }
