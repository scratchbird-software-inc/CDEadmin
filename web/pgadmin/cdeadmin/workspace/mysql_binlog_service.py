"""Registered native-source admission and private archive execution grants."""
from copy import deepcopy

from ..core import EndpointContext
from ..operations.store import JsonOperationStore
from ..providers.mysql_family.mysql_binlog_archives import (
    BinlogArchiveError,capture,delegate_credentials,options,program_identity,rows,run_dump,stage_continuation,verify)
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_binlog_jobs import MySQLBinlogJobs,digest
from .mysql_monitoring_host import MySQLMonitoringHost


class ArchiveTransport:
    def __init__(self,client,route,credentials,workspace,since_directory=None,continuation=None,continuation_artifact=None):
        self.client,self.route,self.credentials,self.workspace=client,route,credentials,workspace
        self.since_directory,self.continuation=since_directory,continuation
        self.continuation_artifact=continuation_artifact

    def close(self):
        if self.credentials is not None:self.credentials.close();self.credentials=None

    def execute(self,record,directory,cancel,progress):
        staged=None;cleanup_safe=True
        try:
            if self.since_directory is not None:
                previous=verify(self.since_directory,record['source'],cancel=cancel)
                if digest(previous)!=record['continuation']['artifact_digest']:
                    raise BinlogArchiveError('Native archive continuation bytes changed')
                staged=stage_continuation(self.since_directory,directory/'continuation',previous,record['source'],cancel=cancel)
            return run_dump(self.client,self.route,self.credentials,record['source'],record['options'],directory/'archive',
                directory,since_directory=staged,expected_program=record['program'],cancel=cancel,progress=progress)
        except BaseException as error:
            observation=getattr(error,'observation',None) or getattr(error,'process_observation',{})
            cleanup_safe=observation.get('process_observation',{}).get('cleanup_confirmed') is not False
            raise
        finally:
            import shutil
            if cleanup_safe:shutil.rmtree(directory/'continuation',ignore_errors=True)


def _public_capture(captured):
    result=deepcopy(captured)
    for row in result['logs']:
        for key in ('File_size',):
            if row.get(key) is not None:row[key]=str(row[key])
    if result['current'] is not None:
        for key in ('Position',):
            if result['current'].get(key) is not None:result['current'][key]=str(result['current'][key])
    return result


def manager(service,server,family='mysql'):
    from flask import current_app
    endpoint=server.endpoint_profile
    if family not in {'mysql','mariadb'}:raise BinlogArchiveError('Native archive family is unavailable')
    if endpoint is None or endpoint.profile_id!=family+'-native' or endpoint.provider_id!='org.cdeadmin.'+family:
        raise BinlogArchiveError('Select a native '+family+' registration')
    context=EndpointContext(endpoint_id=endpoint.id,mode='legacy_native',experience_family=family,
        provider_id=endpoint.provider_id,provider_version=endpoint.provider_version or '0.1.0',
        profile_id=endpoint.profile_id,profile_version=endpoint.profile_version or ('9.7.0' if family=='mysql' else '12.2.2'),
        target_adapter_id=endpoint.target_adapter_id,target_adapter_version=endpoint.target_adapter_version or '0.1.0',
        **{name:getattr(endpoint,name) for name in ('pool_namespace','session_namespace','cache_namespace','diagnostic_namespace')})
    if 'backup_admin' not in service.endpoint_service.provider_registry.admitted_permissions(context):
        raise BinlogArchiveError('Native archive administration permission is unavailable')
    owner=service._principal_id(server);store=getattr(service.operation_bus,'store',None)
    if not isinstance(store,JsonOperationStore):raise BinlogArchiveError('Native archives require durable application storage')
    with service._semantic_lock:
        attribute=family+'_binlog_jobs';jobs=getattr(service,attribute,None)
        if jobs is None:
            cls=MySQLBinlogJobs
            if family=='mariadb':
                from .mariadb_binlog_service import MariaDBBinlogJobs
                cls=MariaDBBinlogJobs
            root=current_app.config.get('CDEADMIN_'+family.upper()+'_BINLOG_ROOT') or str(store.path.parent/(family+'-binary-log-archives'))
            jobs=cls(str(store.path)+'.'+family+'-binlogs',root);setattr(service,attribute,jobs)
            import atexit
            atexit.register(jobs.close)
    return jobs,owner,endpoint,context


def action(service,server,operation,request):
    from flask import current_app
    from mysql.connector import Error as NativeError
    if not isinstance(request,dict):raise BinlogArchiveError('A native binary-log archive request is required')
    jobs,owner,endpoint,context=manager(service,server)
    if operation in {'pin','remove_artifact','removal_reconcile','retention_list','retention_status',
                     'retention_cancel','retention_review','retention_start','retention_reconcile'}:
        from .mysql_archive_retention import action as retention_action
        return retention_action(service,jobs,owner,endpoint.id,operation,request)
    if operation=='list':
        if set(request)-{'offset','limit'}:raise BinlogArchiveError('Invalid native archive page')
        return jobs.list(owner,endpoint.id,**request)
    if operation in {'status','cancel','reconcile'}:
        if set(request)!={'job_id'}:raise BinlogArchiveError('Select one native archive job')
        return {'status':jobs.get,'cancel':jobs.cancel,'reconcile':jobs.reconcile}[operation](request['job_id'],owner,endpoint.id)
    if operation=='files':
        if set(request)-{'job_id','offset','limit'} or 'job_id' not in request:raise BinlogArchiveError('Select a native archive file page')
        return jobs.files(request['job_id'],owner,endpoint.id,request.get('offset',0),request.get('limit',100))
    if operation=='start':
        reviewed=jobs.load(request.get('job_id'),owner,endpoint.id)
        if reviewed['state']!='reviewed':return jobs.start(request,owner,endpoint.id,{},None)
        selected=reviewed['options']
    elif operation=='review':
        if set(request)!={'options'}:raise BinlogArchiveError('Review exact native archive options')
        selected=options(request['options'])
    elif operation=='catalog':
        if request:raise BinlogArchiveError('Native binary-log catalog takes no browser route')
        selected=None
    else:raise BinlogArchiveError('Native binary-log archive action is unavailable')
    connection=transport=None;client=None
    try:
        context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
        provider=service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider,MySQLPilotProvider):raise BinlogArchiveError('Native MySQL archive client is unavailable')
        from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
        route={key:value for key,value in payload['route'].items() if key not in POOL_ARGUMENTS}
        client=provider.client;connection=client._connect({'route':{**route,'read_timeout':5,'write_timeout':15}})
        captured=capture(connection)
        if operation=='catalog':return _public_capture(captured)
        if captured['status']!='available' or captured['state']['gtid_mode'] not in {'ON','ON_PERMISSIVE'}:
            raise BinlogArchiveError('The native Shell dump requires binary logging and GTID mode ON or ON_PERMISSIVE')
        workspace=jobs.prepare_scope(owner,endpoint.id)
        program=program_identity(client,route,workspace)
        runtime_limit=current_app.config.get('CDEADMIN_MYSQL_BINLOG_MAX_RUNTIME_SECONDS')
        if runtime_limit is not None:
            if type(runtime_limit) is not int or not 1<=runtime_limit<=2147483647:raise BinlogArchiveError('Application archive runtime policy is invalid')
            if selected['timeout_seconds'] is None or selected['timeout_seconds']>runtime_limit:
                raise BinlogArchiveError('Application policy limits each native archive to '+str(runtime_limit)+' seconds')
        configuration=digest({'registration':MySQLMonitoringHost._configuration(server),'root':str(jobs.root),'runtime_limit':runtime_limit})
        continuation=since_directory=None
        if selected['since_job_id'] is not None:
            previous=jobs.load(selected['since_job_id'],owner,endpoint.id)
            if previous['state'] not in {'completed','artifact_verified'} or previous.get('artifact_removed') or previous.get('native_process_termination_confirmed') is not True:
                raise BinlogArchiveError('Select a completed, retained archive continuation')
            since_directory=jobs.directory(previous)/'archive'
            artifact=verify(since_directory,captured['identity'])
            if digest(artifact)!=digest(previous.get('result',{}).get('artifact')):
                raise BinlogArchiveError('Native archive continuation bytes changed')
            continuation={'job_id':previous['job_id'],'artifact_digest':digest(artifact)}
        else:
            native=next((row for row in captured['logs'] if row['Log_name']==selected['start_file']),None)
            if native is None or int(selected['start_position'])>int(native['File_size']):
                raise BinlogArchiveError('The selected native binary-log file or position is unavailable')
        if operation=='review':return jobs.review(owner,endpoint.id,selected,captured,configuration,program,continuation)
        valid=rows(connection,'SELECT GTID_SUBSET(%s,@@global.gtid_executed) AS valid',(reviewed['source_state']['gtid_executed'],))[0]['valid']
        if valid!=1 or reviewed['continuation']!=continuation:raise BinlogArchiveError('Native binary-log lineage or continuation changed; prepare a new review')
        transport=ArchiveTransport(client,route,delegate_credentials(client,route),workspace,since_directory,continuation)
        admitted=transport;transport=None
        return jobs.start(request,owner,endpoint.id,{'configuration':configuration,'source':captured['identity'],'program':program},admitted)
    except NativeError as error:
        raise BinlogArchiveError('Native MySQL binary-log admission failed ('+str(error.errno)+', '+str(error.sqlstate)+')') from None
    finally:
        if connection is not None:client._discard_failed_session(connection)
        if transport is not None:transport.close()


def download(service,server,request,*,family='mysql'):
    from flask import send_file
    if not isinstance(request,dict) or set(request)!={'job_id','path'}:raise BinlogArchiveError('Select one native archive file')
    if family=='mysql-raw':
        from .mysql_raw_binlog_service import manager as raw_manager
        jobs,owner,endpoint,_context=raw_manager(service,server)
    else:jobs,owner,endpoint,_context=manager(service,server,family)
    opened=jobs.download(request['job_id'],owner,endpoint.id,request['path'])
    try:stream,selected=opened.__enter__()
    except OSError:raise BinlogArchiveError('The native archive file is unavailable') from None
    try:
        response=send_file(stream,mimetype='application/octet-stream',as_attachment=True,
            download_name=selected['path'].rsplit('/',1)[-1],conditional=False,max_age=0)
        response.content_length=selected['size'];response.direct_passthrough=False
        response.headers.update({'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff',
            'X-Accel-Buffering':'no','X-Content-SHA256':selected['sha256']})
        response.call_on_close(lambda:opened.__exit__(None,None,None))
        return response
    except BaseException:opened.__exit__(None,None,None);raise
