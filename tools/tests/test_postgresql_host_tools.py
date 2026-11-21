"""Native host tools on exclusively task-owned PostgreSQL clusters."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import os
import subprocess
import threading
import time
import uuid

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.postgresql.host_tools import HostTools, OPERATIONS, options, grants, identity
from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
from pgadmin.cdeadmin.workspace.postgresql_host_tool_jobs import PostgreSQLHostToolJobs, HostToolTransport
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import digest
from ui_descriptor_roundtrip import engine_operations, operation_draft

BIN = os.environ.get('CDEADMIN_POSTGRESQL_HOST_TOOL_TEST_BIN')


@pytest.fixture
def native(tmp_path):
    if not BIN:
        pytest.skip('Explicit owned native host qualification required')
    path = tmp_path / 'cluster'
    result = subprocess.run([str(Path(BIN) / 'initdb'), '-D', str(path), '--no-data-checksums', '--auth=trust', '--no-locale', '--encoding=UTF8'], capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr.decode()
    endpoint = str(uuid.uuid4())
    filename = tmp_path / 'grants.json'
    filename.write_text(json.dumps(dict(format='scratchrobin.postgresql.host-tools@1', grants=[dict(endpoint_id=endpoint, clusters=[dict(id='owned', path=str(path))], summary_files=[])])))
    tools = HostTools({name: str(Path(BIN) / name) for name in OPERATIONS.values()})
    jobs = PostgreSQLHostToolJobs(tmp_path / 'receipts.json', tmp_path / 'jobs')
    n = SimpleNamespace(path=path, endpoint=endpoint, manifest=filename, tools=tools, jobs=jobs, workspace=jobs.prepare_scope(1, endpoint))
    try:
        yield n
    finally:
        assert jobs.close(10)
        if (path / 'postmaster.pid').exists():
            subprocess.run([str(Path(BIN) / 'pg_ctl'), '-D', str(path), '-m', 'immediate', '-w', 'stop'], check=True, capture_output=True, timeout=20)


def review(n, operation, **values):
    draft = operation_draft(engine_operations('postgresql')[operation + '@server'], values)
    selected = options(operation, draft)
    def refresh():
        grant, sha = grants(str(n.manifest), n.endpoint)
        program = n.tools.identify(OPERATIONS[operation], n.workspace)
        source = n.tools.observe(operation, selected, grant, n.workspace)
        return source, program, digest(dict(manifest_sha256=sha))
    source, program, configuration = refresh()
    record = n.jobs.review(1, n.endpoint, dict(operation=operation, draft=selected), dict(identity=source, state={}), configuration, program)
    return record, refresh


def start(n, record, refresh):
    source, program, configuration = refresh()
    request = dict(job_id=record['job_id'], review_digest=record['review_digest'], confirmed=True)
    n.jobs.start(request, 1, n.endpoint, dict(source=source, program=program, configuration=configuration), HostToolTransport(n.jobs, n.tools, refresh))
    deadline = time.monotonic() + 40
    while True:
        result = n.jobs.get(record['job_id'], 1, n.endpoint)
        with n.jobs._maps_lock:
            worker = n.jobs.workers.get(record['job_id'])
        if not worker and result['state'] not in {'dispatching', 'active', 'cancel_requested'}:
            return result, request
        assert time.monotonic() < deadline, result
        time.sleep(.02)


def test_native_control_data_exact_identity_readonly_and_no_replay(native):
    n = native
    before = identity(n.path / 'global/pg_control', True)
    record, refresh = review(n, 'host_pg_controldata', cluster_id='owned', confirmation='owned')
    result, request = start(n, record, refresh)
    assert result['state'] == 'completed', result
    fields = result['result']['control_fields']
    independent = subprocess.check_output([str(Path(BIN) / 'pg_controldata'), str(n.path)], env={**os.environ, 'LC_ALL': 'C'}, text=True)
    assert fields['Database system identifier'] in independent
    assert fields['Database cluster state'] == 'shut down'
    assert result['native_process_termination_confirmed'] and result['result']['native_success']
    assert identity(n.path / 'global/pg_control', True) == before
    assert n.jobs.start(request, 1, n.endpoint, {}, None)['state'] == 'completed'
    with pytest.raises(ValueError):
        n.jobs.get(record['job_id'], 2, n.endpoint)


def test_native_cluster_replacement_refuses_review(native):
    n = native
    record, refresh = review(n, 'host_pg_controldata', cluster_id='owned', confirmation='owned')
    control = n.path / 'global/pg_control'
    data = control.read_bytes()
    control.unlink();control.write_bytes(data)
    with pytest.raises(ValueError, match='changed'):
        start(n, record, refresh)
    assert n.jobs.load(record['job_id'], 1, n.endpoint)['state'] == 'reviewed'


@pytest.mark.parametrize('values', [dict(cluster_id='owned', confirmation='other'), dict(cluster_id='owned', confirmation='owned', source_sql='CHECKPOINT'), dict(cluster_id='owned', confirmation='owned', timeout_seconds=True)])
def test_control_data_typed_refusals(values):
    with pytest.raises(ContinuityError):
        options('host_pg_controldata', values)


def start_owned_server(n, *, summarize=False):
    import socket
    listener = socket.socket();listener.bind(('127.0.0.1', 0));port = listener.getsockname()[1];listener.close()
    args = '-h 127.0.0.1 -p ' + str(port) + " -c unix_socket_directories=''" + (' -c summarize_wal=on' if summarize else '')
    subprocess.run([str(Path(BIN) / 'pg_ctl'), '-D', str(n.path), '-l', str(n.path.parent / 'server.log'), '-o', args, '-w', 'start'], check=True, capture_output=True, timeout=20)
    return port


def add_native_summaries(n):
    import psycopg
    port = start_owned_server(n, summarize=True)
    try:
        with psycopg.connect(host='127.0.0.1', port=port, user=__import__('getpass').getuser(), dbname='postgres', autocommit=True) as connection:
            connection.execute('CREATE TABLE owned_summary AS SELECT generate_series(1,1000) AS id')
            connection.execute('CHECKPOINT');connection.execute('SELECT pg_switch_wal()')
        deadline = time.monotonic() + 20
        while not list((n.path / 'pg_wal/summaries').glob('*.summary')):
            assert time.monotonic() < deadline, 'Native WAL summarizer produced no summary'
            time.sleep(.1)
    finally:
        subprocess.run([str(Path(BIN) / 'pg_ctl'), '-D', str(n.path), '-m', 'fast', '-w', 'stop'], check=True, capture_output=True, timeout=20)
    paths = sorted((n.path / 'pg_wal/summaries').glob('*.summary'))
    manifest = json.loads(n.manifest.read_text())
    manifest['grants'][0]['summary_files'] = [dict(id='summary_' + str(i), path=str(path)) for i, path in enumerate(paths)]
    n.manifest.write_text(json.dumps(manifest))
    return paths


def test_native_generated_wal_summary_range_individual_and_quiet(native):
    n = native;paths = add_native_summaries(n)
    ids = ['summary_' + str(i) for i in range(len(paths))]
    for values in [dict(individual=False, quiet=False), dict(individual=True, quiet=False), dict(individual=False, quiet=True)]:
        record, refresh = review(n, 'host_pg_walsummary', summary_ids=ids, confirmation='WAL summaries', **values)
        result, request = start(n, record, refresh)
        assert result['state'] == 'completed', result
        output = result['result']['native']['stdout']
        expected = subprocess.check_output([str(Path(BIN) / 'pg_walsummary'), *(['--individual'] if values['individual'] else []), *(['--quiet'] if values['quiet'] else []), *map(str, paths)], text=True)
        assert output == expected
        if values['quiet']:
            assert all(': limit ' in line for line in output.splitlines())
        else:
            assert output
        assert result['result']['summary_input_count'] == len(paths)
        assert n.jobs.start(request, 1, n.endpoint, {}, None)['state'] == 'completed'


def test_native_summary_format_error_and_stale_file_are_distinct(native):
    n = native
    path = n.path.parent / 'bad.summary';path.write_bytes(b'owned invalid native summary')
    manifest = json.loads(n.manifest.read_text());manifest['grants'][0]['summary_files'] = [dict(id='bad', path=str(path))];n.manifest.write_text(json.dumps(manifest))
    record, refresh = review(n, 'host_pg_walsummary', summary_ids=['bad'], confirmation='WAL summaries')
    result, _request = start(n, record, refresh)
    assert result['state'] == 'failed' and not result['result']['native_success'] and result['native_process_termination_confirmed']
    record, refresh = review(n, 'host_pg_walsummary', summary_ids=['bad'], confirmation='WAL summaries')
    path.write_bytes(b'changed native bytes')
    with pytest.raises(ValueError, match='changed'):
        start(n, record, refresh)


def test_native_timer_exact_host_report_and_no_replay(native):
    import socket
    n = native
    record, refresh = review(n, 'host_pg_test_timing', duration_seconds=1, timeout_seconds=10, confirmation=socket.gethostname())
    result, request = start(n, record, refresh)
    assert result['state'] == 'completed', result
    native = result['result']['native']
    assert 'Histogram of timing durations' in native['stdout']
    assert record['program']['execution_host']['hostname'] == socket.gethostname()
    assert result['source']['database_server_timing_attested'] is False
    assert result['result']['sql_session_borrowed'] is False and result['native_process_termination_confirmed']
    assert n.jobs.start(request, 1, n.endpoint, {}, None)['state'] == 'completed'


def test_native_timer_cancellation_does_not_replay(native):
    import socket
    n = native
    record, refresh = review(n, 'host_pg_test_timing', duration_seconds=10, timeout_seconds=20, confirmation=socket.gethostname())
    source, program, configuration = refresh()
    request = dict(job_id=record['job_id'], review_digest=record['review_digest'], confirmed=True)
    n.jobs.start(request, 1, n.endpoint, dict(source=source, program=program, configuration=configuration), HostToolTransport(n.jobs, n.tools, refresh))
    deadline = time.monotonic() + 10
    while not n.jobs.load(record['job_id'], 1, n.endpoint).get('durable_tool'):
        assert time.monotonic() < deadline
        time.sleep(.02)
    n.jobs.cancel(record['job_id'], 1, n.endpoint)
    while True:
        result = n.jobs.get(record['job_id'], 1, n.endpoint)
        with n.jobs._maps_lock:
            worker = n.jobs.workers.get(record['job_id'])
        if not worker:
            break
        assert time.monotonic() < deadline
        time.sleep(.02)
    assert result['state'] in {'cancelled', 'unknown'}
    result = n.jobs.reconcile(record['job_id'], 1, n.endpoint)
    assert result['native_process_termination_confirmed'] and result['host_resource_lease_released']
    assert n.jobs.start(request, 1, n.endpoint, {}, None)['state'] == result['state']


def add_scratch(n):
    path = n.path.parent / 'scratch';path.mkdir()
    manifest = json.loads(n.manifest.read_text());manifest['grants'][0]['benchmark_roots'] = [dict(id='owned_scratch', path=str(path))];n.manifest.write_text(json.dumps(manifest))
    return path


def test_native_fsync_uses_owned_file_and_cleans_scratch(native):
    import socket
    n = native;scratch = add_scratch(n)
    kept = scratch / 'kept';kept.write_bytes(b'original owned neighbor')
    record, refresh = review(n, 'host_pg_test_fsync', scratch_id='owned_scratch', seconds_per_test=1, timeout_seconds=60, confirmation=socket.gethostname())
    result, request = start(n, record, refresh)
    assert result['state'] == 'completed', result
    assert 'Compare file sync methods' in result['result']['native']['stdout']
    assert result['source']['database_server_storage_performance_attested'] is False
    assert result['native_temporary_cleanup_confirmed'] and result['host_resource_lease_released']
    assert list(scratch.iterdir()) == [kept] and kept.read_bytes() == b'original owned neighbor'
    assert n.jobs.start(request, 1, n.endpoint, {}, None)['state'] == 'completed'


def test_native_fsync_cancellation_preserves_neighbor_and_retired_review(native):
    import socket
    n = native;scratch = add_scratch(n)
    record, refresh = review(n, 'host_pg_test_fsync', scratch_id='owned_scratch', seconds_per_test=10, timeout_seconds=60, confirmation=socket.gethostname())
    source, program, configuration = refresh()
    request = dict(job_id=record['job_id'], review_digest=record['review_digest'], confirmed=True)
    n.jobs.start(request, 1, n.endpoint, dict(source=source, program=program, configuration=configuration), HostToolTransport(n.jobs, n.tools, refresh))
    deadline = time.monotonic() + 15
    while not n.jobs.load(record['job_id'], 1, n.endpoint).get('durable_tool'):
        assert time.monotonic() < deadline
        time.sleep(.02)
    n.jobs.cancel(record['job_id'], 1, n.endpoint)
    while True:
        with n.jobs._maps_lock:
            worker = n.jobs.workers.get(record['job_id'])
        if not worker:
            break
        assert time.monotonic() < deadline
        time.sleep(.02)
    result = n.jobs.reconcile(record['job_id'], 1, n.endpoint)
    assert result['state'] in {'cancelled', 'unknown'} and result['native_process_termination_confirmed']
    assert result['native_temporary_cleanup_confirmed'] and result['host_resource_lease_released']
    assert not list(scratch.iterdir())
    assert n.jobs.start(request, 1, n.endpoint, {}, None)['state'] == result['state']


def checksum_review(n, mode, **values):
    return review(n, 'host_pg_checksums', cluster_id='owned', confirmation='owned', mode=mode,
                  offline_quiescence_confirmed=True, checksum_change_confirmed=mode != 'CHECK', **values)


def test_native_checksum_enable_check_filenode_disable_and_independent_reopen(native):
    import psycopg
    n = native
    before = n.tools.invoke('pg_controldata', n.workspace, [str(n.path)])['stdout']
    assert 'Data page checksum version:           0' in before
    for mode in ['ENABLE', 'CHECK']:
        result, _ = start(n, *checksum_review(n, mode))
        assert result['state'] == 'completed', result
        assert result['result']['checksum_control_readback']['fields']['Data page checksum version'] == '1'
        assert result['native_process_termination_confirmed'] and result['host_resource_lease_released']
    result, _ = start(n, *checksum_review(n, 'CHECK', filenode='0'))
    assert result['state'] == 'completed' and result['result']['filenode_existence_attested'] is False
    port = start_owned_server(n)
    try:
        with psycopg.connect(host='127.0.0.1', port=port, user=__import__('getpass').getuser(), dbname='postgres', autocommit=True) as connection:
            assert connection.execute('SHOW data_checksums').fetchone() == ('on',)
            connection.execute('CREATE TABLE checksum_owned(id BIGINT PRIMARY KEY,body TEXT)')
            connection.execute("INSERT INTO checksum_owned VALUES(9007199254740993,'native 雪')")
    finally:
        subprocess.run([str(Path(BIN) / 'pg_ctl'), '-D', str(n.path), '-m', 'fast', '-w', 'stop'], check=True, capture_output=True, timeout=20)
    result, _ = start(n, *checksum_review(n, 'DISABLE'))
    assert result['state'] == 'completed' and result['result']['checksum_control_readback']['fields']['Data page checksum version'] == '0'
    port = start_owned_server(n)
    with psycopg.connect(host='127.0.0.1', port=port, user=__import__('getpass').getuser(), dbname='postgres', autocommit=True) as connection:
        assert connection.execute('SHOW data_checksums').fetchone() == ('off',)
        assert connection.execute('SELECT * FROM checksum_owned').fetchall() == [(9007199254740993, 'native 雪')]


def test_native_checksum_active_and_stale_cluster_refusals(native):
    n = native
    start_owned_server(n)
    with pytest.raises(ContinuityError, match='stopped cluster'):
        checksum_review(n, 'ENABLE')
    subprocess.run([str(Path(BIN) / 'pg_ctl'), '-D', str(n.path), '-m', 'fast', '-w', 'stop'], check=True, capture_output=True, timeout=20)
    record, refresh = checksum_review(n, 'ENABLE')
    path = next((n.path / 'base').rglob('pg_filenode.map'))
    info = path.stat();os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1))
    with pytest.raises(ValueError, match='changed'):
        start(n, record, refresh)
    assert n.jobs.load(record['job_id'], 1, n.endpoint)['state'] == 'reviewed'


def test_native_checksum_lost_ack_remains_unknown_and_leased_until_reconcile(native, monkeypatch):
    n = native;record, refresh = checksum_review(n, 'ENABLE')
    original = n.tools.invoke
    def lost(name, workspace, arguments, *args, **kwargs):
        result = original(name, workspace, arguments, *args, **kwargs)
        if name == 'pg_checksums' and '--enable' in arguments:
            assert result['return_code'] == 0
            raise OSError('owned post-native acknowledgement loss')
        return result
    monkeypatch.setattr(n.tools, 'invoke', lost)
    result, request = start(n, record, refresh)
    assert result['state'] == 'unknown' and not result['host_resource_lease_released']
    assert n.jobs.start(request, 1, n.endpoint, {}, None)['state'] == 'unknown'
    monkeypatch.setattr(n.tools, 'invoke', original)
    result = n.jobs.reconcile(record['job_id'], 1, n.endpoint)
    assert result['state'] == 'unknown' and result['host_resource_lease_released'] and result['native_process_termination_confirmed']
    assert 'Data page checksum version:           1' in original('pg_controldata', n.workspace, [str(n.path)])['stdout']


@pytest.mark.parametrize('values', [dict(mode='ENABLE', checksum_change_confirmed=False),dict(offline_quiescence_confirmed=False),dict(mode='ENABLE', sync=False, unsafe_no_sync_confirmed=False),dict(mode='DISABLE', filenode='1'),dict(filenode='2147483648'),dict(filenode='1;DROP DATABASE x')])
def test_checksum_typed_authority_and_native_option_refusals(values):
    selected = dict(cluster_id='owned', confirmation='owned', mode='CHECK', offline_quiescence_confirmed=True, checksum_change_confirmed=True)
    selected.update(values)
    with pytest.raises(ContinuityError):
        options('host_pg_checksums', selected)


def test_host_tool_contract_requires_host_authority_and_native_registration():
    from pgadmin.cdeadmin.workspace.postgresql_host_tool_service import action
    with pytest.raises(ContinuityError, match='Administrator'):
        action(None, None, dict(stage='describe'), host_authorized=False)
    wrong = SimpleNamespace(endpoint_profile=SimpleNamespace(provider_id='org.cdeadmin.sqlite'))
    with pytest.raises(ContinuityError, match='PostgreSQL registration'):
        action(None, wrong, dict(stage='describe'), host_authorized=True)


def test_host_tool_contract_is_exactly_the_native_typed_inventory():
    from pgadmin.cdeadmin.workspace.postgresql_host_tool_service import descriptors
    rows = descriptors()
    assert {row['operation_id'] for row in rows} == set(OPERATIONS)
    assert len(rows) == 13
    for row in rows:
        assert all(field['control'] in {'text','number','boolean','select','grid'} for field in row['fields'])
        assert row['resource_kind'] == 'server' and row['status'] == 'draft'


def test_checksum_tablespace_grant_and_independent_native_values(native):
    import psycopg
    n = native;space = n.path.parent / 'tablespace';space.mkdir()
    port = start_owned_server(n)
    try:
        with psycopg.connect(host='127.0.0.1', port=port, user=__import__('getpass').getuser(), dbname='postgres', autocommit=True) as connection:
            from psycopg import sql
            connection.execute(sql.SQL('CREATE TABLESPACE owned_space LOCATION {}').format(sql.Literal(str(space))))
            connection.execute('CREATE TABLE owned_external(id BIGINT PRIMARY KEY) TABLESPACE owned_space')
            connection.execute('INSERT INTO owned_external VALUES(9007199254740993)')
            oid = str(connection.execute("SELECT oid FROM pg_tablespace WHERE spcname='owned_space'").fetchone()[0])
    finally:
        subprocess.run([str(Path(BIN) / 'pg_ctl'), '-D', str(n.path), '-m', 'fast', '-w', 'stop'], check=True, capture_output=True, timeout=20)
    with pytest.raises(ContinuityError, match='tablespace requires'):
        checksum_review(n, 'ENABLE')
    manifest = json.loads(n.manifest.read_text());manifest['grants'][0]['clusters'][0]['tablespaces'] = [dict(oid=oid, path=str(space))];n.manifest.write_text(json.dumps(manifest))
    result, _ = start(n, *checksum_review(n, 'ENABLE', sync_method='syncfs'))
    assert result['state'] == 'completed', result
    assert result['source']['checksum_tree']['tablespaces'][0]['oid'] == oid
    result, _ = start(n, *checksum_review(n, 'CHECK'))
    assert result['state'] == 'completed'
    port = start_owned_server(n)
    with psycopg.connect(host='127.0.0.1', port=port, user=__import__('getpass').getuser(), dbname='postgres', autocommit=True) as connection:
        assert connection.execute('SELECT * FROM owned_external').fetchall() == [(9007199254740993,)]


def test_checksum_ungranted_links_and_shared_files_are_refused(native):
    n = native
    outside = n.path.parent / 'protected';outside.write_bytes(b'owned protected bytes')
    link = n.path / 'base' / 'unexpected_link';link.symlink_to(outside)
    with pytest.raises(ContinuityError, match='symbolic link'):
        checksum_review(n, 'ENABLE')
    link.unlink()
    shared = n.path.parent / 'shared_control';os.link(n.path / 'global/pg_control', shared)
    with pytest.raises(ContinuityError, match='unshared'):
        checksum_review(n, 'ENABLE')
    assert outside.read_bytes() == b'owned protected bytes'


def test_native_checksum_corruption_is_failed_check_not_success(native):
    n = native
    result, _ = start(n, *checksum_review(n, 'ENABLE'))
    assert result['state'] == 'completed'
    control_before = identity(n.path / 'global/pg_control', True)
    data = next(path for path in (n.path / 'base').rglob('*') if path.is_file() and path.name.isdecimal() and path.stat().st_size >= 16384)
    with data.open('r+b') as stream:
        stream.seek(8292);old = stream.read(1);stream.seek(8292);stream.write(bytes([old[0] ^ 1]));stream.flush();os.fsync(stream.fileno())
    result, _ = start(n, *checksum_review(n, 'CHECK', filenode=data.name))
    assert result['state'] == 'failed' and not result['result']['native_success']
    assert result['native_process_termination_confirmed'] and result['host_resource_lease_released']
    assert not result['result']['cluster_mutation_requested']
    independent = subprocess.run([str(Path(BIN) / 'pg_checksums'), '-D', str(n.path), '--check', '--filenode=' + data.name], capture_output=True)
    assert independent.returncode == 1 and b'checksum' in independent.stderr
    assert identity(n.path / 'global/pg_control', True) == control_before


def test_native_checksum_explicit_no_sync_verbose_and_no_progress(native):
    n = native
    result, _ = start(n, *checksum_review(n, 'ENABLE', sync=False, unsafe_no_sync_confirmed=True, verbose=True, progress=False))
    assert result['state'] == 'completed', result
    assert result['result']['native_success'] and result['result']['verification_complete']
    assert result['result']['checksum_control_readback']['fields']['Data page checksum version'] == '1'
    assert result['options']['draft']['sync'] is False


def test_positive_host_task_describe_is_fixed_backend_dispatch():
    from pgadmin.cdeadmin.workspace.postgresql_host_tool_service import action
    from pgadmin.cdeadmin.providers.postgresql.provider import PROVIDER_ID
    endpoint = SimpleNamespace(id=str(uuid.uuid4()), provider_id=PROVIDER_ID, provider_version=None,
        **{name:str(uuid.uuid4()) for name in ('pool_namespace','session_namespace','cache_namespace','diagnostic_namespace')})
    server = SimpleNamespace(endpoint_profile=endpoint, user_id=1)
    service = SimpleNamespace(endpoint_service=SimpleNamespace(provider_registry=SimpleNamespace(admitted_permissions=lambda context: ['backup_admin'])))
    result = action(service, server, dict(stage='describe'), host_authorized=True)
    assert result['workspace_action'] == 'postgresql_host_tools'
    assert {row['operation_id'] for row in result['operations']} == set(OPERATIONS)
    assert result['native_sql_session_required'] is False and not result['automatic_retry']
