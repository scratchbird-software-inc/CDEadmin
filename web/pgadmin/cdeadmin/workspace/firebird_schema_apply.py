"""Durable, owner-bound schema review receipts; native engine owns outcomes."""
from contextlib import contextmanager
from copy import deepcopy
import os
from pathlib import Path
import threading
import time
import uuid

from ..operations.store import JsonOperationStore
from ..operations.fileio import exclusive_file_lock
from .firebird_schema_plan import digest, DERIVED
from .firebird_creation_graph import INSTRUCTION
from .firebird_lifecycle_plan import INSTRUCTION as LIFECYCLE
from .firebird_privilege_plan import INSTRUCTION as GRANT_CHANGE


class SchemaApplyError(ValueError):
    pass


class SchemaApplications:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self.lock = threading.RLock()

    @contextmanager
    def _store(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Each worker reloads while holding the same exclusive file lock. This
        # store is separate from the operation bus's process-local store cache.
        with self.lock:
            fd = os.open(str(self.path) + '.lock', os.O_RDWR | os.O_CREAT, 0o600)
            try:
                with exclusive_file_lock(fd):
                    yield JsonOperationStore(self.path)
            finally:
                os.close(fd)

    @staticmethod
    def _record(state, review_id, owner, binding):
        record = state.get('schema_applications', {}).get(review_id)
        if record is None or record['owner'] != owner or record['binding'] != binding:
            raise SchemaApplyError('Schema application review is unavailable for this owner and target')
        return record

    @staticmethod
    def _public(record):
        result = {key: deepcopy(value) for key, value in record.items()
                  if key not in {'owner', 'binding', 'baseline', 'desired'}}
        result['automatic_retry'] = False
        return result

    def review(self, plan, baseline, desired, owner, binding, database):
        if plan['status'] != 'review-ready' or not plan['operations']:
            raise SchemaApplyError('Only an unblocked plan with operations can be prepared')
        identity = plan['database_identity']
        if any(not isinstance(identity.get(key), str) or not identity[key]
               for key in ('guid', 'file_id')):
            raise SchemaApplyError('Native database GUID and file identity are required')
        ids = {item['resource_id'] for item in plan['operations']}
        def reduced(document):
            return {**deepcopy({key: value for key, value in document.items()
                               if key in {'provenance', 'sha256', 'format'}}),
                    'rows': {key: {**deepcopy(value), 'native': {field: deepcopy(fact)
                        for field, fact in value['native'].items() if field in {INSTRUCTION, LIFECYCLE, GRANT_CHANGE} or field not in DERIVED | {'statistics'}}}
                        for key, value in document['rows'].items() if key in ids}}
        record = {'review_id': str(uuid.uuid4()), 'state': 'reviewed',
                  'created_at': self.clock(), 'expires_at': self.clock() + 300,
                  'owner': owner, 'binding': binding, 'database': database,
                  'plan': deepcopy(plan), 'baseline': reduced(baseline), 'desired': reduced(desired)}
        record['review_digest'] = digest(record)
        import json
        if len(json.dumps(record).encode()) > 4 * 1024 * 1024:
            raise SchemaApplyError('Application review exceeds 4 MiB; use smaller change sets')
        with self._store() as store:
            def save(state):
                records = state.setdefault('schema_applications', {})
                # Discard only expired, never-dispatched reviews. Retain all
                # dispatch/result receipts, including uncertain outcomes.
                for key in list(records):
                    if records[key]['state'] == 'reviewed' and records[key]['expires_at'] < self.clock():
                        del records[key]
                if len(records) >= 1000:
                    raise SchemaApplyError('Schema receipt capacity reached; administrator retention review required')
                records[record['review_id']] = record
            store.change(save)
        return self._public(record)

    def get(self, review_id, owner, binding):
        with self._store() as store:
            return self._public(self._record(store.read(), review_id, owner, binding))

    def apply(self, request, owner, binding, execute):
        if (not isinstance(request, dict) or set(request) != {'review_id', 'review_digest', 'confirmed'} or
                request['confirmed'] is not True or not isinstance(request['review_id'], str) or
                not isinstance(request['review_digest'], str)):
            raise SchemaApplyError('Explicit confirmation of a prepared schema review is required')
        with self._store() as store:
            def claim(state):
                record = self._record(state, request['review_id'], owner, binding)
                if request['review_digest'] != record['review_digest']:
                    raise SchemaApplyError('Review fingerprint does not match')
                if record['state'] != 'reviewed':
                    return None
                if self.clock() > record['expires_at']:
                    raise SchemaApplyError('Schema review expired; prepare it again')
                # Durable uncertainty precedes native access. Crash at any later
                # point is never permission to redispatch this token.
                record.update(state='unknown_outcome', dispatched_at=self.clock())
                return deepcopy(record)
            claimed = store.change(claim)
        if claimed is None:
            return self.get(request['review_id'], owner, binding)
        try:
            outcome = execute(claimed)
        except Exception as error:
            outcome = {'state': 'unknown_outcome', 'error_type': type(error).__name__}
        with self._store() as store:
            def finish(state):
                record = self._record(state, request['review_id'], owner, binding)
                record['outcome'] = outcome
                record['state'] = outcome['state']
                record['finished_at'] = self.clock()
                record.pop('baseline', None)
                record.pop('desired', None)
            store.change(finish)
        return self.get(request['review_id'], owner, binding)
