"""Recurring native acceptance against an explicitly retained recovery checkpoint."""
from copy import deepcopy
import hashlib
from pathlib import Path
import time
import uuid

from . import mysql_physical_backup_schedule as backups
from . import mysql_physical_service as physical
from . import mysql_physical_retention as retention
from .mysql_binlog_jobs import digest, review_digest
from .mysql_monitoring_host import MySQLMonitoringHost
from ..providers.mysql_family import mysql_instance_acceptance as native
from ..providers.mysql_family import mysql_recovery_bridge as bridge
from ..providers.mysql_family.mysql_binlog_archives import program_identity, delegate_credentials
from ..providers.mysql_family import mysql_instance_restores as targets
from .mysql_instance_acceptance_jobs import InstanceAcceptanceTransport
from .mysql_instance_restore_service import input_reference
from .mysql_instance_acceptance_service import manager as acceptance_manager
from .mysql_instance_backup_service import manager as backup_manager


class PolicyJobs(backups.BackupJobs):
    operation='mysql_scheduled_physical_check'
    review_warnings=(
        'Each occurrence starts a fresh read-only recovery from the selected retained copy-back and checks it against the selected sealed expected dump. It does not back up the current live source or infer a new expected checkpoint.',
        'Explicitly authorize trusted LOCAL INFILE, native checksum input and read locks on the isolated target, and encrypted expiring SSH/SQL delegation. Source sessions and credentials are not borrowed. Both retained inputs stay protected until the policy and its work are resolved.',
        'Only exported expected-dump surfaces are checked. Unexported/system state and production cutover remain separate. Differences or interrupted work suspend future occurrences; unknown checks are never automatically repeated.',
    )


class Occurrences(backups.Occurrences):
    operation='mysql_physical_check_occurrence'
    review_warnings=PolicyJobs.review_warnings

    def public(self,record):
        return {**super().public(record),'selected_snapshot_verified':record.get('selected_snapshot_verified',False),
            'acceptance_outcome':record.get('acceptance_outcome','not_observed')}


def options(value):
    if not isinstance(value,dict) or set(value)!={'physical','expected_backup_job_id','threads','interval_seconds','expires_after_days'}:
        raise physical.native.HostError('Select a retained recovery checkpoint, expected dump and expiring check policy')
    selected=physical.options(value['physical'])
    if (selected['phase']!='recover' or selected['recovery_mode']!='read_only' or selected['recovery_port']!=0 and not selected.get('recovery_tls') or
            selected['recovery_local_infile'] is not True or not 30<=selected['timeout_seconds']<=3600):
        raise physical.native.HostError('Scheduled acceptance requires private-socket or provisioned TLS read-only recovery, trusted checksum input and a30–3600-second lifetime')
    native.options({'target_confirmation':str(uuid.UUID(int=0)),'server_wide_write_pause_confirmed':True,
        'threads':value['threads'],'timeout_seconds':selected['timeout_seconds']})
    from .mysql_binlog_jobs import identity
    identity(value['expected_backup_job_id'])
    backups.retained.options({'policy':{'retention_days':0,'keep_latest':1},**{key:value[key] for key in ('interval_seconds','expires_after_days')}})
    return {**deepcopy(value),'physical':selected,'drill':None}


def program(jobs,anchor,peer):
    from . import mysql_instance_acceptance_jobs as accepted
    return {**backups.program(jobs,anchor,peer),'check_scheduler_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'acceptance_adapter_sha256':hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
        'acceptance_jobs_sha256':hashlib.sha256(Path(accepted.__file__).read_bytes()).hexdigest()}


class ScheduleHost(backups.ScheduleHost):
    program=staticmethod(program)

    def __init__(self,app,service):
        super().__init__(app,service)
        path=service.operation_bus.store.path
        self.jobs=PolicyJobs(str(path)+'.mysql-check-schedules',app.config.get('CDEADMIN_MYSQL_CHECK_SCHEDULE_ROOT') or path.parent/'mysql-check-schedules')
        self.enabled=self.jobs.root/'enabled'

    def occurrences(self,grant):
        return Occurrences(str(self.jobs.path)+'.occurrences',self.jobs.root/'occurrences'/grant['job_id'])

    def expected(self,server,owner,job_id):
        reference,directory,source=input_reference(self.service,owner,{'source_server_id':server.id,'backup_job_id':job_id})
        from ..providers.mysql_family import mysql_instance_dumps as dumps
        artifact=dumps.verify(directory,source);selected=native.scopes(directory,artifact)
        if not selected['data_requested'] or not selected['definitions_requested']:
            raise physical.native.HostError('Select an expected full data/definition dump with native checksums')
        return reference,directory,source,selected

    def hold(self,server,jobs,grant,enabled):
        # The physical admission lock is held by every caller. Local file
        # retention and this expected-input hold share the original job store.
        logical,owner,endpoint,_=backup_manager(self.service,server)
        target=grant['options']['expected_backup_job_id'];parent=grant['options']['physical']['input_job_id']
        for manager,job_id in ((logical,target),(jobs,parent)):
            with manager.store(job_id) as store:
                def change(state):
                    record=manager.record(state,job_id,owner,endpoint.id)
                    if enabled and (record.get('artifact_removed') or record.get('artifact_removal') or record.get('retention_batch_id')):
                        raise physical.native.HostError('Recovery-check input has already entered retention')
                    holds=record.setdefault('recovery_check_holds',{})
                    if enabled:holds[grant['job_id']]=True
                    else:holds.pop(grant['job_id'],None)
                store.change(change)

    def action(self,server,jobs,owner,endpoint,operation,request):
        action=operation.removeprefix('check_schedule_')
        if action=='review' and set(request)=={'options','credentials'}:
            if not self.keys.available:raise physical.native.HostError('Configure physical worker encryption keys before scheduling recovery checks')
            selected=options(request['options'])
            with retention.admission(jobs):
                parent=jobs.load(selected['physical']['input_job_id'],owner,endpoint.id)
                if parent['options']['phase']!='copy_back' or not jobs.public(parent)['file_verification_confirmed']:
                    raise physical.native.HostError('Select a retained verified isolated copy-back')
                reference,directory,source,scopes=self.expected(server,owner,selected['expected_backup_job_id'])
                if reference['summary']['source_uuid']!=parent['source']['server_uuid']:
                    raise physical.native.HostError('The expected dump belongs to another physical source')
                template={'options':selected['physical'],'source':deepcopy(parent['source']),
                    'source_state':{**deepcopy(parent['source_state']),'remote_review':{}},'job_id':'','review_digest':''}
                tls=physical.sql_tls(self.service,server)
                if tls is not None:template['source_state']['sql_tls_policy']=tls['policy']
                channel=physical.native.Transport(selected['physical']['connection'],backups.host.credentials(request['credentials']))
                try:
                    peer=channel.connect();template['source_state']['remote_review']=channel.request(physical.remote_request(template,'inspect'))
                    context,payload,_=self.service.endpoint_service.workspace(server,database_target_id=None)
                    client=self.service.endpoint_service.provider_registry.resolve(context).instance.client
                    accepted,_,_=acceptance_manager(self.service,server)
                    shell=program_identity(client,payload['route'],accepted.prepare_scope(owner,endpoint.id))
                    return self.jobs.review(owner,endpoint.id,selected,{'identity':parent['source'],'state':{'template':template,
                        'scope_digest':backups.scope(template),'acceptance_root':str(accepted.root),'expected':reference,'scopes':scopes,'mysql_shell':shell,
                        'preview':{'phases':['recover','acceptance','stop'],'expected_backup':reference,'input_job_id':parent['job_id'],
                            'current_live_source_is_expected':False}}},digest(MySQLMonitoringHost._configuration(server)),self.program(jobs,template,peer),continuation={'server_id':server.id})
                finally:channel.close()
        if action=='enable':
            grant=self.jobs.load(request.get('job_id'),owner,endpoint.id)
            if grant['state']!='reviewed':return super().action(server,jobs,owner,endpoint,'backup_schedule_'+action,request)
            fields={'job_id','confirmed','schedule_confirmation','review_digest','delegate_ssh_credentials','delegate_database_credentials','credentials'}
            if (set(request)!=fields or any(request.get(key) is not True for key in ('confirmed','delegate_ssh_credentials','delegate_database_credentials')) or
                    request['schedule_confirmation']!=grant['job_id'] or request['review_digest']!=grant['review_digest'] or
                    review_digest(grant)!=grant['review_digest'] or grant['expires_at']<time.time()):
                raise physical.native.HostError('Confirm the exact reviewed recovery policy and both encrypted credential delegations')
            acquired=False
            try:
                reference,*_=self.expected(server,owner,grant['options']['expected_backup_job_id'])
                if reference!=grant['source_state']['expected']:raise physical.native.HostError('Expected checkpoint changed after policy review')
                acquired=True;self.hold(server,jobs,grant,True)
                return super().action(server,jobs,owner,endpoint,'backup_schedule_'+action,request)
            finally:
                if acquired and self.read(grant['job_id'])['state']!='enabled':self.hold(server,jobs,grant,False)
        result=super().action(server,jobs,owner,endpoint,'backup_schedule_'+action,request)
        if action in {'disable','release'}:
            grant=self.read(request['job_id'])
            last=grant.get('last_occurrence_id')
            settled=last is None or self.occurrences(grant).load(last,owner,endpoint.id).get('protection_released') is True
            if grant['state']!='enabled' and settled:
                with retention.admission(jobs):self.hold(server,jobs,grant,False)
        return result

    def check(self,server,jobs,grant,records,occurrence,secret,runtime):
        self.require(grant,occurrence['job_id'])
        reference,directory,source,scopes=self.expected(server,grant['owner'],grant['options']['expected_backup_job_id'])
        if reference!=grant['source_state']['expected'] or scopes!=grant['source_state']['scopes']:
            raise physical.native.HostError('The scheduled expected checkpoint changed')
        observed=runtime['remote_observation'];identity=observed['sql_identity']
        binding={'id':str(uuid.uuid4()),'owner':grant['owner'],'endpoint_id':grant['endpoint_id'],'job_id':runtime['job_id'],
            'server_uuid':identity['server_uuid'],'version':identity['version'],'datadir':observed['data_directory'],'recovery_mode':'read_only'}
        stream={'schema':'cdeadmin.mysql-recovery-stream.v1','workspace':runtime['options']['workspace'],
            'job_id':runtime['job_id'],'input_digest':runtime['review_digest'],'binding':deepcopy(runtime['host_binding']),
            'expected':{'server_uuid':identity['server_uuid'],'datadir':observed['data_directory'],'runtime_process':deepcopy(observed['runtime_process'])}}
        channel=physical.native.Transport(runtime['options']['connection'],secret['ssh']);installed=None;utility=None;connection=None;transport=None
        try:
            channel.connect();installed=bridge.bridges.install(binding,channel,stream)
            with backups.sql_client(self.service,server,secret['database'],'check:'+occurrence['job_id'],tool_credentials=True) as (client,route):
                route={**route,bridge.ROUTE_KEY:binding,'database':None,'autocommit':True,'read_timeout':runtime['options']['timeout_seconds']}
                utility=bridge.admit_replay_utility(route,family='acceptance');route=utility.route
                connection=client._connect({'route':route});target=targets.capture(connection)
                if target['identity']!= {key:identity[key] for key in ('server_uuid','version','authenticated_principal','active_role')}:
                    raise physical.native.HostError('Scheduled acceptance reached another recovered target')
                accepted,owner,endpoint=acceptance_manager(self.service,server)
                if str(accepted.root)!=grant['source_state']['acceptance_root']:raise physical.native.HostError('Scheduled acceptance filesystem scope changed')
                shell=program_identity(client,route,accepted.prepare_scope(owner,endpoint.id))
                if shell!=grant['source_state']['mysql_shell']:raise physical.native.HostError('Scheduled native acceptance utility changed')
                selected=native.options({'target_confirmation':identity['server_uuid'],'server_wide_write_pause_confirmed':True,
                    'threads':grant['options']['threads'],'timeout_seconds':runtime['options']['timeout_seconds']})
                ticket=accepted.review(owner,endpoint.id,selected,{'identity':target['identity'],'state':{'target':target,'input_reference':reference,
                    'scopes':scopes,'recovery_binding':binding,'physical_recovery':{'job_id':runtime['job_id'],'review_digest':runtime['review_digest'],
                        'copy_back_job_id':runtime['options']['input_job_id'],'runtime_process':deepcopy(observed['runtime_process']),'expected_boundary':reference['summary']['native_boundary']},
                    'scheduled_policy_id':grant['job_id'],'scheduled_occurrence_id':occurrence['job_id']}},grant['configuration'],shell)
                # Durable ownership precedes native acceptance admission.
                records.update(occurrence,acceptance_job_id=ticket['job_id'],acceptance_review_digest=ticket['review_digest'],recovery_binding=binding)
                self.require(grant,occurrence['job_id'])
                transport=InstanceAcceptanceTransport(client,route,delegate_credentials(client,route),connection,directory,source)
                transport.recovery_utility=utility;connection=None;utility=None
                value=accepted.start({'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True},owner,endpoint.id,
                    {'configuration':grant['configuration'],'source':target['identity'],'program':shell},transport);transport=None
                deadline=time.monotonic()+runtime['options']['timeout_seconds']+30
                while value['state'] in {'dispatching','active','cancel_requested'}:
                    try:self.require(grant,occurrence['job_id'])
                    except Exception:accepted.cancel(ticket['job_id'],owner,endpoint.id);raise
                    if time.monotonic()>deadline:accepted.cancel(ticket['job_id'],owner,endpoint.id);raise physical.native.HostError('Original acceptance observation exceeded its deadline')
                    self.stop.wait(.1);value=accepted.get(ticket['job_id'],owner,endpoint.id)
                while True:
                    with accepted._maps_lock:worker=accepted.workers.get(ticket['job_id'])
                    if not worker or not worker[0].is_alive():break
                    if time.monotonic()>deadline:raise physical.native.HostError('Original acceptance observer cleanup remains unconfirmed')
                    self.stop.wait(.01)
                records.update(occurrence,acceptance_outcome=value['acceptance_outcome'],acceptance_receipt=value)
                if value['acceptance_outcome']!='matched' or value.get('native_process_termination_confirmed') is not True or value.get('recovery_fence_release_confirmed') is not True:
                    raise physical.native.HostError('Scheduled recovery differs or remains unconfirmed; inspect the original acceptance receipt')
                records.update(occurrence,selected_snapshot_verified=True)
        finally:
            if connection is not None:client._discard_failed_session(connection)
            if transport is not None:transport.close()
            if utility is not None:utility.close()
            if installed is None:channel.close()
            elif installed.users==0:bridge.bridges.detach(binding,expected=installed)

    def perform(self,server,jobs,grant,records,occurrence,secret):
        selected=deepcopy(grant['options']['physical'])
        value=self.step(server,jobs,grant,records,occurrence,secret,selected,
            on_ready=lambda runtime:self.check(server,jobs,grant,records,occurrence,secret,runtime))
        return {'recovery_job_id':value['job_id']}

    def release(self,server,jobs,grant,records,occurrence,ssh,authorize=None):
        accepted,owner,endpoint=acceptance_manager(self.service,server)
        job_id=occurrence.get('acceptance_job_id')
        if job_id:
            original=accepted.load(job_id,owner,endpoint.id)
            if (original['review_digest']!=occurrence['acceptance_review_digest'] or original['source_state'].get('scheduled_policy_id')!=grant['job_id'] or
                    original['source_state'].get('scheduled_occurrence_id')!=occurrence['job_id']):raise physical.native.HostError('Original scheduled acceptance binding changed')
            with accepted._maps_lock:
                worker=accepted.workers.get(job_id)
                if worker and worker[0].is_alive():raise physical.native.HostError('The original acceptance observer is still active')
            if original['state']=='reviewed':accepted.cancel(job_id,owner,endpoint.id)
            else:
                accepted.inspect_utilities(original);original=accepted.load(job_id,owner,endpoint.id)
                if original.get('native_process_termination_confirmed') is not True:raise physical.native.HostError('Confirm original acceptance utility termination before release')
            reference=original['source_state']['physical_recovery']
            item=next((item for item in occurrence.get('native_jobs',[]) if item['job_id']==reference['job_id'] and item['review_digest']==reference['review_digest']),None)
            if item is None:raise physical.native.HostError('Original recovered server reference is unavailable')
            value=physical._action(self.service,server,'reconcile',{'job_id':item['job_id'],'credentials':ssh},scheduled_policy_id=grant['job_id'])
            remote=value.get('remote_observation') or {}
            if (remote.get('sql_identity',{}).get('server_uuid')!=original['source']['server_uuid'] or
                    remote.get('runtime_process')!=reference['runtime_process'] or not backups.ended(jobs.load(item['job_id'],owner,endpoint.id))):
                raise physical.native.HostError('Stop and independently confirm the original recovered server before releasing its SQL-lock protection')
            bridge.confirm_raw_utility_termination(original['source_state'].get('recovery_binding'),job_id)
            binding=original['source_state'].get('recovery_binding')
            if binding:
                try:bridge.bridges.detach(binding)
                except Exception:
                    if binding.get('id') in bridge.bridges.entries:raise
            accepted.update(original,recovery_fence_release_confirmed=True,original_target_termination_observed=True)
            accepted.release_fence(original)
        super().release(server,jobs,grant,records,occurrence,ssh,authorize)


def init_app(app,service):
    from ..operations.store import JsonOperationStore
    if not isinstance(getattr(service.operation_bus,'store',None),JsonOperationStore):return
    import atexit
    scheduler=ScheduleHost(app,service);service.mysql_check_scheduler=scheduler
    app.register_before_app_start(scheduler.start);atexit.register(scheduler.close)
