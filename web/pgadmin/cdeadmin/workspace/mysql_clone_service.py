"""Native clone admission with offline, owner-bound durable receipts."""
from ..core import EndpointContext
from ..operations.store import JsonOperationStore
from ..providers.mysql_family.mysql_clone import CloneError, capture, configure, connect, donor_policy, options, seal_password
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_clone_jobs import MySQLCloneJobs, digest
from .mysql_monitoring_host import MySQLMonitoringHost


def donors(owner,request):
    from pgadmin.model import Server,EndpointProfile
    if set(request)-{'offset','limit'}:raise CloneError('Invalid native donor page')
    offset,limit=request.get('offset',0),request.get('limit',25)
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
        raise CloneError('Invalid native donor page')
    query=Server.query.join(Server.endpoint_profile).filter(Server.user_id==owner,
        EndpointProfile.profile_id=='mysql-native',EndpointProfile.provider_id=='org.cdeadmin.mysql').order_by(Server.id)
    return {'donors':[{'server_id':row.id,'name':row.name,'host':row.host,'port':row.port} for row in query.offset(offset).limit(limit)],
            'offset':offset,'limit':limit,'total':query.count()}


def attach_donor(service,owner,selected,source,transport,*,delegate):
    from pgadmin.model import Server,User
    from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
    server=Server.query.filter_by(id=selected['server_id'],user_id=owner).first()
    if (server is None or User.query.filter_by(id=owner,active=True).first() is None or
        server.endpoint_profile is None or server.endpoint_profile.profile_id!='mysql-native' or
        server.endpoint_profile.provider_id!='org.cdeadmin.mysql'):
        raise CloneError('Native MySQL donor is unavailable for this owner')
    context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
    if 'backup_admin' not in service.endpoint_service.provider_registry.admitted_permissions(context):
        raise CloneError('Native donor backup administration permission is unavailable')
    provider=service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider,MySQLPilotProvider):raise CloneError('Native MySQL donor client is unavailable')
    route={key:value for key,value in payload['route'].items() if key not in POOL_ARGUMENTS}
    username=donor_policy(route,selected,source)
    transport.donor_client=provider.client
    from ..providers.mysql_family.mysql_log_purge import private_connection
    transport.donor=private_connection(provider.client,{**route,'read_timeout':5,'write_timeout':15})
    configure(transport.donor)
    native=capture(transport.donor)
    if native['server_uuid']==source['server_uuid']:
        raise CloneError('A remote clone requires a different native donor server')
    transport.donor_identity={'server_id':server.id,'endpoint_id':server.endpoint_profile.id,
        'username':username,'native_identity':native,'native_protocol_source':selected['host']+':'+str(selected['port']),
        'native_protocol_uuid_attested':False}
    if delegate:
        def seal(values):
            transport.password=seal_password(values,source['system_charset'])
        provider.client._tool_secrets(route,seal)
    return MySQLMonitoringHost._configuration(server)


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
    if operation=='donors':return donors(owner,request)
    store=getattr(service.operation_bus,'store',None)
    if not isinstance(store,JsonOperationStore):raise CloneError('Native clone jobs require durable application storage')
    with service._semantic_lock:
        jobs=getattr(service,'mysql_clone_jobs',None)
        if jobs is None:
            root=current_app.config.get('CDEADMIN_MYSQL_CLONE_RECEIPT_ROOT') or str(store.path.parent/'mysql-native-clone-receipts')
            jobs=service.mysql_clone_jobs=MySQLCloneJobs(str(store.path)+'.mysql-clone',root)
            import atexit
            atexit.register(jobs.close)
    from .mysql_backup_protection import manager as backup_protection
    jobs.backup_protection=backup_protection(service)
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
        donor_configuration=None
        if selected.get('donor'):
            donor_configuration=attach_donor(service,owner,selected['donor'],source,transport,delegate=operation=='start')
        configuration=digest({'registration':MySQLMonitoringHost._configuration(server),'runtime_limit':runtime_limit,
                              'donor_registration':donor_configuration})
        if operation=='review':return jobs.review(request,owner,endpoint.id,source,configuration,transport.worker,runtime_limit=runtime_limit,donor=transport.donor_identity)
        if operation=='reconcile':return jobs.reconcile(reviewed,source,transport.monitor)
        admitted=transport;transport=None
        return jobs.start(request,owner,endpoint.id,source,configuration,admitted)
    finally:
        if transport is not None:transport.close()
