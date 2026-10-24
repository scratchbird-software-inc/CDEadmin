"""Native initialization host authority, target admission and cancellation."""
import socket
import json
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import uuid
import pytest
from pgadmin.cdeadmin.providers.mysql_family import mysql_host_initialization as initial
from pgadmin.cdeadmin.providers.mysql_family import mysql_host_worker as worker
from pgadmin.cdeadmin.workspace import mysql_host_service as service
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import DurableCancellation
from test_mysql_host import host


@pytest.mark.skipif(sys.platform!='linux',reason='Linux native host initialization')
def test_initialization_review_has_host_authority_and_no_invented_sql_instance_identity(host,tmp_path):
    target=tmp_path/'new-mysql'
    request={**host.request,'binding':{'scope':initial.SCOPE,'datadir':str(target)},
        'initialization':{'datadir':str(target),'user':'mysql','secure':True}}
    observed=worker.dispatch(request)
    assert observed['host']['hostname']==socket.gethostname() and 'server_uuid' not in observed['host']
    assert observed['initialization_plan']['native_instance_identity_before_initialization'] is None
    assert not observed['initialization_plan']['before']['exists'] and not target.exists()
    assert host.directory.exists()


@pytest.mark.skipif(sys.platform!='linux',reason='Linux native host initialization')
def test_native_empty_directory_rules_preserve_hidden_files_and_lost_found(host,tmp_path):
    target=tmp_path/'empty';target.mkdir();(target/'.preserved').write_text('retained');(target/'lost+found').mkdir()
    request={**host.request,'binding':{'scope':initial.SCOPE,'datadir':str(target)},
        'initialization':{'datadir':str(target),'user':'mysql','secure':False}}
    assert worker.dispatch(request)['initialization_plan']['before']['entries']==['.preserved','lost+found']
    (target/'existing-engine-data').write_text('must not change')
    with pytest.raises(ValueError,match='existing data'):worker.dispatch(request)
    assert (target/'existing-engine-data').read_text()=='must not change'


def test_cancel_between_early_observation_and_atomic_dispatch_claim_never_sends_host_command(tmp_path,monkeypatch):
    jobs=service.HostJobs(tmp_path/'jobs',tmp_path/'files');endpoint=str(uuid.uuid4())
    planned=jobs.review(1,endpoint,{'operation':'validate_config','timeout_seconds':60},
        {'identity':{'server_uuid':str(uuid.uuid4())},'state':{'remote_review':{}}},'registration',{'execution_host':{'hostname':'owned'}})
    record=jobs.load(planned['job_id'],1,endpoint);signal=threading.Event();calls=[]
    def racing_observation(_cancel):
        calls.append(True);jobs.cancel(record['job_id'],1,endpoint)
        return False
    monkeypatch.setattr(DurableCancellation,'is_set',racing_observation)
    transport=SimpleNamespace(request=Mock(side_effect=AssertionError('Cancelled request must never dispatch')),close=Mock())
    jobs.run(record,transport,signal)
    observed=jobs.get(record['job_id'],1,endpoint)
    assert calls and observed['state']=='cancelled' and not observed.get('native_may_have_dispatched')
    transport.request.assert_not_called();jobs.close()


@pytest.mark.skipif(sys.platform!='linux',reason='Linux original-writer reconciliation')
@pytest.mark.parametrize('started',[False,True])
def test_lost_guardian_admission_and_changed_boot_remain_independent_of_native_outcome(tmp_path,monkeypatch,started):
    directory=tmp_path/'receipt';directory.mkdir();target=tmp_path/'partial';target.mkdir();(target/'preserved').write_bytes(b'partial-native-data')
    request={'job_id':str(uuid.uuid4()),'input_digest':'original','workspace':str(tmp_path)}
    intent={'request':request,'observed':{'initialization_plan':{'datadir':str(target)}},'nonce':'original-nonce'}
    worker.save(directory/'initializer-request.json',intent)
    claim=initial.fence_path(target)
    worker.save(claim,{**request,'nonce':intent['nonce']})
    value={'state':'native_dispatch','job_id':request['job_id'],'input_digest':'original','automatic_retry':False}
    if started:
        worker.save(directory/'initializer-started.json',{'nonce':intent['nonce'],'input_digest':'original',
            'kernel':{'boot_id':'old-boot','pid_namespace':'original-namespace'}})
        monkeypatch.setattr(initial,'kernel',lambda:{'boot_id':'new-boot','pid_namespace':'new-namespace'})
    observed=initial.observe(directory,value,worker.__dict__,cancel=True)
    assert observed['state']=='native_dispatch' and 'result' not in observed and 'initialization_result' not in observed
    assert json.loads((directory/'initializer-cancel.json').read_text())=={'nonce':'original-nonce'}
    assert observed['initialization_reconciliation']['process_termination_confirmed']==started
    if started:
        assert initial.observe(directory,value,worker.__dict__,acknowledge=True)['initialization_reconciliation']['target_claim_released']
        assert not claim.exists()
    else:
        with pytest.raises(ValueError,match='writers have not ended'):initial.observe(directory,value,worker.__dict__,acknowledge=True)
        assert claim.exists()
    assert (target/'preserved').read_bytes()==b'partial-native-data'
