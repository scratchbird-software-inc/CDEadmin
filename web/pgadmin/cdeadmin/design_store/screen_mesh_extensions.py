##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Screen Mesh Designer Phase 1 & 2 extensions (SR-F-030021, SR-F-030022).

Implements:
- ``trace_screenshot_regions_to_mesh`` ("Trace as mesh", SR-F-030021): converts
  annotated screenshot ``ui.region`` hotspots into typed ``wireframe.ui@1``
  controls on a companion screen, preserving exact ``(x, y, width, height)``
  geometry and copying every data/resource binding.
- ``build_screen_mesh_field_spec`` ("Field table" specification & exporter,
  SR-F-030022): joins every screen, control, ``ui.grid`` column, ``ui.region``
  hotspot and ``navigation`` link against authoritative ``binding`` rows in
  ``designs.db``, project physical ERD designs, and optional catalog metadata,
  formatting Markdown, CSV, HTML and JSON developer handoff specifications.
- ``compare_screen_mesh_screenshots`` ("Compare with newer screenshot",
  SR-F-030021): computes pixel & bounding-box diffs between a stored
  ``asset_blob`` screenshot and a newer PNG/JPEG/WebP capture (Pillow primary
  with a pure-Python PNG/grid fallback), flags affected ``ui.region`` hotspots,
  and optionally replaces the screenshot blob in a new checkpoint.
"""

from __future__ import annotations

import base64
from collections import deque
import copy
import csv
import hashlib
import html
import io
import re
import struct
from typing import Any, Mapping
import zlib

from .ddn_elements import _parse_blocks
from .identifiers import uuid7
from .screen_mesh_ddn import (
    _BINDING_TARGET_MAP,
    _PNG_SIGNATURE,
    UI_CONTROL_ROLES,
    ScreenMeshSync,
    _paeth_predictor,
    _slug,
    inspect_image_header,
)
from .service import (
    DesignStore,
    DesignStoreError,
    DesignStoreNotFound,
)
from .shared_ddn import StoreDDNProcess, _extract_physical_erd_model

try:
    from PIL import Image as _PILImage
    from PIL import ImageChops as _PILImageChops

    _HAS_PIL = True
except Exception:  # pragma: no cover - optional runtime acceleration
    _PILImage = None
    _PILImageChops = None
    _HAS_PIL = False


_DEFAULT_RE = re.compile(
    r'^\s+default(?:_value)?\s+"((?:[^"]|"")*)"\s*$', re.MULTILINE
)

_BUTTON_KEYWORDS = frozenset({
    'button',
    'btn',
    'submit',
    'save',
    'cancel',
    'close',
    'delete',
    'remove',
    'apply',
    'confirm',
    'approve',
    'reject',
    'lookup',
    'search',
    'refresh',
    'export',
    'next',
    'back',
})

_GRID_KEYWORDS = frozenset({
    'grid',
    'table',
    'list',
    'rows',
    'items',
    'lines',
    'records',
    'results',
    'entries',
    'parts',
    'history',
})

_DROPDOWN_SUFFIXES = (
    '_status',
    '_type',
    '_kind',
    '_mode',
    '_state',
    '_category',
    '_role',
    '_stage',
    '_priority',
)

_BOOLEAN_PREFIXES = ('is_', 'has_', 'can_', 'allow_', 'enable_', 'should_')
_BOOLEAN_SUFFIXES = ('_flag', '_enabled', '_active', '_checked', '_exempt')


def _strip_data_url(raw_b64: str, fallback_media: str = 'image/png') -> tuple[bytes, str]:
    text = str(raw_b64 or '').strip()
    media_type = str(fallback_media or 'image/png').strip().lower()
    if ',' in text and text.startswith('data:'):
        header, text = text.split(',', 1)
        mime_part = header[5:].split(';', 1)[0].strip().lower()
        if mime_part:
            media_type = mime_part
    if media_type == 'image/jpg':
        media_type = 'image/jpeg'
    if not text:
        raise DesignStoreError('Base64 image data is required')
    try:
        decoded = base64.b64decode(text)
    except Exception as exc:
        raise DesignStoreError(f'Invalid base64 image payload: {exc}') from exc
    if not decoded:
        raise DesignStoreError('Decoded screenshot image bytes are empty')
    return decoded, media_type


# ---------------------------------------------------------------------------
# Catalog & Physical ERD Metadata Indexing (for Trace + Field Spec)
# ---------------------------------------------------------------------------


def _normalize_catalog_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    dtype = str(
        entry.get('catalog_type')
        or entry.get('datatype')
        or entry.get('type')
        or entry.get('data_type')
        or ''
    ).strip()
    raw_null = entry.get('nullable')
    if raw_null is None and 'not_null' in entry:
        nullable: bool | None = not bool(entry.get('not_null'))
    elif raw_null is None:
        nullable = None
    else:
        nullable = bool(raw_null)
    default_val = entry.get('default_value')
    if default_val is None:
        default_val = entry.get('default')
    return {
        'catalog_type': dtype,
        'nullable': nullable,
        'default_value': (
            str(default_val) if default_val is not None else None
        ),
        'is_foreign_key': bool(
            entry.get('is_foreign_key') or entry.get('foreign_key')
        ),
        'is_primary_key': bool(
            entry.get('is_primary_key') or entry.get('primary_key')
        ),
    }


def _index_ref_variants(
    col_map: dict[str, dict[str, Any]],
    ref_key: str,
    info: dict[str, Any],
) -> None:
    clean = str(ref_key or '').strip().lower()
    if not clean:
        return
    col_map[clean] = info
    parts = [p for p in clean.split('.') if p]
    if len(parts) >= 3:
        # Also index <table_name>.<column_name> when schema/engine prefixed
        col_map['.'.join(parts[-2:])] = info


def _collect_project_catalog_lookup(
    store: DesignStore,
    project_id: str,
    catalog_metadata: Any = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Build column and table metadata indexes from project ERDs + payload."""
    col_lookup: dict[str, dict[str, Any]] = {}
    table_columns: dict[str, list[dict[str, Any]]] = {}

    # 1. Discover physical ERD tables & columns in the same project_id
    erd_summaries = store.list_designs(project_id=project_id, kind='erd')
    for summary in erd_summaries:
        try:
            erd_design = store.get_design(summary['id'])
            ddn_text = erd_design['version']['ddn_text']
            phys = _extract_physical_erd_model(ddn_text)
            blocks = _parse_blocks(ddn_text)
            defaults_by_id: dict[str, str] = {}
            for blk in blocks:
                if blk.get('kind') == 'element' and blk.get('role') == 'field':
                    dm = _DEFAULT_RE.search(blk.get('body') or '')
                    if dm:
                        defaults_by_id[blk['id']] = dm.group(1).replace(
                            '""', '"'
                        )
            fk_source_tables = {
                rel['source'] for rel in phys.get('relations', {}).values()
            }
            for tid, tbl in phys.get('tables', {}).items():
                tname = str(tbl.get('name') or '').strip()
                if not tname:
                    continue
                tkey = tname.lower()
                tshort = tkey.split('.')[-1]
                t_info = {
                    'catalog_type': 'TABLE',
                    'nullable': None,
                    'default_value': None,
                    'is_foreign_key': False,
                    'is_primary_key': False,
                }
                col_lookup[tkey] = t_info
                col_lookup[tshort] = t_info

                cols_list: list[dict[str, Any]] = []
                for fid, col in tbl.get('columns', {}).items():
                    cname = str(col.get('name') or '').strip()
                    if not cname:
                        continue
                    c_dtype = str(col.get('datatype') or 'TEXT').strip()
                    c_null = bool(col.get('nullable', True))
                    c_def = defaults_by_id.get(fid)
                    is_fk = (
                        tid in fk_source_tables
                        and cname.lower().endswith('_id')
                        and cname.lower() != 'id'
                    )
                    c_info = {
                        'name': cname,
                        'catalog_type': c_dtype,
                        'nullable': c_null,
                        'default_value': c_def,
                        'is_foreign_key': is_fk,
                        'is_primary_key': cname.lower() == 'id',
                    }
                    cols_list.append(c_info)
                    _index_ref_variants(
                        col_lookup, f'{tname}.{cname}', c_info
                    )
                if cols_list:
                    table_columns[tkey] = cols_list
                    table_columns[tshort] = cols_list
        except Exception:
            continue

    # 2. Overlay explicit catalog_metadata passed in request payload
    if isinstance(catalog_metadata, Mapping):
        raw_tables = catalog_metadata.get('tables')
        raw_cols = catalog_metadata.get('columns')
        if isinstance(raw_tables, list):
            for tbl in raw_tables:
                if not isinstance(tbl, Mapping):
                    continue
                tname = str(
                    tbl.get('name') or tbl.get('table') or ''
                ).strip()
                if not tname:
                    continue
                tkey = tname.lower()
                tshort = tkey.split('.')[-1]
                col_lookup[tkey] = {
                    'catalog_type': 'TABLE',
                    'nullable': None,
                    'default_value': None,
                    'is_foreign_key': False,
                    'is_primary_key': False,
                }
                col_lookup[tshort] = col_lookup[tkey]
                t_cols: list[dict[str, Any]] = []
                for c in tbl.get('columns') or []:
                    if not isinstance(c, Mapping):
                        continue
                    cname = str(c.get('name') or '').strip()
                    if not cname:
                        continue
                    norm = _normalize_catalog_entry(c)
                    norm['name'] = cname
                    t_cols.append(norm)
                    _index_ref_variants(col_lookup, f'{tname}.{cname}', norm)
                if t_cols:
                    table_columns[tkey] = t_cols
                    table_columns[tshort] = t_cols
        elif isinstance(raw_tables, Mapping):
            for tname, tval in raw_tables.items():
                if not isinstance(tval, Mapping):
                    continue
                tkey = str(tname).strip().lower()
                tshort = tkey.split('.')[-1]
                t_cols = []
                for c in tval.get('columns') or []:
                    if isinstance(c, Mapping) and c.get('name'):
                        norm = _normalize_catalog_entry(c)
                        norm['name'] = str(c['name']).strip()
                        t_cols.append(norm)
                        _index_ref_variants(
                            col_lookup, f'{tname}.{norm["name"]}', norm
                        )
                if t_cols:
                    table_columns[tkey] = t_cols
                    table_columns[tshort] = t_cols

        if isinstance(raw_cols, Mapping):
            for cref, cval in raw_cols.items():
                if isinstance(cval, Mapping):
                    _index_ref_variants(
                        col_lookup, str(cref), _normalize_catalog_entry(cval)
                    )
        elif isinstance(raw_cols, list):
            for cval in raw_cols:
                if isinstance(cval, Mapping):
                    cref = str(
                        cval.get('target_ref')
                        or cval.get('ref')
                        or cval.get('name')
                        or ''
                    )
                    if cref:
                        _index_ref_variants(
                            col_lookup, cref, _normalize_catalog_entry(cval)
                        )

        # Direct dict mapping {"sales.orders.id": {"datatype": "INTEGER", ...}}
        for k, v in catalog_metadata.items():
            if k in ('tables', 'columns'):
                continue
            if isinstance(v, Mapping):
                _index_ref_variants(
                    col_lookup, str(k), _normalize_catalog_entry(v)
                )
            elif isinstance(v, str):
                _index_ref_variants(
                    col_lookup,
                    str(k),
                    {
                        'catalog_type': v,
                        'nullable': None,
                        'default_value': None,
                        'is_foreign_key': False,
                        'is_primary_key': False,
                    },
                )

    return col_lookup, table_columns


# ---------------------------------------------------------------------------
# 1. Trace Screenshot Regions to Wireframe Mesh ("Trace as mesh", SR-F-030021)
# ---------------------------------------------------------------------------


def _infer_control_from_region(
    region: Mapping[str, Any],
    region_bindings: list[Mapping[str, Any]],
    has_click_nav: bool,
    explicit_hint: str,
    col_lookup: Mapping[str, dict[str, Any]],
    table_columns: Mapping[str, list[dict[str, Any]]],
) -> tuple[str, dict[str, Any]]:
    """Infer a ``wireframe.ui@1`` control role & attributes from a hotspot."""
    hint = (
        explicit_hint
        or str(region.get('kind_hint') or '').strip()
    ).lower()
    notes_lower = str(region.get('notes') or '').strip().lower()
    name = str(region.get('name') or 'Field').strip()
    name_lower = name.lower()
    name_tokens = set(re.findall(r'[a-z0-9]+', name_lower))

    primary_binding = region_bindings[0] if region_bindings else None
    target_kind = (
        str(primary_binding.get('target_kind') or '').lower()
        if primary_binding
        else ''
    )
    target_ref = (
        str(primary_binding.get('target_ref') or '').strip()
        if primary_binding
        else ''
    )
    ref_lower = target_ref.lower()
    leaf = ref_lower.split('.')[-1] if ref_lower else ''
    cat_info = col_lookup.get(ref_lower) or (
        col_lookup.get('.'.join(ref_lower.split('.')[-2:]))
        if ref_lower.count('.') >= 2
        else None
    )
    cat_type = str((cat_info or {}).get('catalog_type') or '').upper()
    is_fk = bool((cat_info or {}).get('is_foreign_key'))

    def _build_grid_columns() -> list[dict[str, Any]]:
        matched_cols = (
            table_columns.get(ref_lower)
            or table_columns.get(leaf)
            or []
        )
        if matched_cols:
            return [
                {
                    'id': _slug(c['name'].lower(), f'col_{idx}'),
                    'name': c['name'],
                    'width': 130,
                    'datatype': str(c.get('catalog_type') or 'text').lower(),
                }
                for idx, c in enumerate(matched_cols[:8], start=1)
            ]
        return [
            {'id': 'id', 'name': 'ID', 'width': 90, 'datatype': 'integer'},
            {'id': 'name', 'name': 'Name', 'width': 160, 'datatype': 'text'},
            {
                'id': 'status',
                'name': 'Status',
                'width': 120,
                'datatype': 'text',
            },
        ]

    # 1. Explicit hint override
    if hint:
        normalized_role = hint if hint.startswith('ui.') else f'ui.{hint}'
        if normalized_role in UI_CONTROL_ROLES:
            if normalized_role == 'ui.grid':
                return 'ui.grid', {'columns': _build_grid_columns()}
            if normalized_role == 'ui.tabs':
                return 'ui.tabs', {'options': ['Overview', 'Details']}
            if normalized_role in ('ui.dropdown', 'ui.radio'):
                return normalized_role, {'options': ['Option 1', 'Option 2']}
            return normalized_role, {}
        if hint in ('boolean', 'bool', 'flag', 'toggle'):
            return 'ui.checkbox', {'checked': False}
        if hint in ('select', 'enum', 'fk', 'foreign_key', 'lookup'):
            return 'ui.dropdown', {'options': [f'<{leaf or "option"}>']}
        if hint in ('table', 'collection', 'rows', 'plural'):
            return 'ui.grid', {'columns': _build_grid_columns()}
        if hint in ('action', 'submit', 'cta', 'command'):
            return 'ui.button', {}
        if hint in ('tab', 'tabbar', 'sections'):
            return 'ui.tabs', {'options': ['Overview', 'Details']}

    # 2. Tabs detection
    if 'tabs' in name_tokens or 'tab' in name_tokens or 'tabs' in notes_lower:
        return 'ui.tabs', {'options': ['General', 'Details', 'History']}

    # 3. Action / Submit button detection
    if (
        (name_tokens & _BUTTON_KEYWORDS and not primary_binding)
        or ('action' in notes_lower or 'submit' in notes_lower)
        or (has_click_nav and not primary_binding)
        or (
            name_lower.endswith(' button')
            or name_lower.startswith('btn ')
            or name_lower in ('save', 'submit', 'cancel', 'search', 'lookup')
        )
    ):
        return 'ui.button', {}

    # 4. Plural / Table / Grid detection
    is_plural_entity = (
        bool(leaf)
        and leaf.endswith('s')
        and not leaf.endswith(('status', 'address', 'notes', 'progress', 'alias'))
        and (target_kind == 'table' or ref_lower.count('.') <= 1)
    )
    if (
        target_kind in ('table', 'question', 'sql_query')
        or bool(name_tokens & _GRID_KEYWORDS)
        or is_plural_entity
    ):
        return 'ui.grid', {'columns': _build_grid_columns()}

    # 5. Boolean is_* / has_* / BOOL column detection
    check_token = leaf or _slug(name_lower, '')
    if (
        check_token.startswith(_BOOLEAN_PREFIXES)
        or check_token.endswith(_BOOLEAN_SUFFIXES)
        or 'BOOL' in cat_type
        or cat_type == 'TINYINT(1)'
    ):
        return 'ui.checkbox', {'checked': False}

    # 6. *_status / *_type / FK (*_id) / enum -> ui.dropdown
    is_fk_column = is_fk or (
        leaf.endswith('_id')
        and leaf != 'id'
        and not any(
            k in name_lower for k in ('number', '#', 'code')
        )
    )
    if (
        check_token.endswith(_DROPDOWN_SUFFIXES)
        or is_fk_column
        or 'ENUM' in cat_type
        or any(
            k in name_tokens
            for k in ('status', 'type', 'dropdown', 'select', 'category')
        )
    ):
        opts = (
            ['Draft', 'Active', 'Completed']
            if 'status' in check_token or 'status' in name_tokens
            else [f'<{leaf or "selection"}>']
        )
        return 'ui.dropdown', {'options': opts}

    # 7. Default to ui.input
    return 'ui.input', {'placeholder': f'Enter {name.lower()}'}


def trace_screenshot_regions_to_mesh(
    store: DesignStore,
    proc: StoreDDNProcess | None,
    *,
    design_id: str,
    actor_id: int,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert ``ui.region`` hotspots on a screenshot into a wireframe screen."""
    body = dict(payload or {})
    sync = ScreenMeshSync(store, proc)
    hydrated = sync.get_screen_mesh(design_id, version=body.get('version'))
    mesh = copy.deepcopy(hydrated['mesh'])
    project_id = hydrated['design']['project_id']

    requested_sid = str(
        body.get('source_screen_id') or body.get('screen_id') or ''
    ).strip()
    source_screen: dict[str, Any] | None = None
    if requested_sid:
        for scr in mesh['screens']:
            if scr['id'] == requested_sid:
                source_screen = scr
                break
        if source_screen is None:
            raise DesignStoreNotFound(
                f'Source screen {requested_sid!r} not found in Screen Mesh '
                f'{design_id!r}'
            )
    else:
        screen_ids_with_regions = {r['screen_id'] for r in mesh['regions']}
        for scr in mesh['screens']:
            if scr['id'] in screen_ids_with_regions:
                source_screen = scr
                break
        if source_screen is None and mesh['screens']:
            source_screen = mesh['screens'][0]

    if source_screen is None:
        raise DesignStoreError('Screen mesh contains no screens to trace')

    source_sid = source_screen['id']
    source_regions = [
        r for r in mesh['regions'] if r['screen_id'] == source_sid
    ]
    if not source_regions:
        raise DesignStoreError(
            f'Screen {source_screen["name"]!r} has no ui.region hotspots to '
            f'trace into a wireframe mesh'
        )

    col_lookup, table_columns = _collect_project_catalog_lookup(
        store, project_id, body.get('catalog_metadata')
    )
    region_hints = (
        dict(body.get('region_hints'))
        if isinstance(body.get('region_hints'), Mapping)
        else {}
    )

    traced_screen_id = uuid7()
    traced_title = (
        str(body.get('target_screen_title') or '').strip()
        or f'{source_screen["name"]} (Traced Mesh)'
    )
    mesh['screens'].append({
        'id': traced_screen_id,
        'name': traced_title,
        'width': int(source_screen.get('width') or 960),
        'height': int(source_screen.get('height') or 640),
        'form_reference': str(source_screen.get('form_reference') or ''),
        'screenshot_path': '',
        'screenshot_sha256': '',
        'notes': f'Traced from screenshot regions on {source_screen["name"]}',
    })

    bindings_by_source: dict[str, list[dict[str, Any]]] = {}
    for bnd in mesh['bindings']:
        bindings_by_source.setdefault(bnd['source_id'], []).append(bnd)

    navs_by_source: dict[str, list[dict[str, Any]]] = {}
    for nav in mesh['navigations']:
        navs_by_source.setdefault(nav['from_id'], []).append(nav)

    created_controls: list[dict[str, Any]] = []
    pinned_positions: dict[str, dict[str, float]] = {}
    bindings_preserved = 0

    for reg in source_regions:
        rid = reg['id']
        reg_bnds = bindings_by_source.get(rid, [])
        reg_navs = navs_by_source.get(rid, [])
        has_click_nav = any(n.get('trigger') == 'click' for n in reg_navs)
        explicit_hint = str(
            region_hints.get(rid) or region_hints.get(reg['name']) or ''
        )
        role, extra = _infer_control_from_region(
            reg,
            reg_bnds,
            has_click_nav,
            explicit_hint,
            col_lookup,
            table_columns,
        )
        bounds = {
            'x': round(float(reg['bounds']['x']), 2),
            'y': round(float(reg['bounds']['y']), 2),
            'width': round(float(reg['bounds']['width']), 2),
            'height': round(float(reg['bounds']['height']), 2),
        }
        new_cid = uuid7()
        ctrl_obj: dict[str, Any] = {
            'id': new_cid,
            'screen_id': traced_screen_id,
            'role': role,
            'name': reg['name'],
            'bounds': bounds,
            'notes': str(reg.get('notes') or ''),
            **extra,
        }
        mesh['controls'].append(ctrl_obj)
        created_controls.append(ctrl_obj)
        pinned_positions[new_cid] = {'x': bounds['x'], 'y': bounds['y']}

        grid_col_ids = {
            c['id'] for c in (ctrl_obj.get('columns') or [])
        }
        for bnd in reg_bnds:
            col_id = str(bnd.get('column_id') or '').strip()
            if col_id and (role != 'ui.grid' or col_id not in grid_col_ids):
                col_id = ''
            mesh['bindings'].append({
                'id': uuid7(),
                'source_id': new_cid,
                'column_id': col_id,
                'target_kind': bnd['target_kind'],
                'target_ref': bnd['target_ref'],
                'access_mode': bnd['access_mode'],
                'target_engine': bnd.get('target_engine'),
                'target_endpoint_id': bnd.get('target_endpoint_id'),
                'target_database_target_id': bnd.get(
                    'target_database_target_id'
                ),
                'notes': str(bnd.get('notes') or ''),
            })
            bindings_preserved += 1

        if body.get('copy_navigations', True):
            for nav in reg_navs:
                if nav['to_screen_id'] != source_sid:
                    mesh['navigations'].append({
                        'id': uuid7(),
                        'from_id': new_cid,
                        'to_screen_id': nav['to_screen_id'],
                        'trigger': nav['trigger'],
                        'action': nav['action'],
                        'delay_ms': int(nav.get('delay_ms') or 0),
                        'url': str(nav.get('url') or ''),
                        'label': str(nav.get('label') or ''),
                    })

    if body.get('link_navigation', False):
        mesh['navigations'].append({
            'id': uuid7(),
            'from_id': source_sid,
            'to_screen_id': traced_screen_id,
            'trigger': 'click',
            'action': 'navigate',
            'delay_ms': 0,
            'url': '',
            'label': str(body.get('navigation_label') or 'Traced Wireframe'),
        })

    expected_head = int(
        body.get('expected_head_version')
        or hydrated['design']['head_version']
    )
    saved = sync.save_screen_mesh(
        design_id,
        expected_head_version=expected_head,
        actor_id=actor_id,
        mesh=mesh,
        pinned_positions=pinned_positions,
        status='draft',
        note=str(
            body.get('note')
            or f'Traced {len(created_controls)} screenshot regions to mesh'
        ),
    )
    return {
        'design': saved['design'],
        'mesh': saved['mesh'],
        'assets': saved['assets'],
        'store_bindings': saved['store_bindings'],
        'suspect_binding_count': saved['suspect_binding_count'],
        'source_screen_id': source_sid,
        'traced_screen_id': traced_screen_id,
        'controls_created': len(created_controls),
        'bindings_preserved': bindings_preserved,
        'traced_controls': created_controls,
    }


# ---------------------------------------------------------------------------
# 2. Field Table Specification View & Exporter (SR-F-030022)
# ---------------------------------------------------------------------------


def _map_spec_access_mode(
    raw_access: str | None,
    element_kind: str,
    has_outgoing_nav: bool = False,
) -> str:
    if element_kind == 'navigation':
        return 'trigger'
    if raw_access:
        norm = raw_access.strip().lower()
        if norm in ('write', 'read_write'):
            return 'read_write'
        return 'read_only'
    if element_kind == 'ui.button' or has_outgoing_nav:
        return 'trigger'
    if element_kind in ('ui.frame', 'ui.label', 'ui.image', 'ui.tabs'):
        return 'read_only'
    return 'read_write'


def _format_nullable(val: bool | None) -> str:
    if val is True:
        return 'YES'
    if val is False:
        return 'NO'
    return '—'


def _render_spec_markdown(
    title: str,
    version: int,
    summary: Mapping[str, int],
    rows: list[Mapping[str, Any]],
) -> str:
    def _esc(val: Any) -> str:
        txt = '' if val is None else str(val)
        return txt.replace('|', '\\|').replace('\n', ' ')

    lines = [
        f'# Screen Mesh Field Specification: {title} (v{version})',
        '',
        (
            f'- **Total Elements**: {summary["total_fields"]}  '
            f'- **Bound**: {summary["bound_fields"]}  '
            f'- **Suspect**: {summary["suspect_fields"]}  '
            f'- **Unbound**: {summary["unbound_fields"]}'
        ),
        '',
        (
            '| Screen | Element / Label | Kind | Access | Target Reference | '
            'Catalog Type | Nullable | Default | Binding State | Notes |'
        ),
        '| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- | :---: | :--- |',
    ]
    for r in rows:
        lines.append(
            f'| {_esc(r["screen_title"])} '
            f'| {_esc(r["label"])} '
            f'| `{_esc(r["element_kind"])}` '
            f'| `{_esc(r["access_mode"])}` '
            f'| {_esc(r["target_ref"] or "—")} '
            f'| {_esc(r["catalog_type"] or "—")} '
            f'| {_format_nullable(r["nullable"])} '
            f'| {_esc(r["default_value"] if r["default_value"] is not None else "—")} '
            f'| `{_esc(r["binding_state"])}` '
            f'| {_esc(r["notes"])} |'
        )
    return '\n'.join(lines) + '\n'


def _render_spec_csv(rows: list[Mapping[str, Any]]) -> str:
    buf = io.StringIO()
    fieldnames = [
        'screen_title',
        'element_id',
        'element_kind',
        'label',
        'access_mode',
        'target_ref',
        'catalog_type',
        'nullable',
        'default_value',
        'binding_state',
        'notes',
    ]
    writer = csv.writer(buf, lineterminator='\n')
    writer.writerow(fieldnames)
    for r in rows:
        null_cell = (
            ''
            if r['nullable'] is None
            else ('true' if r['nullable'] else 'false')
        )
        writer.writerow([
            r['screen_title'],
            r['element_id'],
            r['element_kind'],
            r['label'],
            r['access_mode'],
            r['target_ref'],
            r['catalog_type'],
            null_cell,
            '' if r['default_value'] is None else r['default_value'],
            r['binding_state'],
            r['notes'],
        ])
    return buf.getvalue()


def _render_spec_html(
    title: str,
    version: int,
    summary: Mapping[str, int],
    rows: list[Mapping[str, Any]],
) -> str:
    esc = html.escape
    tr_chunks: list[str] = []
    for r in rows:
        default_txt = (
            '—'
            if r['default_value'] is None
            else esc(str(r['default_value']))
        )
        tr_chunks.append(
            '<tr>'
            f'<td>{esc(str(r["screen_title"]))}</td>'
            f'<td>{esc(str(r["label"]))}</td>'
            f'<td><code>{esc(str(r["element_kind"]))}</code></td>'
            f'<td><code>{esc(str(r["access_mode"]))}</code></td>'
            f'<td><code>{esc(str(r["target_ref"] or "—"))}</code></td>'
            f'<td>{esc(str(r["catalog_type"] or "—"))}</td>'
            f'<td>{_format_nullable(r["nullable"])}</td>'
            f'<td>{default_txt}</td>'
            f'<td data-state="{esc(str(r["binding_state"]))}">'
            f'{esc(str(r["binding_state"]))}</td>'
            f'<td>{esc(str(r["notes"] or ""))}</td>'
            '</tr>'
        )
    body_rows = '\n      '.join(tr_chunks)
    return (
        '<!doctype html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '  <meta charset="utf-8">\n'
        f'  <title>{esc(title)} (v{version}) — Field Specification</title>\n'
        '  <style>\n'
        '    body { font-family: system-ui, sans-serif; margin: 24px; color: #0f172a; }\n'
        '    table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 16px; }\n'
        '    th, td { border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; }\n'
        '    th { background: #f1f5f9; font-weight: 600; }\n'
        '    td[data-state="suspect"] { background: #fef3c7; color: #92400e; font-weight: 600; }\n'
        '    .summary { display: flex; gap: 16px; font-size: 13px; color: #334155; }\n'
        '  </style>\n'
        '</head>\n'
        '<body>\n'
        f'  <h1>{esc(title)} (v{version}) — Screen Mesh Field Specification</h1>\n'
        '  <div class="summary">\n'
        f'    <span>Total: <strong>{summary["total_fields"]}</strong></span>\n'
        f'    <span>Bound: <strong>{summary["bound_fields"]}</strong></span>\n'
        f'    <span>Suspect: <strong>{summary["suspect_fields"]}</strong></span>\n'
        f'    <span>Unbound: <strong>{summary["unbound_fields"]}</strong></span>\n'
        '  </div>\n'
        '  <table>\n'
        '    <thead>\n'
        '      <tr>'
        '<th>Screen</th><th>Label</th><th>Kind</th><th>Access</th>'
        '<th>Target Reference</th><th>Catalog Type</th><th>Nullable</th>'
        '<th>Default</th><th>Binding State</th><th>Notes</th>'
        '</tr>\n'
        '    </thead>\n'
        '    <tbody>\n'
        f'      {body_rows}\n'
        '    </tbody>\n'
        '  </table>\n'
        '</body>\n'
        '</html>\n'
    )


def build_screen_mesh_field_spec(
    store: DesignStore,
    proc: StoreDDNProcess | None,
    *,
    design_id: str,
    payload: Mapping[str, Any] | None = None,
    app: Any = None,
) -> dict[str, Any]:
    """Build joined Screen Mesh field specification table & export docs."""
    del app
    body = dict(payload or {})
    fmt = str(body.get('format') or 'json').strip().lower()
    if fmt not in ('json', 'markdown', 'csv', 'html', 'all'):
        raise DesignStoreError(
            f'Unsupported field specification format {fmt!r}; expected '
            f'json, markdown, csv or html'
        )

    sync = ScreenMeshSync(store, proc)
    hydrated = sync.get_screen_mesh(design_id, version=body.get('version'))
    design = hydrated['design']
    mesh = hydrated['mesh']
    project_id = design['project_id']
    version = int(design['version']['version'])

    col_lookup, _table_cols = _collect_project_catalog_lookup(
        store, project_id, body.get('catalog_metadata')
    )

    # Index authoritative store bindings by (element_id, store_kind, target_ref)
    store_by_tuple = {
        (b['element_id'], b['target_kind'], b['target_ref']): b
        for b in hydrated['store_bindings']
    }

    elem_bindings: dict[str, list[dict[str, Any]]] = {}
    col_bindings: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for bnd in mesh['bindings']:
        store_kind = _BINDING_TARGET_MAP[bnd['target_kind']][0]
        srow = store_by_tuple.get(
            (bnd['source_id'], store_kind, bnd['target_ref'])
        )
        enriched = {
            **bnd,
            'binding_state': (
                srow['state'] if srow else bnd.get('state') or 'unknown'
            ),
            'state_reason': (
                srow['state_reason']
                if srow
                else bnd.get('state_reason')
            ),
        }
        if bnd.get('column_id'):
            col_bindings.setdefault(
                (bnd['source_id'], bnd['column_id']), []
            ).append(enriched)
        else:
            elem_bindings.setdefault(bnd['source_id'], []).append(enriched)

    outgoing_nav_sources = {n['from_id'] for n in mesh['navigations']}
    screens_by_id = {s['id']: s for s in mesh['screens']}
    element_owner_screen: dict[str, str] = {}
    element_labels: dict[str, str] = {}
    for scr in mesh['screens']:
        element_owner_screen[scr['id']] = scr['id']
        element_labels[scr['id']] = scr['name']
    for ctrl in mesh['controls']:
        element_owner_screen[ctrl['id']] = ctrl['screen_id']
        element_labels[ctrl['id']] = ctrl['name']
    for reg in mesh['regions']:
        element_owner_screen[reg['id']] = reg['screen_id']
        element_labels[reg['id']] = reg['name']

    def _resolve_catalog(target_ref: str, fallback_type: str = '') -> dict[str, Any]:
        if not target_ref:
            return {
                'catalog_type': fallback_type,
                'nullable': None,
                'default_value': None,
            }
        key = target_ref.strip().lower()
        found = col_lookup.get(key)
        if found is None and key.count('.') >= 2:
            found = col_lookup.get('.'.join(key.split('.')[-2:]))
        if found is None:
            return {
                'catalog_type': fallback_type,
                'nullable': None,
                'default_value': None,
            }
        return {
            'catalog_type': str(found.get('catalog_type') or fallback_type),
            'nullable': found.get('nullable'),
            'default_value': found.get('default_value'),
        }

    def _emit_element_rows(
        out_rows: list[dict[str, Any]],
        *,
        screen_title: str,
        element_id: str,
        element_kind: str,
        label: str,
        bnds: list[dict[str, Any]],
        fallback_type: str = '',
        base_notes: str = '',
    ) -> None:
        has_nav = element_id in outgoing_nav_sources
        if not bnds:
            out_rows.append({
                'screen_title': screen_title,
                'element_id': element_id,
                'element_kind': element_kind,
                'label': label,
                'access_mode': _map_spec_access_mode(
                    None, element_kind, has_outgoing_nav=has_nav
                ),
                'target_ref': '',
                'catalog_type': fallback_type,
                'nullable': None,
                'default_value': None,
                'binding_state': 'unbound',
                'notes': base_notes,
            })
            return

        for bnd in bnds:
            tref = bnd['target_ref']
            cat = _resolve_catalog(tref, fallback_type=fallback_type)
            note_parts = [
                p
                for p in (
                    base_notes,
                    bnd.get('notes') or '',
                    bnd.get('state_reason') or '',
                )
                if p
            ]
            out_rows.append({
                'screen_title': screen_title,
                'element_id': element_id,
                'element_kind': element_kind,
                'label': label,
                'access_mode': _map_spec_access_mode(
                    bnd['access_mode'], element_kind, has_outgoing_nav=has_nav
                ),
                'target_ref': tref,
                'catalog_type': cat['catalog_type'],
                'nullable': cat['nullable'],
                'default_value': cat['default_value'],
                'binding_state': bnd['binding_state'],
                'notes': '; '.join(note_parts),
            })

    rows: list[dict[str, Any]] = []
    for scr in mesh['screens']:
        sid = scr['id']
        stitle = scr['name']
        scr_notes = (
            f"form_reference={scr['form_reference']}"
            if scr.get('form_reference')
            else str(scr.get('notes') or '')
        )
        _emit_element_rows(
            rows,
            screen_title=stitle,
            element_id=sid,
            element_kind='ui.frame',
            label=stitle,
            bnds=elem_bindings.get(sid, []),
            base_notes=scr_notes,
        )

        for ctrl in mesh['controls']:
            if ctrl['screen_id'] != sid:
                continue
            cid = ctrl['id']
            _emit_element_rows(
                rows,
                screen_title=stitle,
                element_id=cid,
                element_kind=ctrl['role'],
                label=ctrl['name'],
                bnds=elem_bindings.get(cid, []),
                base_notes=str(ctrl.get('notes') or ''),
            )
            if ctrl['role'] == 'ui.grid':
                parent_table_bnds = [
                    b
                    for b in elem_bindings.get(cid, [])
                    if b['target_kind'] == 'table'
                ]
                parent_table = (
                    parent_table_bnds[0]['target_ref']
                    if parent_table_bnds
                    else ''
                )
                for col in ctrl.get('columns') or []:
                    col_id = col['id']
                    cbnds = col_bindings.get((cid, col_id), [])
                    # Also infer catalog metadata if parent grid binds to table
                    inferred_ref = (
                        f'{parent_table}.{col_id}' if parent_table else ''
                    )
                    inferred_cat = _resolve_catalog(
                        inferred_ref, fallback_type=str(col.get('datatype') or '')
                    )
                    _emit_element_rows(
                        rows,
                        screen_title=stitle,
                        element_id=f'{cid}:{col_id}',
                        element_kind='ui.grid.column',
                        label=f'{ctrl["name"]}.{col["name"]}',
                        bnds=cbnds,
                        fallback_type=inferred_cat['catalog_type'],
                    )

        for reg in mesh['regions']:
            if reg['screen_id'] != sid:
                continue
            rid = reg['id']
            b = reg['bounds']
            geom_note = (
                f'bounds=({b["x"]}, {b["y"]}, {b["width"]}x{b["height"]})'
            )
            reg_note = (
                f'{geom_note}; {reg["notes"]}'
                if reg.get('notes')
                else geom_note
            )
            _emit_element_rows(
                rows,
                screen_title=stitle,
                element_id=rid,
                element_kind='ui.region',
                label=reg['name'],
                bnds=elem_bindings.get(rid, []),
                base_notes=reg_note,
            )

        for nav in mesh['navigations']:
            owner_sid = element_owner_screen.get(nav['from_id'], '')
            if owner_sid != sid:
                continue
            dest_scr = screens_by_id.get(nav['to_screen_id'])
            dest_ref = (
                nav['url']
                if nav['action'] == 'url' and nav.get('url')
                else (
                    f"screen:{dest_scr['name']}"
                    if dest_scr
                    else f"screen:{nav['to_screen_id']}"
                )
            )
            src_label = element_labels.get(nav['from_id'], nav['from_id'])
            rows.append({
                'screen_title': stitle,
                'element_id': nav['id'],
                'element_kind': 'navigation',
                'label': f'{src_label} -> {nav["label"]}',
                'access_mode': 'trigger',
                'target_ref': dest_ref,
                'catalog_type': f'{nav["trigger"]} -> {nav["action"]}',
                'nullable': None,
                'default_value': None,
                'binding_state': 'valid' if dest_scr else 'suspect',
                'notes': f'to_screen_id={nav["to_screen_id"]}',
            })

    total_fields = len(rows)
    bound_fields = sum(1 for r in rows if r['binding_state'] != 'unbound')
    suspect_fields = sum(1 for r in rows if r['binding_state'] == 'suspect')
    unbound_fields = total_fields - bound_fields
    summary = {
        'total_fields': total_fields,
        'bound_fields': bound_fields,
        'suspect_fields': suspect_fields,
        'unbound_fields': unbound_fields,
    }

    md_doc = _render_spec_markdown(mesh['name'], version, summary, rows)
    csv_doc = _render_spec_csv(rows)
    html_doc = _render_spec_html(mesh['name'], version, summary, rows)

    return {
        'design_id': design_id,
        'title': mesh['name'],
        'version': version,
        'format': fmt,
        'summary': summary,
        'rows': rows,
        'markdown': md_doc,
        'csv': csv_doc,
        'html': html_doc,
    }


# ---------------------------------------------------------------------------
# 3. Compare With Newer Screenshot (SR-F-030021)
# ---------------------------------------------------------------------------


def _decode_png_rgb_pure(png_bytes: bytes) -> tuple[int, int, bytearray]:
    """Decode an 8-bit non-interlaced PNG into a flat ``width*height*3`` RGB buffer."""
    if len(png_bytes) < 33 or png_bytes[:8] != _PNG_SIGNATURE:
        raise ValueError('Not a valid PNG byte stream')
    pos = 8
    width = height = bit_depth = color_type = interlace = 0
    plte: bytes | None = None
    idat_parts: list[bytes] = []
    while pos + 8 <= len(png_bytes):
        length = struct.unpack('>I', png_bytes[pos:pos + 4])[0]
        ctype = png_bytes[pos + 4:pos + 8]
        cstart = pos + 8
        cend = cstart + length
        if cend + 4 > len(png_bytes):
            break
        chunk = png_bytes[cstart:cend]
        pos = cend + 4
        if ctype == b'IHDR':
            width, height, bit_depth, color_type, _c, _f, interlace = (
                struct.unpack('>IIBBBBB', chunk)
            )
        elif ctype == b'PLTE':
            plte = chunk
        elif ctype == b'IDAT':
            idat_parts.append(chunk)
        elif ctype == b'IEND':
            break

    if width <= 0 or height <= 0 or interlace != 0 or bit_depth != 8:
        raise ValueError('Unsupported PNG encoding for pure-Python decode')
    channels_by_type = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    bpp = channels_by_type.get(color_type)
    if not bpp:
        raise ValueError(f'Unsupported PNG color_type {color_type}')
    stride = width * bpp
    raw = zlib.decompress(b''.join(idat_parts))

    out_rgb = bytearray(width * height * 3)
    prev = bytearray(stride)
    offset = 0
    for y in range(height):
        ftype = raw[offset]
        scan = bytearray(raw[offset + 1:offset + 1 + stride])
        offset += 1 + stride
        if ftype == 1:
            for i in range(bpp, stride):
                scan[i] = (scan[i] + scan[i - bpp]) & 255
        elif ftype == 2:
            for i in range(stride):
                scan[i] = (scan[i] + prev[i]) & 255
        elif ftype == 3:
            for i in range(stride):
                left = scan[i - bpp] if i >= bpp else 0
                scan[i] = (scan[i] + ((left + prev[i]) >> 1)) & 255
        elif ftype == 4:
            for i in range(stride):
                left = scan[i - bpp] if i >= bpp else 0
                up = prev[i]
                up_left = prev[i - bpp] if i >= bpp else 0
                scan[i] = (scan[i] + _paeth_predictor(left, up, up_left)) & 255
        prev = scan

        row_dst = y * width * 3
        if color_type == 2:
            out_rgb[row_dst:row_dst + width * 3] = scan
        elif color_type == 6:
            for x in range(width):
                out_rgb[row_dst + x * 3:row_dst + x * 3 + 3] = (
                    scan[x * 4:x * 4 + 3]
                )
        elif color_type in (0, 4):
            step = 2 if color_type == 4 else 1
            for x in range(width):
                g = scan[x * step]
                out_rgb[row_dst + x * 3:row_dst + x * 3 + 3] = bytes((g, g, g))
        elif color_type == 3 and plte:
            for x in range(width):
                pidx = scan[x] * 3
                if pidx + 3 <= len(plte):
                    out_rgb[row_dst + x * 3:row_dst + x * 3 + 3] = (
                        plte[pidx:pidx + 3]
                    )
    return width, height, out_rgb


def _extract_diff_boxes_from_rgb_buffers(
    old_w: int,
    old_h: int,
    old_rgb: bytes | bytearray,
    new_w: int,
    new_h: int,
    new_rgb: bytes | bytearray,
    *,
    channel_threshold: int = 8,
) -> tuple[float, list[dict[str, int]]]:
    """Compare two flat RGB buffers and return ``(changed_pixel_ratio, boxes)``."""
    canvas_w = max(old_w, new_w)
    canvas_h = max(old_h, new_h)
    overlap_w = min(old_w, new_w)
    overlap_h = min(old_h, new_h)

    cell = 8 if max(canvas_w, canvas_h) <= 320 else 16
    grid_w = max(1, (canvas_w + cell - 1) // cell)
    grid_h = max(1, (canvas_h + cell - 1) // cell)

    # Track exact min/max changed pixel bounds inside each grid cell
    cell_bounds: dict[tuple[int, int], list[int]] = {}
    changed_pixels = 0

    for y in range(overlap_h):
        old_row = y * old_w * 3
        new_row = y * new_w * 3
        if (
            old_rgb[old_row:old_row + overlap_w * 3]
            == new_rgb[new_row:new_row + overlap_w * 3]
        ):
            continue
        gy = y // cell
        for x in range(overlap_w):
            oi = old_row + x * 3
            ni = new_row + x * 3
            if (
                abs(old_rgb[oi] - new_rgb[ni]) > channel_threshold
                or abs(old_rgb[oi + 1] - new_rgb[ni + 1]) > channel_threshold
                or abs(old_rgb[oi + 2] - new_rgb[ni + 2]) > channel_threshold
            ):
                changed_pixels += 1
                gx = x // cell
                key = (gx, gy)
                cur = cell_bounds.get(key)
                if cur is None:
                    cell_bounds[key] = [x, y, x, y]
                else:
                    if x < cur[0]:
                        cur[0] = x
                    if y < cur[1]:
                        cur[1] = y
                    if x > cur[2]:
                        cur[2] = x
                    if y > cur[3]:
                        cur[3] = y

    # Account for non-overlapping area when screenshot dimensions changed
    extra_boxes: list[dict[str, int]] = []
    if canvas_w > overlap_w:
        extra_w = canvas_w - overlap_w
        changed_pixels += extra_w * canvas_h
        extra_boxes.append({
            'x': overlap_w,
            'y': 0,
            'width': extra_w,
            'height': canvas_h,
        })
    if canvas_h > overlap_h:
        extra_h = canvas_h - overlap_h
        changed_pixels += overlap_w * extra_h
        extra_boxes.append({
            'x': 0,
            'y': overlap_h,
            'width': overlap_w,
            'height': extra_h,
        })

    # Connected-component clustering over 8-neighbor changed cells
    visited: set[tuple[int, int]] = set()
    boxes: list[dict[str, int]] = []
    for start_cell in sorted(cell_bounds):
        if start_cell in visited:
            continue
        visited.add(start_cell)
        queue = deque([start_cell])
        min_x, min_y, max_x, max_y = cell_bounds[start_cell]
        while queue:
            cx, cy = queue.popleft()
            cb = cell_bounds[(cx, cy)]
            if cb[0] < min_x:
                min_x = cb[0]
            if cb[1] < min_y:
                min_y = cb[1]
            if cb[2] > max_x:
                max_x = cb[2]
            if cb[3] > max_y:
                max_y = cb[3]
            for ny in (cy - 1, cy, cy + 1):
                for nx in (cx - 1, cx, cx + 1):
                    nb = (nx, ny)
                    if (
                        0 <= nx < grid_w
                        and 0 <= ny < grid_h
                        and nb in cell_bounds
                        and nb not in visited
                    ):
                        visited.add(nb)
                        queue.append(nb)
        boxes.append({
            'x': int(min_x),
            'y': int(min_y),
            'width': int(max_x - min_x + 1),
            'height': int(max_y - min_y + 1),
        })

    boxes.extend(extra_boxes)
    total_pixels = max(1, canvas_w * canvas_h)
    ratio = round(min(1.0, changed_pixels / total_pixels), 6)
    return ratio, boxes


def _compare_image_bytes(
    old_bytes: bytes,
    old_media: str,
    new_bytes: bytes,
    new_media: str,
    *,
    force_pure_python: bool = False,
) -> dict[str, Any]:
    """Compare two screenshot images via Pillow or pure-Python fallback."""
    if _HAS_PIL and not force_pure_python:
        try:
            with _PILImage.open(io.BytesIO(old_bytes)) as im_old:
                rgb_old = im_old.convert('RGB')
                old_w, old_h = rgb_old.size
                old_buf = rgb_old.tobytes()
            with _PILImage.open(io.BytesIO(new_bytes)) as im_new:
                rgb_new = im_new.convert('RGB')
                new_w, new_h = rgb_new.size
                new_buf = rgb_new.tobytes()
                # Fast-path identical check via ImageChops
                if (old_w, old_h) == (new_w, new_h):
                    diff_bbox = _PILImageChops.difference(
                        _PILImage.frombytes('RGB', (old_w, old_h), old_buf),
                        rgb_new,
                    ).getbbox()
                    if diff_bbox is None:
                        return {
                            'old_dimensions': {
                                'width': old_w,
                                'height': old_h,
                            },
                            'new_dimensions': {
                                'width': new_w,
                                'height': new_h,
                            },
                            'dimension_changed': False,
                            'changed_pixel_ratio': 0.0,
                            'diff_bounding_boxes': [],
                        }
            ratio, boxes = _extract_diff_boxes_from_rgb_buffers(
                old_w, old_h, old_buf, new_w, new_h, new_buf
            )
            return {
                'old_dimensions': {'width': old_w, 'height': old_h},
                'new_dimensions': {'width': new_w, 'height': new_h},
                'dimension_changed': (old_w != new_w) or (old_h != new_h),
                'changed_pixel_ratio': ratio,
                'diff_bounding_boxes': boxes,
            }
        except Exception:
            pass

    # Pure-Python PNG scanline path
    if (
        old_bytes[:8] == _PNG_SIGNATURE
        and new_bytes[:8] == _PNG_SIGNATURE
    ):
        try:
            old_w, old_h, old_buf = _decode_png_rgb_pure(old_bytes)
            new_w, new_h, new_buf = _decode_png_rgb_pure(new_bytes)
            ratio, boxes = _extract_diff_boxes_from_rgb_buffers(
                old_w, old_h, old_buf, new_w, new_h, new_buf
            )
            return {
                'old_dimensions': {'width': old_w, 'height': old_h},
                'new_dimensions': {'width': new_w, 'height': new_h},
                'dimension_changed': (old_w != new_w) or (old_h != new_h),
                'changed_pixel_ratio': ratio,
                'diff_bounding_boxes': boxes,
            }
        except Exception:
            pass

    # Header + deterministic 8x8 byte-grid fallback for compressed WebP/JPEG
    old_dims = inspect_image_header(old_bytes, old_media)
    new_dims = inspect_image_header(new_bytes, new_media)
    old_w, old_h = old_dims['width'], old_dims['height']
    new_w, new_h = new_dims['width'], new_dims['height']
    dim_changed = (old_w != new_w) or (old_h != new_h)
    if old_bytes == new_bytes and not dim_changed:
        return {
            'old_dimensions': old_dims,
            'new_dimensions': new_dims,
            'dimension_changed': False,
            'changed_pixel_ratio': 0.0,
            'diff_bounding_boxes': [],
        }

    buckets = 64
    changed_buckets: list[int] = []
    for idx in range(buckets):
        s0 = (len(old_bytes) * idx) // buckets
        e0 = (len(old_bytes) * (idx + 1)) // buckets
        s1 = (len(new_bytes) * idx) // buckets
        e1 = (len(new_bytes) * (idx + 1)) // buckets
        if old_bytes[s0:e0] != new_bytes[s1:e1]:
            changed_buckets.append(idx)

    ratio = round(len(changed_buckets) / buckets, 6)
    boxes = []
    if changed_buckets:
        first_b, last_b = min(changed_buckets), max(changed_buckets)
        y0 = int((first_b // 8) * (new_h / 8))
        y1 = int(((last_b // 8) + 1) * (new_h / 8))
        boxes.append({
            'x': 0,
            'y': y0,
            'width': new_w,
            'height': max(1, y1 - y0),
        })
    return {
        'old_dimensions': old_dims,
        'new_dimensions': new_dims,
        'dimension_changed': dim_changed,
        'changed_pixel_ratio': ratio,
        'diff_bounding_boxes': boxes,
    }


def _box_overlap_ratio(
    region_bounds: Mapping[str, Any],
    diff_boxes: list[Mapping[str, int]],
) -> float:
    rx0 = float(region_bounds['x'])
    ry0 = float(region_bounds['y'])
    rw = float(region_bounds['width'])
    rh = float(region_bounds['height'])
    if rw <= 0 or rh <= 0 or not diff_boxes:
        return 0.0
    rx1 = rx0 + rw
    ry1 = ry0 + rh
    area = rw * rh

    # Exact scanline interval union over integer Y rows inside region bounds
    clipped: list[tuple[float, float, float, float]] = []
    for db in diff_boxes:
        dx0 = max(rx0, float(db['x']))
        dy0 = max(ry0, float(db['y']))
        dx1 = min(rx1, float(db['x'] + db['width']))
        dy1 = min(ry1, float(db['y'] + db['height']))
        if dx1 > dx0 and dy1 > dy0:
            clipped.append((dx0, dy0, dx1, dy1))
    if not clipped:
        return 0.0

    ys = sorted({v for box in clipped for v in (box[1], box[3])})
    union_area = 0.0
    for i in range(len(ys) - 1):
        ya, yb = ys[i], ys[i + 1]
        if yb <= ya:
            continue
        intervals = sorted(
            (b[0], b[2]) for b in clipped if b[1] <= ya and b[3] >= yb
        )
        if not intervals:
            continue
        cur_x0, cur_x1 = intervals[0]
        span_x = 0.0
        for ix0, ix1 in intervals[1:]:
            if ix0 <= cur_x1:
                cur_x1 = max(cur_x1, ix1)
            else:
                span_x += cur_x1 - cur_x0
                cur_x0, cur_x1 = ix0, ix1
        span_x += cur_x1 - cur_x0
        union_area += span_x * (yb - ya)

    return round(min(1.0, union_area / area), 4)


def compare_screen_mesh_screenshots(
    store: DesignStore,
    proc: StoreDDNProcess | None,
    *,
    design_id: str,
    actor_id: int,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare a screen's stored screenshot against a newer image capture."""
    body = dict(payload or {})
    sync = ScreenMeshSync(store, proc)
    current = sync.get_screen_mesh(design_id, version=body.get('version'))
    mesh = current['mesh']

    requested_sid = str(body.get('screen_id') or '').strip()
    target_scr: dict[str, Any] | None = None
    if requested_sid:
        for scr in mesh['screens']:
            if scr['id'] == requested_sid:
                target_scr = scr
                break
        if target_scr is None:
            raise DesignStoreNotFound(
                f'Screen {requested_sid!r} not found in Screen Mesh '
                f'{design_id!r}'
            )
    else:
        for scr in mesh['screens']:
            if scr.get('screenshot_sha256'):
                target_scr = scr
                break
        if target_scr is None and mesh['screens']:
            target_scr = mesh['screens'][0]

    if target_scr is None:
        raise DesignStoreError('Screen mesh has no screens')

    old_sha = str(target_scr.get('screenshot_sha256') or '').strip()
    if not old_sha:
        raise DesignStoreError(
            f'Screen {target_scr["name"]!r} has no attached baseline '
            f'screenshot to compare'
        )
    old_blob = store.get_blob(old_sha)
    raw_new_b64 = str(
        body.get('new_image_base64') or body.get('image_base64') or ''
    )
    new_bytes, new_media = _strip_data_url(
        raw_new_b64, str(body.get('media_type') or old_blob['media_type'])
    )
    inspect_image_header(new_bytes, new_media)

    diff = _compare_image_bytes(
        old_blob['bytes'],
        old_blob['media_type'],
        new_bytes,
        new_media,
        force_pure_python=bool(body.get('_force_pure_python', False)),
    )
    new_w = diff['new_dimensions']['width']
    new_h = diff['new_dimensions']['height']
    diff_boxes = diff['diff_bounding_boxes']

    affected_regions: list[dict[str, Any]] = []
    for reg in mesh['regions']:
        if reg['screen_id'] != target_scr['id']:
            continue
        b = reg['bounds']
        out_of_bounds = (
            float(b['x']) < 0
            or float(b['y']) < 0
            or float(b['x']) + float(b['width']) > new_w
            or float(b['y']) + float(b['height']) > new_h
        )
        overlap_ratio = _box_overlap_ratio(b, diff_boxes)
        needs_review = out_of_bounds or overlap_ratio >= 0.02
        affected_regions.append({
            'region_id': reg['id'],
            'name': reg['name'],
            'bounds': dict(b),
            'overlap_ratio': overlap_ratio,
            'out_of_bounds': bool(out_of_bounds),
            'recommendation': 'review_bounds' if needs_review else 'unchanged',
        })

    new_sha = hashlib.sha256(new_bytes).hexdigest()
    replaced = False
    out_design = current['design']
    out_mesh = current['mesh']
    if bool(body.get('replace_screenshot')):
        updated = sync.attach_screenshot(
            design_id,
            actor_id=actor_id,
            data=new_bytes,
            media_type=new_media,
            screen_id=target_scr['id'],
            note=str(
                body.get('note')
                or 'Replaced screenshot after visual comparison'
            ),
        )
        replaced = True
        out_design = updated['design']
        out_mesh = updated['mesh']

    return {
        'design': out_design,
        'mesh': out_mesh,
        'screen_id': target_scr['id'],
        'replaced': replaced,
        'old_sha256': old_sha,
        'new_sha256': new_sha,
        'old_dimensions': diff['old_dimensions'],
        'new_dimensions': diff['new_dimensions'],
        'dimension_changed': diff['dimension_changed'],
        'changed_pixel_ratio': diff['changed_pixel_ratio'],
        'diff_bounding_boxes': diff_boxes,
        'affected_regions': affected_regions,
    }
