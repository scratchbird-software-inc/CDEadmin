"""DuckDB DDN data capture sees a bounded committed native relation snapshot."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider, _create_client, _resource_id
from pgadmin.cdeadmin.sdk import RelationalClientError


def test_native_data_capture_exact_values_bounds_and_transaction_isolation(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path / 'owned.duckdb'
    owner = duckdb.connect(str(path))
    owner.execute('CREATE SCHEMA "s:x"')
    owner.execute('CREATE TABLE "s:x"."t:y" (id INTEGER, amount DECIMAL(20,3), payload BLOB)')
    owner.execute("INSERT INTO \"s:x\".\"t:y\" VALUES (1, 1.230, X'1020'), (2, NULL, NULL)")
    owner.execute('BEGIN TRANSACTION')
    owner.execute('INSERT INTO "s:x"."t:y" VALUES (3, 3.000, NULL)')
    provider = DuckDBPilotProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    identity = _resource_id('table', [path.stem, 's:x'], 't:y')
    try:
        result = provider.capture_data(route, identity, endpoint_id='ep', target_id='owned', row_limit=1)
        assert result['acquisition']['rows'] == 1
        assert result['acquisition']['more_rows_observed']
        assert result['snapshot']['format'] == 'ddn-source-workspace@1'
        assert [column['name'] for column in result['columns']] == ['id', 'amount', 'payload']
        assert '1.230' in json.dumps(result['snapshot'])
        assert owner.execute('SELECT COUNT(*) FROM "s:x"."t:y"').fetchone() == (3,)
        with pytest.raises(ValueError, match='row budget'):
            provider.capture_data(route, identity, endpoint_id='ep', target_id='owned',
                                  mode='full', row_limit=1)
        owner.execute('ROLLBACK')
        assert owner.execute('SELECT COUNT(*) FROM "s:x"."t:y"').fetchone() == (2,)
        assert provider.client._connections == []
    finally:
        provider.client.close(); owner.close()


def test_invalid_or_missing_file_refuses_before_connection(tmp_path):
    client = Mock()
    provider = DuckDBPilotProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), client)
    route = {'database': str(tmp_path / 'missing.duckdb'), 'filesystem_root': str(tmp_path)}
    for identity in ('table:main:s:t', _resource_id('table', ['wrong', 'main'], 't')):
        with pytest.raises((ValueError, RelationalClientError)):
            provider.capture_data(route, identity, endpoint_id='ep', target_id='owned')
    client._connect.assert_not_called()
