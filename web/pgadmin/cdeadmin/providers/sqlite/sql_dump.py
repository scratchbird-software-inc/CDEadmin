"""Database-Wide Native SQL Script Exchange via matched `sqlite3 .dump` (SQ-AUD-15).

Produces complete database or table-scoped SQL dumps (DDL + INSERT data + sequence/FTS/view/trigger
declarations) using the provenance-matched `sqlite3` CLI in `-readonly -safe -batch` mode,
tracks NUL/newline/BLOB hex fidelity, publishes private `0600` artifacts for protected download,
and provides atomic reviewed SQL script import with independent read-back verification.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from ...operations.fileio import publish_private_file
from ...sdk.tool_process import observe_process
from ..embedded_route import contained_database
from .declarations import quote
from .shell_tool import SQLiteShellError, verify_matching_cli


class SQLDumpError(ValueError):
    pass


DEFAULT_MAX_DUMP_BYTES = 16 * 1024 * 1024
HARD_MAX_DUMP_BYTES = 64 * 1024 * 1024


def _inspect_dump_fidelity(db_path: Path, tables: list[str] | None) -> dict:
    has_blobs = False
    has_embedded_newlines = False
    has_embedded_nul = False
    table_counts = {}
    with closing(sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)) as conn:
        schema_rows = conn.execute(
            "SELECT name, rootpage, sql FROM main.sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        user_tables = [str(r[0]) for r in schema_rows]
        virtual_by_schema = {
            str(r[0]): (r[1] in (0, None)) or str(r[2] or '').lstrip().upper().startswith('CREATE VIRTUAL TABLE')
            for r in schema_rows
        }
        tlist = {
            str(r[1]): str(r[2])
            for r in conn.execute('PRAGMA main.table_list').fetchall()
            if str(r[0]) == 'main'
        }
        selected = user_tables if not tables else [t for t in tables if t in user_tables]
        for tname in selected:
            if tlist.get(tname) == 'virtual' or (not tlist and virtual_by_schema.get(tname)):
                try:
                    cnt = int(conn.execute(f'SELECT count(*) FROM main.{quote(tname)}').fetchone()[0])
                    table_counts[tname] = cnt
                except sqlite3.Error:
                    table_counts[tname] = None
                continue
            cnt = int(conn.execute(f'SELECT count(*) FROM main.{quote(tname)}').fetchone()[0])
            table_counts[tname] = cnt
            cols = [
                str(c[1])
                for c in conn.execute(f'PRAGMA main.table_xinfo({quote(tname)})').fetchall()
                if not c[6]
            ]
            for cname in cols:
                q_c = quote(cname)
                q_t = quote(tname)
                if not has_blobs:
                    b = conn.execute(f"SELECT 1 FROM main.{q_t} WHERE typeof({q_c})='blob' LIMIT 1").fetchone()
                    if b:
                        has_blobs = True
                if not has_embedded_newlines:
                    nl = conn.execute(
                        f"SELECT 1 FROM main.{q_t} WHERE typeof({q_c})='text' AND (instr({q_c}, char(10))>0 OR instr({q_c}, char(13))>0) LIMIT 1"
                    ).fetchone()
                    if nl:
                        has_embedded_newlines = True
                if not has_embedded_nul:
                    # In SQLite, instr(text, char(0)) can stop at NUL; compare octet_length vs length(CAST(... AS BLOB)) or hex
                    nul = conn.execute(
                        f"SELECT 1 FROM main.{q_t} WHERE typeof({q_c})='text' AND instr(hex(CAST({q_c} AS BLOB)), '00')>0 LIMIT 1"
                    ).fetchone()
                    if nul:
                        has_embedded_nul = True
    return {
        'table_row_counts': table_counts,
        'contains_blob_values': has_blobs,
        'contains_embedded_newlines': has_embedded_newlines,
        'contains_embedded_nul_in_text': has_embedded_nul,
    }


def export_sql_dump(
    route: dict,
    request: dict,
    *,
    artifact_path: Path | None = None,
    explicit_binary: str | None = None,
) -> dict:
    if not isinstance(request, dict) or set(request) - {
        'data_only',
        'preserve_newlines',
        'exclude_system',
        'tables',
        'max_bytes',
        'inline_preview_limit',
    }:
        raise SQLDumpError('Invalid SQLite native SQL dump options')

    data_only = bool(request.get('data_only', False))
    preserve_newlines = bool(request.get('preserve_newlines', True))
    exclude_system = bool(request.get('exclude_system', False))
    max_bytes = int(request.get('max_bytes') or DEFAULT_MAX_DUMP_BYTES)
    if not 1024 <= max_bytes <= HARD_MAX_DUMP_BYTES:
        raise SQLDumpError(f'max_bytes must be between 1,024 and {HARD_MAX_DUMP_BYTES}')
    preview_limit = int(request.get('inline_preview_limit') or 65536)
    preview_limit = max(1024, min(preview_limit, 1024 * 1024))

    tables = request.get('tables')
    if tables is not None:
        if (
            not isinstance(tables, list)
            or not 1 <= len(tables) <= 64
            or any(not isinstance(t, str) or not re.fullmatch(r'[A-Za-z0-9_.\-]{1,128}', t) for t in tables)
        ):
            raise SQLDumpError('Optional tables filter must be 1 to 64 simple table names')

    db_path = Path(contained_database(route))
    if str(db_path) == ':memory:' or not db_path.is_file():
        raise SQLDumpError('SQLite SQL script dump requires an existing file-backed SQLite database')
    db_path = db_path.resolve(strict=True)

    try:
        provenance = verify_matching_cli(explicit_binary)
    except SQLiteShellError as exc:
        raise SQLDumpError(str(exc)) from None

    fidelity = _inspect_dump_fidelity(db_path, tables)
    dump_args = ['.dump']
    if data_only:
        dump_args.append('--data-only')
    if preserve_newlines:
        dump_args.append('--newlines')
    if exclude_system:
        dump_args.append('--nosys')
    if tables:
        dump_args.extend(tables)
    dot_cmd = ' '.join(dump_args)

    safe_args = ['-safe'] if provenance.get('safe_flag_supported') else []
    with tempfile.TemporaryDirectory(prefix='sr-sqlite-dump-') as tmp:
        observed = observe_process(
            [
                provenance['binary_path'],
                '-readonly',
                *safe_args,
                '-batch',
                '-bail',
                str(db_path),
                dot_cmd,
            ],
            workspace=tmp,
            environment=dict(os.environ),
            input_bytes=b'',
            input_stream=None,
            timeout=120,
            capture_limit=max_bytes + 1024,
        )
    raw_bytes = observed['stdout']
    if observed.get('stdout_truncated') or len(raw_bytes) > max_bytes:
        raise SQLDumpError(f'SQLite SQL dump exceeded byte budget ({max_bytes} bytes)')
    if observed['return_code'] != 0:
        err_txt = observed['stderr'].decode('utf-8', errors='replace')[:300]
        raise SQLDumpError(f'sqlite3 .dump failed: {err_txt}')

    script_text = raw_bytes.decode('utf-8', errors='replace')
    if 'ROLLBACK; -- due to errors' in script_text:
        raise SQLDumpError('sqlite3 .dump reported internal errors (ROLLBACK; -- due to errors)')

    sha = hashlib.sha256(raw_bytes).hexdigest()
    saved_artifact = None
    if artifact_path is not None:
        artifact_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        staging = artifact_path.with_name(f'.{artifact_path.name}.tmp')
        publish_private_file(artifact_path, raw_bytes, staging=staging)
        saved_artifact = str(artifact_path)

    warnings = []
    if fidelity['contains_embedded_nul_in_text']:
        warnings.append(
            'One or more TEXT values contain embedded NUL bytes; SQLite SQL text literals truncate at NUL unless stored as BLOB or binary backup.'
        )
    if not preserve_newlines and fidelity['contains_embedded_newlines']:
        warnings.append(
            'preserve_newlines=False encodes CR/LF via replace() expressions; enable preserve_newlines (--newlines) for literal newline characters.'
        )

    return {
        'format': 'scratchrobin.sqlite.sql-dump@1',
        'command': dot_cmd,
        'byte_length': len(raw_bytes),
        'sha256': sha,
        'data_only': data_only,
        'preserve_newlines': preserve_newlines,
        'exclude_system': exclude_system,
        'tables': tables or [],
        'fidelity': {
            **fidelity,
            'blobs_encoded_as_hex_literals': True,
            'newlines_flag_enabled': preserve_newlines,
        },
        'warnings': warnings,
        'script_preview': script_text[:preview_limit],
        'preview_truncated': len(script_text) > preview_limit,
        'artifact_saved': saved_artifact is not None,
        'provenance': provenance,
        'process_receipt': {k: v for k, v in observed.items() if k not in {'stdout', 'stderr'}},
    }


def _strip_outer_transaction(script: str) -> list[str]:
    """Split complete SQL statements while stripping outer BEGIN TRANSACTION / COMMIT wrapper from .dump."""
    if '\x00' in script or len(script.encode('utf-8')) > HARD_MAX_DUMP_BYTES:
        raise SQLDumpError('SQL script must be bounded UTF-8 text without NUL bytes')
    statements = []
    buf = []
    for line in script.splitlines(keepends=True):
        stripped = line.strip()
        if not buf and (not stripped or stripped.startswith('--')):
            continue
        buf.append(line)
        candidate = ''.join(buf)
        if sqlite3.complete_statement(candidate):
            stmt = candidate.strip()
            buf.clear()
            upper = stmt.rstrip(';').strip().upper()
            if upper in {'BEGIN', 'BEGIN TRANSACTION', 'COMMIT', 'END', 'END TRANSACTION'}:
                continue
            if upper.startswith('ROLLBACK'):
                raise SQLDumpError('Refusing SQL script containing top-level ROLLBACK statement')
            if stmt.lstrip().startswith('.'):
                raise SQLDumpError('CLI dot-commands are not permitted inside reviewed SQL script import')
            statements.append(stmt)
    trailing = ''.join(buf).strip()
    if trailing and not all(ln.strip().startswith('--') or not ln.strip() for ln in trailing.splitlines()):
        raise SQLDumpError('SQL script ends with an incomplete SQL statement')
    if not statements:
        raise SQLDumpError('SQL script contains no executable SQL statements')
    return statements


def apply_sql_script_import(route: dict, script_text: str) -> dict:
    db_path = Path(contained_database(route))
    if str(db_path) == ':memory:':
        raise SQLDumpError('SQLite SQL script import requires a file-backed SQLite database')
    if route.get('read_only') is True:
        raise SQLDumpError('Cannot import SQL script into a read-only SQLite endpoint')
    statements = _strip_outer_transaction(script_text)

    conn = sqlite3.connect(db_path, isolation_level=None)
    executed = 0
    try:
        conn.enable_load_extension(False)
        conn.execute('BEGIN IMMEDIATE')
        for stmt in statements:
            conn.execute(stmt)
            executed += 1
        conn.commit()
    except Exception as exc:
        try:
            if conn.in_transaction:
                conn.rollback()
        except Exception:
            pass
        raise SQLDumpError(f'SQLite SQL script import rolled back at statement {executed + 1}: {exc}') from None
    finally:
        conn.close()

    # Independent read-back verification
    with closing(sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)) as reader:
        objects = reader.execute(
            "SELECT type, count(*) FROM main.sqlite_schema WHERE name NOT LIKE 'sqlite_%' GROUP BY type ORDER BY type"
        ).fetchall()
        user_tables = [
            str(r[0])
            for r in reader.execute(
                "SELECT name FROM main.sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        row_counts = {}
        for tname in user_tables:
            try:
                row_counts[tname] = int(reader.execute(f'SELECT count(*) FROM main.{quote(tname)}').fetchone()[0])
            except sqlite3.Error:
                row_counts[tname] = None

    return {
        'state': 'committed',
        'executed_statements': executed,
        'rediscovery_verified': True,
        'object_counts': {str(k): int(v) for k, v in objects},
        'table_row_counts': row_counts,
    }
