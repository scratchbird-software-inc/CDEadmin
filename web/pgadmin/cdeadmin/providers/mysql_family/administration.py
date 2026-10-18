"""MySQL native administration additions to the shared relational UI."""
from copy import deepcopy

from ..relational_admin import RelationalAdministration
from ...sdk import RelationalClientError
from . import spatial_reference_systems as srs


class MySQLAdministration(RelationalAdministration):
    def catalog(self, catalog):
        value = deepcopy(catalog)
        value['objects'] = [row for row in value['objects'] if row['resource_kind'] != srs.KIND]
        value['objects'].append({'resource_kind': srs.KIND,
            'title': 'Spatial reference systems', 'operations': [{
                'operation_id': operation,
                'title': 'Inspect spatial reference system' if operation == 'inspect' else srs.form(operation, self._field)['title'],
                'mutation_class': 'read' if operation == 'inspect' else 'destructive' if operation == 'drop' else 'admin',
                'target_required': operation != 'create',
                'confirmation_required': operation != 'inspect',
            } for operation in ['inspect', 'create', 'alter', 'drop']]})
        return super().catalog(value)

    def _form(self, kind, operation):
        if kind == srs.KIND and operation in srs.OPERATIONS:
            return srs.form(operation, self._field)
        return super()._form(kind, operation)

    def _normalize_draft(self, kind, operation, draft):
        if kind == srs.KIND and operation in srs.OPERATIONS:
            return deepcopy(draft)
        return super()._normalize_draft(kind, operation, draft)

    def validate(self, request):
        if request.get('resource_kind') == srs.KIND and request.get('operation_id') in srs.OPERATIONS:
            try:
                srs.compile_operation(request['operation_id'], request.get('draft'), request.get('target_resource'))
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_mysql_spatial_reference', 'message': str(error)}]}
        return super().validate(request)

    def _compile(self, request):
        if request.get('resource_kind') == srs.KIND and request.get('operation_id') in srs.OPERATIONS:
            return srs.compile_operation(request['operation_id'], request['draft'], request.get('target_resource'))
        return super()._compile(request)

    def apply(self, client, request, connection=None):
        if 'mysql_spatial_reference' in (request.get('provider_payload') or {}).get('compiled', {}):
            return srs.apply(client, request, connection)
        return super().apply(client, request, connection)
