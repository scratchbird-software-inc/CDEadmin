"""Version policy for the native SQLite helper libraries.

Owner direction, 2026-10-29: SQLite is supported from a declared floor, with
version-specific features gated per runtime. Each helper's minimum is the
oldest tracked SQLite version whose headers it compiles against with no
implicit declarations and no unresolved SQLite symbols (build matrix over
the tracked versions 3.35.0 / 3.45.1 / 3.53.0, 2026-10-29). The true minimum
lies between the previous tracked version and the value below:

- preupdate, recovery: built on 3.45.1, not on 3.35.0 (client-data API;
  the pinned recover source needs newer file-control and vtab constants).
- session, array: built on 3.53.0 only (sqlite3changeset_apply_v3_strm and
  the core CARRAY binding constants are newer than 3.45.1).

A helper also refuses at load time any runtime older than the headers it was
built with, and only accepts the library instance that opened the connection.
"""

import sqlite3

from .provider import PROFILE

HELPER_MINIMUM = {
    'session': '3.53.0',
    'preupdate': '3.45.1',
    'array': '3.53.0',
    'recovery': '3.45.1',
}


def _version(text):
    return tuple(int(part) for part in str(text).split('.'))


def helper_supported(component, runtime=None):
    """Whether the helper can serve this SQLite runtime at all."""
    runtime = runtime or sqlite3.sqlite_version
    minimum = HELPER_MINIMUM[component]
    return (PROFILE.accepts_runtime_version(runtime) and
            _version(runtime) >= _version(minimum))


def built_against_admitted(component, built, runtime=None):
    """Whether a helper built against ``built`` headers serves ``runtime``."""
    runtime = runtime or sqlite3.sqlite_version
    try:
        built_version = _version(built)
    except (TypeError, ValueError):
        return False
    return (helper_supported(component, runtime) and
            PROFILE.accepts_runtime_version(built) and
            built_version <= _version(runtime))
