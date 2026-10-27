"""Reviewed recovered-service activation under fresh native acceptance locks."""
from copy import deepcopy
import hashlib
from pathlib import Path
import threading
import time

from ..providers.mysql_family import mysql_physical_transport as native
from ..providers.mysql_family import mysql_host_transport as ssh
from ..providers.mysql_family import mysql_instance_restores as targets
from ..providers.mysql_family.mysql_binlog_archives import delegate_credentials, rows
from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
from ..providers.mysql_family.mysql_log_purge import private_connection
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_binlog_jobs import MySQLBinlogJobs, DurableCancellation, digest
from .mysql_binlog_replay_service import source_server
from .mysql_instance_acceptance_service import manager as acceptance_manager
from .mysql_instance_acceptance_jobs import InstanceAcceptanceTransport
from . import mysql_host_service as host
from . import mysql_physical_service as physical


class CutoverJobs(MySQLBinlogJobs):
    operation='mysql_recovered_service_activation'
    remote_database_mutation=True
    review_warnings=(
        'Activation reruns the selected expected-dump checks while native instance/read locks hold. The listed acceptance scope and exclusions require explicit acknowledgement.',
        'The original source must be independently stopped and disabled. Concurrent external administrators are not fenced by the application.',
        'Commits the permanent writable startup policy, then changes native read-only flags and the selected event scheduler. It does not change DNS, application routing or enable the service at boot.',
        'A lost reply never repeats activation. Reconcile current service/startup/SQL facts separately; a committed startup policy can remain after an interrupted live transition.',
    )

    def run(self,record,transport,signal):
        try:
            self.update(record,state='active')
            result=transport.execute(record,self.directory(record),DurableCancellation(self,record,signal))
            self.update(record,state='native_returned',phase='completed',result=result,
                selected_dump_surfaces_verified=True,production_cutover_verified=True,
                native_process_termination_confirmed=result['tool']['process_observation'].get('cleanup_confirmed'),finished_at=time.time())
        except BaseException as error:
            current=self.load(record['job_id'],record['owner'],record['endpoint_id'])
            cancelled=current.get('cancel_requested') and not current.get('activation_may_have_dispatched')
            self.update(record,state='cancelled' if cancelled else 'unknown',error_type=type(error).__name__,
                error_message=str(error) if isinstance(error,native.HostError) else None,
                original_outcome_unchanged=True,production_cutover_verified=False,
                **({'result':error.native_check_result} if getattr(error,'native_check_result',None) else {}),finished_at=time.time())
        finally:
            try:transport.close()
            finally:
                with self._maps_lock:self.workers.pop(record['job_id'],None)

    def begin_activation(self,record,result):
        with self.store(record['job_id']) as store:
            def change(state):
                current=self.record(state,record['job_id'],record['owner'],record['endpoint_id'])
                if current.get('cancel_requested'):raise InterruptedError('Activation cancelled before the startup-policy claim')
                current.update(phase='committing_startup_policy',fresh_acceptance=deepcopy(result),activation_may_have_dispatched=True)
            store.change(change)

    def cancel(self,job_id,owner,endpoint):
        with self.store(job_id) as store:
            def change(state):
                current=self.record(state,job_id,owner,endpoint)
                if current.get('activation_may_have_dispatched'):
                    raise native.HostError('The writable startup policy may be committed; observe the original activation without rollback or replay')
                if current['state']=='reviewed':current.update(state='cancelled',cancel_requested=True)
                elif current['state'] in {'dispatching','active','cancel_requested'}:current.update(state='cancel_requested',cancel_requested=True)
            store.change(change)
        with self._maps_lock:
            known=self.workers.get(job_id)
            if known:known[1].set()
        return self.get(job_id,owner,endpoint)


class ActivationTransport:
    def __init__(self,execute,close):self.execute,self.close=execute,close


def manager(service,jobs):
    with service._semantic_lock:
        value=getattr(service,'mysql_recovery_cutover_jobs',None)
        if value is None:
            value=service.mysql_recovery_cutover_jobs=CutoverJobs(str(jobs.path)+'.cutover',jobs.root/'cutover')
            import atexit
            atexit.register(value.close)
    return value


def policy(connection):
    return rows(connection,'SELECT @@GLOBAL.read_only AS read_only,@@GLOBAL.super_read_only AS super_read_only,'
        '@@GLOBAL.event_scheduler AS event_scheduler')[0]


def bind_target(connection,deployment):
    observed=rows(connection,'SELECT @@datadir AS datadir,@@pid_file AS pid_file,@@port AS port,@@hostname AS hostname')[0]
    directory=deployment['options']['deployment']['directory'].rstrip('/')
    allowed={directory+'/runtime-data',physical.original_binding(deployment)['datadir'].rstrip('/')}
    if (observed['datadir'].rstrip('/') not in allowed or observed['pid_file']!=directory+'/runtime.pid' or
            observed['port']!=deployment['options']['deployment']['port'] or observed['hostname']!=physical.original_binding(deployment)['hostname']):
        raise native.HostError('The registered SQL listener is not the independently observed permanent native service')
    return observed


def acceptance_record(service,server,owner,job_id,uuid):
    jobs,_,endpoint=acceptance_manager(service,server);record=jobs.load(job_id,owner,endpoint.id)
    result=record.get('result') or {};scopes=record['source_state']['scopes']
    if (record.get('acceptance_outcome')!='matched' or record.get('native_process_termination_confirmed') is not True or
            result.get('selected_dump_surfaces_verified') is not True or result.get('server_locks_released') is not True or
            record['source']['server_uuid']!=uuid or not scopes['data_requested'] or not scopes['definitions_requested']):
        raise native.HostError('Select matched native data/definition acceptance on this recovered target with confirmed utility and lock cleanup')
    return record


def source_fence(service,server,owner,endpoint,selected,credentials,source_uuid,*,record=None):
    if record is None:
        jobs,_,_=host.manager(service,server)
        record=jobs.load(selected,owner,endpoint.id)
    if (record['options'].get('operation')!='service_disable' or record['source']['server_uuid']!=source_uuid or
            record.get('state')!='native_process_returned' or
            record.get('remote_receipt',{}).get('result',{}).get('return_code')!=0):
        raise native.HostError('Select an originally observed source-service disable receipt for this physical source')
    transport=ssh.Transport(record['options']['connection'],host.credentials(credentials))
    try:
        transport.connect();payload=host.native_request(record,'status');payload['observe_dictionary_writers']=True
        remote=transport.request(payload)
    finally:transport.close()
    observed=remote.get('service_reconciliation') or {};service_state=observed.get('service') or {}
    if (not observed.get('observed') or service_state.get('unit',{}).get('ActiveState')!='inactive' or
            service_state.get('unit',{}).get('UnitFileState') not in {'disabled','masked'} or
            service_state.get('native_process') is not None or service_state.get('manager_main_pid')!=0 or
            observed.get('dictionary_writers',{}).get('native_dictionary_writers_absent') is not True):
        raise native.HostError('The original native source service must currently be inactive and disabled')
    return {'job_id':record['job_id'],'review_digest':record['review_digest'],
        'binding':record['source_state']['host_binding'],'service':service_state['selected_service'],
        'definition_files':service_state['definition_files'],'command_sha256':service_state['command_sha256'],
        'inactive':True,'disabled':True}


def action(service,server,physical_jobs,owner,endpoint,operation,request):
    jobs=manager(service,physical_jobs)
    if operation=='list' and not set(request)-{'offset','limit'}:return jobs.list(owner,endpoint.id,**request)
    if operation in {'status','cancel'} and set(request)=={'job_id'}:
        return (jobs.get if operation=='status' else jobs.cancel)(request['job_id'],owner,endpoint.id)
    if operation=='review':
        if set(request)!={'deployment_job_id','target_server_id','acceptance_job_id','source_fence_job_id','target_confirmation',
                'acceptance_scope_acknowledged','event_scheduler','credentials'}:
            raise native.HostError('Select the recovered deployment, registered target, acceptance and original source-service fence')
        selected={key:value for key,value in request.items() if key!='credentials'};record=None
        if (request['acceptance_scope_acknowledged'] is not True or request['event_scheduler'] not in {'ON','OFF'}):
            raise native.HostError('Acknowledge the selected dump scope and choose the native event scheduler policy')
    elif operation in {'start','reconcile','observe_utilities'}:
        fields={'job_id','credentials'}|({'review_digest','confirmed'} if operation=='start' else set())
        if set(request)!=fields:raise native.HostError('Select the original cutover and private SSH authentication')
        record=jobs.load(request['job_id'],owner,endpoint.id);selected=record['options']
        if operation=='observe_utilities':
            jobs.observe_utility(record)
            return jobs.get(record['job_id'],owner,endpoint.id)
        if operation=='start' and record['state']!='reviewed':
            if request.get('confirmed') is not True or request.get('review_digest')!=record['review_digest']:
                raise native.HostError('Confirm the original cutover review')
            return jobs.get(record['job_id'],owner,endpoint.id)
    else:raise native.HostError('Select a recovered-service cutover action')
    deployment=physical_jobs.load(selected['deployment_job_id'],owner,endpoint.id)
    if deployment['options'].get('phase')!='deploy':raise native.HostError('Select a permanent recovered deployment')
    target_server=source_server(owner,selected['target_server_id']);host.manager(service,target_server)
    accepted=acceptance_record(service,target_server,owner,selected['acceptance_job_id'],selected['target_confirmation'])
    if accepted['source_state']['input_reference']['summary']['source_uuid']!=deployment['source']['server_uuid']:
        raise native.HostError('The expected dump belongs to another original source')
    context,payload,_root=service.endpoint_service.workspace(target_server,database_target_id=None)
    provider=service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider,MySQLPilotProvider):raise native.HostError('Select the native recovered MySQL client')
    client=provider.client;route={key:value for key,value in payload['route'].items() if key not in POOL_ARGUMENTS}
    transport=native.Transport(deployment['options']['connection'],host.credentials(request['credentials']))
    connection=admitted=None
    try:
        transport.connect()
        remote=transport.request(physical.remote_request(deployment,'status'))
        observed=remote.get('deployment_observation') or {}
        if not observed.get('permanent_native_process_verified') or observed.get('recovered_uuid')!=selected['target_confirmation']:
            raise native.HostError('Independently observe the exact permanent native recovered service before cutover')
        fence=source_fence(service,server,owner,endpoint,selected['source_fence_job_id'],request['credentials'],deployment['source']['server_uuid'])
        connection=private_connection(client,{**route,'database':None,'autocommit':True,'read_timeout':120})
        target=targets.capture(connection);current_policy=policy(connection);binding=bind_target(connection,deployment)
        if target['identity']['server_uuid']!=observed['recovered_uuid']:
            raise native.HostError('The registered SQL target differs from the permanent service')
        facts={'target':target,'policy':current_policy,'sql_service_binding':binding,'source_fence':fence,
            'deployment':{'job_id':deployment['job_id'],'review_digest':deployment['review_digest'],
                'manifest_sha256':observed['manifest_sha256'],'launcher_sha256':observed['launcher_sha256']},
            'acceptance':{'job_id':accepted['job_id'],'review_digest':accepted['review_digest'],
                'result_digest':digest(accepted['result']),'scopes':accepted['source_state']['scopes']}}
        if operation=='reconcile':
            jobs.update(record,current_observation={**facts,'startup_activation':observed.get('startup_activation'),
                'original_outcome_unchanged':True,'automatic_retry':False})
            return jobs.get(record['job_id'],owner,endpoint.id)
        if current_policy['read_only']!=1 or current_policy['super_read_only']!=1 or current_policy['event_scheduler']!='OFF':
            raise native.HostError('The permanent recovered target must still have its staged read-only/event-off policy')
        if target!=accepted['result']['target_observation']:
            raise native.HostError('The target changed after independent acceptance; rerun acceptance')
        configuration=digest({'registration':host.MySQLMonitoringHost._configuration(target_server),'adapter':native.program(),
            'cutover_adapter':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
        if operation=='review':return jobs.review(owner,endpoint.id,selected,
            {'identity':target['identity'],'state':facts},configuration,accepted['program'])
        if facts!=record['source_state'] or configuration!=record['configuration']:
            raise native.HostError('The cutover target, acceptance, deployment or original service fence changed after review')
        lock_name='cdeadmin:binlog-load:'+target['identity']['server_uuid']
        from .mysql_instance_restore_service import input_reference
        original=accepted['source_state']['input_reference']
        reference,directory,source_identity=input_reference(service,owner,{'source_server_id':original['server_id'],'backup_job_id':original['job_id']})
        if reference!=accepted['source_state']['input_reference']:raise native.HostError('The accepted expected dump changed')
        fence_jobs,_,_=host.manager(service,server)
        fence_record=fence_jobs.load(selected['source_fence_job_id'],owner,endpoint.id)
        owned=InstanceAcceptanceTransport(client,route,delegate_credentials(client,route),connection,directory,source_identity)
        connection=None;peer=transport;transport=None
        private_credentials=deepcopy(request['credentials']);held={'marker':False}
        def execute(record,destination,signal):
            fresh=deepcopy(accepted);fresh['job_id']=record['job_id'];fresh['source_state']['target']=target
            def verified(result):
                # The native Shell owns this marker during its checks. Acquire it
                # after that client returns; this private session still holds FTWRL.
                if rows(owned.connection,'SELECT GET_LOCK(%s,0) AS acquired',(lock_name,))[0]['acquired']!=1:
                    raise native.HostError('Another native recovery operation owns this target')
                held['marker']=True
                # Acceptance still owns both native locks here; recheck the stopped
                # original service immediately before changing startup or SQL policy.
                if source_fence(service,server,owner,endpoint,selected['source_fence_job_id'],private_credentials,deployment['source']['server_uuid'],record=fence_record)!=fence:
                    raise native.HostError('The original source-service fence changed during acceptance')
                if policy(owned.connection)!=current_policy:raise native.HostError('The recovered read-only policy changed during acceptance')
                jobs.begin_activation(record,result)
                payload=physical.remote_request(deployment,'activate_policy')
                payload['activation']={'job_id':record['job_id'],'review_digest':record['review_digest'],
                    'event_scheduler':selected['event_scheduler'],'target_uuid':target['identity']['server_uuid']}
                reply=peer.request(payload);jobs.update(record,startup_policy_reply=reply)
                if reply.get('original_claim_exists') or not (reply.get('activation') or {}).get('startup_policy_committed'):
                    raise native.HostError('The original startup transition is already claimed or unconfirmed; reconcile without replay')
                cursor=owned.connection.cursor()
                try:
                    for statement in ('SET GLOBAL super_read_only=OFF','SET GLOBAL read_only=OFF','SET GLOBAL event_scheduler='+selected['event_scheduler']):
                        cursor.execute(statement)
                    after=policy(owned.connection)
                    if after!={'read_only':0,'super_read_only':0,'event_scheduler':selected['event_scheduler']}:
                        raise native.HostError('Native writable activation is unconfirmed')
                    jobs.update(record,live_policy_observed=after,phase='live_policy_observed')
                finally:cursor.close()
            result=owned.execute(fresh,destination,signal,lambda value:jobs.progress(record,value),
                lambda:jobs.update(record,phase='fresh_native_acceptance'),verified=verified)
            physical_jobs.update(deployment,cutover_job_id=record['job_id'])
            return result
        def close():
            try:
                if held['marker']:
                    try:rows(owned.connection,'SELECT RELEASE_LOCK(%s) AS released',(lock_name,))
                    except Exception:pass
                owned.close()
            finally:peer.close();private_credentials.clear()
        admitted=ActivationTransport(execute,close)
        transfer=admitted;admitted=None
        return jobs.start({key:request[key] for key in ('job_id','review_digest','confirmed')},owner,endpoint.id,
            {'configuration':configuration,'source':target['identity'],'program':accepted['program']},transfer)
    finally:
        if admitted is not None:admitted.close()
        elif connection is not None:client._discard_failed_session(connection)
        if transport is not None:transport.close()
