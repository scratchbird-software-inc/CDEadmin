"""Original-session DuckDB DDN admission, with archive reads independent of SQL (DU-AUD-17)."""

from __future__ import annotations

from ..operations.store import JsonOperationStore
from .firebird_schema_apply import SchemaApplyError
from .firebird_schema_plan import digest
from .duckdb_retained_applications import DuckDBRetainedApplications


def scope(service, server, target):
    endpoint = server.endpoint_profile
    if endpoint is None or (endpoint.profile_id, endpoint.provider_id) != ('duckdb-native', 'org.cdeadmin.duckdb'):
        raise ValueError('Select a native DuckDB registration')
    if not isinstance(target, str) or not target:
        raise ValueError('Select the original registered DuckDB target')
    service.endpoint_service._owned_database_target(endpoint, target)
    context = service.endpoint_service._context(endpoint, ())
    permissions = service.endpoint_service.provider_registry.admitted_permissions(context)
    if 'administer' not in permissions:
        raise ValueError('Native retained DuckDB DDL permission is unavailable')
    store = getattr(service.operation_bus, 'store', None)
    if not isinstance(store, JsonOperationStore):
        raise ValueError('Original-session DuckDB DDL requires durable application storage')
    path = str(store.path) + '.duckdb-retained-schema'
    archives = service.__dict__.setdefault('_duckdb_retained_archives', {})
    archive = archives.setdefault(path, DuckDBRetainedApplications(path))
    owner = service._principal_id(server)
    return archive, owner, digest([owner, endpoint.id, target, 'org.cdeadmin.duckdb', 'duckdb-native'])


def serve(service, server, action, data):
    request = data.get('request')
    if not isinstance(request, dict):
        raise ValueError('Select a retained DuckDB DDL request')
    try:
        archive, owner, binding = scope(service, server, data.get('database_target_id'))
        operation = request.get('operation')
        if action == 'duckdb_retained_schema_receipts':
            if operation == 'list' and not set(request) - {'operation', 'offset', 'limit'}:
                return archive.list(owner, binding, offset=request.get('offset', 0), limit=request.get('limit', 25))
            if operation == 'receipt' and set(request) == {'operation', 'review_id'}:
                value = archive.get(request['review_id'], owner, binding)
                return {**value, 'archived_read_only': True, 'native_sql_requested': False}
            if operation == 'remove' and set(request) == {'operation', 'review_id', 'confirmed'}:
                return archive.remove(request['review_id'], owner, binding, confirmed=request['confirmed'])
            raise ValueError('Select a bounded retained DuckDB receipt action')

        fields = {
            'observe': {'operation'},
            'preview': {'operation', 'baseline', 'desired', 'deletions', 'alterations', 'rebuilds'},
            'review': {'operation', 'baseline', 'desired', 'deletions', 'alterations', 'rebuilds', 'execution_sha256'},
            'apply': {'operation', 'review_id', 'review_digest', 'confirmed'},
        }
        if operation not in fields or set(request) - fields[operation]:
            raise ValueError('Invalid original-session DuckDB DDL request')
        if operation == 'apply':
            if set(request) != fields['apply'] or request.get('confirmed') is not True:
                raise ValueError('Confirm the exact original-session DuckDB DDL review')
            value = archive.get(request['review_id'], owner, binding)
            if request['review_digest'] != value['review_digest']:
                raise ValueError('Retained DuckDB review fingerprint does not match')
            if value['state'] != 'reviewed':
                return {**value, 'replay_refused': True}

        context, _endpoint, _root = service.endpoint_service.workspace(
            server, database_target_id=data.get('database_target_id')
        )
        return service.studio_service.duckdb_retained_schema_action(
            context,
            data.get('session_id'),
            request,
            archive,
            owner,
            binding,
            data.get('database_target_id'),
        )
    except SchemaApplyError as err:
        raise ValueError(str(err)) from None
