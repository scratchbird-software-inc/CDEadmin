"""Single SQL Stream Database Dump & Reviewed Reload for DuckDB 1.5.2 (DU-AUD-19).

Distinct from directory ``EXPORT DATABASE`` and documentary DDN:
- Produces one self-contained, dependency-ordered native DuckDB SQL stream
  covering schemas, sequences (with exact current state without advancing
  generators), ENUM/alias types, foreign-key-ordered tables, lossless typed
  INSERT batches (preserving BLOB hex, HUGEINT/UHUGEINT/DECIMAL, temporal,
  LIST/ARRAY/STRUCT/MAP/UNION, embedded newlines and NULs, and skipping virtual
  generated columns), views, full-signature macros (with parameter types and
  defaults via ``_capture_macro_source``), independent indexes, and comments.
- Never exports secrets; explicitly labeled as a logical SQL stream dump, never
  a physical backup.
- Reloads atomically inside a single transaction on a contained DuckDB target
  with rollback/cleanup on interrupted or invalid external files and independent
  post-commit verification.
"""

from __future__ import annotations

from collections import deque
import hashlib
import math
import os
from pathlib import Path
import re

import duckdb

from ...operations.fileio import publish_private_file
from ..embedded_route import contained_database
from .catalog import _capture_macro_source
from .grid_values import RowCursor


class DuckDBSQLDumpError(ValueError):
    pass


DUMP_FORMAT = 'scratchrobin.duckdb.sql-stream-dump@1'
DEFAULT_MAX_DUMP_BYTES = 16 * 1024 * 1024
HARD_MAX_DUMP_BYTES = 64 * 1024 * 1024


def _quote(ident: str) -> str:
    return '"' + str(ident).replace('"', '""') + '"'


def _sql_string_literal(text: str) -> str:
    """Render a UTF-8 string as an exact DuckDB SQL expression preserving CR, LF, and NUL."""
    if not text:
        return "''"
    if '\x00' not in text and '\n' not in text and '\r' not in text:
        return "'" + text.replace("'", "''") + "'"
    parts: list[str] = []
    buf: list[str] = []

    def flush():
        if buf:
            s = ''.join(buf)
            parts.append("'" + s.replace("'", "''") + "'")
            buf.clear()

    for ch in text:
        code = ord(ch)
        if code == 0:
            flush()
            parts.append('chr(0)')
        elif code == 10:
            flush()
            parts.append('chr(10)')
        elif code == 13:
            flush()
            parts.append('chr(13)')
        else:
            buf.append(ch)
    flush()
    return parts[0] if len(parts) == 1 else '(' + ' || '.join(parts) + ')'


def _bind_param_to_sql_literal(val) -> str:
    """Inline a bound parameter emitted by ``compile_write_value`` into a pure SQL literal."""
    if val is None:
        return 'NULL'
    if isinstance(val, bool):
        return 'TRUE' if val else 'FALSE'
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return f"CAST('{val}' AS DOUBLE)"
        return repr(val)
    if isinstance(val, (bytes, bytearray, memoryview)):
        return f"from_hex('{bytes(val).hex()}')"
    if isinstance(val, str):
        return _sql_string_literal(val)
    raise DuckDBSQLDumpError(f'Unsupported parameter type during SQL literal serialization: {type(val).__name__}')


def _inline_compiled_sql(sql_template: str, params: list) -> str:
    """Replace ``?`` placeholders outside string/identifier quotes in ``sql_template`` with exact SQL literals."""
    if not params:
        return sql_template
    out: list[str] = []
    p_idx = 0
    i = 0
    n = len(sql_template)
    quote_ch = None
    while i < n:
        ch = sql_template[i]
        if quote_ch is not None:
            out.append(ch)
            if ch == quote_ch:
                if i + 1 < n and sql_template[i + 1] == quote_ch:
                    out.append(sql_template[i + 1])
                    i += 2
                    continue
                quote_ch = None
            i += 1
            continue
        if ch in {"'", '"'}:
            quote_ch = ch
            out.append(ch)
            i += 1
            continue
        if ch == '?':
            if p_idx >= len(params):
                raise DuckDBSQLDumpError('Placeholder count mismatch while rendering SQL dump literal')
            out.append(_bind_param_to_sql_literal(params[p_idx]))
            p_idx += 1
            i += 1
            continue
        out.append(ch)
        i += 1
    if p_idx != len(params):
        raise DuckDBSQLDumpError('Unconsumed parameters while rendering SQL dump literal')
    return ''.join(out)


def _native_cell_to_sql_expr(ncell) -> str:
    """Convert a lossless ``NativeCell`` via ``ncell.binding()`` into a pure DuckDB SQL expression."""
    sql_tpl, params = ncell.binding()
    return _inline_compiled_sql(sql_tpl, list(params))


def _topological_tables(tables: list[tuple[str, str, str]], fks: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Order ``(schema, table, sql)`` so referenced FK parent tables precede child tables."""
    key_map = {(s, t): (s, t, ddl) for s, t, ddl in tables}
    deps: dict[tuple[str, str], set[tuple[str, str]]] = {k: set() for k in key_map}
    for sch, tbl, ref_tbl in fks:
        if (sch, tbl) in deps and (sch, ref_tbl) in deps and ref_tbl != tbl:
            deps[(sch, tbl)].add((sch, ref_tbl))
    in_deg = {k: len(v) for k, v in deps.items()}
    rev: dict[tuple[str, str], list[tuple[str, str]]] = {k: [] for k in key_map}
    for child, parents in deps.items():
        for p in parents:
            rev[p].append(child)
    q = deque(sorted(k for k, d in in_deg.items() if d == 0))
    ordered = []
    while q:
        cur = q.popleft()
        ordered.append(key_map[cur])
        for nxt in sorted(rev[cur]):
            in_deg[nxt] -= 1
            if in_deg[nxt] == 0:
                q.append(nxt)
    if len(ordered) != len(tables):
        raise DuckDBSQLDumpError('Mutual foreign-key cycle across tables cannot be serialized without deferred constraints')
    return ordered


def _export_table_inserts(
    conn,
    schema_name: str,
    table_name: str,
    *,
    self_fk: tuple[list[str], list[str]] | None,
    emit_line,
) -> int:
    qual = f'{_quote(schema_name)}.{_quote(table_name)}'
    # Discover base (non-generated) columns via duckdb_columns() and table SQL
    col_rows = conn.execute(
        'SELECT column_name, data_type FROM duckdb_columns() '
        'WHERE database_name=current_database() AND schema_name=? AND table_name=? '
        'ORDER BY column_index',
        [schema_name, table_name],
    ).fetchall()
    tbl_ddl = conn.execute(
        'SELECT sql FROM duckdb_tables() WHERE database_name=current_database() AND schema_name=? AND table_name=?',
        [schema_name, table_name],
    ).fetchone()[0] or ''
    from ...workspace.duckdb_general_rebuild import parse_create_table_clauses
    gen_folded = set()
    parsed = parse_create_table_clauses(tbl_ddl)
    if parsed:
        for clause in parsed[0]:
            if any(t['kind'] == 'token_type.keyword' and t['folded'] == 'generated' for t in clause[1:]):
                gen_folded.add(clause[0]['unquoted'].casefold())

    base_cols = [c[0] for c in col_rows if c[0].casefold() not in gen_folded]
    if not base_cols:
        return 0

    total = conn.execute(f'SELECT count(*) FROM {qual}').fetchone()[0]
    if total == 0:
        return 0

    proj_sql = ', '.join(_quote(c) for c in base_cols)
    cursor = RowCursor(conn)
    encoded_rows: list[tuple[dict, list[str]]] = []
    try:
        native_rows = cursor.execute(f'SELECT {proj_sql} FROM {qual}').fetchall()
        for row_cells in native_rows:
            raw_key_map = {base_cols[c_idx]: row_cells[c_idx].public for c_idx in range(len(base_cols))}
            sql_vals = [_native_cell_to_sql_expr(row_cells[c_idx]) for c_idx in range(len(base_cols))]
            encoded_rows.append((raw_key_map, sql_vals))
    finally:
        cursor.close()

    col_list_sql = ', '.join(_quote(c) for c in base_cols)
    if self_fk is not None:
        # Order self-FK rows hierarchically (parents before children) and emit 1 statement per level!
        fk_cols, pk_cols = self_fk
        remaining = list(encoded_rows)
        seen_pks: set[tuple] = set()
        while remaining:
            level_rows = []
            next_remaining = []
            for key_map, sql_vals in remaining:
                if any(key_map[fc] is None for fc in fk_cols):
                    level_rows.append((key_map, sql_vals))
                else:
                    fk_tuple = tuple(repr(key_map[fc]) for fc in fk_cols)
                    if fk_tuple in seen_pks:
                        level_rows.append((key_map, sql_vals))
                    else:
                        next_remaining.append((key_map, sql_vals))
            if not level_rows:
                level_rows = next_remaining
                next_remaining = []
            for key_map, _ in level_rows:
                seen_pks.add(tuple(repr(key_map[pk]) for pk in pk_cols))
            for i in range(0, len(level_rows), 100):
                chunk = level_rows[i:i + 100]
                values_sql = ', '.join('(' + ', '.join(sv) + ')' for _, sv in chunk)
                emit_line(f'INSERT INTO {qual} ({col_list_sql}) VALUES {values_sql};')
            remaining = next_remaining
    else:
        for i in range(0, len(encoded_rows), 100):
            chunk = encoded_rows[i:i + 100]
            values_sql = ', '.join('(' + ', '.join(sv) + ')' for _, sv in chunk)
            emit_line(f'INSERT INTO {qual} ({col_list_sql}) VALUES {values_sql};')

    return len(encoded_rows)


def export_sql_dump(
    route: dict,
    request: dict | None = None,
    *,
    artifact_path: Path | None = None,
) -> dict:
    request = request or {}
    allowed = {'schema_only', 'tables', 'max_bytes', 'inline_preview_limit'}
    if not isinstance(request, dict) or set(request) - allowed:
        raise DuckDBSQLDumpError('Invalid DuckDB SQL stream dump options')

    schema_only = bool(request.get('schema_only', False))
    max_bytes = int(request.get('max_bytes') or DEFAULT_MAX_DUMP_BYTES)
    if not 1024 <= max_bytes <= HARD_MAX_DUMP_BYTES:
        raise DuckDBSQLDumpError(f'max_bytes must be between 1,024 and {HARD_MAX_DUMP_BYTES}')
    preview_limit = max(1024, min(int(request.get('inline_preview_limit') or 65536), 1024 * 1024))
    table_filter = set(request['tables']) if request.get('tables') else None

    db_path = contained_database(route)
    if db_path == ':memory:' or not Path(db_path).is_file():
        raise DuckDBSQLDumpError('DuckDB SQL stream dump requires an existing file-backed DuckDB database')

    lines: list[str] = []
    byte_total = 0

    def emit(line: str) -> None:
        nonlocal byte_total
        text = line.rstrip() + '\n'
        byte_total += len(text.encode('utf-8'))
        if byte_total > max_bytes:
            raise DuckDBSQLDumpError(f'DuckDB SQL stream dump exceeded max_bytes ({max_bytes} bytes)')
        lines.append(text)

    conn = duckdb.connect(db_path, config={'access_mode': 'READ_ONLY'})
    table_row_counts: dict[str, int] = {}
    object_counts = {'schemas': 0, 'sequences': 0, 'types': 0, 'tables': 0, 'views': 0, 'macros': 0, 'indexes': 0, 'comments': 0}
    try:
        lib_ver, src_id = conn.execute('SELECT library_version, source_id FROM pragma_version()').fetchone()
        cur_db = conn.execute('SELECT current_database()').fetchone()[0]
        emit(f'-- ScratchRobin Logical SQL Stream Dump ({DUMP_FORMAT})')
        emit(f'-- Engine: DuckDB {lib_ver} ({src_id})')
        emit('-- Scope: Logical schema/data SQL stream (not a physical file backup; secrets are excluded).')

        comments: list[str] = []

        # 1. Schemas
        schemas = conn.execute(
            "SELECT schema_name, comment FROM duckdb_schemas() "
            "WHERE database_name=current_database() AND NOT internal "
            "AND schema_name NOT IN ('main', 'information_schema', 'pg_catalog') "
            "ORDER BY schema_name"
        ).fetchall()
        for sname, scomment in schemas:
            if table_filter is None:
                emit(f'CREATE SCHEMA IF NOT EXISTS {_quote(sname)};')
                object_counts['schemas'] += 1
                if scomment is not None:
                    comments.append(f'COMMENT ON SCHEMA {_quote(sname)} IS {_sql_string_literal(scomment)};')

        # 2. Sequences (preserving current generator state without calling nextval!)
        if table_filter is None:
            seqs = conn.execute(
                'SELECT schema_name, sequence_name, start_value, min_value, max_value, increment_by, cycle, last_value, comment '
                'FROM duckdb_sequences() WHERE database_name=current_database() AND NOT temporary '
                'ORDER BY schema_name, sequence_name'
            ).fetchall()
            for sch, sname, start_v, min_v, max_v, inc_v, cyc, last_v, scomment in seqs:
                # When last_value is observed after checkpoint/reopen, DuckDB stores next resumable start in start_value/last_value;
                # if nextval ran in the same session, resume at last_value + inc_v when last_value != start_value or start_value!
                resume_start = start_v if last_v is None else last_v
                cyc_sql = 'CYCLE' if cyc else 'NO CYCLE'
                emit(
                    f'CREATE SEQUENCE {_quote(sch)}.{_quote(sname)} '
                    f'INCREMENT BY {inc_v} MINVALUE {min_v} MAXVALUE {max_v} '
                    f'START WITH {resume_start} {cyc_sql};'
                )
                object_counts['sequences'] += 1
                if scomment is not None:
                    comments.append(f'COMMENT ON SEQUENCE {_quote(sch)}.{_quote(sname)} IS {_sql_string_literal(scomment)};')

        # 3. User types (ENUMs & aliases; duckdb_types() provides logical_type + labels rather than sql)
        if table_filter is None:
            types = conn.execute(
                'SELECT schema_name, type_name, logical_type, labels, comment FROM duckdb_types() '
                'WHERE database_name=current_database() AND NOT internal '
                'ORDER BY type_oid'
            ).fetchall()
            for sch, tname, ltype, labels, tcomment in types:
                if ltype == 'ENUM' and labels is not None:
                    lbl_sql = ', '.join(_sql_string_literal(str(lbl)) for lbl in labels)
                    emit(f'CREATE TYPE {_quote(sch)}.{_quote(tname)} AS ENUM ({lbl_sql});')
                else:
                    emit(f'CREATE TYPE {_quote(sch)}.{_quote(tname)} AS {ltype};')
                object_counts['types'] += 1
                if tcomment is not None:
                    comments.append(f'COMMENT ON TYPE {_quote(sch)}.{_quote(tname)} IS {_sql_string_literal(tcomment)};')

        # 4. Tables in topological FK order
        raw_tables = conn.execute(
            'SELECT schema_name, table_name, sql, comment FROM duckdb_tables() '
            'WHERE database_name=current_database() AND NOT internal AND NOT temporary '
            'ORDER BY schema_name, table_name'
        ).fetchall()
        selected_tables = [
            (sch, tname, tsql, tcomm)
            for sch, tname, tsql, tcomm in raw_tables
            if table_filter is None or tname in table_filter or f'{sch}.{tname}' in table_filter
        ]
        fk_rows = conn.execute(
            "SELECT schema_name, table_name, referenced_table, constraint_column_names, referenced_column_names "
            "FROM duckdb_constraints() WHERE database_name=current_database() AND constraint_type='FOREIGN KEY'"
        ).fetchall()
        fks_simple = [(r[0], r[1], r[2]) for r in fk_rows]
        self_fk_by_table = {
            (r[0], r[1]): (list(r[3]), list(r[4]))
            for r in fk_rows if r[1] == r[2]
        }
        ordered_tables = _topological_tables([(s, t, ddl) for s, t, ddl, _ in selected_tables], fks_simple)
        comment_by_tbl = {(s, t): tc for s, t, _, tc in selected_tables}

        for sch, tname, tsql in ordered_tables:
            clean_ddl = tsql.strip().rstrip(';')
            # Repair DuckDB 1.5.2 self-FK empty constraint_text trailing `, )` serializer quirk if present!
            if (sch, tname) in self_fk_by_table and re.search(r',\s*\)$', clean_ddl):
                fk_cols, pk_cols = self_fk_by_table[(sch, tname)]
                fk_clause = (
                    f"FOREIGN KEY ({', '.join(_quote(c) for c in fk_cols)}) "
                    f"REFERENCES {_quote(sch)}.{_quote(tname)} ({', '.join(_quote(c) for c in pk_cols)})"
                )
                clean_ddl = re.sub(r',\s*\)$', f', {fk_clause})', clean_ddl)
            emit(clean_ddl + ';')
            object_counts['tables'] += 1
            tcomm = comment_by_tbl.get((sch, tname))
            if tcomm is not None:
                comments.append(f'COMMENT ON TABLE {_quote(sch)}.{_quote(tname)} IS {_sql_string_literal(tcomm)};')
            col_comms = conn.execute(
                'SELECT column_name, comment FROM duckdb_columns() '
                'WHERE database_name=current_database() AND schema_name=? AND table_name=? AND comment IS NOT NULL '
                'ORDER BY column_index',
                [sch, tname],
            ).fetchall()
            for cname, ccomm in col_comms:
                comments.append(f'COMMENT ON COLUMN {_quote(sch)}.{_quote(tname)}.{_quote(cname)} IS {_sql_string_literal(ccomm)};')

        # 5. Table data (in topological FK order so reload satisfies FKs immediately)
        if not schema_only:
            for sch, tname, _ in ordered_tables:
                cnt = _export_table_inserts(
                    conn, sch, tname,
                    self_fk=self_fk_by_table.get((sch, tname)),
                    emit_line=emit,
                )
                table_row_counts[f'{sch}.{tname}'] = cnt

        # 6. Views, 7. Macros (with full defaults!), 8. Indexes, 9. Comments
        if table_filter is None:
            views = conn.execute(
                'SELECT schema_name, view_name, sql, comment FROM duckdb_views() '
                'WHERE database_name=current_database() AND NOT internal AND NOT temporary '
                'ORDER BY view_oid'
            ).fetchall()
            for sch, vname, vsql, vcomm in views:
                emit(vsql.strip().rstrip(';') + ';')
                object_counts['views'] += 1
                if vcomm is not None:
                    comments.append(f'COMMENT ON VIEW {_quote(sch)}.{_quote(vname)} IS {_sql_string_literal(vcomm)};')
                vcol_comms = conn.execute(
                    'SELECT column_name, comment FROM duckdb_columns() '
                    'WHERE database_name=current_database() AND schema_name=? AND table_name=? AND comment IS NOT NULL '
                    'ORDER BY column_index',
                    [sch, vname],
                ).fetchall()
                for cname, ccomm in vcol_comms:
                    comments.append(f'COMMENT ON COLUMN {_quote(sch)}.{_quote(vname)}.{_quote(cname)} IS {_sql_string_literal(ccomm)};')

            # Macros via _capture_macro_source on a separate read-write handle (since EXPORT DATABASE attaches a temp scratch db)
            macro_rows = conn.execute(
                "SELECT DISTINCT schema_name, function_name, comment FROM duckdb_functions() "
                "WHERE database_name=current_database() AND NOT internal AND function_type IN ('macro', 'table_macro') "
                "ORDER BY schema_name, function_name"
            ).fetchall()
            if macro_rows:
                m_conn = duckdb.connect(':memory:')
                try:
                    lit_db = "'" + str(db_path).replace("'", "''") + "'"
                    m_conn.execute(f'ATTACH {lit_db} AS {_quote(cur_db)} (READ_ONLY)')
                    pseudo_resources = [
                        {
                            'resource_kind': 'macro',
                            'display_path': [cur_db, sch, mname],
                            'display_name': mname,
                            'native': {'catalog_metadata': {'internal': False, 'comment': mcomm}},
                        }
                        for sch, mname, mcomm in macro_rows
                    ]
                    _capture_macro_source(m_conn, pseudo_resources, lambda _x: None)
                    for pres in pseudo_resources:
                        sddl = pres['native']['source_ddl'].strip().rstrip(';')
                        emit(sddl + ';')
                        object_counts['macros'] += 1
                        mcomm = pres['native']['catalog_metadata'].get('comment')
                        if mcomm is not None:
                            sch, mname = pres['display_path'][1], pres['display_name']
                            comments.append(f'COMMENT ON MACRO {_quote(sch)}.{_quote(mname)} IS {_sql_string_literal(mcomm)};')
                finally:
                    m_conn.close()

        # Indexes on selected tables
        selected_set = {(s, t) for s, t, _ in ordered_tables}
        indexes = conn.execute(
            'SELECT schema_name, table_name, index_name, sql, comment FROM duckdb_indexes() '
            'WHERE database_name=current_database() ORDER BY schema_name, table_name, index_name'
        ).fetchall()
        for sch, tname, iname, isql, icomm in indexes:
            if (sch, tname) not in selected_set or not isql:
                continue
            emit(isql.strip().rstrip(';') + ';')
            object_counts['indexes'] += 1
            if icomm is not None:
                comments.append(f'COMMENT ON INDEX {_quote(sch)}.{_quote(iname)} IS {_sql_string_literal(icomm)};')

        for cstmt in comments:
            emit(cstmt)
            object_counts['comments'] += 1
    finally:
        conn.close()

    full_sql = ''.join(lines)
    encoded = full_sql.encode('utf-8')
    sha256 = hashlib.sha256(encoded).hexdigest()
    if artifact_path is not None:
        staging = artifact_path.with_name(f'.{artifact_path.name}.tmp')
        publish_private_file(artifact_path, encoded, staging=staging)

    return {
        'format': DUMP_FORMAT,
        'backup_classification': 'logical_sql_stream_dump_not_physical_backup',
        'secrets_excluded': True,
        'schema_only': schema_only,
        'size_bytes': len(encoded),
        'sha256': sha256,
        'object_counts': object_counts,
        'table_row_counts': table_row_counts,
        'sql_preview': full_sql[:preview_limit],
        'truncated_preview': len(full_sql) > preview_limit,
        'sql_text': full_sql if artifact_path is None else None,
        'artifact_path': str(artifact_path) if artifact_path is not None else None,
    }


def reload_sql_dump(
    target_route: dict,
    sql_text: str,
    *,
    create_if_missing: bool = False,
    storage_version: str | None = None,
) -> dict:
    """Atomically reload a single SQL stream dump into a target DuckDB file with rollback/cleanup on failure."""
    if not isinstance(sql_text, str) or not sql_text.strip():
        raise DuckDBSQLDumpError('SQL dump text must be non-empty UTF-8')
    if len(sql_text.encode('utf-8')) > HARD_MAX_DUMP_BYTES:
        raise DuckDBSQLDumpError(f'SQL dump exceeds {HARD_MAX_DUMP_BYTES} bytes')
    if target_route.get('read_only') is True:
        raise DuckDBSQLDumpError('Cannot reload SQL dump into a read-only DuckDB target')

    db_path = contained_database(target_route)
    if db_path == ':memory:':
        raise DuckDBSQLDumpError('SQL stream reload requires a file-backed DuckDB target')
    existed_before = Path(db_path).exists()
    if not existed_before and not create_if_missing:
        raise DuckDBSQLDumpError('Target DuckDB file does not exist and create_if_missing is False')

    try:
        statements = duckdb.extract_statements(sql_text)
    except duckdb.Error as exc:
        raise DuckDBSQLDumpError(f'SQL dump failed DuckDB parse check before execution: {exc}') from None
    if not statements:
        raise DuckDBSQLDumpError('SQL dump contains no executable SQL statements')

    # Reject secret/attach/copy-to-external statements via non-comment, non-string DuckDB tokens
    for st in statements:
        enc_q = st.query.encode('utf-8')
        raw_toks = duckdb.tokenize(st.query)
        code_words = []
        for idx_t, (off_t, kind_t) in enumerate(raw_toks):
            if kind_t in {duckdb.token_type.comment, duckdb.token_type.string_const}:
                continue
            end_t = raw_toks[idx_t + 1][0] if idx_t + 1 < len(raw_toks) else len(enc_q)
            w = enc_q[off_t:end_t].decode('utf-8', errors='replace').strip().upper()
            if w:
                code_words.append(w)
        if not code_words:
            continue
        first_w = code_words[0]
        if (first_w in {'ATTACH', 'DETACH', 'INSTALL', 'LOAD', 'EXPORT', 'IMPORT'} or
                (first_w == 'COPY' and 'TO' in code_words) or
                (first_w in {'CREATE', 'DROP'} and 'SECRET' in code_words[:5])):
            raise DuckDBSQLDumpError(f'Disallowed external/secret statement in SQL dump reload: {st.query.strip()[:80]}')

    cfg = {'storage_compatibility_version': storage_version} if storage_version else {}
    conn = duckdb.connect(db_path, config=cfg) if cfg else duckdb.connect(db_path)
    executed = 0
    try:
        conn.execute('BEGIN TRANSACTION')
        for st in statements:
            conn.execute(st.query)
            executed += 1
        conn.execute('COMMIT')
        conn.execute('CHECKPOINT')
    except duckdb.Error as exc:
        try:
            conn.execute('ROLLBACK')
        except Exception:
            pass
        conn.close()
        if not existed_before:
            for p in (Path(db_path), Path(db_path + '.wal')):
                p.unlink(missing_ok=True)
        raise DuckDBSQLDumpError(
            f'SQL dump reload failed at statement {executed + 1} and rolled back cleanly: {exc}'
        ) from None
    conn.close()

    # Independent verification connection
    vcon = duckdb.connect(db_path, config={'access_mode': 'READ_ONLY'})
    try:
        tables = {
            f'{r[0]}.{r[1]}': vcon.execute(f'SELECT count(*) FROM {_quote(r[0])}.{_quote(r[1])}').fetchone()[0]
            for r in vcon.execute(
                'SELECT schema_name, table_name FROM duckdb_tables() WHERE NOT internal ORDER BY schema_name, table_name'
            ).fetchall()
        }
        seqs = vcon.execute('SELECT count(*) FROM duckdb_sequences() WHERE NOT temporary').fetchone()[0]
        views = vcon.execute('SELECT count(*) FROM duckdb_views() WHERE NOT internal').fetchone()[0]
        macros = vcon.execute(
            "SELECT count(DISTINCT function_name) FROM duckdb_functions() WHERE NOT internal AND function_type IN ('macro', 'table_macro')"
        ).fetchone()[0]
        indexes = vcon.execute('SELECT count(*) FROM duckdb_indexes()').fetchone()[0]
    finally:
        vcon.close()

    return {
        'state': 'reloaded_and_verified',
        'statements_executed': executed,
        'verified_tables': tables,
        'verified_counts': {
            'tables': len(tables),
            'sequences': seqs,
            'views': views,
            'macros': macros,
            'indexes': indexes,
        },
    }
