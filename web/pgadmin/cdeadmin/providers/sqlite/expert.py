"""Native SQLite Expert Index Advisor admission and preview-only analysis (SQ-AUD-10)."""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile

from ...sdk.tool_process import observe_process
from ..embedded_route import contained_database


class ExpertError(ValueError):
    pass


EXPERT_SOURCES = {
    'sqlite3expert.c': 'e4a43ce024798071e9b436918e9ab12c30e0fe4a691a7967ae0a78d1267b976f',
    'sqlite3expert.h': '9b8aa403e9c6e77ab2049434b02a5901ee687fb78b247aa6557500455294bc77',
}


def digest_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def installed_library() -> str:
    name = (
        'cdeadmin_sqlite_expert.dll' if os.name == 'nt'
        else 'libcdeadmin_sqlite_expert.dylib' if sys.platform == 'darwin'
        else 'libcdeadmin_sqlite_expert.so'
    )
    candidates = [
        Path(prefix) / folder / name
        for prefix in dict.fromkeys((sys.prefix, sys.base_prefix))
        for folder in ('bin', 'lib', 'DLLs')
    ]
    candidates.append(Path(__file__).resolve().parents[2] / 'native' / name)
    env_lib = os.environ.get('CDEADMIN_SQLITE_EXPERT_LIBRARY')
    if env_lib:
        candidates.insert(0, Path(env_lib))
    return next((str(p) for p in candidates if p.is_file() and Path(str(p) + '.json').is_file()), '')


def _runtime_range() -> dict:
    from .native_helpers import HELPER_MINIMUM
    from .provider import PROFILE
    return {'floor': PROFILE.minimum_version, 'minimum': HELPER_MINIMUM['expert']}


def _run_worker(spec: dict, workspace_dir: Path, timeout: int = 60) -> tuple[dict, dict]:
    worker = Path(__file__).with_name('expert_worker.py')
    observed = observe_process(
        [sys.executable, '-I', '-B', str(worker)],
        workspace=str(workspace_dir),
        environment=dict(os.environ),
        input_bytes=json.dumps(spec, ensure_ascii=True).encode('ascii'),
        input_stream=None,
        timeout=timeout,
        capture_limit=2 * 1024 * 1024,
    )
    try:
        reply = json.loads(observed['stdout'])
        if not isinstance(reply, dict):
            raise ValueError()
    except (ValueError, TypeError):
        reply = {'completed': False, 'error_type': 'NativeExpertReplyUnavailable'}
    receipt = {k: v for k, v in observed.items() if k not in {'stdout', 'stderr'}}
    return reply, receipt


def verify_library(library_path: str) -> dict:
    if not isinstance(library_path, str) or not library_path:
        raise ExpertError('Native SQLite expert index advisor helper library is unavailable on this host')
    lib = Path(library_path).resolve(strict=True)
    if not lib.is_file():
        raise ExpertError('Native SQLite expert helper library file does not exist')
    sha = digest_file(lib)
    manifest = Path(str(lib) + '.json')
    if not manifest.is_file() or manifest.stat().st_size > 16384:
        raise ExpertError('Native SQLite expert provenance sidecar is missing or invalid')
    prov = json.loads(manifest.read_text(encoding='utf-8'))
    from .native_helpers import built_against_admitted
    if (
        prov.get('library_sha256') != sha
        or prov.get('adapter_abi') != 1
        or not built_against_admitted('expert', prov.get('sqlite_version'))
        or any(prov.get(k) != v for k, v in EXPERT_SOURCES.items())
    ):
        raise ExpertError('Native SQLite expert helper build provenance does not match the qualified profile')
    with tempfile.TemporaryDirectory(prefix='sr-expert-probe-') as tmp:
        reply, obs = _run_worker(
            {'action': 'probe', 'library': str(lib), 'library_sha256': sha, 'runtime_range': _runtime_range()},
            Path(tmp),
            timeout=15,
        )
    if obs['return_code'] != 0 or reply.get('available') is not True:
        raise ExpertError(reply.get('error_message') or 'Native SQLite expert library is not usable with this runtime')
    return {
        'library': str(lib),
        'library_sha256': sha,
        'provenance_sha256': digest_file(manifest),
        'expert_sources': EXPERT_SOURCES,
        'native': reply['native'],
        'execution_host': {'name': socket.gethostname(), 'platform': sys.platform},
    }


def analyze_queries(route: dict, library_path: str, request: dict) -> dict:
    if not isinstance(request, dict) or set(request) - {'queries', 'sample_percent', 'timeout_seconds'}:
        raise ExpertError('Select queries and optional sample_percent/timeout_seconds for expert index analysis')
    queries = request.get('queries')
    if not isinstance(queries, list) or not 1 <= len(queries) <= 16:
        raise ExpertError('Supply 1 to 16 SQL queries for expert index analysis')
    cleaned_queries = []
    for q in queries:
        if not isinstance(q, str) or not q.strip() or '\x00' in q or len(q.encode('utf-8')) > 65536:
            raise ExpertError('Each expert analysis query must be bounded non-empty UTF-8 SQL text')
        cleaned_queries.append(q.strip())

    sample_pct = request.get('sample_percent', 20)
    if type(sample_pct) is not int or not 0 <= sample_pct <= 100:
        raise ExpertError('sample_percent must be an integer between 0 and 100')
    timeout = request.get('timeout_seconds', 30)
    if type(timeout) is not int or not 1 <= timeout <= 120:
        raise ExpertError('timeout_seconds must be an integer between 1 and 120')

    db_path = Path(contained_database(route))
    if str(db_path) == ':memory:' or not db_path.is_file():
        raise ExpertError('SQLite expert index advisor requires an existing file-backed SQLite database')
    db_path = db_path.resolve(strict=True)

    with closing(sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)) as check_conn:
        before_schema_ver = int(check_conn.execute('PRAGMA main.schema_version').fetchone()[0])

    lib_info = verify_library(library_path)
    spec = {
        'action': 'analyze',
        'library': lib_info['library'],
        'library_sha256': lib_info['library_sha256'],
        'runtime_range': _runtime_range(),
        'database_path': str(db_path),
        'queries': cleaned_queries,
        'sample_percent': sample_pct,
    }
    with tempfile.TemporaryDirectory(prefix='sr-expert-run-') as tmp:
        reply, receipt = _run_worker(spec, Path(tmp), timeout=timeout)
    if receipt['return_code'] != 0 or not reply.get('completed'):
        raise ExpertError(reply.get('error_message') or 'SQLite expert analysis failed')

    with closing(sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)) as after_conn:
        after_schema_ver = int(after_conn.execute('PRAGMA main.schema_version').fetchone()[0])

    return {
        'advisor': 'sqlite3expert',
        'experimental_status': 'experimental-preview-only',
        'experimental_notice': (
            'SQLite ext/expert is an experimental preview-only index advisor. '
            'No indexes were created on the target database; submit chosen CREATE INDEX DDL through ScratchRobin schema review.'
        ),
        'indexes_applied': False,
        'read_only_verified': True,
        'schema_version_before': before_schema_ver,
        'schema_version_after': after_schema_ver,
        'sample_percent': reply['sample_percent'],
        'statement_count': reply['statement_count'],
        'candidates': reply['candidates'],
        'candidates_ddl': reply['candidates_ddl'],
        'statements': reply['statements'],
        'provenance': lib_info,
        'process_receipt': receipt,
    }
