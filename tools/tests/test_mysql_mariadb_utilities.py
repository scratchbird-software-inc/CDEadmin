"""Unit tests for MySQL 9.7.0 (5) and MariaDB 12.2.2 (6) native host utilities."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import threading
import time
from types import SimpleNamespace
import uuid

import pytest
import test_cdeadmin_relational_providers  # noqa: F401

from pgadmin.cdeadmin.providers.mysql_family import (
    mariadb_utilities,
    mysql_utilities,
    utility_host_worker,
)
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MARIADB_ADMINISTRATION,
    MYSQL_ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.security import SecretLease
from pgadmin.cdeadmin.ui_descriptors import UIDescriptorService
from pgadmin.cdeadmin.workspace.mariadb_utility_service import MariaDBUtilityJobManager
from pgadmin.cdeadmin.workspace.mysql_utility_service import MySQLUtilityJobManager

MYSQL_UUID = '11111111-2222-3333-4444-555555555555'
MARIADB_UID = 'A' * 27 + '='


def _mysql_target(server_uuid=MYSQL_UUID):
    return {
        'resource_kind': 'server',
        'resource_id': 'server:MySQL',
        'display_name': 'MySQL',
        'display_path': ['MySQL'],
        'native': {'server_uuid': server_uuid},
    }


def _mariadb_target(server_uid=MARIADB_UID):
    return {
        'resource_kind': 'server',
        'resource_id': 'server:MariaDB',
        'display_name': 'MariaDB',
        'display_path': ['MariaDB'],
        'native': {'server_uid': server_uid},
    }


def _write_executable(path: Path, script_body: str) -> Path:
    path.write_text('#!/bin/sh\n' + script_body + '\n', encoding='utf-8')
    path.chmod(0o755)
    return path


def test_ui_descriptors_declare_all_11_utilities_with_typed_controls_only():
    svc = UIDescriptorService()
    my_bundle = svc.engine('mysql')
    ma_bundle = svc.engine('mariadb')

    my_ops = {op['operation_id']: op for op in my_bundle['operations'] if op['resource_kind'] == 'server'}
    ma_ops = {op['operation_id']: op for op in ma_bundle['operations'] if op['resource_kind'] == 'server'}

    expected_my = {'run_myisamchk', 'run_myisampack', 'run_innochecksum', 'run_ibd2sdi', 'run_mysqlslap'}
    expected_ma = {'run_aria_chk', 'run_aria_pack', 'run_myisamchk', 'run_myisampack', 'run_innochecksum', 'run_mariadb_slap'}

    assert expected_my <= set(my_ops)
    assert expected_ma <= set(ma_ops)

    for op_id in expected_my:
        op = my_ops[op_id]
        assert op['tier'] == 3 and op['execution_host'] is True and op['status'] == 'complete'
        assert all(f['control'] != 'json' for f in op['fields'])
        form_contract = MYSQL_ADMINISTRATION._form('server', op_id)
        assert form_contract['fields']

    for op_id in expected_ma:
        op = ma_ops[op_id]
        assert op['tier'] == 3 and op['execution_host'] is True and op['status'] == 'complete'
        assert all(f['control'] != 'json' for f in op['fields'])
        form_contract = MARIADB_ADMINISTRATION._form('server', op_id)
        assert form_contract['fields']


def test_cross_engine_identity_and_version_banners_fail_closed():
    # MySQL compiler rejects MariaDB target_uid
    with pytest.raises(RelationalClientError):
        mysql_utilities.compile_operation(
            'run_myisamchk',
            {
                'database_name': 'app',
                'table_name': 't1',
                'datadir': '/var/lib/mysql',
                'workspace': '/var/lib/sr-work',
                'confirmation': 'MariaDB',
            },
            _mariadb_target(),
        )
    # MariaDB compiler rejects MySQL target_uuid
    with pytest.raises(RelationalClientError):
        mariadb_utilities.compile_operation(
            'run_aria_chk',
            {
                'database_name': 'app',
                'table_name': 't1',
                'datadir': '/var/lib/mysql',
                'workspace': '/var/lib/sr-work',
                'confirmation': 'MySQL',
            },
            _mysql_target(),
        )
    # Version banner verifier rejects MariaDB binary for MySQL and vice versa
    with pytest.raises(utility_host_worker.UtilityHostError, match='exact MySQL 9.7.0'):
        utility_host_worker.verify_version_banner(
            'myisamchk from 12.2.2-MariaDB, client 2.7', 0, 'mysql', 'myisamchk'
        )
    with pytest.raises(utility_host_worker.UtilityHostError, match='exact 12.2.2-MariaDB'):
        utility_host_worker.verify_version_banner(
            '/usr/bin/myisamchk  Ver 9.7.0 for Linux on x86_64 (MySQL Community Server - GPL)', 0, 'mariadb', 'myisamchk'
        )


@pytest.mark.parametrize('op_id,draft_extra', [
    ('run_myisamchk', {'database_name': 'db', 'table_name': 't', 'mode': 'recover', 'destructive_confirmed': False}),
    ('run_myisamchk', {'database_name': 'db', 'table_name': 't', 'mode': 'sort_index', 'destructive_confirmed': False}),
    ('run_myisampack', {'database_name': 'db', 'table_name': 't', 'dry_run_test': False, 'destructive_confirmed': False}),
    ('run_innochecksum', {'database_name': 'db', 'table_name': 't', 'write_algorithm': 'crc32', 'destructive_confirmed': False}),
    ('run_innochecksum', {'database_name': 'db', 'table_name': 't', 'no_check': True, 'write_algorithm': ''}),
])
def test_mysql_destructive_and_flag_preconditions_refused_at_compile(op_id, draft_extra):
    base = {
        'datadir': '/var/lib/mysql',
        'workspace': '/var/lib/sr-work',
        'confirmation': 'MySQL',
        **draft_extra,
    }
    with pytest.raises(RelationalClientError):
        mysql_utilities.compile_operation(op_id, base, _mysql_target())


@pytest.mark.parametrize('op_id,draft_extra', [
    ('run_aria_chk', {'database_name': 'db', 'table_name': 't', 'mode': 'recover', 'destructive_confirmed': False}),
    ('run_aria_chk', {'database_name': 'db', 'table_name': 't', 'mode': 'zerofill', 'destructive_confirmed': False}),
    ('run_aria_pack', {'database_name': 'db', 'table_name': 't', 'dry_run_test': False, 'destructive_confirmed': False}),
    ('run_myisamchk', {'database_name': 'db', 'table_name': 't', 'mode': 'safe_recover', 'destructive_confirmed': False}),
    ('run_myisampack', {'database_name': 'db', 'table_name': 't', 'dry_run_test': False, 'destructive_confirmed': False}),
    ('run_innochecksum', {'database_name': 'db', 'table_name': 't', 'rewrite_checksum': True, 'destructive_confirmed': False}),
])
def test_mariadb_destructive_preconditions_refused_at_compile(op_id, draft_extra):
    base = {
        'datadir': '/var/lib/mysql',
        'workspace': '/var/lib/sr-work',
        'confirmation': 'MariaDB',
        **draft_extra,
    }
    with pytest.raises(RelationalClientError):
        mariadb_utilities.compile_operation(op_id, base, _mariadb_target())


@pytest.mark.parametrize('bad_draft', [
    {'benchmark_schema': 'mysql', 'isolated_scratch_confirmed': True},
    {'benchmark_schema': 'production_sales', 'isolated_scratch_confirmed': True},
    {'benchmark_schema': 'cdeadmin_slap_ok', 'isolated_scratch_confirmed': False},
    {
        'benchmark_schema': 'cdeadmin_slap_ok',
        'isolated_scratch_confirmed': True,
        'workload_mode': 'explicit_sql',
        'query_sql': 'DROP DATABASE production_sales',
    },
    {
        'benchmark_schema': 'cdeadmin_slap_ok',
        'isolated_scratch_confirmed': True,
        'workload_mode': 'explicit_sql',
        'query_sql': 'SELECT * FROM other_schema.users',
    },
    {
        'benchmark_schema': 'cdeadmin_slap_ok',
        'isolated_scratch_confirmed': True,
        'workload_mode': 'explicit_sql',
        'query_sql': "SELECT 1 INTO OUTFILE '/tmp/leak'",
    },
])
def test_benchmark_isolation_guards_refuse_unsafe_schemas_and_sql(bad_draft):
    base_my = {'workspace': '/var/lib/sr-work', 'confirmation': 'MySQL', **bad_draft}
    with pytest.raises(RelationalClientError):
        mysql_utilities.compile_operation('run_mysqlslap', base_my, _mysql_target())

    base_ma = {'workspace': '/var/lib/sr-work', 'confirmation': 'MariaDB', **bad_draft}
    with pytest.raises(RelationalClientError):
        mariadb_utilities.compile_operation('run_mariadb_slap', base_ma, _mariadb_target())


def test_ssh_credentials_are_redacted_from_public_compiled_plan():
    compiled = mysql_utilities.compile_operation(
        'run_ibd2sdi',
        {
            'execution_host_kind': 'ssh',
            'ssh_host': 'db.internal',
            'ssh_port': 22,
            'ssh_username': 'dbadmin',
            'ssh_host_key': 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB',
            'ssh_auth_mode': 'password',
            'ssh_password': 'TOP_SECRET_SSH_PASSWORD_999',
            'datadir': '/var/lib/mysql',
            'workspace': '/var/lib/sr-work',
            'database_name': 'app',
            'table_name': 'orders',
            'confirmation': 'MySQL',
        },
        _mysql_target(),
    )
    serialized = json.dumps({
        'statements': compiled['statements'],
        'public_draft': compiled['mysql_utility']['public_draft'],
        'host_spec': compiled['mysql_utility']['host_spec'],
    })
    assert 'TOP_SECRET_SSH_PASSWORD_999' not in serialized
    assert compiled['mysql_utility']['public_draft']['ssh_password_redacted'] is True
    mysql_utilities._release_ssh_secrets(compiled['mysql_utility']['ssh_lease_id'])


def test_offline_datadir_check_refuses_active_pidfile_and_open_descriptor_and_symlink_escape(tmp_path):
    session = utility_host_worker.LocalHostSession()
    datadir = tmp_path / 'datadir'
    workspace = tmp_path / 'workspace'
    outside = tmp_path / 'outside'
    (datadir / 'app').mkdir(parents=True)
    workspace.mkdir()
    outside.mkdir()

    myi = datadir / 'app' / 'items.MYI'
    myd = datadir / 'app' / 'items.MYD'
    myi.write_bytes(b'MYI-HEADER')
    myd.write_bytes(b'MYD-ROWS')

    # Symlink escape outside datadir must be refused
    secret_file = outside / 'secret.ibd'
    secret_file.write_bytes(b'SECRET')
    (datadir / 'app' / 'escape.ibd').symlink_to(secret_file)
    with pytest.raises(utility_host_worker.UtilityHostError, match='escapes'):
        session.resolve_contained_file(str(datadir), 'app/escape.ibd')

    # Path traversal refused
    with pytest.raises(utility_host_worker.UtilityHostError):
        session.resolve_contained_file(str(datadir), '../outside/secret.ibd')

    # Active PID file pointing to a live PID (our parent or init/current process) refused!
    pidfile = datadir / 'mysqld.pid'
    pidfile.write_text(f'{os.getppid()}\n', encoding='ascii')
    with pytest.raises(utility_host_worker.UtilityHostError, match='Refused offline utility execution'):
        session.verify_offline_state(str(datadir), [str(myi), str(myd)], 'mysql')
    pidfile.unlink()

    # Open descriptor in another process refused!
    holder_proc = __import__('subprocess').Popen(
        ['python3', '-c', f'import time; f=open({str(myi)!r}, "rb"); time.sleep(10)'],
    )
    try:
        time.sleep(0.15)
        with pytest.raises(utility_host_worker.UtilityHostError, match='Refused offline utility execution'):
            session.verify_offline_state(str(datadir), [str(myi), str(myd)], 'mysql')
    finally:
        holder_proc.terminate()
        holder_proc.wait(timeout=5)

    # Once holder process exits, offline verification passes cleanly!
    ok = session.verify_offline_state(str(datadir), [str(myi), str(myd)], 'mysql')
    assert ok['verified_offline'] is True and ok['holder_pids'] == []


def test_parse_sdi_json_and_slap_output():
    sdi_sample = json.dumps([
        'ibd2sdi',
        {
            'type': 1,
            'id': 367,
            'object': {
                'mysqld_version_id': 90700,
                'dd_version': 90700,
                'sdi_version': 80019,
                'dd_object_type': 'Table',
                'dd_object': {
                    'name': 'orders',
                    'engine': 'InnoDB',
                    'row_format': 2,
                    'columns': [
                        {'name': 'id', 'column_type_utf8': 'bigint', 'is_nullable': False, 'ordinal_position': 1, 'hidden': 1},
                        {'name': 'DB_TRX_ID', 'column_type_utf8': '', 'is_nullable': False, 'ordinal_position': 2, 'hidden': 2},
                    ],
                    'indexes': [{'name': 'PRIMARY'}, {'name': 'idx_orders_created'}],
                },
            },
        },
    ]).encode('utf-8')
    parsed_sdi = mysql_utilities.parse_sdi_json(sdi_sample)
    assert parsed_sdi['record_count'] == 1
    assert parsed_sdi['sdi_version'] == 80019
    tbl = parsed_sdi['objects'][0]
    assert tbl['name'] == 'orders' and tbl['dd_object_type'] == 'Table'
    assert [c['name'] for c in tbl['columns']] == ['id']
    assert tbl['indexes'] == ['PRIMARY', 'idx_orders_created']

    slap_sample = """Benchmark
\tRunning for engine innodb
\tAverage number of seconds to run all queries: 0.042 seconds
\tMinimum number of seconds to run all queries: 0.038 seconds
\tMaximum number of seconds to run all queries: 0.049 seconds
\tNumber of clients running queries: 4
\tAverage number of queries per client: 25
"""
    metrics = mysql_utilities.parse_slap_output(slap_sample)
    assert metrics['run_count'] == 1
    assert metrics['storage_engine'] == 'innodb'
    assert metrics['average_seconds'] == pytest.approx(0.042)
    assert metrics['minimum_seconds'] == pytest.approx(0.038)
    assert metrics['maximum_seconds'] == pytest.approx(0.049)
    assert metrics['clients_per_run'] == 4
    assert metrics['queries_per_client'] == 25


def test_supervised_benchmark_job_cancellation_and_secret_file_redaction(tmp_path):
    workspace = tmp_path / 'ws'
    workspace.mkdir()
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    argv_dump = tmp_path / 'argv_observed.txt'

    # Mock mariadb-slap 12.2.2 binary that logs its argv (verifying no password in argv!)
    # and sleeps until cancelled so we verify real mid-flight cancellation & cleanup.
    slap_bin = _write_executable(
        bindir / 'mariadb-slap',
        f'''
if [ "$1" = "--version" ]; then
  echo "mariadb-slap from 12.2.2-MariaDB, client 1.0 for debian-linux-gnu (x86_64)"
  exit 0
fi
printf '%s\\n' "$@" > "{argv_dump}"
case "$1" in
  --defaults-extra-file=*)
    f="${{1#--defaults-extra-file=}}"
    [ -f "$f" ] || exit 91
    perm=$(stat -c '%a' "$f")
    [ "$perm" = "600" ] || exit 92
    ;;
  *) exit 90 ;;
esac
sleep 30
''',
    )

    class _FakeCursor:
        def __init__(self):
            self.queries = []
            self._last = None

        def execute(self, sql, params=()):
            self.queries.append((sql, params))
            if 'SELECT VERSION()' in sql:
                self._last = ('12.2.2-MariaDB', MARIADB_UID, 3306, None, 'root@localhost')
            elif 'COUNT(*)' in sql:
                self._last = (0,)

        def fetchone(self):
            return self._last

        def close(self):
            pass

    class _FakeConn:
        autocommit = True

        def __init__(self):
            self.cur = _FakeCursor()

        def cursor(self):
            return self.cur

        def close(self):
            pass

    secret_password = 'SUPER_SECRET_BENCH_PASS_777'
    dropped_schemas = []

    class _FakeClient:
        def __init__(self):
            self.config = SimpleNamespace(
                secret_acquirer=lambda ref, principal, purpose, kind: SecretLease(secret_password.encode('utf-8'))
            )

        def _connect(self, req):
            conn = _FakeConn()
            orig_exec = conn.cur.execute
            def _track(sql, params=()):
                if sql.startswith('DROP DATABASE IF EXISTS'):
                    dropped_schemas.append(sql)
                return orig_exec(sql, params)
            conn.cur.execute = _track
            return conn

        def _forget_connection(self, handle):
            handle.close()

        def plan_admin_operation(self, req):
            planned = MARIADB_ADMINISTRATION.plan(req)
            return mariadb_utilities.bind_review(self, planned)

    client = _FakeClient()
    route = {
        'host': '127.0.0.1',
        'port': 3306,
        'user': 'root',
        'principal_reference': 'user:1',
        'credential_reference_id': 'cred-1',
    }
    mgr = MariaDBUtilityJobManager(str(tmp_path / 'ma-jobs.json'))
    reviewed = mgr.review(
        owner=1,
        endpoint_id='ep-ma-1',
        client=client,
        route=route,
        request={
            'operation_id': 'run_mariadb_slap',
            'target_resource': _mariadb_target(),
            'draft': {
                'execution_host_kind': 'local',
                'executable_path': str(slap_bin),
                'workspace': str(workspace),
                'benchmark_schema': 'cdeadmin_slap_cancel_test',
                'concurrency': '2',
                'iterations': 5,
                'isolated_scratch_confirmed': True,
                'timeout_seconds': 60,
                'confirmation': 'MariaDB',
            },
        },
    )
    assert secret_password not in json.dumps(reviewed)
    started = mgr.start(
        owner=1,
        endpoint_id='ep-ma-1',
        client=client,
        request={
            'job_id': reviewed['job_id'],
            'review_digest': reviewed['review_digest'],
            'confirmed': True,
            'async_execution': True,
        },
    )
    assert started['state'] in {'active', 'completed'}
    for _ in range(40):
        if argv_dump.exists():
            break
        time.sleep(0.05)
    assert argv_dump.exists()
    argv_text = argv_dump.read_text(encoding='utf-8')
    assert secret_password not in argv_text
    assert '--defaults-extra-file=' in argv_text.splitlines()[0]

    cancelled = mgr.cancel(1, 'ep-ma-1', reviewed['job_id'])
    assert cancelled['state'] == 'cancelled'
    assert cancelled['cleanup_confirmed'] is True
    assert any('cdeadmin_slap_cancel_test' in s for s in dropped_schemas)
    # Secret defaults file must be completely wiped and unlinked!
    assert list(workspace.rglob('*.cnf')) == []


def test_offline_mysql_utilities_local_roundtrip_and_backup_staging(tmp_path):
    datadir = tmp_path / 'mysql_data'
    workspace = tmp_path / 'mysql_ws'
    bindir = tmp_path / 'mysql_bin'
    (datadir / 'app').mkdir(parents=True)
    workspace.mkdir()
    bindir.mkdir()

    # Write auto.cnf matching target UUID
    (datadir / 'auto.cnf').write_text(f'[auto]\nserver-uuid={MYSQL_UUID}\n', encoding='utf-8')
    myi = datadir / 'app' / 'items.MYI'
    myd = datadir / 'app' / 'items.MYD'
    ibd = datadir / 'app' / 'orders.ibd'
    myi.write_bytes(b'MYI-INITIAL-INDEX')
    myd.write_bytes(b'MYD-UNCOMPRESSED-DATA-' * 20)
    ibd.write_bytes(b'IBD-CLEAN-PAGES' * 64)

    myisamchk_bin = _write_executable(
        bindir / 'myisamchk',
        '''
if [ "$1" = "--version" ]; then
  echo "/usr/bin/myisamchk  Ver 9.7.0 for Linux on x86_64 (MySQL Community Server - GPL)"
  exit 0
fi
for last; do :; done
myi="${last%.MYI}.MYI"
case "$*" in
  *--recover*|*-rq*)
    printf 'REBUILT' >> "$myi"
    echo "myisamchk: recovering $myi"
    exit 0
    ;;
esac
echo "Checking MyISAM file: $last"
exit 0
''',
    )
    myisampack_bin = _write_executable(
        bindir / 'myisampack',
        '''
if [ "$1" = "--version" ]; then
  echo "/usr/bin/myisampack  Ver 9.7.0 for Linux on x86_64 (MySQL Community Server - GPL)"
  exit 0
fi
for last; do :; done
myd="${last%.MYI}.MYD"
case "$*" in
  *--test*)
    echo "Compressing $myd: (100 records) -> 55.0%"
    exit 0
    ;;
esac
printf 'PACKED-DATA' > "$myd"
echo "Compressed $myd"
exit 0
''',
    )
    innochecksum_bin = _write_executable(
        bindir / 'innochecksum',
        '''
if [ "$1" = "--version" ]; then
  echo "/usr/bin/innochecksum  Ver 9.7.0 for Linux on x86_64 (MySQL Community Server - GPL)"
  exit 0
fi
log_out=""
count_mode=0
write_mode=0
for arg in "$@"; do
  case "$arg" in
    --count) count_mode=1 ;;
    --write=*) write_mode=1 ;;
    --log=*) log_out="${arg#--log=}" ;;
  esac
done
for last; do :; done
[ -n "$log_out" ] && printf 'page::0; log sequence number:first = 1\n' > "$log_out"
if [ "$count_mode" = "1" ]; then
  echo "Number of pages:7"
  exit 0
fi
if grep -q "CORRUPT" "$last" 2>/dev/null && [ "$write_mode" = "0" ]; then
  echo "Fail: page 1 invalid" >&2
  exit 1
fi
if [ "$write_mode" = "1" ]; then
  printf 'IBD-REWRITTEN-CLEAN' > "$last"
fi
exit 0
''',
    )
    ibd2sdi_bin = _write_executable(
        bindir / 'ibd2sdi',
        '''
if [ "$1" = "--version" ]; then
  echo "/usr/bin/ibd2sdi  Ver 9.7.0 for Linux on x86_64 (MySQL Community Server - GPL)"
  exit 0
fi
dump=""
for arg in "$@"; do
  case "$arg" in
    --dump-file=*) dump="${arg#--dump-file=}" ;;
  esac
done
cat > "$dump" <<'JSON'
["ibd2sdi", {"type": 1, "id": 501, "object": {"sdi_version": 80019, "dd_object_type": "Table", "dd_object": {"name": "orders", "engine": "InnoDB", "row_format": 2, "columns": [{"name": "order_id", "column_type_utf8": "bigint", "is_nullable": false, "ordinal_position": 1}], "indexes": [{"name": "PRIMARY"}]}}}]
JSON
exit 0
''',
    )

    class _OfflineClient:
        config = SimpleNamespace(secret_acquirer=None)
        def _connect(self, _req):
            raise OSError('Connection refused (server is offline)')
        def _forget_connection(self, _h):
            pass
        def plan_admin_operation(self, req):
            planned = MYSQL_ADMINISTRATION.plan(req)
            return mysql_utilities.bind_review(self, planned)

    client = _OfflineClient()
    route = {'host': '127.0.0.1', 'port': 1}  # Unbound port

    # 1. myisamchk --recover stages private backup and updates .MYI
    plan_chk = client.plan_admin_operation({
        'resource_kind': 'server',
        'operation_id': 'run_myisamchk',
        'target_resource': _mysql_target(),
        'draft': {
            'execution_host_kind': 'local',
            'executable_path': str(myisamchk_bin),
            'datadir': str(datadir),
            'workspace': str(workspace),
            'database_name': 'app',
            'table_name': 'items',
            'mode': 'recover',
            'backup': True,
            'destructive_confirmed': True,
            'confirmation': 'MySQL',
        },
        '_provider_route': route,
    })
    res_chk = MYSQL_ADMINISTRATION.apply(client, plan_chk)['mysql_utility']
    assert res_chk['repaired'] is True
    assert res_chk['backup_artifact']['files']['myi']['sha256'] == res_chk['before_files']['myi']['sha256']
    assert res_chk['after_files']['myi']['sha256'] != res_chk['before_files']['myi']['sha256']

    # 2. myisampack compresses .MYD and invokes companion myisamchk -rq
    plan_pack = client.plan_admin_operation({
        'resource_kind': 'server',
        'operation_id': 'run_myisampack',
        'target_resource': _mysql_target(),
        'draft': {
            'execution_host_kind': 'local',
            'executable_path': str(myisampack_bin),
            'datadir': str(datadir),
            'workspace': str(workspace),
            'database_name': 'app',
            'table_name': 'items',
            'dry_run_test': False,
            'rebuild_indexes': True,
            'destructive_confirmed': True,
            'confirmation': 'MySQL',
        },
        '_provider_route': route,
    })
    res_pack = MYSQL_ADMINISTRATION.apply(client, plan_pack)['mysql_utility']
    assert res_pack['index_rebuild_executed'] is True
    assert res_pack['after_myd_bytes'] < res_pack['before_myd_bytes']

    # 3. innochecksum --count, corrupt detection, and --write=crc32
    plan_cnt = client.plan_admin_operation({
        'resource_kind': 'server',
        'operation_id': 'run_innochecksum',
        'target_resource': _mysql_target(),
        'draft': {
            'execution_host_kind': 'local',
            'executable_path': str(innochecksum_bin),
            'datadir': str(datadir),
            'workspace': str(workspace),
            'database_name': 'app',
            'table_name': 'orders',
            'count_only': True,
            'confirmation': 'MySQL',
        },
        '_provider_route': route,
    })
    assert MYSQL_ADMINISTRATION.apply(client, plan_cnt)['mysql_utility']['page_count'] == 7

    staged_corrupt = workspace / 'corrupt_orders.ibd'
    staged_corrupt.write_bytes(b'CORRUPT-PAGE-1')
    plan_corrupt = client.plan_admin_operation({
        'resource_kind': 'server',
        'operation_id': 'run_innochecksum',
        'target_resource': _mysql_target(),
        'draft': {
            'execution_host_kind': 'local',
            'executable_path': str(innochecksum_bin),
            'datadir': str(datadir),
            'workspace': str(workspace),
            'tablespace_scope': 'workspace_staged',
            'tablespace_relpath': 'corrupt_orders.ibd',
            'strict_check': 'crc32',
            'confirmation': 'MySQL',
        },
        '_provider_route': route,
    })
    res_corrupt = MYSQL_ADMINISTRATION.apply(client, plan_corrupt)['mysql_utility']
    assert res_corrupt['corruption_detected'] is True and res_corrupt['checksum_valid'] is False

    # 4. ibd2sdi extracts structured SDI metadata and records private artifact sha256
    plan_sdi = client.plan_admin_operation({
        'resource_kind': 'server',
        'operation_id': 'run_ibd2sdi',
        'target_resource': _mysql_target(),
        'draft': {
            'execution_host_kind': 'local',
            'executable_path': str(ibd2sdi_bin),
            'datadir': str(datadir),
            'workspace': str(workspace),
            'database_name': 'app',
            'table_name': 'orders',
            'strict_check': 'crc32',
            'confirmation': 'MySQL',
        },
        '_provider_route': route,
    })
    res_sdi = MYSQL_ADMINISTRATION.apply(client, plan_sdi)['mysql_utility']
    assert res_sdi['sdi_metadata']['objects'][0]['name'] == 'orders'
    assert len(res_sdi['artifact']['sha256']) == 64


def test_offline_mariadb_utilities_local_roundtrip_and_backup_staging(tmp_path):
    datadir = tmp_path / 'mariadb_data'
    workspace = tmp_path / 'mariadb_ws'
    bindir = tmp_path / 'mariadb_bin'
    (datadir / 'app').mkdir(parents=True)
    workspace.mkdir()
    bindir.mkdir()

    (datadir / 'aria_log_control').write_bytes(b'ARIA-CTL')
    mai = datadir / 'app' / 'ledger.MAI'
    mad = datadir / 'app' / 'ledger.MAD'
    ibd = datadir / 'app' / 'events.ibd'
    mai.write_bytes(b'MAI-INITIAL-INDEX')
    mad.write_bytes(b'MAD-UNCOMPRESSED-DATA-' * 20)
    ibd.write_bytes(b'IBD-MARIADB-PAGES' * 32)

    aria_chk_bin = _write_executable(
        bindir / 'aria_chk',
        '''
if [ "$1" = "--version" ]; then
  echo "/usr/bin/aria_chk  Ver 1.3 for Linux (x86_64) from 12.2.2-MariaDB"
  exit 0
fi
for last; do :; done
case "$*" in
  *--recover*|*-rq*|*--zerofill*)
    printf 'ARIA-REBUILT' >> "$last"
    echo "aria_chk: recovering $last"
    exit 0
    ;;
esac
echo "Checking Aria file: $last"
exit 0
''',
    )
    aria_pack_bin = _write_executable(
        bindir / 'aria_pack',
        '''
if [ "$1" = "--version" ]; then
  echo "/usr/bin/aria_pack  Ver 1.0 for Linux (x86_64) from 12.2.2-MariaDB"
  exit 0
fi
for last; do :; done
mad="${last%.MAI}.MAD"
case "$*" in
  *--test*)
    echo "Compressing $mad: (80 records) -> 48.0%"
    exit 0
    ;;
esac
printf 'PACKED-ARIA' > "$mad"
echo "Compressed $mad"
exit 0
''',
    )
    innochecksum_bin = _write_executable(
        bindir / 'innochecksum',
        '''
if [ "$1" = "--version" ]; then
  echo "/usr/bin/innochecksum  Ver 12.2.2-MariaDB for debian-linux-gnu (x86_64)"
  exit 0
fi
for arg in "$@"; do
  if [ "$arg" = "--count" ]; then
    echo "Number of pages:5"
    exit 0
  fi
done
exit 0
''',
    )

    class _OfflineMariaDBClient:
        config = SimpleNamespace(secret_acquirer=None)
        def _connect(self, _req):
            raise OSError('Connection refused (mariadbd is offline)')
        def _forget_connection(self, _h):
            pass
        def plan_admin_operation(self, req):
            planned = MARIADB_ADMINISTRATION.plan(req)
            return mariadb_utilities.bind_review(self, planned)

    client = _OfflineMariaDBClient()
    route = {'host': '127.0.0.1', 'port': 1}

    plan_aria_chk = client.plan_admin_operation({
        'resource_kind': 'server',
        'operation_id': 'run_aria_chk',
        'target_resource': _mariadb_target(),
        'draft': {
            'execution_host_kind': 'local',
            'executable_path': str(aria_chk_bin),
            'datadir': str(datadir),
            'workspace': str(workspace),
            'database_name': 'app',
            'table_name': 'ledger',
            'mode': 'zerofill',
            'backup': True,
            'destructive_confirmed': True,
            'confirmation': 'MariaDB',
        },
        '_provider_route': route,
    })
    res_aria_chk = MARIADB_ADMINISTRATION.apply(client, plan_aria_chk)['mariadb_utility']
    assert res_aria_chk['repaired'] is True
    assert res_aria_chk['backup_artifact']['files']['mai']['sha256'] == res_aria_chk['before_files']['mai']['sha256']

    plan_aria_pack = client.plan_admin_operation({
        'resource_kind': 'server',
        'operation_id': 'run_aria_pack',
        'target_resource': _mariadb_target(),
        'draft': {
            'execution_host_kind': 'local',
            'executable_path': str(aria_pack_bin),
            'datadir': str(datadir),
            'workspace': str(workspace),
            'database_name': 'app',
            'table_name': 'ledger',
            'dry_run_test': False,
            'rebuild_indexes': True,
            'destructive_confirmed': True,
            'confirmation': 'MariaDB',
        },
        '_provider_route': route,
    })
    res_aria_pack = MARIADB_ADMINISTRATION.apply(client, plan_aria_pack)['mariadb_utility']
    assert res_aria_pack['index_rebuild_executed'] is True
    assert res_aria_pack['after_mad_bytes'] < res_aria_pack['before_mad_bytes']

    plan_inno = client.plan_admin_operation({
        'resource_kind': 'server',
        'operation_id': 'run_innochecksum',
        'target_resource': _mariadb_target(),
        'draft': {
            'execution_host_kind': 'local',
            'executable_path': str(innochecksum_bin),
            'datadir': str(datadir),
            'workspace': str(workspace),
            'database_name': 'app',
            'table_name': 'events',
            'count_only': True,
            'confirmation': 'MariaDB',
        },
        '_provider_route': route,
    })
    res_inno = MARIADB_ADMINISTRATION.apply(client, plan_inno)['mariadb_utility']
    assert res_inno['page_count'] == 5

