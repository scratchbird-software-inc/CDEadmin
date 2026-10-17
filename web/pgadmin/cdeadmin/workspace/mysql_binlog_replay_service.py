"""Owned sealed archive inputs and separately admitted native recovery targets."""
from copy import deepcopy
import shutil

from ..operations.store import JsonOperationStore
from ..providers.mysql_family import mysql_binlog_archives as archive
from ..providers.mysql_family import mysql_binlog_replay as native
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_binlog_jobs import digest,identity
from .mysql_binlog_replay_jobs import MySQLBinlogReplayJobs
from .mysql_binlog_service import manager as archive_manager
from .mysql_monitoring_host import MySQLMonitoringHost


class ReplayTransport:
    def __init__(self,client,route,credentials,observer,source_directory,source_identity):
        self.client,self.route,self.credentials,self.observer=client,route,credentials,observer
        self.source_directory,self.source_identity=source_directory,source_identity

    def close(self):
        if self.credentials is not None:self.credentials.close();self.credentials=None
        if self.observer is not None:
            owned=self.observer;self.observer=None;self.client._discard_failed_session(owned)

    def execute(self,record,directory,cancel,progress,boundary):
        reference=record['source_state']['input_reference'];staged=directory/'input';cleanup_safe=True
        try:
            artifact=archive.verify(self.source_directory,self.source_identity,cancel=cancel)
            if digest(artifact)!=reference['artifact_digest']:raise archive.BinlogArchiveError('Sealed native replay input changed')
            archive.stage_continuation(self.source_directory,staged,artifact,self.source_identity,cancel=cancel)
            selected=record['options'];target=native.admission(self.observer,artifact,selected)
            before=record['source_state']['target']
            if target['identity']!=record['source'] or archive.rows(self.observer,
                'SELECT GTID_SUBSET(%s,@@global.gtid_executed) AND GTID_SUBSET(@@global.gtid_executed,%s) AS same',
                (before['state']['gtid_executed'],before['state']['gtid_executed']))[0]['same']!=1:
                raise archive.BinlogArchiveError('Native target changed after review; prepare a new replay review')
            boundary()
            result=native.run_load(self.client,self.route,self.credentials,staged,record['source'],before['state']['gtid_executed'],
                selected,directory,record['program'],cancel=cancel,progress=progress)
            if (result.get('control') or {}).get('native_load_returned'):
                try:result['native_coverage']=native.coverage(self.observer,artifact,selected,before)
                except Exception as error:result['native_coverage']={'available':False,'error_type':type(error).__name__}
            result['data_recovery_verified']=False
            return result
        except BaseException as error:
            observed=getattr(error,'observation',None) or getattr(error,'process_observation',{})
            cleanup_safe=observed.get('process_observation',{}).get('cleanup_confirmed') is not False
            raise
        finally:
            if cleanup_safe:shutil.rmtree(staged,ignore_errors=True)


def manager(service,server):
    from flask import current_app
    _archives,owner,endpoint,context=archive_manager(service,server)
    permissions=service.endpoint_service.provider_registry.admitted_permissions(context)
    if not {'restore_admin','administer'}.issubset(permissions):raise archive.BinlogArchiveError('Native restore and administration permissions are required')
    store=getattr(service.operation_bus,'store',None)
    if not isinstance(store,JsonOperationStore):raise archive.BinlogArchiveError('Native replay requires durable application storage')
    with service._semantic_lock:
        jobs=getattr(service,'mysql_binlog_replay_jobs',None)
        if jobs is None:
            root=current_app.config.get('CDEADMIN_MYSQL_BINLOG_REPLAY_ROOT') or str(store.path.parent/'mysql-binary-log-replays')
            jobs=service.mysql_binlog_replay_jobs=MySQLBinlogReplayJobs(str(store.path)+'.mysql-replay',root)
            import atexit
            atexit.register(jobs.close)
    return jobs,owner,endpoint


def source_server(owner,server_id):
    from pgadmin.model import Server
    if type(server_id) is not int or server_id<=0:raise archive.BinlogArchiveError('Select an owned native MySQL source registration')
    source=Server.query.filter_by(id=server_id,user_id=owner).first()
    endpoint=getattr(source,'endpoint_profile',None)
    if endpoint is None or endpoint.profile_id!='mysql-native' or endpoint.provider_id!='org.cdeadmin.mysql':
        raise archive.BinlogArchiveError('Native archive source registration is unavailable')
    return source


def input_reference(service,owner,request):
    source=source_server(owner,request['source_server_id']);jobs,_owner,endpoint,_context=archive_manager(service,source)
    record=jobs.load(identity(request['archive_job_id']),owner,endpoint.id)
    artifact=record.get('result',{}).get('artifact')
    if record['state'] not in {'completed','artifact_verified'} or record.get('artifact_removed') or record.get('native_process_termination_confirmed') is not True or artifact is None:
        raise archive.BinlogArchiveError('Select a retained verified archive whose native writer stopped')
    summary={key:deepcopy(artifact[key]) for key in ('format','source_uuid','start_from','end_at','gtid_set','file_count','total_bytes')}
    reference={'server_id':source.id,'endpoint_id':endpoint.id,'job_id':record['job_id'],'artifact_digest':digest(artifact),'summary':summary}
    return reference,jobs.directory(record)/'archive',record['source']


def action(service,server,operation,request):
    from flask import current_app
    from mysql.connector import Error as NativeError
    from pgadmin.model import Server
    if not isinstance(request,dict):raise archive.BinlogArchiveError('Select a native replay request')
    jobs,owner,endpoint=manager(service,server)
    if operation=='list':
        if set(request)-{'offset','limit'}:raise archive.BinlogArchiveError('Invalid replay receipt page')
        return jobs.list(owner,endpoint.id,**request)
    if operation=='sources':
        if set(request)-{'offset','limit'}:raise archive.BinlogArchiveError('Select an owned source registration page')
        offset,limit=request.get('offset',0),request.get('limit',25)
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
            raise archive.BinlogArchiveError('Invalid source registration page')
        # The joined profile filter keeps pagination bounded by native sources.
        candidates=Server.query.filter_by(user_id=owner).order_by(Server.id)
        from pgadmin.model import EndpointProfile
        candidates=candidates.join(EndpointProfile,Server.endpoint_profile).filter(
            EndpointProfile.profile_id=='mysql-native',EndpointProfile.provider_id=='org.cdeadmin.mysql')
        total=candidates.count()
        return {'sources':[{'server_id':item.id,'name':item.name} for item in candidates.offset(offset).limit(limit)],
            'offset':offset,'limit':limit,'total':total,'more':offset+limit<total}
    if operation=='archives':
        if set(request)-{'source_server_id','offset','limit'} or 'source_server_id' not in request:raise archive.BinlogArchiveError('Select an owned archive source')
        source=source_server(owner,request['source_server_id']);archives,_owner,source_endpoint,_context=archive_manager(service,source)
        return archives.list(owner,source_endpoint.id,request.get('offset',0),request.get('limit',25))
    if operation in {'status','cancel'}:
        if set(request)!={'job_id'}:raise archive.BinlogArchiveError('Select one replay receipt')
        return (jobs.get if operation=='status' else jobs.cancel)(request['job_id'],owner,endpoint.id)
    if operation=='review':
        if set(request)!={'source_server_id','archive_job_id','options'}:raise archive.BinlogArchiveError('Review one sealed archive and exact target options')
        selected=native.options(request['options']);reference,source_directory,source_identity=input_reference(service,owner,request)
    elif operation=='start':
        record=jobs.load(request.get('job_id'),owner,endpoint.id)
        if record['state']!='reviewed':return jobs.start(request,owner,endpoint.id,{},None)
        selected=record['options'];reference,source_directory,source_identity=input_reference(service,owner,{
            'source_server_id':record['source_state']['input_reference']['server_id'],
            'archive_job_id':record['source_state']['input_reference']['job_id']})
        if reference!=record['source_state']['input_reference']:raise archive.BinlogArchiveError('Native replay input reference changed')
    elif operation in {'inspect','reconcile','acknowledge'}:
        if operation=='inspect':
            if request:raise archive.BinlogArchiveError('Native target inspection takes no route')
            record=selected=reference=None
        else:
            allowed={'job_id'} if operation=='reconcile' else {'job_id','target_confirmation','observation_digest'}
            if set(request)!=allowed:raise archive.BinlogArchiveError('Select one replay and its exact observed target facts')
            record=jobs.load(request['job_id'],owner,endpoint.id);selected=record['options'];reference=record['source_state']['input_reference']
    else:raise archive.BinlogArchiveError('Native replay action is unavailable')
    client=connection=transport=None
    try:
        context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
        provider=service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider,MySQLPilotProvider):raise archive.BinlogArchiveError('Native MySQL replay client is unavailable')
        from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
        route={key:value for key,value in payload['route'].items() if key not in POOL_ARGUMENTS}
        client=provider.client;connection=client._connect({'route':{**route,'read_timeout':5,'write_timeout':15}})
        target=native.capture_target(connection)
        if operation=='inspect':return {'identity':target['identity'],'state':target['state'],'scope':'native target identity and GTID state; no mutation'}
        if operation in {'reconcile','acknowledge'}:
            if target['identity']!=record['source']:raise archive.BinlogArchiveError('Reconciliation reached another native target or principal')
            observation=native.coverage(connection,reference['summary'],selected,record['source_state']['target'])
            observation['native_lock_free']=archive.rows(connection,'SELECT IS_FREE_LOCK(%s) AS free',('cdeadmin:binlog-load:'+target['identity']['server_uuid'],))[0]['free']==1
            if operation=='acknowledge':return jobs.acknowledge(record,observation,request)
            result=jobs.reconcile(record,observation);result['observation_digest']=digest(observation);return result
        target=native.admission(connection,reference['summary'],selected)
        runtime_limit=current_app.config.get('CDEADMIN_MYSQL_BINLOG_REPLAY_MAX_RUNTIME_SECONDS')
        if runtime_limit is not None:
            if type(runtime_limit) is not int or not 1<=runtime_limit<=2147483647:raise archive.BinlogArchiveError('Native replay runtime policy is invalid')
            if selected['timeout_seconds'] is None or selected['timeout_seconds']>runtime_limit:raise archive.BinlogArchiveError('Application policy limits each native replay client to '+str(runtime_limit)+' seconds')
        program=archive.program_identity(client,route,jobs.prepare_scope(owner,endpoint.id))
        configuration=digest({'registration':MySQLMonitoringHost._configuration(server),'root':str(jobs.root),'runtime_limit':runtime_limit})
        if operation=='review':return jobs.review(owner,endpoint.id,selected,{'identity':target['identity'],
            'state':{'target':target,'input_reference':reference}},configuration,program)
        transport=ReplayTransport(client,route,archive.delegate_credentials(client,route),connection,source_directory,source_identity);connection=None
        admitted=transport;transport=None
        return jobs.start(request,owner,endpoint.id,{'configuration':configuration,'source':target['identity'],'program':program},admitted)
    except NativeError as error:
        raise archive.BinlogArchiveError('Native MySQL replay admission failed ('+str(error.errno)+', '+str(error.sqlstate)+')') from None
    finally:
        if connection is not None:client._discard_failed_session(connection)
        if transport is not None:transport.close()
