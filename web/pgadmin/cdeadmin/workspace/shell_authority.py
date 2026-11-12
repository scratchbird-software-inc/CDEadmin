##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Server-side authority for the ScratchRobin Project Shell.

Provides authenticated endpoints for:
1. Post-login user authorization (permitted applications and per-action
   ``t_actions`` status overrides configured in Settings).
2. Global Settings and per-Application Settings (templates, default SQL
   reference scripts, tabbed-icon-bar/status defaults, and drawer size reset).
3. Server-enforced Lock Screen state and password-verified Unlock.
4. UI Language listing / switching and Help Reference content (SQL Reference,
   Database Engine Reference, Glossary of Terms).
5. Server-side ``t_actions`` invocation target dispatch.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import Any, Callable

import config as app_config_module
from flask import Blueprint, current_app, jsonify, make_response, request, session
from flask_login import current_user

SHELL_AUTHORITY_EXTENSION_KEY = 'cdeadmin_shell_authority'

CANONICAL_APPLICATIONS: tuple[dict[str, Any], ...] = (
    {
        'id': 'data-navigator',
        'label': 'Data Navigator',
        'icon': 'tool.data-explorer',
        'order': 10,
        'supports_left_drawer': True,
        'supports_right_drawer': True,
        'supports_tabbed_icon_bar': True,
        'supports_status_area': True,
        'default_left_width': 288,
        'default_right_width': 340,
    },
    {
        'id': 'sql-editor',
        'label': 'SQL Editor',
        'icon': 'tool.query',
        'order': 20,
        'supports_left_drawer': True,
        'supports_right_drawer': True,
        'supports_tabbed_icon_bar': True,
        'supports_status_area': True,
        'default_left_width': 260,
        'default_right_width': 320,
    },
    {
        'id': 'erd-designer',
        'label': 'ERD & Data Modelling',
        'icon': 'tool.erd',
        'order': 30,
        'supports_left_drawer': True,
        'supports_right_drawer': True,
        'supports_tabbed_icon_bar': True,
        'supports_status_area': True,
        'default_left_width': 280,
        'default_right_width': 340,
    },
    {
        'id': 'cube-designer',
        'label': 'Cube Designer',
        'icon': 'tool.cube',
        'order': 40,
        'supports_left_drawer': True,
        'supports_right_drawer': True,
        'supports_tabbed_icon_bar': True,
        'supports_status_area': True,
        'default_left_width': 280,
        'default_right_width': 340,
    },
    {
        'id': 'bi-designer',
        'label': 'BI Questions & Dashboards',
        'icon': 'tool.bi',
        'order': 50,
        'supports_left_drawer': True,
        'supports_right_drawer': True,
        'supports_tabbed_icon_bar': True,
        'supports_status_area': True,
        'default_left_width': 280,
        'default_right_width': 340,
    },
    {
        'id': 'screen-mesh-designer',
        'label': 'Screen Mesh Designer',
        'icon': 'tool.screen-mesh',
        'order': 60,
        'supports_left_drawer': True,
        'supports_right_drawer': True,
        'supports_tabbed_icon_bar': True,
        'supports_status_area': True,
        'default_left_width': 280,
        'default_right_width': 340,
    },
    {
        'id': 'schema-compare',
        'label': 'Schema Comparison',
        'icon': 'tool.schema-compare',
        'order': 70,
        'supports_left_drawer': False,
        'supports_right_drawer': True,
        'supports_tabbed_icon_bar': True,
        'supports_status_area': True,
        'default_left_width': 260,
        'default_right_width': 320,
        'required_permission': 'tools_schema_diff',
    },
    {
        'id': 'project-explorer',
        'label': 'Project Assets',
        'icon': 'tool.project-explorer',
        'order': 80,
        'supports_left_drawer': True,
        'supports_right_drawer': True,
        'supports_tabbed_icon_bar': True,
        'supports_status_area': True,
        'default_left_width': 280,
        'default_right_width': 320,
    },
    {
        'id': 'command-line',
        'label': 'Command Line',
        'icon': 'action.terminal',
        'order': 90,
        'supports_left_drawer': False,
        'supports_right_drawer': False,
        'supports_tabbed_icon_bar': False,
        'supports_status_area': True,
        'default_left_width': 240,
        'default_right_width': 280,
        'required_permission': 'tools_psql_tool',
    },
)

VALID_ACTION_STATUSES = frozenset({'enabled', 'disabled', 'invisible'})

BUILTIN_COLOR_SCHEME_IDS: tuple[str, ...] = (
    'light',
    'dark',
    'high_contrast_light',
    'high_contrast_dark',
    'nord_light',
    'nord_dark',
    'solarized_light',
    'solarized_dark',
    'forest_dark',
    'graphite_dark',
)

ENGINE_CATEGORIES: dict[str, str] = {
    'postgresql': 'Relational SQL',
    'firebird': 'Relational SQL',
    'mysql': 'Relational SQL',
    'mariadb': 'Relational SQL',
    'scratchbird': 'Convergent (CDE)',
    'sqlite': 'Embedded & File',
    'duckdb': 'Embedded & Analytical',
    'clickhouse': 'Analytical & Columnar',
    'cockroachdb': 'Distributed SQL',
    'yugabytedb': 'Distributed SQL',
    'tidb': 'Distributed SQL',
    'vitess': 'Distributed SQL',
    'dolt': 'Versioned SQL',
    'xtdb': 'Bitemporal SQL',
    'mongodb': 'Document & Multi-Model',
    'cassandra': 'Wide-Column & KV',
    'redis': 'Wide-Column & KV',
    'foundationdb': 'Wide-Column & KV',
    'tikv': 'Wide-Column & KV',
    'apache_ignite': 'In-Memory & Grid',
    'neo4j': 'Graph & Vector',
    'milvus': 'Graph & Vector',
    'opensearch': 'Search & Time-Series',
    'influxdb': 'Search & Time-Series',
    'immudb': 'Ledger & Immutable',
}

DEFAULT_SECURITY_GROUPS: tuple[dict[str, Any], ...] = (
    {
        'id': 'administrators',
        'name': 'Administrator',
        'description': 'Full administrative access to all applications, connectors, and settings.',
        'builtin': True,
        'enabled_applications': [item['id'] for item in CANONICAL_APPLICATIONS],
        'disabled_applications': [],
        'permissions': ['object_register_server', 'tools_query_tool', 'tools_schema_diff', 'tools_psql_tool', 'project.asset.edit'],
    },
    {
        'id': 'data-architects',
        'name': 'Data Architects',
        'description': 'ERD, Cube, BI, Screen Mesh designers, Schema Comparison, and SQL Editor.',
        'builtin': False,
        'enabled_applications': [
            'data-navigator',
            'sql-editor',
            'erd-designer',
            'cube-designer',
            'bi-designer',
            'screen-mesh-designer',
            'schema-compare',
            'project-explorer',
        ],
        'disabled_applications': ['command-line'],
        'permissions': ['tools_query_tool', 'tools_schema_diff', 'project.asset.edit'],
    },
    {
        'id': 'bi-analysts',
        'name': 'BI & Reporting Analysts',
        'description': 'Read/query access to Data Navigator, SQL Editor, Cube Designer, and BI Dashboards.',
        'builtin': False,
        'enabled_applications': [
            'data-navigator',
            'sql-editor',
            'cube-designer',
            'bi-designer',
            'project-explorer',
        ],
        'disabled_applications': [
            'erd-designer',
            'screen-mesh-designer',
            'schema-compare',
            'command-line',
        ],
        'permissions': ['tools_query_tool'],
    },
)

REFERENCE_TOPICS: dict[str, dict[str, Any]] = {
    'sql': {
        'topic': 'sql',
        'title': 'Multi-Engine SQL Reference',
        'entries': [
            {
                'id': 'select-cte',
                'title': 'SELECT & Common Table Expressions (WITH)',
                'syntax': 'WITH cte_name AS (SELECT ...) SELECT columns FROM cte_name WHERE ...;',
                'notes': (
                    'Supported across PostgreSQL, Firebird 3+, MySQL 8+, MariaDB 10.2+, '
                    'SQLite 3.8.3+, DuckDB, and SBsql.'
                ),
            },
            {
                'id': 'dml-returning',
                'title': 'INSERT / UPDATE / DELETE ... RETURNING',
                'syntax': 'INSERT INTO tbl (col) VALUES (:val) RETURNING id;',
                'notes': (
                    'Supported natively in PostgreSQL, Firebird, SQLite 3.35+, DuckDB, '
                    'and MariaDB 10.5+ (INSERT/DELETE/REPLACE).'
                ),
            },
            {
                'id': 'ddl-table',
                'title': 'CREATE / ALTER TABLE & Constraints',
                'syntax': (
                    'CREATE TABLE schema_name.table_name (\n'
                    '  id BIGINT PRIMARY KEY,\n'
                    '  created_at TIMESTAMP NOT NULL\n'
                    ');'
                ),
                'notes': (
                    'Use ERD & Data Modelling or Object Editor SQL preview to generate '
                    'engine-exact DDL and alter scripts.'
                ),
            },
            {
                'id': 'transactions',
                'title': 'Transactions & Savepoints',
                'syntax': 'BEGIN; SAVEPOINT sp1; ... ROLLBACK TO SAVEPOINT sp1; COMMIT;',
                'notes': (
                    'Firebird supports SNAPSHOT / READ COMMITTED RECORD_VERSION isolation; '
                    'PostgreSQL, MySQL InnoDB, MariaDB, SQLite, and DuckDB support ACID transactions.'
                ),
            },
        ],
    },
    'engines': {
        'topic': 'engines',
        'title': 'Database Engine Reference',
        'entries': [
            {
                'id': 'postgresql',
                'title': 'PostgreSQL',
                'summary': 'Schemas, extensions, row-level security, partitioned tables, MVCC, and PL/pgSQL.',
            },
            {
                'id': 'firebird',
                'title': 'Firebird 5',
                'summary': 'Domains, generators/sequences, triggers, packages, PSQL procedures, GDS/fbclient services, and embedded/network attachments.',
            },
            {
                'id': 'mysql-mariadb',
                'title': 'MySQL & MariaDB',
                'summary': 'Storage engines (InnoDB), character sets/collations, routines, events, binary-log replication, and physical backups.',
            },
            {
                'id': 'duckdb-sqlite',
                'title': 'DuckDB & SQLite',
                'summary': 'Embedded analytical (DuckDB Parquet/Arrow/extensions) and transactional file databases (SQLite WAL, PRAGMA integrity, recovery).',
            },
            {
                'id': 'scratchbird',
                'title': 'ScratchBird (SBsql)',
                'summary': 'Convergent data engine with UUID-backed canonical resource identity and multi-surface dialect access.',
            },
        ],
    },
    'glossary': {
        'topic': 'glossary',
        'title': 'ScratchRobin Glossary of Terms',
        'entries': [
            {
                'id': 'cde',
                'title': 'CDE (Convergent Data Engine)',
                'definition': 'A data-hypervisor architecture unifying administration, modelling, BI, and operations across multiple database engines.',
            },
            {
                'id': 't_actions',
                'title': 't_actions',
                'definition': 'Central action registry holding icon, i18n identifier (caption & hint), tri-state status (enabled/disabled/invisible), owning application, and client/server code target.',
            },
            {
                'id': 'ddn',
                'title': 'DDN (Diagram Design Notation)',
                'definition': 'Text-first versioned design notation stored in designs.db and Git powering ERD, Cube, BI, and Screen Mesh designers.',
            },
            {
                'id': 'floating-subform',
                'title': 'Floating Sub-Form',
                'definition': 'A detached application work window (with its bottom status area) movable to a secondary monitor while menus, drawers, and the tabbed-icon-bar remain on the Main Form.',
            },
            {
                'id': 'data-navigator',
                'title': 'Data Navigator',
                'definition': 'Standard ScratchRobin application presenting the multi-engine server/database/schema/object hierarchy in its Left Side Drawer and object inspection in its work area.',
            },
        ],
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_db_path(app: Any = None) -> str:
    cfg_dir = getattr(app_config_module, 'DATA_DIR', None)
    if app is not None:
        cfg_dir = app.config.get('DATA_DIR') or cfg_dir
    if not cfg_dir:
        cfg_dir = os.path.join(tempfile.gettempdir(), 'scratchrobin-shell')
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, 'shell_settings.db')


class ShellAuthorityStore:
    """SQLite-backed store for shell authorization, global settings, and app settings."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_schema()
        self._server_actions: dict[str, Callable[[dict[str, Any], str], Any]] = {}
        self._register_builtin_server_actions()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS shell_kv (
                    scope TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope, key)
                );
                """
            )

    def _register_builtin_server_actions(self) -> None:
        self.register_server_action(
            'project.session.lock',
            lambda _payload, _actor: {'locked': True},
        )
        self.register_server_action(
            'settings.drawers.reset',
            lambda payload, _actor: self.reset_application_drawers(
                str(payload.get('application') or 'data-navigator')
            ),
        )

    def register_server_action(
        self, action_id: str, handler: Callable[[dict[str, Any], str], Any]
    ) -> None:
        self._server_actions[str(action_id).strip()] = handler

    def invoke_server_action(
        self, action_id: str, payload: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        aid = str(action_id or '').strip()
        authz = self.resolve_user_authorization(actor)
        override = authz['action_overrides'].get(aid)
        if override in ('disabled', 'invisible'):
            raise PermissionError(f'Action {aid} is {override} for current user.')
        handler = self._server_actions.get(aid)
        if handler is None:
            raise KeyError(f'Unknown server action: {aid}')
        result = handler(dict(payload or {}), actor)
        return {'action_id': aid, 'status': 'ok', 'result': result}

    def _get_json(self, scope: str, key: str, default: Any) -> Any:
        with self._connect() as conn:
            row = conn.execute(
                'SELECT value_json FROM shell_kv WHERE scope = ? AND key = ?',
                (scope, key),
            ).fetchone()
        if not row:
            return default
        try:
            return json.loads(row['value_json'])
        except Exception:
            return default

    def _put_json(self, scope: str, key: str, value: Any) -> None:
        payload = json.dumps(value, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO shell_kv (scope, key, value_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scope, key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (scope, key, payload, _now_iso()),
            )

    def get_global_settings(self) -> dict[str, Any]:
        default_zoom = {
            'area_1': 100,
            'area_2': 100,
            'area_3a': 100,
            'area_3b': 100,
            'area_3c': 100,
            'area_3d': 100,
            'area_3e': 100,
        }
        default_typography = {
            'ui_font_family': '',
            'mono_font_family': '',
            'diagram_font_family': '',
            'ui_font_size': 14,
            'mono_font_size': 13,
            'line_height': 1.45,
            'mono_ligatures': True,
        }
        defaults = {
            'default_show_tabbed_icon_bar': True,
            'default_show_status_area': True,
            'lock_screen_timeout_minutes': 15,
            'panel_gap': 6,
            'area_zoom': dict(default_zoom),
            'active_color_scheme': 'light',
            'custom_color_schemes': [],
            'enabled_scheme_ids': list(BUILTIN_COLOR_SCHEME_IDS),
            'typography': dict(default_typography),
            'menu_placements': {},
            'quick_access': [
                'shell.quick.new',
                'shell.quick.save',
                'shell.quick.undo',
                'shell.quick.redo',
            ],
            'icon_assignments': {},
            'enabled_engines': [],
            'shared_templates': [
                {
                    'id': 'select-top-100',
                    'name': 'Inspect Top 100 Rows',
                    'sql': 'SELECT * FROM {{table}} FETCH FIRST 100 ROWS ONLY;',
                },
            ],
            'default_sql_reference_script': '-- ScratchRobin standard session header\n',
            'disabled_applications': [],
            'action_overrides': {},
        }
        stored = self._get_json('global', 'settings', {})
        if not isinstance(stored, dict):
            return defaults
        merged = {**defaults, **stored}
        try:
            merged['panel_gap'] = max(0, min(24, int(merged.get('panel_gap', 6))))
        except Exception:
            merged['panel_gap'] = 6
        try:
            merged['lock_screen_timeout_minutes'] = max(
                0, min(480, int(merged.get('lock_screen_timeout_minutes', 15)))
            )
        except Exception:
            merged['lock_screen_timeout_minutes'] = 15
        raw_zoom = merged.get('area_zoom') if isinstance(merged.get('area_zoom'), dict) else {}
        clean_zoom = dict(default_zoom)
        for k in default_zoom:
            if k in raw_zoom:
                try:
                    clean_zoom[k] = max(70, min(160, int(raw_zoom[k])))
                except Exception:
                    pass
        merged['area_zoom'] = clean_zoom
        raw_typo = merged.get('typography') if isinstance(merged.get('typography'), dict) else {}
        clean_typo = dict(default_typography)
        for key in ('ui_font_family', 'mono_font_family', 'diagram_font_family'):
            if isinstance(raw_typo.get(key), str):
                clean_typo[key] = raw_typo[key].strip()[:240]
        for key, lo, hi, fallback in (
            ('ui_font_size', 11, 24, 14),
            ('mono_font_size', 10, 24, 13),
        ):
            try:
                clean_typo[key] = max(lo, min(hi, int(raw_typo.get(key, fallback))))
            except Exception:
                clean_typo[key] = fallback
        try:
            clean_typo['line_height'] = round(
                max(1.1, min(2.2, float(raw_typo.get('line_height', 1.45)))), 2
            )
        except Exception:
            clean_typo['line_height'] = 1.45
        clean_typo['mono_ligatures'] = bool(raw_typo.get('mono_ligatures', True))
        merged['typography'] = clean_typo
        if not isinstance(merged.get('custom_color_schemes'), list):
            merged['custom_color_schemes'] = []
        if not isinstance(merged.get('enabled_scheme_ids'), list) or not merged['enabled_scheme_ids']:
            merged['enabled_scheme_ids'] = list(BUILTIN_COLOR_SCHEME_IDS)
        merged['active_color_scheme'] = str(merged.get('active_color_scheme') or 'light').strip() or 'light'
        if not isinstance(merged.get('menu_placements'), dict):
            merged['menu_placements'] = {}
        if not isinstance(merged.get('quick_access'), list):
            merged['quick_access'] = list(defaults['quick_access'])
        if not isinstance(merged.get('icon_assignments'), dict):
            merged['icon_assignments'] = {}
        if not isinstance(merged.get('enabled_engines'), list):
            merged['enabled_engines'] = []
        merged['disabled_applications'] = [
            str(x) for x in (merged.get('disabled_applications') or [])
            if str(x) != 'data-navigator'
        ]
        clean_overrides: dict[str, str] = {}
        for k, v in (merged.get('action_overrides') or {}).items():
            if str(v) in VALID_ACTION_STATUSES:
                clean_overrides[str(k)] = str(v)
        merged['action_overrides'] = clean_overrides
        return merged

    def update_global_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.get_global_settings()
        allowed = {
            'default_show_tabbed_icon_bar',
            'default_show_status_area',
            'lock_screen_timeout_minutes',
            'panel_gap',
            'area_zoom',
            'active_color_scheme',
            'custom_color_schemes',
            'enabled_scheme_ids',
            'typography',
            'menu_placements',
            'quick_access',
            'icon_assignments',
            'enabled_engines',
            'shared_templates',
            'default_sql_reference_script',
            'disabled_applications',
            'action_overrides',
        }
        if 'default_tabbed_icon_bar' in (patch or {}) and 'default_show_tabbed_icon_bar' not in (patch or {}):
            current['default_show_tabbed_icon_bar'] = bool(patch['default_tabbed_icon_bar'])
        for key, value in (patch or {}).items():
            if key in allowed:
                current[key] = value
        self._put_json('global', 'settings', current)
        return self.get_global_settings()

    def get_application_settings(self, application_id: str) -> dict[str, Any]:
        app_id = str(application_id or '').strip()
        catalog_entry = next(
            (item for item in CANONICAL_APPLICATIONS if item['id'] == app_id),
            None,
        )
        global_cfg = self.get_global_settings()
        defaults = {
            'application_id': app_id,
            'show_tabbed_icon_bar': bool(
                catalog_entry['supports_tabbed_icon_bar']
                if catalog_entry
                else True
            ) and bool(global_cfg.get('default_show_tabbed_icon_bar', True)),
            'show_status_area': bool(
                catalog_entry['supports_status_area']
                if catalog_entry
                else True
            ) and bool(global_cfg.get('default_show_status_area', True)),
            'left_drawer_width': int(
                catalog_entry['default_left_width'] if catalog_entry else 288
            ),
            'right_drawer_width': int(
                catalog_entry['default_right_width'] if catalog_entry else 340
            ),
            'default_left_drawer_width': int(
                catalog_entry['default_left_width'] if catalog_entry else 288
            ),
            'default_right_drawer_width': int(
                catalog_entry['default_right_width'] if catalog_entry else 340
            ),
            'default_left_drawer_open': bool(
                catalog_entry.get('supports_left_drawer', False) and app_id != 'sql-editor'
                if catalog_entry
                else False
            ),
            'default_right_drawer_open': False,
            'panel_gap': None,
            'area_zoom': {},
            'menu_placements': {},
            'notebookbar_placements': {},
            'quick_access': None,
            'default_sql_script': global_cfg.get('default_sql_reference_script', ''),
            'templates': list(global_cfg.get('shared_templates') or []),
            'drawer_reset_revision': 0,
        }
        stored = self._get_json('application', app_id, {})
        if not isinstance(stored, dict):
            return defaults
        merged = {**defaults, **stored, 'application_id': app_id}
        merged['left_drawer_width'] = max(
            180, min(640, int(merged.get('left_drawer_width') or defaults['left_drawer_width']))
        )
        merged['right_drawer_width'] = max(
            200, min(680, int(merged.get('right_drawer_width') or defaults['right_drawer_width']))
        )
        raw_gap = merged.get('panel_gap')
        if raw_gap is not None and raw_gap != '':
            try:
                merged['panel_gap'] = max(0, min(24, int(raw_gap)))
            except Exception:
                merged['panel_gap'] = None
        else:
            merged['panel_gap'] = None
        raw_zoom = merged.get('area_zoom') if isinstance(merged.get('area_zoom'), dict) else {}
        clean_app_zoom: dict[str, int] = {}
        for k, v in raw_zoom.items():
            if k in {'area_1', 'area_2', 'area_3a', 'area_3b', 'area_3c', 'area_3d', 'area_3e'} and v is not None and v != '':
                try:
                    clean_app_zoom[k] = max(70, min(160, int(v)))
                except Exception:
                    pass
        merged['area_zoom'] = clean_app_zoom
        if not isinstance(merged.get('menu_placements'), dict):
            merged['menu_placements'] = {}
        if not isinstance(merged.get('notebookbar_placements'), dict):
            merged['notebookbar_placements'] = {}
        if merged.get('quick_access') is not None and not isinstance(merged.get('quick_access'), list):
            merged['quick_access'] = None
        return merged

    def update_application_settings(
        self, application_id: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        app_id = str(application_id or '').strip()
        current = self.get_application_settings(app_id)
        allowed = {
            'show_tabbed_icon_bar',
            'show_status_area',
            'left_drawer_width',
            'right_drawer_width',
            'default_left_drawer_open',
            'default_right_drawer_open',
            'panel_gap',
            'area_zoom',
            'menu_placements',
            'notebookbar_placements',
            'quick_access',
            'default_sql_script',
            'templates',
        }
        if 'default_sql_reference_script' in (patch or {}) and 'default_sql_script' not in (patch or {}):
            current['default_sql_script'] = str(patch['default_sql_reference_script'] or '')
        for key, value in (patch or {}).items():
            if key in allowed:
                current[key] = value
        self._put_json('application', app_id, current)
        return self.get_application_settings(app_id)

    def reset_application_drawers(self, application_id: str) -> dict[str, Any]:
        app_id = str(application_id or '').strip()
        current = self.get_application_settings(app_id)
        current['left_drawer_width'] = current['default_left_drawer_width']
        current['right_drawer_width'] = current['default_right_drawer_width']
        current['drawer_reset_revision'] = int(
            current.get('drawer_reset_revision') or 0
        ) + 1
        self._put_json('application', app_id, current)
        return self.get_application_settings(app_id)

    def _list_stored_groups(self) -> list[dict[str, Any]]:
        stored = self._get_json('security', 'groups', None)
        if not isinstance(stored, list) or not stored:
            groups = [dict(g) for g in DEFAULT_SECURITY_GROUPS]
            self._put_json('security', 'groups', groups)
            return groups
        return [dict(g) for g in stored if isinstance(g, dict) and g.get('id')]

    def _list_stored_users(self) -> list[dict[str, Any]]:
        stored = self._get_json('security', 'users', None)
        if not isinstance(stored, list) or not stored:
            default_users = [
                {
                    'id': 'desktop',
                    'username': 'desktop',
                    'email': 'desktop@localhost',
                    'active': True,
                    'locked': False,
                    'auth_source': 'internal',
                    'groups': ['administrators'],
                    'enabled_applications': [],
                    'disabled_applications': [],
                }
            ]
            self._put_json('security', 'users', default_users)
            return default_users
        return [dict(u) for u in stored if isinstance(u, dict) and u.get('username')]

    def get_security_configuration(self) -> dict[str, Any]:
        global_cfg = self.get_global_settings()
        groups = self._list_stored_groups()
        users = self._list_stored_users()

        # Merge live SQLAlchemy Role / User rows when running inside full pgAdmin app
        try:
            from pgadmin.model import Role, User  # type: ignore
            db_roles = Role.query.all()
            existing_by_name = {str(g.get('name', '')).lower(): g for g in groups}
            for r in db_roles:
                rname = str(r.name or '').strip()
                if not rname:
                    continue
                key = rname.lower()
                perms = list(r.get_permissions()) if hasattr(r, 'get_permissions') else []
                if key in existing_by_name:
                    existing_by_name[key]['db_role_id'] = r.id
                    if perms:
                        existing_by_name[key]['permissions'] = perms
                else:
                    slug = key.replace(' ', '-')
                    groups.append(
                        {
                            'id': slug,
                            'db_role_id': r.id,
                            'name': rname,
                            'description': str(r.description or ''),
                            'builtin': rname == 'Administrator',
                            'enabled_applications': [a['id'] for a in CANONICAL_APPLICATIONS],
                            'disabled_applications': [],
                            'permissions': perms,
                        }
                    )

            db_users = User.query.all()
            existing_users = {str(u.get('username', '')).lower(): u for u in users}
            for u in db_users:
                uname = str(u.username or u.email or f'user-{u.id}')
                ukey = uname.lower()
                role_slugs = [
                    next(
                        (
                            g['id']
                            for g in groups
                            if str(g.get('name', '')).lower() == str(r.name or '').lower()
                        ),
                        str(r.name or '').lower().replace(' ', '-'),
                    )
                    for r in (u.roles or [])
                ]
                user_rules = self._get_json('authorization_user', uname, {})
                entry = {
                    'id': str(u.id),
                    'username': uname,
                    'email': str(u.email or ''),
                    'active': bool(u.active),
                    'locked': bool(getattr(u, 'locked', False)),
                    'auth_source': str(getattr(u, 'auth_source', 'internal') or 'internal'),
                    'groups': role_slugs or ['administrators'],
                    'enabled_applications': list(user_rules.get('enabled_applications') or []),
                    'disabled_applications': list(user_rules.get('disabled_applications') or []),
                }
                if ukey in existing_users:
                    existing_users[ukey].update(entry)
                else:
                    users.append(entry)
        except Exception:
            pass

        permission_catalog = [
            {'id': 'object_register_server', 'category': 'Catalog & Servers', 'label': 'Register & Manage Servers'},
            {'id': 'tools_query_tool', 'category': 'Query & Execution', 'label': 'Execute SQL Queries'},
            {'id': 'tools_psql_tool', 'category': 'Query & Execution', 'label': 'Open Native Command Line'},
            {'id': 'tools_schema_diff', 'category': 'Schema & Migration', 'label': 'Run Schema Comparison'},
            {'id': 'schema_compare.apply', 'category': 'Schema & Migration', 'label': 'Approve & Apply Migration Plans'},
            {'id': 'project.asset.edit', 'category': 'Designers & DDN', 'label': 'Edit Project & DDN Designs'},
            {'id': 'design.version.accept', 'category': 'Designers & DDN', 'label': 'Accept DDN Design Versions (Gate)'},
            {'id': 'bi.outward.publish', 'category': 'BI & Dashboards', 'label': 'Enable BI Alerts, Embeds & Remote Server'},
            {'id': 'ai.propose', 'category': 'AI Assistant', 'label': 'Draft Queries & BI Questions with AI'},
        ]

        return {
            'schema': 'cdeadmin.shell-security.v1',
            'system_disabled_applications': list(global_cfg.get('disabled_applications') or []),
            'applications': [
                {
                    'id': item['id'],
                    'label': item['label'],
                    'icon': item['icon'],
                    'system_enabled': item['id'] not in set(global_cfg.get('disabled_applications') or []),
                    'core': item['id'] == 'data-navigator',
                }
                for item in CANONICAL_APPLICATIONS
            ],
            'groups': groups,
            'users': users,
            'permission_catalog': permission_catalog,
        }

    def save_security_group(self, group_payload: dict[str, Any]) -> dict[str, Any]:
        groups = self._list_stored_groups()
        raw_name = str(group_payload.get('name') or '').strip()
        if not raw_name:
            raise ValueError('Group name is required.')
        gid = str(group_payload.get('id') or '').strip() or raw_name.lower().replace(' ', '-')
        enabled_apps = [str(x) for x in (group_payload.get('enabled_applications') or [])]
        if 'data-navigator' not in enabled_apps:
            enabled_apps.insert(0, 'data-navigator')
        disabled_apps = [
            str(x)
            for x in (group_payload.get('disabled_applications') or [])
            if str(x) != 'data-navigator' and str(x) not in enabled_apps
        ]
        perms = [str(x) for x in (group_payload.get('permissions') or [])]
        record = {
            'id': gid,
            'name': raw_name,
            'description': str(group_payload.get('description') or '').strip(),
            'builtin': bool(group_payload.get('builtin', gid == 'administrators')),
            'enabled_applications': enabled_apps,
            'disabled_applications': disabled_apps,
            'permissions': perms,
        }
        replaced = False
        for idx, existing in enumerate(groups):
            if existing.get('id') == gid:
                record['builtin'] = bool(existing.get('builtin', False))
                groups[idx] = record
                replaced = True
                break
        if not replaced:
            groups.append(record)
        self._put_json('security', 'groups', groups)

        # Sync to SQLAlchemy Role table when active
        try:
            from pgadmin.model import Role, db  # type: ignore
            role_row = Role.query.filter_by(name=raw_name).first()
            if role_row is None:
                role_row = Role(name=raw_name, description=record['description'])
                db.session.add(role_row)
            else:
                role_row.description = record['description']
            if hasattr(role_row, 'permissions'):
                role_row.permissions = ','.join(perms)
            db.session.commit()
        except Exception:
            pass

        return self.get_security_configuration()

    def delete_security_group(self, group_id: str) -> dict[str, Any]:
        gid = str(group_id or '').strip()
        groups = self._list_stored_groups()
        target = next((g for g in groups if g.get('id') == gid), None)
        if target and target.get('builtin'):
            raise ValueError('Built-in Administrator group cannot be deleted.')
        groups = [g for g in groups if g.get('id') != gid]
        self._put_json('security', 'groups', groups)
        return self.get_security_configuration()

    def save_security_user(self, user_payload: dict[str, Any]) -> dict[str, Any]:
        users = self._list_stored_users()
        uname = str(user_payload.get('username') or '').strip()
        if not uname:
            raise ValueError('Username is required.')
        uid = str(user_payload.get('id') or uname).strip()
        groups = [str(g) for g in (user_payload.get('groups') or ['administrators']) if str(g).strip()]
        enabled_apps = [str(x) for x in (user_payload.get('enabled_applications') or [])]
        disabled_apps = [
            str(x) for x in (user_payload.get('disabled_applications') or []) if str(x) != 'data-navigator'
        ]
        record = {
            'id': uid,
            'username': uname,
            'email': str(user_payload.get('email') or f'{uname}@localhost').strip(),
            'active': bool(user_payload.get('active', True)),
            'locked': bool(user_payload.get('locked', False)),
            'auth_source': str(user_payload.get('auth_source') or 'internal'),
            'groups': groups,
            'enabled_applications': enabled_apps,
            'disabled_applications': disabled_apps,
        }
        replaced = False
        for idx, existing in enumerate(users):
            if str(existing.get('username', '')).lower() == uname.lower() or str(existing.get('id')) == uid:
                users[idx] = record
                replaced = True
                break
        if not replaced:
            users.append(record)
        self._put_json('security', 'users', users)
        self.update_user_authorization(
            uname,
            {
                'enabled_applications': enabled_apps,
                'disabled_applications': disabled_apps,
                'action_overrides': user_payload.get('action_overrides') or {},
            },
        )
        return self.get_security_configuration()

    def delete_security_user(self, username_or_id: str) -> dict[str, Any]:
        key = str(username_or_id or '').strip().lower()
        if key in ('desktop', 'administrator'):
            raise ValueError('Primary desktop/administrator account cannot be removed.')
        users = [
            u
            for u in self._list_stored_users()
            if str(u.get('username', '')).lower() != key and str(u.get('id', '')).lower() != key
        ]
        self._put_json('security', 'users', users)
        return self.get_security_configuration()

    def list_database_engines(self) -> dict[str, Any]:
        global_cfg = self.get_global_settings()
        stored_enabled = set(str(x) for x in (global_cfg.get('enabled_engines') or []))
        has_stored_list = bool(self._get_json('global', 'engines_initialized', False))

        # Discover full engine catalog from browser.server_groups.engine_types when available
        catalog_rows: list[dict[str, Any]] = []
        try:
            from pgadmin.browser.server_groups.engine_types import (
                ENGINE_LABELS,
                engine_registration_profiles,
                localhost_engine_status,
                supported_engine_types,
            )
            from pgadmin.cdeadmin.endpoints import registration_profiles

            active_profiles = registration_profiles()
            supported = list(supported_engine_types(active_profiles))
            if 'scratchbird' not in {eid for eid, _ in supported} and 'scratchbird' in ENGINE_LABELS:
                supported.append(('scratchbird', ENGINE_LABELS['scratchbird']))
                supported.sort(key=lambda item: item[1])

            for engine_id, label in supported:
                pref_enabled = None
                try:
                    from pgadmin.utils.preferences import Preferences
                    pref = Preferences.module('NODE-engine_type').preference(f'show_connector_{engine_id}')
                    if pref is not None:
                        pref_enabled = bool(pref.get())
                except Exception:
                    pref_enabled = None

                enabled = (
                    pref_enabled
                    if pref_enabled is not None
                    else (engine_id in stored_enabled if has_stored_list else engine_id in {'postgresql', 'firebird', 'sqlite', 'duckdb', 'mysql', 'mariadb', 'scratchbird'})
                )
                profiles = engine_registration_profiles(engine_id, active_profiles)
                ports = sorted(
                    {
                        int(p['default_port'])
                        for p in profiles
                        if isinstance(p.get('default_port'), int)
                    }
                )
                interfaces = [str(p.get('profile_id') or engine_id) for p in profiles]
                try:
                    local_obs = localhost_engine_status(engine_id, active_profiles)
                except Exception:
                    local_obs = {'available': False, 'observation': 'unknown'}

                catalog_rows.append(
                    {
                        'id': engine_id,
                        'label': label,
                        'category': ENGINE_CATEGORIES.get(engine_id, 'Database Engine'),
                        'icon': f'engine.{engine_id}',
                        'enabled': bool(enabled),
                        'interfaces': interfaces,
                        'default_ports': ports,
                        'local_available': bool(local_obs.get('available', False)),
                        'observation': str(local_obs.get('observation') or ''),
                    }
                )
        except Exception:
            for engine_id, category in sorted(ENGINE_CATEGORIES.items()):
                catalog_rows.append(
                    {
                        'id': engine_id,
                        'label': engine_id.replace('_', ' ').title(),
                        'category': category,
                        'icon': f'engine.{engine_id}',
                        'enabled': engine_id in stored_enabled if has_stored_list else engine_id in {'postgresql', 'firebird', 'sqlite', 'duckdb', 'mysql', 'mariadb'},
                        'interfaces': [engine_id],
                        'default_ports': [],
                        'local_available': False,
                        'observation': '',
                    }
                )

        return {
            'schema': 'cdeadmin.shell-engines.v1',
            'engines': catalog_rows,
            'enabled_engine_ids': [row['id'] for row in catalog_rows if row['enabled']],
        }

    def update_database_engines(self, enabled_engine_ids: list[str]) -> dict[str, Any]:
        clean_ids = sorted({str(x).strip() for x in (enabled_engine_ids or []) if str(x).strip()})
        self.update_global_settings({'enabled_engines': clean_ids})
        self._put_json('global', 'engines_initialized', True)

        # Synchronize live Object Explorer connector preferences when Preferences DB is active
        try:
            from pgadmin.utils.preferences import Preferences
            mod = Preferences.module('NODE-engine_type', create=False)
            if mod is not None:
                for eid in ENGINE_CATEGORIES:
                    pref = mod.preference(f'show_connector_{eid}')
                    if pref is not None:
                        pref.set(eid in clean_ids)
        except Exception:
            pass

        return self.list_database_engines()

    def resolve_user_authorization(
        self, username: str, user_obj: Any = None
    ) -> dict[str, Any]:
        global_cfg = self.get_global_settings()
        user_key = str(username or 'anonymous')
        user_rules = self._get_json('authorization_user', user_key, {})

        # System-wide disabled applications cannot be launched until re-enabled in Security
        system_disabled = set(global_cfg.get('disabled_applications') or [])
        disabled = set(system_disabled)

        # Apply group-level grants/revocations for the user's assigned groups
        groups_by_id = {g['id']: g for g in self._list_stored_groups()}
        stored_users = {str(u.get('username', '')).lower(): u for u in self._list_stored_users()}
        matched_user = stored_users.get(user_key.lower())
        if matched_user and not matched_user.get('active', True):
            disabled.update(item['id'] for item in CANONICAL_APPLICATIONS if item['id'] != 'data-navigator')
        elif matched_user and matched_user.get('groups'):
            group_allowed: set[str] = set()
            group_denied: set[str] = set()
            for gid in matched_user['groups']:
                grp = groups_by_id.get(gid)
                if not grp:
                    continue
                group_allowed.update(str(x) for x in (grp.get('enabled_applications') or []))
                group_denied.update(str(x) for x in (grp.get('disabled_applications') or []))
            for denied_app in group_denied - group_allowed:
                disabled.add(denied_app)

        # Apply per-user overrides (while still respecting system_disabled if explicitly turned off globally,
        # unless enabled_applications explicitly grants back to this user when system allows it)
        if isinstance(user_rules, dict):
            disabled.update(str(x) for x in (user_rules.get('disabled_applications') or []))
            for allowed_app in (user_rules.get('enabled_applications') or []):
                if str(allowed_app) not in system_disabled:
                    disabled.discard(str(allowed_app))
        # data-navigator is the standard application and remains first when permitted
        disabled.discard('data-navigator')

        applications: list[dict[str, Any]] = []
        for entry in CANONICAL_APPLICATIONS:
            app_id = entry['id']
            perm = entry.get('required_permission')
            permitted_by_role = True
            if perm and user_obj is not None and hasattr(user_obj, 'has_permission'):
                try:
                    permitted_by_role = bool(user_obj.has_permission(perm))
                except Exception:
                    permitted_by_role = True
            if app_id == 'command-line' and not getattr(
                app_config_module, 'ENABLE_PSQL', True
            ):
                permitted_by_role = False

            authorized = permitted_by_role and (app_id not in disabled)
            app_settings = self.get_application_settings(app_id)
            applications.append(
                {
                    **entry,
                    'authorized': authorized,
                    'status': 'enabled' if authorized else 'invisible',
                    'settings': app_settings,
                }
            )

        action_overrides = dict(global_cfg.get('action_overrides') or {})
        if isinstance(user_rules, dict):
            for k, v in (user_rules.get('action_overrides') or {}).items():
                if str(v) in VALID_ACTION_STATUSES:
                    action_overrides[str(k)] = str(v)

        return {
            'schema': 'cdeadmin.shell-authorization.v1',
            'username': user_key,
            'applications': applications,
            'authorized_application_ids': [
                a['id'] for a in applications if a['authorized']
            ],
            'action_overrides': action_overrides,
            'global_settings': global_cfg,
        }

    def update_user_authorization(
        self, username: str, rules: dict[str, Any]
    ) -> dict[str, Any]:
        user_key = str(username or 'anonymous')
        cleaned = {
            'disabled_applications': [
                str(x)
                for x in (rules.get('disabled_applications') or [])
                if str(x) != 'data-navigator'
            ],
            'enabled_applications': [
                str(x) for x in (rules.get('enabled_applications') or [])
            ],
            'action_overrides': {
                str(k): str(v)
                for k, v in (rules.get('action_overrides') or {}).items()
                if str(v) in VALID_ACTION_STATUSES
            },
        }
        self._put_json('authorization_user', user_key, cleaned)
        return self.resolve_user_authorization(user_key)


def _actor_username() -> str:
    if getattr(current_user, 'is_authenticated', False):
        return str(getattr(current_user, 'username', None) or getattr(current_user, 'email', None) or 'authenticated')
    return 'desktop'


def _verify_unlock_credentials(password: str) -> tuple[bool, str]:
    server_mode = bool(getattr(app_config_module, 'SERVER_MODE', True))
    user_pw_hash = getattr(current_user, 'password', None)
    if server_mode and user_pw_hash:
        if not password:
            return False, 'Password is required to unlock this session.'
        try:
            from flask_security.utils import verify_password
            if verify_password(password, user_pw_hash):
                return True, ''
            return False, 'Incorrect password.'
        except Exception:
            return False, 'Password verification failed.'
    # Desktop mode or external SSO/Kerberos without local password hash:
    # if a password hash exists and password was supplied, check it; otherwise allow unlock.
    if user_pw_hash and password:
        try:
            from flask_security.utils import verify_password
            if not verify_password(password, user_pw_hash):
                return False, 'Incorrect password.'
        except Exception:
            return False, 'Password verification failed.'
    return True, ''


def store_for_app(app: Any = None) -> ShellAuthorityStore:
    target_app = app or current_app
    existing = target_app.extensions.get(SHELL_AUTHORITY_EXTENSION_KEY)
    if existing is not None:
        return existing
    store = ShellAuthorityStore(_default_db_path(target_app))
    target_app.extensions[SHELL_AUTHORITY_EXTENSION_KEY] = store
    return store


def init_app(app: Any, db_path: str | None = None) -> ShellAuthorityStore:
    existing = app.extensions.get(SHELL_AUTHORITY_EXTENSION_KEY)
    if existing is not None:
        return existing

    store = ShellAuthorityStore(db_path or _default_db_path(app))
    app.extensions[SHELL_AUTHORITY_EXTENSION_KEY] = store

    try:
        from pgadmin.utils.csrf import pgCSRFProtect
        csrf_exempt = pgCSRFProtect.exempt
    except Exception:  # pragma: no cover
        def csrf_exempt(fn):
            return fn

    def _require_auth():
        if getattr(app_config_module, 'SERVER_MODE', True) and not getattr(
            current_user, 'is_authenticated', False
        ):
            return jsonify({'error': 'Authentication required', 'code': 'unauthenticated'}), 401
        return None

    bp = Blueprint('cdeadmin_shell_authority', __name__, url_prefix='/cdeadmin/api/shell')

    @bp.route('/authorization', methods=['GET'])
    @csrf_exempt
    def get_authorization_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        actor = _actor_username()
        payload = store.resolve_user_authorization(actor, current_user)
        payload['session_locked'] = bool(session.get('cdeadmin_screen_locked', False))
        return jsonify(payload)

    @bp.route('/authorization', methods=['PUT'])
    def put_authorization_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        target_user = str(body.get('username') or _actor_username())
        if target_user != _actor_username() and hasattr(current_user, 'has_role'):
            if not current_user.has_role('Administrator'):
                return jsonify({'error': 'Administrator role required', 'code': 'forbidden'}), 403
        if 'global' in body and isinstance(body['global'], dict):
            store.update_global_settings(body['global'])
        updated = store.update_user_authorization(target_user, body)
        return jsonify(updated)

    @bp.route('/settings', methods=['GET'])
    @csrf_exempt
    def get_settings_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        app_id = request.args.get('application')
        if app_id:
            return jsonify({
                'scope': 'application',
                'settings': store.get_application_settings(app_id),
            })
        return jsonify({
            'scope': 'global',
            'settings': store.get_global_settings(),
            'applications': {
                item['id']: store.get_application_settings(item['id'])
                for item in CANONICAL_APPLICATIONS
            },
        })

    @bp.route('/settings', methods=['PUT'])
    def put_settings_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        app_id = body.get('application_id') or request.args.get('application')
        if app_id:
            patch = body.get('applications', {}).get(str(app_id)) if isinstance(body.get('applications'), dict) else None
            return jsonify({
                'scope': 'application',
                'settings': store.update_application_settings(
                    str(app_id), patch if isinstance(patch, dict) else body
                ),
            })
        updated_apps = {}
        if isinstance(body.get('applications'), dict):
            for target_app, app_patch in body['applications'].items():
                if isinstance(app_patch, dict):
                    updated_apps[str(target_app)] = store.update_application_settings(
                        str(target_app), app_patch
                    )
            if not body.get('global'):
                return jsonify({'scope': 'application', 'applications': updated_apps})
        global_patch = body['global'] if isinstance(body.get('global'), dict) else body
        return jsonify({
            'scope': 'global',
            'settings': store.update_global_settings(global_patch),
            'applications': updated_apps or {
                item['id']: store.get_application_settings(item['id'])
                for item in CANONICAL_APPLICATIONS
            },
        })

    @bp.route('/settings/<application_id>/reset-drawers', methods=['POST'])
    def reset_drawers_route(application_id: str):
        denied = _require_auth()
        if denied is not None:
            return denied
        return jsonify({
            'scope': 'application',
            'settings': store.reset_application_drawers(application_id),
        })

    @bp.route('/session/status', methods=['GET'])
    @csrf_exempt
    def session_status_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        return jsonify({
            'locked': bool(session.get('cdeadmin_screen_locked', False)),
            'username': _actor_username(),
            'server_mode': bool(getattr(app_config_module, 'SERVER_MODE', True)),
        })

    @bp.route('/session/lock', methods=['POST'])
    def session_lock_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        session['cdeadmin_screen_locked'] = True
        session.modified = True
        return jsonify({'locked': True, 'username': _actor_username()})

    @bp.route('/session/unlock', methods=['POST'])
    def session_unlock_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        password = str(body.get('password') or '')
        ok, err = _verify_unlock_credentials(password)
        if not ok:
            return jsonify({'locked': True, 'error': err, 'code': 'invalid_credentials'}), 403
        session['cdeadmin_screen_locked'] = False
        session.modified = True
        return jsonify({'locked': False, 'username': _actor_username()})

    @bp.route('/languages', methods=['GET'])
    @csrf_exempt
    def list_languages_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        langs = getattr(app_config_module, 'LANGUAGES', {'en': 'English'}) or {'en': 'English'}
        current_lang = request.cookies.get('PGADMIN_LANGUAGE') or 'en'
        try:
            from pgadmin.utils.preferences import Preferences
            pref = Preferences.module('misc').preference('user_language')
            if pref:
                current_lang = pref.get() or current_lang
        except Exception:
            pass
        return jsonify({
            'current': current_lang,
            'languages': [
                {'code': str(code), 'label': str(label)}
                for code, label in langs.items()
            ],
        })

    @bp.route('/language', methods=['POST'])
    def set_language_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        langs = getattr(app_config_module, 'LANGUAGES', {'en': 'English'}) or {'en': 'English'}
        requested = str(body.get('language') or 'en').strip()
        if requested not in langs:
            return jsonify({'error': f'Unsupported language: {requested}', 'code': 'invalid_language'}), 400
        try:
            from pgadmin.utils.preferences import Preferences
            pref = Preferences.module('misc').preference('user_language')
            if pref:
                pref.set(requested)
        except Exception:
            pass
        resp = make_response(jsonify({'current': requested, 'label': str(langs[requested])}))
        resp.set_cookie(
            'PGADMIN_LANGUAGE',
            value=requested,
            path=getattr(app_config_module, 'SESSION_COOKIE_PATH', '/'),
            secure=bool(getattr(app_config_module, 'SESSION_COOKIE_SECURE', False)),
            httponly=bool(getattr(app_config_module, 'SESSION_COOKIE_HTTPONLY', True)),
            samesite=getattr(app_config_module, 'SESSION_COOKIE_SAMESITE', 'Lax'),
        )
        return resp

    @bp.route('/reference/<topic>', methods=['GET'])
    @csrf_exempt
    def get_reference_topic_route(topic: str):
        denied = _require_auth()
        if denied is not None:
            return denied
        data = REFERENCE_TOPICS.get(str(topic or '').strip().lower())
        if data is None:
            return jsonify({'error': f'Unknown reference topic: {topic}', 'code': 'not_found'}), 404
        return jsonify(data)

    @bp.route('/actions/<path:action_id>/invoke', methods=['POST'])
    def invoke_action_route(action_id: str):
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            outcome = store.invoke_server_action(action_id, body, _actor_username())
            return jsonify(outcome)
        except PermissionError as exc:
            return jsonify({'error': str(exc), 'code': 'forbidden'}), 403
        except KeyError as exc:
            return jsonify({'error': str(exc), 'code': 'not_found'}), 404

    @bp.route('/engines', methods=['GET'])
    @csrf_exempt
    def get_engines_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        return jsonify(store.list_database_engines())

    @bp.route('/engines', methods=['PUT'])
    def put_engines_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        if 'engine_id' in body and 'enabled' in body:
            current_ids = set(store.list_database_engines()['enabled_engine_ids'])
            eid = str(body['engine_id']).strip()
            if body['enabled']:
                current_ids.add(eid)
            else:
                current_ids.discard(eid)
            return jsonify(store.update_database_engines(sorted(current_ids)))
        return jsonify(store.update_database_engines(body.get('enabled_engines') or []))

    @bp.route('/security', methods=['GET'])
    @csrf_exempt
    def get_security_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        return jsonify(store.get_security_configuration())

    @bp.route('/security', methods=['PUT'])
    def put_security_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        if 'system_disabled_applications' in body:
            store.update_global_settings(
                {'disabled_applications': list(body.get('system_disabled_applications') or [])}
            )
        return jsonify(store.get_security_configuration())

    @bp.route('/security/groups', methods=['POST'])
    def save_security_group_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(store.save_security_group(body))
        except ValueError as exc:
            return jsonify({'error': str(exc), 'code': 'invalid_group'}), 400

    @bp.route('/security/groups/<group_id>', methods=['DELETE'])
    def delete_security_group_route(group_id: str):
        denied = _require_auth()
        if denied is not None:
            return denied
        try:
            return jsonify(store.delete_security_group(group_id))
        except ValueError as exc:
            return jsonify({'error': str(exc), 'code': 'invalid_group'}), 400

    @bp.route('/security/users', methods=['POST'])
    def save_security_user_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(store.save_security_user(body))
        except ValueError as exc:
            return jsonify({'error': str(exc), 'code': 'invalid_user'}), 400

    @bp.route('/security/users/<username>', methods=['DELETE'])
    def delete_security_user_route(username: str):
        denied = _require_auth()
        if denied is not None:
            return denied
        try:
            return jsonify(store.delete_security_user(username))
        except ValueError as exc:
            return jsonify({'error': str(exc), 'code': 'invalid_user'}), 400

    if 'cdeadmin_shell_authority' not in app.blueprints:
        app.register_blueprint(bp)
    return store
