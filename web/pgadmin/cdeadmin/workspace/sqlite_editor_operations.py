"""Descriptor-backed original-session tasks; never reopen a database file.

The shared UI can submit an operation dialog's typed draft through this
adapter. Native authorization, helper admission and outcome handling stay in
the existing task implementation. No client-supplied transport is accepted.
"""
from copy import deepcopy

from ..ui_descriptors import UIDescriptorService


GROUPS = {
    'schema': {
        'transport': 'sqlite_retained_schema',
        'operations': ('capture', 'columns', 'alter', 'preview', 'review', 'start'),
        'permissions': ['execute', 'administer'],
        'admission': 'Owned original session and registered target; durable review store, exact DDN baseline/desired identities, original-context fingerprint and open caller transaction for apply. Native version/authorizer admission per stage.',
        'outcomes': ['document', 'snapshot', 'operations', 'execution_sha256', 'review_id', 'review_digest', 'state', 'worker_active', 'outcome', 'native_session_release_confirmed'],
        'scope': 'Original-session DDN only. Successful native DDL is pending caller commit; never auto-commit. An owned savepoint bounds rollback; unknown outcomes block reuse. Poll durable receipt; cancellation does not establish rollback.',
    },
    'schema_receipt': {
        'transport': 'sqlite_retained_schema_receipts',
        'operations': ('list', 'receipt', 'cancel', 'remove'),
        'permissions': ['administer'],
        'admission': 'Owned endpoint/registered target, durable archive and original authenticated owner. No native connection or SQL needed for archive reads.',
        'outcomes': ['state', 'worker_active', 'outcome', 'archived_read_only', 'native_sql_requested', 'native_session_release_confirmed'],
        'scope': 'Saved receipts never revive original-session authority. Cancellation is best effort against an active worker; read final outcome. Removal requires confirmation and a released native session.',
    },
    'preupdate': {
        'transport': 'sqlite_native_preupdate',
        'operations': ('inventory', 'start', 'status', 'events', 'stop', 'clear'),
        'permissions': ['execute'],
        'additional_permissions': {'except_inventory': ['administer']},
        'admission': 'Matching native preupdate helper and loaded SQLite instance, runtime >=3.45.1; native hook/capture ownership and operator buffer limits.',
        'outcomes': ['helper_available', 'status', 'events', 'run_id', 'scope', 'transaction_open'],
        'scope': 'Before-change diagnostics, including rolled-back changes. Never commit evidence. Exact sequence strings, typed cells, bounded observations and explicit dropped counts.',
    },
    'array': {
        'transport': 'sqlite_native_arrays',
        'operations': ('inventory', 'create', 'status', 'close'),
        'permissions': ['execute'],
        'admission': 'Native array helper, matching loaded SQLite instance, runtime >=3.53.0 and operator memory policy. Inventory exposes actual availability.',
        'outcomes': ['arrays', 'array', 'binding', 'native_data_bytes', 'helper_available', 'transaction_open', 'closed'],
        'scope': 'Original connection only; native allocations and bindings disappear on close. No database mutation or transaction settlement.',
    },
    'extension': {
        'transport': 'sqlite_extensions',
        'operations': ('inventory', 'review', 'load', 'receipt'),
        'permissions': ['execute'],
        'additional_permissions': {'review': ['administer', 'filesystem'], 'load': ['administer', 'filesystem']},
        'admission': 'Operator manifest, digest-verified staged library and native CPython loader/config API. No client library path.',
        'outcomes': ['review_id', 'state', 'extension', 'loader_cleanup_confirmed', 'native_additions', 'retry_allowed'],
        'scope': 'Original connection; native initialization can have irreversible process effects. No automatic retry/reload. Unknown outcome blocks reuse.',
    },
}


from . import sqlite_capture_descriptors
GROUPS.update(sqlite_capture_descriptors.groups())


def definitions():
    operations = UIDescriptorService().engine('sqlite')['operations']
    return {item['operation_id']: item for item in operations
            if item['operation_id'].startswith('editor_')}


def contract():
    """Machine-readable routes accompany the ordinary engine descriptors."""
    declared = definitions()
    rows = []
    for group, spec in GROUPS.items():
        for operation in spec['operations']:
            identity = 'editor_' + group + '_' + operation
            permissions = list(spec['permissions'])
            extra = spec.get('additional_permissions', {})
            permissions += extra.get(operation, [])
            if operation != 'inventory':
                permissions += extra.get('except_inventory', [])
            if group == 'capture' and operation == 'inventory':
                permissions = ['execute']
            native_operation = operation
            if group in sqlite_capture_descriptors.PREFIXES:
                native_operation = sqlite_capture_descriptors.PREFIXES[group] + ('review' if group == 'inspection' and operation.startswith('review_') else operation)
            if group == 'delivery':
                native_operation = sqlite_capture_descriptors.DELIVERY_ACTIONS[operation]
            original = (group not in sqlite_capture_descriptors.GROUPS and group != 'schema_receipt' or
                        group == 'capture' or group == 'export' and operation == 'review' or
                        group == 'diff' and operation in {'catalog', 'tables', 'review'})
            rows.append({**deepcopy(spec), 'operation_id': identity,
                         'permissions': permissions,
                         'native_operation': native_operation,
                         'descriptor': deepcopy(declared[identity]),
                         'original_session_required': original,
                         **({'transport': 'source_catalog', 'native_operation': None}
                            if identity == 'editor_schema_capture' else {})})
    return {'format': 'scratchrobin.sqlite.editor-operations@1',
            'task_action': 'sqlite_editor_operation', 'operations': rows,
            'envelope_fields': ['database_target_id', 'session_id'],
            'automatic_replay': False,
            'sql_preview': 'Show the native review/preview when available. Native C API actions have no SQL statement; never invent one.'}


def compile_request(identity, draft):
    if not isinstance(identity, str) or not isinstance(draft, dict):
        raise ValueError('Select an original-session descriptor operation and typed draft')
    spec = None
    for group, candidate in GROUPS.items():
        for operation in candidate['operations']:
            if identity == 'editor_' + group + '_' + operation:
                spec, native_operation = candidate, operation
                break
    if spec is None:
        raise ValueError('Original-session descriptor operation is unavailable')
    fields = definitions()[identity]['fields']
    allowed = {field['field_id'] for field in fields}
    if set(draft) - allowed:
        raise ValueError('Original-session draft contains unrelated fields')
    request = {}
    for field in fields:
        key = field['field_id']
        if key not in draft:
            if 'default' in field:
                request[key] = deepcopy(field['default'])
            elif field.get('required'):
                raise ValueError('Required original-session field is missing: ' + key)
            continue
        value = draft[key]
        control = field['control']
        expected = {'boolean': bool, 'text': str, 'code': str,
                    'select': str, 'number': int, 'grid': list}.get(control)
        if expected and type(value) is not expected:
            raise ValueError('Original-session field has the wrong type: ' + key)
        if field.get('required') and value == '':
            raise ValueError('Required original-session field is empty: ' + key)
        if field.get('options') and value not in [row['value'] for row in field['options']]:
            raise ValueError('Original-session choice is unavailable: ' + key)
        if control == 'grid':
            if field.get('required') and not value:
                raise ValueError('Required original-session grid is empty: ' + key)
            if field.get('item_kind') == 'string':
                if any(not isinstance(item, str) or not item for item in value):
                    raise ValueError('Select original object identities in ' + key)
            else:
                columns = {column['field_id']: column for column in field['columns']}
                for row in value:
                    if not isinstance(row, dict) or set(row) - set(columns):
                        raise ValueError('Original-session grid contains unrelated fields: ' + key)
                    for name, item in row.items():
                        if item in (None, '') and not columns[name].get('required'):
                            continue
                        kind = columns[name]['control']
                        expected = {'boolean': bool, 'number': int}.get(kind, str)
                        if type(item) is not expected:
                            raise ValueError('Original-session grid cell has the wrong type: ' + name)
                        choices = columns[name].get('options')
                        if choices and item not in [choice['value'] for choice in choices]:
                            raise ValueError('Original-session grid choice is unavailable: ' + name)
                    if any(column.get('required') and row.get(name) in (None, '')
                           for name, column in columns.items()):
                        raise ValueError('Original-session grid requires its typed operands: ' + key)
        request[key] = deepcopy(value)
    if any(identity.startswith('editor_' + group + '_') for group in sqlite_capture_descriptors.GROUPS):
        return sqlite_capture_descriptors.compile_fields(identity, request, fields)
    if identity == 'editor_array_create':
        request['values'] = array_values(request['type'], request['values'])
    if identity == 'editor_schema_columns':
        request['columns'] = column_values(request['columns'])
    if 'alterations' in request:
        request['alterations'] = alteration_values(request['alterations'])
    if identity == 'editor_schema_capture':
        return 'source_catalog', {}
    if identity == 'editor_schema_receipt_remove' and request['confirmed'] is not True:
        raise ValueError('Confirm removing this original-session receipt')
    return spec['transport'], {'operation': native_operation, **request}


def alteration_values(rows):
    """Keep optional grid cells out of strict native action selectors."""
    from .sqlite_retained_alter import ACTIONS
    values = []
    for row in rows:
        if not isinstance(row, dict) or row.get('action') not in ACTIONS:
            raise ValueError('Select a supported original-session table alteration')
        value = {key: deepcopy(item) for key, item in row.items() if item not in (None, '')}
        if set(value) - ({'action', 'resource_id'} | ACTIONS[row['action']]):
            raise ValueError('Alteration fields do not belong to the selected native action')
        values.append(value)
    return values


def column_values(rows):
    """Flattened typed controls cover the structured native column contract."""
    from .sqlite_column_design import declaration
    columns = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Select typed original-session column additions')
        column, generated, references, names = {}, {}, {}, {}
        for key, value in row.items():
            if value is None or value == '':
                continue
            if key in {'generated_expression', 'generated_storage'}:
                generated[key.removeprefix('generated_')] = value
            elif key.startswith('references_'):
                references[key.removeprefix('references_')] = value
            elif key.endswith('_constraint_name'):
                names[key.removesuffix('_constraint_name')] = value
            else:
                column[key] = value
        if generated:
            column['generated'] = generated
        if references:
            column['references'] = references
        if names:
            column['constraint_names'] = names
        declaration(column)
        columns.append(column)
    return columns


def array_values(kind, rows):
    """Map typed grid cells to the existing lossless native array envelope."""
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'encoding', 'value'}:
            raise ValueError('Select typed array element rows')
        encoding = row.get('encoding')
        value = row.get('value')
        if encoding == 'null':
            if kind not in {'text', 'blob'} or value not in (None, ''):
                raise ValueError('Only native TEXT/BLOB arrays accept null elements without a value')
            result.append(None)
        elif encoding == 'base64':
            if kind not in {'text', 'blob'} or not isinstance(value, str):
                raise ValueError('Base64 elements require native TEXT/BLOB arrays')
            result.append({'encoding': 'base64', 'data': value,
                           **({'native_storage_class': 'text'} if kind == 'text' else {})})
        elif encoding == 'scalar' and kind != 'blob' and isinstance(value, str):
            result.append(value)
        else:
            raise ValueError('Select a compatible array element representation')
    # Exercise native-value admission before allocating or borrowing a handle.
    from ..providers.sqlite.array_values import encode
    encode(kind, result)
    return result


def serve(service, server, data):
    endpoint = server.endpoint_profile
    if endpoint is None or (endpoint.profile_id, endpoint.provider_id) != (
            'sqlite-native', 'org.cdeadmin.sqlite'):
        raise ValueError('Select a native SQLite registration')
    if not isinstance(data.get('database_target_id'), str) or not data['database_target_id']:
        raise ValueError('Select the owned registered SQLite target')
    request = data.get('request')
    if not isinstance(request, dict):
        raise ValueError('Select an original-session descriptor request')
    if request == {'operation_id': 'describe'}:
        # Resolve ownership/admission without opening a native connection.
        service.endpoint_service.workspace(server, database_target_id=data.get('database_target_id'))
        return contract()
    if set(request) != {'operation_id', 'draft'}:
        raise ValueError('Select a descriptor identity and typed draft')
    action, native = compile_request(request['operation_id'], request['draft'])
    if action == 'workspace_form_download':
        native = deepcopy(native)
        action = native.pop('operation')
        return {'binary_delivery': {'method': 'POST', 'workspace_action': action,
                'encoding': 'application/x-www-form-urlencoded',
                'payload': {'database_target_id': data['database_target_id'], **native},
                'max_payload_utf8_bytes': 4096, 'requires_authenticated_workspace': True}}
    if action in {'sqlite_capture_export', 'sqlite_changeset'}:
        return sqlite_capture_descriptors.dispatch(service, server, action, native, data.get('database_target_id'), data.get('session_id'))
    if action != 'sqlite_retained_schema_receipts' and (
            not isinstance(data.get('session_id'), str) or not data['session_id']):
        raise ValueError('Select the original query connection')
    if action == 'source_catalog':
        return service.language_tool_action(server, action, {
            'database_target_id': data.get('database_target_id'),
            'session_id': data['session_id'], 'include_system': False})
    return service.language_tool_action(server, action, {
        'database_target_id': data.get('database_target_id'),
        'session_id': data.get('session_id'), 'request': native})
