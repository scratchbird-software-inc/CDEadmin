"""Native catalog capture preserves ownership, bounds and attachment privacy."""
from types import SimpleNamespace
from unittest.mock import Mock
from copy import deepcopy
import json
import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb import catalog
from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider, _create_client
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.duckdb_schema_plan import plan


def test_attachment_options_and_foreign_locations_do_not_export_credentials():
    value = catalog.database_location("host=remote password='private words'", 'postgres',
        {'password': 'private words', 'encryption_key': 'key', 'read_only': True})
    assert value['path'] is None and value['path_redacted']
    assert value['options'] == {'read_only': True} and value['options_redacted']
    assert 'private' not in json.dumps(value) and 'key' not in json.dumps(value)
    assert catalog.database_location('/owned/file.duckdb', 'duckdb', {})['path'] == '/owned/file.duckdb'


def test_owned_capture_preserves_interactive_work_and_sequence_state(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path / 'owned.duckdb'
    owner = duckdb.connect(str(path))
    client = _create_client()
    provider = DuckDBPilotProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), client)
    try:
        owner.execute('CREATE TABLE committed(id INT PRIMARY KEY, amount DECIMAL(30,4))')
        owner.execute('CREATE SEQUENCE native_seq START 20')
        owner.execute('CREATE MACRO overloaded(x) AS x+1, (x,y) AS x+y')
        owner.execute('CREATE TYPE native_shape AS STRUCT(k INTEGER, l VARCHAR)')
        owner.execute('BEGIN TRANSACTION')
        owner.execute('INSERT INTO committed VALUES (7, 1.2300)')
        owner.execute('CREATE TEMP TABLE session_only(id INT)')
        result = provider.capture_catalog({'database': str(path), 'filesystem_root': str(tmp_path)})
        rows = result['resources']
        assert result['consistency'] == 'owned-native-transaction' and not result['complete']
        assert next(row for row in rows if row['display_name'] == 'overloaded')['native']['overload_count'] == 2
        native_type = next(row for row in rows if row['display_name'] == 'native_shape')
        assert native_type['native']['catalog_metadata']['resolved_type'] == (
            'STRUCT(k INTEGER, l VARCHAR)')
        design = build_export(rows, endpoint_id='endpoint-1', target_id='file-1',
            generation=result['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        assert design['rows'][native_type['resource_id']]['native']['catalog_metadata'][
            'resolved_type'] == 'STRUCT(k INTEGER, l VARCHAR)'
        assert not any(row['display_name'] == 'session_only' for row in rows)
        assert owner.execute('SELECT id FROM committed').fetchall() == [(7,)]
        assert owner.execute("SELECT nextval('native_seq')").fetchone() == (20,)
        owner.execute('ROLLBACK')
        assert owner.execute('SELECT COUNT(*) FROM committed').fetchone() == (0,)
        assert client._connections == []
        provider.permissions.require.assert_called_once_with('data_read', 'resource')
    finally:
        client.close(); owner.close()


@pytest.mark.parametrize('read_only', [False, True])
def test_macro_source_capture_preserves_optional_defaults_without_exporting_rows(
        tmp_path, monkeypatch, read_only):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path/'macro.duckdb'
    owner = duckdb.connect(str(path))
    owner.execute('CREATE TABLE payload(secret VARCHAR)')
    owner.execute("INSERT INTO payload VALUES ('private row value')")
    owner.execute('CREATE MACRO optional_arg(x, y := 5) AS x + y')
    owner.execute('CREATE SCHEMA custom')
    owner.execute('CREATE MACRO custom.overloaded(x) AS x + 1, (x, y) AS x + y')
    owner.close()
    monkeypatch.setattr(catalog.tempfile, 'tempdir', str(tmp_path))
    client = _create_client()
    provider = DuckDBPilotProvider(SimpleNamespace(),
        SimpleNamespace(require=Mock()), client)
    try:
        captured = provider.capture_catalog({'database': str(path),
            'filesystem_root': str(tmp_path), 'read_only': read_only},
            include_macro_source=True)
        macro = next(row for row in captured['resources']
            if row['resource_kind'] == 'macro' and row['display_name'] == 'optional_arg')
        assert 'y := 5' in macro['native']['source_ddl']
        overloaded = next(row for row in captured['resources']
            if row['resource_kind'] == 'macro' and row['display_name'] == 'overloaded')
        assert overloaded['display_path'][1] == 'custom'
        assert '(x, y) AS' in overloaded['native']['source_ddl']
        design = build_export(captured['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=captured['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        assert design['rows'][macro['resource_id']]['native']['source_ddl'] == (
            macro['native']['source_ddl'])
        exported = build_export(captured['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=captured['generation'], refreshed=True,
            engine='duckdb')
        decoded = read_catalog(json.dumps(exported['snapshot']), engine='duckdb')
        assert decoded['rows'][macro['resource_id']]['native']['source_ddl'] == (
            macro['native']['source_ddl'])
        assert 'private row value' not in json.dumps(captured)
        assert sorted(item.name for item in tmp_path.iterdir()) == ['macro.duckdb']
        observer = duckdb.connect(str(path), read_only=read_only)
        assert observer.execute('SELECT optional_arg(3)').fetchone()[0] == 8
        observer.close()
    finally:
        client.close()


def test_macro_source_capture_reads_the_original_catalog_snapshot(tmp_path, monkeypatch):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path/'snapshot.duckdb'
    setup = duckdb.connect(str(path))
    setup.execute('CREATE MACRO optional_arg(x, y := 2) AS x + y')
    setup.close()
    monkeypatch.setattr(catalog.tempfile, 'tempdir', str(tmp_path))
    reader = duckdb.connect(str(path))
    try:
        reader.execute('BEGIN TRANSACTION')
        assert reader.execute("SELECT count(*) FROM duckdb_functions() WHERE "
            "function_name='optional_arg'").fetchone()[0] == 1
        writer = duckdb.connect(str(path))
        writer.execute('CREATE OR REPLACE MACRO optional_arg(x, y := 3) AS x + y')
        writer.close()
        row = {'resource_kind': 'macro',
            'display_path': ['snapshot', 'main', 'optional_arg'],
            'display_name': 'optional_arg',
            'native': {'catalog_metadata': {'internal': False}}}
        catalog._capture_macro_source(reader, [row], lambda value: None)
        assert 'y := 2' in row['native']['source_ddl']
        assert reader.execute('SELECT current_database(), current_schema()').fetchone() == (
            'snapshot', 'main')
        reader.execute('ROLLBACK')
        assert reader.execute('SELECT optional_arg(1)').fetchone()[0] == 4
    finally:
        reader.close()


def test_transient_sequence_ownership_blocks_replacement_review(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path/'owned.duckdb'
    owner = duckdb.connect(str(path))
    client = _create_client()
    provider = DuckDBPilotProvider(SimpleNamespace(),
        SimpleNamespace(require=Mock()), client)
    try:
        owner.execute('CREATE TABLE owner_table(id INTEGER)')
        owner.execute('CREATE SEQUENCE owned_seq')
        owner.execute('ALTER SEQUENCE owned_seq OWNED BY owner_table')
        observed = provider.capture_catalog({
            'database': str(path), 'filesystem_root': str(tmp_path)})
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        sequence = next(row for row in baseline['rows'].values()
            if row['kind'] == 'sequence' and row['name'] == 'owned_seq')
        assert sequence['native']['catalog_metadata']['automatic_dependency_observed'] is True
        desired = deepcopy(baseline)
        changed = desired['rows'][sequence['resource_id']]['native']
        changed['catalog_metadata']['start_value'] = 20
        changed['ddl'] = (f'CREATE OR REPLACE SEQUENCE "{sequence["path"][0]}".'
            '"main"."owned_seq" START 20')
        changed['duckdb_change'] = {'action': 'replace-sequence',
            'reset_state_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert not preview['application_supported']
        assert 'automatic dependency' in preview['blockers'][0]['reason']
    finally:
        client.close(); owner.close()


def test_bound_capture_refuses_active_transactions_and_overflow_without_leaving_transaction(tmp_path, monkeypatch):
    duckdb = pytest.importorskip('duckdb')
    connection = duckdb.connect(str(tmp_path / 'owned.duckdb'))
    try:
        connection.execute('BEGIN TRANSACTION')
        with pytest.raises(duckdb.TransactionException): catalog.capture(connection)
        connection.execute('ROLLBACK')
        monkeypatch.setattr(catalog, 'MAX_FACTS', 1)
        with pytest.raises(ValueError, match='20,000'): catalog.capture(connection)
        connection.execute('BEGIN TRANSACTION'); connection.execute('ROLLBACK')
    finally: connection.close()


def test_missing_and_in_memory_routes_do_not_create_unrelated_databases(tmp_path):
    client = Mock()
    provider = DuckDBPilotProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), client)
    for route in ({'database': ':memory:', 'allow_memory': True},
                  {'database': str(tmp_path/'absent.duckdb'), 'filesystem_root': str(tmp_path)}):
        with pytest.raises(RelationalClientError): provider.capture_catalog(route)
    client._connect.assert_not_called()
    assert not (tmp_path/'absent.duckdb').exists()


def test_catalog_authorization_precedes_file_observation(tmp_path):
    permissions = SimpleNamespace(require=Mock(side_effect=PermissionError('denied')))
    provider = DuckDBPilotProvider(SimpleNamespace(), permissions, Mock())
    with pytest.raises(PermissionError):
        provider.capture_catalog({'database': str(tmp_path/'absent.duckdb'), 'filesystem_root': str(tmp_path)})
    provider.client._connect.assert_not_called()
