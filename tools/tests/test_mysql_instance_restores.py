"""Native instance restore admission, acknowledgement and target fences."""
from types import SimpleNamespace
from unittest.mock import Mock
import threading
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_instance_restores as native
from pgadmin.cdeadmin.workspace.mysql_instance_restore_jobs import InstanceRestoreJobs
from pgadmin.cdeadmin.workspace.mysql_binlog_replay_jobs import MySQLBinlogReplayJobs


def identity():
    return {'server_uuid': str(uuid.uuid4()), 'version': '9.7.0', 'authenticated_principal': 'restore@%', 'active_role': 'NONE'}


def test_instance_load_options_use_native_user_schema_and_gtid_controls_at_server_scope():
    target=identity()['server_uuid']
    selected=native.options({'target_confirmation':target,'load_users':True,'exclude_users':['root'],
        'include_schemas':['native雪'],'update_gtid_set':'append','dry_run':True}, {'host':'owned','tool_workspace':'/owned'})
    assert selected['native_options']['loadUsers'] is True
    assert selected['native_options']['excludeUsers']==['root']
    assert selected['native_options']['updateGtidSet']=='append' and selected['native_options']['dryRun']
    assert selected['target_confirmation']==target


@pytest.mark.parametrize('extra',[{'path':'/outside'},{'progress_file':'/outside'},{'schema':'different'},
    {'enable_local_infile':True},{'timeout_seconds':False},{'load_users':'true'},{'unknown':True}])
def test_instance_load_refuses_unmanaged_paths_and_invalid_native_options(extra):
    with pytest.raises(native.BinlogArchiveError):native.options({'target_confirmation':identity()['server_uuid'],**extra},{'host':'owned','tool_workspace':'/owned'})


def setup(tmp_path):
    replays=MySQLBinlogReplayJobs(tmp_path/'replays',tmp_path/'replay-files')
    jobs=InstanceRestoreJobs(tmp_path/'restores',tmp_path/'restore-files');jobs.replay_jobs=replays
    endpoint=str(uuid.uuid4());target=identity()
    def review():
        return jobs.review(1,endpoint,{}, {'identity':target,'state':{'input_reference':{'job_id':str(uuid.uuid4())}}},
            'config', {'execution_host':{'kind':'application-host'}})
    return jobs,replays,endpoint,target,review


def test_native_ack_survives_a_later_receipt_failure_and_start_does_not_replay(tmp_path,monkeypatch):
    jobs,replays,endpoint,_target,review=setup(tmp_path);planned=review();record=jobs.load(planned['job_id'],1,endpoint)
    original=jobs.update
    def update(value,**fields):
        if fields.get('state')=='native_load_returned':raise OSError('owned receipt failure after native return')
        return original(value,**fields)
    monkeypatch.setattr(jobs,'update',update)
    result={'control':{'native_load_invoked':True,'native_load_returned':True,'stage':'returned','native_error':None},
        'tool':{'process_observation':{'cleanup_confirmed':True},'return_code':0}}
    def execute(_record,_directory,_cancel,_progress,boundary):boundary();return result
    transport=SimpleNamespace(execute=Mock(side_effect=execute),close=Mock())
    jobs.run(record,transport,threading.Event())
    current=jobs.get(record['job_id'],1,endpoint)
    assert current['native_load_outcome']=='returned' and current['state']=='native_returned_unverified'
    assert not current['data_recovery_verified'] and current['native_process_termination_confirmed']
    jobs.start({key:planned[key] for key in ('job_id','review_digest')}|{'confirmed':True},1,endpoint,{},None)
    assert transport.execute.call_count==1
    jobs.close();replays.close()


def test_partial_native_error_keeps_shared_target_fence_until_explicit_observed_acknowledgement(tmp_path):
    jobs,replays,endpoint,target,review=setup(tmp_path);planned=review();record=jobs.load(planned['job_id'],1,endpoint)
    jobs.claim_fence(record)
    result={'control':{'native_load_invoked':True,'native_load_returned':False,'stage':'loading',
        'native_error':{'code':1227,'message':'native partial refusal'}},'tool':{'process_observation':{'cleanup_confirmed':True},'return_code':1}}
    def execute(_record,_directory,_cancel,_progress,boundary):boundary();return result
    jobs.run(record,SimpleNamespace(execute=execute,close=lambda:None),threading.Event())
    assert jobs.get(record['job_id'],1,endpoint)['state']=='unknown'
    with pytest.raises(native.BinlogArchiveError,match='unresolved'):jobs.claim_fence(jobs.load(review()['job_id'],1,endpoint))
    reference={'server_id':1,'endpoint_id':endpoint,'job_id':str(uuid.uuid4()),'artifact_digest':'owned',
        'summary':{'total_bytes':0}}
    replay=replays.review(1,endpoint,{}, {'identity':target,'state':{'input_reference':reference}},'config',{'execution_host':{'kind':'application-host'}})
    with pytest.raises(native.BinlogArchiveError,match='recovery operation'):replays.claim_fence(replays.load(replay['job_id'],1,endpoint))
    record=jobs.load(record['job_id'],1,endpoint);observed={'native_lock_free':False}
    from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import digest
    request={'target_confirmation':target['server_uuid'],'observation_digest':digest(observed)}
    with pytest.raises(native.BinlogArchiveError,match='termination'):jobs.acknowledge(record,observed,request)
    observed={'native_lock_free':True};request['observation_digest']=digest(observed)
    accepted=jobs.acknowledge(record,observed,request)
    assert accepted['native_load_outcome']=='unknown' and accepted['state']=='unknown'
    replays.claim_fence(replays.load(replay['job_id'],1,endpoint));replays.release_fence(replays.load(replay['job_id'],1,endpoint))
    jobs.close();replays.close()
