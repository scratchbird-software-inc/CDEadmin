"""Admitted execution-host worker and transports for MySQL/MariaDB native utilities.

Supports three explicit execution-host boundaries without shell interpolation:
- ``local``: application-host execution inside explicitly admitted datadir/workspace roots
- ``container``: container execution host via ``docker exec`` positional POSIX primitives
- ``ssh``: pinned database-server SSH execution host via ``mysql_host_transport.Transport``
"""
from __future__ import annotations

import base64
import configparser
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid

try:
    from _cdeadmin_native_fileio import private_directory, private_file
except ModuleNotFoundError:
    from ...operations.fileio import private_directory, private_file

MAX_OUTPUT_BYTES = 1024 * 1024
MAX_ARTIFACT_READ_BYTES = 4 * 1024 * 1024
CONTAINER_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
DOCKER_CONTEXT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')
SAFE_IDENT_RE = re.compile(r'^[A-Za-z0-9_@#$ -]{1,64}$')


class UtilityHostError(ValueError):
    """Raised when an execution-host precondition, path, or tool check fails."""


Refused = UtilityHostError


def _clean_text(value, label, max_len=4096):
    if not isinstance(value, str) or not value or '\x00' in value or len(value) > max_len:
        raise UtilityHostError(f'Select a bounded {label}')
    return value


def validate_identifier(value, label='identifier'):
    text = _clean_text(value, label, 64)
    if text in {'.', '..'} or '/' in text or '\\' in text or not SAFE_IDENT_RE.fullmatch(text):
        raise UtilityHostError(f'Invalid {label}: {text!r}')
    return text


def validate_posix_root(value, label='directory'):
    text = _clean_text(value, label, 4096)
    path = PurePosixPath(text)
    if not path.is_absolute() or '..' in path.parts:
        raise UtilityHostError(f'{label.capitalize()} must be a canonical absolute path without parent traversal')
    normalized = str(path)
    if normalized in {'/', '/root', '/home', '/etc', '/bin', '/sbin', '/usr', '/proc', '/sys', '/dev'}:
        raise UtilityHostError(f'{label.capitalize()} root {normalized!r} is over-broad')
    return normalized


def resolve_posix_subpath(root_str, rel_str, label='file path'):
    root = PurePosixPath(validate_posix_root(root_str, 'root directory'))
    rel = _clean_text(rel_str, label, 1024)
    rel_path = PurePosixPath(rel)
    if rel_path.is_absolute() or '..' in rel_path.parts or not rel_path.parts:
        raise UtilityHostError(f'{label.capitalize()} must stay strictly within its admitted root')
    joined = root.joinpath(*rel_path.parts)
    if root not in joined.parents:
        raise UtilityHostError(f'{label.capitalize()} escapes its admitted root')
    return str(joined)


def format_defaults_file(password: str, user: str | None = None) -> bytes:
    if not isinstance(password, str) or '\x00' in password:
        raise UtilityHostError('Database tool credential is invalid')
    escaped = (
        password.replace('\\', '\\\\')
        .replace('"', '\\"')
        .replace('\n', '\\n')
        .replace('\r', '\\r')
    )
    lines = ['[client]']
    if user:
        escaped_user = (
            str(user).replace('\\', '\\\\').replace('"', '\\"')
            .replace('\n', '').replace('\r', '')
        )
        lines.append(f'user="{escaped_user}"')
    lines.append(f'password="{escaped}"')
    return ('\n'.join(lines) + '\n').encode('utf-8')


def redact_text(raw_bytes: bytes, redact_values: tuple[str, ...], limit: int = MAX_OUTPUT_BYTES) -> tuple[str, bool]:
    truncated = len(raw_bytes) > limit
    chunk = raw_bytes[:limit]
    text = chunk.decode('utf-8', errors='replace')
    for secret in sorted({v for v in redact_values if isinstance(v, str) and v}, key=len, reverse=True):
        text = text.replace(secret, '[redacted]')
    return text, truncated


def verify_version_banner(version_text: str, return_code: int, expected_engine: str, binary_name: str) -> str:
    if return_code != 0:
        raise UtilityHostError(f'Native {binary_name} --version check failed (exit {return_code})')
    if expected_engine == 'mysql':
        if 'MariaDB' in version_text or '9.7.0' not in version_text:
            raise UtilityHostError(
                f'MySQL utility {binary_name} must be from the exact MySQL 9.7.0 release; observed: {version_text.strip()[:160]}'
            )
        return '9.7.0'
    if expected_engine == 'mariadb':
        if '12.2.2-MariaDB' not in version_text:
            raise UtilityHostError(
                f'MariaDB utility {binary_name} must be from the exact 12.2.2-MariaDB release; observed: {version_text.strip()[:160]}'
            )
        return '12.2.2-MariaDB'
    raise UtilityHostError(f'Unsupported utility engine: {expected_engine!r}')


class LocalHostSession:
    """Direct local execution-host implementation with strict containment and /proc checks."""

    kind = 'application-host'

    def close(self):
        return None

    @staticmethod
    def _admitted_local_root(path_str: str, label: str, must_exist: bool = True) -> Path:
        validate_posix_root(path_str, label)
        raw = Path(path_str)
        resolved = raw.resolve(strict=must_exist)
        home = Path.home().resolve(strict=False)
        if resolved in {Path('/'), home}:
            raise UtilityHostError(f'{label.capitalize()} grant is over-broad')
        if must_exist and not resolved.is_dir():
            raise UtilityHostError(f'{label.capitalize()} does not exist as a directory')
        return resolved

    def ensure_workspace(self, workspace_str: str) -> str:
        ws = self._admitted_local_root(workspace_str, 'workspace', must_exist=False)
        ws.mkdir(parents=True, exist_ok=True)
        private_directory(ws)
        return str(ws)

    def resolve_contained_file(self, root_str: str, rel_str: str, *, must_exist: bool = True) -> str:
        root = self._admitted_local_root(root_str, 'root directory', must_exist=True)
        joined_str = resolve_posix_subpath(str(root), rel_str)
        candidate = Path(joined_str)
        resolved = candidate.resolve(strict=must_exist)
        try:
            resolved.relative_to(root)
        except ValueError:
            raise UtilityHostError('Target file escapes its admitted directory via symlink or traversal') from None
        if resolved == root:
            raise UtilityHostError('Target path must name a file inside the admitted root')
        if must_exist:
            st = resolved.lstat()
            if not stat.S_ISREG(st.st_mode):
                raise UtilityHostError('Target host path is not a regular file')
        return str(resolved)

    def inspect_binary(self, executable_spec: str, expected_engine: str, workspace_str: str) -> dict:
        spec = _clean_text(executable_spec, 'executable', 1024)
        ws = self.ensure_workspace(workspace_str)
        candidate = None
        if os.path.isabs(spec):
            p = Path(spec)
            if p.is_file() and os.access(p, os.X_OK):
                candidate = p.resolve(strict=True)
        else:
            found = shutil.which(spec)
            if found:
                candidate = Path(found).resolve(strict=True)
            else:
                for prefix in ('/usr/bin', '/usr/sbin', '/usr/local/bin'):
                    p = Path(prefix) / spec
                    if p.is_file() and os.access(p, os.X_OK):
                        candidate = p.resolve(strict=True)
                        break
        if candidate is None or not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise UtilityHostError(f'Native utility executable {spec!r} is unavailable on the execution host')
        digest = self._sha256_file(candidate)
        obs = self.run_supervised(str(candidate), ['--version'], ws, 15)
        banner = (obs['stdout'] + ' ' + obs['stderr']).strip()
        identity = verify_version_banner(banner, obs['return_code'], expected_engine, Path(spec).name)
        return {
            'executable_path': str(candidate),
            'executable_sha256': digest,
            'version_output': banner[:240],
            'tool_version_identity': identity,
            'execution_host_kind': self.kind,
        }

    @staticmethod
    def _sha256_file(path: Path) -> str:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise UtilityHostError('Selected host file is not a regular file')
            h = hashlib.sha256()
            with os.fdopen(fd, 'rb') as stream:
                fd = -1
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        finally:
            if fd >= 0:
                os.close(fd)

    def file_fingerprint(self, path_str: str) -> dict:
        p = Path(path_str)
        if not p.exists():
            return {'exists': False, 'size_bytes': 0, 'sha256': None}
        st = p.lstat()
        if not stat.S_ISREG(st.st_mode):
            raise UtilityHostError('Target path is not a regular file')
        return {
            'exists': True,
            'size_bytes': int(st.st_size),
            'sha256': self._sha256_file(p),
        }

    def sync_datadir_ownership(self, datadir_str: str, target_paths: list[str]) -> None:
        if os.geteuid() != 0:
            return
        datadir = self._admitted_local_root(datadir_str, 'datadir', must_exist=True)
        st = datadir.stat()
        for p_str in target_paths:
            p = Path(p_str)
            if p.is_file():
                os.chown(p, st.st_uid, st.st_gid)

    def observe_datadir_identity(self, datadir_str: str, expected_engine: str) -> dict:
        datadir = self._admitted_local_root(datadir_str, 'datadir', must_exist=True)
        server_uuid = None
        auto_cnf = datadir / 'auto.cnf'
        if auto_cnf.is_file():
            data = auto_cnf.read_text(encoding='utf-8', errors='replace')[:65536]
            cp = configparser.ConfigParser(interpolation=None)
            cp.read_string(data)
            raw_uuid = cp.get('auto', 'server-uuid', fallback=None)
            if raw_uuid:
                server_uuid = str(uuid.UUID(raw_uuid.strip()))
        return {
            'datadir': str(datadir),
            'hostname': socket.gethostname(),
            'server_uuid': server_uuid,
            'has_mysql_ibd': (datadir / 'mysql.ibd').is_file(),
            'has_aria_control': (datadir / 'aria_log_control').is_file(),
            'has_ibdata1': (datadir / 'ibdata1').is_file(),
            'engine': expected_engine,
        }

    def verify_offline_state(
        self,
        datadir_str: str,
        target_files: list[str],
        expected_engine: str,
        *,
        pid_file: str | None = None,
        socket_path: str | None = None,
    ) -> dict:
        datadir = self._admitted_local_root(datadir_str, 'datadir', must_exist=True)
        holder_pids: set[int] = set()
        reasons: list[str] = []

        # 1. Check explicit pid_file and any *.pid inside datadir
        pid_candidates: list[Path] = []
        if pid_file:
            pid_candidates.append(Path(_clean_text(pid_file, 'pid_file', 4096)))
        pid_candidates.extend(sorted(datadir.glob('*.pid'))[:16])
        checked_pid_files = []
        for pf in pid_candidates:
            try:
                if pf.is_file():
                    checked_pid_files.append(pf.name)
                    raw_pid = pf.read_text(encoding='ascii', errors='ignore').strip()
                    if raw_pid.isdigit():
                        pid_int = int(raw_pid)
                        if (Path('/proc') / str(pid_int)).exists():
                            holder_pids.add(pid_int)
                            reasons.append(f'active_pidfile:{pf.name}:{pid_int}')
            except OSError:
                continue

        # 2. Collect target and sentinel inodes
        watched_inodes: set[tuple[int, int]] = set()
        datadir_stat = datadir.stat()
        sentinel_paths = [
            datadir / 'mysql.ibd',
            datadir / 'ibdata1',
            datadir / 'aria_log_control',
            datadir / 'tc.log',
            *(Path(tf) for tf in target_files),
        ]
        for sp in sentinel_paths:
            try:
                if sp.exists():
                    st = sp.stat()
                    watched_inodes.add((st.st_dev, st.st_ino))
            except OSError:
                continue

        # 3. Scan /proc for running mysqld/mariadbd on datadir OR any open fd to watched_inodes
        daemon_names = {'mysqld', 'mariadbd', 'mysqld_safe', 'mariadbd-safe'}
        proc_root = Path('/proc')
        if proc_root.is_dir():
            fd_checked = 0
            for entry in proc_root.iterdir():
                if not entry.name.isdigit():
                    continue
                pid_int = int(entry.name)
                if pid_int == os.getpid():
                    continue
                comm = ''
                try:
                    comm = (entry / 'comm').read_text(encoding='utf-8', errors='ignore').strip()
                except OSError:
                    continue
                is_daemon = comm in daemon_names
                if is_daemon:
                    try:
                        cwd_resolved = (entry / 'cwd').resolve()
                        if cwd_resolved == datadir or datadir in cwd_resolved.parents:
                            holder_pids.add(pid_int)
                            reasons.append(f'daemon_cwd:{comm}:{pid_int}')
                    except OSError:
                        pass
                    try:
                        cmdline = (entry / 'cmdline').read_bytes().decode('utf-8', errors='ignore').replace('\x00', ' ')
                        if str(datadir) in cmdline:
                            holder_pids.add(pid_int)
                            reasons.append(f'daemon_cmdline:{comm}:{pid_int}')
                    except OSError:
                        pass
                try:
                    for fd_entry in (entry / 'fd').iterdir():
                        fd_checked += 1
                        if fd_checked > 250000:
                            break
                        try:
                            st = fd_entry.stat()
                        except OSError:
                            continue
                        if (st.st_dev, st.st_ino) in watched_inodes:
                            holder_pids.add(pid_int)
                            reasons.append(f'open_fd_inode:{comm or "proc"}:{pid_int}')
                            break
                        if is_daemon and st.st_dev == datadir_stat.st_dev:
                            try:
                                target_link = Path(os.readlink(fd_entry))
                                if target_link == datadir or datadir in target_link.parents:
                                    holder_pids.add(pid_int)
                                    reasons.append(f'daemon_open_fd:{comm}:{pid_int}')
                                    break
                            except OSError:
                                pass
                except OSError:
                    continue

        # 4. Non-mutating POSIX advisory lock probe on target files
        for tf in target_files:
            tp = Path(tf)
            if not tp.is_file():
                continue
            try:
                fd = os.open(tp, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
                try:
                    lock_data = fcntl.flock  # check fcntl F_GETLK struct
                    import struct
                    flock_struct = struct.pack('hhllhh', fcntl.F_WRLCK, os.SEEK_SET, 0, 0, 0, 0)
                    res = fcntl.fcntl(fd, fcntl.F_GETLK, flock_struct)
                    l_type, _whence, _start, _len, l_pid, *_ = struct.unpack('hhllhh', res[:24])
                    if l_type != fcntl.F_UNLCK and l_pid > 0:
                        holder_pids.add(int(l_pid))
                        reasons.append(f'posix_lock:{tp.name}:{l_pid}')
                except (OSError, struct.error):
                    pass
                finally:
                    os.close(fd)
            except OSError:
                continue

        # 5. Unix socket listener check inside datadir / explicit socket_path
        sock_candidates = []
        if socket_path:
            sock_candidates.append(Path(_clean_text(socket_path, 'socket_path', 1024)))
        for sname in ('mysql.sock', 'mariadb.sock', 'mysqld.sock'):
            sock_candidates.append(datadir / sname)
        for sp in sock_candidates:
            try:
                if sp.exists() and stat.S_ISSOCK(sp.lstat().st_mode):
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    try:
                        s.connect(str(sp))
                        reasons.append(f'active_unix_socket:{sp.name}')
                    except OSError:
                        pass
                    finally:
                        s.close()
            except OSError:
                continue

        if holder_pids or reasons:
            raise UtilityHostError(
                f'Refused offline utility execution: database server or file lock is active on {datadir.name} '
                f'(holders={sorted(holder_pids)}, reasons={reasons[:4]})'
            )

        return {
            'verified_offline': True,
            'holder_pids': [],
            'pid_files_checked': checked_pid_files,
            'watched_inode_count': len(watched_inodes),
            'execution_host_kind': self.kind,
        }

    def stage_private_backups(self, workspace_str: str, job_id: str, files_map: dict[str, str]) -> dict:
        ws = Path(self.ensure_workspace(workspace_str))
        safe_job = re.sub(r'[^A-Za-z0-9_.-]', '_', job_id)[:80]
        backup_dir = ws / 'backups' / safe_job
        backup_dir.mkdir(parents=True, exist_ok=True)
        private_directory(ws / 'backups')
        private_directory(backup_dir)
        staged = {}
        for label, src_str in sorted(files_map.items()):
            src = Path(src_str)
            if not src.exists():
                continue
            st = src.lstat()
            if not stat.S_ISREG(st.st_mode):
                raise UtilityHostError(f'Cannot stage non-regular file {src.name}')
            dst = backup_dir / src.name
            shutil.copyfile(src, dst)
            private_file(dst)
            staged[label] = {
                'filename': src.name,
                'backup_relpath': f'backups/{safe_job}/{src.name}',
                'size_bytes': int(dst.stat().st_size),
                'sha256': self._sha256_file(dst),
            }
        manifest_path = backup_dir / 'manifest.json'
        manifest_bytes = json.dumps({'job_id': safe_job, 'files': staged}, sort_keys=True, indent=2).encode('utf-8')
        manifest_path.write_bytes(manifest_bytes)
        private_file(manifest_path)
        return {
            'backup_dir_relpath': f'backups/{safe_job}',
            'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
            'files': staged,
        }

    def prepare_job_dir(self, workspace_str: str, job_id: str) -> str:
        ws = Path(self.ensure_workspace(workspace_str))
        safe_job = re.sub(r'[^A-Za-z0-9_.-]', '_', job_id)[:80]
        job_dir = ws / 'jobs' / safe_job
        job_dir.mkdir(parents=True, exist_ok=True)
        private_directory(ws / 'jobs')
        private_directory(job_dir)
        return str(job_dir)

    def write_private_file(self, workspace_str: str, rel_path: str, content: bytes) -> str:
        ws = self._admitted_local_root(workspace_str, 'workspace', must_exist=False)
        ws.mkdir(parents=True, exist_ok=True)
        private_directory(ws)
        target_str = resolve_posix_subpath(str(ws), rel_path, 'private artifact')
        target = Path(target_str)
        target.parent.mkdir(parents=True, exist_ok=True)
        private_directory(target.parent)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, 'wb') as stream:
                fd = -1
                private_file(target)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            if fd >= 0:
                os.close(fd)
        return str(target)

    def read_private_file(self, workspace_str: str, rel_path: str, max_bytes: int = MAX_ARTIFACT_READ_BYTES) -> dict:
        target_str = self.resolve_contained_file(workspace_str, rel_path, must_exist=True)
        p = Path(target_str)
        digest = self._sha256_file(p)
        size = int(p.stat().st_size)
        with p.open('rb') as stream:
            data = stream.read(max_bytes + 1)
        truncated = len(data) > max_bytes
        return {
            'exists': True,
            'size_bytes': size,
            'sha256': digest,
            'truncated': truncated,
            'content_bytes': data[:max_bytes],
        }

    def remove_private_file(self, workspace_str: str, rel_path: str) -> None:
        try:
            target_str = self.resolve_contained_file(workspace_str, rel_path, must_exist=True)
        except (UtilityHostError, OSError):
            return
        p = Path(target_str)
        try:
            size = p.stat().st_size
            if size > 0:
                with p.open('r+b') as stream:
                    stream.write(b'\x00' * min(size, 1024 * 1024))
                    stream.flush()
                    os.fsync(stream.fileno())
        except OSError:
            pass
        finally:
            p.unlink(missing_ok=True)

    def run_supervised(
        self,
        executable_path: str,
        arguments: list[str],
        workspace_str: str,
        timeout_seconds: int,
        *,
        secret_defaults_bytes: bytes | None = None,
        secret_arg_prefix: str = '--defaults-extra-file=',
        redact_values: tuple[str, ...] = (),
        cancel_signal=None,
    ) -> dict:
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
            raise UtilityHostError('Select utility timeout between 1 and 3600 seconds')
        if any(not isinstance(a, str) or '\x00' in a for a in arguments):
            raise UtilityHostError('Utility arguments contain invalid values')
        ws = Path(self.ensure_workspace(workspace_str))
        run_dir = ws / ('run-' + secrets.token_hex(8))
        run_dir.mkdir(parents=True, exist_ok=True)
        private_directory(run_dir)

        secret_file: Path | None = None
        cmd = [str(executable_path)]
        redactions = list(redact_values)
        started_at = time.time()
        try:
            if secret_defaults_bytes is not None:
                secret_file = run_dir / '.client-defaults.cnf'
                fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as stream:
                    private_file(secret_file)
                    stream.write(bytes(secret_defaults_bytes))
                    stream.flush()
                    os.fsync(stream.fileno())
                cmd.append(f'{secret_arg_prefix}{secret_file}')
                redactions.append(str(secret_file))
            cmd.extend(arguments)

            env = {
                'LANG': 'C.UTF-8',
                'LC_ALL': 'C.UTF-8',
                'HOME': str(run_dir),
                'TMPDIR': str(run_dir),
                'PATH': os.pathsep.join((str(Path(executable_path).parent), os.defpath)),
            }
            if cancel_signal is not None and cancel_signal.is_set():
                empty_sha = hashlib.sha256(b'').hexdigest()
                return {
                    'return_code': -15,
                    'timed_out': False,
                    'cancelled': True,
                    'cleanup_confirmed': True,
                    'stdout': '',
                    'stderr': '',
                    'stdout_bytes': 0,
                    'stderr_bytes': 0,
                    'stdout_truncated': False,
                    'stderr_truncated': False,
                    'stdout_sha256': empty_sha,
                    'stderr_sha256': empty_sha,
                    'secret_file_used': secret_defaults_bytes is not None,
                    'secret_file_wiped': True,
                    'started_at': started_at,
                    'finished_at': time.time(),
                    'execution_host_kind': self.kind,
                }
            child = subprocess.Popen(
                cmd,
                cwd=str(run_dir),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
            )
            out_buf = bytearray()
            err_buf = bytearray()
            out_hash = hashlib.sha256()
            err_hash = hashlib.sha256()
            out_total = 0
            err_total = 0

            def _drain(pipe, buf: bytearray, h, is_err: bool):
                nonlocal out_total, err_total
                try:
                    while True:
                        chunk = pipe.read(8192)
                        if not chunk:
                            break
                        h.update(chunk)
                        if is_err:
                            err_total += len(chunk)
                        else:
                            out_total += len(chunk)
                        if len(buf) < MAX_OUTPUT_BYTES + 4096:
                            buf.extend(chunk[: max(0, MAX_OUTPUT_BYTES + 4096 - len(buf))])
                finally:
                    pipe.close()

            t_out = threading.Thread(target=_drain, args=(child.stdout, out_buf, out_hash, False), daemon=True)
            t_err = threading.Thread(target=_drain, args=(child.stderr, err_buf, err_hash, True), daemon=True)
            t_out.start()
            t_err.start()

            timed_out = False
            cancelled = False
            deadline = time.monotonic() + timeout_seconds
            while child.poll() is None:
                if cancel_signal is not None and cancel_signal.is_set():
                    cancelled = True
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                time.sleep(0.025)

            if cancelled or timed_out:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except OSError:
                    pass
                for _ in range(20):
                    if child.poll() is not None:
                        break
                    time.sleep(0.025)
                if child.poll() is None:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except OSError:
                        child.kill()
                    child.wait(timeout=5)

            t_out.join(timeout=5)
            t_err.join(timeout=5)
            cleanup_confirmed = child.poll() is not None and not t_out.is_alive() and not t_err.is_alive()
            stdout_text, stdout_trunc = redact_text(bytes(out_buf), tuple(redactions))
            stderr_text, stderr_trunc = redact_text(bytes(err_buf), tuple(redactions))
            return {
                'return_code': child.returncode,
                'timed_out': timed_out,
                'cancelled': cancelled,
                'cleanup_confirmed': cleanup_confirmed,
                'stdout': stdout_text,
                'stderr': stderr_text,
                'stdout_bytes': out_total,
                'stderr_bytes': err_total,
                'stdout_truncated': stdout_trunc or out_total > MAX_OUTPUT_BYTES,
                'stderr_truncated': stderr_trunc or err_total > MAX_OUTPUT_BYTES,
                'stdout_sha256': out_hash.hexdigest(),
                'stderr_sha256': err_hash.hexdigest(),
                'secret_file_used': secret_defaults_bytes is not None,
                'secret_file_wiped': True,
                'started_at': started_at,
                'finished_at': time.time(),
                'execution_host_kind': self.kind,
            }
        finally:
            if secret_file is not None and secret_file.exists():
                try:
                    sz = secret_file.stat().st_size
                    with secret_file.open('r+b') as stream:
                        stream.write(b'\x00' * sz)
                        stream.flush()
                        os.fsync(stream.fileno())
                except OSError:
                    pass
                finally:
                    secret_file.unlink(missing_ok=True)
            shutil.rmtree(run_dir, ignore_errors=True)


class ContainerHostSession:
    """Admitted Docker container execution-host session using non-interpolated POSIX positional calls."""

    kind = 'container-execution-host'

    def __init__(self, container_name: str, docker_context: str | None = None):
        if not isinstance(container_name, str) or not CONTAINER_NAME_RE.fullmatch(container_name):
            raise UtilityHostError('Select a valid admitted container execution host name')
        if docker_context is not None and docker_context != '':
            if not isinstance(docker_context, str) or not DOCKER_CONTEXT_RE.fullmatch(docker_context):
                raise UtilityHostError('Select a valid Docker context name')
            self.docker_context = docker_context
        else:
            self.docker_context = os.environ.get('DOCKER_CONTEXT') or None
        self.container_name = container_name

    def close(self):
        return None

    def _docker_base(self) -> list[str]:
        cmd = ['docker']
        if self.docker_context:
            cmd.extend(['--context', self.docker_context])
        return cmd

    def _exec_posix(self, script: str, args: list[str] = (), *, input_bytes: bytes = b'', timeout: int = 30) -> subprocess.CompletedProcess:
        cmd = [*self._docker_base(), 'exec', '-i', self.container_name, 'sh', '-c', script, 'sr-posix', *args]
        try:
            return subprocess.run(
                cmd,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise UtilityHostError('Container execution host inspection timed out') from None
        except OSError as exc:
            raise UtilityHostError(f'Docker client is unavailable ({type(exc).__name__})') from None

    def ensure_workspace(self, workspace_str: str) -> str:
        ws = validate_posix_root(workspace_str, 'workspace')
        res = self._exec_posix('mkdir -p -- "$1" && chmod 700 -- "$1" && cd -- "$1" && pwd -P', [ws])
        if res.returncode != 0:
            raise UtilityHostError('Container workspace directory could not be initialized')
        resolved = res.stdout.decode('utf-8', errors='replace').strip()
        return validate_posix_root(resolved, 'workspace')

    def resolve_contained_file(self, root_str: str, rel_str: str, *, must_exist: bool = True) -> str:
        root_norm = validate_posix_root(root_str, 'root directory')
        joined = resolve_posix_subpath(root_norm, rel_str)
        script = '''
set -e
root_real=$(cd -- "$1" 2>/dev/null && pwd -P) || exit 11
parent_dir=$(dirname -- "$2")
base_name=$(basename -- "$2")
parent_real=$(cd -- "$parent_dir" 2>/dev/null && pwd -P) || exit 12
target="$parent_real/$base_name"
case "$target" in
  "$root_real"/*) ;;
  *) exit 13 ;;
esac
if [ "$3" = "1" ]; then
  [ -f "$target" ] || exit 14
  [ ! -L "$target" ] || {
    link_real=$(readlink -f -- "$target" 2>/dev/null) || exit 15
    case "$link_real" in
      "$root_real"/*) target="$link_real" ;;
      *) exit 16 ;;
    esac
    [ -f "$target" ] || exit 14
  }
fi
printf '%s\n' "$target"
'''
        res = self._exec_posix(script, [root_norm, joined, '1' if must_exist else '0'])
        if res.returncode != 0:
            if res.returncode in {13, 16}:
                raise UtilityHostError('Target file escapes its admitted directory via symlink or traversal')
            raise UtilityHostError(f'Target file {rel_str!r} is unavailable or not a regular file inside {root_norm}')
        return res.stdout.decode('utf-8', errors='replace').strip()

    def inspect_binary(self, executable_spec: str, expected_engine: str, workspace_str: str) -> dict:
        spec = _clean_text(executable_spec, 'executable', 1024)
        ws = self.ensure_workspace(workspace_str)
        script = '''
set -e
spec="$1"
found=""
if [ "${spec#/}" != "$spec" ]; then
  [ -f "$spec" ] && [ -x "$spec" ] && found="$spec"
else
  found=$(command -v -- "$spec" 2>/dev/null || true)
  if [ -z "$found" ]; then
    for d in /usr/bin /usr/sbin /usr/local/bin; do
      if [ -f "$d/$spec" ] && [ -x "$d/$spec" ]; then
        found="$d/$spec"
        break
      fi
    done
  fi
fi
[ -n "$found" ] || exit 21
real=$(readlink -f -- "$found" 2>/dev/null || printf '%s' "$found")
[ -f "$real" ] && [ -x "$real" ] || exit 21
hash=$(sha256sum -- "$real" | awk '{print $1}')
printf '%s\n%s\n' "$real" "$hash"
'''
        res = self._exec_posix(script, [spec])
        if res.returncode != 0:
            raise UtilityHostError(f'Native utility executable {spec!r} is unavailable in container {self.container_name}')
        lines = res.stdout.decode('utf-8', errors='replace').strip().splitlines()
        if len(lines) < 2:
            raise UtilityHostError('Failed to inspect binary identity in container')
        real_path, sha256_hex = lines[0].strip(), lines[1].strip()
        obs = self.run_supervised(real_path, ['--version'], ws, 15)
        banner = (obs['stdout'] + ' ' + obs['stderr']).strip()
        identity = verify_version_banner(banner, obs['return_code'], expected_engine, PurePosixPath(spec).name)
        return {
            'executable_path': real_path,
            'executable_sha256': sha256_hex,
            'version_output': banner[:240],
            'tool_version_identity': identity,
            'execution_host_kind': self.kind,
            'container_name': self.container_name,
        }

    def file_fingerprint(self, path_str: str) -> dict:
        p = validate_posix_root(path_str, 'file path')
        script = '''
if [ ! -e "$1" ]; then
  printf 'ABSENT\n'
  exit 0
fi
[ -f "$1" ] || exit 17
sz=$(wc -c < "$1" | tr -d ' ')
h=$(sha256sum -- "$1" | awk '{print $1}')
printf 'PRESENT %s %s\n' "$sz" "$h"
'''
        res = self._exec_posix(script, [p])
        if res.returncode != 0:
            raise UtilityHostError('Target path in container is not a regular file')
        out = res.stdout.decode('utf-8', errors='replace').strip()
        if out == 'ABSENT':
            return {'exists': False, 'size_bytes': 0, 'sha256': None}
        parts = out.split()
        return {'exists': True, 'size_bytes': int(parts[1]), 'sha256': parts[2]}

    def sync_datadir_ownership(self, datadir_str: str, target_paths: list[str]) -> None:
        datadir = validate_posix_root(datadir_str, 'datadir')
        if not target_paths:
            return
        script = '''
if [ "$(id -u)" != "0" ]; then exit 0; fi
ug=$(stat -c '%u:%g' -- "$1" 2>/dev/null || true)
[ -n "$ug" ] || exit 0
shift
for f in "$@"; do
  [ -f "$f" ] && chown -- "$ug" "$f"
done
'''
        self._exec_posix(script, [datadir, *target_paths])

    def observe_datadir_identity(self, datadir_str: str, expected_engine: str) -> dict:
        datadir = validate_posix_root(datadir_str, 'datadir')
        script = '''
set -e
dd_real=$(cd -- "$1" 2>/dev/null && pwd -P) || exit 31
hn=$(hostname 2>/dev/null || cat /etc/hostname 2>/dev/null || printf 'container')
has_ibd=0; [ -f "$dd_real/mysql.ibd" ] && has_ibd=1
has_aria=0; [ -f "$dd_real/aria_log_control" ] && has_aria=1
has_ibdata=0; [ -f "$dd_real/ibdata1" ] && has_ibdata=1
printf '%s\n%s\n%s %s %s\n' "$dd_real" "$hn" "$has_ibd" "$has_aria" "$has_ibdata"
if [ -f "$dd_real/auto.cnf" ]; then
  head -c 4096 -- "$dd_real/auto.cnf"
fi
'''
        res = self._exec_posix(script, [datadir])
        if res.returncode != 0:
            raise UtilityHostError(f'Datadir {datadir!r} is unavailable in container {self.container_name}')
        lines = res.stdout.decode('utf-8', errors='replace').splitlines()
        dd_real = lines[0].strip()
        hostname = lines[1].strip() if len(lines) > 1 else self.container_name
        flags = lines[2].split() if len(lines) > 2 else ['0', '0', '0']
        auto_text = '\n'.join(lines[3:])
        server_uuid = None
        if auto_text.strip():
            cp = configparser.ConfigParser(interpolation=None)
            cp.read_string(auto_text)
            raw_uuid = cp.get('auto', 'server-uuid', fallback=None)
            if raw_uuid:
                server_uuid = str(uuid.UUID(raw_uuid.strip()))
        return {
            'datadir': dd_real,
            'hostname': hostname,
            'server_uuid': server_uuid,
            'has_mysql_ibd': flags[0] == '1',
            'has_aria_control': flags[1] == '1',
            'has_ibdata1': flags[2] == '1',
            'engine': expected_engine,
            'container_name': self.container_name,
        }

    def verify_offline_state(
        self,
        datadir_str: str,
        target_files: list[str],
        expected_engine: str,
        *,
        pid_file: str | None = None,
        socket_path: str | None = None,
    ) -> dict:
        datadir = validate_posix_root(datadir_str, 'datadir')
        pf_arg = _clean_text(pid_file, 'pid_file', 1024) if pid_file else ''
        sock_arg = _clean_text(socket_path, 'socket_path', 1024) if socket_path else ''
        script = r'''
set -e
dd_real=$(cd -- "$1" 2>/dev/null && pwd -P) || exit 41
pf_explicit="$2"
sock_explicit="$3"
shift 3

holders=""
reasons=""

check_pidfile() {
  f="$1"
  if [ -n "$f" ] && [ -f "$f" ]; then
    p=$(tr -d ' \t\r\n' < "$f" 2>/dev/null || true)
    case "$p" in
      ''|*[!0-9]*) ;;
      *)
        if [ -d "/proc/$p" ]; then
          holders="$holders $p"
          reasons="$reasons active_pidfile:$(basename -- "$f"):$p"
        fi
        ;;
    esac
  fi
}

check_pidfile "$pf_explicit"
for pf in "$dd_real"/*.pid; do
  [ -f "$pf" ] && check_pidfile "$pf"
done

inodes=" "
for f in "$dd_real/mysql.ibd" "$dd_real/ibdata1" "$dd_real/aria_log_control" "$dd_real/tc.log" "$@"; do
  if [ -e "$f" ]; then
    ino=$(stat -L -c '%d:%i' -- "$f" 2>/dev/null || true)
    [ -n "$ino" ] && inodes="${inodes}${ino} "
  fi
done

for pdir in /proc/[0-9]*; do
  [ -d "$pdir" ] || continue
  p="${pdir#/proc/}"
  [ "$p" = "$$" ] && continue
  comm=$(cat "$pdir/comm" 2>/dev/null || true)
  is_daemon=0
  case "$comm" in
    mysqld|mariadbd|mysqld_safe|mariadbd-safe) is_daemon=1 ;;
  esac
  if [ "$is_daemon" = "1" ]; then
    cwd_real=$(readlink -f "$pdir/cwd" 2>/dev/null || true)
    if [ "$cwd_real" = "$dd_real" ]; then
      holders="$holders $p"
      reasons="$reasons daemon_cwd:$comm:$p"
    fi
    cmdline=$(tr '\000' ' ' < "$pdir/cmdline" 2>/dev/null || true)
    case "$cmdline" in
      *"$dd_real"*|*"mysqld"*|*"mariadbd"*)
        if [ "$cwd_real" = "$dd_real" ] || case "$cmdline" in *"$dd_real"*) true ;; *) false ;; esac; then
          holders="$holders $p"
          reasons="$reasons daemon_cmdline:$comm:$p"
        fi
        ;;
    esac
  fi
  if [ -d "$pdir/fd" ]; then
    for fd in "$pdir/fd"/*; do
      [ -e "$fd" ] || continue
      ino=$(stat -L -c '%d:%i' -- "$fd" 2>/dev/null || true)
      if [ -n "$ino" ]; then
        case "$inodes" in
          *" $ino "*)
            holders="$holders $p"
            reasons="$reasons open_fd_inode:${comm:-proc}:$p"
            break
            ;;
        esac
      fi
      if [ "$is_daemon" = "1" ]; then
        target=$(readlink -f "$fd" 2>/dev/null || true)
        case "$target" in
          "$dd_real"/*)
            holders="$holders $p"
            reasons="$reasons daemon_open_fd:$comm:$p"
            break
            ;;
        esac
      fi
    done
  fi
done

printf 'HOLDERS:%s\nREASONS:%s\n' "$holders" "$reasons"
'''
        res = self._exec_posix(script, [datadir, pf_arg, sock_arg, *target_files], timeout=20)
        if res.returncode != 0:
            raise UtilityHostError(f'Offline precondition check failed on container {self.container_name}')
        lines = res.stdout.decode('utf-8', errors='replace').splitlines()
        holders_raw = ''
        reasons_raw = ''
        for line in lines:
            if line.startswith('HOLDERS:'):
                holders_raw = line.removeprefix('HOLDERS:').strip()
            elif line.startswith('REASONS:'):
                reasons_raw = line.removeprefix('REASONS:').strip()
        holder_pids = sorted({int(x) for x in holders_raw.split() if x.isdigit()})
        reasons = reasons_raw.split() if reasons_raw else []
        if holder_pids or reasons:
            raise UtilityHostError(
                f'Refused offline utility execution: database server or file lock is active in container {self.container_name} '
                f'(holders={holder_pids}, reasons={reasons[:4]})'
            )
        return {
            'verified_offline': True,
            'holder_pids': [],
            'execution_host_kind': self.kind,
            'container_name': self.container_name,
        }

    def stage_private_backups(self, workspace_str: str, job_id: str, files_map: dict[str, str]) -> dict:
        ws = self.ensure_workspace(workspace_str)
        safe_job = re.sub(r'[^A-Za-z0-9_.-]', '_', job_id)[:80]
        backup_dir = f'{ws}/backups/{safe_job}'
        self._exec_posix('mkdir -p -- "$1" "$2" && chmod 700 -- "$1" "$2"', [f'{ws}/backups', backup_dir])
        staged = {}
        for label, src_str in sorted(files_map.items()):
            fp = self.file_fingerprint(src_str)
            if not fp['exists']:
                continue
            fname = PurePosixPath(src_str).name
            dst_str = f'{backup_dir}/{fname}'
            res = self._exec_posix('cp -p -- "$1" "$2" && chmod 600 -- "$2"', [src_str, dst_str])
            if res.returncode != 0:
                raise UtilityHostError(f'Failed to stage private backup for {fname}')
            dst_fp = self.file_fingerprint(dst_str)
            staged[label] = {
                'filename': fname,
                'backup_relpath': f'backups/{safe_job}/{fname}',
                'size_bytes': dst_fp['size_bytes'],
                'sha256': dst_fp['sha256'],
            }
        manifest_bytes = json.dumps({'job_id': safe_job, 'files': staged}, sort_keys=True, indent=2).encode('utf-8')
        self.write_private_file(ws, f'backups/{safe_job}/manifest.json', manifest_bytes)
        return {
            'backup_dir_relpath': f'backups/{safe_job}',
            'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
            'files': staged,
        }

    def prepare_job_dir(self, workspace_str: str, job_id: str) -> str:
        ws = self.ensure_workspace(workspace_str)
        safe_job = re.sub(r'[^A-Za-z0-9_.-]', '_', job_id)[:80]
        job_dir = f'{ws}/jobs/{safe_job}'
        res = self._exec_posix('mkdir -p -- "$1" "$2" && chmod 700 -- "$1" "$2"', [f'{ws}/jobs', job_dir])
        if res.returncode != 0:
            raise UtilityHostError('Failed to create private job directory in container')
        return job_dir

    def write_private_file(self, workspace_str: str, rel_path: str, content: bytes) -> str:
        ws = self.ensure_workspace(workspace_str)
        target = resolve_posix_subpath(ws, rel_path, 'private artifact')
        parent = str(PurePosixPath(target).parent)
        script = 'set -e; mkdir -p -- "$1" && chmod 700 -- "$1" && umask 077 && cat > "$2" && chmod 600 -- "$2"'
        res = self._exec_posix(script, [parent, target], input_bytes=content)
        if res.returncode != 0:
            raise UtilityHostError('Failed to write private artifact file in container')
        return target

    def read_private_file(self, workspace_str: str, rel_path: str, max_bytes: int = MAX_ARTIFACT_READ_BYTES) -> dict:
        target = self.resolve_contained_file(workspace_str, rel_path, must_exist=True)
        fp = self.file_fingerprint(target)
        res = self._exec_posix('head -c "$2" -- "$1"', [target, str(max_bytes + 1)])
        if res.returncode != 0:
            raise UtilityHostError('Failed to read private artifact file in container')
        data = res.stdout
        return {
            'exists': True,
            'size_bytes': fp['size_bytes'],
            'sha256': fp['sha256'],
            'truncated': len(data) > max_bytes,
            'content_bytes': data[:max_bytes],
        }

    def remove_private_file(self, workspace_str: str, rel_path: str) -> None:
        ws = validate_posix_root(workspace_str, 'workspace')
        target = resolve_posix_subpath(ws, rel_path, 'private artifact')
        self._exec_posix(
            'if [ -f "$1" ]; then dd if=/dev/zero of="$1" bs=4096 count=16 conv=notrunc 2>/dev/null || true; rm -f -- "$1"; fi',
            [target],
        )

    def run_supervised(
        self,
        executable_path: str,
        arguments: list[str],
        workspace_str: str,
        timeout_seconds: int,
        *,
        secret_defaults_bytes: bytes | None = None,
        secret_arg_prefix: str = '--defaults-extra-file=',
        redact_values: tuple[str, ...] = (),
        cancel_signal=None,
    ) -> dict:
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
            raise UtilityHostError('Select utility timeout between 1 and 3600 seconds')
        if any(not isinstance(a, str) or '\x00' in a for a in arguments):
            raise UtilityHostError('Utility arguments contain invalid values')
        ws = self.ensure_workspace(workspace_str)
        token = secrets.token_hex(8)
        run_rel = f'run-{token}'
        run_dir = f'{ws}/{run_rel}'
        self._exec_posix('mkdir -p -- "$1" && chmod 700 -- "$1"', [run_dir])

        secret_rel: str | None = None
        redactions = list(redact_values)
        exec_args: list[str] = []
        started_at = time.time()
        pid_file = f'{run_dir}/child.pid'
        try:
            if secret_defaults_bytes is not None:
                secret_rel = f'{run_rel}/.client-defaults.cnf'
                secret_abs = self.write_private_file(ws, secret_rel, bytes(secret_defaults_bytes))
                exec_args.append(f'{secret_arg_prefix}{secret_abs}')
                redactions.append(secret_abs)
            exec_args.extend(arguments)

            if cancel_signal is not None and cancel_signal.is_set():
                empty_sha = hashlib.sha256(b'').hexdigest()
                return {
                    'return_code': -15,
                    'timed_out': False,
                    'cancelled': True,
                    'cleanup_confirmed': True,
                    'stdout': '',
                    'stderr': '',
                    'stdout_bytes': 0,
                    'stderr_bytes': 0,
                    'stdout_truncated': False,
                    'stderr_truncated': False,
                    'stdout_sha256': empty_sha,
                    'stderr_sha256': empty_sha,
                    'secret_file_used': secret_defaults_bytes is not None,
                    'secret_file_wiped': True,
                    'started_at': started_at,
                    'finished_at': time.time(),
                    'execution_host_kind': self.kind,
                    'container_name': self.container_name,
                }

            # Launch inside container recording child PID in pid_file so cancel/timeout kills inside container!
            wrapper = r'''
set -e
run_dir="$1"
pid_file="$2"
exe="$3"
shift 3
cd -- "$run_dir"
HOME="$run_dir" TMPDIR="$run_dir" LANG=C.UTF-8 LC_ALL=C.UTF-8 "$exe" "$@" </dev/null &
child=$!
printf '%s\n' "$child" > "$pid_file"
wait "$child"
'''
            cmd = [
                *self._docker_base(), 'exec', '-i', self.container_name,
                'sh', '-c', wrapper, 'sr-run', run_dir, pid_file, executable_path, *exec_args,
            ]
            child = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
            out_buf = bytearray()
            err_buf = bytearray()
            out_hash = hashlib.sha256()
            err_hash = hashlib.sha256()
            out_total = 0
            err_total = 0

            def _drain(pipe, buf: bytearray, h, is_err: bool):
                nonlocal out_total, err_total
                try:
                    while True:
                        chunk = pipe.read(8192)
                        if not chunk:
                            break
                        h.update(chunk)
                        if is_err:
                            err_total += len(chunk)
                        else:
                            out_total += len(chunk)
                        if len(buf) < MAX_OUTPUT_BYTES + 4096:
                            buf.extend(chunk[: max(0, MAX_OUTPUT_BYTES + 4096 - len(buf))])
                finally:
                    pipe.close()

            t_out = threading.Thread(target=_drain, args=(child.stdout, out_buf, out_hash, False), daemon=True)
            t_err = threading.Thread(target=_drain, args=(child.stderr, err_buf, err_hash, True), daemon=True)
            t_out.start()
            t_err.start()

            timed_out = False
            cancelled = False
            deadline = time.monotonic() + timeout_seconds
            while child.poll() is None:
                if cancel_signal is not None and cancel_signal.is_set():
                    cancelled = True
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                time.sleep(0.03)

            cleanup_confirmed = True
            if cancelled or timed_out:
                kill_script = r'''
pf="$1"
rdir="$2"
rdir_real=$(readlink -f -- "$rdir" 2>/dev/null || printf '%s' "$rdir")
pids=""
if [ -f "$pf" ]; then
  p=$(tr -d ' \t\r\n' < "$pf" 2>/dev/null || true)
  [ -n "$p" ] && pids="$pids $p"
fi
for pdir in /proc/[0-9]*; do
  [ -d "$pdir" ] || continue
  cpid="${pdir#/proc/}"
  [ "$cpid" = "$$" ] && continue
  cwd_real=$(readlink -f "$pdir/cwd" 2>/dev/null || true)
  if [ "$cwd_real" = "$rdir_real" ]; then
    pids="$pids $cpid"
  fi
done
for kp in $pids; do
  kill -TERM "$kp" 2>/dev/null || true
done
sleep 0.1
for kp in $pids; do
  kill -KILL "$kp" 2>/dev/null || true
done
for _ in 1 2 3 4 5; do
  alive=0
  for kp in $pids; do
    [ -d "/proc/$kp" ] && alive=1
  done
  [ "$alive" = "0" ] && break
  sleep 0.05
done
for kp in $pids; do
  [ ! -d "/proc/$kp" ] || exit 55
done
'''
                kres = self._exec_posix(kill_script, [pid_file, run_dir], timeout=10)
                cleanup_confirmed = kres.returncode == 0
                try:
                    child.terminate()
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)

            t_out.join(timeout=5)
            t_err.join(timeout=5)
            cleanup_confirmed = cleanup_confirmed and child.poll() is not None and not t_out.is_alive() and not t_err.is_alive()
            stdout_text, stdout_trunc = redact_text(bytes(out_buf), tuple(redactions))
            stderr_text, stderr_trunc = redact_text(bytes(err_buf), tuple(redactions))
            return {
                'return_code': child.returncode,
                'timed_out': timed_out,
                'cancelled': cancelled,
                'cleanup_confirmed': cleanup_confirmed,
                'stdout': stdout_text,
                'stderr': stderr_text,
                'stdout_bytes': out_total,
                'stderr_bytes': err_total,
                'stdout_truncated': stdout_trunc or out_total > MAX_OUTPUT_BYTES,
                'stderr_truncated': stderr_trunc or err_total > MAX_OUTPUT_BYTES,
                'stdout_sha256': out_hash.hexdigest(),
                'stderr_sha256': err_hash.hexdigest(),
                'secret_file_used': secret_defaults_bytes is not None,
                'secret_file_wiped': True,
                'started_at': started_at,
                'finished_at': time.time(),
                'execution_host_kind': self.kind,
                'container_name': self.container_name,
            }
        finally:
            if secret_rel is not None:
                self.remove_private_file(ws, secret_rel)
            self._exec_posix('rm -rf -- "$1"', [run_dir])


SSH_REMOTE_LOADER = '''import base64,json,sys,types
p=json.loads(sys.stdin.buffer.read(2097152))
f=types.ModuleType('_cdeadmin_native_fileio');exec(p['fileio'],f.__dict__);sys.modules[f.__name__]=f
w=types.ModuleType('_cdeadmin_utility_worker');exec(p['worker'],w.__dict__);sys.modules[w.__name__]=w
try:
 r=w.ssh_dispatch(p['op'],p['args'],p['kwargs'])
 out={'ok':True,'result':r}
except Exception as e:
 out={'ok':False,'error_type':type(e).__name__,'message':str(e) if isinstance(e,w.UtilityHostError) else 'Remote utility host error'}
print(p['marker']+json.dumps(out,ensure_ascii=True,separators=(',',':')),flush=True)
'''


def ssh_dispatch(op: str, args: list, kwargs: dict):
    session = LocalHostSession()
    if op == 'write_private_file':
        args = [args[0], args[1], base64.b64decode(args[2])]
    elif op == 'run_supervised' and kwargs.get('secret_defaults_b64'):
        kwargs = dict(kwargs)
        kwargs['secret_defaults_bytes'] = base64.b64decode(kwargs.pop('secret_defaults_b64'))
    result = getattr(session, op)(*args, **kwargs)
    if op == 'read_private_file' and isinstance(result, dict) and 'content_bytes' in result:
        result = {**result, 'content_b64': base64.b64encode(result.pop('content_bytes')).decode('ascii')}
    return result


class SSHHostSession:
    """Pinned SSH execution-host session built on mysql_host_transport.Transport."""

    kind = 'database-server-ssh-host'

    def __init__(self, route: dict, credentials: dict):
        from . import mysql_host_transport as ssh_transport
        self._ssh_module = ssh_transport
        try:
            self._transport = ssh_transport.Transport(route, credentials)
            self.peer_info = self._transport.connect()
        except ssh_transport.HostError as exc:
            raise UtilityHostError(str(exc)) from None

    def close(self):
        if getattr(self, '_transport', None) is not None:
            self._transport.close()

    def _rpc(self, op: str, args: list = (), kwargs: dict | None = None, timeout: int = 90):
        from ...operations import fileio
        peer = self._transport.transport
        if peer is None or not peer.is_authenticated():
            raise UtilityHostError('Authenticate the pinned SSH utility host first')
        marker = 'CDEADMIN_UTILITY_SSH_' + secrets.token_hex(16) + ':'
        envelope = {
            'fileio': Path(fileio.__file__).read_text(encoding='utf-8'),
            'worker': Path(__file__).read_text(encoding='utf-8'),
            'op': op,
            'args': list(args),
            'kwargs': dict(kwargs or {}),
            'marker': marker,
        }
        payload = json.dumps(envelope, ensure_ascii=True).encode('utf-8')
        channel = peer.open_session(timeout=5)
        try:
            cmd_str = self._ssh_module.command(self._transport.route['platform'], self._transport.route['python'])
            # Replace LOADER with SSH_REMOTE_LOADER
            cmd_str = 'exec ' + shlex.quote(self._transport.route['python']) + ' -u -c ' + shlex.quote(SSH_REMOTE_LOADER)
            channel.exec_command(cmd_str)
            channel.sendall(payload)
            channel.shutdown_write()
            stdout = bytearray()
            deadline = time.monotonic() + timeout
            while True:
                while channel.recv_ready():
                    stdout.extend(channel.recv(32768))
                while channel.recv_stderr_ready():
                    channel.recv_stderr(32768)
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
                if time.monotonic() > deadline:
                    raise UtilityHostError('SSH utility host call timed out')
                time.sleep(0.02)
            lines = [ln[len(marker):] for ln in stdout.decode('utf-8', errors='replace').splitlines() if ln.startswith(marker)]
            if len(lines) != 1:
                raise UtilityHostError('SSH utility host returned an invalid envelope')
            parsed = json.loads(lines[0])
            if not parsed.get('ok'):
                raise UtilityHostError(parsed.get('message') or 'SSH utility host refused operation')
            return parsed['result']
        finally:
            channel.close()

    def ensure_workspace(self, workspace_str: str) -> str:
        return self._rpc('ensure_workspace', [workspace_str])

    def resolve_contained_file(self, root_str: str, rel_str: str, *, must_exist: bool = True) -> str:
        return self._rpc('resolve_contained_file', [root_str, rel_str], {'must_exist': must_exist})

    def inspect_binary(self, executable_spec: str, expected_engine: str, workspace_str: str) -> dict:
        res = self._rpc('inspect_binary', [executable_spec, expected_engine, workspace_str])
        res['execution_host_kind'] = self.kind
        res['ssh_peer'] = self.peer_info
        return res

    def file_fingerprint(self, path_str: str) -> dict:
        return self._rpc('file_fingerprint', [path_str])

    def sync_datadir_ownership(self, datadir_str: str, target_paths: list[str]) -> None:
        self._rpc('sync_datadir_ownership', [datadir_str, target_paths])

    def observe_datadir_identity(self, datadir_str: str, expected_engine: str) -> dict:
        return self._rpc('observe_datadir_identity', [datadir_str, expected_engine])

    def verify_offline_state(self, datadir_str: str, target_files: list[str], expected_engine: str, *, pid_file=None, socket_path=None) -> dict:
        res = self._rpc('verify_offline_state', [datadir_str, target_files, expected_engine], {'pid_file': pid_file, 'socket_path': socket_path})
        res['execution_host_kind'] = self.kind
        return res

    def stage_private_backups(self, workspace_str: str, job_id: str, files_map: dict[str, str]) -> dict:
        return self._rpc('stage_private_backups', [workspace_str, job_id, files_map])

    def prepare_job_dir(self, workspace_str: str, job_id: str) -> str:
        return self._rpc('prepare_job_dir', [workspace_str, job_id])

    def write_private_file(self, workspace_str: str, rel_path: str, content: bytes) -> str:
        return self._rpc('write_private_file', [workspace_str, rel_path, base64.b64encode(content).decode('ascii')])

    def read_private_file(self, workspace_str: str, rel_path: str, max_bytes: int = MAX_ARTIFACT_READ_BYTES) -> dict:
        res = self._rpc('read_private_file', [workspace_str, rel_path, max_bytes])
        res['content_bytes'] = base64.b64decode(res.pop('content_b64'))
        return res

    def remove_private_file(self, workspace_str: str, rel_path: str) -> None:
        self._rpc('remove_private_file', [workspace_str, rel_path])

    def run_supervised(
        self,
        executable_path: str,
        arguments: list[str],
        workspace_str: str,
        timeout_seconds: int,
        *,
        secret_defaults_bytes: bytes | None = None,
        secret_arg_prefix: str = '--defaults-extra-file=',
        redact_values: tuple[str, ...] = (),
        cancel_signal=None,
    ) -> dict:
        kw = {
            'secret_arg_prefix': secret_arg_prefix,
            'redact_values': list(redact_values),
        }
        if secret_defaults_bytes is not None:
            kw['secret_defaults_b64'] = base64.b64encode(secret_defaults_bytes).decode('ascii')
        res = self._rpc('run_supervised', [executable_path, arguments, workspace_str, timeout_seconds], kw, timeout=timeout_seconds + 30)
        res['execution_host_kind'] = self.kind
        return res


def open_host_session(host_spec: dict, ssh_secrets: dict | None = None):
    kind = host_spec.get('execution_host_kind', 'local')
    if kind == 'local':
        return LocalHostSession()
    if kind == 'container':
        return ContainerHostSession(
            host_spec.get('container_name', ''),
            host_spec.get('docker_context') or None,
        )
    if kind == 'ssh':
        route = {
            'host': host_spec.get('ssh_host', ''),
            'port': int(host_spec.get('ssh_port') or 22),
            'username': host_spec.get('ssh_username', ''),
            'host_key': host_spec.get('ssh_host_key', ''),
            'authentication': host_spec.get('ssh_auth_mode', 'password'),
            'platform': 'posix',
            'python': host_spec.get('ssh_python') or '/usr/bin/python3',
        }
        return SSHHostSession(route, dict(ssh_secrets or {}))
    raise UtilityHostError(f'Unsupported execution_host_kind: {kind!r}')
