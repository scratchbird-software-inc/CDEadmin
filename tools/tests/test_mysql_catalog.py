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


def test_documentary_ddn_roundtrip_and_native_comparison():
    captured = capture(Connection(), 'demo')
    options = {'endpoint_id': 'endpoint', 'target_id': 'target', 'generation': captured['generation'], 'engine': 'mysql'}
    exported = build_export(captured['resources'], **options)
    import json
    decoded = read_catalog(json.dumps(exported['snapshot']), engine='mysql')
    native = build_export(captured['resources'], **options, native_model=True)
    result = compare_catalogs(decoded, native)
    assert not result['changes']
    assert decoded['provenance']['coverage'] == 'partial'
    assert next(row for row in decoded['rows'].values() if row['kind'] == 'table')['native']['definition'].startswith('CREATE TABLE')


def test_native_relation_projection_renders_through_consumed_ddn():
    import json
    import subprocess
    from pathlib import Path
    from pgadmin.cdeadmin.workspace.mysql_erd import build_diagram
    captured = capture(Connection(), 'demo')
    table = captured['resources'][1]
    table['native']['children']['COLUMNS'][0].update(ordinal_position=1, is_nullable='NO')
    table['native']['children']['KEY_COLUMN_USAGE'] = [{'constraint_name': 'self-reference',
        'column_name': 'id', 'ordinal_position': 1, 'referenced_column_name': 'id',
        'referenced_table_schema': 'demo', 'referenced_table_name': 'a:`b'}]
    result = build_diagram(captured['resources'], {'endpoint_id': 'ep', 'database_target_id': 'target'})
    assert result['foreign_keys'] == 1
    runtime = (Path(__file__).resolve().parents[2] / 'web/pgadmin/static/vendor/ddn/current/ddn.mjs').as_uri()
    script = f'''import runtime from {json.dumps(runtime)};
      let input='';for await(const chunk of process.stdin)input+=chunk;
      const snapshot=JSON.parse(input), workspace=runtime.createWorkspace(snapshot.files);
      try {{const output=workspace.renderSync({{entry:snapshot.entry,view:snapshot.view}});
        if(output.diagnostics.some(x=>x.severity==='error'))throw Error(JSON.stringify(output.diagnostics));
        if(!output.svg.includes('a:`b'))throw Error('Missing native label');
      }}finally{{workspace.destroy();}}'''
    subprocess.run(['node', '--input-type=module', '-e', script], input=json.dumps(result['snapshot']),
                   text=True, capture_output=True, timeout=15, check=True)


def test_native_catalog_set_values_are_exact_and_deterministic():
    from pgadmin.cdeadmin.providers.mysql_family.mysql_catalog import _value
    assert _value({'STRICT_TRANS_TABLES', 'NO_ENGINE_SUBSTITUTION'}) == {
        'set': ['NO_ENGINE_SUBSTITUTION', 'STRICT_TRANS_TABLES']}
    assert _value(set()) == {'set': []}
    with pytest.raises(ValueError): _value({1, 'not-native-text'})


def test_native_mysql_workspace_admits_its_real_transaction_controls():
    from tools.tests.test_cdeadmin_relational_providers import context, Permissions, MYSQL_PROFILE
    from pgadmin.cdeadmin.providers.mysql_family.provider import MySQLDBAPIClient, MySQLPilotProvider
    # No socket is needed to negotiate contribution contracts. Use the native
    # client's declarations rather than a fake action list that masks drift.
    client = object.__new__(MySQLDBAPIClient)
    provider = MySQLPilotProvider(context(MYSQL_PROFILE), Permissions(), client)
    contributions = provider.data_studio_contributions()
    session = contributions['sessions'][0]
    assert session.transaction_actions == frozenset(MySQLDBAPIClient.transaction_actions)
    assert {'autocommit_on', 'autocommit_off'} <= session.transaction_actions
    assert callable(session.control_transaction)
