"""Backend field admission from the engine's declarative UI descriptors.

This reads data for validation only. It does not build a legacy form, change a
catalog or render UI. The native compiler remains the authority for key-part
semantics and for compatibility with existing scalar column-name lists.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]/'ui_descriptors/mysql'


@lru_cache(maxsize=4)
def document(name):
    return json.loads((ROOT/name).read_text())


def field_contract(field):
    value = deepcopy(field)
    value['field_id'] = value.pop('backend_field_id', value['field_id'])
    value['required'] = bool(value.get('required', False))
    # Visibility belongs to presentation. The native compiler checks invalid
    # combinations; API callers must not silently lose supplied option values
    # because they omitted a presentation controller's default.
    value.pop('visible_when', None)
    if 'min' in value: value['minimum'] = value.pop('min')
    if 'max' in value: value['maximum'] = value.pop('max')
    if 'columns' in value:
        value['columns'] = [field_contract(child) for child in value['columns']]
    return value


def index_contract(operation, legacy_fields):
    if operation == 'create':
        from .mysql_indexes import KEYS
        descriptor = document('forms/index.form.json')
        fields = [field_contract(field) for field in descriptor['fields'] if 'create' in field.get('modes', ['create', 'alter'])]
        names = {field['field_id'] for field in fields}
        fields += [deepcopy(field) for field in legacy_fields
            if field['field_id'] not in names and field['field_id'] in KEYS | {'options'}]
        return {'fields': fields, 'authority': 'ui_descriptors/mysql/forms/index.form.json'}
    if operation == 'visibility':
        descriptor = next(value for value in document('operations.json')['operations']
            if value['resource_kind'] == 'index' and value['operation_id'] == operation)
        return {'fields': [field_contract(field) for field in descriptor['fields']],
            'authority': 'ui_descriptors/mysql/operations.json'}
    return None


def routine_contract(kind, operation):
    if operation in {'create', 'alter'}:
        suffix = {'procedure': 'routine', 'function': 'routine-function',
                  'event': 'routine-scheduled'}[kind]
        descriptor = document('forms/'+suffix+'.form.json')
        fields = [field_contract(field) for field in descriptor['fields']
                  if operation in field.get('modes', ['create', 'alter'])]
        return {'fields': fields, 'authority': 'ui_descriptors/mysql/forms/'+suffix+'.form.json'}
    if kind == 'event' and operation == 'rename':
        selected = next(value for value in document('operations.json')['operations']
                        if value['resource_kind'] == kind and value['operation_id'] == operation)
        return {'fields': [field_contract(field) for field in selected['fields']]}
    return None
