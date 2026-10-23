"""Reviewed physical retention policies over complete, owner-scoped job graphs."""
from copy import deepcopy
import hashlib
import heapq
import math
from pathlib import Path
import stat
import time
import uuid

from . import mysql_physical_retention as individual
from . import mysql_physical_service as physical
from .mysql_binlog_jobs import MySQLBinlogJobs,digest,review_digest
from .mysql_monitoring_host import MySQLMonitoringHost

native=individual.native
MAX_JOBS=10000
MAX_BATCH=100


def policy(value):
    if not isinstance(value,dict) or set(value)!={'retention_days','keep_latest'}:
        raise native.HostError('Select a physical retention age and minimum full-backup chain count')
    if type(value['retention_days']) is not int or not 0<=value['retention_days']<=36500 or type(value['keep_latest']) is not int or not 1<=value['keep_latest']<=1000:
        raise native.HostError('Select 0–36500 retention days and 1–1000 retained full-backup chains')
    return dict(value)


def scope(record):
    return digest({'source':record['source'],'binding':record['source_state']['host_binding'],
        'connection':record['options']['connection'],'workspace':record['options']['workspace']})


def inventory(jobs,owner,endpoint):
    index=jobs.scope(owner,endpoint)/'index';result={}
    for entry in index.iterdir() if index.exists() else ():
        if entry.name.startswith('.'):continue
        info=entry.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size:raise native.HostError('Physical batch index identity changed')
        record=jobs.load(entry.name.split('_',1)[-1],owner,endpoint)
        if record['job_id'] in result:raise native.HostError('Physical batch index contains duplicate jobs')
        result[record['job_id']]=record
        if len(result)>MAX_JOBS:raise native.HostError('Physical batch inventory exceeds 10000 jobs')
    return result


def ended(record):
    value=record.get('remote_observation') or {}
    supervisor=value.get('supervisor_finished') is True or (record['options']['phase']=='recover' and
        value.get('supervisor_process_live') is False and value.get('runtime_process_live') is False)
    return (supervisor and value.get('process_termination_confirmed') is True and value.get('credential_cleanup_confirmed') is True and
        value.get('runtime_process_live') is not True and value.get('supervisor_process_live') is not True and not value.get('process_presence_unknown'))


def verified_full(record):
    value=record.get('remote_observation') or {}
    return record['options']['phase']=='backup' and ended(record) and value.get('return_code')==0 and not value.get('error_type') and bool(value.get('artifact'))


def absent(record):
    return record.get('artifact_removed') or record['state']=='cancelled' and record.get('native_may_have_dispatched') is False


def fingerprint(record):
    value=record.get('remote_observation') or {}
    return digest({'review':record['review_digest'],'state':record['state'],'pinned':record.get('retention_pinned',False),
        'age_anchor':record.get('retention_age_anchor'),'ended':ended(record),
        'artifact':value.get('artifact') or value.get('restored_files'),'removed':bool(record.get('artifact_removed'))})


def plan(records,anchor,selected,cutoff,*,registered=(),reservation=None):
    """Preserve kept descendants and every input of a retained node."""
    selected=policy(selected);key=scope(anchor);nodes={job:record for job,record in records.items() if scope(record)==key}
    children={job:set() for job in nodes};parents={}
    if any(record['options'].get('input_job_id') in nodes and job not in nodes and not absent(record) for job,record in records.items()):
        raise native.HostError('Physical batch child belongs to another native scope; preserve its input')
    for job,record in nodes.items():
        parent=record['options'].get('input_job_id')
        if parent is not None:
            if parent not in nodes:raise native.HostError('Physical batch dependency is missing or belongs to another native scope')
            children[parent].add(job);parents[job]=parent
    degree={job:len(children[job]) for job in nodes};queue=[(nodes[job]['created_at'],job) for job,count in degree.items() if not count];heapq.heapify(queue);order=[]
    while queue:
        _created,job=heapq.heappop(queue);order.append(job)
        if job in parents:
            parent=parents[job];degree[parent]-=1
            if not degree[parent]:heapq.heappush(queue,(nodes[parent]['created_at'],parent))
    if len(order)!=len(nodes):raise native.HostError('Physical batch dependency graph contains a cycle')
    protected={};full=sorted((record for record in nodes.values() if not absent(record) and not record.get('artifact_removal') and verified_full(record)),
        key=lambda record:(record['created_at'],record['job_id']),reverse=True)
    kept=[record['job_id'] for record in full[:selected['keep_latest']]]
    stack=list(kept)
    while stack:
        job=stack.pop()
        if job in protected:continue
        protected[job]='minimum_full_backup_chains';stack.extend(children[job])
    registered=set(registered)
    for job,record in nodes.items():
        if absent(record):continue
        own=reservation is not None and record.get('retention_batch_id')==reservation
        reason=('backup_workflow' if record.get('backup_workflow_protected') else 'pinned' if record.get('retention_pinned') else 'registered_recovery' if job in registered else
            'other_batch' if record.get('retention_batch_id') and not own else
            'pending_removal' if record.get('artifact_removal') and not own else
            'outstanding_review' if record.get('retention_review_job_id') and not own else
            'unconfirmed_native_end' if not ended(record) else
            'age_unavailable' if type(record.get('retention_age_anchor')) not in (int,float) or not math.isfinite(record['retention_age_anchor']) else
            'within_retention_age' if record['retention_age_anchor']>=cutoff else None)
        if reason:protected.setdefault(job,reason)
    if len(full)<selected['keep_latest']:
        for job in nodes:protected.setdefault(job,'insufficient_verified_full_backups')
    for job in order:
        if job in protected and job in parents:protected.setdefault(parents[job],'input_of_retained_job')
    eligible=[job for job in order if job not in protected and not absent(nodes[job])]
    chosen=eligible[:MAX_BATCH]
    counts={}
    for job,reason in protected.items():
        if not absent(nodes[job]):counts[reason]=counts.get(reason,0)+1
    return {'job_ids':chosen,'eligible_count':len(eligible),'retained_full_backup_ids':kept,'excluded':counts,
        'scope_jobs':len(nodes),'outside_scope_jobs':len(records)-len(nodes),'cutoff_time':cutoff,
        'fingerprints':{job:fingerprint(nodes[job]) for job in chosen}}


class BatchJobs(MySQLBinlogJobs):
    operation='mysql_physical_batch_retention'
    review_warnings=(
        'Remove only these reviewed physical jobs, children before inputs. Keep the newest verified full-backup chains and protect retained jobs, their inputs, pins and recovery registrations.',
        'File verification and age/count policy do not establish full recovery acceptance. This plan adds no new jobs after review; each step rechecks the retained floor and native dependencies.',
        'Closing or pausing the viewer stops future steps. Already admitted host removal may continue. Interrupted steps require independent observation and explicit resume or invalidation.',
        'Fresh SSH authentication is used only for this request. Source SQL login and automatic scheduling are not required; original native receipts and binary-log protections remain.',
    )

    def public(self,record):
        return {**super().public(record),'plan':deepcopy(record['source_state']['plan']),
            'items':deepcopy(record['source_state']['items']),'next_index':record.get('next_index',0),
            'removed_job_ids':list(record.get('removed_job_ids',[])),'automatic_retry':False}


def manager(service,jobs):
    with service._semantic_lock:
        result=getattr(service,'mysql_physical_batch_jobs',None)
        if result is None:result=service.mysql_physical_batch_jobs=BatchJobs(str(jobs.path)+'.batch-retention',str(jobs.root)+'.batch-retention')
    return result


def registered_jobs(service,owner,endpoint):
    from pgadmin.model import Server,EndpointProfile,EndpointExtensionProfile
    from .mysql_recovery_connections import marker
    from ..providers.mysql_family.mysql_recovery_bridge import SCHEMA
    rows=Server.query.join(EndpointProfile,EndpointProfile.legacy_server_id==Server.id).join(
        EndpointExtensionProfile,EndpointExtensionProfile.endpoint_id==EndpointProfile.id).filter(
            Server.user_id==owner,EndpointExtensionProfile.schema_reference==SCHEMA).limit(10001).all()
    if len(rows)>MAX_JOBS:raise native.HostError('Physical batch registration inventory exceeds its bound')
    return {value['source_job_id'] for row in rows if (value:=marker(row))['source_endpoint_id']==endpoint}


def records_for_plan(service,jobs,owner,endpoint):
    records=inventory(jobs,owner,endpoint)
    for record in records.values():
        if not record.get('artifact_removed') and ended(record) and 'retention_age_anchor' not in record:
            observed=record.get('observed_at')
            value=observed if type(observed) in (int,float) and math.isfinite(observed) else time.time()
            jobs.update(record,retention_age_anchor=value);record['retention_age_anchor']=value
    return records,registered_jobs(service,owner,endpoint)


def program(peer,record):
    return {**native.program(),'batch_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'execution_host':{**peer,'kind':'database-server-ssh-host','workspace':record['options']['workspace']}}


def floors(records,planned):
    return [{'job_id':job,'input_digest':records[job]['review_digest']} for job in planned['retained_full_backup_ids']]


def action(service,server,jobs,owner,endpoint,operation,request,*,scheduled_policy_id=None,on_review=None):
    from .mysql_host_service import credentials
    batches=manager(service,jobs);items=individual.manager(service,jobs)
    if operation=='retention_batch_list' and not set(request)-{'offset','limit'}:return batches.list(owner,endpoint.id,**request)
    if operation=='retention_batch_status' and set(request)=={'job_id'}:return batches.get(request['job_id'],owner,endpoint.id)
    configuration=digest(MySQLMonitoringHost._configuration(server))
    if operation=='retention_batch_review' and set(request)=={'scope_job_id','policy','credentials'}:
        anchor=jobs.load(request['scope_job_id'],owner,endpoint.id);selected=policy(request['policy'])
        records,registrations=records_for_plan(service,jobs,owner,endpoint.id);cutoff=time.time()-selected['retention_days']*86400
        planned=plan(records,anchor,selected,cutoff,registered=registrations)
        if not planned['job_ids']:return {'state':'nothing_eligible','plan':planned,'policy':selected}
        reservation=str(uuid.uuid4());ticket=None
    else:
        confirmed=operation in {'retention_batch_advance','retention_batch_resume','retention_batch_cancel'}
        fields={'job_id','credentials'}|({'review_digest','confirmed','batch_confirmation'} if confirmed else set())
        if operation not in {'retention_batch_advance','retention_batch_resume','retention_batch_reconcile','retention_batch_cancel'} or set(request)!=fields:
            raise native.HostError('Select an exact reviewed physical retention batch')
        ticket=batches.load(request['job_id'],owner,endpoint.id)
        owning=ticket['options'].get('scheduled_policy_id')
        if owning and owning!=scheduled_policy_id:
            scheduler=getattr(service,'mysql_physical_scheduler',None)
            if scheduler is None or scheduler.jobs.load(owning,owner,endpoint.id)['state']=='enabled':
                raise native.HostError('Disable the owning physical schedule before manually changing its occurrence')
        if confirmed and (request['confirmed'] is not True or request['review_digest']!=ticket['review_digest'] or review_digest(ticket)!=ticket['review_digest'] or request['batch_confirmation']!=ticket['job_id']):
            raise native.HostError('Confirm this exact batch review and type its batch UUID')
        if ticket['state'] in {'completed','cancelled'}:return batches.get(ticket['job_id'],owner,endpoint.id)
        if ticket['configuration']!=configuration:raise native.HostError('Physical batch registration changed')
        anchor=jobs.load(ticket['options']['scope_job_id'],owner,endpoint.id)
        selected=ticket['options']['policy'];reservation=ticket['options']['reservation_id']
    channel=native.Transport(anchor['options']['connection'],credentials(request['credentials']))
    try:
        peer=channel.connect();current=program(peer,anchor)
        if ticket is not None and ticket['program']!=current:raise native.HostError('Physical batch host or adapter changed')
        if ticket is None:
            reviewed=[]
            channel.request({**physical.remote_request(anchor,'retention_verify_floor'),'retention_id':reservation,'retained_full_backups':floors(records,planned)})
            child_program={key:value for key,value in current.items() if key!='batch_sha256'}
            for job_id in planned['job_ids']:
                record=records[job_id];retention_id=str(uuid.uuid4())
                remote=channel.request({**physical.remote_request(record,'retention_inspect'),'retention_id':retention_id,'planned_job_ids':planned['job_ids']})
                child=items.review(owner,endpoint.id,{'source_job_id':job_id,'retention_id':retention_id,'batch_reservation_id':reservation},
                    {'identity':record['source'],'state':{'remote_review':remote,'source_review_digest':record['review_digest']}},configuration,child_program)
                reviewed.append({'physical_job_id':job_id,'retention_job_id':child['job_id'],'retention_digest':child['review_digest'],'artifact':remote['artifact']})
            result=batches.review(owner,endpoint.id,{'scope_job_id':anchor['job_id'],'policy':selected,'reservation_id':reservation,
                **({'scheduled_policy_id':scheduled_policy_id} if scheduled_policy_id else {})},
                {'identity':anchor['source'],'state':{'plan':planned,'items':reviewed}},configuration,current)
            if on_review is not None:on_review(result)
            for item in reviewed:
                jobs.update(records[item['physical_job_id']],retention_batch_id=reservation,retention_batch_job_id=result['job_id'],retention_review_job_id=item['retention_job_id'])
            batches.update(batches.load(result['job_id'],owner,endpoint.id),next_index=0,removed_job_ids=[])
            return batches.get(result['job_id'],owner,endpoint.id)
        approved=ticket['source_state']['items'];index=ticket.get('next_index',0)
        if operation=='retention_batch_cancel':
            batches.update(ticket,cancellation_requested=True)
            pending=False;removed=set(ticket.get('removed_job_ids',[]));observations={}
            for item in approved[index:]:
                value=individual.action(service,server,jobs,owner,endpoint,'retention_abandon',{'job_id':item['retention_job_id'],
                    'review_digest':item['retention_digest'],'confirmed':True,'job_confirmation':item['physical_job_id'],'credentials':request['credentials']},batch_reservation=reservation)
                observations[item['physical_job_id']]={'state':value['state'],'removal_confirmed':value.get('removal_confirmed') is True}
                if value.get('removal_confirmed'):removed.add(item['physical_job_id'])
                if value['state']=='not_dispatched' or value.get('removal_confirmed'):
                    source=jobs.load(item['physical_job_id'],owner,endpoint.id)
                    if source.get('retention_batch_id')==reservation:jobs.update(source,retention_batch_id=None)
                else:pending=True
            batches.update(ticket,state='interrupted' if pending else 'cancelled',cancellation_requested=True,
                removed_job_ids=[row['physical_job_id'] for row in approved if row['physical_job_id'] in removed],cancellation_observations=observations)
            return batches.get(ticket['job_id'],owner,endpoint.id)
        if index>=len(approved):return batches.get(ticket['job_id'],owner,endpoint.id)
        item=approved[index]
        body={'job_id':item['retention_job_id'],'credentials':request['credentials']}
        if operation=='retention_batch_reconcile':
            value=individual.action(service,server,jobs,owner,endpoint,'retention_reconcile',body,batch_reservation=reservation)
            batches.update(ticket,needs_observation=False)
        else:
            if ticket.get('cancellation_requested') and operation!='retention_batch_resume':raise native.HostError('This batch is cancelling; only its original admitted item can resume')
            if ticket['state']=='interrupted' and operation!='retention_batch_resume':raise native.HostError('Inspect and explicitly resume this batch\'s interrupted item')
            if operation=='retention_batch_resume' and ticket['state']!='interrupted':raise native.HostError('Select an interrupted original batch item')
            if ticket.get('needs_observation'):raise native.HostError('Independently inspect the original batch step before resuming')
            if operation=='retention_batch_advance' and ticket['state'] not in {'reviewed','paused'}:raise native.HostError('Independently inspect the original batch step before continuing')
            if ticket['state']=='reviewed' and ticket['expires_at']<time.time():raise native.HostError('Physical batch review expired')
            records,registrations=records_for_plan(service,jobs,owner,endpoint.id)
            live=plan(records,anchor,selected,ticket['source_state']['plan']['cutoff_time'],registered=registrations,reservation=reservation)
            reviewed_remaining=approved[index:index+1] if ticket.get('cancellation_requested') else approved[index:]
            remaining={row['physical_job_id'] for row in reviewed_remaining}
            if not remaining<=set(live['job_ids']):raise native.HostError('Physical batch eligibility or retained chain floor changed; preserve remaining files')
            for row in reviewed_remaining:
                record=records[row['physical_job_id']]
                if record.get('retention_batch_id')!=reservation or fingerprint(record)!=ticket['source_state']['plan']['fingerprints'][record['job_id']]:
                    raise native.HostError('A reviewed physical job or reservation changed')
            batches.update(ticket,state='running',current_job_id=item['physical_job_id'],needs_observation=True)
            try:
                value=individual.action(service,server,jobs,owner,endpoint,'retention_start',
                    {**body,'review_digest':item['retention_digest'],'confirmed':True,'job_confirmation':item['physical_job_id']},batch_reservation=reservation,batch_floor=floors(records,live))
            except BaseException as error:
                batches.update(ticket,state='interrupted',error_type=type(error).__name__);raise
        if value.get('removal_confirmed'):
            jobs.update(jobs.load(item['physical_job_id'],owner,endpoint.id),retention_batch_id=None)
            removed=[*ticket.get('removed_job_ids',[]),item['physical_job_id']]
            batches.update(ticket,state=('cancelling' if ticket.get('cancellation_requested') else 'completed' if index+1==len(approved) else 'paused'),next_index=index+1,removed_job_ids=removed,current_job_id=None,needs_observation=False)
        else:batches.update(ticket,state='interrupted',current_job_id=item['physical_job_id'],item_observation=value)
        return batches.get(ticket['job_id'],owner,endpoint.id)
    finally:channel.close()
