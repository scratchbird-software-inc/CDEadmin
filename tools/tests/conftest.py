"""Portable identities for large payload test cases, and the native SQLite
CLI, headers and helpers that match this interpreter."""
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

_RUNTIME = Path(__file__).resolve().parents[1] / 'reference_engine_demos/runtime'

# Native schema binding needs a CLI built from exactly this interpreter's
# SQLite; the application checks its version and source ID. bootstrap.py
# builds pinned releases under the reference runtime. An explicit setting wins.
_REFERENCE_CLI = _RUNTIME / f'sqlite-{sqlite3.sqlite_version}/bin/sqlite3'
if 'CDEADMIN_SQLITE_BINARY' not in os.environ and _REFERENCE_CLI.is_file():
    os.environ['CDEADMIN_SQLITE_BINARY'] = str(_REFERENCE_CLI)

# sqlite_tracked.py builds headers and native helpers per tracked version.
# Extension fixtures compile against headers of this interpreter's version.
_TRACKED = _RUNTIME / 'sqlite-tracked' / sqlite3.sqlite_version
if 'CDEADMIN_SQLITE_HEADERS' not in os.environ and (_TRACKED / 'include/sqlite3ext.h').is_file():
    os.environ['CDEADMIN_SQLITE_HEADERS'] = str(_TRACKED / 'include')

# A helper links libsqlite3 and refuses a connection whose SQLite is another
# copy. Select the tracked helpers only when loading each one beside this
# interpreter's sqlite3 still maps exactly one libsqlite3 file. The probe runs
# in a child so this process never loads a second copy. Explicit settings win.
_HELPERS = {'CDEADMIN_SQLITE_SESSION_LIBRARY': 'session/libcdeadmin_sqlite_sessions.so',
            'CDEADMIN_SQLITE_ARRAY_LIBRARY': 'array/libcdeadmin_sqlite_arrays.so',
            'CDEADMIN_SQLITE_PREUPDATE_LIBRARY': 'preupdate/libcdeadmin_sqlite_preupdate.so',
            'CDEADMIN_SQLITE_RECOVERY_LIBRARY': 'recovery/libcdeadmin_sqlite_recovery.so'}
_PROBE = '''import ctypes, sqlite3, sys
def loaded():
    with open("/proc/self/maps") as maps:
        return {line.split()[-1] for line in maps if "/libsqlite3." in line}
before = loaded()
ctypes.CDLL(sys.argv[1])
raise SystemExit(0 if len(before) == 1 and loaded() == before else 1)
'''


def _single_sqlite(library):
    try:
        return subprocess.run([sys.executable, '-I', '-c', _PROBE, str(library)],
                              capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


if sys.platform.startswith('linux'):
    for _name, _relative in _HELPERS.items():
        _library = _TRACKED / 'helpers' / _relative
        if (_name not in os.environ and _library.is_file() and
                Path(str(_library) + '.json').is_file() and _single_sqlite(_library)):
            os.environ[_name] = str(_library)


def pytest_make_parametrize_id(config, val, argname):
    # pytest exports the current node ID in PYTEST_CURRENT_TEST. Windows
    # limits an environment value to 32,767 characters; payload contents
    # belong in assertions rather than the test's process environment.
    if isinstance(val, (str, bytes)) and len(val) > 128:
        raw = val.encode('utf-8', errors='surrogatepass') if isinstance(val, str) else val
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return f'{argname}-{type(val).__name__}-{len(val)}-{digest}'
    return None
