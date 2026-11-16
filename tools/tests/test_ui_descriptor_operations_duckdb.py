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
    # These original-session dialogs are exercised by the typed task adapter,
    # its native regression suite and authenticated HTTP, rather than file apply.
    # An explicit inventory keeps new undeclared qualification gaps detectable.
    exercised.update({
        'editor_attachment_inventory', 'editor_attachment_review_attach',
        'editor_attachment_review_detach', 'editor_attachment_review_rename', 'editor_attachment_apply',
        'editor_attachment_receipt', 'editor_attachment_discard',
        'editor_extension_inventory', 'editor_extension_review_install',
        'editor_extension_review_load', 'editor_extension_apply', 'editor_extension_receipt',
        'editor_copy_inventory', 'editor_copy_review', 'editor_copy_apply',
        'editor_copy_receipt', 'editor_copy_cancel', 'editor_copy_discard',
        'editor_secret_inventory', 'editor_secret_review_create', 'editor_secret_review_drop',
        'editor_secret_apply', 'editor_secret_receipts',
        'editor_receipt_list', 'editor_receipt_get', 'editor_receipt_release',
    })
    assert declared - {'update_extensions'} == exercised
