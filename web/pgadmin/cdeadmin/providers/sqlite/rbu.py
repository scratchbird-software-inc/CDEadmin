"""Native SQLite RBU (Resumable Bulk Update and Resumable Vacuum) admission and lifecycle (SQ-AUD-09)."""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import sys
import tempfile

from ...sdk.tool_process import observe_process
from ..embedded_route import contained_database
from .declarations import quote


class RBUError(ValueError):
    pass


RBU_SOURCES = {
    'sqlite3rbu.c': 'e61e5ee2a9ff281a35800a971b1e6660ef8cf519cbbb6d9c107ab5dd0003ab7b',
    'sqlite3rbu.h': '78d951c78b37cfc1e7b8614dcb23437e704565eaf7f358adb5ecc5bfbd40ceb8',
}


def digest_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def file_identity(path: str | Path) -> dict:
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode):
        raise RBUError('SQLite RBU file must be a regular file')
    return {
        'device': int(info.st_dev),
        'inode': int(info.st_ino),
        'size': int(info.st_size),
    }


def installed_library() -> str:
    name = (
        'cdeadmin_sqlite_rbu.dll' if os.name == 'nt'
        else 'libcdeadmin_sqlite_rbu.dylib' if sys.platform == 'darwin'
        else 'libcdeadmin_sqlite_rbu.so'
    )
    candidates = [
        Path(prefix) / folder / name
        for prefix in dict.fromkeys((sys.prefix, sys.base_prefix))
        for folder in ('bin', 'lib', 'DLLs')
    ]
    candidates.append(Path(__file__).resolve().parents[2] / 'native' / name)
    env_lib = os.environ.get('CDEADMIN_SQLITE_RBU_LIBRARY')
    if env_lib:
        candidates.insert(0, Path(env_lib))
    return next((str(p) for p in candidates if p.is_file() and Path(str(p) + '.json').is_file()), '')


def _runtime_range() -> dict:
    from .native_helpers import HELPER_MINIMUM
    from .provider import PROFILE
    return {'floor': PROFILE.minimum_version, 'minimum': HELPER_MINIMUM['rbu']}


def _run_worker(spec: dict, workspace_dir: Path, timeout: int = 120) -> tuple[dict, dict]:
    worker = Path(__file__).with_name('rbu_worker.py')
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
        reply = {'completed': False, 'error_type': 'NativeRBUReplyUnavailable'}
    receipt = {k: v for k, v in observed.items() if k not in {'stdout', 'stderr'}}
    return reply, receipt


def verify_library(library_path: str) -> dict:
    if not isinstance(library_path, str) or not library_path:
        raise RBUError('Native SQLite RBU helper library is unavailable on this host')
    lib = Path(library_path).resolve(strict=True)
    if not lib.is_file():
        raise RBUError('Native SQLite RBU helper library file does not exist')
    sha = digest_file(lib)
    manifest = Path(str(lib) + '.json')
    if not manifest.is_file() or manifest.stat().st_size > 16384:
        raise RBUError('Native SQLite RBU provenance sidecar is missing or invalid')
    prov = json.loads(manifest.read_text(encoding='utf-8'))
    from .native_helpers import built_against_admitted
    if (
        prov.get('library_sha256') != sha
        or prov.get('adapter_abi') != 1
        or not built_against_admitted('rbu', prov.get('sqlite_version'))
        or any(prov.get(k) != v for k, v in RBU_SOURCES.items())
    ):
        raise RBUError('Native SQLite RBU helper build provenance does not match the qualified profile')
    with tempfile.TemporaryDirectory(prefix='sr-rbu-probe-') as tmp:
        reply, obs = _run_worker(
            {'action': 'probe', 'library': str(lib), 'library_sha256': sha, 'runtime_range': _runtime_range()},
            Path(tmp),
            timeout=15,
        )
    if obs['return_code'] != 0 or reply.get('available') is not True:
        raise RBUError(reply.get('error_message') or 'Native SQLite RBU library is not usable with this runtime')
    return {
        'library': str(lib),
        'library_sha256': sha,
        'provenance_sha256': digest_file(manifest),
        'rbu_sources': RBU_SOURCES,
        'native': reply['native'],
        'execution_host': {'name': socket.gethostname(), 'platform': sys.platform},
    }


def build_rbu_package(target_db_path: Path, rbu_db_path: Path, tables_spec: list[dict]) -> dict:
    """Create a typed RBU update database (`data_<tbl>` + `rbu_control` + `rbu_count`) without raw SQL."""
    if not isinstance(tables_spec, list) or not 1 <= len(tables_spec) <= 32:
        raise RBUError('Supply 1 to 32 typed table batches for an RBU update package')
    if rbu_db_path.exists():
        raise RBUError('RBU package destination path already exists')

    with closing(sqlite3.connect(f'file:{target_db_path}?mode=ro', uri=True)) as target_conn:
        journal = str(target_conn.execute('PRAGMA main.journal_mode').fetchone()[0]).lower()
        if journal == 'wal':
            raise RBUError('SQLite RBU requires the target database not to be in active WAL mode before opening RBU')
        target_schemas = {}
        for item in tables_spec:
            if not isinstance(item, dict) or not isinstance(item.get('table'), str):
                raise RBUError('Each RBU table batch requires table name and rows')
            tname = item['table']
            row_type = target_conn.execute(
                "SELECT type FROM main.sqlite_schema WHERE name = ?", (tname,)
            ).fetchone()
            if row_type != ('table',):
                raise RBUError(f'RBU target {tname!r} must be an existing ordinary table in main')
            cols = [
                (str(c[1]), str(c[2] or ''))
                for c in target_conn.execute(f'PRAGMA main.table_xinfo({quote(tname)})').fetchall()
                if not c[6]
            ]
            if not cols or any(cname == 'rbu_control' for cname, _ in cols):
                raise RBUError(f'RBU target {tname!r} has invalid columns or already defines rbu_control')
            tlist = target_conn.execute('PRAGMA main.table_list').fetchall()
            without_rowid = any(str(r[0]) == 'main' and str(r[1]) == tname and bool(r[4]) for r in tlist)
            pks = [str(c[1]) for c in target_conn.execute(f'PRAGMA main.table_xinfo({quote(tname)})').fetchall() if c[5]]
            target_schemas[tname] = {'columns': cols, 'without_rowid': without_rowid, 'pks': pks}

    total_ops = 0
    with closing(sqlite3.connect(rbu_db_path)) as rbu_conn:
        rbu_conn.execute('CREATE TABLE rbu_count(tbl TEXT PRIMARY KEY, cnt INTEGER) WITHOUT ROWID')
        for item in tables_spec:
            tname = item['table']
            rows = item.get('operations')
            if not isinstance(rows, list) or not 1 <= len(rows) <= 100000:
                raise RBUError(f'RBU batch for {tname!r} requires 1 to 100,000 typed row operations')
            meta = target_schemas[tname]
            cols = meta['columns']
            need_rowid = not meta['pks'] and not meta['without_rowid']
            data_tbl = f'data_{tname}'
            col_defs = [f'{quote(cname)} {ctype}'.strip() for cname, ctype in cols]
            if need_rowid:
                col_defs.append('rbu_rowid INTEGER')
            col_defs.append('rbu_control')
            rbu_conn.execute(f'CREATE TABLE {quote(data_tbl)} (' + ', '.join(col_defs) + ')')

            insert_cols = [cname for cname, _ in cols] + (['rbu_rowid'] if need_rowid else []) + ['rbu_control']
            placeholders = ', '.join('?' for _ in insert_cols)
            ins_sql = f'INSERT INTO {quote(data_tbl)} (' + ', '.join(quote(c) for c in insert_cols) + f') VALUES ({placeholders})'

            batch_tuples = []
            for op in rows:
                if not isinstance(op, dict):
                    raise RBUError('Each RBU operation must be an object')
                kind = op.get('op')
                values = op.get('values') or {}
                if not isinstance(values, dict):
                    raise RBUError('RBU operation values must be an object')
                if kind == 'insert':
                    ctrl = 0
                elif kind == 'delete':
                    ctrl = 1
                elif kind == 'update':
                    mask = []
                    for cname, _ in cols:
                        mask.append('x' if cname in (op.get('set_columns') or ()) else '.')
                    if 'x' not in mask:
                        raise RBUError('RBU update operation requires at least one column in set_columns')
                    ctrl = ''.join(mask)
                else:
                    raise RBUError('RBU op must be insert, update, or delete')
                tup = [values.get(cname) for cname, _ in cols]
                if need_rowid:
                    tup.append(op.get('rbu_rowid'))
                tup.append(ctrl)
                batch_tuples.append(tuple(tup))
            rbu_conn.executemany(ins_sql, batch_tuples)
            rbu_conn.execute('INSERT INTO rbu_count(tbl, cnt) VALUES (?, ?)', (data_tbl, len(batch_tuples)))
            total_ops += len(batch_tuples)
        rbu_conn.commit()
    os.chmod(rbu_db_path, 0o600)
    return {
        'rbu_path': str(rbu_db_path),
        'rbu_sha256': digest_file(rbu_db_path),
        'rbu_identity': file_identity(rbu_db_path),
        'total_operations': total_ops,
        'tables': [item['table'] for item in tables_spec],
    }


def step_rbu_job(library_info: dict, job: dict, *, step_budget: int, timeout: int = 120) -> tuple[dict, dict]:
    if type(step_budget) is not int or not 1 <= step_budget <= 200000:
        raise RBUError('RBU step_budget must be an integer between 1 and 200,000')
    target_path = Path(job['target_path']).resolve(strict=True)
    cur_target_id = file_identity(target_path)
    if [cur_target_id['device'], cur_target_id['inode']] != [
        job['target_identity']['device'],
        job['target_identity']['inode'],
    ]:
        raise RBUError('RBU target database file was replaced; refusing to step against a different inode')
    if job['mode'] == 'update':
        rbu_path = Path(job['rbu_path']).resolve(strict=True)
        cur_rbu_id = file_identity(rbu_path)
        if [cur_rbu_id['device'], cur_rbu_id['inode']] != [
            job['rbu_identity']['device'],
            job['rbu_identity']['inode'],
        ]:
            raise RBUError('RBU source package file identity changed; refusing to resume mismatched RBU state')
    state_path = Path(job['state_path'])
    if job.get('state_identity') is not None:
        if not state_path.is_file():
            raise RBUError('RBU state database disappeared before resume')
        cur_state_id = file_identity(state_path)
        if [cur_state_id['device'], cur_state_id['inode']] != [
            job['state_identity']['device'],
            job['state_identity']['inode'],
        ]:
            raise RBUError('RBU state database identity changed; refusing to resume mismatched state')

    spec = {
        'action': 'step',
        'library': library_info['library'],
        'library_sha256': library_info['library_sha256'],
        'runtime_range': _runtime_range(),
        'mode': job['mode'],
        'target_path': str(target_path),
        'rbu_path': job.get('rbu_path'),
        'state_path': str(state_path),
        'step_budget': step_budget,
        'temp_size_limit': int(job.get('temp_size_limit') or 0),
        'savestate': True,
    }
    with tempfile.TemporaryDirectory(prefix='sr-rbu-step-') as tmp:
        return _run_worker(spec, Path(tmp), timeout=timeout)


def resolve_contained_target(route: dict) -> Path:
    path = Path(contained_database(route))
    if str(path) == ':memory:' or not path.is_file():
        raise RBUError('SQLite RBU requires an existing file-backed SQLite database')
    if route.get('read_only') is True:
        raise RBUError('SQLite RBU cannot mutate a read-only SQLite endpoint')
    return path.resolve(strict=True)
