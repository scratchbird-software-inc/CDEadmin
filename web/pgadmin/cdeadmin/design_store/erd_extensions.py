##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""ERD & Data Modelling Phase 1 + Phase 2 server extensions.

Implements:
- Clean-room SQL DDL (.sql), DBML (.dbml) and Live Catalog ERD importers
  producing 4-level DDN designs with explicit loss reports (SR-F-030015).
- Four-level ERD element inspection and interactive CRUD / whiteboard sketch
  mutation preserving UUIDv7 identities, bindings and layout pins (SR-F-030010).
- Conceptual Whiteboard -> Logical + Physical promotion ("Make it a design...",
  SR-F-030011).
- Configurable Naming Standards checker, 1-click auto-fix and persistent
  waiver management (SR-F-030012).
- Alter-plan 4-category risk classification, Flyway/Liquibase/Atlas/SQL
  migration wrappers, native OperationBus review submission (awaiting_approval)
  and Multi-Target Deployment Environment Matrix (Dev/Staging/Prod) joined
  with designs.db target_deployment (SR-F-030013 & SR-F-030014).
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from pgadmin.cdeadmin.workspace import ddn_source as ddn

from .ddn_elements import (
    _extract_x_record,
    _parse_blocks,
    inspect_ddn_text,
    sha256_text,
)
from .identifiers import is_uuid7, uuid7
from .service import DesignStore, DesignStoreConflict, DesignStoreError
from .shared_ddn import (
    DEFAULT_LOGICAL_TYPE_MAPS,
    DESTRUCTIVE_METADATA_WARNING,
    ERD_LEVELS,
    StoreDDNProcess,
    _extract_existing_layout,
    _quote_sql_ident,
    apply_layout_to_ddn_text,
    build_four_level_erd_ddn,
    compute_server_layout,
    normalize_to_logical_type,
    preview_erd_alter_plan,
)

ERD_ALTER_REVIEW_ADAPTER_ID = 'erd.alter_review'

DEFAULT_NAMING_RULES: dict[str, str] = {
    'table_case': 'snake_case',
    'column_case': 'snake_case',
    'pk_pattern': 'pk_{table}',
    'fk_pattern': 'fk_{table}_{ref}',
    'ix_pattern': 'ix_{table}_{cols}',
}

DEFAULT_ENVIRONMENTS: tuple[dict[str, str], ...] = (
    {
        'environment': 'dev',
        'label': 'Development',
        'endpoint_id': 'env-dev',
        'database_target_id': 'dev_db',
    },
    {
        'environment': 'staging',
        'label': 'Staging',
        'endpoint_id': 'env-staging',
        'database_target_id': 'staging_db',
    },
    {
        'environment': 'prod',
        'label': 'Production',
        'endpoint_id': 'env-prod',
        'database_target_id': 'prod_db',
    },
)

_FALLBACK_OPERATION_BUS = None


# ---------------------------------------------------------------------------
# String / identifier / naming helpers
# ---------------------------------------------------------------------------


def _slug_key(text: str, default: str = 'erd-model') -> str:
    cleaned = re.sub(r'[^a-z0-9]+', '-', str(text or '').lower()).strip('-')
    return (cleaned[:56] or default).strip('-') or default


def _to_snake_case(name: str) -> str:
    s = str(name or '').strip()
    if not s:
        return 'item'
    s = re.sub(r'[\s\-./]+', '_', s)
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s)
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', s)
    s = re.sub(r'[^A-Za-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_').lower()
    return s or 'item'


def _to_pascal_case(name: str) -> str:
    parts = [p for p in _to_snake_case(name).split('_') if p]
    return ''.join(p[:1].upper() + p[1:] for p in parts) or 'Item'


def _to_camel_case(name: str) -> str:
    pascal = _to_pascal_case(name)
    return pascal[:1].lower() + pascal[1:] if pascal else 'item'


def _apply_case_rule(name: str, case_style: str) -> str:
    style = (case_style or 'snake_case').strip()
    if style == 'UPPER_SNAKE_CASE':
        return _to_snake_case(name).upper()
    if style == 'PascalCase':
        return _to_pascal_case(name)
    if style == 'camelCase':
        return _to_camel_case(name)
    return _to_snake_case(name)


def _matches_case_rule(name: str, case_style: str) -> bool:
    if not name:
        return True
    return name == _apply_case_rule(name, case_style)


def _singularize(word: str) -> str:
    w = _to_snake_case(word)
    if w.endswith('ies') and len(w) > 4:
        return w[:-3] + 'y'
    if w.endswith(('ses', 'xes', 'zes', 'ches', 'shes')) and len(w) > 4:
        return w[:-2]
    if w.endswith('s') and not w.endswith(('ss', 'us', 'is')) and len(w) > 2:
        return w[:-1]
    return w


def _pluralize(word: str) -> str:
    w = _singularize(word)
    if w.endswith('y') and len(w) > 1 and w[-2] not in 'aeiou':
        return w[:-1] + 'ies'
    if w.endswith(('s', 'x', 'z', 'ch', 'sh')):
        return w + 'es'
    return w + 's'


def _unquote_ident(raw: str) -> str:
    s = str(raw or '').strip()
    if len(s) >= 2 and (
        (s[0] == '"' and s[-1] == '"')
        or (s[0] == '`' and s[-1] == '`')
        or (s[0] == "'" and s[-1] == "'")
        or (s[0] == '[' and s[-1] == ']')
    ):
        inner = s[1:-1]
        if s[0] == '"':
            return inner.replace('""', '"')
        if s[0] == '`':
            return inner.replace('``', '`')
        return inner
    return s


def _split_qualified_name(raw: str) -> tuple[str | None, str]:
    s = str(raw or '').strip()
    if not s:
        return None, 'unnamed'
    # Split outside quotes
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            elif quote == '[' and ch == ']':
                quote = None
        else:
            if ch in ('"', '`', "'", '['):
                quote = ch
                buf.append(ch)
            elif ch == '.':
                parts.append(''.join(buf).strip())
                buf = []
            else:
                buf.append(ch)
    parts.append(''.join(buf).strip())
    cleaned = [_unquote_ident(p) for p in parts if p]
    if not cleaned:
        return None, 'unnamed'
    if len(cleaned) == 1:
        return None, cleaned[0]
    return cleaned[-2], cleaned[-1]


# ---------------------------------------------------------------------------
# Clean-room SQL DDL & DBML parsers (SR-F-030015)
# ---------------------------------------------------------------------------


def _strip_sql_comments(sql: str) -> str:
    out: list[str] = []
    i = 0
    n = len(sql)
    quote: str | None = None
    while i < n:
        ch = sql[i]
        if quote:
            out.append(ch)
            if ch == quote:
                if i + 1 < n and sql[i + 1] == quote:
                    out.append(sql[i + 1])
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in ("'", '"', '`'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == '-' and i + 1 < n and sql[i + 1] == '-':
            while i < n and sql[i] != '\n':
                i += 1
            continue
        if ch == '/' and i + 1 < n and sql[i + 1] == '*':
            i += 2
            while i + 1 < n and not (sql[i] == '*' and sql[i + 1] == '/'):
                if sql[i] == '\n':
                    out.append('\n')
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def _split_top_level(text: str, delimiter: str = ';') -> list[str]:
    items: list[str] = []
    buf: list[str] = []
    depth = 0
    quote: str | None = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote:
            buf.append(ch)
            if (quote == '[' and ch == ']') or (quote != '[' and ch == quote):
                if quote != '[' and i + 1 < n and text[i + 1] == quote:
                    buf.append(text[i + 1])
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in ("'", '"', '`', '['):
            quote = ch
            buf.append(ch)
        elif ch == '(':
            depth += 1
            buf.append(ch)
        elif ch == ')':
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == delimiter and depth == 0:
            piece = ''.join(buf).strip()
            if piece:
                items.append(piece)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = ''.join(buf).strip()
    if tail:
        items.append(tail)
    return items


def _parse_ident_list(paren_expr: str) -> list[str]:
    inner = paren_expr.strip()
    if inner.startswith('(') and inner.endswith(')'):
        inner = inner[1:-1]
    cols: list[str] = []
    for raw in _split_top_level(inner, ','):
        tok = raw.strip().split()[0] if raw.strip() else ''
        if tok:
            cols.append(_unquote_ident(tok))
    return cols


def parse_sql_ddl_cleanroom(
    sql_text: str, *, default_engine: str = 'postgresql'
) -> dict[str, Any]:
    """Clean-room parser for SQL DDL (.sql) schemas.

    Extracts CREATE TABLE (columns, data types, PK, NOT NULL, DEFAULT, UNIQUE,
    inline and table-level FOREIGN KEY), ALTER TABLE ... ADD CONSTRAINT ...
    FOREIGN KEY / PRIMARY KEY, and CREATE [UNIQUE] INDEX, while recording
    unsupported clauses (CHECK, TRIGGER, VIEW, PROCEDURE) in loss_items.
    """
    cleaned = _strip_sql_comments(str(sql_text or ''))
    statements = _split_top_level(cleaned, ';')
    tables_by_key: dict[str, dict[str, Any]] = {}
    loss_items: list[dict[str, Any]] = []

    def _ensure_table(raw_name: str) -> dict[str, Any]:
        schema, tname = _split_qualified_name(raw_name)
        lookup = tname.lower()
        if lookup not in tables_by_key:
            tables_by_key[lookup] = {
                'id': uuid7(),
                'name': tname,
                'schema': schema or 'public',
                'engine': default_engine,
                'fields': [],
                'indexes': [],
                'foreign_keys': [],
                'pk_constraint_name': None,
            }
        return tables_by_key[lookup]

    create_table_re = re.compile(
        r'^\s*CREATE\s+(?:(?:GLOBAL|LOCAL)\s+)?(?:TEMP(?:ORARY)?\s+)?'
        r'TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)\s*\((.*)\)',
        re.IGNORECASE | re.DOTALL,
    )
    create_index_re = re.compile(
        r'^\s*CREATE\s+(UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?'
        r'(?:IF\s+NOT\s+EXISTS\s+)?([^\s]+)\s+ON\s+(?:ONLY\s+)?([^\s(]+)'
        r'(?:\s+USING\s+[A-Za-z0-9_]+)?\s*(\([^)]*\))',
        re.IGNORECASE | re.DOTALL,
    )
    alter_table_re = re.compile(
        r'^\s*ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?([^\s]+)\s+(.*)$',
        re.IGNORECASE | re.DOTALL,
    )
    fk_clause_re = re.compile(
        r'^(?:CONSTRAINT\s+([^\s]+)\s+)?FOREIGN\s+KEY\s*(\([^)]*\))\s*'
        r'REFERENCES\s+([^\s(]+)\s*(\([^)]*\))?(.*)$',
        re.IGNORECASE | re.DOTALL,
    )
    pk_clause_re = re.compile(
        r'^(?:CONSTRAINT\s+([^\s]+)\s+)?PRIMARY\s+KEY\s*(\([^)]*\))',
        re.IGNORECASE | re.DOTALL,
    )
    uq_clause_re = re.compile(
        r'^(?:CONSTRAINT\s+([^\s]+)\s+)?UNIQUE\s*(\([^)]*\))',
        re.IGNORECASE | re.DOTALL,
    )
    check_clause_re = re.compile(
        r'^(?:CONSTRAINT\s+([^\s]+)\s+)?CHECK\s*\(',
        re.IGNORECASE | re.DOTALL,
    )

    for stmt in statements:
        s_trim = stmt.strip()
        if not s_trim:
            continue

        # 1. CREATE TABLE
        m_ct = create_table_re.match(s_trim)
        if m_ct:
            raw_tname = m_ct.group(1)
            body_raw = m_ct.group(2)
            # Strip trailing ') PARTITION BY ...' if outer parens had tail
            # Find matching closing paren from start of first '(' in s_trim
            first_open = s_trim.find('(')
            depth = 0
            quote: str | None = None
            close_pos = len(s_trim) - 1
            for idx in range(first_open, len(s_trim)):
                ch = s_trim[idx]
                if quote:
                    if ch == quote:
                        quote = None
                elif ch in ("'", '"', '`'):
                    quote = ch
                elif ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        close_pos = idx
                        break
            body_str = s_trim[first_open + 1:close_pos]
            tail_str = s_trim[close_pos + 1:].strip()
            tbl = _ensure_table(raw_tname)
            if tail_str and re.search(r'\bPARTITION\s+BY\b', tail_str, re.I):
                loss_items.append({
                    'code': 'sql_partition_clause_omitted',
                    'severity': 'warning',
                    'object': tbl['name'],
                    'detail': f'Table partitioning clause ({tail_str[:80]}) recorded in loss report.',
                })

            entries = _split_top_level(body_str, ',')
            for entry in entries:
                e_str = entry.strip()
                if not e_str:
                    continue
                m_pk = pk_clause_re.match(e_str)
                if m_pk:
                    cname = _unquote_ident(m_pk.group(1)) if m_pk.group(1) else None
                    pk_cols = {c.lower() for c in _parse_ident_list(m_pk.group(2))}
                    if cname:
                        tbl['pk_constraint_name'] = cname
                    for col in tbl['fields']:
                        if col['name'].lower() in pk_cols:
                            col['pk'] = True
                            col['nullable'] = False
                    continue

                m_fk = fk_clause_re.match(e_str)
                if m_fk:
                    fk_name = _unquote_ident(m_fk.group(1)) if m_fk.group(1) else ''
                    src_cols = _parse_ident_list(m_fk.group(2))
                    _ref_schema, ref_tbl = _split_qualified_name(m_fk.group(3))
                    ref_cols = (
                        _parse_ident_list(m_fk.group(4))
                        if m_fk.group(4)
                        else ['id']
                    )
                    tail_fk = m_fk.group(5) or ''
                    on_del_m = re.search(
                        r'ON\s+DELETE\s+(CASCADE|SET\s+NULL|SET\s+DEFAULT|RESTRICT|NO\s+ACTION)',
                        tail_fk,
                        re.I,
                    )
                    on_upd_m = re.search(
                        r'ON\s+UPDATE\s+(CASCADE|SET\s+NULL|SET\s+DEFAULT|RESTRICT|NO\s+ACTION)',
                        tail_fk,
                        re.I,
                    )
                    tbl['foreign_keys'].append({
                        'id': uuid7(),
                        'name': fk_name or f"fk_{_to_snake_case(tbl['name'])}_{_to_snake_case(ref_tbl)}",
                        'columns': src_cols,
                        'ref_table': ref_tbl,
                        'ref_columns': ref_cols,
                        'on_delete': on_del_m.group(1).upper() if on_del_m else 'NO ACTION',
                        'on_update': on_upd_m.group(1).upper() if on_upd_m else 'NO ACTION',
                    })
                    for col in tbl['fields']:
                        if src_cols and col['name'].lower() == src_cols[0].lower():
                            col['references'] = f"{ref_tbl}.{ref_cols[0]}"
                    continue

                m_uq = uq_clause_re.match(e_str)
                if m_uq:
                    uq_name = _unquote_ident(m_uq.group(1)) if m_uq.group(1) else ''
                    uq_cols = _parse_ident_list(m_uq.group(2))
                    if len(uq_cols) == 1:
                        for col in tbl['fields']:
                            if col['name'].lower() == uq_cols[0].lower():
                                col['unique'] = True
                    tbl['indexes'].append({
                        'id': uuid7(),
                        'name': uq_name or f"ix_{_to_snake_case(tbl['name'])}_{'_'.join(_to_snake_case(c) for c in uq_cols)}",
                        'columns': uq_cols,
                        'unique': True,
                    })
                    continue

                if check_clause_re.match(e_str):
                    loss_items.append({
                        'code': 'sql_check_constraint_omitted',
                        'severity': 'info',
                        'object': tbl['name'],
                        'detail': f'CHECK constraint omitted from ERD diagram: {e_str[:96]}',
                    })
                    continue

                # Column definition
                col_match = re.match(
                    r'^("(?:[^"]|"")+"|`[^`]+`|\[[^\]]+\]|[A-Za-z_][A-Za-z0-9_$]*)\s+(.*)$',
                    e_str,
                    re.DOTALL,
                )
                if not col_match:
                    continue
                col_name = _unquote_ident(col_match.group(1))
                rest = col_match.group(2).strip()

                # Extract data type up to first constraint keyword at depth 0
                kw_re = re.compile(
                    r'\b(PRIMARY\s+KEY|NOT\s+NULL|NULL|UNIQUE|DEFAULT|REFERENCES|CONSTRAINT|CHECK|GENERATED|COLLATE)\b',
                    re.I,
                )
                dtype_end = len(rest)
                depth = 0
                q_ch: str | None = None
                for pos, c_ch in enumerate(rest):
                    if q_ch:
                        if c_ch == q_ch:
                            q_ch = None
                    elif c_ch in ("'", '"', '`'):
                        q_ch = c_ch
                    elif c_ch == '(':
                        depth += 1
                    elif c_ch == ')':
                        depth = max(0, depth - 1)
                    elif depth == 0:
                        m_kw = kw_re.match(rest[pos:])
                        if m_kw and (pos == 0 or rest[pos - 1].isspace() or rest[pos - 1] == ')'):
                            dtype_end = pos
                            break

                raw_dtype = rest[:dtype_end].strip() or 'TEXT'
                modifiers = rest[dtype_end:].strip()
                is_pk = bool(re.search(r'\bPRIMARY\s+KEY\b', modifiers, re.I))
                not_null = is_pk or bool(re.search(r'\bNOT\s+NULL\b', modifiers, re.I))
                is_unique = bool(re.search(r'\bUNIQUE\b', modifiers, re.I))

                default_val = ''
                def_m = re.search(
                    r'\bDEFAULT\s+((?:\'[^\']*\'|"[^"]*"|\([^)]*\)|[^\s,]+))',
                    modifiers,
                    re.I,
                )
                if def_m:
                    default_val = def_m.group(1).strip()

                ref_target = ''
                inl_ref = re.search(
                    r'\bREFERENCES\s+([^\s(]+)\s*(?:\(([^)]*)\))?(.*)$',
                    modifiers,
                    re.I | re.DOTALL,
                )
                if inl_ref:
                    _rs, r_tbl = _split_qualified_name(inl_ref.group(1))
                    r_col = (
                        _unquote_ident(inl_ref.group(2).split(',')[0].strip())
                        if inl_ref.group(2)
                        else 'id'
                    )
                    ref_target = f'{r_tbl}.{r_col}'
                    tail_inl = inl_ref.group(3) or ''
                    od_m = re.search(
                        r'ON\s+DELETE\s+(CASCADE|SET\s+NULL|SET\s+DEFAULT|RESTRICT|NO\s+ACTION)',
                        tail_inl,
                        re.I,
                    )
                    tbl['foreign_keys'].append({
                        'id': uuid7(),
                        'name': f"fk_{_to_snake_case(tbl['name'])}_{_to_snake_case(r_tbl)}",
                        'columns': [col_name],
                        'ref_table': r_tbl,
                        'ref_columns': [r_col],
                        'on_delete': od_m.group(1).upper() if od_m else 'NO ACTION',
                        'on_update': 'NO ACTION',
                    })

                if re.search(r'\bCHECK\s*\(', modifiers, re.I):
                    loss_items.append({
                        'code': 'sql_column_check_omitted',
                        'severity': 'info',
                        'object': f"{tbl['name']}.{col_name}",
                        'detail': 'Column CHECK expression recorded in loss report.',
                    })

                tbl['fields'].append({
                    'id': uuid7(),
                    'name': col_name,
                    'datatype': raw_dtype,
                    'nullable': not not_null,
                    'pk': is_pk,
                    'unique': is_unique,
                    'default': default_val,
                    'references': ref_target,
                })
            continue

        # 2. CREATE [UNIQUE] INDEX
        m_ix = create_index_re.match(s_trim)
        if m_ix:
            is_uq = bool(m_ix.group(1))
            ix_name = _unquote_ident(m_ix.group(2))
            tbl = _ensure_table(m_ix.group(3))
            ix_cols = _parse_ident_list(m_ix.group(4))
            tbl['indexes'].append({
                'id': uuid7(),
                'name': ix_name,
                'columns': ix_cols,
                'unique': is_uq,
            })
            continue

        # 3. ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY / PRIMARY KEY
        m_alt = alter_table_re.match(s_trim)
        if m_alt:
            tbl = _ensure_table(m_alt.group(1))
            action_body = m_alt.group(2).strip()
            add_fk = re.search(
                r'ADD\s+(?:CONSTRAINT\s+([^\s]+)\s+)?FOREIGN\s+KEY\s*'
                r'(\([^)]*\))\s*REFERENCES\s+([^\s(]+)\s*(\([^)]*\))?(.*)$',
                action_body,
                re.I | re.DOTALL,
            )
            if add_fk:
                fk_name = _unquote_ident(add_fk.group(1)) if add_fk.group(1) else ''
                src_cols = _parse_ident_list(add_fk.group(2))
                _rs, ref_tbl = _split_qualified_name(add_fk.group(3))
                ref_cols = (
                    _parse_ident_list(add_fk.group(4))
                    if add_fk.group(4)
                    else ['id']
                )
                tail_fk = add_fk.group(5) or ''
                od_m = re.search(
                    r'ON\s+DELETE\s+(CASCADE|SET\s+NULL|SET\s+DEFAULT|RESTRICT|NO\s+ACTION)',
                    tail_fk,
                    re.I,
                )
                tbl['foreign_keys'].append({
                    'id': uuid7(),
                    'name': fk_name or f"fk_{_to_snake_case(tbl['name'])}_{_to_snake_case(ref_tbl)}",
                    'columns': src_cols,
                    'ref_table': ref_tbl,
                    'ref_columns': ref_cols,
                    'on_delete': od_m.group(1).upper() if od_m else 'NO ACTION',
                    'on_update': 'NO ACTION',
                })
                for col in tbl['fields']:
                    if src_cols and col['name'].lower() == src_cols[0].lower():
                        col['references'] = f"{ref_tbl}.{ref_cols[0]}"
                continue

            add_pk = re.search(
                r'ADD\s+(?:CONSTRAINT\s+([^\s]+)\s+)?PRIMARY\s+KEY\s*(\([^)]*\))',
                action_body,
                re.I | re.DOTALL,
            )
            if add_pk:
                if add_pk.group(1):
                    tbl['pk_constraint_name'] = _unquote_ident(add_pk.group(1))
                pk_cols = {c.lower() for c in _parse_ident_list(add_pk.group(2))}
                for col in tbl['fields']:
                    if col['name'].lower() in pk_cols:
                        col['pk'] = True
                        col['nullable'] = False
                continue

        # 4. Non-table DDL statements -> explicit loss report
        upper_head = ' '.join(s_trim.upper().split()[:3])
        if any(
            upper_head.startswith(prefix)
            for prefix in (
                'CREATE VIEW',
                'CREATE MATERIALIZED VIEW',
                'CREATE TRIGGER',
                'CREATE FUNCTION',
                'CREATE PROCEDURE',
                'CREATE SEQUENCE',
                'CREATE TYPE',
            )
        ):
            loss_items.append({
                'code': 'unsupported_sql_object_in_erd_import',
                'severity': 'warning',
                'object': s_trim.splitlines()[0][:64],
                'detail': f'{upper_head} is outside relational table/FK import and was omitted.',
            })

    return {
        'tables': list(tables_by_key.values()),
        'loss_items': loss_items,
    }


def parse_dbml_cleanroom(
    dbml_text: str, *, default_engine: str = 'postgresql'
) -> dict[str, Any]:
    """Clean-room parser for DBML (.dbml) schemas.

    Supports Table definitions with inline column settings [pk, not null,
    unique, default, note, ref: > other.col], table aliases, indexes blocks,
    and standalone Ref declarations.
    """
    raw = str(dbml_text or '')
    # Strip /* ... */ and // comments outside quotes
    out_chars: list[str] = []
    i = 0
    n = len(raw)
    quote: str | None = None
    while i < n:
        ch = raw[i]
        if quote:
            out_chars.append(ch)
            if ch == quote and (i == 0 or raw[i - 1] != '\\'):
                quote = None
            i += 1
            continue
        if ch in ("'", '"', '`'):
            quote = ch
            out_chars.append(ch)
            i += 1
            continue
        if ch == '/' and i + 1 < n and raw[i + 1] == '/':
            while i < n and raw[i] != '\n':
                i += 1
            continue
        if ch == '/' and i + 1 < n and raw[i + 1] == '*':
            i += 2
            while i + 1 < n and not (raw[i] == '*' and raw[i + 1] == '/'):
                if raw[i] == '\n':
                    out_chars.append('\n')
                i += 1
            i += 2
            continue
        out_chars.append(ch)
        i += 1
    cleaned = ''.join(out_chars)

    tables_by_key: dict[str, dict[str, Any]] = {}
    alias_to_key: dict[str, str] = {}
    pending_refs: list[dict[str, Any]] = []
    loss_items: list[dict[str, Any]] = []

    # Extract Table blocks with brace matching
    tbl_hdr_re = re.compile(
        r'\bTable\s+([^\s{\[]+)(?:\s+as\s+([^\s{\[]+))?(?:\s*\[[^\]]*\])?\s*\{',
        re.IGNORECASE,
    )
    pos = 0
    occupied_spans: list[tuple[int, int]] = []
    while True:
        m = tbl_hdr_re.search(cleaned, pos)
        if not m:
            break
        brace_open = m.end() - 1
        depth = 0
        q_ch: str | None = None
        brace_close = len(cleaned)
        for idx in range(brace_open, len(cleaned)):
            ch = cleaned[idx]
            if q_ch:
                if ch == q_ch and cleaned[idx - 1] != '\\':
                    q_ch = None
            elif ch in ("'", '"', '`'):
                q_ch = ch
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    brace_close = idx
                    break
        occupied_spans.append((m.start(), brace_close + 1))
        pos = brace_close + 1

        schema, tname = _split_qualified_name(m.group(1))
        alias = _unquote_ident(m.group(2)) if m.group(2) else None
        tkey = tname.lower()
        if alias:
            alias_to_key[alias.lower()] = tkey

        tbl = {
            'id': uuid7(),
            'name': tname,
            'schema': schema or 'public',
            'engine': default_engine,
            'fields': [],
            'indexes': [],
            'foreign_keys': [],
            'note': '',
        }
        tables_by_key[tkey] = tbl
        body = cleaned[brace_open + 1:brace_close]

        in_indexes = False
        idx_depth = 0
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if in_indexes:
                idx_depth += line.count('{') - line.count('}')
                if idx_depth <= 0 or line == '}':
                    in_indexes = False
                    continue
                idx_m = re.match(
                    r'^(?:\(([^)]+)\)|([^\s\[]+))(?:\s*\[([^\]]*)\])?',
                    line,
                )
                if idx_m:
                    cols_str = idx_m.group(1) or idx_m.group(2) or ''
                    cols = [
                        _unquote_ident(c.strip())
                        for c in cols_str.split(',')
                        if c.strip()
                    ]
                    opts = (idx_m.group(3) or '').lower()
                    name_m = re.search(
                        r"name\s*:\s*['\"]([^'\"]+)['\"]",
                        idx_m.group(3) or '',
                        re.I,
                    )
                    is_uq = 'unique' in opts or 'pk' in opts
                    tbl['indexes'].append({
                        'id': uuid7(),
                        'name': (
                            name_m.group(1)
                            if name_m
                            else f"ix_{_to_snake_case(tname)}_{'_'.join(_to_snake_case(c) for c in cols)}"
                        ),
                        'columns': cols,
                        'unique': is_uq,
                    })
                continue

            if re.match(r'^indexes\s*\{', line, re.I):
                in_indexes = True
                idx_depth = 1
                continue

            note_m = re.match(
                r"^Note\s*:\s*['\"](.*)['\"]\s*$", line, re.I
            )
            if note_m:
                tbl['note'] = note_m.group(1)
                continue

            col_m = re.match(
                r'^("(?:[^"]|"")+"|`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)\s+'
                r'([^\[\n]+?)(?:\s*\[([^\]]*)\])?\s*$',
                line,
            )
            if not col_m:
                continue
            cname = _unquote_ident(col_m.group(1))
            ctype = col_m.group(2).strip()
            bracket = col_m.group(3) or ''
            b_lower = bracket.lower()
            is_pk = bool(
                re.search(r'\bpk\b|\bprimary\s+key\b', b_lower)
            )
            not_null = is_pk or bool(re.search(r'\bnot\s+null\b', b_lower))
            is_unique = bool(re.search(r'\bunique\b', b_lower))
            def_m = re.search(
                r"default\s*:\s*(`[^`]*`|'[^']*'|\"[^\"]*\"|[^,\]]+)",
                bracket,
                re.I,
            )
            def_val = def_m.group(1).strip() if def_m else ''
            c_note_m = re.search(
                r"note\s*:\s*['\"]([^'\"]*)['\"]", bracket, re.I
            )
            ref_m = re.search(
                r'ref\s*:\s*([<>-]{1,2})\s*([^\s,\]]+)', bracket, re.I
            )
            if ref_m:
                op = ref_m.group(1)
                target_expr = ref_m.group(2).strip()
                pending_refs.append({
                    'name': '',
                    'left_table': tname,
                    'left_col': cname,
                    'op': op,
                    'right_expr': target_expr,
                })

            tbl['fields'].append({
                'id': uuid7(),
                'name': cname,
                'datatype': ctype,
                'nullable': not not_null,
                'pk': is_pk,
                'unique': is_unique,
                'default': def_val,
                'references': '',
                'description': c_note_m.group(1) if c_note_m else '',
            })

    # Blank out table spans to scan top-level Ref / Enum / TableGroup blocks
    outside_chars = list(cleaned)
    for s_idx, e_idx in occupied_spans:
        for k in range(s_idx, min(e_idx, len(outside_chars))):
            if outside_chars[k] != '\n':
                outside_chars[k] = ' '
    outside = ''.join(outside_chars)

    for enum_m in re.finditer(r'\bEnum\s+([^\s{]+)\s*\{', outside, re.I):
        loss_items.append({
            'code': 'dbml_enum_mapped_to_string_check',
            'severity': 'info',
            'object': _unquote_ident(enum_m.group(1)),
            'detail': f"DBML Enum {_unquote_ident(enum_m.group(1))!r} mapped as symbolic column type.",
        })

    ref_line_re = re.compile(
        r'\bRef(?:\s+([A-Za-z0-9_"\'`]+))?\s*:\s*'
        r'([^\s<>-]+)\s*([<>-]{1,2})\s*([^\s\[\n{]+)',
        re.I,
    )
    for rm in ref_line_re.finditer(outside):
        rname = _unquote_ident(rm.group(1)) if rm.group(1) else ''
        left_expr = rm.group(2).strip()
        op = rm.group(3).strip()
        right_expr = rm.group(4).strip()
        if '.' in left_expr:
            lt, lc = left_expr.rsplit('.', 1)
            pending_refs.append({
                'name': rname,
                'left_table': _split_qualified_name(lt)[1],
                'left_col': _unquote_ident(lc),
                'op': op,
                'right_expr': right_expr,
            })

    def _resolve_tkey(raw_t: str) -> str:
        low = _unquote_ident(raw_t).lower()
        return alias_to_key.get(low, low)

    for pref in pending_refs:
        if '.' not in pref['right_expr']:
            continue
        rt_raw, rc_raw = pref['right_expr'].rsplit('.', 1)
        _, rt_clean = _split_qualified_name(rt_raw)
        rc_clean = _unquote_ident(rc_raw)

        l_key = _resolve_tkey(pref['left_table'])
        r_key = _resolve_tkey(rt_clean)
        # In DBML: `a.col > b.id` means many `a` reference one `b`;
        # `a.id < b.a_id` means `b` references `a`!
        if pref['op'] == '<':
            src_key, src_col = r_key, rc_clean
            tgt_key, tgt_col = l_key, pref['left_col']
        else:
            src_key, src_col = l_key, pref['left_col']
            tgt_key, tgt_col = r_key, rc_clean

        src_tbl = tables_by_key.get(src_key)
        tgt_tbl = tables_by_key.get(tgt_key)
        if not src_tbl or not tgt_tbl:
            loss_items.append({
                'code': 'dbml_unresolved_reference',
                'severity': 'warning',
                'object': f'{src_key}.{src_col} -> {tgt_key}.{tgt_col}',
                'detail': 'Referenced table not found in DBML document.',
            })
            continue

        fk_name = (
            pref['name']
            or f"fk_{_to_snake_case(src_tbl['name'])}_{_to_snake_case(tgt_tbl['name'])}"
        )
        src_tbl['foreign_keys'].append({
            'id': uuid7(),
            'name': fk_name,
            'columns': [src_col],
            'ref_table': tgt_tbl['name'],
            'ref_columns': [tgt_col],
            'on_delete': 'NO ACTION',
            'on_update': 'NO ACTION',
        })
        for col in src_tbl['fields']:
            if col['name'].lower() == src_col.lower():
                col['references'] = f"{tgt_tbl['name']}.{tgt_col}"

    return {
        'tables': list(tables_by_key.values()),
        'loss_items': loss_items,
    }


def _introspect_catalog_tables(
    payload: Mapping[str, Any], *, default_engine: str = 'sqlite'
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read physical tables from supplied snapshot or live SQLite/DuckDB file."""
    loss_items: list[dict[str, Any]] = []
    supplied = payload.get('tables')
    if isinstance(supplied, list) and supplied:
        tables: list[dict[str, Any]] = []
        for raw_t in supplied:
            if not isinstance(raw_t, Mapping):
                continue
            tname = str(raw_t.get('name') or 'unnamed_table')
            cols_in = raw_t.get('columns') or raw_t.get('fields') or []
            fields: list[dict[str, Any]] = []
            fks: list[dict[str, Any]] = []
            for col in cols_in:
                if not isinstance(col, Mapping):
                    continue
                cname = str(col.get('name') or 'col')
                ref_str = str(col.get('references') or '')
                fields.append({
                    'id': col.get('id') if is_uuid7(col.get('id')) else uuid7(),
                    'name': cname,
                    'datatype': str(
                        col.get('datatype') or col.get('type') or 'TEXT'
                    ),
                    'nullable': bool(col.get('nullable', not col.get('pk', False))),
                    'pk': bool(col.get('pk', False)),
                    'unique': bool(col.get('unique', False)),
                    'default': str(col.get('default') or ''),
                    'references': ref_str,
                })
                if ref_str and '.' in ref_str:
                    rt, rc = ref_str.split('.', 1)
                    fks.append({
                        'id': uuid7(),
                        'name': f'fk_{_to_snake_case(tname)}_{_to_snake_case(rt)}',
                        'columns': [cname],
                        'ref_table': rt,
                        'ref_columns': [rc],
                        'on_delete': 'NO ACTION',
                        'on_update': 'NO ACTION',
                    })
            for fk in raw_t.get('foreign_keys') or []:
                if isinstance(fk, Mapping) and fk.get('ref_table'):
                    fks.append({
                        'id': uuid7(),
                        'name': str(
                            fk.get('name')
                            or f"fk_{_to_snake_case(tname)}_{_to_snake_case(str(fk['ref_table']))}"
                        ),
                        'columns': list(fk.get('columns') or []),
                        'ref_table': str(fk['ref_table']),
                        'ref_columns': list(fk.get('ref_columns') or ['id']),
                        'on_delete': str(fk.get('on_delete') or 'NO ACTION'),
                        'on_update': str(fk.get('on_update') or 'NO ACTION'),
                    })
            tables.append({
                'id': raw_t.get('id') if is_uuid7(raw_t.get('id')) else uuid7(),
                'name': tname,
                'schema': str(raw_t.get('schema') or 'main'),
                'engine': str(raw_t.get('engine') or default_engine),
                'resource_id': raw_t.get('resource_id')
                or f'{default_engine}:table:main.{tname}',
                'uid': raw_t.get('uid')
                or f"{default_engine}:{payload.get('endpoint_id') or 'local'}:main:{tname}",
                'fields': fields,
                'indexes': list(raw_t.get('indexes') or []),
                'foreign_keys': fks,
            })
        return tables, loss_items

    sqlite_path = payload.get('sqlite_path') or payload.get('database_path')
    if sqlite_path and Path(str(sqlite_path)).is_file():
        ep_id = str(payload.get('endpoint_id') or 'sqlite-local')
        tables = []
        conn = sqlite3.connect(str(sqlite_path))
        try:
            t_rows = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()
            for (tname,) in t_rows:
                q_t = '"' + str(tname).replace('"', '""') + '"'
                c_rows = conn.execute(f'PRAGMA table_info({q_t})').fetchall()
                fk_rows = conn.execute(
                    f'PRAGMA foreign_key_list({q_t})'
                ).fetchall()
                ix_rows = conn.execute(f'PRAGMA index_list({q_t})').fetchall()

                fk_by_col: dict[str, tuple[str, str, str, str]] = {}
                fks = []
                for fk in fk_rows:
                    ref_table = str(fk[2])
                    from_col = str(fk[3])
                    to_col = str(fk[4] or 'id')
                    on_upd = str(fk[5] or 'NO ACTION')
                    on_del = str(fk[6] or 'NO ACTION')
                    fk_by_col[from_col] = (ref_table, to_col, on_del, on_upd)
                    fks.append({
                        'id': uuid7(),
                        'name': f'fk_{_to_snake_case(tname)}_{_to_snake_case(ref_table)}',
                        'columns': [from_col],
                        'ref_table': ref_table,
                        'ref_columns': [to_col],
                        'on_delete': on_del,
                        'on_update': on_upd,
                    })

                fields = []
                for c in c_rows:
                    cname = str(c[1])
                    ctype = str(c[2] or 'TEXT')
                    notnull = bool(c[3])
                    dflt = '' if c[4] is None else str(c[4])
                    pk = bool(c[5])
                    ref_info = fk_by_col.get(cname)
                    fields.append({
                        'id': uuid7(),
                        'name': cname,
                        'datatype': ctype,
                        'nullable': not (notnull or pk),
                        'pk': pk,
                        'unique': False,
                        'default': dflt,
                        'references': (
                            f'{ref_info[0]}.{ref_info[1]}' if ref_info else ''
                        ),
                    })

                indexes = []
                for ix in ix_rows:
                    ix_name = str(ix[1])
                    ix_uq = bool(ix[2])
                    q_ix = '"' + ix_name.replace('"', '""') + '"'
                    ic_rows = conn.execute(
                        f'PRAGMA index_info({q_ix})'
                    ).fetchall()
                    indexes.append({
                        'id': uuid7(),
                        'name': ix_name,
                        'columns': [str(ic[2]) for ic in ic_rows if ic[2]],
                        'unique': ix_uq,
                    })

                tables.append({
                    'id': uuid7(),
                    'name': str(tname),
                    'schema': 'main',
                    'engine': 'sqlite',
                    'resource_id': f'sqlite:table:main.{tname}',
                    'uid': f'sqlite:{ep_id}:main:sqlite:table:main.{tname}',
                    'fields': fields,
                    'indexes': indexes,
                    'foreign_keys': fks,
                })
        finally:
            conn.close()
        return tables, loss_items

    loss_items.append({
        'code': 'catalog_snapshot_empty',
        'severity': 'info',
        'object': str(payload.get('endpoint_id') or 'catalog'),
        'detail': 'No live catalog tables supplied; initialized empty Draft ERD.',
    })
    return [], loss_items


# ---------------------------------------------------------------------------
# 4-Level ERD State <-> DDN Serialization (0 diagnostics in ddn-next-1)
# ---------------------------------------------------------------------------


def _serialize_erd_state_to_ddn(state: Mapping[str, Any]) -> str:
    """Serialize structured 4-level ERD state into valid ddn-next-1 text."""
    title = str(state.get('title') or 'ERD Model')
    user_extensions = dict(state.get('extensions') or {})
    # Strip internal envelope key before re-embedding so it never nests
    user_extensions.pop('_erd_meta', None)

    conceptual_entities_out: list[dict[str, Any]] = []
    logical_entities_out: list[dict[str, Any]] = []
    physical_tables_out: list[dict[str, Any]] = []
    deployment_nodes_out: list[dict[str, Any]] = []

    entity_meta: dict[str, dict[str, Any]] = {}
    field_meta: dict[str, dict[str, Any]] = {}

    # 1. Conceptual entities
    conceptual_ids: set[str] = set()
    for raw_c in state.get('conceptual_entities') or []:
        if not isinstance(raw_c, Mapping):
            continue
        cid = raw_c.get('id') if is_uuid7(raw_c.get('id')) else uuid7()
        cname = str(raw_c.get('name') or raw_c.get('title') or 'Concept')
        c_fields = []
        for f in raw_c.get('fields') or []:
            if not isinstance(f, Mapping):
                continue
            fid = f.get('id') if is_uuid7(f.get('id')) else uuid7()
            c_fields.append({
                'id': fid,
                'name': str(f.get('name') or 'attribute'),
                'datatype': str(f.get('datatype') or f.get('type') or 'string'),
                'nullable': bool(f.get('nullable', True)),
            })
        conceptual_entities_out.append({
            'id': cid,
            'name': cname,
            'role': 'table',
            'fields': c_fields,
        })
        conceptual_ids.add(cid)
        entity_meta[cid] = {
            'area': str(raw_c.get('area') or ''),
            'note': str(raw_c.get('note') or ''),
        }

    # 2. Logical entities
    logical_ids: set[str] = set()
    for raw_l in state.get('logical_entities') or []:
        if not isinstance(raw_l, Mapping):
            continue
        lid = raw_l.get('id') if is_uuid7(raw_l.get('id')) else uuid7()
        lname = str(raw_l.get('name') or raw_l.get('title') or 'Entity')
        raw_attrs = (
            raw_l.get('fields')
            if raw_l.get('fields') is not None
            else (raw_l.get('attributes') or [])
        )
        l_fields = []
        for f in raw_attrs:
            if not isinstance(f, Mapping):
                continue
            fid = f.get('id') if is_uuid7(f.get('id')) else uuid7()
            fname = str(f.get('name') or 'attribute')
            dtype = str(f.get('datatype') or f.get('type') or 'string')
            is_pk = bool(f.get('pk', False))
            nullable = False if is_pk else bool(f.get('nullable', True))
            l_fields.append({
                'id': fid,
                'name': fname,
                'datatype': dtype,
                'nullable': nullable,
            })
            field_meta[fid] = {
                'pk': is_pk,
                'description': str(f.get('description') or ''),
            }
        logical_entities_out.append({
            'id': lid,
            'name': lname,
            'role': 'table',
            'fields': l_fields,
        })
        logical_ids.add(lid)
        entity_meta[lid] = {
            'area': str(raw_l.get('area') or ''),
            'note': str(raw_l.get('note') or ''),
        }

    # 3. Physical tables
    physical_ids: set[str] = set()
    phys_id_by_lower_name: dict[str, str] = {}
    for raw_p in state.get('physical_tables') or []:
        if not isinstance(raw_p, Mapping):
            continue
        pid = raw_p.get('id') if is_uuid7(raw_p.get('id')) else uuid7()
        pname = str(raw_p.get('name') or raw_p.get('title') or 'table_1')
        raw_cols = (
            raw_p.get('fields')
            if raw_p.get('fields') is not None
            else (raw_p.get('columns') or [])
        )
        p_fields = []
        for col in raw_cols:
            if not isinstance(col, Mapping):
                continue
            fid = col.get('id') if is_uuid7(col.get('id')) else uuid7()
            cname = str(col.get('name') or 'id')
            dtype = str(col.get('datatype') or col.get('type') or 'TEXT')
            is_pk = bool(col.get('pk', False))
            nullable = False if is_pk else bool(col.get('nullable', True))
            p_fields.append({
                'id': fid,
                'name': cname,
                'datatype': dtype,
                'nullable': nullable,
            })
            field_meta[fid] = {
                'pk': is_pk,
                'unique': bool(col.get('unique', False)),
                'default': str(col.get('default') or ''),
                'references': str(col.get('references') or ''),
            }
        p_entry: dict[str, Any] = {
            'id': pid,
            'name': pname,
            'role': 'table',
            'engine': str(raw_p.get('engine') or 'sqlite'),
            'fields': p_fields,
        }
        if raw_p.get('resource_id'):
            p_entry['resource_id'] = str(raw_p['resource_id'])
        if raw_p.get('uid'):
            p_entry['uid'] = str(raw_p['uid'])
        physical_tables_out.append(p_entry)
        physical_ids.add(pid)
        phys_id_by_lower_name[pname.lower()] = pid
        entity_meta[pid] = {
            'schema': str(raw_p.get('schema') or 'public'),
            'indexes': list(raw_p.get('indexes') or []),
            'foreign_keys': list(raw_p.get('foreign_keys') or []),
            'pk_constraint_name': raw_p.get('pk_constraint_name'),
        }

    # 4. Deployment nodes (keep DDN element role == 'table' for ddn-next-1)
    deployment_ids: set[str] = set()
    for raw_d in state.get('deployment_nodes') or []:
        if not isinstance(raw_d, Mapping):
            continue
        did = raw_d.get('id') if is_uuid7(raw_d.get('id')) else uuid7()
        dname = str(raw_d.get('name') or raw_d.get('title') or 'db-node')
        node_role = str(
            raw_d.get('node_role')
            or (
                raw_d.get('role')
                if raw_d.get('role') not in (None, '', 'table')
                else 'primary'
            )
        )
        location = str(
            raw_d.get('location') or raw_d.get('cloud_region') or ''
        )
        d_entry: dict[str, Any] = {
            'id': did,
            'name': dname,
            'role': 'table',
            'engine': str(raw_d.get('engine') or 'postgresql'),
            'host': str(raw_d.get('host') or ''),
            'rack': str(raw_d.get('rack') or ''),
            'cloud_region': location,
            'instance_type': str(raw_d.get('instance_type') or ''),
            'resource_id': str(
                raw_d.get('resource_id') or f'host:{_slug_key(dname, "node")}'
            ),
            'fields': [],
        }
        deployment_nodes_out.append(d_entry)
        deployment_ids.add(did)
        entity_meta[did] = {
            'endpoint_id': str(raw_d.get('endpoint_id') or ''),
            'location': location,
            'node_role': node_role,
            'tables': list(raw_d.get('tables') or []),
        }

    # 5. Merge all level links + intra-level relations + inferred physical FK edges
    all_valid_ids = (
        conceptual_ids | logical_ids | physical_ids | deployment_ids
    )
    merged_links: list[dict[str, str]] = []
    seen_link_ids: set[str] = set()
    seen_link_sigs: set[tuple[str, str, str]] = set()

    def _add_link(raw_lnk: Mapping[str, Any], default_kind: str) -> None:
        src = str(raw_lnk.get('source') or '')
        tgt = str(raw_lnk.get('target') or '')
        if src not in all_valid_ids or tgt not in all_valid_ids:
            return
        raw_id = raw_lnk.get('id')
        if raw_id and raw_id in seen_link_ids:
            return
        kind = str(raw_lnk.get('kind') or default_kind)
        sig = (src, tgt, kind)
        if sig in seen_link_sigs:
            return
        seen_link_sigs.add(sig)
        lid = raw_id if is_uuid7(raw_id) else uuid7()
        while lid in seen_link_ids or lid in all_valid_ids:
            lid = uuid7()
        seen_link_ids.add(lid)
        merged_links.append({
            'id': lid,
            'source': src,
            'target': tgt,
            'kind': kind,
            'title': str(raw_lnk.get('title') or f'{src} -> {tgt}'),
        })

    for rel in state.get('conceptual_relations') or []:
        if isinstance(rel, Mapping):
            _add_link(rel, 'conceptual_rel')
    for rel in state.get('logical_relations') or []:
        if isinstance(rel, Mapping):
            _add_link(rel, 'logical_rel')
    for rel in state.get('deployment_links') or []:
        if isinstance(rel, Mapping):
            _add_link(rel, 'replication')
    for rel in state.get('level_links') or []:
        if isinstance(rel, Mapping):
            _add_link(rel, str(rel.get('kind') or 'traces_to'))

    # Ensure physical foreign_keys / column references have physical edges
    for p_entry in physical_tables_out:
        pid = p_entry['id']
        p_meta = entity_meta.get(pid, {})
        for fk in p_meta.get('foreign_keys') or []:
            if not isinstance(fk, Mapping):
                continue
            ref_t = str(fk.get('ref_table') or '').lower()
            tgt_pid = phys_id_by_lower_name.get(ref_t)
            if tgt_pid and (pid, tgt_pid, 'foreign_key') not in seen_link_sigs:
                fk_id = fk.get('id') if is_uuid7(fk.get('id')) else uuid7()
                _add_link(
                    {
                        'id': fk_id,
                        'source': pid,
                        'target': tgt_pid,
                        'kind': 'foreign_key',
                        'title': str(
                            fk.get('name')
                            or f"fk_{_to_snake_case(p_entry['name'])}_{_to_snake_case(ref_t)}"
                        ),
                    },
                    'foreign_key',
                )
        for col in p_entry.get('fields') or []:
            f_m = field_meta.get(col['id'], {})
            ref_s = str(f_m.get('references') or '')
            if '.' in ref_s:
                rt = ref_s.split('.', 1)[0].strip().lower()
                tgt_pid = phys_id_by_lower_name.get(rt)
                if tgt_pid and (pid, tgt_pid, 'foreign_key') not in seen_link_sigs:
                    _add_link(
                        {
                            'source': pid,
                            'target': tgt_pid,
                            'kind': 'foreign_key',
                            'title': f"fk_{_to_snake_case(p_entry['name'])}_{_to_snake_case(rt)}",
                        },
                        'foreign_key',
                    )

    # Conceptual notes normalized with stable ids
    notes_out: list[dict[str, Any]] = []
    for n_item in state.get('conceptual_notes') or []:
        if isinstance(n_item, Mapping):
            notes_out.append({
                'id': n_item.get('id')
                if is_uuid7(n_item.get('id'))
                else uuid7(),
                'title': str(n_item.get('title') or 'Note'),
                'body': str(n_item.get('body') or n_item.get('text') or ''),
                'area': str(n_item.get('area') or ''),
                'target_id': str(n_item.get('target_id') or ''),
            })

    erd_meta = {
        'look_handdrawn': bool(state.get('look_handdrawn', False)),
        'conceptual_notes': notes_out,
        'entity_meta': entity_meta,
        'field_meta': field_meta,
    }
    full_extensions = {
        **user_extensions,
        '_erd_meta': erd_meta,
    }

    ddn_text = build_four_level_erd_ddn(
        title=title,
        conceptual_entities=conceptual_entities_out,
        logical_entities=logical_entities_out,
        physical_tables=physical_tables_out,
        deployment_nodes=deployment_nodes_out,
        level_links=merged_links,
        extensions=full_extensions,
    )
    # Companion model-level x_record guarantees extensions & look_handdrawn
    # round-trip even when all four entity lists are empty.
    root_ann = ddn.annotation(
        'erd_model_root',
        title,
        'erd:model:root',
        {
            'subject_kind': 'model',
            'extensions_json': json.dumps(full_extensions, sort_keys=True),
        },
        'scratchrobin.erd.model',
    )
    return ddn_text.rstrip() + '\n\n' + root_ann


def _parse_ddn_into_erd_state(
    ddn_text: str, *, default_title: str = 'ERD Model'
) -> dict[str, Any]:
    """Parse any ERD DDN document (4-level or catalog physical) into state."""
    if not ddn_text or not ddn_text.strip():
        return {
            'title': default_title,
            'look_handdrawn': False,
            'conceptual_entities': [],
            'conceptual_relations': [],
            'conceptual_notes': [],
            'logical_entities': [],
            'logical_relations': [],
            'physical_tables': [],
            'deployment_nodes': [],
            'deployment_links': [],
            'level_links': [],
            'extensions': {},
        }

    blocks = _parse_blocks(ddn_text)
    annotations: dict[str, dict[str, Any]] = {}
    raw_extensions: dict[str, Any] = {}

    for block in blocks:
        x_rec = _extract_x_record(block)
        if x_rec is not None:
            rec = x_rec.get('record') or {}
            sid = rec.get('subject_id')
            if sid:
                annotations[sid] = {**rec, '_uid': x_rec.get('uid')}
            ext_str = rec.get('extensions_json')
            if ext_str and not raw_extensions:
                try:
                    loaded_ext = json.loads(ext_str)
                    if isinstance(loaded_ext, dict):
                        raw_extensions = loaded_ext
                except ValueError:
                    pass

    erd_meta = (
        raw_extensions.get('_erd_meta')
        if isinstance(raw_extensions.get('_erd_meta'), dict)
        else {}
    )
    user_extensions = {
        k: v for k, v in raw_extensions.items() if k != '_erd_meta'
    }
    entity_meta = erd_meta.get('entity_meta') or {}
    field_meta = erd_meta.get('field_meta') or {}
    look_handdrawn = bool(
        erd_meta.get(
            'look_handdrawn', user_extensions.get('look_handdrawn', False)
        )
    )
    conceptual_notes = list(erd_meta.get('conceptual_notes') or [])

    fields_by_id: dict[str, dict[str, Any]] = {}
    for block in blocks:
        if block['kind'] == 'element' and block['role'] == 'field':
            fid = block['id']
            body = block['body']
            dt_m = re.search(
                r'^\s+datatype\s+"((?:[^"]|"")*)"\s*$', body, re.MULTILINE
            )
            nl_m = re.search(
                r'^\s+nullable\s+(true|false)\s*$', body, re.MULTILINE
            )
            ann = annotations.get(fid, {})
            fm = field_meta.get(fid) or {}
            fields_by_id[fid] = {
                'id': fid,
                'name': block['title'],
                'datatype': (
                    dt_m.group(1).replace('""', '"') if dt_m else 'string'
                ),
                'nullable': nl_m.group(1) == 'true' if nl_m else True,
                'parent_id': ann.get('parent_id'),
                'modelling_level': ann.get('modelling_level'),
                'pk': bool(fm.get('pk', False)),
                'unique': bool(fm.get('unique', False)),
                'default': str(fm.get('default') or ''),
                'references': str(fm.get('references') or ''),
                'description': str(fm.get('description') or ''),
            }

    conceptual_entities: list[dict[str, Any]] = []
    logical_entities: list[dict[str, Any]] = []
    physical_tables: list[dict[str, Any]] = []
    deployment_nodes: list[dict[str, Any]] = []
    level_by_node_id: dict[str, str] = {}

    for block in blocks:
        if block['kind'] != 'element' or block['role'] in (
            'record',
            'field',
            'index',
            'constraint',
        ):
            continue
        eid = block['id']
        ann = annotations.get(eid, {})
        lvl = ann.get('modelling_level') or 'physical'
        if lvl not in ERD_LEVELS:
            lvl = 'physical'
        level_by_node_id[eid] = lvl

        member_ids = [
            m.group(1).replace('""', '"')
            for m in re.finditer(
                r'item\s*\n\s+id\s+"((?:[^"]|"")*)"',
                block['body'],
                re.MULTILINE,
            )
        ]
        child_fields = [
            fields_by_id[mid] for mid in member_ids if mid in fields_by_id
        ]
        # Include any fields referencing parent_id not listed in members
        seen_fids = {f['id'] for f in child_fields}
        for fid, fobj in fields_by_id.items():
            if fobj.get('parent_id') == eid and fid not in seen_fids:
                child_fields.append(fobj)

        em = entity_meta.get(eid) or {}
        if lvl == 'conceptual':
            conceptual_entities.append({
                'id': eid,
                'name': block['title'],
                'area': str(em.get('area') or ''),
                'note': str(em.get('note') or ''),
                'fields': child_fields,
            })
        elif lvl == 'logical':
            logical_entities.append({
                'id': eid,
                'name': block['title'],
                'area': str(em.get('area') or ''),
                'note': str(em.get('note') or ''),
                'fields': child_fields,
            })
        elif lvl == 'deployment':
            node_role = str(em.get('node_role') or 'primary')
            location = str(
                em.get('location') or ann.get('cloud_region') or ''
            )
            deployment_nodes.append({
                'id': eid,
                'name': block['title'],
                'engine': str(ann.get('engine') or 'postgresql'),
                'endpoint_id': str(em.get('endpoint_id') or ''),
                'location': location,
                'host': str(ann.get('host') or ''),
                'rack': str(ann.get('rack') or ''),
                'cloud_region': str(ann.get('cloud_region') or location),
                'instance_type': str(ann.get('instance_type') or ''),
                'resource_id': str(ann.get('resource_id') or ''),
                'role': node_role,
                'node_role': node_role,
                'tables': list(em.get('tables') or []),
            })
        else:
            physical_tables.append({
                'id': eid,
                'name': block['title'],
                'schema': str(em.get('schema') or 'public'),
                'engine': str(ann.get('engine') or 'sqlite'),
                'resource_id': ann.get('resource_id'),
                'uid': ann.get('_uid'),
                'fields': child_fields,
                'columns': child_fields,
                'indexes': list(em.get('indexes') or []),
                'foreign_keys': list(em.get('foreign_keys') or []),
                'pk_constraint_name': em.get('pk_constraint_name'),
            })

    # Extract catalog index/constraint elements if imported from provider ERD
    phys_by_id = {t['id']: t for t in physical_tables}
    for block in blocks:
        if block['kind'] == 'element' and block['role'] == 'index':
            ann = annotations.get(block['id'], {})
            pid = ann.get('parent_id')
            if pid in phys_by_id:
                existing_names = {
                    ix['name'] for ix in phys_by_id[pid]['indexes']
                }
                if block['title'] not in existing_names:
                    phys_by_id[pid]['indexes'].append({
                        'id': block['id'],
                        'name': block['title'],
                        'columns': [],
                        'unique': False,
                    })

    level_links: list[dict[str, Any]] = []
    conceptual_relations: list[dict[str, Any]] = []
    logical_relations: list[dict[str, Any]] = []
    deployment_links: list[dict[str, Any]] = []

    for block in blocks:
        if block['kind'] != 'relation':
            continue
        rid = block['id']
        eps = [
            m.group(1).replace('""', '"')
            for m in re.finditer(
                r'definition\s*\n\s+id\s+"((?:[^"]|"")*)"',
                block['body'],
                re.MULTILINE,
            )
        ]
        if len(eps) < 2:
            continue
        ann = annotations.get(rid, {})
        lkind = str(ann.get('link_kind') or 'foreign_key')
        link_obj = {
            'id': rid,
            'source': eps[0],
            'target': eps[1],
            'title': block['title'],
            'kind': lkind,
        }
        level_links.append(link_obj)
        src_lvl = level_by_node_id.get(eps[0])
        tgt_lvl = level_by_node_id.get(eps[1])
        if src_lvl == 'conceptual' and tgt_lvl == 'conceptual':
            conceptual_relations.append(link_obj)
        elif src_lvl == 'logical' and tgt_lvl == 'logical':
            logical_relations.append(link_obj)
        elif src_lvl == 'deployment' and tgt_lvl == 'deployment':
            deployment_links.append(link_obj)

    return {
        'title': default_title,
        'look_handdrawn': look_handdrawn,
        'conceptual_entities': conceptual_entities,
        'conceptual_relations': conceptual_relations,
        'conceptual_notes': conceptual_notes,
        'logical_entities': logical_entities,
        'logical_relations': logical_relations,
        'physical_tables': physical_tables,
        'deployment_nodes': deployment_nodes,
        'deployment_links': deployment_links,
        'level_links': level_links,
        'extensions': user_extensions,
    }


def _save_erd_state(
    store: DesignStore,
    proc: StoreDDNProcess,
    *,
    design_id: str,
    actor_id: int,
    state: Mapping[str, Any],
    expected_head_version: int | None = None,
    pinned_positions: dict[str, dict[str, Any]] | None = None,
    status: str = 'draft',
    note: str = 'Updated ERD model',
    origin: str = 'local',
    loss_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize state, preserve existing layout pins, and save via proc."""
    current = store.get_design(design_id)
    old_blocks = _parse_blocks(current['version']['ddn_text'])
    saved_pins = {
        nid: pos
        for nid, pos in _extract_existing_layout(old_blocks).items()
        if pos.get('pinned')
    }
    if pinned_positions:
        saved_pins.update(pinned_positions)

    ddn_text = _serialize_erd_state_to_ddn(state)
    head_ver = int(expected_head_version or current['head_version'])
    active_ver = current.get('active_version')
    base_ver = active_ver if active_ver is not None else head_ver
    has_suspect = any(
        b.get('state') == 'suspect' for b in current.get('bindings', ())
    )

    return proc.save_from_ddn(
        design_id,
        expected_head_version=head_ver,
        base_version=base_ver,
        ddn_or_workspace=ddn_text,
        actor_id=actor_id,
        pinned_positions=saved_pins or None,
        status=status if status in ('draft', 'in_progress', 'in_review') else 'draft',
        note=note,
        title=str(state.get('title') or current['title']),
        origin=origin,
        loss_report=loss_report,
        allow_conflict_note=has_suspect,
    )


# ---------------------------------------------------------------------------
# Public Route Entry Point 1: import_erd_external
# ---------------------------------------------------------------------------


def import_erd_external(
    store: DesignStore,
    proc: StoreDDNProcess,
    *,
    project_id: str,
    actor_id: int,
    payload: dict[str, Any],
    app: Any = None,
) -> dict[str, Any]:
    """Import SQL DDL (.sql), DBML (.dbml) or Catalog snapshot into Draft ERD."""
    fmt = str(payload.get('format') or 'sql').strip().lower()
    if fmt not in ('sql', 'dbml', 'catalog'):
        raise DesignStoreError(
            f"Unsupported ERD import format {fmt!r}; expected 'sql', 'dbml' or 'catalog'"
        )
    target_engine = str(
        payload.get('target_engine') or payload.get('engine') or 'postgresql'
    ).lower()
    if target_engine not in DEFAULT_LOGICAL_TYPE_MAPS:
        target_engine = 'postgresql'

    title = str(payload.get('title') or '').strip()
    if not title:
        title = f'Imported {fmt.upper()} Data Model'

    raw_source = str(
        payload.get(fmt)
        or payload.get('source')
        or payload.get('content')
        or ''
    )

    if fmt == 'sql':
        if not raw_source.strip():
            raise DesignStoreError('SQL DDL source text is required for sql import')
        parsed = parse_sql_ddl_cleanroom(
            raw_source, default_engine=target_engine
        )
        physical_tables = parsed['tables']
        loss_items = parsed['loss_items']
    elif fmt == 'dbml':
        if not raw_source.strip():
            raise DesignStoreError('DBML source text is required for dbml import')
        parsed = parse_dbml_cleanroom(
            raw_source, default_engine=target_engine
        )
        physical_tables = parsed['tables']
        loss_items = parsed['loss_items']
    else:
        physical_tables, loss_items = _introspect_catalog_tables(
            payload, default_engine=target_engine
        )

    # Populate Conceptual & Logical levels bridged via refines/implements links
    conceptual_entities: list[dict[str, Any]] = []
    logical_entities: list[dict[str, Any]] = []
    level_links: list[dict[str, Any]] = []
    phys_id_by_lower: dict[str, str] = {}
    log_id_by_lower: dict[str, str] = {}
    con_id_by_lower: dict[str, str] = {}

    populate_levels = bool(payload.get('populate_all_levels', True))
    for pt in physical_tables:
        pid = pt['id']
        tname = pt['name']
        phys_id_by_lower[tname.lower()] = pid
        if populate_levels:
            cid = uuid7()
            lid = uuid7()
            con_id_by_lower[tname.lower()] = cid
            log_id_by_lower[tname.lower()] = lid
            concept_title = _to_pascal_case(_singularize(tname))
            conceptual_entities.append({
                'id': cid,
                'name': concept_title,
                'area': str(pt.get('schema') or ''),
                'note': str(pt.get('note') or ''),
                'fields': [],
            })
            logical_entities.append({
                'id': lid,
                'name': concept_title,
                'fields': [
                    {
                        'id': uuid7(),
                        'name': col['name'],
                        'datatype': normalize_to_logical_type(col['datatype']),
                        'nullable': col['nullable'],
                        'pk': bool(col.get('pk', False)),
                    }
                    for col in pt.get('fields', [])
                ],
            })
            level_links.append({
                'id': uuid7(),
                'source': lid,
                'target': cid,
                'kind': 'refines',
                'title': f'{concept_title} refines concept',
            })
            level_links.append({
                'id': uuid7(),
                'source': pid,
                'target': lid,
                'kind': 'implements',
                'title': f'{tname} implements {concept_title}',
            })

    rel_count = 0
    idx_count = sum(len(pt.get('indexes') or []) for pt in physical_tables)
    for pt in physical_tables:
        src_low = pt['name'].lower()
        for fk in pt.get('foreign_keys') or []:
            tgt_low = str(fk.get('ref_table') or '').lower()
            if tgt_low in phys_id_by_lower:
                rel_count += 1
                level_links.append({
                    'id': fk.get('id') if is_uuid7(fk.get('id')) else uuid7(),
                    'source': pt['id'],
                    'target': phys_id_by_lower[tgt_low],
                    'kind': 'foreign_key',
                    'title': str(
                        fk.get('name')
                        or f"fk_{_to_snake_case(pt['name'])}_{_to_snake_case(tgt_low)}"
                    ),
                })
                if populate_levels and src_low in log_id_by_lower and tgt_low in log_id_by_lower:
                    level_links.append({
                        'id': uuid7(),
                        'source': log_id_by_lower[src_low],
                        'target': log_id_by_lower[tgt_low],
                        'kind': 'logical_rel',
                        'title': f"{pt['name']} -> {fk['ref_table']}",
                    })
                    level_links.append({
                        'id': uuid7(),
                        'source': con_id_by_lower[src_low],
                        'target': con_id_by_lower[tgt_low],
                        'kind': 'conceptual_rel',
                        'title': 'relates to',
                    })

    state = {
        'title': title,
        'look_handdrawn': False,
        'conceptual_entities': conceptual_entities,
        'logical_entities': logical_entities,
        'physical_tables': physical_tables,
        'deployment_nodes': [],
        'level_links': level_links,
        'extensions': {'target_engine': target_engine},
    }
    raw_ddn = _serialize_erd_state_to_ddn(state)
    layout = compute_server_layout(raw_ddn, use_cache=False)
    ddn_with_layout = apply_layout_to_ddn_text(raw_ddn, layout)

    loss_report = {
        'source_format': fmt,
        'target_engine': target_engine,
        'tables_imported': len(physical_tables),
        'relationships_imported': rel_count,
        'indexes_imported': idx_count,
        'loss_count': len(loss_items),
        'items': loss_items,
    }

    requested_key = str(payload.get('key') or '').strip()
    design_key = requested_key or _slug_key(title)
    note = str(payload.get('note') or f'Imported {fmt.upper()} schema as Draft ERD')

    try:
        created = store.create_design(
            project_id=project_id,
            key=design_key,
            kind='erd',
            title=title,
            ddn_text=ddn_with_layout,
            actor_id=actor_id,
            status='draft',
            note=note,
            origin=f'import:{fmt}',
            loss_report=loss_report,
            observe_resources=(fmt == 'catalog'),
        )
    except DesignStoreConflict:
        if requested_key:
            raise
        design_key = f'{design_key}-{uuid7()[-6:]}'
        created = store.create_design(
            project_id=project_id,
            key=design_key,
            kind='erd',
            title=title,
            ddn_text=ddn_with_layout,
            actor_id=actor_id,
            status='draft',
            note=note,
            origin=f'import:{fmt}',
            loss_report=loss_report,
            observe_resources=(fmt == 'catalog'),
        )

    return {
        'design': created,
        'loss_report': loss_report,
        'summary': {
            'format': fmt,
            'tables_imported': len(physical_tables),
            'relationships_imported': rel_count,
            'indexes_imported': idx_count,
            'loss_count': len(loss_items),
        },
    }


# ---------------------------------------------------------------------------
# Public Route Entry Point 2: inspect_erd_elements
# ---------------------------------------------------------------------------


def inspect_erd_elements(
    store: DesignStore,
    *,
    design_id: str,
    version: int | None = None,
) -> dict[str, Any]:
    """Return structured 4-level ERD state for the Property Inspector & forms."""
    design = store.get_design(design_id, version=version)
    ver_obj = design['version']
    parsed = _parse_ddn_into_erd_state(
        ver_obj['ddn_text'], default_title=design['title']
    )
    return {
        'design_id': design['id'],
        'title': design['title'],
        'version': ver_obj['version'],
        'head_version': design['head_version'],
        'active_version': design['active_version'],
        'status': ver_obj['status'],
        'look_handdrawn': parsed['look_handdrawn'],
        'conceptual_entities': parsed['conceptual_entities'],
        'conceptual_relations': parsed['conceptual_relations'],
        'conceptual_notes': parsed['conceptual_notes'],
        'logical_entities': parsed['logical_entities'],
        'logical_relations': parsed['logical_relations'],
        'physical_tables': parsed['physical_tables'],
        'deployment_nodes': parsed['deployment_nodes'],
        'deployment_links': parsed['deployment_links'],
        'level_links': parsed['level_links'],
        'extensions': parsed['extensions'],
        'bindings': design.get('bindings', []),
    }


# ---------------------------------------------------------------------------
# Public Route Entry Point 3: mutate_erd_elements
# ---------------------------------------------------------------------------


def _upsert_by_id(
    items: list[dict[str, Any]], entry: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    eid = entry.get('id') if is_uuid7(entry.get('id')) else uuid7()
    normalized = {**dict(entry), 'id': eid}
    replaced = False
    out: list[dict[str, Any]] = []
    for existing in items:
        if existing.get('id') == eid:
            out.append({**existing, **normalized, 'id': eid})
            normalized = out[-1]
            replaced = True
        else:
            out.append(existing)
    if not replaced:
        out.append(normalized)
    return out, normalized


def _remove_by_id_and_prune_links(
    state: dict[str, Any], list_key: str, target_id: str
) -> None:
    state[list_key] = [
        item for item in state.get(list_key, []) if item.get('id') != target_id
    ]
    for rel_key in (
        'conceptual_relations',
        'logical_relations',
        'deployment_links',
        'level_links',
    ):
        state[rel_key] = [
            lnk
            for lnk in state.get(rel_key, [])
            if lnk.get('source') != target_id and lnk.get('target') != target_id
        ]


def mutate_erd_elements(
    store: DesignStore,
    proc: StoreDDNProcess,
    *,
    design_id: str,
    actor_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Mutate 4-level ERD elements/relations via full arrays or incremental ops."""
    state = inspect_erd_elements(
        store, design_id=design_id, version=payload.get('version')
    )

    if 'title' in payload and payload['title']:
        state['title'] = str(payload['title']).strip()
    if 'look_handdrawn' in payload:
        state['look_handdrawn'] = bool(payload['look_handdrawn'])

    for key in (
        'conceptual_entities',
        'conceptual_relations',
        'conceptual_notes',
        'logical_entities',
        'logical_relations',
        'physical_tables',
        'deployment_nodes',
        'deployment_links',
        'level_links',
    ):
        if key in payload and isinstance(payload[key], list):
            state[key] = copy.deepcopy(payload[key])

    if 'extensions' in payload and isinstance(payload['extensions'], Mapping):
        state['extensions'] = {
            **state.get('extensions', {}),
            **dict(payload['extensions']),
        }

    op = str(payload.get('operation') or '').strip()
    item_data = (
        payload.get('item')
        or payload.get('entity')
        or payload.get('table')
        or payload.get('node')
        or payload.get('note_item')
        or payload
    )

    if op == 'set_sketch_look':
        state['look_handdrawn'] = bool(payload.get('look_handdrawn', True))
    elif op == 'upsert_conceptual':
        state['conceptual_entities'], _ = _upsert_by_id(
            state['conceptual_entities'], item_data
        )
    elif op == 'delete_conceptual':
        tid = str(payload.get('id') or payload.get('element_id') or '')
        _remove_by_id_and_prune_links(state, 'conceptual_entities', tid)
    elif op in ('connect_conceptual', 'upsert_conceptual_relation'):
        rel_obj = payload.get('relation') or item_data
        state['conceptual_relations'], created_rel = _upsert_by_id(
            state['conceptual_relations'],
            {
                'id': rel_obj.get('id'),
                'source': rel_obj.get('source'),
                'target': rel_obj.get('target'),
                'title': rel_obj.get('title') or 'relates to',
                'kind': rel_obj.get('kind') or 'conceptual_rel',
            },
        )
        state['level_links'], _ = _upsert_by_id(
            state['level_links'], created_rel
        )
    elif op == 'delete_conceptual_relation':
        rid = str(payload.get('id') or payload.get('relation_id') or '')
        state['conceptual_relations'] = [
            r for r in state['conceptual_relations'] if r.get('id') != rid
        ]
        state['level_links'] = [
            r for r in state['level_links'] if r.get('id') != rid
        ]
    elif op == 'upsert_conceptual_note':
        state['conceptual_notes'], _ = _upsert_by_id(
            state['conceptual_notes'], item_data
        )
    elif op == 'delete_conceptual_note':
        nid = str(payload.get('id') or payload.get('note_id') or '')
        state['conceptual_notes'] = [
            n for n in state['conceptual_notes'] if n.get('id') != nid
        ]
    elif op == 'upsert_logical':
        state['logical_entities'], _ = _upsert_by_id(
            state['logical_entities'], item_data
        )
    elif op == 'delete_logical':
        tid = str(payload.get('id') or payload.get('element_id') or '')
        _remove_by_id_and_prune_links(state, 'logical_entities', tid)
    elif op == 'upsert_logical_relation':
        rel_obj = payload.get('relation') or item_data
        state['logical_relations'], created_rel = _upsert_by_id(
            state['logical_relations'],
            {
                'id': rel_obj.get('id'),
                'source': rel_obj.get('source'),
                'target': rel_obj.get('target'),
                'title': rel_obj.get('title') or 'associates',
                'kind': rel_obj.get('kind') or 'logical_rel',
            },
        )
        state['level_links'], _ = _upsert_by_id(
            state['level_links'], created_rel
        )
    elif op == 'upsert_physical_table':
        state['physical_tables'], _ = _upsert_by_id(
            state['physical_tables'], item_data
        )
    elif op == 'delete_physical_table':
        tid = str(payload.get('id') or payload.get('element_id') or '')
        _remove_by_id_and_prune_links(state, 'physical_tables', tid)
    elif op == 'upsert_deployment_node':
        state['deployment_nodes'], _ = _upsert_by_id(
            state['deployment_nodes'], item_data
        )
    elif op == 'delete_deployment_node':
        tid = str(payload.get('id') or payload.get('element_id') or '')
        _remove_by_id_and_prune_links(state, 'deployment_nodes', tid)
    elif op == 'upsert_deployment_link':
        rel_obj = payload.get('relation') or item_data
        state['deployment_links'], created_rel = _upsert_by_id(
            state['deployment_links'],
            {
                'id': rel_obj.get('id'),
                'source': rel_obj.get('source'),
                'target': rel_obj.get('target'),
                'title': rel_obj.get('title') or 'replicates to',
                'kind': rel_obj.get('kind') or 'replication',
            },
        )
        state['level_links'], _ = _upsert_by_id(
            state['level_links'], created_rel
        )
    elif op == 'upsert_level_link':
        rel_obj = payload.get('link') or item_data
        state['level_links'], _ = _upsert_by_id(state['level_links'], rel_obj)
    elif op == 'delete_level_link':
        rid = str(payload.get('id') or payload.get('link_id') or '')
        for rel_key in (
            'conceptual_relations',
            'logical_relations',
            'deployment_links',
            'level_links',
        ):
            state[rel_key] = [
                r for r in state.get(rel_key, []) if r.get('id') != rid
            ]
    elif op:
        raise DesignStoreError(f'Unsupported ERD element operation: {op!r}')

    saved = _save_erd_state(
        store,
        proc,
        design_id=design_id,
        actor_id=actor_id,
        state=state,
        expected_head_version=payload.get('expected_head_version'),
        pinned_positions=payload.get('pinned_positions'),
        status=str(payload.get('status') or 'draft'),
        note=str(payload.get('note') or f'ERD update ({op or "elements"})'),
    )
    refreshed = inspect_erd_elements(
        store, design_id=design_id, version=saved['design']['version']['version']
    )
    return {
        'design': saved['design'],
        'layout': saved['layout'],
        'elements': refreshed,
    }


# ---------------------------------------------------------------------------
# Public Route Entry Point 4: promote_whiteboard_to_design (SR-F-030011)
# ---------------------------------------------------------------------------


def promote_whiteboard_to_design(
    store: DesignStore,
    proc: StoreDDNProcess,
    *,
    design_id: str,
    actor_id: int,
    payload: dict[str, Any],
    app: Any = None,
) -> dict[str, Any]:
    """Promote Conceptual Whiteboard boxes/connections into Logical + Physical."""
    state = inspect_erd_elements(
        store, design_id=design_id, version=payload.get('version')
    )
    current_design = store.get_design(
        design_id, version=payload.get('version')
    )
    target_engine = str(
        payload.get('target_engine') or 'postgresql'
    ).strip().lower()
    if target_engine not in DEFAULT_LOGICAL_TYPE_MAPS:
        raise DesignStoreError(
            f'Unsupported target_engine for promotion: {target_engine!r}'
        )
    type_map = DEFAULT_LOGICAL_TYPE_MAPS[target_engine]

    table_naming = str(payload.get('table_naming') or 'plural_snake')
    pk_style = str(payload.get('pk_style') or 'entity_id')
    pk_logical_type = str(payload.get('pk_type') or 'bigint')
    if pk_logical_type not in type_map:
        pk_logical_type = 'integer'
    include_audit = bool(payload.get('include_audit_timestamps', True))
    save_version = bool(payload.get('save_version', True))

    # Index optional catalog_tables by singular and plural snake_case
    catalog_lookup: dict[str, Mapping[str, Any]] = {}
    for c_tbl in payload.get('catalog_tables') or []:
        if isinstance(c_tbl, Mapping) and c_tbl.get('name'):
            raw_n = str(c_tbl['name'])
            catalog_lookup[_to_snake_case(raw_n)] = c_tbl
            catalog_lookup[_singularize(raw_n)] = c_tbl
            catalog_lookup[_pluralize(raw_n)] = c_tbl

    # Index existing level links to prevent duplicates on repeated promotion
    existing_refines: dict[str, str] = {}
    existing_implements: dict[str, str] = {}
    for lnk in state['level_links']:
        if lnk.get('kind') == 'refines':
            existing_refines[lnk['target']] = lnk['source']
        elif lnk.get('kind') == 'implements':
            existing_implements[lnk['target']] = lnk['source']

    logical_by_id = {e['id']: e for e in state['logical_entities']}
    physical_by_id = {t['id']: t for t in state['physical_tables']}

    promoted_logical_count = 0
    promoted_physical_count = 0
    matched_catalog_tables: list[str] = []
    preview_tables: list[dict[str, Any]] = []

    concept_to_logical: dict[str, dict[str, Any]] = {}
    concept_to_physical: dict[str, dict[str, Any]] = {}

    for c_box in state['conceptual_entities']:
        cid = c_box['id']
        cname = str(c_box.get('name') or 'Entity')
        singular = _singularize(cname)
        plural = _pluralize(cname)
        if table_naming == 'singular_snake':
            phys_name = singular
        elif table_naming == 'preserve':
            phys_name = _to_snake_case(cname)
        else:
            phys_name = plural

        pk_col_name = f'{singular}_id' if pk_style == 'entity_id' else 'id'
        cat_match = (
            catalog_lookup.get(_to_snake_case(cname))
            or catalog_lookup.get(singular)
            or catalog_lookup.get(plural)
        )

        if cat_match is not None:
            matched_name = str(cat_match['name'])
            matched_catalog_tables.append(matched_name)
            phys_name = matched_name
            cat_cols = cat_match.get('columns') or cat_match.get('fields') or []
            log_fields = []
            phys_fields = []
            for col in cat_cols:
                if not isinstance(col, Mapping):
                    continue
                col_n = str(col.get('name') or 'id')
                raw_dt = str(col.get('datatype') or col.get('type') or 'TEXT')
                log_dt = normalize_to_logical_type(raw_dt)
                phys_dt = str(
                    col.get('datatype')
                    or col.get('type')
                    or type_map[log_dt]['physical']
                )
                is_pk = bool(col.get('pk', col_n in ('id', pk_col_name)))
                nullable = False if is_pk else bool(col.get('nullable', True))
                log_fields.append({
                    'id': uuid7(),
                    'name': col_n,
                    'datatype': log_dt,
                    'nullable': nullable,
                    'pk': is_pk,
                })
                phys_fields.append({
                    'id': uuid7(),
                    'name': col_n,
                    'datatype': phys_dt,
                    'nullable': nullable,
                    'pk': is_pk,
                    'unique': bool(col.get('unique', False)),
                    'default': str(col.get('default') or ''),
                    'references': str(col.get('references') or ''),
                })
        else:
            pk_phys_dt = type_map[pk_logical_type]['physical']
            str_phys_dt = type_map['string']['physical']
            ts_phys_dt = type_map['timestamptz']['physical']

            log_fields = [
                {
                    'id': uuid7(),
                    'name': pk_col_name,
                    'datatype': pk_logical_type,
                    'nullable': False,
                    'pk': True,
                }
            ]
            phys_fields = [
                {
                    'id': uuid7(),
                    'name': pk_col_name,
                    'datatype': pk_phys_dt,
                    'nullable': False,
                    'pk': True,
                    'unique': True,
                    'default': '',
                    'references': '',
                }
            ]
            sketch_fields = c_box.get('fields') or []
            if sketch_fields:
                for sf in sketch_fields:
                    sf_name = _to_snake_case(str(sf.get('name') or 'value'))
                    if sf_name == pk_col_name:
                        continue
                    l_dt = normalize_to_logical_type(
                        str(sf.get('datatype') or 'string')
                    )
                    log_fields.append({
                        'id': uuid7(),
                        'name': sf_name,
                        'datatype': l_dt,
                        'nullable': True,
                        'pk': False,
                    })
                    phys_fields.append({
                        'id': uuid7(),
                        'name': sf_name,
                        'datatype': type_map[l_dt]['physical'],
                        'nullable': True,
                        'pk': False,
                        'unique': False,
                        'default': '',
                        'references': '',
                    })
            else:
                log_fields.append({
                    'id': uuid7(),
                    'name': 'name',
                    'datatype': 'string',
                    'nullable': False,
                    'pk': False,
                })
                phys_fields.append({
                    'id': uuid7(),
                    'name': 'name',
                    'datatype': str_phys_dt,
                    'nullable': False,
                    'pk': False,
                    'unique': False,
                    'default': '',
                    'references': '',
                })

            if include_audit:
                log_fields.append({
                    'id': uuid7(),
                    'name': 'created_at',
                    'datatype': 'timestamptz',
                    'nullable': False,
                    'pk': False,
                })
                phys_fields.append({
                    'id': uuid7(),
                    'name': 'created_at',
                    'datatype': ts_phys_dt,
                    'nullable': False,
                    'pk': False,
                    'unique': False,
                    'default': 'CURRENT_TIMESTAMP',
                    'references': '',
                })

        # Create or update Logical entity
        existing_lid = existing_refines.get(cid)
        if existing_lid and existing_lid in logical_by_id:
            l_ent = logical_by_id[existing_lid]
            if not l_ent.get('fields'):
                l_ent['fields'] = log_fields
        else:
            l_ent = {
                'id': uuid7(),
                'name': _to_pascal_case(singular),
                'area': c_box.get('area', ''),
                'fields': log_fields,
            }
            state['logical_entities'].append(l_ent)
            logical_by_id[l_ent['id']] = l_ent
            state['level_links'].append({
                'id': uuid7(),
                'source': l_ent['id'],
                'target': cid,
                'kind': 'refines',
                'title': f"{l_ent['name']} refines {cname}",
            })
        promoted_logical_count += 1
        concept_to_logical[cid] = l_ent

        # Create or update Physical table
        existing_pid = existing_implements.get(l_ent['id'])
        if existing_pid and existing_pid in physical_by_id:
            p_tbl = physical_by_id[existing_pid]
            p_tbl['engine'] = target_engine
            if not p_tbl.get('fields'):
                p_tbl['fields'] = phys_fields
        else:
            p_tbl = {
                'id': uuid7(),
                'name': phys_name,
                'schema': 'public',
                'engine': target_engine,
                'fields': phys_fields,
                'indexes': [],
                'foreign_keys': [],
            }
            state['physical_tables'].append(p_tbl)
            physical_by_id[p_tbl['id']] = p_tbl
            state['level_links'].append({
                'id': uuid7(),
                'source': p_tbl['id'],
                'target': l_ent['id'],
                'kind': 'implements',
                'title': f"{phys_name} implements {l_ent['name']}",
            })
        promoted_physical_count += 1
        concept_to_physical[cid] = p_tbl
        preview_tables.append({
            'concept_name': cname,
            'logical_name': l_ent['name'],
            'physical_table': p_tbl['name'],
            'pk_column': pk_col_name,
            'matched_catalog': cat_match is not None,
            'column_count': len(p_tbl['fields']),
        })

    # Infer FK columns and Logical/Physical relations from conceptual connections
    inferred_fk_count = 0
    for crel in state['conceptual_relations']:
        src_cid = crel.get('source')
        tgt_cid = crel.get('target')
        if src_cid not in concept_to_physical or tgt_cid not in concept_to_physical:
            continue
        src_l = concept_to_logical[src_cid]
        tgt_l = concept_to_logical[tgt_cid]
        src_p = concept_to_physical[src_cid]
        tgt_p = concept_to_physical[tgt_cid]

        tgt_pk_col = next(
            (c for c in tgt_p['fields'] if c.get('pk')),
            tgt_p['fields'][0] if tgt_p['fields'] else {'name': 'id', 'datatype': type_map[pk_logical_type]['physical']},
        )
        tgt_singular = _singularize(tgt_p['name'])
        fk_col_name = (
            tgt_pk_col['name']
            if tgt_pk_col['name'] != 'id'
            else f'{tgt_singular}_id'
        )

        if not any(c['name'] == fk_col_name for c in src_l['fields']):
            src_l['fields'].append({
                'id': uuid7(),
                'name': fk_col_name,
                'datatype': normalize_to_logical_type(tgt_pk_col['datatype']),
                'nullable': True,
                'pk': False,
            })

        if not any(c['name'] == fk_col_name for c in src_p['fields']):
            src_p['fields'].append({
                'id': uuid7(),
                'name': fk_col_name,
                'datatype': tgt_pk_col['datatype'],
                'nullable': True,
                'pk': False,
                'unique': False,
                'default': '',
                'references': f"{tgt_p['name']}.{tgt_pk_col['name']}",
            })

        fk_name = f"fk_{_to_snake_case(src_p['name'])}_{_to_snake_case(tgt_p['name'])}"
        if not any(fk.get('name') == fk_name for fk in src_p.get('foreign_keys', [])):
            src_p.setdefault('foreign_keys', []).append({
                'id': uuid7(),
                'name': fk_name,
                'columns': [fk_col_name],
                'ref_table': tgt_p['name'],
                'ref_columns': [tgt_pk_col['name']],
                'on_delete': 'NO ACTION',
                'on_update': 'NO ACTION',
            })

        state['logical_relations'].append({
            'id': uuid7(),
            'source': src_l['id'],
            'target': tgt_l['id'],
            'kind': 'logical_rel',
            'title': crel.get('title') or f"{src_l['name']} -> {tgt_l['name']}",
        })
        state['level_links'].append({
            'id': uuid7(),
            'source': src_p['id'],
            'target': tgt_p['id'],
            'kind': 'foreign_key',
            'title': fk_name,
        })
        inferred_fk_count += 1

    state['extensions']['target_engine'] = target_engine
    ddn_text = _serialize_erd_state_to_ddn(state)

    if save_version:
        saved = _save_erd_state(
            store,
            proc,
            design_id=design_id,
            actor_id=actor_id,
            state=state,
            expected_head_version=payload.get('expected_head_version'),
            status=str(payload.get('status') or 'draft'),
            note=str(
                payload.get('note')
                or f'Promoted conceptual whiteboard to {target_engine} design'
            ),
            origin='promotion:whiteboard',
        )
        out_design = saved['design']
        ddn_text = out_design['version']['ddn_text']
    else:
        out_design = current_design

    return {
        'design': out_design,
        'promoted_logical_count': promoted_logical_count,
        'promoted_physical_count': promoted_physical_count,
        'inferred_foreign_keys': inferred_fk_count,
        'matched_catalog_tables': matched_catalog_tables,
        'preview_tables': preview_tables,
        'ddn_text': ddn_text,
    }


# ---------------------------------------------------------------------------
# Public Route Entry Point 5: evaluate_or_apply_erd_standards (SR-F-030012)
# ---------------------------------------------------------------------------


def _format_pattern(pattern: str, **tokens: str) -> str:
    out = pattern
    for k, v in tokens.items():
        out = out.replace('{' + k + '}', v)
    return out


def _check_erd_naming_violations(
    state: Mapping[str, Any],
    rules: Mapping[str, str],
    waivers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []

    def _find_waiver(rule_name: str, target: str, current_name: str) -> dict[str, Any] | None:
        for w in waivers:
            if not isinstance(w, Mapping):
                continue
            w_rule = str(w.get('rule_id') or w.get('rule') or '*')
            w_tgt = str(w.get('target') or '*')
            if w_rule in (rule_name, '*') and w_tgt in (
                target,
                current_name,
                '*',
            ):
                return dict(w)
        return None

    def _record(
        *,
        rule: str,
        severity: str,
        level: str,
        target: str,
        current_name: str,
        suggested_name: str,
        message: str,
        element_id: str = '',
        parent_id: str = '',
    ) -> None:
        matched_w = _find_waiver(rule, target, current_name)
        violations.append({
            'id': f'{rule}:{target}',
            'rule': rule,
            'severity': severity,
            'level': level,
            'target': target,
            'element_id': element_id,
            'parent_id': parent_id,
            'current_name': current_name,
            'suggested_name': suggested_name,
            'message': message,
            'waived': matched_w is not None,
            'waiver_reason': matched_w.get('reason', '') if matched_w else '',
        })

    table_case = rules.get('table_case', 'snake_case')
    col_case = rules.get('column_case', 'snake_case')
    pk_pattern = rules.get('pk_pattern', 'pk_{table}')
    fk_pattern = rules.get('fk_pattern', 'fk_{table}_{ref}')
    ix_pattern = rules.get('ix_pattern', 'ix_{table}_{cols}')

    phys_by_id = {t['id']: t for t in state.get('physical_tables', [])}

    # Logical attribute casing check
    for lent in state.get('logical_entities', []):
        for attr in lent.get('fields', []):
            aname = str(attr.get('name') or '')
            if not _matches_case_rule(aname, col_case):
                suggested = _apply_case_rule(aname, col_case)
                _record(
                    rule='column_case',
                    severity='warning',
                    level='logical',
                    target=f"logical:{lent['name']}.{aname}",
                    current_name=aname,
                    suggested_name=suggested,
                    message=f"Logical attribute {aname!r} on {lent['name']!r} should use {col_case} ({suggested!r}).",
                    element_id=attr['id'],
                    parent_id=lent['id'],
                )

    # Physical tables, columns, PKs, FKs, indexes
    for ptbl in state.get('physical_tables', []):
        tname = str(ptbl.get('name') or '')
        expected_table = _apply_case_rule(tname, table_case)
        if not _matches_case_rule(tname, table_case):
            _record(
                rule='table_case',
                severity='warning',
                level='physical',
                target=f'table:{tname}',
                current_name=tname,
                suggested_name=expected_table,
                message=f'Physical table {tname!r} should use {table_case} ({expected_table!r}).',
                element_id=ptbl['id'],
            )

        t_token = _to_snake_case(tname)
        expected_pk_cname = _format_pattern(pk_pattern, table=t_token)
        pk_cname = ptbl.get('pk_constraint_name')
        if pk_cname and pk_cname != expected_pk_cname:
            _record(
                rule='pk_pattern',
                severity='warning',
                level='physical',
                target=f'pk:{tname}.{pk_cname}',
                current_name=str(pk_cname),
                suggested_name=expected_pk_cname,
                message=f'Primary key constraint {pk_cname!r} should match {pk_pattern!r} ({expected_pk_cname!r}).',
                element_id=ptbl['id'],
            )

        for col in ptbl.get('fields', []):
            cname = str(col.get('name') or '')
            if not _matches_case_rule(cname, col_case):
                suggested_col = _apply_case_rule(cname, col_case)
                _record(
                    rule='column_case',
                    severity='warning',
                    level='physical',
                    target=f'column:{tname}.{cname}',
                    current_name=cname,
                    suggested_name=suggested_col,
                    message=f'Column {tname}.{cname} should use {col_case} ({suggested_col!r}).',
                    element_id=col['id'],
                    parent_id=ptbl['id'],
                )

        for ix in ptbl.get('indexes', []):
            ix_name = str(ix.get('name') or '')
            cols_tok = '_'.join(
                _to_snake_case(c) for c in (ix.get('columns') or ['col'])
            )
            expected_ix = _format_pattern(
                ix_pattern, table=t_token, cols=cols_tok
            )
            if ix_name and ix_name != expected_ix:
                _record(
                    rule='ix_pattern',
                    severity='info',
                    level='physical',
                    target=f'index:{tname}.{ix_name}',
                    current_name=ix_name,
                    suggested_name=expected_ix,
                    message=f'Index {ix_name!r} on {tname!r} should match {ix_pattern!r} ({expected_ix!r}).',
                    element_id=str(ix.get('id') or ''),
                    parent_id=ptbl['id'],
                )

        for fk in ptbl.get('foreign_keys', []):
            fk_name = str(fk.get('name') or '')
            ref_tok = _to_snake_case(str(fk.get('ref_table') or 'ref'))
            expected_fk = _format_pattern(
                fk_pattern, table=t_token, ref=ref_tok
            )
            if fk_name and fk_name != expected_fk:
                _record(
                    rule='fk_pattern',
                    severity='info',
                    level='physical',
                    target=f'fk:{tname}.{fk_name}',
                    current_name=fk_name,
                    suggested_name=expected_fk,
                    message=f'Foreign key {fk_name!r} on {tname!r} should match {fk_pattern!r} ({expected_fk!r}).',
                    element_id=str(fk.get('id') or ''),
                    parent_id=ptbl['id'],
                )

    # Also check physical relation edge titles in level_links
    for lnk in state.get('level_links', []):
        src_t = phys_by_id.get(lnk.get('source'))
        tgt_t = phys_by_id.get(lnk.get('target'))
        if src_t and tgt_t and lnk.get('kind') not in (
            'refines',
            'implements',
            'hosts',
            'traces_to',
        ):
            cur_title = str(lnk.get('title') or '')
            expected_fk = _format_pattern(
                fk_pattern,
                table=_to_snake_case(src_t['name']),
                ref=_to_snake_case(tgt_t['name']),
            )
            target_key = f"relation:{src_t['name']}->{tgt_t['name']}"
            if cur_title != expected_fk:
                _record(
                    rule='fk_pattern',
                    severity='info',
                    level='physical',
                    target=target_key,
                    current_name=cur_title,
                    suggested_name=expected_fk,
                    message=f'Physical FK relation {cur_title!r} should match {fk_pattern!r} ({expected_fk!r}).',
                    element_id=str(lnk.get('id') or ''),
                )

    return violations


def evaluate_or_apply_erd_standards(
    store: DesignStore,
    proc: StoreDDNProcess,
    *,
    design_id: str,
    actor_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Check naming standards, auto-fix violations, or persist waivers."""
    action = str(payload.get('action') or 'check').strip().lower()
    if action not in ('check', 'apply_fixes', 'save_waivers'):
        raise DesignStoreError(f'Unsupported ERD standards action: {action!r}')

    state = inspect_erd_elements(
        store, design_id=design_id, version=payload.get('version')
    )
    stored_rules = state['extensions'].get('naming_rules') or {}
    rules: dict[str, str] = {
        **DEFAULT_NAMING_RULES,
        **(stored_rules if isinstance(stored_rules, Mapping) else {}),
        **(
            {k: str(v) for k, v in payload['rules'].items() if v}
            if isinstance(payload.get('rules'), Mapping)
            else {}
        ),
    }

    stored_waivers = state['extensions'].get('naming_waivers')
    waivers: list[dict[str, Any]] = (
        list(stored_waivers) if isinstance(stored_waivers, list) else []
    )

    if action == 'save_waivers':
        incoming_waivers = payload.get('waivers')
        if isinstance(incoming_waivers, list):
            waivers = [
                {
                    'rule_id': str(
                        w.get('rule_id') or w.get('rule') or '*'
                    ),
                    'target': str(w.get('target') or '*'),
                    'reason': str(w.get('reason') or 'Approved exception'),
                    'waived_by': str(
                        w.get('waived_by') or f'user:{actor_id}'
                    ),
                }
                for w in incoming_waivers
                if isinstance(w, Mapping) and (w.get('target') or w.get('rule_id'))
            ]
        state['extensions']['naming_waivers'] = waivers
        state['extensions']['naming_rules'] = rules
        saved = _save_erd_state(
            store,
            proc,
            design_id=design_id,
            actor_id=actor_id,
            state=state,
            expected_head_version=payload.get('expected_head_version'),
            note=str(payload.get('note') or 'Saved ERD naming waivers'),
        )
        violations = _check_erd_naming_violations(state, rules, waivers)
        active_cnt = sum(1 for v in violations if not v['waived'])
        waived_cnt = sum(1 for v in violations if v['waived'])
        return {
            'violations': violations,
            'active_count': active_cnt,
            'waived_count': waived_cnt,
            'rules': rules,
            'waivers': waivers,
            'design': saved['design'],
        }

    violations = _check_erd_naming_violations(state, rules, waivers)
    if action == 'check':
        active_cnt = sum(1 for v in violations if not v['waived'])
        waived_cnt = sum(1 for v in violations if v['waived'])
        return {
            'violations': violations,
            'active_count': active_cnt,
            'waived_count': waived_cnt,
            'rules': rules,
            'waivers': waivers,
        }

    # action == 'apply_fixes'
    non_waived = {
        (v['rule'], v['target']): v['suggested_name']
        for v in violations
        if not v['waived']
    }
    fixed_count = 0
    phys_rename_map: dict[str, str] = {}

    for lent in state['logical_entities']:
        for attr in lent.get('fields', []):
            key = ('column_case', f"logical:{lent['name']}.{attr['name']}")
            if key in non_waived:
                attr['name'] = non_waived[key]
                fixed_count += 1

    for ptbl in state['physical_tables']:
        old_tname = ptbl['name']
        t_key = ('table_case', f'table:{old_tname}')
        if t_key in non_waived:
            ptbl['name'] = non_waived[t_key]
            phys_rename_map[old_tname] = ptbl['name']
            fixed_count += 1

        if ptbl.get('pk_constraint_name'):
            pk_key = ('pk_pattern', f"pk:{old_tname}.{ptbl['pk_constraint_name']}")
            if pk_key in non_waived:
                ptbl['pk_constraint_name'] = _format_pattern(
                    rules['pk_pattern'], table=_to_snake_case(ptbl['name'])
                )
                fixed_count += 1

        col_rename_map: dict[str, str] = {}
        for col in ptbl.get('fields', []):
            c_key = ('column_case', f"column:{old_tname}.{col['name']}")
            if c_key in non_waived:
                col_rename_map[col['name']] = non_waived[c_key]
                col['name'] = non_waived[c_key]
                fixed_count += 1

        for ix in ptbl.get('indexes', []):
            ix['columns'] = [
                col_rename_map.get(c, c) for c in (ix.get('columns') or [])
            ]
            ix_key = ('ix_pattern', f"index:{old_tname}.{ix.get('name', '')}")
            if ix_key in non_waived:
                cols_tok = '_'.join(
                    _to_snake_case(c) for c in (ix.get('columns') or ['col'])
                )
                ix['name'] = _format_pattern(
                    rules['ix_pattern'],
                    table=_to_snake_case(ptbl['name']),
                    cols=cols_tok,
                )
                fixed_count += 1

        for fk in ptbl.get('foreign_keys', []):
            fk['columns'] = [
                col_rename_map.get(c, c) for c in (fk.get('columns') or [])
            ]
            if fk.get('ref_table') in phys_rename_map:
                fk['ref_table'] = phys_rename_map[fk['ref_table']]
            fk_key = ('fk_pattern', f"fk:{old_tname}.{fk.get('name', '')}")
            if fk_key in non_waived:
                fk['name'] = _format_pattern(
                    rules['fk_pattern'],
                    table=_to_snake_case(ptbl['name']),
                    ref=_to_snake_case(str(fk.get('ref_table') or 'ref')),
                )
                fixed_count += 1

    # Update references and physical relation edge titles after table renames
    phys_by_id = {t['id']: t for t in state['physical_tables']}
    for ptbl in state['physical_tables']:
        for fk in ptbl.get('foreign_keys', []):
            if fk.get('ref_table') in phys_rename_map:
                fk['ref_table'] = phys_rename_map[fk['ref_table']]
        for col in ptbl.get('fields', []):
            ref_s = str(col.get('references') or '')
            if '.' in ref_s:
                rt, rc = ref_s.split('.', 1)
                if rt in phys_rename_map:
                    col['references'] = f'{phys_rename_map[rt]}.{rc}'

    for lnk in state['level_links']:
        src_t = phys_by_id.get(lnk.get('source'))
        tgt_t = phys_by_id.get(lnk.get('target'))
        if src_t and tgt_t and lnk.get('kind') not in (
            'refines',
            'implements',
            'hosts',
            'traces_to',
        ):
            expected_fk = _format_pattern(
                rules['fk_pattern'],
                table=_to_snake_case(src_t['name']),
                ref=_to_snake_case(tgt_t['name']),
            )
            if lnk.get('title') != expected_fk:
                # Only rewrite if not waived under old or new target key
                waived_rel = any(
                    v['waived']
                    and v['rule'] == 'fk_pattern'
                    and v['element_id'] == lnk.get('id')
                    for v in violations
                )
                if not waived_rel:
                    lnk['title'] = expected_fk
                    fixed_count += 1

    state['extensions']['naming_rules'] = rules
    state['extensions']['naming_waivers'] = waivers
    saved = _save_erd_state(
        store,
        proc,
        design_id=design_id,
        actor_id=actor_id,
        state=state,
        expected_head_version=payload.get('expected_head_version'),
        note=str(
            payload.get('note')
            or f'Auto-fixed {fixed_count} naming standard violation(s)'
        ),
    )
    updated_state = inspect_erd_elements(
        store, design_id=design_id, version=saved['design']['version']['version']
    )
    after_violations = _check_erd_naming_violations(
        updated_state, rules, waivers
    )
    return {
        'violations': after_violations,
        'active_count': sum(1 for v in after_violations if not v['waived']),
        'waived_count': sum(1 for v in after_violations if v['waived']),
        'fixed_count': fixed_count,
        'rules': rules,
        'waivers': waivers,
        'design': saved['design'],
    }


# ---------------------------------------------------------------------------
# Public Route Entry Point 6: plan_or_submit_erd_deployment
# (SR-F-030013 & SR-F-030014)
# ---------------------------------------------------------------------------


class ERDAlterReviewAdapter:
    """OperationBus review adapter for ERD DDL migrations.

    Ensures schema/metadata alter plans enter OperationBus in
    ``awaiting_approval`` stage and never execute destructively without
    explicit native-operation approval.
    """

    @staticmethod
    def validate(operation: Mapping[str, Any]) -> dict[str, Any]:
        req = operation.get('request') or {}
        payload = req.get('payload') or {}
        statements = list(payload.get('statements') or [])
        return {
            'valid': bool(req.get('approval_required') is True),
            'statement_count': len(statements),
            'target_engine': payload.get('target_engine', 'sqlite'),
        }

    @staticmethod
    def preview(operation: Mapping[str, Any]) -> dict[str, Any]:
        req = operation.get('request') or {}
        payload = req.get('payload') or {}
        return {
            'sql_preview': payload.get('migration_sql', ''),
            'statement_count': len(payload.get('statements') or []),
            'risk_summary': copy.deepcopy(payload.get('risk_summary') or {}),
            'destructive_warning': payload.get(
                'destructive_warning', DESTRUCTIVE_METADATA_WARNING
            ),
            'requires_native_approval': True,
            'executed': False,
        }

    @staticmethod
    def start(_operation: Mapping[str, Any]):
        from pgadmin.cdeadmin.operations import OperationStateError

        raise OperationStateError(
            'ERD alter plans require native provider execution handoff after '
            'explicit approval; ERD designer never executes DDL directly'
        )

    @staticmethod
    def inspect(_operation: Mapping[str, Any]):
        from pgadmin.cdeadmin.operations import OperationStateError

        raise OperationStateError('No active ERD provider execution')

    @staticmethod
    def cancel(_operation: Mapping[str, Any]):
        from pgadmin.cdeadmin.operations import OperationStateError

        raise OperationStateError('No active ERD provider execution')

    @staticmethod
    def validate_post_state(_operation: Mapping[str, Any]):
        from pgadmin.cdeadmin.operations import OperationStateError

        raise OperationStateError('No active ERD provider execution')


def _ensure_erd_review_adapter(bus: Any) -> None:
    from pgadmin.cdeadmin.operations import AdapterRegistrationError

    try:
        bus.register_adapter(ERD_ALTER_REVIEW_ADAPTER_ID, ERDAlterReviewAdapter)
    except AdapterRegistrationError:
        pass


def _get_operation_bus(app: Any = None, explicit_bus: Any = None) -> Any:
    global _FALLBACK_OPERATION_BUS
    from pgadmin.cdeadmin.operations import OperationBus

    if explicit_bus is not None:
        return explicit_bus
    if app is not None and hasattr(app, 'extensions'):
        bus = app.extensions.get('cdeadmin_operation_bus')
        if bus is None:
            bus = OperationBus()
            app.extensions['cdeadmin_operation_bus'] = bus
        return bus
    if _FALLBACK_OPERATION_BUS is None:
        _FALLBACK_OPERATION_BUS = OperationBus()
    return _FALLBACK_OPERATION_BUS


def _classify_erd_risks(
    selected_diffs: list[dict[str, Any]], *, target_engine: str
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Classify differences into the 4 mockup risk categories."""
    loses_data: list[dict[str, Any]] = []
    may_fail_on_existing_data: list[dict[str, Any]] = []
    breaks_running_clients: list[dict[str, Any]] = []
    locks_or_copies_table: list[dict[str, Any]] = []

    for diff in selected_diffs:
        kind = str(diff.get('change_kind') or '')
        stmt = str(diff.get('statement') or '').upper()
        after = diff.get('after') or {}
        before = diff.get('before') or {}

        if kind in ('drop_table', 'drop_column'):
            loses_data.append(diff)

        if (
            kind == 'alter_column'
            or kind == 'add_foreign_key'
            or (kind == 'add_column' and 'NOT NULL' in stmt and 'DEFAULT' not in stmt)
            or (
                kind == 'alter_column'
                and before.get('nullable') is True
                and after.get('nullable') is False
            )
        ):
            may_fail_on_existing_data.append(diff)

        if kind in (
            'rename_table',
            'rename_column',
            'drop_table',
            'drop_column',
            'drop_foreign_key',
        ):
            breaks_running_clients.append(diff)

        if kind in ('alter_column', 'add_foreign_key') or (
            kind == 'drop_column' and target_engine == 'sqlite'
        ):
            locks_or_copies_table.append(diff)

    categories = {
        'loses_data': loses_data,
        'may_fail_on_existing_data': may_fail_on_existing_data,
        'breaks_running_clients': breaks_running_clients,
        'locks_or_copies_table': locks_or_copies_table,
    }
    summary = {
        'loses_data': len(loses_data),
        'may_fail_on_existing_data': len(may_fail_on_existing_data),
        'breaks_running_clients': len(breaks_running_clients),
        'locks_or_copies_table': len(locks_or_copies_table),
        'total_selected': len(selected_diffs),
        'has_high_risk': bool(loses_data or breaks_running_clients),
    }
    return categories, summary


def _format_migration_scripts(
    *,
    design_key: str,
    design_title: str,
    desired_version: int,
    target_engine: str,
    statements: list[str],
) -> dict[str, str]:
    slug = _to_snake_case(design_key or design_title)
    body = (
        '\n'.join(statements)
        if statements
        else '-- No physical schema differences selected.'
    )
    checksum = hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]

    plain_sql = (
        f'-- ScratchRobin ERD Migration Plan\n'
        f'-- Design: {design_title} ({design_key}) @ v{desired_version}\n'
        f'-- Target Engine: {target_engine}\n'
        f'-- Native Operation Review Required Before Execution\n\n'
        f'BEGIN;\n\n{body}\n\nCOMMIT;\n'
    )
    flyway = (
        f'-- File: V{desired_version}__{slug}.sql\n'
        f'-- Flyway Repeatable/Versioned Migration generated by ScratchRobin\n'
        f'-- Target Engine: {target_engine} | Checksum: {checksum}\n\n'
        f'{body}\n'
    )
    liquibase = (
        f'--liquibase formatted sql\n'
        f'--changeset scratchrobin:{design_key}-v{desired_version} '
        f'logicalFilePath:migrations/{slug}_v{desired_version}.sql\n'
        f'--comment: {design_title} checkpoint v{desired_version} ({target_engine})\n'
        f'{body}\n'
        f'--rollback -- Manual native review required for destructive rollback\n'
    )
    atlas = (
        f'-- Atlas Versioned Migration ({slug} v{desired_version})\n'
        f'-- atlas:pos {design_key}@v{desired_version} [{target_engine}]\n\n'
        f'{body}\n'
    )
    return {
        'plain_sql': plain_sql,
        'flyway': flyway,
        'liquibase': liquibase,
        'atlas': atlas,
    }


def _build_environment_matrix(
    store: DesignStore,
    *,
    design: Mapping[str, Any],
    desired_version: int,
    default_engine: str,
    custom_environments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    recorded = store.list_deployments(design['id'])
    by_env_key: dict[str, dict[str, Any]] = {}
    for row in recorded:
        ep = str(row['endpoint_id'])
        by_env_key[ep] = row
        for prefix in ('dev', 'staging', 'prod'):
            if prefix in ep.lower() or prefix in str(row['database_target_id']).lower():
                by_env_key.setdefault(prefix, row)

    specs = (
        custom_environments
        if isinstance(custom_environments, list) and custom_environments
        else list(DEFAULT_ENVIRONMENTS)
    )
    matrix: list[dict[str, Any]] = []
    seen_tuples: set[tuple[str, str, str]] = set()

    for spec in specs:
        env_id = str(spec.get('environment') or 'dev').lower()
        label = str(spec.get('label') or env_id.capitalize())
        ep_id = str(spec.get('endpoint_id') or f'env-{env_id}')
        db_id = str(spec.get('database_target_id') or f'{env_id}_db')
        match_row = by_env_key.get(ep_id) or by_env_key.get(env_id)
        if match_row is not None:
            dep_ver = int(match_row['deployed_version'])
            eng = str(match_row['engine'])
            ep_id = str(match_row['endpoint_id'])
            db_id = str(match_row['database_target_id'])
            seen_tuples.add((eng, ep_id, db_id))
            has_drift = dep_ver != desired_version
            drift_status = (
                'in_sync'
                if not has_drift
                else ('behind' if dep_ver < desired_version else 'ahead')
            )
            matrix.append({
                'environment': env_id,
                'label': label,
                'engine': eng,
                'endpoint_id': ep_id,
                'database_target_id': db_id,
                'deployed_version': dep_ver,
                'desired_version': desired_version,
                'active_version': design.get('active_version'),
                'has_drift': has_drift,
                'drift_status': drift_status,
                'plan_sha256': match_row['plan_sha256'],
                'target_fingerprint': match_row['target_fingerprint'],
                'applied_by': match_row['applied_by'],
                'applied_at': match_row['applied_at'],
            })
        else:
            eng = str(spec.get('engine') or default_engine)
            seen_tuples.add((eng, ep_id, db_id))
            matrix.append({
                'environment': env_id,
                'label': label,
                'engine': eng,
                'endpoint_id': ep_id,
                'database_target_id': db_id,
                'deployed_version': None,
                'desired_version': desired_version,
                'active_version': design.get('active_version'),
                'has_drift': True,
                'drift_status': 'not_deployed',
                'plan_sha256': None,
                'target_fingerprint': None,
                'applied_by': None,
                'applied_at': None,
            })

    # Include any additional custom target_deployment rows recorded in designs.db
    for row in recorded:
        tup = (
            str(row['engine']),
            str(row['endpoint_id']),
            str(row['database_target_id']),
        )
        if tup in seen_tuples:
            continue
        dep_ver = int(row['deployed_version'])
        has_drift = dep_ver != desired_version
        matrix.append({
            'environment': str(row['endpoint_id']),
            'label': f"{row['endpoint_id']} / {row['database_target_id']}",
            'engine': str(row['engine']),
            'endpoint_id': str(row['endpoint_id']),
            'database_target_id': str(row['database_target_id']),
            'deployed_version': dep_ver,
            'desired_version': desired_version,
            'active_version': design.get('active_version'),
            'has_drift': has_drift,
            'drift_status': (
                'in_sync'
                if not has_drift
                else ('behind' if dep_ver < desired_version else 'ahead')
            ),
            'plan_sha256': row['plan_sha256'],
            'target_fingerprint': row['target_fingerprint'],
            'applied_by': row['applied_by'],
            'applied_at': row['applied_at'],
        })

    return matrix


def _diff_against_live_catalog(
    state: Mapping[str, Any],
    catalog_tables: list[dict[str, Any]],
    *,
    target_engine: str,
) -> list[dict[str, Any]]:
    """Compute physical schema differences between desired ERD and catalog."""
    cat_by_name = {
        str(t.get('name') or '').lower(): t for t in catalog_tables
    }
    des_by_name = {
        str(t.get('name') or '').lower(): t
        for t in state.get('physical_tables', [])
    }
    diffs: list[dict[str, Any]] = []

    for low_t, pt in sorted(des_by_name.items()):
        q_table = _quote_sql_ident(pt['name'], target_engine)
        ct = cat_by_name.get(low_t)
        if ct is None:
            col_defs = []
            for col in pt.get('fields', []):
                q_c = _quote_sql_ident(col['name'], target_engine)
                nn = '' if col.get('nullable', True) else ' NOT NULL'
                col_defs.append(f"{q_c} {col.get('datatype', 'TEXT')}{nn}")
            cols_sql = ', '.join(col_defs) or 'id INTEGER'
            diffs.append({
                'difference_id': f"create_table:{pt['id']}",
                'element_id': pt['id'],
                'change_kind': 'create_table',
                'object_name': pt['name'],
                'destructive': False,
                'statement': f'CREATE TABLE {q_table} ({cols_sql});',
            })
            continue

        cat_cols = {
            str(c.get('name') or '').lower(): c
            for c in (ct.get('fields') or ct.get('columns') or [])
        }
        des_cols = {
            str(c.get('name') or '').lower(): c
            for c in pt.get('fields', [])
        }
        for low_c, col in sorted(des_cols.items()):
            q_c = _quote_sql_ident(col['name'], target_engine)
            c_before = cat_cols.get(low_c)
            if c_before is None:
                nn = '' if col.get('nullable', True) else ' NOT NULL'
                diffs.append({
                    'difference_id': f"add_column:{col['id']}",
                    'element_id': col['id'],
                    'change_kind': 'add_column',
                    'object_name': f"{pt['name']}.{col['name']}",
                    'destructive': False,
                    'statement': (
                        f"ALTER TABLE {q_table} ADD COLUMN "
                        f"{q_c} {col.get('datatype', 'TEXT')}{nn};"
                    ),
                })
            elif (
                str(c_before.get('datatype') or '').upper()
                != str(col.get('datatype') or '').upper()
                or bool(c_before.get('nullable', True))
                != bool(col.get('nullable', True))
            ):
                nn = '' if col.get('nullable', True) else ' NOT NULL'
                diffs.append({
                    'difference_id': f"alter_column:{col['id']}",
                    'element_id': col['id'],
                    'change_kind': 'alter_column',
                    'object_name': f"{pt['name']}.{col['name']}",
                    'before': {
                        'datatype': c_before.get('datatype'),
                        'nullable': c_before.get('nullable', True),
                    },
                    'after': {
                        'datatype': col.get('datatype'),
                        'nullable': col.get('nullable', True),
                    },
                    'destructive': True,
                    'statement': (
                        f"ALTER TABLE {q_table} ALTER COLUMN "
                        f"{q_c} TYPE {col.get('datatype', 'TEXT')}{nn};"
                    ),
                })

        for low_c, c_before in sorted(cat_cols.items()):
            if low_c not in des_cols:
                q_cold = _quote_sql_ident(c_before['name'], target_engine)
                diffs.append({
                    'difference_id': f"drop_column:{pt['name']}.{c_before['name']}",
                    'element_id': pt['id'],
                    'change_kind': 'drop_column',
                    'object_name': f"{pt['name']}.{c_before['name']}",
                    'destructive': True,
                    'statement': f'ALTER TABLE {q_table} DROP COLUMN {q_cold};',
                })

    for low_t, ct in sorted(cat_by_name.items()):
        if low_t not in des_by_name:
            q_old = _quote_sql_ident(ct['name'], target_engine)
            diffs.append({
                'difference_id': f"drop_table:{ct['name']}",
                'element_id': ct.get('id', ct['name']),
                'change_kind': 'drop_table',
                'object_name': ct['name'],
                'destructive': True,
                'statement': f'DROP TABLE {q_old};',
            })

    return diffs


def plan_or_submit_erd_deployment(
    store: DesignStore,
    proc: StoreDDNProcess,
    *,
    design_id: str,
    actor_id: int,
    payload: dict[str, Any],
    app: Any = None,
) -> dict[str, Any]:
    """Preview ERD alter plan + 4 risk buckets, submit to OperationBus review,
    or record a verified target_deployment row for the Environment Matrix.
    """
    action = str(payload.get('action') or 'preview').strip().lower()
    if action not in (
        'preview',
        'submit_review',
        'record_environment_deployment',
    ):
        raise DesignStoreError(f'Unsupported ERD deploy action: {action!r}')

    desired_version_arg = payload.get('desired_version')
    design = store.get_design(
        design_id,
        version=int(desired_version_arg) if desired_version_arg else None,
    )
    desired_ver = int(design['version']['version'])
    target_engine = str(payload.get('target_engine') or 'sqlite').lower()
    if target_engine not in DEFAULT_LOGICAL_TYPE_MAPS:
        raise DesignStoreError(f'Unsupported target_engine: {target_engine!r}')

    if action == 'record_environment_deployment':
        env_key = str(payload.get('environment') or 'dev').lower()
        default_spec = next(
            (s for s in DEFAULT_ENVIRONMENTS if s['environment'] == env_key),
            DEFAULT_ENVIRONMENTS[0],
        )
        ep_id = str(payload.get('endpoint_id') or default_spec['endpoint_id'])
        db_id = str(
            payload.get('database_target_id')
            or default_spec['database_target_id']
        )
        dep_ver = int(payload.get('deployed_version') or desired_ver)
        plan_sha = str(
            payload.get('plan_sha256')
            or sha256_text(design['version']['ddn_text'])
        )
        fp = str(
            payload.get('target_fingerprint')
            or f'{target_engine}:{ep_id}:{db_id}@v{dep_ver}'
        )
        recorded = store.record_deployment(
            design_id=design_id,
            deployed_version=dep_ver,
            engine=target_engine,
            endpoint_id=ep_id,
            database_target_id=db_id,
            plan_sha256=plan_sha,
            target_fingerprint=fp,
            applied_by=actor_id,
        )
        environments = _build_environment_matrix(
            store,
            design=design,
            desired_version=desired_ver,
            default_engine=target_engine,
            custom_environments=payload.get('environments'),
        )
        return {
            'status': 'recorded',
            'deployment': recorded,
            'environments': environments,
        }

    baseline_mode = str(payload.get('baseline_mode') or 'active').lower()
    if baseline_mode not in ('active', 'version', 'catalog'):
        raise DesignStoreError(f'Unsupported baseline_mode: {baseline_mode!r}')

    selected_ids = payload.get('selected_difference_ids')
    if baseline_mode == 'catalog' and (
        payload.get('tables')
        or payload.get('catalog_tables')
        or payload.get('sqlite_path')
    ):
        cat_payload = {
            **payload,
            'tables': payload.get('catalog_tables') or payload.get('tables'),
        }
        cat_tables, _ = _introspect_catalog_tables(
            cat_payload, default_engine=target_engine
        )
        state = inspect_erd_elements(
            store, design_id=design_id, version=desired_ver
        )
        all_diffs = _diff_against_live_catalog(
            state, cat_tables, target_engine=target_engine
        )
        chosen_set = (
            set(selected_ids)
            if isinstance(selected_ids, list)
            else {d['difference_id'] for d in all_diffs}
        )
        chosen_diffs = [
            d for d in all_diffs if d['difference_id'] in chosen_set
        ]
        plan = {
            'design_id': design_id,
            'baseline_mode': 'catalog',
            'base_version': None,
            'desired_version': desired_ver,
            'target_engine': target_engine,
            'differences': all_diffs,
            'selected_difference_ids': [
                d['difference_id'] for d in chosen_diffs
            ],
            'statements': [d['statement'] for d in chosen_diffs],
            'script': '\n'.join(d['statement'] for d in chosen_diffs),
            'has_destructive_changes': any(
                d['destructive'] for d in chosen_diffs
            ),
            'requires_native_review': True,
            'applied_immediately': False,
            'destructive_warning': DESTRUCTIVE_METADATA_WARNING,
        }
    else:
        if baseline_mode == 'version':
            base_ver = int(payload.get('base_version') or 0)
        elif baseline_mode == 'catalog':
            base_ver = 0
        else:
            base_ver = (
                int(payload['base_version'])
                if payload.get('base_version') is not None
                else (design['active_version'] or 0)
            )
        plan = preview_erd_alter_plan(
            store,
            design_id,
            base_version=base_ver,
            desired_version=desired_ver,
            selected_difference_ids=selected_ids,
            target_engine=target_engine,
            catalog_snapshot=payload.get('catalog_snapshot'),
            handoff_options=payload.get('handoff_options'),
        )
        plan['baseline_mode'] = baseline_mode

    selected_set = set(plan['selected_difference_ids'])
    selected_diffs = [
        d
        for d in plan['differences']
        if d['difference_id'] in selected_set
    ]
    risk_categories, risk_summary = _classify_erd_risks(
        selected_diffs, target_engine=target_engine
    )

    migration_format = str(
        payload.get('migration_format') or 'plain_sql'
    ).strip().lower()
    if migration_format not in ('plain_sql', 'flyway', 'liquibase', 'atlas'):
        raise DesignStoreError(
            f'Unsupported migration_format: {migration_format!r}'
        )
    migration_scripts = _format_migration_scripts(
        design_key=design['key'],
        design_title=design['title'],
        desired_version=desired_ver,
        target_engine=target_engine,
        statements=plan['statements'],
    )
    migration_sql = migration_scripts[migration_format]

    environments = _build_environment_matrix(
        store,
        design=design,
        desired_version=desired_ver,
        default_engine=target_engine,
        custom_environments=payload.get('environments'),
    )

    if action == 'preview':
        return {
            'plan': plan,
            'baseline_mode': baseline_mode,
            'risk_categories': risk_categories,
            'risk_summary': risk_summary,
            'migration_format': migration_format,
            'migration_sql': migration_sql,
            'migration_scripts': migration_scripts,
            'environments': environments,
        }

    # action == 'submit_review' -> queue into OperationBus in awaiting_approval
    from pgadmin.cdeadmin.operations import OperationRequest

    bus = _get_operation_bus(app, payload.get('operation_bus'))
    _ensure_erd_review_adapter(bus)
    principal = f'user:{int(actor_id)}'
    env_name = str(payload.get('environment') or 'dev')
    ep_id = str(payload.get('endpoint_id') or f'env-{env_name}')
    risk_class = (
        'destructive' if plan['has_destructive_changes'] else 'write'
    )

    op_req = OperationRequest(
        operation_kind='erd.schema_migration',
        capability_id='erd.deploy.alter_plan',
        risk_class=risk_class,
        adapter_id=ERD_ALTER_REVIEW_ADAPTER_ID,
        target_resource_id=f'endpoint:{ep_id}:design:{design_id}@v{desired_ver}',
        payload={
            'design_id': design_id,
            'design_key': design['key'],
            'desired_version': desired_ver,
            'baseline_mode': baseline_mode,
            'environment': env_name,
            'endpoint_id': ep_id,
            'target_engine': target_engine,
            'migration_format': migration_format,
            'migration_sql': migration_sql,
            'statements': list(plan['statements']),
            'risk_summary': risk_summary,
            'destructive_warning': plan['destructive_warning'],
        },
        approval_required=True,
    )
    idem = str(payload.get('idempotency_key') or uuid7())
    approvers = tuple(
        str(a) for a in (payload.get('approvers') or ()) if str(a).strip()
    )
    submitted = bus.submit(
        op_req,
        principal=principal,
        idempotency_key=idem,
        readers=approvers,
        approvers=approvers,
    )
    op_id = submitted['operation_id']
    bus.validate(op_id, principal)
    previewed = bus.preview(op_id, principal)

    return {
        'operation_id': op_id,
        'status': previewed['stage'],
        'stage': previewed['stage'],
        'statement_count': len(plan['statements']),
        'risk_summary': risk_summary,
        'risk_categories': risk_categories,
        'migration_format': migration_format,
        'migration_sql': migration_sql,
        'plan': plan,
        'environments': environments,
        'requires_native_review': True,
        'applied_immediately': False,
        'submitted_at': datetime.now(timezone.utc).isoformat(),
        'operation': previewed,
    }
