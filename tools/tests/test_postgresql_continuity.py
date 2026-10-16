"""Native backup admission, review claims and durable process ownership."""
from contextlib import contextmanager
import json
from pathlib import Path
import threading
import time
import uuid

import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError, backup_options, backup_arguments
from pgadmin.cdeadmin.providers.postgresql.continuity_transport import ContinuityTransport
from pgadmin.cdeadmin.workspace.postgresql_continuity_jobs import PostgreSQLContinuityJobs


@pytest.mark.parametrize('options', [
    {'wal_method':'fetch','slot':'slot'}, {'slot':'A'}, {'no_slot':True,'slot':'slot'},
    {'create_slot':True}, {'max_rate_kib':True}, {'max_rate_kib':31},
    {'checkpoint':'arbitrary'}, {'sync':1}, {'label':'native\x00label'},
])
def test_invalid_native_backup_options_do_not_become_commands(options):
    with pytest.raises(ContinuityError):backup_options(options)


def test_native_arguments_preserve_exact_values_without_shell_interpolation():
    values=backup_arguments({'label':'Quoted ü; $(literal)','compression':'server-zstd:level=3'},Path('/owned backup'),
                           tablespaces=[('/source=space\\native','/owned=target\\native')])
    assert '--label=Quoted ü; $(literal)' in values
    assert '--compress=server-zstd:level=3' in values
    assert '--tablespace-mapping=/source\\=space\\\\native=/owned\\=target\\\\native' in values


def test_transport_does_not_expose_credentials_in_repr_and_releases_lease():
    transport=ContinuityTransport({'host':'localhost'},secrets={'database_password':'private-native-canary'})
    assert 'private-native-canary' not in repr(transport)
    with transport.parameters() as value:assert value['password']=='private-native-canary'
    transport.close()
    assert all(lease.closed for lease in transport._secrets.values())
    with pytest.raises(ContinuityError):
        with transport.parameters():pytest.fail('Released native credentials were reused')


@pytest.fixture
def jobs(tmp_path,monkeypatch):
    class FakeTools:
        def __init__(self,_paths):pass
        def identify(self,_name,_workspace):return {'available':True,'version':'PostgreSQL 18.3','executable_sha256':'a'*64}
    import pgadmin.cdeadmin.workspace.postgresql_continuity_jobs as module
    monkeypatch.setattr(module,'PhysicalTools',FakeTools)
    manager=PostgreSQLContinuityJobs(tmp_path/'jobs.json',tmp_path/'artifacts')
    source={'system_identifier':'18446744073709551615','server_version':180003,'authenticated_principal':'native-owner',
            'timeline':1,'lsn':'0/100','tablespaces':[],'summarize_wal':'on'}
    endpoint=str(uuid.uuid4())
    yield manager,source,endpoint
    manager.close()


def review(jobs):
    manager,source,endpoint=jobs
    return manager.review({'operation':'full_backup'},1,endpoint,source,'configuration',{})


def test_backup_review_is_scoped_persistent_and_has_no_private_transport(jobs):
    manager,source,endpoint=jobs
    reviewed=review(jobs)
    restarted=PostgreSQLContinuityJobs(manager.path,manager.root)
    assert restarted.get(reviewed['job_id'],1,endpoint)['source']['system_identifier']=='18446744073709551615'
    with pytest.raises(ContinuityError):restarted.get(reviewed['job_id'],2,endpoint)
    with pytest.raises(ContinuityError):restarted.get(reviewed['job_id'],1,str(uuid.uuid4()))
    assert restarted.list(1,endpoint)['total']==1
    assert restarted.list(2,endpoint)['jobs']==[]
    assert 'password' not in json.dumps(restarted.get(reviewed['job_id'],1,endpoint))


def test_changed_review_and_native_principal_refuse_dispatch(jobs):
    manager,source,endpoint=jobs
    reviewed=review(jobs)
    request={key:reviewed[key] for key in ('job_id','review_digest')};request['confirmed']=True
    lease=ContinuityTransport({})
    with pytest.raises(ContinuityError,match='target or registration'):
        manager.start(request,1,endpoint,{**source,'authenticated_principal':'another-principal'},'configuration',lease)
    assert lease.closed
    with manager.store(reviewed['job_id']) as store:
        def mutate(state):state['postgresql_continuity_jobs'][reviewed['job_id']]['options']['create_slot']=True
        store.change(mutate)
    lease=ContinuityTransport({})
    with pytest.raises(ContinuityError,match='fingerprint'):
        manager.start(request,1,endpoint,source,'configuration',lease)
    assert lease.closed


def test_duplicate_start_never_replays_and_cross_instance_cancel_reaches_worker(jobs):
    manager,source,endpoint=jobs
    reviewed=review(jobs)
    request={key:reviewed[key] for key in ('job_id','review_digest')};request['confirmed']=True
    calls=[];started=threading.Event();stopped=threading.Event()
    def run(record,transport,signal):
        calls.append(record['job_id']);started.set()
        try:signal.wait(5);manager.update(record,state='cancelled')
        finally:
            transport.close();manager.workers.pop(record['job_id'],None);stopped.set()
    manager.run=run
    manager.start(request,1,endpoint,source,'configuration',ContinuityTransport({}))
    assert started.wait(2)
    duplicate=ContinuityTransport({})
    manager.start(request,1,endpoint,source,'configuration',duplicate)
    assert duplicate.closed and len(calls)==1
    restarted=PostgreSQLContinuityJobs(manager.path,manager.root)
    restarted.cancel(reviewed['job_id'],1,endpoint)
    assert stopped.wait(2)
    assert restarted.get(reviewed['job_id'],1,endpoint)['state']=='cancelled'


def test_stopped_worker_is_unknown_and_never_relabelled_as_a_new_review(jobs):
    manager,source,endpoint=jobs
    reviewed=review(jobs)
    manager.update(manager.load(reviewed['job_id'],1,endpoint),state='active',worker_identity=[999999999,0])
    assert manager.get(reviewed['job_id'],1,endpoint)['state']=='unknown'
    request={key:reviewed[key] for key in ('job_id','review_digest')};request['confirmed']=True
    lease=ContinuityTransport({})
    assert manager.start(request,1,endpoint,source,'configuration',lease)['state']=='unknown'
    assert lease.closed


def test_reconstruction_has_its_own_options_and_preserves_order(jobs,monkeypatch):
    manager,source,endpoint=jobs
    records=[review(jobs),review(jobs)]
    for item in records:
        manager.update(manager.load(item['job_id'],1,endpoint),state='verified',manifest={'manifest_sha256':item['job_id']})
    combined=manager.review({'operation':'combine','chain':[item['job_id'] for item in records],
        'options':{'copy_mode':'clone'}},1,endpoint,source,'configuration',{})
    assert combined['options']['copy_mode']=='clone'
    assert [item['job_id'] for item in combined['inputs']]==[item['job_id'] for item in records]
    assert 'create_slot' not in combined['options']


def test_reconciliation_refuses_a_backup_writer_with_no_confirmed_termination(jobs):
    manager,source,endpoint=jobs
    reviewed=review(jobs)
    record=manager.load(reviewed['job_id'],1,endpoint)
    manager.update(record,state='active',worker_identity=[999999999,0])
    with pytest.raises(ContinuityError,match='termination is unconfirmed'):
        manager.require_stopped_writer(manager.load(record['job_id'],1,endpoint))
    manager.update(record,progress={'pid':__import__('os').getpid(),'process_create_time':manager.worker_identity[1]})
    with pytest.raises(ContinuityError,match='termination is unconfirmed'):
        manager.require_stopped_writer(manager.load(record['job_id'],1,endpoint))
    manager.update(record,progress={'pid':999999999,'process_create_time':0})
    manager.require_stopped_writer(manager.load(record['job_id'],1,endpoint))


def test_offline_receipts_and_verification_do_not_open_a_native_workspace(jobs,monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from flask import Flask
    from pgadmin.cdeadmin.workspace.postgresql_continuity_service import action
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService
    from pgadmin.cdeadmin.operations.store import JsonOperationStore
    manager,source,endpoint=jobs
    original=review(jobs)
    manager.update(manager.load(original['job_id'],1,endpoint),state='verified',manifest={'manifest_sha256':'a'*64})
    endpoint_model=SimpleNamespace(id=endpoint,provider_id='org.pgadmin.postgresql',provider_version=None,
        **{name:str(uuid.uuid4()) for name in ('pool_namespace','session_namespace','cache_namespace','diagnostic_namespace')})
    server=SimpleNamespace(id=1,user_id=1,endpoint_profile=endpoint_model,password=None)
    service=object.__new__(ProviderWorkspaceService)
    service._semantic_lock=threading.RLock();service.postgresql_continuity_jobs=manager
    service.operation_bus=SimpleNamespace(store=JsonOperationStore(manager.path))
    service.endpoint_service=Mock()
    service.endpoint_service.workspace.side_effect=AssertionError('Offline artifact inspection must not open SQL')
    service.endpoint_service.provider_registry.admitted_permissions.return_value={'backup_admin'}
    app=Flask(__name__)
    with app.app_context():
        assert action(service,server,'list',{})['total']==1
        assert action(service,server,'status',{'job_id':original['job_id']})['state']=='verified'
        result=action(service,server,'review',{'operation':'verify','base_job_id':original['job_id']})
        assert result['source']==source
        assert result['operation']=='verify'
    service.endpoint_service.workspace.assert_not_called()
    context=service.endpoint_service.provider_registry.admitted_permissions.call_args.args[0]
    assert context.runtime_verification_state=='unverified'


def test_offline_verification_retains_original_wal_and_checksum_scope(jobs):
    manager,source,endpoint=jobs
    selected=manager.review({'operation':'full_backup','options':{'wal_method':'none','manifest_checksums':'NONE'}},
        1,endpoint,source,'configuration',{})
    manager.update(manager.load(selected['job_id'],1,endpoint),state='verified',manifest={'manifest_sha256':'b'*64},
        verification_scope={'files':True,'wal':False})
    checked=manager.review({'operation':'verify','base_job_id':selected['job_id']},1,endpoint,source,'configuration',{})
    assert checked['options']['wal_method']=='none' and checked['options']['manifest_checksums']=='NONE'
    assert checked['artifact_location']==selected['artifact_location']
    assert any('WAL archive' in warning for warning in checked['warnings'])


def test_tar_file_verification_exclusion_does_not_erase_collected_wal(jobs):
    manager,source,endpoint=jobs
    selected=manager.review({'operation':'full_backup','options':{'format':'tar'}},1,endpoint,source,'configuration',{})
    manager.update(manager.load(selected['job_id'],1,endpoint),state='verified',manifest={'manifest_sha256':'c'*64},
        verification_scope={'files':True,'wal':False})
    checked=manager.review({'operation':'verify','base_job_id':selected['job_id']},1,endpoint,source,'configuration',{})
    assert checked['artifact_wal_method']=='stream'
    assert checked['options']['format']=='tar'


def test_native_transport_does_not_embed_a_temporary_service_in_normal_recovery_config(tmp_path):
    from unittest.mock import Mock
    from pgadmin.cdeadmin.providers.postgresql.continuity import PhysicalTools
    tools=PhysicalTools({});tools.identify=lambda *_args:{'available':True};tools.runner=Mock()
    tools.execute('pg_basebackup',tmp_path,['--write-recovery-conf'],parameters={'host':'localhost','password':'native-secret'})
    arguments=tools.runner.run.call_args.args[1]
    keywords=tools.runner.run.call_args.kwargs
    assert arguments==['--write-recovery-conf'] and keywords['secret_config'] is None
    assert keywords['secret_environment']['PGPASSWORD']=='native-secret'
    tools.runner.reset_mock()
    with pytest.raises(ContinuityError,match='temporary native service alias'):
        tools.execute('pg_basebackup',tmp_path,['--write-recovery-conf'],parameters={'sslpassword':'encrypted-key-secret'})
    tools.runner.run.assert_not_called()


@pytest.mark.parametrize('identity',[None,False,'../unowned','not-a-job'])
def test_untrusted_job_identity_is_a_scoped_admission_error(jobs,identity):
    manager,_source,endpoint=jobs
    with pytest.raises(ContinuityError,match='job identity'):manager.get(identity,1,endpoint)


def test_refused_native_worker_preserves_an_actionable_nonsecret_reason(jobs,monkeypatch):
    import pgadmin.cdeadmin.workspace.postgresql_continuity_jobs as module
    manager,_source,endpoint=jobs
    reviewed=review(jobs);record=manager.load(reviewed['job_id'],1,endpoint)
    class ChangedTools:
        def __init__(self,_paths):pass
        def identify(self,*_args):raise ContinuityError('Native utility installation changed')
    monkeypatch.setattr(module,'PhysicalTools',ChangedTools)
    lease=ContinuityTransport({})
    manager.run(record,lease,threading.Event())
    result=manager.get(record['job_id'],1,endpoint)
    assert result['state']=='failed' and result['error_reason']=='Native utility installation changed'
    assert lease.closed and result['automatic_retry'] is False
