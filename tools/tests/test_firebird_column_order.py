"""Native complete-table permutations and execution-time drift guard."""
from copy import deepcopy
from itertools import permutations
from unittest.mock import Mock

import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.providers.firebird import column_order
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine


def target():
    return {'resource_kind': 'table', 'display_name': 'T"ü', 'display_path': ['T"ü'],
        'native': {'relation_id': 128, 'relation_type': 0, 'system_object': False,
                   'columns': [{'name': name, 'position': n} for n, name in enumerate('ABCD')],
                   'column_order': list('ABCD')}}


def request(order):
    return {'resource_kind': 'table', 'operation_id': 'reorder_columns',
        '_provider_route': {'database': 'owned'}, 'target_resource': target(), 'draft': {'column_order': order}}


def test_every_permutation_generates_correct_sequential_moves():
    for order in permutations('ABCD'):
        if order == tuple('ABCD'):
            continue
        compiled = column_order.compile_operation({'column_order': list(order)}, target())
        actual = list('ABCD')
        for command in compiled['statements']:
            sql = command['source']
            assert sql.startswith('ALTER TABLE "T""ü" ALTER COLUMN ')
            name, position = sql.split(' ALTER COLUMN ')[1].split(' POSITION ')
            actual.remove(name.strip('"'))
            actual.insert(int(position) - 1, name.strip('"'))
        assert actual == list(order)
        assert compiled['firebird_column_order']['before'] == list('ABCD')


@pytest.mark.parametrize('order', [[], ['A'], list('AABC'), list('ABCDE'), 'DCBA', [1, 2, 3, 4], list('ABCD')])
def test_incomplete_duplicate_new_or_unchanged_order_refused(order):
    assert ADMINISTRATION.validate(request(order))['errors']


@pytest.mark.parametrize('change', [
    {'system_object': True}, {'relation_type': 1}, {'relation_type': 3},
    {'relation_id': None}, {'columns': []},
    {'columns': [{'name': 'A', 'position': 1}]},
])
def test_missing_or_inapplicable_target_refused(change):
    req = request(list('DCBA'))
    req['target_resource']['native'].update(change)
    assert ADMINISTRATION.validate(req)['errors']


def test_plan_and_native_guard_bind_complete_order_and_relation_identity():
    req = request(list('DABC'))
    assert ADMINISTRATION.validate(req) == {'errors': []}
    plan = ADMINISTRATION.plan(req)
    assert plan['command_preview']['statements'][0]['source'] == 'ALTER TABLE "T""ü" ALTER COLUMN "D" POSITION 1'
    guard = column_order.compile_operation(req['draft'], req['target_resource'])['firebird_column_order']
    cursor = Mock()
    rows = [(128, 0, 0, name, n) for n, name in enumerate('ABCD')]
    cursor.fetchall.return_value = rows
    column_order.verify(cursor, guard)
    assert cursor.execute.call_args.args[1] == ('T"ü',)
    for changed in [[], rows[:-1], [(129, *row[1:]) for row in rows],
                    [(128, 0, 0, name, n) for n, name in enumerate('BACD')]]:
        cursor.fetchall.return_value = changed
        with pytest.raises(RelationalClientError, match='changed'):
            column_order.verify(cursor, guard)


def test_form_is_native_fixed_order_list_in_table_context():
    catalog = ADMINISTRATION.catalog(catalog_for_engine('firebird'))
    table = next(row for row in catalog['objects'] if row['resource_kind'] == 'table')
    operation = next(row for row in table['operations'] if row['operation_id'] == 'reorder_columns')
    assert operation['confirmation_required'] and operation['target_required']
    field = operation['form']['fields'][0]
    assert field['initial_value_path'] == ['column_order']
    assert field['array_editor'] == {'item_kind': 'string', 'fixed_items': True}
    # This is a native extension, never a generic fallback for other engines.
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION
    assert not MYSQL_ADMINISTRATION.supports('table', 'reorder_columns')
