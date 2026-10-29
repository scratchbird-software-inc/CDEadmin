"""Native catalog limits, scoping and privilege observations."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pgadmin.cdeadmin.providers.mysql_family.mariadb_catalog import capture, identifier
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog, compare_catalogs


class Connection:
    server_status = 0
    autocommit = True

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
                    rows = [{'database_name': 'demo', 'version': '12.2.2-MariaDB', 'server_uid': 'native-server',
                             'lower_case_table_names': 0, 'sql_mode': getattr(connection, 'sql_mode', 'STRICT_TRANS_TABLES')}]
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
    connection.server_status = 1
    with pytest.raises(ValueError, match='idle'): capture(connection, 'demo')
    connection.server_status = 0
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mysql_family.mariadb_catalog.MAX_FACTS', 1)
    with pytest.raises(ValueError, match='limit'): capture(connection, 'demo')


def test_documentary_ddn_roundtrip_and_native_comparison():
    captured = capture(Connection(), 'demo')
    options = {'endpoint_id': 'endpoint', 'target_id': 'target', 'generation': captured['generation'], 'engine': 'mariadb'}
    exported = build_export(captured['resources'], **options)
    import json
    decoded = read_catalog(json.dumps(exported['snapshot']), engine='mariadb')
    native = build_export(captured['resources'], **options, native_model=True)
    result = compare_catalogs(decoded, native)
    assert not result['changes']
    assert decoded['provenance']['coverage'] == 'partial'
    assert next(row for row in decoded['rows'].values() if row['kind'] == 'table')['native']['definition'].startswith('CREATE TABLE')


def test_native_relation_projection_passes_consumed_ddn_semantics():
    import json
    import subprocess
    from pathlib import Path
    from pgadmin.cdeadmin.workspace.mariadb_erd import build_diagram
    captured = capture(Connection(), 'demo')
    table = captured['resources'][1]
    table['native']['children']['COLUMNS'][0].update(ordinal_position=1, is_nullable='NO')
    table['native']['children']['KEY_COLUMN_USAGE'] = [{'constraint_name': 'self-reference',
        'column_name': 'id', 'ordinal_position': 1, 'referenced_column_name': 'id',
        'referenced_table_schema': 'demo', 'referenced_table_name': 'a:`b'}]
    result = build_diagram(captured['resources'], {'endpoint_id': 'ep', 'database_target_id': 'target'})
    assert result['foreign_keys'] == 1
    checker=Path(__file__).with_name('check_firebird_catalog_ddn.mjs')
    script='import '+json.dumps(checker.as_uri())+';'
    subprocess.run(['node', '--input-type=module', '-e', script], input=json.dumps(result['snapshot']),
                   text=True, capture_output=True, timeout=15, check=True)


def test_native_catalog_set_values_are_exact_and_deterministic():
    from pgadmin.cdeadmin.providers.mysql_family.mariadb_catalog import _value
    assert _value({'STRICT_TRANS_TABLES', 'NO_ENGINE_SUBSTITUTION'}) == {
        'set': ['NO_ENGINE_SUBSTITUTION', 'STRICT_TRANS_TABLES']}
    assert _value(set()) == {'set': []}
    with pytest.raises(ValueError): _value({1, 'not-native-text'})


def test_native_mariadb_workspace_admits_its_real_transaction_controls():
    from tools.tests.test_cdeadmin_relational_providers import context, Permissions, MARIADB_PROFILE
    from pgadmin.cdeadmin.providers.mysql_family.provider import MariaDBDBAPIClient, MariaDBPilotProvider
    # No socket is needed to negotiate contribution contracts. Use the native
    # client's declarations rather than a fake action list that masks drift.
    client = object.__new__(MariaDBDBAPIClient)
    provider = MariaDBPilotProvider(context(MARIADB_PROFILE), Permissions(), client)
    contributions = provider.data_studio_contributions()
    session = contributions['sessions'][0]
    assert session.transaction_actions == frozenset(MariaDBDBAPIClient.transaction_actions)
    assert {'autocommit_on', 'autocommit_off'} <= session.transaction_actions
    assert callable(session.control_transaction)


def test_oracle_presentation_flags_cannot_hide_native_table_options():
    connection = Connection()
    connection.sql_mode = 'ANSI_QUOTES,ORACLE,NO_TABLE_OPTIONS,NO_KEY_OPTIONS,NO_FIELD_OPTIONS,NO_BACKSLASH_ESCAPES'
    captured = capture(connection, 'demo')
    assert ('SET SESSION sql_mode=?', ('ANSI_QUOTES,NO_BACKSLASH_ESCAPES',)) in connection.calls
    root = captured['resources'][0]['native']
    assert root['catalog_row']['sql_mode'] == connection.sql_mode
    assert root['definition_context']['sql_mode'] == 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'
    assert captured['resources'][1]['native']['definition_context']['sql_mode'] == 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'
