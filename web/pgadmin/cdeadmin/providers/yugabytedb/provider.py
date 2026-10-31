"""YugabyteDB 2025.2.2.2 YSQL distributed provider."""

import copy
from collections.abc import Mapping
from dataclasses import replace
import json
import re

from pgadmin.cdeadmin.sdk import (
    ActualEnginePilotProvider,
    PilotProfile,
    RelationalClientError,
)
from ..distributed_control_plane import DistributedSQLControlPlane
from ..distributed_sql import (
    create_sql_client,
    optional_rows,
    postgresql_catalog,
    postgresql_constraint_details,
    resource,
    sql_administration,
)
from . import (
    databases, indexes as index_sql, objects, policies, routines, sequences,
    tables as tables_sql, tablespaces, types, views,
)
from .driver import YugabyteDBYSQLClient
from ..relational_admin import RelationalAdministration
from ..cockroachdb.policies import form as shared_policy_form
from .control_plane import (
    OPERATIONS as CONTROL_OPERATIONS,
    catalog_resources as control_catalog_resources,
    cancel_action,
    compile_action,
    execute_action,
    inspect_action,
    post_validate_action,
)


PROFILE = PilotProfile(
    'org.cdeadmin.yugabytedb', 'yugabytedb-native', 'yugabytedb',
    'YugabyteDB', '2025.2.2.2', 'postgresql_wire',
    'distributed-relational', 'ysql', 'Yugabyte SQL',
    'yugabytedb-distributed-transaction-native', 'tabular',
    (
        'universe', 'cluster', 'node', 'region', 'zone', 'database',
        'schema', 'table', 'column', 'index', 'constraint', 'sequence',
        'view', 'materialized-view', 'domain', 'type', 'function',
        'procedure', 'trigger', 'extension', 'partition', 'tablespace',
        'tablet', 'tserver', 'master', 'placement-policy', 'user', 'role',
        'privilege', 'row-policy', 'changefeed', 'snapshot', 'schedule',
        'xcluster-replication',
    ),
    ('ysqlsh', 'yb-admin', 'backup-restore'),
    parameter_shape='object-or-array',
    parameter_hint='Named or positional bindings; exact type/value envelopes',
    semantic_sql_dialect={
        'contract_complete': True,
        'language_profile': 'ysql', 'quote_open': '"',
        'quote_close': '"', 'supports_rollup': True,
        'rollup_style': 'function', 'limit_style': 'limit',
        'true_literal': 'TRUE', 'false_literal': 'FALSE',
        'time_operations': (
            'as_of', 'range', 'period_to_date', 'period_comparison',
        ),
        'window_operations': (
            'running_sum', 'moving_sum', 'moving_average', 'lag', 'delta',
            'percent_change', 'rank', 'dense_rank',
        ),
    },
    dialect_contract_id='yugabytedb.ysql-dialect.2025.2.2.2.v1',
    dialect_evidence=(
        'yugabytedb-2025.2.2.2-ysql-source-and-runtime-inventory',
        'yugabytedb-2025.2.2.2-ysql-native-task-live-execution',
    ),
    dialect_contract_file=(
        'yugabytedb_ysql_dialect_2025_2_2_2.json'),
    metrics_contract_file='yugabytedb_metrics_2025_2_2_2.json',
)


_BASE_ADMINISTRATION = sql_administration('yugabytedb', 'postgresql', (
    'universe', 'node', 'region', 'zone', 'tablet', 'tserver', 'master',
    'placement-policy', 'changefeed', 'snapshot', 'schedule',
    'xcluster-replication', 'row-policy',
))
_YSQL_SUPPORTED = dict(_BASE_ADMINISTRATION.dialect.supported)
_YSQL_SUPPORTED.update({
    # In place: rename, tablespace, comment (providers/yugabytedb/indexes).
    'index': frozenset({'inspect', 'create', 'alter', 'drop'}),
    # alter: rename, tablespace, comment (providers/yugabytedb/views).
    'materialized-view': frozenset({
        'inspect', 'create', 'alter', 'rename', 'drop',
    }),
    # alter: values, default, comment, rename (providers/yugabytedb/types).
    'domain': frozenset({'inspect', 'create', 'alter', 'rename', 'drop'}),
    'type': frozenset({'inspect', 'create', 'alter', 'rename', 'drop'}),
    # alter: CREATE OR REPLACE, comment, rename (yugabytedb/routines).
    'function': frozenset({'inspect', 'create', 'alter', 'drop'}),
    'procedure': frozenset({'inspect', 'create', 'alter', 'drop'}),
    # alter: CREATE OR REPLACE, rename, enable, comment (objects.py).
    'trigger': frozenset({'inspect', 'create', 'alter', 'drop'}),
    'extension': frozenset({'inspect', 'create', 'drop'}),
    # Row-level security policies (providers/yugabytedb/policies).
    'row-policy': frozenset({'inspect', 'create', 'alter', 'drop'}),
    # Partition bounds are part of CREATE TABLE in YSQL. Until the table form
    # has a complete structured bound editor, partitions remain inspect-only.
    'partition': frozenset({'inspect'}),
    # YugabyteDB 2025.2.2.2 rejects ALTER TABLESPACE ... RENAME TO and SET
    # as not supported; alter is owner and comment (yugabytedb/tablespaces).
    'tablespace': frozenset({'inspect', 'create', 'alter', 'drop'}),
})
_YSQL_DIALECT = replace(
    _BASE_ADMINISTRATION.dialect,
    supported=_YSQL_SUPPORTED,
    concept_resource_kinds={
        'servers': (
            'universe', 'cluster', 'master', 'node',
            'placement-policy', 'tablet',
        ),
        'replication_objects': ('changefeed', 'xcluster-replication'),
        'jobs_and_events': ('schedule', 'snapshot'),
    },
)


_CONTROL_ADMINISTRATION = DistributedSQLControlPlane(
    _YSQL_DIALECT, CONTROL_OPERATIONS, compile_action,
    inspector=inspect_action, canceller=cancel_action,
    post_validator=post_validate_action, action_executor=execute_action,
)


class YugabyteDBAdministration(RelationalAdministration):
    """Combine YSQL object administration with native cluster controls."""

    @staticmethod
    def _native_object(kind, operation):
        return operation in objects.OPERATIONS.get(kind, ()) or (
            kind in {'table', 'index', 'type', 'domain', 'view',
                     'materialized-view', 'sequence', 'function',
                     'procedure', 'database', 'row-policy',
                     'tablespace'} and
            operation in {'create', 'alter'}) or (
            # Dropped by signature (overloads share a name) or by table.
            operation == 'drop' and kind in {'function', 'procedure',
                                             'row-policy'})

    def _native_compile(self, request):
        draft = request.get('draft')
        if not isinstance(draft, dict):
            raise RelationalClientError('administration draft is invalid')
        if request['resource_kind'] == 'tablespace':
            if request['operation_id'] == 'create':
                return {'statements': tablespaces.create(self, draft)}
            return {'statements': tablespaces.alter(
                self, draft, request.get('target_resource'))}
        if request['resource_kind'] == 'row-policy':
            target = request.get('target_resource')
            if request['operation_id'] == 'drop':
                return {'statements': policies.drop(self, target)}
            if request['operation_id'] == 'create':
                return {'statements': policies.create(self, draft)}
            return {'statements': policies.alter(self, draft, target)}
        if request['resource_kind'] == 'database':
            if request['operation_id'] == 'create':
                return {'statements': databases.create(self, draft)}
            return {'statements': databases.alter(
                self, draft, request.get('target_resource'))}
        if request['resource_kind'] in {'function', 'procedure'}:
            kind, target = request['resource_kind'], request.get(
                'target_resource')
            if request['operation_id'] == 'drop':
                return {'statements': routines.drop(self, kind, target)}
            if request['operation_id'] == 'create':
                return {'statements': routines.create(self, kind, draft)}
            return {'statements': routines.alter(self, kind, draft, target)}
        if request['resource_kind'] == 'sequence':
            if request['operation_id'] == 'create':
                return {'statements': sequences.create(self, draft)}
            return {'statements': sequences.alter(
                self, draft, request.get('target_resource'))}
        if request['resource_kind'] in {'view', 'materialized-view'}:
            kind = request['resource_kind']
            if request['operation_id'] == 'create':
                return {'statements': views.create(self, kind, draft)}
            return {'statements': views.alter(
                self, kind, draft, request.get('target_resource'))}
        if request['resource_kind'] in {'type', 'domain'}:
            builder = {
                ('type', 'create'): lambda: types.create_type(self, draft),
                ('type', 'alter'): lambda: types.alter_type(
                    self, draft, request.get('target_resource')),
                ('domain', 'create'): lambda: types.create_domain(
                    self, draft),
                ('domain', 'alter'): lambda: types.alter_domain(
                    self, draft, request.get('target_resource')),
            }[(request['resource_kind'], request['operation_id'])]
            return {'statements': builder()}
        if request['resource_kind'] == 'index':
            if request['operation_id'] == 'create':
                return {'statements': index_sql.create(self, draft)}
            return {'statements': index_sql.alter(
                self, draft, request.get('target_resource'))}
        if request['resource_kind'] == 'table':
            if request['operation_id'] == 'create':
                return {'statements': tables_sql.create(self, draft)}
            statements, warnings = tables_sql.alter(
                self, draft, request.get('target_resource'))
            return {'statements': statements, 'warnings': warnings}
        return {'statements': objects.compile_operation(
            self, request['resource_kind'], request['operation_id'], draft,
            request.get('target_resource'))}

    def _normalize_draft(self, kind, operation, draft):
        if self._native_object(kind, operation):
            if not isinstance(draft, Mapping):
                raise RelationalClientError(
                    'administration draft is invalid')
            return dict(draft)
        return super()._normalize_draft(kind, operation, draft)

    def _form(self, kind, operation):
        if kind == 'row-policy' and operation in {'create', 'alter'}:
            value = shared_policy_form(self._field, operation)
            value['form_id'] = f'yugabytedb.row-policy.{operation}'
            value['fields'].append(self._field('comment', 'Comment', 'text'))
            if operation == 'alter':
                value['fields'][-1]['initial_value_path'] = ['comment']
            return value
        if kind == 'database' and operation in {'create', 'alter'}:
            return databases.form(self._field, operation)
        if kind in {'function', 'procedure'} and operation in {
                'create', 'alter'}:
            return routines.form(self._field, kind, operation)
        if kind == 'sequence' and operation in {'create', 'alter'}:
            return sequences.form(self._field, operation)
        if kind in {'view', 'materialized-view'} and operation in {
                'create', 'alter'}:
            return views.form(super()._form(kind, 'create')
                              if operation == 'create' else None,
                              self._field, kind, operation)
        if kind == 'index' and operation in {'create', 'alter'}:
            return index_sql.form(super()._form(kind, 'create'),
                                  self._field, operation)
        if kind == 'table' and operation in {'create', 'alter'}:
            return tables_sql.extend_form(
                super()._form(kind, operation), self._field, operation)
        if operation in objects.OPERATIONS.get(kind, ()):
            return objects.form(kind, operation, self._field)
        if operation == 'create' and kind == 'type':
            return {
                'form_id': 'type.create', 'title': 'Create YSQL type',
                'fields': [
                    self._field('name', 'Name', 'text', True),
                    self._field('parent', 'Parent schema', 'text', False),
                    self._field('type_kind', 'Type kind', 'select', True,
                                options=types.TYPE_KINDS),
                    self._field('enum_values', 'Enum values', 'json', False,
                                default=[]),
                    self._field('fields', 'Composite fields', 'json', False,
                                default=[]),
                    self._field('subtype', 'Range subtype', 'text'),
                    self._field('subtype_diff',
                                'Range subtype difference function', 'text'),
                    self._field('comment', 'Comment', 'text'),
                ],
            }
        if operation == 'alter' and kind in {'type', 'domain'}:
            fields = [self._field('name', 'Name', 'text', True)]
            if kind == 'domain':
                fields.append(self._field('default', 'Default', 'text'))
            fields.append(self._field('comment', 'Comment', 'text'))
            for item in fields:
                item['initial_value_path'] = [item['field_id']]
            return {'form_id': f'{kind}.alter',
                    'title': f'Alter YSQL {kind}', 'fields': fields,
                    'notes': 'Enum value changes are descriptor grids.'}
        if operation == 'create' and kind == 'domain':
            return {
                'form_id': 'domain.create', 'title': 'Create YSQL domain',
                'fields': [
                    self._field('name', 'Name', 'text', True),
                    self._field('parent', 'Parent schema', 'text', False),
                    self._field('base_type', 'Base type', 'text', True),
                    self._field('collation', 'Collation', 'text'),
                    self._field('default', 'Default', 'text'),
                    self._field('not_null', 'Not null', 'boolean', False,
                                default=False),
                    self._field('comment', 'Comment', 'text'),
                ],
                'notes': 'Checks are a descriptor grid (type.form.json).',
            }
        if operation == 'create' and kind == 'extension':
            return {
                'form_id': 'extension.create',
                'title': 'Install YSQL extension',
                'fields': [
                    self._field('name', 'Extension name', 'text', True),
                    self._field('schema', 'Install schema', 'text'),
                    self._field('version', 'Version', 'text'),
                    self._field('cascade', 'Install dependencies', 'boolean',
                                default=False),
                ],
            }
        if kind == 'tablespace' and operation in {'create', 'alter'}:
            return tablespaces.form(self._field, operation)
        return super()._form(kind, operation)

    def _compile(self, request):
        if self._native_object(request['resource_kind'],
                               request['operation_id']):
            compiled = self._native_compile(request)
        else:
            compiled = super()._compile(request)
        if request['resource_kind'] in {'database', 'tablespace'} and \
                request['operation_id'] in {'create', 'drop'}:
            # Live, 2025.2.2.2: "CREATE DATABASE / CREATE TABLESPACE cannot
            # run inside a transaction block" (DROP likewise).
            compiled['statements_outside_transaction'] = True
            if len(compiled.get('statements', [])) > 1:
                compiled.setdefault('warnings', []).append(
                    'These statements run outside a transaction and commit '
                    'one at a time.')
        return compiled

    def _compile_create(self, request):
        kind = request['resource_kind']
        draft = request['draft']
        options = draft.get('options') or {}
        name = self._identifier(draft['name'])
        qualified = self._new_object_name(name, options)
        if kind == 'extension':
            source = f'CREATE EXTENSION {self._quote(name)}'
            schema = options.get('schema')
            version = options.get('version')
            clauses = []
            if schema:
                clauses.append('SCHEMA ' + self._quote(
                    self._identifier(schema)
                ))
            if version:
                clauses.append('VERSION ' + self._literal(str(version)))
            if options.get('cascade'):
                clauses.append('CASCADE')
            if clauses:
                source += ' WITH ' + ' '.join(clauses)
            return [{'source': source, 'parameters': ()}]
        return super()._compile_create(request)

    def supports(self, resource_kind, operation_id):
        return _CONTROL_ADMINISTRATION.control_plane.supports(
            resource_kind, operation_id
        ) or super().supports(resource_kind, operation_id)

    def catalog(self, catalog):
        return _CONTROL_ADMINISTRATION.control_plane.apply(
            super().catalog(catalog)
        )

    def validate(self, request):
        if _CONTROL_ADMINISTRATION.control_plane.supports(
                request.get('resource_kind'), request.get('operation_id')):
            return _CONTROL_ADMINISTRATION.validate(request)
        kind = request.get('resource_kind')
        operation = request.get('operation_id')
        if self._native_object(kind, operation) and self.supports(
                kind, operation):
            try:
                self._native_compile(request)
            except RelationalClientError as error:
                return {'errors': [{'field_id': None,
                                    'code': f'invalid_ysql_{kind}',
                                    'message': str(error)}]}
            return {'errors': []}
        return super().validate(request)

    def plan(self, request):
        if _CONTROL_ADMINISTRATION.control_plane.supports(
                request.get('resource_kind'), request.get('operation_id')):
            return _CONTROL_ADMINISTRATION.plan(request)
        return super().plan(request)

    def apply(self, client, request, connection=None):
        plan = request.get('plan') or {}
        if _CONTROL_ADMINISTRATION.control_plane.supports(
                plan.get('resource_kind'), plan.get('operation_id')):
            return _CONTROL_ADMINISTRATION.apply(
                client, request, connection=connection
            )
        return super().apply(client, request, connection=connection)

    @staticmethod
    def _control_request(request):
        plan = request.get('plan') or {}
        return _CONTROL_ADMINISTRATION.control_plane.supports(
            plan.get('resource_kind'), plan.get('operation_id')
        )

    @staticmethod
    def _relational_observation(client, request):
        plan = request.get('plan') or {}
        payload = request.get('provider_payload') or {}
        route = payload.get('route')
        if not isinstance(route, Mapping):
            raise RelationalClientError(
                'YugabyteDB relational observation route is unavailable'
            )
        target = plan.get('target_resource') or {}
        draft = plan.get('draft') or {}
        operation = plan.get('operation_id')
        kind = plan.get('resource_kind')
        path = target.get('display_path')
        if operation == 'create':
            name = draft.get('name')
            if kind in {
                    'database', 'schema', 'role', 'user', 'tablespace',
                    'extension'}:
                path = [name]
            else:
                parent = draft.get('parent') or route.get('database')
                path = [parent, name] if parent else [name]
        if not isinstance(path, list) or not path or not all(
                isinstance(value, str) and value for value in path):
            raise RelationalClientError(
                'YugabyteDB relational observation target is unavailable'
            )
        resources = client.list_resources({'route': route})
        item = next((
            value for value in resources
            if value.get('resource_kind') == kind and
            value.get('display_path') == path
        ), None)
        return {
            'resource_kind': kind, 'display_path': copy.deepcopy(path),
            'present': item is not None, 'resource': copy.deepcopy(item),
            'provider_observation_only': True,
            'provider_finality_authority': True,
        }

    def inspect_operation(self, client, request):
        if not self._control_request(request):
            return self._relational_observation(client, request)
        return _CONTROL_ADMINISTRATION.inspect_operation(client, request)

    def cancel_operation(self, client, request):
        return _CONTROL_ADMINISTRATION.cancel_operation(client, request)

    def validate_operation_post_state(self, client, request):
        if not self._control_request(request):
            plan = request.get('plan') or {}
            observed = self._relational_observation(client, request)
            expected_present = plan.get('operation_id') != 'drop'
            return {
                'confirmed': observed['present'] is expected_present,
                'reason': 'yugabytedb_relational_catalog_state_observed',
                'observation': observed,
                'provider_finality_authority': True,
            }
        return _CONTROL_ADMINISTRATION.validate_operation_post_state(
            client, request
        )


ADMINISTRATION = YugabyteDBAdministration(_YSQL_DIALECT)


def _version(row):
    value = str(row[0] if row else '')
    match = re.search(
        r'(?:YugabyteDB[^\n]*?v?|YB-)(\d+\.\d+\.\d+\.\d+)',
        value,
        re.I,
    )
    if match is None:
        raise RelationalClientError('YugabyteDB version is unavailable')
    return match.group(1)


_CONSTRAINT_TYPES = {'p': 'PRIMARY KEY', 'u': 'UNIQUE', 'f': 'FOREIGN KEY',
                     'c': 'CHECK'}


def _extras(cursor, _request, generation):
    values = [resource('universe', [], 'YugabyteDB', generation)]
    excluded = "('pg_catalog', 'information_schema')"
    # From pg_constraint: information_schema.table_constraints also lists
    # each NOT NULL column as a CHECK, which is nullability, not a
    # constraint an editor should re-create.
    details = postgresql_constraint_details(cursor)
    for schema, table, name, kind, deferrable, deferred in optional_rows(
        cursor,
        'SELECT n.nspname, cl.relname, co.conname, co.contype, '
        'co.condeferrable, co.condeferred '
        'FROM pg_catalog.pg_constraint co '
        'JOIN pg_catalog.pg_class cl ON cl.oid = co.conrelid '
        'JOIN pg_catalog.pg_namespace n ON n.oid = cl.relnamespace '
        f"WHERE co.contype IN ('p', 'u', 'f', 'c') AND n.nspname NOT IN "
        f'{excluded} ORDER BY 1, 2, 3',
    ):
        key = (str(schema), str(table), str(name))
        values.append(resource(
            'constraint', [schema, table], name, generation, {
                'constraint_type': _CONSTRAINT_TYPES[str(kind)],
                'deferrable': bool(deferrable),
                'initially_deferred': bool(deferred),
                **details.get(key, {}),
            }))
    for schema, name in optional_rows(
        cursor,
        'SELECT sequence_schema, sequence_name '
        'FROM information_schema.sequences ORDER BY 1, 2',
    ):
        values.append(resource('sequence', [schema], name, generation))
    for schema, name in optional_rows(
        cursor,
        'SELECT schemaname, matviewname FROM pg_catalog.pg_matviews '
        f'WHERE schemaname NOT IN {excluded} ORDER BY 1, 2',
    ):
        values.append(resource(
            'materialized-view', [schema], name, generation
        ))
    enum_values, fields, checks = {}, {}, {}
    for schema, name, label in optional_rows(
        cursor,
        'SELECT n.nspname, t.typname, e.enumlabel FROM pg_catalog.pg_enum e '
        'JOIN pg_catalog.pg_type t ON t.oid = e.enumtypid '
        'JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace '
        'ORDER BY 1, 2, e.enumsortorder',
    ):
        enum_values.setdefault((str(schema), str(name)), []).append(
            str(label))
    for schema, name, field, field_type in optional_rows(
        cursor,
        'SELECT n.nspname, t.typname, a.attname, '
        'format_type(a.atttypid, a.atttypmod) FROM pg_catalog.pg_type t '
        'JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace '
        'JOIN pg_catalog.pg_attribute a ON a.attrelid = t.typrelid '
        "WHERE t.typtype = 'c' AND a.attnum > 0 AND NOT a.attisdropped "
        'ORDER BY 1, 2, a.attnum',
    ):
        fields.setdefault((str(schema), str(name)), []).append(
            {'name': str(field), 'type': str(field_type)})
    for schema, name, check, definition in optional_rows(
        cursor,
        'SELECT n.nspname, t.typname, co.conname, '
        'pg_get_constraintdef(co.oid) FROM pg_catalog.pg_constraint co '
        'JOIN pg_catalog.pg_type t ON t.oid = co.contypid '
        'JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace '
        'ORDER BY 1, 2, 3',
    ):
        found = re.match(r'CHECK \((.*)\)$', str(definition))
        checks.setdefault((str(schema), str(name)), []).append({
            'name': str(check),
            'expression': found.group(1) if found else str(definition)})
    for (schema, name, type_kind, base_type, not_null, default, collation,
         subtype, subtype_diff, comment) in optional_rows(
        cursor,
        'SELECT n.nspname, t.typname, t.typtype, '
        'format_type(t.typbasetype, t.typtypmod), t.typnotnull, '
        't.typdefault, co.collname, r.rngsubtype::regtype::text, '
        'NULLIF(r.rngsubdiff::text, \'-\'), '
        "obj_description(t.oid, 'pg_type') "
        'FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n '
        'ON n.oid = t.typnamespace LEFT JOIN pg_catalog.pg_class c '
        'ON c.oid = t.typrelid '
        'LEFT JOIN pg_catalog.pg_range r ON r.rngtypid = t.oid '
        'LEFT JOIN pg_catalog.pg_collation co ON co.oid = t.typcollation '
        "AND co.collname <> 'default' WHERE t.typisdefined "
        f'AND n.nspname NOT IN {excluded} AND ('
        "t.typtype IN ('d', 'e', 'r') OR (t.typtype = 'c' AND "
        "c.relkind = 'c')) ORDER BY 1, 2",
    ):
        key = (str(schema), str(name))
        comment = None if comment is None else str(comment)
        if str(type_kind) == 'd':
            values.append(resource('domain', [schema], name, generation, {
                'type_kind': 'd', 'parent': key[0],
                'base_type': str(base_type),
                'collation': None if collation is None else str(collation),
                'default': None if default is None else str(default),
                'not_null': bool(not_null), 'checks': checks.get(key, []),
                'comment': comment,
            }))
            continue
        kind = {'e': 'ENUM', 'c': 'COMPOSITE', 'r': 'RANGE'}[str(type_kind)]
        values.append(resource('type', [schema], name, generation, {
            'type_kind': kind, 'parent': key[0],
            'enum_values': enum_values.get(key, []) if kind == 'ENUM'
            else None,
            'fields': fields.get(key, []) if kind == 'COMPOSITE' else None,
            'subtype': None if subtype is None else str(subtype),
            'subtype_diff': None if subtype_diff is None
            else str(subtype_diff),
            'comment': comment,
        }))
    # Overloads share a name, so a routine's resource is name(argument
    # types); its record keeps the bare name and the signature apart.
    for (schema, name, routine_kind, types, arguments, result, names,
         modes, language, volatility, strict, security, leakproof,
         parallel, cost, rows, config, body, comment) in optional_rows(
        cursor,
        'SELECT n.nspname, p.proname, p.prokind, '
        'oidvectortypes(p.proargtypes), '
        'pg_catalog.pg_get_function_arguments(p.oid), '
        'pg_catalog.pg_get_function_result(p.oid), p.proargnames, '
        'p.proargmodes, l.lanname, p.provolatile, p.proisstrict, '
        'p.prosecdef, p.proleakproof, p.proparallel, p.procost, p.prorows, '
        "p.proconfig, p.prosrc, obj_description(p.oid, 'pg_proc') "
        'FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n '
        'ON n.oid = p.pronamespace '
        'JOIN pg_catalog.pg_language l ON l.oid = p.prolang '
        f'WHERE n.nspname NOT IN {excluded} '
        "AND p.prokind IN ('f', 'p') ORDER BY 1, 2, 4",
    ):
        kind = 'procedure' if str(routine_kind) == 'p' else 'function'
        signature = str(types or '')
        returns, returns_set = routines.returns_from(
            None if result is None else str(result))
        native = {
            'name': str(name), 'signature': signature,
            'identity_arguments': signature, 'parent': str(schema),
            'parameters': routines.parameters_from(
                str(arguments or ''), None if result is None
                else str(result), names, modes),
            'language': 'PLPGSQL' if str(language) == 'plpgsql' else 'SQL',
            'security': 'DEFINER' if security else 'INVOKER',
            'settings': [dict(zip(('name', 'value'),
                                  str(entry).split('=', 1)))
                         for entry in config or ()],
            'body': None if body is None else str(body).strip(),
            'comment': None if comment is None else str(comment),
        }
        if kind == 'function':
            native.update(
                returns=returns, returns_set=returns_set,
                volatility={'i': 'IMMUTABLE', 's': 'STABLE'}.get(
                    str(volatility), 'VOLATILE'),
                strict=bool(strict), leakproof=bool(leakproof),
                parallel={'s': 'SAFE', 'r': 'RESTRICTED'}.get(
                    str(parallel), 'UNSAFE'),
                cost=float(cost) if cost is not None else None,
                rows=float(rows) if rows else None)
        values.append(resource(kind, [schema], f'{name}({signature})',
                               generation, native))
    # pg_trigger, one record per trigger (information_schema.triggers has
    # one row per event); WHEN and UPDATE OF from pg_get_triggerdef.
    for (schema, table, name, tgtype, enabled, function_schema, function,
         arguments, definition, comment) in optional_rows(
        cursor,
        'SELECT n.nspname, cl.relname, tg.tgname, tg.tgtype, tg.tgenabled, '
        'pn.nspname, p.proname, tg.tgargs, pg_get_triggerdef(tg.oid), '
        "obj_description(tg.oid, 'pg_trigger') "
        'FROM pg_catalog.pg_trigger tg '
        'JOIN pg_catalog.pg_class cl ON cl.oid = tg.tgrelid '
        'JOIN pg_catalog.pg_namespace n ON n.oid = cl.relnamespace '
        'JOIN pg_catalog.pg_proc p ON p.oid = tg.tgfoid '
        'JOIN pg_catalog.pg_namespace pn ON pn.oid = p.pronamespace '
        f'WHERE NOT tg.tgisinternal AND n.nspname NOT IN {excluded} '
        'ORDER BY 1, 2, 3',
    ):
        definition = str(definition or '')
        when = re.search(r' WHEN \((.*)\) EXECUTE ', definition)
        columns = re.search(r' UPDATE OF (.+?) (?:OR |ON )', definition)
        values.append(resource(
            'trigger', [schema, table], name, generation,
            objects.trigger_native(
                (str(schema), str(table)), tgtype, enabled,
                (str(function_schema), str(function)), arguments,
                when.group(1) if when else None,
                [part.strip().strip('"') for part in
                 columns.group(1).split(',')] if columns else [],
                None if comment is None else str(comment)),
        ))
    for (schema, table, name, kind, roles, command, using, with_check,
         comment) in optional_rows(
        cursor,
        'SELECT p.schemaname, p.tablename, p.policyname, p.permissive, '
        'p.roles, p.cmd, p.qual, p.with_check, '
        "obj_description(o.oid, 'pg_policy') "
        'FROM pg_catalog.pg_policies p '
        'JOIN pg_catalog.pg_namespace n ON n.nspname = p.schemaname '
        'JOIN pg_catalog.pg_class c '
        'ON c.relnamespace = n.oid AND c.relname = p.tablename '
        'JOIN pg_catalog.pg_policy o '
        'ON o.polrelid = c.oid AND o.polname = p.policyname '
        'ORDER BY 1, 2, 3',
    ):
        values.append(resource('row-policy', [schema, table], name,
                               generation, {
            'table': f'{schema}.{table}',
            'policy_type': str(kind).upper(), 'command': str(command),
            'roles': sorted(str(role) for role in roles or []),
            'using': None if using is None else str(using),
            'with_check': None if with_check is None else str(with_check),
            'comment': None if comment is None else str(comment),
        }))
    for name, version, schema in optional_rows(
        cursor,
        'SELECT e.extname, e.extversion, n.nspname '
        'FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n '
        'ON n.oid = e.extnamespace ORDER BY e.extname',
    ):
        values.append(resource('extension', [], name, generation, {
            'version': str(version), 'schema': str(schema),
        }))
    for schema, parent, child, bound in optional_rows(
        cursor,
        'SELECT pn.nspname, pc.relname, cc.relname, '
        'pg_catalog.pg_get_expr(cc.relpartbound, cc.oid) '
        'FROM pg_catalog.pg_inherits i '
        'JOIN pg_catalog.pg_class pc ON pc.oid = i.inhparent '
        'JOIN pg_catalog.pg_class cc ON cc.oid = i.inhrelid '
        'JOIN pg_catalog.pg_namespace pn ON pn.oid = pc.relnamespace '
        f'WHERE pn.nspname NOT IN {excluded} ORDER BY 1, 2, 3',
    ):
        values.append(resource(
            'partition', [schema, parent], child, generation,
            {'bound': str(bound)},
        ))
    for name, owner, options, comment in optional_rows(
        cursor,
        'SELECT s.spcname, r.rolname, s.spcoptions, '
        "shobj_description(s.oid, 'pg_tablespace') "
        'FROM pg_catalog.pg_tablespace s JOIN pg_catalog.pg_roles r '
        'ON r.oid = s.spcowner '
        "WHERE s.spcname NOT IN ('pg_default', 'pg_global') ORDER BY 1",
    ):
        replicas, blocks = tablespaces.from_options(options)
        values.append(resource('tablespace', [], name, generation, {
            'owner': str(owner), 'options': list(options or ()),
            'num_replicas': replicas, 'placement_blocks': blocks,
            'comment': None if comment is None else str(comment),
        }))
    memberships = {}
    for member, role in optional_rows(
        cursor,
        'SELECT m.rolname, r.rolname FROM pg_catalog.pg_auth_members a '
        'JOIN pg_catalog.pg_roles m ON m.oid = a.member '
        'JOIN pg_catalog.pg_roles r ON r.oid = a.roleid',
    ):
        memberships.setdefault(str(member), []).append(str(role))
    for row in optional_rows(
        cursor,
        'SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, '
        'rolinherit, rolreplication, rolbypassrls, rolconnlimit, '
        'rolvaliduntil::text, '
        "shobj_description(oid, 'pg_authid') "
        'FROM pg_catalog.pg_roles ORDER BY 1',
    ):
        name, comment = str(row[0]), row[-1]
        native = {'can_login': bool(row[1]), **objects.principal_native(
            row[1:-1], memberships.get(name),
            None if comment is None else str(comment))}
        values.append(resource('role', [], name, generation, native))
        if row[1]:
            values.append(resource('user', [], name, generation,
                                   dict(native)))
    for grantee, schema, table, privilege in optional_rows(
        cursor,
        'SELECT grantee, table_schema, table_name, privilege_type '
        'FROM information_schema.table_privileges '
        f'WHERE table_schema NOT IN {excluded} ORDER BY 1, 2, 3, 4',
    ):
        display = f'{grantee}:{privilege}:{schema}.{table}'
        values.append(resource(
            'privilege', [schema, table, str(grantee)], display,
            generation, {'privilege_type': str(privilege)},
        ))
    rows = optional_rows(
        cursor,
        'SELECT host, port, num_connections, node_type, cloud, region, zone '
        'FROM yb_servers() ORDER BY host, port',
    )
    for host, port, connections, node_type, cloud, region, zone in rows:
        name = f'{host}:{port}'
        native = {
            'connections': connections, 'node_type': str(node_type),
            'cloud': str(cloud), 'region': str(region), 'zone': str(zone),
        }
        values.append(resource('tserver', [], name, generation, native))
        if region:
            values.append(resource('region', [], region, generation))
        if zone:
            values.append(resource('zone', [str(region)], zone, generation))
    return values


def _annotate_catalog(connection, values):
    """The table editor's field ids, from YSQL's PostgreSQL catalogs."""
    cursor = connection.cursor()
    try:
        columns = {(str(row[0]), str(row[1]), str(row[2])): row[3:]
                   for row in optional_rows(
                       cursor,
                       'SELECT n.nspname, c.relname, a.attname, '
                       'format_type(a.atttypid, a.atttypmod), a.attnotnull, '
                       'a.attidentity, a.attgenerated, '
                       'pg_get_expr(d.adbin, d.adrelid), '
                       "CASE WHEN a.attcollation <> t.typcollation "
                       'THEN co.collname END, '
                       'col_description(c.oid, a.attnum) '
                       'FROM pg_catalog.pg_attribute a '
                       'JOIN pg_catalog.pg_class c ON c.oid = a.attrelid '
                       'JOIN pg_catalog.pg_namespace n '
                       'ON n.oid = c.relnamespace '
                       'JOIN pg_catalog.pg_type t ON t.oid = a.atttypid '
                       'LEFT JOIN pg_catalog.pg_attrdef d '
                       'ON d.adrelid = c.oid AND d.adnum = a.attnum '
                       'LEFT JOIN pg_catalog.pg_collation co '
                       'ON co.oid = a.attcollation '
                       'WHERE a.attnum > 0 AND NOT a.attisdropped '
                       # User relations only: YSQL fetches catalog rows
                       # over RPC, and the system catalogs dominate.
                       "AND n.nspname NOT IN ('pg_catalog', "
                       "'information_schema') "
                       "AND c.relkind IN ('r', 'p', 'v', 'm', 'f') "
                       # Definition order: view records list names by it.
                       'ORDER BY n.nspname, c.relname, a.attnum')}
        tables = {(str(row[0]), str(row[1])): row[2:]
                  for row in optional_rows(
                      cursor,
                      'SELECT n.nspname, c.relname, ts.spcname, '
                      "obj_description(c.oid, 'pg_class'), "
                      'c.relrowsecurity, c.relforcerowsecurity, '
                      'pg_get_partkeydef(c.oid) '
                      'FROM pg_catalog.pg_class c '
                      'JOIN pg_catalog.pg_namespace n '
                      'ON n.oid = c.relnamespace '
                      'LEFT JOIN pg_catalog.pg_tablespace ts '
                      'ON ts.oid = c.reltablespace '
                      "WHERE c.relkind IN ('r', 'p')")}
        index_facts = {(str(row[0]), str(row[1]), str(row[2])): row[3:]
                       for row in optional_rows(
                           cursor,
                           'SELECT n.nspname, t.relname, i.relname, '
                           'x.indisunique, ts.spcname, '
                           "obj_description(i.oid, 'pg_class') "
                           'FROM pg_catalog.pg_index x '
                           'JOIN pg_catalog.pg_class i '
                           'ON i.oid = x.indexrelid '
                           'JOIN pg_catalog.pg_class t ON t.oid = x.indrelid '
                           'JOIN pg_catalog.pg_namespace n '
                           'ON n.oid = t.relnamespace '
                           'LEFT JOIN pg_catalog.pg_tablespace ts '
                           'ON ts.oid = i.reltablespace')}
        sequence_facts = {(str(row[0]), str(row[1])): row[2:]
                          for row in optional_rows(
                              cursor,
                              'SELECT s.schemaname, s.sequencename, '
                              's.data_type::text, s.start_value, '
                              's.increment_by, s.min_value, s.max_value, '
                              's.cache_size, s.cycle, '
                              "obj_description(c.oid, 'pg_class') "
                              'FROM pg_catalog.pg_sequences s '
                              'JOIN pg_catalog.pg_namespace n '
                              'ON n.nspname = s.schemaname '
                              'JOIN pg_catalog.pg_class c '
                              'ON c.relnamespace = n.oid '
                              'AND c.relname = s.sequencename')}
        owners = {(str(row[0]), str(row[1])): f'{row[2]}.{row[3]}.{row[4]}'
                  for row in optional_rows(
                      cursor,
                      'SELECT n.nspname, s.relname, tn.nspname, t.relname, '
                      'a.attname FROM pg_catalog.pg_depend d '
                      'JOIN pg_catalog.pg_class s ON s.oid = d.objid '
                      'JOIN pg_catalog.pg_namespace n '
                      'ON n.oid = s.relnamespace '
                      'JOIN pg_catalog.pg_class t ON t.oid = d.refobjid '
                      'JOIN pg_catalog.pg_namespace tn '
                      'ON tn.oid = t.relnamespace '
                      'JOIN pg_catalog.pg_attribute a '
                      'ON a.attrelid = t.oid AND a.attnum = d.refobjsubid '
                      "WHERE s.relkind = 'S' AND d.deptype = 'a'")}
        database_facts = {str(row[0]): row[1:] for row in optional_rows(
            cursor,
            'SELECT d.datname, pg_get_userbyid(d.datdba), '
            'pg_encoding_to_char(d.encoding), d.datcollate, d.datctype, '
            'd.datlocprovider, d.daticulocale, d.datconnlimit, '
            'd.datallowconn, d.datistemplate, '
            "shobj_description(d.oid, 'pg_database'), s.setconfig "
            'FROM pg_catalog.pg_database d '
            'LEFT JOIN pg_catalog.pg_db_role_setting s '
            'ON s.setdatabase = d.oid AND s.setrole = 0')}
        # Answers only for the database this connection is in.
        colocated = dict(optional_rows(
            cursor, 'SELECT current_database(), yb_is_database_colocated()'))
        view_facts = {(str(row[0]), str(row[1])): row[2:]
                      for row in optional_rows(
                          cursor,
                          'SELECT n.nspname, c.relname, '
                          'pg_get_viewdef(c.oid, true), c.reloptions, '
                          "obj_description(c.oid, 'pg_class'), ts.spcname "
                          'FROM pg_catalog.pg_class c '
                          'JOIN pg_catalog.pg_namespace n '
                          'ON n.oid = c.relnamespace '
                          'LEFT JOIN pg_catalog.pg_tablespace ts '
                          'ON ts.oid = c.reltablespace '
                          "WHERE c.relkind IN ('v', 'm') AND n.nspname "
                          "NOT IN ('pg_catalog', 'information_schema')")}
        keys = {(str(row[0]), str(row[1])): str(row[2])
                for row in optional_rows(
                    cursor,
                    'SELECT n.nspname, cl.relname, '
                    'pg_get_indexdef(co.conindid) '
                    'FROM pg_catalog.pg_constraint co '
                    'JOIN pg_catalog.pg_class cl ON cl.oid = co.conrelid '
                    'JOIN pg_catalog.pg_namespace n '
                    "ON n.oid = cl.relnamespace WHERE co.contype = 'p'")}
    finally:
        cursor.close()
    membership = {}
    held = {}
    for item in values:
        if item['resource_kind'] != 'constraint':
            continue
        native = item.setdefault('native', {})
        schema, table = (str(part) for part in item['display_path'][:2])
        kind = native.get('constraint_type')
        row = {'kind': kind, 'columns': list(native.get('columns') or [])}
        if kind == 'PRIMARY KEY':
            hashed, order = tables_sql.primary_key_shape(
                keys.get((schema, table), ''))
            row.update(hash_columns=hashed, order=order)
            for column in row['columns']:
                membership[(schema, table, column)] = 'PRI'
        elif kind == 'UNIQUE' and len(row['columns']) == 1:
            membership.setdefault((schema, table, row['columns'][0]), 'UNI')
        if kind == 'FOREIGN KEY':
            row.update(
                references_table=[native.get('referenced_schema'),
                                  native.get('referenced_table')],
                references_columns=list(
                    native.get('referenced_columns') or []),
                on_delete=native.get('delete_rule') or 'NO ACTION',
                on_update=native.get('update_rule') or 'NO ACTION')
        if kind == 'FOREIGN KEY':
            row.update(deferrable=native.get('deferrable', False),
                       initially_deferred=native.get(
                           'initially_deferred', False))
        if kind == 'CHECK':
            row = {'kind': kind, 'expression': tables_sql._unwrap(
                str(native.get('check_clause') or ''))}
        native.update(row)
        if 'references_table' in row:
            # The grid shows the table as the front end's picker sends it.
            native['references_table'] = '.'.join(
                str(part) for part in row['references_table'])
        held.setdefault((schema, table), []).append(
            {'name': item['display_name'], **row})
    for item in values:
        native = item.setdefault('native', {})
        path = tuple(str(part) for part in item.get('display_path') or [])
        if item['resource_kind'] == 'column':
            facts = columns.get(path)
            if not facts:
                continue
            (data_type, not_null, identity, generated, default, collation,
             comment) = facts
            identity = {'a': 'ALWAYS', 'd': 'BY DEFAULT'}.get(
                str(identity or ''), '')
            stored = str(generated or '') == 's'
            native.update(
                type=str(data_type), nullable=not not_null,
                identity=identity,
                generated_expression=str(default) if stored else None,
                default=None if identity or stored or default is None
                else str(default),
                collation=None if collation is None else str(collation),
                comment=None if comment is None else str(comment),
                column_key=membership.get(path, ''))
        elif item['resource_kind'] == 'database':
            facts = database_facts.get(path[-1] if path else '')
            if not facts:
                continue
            (owner, encoding, collate, ctype, provider, icu, limit, allow,
             template, comment, config) = facts
            native.update(
                owner=str(owner), encoding=str(encoding),
                collate=str(collate), ctype=str(ctype),
                locale_provider={'i': 'icu'}.get(str(provider), 'libc'),
                icu_locale=None if icu is None else str(icu),
                connection_limit=limit, allow_connections=bool(allow),
                is_template=bool(template),
                colocation=(None if path[-1] not in colocated
                            else bool(colocated[path[-1]])),
                comment=None if comment is None else str(comment),
                settings=[dict(zip(('name', 'value'),
                                   str(entry).split('=', 1)))
                          for entry in config or ()])
        elif item['resource_kind'] == 'sequence':
            facts = sequence_facts.get(path)
            if not facts:
                continue
            (data_type, start, increment, minimum, maximum, cache, cycle,
             comment) = facts
            native.update(
                parent=path[0], data_type=str(data_type), start=start,
                increment=increment, minimum=minimum, maximum=maximum,
                cache=cache, cycle=bool(cycle),
                owned_by=owners.get(path),
                comment=None if comment is None else str(comment))
        elif item['resource_kind'] in {'view', 'materialized-view'}:
            facts = view_facts.get(path)
            if not facts:
                continue
            definition, options, comment, tablespace = facts
            settings = dict(str(entry).partition('=')[::2]
                            for entry in options or ())
            native.update(
                parent=path[0],
                query=str(definition or '').strip().rstrip(';'),
                column_names=[name for (schema, table, name)
                              in columns if (schema, table) == path],
                comment=None if comment is None else str(comment),
                tablespace=None if tablespace is None else str(tablespace),
                **{key: settings.get(key) == 'true'
                   for key in views.OPTIONS})
        elif item['resource_kind'] == 'index':
            unique, tablespace, comment = index_facts.get(
                path, (False, None, None))
            native.update(index_sql.parse_definition(
                str(native.get('definition') or '')))
            native.update(
                table='.'.join(path[:2]), unique=bool(unique),
                tablespace=None if tablespace is None else str(tablespace),
                comment=None if comment is None else str(comment))
        elif item['resource_kind'] == 'table':
            facts = tables.get(path)
            if not facts:
                continue
            tablespace, comment, secured, forced, partition_key = facts
            strategy, _, key = str(partition_key or '').partition(' ')
            native.update(
                tablespace=None if tablespace is None else str(tablespace),
                comment=None if comment is None else str(comment),
                row_level_security=bool(secured),
                force_row_level_security=bool(forced),
                partition_by=strategy or None,
                partition_key=key.strip()[1:-1] if key else None,
                constraints=held.get(path, []),
                # A collation change restates the type (ALTER ... TYPE).
                column_types={column: str(facts[0]) for (
                    schema, table, column), facts in columns.items()
                    if (schema, table) == path})
    return values


def _catalog(connection, request):
    generation = str(request.get('capability_generation') or 'current')
    values = {
        item['resource_id']: item
        for item in _annotate_catalog(connection, postgresql_catalog(
            connection, request, 'YugabyteDB', _extras
        ))
    }
    route = request.get('route') or request.get('_provider_route') or {}
    for item in control_catalog_resources(route, generation):
        values[item['resource_id']] = item
    return list(values.values())


class YugabyteDBProvider(ActualEnginePilotProvider):
    def _discard_unverified_session(self, handle):
        self.client._discard_failed_session(handle)

    def __init__(self, context, permissions, client):
        super().__init__(context, permissions, client, PROFILE)


def create_provider(context, permissions, client=None):
    return YugabyteDBProvider(
        context,
        permissions,
        client or create_sql_client(
            PROFILE,
            permissions,
            wire='postgresql',
            version_query='SELECT version()',
            version_parser=_version,
            metadata_reader=_catalog,
            administration=ADMINISTRATION,
            pool_namespace=context.pool_namespace,
            client_class=YugabyteDBYSQLClient,
            client_options={'pool_namespace': context.pool_namespace},
        ),
    )
