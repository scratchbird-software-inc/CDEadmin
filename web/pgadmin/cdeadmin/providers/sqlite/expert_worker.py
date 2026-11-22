"""Isolated SQLite Expert Index Advisor C API worker (SQ-AUD-10).

Runs with Python -I -B. Opens the target database strictly SQLITE_OPEN_READONLY
with extension loading disabled, executes preview-only candidate analysis via
ext/expert/sqlite3expert.c, and never creates indexes on the target database.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

SQLITE_OPEN_READONLY = 0x00000001
SQLITE_OPEN_NOMUTEX = 0x00008000
EXPERT_REPORT_SQL = 1
EXPERT_REPORT_INDEXES = 2
EXPERT_REPORT_PLAN = 3
EXPERT_REPORT_CANDIDATES = 4


def _ver_key(text):
    return tuple(int(part) for part in str(text).split('.'))


def _fingerprint(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _load_api(spec):
    path = Path(spec['library']).resolve(strict=True)
    if _fingerprint(path) != spec['library_sha256']:
        raise ValueError('Native SQLite expert helper library changed on disk')
    dll_dir = os.add_dll_directory(str(path.parent)) if os.name == 'nt' else None
    try:
        api = ctypes.CDLL(str(path))
    finally:
        if dll_dir is not None:
            dll_dir.close()

    vp, cint, cstr = ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p
    decls = {
        'cdeadmin_sqlite_expert_abi': ([], cint),
        'cdeadmin_sqlite3_libversion': ([], cstr),
        'cdeadmin_sqlite3_sourceid': ([], cstr),
        'cdeadmin_sqlite3_errstr': ([cint], cstr),
        'cdeadmin_sqlite3_free': ([vp], None),
        'cdeadmin_sqlite3_open_v2': ([cstr, ctypes.POINTER(vp), cint, cstr], cint),
        'cdeadmin_sqlite3_close': ([vp], cint),
        'cdeadmin_sqlite3_enable_load_extension': ([vp, cint], cint),
        'cdeadmin_sqlite3_expert_set_sample': ([vp, cint], cint),
        'sqlite3_expert_new': ([vp, ctypes.POINTER(vp)], vp),
        'sqlite3_expert_sql': ([vp, cstr, ctypes.POINTER(vp)], cint),
        'sqlite3_expert_analyze': ([vp, ctypes.POINTER(vp)], cint),
        'sqlite3_expert_count': ([vp], cint),
        'sqlite3_expert_report': ([vp, cint, cint], cstr),
        'sqlite3_expert_destroy': ([vp], None),
    }
    for fn_name, (argtypes, restype) in decls.items():
        fn = getattr(api, fn_name)
        fn.argtypes = argtypes
        fn.restype = restype

    if api.cdeadmin_sqlite_expert_abi() != 1:
        raise ValueError('Native SQLite expert adapter ABI mismatch')
    lib_ver = api.cdeadmin_sqlite3_libversion().decode('ascii')
    lib_src = api.cdeadmin_sqlite3_sourceid().decode('ascii')
    probe = sqlite3.connect(':memory:')
    try:
        py_src = probe.execute('SELECT sqlite_source_id()').fetchone()[0]
    finally:
        probe.close()
    if lib_ver != sqlite3.sqlite_version or lib_src != py_src:
        raise ValueError('Expert helper library and Python sqlite3 runtime are different SQLite builds')
    rr = spec['runtime_range']
    if _ver_key(lib_ver) < _ver_key(rr['floor']) or _ver_key(lib_ver) < _ver_key(rr['minimum']):
        raise ValueError('SQLite runtime is older than the expert helper minimum')
    return api, {'version': lib_ver, 'source_id': lib_src, 'adapter_abi': 1, 'library_sha256': spec['library_sha256']}


def _take_err(api, err_ptr):
    if not err_ptr.value:
        return None
    msg = ctypes.cast(err_ptr.value, ctypes.c_char_p).value.decode('utf-8', errors='replace')
    api.cdeadmin_sqlite3_free(err_ptr)
    err_ptr.value = 0
    return msg


def _run(spec):
    api, native = _load_api(spec)
    action = spec['action']
    if action == 'probe':
        return {'completed': True, 'available': True, 'native': native}
    if action != 'analyze':
        raise ValueError('Unsupported expert worker action')

    db_handle = ctypes.c_void_p(0)
    rc = api.cdeadmin_sqlite3_open_v2(
        spec['database_path'].encode('utf-8'),
        ctypes.byref(db_handle),
        SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX,
        None,
    )
    if rc != sqlite3.SQLITE_OK or not db_handle.value:
        if db_handle.value:
            api.cdeadmin_sqlite3_close(db_handle)
        raise RuntimeError(f'sqlite3_open_v2(READONLY) failed with code {rc}')

    expert_handle = None
    err_ptr = ctypes.c_void_p(0)
    try:
        api.cdeadmin_sqlite3_enable_load_extension(db_handle, 0)
        expert_handle = api.sqlite3_expert_new(db_handle, ctypes.byref(err_ptr))
        err_msg = _take_err(api, err_ptr)
        if not expert_handle:
            raise ValueError(err_msg or 'sqlite3_expert_new failed')

        sample_pct = int(spec.get('sample_percent', 20))
        rc = api.cdeadmin_sqlite3_expert_set_sample(expert_handle, sample_pct)
        if rc != sqlite3.SQLITE_OK:
            raise ValueError(f'sqlite3_expert_config(EXPERT_CONFIG_SAMPLE) returned {rc}')

        for sql_text in spec['queries']:
            rc = api.sqlite3_expert_sql(expert_handle, sql_text.encode('utf-8'), ctypes.byref(err_ptr))
            err_msg = _take_err(api, err_ptr)
            if rc != sqlite3.SQLITE_OK:
                raise ValueError(err_msg or f'sqlite3_expert_sql rejected query (code {rc})')

        rc = api.sqlite3_expert_analyze(expert_handle, ctypes.byref(err_ptr))
        err_msg = _take_err(api, err_ptr)
        if rc != sqlite3.SQLITE_OK:
            raise ValueError(err_msg or f'sqlite3_expert_analyze failed (code {rc})')

        stmt_count = int(api.sqlite3_expert_count(expert_handle))
        raw_candidates = api.sqlite3_expert_report(expert_handle, 0, EXPERT_REPORT_CANDIDATES)
        candidates_text = raw_candidates.decode('utf-8', errors='replace') if raw_candidates else ''
        statements = []
        for idx in range(stmt_count):
            r_sql = api.sqlite3_expert_report(expert_handle, idx, EXPERT_REPORT_SQL)
            r_idx = api.sqlite3_expert_report(expert_handle, idx, EXPERT_REPORT_INDEXES)
            r_plan = api.sqlite3_expert_report(expert_handle, idx, EXPERT_REPORT_PLAN)
            rec_text = r_idx.decode('utf-8', errors='replace').strip() if r_idx else ''
            rec_list = [line.strip() for line in rec_text.splitlines() if line.strip()]
            statements.append({
                'ordinal': idx,
                'sql': r_sql.decode('utf-8', errors='replace') if r_sql else '',
                'recommended_indexes_ddl': rec_text,
                'recommended_indexes': rec_list,
                'query_plan': r_plan.decode('utf-8', errors='replace').strip() if r_plan else '',
            })
        return {
            'completed': True,
            'statement_count': stmt_count,
            'sample_percent': sample_pct,
            'candidates_ddl': candidates_text.strip(),
            'candidates': [line.strip() for line in candidates_text.splitlines() if line.strip()],
            'statements': statements,
            'indexes_applied': False,
            'read_only_enforced': True,
            'native': native,
        }
    finally:
        if expert_handle:
            api.sqlite3_expert_destroy(expert_handle)
        if db_handle.value:
            api.cdeadmin_sqlite3_close(db_handle)


def main():
    try:
        spec = json.loads(sys.stdin.buffer.read().decode('ascii'))
        reply = _run(spec)
        sys.stdout.write(json.dumps(reply, ensure_ascii=True))
        return 0 if reply.get('completed') else 1
    except Exception as exc:
        sys.stdout.write(json.dumps({
            'completed': False,
            'error_type': type(exc).__name__,
            'error_message': str(exc)[:400],
        }, ensure_ascii=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
