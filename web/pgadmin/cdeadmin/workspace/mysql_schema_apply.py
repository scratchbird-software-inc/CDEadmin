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
                not 1 <= len(operations) <= 32 or
                any(op.get('kind') not in {'table', 'view', 'library', 'event', 'procedure', 'function', 'trigger', 'database', 'materialized-view'} or op.get('operation') not in {'create', 'alter', 'drop'} for op in operations) or
                len({op['resource_id'] for op in operations}) != len(operations) or
                sum(len(op['source'].encode('utf8')) for op in operations) > 1024 * 1024 or
                plan.get('execution_sha256') != digest(operations) or
                not plan.get('server_uuid')):
            raise SchemaApplyError('Prepare 1 to 32 distinct native-validated table/view/library/event/routine operations within 1 MiB')
        ids = {operation['resource_id'] for operation in operations}
        for operation in operations:
            key = operation['resource_id']
            before = baseline['rows'].get(key)
            if operation['operation'] == 'create':
                if before is not None or operation['baseline_schema_sha256'] is not None:
                    raise SchemaApplyError('Native creation requires an absent baseline target')
            elif before is None or digest(schema(before)) != operation['baseline_schema_sha256']:
                raise SchemaApplyError('Exact native baseline is required')
            if digest(schema(desired['rows'][key])) != operation['desired_schema_sha256']:
                raise SchemaApplyError('Exact desired native definition is required')
        def reduced(document):
            return {'rows': {key: {**deepcopy({field: value for field, value in row.items() if field != 'native'}),
                'native': {field: deepcopy(value) for field, value in row['native'].items() if field in {
                    'database', 'navigator_parent_resource_id', 'definition', 'definition_context', 'mysql_change', 'trigger_identity'}}}
                for key, row in document['rows'].items() if key in ids}}
        record = {'review_id': str(uuid.uuid4()), 'state': 'reviewed',
                  'created_at': self.clock(), 'expires_at': self.clock() + 300,
                  'owner': owner, 'binding': binding, 'database': database,
                  'plan': deepcopy(plan), 'baseline': reduced(baseline), 'desired': reduced(desired)}
        if len(operations) > 1:
            record['statement_outcomes'] = [{'index': index, 'resource_id': op['resource_id'],
                'state': 'not_dispatched'} for index, op in enumerate(operations)]
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


    def apply(self, request, owner, binding, execute):
        def run(record):
            operations = record['plan']['operations']
            if len(operations) == 1:
                return execute(record)
            def update(index, outcome=None):
                with self._store() as store:
                    def change(state):
                        retained = self._record(state, record['review_id'], owner, binding)
                        entry = retained['statement_outcomes'][index]
                        if outcome is None:
                            if entry['state'] != 'not_dispatched':
                                raise SchemaApplyError('A batch statement cannot be dispatched twice')
                            entry.update(state='unknown_outcome', dispatched_at=self.clock())
                        else:
                            entry.update(state=outcome['state'], outcome=deepcopy(outcome), finished_at=self.clock())
                    store.change(change)
            for index, operation in enumerate(operations):
                update(index)  # Durable uncertainty precedes this native call.
                key = operation['resource_id']
                step = deepcopy(record)
                step.pop('statement_outcomes', None)
                step['plan']['operations'] = [deepcopy(operation)]
                step['plan']['execution_sha256'] = digest(step['plan']['operations'])
                for field in ('baseline', 'desired'):
                    step[field]['rows'] = {key: step[field]['rows'][key]} if key in step[field]['rows'] else {}
                try:
                    outcome = execute(step)
                except Exception as error:
                    outcome = {'state': 'unknown_outcome', 'error_type': type(error).__name__}
                update(index, outcome)  # Keep the observed prefix before advancing.
                if outcome['state'] != 'committed' or not outcome.get('rediscovery_verified'):
                    break
            entries = self.get(record['review_id'], owner, binding)['statement_outcomes']
            completed = sum(entry['state'] == 'committed' for entry in entries)
            uncertain = any(entry['state'] == 'unknown_outcome' for entry in entries)
            state = ('unknown_outcome' if uncertain else 'committed' if completed == len(entries)
                     else 'partially_committed' if completed else 'not_dispatched')
            return {'state': state, 'statement_outcomes': entries, 'completed_statements': completed,
                    'rediscovery_verified': all(entry['state'] == 'committed' and
                        entry.get('outcome', {}).get('rediscovery_verified') for entry in entries),
                    'transactional_rollback_available': False, 'automatic_retry': False}
        return super().apply(request, owner, binding, run)
