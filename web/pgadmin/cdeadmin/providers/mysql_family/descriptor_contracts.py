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


ROUTINE_VARIANTS = {'procedure': 'procedure', 'function': 'function', 'event': 'scheduled'}


def _shown(field, variant, by_id=None, seen=()):
    """Whether the editor can show the field for this variant: a rule on another field
    holds only where that field is itself shown."""
    rule = field.get('visible_when')
    if not rule:
        return True
    if rule.get('field') == 'variant':
        return variant == rule['equals'] if 'equals' in rule else variant in rule.get('in', ())
    controller = (by_id or {}).get(rule.get('field'))
    if controller is None or controller['field_id'] in seen:
        return True
    return _shown(controller, variant, by_id, seen + (field['field_id'],))


def _variant_fields(variant, operation, name='role'):
    """A variant's fields in a family's one form, as the editor shows them for the operation."""
    descriptor = document('forms/'+name+'.form.json')
    by_id = {field['field_id']: field for field in descriptor['fields']}
    return [field_contract(field) for field in descriptor['fields']
            if operation in field.get('modes', ['create', 'alter']) and not field.get('ui_only')
            and _shown(field, variant, by_id)
            and not (operation == 'alter' and field.get('editable_after_create') is False)]


def routine_contract(kind, operation, legacy_fields=()):
    if kind == 'event' and operation == 'drop':
        # The generic drop form's CASCADE default is not native event grammar;
        # mysql_events admits only the confirmation.
        return {'fields': [deepcopy(field) for field in legacy_fields if field['field_id'] == 'confirmation']}
    if operation in {'create', 'alter'}:
        # One routine form serves every variant (2026-11-05); a variant's fields are
        # those its visible_when shows. Fields locked after create are never altered.
        fields = _variant_fields(ROUTINE_VARIANTS[kind], operation, 'routine')
        return {'fields': fields, 'authority': 'ui_descriptors/mysql/forms/routine.form.json'}
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
    fields = _variant_fields('user', operation)
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
    return {'fields': fields, 'authority': 'ui_descriptors/mysql/forms/role.form.json'}


def role_contract(operation, legacy_fields):
    if operation == 'create':
        fields = _variant_fields('role', operation)
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
    return {'fields':fields,'authority':'ui_descriptors/mysql/operations.json'}
