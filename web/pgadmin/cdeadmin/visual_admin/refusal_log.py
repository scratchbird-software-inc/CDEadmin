"""Where the full reason for a refusal is kept (Decision 22).

A refusal response carries only a code, a catalog sentence and an opaque reference. The provider's
own message may name what the user typed or quote native tool output, so it is kept here under the
reference, and nowhere the application log reaches: the log line carries the reference, the codes,
the operation and the endpoint, never the reason.

The store is bounded and lives in one process. A restart or a second worker does not have the
entry, and ``read`` then answers ``None`` exactly as it does for an unknown or expired reference.
Each entry is bound to the endpoint where the refusal happened and is never returned for another.
"""
import re
import secrets
import threading
import time
from collections import OrderedDict

REFERENCE = re.compile(r'[0-9a-f]{16}')
MESSAGE_LIMIT = 2000


class RefusalReasons:
    def __init__(self, limit=500, ttl=86400, clock=time.time):
        self._entries = OrderedDict()
        self._limit, self._ttl, self._clock = limit, ttl, clock
        self._lock = threading.Lock()

    def record(self, *, endpoint_id, user_id, operation, message, codes):
        """Keep one reason and return its reference."""
        reference = secrets.token_hex(8)
        entry = {
            'reference': reference, 'endpoint_id': str(endpoint_id), 'user_id': user_id,
            'operation': str(operation)[:200], 'codes': [str(code)[:128] for code in codes][:32],
            'message': str(message)[:MESSAGE_LIMIT], 'time': self._clock(),
        }
        with self._lock:
            self._expire()
            self._entries[reference] = entry
            while len(self._entries) > self._limit:
                self._entries.popitem(last=False)
        return reference

    def read(self, reference, endpoint_id):
        """The entry, or None when the reference is unknown, expired or belongs to another endpoint."""
        if not isinstance(reference, str) or REFERENCE.fullmatch(reference) is None:
            return None
        with self._lock:
            self._expire()
            entry = self._entries.get(reference)
            if entry is None or entry['endpoint_id'] != str(endpoint_id):
                return None
            return dict(entry)

    def _expire(self):
        now = self._clock()
        while self._entries:
            reference, entry = next(iter(self._entries.items()))
            if now - entry['time'] <= self._ttl:
                break
            del self._entries[reference]


_STORE = RefusalReasons()


def reasons():
    """The process-wide store."""
    return _STORE


def lookup(reference, endpoint_id, allowed):
    """The HTTP body for a request to read a reason: (status, body).

    ``allowed`` is decided by the caller (a native administrator of the endpoint, or a user holding
    the ``refusal.view_reasons`` permission). Not allowed is refused before the store is consulted,
    so a refusal reveals nothing about whether a reference exists.
    """
    if not allowed:
        return 403, {'success': 0, 'errormsg': 'You are not allowed to read the reasons for refused operations.',
                     'info': 'REFUSAL_REASON_FORBIDDEN'}
    entry = reasons().read(reference, endpoint_id)
    if entry is None:
        return 404, {'success': 0, 'errormsg': 'This reference is unknown, has expired, or belongs to another endpoint.',
                     'info': 'REFUSAL_REASON_UNKNOWN'}
    return 200, {'success': 1, 'data': {key: entry[key] for key in ('reference', 'operation', 'codes', 'message', 'time')}}
