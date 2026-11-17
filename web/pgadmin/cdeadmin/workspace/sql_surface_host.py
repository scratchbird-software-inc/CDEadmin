##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Host-centric engine for Surface 2: SQL Editor & Visual Query Builder (`sql: <DATABASE>`).

Provides:
- Dedicated per-Surface host sessions & transaction activity tracking (Firebird-aware)
- Terminator-aware SQL statement/script splitting (Firebird `SET TERM`, PG `$$`, MySQL `DELIMITER`, SQLite `BEGIN..END`)
- Parameter extraction (`:name`, `@name`, `$1`, `?`) & bound execution
- Multi-result-set host buffering + single-table native row identity & Surface 1 batch row staging
- Universal SQL script generation across all catalog object kinds (`table`, `view`, `procedure`, `function`, `package`, `sequence`, `domain`, `trigger`, `index`, `exception`, `role`)
- Multi-tag SQL Snippets Library (`DATA_DIR/sql_snippets.db`) with faceted AND/OR tag filtering
- Quick Queries store (`DATA_DIR/quick_queries.db`) persisting SQL + parameters + Surface 1 display layout
- Shared host multi-format exporter (`CSV/TSV`, `XLSX`, `ODS`, `PDF`, `JSON`, `SQL`) in pure Python stdlib
"""

from __future__ import annotations

import base64
import collections
import copy
import csv
import io
import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from .data_surface_host import (
    AUTO_LOCAL_SORT_THRESHOLD,
    StagedRowMutation,
    SurfaceLayoutStore,
    _comparable_sort_key,
    _estimate_bytes,
    _infer_client_type,
    _plan_sql_text,
    _quote_ident,
    _row_matches_filter,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# 1. Terminator-Aware SQL Splitter & Parameter Extractor
# ============================================================================

_SET_TERM_RE = re.compile(r'^\s*SET\s+TERM\s+(\S+)\s*', re.IGNORECASE)
_DELIMITER_RE = re.compile(r'^\s*DELIMITER\s+(\S+)\s*$', re.IGNORECASE)
_NAMED_PARAM_RE = re.compile(r'(?<![:\w]):([A-Za-z_][A-Za-z0-9_]*)')
_POS_PG_PARAM_RE = re.compile(r'\$(\d+)')


@dataclass
class ParsedSqlSegment:
    sql: str
    start_offset: int
    end_offset: int
    start_line: int
    terminator: str


def split_sql_statements(
    source: str,
    default_terminator: str = ';',
    engine_id: str = 'relational',
) -> list[ParsedSqlSegment]:
    """Split SQL source into individual executable statements while honoring:
    - Firebird `SET TERM <new> <old>` directives & configurable terminator
    - Single/double/backtick quoted strings & escaped quotes
    - `--` line comments and `/* ... */` block comments
    - PostgreSQL `$tag$...$tag$` dollar-quoted bodies
    - MySQL/MariaDB `DELIMITER <term>` directives
    - SQLite/DuckDB/Firebird `BEGIN ... END` procedural/trigger blocks when terminator is `;`
    """
    text = str(source or '')
    if not text.strip():
        return []

    term = str(default_terminator or ';').strip() or ';'
    n = len(text)
    i = 0
    seg_start = 0
    seg_line = 1
    cur_line = 1
    compound_depth = 0
    segments: list[ParsedSqlSegment] = []

    def _flush_segment(end_pos: int, active_term: str, next_pos: int) -> None:
        nonlocal seg_start, seg_line, compound_depth
        raw = text[seg_start:end_pos].strip()
        if raw:
            segments.append(
                ParsedSqlSegment(
                    sql=raw,
                    start_offset=seg_start,
                    end_offset=end_pos,
                    start_line=seg_line,
                    terminator=active_term,
                )
            )
        seg_start = next_pos
        seg_line = cur_line + text[end_pos:next_pos].count('\n')
        compound_depth = 0

    while i < n:
        # Check line-start directives (`SET TERM` / `DELIMITER`) at start of a statement or line
        if i == seg_start or (i > 0 and text[i - 1] == '\n'):
            line_end = text.find('\n', i)
            if line_end < 0:
                line_end = n
            line_str = text[i:line_end]

            # Firebird: `SET TERM ^ ;` (terminated by current `term`)
            m_term = _SET_TERM_RE.match(line_str)
            if m_term:
                # Find current terminator after the new terminator token
                after_tok_idx = i + m_term.end()
                term_pos = text.find(term, after_tok_idx)
                if term_pos >= 0:
                    candidate_new = text[i + m_term.start(1):term_pos].strip()
                    if candidate_new:
                        # Flush anything accumulated before SET TERM
                        if i > seg_start and text[seg_start:i].strip():
                            _flush_segment(i, term, i)
                        term = candidate_new
                        next_idx = term_pos + len(term)
                        cur_line += text[i:next_idx].count('\n')
                        i = next_idx
                        seg_start = i
                        seg_line = cur_line
                        continue

            # MySQL / MariaDB: `DELIMITER //`
            m_delim = _DELIMITER_RE.match(line_str.strip())
            if m_delim:
                if i > seg_start and text[seg_start:i].strip():
                    _flush_segment(i, term, i)
                term = m_delim.group(1).strip()
                next_idx = min(n, line_end + 1)
                cur_line += text[i:next_idx].count('\n')
                i = next_idx
                seg_start = i
                seg_line = cur_line
                continue

        ch = text[i]
        if ch == '\n':
            cur_line += 1
            i += 1
            continue

        # Line comment `-- ...`
        if ch == '-' and i + 1 < n and text[i + 1] == '-':
            nl = text.find('\n', i + 2)
            if nl < 0:
                i = n
            else:
                cur_line += 1
                i = nl + 1
            continue

        # Block comment `/* ... */`
        if ch == '/' and i + 1 < n and text[i + 1] == '*':
            end_c = text.find('*/', i + 2)
            if end_c < 0:
                cur_line += text[i:].count('\n')
                i = n
            else:
                cur_line += text[i:end_c + 2].count('\n')
                i = end_c + 2
            continue

        # Quoted strings `'...'`, `"..."`, `` `...` ``
        if ch in ("'", '"', '`'):
            quote = ch
            i += 1
            while i < n:
                c = text[i]
                if c == '\n':
                    cur_line += 1
                if c == '\\' and quote != '"' and engine_id in ('mysql', 'mariadb'):
                    i += 2
                    continue
                if c == quote:
                    if i + 1 < n and text[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue

        # PostgreSQL dollar quoting `$tag$...$tag$`
        if ch == '$':
            m_dq = re.match(r'\$([A-Za-z_][A-Za-z0-9_]*)?\$', text[i:])
            if m_dq:
                tag = m_dq.group(0)
                close_dq = text.find(tag, i + len(tag))
                if close_dq >= 0:
                    cur_line += text[i:close_dq + len(tag)].count('\n')
                    i = close_dq + len(tag)
                    continue

        # Track procedural `BEGIN ... END` blocks when using `;` terminator
        # (e.g. SQLite `CREATE TRIGGER ... BEGIN ... END;` or inline `EXECUTE BLOCK AS BEGIN ... END`)
        if term == ';' and (ch.isalpha() or ch == '_'):
            m_word = re.match(r'[A-Za-z_][A-Za-z0-9_$]*', text[i:])
            if m_word:
                word_up = m_word.group(0).upper()
                if word_up == 'BEGIN':
                    # Distinguish `BEGIN TRANSACTION` / `BEGIN WORK` / `BEGIN;` from compound `BEGIN <stmt>`
                    rest = text[i + len(word_up):].lstrip()
                    if rest and not re.match(
                        r'^(TRANSACTION|WORK|IMMEDIATE|DEFERRED|EXCLUSIVE)\b',
                        rest,
                        re.IGNORECASE,
                    ) and not rest.startswith(';'):
                        compound_depth += 1
                elif word_up == 'CASE' and compound_depth > 0:
                    compound_depth += 1
                elif word_up == 'END' and compound_depth > 0:
                    compound_depth = max(0, compound_depth - 1)
                i += len(m_word.group(0))
                continue

        # Active statement terminator match (only when outside nested `BEGIN ... END` if `;`)
        if compound_depth == 0 and text.startswith(term, i):
            _flush_segment(i, term, i + len(term))
            i += len(term)
            continue

        i += 1

    if seg_start < n and text[seg_start:].strip():
        _flush_segment(n, term, n)

    return segments


def extract_statement_at_cursor(
    source: str,
    cursor_offset: int = 0,
    default_terminator: str = ';',
    engine_id: str = 'relational',
) -> ParsedSqlSegment | None:
    segments = split_sql_statements(source, default_terminator, engine_id)
    if not segments:
        return None
    safe_off = max(0, min(int(cursor_offset or 0), len(source or '')))
    for seg in segments:
        if seg.start_offset <= safe_off <= seg.end_offset + len(seg.terminator):
            return seg
    # If cursor is in trailing whitespace after the last statement, return the last statement
    return segments[-1]


def extract_query_parameters(sql: str) -> list[dict[str, Any]]:
    """Detect `:named`, `$1`, or `?` parameter placeholders outside string literals/comments."""
    cleaned: list[str] = []
    text = str(sql or '')
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '-' and i + 1 < n and text[i + 1] == '-':
            nl = text.find('\n', i + 2)
            i = n if nl < 0 else nl + 1
            cleaned.append(' ')
            continue
        if ch == '/' and i + 1 < n and text[i + 1] == '*':
            end_c = text.find('*/', i + 2)
            i = n if end_c < 0 else end_c + 2
            cleaned.append(' ')
            continue
        if ch in ("'", '"', '`'):
            quote = ch
            i += 1
            while i < n:
                if text[i] == quote:
                    if i + 1 < n and text[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            cleaned.append("''")
            continue
        cleaned.append(ch)
        i += 1

    scrubbed = ''.join(cleaned)
    named: list[str] = []
    for m in _NAMED_PARAM_RE.finditer(scrubbed):
        pname = m.group(1)
        if pname not in named:
            named.append(pname)
    if named:
        return [
            {'name': p, 'kind': 'named', 'position': idx + 1, 'data_type': 'text'}
            for idx, p in enumerate(named)
        ]

    pg_pos = sorted({int(m.group(1)) for m in _POS_PG_PARAM_RE.finditer(scrubbed)})
    if pg_pos:
        return [
            {'name': f'${pos}', 'kind': 'positional', 'position': pos, 'data_type': 'text'}
            for pos in pg_pos
        ]

    q_count = scrubbed.count('?')
    if q_count > 0:
        return [
            {
                'name': f'param_{idx + 1}',
                'kind': 'qmark',
                'position': idx + 1,
                'data_type': 'text',
            }
            for idx in range(q_count)
        ]
    return []


def bind_named_to_positional_if_needed(
    sql: str,
    param_values: dict[str, Any] | list[Any],
    parameter_shape: str = 'array',
) -> tuple[str, dict[str, Any] | list[Any]]:
    """Convert `:named` placeholders to `?` array when provider expects positional array (e.g. Firebird/SQLite/DuckDB)."""
    if isinstance(param_values, list):
        return sql, param_values
    val_map = dict(param_values or {})
    if not val_map:
        return sql, ([] if parameter_shape == 'array' else {})

    detected = extract_query_parameters(sql)
    if not detected:
        return sql, ([] if parameter_shape == 'array' else val_map)

    if detected[0]['kind'] == 'qmark':
        ordered = [val_map.get(d['name']) for d in detected]
        return sql, ordered

    if detected[0]['kind'] == 'positional':
        ordered = [val_map.get(d['name']) for d in detected]
        return sql, ordered

    if parameter_shape == 'array':
        ordered_vals: list[Any] = []

        def _repl(match: re.Match[str]) -> str:
            pname = match.group(1)
            ordered_vals.append(val_map.get(pname))
            return '?'

        # Replace `:name` outside comments and string literals
        out: list[str] = []
        i = 0
        n = len(sql)
        while i < n:
            ch = sql[i]
            if ch == '-' and i + 1 < n and sql[i + 1] == '-':
                nl = sql.find('\n', i + 2)
                end_i = n if nl < 0 else nl + 1
                out.append(sql[i:end_i])
                i = end_i
                continue
            if ch == '/' and i + 1 < n and sql[i + 1] == '*':
                end_c = sql.find('*/', i + 2)
                end_i = n if end_c < 0 else end_c + 2
                out.append(sql[i:end_i])
                i = end_i
                continue
            if ch in ("'", '"', '`'):
                q = ch
                start = i
                i += 1
                while i < n:
                    if sql[i] == q:
                        if i + 1 < n and sql[i + 1] == q:
                            i += 2
                            continue
                        i += 1
                        break
                    i += 1
                out.append(sql[start:i])
                continue
            if ch == ':' and (i == 0 or not (sql[i - 1].isalnum() or sql[i - 1] in (':', '_'))):
                m = re.match(r':([A-Za-z_][A-Za-z0-9_]*)', sql[i:])
                if m:
                    ordered_vals.append(val_map.get(m.group(1)))
                    out.append('?')
                    i += len(m.group(0))
                    continue
            out.append(ch)
            i += 1
        return ''.join(out), ordered_vals

    return sql, val_map


# ============================================================================
# 2. Tagged SQL Snippets Store (`DATA_DIR/sql_snippets.db`)
# ============================================================================

BUILTIN_SNIPPETS: tuple[dict[str, Any], ...] = (
    {
        'snippet_id': 'builtin-fb-execute-block',
        'title': 'Firebird EXECUTE BLOCK',
        'shortcut': 'eb',
        'engine_id': 'firebird',
        'description': 'Anonymous PSQL block with input/output parameters and SET TERM wrapper.',
        'sql_text': (
            'SET TERM ^ ;\n'
            'EXECUTE BLOCK (p_min NUMERIC(14,2) = :min_amount)\n'
            'RETURNS (out_id INTEGER, out_total NUMERIC(14,2))\n'
            'AS\n'
            'BEGIN\n'
            '  FOR SELECT ID, BALANCE\n'
            '      FROM ${table}\n'
            '      WHERE BALANCE >= :p_min\n'
            '      INTO :out_id, :out_total\n'
            '  DO\n'
            '    SUSPEND;\n'
            'END^\n'
            'SET TERM ; ^'
        ),
        'tags': ['firebird', 'psql', 'dml', 'procedure'],
    },
    {
        'snippet_id': 'builtin-fb-mon-transactions',
        'title': 'Firebird Active Transactions & OIT/OAT Gap',
        'shortcut': 'fbtx',
        'engine_id': 'firebird',
        'description': 'Inspect MON$TRANSACTIONS and MON$DATABASE OIT/OAT sweep health.',
        'sql_text': (
            'SELECT\n'
            '  t.MON$TRANSACTION_ID,\n'
            '  a.MON$USER,\n'
            '  a.MON$REMOTE_ADDRESS,\n'
            '  t.MON$TIMESTAMP,\n'
            '  t.MON$ISOLATION_MODE,\n'
            '  (d.MON$NEXT_TRANSACTION - d.MON$OLDEST_ACTIVE) AS OAT_GAP\n'
            'FROM MON$TRANSACTIONS t\n'
            'JOIN MON$ATTACHMENTS a ON a.MON$ATTACHMENT_ID = t.MON$ATTACHMENT_ID\n'
            'CROSS JOIN MON$DATABASE d\n'
            'ORDER BY t.MON$TIMESTAMP ASC;'
        ),
        'tags': ['firebird', 'monitoring', 'transactions', 'performance'],
    },
    {
        'snippet_id': 'builtin-fb-package',
        'title': 'Firebird CREATE OR ALTER PACKAGE + BODY',
        'shortcut': 'fbpkg',
        'engine_id': 'firebird',
        'description': 'PSQL Package specification and implementation body with SET TERM.',
        'sql_text': (
            'SET TERM ^ ;\n'
            'CREATE OR ALTER PACKAGE PKG_LEDGER\n'
            'AS\n'
            'BEGIN\n'
            '  FUNCTION FN_NET_BALANCE(p_account_id INTEGER) RETURNS NUMERIC(14,2);\n'
            '  PROCEDURE SP_POST_ENTRY(p_account_id INTEGER, p_amount NUMERIC(14,2));\n'
            'END^\n\n'
            'RECREATE PACKAGE BODY PKG_LEDGER\n'
            'AS\n'
            'BEGIN\n'
            '  FUNCTION FN_NET_BALANCE(p_account_id INTEGER) RETURNS NUMERIC(14,2)\n'
            '  AS\n'
            '  BEGIN\n'
            '    RETURN 0;\n'
            '  END\n\n'
            '  PROCEDURE SP_POST_ENTRY(p_account_id INTEGER, p_amount NUMERIC(14,2))\n'
            '  AS\n'
            '  BEGIN\n'
            '    /* Implementation */\n'
            '  END\n'
            'END^\n'
            'SET TERM ; ^'
        ),
        'tags': ['firebird', 'package', 'ddl', 'psql', 'function', 'procedure'],
    },
    {
        'snippet_id': 'builtin-fb-bi-seq-trigger',
        'title': 'Firebird Sequence + Before Insert Trigger',
        'shortcut': 'fbtrig',
        'engine_id': 'firebird',
        'description': 'Create a sequence and BEFORE INSERT auto-ID trigger.',
        'sql_text': (
            'CREATE SEQUENCE SEQ_${table}_ID;\n\n'
            'SET TERM ^ ;\n'
            'CREATE OR ALTER TRIGGER BI_${table}_ID FOR ${table}\n'
            'ACTIVE BEFORE INSERT POSITION 0\n'
            'AS\n'
            'BEGIN\n'
            '  IF (NEW.ID IS NULL) THEN\n'
            '    NEW.ID = NEXT VALUE FOR SEQ_${table}_ID;\n'
            'END^\n'
            'SET TERM ; ^'
        ),
        'tags': ['firebird', 'trigger', 'sequence', 'table', 'ddl'],
    },
    {
        'snippet_id': 'builtin-ansi-cte-window',
        'title': 'CTE + Window Ranking Query',
        'shortcut': 'cte',
        'engine_id': 'ansi',
        'description': 'Common Table Expression with ROW_NUMBER / SUM OVER window analytics.',
        'sql_text': (
            'WITH ranked_rows AS (\n'
            '  SELECT\n'
            '    t.*,\n'
            '    ROW_NUMBER() OVER (ORDER BY ${pk_col} DESC) AS rn\n'
            '  FROM ${table} t\n'
            ')\n'
            'SELECT *\n'
            'FROM ranked_rows\n'
            'WHERE rn <= 50;'
        ),
        'tags': ['ansi', 'cte', 'window', 'dml', 'table', 'analytics'],
    },
    {
        'snippet_id': 'builtin-pg-locks',
        'title': 'PostgreSQL Blocking & Waiting Locks',
        'shortcut': 'pglocks',
        'engine_id': 'postgresql',
        'description': 'Inspect active sessions blocked on locks in pg_locks / pg_stat_activity.',
        'sql_text': (
            'SELECT\n'
            '  a.pid,\n'
            '  a.usename,\n'
            '  a.state,\n'
            '  a.wait_event_type,\n'
            '  a.query_start,\n'
            '  a.query\n'
            'FROM pg_stat_activity a\n'
            "WHERE a.state <> 'idle'\n"
            'ORDER BY a.query_start ASC;'
        ),
        'tags': ['postgresql', 'monitoring', 'transactions', 'performance'],
    },
)


class SqlSnippetsStore:
    """SQLite store for built-in, personal, and project-shared multi-tag SQL snippets."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            try:
                import config as pg_config
                data_dir = getattr(pg_config, 'DATA_DIR', None)
            except Exception:
                data_dir = None
            base = Path(data_dir or os.path.expanduser('~/.cdeadmin'))
            base.mkdir(parents=True, exist_ok=True)
            db_path = base / 'sql_snippets.db'
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sql_snippet (
                    snippet_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    shortcut TEXT NOT NULL DEFAULT '',
                    engine_id TEXT NOT NULL DEFAULT 'ansi',
                    scope TEXT NOT NULL DEFAULT 'personal',
                    project_id TEXT NOT NULL DEFAULT '',
                    owner_user_id INTEGER NOT NULL DEFAULT 0,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    sql_text TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sql_snippet_tag (
                    snippet_id TEXT NOT NULL REFERENCES sql_snippet(snippet_id) ON DELETE CASCADE,
                    tag TEXT NOT NULL,
                    PRIMARY KEY (snippet_id, tag)
                );
                CREATE INDEX IF NOT EXISTS idx_snippet_tag_lookup
                    ON sql_snippet_tag(tag, snippet_id);
                """
            )
            now = _now_iso()
            for item in BUILTIN_SNIPPETS:
                exists = conn.execute(
                    'SELECT 1 FROM sql_snippet WHERE snippet_id = ?',
                    (item['snippet_id'],),
                ).fetchone()
                if not exists:
                    conn.execute(
                        """
                        INSERT INTO sql_snippet
                            (snippet_id, title, description, shortcut, engine_id, scope,
                             project_id, owner_user_id, favorite, sql_text, updated_at)
                        VALUES (?, ?, ?, ?, ?, 'builtin', '', 0, 0, ?, ?)
                        """,
                        (
                            item['snippet_id'],
                            item['title'],
                            item['description'],
                            item['shortcut'],
                            item['engine_id'],
                            item['sql_text'],
                            now,
                        ),
                    )
                    for tag in item['tags']:
                        clean_tag = str(tag).strip().lower()
                        if clean_tag:
                            conn.execute(
                                'INSERT OR IGNORE INTO sql_snippet_tag (snippet_id, tag) VALUES (?, ?)',
                                (item['snippet_id'], clean_tag),
                            )

    @staticmethod
    def _normalize_tags(tags: list[str] | str | None) -> list[str]:
        if tags is None:
            return []
        raw_items = (
            re.split(r'[,\s]+', tags) if isinstance(tags, str) else list(tags)
        )
        cleaned: list[str] = []
        for t in raw_items:
            norm = re.sub(r'^#+', '', str(t or '').strip().lower())
            norm = re.sub(r'[^a-z0-9_.:-]+', '-', norm).strip('-')
            if norm and norm not in cleaned:
                cleaned.append(norm)
        return cleaned

    def save_snippet(
        self,
        user_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        sid = str(payload.get('snippet_id') or f'snip-{uuid.uuid4()}')
        title = str(payload.get('title') or 'Untitled Snippet').strip()[:160]
        desc = str(payload.get('description') or '').strip()[:500]
        shortcut = re.sub(r'[^a-zA-Z0-9_-]', '', str(payload.get('shortcut') or ''))[:24]
        engine_id = str(payload.get('engine_id') or 'ansi').strip().lower()
        scope = str(payload.get('scope') or 'personal').strip().lower()
        if scope not in ('personal', 'project', 'builtin'):
            scope = 'personal'
        project_id = str(payload.get('project_id') or '').strip()
        favorite = 1 if payload.get('favorite') else 0
        sql_text = str(payload.get('sql_text') or '')
        tags = self._normalize_tags(payload.get('tags'))
        if engine_id and engine_id not in tags:
            tags.insert(0, engine_id)
        now = _now_iso()

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sql_snippet
                    (snippet_id, title, description, shortcut, engine_id, scope,
                     project_id, owner_user_id, favorite, sql_text, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snippet_id) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    shortcut = excluded.shortcut,
                    engine_id = excluded.engine_id,
                    scope = excluded.scope,
                    project_id = excluded.project_id,
                    favorite = excluded.favorite,
                    sql_text = excluded.sql_text,
                    updated_at = excluded.updated_at
                """,
                (
                    sid,
                    title,
                    desc,
                    shortcut,
                    engine_id,
                    scope,
                    project_id,
                    int(user_id),
                    favorite,
                    sql_text,
                    now,
                ),
            )
            conn.execute('DELETE FROM sql_snippet_tag WHERE snippet_id = ?', (sid,))
            for tag in tags:
                conn.execute(
                    'INSERT OR IGNORE INTO sql_snippet_tag (snippet_id, tag) VALUES (?, ?)',
                    (sid, tag),
                )
        return self.get_snippet(sid) or {'snippet_id': sid}

    def get_snippet(self, snippet_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                'SELECT * FROM sql_snippet WHERE snippet_id = ?', (snippet_id,)
            ).fetchone()
            if not row:
                return None
            tags = [
                r['tag']
                for r in conn.execute(
                    'SELECT tag FROM sql_snippet_tag WHERE snippet_id = ? ORDER BY tag ASC',
                    (snippet_id,),
                ).fetchall()
            ]
        return {
            'snippet_id': row['snippet_id'],
            'title': row['title'],
            'description': row['description'],
            'shortcut': row['shortcut'],
            'engine_id': row['engine_id'],
            'scope': row['scope'],
            'project_id': row['project_id'],
            'owner_user_id': row['owner_user_id'],
            'favorite': bool(row['favorite']),
            'sql_text': row['sql_text'],
            'tags': tags,
            'updated_at': row['updated_at'],
        }

    def delete_snippet(self, user_id: int, snippet_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            conn.execute(
                "DELETE FROM sql_snippet WHERE snippet_id = ? AND scope != 'builtin'",
                (snippet_id,),
            )
        return {'deleted': snippet_id}

    def toggle_favorite(self, user_id: int, snippet_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                'SELECT favorite FROM sql_snippet WHERE snippet_id = ?',
                (snippet_id,),
            ).fetchone()
            if not row:
                return None
            next_fav = 0 if row['favorite'] else 1
            conn.execute(
                'UPDATE sql_snippet SET favorite = ?, updated_at = ? WHERE snippet_id = ?',
                (next_fav, _now_iso(), snippet_id),
            )
        return self.get_snippet(snippet_id)

    def search_snippets(
        self,
        user_id: int,
        *,
        engine_id: str | None = None,
        search_text: str = '',
        selected_tags: list[str] | None = None,
        tag_mode: str = 'and',
        favorites_only: bool = False,
        include_all_engines: bool = False,
    ) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sql_snippet
                WHERE scope IN ('builtin', 'project') OR owner_user_id = ?
                ORDER BY favorite DESC, title COLLATE NOCASE ASC
                """,
                (int(user_id),),
            ).fetchall()
            tag_rows = conn.execute(
                'SELECT snippet_id, tag FROM sql_snippet_tag ORDER BY tag ASC'
            ).fetchall()

        tags_by_id: dict[str, list[str]] = collections.defaultdict(list)
        for tr in tag_rows:
            tags_by_id[tr['snippet_id']].append(tr['tag'])

        # Parse inline `#tag` tokens inside `search_text`
        inline_tags: list[str] = []
        free_words: list[str] = []
        for token in str(search_text or '').split():
            if token.startswith('#') and len(token) > 1:
                inline_tags.append(token[1:].lower())
            else:
                free_words.append(token.lower())

        active_tags = self._normalize_tags(list(selected_tags or []) + inline_tags)
        eng_norm = str(engine_id or '').split('-')[0].strip().lower()

        engine_scoped_items: list[dict[str, Any]] = []
        for r in rows:
            item_tags = tags_by_id.get(r['snippet_id'], [])
            if (
                not include_all_engines
                and eng_norm
                and r['engine_id'] not in ('ansi', '', eng_norm)
                and eng_norm not in item_tags
            ):
                continue
            if favorites_only and not r['favorite']:
                continue
            engine_scoped_items.append({
                'snippet_id': r['snippet_id'],
                'title': r['title'],
                'description': r['description'],
                'shortcut': r['shortcut'],
                'engine_id': r['engine_id'],
                'scope': r['scope'],
                'project_id': r['project_id'],
                'favorite': bool(r['favorite']),
                'sql_text': r['sql_text'],
                'tags': item_tags,
                'updated_at': r['updated_at'],
            })

        # Compute live tag counts across the engine-eligible set
        tag_counts: collections.Counter[str] = collections.Counter()
        for item in engine_scoped_items:
            for tg in item['tags']:
                tag_counts[tg] += 1

        matched: list[dict[str, Any]] = []
        for item in engine_scoped_items:
            item_tag_set = set(item['tags'])
            if active_tags:
                if str(tag_mode).lower() == 'or':
                    if not any(t in item_tag_set for t in active_tags):
                        continue
                else:
                    if not all(t in item_tag_set for t in active_tags):
                        continue
            if free_words:
                haystack = ' '.join([
                    item['title'],
                    item['description'],
                    item['shortcut'],
                    item['sql_text'],
                    ' '.join(item['tags']),
                ]).lower()
                if not all(w in haystack for w in free_words):
                    continue
            matched.append(item)

        return {
            'snippets': matched,
            'available_tags': [
                {'tag': tg, 'count': cnt}
                for tg, cnt in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))
            ],
            'active_tags': active_tags,
            'tag_mode': 'or' if str(tag_mode).lower() == 'or' else 'and',
        }


# ============================================================================
# 3. Quick Queries Store (`DATA_DIR/quick_queries.db`)
# ============================================================================


class QuickQueryStore:
    """Persists Quick Queries (SQL + Terminator + Parameter Defaults + Surface 1 Display Layout)."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            try:
                import config as pg_config
                data_dir = getattr(pg_config, 'DATA_DIR', None)
            except Exception:
                data_dir = None
            base = Path(data_dir or os.path.expanduser('~/.cdeadmin'))
            base.mkdir(parents=True, exist_ok=True)
            db_path = base / 'quick_queries.db'
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS quick_query (
                    query_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    server_id INTEGER NOT NULL DEFAULT 0,
                    database_target_id TEXT NOT NULL DEFAULT '',
                    engine_id TEXT NOT NULL DEFAULT '',
                    project_id TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    sql_text TEXT NOT NULL,
                    terminator TEXT NOT NULL DEFAULT ';',
                    parameters_json TEXT NOT NULL DEFAULT '[]',
                    display_layout_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_quick_query_db
                    ON quick_query(user_id, server_id, database_target_id);
                """
            )

    def save_quick_query(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        qid = str(payload.get('query_id') or f'qq-{uuid.uuid4()}')
        name = str(payload.get('name') or 'Quick Query').strip()[:160]
        desc = str(payload.get('description') or '').strip()[:500]
        server_id = int(payload.get('server_id') or 0)
        db_target = str(payload.get('database_target_id') or '')
        engine_id = str(payload.get('engine_id') or '')
        project_id = str(payload.get('project_id') or '')
        sql_text = str(payload.get('sql_text') or '')
        terminator = str(payload.get('terminator') or ';').strip() or ';'
        params_json = json.dumps(payload.get('parameters') or [], ensure_ascii=False)
        layout_json = json.dumps(
            payload.get('display_layout') or {}, ensure_ascii=False, sort_keys=True
        )
        now = _now_iso()

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO quick_query
                    (query_id, user_id, server_id, database_target_id, engine_id, project_id,
                     name, description, sql_text, terminator, parameters_json, display_layout_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(query_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    sql_text = excluded.sql_text,
                    terminator = excluded.terminator,
                    parameters_json = excluded.parameters_json,
                    display_layout_json = excluded.display_layout_json,
                    updated_at = excluded.updated_at
                """,
                (
                    qid,
                    int(user_id),
                    server_id,
                    db_target,
                    engine_id,
                    project_id,
                    name,
                    desc,
                    sql_text,
                    terminator,
                    params_json,
                    layout_json,
                    now,
                ),
            )
        return self.get_quick_query(qid) or {'query_id': qid}

    def get_quick_query(self, query_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            r = conn.execute(
                'SELECT * FROM quick_query WHERE query_id = ?', (query_id,)
            ).fetchone()
        if not r:
            return None
        return self._row_to_dict(r)

    @staticmethod
    def _row_to_dict(r: sqlite3.Row) -> dict[str, Any]:
        return {
            'query_id': r['query_id'],
            'user_id': r['user_id'],
            'server_id': r['server_id'],
            'database_target_id': r['database_target_id'],
            'engine_id': r['engine_id'],
            'project_id': r['project_id'],
            'name': r['name'],
            'description': r['description'],
            'sql_text': r['sql_text'],
            'terminator': r['terminator'],
            'parameters': json.loads(r['parameters_json'] or '[]'),
            'display_layout': json.loads(r['display_layout_json'] or '{}'),
            'updated_at': r['updated_at'],
        }

    def list_quick_queries(
        self,
        user_id: int,
        server_id: int | None = None,
        database_target_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ['user_id = ?']
        args: list[Any] = [int(user_id)]
        if server_id is not None:
            clauses.append('(server_id = ? OR server_id = 0)')
            args.append(int(server_id))
        if database_target_id:
            clauses.append("(database_target_id = ? OR database_target_id = '')")
            args.append(str(database_target_id))
        where_sql = ' AND '.join(clauses)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f'SELECT * FROM quick_query WHERE {where_sql} ORDER BY name COLLATE NOCASE ASC',
                tuple(args),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete_quick_query(self, user_id: int, query_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            conn.execute(
                'DELETE FROM quick_query WHERE query_id = ? AND user_id = ?',
                (query_id, int(user_id)),
            )
        return {'deleted': query_id}


# ============================================================================
# 4. Universal SQL Script Generator Across All Catalog Object Kinds
# ============================================================================


def generate_universal_object_sql(
    workspace_service: Any,
    server: Any,
    *,
    engine_id: str,
    database_target_id: str | None,
    target_resource: dict[str, Any],
    script_kind: str,
) -> dict[str, Any]:
    """Generate engine-native SQL script for any SQL catalog object kind without executing it."""
    eng = str(engine_id or 'relational').split('-')[0].lower()
    r_kind = str(target_resource.get('resource_kind') or 'table').lower()
    r_id = str(target_resource.get('resource_id') or '')
    raw_name = str(
        target_resource.get('display_name')
        or target_resource.get('name')
        or r_id.split(':')[-1]
        or 'OBJECT_NAME'
    )
    path_parts = list(target_resource.get('display_path') or [raw_name])
    qual_name = '.'.join(_quote_ident(str(p), eng) for p in path_parts if p) or _quote_ident(raw_name, eng)
    ident_name = _quote_ident(raw_name, eng)

    # Attempt to inspect live catalog properties/DDL/columns from provider
    inspected: dict[str, Any] = {}
    if r_id and hasattr(workspace_service, 'inspect_resource'):
        try:
            inspected = (
                workspace_service.inspect_resource(
                    server,
                    {
                        'resource_id': r_id,
                        'database_target_id': database_target_id,
                    },
                )
                or {}
            )
        except Exception:
            inspected = {}

    props = (
        inspected.get('properties')
        or inspected.get('extensions', {}).get('provider', {}).get('native', {})
        or {}
    )
    cols_meta: list[dict[str, Any]] = list(
        props.get('columns') or inspected.get('columns') or []
    )
    # If table/view columns weren't on `inspect_resource`, peek 0-row/1-row metadata if available
    if not cols_meta and r_kind in ('table', 'view', 'materialized-view', 'foreign-table'):
        if hasattr(workspace_service, 'read_visual_admin_rows'):
            try:
                peek = workspace_service.read_visual_admin_rows(
                    server,
                    {
                        'target_resource': target_resource,
                        'limit': 1,
                        'database_target_id': database_target_id,
                    },
                )
                cols_meta = list(peek.get('columns') or [])
                if peek.get('continuation') and hasattr(
                    workspace_service, 'cancel_visual_admin_rows'
                ):
                    workspace_service.cancel_visual_admin_rows(
                        server,
                        {
                            'continuation': peek['continuation'],
                            'database_target_id': database_target_id,
                        },
                    )
            except Exception:
                pass

    native_ddl = str(
        props.get('ddl')
        or props.get('source')
        or inspected.get('ddl')
        or inspected.get('source')
        or ''
    ).strip()

    kind_norm = str(script_kind or 'select').lower()
    terminator = ';'

    # --- Relation DML & Trigger Scripts ---
    if r_kind in ('table', 'view', 'materialized-view', 'foreign-table', 'partitioned-table'):
        col_names = [str(c.get('name')) for c in cols_meta if c.get('name')]
        pk_cols = [str(c.get('name')) for c in cols_meta if c.get('key')]
        insertable_cols = [
            c for c in cols_meta
            if c.get('name')
            and c.get('insertable', True) is not False
            and not c.get('computed_source')
            and not c.get('generated')
        ]
        updatable_cols = [
            c for c in insertable_cols
            if not c.get('key') and c.get('editable', True) is not False
        ] or insertable_cols

        where_pk = (
            ' AND '.join(
                f"{_quote_ident(pk, eng)} = :{re.sub(r'[^A-Za-z0-9_]', '_', pk.lower())}"
                for pk in pk_cols
            )
            if pk_cols
            else (
                'RDB$DB_KEY = :db_key'
                if eng == 'firebird'
                else '1 = 0 /* Specify primary key / row filter */'
            )
        )

        if kind_norm == 'select':
            proj = (
                ',\n  '.join(_quote_ident(c, eng) for c in col_names)
                if col_names
                else '*'
            )
            sql = f'SELECT\n  {proj}\nFROM {qual_name}\nWHERE 1 = 1;'
            return {'sql': sql, 'terminator': ';'}

        if kind_norm == 'insert':
            if insertable_cols:
                cols_sql = ',\n  '.join(
                    _quote_ident(str(c['name']), eng) for c in insertable_cols
                )
                vals_lines = []
                for c in insertable_cols:
                    cname = str(c['name'])
                    p_tok = re.sub(r'[^A-Za-z0-9_]', '_', cname.lower())
                    t_hint = ' '.join(
                        p for p in [
                            str(c.get('native_type') or c.get('data_type') or ''),
                            str(c.get('domain_name') or c.get('domain') or ''),
                            'NOT NULL' if c.get('nullable') is False else 'NULL',
                        ] if p
                    )
                    vals_lines.append(f'  :{p_tok} /* {cname}: {t_hint} */')
                sql = (
                    f'INSERT INTO {qual_name} (\n  {cols_sql}\n)\nVALUES (\n'
                    + ',\n'.join(vals_lines)
                    + '\n);'
                )
            else:
                sql = f'INSERT INTO {qual_name} DEFAULT VALUES;'
            return {'sql': sql, 'terminator': ';'}

        if kind_norm == 'update':
            set_lines = []
            for c in updatable_cols:
                cname = str(c['name'])
                p_tok = re.sub(r'[^A-Za-z0-9_]', '_', cname.lower())
                set_lines.append(f'  {_quote_ident(cname, eng)} = :{p_tok}')
            sets_sql = ',\n'.join(set_lines) if set_lines else '  /* column = :value */'
            sql = f'UPDATE {qual_name}\nSET\n{sets_sql}\nWHERE {where_pk};'
            return {'sql': sql, 'terminator': ';'}

        if kind_norm == 'delete':
            sql = f'DELETE FROM {qual_name}\nWHERE {where_pk};'
            return {'sql': sql, 'terminator': ';'}

        if kind_norm in ('upsert', 'merge'):
            ins_cols = [str(c['name']) for c in insertable_cols] or col_names or ['ID']
            cols_sql = ', '.join(_quote_ident(c, eng) for c in ins_cols)
            vals_sql = ', '.join(
                f":{re.sub(r'[^A-Za-z0-9_]', '_', c.lower())}" for c in ins_cols
            )
            match_cols = pk_cols or [ins_cols[0]]
            match_sql = ', '.join(_quote_ident(c, eng) for c in match_cols)
            if eng == 'firebird':
                sql = (
                    f'UPDATE OR INSERT INTO {qual_name} ({cols_sql})\n'
                    f'VALUES ({vals_sql})\n'
                    f'MATCHING ({match_sql});'
                )
            elif eng in ('mysql', 'mariadb'):
                upd_sql = ', '.join(
                    f'{_quote_ident(c, eng)} = VALUES({_quote_ident(c, eng)})'
                    for c in ins_cols
                )
                sql = (
                    f'INSERT INTO {qual_name} ({cols_sql})\n'
                    f'VALUES ({vals_sql})\n'
                    f'ON DUPLICATE KEY UPDATE {upd_sql};'
                )
            else:
                upd_sql = ', '.join(
                    f'{_quote_ident(c, eng)} = EXCLUDED.{_quote_ident(c, eng)}'
                    for c in ins_cols
                )
                sql = (
                    f'INSERT INTO {qual_name} ({cols_sql})\n'
                    f'VALUES ({vals_sql})\n'
                    f'ON CONFLICT ({match_sql}) DO UPDATE SET\n  {upd_sql};'
                )
            return {'sql': sql, 'terminator': ';'}

        if kind_norm.startswith('trigger'):
            pk_first = pk_cols[0] if pk_cols else (col_names[0] if col_names else 'ID')
            trig_base = re.sub(r'[^A-Za-z0-9_]', '_', raw_name.upper())
            if eng == 'firebird':
                if kind_norm == 'trigger_bi_id':
                    sql = (
                        f'CREATE SEQUENCE {_quote_ident("SEQ_" + trig_base, eng)};\n\n'
                        f'SET TERM ^ ;\n'
                        f'CREATE OR ALTER TRIGGER {_quote_ident("BI_" + trig_base, eng)} FOR {qual_name}\n'
                        f'ACTIVE BEFORE INSERT POSITION 0\n'
                        f'AS\n'
                        f'BEGIN\n'
                        f'  IF (NEW.{_quote_ident(pk_first, eng)} IS NULL) THEN\n'
                        f'    NEW.{_quote_ident(pk_first, eng)} = NEXT VALUE FOR {_quote_ident("SEQ_" + trig_base, eng)};\n'
                        f'END^\n'
                        f'SET TERM ; ^'
                    )
                else:
                    sql = (
                        f'SET TERM ^ ;\n'
                        f'CREATE OR ALTER TRIGGER {_quote_ident("TRG_" + trig_base, eng)} FOR {qual_name}\n'
                        f'ACTIVE BEFORE INSERT OR UPDATE POSITION 0\n'
                        f'AS\n'
                        f'BEGIN\n'
                        f'  /* Trigger logic for {raw_name} */\n'
                        f'END^\n'
                        f'SET TERM ; ^'
                    )
                return {'sql': sql, 'terminator': ';'}
            if eng == 'postgresql':
                fn_name = f'trg_fn_{raw_name.lower()}'
                sql = (
                    f'CREATE OR REPLACE FUNCTION {fn_name}() RETURNS trigger\n'
                    f'LANGUAGE plpgsql AS $$\n'
                    f'BEGIN\n'
                    f'  RETURN NEW;\n'
                    f'END;\n'
                    f'$$;\n\n'
                    f'CREATE TRIGGER {_quote_ident("trg_" + raw_name.lower(), eng)}\n'
                    f'BEFORE INSERT OR UPDATE ON {qual_name}\n'
                    f'FOR EACH ROW EXECUTE FUNCTION {fn_name}();'
                )
                return {'sql': sql, 'terminator': ';'}
            sql = (
                f'CREATE TRIGGER {_quote_ident("trg_" + raw_name.lower(), eng)}\n'
                f'AFTER INSERT ON {qual_name}\n'
                f'BEGIN\n'
                f'  -- Trigger body\n'
                f'  SELECT 1;\n'
                f'END;'
            )
            return {'sql': sql, 'terminator': ';'}

        if kind_norm == 'grants':
            sql = (
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON {qual_name} TO /* role_or_user */;'
            )
            return {'sql': sql, 'terminator': ';'}

    # --- Procedures / Functions / Packages / Sequences / Domains / Other DDL ---
    if kind_norm == 'execute':
        if eng == 'firebird':
            sql = (
                f'-- Selectable or executable Firebird procedure/function:\n'
                f'EXECUTE PROCEDURE {qual_name}(/* :param1 */);\n'
                f'-- Or if selectable:\n'
                f'-- SELECT * FROM {qual_name}(/* :param1 */);'
            )
        elif r_kind == 'function':
            sql = f'SELECT {qual_name}(/* args */);'
        else:
            sql = f'CALL {qual_name}(/* args */);'
        return {'sql': sql, 'terminator': ';'}

    if r_kind == 'package':
        if kind_norm == 'ddl_drop':
            return {'sql': f'DROP PACKAGE {qual_name};', 'terminator': ';'}
        if kind_norm == 'package_body':
            sql = native_ddl or (
                f'SET TERM ^ ;\n'
                f'RECREATE PACKAGE BODY {qual_name}\n'
                f'AS\nBEGIN\n  /* Package body routines */\nEND^\n'
                f'SET TERM ; ^'
            )
            return {'sql': sql, 'terminator': ';'}
        sql = native_ddl or (
            f'SET TERM ^ ;\n'
            f'CREATE OR ALTER PACKAGE {qual_name}\n'
            f'AS\nBEGIN\n  /* Public declarations */\nEND^\n'
            f'SET TERM ; ^'
        )
        return {'sql': sql, 'terminator': ';'}

    if r_kind in ('sequence', 'generator'):
        if kind_norm == 'select':
            if eng == 'firebird':
                return {
                    'sql': f'SELECT GEN_ID({qual_name}, 0) AS CURRENT_VAL FROM RDB$DATABASE;\n-- Next value: SELECT NEXT VALUE FOR {qual_name} FROM RDB$DATABASE;',
                    'terminator': ';',
                }
            return {'sql': f'SELECT nextval({raw_name!r});', 'terminator': ';'}
        if kind_norm == 'ddl_alter':
            return {'sql': f'ALTER SEQUENCE {qual_name} RESTART WITH 1;', 'terminator': ';'}
        if kind_norm == 'ddl_drop':
            return {'sql': f'DROP SEQUENCE {qual_name};', 'terminator': ';'}
        return {'sql': native_ddl or f'CREATE SEQUENCE {qual_name} START WITH 1 INCREMENT BY 1;', 'terminator': ';'}

    if r_kind in ('domain', 'type'):
        kw = 'DOMAIN' if (r_kind == 'domain' or eng == 'firebird') else 'TYPE'
        if kind_norm == 'ddl_alter':
            return {'sql': f'ALTER {kw} {qual_name} SET DEFAULT NULL;', 'terminator': ';'}
        if kind_norm == 'ddl_drop':
            return {'sql': f'DROP {kw} {qual_name};', 'terminator': ';'}
        return {
            'sql': native_ddl or f'CREATE {kw} {qual_name} AS VARCHAR(120);',
            'terminator': ';',
        }

    # Generic DDL (`ddl_create`, `ddl_recreate`, `ddl_alter`, `ddl_drop`)
    obj_kw_map = {
        'table': 'TABLE',
        'view': 'VIEW',
        'materialized-view': 'MATERIALIZED VIEW',
        'procedure': 'PROCEDURE',
        'function': 'FUNCTION',
        'routine': 'PROCEDURE' if eng == 'firebird' else 'FUNCTION',
        'trigger': 'TRIGGER',
        'index': 'INDEX',
        'exception': 'EXCEPTION',
        'role': 'ROLE',
    }
    obj_kw = obj_kw_map.get(r_kind, r_kind.upper().replace('-', ' '))

    if kind_norm == 'ddl_drop':
        return {'sql': f'DROP {obj_kw} {qual_name};', 'terminator': ';'}

    if kind_norm == 'ddl_alter':
        if r_kind == 'table':
            return {
                'sql': f'ALTER TABLE {qual_name}\n  ADD /* column_name VARCHAR(64) */;',
                'terminator': ';',
            }
        if r_kind == 'trigger' and eng == 'firebird':
            return {'sql': f'ALTER TRIGGER {qual_name} ACTIVE;', 'terminator': ';'}
        if r_kind == 'index' and eng == 'firebird':
            return {'sql': f'SET STATISTICS INDEX {qual_name};', 'terminator': ';'}
        if native_ddl:
            return {'sql': native_ddl, 'terminator': terminator}
        return {'sql': f'ALTER {obj_kw} {qual_name} /* ... */;', 'terminator': ';'}

    if native_ddl:
        return {'sql': native_ddl, 'terminator': terminator}

    if r_kind == 'table':
        cols_ddl = ',\n  '.join(
            f"{_quote_ident(str(c['name']), eng)} {c.get('native_type') or 'VARCHAR(100)'}"
            + (' NOT NULL' if c.get('nullable') is False else '')
            for c in cols_meta
            if c.get('name')
        ) or f'{_quote_ident("ID", eng)} INTEGER NOT NULL PRIMARY KEY'
        create_kw = 'RECREATE TABLE' if (kind_norm == 'ddl_recreate' and eng == 'firebird') else 'CREATE TABLE'
        return {
            'sql': f'{create_kw} {qual_name} (\n  {cols_ddl}\n);',
            'terminator': ';',
        }

    if r_kind in ('procedure', 'function', 'routine') and eng == 'firebird':
        kw = 'FUNCTION' if r_kind == 'function' else 'PROCEDURE'
        ret_clause = 'RETURNS INTEGER' if kw == 'FUNCTION' else 'RETURNS (OUT_VAL INTEGER)'
        body_stmt = 'RETURN 1;' if kw == 'FUNCTION' else 'OUT_VAL = 1;\n  SUSPEND;'
        return {
            'sql': (
                f'SET TERM ^ ;\n'
                f'CREATE OR ALTER {kw} {qual_name}\n'
                f'{ret_clause}\n'
                f'AS\nBEGIN\n  {body_stmt}\nEND^\n'
                f'SET TERM ; ^'
            ),
            'terminator': ';',
        }

    return {'sql': f'CREATE {obj_kw} {qual_name} /* definition */;', 'terminator': ';'}


# ============================================================================
# 5. Pure-Stdlib Multi-Format Exporter (`CSV/TSV`, `XLSX`, `ODS`, `PDF`, `JSON`, `SQL`)
# ============================================================================


def _excel_col_letter(col_idx_one_based: int) -> str:
    result = []
    n = col_idx_one_based
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result.append(chr(65 + rem))
    return ''.join(reversed(result))


def _format_export_scalar(val: Any, null_text: str = '') -> str:
    if val is None:
        return null_text
    if isinstance(val, (dict, list)):
        return json.dumps(val, default=str, ensure_ascii=False)
    if isinstance(val, bool):
        return 'TRUE' if val else 'FALSE'
    return str(val)


def _build_xlsx_bytes(
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    settings: dict[str, Any],
    sql_text: str = '',
) -> bytes:
    sheet_title = re.sub(r'[\[\]:*?/\\]', '_', str(settings.get('sheet_name') or 'Data'))[:31] or 'Data'
    freeze_header = settings.get('freeze_header', True) is not False
    auto_filter = settings.get('auto_filter', True) is not False
    typed_cells = settings.get('typed_cells', True) is not False
    include_meta_sheet = bool(settings.get('include_sql_sheet'))

    col_names = [str(c.get('name') or f'Col_{i + 1}') for i, c in enumerate(columns)]
    last_col_letter = _excel_col_letter(max(1, len(col_names)))
    total_xml_rows = len(rows) + 1

    # Build worksheet XML
    cols_xml_parts = []
    for idx, c in enumerate(columns, start=1):
        w_px = int(c.get('width') or 140)
        w_chars = max(10, min(60, round(w_px / 7.5, 1)))
        cols_xml_parts.append(
            f'<col min="{idx}" max="{idx}" width="{w_chars}" customWidth="1"/>'
        )
    cols_block = f'<cols>{"".join(cols_xml_parts)}</cols>' if cols_xml_parts else ''

    sheet_views = (
        '<sheetViews><sheetView workbookViewId="0">'
        + (
            '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            if freeze_header
            else ''
        )
        + '</sheetView></sheetViews>'
    )

    row_xml_list: list[str] = []
    # Header row (row 1, style s="1" bold)
    hdr_cells = []
    for c_idx, cname in enumerate(col_names, start=1):
        ref = f'{_excel_col_letter(c_idx)}1'
        hdr_cells.append(
            f'<c r="{ref}" t="inlineStr" s="1"><is><t>{xml_escape(cname)}</t></is></c>'
        )
    row_xml_list.append(f'<row r="1">{"".join(hdr_cells)}</row>')

    for r_idx, row in enumerate(rows, start=2):
        vals = row.get('values') if isinstance(row, dict) and 'values' in row else row
        c_list = []
        for c_idx, cname in enumerate(col_names, start=1):
            ref = f'{_excel_col_letter(c_idx)}{r_idx}'
            v = (vals or {}).get(cname) if isinstance(vals, dict) else None
            if v is None:
                continue
            if typed_cells and isinstance(v, bool):
                c_list.append(f'<c r="{ref}" t="b"><v>{1 if v else 0}</v></c>')
            elif (
                typed_cells
                and isinstance(v, (int, float))
                and not isinstance(v, bool)
                and math.isfinite(v)
            ):
                c_list.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                txt = _format_export_scalar(v, '')
                # Strip XML-illegal control chars
                txt = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', txt)
                c_list.append(
                    f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{xml_escape(txt)}</t></is></c>'
                )
        row_xml_list.append(f'<row r="{r_idx}">{"".join(c_list)}</row>')

    af_xml = (
        f'<autoFilter ref="A1:{last_col_letter}{total_xml_rows}"/>'
        if auto_filter and col_names
        else ''
    )
    sheet1_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'{sheet_views}{cols_block}'
        f'<sheetData>{"".join(row_xml_list)}</sheetData>'
        f'{af_xml}'
        '</worksheet>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        sheets_manifest = [
            f'<sheet name="{xml_escape(sheet_title)}" sheetId="1" r:id="rId1"/>'
        ]
        wb_rels = [
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>',
            '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
        ]
        ct_overrides = [
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>',
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
        ]

        zf.writestr('xl/worksheets/sheet1.xml', sheet1_xml)

        if include_meta_sheet:
            meta_lines = [
                ('Generated At', _now_iso()),
                ('Row Count', str(len(rows))),
                ('SQL Query', sql_text or ''),
            ]
            m_rows = []
            for idx, (k, val) in enumerate(meta_lines, start=1):
                clean_v = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(val))
                m_rows.append(
                    f'<row r="{idx}">'
                    f'<c r="A{idx}" t="inlineStr" s="1"><is><t>{xml_escape(k)}</t></is></c>'
                    f'<c r="B{idx}" t="inlineStr"><is><t xml:space="preserve">{xml_escape(clean_v)}</t></is></c>'
                    f'</row>'
                )
            sheet2_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<sheetData>{"".join(m_rows)}</sheetData>'
                '</worksheet>'
            )
            zf.writestr('xl/worksheets/sheet2.xml', sheet2_xml)
            sheets_manifest.append('<sheet name="SQL_Metadata" sheetId="2" r:id="rId2"/>')
            wb_rels.append(
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
            )
            ct_overrides.append(
                '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )

        zf.writestr(
            '[Content_Types].xml',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            + ''.join(ct_overrides)
            + '</Types>',
        )
        zf.writestr(
            '_rels/.rels',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>',
        )
        zf.writestr(
            'xl/workbook.xml',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(sheets_manifest)}</sheets>'
            '</workbook>',
        )
        zf.writestr(
            'xl/_rels/workbook.xml.rels',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + ''.join(wb_rels)
            + '</Relationships>',
        )
        zf.writestr(
            'xl/styles.xml',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2">'
            '<font><sz val="10"/><name val="Calibri"/></font>'
            '<font><b/><sz val="10"/><name val="Calibri"/></font>'
            '</fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            '</cellXfs>'
            '</styleSheet>',
        )
    return buf.getvalue()


def _build_ods_bytes(
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    settings: dict[str, Any],
    sql_text: str = '',
) -> bytes:
    sheet_title = str(settings.get('sheet_name') or 'Data')[:64] or 'Data'
    typed_cells = settings.get('typed_cells', True) is not False
    include_meta_sheet = bool(settings.get('include_sql_sheet'))
    col_names = [str(c.get('name') or f'Col_{i + 1}') for i, c in enumerate(columns)]

    table_rows_xml: list[str] = []
    # Header row
    hdr_cells = [
        f'<table:table-cell office:value-type="string"><text:p>{xml_escape(c)}</text:p></table:table-cell>'
        for c in col_names
    ]
    table_rows_xml.append(f'<table:table-row>{"".join(hdr_cells)}</table:table-row>')

    for row in rows:
        vals = row.get('values') if isinstance(row, dict) and 'values' in row else row
        cells = []
        for cname in col_names:
            v = (vals or {}).get(cname) if isinstance(vals, dict) else None
            if v is None:
                cells.append('<table:table-cell/>')
            elif typed_cells and isinstance(v, bool):
                b_str = 'true' if v else 'false'
                cells.append(
                    f'<table:table-cell office:value-type="boolean" office:boolean-value="{b_str}"><text:p>{b_str.upper()}</text:p></table:table-cell>'
                )
            elif (
                typed_cells
                and isinstance(v, (int, float))
                and not isinstance(v, bool)
                and math.isfinite(v)
            ):
                cells.append(
                    f'<table:table-cell office:value-type="float" office:value="{v}"><text:p>{v}</text:p></table:table-cell>'
                )
            else:
                txt = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', _format_export_scalar(v, ''))
                cells.append(
                    f'<table:table-cell office:value-type="string"><text:p>{xml_escape(txt)}</text:p></table:table-cell>'
                )
        table_rows_xml.append(f'<table:table-row>{"".join(cells)}</table:table-row>')

    meta_table_xml = ''
    if include_meta_sheet:
        clean_sql = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', sql_text or '')
        meta_table_xml = (
            '<table:table table:name="SQL_Metadata">'
            f'<table:table-row><table:table-cell office:value-type="string"><text:p>Generated At</text:p></table:table-cell>'
            f'<table:table-cell office:value-type="string"><text:p>{xml_escape(_now_iso())}</text:p></table:table-cell></table:table-row>'
            f'<table:table-row><table:table-cell office:value-type="string"><text:p>SQL Query</text:p></table:table-cell>'
            f'<table:table-cell office:value-type="string"><text:p>{xml_escape(clean_sql)}</text:p></table:table-cell></table:table-row>'
            '</table:table>'
        )

    content_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
        'office:version="1.2">'
        '<office:body><office:spreadsheet>'
        f'<table:table table:name="{xml_escape(sheet_title)}">'
        + ''.join(table_rows_xml)
        + '</table:table>'
        + meta_table_xml
        + '</office:spreadsheet></office:body></office:document-content>'
    )

    mimetype_bytes = b'application/vnd.oasis.opendocument.spreadsheet'
    manifest_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">'
        '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>'
        '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
        '</manifest:manifest>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        mi = zipfile.ZipInfo('mimetype')
        mi.compress_type = zipfile.ZIP_STORED
        zf.writestr(mi, mimetype_bytes)
        zf.writestr('content.xml', content_xml, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr('META-INF/manifest.xml', manifest_xml, compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def _pdf_escape(text: str) -> str:
    safe = str(text or '').encode('latin-1', errors='replace').decode('latin-1')
    return safe.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _build_pdf_bytes(
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    settings: dict[str, Any],
    sql_text: str = '',
) -> bytes:
    """Generate a clean multi-page vector PDF 1.4 table report in pure Python stdlib."""
    page_sizes = {
        'letter': (612, 792),
        'legal': (612, 1008),
        'a4': (595, 842),
        'a3': (842, 1191),
    }
    p_key = str(settings.get('page_size') or 'letter').lower()
    base_w, base_h = page_sizes.get(p_key, (612, 792))
    orientation = str(settings.get('orientation') or 'landscape').lower()
    page_w, page_h = (base_h, base_w) if orientation == 'landscape' else (base_w, base_h)

    title = str(settings.get('title') or 'ScratchRobin Query Report')
    subtitle = str(settings.get('subtitle') or '')
    include_header_footer = (
        settings.get('include_header_footer')
        if 'include_header_footer' in settings
        else settings.get('show_footer', True)
    ) is not False
    include_sql_appendix = bool(settings.get('include_sql_appendix'))
    raw_null_pdf = settings.get('null_text') if settings.get('null_text') is not None else settings.get('null_string')
    null_text = str(raw_null_pdf if raw_null_pdf is not None else '<null>')
    font_size = max(6, min(12, int(round(float(settings.get('font_size') or 8)))))

    margin = 36
    usable_w = page_w - 2 * margin
    col_names = [str(c.get('name') or f'Col_{i + 1}') for i, c in enumerate(columns)] or ['Result']
    col_count = len(col_names)
    col_w = usable_w / max(1, col_count)
    max_chars_per_col = max(4, int((col_w - 8) / (font_size * 0.52)))
    row_h = font_size + 7

    pages_streams: list[str] = []
    rows_per_page = max(5, int((page_h - 140) / row_h))
    total_data_pages = max(1, math.ceil(max(1, len(rows)) / rows_per_page))
    total_pages = total_data_pages + (1 if include_sql_appendix and sql_text.strip() else 0)
    ts_label = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    for p_idx in range(total_data_pages):
        cmds: list[str] = []
        y = page_h - margin

        # Title & header
        if p_idx == 0:
            cmds.append(f'BT /F2 13 Tf {margin} {y - 12} Td ({_pdf_escape(title)}) Tj ET')
            y -= 20
            if subtitle:
                cmds.append(f'BT /F1 9 Tf {margin} {y - 8} Td ({_pdf_escape(subtitle)}) Tj ET')
                y -= 14
        elif include_header_footer:
            cmds.append(f'BT /F2 9 Tf {margin} {y - 8} Td ({_pdf_escape(title)}) Tj ET')
            y -= 16

        y -= 6
        # Column Header Band
        cmds.append('0.92 0.94 0.97 rg')
        cmds.append(f'{margin} {y - row_h} {usable_w:.1f} {row_h} re f')
        cmds.append('0 0 0 rg')
        for c_i, cname in enumerate(col_names):
            cx = margin + c_i * col_w + 4
            clipped = cname[:max_chars_per_col]
            cmds.append(
                f'BT /F2 {font_size} Tf {cx:.1f} {y - row_h + 4:.1f} Td ({_pdf_escape(clipped)}) Tj ET'
            )
        cmds.append('0.72 0.76 0.82 RG 0.6 w')
        cmds.append(f'{margin} {y - row_h} m {margin + usable_w:.1f} {y - row_h} l S')
        y -= row_h

        # Data rows
        chunk = rows[p_idx * rows_per_page:(p_idx + 1) * rows_per_page]
        for r_i, row in enumerate(chunk):
            if r_i % 2 == 1:
                cmds.append('0.97 0.98 0.99 rg')
                cmds.append(f'{margin} {y - row_h} {usable_w:.1f} {row_h} re f')
                cmds.append('0 0 0 rg')
            vals = row.get('values') if isinstance(row, dict) and 'values' in row else row
            for c_i, cname in enumerate(col_names):
                v = (vals or {}).get(cname) if isinstance(vals, dict) else None
                txt = _format_export_scalar(v, null_text).replace('\n', ' ')
                if len(txt) > max_chars_per_col:
                    txt = txt[:max(1, max_chars_per_col - 1)] + '~'
                cx = margin + c_i * col_w + 4
                cmds.append(
                    f'BT /F1 {font_size} Tf {cx:.1f} {y - row_h + 4:.1f} Td ({_pdf_escape(txt)}) Tj ET'
                )
            y -= row_h

        if include_header_footer:
            footer_left = f'Generated {ts_label}  |  {len(rows)} row(s)'
            footer_right = f'Page {p_idx + 1} of {total_pages}'
            cmds.append(f'BT /F1 8 Tf {margin} 18 Td ({_pdf_escape(footer_left)}) Tj ET')
            cmds.append(
                f'BT /F1 8 Tf {page_w - margin - 70:.1f} 18 Td ({_pdf_escape(footer_right)}) Tj ET'
            )
        pages_streams.append('\n'.join(cmds))

    if include_sql_appendix and sql_text.strip():
        cmds = [
            f'BT /F2 12 Tf {margin} {page_h - margin - 12} Td (SQL Query Appendix) Tj ET'
        ]
        ay = page_h - margin - 34
        for line in sql_text.splitlines()[:52]:
            cmds.append(f'BT /F1 8 Tf {margin} {ay} Td ({_pdf_escape(line[:110])}) Tj ET')
            ay -= 11
            if ay < 40:
                break
        if include_header_footer:
            cmds.append(
                f'BT /F1 8 Tf {page_w - margin - 70:.1f} 18 Td (Page {total_pages} of {total_pages}) Tj ET'
            )
        pages_streams.append('\n'.join(cmds))

    # Assemble PDF 1.4 object table
    # Obj 1: Catalog, Obj 2: Pages, Obj 3: Font Helvetica (/F1), Obj 4: Font Helvetica-Bold (/F2)
    objects: list[bytes] = [b'', b'', b'', b'']
    objects[2] = b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>'
    objects[3] = b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>'

    page_obj_nums: list[int] = []
    for stream_str in pages_streams:
        stream_bytes = stream_str.encode('latin-1', errors='replace')
        content_obj_num = len(objects) + 1
        objects.append(
            f'<< /Length {len(stream_bytes)} >>\nstream\n'.encode('ascii')
            + stream_bytes
            + b'\nendstream'
        )
        page_obj_num = len(objects) + 1
        page_obj_nums.append(page_obj_num)
        objects.append(
            (
                f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w} {page_h}] '
                f'/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> '
                f'/Contents {content_obj_num} 0 R >>'
            ).encode('ascii')
        )

    kids_str = ' '.join(f'{num} 0 R' for num in page_obj_nums)
    objects[0] = b'<< /Type /Catalog /Pages 2 0 R >>'
    objects[1] = f'<< /Type /Pages /Kids [{kids_str}] /Count {len(page_obj_nums)} >>'.encode('ascii')

    out = io.BytesIO()
    out.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets: list[int] = [0]
    for idx, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f'{idx} 0 obj\n'.encode('ascii'))
        out.write(body)
        out.write(b'\nendobj\n')

    xref_pos = out.tell()
    out.write(f'xref\n0 {len(objects) + 1}\n'.encode('ascii'))
    out.write(b'0000000000 65535 f \n')
    for off in offsets[1:]:
        out.write(f'{off:010d} 00000 n \n'.encode('ascii'))
    out.write(
        (
            f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n'
            f'startxref\n{xref_pos}\n%%EOF\n'
        ).encode('ascii')
    )
    return out.getvalue()


def export_tabular_dataset(
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    fmt: str,
    settings: dict[str, Any] | None = None,
    sql_text: str = '',
    base_filename: str = 'query_export',
) -> dict[str, Any]:
    """Export tabular rows into CSV, TSV, XLSX, ODS, PDF, JSON, or SQL with format settings."""
    cfg = dict(settings or {})
    fmt_norm = str(fmt or 'csv').lower().strip()
    safe_stem = re.sub(r'[^A-Za-z0-9_.-]+', '_', str(base_filename or 'export')).strip('_') or 'export'

    if fmt_norm in ('csv', 'tsv'):
        default_delim = '\t' if fmt_norm == 'tsv' else ','
        delim_raw = cfg.get('delimiter', default_delim)
        delimiter = '\t' if delim_raw in ('\\t', 'tab', '\t') else (str(delim_raw or ',')[0])
        quotechar = (str(cfg.get('quote_char') or cfg.get('quotechar') or '"')[0])
        quoting_map = {
            'minimal': csv.QUOTE_MINIMAL,
            'all': csv.QUOTE_ALL,
            'nonnumeric': csv.QUOTE_NONNUMERIC,
            'none': csv.QUOTE_NONE,
        }
        quoting = quoting_map.get(str(cfg.get('quoting') or 'minimal').lower(), csv.QUOTE_MINIMAL)
        include_header = cfg.get('include_header', True) is not False
        raw_null = cfg.get('null_text') if cfg.get('null_text') is not None else cfg.get('null_string')
        null_text = str(raw_null if raw_null is not None else '')
        raw_le = str(cfg.get('line_ending') or cfg.get('lineterminator') or 'lf')
        line_ending = '\r\n' if raw_le.lower() == 'crlf' or raw_le == '\r\n' else '\n'
        encoding = str(cfg.get('encoding') or 'utf-8').lower()
        if encoding not in ('utf-8', 'utf-8-sig', 'iso-8859-1', 'cp1252'):
            encoding = 'utf-8'

        col_names = [str(c.get('name') or '') for c in columns]
        sio = io.StringIO()
        writer = csv.writer(
            sio,
            delimiter=delimiter,
            quotechar=quotechar,
            quoting=quoting,
            escapechar='\\' if quoting == csv.QUOTE_NONE else None,
            lineterminator=line_ending,
        )
        if include_header:
            writer.writerow(col_names)
        for row in rows:
            vals = row.get('values') if isinstance(row, dict) and 'values' in row else row
            writer.writerow([
                _format_export_scalar((vals or {}).get(c) if isinstance(vals, dict) else None, null_text)
                for c in col_names
            ])
        raw_bytes = sio.getvalue().encode(encoding, errors='replace')
        ext = 'tsv' if fmt_norm == 'tsv' or delimiter == '\t' else 'csv'
        mime = 'text/tab-separated-values' if ext == 'tsv' else 'text/csv'
        return {
            'format': ext,
            'filename': f'{safe_stem}.{ext}',
            'mime_type': f'{mime};charset={encoding}',
            'byte_length': len(raw_bytes),
            'content_base64': base64.b64encode(raw_bytes).decode('ascii'),
        }

    if fmt_norm == 'xlsx':
        raw_bytes = _build_xlsx_bytes(columns, rows, cfg, sql_text=sql_text)
        return {
            'format': 'xlsx',
            'filename': f'{safe_stem}.xlsx',
            'mime_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'byte_length': len(raw_bytes),
            'content_base64': base64.b64encode(raw_bytes).decode('ascii'),
        }

    if fmt_norm == 'ods':
        raw_bytes = _build_ods_bytes(columns, rows, cfg, sql_text=sql_text)
        return {
            'format': 'ods',
            'filename': f'{safe_stem}.ods',
            'mime_type': 'application/vnd.oasis.opendocument.spreadsheet',
            'byte_length': len(raw_bytes),
            'content_base64': base64.b64encode(raw_bytes).decode('ascii'),
        }

    if fmt_norm == 'pdf':
        raw_bytes = _build_pdf_bytes(columns, rows, cfg, sql_text=sql_text)
        return {
            'format': 'pdf',
            'filename': f'{safe_stem}.pdf',
            'mime_type': 'application/pdf',
            'byte_length': len(raw_bytes),
            'content_base64': base64.b64encode(raw_bytes).decode('ascii'),
        }

    if fmt_norm == 'json':
        records = [
            (r.get('values') if isinstance(r, dict) and 'values' in r else r)
            for r in rows
        ]
        indent = 2 if cfg.get('pretty', True) is not False else None
        raw_bytes = json.dumps(records, indent=indent, default=str, ensure_ascii=False).encode('utf-8')
        return {
            'format': 'json',
            'filename': f'{safe_stem}.json',
            'mime_type': 'application/json;charset=utf-8',
            'byte_length': len(raw_bytes),
            'content_base64': base64.b64encode(raw_bytes).decode('ascii'),
        }

    raise ValueError(f'Unsupported export format: {fmt}')


# ============================================================================
# 6. Visual Query Builder <-> DDN Canvas Scene & SQL Synchronizer
# ============================================================================

_SIMPLE_SELECT_TABLE_RE = re.compile(
    r'^\s*SELECT\b[\s\S]+?\bFROM\s+([A-Za-z0-9_."`]+)(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?(?:\s*;?\s*)$',
    re.IGNORECASE,
)


def build_visual_query_ddn_scene(
    visual_model: dict[str, Any],
    catalog_tables: dict[str, list[dict[str, Any]]],
    engine_id: str = 'relational',
) -> tuple[dict[str, Any], str, list[str]]:
    """Build BOTH:
    1. A `RobinTiledCanvas`-compatible DDN diagram scene (`views`, `nodes`, `edges`, `bounds`)
       for `100% Area 3e` visual rendering, and
    2. Synchronized dialect SQL + fan-out warnings!
    """
    eng = str(engine_id or 'relational').split('-')[0].lower()
    tables: list[dict[str, Any]] = list(visual_model.get('tables') or [])
    joins: list[dict[str, Any]] = list(visual_model.get('joins') or [])
    projections: list[dict[str, Any]] = list(visual_model.get('projections') or [])
    filters: list[dict[str, Any]] = list(visual_model.get('filters') or [])
    group_by: list[str] = list(visual_model.get('group_by') or [])
    order_by: list[dict[str, Any]] = list(visual_model.get('order_by') or [])
    limit_val = visual_model.get('limit')
    distinct = bool(visual_model.get('distinct'))

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    fanout_warnings: list[str] = []

    for idx, tbl in enumerate(tables):
        t_id = str(tbl.get('id') or f'tbl_{idx + 1}')
        t_name = str(tbl.get('name') or t_id)
        t_alias = str(tbl.get('alias') or '')
        cols = catalog_tables.get(t_name) or tbl.get('columns') or []
        col_entries = []
        for c in cols:
            cname = str(c.get('name') if isinstance(c, dict) else c)
            is_proj = any(
                (p.get('table') in (t_id, t_name, t_alias) and p.get('column') == cname)
                for p in projections
            ) or not projections
            col_entries.append({
                'name': f"{'☑' if is_proj else '☐'} {cname}",
                'type': str(c.get('native_type') or '') if isinstance(c, dict) else '',
                'pk': bool(c.get('key')) if isinstance(c, dict) else False,
            })
        x = float(tbl.get('x') if tbl.get('x') is not None else 80 + (idx % 3) * 320)
        y = float(tbl.get('y') if tbl.get('y') is not None else 70 + (idx // 3) * 260)
        h = max(110, 46 + len(col_entries[:14]) * 20)
        nodes.append({
            'id': t_id,
            'kind': 'entity',
            'label': f'{t_name} ({t_alias})' if t_alias else t_name,
            'subtitle': str(tbl.get('resource_kind') or 'TABLE').upper(),
            'x': x,
            'y': y,
            'width': 248,
            'height': h,
            'columns': col_entries[:14],
        })

    node_by_id = {n['id']: n for n in nodes}
    one_to_many_count = 0
    for j_idx, jn in enumerate(joins):
        l_tbl = str(jn.get('left_table') or '')
        r_tbl = str(jn.get('right_table') or '')
        l_col = str(jn.get('left_column') or 'ID')
        r_col = str(jn.get('right_column') or 'ID')
        j_type = str(jn.get('join_type') or 'INNER').upper()
        cardinality = str(jn.get('cardinality') or '1:N')
        if cardinality in ('1:N', 'N:M'):
            one_to_many_count += 1
        src = node_by_id.get(l_tbl)
        dst = node_by_id.get(r_tbl)
        sx = (src['x'] + src['width']) if src else 200
        sy = (src['y'] + 42) if src else 120
        dx = dst['x'] if dst else 420
        dy = (dst['y'] + 42) if dst else 120
        mid_x = (sx + dx) / 2.0
        edges.append({
            'id': str(jn.get('id') or f'join_{j_idx + 1}'),
            'source': l_tbl,
            'target': r_tbl,
            'label': f'{j_type} JOIN ({l_col} = {r_col})',
            'cardinality': cardinality,
            'points': [[sx, sy], [mid_x, sy], [mid_x, dy], [dx, dy]],
        })

    if one_to_many_count >= 2:
        fanout_warnings.append(
            'Multiple 1:N / N:M joins detected — aggregate measures may fan out without pre-aggregation.'
        )

    max_x = max((n['x'] + n['width'] for n in nodes), default=800) + 100
    max_y = max((n['y'] + n['height'] for n in nodes), default=500) + 100
    scene = {
        'views': [{'id': 'query_canvas', 'name': 'Visual Query Canvas', 'profile': 'erd.physical@1'}],
        'activeViewId': 'query_canvas',
        'bounds': {'x': 0, 'y': 0, 'width': max_x, 'height': max_y},
        'tileSize': 2048,
        'nodes': nodes,
        'edges': edges,
        'tiles': {'0:0': {'tx': 0, 'ty': 0, 'nodes': nodes, 'edges': edges}},
    }

    # Build Dialect SQL from structured visual model
    if not tables:
        return scene, '', fanout_warnings

    alias_by_id: dict[str, str] = {}
    table_by_id: dict[str, dict[str, Any]] = {}
    for tbl in tables:
        tid = str(tbl.get('id') or tbl.get('name'))
        tname = str(tbl.get('name') or tid)
        talias = str(tbl.get('alias') or '').strip()
        qual = _quote_ident(talias, eng) if talias else _quote_ident(tname, eng)
        for k in (tid, talias, tname):
            if k:
                alias_by_id[k] = qual
                table_by_id[k] = tbl

    if projections:
        proj_parts = []
        for p in projections:
            expr = str(p.get('expression') or p.get('expr') or '').strip()
            agg = str(p.get('aggregate') or '').strip().upper()
            if not expr:
                t_ref = alias_by_id.get(str(p.get('table') or ''), '')
                c_ref = _quote_ident(str(p.get('column') or '*'), eng) if p.get('column') != '*' else '*'
                expr = f'{t_ref}.{c_ref}' if t_ref else c_ref
            if agg in ('COUNT', 'SUM', 'AVG', 'MIN', 'MAX') and not expr.upper().startswith(f'{agg}('):
                expr = f'{agg}({expr})'
            alias_out = str(p.get('alias') or '').strip()
            proj_parts.append(
                f'  {expr} AS {_quote_ident(alias_out, eng)}' if alias_out else f'  {expr}'
            )
        select_head = ('SELECT DISTINCT\n' if distinct else 'SELECT\n') + ',\n'.join(proj_parts)
    else:
        select_head = 'SELECT DISTINCT\n  *' if distinct else 'SELECT\n  *'

    first_t = tables[0]
    first_sql = _quote_ident(str(first_t.get('name')), eng)
    if first_t.get('alias'):
        first_sql += f" AS {_quote_ident(str(first_t['alias']), eng)}"
    from_lines = [f'FROM {first_sql}']

    joined_ids = {
        k
        for k in (
            str(first_t.get('id') or ''),
            str(first_t.get('alias') or ''),
            str(first_t.get('name') or ''),
        )
        if k
    }

    for jn in joins:
        r_id = str(jn.get('right_table') or '')
        l_id = str(jn.get('left_table') or '')
        r_tbl = table_by_id.get(r_id)
        if not r_tbl:
            continue
        for k in (
            r_id,
            str(r_tbl.get('id') or ''),
            str(r_tbl.get('alias') or ''),
            str(r_tbl.get('name') or ''),
        ):
            if k:
                joined_ids.add(k)
        j_type = str(jn.get('join_type') or 'INNER').upper()
        r_sql = _quote_ident(str(r_tbl.get('name')), eng)
        if r_tbl.get('alias'):
            r_sql += f" AS {_quote_ident(str(r_tbl['alias']), eng)}"
        l_qual = alias_by_id.get(l_id, _quote_ident(l_id, eng))
        r_qual = alias_by_id.get(r_id, _quote_ident(str(r_tbl.get('name')), eng))
        on_expr = str(jn.get('custom_on') or '').strip() or (
            f"{l_qual}.{_quote_ident(str(jn.get('left_column') or 'ID'), eng)} = "
            f"{r_qual}.{_quote_ident(str(jn.get('right_column') or 'ID'), eng)}"
        )
        from_lines.append(f'{j_type} JOIN {r_sql} ON {on_expr}')

    # Any additional unjoined tables become CROSS JOIN
    for tbl in tables[1:]:
        tid = str(tbl.get('id') or tbl.get('name'))
        if tid not in joined_ids:
            t_sql = _quote_ident(str(tbl.get('name')), eng)
            if tbl.get('alias'):
                t_sql += f" AS {_quote_ident(str(tbl['alias']), eng)}"
            from_lines.append(f'CROSS JOIN {t_sql}')

    clauses = [select_head, '\n'.join(from_lines)]
    where_items = [
        str(f.get('expression') or '').strip()
        for f in filters
        if isinstance(f, dict) and f.get('clause', 'where') == 'where' and str(f.get('expression') or '').strip()
    ] + [str(w).strip() for w in (visual_model.get('where') or []) if str(w).strip()]
    if where_items:
        clauses.append('WHERE ' + '\n  AND '.join(where_items))
    if group_by:
        clauses.append('GROUP BY ' + ', '.join(str(g) for g in group_by if str(g).strip()))
    having_items = [
        str(f.get('expression') or '').strip()
        for f in filters
        if isinstance(f, dict) and f.get('clause') == 'having' and str(f.get('expression') or '').strip()
    ] + [str(h).strip() for h in (visual_model.get('having') or []) if str(h).strip()]
    if having_items:
        clauses.append('HAVING ' + '\n   AND '.join(having_items))
    if order_by:
        ord_parts = []
        for o in order_by:
            if isinstance(o, str) and o.strip():
                ord_parts.append(o.strip())
            elif isinstance(o, dict) and (o.get('column') or o.get('expr')):
                col_expr = o.get('column') or o.get('expr')
                direction = 'DESC' if str(o.get('direction') or o.get('dir') or 'asc').lower() == 'desc' else 'ASC'
                ord_parts.append(f'{col_expr} {direction}')
        if ord_parts:
            clauses.append('ORDER BY ' + ', '.join(ord_parts))
    if limit_val and int(limit_val) > 0:
        if eng == 'firebird':
            clauses.append(f'FETCH FIRST {int(limit_val)} ROWS ONLY')
        else:
            clauses.append(f'LIMIT {int(limit_val)}')

    return scene, '\n'.join(clauses) + ';', fanout_warnings


def parse_sql_to_visual_model(sql: str) -> tuple[dict[str, Any] | None, str]:
    """Attempt clean-room SQL -> Visual Model parsing with fidelity reporting (`exact`, `lossy`, `none`)."""
    raw = str(sql or '').strip().rstrip(';').strip()
    if not raw:
        return {
            'tables': [],
            'joins': [],
            'projections': [],
            'filters': [],
            'group_by': [],
            'order_by': [],
            'limit': None,
            'distinct': False,
        }, 'exact'

    if not re.match(r'^\s*(?:WITH\b|SELECT\b)', raw, re.IGNORECASE):
        return None, 'none'

    has_cte_or_union = bool(re.search(r'\b(WITH\s+\w+|UNION\b|INTERSECT\b|EXCEPT\b)', raw, re.IGNORECASE))
    from_match = re.search(
        r'\bFROM\s+([A-Za-z0-9_."`]+)(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?',
        raw,
        re.IGNORECASE,
    )
    if not from_match:
        return None, 'none'

    def _strip_q(ident: str) -> str:
        return ident.split('.')[-1].strip('"` ')

    base_name = _strip_q(from_match.group(1))
    base_alias = from_match.group(2) or ''
    if base_alias.upper() in ('WHERE', 'INNER', 'LEFT', 'RIGHT', 'FULL', 'CROSS', 'JOIN', 'GROUP', 'ORDER', 'LIMIT', 'FETCH'):
        base_alias = ''

    tables = [{
        'id': base_alias or base_name,
        'name': base_name,
        'alias': base_alias,
        'x': 90,
        'y': 80,
    }]
    joins = []
    for idx, jm in enumerate(
        re.finditer(
            r'\b(INNER|LEFT(?:\s+OUTER)?|RIGHT(?:\s+OUTER)?|FULL(?:\s+OUTER)?|CROSS)?\s*JOIN\s+([A-Za-z0-9_."`]+)(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?(?:\s+ON\s+([^\n]+?))?(?=\b(?:INNER|LEFT|RIGHT|FULL|CROSS|JOIN|WHERE|GROUP|HAVING|ORDER|LIMIT|FETCH)\b|$)',
            raw,
            re.IGNORECASE,
        ),
        start=1,
    ):
        jtype = (jm.group(1) or 'INNER').upper()
        rname = _strip_q(jm.group(2))
        ralias = jm.group(3) or ''
        if ralias.upper() in ('ON', 'WHERE', 'GROUP', 'ORDER', 'INNER', 'LEFT', 'RIGHT', 'JOIN'):
            ralias = ''
        rid = ralias or rname
        tables.append({
            'id': rid,
            'name': rname,
            'alias': ralias,
            'x': 90 + (idx % 3) * 320,
            'y': 80 + (idx // 3) * 250,
        })
        on_clause = (jm.group(4) or '').strip()
        eq_m = re.match(
            r'([A-Za-z0-9_."`]+)\.([A-Za-z0-9_."`]+)\s*=\s*([A-Za-z0-9_."`]+)\.([A-Za-z0-9_."`]+)',
            on_clause,
        )
        if eq_m:
            l_ref = _strip_q(eq_m.group(1))
            l_col = _strip_q(eq_m.group(2))
            r_ref = _strip_q(eq_m.group(3))
            r_col = _strip_q(eq_m.group(4))
            if r_ref == rid:
                joins.append({
                    'id': f'join_{idx}',
                    'join_type': jtype,
                    'left_table': l_ref,
                    'left_column': l_col,
                    'right_table': rid,
                    'right_column': r_col,
                    'cardinality': '1:N',
                })
            else:
                joins.append({
                    'id': f'join_{idx}',
                    'join_type': jtype,
                    'left_table': r_ref,
                    'left_column': r_col,
                    'right_table': l_ref,
                    'right_column': l_col,
                    'cardinality': '1:N',
                })
        else:
            joins.append({
                'id': f'join_{idx}',
                'join_type': jtype,
                'left_table': tables[0]['id'],
                'left_column': 'ID',
                'right_table': rid,
                'right_column': 'ID',
                'custom_on': on_clause,
                'cardinality': '1:N',
            })

    fidelity = 'lossy' if has_cte_or_union else 'exact'
    return {
        'tables': tables,
        'joins': joins,
        'projections': [],
        'filters': [],
        'group_by': [],
        'order_by': [],
        'limit': None,
        'distinct': bool(re.match(r'^\s*SELECT\s+DISTINCT\b', raw, re.IGNORECASE)),
    }, fidelity


# ============================================================================
# 7. Host Result Set & SqlSurfaceHostService
# ============================================================================


@dataclass
class SqlResultSetBuffer:
    result_index: int
    title: str
    statement_sql: str
    columns: list[dict[str, Any]] = field(default_factory=list)
    field_catalog: list[dict[str, Any]] = field(default_factory=list)
    raw_rows: list[dict[str, Any]] = field(default_factory=list)
    view_indices: list[int] = field(default_factory=list)
    complete_in_buffer: bool = True
    retrieval_limited: bool = False
    editable: bool = False
    identity_policy: str = 'read-only-query'
    row_operations: list[str] = field(default_factory=list)
    target_resource: dict[str, Any] | None = None
    insert_identity_token: str | None = None
    sorts: list[dict[str, Any]] = field(default_factory=list)
    filters: list[dict[str, Any]] = field(default_factory=list)
    sort_mode: str = 'auto'
    sort_execution: str = 'local'
    staged_mutations: collections.OrderedDict[str, StagedRowMutation] = field(
        default_factory=collections.OrderedDict
    )
    execution_ms: float = 0.0
    plan_text: str = ''
    plan_nodes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SqlEditorSurfaceState:
    surface_id: str
    user_id: int
    server_id: int
    database_target_id: str | None
    language_profile: str
    engine_id: str
    parameter_shape: str = 'array'
    session_id: str | None = None
    autocommit: bool = False
    page_size: int = 200
    max_rows: int = 1000
    terminator: str = ';'
    sql_source: str = ''
    bound_parameters: dict[str, Any] = field(default_factory=dict)
    tx_dirty_since_boundary: bool = False
    transaction: dict[str, Any] | None = None
    result_sets: list[SqlResultSetBuffer] = field(default_factory=list)
    active_result_index: int = 0
    visual_model: dict[str, Any] = field(default_factory=lambda: {
        'tables': [],
        'joins': [],
        'projections': [],
        'filters': [],
        'group_by': [],
        'order_by': [],
        'limit': None,
        'distinct': False,
    })
    visual_fidelity: str = 'exact'
    catalog_tables_cache: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    query_history: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=lambda: {
        'prepare_ms': 0.0,
        'execute_ms': 0.0,
        'fetch_ms': 0.0,
        'host_sort_filter_ms': 0.0,
        'total_ms': 0.0,
    })
    lock: threading.RLock = field(default_factory=threading.RLock)


class SqlSurfaceHostService:
    """Host coordinator for Surface 2 (`SQL Editor & Visual Query Builder`)."""

    def __init__(
        self,
        snippets_store: SqlSnippetsStore | None = None,
        quick_query_store: QuickQueryStore | None = None,
        layout_store: SurfaceLayoutStore | None = None,
    ):
        self._surfaces: collections.OrderedDict[str, SqlEditorSurfaceState] = (
            collections.OrderedDict()
        )
        self._lock = threading.RLock()
        self.snippets_store = snippets_store or SqlSnippetsStore()
        self.quick_query_store = quick_query_store or QuickQueryStore()
        self.layout_store = layout_store or SurfaceLayoutStore()

    def _log(
        self,
        surface: SqlEditorSurfaceState,
        severity: str,
        operation: str,
        message: str,
        *,
        elapsed_ms: float | None = None,
        sqlstate: str = '',
        native_code: str = '',
        line: int | None = None,
        column: int | None = None,
        row_index: int | None = None,
        column_name: str = '',
    ) -> None:
        entry = {
            'id': f'smsg-{len(surface.messages) + 1}-{int(time.time() * 1000)}',
            'timestamp': _now_iso(),
            'severity': severity,
            'operation': operation,
            'elapsed_ms': round(elapsed_ms, 2) if elapsed_ms is not None else None,
            'message': message,
            'sqlstate': sqlstate,
            'native_code': native_code,
            'line': line,
            'column': column,
            'row_index': row_index,
            'column_name': column_name,
        }
        surface.messages.append(entry)
        if len(surface.messages) > 500:
            surface.messages = surface.messages[-500:]

    def _get_or_create_surface(
        self, server: Any, request: dict[str, Any]
    ) -> SqlEditorSurfaceState:
        user_id = int(getattr(server, 'user_id', 1) or 1)
        server_id = int(getattr(server, 'id', 0) or 0)
        surface_id = str(request.get('surface_id') or '').strip() or f'sqls-{uuid.uuid4()}'

        with self._lock:
            existing = self._surfaces.get(surface_id)
            if existing is not None and existing.user_id == user_id:
                if request.get('database_target_id') and not existing.database_target_id:
                    existing.database_target_id = request.get('database_target_id')
                if request.get('language_profile') and not existing.language_profile:
                    existing.language_profile = str(request['language_profile'])
                if request.get('engine_id') and existing.engine_id == 'relational':
                    existing.engine_id = str(request['engine_id'])
                self._surfaces.move_to_end(surface_id)
                return existing

            lang = str(request.get('language_profile') or '')
            eng = str(
                request.get('engine_id') or (lang.split('-')[0] if lang else 'relational')
            )
            state = SqlEditorSurfaceState(
                surface_id=surface_id,
                user_id=user_id,
                server_id=server_id,
                database_target_id=request.get('database_target_id') or None,
                language_profile=lang,
                engine_id=eng,
                parameter_shape=str(request.get('parameter_shape') or 'array'),
            )
            self._surfaces[surface_id] = state
            while len(self._surfaces) > 48:
                self._surfaces.popitem(last=False)
            return state

    def _ensure_session(
        self,
        workspace_service: Any,
        server: Any,
        surface: SqlEditorSurfaceState,
    ) -> str | None:
        if surface.session_id:
            return surface.session_id
        if not surface.language_profile:
            return None
        t0 = time.perf_counter()
        opened = workspace_service.open_session(
            server,
            surface.language_profile,
            database_target_id=surface.database_target_id,
        )
        surface.session_id = opened.get('session_id')
        dt_ms = (time.perf_counter() - t0) * 1000.0
        surface.timings_ms['prepare_ms'] = round(dt_ms, 2)
        self._log(
            surface,
            'info',
            'Session',
            f'Dedicated SQL session {surface.session_id} opened on host.',
            elapsed_ms=dt_ms,
        )
        return surface.session_id

    @staticmethod
    def _recompute_rs_view(rs: SqlResultSetBuffer) -> dict[str, float]:
        t0 = time.perf_counter()
        indices = list(range(len(rs.raw_rows)))
        if rs.filters:
            indices = [
                i for i in indices
                if all(
                    _row_matches_filter(rs.raw_rows[i].get('values') or {}, flt)
                    for flt in rs.filters
                )
            ]
        if rs.sorts:
            for srt in reversed(rs.sorts):
                col = str(srt.get('column') or '')
                desc = str(srt.get('direction') or srt.get('dir') or '').lower() == 'desc'
                indices.sort(
                    key=lambda idx: _comparable_sort_key(
                        (rs.raw_rows[idx].get('values') or {}).get(col)
                    ),
                    reverse=desc,
                )
        rs.view_indices = indices
        return {'host_sort_filter_ms': round((time.perf_counter() - t0) * 1000.0, 2)}

    @staticmethod
    def _build_field_catalog_from_columns(
        columns: list[dict[str, Any]], editable: bool
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for idx, col in enumerate(columns, start=1):
            cname = str(col.get('name') or f'COL_{idx}')
            client_type, default_align, is_complex = _infer_client_type(col)
            col['client_type'] = client_type
            col['default_alignment'] = default_align
            col['is_complex'] = is_complex
            out.append({
                'ordinal': idx,
                'name': cname,
                'key_role': 'PK' if col.get('key') else '',
                'nullable': bool(col.get('nullable', True)),
                'default_expression': str(col.get('default_value') or ''),
                'computed_expression': '',
                'native_type': str(col.get('native_type') or col.get('type_name') or 'TEXT'),
                'domain_type': str(col.get('domain_name') or '—'),
                'precision_scale_length': '—',
                'charset': str(col.get('charset') or '—'),
                'collation': str(col.get('collation') or '—'),
                'client_type': client_type,
                'default_alignment': default_align,
                'editable': bool(editable and col.get('editable', not col.get('key'))),
                'insertable': bool(editable and col.get('insertable', True)),
                'is_complex': is_complex,
                'comment': str(col.get('comment') or ''),
            })
        return out

    def _try_resolve_live_editable_rows(
        self,
        workspace_service: Any,
        server: Any,
        surface: SqlEditorSurfaceState,
        stmt_sql: str,
        catalog_resources: list[dict[str, Any]],
    ) -> SqlResultSetBuffer | None:
        """When a simple `SELECT * FROM <table>` matches a single updatable table/view
        and has no WHERE/JOIN/GROUP BY, load via `read_visual_admin_rows` so the query
        result gets native row `identity_token`s and full Surface 1 live editing!
        """
        m = _SIMPLE_SELECT_TABLE_RE.match(stmt_sql)
        if not m:
            return None
        # Must not contain JOIN / WHERE / GROUP BY / HAVING / UNION
        if re.search(
            r'\b(JOIN|WHERE|GROUP\s+BY|HAVING|UNION|INTERSECT|EXCEPT)\b',
            stmt_sql,
            re.IGNORECASE,
        ):
            return None
        # Only `SELECT *` so column projection matches native table row identity
        if not re.match(r'^\s*SELECT\s+\*\s+FROM\b', stmt_sql, re.IGNORECASE):
            return None

        raw_tbl = m.group(1).split('.')[-1].strip('"` ')
        matched_res = next(
            (
                r for r in catalog_resources
                if str(r.get('display_name') or r.get('name') or '').upper()
                == raw_tbl.upper()
                and r.get('resource_kind') in ('table', 'view')
            ),
            None,
        )
        if not matched_res or not hasattr(workspace_service, 'read_visual_admin_rows'):
            return None

        try:
            session_id = self._ensure_session(workspace_service, server, surface)
            t0 = time.perf_counter()
            page = workspace_service.read_visual_admin_rows(
                server,
                {
                    'target_resource': copy.deepcopy(matched_res),
                    'limit': min(500, surface.max_rows),
                    'database_target_id': surface.database_target_id,
                    **({'session_id': session_id} if session_id else {}),
                },
            )
            if page.get('continuation') and hasattr(
                workspace_service, 'cancel_visual_admin_rows'
            ):
                workspace_service.cancel_visual_admin_rows(
                    server,
                    {
                        'continuation': page['continuation'],
                        'database_target_id': surface.database_target_id,
                    },
                )
            dt_ms = (time.perf_counter() - t0) * 1000.0
            cols = list(page.get('columns') or [])
            editable = bool(page.get('editable'))
            fcat = self._build_field_catalog_from_columns(cols, editable)
            rs = SqlResultSetBuffer(
                result_index=0,
                title=f"Result 1 ({matched_res.get('display_name') or raw_tbl})",
                statement_sql=stmt_sql,
                columns=cols,
                field_catalog=fcat,
                raw_rows=list(page.get('rows') or []),
                complete_in_buffer=not bool(page.get('continuation')),
                retrieval_limited=bool(page.get('continuation')),
                editable=editable,
                identity_policy=str(page.get('identity_policy') or 'primary-key'),
                row_operations=list(page.get('row_operations') or []),
                target_resource=copy.deepcopy(matched_res),
                insert_identity_token=page.get('insert_identity_token'),
                execution_ms=round(dt_ms, 2),
                plan_text=f'PLAN ({raw_tbl} LIVE IDENTITY)',
                plan_nodes=[{
                    'id': 'plan-1',
                    'operation': 'LIVE TABLE SCAN',
                    'target': raw_tbl,
                    'strategy': 'Native Row Identity Attached',
                    'rows_buffered': len(page.get('rows') or []),
                    'sort_location': 'Host Cache (Local)',
                    'elapsed_ms': round(dt_ms, 2),
                }],
            )
            self._recompute_rs_view(rs)
            return rs
        except Exception:
            return None

    def _execute_single_statement(
        self,
        workspace_service: Any,
        server: Any,
        surface: SqlEditorSurfaceState,
        seg: ParsedSqlSegment,
        param_values: dict[str, Any] | list[Any],
        catalog_resources: list[dict[str, Any]],
        result_idx: int,
        plan_only: bool = False,
    ) -> SqlResultSetBuffer | None:
        t0 = time.perf_counter()
        session_id = self._ensure_session(workspace_service, server, surface)

        # Check if simple `SELECT * FROM <table>` without params can attach live row identity!
        if (
            not plan_only
            and not extract_query_parameters(seg.sql)
            and re.match(r'^\s*SELECT\s+\*\s+FROM\b', seg.sql, re.IGNORECASE)
        ):
            live_rs = self._try_resolve_live_editable_rows(
                workspace_service, server, surface, seg.sql, catalog_resources
            )
            if live_rs is not None:
                live_rs.result_index = result_idx
                live_rs.title = f'Result {result_idx + 1}'
                self._log(
                    surface,
                    'info',
                    'Execute SELECT (Live Editable)',
                    f'Buffered {len(live_rs.raw_rows)} editable row(s) on host.',
                    elapsed_ms=live_rs.execution_ms,
                )
                return live_rs

        bound_sql, bound_params = bind_named_to_positional_if_needed(
            seg.sql, param_values, surface.parameter_shape
        )

        # Mark Firebird / non-autocommit mutating activity!
        is_readonly_stmt = bool(
            re.match(
                r'^\s*(?:--[^\n]*\n|/\*[\s\S]*?\*/\s*)*(?:SELECT|SHOW|EXPLAIN|PRAGMA)\b',
                seg.sql,
                re.IGNORECASE,
            )
        )
        if not plan_only and not surface.autocommit and not is_readonly_stmt:
            surface.tx_dirty_since_boundary = True

        exec_payload: dict[str, Any] = {
            'session_id': session_id,
            'source': bound_sql,
            'parameters': bound_params,
            'max_rows': surface.max_rows,
            'database_target_id': surface.database_target_id,
        }
        if plan_only:
            exec_payload['plan_mode'] = True
        if surface.language_profile == 'firebird-sql':
            exec_payload['client_sql_dialect'] = 3

        occurrence = workspace_service.execute(server, exec_payload)
        occ_id = occurrence.get('occurrence_id')

        # Poll synchronously on host until terminal (bounded safety timeout)
        poll_resp: dict[str, Any] = {}
        deadline = time.perf_counter() + 60.0
        while time.perf_counter() < deadline:
            poll_resp = workspace_service.poll(
                server,
                occ_id,
                buffer_rows=min(500, surface.page_size),
                database_target_id=surface.database_target_id,
            )
            if poll_resp.get('occurrence', {}).get('operation', {}).get('terminal'):
                break
            time.sleep(0.03)

        dt_ms = (time.perf_counter() - t0) * 1000.0
        occ = poll_resp.get('occurrence') or {}
        res_obj = occ.get('result') or {}
        exts = res_obj.get('extensions') or {}
        rendered = poll_resp.get('rendered_result') or {}

        # Check for provider-reported errors across extensions
        for ext_val in exts.values():
            payload = (ext_val or {}).get('payload') if isinstance(ext_val, dict) else None
            if isinstance(payload, dict) and payload.get('error'):
                err_info = payload['error']
                err_msg = str(
                    err_info.get('message')
                    or err_info.get('type')
                    or 'Statement execution failed.'
                )
                self._log(
                    surface,
                    'error',
                    'Execute',
                    err_msg,
                    elapsed_ms=dt_ms,
                    sqlstate=str(err_info.get('sqlstate') or ''),
                    native_code=str(
                        (err_info.get('native_status_codes') or [''])[0]
                        if isinstance(err_info.get('native_status_codes'), list)
                        else err_info.get('errno') or ''
                    ),
                    line=seg.start_line,
                )
                raise RuntimeError(err_msg)

        # Extract plan text if present
        plan_text = ''
        fb_payload = (exts.get('firebird') or {}).get('payload') or {}
        if fb_payload.get('query_plan'):
            qp = fb_payload['query_plan']
            plan_text = str(qp.get('plan_text') or qp.get('raw') or qp) if isinstance(qp, dict) else str(qp)

        # Extract columns & rows from `rendered_result`
        raw_cols = rendered.get('columns') or res_obj.get('columns') or []
        cols: list[dict[str, Any]] = []
        for idx, c in enumerate(raw_cols):
            if isinstance(c, dict):
                cols.append({
                    'name': str(c.get('name') or c.get('label') or f'COL_{idx + 1}'),
                    'native_type': str(c.get('native_type') or c.get('type_name') or c.get('data_type') or 'TEXT'),
                    'nullable': bool(c.get('nullable', True)),
                    'key': bool(c.get('key', False)),
                    'editable': False,
                })
            else:
                cols.append({
                    'name': str(c),
                    'native_type': 'TEXT',
                    'nullable': True,
                    'key': False,
                    'editable': False,
                })

        page_rows = (
            (rendered.get('page') or {}).get('rows')
            or rendered.get('rows')
            or res_obj.get('rows')
            or []
        )
        normalized_rows: list[dict[str, Any]] = []
        col_names = [c['name'] for c in cols]
        for r_i, r_item in enumerate(page_rows):
            if isinstance(r_item, dict) and 'values' in r_item and isinstance(r_item['values'], dict):
                vals = dict(r_item['values'])
            elif isinstance(r_item, dict):
                vals = {cname: r_item.get(cname) for cname in col_names}
            elif isinstance(r_item, (list, tuple)):
                vals = {
                    col_names[c_i]: r_item[c_i] if c_i < len(r_item) else None
                    for c_i in range(len(col_names))
                }
            else:
                vals = {col_names[0]: r_item} if col_names else {}
            normalized_rows.append({
                'identity_token': f'qrow:{r_i}',
                'values': vals,
            })

        if surface.autocommit and session_id and not is_readonly_stmt and not plan_only:
            try:
                surface.transaction = workspace_service.transaction_action(
                    server,
                    session_id,
                    'commit',
                    database_target_id=surface.database_target_id,
                )
                surface.tx_dirty_since_boundary = False
            except Exception:
                pass

        if not cols and not normalized_rows:
            affected = res_obj.get('rowcount') or rendered.get('rowcount')
            msg_detail = (
                f'Statement completed ({affected} row(s) affected).'
                if affected is not None
                else 'Statement completed.'
            )
            self._log(
                surface,
                'info',
                'Execute Plan' if plan_only else 'Execute Statement',
                plan_text or msg_detail,
                elapsed_ms=dt_ms,
                line=seg.start_line,
            )
            if plan_only and plan_text:
                surface.timings_ms['execute_ms'] = round(dt_ms, 2)
                rs_plan = SqlResultSetBuffer(
                    result_index=result_idx,
                    title='Query Plan',
                    statement_sql=seg.sql,
                    execution_ms=round(dt_ms, 2),
                    plan_text=plan_text,
                    plan_nodes=[{
                        'id': 'plan-1',
                        'operation': 'EXPLAIN / PLAN',
                        'target': seg.sql[:48],
                        'strategy': plan_text[:80],
                        'rows_buffered': 0,
                        'sort_location': 'Server',
                        'elapsed_ms': round(dt_ms, 2),
                    }],
                )
                return rs_plan
            return None

        fcat = self._build_field_catalog_from_columns(cols, False)
        has_more = bool((rendered.get('page') or {}).get('next_cursor'))
        rs = SqlResultSetBuffer(
            result_index=result_idx,
            title=f'Result {result_idx + 1}',
            statement_sql=seg.sql,
            columns=cols,
            field_catalog=fcat,
            raw_rows=normalized_rows,
            complete_in_buffer=not has_more,
            retrieval_limited=has_more,
            editable=False,
            identity_policy='read-only-query',
            row_operations=[],
            execution_ms=round(dt_ms, 2),
            plan_text=plan_text or 'PLAN (Query Execution)',
            plan_nodes=[{
                'id': f'plan-{result_idx + 1}',
                'operation': 'SELECT',
                'target': seg.sql.splitlines()[0][:60],
                'strategy': plan_text or 'Server Execution',
                'rows_buffered': len(normalized_rows),
                'sort_location': 'Host Cache (Local)',
                'elapsed_ms': round(dt_ms, 2),
            }],
        )
        self._recompute_rs_view(rs)
        self._log(
            surface,
            'info',
            'Execute SELECT',
            f'Returned {len(normalized_rows)} row(s) in {round(dt_ms, 2)} ms.',
            elapsed_ms=dt_ms,
            line=seg.start_line,
        )
        return rs

    def _serialize_state(
        self,
        surface: SqlEditorSurfaceState,
        user_id: int,
        *,
        window_offset: int = 0,
        window_size: int | None = None,
    ) -> dict[str, Any]:
        w_size = max(1, min(1000, int(window_size or surface.page_size)))
        active_rs = (
            surface.result_sets[surface.active_result_index]
            if 0 <= surface.active_result_index < len(surface.result_sets)
            else None
        )

        staged_total = sum(len(rs.staged_mutations) for rs in surface.result_sets)
        has_uncommitted = bool(
            not surface.autocommit
            and (surface.tx_dirty_since_boundary or staged_total > 0)
        )

        window_rows: list[dict[str, Any]] = []
        staged_sql: list[dict[str, Any]] = []
        total_filtered = 0
        safe_offset = 0

        if active_rs is not None:
            upd_by_idx: dict[int, StagedRowMutation] = {}
            del_by_idx: set[int] = set()
            ins_list: list[StagedRowMutation] = []
            for mut in active_rs.staged_mutations.values():
                staged_sql.append({
                    'mutation_id': mut.mutation_id,
                    'op': mut.op,
                    'row_key': mut.row_key,
                    'sql': mut.preview_sql,
                })
                if mut.op == 'insert':
                    ins_list.append(mut)
                elif mut.op == 'update' and mut.base_row_index is not None:
                    upd_by_idx[mut.base_row_index] = mut
                elif mut.op == 'delete' and mut.base_row_index is not None:
                    del_by_idx.add(mut.base_row_index)

            total_filtered = len(active_rs.view_indices) + len(ins_list)
            safe_offset = (
                max(0, min(window_offset, max(0, total_filtered - 1)))
                if total_filtered > 0
                else 0
            )
            for pos, raw_idx in enumerate(
                active_rs.view_indices[safe_offset:safe_offset + w_size]
            ):
                base_row = active_rs.raw_rows[raw_idx]
                vals = copy.deepcopy(base_row.get('values') or {})
                st_state = None
                mut_id = None
                if raw_idx in upd_by_idx:
                    m_u = upd_by_idx[raw_idx]
                    vals.update(copy.deepcopy(m_u.overlay_values))
                    st_state = 'updated'
                    mut_id = m_u.mutation_id
                if raw_idx in del_by_idx:
                    st_state = 'deleted'
                window_rows.append({
                    'row_number': safe_offset + pos + 1,
                    'base_row_index': raw_idx,
                    'identity_token': base_row.get('identity_token'),
                    'values': vals,
                    'original_values': base_row.get('values') or {},
                    'stage_state': st_state,
                    'mutation_id': mut_id,
                })

            if len(window_rows) < w_size and ins_list:
                rem = w_size - len(window_rows)
                ins_start = max(0, safe_offset - len(active_rs.view_indices))
                for off, ins in enumerate(ins_list[ins_start:ins_start + rem]):
                    window_rows.append({
                        'row_number': len(active_rs.view_indices) + ins_start + off + 1,
                        'base_row_index': None,
                        'identity_token': ins.mutation_id,
                        'values': copy.deepcopy(ins.overlay_values),
                        'original_values': {},
                        'stage_state': 'inserted',
                        'mutation_id': ins.mutation_id,
                    })

        scene, _, fanout_warnings = build_visual_query_ddn_scene(
            surface.visual_model,
            surface.catalog_tables_cache,
            surface.engine_id,
        )

        result_summaries = [
            {
                'index': rs.result_index,
                'title': rs.title,
                'row_count': len(rs.raw_rows),
                'editable': rs.editable,
            }
            for rs in surface.result_sets
        ]

        active_result_obj = (
            {
                'index': active_rs.result_index,
                'title': active_rs.title,
                'columns': active_rs.columns,
                'rows': window_rows,
                'sort': active_rs.sorts,
                'filters': active_rs.filters,
                'editable': bool(active_rs.editable),
                'identity_policy': active_rs.identity_policy,
                'row_operations': active_rs.row_operations,
                'total_view_rows': total_filtered,
                'total_buffered_rows': len(active_rs.raw_rows),
                'plan_text': active_rs.plan_text,
                'plan_nodes': active_rs.plan_nodes,
                'staged_mutations': [
                    {
                        'mutation_id': mut.mutation_id,
                        'op': mut.op,
                        'row_key': mut.row_key,
                        'preview_sql': mut.preview_sql,
                    }
                    for mut in active_rs.staged_mutations.values()
                ],
                'target_resource': active_rs.target_resource,
            }
            if active_rs is not None
            else None
        )

        return {
            'surface_id': surface.surface_id,
            'has_uncommitted_activity': has_uncommitted,
            'staged_count': staged_total,
            'engine_id': surface.engine_id,
            'language_profile': surface.language_profile,
            'database_target_id': surface.database_target_id,
            'session_id': surface.session_id,
            'autocommit': surface.autocommit,
            'terminator': surface.terminator,
            'sql_source': surface.sql_source,
            'detected_parameters': extract_query_parameters(surface.sql_source),
            'bound_parameters': surface.bound_parameters,
            'result_count': len(surface.result_sets),
            'result_summaries': result_summaries,
            'result_sets_summary': result_summaries,
            'active_result_index': surface.active_result_index,
            'active_result': active_result_obj,
            'editable': bool(active_rs.editable) if active_rs else False,
            'identity_policy': active_rs.identity_policy if active_rs else 'no-result',
            'row_operations': active_rs.row_operations if active_rs else [],
            'page_size': surface.page_size,
            'max_rows': surface.max_rows,
            'window_offset': safe_offset,
            'window_size': w_size,
            'total_buffered_rows': len(active_rs.raw_rows) if active_rs else 0,
            'total_view_rows': total_filtered,
            'complete_in_buffer': active_rs.complete_in_buffer if active_rs else True,
            'retrieval_limited': active_rs.retrieval_limited if active_rs else False,
            'sort_execution': active_rs.sort_execution if active_rs else 'local',
            'sorts': active_rs.sorts if active_rs else [],
            'filters': active_rs.filters if active_rs else [],
            'columns': active_rs.columns if active_rs else [],
            'rows': window_rows,
            'fields_grid': active_rs.field_catalog if active_rs else [],
            'timings_ms': surface.timings_ms,
            'plan_text': active_rs.plan_text if active_rs else '',
            'statement_summaries': getattr(surface, 'last_statement_summaries', []),
            'last_execution_had_error': bool(getattr(surface, 'last_execution_had_error', False)),
            'quick_queries': self.quick_query_store.list_quick_queries(
                user_id,
                server_id=surface.server_id,
                database_target_id=surface.database_target_id,
            ),
            'snippets': self.snippets_store.search_snippets(
                user_id,
                engine_id=surface.engine_id,
            ),
            'sql_view': {
                'server_sql': active_rs.statement_sql if active_rs else surface.sql_source,
                'parameters': surface.bound_parameters,
                'sort_execution': active_rs.sort_execution if active_rs else 'local',
                'sort_mode': active_rs.sort_mode if active_rs else 'auto',
                'is_local_sort_or_filter': bool(
                    active_rs and (active_rs.sorts or active_rs.filters)
                ),
                'local_operations_summary': (
                    'Local host-cached sort/filter active'
                    if active_rs and (active_rs.sorts or active_rs.filters)
                    else 'Executed directly on database server'
                ),
                'staged_sql': staged_sql,
            },
            'metrics_view': {
                'timings_ms': surface.timings_ms,
                'buffer': {
                    'buffered_rows': len(active_rs.raw_rows) if active_rs else 0,
                    'visible_rows': total_filtered,
                    'complete_in_buffer': active_rs.complete_in_buffer if active_rs else True,
                    'retrieval_limited': active_rs.retrieval_limited if active_rs else False,
                    'host_memory_bytes': _estimate_bytes(
                        active_rs.raw_rows if active_rs else []
                    ),
                    'page_size': surface.page_size,
                    'max_rows': surface.max_rows,
                },
                'transaction': {
                    'session_id': surface.session_id,
                    'autocommit': surface.autocommit,
                    'staged_inserts': sum(
                        1 for m in (active_rs.staged_mutations.values() if active_rs else ()) if m.op == 'insert'
                    ),
                    'staged_updates': sum(
                        1 for m in (active_rs.staged_mutations.values() if active_rs else ()) if m.op == 'update'
                    ),
                    'staged_deletes': sum(
                        1 for m in (active_rs.staged_mutations.values() if active_rs else ()) if m.op == 'delete'
                    ),
                    'staged_total': staged_total,
                    'has_uncommitted_activity': has_uncommitted,
                    'provider_observation': surface.transaction,
                },
                'plan_text': active_rs.plan_text if active_rs else '',
                'plan_nodes': active_rs.plan_nodes if active_rs else [],
            },
            'visual_builder': {
                'model': surface.visual_model,
                'fidelity': surface.visual_fidelity,
                'ddn_scene': scene,
                'fanout_warnings': fanout_warnings,
            },
            'query_history': list(reversed(surface.query_history[-50:])),
            'messages': list(reversed(surface.messages)),
        }

    def dispatch(
        self,
        workspace_service: Any,
        server: Any,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        sub_action = str(
            request.get('surface_action') or request.get('sub_action') or 'open'
        ).lower()
        user_id = int(getattr(server, 'user_id', 1) or 1)
        server_id = int(getattr(server, 'id', 0) or 0)

        # Standalone snippet / quick-query actions
        if sub_action in ('snippets_search', 'list_snippets'):
            return self.snippets_store.search_snippets(
                user_id,
                engine_id=request.get('engine_id'),
                search_text=str(request.get('search_text') or ''),
                selected_tags=request.get('selected_tags') or [],
                tag_mode=str(request.get('tag_mode') or 'and'),
                favorites_only=bool(request.get('favorites_only')),
                include_all_engines=bool(request.get('include_all_engines')),
            )

        if sub_action in ('snippets_save', 'save_snippet'):
            saved = self.snippets_store.save_snippet(user_id, dict(request.get('snippet') or {}))
            return {
                'snippet': saved,
                'snippets': self.snippets_store.search_snippets(
                    user_id, engine_id=request.get('engine_id')
                ),
            }

        if sub_action in ('snippets_delete', 'delete_snippet'):
            deleted = self.snippets_store.delete_snippet(
                user_id, str(request.get('snippet_id') or '')
            )
            return {
                **deleted,
                'snippets': self.snippets_store.search_snippets(
                    user_id, engine_id=request.get('engine_id')
                ),
            }

        if sub_action == 'toggle_snippet_favorite':
            toggled = self.snippets_store.toggle_favorite(
                user_id, str(request.get('snippet_id') or '')
            )
            return {
                'snippet': toggled,
                'snippets': self.snippets_store.search_snippets(
                    user_id, engine_id=request.get('engine_id')
                ),
            }

        if sub_action == 'quick_queries_list':
            return {
                'quick_queries': self.quick_query_store.list_quick_queries(
                    user_id,
                    server_id=server_id,
                    database_target_id=request.get('database_target_id'),
                )
            }

        if sub_action in ('quick_queries_save', 'save_quick_query'):
            q_payload = dict(request.get('quick_query') or {})
            q_payload.setdefault('server_id', server_id)
            q_payload.setdefault('database_target_id', request.get('database_target_id') or '')
            q_payload.setdefault('engine_id', request.get('engine_id') or '')
            saved = self.quick_query_store.save_quick_query(user_id, q_payload)
            return {
                'quick_query': saved,
                'saved_quick_query': saved,
                'quick_queries': self.quick_query_store.list_quick_queries(
                    user_id,
                    server_id=server_id,
                    database_target_id=request.get('database_target_id'),
                ),
            }

        if sub_action in ('quick_queries_delete', 'delete_quick_query'):
            deleted = self.quick_query_store.delete_quick_query(
                user_id, str(request.get('query_id') or '')
            )
            return {
                **deleted,
                'quick_queries': self.quick_query_store.list_quick_queries(
                    user_id,
                    server_id=server_id,
                    database_target_id=request.get('database_target_id'),
                ),
            }

        if sub_action == 'generate_object_script':
            return generate_universal_object_sql(
                workspace_service,
                server,
                engine_id=str(request.get('engine_id') or ''),
                database_target_id=request.get('database_target_id'),
                target_resource=dict(request.get('target_resource') or {}),
                script_kind=str(request.get('script_kind') or 'select'),
            )

        surface = self._get_or_create_surface(server, request)
        with surface.lock:
            if 'page_size' in request and request['page_size']:
                surface.page_size = max(10, min(1000, int(request['page_size'])))
            if 'max_rows' in request and request['max_rows']:
                surface.max_rows = max(1, min(100000, int(request['max_rows'])))
            if 'autocommit' in request and request['autocommit'] is not None:
                surface.autocommit = bool(request['autocommit'])
            if 'terminator' in request and request['terminator']:
                surface.terminator = str(request['terminator']).strip() or ';'
            if 'active_result_index' in request and request['active_result_index'] is not None:
                idx_req = int(request['active_result_index'])
                if 0 <= idx_req < len(surface.result_sets):
                    surface.active_result_index = idx_req

            window_offset = int(request.get('window_offset') or 0)
            window_size = int(request.get('window_size') or surface.page_size)
            catalog_resources = list(
                request.get('catalog_resources') or request.get('resources') or []
            )
            for res_item in catalog_resources:
                rname = str(res_item.get('display_name') or res_item.get('name') or '')
                rcols = (
                    (res_item.get('extensions') or {})
                    .get('cdeadmin', {})
                    .get('catalog_metadata', {})
                    .get('columns')
                    or res_item.get('columns')
                    or []
                )
                if rname and rcols and rname not in surface.catalog_tables_cache:
                    surface.catalog_tables_cache[rname] = list(rcols)

            if sub_action == 'open':
                seed_sql = request.get('initial_sql') or request.get('sql_source')
                seed_kind = request.get('script_kind') or request.get('generate_sql_kind')
                if seed_sql and not surface.sql_source:
                    surface.sql_source = str(seed_sql)
                    parsed_vm, fid = parse_sql_to_visual_model(surface.sql_source)
                    if parsed_vm is not None:
                        surface.visual_model = parsed_vm
                        surface.visual_fidelity = fid
                elif request.get('target_resource') and seed_kind and not surface.sql_source:
                    gen = generate_universal_object_sql(
                        workspace_service,
                        server,
                        engine_id=surface.engine_id,
                        database_target_id=surface.database_target_id,
                        target_resource=dict(request['target_resource']),
                        script_kind=str(seed_kind),
                    )
                    surface.sql_source = gen['sql']
                    surface.terminator = gen.get('terminator') or ';'
                return self._serialize_state(
                    surface, user_id, window_offset=window_offset, window_size=window_size
                )

            if sub_action == 'load_quick_query':
                qq = self.quick_query_store.get_quick_query(str(request.get('query_id') or ''))
                if qq:
                    surface.sql_source = qq.get('sql_text') or ''
                    surface.terminator = qq.get('terminator') or ';'
                return {
                    'loaded_quick_query': qq,
                    'state': self._serialize_state(
                        surface, user_id, window_offset=window_offset, window_size=window_size
                    ),
                }

            if sub_action in ('set_options', 'select_result', 'cancel'):
                if sub_action == 'select_result':
                    idx_sel = int(request.get('result_index') or 0)
                    if 0 <= idx_sel < len(surface.result_sets):
                        surface.active_result_index = idx_sel
                elif sub_action == 'cancel':
                    self._log(surface, 'warning', 'Cancel', 'Execution cancel requested.')
                return self._serialize_state(
                    surface, user_id, window_offset=window_offset, window_size=window_size
                )

            if sub_action == 'check_parameters':
                raw_src = str(request.get('sql_source') or surface.sql_source or '')
                sel_src = str(request.get('selection_text') or request.get('selected_sql') or '').strip()
                mode_chk = str(request.get('mode') or 'statement').lower()
                cursor_off = int(request.get('cursor_offset') or 0)
                if mode_chk == 'script':
                    segs = split_sql_statements(raw_src, surface.terminator, surface.engine_id)
                    target_sql = '\n'.join(s.sql for s in segs)
                elif sel_src:
                    target_sql = sel_src
                else:
                    seg_one = extract_statement_at_cursor(
                        raw_src, cursor_off, surface.terminator, surface.engine_id
                    )
                    target_sql = seg_one.sql if seg_one else raw_src
                detected = extract_query_parameters(target_sql)
                return {
                    'parameters': [
                        {
                            **d,
                            'index': d.get('position', idx + 1),
                            'token': (
                                f":{d['name']}"
                                if d['kind'] == 'named'
                                else d['name']
                                if d['kind'] == 'positional'
                                else '?'
                            ),
                        }
                        for idx, d in enumerate(detected)
                    ]
                }

            if sub_action in ('sync_sql_to_visual', 'visual_builder_from_sql'):
                surface.sql_source = str(
                    request.get('sql_source') or request.get('sql_text') or surface.sql_source or ''
                )
                parsed_vm, fid = parse_sql_to_visual_model(surface.sql_source)
                loss_notes: list[str] = []
                if parsed_vm is not None:
                    surface.visual_model = parsed_vm
                    surface.visual_fidelity = fid
                    if fid == 'lossy':
                        loss_notes.append(
                            'Complex SQL expressions or CTEs are preserved lossily in the visual model.'
                        )
                else:
                    surface.visual_fidelity = 'none'
                    loss_notes.append(
                        'Non-SELECT statement cannot be represented as a visual join diagram.'
                    )
                st = self._serialize_state(
                    surface, user_id, window_offset=window_offset, window_size=window_size
                )
                return {
                    **st,
                    'model': surface.visual_model,
                    'scene': st['visual_builder']['ddn_scene'],
                    'fidelity': surface.visual_fidelity,
                    'loss_notes': loss_notes,
                    'fanout_warnings': st['visual_builder']['fanout_warnings'],
                }

            if sub_action in ('sync_visual_to_sql', 'visual_builder_scene'):
                incoming_model = request.get('visual_model') or request.get('model')
                if isinstance(incoming_model, dict):
                    surface.visual_model = copy.deepcopy(incoming_model)
                if isinstance(request.get('table_columns'), dict):
                    surface.catalog_tables_cache.update(request['table_columns'])
                scene_out, built_sql, fanout_out = build_visual_query_ddn_scene(
                    surface.visual_model,
                    surface.catalog_tables_cache,
                    surface.engine_id,
                )
                if built_sql:
                    surface.sql_source = built_sql
                    surface.visual_fidelity = 'exact'
                st = self._serialize_state(
                    surface, user_id, window_offset=window_offset, window_size=window_size
                )
                return {
                    **st,
                    'scene': scene_out,
                    'sql_text': built_sql,
                    'fanout_warnings': fanout_out,
                }

            if sub_action in ('execute', 'execute_statement', 'execute_script', 'explain_plan'):
                t_all = time.perf_counter()
                if 'sql_source' in request and request['sql_source'] is not None:
                    surface.sql_source = str(request['sql_source'])
                req_params = request.get('parameters')
                if isinstance(req_params, dict):
                    surface.bound_parameters.update(req_params)
                    exec_params: dict[str, Any] | list[Any] = surface.bound_parameters
                elif isinstance(req_params, list):
                    exec_params = list(req_params)
                else:
                    exec_params = surface.bound_parameters

                exec_mode = (
                    str(request.get('mode') or 'statement').lower()
                    if sub_action == 'execute'
                    else 'script'
                    if sub_action == 'execute_script'
                    else 'explain'
                    if sub_action == 'explain_plan'
                    else 'statement'
                )
                selected_sql = str(
                    request.get('selected_sql') or request.get('selection_text') or ''
                ).strip()
                cursor_offset = int(request.get('cursor_offset') or 0)
                plan_only = exec_mode == 'explain'

                if exec_mode == 'script':
                    segments = split_sql_statements(
                        selected_sql or surface.sql_source,
                        surface.terminator,
                        surface.engine_id,
                    )
                else:
                    if selected_sql:
                        segments = [
                            ParsedSqlSegment(
                                sql=selected_sql,
                                start_offset=0,
                                end_offset=len(selected_sql),
                                start_line=1,
                                terminator=surface.terminator,
                            )
                        ]
                    else:
                        one = extract_statement_at_cursor(
                            surface.sql_source,
                            cursor_offset,
                            surface.terminator,
                            surface.engine_id,
                        )
                        segments = [one] if one else []

                if not segments:
                    raise ValueError('No SQL statement found to execute.')

                new_results: list[SqlResultSetBuffer] = []
                stmt_summaries: list[dict[str, Any]] = []
                had_error = False
                for ordinal, seg in enumerate(segments, start=1):
                    t_seg = time.perf_counter()
                    try:
                        rs = self._execute_single_statement(
                            workspace_service,
                            server,
                            surface,
                            seg,
                            exec_params,
                            catalog_resources,
                            len(new_results),
                            plan_only=plan_only,
                        )
                        dt_seg = round((time.perf_counter() - t_seg) * 1000.0, 2)
                        if rs is not None:
                            new_results.append(rs)
                        stmt_summaries.append({
                            'ordinal': ordinal,
                            'start_line': seg.start_line,
                            'status': 'ok',
                            'rows_returned': len(rs.raw_rows) if rs is not None else 0,
                            'elapsed_ms': dt_seg,
                            'sql_preview': seg.sql.splitlines()[0][:80] if seg.sql else '',
                        })
                    except RuntimeError as err:
                        had_error = True
                        dt_seg = round((time.perf_counter() - t_seg) * 1000.0, 2)
                        stmt_summaries.append({
                            'ordinal': ordinal,
                            'start_line': seg.start_line,
                            'status': f'error: {err}',
                            'rows_returned': 0,
                            'elapsed_ms': dt_seg,
                            'sql_preview': seg.sql.splitlines()[0][:80] if seg.sql else '',
                        })
                        if sub_action != 'execute':
                            raise
                        break

                total_ms = (time.perf_counter() - t_all) * 1000.0
                surface.timings_ms['execute_ms'] = round(total_ms, 2)
                surface.timings_ms['total_ms'] = round(total_ms, 2)
                surface.last_statement_summaries = stmt_summaries
                surface.last_execution_had_error = had_error
                if new_results or not had_error:
                    surface.result_sets = new_results
                    surface.active_result_index = 0
                surface.query_history.append({
                    'id': f'qh-{len(surface.query_history) + 1}',
                    'timestamp': _now_iso(),
                    'mode': exec_mode,
                    'sql': selected_sql or surface.sql_source,
                    'elapsed_ms': round(total_ms, 2),
                    'result_sets': len(new_results),
                })

                if surface.session_id and hasattr(workspace_service, 'transaction'):
                    try:
                        surface.transaction = workspace_service.transaction(
                            server, surface.session_id, surface.database_target_id
                        )
                    except Exception:
                        pass

                return self._serialize_state(surface, user_id, window_offset=0, window_size=window_size)

            if sub_action in ('read_window', 'sort_filter', 'query_view'):
                active_rs = (
                    surface.result_sets[surface.active_result_index]
                    if 0 <= surface.active_result_index < len(surface.result_sets)
                    else None
                )
                if active_rs and sub_action in ('sort_filter', 'query_view'):
                    incoming_sorts = request.get('sorts') if isinstance(request.get('sorts'), list) else request.get('sort')
                    if isinstance(incoming_sorts, list):
                        active_rs.sorts = list(incoming_sorts)
                    if isinstance(request.get('filters'), list):
                        active_rs.filters = list(request['filters'])
                    t_sf = self._recompute_rs_view(active_rs)
                    surface.timings_ms.update(t_sf)
                return self._serialize_state(
                    surface, user_id, window_offset=window_offset, window_size=window_size
                )

            if sub_action == 'stage_row':
                active_rs = (
                    surface.result_sets[surface.active_result_index]
                    if 0 <= surface.active_result_index < len(surface.result_sets)
                    else None
                )
                if not active_rs or not active_rs.editable or not active_rs.target_resource:
                    raise RuntimeError('Current query result set is read-only.')

                op = str(request.get('op') or 'update').lower()
                base_idx = request.get('base_row_index')
                base_idx = int(base_idx) if base_idx is not None else None
                changes = dict(request.get('changes') or {})
                session_id = self._ensure_session(workspace_service, server, surface)

                if op == 'insert':
                    draft = {'values': changes}
                    row_key = str(request.get('mutation_id') or f'ins-{uuid.uuid4()}')
                    id_tok = None
                elif op in ('update', 'delete'):
                    if base_idx is None or not (0 <= base_idx < len(active_rs.raw_rows)):
                        raise ValueError('Row index out of bounds')
                    id_tok = request.get('identity_token') or active_rs.raw_rows[base_idx].get('identity_token')
                    draft = (
                        {
                            'selector': {'identity_token': id_tok},
                            'changes': changes,
                            'concurrency_token': id_tok,
                        }
                        if op == 'update'
                        else {
                            'selector': {'identity_token': id_tok},
                            'concurrency_token': id_tok,
                            'confirmation': 'provider-row-delete',
                        }
                    )
                    row_key = f'row-{base_idx}'
                else:
                    raise ValueError(f'Unsupported row operation: {op}')

                plan_req = {
                    'resource_kind': active_rs.target_resource.get('resource_kind', 'table'),
                    'operation_id': op,
                    'target_resource': copy.deepcopy(active_rs.target_resource),
                    'draft': draft,
                    'session_id': session_id,
                    'database_target_id': surface.database_target_id,
                }
                val_res = workspace_service.validate_visual_admin(server, plan_req)
                if not val_res.get('valid'):
                    raise RuntimeError('Row validation failed.')
                plan = workspace_service.plan_visual_admin(server, plan_req)
                if plan.get('state') != 'ready' or not plan.get('execution_available'):
                    raise RuntimeError('Row mutation plan blocked.')
                preview_sql = _plan_sql_text(plan)

                if surface.autocommit:
                    workspace_service.apply_visual_admin(
                        server,
                        {
                            'plan_id': plan['plan_id'],
                            'plan_digest': plan['plan_digest'],
                            'confirmed': op == 'delete',
                            'session_id': session_id,
                            'database_target_id': surface.database_target_id,
                        },
                    )
                    if session_id:
                        surface.transaction = workspace_service.transaction_action(
                            server, session_id, 'commit', database_target_id=surface.database_target_id
                        )
                    surface.tx_dirty_since_boundary = False
                else:
                    existing_m = active_rs.staged_mutations.get(row_key)
                    merged_ov = dict(existing_m.overlay_values) if existing_m else {}
                    merged_ov.update(changes)
                    active_rs.staged_mutations[row_key] = StagedRowMutation(
                        mutation_id=row_key,
                        op=op,
                        row_key=row_key,
                        base_row_index=base_idx,
                        identity_token=id_tok,
                        draft=draft,
                        overlay_values=merged_ov,
                        preview_sql=preview_sql,
                        staged_at=_now_iso(),
                    )
                return self._serialize_state(
                    surface, user_id, window_offset=window_offset, window_size=window_size
                )

            if sub_action == 'revert_row':
                active_rs = (
                    surface.result_sets[surface.active_result_index]
                    if 0 <= surface.active_result_index < len(surface.result_sets)
                    else None
                )
                if active_rs:
                    active_rs.staged_mutations.pop(str(request.get('row_key') or ''), None)
                return self._serialize_state(
                    surface, user_id, window_offset=window_offset, window_size=window_size
                )

            if sub_action == 'commit_batch':
                t0 = time.perf_counter()
                session_id = self._ensure_session(workspace_service, server, surface)
                applied = 0
                for rs in surface.result_sets:
                    if not rs.target_resource:
                        continue
                    for row_key, mut in list(rs.staged_mutations.items()):
                        plan_req = {
                            'resource_kind': rs.target_resource.get('resource_kind', 'table'),
                            'operation_id': mut.op,
                            'target_resource': copy.deepcopy(rs.target_resource),
                            'draft': mut.draft,
                            'session_id': session_id,
                            'database_target_id': surface.database_target_id,
                        }
                        plan = workspace_service.plan_visual_admin(server, plan_req)
                        workspace_service.apply_visual_admin(
                            server,
                            {
                                'plan_id': plan['plan_id'],
                                'plan_digest': plan['plan_digest'],
                                'confirmed': mut.op == 'delete',
                                'session_id': session_id,
                                'database_target_id': surface.database_target_id,
                            },
                        )
                        surface.tx_dirty_since_boundary = True
                        if mut.op == 'update' and mut.base_row_index is not None:
                            rs.raw_rows[mut.base_row_index]['values'].update(mut.overlay_values)
                        elif mut.op == 'insert':
                            rs.raw_rows.append({
                                'identity_token': mut.mutation_id,
                                'values': copy.deepcopy(mut.overlay_values),
                            })
                            self._recompute_rs_view(rs)
                        rs.staged_mutations.pop(row_key, None)
                        applied += 1

                if session_id:
                    surface.transaction = workspace_service.transaction_action(
                        server, session_id, 'commit', database_target_id=surface.database_target_id
                    )
                surface.tx_dirty_since_boundary = False
                self._log(
                    surface,
                    'info',
                    'Commit',
                    f'Committed transaction ({applied} staged row mutation(s) flushed).',
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )
                return self._serialize_state(
                    surface, user_id, window_offset=window_offset, window_size=window_size
                )

            if sub_action == 'rollback_batch':
                t0 = time.perf_counter()
                discarded = sum(len(rs.staged_mutations) for rs in surface.result_sets)
                for rs in surface.result_sets:
                    rs.staged_mutations.clear()
                if surface.session_id:
                    try:
                        surface.transaction = workspace_service.transaction_action(
                            server,
                            surface.session_id,
                            'rollback',
                            database_target_id=surface.database_target_id,
                        )
                    except Exception:
                        pass
                surface.tx_dirty_since_boundary = False
                self._log(
                    surface,
                    'warning',
                    'Rollback',
                    f'Rolled back transaction and discarded {discarded} staged mutation(s).',
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )
                return self._serialize_state(
                    surface, user_id, window_offset=window_offset, window_size=window_size
                )

            if sub_action == 'export_formatted':
                active_rs = (
                    surface.result_sets[surface.active_result_index]
                    if 0 <= surface.active_result_index < len(surface.result_sets)
                    else None
                )
                if not active_rs:
                    raise ValueError('No active result set to export.')
                scope = str((request.get('settings') or {}).get('scope') or 'filtered')
                export_rows = (
                    [active_rs.raw_rows[i] for i in active_rs.view_indices]
                    if scope == 'filtered'
                    else list(active_rs.raw_rows)
                )
                return export_tabular_dataset(
                    active_rs.columns,
                    export_rows,
                    fmt=str(request.get('format') or 'csv'),
                    settings=dict(request.get('settings') or {}),
                    sql_text=active_rs.statement_sql or surface.sql_source,
                    base_filename=str(request.get('filename') or 'sql_result'),
                )

            if sub_action == 'column_profile':
                active_rs = (
                    surface.result_sets[surface.active_result_index]
                    if 0 <= surface.active_result_index < len(surface.result_sets)
                    else None
                )
                col_name = str(request.get('column') or '')
                if not active_rs:
                    return {'column': col_name, 'total_rows': 0, 'null_count': 0, 'distinct_count': 0, 'top_values': []}
                null_cnt = 0
                freq: collections.Counter[str] = collections.Counter()
                for idx in active_rs.view_indices:
                    val = (active_rs.raw_rows[idx].get('values') or {}).get(col_name)
                    if val is None:
                        null_cnt += 1
                    else:
                        freq[str(val)] += 1
                return {
                    'column': col_name,
                    'total_rows': len(active_rs.view_indices),
                    'null_count': null_cnt,
                    'non_null_count': len(active_rs.view_indices) - null_cnt,
                    'distinct_count': len(freq),
                    'top_values': [{'value': k, 'count': c} for k, c in freq.most_common(25)],
                }

            if sub_action == 'close_surface':
                with self._lock:
                    self._surfaces.pop(surface.surface_id, None)
                if surface.session_id:
                    try:
                        workspace_service.close_session(
                            server, surface.session_id, surface.database_target_id
                        )
                    except Exception:
                        pass
                return {'closed': True, 'surface_id': surface.surface_id}

            raise ValueError(f'Unknown SQL surface action: {sub_action}')


DEFAULT_SQL_SURFACE_HOST = SqlSurfaceHostService()
