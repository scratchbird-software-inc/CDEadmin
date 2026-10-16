"""Native schema transformations, dependency admission and atomic refusal."""
from copy import deepcopy
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider, _create_client, _resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.sqlite_schema_plan import plan
from pgadmin.cdeadmin.workspace.sqlite_schema_apply import SQLiteSchemaApplications, apply_review


def reviewed(tmp_path, initial, target, *, extra=()):
    path, desired_path = tmp_path / 'live.sqlite', tmp_path / 'desired.sqlite'
    for file, source in ((path, initial), (desired_path, target)):
        with sqlite3.connect(file) as connection:
            for statement in extra:
                connection.execute(statement)
            connection.execute(source)
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    def capture(file):
        return build_export(provider.capture_catalog({**route, 'database': str(file)})['resources'],
            endpoint_id='endpoint', target_id='file', generation='g', engine='sqlite', native_model=True)
    def review():
        baseline, desired_model = capture(path), capture(desired_path)
        desired = deepcopy(baseline)
        for identity, row in list(desired['rows'].items()):
            if row['path'][:2] == ['main', 'owned']:
                del desired['rows'][identity]
        desired['rows'].update({identity: row for identity, row in desired_model['rows'].items()
            if row['path'][:2] == ['main', 'owned']})
        identity = _resource_id('table', ['main'], 'owned')
        desired['rows'][identity]['native']['ddl'] = target
        with sqlite3.connect(path) as connection:
            preview = plan(baseline, desired, baseline, connection, rebuilds=[identity])
        assert preview['ready_for_review'], preview
        info = path.stat()
        store = SQLiteSchemaApplications(tmp_path / 'receipts.json')
        receipt = store.review(preview, baseline, desired, 'owner', 'binding', 'file',
            file_identity=[info.st_dev, info.st_ino])
        request = {key: receipt[key] for key in ('review_id', 'review_digest')}
        request['confirmed'] = True
        return store, request, preview
    return provider, route, path, desired_path, review


def test_types_generated_strict_unique_and_retained_bindings(tmp_path):
    provider, route, path, target_path, review = reviewed(tmp_path,
        'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY, note TEXT, calculated INT AS(id*2) VIRTUAL)',
        'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY, note INTEGER UNIQUE, calculated INT AS(id*3) STORED) STRICT',
        extra=('CREATE TABLE audit(value INT)',))
    try:
        for file in (path, target_path):
            with sqlite3.connect(file) as connection:
                connection.execute('CREATE TRIGGER touch AFTER UPDATE ON owned BEGIN INSERT INTO audit VALUES(new.id); END')
        with sqlite3.connect(path) as connection:
            connection.execute("INSERT INTO owned(id,note) VALUES(7,'007')")
            connection.execute('CREATE VIEW retained AS SELECT id,calculated FROM owned')
            connection.execute('CREATE TRIGGER external AFTER INSERT ON audit BEGIN UPDATE owned SET note=note WHERE id=new.value; END')
        store, request, preview = review()
        assert preview['operations'][0]['dependency_sha256']
        outcome = store.apply(request, 'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome.get('outcome')
        with sqlite3.connect(path) as observer:
            assert observer.execute('SELECT id,note,calculated,typeof(note) FROM owned').fetchall() == [(7, 7, 21, 'integer')]
            assert observer.execute('SELECT * FROM retained').fetchall() == [(7, 21)]
            assert observer.execute('SELECT * FROM audit').fetchall() == []
            observer.execute('UPDATE owned SET note=8 WHERE id=7')
            assert observer.execute('SELECT * FROM audit').fetchall() == [(7,)]
            with pytest.raises(sqlite3.IntegrityError):
                observer.execute('INSERT INTO owned(id,note) VALUES(8,8)')
    finally:
        provider.client.close()


def test_new_primary_key_storage_mode_and_foreign_key(tmp_path):
    provider, route, path, _, review = reviewed(tmp_path,
        'CREATE TABLE "main"."owned"(id INTEGER, code TEXT)',
        'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY REFERENCES parent(id), code TEXT UNIQUE) WITHOUT ROWID, STRICT',
        extra=('CREATE TABLE parent(id INTEGER PRIMARY KEY)', 'INSERT INTO parent VALUES(9)'))
    try:
        with sqlite3.connect(path) as connection:
            connection.execute("INSERT INTO owned VALUES(9,'retained')")
        store, request, preview = review()
        assert preview['operations'][0]['preserve_rowid'] is False
        outcome = store.apply(request, 'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome.get('outcome')
        with sqlite3.connect(path) as observer:
            assert observer.execute('SELECT * FROM owned').fetchall() == [(9, 'retained')]
            assert observer.execute('PRAGMA foreign_key_check').fetchall() == []
            assert next(row for row in observer.execute('PRAGMA table_list') if row[1] == 'owned')[4:] == (1, 1)
    finally:
        provider.client.close()


@pytest.mark.parametrize('target,dependency', [
    ('(id INT, note TEXT UNIQUE)', None),
    ('(id INT, note INT) STRICT', None),
    ('(id INT CHECK(id>10), note TEXT)', None),
    ('(id INT REFERENCES parent(id), note TEXT)', None),
    ('(id INT)', 'CREATE VIEW retained AS SELECT note FROM owned'),
    ('(id INT)', 'CREATE TRIGGER retained AFTER UPDATE ON audit BEGIN SELECT note FROM owned; END'),
])
def test_native_refusal_rolls_back_schema_rows_and_does_not_replay(tmp_path, target, dependency):
    provider, route, path, _, review = reviewed(tmp_path,
        'CREATE TABLE "main"."owned"(id INT, note TEXT)',
        'CREATE TABLE "main"."owned"' + target,
        extra=('CREATE TABLE parent(id INT PRIMARY KEY)', 'CREATE TABLE audit(value TEXT)'))
    try:
        with sqlite3.connect(path) as connection:
            connection.executemany('INSERT INTO owned VALUES(?,?)', [(1, 'bad'), (2, 'bad')])
            if dependency:
                connection.execute(dependency)
        store, request, _ = review()
        outcome = store.apply(request, 'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'rolled_back', outcome.get('outcome')
        assert store.apply(request, 'owner', 'binding', lambda _: pytest.fail('redispatched'))['state'] == 'rolled_back'
        with sqlite3.connect(path) as observer:
            assert observer.execute('SELECT * FROM owned').fetchall() == [(1, 'bad'), (2, 'bad')]
            assert observer.execute("SELECT count(*) FROM sqlite_schema WHERE name LIKE '__cde_rebuild_%'").fetchone()[0] == 0
            assert observer.execute('SELECT * FROM audit').fetchall() == []
    finally:
        provider.client.close()


@pytest.mark.parametrize('former,latter', [('', ' AUTOINCREMENT'), (' AUTOINCREMENT', '')])
def test_explicit_autoincrement_identity_changes(tmp_path, former, latter):
    provider, route, path, _, review = reviewed(tmp_path,
        'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY' + former + ', note TEXT)',
        'CREATE TABLE "main"."owned"(id INTEGER PRIMARY KEY' + latter + ', note TEXT, added INT)')
    try:
        with sqlite3.connect(path) as connection:
            connection.execute("INSERT INTO owned VALUES(90,'kept')")
        store, request, _ = review()
        outcome = store.apply(request, 'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome.get('outcome')
        with sqlite3.connect(path) as observer:
            observer.execute("INSERT INTO owned(note) VALUES('next')")
            assert observer.execute("SELECT id FROM owned WHERE note='next'").fetchone()[0] == 91
    finally:
        provider.client.close()
