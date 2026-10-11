from copy import deepcopy
import pytest
from tools.tests.test_firebird_schema_plan import document, obj
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan


def collation(**native):
    return obj('collation', 'C', character_set='UTF8', base_collation='UNICODE',
               attributes=3, specific_attributes='NUMERIC-SORT=1', **native)


def catalog(*rows):
    result = document([obj('character-set', 'UTF8', bytes_per_character=4), *rows])
    result['rows']['database:database']['native']['catalog_observations'] = [
        {'section': section, 'available': True} for section in ('collation objects', 'character-set objects')]
    return result


def test_native_create_and_independent_comment():
    base = catalog()
    result = build_plan(base, catalog(collation(description="owner's comment")), base)
    assert result['status'] == 'review-ready', result['blockers']
    assert result['operations'][0]['statements'] == [
        'CREATE COLLATION "C" FOR "UTF8" FROM EXTERNAL (\'UNICODE\') PAD SPACE CASE INSENSITIVE ACCENT SENSITIVE \'NUMERIC-SORT=1\'',
        'COMMENT ON COLLATION "C" IS \'owner\'\'s comment\'']
    base = catalog(collation(description='old'))
    desired = catalog(collation(description='new'))
    live = deepcopy(base); live['rows']['collation:C']['native']['attributes'] = 1
    result = build_plan(base, desired, live)
    assert result['status'] == 'review-ready', result['blockers']
    assert result['operations'][0]['after']['attributes'] == 1
    assert result['operations'][0]['statements'] == ['COMMENT ON COLLATION "C" IS \'new\'']


@pytest.mark.parametrize('key,value', [('attributes', 8), ('attributes', True), ('character_set', 'ABSENT'), ('specific_attributes', ['invalid']), ('specific_attributes', []), ('specific_attributes', {}), ('specific_attributes', False), ('base_collation', []), ('base_collation', False)])
def test_invalid_and_unobserved_definitions_block(key, value):
    base = catalog(); desired = catalog(collation())
    desired['rows']['collation:C']['native'][key] = value
    assert build_plan(base, desired, base)['status'] == 'blocked'


def test_no_implicit_definition_replacement():
    base = catalog(collation()); desired = deepcopy(base)
    desired['rows']['collation:C']['native']['attributes'] = 1
    result = build_plan(base, desired, base)
    assert result['status'] == 'blocked'
    assert 'removal/recreation' in result['blockers'][0]['reason']


def test_creation_matches_only_admitted_native_version_additions():
    from pgadmin.cdeadmin.workspace.firebird_collation_plan import created_matches, attributes
    expected = {'name': 'C', 'attributes': 3, 'specific_attributes': 'NUMERIC-SORT=1'}
    observed = {**expected, 'specific_attributes': 'COLL-VERSION=153.128;ICU-VERSION=76.1;NUMERIC-SORT=1'}
    assert created_matches(observed, expected)
    assert not created_matches({**observed, 'specific_attributes': observed['specific_attributes'] + ';OTHER=1'}, expected)
    assert not created_matches(observed, {**expected, 'specific_attributes': 'ICU-VERSION=wrong;NUMERIC-SORT=1'})
    assert attributes(r'A=one\;two;B=one\=two;A=last;B=') == {'A': 'last'}


def test_new_collation_precedes_domain_and_table_without_claiming_live_presence():
    from tools.tests.test_firebird_table_plan import table
    domain = obj('domain', 'D', field_type=37, field_sub_type=0,
                 field_scale=0, character_length=12, field_length=48,
                 dimensions=0, not_null=0, default_source=None,
                 validation_source=None, character_set='UTF8', collation='C')
    column = {'name': 'V', 'position': 0, 'domain': 'D', 'domain_not_null': 0,
              'field_type': 37, 'field_sub_type': 0, 'field_scale': 0,
              'character_length': 12, 'field_length': 48, 'dimensions': 0,
              'character_set': 'UTF8', 'collation': 'C'}
    base = catalog()
    desired = catalog(table('A', columns=[column]), domain, collation())
    for item in (base, desired):
        item['rows']['database:database']['native']['catalog_observations'].append(
            {'section': 'domain objects', 'available': True})
    result = build_plan(base, desired, base)
    assert result['status'] == 'review-ready', result['blockers']
    assert [item['kind'] for item in result['operations']] == ['collation', 'domain', 'table']
    assert result['operations'][1]['native_preconditions']['collation:C'] is None
    assert result['operations'][2]['native_preconditions']['domain:D'] is None

    # Native dependency rows do not exhaust domain/collation type references.
    from pgadmin.cdeadmin.workspace.firebird_lifecycle_plan import order_removals
    operations = [{'resource_id': key, 'kind': desired['rows'][key]['kind'],
                   'operation': 'drop'} for key in ('collation:C', 'domain:D', 'table:A')]
    assert [item['resource_id'] for item in order_removals(operations, desired)] == [
        'table:A', 'domain:D', 'collation:C']
