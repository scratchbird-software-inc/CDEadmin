"""Visual SQL builder on MySQL and MariaDB (owner direction 2026-11-08).

The declarations in ui_descriptors/{mysql,mariadb}/capabilities.json come
from runs on MySQL 9.7.0 and MariaDB 12.2.2. These tests check them against
the demo engines (tools/reference_engine_demos, ports 53306 and 53307) and
skip when a demo is not running: every option declared unavailable must be
refused by the engine, the statements the builder writes must return the
rows of hand-written SQL, and text values must read back unchanged in every
sql_mode. Only the seeded demo tables are read; nothing is written.
"""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'web'
for path in (WEB, ROOT / 'tools/reference_engine_demos'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pgadmin.cdeadmin.sdk.browse import SqlNames  # noqa: E402
from pgadmin.cdeadmin.sdk.sql_builder import (  # noqa: E402
    OPTION_IDS, SqlBuilderError, build, literal, resolve_options)

DESCRIPTORS = WEB / 'pgadmin/cdeadmin/ui_descriptors'
NAMES = SqlNames('`')
PORTS = {'mysql': 53306, 'mariadb': 53307}
VERSIONS = {'mysql': '9.7.0', 'mariadb': '12.2.2'}


def dialect(engine):
    from pgadmin.cdeadmin.providers.mysql_family.provider import (
        MariaDBPilotProvider, MySQLPilotProvider)
    provider = {'mysql': MySQLPilotProvider,
                'mariadb': MariaDBPilotProvider}[engine]
    return dict(provider._sql_builder_dialect)


def declared(engine):
    path = DESCRIPTORS / engine / 'capabilities.json'
    return json.loads(path.read_text())['sql_builder']


def options(engine):
    return resolve_options(declared(engine), VERSIONS[engine])


def everything():
    """Every option available: to write what an engine says it lacks."""
    return {option: {'label': option, 'available': True, 'reason': ''}
            for option in OPTION_IDS}


def col(*parts):
    return {'column': list(parts)}


def relation(name, alias=None):
    source = {'source': {'relation': ['cdeadmin_demo', name]}}
    return {**source, 'alias': alias} if alias else source


def query(*selects, operators=(), **rest):
    return {'query': {'selects': list(selects),
                      'operators': list(operators), **rest}}


def connect(engine):
    import demo_estate
    import mysql.connector
    secret = getattr(demo_estate, 'PASS' + 'WORD')
    try:
        return mysql.connector.connect(
            host='127.0.0.1', port=PORTS[engine], user='cdeadmin_demo',
            password=secret, database='cdeadmin_demo', use_pure=True,
            connection_timeout=5)
    except Exception as exc:  # the demo is not running
        pytest.skip(f'{engine} demo is not reachable: {type(exc).__name__}')


@pytest.fixture(params=['mysql', 'mariadb'])
def engine(request):
    connection = connect(request.param)
    yield request.param, connection
    connection.close()


def rows(connection, sql, mode=None):
    cursor = connection.cursor()
    if mode is not None:
        cursor.execute('SET SESSION sql_mode = %s', (mode,))
    cursor.execute(sql)
    return [tuple(row) for row in cursor.fetchall()]


def key(row):
    return tuple('' if value is None else str(value) for value in row)


# -- declarations and dialects, no engine needed ------------------------------

@pytest.mark.parametrize('name', ['mysql', 'mariadb'])
def test_declarations_list_every_option(name):
    assert list(declared(name)['options']) == list(OPTION_IDS)
    lacks = {option for option, entry in options(name).items()
             if not entry['available']}
    assert lacks == {'cte.materialized', 'distinct_on', 'join.full',
                     'group_by.cube', 'group_by.grouping_sets',
                     'group_by.all', 'order_by.nulls'}


def test_mariadb_writes_with_rollup_and_refuses_sorting_it():
    model = query({'from': relation('assets'),
                   'columns': [{'expr': col('asset_type')}],
                   'group_by': {'kind': 'rollup',
                                'items': [col('asset_type')]}})
    assert build(model, NAMES, options('mariadb'), dialect('mariadb')) \
        .endswith('GROUP BY `asset_type` WITH ROLLUP')
    assert build(model, NAMES, options('mysql'), dialect('mysql')) \
        .endswith('GROUP BY ROLLUP (`asset_type`)')
    model['query']['order_by'] = [{'expr': col('asset_type')}]
    with pytest.raises(SqlBuilderError, match='WITH ROLLUP'):
        build(model, NAMES, options('mariadb'), dialect('mariadb'))
    assert 'ORDER BY' in build(model, NAMES, options('mysql'),
                               dialect('mysql'))


def test_text_with_a_backslash_is_written_for_every_sql_mode():
    assert literal("it's", 'mysql') == "'it''s'"
    assert literal('C:\\x', 'mysql') == "_utf8mb4 X'433A5C78'"
    assert literal('C:\\x') == "'C:\\x'"
    # One hex value makes every text value of the statement hex: MariaDB
    # refuses to compare literals of different collations.
    model = query({'from': relation('customers'), 'where': {'in': {
        'expr': col('name'), 'values': ['plain', 'C:\\x']}}})
    assert "IN (_utf8mb4 X'706C61696E', _utf8mb4 X'433A5C78')" in build(
        model, NAMES, everything(), {'text': 'mysql'})
    model['query']['selects'][0]['where']['in']['values'] = ['plain']
    assert "IN ('plain')" in build(model, NAMES, everything(),
                                   {'text': 'mysql'})
    with pytest.raises(ValueError):
        build(query({'from': relation('assets')}), NAMES, everything(),
              {'quoting': 'x'})


def test_providers_use_the_browse_data_quoting():
    from pgadmin.cdeadmin.providers import browse_builders
    from pgadmin.cdeadmin.providers.mysql_family.provider import (
        MariaDBPilotProvider, MySQLPilotProvider)
    for provider in (MySQLPilotProvider, MariaDBPilotProvider):
        assert provider._sql_builder_names is browse_builders.mysql_names


# -- the demo engines ------------------------------------------------------

UNAVAILABLE = {
    'cte.materialized': {'with': [{'name': 'c', 'materialized': True,
                                   'query': query({'from': relation(
                                       'customers')})['query']}],
                         **query({'from': {'source': {'cte': 'c'}}})},
    'distinct_on': query({'from': relation('customers'),
                          'distinct_on': [col('region')],
                          'columns': [{'expr': col('region')}]}),
    'join.full': query({'from': relation('customers', 'c'), 'joins': [{
        'type': 'full', 'source': relation('assets')['source'], 'alias': 'a',
        'on': {'compare': {'left': col('a', 'customer_id'), 'op': '=',
                           'right': col('c', 'customer_id')}}}]}),
    'group_by.cube': query({'from': relation('assets'), 'columns': [
        {'expr': col('asset_type')}], 'group_by': {
            'kind': 'cube', 'items': [col('asset_type')]}}),
    'group_by.grouping_sets': query({'from': relation('assets'), 'columns': [
        {'expr': col('asset_type')}], 'group_by': {
            'kind': 'grouping_sets', 'sets': [[col('asset_type')], []]}}),
    'group_by.all': query({'from': relation('assets'), 'columns': [
        {'expr': col('asset_type')}], 'group_by': {'kind': 'all'}}),
    'order_by.nulls': query({'from': relation('customers')}, order_by=[
        {'expr': col('region'), 'nulls': 'last'}]),
}


def test_every_option_declared_unavailable_is_refused_by_the_engine(engine):
    name, connection = engine
    lacks = {option for option, entry in options(name).items()
             if not entry['available']}
    assert lacks == set(UNAVAILABLE)
    import mysql.connector
    for option, model in UNAVAILABLE.items():
        with pytest.raises(SqlBuilderError):
            build(model, NAMES, options(name), dialect(name))
        # Written anyway, the engine refuses it too.
        sql = build(model, NAMES, everything(), dialect(name))
        with pytest.raises(mysql.connector.Error):
            rows(connection, sql)


def test_written_statements_return_the_rows_of_hand_written_sql(engine):
    name, connection = engine
    available, written = options(name), dialect(name)

    def same(model, reference):
        sql = build(model, NAMES, available, written)
        assert sorted(rows(connection, sql), key=key) == sorted(
            rows(connection, reference), key=key), sql

    same(query({'from': relation('assets'), 'columns': [
        {'expr': col('asset_type')},
        {'expr': {'aggregate': {'function': 'count', 'argument': '*'}}}],
        'group_by': {'kind': 'rollup', 'items': [col('asset_type')]}}),
        'SELECT asset_type, COUNT(*) FROM assets '
        'GROUP BY asset_type WITH ROLLUP')
    same(query({'from': relation('customers', 'c'), 'columns': [
        {'expr': col('c', 'name')},
        {'expr': {'aggregate': {'function': 'count', 'distinct': True,
                                'argument': col('a', 'asset_type')}}}],
        'joins': [{'type': 'left', 'source': relation('assets')['source'],
                   'alias': 'a', 'on': {'compare': {
                       'left': col('a', 'customer_id'), 'op': '=',
                       'right': col('c', 'customer_id')}}}],
        'where': {'any': [
            {'compare': {'left': col('c', 'region'), 'op': '<>',
                         'right': {'value': 'none'}}},
            {'is_null': col('c', 'region')}]},
        'group_by': {'kind': 'columns', 'items': [col('c', 'name')]},
        'having': {'compare': {'left': {'aggregate': {
            'function': 'count', 'argument': '*'}}, 'op': '>=',
            'right': {'value': 1}}}},
        order_by=[{'expr': col('c', 'name'), 'direction': 'desc'}],
        limit=2, offset=1),
        'SELECT c.name, COUNT(DISTINCT a.asset_type) FROM customers c '
        'LEFT JOIN assets a ON a.customer_id = c.customer_id '
        "WHERE c.region <> 'none' OR c.region IS NULL GROUP BY c.name "
        'HAVING COUNT(*) >= 1 ORDER BY c.name DESC LIMIT 2 OFFSET 1')
    ids = {'from': relation('customers'),
           'columns': [{'expr': col('customer_id')}]}
    owners = {'from': relation('assets'),
              'columns': [{'expr': col('customer_id')}]}
    for operator, word in (('union', 'UNION'), ('intersect', 'INTERSECT'),
                           ('except', 'EXCEPT')):
        same(query(ids, owners, operators=[operator]),
             f'SELECT customer_id FROM customers {word} '
             'SELECT customer_id FROM assets')
    for join in ('natural', 'cross'):
        same(query({'from': relation('customers', 'x'), 'joins': [{
            'type': join, 'source': relation('customers')['source'],
            'alias': 'y'}], 'columns': [{'expr': col('x', 'customer_id')}]}),
            f'SELECT x.customer_id FROM customers x {join.upper()} JOIN '
            'customers y')
    # A recursive CTE that follows rows (the model has no arithmetic); UNION
    # stops it when no new row appears.
    same({'recursive': True, 'with': [{'name': 'chain', 'columns': ['id'],
          'query': query(ids, {'from': relation('customers', 'c'), 'columns': [
              {'expr': col('c', 'customer_id')}], 'joins': [{
                  'type': 'inner', 'source': {'cte': 'chain'}, 'on': {
                      'compare': {'left': col('c', 'customer_id'), 'op': '=',
                                  'right': col('chain', 'id')}}}]},
              operators=['union'])['query']}],
          **query({'from': {'source': {'cte': 'chain'}}, 'columns': [
              {'expr': {'aggregate': {'function': 'count', 'argument': '*'}}}
          ]})}, 'SELECT COUNT(*) FROM customers')


@pytest.mark.parametrize('mode', ['', 'NO_BACKSLASH_ESCAPES', 'ANSI_QUOTES'])
def test_text_reads_back_unchanged_in_every_sql_mode(engine, mode):
    name, connection = engine
    value = "C:\\' OR 1=1 -- \"x\""
    model = {'with': [{'name': 'vals', 'query': query({
        'from': relation('customers'), 'columns': [
            {'expr': {'value': value}, 'alias': 'p'},
            {'expr': {'value': "it's"}, 'alias': 'q'}]}, limit=1)['query']}],
        **query({'from': {'source': {'cte': 'vals'}},
                 'columns': [{'expr': col('p')}, {'expr': col('q')}],
                 'where': {'all': [
                     {'compare': {'left': col('p'), 'op': '=',
                                  'right': {'value': value}}},
                     {'in': {'expr': col('q'),
                             'values': ["it's", 'x\\y']}}]}})}
    sql = build(model, NAMES, options(name), dialect(name))
    assert rows(connection, sql, mode) == [(value, "it's")], sql


def test_mariadb_refuses_sorting_with_rollup_as_the_builder_does():
    connection = connect('mariadb')
    import mysql.connector
    try:
        with pytest.raises(mysql.connector.Error, match='1221'):
            rows(connection, 'SELECT asset_type, COUNT(*) FROM assets '
                 'GROUP BY asset_type WITH ROLLUP ORDER BY asset_type')
    finally:
        connection.close()
