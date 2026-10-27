"""Native system checkpoint identity, coverage and independent differences."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.providers.mysql_family import mysql_system_state as system
from pgadmin.cdeadmin.providers.mysql_family import mysql_instance_dumps as dumps
from pgadmin.cdeadmin.workspace.mysql_instance_backup_jobs import InstanceBackupJobs
from test_mysql_instance_dumps import files,source


def checkpoint(identity):
    return {'format':system.FORMAT,'source_uuid':identity['server_uuid'],'version':'9.7.0',
        'tables':[{'table':'servers','rows':'2','columns_sha256':'a'*64,'definition_sha256':'b'*64,'rows_sha256':'c'*64}]}


def test_native_checkpoint_is_sealed_and_never_reports_missing_file_as_checked(tmp_path):
    identity=source();directory=files(tmp_path/'dump',identity)
    assert 'system_state_checkpoint' not in dumps.verify(directory,identity)
    expected=checkpoint(identity);system.save(directory,expected)
    artifact=dumps.verify(directory,identity)
    assert artifact['system_state_checkpoint']['tables']==['servers']
    assert system.read(directory,identity['server_uuid'])==expected
    expected['source_uuid']=source()['server_uuid']
    (directory/system.FILE).write_text(json.dumps(expected))
    with pytest.raises(system.BinlogArchiveError,match='identity'):dumps.verify(directory,identity)


@pytest.mark.parametrize('fault',['duplicate','unsupported','unsorted','missing','bad-digest','bad-count','extra-secret'])
def test_incomplete_or_unsupported_system_checkpoint_fails_closed(fault):
    value=checkpoint(source());row=value['tables'][0]
    if fault=='duplicate':value['tables'].append(copy.deepcopy(row))
    if fault=='unsupported':row['table']='gtid_executed'
    if fault=='unsorted':value['tables']=[{**row,'table':'user'},row]
    if fault=='missing':value['tables']=[]
    if fault=='bad-digest':row['rows_sha256']='unconfirmed'
    if fault=='bad-count':row['rows']='-1'
    if fault=='extra-secret':row['Password']='must never be serialized'
    with pytest.raises(system.BinlogArchiveError):system.validate(value,value['source_uuid'])


def test_different_target_uuid_is_expected_but_row_definition_and_coverage_changes_fail():
    expected=checkpoint(source());observed=copy.deepcopy(expected);observed['source_uuid']=source()['server_uuid']
    assert system.compare(expected,observed)['matched']
    for field,value in [('rows','3'),('rows_sha256','d'*64),('definition_sha256','d'*64),('columns_sha256','d'*64)]:
        changed=copy.deepcopy(observed);changed['tables'][0][field]=value
        assert system.compare(expected,changed)['matched'] is False
    changed=copy.deepcopy(observed);changed['tables'][0]['table']='user'
    assert system.compare(expected,changed)['matched'] is False


@pytest.mark.parametrize('value',[{'system_state_tables':['servers']},
    {'system_state_tables':['servers'],'system_state_write_pause_confirmed':True,'consistent':False},
    {'system_state_tables':['gtid_executed'],'system_state_write_pause_confirmed':True},
    {'system_state_tables':['servers','servers'],'system_state_write_pause_confirmed':True},
    {'system_state_write_pause_confirmed':True}])
def test_system_checkpoint_requires_exact_scope_and_explicit_write_pause(value):
    with pytest.raises(system.BinlogArchiveError):dumps.options(value,{'host':'owned','tool_workspace':'/owned'})


def test_system_checkpoint_options_are_application_owned_and_not_sent_to_native_dump():
    value=dumps.options({'system_state_tables':['servers','plugin'],'system_state_write_pause_confirmed':True},
        {'host':'owned','tool_workspace':'/owned'})
    assert value['system_state_tables']==['plugin','servers']
    assert not any('system' in name.lower() for name in value['native_options'])


def test_checkpoint_reconciliation_requires_original_requested_coverage(tmp_path):
    import uuid
    jobs=InstanceBackupJobs(tmp_path/'jobs',tmp_path/'files');identity=source();endpoint=str(uuid.uuid4())
    planned=jobs.review(1,endpoint,{'system_state_tables':['servers']},{'identity':identity,'state':{}},'config',{'execution_host':{}})
    record=jobs.load(planned['job_id'],1,endpoint);directory=files(jobs.directory(record)/'archive.incoming',identity)
    jobs.update(record,state='unknown',native_process_termination_confirmed=True)
    jobs.observe_utility=Mock()
    with pytest.raises((OSError,system.BinlogArchiveError)):jobs.reconcile(record['job_id'],1,endpoint)
    assert not (directory.parent/'archive').exists()
    jobs.close()


def test_system_checkpoint_can_be_checked_without_claiming_unexported_data(tmp_path):
    from pgadmin.cdeadmin.providers.mysql_family import mysql_instance_acceptance as acceptance
    (tmp_path/'@.json').write_text(json.dumps({'basenames':{}}))
    selected=acceptance.scopes(tmp_path,{'schemas':[],'users':[],'native_checksums_included':False,'files':[],
        'system_state_checkpoint':{'tables':['servers']}})
    assert selected['system_state_tables']==['servers']
    assert not any(selected[key] for key in ('data_requested','definitions_requested','accounts_requested'))
