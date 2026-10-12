from copy import deepcopy
import pytest
from tools.tests.test_firebird_schema_plan import document, obj
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan


def function(**changes):
    parameters = [{'position': position, 'return_value': position == 0,
                   'field_type': 8, 'field_length': 4, 'field_scale': 0,
                   'field_sub_type': 0, 'field_precision': 0,
                   'mechanism': 0 if position == 0 else 1} for position in (0, 1)]
    return obj('external-function', 'F', **{'parameters': parameters,
        'return_argument': 0, 'entrypoint': 'entry', 'module_name': 'library',
        'description': None, **changes})


def catalog(*rows):
    result = document(list(rows))
    result['rows']['database:database']['native']['catalog_observations'] = [
        {'section': name, 'available': True} for name in ('external-function objects', 'function arguments')]
    return result


def test_structured_creation_and_independent_binding_comment_merge():
    base = catalog()
    result = build_plan(base, catalog(function(description="owner's text", ddl='DROP DATABASE')), base)
    assert result['status'] == 'review-ready', result['blockers']
    assert result['operations'][0]['statements'] == [
        'DECLARE EXTERNAL FUNCTION "F" INTEGER RETURNS INTEGER BY VALUE ENTRY_POINT \'entry\' MODULE_NAME \'library\'',
        'COMMENT ON FUNCTION "F" IS \'owner\'\'s text\'']
    before = catalog(function())
    result = build_plan(before, catalog(function(description='new')), catalog(function(module_name='new_library')))
    assert result['status'] == 'review-ready', result['blockers']
    assert result['operations'][0]['after']['module_name'] == 'new_library'
    assert result['operations'][0]['statements'] == ['COMMENT ON FUNCTION "F" IS \'new\'']
    result = build_plan(before, catalog(function(entrypoint='other')), before)
    assert result['operations'][0]['statements'] == ['ALTER EXTERNAL FUNCTION "F" ENTRY_POINT \'other\'']


@pytest.mark.parametrize('field,value', [('field_length', 8), ('mechanism', 0),
    ('position', True), ('domain', 'D'), ('mode', 'output'), ('field_type', 99), ('return_value', True)])
def test_invalid_signature_blocks_before_mutation(field, value):
    base = catalog(); desired = catalog(function())
    desired['rows']['external-function:F']['native']['parameters'][1][field] = value
    result = build_plan(base, desired, base)
    assert result['status'] == 'blocked' and result['script'] is None


def test_signature_replacement_and_unobserved_catalog_are_not_admitted():
    base = catalog(function()); desired = deepcopy(base)
    desired['rows']['external-function:F']['native']['parameters'][1]['mechanism'] = 2
    result = build_plan(base, desired, base)
    assert result['status'] == 'blocked'
    assert 'removal/recreation' in result['blockers'][0]['reason']
    empty = catalog(); empty['rows']['database:database']['native']['catalog_observations'] = []
    assert build_plan(empty, catalog(function()), empty)['status'] == 'blocked'


@pytest.mark.parametrize('field', ['engine_name', 'package'])
def test_native_family_changes_are_not_ignored(field):
    base = catalog(function()); desired = deepcopy(base)
    desired['rows']['external-function:F']['native'][field] = 'different'
    assert build_plan(base, desired, base)['status'] == 'blocked'
