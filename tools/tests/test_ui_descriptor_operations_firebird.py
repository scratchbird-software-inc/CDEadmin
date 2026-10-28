"""Firebird tier 2/3 operations round-trip (README step 8): the OperationDialog's
draft (field defaults + values) -> provider validate/plan/apply -> observe the
effect on a live Firebird 5 server.

Needs a reachable Firebird 5 server. Set ``CDEADMIN_ROUNDTRIP_FIREBIRD`` to the
same JSON the family suite uses (``{"host", "port", "user", "password",
"database_root"}``, ``database_root`` writable by the server process) and
``CDEADMIN_FIREBIRD_CLIENT_LIBRARY`` to a Firebird 5 ``libfbclient``. Every
database and file is created under ``database_root`` with a unique prefix and
removed at the end. Skipped otherwise.

Service routing: the gfix-class Services API tasks (sweep, repair, every
``set_*`` property, shutdown/online, linger, upgrade, replica mode) are refused
by a Firebird 5.0.3 server over a TCP attachment authenticated with Srp256
("attempt to store 338 bytes in a clumplet with maximum size 255 bytes": the
auth block does not fit the utility's clumplet). gbak, nbackup, validate and
gstat work over TCP. Those gfix-class tasks therefore run through the same
provider path with a route that has no host (the local Services API), against
the same database files; every effect is then observed through a TCP
attachment to the live server.
"""
import json
import os
import shutil
import subprocess
import sys
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

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_FIREBIRD')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_FIREBIRD is not set', allow_module_level=True)
driver = pytest.importorskip('firebird.driver')

from pgadmin.cdeadmin.providers.firebird.provider import ADMINISTRATION, _create_client, _resources  # noqa: E402
from pgadmin.cdeadmin.security.secrets import SecretLease  # noqa: E402
from ui_descriptor_roundtrip import engine_operations, operation_draft  # noqa: E402

SETTINGS = json.loads(SETTINGS)
UNIQUE = uuid.uuid4().hex[:6].lower()
OPERATIONS = engine_operations('firebird')
FILES = Path(SETTINGS['database_root'])
GBAK_AND_TCP_SAFE = {'backup_logical', 'restore_logical', 'backup_physical', 'restore_physical',
                     'validate_database', 'database_statistics'}
SCHEMA = (
    'CREATE TABLE OWNER(ID INTEGER NOT NULL PRIMARY KEY, LABEL VARCHAR(40), NOTE VARCHAR(10))',
    "INSERT INTO OWNER VALUES (1, 'one', 'n1')",
    'CREATE SEQUENCE SEQ_OPS',
    'CREATE PACKAGE PKG_OPS AS BEGIN PROCEDURE P1; END',
)


class Env(SimpleNamespace):
    def dsn(self, path):
        return f"{SETTINGS['host']}/{SETTINGS['port']}:{path}"

    def connect(self, path):
        return driver.connect(self.dsn(path), user=SETTINGS['user'], password=SETTINGS['password'])

    def path(self, suffix):
        path = FILES / f'ops_{UNIQUE}_{suffix}'
        self.created.append(path)
        return str(path)

    def database(self, suffix, schema=SCHEMA):
        path = self.path(suffix + '.fdb')
        seed = driver.create_database(self.dsn(path), user=SETTINGS['user'], password=SETTINGS['password'])
        for statement in schema:
            seed.execute_immediate(statement)
            seed.commit()
        seed.close()
        return path

    def route(self, path, local=False):
        route = {'database': path, 'user': SETTINGS['user'], 'credential_reference_id': 'ui-ops',
                 'principal_reference': 'ui-ops'}
        if not local:
            route.update(host=SETTINGS['host'], port=int(SETTINGS['port']))
        return route

    def resources(self, route):
        connection = self.client._connect({'route': dict(route)})
        try:
            return list(_resources(connection, {}))
        finally:
            self.client._forget_and_close(connection)

    def resource(self, route, kind, name=None):
        return next(row for row in self.resources(route)
                    if row['resource_kind'] == kind and (name is None or row['display_name'] == name))

    def query(self, path, sql, params=()):
        connection = self.connect(path)
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        finally:
            connection.close()

    def monitor(self, path):
        names = ('MON$PAGE_SIZE', 'MON$ODS_MAJOR', 'MON$ODS_MINOR', 'MON$SQL_DIALECT', 'MON$SWEEP_INTERVAL',
                 'MON$READ_ONLY', 'MON$FORCED_WRITES', 'MON$RESERVE_SPACE', 'MON$PAGE_BUFFERS', 'MON$BACKUP_STATE',
                 'MON$REPLICA_MODE', 'MON$OLDEST_TRANSACTION', 'MON$NEXT_TRANSACTION')
        row = self.query(path, 'SELECT ' + ', '.join(names) + ' FROM MON$DATABASE')[0]
        return dict(zip((name.split('$')[1].lower() for name in names), row))

    def run(self, operation_id, path, values=None, *, kind='database', target=None, confirmation=None,
            via_tcp=None, route=None):
        """Dialog draft -> validate -> plan -> apply; the target is the selected resource."""
        operation = OPERATIONS[f'{operation_id}@{kind}']
        tcp = (operation_id in GBAK_AND_TCP_SAFE or kind != 'database'
               or operation_id in {'inspect_limbo', 'commit_limbo_local', 'rollback_limbo_local'}
               or operation.get('tier') == 2) if via_tcp is None else via_tcp
        route = route or self.route(path, local=not tcp)
        if target is None:
            target = self.resource(self.route(path), kind) if kind == 'database' else None
        draft = operation_draft(operation, values, confirmation=confirmation if confirmation is not None else path)
        request = {'resource_kind': kind, 'operation_id': operation_id, 'target_resource': target,
                   '_provider_route': route, 'draft': draft}
        assert ADMINISTRATION.validate(request)['errors'] == [], operation_id
        planned = ADMINISTRATION.plan(request)
        self.native.clear()
        try:
            result = ADMINISTRATION.apply(self.client, planned)
        except Exception as error:
            # The provider wraps native errors without their text; keep the cause in the failure.
            raise AssertionError(f'{operation_id}: {error} native={self.native}') from error
        assert result['accepted'], (operation_id, result)
        return planned, result

    def server_log(self, path):
        """firebird.log entries for one database, read through the Services API."""
        out = []
        with driver.connect_server(self.observer) as server:
            server.info.get_log(callback=out.append)
        blocks = ''.join(out).split('\n\n\n')
        return [block for block in blocks if path in block]

    def observation(self, result):
        return result.get('driver_observation') or {}


@pytest.fixture(scope='module')
def env():
    client = _create_client(SimpleNamespace(acquire_secret=lambda *_args: SecretLease(SETTINGS['password'])))
    state = Env(client=client, created=[], native=[], observer=f'ops_observer_{UNIQUE}')
    driver.driver_config.register_server(
        state.observer, f"[{state.observer}]\nhost = {SETTINGS['host']}\nport = {SETTINGS['port']}\n"
                        f"user = {SETTINGS['user']}\npassword = {SETTINGS['password']}\n")
    wrapped = client._server_operation_error
    client._server_operation_error = lambda error: (state.native.append(f'{type(error).__name__}: {error}'),
                                                    wrapped(error))[1]
    try:
        yield state
    finally:
        client.close()
        for path in state.created:
            if str(path).endswith('.fdb'):
                try:
                    state.connect(str(path)).drop_database()
                except Exception:  # noqa: BLE001 - shut down, never created or already gone
                    pass
        for path in state.created:
            Path(path).unlink(missing_ok=True)
        for leftover in FILES.glob(f'ops_{UNIQUE}_*'):
            leftover.unlink(missing_ok=True)


def lines(result):
    return ''.join(result['driver_observation']['output'])


def test_inspect_prepared_transactions_on_a_clean_database(env):
    path = env.database('inspect')
    _planned, result = env.run('inspect_limbo', path)
    assert env.observation(result)['transactions'] == []
    assert env.observation(result)['inventory_complete'] is True


BULK = SCHEMA + (
    'CREATE TABLE BULK(ID INTEGER NOT NULL PRIMARY KEY, PAYLOAD VARCHAR(200))',
    "EXECUTE BLOCK AS DECLARE I INTEGER = 0; BEGIN WHILE (I < 3000) DO BEGIN "
    "INSERT INTO BULK VALUES (:I, RPAD('x', 200, 'y')); I = I + 1; END END",
)


def test_logical_backup_and_restore_round_trip(env):
    path = env.database('gbak')
    backup = env.path('gbak.fbk')
    _planned, result = env.run('backup_logical', path, {'backup_file': backup})
    assert env.observation(result)['server_completed'] is True
    assert Path(backup).stat().st_size > 0 and 'gbak' in lines(result)

    restored = env.path('gbak_restored.fdb')
    _planned, result = env.run('restore_logical', path, {
        'backup_file': backup, 'restore_database': restored, 'page_size': '16384',
        'access_mode': 'READ_ONLY'})
    assert env.observation(result)['database'] == restored
    assert env.query(restored, 'SELECT COUNT(*) FROM OWNER') == [(1,)]
    monitor = env.monitor(restored)
    assert monitor['page_size'] == 16384 and monitor['read_only'] == 1

    # An existing target needs the explicit replace switch (create is the default).
    replaced = env.path('gbak_replace.fdb')
    env.run('restore_logical', path, {'backup_file': backup, 'restore_database': replaced})
    env.run('restore_logical', path, {'backup_file': backup, 'restore_database': replaced,
                                      'replace_existing': True, 'restore_flags': ['USE_ALL_SPACE', 'NO_VALIDITY'],
                                      'page_buffers': 4096})
    assert env.query(replaced, 'SELECT COUNT(*) FROM OWNER') == [(1,)]
    assert env.monitor(replaced)['reserve_space'] == 0 and env.monitor(replaced)['page_buffers'] == 4096


def test_logical_backup_metadata_only_and_data_filters(env):
    path = env.database('gbak_meta', BULK)
    backup = env.path('meta.fbk')
    env.run('backup_logical', path, {'backup_file': backup, 'backup_flags': ['METADATA_ONLY']})
    meta = env.path('meta.fdb')
    env.run('restore_logical', path, {'backup_file': backup, 'restore_database': meta})
    assert env.query(meta, 'SELECT COUNT(*) FROM BULK') == [(0,)]

    filtered = env.path('filtered.fbk')
    env.run('backup_logical', path, {'backup_file': filtered, 'skip_data': 'BULK', 'verbose': False,
                                     'statistics': 'TD', 'parallel_workers': 1})
    restored = env.path('filtered.fdb')
    env.run('restore_logical', path, {'backup_file': filtered, 'restore_database': restored,
                                      'include_data': 'OWNER', 'verbose': False})
    assert env.query(restored, 'SELECT (SELECT COUNT(*) FROM OWNER), (SELECT COUNT(*) FROM BULK) FROM RDB$DATABASE') == [(1, 0)]


def test_split_logical_backup_and_multi_file_restore(env):
    path = env.database('gbak_split', BULK)
    volumes = [env.path('split_a.fbk'), env.path('split_b.fbk')]
    env.run('backup_logical', path, {'split_backup': True, 'backup_volumes': [
        {'filename': volumes[0], 'size_bytes': 100000}, {'filename': volumes[1]}]})
    assert all(Path(volume).stat().st_size > 0 for volume in volumes)

    restored, secondary = env.path('split.fdb'), env.path('split.fd1')
    env.run('restore_logical', path, {
        'backup_file': volumes[0], 'additional_backup_files': [{'value': volumes[1]}],
        'restore_database': restored, 'multiple_database_files': True, 'primary_file_pages': 300,
        'database_file_volumes': [{'filename': secondary}]})
    assert env.query(restored, 'SELECT COUNT(*) FROM BULK') == [(3000,)]
    assert Path(secondary).stat().st_size > 0
    files = env.query(restored, "SELECT TRIM(RDB$FILE_NAME) FROM RDB$FILES WHERE RDB$SHADOW_NUMBER = 0 "
                                "OR RDB$SHADOW_NUMBER IS NULL")
    assert any(str(secondary) == row[0] for row in files)


def test_physical_backup_and_restore_chain(env):
    path = env.database('nbak')
    full, increment = env.path('nbak0.nbk'), env.path('nbak1.nbk')
    env.run('backup_physical', path, {'backup_file': full, 'backup_level': 0, 'direct_io_mode': 'OFF'})
    assert Path(full).stat().st_size > 0
    connection = env.connect(path)
    connection.execute_immediate("INSERT INTO OWNER VALUES (2, 'two', 'n2')")
    connection.commit()
    connection.close()
    env.run('backup_physical', path, {'backup_file': increment, 'backup_level': 1})
    restored = env.path('nbak_restored.fdb')
    env.run('restore_physical', path, {'backup_files': [{'value': full}, {'value': increment}],
                                       'restore_database': restored})
    assert env.query(restored, 'SELECT COUNT(*) FROM OWNER') == [(2,)]


def test_validate_and_statistics_report_native_output(env):
    path = env.database('stat', BULK)
    _planned, result = env.run('validate_database', path, {'include_table': 'OWNER', 'lock_timeout': 5})
    assert 'Validation finished' in lines(result) and 'OWNER' in lines(result) and 'BULK' not in lines(result)
    _planned, result = env.run('database_statistics', path)
    assert 'Database header page information' in lines(result) and 'Analyzing database pages' not in lines(result)
    _planned, result = env.run('database_statistics', path, {'statistics_flags': ['DATA_PAGES']})
    assert 'OWNER (' in lines(result) and 'BULK (' in lines(result)
    _planned, result = env.run('database_statistics', path, {
        'statistics_flags': ['DATA_PAGES'], 'tables': [{'value': 'OWNER'}]})
    assert 'OWNER (' in lines(result) and 'BULK (' not in lines(result)


def spawn(env, path, code):
    """Run driver code in a child process that then dies without detaching (a crashed client)."""
    script = (
        'import os, sys, firebird.driver as d\n'
        'd.driver_config.fb_client_library.value = os.environ["CDEADMIN_FIREBIRD_CLIENT_LIBRARY"]\n'
        'c = d.connect(sys.argv[1], user=sys.argv[2], password=sys.argv[3])\n'
        + code + '\nsys.stdout.flush()\nos._exit(0)\n')
    done = subprocess.run([sys.executable, '-c', script, env.dsn(path), SETTINGS['user'], SETTINGS['password']],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def test_sweep_advances_the_oldest_transaction(env):
    path = env.database('sweep')
    # A client that dies mid-transaction leaves a dead transaction that holds the OIT back.
    spawn(env, path, '''c.begin(d.TPB(no_auto_undo=True).get_buffer())
c.execute_immediate("INSERT INTO OWNER VALUES (2, 'garbage', 'g')")''')
    before = env.monitor(path)
    assert before['oldest_transaction'] < before['next_transaction'] - 1
    env.run('sweep_database', path)
    after = env.monitor(path)
    assert after['oldest_transaction'] > before['oldest_transaction']
    env.run('sweep_database', path, {'parallel_workers': 1})


def test_database_property_tasks_change_the_header(env):
    path = env.database('props')
    assert env.monitor(path)['sweep_interval'] == 20000
    env.run('set_sweep_interval', path, {'sweep_interval': 12345})
    assert env.monitor(path)['sweep_interval'] == 12345
    env.run('set_page_cache_size', path, {'page_buffers': 5000})
    assert env.monitor(path)['page_buffers'] == 5000
    assert env.monitor(path)['reserve_space'] == 1
    env.run('set_space_reservation', path, {'mode': 'USE_FULL'})
    assert env.monitor(path)['reserve_space'] == 0
    env.run('set_space_reservation', path)
    assert env.monitor(path)['reserve_space'] == 1
    assert env.monitor(path)['forced_writes'] == 1
    env.run('set_write_mode', path, {'mode': 'ASYNC'})
    assert env.monitor(path)['forced_writes'] == 0
    env.run('set_write_mode', path)
    assert env.monitor(path)['forced_writes'] == 1
    env.run('set_access_mode', path, {'mode': 'READ_ONLY'})
    assert env.monitor(path)['read_only'] == 1
    env.run('set_access_mode', path)
    assert env.monitor(path)['read_only'] == 0
    env.run('set_sql_dialect', path, {'sql_dialect': '1'})
    assert env.monitor(path)['sql_dialect'] == 1
    env.run('set_sql_dialect', path)
    assert env.monitor(path)['sql_dialect'] == 3
    assert env.monitor(path)['replica_mode'] in (None, 0)
    env.run('set_replica_mode', path, {'mode': 'READ_ONLY'})
    assert env.monitor(path)['replica_mode'] == 1
    env.run('set_replica_mode', path)
    assert env.monitor(path)['replica_mode'] in (None, 0)


def test_shutdown_denies_attachments_until_the_database_is_brought_online(env):
    path = env.database('shutdown')
    target = env.resource(env.route(path), 'database')
    env.run('shutdown_database', path, target=target)
    with pytest.raises(driver.DatabaseError, match='(?i)shutdown'):
        env.connect(path)
    env.run('bring_online', path, target=target)
    assert env.query(path, 'SELECT COUNT(*) FROM OWNER') == [(1,)]
    env.run('shutdown_database', path, {'mode': 'SINGLE', 'method': 'FORCED', 'shutdown_timeout': 1}, target=target)
    first = env.connect(path)  # single-user shutdown admits exactly one attachment
    try:
        with pytest.raises(driver.DatabaseError, match='(?i)shutdown|single'):
            env.connect(path)
    finally:
        first.close()
    env.run('bring_online', path, {'mode': 'MULTI'}, target=target)
    assert env.query(path, 'SELECT COUNT(*) FROM OWNER') == [(1,)]


def test_remove_linger_completes_without_a_header_change(env):
    # Linger is a server cache lifetime, not a header attribute: the task is accepted and completes, but
    # nothing durable can be observed, so the descriptor keeps this operation at draft.
    path = env.database('linger')
    _planned, before = env.run('database_statistics', path)
    _planned, result = env.run('remove_linger', path)
    assert env.observation(result)['server_completed'] is True
    _planned, after = env.run('database_statistics', path)
    assert lines(before).split('Generation')[1].split('\n')[1:] == lines(after).split('Generation')[1].split('\n')[1:] \
        or 'Attributes' in lines(after)


def test_repair_validates_and_mends_a_database(env):
    path = env.database('repair', BULK)
    runs = ({}, {'repair_modifiers': ['FULL', 'CHECK_DB']}, {'repair_action': 'MEND_DB'},
            {'repair_action': 'CORRUPTION_CHECK'}, {'no_linger': True})
    for values in runs:
        _planned, result = env.run('repair_database', path, values)
        selection = env.observation(result)['repair_selection_requested']
        assert env.observation(result)['server_completed'] is True
        assert selection['action'] == values.get('repair_action', 'VALIDATE_DB')
    # gfix validation reports into the server log, one start and one finish per run.
    log = '\n'.join(env.server_log(path))
    assert log.count('Validation finished: 0 errors') == len(runs)
    env.run('repair_database', path, {'repair_action': 'ICU', 'parallel_workers': 1})
    assert env.query(path, 'SELECT COUNT(*) FROM BULK') == [(3000,)]


def test_physical_backup_mode_and_fixup_of_a_filesystem_copy(env):
    path = env.database('nfix')
    target = env.resource(env.route(path), 'database')
    difference = env.path('nfix.delta')
    env.run('add_difference_file', path, {'filename': difference})
    entry = env.query(path, "SELECT TRIM(RDB$FILE_NAME), RDB$FILE_FLAGS FROM RDB$FILES WHERE RDB$FILE_FLAGS = 32")
    assert [row[0] for row in entry] == [difference]
    env.run('begin_backup', path, {'confirm_difference_overwrite': True})
    assert env.monitor(path)['backup_state'] == 1 or env.monitor(path)['backup_state'] == 2
    copy = env.path('nfix_copy.fdb')
    shutil.copyfile(path, copy)  # the main file is frozen while the difference file takes writes
    env.run('end_backup', path)
    assert env.monitor(path)['backup_state'] == 0
    with pytest.raises(driver.DatabaseError):
        env.connect(copy)  # a copy taken in backup mode is not attachable until it is fixed up
    env.run('fixup_database', copy, target=target)
    assert env.query(copy, 'SELECT COUNT(*) FROM OWNER') == [(1,)]
    assert env.monitor(copy)['backup_state'] == 0
    env.run('drop_difference_file', path)
    assert env.query(path, "SELECT COUNT(*) FROM RDB$FILES WHERE RDB$FILE_FLAGS = 32") == [(0,)]


def test_add_database_files_extends_storage(env):
    path = env.database('files')
    secondary = env.path('files.fd1')
    env.run('add_files', path, {'files': [{'filename': secondary, 'start': 400}]})
    registered = env.query(path, "SELECT TRIM(RDB$FILE_NAME), RDB$FILE_START FROM RDB$FILES WHERE RDB$SHADOW_NUMBER = 0")
    assert (secondary, 400) in registered
    assert env.query(path, 'SELECT COUNT(*) FROM OWNER') == [(1,)]
