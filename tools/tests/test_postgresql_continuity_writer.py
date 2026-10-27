"""Owned native PostgreSQL processes survive an application worker interruption."""
import os
from pathlib import Path
import time
import uuid

import psutil
import pytest

from postgresql_qualification_support import waiting_native

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError, binary_paths
from pgadmin.cdeadmin.workspace.postgresql_continuity_jobs import PostgreSQLContinuityJobs


@pytest.fixture
def owned(tmp_path):
    paths=binary_paths(os.environ.get('CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH','/usr/lib/postgresql/18/bin'))
    if not all(Path(paths[name]).is_file() for name in ('pg_basebackup','pg_verifybackup')):
        pytest.skip('Native PostgreSQL 18 continuity utilities are required')
    jobs=PostgreSQLContinuityJobs(tmp_path/'jobs.json',tmp_path/'artifacts')
    endpoint=str(uuid.uuid4())
    source={'system_identifier':'18446744073709551615','server_version':180003,'authenticated_principal':'owned',
            'timeline':1,'lsn':'0/100','tablespaces':[],'summarize_wal':'on'}
    reviewed=jobs.review({'operation':'full_backup'},1,endpoint,source,'owned',paths)
    record=jobs.load(reviewed['job_id'],1,endpoint)
    directory=jobs.directory(record);directory.mkdir(parents=True)
    jobs.update(record,state='active',worker_identity=[999999999,0],started_at=time.time())
    try:yield jobs,record,endpoint,directory,paths
    finally:jobs.close()


def observe(jobs, record, process):
    jobs.update(record,progress={'pid':process.pid,'process_create_time':process.create_time()})


@pytest.mark.parametrize('progress_recorded',[True,False])
def test_orphan_native_writer_is_stopped_without_claiming_backup_success(owned,progress_recorded):
    jobs,record,endpoint,directory,paths=owned
    with waiting_native(directory,paths,orphan=True) as process, waiting_native(directory.parent/'peer',paths) as peer:
        if progress_recorded:observe(jobs,record,process)
        assert jobs.get(record['job_id'],1,endpoint)['state']=='unknown'
        result=jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':True},1,endpoint)
        assert result['state']=='unknown' and result['automatic_retry'] is False
        proof=result['writer_reconciliation']
        assert proof['process_scope_stopped'] is True
        assert proof['artifact_verified'] is False and proof['remote_finality_inferred'] is False
        assert [item['pid'] for item in proof['processes']]==[process.pid]
        assert peer.is_running() and peer.status()!=psutil.STATUS_ZOMBIE
        jobs.require_stopped_writer(jobs.load(record['job_id'],1,endpoint))
        repeated=jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':True},1,endpoint)
        assert repeated['state']=='unknown' and repeated['writer_reconciliation']==proof


@pytest.mark.parametrize('fault',['owner','endpoint','unconfirmed','active_worker','wrong_workspace','wrong_executable','missing_creation','different_host'])
def test_reconciliation_refuses_unowned_or_unconfirmed_dispatch(owned,fault):
    jobs,record,endpoint,directory,paths=owned
    selected=directory.parent/'peer' if fault=='wrong_workspace' else directory
    with waiting_native(selected,paths) as process:
        observe(jobs,record,process)
        owner=2 if fault=='owner' else 1
        selected_endpoint=str(uuid.uuid4()) if fault=='endpoint' else endpoint
        request={'job_id':record['job_id'],'confirmed':fault!='unconfirmed'}
        if fault=='active_worker':jobs.update(record,worker_identity=jobs.worker_identity);jobs.workers[record['job_id']]=( __import__('threading').current_thread(),None)
        if fault=='wrong_executable':jobs.update(record,tool_identities={'pg_basebackup':{'available':True,'executable_sha256':'0'*64}})
        if fault=='missing_creation':jobs.update(record,progress={'pid':process.pid})
        if fault=='different_host':jobs.update(record,execution_host={'hostname':'different-owned-host.invalid'})
        try:
            with pytest.raises(ContinuityError):jobs.reconcile_writer(request,owner,selected_endpoint)
            assert process.is_running() and process.status()!=psutil.STATUS_ZOMBIE
        finally:jobs.workers.pop(record['job_id'],None)


def test_reused_pid_never_signals_the_new_process(owned):
    jobs,record,endpoint,directory,paths=owned
    with waiting_native(directory,paths) as process:
        jobs.update(record,progress={'pid':process.pid,'process_create_time':process.create_time()-100})
        result=jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':True},1,endpoint)
        assert result['writer_reconciliation']['recorded_process_absent'] is True
        assert result['writer_reconciliation']['processes']==[]
        assert process.is_running() and process.status()!=psutil.STATUS_ZOMBIE


def test_verification_rechecks_the_reconciled_workspace(owned):
    jobs,record,endpoint,directory,paths=owned
    jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':True},1,endpoint)
    with waiting_native(directory,paths) as process:
        with pytest.raises(ContinuityError,match='still using this backup workspace'):
            jobs.require_stopped_writer(jobs.load(record['job_id'],1,endpoint))
        observe(jobs,record,process)
        result=jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':True},1,endpoint)
        assert result['writer_reconciliation']['processes'][0]['termination_confirmed']


def test_dead_parent_observation_does_not_admit_verification_over_orphan_writer(owned):
    jobs,record,endpoint,directory,paths=owned
    with waiting_native(directory,paths,orphan=True):
        jobs.update(record,progress={'pid':999999999,'process_create_time':0})
        with pytest.raises(ContinuityError,match='termination is unconfirmed'):
            jobs.require_stopped_writer(jobs.load(record['job_id'],1,endpoint))
        jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':True},1,endpoint)
        jobs.require_stopped_writer(jobs.load(record['job_id'],1,endpoint))


def test_legacy_receipt_needs_a_locally_observed_owned_utility_before_host_binding(owned):
    jobs,record,endpoint,directory,paths=owned
    jobs.update(record,execution_host={'kind':'application-host','platform':os.name})
    with pytest.raises(ContinuityError,match='legacy receipt'):
        jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':True},1,endpoint)
    with waiting_native(directory,paths) as process:
        observe(jobs,record,process)
        result=jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':True},1,endpoint)
        assert result['writer_reconciliation']['hostname']==__import__('socket').gethostname()
        jobs.require_stopped_writer(jobs.load(record['job_id'],1,endpoint))


def test_a_review_cannot_dispatch_on_another_application_host(owned,monkeypatch):
    jobs,record,endpoint,_directory,_paths=owned
    # This fixture seeds an interrupted dispatch. Return only its owned receipt
    # to reviewed state to exercise the actual immutable review admission.
    jobs.update(record,state='reviewed')
    import pgadmin.cdeadmin.workspace.postgresql_continuity_jobs as module
    monkeypatch.setattr(module.socket,'gethostname',lambda:'another-application-host.invalid')
    from pgadmin.cdeadmin.providers.postgresql.continuity_transport import ContinuityTransport
    transport=ContinuityTransport({})
    with pytest.raises(ContinuityError,match='execution host changed'):
        jobs.start({'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True},
                   1,endpoint,record['source'],record['configuration'],transport)
    assert transport.closed and jobs.load(record['job_id'],1,endpoint)['state']=='reviewed'
