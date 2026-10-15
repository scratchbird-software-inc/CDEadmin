"""Owner-bound PostgreSQL review receipts using the shared durable claim store."""
from copy import deepcopy
import json
import uuid
from .firebird_schema_apply import SchemaApplications, SchemaApplyError
from .firebird_schema_plan import digest


class PostgreSQLSchemaApplications(SchemaApplications):
    def review(self, plan, baseline, desired, owner, binding, database):
        if (not plan.get('ready_for_review') or not plan.get('application_supported') or
                not plan.get('operations') or plan.get('execution_sha256') != digest(plan['operations'])):
            raise SchemaApplyError('Only an admitted, unblocked native plan can be prepared')
        ids = {operation.get('parent_resource_id', operation['resource_id']) for operation in plan['operations']}
        # Table-owned mutations need both the child and its exact owning table
        # in the persisted baseline. Otherwise reduction loses the authority
        # needed to revalidate a trigger/rule/policy after receipt reload.
        ids.update('postgresql:pg_class:' + str(operation['lock_target']['oid'])
                   for operation in plan['operations'] if operation.get('lock_target'))
        def reduced(document):
            return {'provenance': deepcopy(document['provenance']),
                    'rows': {key: deepcopy(value) for key, value in document['rows'].items() if key in ids}}
        record = {'review_id': str(uuid.uuid4()), 'state': 'reviewed',
                  'created_at': self.clock(), 'expires_at': self.clock() + 300,
                  'owner': owner, 'binding': binding, 'database': database,
                  'plan': deepcopy(plan), 'baseline': reduced(baseline), 'desired': reduced(desired)}
        record['review_digest'] = digest(record)
        if len(json.dumps(record).encode()) > 4 * 1024 * 1024:
            raise SchemaApplyError('Application review exceeds 4 MiB; use a smaller change set')
        with self._store() as store:
            def save(state):
                records = state.setdefault('schema_applications', {})
                for key in list(records):
                    if records[key]['state'] == 'reviewed' and records[key]['expires_at'] < self.clock():
                        del records[key]
                if len(records) >= 1000:
                    raise SchemaApplyError('Schema receipt capacity reached; retention review required')
                records[record['review_id']] = record
            store.change(save)
        return self._public(record)
