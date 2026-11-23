"""Once-only retained DuckDB DDL dispatch and owner-scoped durable receipts (DU-AUD-17)."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import uuid

from ..operations.fileio import private_directory, publish_private_file
from .firebird_schema_apply import SchemaApplications, SchemaApplyError
from .firebird_schema_plan import digest
from . import duckdb_retained_schema as native


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
)


class DuckDBRetainedApplications(SchemaApplications):
    IMMUTABLE = {
        'review_id', 'created_at', 'expires_at', 'owner', 'binding', 'database',
        'session_id', 'plan', 'baseline', 'desired', 'native_context',
        'native_context_sha256',
    }

    def _records_dir(self) -> Path:
        d = Path(str(self.path) + '.records')
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_directory(d)
        return d

    def _record_file(self, review_id: str) -> Path:
        safe = str(review_id).strip()
        if not safe or '/' in safe or '\\' in safe or '..' in safe:
            raise SchemaApplyError('Invalid retained DuckDB review identifier')
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
            raise SchemaApplyError('Retained DuckDB receipt payload is unavailable')
        full = json.loads(target.read_text(encoding='utf8'))
        if full.get('owner') != owner or full.get('binding') != binding:
            raise SchemaApplyError('Schema application review is unavailable for this owner and target')
        for k in _INDEX_KEYS:
            if k in entry:
                full[k] = deepcopy(entry[k])
        return full

    @staticmethod
    def _public(record: dict) -> dict:
        value = SchemaApplications._public(record)
        value.pop('native_context', None)
        value.pop('_sidecar', None)
        value['acknowledgement_scope'] = (
            'DDL acknowledgement within its original caller DuckDB transaction; '
            'later commit/rollback is not inferred'
        )
        return value

    def review(self, plan, baseline, desired, native_context, owner, binding, database, session):
        if (plan.get('format') != native.FORMAT or
                not plan.get('ready_for_review') or
                not plan.get('application_supported') or
                plan.get('execution_sha256') != digest(plan.get('operations')) or
                plan.get('provider_session_id') != session or
                native_context.get('viability') != 'viable'):
            raise SchemaApplyError(
                'Retained DuckDB review requires a viable original-session preview; '
                'independent-file migration plans are non-transferable'
            )
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
            raise SchemaApplyError('Retained DuckDB review exceeds 4 MiB')
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
                    raise SchemaApplyError('Retained DuckDB receipt capacity reached')
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
        with self._store() as store:
            return self._public(self._load_full_record(store.read(), identity, owner, binding))

    def apply(self, request, owner, binding, session, client, handle, endpoint, revision):
        if (not isinstance(request, dict) or
                set(request) != {'review_id', 'review_digest', 'confirmed'} or
                request['confirmed'] is not True):
            raise SchemaApplyError('Confirm the exact retained DuckDB DDL review')

        with self._store() as store:
            def claim(state):
                entry = self._record(state, request['review_id'], owner, binding)
                if entry['review_digest'] != request['review_digest']:
                    raise SchemaApplyError('Retained DuckDB review fingerprint does not match')
                if entry['state'] != 'reviewed':
                    return None
                record = self._load_full_record(state, request['review_id'], owner, binding)
                if digest({key: record[key] for key in self.IMMUTABLE}) != record['review_digest']:
                    raise SchemaApplyError('Retained DuckDB review contents changed after confirmation')
                if record['session_id'] != session:
                    raise SchemaApplyError('Retained DuckDB DDL belongs to another original query connection')
                if self.clock() > record['expires_at']:
                    raise SchemaApplyError('Retained DuckDB DDL review expired')
                # Persist unknown_outcome durability before dispatching SQL (one-shot, no replay!)
                record.update(
                    state='unknown_outcome',
                    dispatched_at=self.clock(),
                    native_session_release_confirmed=False,
                )
                state['schema_applications'][request['review_id']] = self._write_sidecar(record)
                return record

            record = store.change(claim)

        if record is None:
            existing = self.get(request['review_id'], owner, binding)
            existing['replay_refused'] = True
            return existing

        identity = record['review_id']
        client._busy.add(id(handle))
        try:
            def acknowledge(value):
                self._update(identity, owner, binding, {
                    'state': value['state'],
                    'outcome': value,
                    'native_acknowledged_at': self.clock(),
                })

            outcome = native.apply(
                client, handle, record, endpoint, session, revision, acknowledge=acknowledge
            )
        except BaseException as err:
            outcome = {
                'state': 'unknown_outcome',
                'error_type': type(err).__name__,
                'commit_dispatched': False,
                'rollback_dispatched': False,
            }
            client._observe(handle, blocked=True)
        finally:
            client._busy.discard(id(handle))
            self._update(identity, owner, binding, {
                'state': outcome['state'],
                'outcome': outcome,
                'finished_at': self.clock(),
                'native_session_release_confirmed': True,
            })
        return self.get(identity, owner, binding)

    def list(self, owner, binding, *, offset=0, limit=25):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise SchemaApplyError('Select a retained DuckDB receipt page of at most 100 entries')
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
                    confirmed is not True or
                    row['state'] == 'unknown_outcome' or
                    not row.get('native_session_release_confirmed')
                ):
                    raise SchemaApplyError(
                        'Confirm completed receipt removal; unresolved native dispatches must be retained'
                    )
                del state['schema_applications'][identity]

            store.change(rem)
            try:
                self._record_file(identity).unlink(missing_ok=True)
            except OSError:
                pass
        return {'removed': True, 'automatic_retry': False}
