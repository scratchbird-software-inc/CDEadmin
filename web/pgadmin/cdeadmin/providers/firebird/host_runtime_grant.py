"""Application-host runtime grant resolution for Firebird host administration.

Separates read-only diagnostic grants from host configuration, plugin/UDR
deployment, daemon lifecycle, ODS migration and replication journal directories.
"""
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import socket
import sys

from ...sdk.relational import RelationalClientError
from .local_services import admit_service_route, file_identity

MAX_MANIFEST_BYTES = 1024 * 1024
ALLOWED_GRANT_KEYS = frozenset({
    'endpoint_id', 'firebird_runtime_root', 'firebird_lock_directory',
    'databases', 'allow_host_administration', 'staging_directory',
    'journal_directories', 'managed_daemon',
})
ALLOWED_DAEMON_KEYS = frozenset({
    'pid_file', 'port', 'bind_host', 'server_log',
})


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def current_boot_id():
    if sys.platform != 'linux':
        raise ValueError('Firebird host administration is currently qualified on Linux only')
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='utf-8').strip()
    if not boot_id:
        raise ValueError('Linux host boot_id is unavailable')
    return boot_id


def _canonical_dir(raw_path, label, must_exist=True):
    if not isinstance(raw_path, str) or not raw_path or '\0' in raw_path:
        raise ValueError(f'{label} must be a non-empty path')
    candidate = Path(raw_path)
    if not candidate.is_absolute() or any(part == '..' for part in candidate.parts):
        raise ValueError(f'{label} must be an absolute path without parent traversal')
    if must_exist:
        resolved = candidate.resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError(f'{label} must be an existing directory')
        return str(resolved)
    parent = candidate.parent.resolve(strict=True)
    target = parent / candidate.name
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError(f'{label} cannot be a symlink or non-directory')
    return str(target)


def _canonical_file_slot(raw_path, label):
    if not isinstance(raw_path, str) or not raw_path or '\0' in raw_path:
        raise ValueError(f'{label} must be a non-empty path')
    candidate = Path(raw_path)
    if not candidate.is_absolute() or any(part == '..' for part in candidate.parts):
        raise ValueError(f'{label} must be an absolute path without parent traversal')
    parent = candidate.parent.resolve(strict=True)
    target = parent / candidate.name
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError(f'{label} cannot be a symlink or directory')
    return str(target)


def _validate_runtime_root(runtime_root):
    root = Path(_canonical_dir(runtime_root, 'firebird_runtime_root', must_exist=True))
    fbclient = root / 'lib/libfbclient.so.5.0.4'
    engine = root / 'plugins/libEngine13.so'
    if not fbclient.is_file() or not engine.is_file():
        raise ValueError(
            'Firebird 5.0.4 runtime root must contain lib/libfbclient.so.5.0.4 and plugins/libEngine13.so'
        )
    return root


def _parse_managed_daemon(raw_daemon):
    if raw_daemon is None:
        return None
    if not isinstance(raw_daemon, Mapping) or set(raw_daemon) - ALLOWED_DAEMON_KEYS:
        raise ValueError('managed_daemon declaration is invalid')
    port = raw_daemon.get('port')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('managed_daemon.port must be a valid TCP port')
    bind_host = raw_daemon.get('bind_host', '127.0.0.1')
    if not isinstance(bind_host, str) or bind_host not in {'127.0.0.1', '::1', 'localhost'}:
        raise ValueError('managed_daemon.bind_host must be loopback (127.0.0.1, ::1 or localhost)')
    pid_file = _canonical_file_slot(raw_daemon.get('pid_file', ''), 'managed_daemon.pid_file')
    server_log = _canonical_file_slot(raw_daemon.get('server_log', ''), 'managed_daemon.server_log')
    return {
        'pid_file': pid_file,
        'port': port,
        'bind_host': bind_host,
        'server_log': server_log,
    }


def resolve_admin_host_scope(endpoint_id, route, *, require_mutation=True):
    """Resolve verified Linux host runtime scope for config, plugins, daemon or replication."""
    boot_id = current_boot_id()
    manifest_path = os.environ.get('CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST') or ''

    if manifest_path:
        mpath = Path(manifest_path)
        if not mpath.is_absolute() or mpath.resolve(strict=True) != mpath:
            raise ValueError('Firebird host-tools manifest must be a canonical absolute file')
        raw = mpath.read_bytes()
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ValueError('Firebird host-tools manifest exceeds its size budget')
        doc = json.loads(raw)
        if (not isinstance(doc, dict)
                or doc.get('format') != 'scratchrobin.firebird.host-tools@1'
                or not isinstance(doc.get('grants'), list)):
            raise ValueError('Invalid Firebird host-tools manifest format')
        matches = [
            g for g in doc['grants']
            if isinstance(g, dict) and g.get('endpoint_id') == endpoint_id
        ]
        if len(matches) == 1:
            grant = matches[0]
            if set(grant) - ALLOWED_GRANT_KEYS:
                raise ValueError('Firebird host grant contains unexpected fields')
            allow_admin = grant.get('allow_host_administration', False)
            if type(allow_admin) is not bool:
                raise ValueError('allow_host_administration must be boolean')
            if require_mutation and not allow_admin:
                raise ValueError(
                    'Host grant for this endpoint is read-only; set allow_host_administration=true '
                    'to authorize configuration, plugin or runtime mutations'
                )
            rt_root = _validate_runtime_root(grant['firebird_runtime_root'])
            lock_dir = _canonical_dir(grant['firebird_lock_directory'], 'firebird_lock_directory', must_exist=False)
            staging_dir = (
                _canonical_dir(grant['staging_directory'], 'staging_directory', must_exist=True)
                if grant.get('staging_directory') else None
            )
            journal_dirs = [
                _canonical_dir(d, 'journal_directory', must_exist=False)
                for d in (grant.get('journal_directories') or ())
            ]
            allowed_dbs = [
                str(Path(d)) for d in (grant.get('databases') or ())
                if isinstance(d, str) and Path(d).is_absolute()
            ]
            return {
                'attachment_mode': (
                    'embedded' if route.get('attachment_mode') == 'embedded'
                    else 'same_host_granted_network'
                ),
                'platform': 'linux',
                'boot_id': boot_id,
                'hostname': socket.gethostname(),
                'engine_version': '5.0.4',
                'firebird_runtime_root': str(rt_root),
                'firebird_lock_directory': lock_dir,
                'staging_directory': staging_dir,
                'journal_directories': journal_dirs,
                'allowed_databases': allowed_dbs,
                'allow_host_administration': allow_admin,
                'managed_daemon': _parse_managed_daemon(grant.get('managed_daemon')),
                'grant_manifest_sha256': hashlib.sha256(raw).hexdigest(),
            }

    if route.get('attachment_mode') == 'embedded':
        try:
            admitted = admit_service_route(route)
            ident = file_identity(admitted)
        except RelationalClientError as error:
            raise ValueError(str(error)) from error
        fb_env = os.environ.get('FIREBIRD') or ''
        if not fb_env:
            raise ValueError('Embedded host administration requires FIREBIRD runtime root')
        rt_root = _validate_runtime_root(fb_env)
        lock_env = os.environ.get('FIREBIRD_LOCK') or str(rt_root / 'lock')
        lock_dir = _canonical_dir(lock_env, 'FIREBIRD_LOCK', must_exist=False)
        fs_root = _canonical_dir(admitted['filesystem_root'], 'filesystem_root', must_exist=True)
        return {
            'attachment_mode': 'embedded',
            'platform': 'linux',
            'boot_id': boot_id,
            'hostname': socket.gethostname(),
            'engine_version': '5.0.4',
            'firebird_runtime_root': str(rt_root),
            'firebird_lock_directory': lock_dir,
            'staging_directory': fs_root,
            'journal_directories': [fs_root],
            'allowed_databases': [ident['path']],
            'filesystem_root': fs_root,
            'allow_host_administration': True,
            'managed_daemon': None,
            'grant_manifest_sha256': None,
        }

    raise ValueError(
        'Host configuration, plugin and runtime management require an application-host '
        'embedded route or an explicit CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST grant for this endpoint'
    )


def verify_same_host(scope):
    if current_boot_id() != scope.get('boot_id'):
        raise ValueError('Application host boot_id changed since review; refresh and review again')
