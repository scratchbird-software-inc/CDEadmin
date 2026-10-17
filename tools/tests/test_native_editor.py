"""Native editor ownership, exact identifiers and nonexecuting preparation."""
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import Mock
import sqlite3
import threading

import pytest

from pgadmin.cdeadmin.providers.native_editor import metadata, mysql_bind_markers, validate_mysql, session_access
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('engine', ['sqlite', 'duckdb'])
def test_native_identifier_case_folds_ascii_without_merging_non_ascii_aliases(engine):
    if engine == 'sqlite':
        connection, error = sqlite3.connect(':memory:'), sqlite3.Error
    else:
        import duckdb
        connection, error = duckdb.connect(), duckdb.Error
    try:
        assert connection.execute('SELECT a.value FROM (SELECT 1 AS value) AS A').fetchone()[0] == 1
        assert connection.execute('SELECT Ä.value FROM (SELECT 1 AS value) AS Ä').fetchone()[0] == 1
        assert connection.execute('SELECT 🚀.value FROM (SELECT 1 AS value) AS 🚀').fetchone()[0] == 1
        with pytest.raises(error):
            connection.execute('SELECT ä.value FROM (SELECT 1 AS value) AS Ä')
    finally:
        connection.close()


def test_sqlite_symbols_include_attached_identifiers_functions_and_compile_identity(tmp_path):
    connection = sqlite3.connect(tmp_path / 'primary.db')
    connection.execute('ATTACH DATABASE ? AS "other.schema"', (str(tmp_path / 'other.db'),))
    connection.execute('CREATE TABLE "odd.table" ("odd.column" INTEGER)')
    connection.execute('CREATE TABLE "other.schema"."odd.table" ("other column" TEXT)')
    connection.create_function('owner_function', 2, lambda a, b: a)
    connection.commit()
    connection.execute('BEGIN')
    connection.execute('INSERT INTO "odd.table" VALUES (9)')
    try:
        result = metadata(connection, 'sqlite')
        symbols = {(row['resource_kind'], tuple(row['display_path'])) for row in result['resources']}
        assert ('column', ('main', 'odd.table', 'odd.column')) in symbols
        assert ('column', ('other.schema', 'odd.table', 'other column')) in symbols
        assert ('function', ('owner_function',)) in symbols
        assert result['context']['compile_options']
        assert connection.in_transaction
        with sqlite3.connect(tmp_path / 'primary.db') as observer:
            assert observer.execute('SELECT count(*) FROM "odd.table"').fetchone() == (0,)
        connection.rollback()
        assert connection.execute('SELECT count(*) FROM "odd.table"').fetchone() == (0,)
    finally:
        connection.close()


def test_sqlite_invalid_view_does_not_hide_other_symbols_or_finish_pending_work(tmp_path):
    path=tmp_path/'editor.sqlite'
    connection=sqlite3.connect(path)
    try:
        connection.execute('CREATE TABLE owned(value INTEGER)')
        connection.execute('CREATE VIEW "broken.😀" AS SELECT value FROM missing_relation')
        connection.execute('INSERT INTO owned VALUES(1)');connection.commit()
        connection.execute('BEGIN');connection.execute('INSERT INTO owned VALUES(2)')
        first=metadata(connection,'sqlite')
        assert any(row['display_path']==['main','owned','value'] for row in first['resources'])
        assert any(row['resource_kind']=='view' and row['display_name']=='broken.😀' for row in first['resources'])
        failed=next(item for item in first['observations'] if item['section']=='columns:main:broken.😀')
        assert failed['available'] is False and failed['error_code']==sqlite3.SQLITE_ERROR
        assert any(row['resource_kind']=='function' for row in first['resources'])
        assert connection.in_transaction
        with closing(sqlite3.connect(path)) as observer:assert observer.execute('SELECT count(*) FROM owned').fetchone()==(1,)
        connection.execute('DROP VIEW "broken.😀"')
        connection.execute('CREATE VIEW "broken.😀" AS SELECT value FROM owned')
        repaired=metadata(connection,'sqlite')
        assert repaired['context']['context_revision']!=first['context']['context_revision']
        assert any(row['display_path']==['main','broken.😀','value'] for row in repaired['resources'])
        assert connection.in_transaction
        connection.rollback()
        assert metadata(connection,'sqlite')['context']['context_revision']==first['context']['context_revision']
    finally:connection.close()


def test_sqlite_denied_view_metadata_retains_native_authorizer():
    connection=sqlite3.connect(':memory:')
    try:
        connection.execute('CREATE TABLE owned(value INTEGER)')
        connection.execute('CREATE VIEW protected_view AS SELECT value FROM owned')
        def authorize(action,name,_column,_database,_origin):
            denied=(action==sqlite3.SQLITE_READ and name=='owned' or
                action==sqlite3.SQLITE_PRAGMA and name=='table_xinfo' and _column=='protected_view')
            return sqlite3.SQLITE_DENY if denied else sqlite3.SQLITE_OK
        connection.set_authorizer(authorize)
        result=metadata(connection,'sqlite')
        assert any(row['display_path']==['main','owned','value'] for row in result['resources'])
        failed=next(item for item in result['observations'] if item['section']=='columns:main:protected_view')
        assert failed['available'] is False and failed['error_code']==sqlite3.SQLITE_AUTH
        with pytest.raises(sqlite3.DatabaseError):connection.execute('SELECT value FROM owned')
    finally:connection.close()


def test_duckdb_metadata_uses_original_session_and_retains_pending_work(tmp_path):
    import duckdb
    connection = duckdb.connect(str(tmp_path / 'source.duckdb'))
    connection.execute('CREATE TABLE t (id INTEGER)')
    connection.execute('CREATE TEMP TABLE "session table" ("session column" INTEGER)')
    connection.execute('CREATE MACRO "session macro"(x) AS x + 1')
    connection.execute('BEGIN')
    connection.execute('INSERT INTO t VALUES (9)')
    try:
        result = metadata(connection, 'duckdb')
        assert any(row['display_name'] == 'session column' for row in result['resources'])
        assert any(row['display_name'] == 'session macro' and row['resource_kind'] == 'function' for row in result['resources'])
        with duckdb.connect(str(tmp_path / 'source.duckdb')) as observer:
            assert observer.execute('SELECT count(*) FROM t').fetchone() == (0,)
        connection.execute('ROLLBACK')
        assert connection.execute('SELECT count(*) FROM t').fetchone() == (0,)
    finally:
        connection.close()


def test_duckdb_full_search_path_and_extension_identity_invalidate_native_context():
    import duckdb
    with duckdb.connect() as connection:
        for schema in ('first', 'Second ü', 'third'):
            connection.execute('CREATE SCHEMA "' + schema + '"')
        connection.execute("SET search_path='first,\"Second ü\"'")
        first = metadata(connection, 'duckdb')
        connection.execute("SET search_path='first,third,\"Second ü\"'")
        changed = metadata(connection, 'duckdb')
        assert changed['context']['default_schema'] == first['context']['default_schema']
        assert changed['resources'] == first['resources']
        assert changed['context']['search_path'] == connection.execute("SELECT current_setting('search_path')").fetchone()[0]
        assert changed['context']['context_revision'] != first['context']['context_revision']
        native = connection.execute('SELECT extension_name,loaded,installed,extension_version,install_mode FROM duckdb_extensions() ORDER BY extension_name').fetchall()
        assert changed['context']['extensions'] == [dict(zip(('name','loaded','installed','version','install_mode'),row)) for row in native]
        assert not any('install_path' in extension or 'installed_from' in extension for extension in changed['context']['extensions'])
        connection.execute("SET search_path='first,\"Second ü\"'")
        assert metadata(connection, 'duckdb')['context']['context_revision'] == first['context']['context_revision']


def test_sqlite_native_quoting_flags_invalidate_context_without_finishing_pending_work(tmp_path):
    path = tmp_path / 'quoting.sqlite'
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('CREATE TABLE owned(value INTEGER)')
        connection.execute('INSERT INTO owned VALUES(1)'); connection.commit()
        connection.execute('BEGIN'); connection.execute('INSERT INTO owned VALUES(2)')
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DML, True)
        first = metadata(connection, 'sqlite')
        assert connection.execute('SELECT "native literal"').fetchone()[0] == 'native literal'
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DML, False)
        changed = metadata(connection, 'sqlite')
        assert first['context']['database_config']['DQS_DML'] is True
        assert changed['context']['database_config']['DQS_DML'] is False
        assert changed['resources'] == first['resources']
        assert changed['context']['context_revision'] != first['context']['context_revision']
        with pytest.raises(sqlite3.OperationalError): connection.execute('SELECT "native literal"')
        assert connection.in_transaction and connection.execute('SELECT count(*) FROM owned').fetchone() == (2,)
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT count(*) FROM owned').fetchone() == (1,)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DML, True)
        assert metadata(connection, 'sqlite')['context']['context_revision'] == first['context']['context_revision']
        connection.rollback()


def test_sqlite_hidden_generated_and_rowid_columns_follow_native_star_projection():
    connection = sqlite3.connect(':memory:')
    try:
        connection.execute('CREATE TABLE ordinary (id INTEGER, computed TEXT GENERATED ALWAYS AS (id || id))')
        connection.execute('CREATE TABLE no_rowid (id INTEGER PRIMARY KEY) WITHOUT ROWID')
        connection.execute('CREATE TABLE shadowed ("RoWiD" TEXT, "_ROWID_" TEXT, oid TEXT)')
        connection.execute('CREATE VIEW projected AS SELECT id FROM ordinary')
        connection.execute('CREATE VIRTUAL TABLE documents USING fts5(body)')
        result = metadata(connection, 'sqlite')
        for table in ('ordinary', 'no_rowid', 'shadowed', 'projected', 'documents'):
            rows = [row for row in result['resources'] if row['resource_kind'] == 'column'
                    and row['display_path'][:2] == ['main', table]]
            native = connection.execute(f'SELECT * FROM "{table}" LIMIT 0')
            assert [row['display_name'] for row in rows if not row.get('hidden_from_star')] == [col[0] for col in native.description]
            for row in rows:
                name = row['display_name'].replace('"', '""')
                connection.execute(f'SELECT "{table}"."{name}" FROM "{table}" LIMIT 0')
        ordinary = {row['display_name']: row for row in result['resources'] if row['display_path'][:2] == ['main', 'ordinary'] and row['resource_kind'] == 'column'}
        assert all(ordinary[alias]['hidden_from_star'] for alias in ('rowid', '_rowid_', 'oid'))
        assert not ordinary['computed'].get('hidden_from_star')
        assert not any(row.get('hidden_from_star') for row in result['resources'] if row['display_path'][:2] == ['main', 'shadowed'])
    finally:
        connection.close()


def test_duckdb_rowid_is_native_storage_only_and_shadowed_by_real_columns():
    import duckdb
    connection = duckdb.connect()
    try:
        connection.execute('CREATE TABLE ordinary (id INTEGER)')
        connection.execute('CREATE TEMP TABLE temporary (id INTEGER)')
        connection.execute('CREATE TABLE shadowed ("RoWiD" VARCHAR)')
        connection.execute('CREATE VIEW projected AS SELECT id FROM ordinary')
        result = metadata(connection, 'duckdb')
        for table in ('ordinary', 'temporary', 'shadowed', 'projected'):
            rows = [row for row in result['resources'] if row['resource_kind'] == 'column' and row['display_path'][-2] == table]
            native = connection.execute(f'SELECT * FROM "{table}" LIMIT 0')
            assert [row['display_name'] for row in rows if not row.get('hidden_from_star')] == [col[0] for col in native.description]
            for row in rows:
                name = row['display_name'].replace('"', '""')
                connection.execute(f'SELECT "{table}"."{name}" FROM "{table}" LIMIT 0')
            assert any(row.get('hidden_from_star') for row in rows) == (table in {'ordinary', 'temporary'})
        assert any(row['display_path'][-1] == 'projected' and row['resource_kind'] == 'view' for row in result['resources'])
    finally:
        connection.close()


@pytest.mark.parametrize('engine', ['mysql', 'mariadb'])
def test_mysql_family_invisible_columns_remain_suggested_but_do_not_expand_star(engine):
    cursor = Mock()
    def execute(sql):
        if sql.startswith('SELECT VERSION()'):
            cursor.fetchmany.return_value = [('native', 'owned', '', 'utf8mb4', 0)]
        elif sql.startswith('SELECT CURRENT_USER()'):
            cursor.fetchmany.return_value=[('native-owner@native-host','NONE' if engine=='mysql' else None)]
        elif 'FROM information_schema.COLUMNS' in sql:
            cursor.fetchmany.return_value = [('owned', 't', 'visible', 'int', ''),
                                            ('owned', 't', 'hidden', 'int', 'DEFAULT_GENERATED INVISIBLE')]
        else:
            cursor.fetchmany.return_value = []
    cursor.execute.side_effect = execute
    result = metadata(SimpleNamespace(cursor=lambda: cursor), engine)
    rows = [row for row in result['resources'] if row['resource_kind'] == 'column']
    assert len(rows) == 2 and rows[1]['hidden_from_star']
    assert not rows[0].get('hidden_from_star')


@pytest.mark.parametrize('engine', ['mysql', 'mariadb'])
def test_mysql_prepare_never_executes_submitted_sql_or_changes_transaction(engine):
    cursor = Mock()
    cursor.fetchone.return_value = ('9.7.0' if engine == 'mysql' else '12.2.2', 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES', 60)
    handle = Mock(); handle.cursor.return_value = cursor
    client = SimpleNamespace(_uncertain_sessions=set())
    source = 'DROP TABLE "do not execute"'
    result = validate_mysql(client, handle, source, engine)
    assert result['grammar_valid'] is True
    commands = [call.args[0] for call in cursor.execute.call_args_list]
    assert not any(command.startswith(('EXECUTE ', 'COMMIT', 'ROLLBACK')) or command == source for command in commands)
    assert any(command.startswith('PREPARE sr_check_') for command in commands)
    assert any(command.startswith('DEALLOCATE PREPARE sr_check_') for command in commands)
    encoded = [call for call in cursor.execute.call_args_list if call.args[0].startswith('SET @')]
    assert encoded[0].args[1] == (source.encode(),)
    assert commands[-1] == 'SET SESSION lock_wait_timeout=60'
    handle.commit.assert_not_called(); handle.rollback.assert_not_called()


@pytest.mark.parametrize('code,expected', [(1064, False), (1146, None), (1142, None), (1295, None)])
def test_native_syntax_context_permission_and_unsupported_are_distinct(code, expected):
    class NativeError(Exception):
        errno = code
    cursor = Mock()
    cursor.fetchone.return_value = ('9.7.0', '', 60)
    cursor.execute.side_effect = lambda sql, *args: (_ for _ in ()).throw(NativeError('literal must not leak')) if sql.startswith('PREPARE ') else None
    result = validate_mysql(SimpleNamespace(_uncertain_sessions=set()), SimpleNamespace(cursor=lambda: cursor), 'SELECT * FROM missing', 'mysql')
    assert result['grammar_valid'] is expected
    assert 'literal must not leak' not in str(result)


def test_editor_metadata_cannot_use_an_active_native_execution():
    handle = object()
    gate = Mock(); gate.closing = False; gate.lock = threading.RLock()
    gate.require_idle.side_effect = RelationalClientError('executing')
    client = SimpleNamespace(_executions=gate, _connections=[handle], _require_usable_session=Mock())
    with pytest.raises(RelationalClientError, match='executing'):
        with session_access(client, handle, 'mysql'):
            pytest.fail('Active session was borrowed')
    client._require_usable_session.assert_not_called()


def test_driver_bind_markers_preserve_native_literals_comments_and_positions():
    source = "SELECT %(name)s, %s, '%s', `%(identifier)s` /* %s */ -- %s\n"
    converted = mysql_bind_markers(source, {'NO_BACKSLASH_ESCAPES'})
    assert len(converted) == len(source)
    assert converted.startswith('SELECT ?       , ? ,')
    assert "'%s'" in converted and '`%(identifier)s`' in converted
    assert '/* %s */ -- %s' in converted
