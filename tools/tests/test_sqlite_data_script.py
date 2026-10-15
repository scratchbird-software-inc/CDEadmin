"""SQLite native SQL data export preserves storage classes and never writes."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider, _create_client, _resource_id


def test_bounded_native_sql_export_roundtrips_exact_values(tmp_path):
    path = tmp_path / 'export.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE "data:x" (id INTEGER PRIMARY KEY, body BLOB, text_value TEXT, real_value REAL)')
        connection.execute('INSERT INTO "data:x" VALUES (?, ?, ?, ?)',
            (9223372036854775807, b'\x00\xff', "a\x00b'c", -0.0))
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        identity = _resource_id('table', ['main'], 'data:x')
        result = provider.export_data_script(route, identity, endpoint_id='ep', target_id='file')
        assert result['executed'] is False and result['rows'] == 1
        assert '9223372036854775807' in result['source']
        assert "X'00ff'" in result['source']
        assert 'char(0)' in result['source']
        clone = tmp_path / 'clone.sqlite'
        with sqlite3.connect(clone) as connection:
            connection.execute('CREATE TABLE "data:x" (id INTEGER PRIMARY KEY, body BLOB, text_value TEXT, real_value REAL)')
            connection.executescript(result['source'])
            assert connection.execute('SELECT id, body, text_value, real_value FROM "data:x"').fetchall() == [
                (9223372036854775807, b'\x00\xff', "a\x00b'c", -0.0)]
        with sqlite3.connect(path) as connection:
            assert connection.execute('SELECT count(*) FROM "data:x"').fetchone() == (1,)
        with pytest.raises(ValueError, match='ordinary user table'):
            provider.export_data_script(route, _resource_id('view', ['main'], 'data:x'),
                endpoint_id='ep', target_id='file')
    finally:
        provider.client.close()
