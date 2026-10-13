"""Owner-bound DuckDB catalog exchange for the shared workspace."""

from ..providers.duckdb.provider import DuckDBPilotProvider
from .firebird_catalog_export import build_export
from .firebird_catalog_import import compare_catalogs, read_catalog


def catalog(service, server, request, *, compare=False):
    if not isinstance(request, dict) or set(request) - {
            'database_target_id', 'include_system', 'resource_id', 'source'}:
        raise ValueError('Invalid DuckDB catalog request')
    target = request.get('database_target_id')
    if not isinstance(target, str) or not target:
        raise ValueError('Select a registered DuckDB database file')
    include_system = request.get('include_system', False)
    if type(include_system) is not bool:
        raise ValueError('Invalid system-object selection')
    resource_id = request.get('resource_id')
    if resource_id is not None and (not isinstance(resource_id, str) or not resource_id):
        raise ValueError('Invalid native object selection')
    document = read_catalog(request.get('source'), engine='duckdb') if compare else None
    context, endpoint, _root = service.endpoint_service.workspace(
        server, database_target_id=target)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, DuckDBPilotProvider) or context.profile_id != 'duckdb-native':
        raise ValueError('Select a native DuckDB endpoint')
    if document and (document['provenance']['endpoint_id'] != context.endpoint_id or
                     document['provenance']['database_target_id'] != target):
        raise ValueError('Document belongs to another endpoint or database')
    captured = provider.capture_catalog(endpoint['route'], include_system=include_system)
    result = build_export(captured['resources'], endpoint_id=context.endpoint_id,
        target_id=target, generation=captured['generation'], resource_id=resource_id,
        include_system=include_system, refreshed=True, engine='duckdb', native_model=compare)
    if compare:
        return compare_catalogs(document, result)
    result['generation'] = captured['generation']
    result['objects'] = [{'resource_id': item['resource_id'], 'name': item['display_name'],
                          'kind': item['resource_kind'], 'path': item['display_path']}
                         for item in captured['resources']]
    return result


def data(service, server, request):
    if not isinstance(request, dict) or set(request) != {
            'database_target_id', 'resource_id', 'mode', 'row_limit'}:
        raise ValueError('Invalid DuckDB data capture request')
    target = request['database_target_id']
    if not isinstance(target, str) or not target:
        raise ValueError('Select a registered DuckDB database file')
    context, endpoint, _root = service.endpoint_service.workspace(
        server, database_target_id=target)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, DuckDBPilotProvider) or context.profile_id != 'duckdb-native':
        raise ValueError('Select a native DuckDB endpoint')
    return provider.capture_data(endpoint['route'], request['resource_id'],
        endpoint_id=context.endpoint_id, target_id=target,
        mode=request['mode'], row_limit=request['row_limit'])


def test_data(service, server, request):
    from .firebird_catalog_export import build_export
    from .duckdb_test_data import generate, template
    if not isinstance(request, dict) or set(request) - {'database_target_id', 'recipe'}:
        raise ValueError('Invalid DuckDB test-data request')
    target = request.get('database_target_id')
    if not isinstance(target, str) or not target:
        raise ValueError('Select a registered DuckDB database file')
    context, endpoint, _root = service.endpoint_service.workspace(
        server, database_target_id=target)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, DuckDBPilotProvider) or context.profile_id != 'duckdb-native':
        raise ValueError('Select a native DuckDB endpoint')
    captured = provider.capture_catalog(endpoint['route'], include_system=False)
    model = build_export(captured['resources'], endpoint_id=str(context.endpoint_id),
        target_id=target, generation=captured['generation'], include_system=False,
        refreshed=True, engine='duckdb', native_model=True)
    return generate(model, request['recipe']) if 'recipe' in request else template(model)


def copy_plan(service, server, request):
    from .firebird_catalog_export import build_export
    from .duckdb_copy import plan
    if not isinstance(request, dict) or set(request) != {
            'database_target_id', 'resource_id', 'direction', 'format', 'path'}:
        raise ValueError('Invalid DuckDB COPY request')
    target = request['database_target_id']
    if not isinstance(target, str) or not target:
        raise ValueError('Select a registered DuckDB database file')
    context, endpoint, _root = service.endpoint_service.workspace(server, database_target_id=target)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, DuckDBPilotProvider) or context.profile_id != 'duckdb-native':
        raise ValueError('Select a native DuckDB endpoint')
    if request['direction'] == 'from':
        if endpoint['route'].get('read_only') is True:
            raise ValueError('Read-only DuckDB file cannot import COPY data')
        provider._require('data_write', 'resource')
    captured = provider.capture_catalog(endpoint['route'], include_system=False)
    model = build_export(captured['resources'], endpoint_id=str(context.endpoint_id),
        target_id=target, generation=captured['generation'], include_system=False,
        refreshed=True, engine='duckdb', native_model=True)
    return plan(model, {key: value for key, value in request.items() if key != 'database_target_id'},
        endpoint['route'].get('filesystem_root'))
