"""Isolated SQLite RBU (Resumable Bulk Update & Vacuum) C API worker (SQ-AUD-09).

Runs with Python -I -B. Links libcdeadmin_sqlite_rbu and verifies exact runtime
version + sqlite_source_id agreement before opening or stepping RBU handles.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

STATE_NAMES = {
    1: 'OAL',
    2: 'MOVE',
    3: 'CHECKPOINT',
    4: 'DONE',
    5: 'ERROR',
}


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
        raise ValueError('Native SQLite RBU helper library changed on disk')
    dll_dir = os.add_dll_directory(str(path.parent)) if os.name == 'nt' else None
    try:
        api = ctypes.CDLL(str(path))
    finally:
        if dll_dir is not None:
            dll_dir.close()

    vp, cint, ci64, cstr = ctypes.c_void_p, ctypes.c_int, ctypes.c_int64, ctypes.c_char_p
    decls = {
        'cdeadmin_sqlite_rbu_abi': ([], cint),
        'cdeadmin_sqlite3_libversion': ([], cstr),
        'cdeadmin_sqlite3_sourceid': ([], cstr),
        'cdeadmin_sqlite3_errstr': ([cint], cstr),
        'cdeadmin_sqlite3_free': ([vp], None),
        'sqlite3rbu_open': ([cstr, cstr, cstr], vp),
        'sqlite3rbu_vacuum': ([cstr, cstr], vp),
        'sqlite3rbu_step': ([vp], cint),
        'sqlite3rbu_savestate': ([vp], cint),
        'sqlite3rbu_close': ([vp, ctypes.POINTER(vp)], cint),
        'sqlite3rbu_progress': ([vp], ci64),
        'sqlite3rbu_bp_progress': ([vp, ctypes.POINTER(cint), ctypes.POINTER(cint)], None),
        'sqlite3rbu_state': ([vp], cint),
        'sqlite3rbu_temp_size': ([vp], ci64),
        'sqlite3rbu_temp_size_limit': ([vp, ci64], ci64),
    }
    for fn_name, (argtypes, restype) in decls.items():
        fn = getattr(api, fn_name)
        fn.argtypes = argtypes
        fn.restype = restype

    if api.cdeadmin_sqlite_rbu_abi() != 1:
        raise ValueError('Native SQLite RBU adapter ABI mismatch')
    lib_ver = api.cdeadmin_sqlite3_libversion().decode('ascii')
    lib_src = api.cdeadmin_sqlite3_sourceid().decode('ascii')
    probe = sqlite3.connect(':memory:')
    try:
        py_src = probe.execute('SELECT sqlite_source_id()').fetchone()[0]
    finally:
        probe.close()
    if lib_ver != sqlite3.sqlite_version or lib_src != py_src:
        raise ValueError('RBU helper library and Python sqlite3 runtime are different SQLite builds')
    rr = spec['runtime_range']
    if _ver_key(lib_ver) < _ver_key(rr['floor']) or _ver_key(lib_ver) < _ver_key(rr['minimum']):
        raise ValueError('SQLite runtime is older than the RBU helper minimum')
    return api, {'version': lib_ver, 'source_id': lib_src, 'adapter_abi': 1, 'library_sha256': spec['library_sha256']}


def _run(spec):
    api, native = _load_api(spec)
    action = spec['action']
    if action == 'probe':
        return {'completed': True, 'available': True, 'native': native}
    if action != 'step':
        raise ValueError('Unsupported RBU worker action')

    mode = spec['mode']
    target_b = spec['target_path'].encode('utf-8')
    state_b = spec['state_path'].encode('utf-8') if spec.get('state_path') else None
    step_budget = int(spec['step_budget'])
    temp_limit = int(spec.get('temp_size_limit') or 0)
    save_on_pause = bool(spec.get('savestate', True))

    if mode == 'vacuum':
        handle = api.sqlite3rbu_vacuum(target_b, state_b)
    elif mode == 'update':
        rbu_b = spec['rbu_path'].encode('utf-8')
        handle = api.sqlite3rbu_open(target_b, rbu_b, state_b)
    else:
        raise ValueError('Unsupported RBU mode')
    if not handle:
        raise RuntimeError('sqlite3rbu_open/vacuum returned NULL')

    err_ptr = ctypes.c_void_p(0)
    steps_taken = 0
    last_step_rc = sqlite3.SQLITE_OK
    savestate_rc = sqlite3.SQLITE_OK
    try:
        if temp_limit > 0:
            api.sqlite3rbu_temp_size_limit(handle, temp_limit)
        for _ in range(step_budget):
            rc = api.sqlite3rbu_step(handle)
            steps_taken += 1
            last_step_rc = rc
            if rc != sqlite3.SQLITE_OK:
                break
        state_code = api.sqlite3rbu_state(handle)
        ops_progress = int(api.sqlite3rbu_progress(handle))
        bp_one = ctypes.c_int(0)
        bp_two = ctypes.c_int(0)
        api.sqlite3rbu_bp_progress(handle, ctypes.byref(bp_one), ctypes.byref(bp_two))
        temp_bytes = int(api.sqlite3rbu_temp_size(handle))
        if last_step_rc == sqlite3.SQLITE_OK and save_on_pause:
            savestate_rc = api.sqlite3rbu_savestate(handle)
    finally:
        close_rc = api.sqlite3rbu_close(handle, ctypes.byref(err_ptr))
        err_msg = None
        if err_ptr.value:
            err_msg = ctypes.cast(err_ptr.value, ctypes.c_char_p).value.decode('utf-8', errors='replace')
            api.cdeadmin_sqlite3_free(err_ptr)

    done = close_rc == sqlite3.SQLITE_DONE or last_step_rc == sqlite3.SQLITE_DONE
    ok = close_rc in (sqlite3.SQLITE_OK, sqlite3.SQLITE_DONE) and savestate_rc == sqlite3.SQLITE_OK
    return {
        'completed': ok,
        'done': done,
        'suspended': ok and not done,
        'steps_executed': steps_taken,
        'step_rc': int(last_step_rc),
        'savestate_rc': int(savestate_rc),
        'close_rc': int(close_rc),
        'rbu_state_code': int(state_code),
        'rbu_state': STATE_NAMES.get(int(state_code), 'UNKNOWN'),
        'key_value_operations': ops_progress,
        'stage1_permyriad': int(bp_one.value),
        'stage2_permyriad': int(bp_two.value),
        'temp_bytes': temp_bytes,
        'error_message': err_msg,
        'native': native,
    }


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
