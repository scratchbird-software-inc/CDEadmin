"""SQLite three-way DDN plan admits only exact native additive SQL."""

from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import _resource_id, SQLiteProvider, _create_client
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import plan
from pgadmin.cdeadmin.workspace.sqlite_schema_apply import SQLiteSchemaApplications, apply_review
from pgadmin.cdeadmin.workspace.sqlite_rebuild import _autoincrement_table
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog


def _model():
    root = _resource_id('database', [], 'main')
    return {'provenance': {'mapping': 'scratchrobin.sqlite.catalog@1',
        'endpoint_id': 'endpoint', 'database_target_id': 'file'},
        'rows': {root: {'resource_id': root, 'kind': 'database', 'path': ['main'],
            'name': 'main', 'system': 'false', 'native': {'system_object': False}}}}


def test_autoincrement_detection_uses_native_schema_not_text_literals():
    assert _autoincrement_table(
        'CREATE TABLE "main"."literal"(id INTEGER PRIMARY KEY, '
        "note TEXT DEFAULT 'AUTOINCREMENT')") is False
    assert _autoincrement_table(
        'CREATE TABLE "main"."real"(id INTEGER PRIMARY KEY AUTOINCREMENT)') is True


def test_additive_create_is_exactly_scoped_and_nonexecuting():
    baseline = _model()
    desired = deepcopy(baseline)
    identity = _resource_id('table', ['main'], 'new:name')
    desired['rows'][identity] = {'resource_id': identity, 'kind': 'table',
        'path': ['main', 'new:name'], 'name': 'new:name', 'system': 'false',
        'native': {'system_object': False,
            'ddl': 'CREATE TABLE "main"."new:name" (id INTEGER PRIMARY KEY)'}}
    connection = sqlite3.connect(':memory:')
    try:
        result = plan(baseline, desired, deepcopy(baseline), connection)
        assert result['ready_for_review']
        assert result['operations'][0]['source'] == desired['rows'][identity]['native']['ddl']
        assert not connection.execute("SELECT name FROM sqlite_schema WHERE name='new:name'").fetchall()
        desired['rows'][identity]['native']['ddl'] = 'CREATE TABLE "main"."other" (id INTEGER)'
        rejected = plan(baseline, desired, deepcopy(baseline), connection)
        assert not rejected['ready_for_review'] and rejected['blockers']
        desired['rows'][identity]['native']['ddl'] = 'CREATE TABLE "main"."new:name" (id INTEGER); DROP TABLE x;'
        rejected = plan(baseline, desired, deepcopy(baseline), connection)
        assert not rejected['ready_for_review'] and rejected['blockers']
    finally:
        connection.close()


def test_missing_desired_object_never_authorizes_deletion():
    baseline = _model()
    table = _resource_id('table', ['main'], 'old')
    baseline['rows'][table] = {'resource_id': table, 'kind': 'table',
        'path': ['main', 'old'], 'name': 'old', 'system': 'false',
        'native': {'system_object': False, 'ddl': 'CREATE TABLE old(id INTEGER)'}}
    live = deepcopy(baseline)
    connection = sqlite3.connect(':memory:')
    try:
        result = plan(baseline, _model(), live, connection)
        assert not result['application_supported']
        assert result['operations'] == []
        assert 'deletion instruction' in result['blockers'][0]['reason']
    finally:
        connection.close()


def test_reviewed_create_applies_once_and_rediscovery_verifies(tmp_path):
    path = tmp_path / 'design.sqlite'
    with sqlite3.connect(path):
        pass
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    baseline = _model()
    desired = deepcopy(baseline)
    identity = _resource_id('table', ['main'], 'designed')
    desired['rows'][identity] = {'resource_id': identity, 'kind': 'table',
        'path': ['main', 'designed'], 'name': 'designed', 'system': 'false',
        'native': {'system_object': False,
            'ddl': 'CREATE TABLE "main"."designed" (id INTEGER PRIMARY KEY)'}}
    connection = sqlite3.connect(path)
    try:
        preview = plan(baseline, desired, deepcopy(baseline), connection)
    finally:
        connection.close()
    info = path.stat()
    applications = SQLiteSchemaApplications(tmp_path / 'receipts.json')
    try:
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        request = {'review_id': receipt['review_id'],
                   'review_digest': receipt['review_digest'], 'confirmed': True}
        first = applications.apply(request, 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert first['state'] == 'committed', first.get('outcome')
        assert first['outcome']['rediscovery_verified'] is True
        second = applications.apply(request, 'owner', 'binding',
            lambda _record: (_ for _ in ()).throw(AssertionError('must not redispatch')))
        assert second['state'] == 'committed'
        with sqlite3.connect(path) as observer:
            assert observer.execute("SELECT count(*) FROM sqlite_schema WHERE name='designed'").fetchone() == (1,)
    finally:
        provider.client.close()


def test_reviewed_index_and_trigger_bind_existing_table(tmp_path):
    path = tmp_path / 'children.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE owned(a INTEGER)')
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        observed = provider.capture_catalog(route)['resources']
        baseline = {'provenance': {'mapping': 'scratchrobin.sqlite.catalog@1',
            'endpoint_id': 'endpoint', 'database_target_id': 'file'},
            'rows': {row['resource_id']: {'resource_id': row['resource_id'],
                'kind': row['resource_kind'], 'path': row['display_path'],
                'name': row['display_name'], 'system': 'false', 'native': row['native']}
                for row in observed}}
        desired = deepcopy(baseline)
        for kind, name, source in (
            ('index', 'by_a', 'CREATE INDEX "main"."by_a" ON "owned"(a)'),
            ('trigger', 'after_owned', 'CREATE TRIGGER "main"."after_owned" AFTER INSERT ON "owned" BEGIN SELECT NEW.a; END')):
            identity = _resource_id(kind, ['main', 'owned'], name)
            desired['rows'][identity] = {'resource_id': identity, 'kind': kind,
                'path': ['main', 'owned', name], 'name': name, 'system': 'false',
                'native': {'system_object': False, 'ddl': source,
                    'catalog_metadata': {'table_name': 'owned'}}}
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, deepcopy(baseline), connection)
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'child-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        result = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed', result.get('outcome')
    finally:
        provider.client.close()


def test_public_ddn_roundtrip_can_describe_an_additive_sqlite_table(tmp_path):
    path = tmp_path / 'ddn.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY)')
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)
        original = build_export(captured['resources'], endpoint_id='endpoint', target_id='file',
            generation=captured['generation'], refreshed=True, engine='sqlite')
        new_resource = {'resource_id': _resource_id('table', ['main'], 'added'),
            'resource_kind': 'table', 'display_name': 'added', 'display_path': ['main', 'added'],
            'generation': captured['generation'], 'native': {'system_object': False,
                'ddl': 'CREATE TABLE "main"."added" (id INTEGER PRIMARY KEY)',
                'catalog_metadata': {'table_name': 'added', 'table_list_type': 'table'}}}
        edited = build_export([*captured['resources'], new_resource],
            endpoint_id='endpoint', target_id='file', generation=captured['generation'],
            refreshed=True, engine='sqlite')
        baseline = read_catalog(json.dumps(original['snapshot']), engine='sqlite')
        desired = read_catalog(json.dumps(edited['snapshot']), engine='sqlite')
        live = build_export(captured['resources'], endpoint_id='endpoint', target_id='file',
            generation=captured['generation'], refreshed=True, engine='sqlite', native_model=True)
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, live, connection)
        assert preview['ready_for_review'], preview
        assert len(preview['operations']) == 1
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'ddn-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        applied = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert applied['state'] == 'committed', applied.get('outcome')
    finally:
        provider.client.close()


def test_failed_multi_create_rolls_back_prior_sqlite_ddl(tmp_path):
    path = tmp_path / 'atomic.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE owned(a INTEGER)')
        connection.executemany('INSERT INTO owned VALUES (?)', [(1,), (1,)])
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        for kind, name, path_parts, source, owner in (
            ('view', 'new_view', ['main', 'new_view'],
             'CREATE VIEW "main"."new_view" AS SELECT a FROM owned', None),
            ('index', 'unique_a', ['main', 'owned', 'unique_a'],
             'CREATE UNIQUE INDEX "main"."unique_a" ON "owned"(a)', 'owned')):
            identity = _resource_id(kind, path_parts[:-1], name)
            desired['rows'][identity] = {'resource_id': identity, 'kind': kind,
                'path': path_parts, 'name': name, 'system': 'false',
                'native': {'system_object': False, 'ddl': source,
                    'catalog_metadata': {'table_name': owner} if owner else {}}}
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection)
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'atomic-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        result = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert result['state'] == 'rolled_back', result.get('outcome')
        with sqlite3.connect(path) as observer:
            assert not observer.execute("SELECT 1 FROM sqlite_schema WHERE name='new_view'").fetchall()
            assert not observer.execute("SELECT 1 FROM sqlite_schema WHERE name='unique_a'").fetchall()
    finally:
        provider.client.close()


def test_reviewed_add_column_preserves_existing_rows(tmp_path):
    path = tmp_path / 'add-column.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE owned(id INTEGER PRIMARY KEY)')
        connection.execute('INSERT INTO owned VALUES (7)')
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('column', ['main', 'owned'], 'added')
        desired['rows'][identity] = {'resource_id': identity, 'kind': 'column',
            'path': ['main', 'owned', 'added'], 'name': 'added', 'system': 'false',
            'native': {'system_object': False,
                'ddl': 'ALTER TABLE "main"."owned" ADD COLUMN "added" TEXT DEFAULT \'hi\'',
                'catalog_metadata': {'data_type': 'TEXT', 'nullable': True,
                    'default': "'hi'", 'hidden': 0, 'primary_key_position': 0}}}
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection)
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'column-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        result = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed', result.get('outcome')
        with sqlite3.connect(path) as observer:
            assert observer.execute('SELECT id, added FROM owned').fetchall() == [(7, 'hi')]
    finally:
        provider.client.close()


def test_explicit_table_deletion_removes_only_selected_native_tree(tmp_path):
    path = tmp_path / 'deletion.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE doomed(id INTEGER PRIMARY KEY, email TEXT UNIQUE)')
        connection.execute('CREATE TABLE keep(id INTEGER PRIMARY KEY)')
        connection.execute('INSERT INTO doomed VALUES (1, \'a\')')
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('table', ['main'], 'doomed')
        for child_id, row in list(desired['rows'].items()):
            if row['path'][:2] == ['main', 'doomed']:
                del desired['rows'][child_id]
        with sqlite3.connect(path) as connection:
            absent_intent = plan(baseline, desired, baseline, connection)
            preview = plan(baseline, desired, baseline, connection,
                           deletions=[identity])
        assert not absent_intent['application_supported']
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'deletion-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        result = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed', result.get('outcome')
        with sqlite3.connect(path) as observer:
            assert not observer.execute("SELECT 1 FROM sqlite_schema WHERE name='doomed'").fetchall()
            assert observer.execute("SELECT 1 FROM sqlite_schema WHERE name='keep'").fetchall()
    finally:
        provider.client.close()


def test_isolated_table_rebuild_preserves_rows_and_rowids(tmp_path):
    path = tmp_path / 'rebuild.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE owned(id INTEGER PRIMARY KEY, note TEXT)')
        connection.executemany('INSERT INTO owned VALUES (?, ?)', [(7, 'one'), (99, 'two')])
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('table', ['main'], 'owned')
        desired['rows'][identity]['native']['ddl'] = (
            'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY, note TEXT, added TEXT DEFAULT \'ok\')')
        added_id = _resource_id('column', ['main', 'owned'], 'added')
        facts = {'ordinal_position': 2, 'data_type': 'TEXT', 'nullable': True,
            'default': "'ok'", 'primary_key_position': 0, 'hidden': 0}
        desired['rows'][identity]['native']['columns'].append({
            'resource_id': added_id, 'name': 'added', **facts})
        desired['rows'][added_id] = {'resource_id': added_id, 'kind': 'column',
            'path': ['main', 'owned', 'added'], 'name': 'added', 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': facts}}
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection, rebuilds=[identity])
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'rebuild-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        result = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed', result.get('outcome')
        with sqlite3.connect(path) as observer:
            assert observer.execute('SELECT rowid, id, note, added FROM owned ORDER BY id').fetchall() == [
                (7, 7, 'one', 'ok'), (99, 99, 'two', 'ok')]
    finally:
        provider.client.close()


def test_rebuild_refuses_new_child_index_after_review(tmp_path):
    path = tmp_path / 'rebuild-race.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE owned(id INTEGER PRIMARY KEY, note TEXT)')
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('table', ['main'], 'owned')
        desired['rows'][identity]['native']['ddl'] = (
            'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY, note TEXT, added TEXT)')
        added_id = _resource_id('column', ['main', 'owned'], 'added')
        facts = {'ordinal_position': 2, 'data_type': 'TEXT', 'nullable': True,
            'default': None, 'primary_key_position': 0, 'hidden': 0}
        desired['rows'][identity]['native']['columns'].append({
            'resource_id': added_id, 'name': 'added', **facts})
        desired['rows'][added_id] = {'resource_id': added_id, 'kind': 'column',
            'path': ['main', 'owned', 'added'], 'name': 'added', 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': facts}}
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection, rebuilds=[identity])
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'race-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE INDEX late ON owned(note)')
        result = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert result['state'] == 'not_dispatched', result.get('outcome')
        with sqlite3.connect(path) as observer:
            assert [row[1] for row in observer.execute('PRAGMA table_info(owned)')] == ['id', 'note']
            assert observer.execute("SELECT 1 FROM sqlite_schema WHERE name='late'").fetchall()
    finally:
        provider.client.close()


def test_reviewed_rebuild_preserves_existing_index_and_trigger(tmp_path):
    path = tmp_path / 'preserved-children.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE owned(id INTEGER PRIMARY KEY, note TEXT)')
        connection.execute('CREATE INDEX by_note ON owned(note)')
        connection.execute('CREATE TRIGGER touch AFTER UPDATE ON owned BEGIN SELECT NEW.id; END')
        connection.execute("INSERT INTO owned VALUES (17, 'kept')")
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('table', ['main'], 'owned')
        desired['rows'][identity]['native']['ddl'] = (
            'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY, note TEXT, extra TEXT)')
        added_id = _resource_id('column', ['main', 'owned'], 'extra')
        facts = {'ordinal_position': 2, 'data_type': 'TEXT', 'nullable': True,
            'default': None, 'primary_key_position': 0, 'hidden': 0}
        desired['rows'][identity]['native']['columns'].append({
            'resource_id': added_id, 'name': 'extra', **facts})
        desired['rows'][added_id] = {'resource_id': added_id, 'kind': 'column',
            'path': ['main', 'owned', 'extra'], 'name': 'extra', 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': facts}}
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection, rebuilds=[identity])
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'preserved-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        result = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed', result.get('outcome')
        with sqlite3.connect(path) as connection:
            assert connection.execute('SELECT rowid, note, extra FROM owned').fetchall() == [(17, 'kept', None)]
            assert {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type IN ('index', 'trigger')")} == {'by_note', 'touch'}
            connection.execute("UPDATE owned SET note='changed' WHERE id=17")
    finally:
        provider.client.close()


def test_reviewed_fts5_creation_and_explicit_removal(tmp_path):
    path = tmp_path / 'fts.sqlite'
    with sqlite3.connect(path):
        pass
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('fts-table', ['main'], 'docs')
        desired['rows'][identity] = {'resource_id': identity, 'kind': 'fts-table',
            'path': ['main', 'docs'], 'name': 'docs', 'system': 'false',
            'native': {'system_object': False,
                'ddl': 'CREATE VIRTUAL TABLE "main"."docs" USING fts5(title, body)',
                'catalog_metadata': {'table_list_type': 'virtual'}}}
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection)
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'fts-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        applied = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert applied['state'] == 'committed', applied.get('outcome')
        with sqlite3.connect(path) as connection:
            connection.execute("INSERT INTO docs(title, body) VALUES ('one', 'indexed text')")
            assert connection.execute("SELECT title FROM docs WHERE docs MATCH 'indexed'").fetchone() == ('one',)
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        for child_id, row in list(desired['rows'].items()):
            if row['path'][:2] == ['main', 'docs']:
                del desired['rows'][child_id]
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection, deletions=[identity])
        assert preview['ready_for_review'], preview
        info = path.stat()
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        removed = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert removed['state'] == 'committed', removed.get('outcome')
        with sqlite3.connect(path) as connection:
            assert not connection.execute("SELECT 1 FROM sqlite_schema WHERE name='docs'").fetchall()
    finally:
        provider.client.close()


def test_rebuild_preserves_autoincrement_high_water_after_deleted_rows(tmp_path):
    path = tmp_path / 'sequence.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE owned(id INTEGER PRIMARY KEY AUTOINCREMENT, note TEXT)')
        connection.execute("INSERT INTO owned(id, note) VALUES (100, 'old')")
        connection.execute('DELETE FROM owned')
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('table', ['main'], 'owned')
        desired['rows'][identity]['native']['ddl'] = (
            'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY AUTOINCREMENT, note TEXT, extra TEXT)')
        added_id = _resource_id('column', ['main', 'owned'], 'extra')
        facts = {'ordinal_position': 2, 'data_type': 'TEXT', 'nullable': True,
            'default': None, 'primary_key_position': 0, 'hidden': 0}
        desired['rows'][identity]['native']['columns'].append({
            'resource_id': added_id, 'name': 'extra', **facts})
        desired['rows'][added_id] = {'resource_id': added_id, 'kind': 'column',
            'path': ['main', 'owned', 'extra'], 'name': 'extra', 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': facts}}
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection, rebuilds=[identity])
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'sequence-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        result = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed', result.get('outcome')
        with sqlite3.connect(path) as connection:
            assert connection.execute("SELECT seq FROM sqlite_sequence WHERE name='owned'").fetchone() == (100,)
            connection.execute("INSERT INTO owned(note) VALUES ('next')")
            assert connection.execute('SELECT id FROM owned').fetchone() == (101,)
    finally:
        provider.client.close()


def test_table_drop_refuses_to_leave_retained_view_invalid(tmp_path):
    path = tmp_path / 'dependencies.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE owned(id INTEGER PRIMARY KEY)')
        connection.execute('CREATE VIEW retained AS SELECT id FROM owned')
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('table', ['main'], 'owned')
        for child_id, row in list(desired['rows'].items()):
            if row['path'][:2] == ['main', 'owned']:
                del desired['rows'][child_id]
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection, deletions=[identity])
        assert not preview['ready_for_review']
        assert any('Retained views' in item['reason'] for item in preview['blockers'])
        with sqlite3.connect(path) as connection:
            assert connection.execute('SELECT id FROM retained').fetchall() == []
    finally:
        provider.client.close()


def test_explicit_column_rename_rebuild_retains_native_values(tmp_path):
    path = tmp_path / 'column-rename.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE owned(id INTEGER PRIMARY KEY, old_note TEXT)')
        connection.execute("INSERT INTO owned VALUES (3, 'retained')")
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('table', ['main'], 'owned')
        desired['rows'][identity]['native']['ddl'] = (
            'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY, new_note TEXT)')
        old_id = _resource_id('column', ['main', 'owned'], 'old_note')
        new_id = _resource_id('column', ['main', 'owned'], 'new_note')
        old_column = desired['rows'].pop(old_id)
        old_column.update(resource_id=new_id, name='new_note',
                          path=['main', 'owned', 'new_note'])
        desired['rows'][new_id] = old_column
        native_column = next(column for column in desired['rows'][identity]['native']['columns']
                             if column['name'] == 'old_note')
        native_column.update(resource_id=new_id, name='new_note')
        with sqlite3.connect(path) as connection:
            absent_intent = plan(baseline, desired, baseline, connection,
                                 rebuilds=[identity])
            preview = plan(baseline, desired, baseline, connection,
                rebuilds=[identity], column_renames=[{
                    'table': identity, 'from': 'old_note', 'to': 'new_note'}])
        assert not absent_intent['ready_for_review']
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'rename-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        result = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed', result.get('outcome')
        with sqlite3.connect(path) as connection:
            assert connection.execute('SELECT id, new_note FROM owned').fetchall() == [(3, 'retained')]
    finally:
        provider.client.close()


def test_native_authorizer_rejects_comment_spoofed_trigger_owner(tmp_path):
    path = tmp_path / 'trigger-owner.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE owned(id INTEGER)')
        connection.execute('CREATE TABLE other(id INTEGER)')
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('trigger', ['main', 'owned'], 'misbound')
        desired['rows'][identity] = {'resource_id': identity, 'kind': 'trigger',
            'path': ['main', 'owned', 'misbound'], 'name': 'misbound',
            'system': 'false', 'native': {'system_object': False,
                'ddl': 'CREATE TRIGGER "main"."misbound" AFTER INSERT '
                       '/* ON "owned" */ ON "other" BEGIN SELECT NEW.id; END',
                'catalog_metadata': {'table_name': 'owned'}}}
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection)
        assert not preview['ready_for_review']
        assert any('different object or owner' in item['reason']
                   for item in preview['blockers'])
        with sqlite3.connect(path) as connection:
            assert not connection.execute(
                "SELECT 1 FROM sqlite_schema WHERE name='misbound'").fetchall()
    finally:
        provider.client.close()


def test_reviewed_rebuild_preserves_inbound_foreign_key_rows(tmp_path):
    path = tmp_path / 'foreign-key.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY, note TEXT)')
        connection.execute('CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id))')
        connection.execute("INSERT INTO parent VALUES (7, 'kept')")
        connection.execute('INSERT INTO child VALUES (1, 7)')
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('table', ['main'], 'parent')
        desired['rows'][identity]['native']['ddl'] = (
            'CREATE TABLE "main"."parent"(id INTEGER PRIMARY KEY, note TEXT, extra TEXT)')
        added_id = _resource_id('column', ['main', 'parent'], 'extra')
        facts = {'ordinal_position': 2, 'data_type': 'TEXT', 'nullable': True,
            'default': None, 'primary_key_position': 0, 'hidden': 0}
        desired['rows'][identity]['native']['columns'].append({
            'resource_id': added_id, 'name': 'extra', **facts})
        desired['rows'][added_id] = {'resource_id': added_id, 'kind': 'column',
            'path': ['main', 'parent', 'extra'], 'name': 'extra', 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': facts}}
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection, rebuilds=[identity])
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'foreign-key-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        result = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed', result.get('outcome')
        with sqlite3.connect(path) as connection:
            connection.execute('PRAGMA foreign_keys=ON')
            assert connection.execute('SELECT id, note, extra FROM parent').fetchall() == [(7, 'kept', None)]
            assert connection.execute('SELECT parent_id FROM child').fetchall() == [(7,)]
            assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    finally:
        provider.client.close()


def test_reviewed_rebuild_preserves_unchanged_outbound_foreign_key(tmp_path):
    path = tmp_path / 'outbound.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY)')
        connection.execute('CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id))')
        connection.execute('INSERT INTO parent VALUES (7)')
        connection.execute('INSERT INTO child VALUES (1, 7)')
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('table', ['main'], 'child')
        desired['rows'][identity]['native']['ddl'] = (
            'CREATE TABLE "main"."child"(id INTEGER PRIMARY KEY, '
            'parent_id INTEGER REFERENCES parent(id), extra TEXT)')
        added_id = _resource_id('column', ['main', 'child'], 'extra')
        facts = {'ordinal_position': 2, 'data_type': 'TEXT', 'nullable': True,
            'default': None, 'primary_key_position': 0, 'hidden': 0}
        desired['rows'][identity]['native']['columns'].append({
            'resource_id': added_id, 'name': 'extra', **facts})
        desired['rows'][added_id] = {'resource_id': added_id, 'kind': 'column',
            'path': ['main', 'child', 'extra'], 'name': 'extra', 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': facts}}
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection, rebuilds=[identity])
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'outbound-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        result = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed', result.get('outcome')
        with sqlite3.connect(path) as connection:
            connection.execute('PRAGMA foreign_keys=ON')
            assert connection.execute('SELECT parent_id, extra FROM child').fetchall() == [(7, None)]
            assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    finally:
        provider.client.close()


def test_rebuild_preserves_implicit_unique_index_and_enforcement(tmp_path):
    path = tmp_path / 'unique.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE owned(id INTEGER PRIMARY KEY, code TEXT UNIQUE)')
        connection.execute("INSERT INTO owned VALUES (7, 'one')")
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('table', ['main'], 'owned')
        desired['rows'][identity]['native']['ddl'] = (
            'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY, code TEXT UNIQUE, extra TEXT)')
        added_id = _resource_id('column', ['main', 'owned'], 'extra')
        facts = {'ordinal_position': 2, 'data_type': 'TEXT', 'nullable': True,
            'default': None, 'primary_key_position': 0, 'hidden': 0}
        desired['rows'][identity]['native']['columns'].append({
            'resource_id': added_id, 'name': 'extra', **facts})
        desired['rows'][added_id] = {'resource_id': added_id, 'kind': 'column',
            'path': ['main', 'owned', 'extra'], 'name': 'extra', 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': facts}}
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection, rebuilds=[identity])
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'unique-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        result = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed', result.get('outcome')
        with sqlite3.connect(path) as connection:
            assert connection.execute('SELECT id, code, extra FROM owned').fetchall() == [(7, 'one', None)]
            assert connection.execute('PRAGMA index_list(owned)').fetchone()[1] == 'sqlite_autoindex_owned_1'
            try:
                connection.execute("INSERT INTO owned(id,code) VALUES (8,'one')")
                assert False, 'UNIQUE constraint must still reject duplicate values'
            except sqlite3.IntegrityError:
                pass
    finally:
        provider.client.close()


def test_rebuild_preserves_without_rowid_composite_key(tmp_path):
    path = tmp_path / 'without-rowid.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE owned(a TEXT, b INTEGER, note TEXT, '
                           'PRIMARY KEY(a,b)) WITHOUT ROWID')
        connection.execute("INSERT INTO owned VALUES ('x', 7, 'kept')")
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    try:
        captured = provider.capture_catalog(route)['resources']
        baseline = build_export(captured, endpoint_id='endpoint', target_id='file',
            generation='g', engine='sqlite', native_model=True)
        desired = deepcopy(baseline)
        identity = _resource_id('table', ['main'], 'owned')
        desired['rows'][identity]['native']['ddl'] = (
            'CREATE TABLE "main"."owned"(a TEXT, b INTEGER, note TEXT, '
            'extra TEXT, PRIMARY KEY(a,b)) WITHOUT ROWID')
        added_id = _resource_id('column', ['main', 'owned'], 'extra')
        facts = {'ordinal_position': 3, 'data_type': 'TEXT', 'nullable': True,
            'default': None, 'primary_key_position': 0, 'hidden': 0}
        desired['rows'][identity]['native']['columns'].append({
            'resource_id': added_id, 'name': 'extra', **facts})
        desired['rows'][added_id] = {'resource_id': added_id, 'kind': 'column',
            'path': ['main', 'owned', 'extra'], 'name': 'extra', 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': facts}}
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection, rebuilds=[identity])
        assert preview['ready_for_review'], preview
        info = path.stat()
        applications = SQLiteSchemaApplications(tmp_path / 'without-rowid-receipts.json')
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        result = applications.apply({'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True},
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed', result.get('outcome')
        with sqlite3.connect(path) as connection:
            assert connection.execute('SELECT a,b,note,extra FROM owned').fetchall() == [
                ('x', 7, 'kept', None)]
            assert next(row for row in connection.execute('PRAGMA table_list')
                        if row[1] == 'owned')[4] == 1
    finally:
        provider.client.close()
