"""Native catalog capture preserves ownership, bounds and attachment privacy."""
from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb import catalog
from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider, _create_client
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export


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
