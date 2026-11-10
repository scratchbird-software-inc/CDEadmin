##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Shared server-side DDN calculation, layout, tiling and Store-DDN process.

Owner direction, 2026-11-09 & 2026-11-10:
- Server-side code performs the calculations, deterministic layered layout,
  incremental placement (preserving pinned nodes) and spatial tiling for
  larger diagrams, while the client renders vectors through the single
  shared DDN viewer.
- Dialect expansion order (B1): bindings and element IDs first, then ERD
  modelling levels, BI content, cube dimensional elements, and screen mesh
  wireframe controls, image regions and screen navigation.
- Acceptance (A9) always requires a ScratchRobin permission, with an
  optional per-project Git review gate recorded on the acceptance row.
- Design inclusion (A10) pins the target version by default with an
  explicit opt-in to follow the latest accepted version.
- ERD modelling (D1-D4) supports conceptual, logical, physical and
  deployment levels, neutral-logical engine-to-engine type conversion with
  user-editable type maps and explicit loss choices, opaque extension
  metadata (no ORM fields), and system-diagram drift overlays whose change
  requests route through native operation review.
"""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import math
import re
import threading
from typing import Any

from pgadmin.cdeadmin.workspace import ddn_source as ddn

from .ddn_elements import (
    _parse_blocks,
    ddn_text_to_workspace,
    inspect_ddn_text,
    sha256_text,
    workspace_to_ddn_text,
)
from .identifiers import is_uuid7, uuid7
from .service import (
    DesignStore,
    DesignStoreError,
    DesignStoreForbidden,
    DesignStoreNotFound,
)

ERD_LEVELS = ('conceptual', 'logical', 'physical', 'deployment')

DIALECT_EXPANSION_ORDER = (
    'bindings_and_element_ids',
    'erd_modelling_levels',
    'bi_questions_and_dashboards',
    'cube_dimensional_elements',
    'screen_mesh_controls_regions_navigation',
)

# Neutral logical types and default per-engine physical type maps (D4).
LOGICAL_TYPES = (
    'integer',
    'bigint',
    'smallint',
    'decimal',
    'float',
    'boolean',
    'string',
    'text',
    'binary',
    'date',
    'time',
    'timestamp',
    'timestamptz',
    'uuid',
    'json',
    'array',
)

DEFAULT_LOGICAL_TYPE_MAPS: dict[str, dict[str, dict[str, Any]]] = {
    'sqlite': {
        'integer': {'physical': 'INTEGER', 'lossy': False},
        'bigint': {'physical': 'INTEGER', 'lossy': False},
        'smallint': {'physical': 'INTEGER', 'lossy': False},
        'decimal': {
            'physical': 'NUMERIC',
            'lossy': True,
            'reason': 'SQLite NUMERIC affinity uses floating/integer storage',
        },
        'float': {'physical': 'REAL', 'lossy': False},
        'boolean': {'physical': 'INTEGER', 'lossy': False},
        'string': {'physical': 'TEXT', 'lossy': False},
        'text': {'physical': 'TEXT', 'lossy': False},
        'binary': {'physical': 'BLOB', 'lossy': False},
        'date': {'physical': 'TEXT', 'lossy': False},
        'time': {'physical': 'TEXT', 'lossy': False},
        'timestamp': {'physical': 'TEXT', 'lossy': False},
        'timestamptz': {
            'physical': 'TEXT',
            'lossy': True,
            'reason': 'SQLite stores ISO-8601 text without native tz catalog',
        },
        'uuid': {'physical': 'TEXT', 'lossy': False},
        'json': {'physical': 'TEXT', 'lossy': False},
        'array': {
            'physical': 'TEXT',
            'lossy': True,
            'reason': 'SQLite has no native array type; encoded as JSON text',
        },
    },
    'duckdb': {
        'integer': {'physical': 'INTEGER', 'lossy': False},
        'bigint': {'physical': 'BIGINT', 'lossy': False},
        'smallint': {'physical': 'SMALLINT', 'lossy': False},
        'decimal': {'physical': 'DECIMAL(18,4)', 'lossy': False},
        'float': {'physical': 'DOUBLE', 'lossy': False},
        'boolean': {'physical': 'BOOLEAN', 'lossy': False},
        'string': {'physical': 'VARCHAR', 'lossy': False},
        'text': {'physical': 'VARCHAR', 'lossy': False},
        'binary': {'physical': 'BLOB', 'lossy': False},
        'date': {'physical': 'DATE', 'lossy': False},
        'time': {'physical': 'TIME', 'lossy': False},
        'timestamp': {'physical': 'TIMESTAMP', 'lossy': False},
        'timestamptz': {'physical': 'TIMESTAMPTZ', 'lossy': False},
        'uuid': {'physical': 'UUID', 'lossy': False},
        'json': {'physical': 'JSON', 'lossy': False},
        'array': {'physical': 'VARCHAR[]', 'lossy': False},
    },
    'firebird': {
        'integer': {'physical': 'INTEGER', 'lossy': False},
        'bigint': {'physical': 'BIGINT', 'lossy': False},
        'smallint': {'physical': 'SMALLINT', 'lossy': False},
        'decimal': {'physical': 'DECIMAL(18,4)', 'lossy': False},
        'float': {'physical': 'DOUBLE PRECISION', 'lossy': False},
        'boolean': {'physical': 'BOOLEAN', 'lossy': False},
        'string': {'physical': 'VARCHAR(255)', 'lossy': False},
        'text': {'physical': 'BLOB SUB_TYPE TEXT', 'lossy': False},
        'binary': {'physical': 'BLOB SUB_TYPE BINARY', 'lossy': False},
        'date': {'physical': 'DATE', 'lossy': False},
        'time': {'physical': 'TIME', 'lossy': False},
        'timestamp': {'physical': 'TIMESTAMP', 'lossy': False},
        'timestamptz': {
            'physical': 'TIMESTAMP WITH TIME ZONE',
            'lossy': False,
        },
        'uuid': {'physical': 'CHAR(16) CHARACTER SET OCTETS', 'lossy': False},
        'json': {
            'physical': 'BLOB SUB_TYPE TEXT',
            'lossy': True,
            'reason': 'Firebird 5 stores JSON in text blobs without JSON type',
        },
        'array': {
            'physical': 'BLOB SUB_TYPE TEXT',
            'lossy': True,
            'reason': 'Unbounded logical array requires explicit bounds in FB',
        },
    },
    'mysql': {
        'integer': {'physical': 'INT', 'lossy': False},
        'bigint': {'physical': 'BIGINT', 'lossy': False},
        'smallint': {'physical': 'SMALLINT', 'lossy': False},
        'decimal': {'physical': 'DECIMAL(18,4)', 'lossy': False},
        'float': {'physical': 'DOUBLE', 'lossy': False},
        'boolean': {'physical': 'TINYINT(1)', 'lossy': False},
        'string': {'physical': 'VARCHAR(255)', 'lossy': False},
        'text': {'physical': 'LONGTEXT', 'lossy': False},
        'binary': {'physical': 'LONGBLOB', 'lossy': False},
        'date': {'physical': 'DATE', 'lossy': False},
        'time': {'physical': 'TIME', 'lossy': False},
        'timestamp': {'physical': 'DATETIME', 'lossy': False},
        'timestamptz': {
            'physical': 'TIMESTAMP',
            'lossy': True,
            'reason': 'MySQL TIMESTAMP has 1970-2038 range and session tz',
        },
        'uuid': {'physical': 'CHAR(36)', 'lossy': False},
        'json': {'physical': 'JSON', 'lossy': False},
        'array': {
            'physical': 'JSON',
            'lossy': True,
            'reason': 'MySQL represents arrays as JSON documents',
        },
    },
    'mariadb': {
        'integer': {'physical': 'INT', 'lossy': False},
        'bigint': {'physical': 'BIGINT', 'lossy': False},
        'smallint': {'physical': 'SMALLINT', 'lossy': False},
        'decimal': {'physical': 'DECIMAL(18,4)', 'lossy': False},
        'float': {'physical': 'DOUBLE', 'lossy': False},
        'boolean': {'physical': 'BOOLEAN', 'lossy': False},
        'string': {'physical': 'VARCHAR(255)', 'lossy': False},
        'text': {'physical': 'LONGTEXT', 'lossy': False},
        'binary': {'physical': 'LONGBLOB', 'lossy': False},
        'date': {'physical': 'DATE', 'lossy': False},
        'time': {'physical': 'TIME', 'lossy': False},
        'timestamp': {'physical': 'DATETIME', 'lossy': False},
        'timestamptz': {
            'physical': 'TIMESTAMP',
            'lossy': True,
            'reason': 'MariaDB TIMESTAMP converts via session time zone',
        },
        'uuid': {'physical': 'UUID', 'lossy': False},
        'json': {'physical': 'JSON', 'lossy': False},
        'array': {
            'physical': 'JSON',
            'lossy': True,
            'reason': 'MariaDB represents arrays as JSON text',
        },
    },
    'postgresql': {
        'integer': {'physical': 'integer', 'lossy': False},
        'bigint': {'physical': 'bigint', 'lossy': False},
        'smallint': {'physical': 'smallint', 'lossy': False},
        'decimal': {'physical': 'numeric(18,4)', 'lossy': False},
        'float': {'physical': 'double precision', 'lossy': False},
        'boolean': {'physical': 'boolean', 'lossy': False},
        'string': {'physical': 'varchar(255)', 'lossy': False},
        'text': {'physical': 'text', 'lossy': False},
        'binary': {'physical': 'bytea', 'lossy': False},
        'date': {'physical': 'date', 'lossy': False},
        'time': {'physical': 'time', 'lossy': False},
        'timestamp': {'physical': 'timestamp', 'lossy': False},
        'timestamptz': {'physical': 'timestamptz', 'lossy': False},
        'uuid': {'physical': 'uuid', 'lossy': False},
        'json': {'physical': 'jsonb', 'lossy': False},
        'array': {'physical': 'text[]', 'lossy': False},
    },
}

_ENDPOINT_DEF_RE = re.compile(
    r'definition\s*\n\s+id\s+"((?:[^"]|"")+)"', re.MULTILINE
)
_MEMBER_ITEM_RE = re.compile(
    r'item\s*\n\s+id\s+"((?:[^"]|"")+)"', re.MULTILINE
)
_DATATYPE_RE = re.compile(
    r'^(\s+datatype\s+)"((?:[^"]|"")+)"\s*$', re.MULTILINE
)


def normalize_to_logical_type(physical_type: str) -> str:
    """Map an engine-native data type string to the neutral logical type."""
    if not isinstance(physical_type, str) or not physical_type.strip():
        return 'string'
    upper = physical_type.strip().upper()
    if upper.endswith('[]') or 'ARRAY' in upper:
        return 'array'
    if 'UUID' in upper or 'CHAR(16) CHARACTER SET OCTETS' in upper:
        return 'uuid'
    if 'JSON' in upper:
        return 'json'
    if 'TIMESTAMPTZ' in upper or 'WITH TIME ZONE' in upper:
        return 'timestamptz'
    if 'TIMESTAMP' in upper or 'DATETIME' in upper:
        return 'timestamp'
    if upper == 'DATE':
        return 'date'
    if upper.startswith('TIME'):
        return 'time'
    if 'BOOL' in upper or upper == 'TINYINT(1)':
        return 'boolean'
    if 'BIGINT' in upper or 'INT8' in upper:
        return 'bigint'
    if 'SMALLINT' in upper or 'TINYINT' in upper or 'INT2' in upper:
        return 'smallint'
    if 'INT' in upper or 'SERIAL' in upper:
        return 'integer'
    if any(k in upper for k in ('DEC', 'NUMERIC', 'NUMBER', 'MONEY')):
        return 'decimal'
    if any(k in upper for k in ('REAL', 'FLOA', 'DOUB')):
        return 'float'
    if any(k in upper for k in ('BLOB', 'BYTEA', 'BINARY', 'VARBINARY')):
        return 'binary'
    if any(k in upper for k in ('TEXT', 'CLOB')):
        return 'text'
    return 'string'


class ServerTileCache:
    """Bounded LRU cache of server-computed layout and spatial tiles (B2)."""

    def __init__(self, max_entries: int = 128) -> None:
        self._max_entries = max(8, int(max_entries))
        self._entries: OrderedDict[tuple[str, str, int], dict[str, Any]] = (
            OrderedDict()
        )
        self._lock = threading.Lock()

    def get(
        self, ddn_sha256: str, view_id: str, tile_size: int
    ) -> dict[str, Any] | None:
        key = (ddn_sha256, view_id, tile_size)
        with self._lock:
            item = self._entries.get(key)
            if item is not None:
                self._entries.move_to_end(key)
                return json.loads(json.dumps(item))
            return None

    def put(
        self,
        ddn_sha256: str,
        view_id: str,
        tile_size: int,
        layout_payload: dict[str, Any],
    ) -> None:
        key = (ddn_sha256, view_id, tile_size)
        with self._lock:
            self._entries[key] = json.loads(json.dumps(layout_payload))
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


GLOBAL_TILE_CACHE = ServerTileCache()


def _extract_existing_layout(
    blocks: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Read saved node coordinates and pin flags from x_record annotations."""
    placements: dict[str, dict[str, Any]] = {}
    for block in blocks:
        if block['kind'] != 'element' or block['role'] != 'record':
            continue
        body = block['body']
        if 'subject_id' not in body:
            continue
        subj_match = re.search(
            r'^\s+subject_id\s+"((?:[^"]|"")+)"\s*$', body, re.MULTILINE
        )
        if not subj_match:
            continue
        subject_id = subj_match.group(1).replace('""', '"')
        x_match = re.search(
            r'^\s+layout_x\s+"?(-?[0-9]+(?:\.[0-9]+)?)"?\s*$',
            body,
            re.MULTILINE,
        )
        y_match = re.search(
            r'^\s+layout_y\s+"?(-?[0-9]+(?:\.[0-9]+)?)"?\s*$',
            body,
            re.MULTILINE,
        )
        pin_match = re.search(
            r'^\s+layout_pinned\s+"?(true|false|1|0)"?\s*$',
            body,
            re.MULTILINE,
        )
        if x_match and y_match:
            pinned = (
                pin_match.group(1).lower() in ('true', '1')
                if pin_match
                else False
            )
            placements[subject_id] = {
                'x': float(x_match.group(1)),
                'y': float(y_match.group(1)),
                'pinned': pinned,
            }
    return placements


def compute_server_layout(
    ddn_text: str,
    *,
    view_id: str | None = None,
    pinned_positions: dict[str, dict[str, Any]] | None = None,
    tile_size: int = 1024,
    gap_x: int = 320,
    gap_y: int = 180,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Compute deterministic layered layout, incremental placement and tiles.

    Implements owner decisions B2 and B3:
    - Runs on the server with deterministic Sugiyama-style longest-path
      layering and barycenter crossing reduction.
    - Honors pinned node coordinates and performs incremental placement for
      unpinned/new nodes without colliding with pinned nodes.
    - Partitions the resulting canvas into spatial tiles of ``tile_size``
      pixels and caches the result by ``(ddn_sha256, view_id, tile_size)``.
    """
    if tile_size < 128:
        raise ValueError('tile_size must be at least 128 pixels')
    info = inspect_ddn_text(ddn_text)
    selected_view = (
        view_id
        or (info['views'][0]['id'] if info['views'] else 'main')
    )
    digest = sha256_text(ddn_text)
    if use_cache and not pinned_positions:
        cached = GLOBAL_TILE_CACHE.get(digest, selected_view, tile_size)
        if cached is not None:
            return cached

    blocks = _parse_blocks(ddn_text)
    saved_placements = _extract_existing_layout(blocks)
    pins: dict[str, dict[str, Any]] = dict(saved_placements)
    if pinned_positions:
        for nid, pos in pinned_positions.items():
            if isinstance(pos, dict) and 'x' in pos and 'y' in pos:
                pins[nid] = {
                    'x': float(pos['x']),
                    'y': float(pos['y']),
                    'pinned': bool(pos.get('pinned', True)),
                }

    # Collect member counts and directed edges between top-level nodes.
    member_To_parent: dict[str, str] = {}
    member_counts: dict[str, int] = {}
    raw_edges: list[dict[str, str]] = []

    for block in blocks:
        if block['kind'] == 'element' and block['role'] != 'record':
            members = [
                m.group(1).replace('""', '"')
                for m in _MEMBER_ITEM_RE.finditer(block['body'])
            ]
            if members:
                member_counts[block['id']] = len(members)
                for mid in members:
                    member_To_parent[mid] = block['id']
        elif block['kind'] == 'relation':
            endpoints = [
                m.group(1).replace('""', '"')
                for m in _ENDPOINT_DEF_RE.finditer(block['body'])
            ]
            if len(endpoints) >= 2:
                raw_edges.append({
                    'id': block['id'],
                    'title': block['title'],
                    'source': endpoints[0],
                    'target': endpoints[1],
                })

    child_roles = {'field', 'index', 'constraint', 'ref', 'record'}
    top_nodes: list[dict[str, Any]] = []
    node_by_id: dict[str, dict[str, Any]] = {}
    for elem in info['elements']:
        eid = elem['id']
        role = elem['role']
        if eid in member_To_parent or role in child_roles:
            continue
        m_count = member_counts.get(eid, 0)
        width = 240.0
        height = float(64 + min(m_count, 24) * 22)
        node_entry = {
            'id': eid,
            'name': elem['name'],
            'role': role,
            'width': width,
            'height': height,
            'member_count': m_count,
        }
        top_nodes.append(node_entry)
        node_by_id[eid] = node_entry

    # If a diagram only has child elements, lay out all non-record elements.
    if not top_nodes:
        for elem in info['elements']:
            if elem['role'] == 'record':
                continue
            eid = elem['id']
            node_entry = {
                'id': eid,
                'name': elem['name'],
                'role': elem['role'],
                'width': 220.0,
                'height': 72.0,
                'member_count': 0,
            }
            top_nodes.append(node_entry)
            node_by_id[eid] = node_entry

    edges: list[dict[str, Any]] = []
    outgoing: dict[str, list[str]] = {n['id']: [] for n in top_nodes}
    incoming: dict[str, list[str]] = {n['id']: [] for n in top_nodes}

    for edge in raw_edges:
        src = member_To_parent.get(edge['source'], edge['source'])
        tgt = member_To_parent.get(edge['target'], edge['target'])
        if src in node_by_id and tgt in node_by_id:
            edges.append({
                'id': edge['id'],
                'title': edge['title'],
                'source': src,
                'target': tgt,
            })
            if src != tgt:
                outgoing[src].append(tgt)
                incoming[tgt].append(src)

    # Deterministic longest-path layering with cycle guard.
    ordered_ids = sorted(
        node_by_id,
        key=lambda nid: (node_by_id[nid]['name'], nid),
    )
    layers: dict[str, int] = {}
    visiting: set[str] = set()

    def assign_layer(nid: str) -> int:
        if nid in layers:
            return layers[nid]
        if nid in visiting:
            return 0
        visiting.add(nid)
        preds = incoming.get(nid, [])
        if not preds:
            depth = 0
        else:
            depth = max(assign_layer(p) + 1 for p in preds)
        visiting.remove(nid)
        layers[nid] = min(depth, max(0, len(ordered_ids) - 1))
        return layers[nid]

    for nid in ordered_ids:
        assign_layer(nid)

    by_layer: dict[int, list[str]] = {}
    for nid in ordered_ids:
        by_layer.setdefault(layers[nid], []).append(nid)

    # Barycenter ordering pass (forward + backward) for crossing reduction.
    sorted_layer_indices = sorted(by_layer)
    order_in_layer: dict[str, int] = {}
    for l_idx in sorted_layer_indices:
        for pos_idx, nid in enumerate(by_layer[l_idx]):
            order_in_layer[nid] = pos_idx

    for _pass in range(2):
        for l_idx in sorted_layer_indices[1:]:
            def _bary_fwd(nid: str) -> tuple[float, str, str]:
                preds = incoming.get(nid, [])
                if not preds:
                    return (
                        float(order_in_layer[nid]),
                        node_by_id[nid]['name'],
                        nid,
                    )
                avg = sum(order_in_layer[p] for p in preds) / len(preds)
                return (avg, node_by_id[nid]['name'], nid)

            by_layer[l_idx].sort(key=_bary_fwd)
            for pos_idx, nid in enumerate(by_layer[l_idx]):
                order_in_layer[nid] = pos_idx

        for l_idx in reversed(sorted_layer_indices[:-1]):
            def _bary_bwd(nid: str) -> tuple[float, str, str]:
                succs = outgoing.get(nid, [])
                if not succs:
                    return (
                        float(order_in_layer[nid]),
                        node_by_id[nid]['name'],
                        nid,
                    )
                avg = sum(order_in_layer[s] for s in succs) / len(succs)
                return (avg, node_by_id[nid]['name'], nid)

            by_layer[l_idx].sort(key=_bary_bwd)
            for pos_idx, nid in enumerate(by_layer[l_idx]):
                order_in_layer[nid] = pos_idx

    # Place nodes: honor pinned nodes first, then incrementally place others.
    occupied_boxes: list[tuple[float, float, float, float]] = []
    placed_nodes: list[dict[str, Any]] = []
    placed_by_id: dict[str, dict[str, Any]] = {}

    for nid in ordered_ids:
        pin = pins.get(nid)
        if pin and pin.get('pinned'):
            node = node_by_id[nid]
            x = float(pin['x'])
            y = float(pin['y'])
            occupied_boxes.append(
                (x, y, x + node['width'], y + node['height'])
            )
            placed = {
                **node,
                'layer': layers[nid],
                'order': order_in_layer[nid],
                'x': x,
                'y': y,
                'pinned': True,
            }
            placed_nodes.append(placed)
            placed_by_id[nid] = placed

    def _overlaps(
        x: float, y: float, w: float, h: float, margin: float = 24.0
    ) -> bool:
        for ox1, oy1, ox2, oy2 in occupied_boxes:
            if not (
                x + w + margin <= ox1
                or ox2 + margin <= x
                or y + h + margin <= oy1
                or oy2 + margin <= y
            ):
                return True
        return False

    for l_idx in sorted_layer_indices:
        cursor_y = 48.0
        base_x = 48.0 + float(l_idx * gap_x)
        for nid in by_layer[l_idx]:
            if nid in placed_by_id:
                continue
            node = node_by_id[nid]
            saved = pins.get(nid)
            if saved and not _overlaps(
                saved['x'], saved['y'], node['width'], node['height']
            ):
                x = float(saved['x'])
                y = float(saved['y'])
            else:
                x = base_x
                y = cursor_y
                while _overlaps(x, y, node['width'], node['height']):
                    y += float(gap_y)
            cursor_y = max(cursor_y, y + node['height'] + 48.0)
            occupied_boxes.append(
                (x, y, x + node['width'], y + node['height'])
            )
            placed = {
                **node,
                'layer': l_idx,
                'order': order_in_layer[nid],
                'x': x,
                'y': y,
                'pinned': False,
            }
            placed_nodes.append(placed)
            placed_by_id[nid] = placed

    placed_nodes.sort(
        key=lambda item: (item['layer'], item['order'], item['id'])
    )

    # Compute orthogonal layered edge waypoints.
    routed_edges: list[dict[str, Any]] = []
    for edge in edges:
        src_node = placed_by_id[edge['source']]
        tgt_node = placed_by_id[edge['target']]
        sx = src_node['x'] + src_node['width']
        sy = src_node['y'] + src_node['height'] / 2.0
        tx = tgt_node['x']
        ty = tgt_node['y'] + tgt_node['height'] / 2.0
        mid_x = round((sx + tx) / 2.0, 2)
        waypoints = [
            {'x': round(sx, 2), 'y': round(sy, 2)},
            {'x': mid_x, 'y': round(sy, 2)},
            {'x': mid_x, 'y': round(ty, 2)},
            {'x': round(tx, 2), 'y': round(ty, 2)},
        ]
        routed_edges.append({
            **edge,
            'points': waypoints,
            'bounds': {
                'min_x': min(p['x'] for p in waypoints),
                'min_y': min(p['y'] for p in waypoints),
                'max_x': max(p['x'] for p in waypoints),
                'max_y': max(p['y'] for p in waypoints),
            },
        })

    if placed_nodes:
        min_x = min(n['x'] for n in placed_nodes)
        min_y = min(n['y'] for n in placed_nodes)
        max_x = max(n['x'] + n['width'] for n in placed_nodes)
        max_y = max(n['y'] + n['height'] for n in placed_nodes)
    else:
        min_x = min_y = 0.0
        max_x = max_y = float(tile_size)

    canvas_bounds = {
        'min_x': round(min_x, 2),
        'min_y': round(min_y, 2),
        'max_x': round(max_x, 2),
        'max_y': round(max_y, 2),
        'width': round(max(1.0, max_x - min_x + 96.0), 2),
        'height': round(max(1.0, max_y - min_y + 96.0), 2),
    }

    # Partition into spatial tiles of tile_size x tile_size.
    min_tx = int(math.floor(min_x / tile_size))
    max_tx = int(math.floor(max_x / tile_size))
    min_ty = int(math.floor(min_y / tile_size))
    max_ty = int(math.floor(max_y / tile_size))

    tiles: list[dict[str, Any]] = []
    for ty in range(min_ty, max_ty + 1):
        for tx in range(min_tx, max_tx + 1):
            bx1 = float(tx * tile_size)
            by1 = float(ty * tile_size)
            bx2 = float((tx + 1) * tile_size)
            by2 = float((ty + 1) * tile_size)
            tile_nodes = [
                n['id']
                for n in placed_nodes
                if not (
                    n['x'] + n['width'] < bx1
                    or n['x'] > bx2
                    or n['y'] + n['height'] < by1
                    or n['y'] > by2
                )
            ]
            tile_edges = [
                e['id']
                for e in routed_edges
                if not (
                    e['bounds']['max_x'] < bx1
                    or e['bounds']['min_x'] > bx2
                    or e['bounds']['max_y'] < by1
                    or e['bounds']['min_y'] > by2
                )
            ]
            if tile_nodes or tile_edges or (tx == min_tx and ty == min_ty):
                tile_key = hashlib.sha256(
                    f'{digest}:{selected_view}:{tile_size}:{tx}:{ty}'.encode(
                        'utf-8'
                    )
                ).hexdigest()[:24]
                tiles.append({
                    'tx': tx,
                    'ty': ty,
                    'tile_key': tile_key,
                    'bounds': {
                        'min_x': bx1,
                        'min_y': by1,
                        'max_x': bx2,
                        'max_y': by2,
                    },
                    'node_ids': tile_nodes,
                    'edge_ids': tile_edges,
                })

    result = {
        'ddn_sha256': digest,
        'view_id': selected_view,
        'algorithm': 'scratchrobin-server-layered@1',
        'tile_size': tile_size,
        'canvas_bounds': canvas_bounds,
        'nodes': placed_nodes,
        'edges': routed_edges,
        'tiles': tiles,
    }
    if use_cache:
        GLOBAL_TILE_CACHE.put(digest, selected_view, tile_size, result)
    return result


def apply_layout_to_ddn_text(
    ddn_text: str, layout: dict[str, Any]
) -> str:
    """Embed server-computed coordinates and pin flags into ``ddn_text``."""
    nodes_by_id = {
        node['id']: node for node in layout.get('nodes', ())
    }
    if not nodes_by_id:
        return ddn_text

    updated = ddn_text
    for nid, node in nodes_by_id.items():
        q_id = nid.replace('"', '""')
        x_str = str(round(float(node['x']), 2))
        y_str = str(round(float(node['y']), 2))
        pin_str = 'true' if node.get('pinned') else 'false'

        # If a companion relations.mapping_<id> record exists, update/add
        # layout_x, layout_y, layout_pinned inside its record block.
        esc_id = re.escape(q_id)
        pattern = re.compile(
            rf'(element\s+"relations\.mapping_{esc_id}"\s+as\s+"record"'
            rf'[\s\S]*?\n\s+record\n\s+subject_id\s+"{esc_id}"\n)'
            rf'(?:\s+layout_x\s+"[^"]*"\n)?'
            rf'(?:\s+layout_y\s+"[^"]*"\n)?'
            rf'(?:\s+layout_pinned\s+"[^"]*"\n)?',
            re.MULTILINE,
        )
        if pattern.search(updated):
            replacement = (
                rf'\g<1>'
                f'                    layout_x "{x_str}"\n'
                f'                    layout_y "{y_str}"\n'
                f'                    layout_pinned "{pin_str}"\n'
            )
            updated = pattern.sub(replacement, updated, count=1)
        else:
            rec_source = ddn.annotation(
                nid,
                node.get('name') or nid,
                f'layout:{nid}',
                {
                    'subject_kind': node.get('role') or 'element',
                    'layout_x': x_str,
                    'layout_y': y_str,
                    'layout_pinned': pin_str,
                },
                'scratchrobin.layout',
            )
            updated = updated.rstrip() + '\n\n' + rec_source
    return updated


def convert_erd_design_engine(
    ddn_text: str,
    *,
    source_engine: str,
    target_engine: str,
    custom_type_map: dict[str, dict[str, Any]] | None = None,
    loss_choices: dict[str, str] | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    """Convert an ERD DDN document from ``source_engine`` to ``target_engine``.

    Implements owner decision D4:
    - Routes every field's data type through the neutral logical level.
    - Applies ``DEFAULT_LOGICAL_TYPE_MAPS[target_engine]`` merged with any
      user-supplied ``custom_type_map`` overrides.
    - Reports lossy items and requires an explicit user choice in
      ``loss_choices`` (keyed by field element ID or field name) when
      ``strict=True``.
    """
    target_key = (target_engine or '').strip().lower()
    if target_key not in DEFAULT_LOGICAL_TYPE_MAPS:
        raise DesignStoreError(
            f'Unsupported target engine for conversion: {target_engine!r}'
        )
    effective_map = copy_type_map(target_key, custom_type_map)
    choices = dict(loss_choices or {})

    blocks = _parse_blocks(ddn_text)
    lossy_items: list[dict[str, Any]] = []
    conversions: list[dict[str, Any]] = []
    unresolved: list[str] = []

    updated = ddn_text
    # Rewrite module comment header if present
    updated = re.sub(
        r'^(//\s*ScratchRobin mapping:\s*scratchrobin\.)'
        r'[a-z0-9_]+(\.relations)',
        rf'\g<1>{target_key}\g<2>',
        updated,
        flags=re.MULTILINE,
    )
    updated = re.sub(
        r'^(\s+module\s+"scratchrobin\.)[a-z0-9_]+(\.relations")',
        rf'\g<1>{target_key}\g<2>',
        updated,
        flags=re.MULTILINE,
    )

    for block in blocks:
        if block['kind'] != 'element' or block['role'] != 'field':
            continue
        field_id = block['id']
        field_name = block['title']
        dt_match = _DATATYPE_RE.search(block['body'])
        if not dt_match:
            continue
        source_dt = dt_match.group(2).replace('""', '"')
        logical_dt = normalize_to_logical_type(source_dt)
        mapping_entry = effective_map.get(
            logical_dt, {'physical': 'TEXT', 'lossy': True}
        )
        target_dt = str(mapping_entry['physical'])
        is_lossy = bool(mapping_entry.get('lossy', False))
        reason = mapping_entry.get('reason') or ''

        choice = choices.get(field_id) or choices.get(field_name)
        if choice and choice.startswith('override:'):
            target_dt = choice.split(':', 1)[1].strip()
        elif is_lossy and strict and choice != 'accept_loss':
            unresolved.append(f'{field_name} ({source_dt} -> {target_dt})')

        if is_lossy:
            lossy_items.append({
                'element_id': field_id,
                'field_name': field_name,
                'source_type': source_dt,
                'logical_type': logical_dt,
                'target_type': target_dt,
                'reason': reason,
                'choice': choice or 'unresolved',
            })

        conversions.append({
            'element_id': field_id,
            'field_name': field_name,
            'source_type': source_dt,
            'logical_type': logical_dt,
            'target_type': target_dt,
            'lossy': is_lossy,
        })

        # Replace datatype in this field block
        q_target = target_dt.replace('"', '""')
        new_body = _DATATYPE_RE.sub(
            rf'\g<1>"{q_target}"', block['body'], count=1
        )
        start, end = block['span']
        header_len = len(ddn_text[start:end]) - len(block['body'])
        header_text = ddn_text[start:start + header_len]
        updated = updated.replace(
            header_text + block['body'], header_text + new_body, 1
        )

    if unresolved and strict:
        raise DesignStoreError(
            'Lossy type conversions require explicit user choices: '
            + ', '.join(unresolved)
        )

    loss_report = {
        'conversion': 'engine-to-engine-via-logical@1',
        'source_engine': source_engine,
        'target_engine': target_key,
        'total_fields_converted': len(conversions),
        'lossy_count': len(lossy_items),
        'lossy_items': lossy_items,
        'conversions': conversions,
    }
    return {
        'ddn_text': updated,
        'loss_report': loss_report,
        'type_map': effective_map,
    }


def copy_type_map(
    target_engine: str,
    custom_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return a copy of the target engine's logical-to-physical type map."""
    base = json.loads(
        json.dumps(DEFAULT_LOGICAL_TYPE_MAPS.get(target_engine, {}))
    )
    if custom_overrides:
        for ltype, spec in custom_overrides.items():
            if isinstance(spec, dict) and 'physical' in spec:
                base[ltype] = {
                    'physical': str(spec['physical']),
                    'lossy': bool(spec.get('lossy', False)),
                    'reason': str(spec.get('reason', '')),
                }
            elif isinstance(spec, str):
                base[ltype] = {
                    'physical': spec,
                    'lossy': False,
                    'reason': '',
                }
    return base


def build_four_level_erd_ddn(
    *,
    title: str,
    conceptual_entities: list[dict[str, Any]] | None = None,
    logical_entities: list[dict[str, Any]] | None = None,
    physical_tables: list[dict[str, Any]] | None = None,
    deployment_nodes: list[dict[str, Any]] | None = None,
    level_links: list[dict[str, str]] | None = None,
    extensions: dict[str, Any] | None = None,
) -> str:
    """Build a multi-level ERD DDN document (conceptual, logical, physical,
    deployment) with opaque extension metadata (D3) and no ORM fields.
    """
    if extensions and any(
        k in extensions
        for k in ('orm_class', 'hibernate_mapping', 'sqlalchemy_mapper')
    ):
        raise DesignStoreError(
            'ORM/application mapping fields are outside ScratchRobin scope; '
            'use opaque extension keys instead'
        )
    parts: list[str] = [ddn.header('scratchrobin.erd.model')]
    level_Buckets: dict[str, list[str]] = {lvl: [] for lvl in ERD_LEVELS}

    def _add_entity(
        item: dict[str, Any], level: str, default_role: str
    ) -> None:
        eid = item.get('id') if is_uuid7(item.get('id')) else uuid7()
        name = str(item.get('name') or item.get('title') or eid)
        role = str(item.get('role') or default_role)
        fields_src = ''
        member_refs = []
        for col in item.get('fields', ()):
            cid = col.get('id') if is_uuid7(col.get('id')) else uuid7()
            cname = str(col.get('name') or cid)
            dtype = str(col.get('datatype') or 'string')
            nullable = bool(col.get('nullable', True))
            f_decl = ddn.native_field(
                cid,
                cname,
                f'erd:{level}:{cid}',
                {'datatype': dtype, 'nullable': nullable},
            )
            fields_src += f_decl['source'] + ddn.annotation(
                cid,
                cname,
                f'erd:{level}:{cid}',
                {
                    'subject_kind': 'field',
                    'parent_id': eid,
                    'modelling_level': level,
                },
                'scratchrobin.erd.model',
            )
            member_refs.append(ddn.ref(cid))

        decl_vals: dict[str, Any] = {'title': name}
        if member_refs:
            decl_vals['members'] = member_refs
        ann_vals: dict[str, Any] = {
            'subject_kind': role,
            'modelling_level': level,
        }
        if item.get('engine'):
            ann_vals['engine'] = str(item['engine'])
        if item.get('host'):
            ann_vals['host'] = str(item['host'])
        if item.get('rack'):
            ann_vals['rack'] = str(item['rack'])
        if item.get('cloud_region'):
            ann_vals['cloud_region'] = str(item['cloud_region'])
        if item.get('instance_type'):
            ann_vals['instance_type'] = str(item['instance_type'])
        if item.get('resource_id'):
            ann_vals['resource_id'] = str(item['resource_id'])
        if extensions:
            ann_vals['extensions_json'] = json.dumps(
                extensions, sort_keys=True
            )
        parts.append(
            fields_src
            + ddn.declaration('element', eid, role, decl_vals)
            + ddn.annotation(
                eid,
                name,
                item.get('uid') or f'erd:{level}:{eid}',
                ann_vals,
                'scratchrobin.erd.model',
            )
        )
        level_Buckets[level].append(eid)

    for ent in conceptual_entities or ():
        _add_entity(ent, 'conceptual', 'table')
    for ent in logical_entities or ():
        _add_entity(ent, 'logical', 'table')
    for tbl in physical_tables or ():
        _add_entity(tbl, 'physical', 'table')
    for dep in deployment_nodes or ():
        _add_entity(dep, 'deployment', dep.get('role') or 'table')

    all_edge_ids: list[str] = []
    for link in level_links or ():
        lid = link.get('id') if is_uuid7(link.get('id')) else uuid7()
        src = link['source']
        tgt = link['target']
        ltitle = str(link.get('title') or f'{src} -> {tgt}')
        parts.append(
            ddn.relation_edge(
                lid,
                ltitle,
                src,
                tgt,
                f'erd:link:{lid}',
                {'link_kind': str(link.get('kind') or 'traces_to')},
                'scratchrobin.erd.model',
            )
        )
        all_edge_ids.append(lid)

    all_nodes = [
        nid for lvl in ERD_LEVELS for nid in level_Buckets[lvl]
    ]
    parts.append(
        ddn.declaration(
            'view',
            'erd_all_levels',
            'ddn@1',
            {
                'title': title,
                'selection': {
                    'include': [
                        ddn.ref(i) for i in (*all_nodes, *all_edge_ids)
                    ]
                },
            },
        )
    )
    for lvl in ERD_LEVELS:
        lvl_nodes = set(level_Buckets[lvl])
        lvl_edges = [
            lid
            for lid, link in zip(all_edge_ids, level_links or ())
            if link['source'] in lvl_nodes and link['target'] in lvl_nodes
        ]
        parts.append(
            ddn.declaration(
                'view',
                f'erd_{lvl}',
                'ddn@1',
                {
                    'title': f'{title} ({lvl})',
                    'selection': {
                        'include': [
                            ddn.ref(i)
                            for i in (*level_Buckets[lvl], *lvl_edges)
                        ]
                    },
                },
            )
        )
    return ''.join(parts)


DESTRUCTIVE_METADATA_WARNING = (
    'Metadata changes may lose data and are not reversible: the metadata can '
    'be recreated, but the data it referred to cannot unless the target '
    'database retains version history (for example ScratchBird). Review the '
    'native operation plan before applying.'
)


def _quote_sql_ident(name: str, engine: str) -> str:
    if engine in ('mysql', 'mariadb'):
        return '`' + name.replace('`', '``') + '`'
    return '"' + name.replace('"', '""') + '"'


def _extract_physical_erd_model(ddn_text: str) -> dict[str, Any]:
    """Extract deployable physical tables, columns and FKs by UUIDv7 ID."""
    if not ddn_text or not ddn_text.strip():
        return {'tables': {}, 'relations': {}}
    blocks = _parse_blocks(ddn_text)
    annotations: dict[str, dict[str, str]] = {}
    for block in blocks:
        if block['kind'] == 'element' and block['role'] == 'record':
            subj = re.search(
                r'^\s+subject_id\s+"((?:[^"]|"")+)"\s*$',
                block['body'],
                re.MULTILINE,
            )
            if subj:
                sid = subj.group(1).replace('""', '"')
                props: dict[str, str] = {}
                for m in re.finditer(
                    r'^\s+([a-zA-Z0-9_]+)\s+"((?:[^"]|"")+)"\s*$',
                    block['body'],
                    re.MULTILINE,
                ):
                    props[m.group(1)] = m.group(2).replace('""', '"')
                annotations[sid] = props

    fields_by_id: dict[str, dict[str, Any]] = {}
    tables_by_id: dict[str, dict[str, Any]] = {}
    relations_by_id: dict[str, dict[str, Any]] = {}

    for block in blocks:
        bid = block['id']
        if block['kind'] == 'element' and block['role'] == 'field':
            title_m = re.search(
                r'^\s+title\s+"((?:[^"]|"")+)"\s*$',
                block['body'],
                re.MULTILINE,
            )
            dtype_m = re.search(
                r'^\s+datatype\s+"((?:[^"]|"")+)"\s*$',
                block['body'],
                re.MULTILINE,
            )
            null_m = re.search(
                r'^\s+nullable\s+(true|false)\s*$',
                block['body'],
                re.MULTILINE,
            )
            ann = annotations.get(bid, {})
            fields_by_id[bid] = {
                'id': bid,
                'name': (
                    title_m.group(1).replace('""', '"') if title_m else bid
                ),
                'datatype': (
                    dtype_m.group(1).replace('""', '"')
                    if dtype_m
                    else 'TEXT'
                ),
                'nullable': (
                    null_m.group(1) == 'true' if null_m else True
                ),
                'parent_id': ann.get('parent_id'),
                'modelling_level': ann.get('modelling_level'),
            }
        elif block['kind'] == 'element' and block['role'] == 'table':
            ann = annotations.get(bid, {})
            lvl = ann.get('modelling_level')
            # Conceptual whiteboard sketches and deployment nodes are not SQL
            # tables (DDN-DB-007).
            if lvl in ('conceptual', 'logical', 'deployment'):
                continue
            title_m = re.search(
                r'^\s+title\s+"((?:[^"]|"")+)"\s*$',
                block['body'],
                re.MULTILINE,
            )
            member_ids = [
                m.group(1).replace('""', '"')
                for m in re.finditer(
                    r'^\s+item\n\s+id\s+"((?:[^"]|"")+)"',
                    block['body'],
                    re.MULTILINE,
                )
            ]
            tables_by_id[bid] = {
                'id': bid,
                'name': (
                    title_m.group(1).replace('""', '"') if title_m else bid
                ),
                'engine': ann.get('engine'),
                'member_ids': member_ids,
                'columns': {},
            }
        elif block['kind'] == 'relation':
            ann = annotations.get(bid, {})
            link_kind = ann.get('link_kind')
            if link_kind in ('traces_to', 'refines', 'implements', 'hosts'):
                continue
            eps = [
                m.group(1).replace('""', '"')
                for m in re.finditer(
                    r'^\s+definition\n\s+id\s+"((?:[^"]|"")+)"',
                    block['body'],
                    re.MULTILINE,
                )
            ]
            title_m = re.search(
                r'^\s+title\s+"((?:[^"]|"")+)"\s*$',
                block['body'],
                re.MULTILINE,
            )
            if len(eps) >= 2:
                relations_by_id[bid] = {
                    'id': bid,
                    'name': (
                        title_m.group(1).replace('""', '"')
                        if title_m
                        else bid
                    ),
                    'source': eps[0],
                    'target': eps[1],
                }

    for fid, fobj in fields_by_id.items():
        pid = fobj.get('parent_id')
        if pid and pid in tables_by_id:
            tables_by_id[pid]['columns'][fid] = fobj

    for tbl in tables_by_id.values():
        for mid in tbl['member_ids']:
            if mid in fields_by_id and mid not in tbl['columns']:
                tbl['columns'][mid] = fields_by_id[mid]

    valid_relations = {
        rid: rel
        for rid, rel in relations_by_id.items()
        if rel['source'] in tables_by_id and rel['target'] in tables_by_id
    }
    return {'tables': tables_by_id, 'relations': valid_relations}


def preview_erd_alter_plan(
    store: DesignStore,
    design_id: str,
    *,
    base_version: int | None = None,
    desired_version: int | None = None,
    selected_difference_ids: list[str] | None = None,
    target_engine: str = 'sqlite',
    catalog_snapshot: dict[str, Any] | None = None,
    handoff_options: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Compare two ERD states by stable UUIDv7 element identity and build a
    reviewable alter plan (owner direction 2026-11-08 & 2026-11-10).

    Never executes statements directly; changes reach a database only through
    ScratchRobin's native-operation review.
    """
    eng = (target_engine or 'sqlite').lower()
    if eng not in DEFAULT_LOGICAL_TYPE_MAPS:
        raise DesignStoreError(f'Unsupported target engine: {target_engine!r}')

    head_design = store.get_design(design_id, version=desired_version)
    des_ver = head_design['version']['version']
    des_ddn = head_design['version']['ddn_text']

    resolved_base_ver = (
        base_version
        if base_version is not None
        else (head_design['active_version'] or 0)
    )
    if resolved_base_ver > 0:
        base_design = store.get_design(design_id, version=resolved_base_ver)
        base_ddn = base_design['version']['ddn_text']
    else:
        base_ddn = ''

    before = _extract_physical_erd_model(base_ddn)
    after = _extract_physical_erd_model(des_ddn)

    differences: list[dict[str, Any]] = []

    # 1. Created, renamed and modified tables + columns
    for tid, t_after in sorted(
        after['tables'].items(), key=lambda item: (item[1]['name'], item[0])
    ):
        t_before = before['tables'].get(tid)
        q_table = _quote_sql_ident(t_after['name'], eng)
        if t_before is None:
            col_defs = []
            for col in t_after['columns'].values():
                q_col = _quote_sql_ident(col['name'], eng)
                nn = '' if col['nullable'] else ' NOT NULL'
                col_defs.append(f'{q_col} {col["datatype"]}{nn}')
            cols_sql = ', '.join(col_defs) if col_defs else 'id INTEGER'
            differences.append({
                'difference_id': f'create_table:{tid}',
                'element_id': tid,
                'change_kind': 'create_table',
                'object_name': t_after['name'],
                'destructive': False,
                'statement': f'CREATE TABLE {q_table} ({cols_sql});',
            })
            continue

        if t_before['name'] != t_after['name']:
            q_old = _quote_sql_ident(t_before['name'], eng)
            differences.append({
                'difference_id': f'rename_table:{tid}',
                'element_id': tid,
                'change_kind': 'rename_table',
                'object_name': f'{t_before["name"]} -> {t_after["name"]}',
                'from_name': t_before['name'],
                'to_name': t_after['name'],
                'destructive': False,
                'statement': (
                    f'ALTER TABLE {q_old} RENAME TO {q_table};'
                ),
            })

        for cid, c_after in sorted(
            t_after['columns'].items(),
            key=lambda item: (item[1]['name'], item[0]),
        ):
            c_before = t_before['columns'].get(cid)
            q_col = _quote_sql_ident(c_after['name'], eng)
            if c_before is None:
                nn = '' if c_after['nullable'] else ' NOT NULL'
                differences.append({
                    'difference_id': f'add_column:{cid}',
                    'element_id': cid,
                    'parent_id': tid,
                    'change_kind': 'add_column',
                    'object_name': f'{t_after["name"]}.{c_after["name"]}',
                    'destructive': False,
                    'statement': (
                        f'ALTER TABLE {q_table} ADD COLUMN '
                        f'{q_col} {c_after["datatype"]}{nn};'
                    ),
                })
                continue

            if c_before['name'] != c_after['name']:
                q_cold = _quote_sql_ident(c_before['name'], eng)
                differences.append({
                    'difference_id': f'rename_column:{cid}',
                    'element_id': cid,
                    'parent_id': tid,
                    'change_kind': 'rename_column',
                    'object_name': (
                        f'{t_after["name"]}.{c_before["name"]} -> '
                        f'{c_after["name"]}'
                    ),
                    'from_name': c_before['name'],
                    'to_name': c_after['name'],
                    'destructive': False,
                    'statement': (
                        f'ALTER TABLE {q_table} RENAME COLUMN '
                        f'{q_cold} TO {q_col};'
                    ),
                })

            if (
                c_before['datatype'] != c_after['datatype']
                or c_before['nullable'] != c_after['nullable']
            ):
                nn = '' if c_after['nullable'] else ' NOT NULL'
                differences.append({
                    'difference_id': f'alter_column:{cid}',
                    'element_id': cid,
                    'parent_id': tid,
                    'change_kind': 'alter_column',
                    'object_name': f'{t_after["name"]}.{c_after["name"]}',
                    'before': {
                        'datatype': c_before['datatype'],
                        'nullable': c_before['nullable'],
                    },
                    'after': {
                        'datatype': c_after['datatype'],
                        'nullable': c_after['nullable'],
                    },
                    'destructive': True,
                    'statement': (
                        f'ALTER TABLE {q_table} ALTER COLUMN '
                        f'{q_col} TYPE {c_after["datatype"]}{nn};'
                    ),
                })

        for cid, c_before in sorted(
            t_before['columns'].items(),
            key=lambda item: (item[1]['name'], item[0]),
        ):
            if cid not in t_after['columns']:
                q_cold = _quote_sql_ident(c_before['name'], eng)
                differences.append({
                    'difference_id': f'drop_column:{cid}',
                    'element_id': cid,
                    'parent_id': tid,
                    'change_kind': 'drop_column',
                    'object_name': f'{t_after["name"]}.{c_before["name"]}',
                    'destructive': True,
                    'statement': (
                        f'ALTER TABLE {q_table} DROP COLUMN {q_cold};'
                    ),
                })

    # 2. Dropped tables
    for tid, t_before in sorted(
        before['tables'].items(), key=lambda item: (item[1]['name'], item[0])
    ):
        if tid not in after['tables']:
            q_old = _quote_sql_ident(t_before['name'], eng)
            differences.append({
                'difference_id': f'drop_table:{tid}',
                'element_id': tid,
                'change_kind': 'drop_table',
                'object_name': t_before['name'],
                'destructive': True,
                'statement': f'DROP TABLE {q_old};',
            })

    # 3. Added and dropped foreign-key relations
    for rid, rel_after in sorted(after['relations'].items()):
        if rid not in before['relations']:
            src_tbl = after['tables'][rel_after['source']]['name']
            tgt_tbl = after['tables'][rel_after['target']]['name']
            differences.append({
                'difference_id': f'add_foreign_key:{rid}',
                'element_id': rid,
                'change_kind': 'add_foreign_key',
                'object_name': f'{src_tbl} -> {tgt_tbl}',
                'destructive': False,
                'statement': (
                    f'-- Review native foreign key {rel_after["name"]}: '
                    f'{_quote_sql_ident(src_tbl, eng)} REFERENCES '
                    f'{_quote_sql_ident(tgt_tbl, eng)}'
                ),
            })

    for rid, rel_before in sorted(before['relations'].items()):
        if rid not in after['relations']:
            src_tbl = before['tables'][rel_before['source']]['name']
            tgt_tbl = before['tables'][rel_before['target']]['name']
            differences.append({
                'difference_id': f'drop_foreign_key:{rid}',
                'element_id': rid,
                'change_kind': 'drop_foreign_key',
                'object_name': f'{src_tbl} -> {tgt_tbl}',
                'destructive': True,
                'statement': (
                    f'-- Review dropping foreign key {rel_before["name"]} '
                    f'on {_quote_sql_ident(src_tbl, eng)}'
                ),
            })

    selected_set = (
        set(selected_difference_ids)
        if selected_difference_ids is not None
        else {d['difference_id'] for d in differences}
    )
    selected_diffs = [
        d for d in differences if d['difference_id'] in selected_set
    ]

    native_handoff = None
    if catalog_snapshot is not None and resolved_base_ver > 0:
        from ..workspace import firebird_relational_review

        orig_ws = ddn_text_to_workspace(
            base_ddn, entry=f'{head_design["key"]}.ddn'
        )
        des_ws = ddn_text_to_workspace(
            des_ddn, entry=f'{head_design["key"]}.ddn'
        )
        native_handoff = firebird_relational_review.handoff(
            catalog_snapshot,
            orig_ws,
            des_ws,
            engine=eng,
            **(handoff_options or {}),
        )

    return {
        'design_id': design_id,
        'base_version': resolved_base_ver,
        'desired_version': des_ver,
        'target_engine': eng,
        'differences': differences,
        'selected_difference_ids': [
            d['difference_id'] for d in selected_diffs
        ],
        'statements': [d['statement'] for d in selected_diffs],
        'script': '\n'.join(d['statement'] for d in selected_diffs),
        'has_destructive_changes': any(
            d['destructive'] for d in selected_diffs
        ),
        'requires_native_review': True,
        'applied_immediately': False,
        'destructive_warning': DESTRUCTIVE_METADATA_WARNING,
        'native_handoff': native_handoff,
    }


def compute_system_diagram_drift(
    ddn_text: str, live_nodes: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare deployment/system diagram elements against live observations.

    Returns a drift overlay classifying bound nodes as ``matched``,
    ``missing_in_live``, ``property_drift`` or ``unmodeled_live``.
    """
    blocks = _parse_blocks(ddn_text)
    info = inspect_ddn_text(ddn_text)
    live_by_id = {
        str(item.get('resource_id') or item.get('id')): item
        for item in (live_nodes or ())
        if isinstance(item, dict)
    }

    annotations: dict[str, dict[str, str]] = {}
    for block in blocks:
        if block['kind'] == 'element' and block['role'] == 'record':
            subj = re.search(
                r'^\s+subject_id\s+"((?:[^"]|"")+)"\s*$',
                block['body'],
                re.MULTILINE,
            )
            if subj:
                sid = subj.group(1).replace('""', '"')
                props: dict[str, str] = {}
                for m in re.finditer(
                    r'^\s+([a-zA-Z0-9_]+)\s+"((?:[^"]|"")+)"\s*$',
                    block['body'],
                    re.MULTILINE,
                ):
                    props[m.group(1)] = m.group(2).replace('""', '"')
                annotations[sid] = props

    matched: list[dict[str, Any]] = []
    missing_in_live: list[dict[str, Any]] = []
    property_drift: list[dict[str, Any]] = []
    seen_live_ids: set[str] = set()

    for elem in info['elements']:
        eid = elem['id']
        ann = annotations.get(eid, {})
        res_id = ann.get('resource_id') or elem.get('resource_id')
        if not res_id:
            continue
        if res_id not in live_by_id:
            missing_in_live.append({
                'element_id': eid,
                'name': elem['name'],
                'resource_id': res_id,
                'status': 'missing_in_live',
            })
            continue
        seen_live_ids.add(res_id)
        live_item = live_by_id[res_id]
        diffs: dict[str, dict[str, Any]] = {}
        for key in ('host', 'rack', 'cloud_region', 'instance_type', 'role'):
            if key in ann and key in live_item:
                if str(ann[key]) != str(live_item[key]):
                    diffs[key] = {
                        'designed': ann[key],
                        'live': live_item[key],
                    }
        if diffs:
            property_drift.append({
                'element_id': eid,
                'name': elem['name'],
                'resource_id': res_id,
                'status': 'property_drift',
                'differences': diffs,
            })
        else:
            matched.append({
                'element_id': eid,
                'name': elem['name'],
                'resource_id': res_id,
                'status': 'matched',
            })

    unmodeled_live = [
        {
            'resource_id': rid,
            'name': str(item.get('name') or rid),
            'status': 'unmodeled_live',
        }
        for rid, item in sorted(live_by_id.items())
        if rid not in seen_live_ids
    ]

    return {
        'has_drift': bool(
            missing_in_live or property_drift or unmodeled_live
        ),
        'matched': matched,
        'missing_in_live': missing_in_live,
        'property_drift': property_drift,
        'unmodeled_live': unmodeled_live,
    }


def propose_system_diagram_change(
    *,
    design_id: str,
    version: int,
    element_id: str,
    action: str,
    parameters: dict[str, Any] | None = None,
    actor_id: int,
) -> dict[str, Any]:
    """Create a native-operation review proposal from a diagram gesture (D1).

    Diagram interactions never execute direct topology or schema actions;
    they return a reviewable change plan with destructive-change warnings.
    """
    if not isinstance(action, str) or not action.strip():
        raise DesignStoreError('Diagram change action is required')
    return {
        'proposal_id': uuid7(),
        'design_id': design_id,
        'version': version,
        'element_id': element_id,
        'action': action.strip(),
        'parameters': dict(parameters or {}),
        'actor_id': actor_id,
        'requires_native_review': True,
        'applied_immediately': False,
        'destructive_warning': (
            'Metadata or topology changes may be destructive and '
            'non-reversible unless the target database retains version '
            'history. Review the native operation plan before applying.'
        ),
    }


class StoreDDNProcess:
    """Shared server-side Store <-> DDN coordinator for all designers."""

    def __init__(
        self,
        store: DesignStore,
        *,
        tile_cache: ServerTileCache | None = None,
    ) -> None:
        self.store = store
        self.tile_cache = tile_cache or GLOBAL_TILE_CACHE

    def open_session(
        self,
        design_id: str,
        *,
        version: int | None = None,
        active_only: bool = False,
        view_id: str | None = None,
        tile_size: int = 1024,
    ) -> dict[str, Any]:
        """Open a design from the store with its DDN workspace, layout, tiles
        and resolved included dependencies.
        """
        design = self.store.get_design(
            design_id, version=version, active_only=active_only
        )
        ver_obj = design['version']
        ddn_text = ver_obj['ddn_text']
        workspace = ddn_text_to_workspace(
            ddn_text,
            entry=f'{design["key"]}.ddn',
            view=view_id,
        )
        layout = compute_server_layout(
            ddn_text,
            view_id=workspace['view'],
            tile_size=tile_size,
        )
        resolved_includes = self.resolve_includes(
            design_id, ver_obj['version']
        )
        bindings = design.get('bindings', ())
        binding_summary = {
            'total': len(bindings),
            'valid': sum(1 for b in bindings if b['state'] == 'valid'),
            'suspect': sum(1 for b in bindings if b['state'] == 'suspect'),
            'unknown': sum(1 for b in bindings if b['state'] == 'unknown'),
        }
        return {
            'design': design,
            'workspace': workspace,
            'layout': layout,
            'resolved_includes': resolved_includes,
            'binding_summary': binding_summary,
        }

    def save_from_ddn(
        self,
        design_id: str,
        *,
        expected_head_version: int,
        ddn_or_workspace: str | dict[str, Any],
        actor_id: int,
        pinned_positions: dict[str, dict[str, Any]] | None = None,
        status: str = 'draft',
        note: str = '',
        origin: str = 'local',
        loss_report: dict[str, Any] | None = None,
        observe_resources: bool = False,
        allow_conflict_note: bool = False,
    ) -> dict[str, Any]:
        """Compute layout on the server, embed it in ``ddn_text``, and save."""
        raw_ddn, _entry, view_id = workspace_to_ddn_text(ddn_or_workspace)
        layout = compute_server_layout(
            raw_ddn,
            view_id=view_id,
            pinned_positions=pinned_positions,
            use_cache=False,
        )
        ddn_with_layout = apply_layout_to_ddn_text(raw_ddn, layout)
        saved = self.store.save_version(
            design_id,
            expected_head_version=expected_head_version,
            ddn_text=ddn_with_layout,
            actor_id=actor_id,
            status=status,
            note=note,
            origin=origin,
            loss_report=loss_report,
            observe_resources=observe_resources,
            allow_conflict_note=allow_conflict_note,
        )
        final_layout = compute_server_layout(
            saved['version']['ddn_text'],
            view_id=view_id,
        )
        return {
            'design': saved,
            'layout': final_layout,
        }

    def include_design(
        self,
        design_id: str,
        version: int,
        *,
        depends_on_design_id: str,
        pin_version: bool = True,
        explicit_version: int | None = None,
    ) -> list[dict[str, Any]]:
        """Add or update an included design dependency (owner decision A10).

        Pins to a specific version by default (``pin_version=True``);
        pass ``pin_version=False`` to opt in to following the target design's
        latest accepted version.
        """
        target = self.store.get_design(depends_on_design_id)
        if pin_version:
            pinned_ver = (
                explicit_version
                if explicit_version is not None
                else (target['active_version'] or target['head_version'])
            )
        else:
            pinned_ver = None

        current_deps = self.store.get_design(
            design_id, version=version
        ).get('dependencies', [])
        merged: list[dict[str, Any]] = [
            d
            for d in current_deps
            if d['depends_on_design_id'] != depends_on_design_id
        ]
        merged.append({
            'depends_on_design_id': depends_on_design_id,
            'depends_on_version': pinned_ver,
        })
        return self.store.set_dependencies(design_id, version, merged)

    def resolve_includes(
        self, design_id: str, version: int
    ) -> list[dict[str, Any]]:
        """Resolve each included design dependency according to A10."""
        design = self.store.get_design(design_id, version=version)
        resolved: list[dict[str, Any]] = []
        for dep in design.get('dependencies', ()):
            dep_id = dep['depends_on_design_id']
            pinned = dep.get('depends_on_version')
            try:
                if pinned is not None:
                    target = self.store.get_design(dep_id, version=pinned)
                    mode = 'pinned'
                else:
                    target = self.store.get_design(dep_id, active_only=True)
                    mode = 'follow_latest_accepted'
                resolved.append({
                    'depends_on_design_id': dep_id,
                    'mode': mode,
                    'resolved_version': target['version']['version'],
                    'title': target['title'],
                    'kind': target['kind'],
                })
            except DesignStoreNotFound:
                resolved.append({
                    'depends_on_design_id': dep_id,
                    'mode': 'unresolved',
                    'resolved_version': pinned,
                })
        return resolved

    def accept_with_policy(
        self,
        design_id: str,
        version: int,
        *,
        actor_id: int,
        has_scratchrobin_permission: bool,
        require_git_review: bool = False,
        git_review_ref: str | None = None,
        comment: str = '',
    ) -> dict[str, Any]:
        """Accept a design version enforcing owner decision A9.

        A ScratchRobin permission is always required; when the project
        enables ``require_git_review``, a Git review reference is also
        required and recorded on the acceptance row.
        """
        if not has_scratchrobin_permission:
            raise DesignStoreForbidden(
                'ScratchRobin acceptance permission is required to accept '
                'a design version'
            )
        if require_git_review and (
            not isinstance(git_review_ref, str) or not git_review_ref.strip()
        ):
            raise DesignStoreForbidden(
                'This project requires a Git review reference before '
                'accepting a design version'
            )
        approval_ref = (
            f'scratchrobin+git:{git_review_ref.strip()}'
            if isinstance(git_review_ref, str) and git_review_ref.strip()
            else f'scratchrobin:user:{actor_id}'
        )
        current = self.store.get_design(design_id, version=version)
        if current['version']['status'] in ('draft', 'in_progress'):
            self.store.advance_status(
                design_id, version, 'in_review', actor_id=actor_id
            )
        return self.store.accept_version(
            design_id,
            version,
            actor_id=actor_id,
            approval_ref=approval_ref,
            authorized=True,
        )
