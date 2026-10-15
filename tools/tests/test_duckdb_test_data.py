"""DuckDB recipes are exact-scope, bounded and nonexecuting until reviewed."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider, _create_client, _resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.duckdb_test_data import FORMAT, generate, template


def model(*, catalog='demo', table='facts', temporary=False):
    root = _resource_id('database', [], catalog)
    identity = _resource_id('table', [catalog, 'main'], table)
    return identity, {'provenance': {'mapping': 'scratchrobin.duckdb.catalog@1',
        'endpoint_id': 'endpoint-1', 'database_target_id': 'file-1'},
        'rows': {root: {'kind': 'database', 'system': 'false', 'name': catalog},
            identity: {'kind': 'table', 'system': 'false', 'name': table,
                'path': [catalog, 'main', table], 'native': {
                    'catalog_metadata': {'temporary': temporary},
                    'columns': [{'name': 'n', 'data_type': 'INTEGER', 'nullable': False, 'default': None},
                                {'name': 'v', 'data_type': 'VARCHAR', 'nullable': True, 'default': None}]}}}}


def recipe(identity, scope=None):
    return {'format': FORMAT, 'seed': 7,
        'scope': scope or {'endpoint_id': 'endpoint-1', 'database_target_id': 'file-1'},
        'tables': [{'table': identity, 'count': 3, 'columns': {
            'n': {'kind': 'sequential', 'start': '1', 'step': '1'},
            'v': {'kind': 'choice', 'values': ["a'b", 'z']}}}]}


def test_qualified_recipe_parses_and_executes_only_when_caller_runs_it():
    duckdb = pytest.importorskip('duckdb')
    identity, captured = model()
    assert template(captured)['tables'][0]['resource_id'] == identity
    result = generate(captured, recipe(identity))
    assert result['rows'] == 3 and result['executed'] is False
    assert '"demo"."main"."facts"' in result['source']
    assert "'a''b'" in result['source']
    assert len(duckdb.extract_statements(result['source'])) == 3
    connection = duckdb.connect(':memory:')
    connection.execute("ATTACH ':memory:' AS demo")
    connection.execute('CREATE TABLE demo.main.facts(n INTEGER, v VARCHAR)')
    # Recipe generation above has not touched the independent native table.
    assert connection.execute('SELECT count(*) FROM demo.main.facts').fetchone()[0] == 0
    connection.execute(result['source'])
    rows = connection.execute('SELECT n, v FROM demo.main.facts ORDER BY n').fetchall()
    assert [number for number, _value in rows] == [1, 2, 3]
    assert {value for _number, value in rows} <= {"a'b", 'z'}
    connection.close()


def test_recipe_uses_real_registered_file_capture(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path / 'qualified.duckdb'
    connection = duckdb.connect(str(path))
    connection.execute('CREATE TABLE facts(n INTEGER, v VARCHAR)')
    connection.close()
    client = _create_client()
    provider = DuckDBPilotProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), client)
    try:
        captured = provider.capture_catalog({'database': str(path), 'filesystem_root': str(tmp_path)})
        model = build_export(captured['resources'], endpoint_id='endpoint-1', target_id='file-1',
            generation=captured['generation'], refreshed=True, engine='duckdb', native_model=True)
        available = template(model)
        table = next(row for row in available['tables'] if row['name'] == 'facts')
        assert table['catalog'] == 'qualified' and table['schema'] == 'main'
        statement = generate(model, {'format': FORMAT, 'seed': 1, 'scope': available['scope'],
            'tables': [{'table': table['resource_id'], 'count': 1, 'columns': {
                'n': {'kind': 'constant', 'value': 9}}}]})
        assert '"qualified"."main"."facts"' in statement['source']
        observer = duckdb.connect(str(path))
        assert observer.execute('SELECT count(*) FROM facts').fetchone()[0] == 0
        observer.execute(statement['source'])
        assert observer.execute('SELECT n FROM facts').fetchall() == [(9,)]
        observer.close()
    finally:
        client.close()


def test_foreign_scope_temporary_table_and_unknown_column_are_refused():
    identity, captured = model()
    with pytest.raises(ValueError, match='another endpoint'):
        generate(captured, recipe(identity, {'endpoint_id': 'foreign', 'database_target_id': 'file-1'}))
    bad = recipe(identity); bad['tables'][0]['columns']['not_a_column'] = {'kind': 'constant', 'value': 3}
    with pytest.raises(ValueError, match='Unknown native column'):
        generate(captured, bad)
    temporary_identity, temporary = model(temporary=True)
    assert template(temporary)['tables'] == []
    with pytest.raises(ValueError, match='Unknown or duplicate'):
        generate(temporary, recipe(temporary_identity))


@pytest.mark.parametrize('value', ["x'); DROP TABLE facts; --", {'type': 'integer', 'value': '3; DROP TABLE facts'},
    {'type': 'binary', 'value': '%%%'}, {'type': 'decimal', 'value': '1e309'}])
def test_value_is_quoted_or_rejected_without_extra_statement(value):
    duckdb = pytest.importorskip('duckdb')
    identity, captured = model()
    candidate = recipe(identity); candidate['tables'][0]['columns']['v'] = {'kind': 'constant', 'value': value}
    if isinstance(value, dict):
        with pytest.raises(ValueError): generate(captured, candidate)
    else:
        result = generate(captured, candidate)
        assert len(duckdb.extract_statements(result['source'])) == 3
        assert 'DROP TABLE' in result['source']  # text only, not another statement


def test_duplicate_or_overflow_is_refused():
    identity, captured = model()
    candidate = recipe(identity); candidate['tables'].append(candidate['tables'][0])
    with pytest.raises(ValueError, match='duplicate'):
        generate(captured, candidate)
    candidate = recipe(identity); candidate['tables'][0]['count'] = 1001
    with pytest.raises(ValueError, match='invalid count'):
        generate(captured, candidate)
