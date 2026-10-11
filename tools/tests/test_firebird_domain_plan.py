"""Existing-domain properties without guessed datatype or recreation."""
from copy import deepcopy

import pytest

from tools.tests.test_firebird_schema_plan import document, obj
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan


def domain(**native):
    return obj('domain', 'D"ü', **{'default_source': None, 'validation_source': None,
        'not_null': None, 'description': None, 'field_type': 8, **native})


def catalog(*rows):
    result = document(list(rows))
    result['rows']['database:database']['native']['catalog_observations'] = [
        {'section': 'domain objects', 'available': True}]
    return result


def test_domain_property_change_and_check_replacement_have_ordered_native_sql():
    base = catalog(domain(default_source='DEFAULT 1', validation_source='CHECK (VALUE > 0)'))
    desired = catalog(domain(default_source='DEFAULT 3', validation_source='CHECK (VALUE > 2)',
                             not_null=1, description='comment'))
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert plan['operations'][0]['statements'] == [
        'ALTER DOMAIN "D""ü" SET DEFAULT 3\n',
        'ALTER DOMAIN "D""ü" SET NOT NULL',
        'ALTER DOMAIN "D""ü" DROP CONSTRAINT',
        'ALTER DOMAIN "D""ü" ADD CHECK (VALUE > 2)\n',
        'COMMENT ON DOMAIN "D""ü" IS \'comment\'']
    assert not plan['apply_available']


def test_removal_uses_native_property_drop_without_dropping_domain():
    base = catalog(domain(default_source='DEFAULT 1', validation_source='CHECK (VALUE > 0)', not_null=1))
    desired = catalog(domain())
    plan = build_plan(base, desired, base)
    assert plan['operations'][0]['statements'] == [
        'ALTER DOMAIN "D""ü" DROP DEFAULT', 'ALTER DOMAIN "D""ü" DROP NOT NULL',
        'ALTER DOMAIN "D""ü" DROP CONSTRAINT']


def test_independent_live_type_and_comment_changes_preserved():
    base = catalog(domain())
    desired = catalog(domain(default_source='DEFAULT 2'))
    live = catalog(domain(field_type=16, description='live'))
    plan = build_plan(base, desired, live)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert plan['operations'][0]['statements'] == ['ALTER DOMAIN "D""ü" SET DEFAULT 2\n']
    assert plan['operations'][0]['after']['description'] == 'live'
    assert build_plan(base, desired, desired)['status'] == 'no-op'


@pytest.mark.parametrize('native', [
    {'default_source': 'DEFAULT 1; DROP DOMAIN D'},
    {'default_source': '1'}, {'default_source': 'DEFAULT -- empty'},
    {'validation_source': 'CHECK (VALUE > 1); DROP DOMAIN D'},
    {'validation_source': 'CHECK VALUE > 1'},
    {'not_null': True}, {'not_null': 2},
    {'field_type': 16}, {'collation': 'OTHER'}, {'dimensions': 2},
])
def test_unsafe_or_unadmitted_changes_block(native):
    base = catalog(domain())
    plan = build_plan(base, catalog(domain(**native)), base)
    assert plan['status'] == 'blocked' and plan['script'] is None


def test_creation_absence_visibility_and_conflicting_changes_block():
    base = catalog(domain())
    desired = catalog(domain(default_source='DEFAULT 1'))
    assert build_plan(catalog(), base, catalog())['status'] == 'blocked'
    assert build_plan(base, catalog(), base)['status'] == 'blocked'
    assert build_plan(base, desired, catalog(domain(default_source='DEFAULT 2')))['status'] == 'blocked'
    unavailable = deepcopy(base)
    unavailable['rows']['database:database']['native']['catalog_observations'] = []
    assert build_plan(base, desired, unavailable)['status'] == 'blocked'


def test_native_keyword_boundaries_do_not_require_spaces_before_punctuation():
    base = catalog(domain(default_source='DEFAULT-1', validation_source='CHECK(VALUE < 0)'))
    desired = catalog(domain(default_source='DEFAULT-2', validation_source='CHECK(VALUE < 0)'))
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert plan['operations'][0]['statements'] == ['ALTER DOMAIN "D""ü" SET DEFAULT-2\n']


@pytest.mark.parametrize('native', [
    {'default_source': 'DEFAULT 1 DROP NOT NULL'},
    {'default_source': 'DEFAULT 1 SET NOT NULL'},
    {'default_source': 'DEFAULT 1 ADD CHECK (VALUE > 0)'},
    {'default_source': 'DEFAULT 1 TO OTHER'},
    {'default_source': 'DEFAULT 1 TYPE BIGINT'},
    {'validation_source': 'CHECK (VALUE > 0) SET DEFAULT (1)'},
])
def test_embedded_alter_clauses_cannot_change_unrequested_properties(native):
    base = catalog(domain())
    plan = build_plan(base, catalog(domain(**native)), base)
    assert plan['status'] == 'blocked' and plan['script'] is None


def test_clause_words_inside_literals_and_comments_remain_data():
    from pgadmin.cdeadmin.workspace.firebird_domain_plan import clause
    for value in ["DEFAULT 'DROP NOT NULL'", "DEFAULT q'[SET NOT NULL]'",
                  "DEFAULT 1 /* DROP NOT NULL */", "DEFAULT 1 -- TYPE BIGINT"]:
        assert clause(value, 'DEFAULT') == value
    value = 'CHECK /* leading */ (VALUE > 0) /* trailing */'
    assert clause(value, 'CHECK') == value


def scalar(**native):
    return domain(field_sub_type=0, field_scale=0, dimensions=None, **native)


def test_integer_domain_creation_and_native_property_clauses():
    base = catalog()
    wanted = catalog(scalar(default_source='DEFAULT 3', validation_source='CHECK (VALUE > 0)',
                            not_null=1, description='created'))
    plan = build_plan(base, wanted, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert plan['operations'][0]['after']['creation_type']['descriptor'] == {'data_type': 'INTEGER'}
    assert plan['operations'][0]['statements'] == [
        'CREATE DOMAIN "D""ü" AS INTEGER DEFAULT 3\n NOT NULL CHECK (VALUE > 0)\n',
        'COMMENT ON DOMAIN "D""ü" IS \'created\'']


@pytest.mark.parametrize('native', [
    {'field_type': 27, 'field_sub_type': 0, 'field_scale': -2},
    {'field_type': 7, 'field_sub_type': 1, 'field_scale': -2, 'field_precision': 18},
    {'field_type': 8, 'field_precision': 999},
    {'field_type': 8, 'character_length': 5},
    {'field_type': 8, 'segment_length': 5},
    {'field_type': 8, 'dimensions': 1},
    {'field_type': 40, 'character_length': 5},
    {'field_type': 261, 'segment_length': None},
    {'field_type': 8, 'collation': 'UTF8'},
])
def test_creation_rejects_lossy_ambiguous_or_inapplicable_type_facts(native):
    row = domain(**{'field_type': 8, 'field_sub_type': 0, 'field_scale': 0,
                    'dimensions': None, **native})
    base = catalog()
    plan = build_plan(base, catalog(row), base)
    assert plan['status'] == 'blocked' and plan['script'] is None


def character_catalog():
    base = catalog(obj('character-set', 'UTF8', default_collation='UTF8', bytes_per_character=4),
                   obj('collation', 'UTF8', character_set='UTF8'))
    base['rows']['database:database']['native']['catalog_observations'].extend([
        {'section': 'character-set objects', 'available': True},
        {'section': 'collation objects', 'available': True}])
    return base


def test_character_creation_fixes_observed_default_collation_and_dependencies():
    from pgadmin.cdeadmin.workspace.firebird_domain_plan import creation_model
    base = character_catalog()
    native = domain(field_type=37, field_sub_type=0, field_scale=0, dimensions=None,
                    character_length=12, character_set='UTF8')
    row = document([native])['rows']['domain:D"ü']
    typed = creation_model(row, base)
    assert typed['sql'] == 'VARCHAR(12) CHARACTER SET "UTF8" COLLATE "UTF8"'
    assert typed['dependencies'] == ['character-set:UTF8', 'collation:UTF8']
    wrong = deepcopy(row)
    wrong['native']['collation'] = 'UNKNOWN'
    with pytest.raises(ValueError):
        creation_model(wrong, base)
    base['rows']['database:database']['native']['catalog_observations'] = []
    with pytest.raises(ValueError):
        creation_model(row, base)


@pytest.mark.parametrize('source', ['DEFAULT 1 NOT NULL', 'DEFAULT 1 CHECK (VALUE > 0)',
                                    "DEFAULT 'x' COLLATE UTF8"])
def test_creation_default_cannot_supply_other_domain_properties(source):
    base = catalog()
    plan = build_plan(base, catalog(scalar(default_source=source)), base)
    assert plan['status'] == 'blocked' and plan['script'] is None


@pytest.mark.parametrize('kind,precision', [(24, 16), (25, 34)])
def test_decfloat_native_precision_matches_its_storage_type(kind, precision):
    base = catalog()
    row = scalar(field_type=kind, field_precision=precision)
    plan = build_plan(base, catalog(row), base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert plan['operations'][0]['after']['creation_type']['descriptor'] == {
        'data_type': 'DECFLOAT', 'precision': precision}
    row['extensions']['firebird']['native']['field_precision'] = 17
    assert build_plan(base, catalog(row), base)['status'] == 'blocked'


def array_catalog(*rows):
    result = catalog(*rows)
    result['rows']['database:database']['native']['catalog_observations'].append(
        {'section': 'array dimensions', 'available': True})
    return result


def array_domain(**native):
    return domain(**{'field_sub_type': 0, 'field_scale': 0, 'dimensions': 2,
        'array_dimensions': [{'position': 0, 'lower_bound': -2, 'upper_bound': 3},
                             {'position': 1, 'lower_bound': 0, 'upper_bound': 4}], **native})


def test_array_creation_retains_positions_and_signed_bounds():
    base = array_catalog()
    plan = build_plan(base, array_catalog(array_domain()), base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert plan['operations'][0]['statements'] == ['CREATE DOMAIN "D""ü" AS INTEGER[-2:3, 0:4]']


@pytest.mark.parametrize('native', [
    {'dimensions': False}, {'dimensions': True}, {'dimensions': 17}, {'dimensions': -1},
    {'dimensions': 0}, {'array_dimensions': None}, {'array_dimensions': []},
    {'array_dimensions': [{'position': 1, 'lower_bound': 0, 'upper_bound': 1}]},
    {'dimensions': 1, 'array_dimensions': [{'position': 0, 'lower_bound': 3, 'upper_bound': 1}]},
    {'dimensions': 1, 'array_dimensions': [{'position': 0, 'lower_bound': 1, 'upper_bound': 1}]},
    {'dimensions': 1, 'array_dimensions': [{'position': 0, 'lower_bound': -2147483649, 'upper_bound': 1}]},
    {'dimensions': 1, 'array_dimensions': [{'position': 0, 'lower_bound': 0, 'upper_bound': 2147483648}]},
    {'dimensions': 1, 'array_dimensions': [{'position': 0, 'lower_bound': False, 'upper_bound': 1}]},
    {'field_type': 261, 'segment_length': 80},
    {'default_source': 'DEFAULT NULL'},
])
def test_array_creation_refuses_missing_malformed_and_inapplicable_bounds(native):
    base = array_catalog()
    plan = build_plan(base, array_catalog(array_domain(**native)), base)
    assert plan['status'] == 'blocked' and plan['script'] is None


def test_array_creation_requires_native_dimension_visibility():
    plan = build_plan(catalog(), catalog(array_domain()), catalog())
    assert plan['status'] == 'blocked'
    assert 'observation' in plan['blockers'][0]['reason']


def test_character_array_places_bounds_before_charset_and_collation_after_properties():
    base = character_catalog()
    base['rows']['database:database']['native']['catalog_observations'].append(
        {'section': 'array dimensions', 'available': True})
    desired = deepcopy(base)
    row = array_domain(field_type=37, character_length=12, character_set='UTF8', not_null=1)
    desired['rows']['domain:D"ü'] = document([row])['rows']['domain:D"ü']
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert plan['operations'][0]['statements'] == [
        'CREATE DOMAIN "D""ü" AS VARCHAR(12)[-2:3, 0:4] CHARACTER SET "UTF8" NOT NULL COLLATE "UTF8"']
