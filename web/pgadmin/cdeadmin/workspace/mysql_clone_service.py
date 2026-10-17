"""Native clone admission with offline, owner-bound durable receipts."""
from ..core import EndpointContext
from ..operations.store import JsonOperationStore
from ..providers.mysql_family.mysql_clone import CloneError, connect, options
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_clone_jobs import MySQLCloneJobs, digest
from .mysql_monitoring_host import MySQLMonitoringHost


def action(service,server,operation,request):
    from flask import current_app
    if not isinstance(request,dict):raise CloneError('A native clone request is required')
    endpoint=server.endpoint_profile
    if endpoint is None or endpoint.profile_id!='mysql-native' or endpoint.provider_id!='org.cdeadmin.mysql':
        raise CloneError('Select a native MySQL registration')
    context=EndpointContext(endpoint_id=endpoint.id,mode='legacy_native',experience_family='mysql',
        provider_id='org.cdeadmin.mysql',provider_version=endpoint.provider_version or '0.1.0',
        profile_id='mysql-native',profile_version=endpoint.profile_version or '9.7.0',
        target_adapter_id='mysql-wire-client',target_adapter_version='26.7.0',
        **{name:getattr(endpoint,name) for name in ('pool_namespace','session_namespace','cache_namespace','diagnostic_namespace')})
    permissions=service.endpoint_service.provider_registry.admitted_permissions(context)
    if 'backup_admin' not in permissions:raise CloneError('Native backup administration permission is unavailable')
    owner=service._principal_id(server)
    store=getattr(service.operation_bus,'store',None)
    if not isinstance(store,JsonOperationStore):raise CloneError('Native clone jobs require durable application storage')
    with service._semantic_lock:
        jobs=getattr(service,'mysql_clone_jobs',None)
        if jobs is None:
            root=current_app.config.get('CDEADMIN_MYSQL_CLONE_RECEIPT_ROOT') or str(store.path.parent/'mysql-native-clone-receipts')
            jobs=service.mysql_clone_jobs=MySQLCloneJobs(str(store.path)+'.mysql-clone',root)
            import atexit
            atexit.register(jobs.close)
    if operation=='list':
        if set(request)-{'offset','limit'}:raise CloneError('Invalid native clone receipt page')
        return jobs.list(owner,endpoint.id,**request)
    if operation in {'status','cancel'}:
        if set(request)!={'job_id'}:raise CloneError('Select one native clone job')
        return (jobs.get if operation=='status' else jobs.cancel)(request['job_id'],owner,endpoint.id)
    if operation=='start':
        reviewed=jobs.load(request.get('job_id'),owner,endpoint.id)
        if reviewed['state']!='reviewed':
            return jobs.start(request,owner,endpoint.id,reviewed['source'],reviewed['configuration'],None)
        selected=reviewed['options']
    elif operation=='review':selected=options(request.get('options'))
    elif operation=='reconcile':
        if set(request)!={'job_id'}:raise CloneError('Select one native clone job')
        reviewed=jobs.load(request['job_id'],owner,endpoint.id);selected={'timeout_seconds':5}
    else:raise CloneError('Native clone action is unavailable')
    transport=None
    try:
        context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
        provider=service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider,MySQLPilotProvider):raise CloneError('Native MySQL clone client is unavailable')
        source,transport=connect(provider,payload['route'],selected['timeout_seconds'] if operation=='start' else 5)
        runtime_limit=current_app.config.get('CDEADMIN_MYSQL_CLONE_MAX_RUNTIME_SECONDS')
        configuration=digest({'registration':MySQLMonitoringHost._configuration(server),'runtime_limit':runtime_limit})
        if operation=='review':return jobs.review(request,owner,endpoint.id,source,configuration,transport.worker,runtime_limit=runtime_limit)
        if operation=='reconcile':return jobs.reconcile(reviewed,source,transport.monitor)
        admitted=transport;transport=None
        return jobs.start(request,owner,endpoint.id,source,configuration,admitted)
    finally:
        if transport is not None:transport.close()
