"""Once-only retained SQLite DDL dispatch and owner-scoped durable receipts (SQ-AUD-14 sharded store)."""
from copy import deepcopy
import json
from pathlib import Path
import threading
import uuid

from ..operations.fileio import private_directory, publish_private_file
from .firebird_schema_apply import SchemaApplications, SchemaApplyError
from .firebird_schema_plan import digest
from . import sqlite_retained_schema as native

_INDEX_KEYS = (
    'review_id',
    'state',
    'created_at',
    'expires_at',
    'owner',
    'binding',
    'database',
    'session_id',
    'review_digest',
    'native_context_sha256',
    'native_session_release_confirmed',
    'dispatched_at',
    'native_acknowledged_at',
    'finished_at',
    'cancel_requested_at',
)


class SQLiteRetainedApplications(SchemaApplications):
    IMMUTABLE = {
        'review_id', 'created_at', 'expires_at', 'owner', 'binding', 'database', 'session_id',
        'plan', 'baseline', 'desired', 'native_context', 'native_context_sha256',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._jobs = {}
        self._completed = {}

    def _records_dir(self) -> Path:
        d = Path(str(self.path) + '.records')
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_directory(d)
        return d

    def _record_file(self, review_id: str) -> Path:
        safe = str(review_id).strip()
        if not safe or '/' in safe or '\\' in safe or '..' in safe:
            raise SchemaApplyError('Invalid retained review identifier')
        return self._records_dir() / f'{safe}.json'

    def _write_sidecar(self, record: dict) -> dict:
        rid = record['review_id']
        target = self._record_file(rid)
        staging = target.with_name(f'.{rid}.{uuid.uuid4().hex}.tmp')
        encoded = json.dumps(record, ensure_ascii=False, separators=(',', ':')).encode('utf8')
        publish_private_file(target, encoded, staging=staging)
        summary = {k: deepcopy(record[k]) for k in _INDEX_KEYS if k in record}
        summary['_sidecar'] = True
        return summary

    def _load_full_record(self, state: dict, review_id: str, owner, binding) -> dict:
        entry = self._record(state, review_id, owner, binding)
        if not entry.get('_sidecar'):
            return deepcopy(entry)
        target = self._record_file(review_id)
        if not target.is_file():
            raise SchemaApplyError('Retained SQLite receipt payload is unavailable')
        full = json.loads(target.read_text(encoding='utf8'))
        if full.get('owner') != owner or full.get('binding') != binding:
            raise SchemaApplyError('Schema application review is unavailable for this owner and target')
        for k in _INDEX_KEYS:
            if k in entry:
                full[k] = deepcopy(entry[k])
        return full

    @staticmethod
    def _public(record):
        value = SchemaApplications._public(record)
        value.pop('native_context', None)
        value.pop('_sidecar', None)
        value['acknowledgement_scope'] = 'DDL acknowledgement within its original caller transaction; later commit/rollback is not inferred'
        return value

    def review(self, plan, baseline, desired, native_context, owner, binding, database, session):
        if (
            plan.get('format') != native.FORMAT
            or not plan.get('ready_for_review')
            or not plan.get('application_supported')
            or plan.get('execution_sha256') != digest(plan.get('operations'))
            or plan.get('provider_session_id') != session
            or not native_context.get('in_transaction')
        ):
            raise SchemaApplyError('Begin an original caller transaction and prepare a native retained DDL preview')
        record = {
            'review_id': str(uuid.uuid4()),
            'state': 'reviewed',
            'created_at': self.clock(),
            'expires_at': self.clock() + 300,
            'owner': owner,
            'binding': binding,
            'database': database,
            'session_id': session,
            'plan': deepcopy(plan),
            'baseline': deepcopy(baseline),
            'desired': deepcopy(desired),
            'native_context': deepcopy(native_context),
            'native_context_sha256': digest(native_context),
            'native_session_release_confirmed': True,
        }
        record['review_digest'] = digest({key: record[key] for key in self.IMMUTABLE})
        if len(json.dumps(record, ensure_ascii=False).encode('utf8')) > 4 * 1024 * 1024:
            raise SchemaApplyError('Retained SQLite review exceeds 4 MiB; use a smaller native design')
        with self._store() as store:
            expired_ids = []

            def save(state):
                records = state.setdefault('schema_applications', {})
                now = self.clock()
                for key in list(records):
                    if records[key]['state'] == 'reviewed' and records[key]['expires_at'] < now:
                        expired_ids.append(key)
                        del records[key]
                if len(records) >= 1000:
                    raise SchemaApplyError('Retained SQLite receipt capacity reached')
                records[record['review_id']] = self._write_sidecar(record)

            store.change(save)
            for exp_id in expired_ids:
                try:
                    self._record_file(exp_id).unlink(missing_ok=True)
                except OSError:
                    pass
        return self._public(record)

    def _update(self, identity, owner, binding, fields):
        if set(fields) & self.IMMUTABLE:
            raise SchemaApplyError('Retained review identities and native stages are immutable')
        with self._store() as store:
            def upd(state):
                full = self._load_full_record(state, identity, owner, binding)
                full.update(deepcopy(fields))
                state['schema_applications'][identity] = self._write_sidecar(full)

            store.change(upd)

    def get(self, identity, owner, binding):
        with self.lock:
            return self._get_locked(identity, owner, binding)

    def _get_locked(self, identity, owner, binding):
        with self._store() as store:
            value = self._public(self._load_full_record(store.read(), identity, owner, binding))
        with self.lock:
            completed = self._completed.get(identity)
            job = self._jobs.get(identity)
            value['worker_active'] = bool(job is not None and not job['done'].is_set())
        if completed is not None and completed['owner'] == owner and completed['binding'] == binding:
            try:
                self._update(identity, owner, binding, completed['fields'])
                with self.lock:
                    self._completed.pop(identity, None)
                value.update(deepcopy(completed['fields']))
            except Exception:
                value.update(deepcopy(completed['fields']))
                value['durable_completion_confirmed'] = False
        return value

    def start(self, request, owner, binding, session, client, handle, endpoint, revision):
        if (
            not isinstance(request, dict)
            or set(request) != {'review_id', 'review_digest', 'confirmed'}
            or request['confirmed'] is not True
        ):
            raise SchemaApplyError('Confirm the exact retained native DDL review')
        with self._store() as store:
            def claim(state):
                entry = self._record(state, request['review_id'], owner, binding)
                if entry['review_digest'] != request['review_digest']:
                    raise SchemaApplyError('Retained review fingerprint does not match')
                if entry['state'] != 'reviewed':
                    return None
                record = self._load_full_record(state, request['review_id'], owner, binding)
                if digest({key: record[key] for key in self.IMMUTABLE}) != record['review_digest']:
                    raise SchemaApplyError('Retained review contents changed after confirmation')
                if record['session_id'] != session:
                    raise SchemaApplyError('Retained DDL belongs to another original query connection')
                if self.clock() > record['expires_at']:
                    raise SchemaApplyError('Retained DDL review expired')
                # No native SQL follows until this uncertainty is durable.
                record.update(
                    state='unknown_outcome',
                    dispatched_at=self.clock(),
                    native_session_release_confirmed=False,
                )
                state['schema_applications'][request['review_id']] = self._write_sidecar(record)
                return record

            record = store.change(claim)
        if record is None:
            return self.get(request['review_id'], owner, binding)
        stop = threading.Event()
        done = threading.Event()
        identity = record['review_id']
        with self.lock:
            self._jobs[identity] = {'owner': owner, 'binding': binding, 'stop': stop, 'done': done, 'handle': handle}
        client._busy.add(id(handle))

        def worker():
            outcome = None
            try:
                def acknowledge(value):
                    self._update(identity, owner, binding, {
                        'state': value['state'],
                        'outcome': value,
                        'native_acknowledged_at': self.clock(),
                    })

                outcome = native.apply(client, handle, record, endpoint, session, revision, cancel=stop, acknowledge=acknowledge)
            except BaseException as error:
                outcome = {'state': 'unknown_outcome', 'error_type': type(error).__name__, 'commit_dispatched': False}
                client._uncertain.add(id(handle))
            finally:
                with client._lock:
                    client._busy.discard(id(handle))
                    fields = {
                        'state': outcome['state'],
                        'outcome': outcome,
                        'finished_at': self.clock(),
                        'native_session_release_confirmed': True,
                    }
                    with self.lock:
                        self._completed[identity] = {'owner': owner, 'binding': binding, 'fields': fields}
                    try:
                        self._update(identity, owner, binding, fields)
                        with self.lock:
                            self._completed.pop(identity, None)
                    except Exception:
                        pass
                    finally:
                        done.set()
                        with self.lock:
                            self._jobs.pop(identity, None)

        thread = threading.Thread(target=worker, daemon=True, name='cdeadmin-sqlite-retained-ddl')
        try:
            thread.start()
        except BaseException:
            client._busy.discard(id(handle))
            with self.lock:
                self._jobs.pop(identity, None)
            self._update(identity, owner, binding, {
                'state': 'not_dispatched',
                'finished_at': self.clock(),
                'native_session_release_confirmed': True,
                'outcome': {'state': 'not_dispatched', 'reason': 'Native worker could not start'},
            })
            raise
        return self.get(identity, owner, binding)

    def cancel(self, identity, owner, binding):
        self.get(identity, owner, binding)
        requested = False
        with self.lock:
            job = self._jobs.get(identity)
            if job is not None and job['owner'] == owner and job['binding'] == binding and not job['done'].is_set():
                job['stop'].set()
                job['handle'].interrupt()
                requested = True
        if requested:
            self._update(identity, owner, binding, {'cancel_requested_at': self.clock()})
        return self.get(identity, owner, binding)

    def list(self, owner, binding, *, offset=0, limit=25):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise SchemaApplyError('Select a retained receipt page of at most 100 entries')
        with self._store() as store:
            state = store.read()
            matching = sorted(
                (
                    entry for entry in state.get('schema_applications', {}).values()
                    if entry['owner'] == owner and entry['binding'] == binding
                ),
                key=lambda row: row['created_at'],
                reverse=True,
            )
            page = [
                self._public(self._load_full_record(state, entry['review_id'], owner, binding))
                for entry in matching[offset:offset + limit]
            ]
            return {
                'receipts': page,
                'offset': offset,
                'limit': limit,
                'total': len(matching),
                'more': offset + limit < len(matching),
                'automatic_retry': False,
            }

    def remove(self, identity, owner, binding, *, confirmed=False):
        with self._store() as store:
            def rem(state):
                row = self._record(state, identity, owner, binding)
                if row['state'] != 'reviewed' and (
                    confirmed is not True
                    or row['state'] == 'unknown_outcome'
                    or not row.get('native_session_release_confirmed')
                ):
                    raise SchemaApplyError('Confirm completed receipt removal; unresolved native dispatches must be retained')
                del state['schema_applications'][identity]

            store.change(rem)
            try:
                self._record_file(identity).unlink(missing_ok=True)
            except OSError:
                pass
        return {'removed': True, 'automatic_retry': False}
