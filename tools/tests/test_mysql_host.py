"""Explicit SSH host authority and durable native diagnostic boundaries."""
import base64
from copy import deepcopy
import hashlib
from pathlib import Path
import shlex
import socket
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_host_transport as transport
from pgadmin.cdeadmin.providers.mysql_family import mysql_host_worker as worker
from pgadmin.cdeadmin.workspace.mysql_host_service import HostJobs


@pytest.fixture
def host(tmp_path, monkeypatch):
    identity = str(uuid.uuid4()); directory = tmp_path / 'native-data'; directory.mkdir()
    (directory / 'auto.cnf').write_text('[auto]\nserver-uuid='+identity+'\n')
    executable = tmp_path / 'mysqld'; executable.write_bytes(b'owned native executable fixture'); executable.chmod(0o700)
    configuration = tmp_path / 'selected.cnf'; configuration.write_text('[mysqld]\n')
    calls = []
    def process(executable, arguments, workspace, timeout, **kwargs):
        calls.append((str(executable), list(arguments)))
        output = b'mysqld Ver 9.7.0 for owned unit fixture\n' if '--version' in arguments else b'configuration accepted\n'
        return {'return_code': 0, 'timed_out': False, 'streams_closed': True,
                'outputs': {'stdout': {'base64': base64.b64encode(output).decode('ascii')}},
                'native_process_termination_observed': True}
    monkeypatch.setattr(worker, 'process', process)
    request = {'schema': 'cdeadmin.mysql-native-host.v1', 'action': 'inspect',
               'binding': {'server_uuid': identity, 'hostname': socket.gethostname(), 'datadir': str(directory)},
               'executable': str(executable), 'configuration_file': str(configuration)}
    review = worker.dispatch(request)
    run = {**request, 'action': 'validate_config', 'workspace': str(tmp_path / 'private-jobs'),
           'job_id': str(uuid.uuid4()), 'reviewed': review, 'timeout_seconds': 60}
    run['input_digest'] = worker.digest(run)
    return SimpleNamespace(request=request, run=run, calls=calls, executable=executable,
                           configuration=configuration, directory=directory)


def test_wrong_database_host_or_uuid_never_executes_the_selected_tool(host):
    for changed in ({'server_uuid': str(uuid.uuid4())}, {'hostname': 'wrong-host'}):
        request = deepcopy(host.request); request['binding'].update(changed)
        with pytest.raises(worker.Refused): worker.dispatch(request)
    assert len(host.calls) == 1


@pytest.mark.parametrize('changed', ['executable', 'configuration'])
def test_changed_reviewed_program_or_configuration_refuses_before_even_the_version_process(host, changed):
    getattr(host, changed).write_bytes(b'changed after explicit native review')
    with pytest.raises(worker.Refused, match='changed after review'): worker.dispatch(host.run)
    assert len(host.calls) == 1
    assert not Path(host.run['workspace']).exists()


def test_host_diagnostic_dispatch_is_fixed_and_duplicate_or_status_requests_never_repeat_it(host):
    result = worker.dispatch(host.run)
    assert host.calls[-1][1] == ['--defaults-file='+str(host.configuration), '--validate-config']
    assert result['state'] == 'native_process_returned' and result['result']['return_code'] == 0
    count = len(host.calls)
    assert worker.dispatch(host.run) == result
    assert worker.dispatch({**host.run, 'action': 'status'}) == result
    assert len(host.calls) == count
    with pytest.raises(worker.Refused): worker.dispatch({**host.run, 'action': 'status', 'input_digest': 'another reviewed job'})


def test_lost_remote_result_write_keeps_dispatch_unknown_and_never_runs_again(host, monkeypatch):
    original = worker.save
    def lost(path, value):
        if value['state'] == 'native_process_returned': raise OSError('Owned lost durable result write')
        original(path, value)
    monkeypatch.setattr(worker, 'save', lost)
    with pytest.raises(OSError): worker.dispatch(host.run)
    count = len(host.calls)
    assert worker.dispatch(host.run)['state'] == 'native_dispatch'
    assert worker.dispatch({**host.run, 'action': 'status'})['state'] == 'native_dispatch'
    assert len(host.calls) == count


def test_missing_remote_receipt_returns_exact_unknown_observation_without_creating_or_replaying(host):
    for existing in (False, True):
        directory = Path(host.run['workspace']) / host.run['job_id']
        if existing: directory.mkdir(parents=True)
        value = worker.dispatch({**host.run, 'action': 'status'})
        assert value == {'state': 'unknown', 'job_id': host.run['job_id'], 'input_digest': host.run['input_digest'],
                         'remote_receipt_available': False, 'automatic_retry': False}
        assert not (directory / 'result.json').exists()
        if existing: assert worker.dispatch(host.run) == value
    assert len(host.calls) == 1


def test_host_jobs_cannot_write_private_receipts_inside_the_active_database(host):
    with pytest.raises(worker.Refused, match='separate from the active data directory'):
        worker.dispatch({**host.run, 'workspace': str(host.directory / 'private-jobs')})
    assert len(host.calls) == 1 and not (host.directory / 'private-jobs').exists()


def test_ssh_host_key_is_checked_before_any_credential_authentication(monkeypatch):
    import paramiko
    expected = paramiko.RSAKey.generate(1024); actual = paramiko.RSAKey.generate(1024)
    connection = Mock(); options = SimpleNamespace(key_types=('rsa-sha2-512', 'rsa-sha2-256', 'ssh-rsa'))
    peer = Mock(); peer.get_security_options.return_value = options; peer.get_remote_server_key.return_value = actual
    monkeypatch.setattr(transport.socket, 'create_connection', Mock(return_value=connection))
    monkeypatch.setattr(paramiko, 'Transport', Mock(return_value=peer))
    route = {'host': 'explicit-host', 'port': 22, 'username': 'host-admin',
             'host_key': expected.get_name()+' '+expected.get_base64(), 'authentication': 'password',
             'platform': 'posix', 'python': 'python3'}
    client = transport.Transport(route, {'password': 'must never be submitted'})
    with pytest.raises(transport.HostError, match='pinned key'): client.connect()
    peer.auth_password.assert_not_called(); peer.auth_publickey.assert_not_called(); peer.close.assert_called_once()
    assert client.credentials == {}


def test_ssh_launch_quotes_the_interpreter_and_sends_source_and_options_only_through_stdin():
    executable = '/selected python;touch wrong'
    assert shlex.split(transport.command('posix', executable)) == ['exec', executable, '-u', '-c', transport.LOADER]
    command = transport.command('windows', "C:\\Native Tools\\python'quoted.exe")
    script = base64.b64decode(command.split()[-1]).decode('utf-16le')
    assert script.startswith("& 'C:\\Native Tools\\python''quoted.exe' -u -c '")
    assert len(command) < 8191 and 'private_key' not in transport.LOADER


def test_native_process_output_is_bounded_while_full_length_and_digest_are_preserved(tmp_path):
    size = worker.MAX_OUTPUT + 128
    result = worker.process(Path(sys.executable), ['-c', 'import sys;sys.stdout.buffer.write(b"x"*'+str(size)+')'], tmp_path, 10)
    output = result['outputs']['stdout']
    assert result['return_code'] == 0 and result['streams_closed'] and result['native_process_termination_observed']
    assert len(base64.b64decode(output['base64'])) == worker.MAX_OUTPUT and output['truncated']
    assert output['total_bytes'] == str(size) and output['sha256'] == hashlib.sha256(b'x'*size).hexdigest()


def test_lost_ssh_reply_preserves_owner_scoped_unknown_receipt_and_never_replays(tmp_path):
    import time
    jobs=HostJobs(tmp_path/'jobs',tmp_path/'receipts');endpoint=str(uuid.uuid4())
    selected={'connection':{'host':'database-ssh','authentication':'password'},'timeout_seconds':60,'executable':'mysqld','configuration_file':None,'workspace':'/private/native-host'}
    captured={'identity':{'server_uuid':str(uuid.uuid4())},'state':{'host_binding':{},'remote_review':{}}}
    program={'execution_host':{'kind':'database-server-ssh-host'}}
    review=jobs.review(1,endpoint,selected,captured,'registration',program)
    request={key:review[key] for key in ('job_id','review_digest')}|{'confirmed':True}
    native=Mock();native.request.side_effect=OSError('Owned lost SSH reply')
    try:
        jobs.start(request,1,endpoint,{'configuration':'registration','source':captured['identity'],'program':program},native)
        deadline=time.monotonic()+5
        while jobs.get(review['job_id'],1,endpoint)['state'] in {'dispatching','active'}:
            if time.monotonic()>deadline:raise TimeoutError('Owned native host job deadline')
            time.sleep(.01)
        assert jobs.get(review['job_id'],1,endpoint)['state']=='unknown'
        assert jobs.start(request,1,endpoint,{},None)['state']=='unknown'
        native.request.assert_called_once();native.close.assert_called_once()
        restarted=HostJobs(jobs.path,jobs.root)
        assert restarted.get(review['job_id'],1,endpoint)['state']=='unknown'
        for owner,scope in ((2,endpoint),(1,str(uuid.uuid4()))):
            with pytest.raises(ValueError):restarted.get(review['job_id'],owner,scope)
        assert 'credentials' not in jobs.load(review['job_id'],1,endpoint)
    finally:assert jobs.close()
