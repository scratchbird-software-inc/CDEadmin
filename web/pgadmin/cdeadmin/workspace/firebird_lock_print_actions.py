"""One-use durable fb_lock_print reviews and metadata-only outcome receipts.

Raw lock keys, AST pointers and raw lock-table dumps are never persisted to disk.
"""
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


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()


class LockPrintActions:
    def __init__(self, path):
        self.path = Path(path)
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

    @staticmethod
    def _record(state, identity, owner, binding):
        record = state.get('firebird_lock_print_actions', {}).get(identity)
        if record is None or record['owner'] != owner or record['binding'] != binding:
            raise ValueError('Lock-print review or receipt unavailable for this owner and target')
        return record

    @staticmethod
    def _public(record):
        return {
            **copy.deepcopy({
                k: v for k, v in record.items()
                if k not in {'owner', 'binding'}
            }),
            'automatic_retry': False,
        }

    @staticmethod
    def _durable_summary(outcome):
        parsed = outcome.get('parsed') or {}
        return {
            'state': outcome.get('state'),
            'native_dispatched': outcome.get('native_dispatched', False),
            'timed_out': outcome.get('timed_out', False),
            'process_cleaned_up': outcome.get('process_cleaned_up', False),
            'return_code': outcome.get('return_code'),
            'started_at': outcome.get('started_at'),
            'completed_at': outcome.get('completed_at'),
            'published_as_default_metric': False,
            'output_truncated': outcome.get('output_truncated', False),
            'reason': outcome.get('reason'),
            'lock_table_state': parsed.get('lock_table_state'),
            'owners_observed': len(parsed.get('owners') or ()),
            'waiting_owners_observed': sum(
                1 for o in (parsed.get('owners') or ()) if o.get('is_waiting')
            ),
            'locks_observed': len(parsed.get('locks') or ()),
            'interactive_samples_observed': len(parsed.get('interactive_samples') or ()),
            'raw_output_persisted': False,
        }

    def review(self, owner, binding, payload):
        now = time.time()
        record = {
            'review_id': str(uuid.uuid4()),
            'owner': owner,
            'binding': binding,
            'state': 'reviewed',
            'payload': copy.deepcopy(payload),
            'created_at': now,
            'expires_at': now + 300,
        }
        record['review_digest'] = digest(record)
        with self._store() as store:
            def save(state):
                records = state.setdefault('firebird_lock_print_actions', {})
                for key in list(records):
                    if records[key]['state'] == 'reviewed' and records[key]['expires_at'] < now:
                        del records[key]
                if len(records) >= 1000:
                    raise ValueError('Lock-print receipt capacity reached; retention review required')
                records[record['review_id']] = record

            store.change(save)
        return self._public(record)

    def get(self, owner, binding, identity):
        with self._store() as store:
            return self._public(self._record(store.read(), identity, owner, binding))

    def listing(self, owner, binding):
        with self._store() as store:
            records = store.read().get('firebird_lock_print_actions', {})
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
            raise ValueError('Confirm the exact retained fb_lock_print review')
        now = time.time()
        with self._store() as store:
            claimed = []

            def claim(state):
                record = self._record(state, request['review_id'], owner, binding)
                if record['review_digest'] != request['review_digest']:
                    raise ValueError('Lock-print review digest does not match')
                if record['state'] != 'reviewed':
                    raise ValueError('Lock-print review was already consumed; create a new review')
                if record['expires_at'] < now:
                    record['state'] = 'expired'
                    raise ValueError('Lock-print review expired; create a new review')
                record['state'] = 'dispatched_unconfirmed'
                record['claimed_at'] = now
                claimed.append(copy.deepcopy(record))

            store.change(claim)

        outcome = execute(claimed[0])
        summary = self._durable_summary(outcome)
        with self._store() as store:
            def finish(state):
                record = self._record(state, request['review_id'], owner, binding)
                record['state'] = summary['state'] or 'completed'
                record['outcome_summary'] = summary

            store.change(finish)

        return {
            'review_id': request['review_id'],
            'automatic_retry': False,
            'outcome': outcome,
            'durable_summary': summary,
        }
