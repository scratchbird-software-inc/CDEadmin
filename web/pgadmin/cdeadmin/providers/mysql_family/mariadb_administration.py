"""MariaDB-native administration extensions to the relational family."""
from collections.abc import Mapping
from copy import deepcopy

from ..relational_admin import RelationalAdministration
from ...sdk import RelationalClientError
from . import destructive_identity
from . import mariadb_all_channels as all_channels
from . import mariadb_available_plugins as available_plugins
from . import mariadb_flush as flush
from . import mariadb_indexes as maria_indexes
from . import mariadb_key_caches as key_caches
from . import mariadb_live_plans as live_plans
from . import mariadb_objects as maria_objects
from . import mariadb_prepared_xa as prepared_xa
from . import mariadb_server_diagnostics as diagnostics
from . import mariadb_shutdown as shutdown
from . import mariadb_tables as maria_tables
from . import mariadb_temporal as maria_temporal
from . import mariadb_temporary_tables as temporary_tables
from . import mariadb_utilities as utilities

SERVER_MODULES = (
    all_channels,
    diagnostics,
    live_plans,
    shutdown,
    prepared_xa,
    key_caches,
    flush,
    utilities,
    available_plugins,
)
MODULES = (
    *SERVER_MODULES,
    temporary_tables,
    maria_indexes,
    maria_temporal,
    maria_objects,
)
OPERATIONS = {
    operation: module
    for module in SERVER_MODULES
    for operation in module.OPERATIONS
}
TABLE_OPERATIONS = {
    **{operation: flush for operation in flush.TABLE_OPERATIONS},
    **{operation: maria_temporal for operation in maria_temporal.TABLE_OPERATIONS},
}
READ_SERVER_OPERATIONS = frozenset(getattr(available_plugins, 'READS', ()))
DESTRUCTIVE_TABLE_OPERATIONS = frozenset(getattr(maria_temporal, 'DESTRUCTIVE', ()))

_TABLE_PASSTHROUGH_CREATE = (
    set(maria_tables.OPTION_KEYS)
    | {
        'mariadb_table_options',
        'temporary',
        'system_versioning',
        'system_time_period',
        'periods',
        'application_periods',
        'partition_by',
        'partition_method',
        'partition_expression',
        'partition_columns',
        'partition_count',
        'partition_definitions',
        'system_time_interval',
        'system_time_limit',
    }
)
_TABLE_PASSTHROUGH_ALTER = (
    set(maria_tables.OPTION_KEYS)
    | {
        'mariadb_table_options',
        'system_versioning',
        'system_time_period',
        'periods',
        'application_periods',
        'drop_periods',
        'partition_by',
        'partition_method',
        'partition_expression',
        'partition_columns',
        'partition_count',
        'partition_definitions',
        'system_time_interval',
        'system_time_limit',
    }
)


def _descriptor_operation_form(kind, operation):
    from ...ui_descriptors import UIDescriptorService
    from .descriptor_contracts import field_contract

    for row in UIDescriptorService().engine('mariadb').get('operations', ()):
        if row.get('resource_kind') == kind and row.get('operation_id') == operation:
            fields = [field_contract(field) for field in row.get('fields', ())]
            if row.get('confirmation') == 'typed_name' and not any(
                f['field_id'] == 'confirmation' for f in fields
            ):
                fields.append({
                    'field_id': 'confirmation',
                    'label': 'Exact object name confirmation',
                    'control': 'text',
                    'required': False,
                })
            return {
                'form_id': f'mariadb.{kind}.{operation}',
                'title': row['title'],
                'fields': fields,
            }
    return None


def _descriptor_editor_form(kind, operation):
    from ...ui_descriptors import UIDescriptorService
    from ...ui_descriptors.field_contract import descriptor_field_contract

    contract = descriptor_field_contract(
        'mariadb',
        {'resource_kind': kind, 'operation_id': operation, 'legacy_fields': []},
    )
    title = f'{operation.replace("_", " ").capitalize()} {kind}'
    for form in UIDescriptorService().engine('mariadb').get('forms', {}).values():
        if kind in form.get('resource_kinds', ()):
            title = f"{operation.replace('_', ' ').capitalize()} {form.get('title', kind).lower()}"
            break
    return {
        'form_id': f'mariadb.{kind}.{operation}',
        'title': title,
        'fields': contract['fields'] if contract else [],
    }


class MariaDBAdministration(RelationalAdministration):
    def requires_dialect(self, resource_kind, operation_id):
        if resource_kind == 'server' and operation_id in utilities.OPERATIONS:
            return False
        return super().requires_dialect(resource_kind, operation_id)

    def catalog(self, catalog):
        value = deepcopy(catalog)
        server = next(row for row in value['objects'] if row['resource_kind'] == 'server')
        server['operations'] = [
            row for row in server['operations']
            if row['operation_id'] not in OPERATIONS
        ]
        server['operations'] += [
            dict(
                operation_id=operation,
                title=title,
                mutation_class='read' if operation in READ_SERVER_OPERATIONS else 'admin',
                target_required=True,
                confirmation_required=operation not in READ_SERVER_OPERATIONS,
            )
            for operation, module in OPERATIONS.items()
            for title, _suffix in [module.OPERATIONS[operation]]
        ]

        table = next((row for row in value['objects'] if row['resource_kind'] == 'table'), None)
        if table is not None:
            extra_table_ids = set(TABLE_OPERATIONS) | {'drop_temporary'}
            table['operations'] = [
                row for row in table['operations']
                if row['operation_id'] not in extra_table_ids
            ]
            table['operations'].append({
                'operation_id': 'drop_temporary',
                'title': 'Drop session temporary table',
                'mutation_class': 'destructive',
                'target_required': True,
                'confirmation_required': True,
            })
            table['operations'] += [
                dict(
                    operation_id=operation,
                    title=title,
                    mutation_class='destructive' if operation in DESTRUCTIVE_TABLE_OPERATIONS else 'admin',
                    target_required=True,
                    confirmation_required=True,
                )
                for operation, module in TABLE_OPERATIONS.items()
                for title, _suffix in [module.TABLE_OPERATIONS[operation]]
            ]

        index_obj = next((row for row in value['objects'] if row['resource_kind'] == 'index'), None)
        if index_obj is not None:
            index_extra = {'alter', 'rename', 'visibility'}
            index_obj['operations'] = [
                row for row in index_obj['operations']
                if row['operation_id'] not in index_extra
            ] + [
                {
                    'operation_id': 'alter',
                    'title': 'Alter MariaDB index',
                    'mutation_class': 'admin',
                    'target_required': True,
                    'confirmation_required': True,
                },
                {
                    'operation_id': 'rename',
                    'title': 'Rename MariaDB index',
                    'mutation_class': 'admin',
                    'target_required': True,
                    'confirmation_required': True,
                },
                {
                    'operation_id': 'visibility',
                    'title': 'Set MariaDB index IGNORED or NOT IGNORED',
                    'mutation_class': 'admin',
                    'target_required': True,
                    'confirmation_required': True,
                },
            ]

        for obj_kind, label in (
            ('view', 'view'),
            ('procedure', 'stored procedure'),
            ('function', 'stored function'),
            ('trigger', 'trigger'),
        ):
            obj = next((row for row in value['objects'] if row['resource_kind'] == obj_kind), None)
            if obj is None:
                continue
            obj['operations'] = [
                row for row in obj['operations']
                if row['operation_id'] not in {'alter', 'create_or_replace'}
            ] + [
                {
                    'operation_id': 'alter',
                    'title': f'Alter MariaDB {label}',
                    'mutation_class': 'admin',
                    'target_required': True,
                    'confirmation_required': True,
                },
                {
                    'operation_id': 'create_or_replace',
                    'title': f'Replace MariaDB {label} (CREATE OR REPLACE)',
                    'mutation_class': 'admin',
                    'target_required': True,
                    'confirmation_required': True,
                },
            ]

        value['objects'] = [
            row for row in value['objects']
            if row['resource_kind'] != available_plugins.KIND
        ]
        value['objects'].append({
            'resource_kind': available_plugins.KIND,
            'title': 'Available plugin modules',
            'navigator_group': 'operations',
            'parent_kinds': ['server'],
            'operations': [{
                'operation_id': 'inspect',
                'title': 'Inspect available plugin module',
                'mutation_class': 'read',
                'target_required': True,
                'confirmation_required': False,
            }],
        })
        return super().catalog(value)

    def _form(self, kind, operation):
        if kind == 'sequence' and operation in {'create', 'alter'}:
            declared = _descriptor_operation_form(kind, operation)
            if declared is not None:
                return declared
        if kind == 'server' and operation in OPERATIONS:
            return OPERATIONS[operation].form(operation)
        if kind == 'table' and operation == 'drop_temporary':
            return temporary_tables.form(operation)
        if kind == 'table' and operation in TABLE_OPERATIONS:
            return TABLE_OPERATIONS[operation].form(operation, 'table')
        if kind == 'index' and operation in {'rename', 'visibility'}:
            declared = _descriptor_operation_form(kind, operation)
            if declared is not None:
                return declared
        if kind in {'view', 'procedure', 'function', 'trigger'} and operation == 'create_or_replace':
            declared = _descriptor_operation_form(kind, operation)
            if declared is not None:
                return declared
        if kind in {'index', 'view', 'procedure', 'function', 'trigger'} and operation == 'alter':
            return _descriptor_editor_form(kind, operation)
        return super()._form(kind, operation)

    @staticmethod
    def _native_operation(request):
        kind = request.get('resource_kind')
        operation = request.get('operation_id')
        draft = request.get('draft')
        target = request.get('target_resource')
        if kind == 'server' and operation in OPERATIONS:
            return (
                OPERATIONS[operation].compile_operation,
                (operation, draft, target),
                'invalid_mariadb_native_operation',
            )
        if kind == 'table' and operation == 'drop_temporary':
            return (
                temporary_tables.compile_operation,
                (operation, draft, target),
                'invalid_mariadb_temporary_table',
            )
        if kind == 'table' and operation in TABLE_OPERATIONS:
            return (
                TABLE_OPERATIONS[operation].compile_operation,
                (operation, draft, target),
                'invalid_mariadb_temporal_operation',
            )
        if kind == 'index' and operation == 'create':
            return (
                maria_indexes.compile_create,
                (draft,),
                'invalid_mariadb_index',
            )
        if kind == 'index' and operation in {'alter', 'rename', 'visibility'}:
            return (
                maria_indexes.compile_change,
                (operation, draft, target),
                'invalid_mariadb_index',
            )
        if kind == 'view' and operation in {'create', 'alter', 'create_or_replace'}:
            return (
                maria_objects.compile_view,
                (operation, draft, target),
                'invalid_mariadb_view',
            )
        if kind in {'procedure', 'function'} and operation in {'create', 'alter', 'create_or_replace'}:
            return (
                maria_objects.compile_routine,
                (kind, operation, draft, target),
                'invalid_mariadb_routine',
            )
        if kind == 'trigger' and operation in {'create', 'alter', 'create_or_replace'}:
            return (
                maria_objects.compile_trigger,
                (operation, draft, target),
                'invalid_mariadb_trigger',
            )
        return None

    def _normalize_draft(self, kind, operation, draft):
        if kind == 'sequence' and operation in {'create', 'alter'} and isinstance(draft, Mapping):
            value = deepcopy(dict(draft))
            slot = 'options' if operation == 'create' else 'changes'
            options = value.pop(slot, {})
            if not isinstance(options, dict):
                raise RelationalClientError('Select typed native sequence options')
            from .mariadb_sequence_options import KEYS
            for key in KEYS:
                if key in value:
                    options[key] = value.pop(key)
            if 'cycle' in options:
                options['cycle_mode'] = 'CYCLE' if options.pop('cycle') else 'NOCYCLE'
            value[slot] = options
            return value
        if self._native_operation({'resource_kind': kind, 'operation_id': operation, 'draft': draft}) is not None:
            if not isinstance(draft, Mapping):
                raise RelationalClientError(f'Select structured MariaDB {kind} properties')
            return deepcopy(dict(draft))
        if kind == 'table' and operation == 'create':
            if not isinstance(draft, Mapping):
                raise RelationalClientError('Select structured MariaDB table properties')
            value = deepcopy(dict(draft))
            extra = {k: value.pop(k) for k in _TABLE_PASSTHROUGH_CREATE if k in value}
            if (
                'temporary' in extra
                and 'temporary' in (value.get('options') or {})
                and extra['temporary'] != value['options']['temporary']
            ):
                raise RelationalClientError('Conflicting MariaDB temporary table selections')
            normalized = super()._normalize_draft(kind, operation, value)
            normalized.setdefault('options', {}).update(extra)
            return normalized
        if kind == 'table' and operation == 'alter' and isinstance(draft, Mapping):
            value = deepcopy(dict(draft))
            extra = {k: value.pop(k) for k in _TABLE_PASSTHROUGH_ALTER if k in value}
            # Allow flat alter drafts from declarative UI forms as well as nested {'changes': ...}
            if 'changes' not in value:
                known_change_keys = {
                    'add_columns', 'drop_columns', 'rename_columns', 'alter_columns',
                    'add_constraints', 'drop_constraints',
                }
                nested_changes = {k: value.pop(k) for k in list(value) if k in known_change_keys}
                if nested_changes or extra:
                    value['changes'] = nested_changes
            normalized = super()._normalize_draft(kind, operation, value)
            normalized.setdefault('changes', {}).update(extra)
            return normalized
        return super()._normalize_draft(kind, operation, draft)

    def _column_definition(self, item):
        return maria_tables.compile_column_clause(self, item, super()._column_definition)

    def _constraint_definition(self, item):
        return maria_tables.compile_constraint_clause(self, item, super()._constraint_definition)

    def validate(self, request):
        selected = self._native_operation(request)
        if selected is not None:
            compiler, args, code = selected
            try:
                compiler(*args)
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': code, 'message': str(error)}]}
        if request.get('resource_kind') == 'table' and request.get('operation_id') in {'create', 'alter'}:
            op = request['operation_id']
            base = super().validate(request)
            if not base['errors']:
                try:
                    normalized = self._normalize_draft('table', op, request.get('draft') or {})
                    self._compile({**request, 'draft': normalized})
                except (RelationalClientError, ValueError) as error:
                    base['errors'].append({
                        'field_id': None,
                        'code': 'invalid_mariadb_table_options',
                        'message': str(error),
                    })
            return base
        return super().validate(request)

    def _compile_table_create(self, request):
        draft = request['draft']
        options = deepcopy(dict(draft.get('options') or {}))
        is_temp = temporary_tables.is_temporary_flag(options)
        sys_ver = options.get('system_versioning', False)
        if type(sys_ver) is not bool:
            raise RelationalClientError('MariaDB system_versioning must be boolean')
        selected = maria_tables.selected_options(options)
        if is_temp:
            if sys_ver:
                raise RelationalClientError('MariaDB TEMPORARY tables do not support WITH SYSTEM VERSIONING')
            if any(
                options.get(k) not in (None, '', {}, [], 0)
                for k in ('partition_by', 'partition_method', 'partition_expression', 'partition_columns', 'partition_count', 'partition_definitions')
            ):
                raise RelationalClientError('MariaDB TEMPORARY tables cannot be partitioned')
        compiled = super()._compile(request)
        source = compiled['statements'][0]['source']
        params = list(compiled['statements'][0].get('parameters') or ())

        period_clauses = maria_tables.compile_period_clauses(options)
        if period_clauses:
            close_idx = source.rfind(')')
            if close_idx < 0:
                raise RelationalClientError('Invalid MariaDB CREATE TABLE clause layout')
            source = source[:close_idx] + ', ' + ', '.join(period_clauses) + source[close_idx:]

        suffix, opt_params = maria_tables.compile_table_options(
            selected, is_alter=False, temporary=is_temp, system_versioning=sys_ver
        )
        part_sql = maria_tables.compile_partition_clause(options, system_versioning=sys_ver)
        if part_sql and 'SYSTEM_TIME' in part_sql.upper() and not sys_ver:
            raise RelationalClientError('PARTITION BY SYSTEM_TIME requires WITH SYSTEM VERSIONING')
        source = source + suffix + part_sql
        params.extend(opt_params)

        if is_temp:
            source = source.replace('CREATE TABLE ', 'CREATE TEMPORARY TABLE ', 1)
            parent = options.get('parent') or draft.get('parent')
            tbl_path = [str(parent), str(draft['name'])] if isinstance(parent, str) and parent else (
                [*[str(p) for p in parent], str(draft['name'])] if isinstance(parent, (list, tuple)) and parent else [str(draft['name'])]
            )
            compiled['statements'][0] = {'source': source, 'parameters': tuple(params)}
            compiled[temporary_tables.KEY] = {
                'operation': 'create_temporary',
                'retained_session_required': True,
                'table': tbl_path,
            }
            compiled['warnings'] = [
                *compiled.get('warnings', []),
                'Requires the selected retained MariaDB session. Temporary table DDL is session-scoped and does not perform an implicit commit.',
            ]
            return compiled

        compiled['statements'][0] = {'source': source, 'parameters': tuple(params)}
        compiled['mariadb_implicit_commit_ddl'] = True
        compiled['warnings'] = [
            *compiled.get('warnings', []),
            'MariaDB CREATE TABLE performs an implicit commit before and after execution.',
        ]
        return compiled

    def _compile_table_alter(self, request):
        draft = request['draft']
        changes = draft.get('changes')
        if not isinstance(changes, Mapping):
            raise RelationalClientError('MariaDB table alter changes must be an object')
        changes = deepcopy(dict(changes))
        extra_opts = {k: changes.pop(k) for k in list(changes) if k in _TABLE_PASSTHROUGH_ALTER}
        target = request.get('target_resource') or {}
        baseline_engine = (target.get('native') or {}).get('engine')
        target_sql = self._qualified(self._target_path(target))

        statements = []
        if any(changes.values()):
            statements.extend(
                super()._compile({**request, 'draft': {**draft, 'changes': changes}})['statements']
            )

        drop_periods = extra_opts.pop('drop_periods', None) or []
        if drop_periods:
            if not isinstance(drop_periods, list):
                raise RelationalClientError('drop_periods must be a list of period names')
            for p_name in drop_periods:
                if not isinstance(p_name, str) or not p_name or p_name.upper() == 'SYSTEM_TIME':
                    raise RelationalClientError('Application period drop requires a non-SYSTEM_TIME period name')
                statements.append({
                    'source': f'ALTER TABLE {target_sql} DROP PERIOD FOR {self._identifier(p_name)}',
                    'parameters': (),
                })

        for p_clause in maria_tables.compile_period_clauses(extra_opts):
            statements.append({
                'source': f'ALTER TABLE {target_sql} ADD {p_clause}',
                'parameters': (),
            })
        for p_key in ('periods', 'application_periods', 'system_time_period'):
            extra_opts.pop(p_key, None)

        if 'system_versioning' in extra_opts:
            if extra_opts.pop('system_versioning') is False:
                raise RelationalClientError(
                    'Use the dedicated drop_system_versioning lifecycle operation with destructive_history_confirmed=True to drop system versioning'
                )
            statements.append({
                'source': f'ALTER TABLE {target_sql} ADD SYSTEM VERSIONING',
                'parameters': (),
            })

        part_sql = maria_tables.compile_partition_clause(
            extra_opts,
            system_versioning=bool((target.get('native') or {}).get('system_versioned')),
        )
        for pk in (
            'partition_by', 'partition_method', 'partition_expression', 'partition_columns',
            'partition_count', 'partition_definitions', 'system_time_interval', 'system_time_limit',
        ):
            extra_opts.pop(pk, None)

        selected = maria_tables.selected_options(extra_opts)
        suffix, opt_params = maria_tables.compile_table_options(
            selected, is_alter=True, baseline_engine=baseline_engine,
        )
        if suffix or part_sql:
            statements.append({
                'source': f'ALTER TABLE {target_sql}{suffix}{part_sql}',
                'parameters': opt_params,
            })

        if not statements:
            raise RelationalClientError('MariaDB table alteration has no structured changes')
        return {
            'statements': statements,
            'mariadb_implicit_commit_ddl': True,
            'warnings': [
                'MariaDB ALTER TABLE performs an implicit commit; rollback cannot undo completed DDL statements.',
            ],
        }

    def _compile(self, request):
        selected = self._native_operation(request)
        if selected is not None:
            return selected[0](*selected[1])
        if request.get('resource_kind') == 'table' and request.get('operation_id') == 'create':
            return self._compile_table_create(request)
        if request.get('resource_kind') == 'table' and request.get('operation_id') == 'alter':
            return self._compile_table_alter(request)
        if destructive_identity.applies(request):
            compiled = super()._compile(request)
            compiled['destructive_identity_required'] = True
            compiled['resource_kind'] = 'table'
            compiled['operation_id'] = 'drop'
            compiled['target_resource'] = deepcopy(dict(request['target_resource']))
            return compiled
        return super()._compile(request)

    def apply(self, client, request, connection=None):
        compiled = (request.get('provider_payload') or {}).get('compiled', {})
        if compiled.get('destructive_identity_required'):
            return destructive_identity.apply(client, request, connection, 'mariadb')
        for module in MODULES:
            if module.KEY in compiled:
                return module.apply(client, request, connection)
        variable = compiled.get('mariadb_global_variable')
        if variable and getattr(getattr(client, 'module', None), '__name__', '') == 'mariadb':
            route = dict((request.get('provider_payload') or {}).get('route') or {})
            probe = client._connect({'route': {**route, 'autocommit': True}})
            cursor = None
            try:
                cursor = probe.cursor()
                cursor.execute(
                    'SELECT VARIABLE_SCOPE,READ_ONLY FROM information_schema.SYSTEM_VARIABLES '
                    'WHERE UPPER(VARIABLE_NAME)=?',
                    (str(variable).upper(),),
                )
                row = cursor.fetchone()
            finally:
                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                client._forget_and_close(probe)
            if not row:
                error = RelationalClientError('Unknown MariaDB system variable')
                error.native_dispatched = False
                error.native_acknowledged = False
                error.automatic_retry = False
                raise error
            if str(row[1] or '').strip().upper() != 'NO':
                error = RelationalClientError('MariaDB reports this system variable as read-only')
                error.native_dispatched = False
                error.native_acknowledged = False
                error.automatic_retry = False
                raise error
            if str(row[0] or '').strip().upper() not in {'GLOBAL', 'SESSION'}:
                error = RelationalClientError('MariaDB does not expose a global scope for this variable')
                error.native_dispatched = False
                error.native_acknowledged = False
                error.automatic_retry = False
                raise error
        result = super().apply(client, request, connection)
        op_id = (
            (request.get('provider_payload') or {}).get('operation_id')
            or (request.get('plan') or {}).get('operation_id')
            or request.get('operation_id')
        )
        res_kind = (
            (request.get('provider_payload') or {}).get('resource_kind')
            or (request.get('plan') or {}).get('resource_kind')
            or request.get('resource_kind')
        )
        if isinstance(result, dict) and (
            compiled.get('mariadb_implicit_commit_ddl')
            or (res_kind == 'table' and op_id in {'create', 'alter', 'rename'})
        ):
            result = {
                **result,
                'native_implicit_commit': True,
            }
        return result

    def _compile_create(self, request):
        if request['resource_kind'] != 'sequence':
            return super()._compile_create(request)
        from .mariadb_sequence_options import clauses
        draft = request['draft']
        options = deepcopy(draft.get('options') or {})
        parent = options.pop('parent', None)
        name = self._new_object_name(self._identifier(draft['name']), {'parent': parent} if parent else {})
        return [{'source': 'CREATE SEQUENCE ' + name + ' ' + clauses(options), 'parameters': ()}]

    def _compile_alter(self, request):
        if request['resource_kind'] != 'sequence':
            return super()._compile_alter(request)
        from .mariadb_sequence_options import clauses
        path = self._target_path(request['target_resource'])
        return [{
            'source': 'ALTER SEQUENCE ' + self._qualified(path) + ' ' +
            clauses(request['draft'].get('changes'), True, path[-1]),
            'parameters': (),
        }]
