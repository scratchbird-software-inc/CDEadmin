"""Portable identities for large payload test cases, and the native SQLite
CLI that matches this interpreter."""
import hashlib
import os
from pathlib import Path
import sqlite3

# Native schema binding needs a CLI built from exactly this interpreter's
# SQLite; the application checks its version and source ID. bootstrap.py
# builds pinned releases under the reference runtime. An explicit setting wins.
_REFERENCE_CLI = (Path(__file__).resolve().parents[1] /
                  'reference_engine_demos/runtime' /
                  f'sqlite-{sqlite3.sqlite_version}/bin/sqlite3')
if 'CDEADMIN_SQLITE_BINARY' not in os.environ and _REFERENCE_CLI.is_file():
    os.environ['CDEADMIN_SQLITE_BINARY'] = str(_REFERENCE_CLI)


def pytest_make_parametrize_id(config, val, argname):
    # pytest exports the current node ID in PYTEST_CURRENT_TEST. Windows
    # limits an environment value to 32,767 characters; payload contents
    # belong in assertions rather than the test's process environment.
    if isinstance(val, (str, bytes)) and len(val) > 128:
        raw = val.encode('utf-8', errors='surrogatepass') if isinstance(val, str) else val
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return f'{argname}-{type(val).__name__}-{len(val)}-{digest}'
    return None
