"""Owner-bound continuity admission, including offline artifact inspection."""
from pathlib import Path
import os

from ..core import EndpointContext
from ..operations.store import JsonOperationStore
from ..providers.postgresql.continuity import ContinuityError, binary_paths
from ..providers.postgresql.continuity_transport import ContinuityTransport, capture
from ..providers.postgresql.provider import PROFILE_ID, PROFILE_VERSION, PROVIDER_ID, PROVIDER_VERSION
from .postgresql_continuity_jobs import PostgreSQLContinuityJobs, fingerprint
from .postgresql_monitoring_host import PostgreSQLMonitoringHost


def artifact_context(server):
    endpoint=server.endpoint_profile
    # This context authorizes local artifact tools. It makes no assertion about
    # a live server's version, availability or authentication.
    return EndpointContext(endpoint_id=endpoint.id,mode='legacy_native',experience_family='postgresql',
        provider_id=PROVIDER_ID,provider_version=PROVIDER_VERSION,profile_id=PROFILE_ID,profile_version=PROFILE_VERSION,
        target_adapter_id='legacy-pgadmin-server',target_adapter_version=PROVIDER_VERSION,
        **{name:getattr(endpoint,name) for name in ('pool_namespace','session_namespace','cache_namespace','diagnostic_namespace')})


def paths_for_app(app):
    configured=app.config.get('CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH')
    if not configured:
        configured=(app.config.get('FIXED_BINARY_PATHS') or {}).get('pg-18') or (app.config.get('DEFAULT_BINARY_PATHS') or {}).get('pg-18')
    if not configured:
        # Prefer an actual native installation to distribution wrapper scripts.
        candidates=[Path('/usr/lib/postgresql/18/bin'),Path('/opt/homebrew/opt/postgresql@18/bin'),Path('/usr/local/opt/postgresql@18/bin')]
        if os.name=='nt':candidates.insert(0,Path(os.environ.get('ProgramFiles','C:/Program Files'))/'PostgreSQL/18/bin')
        configured=next((str(path) for path in candidates if (path/('pg_basebackup.exe' if os.name=='nt' else 'pg_basebackup')).is_file()),None)
    return binary_paths(configured)


def action(service, server, operation, request):
    from flask import current_app
    if not isinstance(request,dict):raise ContinuityError('A native continuity request is required')
    if not PostgreSQLMonitoringHost._native_registration(server):raise ContinuityError('Select a native PostgreSQL registration')
    owner=service._principal_id(server);endpoint=server.endpoint_profile.id
    permissions=service.endpoint_service.provider_registry.admitted_permissions(artifact_context(server))
    if 'backup_admin' not in permissions:raise ContinuityError('Native backup administration permission is unavailable')
    store=getattr(service.operation_bus,'store',None)
    if not isinstance(store,JsonOperationStore):raise ContinuityError('Continuity jobs require durable application storage')
    with service._semantic_lock:
        jobs=getattr(service,'postgresql_continuity_jobs',None)
        if jobs is None:
            root=current_app.config.get('CDEADMIN_POSTGRESQL_CONTINUITY_ROOT') or str(store.path.parent/'postgresql-native-backups')
            jobs=service.postgresql_continuity_jobs=PostgreSQLContinuityJobs(str(store.path)+'.postgresql-continuity',root,
                current_app.config.get('CDEADMIN_POSTGRESQL_WAL_ARCHIVE_ROOT') or None)
            import atexit
            atexit.register(jobs.close)
    if operation=='archives':
        if request:raise ContinuityError('Invalid native WAL archive selection')
        # No cross-owner or cross-endpoint directory traversal is exposed.
        from ..providers.postgresql.continuity_wal import ARCHIVE_NAME
        root=jobs.archive_directory(owner,endpoint)
        return {'archives':sorted(entry.name for entry in root.iterdir() if entry.is_dir() and not entry.is_symlink() and ARCHIVE_NAME.fullmatch(entry.name)) if root.is_dir() else [],
                'execution_host':'application-host','owner_endpoint_directory':str(root)}
    if operation=='list':
        if set(request)-{'offset','limit'}:raise ContinuityError('Invalid backup receipt page')
        return jobs.list(owner,endpoint,**request)
    if operation=='reconcile_writer':return jobs.reconcile_writer(request,owner,endpoint)
    if operation in {'status','cancel'}:
        if set(request)!={'job_id'}:raise ContinuityError('Select one native continuity job')
        return (jobs.get if operation=='status' else jobs.cancel)(request['job_id'],owner,endpoint)
    runtime_limit=current_app.config.get('CDEADMIN_POSTGRESQL_CONTINUITY_MAX_RUNTIME_SECONDS')
    paths=paths_for_app(current_app)
    configuration=fingerprint({'registration':PostgreSQLMonitoringHost._configuration(server),
                               'runtime_limit':runtime_limit,'paths':paths,'wal_archive_root':str(jobs.archive_root)})
    transport=None
    try:
        if operation=='review':
            native_operation=request.get('operation')
            if native_operation in {'verify','combine','recovery_drill'}:
                ids=request.get('chain') if native_operation=='combine' else [request.get('base_job_id')]
                if not isinstance(ids,list) or not ids:raise ContinuityError('Select backup artifacts')
                source=jobs.load(ids[-1],owner,endpoint)['source']
            else:
                context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
                provider=service.endpoint_service.provider_registry.resolve(context).instance
                source,transport=capture(provider,payload['route'],server=server)
            return jobs.review(request,owner,endpoint,source,configuration,paths,runtime_limit=runtime_limit)
        if operation=='start':
            reviewed=jobs.load(request.get('job_id'),owner,endpoint)
            source=reviewed['source']
            if reviewed['state']=='reviewed' and reviewed['operation'] in {'full_backup','incremental_backup'}:
                context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
                provider=service.endpoint_service.provider_registry.resolve(context).instance
                source,transport=capture(provider,payload['route'],server=server)
            else:transport=ContinuityTransport({})
            admitted=transport;transport=None
            return jobs.start(request,owner,endpoint,source,configuration,admitted)
        raise ContinuityError('Native continuity action is unavailable')
    finally:
        if transport is not None:transport.close()
