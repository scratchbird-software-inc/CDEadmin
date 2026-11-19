"""Shared one-use durable review and receipt journal for Firebird host workflows.

Secrets, passwords and raw binary payloads are forbidden in durable records.
"""
from collections.abc import Mapping
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

from ..operations.fileio import exclusive_file_lock
from ..operations.store import JsonOperationStore

FORBIDDEN_KEYS = frozenset({
    'password', 'raw_password', 'secret_value', 'isc_password', 'binary_bytes',
})


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()


def _assert_secret_free(value):
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ValueError(f'Secret or raw binary key {key!r} cannot be persisted')
            _assert_secret_free(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_secret_free(item)


class HostActions:
    def __init__(self, path, namespace, allowed_operations):
        self.path = Path(path)
        self.namespace = str(namespace)
        self.allowed_operations = frozenset(allowed_operations)
        self.lock = threading.RLock()

    @contextmanager
    def _store(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            descriptor = os.open(str(self.path) + '.lock', os.O_RDWR | os.O_CREAT, 0o600)
            try:
                with exclusive_file_lock(descriptor):
                    yield JsonOperationStore(self.path)
            finally:
                os.close(descriptor)

    def _record(self, state, identity, owner, binding):
        record = state.get(self.namespace, {}).get(identity)
        if record is None or record['owner'] != owner or record['binding'] != binding:
            raise ValueError(f'{self.namespace} review or receipt unavailable for this owner and target')
        return record

    @staticmethod
    def _public(record):
        return {
            **copy.deepcopy({
                key: value for key, value in record.items()
                if key not in {'owner', 'binding'}
            }),
            'automatic_retry': False,
        }

    def review(self, owner, binding, operation, payload):
        if operation not in self.allowed_operations:
            raise ValueError(f'Unknown {self.namespace} operation: {operation!r}')
        _assert_secret_free(payload)
        now = time.time()
        record = {
            'review_id': str(uuid.uuid4()),
            'owner': owner,
            'binding': binding,
            'state': 'reviewed',
            'operation': operation,
            'payload': copy.deepcopy(payload),
            'created_at': now,
            'expires_at': now + 300,
        }
        record['review_digest'] = digest(record)
        with self._store() as store:
            def save(state):
                records = state.setdefault(self.namespace, {})
                for key in list(records):
                    if records[key]['state'] == 'reviewed' and records[key]['expires_at'] < now:
                        del records[key]
                if len(records) >= 1000:
                    raise ValueError(f'{self.namespace} receipt capacity reached; retention review required')
                records[record['review_id']] = record

            store.change(save)
        return self._public(record)

    def get(self, owner, binding, identity):
        with self._store() as store:
            return self._public(self._record(store.read(), identity, owner, binding))

    def listing(self, owner, binding):
        with self._store() as store:
            records = store.read().get(self.namespace, {})
            items = [
                self._public(rec)
                for rec in records.values()
                if rec.get('owner') == owner and rec.get('binding') == binding
            ]
        items.sort(key=lambda r: r.get('created_at', 0), reverse=True)
        return {'items': items[:100]}

    def apply(self, owner, binding, request, execute):
        if (not isinstance(request, dict)
                or set(request) != {'review_id', 'review_digest', 'confirmed'}
                or request['confirmed'] is not True
                or not isinstance(request['review_id'], str)
                or not isinstance(request['review_digest'], str)):
            raise ValueError(f'Confirm the exact retained {self.namespace} review')
        now = time.time()
        with self._store() as store:
            claimed = []

            def claim(state):
                record = self._record(state, request['review_id'], owner, binding)
                if record['review_digest'] != request['review_digest']:
                    raise ValueError('Review digest does not match')
                if record['state'] != 'reviewed':
                    raise ValueError('Review was already consumed; create a new review')
                if record['expires_at'] < now:
                    record['state'] = 'expired'
                    raise ValueError('Review expired; create a new review')
                record['state'] = 'dispatched_unconfirmed'
                record['claimed_at'] = now
                claimed.append(copy.deepcopy(record))

            store.change(claim)

        try:
            outcome = execute(claimed[0])
            _assert_secret_free(outcome)
        except Exception as error:
            outcome = {
                'state': 'unknown_outcome',
                'native_dispatched': True,
                'error_type': type(error).__name__,
                'reason': str(error)[:400],
            }
        with self._store() as store:
            def finish(state):
                record = self._record(state, request['review_id'], owner, binding)
                record['state'] = 'submitted'
                record['finished_at'] = time.time()
                record['outcome'] = copy.deepcopy(outcome)

            store.change(finish)
        return self.get(owner, binding, request['review_id'])
