##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Host-side Data Edit Surface engine (Surface 1 — Browse & Edit Data).

Owns result-set buffering/caching on the Python host, smart Local (host-cached)
vs. Server sort/filter execution, batch row-mutation staging (INSERT / UPDATE /
DELETE) with dialect SQL preview, rich column/domain metadata resolution,
execution plan & timing telemetry, chronological session message logging, and
Specific Layout / Template persistence.
"""

from __future__ import annotations

import collections
import copy
import datetime
import json
import os
import sqlite3
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MAX_RETAINED_SURFACES = 64
AUTO_LOCAL_SORT_THRESHOLD = 5000


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        '%Y-%m-%d %H:%M:%S UTC'
    )


def _estimate_bytes(obj: Any) -> int:
    try:
        encoded = json.dumps(obj, default=str, ensure_ascii=False)
        return len(encoded.encode('utf-8'))
    except Exception:
        return sys.getsizeof(obj)


def _plan_sql_text(plan: dict[str, Any] | None) -> str:
    if not isinstance(plan, dict):
        return ''
    preview = (
        plan.get('command_preview')
        or plan.get('native_preview')
        or ({'statements': plan['statements']} if isinstance(plan.get('statements'), list) else None)
    )
    if not preview:
        return ''
    if isinstance(preview, str):
        return preview
    if isinstance(preview, list):
        return ';\n'.join(
            s for s in (_plan_sql_text({'command_preview': item}) for item in preview) if s
        )
    if isinstance(preview, dict):
        stmts = preview.get('statements')
        if isinstance(stmts, list):
            parts = [
                str(st.get('source') or st.get('sql') or '').strip()
                for st in stmts
                if isinstance(st, dict)
            ]
            return ';\n'.join(p for p in parts if p)
        return str(preview.get('source') or preview.get('sql') or '')
    return str(preview)


def _infer_client_type(col: dict[str, Any]) -> tuple[str, str, bool]:
    """Return (client_type, default_alignment, is_complex) for a column."""
    input_kind = str(col.get('input_kind') or '').lower()
    native = str(col.get('native_type') or '').upper()

    if input_kind == 'array' or 'ARRAY' in native or native.endswith('[]'):
        return 'array', 'left', True
    if 'JSON' in native or input_kind == 'json':
        return 'json', 'left', True
    if 'BLOB' in native or 'BYTEA' in native or 'BINARY' in native or input_kind == 'binary':
        return 'blob', 'left', True
    if 'CLOB' in native or native in ('TEXT', 'LONGTEXT', 'MEDIUMTEXT'):
        return 'longtext', 'left', False
    if 'BOOL' in native or input_kind == 'boolean':
        return 'boolean', 'center', False
    if 'UUID' in native or 'GUID' in native:
        return 'uuid', 'left', False
    if any(
        tok in native
        for tok in (
            'INT', 'NUMERIC', 'DECIMAL', 'DECFLOAT', 'FLOAT', 'DOUBLE',
            'REAL', 'NUMBER', 'SERIAL', 'MONEY',
        )
    ) or input_kind in ('integer', 'decimal', 'decfloat', 'float32', 'float64'):
        return 'number', 'right', False
    if any(tok in native for tok in ('TIMESTAMP', 'DATETIME')):
        return 'timestamp', 'left', False
    if 'DATE' in native:
        return 'date', 'left', False
    if 'TIME' in native:
        return 'time', 'left', False
    return 'text', 'left', False


def _quote_ident(name: str, engine_id: str) -> str:
    clean = str(name or '')
    if engine_id in ('mysql', 'mariadb'):
        return '`' + clean.replace('`', '``') + '`'
    return '"' + clean.replace('"', '""') + '"'


def _qualified_target(target: dict[str, Any], engine_id: str) -> str:
    path = (
        target.get('authority_path')
        or target.get('display_path')
        or [target.get('display_name') or target.get('resource_id', '').split(':')[-1]]
    )
    parts = [str(p) for p in path if p]
    if engine_id in ('firebird', 'sqlite') and parts:
        parts = [parts[-1]]
    elif len(parts) > 2:
        parts = parts[-2:]
    return '.'.join(_quote_ident(p, engine_id) for p in parts)


def _comparable_sort_key(val: Any) -> tuple[int, Any]:
    if val is None:
        return (0, '')
    if isinstance(val, bool):
        return (1, 1 if val else 0)
    if isinstance(val, (int, float)):
        return (2, val)
    if isinstance(val, str):
        try:
            return (2, float(val))
        except ValueError:
            return (3, val.lower())
    return (4, json.dumps(val, default=str, sort_keys=True))


def _row_matches_filter(values: dict[str, Any], flt: dict[str, Any]) -> bool:
    col = str(flt.get('column') or '')
    op = str(flt.get('op') or 'contains').lower()
    needle = flt.get('value')
    cell = values.get(col)

    if op == 'is_null':
        return cell is None
    if op == 'not_null':
        return cell is not None
    if cell is None:
        return False

    cell_str = (
        json.dumps(cell, default=str, ensure_ascii=False)
        if isinstance(cell, (dict, list))
        else str(cell)
    )
    needle_str = '' if needle is None else str(needle)

    if op == 'eq':
        return cell_str.lower() == needle_str.lower()
    if op == 'neq':
        return cell_str.lower() != needle_str.lower()
    if op == 'contains':
        return needle_str.lower() in cell_str.lower()
    if op == 'starts_with':
        return cell_str.lower().startswith(needle_str.lower())
    if op == 'ends_with':
        return cell_str.lower().endswith(needle_str.lower())
    if op == 'in':
        allowed = (
            [str(x).strip().lower() for x in needle]
            if isinstance(needle, list)
            else [s.strip().lower() for s in needle_str.split(',') if s.strip()]
        )
        return cell_str.lower() in allowed
    if op in ('gt', 'gte', 'lt', 'lte'):
        try:
            lhs = float(cell) if not isinstance(cell, (int, float)) else cell
            rhs = float(needle_str)
            if op == 'gt':
                return lhs > rhs
            if op == 'gte':
                return lhs >= rhs
            if op == 'lt':
                return lhs < rhs
            return lhs <= rhs
        except (TypeError, ValueError):
            if op == 'gt':
                return cell_str > needle_str
            if op == 'gte':
                return cell_str >= needle_str
            if op == 'lt':
                return cell_str < needle_str
            return cell_str <= needle_str
    return True


def _build_display_select_sql(
    target: dict[str, Any],
    engine_id: str,
    columns: list[str],
    sorts: list[dict[str, Any]],
    filters: list[dict[str, Any]],
    max_rows: int,
    sort_execution: str,
) -> tuple[str, list[Any]]:
    qual = _qualified_target(target, engine_id)
    proj = (
        ', '.join(_quote_ident(c, engine_id) for c in columns)
        if columns else '*'
    )
    where_clauses: list[str] = []
    params: list[Any] = []
    if sort_execution == 'server':
        for flt in filters:
            col_q = _quote_ident(str(flt.get('column') or ''), engine_id)
            op = str(flt.get('op') or 'contains').lower()
            val = flt.get('value')
            if op == 'is_null':
                where_clauses.append(f'{col_q} IS NULL')
            elif op == 'not_null':
                where_clauses.append(f'{col_q} IS NOT NULL')
            elif op == 'eq':
                where_clauses.append(f'{col_q} = ?')
                params.append(val)
            elif op == 'neq':
                where_clauses.append(f'{col_q} <> ?')
                params.append(val)
            elif op == 'contains':
                where_clauses.append(f'CAST({col_q} AS VARCHAR(4000)) LIKE ?')
                params.append(f'%{val}%')
            elif op == 'starts_with':
                where_clauses.append(f'CAST({col_q} AS VARCHAR(4000)) LIKE ?')
                params.append(f'{val}%')
            elif op in ('gt', 'gte', 'lt', 'lte'):
                sym = {'gt': '>', 'gte': '>=', 'lt': '<', 'lte': '<='}[op]
                where_clauses.append(f'{col_q} {sym} ?')
                params.append(val)

    order_clauses: list[str] = []
    if sort_execution == 'server':
        for srt in sorts:
            col_q = _quote_ident(str(srt.get('column') or ''), engine_id)
            direction = 'DESC' if str(srt.get('direction') or '').lower() == 'desc' else 'ASC'
            order_clauses.append(f'{col_q} {direction}')

    where_sql = f"\nWHERE {' AND '.join(where_clauses)}" if where_clauses else ''
    order_sql = f"\nORDER BY {', '.join(order_clauses)}" if order_clauses else ''

    if engine_id == 'firebird':
        return (
            f'SELECT FIRST {max_rows} {proj}\nFROM {qual}{where_sql}{order_sql};',
            params,
        )
    return (
        f'SELECT {proj}\nFROM {qual}{where_sql}{order_sql}\nLIMIT {max_rows};',
        params,
    )


@dataclass
class StagedRowMutation:
    mutation_id: str
    op: str  # 'insert' | 'update' | 'delete'
    row_key: str
    base_row_index: int | None
    identity_token: str | None
    draft: dict[str, Any]
    overlay_values: dict[str, Any]
    preview_sql: str
    staged_at: str


@dataclass
class DataSurfaceState:
    surface_id: str
    user_id: int
    server_id: int
    database_target_id: str | None
    language_profile: str
    engine_id: str
    target_resource: dict[str, Any]
    session_id: str | None = None
    autocommit: bool = False
    page_size: int = 200
    max_rows: int = 1000
    sort_mode: str = 'auto'  # 'auto' | 'local' | 'server'
    sort_execution: str = 'local'  # 'local' | 'server'
    sorts: list[dict[str, Any]] = field(default_factory=list)
    filters: list[dict[str, Any]] = field(default_factory=list)
    columns: list[dict[str, Any]] = field(default_factory=list)
    field_catalog: list[dict[str, Any]] = field(default_factory=list)
    raw_rows: list[dict[str, Any]] = field(default_factory=list)
    view_indices: list[int] = field(default_factory=list)
    complete_in_buffer: bool = True
    retrieval_limited: bool = False
    editable: bool = False
    identity_policy: str = ''
    row_operations: list[str] = field(default_factory=list)
    insert_identity_token: str | None = None
    insert_default_values: bool = False
    server_sql: str = ''
    bound_parameters: list[Any] = field(default_factory=list)
    execution_plan_text: str = ''
    execution_plan_nodes: list[dict[str, Any]] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=lambda: {
        'prepare_ms': 0.0,
        'execute_ms': 0.0,
        'fetch_ms': 0.0,
        'host_sort_filter_ms': 0.0,
        'total_ms': 0.0,
    })
    server_stats: dict[str, Any] = field(default_factory=dict)
    transaction: dict[str, Any] | None = None
    loaded_once: bool = False
    tx_dirty_since_boundary: bool = False
    staged_mutations: collections.OrderedDict[str, StagedRowMutation] = field(
        default_factory=collections.OrderedDict
    )
    messages: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)


class SurfaceLayoutStore:
    """SQLite persistence in DATA_DIR for Specific Layouts & Shareable Templates."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            try:
                import config as pg_config
                data_dir = getattr(pg_config, 'DATA_DIR', None)
            except Exception:
                data_dir = None
            base = Path(data_dir or os.path.expanduser('~/.cdeadmin'))
            base.mkdir(parents=True, exist_ok=True)
            db_path = base / 'surface_layouts.db'
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
                CREATE TABLE IF NOT EXISTS surface_specific_layout (
                    user_id INTEGER NOT NULL,
                    surface_kind TEXT NOT NULL,
                    object_key TEXT NOT NULL,
                    layout_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, surface_kind, object_key)
                );
                CREATE TABLE IF NOT EXISTS surface_layout_template (
                    template_id TEXT PRIMARY KEY,
                    surface_kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    author_user_id INTEGER NOT NULL,
                    layout_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def get_specific_layout(
        self, user_id: int, surface_kind: str, object_key: str
    ) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                'SELECT layout_json FROM surface_specific_layout '
                'WHERE user_id = ? AND surface_kind = ? AND object_key = ?',
                (int(user_id), str(surface_kind), str(object_key)),
            ).fetchone()
            if row is None:
                return None
            try:
                return json.loads(row['layout_json'])
            except Exception:
                return None

    def save_specific_layout(
        self, user_id: int, surface_kind: str, object_key: str, layout: dict[str, Any]
    ) -> dict[str, Any]:
        encoded = json.dumps(layout, ensure_ascii=False, sort_keys=True)
        now = _now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO surface_specific_layout
                    (user_id, surface_kind, object_key, layout_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, surface_kind, object_key)
                DO UPDATE SET layout_json = excluded.layout_json,
                              updated_at = excluded.updated_at
                """,
                (int(user_id), str(surface_kind), str(object_key), encoded, now),
            )
        return {'saved': 'specific', 'object_key': object_key, 'updated_at': now}

    def save_template(
        self,
        user_id: int,
        surface_kind: str,
        name: str,
        layout: dict[str, Any],
        description: str = '',
        template_id: str | None = None,
    ) -> dict[str, Any]:
        tid = str(template_id or uuid.uuid4())
        clean_name = str(name or 'Untitled Template').strip()[:128]
        encoded = json.dumps(layout, ensure_ascii=False, sort_keys=True)
        now = _now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO surface_layout_template
                    (template_id, surface_kind, name, description,
                     author_user_id, layout_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(template_id)
                DO UPDATE SET name = excluded.name,
                              description = excluded.description,
                              layout_json = excluded.layout_json,
                              updated_at = excluded.updated_at
                """,
                (
                    tid,
                    str(surface_kind),
                    clean_name,
                    str(description or '')[:512],
                    int(user_id),
                    encoded,
                    now,
                ),
            )
        return {
            'saved': 'template',
            'template_id': tid,
            'name': clean_name,
            'updated_at': now,
        }

    def list_templates(self, surface_kind: str) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                'SELECT template_id, name, description, author_user_id, '
                'layout_json, updated_at '
                'FROM surface_layout_template WHERE surface_kind = ? '
                'ORDER BY name COLLATE NOCASE ASC',
                (str(surface_kind),),
            ).fetchall()
        out = []
        for r in rows:
            try:
                parsed = json.loads(r['layout_json'])
            except Exception:
                parsed = {}
            out.append({
                'template_id': r['template_id'],
                'name': r['name'],
                'description': r['description'],
                'author_user_id': r['author_user_id'],
                'layout': parsed,
                'updated_at': r['updated_at'],
            })
        return out


class DataSurfaceHostService:
    """Coordinates host-buffered Data Edit Surfaces across provider engines."""

    def __init__(self, layout_store: SurfaceLayoutStore | None = None):
        self._surfaces: collections.OrderedDict[str, DataSurfaceState] = (
            collections.OrderedDict()
        )
        self._lock = threading.RLock()
        self.layout_store = layout_store or SurfaceLayoutStore()

    def _log(
        self,
        surface: DataSurfaceState,
        severity: str,
        operation: str,
        message: str,
        *,
        elapsed_ms: float | None = None,
        sqlstate: str = '',
        native_code: str = '',
        row_index: int | None = None,
        column_name: str = '',
    ) -> None:
        entry = {
            'id': f'msg-{len(surface.messages) + 1}-{int(time.time() * 1000)}',
            'timestamp': _now_iso(),
            'severity': severity,
            'operation': operation,
            'elapsed_ms': round(elapsed_ms, 2) if elapsed_ms is not None else None,
            'message': message,
            'sqlstate': sqlstate,
            'native_code': native_code,
            'row_index': row_index,
            'column_name': column_name,
        }
        surface.messages.append(entry)
        if len(surface.messages) > 500:
            surface.messages = surface.messages[-500:]

    def _get_or_create_surface(
        self,
        workspace_service: Any,
        server: Any,
        request: dict[str, Any],
    ) -> DataSurfaceState:
        user_id = int(getattr(server, 'user_id', 1) or 1)
        server_id = int(getattr(server, 'id', 0) or 0)
        surface_id = str(request.get('surface_id') or '').strip()
        if not surface_id:
            surface_id = f'ds-{uuid.uuid4()}'

        with self._lock:
            existing = self._surfaces.get(surface_id)
            if existing is not None and existing.user_id == user_id:
                self._surfaces.move_to_end(surface_id)
                return existing

            target = copy.deepcopy(request.get('target_resource') or {})
            db_target_id = request.get('database_target_id') or None
            lang_profile = str(request.get('language_profile') or '')
            engine_id = str(
                request.get('engine_id')
                or lang_profile.split('-')[0]
                or 'relational'
            ).lower()
            surface = DataSurfaceState(
                surface_id=surface_id,
                user_id=user_id,
                server_id=server_id,
                database_target_id=db_target_id,
                language_profile=lang_profile,
                engine_id=engine_id,
                target_resource=target,
                page_size=max(10, min(1000, int(request.get('page_size') or 200))),
                max_rows=max(1, min(100000, int(request.get('max_rows') or 1000))),
                autocommit=bool(request.get('autocommit', False)),
            )
            while len(self._surfaces) >= MAX_RETAINED_SURFACES:
                _, evicted = self._surfaces.popitem(last=False)
                if evicted.session_id:
                    try:
                        workspace_service.close_session(
                            server, evicted.session_id, evicted.database_target_id
                        )
                    except Exception:
                        pass
            self._surfaces[surface_id] = surface
            return surface

    def _ensure_host_session(
        self,
        workspace_service: Any,
        server: Any,
        surface: DataSurfaceState,
    ) -> str | None:
        if surface.session_id:
            return surface.session_id
        if not surface.language_profile:
            return None
        t0 = time.perf_counter()
        purpose = (
            'firebird-row-grid'
            if surface.language_profile == 'firebird-sql'
            else None
        )
        try:
            opened = workspace_service.open_session(
                server,
                surface.language_profile,
                database_target_id=surface.database_target_id,
                session_purpose=purpose,
            )
        except TypeError:
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
            f'Host session {surface.session_id} attached.',
            elapsed_ms=dt_ms,
        )
        return surface.session_id

    def _enrich_field_catalog(
        self,
        workspace_service: Any,
        server: Any,
        surface: DataSurfaceState,
    ) -> list[dict[str, Any]]:
        """Build 1-row-per-column Server-to-Client Field Mapping metadata."""
        inspected_cols: dict[str, dict[str, Any]] = {}
        try:
            res_id = surface.target_resource.get('resource_id')
            if res_id and hasattr(workspace_service, 'inspect_resource'):
                inspected = workspace_service.inspect_resource(
                    server,
                    {
                        'resource_id': res_id,
                        'database_target_id': surface.database_target_id,
                    },
                )
                props = (
                    (inspected or {}).get('properties')
                    or (inspected or {}).get('extensions', {}).get('provider', {}).get('native', {})
                    or {}
                )
                for col_item in (props.get('columns') or (inspected or {}).get('columns') or []):
                    if isinstance(col_item, dict) and col_item.get('name'):
                        inspected_cols[str(col_item['name'])] = col_item
        except Exception:
            pass

        enriched: list[dict[str, Any]] = []
        for idx, col in enumerate(surface.columns, start=1):
            cname = str(col.get('name') or f'COL_{idx}')
            extra = inspected_cols.get(cname) or {}
            client_type, default_align, is_complex = _infer_client_type(col)
            col['client_type'] = client_type
            col['default_alignment'] = default_align
            col['is_complex'] = is_complex
            col['comment'] = str(
                col.get('comment')
                or extra.get('comment')
                or extra.get('description')
                or ''
            )
            domain_name = str(
                col.get('domain_name')
                or extra.get('domain')
                or extra.get('domain_name')
                or extra.get('field_source')
                or ''
            )
            col['domain_name'] = domain_name
            nullable = col.get(
                'nullable',
                extra.get('nullable', not bool(col.get('key'))),
            )
            col['nullable'] = bool(nullable)
            default_expr = str(
                col.get('default_value')
                or extra.get('default')
                or extra.get('default_source')
                or ''
            )
            computed_expr = str(
                extra.get('computed_source') or extra.get('generated') or ''
            )
            enriched.append({
                'ordinal': idx,
                'name': cname,
                'key_role': (
                    'PK'
                    if col.get('key')
                    else ('FK' if extra.get('foreign_key') else '')
                ),
                'nullable': bool(nullable),
                'default_expression': default_expr,
                'computed_expression': computed_expr,
                'native_type': str(col.get('native_type') or extra.get('data_type') or 'UNKNOWN'),
                'domain_type': domain_name or '—',
                'precision_scale_length': str(
                    extra.get('length')
                    or extra.get('precision')
                    or (
                        f"{col['array_spec'].get('bounds')}"
                        if isinstance(col.get('array_spec'), dict)
                        else '—'
                    )
                ),
                'charset': str(
                    extra.get('charset')
                    or extra.get('character_set')
                    or (col.get('array_spec') or {}).get('charset')
                    or '—'
                ),
                'collation': str(extra.get('collation') or '—'),
                'client_type': client_type,
                'default_alignment': default_align,
                'editable': bool(col.get('editable')),
                'insertable': bool(col.get('insertable', col.get('editable'))),
                'is_complex': is_complex,
                'comment': col['comment'],
            })
        return enriched

    def _recompute_local_view(self, surface: DataSurfaceState) -> None:
        t0 = time.perf_counter()
        indices = list(range(len(surface.raw_rows)))
        if surface.filters:
            indices = [
                i for i in indices
                if all(
                    _row_matches_filter(surface.raw_rows[i].get('values') or {}, flt)
                    for flt in surface.filters
                )
            ]
        if surface.sorts:
            for srt in reversed(surface.sorts):
                col = str(srt.get('column') or '')
                desc = str(srt.get('direction') or '').lower() == 'desc'
                indices.sort(
                    key=lambda idx: _comparable_sort_key(
                        (surface.raw_rows[idx].get('values') or {}).get(col)
                    ),
                    reverse=desc,
                )
        surface.view_indices = indices
        dt_ms = (time.perf_counter() - t0) * 1000.0
        surface.timings_ms['host_sort_filter_ms'] = round(dt_ms, 2)

    def _fetch_into_host_buffer(
        self,
        workspace_service: Any,
        server: Any,
        surface: DataSurfaceState,
    ) -> None:
        t_start = time.perf_counter()
        session_id = self._ensure_host_session(workspace_service, server, surface)

        collected_rows: list[dict[str, Any]] = []
        continuation: str | None = None
        first_page: dict[str, Any] | None = None
        batch_limit = min(500, max(50, surface.page_size))

        t_exec_start = time.perf_counter()
        first_batch_done = False
        execute_ms = 0.0

        while len(collected_rows) < surface.max_rows:
            remaining = surface.max_rows - len(collected_rows)
            req_limit = min(batch_limit, remaining)
            req_payload: dict[str, Any] = {
                'target_resource': copy.deepcopy(surface.target_resource),
                'limit': req_limit,
                'continuation': continuation,
                'database_target_id': surface.database_target_id,
            }
            if session_id:
                req_payload['session_id'] = session_id

            page = workspace_service.read_visual_admin_rows(server, req_payload)
            if not first_batch_done:
                execute_ms = (time.perf_counter() - t_exec_start) * 1000.0
                first_batch_done = True
                first_page = page

            batch_rows = list(page.get('rows') or [])
            if len(batch_rows) > remaining:
                batch_rows = batch_rows[:remaining]
            collected_rows.extend(batch_rows)
            continuation = page.get('continuation')

            if not continuation or len(collected_rows) >= surface.max_rows:
                if continuation:
                    try:
                        workspace_service.cancel_visual_admin_rows(
                            server,
                            {
                                'continuation': continuation,
                                'database_target_id': surface.database_target_id,
                            },
                        )
                    except Exception:
                        pass
                    surface.retrieval_limited = True
                    surface.complete_in_buffer = False
                else:
                    surface.retrieval_limited = False
                    surface.complete_in_buffer = True
                break

        total_fetch_ms = (time.perf_counter() - t_exec_start) * 1000.0
        surface.raw_rows = collected_rows
        surface.loaded_once = True
        if first_page is not None:
            surface.columns = list(first_page.get('columns') or [])
            surface.editable = bool(first_page.get('editable'))
            surface.identity_policy = str(first_page.get('identity_policy') or '')
            surface.row_operations = list(first_page.get('row_operations') or [])
            surface.insert_identity_token = first_page.get('insert_identity_token')
            surface.insert_default_values = bool(
                first_page.get('insert_default_values')
            )

        surface.field_catalog = self._enrich_field_catalog(
            workspace_service, server, surface
        )

        # Resolve smart Local vs Server sort mode
        if surface.sort_mode == 'local':
            surface.sort_execution = 'local'
        elif surface.sort_mode == 'server':
            surface.sort_execution = 'server'
        else:
            surface.sort_execution = (
                'local'
                if surface.complete_in_buffer
                and len(surface.raw_rows) <= AUTO_LOCAL_SORT_THRESHOLD
                else 'server'
            )

        col_names = [str(c.get('name') or '') for c in surface.columns if c.get('name')]
        surface.server_sql, surface.bound_parameters = _build_display_select_sql(
            surface.target_resource,
            surface.engine_id,
            col_names,
            surface.sorts,
            surface.filters,
            surface.max_rows,
            surface.sort_execution,
        )

        self._recompute_local_view(surface)

        total_ms = (time.perf_counter() - t_start) * 1000.0
        surface.timings_ms.update({
            'execute_ms': round(execute_ms, 2),
            'fetch_ms': round(max(0.0, total_fetch_ms - execute_ms), 2),
            'total_ms': round(total_ms, 2),
        })

        # Synthesize structured execution plan info
        qual_name = _qualified_target(surface.target_resource, surface.engine_id)
        key_cols = [c['name'] for c in surface.columns if c.get('key')]
        plan_access = (
            f'INDEX ({qual_name} PK [{", ".join(key_cols)}])'
            if key_cols
            else f'NATURAL ({qual_name})'
        )
        surface.execution_plan_text = f'PLAN ({plan_access})'
        surface.execution_plan_nodes = [
            {
                'id': 'plan-root',
                'operation': 'SELECT / FETCH',
                'target': qual_name,
                'strategy': 'PK Indexed Order' if key_cols else 'Natural / Sequential Scan',
                'rows_buffered': len(surface.raw_rows),
                'sort_location': (
                    'Host Cache (Local)'
                    if surface.sort_execution == 'local'
                    else 'Database Server'
                ),
                'elapsed_ms': round(total_ms, 2),
            }
        ]

        if session_id:
            try:
                surface.transaction = workspace_service.transaction(
                    server, session_id, surface.database_target_id
                )
            except Exception:
                pass

        self._log(
            surface,
            'info',
            'Fetch',
            f'Buffered {len(surface.raw_rows)} row(s) on host '
            f'({"complete" if surface.complete_in_buffer else "limit reached"}).',
            elapsed_ms=total_ms,
        )

    def _serialize_window(
        self,
        surface: DataSurfaceState,
        user_id: int,
        window_offset: int = 0,
        window_size: int | None = None,
    ) -> dict[str, Any]:
        w_size = max(1, min(1000, int(window_size or surface.page_size)))
        staged_updates_by_idx: dict[int, StagedRowMutation] = {}
        staged_deletes_by_idx: set[int] = set()
        staged_inserts: list[StagedRowMutation] = []

        for mut in surface.staged_mutations.values():
            if mut.op == 'insert':
                staged_inserts.append(mut)
            elif mut.op == 'update' and mut.base_row_index is not None:
                staged_updates_by_idx[mut.base_row_index] = mut
            elif mut.op == 'delete' and mut.base_row_index is not None:
                staged_deletes_by_idx.add(mut.base_row_index)

        total_filtered = len(surface.view_indices) + len(staged_inserts)
        safe_offset = max(0, min(window_offset, max(0, total_filtered - 1))) if total_filtered > 0 else 0

        window_rows: list[dict[str, Any]] = []
        slice_indices = surface.view_indices[safe_offset:safe_offset + w_size]
        for pos, raw_idx in enumerate(slice_indices):
            base_row = surface.raw_rows[raw_idx]
            vals = copy.deepcopy(base_row.get('values') or {})
            stage_state = None
            mut_id = None
            if raw_idx in staged_updates_by_idx:
                mut = staged_updates_by_idx[raw_idx]
                vals.update(copy.deepcopy(mut.overlay_values))
                stage_state = 'updated'
                mut_id = mut.mutation_id
            if raw_idx in staged_deletes_by_idx:
                stage_state = 'deleted'
            window_rows.append({
                'row_number': safe_offset + pos + 1,
                'base_row_index': raw_idx,
                'identity_token': base_row.get('identity_token'),
                'values': vals,
                'original_values': base_row.get('values') or {},
                'stage_state': stage_state,
                'mutation_id': mut_id,
            })

        # Append staged inserts if within window
        remaining_slots = w_size - len(window_rows)
        if remaining_slots > 0 and staged_inserts:
            ins_start = max(0, safe_offset - len(surface.view_indices))
            for ins_pos, mut in enumerate(staged_inserts[ins_start:ins_start + remaining_slots]):
                window_rows.append({
                    'row_number': len(surface.view_indices) + ins_start + ins_pos + 1,
                    'base_row_index': None,
                    'identity_token': mut.mutation_id,
                    'values': copy.deepcopy(mut.overlay_values),
                    'original_values': {},
                    'stage_state': 'inserted',
                    'mutation_id': mut.mutation_id,
                })

        local_ops_parts: list[str] = []
        if surface.filters and surface.sort_execution == 'local':
            local_ops_parts.append(
                f'{len(surface.filters)} host-cached filter(s)'
            )
        if surface.sorts and surface.sort_execution == 'local':
            sort_desc = ', '.join(
                f"{s['column']} {str(s.get('direction', 'asc')).upper()}"
                for s in surface.sorts
            )
            local_ops_parts.append(f'Host-cached sort: {sort_desc}')

        object_key = (
            f"{surface.server_id}:{surface.database_target_id or 'default'}:"
            f"{surface.target_resource.get('resource_id') or surface.target_resource.get('display_name') or ''}"
        )
        saved_layout = self.layout_store.get_specific_layout(
            user_id, 'data-edit-surface', object_key
        )

        staged_sql = [
            {
                'mutation_id': m.mutation_id,
                'op': m.op,
                'row_key': m.row_key,
                'base_row_index': m.base_row_index,
                'sql': m.preview_sql,
                'staged_at': m.staged_at,
            }
            for m in surface.staged_mutations.values()
        ]

        has_uncommitted_activity = bool(
            not surface.autocommit
            and (surface.tx_dirty_since_boundary or len(surface.staged_mutations) > 0)
        )
        return {
            'surface_id': surface.surface_id,
            'has_uncommitted_activity': has_uncommitted_activity,
            'session_id': surface.session_id,
            'object_key': object_key,
            'autocommit': surface.autocommit,
            'editable': surface.editable,
            'identity_policy': surface.identity_policy,
            'row_operations': surface.row_operations,
            'insert_default_values': surface.insert_default_values,
            'page_size': surface.page_size,
            'max_rows': surface.max_rows,
            'window_offset': safe_offset,
            'window_size': w_size,
            'total_buffered_rows': len(surface.raw_rows),
            'total_view_rows': total_filtered,
            'complete_in_buffer': surface.complete_in_buffer,
            'retrieval_limited': surface.retrieval_limited,
            'sort_mode': surface.sort_mode,
            'sort_execution': surface.sort_execution,
            'sorts': surface.sorts,
            'filters': surface.filters,
            'columns': surface.columns,
            'rows': window_rows,
            'fields_grid': surface.field_catalog,
            'sql_view': {
                'server_sql': surface.server_sql,
                'parameters': surface.bound_parameters,
                'sort_execution': surface.sort_execution,
                'sort_mode': surface.sort_mode,
                'is_local_sort_or_filter': bool(local_ops_parts),
                'local_operations_summary': (
                    ' · '.join(local_ops_parts)
                    if local_ops_parts
                    else 'Executed directly on database server'
                ),
                'staged_sql': staged_sql,
            },
            'metrics_view': {
                'timings_ms': surface.timings_ms,
                'buffer': {
                    'buffered_rows': len(surface.raw_rows),
                    'visible_rows': total_filtered,
                    'complete_in_buffer': surface.complete_in_buffer,
                    'retrieval_limited': surface.retrieval_limited,
                    'host_memory_bytes': _estimate_bytes(surface.raw_rows),
                    'page_size': surface.page_size,
                    'max_rows': surface.max_rows,
                },
                'transaction': {
                    'session_id': surface.session_id,
                    'autocommit': surface.autocommit,
                    'staged_inserts': sum(
                        1 for m in surface.staged_mutations.values() if m.op == 'insert'
                    ),
                    'staged_updates': sum(
                        1 for m in surface.staged_mutations.values() if m.op == 'update'
                    ),
                    'staged_deletes': sum(
                        1 for m in surface.staged_mutations.values() if m.op == 'delete'
                    ),
                    'staged_total': len(surface.staged_mutations),
                    'has_uncommitted_activity': has_uncommitted_activity,
                    'provider_observation': surface.transaction,
                },
                'plan_text': surface.execution_plan_text,
                'plan_nodes': surface.execution_plan_nodes,
            },
            'messages': list(reversed(surface.messages)),
            'saved_specific_layout': saved_layout,
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

        if sub_action == 'list_templates':
            return {
                'templates': self.layout_store.list_templates('data-edit-surface')
            }

        surface = self._get_or_create_surface(workspace_service, server, request)
        with surface.lock:
            if 'page_size' in request and request['page_size']:
                surface.page_size = max(10, min(1000, int(request['page_size'])))
            if 'max_rows' in request and request['max_rows']:
                surface.max_rows = max(1, min(100000, int(request['max_rows'])))
            if 'autocommit' in request and request['autocommit'] is not None:
                surface.autocommit = bool(request['autocommit'])

            window_offset = int(request.get('window_offset') or 0)
            window_size = int(request.get('window_size') or surface.page_size)

            if sub_action in ('open', 'refresh'):
                same_target = (
                    not request.get('target_resource')
                    or surface.target_resource.get('resource_id')
                    == (request.get('target_resource') or {}).get('resource_id')
                )
                if (
                    sub_action == 'open'
                    and surface.loaded_once
                    and same_target
                    and not request.get('force_reload')
                ):
                    return self._serialize_window(
                        surface,
                        user_id,
                        window_offset=window_offset,
                        window_size=window_size,
                    )
                if 'sorts' in request and isinstance(request['sorts'], list):
                    surface.sorts = list(request['sorts'])
                if 'filters' in request and isinstance(request['filters'], list):
                    surface.filters = list(request['filters'])
                if 'sort_mode' in request and request['sort_mode'] in ('auto', 'local', 'server'):
                    surface.sort_mode = request['sort_mode']
                self._fetch_into_host_buffer(workspace_service, server, surface)
                return self._serialize_window(
                    surface, user_id, window_offset=0, window_size=window_size
                )

            if sub_action == 'read_window':
                return self._serialize_window(
                    surface,
                    user_id,
                    window_offset=window_offset,
                    window_size=window_size,
                )

            if sub_action == 'sort_filter':
                if 'sorts' in request and isinstance(request['sorts'], list):
                    surface.sorts = list(request['sorts'])
                if 'filters' in request and isinstance(request['filters'], list):
                    surface.filters = list(request['filters'])
                if 'sort_mode' in request and request['sort_mode'] in ('auto', 'local', 'server'):
                    surface.sort_mode = request['sort_mode']

                desired_exec = (
                    surface.sort_mode
                    if surface.sort_mode in ('local', 'server')
                    else (
                        'local'
                        if surface.complete_in_buffer
                        and len(surface.raw_rows) <= AUTO_LOCAL_SORT_THRESHOLD
                        else 'server'
                    )
                )
                surface.sort_execution = desired_exec
                if desired_exec == 'server' and not surface.staged_mutations:
                    self._fetch_into_host_buffer(
                        workspace_service, server, surface
                    )
                else:
                    col_names = [
                        str(c.get('name') or '')
                        for c in surface.columns
                        if c.get('name')
                    ]
                    surface.server_sql, surface.bound_parameters = (
                        _build_display_select_sql(
                            surface.target_resource,
                            surface.engine_id,
                            col_names,
                            surface.sorts,
                            surface.filters,
                            surface.max_rows,
                            surface.sort_execution,
                        )
                    )
                    self._recompute_local_view(surface)
                self._log(
                    surface,
                    'info',
                    'Sort / Filter',
                    f'Applied {len(surface.sorts)} sort(s) and {len(surface.filters)} filter(s) '
                    f'({surface.sort_execution} mode) → {len(surface.view_indices)} row(s).',
                    elapsed_ms=surface.timings_ms.get('host_sort_filter_ms', 0.0),
                )
                return self._serialize_window(
                    surface, user_id, window_offset=0, window_size=window_size
                )

            if sub_action == 'stage_row':
                t0 = time.perf_counter()
                op = str(request.get('op') or 'update').lower()
                base_idx = request.get('base_row_index')
                base_idx = int(base_idx) if base_idx is not None else None
                changes = dict(request.get('changes') or {})
                identity_token = request.get('identity_token')
                session_id = self._ensure_host_session(
                    workspace_service, server, surface
                )

                if op == 'insert':
                    draft = {
                        'values': changes,
                        'options': (
                            {'identity_token': surface.insert_identity_token}
                            if surface.target_resource.get('resource_kind') == 'view'
                            and surface.insert_identity_token
                            else {}
                        ),
                    }
                    row_key = str(request.get('mutation_id') or f'ins-{uuid.uuid4()}')
                elif op == 'update':
                    if base_idx is None or not (0 <= base_idx < len(surface.raw_rows)):
                        raise ValueError('Target row index is out of bounds')
                    identity_token = (
                        identity_token or surface.raw_rows[base_idx].get('identity_token')
                    )
                    draft = {
                        'selector': {'identity_token': identity_token},
                        'changes': changes,
                        'concurrency_token': identity_token,
                    }
                    row_key = f'row-{base_idx}'
                elif op == 'delete':
                    if base_idx is None or not (0 <= base_idx < len(surface.raw_rows)):
                        raise ValueError('Target row index is out of bounds')
                    identity_token = (
                        identity_token or surface.raw_rows[base_idx].get('identity_token')
                    )
                    draft = {
                        'selector': {'identity_token': identity_token},
                        'concurrency_token': identity_token,
                        'confirmation': 'provider-row-delete',
                    }
                    row_key = f'row-{base_idx}'
                else:
                    raise ValueError(f'Unsupported row operation: {op}')

                plan_req = {
                    'resource_kind': surface.target_resource.get('resource_kind', 'table'),
                    'operation_id': op,
                    'target_resource': copy.deepcopy(surface.target_resource),
                    'draft': draft,
                    'session_id': session_id,
                    'database_target_id': surface.database_target_id,
                }
                validation = workspace_service.validate_visual_admin(server, plan_req)
                if not validation.get('valid'):
                    err_msg = ' '.join(
                        str(e.get('message') or e) for e in (validation.get('errors') or [])
                    ) or 'Row validation failed.'
                    dt_ms = (time.perf_counter() - t0) * 1000.0
                    first_col = next(iter(changes.keys()), '')
                    self._log(
                        surface,
                        'error',
                        f'Validate {op.upper()}',
                        err_msg,
                        elapsed_ms=dt_ms,
                        row_index=base_idx,
                        column_name=first_col,
                    )
                    raise RuntimeError(err_msg)

                plan = workspace_service.plan_visual_admin(server, plan_req)
                if plan.get('state') != 'ready' or not plan.get('execution_available'):
                    err_msg = ', '.join(plan.get('blockers') or []) or 'Row plan blocked.'
                    dt_ms = (time.perf_counter() - t0) * 1000.0
                    self._log(
                        surface,
                        'error',
                        f'Plan {op.upper()}',
                        err_msg,
                        elapsed_ms=dt_ms,
                        row_index=base_idx,
                    )
                    raise RuntimeError(err_msg)

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
                    surface.transaction = workspace_service.transaction_action(
                        server,
                        session_id,
                        'commit',
                        database_target_id=surface.database_target_id,
                    )
                    dt_ms = (time.perf_counter() - t0) * 1000.0
                    self._log(
                        surface,
                        'info',
                        f'Autocommit {op.upper()}',
                        f'Applied and committed {op} immediately.',
                        elapsed_ms=dt_ms,
                        row_index=base_idx,
                    )
                    self._fetch_into_host_buffer(workspace_service, server, surface)
                else:
                    existing_mut = surface.staged_mutations.get(row_key)
                    merged_overlay = dict(existing_mut.overlay_values) if existing_mut else {}
                    merged_overlay.update(changes)
                    if existing_mut and existing_mut.op == 'update' and op == 'update':
                        merged_changes = dict(existing_mut.draft.get('changes') or {})
                        merged_changes.update(changes)
                        draft['changes'] = merged_changes
                    surface.staged_mutations[row_key] = StagedRowMutation(
                        mutation_id=row_key,
                        op=op,
                        row_key=row_key,
                        base_row_index=base_idx,
                        identity_token=identity_token,
                        draft=draft,
                        overlay_values=merged_overlay,
                        preview_sql=preview_sql,
                        staged_at=_now_iso(),
                    )
                    dt_ms = (time.perf_counter() - t0) * 1000.0
                    self._log(
                        surface,
                        'info',
                        f'Stage {op.upper()}',
                        f'Staged {op} in host batch ({len(surface.staged_mutations)} pending).',
                        elapsed_ms=dt_ms,
                        row_index=base_idx,
                    )

                return self._serialize_window(
                    surface,
                    user_id,
                    window_offset=window_offset,
                    window_size=window_size,
                )

            if sub_action == 'revert_row':
                row_key = str(request.get('row_key') or '')
                surface.staged_mutations.pop(row_key, None)
                self._log(surface, 'info', 'Revert Row', f'Reverted staged entry {row_key}.')
                return self._serialize_window(
                    surface,
                    user_id,
                    window_offset=window_offset,
                    window_size=window_size,
                )

            if sub_action == 'commit_batch':
                t0 = time.perf_counter()
                session_id = self._ensure_host_session(
                    workspace_service, server, surface
                )
                applied_count = 0
                for row_key, mut in list(surface.staged_mutations.items()):
                    try:
                        plan_req = {
                            'resource_kind': surface.target_resource.get('resource_kind', 'table'),
                            'operation_id': mut.op,
                            'target_resource': copy.deepcopy(surface.target_resource),
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
                        surface.staged_mutations.pop(row_key, None)
                        applied_count += 1
                    except Exception as exc:
                        dt_ms = (time.perf_counter() - t0) * 1000.0
                        first_col = next(iter(mut.overlay_values.keys()), '')
                        self._log(
                            surface,
                            'error',
                            'Commit Batch',
                            f'Failed on {row_key} ({mut.op}): {exc}',
                            elapsed_ms=dt_ms,
                            row_index=mut.base_row_index,
                            column_name=first_col,
                        )
                        raise

                if session_id:
                    surface.transaction = workspace_service.transaction_action(
                        server,
                        session_id,
                        'commit',
                        database_target_id=surface.database_target_id,
                    )
                surface.tx_dirty_since_boundary = False
                dt_ms = (time.perf_counter() - t0) * 1000.0
                self._log(
                    surface,
                    'info',
                    'Commit',
                    f'Committed {applied_count} staged mutation(s) on host.',
                    elapsed_ms=dt_ms,
                )
                self._fetch_into_host_buffer(workspace_service, server, surface)
                return self._serialize_window(
                    surface,
                    user_id,
                    window_offset=window_offset,
                    window_size=window_size,
                )

            if sub_action == 'rollback_batch':
                t0 = time.perf_counter()
                discarded = len(surface.staged_mutations)
                surface.staged_mutations.clear()
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
                dt_ms = (time.perf_counter() - t0) * 1000.0
                self._log(
                    surface,
                    'warning',
                    'Rollback',
                    f'Rolled back transaction and discarded {discarded} staged mutation(s).',
                    elapsed_ms=dt_ms,
                )
                self._fetch_into_host_buffer(workspace_service, server, surface)
                return self._serialize_window(
                    surface,
                    user_id,
                    window_offset=window_offset,
                    window_size=window_size,
                )

            if sub_action == 'export_formatted':
                from .sql_surface_host import export_tabular_dataset
                scope = str((request.get('settings') or {}).get('scope') or 'filtered')
                export_rows = (
                    [surface.raw_rows[i] for i in surface.view_indices]
                    if scope == 'filtered'
                    else list(surface.raw_rows)
                )
                return export_tabular_dataset(
                    surface.columns,
                    export_rows,
                    fmt=str(request.get('format') or 'csv'),
                    settings=dict(request.get('settings') or {}),
                    sql_text=surface.server_sql or '',
                    base_filename=str(
                        request.get('filename')
                        or surface.target_resource.get('display_name')
                        or 'data_export'
                    ),
                )

            if sub_action == 'column_profile':
                col_name = str(request.get('column') or '')
                total = len(surface.view_indices)
                null_cnt = 0
                freq: collections.Counter[str] = collections.Counter()
                comparable_vals: list[tuple[tuple[int, Any], str]] = []
                for idx in surface.view_indices:
                    val = (surface.raw_rows[idx].get('values') or {}).get(col_name)
                    if val is None:
                        null_cnt += 1
                    else:
                        disp = (
                            json.dumps(val, default=str, ensure_ascii=False)
                            if isinstance(val, (dict, list))
                            else str(val)
                        )
                        freq[disp] += 1
                        comparable_vals.append((_comparable_sort_key(val), disp))
                comparable_vals.sort(key=lambda pair: pair[0])
                return {
                    'column': col_name,
                    'total_rows': total,
                    'null_count': null_cnt,
                    'non_null_count': total - null_cnt,
                    'distinct_count': len(freq),
                    'min_value': comparable_vals[0][1] if comparable_vals else None,
                    'max_value': comparable_vals[-1][1] if comparable_vals else None,
                    'top_values': [
                        {'value': k, 'count': cnt}
                        for k, cnt in freq.most_common(25)
                    ],
                }

            if sub_action == 'save_layout':
                layout = dict(request.get('layout') or {})
                scope = str(request.get('scope') or 'specific').lower()
                object_key = (
                    f"{surface.server_id}:{surface.database_target_id or 'default'}:"
                    f"{surface.target_resource.get('resource_id') or surface.target_resource.get('display_name') or ''}"
                )
                if scope == 'template':
                    res = self.layout_store.save_template(
                        user_id,
                        'data-edit-surface',
                        str(request.get('template_name') or 'Custom Data Layout'),
                        layout,
                        description=str(request.get('description') or ''),
                    )
                    self._log(
                        surface,
                        'info',
                        'Save Template',
                        f"Saved layout template '{res['name']}'.",
                    )
                    return res
                res = self.layout_store.save_specific_layout(
                    user_id, 'data-edit-surface', object_key, layout
                )
                self._log(
                    surface,
                    'info',
                    'Save Layout',
                    f'Saved specific layout for {object_key}.',
                )
                return res

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

            raise ValueError(f'Unknown data surface action: {sub_action}')
