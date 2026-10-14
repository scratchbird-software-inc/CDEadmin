"""Durable, owner-bound review of a bounded DuckDB native DDN batch."""

from copy import deepcopy
import json
import uuid

from .firebird_schema_apply import SchemaApplications, SchemaApplyError
from .firebird_schema_plan import digest
from .duckdb_schema_plan import _definition, _fk_parent_definition, _root


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
                not isinstance(operations, list) or not 1 <= len(operations) <= 32 or
                preview.get('execution_sha256') != digest(operations)):
            raise SchemaApplyError('Only bounded, native-validated DuckDB operations can be reviewed')
        baseline_ids, desired_ids = set(), set()
        for operation in operations:
            identity = operation['resource_id']
            source_id = operation.get('source_resource_id', identity)
            before, after = baseline['rows'].get(source_id), desired['rows'].get(identity)
            desired_ids.add(identity)
            baseline_ids.add(source_id)
            if after is None or operation['desired_sha256'] != digest(_definition(after)):
                raise SchemaApplyError('Native desired definition differs from the reviewed plan')
            if operation['operation'] == 'rename':
                if (source_id == identity or before is None or identity in baseline['rows'] or
                        operation['baseline_sha256'] != digest(_definition(before))):
                    raise SchemaApplyError('Native rename requires an exact baseline source and absent target')
            elif before is None:
                if operation['operation'] != 'create' or operation['baseline_sha256'] is not None:
                    raise SchemaApplyError('Native creation requires an absent baseline target')
            elif operation['baseline_sha256'] != digest(_definition(before)):
                raise SchemaApplyError('Native baseline differs from the reviewed plan')
            if operation['operation'] == 'rebuild':
                for inbound_id in operation.get('affected_inbound_ids', []):
                    old_inbound = baseline['rows'].get(inbound_id)
                    new_inbound = desired['rows'].get(inbound_id)
                    if (old_inbound is None or new_inbound is None or
                            operation['baseline_inbound_sha256'].get(inbound_id) !=
                                digest(_definition(old_inbound)) or
                            operation['desired_inbound_sha256'].get(inbound_id) !=
                                digest(_definition(new_inbound))):
                        raise SchemaApplyError('Inbound child differs from reviewed plan')
                    baseline_ids.add(inbound_id)
                    desired_ids.add(inbound_id)
                for macro_id in operation.get('affected_macro_ids', []):
                    old_macro = baseline['rows'].get(macro_id)
                    new_macro = desired['rows'].get(macro_id)
                    if (old_macro is None or new_macro is None or
                            operation['baseline_macro_sha256'].get(macro_id) !=
                                digest(_definition(old_macro)) or
                            operation['desired_macro_sha256'].get(macro_id) !=
                                digest(_definition(new_macro))):
                        raise SchemaApplyError('Preserved macro differs from reviewed plan')
                    baseline_ids.add(macro_id)
                    desired_ids.add(macro_id)
                for view_id in operation.get('affected_view_ids', []):
                    old_view = baseline['rows'].get(view_id)
                    new_view = desired['rows'].get(view_id)
                    if (old_view is None or new_view is None or
                            operation['baseline_view_sha256'].get(view_id) !=
                                digest(_definition(old_view)) or
                            operation['desired_view_sha256'].get(view_id) !=
                                digest(_definition(new_view))):
                        raise SchemaApplyError('Preserved view differs from reviewed plan')
                    baseline_ids.add(view_id)
                    desired_ids.add(view_id)
                for column_id in operation.get('affected_view_column_ids', []):
                    old_column = baseline['rows'].get(column_id)
                    new_column = desired['rows'].get(column_id)
                    if (old_column is None or new_column is None or
                            operation['baseline_view_column_sha256'].get(column_id) !=
                                digest(_definition(old_column)) or
                            operation['desired_view_column_sha256'].get(column_id) !=
                                digest(_definition(new_column))):
                        raise SchemaApplyError('Preserved view column differs from reviewed plan')
                    baseline_ids.add(column_id)
                    desired_ids.add(column_id)
                for column_id in operation.get('affected_column_ids', []):
                    old_column = baseline['rows'].get(column_id)
                    new_column = desired['rows'].get(column_id)
                    if (new_column is None or
                            (old_column is None and column_id not in
                                operation.get('added_column_ids', [])) or
                            operation['baseline_column_sha256'].get(column_id) !=
                                (digest(_definition(old_column)) if old_column else None) or
                            operation['desired_column_sha256'].get(column_id) !=
                                digest(_definition(new_column))):
                        raise SchemaApplyError('Staged rebuild column facts differ from reviewed plan')
                    if old_column is not None:
                        baseline_ids.add(column_id)
                    desired_ids.add(column_id)
                for child_id in operation['affected_child_ids']:
                    old_child = baseline['rows'].get(child_id)
                    new_child = desired['rows'].get(child_id)
                    if old_child is not None:
                        baseline_ids.add(child_id)
                    if new_child is not None:
                        desired_ids.add(child_id)
                    if (operation['baseline_child_sha256'].get(child_id) !=
                            (digest(_definition(old_child)) if old_child else None) or
                            operation['desired_child_sha256'].get(child_id) !=
                            (digest(_definition(new_child)) if new_child else None)):
                        raise SchemaApplyError('Constraint rebuild child facts differ from reviewed plan')
                for index_id in operation['affected_index_ids']:
                    old_index = baseline['rows'].get(index_id)
                    new_index = desired['rows'].get(index_id)
                    if (old_index is None or new_index is None or
                            operation['baseline_index_sha256'].get(index_id) !=
                                digest(_definition(old_index)) or
                            operation['desired_index_sha256'].get(index_id) !=
                                digest(_definition(new_index))):
                        raise SchemaApplyError('Constraint rebuild index facts differ from reviewed plan')
                    baseline_ids.add(index_id)
                    desired_ids.add(index_id)
                for parent_id, parent_sha in operation.get('fk_parent_sha256', {}).items():
                    old_parent = baseline['rows'].get(parent_id)
                    new_parent = desired['rows'].get(parent_id)
                    if (old_parent is None or new_parent is None or
                            digest(_fk_parent_definition(old_parent)) != parent_sha or
                            digest(_fk_parent_definition(new_parent)) != parent_sha):
                        raise SchemaApplyError('Foreign-key parent differs from reviewed plan')
                    baseline_ids.add(parent_id)
                    desired_ids.add(parent_id)
        if (_root(baseline) != preview['catalog'] or _root(desired) != preview['catalog'] or
                any(baseline['provenance'].get(key) != desired['provenance'].get(key)
                    for key in ('endpoint_id', 'database_target_id'))):
            raise SchemaApplyError('Native design scope differs from the reviewed file')

        def reduced(document, selected):
            rows = {key: deepcopy(row) for key, row in document['rows'].items()
                    if row['kind'] == 'database' or key in selected}
            return {'provenance': deepcopy(document['provenance']), 'rows': rows}

        record = {'review_id': str(uuid.uuid4()), 'state': 'reviewed',
            'created_at': self.clock(), 'expires_at': self.clock() + 300,
            'owner': owner, 'binding': binding, 'database': database,
            'plan': deepcopy(preview), 'baseline': reduced(baseline, baseline_ids),
            'desired': reduced(desired, desired_ids),
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
