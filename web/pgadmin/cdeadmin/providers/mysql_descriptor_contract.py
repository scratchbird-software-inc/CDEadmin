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
    fields = []
    for original in row['fields']:
        field = deepcopy(original)
        field['field_id'] = field.pop('backend_field_id', field['field_id'])
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
        fields.append(field)
    return {'form_id': 'mysql.' + kind + '.' + operation,
            'title': row['title'], 'fields': fields}


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
