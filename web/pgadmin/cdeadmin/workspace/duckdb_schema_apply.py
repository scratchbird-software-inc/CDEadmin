"""Durable, owner-bound review of one DuckDB native DDN statement."""

from copy import deepcopy
import json
import uuid

from .firebird_schema_apply import SchemaApplications, SchemaApplyError
from .firebird_schema_plan import digest
from .duckdb_schema_plan import _definition, _root


class DuckDBSchemaApplications(SchemaApplications):
    def review(self, preview, baseline, desired, owner, binding, database, *, file_identity=None):
        if file_identity is not None and (not isinstance(file_identity, list) or
                len(file_identity) != 2 or any(type(part) is not int or part < 0 for part in file_identity)):
            raise SchemaApplyError('Native file identity must be an exact device/inode pair')
        operations = preview.get('operations')
        if (preview.get('format') != 'scratchrobin.duckdb.schema-plan@1' or
                preview.get('ready_for_review') is not True or
                preview.get('application_supported') is not True or
                preview.get('native_grammar_validated') is not True or
                not isinstance(operations, list) or len(operations) != 1 or
                preview.get('execution_sha256') != digest(operations)):
            raise SchemaApplyError('Only one admitted, native-validated DuckDB operation can be reviewed')
        operation = operations[0]
        identity = operation['resource_id']
        before, after = baseline['rows'].get(identity), desired['rows'].get(identity)
        if after is None or operation['desired_sha256'] != digest(_definition(after)):
            raise SchemaApplyError('Native desired definition differs from the reviewed plan')
        if before is None:
            if operation['operation'] != 'create' or operation['baseline_sha256'] is not None:
                raise SchemaApplyError('Native creation requires an absent baseline target')
        elif operation['baseline_sha256'] != digest(_definition(before)):
            raise SchemaApplyError('Native baseline differs from the reviewed plan')
        if (_root(baseline) != preview['catalog'] or _root(desired) != preview['catalog'] or
                any(baseline['provenance'].get(key) != desired['provenance'].get(key)
                    for key in ('endpoint_id', 'database_target_id'))):
            raise SchemaApplyError('Native design scope differs from the reviewed file')

        def reduced(document):
            rows = {key: deepcopy(row) for key, row in document['rows'].items()
                    if row['kind'] == 'database' or key == identity}
            return {'provenance': deepcopy(document['provenance']), 'rows': rows}

        record = {'review_id': str(uuid.uuid4()), 'state': 'reviewed',
            'created_at': self.clock(), 'expires_at': self.clock() + 300,
            'owner': owner, 'binding': binding, 'database': database,
            'plan': deepcopy(preview), 'baseline': reduced(baseline), 'desired': reduced(desired),
            'file_identity': file_identity}
        record['review_digest'] = digest(record)
        if len(json.dumps(record, ensure_ascii=False).encode()) > 4 * 1024 * 1024:
            raise SchemaApplyError('Native review exceeds 4 MiB')
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
