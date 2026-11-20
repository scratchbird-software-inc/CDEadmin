"""Native MariaDB physical backup, immutable incremental prepare, isolated recovery & cutover.

Implements MA-AUDIT-PHYSICAL-BACKUP, MA-AUDIT-INCREMENTAL-PREPARE, and
MA-AUDIT-RECOVERY-CUTOVER over native mariadb-backup, mariadbd, mariadb-binlog,
and mariadb utilities with explicit execution-host/tool/version admission,
private 0600 credential files, bounded supervision & cancellation, immutable
staging, independent recovery verification, and one-use production cutover.
"""
from copy import deepcopy
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
import threading
import time
import uuid

from ...operations.fileio import durable_replace, private_directory, private_file
from .mariadb_binlog_replay import gtids, inventory


class MariaDBPhysicalError(ValueError):
    """Refusal or execution error in native MariaDB physical continuity workflows."""


def mariadb_bool(value):
    """Normalize MariaDB boolean system/status variables (0/1, OFF/ON, NO/YES, False/True)."""
    if isinstance(value, str):
        return value.strip().upper() in {'1', 'ON', 'YES', 'TRUE'}
    return bool(value)


def rows(connection, source, parameters=()):
    """Execute SQL and return dict rows across MariaDB Connector/Python, PyMySQL, or DBAPI connections."""
    try:
        cursor = connection.cursor(dictionary=True)
    except TypeError:
        cursor = connection.cursor()
    try:
        if parameters:
            cursor.execute(source, parameters)
        else:
            cursor.execute(source)
        if not cursor.description:
            return []
        fetched = cursor.fetchall()
        if not fetched:
            return []
        if isinstance(fetched[0], dict):
            return list(fetched)
        cols = [col[0] for col in cursor.description]
        return [dict(zip(cols, item)) for item in fetched]
    finally:
        cursor.close()


MAX_FILES = 200000
MAX_OUTPUT = 256 * 1024
ADMITTED_ENGINES = frozenset({
    'innodb', 'aria', 'myisam', 'csv', 'archive', 'blackhole',
    'mrg_myisam', 'memory', 'sequence',
})


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()


def safe_absolute_path(value, label='path'):
    if not isinstance(value, str) or not value.strip() or '\x00' in value or len(value) > 4096:
        raise MariaDBPhysicalError(f'Select a bounded absolute {label}')
    raw = Path(value)
    if not raw.is_absolute():
        raise MariaDBPhysicalError(f'{label} must be an absolute path')
    if raw.exists() and raw.is_symlink():
        raise MariaDBPhysicalError(f'{label} cannot be a symbolic link')
    resolved = raw.resolve(strict=False)
    if resolved in {Path('/'), Path.home().resolve(strict=False)}:
        raise MariaDBPhysicalError(f'{label} cannot target root or home directory')
    return resolved


def execution_host_identity():
    account = pwd.getpwuid(os.geteuid()).pw_name if hasattr(os, 'geteuid') else 'unknown'
    return {
        'kind': 'local_posix',
        'platform': sys.platform,
        'hostname': socket.gethostname(),
        'uid': os.geteuid() if hasattr(os, 'geteuid') else None,
        'gid': os.getegid() if hasattr(os, 'getegid') else None,
        'os_account': account,
    }


def admit_executable(executable_path, expected_kind, *, version_prefix='12.2.2'):
    """Verify native MariaDB utility path, SHA-256, and exact MariaDB release version."""
    if not isinstance(executable_path, str) or not executable_path.strip() or '\x00' in executable_path:
        raise MariaDBPhysicalError(f'Select the native {expected_kind} executable path')
    candidate = Path(executable_path)
    if not candidate.is_absolute():
        found = shutil.which(executable_path)
        if not found:
            raise MariaDBPhysicalError(f'Native {expected_kind} executable is unavailable')
        candidate = Path(found)
    resolved = candidate.resolve(strict=False)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise MariaDBPhysicalError(f'Native {expected_kind} executable is missing or not executable: {resolved}')
    proc = subprocess.run(
        [str(resolved), '--no-defaults', '--version'],
        capture_output=True, text=True, timeout=15,
        env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'PATH': os.defpath},
        check=False,
    )
    combined = ((proc.stdout or '') + ' ' + (proc.stderr or '')).strip()
    allowed_rc = {0, 1} if expected_kind == 'mariadb-upgrade' else {0}
    if proc.returncode not in allowed_rc or 'MariaDB' not in combined:
        raise MariaDBPhysicalError(f'Selected executable {resolved} did not report a valid MariaDB version')
    if version_prefix and not re.search(r'\b' + re.escape(version_prefix) + r'(?:[.-]|-MariaDB\b)', combined):
        raise MariaDBPhysicalError(
            f'Native {expected_kind} version mismatch: expected {version_prefix}, got {combined!r}'
        )
    version_match = re.search(r'(\d+\.\d+\.\d+-MariaDB[^\s,]*)', combined)
    tool_version = version_match.group(1) if version_match else combined
    return {
        'kind': expected_kind,
        'path': str(resolved),
        'executable_sha256': file_sha256(resolved),
        'tool_version': tool_version,
        'version_output': combined,
        'execution_host': execution_host_identity(),
    }


def write_private_defaults_file(directory, *, user, password='', host=None, port=None, socket_path=None, ssl=False):
    """Create a private 0600 MariaDB option file inside a 0700 job directory."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(directory)
    if '\x00' in (user or '') or '\x00' in (password or ''):
        raise MariaDBPhysicalError('MariaDB credential contains NUL bytes')
    def _esc(val):
        return (
            str(val).replace('\\', '\\\\').replace('"', '\\"')
            .replace('\n', '\\n').replace('\r', '\\r')
        )
    lines = ['[client]', f'user="{_esc(user)}"']
    if password:
        lines.append(f'password="{_esc(password)}"')
    if socket_path:
        lines.append('protocol=socket')
        lines.append(f'socket="{_esc(socket_path)}"')
    elif host:
        lines.append('protocol=tcp')
        lines.append(f'host="{_esc(host)}"')
        if port:
            lines.append(f'port={int(port)}')
    lines.append('ssl' if ssl else 'skip-ssl')
    fd, raw_name = tempfile.mkstemp(prefix='.sr-mariadb-auth-', suffix='.cnf', dir=str(directory))
    cnf_path = Path(raw_name)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        private_file(cnf_path)
        stream.write(('\n'.join(lines) + '\n').encode('utf-8'))
        stream.flush()
        os.fsync(stream.fileno())
    mode = stat.S_IMODE(cnf_path.lstat().st_mode)
    if mode != 0o600:
        cnf_path.unlink(missing_ok=True)
        raise MariaDBPhysicalError('Private 0600 defaults file mode verification failed')
    return cnf_path


def _proc_birth(pid):
    stat_path = Path(f'/proc/{pid}/stat')
    boot_path = Path('/proc/sys/kernel/random/boot_id')
    if not stat_path.exists():
        return {'pid': pid, 'observed': False}
    try:
        fields = stat_path.read_text().rpartition(')')[2].split()
        boot_id = boot_path.read_text().strip() if boot_path.exists() else None
        return {'pid': pid, 'start_ticks': fields[19], 'boot_id': boot_id, 'observed': True}
    except OSError:
        return {'pid': pid, 'observed': False}


def process_alive(birth_info):
    if not isinstance(birth_info, dict) or not birth_info.get('pid'):
        return False
    pid = int(birth_info['pid'])
    stat_path = Path(f'/proc/{pid}/stat')
    if not stat_path.exists():
        return False
    try:
        boot_path = Path('/proc/sys/kernel/random/boot_id')
        if birth_info.get('boot_id') and boot_path.exists():
            if boot_path.read_text().strip() != birth_info['boot_id']:
                return False
        fields = stat_path.read_text().rpartition(')')[2].split()
        if birth_info.get('start_ticks') and fields[19] != birth_info['start_ticks']:
            return False
        return fields[0] not in {'Z', 'X'}
    except OSError:
        return False


def run_supervised_process(
    executable_path, arguments, workspace, *,
    timeout_seconds=3600, cancel=None, defaults_file=None,
    redact_values=(), input_path=None, extra_env=None,
):
    """Run one native MariaDB binary with bounded output, cancellation & credential cleanup."""
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(workspace)
    cmd = [str(executable_path)]
    if defaults_file is not None:
        cmd.append(f'--defaults-file={defaults_file}')
    cmd.extend(str(a) for a in arguments)

    env = {
        'LANG': 'C.UTF-8',
        'LC_ALL': 'C.UTF-8',
        'PATH': os.pathsep.join([str(Path(executable_path).parent), os.defpath]),
        'HOME': str(workspace),
        'TMPDIR': str(workspace),
    }
    if extra_env:
        env.update(extra_env)

    stdout_buf = bytearray()
    stderr_buf = bytearray()
    stdout_truncated = False
    stderr_truncated = False
    stdin_handle = Path(input_path).open('rb') if input_path is not None else subprocess.DEVNULL
    proc = None
    birth = None
    timed_out = False
    cancelled = False
    started_at = time.time()

    def _reader(pipe, buf, mark_trunc):
        try:
            while True:
                chunk = pipe.read(16384)
                if not chunk:
                    break
                remaining = MAX_OUTPUT - len(buf)
                if remaining > 0:
                    buf.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    mark_trunc()
        finally:
            pipe.close()

    def _mark_out():
        nonlocal stdout_truncated
        stdout_truncated = True

    def _mark_err():
        nonlocal stderr_truncated
        stderr_truncated = True

    try:
        if cancel is not None and cancel.is_set():
            cancelled = True
            raise InterruptedError('Operation cancelled before native process dispatch')
        proc = subprocess.Popen(
            cmd,
            cwd=str(workspace),
            env=env,
            stdin=stdin_handle,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        birth = _proc_birth(proc.pid)
        t_out = threading.Thread(target=_reader, args=(proc.stdout, stdout_buf, _mark_out), daemon=True)
        t_err = threading.Thread(target=_reader, args=(proc.stderr, stderr_buf, _mark_err), daemon=True)
        t_out.start()
        t_err.start()

        deadline = time.monotonic() + timeout_seconds if timeout_seconds else None
        while proc.poll() is None:
            if cancel is not None and cancel.is_set():
                cancelled = True
                break
            if deadline is not None and time.monotonic() > deadline:
                timed_out = True
                break
            time.sleep(0.03)

        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            grace_end = time.monotonic() + 5.0
            while proc.poll() is None and time.monotonic() < grace_end:
                time.sleep(0.05)
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait(timeout=5)

        t_out.join(timeout=5)
        t_err.join(timeout=5)
        rc = proc.returncode
        termination_confirmed = proc.poll() is not None and not process_alive(birth)
    finally:
        if stdin_handle is not subprocess.DEVNULL:
            stdin_handle.close()
        credential_cleanup_confirmed = True
        if defaults_file is not None:
            try:
                Path(defaults_file).unlink(missing_ok=True)
                credential_cleanup_confirmed = not Path(defaults_file).exists()
            except OSError:
                credential_cleanup_confirmed = False

    def _redact(raw_bytes):
        text = raw_bytes.decode('utf-8', errors='replace')
        for secret in redact_values:
            if isinstance(secret, str) and secret:
                text = text.replace(secret, '<redacted>')
        if defaults_file is not None:
            text = text.replace(str(defaults_file), '<private-defaults-file>')
        return text

    return {
        'executable': str(executable_path),
        'executable_sha256': file_sha256(executable_path),
        'return_code': rc,
        'timed_out': timed_out,
        'cancel_requested': cancelled,
        'process_birth': birth,
        'process_termination_confirmed': termination_confirmed,
        'credential_cleanup_confirmed': credential_cleanup_confirmed,
        'started_at': started_at,
        'finished_at': time.time(),
        'stdout': _redact(stdout_buf),
        'stderr': _redact(stderr_buf),
        'stdout_truncated': stdout_truncated,
        'stderr_truncated': stderr_truncated,
        'execution_host': execution_host_identity(),
    }


def parse_kv_file(path):
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, sep, val = line.partition('=')
        if not sep:
            raise MariaDBPhysicalError(f'Malformed metadata line in {path.name}')
        k = key.strip()
        if k in result:
            raise MariaDBPhysicalError(f'Duplicate metadata field {k!r} in {path.name}')
        result[k] = val.strip()
    return result


def resolve_metadata_file(directory, modern_name, legacy_name, *, required=True):
    directory = Path(directory)
    modern = directory / modern_name
    legacy = directory / legacy_name
    if modern.is_file():
        return modern
    if legacy.is_file():
        return legacy
    if required:
        raise MariaDBPhysicalError(f'Missing native physical metadata file ({modern_name} / {legacy_name})')
    return None


def parse_binlog_info(directory, info_dict):
    """Extract binlog file, position, and MariaDB GTID from mariadb_backup_binlog_info or info."""
    binlog_path = resolve_metadata_file(
        directory, 'mariadb_backup_binlog_info', 'xtrabackup_binlog_info', required=False
    )
    binlog_file = binlog_pos = gtid_pos = None
    raw_text = None
    if binlog_path is not None:
        raw_text = binlog_path.read_text(encoding='utf-8', errors='replace').strip()
        if raw_text:
            parts = raw_text.splitlines()[0].split('\t')
            if len(parts) >= 2:
                binlog_file, binlog_pos = parts[0].strip(), parts[1].strip()
            if len(parts) >= 3:
                gtid_pos = parts[2].strip()
    if not binlog_file and info_dict.get('binlog_pos'):
        raw_info = info_dict['binlog_pos']
        m_file = re.search(r"filename\s+'([^']+)'", raw_info)
        m_pos = re.search(r"position\s+'([0-9]+)'", raw_info)
        m_gtid = re.search(r"GTID of the last change\s+'([^']*)'", raw_info)
        if m_file:
            binlog_file = m_file.group(1)
        if m_pos:
            binlog_pos = m_pos.group(1)
        if m_gtid:
            gtid_pos = m_gtid.group(1)
    if gtid_pos:
        gtids(gtid_pos)
    return {
        'raw': raw_text,
        'binlog_file': binlog_file,
        'binlog_position': binlog_pos,
        'gtid_pos': gtid_pos or '',
    }


def directory_manifest(directory):
    directory = safe_absolute_path(str(directory), 'artifact directory')
    if not directory.is_dir():
        raise MariaDBPhysicalError(f'Physical artifact directory does not exist: {directory}')
    files = []
    for root, dirs, names in os.walk(directory, followlinks=False):
        for d in dirs:
            if (Path(root) / d).is_symlink():
                raise MariaDBPhysicalError('Physical artifact cannot contain directory symlinks')
        for name in names:
            p = Path(root) / name
            st = p.lstat()
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                raise MariaDBPhysicalError(f'Physical artifact entry is not a regular file: {p.name}')
            digest = file_sha256(p)
            st2 = p.stat()
            if (st.st_ino, st.st_size, st.st_mtime_ns) != (st2.st_ino, st2.st_size, st2.st_mtime_ns):
                raise MariaDBPhysicalError(f'Physical artifact file changed during digesting: {p.name}')
            files.append({
                'path': p.relative_to(directory).as_posix(),
                'bytes': str(st2.st_size),
                'sha256': digest,
            })
            if len(files) > MAX_FILES:
                raise MariaDBPhysicalError('Physical artifact exceeds maximum file count')
    files.sort(key=lambda item: item['path'])
    return files


def inspect_backup_artifact(directory, *, expected_type=None):
    """Inspect & digest a MariaDB physical backup or prepared directory."""
    directory = safe_absolute_path(str(directory), 'physical backup artifact')
    cp_path = resolve_metadata_file(directory, 'mariadb_backup_checkpoints', 'xtrabackup_checkpoints')
    info_path = resolve_metadata_file(directory, 'mariadb_backup_info', 'xtrabackup_info')
    checkpoints = parse_kv_file(cp_path)
    info = parse_kv_file(info_path)

    btype = checkpoints.get('backup_type')
    if btype not in {'full-backuped', 'incremental', 'log-applied', 'full-prepared'}:
        raise MariaDBPhysicalError(f'Unsupported MariaDB physical backup_type: {btype!r}')
    if expected_type is not None:
        allowed = {expected_type} if isinstance(expected_type, str) else set(expected_type)
        if btype not in allowed:
            raise MariaDBPhysicalError(f'Expected backup_type in {sorted(allowed)}, observed {btype!r}')
    if info.get('partial') != 'N' or info.get('compressed') != 'N':
        raise MariaDBPhysicalError('Only complete, uncompressed MariaDB physical backups are admitted')
    for key in ('from_lsn', 'to_lsn', 'last_lsn'):
        if not re.fullmatch(r'[0-9]+', checkpoints.get(key, '')):
            raise MariaDBPhysicalError(f'Missing or non-numeric {key} in {cp_path.name}')
    from_lsn, to_lsn, last_lsn = (int(checkpoints[k]) for k in ('from_lsn', 'to_lsn', 'last_lsn'))
    if not (0 <= from_lsn <= to_lsn <= last_lsn):
        raise MariaDBPhysicalError(
            f'Invalid MariaDB checkpoint LSN order: from_lsn={from_lsn}, to_lsn={to_lsn}, last_lsn={last_lsn}'
        )
    if btype == 'full-backuped' and from_lsn != 0:
        raise MariaDBPhysicalError('Full MariaDB physical backup must start at from_lsn=0')
    binlog = parse_binlog_info(directory, info)
    files = directory_manifest(directory)
    manifest_sha256 = canonical_digest(files)
    return {
        'format': f'mariadb-backup-{btype}',
        'checkpoints_filename': cp_path.name,
        'info_filename': info_path.name,
        'checkpoints': checkpoints,
        'xtrabackup_checkpoints': checkpoints,
        'info': info,
        'xtrabackup_info': info,
        'backup_uuid': info.get('uuid'),
        'tool_version': info.get('tool_version'),
        'server_version': info.get('server_version'),
        'from_lsn': str(from_lsn),
        'to_lsn': str(to_lsn),
        'last_lsn': str(last_lsn),
        'binlog_info': binlog,
        'prepared': btype in {'log-applied', 'full-prepared'},
        'files': files,
        'file_count': len(files),
        'manifest_sha256': manifest_sha256,
        'total_bytes': str(sum(int(f['bytes']) for f in files)),
    }


def capture_source_state(connection):
    """Capture live MariaDB server identity, storage engines, encryption & datadir."""
    if rows(connection, 'SELECT @@in_transaction AS active')[0]['active']:
        raise MariaDBPhysicalError('Physical backup requires an idle MariaDB connection')
    connection.autocommit = True
    meta = rows(
        connection,
        'SELECT VERSION() AS version, @@server_uid AS server_uid, @@server_id AS server_id, '
        '@@datadir AS datadir, @@hostname AS hostname, @@port AS port, @@socket AS socket, '
        'CURRENT_USER() AS authenticated_principal, CURRENT_ROLE() AS active_role, '
        '@@global.log_bin AS log_bin, @@global.gtid_binlog_pos AS gtid_binlog_pos, '
        '@@global.gtid_current_pos AS gtid_current_pos, '
        '@@global.innodb_encrypt_tables AS innodb_encrypt_tables, '
        '@@global.innodb_encrypt_log AS innodb_encrypt_log, '
        '@@global.aria_encrypt_tables AS aria_encrypt_tables, '
        '@@global.encrypt_binlog AS encrypt_binlog',
    )[0]
    if 'MariaDB' not in str(meta['version']):
        raise MariaDBPhysicalError('Target server is not a native MariaDB instance')
    engines = rows(
        connection,
        "SELECT ENGINE AS engine, COUNT(*) AS table_count FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA NOT IN ('information_schema','performance_schema','sys') "
        "AND TABLE_TYPE='BASE TABLE' GROUP BY ENGINE ORDER BY ENGINE",
    )
    unsupported = [
        r['engine'] for r in engines
        if (r['engine'] or '').casefold() not in ADMITTED_ENGINES
    ]
    if unsupported:
        raise MariaDBPhysicalError(
            'Unsupported persistent storage engines for MariaDB physical backup: ' + ', '.join(map(str, unsupported))
        )
    encryption_flags = {
        'innodb_tables': str(meta['innodb_encrypt_tables']).upper() not in {'OFF', '0'},
        'innodb_log': bool(meta['innodb_encrypt_log']),
        'aria_tables': bool(meta['aria_encrypt_tables']),
        'binlog': bool(meta['encrypt_binlog']),
    }
    volatile_memory = rows(
        connection,
        "SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS table_name FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA NOT IN ('information_schema','performance_schema','sys') "
        "AND ENGINE='MEMORY' ORDER BY TABLE_SCHEMA, TABLE_NAME",
    )
    return {
        'identity': {
            'version': meta['version'],
            'clean_version': str(meta['version']).split('-')[0],
            'server_uid': meta['server_uid'],
            'server_id': int(meta['server_id']),
            'hostname': meta['hostname'],
            'datadir': str(Path(meta['datadir']).resolve(strict=False)),
            'port': int(meta['port']),
            'socket': meta['socket'],
            'authenticated_principal': meta['authenticated_principal'],
            'active_role': meta['active_role'],
        },
        'state': {
            'log_bin': bool(meta['log_bin']),
            'gtid_binlog_pos': meta['gtid_binlog_pos'] or '',
            'gtid_current_pos': meta['gtid_current_pos'] or '',
            'storage_engines': engines,
            'encryption': encryption_flags,
            'volatile_memory_tables': volatile_memory,
        },
    }


def validate_backup_chain(base_record, incremental_records=()):
    """Validate immutable full + incremental LSN & server_uid lineage and artifact digests."""
    base_art = (base_record.get('result') or {}).get('artifact')
    if not base_art or base_record.get('artifact_adoption_state') != 'artifact_adopted':
        raise MariaDBPhysicalError('Select an adopted, verified full MariaDB physical backup as chain root')
    base_dir = Path(base_record['artifact_dir'])
    live_base = inspect_backup_artifact(base_dir, expected_type='full-backuped')
    if live_base['manifest_sha256'] != base_art['manifest_sha256']:
        raise MariaDBPhysicalError('Immutable full base backup bytes changed on disk; prepare refused')

    source_uid = base_record['source']['server_uid']
    server_version = live_base['server_version']
    prev_to_lsn = int(live_base['to_lsn'])
    prev_last_lsn = int(live_base['last_lsn'])
    verified_incrementals = []

    for idx, inc_rec in enumerate(incremental_records):
        inc_art = (inc_rec.get('result') or {}).get('artifact')
        if not inc_art or inc_rec.get('artifact_adoption_state') != 'artifact_adopted':
            raise MariaDBPhysicalError(f'Incremental backup at position {idx + 1} is not verified/adopted')
        if inc_rec['source']['server_uid'] != source_uid:
            raise MariaDBPhysicalError(
                f'Incremental backup {inc_rec["job_id"]} belongs to a different MariaDB server_uid'
            )
        inc_dir = Path(inc_rec['artifact_dir'])
        live_inc = inspect_backup_artifact(inc_dir, expected_type='incremental')
        if live_inc['manifest_sha256'] != inc_art['manifest_sha256']:
            raise MariaDBPhysicalError(
                f'Immutable incremental backup {inc_rec["job_id"]} bytes changed on disk; prepare refused'
            )
        if live_inc['server_version'] != server_version:
            raise MariaDBPhysicalError('Incremental backup server_version differs from base backup')
        inc_from = int(live_inc['from_lsn'])
        inc_to = int(live_inc['to_lsn'])
        inc_last = int(live_inc['last_lsn'])
        if inc_from != prev_to_lsn:
            raise MariaDBPhysicalError(
                f'Broken LSN chain at incremental {inc_rec["job_id"]}: '
                f'from_lsn={inc_from} != parent.to_lsn={prev_to_lsn}'
            )
        if inc_last < prev_last_lsn:
            raise MariaDBPhysicalError(
                f'Incremental {inc_rec["job_id"]} last_lsn={inc_last} regressed below {prev_last_lsn}'
            )
        prev_to_lsn = inc_to
        prev_last_lsn = inc_last
        verified_incrementals.append({
            'job_id': inc_rec['job_id'],
            'artifact_dir': str(inc_dir),
            'manifest_sha256': live_inc['manifest_sha256'],
            'from_lsn': str(inc_from),
            'to_lsn': str(inc_to),
            'last_lsn': str(inc_last),
            'binlog_info': live_inc['binlog_info'],
        })

    return {
        'source_uid': source_uid,
        'server_version': server_version,
        'base': {
            'job_id': base_record['job_id'],
            'artifact_dir': str(base_dir),
            'manifest_sha256': live_base['manifest_sha256'],
            'from_lsn': live_base['from_lsn'],
            'to_lsn': live_base['to_lsn'],
            'last_lsn': live_base['last_lsn'],
            'binlog_info': live_base['binlog_info'],
        },
        'incrementals': verified_incrementals,
        'expected_final_to_lsn': str(prev_to_lsn),
        'expected_final_last_lsn': str(prev_last_lsn),
    }


def run_physical_backup(
    *, backup_binary, source_datadir, job_dir, db_user, db_password,
    host=None, port=None, socket_path=None, ssl=False,
    parallel=1, timeout_seconds=3600, cancel=None,
    incremental_basedir=None, incremental_lsn=None,
    version_prefix='12.2.2', on_dispatch=None, on_acknowledge=None,
):
    """Execute mariadb-backup --backup (full or incremental) with private 0600 credentials."""
    tool = admit_executable(backup_binary, 'mariadb-backup', version_prefix=version_prefix)
    source_datadir = safe_absolute_path(str(source_datadir), 'source datadir')
    job_dir = safe_absolute_path(str(job_dir), 'backup job directory')
    if job_dir.is_relative_to(source_datadir) or source_datadir.is_relative_to(job_dir):
        raise MariaDBPhysicalError('Backup workspace must be disjoint from the live MariaDB datadir')
    job_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(job_dir)
    target_dir = job_dir / 'artifact'
    if target_dir.exists():
        raise MariaDBPhysicalError('Target backup artifact directory already exists; no overwrite allowed')

    if incremental_basedir is not None and incremental_lsn is not None:
        raise MariaDBPhysicalError('Specify at most one of incremental_basedir or incremental_lsn')
    parent_manifest_before = None
    if incremental_basedir is not None:
        inc_base = safe_absolute_path(str(incremental_basedir), 'incremental basedir')
        parent_manifest_before = inspect_backup_artifact(inc_base)['manifest_sha256']

    cnf_path = write_private_defaults_file(
        job_dir, user=db_user, password=db_password,
        host=host, port=port, socket_path=socket_path, ssl=ssl,
    )
    args = [
        '--backup',
        f'--datadir={source_datadir}',
        f'--target-dir={target_dir}',
        f'--parallel={int(parallel)}',
    ]
    if incremental_basedir is not None:
        args.append(f'--incremental-basedir={incremental_basedir}')
    elif incremental_lsn is not None:
        if not re.fullmatch(r'[0-9]+', str(incremental_lsn)):
            cnf_path.unlink(missing_ok=True)
            raise MariaDBPhysicalError('incremental_lsn must be an unsigned decimal integer')
        args.append(f'--incremental-lsn={incremental_lsn}')

    if on_dispatch is not None:
        on_dispatch({'tool': tool, 'dispatched_at': time.time()})

    obs = run_supervised_process(
        tool['path'], args, job_dir,
        timeout_seconds=timeout_seconds, cancel=cancel,
        defaults_file=cnf_path, redact_values=(db_password,),
    )
    completed_ok = 'completed OK!' in (obs['stdout'] + '\n' + obs['stderr'])
    acknowledged = (
        obs['return_code'] == 0 and completed_ok
        and not obs['timed_out'] and not obs['cancel_requested']
    )
    if on_acknowledge is not None:
        on_acknowledge({
            'native_acknowledged': acknowledged,
            'completed_ok_marker': completed_ok,
            'observation': {k: v for k, v in obs.items() if k not in {'stdout', 'stderr'}},
        })
    if not acknowledged:
        err = MariaDBPhysicalError(
            'mariadb-backup did not complete cleanly '
            f"(rc={obs['return_code']}, cancelled={obs['cancel_requested']}, timed_out={obs['timed_out']})"
        )
        err.observation = obs
        raise err

    expected_type = 'incremental' if (incremental_basedir or incremental_lsn is not None) else 'full-backuped'
    artifact = inspect_backup_artifact(target_dir, expected_type=expected_type)
    if parent_manifest_before is not None:
        after_parent = inspect_backup_artifact(incremental_basedir)['manifest_sha256']
        if after_parent != parent_manifest_before:
            raise MariaDBPhysicalError('Parent backup directory was unexpectedly modified during incremental backup')
    return {
        'tool': tool,
        'process_observation': obs,
        'native_acknowledged': True,
        'completed_ok_marker': True,
        'artifact': artifact,
        'artifact_dir': str(target_dir),
    }


def _write_prepare_state(job_dir, state_payload):
    state_file = Path(job_dir) / 'prepare-state.json'
    tmp_file = Path(job_dir) / '.prepare-state.json.tmp'
    with tmp_file.open('w', encoding='utf-8') as stream:
        private_file(tmp_file)
        json.dump(state_payload, stream, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    durable_replace(tmp_file, state_file)


def run_staged_prepare(
    *, backup_binary, base_record, incremental_records, job_dir,
    memory_bytes=268435456, timeout_seconds=3600, cancel=None,
    version_prefix='12.2.2', simulate_interrupt_after_step=None,
):
    """Stage immutable full + incrementals onto a private working copy and run mariadb-backup --prepare."""
    tool = admit_executable(backup_binary, 'mariadb-backup', version_prefix=version_prefix)
    chain = validate_backup_chain(base_record, incremental_records)
    job_dir = safe_absolute_path(str(job_dir), 'prepare job directory')
    job_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(job_dir)

    working_copy = job_dir / 'working_copy'
    final_artifact = job_dir / 'artifact'
    if working_copy.exists() or final_artifact.exists():
        raise MariaDBPhysicalError('Prepare working or target directory already exists')

    state = {
        'stage': 'staging_base',
        'chain': chain,
        'steps_completed': [],
        'active_pid': None,
        'started_at': time.time(),
    }
    _write_prepare_state(job_dir, state)

    shutil.copytree(chain['base']['artifact_dir'], working_copy)
    state['steps_completed'].append('staging_base')
    state['stage'] = 'preparing_base'
    _write_prepare_state(job_dir, state)

    use_mem = f'--use-memory={int(memory_bytes)}'
    observations = []
    obs_base = run_supervised_process(
        tool['path'],
        ['--no-defaults', '--prepare', f'--target-dir={working_copy}', use_mem],
        job_dir, timeout_seconds=timeout_seconds, cancel=cancel,
    )
    observations.append(obs_base)
    if obs_base['return_code'] != 0 or 'completed OK!' not in (obs_base['stdout'] + '\n' + obs_base['stderr']):
        state['stage'] = 'interrupted_or_failed_base_prepare'
        state['last_observation'] = {k: v for k, v in obs_base.items() if k not in {'stdout', 'stderr'}}
        _write_prepare_state(job_dir, state)
        err = MariaDBPhysicalError('mariadb-backup --prepare failed on staged base copy')
        err.observation = obs_base
        raise err

    state['steps_completed'].append('preparing_base')
    _write_prepare_state(job_dir, state)

    if simulate_interrupt_after_step == 'preparing_base':
        state['stage'] = 'interrupted_after_preparing_base'
        _write_prepare_state(job_dir, state)
        raise InterruptedError('Simulated prepare interruption after base prepare')

    for idx, inc in enumerate(chain['incrementals']):
        step_name = f'applying_incremental_{idx}'
        state['stage'] = step_name
        _write_prepare_state(job_dir, state)
        inc_stage = job_dir / f'inc_stage_{idx}'
        shutil.copytree(inc['artifact_dir'], inc_stage)
        try:
            obs_inc = run_supervised_process(
                tool['path'],
                [
                    '--no-defaults', '--prepare',
                    f'--target-dir={working_copy}',
                    f'--incremental-dir={inc_stage}',
                    use_mem,
                ],
                job_dir, timeout_seconds=timeout_seconds, cancel=cancel,
            )
            observations.append(obs_inc)
            if obs_inc['return_code'] != 0 or 'completed OK!' not in (obs_inc['stdout'] + '\n' + obs_inc['stderr']):
                state['stage'] = f'interrupted_or_failed_{step_name}'
                state['last_observation'] = {k: v for k, v in obs_inc.items() if k not in {'stdout', 'stderr'}}
                _write_prepare_state(job_dir, state)
                err = MariaDBPhysicalError(f'mariadb-backup --prepare failed on incremental {inc["job_id"]}')
                err.observation = obs_inc
                raise err
        finally:
            shutil.rmtree(inc_stage, ignore_errors=True)
        state['steps_completed'].append(step_name)
        _write_prepare_state(job_dir, state)

    state['stage'] = 'verifying_prepared_artifact'
    _write_prepare_state(job_dir, state)

    prepared_artifact = inspect_backup_artifact(working_copy, expected_type={'log-applied', 'full-prepared'})
    if int(prepared_artifact['to_lsn']) < int(chain['expected_final_to_lsn']):
        raise MariaDBPhysicalError(
            f"Prepared to_lsn={prepared_artifact['to_lsn']} did not advance to {chain['expected_final_to_lsn']}"
        )
    if chain['incrementals'] and int(prepared_artifact['last_lsn']) < int(chain['expected_final_last_lsn']):
        raise MariaDBPhysicalError(
            f"Prepared last_lsn={prepared_artifact['last_lsn']} did not advance to {chain['expected_final_last_lsn']}"
        )

    # Re-verify that original base and incremental artifacts remain 100% immutable!
    after_chain = validate_backup_chain(base_record, incremental_records)
    if after_chain['base']['manifest_sha256'] != chain['base']['manifest_sha256'] or [
        i['manifest_sha256'] for i in after_chain['incrementals']
    ] != [i['manifest_sha256'] for i in chain['incrementals']]:
        raise MariaDBPhysicalError('Original immutable backup chain modified during prepare!')

    durable_replace(working_copy, final_artifact)
    final_inspected = inspect_backup_artifact(final_artifact, expected_type={'log-applied', 'full-prepared'})
    state['stage'] = 'completed'
    state['steps_completed'].append('promoted_prepared_artifact')
    state['finished_at'] = time.time()
    _write_prepare_state(job_dir, state)

    return {
        'tool': tool,
        'chain': chain,
        'immutable_inputs_verified_unchanged': True,
        'lsn_advancement': {
            'base_to_lsn': chain['base']['to_lsn'],
            'base_last_lsn': chain['base']['last_lsn'],
            'prepared_to_lsn': final_inspected['to_lsn'],
            'prepared_last_lsn': final_inspected['last_lsn'],
            'advanced': (
                int(final_inspected['to_lsn']) >= int(chain['expected_final_to_lsn'])
                and int(final_inspected['last_lsn']) >= int(chain['expected_final_last_lsn'])
            ),
        },
        'process_observations': [
            {k: v for k, v in o.items() if k not in {'stdout', 'stderr'}} for o in observations
        ],
        'artifact': final_inspected,
        'artifact_dir': str(final_artifact),
    }


def reconcile_interrupted_prepare(*, job_dir, base_record, incremental_records):
    """Reconcile an interrupted/failed prepare job without mutating immutable inputs or auto-replaying."""
    job_dir = safe_absolute_path(str(job_dir), 'prepare job directory')
    state_file = job_dir / 'prepare-state.json'
    state = json.loads(state_file.read_text(encoding='utf-8')) if state_file.is_file() else {'stage': 'unrecorded'}
    last_obs = state.get('last_observation') or {}
    birth = last_obs.get('process_birth')
    if birth and process_alive(birth):
        raise MariaDBPhysicalError('Native mariadb-backup prepare process is still running; wait or cancel first')

    # Verify original base + incrementals are completely untouched
    chain_check = validate_backup_chain(base_record, incremental_records)
    working_copy = job_dir / 'working_copy'
    working_copy_cleaned = False
    if working_copy.exists():
        shutil.rmtree(working_copy)
        working_copy_cleaned = True
    for leftover in job_dir.glob('inc_stage_*'):
        shutil.rmtree(leftover, ignore_errors=True)

    reconciled = {
        'reconciled_at': time.time(),
        'interrupted_stage': state.get('stage'),
        'steps_completed_before_interruption': state.get('steps_completed', []),
        'immutable_inputs_intact': True,
        'verified_chain_digests': {
            'base': chain_check['base']['manifest_sha256'],
            'incrementals': [i['manifest_sha256'] for i in chain_check['incrementals']],
        },
        'partial_working_copy_removed': working_copy_cleaned,
        'usable_for_recovery': (job_dir / 'artifact').is_dir() and state.get('stage') == 'completed',
        'automatic_retry': False,
    }
    state['reconciliation'] = reconciled
    _write_prepare_state(job_dir, state)
    return reconciled


def run_isolated_copy_or_move_back(
    *, backup_binary, prepared_record, target_datadir, source_datadir, job_dir,
    mode='copy_back', daemon_user=None, timeout_seconds=3600, cancel=None,
    version_prefix='12.2.2',
):
    """Restore a prepared physical artifact into an unshared empty target datadir."""
    if mode not in {'copy_back', 'move_back'}:
        raise MariaDBPhysicalError("Select 'copy_back' or 'move_back'")
    tool = admit_executable(backup_binary, 'mariadb-backup', version_prefix=version_prefix)
    prep_art = (prepared_record.get('result') or {}).get('artifact')
    if not prep_art or not prep_art.get('prepared'):
        raise MariaDBPhysicalError('Select a verified prepared MariaDB physical backup before copy-back/move-back')
    prep_dir = safe_absolute_path(str(prepared_record['artifact_dir']), 'prepared artifact')
    live_prep = inspect_backup_artifact(prep_dir, expected_type={'log-applied', 'full-prepared'})
    if live_prep['manifest_sha256'] != prep_art['manifest_sha256']:
        raise MariaDBPhysicalError('Prepared physical artifact bytes changed before copy-back/move-back')

    target_datadir = safe_absolute_path(str(target_datadir), 'target recovery datadir')
    source_datadir = safe_absolute_path(str(source_datadir), 'source datadir')
    job_dir = safe_absolute_path(str(job_dir), 'restore job directory')
    if (target_datadir == source_datadir
            or target_datadir.is_relative_to(source_datadir)
            or source_datadir.is_relative_to(target_datadir)
            or target_datadir.is_relative_to(prep_dir)):
        raise MariaDBPhysicalError('Target recovery datadir must be completely isolated from live source datadir')
    if target_datadir.exists() and any(target_datadir.iterdir()):
        raise MariaDBPhysicalError('Target recovery datadir must be empty before copy-back/move-back')
    target_datadir.mkdir(parents=True, exist_ok=True, mode=0o700)
    job_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(job_dir)

    if mode == 'move_back':
        # Stage a private copy so native --move-back moves files into target_datadir
        # while keeping the sealed prepared backup immutable for audit/repeatability!
        move_stage = job_dir / 'move_stage'
        shutil.copytree(prep_dir, move_stage)
        source_arg_dir = move_stage
        flag = '--move-back'
    else:
        source_arg_dir = prep_dir
        flag = '--copy-back'

    obs = run_supervised_process(
        tool['path'],
        ['--no-defaults', flag, f'--target-dir={source_arg_dir}', f'--datadir={target_datadir}'],
        job_dir, timeout_seconds=timeout_seconds, cancel=cancel,
    )
    if mode == 'move_back':
        shutil.rmtree(job_dir / 'move_stage', ignore_errors=True)
    if obs['return_code'] != 0 or 'completed OK!' not in (obs['stdout'] + '\n' + obs['stderr']):
        err = MariaDBPhysicalError(f'mariadb-backup {flag} failed')
        err.observation = obs
        raise err

    if os.geteuid() == 0 and daemon_user:
        pw = pwd.getpwnam(daemon_user)
        for root, dirs, files in os.walk(target_datadir, followlinks=False):
            os.chown(root, pw.pw_uid, pw.pw_gid)
            for d in dirs:
                os.chown(Path(root) / d, pw.pw_uid, pw.pw_gid)
            for f in files:
                os.chown(Path(root) / f, pw.pw_uid, pw.pw_gid)

    # Confirm sealed prepared artifact remained untouched
    if inspect_backup_artifact(prep_dir)['manifest_sha256'] != prep_art['manifest_sha256']:
        raise MariaDBPhysicalError('Prepared artifact changed unexpectedly during restore')
    restored_files = directory_manifest(target_datadir)
    return {
        'tool': tool,
        'mode': mode,
        'target_datadir': str(target_datadir),
        'restored_file_count': len(restored_files),
        'restored_manifest_sha256': canonical_digest(restored_files),
        'prepared_artifact_preserved': True,
        'process_observation': {k: v for k, v in obs.items() if k not in {'stdout', 'stderr'}},
    }


def _short_unix_socket_base():
    """Return a short local runtime directory suitable for AF_UNIX sun_path (<= 107 bytes)."""
    uid = os.geteuid() if hasattr(os, 'geteuid') else 0
    run_user = Path(f'/run/user/{uid}')
    if run_user.is_dir() and os.access(run_user, os.W_OK | os.X_OK) and len(str(run_user)) <= 40:
        return run_user
    return Path('/tmp')


def _short_runtime_dir(job_dir):
    candidate = Path(job_dir) / 'run'
    if len(str(candidate / 'm.sock')) <= 96:
        candidate.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_directory(candidate)
        return candidate, False
    short = Path(tempfile.mkdtemp(prefix='sr-mrec-', dir=str(_short_unix_socket_base())))
    os.chmod(short, 0o700)
    return short, True


def check_port_available(port):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise MariaDBPhysicalError('Select an isolated recovery port between 1024 and 65535')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(('127.0.0.1', port))
        except OSError:
            raise MariaDBPhysicalError(f'Recovery loopback TCP port {port} is already in use') from None


def start_isolated_recovery_instance(
    *, mariadbd_binary, mariadb_client_binary, mariadb_binlog_binary,
    target_datadir, source_datadir, source_port, recovery_port,
    job_dir, db_user, db_password, recovery_server_id=99173,
    basedir=None, plugin_dir=None, lc_messages_dir=None, daemon_user=None,
    pitr=None, expected_checks=None, version_prefix='12.2.2', timeout_seconds=120,
):
    """Start isolated mariadbd (--skip-slave-start), optionally replay binlogs to PITR, and verify data/schema/security."""
    import mariadb

    if int(recovery_port) == int(source_port):
        raise MariaDBPhysicalError('Isolated recovery port must differ from live source port')
    check_port_available(recovery_port)
    target_datadir = safe_absolute_path(str(target_datadir), 'recovery datadir')
    source_datadir = safe_absolute_path(str(source_datadir), 'source datadir')
    if target_datadir == source_datadir or target_datadir.is_relative_to(source_datadir):
        raise MariaDBPhysicalError('Isolated recovery datadir cannot overlap source datadir')

    mariadbd_tool = admit_executable(mariadbd_binary, 'mariadbd', version_prefix=version_prefix)
    client_tool = admit_executable(mariadb_client_binary, 'mariadb', version_prefix=version_prefix)
    binlog_tool = (
        admit_executable(mariadb_binlog_binary, 'mariadb-binlog', version_prefix=version_prefix)
        if pitr else None
    )

    job_dir = safe_absolute_path(str(job_dir), 'recovery job directory')
    job_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(job_dir)
    run_dir, short_temp_used = _short_runtime_dir(job_dir)
    sock_path = run_dir / 'm.sock'
    pid_path = run_dir / 'm.pid'
    err_log = job_dir / 'recovery-mariadbd.err'
    tmp_dir = job_dir / 'tmpdir'
    tmp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    if os.geteuid() == 0 and daemon_user:
        pw = pwd.getpwnam(daemon_user)
        for p in (run_dir, tmp_dir, job_dir):
            os.chown(p, pw.pw_uid, pw.pw_gid)

    daemon_args = [
        str(mariadbd_tool['path']),
        '--no-defaults',
        f'--datadir={target_datadir}',
        f'--tmpdir={tmp_dir}',
        f'--socket={sock_path}',
        f'--pid-file={pid_path}',
        '--bind-address=127.0.0.1',
        f'--port={int(recovery_port)}',
        '--skip-slave-start',
        '--event-scheduler=DISABLED',
        '--read-only=1',
        f'--server-id={int(recovery_server_id)}',
        '--log-bin=sr-recovery-bin',
        '--gtid-strict-mode=ON',
        '--binlog-format=ROW',
        f'--log-error={err_log}',
    ]
    if basedir:
        daemon_args.append(f'--basedir={safe_absolute_path(str(basedir), "basedir")}')
    if plugin_dir:
        daemon_args.append(f'--plugin-dir={safe_absolute_path(str(plugin_dir), "plugin_dir")}')
    if lc_messages_dir:
        daemon_args.append(f'--lc-messages-dir={safe_absolute_path(str(lc_messages_dir), "lc_messages_dir")}')
    if daemon_user:
        daemon_args.append(f'--user={daemon_user}')

    proc = subprocess.Popen(
        daemon_args,
        cwd=str(job_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    birth = _proc_birth(proc.pid)
    ready = False
    deadline = time.monotonic() + timeout_seconds
    last_err = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log_tail = err_log.read_text(encoding='utf-8', errors='replace')[-2000:] if err_log.exists() else ''
            raise MariaDBPhysicalError(f'Isolated recovery mariadbd exited prematurely (rc={proc.returncode}): {log_tail}')
        try:
            conn = mariadb.connect(
                host='127.0.0.1', port=int(recovery_port),
                user=db_user, password=db_password or '',
                connect_timeout=2, autocommit=True,
            )
            conn.close()
            ready = True
            break
        except Exception as exc:
            last_err = exc
            time.sleep(0.15)

    if not ready:
        stop_isolated_recovery_instance(
            pid_birth=birth, socket_path=str(sock_path), port=recovery_port,
            db_user=db_user, db_password=db_password, run_dir=str(run_dir) if short_temp_used else None,
        )
        raise MariaDBPhysicalError(f'Isolated recovery mariadbd did not become SQL-ready: {last_err}')

    pitr_receipt = None
    try:
        conn = mariadb.connect(
            host='127.0.0.1', port=int(recovery_port),
            user=db_user, password=db_password or '', autocommit=True,
        )
        try:
            obs_init = rows(
                conn,
                'SELECT VERSION() AS version, @@server_uid AS server_uid, @@datadir AS datadir, '
                '@@port AS port, @@read_only AS read_only, @@gtid_binlog_pos AS gtid_binlog_pos, '
                '@@gtid_current_pos AS gtid_current_pos, @@gtid_slave_pos AS gtid_slave_pos',
            )[0]
            if Path(obs_init['datadir']).resolve(strict=False) != target_datadir:
                raise MariaDBPhysicalError('Recovery connection reached unexpected datadir')

            if pitr:
                pitr_receipt = _apply_pitr_catchup(
                    conn=conn,
                    binlog_tool=binlog_tool,
                    client_tool=client_tool,
                    pitr=pitr,
                    job_dir=job_dir,
                    recovery_port=recovery_port,
                    db_user=db_user,
                    db_password=db_password,
                    timeout_seconds=timeout_seconds,
                )

            verification = verify_restored_instance(conn, expected_checks=expected_checks)
        finally:
            conn.close()
    except BaseException:
        stop_isolated_recovery_instance(
            pid_birth=birth, socket_path=str(sock_path), port=recovery_port,
            db_user=db_user, db_password=db_password, run_dir=str(run_dir) if short_temp_used else None,
        )
        raise

    runtime_info = {
        'mariadbd': mariadbd_tool,
        'mariadb_client': client_tool,
        'process_birth': birth,
        'recovery_port': int(recovery_port),
        'socket_path': str(sock_path),
        'pid_path': str(pid_path),
        'short_run_dir': str(run_dir) if short_temp_used else None,
        'target_datadir': str(target_datadir),
        'skip_slave_start': True,
        'read_only': True,
        'sql_ready_observed': True,
        'pitr_catchup': pitr_receipt,
        'independent_verification': verification,
        'database_recovery_verified': verification['verified'] is True,
    }
    (job_dir / 'recovery-runtime.json').write_text(json.dumps(runtime_info, indent=2, sort_keys=True) + '\n')
    return runtime_info


def _apply_pitr_catchup(
    *, conn, binlog_tool, client_tool, pitr, job_dir,
    recovery_port, db_user, db_password, timeout_seconds,
):
    """Apply point-in-time binary log catch-up (by stop_gtid or stop_position) onto isolated recovery mariadbd."""
    log_files = [safe_absolute_path(str(p), 'PITR binlog file') for p in pitr['binlog_files']]
    if not log_files:
        raise MariaDBPhysicalError('PITR catch-up requires at least one verified binary log file')
    before = rows(
        conn,
        'SELECT @@global.gtid_current_pos AS gtid_current_pos, '
        '@@global.gtid_binlog_pos AS gtid_binlog_pos, @@global.gtid_slave_pos AS gtid_slave_pos',
    )[0]

    decode_dir = Path(job_dir) / 'pitr_load'
    decode_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    decoded_sql = Path(job_dir) / 'pitr_decoded.sql'

    args = [
        '--no-defaults',
        '--verify-binlog-checksum',
        f'--local-load={decode_dir}',
        f'--result-file={decoded_sql}',
    ]
    start_gtid = pitr.get('start_gtid')
    stop_gtid = pitr.get('stop_gtid')
    stop_mode = pitr.get('stop_mode', 'after')
    start_position = pitr.get('start_position')
    stop_position = pitr.get('stop_position')
    stop_datetime = pitr.get('stop_datetime')
    baseline_gtid = pitr.get('baseline_gtid_pos') or start_gtid

    if start_gtid or stop_gtid:
        args.append('--gtid-strict-mode')

    if stop_gtid is not None:
        gtids(stop_gtid)
        # Scan byte offset of stop_gtid in the provided log files using native event framing
        archive_dir = log_files[0].parent
        if (archive_dir / 'archive.json').is_file():
            inv = inventory(archive_dir, None, stop=stop_gtid)
            bound = inv['stop_before'] if stop_mode == 'before' else inv['stop_after']
            if bound is not None:
                log_files = log_files[:bound['file_index'] + 1]
                args.append(f"--stop-position={bound['position']}")
        else:
            args.append(f'--stop-position={stop_gtid}')
    elif stop_position is not None:
        args.append(f'--stop-position={int(stop_position)}')

    if start_gtid:
        gtids(start_gtid)
        args.append(f'--start-position={start_gtid}')
    elif start_position is not None:
        args.append(f'--start-position={int(start_position)}')

    if stop_datetime:
        args.append(f'--stop-datetime={stop_datetime}')

    args.append('--')
    args.extend(str(p) for p in log_files)

    dec_obs = run_supervised_process(
        binlog_tool['path'], args, job_dir, timeout_seconds=timeout_seconds,
    )
    if dec_obs['return_code'] != 0:
        raise MariaDBPhysicalError(f"mariadb-binlog PITR decode failed: {dec_obs['stderr'][:400]}")

    cur = conn.cursor()
    try:
        cur.execute('SET GLOBAL read_only=0')
        if baseline_gtid and not before.get('gtid_slave_pos') and not before.get('gtid_binlog_pos'):
            gtids(baseline_gtid)
            cur.execute('SET GLOBAL gtid_slave_pos = ?', (baseline_gtid,))
        cnf = write_private_defaults_file(
            job_dir, user=db_user, password=db_password, host='127.0.0.1', port=recovery_port,
        )
        apply_obs = run_supervised_process(
            client_tool['path'],
            [
                '--default-character-set=utf8mb4', '--batch', '--raw',
                '--binary-mode', '--abort-source-on-error',
            ],
            job_dir, timeout_seconds=timeout_seconds,
            defaults_file=cnf, redact_values=(db_password,), input_path=decoded_sql,
        )
        if apply_obs['return_code'] != 0:
            raise MariaDBPhysicalError(f"mariadb client PITR apply failed: {apply_obs['stderr'][:400]}")
    finally:
        try:
            cur.execute('SET GLOBAL read_only=1')
        finally:
            cur.close()
        decoded_sql.unlink(missing_ok=True)
        shutil.rmtree(decode_dir, ignore_errors=True)

    after = rows(
        conn,
        'SELECT @@global.gtid_current_pos AS gtid_current_pos, '
        '@@global.gtid_binlog_pos AS gtid_binlog_pos, @@global.gtid_slave_pos AS gtid_slave_pos',
    )[0]
    return {
        'applied': True,
        'before_gtid': before,
        'after_gtid': after,
        'stop_gtid': stop_gtid,
        'stop_mode': stop_mode if stop_gtid else None,
        'stop_position': stop_position,
        'decoder_return_code': dec_obs['return_code'],
        'client_return_code': apply_obs['return_code'],
    }


def verify_restored_instance(conn, *, expected_checks=None):
    """Independently verify restored schemas, tables, row counts, checksums, routines, views & accounts."""
    server_info = rows(
        conn,
        'SELECT VERSION() AS version, @@server_uid AS server_uid, @@datadir AS datadir, '
        '@@port AS port, @@read_only AS read_only, @@gtid_current_pos AS gtid_current_pos',
    )[0]
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
    table_digests = []
    for tbl in tables:
        schema_q = '`' + str(tbl['schema_name']).replace('`', '``') + '`'
        table_q = '`' + str(tbl['table_name']).replace('`', '``') + '`'
        cnt = rows(conn, f'SELECT COUNT(*) AS row_count FROM {schema_q}.{table_q}')[0]['row_count']
        csum = rows(conn, f'CHECKSUM TABLE {schema_q}.{table_q} EXTENDED')[0]
        table_digests.append({
            'schema_name': tbl['schema_name'],
            'table_name': tbl['table_name'],
            'engine': tbl['engine'],
            'row_count': int(cnt),
            'checksum': str(csum.get('Checksum')),
        })

    mismatches = []
    if expected_checks:
        for req_db in expected_checks.get('databases', []):
            if req_db not in databases:
                mismatches.append(f'missing_database:{req_db}')
        by_fqn = {f"{t['schema_name']}.{t['table_name']}": t for t in table_digests}
        for fqn, exp_count in (expected_checks.get('table_row_counts') or {}).items():
            if fqn not in by_fqn:
                mismatches.append(f'missing_table:{fqn}')
            elif by_fqn[fqn]['row_count'] != int(exp_count):
                mismatches.append(f"row_count_mismatch:{fqn}:{by_fqn[fqn]['row_count']}!={exp_count}")
        acct_set = {f"{a['user']}@{a['host']}" for a in accounts}
        for exp_acct in expected_checks.get('accounts', []):
            if exp_acct not in acct_set:
                mismatches.append(f'missing_account:{exp_acct}')

    if mismatches:
        raise MariaDBPhysicalError('Independent restored verification failed: ' + ', '.join(mismatches))

    return {
        'verified': True,
        'server': server_info,
        'databases': databases,
        'tables': table_digests,
        'views': views,
        'routines': routines,
        'security_accounts': accounts,
        'read_only_enforced': mariadb_bool(server_info['read_only']),
    }


def stop_isolated_recovery_instance(*, pid_birth, socket_path=None, port=None, db_user='root', db_password='', run_dir=None):
    """Cleanly shut down an isolated recovery mariadbd and confirm PID exit."""
    import mariadb

    if process_alive(pid_birth) and port:
        try:
            conn = mariadb.connect(
                host='127.0.0.1', port=int(port),
                user=db_user, password=db_password or '',
                connect_timeout=3, autocommit=True,
            )
            try:
                cur = conn.cursor()
                cur.execute('SHUTDOWN')
                cur.close()
            finally:
                conn.close()
        except Exception:
            pass
    deadline = time.monotonic() + 15.0
    while process_alive(pid_birth) and time.monotonic() < deadline:
        time.sleep(0.1)
    if process_alive(pid_birth):
        pid = int(pid_birth['pid'])
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        grace = time.monotonic() + 5.0
        while process_alive(pid_birth) and time.monotonic() < grace:
            time.sleep(0.1)
        if process_alive(pid_birth):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    if run_dir:
        shutil.rmtree(run_dir, ignore_errors=True)
    return {
        'stopped': not process_alive(pid_birth),
        'pid': pid_birth.get('pid') if isinstance(pid_birth, dict) else None,
    }
