##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""RFC 9562 UUIDv7 identifiers for the ScratchRobin design store.

Owner decision, 2026-11-10 (A1): design, element, binding and
resource-identity rows use time-ordered UUIDv7 identifiers written into DDN
text as ``id``; legacy configuration tables retain uuid4.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
import uuid

_UUID7_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
)
_LOCK = threading.Lock()
_LAST_MS = -1
_COUNTER = 0


def uuid7(timestamp_ms: int | None = None) -> str:
    """Return a canonical lowercase 36-char UUIDv7 string.

    Uses a 48-bit Unix millisecond timestamp, a 12-bit monotonic counter
    within each millisecond so back-to-back allocations sort strictly in
    creation order, and 62 bits of cryptographic randomness.
    """
    global _LAST_MS, _COUNTER
    with _LOCK:
        now_ms = (
            int(timestamp_ms)
            if timestamp_ms is not None
            else time.time_ns() // 1_000_000
        )
        if now_ms < 0 or now_ms > 0xFFFFFFFFFFFF:
            raise ValueError('UUIDv7 timestamp_ms is out of 48-bit range')
        if timestamp_ms is None:
            if now_ms <= _LAST_MS:
                now_ms = _LAST_MS
                _COUNTER += 1
                if _COUNTER > 0xFFF:
                    now_ms += 1
                    _COUNTER = 0
                _LAST_MS = now_ms
            else:
                _LAST_MS = now_ms
                _COUNTER = int.from_bytes(os.urandom(2), 'big') & 0x03FF
            seq = _COUNTER
        else:
            seq = int.from_bytes(os.urandom(2), 'big') & 0x0FFF

    rand_b = int.from_bytes(os.urandom(8), 'big') & ((1 << 62) - 1)
    value = (
        ((now_ms & 0xFFFFFFFFFFFF) << 80)
        | (0x7 << 76)
        | ((seq & 0x0FFF) << 64)
        | (0x2 << 62)
        | rand_b
    )
    return str(uuid.UUID(int=value))


def deterministic_uuid7(key: str, timestamp_ms: int = 0) -> str:
    """Derive a reproducible UUIDv7 from ``key`` for idempotent backfill."""
    if not isinstance(key, str) or not key:
        raise ValueError('Deterministic UUIDv7 key must be a non-empty string')
    if timestamp_ms < 0 or timestamp_ms > 0xFFFFFFFFFFFF:
        raise ValueError('UUIDv7 timestamp_ms is out of 48-bit range')
    digest = hashlib.sha256(key.encode('utf-8')).digest()
    rand_a = int.from_bytes(digest[:2], 'big') & 0x0FFF
    rand_b = int.from_bytes(digest[2:10], 'big') & ((1 << 62) - 1)
    value = (
        ((timestamp_ms & 0xFFFFFFFFFFFF) << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0x2 << 62)
        | rand_b
    )
    return str(uuid.UUID(int=value))


def is_uuid7(value: object) -> bool:
    """Return True when ``value`` is a canonical lowercase UUIDv7 string."""
    return isinstance(value, str) and bool(_UUID7_RE.match(value))
