"""Instance dump metadata and durable acknowledgement/reconciliation boundaries."""
import hashlib
import json
from pathlib import Path
import re
import socket
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_instance_dumps as native
from pgadmin.cdeadmin.workspace.mysql_instance_backup_jobs import InstanceBackupJobs
from pgadmin.cdeadmin.workspace.mysql_backup_protection import Registry


def source():
    return {'server_uuid':str(uuid.uuid4()),'version':'9.7.0','authenticated_principal':'backup@%','active_role':'NONE'}


def files(path,identity):
    path.mkdir(parents=True)
    for name,value in {
        '@.json':{'version':'2.0.1','origin':'dumpInstance','serverVersion':'9.7.0','schemas':['native'],
            'basenames':{'native':'native'},'consistent':True,'gtidExecutedInconsistent':False,'checksum':True,
            'source':{'sysvars':{'server_uuid':identity['server_uuid']},'binlog':{'file':'native.000001','position':123,'gtidExecuted':identity['server_uuid']+':1-2'}}},
        '@.done.json':{'end':'owned metadata fixture'},
        'native.json':{'schema':'native','tables':[],'views':[],'includesDdl':True,'includesData':True},
    }.items():(path/name).write_text(json.dumps(value))
    return path


def test_instance_options_preserve_native_accounts_and_filters_without_enterprise_policy_execution():
    selected=native.options({'users':True,'include_schemas':['quoted`雪'],'exclude_users':["'backup'@'%'"]},
        {'host':'owned','tool_workspace':'/owned/workspace'})
    assert selected['native_options']['users'] is True
    assert selected['native_options']['includeSchemas']==['quoted`雪']
    assert selected['native_options']['excludeUsers']==["'backup'@'%'"]
    assert selected['native_options']['dataMaskingPolicies'] is False


@pytest.mark.parametrize('value',[{'path':'/unowned'},{'users':'true'},{'include_schemas':['ok',None]},
    {'include_schemas':['\ud800']},{'threads':True},{'timeout_seconds':False},{'unknown_native_option':True},{'dry_run':True}])
def test_invalid_managed_native_options_refuse_before_dispatch(value):
    with pytest.raises(native.BinlogArchiveError):native.options(value,{'host':'owned','tool_workspace':'/owned/workspace'})


def test_byte_metadata_verification_does_not_assert_recovered_data_or_suppress_account_coverage(tmp_path):
    identity=source();path=files(tmp_path/'dump',identity)
    value=native.verify(path,identity)
    assert value['schemas'][0]['schema']=='native' and not value['data_recovery_verified']
    top=json.loads((path/'@.json').read_text());top['users']=["'backup'@'%'"];(path/'@.json').write_text(json.dumps(top))
    with pytest.raises(native.BinlogArchiveError,match='account DDL'):native.verify(path,identity)
    (path/'@.users.sql').write_text('-- owned account fixture')
    assert native.verify(path,identity)['users']==["'backup'@'%'"]


def test_native_acknowledgement_survives_a_later_artifact_failure(tmp_path,monkeypatch):
    identity=source();client=SimpleNamespace(_shell_connection_arguments=lambda _route:[],_tool_runner=Mock())
    def run(_grant,args,**_kwargs):
        script=Path(next(arg.split('=',1)[1] for arg in args if arg.startswith('--file='))).read_text()
        marker=re.search(r'CDEADMIN_MYSQL_INSTANCE_DUMP_[0-9a-f]{32}:',script)[0]
        return {'return_code':0,'executable_sha256':'native','stdout_truncated':False,'stderr':'',
            'process_observation':{'cleanup_confirmed':True},'stdout':marker+json.dumps({'native_dump_invoked':True,'native_dump_returned':True,'stage':'returned','native_error':None})}
    client._tool_runner.run.side_effect=run
    credentials=SimpleNamespace(use=lambda callback:callback(b'{"password":"true"}'))
    monkeypatch.setattr(native,'verify',Mock(side_effect=OSError('owned post-reply artifact loss')))
    with pytest.raises(OSError) as caught:
        native.run_dump(client,{},credentials,identity,{'native_options':{},'timeout_seconds':30},tmp_path/'dump',tmp_path,{'executable_sha256':'native'})
    assert caught.value.native_dump_acknowledged is True
    assert caught.value.observation['process_observation']['cleanup_confirmed'] is True
    assert not list(tmp_path.glob('native-instance-dump-*.js'))


@pytest.mark.parametrize('password',['true','line\n"quote雪','p@ss:w/rd'])
def test_native_error_details_are_observable_without_credential_disclosure_or_control_corruption(tmp_path,password):
    from urllib.parse import quote
    identity=source();client=SimpleNamespace(_shell_connection_arguments=lambda _route:[],_tool_runner=Mock())
    def run(_grant,args,**_kwargs):
        script=Path(next(arg.split('=',1)[1] for arg in args if arg.startswith('--file='))).read_text()
        marker=re.search(r'CDEADMIN_MYSQL_INSTANCE_DUMP_[0-9a-f]{32}:',script)[0]
        control={'native_dump_invoked':True,'native_dump_returned':False,'stage':'dumping',
            'native_error':{'code':1227,'sqlstate':'42000','message':'denied '+password+' '+quote(password,safe='')}}
        return {'return_code':1,'executable_sha256':'native','stdout_truncated':False,'stderr':password,
                'process_observation':{'cleanup_confirmed':True},'stdout':marker+json.dumps(control)}
    client._tool_runner.run.side_effect=run
    credentials=SimpleNamespace(use=lambda callback:callback(json.dumps({'password':password}).encode('utf8')))
    with pytest.raises(native.BinlogArchiveError) as caught:
        native.run_dump(client,{},credentials,identity,{'native_options':{},'timeout_seconds':30},tmp_path/'dump',tmp_path,{'executable_sha256':'native'})
    assert caught.value.native_dump_acknowledged is False
    assert caught.value.native_error['code']==1227 and caught.value.native_error['sqlstate']=='42000'
    assert password not in caught.value.native_error['message'] and quote(password,safe='') not in caught.value.native_error['message']
    assert 'stdout' not in caught.value.observation and 'stderr' not in caught.value.observation


def test_explicit_reconciliation_accepts_sealed_files_without_inventing_a_lost_native_reply(tmp_path):
    jobs=InstanceBackupJobs(tmp_path/'jobs',tmp_path/'backups');registry=jobs.backup_protection=Registry(tmp_path/'holds')
    endpoint=str(uuid.uuid4());identity=source()
    reviewed=jobs.review(1,endpoint,{'native_options':{}},{'identity':identity,'state':{}},'configuration',{'execution_host':{'kind':'application-host'}})
    record=jobs.load(reviewed['job_id'],1,endpoint);directory=jobs.directory(record)
    files(directory/'archive.incoming',identity)
    ticket=registry.scoped(1,endpoint).begin(identity,'MySQL instance',str(directory/'archive'),
        {'_instance_scope':True,'_instance_job_id':record['job_id'],'native_options':{}})
    jobs.update(record,state='failed',native_dump_acknowledged=False,native_process_termination_confirmed=True,backup_protection_id=ticket.backup_id)
    result=jobs.reconcile(record['job_id'],1,endpoint)
    assert result['state']=='artifact_verified' and result['native_dump_acknowledged'] is False
    protected=registry.list(1,endpoint)['backups'][0]
    assert protected['native_dump_completion_acknowledged'] is False and protected['native_artifact_completion_observed'] is True
    assert protected['state']=='native_dump_artifact_verified' and protected['native_schemas']==['native']
    assert registry.protected(jobs.load(record['job_id'],1,endpoint),registry.protections(1,endpoint))
    jobs.close()


def test_truncated_control_preserves_confirmed_process_cleanup_without_raw_output(tmp_path):
    client=SimpleNamespace(_shell_connection_arguments=lambda _route:[],_tool_runner=Mock())
    def run(_grant,args,**_kwargs):
        script=Path(next(arg.split('=',1)[1] for arg in args if arg.startswith('--file='))).read_text()
        marker=re.search(r'CDEADMIN_MYSQL_INSTANCE_DUMP_[0-9a-f]{32}:',script)[0]
        return {'return_code':0,'executable_sha256':'native','stdout_truncated':True,'stderr':'private secret',
            'process_observation':{'cleanup_confirmed':True},'stdout':marker+'{"native_dump_returned":'}
    client._tool_runner.run.side_effect=run
    credentials=SimpleNamespace(use=lambda callback:callback(b'{"password":"secret"}'))
    with pytest.raises(native.BinlogArchiveError) as caught:
        native.run_dump(client,{},credentials,source(),{'native_options':{},'timeout_seconds':30},tmp_path/'dump',tmp_path,{'executable_sha256':'native'})
    assert caught.value.native_dump_acknowledged is False
    assert caught.value.observation['process_observation']['cleanup_confirmed'] is True
    assert 'stdout' not in caught.value.observation and 'stderr' not in caught.value.observation


def test_private_script_cleanup_is_host_bound_hash_bound_and_preserves_the_original_reply(tmp_path):
    jobs=InstanceBackupJobs(tmp_path/'jobs',tmp_path/'backups');endpoint=str(uuid.uuid4());identity=source()
    reviewed=jobs.review(1,endpoint,{}, {'identity':identity,'state':{}},'configuration',{'execution_host':{'kind':'application-host'}})
    record=jobs.load(reviewed['job_id'],1,endpoint);name='native-instance-dump-'+uuid.uuid4().hex+'.js';path=jobs.directory(record)/name
    expected=b'private script without actual credentials';path.write_bytes(expected)
    cleanup={'complete':False,'relative_file':name,'sha256':hashlib.sha256(expected).hexdigest(),'execution_hostname':socket.gethostname()}
    jobs.update(record,state='failed',native_dump_acknowledged=False,native_process_termination_confirmed=True,private_script_cleanup=cleanup)
    path.write_text('changed after native execution')
    with pytest.raises(native.BinlogArchiveError,match='changed'):jobs.cleanup_script(record['job_id'],1,endpoint)
    path.write_bytes(expected)
    result=jobs.cleanup_script(record['job_id'],1,endpoint)
    assert not path.exists() and result['native_dump_acknowledged'] is False and result['private_script_cleanup']['complete'] is True
    assert jobs.cleanup_script(record['job_id'],1,endpoint)==result
    jobs.close()


def test_a_completion_receipt_failure_cannot_replace_an_already_returned_native_ack(tmp_path,monkeypatch):
    jobs=InstanceBackupJobs(tmp_path/'jobs',tmp_path/'backups');endpoint=str(uuid.uuid4());identity=source()
    reviewed=jobs.review(1,endpoint,{}, {'identity':identity,'state':{}},'configuration',{'execution_host':{'kind':'application-host'}})
    record=jobs.load(reviewed['job_id'],1,endpoint);original=jobs.update
    def update(value,**fields):
        if fields.get('state')=='completed':raise OSError('owned final receipt failure')
        return original(value,**fields)
    monkeypatch.setattr(jobs,'update',update)
    result={'native_dump_acknowledged':True,'artifact':{'files':[],'total_bytes':0},'tool':{'process_observation':{'cleanup_confirmed':True}}}
    transport=SimpleNamespace(execute=Mock(return_value=result),close=Mock())
    jobs.run(record,transport,threading.Event())
    reply=jobs.get(record['job_id'],1,endpoint)
    assert reply['state']=='native_returned_unverified' and reply['native_dump_acknowledged'] is True
    assert reply['native_process_termination_confirmed'] is True and reply['error_type']=='OSError'
    assert transport.execute.call_count==1
    jobs.close()
