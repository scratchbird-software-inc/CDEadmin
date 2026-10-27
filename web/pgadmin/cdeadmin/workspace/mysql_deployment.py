"""Versioned, explicitly bound artifacts over the existing native DDN workflow."""
from copy import deepcopy
import hashlib
import json
import re
import time

from .firebird_catalog_import import read_catalog
from .mysql_schema_plan import root,plan as native_plan
from .mysql_monitoring_host import MySQLMonitoringHost
from .mysql_online_policy import policy

FORMAT = 'scratchrobin.mysql.deployment@1'
CAPTURE = 'scratchrobin.mysql.deployment-source@1'
TICKET = 'scratchrobin.mysql.deployment-review@1'
MAX_BYTES = 32 * 1024 * 1024
BINDING = {'owner_id','server_id','endpoint_id','database_target_id','database','server_uuid','runtime_version','registration_sha256'}
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')


class DeploymentError(ValueError):
    pass


def label(value):
    if not isinstance(value,str) or not LABEL.fullmatch(value):
        raise DeploymentError('Use a 1–128 character version/environment name containing letters, digits, dot, dash or underscore')
    return value


def encode(value):
    return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def sealed(value):
    return {**value,'sha256':fingerprint(value)}


def verify(value,format,fields):
    if not isinstance(value,dict) or set(value)!=fields|{'format','sha256'} or value['format']!=format:
        raise DeploymentError('Deployment document has an unsupported format or fields')
    if len(encode(value).encode())>MAX_BYTES or value['sha256']!=fingerprint({k:v for k,v in value.items() if k!='sha256'}):
        raise DeploymentError('Deployment document fingerprint or byte bound does not match')
    return value


def binding(value):
    if not isinstance(value,dict) or set(value)!=BINDING:
        raise DeploymentError('Select an exact native environment binding')
    if any(type(value[k]) is not int or value[k]<1 for k in ('owner_id','server_id')):
        raise DeploymentError('Environment owner/server identities must be positive integers')
    if any(not isinstance(value[k],str) or not value[k] or len(value[k])>256 or '\0' in value[k] for k in BINDING-{'owner_id','server_id'}):
        raise DeploymentError('Environment native identities are unavailable')
    if value['runtime_version']!='9.7.0':raise DeploymentError('Deployment requires the admitted native MySQL 9.7.0 profile')
    return value


def documents(item):
    target=binding(item['binding'])
    for key in ('baseline','desired'):
        model=read_catalog(item[key],engine='mysql');database,identity=root(model)
        if (database!=target['database'] or identity['server_uuid']!=target['server_uuid'] or
                any(model['provenance'][k]!=target[k] for k in ('endpoint_id','database_target_id'))):
            raise DeploymentError('DDN belongs to another bound endpoint, database or native server')
    policy(item['execution'])


def artifact(version,environments):
    label(version)
    if not isinstance(environments,dict) or not 1<=len(environments)<=16:
        raise DeploymentError('Select 1–16 explicitly bound deployment environments')
    for name,item in environments.items():
        label(name)
        if not isinstance(item,dict) or set(item)!={'binding','baseline','desired','execution'}:
            raise DeploymentError('Environment requires exact binding, baseline, desired DDN and execution policy')
        documents(item)
    value=sealed({'format':FORMAT,'version':version,'environments':deepcopy(environments)})
    if len(encode(value).encode())>MAX_BYTES:raise DeploymentError('Deployment artifact exceeds 32 MiB')
    return value


def select(value,environment):
    verify(value,FORMAT,{'version','environments'});label(value['version']);label(environment)
    if not isinstance(value['environments'],dict) or not 1<=len(value['environments'])<=16 or environment not in value['environments']:
        raise DeploymentError('Select an environment contained in this exact artifact')
    item=value['environments'][environment]
    if not isinstance(item,dict) or set(item)!={'binding','baseline','desired','execution'}:
        raise DeploymentError('Unsupported deployment environment fields')
    documents(item)
    return item


def outcome(record):
    state=record.get('state');facts=record.get('outcome',{})
    if state=='committed' and facts.get('rediscovery_verified'):return 0
    if state=='not_dispatched':return 4
    return 5  # Partial, uncertain, active, or committed without verified rediscovery.


class Deployment:
    def __init__(self,service,server,target):
        self.service,self.server,self.target=service,server,target

    def current_binding(self):
        context,endpoint,provider=self.service._mysql_catalog_context(self.server,self.target)
        provider._require('administer','resource');provider._require('execute')
        captured=provider.capture_catalog(endpoint['route'])
        native=next(r for r in captured['resources'] if r['resource_kind']=='database')['native']['catalog_row']
        return binding({'owner_id':self.server.user_id,'server_id':self.server.id,'endpoint_id':str(context.endpoint_id),
            'database_target_id':self.target,'database':native['database_name'],'server_uuid':native['server_uuid'],
            'runtime_version':str(native['version']).split('-')[0],
            'registration_sha256':MySQLMonitoringHost._configuration(self.server)})

    def capture(self,environment):
        label(environment);identity=self.current_binding()
        result=self.service.mysql_catalog(self.server,{'database_target_id':self.target})
        model=read_catalog(encode(result['snapshot']),engine='mysql');database,native=root(model)
        if native['server_uuid']!=identity['server_uuid'] or database!=identity['database']:
            raise DeploymentError('Native identity changed during capture')
        return sealed({'format':CAPTURE,'environment':environment,'binding':identity,'snapshot':result['snapshot']})

    def admitted(self,source,environment):
        item=select(source,environment)
        if item['binding']!=self.current_binding():
            raise DeploymentError('Live owner, registration or native environment differs from the artifact binding')
        return item

    def plan(self,source,environment):
        item=self.admitted(source,environment)
        request={'database_target_id':self.target,'baseline':item['baseline'],'source':item['desired'],'execution':item['execution']}
        plan=self.service.mysql_schema_plan(self.server,request,validate=False)
        # Native PREPARE accepts only an unblocked plan with operations. Retain
        # three-way conflicts/no-change results instead of replacing them with
        # a validation-admission exception.
        if plan['ready_for_review']:
            plan=self.service.mysql_schema_plan(self.server,request,validate=True)
        return plan,request

    def review(self,source,environment,expected):
        plan,request=self.plan(source,environment)
        if not plan['ready_for_review'] or not plan.get('native_grammar_validated'):
            return None,plan
        if expected!=plan['execution_sha256']:raise DeploymentError('Reviewed execution fingerprint differs from the displayed plan')
        record=self.service.mysql_schema_application(self.server,'mysql_schema_review',{**request,'execution_sha256':expected})
        ticket=sealed({'format':TICKET,'artifact_sha256':source['sha256'],'version':source['version'],'environment':environment,
            'binding':deepcopy(source['environments'][environment]['binding']),'review':record})
        return ticket,plan

    def ticket(self,source,environment,ticket):
        item=self.admitted(source,environment)
        verify(ticket,TICKET,{'artifact_sha256','version','environment','binding','review'})
        if (ticket['artifact_sha256']!=source['sha256'] or ticket['environment']!=environment or
                ticket['version']!=source['version'] or ticket['binding']!=item['binding'] or not isinstance(ticket['review'],dict)):
            raise DeploymentError('Review ticket belongs to a different exact artifact or environment')
        request={'database_target_id':self.target,'review_id':ticket['review']['review_id']}
        retained=self.service.mysql_schema_application(self.server,'mysql_schema_receipt',request)
        if (retained['review_digest']!=ticket['review'].get('review_digest') or retained['plan']!=ticket['review'].get('plan')):
            raise DeploymentError('Review ticket differs from its durable native review')
        baseline=read_catalog(item['baseline'],engine='mysql');desired=read_catalog(item['desired'],engine='mysql')
        expected=native_plan(baseline,desired,baseline,execution=item['execution'])
        # Online-copy admission is separately captured/revalidated by its native
        # workflow. It cannot replace the exact compiled source/identity/context.
        operations=[{k:v for k,v in op.items() if k!='copy_admission'} for op in retained['plan']['operations']]
        if not expected['ready_for_review'] or expected['operations']!=operations:
            raise DeploymentError('Durable native review does not implement this artifact')
        return item,request

    def receipt(self,source,environment,ticket):
        item,request=self.ticket(source,environment,ticket)
        if item['execution'] is not None:return self.service.mysql_online_ddl(self.server,'status',request)
        return self.service.mysql_schema_application(self.server,'mysql_schema_receipt',request)

    def apply(self,source,environment,ticket,approval,*,cutover=False,wait_seconds=300):
        item,request=self.ticket(source,environment,ticket)
        if approval!=ticket['sha256']:raise DeploymentError('Explicit approval of the exact review ticket fingerprint is required')
        if type(wait_seconds) is not int or not 1<=wait_seconds<=86430:raise DeploymentError('Select a bounded deployment wait')
        execution=item['execution']
        if cutover and (execution or {}).get('method')!='pt-online-schema-change':
            raise DeploymentError('Cutover approval applies only to the reviewed online-copy workflow')
        request.update(review_digest=ticket['review']['review_digest'],confirmed=True)
        if execution is None:return self.service.mysql_schema_application(self.server,'mysql_schema_apply',request)
        record=self.service.mysql_online_ddl(self.server,'start',request)
        status_request={'database_target_id':self.target,'review_id':request['review_id']}
        deadline=time.monotonic()+wait_seconds;cutover_sent=False
        try:
            while not record.get('controlled_terminal'):
                if record.get('controlled_job',{}).get('copy_stage')=='cutover-waiting' and not cutover_sent:
                    if not cutover:break
                    self.service.mysql_online_ddl(self.server,'cutover',status_request);cutover_sent=True
                if time.monotonic()>=deadline:break
                time.sleep(.1);record=self.service.mysql_online_ddl(self.server,'status',status_request)
        finally:
            # This CLI owns the worker process. Exit never leaves an intentionally
            # orphaned online copy, and never treats cancellation as rollback.
            jobs=getattr(self.service,'mysql_online_ddl_jobs',None)
            if jobs is not None:jobs.close()
        return self.service.mysql_online_ddl(self.server,'status',status_request)
