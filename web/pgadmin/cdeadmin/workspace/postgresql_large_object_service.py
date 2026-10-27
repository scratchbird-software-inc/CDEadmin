"""Native admission and authenticated delivery of PostgreSQL client files."""
from ..operations.store import JsonOperationStore
from ..providers.postgresql import large_object_files as native
from ..providers.postgresql.provider import PostgreSQLProvider
from .postgresql_continuity_service import artifact_context
from .postgresql_monitoring_host import PostgreSQLMonitoringHost
from .postgresql_large_object_jobs import PostgreSQLLargeObjectJobs,digest,file_identity


def manager(service,server,target):
    from flask import current_app
    if not PostgreSQLMonitoringHost._native_registration(server):raise native.LargeObjectFileError('Select a native PostgreSQL registration')
    if not isinstance(target,str) or not target or len(target)>256:raise native.LargeObjectFileError('Select an explicit PostgreSQL database target')
    permissions=service.endpoint_service.provider_registry.admitted_permissions(artifact_context(server))
    if 'data_read' not in permissions:raise native.LargeObjectFileError('Native data read permission is unavailable')
    store=getattr(service.operation_bus,'store',None)
    if not isinstance(store,JsonOperationStore):raise native.LargeObjectFileError('File transfers require durable application storage')
    with service._semantic_lock:
        jobs=getattr(service,'postgresql_large_object_jobs',None)
        if jobs is None:
            root=current_app.config.get('CDEADMIN_POSTGRESQL_LARGE_OBJECT_ROOT') or str(store.path.parent/'postgresql-large-object-files')
            jobs=service.postgresql_large_object_jobs=PostgreSQLLargeObjectJobs(str(store.path)+'.postgresql-lo-files',root)
            import atexit
            atexit.register(jobs.close)
    return jobs,service._principal_id(server),server.endpoint_profile.id,permissions


def action(service,server,operation,request):
    from psycopg import Error as NativeError
    if not isinstance(request,dict):raise native.LargeObjectFileError('Select a native file transfer request')
    selected_request=dict(request);target=selected_request.pop('database_target_id',None)
    jobs,owner,endpoint,permissions=manager(service,server,target)
    if operation=='list':
        if set(selected_request)-{'offset','limit'}:raise native.LargeObjectFileError('Invalid file receipt page')
        return jobs.list(owner,endpoint,target,**selected_request)
    if operation in {'status','cancel'}:
        if set(selected_request)!={'job_id'}:raise native.LargeObjectFileError('Select one file transfer')
        return (jobs.get if operation=='status' else jobs.cancel)(selected_request['job_id'],owner,endpoint,target)
    if operation=='remove_artifact':
        if set(selected_request)!={'job_id','confirmation'}:raise native.LargeObjectFileError('Select and confirm one application file artifact')
        return jobs.remove_artifact(selected_request['job_id'],owner,endpoint,target,selected_request['confirmation'])
    if operation=='upload':
        if 'administer' not in permissions:raise native.LargeObjectFileError('Native data administration permission is unavailable')
        job_id=selected_request.pop('job_id',None)
        return jobs.upload(job_id,owner,endpoint,target,selected_request)
    if operation=='start':
        reviewed=jobs.load(selected_request.get('job_id'),owner,endpoint,target)
        if reviewed['state']!='reviewed':return jobs.start(selected_request,owner,endpoint,target,reviewed['source'],reviewed['configuration'],None)
        selected=reviewed['options']
    elif operation=='create':
        if set(selected_request)!={'options'}:raise native.LargeObjectFileError('Invalid file transfer creation')
        selected=native.options(selected_request['options'])
    elif operation=='seal':
        if set(selected_request)!={'job_id'}:raise native.LargeObjectFileError('Select one uploaded file')
        reviewed=jobs.load(selected_request['job_id'],owner,endpoint,target);selected=reviewed['options']
        if reviewed['state']!='uploading':return jobs.get(reviewed['job_id'],owner,endpoint,target)
    elif operation=='reconcile':
        if set(selected_request)!={'job_id'}:raise native.LargeObjectFileError('Select one unknown file transfer')
        reviewed=jobs.load(selected_request['job_id'],owner,endpoint,target);selected=reviewed['options']
        if selected['operation']=='export':return jobs.reconcile(reviewed)
    else:raise native.LargeObjectFileError('Native file transfer action is unavailable')
    if selected['operation']=='import' and 'administer' not in permissions:
        raise native.LargeObjectFileError('Native data administration permission is unavailable')
    transport=None;connection=None
    try:
        context,payload,_root=service.endpoint_service.workspace(server,database_target_id=target)
        provider=service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider,PostgreSQLProvider):raise native.LargeObjectFileError('Native PostgreSQL file client is unavailable')
        source,transport=native.capture(provider,payload['route'],server)
        configuration=digest({'registration':PostgreSQLMonitoringHost._configuration(server),'generation':server.endpoint_profile.profile_generation or server.endpoint_profile.cache_namespace})
        if operation=='reconcile':
            if source!=reviewed['source']:raise native.LargeObjectFileError('Native transaction reconciliation reached another server or principal')
            with transport.parameters() as parameters:
                connection=native.attach(parameters,source)
                try:return jobs.reconcile(reviewed,connection)
                finally:connection.close();connection=None
        if operation=='seal':return jobs.seal(reviewed['job_id'],owner,endpoint,target,source,configuration)
        if operation=='create':
            observed=None
            if selected['operation']=='export':
                with transport.parameters() as parameters:
                    connection=native.attach(parameters,source)
                    try:
                        with native.cursor(connection) as query:query.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
                        observed=native.metadata(connection,selected['oid'])
                    finally:connection.close();connection=None
            return jobs.create(owner,endpoint,target,selected,source,configuration,observed)
        admitted=transport;transport=None
        return jobs.start(selected_request,owner,endpoint,target,source,configuration,admitted)
    except NativeError as error:
        raise native.LargeObjectFileError('Native PostgreSQL file admission failed ('+(error.sqlstate or type(error).__name__)+')') from None
    finally:
        if connection is not None:connection.close()
        if transport is not None:transport.close()


def download(service,server,request):
    import os
    from flask import send_file
    if not isinstance(request,dict) or set(request)!={'job_id','database_target_id'}:raise native.LargeObjectFileError('Invalid file download request')
    target=request['database_target_id'];jobs,owner,endpoint,_permissions=manager(service,server,target)
    record=jobs.load(request['job_id'],owner,endpoint,target)
    if record.get('artifact_available') is False:raise native.LargeObjectFileError('This application export artifact was removed')
    if record['state'] not in {'committed','artifact_verified'} or record['options']['operation']!='export':raise native.LargeObjectFileError('A verified native export artifact is required')
    owned=jobs.payload(record)
    try:stream=owned.__enter__()
    except OSError:raise native.LargeObjectFileError('The application export artifact is unavailable') from None
    try:
        if file_identity(os.fstat(stream.fileno()))!=record['artifact_identity']:raise native.LargeObjectFileError('Native export artifact changed after verification')
        response=send_file(stream,mimetype='application/octet-stream',as_attachment=True,
            download_name=record['options']['filename'],conditional=False,max_age=0)
        response.content_length=int(record['result']['length'])
        response.headers.update({'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff','X-Accel-Buffering':'no'})
        response.headers['X-Content-SHA256']=record['result']['sha256']
        response.direct_passthrough=False
        response.call_on_close(lambda:owned.__exit__(None,None,None))
        return response
    except BaseException:owned.__exit__(None,None,None);raise
