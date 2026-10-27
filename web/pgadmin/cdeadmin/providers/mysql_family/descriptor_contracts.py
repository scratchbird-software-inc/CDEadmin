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


def trigger_contract(legacy_fields):
    descriptor = document('forms/trigger.form.json')
    fields = [field_contract(field) for field in descriptor['fields']]
    names = {field['field_id'] for field in fields}
    fields += [deepcopy(field) for field in legacy_fields
               if field['field_id'] not in names and field['field_id'] in {'active', 'position', 'options', 'events'}]
    # A legacy event list must not acquire a default beside the descriptor's
    # single native event; the compiler refuses ambiguous explicit inputs.
    for field in fields:
        if field['field_id'] in {'event', 'events'}:
            field.pop('default', None)
            field['required'] = False
    return {'fields': fields, 'authority': 'ui_descriptors/mysql/forms/trigger.form.json'}


def account_contract(operation, legacy_fields):
    if operation == 'rename':
        descriptor = next(value for value in document('operations.json')['operations']
                          if value['resource_kind'] == 'user' and value['operation_id'] == operation)
        return {'fields': [field_contract(field) for field in descriptor['fields']]}
    descriptor = document('forms/role-user.form.json')
    fields = [field_contract(field) for field in descriptor['fields']
              if operation in field.get('modes', ['create', 'alter'])]
    # Factor rows contain password/authentication-string cells. The backend
    # redacts the entire supplied group from validation and public plans.
    for field in fields:
        if field['field_id'] in {'authentication_factors', 'factor_actions'}:
            field['sensitive'] = True
    names = {field['field_id'] for field in fields}
    for field in legacy_fields:
        if field['field_id'] not in names and field['field_id'] in {'active', 'administrator', 'options'}:
            value = deepcopy(field)
            if value['field_id'] == 'active':
                value.pop('default', None)
                value['required'] = False
            fields.append(value)
    return {'fields': fields, 'authority': 'ui_descriptors/mysql/forms/role-user.form.json'}


def role_contract(operation, legacy_fields):
    if operation == 'create':
        descriptor = document('forms/role.form.json')
        fields = [field_contract(field) for field in descriptor['fields']]
        fields.extend(deepcopy(field) for field in legacy_fields if field['field_id'] == 'options')
        return {'fields': fields, 'authority': 'ui_descriptors/mysql/forms/role.form.json'}
    if operation in {'grant', 'revoke', 'set_default'}:
        descriptor = next(value for value in document('operations.json')['operations']
                          if value['resource_kind'] == 'role' and value['operation_id'] == operation)
        return {'fields': [field_contract(field) for field in descriptor['fields']],
                'authority': 'ui_descriptors/mysql/operations.json'}
    return None


def privilege_contract(operation):
    descriptor = next(row for row in document('operations.json')['operations']
                      if row['resource_kind'] == 'privilege' and row['operation_id'] == operation)
    fields = [field_contract(field) for field in descriptor['fields']]
    next(field for field in fields if field['field_id'] == 'grantees')['required'] = False
    # Preserve the former scalar account/list API without exposing a second UI.
    fields += [{'field_id':'principal','label':'Principal','control':'text','required':False},
               {'field_id':'object_name','label':'Object name','control':'text','required':False}]
    return {'fields':fields,'authority':'ui_descriptors/mysql/forms/role-privilege.form.json'}
