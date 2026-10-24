"""Native unit association, offline provenance and no-replay service receipts."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_host_services as services
from pgadmin.cdeadmin.providers.mysql_family import mysql_host_worker as worker
from pgadmin.cdeadmin.workspace import mysql_host_service as workspace
from test_mysql_host import host


@pytest.fixture
def systemd(tmp_path, monkeypatch):
    monkeypatch.setattr(services.sys, 'platform', 'linux')
    executable = tmp_path / 'mysqld'; executable.write_bytes(b'owned native fixture')
    unit = tmp_path / 'mysql.service'; unit.write_text('[Service]\n')
    pidfile = tmp_path / 'mysql.pid'; pidfile.write_text('12345\n')
    directory = tmp_path / 'proc/12345'; directory.mkdir(parents=True)
    (directory / 'exe').symlink_to(executable)
    (directory / 'cgroup').write_text('0::/system.slice/mysql.service\n')
    (directory / 'stat').write_text('12345 (mysql (worker)) S ' + ' '.join(str(i) for i in range(1, 30)))
    boot = tmp_path / 'proc/sys/kernel/random'; boot.mkdir(parents=True); (boot / 'boot_id').write_text('owned-boot-id')
    original = Path
    monkeypatch.setattr(services, 'Path', lambda value: original(tmp_path / str(value).lstrip('/')) if str(value) == '/proc' or str(value).startswith('/proc/') else original(value))
    monkeypatch.setattr(services.shutil, 'which', lambda name: '/usr/bin/' + name)
    values = {'Id': 'mysql.service', 'Names': ['mysql.service', 'mysqld.service'], 'LoadState': 'loaded',
        'ActiveState': 'active', 'SubState': 'running', 'FragmentPath': str(unit), 'DropInPaths': [],
        'InvocationID': [1, 2, 3],'UnitFileState':'enabled', 'MainPID': 12344, 'ControlGroup': '/system.slice/mysql.service',
        'ExecStart': [['/native/mysqld', ['mysqld', '--private-key-password=must-not-leak'], False, 1, 2, 3]], 'ExecStop': []}
    def run(program, arguments, directory, timeout):
        data = ['/org/freedesktop/systemd1/unit/mysql_2eservice'] if 'LoadUnit' in arguments else values[arguments[-1]]
        return {'return_code': 0, 'outputs': {'stdout': {'base64': base64.b64encode(json.dumps({'data': data}).encode()).decode()}}}
    request = {'service': {'manager': 'systemd', 'name': 'mysqld.service'}, 'native_pid_file': str(pidfile)}
    checksum = lambda path: hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else 'owned-manager'
    observed = {'program': {'path': str(executable), 'sha256': checksum(executable)}}
    return request, observed, run, checksum, values, directory, unit


def inspect(fixture):
    request, observed, run, checksum, *_ = fixture
    return services.inspect(request, observed, run, checksum, worker.regular_stream, worker.Refused)


def test_native_mysql_must_belong_to_selected_unit_even_when_wrapper_is_main_pid(systemd):
    result = inspect(systemd)
    assert result['service_binding_verified'] and result['native_process']['pid'] == 12345
    assert result['manager_main_pid'] == 12344
    assert result['source_association'] == 'current_native_process'
    assert 'must-not-leak' not in json.dumps(result)
    assert result['native_process']['unit_control_group_verified'] and not result['database_readiness_observed']
    (systemd[5] / 'cgroup').write_text('0::/system.slice/another.service\n')
    with pytest.raises(worker.Refused, match='another service'): inspect(systemd)


def test_stopped_service_requires_prior_verified_association(systemd):
    known = inspect(systemd); systemd[4].update(ActiveState='inactive', SubState='dead', MainPID=0, ControlGroup='')
    with pytest.raises(worker.Refused, match='prior verified'): inspect(systemd)
    systemd[0]['previous_service_binding'] = known
    result = inspect(systemd)
    assert result['source_association'] == 'last_observed_native_process' and result['native_process'] is None
    systemd[0]['previous_service_binding'] = {**known, 'selected_service': {'manager': 'systemd', 'name': 'another.service'}}
    with pytest.raises(worker.Refused): inspect(systemd)


def test_service_file_changes_and_native_argv_are_bounded_review_facts(systemd):
    before = inspect(systemd); systemd[6].write_text('[Service]\nchanged-definition\n')
    after = inspect(systemd)
    assert before['definition_files'] != after['definition_files']
    run = Mock(return_value={'return_code': 1})
    assert services.execute('service_stop', after, Path('/owned'), 5, run, worker.Refused)['return_code'] == 1
    assert run.call_args.args[1] == ['--no-ask-password', '--no-pager', '--job-mode=fail', 'stop', '--', 'mysqld.service']


@pytest.mark.parametrize('changed',['file','command'])
def test_offline_original_service_definition_changes_require_a_new_running_instance_binding(systemd,changed):
    known=inspect(systemd);systemd[4].update(ActiveState='inactive',SubState='dead',MainPID=0,ControlGroup='')
    systemd[0]['previous_service_binding']=known
    if changed=='file':systemd[6].write_text('[Service]\nExecStart=/another/service\n')
    else:systemd[4]['ExecStart'][0][1].append('--changed-native-argument')
    with pytest.raises(worker.Refused,match='offline MySQL service definition changed'):inspect(systemd)


@pytest.mark.parametrize('operation', ['service_stop', 'service_restart'])
def test_service_disconnect_requires_explicit_native_consent(operation):
    base = {'connection': {'host': 'owned', 'port': 22, 'username': 'operator', 'host_key': 'key',
        'authentication': 'password', 'platform': 'posix', 'python': 'python3'}, 'executable': 'mysqld',
        'configuration_file': None, 'workspace': '/private', 'timeout_seconds': 60,
        'operation': operation, 'service': {'manager': 'systemd', 'name': 'mysql.service'}}
    for value in (False, 'yes', 1, None):
        with pytest.raises(ValueError, match='disconnection'): workspace.options({**base, 'disconnect_all_clients': value})
    assert workspace.options({**base, 'disconnect_all_clients': True})['operation'] == operation


@pytest.mark.parametrize('kind',[None,'previous_native_initializer'])
def test_offline_capture_is_owner_registration_and_pinned_host_scoped_without_sql(monkeypatch,kind):
    selected = {'binding_job_id': 'old', 'connection': {'host': 'db', 'port': 22, 'host_key': 'pinned', 'platform': 'posix'},
                'service': {'manager': 'systemd', 'name': 'mysql.service'}}
    association = {'service_binding_verified': True, 'selected_service': selected['service']}
    known = {'configuration': 'registration', 'options': selected, 'source': {'server_uuid': 'native'},
             'source_state': {'host_binding': {'server_uuid': 'native'}, 'native_pid_file': '/run/mysql.pid', 'remote_review': {'service': association}}}
    if kind:known['source']['kind']=kind
    jobs = Mock(); jobs.load.return_value = known
    source = Mock(side_effect=AssertionError('Offline service capture must not run SQL')); monkeypatch.setattr(workspace, 'source', source)
    captured = workspace.capture(None, None, jobs, 1, 'endpoint', selected, 'registration')
    assert captured['state']['source_identity_scope'] == ('previous_installed_native_service_association' if kind else 'previous_online_service_association')
    jobs.load.assert_called_once_with('old', 1, 'endpoint'); source.assert_not_called()
    changed = deepcopy(selected); changed['connection']['host_key'] = 'other'
    with pytest.raises(ValueError, match='verified service association'):
        workspace.capture(None, None, jobs, 1, 'endpoint', changed, 'registration')


def test_service_dispatch_and_later_reconciliation_never_repeat_manager_action(host, monkeypatch):
    observation = {'unit': {'Id': 'mysql.service'}, 'selected_service': {'manager': 'systemd', 'name': 'mysql.service'},
                   'service_binding_verified': True}
    monkeypatch.setattr(worker.native_services, 'inspect', Mock(return_value=observation))
    execute = Mock(return_value={'return_code': 0, 'native_process_termination_observed': True})
    monkeypatch.setattr(worker.native_services, 'execute', execute)
    request = {**host.request, 'service': observation['selected_service'], 'native_pid_file': '/run/mysql.pid'}
    reviewed = worker.dispatch(request)
    request = {**host.run, **request, 'action': 'service_stop', 'reviewed': reviewed}
    result = worker.dispatch(request)
    assert result['service_request']['manager_client_completed'] and not result['service_request']['database_readiness_observed']
    assert result['result']['native_process_termination_observed']
    assert result['service_request']['native_process_outcome_scope'] == 'service_manager_client_only'
    again = worker.dispatch(request); assert again == result
    reconciled = worker.dispatch({**request, 'action': 'status'})
    assert reconciled['service_reconciliation']['original_native_result_unchanged']
    assert reconciled['result'] == result['result'] and execute.call_count == 1
