"""Isolated SQLite recovery API worker; protocol input/output contain no row data.

Run with Python -I. The application supplies a private source image and output
directory. No live provider handle or application imports cross this boundary.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time




def _runtime_supported(version, spec):
    """Floor and recovery minimum come from the parent (native_helpers)."""
    def key(text):
        return tuple(int(part) for part in str(text).split('.'))
    try:
        observed = key(version)
        return (observed >= key(spec['runtime_range']['floor']) and
                observed >= key(spec['runtime_range']['minimum']))
    except (KeyError, TypeError, ValueError):
        return False


def fingerprint(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): checksum.update(block)
    return checksum.hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.writing')
    with temporary.open('w', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=True, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def library(spec):
    path = Path(spec['library']).resolve(strict=True)
    if fingerprint(path) != spec['library_sha256']:
        raise ValueError('Native SQLite recovery library changed')
    directory = os.add_dll_directory(str(path.parent)) if os.name == 'nt' else None
    try:
        api = ctypes.CDLL(str(path))
    finally:
        if directory is not None: directory.close()
    pointer, integer, string = ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p
    declarations = {
        'sqlite3_libversion': ([], string), 'sqlite3_sourceid': ([], string),
        'sqlite3_errstr': ([integer], string),
        'sqlite3_compileoption_used': ([string], integer),
        'sqlite3_open_v2': ([string, ctypes.POINTER(pointer), integer, string], integer),
        'sqlite3_close': ([pointer], integer),
        'sqlite3_auto_extension': ([pointer], integer),
        'sqlite3_set_authorizer': ([pointer, pointer, pointer], integer),
        'sqlite3_db_filename': ([pointer, string], string),
        'sqlite3_enable_load_extension': ([pointer, integer], integer),
        'sqlite3_limit': ([pointer, integer, integer], integer),
        'sqlite3_recover_init': ([pointer, string, string], pointer),
        'sqlite3_recover_config': ([pointer, integer, pointer], integer),
        'sqlite3_recover_step': ([pointer], integer),
        'sqlite3_recover_finish': ([pointer], integer),
        'sqlite3_recover_errcode': ([pointer], integer),
    }
    for name, (arguments, result) in declarations.items():
        function = getattr(api, name if name.startswith('sqlite3_recover_') else 'cdeadmin_' + name)
        function.argtypes, function.restype = arguments, result
        setattr(api, name, function)
    abi = api.cdeadmin_sqlite_recovery_abi
    abi.argtypes, abi.restype = [], integer
    if abi() != 1: raise ValueError('Native SQLite recovery adapter ABI is unavailable')
    identity = {'version': api.sqlite3_libversion().decode('ascii'),
                'source_id': api.sqlite3_sourceid().decode('ascii'),
                'dbpage': bool(api.sqlite3_compileoption_used(b'ENABLE_DBPAGE_VTAB')),
                'library_sha256': spec['library_sha256'], 'adapter_abi': 1}
    binding = sqlite3.connect(':memory:')
    try: binding_source = binding.execute('SELECT sqlite_source_id()').fetchone()[0]
    finally: binding.close()
    identity['verification_binding_version'] = sqlite3.sqlite_version
    # The helper's library and the verifying binding must be one SQLite
    # build (same version and source); that build must be admitted, new
    # enough for the recovery helper, and compiled with DBPAGE.
    if (identity['version'] != sqlite3.sqlite_version or
            identity['source_id'] != binding_source):
        raise ValueError('Recovery helper and verifying binding are different SQLite builds')
    if not _runtime_supported(identity['version'], spec) or not identity['dbpage']:
        raise ValueError('SQLite recovery needs a supported runtime compiled with DBPAGE')
    return api, identity


def confine(api, target):
    """Guard every handle opened by the native recovery implementation.

    Recovery executes schema text from damaged pages. The qualified API needs
    one NULL/temporary attachment on its output handle; recovered SQL cannot
    attach another file, detach that guard database, or load executable code.
    """
    pointer, integer, string = ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p
    authorizer_type = ctypes.CFUNCTYPE(integer, pointer, integer, string, string, string, string)
    initialize_type = ctypes.CFUNCTYPE(integer, pointer, pointer, pointer)
    callbacks = []
    @initialize_type
    def initialize(connection, _error, _api):
        try:
            filename = api.sqlite3_db_filename(connection, b'main')
            output = bool(filename and Path(filename.decode('utf8')).resolve() == target)
            attached = False
            @authorizer_type
            def authorize(_context, action, first, second, _database, _source):
                nonlocal attached
                try:
                    if action == sqlite3.SQLITE_ATTACH:
                        if output and not attached and first in (None, b'', b':memory:'):
                            attached = True
                            return sqlite3.SQLITE_OK
                        return sqlite3.SQLITE_DENY
                    if action == sqlite3.SQLITE_DETACH: return sqlite3.SQLITE_DENY
                    if action == sqlite3.SQLITE_FUNCTION and (second or b'').lower() == b'load_extension':
                        return sqlite3.SQLITE_DENY
                    if action == sqlite3.SQLITE_PRAGMA and (first or b'').lower() in {
                            b'temp_store_directory', b'data_store_directory'}:
                        return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK
                except BaseException:
                    return sqlite3.SQLITE_DENY
            callbacks.append(authorize)
            api.sqlite3_enable_load_extension(connection, 0)
            # The internal temporary database consumes the output's sole slot.
            api.sqlite3_limit(connection, 7, 1 if output else 0)
            return api.sqlite3_set_authorizer(connection, ctypes.cast(authorize, pointer), None)
        except BaseException:
            return sqlite3.SQLITE_ERROR
    callbacks.append(initialize)
    if api.sqlite3_auto_extension(ctypes.cast(initialize, pointer)) != 0:
        raise ValueError('Native SQLite recovery connection guards could not be installed')
    # Native SQLite retains C pointers; keep every Python callback alive until
    # all recovery handles are released and this isolated process exits.
    api._recovery_callbacks = callbacks


def verify(path, progress):
    connection = sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True)
    try:
        connection.execute('PRAGMA trusted_schema=OFF')
        connection.execute('PRAGMA query_only=ON')
        if connection.execute('PRAGMA integrity_check(100)').fetchall() != [('ok',)]:
            raise ValueError('Recovered SQLite file failed native integrity checking')
        foreign = connection.execute('PRAGMA foreign_key_check').fetchmany(101)
        objects = connection.execute('SELECT name,type FROM sqlite_schema WHERE type IN (\'table\',\'view\') ORDER BY name').fetchmany(1001)
        tables = []
        for name, kind in objects[:1000]:
            if kind != 'table': continue
            progress(stage='verifying', inspected_tables=len(tables))
            try:
                count = connection.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
                tables.append({'name': name, 'row_count': str(count), 'readable': True})
            except sqlite3.Error as error:
                tables.append({'name': name, 'readable': False,
                               'native_error_code': getattr(error, 'sqlite_errorcode', None)})
        return {'integrity_check': 'ok', 'tables': tables, 'catalog_complete': len(objects) <= 1000,
                'foreign_key_violations': [{'table': row[0], 'rowid': None if row[1] is None else str(row[1]),
                                            'parent': row[2], 'constraint': row[3]} for row in foreign[:100]],
                'foreign_key_check_complete': len(foreign) <= 100,
                'application_data_verified': False}
    finally:
        connection.close()


def run(spec):
    if fingerprint(__file__) != spec.get('worker_sha256'):
        raise ValueError('The reviewed SQLite recovery worker changed')
    api, identity = library(spec)
    if spec.get('action') == 'probe': return {'available': True, 'native': identity}
    if spec.get('action') != 'recover': raise ValueError('Unknown native recovery action')
    source, target = Path(spec['source']).resolve(strict=True), Path(spec['target']).resolve()
    if not source.is_file() or target.exists() or source == target:
        raise ValueError('Recovery requires a private source image and a new output file')
    if '\x00' in str(source) or '\x00' in str(target):
        raise ValueError('Recovery filenames contain an invalid NUL')
    for name in ('SQLITE_TMPDIR', 'TMPDIR', 'TEMP', 'TMP'): os.environ[name] = str(target.parent)
    confine(api, target)
    last_progress, steps = 0, 0
    def progress(**values):
        nonlocal last_progress
        now = time.monotonic()
        if now - last_progress >= .25 or values.get('stage') == 'complete':
            write_json(spec['progress_file'], {'native_steps': steps, **values})
            last_progress = now
    progress(stage='recovering')
    handle, recovery, finish, close = ctypes.c_void_p(), None, None, None
    code = api.sqlite3_open_v2(str(source).encode('utf8'), ctypes.byref(handle), 2, None)
    try:
        if code != 0: raise ValueError('Private SQLite recovery image cannot be opened')
        recovery = api.sqlite3_recover_init(handle, b'main', str(target).encode('utf8'))
        if not recovery: raise MemoryError('Native SQLite recovery allocation failed')
        lost = ctypes.create_string_buffer(spec['options']['lost_and_found'].encode('utf8'))
        if api.sqlite3_recover_config(recovery, 1, ctypes.cast(lost, ctypes.c_void_p)) != 0:
            raise ValueError('Native lost-and-found configuration failed')
        for option, value in ((2, spec['options']['include_freelist']),
                              (3, spec['options']['preserve_rowids']), (4, True)):
            number = ctypes.c_int(int(value))
            if api.sqlite3_recover_config(recovery, option, ctypes.byref(number)) != 0:
                raise ValueError('Native SQLite recovery configuration failed')
        while True:
            code = api.sqlite3_recover_step(recovery)
            steps += 1
            progress(stage='recovering')
            if code != 0: break
        if code != 101:
            return {'completed': False, 'native': identity,
                    'native_error_code': api.sqlite3_recover_errcode(recovery),
                    'native_error_message': api.sqlite3_errstr(code).decode('utf8'), 'native_steps': steps}
    finally:
        if recovery is not None: finish = api.sqlite3_recover_finish(recovery)
        if handle.value: close = api.sqlite3_close(handle)
    if finish != 0 or close != 0:
        raise ValueError('Native SQLite recovery release failed')
    observed = verify(target, progress)
    if any(Path(str(target) + suffix).exists() and Path(str(target) + suffix).stat().st_size
           for suffix in ('-wal', '-journal')):
        raise ValueError('Recovered SQLite output still has an unmaterialized journal')
    progress(stage='complete')
    return {'completed': True, 'native': identity, 'native_steps': steps,
            'artifact_sha256': fingerprint(target), 'bytes': str(target.stat().st_size), **observed}


if __name__ == '__main__':
    os.umask(0o077)
    try:
        request = json.loads(sys.stdin.buffer.read(65537))
        response = run(request)
        print(json.dumps(response, ensure_ascii=True, allow_nan=False), flush=True)
        sys.exit(0 if response.get('available') or response.get('completed') else 1)
    except Exception as error:
        print(json.dumps({'completed': False, 'error_type': type(error).__name__,
            'error_message': str(error) if isinstance(error, ValueError) else None,
            'native_error_code': getattr(error, 'sqlite_errorcode', None)}), flush=True)
        sys.exit(1)
