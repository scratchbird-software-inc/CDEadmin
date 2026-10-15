from copy import deepcopy
import pytest
from pgadmin.cdeadmin.workspace.postgresql_test_data import generate, template, FORMAT


def model():
    return {'provenance': {'endpoint_id': 'ep', 'database_target_id': 'postgresql-database:42'}, 'rows': {key: {'kind': 'table', 'name': key, 'system': 'false', 'native': {
        'schema': 'odd schema', 'catalog_row': {'relname': key}, 'children': {'pg_attribute': [
            {'attname': 'id', 'attidentity': ''}, {'attname': 'value', 'attgenerated': ''},
            {'attname': 'native_id', 'attidentity': 'a'}, {'attname': 'computed', 'attgenerated': 's'}]}}}
        for key in ('parent', 'child')}}


def recipe(columns=None):
    return {'format': FORMAT, 'scope': model()['provenance'], 'seed': 42, 'tables': [{'table': 'parent', 'count': 2,
        'columns': columns if columns is not None else {'id': {'kind': 'sequential', 'start': '9223372036854775790', 'step': '1'}}}]}


def test_exact_literals_seed_and_generated_parent_order():
    request = recipe({'id': {'kind': 'sequential', 'start': '9223372036854775790', 'step': '1'},
        'value': {'kind': 'constant', 'value': "é\\'; DROP TABLE x; --"}})
    request['tables'].insert(0, {'table': 'child', 'count': 2, 'columns': {
        'id': {'kind': 'generated', 'table': 'parent', 'column': 'id'},
        'value': {'kind': 'random-integer', 'min': '-100', 'max': '100'}}})
    result = generate(model(), request)
    assert result == generate(model(), deepcopy(request))
    assert result['executed'] is False and result['rows'] == 4
    from pglast import parse_sql, ast
    statements = parse_sql(result['source'])
    assert len(statements) == 2 and all(isinstance(item.stmt, ast.InsertStmt) for item in statements)
    assert statements[0].stmt.relation.relname == 'parent'
    assert statements[-1].stmt.relation.relname == 'child'
    assert '9223372036854775791' in result['source']


@pytest.mark.parametrize('value', [1.5, 2**53, {'type': 'integer', 'value': '1);DROP TABLE x'},
    {'type': 'decimal', 'value': '1; SELECT 2'}, {'type': 'binary', 'value': 'not base64'}, '\0'])
def test_invalid_values_do_not_become_sql(value):
    with pytest.raises(ValueError): generate(model(), recipe({'value': {'kind': 'constant', 'value': value}}))


def test_native_defaults_identity_and_computed_columns():
    assert 'DEFAULT VALUES RETURNING 1' in generate(model(), recipe({'native_id': {'kind': 'default'}}))['source']
    for name in ('native_id', 'computed', 'missing'):
        with pytest.raises(ValueError): generate(model(), recipe({name: {'kind': 'constant', 'value': 1}}))
    columns = template(model())['tables'][0]['columns']
    assert not next(column for column in columns if column['name'] == 'native_id')['insertable']


def test_cycles_missing_parent_and_limits_are_explicit():
    request = recipe({'id': {'kind': 'generated', 'table': 'parent', 'column': 'id'}})
    with pytest.raises(ValueError, match='cycle'): generate(model(), request)
    request['tables'][0]['columns']['id']['table'] = 'missing'
    with pytest.raises(ValueError, match='parent'): generate(model(), request)
    request = recipe(); request['tables'][0]['count'] = 1001
    with pytest.raises(ValueError): generate(model(), request)


def test_binary_decimal_and_file_values_remain_exact():
    request = recipe({'value': {'kind': 'file', 'values': [{'type': 'binary', 'value': 'AP8='},
        {'type': 'decimal', 'value': '12345678901234567890.123456789'}]}})
    sql = generate(model(), request)['source']
    assert "pg_catalog.decode(E'AP8=', 'base64')" in sql
    assert "E'12345678901234567890.123456789'::numeric" in sql


def test_recipe_scope_cannot_retarget_equal_object_ids():
    request = recipe()
    request['scope']['database_target_id'] = 'postgresql-database:43'
    with pytest.raises(ValueError, match='another endpoint or database'): generate(model(), request)


def test_returned_identity_is_native_value_not_predicted_sequence():
    request = recipe({'native_id': {'kind': 'default'}})
    request['tables'].insert(0, {'table': 'child', 'count': 3, 'columns': {
        'id': {'kind': 'returned', 'table': 'parent', 'column': 'native_id'}}})
    result = generate(model(), request)
    from pglast import parse_sql, ast
    statements = parse_sql(result['source'])
    assert len(statements) == 1 and isinstance(statements[0].stmt, ast.SelectStmt)
    assert len(statements[0].stmt.withClause.ctes) == 5
    assert 'DEFAULT VALUES RETURNING "native_id"' in result['source']
    assert result['source'].count('(SELECT "native_id" FROM srb_recipe_0_0)') == 2
    assert not result['executed'] and result['rows'] == 5
    for column in ('missing', 'native_id"; SELECT 1; --'):
        request['tables'][0]['columns']['id']['column'] = column
        with pytest.raises(ValueError, match='Returned parent'): generate(model(), request)


def test_returned_dependencies_reject_cycles_and_unselected_parents():
    request = recipe({'id': {'kind': 'returned', 'table': 'parent', 'column': 'native_id'}})
    with pytest.raises(ValueError, match='cycle'): generate(model(), request)
    request['tables'][0]['columns']['id']['table'] = 'child'
    with pytest.raises(ValueError, match='selected table'): generate(model(), request)


def test_existing_samples_share_order_and_keep_native_column_values():
    request = recipe({name: {'kind': 'existing', 'table': 'child', 'column': name, 'order_by': ['id']}
                      for name in ('id', 'value')})
    result = generate(model(), request)
    from pglast import parse_sql
    assert len(parse_sql(result['source'])[0].stmt.withClause.ctes) == 3
    assert result['source'].count('AS MATERIALIZED') == 1
    assert 'ORDER BY "id" LIMIT 200' in result['source']
    assert 'NULLIF((SELECT count(*) FROM srb_sample_0), 0)' in result['source']
    assert not result['executed']
    request['tables'][0]['columns']['value']['order_by'] = ['value']
    with pytest.raises(ValueError, match='same ordering'): generate(model(), request)


@pytest.mark.parametrize('patch', [{'table': 'missing'}, {'column': 'missing'}, {'order_by': []},
    {'order_by': ['id', 'id']}, {'order_by': ['id); DROP TABLE x']}, {'order_by': [None]}])
def test_existing_samples_reject_unknown_or_invalid_native_identifiers(patch):
    source = {'kind': 'existing', 'table': 'child', 'column': 'value', 'order_by': ['id'], **patch}
    with pytest.raises(ValueError): generate(model(), recipe({'value': source}))


def test_large_recipes_stay_within_shared_script_framing():
    from pgadmin.cdeadmin.providers.postgresql.language import analyze
    m = model()
    request = recipe()
    request['tables'] = []
    for index in range(5):
        key = 'table_' + str(index)
        m['rows'][key] = deepcopy(m['rows']['parent'])
        m['rows'][key]['native']['catalog_row']['relname'] = key
        request['tables'].append({'table': key, 'count': 1000, 'columns': {
            'id': {'kind': 'sequential', 'start': '1', 'step': '1'}}})
    result = generate(m, request)
    checked = analyze(result['source'], script=True, standard_strings='on')
    assert checked['script_ready'] and len(checked['statements']) == 5
    assert result['rows'] == 5000
    request['tables'][0]['columns'] = {}
    assert analyze(generate(m, request)['source'], script=True, standard_strings='on')['script_ready']


def test_script_file_limit_is_enforced_before_returning_preview():
    request = recipe({'value': {'kind': 'constant', 'value': 'x' * 600000}})
    with pytest.raises(ValueError, match='1 MiB'): generate(model(), request)
