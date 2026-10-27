"""Sandbox OS authority, foreign process refusal and durable uncertainty."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import uuid
import threading

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_sandbox as native
from pgadmin.cdeadmin.workspace.mysql_sandbox_service import SandboxJobs


def selected(tmp_path, **changes):
    return native.options({'operation': 'deploy', 'port': 3310, 'sandbox_directory': str(tmp_path), **changes})


@pytest.mark.parametrize('changes', [
    {'port': True}, {'port': 0}, {'operation': 'restart'}, {'operation': []}, {'sandbox_directory': 'relative'},
    {'native_options': {'password': 'private'}}, {'native_options': {'mysqldPath': '/unadmitted/mysqld'}},
    {'native_options': {'sandboxDir': '/other'}}, {'operation': 'stop', 'native_options': {'portx': 33100}},
    {'native_options': {'mysqldOptions': 'one=1'}}, {'native_options': {'portx': True}},
    {'timeout_seconds': 0}, {'timeout_seconds': True},
])
def test_native_arguments_do_not_admit_credentials_or_unapproved_execution_paths(tmp_path, changes):
    with pytest.raises(native.BinlogArchiveError): selected(tmp_path, **changes)


def test_native_ordered_options_and_unbounded_runtime_are_retained(tmp_path):
    options = {'portx': 33100, 'allowRootFrom': 'localhost', 'ignoreSslError': False,
               'mysqldOptions': ['max_connections=47', 'max_connections=49']}
    assert selected(tmp_path, native_options=options, timeout_seconds=None)['native_options'] == options


def test_control_paths_reject_symlinks_and_hash_real_bytes(tmp_path):
    original = tmp_path / 'config'; original.write_bytes(b'actual config')
    alias = tmp_path / 'alias'; alias.symlink_to(original)
    with pytest.raises(native.BinlogArchiveError): native.file_identity(alias)
    assert native.file_identity(original)['size'] == '13'
    with pytest.raises(native.BinlogArchiveError): native.file_identity(original, maximum=2)
    child = tmp_path / 'real'; child.mkdir(); link = tmp_path / 'linked'; link.symlink_to(child, target_is_directory=True)
    with pytest.raises(native.BinlogArchiveError): native.directory_identity(link)


@pytest.mark.parametrize('operation', native.METHODS)
def test_foreign_port_or_process_never_admits_a_native_mutation(tmp_path, operation):
    with pytest.raises(native.BinlogArchiveError, match='unconfirmed'):
        native.admit(selected(tmp_path, operation=operation), {'state': {'exists': True,
            'process': {'qualified': False, 'running': True, 'port_listening': True}}})


def test_delete_and_kill_use_the_actual_native_pid_and_port_identity(tmp_path):
    values = {'exists': True, 'controls': {'my.cnf': {'sha256': 'a'}},
              'native_configuration': {'port': '3310', 'pid_file': str(tmp_path / '3310' / '3310.pid')},
              'process': {'qualified': True, 'running': True, 'port_listening': True, 'owns_port': True}}
    with pytest.raises(native.BinlogArchiveError, match='Stop'): native.admit(selected(tmp_path, operation='delete'), {'state': values})
    native.admit(selected(tmp_path, operation='kill'), {'state': values})
    values['native_configuration']['pid_file'] = '/foreign.pid'
    with pytest.raises(native.BinlogArchiveError, match='PID file'): native.admit(selected(tmp_path, operation='kill'), {'state': values})


def review(jobs, tmp_path, *, endpoint=None, directory=None):
    return jobs.review(1, endpoint or str(uuid.uuid4()), selected(directory or tmp_path),
        {'identity': {'host_id': 'native-host', 'sandbox_directory': str(directory or tmp_path), 'port': 3310}, 'state': {}},
        'configuration', {'executable_sha256': 'a'*64, 'execution_host': {'kind': 'application', 'platform': 'linux'}})


def test_host_port_fence_spans_registration_aliases_and_base_directories(tmp_path):
    jobs = SandboxJobs(tmp_path / 'jobs.json', tmp_path / 'jobs')
    first = review(jobs, tmp_path); other = review(jobs, tmp_path, directory=tmp_path / 'another')
    record = jobs.load(first['job_id'], 1, first['endpoint_id']); second = jobs.load(other['job_id'], 1, other['endpoint_id'])
    jobs.fence(record)
    with pytest.raises(native.BinlogArchiveError, match='holds'): jobs.fence(second)
    jobs.fence(second, release=True)
    with pytest.raises(native.BinlogArchiveError): jobs.fence(second)
    jobs.fence(record, release=True); jobs.fence(second)


def test_uncertain_acknowledgement_requires_terminated_utility_and_exact_observation(tmp_path):
    jobs = SandboxJobs(tmp_path / 'jobs.json', tmp_path / 'jobs'); reviewed = review(jobs, tmp_path)
    record = jobs.load(reviewed['job_id'], 1, reviewed['endpoint_id']); jobs.fence(record)
    observation = {'identity': record['source'], 'state': {'process': {'qualified': True}}}
    request = {'observation_digest': native.hashlib.sha256(native.canonical(observation).encode()).hexdigest(), 'sandbox_confirmation': '3310'}
    jobs.update(record, state='unknown', native_may_have_dispatched=True, native_operation_outcome='unknown', reconciliation=observation)
    record = jobs.load(record['job_id'], 1, record['endpoint_id'])
    with pytest.raises(native.BinlogArchiveError, match='termination'): jobs.acknowledge(record, observation, request)
    jobs.update(record, native_process_termination_confirmed=True)
    record = jobs.load(record['job_id'], 1, record['endpoint_id'])
    changed = deepcopy(observation); changed['state']['process']['qualified'] = False
    with pytest.raises(native.BinlogArchiveError): jobs.acknowledge(record, changed, request)
    result = jobs.acknowledge(record, observation, request)
    assert result['native_operation_outcome'] == 'unknown' and result['state'] == 'unknown'
    assert result['target_state_acknowledged_at'] and result['automatic_retry'] is False


def test_inspection_does_not_invent_a_database_uuid_before_deployment(tmp_path, monkeypatch):
    monkeypatch.setattr(native, 'listening', lambda _port: False)
    result = native.observe(object(), selected(tmp_path), tmp_path)
    assert result['state']['exists'] is False and result['state']['process']['qualified']
    assert 'server_uuid' not in json.dumps(result)


def test_short_password_does_not_corrupt_native_control_booleans(tmp_path):
    class Runner:
        def run(self, _grant, arguments, **kwargs):
            assert not kwargs.get('redact_values')
            script = Path(arguments[-1].split('=', 1)[1])
            namespace = {}
            source = script.read_text()
            marker = source.split("print('", 1)[1].split("'", 1)[0]
            return {'return_code': 0, 'stdout': marker+json.dumps({'returned': True, 'native_error': {'message': 'true private'}}), 'stderr': ''}
    result = native.invoke(SimpleNamespace(_tool_runner=Runner()), tmp_path, 'result={}', port=3310,
                           secret=b'{"password":"true"}')
    assert result['control']['returned'] is True
    assert result['control']['native_error']['message'] == '[redacted] private'


def test_proven_unstarted_utility_is_not_an_uncertain_native_dispatch(tmp_path):
    jobs = SandboxJobs(tmp_path / 'jobs.json', tmp_path / 'jobs'); reviewed = review(jobs, tmp_path)
    record = jobs.load(reviewed['job_id'], 1, reviewed['endpoint_id']); jobs.fence(record)
    class Transport:
        def execute(self, _record, _directory, _cancel, _progress, boundary):
            boundary()
            return {'control': None, 'tool': {'process_observation': {'started': False, 'cleanup_confirmed': True}}}
        def close(self): pass
    jobs.run(record, Transport(), threading.Event())
    result = jobs.get(record['job_id'], 1, record['endpoint_id'])
    assert result['state'] == 'not_dispatched' and result['native_operation_outcome'] == 'not_dispatched'
    assert result['native_may_have_dispatched'] is False
