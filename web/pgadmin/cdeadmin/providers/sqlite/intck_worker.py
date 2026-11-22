"""Isolated SQLite Incremental Integrity-Check (`ext/intck`) C API worker (SQ-AUD-11).

Runs with Python -I -B. Executes bounded `sqlite3_intck_step` batches, invokes
`sqlite3_intck_unlock` between sub-batches so readers/writers are not continuously
locked, and collects corruption diagnostics + schema/data version drift.
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
        raise ValueError('Native SQLite intck helper library changed on disk')
    dll_dir = os.add_dll_directory(str(path.parent)) if os.name == 'nt' else None
    try:
        api = ctypes.CDLL(str(path))
    finally:
        if dll_dir is not None:
            dll_dir.close()

    vp, cint, cstr = ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p
    decls = {
        'cdeadmin_sqlite_intck_abi': ([], cint),
        'cdeadmin_sqlite3_libversion': ([], cstr),
        'cdeadmin_sqlite3_sourceid': ([], cstr),
        'cdeadmin_sqlite3_errstr': ([cint], cstr),
        'cdeadmin_sqlite3_open_v2': ([cstr, ctypes.POINTER(vp), cint, cstr], cint),
        'cdeadmin_sqlite3_close': ([vp], cint),
        'cdeadmin_sqlite3_enable_load_extension': ([vp, cint], cint),
        'cdeadmin_sqlite3_scalar_int': ([vp, cstr, ctypes.POINTER(cint)], cint),
        'sqlite3_intck_open': ([vp, cstr, ctypes.POINTER(vp)], cint),
        'sqlite3_intck_step': ([vp], cint),
        'sqlite3_intck_message': ([vp], cstr),
        'sqlite3_intck_unlock': ([vp], cint),
        'sqlite3_intck_error': ([vp, ctypes.POINTER(cstr)], cint),
        'sqlite3_intck_close': ([vp], None),
    }
    for fn_name, (argtypes, restype) in decls.items():
        fn = getattr(api, fn_name)
        fn.argtypes = argtypes
        fn.restype = restype

    if api.cdeadmin_sqlite_intck_abi() != 1:
        raise ValueError('Native SQLite intck adapter ABI mismatch')
    lib_ver = api.cdeadmin_sqlite3_libversion().decode('ascii')
    lib_src = api.cdeadmin_sqlite3_sourceid().decode('ascii')
    probe = sqlite3.connect(':memory:')
    try:
        py_src = probe.execute('SELECT sqlite_source_id()').fetchone()[0]
    finally:
        probe.close()
    if lib_ver != sqlite3.sqlite_version or lib_src != py_src:
        raise ValueError('Intck helper library and Python sqlite3 runtime are different SQLite builds')
    rr = spec['runtime_range']
    if _ver_key(lib_ver) < _ver_key(rr['floor']) or _ver_key(lib_ver) < _ver_key(rr['minimum']):
        raise ValueError('SQLite runtime is older than the intck helper minimum')
    return api, {'version': lib_ver, 'source_id': lib_src, 'adapter_abi': 1, 'library_sha256': spec['library_sha256']}


def _scalar(api, db_handle, sql_text):
    out = ctypes.c_int(0)
    rc = api.cdeadmin_sqlite3_scalar_int(db_handle, sql_text.encode('utf-8'), ctypes.byref(out))
    return int(out.value) if rc == sqlite3.SQLITE_OK else None


def _run(spec):
    api, native = _load_api(spec)
    action = spec['action']
    if action == 'probe':
        return {'completed': True, 'available': True, 'native': native}
    if action != 'check':
        raise ValueError('Unsupported intck worker action')

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

    ck_handle = ctypes.c_void_p(0)
    try:
        api.cdeadmin_sqlite3_enable_load_extension(db_handle, 0)
        schema_name = spec.get('schema_name', 'main')
        q_schema = '"' + schema_name.replace('"', '""') + '"'
        schema_ver_before = _scalar(api, db_handle, f'PRAGMA {q_schema}.schema_version')
        data_ver_before = _scalar(api, db_handle, f'PRAGMA {q_schema}.data_version')

        rc = api.sqlite3_intck_open(db_handle, schema_name.encode('utf-8'), ctypes.byref(ck_handle))
        if rc != sqlite3.SQLITE_OK or not ck_handle.value:
            raise RuntimeError(f'sqlite3_intck_open failed with code {rc}')

        skip_steps = int(spec.get('skip_steps') or 0)
        max_steps = int(spec['max_steps'])
        unlock_interval = int(spec.get('unlock_interval') or 16)
        max_messages = int(spec.get('max_messages') or 100)

        total_steps = 0
        batch_steps = 0
        unlock_count = 0
        messages = []
        done = False
        err_code = sqlite3.SQLITE_OK
        err_text = None

        # Fast-forward prior completed steps if resuming a paused session, unlocking periodically
        target_total = skip_steps + max_steps
        while total_steps < target_total:
            step_rc = api.sqlite3_intck_step(ck_handle)
            total_steps += 1
            if total_steps > skip_steps:
                batch_steps += 1
            if step_rc == sqlite3.SQLITE_DONE:
                done = True
                break
            if step_rc != sqlite3.SQLITE_OK:
                err_out = ctypes.c_char_p(None)
                err_code = api.sqlite3_intck_error(ck_handle, ctypes.byref(err_out))
                err_text = err_out.value.decode('utf-8', errors='replace') if err_out.value else f'SQLite error {step_rc}'
                break
            msg_ptr = api.sqlite3_intck_message(ck_handle)
            if msg_ptr and total_steps > skip_steps and len(messages) < max_messages:
                messages.append(msg_ptr.decode('utf-8', errors='replace'))
            if unlock_interval > 0 and (total_steps % unlock_interval) == 0:
                urc = api.sqlite3_intck_unlock(ck_handle)
                unlock_count += 1
                if urc != sqlite3.SQLITE_OK:
                    err_out = ctypes.c_char_p(None)
                    err_code = api.sqlite3_intck_error(ck_handle, ctypes.byref(err_out))
                    err_text = err_out.value.decode('utf-8', errors='replace') if err_out.value else f'Unlock error {urc}'
                    break

        # Ensure read transaction is unlocked before closing ck_handle and inspecting post-versions
        if err_code == sqlite3.SQLITE_OK:
            api.sqlite3_intck_unlock(ck_handle)
            unlock_count += 1

        api.sqlite3_intck_close(ck_handle)
        ck_handle.value = 0

        schema_ver_after = _scalar(api, db_handle, f'PRAGMA {q_schema}.schema_version')
        data_ver_after = _scalar(api, db_handle, f'PRAGMA {q_schema}.data_version')

        return {
            'completed': err_code == sqlite3.SQLITE_OK,
            'done': done,
            'paused': err_code == sqlite3.SQLITE_OK and not done,
            'total_steps': total_steps,
            'batch_steps': batch_steps,
            'unlock_count': unlock_count,
            'corrupt_detected': len(messages) > 0,
            'corruption_messages': messages,
            'error_code': int(err_code),
            'error_message': err_text,
            'schema_version_before': schema_ver_before,
            'schema_version_after': schema_ver_after,
            'data_version_before': data_ver_before,
            'data_version_after': data_ver_after,
            'concurrent_drift_detected': (
                schema_ver_before != schema_ver_after or data_ver_before != data_ver_after
            ),
            'native': native,
        }
    finally:
        if ck_handle.value:
            api.sqlite3_intck_close(ck_handle)
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
