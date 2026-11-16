##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""ScratchRobin Native Host Scene, Layout, Routing & Spatial Tile Engine.

Replaces the proof-of-concept client-side DDN runtime with ScratchRobin's own
host-calculated diagram, wireframe, cube, matrix, and BI chart/dashboard engine
designed for large, complex enterprise models:

1. Fast O(N) single-pass DDN block/view/annotation scanner + profile adapters.
2. Strict per-view selection filtering and 4-level ERD architectural swimlanes.
3. Exact card measurement (width, height, per-column port_y anchors) shared by
   both the host layout/router and the tiled vector renderer.
4. Cycle-safe Sugiyama longest-path ranking, 4-sweep barycenter crossing
   reduction, tall-layer sub-column wrapping, and 2D connected-component shelf
   packing with dynamic edge-density routing gutters.
5. Obstacle-avoiding field-port & lane-staggered orthogonal router (self-loops,
   forward lanes, corridor-routed back/long-span edges, Crow's-Foot & arrow
   markers, and collision-nudged label pills — never slicing through boxes or
   leaving mid-air stubs).
6. Spatial tile pyramid slicing (tile_size x tile_size) cached in an LRU cache
   plus standalone host SVG export.
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict
import hashlib
from html import escape as xml_escape
import json
import math
import re
import threading
from typing import Any, Mapping


CARD_HEADER_H = 38.0
CARD_ROW_H = 22.0
CARD_PAD_BOTTOM = 12.0
CARD_MAX_VISIBLE_FIELDS = 28
ROW_CORRIDOR_GAP = 84.0
BASE_COL_GUTTER = 176.0
LANE_SPACING = 14.0

LEVEL_PALETTE: dict[str, dict[str, str]] = {
    'conceptual': {
        'header_bg': '#fef3c7',
        'header_fg': '#78350f',
        'border': '#d97706',
        'badge_bg': '#fde68a',
        'badge_label': 'CONCEPTUAL',
    },
    'logical': {
        'header_bg': '#ccfbf1',
        'header_fg': '#115e59',
        'border': '#0d9488',
        'badge_bg': '#99f6e4',
        'badge_label': 'LOGICAL',
    },
    'physical': {
        'header_bg': '#dbeafe',
        'header_fg': '#1e3a8a',
        'border': '#2563eb',
        'badge_bg': '#bfdbfe',
        'badge_label': 'PHYSICAL',
    },
    'deployment': {
        'header_bg': '#dcfce7',
        'header_fg': '#14532d',
        'border': '#16a34a',
        'badge_bg': '#bbf7d0',
        'badge_label': 'DEPLOYMENT',
    },
    'cube_fact': {
        'header_bg': '#ede9fe',
        'header_fg': '#4c1d95',
        'border': '#7c3aed',
        'badge_bg': '#ddd6fe',
        'badge_label': 'FACT / GROUP',
    },
    'cube_dim': {
        'header_bg': '#e0f2fe',
        'header_fg': '#0c4a6e',
        'border': '#0284c7',
        'badge_bg': '#bae6fd',
        'badge_label': 'DIMENSION',
    },
}


class RobinSceneCache:
    """Thread-safe LRU cache of compiled host scenes keyed by (sha, view, tile_size)."""

    def __init__(self, max_entries: int = 192) -> None:
        self._max_entries = max(16, int(max_entries))
        self._entries: OrderedDict[tuple[str, str, int], dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, ddn_sha: str, view_id: str, tile_size: int) -> dict[str, Any] | None:
        key = (ddn_sha, view_id, tile_size)
        with self._lock:
            val = self._entries.get(key)
            if val is not None:
                self._entries.move_to_end(key)
                return val
            return None

    def put(
        self, ddn_sha: str, view_id: str, tile_size: int, scene: dict[str, Any]
    ) -> None:
        key = (ddn_sha, view_id, tile_size)
        with self._lock:
            self._entries[key] = scene
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


GLOBAL_ROBIN_SCENE_CACHE = RobinSceneCache()


_TOP_DECL_RE = re.compile(
    r'^(element|relation|view|data|erd)\s+"?((?:[^"\n]|"")+?)"?'
    r'(?:\s+as\s+"((?:[^"]|"")*)")?\s*$'
)
_KV_QUOTED_RE = re.compile(r'^([A-Za-z0-9_.]+)\s+"((?:[^"]|"")*)"\s*$')
_KV_BARE_RE = re.compile(r'^([A-Za-z0-9_.]+)\s+([^\s"].*?)\s*$')


def _unq(val: str) -> str:
    return val.replace('""', '"')


def fast_scan_ddn(ddn_text: str) -> dict[str, Any]:
    """Single-pass O(N) scanner for DDN declarations, views, members & x_records."""
    elements: dict[str, dict[str, Any]] = {}
    relations: dict[str, dict[str, Any]] = {}
    views: list[dict[str, Any]] = []
    annotations: dict[str, dict[str, str]] = {}
    module_hint = ''

    lines = ddn_text.splitlines()
    n = len(lines)
    i = 0

    while i < n:
        raw_line = lines[i]
        stripped = raw_line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith('//'):
            if 'ScratchRobin module:' in stripped or 'ScratchRobin mapping:' in stripped:
                module_hint = stripped.split(':', 1)[1].strip()
            i += 1
            continue
        if stripped.startswith('version '):
            i += 1
            continue

        top_m = _TOP_DECL_RE.match(raw_line)
        if not top_m:
            i += 1
            continue

        decl_kind = top_m.group(1)
        decl_id = _unq(top_m.group(2).strip())
        decl_role = _unq(top_m.group(3) or '') or decl_kind
        i += 1

        # Collect indented body lines belonging to this declaration
        body_lines: list[tuple[int, str]] = []
        while i < n:
            bline = lines[i]
            bstripped = bline.strip()
            if not bstripped:
                i += 1
                continue
            if not bline.startswith((' ', '\t')) and not bstripped.startswith('//'):
                break
            if not bstripped.startswith('//'):
                indent = len(bline) - len(bline.lstrip(' '))
                body_lines.append((indent, bstripped))
            i += 1

        # Shorthand `erd <id>` syntax (used in lightweight tests/snippets)
        if decl_kind == 'erd':
            shorthand_nodes: list[str] = []
            v_title = decl_id
            for ind, bstr in body_lines:
                if bstr == 'with' or bstr.startswith('id '):
                    continue
                qm = _KV_QUOTED_RE.match(bstr)
                if qm and qm.group(1) == 'title':
                    v_title = _unq(qm.group(2))
                    continue
                if ind <= 8 and re.match(r'^[A-Za-z_][A-Za-z0-9_ -]*$', bstr):
                    nid = f'{decl_id}:{bstr}'
                    elements[nid] = {
                        'id': nid,
                        'role': 'table',
                        'title': bstr,
                        'props': {'title': bstr},
                        'members': [],
                        'inline_rows': [],
                    }
                    shorthand_nodes.append(nid)
            views.append({
                'id': decl_id,
                'profile': 'ddn@1',
                'title': v_title,
                'include': shorthand_nodes,
                'include_empty': len(shorthand_nodes) == 0,
            })
            continue

        props: dict[str, str] = {}
        members: list[str] = []
        endpoints: list[str] = []
        include_ids: list[str] = []
        include_empty = False
        x_rec_fields: dict[str, str] = {}
        x_rec_meta: dict[str, str] = {}
        inline_rows: list[list[str]] = []
        ui_bounds: dict[str, float] = {}
        diagram_owner = ''

        ctx_stack: list[tuple[int, str]] = []
        current_row: list[str] | None = None

        for ind, bstr in body_lines:
            while ctx_stack and ind <= ctx_stack[-1][0]:
                popped = ctx_stack.pop()
                if popped[1] == 'row_item' and current_row is not None:
                    inline_rows.append(current_row)
                    current_row = None

            path_names = [c[1] for c in ctx_stack]

            if bstr in (
                'with', 'members', 'endpoints', 'selection', 'metadata',
                'x_record', 'record', 'x_ui', 'bounds', 'x_diagram',
                'data', 'columns', 'rows', 'definition',
            ):
                ctx_stack.append((ind, bstr))
                continue

            if bstr == 'include empty list':
                include_empty = True
                continue

            if bstr == 'include':
                ctx_stack.append((ind, 'include'))
                continue

            if bstr == 'item':
                if 'rows' in path_names and 'row_item' not in path_names:
                    current_row = []
                    ctx_stack.append((ind, 'row_item'))
                else:
                    ctx_stack.append((ind, 'item'))
                continue

            qm = _KV_QUOTED_RE.match(bstr)
            if qm:
                k, v = qm.group(1), _unq(qm.group(2))
            else:
                bm = _KV_BARE_RE.match(bstr)
                if bm:
                    k, v = bm.group(1), bm.group(2).strip('"')
                else:
                    continue

            if 'row_item' in path_names and k == 'item' and current_row is not None:
                current_row.append(v)
            elif 'record' in path_names and 'x_record' in path_names:
                x_rec_fields[k] = v
            elif 'x_record' in path_names:
                x_rec_meta[k] = v
            elif 'bounds' in path_names and k in ('x', 'y', 'width', 'height'):
                try:
                    ui_bounds[k] = float(v)
                except ValueError:
                    pass
            elif 'x_diagram' in path_names and k == 'owner':
                diagram_owner = v
            elif 'members' in path_names and k == 'id':
                members.append(v)
            elif 'endpoints' in path_names and k == 'id':
                endpoints.append(v)
            elif 'include' in path_names and k == 'id':
                include_ids.append(v)
            else:
                if k not in props:
                    props[k] = v

        while ctx_stack:
            popped = ctx_stack.pop()
            if popped[1] == 'row_item' and current_row is not None:
                inline_rows.append(current_row)
                current_row = None

        if decl_kind == 'element':
            if decl_role == 'record':
                subj = x_rec_fields.get('subject_id')
                if subj:
                    merged = dict(annotations.get(subj, {}))
                    merged.update(x_rec_meta)
                    merged.update(x_rec_fields)
                    annotations[subj] = merged
            else:
                elements[decl_id] = {
                    'id': decl_id,
                    'role': decl_role,
                    'title': props.get('title') or decl_id,
                    'props': props,
                    'members': members,
                    'inline_rows': inline_rows,
                    'ui_bounds': ui_bounds,
                    'owner': diagram_owner,
                }
        elif decl_kind == 'relation':
            relations[decl_id] = {
                'id': decl_id,
                'role': decl_role,
                'title': props.get('title') or decl_id,
                'props': props,
                'endpoints': endpoints,
            }
        elif decl_kind == 'view':
            views.append({
                'id': decl_id,
                'profile': decl_role,
                'title': props.get('title') or decl_id,
                'include': include_ids,
                'include_empty': include_empty,
            })

    return {
        'module_hint': module_hint,
        'elements': elements,
        'relations': relations,
        'views': views,
        'annotations': annotations,
    }


def _estimate_text_px(text: str, char_w: float = 7.1) -> float:
    return float(len(text or '')) * char_w


def _measure_entity_card(
    eid: str,
    elem: dict[str, Any],
    fields: list[dict[str, Any]],
    ann: dict[str, str],
) -> dict[str, Any]:
    """Compute exact card dimensions and per-field Y port anchors."""
    title = elem['title']
    role = elem['role']
    level = ann.get('modelling_level') or (
        'cube_fact' if role in ('cube', 'measure_group')
        else 'cube_dim' if role == 'dimension'
        else 'physical'
    )
    palette = LEVEL_PALETTE.get(level, LEVEL_PALETTE['physical'])

    visible_fields = fields[:CARD_MAX_VISIBLE_FIELDS]
    hidden_count = max(0, len(fields) - len(visible_fields))

    max_title_w = _estimate_text_px(title, 7.8) + 96.0
    max_row_w = 240.0
    measured_fields: list[dict[str, Any]] = []

    for idx, f in enumerate(visible_fields):
        port_y = CARD_HEADER_H + (idx + 0.5) * CARD_ROW_H
        fname = f['name']
        dtype = f.get('datatype') or ''
        row_w = _estimate_text_px(fname, 6.9) + _estimate_text_px(dtype, 6.2) + 68.0
        if row_w > max_row_w:
            max_row_w = row_w
        measured_fields.append({
            **f,
            'row_index': idx,
            'port_y': round(port_y, 2),
        })

    # Also support inline property/measure rows (e.g. Cube Star cards)
    if not measured_fields and elem.get('inline_rows'):
        for idx, r in enumerate(elem['inline_rows'][:16]):
            lbl = str(r[0]) if r else ''
            val = str(r[1]) if len(r) > 1 else ''
            port_y = CARD_HEADER_H + (idx + 0.5) * CARD_ROW_H
            row_w = _estimate_text_px(lbl, 6.9) + _estimate_text_px(val, 6.4) + 56.0
            if row_w > max_row_w:
                max_row_w = row_w
            measured_fields.append({
                'id': f'{eid}:row:{idx}',
                'name': lbl,
                'datatype': val,
                'nullable': True,
                'is_pk': False,
                'is_fk': False,
                'row_index': idx,
                'port_y': round(port_y, 2),
            })

    extra_rows = 1 if hidden_count > 0 else 0
    row_total = len(measured_fields) + extra_rows
    width = round(max(256.0, min(420.0, max(max_title_w, max_row_w))), 2)
    height = round(
        max(76.0, CARD_HEADER_H + row_total * CARD_ROW_H + CARD_PAD_BOTTOM), 2
    )
    return {
        'id': eid,
        'name': title,
        'role': role,
        'level': level,
        'palette': palette,
        'engine': ann.get('engine') or '',
        'host': ann.get('host') or '',
        'cloud_region': ann.get('cloud_region') or '',
        'width': width,
        'height': height,
        'member_count': len(fields),
        'hidden_field_count': hidden_count,
        'fields': measured_fields,
    }


def _place_layered_component_zone(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    pins: Mapping[str, Mapping[str, Any]],
    *,
    origin_x: float = 48.0,
    origin_y: float = 48.0,
    max_col_height: float = 1900.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, float]]:
    """Place a set of graph/ERD nodes with Sugiyama ranking, sub-column wrapping,
    shelf packing for disconnected islands, and obstacle-free orthogonal routing.
    """
    if not nodes:
        return [], [], {
            'min_x': origin_x,
            'min_y': origin_y,
            'max_x': origin_x + 400.0,
            'max_y': origin_y + 300.0,
        }

    node_by_id = {n['id']: n for n in nodes}
    ordered_ids = sorted(node_by_id, key=lambda nid: (node_by_id[nid]['name'], nid))

    outgoing: dict[str, list[str]] = {nid: [] for nid in ordered_ids}
    incoming: dict[str, list[str]] = {nid: [] for nid in ordered_ids}
    undirected: dict[str, set[str]] = {nid: set() for nid in ordered_ids}

    valid_edges: list[dict[str, Any]] = []
    for e in edges:
        s, t = e['source'], e['target']
        if s in node_by_id and t in node_by_id:
            valid_edges.append(e)
            if s != t:
                outgoing[s].append(t)
                incoming[t].append(s)
                undirected[s].add(t)
                undirected[t].add(s)

    # 1. Connected components (largest connected clusters first, singletons packed cleanly below/beside)
    visited: set[str] = set()
    components: list[list[str]] = []
    for nid in ordered_ids:
        if nid in visited:
            continue
        comp: list[str] = []
        queue = [nid]
        visited.add(nid)
        while queue:
            cur = queue.pop(0)
            comp.append(cur)
            for nb in sorted(undirected[cur]):
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
        comp.sort(key=lambda x: (node_by_id[x]['name'], x))
        components.append(comp)

    multi_comps = [c for c in components if len(c) > 1]
    multi_comps.sort(key=lambda c: (-len(c), node_by_id[c[0]]['name']))
    singletons = [c[0] for c in components if len(c) == 1]

    occupied_boxes: list[tuple[float, float, float, float]] = []
    placed_by_id: dict[str, dict[str, Any]] = {}
    col_assignment: dict[str, int] = {}

    def _box_hits(x: float, y: float, w: float, h: float, pad: float = 28.0) -> bool:
        for bx1, by1, bx2, by2 in occupied_boxes:
            if not (
                x + w + pad <= bx1
                or bx2 + pad <= x
                or y + h + pad <= oy1_val(by1)
                or by2 + pad <= y
            ):
                return True
        return False

    def oy1_val(v: float) -> float:
        return v

    # Honor explicitly pinned nodes first
    for nid in ordered_ids:
        pin = pins.get(nid)
        if pin and pin.get('pinned'):
            nd = node_by_id[nid]
            px, py = float(pin['x']), float(pin['y'])
            occupied_boxes.append((px, py, px + nd['width'], py + nd['height']))
            placed_by_id[nid] = {
                **nd,
                'layer': 0,
                'col_index': 0,
                'order': 0,
                'x': px,
                'y': py,
                'pinned': True,
            }

    cursor_zone_y = origin_y
    global_col_offset = 0

    for comp in multi_comps:
        comp_set = set(comp)
        layers: dict[str, int] = {}
        visiting: set[str] = set()

        def _rank(nid: str) -> int:
            if nid in layers:
                return layers[nid]
            if nid in visiting:
                return 0
            visiting.add(nid)
            preds = [p for p in incoming[nid] if p in comp_set]
            depth = 0 if not preds else max(_rank(p) + 1 for p in preds)
            visiting.remove(nid)
            layers[nid] = min(depth, max(0, len(comp) - 1))
            return layers[nid]

        for nid in comp:
            _rank(nid)

        by_layer: dict[int, list[str]] = defaultdict(list)
        for nid in comp:
            by_layer[layers[nid]].append(nid)

        sorted_l = sorted(by_layer)
        order_map: dict[str, int] = {}
        for li in sorted_l:
            for idx, nid in enumerate(by_layer[li]):
                order_map[nid] = idx

        # 4-sweep barycenter crossing minimization
        for _ in range(4):
            for li in sorted_l[1:]:
                by_layer[li].sort(
                    key=lambda nid: (
                        (
                            sum(order_map[p] for p in incoming[nid] if p in comp_set)
                            / max(1, len([p for p in incoming[nid] if p in comp_set]))
                        )
                        if any(p in comp_set for p in incoming[nid])
                        else float(order_map[nid]),
                        node_by_id[nid]['name'],
                    )
                )
                for idx, nid in enumerate(by_layer[li]):
                    order_map[nid] = idx
            for li in reversed(sorted_l[:-1]):
                by_layer[li].sort(
                    key=lambda nid: (
                        (
                            sum(order_map[s] for s in outgoing[nid] if s in comp_set)
                            / max(1, len([s for s in outgoing[nid] if s in comp_set]))
                        )
                        if any(s in comp_set for s in outgoing[nid])
                        else float(order_map[nid]),
                        node_by_id[nid]['name'],
                    )
                )
                for idx, nid in enumerate(by_layer[li]):
                    order_map[nid] = idx

        # Split overly tall layers into balanced visual sub-columns
        visual_cols: list[tuple[int, list[str]]] = []
        target_col_h = max(
            max_col_height,
            math.sqrt(sum(node_by_id[n]['height'] + ROW_CORRIDOR_GAP for n in comp) * 420.0),
        )
        for li in sorted_l:
            cur_bucket: list[str] = []
            cur_h = 0.0
            for nid in by_layer[li]:
                nh = node_by_id[nid]['height']
                if cur_bucket and (cur_h + nh > target_col_h) and len(cur_bucket) >= 5:
                    visual_cols.append((li, cur_bucket))
                    cur_bucket = [nid]
                    cur_h = nh + ROW_CORRIDOR_GAP
                else:
                    cur_bucket.append(nid)
                    cur_h += nh + ROW_CORRIDOR_GAP
            if cur_bucket:
                visual_cols.append((li, cur_bucket))

        # Count cross-column edge density to size horizontal routing gutters dynamically
        temp_col_of: dict[str, int] = {}
        for c_i, (_, bucket) in enumerate(visual_cols):
            for nid in bucket:
                temp_col_of[nid] = c_i

        gutter_edges: dict[int, int] = defaultdict(int)
        for e in valid_edges:
            if e['source'] in temp_col_of and e['target'] in temp_col_of:
                c1, c2 = temp_col_of[e['source']], temp_col_of[e['target']]
                lo, hi = min(c1, c2), max(c1, c2)
                for g in range(lo, max(lo + 1, hi)):
                    gutter_edges[g] += 1

        col_x = origin_x
        comp_max_y = cursor_zone_y
        for c_i, (logical_layer, bucket) in enumerate(visual_cols):
            col_w = max(node_by_id[nid]['width'] for nid in bucket)
            cy = cursor_zone_y
            for ord_i, nid in enumerate(bucket):
                col_assignment[nid] = global_col_offset + c_i
                if nid in placed_by_id:
                    placed_by_id[nid]['layer'] = logical_layer
                    placed_by_id[nid]['col_index'] = global_col_offset + c_i
                    comp_max_y = max(
                        comp_max_y,
                        placed_by_id[nid]['y'] + placed_by_id[nid]['height'],
                    )
                    continue
                nd = node_by_id[nid]
                nx = col_x
                ny = cy
                while _box_hits(nx, ny, nd['width'], nd['height']):
                    ny += ROW_CORRIDOR_GAP
                occupied_boxes.append((nx, ny, nx + nd['width'], ny + nd['height']))
                placed_by_id[nid] = {
                    **nd,
                    'layer': logical_layer,
                    'col_index': global_col_offset + c_i,
                    'order': ord_i,
                    'x': round(nx, 2),
                    'y': round(ny, 2),
                    'pinned': False,
                }
                cy = ny + nd['height'] + ROW_CORRIDOR_GAP
                comp_max_y = max(comp_max_y, ny + nd['height'])

            density = min(18, gutter_edges.get(c_i, 0))
            gutter_w = max(BASE_COL_GUTTER, 128.0 + density * LANE_SPACING)
            col_x += col_w + gutter_w

        global_col_offset += len(visual_cols)
        cursor_zone_y = comp_max_y + ROW_CORRIDOR_GAP * 1.5

    # Pack disconnected singleton tables in a clean multi-column shelf grid
    if singletons:
        shelf_cols = max(3, min(8, int(math.ceil(math.sqrt(len(singletons) * 1.4)))))
        col_widths = [0.0] * shelf_cols
        for idx, nid in enumerate(singletons):
            c = idx % shelf_cols
            col_widths[c] = max(col_widths[c], node_by_id[nid]['width'])
        col_xs = [origin_x]
        for c in range(1, shelf_cols):
            col_xs.append(col_xs[-1] + col_widths[c - 1] + 112.0)

        row_y = cursor_zone_y
        for row_start in range(0, len(singletons), shelf_cols):
            row_slice = singletons[row_start:row_start + shelf_cols]
            row_max_h = 0.0
            for c_idx, nid in enumerate(row_slice):
                if nid in placed_by_id:
                    continue
                nd = node_by_id[nid]
                nx = col_xs[c_idx]
                ny = row_y
                while _box_hits(nx, ny, nd['width'], nd['height']):
                    ny += ROW_CORRIDOR_GAP
                occupied_boxes.append((nx, ny, nx + nd['width'], ny + nd['height']))
                placed_by_id[nid] = {
                    **nd,
                    'layer': 0,
                    'col_index': global_col_offset + c_idx,
                    'order': row_start + c_idx,
                    'x': round(nx, 2),
                    'y': round(ny, 2),
                    'pinned': False,
                }
                row_max_h = max(row_max_h, nd['height'])
            row_y += row_max_h + ROW_CORRIDOR_GAP

    placed_nodes = sorted(
        placed_by_id.values(),
        key=lambda item: (item['layer'], item['order'], item['id']),
    )

    # 2. Obstacle-Avoiding Field-Port & Lane-Staggered Orthogonal Edge Router
    routed_edges = _route_orthogonal_edges(placed_nodes, valid_edges)

    all_min_x = min(n['x'] for n in placed_nodes)
    all_min_y = min(n['y'] for n in placed_nodes)
    all_max_x = max(n['x'] + n['width'] for n in placed_nodes)
    all_max_y = max(n['y'] + n['height'] for n in placed_nodes)
    for re_edge in routed_edges:
        eb = re_edge['bounds']
        all_min_x = min(all_min_x, eb['min_x'])
        all_min_y = min(all_min_y, eb['min_y'])
        all_max_x = max(all_max_x, eb['max_x'])
        all_max_y = max(all_max_y, eb['max_y'])

    return placed_nodes, routed_edges, {
        'min_x': round(all_min_x, 2),
        'min_y': round(all_min_y, 2),
        'max_x': round(all_max_x, 2),
        'max_y': round(all_max_y, 2),
    }


def _match_field_port_y(
    node: dict[str, Any], edge_title: str, *, is_source: bool
) -> float | None:
    """Match an FK edge title (e.g. 'CUSTOMER' or 'SALES_INVOICE.CUSTOMER -> ...')
    to the exact Y coordinate of that field row on ``node``.
    """
    fields = node.get('fields') or []
    if not fields:
        return None
    clean_title = (edge_title or '').strip().upper()
    if is_source:
        # Direct column name match or suffix match
        for f in fields:
            fn = f['name'].upper()
            if fn == clean_title or clean_title.endswith('.' + fn) or clean_title.endswith(':' + fn):
                return float(f['port_y'])
    else:
        # Target usually binds to PK ('DOC_NAME', 'ID', or first PK column)
        for f in fields:
            if f.get('is_pk'):
                return float(f['port_y'])
        if fields:
            return float(fields[0]['port_y'])
    return None


def _segment_hits_any_box(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    boxes: list[tuple[str, float, float, float, float]],
    ignore_ids: set[str],
    pad: float = 8.0,
) -> bool:
    lx, rx = min(x1, x2), max(x1, x2)
    ty, by = min(y1, y2), max(y1, y2)
    for bid, bx1, by1, bx2, by2 in boxes:
        if bid in ignore_ids:
            continue
        if not (
            rx < bx1 - pad
            or lx > bx2 + pad
            or by < by1 - pad
            or ty > by2 + pad
        ):
            return True
    return False


def _dedupe_collinear(pts: list[dict[str, float]]) -> list[dict[str, float]]:
    if len(pts) <= 2:
        return pts
    cleaned = [pts[0]]
    for pt in pts[1:]:
        if abs(pt['x'] - cleaned[-1]['x']) < 0.5 and abs(pt['y'] - cleaned[-1]['y']) < 0.5:
            continue
        cleaned.append(pt)
    if len(cleaned) <= 2:
        return cleaned
    out = [cleaned[0]]
    for idx in range(1, len(cleaned) - 1):
        prev_p = out[-1]
        cur_p = cleaned[idx]
        nxt_p = cleaned[idx + 1]
        same_x = abs(prev_p['x'] - cur_p['x']) < 0.5 and abs(cur_p['x'] - nxt_p['x']) < 0.5
        same_y = abs(prev_p['y'] - cur_p['y']) < 0.5 and abs(cur_p['y'] - nxt_p['y']) < 0.5
        if not (same_x or same_y):
            out.append(cur_p)
    out.append(cleaned[-1])
    return out


def _route_orthogonal_edges(
    placed_nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Route all edges as continuous obstacle-avoiding orthogonal polylines."""
    if not edges:
        return []

    by_id = {n['id']: n for n in placed_nodes}
    boxes = [
        (n['id'], n['x'], n['y'], n['x'] + n['width'], n['y'] + n['height'])
        for n in placed_nodes
    ]

    # Count side attachments so unmapped ports distribute evenly along the card border
    side_slots: dict[tuple[str, str], list[int]] = defaultdict(list)
    edge_sides: list[tuple[str, str]] = []
    for idx, e in enumerate(edges):
        sn = by_id[e['source']]
        tn = by_id[e['target']]
        if e['source'] == e['target']:
            s_side, t_side = 'right', 'top'
        elif sn['x'] + sn['width'] <= tn['x'] + 4.0:
            s_side, t_side = 'right', 'left'
        elif tn['x'] + tn['width'] <= sn['x'] + 4.0:
            s_side, t_side = 'left', 'right'
        else:
            # Same X column: exit & enter right gutter cleanly!
            s_side, t_side = 'right', 'right'
        edge_sides.append((s_side, t_side))
        side_slots[(e['source'], s_side)].append(idx)
        side_slots[(e['target'], t_side)].append(idx)

    # Track used vertical channel X coordinates and horizontal corridor Y coordinates
    used_lanes: list[float] = []
    used_corridors: list[float] = []
    used_labels: list[tuple[float, float, float, float]] = []

    def _find_clear_vertical_lane(
        port_x: float,
        port_y: float,
        target_y: float,
        owner_id: str,
        preferred_dir: float = 0.0,
    ) -> float:
        # Try 10px spacing first, then 4px fine lane spacing inside the immediate column gutter
        for pitch in (10.0, 4.0, 2.0):
            for attempt in range(1, 75):
                if preferred_dir != 0.0:
                    tx = round(port_x + preferred_dir * (12.0 + attempt * pitch), 1)
                else:
                    off = (attempt // 2) * pitch * (1 if attempt % 2 == 0 else -1)
                    tx = round(port_x + off, 1)
                if pitch >= 4.0 and any(abs(tx - ux) < pitch * 0.7 for ux in used_lanes):
                    continue
                # 1. Horizontal exit/entry stub from port_x -> tx at port_y must NOT cross any box!
                if _segment_hits_any_box(port_x, port_y, tx, port_y, boxes, {owner_id}, pad=3.0):
                    if preferred_dir != 0.0:
                        # Reached the far wall of the gutter; tighten pitch instead of jumping across next column!
                        break
                    continue
                # 2. Vertical run at tx from port_y -> target_y must NOT cross any box!
                if not _segment_hits_any_box(tx, port_y, tx, target_y, boxes, set(), pad=4.0):
                    used_lanes.append(tx)
                    return tx
        # Fallback right next to card border (guaranteed inside the 140px+ column gutter)
        fallback_x = round(port_x + (preferred_dir or 1.0) * 14.0, 1)
        used_lanes.append(fallback_x)
        return fallback_x

    def _find_clear_corridor(
        x1: float, x2: float, pref_y: float
    ) -> float:
        # Search outward from pref_y in 16px steps for a 100% unobstructed horizontal corridor
        for step_i in range(120):
            for sign in (1, -1) if step_i > 0 else (1,):
                cy = round(pref_y + sign * step_i * 16.0, 1)
                if any(abs(cy - uy) < 10.0 for uy in used_corridors):
                    continue
                if not _segment_hits_any_box(x1, cy, x2, cy, boxes, set(), pad=8.0):
                    used_corridors.append(cy)
                    return cy
        # Guaranteed unobstructed fallback: above all boxes intersecting [x1, x2]
        xlo, xhi = min(x1, x2) - 6.0, max(x1, x2) + 6.0
        blocking_min_y = min(
            (by1 for _bid, bx1, by1, bx2, _by2 in boxes if bx2 >= xlo and bx1 <= xhi),
            default=pref_y,
        )
        safe_y = round(blocking_min_y - 28.0 - (len(used_corridors) % 8) * 10.0, 1)
        used_corridors.append(safe_y)
        return safe_y

    routed: list[dict[str, Any]] = []

    for idx, e in enumerate(edges):
        sn = by_id[e['source']]
        tn = by_id[e['target']]
        s_side, t_side = edge_sides[idx]
        ignore = {sn['id'], tn['id']}

        # Source Y port
        matched_sy = _match_field_port_y(sn, e.get('title') or '', is_source=True)
        if matched_sy is not None:
            sy = sn['y'] + matched_sy
        else:
            peers = side_slots[(sn['id'], s_side)]
            slot_i = peers.index(idx)
            usable_h = max(24.0, sn['height'] - CARD_HEADER_H - 12.0)
            sy = sn['y'] + CARD_HEADER_H + usable_h * ((slot_i + 1) / (len(peers) + 1))

        # Target Y port
        matched_ty = _match_field_port_y(tn, e.get('title') or '', is_source=False)
        if matched_ty is not None:
            # Slightly stagger multiple incoming FKs around the PK row so arrowheads stay distinct
            t_peers = side_slots[(tn['id'], t_side)]
            t_slot = t_peers.index(idx)
            nudge = ((t_slot - (len(t_peers) - 1) / 2.0) * 6.0) if len(t_peers) > 1 else 0.0
            ty = min(
                tn['y'] + tn['height'] - 10.0,
                max(tn['y'] + 18.0, tn['y'] + matched_ty + nudge),
            )
        else:
            t_peers = side_slots[(tn['id'], t_side)]
            t_slot = t_peers.index(idx)
            usable_h = max(24.0, tn['height'] - CARD_HEADER_H - 12.0)
            ty = tn['y'] + CARD_HEADER_H + usable_h * ((t_slot + 1) / (len(t_peers) + 1))

        sx = sn['x'] + sn['width'] if s_side == 'right' else sn['x']
        tx = tn['x'] + tn['width'] if t_side == 'right' else tn['x']

        if sn['id'] == tn['id']:
            # Clean self-referencing loop outside top-right corner
            loop_y = sn['y'] - 22.0
            loop_x = _find_clear_vertical_lane(sx, sy, loop_y, sn['id'], preferred_dir=1.0)
            top_x = sn['x'] + sn['width'] - 34.0
            pts = [
                {'x': round(sx, 2), 'y': round(sy, 2)},
                {'x': round(loop_x, 2), 'y': round(sy, 2)},
                {'x': round(loop_x, 2), 'y': round(loop_y, 2)},
                {'x': round(top_x, 2), 'y': round(loop_y, 2)},
                {'x': round(top_x, 2), 'y': round(sn['y'], 2)},
            ]
        elif s_side == 'right' and t_side == 'right':
            # Same-column tables: step out past the widest card between sy and ty into right gutter!
            ylo, yhi = min(sy, ty) - 6.0, max(sy, ty) + 6.0
            col_max_right = max(
                (
                    bx2 for _bid, bx1, by1, bx2, by2 in boxes
                    if by2 >= ylo and by1 <= yhi and abs(bx1 - sn['x']) < 60.0
                ),
                default=max(sx, tx),
            )
            gutter_x = _find_clear_vertical_lane(col_max_right, sy, ty, sn['id'], preferred_dir=1.0)
            pts = [
                {'x': round(sx, 2), 'y': round(sy, 2)},
                {'x': round(gutter_x, 2), 'y': round(sy, 2)},
                {'x': round(gutter_x, 2), 'y': round(ty, 2)},
                {'x': round(tx, 2), 'y': round(ty, 2)},
            ]
        else:
            # Forward (right -> left) or backward (left -> right) between distinct columns
            ideal_mid_x = (sx + tx) / 2.0
            lane_x = _find_clear_vertical_lane(ideal_mid_x, sy, ty, sn['id'], preferred_dir=0.0)
            direct_ok = (
                not _segment_hits_any_box(sx, sy, lane_x, sy, boxes, {sn['id']}, pad=3.0)
                and not _segment_hits_any_box(lane_x, sy, lane_x, ty, boxes, set(), pad=4.0)
                and not _segment_hits_any_box(lane_x, ty, tx, ty, boxes, {tn['id']}, pad=3.0)
            )
            if direct_ok:
                pts = [
                    {'x': round(sx, 2), 'y': round(sy, 2)},
                    {'x': round(lane_x, 2), 'y': round(sy, 2)},
                    {'x': round(lane_x, 2), 'y': round(ty, 2)},
                    {'x': round(tx, 2), 'y': round(ty, 2)},
                ]
            else:
                # Route via unobstructed vertical gutter stub -> clear horizontal corridor -> target stub!
                s_dir = 1.0 if s_side == 'right' else -1.0
                t_dir = 1.0 if t_side == 'right' else -1.0
                pref_corr_y = (
                    min(sn['y'], tn['y']) - 28.0
                    if abs(sy - min(sn['y'], tn['y'])) <= abs(sy - max(sn['y'] + sn['height'], tn['y'] + tn['height']))
                    else max(sn['y'] + sn['height'], tn['y'] + tn['height']) + 28.0
                )
                stub_sx = _find_clear_vertical_lane(sx, sy, pref_corr_y, sn['id'], preferred_dir=s_dir)
                stub_tx = _find_clear_vertical_lane(tx, ty, pref_corr_y, tn['id'], preferred_dir=t_dir)
                corr_y = _find_clear_corridor(stub_sx, stub_tx, pref_corr_y)
                if _segment_hits_any_box(stub_sx, sy, stub_sx, corr_y, boxes, set(), pad=4.0):
                    stub_sx = _find_clear_vertical_lane(sx, sy, corr_y, sn['id'], preferred_dir=s_dir)
                if _segment_hits_any_box(stub_tx, ty, stub_tx, corr_y, boxes, set(), pad=4.0):
                    stub_tx = _find_clear_vertical_lane(tx, ty, corr_y, tn['id'], preferred_dir=t_dir)
                pts = [
                    {'x': round(sx, 2), 'y': round(sy, 2)},
                    {'x': round(stub_sx, 2), 'y': round(sy, 2)},
                    {'x': round(stub_sx, 2), 'y': round(corr_y, 2)},
                    {'x': round(stub_tx, 2), 'y': round(corr_y, 2)},
                    {'x': round(stub_tx, 2), 'y': round(ty, 2)},
                    {'x': round(tx, 2), 'y': round(ty, 2)},
                ]

        pts = _dedupe_collinear(pts)

        # Place label pill on the longest segment and nudge if overlapping another pill
        raw_lbl = str(e.get('title') or '').strip()
        if len(raw_lbl) > 28:
            raw_lbl = raw_lbl[:26] + '…'
        best_seg_len = -1.0
        lx, ly = pts[0]['x'], pts[0]['y']
        for p1, p2 in zip(pts, pts[1:]):
            slen = math.hypot(p2['x'] - p1['x'], p2['y'] - p1['y'])
            if slen > best_seg_len:
                best_seg_len = slen
                lx = (p1['x'] + p2['x']) / 2.0
                ly = (p1['y'] + p2['y']) / 2.0

        pill_w = max(44.0, len(raw_lbl) * 6.2 + 14.0) if raw_lbl else 0.0
        pill_h = 18.0
        if raw_lbl:
            for _ in range(12):
                hit = any(
                    not (
                        lx + pill_w / 2 < ux1
                        or lx - pill_w / 2 > ux2
                        or ly + pill_h / 2 < uy1
                        or ly - pill_h / 2 > uy2
                    )
                    for ux1, uy1, ux2, uy2 in used_labels
                )
                if not hit:
                    break
                ly += 19.0
            used_labels.append((
                lx - pill_w / 2,
                ly - pill_h / 2,
                lx + pill_w / 2,
                ly + pill_h / 2,
            ))

        link_kind = e.get('link_kind') or 'fk'
        is_trace = link_kind in ('traces_to', 'refines', 'implements', 'hosts', 'inactive_role')
        routed.append({
            'id': e['id'],
            'title': e.get('title') or '',
            'display_label': raw_lbl,
            'source': e['source'],
            'target': e['target'],
            'link_kind': link_kind,
            'dashed': is_trace,
            'source_mark': 'none' if is_trace else 'many',
            'target_mark': 'arrow' if is_trace else 'one',
            'points': pts,
            'label_pos': {'x': round(lx, 2), 'y': round(ly, 2), 'w': round(pill_w, 1)},
            'bounds': {
                'min_x': min(p['x'] for p in pts) - 20.0,
                'min_y': min(p['y'] for p in pts) - 20.0,
                'max_x': max(p['x'] for p in pts) + 20.0,
                'max_y': max(p['y'] for p in pts) + 20.0,
            },
        })

    return routed


def _slice_scene_into_tiles(
    ddn_sha: str,
    view_id: str,
    tile_size: int,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    zones: list[dict[str, Any]],
    widgets: list[dict[str, Any]],
    canvas_bounds: dict[str, float],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Slice all positioned nodes, edges, zones, and widgets into spatial tiles."""
    min_tx = int(math.floor(canvas_bounds['min_x'] / tile_size))
    max_tx = int(math.floor(canvas_bounds['max_x'] / tile_size))
    min_ty = int(math.floor(canvas_bounds['min_y'] / tile_size))
    max_ty = int(math.floor(canvas_bounds['max_y'] / tile_size))

    manifest_tiles: list[dict[str, Any]] = []
    tiles_by_coord: dict[str, dict[str, Any]] = {}

    for ty in range(min_ty, max_ty + 1):
        for tx in range(min_tx, max_tx + 1):
            bx1 = float(tx * tile_size)
            by1 = float(ty * tile_size)
            bx2 = float((tx + 1) * tile_size)
            by2 = float((ty + 1) * tile_size)

            t_nodes = [
                n for n in nodes
                if not (
                    n['x'] + n['width'] < bx1
                    or n['x'] > bx2
                    or n['y'] + n['height'] < by1
                    or n['y'] > by2
                )
            ]
            t_edges = [
                e for e in edges
                if not (
                    e['bounds']['max_x'] < bx1
                    or e['bounds']['min_x'] > bx2
                    or e['bounds']['max_y'] < by1
                    or e['bounds']['min_y'] > by2
                )
            ]
            t_zones = [
                z for z in zones
                if not (
                    z['x'] + z['width'] < bx1
                    or z['x'] > bx2
                    or z['y'] + z['height'] < by1
                    or z['y'] > by2
                )
            ]
            t_widgets = [
                w for w in widgets
                if not (
                    w['x'] + w['width'] < bx1
                    or w['x'] > bx2
                    or w['y'] + w['height'] < by1
                    or w['y'] > by2
                )
            ]
            if t_nodes or t_edges or t_zones or t_widgets or (tx == min_tx and ty == min_ty):
                coord_key = f'{tx}:{ty}'
                tile_hash = hashlib.sha256(
                    f'{ddn_sha}:{view_id}:{tile_size}:{coord_key}'.encode('utf-8')
                ).hexdigest()[:20]
                tile_meta = {
                    'tx': tx,
                    'ty': ty,
                    'coord': coord_key,
                    'tile_key': tile_hash,
                    'bounds': {
                        'min_x': bx1,
                        'min_y': by1,
                        'max_x': bx2,
                        'max_y': by2,
                    },
                    'node_ids': [n['id'] for n in t_nodes],
                    'edge_ids': [e['id'] for e in t_edges],
                    'node_count': len(t_nodes),
                    'edge_count': len(t_edges),
                }
                manifest_tiles.append(tile_meta)
                tiles_by_coord[coord_key] = {
                    **tile_meta,
                    'nodes': t_nodes,
                    'edges': t_edges,
                    'zones': t_zones,
                    'widgets': t_widgets,
                }

    return manifest_tiles, tiles_by_coord


def _compile_bi_scene_widgets(
    ddn_text: str, module_hint: str
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Compile BI Question or Composed BI Dashboard into native positioned widgets."""
    from .bi_ddn import ddn_to_dashboard, ddn_to_question

    if 'bi.question' in module_hint:
        parsed = ddn_to_question(ddn_text)
        q = parsed.get('question', parsed)
        vis_type = (q.get('visualization') or {}).get('type') or 'bar'
        rows = q.get('preview_rows') or []
        views = [{'id': 'question_main', 'profile': f'chart.{vis_type}@1', 'title': q.get('name') or 'Question'}]
        widgets = [{
            'id': 'bi-question-card',
            'widget_kind': 'bi_card',
            'card_type': 'question',
            'chart_type': vis_type,
            'title': q.get('name') or 'BI Question',
            'subtitle': q.get('raw_sql') or '',
            'rows': rows[:24],
            'x': 48.0,
            'y': 48.0,
            'width': 880.0,
            'height': 500.0,
        }]
        return 'question_main', views, widgets

    parsed = ddn_to_dashboard(ddn_text)
    dash = parsed.get('dashboard', parsed)
    tabs = dash.get('tabs') or [{'id': 'main', 'name': 'Overview'}]
    views = [
        {
            'id': f"tab_{t['id']}",
            'profile': 'panels.composed@1',
            'title': f"{dash.get('name') or 'Dashboard'} — {t['name']}",
            'tab_id': t['id'],
        }
        for t in tabs
    ]
    views.insert(0, {
        'id': 'dashboard_composed',
        'profile': 'panels.composed@1',
        'title': dash.get('name') or 'Composed Dashboard',
        'tab_id': None,
    })

    widgets: list[dict[str, Any]] = []
    col_unit_w = 48.0
    row_unit_h = 42.0
    tab_offsets: dict[str, float] = {}
    cur_tab_y = 48.0
    for t in tabs:
        tab_offsets[t['id']] = cur_tab_y
        t_cards = [c for c in dash.get('cards', ()) if c.get('tab_id') == t['id']]
        max_bottom = max(
            ((c['layout']['y'] + c['layout']['h']) * row_unit_h for c in t_cards),
            default=320.0,
        )
        cur_tab_y += max_bottom + 72.0

    for c in dash.get('cards', ()):
        lay = c.get('layout') or {'x': 0, 'y': 0, 'w': 12, 'h': 8}
        tid = c.get('tab_id') or tabs[0]['id']
        wx = 48.0 + float(lay.get('x', 0)) * col_unit_w
        wy = tab_offsets.get(tid, 48.0) + float(lay.get('y', 0)) * row_unit_h
        ww = max(220.0, float(lay.get('w', 12)) * col_unit_w - 16.0)
        wh = max(110.0, float(lay.get('h', 8)) * row_unit_h - 14.0)
        ctype = c.get('type') or 'question'
        widgets.append({
            'id': c['id'],
            'tab_id': tid,
            'widget_kind': 'bi_card',
            'card_type': ctype,
            'chart_type': (c.get('visualization') or {}).get('type', 'bar'),
            'title': c.get('title') or c['id'],
            'markdown': (c.get('text') or {}).get('markdown', ''),
            'rows': (
                c.get('preview_rows')
                or (c.get('metric_panel') or {}).get('rows')
                or []
            )[:24],
            'columns': (c.get('metric_panel') or {}).get('columns') or [],
            'x': round(wx, 2),
            'y': round(wy, 2),
            'width': round(ww, 2),
            'height': round(wh, 2),
        })
    return 'dashboard_composed', views, widgets


def _compile_screen_mesh_scene(
    ddn_text: str, view_id: str | None
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Compile Screen Mesh wireframes & Screen Flow into positioned host primitives."""
    from .screen_mesh_ddn import ddn_to_screen_mesh

    parsed = ddn_to_screen_mesh(ddn_text)
    mesh = parsed.get('mesh', parsed)
    screens = mesh.get('screens') or []
    controls = mesh.get('controls') or []
    regions = mesh.get('regions') or []
    bindings = mesh.get('bindings') or []
    navs = mesh.get('navigations') or []

    views = [
        {'id': 'screen_mesh', 'profile': 'wireframe.ui@1', 'title': f"{mesh.get('name') or 'Screen Mesh'} (Wireframes)"},
        {'id': 'screen_flow', 'profile': 'wireframe.ui@1', 'title': f"{mesh.get('name') or 'Screen Mesh'} (Navigation Flow)"},
    ]
    sel_view = view_id if view_id in ('screen_mesh', 'screen_flow') else 'screen_mesh'

    bind_by_src = {b.get('source_id'): b.get('target_ref') for b in bindings if b.get('source_id')}

    if sel_view == 'screen_flow':
        flow_nodes = []
        for idx, scr in enumerate(screens):
            ctrl_cnt = sum(1 for c in controls if c.get('screen_id') == scr['id'])
            flow_nodes.append({
                'id': scr['id'],
                'name': scr.get('name') or scr['id'],
                'role': 'ui.frame',
                'level': 'logical',
                'palette': LEVEL_PALETTE['logical'],
                'engine': scr.get('form_reference') or 'wireframe',
                'host': '',
                'cloud_region': '',
                'width': 290.0,
                'height': 108.0,
                'member_count': ctrl_cnt,
                'hidden_field_count': 0,
                'fields': [
                    {
                        'id': f"{scr['id']}:size",
                        'name': 'Canvas',
                        'datatype': f"{scr.get('width', 960)}×{scr.get('height', 640)}",
                        'nullable': False,
                        'is_pk': False,
                        'is_fk': False,
                        'row_index': 0,
                        'port_y': 49.0,
                    },
                    {
                        'id': f"{scr['id']}:ctrls",
                        'name': 'Controls',
                        'datatype': str(ctrl_cnt),
                        'nullable': False,
                        'is_pk': False,
                        'is_fk': False,
                        'row_index': 1,
                        'port_y': 71.0,
                    },
                ],
            })
        ctrl_to_scr = {c['id']: c.get('screen_id') for c in controls}
        for r in regions:
            ctrl_to_scr[r['id']] = r.get('screen_id')
        flow_edges = []
        for idx, nv in enumerate(navs):
            raw_from = nv.get('from_id') or nv.get('source_id')
            src_scr = ctrl_to_scr.get(raw_from, raw_from)
            tgt_scr = nv.get('to_screen_id') or nv.get('target_screen_id')
            if src_scr and tgt_scr:
                flow_edges.append({
                    'id': nv.get('id') or f'nav-{idx}',
                    'source': src_scr,
                    'target': tgt_scr,
                    'title': f"{nv.get('trigger', 'click')} → {nv.get('action', 'open')}",
                    'link_kind': 'navigation',
                })
        placed, routed, _ = _place_layered_component_zone(flow_nodes, flow_edges, {})
        return sel_view, views, placed, routed, []

    # Full interactive wireframe layout: place screens cleanly in a 2-column / horizontal strip
    widgets: list[dict[str, Any]] = []
    scr_pos: dict[str, tuple[float, float, float, float]] = {}
    cur_x = 56.0
    cur_y = 56.0
    row_h = 0.0
    for idx, scr in enumerate(screens):
        sw = float(scr.get('width') or 960.0)
        sh = float(scr.get('height') or 620.0)
        if idx > 0 and idx % 2 == 0:
            cur_x = 56.0
            cur_y += row_h + 120.0
            row_h = 0.0
        scr_ctrls = [
            {
                **c,
                'binding_ref': bind_by_src.get(c['id']) or '',
            }
            for c in controls
            if c.get('screen_id') == scr['id']
        ]
        scr_regs = [
            {
                **r,
                'binding_ref': bind_by_src.get(r['id']) or '',
            }
            for r in regions
            if r.get('screen_id') == scr['id']
        ]
        widgets.append({
            'id': scr['id'],
            'widget_kind': 'screen_frame',
            'title': scr.get('name') or scr['id'],
            'form_reference': scr.get('form_reference') or '',
            'notes': scr.get('notes') or '',
            'x': round(cur_x, 2),
            'y': round(cur_y, 2),
            'width': round(sw, 2),
            'height': round(sh, 2),
            'controls': scr_ctrls,
            'regions': scr_regs,
        })
        scr_pos[scr['id']] = (cur_x, cur_y, sw, sh)
        cur_x += sw + 136.0
        row_h = max(row_h, sh)

    # Route navigation arrows cleanly between screen frames
    ctrl_to_scr = {c['id']: c.get('screen_id') for c in controls}
    for r in regions:
        ctrl_to_scr[r['id']] = r.get('screen_id')
    pseudo_nodes = [
        {
            'id': sid,
            'name': sid,
            'x': bx,
            'y': by,
            'width': bw,
            'height': bh,
            'fields': [],
        }
        for sid, (bx, by, bw, bh) in scr_pos.items()
    ]
    raw_nav_edges = []
    for idx, nv in enumerate(navs):
        raw_from = nv.get('from_id') or nv.get('source_id')
        s_scr = ctrl_to_scr.get(raw_from, raw_from)
        t_scr = nv.get('to_screen_id') or nv.get('target_screen_id')
        if s_scr in scr_pos and t_scr in scr_pos:
            raw_nav_edges.append({
                'id': nv.get('id') or f'nav-{idx}',
                'source': s_scr,
                'target': t_scr,
                'title': f"{nv.get('trigger', 'click')}: {nv.get('action', 'open')}",
                'link_kind': 'traces_to',
            })
    routed_navs = _route_orthogonal_edges(pseudo_nodes, raw_nav_edges)
    return sel_view, views, [], routed_navs, widgets


def _compile_cube_matrix_or_grid(
    ddn_text: str, view_id: str
) -> list[dict[str, Any]]:
    """Compile Cube Usage Matrix (matrix.relations@1) or Aggregation Grid (table.records@1)."""
    from .cube_ddn import ddn_to_semantic_model

    parsed = ddn_to_semantic_model(ddn_text)
    model = parsed.get('model', parsed)
    dims = model.get('dimensions') or []
    mgs = model.get('measure_groups') or []
    mats = model.get('materializations') or []

    if view_id == 'cube_usage_matrix':
        headers = ['Measure Group / Fact'] + [d['name'] for d in dims]
        rows = []
        for mg in mgs:
            usage_map = {u['dimension_id']: u for u in mg.get('dimension_usage') or []}
            r_cells = [f"{mg['name']} ({mg.get('fact_source', '')})"]
            for d in dims:
                u = usage_map.get(d['id'])
                if not u:
                    r_cells.append('—')
                else:
                    kind = u.get('relationship_kind', 'regular')
                    act = '' if u.get('active', True) else ' [inactive]'
                    r_cells.append(f'{kind}{act}')
            rows.append(r_cells)
        w = max(560.0, 240.0 + len(dims) * 165.0)
        h = max(180.0, 92.0 + len(rows) * 38.0)
        return [{
            'id': 'cube-usage-matrix-widget',
            'widget_kind': 'data_grid',
            'title': f"{model.get('name') or 'Cube'} — Dimension Usage Matrix",
            'headers': headers,
            'rows': rows,
            'x': 48.0,
            'y': 48.0,
            'width': w,
            'height': h,
        }]

    headers = ['Plan ID', 'Name', 'Strategy', 'Target Relation', 'Grain Dimensions', 'Refresh Policy']
    rows = [
        [
            m.get('id', ''),
            m.get('name', ''),
            m.get('strategy', 'aggregate_table'),
            '.'.join(m.get('target_relation') or []),
            ', '.join(m.get('grain_dimensions') or []),
            m.get('refresh_policy', 'manual'),
        ]
        for m in mats
    ] or [['—', 'No materialization plans configured', '—', '—', '—', '—']]
    return [{
        'id': 'cube-agg-grid-widget',
        'widget_kind': 'data_grid',
        'title': f"{model.get('name') or 'Cube'} — Materialization & Aggregation Plans",
        'headers': headers,
        'rows': rows,
        'x': 48.0,
        'y': 48.0,
        'width': 980.0,
        'height': max(180.0, 92.0 + len(rows) * 38.0),
    }]


def compile_robin_scene(
    ddn_text: str,
    *,
    view_id: str | None = None,
    pinned_positions: Mapping[str, Mapping[str, Any]] | None = None,
    tile_size: int = 1024,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Compile a DDN document into a complete host-laid-out, tiled Robin Scene."""
    if tile_size < 128:
        raise ValueError('tile_size must be at least 128 pixels')

    ddn_sha = hashlib.sha256((ddn_text or '').encode('utf-8')).hexdigest()
    req_view = (view_id or '').strip()

    if use_cache and not pinned_positions:
        cached = GLOBAL_ROBIN_SCENE_CACHE.get(ddn_sha, req_view or '__default__', tile_size)
        if cached is not None:
            return cached

    scanned = fast_scan_ddn(ddn_text or '')
    module_hint = scanned['module_hint']
    views = scanned['views']

    # Specialized profile compilation: BI Question / BI Composed Dashboard
    if 'scratchrobin.bi.' in module_hint:
        default_vid, bi_views, bi_widgets = _compile_bi_scene_widgets(ddn_text, module_hint)
        sel_vid = req_view if any(v['id'] == req_view for v in bi_views) else default_vid
        if sel_vid.startswith('tab_'):
            target_tab = sel_vid[4:]
            active_widgets = [w for w in bi_widgets if w.get('tab_id') == target_tab]
            # Normalize Y to top of canvas when viewing single tab
            if active_widgets:
                min_wy = min(w['y'] for w in active_widgets)
                active_widgets = [
                    {**w, 'y': round(w['y'] - min_wy + 48.0, 2)}
                    for w in active_widgets
                ]
        else:
            active_widgets = bi_widgets
        c_bounds = _compute_overall_bounds([], [], [], active_widgets, tile_size)
        m_tiles, tiles_map = _slice_scene_into_tiles(
            ddn_sha, sel_vid, tile_size, [], [], [], active_widgets, c_bounds
        )
        scene = _assemble_scene(
            ddn_sha, sel_vid, 'panels.composed@1', bi_views, tile_size,
            c_bounds, [], [], [], active_widgets, m_tiles, tiles_map,
        )
        if use_cache and not pinned_positions:
            GLOBAL_ROBIN_SCENE_CACHE.put(ddn_sha, sel_vid, tile_size, scene)
        return scene

    # Specialized profile compilation: Screen Mesh & Screen Flow
    if 'scratchrobin.screen.mesh' in module_hint or any(
        el['role'] == 'ui.frame' for el in scanned['elements'].values()
    ):
        sel_vid, sm_views, sm_nodes, sm_edges, sm_widgets = _compile_screen_mesh_scene(
            ddn_text, req_view or None
        )
        c_bounds = _compute_overall_bounds(sm_nodes, sm_edges, [], sm_widgets, tile_size)
        m_tiles, tiles_map = _slice_scene_into_tiles(
            ddn_sha, sel_vid, tile_size, sm_nodes, sm_edges, [], sm_widgets, c_bounds
        )
        scene = _assemble_scene(
            ddn_sha, sel_vid, 'wireframe.ui@1', sm_views, tile_size,
            c_bounds, sm_nodes, sm_edges, [], sm_widgets, m_tiles, tiles_map,
        )
        if use_cache and not pinned_positions:
            GLOBAL_ROBIN_SCENE_CACHE.put(ddn_sha, sel_vid, tile_size, scene)
        return scene

    if not views:
        views = [{'id': 'main', 'profile': 'ddn@1', 'title': 'Main Diagram', 'include': [], 'include_empty': False}]

    sel_view_obj = next((v for v in views if v['id'] == req_view), views[0])
    sel_vid = sel_view_obj['id']
    sel_profile = sel_view_obj['profile']

    if use_cache and not pinned_positions:
        cached = GLOBAL_ROBIN_SCENE_CACHE.get(ddn_sha, sel_vid, tile_size)
        if cached is not None:
            return cached

    # Cube Matrix / Aggregation Grid views
    if sel_vid in ('cube_usage_matrix', 'cube_aggregation_grid') or sel_profile in (
        'matrix.relations@1', 'table.records@1'
    ):
        try:
            grid_widgets = _compile_cube_matrix_or_grid(ddn_text, sel_vid)
            c_bounds = _compute_overall_bounds([], [], [], grid_widgets, tile_size)
            m_tiles, tiles_map = _slice_scene_into_tiles(
                ddn_sha, sel_vid, tile_size, [], [], [], grid_widgets, c_bounds
            )
            scene = _assemble_scene(
                ddn_sha, sel_vid, sel_profile, views, tile_size,
                c_bounds, [], [], [], grid_widgets, m_tiles, tiles_map,
            )
            if use_cache and not pinned_positions:
                GLOBAL_ROBIN_SCENE_CACHE.put(ddn_sha, sel_vid, tile_size, scene)
            return scene
        except Exception:
            pass

    # Standard Graph / 4-Level ERD / Physical Schema / Cube Star compilation
    elements = scanned['elements']
    relations = scanned['relations']
    annotations = scanned['annotations']

    # Build member -> parent lookup and collect structured field metadata per table
    member_to_parent: dict[str, str] = {}
    pk_fields_by_table: dict[str, set[str]] = defaultdict(set)
    fk_fields_by_table: dict[str, set[str]] = defaultdict(set)

    for eid, el in elements.items():
        for mid in el['members']:
            member_to_parent[mid] = eid
        if el['role'] == 'constraint':
            ann = annotations.get(eid, {})
            ckind = (ann.get('constraint_type') or el['title'] or '').upper()
            p_tbl = member_to_parent.get(eid) or ann.get('parent_id') or ''
            if 'PRIMARY' in ckind or el['title'].upper().startswith('PK_'):
                for mid in el['members']:
                    pk_fields_by_table[p_tbl].add(mid)

    # Extract saved pins
    pins: dict[str, dict[str, Any]] = {}
    for subj_id, ann in annotations.items():
        if 'layout_x' in ann and 'layout_y' in ann:
            try:
                pins[subj_id] = {
                    'x': float(ann['layout_x']),
                    'y': float(ann['layout_y']),
                    'pinned': str(ann.get('layout_pinned', 'false')).lower() in ('true', '1'),
                }
            except ValueError:
                pass
    if pinned_positions:
        for nid, pos in pinned_positions.items():
            if isinstance(pos, Mapping) and 'x' in pos and 'y' in pos:
                pins[nid] = {
                    'x': float(pos['x']),
                    'y': float(pos['y']),
                    'pinned': bool(pos.get('pinned', True)),
                }

    # Filter to selected view's selection.include set!
    include_set = set(sel_view_obj.get('include') or ())
    has_filter = bool(include_set) or bool(sel_view_obj.get('include_empty'))

    # Identify FK columns from relations before measuring cards
    resolved_raw_edges: list[dict[str, Any]] = []
    for rid, rel in relations.items():
        if has_filter and rid not in include_set:
            # Also include relation if both endpoints belong to included top-level nodes
            eps = rel['endpoints']
            if len(eps) < 2:
                continue
            s_top = member_to_parent.get(eps[0], eps[0])
            t_top = member_to_parent.get(eps[1], eps[1])
            if not (s_top in include_set and t_top in include_set):
                continue
        eps = rel['endpoints']
        if len(eps) < 2:
            continue
        s_raw, t_raw = eps[0], eps[1]
        s_top = member_to_parent.get(s_raw, s_raw)
        t_top = member_to_parent.get(t_raw, t_raw)
        if s_raw != s_top:
            fk_fields_by_table[s_top].add(s_raw)
        ann = annotations.get(rid, {})
        resolved_raw_edges.append({
            'id': rid,
            'title': rel['title'],
            'source': s_top,
            'target': t_top,
            'source_field_id': s_raw if s_raw != s_top else '',
            'target_field_id': t_raw if t_raw != t_top else '',
            'link_kind': ann.get('link_kind') or (
                'inactive_role' if ann.get('active') == 'false' else 'fk'
            ),
        })

    child_roles = {'field', 'index', 'constraint', 'ref', 'record'}
    measured_nodes: list[dict[str, Any]] = []
    for eid, el in elements.items():
        if eid in member_to_parent or el['role'] in child_roles:
            continue
        if has_filter and eid not in include_set:
            continue
        ann = annotations.get(eid, {})
        fields_list: list[dict[str, Any]] = []
        for idx, mid in enumerate(el['members']):
            mel = elements.get(mid)
            if not mel or mel['role'] != 'field':
                continue
            mprops = mel['props']
            fname = mel['title']
            is_pk = (
                mid in pk_fields_by_table.get(eid, set())
                or fname.upper() in ('ID', 'DOC_NAME')
                or (idx == 0 and mprops.get('nullable') == 'false')
            )
            is_fk = (
                mid in fk_fields_by_table.get(eid, set())
                or any(
                    re_e['source'] == eid and re_e['title'].upper() == fname.upper()
                    for re_e in resolved_raw_edges
                )
            )
            fields_list.append({
                'id': mid,
                'name': fname,
                'datatype': mprops.get('datatype') or '',
                'nullable': mprops.get('nullable', 'true').lower() != 'false',
                'is_pk': is_pk,
                'is_fk': is_fk,
            })
        measured_nodes.append(_measure_entity_card(eid, el, fields_list, ann))

    # Fallback if a view only contains standalone non-parented elements
    if not measured_nodes and not sel_view_obj.get('include_empty'):
        for eid, el in elements.items():
            if el['role'] == 'record':
                continue
            if has_filter and eid not in include_set:
                continue
            measured_nodes.append(
                _measure_entity_card(eid, el, [], annotations.get(eid, {}))
            )

    zones: list[dict[str, Any]] = []
    distinct_levels = {n['level'] for n in measured_nodes}
    erd_4_levels = [
        lvl for lvl in ('conceptual', 'logical', 'physical', 'deployment')
        if lvl in distinct_levels
    ]

    if sel_vid == 'erd_all_levels' and len(erd_4_levels) > 1:
        # Place each modelling level in its own clean architectural swimlane band!
        placed_nodes: list[dict[str, Any]] = []
        intra_edges_routed: list[dict[str, Any]] = []
        node_ids_by_level: dict[str, set[str]] = {}
        cur_band_y = 72.0

        for lvl in erd_4_levels:
            lvl_nodes = [n for n in measured_nodes if n['level'] == lvl]
            lvl_ids = {n['id'] for n in lvl_nodes}
            node_ids_by_level[lvl] = lvl_ids
            lvl_edges = [
                e for e in resolved_raw_edges
                if e['source'] in lvl_ids and e['target'] in lvl_ids
            ]
            p_nodes, r_edges, b_bounds = _place_layered_component_zone(
                lvl_nodes, lvl_edges, pins, origin_x=72.0, origin_y=cur_band_y + 52.0
            )
            pal = LEVEL_PALETTE[lvl]
            zone_w = max(840.0, b_bounds['max_x'] - 40.0 + 48.0)
            zone_h = max(220.0, b_bounds['max_y'] - cur_band_y + 36.0)
            zones.append({
                'id': f'zone-{lvl}',
                'level': lvl,
                'label': f"{pal['badge_label']} LEVEL ({len(lvl_nodes)} items)",
                'x': 32.0,
                'y': round(cur_band_y, 2),
                'width': round(zone_w, 2),
                'height': round(zone_h, 2),
                'border': pal['border'],
                'header_bg': pal['header_bg'],
                'header_fg': pal['header_fg'],
            })
            placed_nodes.extend(p_nodes)
            intra_edges_routed.extend(r_edges)
            cur_band_y += zone_h + 72.0

        # Cross-level trace links: route cleanly only when count <= 24 so 4-level overview stays crisp
        cross_edges = [
            e for e in resolved_raw_edges
            if e['source'] != e['target']
            and not any(
                e['source'] in s and e['target'] in s
                for s in node_ids_by_level.values()
            )
        ]
        if len(cross_edges) <= 24:
            routed_edges = intra_edges_routed + _route_orthogonal_edges(placed_nodes, cross_edges)
        else:
            routed_edges = intra_edges_routed
    else:
        placed_nodes, routed_edges, _ = _place_layered_component_zone(
            measured_nodes, resolved_raw_edges, pins, origin_x=48.0, origin_y=48.0
        )

    c_bounds = _compute_overall_bounds(placed_nodes, routed_edges, zones, [], tile_size)
    m_tiles, tiles_map = _slice_scene_into_tiles(
        ddn_sha, sel_vid, tile_size, placed_nodes, routed_edges, zones, [], c_bounds
    )
    scene = _assemble_scene(
        ddn_sha, sel_vid, sel_profile, views, tile_size,
        c_bounds, placed_nodes, routed_edges, zones, [], m_tiles, tiles_map,
    )
    if use_cache and not pinned_positions:
        GLOBAL_ROBIN_SCENE_CACHE.put(ddn_sha, sel_vid, tile_size, scene)
        if not req_view:
            GLOBAL_ROBIN_SCENE_CACHE.put(ddn_sha, '__default__', tile_size, scene)
    return scene


def _compute_overall_bounds(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    zones: list[dict[str, Any]],
    widgets: list[dict[str, Any]],
    tile_size: int,
) -> dict[str, float]:
    xs: list[float] = []
    ys: list[float] = []
    for n in nodes:
        xs.extend((n['x'], n['x'] + n['width']))
        ys.extend((n['y'], n['y'] + n['height']))
    for e in edges:
        xs.extend((e['bounds']['min_x'], e['bounds']['max_x']))
        ys.extend((e['bounds']['min_y'], e['bounds']['max_y']))
    for z in zones:
        xs.extend((z['x'], z['x'] + z['width']))
        ys.extend((z['y'], z['y'] + z['height']))
    for w in widgets:
        xs.extend((w['x'], w['x'] + w['width']))
        ys.extend((w['y'], w['y'] + w['height']))

    if not xs:
        return {
            'min_x': 0.0,
            'min_y': 0.0,
            'max_x': float(tile_size),
            'max_y': 640.0,
            'width': float(tile_size),
            'height': 640.0,
        }

    min_x = round(min(xs) - 36.0, 2)
    min_y = round(min(ys) - 36.0, 2)
    max_x = round(max(xs) + 48.0, 2)
    max_y = round(max(ys) + 48.0, 2)
    return {
        'min_x': min_x,
        'min_y': min_y,
        'max_x': max_x,
        'max_y': max_y,
        'width': round(max(320.0, max_x - min_x), 2),
        'height': round(max(240.0, max_y - min_y), 2),
    }


def _assemble_scene(
    ddn_sha: str,
    view_id: str,
    profile: str,
    views: list[dict[str, Any]],
    tile_size: int,
    canvas_bounds: dict[str, float],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    zones: list[dict[str, Any]],
    widgets: list[dict[str, Any]],
    manifest_tiles: list[dict[str, Any]],
    tiles_by_coord: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    minimap_nodes = [
        {
            'id': n['id'],
            'x': n['x'],
            'y': n['y'],
            'w': n['width'],
            'h': n['height'],
            'color': (n.get('palette') or {}).get('border', '#2563eb'),
        }
        for n in nodes
    ] + [
        {
            'id': w['id'],
            'x': w['x'],
            'y': w['y'],
            'w': w['width'],
            'h': w['height'],
            'color': '#0284c7',
        }
        for w in widgets
    ]
    return {
        'ddn_sha256': ddn_sha,
        'view_id': view_id,
        'profile': profile,
        'algorithm': 'scratchrobin-server-layered@1',
        'tile_size': tile_size,
        'canvas_bounds': canvas_bounds,
        'views': [
            {'id': v['id'], 'name': v.get('title') or v['id'], 'profile': v.get('profile', 'ddn@1')}
            for v in views
        ],
        'summary': {
            'view_count': len(views),
            'node_count': len(nodes),
            'edge_count': len(edges),
            'widget_count': len(widgets),
            'tile_count': len(manifest_tiles),
        },
        'diagnostics': [],
        'minimap': minimap_nodes,
        'nodes': nodes,
        'edges': edges,
        'zones': zones,
        'widgets': widgets,
        'tiles': manifest_tiles,
        'tiles_by_coord': tiles_by_coord,
    }


def slice_scene_response(
    scene: dict[str, Any], coords: list[str] | None = None
) -> dict[str, Any]:
    """Return lightweight Scene Manifest + requested tile payloads."""
    tiles_map = scene['tiles_by_coord']
    if coords is None:
        # Default initial viewport burst: up to first 6 tiles so initial paint is instant
        selected_coords = list(tiles_map.keys())[:6]
    else:
        selected_coords = [c for c in coords if c in tiles_map]

    return {
        'ddn_sha256': scene['ddn_sha256'],
        'view_id': scene['view_id'],
        'profile': scene['profile'],
        'algorithm': scene['algorithm'],
        'tile_size': scene['tile_size'],
        'canvas_bounds': scene['canvas_bounds'],
        'views': scene['views'],
        'summary': scene['summary'],
        'diagnostics': scene['diagnostics'],
        'minimap': scene['minimap'],
        'tile_index': scene['tiles'],
        'loaded_tiles': {c: tiles_map[c] for c in selected_coords},
    }


def render_scene_to_svg(scene: dict[str, Any]) -> str:
    """Render any compiled Robin Scene into a crisp standalone vector SVG document."""
    cb = scene['canvas_bounds']
    vx, vy, vw, vh = cb['min_x'], cb['min_y'], cb['width'], cb['height']
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx} {vy} {vw} {vh}" '
        f'width="{int(vw)}" height="{int(vh)}" font-family="Inter, system-ui, -apple-system, sans-serif">',
        '<defs>',
        '<marker id="sr-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#475569"/></marker>',
        '<marker id="sr-one" viewBox="0 0 10 12" refX="9" refY="6" markerWidth="8" markerHeight="9" orient="auto">'
        '<line x1="6" y1="1" x2="6" y2="11" stroke="#334155" stroke-width="1.6"/></marker>',
        '<marker id="sr-many" viewBox="0 0 14 12" refX="1" refY="6" markerWidth="10" markerHeight="9" orient="auto">'
        '<path d="M 13 6 L 1 1 M 13 6 L 1 6 M 13 6 L 1 11" stroke="#334155" stroke-width="1.4" fill="none"/></marker>',
        '</defs>',
        f'<rect x="{vx}" y="{vy}" width="{vw}" height="{vh}" fill="#f8fafc"/>',
    ]

    for z in scene.get('zones', ()):
        parts.append(
            f'<g><rect x="{z["x"]}" y="{z["y"]}" width="{z["width"]}" height="{z["height"]}" '
            f'rx="10" fill="#ffffff" fill-opacity="0.65" stroke="{z["border"]}" stroke-dasharray="6 4" stroke-width="1.5"/>'
            f'<rect x="{z["x"]}" y="{z["y"]}" width="{z["width"]}" height="32" rx="10" fill="{z["header_bg"]}"/>'
            f'<text x="{z["x"] + 16}" y="{z["y"] + 21}" font-size="12" font-weight="700" fill="{z["header_fg"]}">'
            f'{xml_escape(z["label"])}</text></g>'
        )

    for e in scene.get('edges', ()):
        pts = e['points']
        if len(pts) < 2:
            continue
        d_cmd = 'M ' + ' L '.join(f'{p["x"]} {p["y"]}' for p in pts)
        dash = ' stroke-dasharray="5 4"' if e.get('dashed') else ''
        m_start = ' marker-start="url(#sr-many)"' if e.get('source_mark') == 'many' else ''
        m_end = (
            ' marker-end="url(#sr-arrow)"'
            if e.get('target_mark') == 'arrow'
            else ' marker-end="url(#sr-one)"'
        )
        parts.append(
            f'<path d="{d_cmd}" fill="none" stroke="#475569" stroke-width="1.5" '
            f'stroke-linejoin="round"{dash}{m_start}{m_end}/>'
        )
        lbl = e.get('display_label')
        if lbl:
            lp = e['label_pos']
            pw = lp['w']
            parts.append(
                f'<rect x="{lp["x"] - pw / 2:.1f}" y="{lp["y"] - 9:.1f}" width="{pw:.1f}" height="18" '
                f'rx="4" fill="#ffffff" stroke="#cbd5e1" stroke-width="1"/>'
                f'<text x="{lp["x"]:.1f}" y="{lp["y"] + 4:.1f}" text-anchor="middle" font-size="10" fill="#334155">'
                f'{xml_escape(lbl)}</text>'
            )

    for n in scene.get('nodes', ()):
        pal = n.get('palette') or LEVEL_PALETTE['physical']
        nx, ny, nw, nh = n['x'], n['y'], n['width'], n['height']
        parts.append(
            f'<g><rect x="{nx}" y="{ny}" width="{nw}" height="{nh}" rx="6" fill="#ffffff" '
            f'stroke="{pal["border"]}" stroke-width="1.5"/>'
            f'<rect x="{nx}" y="{ny}" width="{nw}" height="{CARD_HEADER_H}" rx="6" fill="{pal["header_bg"]}"/>'
            f'<line x1="{nx}" y1="{ny + CARD_HEADER_H}" x2="{nx + nw}" y2="{ny + CARD_HEADER_H}" stroke="{pal["border"]}" stroke-width="1"/>'
            f'<text x="{nx + 12}" y="{ny + 23}" font-size="12.5" font-weight="700" fill="{pal["header_fg"]}">'
            f'{xml_escape(n["name"])}</text>'
        )
        for f in n.get('fields', ()):
            fy = ny + f['port_y'] + 4.0
            prefix = '🔑 ' if f.get('is_pk') else ('🔗 ' if f.get('is_fk') else '')
            nn_mark = '' if f.get('nullable', True) else ' *'
            parts.append(
                f'<text x="{nx + 12}" y="{fy:.1f}" font-size="11" fill="#1e293b">'
                f'{xml_escape(prefix + f["name"] + nn_mark)}</text>'
            )
            if f.get('datatype'):
                parts.append(
                    f'<text x="{nx + nw - 10}" y="{fy:.1f}" text-anchor="end" font-size="10.5" fill="#64748b">'
                    f'{xml_escape(str(f["datatype"])[:22])}</text>'
                )
        parts.append('</g>')

    for w in scene.get('widgets', ()):
        wx, wy, ww, wh = w['x'], w['y'], w['width'], w['height']
        parts.append(
            f'<g><rect x="{wx}" y="{wy}" width="{ww}" height="{wh}" rx="8" fill="#ffffff" stroke="#94a3b8" stroke-width="1.5"/>'
            f'<rect x="{wx}" y="{wy}" width="{ww}" height="34" rx="8" fill="#f1f5f9"/>'
            f'<text x="{wx + 14}" y="{wy + 22}" font-size="12.5" font-weight="700" fill="#0f172a">'
            f'{xml_escape(w.get("title") or w["id"])}</text></g>'
        )

    parts.append('</svg>')
    return ''.join(parts)
