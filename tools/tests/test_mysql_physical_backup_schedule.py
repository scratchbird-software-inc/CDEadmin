"""Durable backup/drill ordering, encrypted SQL ownership and interruption."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace
import time

import pytest

from test_mysql_physical_retention_schedule import scheduled  # noqa: F401
from test_mysql_physical_batch_retention import setup  # noqa: F401
from pgadmin.cdeadmin.workspace import mysql_physical_backup_schedule as backup
from pgadmin.cdeadmin.workspace import mysql_physical_service as physical
from pgadmin.cdeadmin.workspace import mysql_physical_retention as retention


@pytest.fixture
def workflow(scheduled,monkeypatch):
    s=scheduled;seed=s.create();template=s.jobs.load(seed['job_id'],1,s.endpoint.id)
    captured={'identity':deepcopy(template['source']),'state':deepcopy(template['source_state'])}
    captured['state']['source_connection_class']='owned-native-client'
    s.physical_options={**deepcopy(seed['options']),'accept_release_candidate':True,'connection':{'host':'owned','port':22,'username':'owner',
        'host_key':'pinned-key','authentication':'private_key','platform':'posix','python':'/usr/bin/python3'}}
    server=SimpleNamespace(id=9,user_id=1,endpoint_profile=s.endpoint);s.server=server;s.remote={};s.calls=[]
    s.service.mysql_physical_jobs=s.jobs
    observed={'xtrabackup':{'path':'/usr/bin/xtrabackup','sha256':'native-tool'},'mysql':{'path':'/usr/bin/mysql','sha256':'native-client'}}
    monkeypatch.setattr(physical,'manager',lambda *_args:(s.jobs,1,s.endpoint))
    monkeypatch.setattr(physical,'source',lambda *_args,**_kwargs:deepcopy(captured))
    monkeypatch.setattr(physical,'delegate',lambda *_args:{'user':'native-user','password':'private-SQL-password'})
    @contextmanager
    def sql(*_args):yield (None,{'host':'owned'})
    monkeypatch.setattr(backup,'sql_client',sql)
    def request(_channel,value):
        action=value['action'];s.calls.append((action,value.get('phase'),value.get('job_id')))
        if action=='inspect':return deepcopy(observed)
        if action=='start':
            grant=s.host.read(s.grant_value['job_id']);occurrence=s.host.occurrences(grant).get(grant['last_occurrence_id'],1,s.endpoint.id)
            assert value['job_id'] in {item['job_id'] for item in occurrence['native_jobs']}
            assert s.jobs.load(value['job_id'],1,s.endpoint.id)['backup_workflow_protected']
            phase=value['phase'];running=phase=='recover'
            remote={'job_id':value['job_id'],'input_digest':value['input_digest'],'state':'recovery_running' if running else 'native_returned',
                'supervisor_finished':not running,'process_termination_confirmed':not running,'credential_cleanup_confirmed':True,'return_code':None if running else 0}
            if phase=='copy_back':remote['restored_files']={'files':2,'total_bytes':'4'}
            elif running:remote.update(sql_ready_observed=True,recovery_running_verified=True,runtime_process_live=True,supervisor_process_live=True)
            else:remote['artifact']={'prepared':phase=='prepare','files':2,'total_bytes':'4'}
            s.remote[value['job_id']]=remote;return deepcopy(remote)
        if action=='cancel':s.remote[value['job_id']].update(state='native_returned',supervisor_finished=True,process_termination_confirmed=True,return_code=0,
            recovery_running_verified=False,runtime_process_live=False,supervisor_process_live=False)
        return deepcopy(s.remote[value['job_id']])
    monkeypatch.setattr(s.Transport,'request',request)
    s.request=request;s.captured=captured;s.observed=observed
    def factory():
        scheduler=backup.ScheduleHost(s.app,s.service)
        def authority(grant):
            anchor=scheduler.anchor(grant,s.jobs)
            if not s.active or scheduler.program(s.jobs,anchor,grant['program']['execution_host'])!=grant['program']:raise backup.native.HostError('Owned authority changed')
            return server,s.jobs,1,s.endpoint
        monkeypatch.setattr(scheduler,'authority',authority);monkeypatch.setattr(scheduler,'start',lambda:None)
        s.service.mysql_backup_scheduler=scheduler;return scheduler
    s.host_factory=factory;s.host=factory()
    def action(operation,request):return s.host.action(server,s.jobs,1,s.endpoint,'backup_schedule_'+operation,request)
    def grant(drill=True):
        value=action('review',{'options':{'physical':deepcopy(s.physical_options),
            'drill':{'mysqld':'/usr/sbin/mysqld','gtid_mode':'ON','timeout_seconds':30} if drill else None,'interval_seconds':60,'expires_after_days':1},'credentials':{}})
        s.grant_value=value
        return action('enable',{**s.confirm(value),'review_digest':value['review_digest'],'delegate_ssh_credentials':True,'delegate_database_credentials':True,'credentials':{}})
    s.action=action;s.backup_grant=grant
    yield s
    s.host.close()


def occurrence(s,value):return s.host.occurrences(s.host.read(value['job_id'])).get(value['last_occurrence_id'],1,s.endpoint.id)


def test_pipeline_binds_native_jobs_before_dispatch_and_stops_isolated_startup_before_release(workflow):
    s=workflow;grant=s.backup_grant();private=s.host.read(grant['job_id'])
    assert 'private-SQL-password' not in str(private) and 'ssh_envelope' not in grant
    value=s.host.tick(grant['job_id']);result=occurrence(s,value)
    assert result['state']=='completed' and result['startup_drill_outcome']=='passed'
    assert result['database_recovery_verified'] is False and result['production_cutover_verified'] is False
    assert [item['phase'] for item in result['native_jobs']]==['backup','prepare','copy_back','recover']
    assert ('cancel','recover',result['native_jobs'][-1]['job_id']) in s.calls
    assert result['protection_released'] and all(not s.jobs.load(item['job_id'],1,s.endpoint.id)['backup_workflow_protected'] for item in result['native_jobs'])


def test_backup_only_and_idle_restart_create_new_occurrences_without_native_replay(workflow):
    s=workflow;grant=s.backup_grant(False);first=s.host.tick(grant['job_id']);result=occurrence(s,first)
    assert result['state']=='completed' and result['startup_drill_outcome']=='not_requested' and len(result['native_jobs'])==1
    count=len(s.calls);assert s.host.tick(grant['job_id'])['last_occurrence_id']==first['last_occurrence_id'] and len(s.calls)==count
    s.host.close();s.host=s.host_factory();s.host.jobs.update(s.host.read(grant['job_id']),next_scan_at=0)
    second=s.host.tick(grant['job_id']);assert second['last_occurrence_id']!=first['last_occurrence_id']
    assert occurrence(s,second)['native_jobs'][0]['job_id']!=result['native_jobs'][0]['job_id']


def test_lost_native_reply_suspends_and_explicit_release_never_reclassifies_original_unknown(workflow,monkeypatch):
    s=workflow;grant=s.backup_grant(False);request=s.request
    def lost(channel,value):
        observed=request(channel,value)
        if value['action']=='start':raise ConnectionError('owned original native reply loss')
        return observed
    with monkeypatch.context() as patch:
        patch.setattr(s.Transport,'request',lost);value=s.host.tick(grant['job_id'])
    result=occurrence(s,value);assert value['state']=='attention_required' and not value['ssh_delegation_present'] and result['state']=='interrupted'
    native=result['native_jobs'][0]['job_id'];record=s.jobs.load(native,1,s.endpoint.id)
    assert record['state']=='unknown' and record['backup_workflow_protected']
    with pytest.raises(backup.native.HostError,match='workflow'):retention.dependencies(s.jobs,record,1,s.endpoint.id)
    released=s.action('release',{**s.confirm(value),'occurrence_id':result['job_id'],'credentials':{}})
    assert released['state']=='interrupted' and released['protection_released']
    assert s.jobs.load(native,1,s.endpoint.id)['state']=='unknown'
    count=len(s.calls);assert s.host.tick(grant['job_id'],force=True)['state']=='attention_required' and len(s.calls)==count


def test_disable_between_pipeline_steps_preserves_input_and_prevents_automatic_prepare(workflow,monkeypatch):
    s=workflow;grant=s.backup_grant();original=s.host.step
    def revoke(*args,**kwargs):
        value=original(*args,**kwargs)
        s.action('disable',s.confirm(grant));return value
    monkeypatch.setattr(s.host,'step',revoke);value=s.host.tick(grant['job_id']);result=occurrence(s,value)
    assert value['state']=='disabled' and result['state']=='interrupted' and len(result['native_jobs'])==1
    assert s.jobs.load(result['native_jobs'][0]['job_id'],1,s.endpoint.id)['backup_workflow_protected']
    released=s.action('release',{**s.confirm(value),'occurrence_id':result['job_id'],'credentials':{}})
    assert released['protection_released'] and not any(phase=='prepare' and action=='start' for action,phase,_job in s.calls)


def test_incomplete_native_shutdown_prevents_release_and_preserves_protection(workflow,monkeypatch):
    s=workflow;grant=s.backup_grant(False);request=s.request
    def unknown(channel,value):
        observed=request(channel,value)
        if value['action']=='start':
            s.remote[value['job_id']].update(supervisor_finished=False,process_termination_confirmed=False)
            raise ConnectionError('owned live native work without original reply')
        return observed
    with monkeypatch.context() as patch:
        patch.setattr(s.Transport,'request',unknown);value=s.host.tick(grant['job_id'])
    result=occurrence(s,value)
    with pytest.raises(backup.native.HostError,match='every original'):s.action('release',{**s.confirm(value),'occurrence_id':result['job_id'],'credentials':{}})
    assert s.jobs.load(result['native_jobs'][0]['job_id'],1,s.endpoint.id)['backup_workflow_protected']


def test_changed_source_and_native_executable_never_dispatch_new_backup(workflow):
    s=workflow;grant=s.backup_grant(False);s.captured['identity']['server_uuid']='another-native-source'
    assert s.host.tick(grant['job_id'])['state']=='attention_required'
    assert not any(action=='start' for action,_phase,_job in s.calls)
    s.captured['identity']['server_uuid']=grant['source']['server_uuid'];grant=s.backup_grant(False)
    s.observed['xtrabackup']['sha256']='replaced-program'
    assert s.host.tick(grant['job_id'])['state']=='attention_required'
    assert not any(action=='start' for action,_phase,_job in s.calls)


def test_registration_removal_requires_policy_disable_and_release_of_held_work(workflow,monkeypatch):
    from pgadmin.cdeadmin.endpoints.service import EndpointRegistrationError
    s=workflow;grant=s.backup_grant(False)
    with pytest.raises(EndpointRegistrationError,match='Disable'):
        with s.host.removal_guard(s.server):pytest.fail('enabled backup policy was abandoned')
    original=s.request
    def lost(channel,value):
        result=original(channel,value)
        if value['action']=='start':raise ConnectionError('owned lost reply')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(s.Transport,'request',lost);value=s.host.tick(grant['job_id'])
    with pytest.raises(EndpointRegistrationError,match='Reconcile'):
        with s.host.removal_guard(s.server):pytest.fail('protected native work was abandoned')
    result=occurrence(s,value);s.action('release',{**s.confirm(value),'occurrence_id':result['job_id'],'credentials':{}})
    with s.host.removal_guard(s.server):pass


@pytest.mark.parametrize('tool_credentials',[False,True])
def test_dedicated_SQL_credentials_never_replace_or_close_the_interactive_client(monkeypatch,tool_credentials):
    @dataclass
    class Config:
        secret_acquirer:object
    original_acquirer=lambda *_args:pytest.fail('interactive secret resolver was borrowed')
    original=SimpleNamespace(config=Config(original_acquirer),module=object());created=[]
    class Private:
        def __init__(self,config,module):self.config=config;self.module=module;self.closed=False;created.append(self)
        def close(self):self.closed=True
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mysql_family.provider.MySQLDBAPIClient',Private)
    binding=SimpleNamespace(instance=SimpleNamespace(client=original))
    endpoint=SimpleNamespace(workspace=lambda *_args,**_kwargs:(None,{'route':{'host':'pinned-source','user':'native-user','credential_reference_id':'interactive','principal_reference':'interactive-owner','pool_name':'interactive-pool'}},None),
        provider_registry=SimpleNamespace(resolve=lambda _context:binding))
    with backup.sql_client(SimpleNamespace(endpoint_service=endpoint),object(),{'user':'native-user','password':'encrypted-worker-SQL'},'worker:owned',tool_credentials=tool_credentials) as (client,route):
        assert client is not original and route['credential_reference_id']!='interactive' and 'pool_name' not in route
        with client.config.secret_acquirer(route['credential_reference_id'],route['principal_reference'],'connect','database_password') as lease:
            assert lease.use(lambda value:bytes(value))==b'encrypted-worker-SQL'
        with pytest.raises(backup.native.HostError):client.config.secret_acquirer('interactive','interactive-owner','connect','database_password')
        if tool_credentials:
            with client.config.secret_acquirer(route['credential_reference_id'],route['principal_reference'],'provider_tool','database_password') as lease:
                assert lease.use(lambda value:bytes(value))==b'encrypted-worker-SQL'
        else:
            with pytest.raises(backup.native.HostError):client.config.secret_acquirer(route['credential_reference_id'],route['principal_reference'],'provider_tool','database_password')
    assert created[0].closed and original.config.secret_acquirer is original_acquirer


@pytest.mark.parametrize('drill',[{}, {'mysqld':'relative','gtid_mode':'ON','timeout_seconds':30}, {'mysqld':'/usr/sbin/mysqld','gtid_mode':'ON','timeout_seconds':True}])
def test_invalid_drill_does_not_create_or_delegate_a_policy(workflow,drill):
    s=workflow
    with pytest.raises(backup.native.HostError):s.action('review',{'options':{'physical':s.physical_options,
        'drill':drill,'interval_seconds':60,'expires_after_days':1},'credentials':{}})


@pytest.mark.parametrize('different',[False,True])
def test_recovery_callback_finishes_before_shutdown_and_failed_checks_preserve_protection(workflow,different):
    s=workflow;value=s.backup_grant(False);grant=s.host.read(value['job_id']);records=s.host.occurrences(grant)
    reviewed=records.review(1,s.endpoint.id,grant['options'],{'identity':grant['source'],'state':{}},grant['configuration'],grant['program'])
    occurrence=records.load(reviewed['job_id'],1,s.endpoint.id);records.update(occurrence,state='running',native_jobs=[])
    s.host.jobs.update(grant,last_occurrence_id=occurrence['job_id'])
    options={**deepcopy(s.physical_options),'phase':'copy_back','input_job_id':None}
    parent=s.jobs.review(1,s.endpoint.id,options,s.captured,'config',{'execution_host':{}})
    record=s.jobs.load(parent['job_id'],1,s.endpoint.id)
    s.jobs.update(record,state='native_returned',remote_observation={'return_code':0,'restored_files':{'files':1},'process_termination_confirmed':True,'credential_cleanup_confirmed':True,'supervisor_finished':True})
    selected={**deepcopy(s.physical_options),'phase':'recover','input_job_id':parent['job_id'],'mysqld':'/usr/sbin/mysqld','recovery_gtid_mode':'ON'}
    reached=[]
    def check(runtime):
        reached.append(runtime['job_id'])
        assert runtime['recovery_running']
        assert not any(action=='cancel' and job==runtime['job_id'] for action,_phase,job in s.calls)
        if different:raise physical.native.HostError('Expected data differs')
    if different:
        with pytest.raises(physical.native.HostError,match='Expected data differs'):
            s.host.step(s.server,s.jobs,grant,records,occurrence,{'ssh':{},'database':{}},selected,on_ready=check)
    else:s.host.step(s.server,s.jobs,grant,records,occurrence,{'ssh':{},'database':{}},selected,on_ready=check)
    assert len(reached)==1 and ('cancel','recover',reached[0]) in s.calls
    assert s.jobs.get(reached[0],1,s.endpoint.id)['native_process_termination_confirmed']
    assert s.jobs.load(reached[0],1,s.endpoint.id)['backup_workflow_protected']
