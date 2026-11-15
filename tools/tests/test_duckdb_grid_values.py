"""Native row-page precision and optimistic mutation acceptance."""
import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import _create_client, _resources
from pgadmin.cdeadmin.sdk import RelationalClientError


@pytest.fixture
def native(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    pytest.importorskip('pyarrow')
    path = tmp_path / 'exact.duckdb'
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    client = _create_client()
    handle = client.open_session({'route': route})
    try:
        yield client, handle, route, duckdb
    finally:
        client.close()


def page(client, handle, route):
    target = next(row for row in _resources(handle, {'session_catalog': True})
                  if row['resource_kind'] == 'table' and
                  row['display_name'] == 'exact')
    value = client.read_admin_rows({
        '_provider_route': route, '_provider_session_handle': handle,
        'session_id': 'owned', 'target_resource': target})
    return target, value


def update(client, handle, route, target, row, changes):
    planned = client.plan_admin_operation({
        'resource_kind': 'table', 'operation_id': 'update',
        'target_resource': target, '_provider_route': route,
        'session_id': 'owned', 'draft': {
            'selector': {'identity_token': row['identity_token']},
            'changes': changes}})
    planned['_provider_session_handle'] = handle
    return client.apply_admin_operation(planned)


def test_nanoseconds_and_wide_integers_survive_page_and_unrelated_edit(native):
    client, handle, route, duckdb = native
    handle.execute('CREATE TABLE exact(id INT PRIMARY KEY, n INT, '
                   'ts TIMESTAMP_NS, wide HUGEINT)')
    handle.execute("INSERT INTO exact VALUES(1,0,"
                   "TIMESTAMP_NS '2026-01-01 00:00:00.123456789',"
                   '170141183460469231731687303715884105727)')
    client.control_transaction(handle, 'commit')
    target, result = page(client, handle, route)
    row = result['rows'][0]
    assert row['values']['ts']['ticks'] == '1767225600123456789'
    assert row['values']['wide'] == '170141183460469231731687303715884105727'
    assert update(client, handle, route, target, row, {'n': 7})[
        'staged_in_provider_session']
    assert handle.execute('SELECT n,epoch_ns(ts) FROM exact').fetchone() == (
        7, 1767225600123456789)
    with duckdb.connect(route['database']) as observer:
        assert observer.execute('SELECT n FROM exact').fetchone() == (0,)
    client.control_transaction(handle, 'rollback')
    assert handle.execute('SELECT n FROM exact').fetchone() == (0,)


@pytest.mark.parametrize('expression', [
    "TIMESTAMP_NS '1960-01-01 00:00:00.123456789'",
    "TIMESTAMP 'infinity'", "DATE '-infinity'",
    "'12:00:00.123456+05:30'::TIMETZ", "'101001'::BIT",
    "INTERVAL '1 month 2 days 3 microseconds'",
    "'170141183460469231731687303715884105727'::HUGEINT",
    "'340282366920938463463374607431768211455'::UHUGEINT",
    "12345678901234567890.123456789012345678::DECIMAL(38,18)",
    "'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::UUID",
    "'NaN'::DOUBLE", "'-0.0'::DOUBLE", "BLOB '\\x00\\xFF'",
    "map([1,2],['NUL' || chr(0) || '雪',NULL])",
    "{'nested':[TIMESTAMP_NS '2026-01-01 00:00:00.123456789',NULL]}",
    "union_value(x:=42)::UNION(x INT,y VARCHAR)",
    "union_value(y:=NULL::VARCHAR)::UNION(x INT,y VARCHAR)",
    "NULL::UNION(x INT,y VARCHAR)",
    "[union_value(y:='雪'),NULL]::UNION(x INT,y VARCHAR)[]",
    "{'u':union_value(x:=42)}", "[]::INT[]", "[1,NULL]::INT[2]",
])
def test_exact_native_originals_do_not_make_unchanged_rows_stale(native, expression):
    client, handle, route, _duckdb = native
    handle.execute('CREATE TABLE exact AS SELECT 1 AS id,0 AS n,'
                   + expression + ' AS value')
    handle.execute('ALTER TABLE exact ADD PRIMARY KEY(id)')
    target, result = page(client, handle, route)
    assert update(client, handle, route, target, result['rows'][0],
                  {'n': 9})['accepted']
    assert handle.execute('SELECT n FROM exact').fetchone() == (9,)


def test_one_nanosecond_change_invalidates_original_row_token(native):
    client, handle, route, _duckdb = native
    handle.execute('CREATE TABLE exact(id INT PRIMARY KEY,n INT,ts TIMESTAMP_NS)')
    handle.execute("INSERT INTO exact VALUES(1,0,"
                   "TIMESTAMP_NS '2026-01-01 00:00:00.123456789')")
    target, result = page(client, handle, route)
    handle.execute("UPDATE exact SET ts=TIMESTAMP_NS "
                   "'2026-01-01 00:00:00.123456790'")
    with pytest.raises(RelationalClientError, match='exactly one row'):
        update(client, handle, route, target, result['rows'][0], {'n': 9})
    assert handle.execute('SELECT n,epoch_ns(ts) FROM exact').fetchone() == (
        0, 1767225600123456790)


def test_row_observation_does_not_change_callers_arrow_policy(native):
    client, handle, route, _duckdb = native
    handle.execute('CREATE TABLE exact(id INT PRIMARY KEY)')
    handle.execute('INSERT INTO exact VALUES(1)')
    handle.execute('SET arrow_lossless_conversion=false')
    page(client, handle, route)
    assert handle.execute("SELECT current_setting("
                          "'arrow_lossless_conversion')").fetchone() == (False,)


def test_native_identity_helpers_cannot_be_shadowed_by_user_macros(native):
    client, handle, route, _duckdb = native
    handle.execute('CREATE TABLE exact(id INT PRIMARY KEY,n INT, '
                   'u UNION(x INT,y VARCHAR))')
    handle.execute("INSERT INTO exact VALUES(1,0,union_value(y:='雪'))")
    handle.execute('CREATE MACRO list_transform(a,b) AS [999]')
    handle.execute('CREATE MACRO union_value(x) AS 999')
    handle.execute('CREATE MACRO current_setting(x) AS true')
    handle.execute('SET arrow_lossless_conversion=false')
    target, result = page(client, handle, route)
    assert handle.execute('SELECT "system"."main".current_setting('
                          "'arrow_lossless_conversion')").fetchone() == (False,)
    assert result['rows'][0]['values']['u']['tag'] == 'y'
    assert update(client, handle, route, target, result['rows'][0],
                  {'n': 3})['accepted']
    assert handle.execute('SELECT n FROM exact').fetchone() == (3,)


def test_generated_source_value_is_observed_once_for_public_and_identity(native):
    client, handle, route, _duckdb = native
    calls = []

    def observe(value: int) -> int:
        calls.append(value)
        return value

    handle.create_function('observe_once', observe, side_effects=True)
    handle.execute('CREATE TABLE exact(id INT PRIMARY KEY, '
                   'n INT GENERATED ALWAYS AS (observe_once(id)))')
    handle.execute('INSERT INTO exact(id) VALUES(1)')
    calls.clear()
    _target, result = page(client, handle, route)
    assert result['rows'][0]['values']['n'] == 1
    assert calls == [1]
