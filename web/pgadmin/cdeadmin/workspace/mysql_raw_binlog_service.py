"""MySQL raw native closed-log admission on the shared archive lifecycle."""
from copy import deepcopy

from ..providers.mysql_family import mysql_raw_binlog_archives as native
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_binlog_jobs import MySQLBinlogJobs,digest
from .mysql_binlog_service import manager as archive_manager
from .mysql_monitoring_host import MySQLMonitoringHost


class MySQLRawBinlogJobs(MySQLBinlogJobs):
    operation='mysql_closed_raw_binary_log_archive'
    native_verify=staticmethod(native.verify)


def manager(service,server):
    from flask import current_app
    _archives,owner,endpoint,context=archive_manager(service,server)
    with service._semantic_lock:
        jobs=getattr(service,'mysql_raw_binlog_jobs',None)
        if jobs is None:
            store=service.operation_bus.store
            root=current_app.config.get('CDEADMIN_MYSQL_RAW_BINLOG_ROOT') or str(store.path.parent/'mysql-raw-binary-log-archives')
            jobs=service.mysql_raw_binlog_jobs=MySQLRawBinlogJobs(str(store.path)+'.mysql-raw-binlogs',root)
            import atexit
            atexit.register(jobs.close)
        jobs.backup_protection = _archives.backup_protection
    return jobs,owner,endpoint,context


def action(service,server,operation,request):
    from flask import current_app
    from mysql.connector import Error as NativeError
    if not isinstance(request,dict):raise native.BinlogArchiveError('Select a native archive request')
    jobs,owner,endpoint,_context=manager(service,server)
    if operation.startswith('retention_schedule_'):
        host=getattr(service,'mysql_retention_scheduler',None)
        if host is None:raise native.BinlogArchiveError('Durable archive scheduling is unavailable')
        return host.action(server,jobs,owner,endpoint.id,operation,request)
    if operation in {'pin','remove_artifact','removal_reconcile','retention_list','retention_status',
                     'retention_cancel','retention_review','retention_start','retention_reconcile'}:
        from .mysql_archive_retention import action as retention_action
        return retention_action(service,jobs,owner,endpoint.id,operation,request)
    if operation=='list':
        if set(request)-{'offset','limit'}:raise native.BinlogArchiveError('Invalid archive receipt page')
        return jobs.list(owner,endpoint.id,**request)
    if operation in {'status','cancel','reconcile'}:
        if set(request)!={'job_id'}:raise native.BinlogArchiveError('Select one native archive job')
        return {'status':jobs.get,'cancel':jobs.cancel,'reconcile':jobs.reconcile}[operation](request['job_id'],owner,endpoint.id)
    if operation=='files':
        if set(request)-{'job_id','offset','limit'} or 'job_id' not in request:raise native.BinlogArchiveError('Select an archive file page')
        return jobs.files(request['job_id'],owner,endpoint.id,request.get('offset',0),request.get('limit',100))
    if operation=='start':
        reviewed=jobs.load(request.get('job_id'),owner,endpoint.id)
        if (reviewed.get('continuation') or {}).get('stopped_receiver_job_id'):
            from .continuous_binlog_service import action as receiver_action
            return receiver_action(service,server,'tail_start',request,'mysql')
        if reviewed['state']!='reviewed':return jobs.start(request,owner,endpoint.id,{},None)
        selected=reviewed['options']
    elif operation=='review':
        if set(request)!={'options'}:raise native.BinlogArchiveError('Review exact native archive options')
        selected=native.options(request['options'])
    elif operation=='catalog':
        if request:raise native.BinlogArchiveError('Native catalog takes no browser connection route')
        selected=None
    else:raise native.BinlogArchiveError('Native archive action is unavailable')
    client=connection=transport=None
    try:
        context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
        provider=service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider,MySQLPilotProvider):raise native.BinlogArchiveError('Native MySQL client is unavailable')
        client=provider.client
        from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
        route={key:value for key,value in payload['route'].items() if key not in POOL_ARGUMENTS}
        connection=client._connect({'route':{**route,'read_timeout':5,'write_timeout':15}})
        captured=native.capture(connection)
        if operation=='catalog':return captured
        chosen=native.selected_logs(captured,selected)
        scope=jobs.prepare_scope(owner,endpoint.id);program=native.program_identity(client,route,scope)
        runtime_limit=current_app.config.get('CDEADMIN_MYSQL_RAW_BINLOG_MAX_RUNTIME_SECONDS')
        if runtime_limit is not None:
            if type(runtime_limit) is not int or not 1<=runtime_limit<=2147483647:raise native.BinlogArchiveError('Application archive runtime policy is invalid')
            if selected['timeout_seconds'] is None or selected['timeout_seconds']>runtime_limit:
                raise native.BinlogArchiveError('Application policy limits each native archive client to '+str(runtime_limit)+' seconds')
        configuration=digest({'registration':MySQLMonitoringHost._configuration(server),'root':str(jobs.root),'runtime_limit':runtime_limit})
        captured['state']['selected_logs']=deepcopy(chosen)
        if operation=='review':return jobs.review(owner,endpoint.id,selected,captured,configuration,program)
        if reviewed['source_state']['selected_logs']!=chosen:
            raise native.BinlogArchiveError('Native closed-log range changed; prepare a new review')
        transport=native.ArchiveTransport(client,route,native.delegate_credentials(client,route),connection);connection=None
        admitted=transport;transport=None
        return jobs.start(request,owner,endpoint.id,{'source':captured['identity'],'configuration':configuration,'program':program},admitted)
    except NativeError as error:
        raise native.BinlogArchiveError('Native MySQL archive admission failed ('+str(error.errno)+', '+str(error.sqlstate)+')') from None
    finally:
        if connection is not None:client._discard_failed_session(connection)
        if transport is not None:transport.close()
