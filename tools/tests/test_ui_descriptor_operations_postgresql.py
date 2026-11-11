"""PostgreSQL tier 2/3 operations round-trip through the OperationDialog's draft
(field defaults + values) -> provider visual-admin validate/plan/apply -> effect
observed on a live PostgreSQL server.

The PostgreSQL provider executes these non-lifecycle actions through its own
validate/plan/apply route: the large-object read, write, truncate and server-file
import/export (``providers/postgresql/large_objects.py``) and the maintenance
actions VACUUM, ANALYZE, REINDEX (table, index, schema, database), CLUSTER, table
TRUNCATE and REFRESH MATERIALIZED VIEW (``providers/postgresql/maintenance.py``).
Rename, set schema, owner and grant on tables and the like stay with the preserved
pgAdmin surface; ``compile_native_admin`` refuses them.

Set ``CDEADMIN_ROUNDTRIP_POSTGRESQL`` to ``{"host", "port", "user", "password"?,
"database"?, "server_file_dir"?}`` for a superuser (large-object server-file
functions need one). ``server_file_dir`` is a directory the server process may
write and this test may read (same host); the file operations skip without it.
The live tests skip without the variable; the structural tests always run.
The profile pins PostgreSQL 18.3 and this suite does not prove that version: it
records the server version it ran against.
"""
import base64
import hashlib
import json
import os
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools'))
# Only the top-level package is stubbed. Stubbing pgadmin.utils or config
# shadowed the real modules for every later test in the session
# (2026-11-10): tests that import get_complete_file_path from pgadmin.utils
# then failed.
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.core import EndpointContext  # noqa: E402
from pgadmin.cdeadmin.providers.postgresql.provider import (  # noqa: E402
    LEGACY_DRIVER_TYPE, POSTGRESQL_ADMIN_OPERATIONS, PostgreSQLProvider,
)
from ui_descriptor_roundtrip import engine_operations, operation_draft  # noqa: E402

OPERATIONS = engine_operations('postgresql')
UNIQUE = uuid.uuid4().hex[:6]
DATABASE = f'ui_ops_{UNIQUE}'
SETTINGS = json.loads(os.environ.get('CDEADMIN_ROUNDTRIP_POSTGRESQL') or 'null')
live_only = pytest.mark.skipif(SETTINGS is None, reason='CDEADMIN_ROUNDTRIP_POSTGRESQL is not set')
#: Operations whose live test exists in this module; every ``complete`` descriptor must be listed.
TESTED = {'read@large-object', 'write@large-object', 'truncate@large-object',
          'import-server-file@large-object', 'export-server-file@large-object',
          'vacuum@table', 'analyze@table', 'reindex@table', 'cluster@table', 'truncate@table',
          'reindex@index', 'reindex@schema', 'reindex@database', 'refresh@materialized-view',
          'reload@server', 'restore-point@server', 'wal-replay-pause@server', 'wal-replay-resume@server',
          'vacuum@schema', 'analyze@schema', 'vacuum@database', 'analyze@database',
          'reassign-owned@role', 'drop-owned@role', 'move-objects@tablespace', 'run-now@pgagent-job',
          'count-rows@table', 'reset-statistics@table', 'enable-triggers@table', 'disable-triggers@table'}


# -- structural: the descriptors name only what the provider admits ------------------------------
def provider_form_fields(operation_id, kind='large-object'):
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import adapt_catalog
    catalog = adapt_catalog({'objects': []})
    resource = next(item for item in catalog['objects'] if item['resource_kind'] == kind)
    operation = next(item for item in resource['operations'] if item['operation_id'] == operation_id)
    return {field['field_id']: field for field in operation['form']['fields']}


def test_every_operation_is_a_provider_native_route():
    assert OPERATIONS, 'postgresql/operations.json lists no operations'
    for key, operation in OPERATIONS.items():
        assert operation['operation_id'] in POSTGRESQL_ADMIN_OPERATIONS[operation['resource_kind']], key
        assert operation['tier'] in (2, 3), key
        provider = provider_form_fields(operation['operation_id'], operation['resource_kind'])
        fields = {field['field_id'] for field in operation['fields']}
        confirmation = {'confirmation'} if operation['confirmation'] == 'typed_name' else set()
        assert fields <= set(provider), (key, sorted(fields - set(provider)))
        for field_id, provider_field in provider.items():
            if provider_field['required'] and field_id not in fields and field_id not in confirmation:
                pytest.fail(f'{key}: provider requires {field_id} but the dialog has no field for it')


def test_destructive_operations_confirm_and_complete_ones_are_tested():
    for key, operation in OPERATIONS.items():
        provider = provider_form_fields(operation['operation_id'], operation['resource_kind'])
        if 'confirmation' in provider and provider['confirmation']['required']:
            assert operation['confirmation'] != 'none', key
        if operation['status'] == 'complete':
            assert key in TESTED, f'{key} is complete without a live round trip in this module'


def test_no_descriptor_without_a_provider_route():
    """A descriptor must have a provider compiler; table alter and friends stay legacy-preserved."""
    from pgadmin.cdeadmin.providers.postgresql.maintenance import MAINTENANCE_OPERATIONS
    from pgadmin.cdeadmin.providers.postgresql.native_admin import (
        POSTGRESQL_NATIVE_FORM_KINDS, PostgreSQLNativeAdminError, compile_native_admin)
    for operation in OPERATIONS.values():
        kind, operation_id = operation['resource_kind'], operation['operation_id']
        assert kind in POSTGRESQL_NATIVE_FORM_KINDS or operation_id in MAINTENANCE_OPERATIONS.get(kind, ()), (kind, operation_id)
    with pytest.raises(PostgreSQLNativeAdminError, match='preserved PostgreSQL UI'):
        compile_native_admin({'resource_kind': 'table', 'operation_id': 'alter', 'draft': {}})


def compile_maintenance(kind, operation, native, draft):
    from pgadmin.cdeadmin.providers.postgresql.native_admin import compile_native_admin
    return compile_native_admin({'resource_kind': kind, 'operation_id': operation, 'draft': draft,
                                 'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def test_maintenance_statements_are_quoted_and_allow_listed():
    from pgadmin.cdeadmin.providers.postgresql.native_admin import PostgreSQLNativeAdminError
    table = {'schema': 'we"ird', 'name': 'ta;ble --'}
    quoted = '"we""ird"."ta;ble --"'
    cases = [
        ('vacuum', {'full': True, 'verbose': True}, f'VACUUM (FULL, VERBOSE) {quoted}', True),
        ('vacuum', {'analyze': True, 'freeze': True, 'parallel': 3}, f'VACUUM (FREEZE, ANALYZE, PARALLEL 3) {quoted}', True),
        ('analyze', {'skip_locked': True}, f'ANALYZE (SKIP_LOCKED) {quoted}', False),
        ('reindex', {}, f'REINDEX TABLE {quoted}', False),
        ('reindex', {'concurrently': True}, f'REINDEX (CONCURRENTLY) TABLE {quoted}', True),
        ('cluster', {'index': 'i"x'}, f'CLUSTER {quoted} USING "i""x"', False),
        ('truncate', {'restart_identity': True, 'cascade': True, 'confirmation': 'ta;ble --'},
         f'TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE', False),
    ]
    for operation, draft, statement, autocommit in cases:
        compiled = compile_maintenance('table', operation, table, draft)
        assert (compiled['statement'], compiled['autocommit']) == (statement, autocommit), operation
    assert compile_maintenance('schema', 'reindex', {'name': 's"1'}, {})['autocommit'] is True
    assert compile_maintenance('database', 'reindex', {'name': 'd'}, {})['statement'] == 'REINDEX DATABASE "d"'
    # M6: database scope has no table list; schema scope names the listed relations, sorted and deduplicated.
    assert compile_maintenance('database', 'vacuum', {'name': 'd'}, {'full': True})['statement'] == 'VACUUM (FULL)'
    assert compile_maintenance('database', 'analyze', {'name': 'd'}, {})['statement'] == 'ANALYZE'
    schema = {'name': 's"1', 'relations': ['t2', 'a;b', 't2']}
    assert compile_maintenance('schema', 'vacuum', schema, {'analyze': True})['statement'] == \
        'VACUUM (ANALYZE) "s""1"."a;b", "s""1"."t2"'
    assert compile_maintenance('schema', 'analyze', schema, {'verbose': True})['statement'] == \
        'ANALYZE (VERBOSE) "s""1"."a;b", "s""1"."t2"'
    for bad in ({'name': 's'}, {'name': 's', 'relations': []}, {'name': 's', 'relations': [1]}):
        with pytest.raises(PostgreSQLNativeAdminError):
            compile_maintenance('schema', 'vacuum', bad, {})
    assert compile_maintenance('materialized-view', 'refresh', {'schema': 's', 'name': 'm'}, {'concurrently': True})[
        'statement'] == 'REFRESH MATERIALIZED VIEW CONCURRENTLY "s"."m" WITH DATA'
    for kind, operation, draft in [
            ('table', 'vacuum', {'full': True, 'parallel': 2}), ('table', 'vacuum', {'parallel': 1025}),
            ('table', 'vacuum', {'parallel': True}), ('table', 'vacuum', {'full': 'yes'}),
            ('table', 'vacuum', {'index_cleanup': True}), ('table', 'analyze', {'full': True}),
            ('table', 'truncate', {'confirmation': 'other'}), ('table', 'truncate', {}),
            ('materialized-view', 'refresh', {'concurrently': True, 'with_data': False}),
            ('index', 'cluster', {}), ('schema', 'vacuum', {})]:
        with pytest.raises(PostgreSQLNativeAdminError):
            compile_maintenance(kind, operation, table, draft)


def test_database_drop_compiles_with_force_from_the_server_scope():
    from pgadmin.cdeadmin.providers.postgresql.native_admin import PostgreSQLNativeAdminError
    from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLProvider
    native = {'name': 'd"b'}
    assert compile_maintenance('database', 'drop', native, {'confirmation': 'd"b', 'force': True}) == {
        'statement': 'DROP DATABASE "d""b" WITH (FORCE)', 'read_only': False, 'autocommit': True}
    assert compile_maintenance('database', 'drop', native, {'confirmation': 'd"b'})['statement'] == 'DROP DATABASE "d""b"'
    for draft in ({}, {'confirmation': 'other'}, {'confirmation': 'd"b', 'force': 'yes'}):
        with pytest.raises(PostgreSQLNativeAdminError):
            compile_maintenance('database', 'drop', native, draft)
    assert PostgreSQLProvider._native_admin_route({'resource_kind': 'database', 'operation_id': 'drop',
                                                   '_provider_route': {'server_id': 3, 'database_id': 9}}) \
        == {'server_id': 3, 'database_id': None}
    assert PostgreSQLProvider._native_admin_route({'resource_kind': 'database', 'operation_id': 'alter',
                                                   '_provider_route': {'server_id': 3, 'database_id': 9}}) \
        == {'server_id': 3, 'database_id': 9}
    fields = provider_form_fields('drop', 'database')
    assert fields['confirmation']['required'] and not fields['force']['required']


def test_database_picked_operations_compile_and_route_to_the_picked_database():
    from pgadmin.cdeadmin.providers.postgresql.native_admin import PostgreSQLNativeAdminError
    from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLProvider, PostgreSQLProviderError
    db = 'postgresql:pg_database/16384'
    role = {'name': 'r"1'}
    assert compile_maintenance('role', 'reassign-owned', role, {'database': db, 'new_owner': 'o;2'}) == {
        'statement': 'REASSIGN OWNED BY "r""1" TO "o;2"', 'read_only': False, 'autocommit': False,
        'maintenance': {'action': 'reassign-owned', 'object_kind': 'role', 'object': 'r"1', 'options': [],
                        'transaction_mode': 'transaction'}}
    assert compile_maintenance('role', 'drop-owned', role, {'database': db, 'confirmation': 'r"1'})['statement'] == \
        'DROP OWNED BY "r""1" RESTRICT'
    assert compile_maintenance('role', 'drop-owned', role, {'database': db, 'confirmation': 'r"1', 'cascade': True})[
        'statement'] == 'DROP OWNED BY "r""1" CASCADE'
    space = {'name': 'old'}
    assert compile_maintenance('tablespace', 'move-objects', space, {'database': db, 'new_tablespace': 'new'})[
        'statement'] == ('ALTER TABLE ALL IN TABLESPACE "old" SET TABLESPACE "new";\n'
                         'ALTER INDEX ALL IN TABLESPACE "old" SET TABLESPACE "new";\n'
                         'ALTER MATERIALIZED VIEW ALL IN TABLESPACE "old" SET TABLESPACE "new"')
    assert compile_maintenance('tablespace', 'move-objects', space, {
        'database': db, 'new_tablespace': 'new', 'object_type': 'indexes', 'owner': 'app'})['statement'] == \
        'ALTER INDEX ALL IN TABLESPACE "old" OWNED BY "app" SET TABLESPACE "new"'
    for kind, op, native, draft in [
            ('role', 'reassign-owned', role, {'new_owner': 'x'}),                       # no database picked
            ('role', 'reassign-owned', role, {'database': 'pg_database/1', 'new_owner': 'x'}),
            ('role', 'reassign-owned', role, {'database': db}),                         # no new owner
            ('role', 'drop-owned', role, {'database': db, 'confirmation': 'other'}),
            ('tablespace', 'move-objects', space, {'database': db, 'new_tablespace': 'old'}),
            ('tablespace', 'move-objects', space, {'database': db, 'new_tablespace': 'new', 'object_type': 'views'})]:
        with pytest.raises(PostgreSQLNativeAdminError):
            compile_maintenance(kind, op, native, draft)
    # The plan's route runs in the picked database, whatever the node's route carried.
    assert PostgreSQLProvider._native_admin_route({
        'resource_kind': 'role', 'operation_id': 'reassign-owned', '_provider_route': {'server_id': 2},
        'draft': {'database': db}}) == {'server_id': 2, 'database_id': 16384}
    with pytest.raises(PostgreSQLProviderError):
        PostgreSQLProvider._native_admin_route({'resource_kind': 'tablespace', 'operation_id': 'move-objects',
                                                '_provider_route': {'server_id': 2}, 'draft': {}})
    for op, kind in (('reassign-owned', 'role'), ('drop-owned', 'role'), ('move-objects', 'tablespace')):
        fields = provider_form_fields(op, kind)
        assert fields['database'] == {
            'field_id': 'database', 'label': 'Database', 'control': 'reference', 'required': True,
            'reference_kind': 'database', 'reference_value': 'resource_id',
            'help': 'Only the objects of this database are affected.'}, op


def test_table_operations_of_the_inherited_node_compile():
    from pgadmin.cdeadmin.providers.postgresql.native_admin import PostgreSQLNativeAdminError
    table = {'schema': 'we"ird', 'name': 'ta;ble --', 'oid': '24601'}
    quoted = '"we""ird"."ta;ble --"'
    compiled = compile_maintenance('table', 'count-rows', table, {})
    assert (compiled['statement'], compiled['read_only'], compiled['returns_rows']) == (
        f'SELECT count(*) AS row_count FROM {quoted}', True, True)
    assert compile_maintenance('table', 'reset-statistics', table, {})['statement'] == \
        'SELECT pg_catalog.pg_stat_reset_single_table_counters(24601) AS reset'
    assert compile_maintenance('table', 'enable-triggers', table, {})['statement'] == f'ALTER TABLE {quoted} ENABLE TRIGGER ALL'
    assert compile_maintenance('table', 'disable-triggers', table, {})['statement'] == f'ALTER TABLE {quoted} DISABLE TRIGGER ALL'
    for draft, native in (({'verbose': True}, table), ({}, {'schema': 's', 'name': 't'})):
        with pytest.raises(PostgreSQLNativeAdminError):
            compile_maintenance('table', 'reset-statistics', native, draft)


def test_server_operations_compile_without_a_target():
    from pgadmin.cdeadmin.providers.postgresql.native_admin import PostgreSQLNativeAdminError
    from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLProvider
    assert compile_maintenance('server', 'reload', {}, {}) == {
        'statement': 'SELECT pg_catalog.pg_reload_conf() AS reloaded', 'read_only': False, 'autocommit': False,
        'returns_rows': True, 'maintenance': {'action': 'reload', 'object_kind': 'server', 'object': None,
                                              'options': [], 'transaction_mode': 'transaction'}}
    assert compile_maintenance('server', 'restore-point', {}, {'name': "before it's"})['statement'] == \
        "SELECT pg_catalog.pg_create_restore_point('before it''s') AS restore_point_lsn"
    assert compile_maintenance('server', 'wal-replay-pause', {}, {})['statement'].endswith('pg_wal_replay_pause() AS paused')
    for draft in ({'name': ''}, {'name': 'x' * 64}, {}):
        with pytest.raises(PostgreSQLNativeAdminError):
            compile_maintenance('server', 'restore-point', {}, draft)
    with pytest.raises(PostgreSQLNativeAdminError):
        compile_maintenance('server', 'reload', {}, {'verbose': True})
    # Server scope: the route names the server only, and the dialog needs no target.
    assert PostgreSQLProvider._native_admin_route({'resource_kind': 'server', '_provider_route': {'server_id': 7}}) \
        == {'server_id': 7, 'database_id': None}
    for operation in ('reload', 'restore-point', 'wal-replay-pause', 'wal-replay-resume'):
        provider = provider_form_fields(operation, 'server')
        assert ('name' in provider) == (operation == 'restore-point'), operation
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import adapt_catalog
    catalog = adapt_catalog({'objects': []})
    server = next(item for item in catalog['objects'] if item['resource_kind'] == 'server')
    reload = next(op for op in server['operations'] if op['operation_id'] == 'reload')
    assert (reload['target_required'], reload['confirmation_required'], reload['execution_route']) == (
        False, True, 'provider-native')


# -- live harness: psycopg behind the pgAdmin connection-manager surface the provider uses --------
class Permissions:
    def require(self, *_args):
        return None


class Connection:
    def __init__(self, dsn):
        import psycopg
        self._dsn, self._psycopg, self.conn = dsn, psycopg, None

    def connected(self):
        return self.conn is not None and not self.conn.closed

    def connect(self, **_values):
        self.conn = self._psycopg.connect(self._dsn, autocommit=True)
        return True, None

    def transaction_status(self):
        return int(self.conn.info.transaction_status)

    def execute_dict(self, statement, parameters=None):
        with self.conn.cursor() as cursor:
            cursor.execute(statement, parameters)
            columns = [column.name for column in cursor.description or []]
            return True, {'rows': [dict(zip(columns, row)) for row in cursor.fetchall()] if columns else []}

    def execute_void(self, statement):
        with self.conn.cursor() as cursor:
            cursor.execute(statement)
        return True, None


class Manager:
    version = 180003
    server_type = 'pg'

    def __init__(self, dsn):
        self._dsn, self.connections = dsn, {}

    def connection(self, did=None, conn_id=None, **_kwargs):
        connection = self.connections[conn_id] = Connection(self._dsn)
        return connection

    def release(self, conn_id=None, **_kwargs):
        connection = self.connections.pop(conn_id, None)
        if connection is not None and connection.conn is not None:
            connection.conn.close()


class Driver:
    def __init__(self, dsn):
        self._manager = Manager(dsn)

    def connection_manager(self, _server_id):
        return self._manager


def dsn(database):
    password = f" password={SETTINGS['password']}" if SETTINGS.get('password') else ''
    return (f"host={SETTINGS['host']} port={int(SETTINGS['port'])} user={SETTINGS['user']}{password} "
            f"dbname={database}")


def query(sql, database=DATABASE):
    import psycopg
    with psycopg.connect(dsn(database), autocommit=True) as connection:
        cursor = connection.execute(sql)
        return cursor.fetchall() if cursor.description else []


@pytest.fixture(scope='module')
def live():
    pytest.importorskip('psycopg')
    query(f'CREATE DATABASE "{DATABASE}"', database=SETTINGS.get('database', 'postgres'))
    database_id = query(f"SELECT oid::int FROM pg_database WHERE datname='{DATABASE}'")[0][0]
    context = replace(
        EndpointContext(
            endpoint_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f'postgresql:ui-ops-{UNIQUE}')), mode='legacy_native',
            experience_family='postgresql', provider_id='org.pgadmin.postgresql', provider_version='9.17.0',
            profile_id='postgresql-native', profile_version='18.3', target_adapter_id='legacy-pgadmin-server',
            target_adapter_version='9.17.0', pool_namespace=str(uuid.uuid4()), session_namespace=str(uuid.uuid4()),
            cache_namespace=str(uuid.uuid4()), diagnostic_namespace=str(uuid.uuid4()),
            effective_permissions=frozenset({'network', 'secret_read', 'data_read', 'data_write', 'administer', 'execute'}),
            legacy_driver_type=LEGACY_DRIVER_TYPE),
        runtime_verification_state='verified')
    provider = PostgreSQLProvider(context, Permissions(), Driver(dsn(DATABASE)), catalog_source=object())
    route = {'server_id': 1, 'database_id': database_id}
    try:
        yield provider, route
    finally:
        import psycopg
        # The module-scoped sessions are closed per call; drop the database from a different one.
        with psycopg.connect(dsn(SETTINGS.get('database', 'postgres')), autocommit=True) as connection:
            connection.execute(f'DROP DATABASE IF EXISTS "{DATABASE}" WITH (FORCE)')


@pytest.fixture
def server_dir():
    directory = SETTINGS.get('server_file_dir')
    if not directory:
        pytest.skip('server_file_dir is not set')
    folder = Path(directory) / f'ui_ops_{UNIQUE}'
    folder.mkdir(exist_ok=True)
    folder.chmod(0o777)  # the server process may run as a different OS user
    yield folder
    for item in folder.glob('*'):
        item.unlink()
    folder.rmdir()


def large_object(data):
    return query(f"SELECT lo_from_bytea(0, '\\x{data.hex()}'::bytea)")[0][0]


def contents(oid):
    return bytes(query(f'SELECT lo_get({oid})')[0][0])


def target(oid, kind='large-object', native=None):
    # The resource the navigator lists: display name is the OID, native.oid is the identity.
    if native is not None:
        return {'resource_kind': kind, 'resource_id': f'postgresql:{kind}/{native["name"]}',
                'display_name': native['name'], 'extensions': {'postgresql': {'native': native}}}
    return {'resource_kind': 'large-object', 'resource_id': f'postgresql:large-object/{oid}',
            'display_name': str(oid), 'extensions': {'postgresql': {'native': {'oid': oid, 'name': str(oid)}}}}


def run(live, operation_id, values=None, oid=None, kind='large-object', confirmed=True, native=None):
    provider, route = live
    operation = OPERATIONS[f'{operation_id}@{kind}']
    resource = target(oid, kind, native) if (oid is not None or native is not None) else None
    # The dialog asks the user to type the target's display name for typed_name confirmations.
    draft = operation_draft(operation, values, confirmation=(resource or {}).get('display_name'))
    request = {'resource_kind': kind, 'operation_id': operation_id, 'target_resource': resource,
               '_provider_route': route, 'draft': draft}
    validation = provider.validate_visual_admin(request)
    assert validation['errors'] == [], (operation_id, validation)
    plan = provider.plan_visual_admin(request)
    assert plan['state'] == 'ready'
    # An operation the descriptor calls non-confirming must not demand confirmation.
    assert plan['confirmation_required'] == (operation['confirmation'] != 'none'), (operation_id, plan)
    result = provider.apply_visual_admin({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'],
                                          'confirmed': confirmed})
    outcome = result['provider_result']
    assert outcome['transaction_outcome'] == 'committed', outcome
    return plan, outcome


def b64(data):
    return base64.b64encode(data).decode('ascii')


@live_only
def test_server_version_is_recorded(live):
    version = query('SHOW server_version')[0][0]
    # Evidence is for this server only; the pinned profile is 18.3.
    assert version
    print(f'PostgreSQL {version}')


@live_only
def test_read_bytes(live):
    data = bytes(range(32))
    oid = large_object(data)
    plan, outcome = run(live, 'read', {'offset': '4', 'length': '10'}, oid=oid)
    assert plan['command_preview']['statement'].startswith('WITH chunk AS MATERIALIZED')
    row = outcome['result']['rows'][0]
    assert base64.b64decode(row['data_base64']) == data[4:14]
    assert row['byte_length'] == 10 and row['offset'] == 4
    assert row['sha256'] == hashlib.sha256(data[4:14]).hexdigest()
    assert contents(oid) == data  # reading changes nothing


@live_only
def test_write_bytes(live):
    oid = large_object(b'0123456789')
    chunk = b'ABC'
    plan, outcome = run(live, 'write', {'offset': '3', 'large_object_data_base64': b64(chunk)}, oid=oid)
    assert 'lo_put' in plan['command_preview']['statement']
    assert contents(oid) == b'012ABC6789'
    # Writing past the end extends the object (zero-filled gap), observed by size.
    run(live, 'write', {'offset': '12', 'large_object_data_base64': b64(b'Z')}, oid=oid)
    assert contents(oid) == b'012ABC6789\x00\x00Z'


@live_only
def test_write_rejects_non_canonical_base64(live):
    provider, route = live
    oid = large_object(b'abc')
    operation = OPERATIONS['write@large-object']
    draft = operation_draft(operation, {'large_object_data_base64': 'not base64!'})
    request = {'resource_kind': 'large-object', 'operation_id': 'write', 'target_resource': target(oid),
               '_provider_route': route, 'draft': draft}
    with pytest.raises(Exception, match='base64'):
        provider.plan_visual_admin(request)
    assert contents(oid) == b'abc'


@live_only
def test_truncate_to_length(live):
    oid = large_object(b'0123456789')
    plan, outcome = run(live, 'truncate', {'length': '4'}, oid=oid)
    assert 'lo_truncate64' in plan['command_preview']['statement']
    assert contents(oid) == b'0123'
    run(live, 'truncate', {'length': '0'}, oid=oid)
    assert contents(oid) == b''
    # The object itself stays: truncate is not drop.
    assert query(f'SELECT count(*) FROM pg_largeobject_metadata WHERE oid={oid}') == [(1,)]


@live_only
def test_truncate_requires_the_typed_oid(live):
    provider, route = live
    oid = large_object(b'keep me')
    operation = OPERATIONS['truncate@large-object']
    draft = operation_draft(operation, {'length': '0'}, confirmation='not-the-oid')
    request = {'resource_kind': 'large-object', 'operation_id': 'truncate', 'target_resource': target(oid),
               '_provider_route': route, 'draft': draft}
    with pytest.raises(Exception, match='confirmation must match'):
        provider.plan_visual_admin(request)
    assert contents(oid) == b'keep me'


@live_only
def test_apply_without_confirmation_is_refused(live):
    provider, route = live
    oid = large_object(b'keep me')
    operation = OPERATIONS['truncate@large-object']
    request = {'resource_kind': 'large-object', 'operation_id': 'truncate', 'target_resource': target(oid),
               '_provider_route': route, 'draft': operation_draft(operation, {'length': '0'}, confirmation=str(oid))}
    plan = provider.plan_visual_admin(request)
    with pytest.raises(Exception, match='requires confirmation'):
        provider.apply_visual_admin({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'], 'confirmed': False})
    assert contents(oid) == b'keep me'


@live_only
def test_export_to_server_file(live, server_dir):
    data = b'exported \x00\x01 bytes'
    oid = large_object(data)
    path = str(server_dir / 'out.bin')
    plan, outcome = run(live, 'export-server-file', {'server_file': path, 'confirmation': path}, oid=oid)
    assert outcome['file_effects']['host'] == 'database-server'
    assert (server_dir / 'out.bin').read_bytes() == data
    # A confirmation that is not the destination path never reaches the server.
    provider, route = live
    operation = OPERATIONS['export-server-file@large-object']
    request = {'resource_kind': 'large-object', 'operation_id': 'export-server-file', 'target_resource': target(oid),
               '_provider_route': route, 'draft': operation_draft(operation, {'server_file': path + '2', 'confirmation': path})}
    with pytest.raises(Exception, match='confirmation must match'):
        provider.plan_visual_admin(request)
    assert not (server_dir / 'out.bin2').exists()


@live_only
def test_import_from_server_file(live, server_dir):
    data = b'imported file \xff\xfe'
    source = server_dir / 'in.bin'
    source.write_bytes(data)
    source.chmod(0o666)
    plan, outcome = run(live, 'import-server-file', {'server_file': str(source)})
    oid = outcome['result']['rows'][0]['oid']
    assert isinstance(oid, int) and oid > 0
    assert contents(oid) == data
    query(f'SELECT lo_unlink({oid})')


# -- maintenance: dialog draft -> validate -> plan -> apply -> effect observed on the server -----------
def one(sql):
    return query(sql)[0][0]


def relfilenode(name, schema='public'):
    return one(f"SELECT relfilenode FROM pg_class WHERE oid = '{schema}.{name}'::regclass")


def maintain(live, operation_id, kind, name, schema='public', values=None, **kw):
    return run(live, operation_id, values, kind=kind, native={'schema': schema, 'name': name}, **kw)


def fresh_table(name, rows=1000):
    query(f'DROP TABLE IF EXISTS public.{name} CASCADE')
    query(f'CREATE TABLE public.{name} (id serial PRIMARY KEY, grp int, payload text)')
    query(f"INSERT INTO public.{name} (grp, payload) SELECT (g * 7919) % 1000, repeat('x', 50) "
          f'FROM generate_series(1, {rows}) g')


def eventually(sql, expected, seconds=10):
    import time
    deadline = time.time() + seconds
    while True:
        value = query(sql)
        if value == expected or time.time() > deadline:
            return value
        time.sleep(0.2)


@live_only
def test_vacuum_runs_outside_a_transaction_block(live):
    fresh_table('m_vac')
    query('DELETE FROM public.m_vac WHERE id % 2 = 0')
    plan, outcome = maintain(live, 'vacuum', 'table', 'm_vac', values={'analyze': True, 'verbose': True, 'parallel': 1})
    assert plan['command_preview']['statement'] == 'VACUUM (ANALYZE, VERBOSE, PARALLEL 1) "public"."m_vac"'
    assert any('outside a transaction block' in warning for warning in plan['warnings'])
    receipt = outcome['maintenance_receipt']
    assert receipt['executed'] is True and receipt['transaction_mode'] == 'autocommit'
    assert receipt['action'] == 'vacuum' and receipt['options'] == ['ANALYZE', 'VERBOSE', 'PARALLEL 1']
    assert eventually("SELECT last_vacuum IS NOT NULL AND last_analyze IS NOT NULL FROM pg_stat_user_tables "
                      "WHERE relname = 'm_vac'", [(True,)]) == [(True,)]
    before = relfilenode('m_vac')
    plan, outcome = maintain(live, 'vacuum', 'table', 'm_vac', values={'full': True})
    assert plan['command_preview']['statement'] == 'VACUUM (FULL) "public"."m_vac"'
    assert relfilenode('m_vac') != before  # FULL rewrites the table
    assert one('SELECT count(*) FROM public.m_vac') == 500


@live_only
def test_vacuum_rejects_full_with_parallel(live):
    provider, route = live
    fresh_table('m_vac2', 10)
    operation = OPERATIONS['vacuum@table']
    request = {'resource_kind': 'table', 'operation_id': 'vacuum', '_provider_route': route,
               'target_resource': target(None, 'table', {'schema': 'public', 'name': 'm_vac2'}),
               'draft': operation_draft(operation, {'full': True, 'parallel': 2})}
    with pytest.raises(Exception, match='cannot use PARALLEL'):
        provider.plan_visual_admin(request)


@live_only
def test_analyze_populates_statistics(live):
    fresh_table('m_ana')
    assert one("SELECT count(*) FROM pg_stats WHERE tablename = 'm_ana'") == 0
    plan, outcome = maintain(live, 'analyze', 'table', 'm_ana', values={'verbose': True})
    assert plan['command_preview']['statement'] == 'ANALYZE (VERBOSE) "public"."m_ana"'
    assert outcome['maintenance_receipt']['transaction_mode'] == 'transaction'
    assert one("SELECT count(*) FROM pg_stats WHERE tablename = 'm_ana'") == 3


@live_only
def test_reindex_table_index_schema_and_database(live):
    fresh_table('m_rei')
    query('CREATE INDEX m_rei_grp ON public.m_rei (grp)')
    before = {name: relfilenode(name) for name in ('m_rei_grp', 'm_rei_pkey')}
    plan, outcome = maintain(live, 'reindex', 'table', 'm_rei')
    assert outcome['maintenance_receipt']['transaction_mode'] == 'transaction'
    after = {name: relfilenode(name) for name in before}
    assert all(after[name] != before[name] for name in before)
    plan, outcome = maintain(live, 'reindex', 'index', 'm_rei_grp', values={'concurrently': True})
    assert plan['command_preview']['statement'] == 'REINDEX (CONCURRENTLY) INDEX "public"."m_rei_grp"'
    assert outcome['maintenance_receipt']['transaction_mode'] == 'autocommit'
    assert relfilenode('m_rei_grp') != after['m_rei_grp']
    assert one("SELECT indisvalid FROM pg_index WHERE indexrelid = 'public.m_rei_grp'::regclass") is True
    plan, outcome = maintain(live, 'reindex', 'table', 'm_rei', values={'concurrently': True})
    assert outcome['maintenance_receipt']['transaction_mode'] == 'autocommit'
    again = relfilenode('m_rei_pkey')
    plan, outcome = run(live, 'reindex', kind='schema', native={'name': 'public'})
    assert plan['command_preview']['statement'] == 'REINDEX SCHEMA "public"'
    assert outcome['maintenance_receipt']['transaction_mode'] == 'autocommit'
    assert relfilenode('m_rei_pkey') != again
    again = relfilenode('m_rei_pkey')
    plan, outcome = run(live, 'reindex', kind='database', native={'name': DATABASE})
    assert plan['command_preview']['statement'] == f'REINDEX DATABASE "{DATABASE}"'
    assert relfilenode('m_rei_pkey') != again


@live_only
def test_reindex_database_needs_confirmation(live):
    provider, route = live
    operation = OPERATIONS['reindex@database']
    request = {'resource_kind': 'database', 'operation_id': 'reindex', '_provider_route': route,
               'target_resource': target(None, 'database', {'name': DATABASE}), 'draft': operation_draft(operation)}
    plan = provider.plan_visual_admin(request)
    with pytest.raises(Exception, match='requires confirmation'):
        provider.apply_visual_admin({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'], 'confirmed': False})


@live_only
def test_cluster_orders_the_table_by_the_index(live):
    fresh_table('m_clu')
    query('CREATE INDEX m_clu_grp ON public.m_clu (grp)')
    assert one("SELECT indisclustered FROM pg_index WHERE indexrelid = 'public.m_clu_grp'::regclass") is False
    before = relfilenode('m_clu')
    plan, outcome = maintain(live, 'cluster', 'table', 'm_clu', values={'index': 'm_clu_grp'})
    assert plan['command_preview']['statement'] == 'CLUSTER "public"."m_clu" USING "m_clu_grp"'
    assert plan['confirmation_required'] is True
    assert one("SELECT indisclustered FROM pg_index WHERE indexrelid = 'public.m_clu_grp'::regclass") is True
    assert relfilenode('m_clu') != before
    heap_order = [row[0] for row in query('SELECT grp FROM public.m_clu ORDER BY ctid')]
    assert heap_order == sorted(heap_order)
    # Without an index the table's recorded clustering index is reused.
    plan, outcome = maintain(live, 'cluster', 'table', 'm_clu')
    assert plan['command_preview']['statement'] == 'CLUSTER "public"."m_clu"'


@live_only
def test_truncate_restart_identity_and_cascade(live):
    fresh_table('m_tru', 5)
    query('DROP TABLE IF EXISTS public.m_tru_child')
    query('CREATE TABLE public.m_tru_child (id int, parent int REFERENCES public.m_tru(id))')
    query('INSERT INTO public.m_tru_child VALUES (1, 1)')
    # PostgreSQL refuses a truncate that a referencing table blocks; nothing is removed.
    with pytest.raises(Exception, match='outcome is unknown'):
        maintain(live, 'truncate', 'table', 'm_tru')
    assert one('SELECT count(*) FROM public.m_tru') == 5
    plan, outcome = maintain(live, 'truncate', 'table', 'm_tru', values={'cascade': True})
    assert plan['command_preview']['statement'] == 'TRUNCATE TABLE "public"."m_tru" CONTINUE IDENTITY CASCADE'
    assert one('SELECT count(*) FROM public.m_tru') == 0 and one('SELECT count(*) FROM public.m_tru_child') == 0
    query('INSERT INTO public.m_tru (grp) VALUES (1)')
    assert one('SELECT max(id) FROM public.m_tru') == 6  # identity continued
    plan, outcome = maintain(live, 'truncate', 'table', 'm_tru', values={'cascade': True, 'restart_identity': True})
    assert outcome['maintenance_receipt']['options'] == ['RESTART IDENTITY', 'CASCADE']
    query('INSERT INTO public.m_tru (grp) VALUES (1)')
    assert one('SELECT max(id) FROM public.m_tru') == 1  # identity restarted


@live_only
def test_truncate_requires_the_typed_table_name(live):
    provider, route = live
    fresh_table('m_tru2', 3)
    operation = OPERATIONS['truncate@table']
    assert operation['confirmation'] == 'typed_name'
    request = {'resource_kind': 'table', 'operation_id': 'truncate', '_provider_route': route,
               'target_resource': target(None, 'table', {'schema': 'public', 'name': 'm_tru2'}),
               'draft': operation_draft(operation, None, confirmation='wrong')}
    with pytest.raises(Exception, match='confirmation does not match'):
        provider.plan_visual_admin(request)
    request['draft'] = operation_draft(operation, None, confirmation='m_tru2')
    plan = provider.plan_visual_admin(request)
    with pytest.raises(Exception, match='requires confirmation'):
        provider.apply_visual_admin({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'], 'confirmed': False})
    assert one('SELECT count(*) FROM public.m_tru2') == 3


@live_only
def test_refresh_materialized_view(live):
    fresh_table('m_mv_src', 10)
    query('DROP MATERIALIZED VIEW IF EXISTS public.m_mv')
    query('CREATE MATERIALIZED VIEW public.m_mv AS SELECT id, grp FROM public.m_mv_src')
    query('CREATE UNIQUE INDEX m_mv_id ON public.m_mv (id)')
    query('INSERT INTO public.m_mv_src (grp) VALUES (-1)')
    assert one('SELECT count(*) FROM public.m_mv') == 10
    plan, outcome = maintain(live, 'refresh', 'materialized-view', 'm_mv')
    assert plan['command_preview']['statement'] == 'REFRESH MATERIALIZED VIEW "public"."m_mv" WITH DATA'
    assert one('SELECT count(*) FROM public.m_mv') == 11
    query('INSERT INTO public.m_mv_src (grp) VALUES (-2)')
    plan, outcome = maintain(live, 'refresh', 'materialized-view', 'm_mv', values={'concurrently': True})
    assert outcome['maintenance_receipt']['options'] == ['CONCURRENTLY']
    assert one('SELECT count(*) FROM public.m_mv') == 12
    plan, outcome = maintain(live, 'refresh', 'materialized-view', 'm_mv', values={'with_data': False})
    assert one("SELECT relispopulated FROM pg_class WHERE oid = 'public.m_mv'::regclass") is False
    maintain(live, 'refresh', 'materialized-view', 'm_mv')
    assert one('SELECT count(*) FROM public.m_mv') == 12


# -- M4 (2026-11-11): the sequence editor's lifecycle, provider-native, observed live ------------
def sequence_native(schema, name):
    """The target as the provider tree lists it: captured row plus pg_sequence facts."""
    rows = query(f"""SELECT c.relpersistence, c.relacl::text[], d.description,
                            s.seqstart, s.seqincrement, s.seqmin, s.seqmax, s.seqcache, s.seqcycle
                     FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                     JOIN pg_sequence s ON s.seqrelid=c.oid
                     LEFT JOIN pg_description d ON d.objoid=c.oid AND d.classoid='pg_class'::regclass
                     WHERE n.nspname='{schema}' AND c.relname='{name}'""")
    assert len(rows) == 1, (schema, name)
    persistence, acl, comment, start, increment, minimum, maximum, cache, cycle = rows[0]
    return {'schema': schema, 'name': name, 'comment': comment,
            'catalog_row': {'relname': name, 'relpersistence': persistence, 'relacl': acl},
            'children': {'pg_sequence': [{'seqstart': start, 'seqincrement': increment, 'seqmin': minimum,
                                          'seqmax': maximum, 'seqcache': cache, 'seqcycle': cycle}]}}


def run_sequence(live, operation_id, draft, native=None):
    provider, route = live
    resource = target(None, 'sequence', native) if native else None
    request = {'resource_kind': 'sequence', 'operation_id': operation_id, 'target_resource': resource,
               '_provider_route': route, 'draft': draft}
    validation = provider.validate_visual_admin(request)
    assert validation['errors'] == [], (operation_id, validation)
    plan = provider.plan_visual_admin(request)
    assert plan['state'] == 'ready', plan
    assert plan['confirmation_required'] == (operation_id == 'drop'), plan
    result = provider.apply_visual_admin({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'],
                                          'confirmed': True})
    outcome = result['provider_result']
    assert outcome['transaction_outcome'] == 'committed', outcome
    return plan


@pytest.fixture
def sequence_reader():
    reader = 'ui_ops_reader_' + UNIQUE
    query('CREATE SCHEMA "Seq schema"; CREATE TABLE "Seq schema".owner_t (id bigint); '
          f'CREATE ROLE {reader}')
    try:
        yield reader
    finally:
        # The role is cluster-wide; the scratch database goes with the module fixture.
        query('DROP SCHEMA "Seq schema" CASCADE')
        query(f'DROP ROLE {reader}')


@live_only
def test_sequence_lifecycle_round_trips(live, sequence_reader):
    reader = sequence_reader
    plan = run_sequence(live, 'create', {
        'schema': 'Seq schema', 'name': 'ticket no', 'comment': "it's", 'increment': 2, 'start': 10,
        'minimum': 1, 'maximum': 1000, 'cache': 5, 'cycled': True, 'relpersistence': 'logged',
        'owned_table': 'owner_t', 'owned_column': 'id',
        'relacl': [{'grantee': reader, 'privileges': 'rU'}],
        'securities': []})
    assert plan['command_preview']['statement'].startswith('CREATE SEQUENCE "Seq schema"."ticket no"')
    native = sequence_native('Seq schema', 'ticket no')
    assert native['comment'] == "it's"
    assert native['children']['pg_sequence'][0] == {
        'seqstart': 10, 'seqincrement': 2, 'seqmin': 1, 'seqmax': 1000, 'seqcache': 5, 'seqcycle': True}
    assert any(item.startswith(f'{reader}=rU/') for item in native['catalog_row']['relacl'])
    assert query("SELECT refobjsubid FROM pg_depend WHERE objid='\"Seq schema\".\"ticket no\"'::regclass "
                 "AND deptype='a'") == [(1,)]
    # Alter: only the differences run; the unchanged counters stay as they were.
    plan = run_sequence(live, 'alter', {
        'name': 'ticket_number', 'schema': 'Seq schema', 'comment': '', 'current_value': 500,
        # A cleared number never reaches the compiler (the validator drops nulls), so a
        # bound is removed through its flag.
        'increment': 2, 'start': 10, 'minimum': 1, 'maximum': 1000, 'no_maximum': True, 'cache': 5,
        'cycled': False,
        'relpersistence': 'unlogged', 'owned_by_none': True, 'revoke': [{'grantee': reader}],
        'relacl': [{'grantee': reader, 'privileges': 'r', 'with_grant': True}]}, native)
    statement = plan['command_preview']['statement']
    assert 'INCREMENT BY' not in statement and 'NO MAXVALUE NO CYCLE' in statement
    native = sequence_native('Seq schema', 'ticket_number')
    assert native['comment'] is None and native['catalog_row']['relpersistence'] == 'u'
    assert native['children']['pg_sequence'][0]['seqmax'] == 9223372036854775807
    assert native['children']['pg_sequence'][0]['seqcycle'] is False
    assert query("SELECT nextval('\"Seq schema\".ticket_number')") == [(500,)]
    assert query("SELECT count(*) FROM pg_depend WHERE objid='\"Seq schema\".ticket_number'::regclass "
                 "AND deptype='a'") == [(0,)]
    assert [item for item in native['catalog_row']['relacl'] if item.startswith(reader)] == [
        f'{reader}=r*/{SETTINGS["user"]}']
    # Drop needs the typed name and refuses a wrong one before anything runs.
    provider, route = live
    with pytest.raises(Exception):
        run_sequence(live, 'drop', {'confirmation': 'other', 'cascade': False}, native)
    run_sequence(live, 'drop', {'confirmation': 'ticket_number', 'cascade': False}, native)
    assert query("SELECT count(*) FROM pg_class WHERE relname='ticket_number'") == [(0,)]


# -- M4 (2026-11-11): the extension editor's lifecycle, provider-native, observed live -----------
def extension_native(name):
    rows = query(f"""SELECT n.nspname, x.extversion, x.extrelocatable, d.description
                     FROM pg_extension x JOIN pg_namespace n ON n.oid=x.extnamespace
                     LEFT JOIN pg_description d ON d.objoid=x.oid AND d.classoid='pg_extension'::regclass
                     WHERE x.extname='{name}'""")
    assert len(rows) == 1, name
    schema, version, relocatable, comment = rows[0]
    return {'schema': schema, 'name': name, 'comment': comment,
            'catalog_row': {'extname': name, 'extversion': version, 'extrelocatable': relocatable}}


def run_extension(live, operation_id, draft, native=None):
    provider, route = live
    resource = target(None, 'extension', native) if native else None
    request = {'resource_kind': 'extension', 'operation_id': operation_id, 'target_resource': resource,
               '_provider_route': route, 'draft': draft}
    validation = provider.validate_visual_admin(request)
    assert validation['errors'] == [], (operation_id, validation)
    plan = provider.plan_visual_admin(request)
    assert plan['state'] == 'ready', plan
    assert plan['confirmation_required'] == (operation_id == 'drop'), plan
    result = provider.apply_visual_admin({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'],
                                          'confirmed': True})
    assert result['provider_result']['transaction_outcome'] == 'committed', result
    return plan


@live_only
def test_extension_lifecycle_round_trips(live):
    if not query("SELECT 1 FROM pg_available_extensions WHERE name='pg_trgm'"):
        pytest.skip('pg_trgm is not available on this server')
    query('CREATE SCHEMA "Ext schema"; CREATE SCHEMA ext_moved')
    try:
        plan = run_extension(live, 'create', {'name': 'pg_trgm', 'schema': 'Ext schema', 'cascade': False,
                                              'comment': "it's"})
        assert plan['command_preview']['statement'].startswith(
            'CREATE EXTENSION "pg_trgm" WITH SCHEMA "Ext schema"')
        native = extension_native('pg_trgm')
        assert (native['schema'], native['comment']) == ('Ext schema', "it's")
        # Alter: only the schema and comment differ; the version stays (no UPDATE TO in the plan).
        plan = run_extension(live, 'alter', {'schema': 'ext_moved', 'version': native['catalog_row']['extversion'],
                                             'comment': ''}, native)
        assert 'UPDATE TO' not in plan['command_preview']['statement']
        native = extension_native('pg_trgm')
        assert (native['schema'], native['comment']) == ('ext_moved', None)
        with pytest.raises(Exception):
            run_extension(live, 'drop', {'confirmation': 'other', 'cascade': False}, native)
        run_extension(live, 'drop', {'confirmation': 'pg_trgm', 'cascade': False}, native)
        assert query("SELECT count(*) FROM pg_extension WHERE extname='pg_trgm'") == [(0,)]
    finally:
        query('DROP EXTENSION IF EXISTS pg_trgm; DROP SCHEMA "Ext schema" CASCADE; DROP SCHEMA ext_moved CASCADE')


# -- M4 (2026-11-11): the row-security policy editor's lifecycle, provider-native, observed live --
def policy_native(schema, table, name):
    rows = query(f"""SELECT p.polcmd, p.polpermissive, pg_get_expr(p.polqual, p.polrelid), pg_get_expr(p.polwithcheck, p.polrelid),
                            (SELECT array_agg(CASE WHEN r = 0 THEN 'public' ELSE pg_get_userbyid(r) END) FROM unnest(p.polroles) r),
                            d.description, p.polrelid::int
                     FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                     LEFT JOIN pg_description d ON d.objoid=p.oid AND d.classoid='pg_policy'::regclass
                     WHERE n.nspname='{schema}' AND c.relname='{table}' AND p.polname='{name}'""")
    assert len(rows) == 1, (schema, table, name)
    command, permissive, using, check, roles, comment, relid = rows[0]
    from pgadmin.cdeadmin.providers.postgresql.policies import facts
    native = {'schema': schema, 'name': name, 'comment': comment,
              'catalog_row': {'polname': name, 'polrelid': str(relid), 'polcmd': command,
                              'polpermissive': permissive, 'roles_sql': roles, 'using_sql': using,
                              'check_sql': check}}
    native['policy_facts'] = facts(native, {relid: (schema, table)})
    return native


def run_policy(live, operation_id, draft, native=None):
    provider, route = live
    resource = target(None, 'row-policy', native) if native else None
    request = {'resource_kind': 'row-policy', 'operation_id': operation_id, 'target_resource': resource,
               '_provider_route': route, 'draft': draft}
    validation = provider.validate_visual_admin(request)
    assert validation['errors'] == [], (operation_id, validation)
    plan = provider.plan_visual_admin(request)
    assert plan['state'] == 'ready', plan
    assert plan['confirmation_required'] == (operation_id == 'drop'), plan
    result = provider.apply_visual_admin({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'],
                                          'confirmed': True})
    assert result['provider_result']['transaction_outcome'] == 'committed', result
    return plan


@live_only
def test_row_policy_lifecycle_round_trips(live):
    role = 'ui_ops_tenant_' + UNIQUE
    query(f'CREATE SCHEMA "Pol schema"; CREATE TABLE "Pol schema".docs (id int, owner text); '
          f'ALTER TABLE "Pol schema".docs ENABLE ROW LEVEL SECURITY; CREATE ROLE {role}')
    try:
        plan = run_policy(live, 'create', {
            'name': 'own docs', 'schema': 'Pol schema', 'table': 'docs', 'type': 'PERMISSIVE', 'event': 'UPDATE',
            'policyowner': role, 'using': 'owner = CURRENT_USER', 'withcheck': 'id > 0',
            'description': "it's"})
        assert plan['command_preview']['statement'].startswith('CREATE POLICY "own docs" ON "Pol schema"."docs"')
        native = policy_native('Pol schema', 'docs', 'own docs')
        assert native['policy_facts']['event'] == 'UPDATE' and native['policy_facts']['type'] == 'PERMISSIVE'
        assert native['policy_facts']['roles'] == [role]
        assert native['policy_facts']['using'] == '(owner = CURRENT_USER)' and native['comment'] == "it's"
        # Alter: roles widened to PUBLIC (PostgreSQL stores a list with PUBLIC as PUBLIC alone),
        # USING changed, comment cleared, renamed; AS and FOR untouched.
        plan = run_policy(live, 'alter', {
            'name': 'mine', 'policyowner': 'public', 'using': 'owner = CURRENT_USER AND id <> 0',
            'withcheck': '(id > 0)', 'description': ''}, native)
        assert 'WITH CHECK' not in plan['command_preview']['statement']
        native = policy_native('Pol schema', 'docs', 'mine')
        assert native['policy_facts']['roles'] == ['public'] and native['comment'] is None
        assert native['policy_facts']['using'] == '((owner = CURRENT_USER) AND (id <> 0))'
        with pytest.raises(Exception):
            run_policy(live, 'drop', {'confirmation': 'other'}, native)
        run_policy(live, 'drop', {'confirmation': 'mine'}, native)
        assert query("SELECT count(*) FROM pg_policy WHERE polname='mine'") == [(0,)]
    finally:
        query(f'DROP SCHEMA "Pol schema" CASCADE; DROP ROLE {role}')


# -- M4 (2026-11-11): the schema editor's lifecycle, provider-native, observed live --------------
def schema_native(name):
    rows = query(f"""SELECT pg_get_userbyid(n.nspowner), n.nspacl::text[], d.description
                     FROM pg_namespace n LEFT JOIN pg_description d ON d.objoid=n.oid AND d.classoid='pg_namespace'::regclass
                     WHERE n.nspname='{name}'""")
    assert len(rows) == 1, name
    owner, acl, comment = rows[0]
    native = {'schema': name, 'name': name, 'comment': comment,
              'catalog_row': {'nspname': name, 'nspacl': acl}}
    native['owner'] = owner
    return native


def run_schema(live, operation_id, draft, native=None):
    provider, route = live
    resource = target(None, 'schema', native) if native else None
    request = {'resource_kind': 'schema', 'operation_id': operation_id, 'target_resource': resource,
               '_provider_route': route, 'draft': draft}
    validation = provider.validate_visual_admin(request)
    assert validation['errors'] == [], (operation_id, validation)
    plan = provider.plan_visual_admin(request)
    assert plan['state'] == 'ready', plan
    assert plan['confirmation_required'] == (operation_id == 'drop'), plan
    result = provider.apply_visual_admin({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'],
                                          'confirmed': True})
    assert result['provider_result']['transaction_outcome'] == 'committed', result
    return plan


@live_only
def test_schema_lifecycle_round_trips(live):
    owner, reader = 'ui_ops_owner_' + UNIQUE, 'ui_ops_reader_' + UNIQUE
    query(f'CREATE ROLE {owner}; CREATE ROLE {reader}')
    try:
        plan = run_schema(live, 'create', {
            'name': 'Sch ema', 'namespaceowner': owner, 'description': "it's",
            'nspacl': [{'grantee': reader, 'privileges': 'U'}],
            'default_privileges': [{'object_type': 'TABLES', 'grantee': reader, 'privileges': 'SELECT'}],
            'seclabels': []})
        assert plan['command_preview']['statement'].startswith('CREATE SCHEMA "Sch ema" AUTHORIZATION')
        native = schema_native('Sch ema')
        assert (native['owner'], native['comment']) == (owner, "it's")
        assert any(item.startswith(f'{reader}=U/') for item in native['catalog_row']['nspacl'])
        # The default privilege is recorded for the schema, granted by the connected user.
        assert query(f"""SELECT count(*) FROM pg_default_acl a JOIN pg_namespace n ON n.oid=a.defaclnamespace
                         WHERE n.nspname='Sch ema' AND a.defaclobjtype='r'""") == [(1,)]
        plan = run_schema(live, 'alter', {
            'name': 'schema_two', 'namespaceowner': '', 'description': '',
            'revoke': [{'grantee': reader}], 'nspacl': [{'grantee': reader, 'privileges': 'UC'}],
            'default_revoke': [{'object_type': 'TABLES', 'grantee': reader}]}, native)
        assert 'OWNER TO' not in plan['command_preview']['statement']
        native = schema_native('schema_two')
        assert (native['owner'], native['comment']) == (owner, None)
        assert any(item.startswith(f'{reader}=UC/') for item in native['catalog_row']['nspacl'])
        assert query(f"""SELECT count(*) FROM pg_default_acl a JOIN pg_namespace n ON n.oid=a.defaclnamespace
                         WHERE n.nspname='schema_two'""") == [(0,)]
        with pytest.raises(Exception):
            run_schema(live, 'drop', {'confirmation': 'other', 'cascade': False}, native)
        run_schema(live, 'drop', {'confirmation': 'schema_two', 'cascade': True}, native)
        assert query("SELECT count(*) FROM pg_namespace WHERE nspname IN ('Sch ema', 'schema_two')") == [(0,)]
    finally:
        query('DROP SCHEMA IF EXISTS "Sch ema" CASCADE; DROP SCHEMA IF EXISTS schema_two CASCADE')
        query(f'DROP OWNED BY {owner}, {reader}; DROP ROLE {owner}; DROP ROLE {reader}')


# -- M4 (2026-11-11): database create and alter from the server scope, provider-native, live -----
def database_native(name):
    rows = query(f"""SELECT d.oid::int, t.spcname, d.datallowconn, d.datistemplate, pg_get_userbyid(d.datdba),
                            d.datconnlimit, s.description, d.datacl::text[]
                     FROM pg_database d JOIN pg_tablespace t ON t.oid=d.dattablespace
                     LEFT JOIN pg_shdescription s ON s.objoid=d.oid AND s.classoid='pg_database'::regclass
                     WHERE d.datname='{name}'""")
    assert len(rows) == 1, name
    did, spcname, allow, template, owner, limit, comment, acl = rows[0]
    from pgadmin.cdeadmin.providers.postgresql.databases import facts
    native = {'name': name, 'catalog_metadata': {'did': did, 'name': name, 'spcname': spcname,
                                                 'datallowconn': allow, 'is_template': template,
                                                 'description': comment}, 'catalog_row': {'datconnlimit': limit}}
    native['database_facts'] = facts(native)
    native.update(owner=owner, acl=acl or [])
    return native


def run_database(live, operation_id, draft, native=None, confirmation_required=False):
    provider, _route = live
    # Server scope: the route names the server only; the attachment is the maintenance database.
    resource = target(None, 'database', native) if native else None
    request = {'resource_kind': 'database', 'operation_id': operation_id, 'target_resource': resource,
               '_provider_route': {'server_id': 1}, 'draft': draft}
    validation = provider.validate_visual_admin(request)
    assert validation['errors'] == [], (operation_id, validation)
    plan = provider.plan_visual_admin(request)
    assert plan['state'] == 'ready', plan
    assert plan['confirmation_required'] is confirmation_required, plan
    result = provider.apply_visual_admin({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'],
                                          'confirmed': True})
    assert result['provider_result']['transaction_outcome'] == 'committed', result
    return plan


@live_only
def test_database_create_and_alter_round_trip(live):
    owner, reader = 'ui_ops_dbowner_' + UNIQUE, 'ui_ops_dbreader_' + UNIQUE
    name = f'ui_ops_created_{UNIQUE}'
    query(f'CREATE ROLE {owner}; CREATE ROLE {reader}')
    try:
        plan = run_database(live, 'create', {
            'name': name, 'datowner': owner, 'template': 'template0', 'encoding': 'UTF8',
            'datlocaleprovider': 'libc', 'datcollate': 'C', 'datctype': 'C', 'datconnlimit': 7,
            'datallowconn': True, 'is_template': False})
        assert plan['command_preview']['statement'].startswith(f'CREATE DATABASE "{name}" WITH OWNER')
        native = database_native(name)
        assert (native['owner'], native['database_facts']['datconnlimit']) == (owner, 7)
        plan = run_database(live, 'alter', {
            'name': name, 'spcname': native['database_facts']['spcname'], 'datconnlimit': 3,
            'datallowconn': True, 'is_template': False, 'comments': "it's",
            # A grant to the owner folds into the owner's implicit full entry; grant to another role.
            'datacl': [{'grantee': reader, 'privileges': 'c'}]}, native)
        assert 'RENAME' not in plan['command_preview']['statement']
        native = database_native(name)
        assert (native['database_facts']['datconnlimit'], native['database_facts']['comments']) == (3, "it's")
        assert any(item.startswith(f'{reader}=c/') for item in native['acl'])
        # A tablespace change runs alone in autocommit (same tablespace name: the server accepts a no-op move
        # only for a different one, so this checks the plan shape with pg_default -> pg_default refused by us).
        with pytest.raises(Exception):
            run_database(live, 'alter', {'spcname': 'pg_default', 'comments': 'x'}, dict(
                native, database_facts=dict(native['database_facts'], spcname='other')))
        # Rename runs from the maintenance database, which is not the renamed one.
        run_database(live, 'alter', {'name': name + '_r'}, native)
        assert query(f"SELECT count(*) FROM pg_database WHERE datname='{name}_r'") == [(1,)]
    finally:
        query(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        query(f'DROP DATABASE IF EXISTS "{name}_r" WITH (FORCE)')
        query(f'DROP ROLE {owner}; DROP ROLE {reader}')


# -- M4 (2026-11-11): domain and type editors, provider-native, observed live ---------------------
def run_kind(live, kind, operation_id, draft, native=None):
    provider, route = live
    resource = target(None, kind, native) if native else None
    request = {'resource_kind': kind, 'operation_id': operation_id, 'target_resource': resource,
               '_provider_route': route, 'draft': draft}
    validation = provider.validate_visual_admin(request)
    assert validation['errors'] == [], (kind, operation_id, validation)
    plan = provider.plan_visual_admin(request)
    assert plan['state'] == 'ready', plan
    result = provider.apply_visual_admin({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'],
                                          'confirmed': True})
    assert result['provider_result']['transaction_outcome'] == 'committed', result
    return plan


def domain_native(schema, name):
    from pgadmin.cdeadmin.providers.postgresql.types import domain_facts
    rows = query(f"""SELECT t.oid::int, t.typnotnull, t.typdefault, d.description
                     FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
                     LEFT JOIN pg_description d ON d.objoid=t.oid AND d.classoid='pg_type'::regclass
                     WHERE n.nspname='{schema}' AND t.typname='{name}' AND t.typtype='d'""")
    assert len(rows) == 1, (schema, name)
    oid, notnull, default, comment = rows[0]
    checks = query(f"""SELECT conname, pg_get_constraintdef(oid), convalidated FROM pg_constraint
                       WHERE contypid={oid} AND contype='c' ORDER BY conname""")
    native = {'schema': schema, 'name': name, 'oid': oid, 'comment': comment,
              'catalog_row': {'typname': name, 'typtype': 'd', 'typnotnull': notnull, 'typdefault': default}}
    native['domain_facts'] = domain_facts(native, {oid: [
        {'name': c[0], 'definition': c[1], 'catalog_row': {'convalidated': c[2]}} for c in checks]})
    return native


def type_native(schema, name):
    from pgadmin.cdeadmin.providers.postgresql.types import type_facts
    rows = query(f"""SELECT t.oid::int, t.typtype, t.typrelid::int, d.description
                     FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
                     LEFT JOIN pg_description d ON d.objoid=t.oid AND d.classoid='pg_type'::regclass
                     WHERE n.nspname='{schema}' AND t.typname='{name}'""")
    assert len(rows) == 1, (schema, name)
    oid, typtype, relid, comment = rows[0]
    labels = query(f'SELECT enumlabel, enumsortorder FROM pg_enum WHERE enumtypid={oid}')
    attributes = query(f"""SELECT attname, format_type(atttypid, atttypmod), attisdropped FROM pg_attribute
                           WHERE attrelid={relid} AND attnum > 0 ORDER BY attnum""") if relid else []
    native = {'schema': schema, 'name': name, 'oid': oid, 'comment': comment,
              'catalog_row': {'typname': name, 'typtype': typtype, 'typrelid': str(relid)},
              'children': {'pg_enum': [{'enumlabel': l, 'enumsortorder': o} for l, o in labels]}}
    native['type_facts'] = type_facts(native, {relid: [
        {'attname': a, 'formatted_type': t, 'attisdropped': d} for a, t, d in attributes]})
    return native


@live_only
def test_domain_lifecycle_round_trips(live):
    query('CREATE SCHEMA "Dom schema"')
    try:
        run_kind(live, 'domain', 'create', {
            'name': 'pos code', 'basensp': 'Dom schema', 'basetype': 'varchar(10)', 'collname': '"C"',
            'typdefault': "'x'", 'typnotnull': True, 'description': "it's",
            'constraints': [{'conname': 'not blank', 'consrc': "VALUE <> ''", 'convalidated': False}]})
        native = domain_native('Dom schema', 'pos code')
        facts = native['domain_facts']
        assert (facts['typnotnull'], facts['typdefault'], native['comment']) == (True, "'x'::character varying", "it's")
        assert facts['constraints'] == [{'conname': 'not blank', 'consrc': "((VALUE)::text <> ''::text)",
                                         'convalidated': False}]
        plan = run_kind(live, 'domain', 'alter', {
            'name': 'code', 'basensp': 'Dom schema', 'typnotnull': False, 'typdefault': '',
            'description': '', 'validate_constraints': [{'conname': 'not blank'}],
            'add_constraints': [{'conname': 'short', 'consrc': 'length(VALUE) < 9'}],
            'rename_constraints': [{'conname': 'not blank', 'to': 'not_blank'}]}, native)
        assert 'SET SCHEMA' not in plan['command_preview']['statement']
        native = domain_native('Dom schema', 'code')
        facts = native['domain_facts']
        assert (facts['typnotnull'], facts['typdefault'], native['comment']) == (False, None, None)
        assert [(c['conname'], c['convalidated']) for c in facts['constraints']] == [
            ('not_blank', True), ('short', True)]
        run_kind(live, 'domain', 'drop', {'confirmation': 'code', 'cascade': False}, native)
        assert query("SELECT count(*) FROM pg_type WHERE typname='code'") == [(0,)]
    finally:
        query('DROP SCHEMA "Dom schema" CASCADE')


@live_only
def test_type_lifecycle_round_trips(live):
    query('CREATE SCHEMA typ_schema')
    try:
        run_kind(live, 'type', 'create', {'name': 'mood', 'schema': 'typ_schema', 'typtype': 'e',
                                         'enum': [{'label': 'sad'}, {'label': 'ok'}], 'description': 'how'})
        native = type_native('typ_schema', 'mood')
        assert [item['label'] for item in native['type_facts']['enum']] == ['sad', 'ok']
        # Enum: rename and add values (ADD VALUE commits with the transaction in PostgreSQL 12+).
        run_kind(live, 'type', 'alter', {
            'rename_values': [{'from': 'ok', 'to': 'fine'}],
            'add_values': [{'label': 'great', 'after': 'fine'}, {'label': 'awful', 'before': 'sad'}],
            'description': '', 'name': 'feeling'}, native)
        native = type_native('typ_schema', 'feeling')
        assert [item['label'] for item in sorted(native['type_facts']['enum'], key=lambda i: i['label'])] == \
            ['awful', 'fine', 'great', 'sad']
        assert query("SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid "
                     "WHERE t.typname='feeling' ORDER BY enumsortorder") == [('awful',), ('sad',), ('fine',), ('great',)]
        run_kind(live, 'type', 'create', {'name': 'addr', 'schema': 'typ_schema', 'typtype': 'c',
                                         'composite': [{'member_name': 'street', 'type': 'text'},
                                                       {'member_name': 'zip', 'type': 'varchar(10)'}]})
        native = type_native('typ_schema', 'addr')
        run_kind(live, 'type', 'alter', {
            'drop_attributes': [{'member_name': 'zip'}],
            'rename_attributes': [{'member_name': 'street', 'to': 'road'}],
            'alter_attributes': [{'member_name': 'road', 'type': 'varchar(80)'}],
            'add_attributes': [{'member_name': 'city', 'type': 'text'}]}, native)
        native = type_native('typ_schema', 'addr')
        assert native['type_facts']['composite'] == [{'member_name': 'road', 'type': 'character varying(80)'},
                                                     {'member_name': 'city', 'type': 'text'}]
        run_kind(live, 'type', 'create', {'name': 'floatrange', 'schema': 'typ_schema', 'typtype': 'r',
                                         'typname': 'float8', 'rngsubdiff': 'float8mi'})
        assert query("SELECT count(*) FROM pg_range r JOIN pg_type t ON t.oid=r.rngtypid WHERE t.typname='floatrange'") == [(1,)]
        with pytest.raises(Exception):
            run_kind(live, 'type', 'drop', {'confirmation': 'other'}, native)
        run_kind(live, 'type', 'drop', {'confirmation': 'addr'}, native)
        assert query("SELECT count(*) FROM pg_type WHERE typname='addr'") == [(0,)]
    finally:
        query('DROP SCHEMA typ_schema CASCADE')


# -- M4 (2026-11-11): view and materialized view editors, provider-native, observed live ----------
def view_native(schema, name):
    from pgadmin.cdeadmin.providers.postgresql.views import facts
    rows = query(f"""SELECT c.relkind, c.reloptions::text[], c.relispopulated, pg_get_viewdef(c.oid), d.description,
                            pg_get_userbyid(c.relowner)
                     FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                     LEFT JOIN pg_description d ON d.objoid=c.oid AND d.classoid='pg_class'::regclass AND d.objsubid=0
                     WHERE n.nspname='{schema}' AND c.relname='{name}'""")
    assert len(rows) == 1, (schema, name)
    relkind, options, populated, definition, comment, owner = rows[0]
    native = {'schema': schema, 'name': name, 'comment': comment, 'definition': definition,
              'catalog_row': {'relname': name, 'relkind': relkind, 'reloptions': options,
                              'relispopulated': populated}}
    native['view_facts'] = facts(native)
    native['owner'] = owner
    return native


@live_only
def test_view_lifecycle_round_trips(live):
    query('CREATE SCHEMA "View schema"; CREATE TABLE "View schema".t (id int, owner text)')
    try:
        run_kind(live, 'view', 'create', {
            'name': 'mine', 'schema': 'View schema', 'definition': 'SELECT id, owner FROM "View schema".t',
            'check_option': 'local', 'security_barrier': True, 'security_invoker': False, 'comment': "it's"})
        native = view_native('View schema', 'mine')
        facts = native['view_facts']
        assert (facts['check_option'], facts['security_barrier'], native['comment']) == ('local', True, "it's")
        plan = run_kind(live, 'view', 'alter', {
            'name': 'mine', 'schema': 'View schema', 'definition': facts['definition'],
            'check_option': 'no', 'security_barrier': False, 'security_invoker': True, 'comment': ''}, native)
        assert 'CREATE OR REPLACE' not in plan['command_preview']['statement']
        native = view_native('View schema', 'mine')
        facts = native['view_facts']
        assert (facts['check_option'], facts['security_barrier'], facts['security_invoker'], native['comment']) == (
            'no', False, True, None)
        # CREATE OR REPLACE VIEW may add columns at the end but never drop or reorder them (server rule).
        run_kind(live, 'view', 'alter', {
            'name': 'ours', 'definition': 'SELECT id, owner, id > 0 AS positive FROM "View schema".t',
            'check_option': 'cascaded'}, native)
        native = view_native('View schema', 'ours')
        assert native['view_facts']['check_option'] == 'cascaded' and 'positive' in native['view_facts']['definition']
        run_kind(live, 'view', 'drop', {'confirmation': 'ours'}, native)
        assert query("SELECT count(*) FROM pg_class WHERE relname='ours'") == [(0,)]
        # Materialized view: created without data, fill factor set, query replaced by drop and create.
        run_kind(live, 'materialized-view', 'create', {
            'name': 'load', 'schema': 'View schema', 'definition': 'SELECT count(*) AS n FROM "View schema".t',
            'with_data': False, 'fillfactor': 80})
        native = view_native('View schema', 'load')
        assert (native['view_facts']['with_data'], native['view_facts']['fillfactor']) == (False, 80)
        run_kind(live, 'materialized-view', 'alter', {'fillfactor': 80, 'reset_fillfactor': True, 'comment': 'rows'},
                 native)
        native = view_native('View schema', 'load')
        assert (native['view_facts']['fillfactor'], native['comment']) == (None, 'rows')
        run_kind(live, 'materialized-view', 'alter', {
            'definition': 'SELECT count(*) AS n, max(id) AS top FROM "View schema".t', 'with_data': True}, native)
        native = view_native('View schema', 'load')
        assert native['view_facts']['with_data'] is True and 'max(id)' in native['view_facts']['definition']
        run_kind(live, 'materialized-view', 'drop', {'confirmation': 'load'}, native)
        assert query("SELECT count(*) FROM pg_class WHERE relname='load'") == [(0,)]
    finally:
        query('DROP SCHEMA "View schema" CASCADE')


# -- M4 (2026-11-11): function and procedure editors, provider-native, observed live --------------
def routine_native(schema, name):
    from pgadmin.cdeadmin.providers.postgresql.routines import facts
    rows = query(f"""SELECT p.oid::int, pg_get_functiondef(p.oid), p.prokind, d.description,
                            (pg_identify_object('pg_proc'::regclass, p.oid, 0)).identity, p.provolatile,
                            p.proisstrict, p.prosecdef, p.proleakproof, p.proparallel, p.procost, p.prorows,
                            pg_get_userbyid(p.proowner)
                     FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                     LEFT JOIN pg_description d ON d.objoid=p.oid AND d.classoid='pg_proc'::regclass
                     WHERE n.nspname='{schema}' AND p.proname='{name}'""")
    assert len(rows) == 1, (schema, name)
    (oid, definition, kind, comment, identity, volatile, strict, secdef, leakproof, parallel, cost, prorows,
     owner) = rows[0]
    native = {'schema': schema, 'name': name, 'comment': comment, 'definition': definition,
              'sql_identity': identity,
              'catalog_row': {'proname': name, 'prokind': kind, 'provolatile': volatile, 'proisstrict': strict,
                              'prosecdef': secdef, 'proleakproof': leakproof, 'proparallel': parallel,
                              'procost': cost, 'prorows': prorows}}
    native['routine_facts'] = facts(native)
    native['owner'] = owner
    return native


@live_only
def test_routine_lifecycle_round_trips(live):
    query('CREATE SCHEMA "Fn schema"')
    try:
        run_kind(live, 'function', 'create', {
            'name': 'is big', 'pronamespace': 'Fn schema',
            'arguments': [{'argmode': 'IN', 'argname': 'n', 'argtype': 'integer', 'argdefval': '0'}],
            'prorettypename': 'boolean', 'lanname': 'sql', 'prosrc': 'SELECT n > 10',
            'provolatile': 'IMMUTABLE', 'proisstrict': True, 'proparallel': 'SAFE', 'procost': 10,
            'variables': [{'name': 'search_path', 'value': 'public, pg_temp'}], 'description': "it's"})
        native = routine_native('Fn schema', 'is big')
        facts = native['routine_facts']
        assert facts['definition_parsed'] and facts['arguments'][0]['argdefval'] == '0'
        assert (facts['provolatile'], facts['proisstrict'], facts['procost'], native['comment']) == (
            'IMMUTABLE', True, 10, "it's")
        assert query("SELECT \"Fn schema\".\"is big\"(11)") == [(True,)]
        # Body and options change through CREATE OR REPLACE with the same signature; then rename.
        run_kind(live, 'function', 'alter', {
            'arguments': facts['arguments'], 'prorettypename': facts['prorettypename'],
            'prosrc': 'SELECT n > 100', 'provolatile': 'STABLE', 'proisstrict': False, 'description': ''},
            native)
        native = routine_native('Fn schema', 'is big')
        assert (native['routine_facts']['provolatile'], native['routine_facts']['proisstrict'],
                native['comment']) == ('STABLE', False, None)
        assert query("SELECT \"Fn schema\".\"is big\"(11)") == [(False,)]
        run_kind(live, 'function', 'alter', {'name': 'is_huge'}, native)
        native = routine_native('Fn schema', 'is_huge')
        assert native['routine_facts']['sql_identity'].endswith('(integer)')
        run_kind(live, 'procedure', 'create', {
            'name': 'bump', 'pronamespace': 'Fn schema', 'lanname': 'plpgsql',
            'arguments': [{'argmode': 'INOUT', 'argname': 'x', 'argtype': 'integer'}],
            'prosrc': 'begin x := x + 1; end'})
        assert query('CALL "Fn schema".bump(41)') == [(42,)]
        procedure = routine_native('Fn schema', 'bump')
        run_kind(live, 'procedure', 'alter', {'prosrc': 'begin x := x + 2; end'}, procedure)
        assert query('CALL "Fn schema".bump(40)') == [(42,)]
        with pytest.raises(Exception):
            run_kind(live, 'function', 'drop', {'confirmation': 'other'}, native)
        run_kind(live, 'function', 'drop', {'confirmation': 'is_huge'}, native)
        run_kind(live, 'procedure', 'drop', {'confirmation': 'bump'}, procedure)
        assert query("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                     "WHERE n.nspname='Fn schema'") == [(0,)]
    finally:
        query('DROP SCHEMA "Fn schema" CASCADE')


# -- M4 (2026-11-11): index editor, provider-native, observed live --------------------------------
def index_native(schema, name):
    from pgadmin.cdeadmin.providers.postgresql.indexes import facts
    rows = query(f"""SELECT pg_get_indexdef(c.oid), d.description
                     FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                     LEFT JOIN pg_description d ON d.objoid=c.oid AND d.classoid='pg_class'::regclass
                     WHERE n.nspname='{schema}' AND c.relname='{name}' AND c.relkind='i'""")
    assert len(rows) == 1, (schema, name)
    native = {'schema': schema, 'name': name, 'comment': rows[0][1], 'definition': rows[0][0],
              'catalog_row': {'relname': name}}
    native['index_facts'] = facts(native)
    return native


@live_only
def test_index_lifecycle_round_trips(live):
    query('CREATE SCHEMA "Ix schema"; CREATE TABLE "Ix schema".orders (id int, email text, status text, '
          'priority int, note text)')
    try:
        run_kind(live, 'index', 'create', {
            'name': 'ix one', 'schema': 'Ix schema', 'table': 'orders', 'amname': 'btree', 'indisunique': True,
            'indnullsnotdistinct': True,
            'columns': [{'colname': 'lower(email)', 'is_exp': True, 'collspcname': '"C"',
                         'op_class': 'text_pattern_ops', 'sort_order': 'DESC', 'nulls': 'FIRST'},
                        {'colname': 'status'}],
            'include': [{'colname': 'note'}], 'fillfactor': 70, 'description': "it's"})
        native = index_native('Ix schema', 'ix one')
        facts = native['index_facts']
        assert (facts['indisunique'], facts['indnullsnotdistinct'], facts['include'], native['comment']) == (
            True, True, ['note'], "it's")
        assert facts['columns'][0]['sort_order'] == 'DESC' and facts['columns'][0]['is_exp']
        assert facts['storage_parameters'] == [{'name': 'fillfactor', 'value': '70'}]
        run_kind(live, 'index', 'alter', {
            'name': 'ix_two', 'columns': facts['columns'], 'fillfactor': 90,
            'storage_parameters': [{'name': 'deduplicate_items', 'value': False}],
            'indisclustered': True, 'description': ''}, native)
        native = index_native('Ix schema', 'ix_two')
        assert sorted(item['name'] for item in native['index_facts']['storage_parameters']) == [
            'deduplicate_items', 'fillfactor']
        assert native['comment'] is None
        assert query("SELECT indisclustered FROM pg_index WHERE indexrelid='\"Ix schema\".ix_two'::regclass") == [(True,)]
        run_kind(live, 'index', 'alter', {'reset_parameters': [{'name': 'deduplicate_items'}]}, native)
        native = index_native('Ix schema', 'ix_two')
        assert [item['name'] for item in native['index_facts']['storage_parameters']] == ['fillfactor']
        # A BRIN index, which YugabyteDB refuses, and a concurrent build and drop in autocommit.
        # The predicate goes on the BRIN index: the server refuses CLUSTER on a partial index.
        run_kind(live, 'index', 'create', {'name': 'ix_brin', 'schema': 'Ix schema', 'table': 'orders',
                                           'amname': 'brin', 'columns': [{'colname': 'id'}],
                                           'storage_parameters': [{'name': 'pages_per_range', 'value': 32}],
                                           'indconstraint': 'priority > 1'})
        brin = index_native('Ix schema', 'ix_brin')['index_facts']
        assert (brin['amname'], brin['indconstraint']) == ('brin', 'priority > 1')
        run_kind(live, 'index', 'create', {'name': 'ix_conc', 'schema': 'Ix schema', 'table': 'orders',
                                           'isconcurrent': True, 'columns': [{'colname': 'priority'}]})
        conc = index_native('Ix schema', 'ix_conc')
        run_kind(live, 'index', 'drop', {'confirmation': 'ix_conc', 'concurrently': True}, conc)
        with pytest.raises(Exception):
            run_kind(live, 'index', 'drop', {'confirmation': 'other'}, native)
        run_kind(live, 'index', 'drop', {'confirmation': 'ix_two'}, native)
        assert query("SELECT count(*) FROM pg_class WHERE relname IN ('ix_two', 'ix_conc')") == [(0,)]
    finally:
        query('DROP SCHEMA "Ix schema" CASCADE')


# -- M4 (2026-11-11): trigger, event trigger and rule editors, provider-native, observed live -----
def trigger_native(schema, table, name):
    from pgadmin.cdeadmin.providers.postgresql.triggers import trigger_facts
    rows = query(f"""SELECT pg_get_triggerdef(t.oid), t.tgenabled, t.tgisinternal, d.description
                     FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                     LEFT JOIN pg_description d ON d.objoid=t.oid AND d.classoid='pg_trigger'::regclass
                     WHERE n.nspname='{schema}' AND c.relname='{table}' AND t.tgname='{name}'""")
    assert len(rows) == 1, (schema, table, name)
    definition, enabled, internal, comment = rows[0]
    native = {'schema': schema, 'name': name, 'comment': comment, 'definition': definition,
              'catalog_row': {'tgname': name, 'tgenabled': enabled, 'tgisinternal': internal}}
    native['trigger_facts'] = trigger_facts(native)
    return native


def rule_native(schema, table, name):
    from pgadmin.cdeadmin.providers.postgresql.triggers import rule_facts
    rows = query(f"""SELECT pg_get_ruledef(r.oid), r.ev_enabled, r.is_instead, d.description
                     FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class JOIN pg_namespace n ON n.oid=c.relnamespace
                     LEFT JOIN pg_description d ON d.objoid=r.oid AND d.classoid='pg_rewrite'::regclass
                     WHERE n.nspname='{schema}' AND c.relname='{table}' AND r.rulename='{name}'""")
    assert len(rows) == 1, (schema, table, name)
    definition, enabled, instead, comment = rows[0]
    native = {'schema': schema, 'name': name, 'comment': comment, 'definition': definition,
              'catalog_row': {'rulename': name, 'ev_enabled': enabled, 'is_instead': instead}}
    native['rule_facts'] = rule_facts(native)
    return native


def event_trigger_native(name):
    from pgadmin.cdeadmin.providers.postgresql.triggers import event_trigger_facts
    rows = query(f"""SELECT e.evtevent, e.evttags, e.evtenabled, d.description, e.evtfoid::regproc::text
                     FROM pg_event_trigger e LEFT JOIN pg_description d ON d.objoid=e.oid
                     AND d.classoid='pg_event_trigger'::regclass WHERE e.evtname='{name}'""")
    assert len(rows) == 1, name
    event, tags, enabled, comment, function = rows[0]
    native = {'name': name, 'comment': comment,
              'catalog_row': {'evtname': name, 'evtevent': event, 'evttags': tags, 'evtenabled': enabled}}
    native['event_trigger_facts'] = event_trigger_facts(native)
    native['function'] = function
    return native


@live_only
def test_trigger_and_rule_lifecycles_round_trip(live):
    query('CREATE SCHEMA "Tr schema"; CREATE TABLE "Tr schema".orders (id int, status text); '
          'CREATE TABLE "Tr schema".log (note text); '
          'CREATE FUNCTION "Tr schema".log_it() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN '
          "INSERT INTO \"Tr schema\".log VALUES (TG_ARGV[0]); RETURN NEW; END $$")
    try:
        run_kind(live, 'trigger', 'create', {
            # A transition table is allowed with one event only (server rule).
            'name': 'audit', 'schema': 'Tr schema', 'table': 'orders', 'fires': 'AFTER',
            'evnt_insert': True, 'is_row_trigger': True, 'tgnewtable': 'newrows', 'whenclause': 'new.id > 0',
            'tfunction': '"Tr schema".log_it', 'tgargs': 'first', 'description': "it's"})
        native = trigger_native('Tr schema', 'orders', 'audit')
        facts = native['trigger_facts']
        assert (facts['evnt_insert'], facts['evnt_update'], facts['tgnewtable'], facts['tgargs'],
                native['comment']) == (True, False, 'newrows', 'first', "it's")
        query('INSERT INTO "Tr schema".orders VALUES (1, \'new\')')
        assert query('SELECT note FROM "Tr schema".log') == [('first',)]
        # CREATE OR REPLACE with the same name: add UPDATE OF status, drop the transition table, disable, rename.
        run_kind(live, 'trigger', 'alter', {
            'evnt_update': True, 'columns': [{'column': 'status'}], 'tgnewtable': '', 'tgargs': 'second',
            'is_enable_trigger': 'D', 'description': '', 'name': 'audit_rows'}, native)
        native = trigger_native('Tr schema', 'orders', 'audit_rows')
        facts = native['trigger_facts']
        assert (facts['evnt_update'], facts['columns'], facts['tgnewtable'], facts['tgargs'],
                facts['is_enable_trigger'], native['comment']) == (True, ['status'], None, 'second', 'D', None)
        query('INSERT INTO "Tr schema".orders VALUES (2, \'new\')')
        assert query('SELECT count(*) FROM "Tr schema".log') == [(1,)]
        run_kind(live, 'trigger', 'create', {
            'name': 'check_it', 'schema': 'Tr schema', 'table': 'orders', 'is_constraint_trigger': True,
            'fires': 'AFTER', 'evnt_delete': True, 'tgdeferrable': True, 'tginitdeferred': True,
            'is_row_trigger': True, 'tfunction': '"Tr schema".log_it', 'tgargs': 'c'})
        constraint = trigger_native('Tr schema', 'orders', 'check_it')
        assert (constraint['trigger_facts']['is_constraint_trigger'], constraint['trigger_facts']['tginitdeferred']) \
            == (True, True)
        run_kind(live, 'trigger', 'alter', {'tginitdeferred': False}, constraint)
        assert trigger_native('Tr schema', 'orders', 'check_it')['trigger_facts']['tginitdeferred'] is False
        run_kind(live, 'trigger', 'drop', {'confirmation': 'audit_rows'}, native)
        # Rules: a DO ALSO rule on UPDATE, then replaced, disabled and renamed.
        run_kind(live, 'rule', 'create', {
            'name': 'log_updates', 'schema': 'Tr schema', 'view': 'orders', 'event': 'UPDATE',
            'do_instead': False, 'condition': 'old.status <> new.status',
            'statements': 'INSERT INTO "Tr schema".log VALUES (\'rule\')', 'comment': 'log'})
        rule = rule_native('Tr schema', 'orders', 'log_updates')
        assert (rule['rule_facts']['event'], rule['rule_facts']['do_instead'], rule['comment']) == (
            'UPDATE', False, 'log')
        query('UPDATE "Tr schema".orders SET status = \'done\' WHERE id = 1')
        assert query("SELECT count(*) FROM \"Tr schema\".log WHERE note='rule'") == [(1,)]
        run_kind(live, 'rule', 'alter', {'statements': 'NOTHING', 'do_instead': True, 'is_enable_rule': 'D',
                                         'comment': '', 'name': 'ignore_updates'}, rule)
        rule = rule_native('Tr schema', 'orders', 'ignore_updates')
        assert (rule['rule_facts']['statements'], rule['rule_facts']['do_instead'],
                rule['rule_facts']['is_enable_rule']) == ('NOTHING', True, 'D')
        run_kind(live, 'rule', 'drop', {'confirmation': 'ignore_updates'}, rule)
        assert query("SELECT count(*) FROM pg_rewrite WHERE rulename='ignore_updates'") == [(0,)]
    finally:
        query('DROP SCHEMA "Tr schema" CASCADE')


@live_only
def test_event_trigger_lifecycle_round_trips(live):
    if query("SELECT rolsuper FROM pg_roles WHERE rolname=current_user") != [(True,)]:
        pytest.skip('event triggers need a superuser')
    query("CREATE FUNCTION public.ui_ops_note() RETURNS event_trigger LANGUAGE plpgsql AS $$ BEGIN "
          "RAISE NOTICE 'noted'; END $$")
    try:
        run_kind(live, 'event-trigger', 'create', {
            'name': 'ui_ops_notes', 'eventname': 'ddl_command_end', 'when': 'CREATE TABLE, DROP TABLE',
            'eventfunname': 'public.ui_ops_note', 'comment': "it's"})
        native = event_trigger_native('ui_ops_notes')
        assert (native['event_trigger_facts']['eventname'], native['event_trigger_facts']['when'],
                native['comment']) == ('ddl_command_end', 'CREATE TABLE, DROP TABLE', "it's")
        run_kind(live, 'event-trigger', 'alter', {'enabled': 'D', 'comment': '', 'name': 'ui_ops_quiet'}, native)
        native = event_trigger_native('ui_ops_quiet')
        assert (native['event_trigger_facts']['enabled'], native['comment']) == ('D', None)
        run_kind(live, 'event-trigger', 'alter', {'when': 'DROP TABLE', 'eventfunname': 'public.ui_ops_note',
                                                  'enabled': 'O'}, native)
        native = event_trigger_native('ui_ops_quiet')
        assert (native['event_trigger_facts']['when'], native['event_trigger_facts']['enabled']) == (
            'DROP TABLE', 'O')
        run_kind(live, 'event-trigger', 'drop', {'confirmation': 'ui_ops_quiet'}, native)
        assert query("SELECT count(*) FROM pg_event_trigger WHERE evtname LIKE 'ui_ops%'") == [(0,)]
    finally:
        query("DROP EVENT TRIGGER IF EXISTS ui_ops_notes; DROP EVENT TRIGGER IF EXISTS ui_ops_quiet; "
              "DROP FUNCTION public.ui_ops_note()")


# -- M4 (2026-11-11): role and tablespace editors from the server scope, provider-native, live -----
def run_server_scope(live, kind, operation_id, draft, native=None):
    provider, _route = live
    resource = target(None, kind, native) if native else None
    request = {'resource_kind': kind, 'operation_id': operation_id, 'target_resource': resource,
               '_provider_route': {'server_id': 1}, 'draft': draft}
    validation = provider.validate_visual_admin(request)
    assert validation['errors'] == [], (kind, operation_id, validation)
    plan = provider.plan_visual_admin(request)
    assert plan['state'] == 'ready', plan
    result = provider.apply_visual_admin({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'],
                                          'confirmed': True})
    assert result['provider_result']['transaction_outcome'] == 'committed', result
    return plan


def role_native(name):
    from pgadmin.cdeadmin.providers.postgresql.cluster import role_facts
    rows = query(f"""SELECT r.rolcanlogin, r.rolsuper, r.rolcreatedb, r.rolinherit, r.rolconnlimit, r.rolvaliduntil::text,
                            d.description, r.rolconfig::text[]
                     FROM pg_roles r LEFT JOIN pg_shdescription d ON d.objoid=r.oid AND d.classoid='pg_authid'::regclass
                     WHERE r.rolname='{name}'""")
    assert len(rows) == 1, name
    login, superuser, createdb, inherit, limit, until, comment, config = rows[0]
    native = {'name': name, 'catalog_metadata': {'rolname': name, 'rolcanlogin': login, 'rolsuper': superuser,
                                                 'description': comment}}
    native['role_facts'] = role_facts(native)
    native.update(createdb=createdb, inherit=inherit, limit=limit, until=until, config=config or [])
    return native


@live_only
def test_role_lifecycle_round_trips(live):
    if query("SELECT rolsuper FROM pg_roles WHERE rolname=current_user") != [(True,)]:
        pytest.skip('role changes need a superuser')
    group, member, name = f'ui_ops_grp_{UNIQUE}', f'ui_ops_mem_{UNIQUE}', f'ui_ops_role_{UNIQUE}'
    query(f'CREATE ROLE {group}; CREATE ROLE {member}')
    try:
        run_server_scope(live, 'role', 'create', {
            'rolname': name, 'rolcanlogin': True, 'rolsuper': False, 'rolcreatedb': True, 'rolinherit': False,
            'rolconnlimit': 5, 'rolvaliduntil': '2030-01-01 00:00:00+00',
            'rolmembership': [{'role': group, 'admin': True}], 'rolmembers': [{'role': member}],
            'variables': [{'name': 'work_mem', 'value': '4MB'}], 'description': "it's"})
        native = role_native(name)
        assert (native['role_facts']['rolcanlogin'], native['createdb'], native['inherit'], native['limit'],
                native['role_facts']['description']) == (True, True, False, 5, "it's")
        assert native['until'].startswith('2030-01-01') and native['config'] == ['work_mem=4MB']
        assert query(f"SELECT admin_option FROM pg_auth_members WHERE roleid='{group}'::regrole "
                     f"AND member='{name}'::regrole") == [(True,)]
        assert query(f"SELECT count(*) FROM pg_auth_members WHERE roleid='{name}'::regrole "
                     f"AND member='{member}'::regrole") == [(1,)]
        run_server_scope(live, 'role', 'alter', {
            'rolname': name + '_r', 'rolcanlogin': '', 'rolcreatedb': 'no', 'rolinherit': 'yes',
            'rolconnlimit': -1, 'rolvaliduntil': 'infinity',
            'revoke_membership': [{'role': group, 'admin_only': True}],
            'revoke_members': [{'role': member}],
            'reset_variables': [{'name': 'work_mem'}],
            'variables': [{'name': 'statement_timeout', 'value': '5s'}], 'description': ''}, native)
        native = role_native(name + '_r')
        assert (native['role_facts']['rolcanlogin'], native['createdb'], native['inherit'], native['limit'],
                native['until'], native['role_facts']['description']) == (True, False, True, -1, 'infinity', None)
        assert native['config'] == ['statement_timeout=5s']
        assert query(f"SELECT admin_option FROM pg_auth_members WHERE roleid='{group}'::regrole "
                     f"AND member='{name}_r'::regrole") == [(False,)]
        assert query(f"SELECT count(*) FROM pg_auth_members WHERE roleid='{name}_r'::regrole") == [(0,)]
        with pytest.raises(Exception):
            run_server_scope(live, 'role', 'drop', {'confirmation': 'other'}, native)
        run_server_scope(live, 'role', 'drop', {'confirmation': name + '_r'}, native)
        assert query(f"SELECT count(*) FROM pg_roles WHERE rolname LIKE '{name}%'") == [(0,)]
    finally:
        query(f'DROP ROLE IF EXISTS {name}; DROP ROLE IF EXISTS {name}_r; DROP ROLE {member}; DROP ROLE {group}')


def tablespace_native(name):
    from pgadmin.cdeadmin.providers.postgresql.cluster import tablespace_facts
    rows = query(f"""SELECT pg_get_userbyid(spcowner), spcoptions::text[], shobj_description(oid, 'pg_tablespace'),
                            spcacl::text[]
                     FROM pg_tablespace WHERE spcname='{name}'""")
    assert len(rows) == 1, name
    owner, options, comment, acl = rows[0]
    native = {'name': name, 'catalog_metadata': {'name': name, 'description': comment}}
    native['tablespace_facts'] = tablespace_facts(native)
    native.update(owner=owner, options=options or [], acl=acl or [])
    return native


@live_only
def test_tablespace_lifecycle_round_trips(live):
    directory = SETTINGS.get('tablespace_dir')
    if not directory:
        pytest.skip('tablespace_dir (a server-host directory owned by the server user) is not set')
    owner, name = f'ui_ops_tsowner_{UNIQUE}', f'ui_ops_ts_{UNIQUE}'
    query(f'CREATE ROLE {owner}')
    try:
        plan = run_server_scope(live, 'tablespace', 'create', {
            'name': name, 'spcuser': owner, 'spclocation': directory,
            'spcoptions': [{'name': 'random_page_cost', 'value': 1.5}]})
        assert plan['command_preview']['statement'].startswith(f'CREATE TABLESPACE "{name}"')
        native = tablespace_native(name)
        assert (native['owner'], native['options']) == (owner, ['random_page_cost=1.5'])
        run_server_scope(live, 'tablespace', 'alter', {
            'name': name + '_r', 'spcoptions': [{'name': 'seq_page_cost', 'value': '0.5'}],
            'reset_options': [{'name': 'random_page_cost'}], 'spcacl': [{'grantee': owner}],
            'description': 'ssd'}, native)
        native = tablespace_native(name + '_r')
        assert (native['options'], native['tablespace_facts']['description']) == (['seq_page_cost=0.5'], 'ssd')
        assert any(item.startswith(f'{owner}=C/') for item in native['acl'])
        run_server_scope(live, 'tablespace', 'drop', {'confirmation': name + '_r'}, native)
        assert query(f"SELECT count(*) FROM pg_tablespace WHERE spcname LIKE '{name}%'") == [(0,)]
    finally:
        # DROP TABLESPACE refuses a multi-statement string (an implicit transaction block): one per call.
        query(f'DROP TABLESPACE IF EXISTS {name}')
        query(f'DROP TABLESPACE IF EXISTS {name}_r')
        query(f'DROP ROLE {owner}')


# -- M5 (2026-11-11): cast, collation and language editors, provider-native, observed live --------
def catalog_object_native(kind, name, schema=None):
    from pgadmin.cdeadmin.providers.postgresql.catalog_objects import FACTS
    if kind == 'cast':
        rows = query(f"""SELECT c.castcontext, c.castmethod, d.description,
                                (pg_identify_object('pg_cast'::regclass, c.oid, 0)).identity
                         FROM pg_cast c LEFT JOIN pg_description d ON d.objoid=c.oid AND d.classoid='pg_cast'::regclass
                         WHERE format_type(c.castsource, NULL) || ' AS ' || format_type(c.casttarget, NULL) = '{name}'""")
        assert len(rows) == 1, name
        native = {'name': name, 'comment': rows[0][2], 'sql_identity': rows[0][3],
                  'catalog_row': {'castcontext': rows[0][0], 'castmethod': rows[0][1]}}
    elif kind == 'collation':
        rows = query(f"""SELECT c.collprovider, c.colllocale, c.collcollate, c.collctype, c.collisdeterministic,
                                c.collicurules, c.collversion, d.description, pg_get_userbyid(c.collowner)
                         FROM pg_collation c JOIN pg_namespace n ON n.oid=c.collnamespace
                         LEFT JOIN pg_description d ON d.objoid=c.oid AND d.classoid='pg_collation'::regclass
                         WHERE n.nspname='{schema}' AND c.collname='{name}'""")
        assert len(rows) == 1, (schema, name)
        provider, locale, collate, ctype, deterministic, rules, version, comment, owner = rows[0]
        native = {'schema': schema, 'name': name, 'comment': comment, 'owner': owner,
                  'catalog_row': {'collname': name, 'collprovider': provider, 'colllocale': locale,
                                  'collcollate': collate, 'collctype': ctype, 'collisdeterministic': deterministic,
                                  'collicurules': rules, 'collversion': version}}
    else:
        rows = query(f"""SELECT l.lanpltrusted, l.lanispl, d.description, pg_get_userbyid(l.lanowner)
                         FROM pg_language l LEFT JOIN pg_description d ON d.objoid=l.oid AND d.classoid='pg_language'::regclass
                         WHERE l.lanname='{name}'""")
        assert len(rows) == 1, name
        native = {'name': name, 'comment': rows[0][2], 'owner': rows[0][3],
                  'catalog_row': {'lanname': name, 'lanpltrusted': rows[0][0], 'lanispl': rows[0][1]}}
    key, reader = FACTS[kind]
    native[key] = reader(native)
    return native


@live_only
def test_cast_collation_and_language_lifecycles_round_trip(live):
    query('CREATE SCHEMA "Cat schema"; CREATE FUNCTION "Cat schema".to_int(text) RETURNS integer LANGUAGE sql '
          "IMMUTABLE AS 'SELECT 42'")
    try:
        run_kind(live, 'cast', 'create', {
            'srctyp': 'text', 'trgtyp': 'integer', 'castmethod': 'function',
            'proname': '"Cat schema".to_int(text)', 'castcontext': 'assignment', 'description': "it's"})
        cast = catalog_object_native('cast', 'text AS integer')
        assert (cast['cast_facts']['castcontext'], cast['cast_facts']['castmethod'], cast['comment']) == (
            'assignment', 'function', "it's")
        assert query("SELECT 'x'::text::integer") == [(42,)]
        run_kind(live, 'cast', 'drop', {'confirmation': 'text AS integer'}, cast)
        assert query("SELECT count(*) FROM pg_cast WHERE castsource='text'::regtype AND casttarget='integer'::regtype") == [(0,)]
        run_kind(live, 'collation', 'create', {
            'name': 'c one', 'schema': 'Cat schema', 'provider': 'icu', 'locale': 'en-US',
            'is_deterministic': False, 'description': 'c'})
        collation = catalog_object_native('collation', 'c one', 'Cat schema')
        facts = collation['collation_facts']
        assert (facts['provider'], facts['locale'], facts['is_deterministic'], collation['comment']) == (
            'icu', 'en-US', False, 'c')
        run_kind(live, 'collation', 'alter', {'name': 'c_two', 'description': '', 'refresh_version': True}, collation)
        collation = catalog_object_native('collation', 'c_two', 'Cat schema')
        assert collation['comment'] is None
        # A changed locale drops and recreates with the merged definition.
        run_kind(live, 'collation', 'alter', {'locale': 'de-DE', 'is_deterministic': False}, collation)
        collation = catalog_object_native('collation', 'c_two', 'Cat schema')
        assert (collation['collation_facts']['locale'], collation['collation_facts']['is_deterministic']) == (
            'de-DE', False)
        run_kind(live, 'collation', 'drop', {'confirmation': 'c_two'}, collation)
        run_kind(live, 'language', 'create', {
            'name': 'ui_ops_lang', 'trusted': True, 'lanproc': 'plpgsql_call_handler',
            'laninl': 'plpgsql_inline_handler', 'lanval': 'plpgsql_validator', 'description': 'twin'})
        language = catalog_object_native('language', 'ui_ops_lang')
        assert (language['language_facts']['trusted'], language['comment']) == (True, 'twin')
        run_kind(live, 'language', 'alter', {'description': '', 'name': 'ui_ops_lang2'}, language)
        language = catalog_object_native('language', 'ui_ops_lang2')
        assert language['comment'] is None
        run_kind(live, 'language', 'drop', {'confirmation': 'ui_ops_lang2'}, language)
        assert query("SELECT count(*) FROM pg_language WHERE lanname LIKE 'ui_ops%'") == [(0,)]
    finally:
        query('DROP CAST IF EXISTS (text AS integer)')
        query('DROP LANGUAGE IF EXISTS ui_ops_lang; DROP LANGUAGE IF EXISTS ui_ops_lang2')
        query('DROP SCHEMA "Cat schema" CASCADE')


# -- M5 (2026-11-11): foreign data wrapper, server and user mapping editors, provider-native, live --
def foreign_native(kind, name, server=None):
    from pgadmin.cdeadmin.providers.postgresql.foreign_objects import FACTS
    if kind == 'foreign-data-wrapper':
        rows = query(f"""SELECT w.fdwoptions::text[], d.description, w.fdwhandler::regproc::text,
                                w.fdwvalidator::regproc::text
                         FROM pg_foreign_data_wrapper w
                         LEFT JOIN pg_description d ON d.objoid=w.oid AND d.classoid='pg_foreign_data_wrapper'::regclass
                         WHERE w.fdwname='{name}'""")
        assert len(rows) == 1, name
        native = {'name': name, 'comment': rows[0][1], 'catalog_row': {'fdwname': name}}
        native.update(options=rows[0][0] or [], handler=rows[0][2], validator=rows[0][3])
        native['wrapper_facts'] = FACTS[kind][1](native)
    elif kind == 'foreign-server':
        rows = query(f"""SELECT s.srvfdw::int, s.srvtype, s.srvversion, s.srvoptions::text[], d.description, w.fdwname
                         FROM pg_foreign_server s JOIN pg_foreign_data_wrapper w ON w.oid=s.srvfdw
                         LEFT JOIN pg_description d ON d.objoid=s.oid AND d.classoid='pg_foreign_server'::regclass
                         WHERE s.srvname='{name}'""")
        assert len(rows) == 1, name
        fdw, typ, version, options, comment, fdwname = rows[0]
        native = {'name': name, 'comment': comment,
                  'catalog_row': {'srvname': name, 'srvfdw': str(fdw), 'srvtype': typ, 'srvversion': version}}
        native['options'] = options or []
        native['server_facts'] = FACTS[kind][1](native, {fdw: fdwname})
    else:
        rows = query(f"""SELECT (pg_identify_object('pg_user_mapping'::regclass, u.oid, 0)).identity,
                                u.umoptions::text[]
                         FROM pg_user_mapping u JOIN pg_foreign_server s ON s.oid=u.umserver
                         WHERE s.srvname='{server}' AND pg_get_userbyid(u.umuser)='{name}'""")
        assert len(rows) == 1, (name, server)
        native = {'name': f'{name} / {server}', 'sql_identity': rows[0][0], 'catalog_row': {'options_redacted': True}}
        native['options'] = rows[0][1] or []
        native['mapping_facts'] = FACTS[kind][1](native)
    return native


@live_only
def test_foreign_objects_lifecycle_round_trips(live):
    try:
        run_kind(live, 'foreign-data-wrapper', 'create', {
            'name': 'ui ops fdw', 'fdwoptions': [{'name': 'debug', 'value': 'on'}], 'description': "it's"})
        wrapper = foreign_native('foreign-data-wrapper', 'ui ops fdw')
        assert (wrapper['options'], wrapper['comment']) == (['debug=on'], "it's")
        run_kind(live, 'foreign-data-wrapper', 'alter', {
            'name': 'ui_ops_fdw', 'set_options': [{'name': 'debug', 'value': 'off'}],
            'add_options': [{'name': 'level', 'value': '2'}], 'description': ''}, wrapper)
        wrapper = foreign_native('foreign-data-wrapper', 'ui_ops_fdw')
        assert (sorted(wrapper['options']), wrapper['comment']) == (['debug=off', 'level=2'], None)
        run_kind(live, 'foreign-server', 'create', {
            'name': 'ui ops srv', 'fdwname': 'ui_ops_fdw', 'fsrvtype': 'pg', 'fsrvversion': '18',
            'fsrvoptions': [{'name': 'host', 'value': '127.0.0.1'}, {'name': 'dbname', 'value': 'x'}],
            'description': 'remote'})
        server = foreign_native('foreign-server', 'ui ops srv')
        assert (server['server_facts']['fdwname'], server['server_facts']['fsrvtype'],
                sorted(server['options'])) == ('ui_ops_fdw', 'pg', ['dbname=x', 'host=127.0.0.1'])
        run_kind(live, 'foreign-server', 'alter', {
            'name': 'ui_ops_srv', 'fsrvversion': '19', 'drop_options': [{'name': 'dbname'}],
            'set_options': [{'name': 'host', 'value': '127.0.0.2'}], 'description': ''}, server)
        server = foreign_native('foreign-server', 'ui_ops_srv')
        assert (server['server_facts']['fsrvversion'], server['options'], server['comment']) == (
            '19', ['host=127.0.0.2'], None)
        run_kind(live, 'user-mapping', 'create', {
            'name': SETTINGS['user'], 'server': 'ui_ops_srv', 'umoptions': [{'name': 'user', 'value': 'reader'}]})
        mapping = foreign_native('user-mapping', SETTINGS['user'], 'ui_ops_srv')
        assert mapping['options'] == ['user=reader']
        # A credential option is refused when the plan is compiled, before anything runs.
        provider, route = live
        with pytest.raises(Exception, match='credential'):
            provider.plan_visual_admin({
                'resource_kind': 'user-mapping', 'operation_id': 'alter',
                'target_resource': target(None, 'user-mapping', mapping), '_provider_route': route,
                'draft': {'add_options': [{'name': 'password', 'value': 'x'}]}})
        run_kind(live, 'user-mapping', 'alter', {'set_options': [{'name': 'user', 'value': 'writer'}]}, mapping)
        mapping = foreign_native('user-mapping', SETTINGS['user'], 'ui_ops_srv')
        assert mapping['options'] == ['user=writer']
        run_kind(live, 'user-mapping', 'drop', {'confirmation': mapping['name']}, mapping)
        run_kind(live, 'foreign-server', 'drop', {'confirmation': 'ui_ops_srv'}, server)
        run_kind(live, 'foreign-data-wrapper', 'drop', {'confirmation': 'ui_ops_fdw'}, wrapper)
        assert query("SELECT count(*) FROM pg_foreign_data_wrapper WHERE fdwname LIKE 'ui%'") == [(0,)]
    finally:
        query('DROP FOREIGN DATA WRAPPER IF EXISTS "ui ops fdw" CASCADE')
        query('DROP FOREIGN DATA WRAPPER IF EXISTS ui_ops_fdw CASCADE')


# -- M5 (2026-11-11): publication and subscription editors, provider-native, observed live --------
def publication_native(name):
    from pgadmin.cdeadmin.providers.postgresql.replication import publication_facts
    rows = query(f"""SELECT p.puballtables, p.pubinsert, p.pubupdate, p.pubdelete, p.pubtruncate, p.pubviaroot,
                            d.description, pg_get_userbyid(p.pubowner)
                     FROM pg_publication p LEFT JOIN pg_description d ON d.objoid=p.oid AND d.classoid='pg_publication'::regclass
                     WHERE p.pubname='{name}'""")
    assert len(rows) == 1, name
    alltables, ins, upd, dele, trunc, root, comment, owner = rows[0]
    members = query(f"""SELECT n.nspname, c.relname, c.oid::int, pr.prattrs::int[], pg_get_expr(pr.prqual, pr.prrelid)
                        FROM pg_publication_rel pr JOIN pg_publication p ON p.oid=pr.prpubid
                        JOIN pg_class c ON c.oid=pr.prrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                        WHERE p.pubname='{name}' ORDER BY c.relname""")
    schemas = query(f"""SELECT n.nspname, n.oid::int FROM pg_publication_namespace pn JOIN pg_publication p ON p.oid=pn.pnpubid
                        JOIN pg_namespace n ON n.oid=pn.pnnspid WHERE p.pubname='{name}'""")
    relations = {m[2]: (m[0], m[1]) for m in members}
    attributes = {m[2]: [{'attnum': a, 'attname': b} for a, b in query(
        f'SELECT attnum, attname FROM pg_attribute WHERE attrelid={m[2]} AND attnum > 0')] for m in members}
    native = {'name': name, 'comment': comment,
              'catalog_row': {'pubname': name, 'puballtables': alltables, 'pubinsert': ins, 'pubupdate': upd,
                              'pubdelete': dele, 'pubtruncate': trunc, 'pubviaroot': root},
              'children': {'pg_publication_rel': [{'prrelid': str(m[2]), 'prattrs': m[3], 'row_filter_sql': m[4]}
                                                  for m in members],
                           'pg_publication_namespace': [{'pnnspid': str(s[1])} for s in schemas]}}
    native['publication_facts'] = publication_facts(native, relations, attributes, {s[1]: s[0] for s in schemas})
    native['owner'] = owner
    return native


def subscription_native(name):
    from pgadmin.cdeadmin.providers.postgresql.replication import subscription_facts
    rows = query(f"""SELECT s.subpublications, s.subenabled, s.subslotname, s.subsynccommit, s.subbinary, s.substream,
                            s.subtwophasestate, s.subdisableonerr, s.subrunasowner, s.subpasswordrequired, s.suborigin,
                            s.subfailover, d.description
                     FROM pg_subscription s LEFT JOIN pg_description d ON d.objoid=s.oid AND d.classoid='pg_subscription'::regclass
                     WHERE s.subname='{name}'""")
    assert len(rows) == 1, name
    keys = ('subpublications', 'subenabled', 'subslotname', 'subsynccommit', 'subbinary', 'substream',
            'subtwophasestate', 'subdisableonerr', 'subrunasowner', 'subpasswordrequired', 'suborigin', 'subfailover')
    native = {'name': name, 'comment': rows[0][12], 'catalog_row': dict(zip(keys, rows[0][:12]), subname=name,
                                                                        connection_redacted=True)}
    native['subscription_facts'] = subscription_facts(native)
    return native


@live_only
def test_publication_and_subscription_lifecycles_round_trip(live):
    # Publications and a non-connecting subscription (connect = false, no slot) need no logical WAL.
    query('CREATE SCHEMA "Rep schema"; CREATE TABLE "Rep schema".t (id int PRIMARY KEY, note text); '
          'CREATE TABLE "Rep schema".u (id int PRIMARY KEY); CREATE SCHEMA rep_other')
    try:
        run_kind(live, 'publication', 'create', {
            'name': 'ui ops pub', 'pubtable': [{'table_name': '"Rep schema".t', 'columns': 'id, note',
                                                'where': 'id > 0'}],
            'evnt_insert': True, 'evnt_update': True, 'evnt_delete': False, 'evnt_truncate': False,
            'publish_via_partition_root': True, 'description': "it's"})
        publication = publication_native('ui ops pub')
        facts = publication['publication_facts']
        assert (facts['evnt_delete'], facts['publish_via_partition_root'], publication['comment']) == (
            False, True, "it's")
        assert facts['pubtable'] == [{'table_name': 'Rep schema.t', 'columns': 'id, note', 'where': '(id > 0)'}]
        run_kind(live, 'publication', 'alter', {
            'name': 'ui_ops_pub', 'evnt_delete': True, 'add_tables': [{'table_name': '"Rep schema".u'}],
            'drop_tables': [{'table_name': '"Rep schema".t'}], 'description': ''}, publication)
        publication = publication_native('ui_ops_pub')
        assert publication['publication_facts']['evnt_delete'] is True
        assert [item['table_name'] for item in publication['publication_facts']['pubtable']] == ['Rep schema.u']
        run_kind(live, 'publication', 'create', {'name': 'ui_ops_schemas', 'pubschema': [{'schema': 'rep_other'}]})
        assert publication_native('ui_ops_schemas')['publication_facts']['pubschema'] == [{'schema': 'rep_other'}]
        # A subscription to this same server, created without connecting (no slot, disabled).
        run_kind(live, 'subscription', 'create', {
            'name': 'ui ops sub', 'host': SETTINGS['host'], 'port': SETTINGS['port'], 'db': DATABASE,
            'username': SETTINGS['user'], 'pub': 'ui_ops_pub', 'connect': False, 'enabled': False,
            'create_slot': False, 'copy_data': False, 'slot_name': 'NONE', 'sync': 'off', 'streaming': 'on',
            'binary': True})
        subscription = subscription_native('ui ops sub')
        facts = subscription['subscription_facts']
        assert (facts['pub'], facts['enabled'], facts['slot_name'], facts['streaming'], facts['binary']) == (
            ['ui_ops_pub'], False, None, 'on', True)
        run_kind(live, 'subscription', 'alter', {
            'name': 'ui_ops_sub', 'sync': 'local', 'binary': False, 'pub': 'ui_ops_pub, ui_ops_schemas',
            'enabled': False, 'description': 'mirror'}, subscription)
        subscription = subscription_native('ui_ops_sub')
        facts = subscription['subscription_facts']
        assert (sorted(facts['pub']), facts['sync'], facts['binary'], subscription['comment']) == (
            ['ui_ops_pub', 'ui_ops_schemas'], 'local', False, 'mirror')
        # The alter form has no connection fields, so the draft is refused before the compiler's own
        # "credentials" refusal; either way no connection change can run from here.
        with pytest.raises(Exception):
            provider, route = live
            provider.plan_visual_admin({'resource_kind': 'subscription', 'operation_id': 'alter',
                                        'target_resource': target(None, 'subscription', subscription),
                                        '_provider_route': route, 'draft': {'host': 'elsewhere'}})
        run_kind(live, 'subscription', 'drop', {'confirmation': 'ui_ops_sub'}, subscription)
        run_kind(live, 'publication', 'drop', {'confirmation': 'ui_ops_pub'}, publication)
        run_kind(live, 'publication', 'drop', {'confirmation': 'ui_ops_schemas'},
                 publication_native('ui_ops_schemas'))
        assert query("SELECT count(*) FROM pg_publication WHERE pubname LIKE 'ui%'") == [(0,)]
    finally:
        query('DROP SUBSCRIPTION IF EXISTS "ui ops sub"')
        query('DROP SUBSCRIPTION IF EXISTS ui_ops_sub')
        query('DROP PUBLICATION IF EXISTS "ui ops pub"; DROP PUBLICATION IF EXISTS ui_ops_pub; '
              'DROP PUBLICATION IF EXISTS ui_ops_schemas')
        query('DROP SCHEMA "Rep schema" CASCADE; DROP SCHEMA rep_other CASCADE')


# -- M5 (2026-11-11): text search editors, provider-native, observed live -------------------------
def text_search_native(kind, schema, name):
    from pgadmin.cdeadmin.providers.postgresql.text_search import facts
    catalog, column, classoid = {
        'text-search-configuration': ('pg_ts_config', 'cfgname', 'pg_ts_config'),
        'text-search-dictionary': ('pg_ts_dict', 'dictname', 'pg_ts_dict'),
        'text-search-parser': ('pg_ts_parser', 'prsname', 'pg_ts_parser'),
        'text-search-template': ('pg_ts_template', 'tmplname', 'pg_ts_template')}[kind]
    namespace = column.replace('name', 'namespace')
    rows = query(f"""SELECT to_jsonb(c) - 'oid', d.description FROM {catalog} c
                     JOIN pg_namespace n ON n.oid=c.{namespace}
                     LEFT JOIN pg_description d ON d.objoid=c.oid AND d.classoid='{classoid}'::regclass
                     WHERE n.nspname='{schema}' AND c.{column}='{name}'""")
    assert len(rows) == 1, (kind, schema, name)
    native = {'schema': schema, 'name': name, 'comment': rows[0][1], 'catalog_row': rows[0][0]}
    native['text_search_facts'] = facts(kind, native)
    return native


@live_only
def test_text_search_lifecycles_round_trip(live):
    query('CREATE SCHEMA "Fts schema"')
    try:
        run_kind(live, 'text-search-template', 'create', {
            'name': 't one', 'schema': 'Fts schema', 'tmplinit': 'dsimple_init', 'tmpllexize': 'dsimple_lexize',
            'description': "it's"})
        template = text_search_native('text-search-template', 'Fts schema', 't one')
        assert (template['text_search_facts']['tmplinit'], template['comment']) == ('dsimple_init', "it's")
        run_kind(live, 'text-search-dictionary', 'create', {
            'name': 'd one', 'schema': 'Fts schema', 'template': '"Fts schema"."t one"',
            'options': [{'option': 'stopwords', 'value': 'english'}], 'description': 'd'})
        dictionary = text_search_native('text-search-dictionary', 'Fts schema', 'd one')
        assert dictionary['text_search_facts']['dictinitoption'] == "stopwords = 'english'"
        run_kind(live, 'text-search-dictionary', 'alter', {
            'name': 'd_two', 'set_options': [{'option': 'accept', 'value': 'false'}],
            'drop_options': [{'option': 'stopwords'}], 'description': ''}, dictionary)
        dictionary = text_search_native('text-search-dictionary', 'Fts schema', 'd_two')
        assert (dictionary['text_search_facts']['dictinitoption'], dictionary['comment']) == (
            "accept = 'false'", None)
        run_kind(live, 'text-search-parser', 'create', {
            'name': 'p one', 'schema': 'Fts schema', 'prsstart': 'prsd_start', 'prstoken': 'prsd_nexttoken',
            'prsend': 'prsd_end', 'prslextype': 'prsd_lextype'})
        parser = text_search_native('text-search-parser', 'Fts schema', 'p one')
        assert parser['text_search_facts']['prsheadline'] is None
        run_kind(live, 'text-search-parser', 'alter', {'prsheadline': 'prsd_headline', 'name': 'p_two'}, parser)
        parser = text_search_native('text-search-parser', 'Fts schema', 'p_two')
        assert parser['text_search_facts']['prsheadline'] == 'prsd_headline'
        run_kind(live, 'text-search-configuration', 'create', {
            'name': 'c one', 'schema': 'Fts schema', 'prsname': '"Fts schema".p_two',
            'tokens': [{'token': 'asciiword', 'dictname': '"Fts schema".d_two, pg_catalog.simple'}],
            'description': 'c'})
        configuration = text_search_native('text-search-configuration', 'Fts schema', 'c one')
        assert query("""SELECT count(*) FROM pg_ts_config_map m JOIN pg_ts_config c ON c.oid=m.mapcfg
                        WHERE c.cfgname='c one'""") == [(2,)]
        run_kind(live, 'text-search-configuration', 'alter', {
            'name': 'c_two', 'add_mappings': [{'token': 'word', 'dictname': 'pg_catalog.simple'}],
            'alter_mappings': [{'token': 'asciiword', 'dictname': 'pg_catalog.simple'}],
            'description': ''}, configuration)
        configuration = text_search_native('text-search-configuration', 'Fts schema', 'c_two')
        assert configuration['comment'] is None
        assert query("""SELECT count(*) FROM pg_ts_config_map m JOIN pg_ts_config c ON c.oid=m.mapcfg
                        WHERE c.cfgname='c_two'""") == [(2,)]
        run_kind(live, 'text-search-configuration', 'alter', {'drop_mappings': [{'token': 'word'}]}, configuration)
        assert query("""SELECT count(*) FROM pg_ts_config_map m JOIN pg_ts_config c ON c.oid=m.mapcfg
                        WHERE c.cfgname='c_two'""") == [(1,)]
        for kind, name in (('text-search-configuration', 'c_two'), ('text-search-dictionary', 'd_two'),
                           ('text-search-parser', 'p_two'), ('text-search-template', 't one')):
            run_kind(live, kind, 'drop', {'confirmation': name}, text_search_native(kind, 'Fts schema', name))
        assert query("SELECT count(*) FROM pg_ts_config c JOIN pg_namespace n ON n.oid=c.cfgnamespace "
                     "WHERE n.nspname='Fts schema'") == [(0,)]
    finally:
        query('DROP SCHEMA "Fts schema" CASCADE')


# -- M6 (2026-11-11): server operations from the server scope, provider-native, observed live -----
def run_server(live, operation_id, values=None):
    provider, _route = live
    operation = OPERATIONS[f'{operation_id}@server']
    draft = operation_draft(operation, values)
    request = {'resource_kind': 'server', 'operation_id': operation_id, 'target_resource': None,
               '_provider_route': {'server_id': 1}, 'draft': draft}
    validation = provider.validate_visual_admin(request)
    assert validation['errors'] == [], (operation_id, validation)
    plan = provider.plan_visual_admin(request)
    assert plan['state'] == 'ready', plan
    assert plan['confirmation_required'] == (operation['confirmation'] != 'none'), (operation_id, plan)
    result = provider.apply_visual_admin({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'],
                                          'confirmed': True})
    outcome = result['provider_result']
    assert outcome['transaction_outcome'] == 'committed', outcome
    return outcome


@live_only
def test_server_reload_and_restore_point(live):
    if query("SELECT rolsuper FROM pg_roles WHERE rolname=current_user") != [(True,)]:
        pytest.skip('pg_reload_conf and restore points need a superuser')
    outcome = run_server(live, 'reload')
    assert outcome['result']['rows'] == [{'reloaded': True}]
    assert outcome['maintenance_receipt']['action'] == 'reload'
    if query("SELECT setting FROM pg_settings WHERE name='wal_level'") == [('minimal',)]:
        pytest.skip('restore points need wal_level above minimal')
    outcome = run_server(live, 'restore-point', {'name': f'ui ops {UNIQUE}'})
    lsn = outcome['result']['rows'][0]['restore_point_lsn']
    assert isinstance(lsn, str) and '/' in lsn


@live_only
def test_wal_replay_control_is_refused_on_a_primary(live):
    if query('SELECT pg_is_in_recovery()') == [(True,)]:
        pytest.skip('this server is a standby; pause and resume would succeed')
    for operation_id in ('wal-replay-pause', 'wal-replay-resume'):
        with pytest.raises(Exception):
            run_server(live, operation_id)


# -- M6 (2026-11-11): schema/database VACUUM+ANALYZE and forced database drop, observed live -------
@live_only
def test_vacuum_and_analyze_at_schema_and_database_scope(live):
    fresh_table('m_sv')
    query('CREATE MATERIALIZED VIEW public.m_sv_mv AS SELECT * FROM public.m_sv')
    query("DELETE FROM public.m_sv WHERE id % 2 = 0")
    dead = lambda: one("SELECT n_dead_tup FROM pg_stat_user_tables WHERE relname='m_sv'")
    assert dead() > 0
    native = {'name': 'public', 'relations': ['m_sv', 'm_sv_mv']}
    plan, outcome = run(live, 'vacuum', kind='schema', native=native, values={'analyze': True})
    assert plan['command_preview']['statement'] == 'VACUUM (ANALYZE) "public"."m_sv", "public"."m_sv_mv"'
    assert outcome['maintenance_receipt']['transaction_mode'] == 'autocommit'
    assert dead() == 0
    plan, outcome = run(live, 'analyze', kind='schema', native=native)
    assert plan['command_preview']['statement'] == 'ANALYZE "public"."m_sv", "public"."m_sv_mv"'
    assert one("SELECT count(*) FROM pg_stats WHERE schemaname='public' AND tablename='m_sv_mv'") > 0
    query("DELETE FROM public.m_sv WHERE id % 3 = 0")
    assert dead() > 0
    plan, outcome = run(live, 'vacuum', kind='database', native={'name': DATABASE}, values={'freeze': True})
    assert plan['command_preview']['statement'] == 'VACUUM (FREEZE)'
    assert dead() == 0
    plan, outcome = run(live, 'analyze', kind='database', native={'name': DATABASE}, values={'verbose': True})
    assert plan['command_preview']['statement'] == 'ANALYZE (VERBOSE)'
    assert outcome['maintenance_receipt']['transaction_mode'] == 'transaction'
    # The provider's own listing carries the schema's relation list the compiler consumed.
    provider, route = live
    listed = provider._captured_resources({'resource_id': None, 'authority_path': []}, route)
    public = next(r for r in listed if r['resource_kind'] == 'schema' and r['display_name'] == 'public')
    relations = public['extensions']['postgresql']['native']['relations']
    assert {'m_sv', 'm_sv_mv'} <= set(relations)
    with pytest.raises(Exception, match='no tables'):
        run(live, 'vacuum', kind='schema', native={'name': 'public', 'relations': []})


@live_only
def test_database_drop_with_force_terminates_sessions(live):
    import psycopg
    name = f'ui_ops_dropme_{UNIQUE}'
    query(f'CREATE DATABASE "{name}"', database=SETTINGS.get('database', 'postgres'))
    held = psycopg.connect(dsn(name), autocommit=True)
    try:
        held.execute('SELECT 1')
        native = database_native(name)
        # Without FORCE the held session blocks the drop and the server refuses.
        with pytest.raises(Exception):
            run_database(live, 'drop', {'confirmation': name}, native, confirmation_required=True)
        assert query(f"SELECT count(*) FROM pg_database WHERE datname='{name}'") == [(1,)]
        plan = run_database(live, 'drop', {'confirmation': name, 'force': True}, native, confirmation_required=True)
        assert plan['command_preview']['statement'] == f'DROP DATABASE "{name}" WITH (FORCE)'
        assert query(f"SELECT count(*) FROM pg_database WHERE datname='{name}'") == [(0,)]
        with pytest.raises(psycopg.OperationalError):
            held.execute('SELECT 1')
    finally:
        held.close()
        query(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', database=SETTINGS.get('database', 'postgres'))


# -- M6 (2026-11-11): role REASSIGN/DROP OWNED and tablespace move, database picked in the dialog --
def run_picked(live, kind, operation_id, native, values, confirmation=None):
    provider, route = live
    operation = OPERATIONS[f'{operation_id}@{kind}']
    draft = operation_draft(operation, values, confirmation=confirmation)
    request = {'resource_kind': kind, 'operation_id': operation_id, 'target_resource': target(None, kind, native),
               '_provider_route': {'server_id': route['server_id']}, 'draft': draft}
    validation = provider.validate_visual_admin(request)
    assert validation['errors'] == [], (operation_id, validation)
    plan = provider.plan_visual_admin(request)
    assert plan['state'] == 'ready', plan
    assert plan['confirmation_required'] is True, plan
    result = provider.apply_visual_admin({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'],
                                          'confirmed': True})
    outcome = result['provider_result']
    assert outcome['transaction_outcome'] == 'committed', outcome
    return plan, outcome


@live_only
def test_reassign_and_drop_owned_act_in_the_picked_database(live):
    if query("SELECT rolsuper FROM pg_roles WHERE rolname=current_user") != [(True,)]:
        pytest.skip('REASSIGN OWNED needs a superuser or membership in both roles')
    provider, route = live
    picked = f"postgresql:pg_database/{route['database_id']}"
    old, new = f'ui_ops_old_{UNIQUE}', f'ui_ops_new_{UNIQUE}'
    query(f'CREATE ROLE {old}; CREATE ROLE {new}')
    try:
        query(f'CREATE TABLE public.m_own (id int); ALTER TABLE public.m_own OWNER TO {old}')
        query(f'CREATE SEQUENCE public.m_own_seq; ALTER SEQUENCE public.m_own_seq OWNER TO {new}')
        plan, outcome = run_picked(live, 'role', 'reassign-owned', role_native(old), {'database': picked, 'new_owner': new})
        assert plan['command_preview']['statement'] == f'REASSIGN OWNED BY "{old}" TO "{new}"'
        assert one("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='public.m_own'::regclass") == new
        plan, outcome = run_picked(live, 'role', 'drop-owned', role_native(new), {'database': picked},
                                   confirmation=new)
        assert plan['command_preview']['statement'] == f'DROP OWNED BY "{new}" RESTRICT'
        assert one("SELECT count(*) FROM pg_class WHERE relname IN ('m_own', 'm_own_seq')") == 0
        # The picked database is the plan's route, not the node's server-scope route.
        assert plan['provider_payload']['route']['database_id'] == route['database_id'] if 'provider_payload' in plan \
            else True
    finally:
        query('DROP TABLE IF EXISTS public.m_own; DROP SEQUENCE IF EXISTS public.m_own_seq')
        query(f'DROP OWNED BY {old}, {new}; DROP ROLE {old}; DROP ROLE {new}')


@live_only
def test_move_objects_between_tablespaces(live):
    directory = SETTINGS.get('tablespace_dir')
    if not directory:
        pytest.skip('tablespace_dir (a server-host directory owned by the server user) is not set')
    provider, route = live
    picked = f"postgresql:pg_database/{route['database_id']}"
    name = f'ui_ops_mv_{UNIQUE}'
    query(f'CREATE TABLESPACE "{name}" LOCATION \'{directory}\'', database=SETTINGS.get('database', 'postgres'))
    try:
        query(f'CREATE TABLE public.m_move (id int PRIMARY KEY USING INDEX TABLESPACE "{name}") TABLESPACE "{name}"')
        query(f'CREATE INDEX m_move_ix ON public.m_move (id) TABLESPACE "{name}"')
        spaces = lambda: dict(query("SELECT c.relname, coalesce(t.spcname, 'pg_default') FROM pg_class c "
                                    "LEFT JOIN pg_tablespace t ON t.oid=c.reltablespace "
                                    "WHERE c.relname IN ('m_move', 'm_move_ix', 'm_move_pkey')"))
        assert set(spaces().values()) == {name}
        plan, outcome = run_picked(live, 'tablespace', 'move-objects', tablespace_native(name),
                                   {'database': picked, 'new_tablespace': 'pg_default', 'object_type': 'indexes'})
        assert plan['command_preview']['statement'] == \
            f'ALTER INDEX ALL IN TABLESPACE "{name}" SET TABLESPACE "pg_default"'
        assert spaces() == {'m_move': name, 'm_move_ix': 'pg_default', 'm_move_pkey': 'pg_default'}
        plan, outcome = run_picked(live, 'tablespace', 'move-objects', tablespace_native(name),
                                   {'database': picked, 'new_tablespace': 'pg_default'})
        assert outcome['maintenance_receipt']['options'] == ['all']
        assert set(spaces().values()) == {'pg_default'}
    finally:
        query('DROP TABLE IF EXISTS public.m_move')
        query(f'DROP TABLESPACE IF EXISTS "{name}"', database=SETTINGS.get('database', 'postgres'))


# -- M6 (2026-11-11): pgAgent job editor and Run now against a stand-in pgagent schema -------------
STAND_IN_PGAGENT = """
CREATE SCHEMA pgagent;
CREATE TABLE pgagent.pga_jobclass (jclid serial PRIMARY KEY, jclname text NOT NULL);
INSERT INTO pgagent.pga_jobclass (jclname) VALUES ('Routine Maintenance');
CREATE TABLE pgagent.pga_job (
    jobid serial PRIMARY KEY, jobjclid int NOT NULL, jobname text NOT NULL, jobdesc text NOT NULL DEFAULT '',
    jobhostagent text NOT NULL DEFAULT '', jobenabled bool NOT NULL DEFAULT true,
    jobcreated timestamptz NOT NULL DEFAULT now(), jobchanged timestamptz NOT NULL DEFAULT now(),
    jobagentid int, jobnextrun timestamptz, joblastrun timestamptz);
CREATE TABLE pgagent.pga_jobstep (
    jstid serial PRIMARY KEY, jstjobid int NOT NULL REFERENCES pgagent.pga_job ON DELETE CASCADE,
    jstname text NOT NULL, jstdesc text NOT NULL DEFAULT '', jstenabled bool NOT NULL DEFAULT true,
    jstkind char(1) NOT NULL, jstcode text NOT NULL DEFAULT '', jstconnstr text NOT NULL DEFAULT '',
    jstdbname name NOT NULL DEFAULT '', jstonerror char(1) NOT NULL DEFAULT 'f', jscnextrun timestamptz);
CREATE TABLE pgagent.pga_schedule (
    jscid serial PRIMARY KEY, jscjobid int NOT NULL REFERENCES pgagent.pga_job ON DELETE CASCADE,
    jscname text NOT NULL, jscdesc text NOT NULL DEFAULT '', jscenabled bool NOT NULL DEFAULT true,
    jscstart timestamptz NOT NULL, jscend timestamptz, jscminutes bool[] NOT NULL, jschours bool[] NOT NULL,
    jscweekdays bool[] NOT NULL, jscmonthdays bool[] NOT NULL, jscmonths bool[] NOT NULL);
CREATE TABLE pgagent.pga_exception (jexid serial PRIMARY KEY, jexscid int NOT NULL, jexdate date, jextime time);
CREATE TABLE pgagent.pga_jobagent (jagpid int PRIMARY KEY, jagstation text NOT NULL);
CREATE TABLE pgagent.pga_joblog (jlgid serial PRIMARY KEY, jlgjobid int NOT NULL, jlgstatus char(1) NOT NULL);
"""


def job_native(jobid):
    """What the provider's server-scope capture attaches to a job node."""
    from pgadmin.cdeadmin.providers.postgresql.pgagent import facts
    # The harness driver attaches to the scratch database for every scope.
    maintenance = DATABASE
    (jobname, enabled, desc, agent, jclid), = query(
        f"SELECT jobname, jobenabled, jobdesc, jobhostagent, jobjclid FROM pgagent.pga_job WHERE jobid={jobid}",
        database=maintenance)
    steps = [dict(zip(('jstid', 'jstname', 'jstenabled', 'jstkind', 'jstconntype', 'jstconnstr', 'jstdbname',
                       'jstonerror', 'jstcode', 'jstdesc'), row)) for row in query(
        f"""SELECT jstid, jstname, jstenabled, jstkind = 's', (jstdbname != '' OR jstkind = 'b'), jstconnstr,
                   jstdbname, jstonerror, jstcode, jstdesc FROM pgagent.pga_jobstep WHERE jstjobid={jobid}
            ORDER BY jstname""", database=maintenance)]
    schedules = [dict(zip(('jscid', 'jscname', 'jscenabled', 'jscstart', 'jscend', 'jscminutes', 'jschours',
                           'jscweekdays', 'jscmonthdays', 'jscmonths', 'jscdesc'), row)) for row in query(
        f"""SELECT jscid, jscname, jscenabled, jscstart::text, jscend::text, jscminutes::text, jschours::text,
                   jscweekdays::text, jscmonthdays::text, jscmonths::text, jscdesc
            FROM pgagent.pga_schedule WHERE jscjobid={jobid} ORDER BY jscname""",
        database=maintenance)]
    native = {'name': jobname, 'catalog_metadata': {
        'jobid': jobid, 'jobname': jobname, 'jobenabled': enabled, 'jobdesc': desc, 'jobhostagent': agent,
        'jobjclid': jclid, 'has_connstr': True, 'steps': steps, 'schedules': schedules}}
    native['job_facts'] = facts(native)
    return native


@live_only
def test_pgagent_job_lifecycle_and_run_now(live):
    # The harness driver attaches to the scratch database for every scope.
    maintenance = DATABASE
    if query("SELECT count(*) FROM pg_namespace WHERE nspname='pgagent'", database=maintenance) != [(0,)]:
        pytest.skip('a pgagent schema already exists on this server; the stand-in would collide')
    query(STAND_IN_PGAGENT, database=maintenance)
    name = f'ui_ops_job_{UNIQUE}'
    try:
        plan = run_server_scope(live, 'pgagent-job', 'create', {
            'jobname': name, 'jobenabled': True, 'jobjclid': 1, 'jobhostagent': '', 'jobdesc': "it's nightly",
            'jsteps': [{'jstname': 'vac', 'jstkind': 'sql', 'jstconntype': 'local', 'jstdbname': DATABASE,
                        'jstcode': 'VACUUM'},
                       {'jstname': 'report', 'jstkind': 'batch', 'jstonerror': 'i', 'jstcode': 'echo done'}],
            'jschedules': [{'jscname': 'daily', 'jscstart': '2026-01-01 02:00:00+00', 'jscminutes': '0',
                            'jschours': '2', 'jscweekdays': '0, 1, 2, 3, 4, 5, 6',
                            'jscmonthdays': ', '.join(str(i) for i in range(32)),
                            'jscmonths': ', '.join(str(i) for i in range(12))}]})
        assert plan['command_preview']['statement'].startswith('DO $$')
        (jobid,), = query(f"SELECT jobid FROM pgagent.pga_job WHERE jobname='{name}'", database=maintenance)
        native = job_native(jobid)
        assert [s['jstname'] for s in native['job_facts']['jsteps']] == ['report', 'vac']
        assert native['job_facts']['jschedules'][0]['jschours'] == '2'
        # Alter: disable, rewrite one step, drop the other, add a second schedule, keep the first.
        steps = {s['jstname']: s for s in native['job_facts']['jsteps']}
        schedules = native['job_facts']['jschedules']
        run_server_scope(live, 'pgagent-job', 'alter', {
            'jobenabled': False,
            'jsteps': [dict(steps['vac'], jstcode='VACUUM ANALYZE')],
            'jschedules': schedules + [{'jscname': 'weekly', 'jscstart': '2026-01-04 03:00:00+00',
                                        'jscminutes': '15', 'jschours': '3', 'jscweekdays': '0',
                                        'jscmonthdays': '', 'jscmonths': ''}]}, native)
        native = job_native(jobid)
        assert native['job_facts']['jobenabled'] is False
        assert [(s['jstname'], s['jstcode']) for s in native['job_facts']['jsteps']] == [('vac', 'VACUUM ANALYZE')]
        assert [s['jscname'] for s in native['job_facts']['jschedules']] == ['daily', 'weekly']
        assert query(f"SELECT jscweekdays[1], jscweekdays[2] FROM pgagent.pga_schedule WHERE jscname='weekly'",
                     database=maintenance) == [(True, False)]
        # Run now: the next run is set to the present.
        assert query(f"SELECT jobnextrun FROM pgagent.pga_job WHERE jobid={jobid}", database=maintenance) == [(None,)]
        plan, outcome = run(live, 'run-now', kind='pgagent-job', native=native)
        assert plan['command_preview']['statement'] == f'UPDATE pgagent.pga_job SET jobnextrun = now() WHERE jobid = {jobid}'
        assert query(f"SELECT jobnextrun IS NOT NULL FROM pgagent.pga_job WHERE jobid={jobid}",
                     database=maintenance) == [(True,)]
        # Drop cascades to steps and schedules.
        run_server_scope(live, 'pgagent-job', 'drop', {'confirmation': name}, native)
        assert query(f"SELECT count(*) FROM pgagent.pga_job WHERE jobid={jobid}", database=maintenance) == [(0,)]
        assert query(f"SELECT count(*) FROM pgagent.pga_jobstep WHERE jstjobid={jobid}", database=maintenance) == [(0,)]
    finally:
        query('DROP SCHEMA IF EXISTS pgagent CASCADE', database=maintenance)


# -- M7 (2026-11-11): the inherited table node's operations, observed live ------------------------
@live_only
def test_table_count_reset_and_trigger_toggles(live):
    fresh_table('m_ops')
    oid = one("SELECT oid::int FROM pg_class WHERE oid='public.m_ops'::regclass")
    query('CREATE OR REPLACE FUNCTION public.m_ops_noop() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$')
    query('CREATE TRIGGER m_ops_trg BEFORE INSERT ON public.m_ops FOR EACH ROW EXECUTE FUNCTION public.m_ops_noop()')
    enabled = lambda: one("SELECT tgenabled FROM pg_trigger WHERE tgname='m_ops_trg'")
    native = {'schema': 'public', 'name': 'm_ops', 'oid': oid}
    plan, outcome = run(live, 'count-rows', kind='table', native=native)
    assert outcome['result']['rows'] == [{'row_count': 1000}]
    assert outcome['maintenance_receipt']['action'] == 'count-rows'
    query("INSERT INTO public.m_ops (grp, payload) VALUES (1, 'y')")
    assert one("SELECT n_tup_ins FROM pg_stat_user_tables WHERE relname='m_ops'") > 0
    plan, outcome = run(live, 'reset-statistics', kind='table', native=native)
    assert eventually("SELECT n_tup_ins FROM pg_stat_user_tables WHERE relname='m_ops'", [(0,)]) == [(0,)]
    assert enabled() == 'O'
    plan, outcome = run(live, 'disable-triggers', kind='table', native=native)
    assert plan['confirmation_required'] is True
    assert enabled() == 'D'
    plan, outcome = run(live, 'enable-triggers', kind='table', native=native)
    assert enabled() == 'O'
