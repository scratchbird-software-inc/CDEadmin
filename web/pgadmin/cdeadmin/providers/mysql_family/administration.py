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
from . import mysql_failover
from . import mysql_user_keys
from . import mysql_xa
from . import mysql_page_tracking
from . import mysql_rewriter
from . import mysql_server_control
from . import mysql_key_cache_lifecycle as cache_lifecycle


HANDLERS = dict(zip(('mysql_'+key for key in (
    'failover privilege_change account_change trigger_create routine_create index_create user_keys page_tracking '
    'rewriter server_control xa key_cache_lifecycle instance key_cache column_masking foreign_server spatial_reference').split()),
    (mysql_failover,mysql_privileges,mysql_accounts,mysql_triggers,mysql_routines,mysql_indexes,mysql_user_keys,mysql_page_tracking,
     mysql_rewriter,mysql_server_control,mysql_xa,cache_lifecycle,mysql_instance,mysql_key_cache,column_masking,foreign_servers,srs)))


class MySQLAdministration(RelationalAdministration):
    def catalog(self, catalog):
        value = deepcopy(catalog)
        for resource in value['objects']:
            if resource['resource_kind']=='server':
                policies = (
                    (mysql_page_tracking, mysql_page_tracking.READS, {'set_page_tracking_backup_id','purge_page_tracking'}),
                    (mysql_rewriter, {'inspect_rewrite_rules'}, {'drop_rewrite_rule'}),
                    (mysql_server_control, set(), set(mysql_server_control.OPERATIONS)),
                    (mysql_xa, {'inspect_prepared_xa'}, set(mysql_xa.OPERATIONS)-{'inspect_prepared_xa'}),
                    (mysql_instance, set(), set()),
                    (cache_lifecycle, {'inspect_key_cache'}, set()),
                )
                for module, reads, destructive in policies:
                    operations = module.OPERATIONS
                    resource['operations'] = [row for row in resource['operations'] if row['operation_id'] not in operations] + [{
                        'operation_id':operation,'title':title[0] if isinstance(title,tuple) else title,
                        'mutation_class':'read' if operation in reads else 'destructive' if operation in destructive else 'admin',
                        'target_required':True,'confirmation_required':operation not in reads,
                    } for operation,title in operations.items()]
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
        for resource in value['objects']:
            for operation in mysql_failover.OPERATIONS:
                if resource['resource_kind']!=('server' if operation=='reset_failover_sources' else 'replication-channel'):continue
                resource['operations'].append({'operation_id':operation,'title':operation_entry(resource['resource_kind'],operation)['title'],
                    'form':operation_entry(resource['resource_kind'],operation),
                    'mutation_class':'destructive' if operation.startswith(('remove_','reset_')) else 'admin',
                    'target_required':True,'confirmation_required':True})
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
        if self._native_operation({'resource_kind':kind,'operation_id':operation,'draft':draft}):return deepcopy(draft)
        if kind=='table' and operation=='create':
            if not isinstance(draft,Mapping):raise RelationalClientError('Select structured native MySQL table properties')
            value=deepcopy(dict(draft));native={key:value.pop(key) for key in ('mysql_table_options','mysql_connection') if key in value}
            if native.get('mysql_connection')=='':native.pop('mysql_connection')
            value=super()._normalize_draft(kind,operation,value);value['options'].update(native);return value
        return super()._normalize_draft(kind, operation, draft)

    @staticmethod
    def _native_operation(request):
        kind,operation=request.get('resource_kind'),request.get('operation_id')
        draft,target=request.get('draft'),request.get('target_resource')
        if kind=='privilege' and operation in {'grant','revoke'}:
            return mysql_privileges.compile_operation,(operation,draft),'invalid_mysql_privilege'
        if kind=='user' and operation in {'rename','drop'} or kind=='role' and operation=='drop':
            return mysql_accounts.compile_operation,(operation+'_'+kind,draft,target),'invalid_mysql_account_identity'
        if kind=='role' and operation=='create':return mysql_accounts.compile_role,(draft,),'invalid_mysql_role'
        if kind=='user' and operation in {'create','alter'}:
            return mysql_accounts.compile_operation,(operation,draft,target),'invalid_mysql_account'
        if kind in mysql_routines.KINDS and operation=='create':return mysql_routines.compile_create,(kind,draft),'invalid_mysql_routine'
        if kind in {'trigger','index'} and operation=='create':
            return (mysql_triggers if kind=='trigger' else mysql_indexes).compile_create,(draft,),'invalid_mysql_'+kind
        for family,module,code in (
            ('server',mysql_failover,'invalid_mysql_failover'),
            ('replication-channel',mysql_failover,'invalid_mysql_failover'),
            ('server',mysql_user_keys,'invalid_user_key'),
            ('server',mysql_page_tracking,'invalid_mysql_page_tracking'),
            ('server',mysql_rewriter,'invalid_mysql_rewriter'),
            ('server',mysql_server_control,'invalid_mysql_server_control'),
            ('server',mysql_xa,'invalid_mysql_xa'),
            ('server',cache_lifecycle,'invalid_mysql_key_cache_lifecycle'),
            ('server',mysql_instance,'invalid_mysql_instance'),
            ('table',mysql_key_cache,'invalid_mysql_key_cache'),
            ('column',column_masking,'invalid_mysql_column_masking'),
            (foreign_servers.KIND,foreign_servers,'invalid_mysql_foreign_server'),
            (srs.KIND,srs,'invalid_mysql_spatial_reference'),
        ):
            if kind==family and operation in module.OPERATIONS:
                if module is mysql_failover and (kind=='server')!=(operation=='reset_failover_sources'):continue
                return module.compile_operation,(operation,draft,target),code

    def validate(self, request):
        from .database_inputs import OPERATIONS, normalize
        if request.get('resource_kind') == 'database' and request.get('operation_id') in OPERATIONS:
            try:
                return super().validate({**request, 'draft': normalize(request['operation_id'], request.get('draft'))})
            except (RelationalClientError, TypeError, ValueError, OverflowError) as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_database_input', 'message': str(error)}]}
        selected=self._native_operation(request)
        if selected:
            compile,args,code=selected
            try:
                compile(*args);return {'errors':[]}
            except RelationalClientError as error:
                return {'errors':[{'field_id':None,'code':code,'message':str(error)}]}
        if request.get('resource_kind')=='table' and request.get('operation_id')=='create':
            value=super().validate(request)
            try:
                draft=request.get('draft') or {};options=draft.get('options') or {}
                mysql_table_options.compile_options(draft.get('mysql_table_options',mysql_table_options.selected(options)),draft.get('mysql_connection',options.get('mysql_connection')) or None)
            except (RelationalClientError,ValueError) as error:value['errors'].append({'field_id':None,'code':'invalid_mysql_table_options','message':str(error)})
            return value
        return super().validate(request)

    def _compile(self, request):
        selected=self._native_operation(request)
        if selected:return selected[0](*selected[1])
        if request.get('resource_kind')=='table' and request.get('operation_id')=='create':
            compiled=super()._compile(request);options=request['draft'].get('options') or {}
            suffix,parameters=mysql_table_options.compile_options(mysql_table_options.selected(options),options.get('mysql_connection'))
            compiled['statements'][0]['source']+=suffix;compiled['statements'][0]['parameters']+=parameters
            if options.get('mysql_connection') is not None:compiled['warnings']=[*compiled.get('warnings',[]),
                'FEDERATED stores a native remote reference; it does not copy remote rows or verify their recovery. Native table access can contact that remote server.']
            return compiled
        return super()._compile(request)

    def apply(self, client, request, connection=None):
        from .relay_positions import position, apply as apply_relay
        compiled = (request.get('provider_payload') or {}).get('compiled', {})
        if 'mysql_relay_review' in compiled or position(compiled):
            return apply_relay(client, request, connection)
        for key,module in HANDLERS.items():
            if key in compiled:return module.apply(client, request, connection)
        return super().apply(client, request, connection)
