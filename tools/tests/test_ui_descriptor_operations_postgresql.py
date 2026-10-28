"""PostgreSQL tier 2/3 operations round-trip through the OperationDialog's draft
(field defaults + values) -> provider visual-admin validate/plan/apply -> effect
observed on a live PostgreSQL server.

The PostgreSQL provider executes only a few non-lifecycle actions through its own
validate/plan/apply route: the large-object read, write, truncate and server-file
import/export (``providers/postgresql/large_objects.py``). Maintenance such as
VACUUM, ANALYZE, REINDEX and CLUSTER is owned by the preserved pgAdmin surface and
``compile_native_admin`` refuses it, so no descriptor exists for it.

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
          'import-server-file@large-object', 'export-server-file@large-object'}


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


def test_no_maintenance_descriptor_without_a_provider_route():
    """VACUUM/ANALYZE/REINDEX/CLUSTER are legacy-preserved: a descriptor would promise a dialog nothing plans."""
    from pgadmin.cdeadmin.providers.postgresql.native_admin import (
        POSTGRESQL_NATIVE_FORM_KINDS, PostgreSQLNativeAdminError, compile_native_admin)
    for operation in OPERATIONS.values():
        assert operation['resource_kind'] in POSTGRESQL_NATIVE_FORM_KINDS
    with pytest.raises(PostgreSQLNativeAdminError, match='preserved PostgreSQL UI'):
        compile_native_admin({'resource_kind': 'table', 'operation_id': 'alter', 'draft': {}})


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


def target(oid):
    # The resource the navigator lists: display name is the OID, native.oid is the identity.
    return {'resource_kind': 'large-object', 'resource_id': f'postgresql:large-object/{oid}',
            'display_name': str(oid), 'extensions': {'postgresql': {'native': {'oid': oid, 'name': str(oid)}}}}


def run(live, operation_id, values=None, oid=None, kind='large-object', confirmed=True):
    provider, route = live
    operation = OPERATIONS[f'{operation_id}@{kind}']
    resource = target(oid) if oid is not None else None
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
