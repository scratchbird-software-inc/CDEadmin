"""DuckDB tier 2/3 database operations round-trip through the OperationDialog's draft."""
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

duckdb = pytest.importorskip('duckdb')
pytest.importorskip('pyarrow')

from pgadmin.cdeadmin.providers.duckdb.provider import ADMINISTRATION, _create_client, _resources  # noqa: E402
from ui_descriptor_roundtrip import engine_operations, operation_draft  # noqa: E402

OPERATIONS = engine_operations('duckdb')


@pytest.fixture
def live(tmp_path):
    path = tmp_path / 'ops.duckdb'
    connection = duckdb.connect(str(path))
    connection.execute('CREATE TABLE owner(id INTEGER PRIMARY KEY, label VARCHAR)')
    connection.execute("INSERT INTO owner VALUES (1, 'a')")
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    client = _create_client()
    try:
        database = next(row for row in _resources(connection, {}) if row['resource_kind'] == 'database')
        yield path, route, client, connection, database
    finally:
        client.close()
        connection.close()


def run(client, route, target, operation_id, values=None):
    operation = OPERATIONS[f'{operation_id}@database']
    draft = operation_draft(operation, values, confirmation=route['database'])
    request = {'resource_kind': 'database', 'operation_id': operation_id, 'target_resource': target,
               '_provider_route': route, 'draft': draft}
    assert ADMINISTRATION.validate(request)['errors'] == [], operation_id
    planned = ADMINISTRATION.plan(request)
    result = ADMINISTRATION.apply(client, planned)
    assert result['accepted'], (operation_id, result)
    return planned, result


@pytest.mark.parametrize('operation_id', ['checkpoint', 'force_checkpoint', 'vacuum', 'analyze'])
def test_maintenance_operations(live, operation_id):
    path, route, client, connection, database = live
    connection.close()  # DuckDB allows one writer per file
    planned, _result = run(client, route, database, operation_id)
    assert planned['command_preview']['statements'], operation_id


def test_export_and_import_operations(live):
    path, route, client, connection, database = live
    connection.close()
    directory = Path(route['filesystem_root']) / 'exported'
    run(client, route, database, 'export_database', {'directory': str(directory), 'format': 'PARQUET'})
    assert (directory / 'schema.sql').exists()
    fresh = Path(route['filesystem_root']) / 'fresh.duckdb'
    fresh_connection = duckdb.connect(str(fresh))
    fresh_database = next(row for row in _resources(fresh_connection, {}) if row['resource_kind'] == 'database')
    fresh_connection.close()
    run(client, {**route, 'database': str(fresh)}, fresh_database, 'import_database', {'directory': str(directory)})
    probe = duckdb.connect(str(fresh))
    assert probe.execute('SELECT count(*) FROM owner').fetchone() == (1,)
    probe.close()


def test_every_declared_database_operation_is_exercised():
    declared = {key.split('@')[0] for key, op in OPERATIONS.items() if op['resource_kind'] == 'database'}
    exercised = {'checkpoint', 'force_checkpoint', 'vacuum', 'analyze', 'export_database', 'import_database'}
    # update_extensions needs network access to the extension repository; it is not round-tripped here.
    assert declared - {'update_extensions'} == exercised
