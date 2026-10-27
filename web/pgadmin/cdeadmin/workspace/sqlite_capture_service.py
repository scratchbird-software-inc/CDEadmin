"""Authorized native capture export reviews and offline artifact receipts."""
import hashlib
from pathlib import Path

from ..core import EndpointContext
from ..operations.store import JsonOperationStore
from ..providers.embedded_route import contained_database
from ..providers.sqlite.session_api import SessionAPI,SessionAPIError,installed_library
from .sqlite_capture_jobs import SQLiteCaptureJobs,ExportTransport,digest


def manager(service,server,target_id):
    from flask import current_app
    endpoint=server.endpoint_profile
    if endpoint is None or endpoint.profile_id!='sqlite-native' or endpoint.provider_id!='org.cdeadmin.sqlite':
        raise SessionAPIError('Select a native SQLite registration')
    if not isinstance(target_id,str) or not target_id:raise SessionAPIError('Select an exact SQLite database target')
    service.endpoint_service._owned_database_target(endpoint,target_id)
    context=EndpointContext(endpoint_id=endpoint.id,mode='legacy_native',experience_family='sqlite',provider_id=endpoint.provider_id,
        provider_version=endpoint.provider_version or '0.1.0',profile_id=endpoint.profile_id,profile_version=endpoint.profile_version or '3.53.0',
        target_adapter_id=endpoint.target_adapter_id,target_adapter_version=endpoint.target_adapter_version or '0.1.0',
        **{name:getattr(endpoint,name) for name in ('pool_namespace','session_namespace','cache_namespace','diagnostic_namespace')})
    if not {'execute','administer'}<=set(service.endpoint_service.provider_registry.admitted_permissions(context)):
        raise SessionAPIError('Native capture export administration is unavailable')
    store=getattr(service.operation_bus,'store',None)
    if not isinstance(store,JsonOperationStore):raise SessionAPIError('Native capture exports require durable application storage')
    owner=service._principal_id(server);key=hashlib.sha256(target_id.encode('utf8')).hexdigest()
    root=current_app.config.get('CDEADMIN_SQLITE_CAPTURE_ROOT') or str(store.path.parent/'sqlite-captures')
    with service._semantic_lock:
        managers=getattr(service,'sqlite_capture_jobs',None)
        if managers is None:managers=service.sqlite_capture_jobs={}
        jobs=managers.get(key)
        if jobs is None:
            jobs=managers[key]=SQLiteCaptureJobs(str(store.path)+'.sqlite-captures.'+key,Path(root)/key)
            import atexit
            atexit.register(jobs.close)
    return jobs,owner,endpoint


def binding(service,server,target_id,session_id,capture_id):
    context,_payload,_root=service.endpoint_service.workspace(server,database_target_id=target_id)
    result=service.studio_service.sqlite_capture_binding(context,session_id,capture_id)
    from .sqlite_recovery_service import route
    registered=route(service,server,server.endpoint_profile,target_id)
    actual=result['client']._connection_databases.get(id(result['handle']))
    if not isinstance(actual,str) or contained_database({**registered,'database':actual})!=contained_database(registered):
        raise SessionAPIError('The retained query connection belongs to another SQLite database target')
    return result,registered


def action(service,server,operation,request):
    from flask import current_app
    if not isinstance(request,dict):raise SessionAPIError('Select a native capture export request')
    target=request.get('database_target_id');fields={key:value for key,value in request.items() if key!='database_target_id'}
    jobs,owner,endpoint=manager(service,server,target)
    if operation=='list':
        if set(fields)-{'offset','limit'}:raise SessionAPIError('Select one capture export receipt page')
        return jobs.list(owner,endpoint.id,**fields)
    if operation in {'status','cancel','reconcile'}:
        if set(fields)!={'job_id'}:raise SessionAPIError('Select one native capture export receipt')
        if operation=='reconcile':
            def inspect(descriptor,program):
                import sqlite3
                from ..providers.sqlite.driver import SQLiteConnection
                connection=sqlite3.connect(':memory:',factory=SQLiteConnection)
                try:
                    api=SessionAPI(connection,current_app.config.get('CDEADMIN_SQLITE_SESSION_LIBRARY') or installed_library())
                    if api.program!=program:raise SessionAPIError('The recorded native capture helper is unavailable on this host')
                    return api.call('inspect_file',descriptor,-1)
                finally:connection.close()
            return jobs.reconcile(fields['job_id'],owner,endpoint.id,inspect)
        return {'status':jobs.get,'cancel':jobs.cancel}[operation](fields['job_id'],owner,endpoint.id)
    if operation=='files':
        if set(fields)-{'job_id','offset','limit'} or 'job_id' not in fields:raise SessionAPIError('Select one capture artifact file page')
        return jobs.files(fields['job_id'],owner,endpoint.id,fields.get('offset',0),fields.get('limit',100))
    if operation=='remove_artifact':
        if set(fields)!={'job_id','confirmation'}:raise SessionAPIError('Confirm one native capture artifact removal')
        return jobs.remove_artifact(fields['job_id'],owner,endpoint.id,fields['confirmation'])
    if operation=='review':
        if set(fields)!={'session_id','capture_id','kind','timeout_seconds'}:raise SessionAPIError('Review exact retained capture export options')
        kind,timeout=fields['kind'],fields['timeout_seconds']
        if kind not in {'changeset','patchset'} or timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):
            raise SessionAPIError('Select native changeset/patchset format and a positive runtime or no deadline')
        selected={'kind':kind,'timeout_seconds':timeout}
        session_id,capture_id=fields['session_id'],fields['capture_id']
    elif operation=='start':
        reviewed=jobs.load(fields.get('job_id'),owner,endpoint.id)
        if reviewed['state']!='reviewed':return jobs.start(fields,owner,endpoint.id,{},None)
        selected=reviewed['options'];session_id=reviewed['source']['studio_session_id'];capture_id=reviewed['source']['capture_id']
    else:raise SessionAPIError('Native capture export action is unavailable')
    selected_binding,registered=binding(service,server,target,session_id,capture_id)
    limit=current_app.config.get('CDEADMIN_SQLITE_CAPTURE_MAX_RUNTIME_SECONDS')
    if limit is not None and (type(limit) is not int or not 1<=limit<=2147483647 or selected['timeout_seconds'] is None or selected['timeout_seconds']>limit):
        raise SessionAPIError('Application policy requires a bounded native capture export duration')
    configuration=digest({'registration':registered,'root':str(jobs.root),'runtime_limit':limit,'database_target_id':target})
    if operation=='review':
        return jobs.review(owner,endpoint.id,selected,{'identity':selected_binding['source'],'state':{}},configuration,selected_binding['program'])
    transport=ExportTransport(jobs,selected_binding['client'],selected_binding['handle'],selected_binding['api'],selected_binding['source'])
    return jobs.start(fields,owner,endpoint.id,{'source':selected_binding['source'],'configuration':configuration,'program':selected_binding['program']},transport)


def download(service,server,request):
    from flask import send_file
    if not isinstance(request,dict) or set(request)!={'database_target_id','job_id','path'}:
        raise SessionAPIError('Select one verified native capture artifact file')
    jobs,owner,endpoint=manager(service,server,request['database_target_id'])
    if not isinstance(request['path'],str):raise SessionAPIError('Select an exact capture file path')
    opened=(jobs.diagnostic_download if request['path'].startswith('partial/') else jobs.download)(request['job_id'],owner,endpoint.id,request['path'])
    stream,row=opened.__enter__()
    try:
        response=send_file(stream,mimetype='application/octet-stream',as_attachment=True,download_name=row['path'],conditional=False,max_age=0)
        response.content_length=row['size'];response.direct_passthrough=False
        response.headers.update({'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff'})
        response.call_on_close(lambda:opened.__exit__(None,None,None));return response
    except BaseException:opened.__exit__(None,None,None);raise
