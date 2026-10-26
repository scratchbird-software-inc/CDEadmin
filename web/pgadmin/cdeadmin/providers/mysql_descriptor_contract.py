"""MySQL native input admission from its single declarative field source."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'ui_descriptors/mysql'


@lru_cache(maxsize=1)
def operation_documents():
    return {(row['resource_kind'], row['operation_id']): row
            for row in json.loads((ROOT / 'operations.json').read_text())['operations']}


def operation_entry(kind, operation):
    """Adapt descriptor data to the existing native catalog/input contract."""
    row = operation_documents().get((kind, operation))
    if row is None:
        return None
    fields = {}
    for original in row['fields']:
        if original.get('ui_only'):
            continue
        field = deepcopy(original)
        field['field_id'] = field.pop('backend_field_id', field['field_id'])
        if '.' in field['field_id']:
            root = field['field_id'].split('.')[0]
            fields.setdefault(root, {'field_id': root, 'label': root.replace('_', ' ').title(),
                                     'control': 'keyvalue', 'required': False})
            continue
        field['required'] = bool(field.get('required', False))
        # Visibility is a UI concern. The native compiler owns conditional
        # requirements, including DEFAULT without a supplied cache value.
        if field.pop('visible_when', None) is not None:
            field['required'] = False
        if 'min' in field:
            field['minimum'] = field.pop('min')
        if 'max' in field:
            field['maximum'] = field.pop('max')
        if 'default_path' in field:
            field['initial_value_path'] = field.pop('default_path')
        fields.setdefault(field['field_id'], field)
    return {'form_id': 'mysql.' + kind + '.' + operation,
            'title': row['title'], 'fields': list(fields.values())}


def maintenance_contract(kind, operation, draft):
    """Validate native inputs; presentation controls stay in descriptor JSON.

    AUTO and encoded mapping strings preserve the former scalar/object API.
    Typed inputs use their declared representation without JSON coercion.
    """
    entry = operation_entry(kind, operation)
    if entry is None:
        return None
    fields = entry['fields']
    for field in fields:
        name = field['field_id']
        if kind == 'system-variable' and name == 'value_type':
            field['default'] = 'AUTO'
            field['options'].append({'value': 'AUTO', 'label': 'Automatic'})
        if kind == 'system-variable' and name == 'value':
            mode = draft.get('value_type', 'AUTO')
            field['control'] = {'AUTO': 'json', 'TEXT': 'text', 'BOOLEAN': 'boolean',
                                'SAFE_INTEGER': 'number'}.get(mode if isinstance(mode, str) else None, 'text')
            field.pop('default', None)
            if field['control'] == 'json':
                field['json_type'] = 'scalar'
            if draft.get('value_mode', 'VALUE') != 'VALUE':
                field['visible_when'] = {'field_id': 'value_mode', 'equals': 'VALUE'}
        elif name in {'until', 'filters', 'histogram_data', 'partitions', 'where'} and isinstance(draft.get(name), str):
            field['control'] = 'json'
        elif name in {'partitions', 'where'} and isinstance(draft.get(name), dict):
            field['control'] = 'keyvalue'
    return {'fields': fields, 'authority': 'ui_descriptors/mysql/operations.json'}


def database_fields(mode):
    """Keep existing endpoint/visual input contracts without a second form.

    Catalog-backed choices are native identifier text at the backend boundary:
    validate/plan must also work before there is a connected catalog. MySQL
    validates availability when executing the reviewed native statement.
    """
    descriptor = json.loads((ROOT / 'forms/database.form.json').read_text())
    fields = []
    for item in descriptor['fields']:
        if item.get('ui_only') or mode not in item.get('modes', ['create', 'alter']):
            continue
        field = deepcopy(item)
        field['field_id'] = field.pop('backend_field_id', field['field_id'])
        field['required'] = bool(field.get('required', False))
        if field.get('option_values_path'):
            field['control'] = 'text'
        fields.append(field)
    return tuple(fields)
