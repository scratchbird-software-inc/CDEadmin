"""Typed descriptor-to-task adapter for original-session DuckDB workflows.

Only fixed backend-owned routes can be dispatched. Native admission, private
review storage, one-use execution and caller transaction decisions remain in
the existing task implementations.
"""
from copy import deepcopy

from ..ui_descriptors import UIDescriptorService

GROUPS = {
    'receipt': {
        'transport': 'duckdb_session_receipts',
        'operations': ('list', 'get', 'release'),
        'permissions': ['execute', 'data_read'],
        'admission': 'Owned endpoint/registered target and durable archive. Read-only get/list need no native connection; release requires the exact live original query session and explicit confirmation.',
        'outcomes': ['receipts', 'offset', 'limit', 'total', 'more', 'family', 'receipt', 'original_session', 'archived_read_only', 'live_session_observed', 'outcome_observation', 'transaction_finality_inferred', 'provider_closed'],
        'scope': 'Archived observations never restore native authority. Release discards uncommitted database work but cannot reverse persistent file/secret/process effects. Report native release separately from archive recording. No automatic replay.',
    },
    'secret': {
        'transport': 'native_secret_administration',
        'operations': ('inventory', 'review_create', 'review_drop', 'apply', 'receipts'),
        'permissions': ['execute'],
        'mutation_permissions': ['administer:resource'],
        'admission': 'Owned original session and common native secret administration permissions. Creation uses a typed private constant tree and explicit parse-only expressions. Removal selects the authoritative native resource/storage identity, never a client-supplied native record.',
        'outcomes': ['resources', 'plan_id', 'plan_digest', 'command_preview', 'control_operation', 'provider_result', 'native_storage_observation'],
        'scope': 'Values and private expressions are redacted in public plans/receipts. Persistent-file effects can survive rollback; only the caller settles the transaction. Same-public-metadata secret replacement is not detectable. No automatic replay.',
    },
    'copy': {
        'transport': 'duckdb_database_copy',
        'operations': ('inventory', 'review', 'apply', 'receipt', 'cancel', 'discard'),
        'permissions': ['execute', 'data_read:resource'],
        'mutation_permissions': ['administer:resource', 'data_write:resource', 'filesystem'],
        'admission': 'Distinct attached native catalogs with exact original-session/file/storage identity, writable destination, registered filesystem/memory admission and durable dispatch receipts. Native copy modes are ALL, SCHEMA, DATA.',
        'outcomes': ['review_id', 'review_digest', 'phase', 'state', 'source', 'steps', 'active_table', 'storage', 'storage_observation', 'cancel_requested', 'native_dispatched', 'native_acknowledged', 'rediscovery_verified', 'session_reuse_blocked'],
        'scope': 'Native worker on original handle; poll receipt until finished. ALL uses two native steps; DATA appends. Encryption belongs to separately attached destination. Caller owns commit/rollback; no implicit cutover/rekey or automatic replay.',
    },
    'extension': {
        'transport': 'duckdb_extensions',
        'operations': ('inventory', 'review_install', 'review_load', 'apply', 'receipt'),
        'permissions': ['execute', 'data_read:resource'],
        'mutation_permissions': ['administer:resource', 'filesystem'],
        'admission': 'Native DuckDB1.5.2, original session, actual extension/settings/source identity, native signature/load policy. Native HTTP credentials require separate secret_read authority and httpfs availability; never read credential values.',
        'outcomes': ['extensions', 'context', 'review_id', 'review_digest', 'source', 'state', 'native_dispatched', 'native_acknowledged', 'rediscovery_verified', 'source_access'],
        'scope': 'Original-session synchronous install/load with native filesystem/process effects. No progress/cancel API, implicit rollback or automatic replay. Remote transport qualification remains independent.',
    },
    'attachment': {
        'transport': 'duckdb_attachments',
        'operations': ('inventory', 'review_attach', 'review_detach', 'review_rename', 'apply', 'receipt', 'discard'),
        'permissions': ['execute'],
        'mutation_permissions': ['administer:resource', 'filesystem'],
        'admission': 'Owned original query session, exact native catalog/file identity, registered filesystem root, native read/write/memory authorization and storage eligibility.',
        'outcomes': ['session_scope_id', 'catalogs', 'review_id', 'review_digest', 'state', 'source', 'key_bound', 'native_dispatched', 'native_acknowledged', 'rediscovery_verified', 'native_catalogs', 'new_alias', 'alias_review',
            'invalidate_resource_ids', 'refreshed_descendant_identities', 'binding_notice',
            'physical_file_renamed', 'stored_sql_rewritten', 'alias_restored_by_rollback'],
        'scope': 'Original native session. Catalogs can be instance-visible. Detached catalogs and created files are not restored/removed by rollback. Private key authority expires; never automatically replay.',
    },
}


def definitions():
    return {row['operation_id']: row for row in UIDescriptorService().engine('duckdb')['operations']
            if row['operation_id'].startswith('editor_')}


def contract():
    declared = definitions()
    result = []
    for group, spec in GROUPS.items():
        for operation in spec['operations']:
            identity = 'editor_' + group + '_' + operation
            routing = {}
            if operation.startswith('review_') and group in {'attachment', 'extension'}:
                routing['fixed_draft_action'] = operation.removeprefix('review_')
            if group == 'secret':
                transport, native_operation = {
                    'inventory': ('source_catalog', None),
                    'review_create': ('visual_admin_plan', 'create'),
                    'review_drop': ('visual_admin_plan', 'drop'),
                    'apply': ('visual_admin_apply', None),
                    'receipts': ('visual_admin_operation_list', None),
                }[operation]
                routing.update(transport=transport, native_operation=native_operation)
                if operation == 'review_drop':
                    routing['preflight_transport'] = 'source_catalog'
            permissions = list(spec['permissions'])
            if operation not in {'inventory', 'receipt'}:
                permissions += spec.get('mutation_permissions', [])
            result.append({**deepcopy(spec), 'operation_id': identity,
                'native_operation': 'review' if operation.startswith('review_') else operation,
                'permissions': permissions,
                'original_session_required': group != 'receipt' or operation == 'release',
                **({'transport': 'close_session', 'native_operation': None}
                   if group == 'receipt' and operation == 'release' else {}),
                **routing,
                'descriptor': deepcopy(declared[identity])})
    return {'format': 'scratchrobin.duckdb.editor-operations@1',
        'task_action': 'duckdb_editor_operation', 'operations': result,
        'envelope_fields': ['database_target_id', 'session_id'], 'automatic_replay': False}


def typed_draft(fields, draft):
    if not isinstance(draft, dict) or set(draft) - {f['field_id'] for f in fields}:
        raise ValueError('Original-session draft contains unrelated fields')
    result = {}
    for f in fields:
        key = f['field_id']
        if key not in draft:
            if 'default' in f:
                result[key] = deepcopy(f['default'])
            elif f.get('required'):
                raise ValueError('Required original-session field is missing: ' + key)
            continue
        value = draft[key]
        expected = {'boolean': bool, 'number': int, 'grid': list}.get(f['control'], str)
        if type(value) is not expected:
            raise ValueError('Original-session field has the wrong type: ' + key)
        if f.get('required') and (value == '' or value == []):
            raise ValueError('Required original-session field is empty: ' + key)
        if f.get('options') and value not in [row['value'] for row in f['options']]:
            raise ValueError('Original-session choice is unavailable: ' + key)
        if f['control'] == 'grid':
            value = [typed_draft(f['columns'], row) for row in value]
        result[key] = deepcopy(value)
    return result


def compile_request(identity, draft):
    found = None
    for group, spec in GROUPS.items():
        for operation in spec['operations']:
            if identity == 'editor_' + group + '_' + operation:
                found = group, spec, operation
    if found is None:
        raise ValueError('Original-session descriptor operation is unavailable')
    group, spec, operation = found
    values = typed_draft(definitions()[identity]['fields'], draft)
    if group == 'attachment' and operation == 'review_attach':
        native = {key: values[key] for key in ('alias', 'path', 'read_only', 'conflict', 'create_if_missing')}
        storage = {key: values[key] for key in ('block_size', 'row_group_size', 'storage_version') if values.get(key) != '' and key in values}
        if values['compress_mode'] != 'NATIVE':
            storage['compress'] = values['compress_mode'] == 'ENABLED'
        if storage:
            native['storage_options'] = storage
        if values['key_mode'] == 'SUPPLIED':
            if not values.get('encryption_key'):
                raise ValueError('Supply the private native encryption key')
            native['encryption_key'] = values['encryption_key']
            if values['encryption_cipher'] != 'NATIVE':
                native['encryption_cipher'] = values['encryption_cipher']
        elif values.get('encryption_key') or values['encryption_cipher'] != 'NATIVE':
            raise ValueError('Select supplied-key mode before setting encryption controls')
        return spec['transport'], {'operation': 'review', 'draft': {'action': 'attach', **native}}
    if group == 'attachment' and operation in {'review_detach', 'review_rename'}:
        return spec['transport'], {'operation': 'review', 'draft': {'action': operation.removeprefix('review_'), **values}}
    if group == 'extension' and operation.startswith('review_'):
        native = {key: value for key, value in values.items() if value != ''}
        return spec['transport'], {'operation': 'review', 'draft': {
            'action': operation.removeprefix('review_'), **native}}
    if group == 'copy' and operation == 'review':
        return spec['transport'], {'operation': 'review', 'draft': values}
    if group == 'secret' and operation == 'review_create':
        from .duckdb_secret_fields import properties, expressions
        native = {key: values[key] for key in ('name', 'secret_type', 'persistence_mode', 'on_conflict')}
        if values.get('storage'):
            native['storage'] = values['storage']
        native['properties'] = properties(values.get('property_nodes', []))
        native['property_expressions'] = expressions(values.get('property_expressions', []))
        return spec['transport'], {'operation': operation, 'draft': native}
    if group == 'receipt' and operation == 'release':
        if values['confirmed'] is not True:
            raise ValueError('Confirm releasing the original DuckDB query connection')
        return 'close_session', {}
    return spec['transport'], {'operation': operation, **values}


def serve(service, server, data):
    endpoint = server.endpoint_profile
    if endpoint is None or (endpoint.profile_id, endpoint.provider_id) != ('duckdb-native', 'org.cdeadmin.duckdb'):
        raise ValueError('Select a native DuckDB registration')
    target = data.get('database_target_id')
    if not isinstance(target, str) or not target:
        raise ValueError('Select the owned registered DuckDB target')
    request = data.get('request')
    if request == {'operation_id': 'describe'}:
        service.endpoint_service.workspace(server, database_target_id=target)
        return contract()
    if not isinstance(request, dict) or set(request) != {'operation_id', 'draft'}:
        raise ValueError('Select a descriptor identity and typed draft')
    action, native = compile_request(request['operation_id'], request['draft'])
    if action != 'duckdb_session_receipts' and (
            not isinstance(data.get('session_id'), str) or not data['session_id']):
        raise ValueError('Select the original DuckDB query connection')
    if action == 'close_session':
        return service.close_session(server, data['session_id'], database_target_id=target)
    if action == 'native_secret_administration':
        return secret_action(service, server, target, data['session_id'], native)
    return service.language_tool_action(server, action, {'database_target_id': target,
        'session_id': data.get('session_id'), 'request': native})


def secret_action(service, server, target, session, request):
    """Use the established one-use common plan/apply path for native secrets."""
    envelope = {'database_target_id': target, 'session_id': session}
    operation = request['operation']
    if operation == 'apply':
        return service.apply_visual_admin(server, {**envelope,
            **{key: value for key, value in request.items() if key != 'operation'}})
    if operation == 'receipts':
        value = service.visual_admin_operation_action(server, 'visual_admin_operation_list', envelope)
        return {**value, 'items': [row for row in value['items'] if row['resource_kind'] == 'secret']}
    if operation in {'inventory', 'review_drop'}:
        catalog = service.language_tool_action(server, 'source_catalog', envelope)
        resources = [row for row in catalog['resources'] if row['resource_kind'] == 'secret']
        if operation == 'inventory':
            return {'resources': resources, 'secret_values_read': False, 'scope': 'original-session'}
        resource = next((row for row in resources if row['resource_id'] == request['resource_id']), None)
        if resource is None:
            raise ValueError('Select an observed original-session secret storage identity')
        return service.plan_visual_admin(server, {**envelope, 'resource_kind': 'secret',
            'operation_id': 'drop', 'target_resource': resource,
            'draft': {'confirmation': request['confirmation']}})
    if operation == 'review_create':
        return service.plan_visual_admin(server, {**envelope, 'resource_kind': 'secret',
            'operation_id': 'create', 'draft': request['draft']})
    raise ValueError('Original-session secret operation is unavailable')
