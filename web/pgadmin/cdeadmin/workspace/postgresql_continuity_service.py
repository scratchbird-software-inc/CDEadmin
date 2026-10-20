"""Owner-bound continuity admission, including offline artifact inspection."""
from pathlib import Path
import os

from ..core import EndpointContext
from ..operations.store import JsonOperationStore
from ..providers.postgresql.continuity import ContinuityError, binary_paths
from ..providers.postgresql.continuity_transport import ContinuityTransport, capture
from ..providers.postgresql.provider import PROFILE_ID, PROFILE_VERSION, PROVIDER_ID, PROVIDER_VERSION
from .postgresql_continuity_jobs import PostgreSQLContinuityJobs, fingerprint,artifact_tablespaces
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
    replication_access = request.get('replication_access')
    if 'replication_access' in request:
        if operation not in {'review', 'start'} or not isinstance(replication_access, dict):
            raise ContinuityError('Replication-only credentials apply to review/start of native physical backup or WAL capture')
        if 'secret_read' not in permissions:
            raise ContinuityError('Native replication credential permission is unavailable')
        request = {key: value for key, value in request.items() if key != 'replication_access'}
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
    if operation=='slot_databases':
        if request:raise ContinuityError('Invalid native slot database selection')
        return service.endpoint_service.database_catalog(server)
    if operation in {'logical_stream_preview','logical_stream_reconcile'}:
        from . import postgresql_logical_stream as stream
        record=jobs.load(request.get('job_id'),owner,endpoint)
        try:
            if operation=='logical_stream_reconcile':
                if set(request)!={'job_id'}:raise ContinuityError('Select one owned native logical stream')
                return stream.reconcile(jobs,record)
            return stream.preview(jobs,record,request)
        except OSError:raise ContinuityError('The owned native logical stream bytes are unavailable') from None
    if operation in {'change_preview','change_reconcile'}:
        from . import postgresql_slot_changes as changes
        if operation=='change_reconcile' and set(request)!={'job_id'}:
            raise ContinuityError('Select one owned logical change artifact')
        record=jobs.load(request.get('job_id'),owner,endpoint)
        return changes.preview(jobs,record,request) if operation=='change_preview' else changes.reconcile(jobs,record)
    runtime_limit=current_app.config.get('CDEADMIN_POSTGRESQL_CONTINUITY_MAX_RUNTIME_SECONDS')
    paths=paths_for_app(current_app)
    configuration=fingerprint({'registration':PostgreSQLMonitoringHost._configuration(server),
                               'runtime_limit':runtime_limit,'paths':paths,'wal_archive_root':str(jobs.archive_root)})
    transport=None
    try:
        from . import postgresql_continuity_slot_sql as sql_slots
        if operation=='slots':
            from .postgresql_continuity_slots import catalog
            context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
            provider=service.endpoint_service.provider_registry.resolve(context).instance
            source,transport=capture(provider,payload['route'],server=server)
            return catalog(source,transport,request)
        if operation=='review':
            native_operation=request.get('operation')
            if replication_access is not None:
                if native_operation not in {'wal_capture','full_backup','incremental_backup'}:
                    raise ContinuityError('Select a native physical backup or WAL capture for replication-only admission')
                from ..providers.postgresql.replication_admission import registered
                source, transport = registered(server, replication_access)
                return jobs.review(request,owner,endpoint,source,configuration,paths,runtime_limit=runtime_limit)
            if native_operation in sql_slots.OPERATIONS or native_operation=='logical_stream_capture':
                from ..providers.postgresql.connection_target import database_oid
                target=request.get('database_target_id')
                if not isinstance(target,str) or not 1<=len(target)<=256:
                    raise ContinuityError('Select an explicit PostgreSQL database target')
                if native_operation=='logical_stream_capture':
                    from .postgresql_logical_stream import options
                    selected=options(request.get('options',{}))
                else:selected=sql_slots.options(native_operation,request.get('options',{}))
                try:selected_oid=database_oid(target)
                except ValueError as error:raise ContinuityError(str(error)) from None
                context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
                provider=service.endpoint_service.provider_registry.resolve(context).instance
                source,transport=sql_slots.capture(provider,payload['route'],server,selected,selected_oid)
                if native_operation=='logical_stream_capture':
                    from .postgresql_logical_stream import bind_source
                    source=bind_source(source)
                return jobs.review(request,owner,endpoint,source,configuration,paths,runtime_limit=runtime_limit)
            slot=None
            if native_operation in {'wal_slot_create','wal_slot_drop'}:
                from .postgresql_continuity_slots import options
                slot=options(native_operation,request.get('options',{}))['slot']
            if native_operation in {'verify','combine','recovery_drill'}:
                ids=request.get('chain') if native_operation=='combine' else [request.get('base_job_id')]
                if not isinstance(ids,list) or not ids:raise ContinuityError('Select backup artifacts')
                previous=jobs.load(ids[-1],owner,endpoint)
                source=dict(previous['source'])
                spaces=artifact_tablespaces(previous)
                if spaces is not None and source.get('tablespace_catalog_observed') is False:
                    source.update(tablespaces=spaces,tablespace_artifact_observed=True)
            else:
                context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
                provider=service.endpoint_service.provider_registry.resolve(context).instance
                source,transport=capture(provider,payload['route'],server=server,wal_details=native_operation=='wal_capture')
                if native_operation in {'wal_slot_create','wal_slot_drop'}:
                    from .postgresql_continuity_slots import enrich
                    source=enrich(source,transport,slot)
            return jobs.review(request,owner,endpoint,source,configuration,paths,runtime_limit=runtime_limit)
        if operation=='start':
            reviewed=jobs.load(request.get('job_id'),owner,endpoint)
            source=reviewed['source']
            replication_only = source.get('admission_interface') == 'physical-replication'
            if replication_access is not None and (not replication_only or reviewed['operation'] not in {'wal_capture','full_backup','incremental_backup'}):
                raise ContinuityError('Replication credentials do not match the reviewed native admission interface')
            if reviewed['state']=='reviewed' and replication_only and reviewed['operation'] in {'wal_capture','full_backup','incremental_backup'}:
                if replication_access is None:
                    raise ContinuityError('Reauthenticate the reviewed replication-only backup or WAL capture before dispatch')
                from ..providers.postgresql.replication_admission import registered
                source, transport = registered(server, replication_access)
            elif reviewed['state']=='reviewed' and (reviewed['operation'] in sql_slots.OPERATIONS or reviewed['operation']=='logical_stream_capture'):
                from ..providers.postgresql.connection_target import database_oid
                context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
                provider=service.endpoint_service.provider_registry.resolve(context).instance
                source,transport=sql_slots.capture(provider,payload['route'],server,reviewed['options'],database_oid(reviewed['database_target_id']))
                if reviewed['operation']=='logical_stream_capture':
                    from .postgresql_logical_stream import bind_source
                    source=bind_source(source)
            elif reviewed['state']=='reviewed' and reviewed['operation'] in {'full_backup','incremental_backup','wal_capture','wal_slot_create','wal_slot_drop'}:
                context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
                provider=service.endpoint_service.provider_registry.resolve(context).instance
                source,transport=capture(provider,payload['route'],server=server,wal_details=reviewed['operation']=='wal_capture')
                if reviewed['operation'] in {'wal_slot_create','wal_slot_drop'}:
                    from .postgresql_continuity_slots import enrich
                    source=enrich(source,transport,reviewed['options']['slot'])
            else:transport=ContinuityTransport({})
            admitted=transport;transport=None
            return jobs.start(request,owner,endpoint,source,configuration,admitted)
        raise ContinuityError('Native continuity action is unavailable')
    finally:
        if transport is not None:transport.close()


def change_download(service,server,request):
    """Authenticated delivery is available without a live database connection."""
    import os
    from flask import send_file
    from . import postgresql_slot_changes as changes
    if not isinstance(request,dict) or set(request)!={'job_id'}:
        raise ContinuityError('Select one native logical change artifact')
    action(service,server,'status',request)  # Native registration, permission and owner/endpoint admission.
    jobs=service.postgresql_continuity_jobs
    record=jobs.load(request['job_id'],service._principal_id(server),server.endpoint_profile.id)
    owned=changes.payload(jobs,record)
    try:stream=owned.__enter__()
    except OSError:raise ContinuityError('Captured native change bytes are unavailable') from None
    try:
        artifact=record['change_artifact'];partial=artifact['state']=='partial'
        response=send_file(stream,mimetype='application/x-ndjson',as_attachment=True,
            download_name='postgresql-logical-'+record['job_id']+'.jsonl'+('.partial' if partial else ''),conditional=False,max_age=0)
        response.content_length=os.fstat(stream.fileno()).st_size
        response.headers.update({'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff',
            'X-Content-SHA256':artifact['sha256'],'X-Export-Completeness':'incomplete' if partial else 'verified',
            'X-Native-SQL-Acknowledged':'yes' if record.get('native_sql_acknowledged') is True else 'unconfirmed'})
        response.direct_passthrough=False
        response.call_on_close(lambda:owned.__exit__(None,None,None))
        return response
    except BaseException:owned.__exit__(None,None,None);raise


def logical_stream_download(service,server,request,*,database_target_id=None):
    from flask import send_file
    from . import postgresql_logical_stream as stream
    if not isinstance(request,dict) or set(request)!={'job_id'}:raise ContinuityError('Select one owned native logical output file')
    action(service,server,'status',request)
    jobs=service.postgresql_continuity_jobs;record=jobs.load(request['job_id'],service._principal_id(server),server.endpoint_profile.id)
    if database_target_id is not None and record.get('database_target_id')!=database_target_id:
        raise ContinuityError('Native logical output belongs to another database workspace')
    opened=stream.payload(jobs,record);source=opened.__enter__();artifact=record['logical_stream_artifact']
    try:
        response=send_file(source,mimetype='application/octet-stream',as_attachment=True,
                           download_name='postgresql-logical-stream-'+record['job_id']+'.native',conditional=False,max_age=0)
        response.content_length=int(artifact['bytes']);response.direct_passthrough=False
        response.headers.update({'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff',
            'X-Content-SHA256':artifact['sha256'],'X-Native-Receiver-Returned':'yes' if artifact['native_receiver_returned'] else 'unconfirmed',
            'X-Transaction-Completeness':'not-inferred'})
        response.call_on_close(lambda:opened.__exit__(None,None,None));return response
    except BaseException:opened.__exit__(None,None,None);raise
