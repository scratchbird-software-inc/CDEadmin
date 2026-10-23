"""Native spatial reads use ordinary owner admission and independent sessions."""
import threading

from ..providers.mysql_family import mysql_spatial as native
from ..providers.mysql_family import mysql_content_search as catalog
from .mysql_monitoring_host import MySQLMonitoringHost


def action(service, server, operation, request):
    from pgadmin.model import Server, User
    if not isinstance(request,dict):raise native.Error('Select one native spatial inspection scope')
    endpoint = server.endpoint_profile
    if endpoint is None or endpoint.profile_id!='mysql-native' or endpoint.provider_id!='org.cdeadmin.mysql':
        raise native.Error('Spatial inspection requires a native MySQL registration')
    allowed = {'databases':{'offset'},'tables':{'schema_name','offset'},'columns':{'schema_name','table_name','offset'},
        'read':{'schema_name','table_name','column_name','fingerprint','options','confirmed'}}
    if operation not in allowed or set(request)-({'database_target_id'}|allowed[operation]):raise native.Error('Unsupported spatial inspection request')
    target = request.get('database_target_id')
    context, payload, _ = service.endpoint_service.workspace(server,database_target_id=target)
    registry = service.endpoint_service.provider_registry
    def authorize():
        live = Server.query.filter_by(id=server.id,user_id=owner).first()
        if (live is None or User.query.filter_by(id=owner,active=True).first() is None or
                MySQLMonitoringHost._configuration(live)!=configuration or
                not {'data_read','execute'}<=registry.admitted_permissions(context)):
            raise native.Error('Spatial inspection owner, registration or admission changed')
    owner, configuration = service._principal_id(server), MySQLMonitoringHost._configuration(server)
    authorize()
    schema = request.get('schema_name')
    if target is not None:
        if operation=='databases':return {'rows':[{'name':payload['route']['database']}],'next_offset':None}
        if schema!=payload['route'].get('database'):raise native.Error('Spatial database differs from the registered target')
    if operation!='databases':catalog.name(schema)
    selected = None
    if operation=='read':
        if request.get('confirmed') is not True:raise native.Error('Explicit private spatial data inspection consent is required')
        catalog.name(request.get('table_name'));catalog.name(request.get('column_name'))
        selected = native.options(request.get('options'))
    binding = registry.resolve(context)
    with service._semantic_lock:
        slots = getattr(service,'mysql_spatial_slots',None)
        if slots is None:slots=service.mysql_spatial_slots=threading.BoundedSemaphore(4)
    if not slots.acquire(blocking=False):raise native.Error('Four spatial reads are already active; wait for native release')
    observer = None
    try:
        observer = catalog.Observer(binding.permissions,payload['route'])
        if operation=='databases':result=catalog.databases(observer,request.get('offset',0))
        elif operation=='tables':result=catalog.tables(observer,schema,request.get('offset',0))
        elif operation=='columns':
            offset=request.get('offset',0);catalog.page(offset)
            source=native.describe(observer,schema,request.get('table_name'));rows=source['spatial_columns']
            result={k:source[k] for k in ('fingerprint','schema_name','table_name','server_uuid','engine')}
            result.update(rows=rows[offset:offset+128],next_offset=offset+128 if len(rows)>offset+128 else None)
        else:result=native.inspect(observer,schema,request['table_name'],request['column_name'],request.get('fingerprint'),selected)
        authorize()
        return result
    finally:
        try:
            if observer is not None:observer.close()
        finally:slots.release()
