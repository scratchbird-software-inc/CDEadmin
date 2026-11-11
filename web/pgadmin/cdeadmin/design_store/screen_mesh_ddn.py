##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Screen Mesh Designer Store <-> DDN bridge, redaction & SR-F importer.

Implements the 2026-11-08, 2026-11-09 and 2026-11-10 owner decisions (F1-F4):
- Scope boundary: ScratchRobin designs screen meshes (low-fidelity wireframes
  and annotated screenshots) linked to catalog tables/columns, BI questions,
  dashboards and cubes. Working form builders and executable UI event scripts
  are strictly outside scope and rejected.
- F1: Uses the expanded ``wireframe.ui@1`` profile with ``ui.grid`` (named
  columns), ``ui.dropdown``, ``ui.radio``, ``ui.tabs`` and first-class
  rectangular ``ui.region`` hotspot elements alongside the baseline controls.
- F2: Models screen-to-screen navigation with ``navigation`` relations
  (``control`` or ``ui.region`` -> ``ui.frame`` screen with bounded
  non-executable ``trigger`` / ``action`` metadata) in ``wireframe.ui@1`` and
  emits both per-screen wireframe views and the derived ``screen_flow`` view.
- F3: Discovers and imports ScratchRobin's ``SR-F`` ``ui_descriptors`` forms
  (and optional QA screenshot manifests) as ``Draft`` screen meshes.
- F4: Destructively replaces stored ``asset_blob`` screenshot bytes on region
  redaction so unredacted screenshot bytes are never retained in
  ``designs.db``.
"""

from __future__ import annotations

import base64
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import struct
from typing import Any, Mapping
import zlib

from .ddn_elements import (
    DEFAULT_DIALECT,
    _extract_x_record,
    _parse_blocks,
)
from .identifiers import is_uuid7, uuid7
from .service import (
    DesignStore,
    DesignStoreError,
    DesignStoreNotFound,
)
from .shared_ddn import StoreDDNProcess

SCREEN_MESH_MODULE = 'scratchrobin.screen.mesh@1'
WIREFRAME_PROFILE = 'wireframe.ui@1'

UI_CONTROL_ROLES = frozenset({
    'ui.button',
    'ui.checkbox',
    'ui.dropdown',
    'ui.grid',
    'ui.image',
    'ui.input',
    'ui.label',
    'ui.list',
    'ui.radio',
    'ui.tabs',
})

ALL_WIREFRAME_ROLES = UI_CONTROL_ROLES | frozenset({'ui.frame', 'ui.region'})

ACCESS_MODES = frozenset({'read', 'write', 'read_write'})
NAVIGATION_TRIGGERS = frozenset({'click', 'hover', 'delay'})
NAVIGATION_ACTIONS = frozenset({'navigate', 'back', 'overlay', 'url'})

LOGICAL_BINDING_KINDS = frozenset({
    'table',
    'column',
    'question',
    'dashboard',
    'cube',
    'sql_query',
    'diagram',
    'screen',
})

# Maps logical screen-mesh binding kinds onto designs.db binding.target_kind
# and DDN context element roles.
_BINDING_TARGET_MAP: dict[str, tuple[str, str, str]] = {
    'table': ('resource', 'table', 'binds'),
    'column': ('resource', 'field', 'bindfield'),
    'sql_query': ('resource', 'record', 'binds'),
    'question': ('question', 'saved_view', 'binds'),
    'dashboard': ('dashboard', 'dashboard', 'binds'),
    'cube': ('measure', 'binding', 'binds'),
    'diagram': ('element', 'record', 'binds'),
    'screen': ('element', 'binding', 'binds'),
}

# Working form builders and executable scripts are strictly out of scope.
FORBIDDEN_WORKING_FORM_KEYS = frozenset({
    'event_handler',
    'event_handlers',
    'on_click_script',
    'on_change_script',
    'on_submit_script',
    'javascript',
    'validation_script',
    'submit_sql',
    'crud_endpoint',
    'working_form',
    'executable_code',
})

# Sensitive principals and secrets must never enter DDN text or Git.
FORBIDDEN_SECRET_KEYS = frozenset({
    'users',
    'grants',
    'permissions',
    'recipients',
    'password',
    'api_key',
    'secret',
    'token',
    'smtp_password',
    'webhook_secret',
})

SUPPORTED_SCREENSHOT_MEDIA = frozenset({
    'image/png',
    'image/webp',
})

_PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
_WEBP_RIFF = b'RIFF'


def _q(value: Any) -> str:
    text = str(value if value is not None else '')
    text = text.replace('\r\n', ' ').replace('\n', ' ').replace('\x00', '')
    return '"' + text.replace('"', '""') + '"'


def _json_str(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(',', ':'), ensure_ascii=False
    )


def _alloc_id(id_map: dict[str, str], logical_key: str) -> str:
    existing = id_map.get(logical_key)
    if existing and is_uuid7(existing):
        return existing
    fresh = uuid7()
    id_map[logical_key] = fresh
    return fresh


def _scan_forbidden_keys(payload: Any, path: str = 'mesh') -> None:
    if isinstance(payload, Mapping):
        for raw_key, val in payload.items():
            key = str(raw_key)
            lower = key.lower()
            if lower in FORBIDDEN_WORKING_FORM_KEYS:
                raise DesignStoreError(
                    f'Working form builders and executable UI handlers are '
                    f'outside ScratchRobin Screen Mesh scope ({path}.{key})'
                )
            if lower in FORBIDDEN_SECRET_KEYS:
                raise DesignStoreError(
                    f'Principals, grants and secrets cannot be stored in '
                    f'Screen Mesh DDN ({path}.{key})'
                )
            _scan_forbidden_keys(val, f'{path}.{key}')
    elif isinstance(payload, list):
        for idx, item in enumerate(payload):
            _scan_forbidden_keys(item, f'{path}[{idx}]')


def _slug(value: str, fallback: str = 'item') -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9_-]+', '_', str(value or '').strip()).strip(
        '_'
    )
    return cleaned or fallback


# ---------------------------------------------------------------------------
# Pure-Python PNG synthetic generator & destructive region redactor (F4)
# ---------------------------------------------------------------------------


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
    return (
        struct.pack('>I', len(payload))
        + chunk_type
        + payload
        + struct.pack('>I', crc)
    )


def build_solid_png(
    width: int = 320,
    height: int = 200,
    rgb: tuple[int, int, int] = (241, 245, 249),
    stripe_box: Mapping[str, int] | None = None,
    stripe_rgb: tuple[int, int, int] = (220, 38, 38),
) -> bytes:
    """Create a deterministic 8-bit RGB PNG image using Python stdlib only."""
    w = max(1, min(4096, int(width)))
    h = max(1, min(4096, int(height)))
    r0, g0, b0 = (int(rgb[0]) & 255, int(rgb[1]) & 255, int(rgb[2]) & 255)
    sr, sg, sb = (
        int(stripe_rgb[0]) & 255,
        int(stripe_rgb[1]) & 255,
        int(stripe_rgb[2]) & 255,
    )
    sx0 = sy0 = sx1 = sy1 = -1
    if stripe_box:
        sx0 = max(0, int(stripe_box.get('x', 0)))
        sy0 = max(0, int(stripe_box.get('y', 0)))
        sx1 = min(w, sx0 + max(0, int(stripe_box.get('width', 0))))
        sy1 = min(h, sy0 + max(0, int(stripe_box.get('height', 0))))

    raw = bytearray()
    base_pixel = bytes((r0, g0, b0))
    stripe_pixel = bytes((sr, sg, sb))
    for y in range(h):
        raw.append(0)  # Filter type 0 (None)
        if sy0 <= y < sy1 and sx1 > sx0:
            raw.extend(base_pixel * sx0)
            raw.extend(stripe_pixel * (sx1 - sx0))
            raw.extend(base_pixel * (w - sx1))
        else:
            raw.extend(base_pixel * w)

    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    compressed = zlib.compress(bytes(raw), level=6)
    return (
        _PNG_SIGNATURE
        + _png_chunk(b'IHDR', ihdr)
        + _png_chunk(b'IDAT', compressed)
        + _png_chunk(b'IEND', b'')
    )


def _paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def inspect_image_header(data: bytes, media_type: str) -> dict[str, int]:
    """Validate screenshot header and return ``{width, height}``."""
    mtype = str(media_type or '').strip().lower()
    if mtype not in SUPPORTED_SCREENSHOT_MEDIA:
        raise DesignStoreError(
            f'Unsupported screenshot media_type {media_type!r}; expected '
            f'image/png or image/webp'
        )
    if mtype == 'image/png':
        if (
            len(data) < 24
            or data[:8] != _PNG_SIGNATURE
            or data[12:16] != b'IHDR'
        ):
            raise DesignStoreError('Invalid PNG screenshot header')
        w, h = struct.unpack('>II', data[16:24])
        if w <= 0 or h <= 0:
            raise DesignStoreError('PNG dimensions must be positive')
        return {'width': int(w), 'height': int(h)}

    if len(data) < 30 or data[:4] != _WEBP_RIFF or data[8:12] != b'WEBP':
        raise DesignStoreError('Invalid WebP screenshot header')
    chunk_tag = data[12:16]
    if chunk_tag == b'VP8X' and len(data) >= 30:
        w = 1 + int.from_bytes(data[24:27], 'little')
        h = 1 + int.from_bytes(data[27:30], 'little')
        return {'width': w, 'height': h}
    return {'width': 800, 'height': 600}


def redact_png_regions(
    png_bytes: bytes,
    regions: list[Mapping[str, Any]],
    *,
    fill_rgb: tuple[int, int, int] = (15, 23, 42),
) -> tuple[bytes, dict[str, Any]]:
    """Destructively overwrite rectangular regions in an 8-bit PNG image (F4).

    Decodes PNG scanlines (filters 0..4), overwrites every pixel inside each
    redaction rectangle with ``fill_rgb`` (and opaque alpha when present),
    drops ancillary metadata chunks that could leak thumbnails/EXIF text, and
    re-encodes a clean PNG byte stream.
    """
    if not regions:
        raise DesignStoreError(
            'At least one redaction region {x, y, width, height} is required'
        )
    if len(png_bytes) < 33 or png_bytes[:8] != _PNG_SIGNATURE:
        raise DesignStoreError(
            'Destructive pixel redaction requires a valid PNG image'
        )

    pos = 8
    width = height = bit_depth = color_type = interlace = 0
    plte_payload: bytes | None = None
    idat_parts: list[bytes] = []
    while pos + 8 <= len(png_bytes):
        length = struct.unpack('>I', png_bytes[pos:pos + 4])[0]
        ctype = png_bytes[pos + 4:pos + 8]
        cstart = pos + 8
        cend = cstart + length
        if cend + 4 > len(png_bytes):
            raise DesignStoreError('Truncated PNG chunk in screenshot')
        payload = png_bytes[cstart:cend]
        pos = cend + 4
        if ctype == b'IHDR':
            (
                width,
                height,
                bit_depth,
                color_type,
                _comp,
                _flt,
                interlace,
            ) = struct.unpack('>IIBBBBB', payload)
        elif ctype == b'PLTE':
            plte_payload = payload
        elif ctype == b'IDAT':
            idat_parts.append(payload)
        elif ctype == b'IEND':
            break

    if width <= 0 or height <= 0:
        raise DesignStoreError('PNG IHDR missing or invalid')
    if interlace != 0 or bit_depth != 8:
        raise DesignStoreError(
            'PNG redaction supports non-interlaced 8-bit PNG screenshots'
        )

    channels_by_type = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    if color_type not in channels_by_type:
        raise DesignStoreError(
            f'Unsupported PNG color_type {color_type} for redaction'
        )
    bpp = channels_by_type[color_type]
    stride = width * bpp
    decompressed = zlib.decompress(b''.join(idat_parts))
    expected_len = height * (1 + stride)
    if len(decompressed) < expected_len:
        raise DesignStoreError('Corrupt PNG scanline buffer length')

    # Unfilter all scanlines into flat RGB/RGBA/Gray byte buffer
    rows: list[bytearray] = []
    prev = bytearray(stride)
    offset = 0
    for _y in range(height):
        ftype = decompressed[offset]
        scan = bytearray(decompressed[offset + 1:offset + 1 + stride])
        offset += 1 + stride
        if ftype == 1:  # Sub
            for i in range(bpp, stride):
                scan[i] = (scan[i] + scan[i - bpp]) & 255
        elif ftype == 2:  # Up
            for i in range(stride):
                scan[i] = (scan[i] + prev[i]) & 255
        elif ftype == 3:  # Average
            for i in range(stride):
                left = scan[i - bpp] if i >= bpp else 0
                scan[i] = (scan[i] + ((left + prev[i]) >> 1)) & 255
        elif ftype == 4:  # Paeth
            for i in range(stride):
                left = scan[i - bpp] if i >= bpp else 0
                up = prev[i]
                up_left = prev[i - bpp] if i >= bpp else 0
                scan[i] = (
                    scan[i] + _paeth_predictor(left, up, up_left)
                ) & 255
        elif ftype != 0:
            raise DesignStoreError(f'Unsupported PNG filter type {ftype}')
        rows.append(scan)
        prev = scan

    # Convert palette-indexed PNG (color_type 3) to truecolor RGB
    # (color_type 2) before redacting so palette entries never retain colors.
    if color_type == 3:
        if not plte_payload or len(plte_payload) < 3:
            raise DesignStoreError('Indexed PNG is missing PLTE palette')
        rgb_rows: list[bytearray] = []
        for scan in rows:
            rgb_row = bytearray(width * 3)
            for x in range(width):
                idx = scan[x] * 3
                if idx + 3 <= len(plte_payload):
                    rgb_row[x * 3:x * 3 + 3] = plte_payload[idx:idx + 3]
            rgb_rows.append(rgb_row)
        rows = rgb_rows
        color_type = 2
        bpp = 3
        stride = width * 3

    fr, fg, fb = (
        int(fill_rgb[0]) & 255,
        int(fill_rgb[1]) & 255,
        int(fill_rgb[2]) & 255,
    )
    lum = int(round(0.299 * fr + 0.587 * fg + 0.114 * fb)) & 255
    if color_type == 0:
        fill_pixel = bytes((lum,))
    elif color_type == 4:
        fill_pixel = bytes((lum, 255))
    elif color_type == 2:
        fill_pixel = bytes((fr, fg, fb))
    else:
        fill_pixel = bytes((fr, fg, fb, 255))

    applied_boxes: list[dict[str, int]] = []
    pixels_redacted = 0
    for reg in regions:
        rx = max(0, min(width, int(round(float(reg.get('x', 0))))))
        ry = max(0, min(height, int(round(float(reg.get('y', 0))))))
        rw = max(0, int(round(float(reg.get('width', reg.get('w', 0))))))
        rh = max(0, int(round(float(reg.get('height', reg.get('h', 0))))))
        rx2 = max(rx, min(width, rx + rw))
        ry2 = max(ry, min(height, ry + rh))
        span_w = rx2 - rx
        span_h = ry2 - ry
        if span_w <= 0 or span_h <= 0:
            continue
        replacement = fill_pixel * span_w
        byte_x0 = rx * bpp
        byte_x1 = rx2 * bpp
        for y in range(ry, ry2):
            rows[y][byte_x0:byte_x1] = replacement
        pixels_redacted += span_w * span_h
        applied_boxes.append({
            'x': rx,
            'y': ry,
            'width': span_w,
            'height': span_h,
        })

    if not applied_boxes:
        raise DesignStoreError(
            'Redaction regions did not overlap any screenshot pixels'
        )

    out_raw = bytearray()
    for scan in rows:
        out_raw.append(0)
        out_raw.extend(scan)
    ihdr_out = struct.pack(
        '>IIBBBBB', width, height, 8, color_type, 0, 0, 0
    )
    encoded = (
        _PNG_SIGNATURE
        + _png_chunk(b'IHDR', ihdr_out)
        + _png_chunk(b'IDAT', zlib.compress(bytes(out_raw), level=6))
        + _png_chunk(b'IEND', b'')
    )
    return encoded, {
        'width': width,
        'height': height,
        'applied_regions': applied_boxes,
        'pixels_redacted': pixels_redacted,
    }


def read_png_pixel_rgb(png_bytes: bytes, x: int, y: int) -> tuple[int, ...]:
    """Read a single pixel from a non-interlaced 8-bit filter-0 PNG."""
    pos = 8
    width = height = color_type = 0
    idat_parts: list[bytes] = []
    while pos + 8 <= len(png_bytes):
        length = struct.unpack('>I', png_bytes[pos:pos + 4])[0]
        ctype = png_bytes[pos + 4:pos + 8]
        payload = png_bytes[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b'IHDR':
            width, height, _bd, color_type, *_ = struct.unpack(
                '>IIBBBBB', payload
            )
        elif ctype == b'IDAT':
            idat_parts.append(payload)
        elif ctype == b'IEND':
            break
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    stride = width * bpp
    raw = zlib.decompress(b''.join(idat_parts))
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError('Pixel coordinate out of bounds')
    row_start = y * (1 + stride)
    if raw[row_start] != 0:
        # Run through zero-region no-op decode path via redact helper logic
        raise ValueError('Expected filter-0 PNG in pixel probe')
    px_start = row_start + 1 + x * bpp
    return tuple(raw[px_start:px_start + bpp])


# ---------------------------------------------------------------------------
# Screen Mesh canonical model validation & DDN round-trip (F1, F2)
# ---------------------------------------------------------------------------


def default_screen_mesh_model(
    name: str = 'New Screen Mesh',
    *,
    form_reference: str | None = None,
    screens: list[dict[str, Any]] | None = None,
    controls: list[dict[str, Any]] | None = None,
    regions: list[dict[str, Any]] | None = None,
    bindings: list[dict[str, Any]] | None = None,
    navigations: list[dict[str, Any]] | None = None,
    notes: str = '',
) -> dict[str, Any]:
    """Build and validate a canonical Screen Mesh model."""
    title = str(name or 'New Screen Mesh').strip() or 'New Screen Mesh'
    if screens is None:
        main_screen_id = uuid7()
        screens_in: list[dict[str, Any]] = [{
            'id': main_screen_id,
            'name': title,
            'width': 960,
            'height': 640,
            'form_reference': form_reference or '',
            'screenshot_path': '',
            'screenshot_sha256': '',
            'notes': '',
        }]
    else:
        screens_in = list(screens)

    return validate_screen_mesh({
        'name': title,
        'screens': screens_in,
        'controls': list(controls or []),
        'regions': list(regions or []),
        'bindings': list(bindings or []),
        'navigations': list(navigations or []),
        'notes': str(notes or ''),
    })


def validate_screen_mesh(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a Screen Mesh payload, enforcing scope."""
    if not isinstance(raw, Mapping):
        raise DesignStoreError('Screen mesh payload must be a JSON object')
    _scan_forbidden_keys(raw)

    name = str(raw.get('name') or 'Screen Mesh').strip() or 'Screen Mesh'
    raw_screens = list(raw.get('screens') or [])
    if not raw_screens:
        raise DesignStoreError(
            'Screen mesh requires at least one ui.frame screen'
        )

    screens: list[dict[str, Any]] = []
    screen_ids: set[str] = set()
    for idx, sraw in enumerate(raw_screens, start=1):
        if not isinstance(sraw, Mapping):
            raise DesignStoreError('Each screen entry must be an object')
        sid = str(sraw.get('id') or '').strip()
        if not is_uuid7(sid):
            sid = uuid7()
        if sid in screen_ids:
            raise DesignStoreError(f'Duplicate screen id: {sid!r}')
        screen_ids.add(sid)
        sname = (
            str(sraw.get('name') or f'Screen {idx}').strip()
            or f'Screen {idx}'
        )
        screens.append({
            'id': sid,
            'name': sname,
            'width': max(120, int(sraw.get('width') or 960)),
            'height': max(80, int(sraw.get('height') or 640)),
            'form_reference': str(sraw.get('form_reference') or '').strip(),
            'screenshot_path': str(sraw.get('screenshot_path') or '').strip(),
            'screenshot_sha256': str(
                sraw.get('screenshot_sha256') or ''
            ).strip(),
            'notes': str(sraw.get('notes') or '').strip(),
        })

    default_screen_id = screens[0]['id']
    controls: list[dict[str, Any]] = []
    control_ids: set[str] = set()
    column_owner_ids: dict[str, str] = {}

    for idx, craw in enumerate(raw.get('controls') or [], start=1):
        if not isinstance(craw, Mapping):
            raise DesignStoreError('Each control entry must be an object')
        role = str(craw.get('role') or 'ui.input').strip()
        if not role.startswith('ui.'):
            role = f'ui.{role}'
        if role not in UI_CONTROL_ROLES:
            raise DesignStoreError(
                f'Unsupported wireframe control role {role!r}; admitted '
                f'roles: {sorted(UI_CONTROL_ROLES)}'
            )
        cid = str(craw.get('id') or '').strip()
        if not is_uuid7(cid):
            cid = uuid7()
        if cid in control_ids or cid in screen_ids:
            raise DesignStoreError(f'Duplicate element id: {cid!r}')
        control_ids.add(cid)

        owner_screen = str(
            craw.get('screen_id') or default_screen_id
        ).strip()
        if owner_screen not in screen_ids:
            raise DesignStoreError(
                f'Control {cid!r} references unknown screen_id '
                f'{owner_screen!r}'
            )

        columns_out: list[dict[str, Any]] = []
        if role == 'ui.grid':
            for cidx, col in enumerate(craw.get('columns') or [], start=1):
                if isinstance(col, str):
                    col_id = f'col_{cidx}'
                    col_name = col.strip() or col_id
                    col_w = 120
                    col_dt = 'text'
                elif isinstance(col, Mapping):
                    col_id = _slug(
                        str(col.get('id') or col.get('name') or f'col_{cidx}'),
                        f'col_{cidx}',
                    )
                    col_name = (
                        str(col.get('name') or col_id).strip() or col_id
                    )
                    col_w = max(40, int(col.get('width') or 120))
                    col_dt = str(col.get('datatype') or 'text').strip()
                else:
                    raise DesignStoreError('Invalid ui.grid column entry')
                columns_out.append({
                    'id': col_id,
                    'name': col_name,
                    'width': col_w,
                    'datatype': col_dt,
                })
                column_owner_ids[f'{cid}:{col_id}'] = cid

        options_out = [
            str(o).strip()
            for o in (craw.get('options') or [])
            if str(o).strip()
        ]
        controls.append({
            'id': cid,
            'screen_id': owner_screen,
            'role': role,
            'name': (
                str(craw.get('name') or f'Control {idx}').strip()
                or f'Control {idx}'
            ),
            'placeholder': str(craw.get('placeholder') or '').strip(),
            'checked': bool(craw.get('checked', False)),
            'options': options_out,
            'columns': columns_out,
            'field_id': str(craw.get('field_id') or '').strip(),
            'tab': str(craw.get('tab') or '').strip(),
            'notes': str(craw.get('notes') or '').strip(),
        })

    regions: list[dict[str, Any]] = []
    region_ids: set[str] = set()
    for idx, rraw in enumerate(raw.get('regions') or [], start=1):
        if not isinstance(rraw, Mapping):
            raise DesignStoreError('Each ui.region entry must be an object')
        rid = str(rraw.get('id') or '').strip()
        if not is_uuid7(rid):
            rid = uuid7()
        if rid in region_ids or rid in control_ids or rid in screen_ids:
            raise DesignStoreError(f'Duplicate region id: {rid!r}')
        region_ids.add(rid)

        owner_screen = str(
            rraw.get('screen_id') or default_screen_id
        ).strip()
        if owner_screen not in screen_ids:
            raise DesignStoreError(
                f'Region {rid!r} references unknown screen_id '
                f'{owner_screen!r}'
            )
        braw = rraw.get('bounds') or {}
        if not isinstance(braw, Mapping):
            raise DesignStoreError('ui.region.bounds must be an object')
        bx = float(braw.get('x', 0))
        by = float(braw.get('y', 0))
        bw = float(braw.get('width', braw.get('w', 120)))
        bh = float(braw.get('height', braw.get('h', 48)))
        if bw <= 0 or bh <= 0:
            raise DesignStoreError(
                'ui.region bounds width and height must be positive'
            )
        regions.append({
            'id': rid,
            'screen_id': owner_screen,
            'role': 'ui.region',
            'name': (
                str(rraw.get('name') or f'Region {idx}').strip()
                or f'Region {idx}'
            ),
            'bounds': {
                'x': round(bx, 2),
                'y': round(by, 2),
                'width': round(bw, 2),
                'height': round(bh, 2),
            },
            'notes': str(rraw.get('notes') or '').strip(),
        })

    bindable_ids = screen_ids | control_ids | region_ids
    bindings: list[dict[str, Any]] = []
    seen_bind_ids: set[str] = set()
    for braw in raw.get('bindings') or []:
        if not isinstance(braw, Mapping):
            raise DesignStoreError('Each binding entry must be an object')
        bid = str(braw.get('id') or '').strip()
        if not is_uuid7(bid):
            bid = uuid7()
        if bid in seen_bind_ids:
            raise DesignStoreError(f'Duplicate binding id: {bid!r}')
        seen_bind_ids.add(bid)

        src_id = str(braw.get('source_id') or '').strip()
        col_id = str(braw.get('column_id') or '').strip()
        if src_id not in bindable_ids:
            raise DesignStoreError(
                f'Binding {bid!r} source_id {src_id!r} does not match any '
                f'screen, control or ui.region'
            )
        if col_id and f'{src_id}:{col_id}' not in column_owner_ids:
            raise DesignStoreError(
                f'Binding {bid!r} column_id {col_id!r} is not declared on '
                f'grid {src_id!r}'
            )

        lkind = str(braw.get('target_kind') or 'column').strip().lower()
        if lkind not in LOGICAL_BINDING_KINDS:
            raise DesignStoreError(
                f'Unsupported screen mesh binding target_kind {lkind!r}; '
                f'expected one of {sorted(LOGICAL_BINDING_KINDS)}'
            )
        tref = str(braw.get('target_ref') or '').strip()
        if not tref:
            raise DesignStoreError(
                f'Binding {bid!r} requires a non-empty target_ref'
            )
        access = str(braw.get('access_mode') or 'read').strip().lower()
        if access not in ACCESS_MODES:
            raise DesignStoreError(
                f'Unsupported access_mode {access!r}; expected '
                f'{sorted(ACCESS_MODES)}'
            )
        bindings.append({
            'id': bid,
            'source_id': src_id,
            'column_id': col_id,
            'target_kind': lkind,
            'target_ref': tref,
            'access_mode': access,
            'target_engine': (
                str(braw['target_engine']).strip()
                if braw.get('target_engine')
                else None
            ),
            'target_endpoint_id': (
                str(braw['target_endpoint_id']).strip()
                if braw.get('target_endpoint_id')
                else None
            ),
            'target_database_target_id': (
                str(braw['target_database_target_id']).strip()
                if braw.get('target_database_target_id')
                else None
            ),
            'notes': str(braw.get('notes') or '').strip(),
        })

    navigations: list[dict[str, Any]] = []
    seen_nav_ids: set[str] = set()
    for nraw in raw.get('navigations') or []:
        if not isinstance(nraw, Mapping):
            raise DesignStoreError('Each navigation entry must be an object')
        nid = str(nraw.get('id') or '').strip()
        if not is_uuid7(nid):
            nid = uuid7()
        if nid in seen_nav_ids:
            raise DesignStoreError(f'Duplicate navigation id: {nid!r}')
        seen_nav_ids.add(nid)

        from_id = str(nraw.get('from_id') or '').strip()
        to_screen_id = str(nraw.get('to_screen_id') or '').strip()
        if from_id not in bindable_ids:
            raise DesignStoreError(
                f'Navigation {nid!r} from_id {from_id!r} does not match any '
                f'screen, control or ui.region'
            )
        if to_screen_id not in screen_ids:
            raise DesignStoreError(
                f'Navigation {nid!r} to_screen_id {to_screen_id!r} must '
                f'reference a ui.frame screen'
            )
        trigger = str(nraw.get('trigger') or 'click').strip().lower()
        if trigger not in NAVIGATION_TRIGGERS:
            raise DesignStoreError(
                f'Unsupported navigation trigger {trigger!r}; expected '
                f'{sorted(NAVIGATION_TRIGGERS)}'
            )
        action = str(nraw.get('action') or 'navigate').strip().lower()
        if action not in NAVIGATION_ACTIONS:
            raise DesignStoreError(
                f'Unsupported navigation action {action!r}; expected '
                f'{sorted(NAVIGATION_ACTIONS)}'
            )
        delay_ms = max(0, int(nraw.get('delay_ms') or 0))
        url = str(nraw.get('url') or '').strip()
        label = (
            str(nraw.get('label') or f'{trigger} -> {action}').strip()
            or f'{trigger} -> {action}'
        )
        navigations.append({
            'id': nid,
            'from_id': from_id,
            'to_screen_id': to_screen_id,
            'trigger': trigger,
            'action': action,
            'delay_ms': delay_ms,
            'url': url,
            'label': label,
        })

    return {
        'name': name,
        'screens': screens,
        'controls': controls,
        'regions': regions,
        'bindings': bindings,
        'navigations': navigations,
        'notes': str(raw.get('notes') or '').strip(),
    }


def _emit_companion_record(
    lines: list[str],
    record_id: str,
    *,
    block_kind: str,
    subject_id: str,
    logical_name: str,
    fields: Mapping[str, str],
    position: Mapping[str, float] | None = None,
) -> None:
    lines.extend([
        f'element {_q(record_id)} as "record"',
        '    with',
        f'        id {_q(record_id)}',
        f'        title {_q(f"{block_kind}:{logical_name}")}',
        '        metadata',
        '            x_record',
        f'                module {_q(SCREEN_MESH_MODULE)}',
        f'                block {_q(block_kind)}',
        f'                name_json {_q(json.dumps(logical_name))}',
        '                record',
        f'                    subject_id {_q(subject_id)}',
    ])
    if position and 'x' in position and 'y' in position:
        lines.append(
            f'                    pos_x {_q(str(float(position["x"])))}'
        )
        lines.append(
            f'                    pos_y {_q(str(float(position["y"])))}'
        )
    for key, val in sorted(fields.items()):
        lines.append(f'                    {key} {_q(val)}')
    lines.append('')


def _emit_view_block(
    lines: list[str],
    view_id: str,
    title: str,
    include_ids: list[str],
) -> None:
    lines.extend([
        f'view {_q(view_id)} as {_q(WIREFRAME_PROFILE)}',
        '    with',
        f'        id {_q(view_id)}',
        f'        title {_q(title)}',
        '        selection',
    ])
    if not include_ids:
        lines.append('            include empty list')
    else:
        lines.append('            include')
        for inc_id in include_ids:
            lines.extend([
                '                item',
                f'                    id {_q(inc_id)}',
            ])
    lines.append('')


def screen_mesh_to_ddn(
    mesh_raw: Mapping[str, Any],
    *,
    element_ids: Mapping[str, str] | None = None,
    layout_positions: Mapping[str, Mapping[str, float]] | None = None,
) -> tuple[str, dict[str, str]]:
    """Serialize a validated Screen Mesh losslessly into ``ddn-next-1``."""
    mesh = validate_screen_mesh(mesh_raw)
    id_map: dict[str, str] = dict(element_ids or {})
    pos_map = dict(layout_positions or {})

    lines: list[str] = [
        f'version {DEFAULT_DIALECT}',
        f'// ScratchRobin module: {SCREEN_MESH_MODULE}',
        '',
    ]

    main_items: list[str] = []
    per_screen_items: dict[str, list[str]] = {
        s['id']: [s['id']] for s in mesh['screens']
    }

    # Pre-index column bindings so ui.grid columns carry binding_id in x_ui
    col_binding_lookup: dict[tuple[str, str], str] = {}
    source_access_lookup: dict[str, str] = {}
    for bnd in mesh['bindings']:
        source_access_lookup[bnd['source_id']] = bnd['access_mode']
        if bnd.get('column_id'):
            col_binding_lookup[(bnd['source_id'], bnd['column_id'])] = (
                bnd['id']
            )

    # 1. Emit ui.frame screens
    for scr in mesh['screens']:
        sid = scr['id']
        id_map[f'screen:{sid}'] = sid
        main_items.append(sid)
        lines.extend([
            f'element {_q(sid)} as "ui.frame"',
            '    with',
            f'        id {_q(sid)}',
            f'        title {_q(scr["name"])}',
        ])
        has_x_ui = bool(scr['form_reference'] or scr['screenshot_path'])
        if has_x_ui:
            lines.extend([
                '        metadata',
                '            x_ui',
            ])
            if scr['form_reference']:
                lines.append(
                    f'                form_reference '
                    f'{_q(scr["form_reference"])}'
                )
            if scr['screenshot_path']:
                # Reference the logical asset path in DDN so destructive F4
                # blob replacement never leaves old SHA-256 digests in history.
                lines.append(
                    f'                asset_sha256 '
                    f'{_q(scr["screenshot_path"])}'
                )
        if scr['notes']:
            lines.append(f'        description {_q(scr["notes"])}')
        lines.append('')

    # 2. Emit ui.* controls
    control_screen_of: dict[str, str] = {}
    for ctrl in mesh['controls']:
        cid = ctrl['id']
        owner_sid = ctrl['screen_id']
        control_screen_of[cid] = owner_sid
        id_map[f'control:{cid}'] = cid
        main_items.append(cid)
        per_screen_items[owner_sid].append(cid)

        lines.extend([
            f'element {_q(cid)} as {_q(ctrl["role"])}',
            '    with',
            f'        id {_q(cid)}',
            f'        title {_q(ctrl["name"])}',
            '        metadata',
            '            x_diagram',
            f'                owner {_q(owner_sid)}',
        ])
        need_x_ui = (
            bool(ctrl['placeholder'])
            or ctrl['role'] in ('ui.checkbox', 'ui.radio')
            or bool(ctrl['options'])
            or bool(ctrl['columns'])
            or cid in source_access_lookup
        )
        if need_x_ui:
            lines.append('            x_ui')
            if ctrl['role'] in ('ui.checkbox', 'ui.radio'):
                lines.append(
                    f'                checked '
                    f'{"true" if ctrl["checked"] else "false"}'
                )
            if ctrl['placeholder']:
                lines.append(
                    f'                placeholder {_q(ctrl["placeholder"])}'
                )
            if cid in source_access_lookup:
                lines.append(
                    f'                access_mode '
                    f'{_q(source_access_lookup[cid])}'
                )
            if ctrl['options']:
                lines.append('                options')
                for opt in ctrl['options']:
                    lines.append(f'                    item {_q(opt)}')
            if ctrl['columns']:
                lines.append('                columns')
                for col in ctrl['columns']:
                    lines.extend([
                        '                    item',
                        f'                        id {_q(col["id"])}',
                        f'                        name {_q(col["name"])}',
                        f'                        width {int(col["width"])}',
                        f'                        datatype '
                        f'{_q(col["datatype"])}',
                    ])
                    cbid = col_binding_lookup.get((cid, col['id']))
                    if cbid:
                        lines.append(
                            f'                        binding_id {_q(cbid)}'
                        )
        if ctrl['notes']:
            lines.append(f'        description {_q(ctrl["notes"])}')
        lines.append('')

    # 3. Emit first-class ui.region screenshot hotspot elements (F1)
    for reg in mesh['regions']:
        rid = reg['id']
        owner_sid = reg['screen_id']
        control_screen_of[rid] = owner_sid
        id_map[f'region:{rid}'] = rid
        main_items.append(rid)
        per_screen_items[owner_sid].append(rid)
        b = reg['bounds']
        lines.extend([
            f'element {_q(rid)} as "ui.region"',
            '    with',
            f'        id {_q(rid)}',
            f'        title {_q(reg["name"])}',
            '        metadata',
            '            x_diagram',
            f'                owner {_q(owner_sid)}',
            '            x_ui',
        ])
        if rid in source_access_lookup:
            lines.append(
                f'                access_mode {_q(source_access_lookup[rid])}'
            )
        lines.extend([
            '                bounds',
            f'                    x {json.dumps(b["x"])}',
            f'                    y {json.dumps(b["y"])}',
            f'                    width {json.dumps(b["width"])}',
            f'                    height {json.dumps(b["height"])}',
        ])
        if reg['notes']:
            lines.append(f'        description {_q(reg["notes"])}')
        lines.append('')

    # 4. Emit context target nodes & binds / bindfield relations
    target_node_by_key: dict[tuple[str, str], str] = {}
    for bnd in mesh['bindings']:
        lkind = bnd['target_kind']
        tref = bnd['target_ref']
        _store_kind, ctx_role, rel_role = _BINDING_TARGET_MAP[lkind]
        tkey = (lkind, tref)
        target_el_id = target_node_by_key.get(tkey)
        if target_el_id is None:
            target_el_id = _alloc_id(id_map, f'target:{lkind}:{tref}')
            target_node_by_key[tkey] = target_el_id
            main_items.append(target_el_id)
            lines.extend([
                f'element {_q(target_el_id)} as {_q(ctx_role)}',
                '    with',
                f'        id {_q(target_el_id)}',
                f'        title {_q(tref)}',
                '',
            ])
        owner_sid = control_screen_of.get(bnd['source_id'], bnd['source_id'])
        if (
            owner_sid in per_screen_items
            and target_el_id not in per_screen_items[owner_sid]
        ):
            per_screen_items[owner_sid].append(target_el_id)

        rel_id = bnd['id']
        id_map[f'binding:{rel_id}'] = rel_id
        main_items.append(rel_id)
        if owner_sid in per_screen_items:
            per_screen_items[owner_sid].append(rel_id)
        col_suffix = f".{bnd['column_id']}" if bnd['column_id'] else ''
        rel_title = f"{bnd['access_mode']}{col_suffix} -> {tref}"
        lines.extend([
            f'relation {_q(rel_id)} as {_q(rel_role)}',
            f'    endpoint {_q(bnd["source_id"])}',
            f'    endpoint {_q(target_el_id)}',
            '    with',
            f'        id {_q(rel_id)}',
            f'        title {_q(rel_title)}',
            '',
        ])

    # 5. Emit bounded non-executable navigation relations (F2)
    flow_items: list[str] = [s['id'] for s in mesh['screens']]
    for nav in mesh['navigations']:
        nid = nav['id']
        id_map[f'nav:{nid}'] = nid
        main_items.append(nid)
        if nav['from_id'] not in flow_items:
            flow_items.append(nav['from_id'])
        flow_items.append(nid)
        lines.extend([
            f'relation {_q(nid)} as "navigation"',
            f'    endpoint {_q(nav["from_id"])}',
            f'    endpoint {_q(nav["to_screen_id"])}',
            '    with',
            f'        id {_q(nid)}',
            f'        title {_q(nav["label"])}',
            '        metadata',
            '            x_ui',
            f'                trigger {_q(nav["trigger"])}',
            f'                action {_q(nav["action"])}',
        ])
        if nav['delay_ms'] > 0:
            lines.append(f'                delay_ms {int(nav["delay_ms"])}')
        if nav['url']:
            lines.append(f'                url {_q(nav["url"])}')
        lines.append('')

    # 6. Companion envelope record (outside wireframe views so round-trip is
    #    100% lossless while views stay pure wireframe.ui@1)
    #    Note: screenshot_sha256 is stripped from the immutable DDN text
    #    envelope and resolved live from design_asset so F4 redaction never
    #    leaves unredacted blob hashes in design_version.ddn_text.
    sanitized_mesh = copy.deepcopy(mesh)
    for scr in sanitized_mesh['screens']:
        scr['screenshot_sha256'] = ''
    root_rec_id = _alloc_id(id_map, 'record:screen_mesh:root')
    envelope = {
        'mesh': sanitized_mesh,
        'element_ids': dict(id_map),
        'layout_positions': {
            k: {'x': float(v['x']), 'y': float(v['y'])}
            for k, v in pos_map.items()
            if isinstance(v, Mapping) and 'x' in v and 'y' in v
        },
    }
    envelope_b64 = base64.b64encode(
        _json_str(envelope).encode('utf-8')
    ).decode('ascii')
    _emit_companion_record(
        lines,
        root_rec_id,
        block_kind='screen_mesh_root',
        subject_id=mesh['screens'][0]['id'],
        logical_name=mesh['name'],
        fields={'envelope_b64': envelope_b64},
        position=pos_map.get(mesh['screens'][0]['id']),
    )

    # 7. Emit main wireframe view, per-screen views, and derived screen_flow
    _emit_view_block(lines, 'screen_mesh_main', mesh['name'], main_items)
    if len(mesh['screens']) > 1:
        for idx, scr in enumerate(mesh['screens'], start=1):
            _emit_view_block(
                lines,
                f'screen_{idx}',
                f'Screen: {scr["name"]}',
                per_screen_items[scr['id']],
            )
    _emit_view_block(
        lines,
        'screen_flow',
        f'{mesh["name"]} — Screen Flow',
        flow_items,
    )

    return '\n'.join(lines).rstrip() + '\n', id_map


def ddn_to_screen_mesh(ddn_text: str) -> dict[str, Any]:
    """Parse a Screen Mesh DDN document back into its canonical model."""
    blocks = _parse_blocks(ddn_text)
    for blk in blocks:
        xrec = _extract_x_record(blk)
        if not xrec:
            continue
        if (
            xrec.get('module') == SCREEN_MESH_MODULE
            and xrec.get('block') == 'screen_mesh_root'
        ):
            rec_fields = xrec.get('record') or {}
            raw_b64 = rec_fields.get('envelope_b64')
            raw_env = rec_fields.get('envelope_json')
            if raw_b64:
                decoded = base64.b64decode(raw_b64).decode('utf-8')
                parsed = json.loads(decoded)
            elif raw_env:
                parsed = json.loads(raw_env)
            else:
                parsed = None
            if parsed is not None:
                mesh = validate_screen_mesh(parsed['mesh'])
                return {
                    'mesh': mesh,
                    'element_ids': dict(parsed.get('element_ids') or {}),
                    'layout_positions': dict(
                        parsed.get('layout_positions') or {}
                    ),
                }

    # Fallback parser for hand-written wireframe.ui@1 DDN documents
    screens: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    regions: list[dict[str, Any]] = []
    for blk in blocks:
        if blk.get('kind') != 'element':
            continue
        role = str(blk.get('role') or '')
        eid = str(blk.get('id') or '')
        title = str(blk.get('title') or eid)
        if role == 'ui.frame':
            screens.append({
                'id': eid if is_uuid7(eid) else uuid7(),
                'name': title,
                'width': 960,
                'height': 640,
            })
        elif role == 'ui.region':
            regions.append({
                'id': eid if is_uuid7(eid) else uuid7(),
                'name': title,
                'bounds': {'x': 0, 'y': 0, 'width': 120, 'height': 48},
            })
        elif role in UI_CONTROL_ROLES:
            controls.append({
                'id': eid if is_uuid7(eid) else uuid7(),
                'role': role,
                'name': title,
            })
    if not screens:
        raise DesignStoreError(
            'DDN document does not contain a valid Screen Mesh'
        )
    if controls or regions:
        first_sid = screens[0]['id']
        for c in controls:
            c['screen_id'] = first_sid
        for r in regions:
            r['screen_id'] = first_sid
    mesh = validate_screen_mesh({
        'name': screens[0]['name'],
        'screens': screens,
        'controls': controls,
        'regions': regions,
    })
    return {'mesh': mesh, 'element_ids': {}, 'layout_positions': {}}


# ---------------------------------------------------------------------------
# SR-F UI Descriptor Form & QA Manifest Importer (F3)
# ---------------------------------------------------------------------------


def _ui_descriptors_root() -> Path:
    return Path(__file__).resolve().parents[1] / 'ui_descriptors'


def list_available_descriptor_forms(
    descriptors_root: Path | None = None,
) -> list[dict[str, Any]]:
    """List ``cdeadmin.ui-form.v1`` descriptor forms with ``SR-F`` codes."""
    root = descriptors_root or _ui_descriptors_root()
    items: list[dict[str, Any]] = []
    if not root.is_dir():
        return items
    for engine_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        forms_dir = engine_dir / 'forms'
        if not forms_dir.is_dir():
            continue
        for form_file in sorted(forms_dir.glob('*.form.json')):
            data = json.loads(form_file.read_text(encoding='utf-8'))
            form_key = form_file.name[:-len('.form.json')]
            fields = list(data.get('fields') or [])
            tabs = list(dict.fromkeys(
                str(f.get('tab') or 'General') for f in fields
            ))
            items.append({
                'engine': str(data.get('engine') or engine_dir.name),
                'form_key': form_key,
                'family': str(data.get('family') or form_key),
                'form_reference': str(data.get('form_reference') or ''),
                'status': str(data.get('status') or 'draft'),
                'resource_kinds': list(data.get('resource_kinds') or []),
                'tabs': tabs,
                'field_count': len(fields),
            })
    return items


def _map_descriptor_control(field: Mapping[str, Any]) -> tuple[str, dict]:
    ctrl = str(field.get('control') or 'text').strip().lower()
    extra: dict[str, Any] = {}
    if ctrl in ('grid', 'collection', 'table', 'subform'):
        cols = []
        for idx, c in enumerate(field.get('columns') or [], start=1):
            cid = _slug(
                str(c.get('field_id') or c.get('name') or f'col_{idx}'),
                f'col_{idx}',
            )
            cols.append({
                'id': cid,
                'name': str(c.get('label') or c.get('name') or cid),
                'width': 140,
                'datatype': str(c.get('control') or 'text'),
            })
        if not cols:
            cols = [
                {
                    'id': 'name',
                    'name': 'Name',
                    'width': 160,
                    'datatype': 'text',
                },
                {
                    'id': 'value',
                    'name': 'Value',
                    'width': 180,
                    'datatype': 'text',
                },
            ]
        extra['columns'] = cols
        return 'ui.grid', extra
    if ctrl in ('boolean', 'checkbox', 'switch'):
        extra['checked'] = bool(field.get('default', False))
        return 'ui.checkbox', extra
    if ctrl == 'radio':
        opts = [
            str(o.get('label') or o.get('value'))
            if isinstance(o, Mapping)
            else str(o)
            for o in (field.get('options') or [])
        ]
        extra['options'] = [o for o in opts if o]
        return 'ui.radio', extra
    if ctrl in ('select', 'multiselect', 'enum', 'reference'):
        opts = [
            str(o.get('label') or o.get('value'))
            if isinstance(o, Mapping)
            else str(o)
            for o in (field.get('options') or [])
        ]
        if not opts and field.get('reference_kind'):
            opts = [f"<{field['reference_kind']}>"]
        extra['options'] = [o for o in opts if o]
        return 'ui.dropdown', extra
    if ctrl == 'list':
        return 'ui.list', extra
    if ctrl in ('label', 'readonly_text'):
        return 'ui.label', extra
    placeholder = str(field.get('placeholder') or field.get('help') or '')
    if placeholder:
        extra['placeholder'] = placeholder[:120]
    return 'ui.input', extra


def parse_qa_screenshot_manifest(
    manifest_raw: str | list[Any] | Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Parse an optional QA screenshot manifest (JSON list/dict or CSV).

    Returns a lookup keyed by ``form_reference`` (``SR-F-...``) or
    ``<engine>:<form_key>``.
    """
    if not manifest_raw:
        return {}
    entries: list[Mapping[str, Any]] = []
    if isinstance(manifest_raw, str):
        stripped = manifest_raw.strip()
        if not stripped:
            return {}
        if stripped.startswith('[') or stripped.startswith('{'):
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                entries = [x for x in parsed if isinstance(x, Mapping)]
            elif isinstance(parsed, Mapping):
                entries = [
                    x for x in (parsed.get('items') or [parsed])
                    if isinstance(x, Mapping)
                ]
        else:
            reader = csv.DictReader(io.StringIO(stripped))
            entries = [dict(row) for row in reader]
    elif isinstance(manifest_raw, list):
        entries = [x for x in manifest_raw if isinstance(x, Mapping)]
    elif isinstance(manifest_raw, Mapping):
        entries = [
            x for x in (manifest_raw.get('items') or [manifest_raw])
            if isinstance(x, Mapping)
        ]

    lookup: dict[str, dict[str, Any]] = {}
    for item in entries:
        fref = str(item.get('form_reference') or '').strip()
        eng = str(item.get('engine') or '').strip()
        fkey = str(item.get('form_key') or item.get('family') or '').strip()
        record = {
            'media_type': str(item.get('media_type') or 'image/png').strip(),
            'image_base64': str(item.get('image_base64') or '').strip(),
            'caption': str(item.get('caption') or '').strip(),
            'regions': list(item.get('regions') or []),
        }
        if fref:
            lookup[fref] = record
        if eng and fkey:
            lookup[f'{eng}:{fkey}'] = record
    return lookup


def descriptor_form_to_screen_mesh(
    *,
    engine: str | None = None,
    form_key: str | None = None,
    form_reference: str | None = None,
    descriptors_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert a ScratchRobin ``SR-F`` descriptor form into a Draft mesh (F3).

    Returns ``(mesh_model, loss_report)`` documenting non-visual descriptor
    rules (``visible_when``, ``enabled_when``, provider gaps) omitted from the
    wireframe representation.
    """
    root = descriptors_root or _ui_descriptors_root()
    chosen_file: Path | None = None
    chosen_data: dict[str, Any] | None = None

    if engine and form_key:
        candidate = root / engine / 'forms' / f'{form_key}.form.json'
        if candidate.is_file():
            chosen_file = candidate
            chosen_data = json.loads(candidate.read_text(encoding='utf-8'))
    elif form_reference:
        target_ref = str(form_reference).strip()
        for form_path in sorted(root.glob('*/forms/*.form.json')):
            loaded = json.loads(form_path.read_text(encoding='utf-8'))
            if str(loaded.get('form_reference') or '') == target_ref:
                chosen_file = form_path
                chosen_data = loaded
                break

    if chosen_file is None or chosen_data is None:
        raise DesignStoreNotFound(
            f'UI descriptor form not found for engine={engine!r}, '
            f'form_key={form_key!r}, form_reference={form_reference!r}'
        )

    eng = str(chosen_data.get('engine') or chosen_file.parent.parent.name)
    fkey = chosen_file.name[:-len('.form.json')]
    family = str(chosen_data.get('family') or fkey)
    fref = str(chosen_data.get('form_reference') or '')
    family_title = family.replace('_', ' ').title()
    title = f'{eng.upper()} {family_title} ({fref or fkey})'

    screen_id = uuid7()
    controls: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    omitted_rules: list[dict[str, Any]] = []

    fields = list(chosen_data.get('fields') or [])
    tabs = list(dict.fromkeys(
        str(f.get('tab') or 'General') for f in fields
    ))
    if len(tabs) > 1:
        controls.append({
            'id': uuid7(),
            'screen_id': screen_id,
            'role': 'ui.tabs',
            'name': 'Form Sections',
            'options': tabs,
        })

    for field in fields:
        fid = str(field.get('field_id') or '').strip()
        flabel = str(field.get('label') or fid or 'Field').strip()
        ftab = str(field.get('tab') or 'General').strip()
        role, extra = _map_descriptor_control(field)
        cid = uuid7()
        controls.append({
            'id': cid,
            'screen_id': screen_id,
            'role': role,
            'name': flabel,
            'field_id': fid,
            'tab': ftab,
            **extra,
        })

        for rule_key in ('visible_when', 'enabled_when', 'option_values_path'):
            if field.get(rule_key) is not None:
                omitted_rules.append({
                    'field_id': fid,
                    'attribute': rule_key,
                    'reason': (
                        'Dynamic form evaluation is outside wireframe '
                        'Screen Mesh scope'
                    ),
                })

        if not field.get('ui_only') and fid:
            backend_field = str(field.get('backend_field_id') or fid).strip()
            access = 'read' if field.get('readonly') else 'read_write'
            bindings.append({
                'id': uuid7(),
                'source_id': cid,
                'target_kind': (
                    'table' if role == 'ui.grid' else 'column'
                ),
                'target_ref': f'{eng}.{family}.{backend_field}',
                'access_mode': access,
                'target_engine': eng,
            })

    # Standard non-executable dialog action buttons on descriptor forms
    for btn_label in ('Preview SQL', 'Cancel', 'Save'):
        controls.append({
            'id': uuid7(),
            'screen_id': screen_id,
            'role': 'ui.button',
            'name': btn_label,
            'tab': 'Footer',
        })

    mesh = validate_screen_mesh({
        'name': title,
        'screens': [{
            'id': screen_id,
            'name': title,
            'width': 960,
            'height': 680,
            'form_reference': fref,
            'notes': (
                f'Imported from ui_descriptors/{eng}/forms/{fkey}.form.json'
            ),
        }],
        'controls': controls,
        'regions': [],
        'bindings': bindings,
        'navigations': [],
        'notes': f'Descriptor form {fref} ({eng}/{fkey})',
    })
    loss_report = {
        'source_format': 'cdeadmin.ui-form.v1',
        'engine': eng,
        'form_key': fkey,
        'form_reference': fref,
        'preserved_controls': len(controls),
        'preserved_bindings': len(bindings),
        'omitted_dynamic_rules': omitted_rules,
        'omitted_tabs': list(chosen_data.get('omitted_tabs') or []),
    }
    return mesh, loss_report


# ---------------------------------------------------------------------------
# ScreenMeshSync service: store sync, bindings, usage & F4 redaction
# ---------------------------------------------------------------------------


class ScreenMeshSync:
    """Coordinates ``screen`` designs in ``designs.db`` with DDN & blobs."""

    def __init__(
        self,
        store: DesignStore,
        process: StoreDDNProcess | None = None,
    ) -> None:
        self.store = store
        self.process = process or StoreDDNProcess(store)

    def _sync_store_bindings(
        self,
        design_id: str,
        mesh: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Synchronize authoritative binding rows in ``designs.db`` (A5/A6).

        Preserves existing ``suspect`` / ``unknown`` validity state when the
        same ``(element_id, target_kind, target_ref)`` binding already exists,
        and removes bindings that were deleted from the mesh.
        """
        existing_rows = self.store.list_bindings(design_id)
        existing_by_tuple = {
            (r['element_id'], r['target_kind'], r['target_ref']): r
            for r in existing_rows
        }
        desired_tuples: set[tuple[str, str, str]] = set()
        for bnd in mesh['bindings']:
            store_kind, _ctx_role, _rel_role = _BINDING_TARGET_MAP[
                bnd['target_kind']
            ]
            tup = (bnd['source_id'], store_kind, bnd['target_ref'])
            desired_tuples.add(tup)
            prev = existing_by_tuple.get(tup)
            preserved_state = prev['state'] if prev else 'valid'
            preserved_reason = prev['state_reason'] if prev else None
            self.store.add_binding(
                design_id=design_id,
                element_id=bnd['source_id'],
                target_kind=store_kind,
                target_ref=bnd['target_ref'],
                target_engine=bnd.get('target_engine'),
                target_endpoint_id=bnd.get('target_endpoint_id'),
                target_database_target_id=bnd.get('target_database_target_id'),
                state=preserved_state,
                state_reason=preserved_reason,
            )

        stale_ids = [
            row['id']
            for tup, row in existing_by_tuple.items()
            if tup not in desired_tuples
        ]
        if stale_ids:
            placeholders = ', '.join('?' for _ in stale_ids)
            with self.store._lock:
                conn = self.store._connect()
                try:
                    conn.execute(
                        f'DELETE FROM binding WHERE id IN ({placeholders})',
                        stale_ids,
                    )
                    conn.commit()
                finally:
                    conn.close()
        return self.store.list_bindings(design_id)

    def _hydrate_mesh_state(
        self,
        design: Mapping[str, Any],
    ) -> dict[str, Any]:
        design_id = design['id']
        ver_num = int(design['version']['version'])
        parsed = ddn_to_screen_mesh(design['version']['ddn_text'])
        mesh = parsed['mesh']

        assets = self.store.list_design_assets(design_id, version=ver_num)
        sha_by_path = {a['path']: a['sha256'] for a in assets}
        for scr in mesh['screens']:
            spath = scr.get('screenshot_path') or ''
            if spath and spath in sha_by_path:
                scr['screenshot_sha256'] = sha_by_path[spath]

        store_bindings = self.store.list_bindings(design_id)
        by_tuple = {
            (b['element_id'], b['target_kind'], b['target_ref']): b
            for b in store_bindings
        }
        suspect_count = 0
        for bnd in mesh['bindings']:
            store_kind = _BINDING_TARGET_MAP[bnd['target_kind']][0]
            row = by_tuple.get(
                (bnd['source_id'], store_kind, bnd['target_ref'])
            )
            bnd['store_binding_id'] = row['id'] if row else None
            bnd['state'] = row['state'] if row else 'unknown'
            bnd['state_reason'] = row['state_reason'] if row else None
            if bnd['state'] == 'suspect':
                suspect_count += 1

        return {
            'design': design,
            'mesh': mesh,
            'assets': assets,
            'store_bindings': store_bindings,
            'suspect_binding_count': suspect_count,
            'element_ids': parsed['element_ids'],
            'layout_positions': parsed['layout_positions'],
        }

    def get_screen_mesh(
        self,
        design_id: str,
        *,
        version: int | None = None,
    ) -> dict[str, Any]:
        design = self.store.get_design(design_id, version=version)
        if design['kind'] not in ('screen', 'screen_flow'):
            raise DesignStoreError(
                f'Design {design_id!r} is not a Screen Mesh design'
            )
        return self._hydrate_mesh_state(design)

    def create_screen_mesh(
        self,
        *,
        project_id: str,
        key: str,
        title: str,
        actor_id: int,
        mesh: Mapping[str, Any] | None = None,
        form_reference: str | None = None,
        note: str = '',
    ) -> dict[str, Any]:
        clean_key = str(key or _slug(title, 'screen_mesh')).strip()
        model = (
            validate_screen_mesh(mesh)
            if mesh is not None
            else default_screen_mesh_model(
                name=title, form_reference=form_reference
            )
        )
        ddn_text, _ids = screen_mesh_to_ddn(model)
        created = self.store.create_design(
            project_id=project_id,
            key=clean_key,
            kind='screen',
            title=model['name'],
            ddn_text=ddn_text,
            actor_id=actor_id,
            status='draft',
            note=note or 'Created Screen Mesh draft',
            origin='local',
        )
        self._sync_store_bindings(created['id'], model)
        return self.get_screen_mesh(created['id'])

    def save_screen_mesh(
        self,
        design_id: str,
        *,
        expected_head_version: int,
        actor_id: int,
        mesh: Mapping[str, Any] | None = None,
        ddn_text: str | None = None,
        pinned_positions: Mapping[str, Mapping[str, float]] | None = None,
        status: str = 'draft',
        note: str = 'Updated Screen Mesh',
    ) -> dict[str, Any]:
        current = self.get_screen_mesh(design_id)
        prev_assets = current['assets']

        if mesh is not None:
            validated = validate_screen_mesh(mesh)
            merged_pos = {
                **current['layout_positions'],
                **dict(pinned_positions or {}),
            }
            out_ddn, _ids = screen_mesh_to_ddn(
                validated,
                element_ids=current['element_ids'],
                layout_positions=merged_pos,
            )
        elif ddn_text is not None:
            parsed = ddn_to_screen_mesh(ddn_text)
            validated = parsed['mesh']
            out_ddn = ddn_text
        else:
            raise DesignStoreError(
                'Either mesh model or ddn_text is required to save Screen Mesh'
            )

        saved = self.process.save_from_ddn(
            design_id,
            expected_head_version=expected_head_version,
            ddn_or_workspace=out_ddn,
            actor_id=actor_id,
            status=status,
            note=note,
            title=validated['name'],
            allow_conflict_note=True,
        )['design']

        new_ver = int(saved['version']['version'])
        valid_paths = {
            s['screenshot_path']
            for s in validated['screens']
            if s.get('screenshot_path')
        }
        for asset in prev_assets:
            if asset['path'] in valid_paths:
                self.store.attach_blob(
                    design_id, new_ver, asset['path'], asset['sha256']
                )

        self._sync_store_bindings(design_id, validated)
        return self.get_screen_mesh(design_id, version=new_ver)

    def attach_screenshot(
        self,
        design_id: str,
        *,
        actor_id: int,
        data: bytes,
        media_type: str = 'image/png',
        screen_id: str | None = None,
        note: str = 'Attached screenshot to Screen Mesh',
    ) -> dict[str, Any]:
        dims = inspect_image_header(data, media_type)
        current = self.get_screen_mesh(design_id)
        mesh = copy.deepcopy(current['mesh'])
        target_scr = None
        for scr in mesh['screens']:
            if screen_id is None or scr['id'] == screen_id:
                target_scr = scr
                break
        if target_scr is None:
            raise DesignStoreNotFound(
                f'Screen {screen_id!r} not found in Screen Mesh {design_id!r}'
            )

        ext = 'webp' if media_type.lower() == 'image/webp' else 'png'
        asset_path = f"screenshots/{target_scr['id']}.{ext}"
        blob = self.store.put_blob(media_type, data)
        target_scr['screenshot_path'] = asset_path
        target_scr['width'] = dims['width']
        target_scr['height'] = dims['height']

        ddn_text, _ids = screen_mesh_to_ddn(
            mesh,
            element_ids=current['element_ids'],
            layout_positions=current['layout_positions'],
        )
        saved = self.process.save_from_ddn(
            design_id,
            expected_head_version=int(current['design']['head_version']),
            ddn_or_workspace=ddn_text,
            actor_id=actor_id,
            status='draft',
            note=note,
            title=mesh['name'],
            allow_conflict_note=True,
        )['design']
        new_ver = int(saved['version']['version'])
        for prev in current['assets']:
            if prev['path'] != asset_path:
                self.store.attach_blob(
                    design_id, new_ver, prev['path'], prev['sha256']
                )
        self.store.attach_blob(design_id, new_ver, asset_path, blob['sha256'])
        self._sync_store_bindings(design_id, mesh)
        return self.get_screen_mesh(design_id, version=new_ver)

    def redact_screenshot(
        self,
        design_id: str,
        *,
        actor_id: int,
        regions: list[Mapping[str, Any]],
        screen_id: str | None = None,
        fill_rgb: tuple[int, int, int] = (15, 23, 42),
        note: str = 'Redacted sensitive screenshot regions',
    ) -> dict[str, Any]:
        """Destructively redact screenshot regions and purge old bytes (F4)."""
        current = self.get_screen_mesh(design_id)
        mesh = copy.deepcopy(current['mesh'])
        target_scr = None
        for scr in mesh['screens']:
            if screen_id is None or scr['id'] == screen_id:
                target_scr = scr
                break
        if target_scr is None:
            raise DesignStoreNotFound(
                f'Screen {screen_id!r} not found in Screen Mesh {design_id!r}'
            )
        asset_path = target_scr.get('screenshot_path') or ''
        old_sha = target_scr.get('screenshot_sha256') or ''
        if not asset_path or not old_sha:
            raise DesignStoreError(
                'Target screen has no attached screenshot to redact'
            )

        old_blob = self.store.get_blob(old_sha)
        if old_blob['media_type'].lower() != 'image/png':
            raise DesignStoreError(
                'Destructive pixel redaction requires a PNG screenshot'
            )
        redacted_bytes, report = redact_png_regions(
            old_blob['bytes'], regions, fill_rgb=fill_rgb
        )

        ddn_text, _ids = screen_mesh_to_ddn(
            mesh,
            element_ids=current['element_ids'],
            layout_positions=current['layout_positions'],
        )
        saved = self.process.save_from_ddn(
            design_id,
            expected_head_version=int(current['design']['head_version']),
            ddn_or_workspace=ddn_text,
            actor_id=actor_id,
            status='draft',
            note=note,
            title=mesh['name'],
            allow_conflict_note=True,
        )['design']
        new_ver = int(saved['version']['version'])

        for prev in current['assets']:
            if prev['path'] != asset_path:
                self.store.attach_blob(
                    design_id, new_ver, prev['path'], prev['sha256']
                )
        replaced = self.store.replace_and_purge_blob(
            design_id=design_id,
            version=new_ver,
            path=asset_path,
            old_sha256=old_sha,
            media_type='image/png',
            new_data=redacted_bytes,
        )
        self._sync_store_bindings(design_id, mesh)
        hydrated = self.get_screen_mesh(design_id, version=new_ver)
        return {
            **hydrated,
            'redaction': {
                **report,
                'old_sha256': old_sha,
                'new_sha256': replaced['sha256'],
                'purged_original': replaced['purged_original'],
            },
        }

    def import_descriptor_form(
        self,
        *,
        project_id: str,
        actor_id: int,
        key: str | None = None,
        engine: str | None = None,
        form_key: str | None = None,
        form_reference: str | None = None,
        qa_manifest: str | list[Any] | Mapping[str, Any] | None = None,
        descriptors_root: Path | None = None,
        note: str = '',
    ) -> dict[str, Any]:
        """Import a ScratchRobin ``SR-F`` descriptor form as Draft (F3)."""
        mesh, loss_report = descriptor_form_to_screen_mesh(
            engine=engine,
            form_key=form_key,
            form_reference=form_reference,
            descriptors_root=descriptors_root,
        )
        eng = loss_report['engine']
        fkey = loss_report['form_key']
        fref = loss_report['form_reference']
        design_key = str(
            key or _slug(f'srf_{eng}_{fkey}', 'descriptor_mesh')
        ).strip()

        qa_lookup = parse_qa_screenshot_manifest(qa_manifest)
        qa_entry = qa_lookup.get(fref) or qa_lookup.get(f'{eng}:{fkey}')
        screenshot_bytes: bytes | None = None
        screenshot_media = 'image/png'
        if qa_entry:
            for ridx, ritem in enumerate(qa_entry.get('regions') or [], 1):
                if isinstance(ritem, Mapping) and ritem.get('bounds'):
                    mesh['regions'].append({
                        'id': uuid7(),
                        'screen_id': mesh['screens'][0]['id'],
                        'role': 'ui.region',
                        'name': str(ritem.get('name') or f'QA Region {ridx}'),
                        'bounds': dict(ritem['bounds']),
                        'notes': str(ritem.get('notes') or ''),
                    })
            if qa_entry.get('image_base64'):
                raw_b64 = qa_entry['image_base64']
                if ',' in raw_b64 and raw_b64.startswith('data:'):
                    raw_b64 = raw_b64.split(',', 1)[1]
                screenshot_bytes = base64.b64decode(raw_b64)
                screenshot_media = qa_entry['media_type']
                dims = inspect_image_header(screenshot_bytes, screenshot_media)
                ext = (
                    'webp'
                    if screenshot_media.lower() == 'image/webp'
                    else 'png'
                )
                mesh['screens'][0]['screenshot_path'] = (
                    f"screenshots/{mesh['screens'][0]['id']}.{ext}"
                )
                mesh['screens'][0]['width'] = dims['width']
                mesh['screens'][0]['height'] = dims['height']

        mesh = validate_screen_mesh(mesh)
        ddn_text, _ids = screen_mesh_to_ddn(mesh)
        imported = self.store.import_ddn(
            project_id=project_id,
            key=design_key,
            kind='screen',
            title=mesh['name'],
            ddn_or_workspace=ddn_text,
            actor_id=actor_id,
            origin=f'import:ui_descriptor:{fref or f"{eng}:{fkey}"}',
            loss_report=loss_report,
            note=note or f'Imported SR-F descriptor form {fref or fkey}',
        )
        ver_num = int(imported['version']['version'])
        if screenshot_bytes is not None:
            blob = self.store.put_blob(screenshot_media, screenshot_bytes)
            self.store.attach_blob(
                imported['id'],
                ver_num,
                mesh['screens'][0]['screenshot_path'],
                blob['sha256'],
            )
        self._sync_store_bindings(imported['id'], mesh)
        hydrated = self.get_screen_mesh(imported['id'], version=ver_num)
        return {**hydrated, 'loss_report': loss_report}

    def query_usage(
        self,
        *,
        project_id: str,
        target_ref: str | None = None,
        target_kind: str | None = None,
        include_suspect: bool = True,
    ) -> list[dict[str, Any]]:
        """Answer 'Where is this column/table/question used?' across meshes."""
        needle = str(target_ref or '').strip().lower()
        kind_filter = str(target_kind or '').strip().lower()
        designs = self.store.list_designs(project_id=project_id, kind='screen')
        matches: list[dict[str, Any]] = []
        for dsummary in designs:
            hydrated = self.get_screen_mesh(dsummary['id'])
            mesh = hydrated['mesh']
            screens_by_id = {s['id']: s['name'] for s in mesh['screens']}
            elements_by_id: dict[str, tuple[str, str, str]] = {}
            for s in mesh['screens']:
                elements_by_id[s['id']] = ('ui.frame', s['name'], s['name'])
            for c in mesh['controls']:
                elements_by_id[c['id']] = (
                    c['role'],
                    c['name'],
                    screens_by_id.get(c['screen_id'], ''),
                )
            for r in mesh['regions']:
                elements_by_id[r['id']] = (
                    'ui.region',
                    r['name'],
                    screens_by_id.get(r['screen_id'], ''),
                )

            for bnd in mesh['bindings']:
                if not include_suspect and bnd.get('state') == 'suspect':
                    continue
                if kind_filter and bnd['target_kind'] != kind_filter:
                    continue
                if needle and needle not in bnd['target_ref'].lower():
                    continue
                el_role, el_name, scr_name = elements_by_id.get(
                    bnd['source_id'], ('unknown', bnd['source_id'], '')
                )
                matches.append({
                    'design_id': dsummary['id'],
                    'design_key': dsummary['key'],
                    'design_title': dsummary['title'],
                    'screen_name': scr_name,
                    'element_id': bnd['source_id'],
                    'element_role': el_role,
                    'element_name': el_name,
                    'column_id': bnd.get('column_id') or '',
                    'binding_id': bnd['id'],
                    'target_kind': bnd['target_kind'],
                    'target_ref': bnd['target_ref'],
                    'access_mode': bnd['access_mode'],
                    'state': bnd.get('state', 'valid'),
                    'state_reason': bnd.get('state_reason'),
                })
        return matches
