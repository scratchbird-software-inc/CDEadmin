"""Native SQLite Incremental Integrity-Check (`ext/intck`) admission and lifecycle (SQ-AUD-11)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import sys
import tempfile

from ...sdk.tool_process import observe_process
from ..embedded_route import contained_database


class IntckError(ValueError):
    pass


INTCK_SOURCES = {
    'sqlite3intck.c': '5c66e9b6e5e2a1a3e8c3348ae42dc6bee0e8b25dc328a6788912917f233b1b8a',
    'sqlite3intck.h': '28364023e640f1212e194812d26e94b191c1037adf6623be15065322fc8b5887',
}

NON_RECOVERY_DISCLAIMER = (
    'SQLite ext/intck performs incremental B-tree and index corruption diagnostics across unlocked '
    'read batches so writers are not continuously blocked. It is less exhaustive than full PRAGMA '
    'integrity_check and never repairs or recovers damaged data (use Recover SQLite file for reconstruction).'
)


def digest_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def file_identity(path: str | Path) -> dict:
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode):
        raise IntckError('Incremental integrity check target must be a regular SQLite file')
    return {'device': int(info.st_dev), 'inode': int(info.st_ino), 'size': int(info.st_size)}


def installed_library() -> str:
    name = (
        'cdeadmin_sqlite_intck.dll' if os.name == 'nt'
        else 'libcdeadmin_sqlite_intck.dylib' if sys.platform == 'darwin'
        else 'libcdeadmin_sqlite_intck.so'
    )
    candidates = [
        Path(prefix) / folder / name
        for prefix in dict.fromkeys((sys.prefix, sys.base_prefix))
        for folder in ('bin', 'lib', 'DLLs')
    ]
    candidates.append(Path(__file__).resolve().parents[2] / 'native' / name)
    env_lib = os.environ.get('CDEADMIN_SQLITE_INTCK_LIBRARY')
    if env_lib:
        candidates.insert(0, Path(env_lib))
    return next((str(p) for p in candidates if p.is_file() and Path(str(p) + '.json').is_file()), '')


def _runtime_range() -> dict:
    from .native_helpers import HELPER_MINIMUM
    from .provider import PROFILE
    return {'floor': PROFILE.minimum_version, 'minimum': HELPER_MINIMUM['intck']}


def _run_worker(spec: dict, workspace_dir: Path, timeout: int = 60) -> tuple[dict, dict]:
    worker = Path(__file__).with_name('intck_worker.py')
    observed = observe_process(
        [sys.executable, '-I', '-B', str(worker)],
        workspace=str(workspace_dir),
        environment=dict(os.environ),
        input_bytes=json.dumps(spec, ensure_ascii=True).encode('ascii'),
        input_stream=None,
        timeout=timeout,
        capture_limit=1024 * 1024,
    )
    try:
        reply = json.loads(observed['stdout'])
        if not isinstance(reply, dict):
            raise ValueError()
    except (ValueError, TypeError):
        reply = {'completed': False, 'error_type': 'NativeIntckReplyUnavailable'}
    receipt = {k: v for k, v in observed.items() if k not in {'stdout', 'stderr'}}
    return reply, receipt


def verify_library(library_path: str) -> dict:
    if not isinstance(library_path, str) or not library_path:
        raise IntckError('Native SQLite incremental integrity-check library is unavailable on this host')
    lib = Path(library_path).resolve(strict=True)
    if not lib.is_file():
        raise IntckError('Native SQLite intck helper library file does not exist')
    sha = digest_file(lib)
    manifest = Path(str(lib) + '.json')
    if not manifest.is_file() or manifest.stat().st_size > 16384:
        raise IntckError('Native SQLite intck provenance sidecar is missing or invalid')
    prov = json.loads(manifest.read_text(encoding='utf-8'))
    from .native_helpers import built_against_admitted
    if (
        prov.get('library_sha256') != sha
        or prov.get('adapter_abi') != 1
        or not built_against_admitted('intck', prov.get('sqlite_version'))
        or any(prov.get(k) != v for k, v in INTCK_SOURCES.items())
    ):
        raise IntckError('Native SQLite intck helper build provenance does not match the qualified profile')
    with tempfile.TemporaryDirectory(prefix='sr-intck-probe-') as tmp:
        reply, obs = _run_worker(
            {'action': 'probe', 'library': str(lib), 'library_sha256': sha, 'runtime_range': _runtime_range()},
            Path(tmp),
            timeout=15,
        )
    if obs['return_code'] != 0 or reply.get('available') is not True:
        raise IntckError(reply.get('error_message') or 'Native SQLite intck library is not usable with this runtime')
    return {
        'library': str(lib),
        'library_sha256': sha,
        'provenance_sha256': digest_file(manifest),
        'intck_sources': INTCK_SOURCES,
        'native': reply['native'],
        'execution_host': {'name': socket.gethostname(), 'platform': sys.platform},
    }


def resolve_target(route: dict) -> Path:
    path = Path(contained_database(route))
    if str(path) == ':memory:' or not path.is_file():
        raise IntckError('SQLite incremental integrity check requires an existing file-backed SQLite database')
    return path.resolve(strict=True)


def run_batch(
    library_info: dict,
    target_path: Path,
    *,
    schema_name: str = 'main',
    skip_steps: int = 0,
    max_steps: int = 200,
    unlock_interval: int = 16,
    timeout: int = 60,
) -> tuple[dict, dict]:
    if type(max_steps) is not int or not 1 <= max_steps <= 100000:
        raise IntckError('max_steps must be an integer between 1 and 100,000')
    if type(unlock_interval) is not int or not 1 <= unlock_interval <= 10000:
        raise IntckError('unlock_interval must be an integer between 1 and 10,000')
    if type(skip_steps) is not int or skip_steps < 0:
        raise IntckError('skip_steps must be a non-negative integer')
    spec = {
        'action': 'check',
        'library': library_info['library'],
        'library_sha256': library_info['library_sha256'],
        'runtime_range': _runtime_range(),
        'database_path': str(target_path),
        'schema_name': schema_name,
        'skip_steps': skip_steps,
        'max_steps': max_steps,
        'unlock_interval': unlock_interval,
    }
    with tempfile.TemporaryDirectory(prefix='sr-intck-step-') as tmp:
        return _run_worker(spec, Path(tmp), timeout=timeout)
