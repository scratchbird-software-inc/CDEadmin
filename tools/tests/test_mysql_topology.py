"""Native topology argument fidelity, safe receipts and shared target claims."""
import ast
import json
from types import SimpleNamespace
from unittest.mock import Mock
import threading
import time
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_topology as native
from pgadmin.cdeadmin.security import SecretLease
from pgadmin.cdeadmin.workspace.mysql_binlog_replay_jobs import MySQLBinlogReplayJobs
from pgadmin.cdeadmin.workspace.mysql_topology_jobs import TopologyJobs
from pgadmin.cdeadmin.workspace.mysql_backup_protection import Registry


def selected(operation='cluster.set_option',arguments='["tag:wide",9223372036854775808]'):
    return native.options({'operation':operation,'arguments_json':arguments,'target_confirmation':str(uuid.uuid4())})


def test_native_json_integer_and_method_specific_instance_types_remain_exact():
    value=selected()
    assert native.parse(value['arguments_json'])==['tag:wide',9223372036854775808]
    assert native.CALLS['cluster.add_instance']['instance_format']=='connection'
    assert native.CALLS['cluster.add_replica_instance']['instance_format']=='uri'
    assert native.CALLS['replica_set.add_instance']['instance_format']=='uri'
    assert native.CALLS['cluster_set.create_replica_cluster']['instance_format']=='uri'


@pytest.mark.parametrize('context',['cluster','replica_set','cluster_set'])
def test_guidelines_accept_native_documents_without_accepting_execution_host_paths(context):
    value=selected(context+'.import_routing_guideline','[{"name":"routes","native_number":9223372036854775808},{}]')
    assert native.parse(value['arguments_json'])[0]['native_number']==2**63
    with pytest.raises(native.BinlogArchiveError,match='JSON object'):
        selected(context+'.import_routing_guideline','["/arbitrary/file.json"]')
    assert native.CALLS[context+'.guideline.export']['read_only'] is True
    with pytest.raises(native.BinlogArchiveError):selected(context+'.guideline.export','["/arbitrary/file.json"]')
    assert native.options({'operation':context+'.guideline.rename','guideline_name':'old',
        'arguments_json':'["new"]','target_confirmation':str(uuid.uuid4())})['guideline_name']=='old'
    assert native.CALLS[context+'.guideline.rename']['arguments']==['name']


def test_router_global_and_selected_overloads_do_not_lose_null_or_false():
    assert native.parse(selected('cluster.set_router_option','["host::router","guideline",null]')['arguments_json'])==['host::router','guideline',None]
    assert native.CALLS['cluster.set_router_option']['method']=='set_routing_option'
    assert native.parse(selected('replica_set.guideline.set_route_option','["route","enabled",false]')['arguments_json'])==['route','enabled',False]
    with pytest.raises(native.BinlogArchiveError):selected('cluster.guideline.add_route','["route","true",[{}]]')
    assert native.CALLS['cluster_set.list_routers']['arguments']==['router?']


def test_reviewed_routing_documents_and_router_options_are_native_text_not_float_values():
    queries=[]
    def execute(_connection,source,parameters=()):
        queries.append(source)
        if source.startswith('SELECT TABLE_NAME'):
            return [{'TABLE_NAME':'routing_guidelines','COLUMN_NAME':name} for name in ('guideline_id','name','guideline')]
        return [{'identity':'owned','name':'route','document':'{"native":9223372036854775808}'}]
    from unittest.mock import patch
    with patch.object(native,'rows',execute):value=native.metadata(object())
    assert 'CAST(`guideline` AS CHAR)' in queries[-1]
    assert value['results'][-1][0][-1]=='{"native":9223372036854775808}'


@pytest.mark.parametrize('change',[{'operation':[]},{'operation':'unsupported'},
    {'arguments_json':'["tag:wide",NaN]'}, {'arguments_json':'["tag:wide",1e9999]'}, {'arguments_json':'["tag:wide"]'},
    {'arguments_json':'["tag:wide",18446744073709551616]'},
    {'arguments_json':'["tag:wide",-9223372036854775809]'},
    {'operation':'cluster.add_instance','arguments_json':'[{"host":"arbitrary","password":"must-not-be-retained"}]'},
    {'operation':'instance.configure_cluster','arguments_json':'[{"clusterAdminPassword":"must-not-be-retained"}]'},
    {'context_options_json':'{"password":"must-not-be-retained"}'}, {'timeout_seconds':True}])
def test_unowned_instances_and_inline_native_credentials_never_enter_a_review(change):
    with pytest.raises(native.BinlogArchiveError):native.options({'operation':'cluster.set_option',
        'arguments_json':'["tag:wide",1]','target_confirmation':str(uuid.uuid4()),**change})


@pytest.mark.parametrize("exported",[None,'{ "enabled": true, "wide": 9223372036854775808 }','{"enabled":true,"label":"true"}'])
def test_native_control_redaction_preserves_booleans_and_uint64_result_json(tmp_path,monkeypatch,exported):
    program={'executable_sha256':'owned','execution_host':{'kind':'application-host'}}
    monkeypatch.setattr(native,'program_identity',lambda *_args,**_kwargs:program)
    class Runner:
        def run(self,_grant,arguments,**_kwargs):
            assert _grant.durable_name=='mysql-topology' and _grant.guard_parent_death is True
            source=(tmp_path/'native-topology.py').read_text()
            tree=ast.parse(source)
            settings=next(node for node in tree.body if isinstance(node,ast.Assign) and
                any(isinstance(item,ast.Name) and item.id=='settings' for item in node.targets))
            marker=json.loads(settings.value.args[0].value)['marker']
            control={'native_load_invoked':True,'native_load_returned':True,'stage':'returned','native_error':None,
                'result_json':'{"enabled":true,"wide":9223372036854775808,"private":"true","tags":{"guideline_export_json":"true"}}',
                'observation_error':None}
            if exported is not None:control['result_json']=json.dumps({'guideline_export_json':exported})
            return {'stdout':marker+json.dumps(control)+'\n','stderr':'native text true',
                'return_code':0,'executable_sha256':'owned','process_observation':{'cleanup_confirmed':True}}
    client=SimpleNamespace(_tool_runner=Runner())
    with SecretLease(b'{"seed":{"password":"true"}}') as credentials:
        result=native.run(client,{'host':'owned'},credentials,
            selected() if exported is None else selected('cluster.guideline.export','[]'),
            {'connection':{'host':'owned','port':3306}}, {},tmp_path,program)
    if exported is None:
        assert json.loads(result['control']['result_json'])=={'enabled':True,'wide':9223372036854775808,'private':'[redacted]',
            'tags':{'guideline_export_json':'[redacted]'}}
    else:
        value=json.loads(result['control']['result_json'])
        if 'label' in exported:
            assert value['guideline_export_redacted'] is True
            assert json.loads(value['guideline_export_json'])=={'enabled':True,'label':'[redacted]'}
        else:
            assert value['guideline_export_json']==exported
            assert value['guideline_export_redacted'] is False
    assert result['control']['native_load_returned'] is True and 'true' not in result['output_text']


def setup(tmp_path,operation='cluster.set_option',arguments='["tag:wide",1]'):
    replays=MySQLBinlogReplayJobs(tmp_path/'replays',tmp_path/'replay-files')
    jobs=TopologyJobs(tmp_path/'topologies',tmp_path/'topology-files');jobs.replay_jobs=replays
    endpoint=str(uuid.uuid4());target={'server_uuid':str(uuid.uuid4()),'version':'9.7.0'}
    options=selected(operation,arguments)
    planned=jobs.review(1,endpoint,options,{'identity':target,'state':{'seed':{},'members':{}}},'config',{'execution_host':{'kind':'application-host'}})
    return jobs,replays,endpoint,target,planned


def test_returned_native_reply_survives_later_observation_failure(tmp_path):
    jobs,replays,endpoint,_target,planned=setup(tmp_path)
    record=jobs.load(planned['job_id'],1,endpoint);jobs.claim_fence(record)
    control={'native_load_invoked':True,'native_load_returned':True,'stage':'returned','native_error':None,
        'observation_error':{'code':1142,'message':'native observation denied'},'result_json':None}
    def execute(_record,_directory,_cancel,_progress,boundary):
        boundary();return {'control':control,'tool':{'return_code':0,'process_observation':{'cleanup_confirmed':True}}}
    jobs.run(record,SimpleNamespace(execute=execute,close=lambda:None),threading.Event())
    receipt=jobs.get(record['job_id'],1,endpoint)
    assert receipt['state']=='operation_returned' and receipt['native_operation_outcome']=='returned'
    assert receipt['result']['control']['observation_error']['code']==1142
    assert receipt['workload_readiness_verified'] is False
    jobs.close();replays.close()


def test_independent_native_tag_json_keeps_uint64_and_records_shell_decoder_scope():
    observation=native.tag_observation({'native_tag_json':[{'table':'clusters','identity':'native',
        'tags_json':'{"wide":18446744073709551615,"enabled":true}'}]})
    assert observation['native_shell_json_signed_limit'] is True
    assert json.loads(observation['tags'][0]['tags_json'])=={'wide':2**64-1,'enabled':True}
    assert native.tag_observation({'native_tag_json':[{'tags_json':'{"wide":9007199254740993}'}]})['native_shell_json_signed_limit'] is False


def test_utility_cleanup_cannot_clear_uncertain_server_side_clone_recovery(tmp_path):
    jobs,replays,endpoint,target,planned=setup(tmp_path,'cluster.add_instance','[{"server_id":2},{}]')
    record=jobs.load(planned['job_id'],1,endpoint);jobs.claim_fence(record)
    jobs.update(record,state='unknown',native_load_outcome='unknown',native_process_termination_confirmed=True)
    record=jobs.load(record['job_id'],1,endpoint)
    assert jobs.get(record['job_id'],1,endpoint)['server_recovery_clearance_required'] is True
    with pytest.raises(native.BinlogArchiveError,match='server-side completion evidence'):
        jobs.acknowledge(record,{'native_lock_free':True},{'target_confirmation':target['server_uuid']})
    with replays.fence_store(target['server_uuid']) as store:assert store.read()['replay_fence']['job_id']==record['job_id']
    jobs.close();replays.close()


def test_selected_and_metadata_members_share_native_recovery_fences_and_partial_claims_unwind(tmp_path):
    jobs,replays,endpoint,target,planned=setup(tmp_path)
    record=jobs.load(planned['job_id'],1,endpoint)
    member_uuid=str(uuid.uuid4());metadata_uuid=str(uuid.uuid4())
    record['source_state']={'members':{'2':{'identity':{'server_uuid':member_uuid}}},
        'seed':{'metadata':{'instance_uuids':[metadata_uuid]}}}
    reference={'server_id':2,'endpoint_id':endpoint,'job_id':str(uuid.uuid4()),'artifact_digest':'owned','summary':{'total_bytes':0}}
    replay=replays.review(1,endpoint,{}, {'identity':{'server_uuid':member_uuid},'state':{'input_reference':reference}},
        'config',{'execution_host':{'kind':'application-host'}})
    foreign=replays.load(replay['job_id'],1,endpoint);replays.claim_fence(foreign)
    with pytest.raises(native.BinlogArchiveError):jobs.claim_fence(record)
    for native_uuid in (target['server_uuid'],metadata_uuid):
        with replays.fence_store(native_uuid) as store:assert not store.read().get('replay_fence')
    replays.release_fence(foreign);jobs.claim_fence(record)
    for native_uuid in (target['server_uuid'],member_uuid,metadata_uuid):
        with replays.fence_store(native_uuid) as store:assert store.read()['replay_fence']['job_id']==record['job_id']
    jobs.release_fence(record)
    for native_uuid in (target['server_uuid'],member_uuid,metadata_uuid):
        with replays.fence_store(native_uuid) as store:assert not store.read().get('replay_fence')
    jobs.close();replays.close()


def test_native_topology_clone_recovery_protects_known_sources_and_registration_aliases_until_explicit_retirement(tmp_path):
    jobs,replays,endpoint,target,planned=setup(tmp_path)
    record=jobs.load(planned['job_id'],1,endpoint);record['source']['version']='9.7.0'
    member_endpoint=str(uuid.uuid4());member_uuid=str(uuid.uuid4())
    record['source_state']={'members':{'2':{'endpoint_id':member_endpoint,
        'identity':{'server_uuid':member_uuid,'version':'9.7.0'}}},
        'seed':{'metadata':{'instance_uuids':[member_uuid]}}}
    record['execution_host']={'kind':'application-host'}
    registry=Registry(tmp_path/'holds');tickets=registry.begin_topology(record)
    assert len(tickets)==3
    assert [t.backup_id for t in registry.begin_topology(record)]==[t.backup_id for t in tickets]
    alias=str(uuid.uuid4())
    for native_uuid in (target['server_uuid'],member_uuid):
        archive={'operation':'mysql_binary_log_archive','source':{'server_uuid':native_uuid}}
        assert Registry.protected(archive,registry.protections(1,alias))
    for ticket in tickets:
        review=registry.review_retire(1,ticket.sink.endpoint,ticket.backup_id)
        registry.retire(1,ticket.sink.endpoint,{key:review[key] for key in ('review_id','review_digest')}|{'confirmed':True})
    assert not registry.protections(1,alias)
    with pytest.raises(native.BinlogArchiveError):registry.begin_topology(record)
    jobs.close();replays.close()


def test_native_inspection_does_not_claim_or_release_an_uncertain_recovery_target(tmp_path):
    jobs,replays,endpoint,target,planned=setup(tmp_path,'cluster.status','[{}]')
    reference={'server_id':1,'endpoint_id':endpoint,'job_id':str(uuid.uuid4()),'artifact_digest':'owned','summary':{'total_bytes':0}}
    replay=replays.review(1,endpoint,{}, {'identity':target,'state':{'input_reference':reference}},'config',{'execution_host':{'kind':'application-host'}})
    replay_record=replays.load(replay['job_id'],1,endpoint);replays.claim_fence(replay_record)
    replays.update(replay_record,state='unknown',native_load_outcome='unknown',native_process_termination_confirmed=False)
    record=jobs.load(planned['job_id'],1,endpoint)
    def execute(_record,_directory,_cancel,_progress,boundary):
        boundary();return {'control':{'native_load_invoked':True,'native_load_returned':True,'stage':'returned','native_error':None},
            'tool':{'return_code':0,'process_observation':{'cleanup_confirmed':True}}}
    jobs.start({'job_id':planned['job_id'],'review_digest':planned['review_digest'],'confirmed':True},1,endpoint,
        {key:record[key] for key in ('source','configuration','program')},SimpleNamespace(execute=execute,close=lambda:None))
    deadline=time.monotonic()+5
    while True:
        with jobs._maps_lock:known=jobs.workers.get(record['job_id'])
        if not known or not known[0].is_alive():break
        assert time.monotonic()<deadline;time.sleep(.01)
    assert jobs.get(planned['job_id'],1,endpoint)['state']=='operation_returned'
    assert jobs.get(planned['job_id'],1,endpoint)['remote_database_mutation'] is False
    with replays.fence_store(target['server_uuid']) as store:assert store.read()['replay_fence']['job_id']==replay['job_id']
    jobs.close();replays.close()


def test_topology_retains_its_original_utility_reference_without_replay_archive_inputs(tmp_path,monkeypatch):
    from pgadmin.cdeadmin.sdk import durable_tool
    jobs,replays,endpoint,target,planned=setup(tmp_path,'cluster.list_routers','[]')
    record=jobs.load(planned['job_id'],1,endpoint)
    assert 'input_reference' not in record['source_state']
    reference={'name':'mysql-topology','nonce':'original','request_sha256':'signed','host':{'hostname':'owned'}}
    jobs.progress(record,{'durable_tool':reference})
    record=jobs.load(record['job_id'],1,endpoint);assert record['durable_tool']==reference
    record['program']['executable_sha256']='native-shell'
    observation={'complete':True,'cleanup_confirmed':True,'return_code':0,'native_outcome_inferred':False}
    def observe(directory,saved,fingerprint):
        assert saved==reference and fingerprint=='native-shell'
        return observation
    monkeypatch.setattr(durable_tool,'observe',observe)
    facts=jobs.observe_utility(record)
    assert facts['native_process_termination_confirmed'] and facts['return_code']==0
    assert jobs.load(record['job_id'],1,endpoint)['interrupted_utility_observation']['native_outcome_inferred'] is False
    jobs.close();replays.close()
