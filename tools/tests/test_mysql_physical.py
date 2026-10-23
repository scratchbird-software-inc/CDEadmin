"""Physical artifact admission, immutable inputs and non-replaying host jobs."""
from copy import deepcopy
import json
from pathlib import Path
import socket
from types import SimpleNamespace
import uuid
from unittest.mock import Mock

import pytest
from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_worker as worker
from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_transport as transport
from pgadmin.cdeadmin.workspace.mysql_physical_service import PhysicalJobs, claim, options
from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError


def artifact(path, prepared=False):
    path.mkdir()
    (path / 'xtrabackup_checkpoints').write_text('backup_type = '+('full-prepared' if prepared else 'full-backuped')+'\nfrom_lsn = 0\nto_lsn = 123\nlast_lsn = 124\n')
    (path / 'xtrabackup_info').write_text('uuid = '+str(uuid.uuid4())+'\nserver_version = 9.7.0\ntool_version = 9.7.1-rc1\npartial = N\nincremental = N\ncompressed = N\nencrypted = N\n')
    (path / 'xtrabackup_binlog_info').write_text('binlog.000001\t123\tnative:1-2\n')
    (path / 'xtrabackup_tablespaces').write_text('{"version":3,"external_tablespaces":[]}')
    (path / 'ibdata1').write_bytes(b'owned native test data')
    return worker.artifact(path, prepared=prepared)


def test_artifact_keeps_exact_bytes_and_refuses_external_paths_symlinks_and_modified_inputs(tmp_path):
    path = tmp_path / 'base'; value = artifact(path)
    assert value['prepared'] is False and value['checkpoint']['to_lsn'] == '123'
    public = worker.public(value); assert 'files' not in public and public['file_count'] == 5
    (path / 'ibdata1').write_bytes(b'changed')
    assert worker.artifact(path)['manifest_sha256'] != value['manifest_sha256']
    (path / 'outside').symlink_to(tmp_path)
    with pytest.raises(worker.Refused, match='symbolic'): worker.artifact(path)
    (path / 'outside').unlink()
    (path / 'xtrabackup_tablespaces').write_text('{"version":3,"external_tablespaces":[{"path":"/live/external"}]}')
    with pytest.raises(worker.Refused, match='External'): worker.artifact(path)


@pytest.mark.parametrize('field,value', [('partial','Y'),('incremental','Y'),('encrypted','Y'),('compressed','Y'),('server_version','9.7.1'),('tool_version','8.4')])
def test_unadmitted_native_artifacts_are_not_relabelled(tmp_path, field, value):
    path = tmp_path / 'base'; artifact(path)
    text = (path / 'xtrabackup_info').read_text(); old = worker.properties(path / 'xtrabackup_info')[field]
    (path / 'xtrabackup_info').write_text(text.replace(field+' = '+old, field+' = '+value))
    with pytest.raises(worker.Refused): worker.artifact(path)


def request(tmp_path):
    data = tmp_path / 'live'; data.mkdir()
    identity = str(uuid.uuid4()); (data / 'auto.cnf').write_text('[auto]\nserver-uuid='+identity+'\n')
    return {'schema':'cdeadmin.mysql-physical.v1','action':'start','phase':'backup',
        'binding':{'server_uuid':identity,'hostname':socket.gethostname(),'datadir':str(data)},
        'workspace':str(tmp_path/'private'),'job_id':str(uuid.uuid4()),'input_digest':'exact-reviewed-input',
        'reviewed':{'native':'same'},'database_credentials':{'user':'owned','password':'private value'}}


def test_exclusive_remote_claim_and_status_never_repeat_a_native_launch(tmp_path, monkeypatch):
    selected = request(tmp_path); spawn = Mock()
    monkeypatch.setattr(worker, 'inspection', lambda _request: selected['reviewed'])
    monkeypatch.setattr(worker.subprocess, 'Popen', spawn)
    assert worker.dispatch(selected, 'owned supervisor source')['state'] == 'admitted'
    assert spawn.call_count == 1
    assert worker.dispatch(selected, 'owned supervisor source')['state'] == 'claimed'
    assert worker.dispatch({**selected,'action':'status'})['state'] == 'claimed'
    assert spawn.call_count == 1
    with pytest.raises(worker.Refused): worker.dispatch({**selected,'action':'status','input_digest':'wrong'})


def test_known_failed_supervisor_launch_removes_delegated_credentials(tmp_path, monkeypatch):
    selected = request(tmp_path)
    monkeypatch.setattr(worker, 'inspection', lambda _request: selected['reviewed'])
    monkeypatch.setattr(worker.subprocess, 'Popen', Mock(side_effect=OSError('owned launch refusal')))
    with pytest.raises(OSError): worker.dispatch(selected, 'owned supervisor source')
    directory = Path(selected['workspace']) / selected['job_id']
    assert worker.read_json(directory/'request.json')['database_credentials'] is None
    result = worker.dispatch({**selected,'action':'status'})
    assert result['state'] == 'not_dispatched' and result['process_termination_confirmed'] and result['credential_cleanup_confirmed']


def test_offline_artifact_observation_does_not_require_the_original_data_directory(tmp_path, monkeypatch):
    selected = request(tmp_path)
    root = Path(selected['workspace']); directory = root/selected['job_id']; directory.mkdir(parents=True, mode=0o700); root.chmod(0o700)
    worker.host.save(directory/'result.json', {'state':'claimed','job_id':selected['job_id'],'input_digest':selected['input_digest']})
    (Path(selected['binding']['datadir'])/'auto.cnf').unlink(); Path(selected['binding']['datadir']).rmdir()
    monkeypatch.setattr(worker.host, 'binding', Mock(side_effect=AssertionError('Live source must not be contacted')))
    assert worker.dispatch({**selected,'action':'status'})['state'] == 'claimed'


def test_workspace_cannot_be_the_live_directory_its_child_or_ancestor(tmp_path):
    selected = request(tmp_path)
    for path in [selected['binding']['datadir'], str(Path(selected['binding']['datadir'])/'child'),str(tmp_path)]:
        with pytest.raises(worker.Refused): worker.root_directory(path, selected['binding'])


def test_option_file_preserves_secret_bytes_without_command_line_passwords(tmp_path):
    selected = {'database_credentials':{'user':'owned','password':'line\nquote"slash\\雪'},'sql_host':'127.0.0.1','sql_port':3306}
    path = worker.client_options(selected,tmp_path)
    assert 'password="line\\nquote\\"slash\\\\雪"' in path.read_text()
    assert path.stat().st_mode & 0o077 == 0


def test_claim_checks_owner_review_expiry_and_single_dispatch(tmp_path):
    jobs = PhysicalJobs(tmp_path/'jobs',tmp_path/'artifacts'); endpoint = str(uuid.uuid4())
    value = jobs.review(1, endpoint, {'phase':'backup'},
        {'identity':{'server_uuid':str(uuid.uuid4())},'state':{'remote_review':{},'host_binding':{}}},'configuration',{'execution_host':{}})
    record = jobs.load(value['job_id'],1,endpoint)
    selected = {'confirmed':True,'review_digest':value['review_digest']}
    with pytest.raises(BinlogArchiveError): claim(jobs, record,2,endpoint,selected)
    with pytest.raises(transport.HostError): claim(jobs, record,1,endpoint,{**selected,'review_digest':'changed'})
    assert claim(jobs,record,1,endpoint,selected) is True
    assert claim(jobs,record,1,endpoint,selected) is False


def test_native_transport_sends_sources_and_invocation_privately_and_has_no_password_in_loader():
    assert 'password' not in transport.LOADER
    assert set(transport.program()) == {'host_sha256','fileio_sha256','services_sha256','physical_sha256','transport_sha256'}
    with pytest.raises(transport.HostError): transport.Transport({'platform':'windows'}, {})


def test_native_return_does_not_accept_files_before_supervisor_publication_and_credential_cleanup(tmp_path):
    jobs = PhysicalJobs(tmp_path/'jobs',tmp_path/'artifacts'); endpoint = str(uuid.uuid4())
    value = jobs.review(1,endpoint,{'phase':'backup'},
        {'identity':{},'state':{'remote_review':{},'host_binding':{}}},'configuration',{'execution_host':{}})
    record = jobs.load(value['job_id'],1,endpoint)
    remote = {'return_code':0,'process_termination_confirmed':True,'artifact':{'manifest_sha256':'verified'}}
    for flags in ({}, {'supervisor_finished':True}, {'credential_cleanup_confirmed':True}):
        jobs.update(record,remote_observation={**remote,**flags})
        assert jobs.get(value['job_id'],1,endpoint)['file_verification_confirmed'] is False
    jobs.update(record,remote_observation={**remote,'supervisor_finished':True,'credential_cleanup_confirmed':True})
    assert jobs.get(value['job_id'],1,endpoint)['file_verification_confirmed'] is True
