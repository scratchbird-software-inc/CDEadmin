"""Authorized file-target apply reviews from verified native capture artifacts."""
from ..providers.sqlite.changeset_apply import connect,options,target_snapshot
from ..providers.sqlite.session_api import SessionAPIError,identity,installed_library
from .sqlite_capture_service import manager as capture_manager
from .sqlite_capture_jobs import digest
from .sqlite_changeset_jobs import SQLiteChangesetJobs,ApplyTransport
from .sqlite_recovery_service import route


def manager(service,server,target):
    base,owner,endpoint=capture_manager(service,server,target)
    with service._semantic_lock:
        managers=getattr(service,'sqlite_changeset_jobs',None)
        if managers is None:managers=service.sqlite_changeset_jobs={}
        jobs=managers.get(target)
        if jobs is None:
            jobs=managers[target]=SQLiteChangesetJobs(str(base.path)+'.apply',base.root/'apply-output')
            import atexit
            atexit.register(jobs.close)
    return jobs,owner,endpoint


def source(service,server,fields,owner,endpoint):
    jobs,source_owner,source_endpoint=capture_manager(service,server,fields['source_database_target_id'])
    if owner!=source_owner or endpoint.id!=source_endpoint.id:raise SessionAPIError('Select an owned native source export')
    record=jobs.load(fields['source_job_id'],owner,endpoint.id)
    if record['state'] not in {'completed','artifact_verified'} or record.get('artifact_removed'):
        raise SessionAPIError('Select a retained verified native changeset/patchset export')
    expected='capture.'+record['options']['kind']
    artifact=(record.get('result') or {}).get('artifact') or {}
    row=next((row for row in artifact.get('files',[]) if row['path']==expected),None)
    if fields['path']!=expected or row is None or not artifact.get('native_iterator_complete'):
        raise SessionAPIError('Select the exact verified native changeset or patchset file')
    return jobs,{'source_database_target_id':fields['source_database_target_id'],'source_job_id':record['job_id'],
        'input_path':expected,'input_file':row,'input_format':artifact['format'],'native_record_count':artifact['native_record_count']}


def action(service,server,operation,request):
    from flask import current_app
    if not isinstance(request,dict):raise SessionAPIError('Select a native changeset apply request')
    target=request.get('database_target_id');fields={key:value for key,value in request.items() if key!='database_target_id'}
    jobs,owner,endpoint=manager(service,server,target)
    library=current_app.config.get('CDEADMIN_SQLITE_SESSION_LIBRARY') or installed_library()
    if operation=='catalog':
        if fields:raise SessionAPIError('Select native apply source registrations')
        try:_path,program=identity(library);available=True;reason=None
        except (OSError,ValueError) as error:program=None;available=False;reason=str(error)
        return {'targets':[{'target_id':item.id,'display_name':item.display_name,'database':item.database} for item in endpoint.database_targets],
            'helper_available':available,'program':program,'unavailable_reason':reason,
            'scope':'Verified capture exports from this endpoint; application-owned main database writes on an independent connection'}
    if operation=='sources':
        if set(fields)-{'source_database_target_id','offset','limit'} or 'source_database_target_id' not in fields:raise SessionAPIError('Select one native source export page')
        sources,source_owner,source_endpoint=capture_manager(service,server,fields['source_database_target_id'])
        return sources.list(source_owner,source_endpoint.id,fields.get('offset',0),fields.get('limit',25))
    if operation=='list':
        if set(fields)-{'offset','limit'}:raise SessionAPIError('Select one apply receipt page')
        return jobs.list(owner,endpoint.id,**fields)
    if operation in {'status','cancel','reconcile'}:
        if set(fields)!={'job_id'}:raise SessionAPIError('Select one native apply receipt')
        return {'status':jobs.get,'cancel':jobs.cancel,'reconcile':jobs.reconcile}[operation](fields['job_id'],owner,endpoint.id)
    if operation=='files':
        if set(fields)-{'job_id','offset','limit'} or 'job_id' not in fields:raise SessionAPIError('Select one native apply output file page')
        return jobs.files(fields['job_id'],owner,endpoint.id,fields.get('offset',0),fields.get('limit',25))
    if operation=='remove_artifact':
        if set(fields)!={'job_id','confirmation'}:raise SessionAPIError('Confirm one native apply output removal')
        return jobs.remove_artifact(fields['job_id'],owner,endpoint.id,fields['confirmation'])
    if operation=='review':
        if set(fields)!={'source_database_target_id','source_job_id','path','options'}:raise SessionAPIError('Review exact native source and apply options')
        selected=options(fields['options']);input_fields=fields
    elif operation=='start':
        reviewed=jobs.load(fields.get('job_id'),owner,endpoint.id)
        if reviewed['state']!='reviewed':return jobs.start(fields,owner,endpoint.id,{},None)
        selected=reviewed['options'];input_fields={key:reviewed['source'][key] for key in ('source_database_target_id','source_job_id')}
        input_fields['path']=reviewed['source']['input_path']
    else:raise SessionAPIError('Native changeset apply action is unavailable')
    source_jobs,observed_source=source(service,server,input_fields,owner,endpoint)
    if observed_source['input_format'].startswith('sqlite-native-patchset') and selected['invert']:
        raise SessionAPIError('Native patchsets cannot be inverted')
    limit=current_app.config.get('CDEADMIN_SQLITE_CAPTURE_MAX_RUNTIME_SECONDS')
    if limit is not None and (type(limit) is not int or not 1<=limit<=2147483647 or selected['timeout_seconds'] is None or selected['timeout_seconds']>limit):raise SessionAPIError('Application policy requires a bounded native apply duration')
    registered=route(service,server,endpoint,target)
    connection,api=connect(registered,library)
    try:observed={**observed_source,'destination':target_snapshot(connection,registered)};program=api.program
    finally:connection.close()
    configuration=digest({'registration':registered,'root':str(jobs.root),'runtime_limit':limit,'database_target_id':target})
    if operation=='review':return jobs.review(owner,endpoint.id,selected,{'identity':observed,'state':{}},configuration,program)
    transport=ApplyTransport(jobs,registered,library,lambda:source_jobs.download(observed_source['source_job_id'],owner,endpoint.id,observed_source['input_path']))
    return jobs.start(fields,owner,endpoint.id,{'source':observed,'program':program,'configuration':configuration},transport)


def download(service,server,request):
    from flask import send_file
    if not isinstance(request,dict) or set(request)!={'database_target_id','job_id','path'}:raise SessionAPIError('Select one native apply output file')
    jobs,owner,endpoint=manager(service,server,request['database_target_id'])
    opened=jobs.output_download(request['job_id'],owner,endpoint.id,request['path']);stream,row=opened.__enter__()
    try:
        response=send_file(stream,mimetype='application/octet-stream',as_attachment=True,download_name=row['path'],conditional=False,max_age=0)
        response.content_length=row['size'];response.direct_passthrough=False
        response.headers.update({'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff'})
        response.call_on_close(lambda:opened.__exit__(None,None,None));return response
    except BaseException:opened.__exit__(None,None,None);raise
