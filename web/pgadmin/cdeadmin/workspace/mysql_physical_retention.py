"""Owner-scoped physical retention, independently observed on the pinned host."""
from contextlib import contextmanager
import time
import uuid

from ..operations.fileio import exclusive_file_lock,private_file
from ..providers.mysql_family import mysql_physical_transport as native
from .mysql_binlog_jobs import MySQLBinlogJobs,digest,review_digest
from . import mysql_physical_service as physical


@contextmanager
def admission(jobs):
    path=jobs.path.with_name(jobs.path.name+'.lifecycle.lock')
    with path.open('a+b') as stream:
        private_file(path)
        with exclusive_file_lock(stream.fileno()):yield


def dependencies(jobs,record,owner,endpoint):
    children=[];index=jobs.scope(owner,endpoint)/'index'
    entries=list(index.iterdir()) if index.exists() else []
    if len(entries)>10000:raise native.HostError('Physical retention dependency inventory exceeds 10000 jobs')
    for entry in entries:
        if entry.name.startswith('.'):continue
        item=jobs.load(entry.name.split('_',1)[-1],owner,endpoint)
        if item['options'].get('input_job_id')!=record['job_id'] or item.get('artifact_removed'):continue
        if item['state']=='cancelled' and item.get('native_may_have_dispatched') is False:continue
        children.append(item['job_id'])
    from .mysql_recovery_connections import targets
    registrations=targets(owner,record) if record['options']['phase']=='recover' else []
    if children or registrations:
        raise native.HostError('Retain this physical artifact until dependent jobs are removed or cancelled before dispatch, and recovery registrations are removed')
    if record.get('retention_pinned'):raise native.HostError('Unpin this protected physical artifact before retention')
    return {'physical_dependencies':children,'recovery_registrations':[]}


class RetentionJobs(MySQLBinlogJobs):
    operation='mysql_physical_retention'
    review_warnings=(
        'Removes only the reviewed physical artifact, recovered data copy and its private replay binary logs on the pinned SSH host. Original native receipts and output are retained.',
        'Remove dependent artifacts first. Stop managed recovery, reconcile native termination and remove its recovery registrations before retaining their parent inputs.',
        'An interrupted removal keeps its exact intent. Independent inspection never reclassifies the original backup or recovery outcome. Resume only that reviewed intent; an unclaimed review can be explicitly invalidated.',
        'Binary-log archive protection and production cutover remain separate workflows.',
    )


def manager(service,jobs):
    with service._semantic_lock:
        value=getattr(service,'mysql_physical_retention_jobs',None)
        if value is None:
            value=service.mysql_physical_retention_jobs=RetentionJobs(str(jobs.path)+'.retention',str(jobs.root)+'.retention')
        return value


def action(service,server,jobs,owner,endpoint,operation,request,*,batch_reservation=None,batch_floor=None):
    from .mysql_host_service import credentials
    from .mysql_monitoring_host import MySQLMonitoringHost
    tickets=manager(service,jobs)
    if operation=='retention_status' and set(request)=={'job_id'}:return tickets.get(request['job_id'],owner,endpoint.id)
    if operation=='retention_pin' and set(request)=={'job_id','pinned'}:
        if type(request['pinned']) is not bool:raise native.HostError('Select an explicit physical retention pin')
        record=jobs.load(request['job_id'],owner,endpoint.id)
        if record.get('artifact_removed') or record.get('artifact_removal'):raise native.HostError('Physical artifact has already entered retention')
        jobs.update(record,retention_pinned=request['pinned']);return jobs.get(record['job_id'],owner,endpoint.id)
    if operation=='retention_review' and set(request)=={'job_id','credentials'}:
        record=jobs.load(request['job_id'],owner,endpoint.id);ticket=None
        if record.get('artifact_removed') or record.get('artifact_removal') or record.get('retention_batch_id'):raise native.HostError('Inspect the original physical retention intent or its owning batch')
        selected={'source_job_id':record['job_id'],'retention_id':str(uuid.uuid4())}
    elif operation in {'retention_start','retention_reconcile','retention_abandon'}:
        fields={'job_id','credentials'}|({'review_digest','confirmed','job_confirmation'} if operation!='retention_reconcile' else set())
        if set(request)!=fields:raise native.HostError('Select the exact physical retention review and private SSH authentication')
        ticket=tickets.load(request['job_id'],owner,endpoint.id);selected=ticket['options']
        if selected.get('batch_reservation_id') and selected['batch_reservation_id']!=batch_reservation:
            raise native.HostError('Use the owning physical retention batch for this reviewed item')
        record=jobs.load(selected['source_job_id'],owner,endpoint.id)
        prior=record.get('artifact_removal')
        if prior and prior['retention_job_id']!=ticket['job_id']:
            raise native.HostError('Another original physical removal intent owns this artifact')
        if operation!='retention_reconcile' and (request['confirmed'] is not True or request['review_digest']!=ticket['review_digest'] or
                review_digest(ticket)!=ticket['review_digest'] or request['job_confirmation']!=record['job_id']):
            raise native.HostError('Confirm the exact physical retention review and type its original physical job UUID')
        if ticket['state'] in {'removed','not_dispatched'}:return tickets.get(ticket['job_id'],owner,endpoint.id)
        if operation=='retention_abandon' and not prior and record.get('retention_review_job_id')!=ticket['job_id'] and not selected.get('batch_reservation_id'):
            raise native.HostError('Select the current physical retention review')
    else:raise native.HostError('Select an explicit physical retention action')
    configuration=digest(MySQLMonitoringHost._configuration(server))
    if ticket and (ticket['configuration']!=configuration or any(ticket['program'].get(key)!=value for key,value in native.program().items())):
        raise native.HostError('Retention registration or host adapter changed; preserve the original intent')
    transport=native.Transport(record['options']['connection'],credentials(request['credentials']))
    try:
        peer=transport.connect();program={**native.program(),'execution_host':{**peer,'kind':'database-server-ssh-host','workspace':record['options']['workspace']}}
        remote={**physical.remote_request(record,'retention_inspect'),'retention_id':selected['retention_id']}
        if operation=='retention_review':
            dependencies(jobs,record,owner,endpoint.id)
            observed=transport.request(remote)
            value=tickets.review(owner,endpoint.id,selected,{'identity':record['source'],
                'state':{'remote_review':observed,'source_review_digest':record['review_digest']}},configuration,program)
            jobs.update(record,retention_review_job_id=value['job_id']);return value
        if program!=ticket['program'] or ticket['source_state']['source_review_digest']!=record['review_digest']:
            raise native.HostError('Original physical retention host or artifact identity changed')
        if operation=='retention_reconcile':
            observed=transport.request({**remote,'action':'retention_status'})
        else:
            if operation=='retention_start':
                dependencies(jobs,record,owner,endpoint.id)
                if ticket['state']=='reviewed' and ticket['expires_at']<time.time():raise native.HostError('Physical retention review expired')
                prior=record.get('artifact_removal')
                if prior and prior['retention_job_id']!=ticket['job_id']:raise native.HostError('Another original physical removal intent owns this artifact')
                if not prior and record.get('retention_review_job_id')!=ticket['job_id']:raise native.HostError('A newer physical retention review replaced this preview')
                tickets.update(ticket,state='removing',started_at=ticket.get('started_at',time.time()))
                jobs.update(record,artifact_removal={'retention_job_id':ticket['job_id'],'state':'unknown'})
            try:
                observed=transport.request({**remote,'action':'retention_remove' if operation=='retention_start' else 'retention_abandon',
                    'confirmed':True,'retention_review':ticket['source_state']['remote_review'],
                    **({'retained_full_backups':batch_floor} if batch_floor is not None else {})})
            except BaseException as error:
                tickets.update(ticket,state='unknown',error_type=type(error).__name__,original_reply_unchanged=True)
                raise
        if observed.get('removal_confirmed') is True:
            tickets.update(ticket,state='removed',remote_observation=observed,removal_confirmed=True)
            jobs.update(record,artifact_removed=True,artifact_removal={'retention_job_id':ticket['job_id'],'state':'removed'},
                artifact_retention=observed)
        elif observed.get('late_dispatch_refused') is True:
            tickets.update(ticket,state='not_dispatched',remote_observation=observed,removal_confirmed=False)
            if record.get('retention_review_job_id')==ticket['job_id']:
                jobs.update(record,artifact_removal=None,retention_review_job_id=None)
        else:
            tickets.update(ticket,state='unknown' if ticket['state']!='reviewed' else 'reviewed',remote_observation=observed)
        return tickets.get(ticket['job_id'],owner,endpoint.id)
    finally:transport.close()
