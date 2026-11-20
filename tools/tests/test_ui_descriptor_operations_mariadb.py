"""MariaDB tier 2/3 operations round-trip through the OperationDialog's draft
(field defaults + values) -> MARIADB_ADMINISTRATION validate/plan/apply -> effect
observed on a live MariaDB 10.11 server.

Set ``CDEADMIN_ROUNDTRIP_MARIADB`` to ``{"host", "port", "user", "password"}`` for
an account that may create databases and accounts. Skipped otherwise.
"""
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_MARIADB')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_MARIADB is not set', allow_module_level=True)
mariadb = pytest.importorskip('mariadb')

from pgadmin.cdeadmin.providers.mysql_family.provider import (  # noqa: E402
    MARIADB_ADMINISTRATION as ADMINISTRATION, MARIADB_PROFILE, _create_client, _resources,
)
from pgadmin.cdeadmin.security.secrets import SecretLease  # noqa: E402
from ui_descriptor_roundtrip import engine_operations, operation_draft  # noqa: E402

SETTINGS = json.loads(SETTINGS)
OPERATIONS = engine_operations('mariadb')
UNIQUE = uuid.uuid4().hex[:6]
DATABASE = f'ui_ops_{UNIQUE}'


def admin(database=None, settings=None):
    settings = settings or SETTINGS
    return mariadb.connect(host=settings['host'], port=int(settings['port']), user=settings['user'],
                           password=settings['password'], autocommit=True, **({'database': database} if database else {}))


def query(sql, database=None, settings=None):
    connection = admin(database, settings)
    try:
        cursor = connection.cursor()
        cursor.execute(sql)
        return cursor.fetchall() if cursor.description else []
    finally:
        connection.close()


def execute(*statements, database=None):
    connection = admin(database)
    try:
        for statement in statements:
            connection.cursor().execute(statement)
    finally:
        connection.close()


@pytest.fixture(scope='module')
def live(tmp_path_factory):
    workspace = tmp_path_factory.mktemp('mariadb_ops')
    execute(f'CREATE DATABASE `{DATABASE}`')
    execute('CREATE TABLE owner(id INT PRIMARY KEY, label VARCHAR(40))',
            "INSERT INTO owner VALUES (1, 'a'), (2, 'b')", 'CREATE VIEW owner_view AS SELECT id FROM owner',
            'CREATE TABLE legacy(id INT) ENGINE=MyISAM', 'INSERT INTO legacy VALUES (1), (2)', database=DATABASE)
    execute('CREATE TABLE parted(id INT NOT NULL, label VARCHAR(20)) PARTITION BY RANGE (id) ('
            'PARTITION p0 VALUES LESS THAN (10), PARTITION p1 VALUES LESS THAN (20))',
            "INSERT INTO parted VALUES (1, 'x'), (11, 'y')", database=DATABASE)
    route = {'host': SETTINGS['host'], 'port': int(SETTINGS['port']), 'database': DATABASE, 'user': SETTINGS['user'],
             'credential_reference_id': 'ui-ops', 'principal_reference': 'ui-ops',
             'tool_workspace': str(workspace), 'tool_timeout': 120}
    client = _create_client(MARIADB_PROFILE, SimpleNamespace(acquire_secret=lambda *_args: SecretLease(SETTINGS['password'])),
                            SimpleNamespace(pool_namespace=f'ui-ops-{UNIQUE}'))
    try:
        yield route, client, workspace
    finally:
        client.close()
        execute(f'DROP DATABASE IF EXISTS `{DATABASE}`', f'DROP DATABASE IF EXISTS `{DATABASE}_x`',
                f'DROP ROLE IF EXISTS rt_ops_{UNIQUE}')


def resources(client, route):
    connection = client._connect({'route': dict(route)})
    try:
        return list(_resources(connection, {'route': route}, MARIADB_PROFILE))
    finally:
        client._forget_and_close(connection)


def find(client, route, kind, name=None):
    rows = [row for row in resources(client, route) if row['resource_kind'] == kind]
    if name is not None:
        rows = [row for row in rows if row['display_name'] == name]
    assert rows, (kind, name)
    return rows[0]


def run(live, kind, operation_id, values=None, name=None, target=None, confirmation=None, session_id=None, connection=None):
    route, client, _workspace = live
    operation = OPERATIONS[f'{operation_id}@{kind}']
    target = find(client, route, kind, name) if target is None else (target or None)  # False: the operation has no target
    # The dialog asks the user to type the target's display name for typed-name confirmations.
    draft = operation_draft(operation, values, confirmation=confirmation or (target or {}).get('display_name'))
    request = {'resource_kind': kind, 'operation_id': operation_id, 'target_resource': target,
               '_provider_route': route, 'draft': draft,
               **({'session_id': session_id} if session_id else {})}
    assert ADMINISTRATION.validate(request)['errors'] == [], (operation_id, ADMINISTRATION.validate(request))
    planned = client.plan_admin_operation(request)
    apply_req = dict(planned)
    if connection is not None:
        apply_req['_provider_session_handle'] = connection
        if session_id:
            apply_req['session_id'] = session_id
    result = client.apply_admin_operation(apply_req)
    assert result['accepted'], (operation_id, result)
    return planned, result


def names(*values):
    """Rows of a string-list grid exactly as the dialog's grid control emits them."""
    return [{'value': value} for value in values]


def rows_of(result):
    return [tuple(row) for item in result['statement_results'] for row in item['rows']]


def test_table_maintenance_operations(live):
    planned, result = run(live, 'database', 'analyze_tables', {
        'tables': names('owner'), 'persistent_for': 'ALL', 'binlog_mode': 'NO_WRITE_TO_BINLOG'}, name=DATABASE)
    assert planned['command_preview']['statements'][0]['source'] == (
        f'ANALYZE NO_WRITE_TO_BINLOG TABLE `{DATABASE}`.`owner` PERSISTENT FOR ALL')
    assert rows_of(result)[-1][3] == 'OK'
    # Engine-independent statistics were collected: the observable effect of PERSISTENT FOR ALL.
    assert query(f"SELECT count(*) FROM mysql.table_stats WHERE db_name='{DATABASE}' AND table_name='owner'") == [(1,)]
    assert query(f"SELECT count(*) FROM mysql.column_stats WHERE db_name='{DATABASE}' AND table_name='owner'") == [(2,)]
    run(live, 'database', 'analyze_tables', {
        'tables': names('owner'), 'persistent_for': 'SPECIFIED', 'persistent_columns': names('label'),
        'persistent_indexes': names('PRIMARY')}, name=DATABASE)

    planned, result = run(live, 'database', 'check_objects', {
        'objects': names('owner', 'parted'), 'check_options': ['QUICK']}, name=DATABASE)
    assert [row[2:] for row in rows_of(result)] == [('status', 'OK'), ('status', 'OK')]
    planned, result = run(live, 'database', 'check_objects', {
        'object_type': 'VIEW', 'objects': names('owner_view'), 'check_options': ['FOR UPGRADE']}, name=DATABASE)
    assert planned['command_preview']['statements'][0]['source'] == f'CHECK VIEW `{DATABASE}`.`owner_view` FOR UPGRADE'
    assert rows_of(result)[-1][3] == 'OK'

    planned, result = run(live, 'database', 'optimize_tables', {
        'tables': names('owner'), 'lock_wait_mode': 'WAIT', 'lock_wait_seconds': 5}, name=DATABASE)
    assert planned['command_preview']['statements'][0]['source'].endswith('WAIT 5')
    assert rows_of(result)[-1][3] == 'OK'

    planned, result = run(live, 'database', 'repair_objects', {
        'objects': names('legacy'), 'repair_options': ['QUICK']}, name=DATABASE)
    assert planned['command_preview']['statements'][0]['source'] == f'REPAIR TABLE `{DATABASE}`.`legacy` QUICK'
    assert rows_of(result)[-1][3] == 'OK'

    planned, result = run(live, 'database', 'checksum_tables', {'tables': names('owner'), 'checksum_type': 'EXTENDED'}, name=DATABASE)
    observed = query(f'CHECKSUM TABLE `{DATABASE}`.`owner` EXTENDED')
    assert rows_of(result) == [tuple(row) for row in observed]
    assert rows_of(result)[0][1] != 0


def partitions(table):
    return [row[0] for row in query(
        "SELECT partition_name FROM information_schema.partitions WHERE table_schema=%s AND table_name='%s' "
        "AND partition_name IS NOT NULL ORDER BY partition_ordinal_position" % (f"'{DATABASE}'", table))]


def find_partition(live, table, partition):
    route, client, _workspace = live
    rows = [row for row in resources(client, route) if row['resource_kind'] == 'partition'
            and row['display_path'][-2:] == [table, partition]]
    assert rows, (table, partition)
    return rows[0]


def table_target(live, name):
    route, client, _workspace = live
    return find(client, route, 'table', name)


def test_table_partition_operations(live):
    execute('CREATE TABLE tp_range(id INT NOT NULL) PARTITION BY RANGE (id) (PARTITION p0 VALUES LESS THAN (10))',
            'CREATE TABLE tp_hash(id INT NOT NULL) PARTITION BY HASH (id) PARTITIONS 4',
            'CREATE TABLE tp_plain(id INT NOT NULL)', database=DATABASE)
    run(live, 'table', 'add_partitions', {'mode': 'DEFINITIONS', 'definitions': 'PARTITION p1 VALUES LESS THAN (20), PARTITION p2 VALUES LESS THAN (30)'},
        target=table_target(live, 'tp_range'))
    assert partitions('tp_range') == ['p0', 'p1', 'p2']
    run(live, 'table', 'add_partitions', {'mode': 'COUNT', 'count': 2}, target=table_target(live, 'tp_hash'))
    assert len(partitions('tp_hash')) == 6
    run(live, 'table', 'coalesce_partitions', {'count': 3}, target=table_target(live, 'tp_hash'))
    assert len(partitions('tp_hash')) == 3
    run(live, 'table', 'partition_by', {'partition_clause': 'PARTITION BY HASH (id) PARTITIONS 2'}, target=table_target(live, 'tp_plain'))
    assert len(partitions('tp_plain')) == 2
    run(live, 'table', 'remove_partitioning', target=table_target(live, 'tp_hash'))
    assert partitions('tp_hash') == []


def test_partition_operations(live):
    execute('CREATE TABLE pp_inno(id INT NOT NULL) PARTITION BY RANGE (id) (PARTITION p0 VALUES LESS THAN (10), '
            'PARTITION p1 VALUES LESS THAN (20), PARTITION p2 VALUES LESS THAN (30))',
            'INSERT INTO pp_inno VALUES (1), (11), (21)',
            'CREATE TABLE pp_myisam(id INT NOT NULL) ENGINE=MyISAM PARTITION BY RANGE (id) (PARTITION p0 VALUES LESS THAN (10), '
            'PARTITION p1 VALUES LESS THAN (20))', 'INSERT INTO pp_myisam VALUES (1), (11)', database=DATABASE)
    for operation in ('analyze', 'check', 'optimize'):
        planned, result = run(live, 'partition', operation, target=find_partition(live, 'pp_inno', 'p0'))
        assert planned['command_preview']['statements'][0]['source'] == (
            f'ALTER TABLE `{DATABASE}`.`pp_inno` {operation.upper()} PARTITION `p0`')
        assert rows_of(result)[-1][2] == 'status' and rows_of(result)[-1][3] in ('OK', 'Table is already up to date'), (operation, result)
    planned, result = run(live, 'partition', 'rebuild', target=find_partition(live, 'pp_inno', 'p1'))
    assert query('SELECT count(*) FROM pp_inno', DATABASE) == [(3,)]
    planned, result = run(live, 'partition', 'repair', target=find_partition(live, 'pp_myisam', 'p1'))
    assert planned['command_preview']['statements'][0]['source'] == f'ALTER TABLE `{DATABASE}`.`pp_myisam` REPAIR PARTITION `p1`'
    assert rows_of(result)[-1][3] == 'OK'
    run(live, 'partition', 'reorganize', {'partitions': names('p1', 'p2'), 'definitions': 'PARTITION p12 VALUES LESS THAN (30)'},
        target=find_partition(live, 'pp_inno', 'p1'))
    assert partitions('pp_inno') == ['p0', 'p12']
    assert query('SELECT id FROM pp_inno PARTITION (p12) ORDER BY id', DATABASE) == [(11,), (21,)]


def call_answer():
    connection = admin(DATABASE)
    try:
        cursor = connection.cursor()
        cursor.execute("SET SESSION sql_mode='ORACLE'")
        cursor.execute('SELECT pkg_rt.answer()')
        return cursor.fetchone()[0]
    finally:
        connection.close()


SPECIFICATION = 'AS FUNCTION answer RETURN INT; END;'


def body(value):
    return f'AS FUNCTION answer RETURN INT AS BEGIN RETURN {value}; END; END;'


def test_package_operations(live):
    # Packages are created under ORACLE sql_mode; the dialog selects it with the SQL mode field.
    run(live, 'package', 'create_specification', {'database': DATABASE, 'name': 'pkg_rt', 'sql_mode': 'oracle',
                                                  'definition': SPECIFICATION}, target=False)
    assert query(f"SELECT count(*) FROM information_schema.routines WHERE routine_schema='{DATABASE}' "
                 "AND routine_name='pkg_rt' AND routine_type='PACKAGE'") == [(1,)]
    planned, _result = run(live, 'package', 'create_body', {'sql_mode': 'oracle', 'definition': body(1)}, name='pkg_rt')
    assert planned['command_preview']['statements'][-1]['source'].startswith(f'CREATE PACKAGE BODY `{DATABASE}`.`pkg_rt`')
    assert query(f"SELECT count(*) FROM information_schema.routines WHERE routine_schema='{DATABASE}' "
                 "AND routine_name='pkg_rt' AND routine_type='PACKAGE BODY'") == [(1,)]
    assert call_answer() == 1
    # Replace with the default 'stored' SQL mode: the provider reuses the mode the package was created in.
    planned, _result = run(live, 'package', 'replace_body', {'definition': body(2)}, name='pkg_rt')
    assert planned['command_preview']['statements'][0]['source'] == 'SET SESSION sql_mode=%s'
    assert call_answer() == 2
    # DROP PACKAGE BODY only parses under ORACLE sql_mode, which the dialog selects.
    planned, _result = run(live, 'package', 'drop_body', {'sql_mode': 'oracle'}, name='pkg_rt')
    assert [row['source'] for row in planned['command_preview']['statements']] == [
        'SET SESSION sql_mode=%s', f'DROP PACKAGE BODY `{DATABASE}`.`pkg_rt`']
    assert query(f"SELECT count(*) FROM information_schema.routines WHERE routine_schema='{DATABASE}' "
                 "AND routine_name='pkg_rt' AND routine_type='PACKAGE BODY'") == [(0,)]
    run(live, 'package', 'replace_specification', {
        'definition': 'AS FUNCTION answer RETURN INT; FUNCTION extra RETURN INT; END;'}, name='pkg_rt')
    assert b'extra' in query(f"SELECT body FROM mysql.proc WHERE db='{DATABASE}' AND name='pkg_rt' AND type='PACKAGE'")[0][0]


def replica_status(channel):
    connection = admin()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(f"SHOW SLAVE '{channel}' STATUS")
        return cursor.fetchall()
    except mariadb.OperationalError:
        return []  # reset with delete_connection removed the connection itself
    finally:
        connection.close()


def channel_target(channel):
    # MariaDB 10.11 has no information_schema.SLAVE_STATUS, which the provider's inventory reads
    # (it ships in 12.x), so the channel is absent from the listing here; build the resource the
    # inventory would return for it.
    return {'resource_id': f'replication-channel:{channel}', 'resource_kind': 'replication-channel',
            'display_name': channel, 'display_path': [channel], 'authority_path': ['replication-channel', channel],
            'generation': 'current', 'native': {}}


def test_replication_channel_operations(live):
    channel = f'rt_{UNIQUE}'
    # A dummy primary on a closed port: START launches the threads (the IO thread keeps retrying), no data flows.
    execute(f"CHANGE MASTER '{channel}' TO MASTER_HOST='127.0.0.1', MASTER_PORT=1, MASTER_USER='nobody', "
            "MASTER_PASSWORD='x', MASTER_CONNECT_RETRY=1")
    try:
        assert replica_status(channel)[0]['Slave_IO_Running'] == 'No'
        run(live, 'replication-channel', 'start', {'thread': 'IO_THREAD'}, target=channel_target(channel))
        assert replica_status(channel)[0]['Slave_IO_Running'] in ('Connecting', 'Yes')
        assert replica_status(channel)[0]['Slave_SQL_Running'] == 'No'
        run(live, 'replication-channel', 'start', {'thread': 'SQL_THREAD'}, target=channel_target(channel))
        assert replica_status(channel)[0]['Slave_SQL_Running'] == 'Yes'
        run(live, 'replication-channel', 'stop', {'thread': 'SQL_THREAD'}, target=channel_target(channel))
        assert replica_status(channel)[0]['Slave_SQL_Running'] == 'No'
        run(live, 'replication-channel', 'stop', target=channel_target(channel))
        assert replica_status(channel)[0]['Slave_IO_Running'] == 'No'
        run(live, 'replication-channel', 'reset', {'delete_connection': True}, target=channel_target(channel))
        assert replica_status(channel) == []
    finally:
        if replica_status(channel):
            execute(f"STOP SLAVE '{channel}'", f"RESET SLAVE '{channel}' ALL")


def test_role_set_default(live):
    role, user = f'rt_ops_{UNIQUE}', f'rt_ops_user_{UNIQUE}'
    execute(f'CREATE ROLE {role}', f"CREATE USER '{user}'@'localhost' IDENTIFIED BY 'x'", f"GRANT {role} TO '{user}'@'localhost'")
    try:
        assert query(f"SELECT default_role FROM mysql.user WHERE user='{user}'") == [('',)]
        run(live, 'role', 'set_default', {'member': f'{user}@localhost'}, name=role)
        assert query(f"SELECT default_role FROM mysql.user WHERE user='{user}'") == [(role,)]
    finally:
        execute(f"DROP USER IF EXISTS '{user}'@'localhost'")


def test_set_global_system_variable(live):
    original = query('SELECT @@global.max_connections')[0][0]
    try:
        run(live, 'system-variable', 'set_global', {'value': '222'}, name='MAX_CONNECTIONS')
        assert query('SELECT @@global.max_connections') == [(222,)]
        run(live, 'system-variable', 'set_global', {'value_mode': 'DEFAULT'}, name='MAX_CONNECTIONS')
        assert query('SELECT @@global.max_connections') == [(151,)]  # the compiled default
    finally:
        execute(f'SET GLOBAL max_connections = {original}')


def sleeper():
    """A second connection running a long SLEEP; returns (connection, thread, outcome, connection id)."""
    connection = admin()
    identifier = connection.connection_id
    outcome = {}

    def work():
        try:
            cursor = connection.cursor()
            cursor.execute('SELECT SLEEP(60)')
            outcome['rows'] = cursor.fetchall()
        except Exception as error:  # noqa: BLE001 - the observation is the error itself
            outcome['error'] = error
    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    return connection, thread, outcome, identifier


def wait_for(predicate, seconds=10):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(.1)
    return False


def sleeping_session(live, identifier):
    # The provider's session inventory selects PROCESSLIST columns (SENT_ROWS, TMP_SPACE_USED) that
    # MariaDB 10.11 does not have, so the row is absent from the listing here; build the resource
    # the inventory returns (display name and native id are the process ID).
    assert wait_for(lambda: query(f"SELECT 1 FROM information_schema.processlist WHERE id={identifier} AND info LIKE 'SELECT SLEEP%'"))
    return {'resource_id': f'session:Sessions:{identifier}', 'resource_kind': 'session', 'display_name': str(identifier),
            'display_path': ['Sessions', str(identifier)], 'authority_path': ['Sessions', 'session', str(identifier)],
            'generation': 'current', 'native': {'id': identifier, 'user': SETTINGS['user'], 'command': 'Query'}}


def test_terminate_query_and_connection(live):
    connection, thread, outcome, identifier = sleeper()
    target = sleeping_session(live, identifier)
    # The dialog's typed confirmation is the process ID (the session's display name).
    run(live, 'session', 'terminate_query', {'termination_mode': 'SOFT'}, target=target)
    thread.join(10)
    assert not thread.is_alive()
    # KILL QUERY ends the statement and keeps the connection.
    assert query(f'SELECT count(*) FROM information_schema.processlist WHERE id={identifier}') == [(1,)]
    run(live, 'session', 'terminate_connection', {'termination_mode': 'HARD'}, target=target)
    assert wait_for(lambda: query(f'SELECT count(*) FROM information_schema.processlist WHERE id={identifier}') == [(0,)])


@pytest.fixture
def binlog_live():
    """A server with binary logging on: the main server when it has it, else the one named by
    CDEADMIN_ROUNDTRIP_MARIADB_BINLOG (same JSON shape)."""
    settings = SETTINGS
    if query('SELECT @@global.log_bin')[0][0] != 1:
        extra = os.environ.get('CDEADMIN_ROUNDTRIP_MARIADB_BINLOG')
        if not extra:
            pytest.skip('binary logging is off and CDEADMIN_ROUNDTRIP_MARIADB_BINLOG is not set')
        settings = json.loads(extra)
        assert query('SELECT @@global.log_bin', settings=settings)[0][0] == 1
    route = {'host': settings['host'], 'port': int(settings['port']), 'database': 'mysql', 'user': settings['user'],
             'credential_reference_id': 'ui-ops-binlog', 'principal_reference': 'ui-ops-binlog'}
    client = _create_client(MARIADB_PROFILE, SimpleNamespace(acquire_secret=lambda *_args: SecretLease(settings['password'])),
                            SimpleNamespace(pool_namespace=f'ui-ops-binlog-{UNIQUE}'))
    try:
        yield (route, client, None), settings
    finally:
        client.close()


def binary_logs(settings):
    return [row[0] for row in query('SHOW BINARY LOGS', settings=settings)]


def test_binary_log_rotate_and_purge(binlog_live):
    live, settings = binlog_live
    route, client, _workspace = live
    before = binary_logs(settings)
    # The status row names the current file; rotate closes it and opens the next.
    status = find(client, route, 'binary-log-status')
    run(live, 'binary-log-status', 'rotate', target=status)
    assert len(binary_logs(settings)) == len(before) + 1
    run(live, 'binary-log-status', 'rotate', target=find(client, route, 'binary-log-status'))
    logs = binary_logs(settings)
    assert len(logs) == len(before) + 2
    # purge_before: the typed confirmation is the selected log file's name; earlier files go.
    keep = logs[-2]
    planned, _result = run(live, 'binary-log', 'purge_before', name=keep)
    assert binary_logs(settings) == logs[-2:]  # everything before the selected file was purged
    assert planned['command_preview']['statements'][0]['source'].startswith('PURGE BINARY LOGS TO')


TOOL_SETTINGS = {'mariadb-dump': 'CDEADMIN_MARIADB_DUMP_BINARY', 'mariadb': 'CDEADMIN_MARIADB_CLIENT_BINARY',
                 'mariadb-upgrade': 'CDEADMIN_MARIADB_UPGRADE_BINARY'}


def require_release_tools(*programs):
    """The provider runs only the exact 12.2.2 tool release; skip where the host has another.
    Check the executable the provider will run: its setting, else the name on PATH."""
    for program in programs:
        found = subprocess.run([os.environ.get(TOOL_SETTINGS[program], program), '--version'],
                               capture_output=True, text=True).stdout
        if '12.2.2-MariaDB' not in found:
            pytest.skip(f'{program} is not the 12.2.2-MariaDB release the provider requires: {found.strip()}')


def test_logical_backup_and_restore(live):
    require_release_tools('mariadb-dump', 'mariadb')
    route, client, workspace = live
    # The dialog's path is relative to the endpoint tool workspace (route tool_workspace / tool_timeout).
    planned, result = run(live, 'database', 'backup_logical', {'path': 'dump.sql'}, name=DATABASE)
    dump = workspace / 'dump.sql'
    assert dump.exists() and "CREATE TABLE `owner`" in dump.read_text()
    assert result['driver_observation']['mariadb_dump_completed'] is True
    execute('DROP TABLE owner', database=DATABASE)
    # restore_logical is typed-name confirmed: the dialog sends the database name as ``confirmation``.
    run(live, 'database', 'restore_logical', {'path': 'dump.sql'}, name=DATABASE)
    assert query('SELECT id FROM owner ORDER BY id', DATABASE) == [(1,), (2,)]


def test_check_upgrade_required(live):
    require_release_tools('mariadb-upgrade')
    _planned, result = run(live, 'server', 'check_upgrade_required', name='MariaDB')
    assert result['driver_observation']['upgrade_check_completed'] is True
    assert result['driver_observation']['upgrade_required'] is False


def server_major():
    return int(query('SELECT @@version')[0][0].split('.')[0])


def test_exchange_and_convert_partition_operations(live):
    """These emit ``{WITH|WITHOUT} VALIDATION`` (MariaDB 12.2.2 grammar); a 10.11 server answers
    error 1064 for that clause, so the dialog draft is validated and planned on every server but only
    applied (and observed) on 12.x."""
    route, client, _workspace = live
    execute('CREATE TABLE ex_range(id INT NOT NULL) PARTITION BY RANGE (id) (PARTITION p0 VALUES LESS THAN (10), '
            'PARTITION p1 VALUES LESS THAN (20))', 'INSERT INTO ex_range VALUES (1), (11)',
            'CREATE TABLE ex_swap(id INT NOT NULL)', 'INSERT INTO ex_swap VALUES (12)',
            'CREATE TABLE ex_incoming(id INT NOT NULL)', 'INSERT INTO ex_incoming VALUES (31)', database=DATABASE)
    cases = [('partition', 'exchange', find_partition(live, 'ex_range', 'p1'),
              {'exchange_database': DATABASE, 'exchange_table': 'ex_swap'},
              f'ALTER TABLE `{DATABASE}`.`ex_range` EXCHANGE PARTITION `p1` WITH TABLE `{DATABASE}`.`ex_swap` WITH VALIDATION'),
             ('partition', 'convert_to_table', find_partition(live, 'ex_range', 'p0'),
              {'exchange_database': DATABASE, 'exchange_table': 'ex_detached'},
              f'ALTER TABLE `{DATABASE}`.`ex_range` CONVERT PARTITION `p0` TO TABLE `{DATABASE}`.`ex_detached` WITH VALIDATION'),
             ('table', 'convert_from_table', table_target(live, 'ex_range'),
              {'exchange_database': DATABASE, 'exchange_table': 'ex_incoming', 'definitions': 'PARTITION p3 VALUES LESS THAN (40)'},
              f'ALTER TABLE `{DATABASE}`.`ex_range` CONVERT TABLE `{DATABASE}`.`ex_incoming` TO PARTITION p3 VALUES LESS THAN (40) WITH VALIDATION')]
    for kind, operation_id, target, values, expected in cases:
        operation = OPERATIONS[f'{operation_id}@{kind}']
        request = {'resource_kind': kind, 'operation_id': operation_id, 'target_resource': target, '_provider_route': route,
                   'draft': operation_draft(operation, values)}
        assert ADMINISTRATION.validate(request)['errors'] == [], operation_id
        assert ADMINISTRATION.plan(request)['command_preview']['statements'][0]['source'] == expected
    if server_major() < 12:
        pytest.skip('applying needs the MariaDB 12 {WITH|WITHOUT} VALIDATION grammar (10.11 rejects it with error 1064)')
    for kind, operation_id, target, values, _expected in cases:
        run(live, kind, operation_id, values, target=target)
    assert partitions('ex_range') == ['p1', 'p3']


def test_mariadb_12_extended_descriptor_operations(live):
    route, client, _workspace = live
    server_uid = query('SELECT @@server_uid')[0][0]
    server_target = {
        'resource_id': 'server:MariaDB',
        'resource_kind': 'server',
        'display_name': 'MariaDB',
        'display_path': ['MariaDB'],
        'native': {'server_uid': server_uid},
    }
    run(live, 'server', 'flush', {'targets': ['STATUS'], 'binlog_mode': 'NO_WRITE_TO_BINLOG'}, target=server_target)
    run(live, 'table', 'flush', {'binlog_mode': 'NO_WRITE_TO_BINLOG', 'lock_mode': 'NONE'}, target=table_target(live, 'owner'))
    _pl, ap_res = run(live, 'server', 'inspect_available_plugins', {'status_filter': 'ALL', 'include_test_modules': False}, target=server_target)
    assert ap_res['available_plugins']['active_count'] > 0

    # Sequence signed & unsigned BIGINT bounds
    run(live, 'sequence', 'create', {
        'name': 'seq_u64', 'parent': DATABASE, 'integer_type': 'BIGINT', 'unsigned': True,
        'start': '18446744073709551610', 'minimum_mode': 'VALUE', 'minimum': '18446744073709551600',
        'maximum_mode': 'VALUE', 'maximum': '18446744073709551614', 'cache': '0'}, target=False)
    seq_target = find(client, route, 'sequence', 'seq_u64')
    run(live, 'sequence', 'alter', {'restart': '18446744073709551612'}, target=seq_target)
    assert query('SELECT next_not_cached_value FROM seq_u64', DATABASE) == [(18446744073709551612,)]

    # Index visibility & rename
    execute('CREATE INDEX ix_owner_lbl ON owner(label)', database=DATABASE)
    run(live, 'index', 'visibility', {'visibility': 'IGNORED'}, name='ix_owner_lbl')
    run(live, 'index', 'rename', {'new_name': 'ix_owner_lbl_v2'}, name='ix_owner_lbl')
    assert query(f"SELECT IGNORED FROM information_schema.statistics WHERE table_schema='{DATABASE}' AND index_name='ix_owner_lbl_v2'") == [('YES',)]

    # Temporal system-versioning & application-time period lifecycle
    execute('CREATE TABLE temp_sv(id INT PRIMARY KEY, label VARCHAR(32)) ENGINE=InnoDB',
            "INSERT INTO temp_sv VALUES (1, 'v1')",
            'CREATE TABLE temp_ap(id INT PRIMARY KEY, vf DATE NOT NULL, vt DATE NOT NULL) ENGINE=InnoDB', database=DATABASE)
    run(live, 'table', 'add_system_versioning', {
        'explicit_period_columns': True, 'row_start_column': 'rs', 'row_end_column': 're',
        'invisible_period_columns': True}, target=table_target(live, 'temp_sv'))
    execute("UPDATE temp_sv SET label='v2' WHERE id=1", database=DATABASE)
    run(live, 'table', 'rotate_system_time_partitions', {
        'rotation_action': 'PARTITION_BY_LIMIT', 'row_limit': 50, 'history_partitions': 2}, target=table_target(live, 'temp_sv'))
    run(live, 'table', 'truncate_system_versioning_history', {
        'cutoff_mode': 'ALL', 'destructive_history_confirmed': True}, target=table_target(live, 'temp_sv'))
    execute('ALTER TABLE temp_sv REMOVE PARTITIONING', database=DATABASE)
    run(live, 'table', 'drop_system_versioning', {
        'drop_period_columns': True, 'row_start_column': 'rs', 'row_end_column': 're', 'destructive_history_confirmed': True},
        target=table_target(live, 'temp_sv'))
    run(live, 'table', 'add_application_period', {
        'period_name': 'p_win', 'start_column': 'vf', 'end_column': 'vt'}, target=table_target(live, 'temp_ap'))
    run(live, 'table', 'drop_application_period', {
        'period_name': 'p_win', 'destructive_history_confirmed': True}, target=table_target(live, 'temp_ap'))

    # Retained-session drop_temporary
    retained = client.open_session({'route': dict(route, autocommit=False)})
    try:
        retained.cursor().execute(f'CREATE TEMPORARY TABLE `{DATABASE}`.`owner` (tmp_id INT PRIMARY KEY)')
        tmp_target = {
            'resource_id': f'temporary-table:{DATABASE}:owner',
            'resource_kind': 'table',
            'display_name': 'owner',
            'display_path': [DATABASE, 'owner'],
            'native': {'temporary': True, 'table_type': 'TEMPORARY', 'server_uid': server_uid},
        }
        run(live, 'table', 'drop_temporary', target=tmp_target, session_id='ops-tmp-1', connection=retained)
        assert query('SELECT count(*) FROM owner', DATABASE) == [(2,)]
    finally:
        client.close_session(retained)

    # View / procedure / function / trigger create_or_replace
    execute('CREATE PROCEDURE pr_rep() SELECT 1',
            'CREATE FUNCTION fn_rep() RETURNS INT DETERMINISTIC NO SQL RETURN 1',
            "CREATE TRIGGER tr_rep BEFORE INSERT ON owner FOR EACH ROW SET NEW.label = NEW.label", database=DATABASE)
    run(live, 'view', 'create_or_replace', {'definition': 'SELECT id, label FROM owner'}, name='owner_view')
    run(live, 'procedure', 'create_or_replace', {'body': 'BEGIN SELECT 2; END'}, name='pr_rep')
    run(live, 'function', 'create_or_replace', {
        'returns': 'INT', 'deterministic': 'DETERMINISTIC', 'data_access': 'NO SQL', 'body': 'RETURN 2'}, name='fn_rep')
    run(live, 'trigger', 'create_or_replace', {'body': "SET NEW.label = COALESCE(NEW.label, '')"}, name='tr_rep')
    assert query(f'SELECT `{DATABASE}`.fn_rep()') == [(2,)]


def test_every_declared_operation_is_exercised():
    declared = {key for key in OPERATIONS}
    assert len(declared) == 90
    exercised = {
        'analyze_tables@database', 'check_objects@database', 'optimize_tables@database', 'repair_objects@database',
        'checksum_tables@database', 'backup_logical@database', 'restore_logical@database', 'check_upgrade_required@server',
        'add_partitions@table', 'coalesce_partitions@table', 'partition_by@table', 'remove_partitioning@table',
        'convert_from_table@table', 'analyze@partition', 'check@partition', 'optimize@partition', 'rebuild@partition',
        'repair@partition', 'reorganize@partition', 'exchange@partition', 'convert_to_table@partition',
        'create_specification@package', 'create_body@package', 'replace_body@package', 'replace_specification@package',
        'drop_body@package', 'set_default@role', 'start@replication-channel', 'stop@replication-channel',
        'reset@replication-channel', 'terminate_query@session', 'terminate_connection@session',
        'set_global@system-variable', 'purge_before@binary-log', 'rotate@binary-log-status',
    }
    # Additional native workflows are qualified in their dedicated server/sequence suites.
    exercised.update({'set_session@system-variable', 'set_session_optimizer_switch_flags@system-variable', 'inspect_live_explain@server', 'reset_query_cache@server', 'preload_index_cache@server', 'refresh_editor_context@database', 'assign_index_cache@server', 'inspect_live_analyze@server', 'create@sequence', 'release_key_cache@server', 'start_all_replicas@server', 'rollback_prepared_xa@server', 'inspect_engine_logs@server', 'inspect_key_cache@server', 'configure_key_cache@server', 'shutdown_server@server', 'stop_all_replicas@server', 'inspect_prepared_xa@server', 'reset_binary_logs@server', 'commit_prepared_xa@server', 'inspect_key_caches@server', 'inspect_engine_mutex@server', 'reset_default_replica@server', 'inspect_engine_status@server', 'set_session_optimizer_trace_flags@system-variable', 'alter@sequence', 'physical_backup@server', 'prepare_physical_chain@server', 'recover_physical_instance@server', 'evaluate_archive_retention@server', 'manage_host_service@server', 'upgrade_server_instance@server', 'manage_galera_cluster@server', 'run_aria_chk@server', 'run_aria_pack@server', 'run_myisamchk@server', 'run_myisampack@server', 'run_innochecksum@server', 'run_mariadb_slap@server', 'flush@server', 'flush@table', 'add_application_period@table', 'add_system_versioning@table', 'create_or_replace@function', 'create_or_replace@procedure', 'create_or_replace@trigger', 'create_or_replace@view', 'drop_application_period@table', 'drop_system_versioning@table', 'drop_temporary@table', 'inspect_available_plugins@server', 'rename@index', 'rotate_system_time_partitions@table', 'truncate_system_versioning_history@table', 'visibility@index'})
    assert declared == exercised
