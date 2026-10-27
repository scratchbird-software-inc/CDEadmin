"""Native search admission, credential ownership and bounded result navigation."""
import atexit

from ..providers.mysql_family import mysql_content_search as native
from .mysql_content_search import SearchJobs, navigate
from .mysql_monitoring_host import MySQLMonitoringHost


def selected_tables(value):
    if not isinstance(value, list) or not 1<=len(value)<=64:
        raise native.SearchError('Select 1–64 native tables')
    seen, total, result = set(), 0, []
    for item in value:
        if not isinstance(item, dict) or set(item)!={'table_name','fingerprint','columns'}:
            raise native.SearchError('Select observed native table and column identities')
        table = native.name(item['table_name'])
        columns = item['columns']
        if table in seen or not isinstance(columns,list) or not columns or len(columns)!=len(set(columns)):
            raise native.SearchError('Select distinct native tables and nonempty column lists')
        for name in columns: native.name(name)
        if not isinstance(item['fingerprint'],str) or len(item['fingerprint'])!=64:
            raise native.SearchError('Rediscover the selected native table structure')
        seen.add(table);total += len(columns)
        result.append({'table_name':table,'fingerprint':item['fingerprint'],'columns':list(columns)})
    if total>256:
        raise native.SearchError('One private search admits at most 256 selected columns')
    return result


def action(service, server, operation, request):
    from flask import current_app
    if not isinstance(request,dict):
        raise native.SearchError('A native content-search request is required')
    endpoint = server.endpoint_profile
    if endpoint is None or endpoint.profile_id!='mysql-native' or endpoint.provider_id!='org.cdeadmin.mysql':
        raise native.SearchError('Select a native MySQL registration')
    target = request.get('database_target_id')
    context, payload, _ = service.endpoint_service.workspace(server,database_target_id=target)
    registry = service.endpoint_service.provider_registry
    if not {'data_read','execute'} <= registry.admitted_permissions(context):
        raise native.SearchError('Native content search requires data-read and execution authority')
    binding = registry.resolve(context)
    owner, configuration = service._principal_id(server), MySQLMonitoringHost._configuration(server)
    scope = owner, server.id, target, configuration
    allowed = {'databases': {'offset'}, 'tables': {'schema_name','offset'},
        'columns': {'schema_name','table_name','offset'},
        'start': {'schema_name','tables','options','confirmed'}, 'status': {'job_id'},
        'cancel': {'job_id'}, 'forget': {'job_id'}, 'row': {'job_id','match_id'}}
    if operation not in allowed or set(request)-({'database_target_id'}|allowed[operation]):
        raise native.SearchError('Unsupported native content-search request')
    app, sid = current_app._get_current_object(), server.id
    def authorize():
        from pgadmin.model import Server, User
        with app.app_context():
            live = Server.query.filter_by(id=sid,user_id=owner).first()
            if (live is None or User.query.filter_by(id=owner,active=True).first() is None or
                    MySQLMonitoringHost._configuration(live)!=configuration or
                    not {'data_read','execute'}<=registry.admitted_permissions(context)):
                raise native.SearchError('Search owner, registration or admission changed')
    with service._semantic_lock:
        jobs = getattr(service,'mysql_content_search_jobs',None)
        if jobs is None:
            jobs = service.mysql_content_search_jobs = SearchJobs()
            atexit.register(jobs.close)
    if operation in {'status','cancel','forget','row'}:
        if not isinstance(request.get('job_id'),str):
            raise native.SearchError('Select one private native search')
        job = jobs.get(scope,request['job_id'])
        if operation=='forget':return jobs.forget(scope,job.id)
        if operation=='cancel':job.stop()
        if operation!='row':return job.snapshot()
        observer = native.Observer(binding.permissions,payload['route'])
        try:return navigate(observer,job,request.get('match_id'))
        finally:observer.close()
    schema = request.get('schema_name')
    if target is not None:
        if operation=='databases':
            return {'rows':[{'name':payload['route']['database']}],'next_offset':None,'visibility':'registered database target'}
        if schema!=payload['route'].get('database'):
            raise native.SearchError('Search scope differs from the registered database target')
    if operation!='databases':native.name(schema)
    if operation=='start':
        if request.get('confirmed') is not True:
            raise native.SearchError('Explicit private table-value search consent is required')
        tables, selected = selected_tables(request.get('tables')), native.options(request.get('options'))
    observer, control = None, None
    try:
        observer = native.Observer(binding.permissions,payload['route'])
        if operation=='databases':return native.databases(observer,request.get('offset',0))
        if operation=='tables':return native.tables(observer,schema,request.get('offset',0))
        if operation=='columns':
            offset = request.get('offset',0);native.page(offset)
            value = native.describe(observer,schema,request.get('table_name'))
            rows = value.pop('columns');value.pop('indexes')
            return {**value,'rows':rows[offset:offset+128], 'next_offset':offset+128 if len(rows)>offset+128 else None,
                'visibility':'native permission-filtered columns; SELECT remains authoritative'}
        control = native.Observer(binding.permissions,payload['route'])
        if any(observer.identity[k]!=control.identity[k] for k in ('server_uuid','account','active_role')):
            raise native.SearchError('Worker and cancellation observer reached different native identities')
        result = jobs.start(scope,observer,control,schema,tables,selected,authorize)
        observer = control = None
        return result
    finally:
        if control is not None:control.close()
        if observer is not None:observer.close()
