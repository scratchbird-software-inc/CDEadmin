"""Independent owner-scoped native MySQL comparison admission."""
import atexit
from copy import deepcopy
from pathlib import Path

from ..providers.mysql_family import mysql_drift as native
from ..providers.mysql_family import mysql_content_search as catalog
from ..providers.mysql_family.mysql_catalog import identifier
from .mysql_drift_jobs import DriftJobs
from .mysql_monitoring_host import MySQLMonitoringHost


def action(service,server,operation,request):
    from flask import current_app
    from pgadmin.model import Server,User
    from ..operations.store import JsonOperationStore
    from .mysql_online_replicas import available
    if not isinstance(request,dict):raise native.Error('Select a native full-table comparison request')
    owner=service._principal_id(server)
    if operation=='peers':
        if set(request)-{'database_target_id','peer_endpoint_id','offset'}:raise native.Error('Select one registered native peer page')
        page=available(owner,request.get('offset',0))
        selected={s.id:s for s in Server.query.filter(Server.id.in_([r['endpoint_id'] for r in page['rows']]),Server.user_id==owner).all()}
        for row in page['rows']:
            endpoint=selected[row['endpoint_id']];row['label']+=' / '+str(endpoint.host or 'local')+':'+str(endpoint.port or 3306)
        return page
    allowed={'databases':{'side','offset'},'tables':{'side','schema_name','offset'},'describe':{'side','schema_name','table_name'},
        'start':{'source_schema','target_schema','tables','options','confirmed'},'status':{'job_id'},'cancel':{'job_id'},'forget':{'job_id'}}
    common={'database_target_id','peer_endpoint_id','peer_database_target_id'}
    if operation not in allowed or set(request)-(common|allowed[operation]):raise native.Error('Unsupported native data-drift request')
    peer_id=request.get('peer_endpoint_id')
    if type(peer_id) is not int or peer_id<=0:raise native.Error('Select a registered native comparison endpoint')
    peer=Server.query.filter_by(id=peer_id,user_id=owner).first()
    if peer is None:raise native.Error('The selected comparison endpoint is unavailable for this owner')
    endpoints=[server,peer];targets=[request.get('database_target_id'),request.get('peer_database_target_id')]
    contexts=[];bindings=[];routes=[];configurations=[]
    for endpoint,target in zip(endpoints,targets):
        if endpoint.endpoint_profile is None or endpoint.endpoint_profile.profile_id!='mysql-native':raise native.Error('Select two native MySQL registrations')
        context,payload,_=service.endpoint_service.workspace(endpoint,database_target_id=target)
        registry=service.endpoint_service.provider_registry
        if not {'data_read','execute','administer'}<=registry.admitted_permissions(context):
            raise native.Error('Native comparison requires data-read, execution and administration admission on both scopes')
        binding=registry.resolve(context);bindings.append(binding);contexts.append(context)
        route=deepcopy(payload['route'])
        for name in ('pool_name','pool_size','pool_reset_session','init_command'):route.pop(name,None)
        routes.append(route);configurations.append(MySQLMonitoringHost._configuration(endpoint))
    scope=owner,server.id,targets[0],configurations[0],peer.id,targets[1],configurations[1]
    app=current_app._get_current_object();ids=[endpoint.id for endpoint in endpoints]
    def authorize():
        with app.app_context():
            if User.query.filter_by(id=owner,active=True).first() is None:raise native.Error('Comparison owner is no longer active')
            for sid,configuration,context in zip(ids,configurations,contexts):
                endpoint=Server.query.filter_by(id=sid,user_id=owner).first()
                if endpoint is None or MySQLMonitoringHost._configuration(endpoint)!=configuration or not {'data_read','execute','administer'}<=registry.admitted_permissions(context):
                    raise native.Error('Comparison registration or admission changed')
    store=service.operation_bus.store
    if not isinstance(store,JsonOperationStore):raise native.Error('Private comparisons require the application data workspace')
    with service._semantic_lock:
        jobs=getattr(service,'mysql_drift_jobs',None)
        if jobs is None:
            jobs=service.mysql_drift_jobs=DriftJobs(Path(str(store.path)+'.mysql-drift'));atexit.register(jobs.close)
    if operation in {'status','cancel','forget'}:
        job=jobs.get(scope,request.get('job_id'))
        if operation=='cancel':job.stop()
        if operation=='forget':
            if not job.closed:raise native.Error('Cancel and wait for native release before clearing a comparison')
            with jobs.lock:jobs.jobs.pop(job.id,None)
            return {'forgotten':True,'job_id':job.id}
        return job.snapshot()
    side=request.get('side')
    if operation!='start' and side not in {'source','target'}:raise native.Error('Select a source or target observation')
    def schema_name(index,value):
        catalog.name(value)
        if targets[index] is not None and value!=routes[index].get('database'):raise native.Error('Comparison database differs from its registered database target')
        return value
    selected=native.options(request.get('options')) if operation=='start' else {'seconds':5}
    if operation=='start':
        if request.get('confirmed') is not True:raise native.Error('Explicit consent to native server read locks and private comparison is required')
        tables=native.selections(request.get('tables'))
        schemas=[schema_name(0,request.get('source_schema')),schema_name(1,request.get('target_schema'))]
    observers=[];controls=[]
    try:
        def open_observer(index,control=False):
            client=bindings[index].instance.client
            role=routes[index].get('role')
            connection=client._connect({'route':{**routes[index],**({'database':None} if role else {}),'autocommit':True,'connection_timeout':5,
                'read_timeout':5 if control else selected['seconds']+10,'write_timeout':5,'get_warnings':False,'raise_on_warnings':False}})
            try:
                if role:
                    with connection.cursor() as cursor:cursor.execute('SET ROLE '+identifier(role))
                    if routes[index].get('database'):connection.database=routes[index]['database']
                return native.Observer(connection,client._discard_failed_session,5 if control else selected['seconds'])
            except BaseException:
                client._discard_failed_session(connection);raise
        if operation!='start':
            index=0 if side=='source' else 1;observer=open_observer(index);observers.append(observer)
            if operation=='databases':
                return {'rows':[{'name':routes[index]['database']}],'next_offset':None,'visibility':'registered database target'} if targets[index] is not None else catalog.databases(observer,request.get('offset',0))
            schema=schema_name(index,request.get('schema_name'))
            if operation=='tables':return catalog.tables(observer,schema,request.get('offset',0))
            source=native.describe(observer,schema,request.get('table_name'))
            return {k:source[k] for k in ('schema_name','table_name','engine','fingerprint','key','server_uuid')}|{
                'column_count':len(source['columns']),'column_shape_sha256':catalog.digest(native.shape(source))}
        for index in (0,1):
            observers.append(open_observer(index));controls.append(open_observer(index,True))
            if any(observers[-1].identity[k]!=controls[-1].identity[k] for k in ('server_uuid','account','active_role')):
                raise native.Error('Native scan and cancellation connections reached different scopes')
        result=jobs.start(scope,observers,controls,schemas,tables,selected,authorize)
        observers=controls=[]
        return result
    finally:
        for observer in [*observers,*controls]:observer.close()
