"""MySQL native administration additions to the shared relational UI."""
from copy import deepcopy
from collections.abc import Mapping

from ..relational_admin import RelationalAdministration
from ..mysql_descriptor_contract import operation_entry
from ...sdk import RelationalClientError
from . import spatial_reference_systems as srs
from . import foreign_servers
from . import column_masking
from . import mysql_key_cache
from . import mysql_instance
from . import mysql_table_options
from . import mysql_indexes
from . import mysql_routines
from . import mysql_triggers
from . import mysql_accounts
from . import mysql_privileges
from . import mysql_user_keys
from . import mysql_xa
from . import mysql_page_tracking
from . import mysql_rewriter
from . import mysql_server_control
from . import mysql_key_cache_lifecycle as cache_lifecycle


class MySQLAdministration(RelationalAdministration):
    def catalog(self, catalog):
        value = deepcopy(catalog)
        for resource in value['objects']:
            if resource['resource_kind']=='server':
                resource['operations'] = [row for row in resource['operations'] if row['operation_id'] not in mysql_page_tracking.OPERATIONS] + [{
                    'operation_id': operation, 'title': title,
                    'mutation_class': 'read' if operation in mysql_page_tracking.READS else 'destructive' if operation in {'set_page_tracking_backup_id', 'purge_page_tracking'} else 'admin',
                    'target_required': True, 'confirmation_required': operation not in mysql_page_tracking.READS,
                } for operation, title in mysql_page_tracking.OPERATIONS.items()]
                resource['operations'] = [row for row in resource['operations'] if row['operation_id'] not in mysql_rewriter.OPERATIONS] + [{
                    'operation_id': operation, 'title': title,
                    'mutation_class': 'read' if operation == 'inspect_rewrite_rules' else 'destructive' if operation == 'drop_rewrite_rule' else 'admin',
                    'target_required': True, 'confirmation_required': operation != 'inspect_rewrite_rules',
                } for operation, title in mysql_rewriter.OPERATIONS.items()]
                resource['operations']=[row for row in resource['operations'] if row['operation_id'] not in mysql_server_control.OPERATIONS]+[{
                    'operation_id':operation,'title':title[0],'mutation_class':'destructive',
                    'target_required':True,'confirmation_required':True,
                } for operation,title in mysql_server_control.OPERATIONS.items()]
                resource['operations']=[row for row in resource['operations'] if row['operation_id'] not in mysql_xa.OPERATIONS]+[{
                    'operation_id':operation,'title':title,'mutation_class':'read' if operation=='inspect_prepared_xa' else 'destructive',
                    'target_required':True,'confirmation_required':operation!='inspect_prepared_xa',
                } for operation,title in mysql_xa.OPERATIONS.items()]
                resource['operations']=[row for row in resource['operations'] if row['operation_id'] not in mysql_instance.OPERATIONS]+[{
                    'operation_id':operation,'title':mysql_instance.OPERATIONS[operation][0],
                    'mutation_class':'admin','target_required':True,'confirmation_required':True,
                } for operation in mysql_instance.OPERATIONS]
                resource['operations']=[row for row in resource['operations'] if row['operation_id'] not in cache_lifecycle.OPERATIONS]+[{
                    'operation_id':operation,'title':title,'mutation_class':'read' if operation=='inspect_key_cache' else 'admin',
                    'target_required':True,'confirmation_required':operation!='inspect_key_cache',
                } for operation,title in cache_lifecycle.OPERATIONS.items()]
            if resource['resource_kind'] == 'table':
                resource['operations'] = [row for row in resource['operations'] if row['operation_id'] not in mysql_key_cache.OPERATIONS] + [{
                    'operation_id':operation,'title':operation_entry('table',operation)['title'],
                    'mutation_class':'admin','target_required':True,'confirmation_required':True,
                } for operation in sorted(mysql_key_cache.OPERATIONS)]
            if resource['resource_kind'] == 'column':
                resource['operations'] = [row for row in resource['operations']
                    if row['operation_id'] not in column_masking.OPERATIONS] + [{
                        'operation_id': operation,
                        'title': 'Assign native masking policy reference' if operation == 'set_masking_policy' else 'Remove native masking policy reference',
                        'mutation_class': 'admin', 'target_required': True, 'confirmation_required': True,
                    } for operation in sorted(column_masking.OPERATIONS)]
        value['objects'] = [row for row in value['objects'] if row['resource_kind'] != srs.KIND]
        value['objects'].append({'resource_kind': srs.KIND,
            'title': 'Spatial reference systems', 'operations': [{
                'operation_id': operation,
                'title': 'Inspect spatial reference system' if operation == 'inspect' else srs.form(operation, self._field)['title'],
                'mutation_class': 'read' if operation == 'inspect' else 'destructive' if operation == 'drop' else 'admin',
                'target_required': operation != 'create',
                'confirmation_required': operation != 'inspect',
            } for operation in ['inspect', 'create', 'alter', 'drop']]})
        value['objects'] = [row for row in value['objects'] if row['resource_kind'] != foreign_servers.KIND]
        value['objects'].append({'resource_kind': foreign_servers.KIND,
            'title': 'Foreign servers', 'operations': [{
                'operation_id': operation,
                'title': 'Inspect foreign server' if operation == 'inspect' else foreign_servers.form(operation, self._field)['title'],
                'mutation_class': 'read' if operation == 'inspect' else 'destructive' if operation == 'drop' else 'admin',
                'target_required': operation != 'create', 'confirmation_required': operation != 'inspect',
            } for operation in ['inspect', 'create', 'alter', 'drop']]})
        value=super().catalog(value)
        server=next(row for row in value['objects'] if row['resource_kind']=='server')
        server['operations'] += deepcopy(mysql_user_keys.catalog_entries())
        return value

    def _form(self, kind, operation):
        declared = operation_entry(kind, operation)
        if declared is not None:
            return declared
        if kind == 'column' and operation in column_masking.OPERATIONS:
            fields = []
            if operation == 'set_masking_policy':
                fields.append({**self._field('policy_name', 'Exact native policy reference name', 'text', True),
                    'initial_value_path': ['masking_policy', 'name']})
            fields.append(self._field('confirmation', 'Exact native column name', 'text', True))
            return {'form_id': 'mysql.column.' + operation, 'title': 'Native column policy reference', 'fields': fields}
        if kind == srs.KIND and operation in srs.OPERATIONS:
            return srs.form(operation, self._field)
        if kind == foreign_servers.KIND and operation in foreign_servers.OPERATIONS:
            return foreign_servers.form(operation, self._field)
        return super()._form(kind, operation)

    def _normalize_draft(self, kind, operation, draft):
        from .database_inputs import OPERATIONS, normalize
        if kind == 'database' and operation in OPERATIONS:
            return normalize(operation, draft)
        if kind == 'privilege' and operation in {'grant', 'revoke'}:return deepcopy(draft)
        if kind == 'user' and operation in {'rename', 'drop'} or kind == 'role' and operation == 'drop':return deepcopy(draft)
        if kind == 'role' and operation == 'create':return deepcopy(draft)
        if kind == 'user' and operation in {'create', 'alter'}:return deepcopy(draft)
        if kind == 'trigger' and operation == 'create':return deepcopy(draft)
        if kind in mysql_routines.KINDS and operation == 'create':return deepcopy(draft)
        if kind == 'index' and operation == 'create':return deepcopy(draft)
        if kind=='server' and operation in mysql_user_keys.OPERATIONS:return deepcopy(draft)
        if kind=='table' and operation=='create':
            if not isinstance(draft,Mapping):raise RelationalClientError('Select structured native MySQL table properties')
            value=deepcopy(dict(draft));native={key:value.pop(key) for key in ('mysql_table_options','mysql_connection') if key in value}
            if native.get('mysql_connection')=='':native.pop('mysql_connection')
            value=super()._normalize_draft(kind,operation,value);value['options'].update(native);return value
        if kind == 'server' and operation in mysql_page_tracking.OPERATIONS:
            return deepcopy(draft)
        if kind == 'server' and operation in mysql_rewriter.OPERATIONS:
            return deepcopy(draft)
        if kind=='server' and operation in mysql_server_control.OPERATIONS:return deepcopy(draft)
        if kind=='server' and operation in mysql_xa.OPERATIONS:return deepcopy(draft)
        if kind=='server' and operation in cache_lifecycle.OPERATIONS:return deepcopy(draft)
        if kind=='server' and operation in mysql_instance.OPERATIONS:return deepcopy(draft)
        if kind == 'table' and operation in mysql_key_cache.OPERATIONS:return deepcopy(draft)
        if kind == 'column' and operation in column_masking.OPERATIONS:
            return deepcopy(draft)
        if ((kind == srs.KIND and operation in srs.OPERATIONS) or
                (kind == foreign_servers.KIND and operation in foreign_servers.OPERATIONS)):
            return deepcopy(draft)
        return super()._normalize_draft(kind, operation, draft)

    def validate(self, request):
        from .database_inputs import OPERATIONS, normalize
        if request.get('resource_kind') == 'database' and request.get('operation_id') in OPERATIONS:
            try:
                return super().validate({**request, 'draft': normalize(request['operation_id'], request.get('draft'))})
            except (RelationalClientError, TypeError, ValueError, OverflowError) as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_database_input', 'message': str(error)}]}
        if request.get('resource_kind') == 'privilege' and request.get('operation_id') in {'grant', 'revoke'}:
            try:
                mysql_privileges.compile_operation(request['operation_id'], request.get('draft'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_privilege', 'message': str(error)}]}
        kind, operation = request.get('resource_kind'), request.get('operation_id')
        if kind == 'user' and operation in {'rename', 'drop'} or kind == 'role' and operation == 'drop':
            try:
                mysql_accounts.compile_operation(operation+'_'+kind, request.get('draft'), request.get('target_resource'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_account_identity', 'message': str(error)}]}
        if request.get('resource_kind') == 'role' and request.get('operation_id') == 'create':
            try:
                mysql_accounts.compile_role(request.get('draft'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_role', 'message': str(error)}]}
        if request.get('resource_kind') == 'user' and request.get('operation_id') in {'create', 'alter'}:
            try:
                mysql_accounts.compile_operation(request['operation_id'], request.get('draft'), request.get('target_resource'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_account', 'message': str(error)}]}
        if request.get('resource_kind') == 'trigger' and request.get('operation_id') == 'create':
            try:
                mysql_triggers.compile_create(request.get('draft'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_trigger', 'message': str(error)}]}
        if request.get('resource_kind') in mysql_routines.KINDS and request.get('operation_id') == 'create':
            try:
                mysql_routines.compile_create(request['resource_kind'], request.get('draft'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_routine', 'message': str(error)}]}
        if request.get('resource_kind') == 'index' and request.get('operation_id') == 'create':
            try:
                mysql_indexes.compile_create(request.get('draft'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_index', 'message': str(error)}]}
        if request.get('resource_kind')=='server' and request.get('operation_id') in mysql_user_keys.OPERATIONS:
            try:
                mysql_user_keys.compile_operation(request['operation_id'],request.get('draft'),request.get('target_resource'))
                return {'errors':[]}
            except RelationalClientError as error:return {'errors':[{'field_id':None,'code':'invalid_user_key','message':str(error)}]}
        if request.get('resource_kind')=='table' and request.get('operation_id')=='create':
            value=super().validate(request)
            try:
                draft=request.get('draft') or {};options=draft.get('options') or {}
                mysql_table_options.compile_options(draft.get('mysql_table_options',mysql_table_options.selected(options)),draft.get('mysql_connection',options.get('mysql_connection')) or None)
            except (RelationalClientError,ValueError) as error:value['errors'].append({'field_id':None,'code':'invalid_mysql_table_options','message':str(error)})
            return value
        if request.get('resource_kind') == 'server' and request.get('operation_id') in mysql_page_tracking.OPERATIONS:
            try:
                mysql_page_tracking.compile_operation(request['operation_id'], request.get('draft'), request.get('target_resource'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_page_tracking', 'message': str(error)}]}
        if request.get('resource_kind') == 'server' and request.get('operation_id') in mysql_rewriter.OPERATIONS:
            try:
                mysql_rewriter.compile_operation(request['operation_id'], request.get('draft'), request.get('target_resource'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_rewriter', 'message': str(error)}]}
        if request.get('resource_kind')=='server' and request.get('operation_id') in mysql_server_control.OPERATIONS:
            try:
                mysql_server_control.compile_operation(request['operation_id'],request.get('draft'),request.get('target_resource'))
                return {'errors':[]}
            except RelationalClientError as error:
                return {'errors':[{'field_id':None,'code':'invalid_mysql_server_control','message':str(error)}]}
        if request.get('resource_kind')=='server' and request.get('operation_id') in mysql_xa.OPERATIONS:
            try:
                mysql_xa.compile_operation(request['operation_id'],request.get('draft'),request.get('target_resource'))
                return {'errors':[]}
            except RelationalClientError as error:
                return {'errors':[{'field_id':None,'code':'invalid_mysql_xa','message':str(error)}]}
        if request.get('resource_kind')=='server' and request.get('operation_id') in cache_lifecycle.OPERATIONS:
            try:
                cache_lifecycle.compile_operation(request['operation_id'],request.get('draft'),request.get('target_resource'))
                return {'errors':[]}
            except RelationalClientError as error:
                return {'errors':[{'field_id':None,'code':'invalid_mysql_key_cache_lifecycle','message':str(error)}]}
        if request.get('resource_kind')=='server' and request.get('operation_id') in mysql_instance.OPERATIONS:
            try:
                mysql_instance.compile_operation(request['operation_id'],request.get('draft'),request.get('target_resource'))
                return {'errors':[]}
            except RelationalClientError as error:
                return {'errors':[{'field_id':None,'code':'invalid_mysql_instance','message':str(error)}]}
        if request.get('resource_kind')=='table' and request.get('operation_id') in mysql_key_cache.OPERATIONS:
            try:
                mysql_key_cache.compile_operation(request['operation_id'],request.get('draft'),request.get('target_resource'))
                return {'errors':[]}
            except RelationalClientError as error:
                return {'errors':[{'field_id':None,'code':'invalid_mysql_key_cache','message':str(error)}]}
        if request.get('resource_kind') == 'column' and request.get('operation_id') in column_masking.OPERATIONS:
            try:
                column_masking.compile_operation(request['operation_id'], request.get('draft'), request.get('target_resource'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_column_masking', 'message': str(error)}]}
        if request.get('resource_kind') == foreign_servers.KIND and request.get('operation_id') in foreign_servers.OPERATIONS:
            try:
                foreign_servers.compile_operation(request['operation_id'], request.get('draft'), request.get('target_resource'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_foreign_server', 'message': str(error)}]}
        if request.get('resource_kind') == srs.KIND and request.get('operation_id') in srs.OPERATIONS:
            try:
                srs.compile_operation(request['operation_id'], request.get('draft'), request.get('target_resource'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_spatial_reference', 'message': str(error)}]}
        return super().validate(request)

    def _compile(self, request):
        if request.get('resource_kind') == 'privilege' and request.get('operation_id') in {'grant', 'revoke'}:
            return mysql_privileges.compile_operation(request['operation_id'], request['draft'])
        kind, operation = request.get('resource_kind'), request.get('operation_id')
        if kind == 'user' and operation in {'rename', 'drop'} or kind == 'role' and operation == 'drop':
            return mysql_accounts.compile_operation(operation+'_'+kind, request['draft'], request.get('target_resource'))
        if request.get('resource_kind') == 'role' and request.get('operation_id') == 'create':
            return mysql_accounts.compile_role(request['draft'])
        if request.get('resource_kind') == 'user' and request.get('operation_id') in {'create', 'alter'}:
            return mysql_accounts.compile_operation(request['operation_id'], request['draft'], request.get('target_resource'))
        if request.get('resource_kind') == 'trigger' and request.get('operation_id') == 'create':
            return mysql_triggers.compile_create(request['draft'])
        if request.get('resource_kind') in mysql_routines.KINDS and request.get('operation_id') == 'create':
            return mysql_routines.compile_create(request['resource_kind'], request['draft'])
        if request.get('resource_kind') == 'index' and request.get('operation_id') == 'create':
            return mysql_indexes.compile_create(request['draft'])
        if request.get('resource_kind')=='server' and request.get('operation_id') in mysql_user_keys.OPERATIONS:
            return mysql_user_keys.compile_operation(request['operation_id'],request['draft'],request.get('target_resource'))
        if request.get('resource_kind')=='table' and request.get('operation_id')=='create':
            compiled=super()._compile(request);options=request['draft'].get('options') or {}
            suffix,parameters=mysql_table_options.compile_options(mysql_table_options.selected(options),options.get('mysql_connection'))
            compiled['statements'][0]['source']+=suffix;compiled['statements'][0]['parameters']+=parameters
            if options.get('mysql_connection') is not None:compiled['warnings']=[*compiled.get('warnings',[]),
                'FEDERATED stores a native remote reference; it does not copy remote rows or verify their recovery. Native table access can contact that remote server.']
            return compiled
        if request.get('resource_kind') == 'server' and request.get('operation_id') in mysql_page_tracking.OPERATIONS:
            return mysql_page_tracking.compile_operation(request['operation_id'], request['draft'], request.get('target_resource'))
        if request.get('resource_kind') == 'server' and request.get('operation_id') in mysql_rewriter.OPERATIONS:
            return mysql_rewriter.compile_operation(request['operation_id'], request['draft'], request.get('target_resource'))
        if request.get('resource_kind')=='server' and request.get('operation_id') in mysql_server_control.OPERATIONS:
            return mysql_server_control.compile_operation(request['operation_id'],request['draft'],request.get('target_resource'))
        if request.get('resource_kind')=='server' and request.get('operation_id') in mysql_xa.OPERATIONS:
            return mysql_xa.compile_operation(request['operation_id'],request['draft'],request.get('target_resource'))
        if request.get('resource_kind')=='server' and request.get('operation_id') in cache_lifecycle.OPERATIONS:
            return cache_lifecycle.compile_operation(request['operation_id'],request['draft'],request.get('target_resource'))
        if request.get('resource_kind')=='server' and request.get('operation_id') in mysql_instance.OPERATIONS:
            return mysql_instance.compile_operation(request['operation_id'],request['draft'],request.get('target_resource'))
        if request.get('resource_kind')=='table' and request.get('operation_id') in mysql_key_cache.OPERATIONS:
            return mysql_key_cache.compile_operation(request['operation_id'],request['draft'],request.get('target_resource'))
        if request.get('resource_kind') == 'column' and request.get('operation_id') in column_masking.OPERATIONS:
            return column_masking.compile_operation(request['operation_id'], request['draft'], request.get('target_resource'))
        if request.get('resource_kind') == foreign_servers.KIND and request.get('operation_id') in foreign_servers.OPERATIONS:
            return foreign_servers.compile_operation(request['operation_id'], request['draft'], request.get('target_resource'))
        if request.get('resource_kind') == srs.KIND and request.get('operation_id') in srs.OPERATIONS:
            return srs.compile_operation(request['operation_id'], request['draft'], request.get('target_resource'))
        return super()._compile(request)

    def apply(self, client, request, connection=None):
        if 'mysql_privilege_change' in (request.get('provider_payload') or {}).get('compiled', {}):
            return mysql_privileges.apply(client, request, connection)
        if 'mysql_account_change' in (request.get('provider_payload') or {}).get('compiled', {}):
            return mysql_accounts.apply(client, request, connection)
        if 'mysql_trigger_create' in (request.get('provider_payload') or {}).get('compiled', {}):
            return mysql_triggers.apply(client, request, connection)
        if 'mysql_routine_create' in (request.get('provider_payload') or {}).get('compiled', {}):
            return mysql_routines.apply(client, request, connection)
        if 'mysql_index_create' in (request.get('provider_payload') or {}).get('compiled', {}):
            return mysql_indexes.apply(client, request, connection)
        if 'mysql_user_keys' in (request.get('provider_payload') or {}).get('compiled',{}):
            return mysql_user_keys.apply(client,request,connection)
        if 'mysql_page_tracking' in (request.get('provider_payload') or {}).get('compiled', {}):
            return mysql_page_tracking.apply(client, request, connection)
        if 'mysql_rewriter' in (request.get('provider_payload') or {}).get('compiled', {}):
            return mysql_rewriter.apply(client, request, connection)
        if 'mysql_server_control' in (request.get('provider_payload') or {}).get('compiled',{}):
            return mysql_server_control.apply(client,request,connection)
        if 'mysql_xa' in (request.get('provider_payload') or {}).get('compiled',{}):
            return mysql_xa.apply(client,request,connection)
        if 'mysql_key_cache_lifecycle' in (request.get('provider_payload') or {}).get('compiled',{}):
            return cache_lifecycle.apply(client,request,connection)
        if 'mysql_instance' in (request.get('provider_payload') or {}).get('compiled',{}):
            return mysql_instance.apply(client,request,connection)
        if 'mysql_key_cache' in (request.get('provider_payload') or {}).get('compiled',{}):
            return mysql_key_cache.apply(client,request,connection)
        if 'mysql_column_masking' in (request.get('provider_payload') or {}).get('compiled', {}):
            return column_masking.apply(client, request, connection)
        if 'mysql_foreign_server' in (request.get('provider_payload') or {}).get('compiled', {}):
            return foreign_servers.apply(client, request, connection)
        if 'mysql_spatial_reference' in (request.get('provider_payload') or {}).get('compiled', {}):
            return srs.apply(client, request, connection)
        return super().apply(client, request, connection)
