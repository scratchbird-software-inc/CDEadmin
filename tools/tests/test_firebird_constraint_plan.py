from copy import deepcopy
import pytest
from tools.tests.test_firebird_schema_plan import document, obj
from tools.tests.test_firebird_table_plan import table
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan


def constraint(name='CK', **changes):
    row = obj('constraint', name, **{'constraint_type': 'CHECK', 'check_source': 'CHECK ("Exact""Column" > 0)', **changes})
    row['display_path'] = ['T', name]; row['resource_id'] = 'constraint:T:' + name
    return row


def test_check_creation_and_replacement_are_whole_native_statements():
    base = document([table()]); desired = document([table(), constraint()])
    created = build_plan(base, desired, base)
    assert created['status'] == 'review-ready', created['blockers']
    assert created['operations'][0]['statements'] == ['ALTER TABLE "T" ADD CONSTRAINT "CK" CHECK ("Exact""Column" > 0)\n']
    changed = document([table(), constraint(check_source='CHECK ("Exact""Column" >= 0)')])
    replaced = build_plan(desired, changed, desired)
    assert replaced['status'] == 'review-ready', replaced['blockers']
    assert replaced['operations'][0]['statements'][0] == 'ALTER TABLE "T" DROP CONSTRAINT "CK"'
    assert any('DROP and ADD' in text for text in replaced['warnings'])


def test_exact_unique_backing_index_preserves_direction_and_comment():
    index = {'name': 'UX', 'unique': 1, 'inactive': 0, 'index_type': 1,
        'segments': [{'field_name': 'Exact"Column', 'position': 0}], 'description': 'key comment'}
    base = document([table()]); desired = document([table(), constraint(constraint_type='UNIQUE', check_source=None, index_name='UX', backing_index=index)])
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert 'USING DESCENDING INDEX "UX"' in plan['script']
    assert 'COMMENT ON INDEX "UX"' in plan['script']


def test_matching_standalone_backing_projection_emits_only_constraint_sql():
    index = {'name': 'UX', 'unique': 1, 'inactive': 0, 'index_type': 1,
        'segments': [{'field_name': 'Exact"Column', 'position': 0}], 'description': 'key comment'}
    projection = obj('index', 'UX', **{key: value for key, value in index.items() if key != 'name'})
    projection.update(resource_id='index:T:UX', display_path=['T', 'UX'])
    base = document([table()])
    desired = document([table(), constraint(constraint_type='UNIQUE', check_source=None,
        index_name='UX', backing_index=index), projection])
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert [item['resource_id'] for item in plan['operations']] == ['constraint:T:CK', 'index:T:UX']
    assert plan['operations'][1]['embedded_index_definition']
    assert plan['operations'][1]['statements'] == []
    assert plan['script'].count('USING DESCENDING INDEX "UX"') == 1
    desired['rows']['index:T:UX']['native']['index_type'] = 0
    assert build_plan(base, desired, base)['status'] == 'blocked'


@pytest.mark.parametrize('changes', [{'description': 'not supported'}, {'check_source': 'CHECK (1=1); DROP TABLE T'},
    {'constraint_type': 'NOT NULL', 'check_source': None, 'not_null_column': 'Exact"Column'},
    {'constraint_type': 'UNIQUE', 'check_source': None, 'index_name': 'UX'},
    {'update_rule': 'CASCADE'}])
def test_incomplete_or_inapplicable_definition_blocks(changes):
    base = document([table()]); result = build_plan(base, document([table(), constraint(**changes)]), base)
    assert result['status'] == 'blocked' and result['script'] is None


def test_new_table_embedded_check_is_emitted_once():
    child = constraint()
    parent = table(constraints=[{'name': 'CK', 'constraint_type': 'CHECK', 'check_source': 'CHECK ("Exact""Column" > 0)'}])
    base = document([]); desired = document([parent, child])
    result = build_plan(base, desired, base)
    assert result['status'] == 'review-ready', result['blockers']
    assert result['script'].count('CONSTRAINT "CK" CHECK') == 1
    assert result['operations'][1]['embedded_constraint_definition']
    desired = deepcopy(desired)
    desired['rows']['constraint:T:CK']['native']['check_source'] = 'CHECK (1=1)'
    assert build_plan(base, desired, base)['status'] == 'blocked'


def test_self_reference_uses_observed_key_without_recreating_it():
    index = {'name': 'PK_INDEX', 'unique': 1, 'inactive': 0, 'index_type': 0,
        'segments': [{'field_name': 'Exact"Column', 'position': 0}]}
    parent = table(constraints=[{'name': 'PK', 'constraint_type': 'PRIMARY KEY', 'index_name': 'PK_INDEX'}], indexes=[index])
    backing = {**index, 'name': 'FK_INDEX', 'unique': 0}
    base = document([parent]); desired = document([parent, constraint('FK', constraint_type='FOREIGN KEY',
        check_source=None, index_name='FK_INDEX', backing_index=backing,
        referenced_relation='T', referenced_index='PK_INDEX', update_rule='CASCADE', delete_rule='NO ACTION')])
    result = build_plan(base, desired, base)
    assert result['status'] == 'review-ready', result['blockers']
    assert 'REFERENCES "T" ("Exact""Column")' in result['script']
    assert 'ADD CONSTRAINT "PK"' not in result['script']


def test_new_table_not_null_projection_has_no_second_native_operation():
    parent = table(columns=[{'name': 'C', 'position': 0, 'field_type': 8, 'field_sub_type': 0,
        'field_scale': 0, 'dimensions': 0, 'not_null': 1}], constraints=[
        {'name': 'NN', 'constraint_type': 'NOT NULL', 'not_null_column': 'C'}])
    child = constraint('NN', constraint_type='NOT NULL', check_source=None, not_null_column='C')
    base = document([]); desired = document([parent, child])
    result = build_plan(base, desired, base)
    assert result['status'] == 'review-ready', result['blockers']
    assert result['script'].count('CONSTRAINT "NN" NOT NULL') == 1
