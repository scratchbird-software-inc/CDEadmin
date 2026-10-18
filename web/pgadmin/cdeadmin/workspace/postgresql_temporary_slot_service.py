"""Authenticated database/owner scoped temporary-slot resources and requests."""
import hashlib
from pathlib import Path
import socket
import sys
import time

from ..operations.store import JsonOperationStore
from ..providers.postgresql import large_object_files as private_sql
from ..providers.postgresql.connection_target import database_oid
from ..providers.postgresql.provider import PostgreSQLProvider
from ..providers.postgresql.temporary_slots import TemporarySlotError,options
from .mysql_binlog_jobs import digest
from .postgresql_continuity_service import artifact_context
from .postgresql_monitoring_host import PostgreSQLMonitoringHost
from .postgresql_temporary_slot_jobs import TemporarySlotResources,TemporarySlotTransport


def program():
    from ..providers.postgresql import temporary_slots
    return {'kind':'native-postgresql-temporary-slot-resource','adapter_sha256':hashlib.sha256(Path(temporary_slots.__file__).read_bytes()).hexdigest(),
        'channel_sha256':hashlib.sha256(Path(__file__).with_name('postgresql_temporary_slot_jobs.py').read_bytes()).hexdigest(),
        'execution_host':{'kind':'application-host','hostname':socket.gethostname(),'platform':sys.platform}}


def authorize(service,server):
    if not PostgreSQLMonitoringHost._native_registration(server):raise TemporarySlotError('Select a native PostgreSQL registration')
    permissions=service.endpoint_service.provider_registry.admitted_permissions(artifact_context(server))
    if 'backup_admin' not in permissions:raise TemporarySlotError('Native backup/replication administration permission is unavailable')
    return service._principal_id(server),server.endpoint_profile.id


def manager(service,server,target):
    from flask import current_app
    owner,endpoint=authorize(service,server)
    if database_oid(target) is None:raise TemporarySlotError('Select an explicit PostgreSQL database target')
    store=getattr(service.operation_bus,'store',None)
    if not isinstance(store,JsonOperationStore):raise TemporarySlotError('Temporary-slot resources require durable application storage')
    key=hashlib.sha256((endpoint+'\0'+target).encode('utf8')).hexdigest()
    with service._semantic_lock:
        managers=getattr(service,'postgresql_temporary_slot_resources',None)
        if managers is None:managers=service.postgresql_temporary_slot_resources={}
        jobs=managers.get(key)
        if jobs is None:
            root=current_app.config.get('CDEADMIN_POSTGRESQL_TEMPORARY_SLOT_ROOT') or str(store.path.parent/'postgresql-temporary-slots')
            jobs=managers[key]=TemporarySlotResources(str(store.path)+'.postgresql-temporary-slots.'+key,Path(root)/key)
            import atexit
            atexit.register(jobs.close)
    return jobs,owner,endpoint


def action(service,server,operation,request):
    from flask import current_app
    if not isinstance(request,dict):raise TemporarySlotError('Select a temporary-slot resource request')
    if operation=='databases':
        authorize(service,server)
        if set(request)-{'database_target_id'}:raise TemporarySlotError('Select the native database catalog')
        return service.endpoint_service.database_catalog(server)
    fields=dict(request);target=fields.pop('database_target_id',None)
    jobs,owner,endpoint=manager(service,server,target)
    if operation=='list':
        if set(fields)-{'offset','limit'}:raise TemporarySlotError('Select a temporary resource receipt page')
        return jobs.list(owner,endpoint,**fields)
    if operation=='status':
        if set(fields)!={'job_id'}:raise TemporarySlotError('Select one temporary-slot resource')
        return jobs.get(fields['job_id'],owner,endpoint)
    if operation=='release':
        if set(fields)!={'job_id','confirmation'} or fields['confirmation']!=fields['job_id']:
            raise TemporarySlotError('Confirm release of this resource and all its temporary slots')
        return jobs.cancel(fields['job_id'],owner,endpoint)
    if operation=='reconcile':
        if set(fields)!={'job_id'}:raise TemporarySlotError('Select one temporary-slot resource cleanup observation')
        return reconcile(service,server,target,jobs,jobs.load(fields['job_id'],owner,endpoint))
    if operation in {'inventory','command_status','command_list','command_cancel','command_review','command_start'}:
        resource=jobs.load(fields.get('resource_id'),owner,endpoint);commands=jobs.commands(resource)
        remaining={key:value for key,value in fields.items() if key!='resource_id'}
        if operation in {'inventory','command_review','command_start'} and resource['program']!=program():
            raise TemporarySlotError('The retained resource uses another application-host adapter; release it before opening a new resource')
        if operation=='inventory':
            if set(remaining)-{'offset','limit'}:raise TemporarySlotError('Select a temporary-slot catalog page')
            return jobs.queue_catalog(resource['job_id'],owner,endpoint,**remaining)
        if operation=='command_list':
            if set(remaining)-{'offset','limit'}:raise TemporarySlotError('Select a native command receipt page')
            return commands.list(owner,endpoint,**remaining)
        if operation in {'command_status','command_cancel'}:
            if set(remaining)!={'job_id'}:raise TemporarySlotError('Select one temporary-slot command receipt')
            return commands.get(remaining['job_id'],owner,endpoint) if operation=='command_status' else jobs.cancel_command(resource['job_id'],owner,endpoint,remaining['job_id'])
        if operation=='command_start':return jobs.queue_execute(resource['job_id'],owner,endpoint,remaining)
        if set(remaining)!={'operation','options'}:raise TemporarySlotError('Review exact native temporary-slot command options')
        selected=options(remaining['operation'],remaining['options'])
        limit=current_app.config.get('CDEADMIN_POSTGRESQL_CONTINUITY_MAX_RUNTIME_SECONDS')
        if limit is not None and (type(limit) is not int or limit<1 or selected['timeout_seconds'] is None or selected['timeout_seconds']>limit):
            raise TemporarySlotError('Application policy requires a bounded native slot command duration')
        return jobs.queue_review(resource['job_id'],owner,endpoint,remaining['operation'],selected)
    if operation=='review':
        if set(fields)!={'options'} or not isinstance(fields['options'],dict) or set(fields['options'])!={'max_lifetime_seconds'}:
            raise TemporarySlotError('Review the exact owned resource lifetime')
        selected=fields['options'];lifetime=selected['max_lifetime_seconds']
    elif operation=='start':
        reviewed=jobs.load(fields.get('job_id'),owner,endpoint)
        if reviewed['state']!='reviewed':return jobs.start(fields,owner,endpoint,{},None)
        selected=reviewed['options'];lifetime=selected['max_lifetime_seconds']
    else:raise TemporarySlotError('Temporary-slot resource action is unavailable')
    if lifetime is not None and (type(lifetime) is not int or not 1<=lifetime<=2147483647):raise TemporarySlotError('Select a positive resource lifetime or no deadline')
    limit=current_app.config.get('CDEADMIN_POSTGRESQL_TEMPORARY_SLOT_MAX_LIFETIME_SECONDS')
    if limit is not None and (type(limit) is not int or limit<1 or lifetime is None or lifetime>limit):
        raise TemporarySlotError('Application policy requires a bounded temporary-slot resource lifetime')
    from psycopg._capabilities import capabilities
    if not capabilities.has_cancel_safe():raise TemporarySlotError('Temporary-slot resources require libpq17 or later for bounded cancellation')
    transport=None
    try:
        context,payload,_root=service.endpoint_service.workspace(server,database_target_id=target)
        provider=service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider,PostgreSQLProvider):raise TemporarySlotError('Select a native PostgreSQL provider')
        identity,transport=private_sql.capture(provider,payload['route'],server,application_name='ScratchRobin temporary-slot admission')
        if identity['database_oid']!=str(database_oid(target)):raise TemporarySlotError('The retained resource admission reached another database')
        source={'sql_identity':identity};native_program=program()
        configuration=digest({'registration':PostgreSQLMonitoringHost._configuration(server),'database_target_id':target,'root':str(jobs.root),'lifetime_limit':limit})
        if operation=='review':return jobs.review(owner,endpoint,selected,{'identity':source,'state':{}},configuration,native_program)
        admitted=transport;transport=None
        return jobs.start(fields,owner,endpoint,{'source':source,'configuration':configuration,'program':native_program},TemporarySlotTransport(admitted))
    finally:
        if transport is not None:transport.close()


def reconcile(service,server,target,jobs,record):
    """Observe original backend/slot cleanup; preserve every command outcome."""
    if not record.get('backend_pid'):return jobs.get(record['job_id'],record['owner'],record['endpoint_id'])
    if not record.get('worker_io_closed'):
        import psutil
        if record['execution_host']['hostname']!=socket.gethostname():raise TemporarySlotError('Confirm resource-owner I/O on its recorded application host')
        pid,created=record.get('worker_identity',(None,None))
        try:alive=pid is not None and psutil.Process(pid).create_time()==created
        except psutil.NoSuchProcess:alive=False
        except psutil.Error:raise TemporarySlotError('Resource-owner process termination is unconfirmed') from None
        if alive:raise TemporarySlotError('Release this resource and wait for its owner worker to close I/O before checking backend cleanup')
    transport=None
    try:
        context,payload,_root=service.endpoint_service.workspace(server,database_target_id=target)
        provider=service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider,PostgreSQLProvider):raise TemporarySlotError('Select a native PostgreSQL provider')
        source,transport=private_sql.capture(provider,payload['route'],server,application_name='ScratchRobin temporary-slot cleanup observation')
        original=record['source']['sql_identity']
        if any(source[key]!=value for key,value in original.items() if key not in {'authenticated_principal','effective_principal'}):
            raise TemporarySlotError('The cleanup observer reached another native server or database identity')
        with transport.parameters() as parameters:
            connection=private_sql.attach(parameters,source)
            try:
                with private_sql.cursor(connection) as query:
                    query.execute('SET statement_timeout=5000')
                    query.execute('SELECT EXTRACT(EPOCH FROM backend_start)::pg_catalog.text,datid::pg_catalog.text,usename,application_name FROM pg_catalog.pg_stat_activity WHERE pid=%s::pg_catalog.int4',(record['backend_pid'],))
                    backend=query.fetchone()
                    query.execute('SELECT pg_catalog.count(*) FROM pg_catalog.pg_replication_slots WHERE temporary AND active_pid=%s::pg_catalog.int4',(record['backend_pid'],))
                    remaining=int(query.fetchone()[0])
            finally:connection.close()
        reused=bool(backend and backend[0] is not None and record.get('backend_started_epoch') is not None and backend[0]!=record['backend_started_epoch'])
        ended=backend is None or reused
        observed={'observed_at':time.time(),'observer_identity':source,'backend_pid':record['backend_pid'],
            'original_backend_started_epoch':record.get('backend_started_epoch'),
            'current_backend_started_epoch':backend[0] if backend else None,'pid_reused':reused,
            'original_backend_termination_observed':ended,'current_pid_temporary_slot_count':remaining,
            'temporary_slot_cleanup_observed':ended and (reused or remaining==0),
            'original_command_outcomes_inferred':False}
        jobs.update(record,backend_cleanup_observation=observed)
        return jobs.get(record['job_id'],record['owner'],record['endpoint_id'])
    finally:
        if transport is not None:transport.close()
