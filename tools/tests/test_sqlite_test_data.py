"""SQLite recipes preserve exact values and cannot write during generation."""

import base64
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider, _create_client
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.sqlite_test_data import generate, template


def test_sqlite_recipe_is_scoped_and_generates_native_insert_script(tmp_path):
    path = tmp_path / 'recipe.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE "a:b" (id INTEGER PRIMARY KEY, body BLOB, note TEXT)')
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    try:
        captured = provider.capture_catalog({'database': str(path), 'filesystem_root': str(tmp_path)})
        model = build_export(captured['resources'], endpoint_id='endpoint', target_id='file',
            generation=captured['generation'], refreshed=True, engine='sqlite', native_model=True)
        available = template(model)
        table = next(row for row in available['tables'] if row['name'] == 'a:b')
        recipe = {'format': available['format'], 'scope': available['scope'],
            'seed': 17, 'tables': [{'table': table['resource_id'], 'count': 2,
            'columns': {'id': {'kind': 'sequential', 'start': '9223372036854775806', 'step': '1'},
                'body': {'kind': 'constant', 'value': {'type': 'binary',
                    'value': base64.b64encode(b'\x00\xff').decode()}},
                'note': {'kind': 'constant', 'value': "a'b"}}}]}
        result = generate(model, recipe)
        assert result['executed'] is False
        assert '9223372036854775807' in result['source']
        assert "X'00ff'" in result['source']
        with sqlite3.connect(path) as connection:
            assert connection.execute('SELECT count(*) FROM "a:b"').fetchone()[0] == 0
            connection.executescript(result['source'])
            assert connection.execute('SELECT id, body, note FROM "a:b" ORDER BY id').fetchall() == [
                (9223372036854775806, b'\x00\xff', "a'b"),
                (9223372036854775807, b'\x00\xff', "a'b")]
        with pytest.raises(ValueError, match='another endpoint'):
            generate(model, {**recipe, 'scope': {'endpoint_id': 'other', 'database_target_id': 'file'}})
        with pytest.raises(ValueError, match='Unknown or generated'):
            generate(model, {**recipe, 'tables': [{**recipe['tables'][0],
                'columns': {'wrong': {'kind': 'default'}}}]})
    finally:
        provider.client.close()
