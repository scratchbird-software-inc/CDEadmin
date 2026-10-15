"""Documentary DDN capture for the files registered on one DuckDB endpoint."""

import json
import uuid

from .firebird_catalog_export import build_export
from ..providers.duckdb.provider import DuckDBPilotProvider


MAX_REGISTERED_FILES = 1000
MAX_SELECTED_FILES = 32
MAX_BUNDLE_BYTES = 32 * 1024 * 1024


def _inventory(service, server):
    context, _endpoint, _root = service.endpoint_service.workspace(
        server, database_target_id=None)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, DuckDBPilotProvider) or context.profile_id != 'duckdb-native':
        raise ValueError('Select a native DuckDB endpoint')
    provider._require('data_read', 'resource')
    registered = service.endpoint_service.database_catalog(server)
    if (registered.get('endpoint_id') != context.endpoint_id or
            registered.get('multiple') is not True or
            not isinstance(registered.get('targets'), list) or
            len(registered['targets']) > MAX_REGISTERED_FILES):
        raise ValueError('DuckDB registered-file inventory is unavailable or exceeds 1,000 files')
    targets = []
    for item in registered['targets']:
        identity, name = item.get('target_id'), item.get('display_name')
        if not isinstance(identity, str) or not identity or not isinstance(name, str):
            raise ValueError('DuckDB registered-file inventory contains an invalid target')
        targets.append({'target_id': identity, 'display_name': name,
                        'active': item.get('active') is True})
    if len({item['target_id'] for item in targets}) != len(targets):
        raise ValueError('DuckDB registered-file inventory has duplicate identities')
    return context, sorted(targets, key=lambda item: (item['display_name'], item['target_id']))


def serve(service, server, request):
    if not isinstance(request, dict) or set(request) - {
            'database_target_ids', 'include_system'}:
        raise ValueError('Invalid DuckDB endpoint catalog request')
    context, targets = _inventory(service, server)
    if 'database_target_ids' not in request:
        if request:
            raise ValueError('File selection is required for DuckDB endpoint capture')
        return {'format': 'scratchrobin.duckdb.registered-files@1',
                'endpoint_id': context.endpoint_id, 'files': targets,
                'capture_limit': MAX_SELECTED_FILES}
    identities = request['database_target_ids']
    include_system = request.get('include_system', False)
    if (not isinstance(identities, list) or
            not 1 <= len(identities) <= MAX_SELECTED_FILES or
            any(not isinstance(item, str) or not item for item in identities) or
            len(set(identities)) != len(identities) or type(include_system) is not bool):
        raise ValueError('Select one to thirty-two distinct registered DuckDB files')
    known = {item['target_id']: item for item in targets}
    if any(identity not in known for identity in identities):
        raise ValueError('File selection includes an unregistered DuckDB target')

    resources = [{'resource_id': 'duckdb:registered-endpoint:' + str(context.endpoint_id),
        'resource_kind': 'server', 'display_name': 'Registered DuckDB files',
        'display_path': [str(context.endpoint_id)],
        'native': {'system_object': False, 'catalog_warnings': [
            'This is a registration inventory, not a native DuckDB server.']}}]
    for item in targets:
        resources.append({'resource_id': 'duckdb:registered-file:' + item['target_id'],
            'resource_kind': 'database', 'display_name': item['display_name'],
            'display_path': [str(context.endpoint_id), item['target_id']],
            'native': {'system_object': False, 'target_id': item['target_id'],
                'registration_only': True}})
    overview = build_export(resources, endpoint_id=str(context.endpoint_id),
        target_id='duckdb-registered-endpoint:' + str(context.endpoint_id),
        generation=str(uuid.uuid4()), include_system=include_system, engine='duckdb')
    documents, size = [], len(json.dumps(overview, ensure_ascii=False).encode('utf8'))
    for identity in identities:
        selected = known[identity]
        try:
            file_context, endpoint, _root = service.endpoint_service.workspace(
                server, database_target_id=identity)
            provider = service.endpoint_service.provider_registry.resolve(
                file_context).instance
            if (not isinstance(provider, DuckDBPilotProvider) or
                    file_context.profile_id != 'duckdb-native' or
                    file_context.endpoint_id != context.endpoint_id):
                raise ValueError('Registered DuckDB file belongs to another endpoint')
            captured = provider.capture_catalog(endpoint['route'],
                include_system=include_system, include_macro_source=True)
            document = build_export(captured['resources'],
                endpoint_id=str(context.endpoint_id), target_id=identity,
                generation=captured['generation'], include_system=include_system,
                engine='duckdb')
        except Exception as error:
            documents.append({'database_target_id': identity,
                'display_name': selected['display_name'], 'available': False,
                'error_type': type(error).__name__,
                'reason': 'Native file capture failed; no substitute file was used'})
            continue
        size += len(json.dumps(document, ensure_ascii=False).encode('utf8'))
        if size > MAX_BUNDLE_BYTES:
            raise ValueError('DuckDB endpoint DDN bundle exceeds 32 MiB; select fewer files')
        documents.append({'database_target_id': identity,
            'display_name': selected['display_name'], 'available': True,
            'document': document})
    bundle = {'format': 'scratchrobin.duckdb.registered-files-ddn@1',
        'endpoint_id': context.endpoint_id, 'server': {'document': overview},
        'files': documents, 'all_selected_captured': all(
            item['available'] for item in documents),
        'consistency': 'independent-file-observations; not an atomic snapshot',
        'complete': False}
    if len(json.dumps(bundle, ensure_ascii=False).encode('utf8')) > MAX_BUNDLE_BYTES:
        raise ValueError('DuckDB endpoint DDN bundle exceeds 32 MiB; select fewer files')
    return bundle
