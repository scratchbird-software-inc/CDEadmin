"""Firebird query generation preserves catalog identity with minimal quoting."""
import pytest

from pgadmin.cdeadmin.providers.firebird.identifiers import query_names
from pgadmin.cdeadmin.workspace.data_surface_host import _quote_ident, _build_display_select_sql
from pgadmin.cdeadmin.workspace.sql_surface_host import build_visual_query_ddn_scene


@pytest.mark.parametrize('name,expected', [
    ('ASSETS', 'ASSETS'), ('CUSTOMER_ID', 'CUSTOMER_ID'), ('RDB$DATABASE', 'RDB$DATABASE'),
    ('A_9$', 'A_9$'), ('NAME', 'NAME'), ('FIRST', 'FIRST'),
    ('MyTable', '"MyTable"'), ('mytable', '"mytable"'),
    ('9TABLE', '"9TABLE"'), ('_TABLE', '"_TABLE"'), ('$TABLE', '"$TABLE"'),
    ('A B', '"A B"'), ('A-B', '"A-B"'), ('CAFÉ', '"CAFÉ"'),
    ('ORDER', '"ORDER"'), ('USER', '"USER"'), ('DATE', '"DATE"'),
    ('A"B', '"A""B"'), (' TRAILING ', '" TRAILING "'),
])
def test_catalog_identifiers(name, expected):
    for engine in ('firebird', 'firebird-embedded'):
        assert _quote_ident(name, engine) == expected
    assert query_names()(name) == expected


def test_visual_query_quotes_only_required_names_in_each_position():
    model = {
        'tables': [{'id': 'a', 'name': 'ASSETS', 'alias': 'A'},
                   {'id': 'b', 'name': 'Order Details', 'alias': 'b'}],
        'joins': [{'left_table': 'a', 'left_column': 'CUSTOMER_ID',
                   'right_table': 'b', 'right_column': 'CustomerId'}],
        'projections': [{'table': 'a', 'column': 'TAG', 'alias': 'NAME'},
                        {'table': 'b', 'column': 'ORDER', 'alias': 'MixedCase'}],
    }
    _, sql, _ = build_visual_query_ddn_scene(model, {}, 'firebird')
    assert sql == ('SELECT\n  A.TAG AS NAME,\n  "b"."ORDER" AS "MixedCase"\n'
                   'FROM ASSETS AS A\nINNER JOIN "Order Details" AS "b" '
                   'ON A.CUSTOMER_ID = "b"."CustomerId";')


def test_selectable_procedure_and_output_field_identity():
    _, sql, _ = build_visual_query_ddn_scene({
        'tables': [{'id': 'p', 'name': 'READ_ASSETS', 'alias': 'P',
                    'resource_kind': 'procedure'}],
        'projections': [{'table': 'p', 'column': 'ASSET_ID'},
                        {'table': 'p', 'column': 'Mixed Field'}],
    }, {}, 'firebird')
    assert sql == 'SELECT\n  P.ASSET_ID,\n  P."Mixed Field"\nFROM READ_ASSETS AS P;'


def test_other_engines_keep_their_identifier_policy():
    assert _quote_ident('ASSETS', 'postgresql') == '"ASSETS"'
    assert _quote_ident('ASSETS', 'mysql') == '`ASSETS`'
    assert _quote_ident('MixedCase', 'sqlite') == '"MixedCase"'


def test_display_select_quotes_filters_and_sorts_without_changing_values():
    sql, parameters = _build_display_select_sql(
        {'authority_path': ['ASSETS']}, 'firebird', ['ASSET_ID', 'MixedCase', 'ORDER'],
        [{'column': 'ASSET_ID', 'direction': 'desc'}],
        [{'column': 'MixedCase', 'op': 'eq', 'value': 'unchanged'}], 10, 'server')
    assert sql == ('SELECT FIRST 10 ASSET_ID, "MixedCase", "ORDER"\nFROM ASSETS'
                   '\nWHERE "MixedCase" = ?\nORDER BY ASSET_ID DESC;')
    assert parameters == ['unchanged']
