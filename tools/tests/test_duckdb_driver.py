"""Real DuckDB retained connection, exact Arrow and native failure tests."""
import time
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import _create_client
from pgadmin.cdeadmin.providers.duckdb.values import parameters


def native():
    return pytest.importorskip('duckdb')


@pytest.fixture
def client():
    native()
    pytest.importorskip('pyarrow')
    value = _create_client()
    yield value
    value.close()


def open_database(client, tmp_path, **options):
    route = dict(database=str(tmp_path / 'active.duckdb'),
                 filesystem_root=str(tmp_path), **options)
    return client.open_session({'route': route}), route


def execute(client, handle, source, bindings=None):
    token = client.execute(handle, dict(source=source, parameters=bindings))
    return observe(client, token)


def observe(client, token):
    deadline = time.monotonic() + 10
    pages = []
    while time.monotonic() < deadline:
        page = client.describe_result(token)
        pages.append(page)
        if page['complete']:
            return pages
    raise AssertionError('DuckDB query did not finish')


def rows(pages):
    assert not pages[-1]['payload'].get('error'), pages[-1]
    return [row for page in pages for row in page['payload']['rows']]


def test_exact_arrow_types_and_bindings(client, tmp_path):
    h, _ = open_database(client, tmp_path)
    result = execute(client, h, '''SELECT $i AS same, $u AS same, $d,
        $b, $s, NULL, timestamp_ns '2026-01-01 00:00:00.123456789',
        interval '1 month 2 days 3 microseconds',
        '12:00:00+05:30'::TIMETZ, '101001'::BIT,
        date 'infinity', union_value(x:=42), map([1,2],['a','b']),
        {'nested':[1,2]}, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::UUID''', {
        'i': {'encoding': 'integer',
              'data': '170141183460469231731687303715884105727'},
        'u': {'encoding': 'integer',
              'data': '340282366920938463463374607431768211455'},
        'd': {'encoding': 'decimal', 'data': '1234567890.12345678'},
        'b': {'encoding': 'base64', 'data': 'AP8='}, 's': 'Grüße 🌲'})
    r = rows(result)[0]
    assert r[:3] == ['170141183460469231731687303715884105727',
                     '340282366920938463463374607431768211455',
                     '1234567890.12345678']
    assert r[3] == {'encoding': 'base64', 'data': 'AP8=', 'byte_length': 2}
    assert r[4:6] == ['Grüße 🌲', None]
    assert r[6]['ticks'].endswith('123456789')
    assert r[6]['arrow_type'] == 'timestamp[ns]'
    assert r[7] == {'months': 1, 'days': 2, 'nanoseconds': '3000'}
    assert r[8]['native_type'] == 'time_tz'
    assert r[9]['native_type'] == 'bit'
    assert r[10]['ticks'] == '2147483647'
    assert r[11] == {'tag': 'x', 'type_code': 0, 'value': 42}
    assert r[12] == {'encoding': 'map', 'entries': [[1, 'a'], [2, 'b']]}
    assert r[13] == {'nested': [1, 2]}
    assert r[14] == 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
    cols = next(p['schema']['columns'] for p in result
                if p['payload'].get('has_page'))
    # Native sql(params=...) materializes a relation and disambiguates labels.
    assert [c['name'] for c in cols[:2]] == ['same', 'same_1']
    assert cols[0]['key'] != cols[1]['key']
    assert rows(execute(client, h, 'SELECT ?', [42])) == [[42]]


def test_ordinary_run_refuses_multiple_statements_before_effects(client, tmp_path):
    h, _ = open_database(client, tmp_path)
    pages = execute(client, h, 'CREATE TABLE forbidden(i INT); SELECT 3')
    assert pages[-1]['payload']['error']['type'] == 'StatementCountError'
    assert h.execute("SELECT count(*) FROM duckdb_tables() "
                     "WHERE table_name='forbidden'").fetchone() == (0,)
    pages = execute(client, h, 'EXPLAIN SELECT 1; CREATE TABLE forbidden(i INT)')
    assert pages[-1]['payload']['error']['type'] == 'StatementCountError'
    assert h.execute("SELECT count(*) FROM duckdb_tables() "
                     "WHERE table_name='forbidden'").fetchone() == (0,)
    assert execute(client, h, '-- comment only')[-1]['payload']['error'][
        'type'] == 'StatementCountError'
    assert rows(execute(client, h, "SELECT 'é;😀';")) == [['é;😀']]
    assert rows(execute(client, h, 'SELECT 5;;')) == [[5]]
    assert rows(execute(client, h, 'SELECT 4')) == [[4]]


def test_one_import_command_may_expand_into_native_internal_statements(client, tmp_path):
    duckdb = native()
    source = tmp_path / 'export-source.duckdb'
    export = tmp_path / 'export-directory'
    quoted_export = str(export).replace("'", "''")
    owner = duckdb.connect(str(source))
    owner.execute('CREATE TABLE imported(i INTEGER)')
    owner.execute('INSERT INTO imported VALUES (7)')
    owner.execute(f"EXPORT DATABASE '{quoted_export}'")
    owner.close()
    handle, _ = open_database(client, tmp_path)
    pages = execute(client, handle, f"IMPORT DATABASE '{quoted_export}'")
    assert not pages[-1]['payload'].get('error'), pages[-1]
    assert rows(execute(client, handle, 'SELECT * FROM imported')) == [[7]]


def test_native_statement_metrics_identify_their_measured_scope(client, tmp_path):
    handle, _ = open_database(client, tmp_path)
    pages = execute(client, handle, 'SELECT i FROM range(600) t(i)')
    metrics = pages[-1]['payload']['statement_metrics']
    assert metrics['rows_buffered'] == 600
    assert metrics['prepare_ms'] is not None and metrics['prepare_ms'] >= 0
    assert metrics['dispatch_ms'] is not None and metrics['dispatch_ms'] >= 0
    assert metrics['fetch_ms'] is not None and metrics['fetch_ms'] >= 0
    assert metrics['execute_ms'] >= metrics['dispatch_ms']
    assert metrics['plan'] is None
    assert 'consumer backpressure' in metrics['measurement_scope']


def test_unsafe_parameters_refused_before_effects(client, tmp_path):
    h, _ = open_database(client, tmp_path)
    with pytest.raises(RuntimeError):
        client.execute(h, dict(source='SELECT ?', parameters=[2**60]))
    pages = execute(client, h, 'CREATE TABLE forbidden(i INT); SELECT ?', [1])
    assert pages[-1]['payload']['error']
    assert h.execute("SELECT count(*) FROM duckdb_tables() "
                     "WHERE table_name='forbidden'").fetchone() == (0,)
    # A refused request has no SQL effects; this validation does not poison it.


def test_transaction_commit_abort_and_metadata_same_session(client, tmp_path):
    h, route = open_database(client, tmp_path)
    rows(execute(client, h, 'CREATE TABLE retained(i INTEGER PRIMARY KEY)'))
    resources = client.list_resources({'route': route,
                                       '_provider_session_handle': h})
    assert any(r['display_name'] == 'retained' for r in resources)
    client.control_transaction(h, 'commit')
    rows(execute(client, h, 'INSERT INTO retained VALUES(1)'))
    failed = execute(client, h, 'INSERT INTO retained VALUES(1)')
    assert failed[-1]['payload']['error']['type'] == 'ConstraintException'
    assert client.describe_transaction(h)[
        'native_transaction_viability'] == 'aborted'
    client.control_transaction(h, 'commit')
    assert client.describe_transaction(h)['last_decision'] == 'rollback'
    assert rows(execute(client, h, 'SELECT count(*) FROM retained')) == [[0]]
    rows(execute(client, h, 'INSERT INTO retained VALUES(2)'))
    client.control_transaction(h, 'commit')
    with native().connect(route['database']) as observer:
        assert observer.execute('SELECT * FROM retained').fetchall() == [(2,)]


def test_interrupt_and_exclusive_session(client, tmp_path):
    h, _ = open_database(client, tmp_path)
    token = client.execute(h, {'source': 'SELECT sum(i*j) FROM '
                               'range(1000000) a(i), range(1000000) b(j)'})
    time.sleep(.1)
    with pytest.raises(RuntimeError, match='execution is active'):
        client.control_transaction(h, 'commit')
    assert client.cancel(token)
    pages = observe(client, token)
    assert pages[-1]['payload']['error']['type'] == 'InterruptException'
    client.control_transaction(h, 'rollback')
    assert rows(execute(client, h, 'SELECT 7')) == [[7]]


def test_close_backpressure_discards_uncommitted(client, tmp_path):
    h, route = open_database(client, tmp_path)
    rows(execute(client, h, 'CREATE TABLE t(i INT)'))
    client.control_transaction(h, 'commit')
    rows(execute(client, h, 'INSERT INTO t VALUES(1)'))
    token = client.execute(h, {'source': 'SELECT * FROM range(10000)'})
    deadline = time.monotonic() + 3
    while token.pages.qsize() < 2 and time.monotonic() < deadline:
        time.sleep(.01)
    assert client.close_session(h)['connection_released']
    with native().connect(route['database']) as observer:
        assert observer.execute('SELECT * FROM t').fetchall() == []


def test_read_only_and_quoted_attachment(client, tmp_path):
    h, route = open_database(client, tmp_path)
    rows(execute(client, h, 'CREATE TABLE t(i INT)'))
    client.control_transaction(h, 'commit')
    client.close_session(h)
    attachment = tmp_path / 'archive.duckdb'
    with native().connect(str(attachment)) as archive:
        archive.execute('CREATE TABLE archived(i INT)')
    attached_route = dict(route, read_only=True, attached_databases=[{
        'name': '档案 " copy', 'database': str(attachment)}])
    h = client.open_session({'route': attached_route})
    source = 'SELECT 1 FROM "档案 "" copy".main.archived LIMIT 0'
    assert rows(execute(client, h, source)) == []
    failed = execute(client, h, 'INSERT INTO t VALUES(1)')
    assert failed[-1]['payload']['error']


def test_decision_survives_next_begin_failure(client):
    h = Mock()
    client._connections.append(h)
    client._states[id(h)] = {'session_reuse_blocked': False}
    calls = []

    def command(sql):
        calls.append(sql)
        if sql == 'BEGIN TRANSACTION':
            raise native().IOException('fixture private detail')
        return Mock(fetchone=lambda: (42,))

    h.execute.side_effect = command
    client.control_transaction(h, 'commit')
    state = client.describe_transaction(h)
    assert state['decision_returned'] and state['last_decision'] == 'commit'
    assert state['session_reuse_blocked']
    assert not state['next_transaction_started']
    with pytest.raises(RuntimeError):
        client.control_transaction(h, 'commit')
    assert calls.count('COMMIT') == 1
    assert 'fixture private detail' not in str(state)


def test_release_failure_retains_owner(client):
    h = Mock()
    client._connections.append(h)
    client._states[id(h)] = {}
    h.close.side_effect = RuntimeError('fixture')
    with pytest.raises(RuntimeError, match='release failed'):
        client.close_session(h)
    assert h in client._connections
    h.close.side_effect = None
    client.close_session(h)
    assert h not in client._connections


def test_catalog_keys_and_uncommitted_grid(client, tmp_path):
    from pgadmin.cdeadmin.providers.duckdb.provider import ADMINISTRATION
    h, route = open_database(client, tmp_path)
    rows(execute(client, h, 'CREATE TABLE own(i INT PRIMARY KEY, v VARCHAR)'))
    rows(execute(client, h, "INSERT INTO own VALUES(1,'pending')"))
    assert ADMINISTRATION._primary_key(h, ['active', 'main', 'own']) == ['i']
    target = dict(resource_kind='table',
                  display_path=['active', 'main', 'own'])
    page = client.read_admin_rows(dict(
        _provider_route=route, _provider_session_handle=h,
        session_id='owned-test', target_resource=target))
    assert page['editable'] and page['rows'][0]['values']['v'] == 'pending'
    assert page['rows'][0]['identity_token']
    client.control_transaction(h, 'rollback')
    rows(execute(client, h, 'CREATE TABLE own(i INT PRIMARY KEY)'))
    client.control_transaction(h, 'commit')
    archive = tmp_path / 'archive.duckdb'
    with native().connect(str(archive)) as c:
        c.execute('CREATE TABLE own(other INTEGER PRIMARY KEY)')
    client.control_transaction(h, 'rollback')
    # ATTACH is a native SQL operation on this same retained connection.
    rows(execute(client, h, "ATTACH '" + str(archive).replace("'", "''") +
                 "' AS archive"))
    assert ADMINISTRATION._primary_key(
        h, ['archive', 'main', 'own']) == ['other']
    assert ADMINISTRATION._primary_key(h, ['active', 'main', 'own']) == ['i']


def test_native_write_conflict_is_not_retried(client, tmp_path):
    h, route = open_database(client, tmp_path)
    rows(execute(client, h, 'CREATE TABLE conflict(i INT PRIMARY KEY, v INT)'))
    rows(execute(client, h, 'INSERT INTO conflict VALUES(1,0)'))
    client.control_transaction(h, 'commit')
    other = client.open_session({'route': route})
    rows(execute(client, other, 'SELECT * FROM conflict'))
    rows(execute(client, h, 'UPDATE conflict SET v=1'))
    failed = execute(client, other, 'UPDATE conflict SET v=2')
    assert failed[-1]['payload']['error']['type'] == 'TransactionException'
    client.control_transaction(other, 'rollback')
    client.control_transaction(h, 'commit')
    assert rows(execute(client, other, 'SELECT v FROM conflict')) == [[1]]


def test_parser_refusal_never_applies_earlier_statement(client, tmp_path):
    h, _ = open_database(client, tmp_path)
    pages = execute(client, h, 'CREATE TABLE never(i INT); SELECT FROM')
    assert pages[-1]['payload']['error']['type'] == 'ParserException'
    assert rows(execute(client, h, "SELECT count(*) FROM duckdb_tables() "
                        "WHERE table_name='never'")) == [[0]]


def test_exact_nested_parameters_and_opaque_results(client, tmp_path):
    h, _ = open_database(client, tmp_path)
    assert rows(execute(client, h, 'SELECT ?', [[1, 2, 3]])) == [[[1, 2, 3]]]
    assert rows(execute(client, h, 'SELECT ?', [{'a': 42}])) == [[{'a': 42}]]
    big = '9' * 80
    result = rows(execute(client, h, 'SELECT ?', [
        {'encoding': 'integer', 'data': big}]))[0][0]
    assert result['native_type'] == 'bignum'
    assert result['storage']['encoding'] == 'base64'
    assert rows(execute(client, h, 'SELECT CAST(? AS VARCHAR)', [
        {'encoding': 'integer', 'data': big}])) == [[big]]
    assert rows(execute(client, h, "SELECT ['1'::UHUGEINT, NULL]")) == [
        [['1', None]]]
    assert rows(
        execute(
            client,
            h,
            "SELECT 'red'::ENUM('red','blue')")) == [
        ['red']]


def test_union_null_validity_and_volatile_expression_once(client, tmp_path):
    h, _ = open_database(client, tmp_path)
    rows(execute(client, h, 'CREATE SEQUENCE seq'))
    source = ("SELECT union_value(x:=NULL::INT), "
              "NULL::UNION(x INT,y VARCHAR), "
              "union_value(x:=nextval('seq')), "
              "[union_value(y:=NULL::VARCHAR)], "
              "{'a':union_value(x:=NULL::INT)}, "
              "map([1],[union_value(x:=NULL::INT)])")
    result = rows(execute(client, h, source))[0]
    null_x = dict(tag='x', type_code=0, value=None)
    assert result[:3] == [null_x, None, dict(tag='x', type_code=0, value=1)]
    assert result[3] == [dict(tag='y', type_code=0, value=None)]
    assert result[4] == {'a': null_x}
    assert result[5] == dict(encoding='map', entries=[[1, null_x]])
    assert rows(execute(client, h, "SELECT currval('seq')")) == [[1]]


def test_returning_union_never_replays_dml(client, tmp_path):
    h, _ = open_database(client, tmp_path)
    rows(execute(client, h,
                 'CREATE TABLE effects(i INT, u UNION(x INT,y VARCHAR))'))
    source = ("INSERT INTO effects VALUES(1,union_value(y:=NULL::VARCHAR)) "
              'RETURNING i,u')
    assert rows(execute(client, h, source)) == [[
        1, dict(tag='y', type_code=1, value=None)]]
    assert rows(execute(client, h, 'SELECT count(*) FROM effects')) == [[1]]
    updated = execute(client, h, 'UPDATE effects SET i=i+1 RETURNING i,u')
    assert rows(updated) == [[2, dict(tag='y', type_code=1, value=None)]]
    assert rows(execute(client, h, 'SELECT i FROM effects')) == [[2]]


def test_native_catalog_preserves_all_function_and_macro_overloads(client, tmp_path):
    from pgadmin.cdeadmin.providers.duckdb.provider import _resources
    handle, _ = open_database(client, tmp_path)
    handle.execute('CREATE MACRO owned_overloads(x) AS x+1, (x,y) AS x+y')
    handle.execute('CREATE TABLE pending_catalog(id INTEGER)')
    handle.execute('INSERT INTO pending_catalog VALUES (7)')
    expected = handle.execute('SELECT COUNT(*) FROM duckdb_functions()').fetchone()[0]
    resources = _resources(handle, {})
    functions = [item for item in resources if item['resource_kind'] in ('function', 'macro')]
    assert sum(item['native']['overload_count'] for item in functions) == expected
    group = next(item for item in functions if item['display_name'] == 'owned_overloads')
    native = group['native']
    assert native['overload_count'] == 2
    assert {tuple(p['name'] for p in item['parameters']) for item in native['overloads']} == {('x',), ('x', 'y')}
    assert {item['definition'] for item in native['overloads']} == {'(x + 1)', '(x + y)'}
    assert 'definition' not in native and 'parameters' not in native
    assert native['catalog_metadata']['function_type'] == 'macro'
    assert handle.execute('SELECT * FROM pending_catalog').fetchall() == [(7,)]
    client.control_transaction(handle, 'rollback')
    assert not handle.execute("SELECT * FROM duckdb_tables() WHERE table_name='pending_catalog'").fetchall()


def test_single_macro_keeps_its_unambiguous_definition(client, tmp_path):
    from pgadmin.cdeadmin.providers.duckdb.provider import _resources
    handle, _ = open_database(client, tmp_path)
    handle.execute('CREATE MACRO owned_single(x) AS x+1')
    native = next(item['native'] for item in _resources(handle, {}) if item['display_name'] == 'owned_single')
    assert native['overload_count'] == 1
    assert native['definition'] == '(x + 1)'
    assert native['parameters'] == [{'name': 'x', 'data_type': None}]
    assert native['overloads'][0]['definition'] == native['definition']
