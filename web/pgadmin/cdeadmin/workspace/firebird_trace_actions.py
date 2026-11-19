"""One-use durable trace reviews and outcomes, never captured SQL history."""
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
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class TraceActions:
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
        record = state.get('firebird_trace_actions', {}).get(identity)
        if record is None or record['owner'] != owner or record['binding'] != binding:
            raise ValueError('Trace review unavailable for this owner and target')
        return record

    @staticmethod
    def _public(record):
        return {**copy.deepcopy({key: value for key, value in record.items()
                                if key not in {'owner', 'binding'}}), 'automatic_retry': False}

    ALLOWED_OPERATIONS = frozenset({
        'start', 'start_services', 'stop', 'suspend', 'resume', 'release', 'forget',
        'suspend_external', 'resume_external', 'stop_external',
    })

    def review(self, owner, binding, operation, payload):
        if operation not in self.ALLOWED_OPERATIONS:
            raise ValueError('Unknown native trace action')
        now = time.time()
        record = {'review_id': str(uuid.uuid4()), 'owner': owner, 'binding': binding,
                  'state': 'reviewed', 'operation': operation, 'payload': copy.deepcopy(payload),
                  'created_at': now, 'expires_at': now + 300}
        record['review_digest'] = digest(record)
        with self._store() as store:
            def save(state):
                records = state.setdefault('firebird_trace_actions', {})
                for key in list(records):
                    if records[key]['state'] == 'reviewed' and records[key]['expires_at'] < now:
                        del records[key]
                if len(records) >= 1000:
                    raise ValueError('Trace receipt capacity reached; retention review required')
                records[record['review_id']] = record
            store.change(save)
        return self._public(record)

    def get(self, owner, binding, identity):
        with self._store() as store:
            return self._public(self._record(store.read(), identity, owner, binding))

    def session(self, owner, binding, identity):
        with self._store() as store:
            record = store.read().get('firebird_trace_sessions', {}).get(identity)
            if record is None or record['owner'] != owner or record['binding'] != binding:
                raise ValueError('Trace receipt unavailable for this owner and target')
            result = copy.deepcopy(record['snapshot'])
            if not result.get('cleanup_confirmed'):
                result['state'] = 'unknown_after_process_loss'
            return {**result, 'live_handle_available': False,
                    'output_available': False, 'output_persisted': False}

    def finish_session(self, owner, binding, snapshot):
        if 'lines' in snapshot:
            raise ValueError('Captured trace text must not enter the operation store')
        with self._store() as store:
            def save(state):
                records = state.setdefault('firebird_trace_sessions', {})
                previous = records.get(snapshot['trace_id'])
                if previous and previous['snapshot'].get('cleanup_confirmed') and not snapshot.get('cleanup_confirmed'):
                    return
                records[snapshot['trace_id']] = {
                    'owner': owner, 'binding': binding, 'snapshot': copy.deepcopy(snapshot)}
            store.change(save)

    def apply(self, owner, binding, request, execute):
        if (not isinstance(request, dict) or set(request) != {'review_id', 'review_digest', 'confirmed'}
                or request['confirmed'] is not True or not isinstance(request['review_id'], str)
                or not isinstance(request['review_digest'], str)):
            raise ValueError('Confirm the exact retained native trace review')
        with self._store() as store:
            def claim(state):
                record = self._record(state, request['review_id'], owner, binding)
                if record['review_digest'] != request['review_digest']:
                    raise ValueError('Trace review fingerprint differs')
                if record['state'] != 'reviewed':
                    return None
                if time.time() > record['expires_at']:
                    raise ValueError('Trace review expired')
                record.update(state='unknown_outcome', claimed_at=time.time())
                return copy.deepcopy(record)
            claimed = store.change(claim)
        if claimed is not None:
            try:
                outcome = execute(claimed)
                if 'lines' in outcome:
                    raise ValueError('Captured output must not enter the trace action journal')
            except Exception as error:
                outcome = {'state': 'unknown_outcome', 'error_type': type(error).__name__}
            with self._store() as store:
                def finish(state):
                    record = self._record(state, request['review_id'], owner, binding)
                    record.update(state='submitted', outcome=copy.deepcopy(
                        outcome), finished_at=time.time())
                store.change(finish)
        return self.get(owner, binding, request['review_id'])
