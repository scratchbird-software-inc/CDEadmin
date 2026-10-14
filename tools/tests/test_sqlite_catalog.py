"""SQLite native catalog identity, isolation and DDN exchange."""

import json
from pathlib import Path
import sqlite3
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import (
    SQLiteProvider, _create_client, _resources)
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog


def test_catalog_identity_and_native_parentage_with_punctuation():
    connection = sqlite3.connect(':memory:')
    try:
        connection.executescript('''
            CREATE TABLE "a:b"("id:x" INTEGER PRIMARY KEY, "value" TEXT UNIQUE);
            CREATE TABLE "a"("b:id:x" INTEGER);
            CREATE INDEX "ix:a" ON "a:b"("value");
            CREATE UNIQUE INDEX "ix:unique" ON "a:b"("value" COLLATE NOCASE DESC);
            CREATE TRIGGER "tr:a" AFTER INSERT ON "a:b"
              BEGIN UPDATE "a:b" SET "value"="value" WHERE "id:x"=NEW."id:x"; END;
        ''')
        rows = _resources(connection, {})
        assert len({row['resource_id'] for row in rows}) == len(rows)
        table = next(row for row in rows if row['resource_kind'] == 'table'
                     and row['display_name'] == 'a:b')
        children = [row for row in rows if row['native'].get(
            'navigator_parent_resource_id') == table['resource_id']]
        assert {row['display_name'] for row in children} >= {
            'id:x', 'value', 'ix:a', 'tr:a'}
        assert table['native']['indexes'][0]['resource_id'] in {
            row['resource_id'] for row in children}
        assert table['native']['triggers'][0]['resource_id'] in {
            row['resource_id'] for row in children}
        unique = next(index for index in table['native']['indexes']
                      if index['name'] == 'ix:unique')
        assert unique['unique']
        assert unique['keys'][0]['collation'] == 'NOCASE'
        assert unique['keys'][0]['descending']
        assert any(item['constraint_type'] == 'UNIQUE'
                   for item in table['native']['constraints'])
    finally:
        connection.close()


def test_virtual_table_shadow_descendants_are_not_user_objects(tmp_path):
    path = tmp_path / 'fts.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE VIRTUAL TABLE search USING fts5(content)')
    provider = SQLiteProvider(SimpleNamespace(),
        SimpleNamespace(require=Mock()), _create_client())
    try:
        route = {'database': str(path), 'filesystem_root': str(tmp_path)}
        user_rows = provider.capture_catalog(route)['resources']
        all_rows = provider.capture_catalog(route, include_system=True)['resources']
        assert any(row['display_name'] == 'search' and row['resource_kind'] == 'fts-table'
                   for row in user_rows)
        shadow_names = {'search_data', 'search_idx', 'search_content', 'search_docsize', 'search_config'}
        assert not any(row['display_name'] in shadow_names for row in user_rows)
        shadow = [row for row in all_rows if row['display_name'] in shadow_names]
        assert shadow and all(row['native']['system_object'] for row in shadow)
        for item in all_rows:
            parent = item['native'].get('navigator_parent_resource_id')
            if parent in {row['resource_id'] for row in shadow}:
                assert item['native']['system_object'] is True
    finally:
        provider.client.close()


def test_owned_file_capture_and_ddn_roundtrip(tmp_path):
    path = tmp_path / 'native.sqlite'
    owner = sqlite3.connect(path)
    owner.execute('PRAGMA foreign_keys=ON')
    owner.executescript('''
        CREATE TABLE parent(id INTEGER PRIMARY KEY);
        CREATE TABLE child(id INTEGER PRIMARY KEY,
          parent_id INTEGER REFERENCES parent(id));
        INSERT INTO parent VALUES (1);
    ''')
    owner.execute('BEGIN')
    owner.execute('CREATE TABLE pending(secret TEXT)')
    client = _create_client()
    provider = SQLiteProvider(SimpleNamespace(),
        SimpleNamespace(require=Mock()), client)
    try:
        captured = provider.capture_catalog({
            'database': str(path), 'filesystem_root': str(tmp_path)})
        rows = captured['resources']
        assert captured['consistency'] == 'owned-native-read-transaction'
        assert not any(row['display_name'] == 'pending' for row in rows)
        child = next(row for row in rows if row['resource_kind'] == 'table'
                     and row['display_name'] == 'child')
        assert child['native']['constraints'][1]['referenced_table'] == 'parent'
        result = build_export(rows, endpoint_id='e', target_id='f',
                              generation=captured['generation'], refreshed=True,
                              engine='sqlite')
        assert result['diagram']['foreign_keys'] == 1
        runtime = (Path(__file__).resolve().parents[2] /
                   'web/pgadmin/static/vendor/ddn/current/ddn.mjs').as_uri()
        script = f'''import runtime from {json.dumps(runtime)};
          let input='';for await(const chunk of process.stdin)input+=chunk;
          const snapshot=JSON.parse(input), workspace=runtime.createWorkspace(snapshot.files);
          try {{const output=workspace.renderSync({{entry:snapshot.entry,view:snapshot.view}});
            if(output.diagnostics.some(x=>x.severity==='error'))throw Error(JSON.stringify(output.diagnostics));
            if(!output.svg.includes('child') || !output.svg.includes('parent'))throw Error('Missing native relation labels');
          }}finally{{workspace.destroy();}}'''
        subprocess.run(['node', '--input-type=module', '-e', script],
                       input=json.dumps(result['diagram']['snapshot']),
                       text=True, capture_output=True, timeout=15, check=True)
        document = read_catalog(json.dumps(result['snapshot']), engine='sqlite')
        assert document['rows'][child['resource_id']]['native']['ddl'].startswith(
            'CREATE TABLE child')
        assert client._connections == []
    finally:
        owner.rollback()
        owner.close()
        client.close()


def test_data_capture_preserves_exact_values_and_never_borrows_owner(tmp_path):
    path = tmp_path / 'data.sqlite'
    owner = sqlite3.connect(path)
    owner.execute('CREATE TABLE "sample:x"(id INTEGER PRIMARY KEY, content BLOB)')
    owner.executemany('INSERT INTO "sample:x" VALUES (?, ?)', [
        (1, b'\x00\xff'), (9223372036854775807, b'last')])
    owner.commit()
    owner.execute('BEGIN')
    owner.execute('INSERT INTO "sample:x" VALUES (3, ?)', (b'pending',))
    client = _create_client()
    provider = SQLiteProvider(SimpleNamespace(),
        SimpleNamespace(require=Mock()), client)
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    from pgadmin.cdeadmin.providers.sqlite.provider import _resource_id
    identity = _resource_id('table', ['main'], 'sample:x')
    try:
        captured = provider.capture_data(
            route, identity, endpoint_id='e', target_id='f',
            mode='full', row_limit=2)
        assert captured['acquisition']['rows'] == 2
        assert captured['acquisition']['more_rows_observed'] is False
        source = json.dumps(captured['snapshot'])
        assert '9223372036854775807' in source
        assert 'AP8=' in source
        assert 'pending' not in source
        assert owner.in_transaction
        assert client._connections == []
        with pytest.raises(ValueError, match='row budget'):
            provider.capture_data(route, identity, endpoint_id='e',
                                  target_id='f', mode='full', row_limit=1)
    finally:
        owner.rollback()
        owner.close()
        client.close()
