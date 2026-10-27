"""Independent acceptance scopes, native SQL preservation and lock outcomes."""
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_instance_acceptance as native
from pgadmin.cdeadmin.providers.mysql_family import mysql_acceptance_lock_owner as lock_owner
from pgadmin.cdeadmin.workspace.mysql_instance_acceptance_jobs import InstanceAcceptanceJobs
from pgadmin.cdeadmin.workspace.mysql_binlog_replay_jobs import MySQLBinlogReplayJobs


def write(path,body,host='owned source'):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('-- MySQLShell dump 2.0.1  Distrib Ver 9.7.0 for Linux\n--\n-- Host: '+host+'\n-- ------------------------------------------------------\n-- Server version\t9.7.0\n'+body)


def test_only_the_native_transport_preamble_is_omitted_and_sql_text_is_preserved(tmp_path):
    a,b=tmp_path/'a.sql',tmp_path/'b.sql'
    body="SELECT '-- Host: value in actual SQL';\n-- Server version is an application comment\n"
    write(a,body);write(b,body,host='independent target')
    assert native.definition_hash(a)==native.definition_hash(b)
    write(b,body.replace('actual SQL','changed SQL'),host='independent target')
    assert native.definition_hash(a)!=native.definition_hash(b)
    a.write_text('-- arbitrary application SQL\n'+body)
    with pytest.raises(native.BinlogArchiveError,match='header'):native.definition_hash(a)


def test_exported_account_differences_are_separate_and_no_sql_or_authentication_material_is_returned(tmp_path):
    source,target=tmp_path/'source',tmp_path/'target'
    for root in (source,target):write(root/'native.sql','CREATE DATABASE `native`;\n')
    write(source/'@.users.sql','-- owned fixture authentication material\n')
    write(target/'@.users.sql','-- changed fixture authentication material\n')
    artifact={'files':[{'path':'native.sql'},{'path':'@.users.sql'}]}
    result=native.definitions(source,target,{'definitions_requested':True,'accounts_requested':True},artifact,artifact)
    assert result['definitions']['matched'] is True and result['accounts']['matched'] is False
    assert 'authentication material' not in json.dumps(result)
    assert result['accounts']['differences'][0]['file']=='@.users.sql'


def test_unexported_data_and_empty_account_selection_are_never_inferred_successful(tmp_path):
    (tmp_path/'@.json').write_text(json.dumps({'basenames':{'native':'native'}}))
    (tmp_path/'native.json').write_text(json.dumps({'schema':'native','tables':[],'views':[],'basenames':{}}))
    artifact={'schemas':[{'schema':'native','includes_data':False,'includes_ddl':True,'objects':{'tables':[],'views':[]}}],
        'users':[],'native_checksums_included':False,'files':[{'path':'native.sql'}]}
    result=native.scopes(tmp_path,artifact)
    assert not result['data_requested'] and not result['accounts_requested'] and result['definitions_requested']
    artifact['files']=[]
    with pytest.raises(native.BinlogArchiveError,match='SQL files'):native.scopes(tmp_path,artifact)


def test_native_object_basenames_are_complete_filenames_not_table_suffixes(tmp_path):
    (tmp_path/'@.json').write_text(json.dumps({'basenames':{'native':'native'}}))
    (tmp_path/'native.json').write_text(json.dumps({'includesViewsDdl':True,'basenames':{'t':'native@t'}}))
    artifact={'schemas':[{'schema':'native','includes_data':False,'includes_ddl':True,'objects':{'tables':['t'],'views':[]}}],
        'users':None,'native_checksums_included':False,'files':[{'path':'native.sql'},{'path':'native@t.sql'}]}
    assert native.scopes(tmp_path,artifact)['definitions_requested']


@pytest.mark.parametrize('value',[{}, {'target_confirmation':'unknown','server_wide_write_pause_confirmed':True},
    {'target_confirmation':str(uuid.uuid4()),'server_wide_write_pause_confirmed':False},
    {'target_confirmation':str(uuid.uuid4()),'server_wide_write_pause_confirmed':True,'threads':True}])
def test_read_lock_and_exact_native_target_need_explicit_admission(value):
    with pytest.raises(native.BinlogArchiveError):native.options(value)


def test_unconfirmed_server_lock_cleanup_cannot_release_shared_target_protection(tmp_path):
    replay=MySQLBinlogReplayJobs(tmp_path/'replays',tmp_path/'replay-files')
    jobs=InstanceAcceptanceJobs(tmp_path/'acceptance',tmp_path/'acceptance-files');jobs.replay_jobs=replay
    endpoint=str(uuid.uuid4());target={'server_uuid':str(uuid.uuid4()),'version':'9.7.0'}
    def review():return jobs.review(1,endpoint,{}, {'identity':target,'state':{'input_reference':{}}},'config',{'execution_host':{'kind':'application-host'}})
    planned=review();record=jobs.load(planned['job_id'],1,endpoint);jobs.claim_fence(record)
    result={'native_checks_returned':True,'selected_dump_surfaces_verified':True,'server_locks_released':False,
        'tool':{'process_observation':{'cleanup_confirmed':True}},'data':{'requested':True,'matched':True}}
    transport=SimpleNamespace(execute=Mock(return_value=result),close=Mock())
    jobs.run(record,transport,threading.Event())
    receipt=jobs.get(record['job_id'],1,endpoint)
    assert receipt['acceptance_outcome']=='matched' and receipt['restore_issued'] is False
    assert receipt['recovery_fence_release_confirmed'] is False
    with pytest.raises(native.BinlogArchiveError,match='unresolved'):jobs.claim_fence(jobs.load(review()['job_id'],1,endpoint))
    jobs.close();replay.close()


@pytest.mark.parametrize('present,free,expected', [(False,1,True),(True,1,False),(False,0,False),(True,0,False),(False,None,False)])
def test_private_owner_absence_requires_both_thread_cleanup_and_released_marker(monkeypatch,present,free,expected):
    job_id,target=str(uuid.uuid4()),str(uuid.uuid4())
    record={'job_id':job_id,'source':{'server_uuid':target},'server_lock_owner':{
        'admitted':True,'server_uuid':target,'thread_id':'12','connection_id':'42','lock_name':lock_owner.lock_name(job_id)}}
    monkeypatch.setattr(lock_owner,'private_thread',lambda _connection:{'server_uuid':target})
    def rows(_connection,source,_parameters):
        return ([{'THREAD_ID':12}] if present else []) if 'performance_schema.threads' in source else [{'free':free}]
    monkeypatch.setattr(lock_owner,'rows',rows)
    result=lock_owner.observe(object(),record)
    assert result['qualified'] and result['released'] is expected


@pytest.mark.parametrize('fault',['legacy','denied','different-server','changed-marker','invalid-thread'])
def test_missing_or_unqualified_native_owner_evidence_never_confirms_cleanup(monkeypatch,fault):
    job_id,target=str(uuid.uuid4()),str(uuid.uuid4())
    record={'job_id':job_id,'source':{'server_uuid':target},'server_lock_owner':{
        'admitted':True,'server_uuid':target,'thread_id':'12','connection_id':'42','lock_name':lock_owner.lock_name(job_id)}}
    if fault=='legacy':record.pop('server_lock_owner')
    if fault=='changed-marker':record['server_lock_owner']['lock_name']=lock_owner.lock_name(str(uuid.uuid4()))
    if fault=='invalid-thread':record['server_lock_owner']['thread_id']='0'
    def private(_connection):
        if fault=='denied':raise PermissionError('owned unavailable fixture')
        return {'server_uuid':str(uuid.uuid4()) if fault=='different-server' else target}
    monkeypatch.setattr(lock_owner,'private_thread',private)
    monkeypatch.setattr(lock_owner,'rows',Mock(side_effect=AssertionError('No unsafe fallback observation')))
    result=lock_owner.observe(object(),record)
    assert result['qualified'] is False and result['released'] is None


def test_marker_contention_refuses_before_sql_locks_instead_of_downgrading_admission(monkeypatch):
    target=str(uuid.uuid4())
    monkeypatch.setattr(lock_owner,'private_thread',lambda _connection:{'server_uuid':target,'thread_id':12,'connection_id':42})
    monkeypatch.setattr(lock_owner,'rows',lambda *_args:[{'acquired':0}])
    with pytest.raises(native.BinlogArchiveError,match='Another native connection'):
        lock_owner.acquire(object(),str(uuid.uuid4()),target)


@pytest.mark.parametrize('unknown',[False,True])
def test_cleanup_reconciliation_preserves_original_facts_and_unknown_acknowledgement(tmp_path,unknown):
    replay=MySQLBinlogReplayJobs(tmp_path/'replays',tmp_path/'replay-files')
    jobs=InstanceAcceptanceJobs(tmp_path/'acceptance',tmp_path/'acceptance-files');jobs.replay_jobs=replay
    endpoint,target=str(uuid.uuid4()),str(uuid.uuid4())
    planned=jobs.review(1,endpoint,{}, {'identity':{'server_uuid':target},'state':{'input_reference':{}}},'config',{'execution_host':{'kind':'application-host'}})
    record=jobs.load(planned['job_id'],1,endpoint);jobs.claim_fence(record)
    original={'server_locks_released':False,'selected_dump_surfaces_verified':True}
    jobs.update(record,state='unknown' if unknown else 'verification_observed',result=original,
        acceptance_outcome='unconfirmed' if unknown else 'matched',native_load_outcome='not_dispatched',
        native_process_termination_confirmed=True,recovery_fence_release_confirmed=False)
    observation={'native_lock_free':True,'private_server_lock_cleanup':{'qualified':True,'released':True}}
    result=jobs.reconcile(jobs.load(record['job_id'],1,endpoint),observation)
    assert result['result']==original and result['recovery_fence_release_confirmed']
    with jobs.fence_store(target) as store:assert bool(store.read().get('replay_fence')) is unknown
    if unknown:
        from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import digest
        result=jobs.acknowledge(record,observation,{'target_confirmation':target,'observation_digest':digest(observation)})
        assert result['state']=='unknown' and result['acceptance_outcome']=='unconfirmed'
    jobs.close();replay.close()
