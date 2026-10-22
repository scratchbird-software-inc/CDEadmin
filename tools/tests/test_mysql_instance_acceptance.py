"""Independent acceptance scopes, native SQL preservation and lock outcomes."""
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_instance_acceptance as native
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
