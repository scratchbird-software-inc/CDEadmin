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
for name, folder in (('pgadmin', 'web/pgadmin'), ('pgadmin.utils', 'web/pgadmin/utils')):
    if name not in sys.modules:
        package = ModuleType(name)
        package.__path__ = [str(ROOT / folder)]
        sys.modules[name] = package
if 'config' not in sys.modules:
    sys.modules['config'] = ModuleType('config')

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
          'reindex@index', 'reindex@schema', 'reindex@database', 'refresh@materialized-view'}


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
