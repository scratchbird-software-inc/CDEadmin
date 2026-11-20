"""MariaDB-native administration extensions to the relational family."""
from copy import deepcopy
from collections.abc import Mapping
from ..relational_admin import RelationalAdministration
from ...sdk import RelationalClientError
from . import mariadb_server_diagnostics as diagnostics
from . import mariadb_live_plans as live_plans

from . import mariadb_shutdown as shutdown

from . import mariadb_prepared_xa as prepared_xa

from . import mariadb_key_caches as key_caches

from . import mariadb_all_channels as all_channels
from . import mariadb_flush as flush
from . import destructive_identity
from . import mariadb_utilities as utilities

MODULES = (all_channels, diagnostics, live_plans, shutdown, prepared_xa, key_caches, flush, utilities)
OPERATIONS = {operation: module for module in MODULES for operation in module.OPERATIONS}
TABLE_OPERATIONS = {operation: flush for operation in flush.TABLE_OPERATIONS}


class MariaDBAdministration(RelationalAdministration):
    def requires_dialect(self, resource_kind, operation_id):
        if resource_kind == 'server' and operation_id in utilities.OPERATIONS:
            return False
        return super().requires_dialect(resource_kind, operation_id)

    def catalog(self, catalog):
        value = deepcopy(catalog)
        server = next(row for row in value['objects'] if row['resource_kind'] == 'server')
        server['operations'] = [row for row in server['operations']
                                if row['operation_id'] not in OPERATIONS]
        server['operations'] += [dict(operation_id=operation, title=title,
            mutation_class='admin', target_required=True, confirmation_required=True)
            for operation, module in OPERATIONS.items()
            for title, _suffix in [module.OPERATIONS[operation]]]
        table = next((row for row in value['objects'] if row['resource_kind'] == 'table'), None)
        if table is not None:
            table['operations'] = [row for row in table['operations']
                                   if row['operation_id'] not in TABLE_OPERATIONS]
            table['operations'] += [dict(operation_id=operation, title=title,
                mutation_class='admin', target_required=True, confirmation_required=True)
                for operation, module in TABLE_OPERATIONS.items()
                for title, _suffix in [module.TABLE_OPERATIONS[operation]]]
        return super().catalog(value)

    def _form(self, kind, operation):
        if kind == 'sequence' and operation in {'create', 'alter'}:
            from ...ui_descriptors import UIDescriptorService
            from .descriptor_contracts import field_contract
            row = next(row for row in UIDescriptorService().engine('mariadb')['operations']
                       if row['resource_kind'] == kind and row['operation_id'] == operation)
            return {'form_id': 'mariadb.sequence.' + operation, 'title': row['title'],
                    'fields': [field_contract(field) for field in row['fields']]}

        if kind == 'server' and operation in OPERATIONS:
            return OPERATIONS[operation].form(operation)
        if kind == 'table' and operation in TABLE_OPERATIONS:
            return TABLE_OPERATIONS[operation].form(operation, 'table')
        return super()._form(kind, operation)

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
        if kind == 'server' and operation in OPERATIONS and isinstance(draft, Mapping):
            return deepcopy(dict(draft))
        if kind == 'table' and operation in TABLE_OPERATIONS and isinstance(draft, Mapping):
            return deepcopy(dict(draft))
        return super()._normalize_draft(kind, operation, draft)

    def validate(self, request):
        if request.get('resource_kind') == 'server' and request.get('operation_id') in OPERATIONS:
            try:
                OPERATIONS[request['operation_id']].compile_operation(request['operation_id'], request.get('draft'), request.get('target_resource'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mariadb_native_operation', 'message': str(error)}]}
        if request.get('resource_kind') == 'table' and request.get('operation_id') in TABLE_OPERATIONS:
            try:
                TABLE_OPERATIONS[request['operation_id']].compile_operation(request['operation_id'], request.get('draft'), request.get('target_resource'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mariadb_native_operation', 'message': str(error)}]}
        return super().validate(request)

    def _compile(self, request):
        if request.get('resource_kind') == 'server' and request.get('operation_id') in OPERATIONS:
            return OPERATIONS[request['operation_id']].compile_operation(request['operation_id'], request.get('draft'), request.get('target_resource'))
        if request.get('resource_kind') == 'table' and request.get('operation_id') in TABLE_OPERATIONS:
            return TABLE_OPERATIONS[request['operation_id']].compile_operation(request['operation_id'], request.get('draft'), request.get('target_resource'))
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
        return super().apply(client, request, connection)

    def _compile_create(self, request):
        if request['resource_kind'] != 'sequence':
            return super()._compile_create(request)
        from .mariadb_sequence_options import clauses
        draft = request['draft']; options = deepcopy(draft.get('options') or {})
        parent = options.pop('parent', None)
        name = self._new_object_name(self._identifier(draft['name']), {'parent': parent} if parent else {})
        return [{'source': 'CREATE SEQUENCE ' + name + ' ' + clauses(options), 'parameters': ()}]

    def _compile_alter(self, request):
        if request['resource_kind'] != 'sequence':
            return super()._compile_alter(request)
        from .mariadb_sequence_options import clauses
        path = self._target_path(request['target_resource'])
        return [{'source': 'ALTER SEQUENCE ' + self._qualified(path) + ' ' +
                 clauses(request['draft'].get('changes'), True, path[-1]), 'parameters': ()}]
