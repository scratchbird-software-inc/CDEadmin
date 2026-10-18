"""Authorized ordered native transforms and optional registered schema basis."""
from copy import deepcopy

from ..providers.sqlite.changeset_transform import options
from ..providers.sqlite.transform_context import context,schema_snapshot
from ..providers.sqlite.session_api import SessionAPIError,installed_library
from .sqlite_capture_service import manager as capture_manager
from .sqlite_capture_jobs import digest
from .sqlite_native_files import resolve,manager as source_manager
from .sqlite_recovery_service import route
from .sqlite_transform_jobs import SQLiteTransformJobs,TransformTransport


def retained_binding(service,server,target,session_id,library,database=None):
    from ..providers.embedded_route import contained_database
    context,_payload,_root=service.endpoint_service.workspace(server,database_target_id=target)
    result=service.studio_service.sqlite_transform_binding(context,session_id,library,database)
    registered=route(service,server,server.endpoint_profile,target)
    actual=result['client']._connection_databases.get(id(result['handle']))
    if not isinstance(actual,str) or contained_database({**registered,'database':actual})!=contained_database(registered):
        raise SessionAPIError('The retained schema connection belongs to another SQLite database target')
    return result,registered


def manager(service,server,target):
    base,owner,endpoint=capture_manager(service,server,target)
    with service._semantic_lock:
        managers=getattr(service,'sqlite_transform_jobs',None)
        if managers is None:managers=service.sqlite_transform_jobs={}
        jobs=managers.get(target)
        if jobs is None:
            jobs=managers[target]=SQLiteTransformJobs(str(base.path)+'.transforms',base.root/'transformed-files')
            import atexit
            atexit.register(jobs.close)
    return jobs,owner,endpoint


def action(service,server,operation,request):
    from flask import current_app
    if not isinstance(request,dict):raise SessionAPIError('Select a native file transform request')
    target=request.get('database_target_id');fields={key:value for key,value in request.items() if key!='database_target_id'}
    jobs,owner,endpoint=manager(service,server,target)
    library=current_app.config.get('CDEADMIN_SQLITE_SESSION_LIBRARY') or installed_library()
    if operation=='catalog':
        if fields:raise SessionAPIError('Select native transform capability inspection')
        try:
            with context(library) as (_connection,api):program=api.program
            available=True;reason=None
        except (ValueError,OSError) as error:program=None;available=False;reason=str(error)
        return {'helper_available':available,'program':program,'unavailable_reason':reason,
            'targets':[{'target_id':item.id,'display_name':item.display_name,'database':item.database} for item in endpoint.database_targets],
            'input_kinds':['capture','upload','transform','diff','rebase'],'database_mutation':False}
    if operation=='schemas':
        if set(fields)-{'session_id'}:raise SessionAPIError('Select the registered or retained schema basis')
        if 'session_id' in fields:
            if not isinstance(fields['session_id'],str) or not fields['session_id']:raise SessionAPIError('Select a retained query session')
            selected,_registered=retained_binding(service,server,target,fields['session_id'],library)
            return {'schemas':[{'name':row[1],'filename':row[2]} for row in selected['source']['databases']],
                'session_id':fields['session_id'],'transaction_open':selected['source']['transaction_open'],
                'scope':'this retained query connection, including temporary, in-memory, attached and uncommitted schema; its SQL transaction is preserved'}
        registered=route(service,server,endpoint,target)
        with context(library,registered) as (connection,_api):
            return {'schemas':[{'name':row[1],'filename':row[2]} for row in connection.execute('PRAGMA database_list') if row[2]],
                'scope':'this registered file and its configured attachments; transient query-session schema is separate'}
    if operation=='sources':
        if set(fields)-{'source_database_target_id','kind','offset','limit'} or not {'source_database_target_id','kind'}<=set(fields):
            raise SessionAPIError('Select an owned native artifact source page')
        sources,source_owner,source_endpoint=source_manager(service,server,fields['source_database_target_id'],fields['kind'])
        return sources.list(source_owner,source_endpoint.id,fields.get('offset',0),fields.get('limit',25))
    if operation=='list':
        if set(fields)-{'offset','limit'}:raise SessionAPIError('Select a native transform receipt page')
        return jobs.list(owner,endpoint.id,**fields)
    if operation in {'status','cancel','reconcile'}:
        if set(fields)!={'job_id'}:raise SessionAPIError('Select one native transform receipt')
        if operation=='reconcile':
            def inspect(descriptor,expected):
                with context(library) as (_connection,api):
                    if api.program!=expected:raise SessionAPIError('The recorded native transform helper is unavailable')
                    return api.call('inspect_file',descriptor,-1)
            return jobs.reconcile(fields['job_id'],owner,endpoint.id,inspect)
        return {'status':jobs.get,'cancel':jobs.cancel}[operation](fields['job_id'],owner,endpoint.id)
    if operation=='files':
        if set(fields)-{'job_id','offset','limit'} or 'job_id' not in fields:raise SessionAPIError('Select a native transform output file page')
        return jobs.files(fields['job_id'],owner,endpoint.id,fields.get('offset',0),fields.get('limit',25))
    if operation=='remove_artifact':
        if set(fields)!={'job_id','confirmation'}:raise SessionAPIError('Confirm native transform output removal')
        return jobs.remove_artifact(fields['job_id'],owner,endpoint.id,fields['confirmation'])
    if operation=='review':
        if set(fields)!={'inputs','options'}:raise SessionAPIError('Review exact ordered native inputs and transform options')
        selected=options(fields['options']);references=fields['inputs']
        if not isinstance(references,list) or not 1<=len(references)<=100:raise SessionAPIError('Select between one and 100 ordered native inputs')
    elif operation=='start':
        reviewed=jobs.load(fields.get('job_id'),owner,endpoint.id)
        if reviewed['state']!='reviewed':return jobs.start(fields,owner,endpoint.id,{},None)
        selected=reviewed['options'];references=[deepcopy(item['reference']) for item in reviewed['source']['inputs']]
    else:raise SessionAPIError('Native transform action is unavailable')
    native_inputs=[resolve(service,server,reference,owner,endpoint) for reference in references]
    identities=[item[0] for item in native_inputs];mode=selected['operation']
    if mode=='invert' and len(identities)!=1 or mode=='concat' and len(identities)!=2 or mode=='rebase' and len(identities)<2:
        raise SessionAPIError('Ordered native input count differs from the transform')
    expected=['changeset']+['rebase']*(len(identities)-1) if mode=='rebase' else None
    if expected is not None and [item['native_kind'] for item in identities]!=expected or mode!='rebase' and any(item['native_kind']=='rebase' for item in identities):
        raise SessionAPIError('Rebasing requires a local changeset followed by ordered native rebase buffers')
    if mode=='invert' and identities[0]['native_kind']!='changeset':raise SessionAPIError('Native patchsets cannot be inverted')
    limit=current_app.config.get('CDEADMIN_SQLITE_CAPTURE_MAX_RUNTIME_SECONDS')
    if limit is not None and (type(limit) is not int or not 1<=limit<=2147483647 or selected['timeout_seconds'] is None or selected['timeout_seconds']>limit):
        raise SessionAPIError('Application policy requires a bounded native transform duration')
    retained=None
    if selected.get('schema_session_id') is not None:
        retained,registered=retained_binding(service,server,target,selected['schema_session_id'],library,selected['schema_database'])
        schema=retained['source']['schema'];program=retained['program']
    else:
        registered=route(service,server,endpoint,target) if selected['schema_database'] is not None else None
        with context(library,registered) as (connection,api):
            schema=None if registered is None else schema_snapshot(connection,selected['schema_database']);program=api.program
    observed={'inputs':identities,'schema':schema}
    if retained is not None:observed['schema_binding']=retained['source']
    configuration=digest({'database_target_id':target,'root':str(jobs.root),'schema_registration':registered,'runtime_limit':limit})
    if operation=='review':return jobs.review(owner,endpoint.id,selected,{'identity':observed,'state':{}},configuration,program)
    transport=TransformTransport(jobs,library,[item[1] for item in native_inputs],registered,retained_binding=retained)
    return jobs.start(fields,owner,endpoint.id,{'source':observed,'configuration':configuration,'program':program},transport)


def download(service,server,request):
    from flask import send_file
    if not isinstance(request,dict) or set(request)!={'database_target_id','job_id','path'} or not isinstance(request['path'],str):
        raise SessionAPIError('Select one retained native transform file')
    jobs,owner,endpoint=manager(service,server,request['database_target_id'])
    opened=(jobs.diagnostic_download if request['path'].startswith('partial/') else jobs.download)(request['job_id'],owner,endpoint.id,request['path'])
    stream,row=opened.__enter__()
    try:
        response=send_file(stream,mimetype='application/octet-stream',as_attachment=True,download_name=row['path'],conditional=False,max_age=0)
        response.content_length=row['size'];response.direct_passthrough=False
        response.headers.update({'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff'})
        response.call_on_close(lambda:opened.__exit__(None,None,None));return response
    except BaseException:opened.__exit__(None,None,None);raise
