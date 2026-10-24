"""Revocable recurring full backups and isolated native startup drills."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time

from . import mysql_physical_service as physical
from . import mysql_physical_retention_schedule as retained
from . import mysql_physical_retention as retention
from . import mysql_host_service as host
from .mysql_binlog_jobs import MySQLBinlogJobs,digest
from .mysql_physical_batch_retention import scope,ended
from .mysql_monitoring_host import MySQLMonitoringHost

native=retained.native


class BackupJobs(retained.ScheduleJobs):
    operation='mysql_scheduled_physical_backup'
    review_warnings=(
        'Authorize future full native backups of this exact source and pinned SSH workspace, including native backup/read locks and archive protection. Explicitly delegate SSH and the registered single-factor SQL password encrypted until expiry or revocation.',
        'An optional startup drill prepares and copies separate files, starts an isolated read-only native MySQL with a private Unix socket, then stops it. Events, replication autostart and upgrades stay disabled. SQL startup is distinct from full data/definition recovery acceptance.',
        'Each occurrence and native dispatch is durable before execution. Interrupted work is never automatically repeated. Disable stops future admissions; admitted native work can continue until its reviewed timeout. Original outcomes and protection remain until independently resolved.',
    )


class Occurrences(MySQLBinlogJobs):
    operation='mysql_physical_backup_occurrence'
    review_warnings=BackupJobs.review_warnings

    def public(self,record):
        return {**super().public(record),'database_recovery_verified':False,'production_cutover_verified':False,
            'startup_drill_outcome':record.get('startup_drill_outcome','not_observed')}


def options(value):
    if not isinstance(value,dict) or set(value)!={'physical','drill','interval_seconds','expires_after_days'}:
        raise native.HostError('Select full physical options, startup drill, interval and expiry')
    selected=physical.options(value['physical'])
    if selected['phase']!='backup':raise native.HostError('A recurring full backup has no input job')
    drill=value['drill']
    if drill is not None and (not isinstance(drill,dict) or not {'mysqld','gtid_mode','timeout_seconds'}<=set(drill) or set(drill)-{'mysqld','gtid_mode','timeout_seconds','recovery_tls','recovery_port'} or
            not isinstance(drill['mysqld'],str) or not drill['mysqld'].startswith('/') or '\0' in drill['mysqld'] or len(drill['mysqld'])>4096 or
            drill['gtid_mode'] not in {'OFF','OFF_PERMISSIVE','ON_PERMISSIVE','ON'} or
            type(drill['timeout_seconds']) is not int or not 30<=drill['timeout_seconds']<=3600):
        raise native.HostError('Select an absolute native mysqld, GTID mode and startup drill lifetime of30–3600 seconds')
    if drill is not None:
        physical.options({**selected,'phase':'recover','input_job_id':'00000000-0000-0000-0000-000000000001',
            'mysqld':drill['mysqld'],'recovery_gtid_mode':drill['gtid_mode'],
            **{key:drill[key] for key in ('recovery_tls','recovery_port') if key in drill}})
    retained.options({'policy':{'retention_days':0,'keep_latest':1},**{key:value[key] for key in ('interval_seconds','expires_after_days')}})
    return {**deepcopy(value),'physical':selected}


def program(jobs,anchor,peer):
    return {**retained.program(jobs,anchor,peer),'backup_scheduler_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


@contextmanager
def sql_client(service,server,secret,principal,*,tool_credentials=False):
    """One connection owner; never replace an interactive client's resolver."""
    from ..providers.mysql_family.provider import MySQLDBAPIClient
    from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
    from ..security.secrets import SecretLease
    context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
    original=service.endpoint_service.provider_registry.resolve(context).instance.client
    route={key:value for key,value in payload['route'].items() if key not in POOL_ARGUMENTS and key not in
        {'credential_references','credential_reference_id','credential_kinds','credential_kind','principal_reference'}}
    route.update(user=secret['user'])
    reference='physical-backup:'+principal
    if secret['password']:route.update(credential_reference_id=reference,principal_reference=principal,credential_kind='database_password')
    def acquire(selected,owner,purpose,kind):
        if (selected,owner,kind)!=(reference,principal,'database_password') or purpose not in ({'connect','provider_tool'} if tool_credentials else {'connect'}):raise native.HostError('Physical SQL delegation scope changed')
        return SecretLease(secret['password'])
    client=MySQLDBAPIClient(replace(original.config,secret_acquirer=acquire),module=original.module)
    try:yield client,route
    finally:client.close()


class ScheduleHost(retained.ScheduleHost):
    program=staticmethod(program)

    def __init__(self,app,service):
        super().__init__(app,service)
        path=service.operation_bus.store.path
        root=app.config.get('CDEADMIN_MYSQL_BACKUP_SCHEDULE_ROOT') or str(path.parent/'mysql-backup-schedules')
        self.jobs=BackupJobs(str(path)+'.mysql-backup-schedules',root);self.enabled=self.jobs.root/'enabled'

    def anchor(self,grant,jobs):return deepcopy(grant['source_state']['template'])

    def validate_credentials(self,value):
        if (not isinstance(value,dict) or set(value)!={'ssh','database'} or not isinstance(value['database'],dict) or
                not {'user','password'}<=set(value['database']) or set(value['database'])-{'user','password','tls'}):
            raise native.HostError('Physical backup requires scoped SSH and SQL delegation')
        sql=value['database']
        if any(not isinstance(sql[key],str) or '\0' in sql[key] or len(sql[key].encode('utf8'))>limit for key,limit in [('user',1024),('password',16384)]) or not sql['user']:
            raise native.HostError('Physical SQL delegation is invalid')
        if 'tls' in sql and (not isinstance(sql['tls'],dict) or set(sql['tls'])!={'policy','files'} or
                len(json.dumps(sql['tls'],ensure_ascii=True))>600000):
            raise native.HostError('Physical TLS delegation is invalid or exceeds its bound')
        return {'ssh':host.credentials(value['ssh']),'database':deepcopy(sql)}

    def ssh_credentials(self,value):return value['ssh']

    def delegation(self,server,request,grant):
        value=self.validate_credentials({'ssh':request['credentials'],'database':physical.delegate(self.service,server)})
        with sql_client(self.service,server,value['database'],'worker:'+grant['job_id']) as admitted:
            captured=physical.source(self.service,server,admitted=admitted,keyring=grant['options']['physical'].get('keyring'),isolate_external_paths=grant['options']['physical'].get('isolate_external_paths',False))
        if captured['identity']!=grant['source'] or captured['state']['host_binding']!=grant['source_state']['template']['source_state']['host_binding']:
            raise native.HostError('Reviewed backup source changed before SQL delegation')
        return value

    def occurrences(self,grant):
        return Occurrences(str(self.jobs.path)+'.occurrences',self.jobs.root/'occurrences'/grant['job_id'])

    @contextmanager
    def removal_guard(self,server):
        from ..endpoints.service import EndpointRegistrationError
        from .mysql_physical_batch_retention import inventory
        path=self.service.operation_bus.store.path
        jobs=getattr(self.service,'mysql_physical_jobs',None) or physical.PhysicalJobs(str(path)+'.mysql-physical',
            self.app.config.get('CDEADMIN_MYSQL_PHYSICAL_ROOT') or path.parent/'mysql-physical-receipts')
        owner=server.user_id;endpoint=server.endpoint_profile.id
        with retention.admission(jobs):
            for scheduler in (self,getattr(self.service,'mysql_physical_scheduler',None),getattr(self.service,'mysql_check_scheduler',None)):
                if scheduler is None:continue
                offset=0
                while True:
                    page=scheduler.jobs.list(owner,endpoint,offset=offset,limit=100)
                    if page['unavailable_job_ids'] or any(item['state']=='enabled' for item in page['jobs']):
                        raise EndpointRegistrationError('Disable physical policies before removing their connection profile')
                    if not page['more']:break
                    offset+=100
                    if offset>=10000:raise EndpointRegistrationError('Physical policy inventory exceeds its removal bound')
            if any(record.get('backup_workflow_protected') or record.get('recovery_check_holds') for record in inventory(jobs,owner,endpoint).values()):
                raise EndpointRegistrationError('Reconcile native backup work and release its workflow protection before removing this profile')
            yield

    def action(self,server,jobs,owner,endpoint,operation,request):
        action=operation.removeprefix('backup_schedule_')
        if action=='review' and set(request)=={'options','credentials'}:
            if not self.keys.available:raise native.HostError('Configure physical worker encryption keys before scheduling backups')
            selected=options(request['options'])
            with retention.admission(jobs):
                captured=physical.source(self.service,server,keyring=selected['physical'].get('keyring'),isolate_external_paths=selected['physical'].get('isolate_external_paths',False))
                template={'options':selected['physical'],'source':captured['identity'],'source_state':{**captured['state'],'remote_review':{}},'job_id':'','review_digest':''}
                channel=native.Transport(selected['physical']['connection'],host.credentials(request['credentials']))
                try:
                    peer=channel.connect();template['source_state']['remote_review']=channel.request(physical.remote_request(template,'inspect'))
                    return self.jobs.review(owner,endpoint.id,selected,{'identity':captured['identity'],
                        'state':{'template':template,'scope_digest':scope(template),'preview':{'phases':['backup','prepare','copy_back','recover','stop'] if selected['drill'] else ['backup'],
                        'sql_startup_is_full_recovery_acceptance':False}}},digest(MySQLMonitoringHost._configuration(server)),self.program(jobs,template,peer),continuation={'server_id':server.id})
                finally:channel.close()
        if action in {'occurrences','occurrence'}:
            grant=self.jobs.load(request['job_id'],owner,endpoint.id);records=self.occurrences(grant)
            if action=='occurrences' and not set(request)-{'job_id','offset','limit'}:return records.list(owner,endpoint.id,**{k:v for k,v in request.items() if k!='job_id'})
            if action=='occurrence' and set(request)=={'job_id','occurrence_id'}:return records.get(request['occurrence_id'],owner,endpoint.id)
            raise native.HostError('Select a scoped backup occurrence or page')
        if action=='release':
            if set(request)!={'job_id','occurrence_id','confirmed','schedule_confirmation','credentials'} or request['confirmed'] is not True or request['schedule_confirmation']!=request['job_id']:
                raise native.HostError('Confirm the exact backup policy and original occurrence to release')
            grant=self.jobs.load(request['job_id'],owner,endpoint.id)
            if grant['state']=='enabled':raise native.HostError('Disable the backup policy before releasing an interrupted occurrence')
            records=self.occurrences(grant);occurrence=records.load(request['occurrence_id'],owner,endpoint.id)
            with retention.admission(jobs):
                self.release(server,jobs,grant,records,occurrence,host.credentials(request['credentials']))
            return records.get(occurrence['job_id'],owner,endpoint.id)
        if action=='enable':
            request=dict(request)
            if request.pop('delegate_database_credentials',None) is not True:raise native.HostError('Explicitly delegate the registered SQL password for this expiring backup policy')
        return super().action(server,jobs,owner,endpoint,'retention_schedule_'+action,request)

    def release(self,server,jobs,grant,records,occurrence,ssh,authorize=None):
        observed=[]
        for item in occurrence.get('native_jobs',[]):
            if authorize is not None:authorize()
            record=jobs.load(item['job_id'],grant['owner'],grant['endpoint_id'])
            if record['review_digest']!=item['review_digest'] or record['source_state'].get('backup_schedule_id')!=grant['job_id']:
                raise native.HostError('Original scheduled native job binding changed')
            value=physical._action(self.service,server,'cancel' if record['state']=='reviewed' else 'reconcile',{'job_id':record['job_id'],'credentials':ssh},scheduled_policy_id=grant['job_id'])
            current=jobs.load(record['job_id'],grant['owner'],grant['endpoint_id'])
            if not (current['state']=='cancelled' and current.get('native_may_have_dispatched') is False) and not ended(current):
                raise native.HostError('Confirm every original native process and credential cleanup before releasing the occurrence')
            observed.append(current)
        for record in observed:jobs.update(record,backup_workflow_protected=False)
        records.update(occurrence,protection_released=True,released_job_ids=[record['job_id'] for record in observed],released_at=time.time())

    def step(self,server,jobs,grant,records,occurrence,secret,selected,*,on_ready=None):
        def require():return self.require(grant,occurrence['job_id'])
        def capture():
            with sql_client(self.service,server,secret['database'],'worker:'+grant['job_id']) as admitted:
                value=physical.source(self.service,server,admitted=admitted,keyring=selected.get('keyring'),isolate_external_paths=selected.get('isolate_external_paths',False))
            if value['identity']!=grant['source'] or value['state']['host_binding']!=self.anchor(grant,jobs)['source_state']['host_binding']:
                raise native.HostError('Scheduled physical source identity changed')
            return value
        def bind(value):
            current=records.load(occurrence['job_id'],grant['owner'],grant['endpoint_id'])
            records.update(current,native_jobs=[*current.get('native_jobs',[]),{'job_id':value['job_id'],'review_digest':value['review_digest'],'phase':selected['phase']}],current_phase=selected['phase'])
        def call(operation,body):
            with retention.admission(jobs):
                require()
                return physical._action(self.service,server,operation,{**body,'credentials':secret['ssh']},source_capture=capture,
                    database_credentials=secret['database'],on_review=bind,scheduled_policy_id=grant['job_id'],scheduled_operation=grant['operation'],authorize=require)
        value=call('review',{'options':selected})
        expected=self.anchor(grant,jobs)['source_state']['remote_review']
        if any(key in value['remote_review'] and value['remote_review'][key]!=expected[key] for key in ('mysql','xtrabackup','mysqld') if key in expected):
            raise native.HostError('Scheduled physical executable changed after policy review')
        value=call('start',{'job_id':value['job_id'],'review_digest':value['review_digest'],'confirmed':True,'delegate_database_credentials':True})
        deadline=time.monotonic()+selected['timeout_seconds']+180
        ready=False;stopping=False;failure=None
        while time.monotonic()<deadline:
            value=call('reconcile',{'job_id':value['job_id']})
            if value['state']=='unknown':raise native.HostError('Original scheduled native outcome is unknown; independently inspect it')
            remote=value.get('remote_observation') or {}
            if selected['phase']=='recover' and value['recovery_running'] and not stopping:
                ready=True
                if on_ready is not None:
                    try:on_ready(value)
                    except Exception as error:failure=error
                value=call('cancel',{'job_id':value['job_id']});stopping=True
            elif remote.get('supervisor_finished'):
                if remote.get('return_code')!=0 or remote.get('error_type') or not value['native_process_termination_confirmed'] or remote.get('credential_cleanup_confirmed') is not True:
                    raise native.HostError('Scheduled native work did not confirm successful completion and cleanup')
                if selected['phase']=='recover' and not ready:raise native.HostError('Native startup drill did not observe SQL readiness')
                if selected['phase']!='recover' and not value['file_verification_confirmed']:raise native.HostError('Scheduled physical files remain unverified')
                if failure is not None:raise failure
                return value
            self.stop.wait(.25)
        raise native.HostError('Original scheduled native process exceeded its observation deadline')

    def perform(self,server,jobs,grant,records,occurrence,secret):
        selected=deepcopy(grant['options']['physical']);backup=self.step(server,jobs,grant,records,occurrence,secret,selected)
        drill=grant['options']['drill']
        if drill:
            parent=backup
            for phase in ('prepare','copy_back','recover'):
                selected={**deepcopy(grant['options']['physical']),'phase':phase,'input_job_id':parent['job_id']}
                if phase=='recover':selected.update(mysqld=drill['mysqld'],recovery_gtid_mode=drill['gtid_mode'],recovery_port=0,recovery_mode='read_only',timeout_seconds=drill['timeout_seconds'])
                if phase=='recover':selected.update({key:deepcopy(drill[key]) for key in ('recovery_tls','recovery_port') if key in drill})
                parent=self.step(server,jobs,grant,records,occurrence,secret,selected)
            records.update(occurrence,startup_drill_outcome='passed')
        return {'backup_job_id':backup['job_id']}

    def tick(self,job_id,*,force=False):
        from .continuous_binlog_tails import file_claim
        from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
        grant=self.read(job_id)
        try:
            with file_claim(self.jobs.directory(grant)),self.app.app_context():
                grant=self.read(job_id);secret={};records=self.occurrences(grant);occurrence=None
                if grant['state']!='enabled':return self.jobs.public(grant)
                try:
                    if grant.get('scan_state'):raise native.HostError('The previous backup occurrence was interrupted; inspect and release it before a new policy')
                    if grant.get('valid_until',0)<=time.time():raise native.HostError('Backup policy expired')
                    if not force and grant.get('next_scan_at',0)>time.time():return self.jobs.public(grant)
                    server,jobs,owner,endpoint=self.require(grant)
                    previous=grant.get('last_occurrence_id')
                    if previous and records.get(previous,owner,endpoint.id)['state']!='completed':raise native.HostError('The previous backup occurrence remains unresolved')
                    secret=self.credentials(grant);self.jobs.update(grant,scan_state='preparing')
                    value=records.review(owner,endpoint.id,grant['options'],{'identity':grant['source'],'state':{}},grant['configuration'],grant['program'],continuation={'policy_id':job_id})
                    occurrence=records.load(value['job_id'],owner,endpoint.id)
                    self.jobs.update(grant,last_occurrence_id=value['job_id'],scan_state='running')
                    records.update(occurrence,state='running',native_jobs=[],startup_drill_outcome='not_requested' if grant['options'].get('drill') is None else 'not_observed')
                    result=self.perform(server,jobs,grant,records,occurrence,secret)
                    current=records.load(occurrence['job_id'],owner,endpoint.id)
                    with retention.admission(jobs):self.release(server,jobs,grant,records,current,secret['ssh'],authorize=lambda:self.require(grant,occurrence['job_id']))
                    records.update(occurrence,state='completed',finished_at=time.time(),**result)
                    self.jobs.update(grant,scan_state=None,last_scan_at=time.time(),next_scan_at=time.time()+grant['options']['interval_seconds'])
                except Exception as error:
                    if occurrence is not None:records.update(occurrence,state='interrupted',error_type=type(error).__name__,original_native_outcomes_unchanged=True)
                    self.suspend(grant,error)
                finally:
                    for value in secret.values():
                        if isinstance(value,dict):value.clear()
                    secret.clear()
                return self.jobs.get(job_id,grant['owner'],grant['endpoint_id'])
        except BinlogArchiveError as error:
            if str(error).startswith('Another operation'):return self.jobs.get(job_id,grant['owner'],grant['endpoint_id'])
            raise


def init_app(app,service):
    from ..operations.store import JsonOperationStore
    if not isinstance(getattr(service.operation_bus,'store',None),JsonOperationStore):return
    import atexit
    scheduler=ScheduleHost(app,service);service.mysql_backup_scheduler=scheduler
    app.register_before_app_start(scheduler.start);atexit.register(scheduler.close)
