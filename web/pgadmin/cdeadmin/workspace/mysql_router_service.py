"""Reviewed native Router bootstrap and SQL-independent original observation."""
from copy import deepcopy
from pathlib import Path
import threading
import time

from ..providers.mysql_family import mysql_router_transport as native
from ..providers.mysql_family.mysql_clone import configure
from ..providers.mysql_family.mysql_log_purge import private_connection
from ..providers.mysql_family.mysql_router_worker import connection_observation
from ..security import SecretLease
from . import mysql_host_service as host
from .mysql_binlog_jobs import digest
from .mysql_topology_service import context
from .mysql_monitoring_host import MySQLMonitoringHost


def options(value):
    fields={'connection','executable','directory','user','base_port','bind_address','seed','extra_arguments','workspace','timeout_seconds'}
    if not isinstance(value,dict) or set(value)-{'operation','service','binding_job_id','disconnect_all_clients'}!=fields:raise native.HostError('Select the exact native Router host, metadata seed and deployment options')
    selected=deepcopy(value);selected['connection']=native.ssh.public_route(selected['connection'])
    # Path meaning belongs to the remote Linux adapter, including for Windows
    # application hosts. Do not interpret remote paths with local Path rules.
    for key in ('executable','directory','user','bind_address','workspace'):
        if not isinstance(selected[key],str) or not selected[key] or '\0' in selected[key] or len(selected[key])>32768:raise native.HostError('Select bounded native Router options')
    if type(selected['base_port']) is not int or not 1<=selected['base_port']<=65528:raise native.HostError('Select a native Router base port')
    if type(selected['timeout_seconds']) is not int or not 1<=selected['timeout_seconds']<=3600:raise native.HostError('Select a bounded native Router runtime')
    if not isinstance(selected['seed'],dict) or not isinstance(selected['extra_arguments'],list):raise native.HostError('Select exact native Router seed and additional arguments')
    operation=selected.get('operation','bootstrap')
    if operation not in {'bootstrap','install_service','service_start','service_stop','service_restart','service_enable','service_disable'}:raise native.HostError('Select a native Router operation')
    if operation!='bootstrap':
        if not isinstance(selected.get('binding_job_id'),str):raise native.HostError('Select a prior native Router deployment receipt')
        if operation in {'service_stop','service_restart'} and selected.get('disconnect_all_clients') is not True:raise native.HostError('Confirm disconnection of all routed clients')
    return selected


def remote_options(selected):return {key:value for key,value in selected.items() if key not in {'connection','binding_job_id'}}


def request(record,action,password=None):
    value={'schema':'cdeadmin.mysql-router-host.v1','action':action,'options':remote_options(record['options']),
        'expected_seed':record['source_state']['seed'],'reviewed':record['source_state']['remote_review'],
        'job_id':record['job_id'],'input_digest':record['review_digest']}
    if password is not None:value['database_password']=password
    if record['source_state'].get('deployment_binding'):value['deployment_binding']=record['source_state']['deployment_binding']
    return value


class Invocation:
    def __init__(self,transport,client,route,password):
        self.transport,self.client,self.route,self.password=transport,client,route,password
        self.guard=None;self.secret=None;self.closed=False;self.lock=threading.RLock()
    def acquire(self):
        # Vault authorization belongs to the admitting request. The worker has
        # no Flask request principal and must not reacquire the credential.
        if self.client is not None:
            self.secret=self.use_password(lambda password:SecretLease(password+'\n'));self.password=None
            guard=self.client._native_operation();guard.__enter__();self.guard=guard
    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True;guard=self.guard;self.guard=None;self.password=None
            secret=self.secret;self.secret=None
        try:self.transport.close()
        finally:
            try:
                if secret is not None:secret.close()
            finally:
                if guard is not None:guard.__exit__(None,None,None)
    def use_password(self,callback):
        if self.password is not None:return callback(self.password)
        def use(values):
            if len(values)>1:raise native.HostError('Native Router bootstrap needs a compatible bootstrap account; select its private password explicitly')
            return callback(values[0] if values else '')
        return self.client._tool_secrets(self.route,use)
    def execute(self,record):
        operation=record['options'].get('operation','bootstrap')
        if operation!='bootstrap':return self.transport.request(request(record,operation),timeout=record['options']['timeout_seconds']+30)
        with self.client._native_operation():
            return self.secret.use(lambda view:self.transport.request(request(record,'bootstrap',bytes(view).decode('utf8')[:-1]),timeout=record['options']['timeout_seconds']+30))


class RouterJobs(host.HostJobs):
    operation='mysql_native_router_bootstrap'
    remote_database_mutation=True
    review_warnings=(
        'Runs native MySQL Router bootstrap on the explicitly authenticated SSH host. The Router host need not contain the SQL server data directory.',
        'The Router host independently checks the native seed UUID and Cluster/ReplicaSet/ClusterSet identity. Its actual database account, role, grants and TLS observation bind this review; host-specific MySQL accounts may differ from the application connection.',
        'Native Router creates its account/metadata and deployment files. Partial changes can remain after failure or cancellation. Native keyring and certificate files stay private on the Router host; their contents are not included in deployment manifests.',
        'Bootstrap configures Router; it does not start a service or establish routed SQL readiness. A native return code, original SSH acknowledgement and later utility observations remain separate.',
        'The independent native guardian owns the original invocation and private input cleanup. Closing the workbench does not retry or cancel an admitted bootstrap. Unknown replies require original observation; no automatic metadata/account rollback is attempted.',
    )
    def run(self,record,invocation,signal):
        sent=False
        try:
            self.update(record,state='active',phase='before_native_dispatch')
            with self.store(record['job_id']) as store:
                def admit(state):
                    current=self.record(state,record['job_id'],record['owner'],record['endpoint_id'])
                    if current.get('cancel_requested') or signal.is_set():raise InterruptedError('Native Router request cancelled before admission')
                    current.update(phase='native_dispatch',native_may_have_dispatched=True)
                store.change(admit)
            sent=True;remote=invocation.execute(record)
            self.update(record,ssh_reply_observed=True,remote_receipt=remote)
            if remote.get('input_digest')!=record['review_digest']:raise native.HostError('The native Router reply belongs to another reviewed request')
            self.update(record,state='native_process_returned' if remote.get('state')=='native_process_returned' else 'unknown',phase='finished',finished_at=time.time())
        except BaseException as error:
            self.update(record,state='unknown' if sent else 'cancelled' if isinstance(error,InterruptedError) else 'not_dispatched',
                phase='finished',error_type=type(error).__name__,error_message=str(error) if isinstance(error,native.HostError) else None,
                native_error=getattr(error,'native_error',None),finished_at=time.time())
        finally:
            try:invocation.close()
            finally:
                with self._maps_lock:
                    known=self.workers.get(record['job_id'])
                    if known and known[0] is threading.current_thread():self.workers.pop(record['job_id'],None)


def manager(service,server):
    original,owner,endpoint=host.manager(service,server)
    with service._semantic_lock:
        jobs=getattr(service,'mysql_router_jobs',None)
        if jobs is None:
            jobs=service.mysql_router_jobs=RouterJobs(str(original.path)+'.router',original.root.parent/'mysql-native-router-receipts')
            import atexit
            atexit.register(jobs.close)
    return jobs,owner,endpoint


def source(service,server):
    client,route=context(service,server);connection=private_connection(client,route)
    try:
        configure(connection);identity=connection_observation(connection)
        identity.update(connector_version='26.7.0',sql_connection_closed_after_observation=True)
        return client,route,{'identity':identity,'state':{'seed':identity,'source_connection_class':type(connection).__name__,
            'source_identity_scope':'current_native_metadata_seed_and_independent_router_host'}}
    finally:client._discard_failed_session(connection)


def bound_source(jobs,owner,endpoint,selected):
    prior=jobs.load(selected['binding_job_id'],owner,endpoint)
    for key in ('connection','executable','directory','user'):
        if prior['options'][key]!=selected[key]:raise native.HostError('Select the original Router deployment host, executable, directory and native user')
    remote=prior.get('remote_receipt') or {}
    # Later facts may establish the file/manager association, but never replace
    # the prior request's original unknown outcome.
    later=(prior.get('reconciliation') or {}).get('remote_receipt') or {}
    binding=deepcopy(prior['source_state'].get('deployment_binding'))
    if prior['options'].get('operation','bootstrap')=='bootstrap':
        completed=remote if remote.get('deployment_observation') else later
        deployment=completed.get('deployment_observation') or {}
        facts=later.get('utility_observation') or {}
        if deployment.get('observed') is not True and facts.get('cleanup_confirmed') is True and facts.get('complete') is True and facts.get('return_code')==0:
            completed=later;deployment=completed.get('current_deployment_observation') or {}
        if deployment.get('observed') is not True:raise native.HostError('Select a native Router receipt with an observed completed deployment')
        from ..providers.mysql_family.mysql_router_services import stable
        binding={'observation':completed['observation'],'deployment':stable(deployment)}
    if not binding:raise native.HostError('The original Router deployment association is unavailable')
    installation=remote.get('service_installation_result') or later.get('service_installation_phase_observation') or {}
    associated=remote.get('service_after') or installation.get('installed_service_binding') or prior['source_state']['remote_review'].get('service')
    if associated:binding['service']=associated
    return {'identity':deepcopy(prior['source']),'state':{'seed':deepcopy(prior['source_state']['seed']),
        'deployment_binding':binding,'source_identity_scope':'original_native_router_deployment_and_current_ssh_host_authority'}}


def action(service,server,operation,value):
    if not isinstance(value,dict):raise native.HostError('Select a native Router workspace request')
    jobs,owner,endpoint=manager(service,server)
    if operation=='peer' and set(value)=={'host','port'}:return native.ssh.probe(value['host'],value['port'])
    if operation=='list' and not set(value)-{'offset','limit'}:return jobs.list(owner,endpoint.id,**value)
    if operation in {'status','cancel'} and set(value)=={'job_id'}:return (jobs.get if operation=='status' else jobs.cancel)(value['job_id'],owner,endpoint.id)
    if operation=='catalog' and not value:
        _client,route,captured=source(service,server)
        return {**captured,'suggested_seed':{'host':route['host'],'port':route.get('port',3306),'user':route['user'],
            'ssl_mode':'REQUIRED','ssl_ca':None,'ssl_cert':None,'ssl_key':None}}
    record=None
    if operation in {'start','reconcile','cancel_original','acknowledge'}:
        record=jobs.load(value.get('job_id'),owner,endpoint.id)
        fields={'job_id','credentials'}|({'review_digest','confirmed'} if operation=='start' else set())
        if set(value)-{'bootstrap_secret'}!=fields:raise native.HostError('Select one exact reviewed native Router request')
        selected=record['options']
        if operation=='start':
            if value['confirmed'] is not True:raise native.HostError('Confirm the exact native Router bootstrap review')
            if record['state']!='reviewed':return jobs.start({key:value[key] for key in ('job_id','review_digest','confirmed')},owner,endpoint.id,{},None)
    elif operation=='review' and set(value)-{'bootstrap_secret'}=={'options','credentials'}:selected=options(value['options'])
    else:raise native.HostError('Native Router workspace action unavailable')
    password=None
    if 'bootstrap_secret' in value:
        secret=value['bootstrap_secret']
        if operation not in {'review','start'} or not isinstance(secret,dict) or set(secret)!={'password'} or not isinstance(secret['password'],str):raise native.HostError('Supply the bootstrap password privately for review or dispatch')
        password=secret['password']
        if len(password)>1024*1024 or any(char in password for char in '\0\r\n'):raise native.HostError('Native Router accepts one bounded private password input line')
    configuration=digest(MySQLMonitoringHost._configuration(server))
    if operation=='start' and (record['configuration']!=configuration or any(record['program'].get(key)!=item for key,item in native.program().items())):
        raise native.HostError('Use the reviewed native Router adapter and registration')
    transport=native.Transport(selected['connection'],host.credentials(value['credentials']))
    try:
        peer=transport.connect()
        if operation in {'reconcile','cancel_original','acknowledge'}:
            remote=transport.request(request(record,{'reconcile':'status','cancel_original':'cancel','acknowledge':'acknowledge'}[operation]))
            if remote.get('input_digest')!=record['review_digest']:raise native.HostError('The original Router receipt identity differs')
            jobs.update(record,reconciliation={'remote_receipt':remote,'observed_at':time.time(),'original_ssh_acknowledgement_unchanged':True})
            return jobs.get(record['job_id'],owner,endpoint.id)
        service_operation=selected.get('operation','bootstrap')!='bootstrap'
        if service_operation:
            captured=bound_source(jobs,owner,endpoint.id,selected);client=route=None
        else:client,route,captured=source(service,server)
        invocation=Invocation(transport,client,route,password)
        inspection={'schema':'cdeadmin.mysql-router-host.v1','action':'inspect','options':remote_options(selected),'expected_seed':captured['identity']}
        if service_operation:
            observed=transport.request({**inspection,'deployment_binding':captured['state']['deployment_binding']})
        else:observed=invocation.use_password(lambda secret:transport.request({**inspection,'database_password':secret}))
        captured['state']['remote_review']=observed
        program={**native.program(),'native_executable':observed['program'],'execution_host':{**peer,'kind':'native-router-ssh-host','hostname':observed['host']['hostname'],'platform':observed['host']['platform']}}
        if operation=='review':
            reviewed=jobs.review(owner,endpoint.id,selected,captured,configuration,program)
            if service_operation:
                record=jobs.load(reviewed['job_id'],owner,endpoint.id)
                jobs.update(record,warnings=[
                    'Controls the exact native Router deployment and Linux systemd unit on its recorded SSH host. Current database access is not required.',
                    'Installation creates a new unit without replacing existing definitions, starting Router or enabling boot startup. Native Router configuration acceptance occurs at startup.',
                    'Stop/restart disconnect routed clients. Native clients own pending transaction outcomes; an interrupted commit can remain unknown.',
                    'Original service-manager command receipts, later process/unit observations and routed SQL readiness remain separate. Unknown replies are never automatically replayed.'])
                reviewed=jobs.get(record['job_id'],owner,endpoint.id)
            return reviewed
        if captured['state']!=record['source_state']:raise native.HostError('The native Router seed, actor, host or selected files changed; prepare a new review')
        try:
            invocation.acquire();transport=None
            return jobs.start({key:value[key] for key in ('job_id','review_digest','confirmed')},owner,endpoint.id,
                {'configuration':configuration,'source':captured['identity'],'program':program},invocation)
        except BaseException:
            invocation.close();raise
    finally:
        if transport is not None:transport.close()
