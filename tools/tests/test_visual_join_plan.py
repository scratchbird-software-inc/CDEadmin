"""Execute generated joins, including reverse canvas edges and repeated tables."""
from itertools import permutations, product
import copy
import sqlite3

import pytest

from pgadmin.cdeadmin.workspace.sql_surface_host import build_visual_query_ddn_scene, parse_sql_to_visual_model


TABLES = [
    {'id': 'assets', 'name': 'ASSETS', 'alias': 't1'},
    {'id': 'customers', 'name': 'CUSTOMERS', 'alias': 't2'},
    {'id': 'open', 'name': 'OPEN_WORK_ORDERS', 'alias': 't3'},
]
JOINS = [
    {'join_type': 'INNER', 'left_table': 'customers', 'left_column': 'CUSTOMER_ID',
     'right_table': 'assets', 'right_column': 'CUSTOMER_ID'},
    {'join_type': 'INNER', 'left_table': 'customers', 'left_column': 'CUSTOMER_ID',
     'right_table': 'open', 'right_column': 'CUSTOMER'},
]


def render(tables=TABLES, joins=JOINS, **rest):
    return build_visual_query_ddn_scene({'tables': tables, 'joins': joins, **rest}, {}, 'firebird')


def rows(sql):
    with sqlite3.connect(':memory:') as db:
        db.executescript('''
            CREATE TABLE ASSETS(ASSET_ID INTEGER, CUSTOMER_ID INTEGER);
            CREATE TABLE CUSTOMERS(CUSTOMER_ID INTEGER);
            CREATE TABLE OPEN_WORK_ORDERS(CUSTOMER INTEGER);
            CREATE TABLE EMPTY_TABLE(ID INTEGER);
            INSERT INTO ASSETS VALUES(1,7),(2,7);
            INSERT INTO CUSTOMERS VALUES(7),(8);
            INSERT INTO OPEN_WORK_ORDERS VALUES(7),(8);
        ''')
        return db.execute(sql).fetchall()


@pytest.mark.parametrize('table_order', list(permutations(range(3))))
@pytest.mark.parametrize('join_order', [(0, 1), (1, 0)])
@pytest.mark.parametrize('directions', list(product((False, True), repeat=2)))
def test_join_graph_is_valid_in_every_drag_order(table_order, join_order, directions):
    joins = copy.deepcopy(JOINS)
    for join, reverse in zip(joins, directions):
        if reverse:
            join['left_table'], join['right_table'] = join['right_table'], join['left_table']
            join['left_column'], join['right_column'] = join['right_column'], join['left_column']
    projections = [{'table': 't1', 'column': 'ASSET_ID'}, {'table': 't2', 'column': 'CUSTOMER_ID'}]
    _, sql, _ = render([TABLES[i] for i in table_order], [joins[i] for i in join_order], projections=projections)
    assert sorted(rows(sql)) == [(1, 7), (2, 7)]
    for alias in ('t1', 't2', 't3'):
        assert sql.count(f'AS "{alias}"') == 1
    assert 'CROSS JOIN' not in sql


def test_reversed_left_join_keeps_unmatched_preserved_rows():
    join = {**JOINS[0], 'join_type': 'LEFT'}
    _, sql, _ = render(TABLES[:2], [join], projections=[
        {'table': 't1', 'column': 'ASSET_ID', 'expr': 't1.ASSET_ID'},
        {'table': 't2', 'column': 'CUSTOMER_ID', 'expr': 't2.CUSTOMER_ID'},
    ])
    assert 'LEFT JOIN' in sql and 'RIGHT JOIN' not in sql
    assert set(rows(sql)) == {(1, 7), (2, 7), (None, 8)}


def test_composite_relationship_uses_one_join_and_all_conditions():
    joins = [JOINS[0], {**JOINS[0], 'left_column': 'CUSTOMER_ID', 'right_column': 'ASSET_ID'}]
    _, sql, warnings = render(TABLES[:2], joins)
    assert sql.count('JOIN') == 1
    assert ' AND ' in sql
    assert rows(sql) == []
    assert not warnings
    parsed, _ = parse_sql_to_visual_model(sql)
    _, regenerated, _ = build_visual_query_ddn_scene(parsed, {}, 'firebird')
    assert rows(regenerated) == []


def test_inner_cycle_becomes_a_constraint_without_repeating_a_table():
    cycle = {'join_type': 'INNER', 'left_table': 'assets', 'left_column': 'CUSTOMER_ID',
             'right_table': 'open', 'right_column': 'CUSTOMER'}
    _, sql, _ = render(joins=JOINS+[cycle], where=['"t1"."ASSET_ID" = 1 OR "t1"."ASSET_ID" = 2'])
    assert len(rows(sql)) == 2
    assert sql.count(' JOIN ') == 2
    assert 'WHERE' in sql


def test_disconnected_full_component_is_grouped_before_cross_product():
    tables = [{'id': 'empty', 'name': 'EMPTY_TABLE', 'alias': 'e'}, *TABLES[1:]]
    join = {**JOINS[1], 'join_type': 'FULL'}
    _, sql, _ = render(tables, [join])
    assert 'CROSS JOIN (' in sql
    assert rows(sql) == []


def test_self_join_uses_two_instances_of_the_same_table():
    tables = [TABLES[0], {'id': 'other', 'name': 'ASSETS', 'alias': 'other'}]
    join = {**JOINS[0], 'left_table': 'assets', 'right_table': 'other'}
    _, sql, _ = render(tables, [join], projections=[
        {'table': 'assets', 'column': 'ASSET_ID'}, {'table': 'other', 'column': 'ASSET_ID'}])
    assert set(rows(sql)) == {(1,1), (1,2), (2,1), (2,2)}
    with pytest.raises(ValueError, match='Ambiguous'):
        render(tables, [{**join, 'left_table': 'ASSETS'}])


@pytest.mark.parametrize('tables,joins,message', [
    ([TABLES[0], {**TABLES[1], 'alias':'t1'}], [JOINS[0]], 'unique alias'),
    ([TABLES[0], {**TABLES[1], 'id':'assets'}], [JOINS[0]], 'Duplicate'),
    (TABLES, [{**JOINS[0], 'left_table':'missing'}], 'Unknown'),
    (TABLES, [{**JOINS[0], 'join_type':'TYPO'}], 'Unsupported'),
    (TABLES, [{**JOINS[0], 'left_column':''}], 'Select both'),
])
def test_invalid_models_are_refused(tables, joins, message):
    with pytest.raises(ValueError, match=message):
        render(tables, joins)


def test_cross_join_never_emits_on():
    _, sql, _ = render(TABLES[:2], [{**JOINS[0], 'join_type':'CROSS'}])
    assert 'CROSS JOIN' in sql and ' ON ' not in sql
    assert len(rows(sql)) == 4


def test_custom_on_dependencies_are_available_before_its_join():
    joins = [{**JOINS[0], 'custom_on':'"t2"."CUSTOMER_ID" = "t1"."CUSTOMER_ID" AND "t3"."CUSTOMER" = "t2"."CUSTOMER_ID"'}, JOINS[1]]
    _, sql, _ = render(joins=joins)
    assert len(rows(sql)) == 2


def test_duplicate_alias_sql_is_not_claimed_as_an_exact_visual_model():
    model, fidelity = parse_sql_to_visual_model('SELECT * FROM ASSETS t1 JOIN ASSETS t1 ON t1.ASSET_ID=t1.ASSET_ID')
    assert model is None and fidelity == 'none'


def test_outer_cycle_is_refused_instead_of_changing_null_preservation():
    joins = [{**join, 'join_type':'LEFT'} for join in JOINS]
    joins.append({'join_type':'LEFT','left_table':'assets','left_column':'CUSTOMER_ID',
                  'right_table':'open','right_column':'CUSTOMER'})
    with pytest.raises(ValueError, match='Cyclic outer'):
        render(joins=joins)


def test_left_reversal_groups_an_existing_inner_prefix():
    joins = [{'join_type':'INNER','left_table':'assets','left_column':'CUSTOMER_ID',
              'right_table':'open','right_column':'CUSTOMER'},
             {**JOINS[0], 'join_type':'LEFT'}]
    _, sql, _ = render(TABLES, joins, projections=[
        {'table':'t1','column':'ASSET_ID'}, {'table':'t2','column':'CUSTOMER_ID'}])
    assert set(rows(sql)) == {(1,7),(2,7),(None,8)}
    assert 'RIGHT JOIN' not in sql
