"""Owner-bound MySQL review receipts; native DDL is independently committed."""
from copy import deepcopy
import json
import uuid

from .firebird_schema_apply import SchemaApplications, SchemaApplyError
from .firebird_schema_plan import digest
from .mysql_schema_plan import schema


class MySQLSchemaApplications(SchemaApplications):
    def review(self, plan, baseline, desired, owner, binding, database):
        operations = plan.get('operations', [])
        if (plan.get('format') != 'scratchrobin.mysql.schema-plan@1' or
                not plan.get('ready_for_review') or not plan.get('native_grammar_validated') or
                len(operations) != 1 or operations[0].get('operation') not in {'alter', 'drop'} or
                plan.get('execution_sha256') != digest(operations) or
                not plan.get('server_uuid')):
            raise SchemaApplyError('Prepare one native-validated existing-table alteration or removal')
        operation = operations[0]
        key = operation['resource_id']
        before = baseline['rows'].get(key)
        if before is None or digest(schema(before)) != operation['baseline_schema_sha256']:
            raise SchemaApplyError('Exact native baseline is required')
        def reduced(document):
            row = document['rows'][key]
            native = row['native']
            return {'rows': {key: {**deepcopy({field: value for field, value in row.items() if field != 'native'}),
                'native': {field: deepcopy(value) for field, value in native.items() if field in {
                    'database', 'navigator_parent_resource_id', 'definition', 'definition_context', 'mysql_change'}}}}}
        record = {'review_id': str(uuid.uuid4()), 'state': 'reviewed',
                  'created_at': self.clock(), 'expires_at': self.clock() + 300,
                  'owner': owner, 'binding': binding, 'database': database,
                  'plan': deepcopy(plan), 'baseline': reduced(baseline), 'desired': reduced(desired)}
        record['review_digest'] = digest(record)
        if len(json.dumps(record).encode('utf8')) > 4 * 1024 * 1024:
            raise SchemaApplyError('Application review exceeds 4 MiB')
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
