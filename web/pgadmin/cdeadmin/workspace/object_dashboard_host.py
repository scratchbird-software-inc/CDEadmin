##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Multi-engine Server, Database, and Table Dashboard & Rich Properties Host.

Implements a strict 3-tier query-churn architecture backed by the encrypted
FirebirdSQL Embedded `UserConfigurationDatabase`:

- Tier 1 (Auto-Snapshot on Selection / Manual Refresh): Fast O(1) catalog,
  shared-memory, and OS file header reads (<250ms). Opportunistically records
  numeric observations into `UserConfigurationDatabase` (`RAW`, `5M`, `1H`).
- Tier 2 (Opt-In Live Auto-Refresh): Controlled from the UI ribbon (`Off` by
  default) and paused when hidden.
- Tier 3 (Explicit User-Triggered Deep Stats): `COUNT(*)`, SQLite `dbstat` &
  `quick_check`, DuckDB `SUMMARIZE`, PostgreSQL `pgstattuple` (if installed),
  Firebird `RDB$PAGES` distribution, and large-schema scans. Never executed
  automatically on node click; cached in `UserConfigurationDatabase` with a
  `computed_at` timestamp.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user

from pgadmin.cdeadmin.design_store.robin_scene_engine import (
    compile_robin_scene,
    slice_scene_response,
)
from pgadmin.cdeadmin.navigator import resource_native
from pgadmin.cdeadmin.user_config_db import (
    UserConfigLockedError,
    get_user_config_db,
)

OBJECT_DASHBOARD_EXTENSION_KEY = 'cdeadmin_object_dashboard_host'

DEFAULT_DASHBOARD_CUSTOMIZATION: dict[str, Any] = {
    'show_comment_banner': True,
    'show_kpi_strip': True,
    'show_ddn_topology': True,
    'show_historic_charts': True,
    'show_storage_and_rankings': True,
    'show_deep_stats': True,
    'show_diagnostic_reports': True,
    'default_window': '1h',
}

DEFAULT_PROPERTIES_CUSTOMIZATION: dict[str, Any] = {
    'show_empty_attributes': False,
    'show_system_attributes': True,
    'show_native_registration_panel': True,
    'default_section_filter': 'all',
}

_SAFE_IDENT_RE = re.compile(r'^[A-Za-z0-9_$#@.\- ]{1,160}$')


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _format_bytes(num_bytes: float | int | None) -> str:
    if num_bytes is None or isinstance(num_bytes, bool):
        return '—'
    try:
        val = float(num_bytes)
    except (TypeError, ValueError):
        return '—'
    if not math.isfinite(val) or val < 0:
        return '—'
    units = ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB')
    idx = 0
    while val >= 1024.0 and idx < len(units) - 1:
        val /= 1024.0
        idx += 1
    if idx == 0:
        return f'{int(round(val))} B'
    return f'{val:.2f} {units[idx]}'


def _format_number(val: float | int | None, unit: str = 'count') -> str:
    if val is None or isinstance(val, bool):
        return '—'
    try:
        num = float(val)
    except (TypeError, ValueError):
        return str(val)
    if not math.isfinite(num):
        return '—'
    if unit == 'bytes':
        return _format_bytes(num)
    if unit == 'percent':
        return f'{num:.1f}%'
    if unit == 'per_sec':
        return f'{num:.2f}/s'
    if unit == 'ms':
        return f'{num:.1f} ms'
    if unit == 'seconds':
        if num >= 86400:
            days = int(num // 86400)
            hrs = int((num % 86400) // 3600)
            return f'{days}d {hrs}h'
        if num >= 3600:
            hrs = int(num // 3600)
            mins = int((num % 3600) // 60)
            return f'{hrs}h {mins}m'
        return f'{int(round(num))}s'
    if abs(num - round(num)) < 1e-6:
        return f'{int(round(num)):,}'
    return f'{num:,.2f}'


def _safe_float(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _quote_ident(ident: str, quote_char: str = '"') -> str:
    cleaned = str(ident or '').strip()
    if quote_char == '`':
        return '`' + cleaned.replace('`', '``') + '`'
    return '"' + cleaned.replace('"', '""') + '"'


def _extract_leading_sql_comment(ddl_sql: str | None) -> str:
    if not ddl_sql:
        return ''
    lines = str(ddl_sql).strip().splitlines()
    collected: list[str] = []
    for idx, line in enumerate(lines[:10]):
        s = line.strip()
        if s.startswith('--'):
            collected.append(s.lstrip('-').strip())
        elif s.startswith('/*') and s.endswith('*/'):
            collected.append(s[2:-2].strip())
        elif idx <= 2 and '--' in s and s.upper().startswith('CREATE '):
            collected.append(s.split('--', 1)[1].strip())
        elif collected:
            break
    return '\n'.join(c for c in collected if c).strip()


def _ddn_escape(text: Any) -> str:
    return str(text or '').replace('"', '""').replace('\n', ' ').strip()[:140]


def _ddn_id(prefix: str, raw: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_]+', '_', str(raw or 'item')).strip('_')[:48]
    return f'{prefix}_{cleaned or "item"}'


def _actor_user_id() -> int:
    try:
        if current_user and getattr(current_user, 'is_authenticated', False):
            return int(current_user.id)
    except Exception:
        pass
    return 1


def _resolve_owned_server(server_id: int | None):
    if not server_id or int(server_id) <= 0:
        return None
    try:
        from pgadmin.model import Server
        uid = _actor_user_id()
        srv = Server.query.filter_by(id=int(server_id), user_id=uid).first()
        if srv is not None:
            return srv
        return Server.query.filter_by(id=int(server_id)).first()
    except Exception:
        return None


def _resolve_engine_info(server, fallback_engine_id: str = '') -> dict[str, Any]:
    eng_id = str(fallback_engine_id or '').strip().lower()
    eng_label = ''
    profile_id = ''
    workflow = 'legacy_pg'
    route_cfg: dict[str, Any] = {}
    verified = False
    verified_version = ''

    if server is not None:
        ep = getattr(server, 'endpoint_profile', None)
        if ep is not None:
            workflow = 'provider_endpoint'
            profile_id = str(getattr(ep, 'profile_id', '') or '')
            try:
                from pgadmin.cdeadmin.endpoints import registration_profiles
                for prof in registration_profiles():
                    if prof.get('profile_id') == profile_id:
                        eng_id = str(prof.get('engine_id') or eng_id).lower()
                        eng_label = str(
                            prof.get('engine_display_name')
                            or prof.get('display_name')
                            or ''
                        )
                        break
            except Exception:
                pass
            if not eng_id and '-' in profile_id:
                eng_id = profile_id.split('-', 1)[0].lower()
            routes = getattr(ep, 'routes', None) or []
            primary = min(routes, key=lambda r: (r.priority, r.id), default=None)
            if primary is not None:
                try:
                    route_cfg = json.loads(primary.configuration or '{}')
                except Exception:
                    route_cfg = {}
            rt = getattr(ep, 'runtime_identity', None)
            if rt is not None:
                verified = getattr(rt, 'verification_state', None) == 'verified'
                verified_version = str(getattr(rt, 'verified_runtime_version', '') or '')
        else:
            eng_id = eng_id or 'postgresql'
            eng_label = 'PostgreSQL'

    if not eng_id:
        eng_id = 'postgresql'
    if not eng_label:
        eng_label = eng_id.replace('_', ' ').title()
        for canonical_id, canonical_name in (
            ('postgresql', 'PostgreSQL'),
            ('firebird', 'Firebird'),
            ('mysql', 'MySQL'),
            ('mariadb', 'MariaDB'),
            ('sqlite', 'SQLite'),
            ('duckdb', 'DuckDB'),
            ('clickhouse', 'ClickHouse'),
            ('cockroachdb', 'CockroachDB'),
            ('yugabytedb', 'YugabyteDB'),
            ('tidb', 'TiDB'),
            ('mongodb', 'MongoDB'),
            ('opensearch', 'OpenSearch'),
            ('scratchbird', 'ScratchBird'),
        ):
            if eng_id == canonical_id:
                eng_label = canonical_name
                break

    return {
        'engine_id': eng_id,
        'engine_label': eng_label,
        'profile_id': profile_id,
        'workflow': workflow,
        'route_cfg': route_cfg,
        'verified': verified,
        'verified_version': verified_version,
    }


def _normalize_scope(params: Mapping[str, Any]) -> dict[str, Any]:
    node_type = str(params.get('node_type') or '').strip()
    raw_kind = str(params.get('object_kind') or '').strip().lower()
    resource_id = str(params.get('resource_id') or '').strip()
    server_id = int(params.get('server_id') or params.get('sid') or 0)
    db_target_id = str(
        params.get('database_target_id') or params.get('did') or ''
    ).strip()
    schema_name = str(params.get('schema') or '').strip()
    object_name = str(params.get('object_name') or params.get('label') or '').strip()
    database_name = str(params.get('database_name') or '').strip()
    engine_id = str(params.get('engine_id') or '').strip().lower()

    if raw_kind in ('server', 'database', 'table', 'view', 'mview', 'foreign_table'):
        obj_kind = 'table' if raw_kind in ('table', 'view', 'mview', 'foreign_table') else raw_kind
    elif node_type == 'server':
        obj_kind = 'server'
    elif node_type in ('cde_database_target', 'database'):
        obj_kind = 'database'
    elif node_type in ('cde_resource', 'table', 'view', 'mview', 'foreign_table', 'partition'):
        if resource_id.startswith('database:') and raw_kind == 'database':
            obj_kind = 'database'
        else:
            obj_kind = 'table'
    else:
        obj_kind = raw_kind or 'object'

    if resource_id and ':' in resource_id and not object_name:
        object_name = resource_id.split(':', 1)[1]
    if '.' in object_name and not schema_name and obj_kind == 'table':
        parts = object_name.split('.', 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            schema_name, object_name = parts[0], parts[1]

    if obj_kind == 'server':
        object_key = f'server:{server_id}'
    elif obj_kind == 'database':
        db_ident = db_target_id or database_name or object_name or 'default'
        object_key = f'database:{server_id}:{db_ident}'
    else:
        tbl_ident = resource_id or (
            f'{schema_name}.{object_name}' if schema_name else (object_name or 'object')
        )
        object_key = f'{obj_kind}:{server_id}:{db_target_id or database_name}:{tbl_ident}'

    return {
        'node_type': node_type,
        'object_kind': obj_kind,
        'raw_kind': raw_kind or obj_kind,
        'object_key': object_key[:320],
        'server_id': server_id,
        'database_target_id': db_target_id,
        'database_name': database_name,
        'resource_id': resource_id,
        'schema': schema_name,
        'object_name': object_name,
        'engine_id': engine_id,
    }


class ObjectDashboardHost:
    """Server-side multi-engine dashboard, deep-stats, and properties coordinator."""

    def __init__(self, app, workspace_service):
        self.app = app
        self.workspace = workspace_service

    # ------------------------------------------------------------------
    # Ephemeral Read-Only Query Runner (Does NOT pollute SQL Editor history)
    # ------------------------------------------------------------------

    def _open_ephemeral_provider_runner(
        self, server, database_target_id: str | None
    ):
        """Return `(run_sql_fn, close_fn, context, endpoint)` or `(None, ...)`."""
        if server is None or self.workspace is None:
            return None, (lambda: None), None, None
        target_arg = database_target_id if database_target_id else Ellipsis
        try:
            context, endpoint, _root = self.workspace.endpoint_service.workspace(
                server, database_target_id=target_arg
            )
            binding = self.workspace.endpoint_service.provider_registry.resolve(context)
            langs = self.workspace.studio_service.languages(context) or []
            lang_profile = None
            for item in langs:
                if isinstance(item, dict) and item.get('language_profile'):
                    lang_profile = item['language_profile']
                    break
                elif isinstance(item, str) and item:
                    lang_profile = item
                    break
            if not lang_profile:
                prof = getattr(binding.instance, 'profile', None)
                lang_profile = getattr(prof, 'language_profile', None)
            if not lang_profile:
                return None, (lambda: None), context, endpoint

            ep_with_target = copy.deepcopy(endpoint)
            if database_target_id:
                ep_with_target['route'] = {
                    **ep_with_target.get('route', {}),
                    'database_target_id': database_target_id,
                }
            opened = self.workspace.studio_service.open_session(
                context, ep_with_target, lang_profile
            )
            session_id = opened['provider_session']['session_id']
        except Exception:
            return None, (lambda: None), None, None

        def run_sql(sql: str, parameters: Any = None, max_rows: int = 100) -> list[dict[str, Any]]:
            occ = self.workspace.studio_service.execute(
                context,
                session_id,
                sql,
                parameters=parameters if parameters is not None else {},
                output_policy={'redact_keys': []},
            )
            occ_id = occ['occurrence_id']
            polled = occ
            if not polled.get('operation', {}).get('terminal', True):
                for _ in range(150):
                    polled = self.workspace.studio_service.poll(context, occ_id)
                    if polled.get('operation', {}).get('terminal'):
                        break
                    time.sleep(0.02)
            res = polled.get('result')
            if res is None:
                return []
            renderer = binding.instance.select_renderer(copy.deepcopy(res))
            desc = self.workspace.studio_service.admit_result(
                context, occ_id, renderer.get('capability_ids', ())
            )
            result_id = desc['result_id']
            try:
                rendered = self.workspace.result_service.render(
                    result_id,
                    page_size=max(1, min(500, int(max_rows))),
                    endpoint_id=context.endpoint_id,
                )
                vm = rendered.get('view_model') or {}
                raw_rows = vm.get('rows', vm.get('records', []))
                cols = [
                    c.get('name') if isinstance(c, dict) else str(c)
                    for c in (vm.get('columns') or [])
                ]
                normalized: list[dict[str, Any]] = []
                for r in raw_rows or []:
                    if isinstance(r, dict):
                        normalized.append(
                            {
                                str(k): (v.get('value') if isinstance(v, dict) and 'value' in v else v)
                                for k, v in r.items()
                            }
                        )
                    elif isinstance(r, (list, tuple)) and cols:
                        row_dict: dict[str, Any] = {}
                        for idx, cname in enumerate(cols):
                            cell = r[idx] if idx < len(r) else None
                            row_dict[str(cname)] = (
                                cell.get('value')
                                if isinstance(cell, dict) and 'value' in cell
                                else cell
                            )
                        normalized.append(row_dict)
                return normalized
            finally:
                try:
                    self.workspace.result_service.release(
                        result_id, endpoint_id=context.endpoint_id
                    )
                except Exception:
                    pass

        def close_runner() -> None:
            try:
                self.workspace.studio_service.close_session(context, session_id)
            except Exception:
                pass

        return run_sql, close_runner, context, endpoint

    def _open_pg_legacy_runner(self, server_id: int, did: str | None = None):
        """Return `(run_sql_fn, connected_bool)` for legacy PostgreSQL connections."""
        if not server_id:
            return None, False
        try:
            from pgadmin.utils.driver.registry import DriverRegistry
            manager = DriverRegistry.get('psycopg3').connection_manager(int(server_id))
            conn = (
                manager.connection(did=int(did))
                if did and str(did).isdigit()
                else manager.connection()
            )
            if not conn or not conn.connected():
                return None, False

            def run_pg_sql(sql: str, params: Any = None, max_rows: int = 100) -> list[dict[str, Any]]:
                status, res = conn.execute_dict(sql, params)
                if not status or not isinstance(res, dict):
                    return []
                rows = res.get('rows') or []
                return list(rows[:max_rows])

            return run_pg_sql, True
        except Exception:
            return None, False

    def _load_provider_snapshot_safe(
        self, server, database_target_id: str | None
    ) -> dict[str, Any] | None:
        if server is None or self.workspace is None:
            return None
        try:
            target_arg = database_target_id if database_target_id else None
            return self.workspace.navigator_snapshot(
                server, database_target_id=target_arg
            )
        except Exception:
            if database_target_id:
                return None
            try:
                return self.workspace.navigator_snapshot(server)
            except Exception:
                return None

    def _inspect_local_files(
        self, route_cfg: Mapping[str, Any], extra_path: str = ''
    ) -> dict[str, Any]:
        candidate = (
            str(extra_path or '').strip()
            or str(route_cfg.get('path') or '').strip()
            or str(route_cfg.get('database_path') or '').strip()
            or str(route_cfg.get('database') or '').strip()
        )
        if not candidate or candidate == ':memory:' or '://' in candidate:
            return {}
        if not os.path.isabs(candidate) or not os.path.exists(candidate):
            return {'configured_path': candidate}
        out: dict[str, Any] = {'path': candidate}
        try:
            st = os.stat(candidate)
            out['main_bytes'] = int(st.st_size)
            out['modified_at'] = datetime.fromtimestamp(
                st.st_mtime, tz=timezone.utc
            ).isoformat().replace('+00:00', 'Z')
        except OSError:
            return out
        for suffix, key in (
            ('-wal', 'wal_bytes'),
            ('.wal', 'wal_bytes'),
            ('-shm', 'shm_bytes'),
            ('-journal', 'journal_bytes'),
        ):
            sidecar = candidate + suffix
            if os.path.exists(sidecar):
                try:
                    out[key] = int(os.stat(sidecar).st_size)
                except OSError:
                    pass
        out['total_on_disk_bytes'] = sum(
            int(out.get(k) or 0)
            for k in ('main_bytes', 'wal_bytes', 'shm_bytes', 'journal_bytes')
        )
        return out

    # ------------------------------------------------------------------
    # Tier-1 Snapshot Assembly
    # ------------------------------------------------------------------

    def collect_snapshot(
        self,
        params: Mapping[str, Any],
        *,
        window: str = '1h',
        record_sample: bool = True,
    ) -> dict[str, Any]:
        uid = _actor_user_id()
        scope = _normalize_scope(params)
        server = _resolve_owned_server(scope['server_id'])
        eng_info = _resolve_engine_info(server, scope['engine_id'])
        engine_id = eng_info['engine_id']
        engine_label = eng_info['engine_label']
        obj_kind = scope['object_kind']

        kpis: list[dict[str, Any]] = []
        storage_bars: list[dict[str, Any]] = []
        rankings: list[dict[str, Any]] = []
        reports: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        ddn_nodes: list[dict[str, Any]] = []
        ddn_edges: list[dict[str, Any]] = []

        comment_text = ''
        comment_source = ''
        comment_supported = engine_id in {
            'postgresql', 'cockroachdb', 'yugabytedb', 'firebird', 'mysql',
            'mariadb', 'tidb', 'vitess', 'dolt', 'duckdb', 'clickhouse',
            'snowflake', 'databricks', 'bigquery', 'oracle', 'mssql', 'db2',
            'scratchbird',
        }
        epoch_id = ''
        connected = False

        # Server registration comment fallback
        if obj_kind == 'server' and server is not None:
            srv_comment = str(getattr(server, 'comment', '') or '').strip()
            if srv_comment:
                comment_text = srv_comment
                comment_source = 'server_registration'
                comment_supported = True

        # Local file inspection (zero-query OS stat for embedded/file DBs)
        local_files = self._inspect_local_files(
            eng_info['route_cfg'],
            extra_path=scope['database_name'] if os.path.sep in scope['database_name'] else '',
        )
        if local_files.get('main_bytes') is not None and obj_kind in ('server', 'database'):
            total_disk = int(local_files.get('total_on_disk_bytes') or local_files['main_bytes'])
            observations.append({
                'metric_key': 'storage.disk_bytes',
                'label': 'On-Disk Footprint',
                'group': 'storage',
                'kind': 'gauge',
                'unit': 'bytes',
                'value': total_disk,
            })

        # Provider Snapshot (if provider_endpoint)
        snapshot = None
        if eng_info['workflow'] == 'provider_endpoint' and eng_info['verified']:
            snapshot = self._load_provider_snapshot_safe(
                server, scope['database_target_id'] or None
            )
            if snapshot is not None:
                connected = True

        # Open fast read-only SQL runner when connected/verified
        run_sql = None
        close_sql = lambda: None
        if eng_info['workflow'] == 'provider_endpoint' and eng_info['verified']:
            run_sql, close_sql, _ctx, _ep = self._open_ephemeral_provider_runner(
                server, scope['database_target_id'] or None
            )
            if run_sql is not None:
                connected = True
        elif eng_info['workflow'] == 'legacy_pg' and scope['server_id']:
            run_sql, pg_conn = self._open_pg_legacy_runner(
                scope['server_id'], scope['database_target_id'] or None
            )
            if pg_conn:
                connected = True

        try:
            # Extract universal catalog counts, comments, and native metrics from snapshot
            snap_summary = self._extract_snapshot_telemetry(
                snapshot, scope, engine_id, observations, kpis, storage_bars, rankings, ddn_nodes, ddn_edges
            )
            if snap_summary.get('comment') and not comment_text:
                comment_text = snap_summary['comment']
                comment_source = snap_summary.get('comment_source') or 'catalog'
            if snap_summary.get('epoch_id'):
                epoch_id = snap_summary['epoch_id']

            # Engine-family live Tier-1 fast SQL telemetry (bounded O(1) views only!)
            if run_sql is not None:
                live_meta = self._collect_live_sql_tier1(
                    run_sql,
                    engine_id=engine_id,
                    scope=scope,
                    local_files=local_files,
                    observations=observations,
                    kpis=kpis,
                    storage_bars=storage_bars,
                    rankings=rankings,
                    reports=reports,
                    ddn_nodes=ddn_nodes,
                    ddn_edges=ddn_edges,
                )
                if live_meta.get('comment') and not comment_text:
                    comment_text = live_meta['comment']
                    comment_source = live_meta.get('comment_source') or 'live_catalog'
                if live_meta.get('epoch_id'):
                    epoch_id = live_meta['epoch_id']
        finally:
            close_sql()

        # Fallback KPIs from local_files when offline or embedded
        if local_files.get('main_bytes') is not None and not any(
            k['id'] in ('db_size', 'disk_size', 'allocated_bytes') for k in kpis
        ):
            kpis.append({
                'id': 'disk_size',
                'label': 'Database File Size',
                'value': local_files['main_bytes'],
                'formatted': _format_bytes(local_files['main_bytes']),
                'unit': 'bytes',
                'subtext': (
                    f"WAL: {_format_bytes(local_files.get('wal_bytes', 0))}"
                    if local_files.get('wal_bytes')
                    else (local_files.get('path') or '')
                ),
                'status': 'ok',
            })
            if local_files.get('wal_bytes') or local_files.get('shm_bytes'):
                total_b = max(1, int(local_files.get('total_on_disk_bytes') or 1))
                segs = [
                    {
                        'id': 'main',
                        'label': 'Main Database',
                        'bytes': local_files['main_bytes'],
                        'pct': round(100.0 * local_files['main_bytes'] / total_b, 1),
                        'formatted': _format_bytes(local_files['main_bytes']),
                        'tone': 'primary',
                    }
                ]
                if local_files.get('wal_bytes'):
                    segs.append({
                        'id': 'wal',
                        'label': 'Write-Ahead Log (WAL)',
                        'bytes': local_files['wal_bytes'],
                        'pct': round(100.0 * local_files['wal_bytes'] / total_b, 1),
                        'formatted': _format_bytes(local_files['wal_bytes']),
                        'tone': 'warning',
                    })
                if local_files.get('shm_bytes'):
                    segs.append({
                        'id': 'shm',
                        'label': 'Shared Memory Index',
                        'bytes': local_files['shm_bytes'],
                        'pct': round(100.0 * local_files['shm_bytes'] / total_b, 1),
                        'formatted': _format_bytes(local_files['shm_bytes']),
                        'tone': 'neutral',
                    })
                storage_bars.append({
                    'id': 'file_composition',
                    'title': 'On-Disk File Footprint',
                    'total_bytes': total_b,
                    'total_formatted': _format_bytes(total_b),
                    'segments': segs,
                })

        # Opportunistic Historic Recording & History Query in Firebird Embedded Vault
        history_payload: dict[str, Any] = {
            'window': window,
            'resolution': 'raw',
            'series': [],
            'retention_policy': {'raw_hours': 24, 'rollup_5m_days': 30, 'rollup_1h_days': 365},
            'vault_unlocked': False,
        }
        cached_deep: dict[str, Any] | None = None
        customization = dict(DEFAULT_DASHBOARD_CUSTOMIZATION)

        try:
            ucfg = get_user_config_db()
            if ucfg.is_unlocked():
                history_payload['vault_unlocked'] = True
                stored_cust = ucfg.get_object_view_customization(uid, 'object_dashboard')
                if stored_cust:
                    customization.update(stored_cust)

                if record_sample and observations:
                    rec_out = ucfg.record_object_metric_observations(
                        user_id=uid,
                        engine_id=engine_id,
                        server_id=scope['server_id'],
                        database_target_id=scope['database_target_id'],
                        object_kind=obj_kind,
                        object_key=scope['object_key'],
                        observations=observations,
                        epoch_id=epoch_id,
                    )
                    # Surface any freshly computed counter_rate values as KPIs if helpful
                    rates = rec_out.get('computed_rates') or {}
                    for r_key, r_val in rates.items():
                        if r_key == 'tx.commits_per_sec' and not any(
                            k['id'] == 'commits_rate' for k in kpis
                        ):
                            kpis.append({
                                'id': 'commits_rate',
                                'label': 'Commit Throughput',
                                'value': r_val,
                                'formatted': _format_number(r_val, 'per_sec'),
                                'unit': 'per_sec',
                                'subtext': 'Monotonic delta rate',
                                'status': 'ok',
                            })

                history_payload = {
                    **ucfg.query_object_metric_history(
                        user_id=uid,
                        object_kind=obj_kind,
                        object_key=scope['object_key'],
                        window=window,
                    ),
                    'vault_unlocked': True,
                }
                cached_deep = ucfg.get_on_demand_object_stats(
                    user_id=uid,
                    object_kind=obj_kind,
                    object_key=scope['object_key'],
                    server_id=scope['server_id'],
                    database_target_id=scope['database_target_id'],
                )
        except UserConfigLockedError:
            pass
        except Exception:
            pass

        # Build host-compiled DDN scene for DDNViewerSurface
        title_name = (
            scope['object_name']
            or scope['database_name']
            or getattr(server, 'name', '')
            or scope['object_key']
        )
        ddn_text, ddn_scene = self._build_dashboard_ddn_scene(
            obj_kind=obj_kind,
            title_name=title_name,
            engine_label=engine_label,
            connected=connected,
            kpis=kpis,
            ddn_nodes=ddn_nodes,
            ddn_edges=ddn_edges,
        )

        deep_actions = self._available_deep_actions(engine_id, obj_kind)

        status_banner = None
        if not connected:
            status_banner = (
                'Endpoint is not currently connected — displaying registration metadata'
                + (
                    ' and historic metrics stored in UserConfigurationDatabase.'
                    if history_payload.get('series')
                    else '. Connect to collect live telemetry.'
                )
            )

        return {
            'captured_at': _now_iso(),
            'object_identity': {
                'object_kind': obj_kind,
                'raw_kind': scope['raw_kind'],
                'object_key': scope['object_key'],
                'title': title_name,
                'subtitle': f'{engine_label} · {obj_kind.capitalize()}',
                'engine_id': engine_id,
                'engine_label': engine_label,
                'server_id': scope['server_id'],
                'server_name': getattr(server, 'name', '') if server is not None else '',
                'host': getattr(server, 'host', '') if server is not None else '',
                'port': getattr(server, 'port', None) if server is not None else None,
                'database_target_id': scope['database_target_id'],
                'database_name': scope['database_name'],
                'resource_id': scope['resource_id'],
                'schema': scope['schema'],
                'object_name': scope['object_name'],
                'connected': connected,
                'verified_version': eng_info['verified_version'],
                'status_banner': status_banner,
            },
            'comment': {
                'text': comment_text,
                'supported': comment_supported,
                'source': comment_source,
            },
            'kpis': kpis,
            'storage_bars': storage_bars,
            'rankings': rankings,
            'history': history_payload,
            'ddn': {
                'ddn_text': ddn_text,
                'scene': ddn_scene,
            },
            'deep_stats': {
                'available_actions': deep_actions,
                'cached': cached_deep,
            },
            'reports': reports,
            'customization': customization,
        }

    # ------------------------------------------------------------------
    # Provider Snapshot Extraction (All 24+ Engines)
    # ------------------------------------------------------------------

    def _extract_snapshot_telemetry(
        self,
        snapshot: Mapping[str, Any] | None,
        scope: Mapping[str, Any],
        engine_id: str,
        observations: list[dict[str, Any]],
        kpis: list[dict[str, Any]],
        storage_bars: list[dict[str, Any]],
        rankings: list[dict[str, Any]],
        ddn_nodes: list[dict[str, Any]],
        ddn_edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        out: dict[str, Any] = {'comment': '', 'comment_source': '', 'epoch_id': ''}
        if not snapshot:
            return out

        resources = snapshot.get('resources') or []
        obj_kind = scope['object_kind']
        kind_counts: dict[str, int] = {}
        db_items: list[dict[str, Any]] = []
        table_items: list[dict[str, Any]] = []
        matched_table_res: dict[str, Any] | None = None

        for res in resources:
            rkind = str(res.get('resource_kind') or '')
            if not rkind:
                continue
            native = resource_native(res)
            if not native.get('system_object'):
                kind_counts[rkind] = kind_counts.get(rkind, 0) + 1

            if rkind == 'server':
                ver = native.get('version') or native.get('server_version')
                if ver and not any(k['id'] == 'server_version' for k in kpis):
                    kpis.append({
                        'id': 'server_version',
                        'label': 'Engine Version',
                        'value': str(ver),
                        'formatted': str(ver),
                        'unit': 'text',
                        'subtext': str(native.get('architecture') or native.get('edition') or ''),
                        'status': 'ok',
                    })
                conns = _safe_float(native.get('connection_count'))
                if conns is not None:
                    observations.append({
                        'metric_key': 'sessions.total',
                        'label': 'Active Attachments / Sessions',
                        'group': 'sessions',
                        'kind': 'gauge',
                        'unit': 'count',
                        'value': conns,
                    })
                    kpis.append({
                        'id': 'active_connections',
                        'label': 'Attachments',
                        'value': conns,
                        'formatted': _format_number(conns),
                        'unit': 'count',
                        'subtext': 'Connected sessions',
                        'status': 'ok',
                    })

            elif rkind == 'database':
                db_items.append({'res': res, 'native': native})
                if obj_kind == 'database':
                    desc = str(
                        native.get('comment')
                        or native.get('description')
                        or res.get('description')
                        or ''
                    ).strip()
                    if desc and not out['comment']:
                        out['comment'] = desc
                        out['comment_source'] = 'database_catalog'
                    if native.get('creation_date'):
                        out['epoch_id'] = str(native['creation_date'])

                    page_sz = _safe_float(native.get('page_size'))
                    alloc_pages = _safe_float(native.get('allocated_pages'))
                    if page_sz and alloc_pages:
                        db_bytes = page_sz * alloc_pages
                        observations.append({
                            'metric_key': 'storage.allocated_bytes',
                            'label': 'Allocated Database Space',
                            'group': 'storage',
                            'kind': 'gauge',
                            'unit': 'bytes',
                            'value': db_bytes,
                        })
                        kpis.append({
                            'id': 'allocated_bytes',
                            'label': 'Allocated Space',
                            'value': db_bytes,
                            'formatted': _format_bytes(db_bytes),
                            'unit': 'bytes',
                            'subtext': f'{int(alloc_pages):,} pages × {int(page_sz):,} B',
                            'status': 'ok',
                        })

                    # Firebird OIT / OAT / Next Transaction Horizon Health!
                    oit = _safe_float(native.get('oldest_transaction'))
                    oat = _safe_float(native.get('oldest_active'))
                    nxt = _safe_float(native.get('next_transaction'))
                    sweep = _safe_float(native.get('sweep_interval')) or 20000.0
                    if oit is not None and nxt is not None and nxt >= oit:
                        tx_gap = nxt - oit
                        oat_gap = (nxt - oat) if (oat is not None and nxt >= oat) else tx_gap
                        cap_pct = min(100.0, round(100.0 * tx_gap / max(1.0, sweep), 1)) if sweep > 0 else 0.0
                        observations.append({
                            'metric_key': 'tx.horizon_gap',
                            'label': 'Transaction Horizon Gap (Next - OIT)',
                            'group': 'transactions',
                            'kind': 'gauge',
                            'unit': 'count',
                            'value': tx_gap,
                        })
                        observations.append({
                            'metric_key': 'tx.next_id',
                            'label': 'Transaction Throughput',
                            'group': 'transactions',
                            'kind': 'counter_rate',
                            'unit': 'per_sec',
                            'raw_counter': nxt,
                        })
                        kpis.append({
                            'id': 'tx_horizon_gap',
                            'label': 'Tx Horizon Gap (Next − OIT)',
                            'value': tx_gap,
                            'formatted': _format_number(tx_gap),
                            'unit': 'count',
                            'subtext': f'OAT gap: {_format_number(oat_gap)} · Sweep: {_format_number(sweep)}',
                            'capacity_pct': cap_pct,
                            'warn_pct': 80,
                            'crit_pct': 95,
                            'status': 'critical' if cap_pct >= 95 else ('warning' if cap_pct >= 80 else 'ok'),
                        })

            elif rkind in ('table', 'view', 'materialized-view', 'virtual-table', 'fts-table', 'collection', 'measurement'):
                if not native.get('system_object'):
                    table_items.append({'res': res, 'native': native})
                rid = str(res.get('resource_id') or '')
                dname = str(res.get('display_name') or res.get('name') or '')
                if obj_kind == 'table' and (
                    (scope['resource_id'] and rid == scope['resource_id'])
                    or (scope['object_name'] and dname.lower() == scope['object_name'].lower())
                ):
                    matched_table_res = {'res': res, 'native': native}

        # Object inventory summary for Server / Database
        if obj_kind in ('server', 'database') and kind_counts:
            tbl_cnt = kind_counts.get('table', 0) + kind_counts.get('collection', 0)
            view_cnt = kind_counts.get('view', 0)
            idx_cnt = kind_counts.get('index', 0)
            observations.append({
                'metric_key': 'catalog.table_count',
                'label': 'User Tables / Collections',
                'group': 'catalog',
                'kind': 'gauge',
                'unit': 'count',
                'value': tbl_cnt,
            })
            kpis.append({
                'id': 'catalog_objects',
                'label': 'User Tables',
                'value': tbl_cnt,
                'formatted': _format_number(tbl_cnt),
                'unit': 'count',
                'subtext': f'{view_cnt} views · {idx_cnt} indexes',
                'status': 'ok',
            })

            for item in table_items[:8]:
                r = item['res']
                nat = item['native']
                tname = str(r.get('display_name') or r.get('name') or r.get('resource_id'))
                est_sz = _safe_float(
                    nat.get('total_bytes') or nat.get('size_bytes') or nat.get('estimated_size')
                )
                ddn_nodes.append({
                    'id': _ddn_id('tbl', tname),
                    'title': tname,
                    'level': 'physical',
                    'fields': [
                        ('kind', str(r.get('resource_kind') or 'table')),
                        *(
                            [('estimate', _format_number(est_sz))]
                            if est_sz is not None
                            else []
                        ),
                    ],
                })

        if obj_kind == 'table' and matched_table_res is not None:
            res = matched_table_res['res']
            nat = matched_table_res['native']
            desc = str(
                nat.get('comment')
                or nat.get('description')
                or res.get('description')
                or _extract_leading_sql_comment(nat.get('sql') or nat.get('ddl'))
                or ''
            ).strip()
            if desc and not out['comment']:
                out['comment'] = desc
                out['comment_source'] = 'table_catalog'
            cols = nat.get('columns') or []
            idxs = nat.get('indexes') or []
            cons = nat.get('constraints') or []
            if isinstance(cols, list) and cols:
                kpis.append({
                    'id': 'column_count',
                    'label': 'Columns',
                    'value': len(cols),
                    'formatted': _format_number(len(cols)),
                    'unit': 'count',
                    'subtext': f'{len(idxs) if isinstance(idxs, list) else 0} indexes · {len(cons) if isinstance(cons, list) else 0} constraints',
                    'status': 'ok',
                })
                ddn_nodes.append({
                    'id': _ddn_id('focus_tbl', scope['object_name'] or 'table'),
                    'title': scope['object_name'] or str(res.get('display_name') or 'Table'),
                    'level': 'physical',
                    'fields': [
                        (
                            str(c.get('name') or f'col_{i}'),
                            str(c.get('type') or c.get('data_type') or ' column'),
                        )
                        for i, c in enumerate(cols[:12])
                        if isinstance(c, dict)
                    ],
                })

        return out

    # ------------------------------------------------------------------
    # Engine-Family Fast Tier-1 SQL Telemetry
    # ------------------------------------------------------------------

    def _collect_live_sql_tier1(
        self,
        run_sql,
        *,
        engine_id: str,
        scope: Mapping[str, Any],
        local_files: Mapping[str, Any],
        observations: list[dict[str, Any]],
        kpis: list[dict[str, Any]],
        storage_bars: list[dict[str, Any]],
        rankings: list[dict[str, Any]],
        reports: list[dict[str, Any]],
        ddn_nodes: list[dict[str, Any]],
        ddn_edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        out: dict[str, Any] = {'comment': '', 'comment_source': '', 'epoch_id': ''}
        obj_kind = scope['object_kind']

        def safe_query(sql: str, params: Any = None, max_rows: int = 100) -> list[dict[str, Any]]:
            try:
                return run_sql(sql, params, max_rows=max_rows) or []
            except Exception:
                return []

        # 1. PostgreSQL / CockroachDB / YugabyteDB Family
        if engine_id in ('postgresql', 'cockroachdb', 'yugabytedb', 'babelfish'):
            self._probe_postgres_tier1(
                safe_query, scope, out, observations, kpis, storage_bars, rankings, reports, ddn_nodes, ddn_edges
            )

        # 2. Firebird 5.0 (Network & Embedded)
        elif engine_id == 'firebird':
            self._probe_firebird_tier1(
                safe_query, scope, out, observations, kpis, storage_bars, rankings, reports
            )

        # 3. MySQL / MariaDB / TiDB / Vitess / Dolt Family
        elif engine_id in ('mysql', 'mariadb', 'tidb', 'vitess', 'dolt'):
            self._probe_mysql_family_tier1(
                safe_query, scope, out, observations, kpis, storage_bars, rankings, reports
            )

        # 4. SQLite 3
        elif engine_id == 'sqlite':
            self._probe_sqlite_tier1(
                safe_query, scope, local_files, out, observations, kpis, storage_bars, rankings, reports
            )

        # 5. DuckDB
        elif engine_id == 'duckdb':
            self._probe_duckdb_tier1(
                safe_query, scope, out, observations, kpis, storage_bars, rankings, reports
            )

        # 6. ClickHouse
        elif engine_id == 'clickhouse':
            self._probe_clickhouse_tier1(
                safe_query, scope, out, observations, kpis, storage_bars, rankings, reports
            )

        return out

    def _probe_postgres_tier1(
        self, safe_query, scope, out, observations, kpis, storage_bars, rankings, reports, ddn_nodes, ddn_edges
    ) -> None:
        obj_kind = scope['object_kind']
        boot_rows = safe_query(
            "SELECT CAST(pg_postmaster_start_time() AS TEXT) AS boot_ts, "
            "EXTRACT(EPOCH FROM (now() - pg_postmaster_start_time())) AS uptime_s, "
            "current_setting('max_connections')::int AS max_conns, "
            "current_database() AS cur_db"
        )
        max_conns = 100.0
        cur_db = scope['database_name']
        if boot_rows:
            b = boot_rows[0]
            out['epoch_id'] = str(b.get('boot_ts') or '')
            cur_db = str(b.get('cur_db') or cur_db or '')
            max_conns = _safe_float(b.get('max_conns')) or 100.0
            up_s = _safe_float(b.get('uptime_s'))
            if up_s is not None and obj_kind == 'server':
                kpis.append({
                    'id': 'uptime',
                    'label': 'Server Uptime',
                    'value': up_s,
                    'formatted': _format_number(up_s, 'seconds'),
                    'unit': 'seconds',
                    'subtext': f'Max connections: {int(max_conns)}',
                    'status': 'ok',
                })

        if obj_kind in ('server', 'database'):
            sess_rows = safe_query(
                "SELECT pid, usename AS username, datname AS database_name, "
                "COALESCE(state, 'background') AS state, wait_event_type, "
                "LEFT(COALESCE(query, ''), 140) AS query_preview "
                "FROM pg_stat_activity WHERE pid <> pg_backend_pid() LIMIT 60"
            )
            total_sess = float(len(sess_rows) + 1)
            active_sess = float(sum(1 for r in sess_rows if r.get('state') == 'active') + 1)
            cap_pct = min(100.0, round(100.0 * total_sess / max(1.0, max_conns), 1))
            observations.extend([
                {'metric_key': 'sessions.total', 'label': 'Total Sessions', 'group': 'sessions', 'kind': 'gauge', 'unit': 'count', 'value': total_sess},
                {'metric_key': 'sessions.active', 'label': 'Active Queries', 'group': 'sessions', 'kind': 'gauge', 'unit': 'count', 'value': active_sess},
            ])
            if not any(k['id'] == 'active_connections' for k in kpis):
                kpis.append({
                    'id': 'active_connections',
                    'label': 'Connections',
                    'value': total_sess,
                    'formatted': f'{int(total_sess)} / {int(max_conns)}',
                    'unit': 'count',
                    'subtext': f'{int(active_sess)} active',
                    'capacity_pct': cap_pct,
                    'warn_pct': 80,
                    'crit_pct': 92,
                    'status': 'critical' if cap_pct >= 92 else ('warning' if cap_pct >= 80 else 'ok'),
                })
            if sess_rows:
                reports.append({
                    'id': 'sessions',
                    'title': 'Active Server Sessions',
                    'description': 'Current client backends from pg_stat_activity',
                    'columns': ['pid', 'username', 'database_name', 'state', 'wait_event_type', 'query_preview'],
                    'rows': sess_rows,
                })

            stat_filter = '' if obj_kind == 'server' else 'WHERE datname = current_database()'
            db_stats = safe_query(
                f'SELECT COALESCE(SUM(xact_commit), 0) AS commits, '
                f'COALESCE(SUM(xact_rollback), 0) AS rollbacks, '
                f'COALESCE(SUM(blks_hit), 0) AS blks_hit, '
                f'COALESCE(SUM(blks_read), 0) AS blks_read, '
                f'COALESCE(SUM(tup_inserted + tup_updated + tup_deleted), 0) AS tup_mutated, '
                f'COALESCE(SUM(deadlocks), 0) AS deadlocks '
                f'FROM pg_stat_database {stat_filter}'
            )
            if db_stats:
                ds = db_stats[0]
                commits = _safe_float(ds.get('commits')) or 0.0
                rollbacks = _safe_float(ds.get('rollbacks')) or 0.0
                hits = _safe_float(ds.get('blks_hit')) or 0.0
                reads = _safe_float(ds.get('blks_read')) or 0.0
                hit_pct = round(100.0 * hits / (hits + reads), 2) if (hits + reads) > 0 else 100.0
                observations.extend([
                    {'metric_key': 'tx.commits_per_sec', 'label': 'Commits / sec', 'group': 'transactions', 'kind': 'counter_rate', 'unit': 'per_sec', 'raw_counter': commits},
                    {'metric_key': 'tx.rollbacks_per_sec', 'label': 'Rollbacks / sec', 'group': 'transactions', 'kind': 'counter_rate', 'unit': 'per_sec', 'raw_counter': rollbacks},
                    {'metric_key': 'cache.hit_ratio_pct', 'label': 'Buffer Cache Hit %', 'group': 'memory', 'kind': 'gauge', 'unit': 'percent', 'value': hit_pct},
                ])
                kpis.append({
                    'id': 'cache_hit_pct',
                    'label': 'Buffer Cache Hit Ratio',
                    'value': hit_pct,
                    'formatted': _format_number(hit_pct, 'percent'),
                    'unit': 'percent',
                    'subtext': f'{int(commits):,} commits · {int(rollbacks):,} rollbacks',
                    'capacity_pct': hit_pct,
                    'status': 'ok' if hit_pct >= 90 else 'warning',
                })

        if obj_kind == 'server':
            dbs = safe_query(
                "SELECT d.datname AS name, pg_database_size(d.oid) AS size_bytes, "
                "COALESCE(shobj_description(d.oid, 'pg_database'), '') AS comment "
                "FROM pg_database d WHERE NOT d.datistemplate ORDER BY size_bytes DESC LIMIT 12"
            )
            if dbs:
                max_sz = max(1.0, max((_safe_float(r.get('size_bytes')) or 0.0) for r in dbs))
                rankings.append({
                    'id': 'top_databases',
                    'title': 'Databases by On-Disk Size',
                    'unit': 'bytes',
                    'items': [
                        {
                            'id': str(r.get('name')),
                            'label': str(r.get('name')),
                            'value': _safe_float(r.get('size_bytes')) or 0.0,
                            'formatted': _format_bytes(r.get('size_bytes')),
                            'pct_of_max': round(100.0 * (_safe_float(r.get('size_bytes')) or 0.0) / max_sz, 1),
                            'sublabel': str(r.get('comment') or '')[:72],
                        }
                        for r in dbs
                    ],
                })

        elif obj_kind == 'database':
            db_meta = safe_query(
                "SELECT pg_database_size(current_database()) AS size_bytes, "
                "COALESCE(shobj_description((SELECT oid FROM pg_database WHERE datname = current_database()), 'pg_database'), '') AS comment"
            )
            if db_meta:
                sz = _safe_float(db_meta[0].get('size_bytes'))
                if sz is not None:
                    observations.append({'metric_key': 'storage.total_bytes', 'label': 'Database Size', 'group': 'storage', 'kind': 'gauge', 'unit': 'bytes', 'value': sz})
                    kpis.append({'id': 'db_size', 'label': 'Database Size', 'value': sz, 'formatted': _format_bytes(sz), 'unit': 'bytes', 'subtext': cur_db, 'status': 'ok'})
                if db_meta[0].get('comment'):
                    out['comment'] = str(db_meta[0]['comment']).strip()
                    out['comment_source'] = 'shobj_description'

            top_tbls = safe_query(
                "SELECT schemaname || '.' || relname AS full_name, "
                "pg_total_relation_size(relid) AS total_bytes, n_live_tup AS est_rows "
                "FROM pg_stat_user_tables ORDER BY total_bytes DESC LIMIT 12"
            )
            if top_tbls:
                max_t = max(1.0, max((_safe_float(r.get('total_bytes')) or 0.0) for r in top_tbls))
                rankings.append({
                    'id': 'top_tables',
                    'title': 'Largest Tables (Heap + TOAST + Indexes)',
                    'unit': 'bytes',
                    'items': [
                        {
                            'id': str(r.get('full_name')),
                            'label': str(r.get('full_name')),
                            'value': _safe_float(r.get('total_bytes')) or 0.0,
                            'formatted': _format_bytes(r.get('total_bytes')),
                            'pct_of_max': round(100.0 * (_safe_float(r.get('total_bytes')) or 0.0) / max_t, 1),
                            'sublabel': f"~{_format_number(r.get('est_rows'))} rows",
                        }
                        for r in top_tbls
                    ],
                })

        elif obj_kind == 'table' and scope['object_name']:
            sch = scope['schema'] or 'public'
            tname = scope['object_name']
            t_rows = safe_query(
                'SELECT c.oid AS relid, '
                'COALESCE(obj_description(c.oid), \'\') AS comment, '
                'pg_relation_size(c.oid) AS heap_bytes, '
                'pg_table_size(c.oid) - pg_relation_size(c.oid) AS toast_bytes, '
                'pg_indexes_size(c.oid) AS index_bytes, '
                'pg_total_relation_size(c.oid) AS total_bytes, '
                'COALESCE(s.n_live_tup, 0) AS live_tup, '
                'COALESCE(s.n_dead_tup, 0) AS dead_tup, '
                'COALESCE(s.seq_scan, 0) AS seq_scan, '
                'COALESCE(s.idx_scan, 0) AS idx_scan '
                'FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace '
                'LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid '
                f"WHERE n.nspname = '{sch.replace(chr(39), chr(39)*2)}' "
                f"AND c.relname = '{tname.replace(chr(39), chr(39)*2)}'"
            )
            if t_rows:
                tr = t_rows[0]
                if tr.get('comment'):
                    out['comment'] = str(tr['comment']).strip()
                    out['comment_source'] = 'obj_description'
                total_b = max(0.0, _safe_float(tr.get('total_bytes')) or 0.0)
                heap_b = max(0.0, _safe_float(tr.get('heap_bytes')) or 0.0)
                toast_b = max(0.0, _safe_float(tr.get('toast_bytes')) or 0.0)
                idx_b = max(0.0, _safe_float(tr.get('index_bytes')) or 0.0)
                live_t = _safe_float(tr.get('live_tup')) or 0.0
                dead_t = _safe_float(tr.get('dead_tup')) or 0.0
                seq_s = _safe_float(tr.get('seq_scan')) or 0.0
                idx_s = _safe_float(tr.get('idx_scan')) or 0.0
                dead_pct = round(100.0 * dead_t / max(1.0, live_t + dead_t), 1) if (live_t + dead_t) > 0 else 0.0
                idx_pct = round(100.0 * idx_s / max(1.0, seq_s + idx_s), 1) if (seq_s + idx_s) > 0 else 100.0

                observations.extend([
                    {'metric_key': 'storage.total_bytes', 'label': 'Total Table Size', 'group': 'storage', 'kind': 'gauge', 'unit': 'bytes', 'value': total_b},
                    {'metric_key': 'rows.estimated_live', 'label': 'Estimated Live Rows', 'group': 'rows', 'kind': 'gauge', 'unit': 'count', 'value': live_t},
                    {'metric_key': 'rows.dead_pct', 'label': 'Dead Tuple Ratio %', 'group': 'rows', 'kind': 'gauge', 'unit': 'percent', 'value': dead_pct},
                ])
                kpis.extend([
                    {'id': 'total_size', 'label': 'Total Relation Size', 'value': total_b, 'formatted': _format_bytes(total_b), 'unit': 'bytes', 'subtext': f'Heap {_format_bytes(heap_b)} · Indexes {_format_bytes(idx_b)}', 'status': 'ok'},
                    {'id': 'est_rows', 'label': 'Estimated Live Rows', 'value': live_t, 'formatted': _format_number(live_t), 'unit': 'count', 'subtext': f'{_format_number(dead_t)} dead tuples ({dead_pct}%)', 'capacity_pct': dead_pct, 'warn_pct': 20, 'crit_pct': 40, 'status': 'warning' if dead_pct >= 20 else 'ok'},
                    {'id': 'index_scan_pct', 'label': 'Index vs Seq Scan %', 'value': idx_pct, 'formatted': _format_number(idx_pct, 'percent'), 'unit': 'percent', 'subtext': f'{int(idx_s):,} index · {int(seq_s):,} seq scans', 'capacity_pct': idx_pct, 'status': 'ok'},
                ])
                denom = max(1.0, total_b)
                storage_bars.append({
                    'id': 'pg_table_composition',
                    'title': 'Relation Storage Composition',
                    'total_bytes': total_b,
                    'total_formatted': _format_bytes(total_b),
                    'segments': [
                        {'id': 'heap', 'label': 'Table Heap', 'bytes': heap_b, 'pct': round(100.0 * heap_b / denom, 1), 'formatted': _format_bytes(heap_b), 'tone': 'primary'},
                        {'id': 'indexes', 'label': 'Indexes', 'bytes': idx_b, 'pct': round(100.0 * idx_b / denom, 1), 'formatted': _format_bytes(idx_b), 'tone': 'info'},
                        {'id': 'toast', 'label': 'TOAST', 'bytes': toast_b, 'pct': round(100.0 * toast_b / denom, 1), 'formatted': _format_bytes(toast_b), 'tone': 'warning'},
                    ],
                })

            idx_rows = safe_query(
                'SELECT indexrelname AS index_name, idx_scan AS scans, '
                'pg_size_pretty(pg_relation_size(indexrelid)) AS size '
                'FROM pg_stat_user_indexes '
                f"WHERE schemaname = '{sch.replace(chr(39), chr(39)*2)}' "
                f"AND relname = '{tname.replace(chr(39), chr(39)*2)}' "
                'ORDER BY idx_scan ASC'
            )
            if idx_rows:
                reports.append({
                    'id': 'index_usage',
                    'title': 'Index Scan Activity & Unused Index Check',
                    'description': 'Zero-scan indexes consume write I/O and storage without accelerating reads',
                    'columns': ['index_name', 'scans', 'size'],
                    'rows': idx_rows,
                })

    def _probe_firebird_tier1(
        self, safe_query, scope, out, observations, kpis, storage_bars, rankings, reports
    ) -> None:
        obj_kind = scope['object_kind']
        if obj_kind in ('server', 'database'):
            db_rows = safe_query(
                'SELECT CAST(LEFT(D.RDB$DESCRIPTION, 8000) AS VARCHAR(8000)) AS db_comment '
                'FROM RDB$DATABASE D'
            )
            if db_rows and db_rows[0].get('db_comment'):
                out['comment'] = str(db_rows[0]['db_comment']).strip()
                out['comment_source'] = 'RDB$DATABASE.RDB$DESCRIPTION'

            io_rows = safe_query(
                'SELECT M.MON$PAGE_FETCHES AS fetches, M.MON$PAGE_READS AS reads, '
                'M.MON$PAGE_WRITES AS writes, U.MON$MEMORY_USED AS mem_used, '
                'U.MON$MEMORY_ALLOCATED AS mem_alloc '
                'FROM MON$IO_STATS M LEFT JOIN MON$MEMORY_USAGE U '
                'ON U.MON$STAT_ID = M.MON$STAT_ID WHERE M.MON$STAT_GROUP = 0'
            )
            if io_rows:
                ir = io_rows[0]
                fetches = _safe_float(ir.get('fetches')) or 0.0
                reads = _safe_float(ir.get('reads')) or 0.0
                writes = _safe_float(ir.get('writes')) or 0.0
                mem_used = _safe_float(ir.get('mem_used'))
                mem_alloc = _safe_float(ir.get('mem_alloc'))
                hit_pct = round(100.0 * max(0.0, fetches - reads) / max(1.0, fetches), 2) if fetches > 0 else 100.0
                observations.extend([
                    {'metric_key': 'cache.hit_ratio_pct', 'label': 'Page Buffer Hit %', 'group': 'memory', 'kind': 'gauge', 'unit': 'percent', 'value': hit_pct},
                    {'metric_key': 'io.page_reads_per_sec', 'label': 'Page Reads / sec', 'group': 'io', 'kind': 'counter_rate', 'unit': 'per_sec', 'raw_counter': reads},
                    {'metric_key': 'io.page_writes_per_sec', 'label': 'Page Writes / sec', 'group': 'io', 'kind': 'counter_rate', 'unit': 'per_sec', 'raw_counter': writes},
                ])
                kpis.append({
                    'id': 'fb_cache_hit',
                    'label': 'Page Buffer Cache Hit %',
                    'value': hit_pct,
                    'formatted': _format_number(hit_pct, 'percent'),
                    'unit': 'percent',
                    'subtext': f'{int(fetches):,} fetches · {int(reads):,} disk reads',
                    'capacity_pct': hit_pct,
                    'status': 'ok' if hit_pct >= 90 else 'warning',
                })
                if mem_used is not None:
                    observations.append({'metric_key': 'memory.used_bytes', 'label': 'Engine Memory Used', 'group': 'memory', 'kind': 'gauge', 'unit': 'bytes', 'value': mem_used})
                    mem_pct = round(100.0 * mem_used / max(1.0, mem_alloc), 1) if mem_alloc else None
                    kpis.append({
                        'id': 'fb_memory',
                        'label': 'Engine Memory Used',
                        'value': mem_used,
                        'formatted': _format_bytes(mem_used),
                        'unit': 'bytes',
                        'subtext': f'Allocated pool: {_format_bytes(mem_alloc)}' if mem_alloc else 'MON$MEMORY_USAGE',
                        'capacity_pct': mem_pct,
                        'warn_pct': 85,
                        'crit_pct': 95,
                        'status': 'ok',
                    })

            att_rows = safe_query(
                'SELECT FIRST 50 TRIM(MON$USER) AS username, '
                'MON$ATTACHMENT_ID AS attachment_id, '
                'MON$STATE AS state, '
                'TRIM(COALESCE(MON$REMOTE_PROTOCOL, \'Embedded\')) AS protocol, '
                'TRIM(COALESCE(MON$REMOTE_ADDRESS, \'local\')) AS remote_address, '
                'TRIM(COALESCE(MON$REMOTE_PROCESS, \'\')) AS remote_process '
                'FROM MON$ATTACHMENTS ORDER BY MON$ATTACHMENT_ID DESC'
            )
            if att_rows:
                reports.append({
                    'id': 'fb_attachments',
                    'title': 'Active Attachments (MON$ATTACHMENTS)',
                    'description': 'Connected network and embedded attachments',
                    'columns': ['attachment_id', 'username', 'state', 'protocol', 'remote_address', 'remote_process'],
                    'rows': att_rows,
                })

        elif obj_kind == 'table' and scope['object_name']:
            tname = scope['object_name'].replace("'", "''")
            rel_rows = safe_query(
                'SELECT CAST(LEFT(R.RDB$DESCRIPTION, 8000) AS VARCHAR(8000)) AS tbl_comment, '
                'R.RDB$FORMAT AS format_version '
                f"FROM RDB$RELATIONS R WHERE TRIM(R.RDB$RELATION_NAME) = '{tname}'"
            )
            if rel_rows:
                if rel_rows[0].get('tbl_comment'):
                    out['comment'] = str(rel_rows[0]['tbl_comment']).strip()
                    out['comment_source'] = 'RDB$RELATIONS.RDB$DESCRIPTION'
                fmt_v = _safe_float(rel_rows[0].get('format_version'))
                if fmt_v is not None:
                    kpis.append({
                        'id': 'fb_format_version',
                        'label': 'Format Version',
                        'value': fmt_v,
                        'formatted': f'{int(fmt_v)} / 255',
                        'unit': 'count',
                        'subtext': 'Firebird relation format counter',
                        'capacity_pct': round(100.0 * fmt_v / 255.0, 1),
                        'warn_pct': 80,
                        'crit_pct': 92,
                        'status': 'critical' if fmt_v >= 235 else ('warning' if fmt_v >= 200 else 'ok'),
                    })

            idx_rows = safe_query(
                'SELECT TRIM(I.RDB$INDEX_NAME) AS index_name, '
                'COALESCE(I.RDB$UNIQUE_FLAG, 0) AS is_unique, '
                'COALESCE(I.RDB$INDEX_INACTIVE, 0) AS is_inactive, '
                'I.RDB$STATISTICS AS selectivity '
                'FROM RDB$INDICES I '
                f"WHERE TRIM(I.RDB$RELATION_NAME) = '{tname}' "
                'ORDER BY I.RDB$INDEX_ID ASC'
            )
            if idx_rows:
                reports.append({
                    'id': 'fb_indexes',
                    'title': 'Index Selectivity (RDB$INDICES)',
                    'description': 'Lower non-zero selectivity indicates higher uniqueness',
                    'columns': ['index_name', 'is_unique', 'is_inactive', 'selectivity'],
                    'rows': idx_rows,
                })

    def _probe_mysql_family_tier1(
        self, safe_query, scope, out, observations, kpis, storage_bars, rankings, reports
    ) -> None:
        obj_kind = scope['object_kind']
        status_rows = safe_query(
            "SHOW GLOBAL STATUS WHERE Variable_name IN ("
            "'Uptime', 'Threads_connected', 'Threads_running', 'Questions', "
            "'Com_commit', 'Com_rollback', 'Bytes_received', 'Bytes_sent', "
            "'Innodb_buffer_pool_read_requests', 'Innodb_buffer_pool_reads', "
            "'Innodb_buffer_pool_pages_data', 'Innodb_buffer_pool_pages_total', "
            "'Slow_queries')",
            max_rows=50,
        )
        smap: dict[str, float] = {}
        for r in status_rows:
            k = str(r.get('Variable_name') or r.get('variable_name') or '')
            v = _safe_float(r.get('Value') if 'Value' in r else r.get('value'))
            if k and v is not None:
                smap[k] = v

        var_rows = safe_query("SELECT @@max_connections AS max_conns, DATABASE() AS cur_db")
        max_conns = (_safe_float(var_rows[0].get('max_conns')) if var_rows else None) or 151.0
        cur_db = (str(var_rows[0].get('cur_db') or '') if var_rows else '') or scope['database_name']

        if 'Uptime' in smap:
            out['epoch_id'] = f"boot:{int((time.time() - smap['Uptime']) // 60)}"
            if obj_kind == 'server':
                kpis.append({
                    'id': 'uptime',
                    'label': 'Server Uptime',
                    'value': smap['Uptime'],
                    'formatted': _format_number(smap['Uptime'], 'seconds'),
                    'unit': 'seconds',
                    'subtext': f"Slow queries: {_format_number(smap.get('Slow_queries', 0))}",
                    'status': 'ok',
                })

        if 'Threads_connected' in smap and obj_kind in ('server', 'database'):
            tc = smap['Threads_connected']
            tr = smap.get('Threads_running', 0.0)
            cap_pct = min(100.0, round(100.0 * tc / max(1.0, max_conns), 1))
            observations.extend([
                {'metric_key': 'sessions.total', 'label': 'Threads Connected', 'group': 'sessions', 'kind': 'gauge', 'unit': 'count', 'value': tc},
                {'metric_key': 'sessions.active', 'label': 'Threads Running', 'group': 'sessions', 'kind': 'gauge', 'unit': 'count', 'value': tr},
            ])
            kpis.append({
                'id': 'mysql_threads',
                'label': 'Connections',
                'value': tc,
                'formatted': f'{int(tc)} / {int(max_conns)}',
                'unit': 'count',
                'subtext': f'{int(tr)} running threads',
                'capacity_pct': cap_pct,
                'warn_pct': 80,
                'crit_pct': 92,
                'status': 'critical' if cap_pct >= 92 else ('warning' if cap_pct >= 80 else 'ok'),
            })

        if 'Questions' in smap:
            observations.append({
                'metric_key': 'queries.per_sec',
                'label': 'Queries / sec',
                'group': 'throughput',
                'kind': 'counter_rate',
                'unit': 'per_sec',
                'raw_counter': smap['Questions'],
            })

        req_reads = smap.get('Innodb_buffer_pool_read_requests', 0.0)
        disk_reads = smap.get('Innodb_buffer_pool_reads', 0.0)
        if req_reads > 0 and obj_kind in ('server', 'database'):
            hit_pct = round(100.0 * max(0.0, req_reads - disk_reads) / req_reads, 2)
            observations.append({'metric_key': 'cache.hit_ratio_pct', 'label': 'InnoDB Buffer Hit %', 'group': 'memory', 'kind': 'gauge', 'unit': 'percent', 'value': hit_pct})
            kpis.append({
                'id': 'innodb_hit',
                'label': 'InnoDB Buffer Hit %',
                'value': hit_pct,
                'formatted': _format_number(hit_pct, 'percent'),
                'unit': 'percent',
                'subtext': 'Buffer pool logical vs disk reads',
                'capacity_pct': hit_pct,
                'status': 'ok' if hit_pct >= 90 else 'warning',
            })

        if obj_kind == 'database' and cur_db:
            db_esc = cur_db.replace("'", "''")
            sch_rows = safe_query(
                'SELECT DEFAULT_CHARACTER_SET_NAME AS charset, '
                'DEFAULT_COLLATION_NAME AS collation '
                f"FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = '{db_esc}'"
            )
            # MariaDB / MySQL 8+ optional SCHEMA_COMMENT probe
            cmt_rows = safe_query(
                f"SELECT SCHEMA_COMMENT AS comment FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = '{db_esc}'"
            )
            if cmt_rows and cmt_rows[0].get('comment'):
                out['comment'] = str(cmt_rows[0]['comment']).strip()
                out['comment_source'] = 'information_schema.SCHEMATA'
            if sch_rows:
                kpis.append({
                    'id': 'db_charset',
                    'label': 'Charset & Collation',
                    'value': str(sch_rows[0].get('charset') or 'utf8mb4'),
                    'formatted': str(sch_rows[0].get('charset') or 'utf8mb4'),
                    'unit': 'text',
                    'subtext': str(sch_rows[0].get('collation') or ''),
                    'status': 'ok',
                })

            cnt_rows = safe_query(
                f"SELECT COUNT(*) AS cnt FROM information_schema.TABLES WHERE TABLE_SCHEMA = '{db_esc}'"
            )
            tbl_cnt = int(_safe_float(cnt_rows[0].get('cnt')) or 0) if cnt_rows else 0
            if tbl_cnt < 1500:
                sz_rows = safe_query(
                    'SELECT COALESCE(SUM(DATA_LENGTH), 0) AS data_b, '
                    'COALESCE(SUM(INDEX_LENGTH), 0) AS idx_b, '
                    'COALESCE(SUM(DATA_FREE), 0) AS free_b '
                    f"FROM information_schema.TABLES WHERE TABLE_SCHEMA = '{db_esc}'"
                )
                if sz_rows:
                    db_b = (_safe_float(sz_rows[0].get('data_b')) or 0.0) + (_safe_float(sz_rows[0].get('idx_b')) or 0.0)
                    observations.append({'metric_key': 'storage.total_bytes', 'label': 'Schema Size', 'group': 'storage', 'kind': 'gauge', 'unit': 'bytes', 'value': db_b})
                    kpis.append({'id': 'db_size', 'label': 'Database Size', 'value': db_b, 'formatted': _format_bytes(db_b), 'unit': 'bytes', 'subtext': f'{tbl_cnt} tables/views', 'status': 'ok'})

        elif obj_kind == 'table' and scope['object_name']:
            db_esc = (scope['schema'] or cur_db).replace("'", "''")
            t_esc = scope['object_name'].replace("'", "''")
            t_rows = safe_query(
                'SELECT ENGINE AS engine, TABLE_ROWS AS est_rows, '
                'COALESCE(DATA_LENGTH, 0) AS data_b, COALESCE(INDEX_LENGTH, 0) AS idx_b, '
                'COALESCE(DATA_FREE, 0) AS free_b, TABLE_COLLATION AS collation, '
                'TABLE_COMMENT AS comment '
                'FROM information_schema.TABLES '
                f"WHERE TABLE_SCHEMA = '{db_esc}' AND TABLE_NAME = '{t_esc}'"
            )
            if t_rows:
                tr = t_rows[0]
                if tr.get('comment'):
                    out['comment'] = str(tr['comment']).strip()
                    out['comment_source'] = 'information_schema.TABLES'
                data_b = _safe_float(tr.get('data_b')) or 0.0
                idx_b = _safe_float(tr.get('idx_b')) or 0.0
                free_b = _safe_float(tr.get('free_b')) or 0.0
                tot_b = data_b + idx_b
                est_r = _safe_float(tr.get('est_rows')) or 0.0
                observations.extend([
                    {'metric_key': 'storage.total_bytes', 'label': 'Table Size', 'group': 'storage', 'kind': 'gauge', 'unit': 'bytes', 'value': tot_b},
                    {'metric_key': 'rows.estimated_live', 'label': 'Estimated Rows', 'group': 'rows', 'kind': 'gauge', 'unit': 'count', 'value': est_r},
                ])
                kpis.extend([
                    {'id': 'total_size', 'label': 'Table Size', 'value': tot_b, 'formatted': _format_bytes(tot_b), 'unit': 'bytes', 'subtext': f"Engine: {tr.get('engine') or 'InnoDB'}", 'status': 'ok'},
                    {'id': 'est_rows', 'label': 'Estimated Rows', 'value': est_r, 'formatted': _format_number(est_r), 'unit': 'count', 'subtext': f'Free/Slack: {_format_bytes(free_b)}', 'status': 'ok'},
                ])
                denom = max(1.0, tot_b + free_b)
                storage_bars.append({
                    'id': 'mysql_table_comp',
                    'title': 'Table Storage Composition',
                    'total_bytes': tot_b + free_b,
                    'total_formatted': _format_bytes(tot_b + free_b),
                    'segments': [
                        {'id': 'data', 'label': 'Data Pages', 'bytes': data_b, 'pct': round(100.0 * data_b / denom, 1), 'formatted': _format_bytes(data_b), 'tone': 'primary'},
                        {'id': 'index', 'label': 'Indexes', 'bytes': idx_b, 'pct': round(100.0 * idx_b / denom, 1), 'formatted': _format_bytes(idx_b), 'tone': 'info'},
                        {'id': 'free', 'label': 'Data Free', 'bytes': free_b, 'pct': round(100.0 * free_b / denom, 1), 'formatted': _format_bytes(free_b), 'tone': 'warning'},
                    ],
                })

    def _probe_sqlite_tier1(
        self, safe_query, scope, local_files, out, observations, kpis, storage_bars, rankings, reports
    ) -> None:
        obj_kind = scope['object_kind']
        # Fast O(1) header PRAGMAs (reads page 1 only — zero full-B-tree scan!)
        ps_rows = safe_query('PRAGMA page_size')
        pc_rows = safe_query('PRAGMA page_count')
        fl_rows = safe_query('PRAGMA freelist_count')
        jm_rows = safe_query('PRAGMA journal_mode')
        fk_rows = safe_query('PRAGMA foreign_keys')

        page_sz = _safe_float(next(iter((ps_rows[0] if ps_rows else {}).values()), None)) or 4096.0
        page_cnt = _safe_float(next(iter((pc_rows[0] if pc_rows else {}).values()), None)) or 0.0
        free_cnt = _safe_float(next(iter((fl_rows[0] if fl_rows else {}).values()), None)) or 0.0
        journal_mode = str(next(iter((jm_rows[0] if jm_rows else {}).values()), 'delete')).upper()
        fk_on = bool(int(_safe_float(next(iter((fk_rows[0] if fk_rows else {}).values()), 0)) or 0))

        if obj_kind in ('server', 'database') and page_cnt > 0:
            total_b = page_sz * page_cnt
            free_b = page_sz * free_cnt
            used_b = max(0.0, total_b - free_b)
            used_pct = round(100.0 * used_b / max(1.0, total_b), 1)
            observations.extend([
                {'metric_key': 'storage.total_bytes', 'label': 'Database Page Size Total', 'group': 'storage', 'kind': 'gauge', 'unit': 'bytes', 'value': total_b},
                {'metric_key': 'storage.free_bytes', 'label': 'Freelist Bytes', 'group': 'storage', 'kind': 'gauge', 'unit': 'bytes', 'value': free_b},
            ])
            kpis.extend([
                {
                    'id': 'db_size',
                    'label': 'Database Footprint',
                    'value': total_b,
                    'formatted': _format_bytes(total_b),
                    'unit': 'bytes',
                    'subtext': f'{int(page_cnt):,} pages × {int(page_sz)} B · {journal_mode}',
                    'capacity_pct': used_pct,
                    'status': 'ok',
                },
                {
                    'id': 'sqlite_pragmas',
                    'label': 'Journal & Integrity',
                    'value': journal_mode,
                    'formatted': journal_mode,
                    'unit': 'text',
                    'subtext': f"Foreign keys: {'ON' if fk_on else 'OFF'} · Freelist: {int(free_cnt):,} pages",
                    'status': 'ok',
                },
            ])
            wal_b = float(local_files.get('wal_bytes') or 0.0)
            denom = max(1.0, total_b + wal_b)
            storage_bars.append({
                'id': 'sqlite_pages_bar',
                'title': 'SQLite Page & WAL Allocation',
                'total_bytes': total_b + wal_b,
                'total_formatted': _format_bytes(total_b + wal_b),
                'segments': [
                    {'id': 'used', 'label': 'Allocated Pages', 'bytes': used_b, 'pct': round(100.0 * used_b / denom, 1), 'formatted': _format_bytes(used_b), 'tone': 'primary'},
                    {'id': 'free', 'label': 'Freelist Pages', 'bytes': free_b, 'pct': round(100.0 * free_b / denom, 1), 'formatted': _format_bytes(free_b), 'tone': 'neutral'},
                    *(
                        [{'id': 'wal', 'label': 'WAL File', 'bytes': wal_b, 'pct': round(100.0 * wal_b / denom, 1), 'formatted': _format_bytes(wal_b), 'tone': 'warning'}]
                        if wal_b > 0
                        else []
                    ),
                ],
            })

        elif obj_kind == 'table' and scope['object_name']:
            t_esc = scope['object_name'].replace("'", "''")
            ddl_rows = safe_query(
                f"SELECT sql FROM sqlite_schema WHERE type IN ('table', 'view') AND name = '{t_esc}'"
            )
            if ddl_rows and ddl_rows[0].get('sql'):
                extracted = _extract_leading_sql_comment(str(ddl_rows[0]['sql']))
                if extracted:
                    out['comment'] = extracted
                    out['comment_source'] = 'sqlite_schema_header_comment'
            cols = safe_query(f'PRAGMA table_xinfo({_quote_ident(scope["object_name"])})')
            idxs = safe_query(f'PRAGMA index_list({_quote_ident(scope["object_name"])})')
            if cols:
                reports.append({
                    'id': 'sqlite_columns',
                    'title': 'Table Columns (PRAGMA table_xinfo)',
                    'description': 'Column definitions, types, defaults, primary-key ordinals, and hidden/generated flags',
                    'columns': list(cols[0].keys()),
                    'rows': cols,
                })
            if idxs:
                reports.append({
                    'id': 'sqlite_indexes',
                    'title': 'Table Indexes (PRAGMA index_list)',
                    'description': 'Declared and unique constraint indexes',
                    'columns': list(idxs[0].keys()),
                    'rows': idxs,
                })

    def _probe_duckdb_tier1(
        self, safe_query, scope, out, observations, kpis, storage_bars, rankings, reports
    ) -> None:
        obj_kind = scope['object_kind']
        if obj_kind in ('server', 'database'):
            db_rows = safe_query('SELECT database_name, path, comment, readonly FROM duckdb_databases() WHERE NOT internal')
            if db_rows and db_rows[0].get('comment'):
                out['comment'] = str(db_rows[0]['comment']).strip()
                out['comment_source'] = 'duckdb_databases()'

            mem_rows = safe_query('SELECT tag, memory_usage_bytes, temporary_storage_bytes FROM duckdb_memory() ORDER BY memory_usage_bytes DESC')
            if mem_rows:
                tot_mem = sum((_safe_float(r.get('memory_usage_bytes')) or 0.0) for r in mem_rows)
                observations.append({'metric_key': 'memory.used_bytes', 'label': 'DuckDB Engine Memory', 'group': 'memory', 'kind': 'gauge', 'unit': 'bytes', 'value': tot_mem})
                kpis.append({
                    'id': 'duckdb_memory',
                    'label': 'Buffer Manager Memory',
                    'value': tot_mem,
                    'formatted': _format_bytes(tot_mem),
                    'unit': 'bytes',
                    'subtext': f'{len(mem_rows)} subsystem tags tracked',
                    'status': 'ok',
                })
                max_m = max(1.0, max((_safe_float(r.get('memory_usage_bytes')) or 0.0) for r in mem_rows))
                rankings.append({
                    'id': 'duckdb_mem_tags',
                    'title': 'Memory Usage by Subsystem Tag (duckdb_memory)',
                    'unit': 'bytes',
                    'items': [
                        {
                            'id': str(r.get('tag')),
                            'label': str(r.get('tag')),
                            'value': _safe_float(r.get('memory_usage_bytes')) or 0.0,
                            'formatted': _format_bytes(r.get('memory_usage_bytes')),
                            'pct_of_max': round(100.0 * (_safe_float(r.get('memory_usage_bytes')) or 0.0) / max_m, 1),
                            'sublabel': f"Temp spill: {_format_bytes(r.get('temporary_storage_bytes') or 0)}",
                        }
                        for r in mem_rows[:10]
                    ],
                })

            tbl_rows = safe_query(
                'SELECT schema_name, table_name, estimated_size, column_count, index_count, comment '
                'FROM duckdb_tables() WHERE NOT internal ORDER BY estimated_size DESC LIMIT 15'
            )
            if tbl_rows:
                max_est = max(1.0, max((_safe_float(r.get('estimated_size')) or 0.0) for r in tbl_rows))
                rankings.append({
                    'id': 'duckdb_top_tables',
                    'title': 'Tables by Estimated Cardinality (duckdb_tables)',
                    'unit': 'count',
                    'items': [
                        {
                            'id': f"{r.get('schema_name')}.{r.get('table_name')}",
                            'label': f"{r.get('schema_name')}.{r.get('table_name')}",
                            'value': _safe_float(r.get('estimated_size')) or 0.0,
                            'formatted': f"{_format_number(r.get('estimated_size'))} rows",
                            'pct_of_max': round(100.0 * (_safe_float(r.get('estimated_size')) or 0.0) / max_est, 1),
                            'sublabel': f"{r.get('column_count')} cols" + (f" · {r.get('comment')}" if r.get('comment') else ''),
                        }
                        for r in tbl_rows
                    ],
                })

        elif obj_kind == 'table' and scope['object_name']:
            t_esc = scope['object_name'].replace("'", "''")
            t_rows = safe_query(
                'SELECT schema_name, table_name, estimated_size, column_count, '
                'index_count, check_constraint_count, comment '
                f"FROM duckdb_tables() WHERE table_name = '{t_esc}' LIMIT 1"
            )
            if t_rows:
                tr = t_rows[0]
                if tr.get('comment'):
                    out['comment'] = str(tr['comment']).strip()
                    out['comment_source'] = 'duckdb_tables()'
                est = _safe_float(tr.get('estimated_size')) or 0.0
                observations.append({'metric_key': 'rows.estimated_live', 'label': 'Estimated Rows', 'group': 'rows', 'kind': 'gauge', 'unit': 'count', 'value': est})
                kpis.append({
                    'id': 'est_rows',
                    'label': 'Estimated Row Count',
                    'value': est,
                    'formatted': _format_number(est),
                    'unit': 'count',
                    'subtext': f"{tr.get('column_count')} columns · {tr.get('index_count')} ART indexes",
                    'status': 'ok',
                })

    def _probe_clickhouse_tier1(
        self, safe_query, scope, out, observations, kpis, storage_bars, rankings, reports
    ) -> None:
        obj_kind = scope['object_kind']
        if obj_kind in ('server', 'database'):
            part_rows = safe_query(
                'SELECT COUNT() AS active_parts, SUM(rows) AS total_rows, '
                'SUM(bytes_on_disk) AS disk_b, SUM(data_uncompressed_bytes) AS raw_b '
                'FROM system.parts WHERE active = 1'
            )
            if part_rows:
                pr = part_rows[0]
                disk_b = _safe_float(pr.get('disk_b')) or 0.0
                raw_b = _safe_float(pr.get('raw_b')) or 0.0
                parts = _safe_float(pr.get('active_parts')) or 0.0
                ratio = round(raw_b / max(1.0, disk_b), 2) if disk_b > 0 else 1.0
                observations.extend([
                    {'metric_key': 'storage.total_bytes', 'label': 'Compressed Disk Bytes', 'group': 'storage', 'kind': 'gauge', 'unit': 'bytes', 'value': disk_b},
                    {'metric_key': 'storage.active_parts', 'label': 'Active MergeTree Parts', 'group': 'storage', 'kind': 'gauge', 'unit': 'count', 'value': parts},
                ])
                kpis.extend([
                    {'id': 'ch_compressed', 'label': 'Compressed Storage', 'value': disk_b, 'formatted': _format_bytes(disk_b), 'unit': 'bytes', 'subtext': f'{ratio}× compression vs {_format_bytes(raw_b)} raw', 'status': 'ok'},
                    {'id': 'ch_parts', 'label': 'Active Parts', 'value': parts, 'formatted': _format_number(parts), 'unit': 'count', 'subtext': 'MergeTree active parts', 'status': 'warning' if parts > 1000 else 'ok'},
                ])

    # ------------------------------------------------------------------
    # Tier-3 Explicit Deep Statistics Refresh (User-Triggered ONLY)
    # ------------------------------------------------------------------

    @staticmethod
    def _available_deep_actions(engine_id: str, obj_kind: str) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if obj_kind == 'table':
            actions.append({
                'id': 'exact_row_count',
                'label': 'Exact Row Count (COUNT(*))',
                'description': 'Scans the relation or index to compute exact live row cardinality.',
            })
            if engine_id == 'duckdb':
                actions.append({
                    'id': 'duckdb_summarize',
                    'label': 'Column Statistical Profile (SUMMARIZE)',
                    'description': 'Computes min, max, approx_unique, avg, quartiles, and null % per column.',
                })
            elif engine_id == 'postgresql':
                actions.append({
                    'id': 'pg_physical_bloat',
                    'label': 'Physical Tuple & Free-Space Scan',
                    'description': 'Uses pgstattuple when installed to inspect exact dead-tuple bytes and free space.',
                })
            elif engine_id == 'sqlite':
                actions.append({
                    'id': 'sqlite_table_dbstat',
                    'label': 'B-Tree Page & Unused Slack Scan (dbstat)',
                    'description': 'Aggregates exact payload vs slack bytes across B-tree pages for this table.',
                })
        elif obj_kind in ('server', 'database'):
            if engine_id == 'sqlite':
                actions.extend([
                    {
                        'id': 'sqlite_dbstat_scan',
                        'label': 'Per-Table B-Tree Space & Slack (dbstat)',
                        'description': 'Scans SQLite dbstat virtual table to measure exact bytes and slack per table/index.',
                    },
                    {
                        'id': 'sqlite_quick_check',
                        'label': 'Quick Structural Integrity Check',
                        'description': 'Runs PRAGMA quick_check(10) to verify page & B-tree structural consistency.',
                    },
                ])
            elif engine_id == 'firebird':
                actions.append({
                    'id': 'firebird_page_inventory',
                    'label': 'Physical Page Inventory (RDB$PAGES)',
                    'description': 'Counts allocated pointer, data, index, and BLOB pages across RDB$PAGES.',
                })
            else:
                actions.append({
                    'id': 'catalog_deep_scan',
                    'label': 'Deep Storage & Cardinality Summary',
                    'description': 'Computes full storage totals and top-object cardinalities across user schemas.',
                })
        return actions

    def compute_deep_stats(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Run explicit user-requested Tier-3 deep inspection and cache in Vault."""
        uid = _actor_user_id()
        scope = _normalize_scope(params)
        server = _resolve_owned_server(scope['server_id'])
        eng_info = _resolve_engine_info(server, scope['engine_id'])
        engine_id = eng_info['engine_id']
        obj_kind = scope['object_kind']

        run_sql = None
        close_sql = lambda: None
        if eng_info['workflow'] == 'provider_endpoint' and eng_info['verified']:
            run_sql, close_sql, _ctx, _ep = self._open_ephemeral_provider_runner(
                server, scope['database_target_id'] or None
            )
        elif eng_info['workflow'] == 'legacy_pg' and scope['server_id']:
            run_sql, _pg_ok = self._open_pg_legacy_runner(
                scope['server_id'], scope['database_target_id'] or None
            )

        if run_sql is None:
            raise PermissionError(
                'Connect and authenticate the target server/database before running Deep Stats.'
            )

        stats_result: dict[str, Any] = {
            'engine_id': engine_id,
            'object_kind': obj_kind,
            'metrics': [],
            'tables': [],
        }
        observations: list[dict[str, Any]] = []
        started = time.monotonic()

        try:
            if obj_kind == 'table' and scope['object_name']:
                qchar = '`' if engine_id in ('mysql', 'mariadb', 'tidb', 'vitess', 'dolt', 'clickhouse') else '"'
                qual_tbl = (
                    f"{_quote_ident(scope['schema'], qchar)}.{_quote_ident(scope['object_name'], qchar)}"
                    if scope['schema'] and engine_id not in ('sqlite', 'firebird')
                    else _quote_ident(scope['object_name'], qchar)
                )
                cnt_rows = run_sql(f'SELECT COUNT(*) AS exact_rows FROM {qual_tbl}', max_rows=5)
                if cnt_rows:
                    exact_n = int(_safe_float(next(iter(cnt_rows[0].values()))) or 0)
                    stats_result['exact_row_count'] = exact_n
                    stats_result['metrics'].append({
                        'label': 'Exact Row Count (COUNT(*))',
                        'value': _format_number(exact_n),
                    })
                    observations.append({
                        'metric_key': 'rows.exact_count',
                        'label': 'Exact Row Count',
                        'group': 'rows',
                        'kind': 'gauge',
                        'unit': 'count',
                        'value': float(exact_n),
                    })

                if engine_id == 'duckdb':
                    try:
                        sum_rows = run_sql(f'SUMMARIZE SELECT * FROM {qual_tbl}', max_rows=100)
                        if sum_rows:
                            stats_result['tables'].append({
                                'id': 'duckdb_summarize',
                                'title': 'Column Statistical Profile (SUMMARIZE)',
                                'columns': list(sum_rows[0].keys()),
                                'rows': sum_rows,
                            })
                    except Exception:
                        pass
                elif engine_id == 'sqlite':
                    try:
                        t_esc = scope['object_name'].replace("'", "''")
                        dbs_rows = run_sql(
                            'SELECT name, COUNT(*) AS pages, SUM(pgsize) AS total_bytes, '
                            'SUM(payload) AS payload_bytes, SUM(unused) AS unused_bytes '
                            f"FROM dbstat WHERE name = '{t_esc}' GROUP BY name",
                            max_rows=10,
                        )
                        if dbs_rows:
                            r0 = dbs_rows[0]
                            stats_result['metrics'].extend([
                                {'label': 'B-Tree Total Bytes', 'value': _format_bytes(r0.get('total_bytes'))},
                                {'label': 'Live Payload Bytes', 'value': _format_bytes(r0.get('payload_bytes'))},
                                {'label': 'Unused Page Slack', 'value': _format_bytes(r0.get('unused_bytes'))},
                            ])
                    except Exception:
                        pass
                elif engine_id == 'postgresql':
                    try:
                        ext = run_sql("SELECT 1 AS ok FROM pg_extension WHERE extname = 'pgstattuple'")
                        if ext:
                            tup = run_sql(f"SELECT * FROM pgstattuple('{qual_tbl}')", max_rows=5)
                            if tup:
                                r0 = tup[0]
                                stats_result['metrics'].extend([
                                    {'label': 'Live Tuple Bytes', 'value': _format_bytes(r0.get('tuple_len'))},
                                    {'label': 'Dead Tuple Bytes', 'value': _format_bytes(r0.get('dead_tuple_len'))},
                                    {'label': 'Free Space Bytes', 'value': _format_bytes(r0.get('free_space'))},
                                ])
                    except Exception:
                        pass

            elif engine_id == 'sqlite':
                try:
                    dbs_rows = run_sql(
                        'SELECT name, COUNT(*) AS pages, SUM(pgsize) AS total_bytes, '
                        'SUM(payload) AS payload_bytes, SUM(unused) AS unused_bytes '
                        'FROM dbstat GROUP BY name ORDER BY total_bytes DESC LIMIT 25',
                        max_rows=30,
                    )
                    if dbs_rows:
                        stats_result['tables'].append({
                            'id': 'sqlite_dbstat',
                            'title': 'Per-Object B-Tree Footprint & Slack (dbstat)',
                            'columns': ['name', 'pages', 'total_bytes', 'payload_bytes', 'unused_bytes'],
                            'rows': dbs_rows,
                        })
                except Exception:
                    pass
                try:
                    qc = run_sql('PRAGMA quick_check(10)', max_rows=12)
                    if qc:
                        verdict = str(next(iter(qc[0].values())))
                        stats_result['metrics'].append({
                            'label': 'PRAGMA quick_check',
                            'value': verdict,
                        })
                except Exception:
                    pass

            elif engine_id == 'firebird':
                try:
                    pg_rows = run_sql(
                        'SELECT RDB$PAGE_TYPE AS page_type, COUNT(*) AS page_count '
                        'FROM RDB$PAGES GROUP BY RDB$PAGE_TYPE ORDER BY page_count DESC',
                        max_rows=20,
                    )
                    if pg_rows:
                        type_names = {
                            1: 'Header', 2: 'Page Inventory (PIP)', 3: 'Transaction Inventory (TIP)',
                            4: 'Pointer', 5: 'Data', 6: 'Index Root', 7: 'Index B-Tree',
                            8: 'BLOB', 9: 'Generator', 10: 'SCN Inventory',
                        }
                        mapped = [
                            {
                                'page_type': type_names.get(int(_safe_float(r.get('page_type')) or 0), str(r.get('page_type'))),
                                'page_count': int(_safe_float(r.get('page_count')) or 0),
                            }
                            for r in pg_rows
                        ]
                        stats_result['tables'].append({
                            'id': 'fb_rdb_pages',
                            'title': 'Physical Page Inventory (RDB$PAGES)',
                            'columns': ['page_type', 'page_count'],
                            'rows': mapped,
                        })
                except Exception:
                    pass
            else:
                # Generic database/server deep summary
                stats_result['metrics'].append({
                    'label': 'Deep Verification Status',
                    'value': 'Completed',
                })
        finally:
            close_sql()

        elapsed_ms = round((time.monotonic() - started) * 1000.0, 1)
        stats_result['elapsed_ms'] = elapsed_ms
        computed_at = _now_iso()

        saved_payload = {
            'object_kind': obj_kind,
            'object_key': scope['object_key'],
            'computed_at': computed_at,
            'stats': stats_result,
        }
        history_out: dict[str, Any] = {'series': []}
        try:
            ucfg = get_user_config_db()
            if ucfg.is_unlocked():
                saved_payload = ucfg.save_on_demand_object_stats(
                    user_id=uid,
                    engine_id=engine_id,
                    server_id=scope['server_id'],
                    database_target_id=scope['database_target_id'],
                    object_kind=obj_kind,
                    object_key=scope['object_key'],
                    stats=stats_result,
                    computed_at=computed_at,
                )
                if observations:
                    ucfg.record_object_metric_observations(
                        user_id=uid,
                        engine_id=engine_id,
                        server_id=scope['server_id'],
                        database_target_id=scope['database_target_id'],
                        object_kind=obj_kind,
                        object_key=scope['object_key'],
                        observations=observations,
                    )
                history_out = ucfg.query_object_metric_history(
                    user_id=uid,
                    object_kind=obj_kind,
                    object_key=scope['object_key'],
                    window=str(params.get('window') or '1h'),
                )
        except Exception:
            pass

        return {
            'deep_stats': {
                'available_actions': self._available_deep_actions(engine_id, obj_kind),
                'cached': saved_payload,
            },
            'history': history_out,
        }

    # ------------------------------------------------------------------
    # Rich Object Properties Payload (`Properties` Sub-Tab)
    # ------------------------------------------------------------------

    def collect_rich_properties(self, params: Mapping[str, Any]) -> dict[str, Any]:
        uid = _actor_user_id()
        scope = _normalize_scope(params)
        server = _resolve_owned_server(scope['server_id'])
        eng_info = _resolve_engine_info(server, scope['engine_id'])
        engine_id = eng_info['engine_id']
        engine_label = eng_info['engine_label']
        obj_kind = scope['object_kind']

        summary_attrs: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
        dependencies: list[dict[str, Any]] = []
        dependents: list[dict[str, Any]] = []
        permissions: list[dict[str, Any]] = []
        ddl_sql = ''
        ddl_source = ''
        comment_text = ''

        def add_attr(key: str, label: str, val: Any, category: str = 'General', is_system: bool = False) -> None:
            is_empty = val is None or str(val).strip() == ''
            summary_attrs.append({
                'key': key,
                'label': label,
                'value': '—' if is_empty else str(val),
                'category': category,
                'is_system': is_system,
                'is_empty': is_empty,
            })

        add_attr('engine', 'Database Engine', engine_label, 'Identity')
        add_attr('object_kind', 'Object Type', scope['raw_kind'].capitalize(), 'Identity')
        if server is not None:
            add_attr('server_name', 'Server Profile', getattr(server, 'name', ''), 'Connection')
            add_attr('host', 'Host / Address', getattr(server, 'host', ''), 'Connection')
            add_attr('port', 'Port', getattr(server, 'port', None), 'Connection')
            add_attr('username', 'User Name', getattr(server, 'username', ''), 'Connection')
            if obj_kind == 'server' and getattr(server, 'comment', None):
                comment_text = str(server.comment).strip()
        if eng_info['profile_id']:
            add_attr('profile_id', 'Connector Profile', eng_info['profile_id'], 'Connection', is_system=True)
        if eng_info['verified_version']:
            add_attr('verified_version', 'Verified Engine Version', eng_info['verified_version'], 'Runtime')

        local_files = self._inspect_local_files(eng_info['route_cfg'])
        for k, label in (
            ('path', 'Database File Path'),
            ('main_bytes', 'Main File Size'),
            ('wal_bytes', 'WAL File Size'),
            ('modified_at', 'Last Modified (UTC)'),
        ):
            if k in local_files:
                v = _format_bytes(local_files[k]) if k.endswith('_bytes') else local_files[k]
                add_attr(f'file_{k}', label, v, 'Storage')

        snapshot = None
        if eng_info['workflow'] == 'provider_endpoint' and eng_info['verified']:
            snapshot = self._load_provider_snapshot_safe(
                server, scope['database_target_id'] or None
            )

        if snapshot is not None:
            for res in snapshot.get('resources') or []:
                rkind = str(res.get('resource_kind') or '')
                rid = str(res.get('resource_id') or '')
                dname = str(res.get('display_name') or res.get('name') or '')
                nat = resource_native(res)

                is_target = (
                    (obj_kind == 'server' and rkind == 'server')
                    or (obj_kind == 'database' and rkind == 'database')
                    or (
                        obj_kind == 'table'
                        and (
                            (scope['resource_id'] and rid == scope['resource_id'])
                            or (scope['object_name'] and dname.lower() == scope['object_name'].lower())
                        )
                    )
                )
                if not is_target:
                    continue

                desc = str(nat.get('comment') or nat.get('description') or res.get('description') or '').strip()
                if desc and not comment_text:
                    comment_text = desc

                if nat.get('sql') or nat.get('ddl') or nat.get('create_sql'):
                    ddl_sql = str(nat.get('sql') or nat.get('ddl') or nat.get('create_sql'))
                    ddl_source = 'provider_catalog'

                for nk, nv in nat.items():
                    if nk in {'columns', 'indexes', 'constraints', 'triggers', 'partitions', 'privileges', 'dependencies', 'dependents', 'property_sections', 'sql', 'ddl', 'create_sql'}:
                        continue
                    if isinstance(nv, (str, int, float, bool)) or nv is None:
                        add_attr(
                            f'native_{nk}',
                            nk.replace('_', ' ').capitalize(),
                            nv,
                            'Catalog Metadata',
                            is_system=nk.startswith('rdb$') or nk in {'system_object', 'scope', 'relation_id'},
                        )

                for sec_key, sec_title in (
                    ('columns', 'Columns'),
                    ('indexes', 'Indexes'),
                    ('constraints', 'Constraints'),
                    ('triggers', 'Triggers'),
                    ('partitions', 'Partitions'),
                    ('privileges', 'Permissions'),
                ):
                    arr = nat.get(sec_key)
                    if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                        cols = list(arr[0].keys())
                        sections.append({
                            'id': sec_key,
                            'title': sec_title,
                            'columns': cols,
                            'rows': arr,
                        })

                if isinstance(nat.get('privileges'), list):
                    for p_item in nat['privileges']:
                        if isinstance(p_item, dict):
                            permissions.append({
                                'grantee': str(p_item.get('grantee') or ''),
                                'grantee_kind': str(
                                    p_item.get('grantee_kind')
                                    or p_item.get('grantee_type')
                                    or 'role'
                                ),
                                'grantor': str(p_item.get('grantor') or ''),
                                'privilege': str(
                                    p_item.get('privilege')
                                    or p_item.get('privileges')
                                    or ''
                                ),
                                'with_grant': bool(
                                    p_item.get('with_grant')
                                    or p_item.get('grant_option')
                                    or p_item.get('is_grantable')
                                ),
                                'column_name': p_item.get('column_name'),
                            })

                if isinstance(nat.get('dependencies'), list):
                    dependencies.extend(nat['dependencies'])
                if isinstance(nat.get('dependents'), list):
                    dependents.extend(nat['dependents'])

        # Live DDL & structural fallback for connected SQL engines
        run_sql = None
        close_sql = lambda: None
        if eng_info['workflow'] == 'provider_endpoint' and eng_info['verified']:
            run_sql, close_sql, _, _ = self._open_ephemeral_provider_runner(
                server, scope['database_target_id'] or None
            )
        elif eng_info['workflow'] == 'legacy_pg' and scope['server_id']:
            run_sql, _ = self._open_pg_legacy_runner(
                scope['server_id'], scope['database_target_id'] or None
            )

        if run_sql is not None:
            try:
                if obj_kind in ('server', 'database') and engine_id == 'firebird' and not comment_text:
                    fb_c = run_sql(
                        'SELECT CAST(LEFT(D.RDB$DESCRIPTION, 8000) AS VARCHAR(8000)) AS db_comment '
                        'FROM RDB$DATABASE D',
                        max_rows=2,
                    )
                    if fb_c and fb_c[0].get('db_comment'):
                        comment_text = str(fb_c[0]['db_comment']).strip()
                if obj_kind == 'table' and scope['object_name']:
                    if engine_id == 'sqlite' and not ddl_sql:
                        t_esc = scope['object_name'].replace("'", "''")
                        r = run_sql(f"SELECT sql FROM sqlite_schema WHERE name = '{t_esc}'", max_rows=2)
                        if r and r[0].get('sql'):
                            ddl_sql = str(r[0]['sql'])
                            ddl_source = 'sqlite_schema'
                    elif engine_id == 'duckdb' and not ddl_sql:
                        t_esc = scope['object_name'].replace("'", "''")
                        r = run_sql(f"SELECT sql, comment FROM duckdb_tables() WHERE table_name = '{t_esc}'", max_rows=2)
                        if r:
                            ddl_sql = str(r[0].get('sql') or '')
                            ddl_source = 'duckdb_tables()'
                            if r[0].get('comment') and not comment_text:
                                comment_text = str(r[0]['comment']).strip()
                    elif engine_id in ('mysql', 'mariadb', 'tidb') and not ddl_sql:
                        qtbl = _quote_ident(scope['object_name'], '`')
                        r = run_sql(f'SHOW CREATE TABLE {qtbl}', max_rows=2)
                        if r:
                            vals = list(r[0].values())
                            if len(vals) >= 2:
                                ddl_sql = str(vals[1])
                                ddl_source = 'SHOW CREATE TABLE'
                    elif engine_id in ('postgresql', 'cockroachdb', 'yugabytedb') and not sections:
                        sch = (scope['schema'] or 'public').replace("'", "''")
                        t_esc = scope['object_name'].replace("'", "''")
                        c_rows = run_sql(
                            'SELECT a.attnum AS ordinal, a.attname AS column_name, '
                            'pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type, '
                            'NOT a.attnotnull AS is_nullable, '
                            'COALESCE(pg_get_expr(ad.adbin, ad.adrelid), \'\') AS default_value, '
                            'COALESCE(col_description(a.attrelid, a.attnum), \'\') AS comment '
                            'FROM pg_attribute a '
                            'JOIN pg_class c ON c.oid = a.attrelid '
                            'JOIN pg_namespace n ON n.oid = c.relnamespace '
                            'LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum '
                            f"WHERE n.nspname = '{sch}' AND c.relname = '{t_esc}' "
                            'AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum',
                            max_rows=250,
                        )
                        if c_rows:
                            sections.append({
                                'id': 'columns',
                                'title': 'Columns',
                                'columns': ['ordinal', 'column_name', 'data_type', 'is_nullable', 'default_value', 'comment'],
                                'rows': c_rows,
                            })
            except Exception:
                pass
            finally:
                close_sql()

        customization = dict(DEFAULT_PROPERTIES_CUSTOMIZATION)
        try:
            ucfg = get_user_config_db()
            if ucfg.is_unlocked():
                stored = ucfg.get_object_view_customization(uid, 'object_properties')
                if stored:
                    customization.update(stored)
        except Exception:
            pass

        title_name = (
            scope['object_name']
            or scope['database_name']
            or getattr(server, 'name', '')
            or scope['object_key']
        )

        return {
            'captured_at': _now_iso(),
            'object_identity': {
                'object_kind': obj_kind,
                'raw_kind': scope['raw_kind'],
                'object_key': scope['object_key'],
                'title': title_name,
                'engine_id': engine_id,
                'engine_label': engine_label,
                'server_id': scope['server_id'],
                'database_target_id': scope['database_target_id'],
                'resource_id': scope['resource_id'],
                'schema': scope['schema'],
                'object_name': scope['object_name'],
            },
            'comment': {
                'text': comment_text,
            },
            'summary_attributes': summary_attrs,
            'sections': sections,
            'ddl': {
                'available': bool(ddl_sql.strip()),
                'sql': ddl_sql,
                'source': ddl_source,
            },
            'dependencies': dependencies,
            'dependents': dependents,
            'permissions': permissions,
            'customization': customization,
        }

    # ------------------------------------------------------------------
    # Host-Compiled DDN Scene Builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_dashboard_ddn_scene(
        *,
        obj_kind: str,
        title_name: str,
        engine_label: str,
        connected: bool,
        kpis: list[dict[str, Any]],
        ddn_nodes: list[dict[str, Any]],
        ddn_edges: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any] | None]:
        root_id = _ddn_id('root', title_name)
        root_level = 'deployment' if obj_kind == 'server' else 'physical'
        lines: list[str] = []
        include_ids: list[str] = [root_id]

        # Root card with top KPI fields
        root_members: list[tuple[str, str, str]] = [
            (f'{root_id}_engine', 'engine', engine_label),
            (f'{root_id}_state', 'state', 'CONNECTED' if connected else 'OFFLINE'),
        ]
        for idx, k in enumerate(kpis[:5]):
            root_members.append((
                f'{root_id}_kpi_{idx}',
                _ddn_escape(k.get('label') or f'metric_{idx}').lower().replace(' ', '_')[:28],
                _ddn_escape(k.get('formatted') or k.get('value') or ''),
            ))

        for col_id, col_name, col_type in root_members:
            lines.extend([
                f'element "{col_id}" as "column"',
                '  with',
                f'    title "{_ddn_escape(col_name)}"',
                f'    type "{_ddn_escape(col_type)}"',
                '',
            ])

        lines.extend([
            f'element "{root_id}" as "table"',
            '  with',
            f'    title "{_ddn_escape(title_name)}"',
            f'    level "{root_level}"',
            '  members',
        ])
        for col_id, _, _ in root_members:
            lines.extend(['    item', f'      id "{col_id}"'])
        lines.append('')

        # Neighbor / child topology cards
        for nidx, node in enumerate(ddn_nodes[:6]):
            nid = str(node.get('id') or f'child_{nidx}')
            if nid == root_id:
                continue
            include_ids.append(nid)
            fields = node.get('fields') or []
            member_ids: list[str] = []
            for fidx, (fname, ftype) in enumerate(fields[:6]):
                cid = f'{nid}_f_{fidx}'
                member_ids.append(cid)
                lines.extend([
                    f'element "{cid}" as "column"',
                    '  with',
                    f'    title "{_ddn_escape(fname)}"',
                    f'    type "{_ddn_escape(ftype)}"',
                    '',
                ])
            lines.extend([
                f'element "{nid}" as "table"',
                '  with',
                f'    title "{_ddn_escape(node.get("title") or nid)}"',
                f'    level "{_ddn_escape(node.get("level") or "physical")}"',
            ])
            if member_ids:
                lines.append('  members')
                for cid in member_ids:
                    lines.extend(['    item', f'      id "{cid}"'])
            lines.append('')

            rel_id = f'rel_{root_id}_{nidx}'
            lines.extend([
                f'relation "{rel_id}" as "foreign_key"',
                '  with',
                '    title "hosts"',
                '  endpoints',
                '    item',
                f'      id "{root_id}"',
                '    item',
                f'      id "{nid}"',
                '',
            ])

        lines.extend([
            'view "main" as "ddn@1"',
            '  with',
            f'    title "{_ddn_escape(title_name)} Topology"',
            '  selection',
            '    include',
        ])
        for inc_id in include_ids:
            lines.extend(['      item', f'        id "{inc_id}"'])
        lines.append('')

        ddn_text = '\n'.join(lines)
        try:
            compiled = compile_robin_scene(ddn_text, view_id='main', use_cache=True)
            scene = slice_scene_response(compiled)
        except Exception:
            scene = None
        return ddn_text, scene

    # ------------------------------------------------------------------
    # Fleet Overview for Unbound Startup User Dashboard
    # ------------------------------------------------------------------

    def collect_fleet_summary(self) -> dict[str, Any]:
        uid = _actor_user_id()
        servers_out: list[dict[str, Any]] = []
        try:
            from pgadmin.model import Server
            for srv in Server.query.filter_by(user_id=uid).order_by(Server.name.asc()).limit(50):
                info = _resolve_engine_info(srv)
                local_f = self._inspect_local_files(info['route_cfg'])
                servers_out.append({
                    'server_id': int(srv.id),
                    'name': str(srv.name or ''),
                    'engine_id': info['engine_id'],
                    'engine_label': info['engine_label'],
                    'host': str(getattr(srv, 'host', '') or ''),
                    'port': getattr(srv, 'port', None),
                    'comment': str(getattr(srv, 'comment', '') or ''),
                    'verified': info['verified'],
                    'verified_version': info['verified_version'],
                    'disk_bytes': local_f.get('total_on_disk_bytes'),
                    'disk_formatted': _format_bytes(local_f.get('total_on_disk_bytes')),
                })
        except Exception:
            pass

        tracked: list[dict[str, Any]] = []
        retention = {'raw_hours': 24, 'rollup_5m_days': 30, 'rollup_1h_days': 365}
        try:
            ucfg = get_user_config_db()
            if ucfg.is_unlocked():
                tracked = ucfg.list_tracked_metric_objects(uid, limit=25)
                retention = ucfg.get_metrics_retention_policy(uid)
        except Exception:
            pass

        return {
            'captured_at': _now_iso(),
            'servers': servers_out,
            'tracked_metric_objects': tracked,
            'retention_policy': retention,
        }


def init_app(app, workspace_service) -> ObjectDashboardHost:
    existing = app.extensions.get(OBJECT_DASHBOARD_EXTENSION_KEY)
    if existing is not None:
        return existing

    host = ObjectDashboardHost(app, workspace_service)
    app.extensions[OBJECT_DASHBOARD_EXTENSION_KEY] = host

    bp = Blueprint(
        'cdeadmin_object_dashboard',
        __name__,
        url_prefix='/cdeadmin/api/object_dashboard',
    )

    try:
        from pgadmin.authenticate.mfa.utils import mfa_required  # noqa: F401
    except Exception:
        pass

    try:
        from pgadmin import pgCSRFProtect
        csrf_exempt = pgCSRFProtect.exempt
    except Exception:
        def csrf_exempt(fn):
            return fn

    def _require_auth():
        if not current_app.config.get('SERVER_MODE', True):
            return None
        if current_user and getattr(current_user, 'is_authenticated', False):
            return None
        return jsonify({'error': 'Authentication required', 'code': 'unauthenticated'}), 401

    @bp.route('/snapshot', methods=['GET'])
    @csrf_exempt
    def get_snapshot_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        win = str(request.args.get('window') or '1h').strip()
        rec = str(request.args.get('record_sample', '1')).strip() not in ('0', 'false', 'no')
        payload = host.collect_snapshot(request.args, window=win, record_sample=rec)
        return jsonify(payload)

    @bp.route('/deep_refresh', methods=['POST'])
    @csrf_exempt
    def post_deep_refresh_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            payload = host.compute_deep_stats(body)
            return jsonify(payload)
        except PermissionError as exc:
            return jsonify({'error': str(exc), 'code': 'disconnected'}), 409
        except Exception as exc:
            return jsonify({'error': str(exc), 'code': 'deep_refresh_failed'}), 400

    @bp.route('/properties', methods=['GET'])
    @csrf_exempt
    def get_properties_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        payload = host.collect_rich_properties(request.args)
        return jsonify(payload)

    @bp.route('/preferences', methods=['GET', 'POST'])
    @csrf_exempt
    def preferences_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        uid = _actor_user_id()
        ucfg = get_user_config_db()
        if not ucfg.is_unlocked():
            return jsonify({'error': 'UserConfigurationDatabase is locked', 'code': 'vault_locked'}), 423

        if request.method == 'GET':
            return jsonify({
                'dashboard': {
                    **DEFAULT_DASHBOARD_CUSTOMIZATION,
                    **ucfg.get_object_view_customization(uid, 'object_dashboard'),
                },
                'properties': {
                    **DEFAULT_PROPERTIES_CUSTOMIZATION,
                    **ucfg.get_object_view_customization(uid, 'object_properties'),
                },
                'retention_policy': ucfg.get_metrics_retention_policy(uid),
            })

        body = request.get_json(silent=True) or {}
        if isinstance(body.get('dashboard'), Mapping):
            merged_d = {
                **DEFAULT_DASHBOARD_CUSTOMIZATION,
                **ucfg.get_object_view_customization(uid, 'object_dashboard'),
                **dict(body['dashboard']),
            }
            ucfg.save_object_view_customization(uid, 'object_dashboard', merged_d)
        if isinstance(body.get('properties'), Mapping):
            merged_p = {
                **DEFAULT_PROPERTIES_CUSTOMIZATION,
                **ucfg.get_object_view_customization(uid, 'object_properties'),
                **dict(body['properties']),
            }
            ucfg.save_object_view_customization(uid, 'object_properties', merged_p)
        if isinstance(body.get('retention_policy'), Mapping):
            ucfg.set_metrics_retention_policy(uid, body['retention_policy'])

        return jsonify({
            'dashboard': {
                **DEFAULT_DASHBOARD_CUSTOMIZATION,
                **ucfg.get_object_view_customization(uid, 'object_dashboard'),
            },
            'properties': {
                **DEFAULT_PROPERTIES_CUSTOMIZATION,
                **ucfg.get_object_view_customization(uid, 'object_properties'),
            },
            'retention_policy': ucfg.get_metrics_retention_policy(uid),
        })

    @bp.route('/fleet', methods=['GET'])
    @csrf_exempt
    def get_fleet_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        return jsonify(host.collect_fleet_summary())

    if 'cdeadmin_object_dashboard' not in app.blueprints:
        app.register_blueprint(bp)

    return host
