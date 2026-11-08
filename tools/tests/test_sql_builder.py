"""Visual SQL builder: SQLite and DuckDB first (owner direction 2026-11-08).

The builder (owner direction 2026-11-06, option b) writes a query into the
SQL editor; nothing is run by ScratchRobin. These tests run the statements
it writes on real engines and check the rows: Python's sqlite3, DuckDB, and
the tracked SQLite 3.35.0 runtime for the version gate on RIGHT and FULL
joins. Every option is declared by each engine that offers the builder, and
the server refuses an option the connected runtime lacks.
"""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'web'
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from pgadmin.cdeadmin.sdk.browse import SqlNames  # noqa: E402
from pgadmin.cdeadmin.sdk.sql_builder import (  # noqa: E402
    OPTION_IDS, SqlBuilderError, build, relations, resolve_options)
from pgadmin.cdeadmin.workspace.service import (  # noqa: E402
    ProviderWorkspaceError, ProviderWorkspaceService)

DESCRIPTORS = WEB / 'pgadmin/cdeadmin/ui_descriptors'
TRACKED = ROOT / 'tools/reference_engine_demos/runtime/sqlite-tracked'
# Delimit every name; the providers' own keyword lists are tested below.
NAMES = SqlNames('"')


def declared(engine):
    path = DESCRIPTORS / engine / 'capabilities.json'
    return json.loads(path.read_text())['sql_builder']


def options(engine, version):
    return resolve_options(declared(engine), version)


SETUP = '''
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, region TEXT);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER,
                     amount INTEGER);
INSERT INTO customers VALUES (1, 'Ada', 'north'), (2, 'Bo''s', 'south'),
                             (3, 'Cy', NULL);
INSERT INTO orders VALUES (10, 1, 5), (11, 1, 7), (12, 2, 3), (13, 9, 1);
CREATE TABLE staff (id INTEGER PRIMARY KEY, manager_id INTEGER);
INSERT INTO staff VALUES (1, NULL), (2, 1), (3, 2), (4, NULL), (5, 4);
'''


def col(*parts):
    return {'column': list(parts)}


def value(item):
    return {'value': item}


def query(*selects, operators=(), **rest):
    return {'selects': list(selects), 'operators': list(operators), **rest}


def select(source, alias=None, **rest):
    return {'from': {'source': {'relation': [source]},
                     **({'alias': alias} if alias else {})}, **rest}


def sqlite_rows(sql):
    connection = sqlite3.connect(':memory:')
    connection.executescript(SETUP)
    return connection.execute(sql).fetchall()


def duckdb_rows(sql):
    duckdb = pytest.importorskip('duckdb')
    connection = duckdb.connect()
    for statement in SETUP.split(';'):
        if statement.strip():
            connection.execute(statement)
    return connection.execute(sql).fetchall()


TOTALS = {
    'with': [{'name': 'totals', 'materialized': True, 'query': query(
        select('orders', columns=[
            {'expr': col('customer_id')},
            {'expr': {'aggregate': {'function': 'sum',
                                    'argument': col('amount')}},
             'alias': 'total'},
            {'expr': {'aggregate': {'function': 'count', 'distinct': True,
                                    'argument': col('id')}},
             'alias': 'orders'}],
            group_by={'kind': 'columns', 'items': [col('customer_id')]},
            having={'compare': {'left': {'aggregate': {
                'function': 'count', 'argument': '*'}},
                'op': '>=', 'right': value(1)}}))}],
    'query': query(
        select('customers', 'c', columns=[
            {'expr': col('c', 'name')}, {'expr': col('t', 'total')}],
            joins=[{'type': 'left', 'source': {'cte': 'totals'},
                    'alias': 't', 'on': {'compare': {
                        'left': col('t', 'customer_id'), 'op': '=',
                        'right': col('c', 'id')}}}],
            where={'any': [{'compare': {'left': col('c', 'name'),
                                        'op': 'LIKE', 'right': value('%o%')}},
                           {'is_not_null': col('t', 'total')}]}),
        order_by=[{'expr': col('t', 'total'), 'direction': 'desc',
                   'nulls': 'last'}], limit=2, offset=0),
}
TOTALS_ROWS = [('Ada', 12), ("Bo's", 3)]

# A hierarchy walk: everyone reporting to staff 1, directly or not. The
# model has no arithmetic, so recursion follows rows (joins), not counters.
RECURSIVE = {
    'recursive': True,
    'with': [{'name': 'chain', 'columns': ['id'], 'query': query(
        select('staff', columns=[{'expr': col('id')}],
               where={'compare': {'left': col('id'), 'op': '=',
                                  'right': value(1)}}),
        select('staff', 's', columns=[{'expr': col('s', 'id')}],
               joins=[{'type': 'inner', 'source': {'cte': 'chain'},
                       'on': {'compare': {
                           'left': col('s', 'manager_id'), 'op': '=',
                           'right': col('chain', 'id')}}}]),
        operators=['union_all'])}],
    'query': query({'from': {'source': {'cte': 'chain'}}, 'columns': [
        {'expr': {'aggregate': {'function': 'count', 'argument': '*'}}}]}),
}

SETS = query(select('customers', columns=[{'expr': col('id')}]),
             select('orders', columns=[{'expr': col('customer_id')}]),
             select('orders', columns=[{'expr': col('customer_id')}],
                    where={'compare': {'left': col('amount'), 'op': '>',
                                       'right': value(4)}}),
             operators=['union', 'except'],
             order_by=[{'expr': col('id')}])


def joins(kind, **extra):
    return {'query': query(select(
        'customers', 'c', columns=[{'all': None}],
        joins=[{'type': kind, 'source': {'relation': ['orders']},
                'alias': 'o', **extra}]))}


ON = {'on': {'compare': {'left': col('o', 'customer_id'), 'op': '=',
                         'right': col('c', 'id')}}}


def test_every_offering_engine_declares_every_option():
    offering = sorted(path.parent.name for path in
                      DESCRIPTORS.glob('*/capabilities.json')
                      if 'sql_builder' in json.loads(path.read_text()))
    # MySQL and MariaDB: tools/tests/test_sql_builder_mysql_family.py.
    assert offering == ['duckdb', 'mariadb', 'mysql', 'sqlite']
    for engine in offering:
        assert list(declared(engine)['options']) == list(OPTION_IDS)
        for option, entry in declared(engine)['options'].items():
            assert entry['available'] or entry['reason'], (engine, option)


def test_sqlite_options_follow_the_connected_runtime():
    old, new = options('sqlite', '3.35.0'), options('sqlite', '3.53.0')
    for join in ('join.right', 'join.full'):
        assert not old[join]['available'] and '3.45.1' in old[join]['reason']
        assert new[join]['available'] and new[join]['reason'] == ''
    for option in ('distinct_on', 'group_by.rollup', 'group_by.cube',
                   'group_by.grouping_sets', 'group_by.all'):
        assert not new[option]['available'], option
    assert all(entry['available'] for entry in
               options('duckdb', '1.5.2').values())


@pytest.mark.parametrize('rows', [sqlite_rows, duckdb_rows])
def test_written_statements_return_the_expected_rows(rows):
    available = options('sqlite' if rows is sqlite_rows else 'duckdb', '3.53.0'
                        if rows is sqlite_rows else '1.5.2')
    assert rows(build(TOTALS, NAMES, available)) == TOTALS_ROWS
    assert rows(build(RECURSIVE, NAMES, available)) == [(3,)]
    assert rows(build({'query': SETS}, NAMES, available)) == [
        (2,), (3,), (9,)]
    assert len(rows(build(joins('inner', **ON), NAMES, available))) == 3
    assert len(rows(build(joins('left', **ON), NAMES, available))) == 4
    assert len(rows(build(joins('right', **ON), NAMES, available))) == 4
    assert len(rows(build(joins('full', **ON), NAMES, available))) == 5
    assert len(rows(build(joins('cross'), NAMES, available))) == 12
    assert len(rows(build(joins('inner', using=['id']), NAMES,
                          available))) == 0
    natural = {'query': query(select('customers', 'a', columns=[
        {'expr': col('a', 'id')}], joins=[{'type': 'natural', 'source': {
            'relation': ['customers']}, 'alias': 'b'}]),
        order_by=[{'expr': col('a', 'id')}])}
    # Natural joins match every shared column; customer 3's region is
    # NULL, which equals nothing, so it is not joined to itself.
    assert rows(build(natural, NAMES, available)) == [(1,), (2,)]


def test_duckdb_grouping_options():
    available = options('duckdb', '1.5.2')
    base = {'from': {'source': {'relation': ['customers']}}, 'columns': [
        {'expr': col('region')},
        {'expr': {'aggregate': {'function': 'count', 'argument': '*'}}}]}
    for group, count in (({'kind': 'rollup', 'items': [col('region')]}, 4),
                         ({'kind': 'cube', 'items': [col('region')]}, 4),
                         ({'kind': 'grouping_sets',
                           'sets': [[col('region')], []]}, 4),
                         ({'kind': 'all'}, 3)):
        sql = build({'query': query({**base, 'group_by': group})}, NAMES,
                    available)
        assert len(duckdb_rows(sql)) == count, sql
    distinct_on = {'query': query({
        'from': {'source': {'relation': ['orders']}},
        'distinct_on': [col('customer_id')], 'columns': [
            {'expr': col('customer_id')}]},
        order_by=[{'expr': col('customer_id')}])}
    assert duckdb_rows(build(distinct_on, NAMES, available)) == [
        (1,), (2,), (9,)]


def test_options_the_engine_lacks_are_refused():
    sqlite_now = options('sqlite', '3.53.0')
    for model in ({'query': query(select('orders', distinct_on=[
            col('customer_id')]))},
                  {'query': query(select('orders',
                                         group_by={'kind': 'all'}))}):
        with pytest.raises(SqlBuilderError, match='not available'):
            build(model, NAMES, sqlite_now)
    with pytest.raises(SqlBuilderError, match='3.45.1'):
        build(joins('right', **ON), NAMES, options('sqlite', '3.35.0'))


@pytest.mark.skipif(not (TRACKED / '3.35.0/bin/sqlite3').is_file(),
                    reason='the tracked SQLite 3.35.0 runtime is not built')
def test_the_join_gate_matches_sqlite_3_35_0():
    # The statement the gate refuses is one 3.35.0 itself refuses.
    sql = build(joins('right', **ON), NAMES, options('sqlite', '3.53.0'))
    runtime = TRACKED / '3.35.0'
    result = subprocess.run(
        [str(runtime / 'bin/sqlite3'), ':memory:', SETUP + sql + ';'],
        capture_output=True, text=True, timeout=30,
        env={'LD_LIBRARY_PATH': str(runtime / 'lib')})
    assert 'RIGHT and FULL OUTER JOINs are not currently supported' in (
        result.stderr + result.stdout)


def test_names_and_values_cannot_escape_their_quotes():
    available = options('sqlite', '3.53.0')
    connection = sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE "we""ird" ("a b" TEXT)')
    connection.execute('INSERT INTO "we""ird" VALUES (?)', ("x'); DROP",))
    sql = build({'query': query(select('we"ird', columns=[
        {'expr': col('a b'), 'alias': 'c"d'}], where={'compare': {
            'left': col('a b'), 'op': '=', 'right': value("x'); DROP")}}))},
        NAMES, available)
    assert connection.execute(sql).fetchall() == [("x'); DROP",)]
    for bad in ({'query': query(select('t', columns=[{'expr': {
            'raw': 'x'}}]))},
                {'query': query(select('t', where={'compare': {
                    'left': col('a'), 'op': 'OR 1=1', 'right': value(1)}}))},
                {'query': query({'from': {'source': {'cte': 'later'}}})},
                {'query': query(select('t'), select('t'))},
                {'query': query(select('t'), offset=1)},
                {'query': query(select('t', joins=[{
                    'type': 'inner', 'source': {'relation': ['u']}}]))},
                {'recursive': True, 'query': query(select('t'))},
                # Aggregates do not nest (and the model stays shallow).
                {'query': query(select('t', columns=[{'expr': {'aggregate': {
                    'function': 'count', 'argument': {'aggregate': {
                        'function': 'sum', 'argument': col('a')}}}}}]))}):
        with pytest.raises(SqlBuilderError):
            build(bad, NAMES, available)


def test_relations_list_the_catalog_tables_with_columns():
    catalog = [
        {'resource_kind': 'table', 'display_name': 'b',
         'display_path': ['main', 'b']},
        {'resource_kind': 'view', 'display_name': 'a',
         'display_path': ['main', 'a']},
        {'resource_kind': 'index', 'display_name': 'i',
         'display_path': ['main', 'i']}]
    listed = relations(catalog, ['table', 'view'],
                       lambda resource: [resource['display_name'] + '_id'])
    assert [(item['path'], item['columns']) for item in listed] == [
        (['main', 'a'], ['a_id']), (['main', 'b'], ['b_id'])]


def _service(version, profile='sqlite-native'):
    context = SimpleNamespace(endpoint_id=7)
    endpoint = {'identity': {'profile_id': profile}, 'route': {},
                'verified_runtime': {'version': version}}
    provider = SimpleNamespace(sql_builder_names=lambda: NAMES,
                               sql_builder_dialect=lambda: {},
                               profile=SimpleNamespace(
                                   language_profile='sqlite-sql'))
    page = SimpleNamespace(to_dict=lambda: {
        'items': [{'resource_kind': 'table', 'display_name': 'orders',
                   'display_path': ['main', 'orders']},
                  {'resource_kind': 'column', 'display_name': 'id',
                   'display_path': ['main', 'orders', 'id']}],
        'generation': 'g', 'next_cursor': None})
    return SimpleNamespace(
        endpoint_service=SimpleNamespace(
            workspace=Mock(return_value=(context, endpoint, {})),
            provider_registry=SimpleNamespace(resolve=Mock(
                return_value=SimpleNamespace(instance=provider)))),
        resource_service=SimpleNamespace(list_page=Mock(return_value=page)))


def test_the_server_refuses_a_gated_join_for_an_older_runtime():
    request = {'operation': 'source', 'model': joins('right', **ON)}
    # The route returns SqlBuilderError's text to the user.
    with pytest.raises(SqlBuilderError, match='3.45.1'):
        ProviderWorkspaceService.sql_builder(_service('3.35.0'), None, request)
    written = ProviderWorkspaceService.sql_builder(
        _service('3.53.0'), None, request)
    assert written['language_profile'] == 'sqlite-sql'
    assert 'RIGHT JOIN "orders" AS "o"' in written['source']
    listed = ProviderWorkspaceService.sql_builder(
        _service('3.35.0'), None, {'operation': 'options'})
    assert listed['options']['join.right']['available'] is False
    assert listed['relations'] == [{'path': ['main', 'orders'],
                                    'kind': 'table', 'name': 'orders',
                                    'columns': ['id']}]
    with pytest.raises(ProviderWorkspaceError, match='not available'):
        ProviderWorkspaceService.sql_builder(
            _service('5.0.4', 'firebird-native'), None,
            {'operation': 'options'})
    with pytest.raises(ProviderWorkspaceError, match='invalid'):
        ProviderWorkspaceService.sql_builder(
            _service('3.53.0'), None, {'operation': 'run'})


def test_providers_quote_with_their_own_keywords():
    from pgadmin.cdeadmin.providers import browse_builders
    provider = SimpleNamespace(browse_runtime_keywords=lambda: ['SELECT',
                                                                'ORDER'])
    names = browse_builders.sqlite_names(provider)
    assert names('orders') == 'orders' and names('order') == '"order"'
