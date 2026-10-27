"""Authorized retained-session native comparison and durable artifact access."""
from ..providers.sqlite.diff_export import options
from ..providers.sqlite.session_api import SessionAPIError,installed_library
from ..providers.sqlite.transform_context import context,retained_snapshot,schema_snapshot
from .sqlite_capture_service import manager as capture_manager
from .sqlite_capture_jobs import digest
from .sqlite_diff_jobs import SQLiteDiffJobs,DiffTransport
from .sqlite_transform_service import retained_binding


def manager(service,server,target):
    base,owner,endpoint=capture_manager(service,server,target)
    with service._semantic_lock:
        managers=getattr(service,'sqlite_diff_jobs',None)
        if managers is None:managers=service.sqlite_diff_jobs={}
        jobs=managers.get(target)
        if jobs is None:
            jobs=managers[target]=SQLiteDiffJobs(str(base.path)+'.diffs',base.root/'table-differences')
            import atexit
            atexit.register(jobs.close)
    return jobs,owner,endpoint


def action(service,server,operation,request):
    from flask import current_app
    if not isinstance(request,dict):raise SessionAPIError('Select a native table comparison request')
    target=request.get('database_target_id');fields={key:value for key,value in request.items() if key!='database_target_id'}
    jobs,owner,endpoint=manager(service,server,target)
    library=current_app.config.get('CDEADMIN_SQLITE_SESSION_LIBRARY') or installed_library()
    if operation=='list':
        if set(fields)-{'offset','limit'}:raise SessionAPIError('Select a native comparison receipt page')
        return jobs.list(owner,endpoint.id,**fields)
    if operation in {'status','cancel','reconcile'}:
        if set(fields)!={'job_id'}:raise SessionAPIError('Select one native comparison receipt')
        if operation=='reconcile':
            def inspect(descriptor,program):
                with context(library) as (_connection,api):
                    if api.program!=program:raise SessionAPIError('The recorded native comparison helper is unavailable')
                    return api.call('inspect_file',descriptor,-1)
            return jobs.reconcile(fields['job_id'],owner,endpoint.id,inspect)
        return {'status':jobs.get,'cancel':jobs.cancel}[operation](fields['job_id'],owner,endpoint.id)
    if operation=='files':
        if set(fields)-{'job_id','offset','limit'} or 'job_id' not in fields:raise SessionAPIError('Select a native comparison file page')
        return jobs.files(fields['job_id'],owner,endpoint.id,fields.get('offset',0),fields.get('limit',25))
    if operation=='remove_artifact':
        if set(fields)!={'job_id','confirmation'}:raise SessionAPIError('Confirm native comparison output removal')
        return jobs.remove_artifact(fields['job_id'],owner,endpoint.id,fields['confirmation'])
    if operation in {'catalog','tables'}:
        if set(fields)!=({'session_id'} if operation=='catalog' else {'session_id','database'}):
            raise SessionAPIError('Select this retained query session and exact destination schema')
        if not isinstance(fields['session_id'],str) or not fields['session_id']:raise SessionAPIError('Select an open query session')
        selected,_registered=retained_binding(service,server,target,fields['session_id'],library,
            fields['database'] if operation=='tables' else None)
        if operation=='catalog':
            return {'program':selected['program'],'helper_available':True,
                'schemas':[{'name':row[1],'filename':row[2]} for row in selected['source']['databases']],
                'transaction_open':selected['source']['transaction_open'],
                'scope':'this exact query connection; current SQL visibility, existing captures and transaction ownership remain intact'}
        with selected['client']._lock:
            connection=selected['handle'];selected['client']._require_idle(connection)
            quoted='"'+fields['database'].replace('"','""')+'"'
            rows=connection.execute('SELECT name,sql FROM '+quoted+'.sqlite_schema WHERE type=\'table\' ORDER BY name')
            return {'tables':[{'name':row[0],'definition':row[1]} for row in rows],'database':fields['database']}
    if operation=='review':
        if set(fields)!={'session_id','options'}:raise SessionAPIError('Review exact retained table comparison options')
        selected=options(fields['options']);session_id=fields['session_id']
    elif operation=='start':
        reviewed=jobs.load(fields.get('job_id'),owner,endpoint.id)
        if reviewed['state']!='reviewed':return jobs.start(fields,owner,endpoint.id,{},None)
        selected=reviewed['options'];session_id=reviewed['source']['schema_binding']['studio_session_id']
    else:raise SessionAPIError('Native table comparison action is unavailable')
    if not isinstance(session_id,str) or not session_id:raise SessionAPIError('Select an open retained query session')
    limit=current_app.config.get('CDEADMIN_SQLITE_CAPTURE_MAX_RUNTIME_SECONDS')
    if limit is not None and (type(limit) is not int or not 1<=limit<=2147483647 or selected['timeout_seconds'] is None or selected['timeout_seconds']>limit):
        raise SessionAPIError('Application policy requires a bounded native comparison duration')
    binding,registered=retained_binding(service,server,target,session_id,library,selected['database'])
    with binding['client']._lock:
        connection=binding['handle'];binding['client']._require_idle(connection)
        observed={'schema_binding':retained_snapshot(connection,binding['api'],session_id,selected['database']),
            'source_schema':schema_snapshot(connection,selected['source_database'],transient=True)}
    configuration=digest({'database_target_id':target,'registration':registered,'root':str(jobs.root),'runtime_limit':limit})
    if operation=='review':return jobs.review(owner,endpoint.id,selected,{'identity':observed,'state':{}},configuration,binding['program'])
    return jobs.start(fields,owner,endpoint.id,{'source':observed,'configuration':configuration,'program':binding['program']},DiffTransport(jobs,library,binding))


def download(service,server,request):
    from flask import send_file
    if not isinstance(request,dict) or set(request)!={'database_target_id','job_id','path'} or not isinstance(request['path'],str):
        raise SessionAPIError('Select one retained native comparison file')
    jobs,owner,endpoint=manager(service,server,request['database_target_id'])
    opened=(jobs.diagnostic_download if request['path'].startswith('partial/') else jobs.download)(request['job_id'],owner,endpoint.id,request['path'])
    stream,row=opened.__enter__()
    try:
        response=send_file(stream,mimetype='application/octet-stream',as_attachment=True,download_name=row['path'],conditional=False,max_age=0)
        response.content_length=row['size'];response.direct_passthrough=False
        response.headers.update({'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff'})
        response.call_on_close(lambda:opened.__exit__(None,None,None));return response
    except BaseException:opened.__exit__(None,None,None);raise
