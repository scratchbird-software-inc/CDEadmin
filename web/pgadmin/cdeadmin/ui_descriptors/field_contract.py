"""Backend field admission from an engine's declarative UI descriptors.

Visual administration validates a draft against an operation's fields before
the provider plans it. The catalog's fields predate several engines' UI
descriptors, so drafts their editors send were refused as unknown fields
(live, 2026-10-31: 13 of 15 YugabyteDB form round trips through the UI path).
This admits what the engine's own descriptors send, plus every catalog field
they do not define, so existing API drafts keep working. The provider's
native compiler stays the authority on values and combinations.

Data for validation only: it builds no form and changes no catalog.
"""
from copy import deepcopy
import re

_BRACKET = re.compile(r'^([a-z0-9_]+)\[[a-z0-9_]+=[^\]]+\]$', re.I)
_EDITOR_OPERATIONS = {'create', 'alter'}
# An alter's Columns grid is sent as its row diff (diffColumns in
# static/js/cdeadmin_ui/objects/descriptors.js).
_COLUMN_DIFF = ('add_columns', 'drop_columns', 'rename_columns',
                'alter_columns')


def _service():
    from . import UIDescriptorService
    return UIDescriptorService()


def _root(field):
    target = field.get('backend_field_id') or field['field_id']
    bracket = _BRACKET.match(target)
    if bracket:
        return bracket.group(1), 'list'
    if '.' in target:
        return target.split('.', 1)[0], 'object'
    return target, None


def _contract(field, operation):
    root, shape = _root(field)
    if shape == 'list':
        return {'field_id': root, 'label': root.replace('_', ' ').title(),
                'control': 'grid', 'required': False}
    if shape == 'object':
        return {'field_id': root, 'label': root.replace('_', ' ').title(),
                'control': 'keyvalue', 'required': False}
    value = deepcopy(field)
    value['field_id'] = root
    value.pop('backend_field_id', None)
    # An alter sends only what changed and the target names the object, so
    # a field the create form requires is not required in the change set;
    # a field shown for one variant is required only there, which the
    # native compiler checks.
    value['required'] = (bool(value.get('required')) and
                         operation == 'create' and
                         not value.get('visible_when'))
    # Visibility and defaults are presentation: the editor sends what it
    # shows, so nothing hidden is filled in here.
    value.pop('visible_when', None)
    value.pop('default', None)
    if 'min' in value:
        value['minimum'] = value.pop('min')
    if 'max' in value:
        value['maximum'] = value.pop('max')
    if value.pop('wrap_list', False):
        # The editor sends the one chosen value as a list (toBackendDraft).
        for key in ('options', 'option_values_path', 'record_key'):
            value.pop(key, None)
        value.update(control='json', json_type='array',
                     array_editor={'item_kind': 'string'})
        return value
    if value.get('control') in {'select', 'multiselect'} and not value.get(
            'options'):
        # Choices drawn from the draft, catalog or dialect at runtime have no
        # static list here; the native compiler checks the chosen names.
        value['control'] = (
            'text' if value['control'] == 'select' else 'reference')
        value.pop('option_values_path', None)
    return value


def _editor_fields(engine, kind, operation):
    for form in _service().engine(engine)['forms'].values():
        if kind not in form.get('resource_kinds', ()):
            continue
        return [field for tab in form.get('tabs', ())
                for field in tab.get('fields', ())
                if not field.get('ui_only') and (
                    not field.get('modes') or operation in field['modes'])
                and not (operation == 'alter' and
                         field.get('editable_after_create') is False)]
    return None


def _operation_fields(engine, kind, operation):
    for item in _service().engine(engine).get('operations', ()):
        if (item.get('resource_kind'), item.get('operation_id')) != (
                kind, operation):
            continue
        fields = list(item.get('fields', ()))
        if item.get('confirmation') == 'typed_name':
            fields.append({'field_id': 'confirmation', 'label': 'Confirmation',
                           'control': 'text', 'required': False})
        return fields
    return None


def descriptor_field_contract(engine, request):
    """Return the admitted fields for one operation, or None to keep the
    catalog's fields when the engine's descriptors do not cover it."""
    kind, operation = request['resource_kind'], request['operation_id']
    descriptor = (_editor_fields(engine, kind, operation)
                  if operation in _EDITOR_OPERATIONS else None)
    if descriptor is None:
        descriptor = _operation_fields(engine, kind, operation)
    if descriptor is None:
        return None
    legacy = request.get('legacy_fields') or ()
    by_id = {field['field_id']: field for field in legacy}
    fields, seen = [], set()
    for field in descriptor:
        value = _contract(field, operation)
        if value['field_id'] in seen:
            continue
        seen.add(value['field_id'])
        if _root(field)[1] and value['field_id'] in by_id:
            # A catalog field already describes this list or object root.
            value = deepcopy(by_id[value['field_id']])
        fields.append(value)
    grid = next((field for field in descriptor
                 if _root(field)[0] == 'columns' and
                 field.get('control') == 'grid'), None)
    if operation == 'alter' and grid is not None:
        for name in _COLUMN_DIFF:
            if name in seen:
                continue
            seen.add(name)
            if name not in by_id:
                fields.append({'field_id': name, 'control': 'grid',
                               'label': name.replace('_', ' ').capitalize(),
                               'required': False})
                continue
            value = deepcopy(by_id[name])
            children = (value.get('array_editor') or {}).get('fields')
            if name == 'add_columns' and isinstance(children, list):
                # An added row carries the editor's column fields; each is
                # still checked, beside the catalog's own.
                known = {child['field_id'] for child in children}
                for column in grid.get('columns', ()):
                    child = _contract(column, 'alter')
                    if child['field_id'] not in known:
                        child.setdefault('label', child['field_id'])
                        children.append(child)
            fields.append(value)
    # Catalog fields the descriptors replaced stay admitted for API callers
    # but are no longer required: the editor sends the descriptor's fields.
    for field in legacy:
        if field['field_id'] not in seen:
            value = deepcopy(field)
            value['required'] = False
            fields.append(value)
    for field in fields:
        field.setdefault('label', field['field_id'])
        field['required'] = (bool(field.get('required')) and
                             operation != 'alter')
    return {'fields': fields,
            'authority': f'ui_descriptors/{engine}'}


class DescriptorFieldContract:
    """Client mixin: admit drafts by the engine's descriptors.

    Set ``descriptor_engine`` to the ui_descriptors folder name.
    """

    descriptor_engine = None

    def admin_operation_field_contract(self, request):
        if not self.descriptor_engine:
            return None
        return descriptor_field_contract(self.descriptor_engine, request)
