"""Authorized offline typed inspection of retained native input artifacts."""
from copy import deepcopy

from ..providers.sqlite.changeset_inspection import options
from ..providers.sqlite.transform_context import context
from ..providers.sqlite.session_api import SessionAPIError,installed_library
from .sqlite_capture_service import manager as capture_manager
from .sqlite_capture_jobs import digest
from .sqlite_native_files import resolve
from .sqlite_inspection_jobs import SQLiteInspectionJobs,InspectionTransport


def manager(service,server,target):
    base,owner,endpoint=capture_manager(service,server,target)
    with service._semantic_lock:
        managers=getattr(service,'sqlite_inspection_jobs',None)
        if managers is None:managers=service.sqlite_inspection_jobs={}
        jobs=managers.get(target)
        if jobs is None:
            jobs=managers[target]=SQLiteInspectionJobs(str(base.path)+'.inspections',base.root/'inspections')
            import atexit
            atexit.register(jobs.close)
    return jobs,owner,endpoint


def action(service,server,operation,request):
    from flask import current_app
    if not isinstance(request,dict):raise SessionAPIError('Select a native inspection request')
    target=request.get('database_target_id');fields={key:value for key,value in request.items() if key!='database_target_id'}
    jobs,owner,endpoint=manager(service,server,target)
    library=current_app.config.get('CDEADMIN_SQLITE_SESSION_LIBRARY') or installed_library()
    if operation=='catalog':
        if fields:raise SessionAPIError('Select native inspection support')
        try:
            with context(library) as (_connection,api):
                if api.program.get('native_session_revision',0)<6:raise SessionAPIError('The native helper lacks typed file inspection')
                program=api.program
            available=True;reason=None
        except (ValueError,OSError) as error:available=False;reason=str(error);program=None
        return {'helper_available':available,'program':program,'unavailable_reason':reason,'database_mutation':False,'apply_input':False}
    if operation=='list':
        if set(fields)-{'offset','limit'}:raise SessionAPIError('Select a native inspection receipt page')
        return jobs.list(owner,endpoint.id,**fields)
    if operation in {'status','cancel','result','reconcile'}:
        if set(fields)!={'job_id'}:raise SessionAPIError('Select one native inspection receipt')
        if operation=='reconcile':
            import json,os
            record=jobs.load(fields['job_id'],owner,endpoint.id)
            def inspect_partial(descriptor,expected):
                if record['options']['mode']=='extract':return {'byte_value_complete':False,'diagnostic_only':True}
                if os.fstat(descriptor).st_size>134217728:return {'json_complete':False,'exceeds_inspection_bound':True}
                try:
                    with os.fdopen(os.dup(descriptor),'r',encoding='utf8') as stream:value=json.load(stream)
                    return {'json_complete':True,'format_matches':isinstance(value,dict) and value.get('format')=='sqlite-native-inspection@1','recorded_program_matches':isinstance(value,dict) and value.get('program')==expected}
                except (ValueError,UnicodeError):return {'json_complete':False}
            return jobs.reconcile(fields['job_id'],owner,endpoint.id,inspect_partial)
        return {'status':jobs.get,'cancel':jobs.cancel,'result':jobs.result}[operation](fields['job_id'],owner,endpoint.id)
    if operation=='files':
        if set(fields)-{'job_id','offset','limit'} or 'job_id' not in fields:raise SessionAPIError('Select a native inspection file page')
        return jobs.files(fields['job_id'],owner,endpoint.id,fields.get('offset',0),fields.get('limit',25))
    if operation=='remove_artifact':
        if set(fields)!={'job_id','confirmation'}:raise SessionAPIError('Confirm native inspection output removal')
        return jobs.remove_artifact(fields['job_id'],owner,endpoint.id,fields['confirmation'])
    if operation=='review':
        if set(fields)!={'input','options'}:raise SessionAPIError('Select one exact native artifact and inspection options')
        selected=options(fields['options']);reference=fields['input']
    elif operation=='start':
        reviewed=jobs.load(fields.get('job_id'),owner,endpoint.id)
        if reviewed['state']!='reviewed':return jobs.start(fields,owner,endpoint.id,{},None)
        selected=reviewed['options'];reference=deepcopy(reviewed['source']['input']['reference'])
    else:raise SessionAPIError('Native inspection action is unavailable')
    observed,input_factory=resolve(service,server,reference,owner,endpoint)
    if observed['native_kind'] not in {'changeset','patchset'}:raise SessionAPIError('Select a native changeset or patchset for typed inspection')
    limit=current_app.config.get('CDEADMIN_SQLITE_CAPTURE_MAX_RUNTIME_SECONDS')
    if limit is not None and (type(limit) is not int or not 1<=limit<=2147483647 or selected['timeout_seconds'] is None or selected['timeout_seconds']>limit):
        raise SessionAPIError('Application policy requires a bounded native inspection duration')
    with context(library) as (_connection,api):
        if api.program.get('native_session_revision',0)<6:raise SessionAPIError('The native helper lacks typed file inspection')
        program=api.program
    source={'input':observed};configuration=digest({'database_target_id':target,'root':str(jobs.root),'runtime_limit':limit})
    if operation=='review':return jobs.review(owner,endpoint.id,selected,{'identity':source,'state':{}},configuration,program)
    return jobs.start(fields,owner,endpoint.id,{'source':source,'configuration':configuration,'program':program},InspectionTransport(jobs,library,input_factory))


def download(service,server,request):
    from flask import send_file
    if not isinstance(request,dict) or set(request)!={'database_target_id','job_id','path'} or request.get('path') not in {'inspection.json','value.bin','partial/inspection.json','partial/value.bin'}:
        raise SessionAPIError('Select the exact retained native inspection JSON file')
    jobs,owner,endpoint=manager(service,server,request['database_target_id']);factory=jobs.diagnostic_download if request['path'].startswith('partial/') else jobs.download
    opened=factory(request['job_id'],owner,endpoint.id,request['path']);stream,row=opened.__enter__()
    try:
        response=send_file(stream,mimetype='application/json' if request['path'].endswith('.json') else 'application/octet-stream',as_attachment=True,download_name=request['path'].split('/')[-1],conditional=False,max_age=0)
        response.content_length=row['size'];response.direct_passthrough=False
        response.headers['X-Content-Type-Options']='nosniff';response.headers['Cache-Control']='no-store'
        response.call_on_close(lambda:opened.__exit__(None,None,None));return response
    except BaseException:opened.__exit__(*__import__('sys').exc_info());raise
