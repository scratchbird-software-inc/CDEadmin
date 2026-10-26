"""MySQL native input admission from its single declarative field source."""
from copy import deepcopy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'ui_descriptors/mysql'


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
