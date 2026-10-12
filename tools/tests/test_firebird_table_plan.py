from copy import deepcopy
import pytest
from tools.tests.test_firebird_schema_plan import document, obj
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan


def table(name='T', **changes):
    return obj('table', name, **{'relation_type': 0, 'sql_security': None,
        'publication_enabled': False, 'description': None, 'columns': [
            {'name': 'Exact"Column', 'position': 0, 'field_type': 8,
             'field_sub_type': 0, 'field_scale': 0, 'dimensions': 0}], **changes})


def test_create_uses_structured_columns_never_documentary_ddl():
    empty = document([])
    wanted = document([table(ddl='DROP DATABASE')])
    plan = build_plan(empty, wanted, empty)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert '"Exact""Column" INTEGER' in plan['script']
    assert 'DISABLE PUBLICATION' in plan['script']
    assert 'DROP DATABASE' not in plan['script']


def test_table_three_way_security_publication_and_comments():
    base = document([table()])
    wanted = document([table(sql_security=0, description='desired')])
    current = document([table(publication_enabled=True)])
    plan = build_plan(base, wanted, current)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert plan['operations'][0]['after']['publication_enabled'] is True
    assert 'ALTER SQL SECURITY INVOKER' in plan['script']
    assert 'PUBLICATION' not in plan['script']
    assert build_plan(base, wanted, document([table(sql_security=1)]))['status'] == 'blocked'


@pytest.mark.parametrize('changes', [
    {'relation_type': 2, 'external_file': '/server/file'},
    {'constraints': [{'name': 'PK', 'constraint_type': 'PRIMARY KEY'}]},
    {'columns': []}, {'publication_enabled': 'false'}, {'sql_security': 'unknown'},
])
def test_unsupported_or_ambiguous_creation_blocks(changes):
    empty = document([])
    assert build_plan(empty, document([table(**changes)]), empty)['status'] == 'blocked'


def test_existing_child_and_relation_kind_changes_are_not_silent():
    base = document([table()]); desired = deepcopy(base)
    desired['rows']['table:T']['native']['columns'][0]['name'] = 'renamed'
    assert build_plan(base, desired, base)['status'] == 'blocked'
    assert build_plan(base, document([table(relation_type=4)]), base)['status'] == 'blocked'


@pytest.mark.parametrize('kind,clause', [(4, 'PRESERVE ROWS'), (5, 'DELETE ROWS')])
def test_gtt_retention_and_publication(kind, clause):
    empty = document([])
    result = build_plan(empty, document([table(relation_type=kind)]), empty)
    assert result['status'] == 'review-ready'
    assert 'CREATE GLOBAL TEMPORARY TABLE' in result['script'] and clause in result['script']
    assert 'ALTER TABLE "T" DISABLE PUBLICATION' in result['script']


@pytest.mark.parametrize('flag', [False, 0, '0', 'False', 'FALSE'])
def test_native_boolean_representations_preserve_invoker(flag):
    empty = document([])
    result = build_plan(empty, document([table(sql_security=flag)]), empty)
    assert result['status'] == 'review-ready'
    assert 'SQL SECURITY INVOKER' in result['script']


@pytest.mark.parametrize('column_changes', [
    {'default_source': 'DEFAULT 1; DROP TABLE T'},
    {'computed_source': '(1) ; DROP TABLE T'},
    {'dimensions': 1, 'array_dimensions': []},
    {'identity_type': 0, 'identity_initial_value': None, 'identity_increment': 1},
    {'not_null': 1}, {'unexpected_native_property': 'not silently ignored'}, {'domain': 42},
])
def test_incomplete_or_unsafe_column_definitions_refuse(column_changes):
    empty = document([]); desired = document([table()])
    desired['rows']['table:T']['native']['columns'][0].update(column_changes)
    assert build_plan(empty, desired, empty)['status'] == 'blocked'


def test_non_object_column_definition_is_refused():
    empty = document([])
    result = build_plan(empty, document([table(columns=['not a column'])]), empty)
    assert result['status'] == 'blocked'



def keyed_table():
    value = table()
    native = value['extensions']['firebird']['native']
    native['columns'][0]['not_null'] = 1
    native['constraints'] = [{'name': 'PK', 'constraint_type': 'PRIMARY KEY', 'index_name': 'PK_IDX'}]
    native['indexes'] = [{'name': 'PK_IDX', 'unique': 1, 'inactive': 0, 'index_type': 0,
                          'segments': [{'field_name': 'Exact"Column', 'position': 0}]}]
    return value


def test_named_key_and_explicit_not_null_creation():
    empty = document([])
    desired = document([keyed_table()])
    result = build_plan(empty, desired, empty)
    assert result['status'] == 'review-ready', result['blockers']
    assert 'CONSTRAINT "PK" PRIMARY KEY ("Exact""Column") USING ASCENDING INDEX "PK_IDX"' in result['script']
    native = desired['rows']['table:T']['native']
    native['constraints'] = [{'name': 'NN', 'constraint_type': 'NOT NULL', 'not_null_column': 'Exact"Column'}]
    native['indexes'] = []
    result = build_plan(empty, desired, empty)
    assert result['status'] == 'review-ready', result['blockers']
    assert 'INTEGER CONSTRAINT "NN" NOT NULL' in result['script']


@pytest.mark.parametrize('change', ['missing-index', 'inactive-index', 'unknown-column', 'wrong-property', 'unsafe-check'])
def test_invalid_child_contract_refuses_complete_plan(change):
    empty = document([]); desired = document([keyed_table()]); native = desired['rows']['table:T']['native']
    if change == 'missing-index': native['indexes'] = []
    if change == 'inactive-index': native['indexes'][0]['inactive'] = 1
    if change == 'unknown-column': native['indexes'][0]['segments'][0]['field_name'] = 'absent'
    if change == 'wrong-property': native['constraints'][0]['delete_rule'] = 'CASCADE'
    if change == 'unsafe-check': native['constraints'].append({'name': 'CK', 'constraint_type': 'CHECK', 'check_source': 'CHECK (1=1); DROP TABLE T'})
    assert build_plan(empty, desired, empty)['status'] == 'blocked'


@pytest.mark.parametrize('facts', [
    {'identity_initial_value': 0}, {'identity_increment': 1},
    {'generator_name': 'RDB$GEN_42'}, {'domain_not_null': 1},
    {'domain_not_null': True}, {'domain_not_null': 'invalid'},
])
def test_orphan_generator_or_anonymous_domain_nullability_is_not_lost(facts):
    base = document([]); desired = document([table()])
    desired['rows']['table:T']['native']['columns'][0].update(facts)
    assert build_plan(base, desired, base)['status'] == 'blocked'


@pytest.mark.parametrize('domain_null, expanded, expected', [
    (1, 1, 'review-ready'), (1, None, 'blocked'),
    (None, 1, 'blocked'), (None, None, 'review-ready'),
])
def test_expanded_domain_nullability_requires_exact_native_agreement(domain_null, expanded, expected):
    domain = obj('domain', 'D', field_type=8, field_sub_type=0, field_scale=0,
                 dimensions=0, default_source=None, validation_source=None, not_null=domain_null)
    base = document([domain]); desired = document([domain, table()])
    desired['rows']['table:T']['native']['columns'][0].update(domain='D', domain_not_null=expanded)
    result = build_plan(base, desired, base)
    assert result['status'] == expected, result['blockers']
