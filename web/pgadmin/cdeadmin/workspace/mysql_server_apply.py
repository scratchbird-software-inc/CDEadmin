"""Durable one-use server change reviews and ordered native acknowledgements."""
from copy import deepcopy
import json
import uuid

from .firebird_schema_apply import SchemaApplications, SchemaApplyError
from .firebird_schema_plan import digest


class MySQLServerApplications(SchemaApplications):
    format = 'scratchrobin.mysql.server-plan@1'
    def recent(self, owner, binding):
        with self._store() as store:
            records = [row for row in store.read().get('schema_applications', {}).values()
                       if row['owner'] == owner and row['binding'] == binding]
            return [self._public(row) for row in sorted(records, key=lambda row: row['created_at'], reverse=True)[:20]]

    def review(self, plan, baseline, desired, owner, binding):
        operations = plan.get('operations', [])
        if (plan.get('format') != self.format or not plan.get('ready_for_review') or
                not 1 <= len(operations) <= 32 or plan.get('execution_sha256') != digest(operations) or
                len({item['resource_id'] for item in operations}) != len(operations)):
            raise SchemaApplyError('Prepare an unblocked native server plan with 1 to 32 distinct targets')
        keys = {item['resource_id'] for item in operations}
        guards = keys | {key for item in operations for key in item['guard_ids']}
        record = {'review_id': str(uuid.uuid4()), 'state': 'reviewed', 'owner': owner, 'binding': binding,
                  'created_at': self.clock(), 'expires_at': self.clock() + 300, 'plan': deepcopy(plan),
                  'baseline': {'rows': {key: deepcopy(row) for key, row in baseline['rows'].items() if key in guards}},
                  'desired': {'rows': {key: deepcopy(desired['rows'][key]) for key in keys}},
                  'statement_outcomes': [{'index': i, 'resource_id': item['resource_id'], 'state': 'not_dispatched'}
                                         for i, item in enumerate(operations)]}
        record['review_digest'] = digest(record)
        if len(json.dumps(record).encode()) > 4 * 1024 * 1024:
            raise SchemaApplyError('Server review exceeds 4 MiB')
        with self._store() as store:
            def save(state):
                records = state.setdefault('schema_applications', {})
                for key in list(records):
                    if records[key]['state'] == 'reviewed' and records[key]['expires_at'] < self.clock():
                        del records[key]
                if len(records) >= 1000:
                    raise SchemaApplyError('Server receipt capacity reached')
                records[record['review_id']] = record
            store.change(save)
        return self._public(record)

    def apply(self, request, owner, binding, execute):
        def run(record):
            for index, operation in enumerate(record['plan']['operations']):
                def update(outcome=None):
                    with self._store() as store:
                        def change(state):
                            retained = self._record(state, record['review_id'], owner, binding)
                            entry = retained['statement_outcomes'][index]
                            if outcome is None:
                                if entry['state'] != 'not_dispatched':
                                    raise SchemaApplyError('Server statement cannot be dispatched twice')
                                entry.update(state='unknown_outcome', dispatched_at=self.clock())
                            else:
                                entry.update(state=outcome['state'], outcome=deepcopy(outcome), finished_at=self.clock())
                        store.change(change)
                update()
                try:
                    outcome = execute(record, operation)
                except Exception as error:
                    outcome = {'state': 'unknown_outcome', 'error_type': type(error).__name__}
                update(outcome)
                if outcome['state'] != 'acknowledged' or not outcome.get('rediscovery_verified'):
                    break
            entries = self.get(record['review_id'], owner, binding)['statement_outcomes']
            complete = all(item['state'] == 'acknowledged' and item['outcome'].get('rediscovery_verified') for item in entries)
            return {'state': 'acknowledged' if complete else 'unknown_outcome' if any(item['state'] == 'unknown_outcome' for item in entries)
                    else 'partially_applied' if any(item['state'] == 'acknowledged' for item in entries) else 'not_applied',
                    'statement_outcomes': entries, 'rediscovery_verified': complete, 'automatic_retry': False,
                    'durability': 'native-operation-specific', 'transactional_rollback_available': False}
        return super().apply(request, owner, binding, run)
