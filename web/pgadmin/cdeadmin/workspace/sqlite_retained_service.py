"""Original-session DDN admission, with archive reads independent of SQL."""
from ..operations.store import JsonOperationStore
from .firebird_schema_plan import digest
from .sqlite_retained_applications import SQLiteRetainedApplications


def scope(service,server,target):
    endpoint=server.endpoint_profile
    if endpoint is None or (endpoint.profile_id,endpoint.provider_id)!=('sqlite-native','org.cdeadmin.sqlite'):
        raise ValueError('Select a native SQLite registration')
    if not isinstance(target,str) or not target:raise ValueError('Select the original registered SQLite target')
    service.endpoint_service._owned_database_target(endpoint,target)
    context=service.endpoint_service._context(endpoint,())
    permissions=service.endpoint_service.provider_registry.admitted_permissions(context)
    if 'administer' not in permissions:raise ValueError('Native retained DDL receipt permission is unavailable')
    store=getattr(service.operation_bus,'store',None)
    if not isinstance(store,JsonOperationStore):raise ValueError('Original-session DDL requires durable application storage')
    path=str(store.path)+'.sqlite-retained-schema'
    archives=service.__dict__.setdefault('_sqlite_retained_archives',{})
    archive=archives.setdefault(path,SQLiteRetainedApplications(path))
    owner=service._principal_id(server)
    return archive,owner,digest([owner,endpoint.id,target,'org.cdeadmin.sqlite','sqlite-native'])


def serve(service,server,action,data):
    request=data.get('request')
    if not isinstance(request,dict):raise ValueError('Select a retained SQLite DDL request')
    archive,owner,binding=scope(service,server,data.get('database_target_id'))
    operation=request.get('operation')
    if action=='sqlite_retained_schema_receipts':
        if operation=='list' and not set(request)-{'operation','offset','limit'}:
            return archive.list(owner,binding,offset=request.get('offset',0),limit=request.get('limit',25))
        if operation in {'receipt','cancel'} and set(request)=={'operation','review_id'}:
            value=(archive.get if operation=='receipt' else archive.cancel)(request['review_id'],owner,binding)
            return {**value,'archived_read_only':operation=='receipt','native_sql_requested':False}
        if operation=='remove' and set(request)=={'operation','review_id','confirmed'}:
            return archive.remove(request['review_id'],owner,binding,confirmed=request['confirmed'])
        raise ValueError('Select a bounded retained SQLite receipt action')
    fields={'preview':{'operation','baseline','desired','deletions'},
        'review':{'operation','baseline','desired','deletions','execution_sha256'},
        'columns':{'operation','baseline','resource_id','columns'},
        'start':{'operation','review_id','review_digest','confirmed'}}
    if operation not in fields or set(request)-fields[operation]:raise ValueError('Invalid original-session SQLite DDL request')
    if operation=='start':
        if set(request)!=fields['start'] or request.get('confirmed') is not True:
            raise ValueError('Confirm the exact original-session SQLite DDL review')
        value=archive.get(request['review_id'],owner,binding)
        if request['review_digest']!=value['review_digest']:raise ValueError('Retained review fingerprint does not match')
        if value['state']!='reviewed':return value
    context,_endpoint,_root=service.endpoint_service.workspace(server,database_target_id=data.get('database_target_id'))
    return service.studio_service.sqlite_retained_schema_action(context,data.get('session_id'),request,archive,
        owner,binding,data.get('database_target_id'))
