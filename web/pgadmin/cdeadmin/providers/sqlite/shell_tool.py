"""Declared External Shell (`sqlite-shell`) and Matching CLI Qualification (SQ-AUD-13).

Enforces exact `sqlite_version()` + `sqlite_source_id()` agreement between the loaded
Python `sqlite3` library and `CDEADMIN_SQLITE_BINARY`, failing closed on mismatch.
Executes strictly allowlisted read-only dot-commands in `-readonly -safe -batch` child
processes with separate process receipts, never passing dot-commands to SQL `execute`.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import sys
import tempfile

from flask import current_app, has_app_context

from ...sdk.tool_process import observe_process
from ..embedded_route import contained_database
from .provider import PROFILE


class SQLiteShellError(ValueError):
    pass


ALLOWED_DOT_COMMANDS = {
    'dbinfo': '.dbinfo',
    'schema': '.schema',
    'fullschema': '.fullschema',
    'tables': '.tables',
    'indexes': '.indexes',
    'vfsinfo': '.vfsinfo',
}


def digest_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def python_runtime_identity() -> dict:
    with closing(sqlite3.connect(':memory:')) as probe:
        ver, src_id = probe.execute('SELECT sqlite_version(), sqlite_source_id()').fetchone()
    if ver != sqlite3.sqlite_version or not PROFILE.accepts_runtime_version(ver):
        raise SQLiteShellError(f'Loaded Python sqlite3 library ({ver}) is outside admitted runtime range')
    return {'version': str(ver), 'source_id': str(src_id)}


def resolve_cli_binary(explicit_path: str | None = None) -> Path:
    configured = explicit_path
    if not configured and has_app_context():
        configured = current_app.config.get('CDEADMIN_SQLITE_BINARY')
    configured = configured or os.environ.get('CDEADMIN_SQLITE_BINARY')
    suffix = '.exe' if os.name == 'nt' else ''
    candidates = (
        [configured]
        if configured
        else [
            *(str(Path(prefix) / 'bin' / ('sqlite3' + suffix)) for prefix in dict.fromkeys((sys.prefix, sys.base_prefix))),
            shutil.which('sqlite3' + suffix),
        ]
    )
    selected = next((Path(p).resolve() for p in candidates if p and Path(p).is_file()), None)
    if selected is None:
        raise SQLiteShellError('Native sqlite3 CLI binary is unavailable on this application host')
    return selected


def _cli_supports_safe_flag(version_text: str) -> bool:
    try:
        parts = tuple(int(p) for p in str(version_text).split('.')[:3])
        return parts >= (3, 37, 0)
    except (TypeError, ValueError):
        return False


def verify_matching_cli(explicit_path: str | None = None) -> dict:
    py_rt = python_runtime_identity()
    exe = resolve_cli_binary(explicit_path)
    sha_before = digest_file(exe)
    with tempfile.TemporaryDirectory(prefix='sr-sqlite-cli-probe-') as tmp:
        observed = observe_process(
            [
                str(exe),
                '-batch',
                '-bail',
                '-json',
                ':memory:',
                'SELECT sqlite_version() AS version, sqlite_source_id() AS source_id;',
            ],
            workspace=tmp,
            environment=dict(os.environ),
            input_bytes=b'',
            input_stream=None,
            timeout=15,
            capture_limit=65536,
        )
    sha_after = digest_file(exe)
    if sha_before != sha_after:
        raise SQLiteShellError('sqlite3 CLI binary changed during provenance verification')
    if observed['return_code'] != 0:
        raise SQLiteShellError('sqlite3 CLI failed provenance probe: ' + observed.get('stderr', '').decode('utf-8', errors='replace')[:200])
    try:
        rows = json.loads(observed['stdout'].decode('utf-8'))
        cli_ver = str(rows[0]['version'])
        cli_src = str(rows[0]['source_id'])
    except Exception as exc:
        raise SQLiteShellError('sqlite3 CLI returned unreadable JSON provenance output') from exc

    matched = (cli_ver == py_rt['version'] and cli_src == py_rt['source_id'])
    if not matched:
        raise SQLiteShellError(
            f'SQLite CLI provenance mismatch: Python runtime is {py_rt["version"]} ({py_rt["source_id"]}), '
            f'but sqlite3 CLI at {exe} is {cli_ver} ({cli_src}); refusing mismatched external shell execution'
        )
    safe_supported = _cli_supports_safe_flag(cli_ver)
    return {
        'matched': True,
        'binary_path': str(exe),
        'binary_sha256': sha_after,
        'safe_flag_supported': safe_supported,
        'python_runtime': py_rt,
        'cli_runtime': {'version': cli_ver, 'source_id': cli_src},
        'execution_host': {'name': socket.gethostname(), 'platform': sys.platform},
        'probe_receipt': {k: v for k, v in observed.items() if k not in {'stdout', 'stderr'}},
    }


def run_dot_command(route: dict, request: dict, *, explicit_binary: str | None = None) -> dict:
    if not isinstance(request, dict) or set(request) - {'command', 'pattern', 'indent'}:
        raise SQLiteShellError('Select an allowlisted read-only sqlite-shell dot command')
    cmd_key = request.get('command')
    if cmd_key not in ALLOWED_DOT_COMMANDS:
        raise SQLiteShellError(
            'Unsupported or unsafe dot-command; allowed read-only commands: ' + ', '.join(sorted(ALLOWED_DOT_COMMANDS))
        )
    pattern = request.get('pattern')
    if pattern is not None:
        if not isinstance(pattern, str) or not re.fullmatch(r'[A-Za-z0-9_.*%\-]{1,128}', pattern):
            raise SQLiteShellError('Optional dot-command table pattern must be a simple 1..128 identifier/wildcard pattern')
        if cmd_key not in {'schema', 'tables', 'indexes'}:
            raise SQLiteShellError(f'Dot-command .{cmd_key} does not accept a table pattern')

    db_path = Path(contained_database(route))
    if str(db_path) == ':memory:' or not db_path.is_file():
        raise SQLiteShellError('sqlite-shell dot-command inspection requires an existing file-backed SQLite database')
    db_path = db_path.resolve(strict=True)

    provenance = verify_matching_cli(explicit_binary)
    dot_expr = ALLOWED_DOT_COMMANDS[cmd_key]
    if cmd_key == 'schema' and request.get('indent') is True:
        dot_expr += ' --indent'
    if pattern:
        dot_expr += f' {pattern}'

    safe_args = ['-safe'] if provenance.get('safe_flag_supported') else []
    with tempfile.TemporaryDirectory(prefix='sr-sqlite-shell-') as tmp:
        observed = observe_process(
            [
                provenance['binary_path'],
                '-readonly',
                *safe_args,
                '-batch',
                '-bail',
                str(db_path),
                dot_expr,
            ],
            workspace=tmp,
            environment=dict(os.environ),
            input_bytes=b'',
            input_stream=None,
            timeout=30,
            capture_limit=4 * 1024 * 1024,
        )
    stdout_text = observed['stdout'].decode('utf-8', errors='replace')
    stderr_text = observed['stderr'].decode('utf-8', errors='replace')
    if observed['return_code'] != 0:
        raise SQLiteShellError(f'sqlite3 {dot_expr} failed: {stderr_text[:300]}')
    return {
        'tool_id': 'sqlite-shell',
        'command': dot_expr,
        'sql_execute_dispatched': False,
        'read_only_safe_mode': True,
        'output': stdout_text,
        'stderr': stderr_text,
        'provenance': provenance,
        'process_receipt': {k: v for k, v in observed.items() if k not in {'stdout', 'stderr'}},
    }
