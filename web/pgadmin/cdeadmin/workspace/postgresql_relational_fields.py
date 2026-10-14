"""Translate admitted graphical field edits without discarding native facts."""
from copy import deepcopy


def merge_fields(before, desired):
    native = deepcopy(desired['native'])
    old_columns = before['native'].get('children', {}).get('pg_attribute', [])
    columns = native.get('children', {}).get('pg_attribute', [])
    old_by_number = {str(column['attnum']): column for column in old_columns}
    by_number = {str(column['attnum']): column for column in columns}
    prefix = before['uid'] + ':'
    for uid, fields in desired.get('fields', {}).items():
        original = before.get('fields', {}).get(uid)
        number = uid[len(prefix):] if uid.startswith(prefix) else None
        if original is None and isinstance(number, str) and number.startswith('new:'):
            import uuid
            from .postgresql_creation import column_definition
            suffix = number[4:]
            if str(uuid.UUID(suffix)) != suffix:
                raise ValueError('New graphical field requires a canonical draft UUID')
            if set(fields.get('_property_names', [])) - {'uid', 'datatype', 'nullable'}:
                raise ValueError('New graphical field has unsupported native creation properties')
            definition = {'name': fields.get('_label'), 'data_type': fields.get('datatype')}
            if 'nullable' in fields:
                definition['nullable'] = fields['nullable']
            column_definition(definition)
            draft = {'resource_id': 'postgresql:new:' + suffix, 'definition': definition}
            additions = native.setdefault('add_columns', [])
            if not isinstance(additions, list):
                raise ValueError('Native column additions must be an array')
            matches = [item for item in additions if isinstance(item, dict) and item.get('resource_id') == draft['resource_id']]
            if matches and (len(matches) != 1 or matches[0] != draft):
                raise ValueError('Graphical and native column creation disagree')
            if not matches:
                additions.append(draft)
            continue
        if original is None or number not in old_by_number or number not in by_number:
            raise ValueError('Graphical field requires explicit native identity reconciliation')
        old, column = old_by_number[number], by_number[number]
        for graphical, catalog in [('nullable', 'attnotnull'), ('description', 'comment'), ('datatype', 'formatted_type')]:
            if graphical in fields and ((graphical == 'nullable' and type(fields[graphical]) is not bool) or
                    (graphical == 'description' and not isinstance(fields[graphical], str))):
                raise ValueError('Invalid graphical column property type')
            # Absence is presentation omission, never implicit DROP/clear intent.
            if graphical not in fields or fields[graphical] == original.get(graphical):
                continue
            value = fields[graphical]
            if graphical == 'nullable':
                if type(value) is not bool:
                    raise ValueError('Graphical nullable must be boolean')
                value = not value
            elif not isinstance(value, str):
                raise ValueError('Graphical description must be text; use empty text to clear it')
            if graphical == 'datatype':
                from ..providers.postgresql.native_admin import _type_reference
                _type_reference(value, 'graphical datatype')
            native_value = column.get(catalog)
            if native_value != old.get(catalog) and native_value != value:
                raise ValueError('Graphical and native column edits disagree')
            column[catalog] = value
    return native
