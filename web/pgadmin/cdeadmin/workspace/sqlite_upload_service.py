"""Authorized external native-file intake; database apply remains separate."""
import sqlite3

from ..providers.sqlite.driver import SQLiteConnection
from ..providers.sqlite.session_api import SessionAPI,SessionAPIError,installed_library
from .sqlite_capture_service import manager as capture_manager
from .sqlite_capture_jobs import digest
from .sqlite_upload_jobs import SQLiteUploadJobs,CHUNK_BYTES,options


def manager(service,server,target):
    base,owner,endpoint=capture_manager(service,server,target)
    with service._semantic_lock:
        managers=getattr(service,'sqlite_upload_jobs',None)
        if managers is None:managers=service.sqlite_upload_jobs={}
        jobs=managers.get(target)
        if jobs is None:
            jobs=managers[target]=SQLiteUploadJobs(str(base.path)+'.uploads',base.root/'uploaded-files')
            import atexit
            atexit.register(jobs.close)
    return jobs,owner,endpoint


def program(library):
    connection=sqlite3.connect(':memory:',factory=SQLiteConnection)
    try:return SessionAPI(connection,library).program
    finally:connection.close()


def action(service,server,operation,request):
    from flask import current_app
    if not isinstance(request,dict):raise SessionAPIError('Select a native file intake request')
    target=request.get('database_target_id');fields={key:value for key,value in request.items() if key!='database_target_id'}
    jobs,owner,endpoint=manager(service,server,target)
    library=current_app.config.get('CDEADMIN_SQLITE_SESSION_LIBRARY') or installed_library()
    if operation=='list':
        if set(fields)-{'offset','limit'}:raise SessionAPIError('Select one native intake receipt page')
        return jobs.list(owner,endpoint.id,**fields)
    if operation in {'status','cancel','reconcile'}:
        if set(fields)!={'job_id'}:raise SessionAPIError('Select one native intake receipt')
        if operation=='reconcile':
            def inspect(descriptor,expected):
                connection=sqlite3.connect(':memory:',factory=SQLiteConnection)
                try:
                    api=SessionAPI(connection,library)
                    if api.program!=expected:raise SessionAPIError('The recorded native intake helper is unavailable')
                    return api.call('inspect_file',descriptor,-1)
                finally:connection.close()
            return jobs.reconcile(fields['job_id'],owner,endpoint.id,inspect)
        return {'status':jobs.get,'cancel':jobs.cancel}[operation](fields['job_id'],owner,endpoint.id)
    if operation=='files':
        if set(fields)-{'job_id','offset','limit'} or 'job_id' not in fields:raise SessionAPIError('Select one native intake file page')
        return jobs.files(fields['job_id'],owner,endpoint.id,fields.get('offset',0),fields.get('limit',25))
    if operation=='remove_artifact':
        if set(fields)!={'job_id','confirmation'}:raise SessionAPIError('Confirm native intake file removal')
        return jobs.remove_artifact(fields['job_id'],owner,endpoint.id,fields['confirmation'])
    if operation=='chunk':
        if set(fields)!={'job_id','chunk'}:raise SessionAPIError('Select one owned native upload chunk')
        return jobs.upload(fields['job_id'],owner,endpoint.id,fields['chunk'])
    maximum=current_app.config.get('CDEADMIN_SQLITE_CAPTURE_MAX_UPLOAD_BYTES')
    limit=current_app.config.get('CDEADMIN_SQLITE_CAPTURE_MAX_RUNTIME_SECONDS')
    configuration=digest({'root':str(jobs.root),'database_target_id':target,'maximum_upload_bytes':maximum,'validation_runtime_limit':limit})
    if operation=='create':
        if set(fields)!={'options'}:raise SessionAPIError('Select exact native intake options')
        selected=options(fields['options'])
        if maximum is not None and (type(maximum) is not int or maximum<0 or int(selected['length'])>maximum):raise SessionAPIError('Native upload exceeds application size policy')
        if limit is not None and (type(limit) is not int or not 1<=limit<=2147483647 or selected['timeout_seconds'] is None or selected['timeout_seconds']>limit):
            raise SessionAPIError('Application policy requires bounded native file validation')
        return jobs.create(owner,endpoint.id,selected,configuration,program(library))
    if operation=='seal':
        if set(fields)!={'job_id'}:raise SessionAPIError('Select one native upload for validation')
        record=jobs.load(fields['job_id'],owner,endpoint.id)
        if record['state'] not in {'uploading','reviewed'}:return jobs.get(record['job_id'],owner,endpoint.id)
        return jobs.seal(record['job_id'],owner,endpoint.id,configuration,program(library),library)
    if operation=='catalog':
        if fields:raise SessionAPIError('Select native intake capability inspection')
        try:observed=program(library);available=True;reason=None
        except (OSError,ValueError,sqlite3.Error) as error:observed=None;available=False;reason=str(error)
        return {'helper_available':available,'program':observed,'unavailable_reason':reason,'chunk_bytes':CHUNK_BYTES,
            'maximum_upload_bytes':None if maximum is None else str(maximum),'database_mutation':False}
    raise SessionAPIError('Native intake action is unavailable')


def download(service,server,request):
    from flask import send_file
    if not isinstance(request,dict) or set(request)!={'database_target_id','job_id','path'} or not isinstance(request['path'],str):
        raise SessionAPIError('Select one native intake file')
    jobs,owner,endpoint=manager(service,server,request['database_target_id'])
    opened=(jobs.diagnostic_download if request['path'].startswith('partial/') else jobs.download)(request['job_id'],owner,endpoint.id,request['path'])
    stream,row=opened.__enter__()
    try:
        response=send_file(stream,mimetype='application/octet-stream',as_attachment=True,download_name=row['path'],conditional=False,max_age=0)
        response.content_length=row['size'];response.direct_passthrough=False
        response.headers.update({'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff'})
        response.call_on_close(lambda:opened.__exit__(None,None,None));return response
    except BaseException:opened.__exit__(None,None,None);raise
