"""Index ownership, namespace, exact segments and three-way preview checks."""
from copy import deepcopy

import pytest

from tools.tests.test_firebird_schema_plan import document, obj
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan
from pgadmin.cdeadmin.providers.firebird.identity import catalog_resource_id


def index(name='I', table='T', **native):
    row = obj('index', name, **{'unique': '0', 'inactive': '0', 'index_type': '0',
        'segments': [{'field_name': 'A', 'position': 0}], 'expression_source': None,
        'condition_source': None, 'description': None, **native})
    row['display_path'] = [table, name]
    row['resource_id'] = catalog_resource_id('index', [table], name)
    return row


def catalog(indices=()):
    columns = []
    for name in ('A', 'B'):
        column = obj('column', name)
        column['display_path'] = ['T', name]
        column['resource_id'] = catalog_resource_id('column', ['T'], name)
        columns.append(column)
    result = document([obj('table', 'T', constraints=[]), *columns, *indices])
    result['rows']['database:database']['native']['catalog_observations'] = [
        {'section': section, 'available': True} for section in (
            'index objects', 'system index objects', 'constraint objects', 'column objects')]
    return result


def test_unique_descending_index_creation_preserves_order_state_comments_and_parent():
    base = catalog()
    desired = catalog([index('I"', unique=1, index_type=1, inactive=1, description="It's an index",
                             segments=[{'field_name': 'B', 'position': 1}, {'field_name': 'A', 'position': 0}])])
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert plan['operations'][0]['statements'] == [
        'CREATE UNIQUE DESCENDING INDEX "I""" ON "T" ("A", "B")',
        'ALTER INDEX "I""" INACTIVE', "COMMENT ON INDEX \"I\"\"\" IS 'It''s an index'"]
    assert plan['operations'][0]['dependencies'] == ['table:T']


def test_state_change_preserves_independent_comment_and_statistics():
    base = catalog([index()])
    desired = catalog([index(inactive=1)])
    current = catalog([index(description='external', statistics='0.1234')])
    plan = build_plan(base, desired, current)
    assert plan['operations'][0]['statements'] == ['ALTER INDEX "I" INACTIVE']
    assert plan['operations'][0]['after']['description'] == 'external'
    assert build_plan(base, base, current)['status'] == 'no-op'


@pytest.mark.parametrize('native', [
    {'segments': [{'field_name': 'A', 'position': 2}]},
    {'segments': [{'field_name': 'A', 'position': 0}, {'field_name': 'A', 'position': 1}]},
    {'segments': [{'field_name': 'MISSING', 'position': 0}]},
    {'unique': True}, {'inactive': '2'},
    {'condition_source': 'WHERE A > 0; DROP TABLE T'},
    {'condition_source': 'A > 0'},
    {'condition_source': 'WHERE /* empty */'},
    {'segments': [], 'expression_source': 'COMPUTED BY (A + 1)'},
])
def test_invalid_incomplete_or_unadmitted_definitions_block(native):
    base = catalog()
    plan = build_plan(base, catalog([index(**native)]), base)
    assert plan['status'] == 'blocked' and plan['script'] is None


def test_existing_definition_changes_require_rebuild_but_expression_state_is_admitted():
    base = catalog([index()])
    assert build_plan(base, catalog([index(unique=1)]), base)['status'] == 'blocked'
    base = catalog([index(segments=[], expression_source='COMPUTED BY (A + 1)')])
    del base['rows']['index:T:I']['native']['segments']  # Native computed-index shape.
    desired = deepcopy(base)
    desired['rows']['index:T:I']['native']['inactive'] = 1
    assert build_plan(base, desired, base)['operations'][0]['statements'] == ['ALTER INDEX "I" INACTIVE']


def test_constraint_index_namespace_collision_and_missing_visibility_block():
    base = catalog([index()])
    desired = catalog([index(inactive=1)])
    current = deepcopy(base)
    current['rows']['table:T']['native']['constraints'] = [{'index_name': 'I'}]
    assert build_plan(base, desired, current)['status'] == 'blocked'
    current = deepcopy(base)
    current['rows']['database:database']['native']['catalog_observations'] = []
    assert build_plan(base, desired, current)['status'] == 'blocked'
    base = catalog()
    current = catalog([index(table='OTHER')])
    assert build_plan(base, catalog([index()]), current)['status'] == 'blocked'


@pytest.mark.parametrize('expression,condition', [
    ('("A" + 1)', None),
    (None, 'WHERE "B" > 0 -- final comment'),
    ("(CHAR_LENGTH(q'[); quoted text]'))", 'WHERE "A" IS NOT NULL'),
])
def test_computed_and_partial_creation_preserves_native_source(expression, condition):
    base = catalog()
    native = {'expression_source': expression, 'condition_source': condition}
    if expression:
        native['segments'] = []
    plan = build_plan(base, catalog([index(**native)]), base)
    assert plan['status'] == 'review-ready', plan['blockers']
    statement = plan['operations'][0]['statements'][0]
    if expression:
        assert 'COMPUTED BY ' + expression + '\n' in statement
    if condition:
        assert statement.endswith(condition + '\n')
    assert plan['apply_available'] is False


@pytest.mark.parametrize('expression,condition', [
    ('("A" + 1); DROP TABLE T', None),
    ('("A" + 1) /* unterminated', None),
    ('("A" + 1', None),
    ('("A" + 1)', 'WHERE "A" > 0); DROP TABLE T'),
    ('("A" + 1)', "WHERE \"A\" = 'unclosed"),
])
def test_expression_boundary_failure_blocks_entire_script(expression, condition):
    base = catalog()
    plan = build_plan(base, catalog([index(segments=[], expression_source=expression,
                                           condition_source=condition)]), base)
    assert plan['status'] == 'blocked'
    assert plan['script'] is None


def test_computed_source_cannot_hide_an_unrequested_partial_predicate():
    base = catalog()
    desired = catalog([index(segments=[], expression_source='("A" + 1) WHERE ("B" > 0)')])
    assert build_plan(base, desired, base)['status'] == 'blocked'
