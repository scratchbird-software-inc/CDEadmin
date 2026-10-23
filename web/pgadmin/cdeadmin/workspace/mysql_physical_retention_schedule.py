"""Expiring SSH delegation for independently scheduled physical retention."""
import atexit
import hashlib
import json
import os
from pathlib import Path
import socket
import threading
import time

from ..operations.fileio import private_directory,private_file
from ..report_scheduler.crypto import WorkerKeyRing
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from . import mysql_physical_batch_retention as batch
from . import mysql_physical_retention as individual
from . import mysql_physical_service as physical
from .continuous_binlog_tails import file_claim
from .mysql_binlog_jobs import MySQLBinlogJobs,digest,review_digest
from .mysql_monitoring_host import MySQLMonitoringHost
from .mysql_retention_schedule import ScheduleHost as ArchiveHost

native=batch.native


class ScheduleJobs(MySQLBinlogJobs):
    operation='mysql_scheduled_physical_retention'
    review_warnings=(
        'Authorize future physical retention scans, including later jobs in this exact original source, principal, SSH host/account and workspace. Each occurrence contains at most100 fixed jobs and retains the full-backup floor.',
        'Delegate SSH authentication encrypted with the configured worker key, only until policy expiry or revocation. Source SQL credentials are not delegated.',
        'Scans continue without an open viewer. Disable stops future admissions; already admitted host work can continue. Interrupted occurrences suspend future scans and require independent observation and a new policy review.',
        'Original native outcomes, recovery acceptance, archive protection and production cutover remain separate.',
    )

    def public(self,record):
        return {**super().public({k:v for k,v in record.items() if k!='ssh_envelope'}),
            'preview':record['source_state']['preview'],'automatic_future_scans':record['state']=='enabled',
            'automatic_occurrence_retry':False,'ssh_delegation_present':bool(record.get('ssh_envelope'))}


def options(value):
    if not isinstance(value,dict) or set(value)!={'policy','interval_seconds','expires_after_days'}:
        raise native.HostError('Select a physical age/count policy, scan interval and expiry')
    batch.policy(value['policy'])
    if type(value['interval_seconds']) is not int or not 60<=value['interval_seconds']<=31536000 or type(value['expires_after_days']) is not int or not 1<=value['expires_after_days']<=365:
        raise native.HostError('Select a scan interval of60 seconds to one year and a policy lifetime of1–365 days')
    return dict(value)


def program(jobs,anchor,peer):
    return {**batch.program(peer,anchor),'scheduler_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'application_host':socket.gethostname(),'physical_root':str(jobs.root.resolve()),'physical_store':str(jobs.path.resolve())}


def aad(grant):
    return {'purpose':ScheduleJobs.operation,**{k:grant[k] for k in ('job_id','owner','endpoint_id','review_digest','configuration')}}


class ScheduleHost(ArchiveHost):
    def __init__(self,app,service):
        super().__init__(app,service)
        path=service.operation_bus.store.path
        root=app.config.get('CDEADMIN_MYSQL_PHYSICAL_SCHEDULE_ROOT') or str(path.parent/'mysql-physical-schedules')
        self.jobs=ScheduleJobs(str(path)+'.mysql-physical-schedules',root);self.enabled=self.jobs.root/'enabled'
        self.keys=WorkerKeyRing(app.config.get('CDEADMIN_MYSQL_PHYSICAL_WORKER_KEYS',{}),app.config.get('CDEADMIN_MYSQL_PHYSICAL_WORKER_ACTIVE_KEY_ID'))

    def close(self):
        self.stop.set();thread=self.thread
        if thread is not None and thread is not threading.current_thread():thread.join(timeout=5)
        return not (thread and thread.is_alive())

    def authority(self,grant):
        from pgadmin.model import Server,User
        server=Server.query.filter_by(id=grant['continuation']['server_id'],user_id=grant['owner']).first()
        if User.query.filter_by(id=grant['owner'],active=True).first() is None or server is None or server.endpoint_profile is None or server.endpoint_profile.id!=grant['endpoint_id']:
            raise native.HostError('Physical policy owner or registration is unavailable')
        jobs,owner,endpoint=physical.manager(self.service,server)
        anchor=jobs.load(grant['options']['scope_job_id'],owner,endpoint.id)
        if (grant['configuration']!=digest(MySQLMonitoringHost._configuration(server)) or
                batch.scope(anchor)!=grant['source_state']['scope_digest'] or
                program(jobs,anchor,grant['program']['execution_host'])!=grant['program']):
            raise native.HostError('Physical policy registration, source, adapter or execution host changed')
        return server,jobs,owner,endpoint

    def require(self,grant,occurrence=None):
        current=self.read(grant['job_id'])
        if (current['state']!='enabled' or current.get('valid_until',0)<=time.time() or self.stop.is_set() or
                review_digest(current)!=current['review_digest'] or occurrence is not None and current.get('last_occurrence_id')!=occurrence):
            raise native.HostError('Physical retention policy is revoked, expired, interrupted or changed')
        return self.authority(current)

    def credentials(self,grant):
        value=bytearray(self.keys.decrypt(grant['ssh_envelope'],aad(grant)))
        try:
            from .mysql_host_service import credentials
            return credentials(json.loads(value))
        finally:value[:]=b'\0'*len(value)

    def suspend(self,grant,error):
        with self.jobs.store(grant['job_id']) as store:
            def change(state):
                current=self.jobs.record(state,grant['job_id'],grant['owner'],grant['endpoint_id'])
                if current['state']=='enabled':current.update(state='expired' if current.get('valid_until',0)<=time.time() else 'attention_required',
                    ssh_envelope=None,suspended_at=time.time(),error_type=type(error).__name__,
                    error_message=str(error) if isinstance(error,(native.HostError,BinlogArchiveError)) else 'Scheduled physical retention could not complete; inspect its occurrence and worker key authority.',automatic_retry=False)
            store.change(change)
        self.marker(grant['job_id']).unlink(missing_ok=True)

    def tick(self,job_id,*,force=False):
        grant=self.read(job_id)
        try:
            with file_claim(self.jobs.directory(grant)):
                with self.app.app_context():
                    grant=self.read(job_id);secret={}
                    if grant['state']!='enabled':return self.jobs.public(grant)
                    try:
                        if grant.get('scan_state'):raise native.HostError('The previous physical scan was interrupted; inspect its occurrence and review a new policy')
                        if grant.get('valid_until',0)<=time.time():raise native.HostError('Physical policy expired')
                        if not force and grant.get('next_scan_at',0)>time.time():return self.jobs.public(grant)
                        server,jobs,owner,endpoint=self.require(grant)
                        previous=grant.get('last_occurrence_id')
                        if previous and batch.manager(self.service,jobs).get(previous,owner,endpoint.id)['state']!='completed':
                            raise native.HostError('The previous physical occurrence is unresolved')
                        secret=self.credentials(grant)
                        self.jobs.update(grant,scan_state='preparing',scan_started_at=time.time())
                        def bind(value):
                            self.jobs.update(grant,last_occurrence_id=value['job_id'],scan_state='running')
                        with individual.admission(jobs):
                            self.require(grant)
                            value=batch.action(self.service,server,jobs,owner,endpoint,'retention_batch_review',
                                {'scope_job_id':grant['options']['scope_job_id'],'policy':grant['options']['policy'],'credentials':secret},
                                scheduled_policy_id=job_id,on_review=bind)
                        if value['state']=='nothing_eligible':
                            self.jobs.update(grant,scan_state=None,last_scan_empty=True,last_scan_at=time.time(),next_scan_at=time.time()+grant['options']['interval_seconds'])
                        else:
                            while value['state'] in {'reviewed','paused'}:
                                with individual.admission(jobs):
                                    self.require(grant,value['job_id'])
                                    value=batch.action(self.service,server,jobs,owner,endpoint,'retention_batch_advance',
                                        {'job_id':value['job_id'],'review_digest':value['review_digest'],'confirmed':True,'batch_confirmation':value['job_id'],'credentials':secret},scheduled_policy_id=job_id)
                            if value['state']!='completed':raise native.HostError('Physical occurrence needs independent inspection')
                            self.jobs.update(grant,scan_state=None,last_scan_empty=False,last_scan_at=time.time(),next_scan_at=time.time()+grant['options']['interval_seconds'])
                    except Exception as error:self.suspend(grant,error)
                    finally:secret.clear()
                    return self.jobs.get(job_id,grant['owner'],grant['endpoint_id'])
        except BinlogArchiveError as error:
            if str(error).startswith('Another operation'):return self.jobs.get(job_id,grant['owner'],grant['endpoint_id'])
            raise

    def action(self,server,jobs,owner,endpoint,operation,request):
        if operation=='retention_schedule_list' and not set(request)-{'offset','limit'}:return self.jobs.list(owner,endpoint.id,**request)
        if operation=='retention_schedule_status' and set(request)=={'job_id'}:return self.jobs.get(request['job_id'],owner,endpoint.id)
        if operation=='retention_schedule_review' and set(request)=={'scope_job_id','options','credentials'}:
            if not self.keys.available:raise native.HostError('Configure physical worker encryption keys before delegating scheduled SSH access')
            selected=options(request['options']);anchor=jobs.load(request['scope_job_id'],owner,endpoint.id)
            from .mysql_host_service import credentials
            secret=credentials(request['credentials']);channel=native.Transport(anchor['options']['connection'],secret)
            try:
                peer=channel.connect()
                with individual.admission(jobs):
                    observed=channel.request(physical.remote_request(anchor,'status'))
                    if observed.get('input_digest')!=anchor['review_digest']:raise native.HostError('Original physical host receipt is unavailable')
                    records,registered=batch.records_for_plan(self.service,jobs,owner,endpoint.id)
                    planned=batch.plan(records,anchor,selected['policy'],time.time()-selected['policy']['retention_days']*86400,registered=registered)
                    result=self.jobs.review(owner,endpoint.id,{'scope_job_id':anchor['job_id'],**selected},
                        {'identity':anchor['source'],'state':{'scope_digest':batch.scope(anchor),'preview':planned}},
                        digest(MySQLMonitoringHost._configuration(server)),program(jobs,anchor,peer),continuation={'server_id':server.id})
                    return result
            finally:channel.close();secret.clear()
        fields={'job_id','confirmed','schedule_confirmation'}|({'review_digest','delegate_ssh_credentials','credentials'} if operation=='retention_schedule_enable' else set())
        if operation not in {'retention_schedule_enable','retention_schedule_disable','retention_schedule_scan','retention_schedule_rotate'} or set(request)!=fields or request['confirmed'] is not True or request['schedule_confirmation']!=request['job_id']:
            raise native.HostError('Confirm the exact physical schedule and type its UUID')
        grant=self.jobs.load(request['job_id'],owner,endpoint.id)
        if operation=='retention_schedule_disable':
            self.jobs.update(grant,state='disabled',ssh_envelope=None,disabled_at=time.time())
            self.marker(grant['job_id']).unlink(missing_ok=True)
        elif operation=='retention_schedule_scan':
            self.require(grant);self.jobs.update(grant,next_scan_at=0);self.start()
        elif operation=='retention_schedule_rotate':
            with self.jobs.store(grant['job_id']) as store:
                def rotate(state):
                    current=self.jobs.record(state,grant['job_id'],owner,endpoint.id)
                    if current['state'] not in {'reviewed','enabled'} or not current.get('ssh_envelope'):raise native.HostError('This physical SSH delegation is unavailable')
                    current['ssh_envelope']=self.keys.rotate(current['ssh_envelope'],aad(current))
                store.change(rotate)
        else:
            if request['delegate_ssh_credentials'] is not True or request['review_digest']!=grant['review_digest'] or review_digest(grant)!=grant['review_digest']:
                raise native.HostError('Confirm the reviewed physical schedule and encrypted SSH delegation')
            if grant['state']!='reviewed':return self.jobs.public(grant)
            self.authority(grant)
            from .mysql_host_service import credentials
            secret=credentials(request['credentials']);anchor=jobs.load(grant['options']['scope_job_id'],owner,endpoint.id)
            channel=native.Transport(anchor['options']['connection'],secret)
            try:
                if program(jobs,anchor,channel.connect())!=grant['program']:raise native.HostError('Reviewed physical schedule host changed')
                envelope=self.keys.encrypt(json.dumps(secret).encode('utf8'),aad(grant))
            finally:channel.close();secret.clear()
            self.enabled.mkdir(parents=True,exist_ok=True,mode=0o700);private_directory(self.enabled)
            from .mysql_archive_retention import directory_identity
            directory_identity(self.enabled)
            with self.jobs.store(grant['job_id']) as store:
                def enable(state):
                    current=self.jobs.record(state,grant['job_id'],owner,endpoint.id)
                    if current['state']!='reviewed':return
                    if current['expires_at']<time.time():raise native.HostError('Physical schedule review expired')
                    marker=self.marker(grant['job_id'])
                    if marker.exists() or marker.is_symlink():raise native.HostError('Physical schedule marker already exists')
                    with marker.open('xb') as stream:private_file(marker);stream.flush();os.fsync(stream.fileno())
                    if os.name!='nt':
                        descriptor=os.open(self.enabled,os.O_RDONLY|os.O_DIRECTORY)
                        try:os.fsync(descriptor)
                        finally:os.close(descriptor)
                    current.update(state='enabled',ssh_envelope=envelope,valid_until=time.time()+current['options']['expires_after_days']*86400,next_scan_at=time.time(),enabled_at=time.time())
                store.change(enable)
            self.start()
        return self.jobs.get(grant['job_id'],owner,endpoint.id)


def init_app(app,service):
    from ..operations.store import JsonOperationStore
    if not isinstance(getattr(service.operation_bus,'store',None),JsonOperationStore):return
    host=ScheduleHost(app,service);service.mysql_physical_scheduler=host
    app.register_before_app_start(host.start);atexit.register(host.close)
