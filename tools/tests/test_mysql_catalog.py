"""Native catalog limits, scoping and privilege observations."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pgadmin.cdeadmin.providers.mysql_family.mysql_catalog import capture, identifier
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog, compare_catalogs


class Connection:
    in_transaction = False

    def __init__(self):
        self.calls = []
        self.failure = None

    def cursor(self, **options):
        connection = self
        class Cursor:
            def execute(self, query, parameters):
                connection.calls.append((query, parameters))
                if connection.failure and 'STATISTICS' in query:
                    raise connection.failure
                if query.startswith('SELECT DATABASE()'):
                    rows = [{'database_name': 'demo', 'version': '9.7.0', 'server_uuid': 'native-server',
                             'lower_case_table_names': 0, 'sql_mode': 'STRICT_TRANS_TABLES'}]
                elif 'FROM information_schema.TABLES ' in query:
                    rows = [{'table_name': 'a:`b', 'table_type': 'BASE TABLE'}]
                elif query.startswith('SHOW CREATE TABLE'):
                    rows = [{'Table': 'a:`b', 'Create Table': 'CREATE TABLE `a:``b` (`id` bigint PRIMARY KEY)'}]
                elif query.startswith('SHOW CREATE DATABASE'):
                    rows = [{'Database': 'demo', 'Create Database': 'CREATE DATABASE `demo`'}]
                elif 'FROM information_schema.COLUMNS ' in query:
                    rows = [{'table_name': 'a:`b', 'column_name': 'id', 'column_type': 'bigint'}]
                else:
                    rows = []
                self.description = [(key,) for key in rows[0]] if rows else []
                self.rows = [tuple(row.values()) for row in rows]
            def fetchmany(self, count):
                result, self.rows = self.rows[:count], self.rows[count:]
                return result
            def close(self): pass
        assert options == {'buffered': False}
        return Cursor()


def test_exact_native_definitions_children_and_bound_scope():
    connection = Connection()
    result = capture(connection, 'demo')
    table = next(item for item in result['resources'] if item['resource_kind'] == 'table')
    assert table['native']['definition'].startswith('CREATE TABLE')
    assert table['native']['children']['COLUMNS'][0]['column_type'] == 'bigint'
    assert not result['complete']
    assert all(params == ('demo',) for sql, params in connection.calls if 'FROM information_schema.' in sql)
    assert any('`demo`.`a:``b`' in sql for sql, _ in connection.calls)
    assert identifier('a`b') == '`a``b`'


def test_permission_denial_is_observed_other_errors_abort():
    class Denied(Exception):
        errno, sqlstate = 1142, '42000'
    connection = Connection(); connection.failure = Denied()
    result = capture(connection, 'demo')
    assert any(item['available'] is False for item in result['observations'])
    connection.failure = RuntimeError('connection lost')
    with pytest.raises(RuntimeError): capture(connection, 'demo')


def test_foreign_or_busy_target_cannot_be_captured(monkeypatch):
    connection = Connection()
    with pytest.raises(ValueError, match='identity changed'): capture(connection, 'other')
    connection.in_transaction = True
    with pytest.raises(ValueError, match='idle'): capture(connection, 'demo')
    connection.in_transaction = False
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mysql_family.mysql_catalog.MAX_FACTS', 1)
    with pytest.raises(ValueError, match='limit'): capture(connection, 'demo')
