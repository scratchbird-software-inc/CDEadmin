"""DuckDB Native Shell & Client Directive Integration (DU-AUD-18).

Separates client dot-directives from SQL execution:
1. Qualifies an installed ``duckdb`` CLI binary when configured/present on the
   host (verifying exact ``v1.5.2`` + ``8a5851971f`` correspondence with the
   loaded Python ``duckdb`` library, failing closed on version/source mismatch).
2. Provides a supervised, contained directive & SQL batch runner on an isolated
   dedicated DuckDB connection (never borrowing interactive user sessions, and
   never passing dot-commands to SQL ``execute``), supporting ``.mode``,
   ``.headers``, ``.separator``, ``.nullvalue``, ``.bail``, ``.echo``,
   ``.tables``, ``.schema``, ``.indexes``, ``.databases``, ``.show``,
   nested ``.read`` includes, ``.output`` / ``.once`` contained file routing,
   bounded wall-clock timeout, and cancellation via ``connection.interrupt()``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import sys
import tempfile
import threading
import time

import duckdb
from flask import current_app, has_app_context

from ...sdk.tool_process import observe_process
from ..embedded_route import contained_database, resolve_contained_path
from .provider import PROFILE


class DuckDBShellError(ValueError):
    pass


SUPPORTED_MODES = frozenset('box csv json line list markdown tsv'.split())
FORBIDDEN_DIRECTIVES = frozenset({
    '.shell', '.system', '.cd', '.open', '.exit', '.quit', '.excel', '.edit',
})
SUPPORTED_DIRECTIVES = frozenset({
    '.mode', '.headers', '.separator', '.nullvalue', '.bail', '.echo',
    '.timer', '.tables', '.schema', '.indexes', '.indices', '.databases',
    '.show', '.read', '.output', '.once', '.help',
})
MAX_INCLUDE_DEPTH = 8
MAX_OUTPUT_BYTES = 8 * 1024 * 1024


def _digest_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def python_runtime_identity() -> dict:
    con = duckdb.connect(':memory:')
    try:
        lib_ver, src_id = con.execute('SELECT library_version, source_id FROM pragma_version()').fetchone()
    finally:
        con.close()
    clean_ver = str(lib_ver).lstrip('v')
    if clean_ver != duckdb.__version__ or not PROFILE.accepts_runtime_version(clean_ver):
        raise DuckDBShellError(f'Loaded Python duckdb library ({lib_ver}) is outside admitted 1.5.2 profile')
    return {
        'version': clean_ver,
        'library_version': str(lib_ver),
        'source_id': str(src_id),
    }


def resolve_cli_binary(explicit_path: str | None = None) -> Path | None:
    configured = explicit_path
    if not configured and has_app_context():
        configured = current_app.config.get('CDEADMIN_DUCKDB_BINARY')
    configured = configured or os.environ.get('CDEADMIN_DUCKDB_BINARY')
    suffix = '.exe' if os.name == 'nt' else ''
    if configured:
        p = Path(configured)
        if not p.is_file():
            raise DuckDBShellError(f'Configured DuckDB CLI binary does not exist: {configured}')
        return p.resolve()
    candidates = [
        *(str(Path(prefix) / 'bin' / ('duckdb' + suffix)) for prefix in dict.fromkeys((sys.prefix, sys.base_prefix))),
        shutil.which('duckdb' + suffix),
    ]
    return next((Path(c).resolve() for c in candidates if c and Path(c).is_file()), None)


def inspect_shell_provenance(explicit_binary: str | None = None) -> dict:
    py_rt = python_runtime_identity()
    exe = resolve_cli_binary(explicit_binary)
    host_info = {'name': socket.gethostname(), 'platform': sys.platform}
    if exe is None:
        return {
            'cli_available': False,
            'matched': False,
            'host_mode': 'python_supervised_directive_runner',
            'binary_path': None,
            'binary_sha256': None,
            'python_runtime': py_rt,
            'cli_runtime': None,
            'execution_host': host_info,
            'supported_directives': sorted(SUPPORTED_DIRECTIVES),
            'forbidden_directives': sorted(FORBIDDEN_DIRECTIVES),
            'notes': [
                'No standalone duckdb CLI binary is installed on this host; supervised directive execution uses an isolated Python duckdb 1.5.2 connection.',
                'Dot-commands are parsed by the directive supervisor and are never submitted as SQL.',
            ],
        }

    sha_before = _digest_file(exe)
    with tempfile.TemporaryDirectory(prefix='sr-duckdb-cli-probe-') as tmp:
        observed = observe_process(
            [
                str(exe),
                '-batch',
                '-json',
                ':memory:',
                'SELECT library_version, source_id FROM pragma_version();',
            ],
            workspace=tmp,
            environment=dict(os.environ),
            input_bytes=b'',
            input_stream=None,
            timeout=15,
            capture_limit=65536,
        )
    sha_after = _digest_file(exe)
    if sha_before != sha_after:
        raise DuckDBShellError('duckdb CLI binary changed during provenance verification')
    if observed['return_code'] != 0:
        raise DuckDBShellError(
            'duckdb CLI failed provenance probe: ' +
            observed.get('stderr', b'').decode('utf-8', errors='replace')[:200]
        )
    try:
        rows = json.loads(observed['stdout'].decode('utf-8'))
        cli_lib_ver = str(rows[0]['library_version'])
        cli_src_id = str(rows[0]['source_id'])
    except Exception as exc:
        raise DuckDBShellError('duckdb CLI returned unreadable JSON provenance output') from exc

    matched = (cli_lib_ver == py_rt['library_version'] and cli_src_id == py_rt['source_id'])
    if not matched:
        raise DuckDBShellError(
            f'DuckDB CLI provenance mismatch: Python runtime is {py_rt["library_version"]} ({py_rt["source_id"]}), '
            f'but CLI at {exe} is {cli_lib_ver} ({cli_src_id}); refusing mismatched CLI execution'
        )
    return {
        'cli_available': True,
        'matched': True,
        'host_mode': 'matched_native_cli_and_supervised_runner',
        'binary_path': str(exe),
        'binary_sha256': sha_after,
        'python_runtime': py_rt,
        'cli_runtime': {'library_version': cli_lib_ver, 'source_id': cli_src_id},
        'execution_host': host_info,
        'supported_directives': sorted(SUPPORTED_DIRECTIVES),
        'forbidden_directives': sorted(FORBIDDEN_DIRECTIVES),
        'probe_receipt': {k: v for k, v in observed.items() if k not in {'stdout', 'stderr'}},
    }


def execute_cli_batch(
    route: dict,
    script_text: str,
    *,
    read_only: bool = True,
    timeout_seconds: float = 15.0,
    explicit_binary: str | None = None,
) -> dict:
    """Execute a batch script in a supervised matching ``duckdb`` CLI child process."""
    prov = inspect_shell_provenance(explicit_binary)
    if not prov['cli_available']:
        raise DuckDBShellError('Standalone duckdb CLI binary is not installed on this host')
    db_path = contained_database(route)
    flags = ['-batch']
    if read_only and db_path != ':memory:':
        flags.append('-readonly')
    with tempfile.TemporaryDirectory(prefix='sr-duckdb-cli-exec-') as tmp:
        observed = observe_process(
            [prov['binary_path'], *flags, db_path],
            workspace=route.get('filesystem_root') or tmp,
            environment=dict(os.environ),
            input_bytes=script_text.encode('utf-8'),
            input_stream=None,
            timeout=max(1.0, min(float(timeout_seconds), 120.0)),
            capture_limit=MAX_OUTPUT_BYTES,
        )
    return {
        'mode': 'native_cli_process',
        'provenance': prov,
        'return_code': observed['return_code'],
        'timed_out': bool(observed.get('timed_out')),
        'stdout': observed.get('stdout', b'').decode('utf-8', errors='replace'),
        'stderr': observed.get('stderr', b'').decode('utf-8', errors='replace'),
        'process_finality': 'local_waitpid_observed',
    }


def _format_rows(columns: list[str], rows: list[tuple], state: dict) -> str:
    mode = state['mode']
    null_str = state['nullvalue']
    show_headers = state['headers']
    sep = state['separator']

    def cell_str(val) -> str:
        return null_str if val is None else str(val)

    if mode == 'json':
        payload = [
            {col: (None if val is None else val if isinstance(val, (int, float, bool, str, list, dict)) else str(val))
             for col, val in zip(columns, row)}
            for row in rows
        ]
        return json.dumps(payload, ensure_ascii=False) + '\n'

    if mode in {'csv', 'tsv'}:
        delim = '\t' if mode == 'tsv' else (sep or ',')
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=delim, lineterminator='\n')
        if show_headers and columns:
            writer.writerow(columns)
        for row in rows:
            writer.writerow([cell_str(v) for v in row])
        return buf.getvalue()

    if mode == 'line':
        lines = []
        for row in rows:
            for col, val in zip(columns, row):
                lines.append(f'{col} = {cell_str(val)}')
            lines.append('')
        return '\n'.join(lines) + ('\n' if lines else '')

    if mode == 'markdown':
        if not columns:
            return ''
        out = []
        out.append('| ' + ' | '.join(columns) + ' |')
        out.append('| ' + ' | '.join('---' for _ in columns) + ' |')
        for row in rows:
            out.append('| ' + ' | '.join(cell_str(v).replace('|', '\\|') for v in row) + ' |')
        return '\n'.join(out) + '\n'

    if mode == 'box':
        if not columns:
            return ''
        str_rows = [[cell_str(v) for v in row] for row in rows]
        widths = [
            max([len(col), *(len(r[i]) for r in str_rows)] if str_rows else [len(col)])
            for i, col in enumerate(columns)
        ]
        border = '+' + '+'.join('-' * (w + 2) for w in widths) + '+'
        out = [border]
        if show_headers:
            out.append('|' + '|'.join(f' {col.ljust(widths[i])} ' for i, col in enumerate(columns)) + '|')
            out.append(border)
        for r in str_rows:
            out.append('|' + '|'.join(f' {r[i].ljust(widths[i])} ' for i in range(len(columns))) + '|')
        out.append(border)
        return '\n'.join(out) + '\n'

    # Default 'list' mode
    delim = sep or '|'
    out = []
    if show_headers and columns:
        out.append(delim.join(columns))
    for row in rows:
        out.append(delim.join(cell_str(v) for v in row))
    return ('\n'.join(out) + '\n') if out else ''


def _split_script_items(script_text: str) -> list[tuple[str, str, int]]:
    """Split script into ('directive' | 'sql', text, line_no) items without sending dot-commands to SQL."""
    items: list[tuple[str, str, int]] = []
    sql_buf: list[str] = []
    sql_start_line = 1

    def flush_sql():
        nonlocal sql_buf
        joined = '\n'.join(sql_buf).strip()
        sql_buf = []
        if not joined:
            return
        # Check if purely comments
        tokens = duckdb.tokenize(joined)
        non_comment = [t for t in tokens if t[1] != duckdb.token_type.comment]
        if not non_comment:
            return
        for st in duckdb.extract_statements(joined):
            q = st.query.strip()
            if q:
                items.append(('sql', q, sql_start_line))

    for lineno, line in enumerate(script_text.splitlines(), 1):
        stripped = line.strip()
        if not sql_buf:
            if not stripped or stripped.startswith('--'):
                continue
            if stripped.startswith('.'):
                items.append(('directive', stripped, lineno))
                continue
            sql_start_line = lineno
        sql_buf.append(line)
        # Flush SQL buffer once complete statement(s) end with ';' outside quotes/comments
        joined_now = '\n'.join(sql_buf)
        try:
            toks = duckdb.tokenize(joined_now)
            encoded = joined_now.encode('utf-8')
            non_comment = [t for t in toks if t[1] != duckdb.token_type.comment]
            if non_comment and encoded[non_comment[-1][0]:non_comment[-1][0] + 1] == b';':
                flush_sql()
        except duckdb.Error:
            pass

    if sql_buf:
        flush_sql()
    return items


def execute_directive_script(
    route: dict,
    request: dict,
    *,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Execute client dot-directives and SQL statements on a dedicated supervised DuckDB connection."""
    if not isinstance(request, dict):
        raise DuckDBShellError('Invalid DuckDB directive script request')
    allowed_keys = {'script', 'source_file', 'read_only', 'timeout_seconds', 'bail'}
    if set(request) - allowed_keys:
        raise DuckDBShellError('Unsupported fields in DuckDB directive script request')

    fs_root = route.get('filesystem_root')
    db_path = contained_database(route)
    read_only = bool(request.get('read_only', bool(route.get('read_only', False))))
    if route.get('read_only') is True and not read_only:
        raise DuckDBShellError('Registered DuckDB route is read-only')
    timeout_sec = float(request.get('timeout_seconds', 15.0))
    if not 0.1 <= timeout_sec <= 120.0:
        raise DuckDBShellError('timeout_seconds must be between 0.1 and 120.0')

    initial_script = request.get('script')
    source_file = request.get('source_file')
    include_stack: list[Path] = []
    if source_file is not None:
        if not fs_root:
            raise DuckDBShellError('source_file execution requires a configured filesystem_root')
        resolved_src = Path(resolve_contained_path(fs_root, str(source_file), must_exist=True))
        if not resolved_src.is_file():
            raise DuckDBShellError('Selected source_file does not exist')
        initial_script = resolved_src.read_text(encoding='utf-8')
        include_stack.append(resolved_src)
    elif not isinstance(initial_script, str) or not initial_script.strip():
        raise DuckDBShellError('Provide non-empty script text or a contained source_file')

    if len(initial_script.encode('utf-8')) > MAX_OUTPUT_BYTES:
        raise DuckDBShellError('Directive script exceeds 8 MiB limit')

    state = {
        'mode': 'box',
        'headers': True,
        'separator': ',',
        'nullvalue': '',
        'bail': bool(request.get('bail', True)),
        'echo': False,
        'timer': False,
        'output_path': None,
        'once_path': None,
    }
    stdout_chunks: list[str] = []
    stdout_bytes = 0
    files_written: list[str] = []
    steps: list[dict] = []
    timed_out = False
    cancelled = False

    def emit_output(text: str) -> None:
        nonlocal stdout_bytes
        if not text:
            return
        target_file = state['once_path'] or state['output_path']
        if state['once_path'] is not None:
            state['once_path'] = None
        if target_file is not None:
            encoded = text.encode('utf-8')
            prev_size = target_file.stat().st_size if target_file.exists() else 0
            if prev_size + len(encoded) > MAX_OUTPUT_BYTES:
                raise DuckDBShellError('Redirected .output file exceeded 8 MiB limit')
            with target_file.open('ab') as f:
                f.write(encoded)
            if str(target_file) not in files_written:
                files_written.append(str(target_file))
        else:
            stdout_bytes += len(text.encode('utf-8'))
            if stdout_bytes > MAX_OUTPUT_BYTES:
                raise DuckDBShellError('Rendered script output exceeded 8 MiB limit')
            stdout_chunks.append(text)

    open_cfg = {}
    if read_only and db_path != ':memory:':
        open_cfg['access_mode'] = 'READ_ONLY'
    conn = duckdb.connect(db_path, config=open_cfg) if open_cfg else duckdb.connect(db_path)

    def _on_timeout():
        nonlocal timed_out
        timed_out = True
        conn.interrupt()

    timer = threading.Timer(timeout_sec, _on_timeout)
    timer.daemon = True
    timer.start()

    def run_items(script_str: str, depth: int) -> bool:
        nonlocal cancelled
        parsed_items = _split_script_items(script_str)
        for kind, content, lineno in parsed_items:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                conn.interrupt()
                return False
            if timed_out:
                return False
            if state['echo']:
                emit_output(content + '\n')

            t0 = time.perf_counter()
            if kind == 'directive':
                try:
                    parts = shlex.split(content)
                except ValueError as exc:
                    raise DuckDBShellError(f'Line {lineno}: malformed directive quoting ({exc})') from None
                cmd = parts[0].lower()
                args = parts[1:]
                if cmd in FORBIDDEN_DIRECTIVES:
                    raise DuckDBShellError(
                        f'Line {lineno}: directive {cmd} is forbidden in supervised server execution'
                    )
                if cmd not in SUPPORTED_DIRECTIVES:
                    raise DuckDBShellError(f'Line {lineno}: unsupported client directive {cmd}')

                if cmd == '.mode':
                    if len(args) != 1 or args[0].lower() not in SUPPORTED_MODES:
                        raise DuckDBShellError(f'Line {lineno}: .mode requires one of {sorted(SUPPORTED_MODES)}')
                    state['mode'] = args[0].lower()
                elif cmd == '.headers':
                    if len(args) != 1 or args[0].lower() not in {'on', 'off'}:
                        raise DuckDBShellError(f'Line {lineno}: .headers requires on or off')
                    state['headers'] = (args[0].lower() == 'on')
                elif cmd == '.separator':
                    if not 1 <= len(args) <= 2:
                        raise DuckDBShellError(f'Line {lineno}: .separator requires 1 or 2 arguments')
                    state['separator'] = args[0]
                elif cmd == '.nullvalue':
                    if len(args) != 1:
                        raise DuckDBShellError(f'Line {lineno}: .nullvalue requires 1 string argument')
                    state['nullvalue'] = args[0]
                elif cmd == '.bail':
                    if len(args) != 1 or args[0].lower() not in {'on', 'off'}:
                        raise DuckDBShellError(f'Line {lineno}: .bail requires on or off')
                    state['bail'] = (args[0].lower() == 'on')
                elif cmd == '.echo':
                    if len(args) != 1 or args[0].lower() not in {'on', 'off'}:
                        raise DuckDBShellError(f'Line {lineno}: .echo requires on or off')
                    state['echo'] = (args[0].lower() == 'on')
                elif cmd == '.timer':
                    if len(args) != 1 or args[0].lower() not in {'on', 'off'}:
                        raise DuckDBShellError(f'Line {lineno}: .timer requires on or off')
                    state['timer'] = (args[0].lower() == 'on')
                elif cmd == '.show':
                    emit_output(
                        f"     echo: {'on' if state['echo'] else 'off'}\n"
                        f"  headers: {'on' if state['headers'] else 'off'}\n"
                        f"     mode: {state['mode']}\n"
                        f"nullvalue: {state['nullvalue']!r}\n"
                        f"   output: {str(state['output_path']) if state['output_path'] else 'stdout'}\n"
                        f"separator: {state['separator']!r}\n"
                    )
                elif cmd == '.help':
                    emit_output('Supported directives: ' + ', '.join(sorted(SUPPORTED_DIRECTIVES)) + '\n')
                elif cmd == '.databases':
                    rows = conn.execute(
                        'SELECT database_name, path, readonly, type FROM duckdb_databases() WHERE NOT internal ORDER BY database_name'
                    ).fetchall()
                    emit_output(_format_rows(['database_name', 'path', 'readonly', 'type'], rows, state))
                elif cmd == '.tables':
                    pat = args[0] if args else '%'
                    rows = conn.execute(
                        'SELECT schema_name, table_name FROM duckdb_tables() '
                        'WHERE NOT internal AND table_name ILIKE ? ORDER BY schema_name, table_name',
                        [pat],
                    ).fetchall()
                    emit_output(_format_rows(['schema_name', 'table_name'], rows, state))
                elif cmd == '.schema':
                    pat = args[0] if args else '%'
                    rows = conn.execute(
                        'SELECT sql FROM duckdb_tables() WHERE NOT internal AND table_name ILIKE ? AND sql IS NOT NULL '
                        'UNION ALL SELECT sql FROM duckdb_views() WHERE NOT internal AND view_name ILIKE ? AND sql IS NOT NULL',
                        [pat, pat],
                    ).fetchall()
                    emit_output('\n'.join(str(r[0]) for r in rows) + ('\n' if rows else ''))
                elif cmd in {'.indexes', '.indices'}:
                    pat = args[0] if args else '%'
                    rows = conn.execute(
                        'SELECT index_name, table_name, is_unique, sql FROM duckdb_indexes() '
                        'WHERE index_name ILIKE ? OR table_name ILIKE ? ORDER BY index_name',
                        [pat, pat],
                    ).fetchall()
                    emit_output(_format_rows(['index_name', 'table_name', 'is_unique', 'sql'], rows, state))
                elif cmd in {'.output', '.once'}:
                    if not args or args[0].lower() == 'stdout':
                        if cmd == '.output':
                            state['output_path'] = None
                        else:
                            state['once_path'] = None
                    else:
                        if not fs_root:
                            raise DuckDBShellError(f'Line {lineno}: {cmd} file redirection requires filesystem_root')
                        out_p = Path(resolve_contained_path(fs_root, args[0], must_exist=False))
                        out_p.parent.mkdir(parents=True, exist_ok=True)
                        if cmd == '.output':
                            state['output_path'] = out_p
                        else:
                            state['once_path'] = out_p
                elif cmd == '.read':
                    if len(args) != 1:
                        raise DuckDBShellError(f'Line {lineno}: .read requires exactly 1 contained file path')
                    if depth >= MAX_INCLUDE_DEPTH:
                        raise DuckDBShellError(f'Line {lineno}: .read nested include depth exceeded {MAX_INCLUDE_DEPTH}')
                    if not fs_root:
                        raise DuckDBShellError(f'Line {lineno}: .read requires filesystem_root')
                    inc_path = Path(resolve_contained_path(fs_root, args[0], must_exist=True))
                    if not inc_path.is_file():
                        raise DuckDBShellError(f'Line {lineno}: .read file not found: {args[0]}')
                    if inc_path in include_stack:
                        raise DuckDBShellError(f'Line {lineno}: recursive .read cycle detected on {inc_path.name}')
                    inc_text = inc_path.read_text(encoding='utf-8')
                    include_stack.append(inc_path)
                    try:
                        cont = run_items(inc_text, depth + 1)
                    finally:
                        include_stack.pop()
                    if not cont:
                        return False

                steps.append({
                    'kind': 'directive',
                    'line': lineno,
                    'directive': cmd,
                    'status': 'ok',
                    'elapsed_ms': round((time.perf_counter() - t0) * 1000, 3),
                })
            else:
                # Native SQL statement
                try:
                    cur = conn.execute(content)
                    if cur.description:
                        cols = [d[0] for d in cur.description]
                        rows = cur.fetchall()
                        emit_output(_format_rows(cols, rows, state))
                        row_count = len(rows)
                    else:
                        row_count = 0
                    elapsed = round((time.perf_counter() - t0) * 1000, 3)
                    if state['timer']:
                        emit_output(f'Run Time (ms): real {elapsed}\n')
                    steps.append({
                        'kind': 'sql',
                        'line': lineno,
                        'status': 'ok',
                        'rows': row_count,
                        'elapsed_ms': elapsed,
                    })
                except duckdb.Error as exc:
                    elapsed = round((time.perf_counter() - t0) * 1000, 3)
                    if timed_out or (cancel_event is not None and cancel_event.is_set()):
                        if cancel_event is not None and cancel_event.is_set():
                            cancelled = True
                        steps.append({
                            'kind': 'sql',
                            'line': lineno,
                            'status': 'interrupted',
                            'error_type': type(exc).__name__,
                            'elapsed_ms': elapsed,
                        })
                        return False
                    steps.append({
                        'kind': 'sql',
                        'line': lineno,
                        'status': 'error',
                        'error_type': type(exc).__name__,
                        'error': str(exc)[:300],
                        'elapsed_ms': elapsed,
                    })
                    if state['bail']:
                        return False
        return True

    error_summary = None
    try:
        run_items(initial_script, 0)
    except (DuckDBShellError, ValueError) as exc:
        error_summary = str(exc)
    finally:
        timer.cancel()
        timer.join(timeout=1.0)
        try:
            conn.close()
            cleanup_confirmed = True
        except Exception:
            cleanup_confirmed = False

    has_step_errors = any(s['status'] == 'error' for s in steps)
    outcome_state = (
        'cancelled' if cancelled else
        'timed_out' if timed_out else
        'failed' if (error_summary or has_step_errors) else
        'succeeded'
    )
    return {
        'mode': 'supervised_directive_runner',
        'state': outcome_state,
        'timed_out': timed_out,
        'cancelled': cancelled,
        'error': error_summary,
        'steps': steps,
        'output': ''.join(stdout_chunks),
        'files_written': files_written,
        'connection_isolated': True,
        'connection_cleanup_confirmed': cleanup_confirmed,
        'provenance': inspect_shell_provenance(),
    }
