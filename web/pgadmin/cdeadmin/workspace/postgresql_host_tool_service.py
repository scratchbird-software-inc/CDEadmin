"""Native host admission: registered endpoint plus independent local grants."""
from pathlib import Path
from ..operations.store import JsonOperationStore
from ..providers.postgresql.host_tools import HostTools, OPERATIONS, options, grants, digest
from ..providers.postgresql.continuity import ContinuityError
from .postgresql_continuity_service import artifact_context, paths_for_app
from .postgresql_monitoring_host import PostgreSQLMonitoringHost
from .postgresql_host_tool_jobs import PostgreSQLHostToolJobs, HostToolTransport


def descriptors():
    from ..ui_descriptors import UIDescriptorService
    return [row for row in UIDescriptorService().engine('postgresql')['operations']
            if row['operation_id'] in OPERATIONS]


def action(service, server, request, *, host_authorized=False):
    from flask import current_app
    if host_authorized is not True:
        raise ContinuityError('Application-host Administrator authority is required')
    if not isinstance(request, dict) or not PostgreSQLMonitoringHost._native_registration(server):
        raise ContinuityError('Select a native PostgreSQL registration and typed host request')
    permissions = service.endpoint_service.provider_registry.admitted_permissions(artifact_context(server))
    if 'backup_admin' not in permissions:
        raise ContinuityError('Native host administration permission is unavailable')
    stage = request.get('stage')
    allowed = {'describe': {'stage'}, 'catalog': {'stage'}, 'list': {'stage', 'offset', 'limit'},
               'review': {'stage', 'operation_id', 'draft'},
               'start': {'stage', 'job_id', 'review_digest', 'confirmed'},
               'status': {'stage', 'job_id'}, 'cancel': {'stage', 'job_id'}, 'reconcile': {'stage', 'job_id'}}
    if not isinstance(stage, str) or stage not in allowed or set(request) - allowed[stage]:
        raise ContinuityError('Select one typed native host stage')
    if stage == 'describe':
        return {'format': 'scratchrobin.postgresql.host-tool-operations@1', 'workspace_action': 'postgresql_host_tools',
                'operations': descriptors(), 'stages': list(allowed), 'automatic_retry': False,
                'permissions': ['backup_admin', 'application_host_administrator'],
                'execution_host': 'application-host', 'native_sql_session_required': False}
    owner, endpoint = service._principal_id(server), server.endpoint_profile.id
    manifest = current_app.config.get('CDEADMIN_POSTGRESQL_HOST_TOOL_MANIFEST')
    store = getattr(service.operation_bus, 'store', None)
    if not isinstance(store, JsonOperationStore):
        raise ContinuityError('Native host utility jobs require durable application storage')
    root = current_app.config.get('CDEADMIN_POSTGRESQL_HOST_TOOL_ROOT') or str(store.path.parent / 'postgresql-host-tools')
    with service._semantic_lock:
        jobs = getattr(service, 'postgresql_host_tool_jobs', None)
        if jobs is None:
            jobs = service.postgresql_host_tool_jobs = PostgreSQLHostToolJobs(str(store.path) + '.postgresql-host-tools', root)
            import atexit
            atexit.register(jobs.close)
    if stage == 'list':
        return jobs.list(owner, endpoint, request.get('offset', 0), request.get('limit', 25))
    if stage in {'status', 'cancel', 'reconcile'}:
        return {'status': jobs.get, 'cancel': jobs.cancel, 'reconcile': jobs.reconcile}[stage](request.get('job_id'), owner, endpoint)
    directory = current_app.config.get('CDEADMIN_POSTGRESQL_HOST_BINARY_PATH')
    if not directory:
        directory = str(Path(paths_for_app(current_app)['pg_controldata']).parent)
    paths = {name: str(Path(directory) / (name + ('.exe' if __import__('os').name == 'nt' else '')))
             for name in OPERATIONS.values()}
    tools = HostTools(paths)
    workspace = jobs.prepare_scope(owner, endpoint)
    if stage == 'catalog':
        grant, grant_sha = grants(manifest, endpoint)
        capabilities = {}
        for name in OPERATIONS.values():
            try: capabilities[name] = {'available': True, **tools.identify(name, workspace)}
            except ContinuityError as error: capabilities[name] = {'available': False, 'reason': str(error)}
        return {'clusters': [{'id': row['id']} for row in grant.get('clusters', [])],
                'summary_files': [{'id': row['id']} for row in grant.get('summary_files', [])],
                'benchmark_roots': [{'id': row['id']} for row in grant.get('benchmark_roots', [])],
                'execution_host': __import__('socket').gethostname(), 'grant_sha256': grant_sha,
                'tools': capabilities, 'native_server_connection_observed': False}
    if stage == 'review':
        operation = request.get('operation_id')
        selected = options(operation, request.get('draft'))
    else:
        record = jobs.load(request.get('job_id'), owner, endpoint)
        if record['state'] != 'reviewed':
            return jobs.start({key: value for key, value in request.items() if key != 'stage'}, owner, endpoint, {}, None)
        operation, selected = record['options']['operation'], record['options']['draft']
    config = {'manifest': manifest, 'paths': paths, 'root': str(jobs.root)}
    def refresh():
        current_grant, current_sha = grants(manifest, endpoint)
        program = tools.identify(OPERATIONS[operation], workspace)
        source = tools.observe(operation, selected, current_grant, workspace)
        cluster = source.get('cluster_path')
        if cluster and jobs.root.is_relative_to(Path(cluster)):
            raise ContinuityError('Native host job storage cannot be inside the selected database cluster')
        return source, program, digest({**config, 'grant_sha256': current_sha})
    source, program, configuration = refresh()
    if stage == 'review':
        return jobs.review(owner, endpoint, {'operation': operation, 'draft': selected},
                           {'identity': source, 'state': {}}, configuration, program)
    return jobs.start({key: value for key, value in request.items() if key != 'stage'}, owner, endpoint,
                      {'source': source, 'program': program, 'configuration': configuration},
                      HostToolTransport(jobs, tools, refresh))
