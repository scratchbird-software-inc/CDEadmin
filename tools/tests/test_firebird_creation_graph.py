from copy import deepcopy
import pytest
from tools.tests.test_firebird_schema_plan import obj
from tools.tests.test_firebird_domain_plan import catalog
from tools.tests.test_firebird_table_plan import table, keyed_table
from tools.tests.test_firebird_view_plan import view
from tools.tests.test_firebird_index_plan import index
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan


def new_domain():
    return obj('domain', 'Z_DOMAIN', field_type=8, field_sub_type=0, field_scale=0,
        dimensions=0, not_null=1, default_source=None, validation_source=None)


def test_new_domain_precedes_table_with_exact_expanded_nullability():
    base = catalog()
    value = table('A_TABLE')
    value['extensions']['firebird']['native']['columns'][0].update(domain='Z_DOMAIN', domain_not_null=1)
    desired = catalog(value, new_domain())
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert [item['resource_id'] for item in plan['operations']] == ['domain:Z_DOMAIN', 'table:A_TABLE']
    assert plan['operations'][1]['native_preconditions']['domain:Z_DOMAIN'] is None
    assert base['rows'].keys() == catalog()['rows'].keys()


def test_foreign_key_add_follows_all_new_table_definitions():
    parent = keyed_table()
    child = table('A_CHILD', constraints=[{'name':'FK', 'constraint_type':'FOREIGN KEY', 'index_name':'FI',
        'referenced_relation':'T', 'referenced_index':'PK_IDX', 'update_rule':'CASCADE', 'delete_rule':'SET NULL'}],
        indexes=[{'name':'FI', 'unique':0, 'inactive':0, 'index_type':0,
        'segments':[{'field_name':'Exact"Column', 'position':0}]}])
    plan = build_plan(catalog(), catalog(child, parent), catalog())
    assert plan['status'] == 'review-ready', plan['blockers']
    assert [item['resource_id'] for item in plan['operations']] == ['table:A_CHILD', 'table:T']
    assert plan['script'].index('CREATE TABLE "T"') < plan['script'].index('ALTER TABLE "A_CHILD" ADD')
    assert plan['operations'][0]['deferred_statements']


def test_declared_view_graph_orders_native_queries_without_parsing_or_executing_them():
    base = catalog()
    desired = catalog(view('A', definition='SELECT 2 FROM "Z"', creation_dependencies=['view:Z']),
                      view('Z', creation_dependencies=[]))
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert [item['resource_id'] for item in plan['operations']] == ['view:Z', 'view:A']
    assert plan['operations'][1]['order_dependencies'] == ['view:Z']


@pytest.mark.parametrize('dependencies', [['view:A'], ['view:missing'], ['view:Z','view:Z'], 'view:Z', [None]])
def test_malformed_missing_and_self_dependencies_block_whole_plan(dependencies):
    base = catalog()
    result = build_plan(base, catalog(view('A', creation_dependencies=dependencies)), base)
    assert result['status'] == 'blocked' and result['script'] is None


def test_cycle_and_undeclared_multiple_views_do_not_guess_order():
    base = catalog()
    for desired in [catalog(view('A', creation_dependencies=['view:Z']), view('Z', creation_dependencies=['view:A'])),
                    catalog(view('A'),view('Z'))]:
        assert build_plan(base, desired, base)['status'] == 'blocked'


def test_existing_object_cannot_be_reordered_by_creation_instruction():
    base = catalog(view('A'))
    desired = deepcopy(base);desired['rows']['view:A']['native']['creation_dependencies']=['database:database']
    assert build_plan(base, desired, base)['status'] == 'blocked'


def test_standalone_index_resolves_columns_of_new_table_without_claiming_observation():
    base = catalog()
    base['rows']['database:database']['native']['catalog_observations'] += [
        {'section': section, 'available': True} for section in ('index objects','system index objects','constraint objects','column objects')]
    desired = deepcopy(base)
    authored = catalog(table('T'), index(segments=[{'field_name':'Exact"Column','position':0}]))
    desired['rows'].update({key:value for key,value in authored['rows'].items() if value['kind'] in {'table','index'}})
    result = build_plan(base, desired, base)
    assert result['status'] == 'review-ready', result['blockers']
    assert [item['kind'] for item in result['operations']] == ['table','index']
    assert result['operations'][1]['native_preconditions']['table:T'] is None


@pytest.mark.parametrize('malformed', [1, True, 'columns', {}])
@pytest.mark.parametrize('field', ['columns', 'constraints'])
def test_malformed_projected_table_arrays_are_plan_blockers(field, malformed):
    base = catalog()
    desired = catalog(table('T', **{field: malformed}))
    result = build_plan(base, desired, base)
    assert result['status'] == 'blocked' and result['script'] is None


@pytest.mark.parametrize('conflict', [False, True])
def test_nested_and_standalone_index_definitions_must_agree_and_emit_once(conflict):
    base = catalog()
    base['rows']['database:database']['native']['catalog_observations'] += [
        {'section': section, 'available': True} for section in
        ('index objects','system index objects','constraint objects','column objects')]
    native = {'name': 'I', 'unique': 0, 'inactive': 0, 'index_type': 0,
              'segments': [{'field_name': 'Exact"Column', 'position': 0}]}
    authored = catalog(table('T', indexes=[native]),
        index(segments=native['segments'], index_type=1 if conflict else 0))
    desired = deepcopy(base)
    desired['rows'].update({key: value for key, value in authored['rows'].items()
                           if value['kind'] in {'table', 'index'}})
    result = build_plan(base, desired, base)
    if conflict:
        assert result['status'] == 'blocked'
        assert any('disagree' in item['reason'] for item in result['blockers'])
    else:
        assert result['status'] == 'review-ready', result['blockers']
        assert result['script'].count('INDEX "I" ON') == 1
        operation = next(item for item in result['operations'] if item['kind'] == 'index')
        assert operation['embedded_index_definition'] and operation['statements'] == []


def test_mutually_referencing_tables_use_one_final_constraint_phase():
    base = catalog()
    tables = []
    for name, other in [('A', 'B'), ('B', 'A')]:
        row = table(name, columns=[{'name': 'ID', 'position': 0, 'field_type': 8,
            'field_sub_type': 0, 'field_scale': 0, 'dimensions': 0, 'not_null': 1}],
            constraints=[{'name': name + '_PK', 'constraint_type': 'PRIMARY KEY', 'index_name': name + '_PK_I'},
                {'name': name + '_FK', 'constraint_type': 'FOREIGN KEY', 'index_name': name + '_FK_I',
                 'referenced_relation': other, 'referenced_index': other + '_PK_I',
                 'update_rule': 'NO ACTION', 'delete_rule': 'NO ACTION'}],
            indexes=[{'name': name + suffix, 'unique': unique, 'inactive': 0, 'index_type': 0,
                      'segments': [{'field_name': 'ID', 'position': 0}], 'description': 'index comment'}
                     for suffix, unique in [('_PK_I', 1), ('_FK_I', 0)]])
        tables.append(row)
    result = build_plan(base, catalog(*tables), base)
    assert result['status'] == 'review-ready', result['blockers']
    assert all('FOREIGN KEY' not in sql for item in result['operations'] for sql in item['statements'])
    assert all(len(item['deferred_statements']) == 2 for item in result['operations'])
    assert result['script'].index('CREATE TABLE "B"') < result['script'].index('ALTER TABLE "A" ADD')
    assert result['script'].index('ALTER TABLE "A" ADD') < result['script'].index('COMMENT ON INDEX "A_FK_I"')
